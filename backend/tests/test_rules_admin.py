"""T3.11.02 — the rules editor: the publication gate and the two permissions.

The interesting cases are not "does the form save". They are:

  * can a set reach `published` with a section nobody cited — **asserted against
    the API, not the screen**, because a rule enforced in the UI is bypassed by
    a CLI import and by the first bulk load of a corpus;
  * can an editor publish, when publishing is the other permission;
  * does a published set stay what people read.

`vimana_test` is seeded once and never wiped (ENVIRONMENT.md §8), so every test
builds its own jurisdiction and category and tears them down after.
"""
from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import delete, select

from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatusEvent,
)
from app.models.marketplace import Category
from app.models.user import User
from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _account(client, tag: str, roles: list[str], session_maker):
    """A fresh account holding exactly these roles, plus its headers."""
    email = unique_email(tag)
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": f"Rules {tag}"}
    )
    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.roles = roles
        await db.commit()
        user_id = user.id
    resp = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    resp.raise_for_status()
    return user_id, {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def editor(client, session_maker):
    """Writes and sends to review. Cannot publish — that is the point."""
    _id, headers = await _account(client, "rules-ed", ["compliance_editor"], session_maker)
    return headers


@pytest.fixture
async def publisher(client, session_maker):
    _id, headers = await _account(client, "rules-pub", ["superuser"], session_maker)
    return headers


@pytest.fixture
async def corridor(session_maker):
    """A private jurisdiction and category, removed afterwards."""
    suffix = uuidlib.uuid4().hex[:6]
    code, cat_key = f"ZZ-{suffix}", f"testcat-{suffix}"

    async with session_maker() as db:
        db.add(Jurisdiction(code=code, kind=JurisdictionKind.country, name="Testland"))
        db.add(Category(name_key=cat_key, is_default=False, usage_count=0))
        await db.commit()

    yield code, cat_key

    async with session_maker() as db:
        sets = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalars().all()
        for rs in sets:
            sections = (
                await db.execute(
                    select(RuleSection).where(RuleSection.rule_set_id == rs.id)
                )
            ).scalars().all()
            for sec in sections:
                await db.execute(
                    delete(RuleSource).where(RuleSource.section_id == sec.id)
                )
            await db.execute(delete(RuleSection).where(RuleSection.rule_set_id == rs.id))
            await db.execute(
                delete(DocumentRequirement).where(
                    DocumentRequirement.rule_set_id == rs.id
                )
            )
            await db.execute(
                delete(RuleStatusEvent).where(RuleStatusEvent.rule_set_id == rs.id)
            )
        await db.execute(delete(RuleSet).where(RuleSet.jurisdiction_code == code))
        await db.execute(delete(Category).where(Category.name_key == cat_key))
        await db.execute(delete(Jurisdiction).where(Jurisdiction.code == code))
        await db.commit()


async def _new_set(client, headers, corridor, **over) -> str:
    code, cat_key = corridor
    body = {
        "direction": "import",
        "jurisdiction_code": code,
        "category_key": cat_key,
        "title": "Test corpus",
        **over,
    }
    resp = await client.post("/api/admin/rules", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _section(client, headers, set_id, anchor="overview") -> str:
    resp = await client.post(
        f"/api/admin/rules/{set_id}/sections",
        headers=headers,
        json={"anchor": anchor, "locale": "en", "title": "Overview", "body": "Text"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _source(client, headers, section_id, quote="A verbatim quotation."):
    return await client.post(
        f"/api/admin/rules/sections/{section_id}/sources",
        headers=headers,
        json={
            "authority": "Test Authority",
            "document_title": "Test Regulation",
            "quote": quote,
        },
    )


# --- the publication gate ---------------------------------------------------

async def test_a_section_without_a_source_blocks_publication(
    client, editor, publisher, corridor
):
    """The acceptance case, and asserted where it has to hold.

    Not "the button is disabled" — the button is not the rule. The transition
    endpoint is called directly and must refuse, because that is the path a
    bulk corpus import takes.
    """
    set_id = await _new_set(client, editor, corridor)
    await _section(client, editor, set_id)

    await client.post(
        f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "review"}
    )
    refused = await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "published"}
    )
    assert refused.status_code == 409
    assert "cites no source" in refused.json()["detail"]

    detail = await client.get(f"/api/admin/rules/{set_id}", headers=editor)
    assert detail.json()["status"] == "review"


async def test_publication_succeeds_once_every_section_is_cited(
    client, editor, publisher, corridor
):
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    assert (await _source(client, editor, section_id)).status_code == 201

    await client.post(
        f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "review"}
    )
    published = await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "published"}
    )
    assert published.status_code == 200, published.text
    assert published.json()["to_status"] == "published"

    detail = (await client.get(f"/api/admin/rules/{set_id}", headers=editor)).json()
    assert detail["status"] == "published"
    # Publication is a human vouching for the text — that is the date the reader
    # is shown and the daily watcher compares against.
    assert detail["reviewed_at"] is not None


async def test_blockers_are_visible_before_the_attempt(client, editor, corridor):
    """The editor should not learn what is wrong only by being refused."""
    set_id = await _new_set(client, editor, corridor)
    empty = (await client.get(f"/api/admin/rules/{set_id}", headers=editor)).json()
    assert any("no sections" in b for b in empty["blockers"])

    section_id = await _section(client, editor, set_id)
    uncited = (await client.get(f"/api/admin/rules/{set_id}", headers=editor)).json()
    assert any("overview" in b for b in uncited["blockers"])

    await _source(client, editor, section_id)
    ready = (await client.get(f"/api/admin/rules/{set_id}", headers=editor)).json()
    assert ready["blockers"] == []


async def test_a_source_without_a_quotation_is_refused(client, editor, corridor):
    """A paraphrase checks the text against whoever wrote it."""
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    resp = await _source(client, editor, section_id, quote="")
    assert resp.status_code == 422


# --- the two permissions ----------------------------------------------------

async def test_editor_may_send_to_review_but_not_publish(client, editor, corridor):
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    await _source(client, editor, section_id)

    to_review = await client.post(
        f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "review"}
    )
    assert to_review.status_code == 200

    refused = await client.post(
        f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "published"}
    )
    assert refused.status_code == 403
    assert "rules:publish" in refused.json()["detail"]


async def test_an_ordinary_account_reaches_nothing(client, corridor, session_maker):
    _id, headers = await _account(client, "rules-none", [], session_maker)
    assert (await client.get("/api/admin/rules", headers=headers)).status_code == 403


# --- transitions ------------------------------------------------------------

async def test_publishing_supersedes_the_previous_version(
    client, editor, publisher, corridor
):
    """One published version per triple — and the old one becomes history, not
    a second answer to the same question."""
    first = await _new_set(client, editor, corridor)
    s1 = await _section(client, editor, first)
    await _source(client, editor, s1)
    await client.post(f"/api/admin/rules/{first}/status", headers=editor, json={"to": "review"})
    await client.post(
        f"/api/admin/rules/{first}/status", headers=publisher, json={"to": "published"}
    )

    second = await _new_set(client, editor, corridor)
    s2 = await _section(client, editor, second)
    await _source(client, editor, s2)
    await client.post(f"/api/admin/rules/{second}/status", headers=editor, json={"to": "review"})
    ok = await client.post(
        f"/api/admin/rules/{second}/status", headers=publisher, json={"to": "published"}
    )
    assert ok.status_code == 200, ok.text

    old = (await client.get(f"/api/admin/rules/{first}", headers=editor)).json()
    new = (await client.get(f"/api/admin/rules/{second}", headers=editor)).json()
    assert old["status"] == "outdated"
    assert new["status"] == "published"
    assert new["version"] == old["version"] + 1

    # The supersession is written down, not merely done.
    history = (
        await client.get(f"/api/admin/rules/{first}/history", headers=editor)
    ).json()
    assert history[0]["to_status"] == "outdated"
    assert "Superseded" in history[0]["note"]


async def test_draft_cannot_jump_straight_to_published(
    client, editor, publisher, corridor
):
    """Skipping review would leave the split between the two permissions
    existing only on paper."""
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    await _source(client, editor, section_id)

    refused = await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "published"}
    )
    assert refused.status_code == 409


async def test_outdated_is_terminal(client, editor, publisher, corridor):
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    await _source(client, editor, section_id)
    await client.post(f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "review"})
    await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "published"}
    )
    await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "outdated"}
    )

    for target in ("draft", "review", "published"):
        resp = await client.post(
            f"/api/admin/rules/{set_id}/status",
            headers=publisher,
            json={"to": target},
        )
        assert resp.status_code == 409, target


async def test_the_journal_records_creation_and_every_move(
    client, editor, publisher, corridor
):
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    await _source(client, editor, section_id)
    await client.post(f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "review"})
    await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "published"}
    )

    history = (
        await client.get(f"/api/admin/rules/{set_id}/history", headers=editor)
    ).json()
    moves = [(h["from_status"], h["to_status"]) for h in reversed(history)]
    assert moves == [
        (None, "draft"),        # creation: there was no status before it
        ("draft", "review"),
        ("review", "published"),
    ]


# --- the freeze -------------------------------------------------------------

async def test_a_published_set_cannot_be_edited(client, editor, publisher, corridor):
    """What people read stays what people read. A correction is a new version."""
    set_id = await _new_set(client, editor, corridor)
    section_id = await _section(client, editor, set_id)
    await _source(client, editor, section_id)
    await client.post(f"/api/admin/rules/{set_id}/status", headers=editor, json={"to": "review"})
    await client.post(
        f"/api/admin/rules/{set_id}/status", headers=publisher, json={"to": "published"}
    )

    assert (
        await client.patch(
            f"/api/admin/rules/{set_id}", headers=editor, json={"title": "rewritten"}
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/api/admin/rules/{set_id}/sections",
            headers=editor,
            json={"anchor": "sneaked-in"},
        )
    ).status_code == 409
    assert (
        await client.delete(f"/api/admin/rules/sections/{section_id}", headers=editor)
    ).status_code == 409
    assert (
        await client.delete(f"/api/admin/rules/{set_id}", headers=editor)
    ).status_code == 409


# --- requirements -----------------------------------------------------------

async def test_requirement_predicate_is_validated_at_the_endpoint_too(
    client, editor, corridor
):
    """The model rejects it as well; the endpoint answers 400 rather than 500."""
    set_id = await _new_set(client, editor, corridor)
    bad = await client.post(
        f"/api/admin/rules/{set_id}/requirements",
        headers=editor,
        json={
            "code": "bogus",
            "title": "Made-up paper",
            "condition": {"attr": "colour", "op": "==", "value": "blue"},
        },
    )
    assert bad.status_code == 400
    assert "colour" in bad.json()["detail"]

    good = await client.post(
        f"/api/admin/rules/{set_id}/requirements",
        headers=editor,
        json={
            "code": "export_conclusion",
            "title": "Conclusion on cultural value",
            "issuer": "Authorised expert",
            "lead_time_days": 21,
            "condition": {"attr": "age_years", "op": ">=", "value": 100},
        },
    )
    assert good.status_code == 201
    assert good.json()["lead_time_days"] == 21


# --- jurisdictions ----------------------------------------------------------

async def test_a_state_can_be_added_under_its_country(client, editor):
    """Breed bans live in a state or a city, so the tree has to grow on demand:
    a list of every subdivision on earth is a list nobody maintains."""
    code = f"US-Z{uuidlib.uuid4().hex[:3].upper()}"
    created = await client.post(
        "/api/admin/jurisdictions",
        headers=editor,
        json={"code": code, "kind": "subdivision", "parent_code": "US", "name": "Testate"},
    )
    assert created.status_code == 201, created.text

    again = await client.post(
        "/api/admin/jurisdictions",
        headers=editor,
        json={"code": code, "kind": "subdivision", "parent_code": "US"},
    )
    assert again.status_code == 409

    orphan = await client.post(
        "/api/admin/jurisdictions",
        headers=editor,
        json={"code": f"{code}-X", "kind": "city", "parent_code": "NOPE"},
    )
    assert orphan.status_code == 400
