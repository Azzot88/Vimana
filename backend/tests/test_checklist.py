"""T3.11.06 — the checklist: what the corridor asks for, and by when.

The corpus was written first and had no consumer but the directory. What is
worth asserting here is not «does it return rows» but the four decisions that
make the list usable rather than merely correct:

  * the walk goes **up the jurisdiction tree**, because breed and generation
    bans live below the country level and a lookup stopping at `US` returns an
    answer that is true and useless;
  * a code named twice merges to the **stricter** side, because the failure
    modes are not symmetric — over-preparing costs a trip to an office, and
    under-preparing costs the flight;
  * an unanswered attribute puts the document **in**, marked, rather than
    dropping it (`IMPLEMENTATIONPLAN §3.11.6`);
  * the snapshot does not move when the rule does.
"""
from __future__ import annotations

import uuid as uuidlib
from datetime import date, timedelta

import pytest_asyncio
from sqlalchemy import delete

from app.models.marketplace import Category
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    RuleDirection,
    RuleSet,
    RuleStatus,
)


@pytest_asyncio.fixture
async def corridor(session_maker):
    """A two-level import side and a one-level export side, of our own.

    Built directly rather than through the loader: the loader is tested in
    `test_load_rules.py`, and going through it here would make this file depend
    on a corpus format it does not care about. Codes are randomised because
    `vimana_test` is never reset (`ENVIRONMENT §8`).
    """
    tag = uuidlib.uuid4().hex[:6].upper()
    country, state, out = f"X{tag[:2]}", f"X{tag[:2]}-{tag[2:4]}", f"Y{tag[:2]}"
    category = f"chk-{tag.lower()}"

    async with session_maker() as db:
        # `RuleSet.category_key` is a foreign key into the category registry the
        # trips already use (`T1.17`) — deliberately, so a rule can attach to a
        # trip whose category is already chosen. A corpus for a category nobody
        # has registered is therefore not a thing, and the fixture registers it.
        db.add_all(
            [
                Category(name_key=category, is_default=False),
                Category(name_key=f"{category}-draft", is_default=False),
                Jurisdiction(
                    code=country, kind=JurisdictionKind.country,
                    parent_code=None, name="In",
                ),
                Jurisdiction(
                    code=state, kind=JurisdictionKind.subdivision,
                    parent_code=country, name="St",
                ),
                Jurisdiction(
                    code=out, kind=JurisdictionKind.country,
                    parent_code=None, name="Out",
                ),
            ]
        )
        await db.flush()

        federal = RuleSet(
            direction=RuleDirection.import_,
            jurisdiction_code=country,
            category_key=category,
            status=RuleStatus.published,
            title="Federal",
        )
        local = RuleSet(
            direction=RuleDirection.import_,
            jurisdiction_code=state,
            category_key=category,
            status=RuleStatus.published,
            title="State",
        )
        leaving = RuleSet(
            direction=RuleDirection.export,
            jurisdiction_code=out,
            category_key=category,
            status=RuleStatus.published,
            title="Export",
        )
        draft = RuleSet(
            direction=RuleDirection.import_,
            jurisdiction_code=country,
            category_key=f"{category}-draft",
            status=RuleStatus.draft,
            title="Draft",
        )
        db.add_all([federal, local, leaving, draft])
        await db.flush()

        db.add_all(
            [
                # Same code twice, deliberately at odds: the federal set calls it
                # optional with a short lead, the state one mandatory with a long
                # one. The merge must land on mandatory + 30.
                DocumentRequirement(
                    rule_set_id=federal.id, code="vet", title="Vet certificate",
                    is_mandatory=False, lead_time_days=3, valid_for_days=30,
                ),
                DocumentRequirement(
                    rule_set_id=local.id, code="vet", title="Vet certificate",
                    is_mandatory=True, lead_time_days=30, valid_for_days=10,
                ),
                # Conditional on an attribute the caller may not have answered.
                DocumentRequirement(
                    rule_set_id=federal.id, code="resale-permit", title="Resale permit",
                    is_mandatory=True, lead_time_days=5,
                    condition={"attr": "purpose", "op": "==", "value": "resale"},
                ),
                DocumentRequirement(
                    rule_set_id=leaving.id, code="export-decl", title="Export declaration",
                    is_mandatory=True, lead_time_days=1,
                ),
                DocumentRequirement(
                    rule_set_id=draft.id, code="never", title="Never seen",
                    is_mandatory=True,
                ),
            ]
        )
        await db.commit()

    yield {
        "country": country,
        "state": state,
        "out": out,
        "category": category,
        # The ids let the last test delete inside its own corpus. `vimana_test` is
        # shared, and a delete by document code alone would reach into whatever
        # other file happens to use the word.
        "set_ids": [federal.id, local.id, leaving.id, draft.id],
    }

    async with session_maker() as db:
        for rs in (federal, local, leaving, draft):
            await db.execute(
                delete(DocumentRequirement).where(
                    DocumentRequirement.rule_set_id == rs.id
                )
            )
        await db.execute(delete(RuleSet).where(RuleSet.id.in_([rs.id for rs in (federal, local, leaving, draft)])))
        await db.execute(
            delete(Jurisdiction).where(Jurisdiction.code.in_([state, country, out]))
        )
        await db.execute(
            delete(Category).where(
                Category.name_key.in_([category, f"{category}-draft"])
            )
        )
        await db.commit()


async def _create_message(client, headers, deal_id) -> str:
    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=headers,
        json={"text": "checklist document", "is_system": False},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _build(client, corridor, **over):

    body = {
        "origin": corridor["out"],
        "destination": corridor["state"],
        "category": corridor["category"],
        "attrs": {"purpose": "personal"},
        **over,
    }
    return await client.post("/api/checklist", json=body)


async def test_the_wizard_needs_no_account(client, corridor):
    """`MASTERPLAN §4.1` — the corpus is free, and a sign-up wall in front of
    free information is a sign-up form pretending to be a service."""
    r = await _build(client, corridor)
    assert r.status_code == 200, r.text
    assert r.json()["items"]


async def test_the_walk_goes_up_the_tree(client, corridor):
    """A rule attached to the country must reach a parcel arriving in the state.

    Breed and generation bans live below the country level, so a lookup that
    stopped at either end would be true and useless.
    """
    body = (await _build(client, corridor)).json()
    assert corridor["state"] in body["corridor"]
    assert corridor["country"] in body["corridor"]
    assert corridor["out"] in body["corridor"]
    codes = {i["code"] for i in body["items"]}
    assert "export-decl" in codes  # the leaving side
    assert "vet" in codes          # the arriving side, two levels up


async def test_the_same_document_merges_to_the_stricter_side(client, corridor):
    """Optional + mandatory is mandatory; 3 days + 30 days is 30.

    And validity is the mirror: a certificate expired for one jurisdiction is
    expired, so the shortest window binds.
    """
    body = (await _build(client, corridor)).json()
    vet = next(i for i in body["items"] if i["code"] == "vet")
    assert vet["is_mandatory"] is True
    assert vet["lead_time_days"] == 30
    assert vet["valid_for_days"] == 10


async def test_a_condition_that_does_not_apply_is_left_out(client, corridor):
    body = (await _build(client, corridor)).json()
    assert "resale-permit" not in {i["code"] for i in body["items"]}


async def test_an_unanswered_condition_includes_the_document_and_asks(
    client, corridor
):
    """`IMPLEMENTATIONPLAN §3.11.6` — unknown decides strictly.

    The document goes in marked `undecided`, and the attribute is named, because
    dropping a paper nobody had been asked about is the one failure this
    subsystem exists to prevent.
    """
    body = (await _build(client, corridor, attrs={})).json()
    permit = next(i for i in body["items"] if i["code"] == "resale-permit")
    assert permit["undecided"] is True
    assert body["unanswered"]["resale-permit"] == ["purpose"]
    # And the questionnaire is computed from the corpus, not kept beside it.
    assert "purpose" in body["asks"]


async def test_an_unpublished_set_is_invisible(client, corridor):
    """A draft is somebody's work in progress; serving it would be the platform
    stating something it has not agreed to say."""
    r = await _build(client, corridor, category=f"{corridor['category']}-draft")
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_the_countdown_marks_what_is_already_too_late(client, corridor):
    """31 % of this market publishes within two days of the flight, so a 30-day
    requirement is not an edge case — it is the commonest red line there is."""
    soon = (date.today() + timedelta(days=2)).isoformat()
    body = (await _build(client, corridor, depart_at=soon)).json()
    vet = next(i for i in body["items"] if i["code"] == "vet")
    assert vet["too_late"] is True
    quick = next(i for i in body["items"] if i["code"] == "export-decl")
    assert quick["too_late"] is False
    # Soonest-to-start first, so the impossible one is at the top where it is read.
    assert body["items"][0]["code"] == "vet"


async def test_without_a_departure_there_are_no_deadlines(client, corridor):
    """«Когда-нибудь» has no red lines, and inventing one would be a warning
    about a date nobody named."""
    body = (await _build(client, corridor)).json()
    assert all(i["start_by"] is None and i["too_late"] is False for i in body["items"])


async def test_a_saved_case_does_not_move_when_the_rule_does(
    client, session_maker, corridor
):
    """The snapshot is the whole point (`T_UX.15`, `MASTERPLAN §4.1`).

    Publishing a new version must not rewrite the list under somebody already
    standing in a queue with the old one; a changed rule produces a notice, not
    a silent edit.
    """
    saved = await client.post(
        "/api/checklist/cases",
        json={
            "origin": corridor["out"],
            "destination": corridor["state"],
            "category": corridor["category"],
            "attrs": {"purpose": "personal"},
        },
    )
    assert saved.status_code == 201, saved.text
    case_id = saved.json()["id"]
    before = {i["code"] for i in saved.json()["checklist"]["items"]}

    async with session_maker() as db:
        await db.execute(
            delete(DocumentRequirement).where(
                DocumentRequirement.code == "vet",
                DocumentRequirement.rule_set_id.in_(corridor["set_ids"]),
            )
        )
        await db.commit()

    again = await client.get(f"/api/checklist/cases/{case_id}")
    assert again.status_code == 200
    assert {i["code"] for i in again.json()["checklist"]["items"]} == before
    assert "vet" in before

    # …while a fresh build reflects the change, which is what makes the frozen
    # one meaningful rather than merely stale.
    fresh = (await _build(client, corridor)).json()
    assert "vet" not in {i["code"] for i in fresh["items"]}


# ── T3.11.09 · the checklist inside a deal ────────────────────────────────


async def test_a_deal_without_a_case_says_so_quietly(
    client, sender_headers, seed_deal
):
    """Most deals carry no corridor requirements at all.

    A 404 here would make «нет чеклиста» look like «что-то сломалось», and the
    deal screen would have to tell the two apart.
    """
    r = await client.get(
        f"/api/deals/{seed_deal.id}/checklist", headers=sender_headers
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "case_id": None,
        "items": [],
        "unanswered": {},
        "corridor": [],
        "open_mandatory": 0,
    }


async def test_a_filed_document_closes_its_line(
    client, sender_headers, seed_deal, corridor
):
    """The list is a snapshot; the ticks are derived.

    Two different kinds of fact, kept where each can be right: what the corridor
    asked does not change, what has been filed does.
    """
    case = await client.post(
        "/api/checklist/cases",
        headers=sender_headers,
        json={
            "origin": corridor["out"],
            "destination": corridor["state"],
            "category": corridor["category"],
            "attrs": {"purpose": "personal"},
            "deal_id": str(seed_deal.id),
        },
    )
    assert case.status_code == 201, case.text

    before = await client.get(
        f"/api/deals/{seed_deal.id}/checklist", headers=sender_headers
    )
    body = before.json()
    assert body["case_id"] == case.json()["id"]
    vet = next(i for i in body["items"] if i["code"] == "vet")
    assert vet["attached"] is False
    assert body["open_mandatory"] >= 1

    msg = await _create_message(client, sender_headers, seed_deal.id)
    up = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg}/attachments",
        headers=sender_headers,
        files={"file": ("vet.pdf", b"%PDF-1.4\n%x", "application/pdf")},
        data={"kind": "doc", "requirement_code": "vet"},
    )
    assert up.status_code == 201, up.text

    after = (
        await client.get(
            f"/api/deals/{seed_deal.id}/checklist", headers=sender_headers
        )
    ).json()
    vet = next(i for i in after["items"] if i["code"] == "vet")
    assert vet["attached"] is True
    assert vet["attachment_count"] == 1
    assert after["open_mandatory"] == body["open_mandatory"] - 1


async def test_an_open_checklist_blocks_nothing(
    client, sender_headers, carrier_headers, seed_deal, corridor
):
    """`D-COMPLIANCE-STANCE` — «вы знали» доказывается записью, а не запретом.

    The card is informational by declaration (`ack_by=None`), and the deal keeps
    moving with lines still open. A checklist that blocked would be the platform
    ruling on somebody's paperwork, which is exactly the posture this project
    refuses.
    """
    await client.post(
        "/api/checklist/cases",
        headers=sender_headers,
        json={
            "origin": corridor["out"],
            "destination": corridor["state"],
            "category": corridor["category"],
            "attrs": {"purpose": "personal"},
            "deal_id": str(seed_deal.id),
        },
    )
    raised = await client.post(
        f"/api/deals/{seed_deal.id}/cards",
        headers=sender_headers,
        json={
            "kind": "compliance.checklist",
            "payload": {"case_id": str(seed_deal.id)},
        },
    )
    assert raised.status_code == 201, raised.text
    # Nobody owes an answer: it states, it does not ask.
    assert raised.json()["requires_ack_by"] is None

    # And an unrelated step still goes through with the checklist wide open.
    moved = await client.post(
        f"/api/deals/{seed_deal.id}/cards",
        headers=carrier_headers,
        json={"kind": "transit.update", "payload": {"status": "in_transit"}},
    )
    assert moved.status_code in (201, 403), moved.text


async def test_a_stranger_cannot_read_the_checklist(
    client, seed_deal, corridor
):
    """The arbiter reaches a disputed deal through `api/admin`, which keeps its
    own grant check and writes its own audit entry. A second door here would be
    the same content without either."""
    from tests.conftest import make_account

    outsider = await make_account(client, "chk-outsider")
    r = await client.get(
        f"/api/deals/{seed_deal.id}/checklist", headers=outsider["headers"]
    )
    assert r.status_code == 403, r.text
