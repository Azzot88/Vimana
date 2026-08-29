"""T3.42 — a role is an offer, and where it came from is written down.

The interesting cases are not "does the row save". They are: does an open offer
grant anything (it must not, checked by calling an arbiter endpoint rather than
by looking at the screen), does a withdrawal leave the same kind of trace as a
grant, and can the role in force right now be traced back to the person who
proposed it.

The long-lived seed accounts are deliberately not used as subjects here — each
test makes its own account. `e2e/specs/admin-guard.spec.ts` asserts that the
shared account stays `role='user'`, and a test that borrows it and crashes
half-way would turn that spec red for reasons no one would find.
"""
from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import delete, select

from app.models.role_grant import RoleGrant, RoleGrantEvent
from app.models.user import User
from tests.conftest import SEED_PASSWORD, make_account, unique_email


@pytest.fixture
async def superuser_headers(client, session_maker, seed_carrier):
    """Borrow the seed carrier as User Zero for the length of one test.

    Same shape as the fixture in `test_arbiter.py` rather than a shared one:
    both files raise and lower the same account, and a session-scoped version
    would leave it a superuser for whatever ran next.
    """
    async with session_maker() as db:
        u = await db.get(User, seed_carrier.id)
        u.role = "superuser"
        await db.commit()
    try:
        from tests.conftest import _login

        token = await _login(client, seed_carrier.email)
        yield {"Authorization": f"Bearer {token}"}
    finally:
        async with session_maker() as db:
            u = await db.get(User, seed_carrier.id)
            u.role = "user"
            await db.commit()


async def _make_subject(client, tag: str) -> tuple[uuidlib.UUID, dict]:
    """A fresh account plus its auth headers.

    The id comes back as a `UUID` rather than a string: it is used both in URLs
    and as a query parameter, and a string reaching the second place is the kind
    of mismatch the driver reports as something unrelated.
    """
    email = unique_email(tag)
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": f"Subject {tag}"}
    )
    resp = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    resp.raise_for_status()
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = await client.get("/api/auth/me", headers=headers)
    return uuidlib.UUID(me.json()["id"]), headers


@pytest.fixture
async def subject(client, session_maker):
    user_id, headers = await _make_subject(client, "role-subj")
    yield user_id, headers
    async with session_maker() as db:
        await db.execute(delete(RoleGrant).where(RoleGrant.subject_id == user_id))
        await db.commit()


# --- the invariant: an offer grants nothing --------------------------------

async def test_open_offer_grants_no_permission(client, superuser_headers, subject):
    """The acceptance case, checked the way the task demands it.

    Not "the section is hidden" — a hidden link is not protection, which
    `T_UX.20` already established. The arbiter endpoint is called directly, with
    the offer open, and must refuse exactly as it would for any account.
    """
    user_id, headers = subject

    before = await client.get("/api/admin/disputes", headers=headers)
    assert before.status_code == 403

    offered = await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter", "reason": "needed on disputes"},
    )
    assert offered.status_code == 201
    assert offered.json()["event"] == "offered"

    after = await client.get("/api/admin/disputes", headers=headers)
    assert after.status_code == 403, "an unaccepted offer must grant nothing"

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["role"] == "user"


async def test_accepting_is_what_starts_the_role(client, superuser_headers, subject):
    user_id, headers = subject
    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )

    accepted = await client.post("/api/me/roles/arbiter/accept", headers=headers)
    assert accepted.status_code == 200
    assert accepted.json()["event"] == "accepted"

    # A fresh token: the role is read from the database on every request, but
    # asking again also proves the change survived the commit.
    now = await client.get("/api/admin/disputes", headers=headers)
    assert now.status_code == 200


async def test_declining_leaves_the_account_untouched(client, superuser_headers, subject):
    user_id, headers = subject
    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )

    declined = await client.post("/api/me/roles/arbiter/decline", headers=headers)
    assert declined.status_code == 200
    assert declined.json()["event"] == "declined"

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["role"] == "user"
    assert (await client.get("/api/admin/disputes", headers=headers)).status_code == 403


# --- withdrawal is an event too --------------------------------------------

async def test_revoking_a_live_role_is_journalled_like_granting_it(
    client, superuser_headers, subject
):
    """The half that gets lost: an appointment is remembered, a withdrawal is
    not. A journal that records only grants describes a platform where nobody's
    power ever ends."""
    user_id, headers = subject
    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )
    await client.post("/api/me/roles/arbiter/accept", headers=headers)

    revoked = await client.request(
        "DELETE",
        f"/api/admin/users/{user_id}/roles/arbiter",
        headers=superuser_headers,
        json={"reason": "no longer on the rota"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["event"] == "revoked"
    assert revoked.json()["reason"] == "no longer on the rota"

    assert (await client.get("/api/admin/disputes", headers=headers)).status_code == 403

    journal = await client.get(
        f"/api/admin/users/{user_id}/roles", headers=superuser_headers
    )
    events = [row["event"] for row in journal.json()]
    assert events == ["revoked", "accepted", "offered"]


async def test_withdrawing_an_unanswered_offer_does_not_clear_another_role(
    client, superuser_headers, subject
):
    """A withdrawn offer must not touch `users.role`.

    The account may already hold a different role, and clearing the column here
    would revoke that one silently — a bug that looks like nothing at all until
    somebody loses access they never gave up.
    """
    user_id, headers = subject

    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )
    await client.post("/api/me/roles/arbiter/accept", headers=headers)

    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "compliance_editor"},
    )
    await client.request(
        "DELETE",
        f"/api/admin/users/{user_id}/roles/compliance_editor",
        headers=superuser_headers,
    )

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["role"] == "arbiter", "the live role survived an unrelated withdrawal"


# --- the journal answers "where did this come from" ------------------------

async def test_journal_traces_the_role_in_force_to_who_proposed_it(
    client, superuser_headers, subject, session_maker
):
    user_id, headers = subject
    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter", "reason": "covering August"},
    )
    await client.post("/api/me/roles/arbiter/accept", headers=headers)

    journal = (
        await client.get(f"/api/admin/users/{user_id}/roles", headers=superuser_headers)
    ).json()

    accepted = next(r for r in journal if r["event"] == "accepted")
    offered = next(r for r in journal if r["event"] == "offered")

    # Acceptance carries no actor — the subject is the actor, and storing them
    # twice invites the two columns to disagree.
    assert accepted["actor_id"] is None
    # The offer names a person, by name and not only by id: a UUID answers
    # "who proposed this" only for somebody with database access.
    assert offered["actor_id"] is not None
    assert offered["actor_name"]
    assert offered["reason"] == "covering August"


async def test_subject_sees_their_own_offers_and_current_role(
    client, superuser_headers, subject
):
    user_id, headers = subject
    mine = (await client.get("/api/me/roles", headers=headers)).json()
    assert mine["role"] == "user" and mine["offers"] == []

    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )
    mine = (await client.get("/api/me/roles", headers=headers)).json()
    assert mine["role"] == "user", "the offer is not the role"
    assert [o["role"] for o in mine["offers"]] == ["arbiter"]

    await client.post("/api/me/roles/arbiter/accept", headers=headers)
    mine = (await client.get("/api/me/roles", headers=headers)).json()
    assert mine["role"] == "arbiter" and mine["offers"] == []


# --- refusals ---------------------------------------------------------------

async def test_cannot_offer_the_same_role_twice(client, superuser_headers, subject):
    user_id, _ = subject
    body = {"role": "arbiter"}
    assert (
        await client.post(
            f"/api/admin/users/{user_id}/roles", headers=superuser_headers, json=body
        )
    ).status_code == 201
    second = await client.post(
        f"/api/admin/users/{user_id}/roles", headers=superuser_headers, json=body
    )
    assert second.status_code == 400


async def test_cannot_offer_a_role_to_yourself(client, superuser_headers):
    """Not about privilege escalation — the offerer already holds everything.
    It is that a journal where somebody offered themselves a role records a
    consent that never happened.

    The id is read back from `/auth/me` rather than queried by role: there can
    be more than one superuser, and picking an arbitrary one would exercise the
    "already holds every power" branch while claiming to test this one.
    """
    me = await client.get("/api/auth/me", headers=superuser_headers)
    resp = await client.post(
        f"/api/admin/users/{me.json()['id']}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )
    assert resp.status_code == 400


async def test_unknown_role_is_refused(client, superuser_headers, subject):
    user_id, _ = subject
    resp = await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "superuser"},
    )
    assert resp.status_code == 400


async def test_cannot_accept_what_was_never_offered(client, subject):
    _, headers = subject
    resp = await client.post("/api/me/roles/arbiter/accept", headers=headers)
    assert resp.status_code == 400
    assert (await client.get("/api/admin/disputes", headers=headers)).status_code == 403


async def test_offerable_roles_are_served_not_guessed(client, superuser_headers):
    resp = await client.get("/api/roles/offerable", headers=superuser_headers)
    assert resp.status_code == 200
    assert set(resp.json()) == {"arbiter", "compliance_editor"}
    assert "superuser" not in resp.json()


# --- the letter -------------------------------------------------------------

async def test_letter_goes_out_with_every_toggle_off(
    client, superuser_headers, subject, session_maker, monkeypatch
):
    """A change of what somebody may do with other people's data cannot depend
    on a notification setting."""
    user_id, _ = subject

    async with session_maker() as db:
        user = await db.get(User, user_id)
        # Every class, every channel, off. The security class is meant to
        # ignore this entirely.
        user.notification_prefs = {
            cls: {"email": False, "telegram": False, "whatsapp": False}
            for cls in ("deal", "deadline", "vault", "trust", "dispute", "security")
        }
        await db.commit()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker as sync_sessionmaker

    from app.tasks import notifications as notif
    from tests.conftest import TEST_DATABASE_URL

    engine = create_engine(
        TEST_DATABASE_URL.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True
    )
    monkeypatch.setattr(
        notif, "SyncSessionLocal", sync_sessionmaker(engine, expire_on_commit=False)
    )
    sent: list[tuple] = []
    monkeypatch.setattr(
        notif, "send_email", lambda to, subj, body, html=None: sent.append((to, subj, body))
    )

    try:
        notif.send_role_offered(str(user_id), "arbiter", "Alan")
    finally:
        engine.dispose()

    assert len(sent) == 1
    _, subject_line, body = sent[0]
    # §9.1 — until the answer comes back, the letter says proposed, not
    # assigned. The check is on the rendered text, because that is what the
    # person actually reads.
    lowered = f"{subject_line} {body}".lower()
    assert "offered" in lowered or "propose" in lowered
    assert "assigned" not in lowered


async def test_letter_is_registered_in_every_catalogue():
    """`test_email_templates` enforces this for all letters; asserted here too
    because a security letter that renders in English for a Russian-speaking
    arbiter is the kind of gap that only shows up in production."""
    from app.core.email_templates import available_locales, render

    for locale in available_locales():
        rendered = render(
            "role_offered",
            locale,
            role="arbiter",
            offered_by="Alan",
            cta_url="https://example.test/profile/keys",
        )
        assert rendered.subject and rendered.text


async def test_role_offered_belongs_to_the_mandatory_class():
    from app.core.notification_prefs import class_of, locked_classes

    assert class_of("role_offered") == "security"
    assert "security" in locked_classes()


# --- the model invariant ----------------------------------------------------

async def test_every_role_change_left_a_row(client, superuser_headers, subject, session_maker):
    """`users.role` is written in exactly one place, and that place appends a
    journal row in the same transaction. This asserts the pairing from the
    other end: after a full offer → accept → revoke cycle, the column is back
    where it started and the history explains every step."""
    user_id, headers = subject
    await client.post(
        f"/api/admin/users/{user_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter"},
    )
    await client.post("/api/me/roles/arbiter/accept", headers=headers)
    await client.request(
        "DELETE", f"/api/admin/users/{user_id}/roles/arbiter", headers=superuser_headers
    )

    async with session_maker() as db:
        rows = (
            await db.execute(
                select(RoleGrant)
                .where(RoleGrant.subject_id == user_id)
                .order_by(RoleGrant.created_at)
            )
        ).scalars().all()
        user = await db.get(User, user_id)

    assert [r.event for r in rows] == [
        RoleGrantEvent.offered,
        RoleGrantEvent.accepted,
        RoleGrantEvent.revoked,
    ]
    assert user.role == "user"
