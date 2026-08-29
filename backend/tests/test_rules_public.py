"""T3.11.03 — the public rules directory.

Three properties, and each is the reason the endpoint exists rather than a
detail of it:

  * **it is open** — no session, no account, nothing to sign;
  * **it serves only what is published** — a draft is somebody's work in
    progress and an `outdated` set is what a rule *used* to say, and to a
    stranger both read exactly like the current answer;
  * **it says how much to trust itself** — the date a person last checked the
    text, and whether the reader is looking at a translation or at English
    standing in for one.
"""
from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import delete, select

from app.models.marketplace import Category
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    RuleDirection,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
    RuleStatusEvent,
)


@pytest.fixture
async def published(session_maker):
    """A published set with two locales on one section and one English-only.

    Built directly rather than through the editor API: this file is about what
    a reader gets, and driving eight admin endpoints first would make the
    editor the thing under test.
    """
    suffix = uuidlib.uuid4().hex[:6]
    code, cat_key = f"ZZ-{suffix}", f"pubcat-{suffix}"

    async with session_maker() as db:
        db.add(Jurisdiction(code=code, kind=JurisdictionKind.country, name="Testland"))
        db.add(Category(name_key=cat_key, is_default=False, usage_count=0))
        await db.flush()

        rule_set = RuleSet(
            direction=RuleDirection.export,
            jurisdiction_code=code,
            category_key=cat_key,
            version=1,
            status=RuleStatus.published,
            title="Taking things out of Testland",
        )
        db.add(rule_set)
        await db.flush()

        en = RuleSection(
            rule_set_id=rule_set.id, anchor="overview", order=0, locale="en",
            title="Overview", body="English body",
        )
        ru = RuleSection(
            rule_set_id=rule_set.id, anchor="overview", order=0, locale="ru",
            title="Обзор", body="Русский текст",
        )
        only_en = RuleSection(
            rule_set_id=rule_set.id, anchor="deadlines", order=1, locale="en",
            title="Deadlines", body="Not translated yet",
        )
        db.add_all([en, ru, only_en])
        await db.flush()
        for section in (en, ru, only_en):
            db.add(
                RuleSource(
                    section_id=section.id,
                    authority="Test Authority",
                    document_title="Test Regulation",
                    quote="A verbatim quotation.",
                )
            )
        db.add(
            DocumentRequirement(
                rule_set_id=rule_set.id,
                code="export_conclusion",
                title="Conclusion on cultural value",
                issuer="Authorised expert",
                lead_time_days=21,
            )
        )

        draft = RuleSet(
            direction=RuleDirection.import_,
            jurisdiction_code=code,
            category_key=cat_key,
            version=1,
            status=RuleStatus.draft,
            title="Not for readers yet",
        )
        db.add(draft)
        await db.commit()
        set_id = rule_set.id

    yield code, cat_key

    async with session_maker() as db:
        sections = (
            await db.execute(select(RuleSection).where(RuleSection.rule_set_id == set_id))
        ).scalars().all()
        for sec in sections:
            await db.execute(delete(RuleSource).where(RuleSource.section_id == sec.id))
        for rs_id in (
            await db.execute(
                select(RuleSet.id).where(RuleSet.jurisdiction_code == code)
            )
        ).scalars().all():
            await db.execute(delete(RuleSection).where(RuleSection.rule_set_id == rs_id))
            await db.execute(
                delete(DocumentRequirement).where(DocumentRequirement.rule_set_id == rs_id)
            )
            await db.execute(
                delete(RuleStatusEvent).where(RuleStatusEvent.rule_set_id == rs_id)
            )
        await db.execute(delete(RuleSet).where(RuleSet.jurisdiction_code == code))
        await db.execute(delete(Category).where(Category.name_key == cat_key))
        await db.execute(delete(Jurisdiction).where(Jurisdiction.code == code))
        await db.commit()


async def test_the_directory_needs_no_account(client, published):
    """The free half of stream D. Text nobody can read without an account is
    text nobody reads, and what is sold is the packet, not the knowledge."""
    code, cat_key = published
    resp = await client.get(f"/api/rules/{cat_key}/export/{code}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Taking things out of Testland"


async def test_a_draft_is_not_served(client, published):
    code, cat_key = published
    resp = await client.get(f"/api/rules/{cat_key}/import/{code}")
    assert resp.status_code == 404


async def test_the_index_lists_only_published_sets_with_their_paths(client, published):
    code, cat_key = published
    rows = (await client.get("/api/rules")).json()
    mine = [r for r in rows if r["category_key"] == cat_key]
    assert len(mine) == 1
    # The path is served, not assembled by the caller: the prerender step writes
    # one file per path, and a path built in two places differs in one of them.
    assert mine[0]["path"] == f"/rules/{cat_key}/export/{code}/"
    assert mine[0]["jurisdiction_name"] == "Testland"


async def test_russian_gets_russian_where_it_exists(client, published):
    code, cat_key = published
    body = (
        await client.get(f"/api/rules/{cat_key}/export/{code}", params={"locale": "ru"})
    ).json()

    overview = next(s for s in body["sections"] if s["anchor"] == "overview")
    deadlines = next(s for s in body["sections"] if s["anchor"] == "deadlines")

    assert overview["locale"] == "ru" and overview["body"] == "Русский текст"
    # Half-translated is a real state, and the honest answer is the translated
    # sections in the reader's language and the rest in English — each saying
    # which it is, rather than a page pretending to be one or the other.
    assert deadlines["locale"] == "en"
    assert body["fallback_locale"] is True


async def test_english_reader_sees_no_fallback_flag(client, published):
    code, cat_key = published
    body = (
        await client.get(f"/api/rules/{cat_key}/export/{code}", params={"locale": "en"})
    ).json()
    assert body["fallback_locale"] is False
    assert all(s["locale"] == "en" for s in body["sections"])


async def test_an_untranslated_locale_falls_back_to_english(client, published):
    """A corpus locale the product does not have yet is not an error."""
    code, cat_key = published
    body = (
        await client.get(f"/api/rules/{cat_key}/export/{code}", params={"locale": "fr"})
    ).json()
    assert body["locale"] == "en"


async def test_every_section_carries_its_citation(client, published):
    code, cat_key = published
    body = (await client.get(f"/api/rules/{cat_key}/export/{code}")).json()
    assert body["sections"]
    for section in body["sections"]:
        assert section["sources"], section["anchor"]
        assert section["sources"][0]["quote"]


async def test_freshness_travels_as_fields_not_prose(client, published):
    """A machine cannot parse a sentence in a footer, and a person deserves the
    date next to the claim."""
    code, cat_key = published
    body = (await client.get(f"/api/rules/{cat_key}/export/{code}")).json()
    for key in ("reviewed_at", "checked_at", "needs_review", "version", "effective_from"):
        assert key in body


async def test_requirements_come_with_their_lead_time(client, published):
    """The one number a person cannot look up for themselves."""
    code, cat_key = published
    body = (await client.get(f"/api/rules/{cat_key}/export/{code}")).json()
    req = next(r for r in body["requirements"] if r["code"] == "export_conclusion")
    assert req["lead_time_days"] == 21


async def test_unknown_corridor_is_a_plain_404(client):
    resp = await client.get("/api/rules/nosuch/export/ZZ")
    assert resp.status_code == 404
