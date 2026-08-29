"""T_TEST.7 pt.2 — IDOR matrix built from the router, not from a hand list.

The manual audit of 2026-07-29 found no classic IDOR: ownership is checked
everywhere, nested resources are scoped, identifiers are UUID v4. Nothing held
that state in place, though — automation does not catch IDOR by itself.
Schemathesis (T_TEST.4) asks "is it a 500?", and to it a 403 and a 200 look
equally valid. ZAP baseline is passive and models no authorisation at all.

So the property is asserted directly: every route that takes a path parameter
is called by a stranger against somebody else's object, and must answer 403 or
404 — never 200, never 500.

The table below is the whole point. It is compared against `app.routes` in both
directions, so a new endpoint with a path parameter fails this file by the mere
fact of existing until somebody writes down what a stranger should get from it.
That is the check the next author gets for free; the 41 manual 403-assertions
scattered across 18 files only ever covered what somebody remembered to cover.

Three verdicts, because "denied" is not the only honest answer:

  DENIED      — foreign object, must refuse.
  PUBLIC      — deliberately readable (or usable) by a stranger; the reason is
                written next to it, and the assertion drops to "does not 500".
  CAPABILITY  — the unguessable token *is* the authorisation (invite links).
                Asserting 403 here would be asserting the opposite of the
                feature; what is asserted instead is that an unknown token is a
                404 and discloses nothing.
"""
from __future__ import annotations

import uuid as uuidlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import make_account

DENIED = "denied"
PUBLIC = "public"
CAPABILITY = "capability"


@dataclass(frozen=True)
class Case:
    """One row of the matrix: what a stranger must get, and what to send."""

    kind: str
    why: str
    json: dict | None = None
    data: dict | None = None
    files: dict | None = None
    headers: dict = field(default_factory=dict)
    # Extra statuses accepted for this row only, each with its reason in `why`.
    also_ok: tuple[int, ...] = ()


# Bodies are supplied wherever the endpoint requires one. Without them FastAPI
# answers 422 before the handler runs, and a 422 would let a missing ownership
# check pass this test — the request would never have reached it.
MATRIX: dict[tuple[str, str], Case] = {
    # ---- deals ---------------------------------------------------------
    ("POST", "/api/deals/{deal_id}/event"): Case(
        DENIED, "only participants add events", json={"event_type": "handoff"}
    ),
    ("POST", "/api/deals/{deal_id}/confirm"): Case(DENIED, "only the sender confirms"),
    ("GET", "/api/deals/{deal_id}"): Case(DENIED, "deal detail is participants-only"),
    ("GET", "/api/deals/{deal_id}/chain"): Case(
        DENIED, "chain status names the deal's events"
    ),
    # ---- trips (T_UX.19) -----------------------------------------------
    ("POST", "/api/trips/{trip_id}/cancel"): Case(
        DENIED, "withdrawing a stranger's trip"
    ),
    ("POST", "/api/deals/{deal_id}/cards"): Case(
        DENIED,
        "raising a card in a stranger's deal",
        json={"kind": "issue.reported", "payload": {"category": "delay"}},
    ),
    # ---- terms (T3.35) -------------------------------------------------
    ("GET", "/api/deals/{deal_id}/terms"): Case(
        DENIED, "the contract states the price two other people agreed"
    ),
    ("POST", "/api/deals/{deal_id}/terms"): Case(
        DENIED,
        "proposing terms into a stranger's deal",
        json={
            "weight_kg": 2,
            "price_total": 50,
            "declared_value": 500,
            "currency": "USD",
            "payment_method": "cash",
        },
    ),
    # ---- DealVault -----------------------------------------------------
    ("GET", "/api/deals/{deal_id}/dealvault"): Case(
        DENIED, "the vault is the deal's private content"
    ),
    ("POST", "/api/deals/{deal_id}/dealvault/messages/{message_id}/ack"): Case(
        DENIED,
        "answering a card in a stranger's deal — the rule the UI only decorates",
        json={"decision": "accepted"},
    ),
    ("POST", "/api/deals/{deal_id}/dealvault/messages"): Case(
        DENIED, "writing into a stranger's vault", json={"text": "idor probe"}
    ),
    ("POST", "/api/deals/{deal_id}/dealvault/messages/share-address"): Case(
        DENIED,
        "sharing my address into a stranger's vault; 429 accepted because the "
        "5/hour limiter sits in front of the ownership check and answering "
        "before authorisation is itself non-disclosure",
        json={},
        also_ok=(429,),
    ),
    ("POST", "/api/deals/{deal_id}/dealvault/messages/{message_id}/attachments"): Case(
        DENIED,
        "participation is checked before a single byte reaches R2",
        files={"file": ("probe.txt", b"probe", "text/plain")},
        data={"kind": "doc"},
    ),
    ("POST", "/api/deals/{deal_id}/dealvault/messages/{message_id}/decrypt-for-me"): Case(
        DENIED, "server-mediated decrypt is the most valuable thing to steal"
    ),
    # ---- threshold -----------------------------------------------------
    ("POST", "/api/threshold/dealvault/messages/{message_id}/reveal-my-share"): Case(
        DENIED, "a share of a session key for a message that is not mine"
    ),
    ("POST", "/api/threshold/disputes/{deal_id}/arbiter-reveal"): Case(
        DENIED, "arbiter-only permission, refused at the dependency"
    ),
    # ---- verification --------------------------------------------------
    ("POST", "/api/deals/{deal_id}/verification"): Case(
        DENIED, "only participants ask each other for documents",
        json={"target_role": "carrier"},
    ),
    ("POST", "/api/deals/{deal_id}/verification/{req_id}/respond"): Case(
        DENIED, "answering a request addressed to someone else",
        json={"action": "declined"},
    ),
    ("POST", "/api/deals/{deal_id}/verification/{req_id}/submit-document"): Case(
        DENIED,
        "participation is checked before the document is stored",
        files={"file": ("id.jpg", b"\xff\xd8\xff\xdb probe", "image/jpeg")},
        data={"doc_type": "passport", "doc_country": "PL"},
    ),
    ("POST", "/api/deals/{deal_id}/verification/{req_id}/request-additional"): Case(
        DENIED, "escalating a stranger's verification thread"
    ),
    ("POST", "/api/deals/{deal_id}/verification/{req_id}/escalate"): Case(
        DENIED, "opening a dispute off someone else's request",
        json={"reason": "idor probe"},
    ),
    ("GET", "/api/deals/{deal_id}/verification-requests"): Case(
        DENIED, "who asked whom for identity documents is deal-private"
    ),
    ("POST", "/api/verifications/{badge_id}/revoke"): Case(
        DENIED, "revoking a badge issued by and about other people"
    ),
    ("GET", "/api/users/{user_id}/verifications"): Case(
        PUBLIC,
        "levels without document contents — the same summary the profile and "
        "trip cards show; a marketplace where nobody can check anybody is one "
        "where nobody deals",
    ),
    # ---- participants --------------------------------------------------
    ("POST", "/api/deals/{deal_id}/invite-recipient"): Case(
        DENIED, "minting an invite into a stranger's deal"
    ),
    ("POST", "/api/deals/{deal_id}/participants/{user_id}/revoke"): Case(
        DENIED, "kicking a participant out of a deal that is not mine"
    ),
    ("GET", "/api/deals/{deal_id}/participants"): Case(
        DENIED, "the participant list names people and their roles"
    ),
    ("POST", "/api/deals/join/{token}"): Case(
        CAPABILITY, "the recipient invite token is the authorisation"
    ),
    # ---- disputes / arbiter --------------------------------------------
    ("POST", "/api/deals/{deal_id}/dispute"): Case(
        DENIED, "only participants dispute a deal", json={"reason": "idor probe"}
    ),
    ("POST", "/api/disputes/{dispute_id}/grant-access"): Case(
        DENIED, "consent to arbiter access belongs to the parties"
    ),
    ("POST", "/api/disputes/{dispute_id}/revoke-access"): Case(
        DENIED, "withdrawing somebody else's consent"
    ),
    ("POST", "/api/disputes/{dispute_id}/claim"): Case(
        DENIED, "arbiter-only permission"
    ),
    ("POST", "/api/disputes/{dispute_id}/resolve"): Case(
        DENIED, "arbiter-only permission", json={"verdict": "idor probe"}
    ),
    ("GET", "/api/admin/deals/{deal_id}/vault"): Case(
        DENIED, "the whole point of T3.2: reading a vault as staff is gated"
    ),
    # T3.42 — offering, revoking and reading the role journal. All three are
    # superuser-only, and the journal deliberately so: who granted somebody
    # power over other people's data is not public.
    ("POST", "/api/admin/users/{user_id}/roles"): Case(
        DENIED, "superuser-only", json={"role": "arbiter"}
    ),
    ("DELETE", "/api/admin/users/{user_id}/roles/arbiter"): Case(
        DENIED, "superuser-only"
    ),
    ("GET", "/api/admin/users/{user_id}/roles"): Case(DENIED, "superuser-only"),
    ("DELETE", "/api/admin/users/{user_id}"): Case(DENIED, "superuser-only"),
    # ---- platform parameters (T3.40) -----------------------------------
    ("GET", "/api/admin/params/{key}/history"): Case(
        DENIED, "who changed the fee and when is superuser-only"
    ),
    # ---- notices (admin CRUD) ------------------------------------------
    ("PATCH", "/api/admin/route-notes/{note_id}"): Case(
        DENIED, "superuser-only", json={"headline": "idor probe"}
    ),
    ("DELETE", "/api/admin/route-notes/{note_id}"): Case(DENIED, "superuser-only"),
    ("DELETE", "/api/admin/platform-notices/{notice_id}"): Case(
        DENIED, "superuser-only"
    ),
    # ---- addresses -----------------------------------------------------
    ("PATCH", "/api/me/addresses/{address_id}"): Case(
        DENIED, "a delivery address decides where a parcel goes",
        json={"label": "idor probe"},
    ),
    ("POST", "/api/me/addresses/{address_id}/default"): Case(
        DENIED, "promoting a stranger's address to their default"
    ),
    ("DELETE", "/api/me/addresses/{address_id}"): Case(
        DENIED, "deleting a stranger's address"
    ),
    # ---- inquiries -----------------------------------------------------
    ("POST", "/api/trips/{trip_id}/inquiry"): Case(
        PUBLIC,
        "opening a thread about a published listing is what the marketplace is "
        "for; the endpoint is idempotent per (trip, sender)",
    ),
    ("GET", "/api/inquiries/{inquiry_id}/messages"): Case(
        DENIED, "the thread is private between its two sides"
    ),
    ("POST", "/api/inquiries/{inquiry_id}/messages"): Case(
        DENIED, "writing into a stranger's thread", json={"text": "idor probe"}
    ),
    ("POST", "/api/inquiries/{inquiry_id}/messages/share-address"): Case(
        DENIED,
        "same limiter as the vault variant, same reasoning",
        json={},
        also_ok=(429,),
    ),
    # ---- social / nostr / trips ----------------------------------------
    ("POST", "/api/invites/{token}/accept"): Case(
        CAPABILITY, "an invite link is meant to be handed to strangers"
    ),
    ("POST", "/api/nostr/republish/{trip_id}"): Case(
        DENIED, "republishing under the platform key is a staff permission"
    ),
    ("GET", "/api/trips/{trip_id}/nostr-event"): Case(
        PUBLIC,
        "the event is the public form of a public listing — it is what the "
        "relays already carry; 503 when publishing is switched off",
        also_ok=(503,),
    ),
    # ---- public profile surface ----------------------------------------
    ("GET", "/api/users/{user_id}/uba"): Case(
        PUBLIC, "activity level is shown on trip cards and profiles by design"
    ),
    ("GET", "/api/users/{user_id}/trust-metrics"): Case(
        PUBLIC, "the counters behind the public identity page"
    ),
    ("GET", "/api/identities/{npub}"): Case(
        PUBLIC, "T3.18 — readable without an account at all, by decision"
    ),
    # ---- passkeys ------------------------------------------------------
    ("DELETE", "/api/auth/passkey/{credential_id}"): Case(
        DENIED,
        "removing somebody's authenticator; the step-up header is required by "
        "the signature, so a placeholder is sent to reach the ownership check "
        "that runs before the grant is consumed",
        headers={"X-Step-Up-Token": "not-a-real-grant"},
    ),
}


def _parameterised_routes() -> set[tuple[str, str]]:
    """Every mounted route that takes a path parameter."""
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or "{" not in route.path:
            continue
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            found.add((method, route.path))
    return found


# ---------------------------------------------------------------------------
# Fixtures: one stranger, one full set of somebody else's objects.
#
# Both are built once per pytest process and cached in a module global rather
# than rebuilt per test. There are ~40 parameterised cases here, and a
# per-case fixture would mean forty trips, forty deals and forty disputes for a
# file whose every request is *supposed to be refused* — nothing it does can
# change the state it reads. Caching plain strings (ids, a bearer token) also
# keeps this clear of the event-loop trouble a module-scoped async fixture
# would bring, since the DB session and the HTTP client stay per-test.
#
# The one test that mutates — arbiter claims a dispute, party revokes consent —
# gets its own fresh deal below, so it cannot depend on file order.
# ---------------------------------------------------------------------------

_STRANGER: dict | None = None
_VICTIM: dict | None = None
_STRANGER_DEAL: str | None = None


async def _register(client, prefix: str) -> dict:
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    email = unique_email(prefix)
    resp = await make_account({"email": email, "password": SEED_PASSWORD, "display_name": prefix.title()},
    )
    assert resp.status_code == 201, resp.text
    token = await _login(client, email)
    return {
        "id": uuidlib.UUID(resp.json()["id"]),
        "email": email,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def stranger(client) -> dict:
    """User A: a fresh account with no connection, deal or invite to anyone."""
    global _STRANGER
    if _STRANGER is None:
        _STRANGER = await _register(client, "idor-stranger")
    return _STRANGER


@pytest_asyncio.fixture
async def victim(client, carrier_headers, sender_headers, session_maker, seed_carrier, seed_sender):
    """User B's world: one of everything, none of it the stranger's.

    Built through the API where an endpoint exists, because that is what
    produces the same rows a real user would leave behind. The rest goes in
    directly — a badge, a passkey and the two notice kinds have no create path
    a test can reach without a document scanner, an authenticator or a
    superuser.
    """
    global _VICTIM
    if _VICTIM is not None:
        return _VICTIM

    from sqlalchemy import select

    from app.models.notices import (
        NoticeSeverity,
        NoticeSurface,
        PlatformNotice,
        RouteNote,
        RouteStatus,
    )
    from app.models.verification import (
        VerificationBadge,
        VerificationLevel,
        VerificationSource,
    )
    from app.models.user import User
    from app.models.webauthn import WebAuthnCredential

    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "IDR",
            "destination": "MTX",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat(),
            "capacity": 3.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201, trip.text
    trip_id = trip.json()["id"]

    deal = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000077",
                "origin": "IDR",
                "destination": "MTX",
                "category": "document",
                "declared_value": 250.0,
            },
        },
    )
    assert deal.status_code == 201, deal.text
    deal_id = deal.json()["id"]

    message = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "victim message"},
    )
    assert message.status_code == 201, message.text
    message_id = message.json()["id"]

    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=sender_headers,
        json={"target_role": "carrier"},
    )
    assert req.status_code == 201, req.text
    req_id = req.json()["id"]

    dispute = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "victim dispute for the matrix"},
    )
    assert dispute.status_code == 201, dispute.text
    dispute_id = dispute.json()["id"]

    address = await client.post(
        "/api/me/addresses",
        headers=sender_headers,
        json={"label": "Victim home", "country_iso": "PL", "city": "Warsaw"},
    )
    assert address.status_code == 201, address.text
    address_id = address.json()["id"]

    inquiry = await client.post(
        f"/api/trips/{trip_id}/inquiry", headers=sender_headers
    )
    assert inquiry.status_code == 201, inquiry.text
    inquiry_id = inquiry.json()["id"]

    badge_id = uuidlib.uuid4()
    note_id = uuidlib.uuid4()
    notice_id = uuidlib.uuid4()
    credential_id = uuidlib.uuid4()
    async with session_maker() as db:
        victim_user = (
            await db.execute(select(User).where(User.id == seed_carrier.id))
        ).scalar_one()
        npub = victim_user.nostr_pubkey or "0" * 64

        db.add(
            VerificationBadge(
                id=badge_id,
                subject_id=seed_carrier.id,
                level=VerificationLevel.peer,
                source=VerificationSource.peer,
                verified_by_id=seed_sender.id,
                in_deal_id=uuidlib.UUID(deal_id),
            )
        )
        db.add(
            RouteNote(
                id=note_id,
                origin_iso="IDR",
                destination_iso="MTX",
                status=RouteStatus.attention,
                severity=NoticeSeverity.info,
                headline="matrix fixture note",
            )
        )
        db.add(
            PlatformNotice(
                id=notice_id,
                key=f"idor-matrix-{notice_id.hex[:8]}",
                severity=NoticeSeverity.info,
                target_surface=NoticeSurface.footer,
                headline="matrix fixture notice",
            )
        )
        db.add(
            WebAuthnCredential(
                id=credential_id,
                user_id=seed_carrier.id,
                credential_id=uuidlib.uuid4().bytes,
                public_key=b"matrix-fixture-public-key",
            )
        )
        await db.commit()

    _VICTIM = {
        "deal_id": deal_id,
        "trip_id": trip_id,
        "message_id": message_id,
        "req_id": req_id,
        "dispute_id": dispute_id,
        "address_id": address_id,
        "inquiry_id": inquiry_id,
        "badge_id": str(badge_id),
        "note_id": str(note_id),
        "notice_id": str(notice_id),
        "credential_id": str(credential_id),
        "user_id": str(seed_carrier.id),
        "npub": npub,
        # T3.40 — a real parameter name: the row asserts that a stranger is
        # refused, not that an unknown key is a 404.
        "key": "carrier_fee_percent",
        # Only the capability rows use this, and they want an unknown one.
        "token": uuidlib.uuid4().hex,
    }
    return _VICTIM


async def _call(client, method: str, url: str, case: Case, headers: dict):
    merged = {**headers, **case.headers}
    kwargs: dict = {"headers": merged}
    if case.json is not None:
        kwargs["json"] = case.json
    if case.files is not None:
        kwargs["files"] = case.files
    if case.data is not None:
        kwargs["data"] = case.data
    return await client.request(method, url, **kwargs)


# ---------------------------------------------------------------------------
# The matrix itself
# ---------------------------------------------------------------------------


def test_every_parameterised_route_is_in_the_matrix():
    """A new endpoint with a path parameter fails here until it is classified.

    Both directions: unlisted routes are the gap this file exists to close, and
    stale rows are how a matrix quietly stops describing the app.
    """
    mounted = _parameterised_routes()
    listed = set(MATRIX)

    missing = sorted(f"{m} {p}" for m, p in mounted - listed)
    stale = sorted(f"{m} {p}" for m, p in listed - mounted)

    assert not missing, (
        "endpoints with path parameters and no IDOR expectation:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd each to MATRIX with DENIED, PUBLIC or CAPABILITY and a reason."
    )
    assert not stale, (
        "MATRIX rows for routes that no longer exist:\n  " + "\n  ".join(stale)
    )


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(k for k, v in MATRIX.items() if v.kind == DENIED),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
async def test_foreign_object_is_refused(client, stranger, victim, method, path):
    case = MATRIX[(method, path)]
    url = path.format(**victim)

    resp = await _call(client, method, url, case, stranger["headers"])

    allowed = (403, 404, *case.also_ok)
    assert resp.status_code in allowed, (
        f"{method} {path} answered {resp.status_code} to a stranger holding a "
        f"foreign id — expected one of {allowed}. Reason on file: {case.why}. "
        f"Body: {resp.text[:300]}"
    )


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(k for k, v in MATRIX.items() if v.kind == PUBLIC),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
async def test_public_routes_answer_without_breaking(client, stranger, victim, method, path):
    """Public is a decision, not an absence of one — so it is still asserted.

    A 500 here is the failure mode that matters: these are the routes an
    anonymous or unrelated caller reaches by design, so they are the ones a
    malformed identifier reaches first (see the NUL-byte bug in `T_KEYS.1`).
    """
    case = MATRIX[(method, path)]
    url = path.format(**victim)

    resp = await _call(client, method, url, case, stranger["headers"])

    assert resp.status_code in (200, 201, 400, 404, *case.also_ok), (
        f"{method} {path} answered {resp.status_code}: {resp.text[:300]}"
    )
    assert resp.status_code < 500, f"{method} {path} broke: {resp.text[:300]}"


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(k for k, v in MATRIX.items() if v.kind == CAPABILITY),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
async def test_unknown_capability_token_discloses_nothing(
    client, stranger, victim, method, path
):
    """An invite token is meant to work for whoever holds it — so the property
    worth asserting is the other one: an unknown token is a flat 404."""
    case = MATRIX[(method, path)]
    url = path.format(**victim)  # `token` is a fresh random hex

    resp = await _call(client, method, url, case, stranger["headers"])

    assert resp.status_code == 404, (
        f"{method} {path} answered {resp.status_code} to an unknown token: "
        f"{resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# Nested substitution — own parent, foreign child. Where it usually leaks.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def stranger_deal(client, stranger, carrier_headers) -> str:
    """A deal the stranger legitimately owns, to put in front of foreign ids.

    Cached like the rest: the four tests below only make calls that must be
    refused, so none of them changes what the next one sees.
    """
    global _STRANGER_DEAL
    if _STRANGER_DEAL is not None:
        return _STRANGER_DEAL

    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "OWN",
            "destination": "MIN",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=11)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201, trip.text
    deal = await client.post(
        "/api/deals/match",
        headers=stranger["headers"],
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000000078",
                "origin": "OWN",
                "destination": "MIN",
                "category": "document",
                "declared_value": 60.0,
            },
        },
    )
    assert deal.status_code == 201, deal.text
    _STRANGER_DEAL = deal.json()["id"]
    return _STRANGER_DEAL


async def test_own_deal_with_foreign_message_is_404(client, stranger, victim, stranger_deal):
    """The classic shape: authorisation passes on the parent, the child is
    somebody else's. `_get_deal_as_participant` says yes, and then the message
    lookup has to say no by itself."""
    resp = await client.post(
        f"/api/deals/{stranger_deal}/dealvault/messages/{victim['message_id']}/decrypt-for-me",
        headers=stranger["headers"],
    )
    assert resp.status_code == 404, resp.text


async def test_own_deal_with_foreign_verification_request_is_404(
    client, stranger, victim, stranger_deal
):
    resp = await client.post(
        f"/api/deals/{stranger_deal}/verification/{victim['req_id']}/respond",
        headers=stranger["headers"],
        json={"action": "declined"},
    )
    assert resp.status_code == 404, resp.text


async def test_own_deal_with_foreign_participant_is_refused(
    client, stranger, stranger_deal, seed_carrier
):
    """Revoking somebody who is not in my deal must not touch their row
    elsewhere. 404 or 403 — both say "not here"; a 200 would mean the
    `user_id` was taken on trust."""
    resp = await client.post(
        f"/api/deals/{stranger_deal}/participants/{seed_carrier.id}/revoke",
        headers=stranger["headers"],
    )
    assert resp.status_code in (403, 404), resp.text


async def test_foreign_message_share_is_not_reachable_by_id_alone(
    client, stranger, victim, stranger_deal
):
    """Same substitution against the upload path: own deal, foreign message."""
    resp = await client.post(
        f"/api/deals/{stranger_deal}/dealvault/messages/{victim['message_id']}/attachments",
        headers=stranger["headers"],
        files={"file": ("probe.txt", b"probe", "text/plain")},
        data={"kind": "doc"},
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Roles: staff paths are guarded by more than a role flag.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def arbiter(client, session_maker) -> dict:
    from app.models.user import User

    who = await _register(client, "idor-arbiter")
    async with session_maker() as db:
        u = await db.get(User, who["id"])
        u.role = "arbiter"
        await db.commit()
    # Re-login so the token is minted after the promotion.
    from tests.conftest import _login

    token = await _login(client, who["email"])
    who["headers"] = {"Authorization": f"Bearer {token}"}
    return who


@pytest_asyncio.fixture
async def disputed_deal(client, carrier_headers, sender_headers) -> dict:
    """A fresh deal with a fresh open dispute — deliberately NOT the cached one.

    These two tests claim and revoke, and a claim can only happen once. Sharing
    the matrix's dispute would make them pass or fail by file order, which is
    exactly the property ENVIRONMENT §7 forbids.
    """
    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "ARB",
            "destination": "GNT",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=13)).isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201, trip.text
    deal = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000000079",
                "origin": "ARB",
                "destination": "GNT",
                "category": "document",
                "declared_value": 40.0,
            },
        },
    )
    assert deal.status_code == 201, deal.text
    deal_id = deal.json()["id"]

    dispute = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "consent lifecycle test"},
    )
    assert dispute.status_code == 201, dispute.text
    return {"deal_id": deal_id, "dispute_id": dispute.json()["id"]}


async def test_arbiter_without_claim_cannot_read_vault(client, arbiter, disputed_deal):
    """The role opens the door to the endpoint, not to the deal."""
    resp = await client.get(
        f"/api/admin/deals/{disputed_deal['deal_id']}/vault", headers=arbiter["headers"]
    )
    assert resp.status_code == 403, resp.text


async def test_arbiter_loses_vault_access_when_consent_is_revoked(
    client, arbiter, disputed_deal, sender_headers
):
    """T3.2 in one test: claiming is not consent, and consent is withdrawable.

    The grant here is the automatic one from whoever opened the dispute. Once
    the opener revokes it, no active grant remains and the read must stop —
    otherwise "the arbiter sees the conversation only while a party keeps it
    open" is a sentence the product cannot back.
    """
    claim = await client.post(
        f"/api/disputes/{disputed_deal['dispute_id']}/claim", headers=arbiter["headers"]
    )
    assert claim.status_code == 200, claim.text

    opened = await client.get(
        f"/api/admin/deals/{disputed_deal['deal_id']}/vault", headers=arbiter["headers"]
    )
    assert opened.status_code == 200, opened.text

    revoke = await client.post(
        f"/api/disputes/{disputed_deal['dispute_id']}/revoke-access",
        headers=sender_headers,
    )
    assert revoke.status_code == 200, revoke.text

    after = await client.get(
        f"/api/admin/deals/{disputed_deal['deal_id']}/vault", headers=arbiter["headers"]
    )
    assert after.status_code == 403, after.text


# ---------------------------------------------------------------------------
# Presigned links: the sensitive kind expires sooner.
# ---------------------------------------------------------------------------


def test_identity_document_links_expire_sooner_than_the_rest():
    """A link is a bearer token that ends up in history, logs and `Referer`.

    Identity documents are the most sensitive bytes stored, so their TTL is
    asserted to be *strictly* shorter — equal values would mean the distinction
    was dropped by an edit and nobody noticed.
    """
    from app.core.storage import presign_ttl_for_kind

    sensitive = presign_ttl_for_kind("identity_doc")
    ordinary = presign_ttl_for_kind("handoff_photo")

    assert sensitive < ordinary, (sensitive, ordinary)
    assert presign_ttl_for_kind(None) == ordinary
