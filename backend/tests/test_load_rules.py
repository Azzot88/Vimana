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
from app.core.rule_status import publication_blockers
from app.models.marketplace import Category
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
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

def test_the_shipped_animal_corpus_is_loadable():
    """The file in the repository must always be valid — it is reviewed in a
    diff, and a diff of a file that cannot load is a review of nothing."""
    path = Path(__file__).resolve().parent.parent / "app" / "data" / "rules" / "us-animal-import.json"
    corpus = json.loads(path.read_text(encoding="utf-8"))
    assert validate(corpus) == []

    section_anchors = {s["anchor"] for s in corpus["sets"][0]["sections"]}
    # The three layers nobody has sourced yet are present as admitted gaps
    # rather than absent — an absent section is indistinguishable from a
    # complete corpus.
    assert {"hybrid-breeds", "state-and-city", "transit"} <= section_anchors
