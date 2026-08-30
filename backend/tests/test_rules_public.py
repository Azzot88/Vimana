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
    RuleQuestion,
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
        db.add_all(
            [
                RuleQuestion(
                    rule_set_id=rule_set.id,
                    anchor="q-permit",
                    order=0,
                    locale="en",
                    question="Do I need a permit?",
                    answer="Above fifty years, yes.",
                    section_anchor="overview",
                ),
                RuleQuestion(
                    rule_set_id=rule_set.id,
                    anchor="q-permit",
                    order=0,
                    locale="ru",
                    question="Нужно ли разрешение?",
                    answer="Старше пятидесяти лет — да.",
                    section_anchor="overview",
                ),
                RuleQuestion(
                    rule_set_id=rule_set.id,
                    anchor="q-how-long",
                    order=1,
                    locale="en",
                    question="How long does it take?",
                    answer="About a month.",
                    section_anchor="deadlines",
                ),
            ]
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
                delete(RuleQuestion).where(RuleQuestion.rule_set_id == rs_id)
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
    # The directory reads as entries, not as a menu: each row carries what
    # changed and when, which is what the chronological default sorts by.
    assert "published_note" in mine[0]
    assert "version" in mine[0]


async def test_the_index_is_ordered_by_when_the_rule_last_changed(client, published):
    """Chronological is the server's order, not a client's option: grouping is
    a `reduce` over any list, ordering by publication needs the dates."""
    rows = (await client.get("/api/rules")).json()
    dated = [r["reviewed_at"] for r in rows if r["reviewed_at"]]
    assert dated == sorted(dated, reverse=True)
    # A published row without a review date could only come from something
    # writing the status outside `core/rule_status`; it belongs at the bottom
    # of a chronology rather than the top.
    undated_first = next(
        (i for i, r in enumerate(rows) if not r["reviewed_at"]), len(rows)
    )
    assert all(not r["reviewed_at"] for r in rows[undated_first:])


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


async def test_the_corridor_downloads_as_markdown(client, published):
    """`body` is stored as Markdown, so the file is the text rather than a
    conversion of it — which is why the format was chosen over HTML."""
    code, cat_key = published
    resp = await client.get(f"/api/rules/{cat_key}/export/{code}/markdown")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert ".md" in resp.headers["content-disposition"]

    text = resp.text
    assert "# Taking things out of Testland" in text
    assert "## Overview" in text
    # The citation travels with the claim. A file that dropped it would read
    # like an opinion, which is the one thing this corpus must not do.
    assert "A verbatim quotation." in text
    assert "Test Authority" in text
    # And the document list, with the number nobody can look up themselves.
    assert "21 days to obtain" in text


async def test_markdown_download_follows_the_locale(client, published):
    code, cat_key = published
    ru = (
        await client.get(
            f"/api/rules/{cat_key}/export/{code}/markdown", params={"locale": "ru"}
        )
    ).text
    assert "Русский текст" in ru
    # The untranslated section says so in the file too, not only on the page.
    assert "not translated yet" in ru


async def test_a_script_in_the_body_never_becomes_markup(client, session_maker, published):
    """The security property of storing Markdown, asserted rather than assumed.

    Rendering happens on the client with raw HTML disabled, so the guarantee
    that matters here is at the boundary: whatever an editor typed comes back
    from the API as the characters they typed. If the API ever started helping
    by emitting markup, this test is where that would show.
    """
    from sqlalchemy import select as sa_select

    from app.models.rules import RuleSection as RS

    code, cat_key = published
    payload = '<script>alert(1)</script> and <img src=x onerror=alert(1)>'

    async with session_maker() as db:
        section = (
            await db.execute(sa_select(RS).where(RS.anchor == "deadlines"))
        ).scalars().first()
        section.body = payload
        await db.commit()

    body = (await client.get(f"/api/rules/{cat_key}/export/{code}")).json()
    served = next(s for s in body["sections"] if s["anchor"] == "deadlines")["body"]
    assert served == payload

    text = (await client.get(f"/api/rules/{cat_key}/export/{code}/markdown")).text
    assert payload in text


async def test_unknown_corridor_is_a_plain_404(client):
    resp = await client.get("/api/rules/nosuch/export/ZZ")
    assert resp.status_code == 404


# --- the questions layer (T3.11.05) -----------------------------------------

async def test_the_corridor_leads_with_its_questions(client, published):
    """The compact reading of the same corpus, served first.

    A corpus written as law is checkable and unreadable. The questions are the
    second reading, and they arrive on the same response rather than from a
    second call: the page has no state in which it has the sections but not the
    answers, so there is no state in which it renders half of itself.
    """
    code, cat_key = published
    body = (await client.get(f"/api/rules/{cat_key}/export/{code}")).json()

    assert [q["anchor"] for q in body["questions"]] == ["q-permit", "q-how-long"]
    # Every answer names the section it came from. That pointer is what lets
    # the answer be three lines: the quotation is one click away.
    anchors = {s["anchor"] for s in body["sections"]}
    for question in body["questions"]:
        assert question["section_anchor"] in anchors


async def test_questions_follow_the_reader_s_locale_per_row(client, published):
    """Same fallback rule as sections, deliberately.

    Two different rules for the same decision on one page is how a page ends up
    half in each language with no way to say which half.
    """
    code, cat_key = published
    body = (
        await client.get(f"/api/rules/{cat_key}/export/{code}", params={"locale": "ru"})
    ).json()

    permit = next(q for q in body["questions"] if q["anchor"] == "q-permit")
    untranslated = next(q for q in body["questions"] if q["anchor"] == "q-how-long")

    assert permit["locale"] == "ru" and permit["question"] == "Нужно ли разрешение?"
    assert untranslated["locale"] == "en"


async def test_an_untranslated_question_raises_the_fallback_flag(client, session_maker, published):
    """The flag has to count questions, not only sections.

    They are the first thing on the page. A page whose entire visible top half
    is English while the flag says "fully translated" tells the reader the one
    thing they cannot check for themselves.
    """
    from sqlalchemy import update as sa_update

    from app.models.rules import RuleSection as RS

    code, cat_key = published

    # Translate every section, leaving one question untranslated. Without the
    # question being counted, `fallback_locale` would now be False.
    async with session_maker() as db:
        set_id = (
            await db.execute(
                select(RuleSet.id).where(
                    RuleSet.jurisdiction_code == code,
                    RuleSet.status == RuleStatus.published,
                )
            )
        ).scalar_one()
        await db.execute(
            sa_update(RS)
            .where(RS.rule_set_id == set_id, RS.anchor == "deadlines")
            .values(locale="ru")
        )
        await db.commit()

    body = (
        await client.get(f"/api/rules/{cat_key}/export/{code}", params={"locale": "ru"})
    ).json()
    assert all(s["locale"] == "ru" for s in body["sections"])
    assert any(q["locale"] != "ru" for q in body["questions"])
    assert body["fallback_locale"] is True


async def test_the_index_says_how_many_questions_a_corridor_answers(client, published):
    """Said before the click: a corridor answering twelve questions is a
    different offer from one carrying only the legal text."""
    _code, cat_key = published
    row = next(r for r in (await client.get("/api/rules")).json() if r["category_key"] == cat_key)
    # Two anchors, three rows — the Russian translation is the same question.
    assert row["question_count"] == 2


async def test_the_index_carries_the_questions_themselves(client, published):
    """The directory lists real questions, not a count of them.

    Somebody who does not know the taxonomy ("art / export / RU") still knows
    their own question, and that is the only entry point that works for a
    first-time reader. It is also what makes the directory searchable without a
    second request.
    """
    _code, cat_key = published
    row = next(
        r for r in (await client.get("/api/rules")).json() if r["category_key"] == cat_key
    )
    assert [q["anchor"] for q in row["questions"]] == ["q-permit", "q-how-long"]
    assert row["questions"][0]["question"] == "Do I need a permit?"
    # Text only. The answer stays behind the click, so the index does not grow
    # into a copy of every corridor page.
    assert "answer" not in row["questions"][0]


async def test_the_index_follows_the_readers_locale(client, published):
    """Same per-anchor fallback as the corridor page.

    A directory that listed questions in English while the page underneath
    showed them in Russian would be two different products sharing a link.
    """
    _code, cat_key = published
    rows = (await client.get("/api/rules", params={"locale": "ru"})).json()
    row = next(r for r in rows if r["category_key"] == cat_key)

    permit = next(q for q in row["questions"] if q["anchor"] == "q-permit")
    untranslated = next(q for q in row["questions"] if q["anchor"] == "q-how-long")

    assert permit["locale"] == "ru" and permit["question"] == "Нужно ли разрешение?"
    # Not dropped for lacking a translation: a question nobody has translated
    # is still a question this corridor answers.
    assert untranslated["locale"] == "en"
    # And the count stays anchors, so a half-translated corpus does not read as
    # a longer one.
    assert row["question_count"] == 2


async def test_the_markdown_carries_the_questions_and_their_sections(client, published):
    code, cat_key = published
    text = (await client.get(f"/api/rules/{cat_key}/export/{code}/markdown")).text

    assert "## Short answers" in text
    assert "Do I need a permit?" in text
    # The pointer travels with the answer, so the compact form stays traceable
    # once the file has left the site.
    assert "`overview`" in text
