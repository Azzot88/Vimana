"""T3.11.04 — the corpus loader: what it refuses, and that it never publishes.

The interesting cases are not "does JSON parse". They are:

  * a claim with no citation is refused — the **whole file**, before anything is
    written, because a half-loaded corpus looks like a corpus;
  * an admitted gap is allowed and cannot be published, which is the point of
    admitting it;
  * nothing the loader writes is ever `published`, with or without a flag.
"""
from __future__ import annotations

import json
import uuid as uuidlib
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.cli.load_rules import CorpusError, load, validate
from app.core.rule_conditions import MEMBERSHIP_OPS, ORDERED_OPS
from app.core.rule_status import is_fictional_jurisdiction, publication_blockers
from app.models.marketplace import Category
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    ObtainedBy,
    RuleDirection,
    RuleQuestion,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
    RuleStatusEvent,
)


def _corpus(code: str, category: str, **over) -> dict:
    base = {
        "jurisdictions": [
            {"code": code, "kind": "country", "parent_code": None, "name": "Testland"}
        ],
        "sets": [
            {
                "direction": "import",
                "jurisdiction": code,
                "category": category,
                "title": "Test corpus",
                "sections": [
                    {
                        "anchor": "overview",
                        "locale": "en",
                        "title": "Overview",
                        "body": "A claim about the law.",
                        "sources": [
                            {
                                "authority": "Test Authority",
                                "document_title": "Test Regulation",
                                "url": "https://example.test/reg",
                                "quote": "A verbatim quotation.",
                            }
                        ],
                    }
                ],
                "questions": [
                    {
                        "anchor": "q-overview",
                        "locale": "en",
                        "question": "What does this corridor need?",
                        "answer": "One certificate.",
                        "section_anchor": "overview",
                    }
                ],
                "requirements": [
                    {
                        "code": "health_cert",
                        "title": "Health certificate",
                        "issuer": "A vet",
                        "obtained_by": "sender",
                        "lead_time_days": 30,
                        "condition": {"attr": "purpose", "op": "==", "value": "resale"},
                    }
                ],
            }
        ],
    }
    base["sets"][0].update(over)
    return base


@pytest.fixture
async def corridor(session_maker):
    suffix = uuidlib.uuid4().hex[:6]
    code, category = f"ZZ-{suffix}", f"loadcat-{suffix}"

    async with session_maker() as db:
        db.add(Category(name_key=category, is_default=False, usage_count=0))
        await db.commit()

    yield code, category

    async with session_maker() as db:
        for rs_id in (
            await db.execute(select(RuleSet.id).where(RuleSet.jurisdiction_code == code))
        ).scalars().all():
            for sec_id in (
                await db.execute(
                    select(RuleSection.id).where(RuleSection.rule_set_id == rs_id)
                )
            ).scalars().all():
                await db.execute(delete(RuleSource).where(RuleSource.section_id == sec_id))
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
        await db.execute(delete(Category).where(Category.name_key == category))
        await db.execute(delete(Jurisdiction).where(Jurisdiction.code == code))
        await db.commit()


# --- what it refuses --------------------------------------------------------

def test_a_claim_without_a_citation_is_refused():
    """The acceptance case. The publication gate would catch it later, and
    later means a corpus nobody can publish sitting in the database while
    whoever wrote it has forgotten what it was."""
    corpus = _corpus("ZZ-x", "cat")
    del corpus["sets"][0]["sections"][0]["sources"]

    problems = validate(corpus)
    assert any("no source" in p for p in problems), problems


def test_a_source_without_a_quotation_is_refused():
    corpus = _corpus("ZZ-x", "cat")
    corpus["sets"][0]["sections"][0]["sources"][0]["quote"] = "   "
    assert any("no quotation" in p for p in validate(corpus))


def test_a_placeholder_may_have_no_source(corridor):
    """An admitted gap is not a claim — that is how the state-by-state layer
    lands, one set per state saying out loud it has nothing in it yet."""
    code, category = corridor
    corpus = _corpus(code, category)
    corpus["sets"][0]["sections"].append(
        {"anchor": "states", "locale": "en", "title": "State law", "placeholder": True}
    )
    assert validate(corpus) == []


def test_a_placeholder_with_a_body_is_refused():
    """A gap that says something is not a gap."""
    corpus = _corpus("ZZ-x", "cat")
    corpus["sets"][0]["sections"].append(
        {
            "anchor": "states",
            "locale": "en",
            "title": "State law",
            "placeholder": True,
            "body": "Bengals are banned in some states.",
        }
    )
    assert any("not a gap" in p for p in validate(corpus))


def test_a_question_answering_from_a_missing_section_is_refused():
    """Caught by the loader, not only by the publication gate.

    A file is the artefact somebody reviews in a diff. An anchor typo caught
    here is one line of output; the same typo caught at publication is an
    editor hunting through a screen for which of twenty questions is broken.
    """
    corpus = _corpus("ZZ-x", "cat")
    corpus["sets"][0]["questions"][0]["section_anchor"] = "no-such-anchor"
    assert any("no-such-anchor" in p for p in validate(corpus))


def test_a_question_without_an_answer_is_refused():
    """A question with no answer is a heading, and a heading in a list of
    answers is a promise the page does not keep."""
    corpus = _corpus("ZZ-x", "cat")
    corpus["sets"][0]["questions"][0]["answer"] = "   "
    assert any("no answer" in p for p in validate(corpus))


def test_two_questions_may_share_an_anchor_across_locales():
    """The translation of a question is the same question.

    The unique constraint is on `(set, anchor, locale)` for exactly this: one
    anchor per question, one row per language, and the directory counts anchors
    rather than rows so a translated corpus does not look like a longer one.
    """
    corpus = _corpus("ZZ-x", "cat")
    corpus["sets"][0]["questions"].append(
        {
            "anchor": "q-overview",
            "locale": "ru",
            "question": "Что нужно на этом коридоре?",
            "answer": "Одна справка.",
            "section_anchor": "overview",
        }
    )
    assert validate(corpus) == []


def test_an_unknown_predicate_attribute_is_refused():
    corpus = _corpus("ZZ-x", "cat")
    corpus["sets"][0]["requirements"][0]["condition"] = {
        "attr": "colour",
        "op": "==",
        "value": "blue",
    }
    assert any("colour" in p for p in validate(corpus))


def test_every_problem_is_reported_not_just_the_first():
    """A file fixed one error per run is a file loaded on the fifth attempt."""
    corpus = _corpus("ZZ-x", "cat")
    del corpus["sets"][0]["sections"][0]["sources"]
    corpus["sets"][0]["requirements"][0]["condition"] = {
        "attr": "colour",
        "op": "==",
        "value": "blue",
    }
    assert len(validate(corpus)) >= 2


# --- what it writes ---------------------------------------------------------

async def test_questions_are_written_with_the_corpus(session_maker, corridor):
    code, category = corridor
    async with session_maker() as db:
        counts = await load(db, _corpus(code, category), replace=False)
    assert counts["questions"] == 1

    async with session_maker() as db:
        rule_set = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalar_one()
        question = (
            await db.execute(
                select(RuleQuestion).where(RuleQuestion.rule_set_id == rule_set.id)
            )
        ).scalar_one()
    assert question.section_anchor == "overview"


async def test_the_corpus_lands_as_a_draft(session_maker, corridor):
    """Never published, not once, not with a flag: publication is the moment
    the platform starts making a checkable claim about somebody else's law."""
    code, category = corridor
    async with session_maker() as db:
        counts = await load(db, _corpus(code, category), replace=False)

    assert counts["sets"] == 1 and counts["sources"] == 1

    async with session_maker() as db:
        rule_set = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalar_one()
        assert rule_set.status is RuleStatus.draft
        assert rule_set.version == 1
        assert rule_set.reviewed_at is None

        events = (
            await db.execute(
                select(RuleStatusEvent).where(RuleStatusEvent.rule_set_id == rule_set.id)
            )
        ).scalars().all()
    assert len(events) == 1
    assert events[0].to_status is RuleStatus.draft
    # No actor: the row came from a file, not from a person pressing a button.
    assert events[0].actor_id is None


async def test_a_placeholder_keeps_the_set_unpublishable(session_maker, corridor):
    """The gap is visible *and* blocking — which is the correct outcome for a
    layer nobody has sourced yet."""
    code, category = corridor
    corpus = _corpus(code, category)
    corpus["sets"][0]["sections"].append(
        {"anchor": "states", "locale": "en", "title": "State law", "placeholder": True}
    )

    async with session_maker() as db:
        await load(db, corpus, replace=False)
        rule_set = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalar_one()
        blockers = await publication_blockers(db, rule_set)

    assert any("states" in b for b in blockers), blockers


async def test_loading_twice_is_refused_without_replace(session_maker, corridor):
    code, category = corridor
    async with session_maker() as db:
        await load(db, _corpus(code, category), replace=False)

    async with session_maker() as db:
        with pytest.raises(CorpusError) as exc:
            await load(db, _corpus(code, category), replace=False)
    assert "--replace" in str(exc.value)


async def test_a_set_already_in_review_is_replaced_too(session_maker, corridor):
    """Matching only drafts had a failure that looked like a broken button.

    A corpus already sent to review was left alone, a second set was created
    beside it, and the editor went on looking at the old one — publishing
    blocked by placeholders they had just removed from the file. `--replace`
    means "this file is the corpus now", and a set waiting for review is a set
    this file supersedes.
    """
    code, category = corridor
    async with session_maker() as db:
        await load(db, _corpus(code, category), replace=False)
        rule_set = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalar_one()
        rule_set.status = RuleStatus.review
        await db.commit()

    # Without the flag it now refuses and names the status, instead of quietly
    # building a second set.
    async with session_maker() as db:
        with pytest.raises(CorpusError) as exc:
            await load(db, _corpus(code, category), replace=False)
    assert "review" in str(exc.value)

    async with session_maker() as db:
        await load(db, _corpus(code, category, title="Second pass"), replace=True)
        rows = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].title == "Second pass"
    assert rows[0].status is RuleStatus.draft


async def test_replace_discards_the_previous_draft(session_maker, corridor):
    code, category = corridor
    async with session_maker() as db:
        await load(db, _corpus(code, category), replace=False)

    changed = _corpus(code, category, title="Second pass")
    async with session_maker() as db:
        await load(db, changed, replace=True)

    async with session_maker() as db:
        rows = (
            await db.execute(select(RuleSet).where(RuleSet.jurisdiction_code == code))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Second pass"


async def test_an_undeclared_jurisdiction_is_refused(session_maker, corridor):
    """Not created silently: a typo in a code would become a corridor, and a
    corridor nobody meant to make is a page nobody finds and nobody deletes."""
    _code, category = corridor
    corpus = _corpus("ZZ-nope", category)
    corpus["jurisdictions"] = []

    async with session_maker() as db:
        with pytest.raises(CorpusError) as exc:
            await load(db, corpus, replace=False)
    assert "unknown jurisdiction" in str(exc.value)


# --- the shipped corpus -----------------------------------------------------

CORPORA = (
    "us-animal-import.json",
    "us-art-import.json",
    "ru-animal-export.json",
    "ru-art-export.json",
)


@pytest.mark.parametrize("filename", CORPORA)
def test_every_shipped_corpus_is_loadable(filename):
    """The files in the repository must always be valid.

    They are reviewed in a diff, and a diff of a file that cannot load is a
    review of nothing.
    """
    path = Path(__file__).resolve().parent.parent / "app" / "data" / "rules" / filename
    corpus = json.loads(path.read_text(encoding="utf-8"))
    assert validate(corpus) == [], filename

    sections = corpus["sets"][0]["sections"]

    # No placeholders left in any shipped corpus: every section makes a claim
    # and cites it. Where a gap remains it is closed **narrowly** — the section
    # cites the text that establishes the gap exists and then says plainly what
    # it does not answer, rather than inventing the answer. Saying what a page
    # does not cover is a claim like any other, and it is true.
    assert [s["anchor"] for s in sections if s.get("placeholder")] == [], filename

    for section in sections:
        assert section["sources"], f"{filename}: {section['anchor']}"
        for source in section["sources"]:
            assert source["quote"].strip(), f"{filename}: {section['anchor']}"


@pytest.mark.parametrize("filename", CORPORA)
def test_every_shipped_corpus_answers_questions(filename):
    """A corpus with no questions is law nobody reads.

    Asserted rather than left to review: the sections are what makes the corpus
    checkable, and the questions are what makes it useful. Shipping the first
    without the second is the failure this layer exists to prevent, and it is
    invisible in a diff of a file that is already long.
    """
    path = Path(__file__).resolve().parent.parent / "app" / "data" / "rules" / filename
    corpus = json.loads(path.read_text(encoding="utf-8"))
    questions = corpus["sets"][0].get("questions", [])

    assert questions, filename
    anchors = {s["anchor"] for s in corpus["sets"][0]["sections"]}
    for question in questions:
        assert question["section_anchor"] in anchors, f"{filename}: {question['anchor']}"
        assert question["answer"].strip(), f"{filename}: {question['anchor']}"


# --- T_RULES.7: the fictional test corridor ---------------------------------

TEST_CORRIDOR = (
    Path(__file__).resolve().parent.parent / "app" / "data" / "rules" / "xa-test-corridor.json"
)


def _ops(condition) -> set[str]:
    if not condition:
        return set()
    for group in ("all", "any"):
        if group in condition:
            return {leaf["op"] for leaf in condition[group]}
    return {condition["op"]}


def test_the_test_corridor_exercises_everything_the_loader_accepts():
    """The file exists to show every field on the page, so "every" is asserted:
    a corpus that quietly stops using a field stops testing its rendering."""
    corpus = json.loads(TEST_CORRIDOR.read_text(encoding="utf-8"))
    assert validate(corpus) == []

    codes = [node["code"] for node in corpus["jurisdictions"]]
    assert all(is_fictional_jurisdiction(code) for code in codes), codes
    assert {node["kind"] for node in corpus["jurisdictions"]} == {
        kind.value for kind in JurisdictionKind
    }

    sets = corpus["sets"]
    assert all(is_fictional_jurisdiction(s["jurisdiction"]) for s in sets)
    assert {s["direction"] for s in sets} == {d.value for d in RuleDirection}
    assert all(s["title"].startswith("[ТЕСТ]") for s in sets)

    sections = [sec for s in sets for sec in s["sections"]]
    assert {sec["locale"] for sec in sections} == {"en", "ru"}
    assert any(sec.get("placeholder") for sec in sections)
    sources = [src for sec in sections for src in sec.get("sources", [])]
    assert any(src.get("url") and src.get("document_date") for src in sources)
    assert any(not src.get("url") for src in sources)
    assert any(not src.get("document_date") for src in sources)

    requirements = [r for s in sets for r in s["requirements"]]
    assert {r["obtained_by"] for r in requirements} == {o.value for o in ObtainedBy}
    assert {r.get("is_mandatory", True) for r in requirements} == {True, False}
    assert any(r.get("condition") is None for r in requirements)
    assert any("all" in (r.get("condition") or {}) for r in requirements)
    assert any("any" in (r.get("condition") or {}) for r in requirements)
    used_ops = set().union(*(_ops(r.get("condition")) for r in requirements))
    assert used_ops == set(ORDERED_OPS) | set(MEMBERSHIP_OPS)


async def test_the_test_corridor_loads_and_can_never_be_published(session_maker):
    corpus = json.loads(TEST_CORRIDOR.read_text(encoding="utf-8"))
    set_codes = [s["jurisdiction"] for s in corpus["sets"]]
    try:
        async with session_maker() as db:
            counts = await load(db, corpus, replace=True)
        assert counts["sets"] == len(corpus["sets"])

        async with session_maker() as db:
            loaded = (
                await db.execute(
                    select(RuleSet).where(RuleSet.jurisdiction_code.in_(set_codes))
                )
            ).scalars().all()
            assert {rs.status for rs in loaded} == {RuleStatus.draft}
            for rs in loaded:
                blockers = await publication_blockers(db, rs)
                assert any("fictional" in b for b in blockers), rs.jurisdiction_code
            # The city hangs under its province, the province under its country.
            city = await db.get(Jurisdiction, "XB-NO-CAP")
            assert city.parent_code == "XB-NO"
    finally:
        async with session_maker() as db:
            for rs_id in (
                await db.execute(
                    select(RuleSet.id).where(RuleSet.jurisdiction_code.in_(set_codes))
                )
            ).scalars().all():
                for sec_id in (
                    await db.execute(
                        select(RuleSection.id).where(RuleSection.rule_set_id == rs_id)
                    )
                ).scalars().all():
                    await db.execute(
                        delete(RuleSource).where(RuleSource.section_id == sec_id)
                    )
                await db.execute(delete(RuleSection).where(RuleSection.rule_set_id == rs_id))
                await db.execute(
                    delete(DocumentRequirement).where(DocumentRequirement.rule_set_id == rs_id)
                )
                await db.execute(delete(RuleQuestion).where(RuleQuestion.rule_set_id == rs_id))
                await db.execute(
                    delete(RuleStatusEvent).where(RuleStatusEvent.rule_set_id == rs_id)
                )
            await db.execute(delete(RuleSet).where(RuleSet.jurisdiction_code.in_(set_codes)))
            # Children before parents: `parent_code` is a foreign key.
            for code in reversed([node["code"] for node in corpus["jurisdictions"]]):
                await db.execute(delete(Jurisdiction).where(Jurisdiction.code == code))
            await db.commit()
