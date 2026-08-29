"""T3.11.01 — corridor rules: the two invariants, and the predicate interpreter.

The interesting cases are not "does a row save". They are: can the reference book
end up holding two published answers to one question, and can a rule be stored
that looks accounted for and never fires. Both failures are silent — the first
shows a plausible page built from whichever row came back first, the second shows
a complete-looking corpus with a document quietly missing from every checklist.

`vimana_test` is seeded once and never wiped (ENVIRONMENT.md §8), so every set
built here carries a unique category-and-jurisdiction pair rather than relying on
an empty table.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.rule_conditions import (
    ATTRIBUTES,
    OPS_BY_KIND,
    ConditionAttributeMissing,
    ConditionError,
    evaluate,
    required_attributes,
    validate_condition,
)
from app.models.marketplace import DEFAULT_CATEGORIES, Category
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    RuleDirection,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
)


# --- predicates: validation ------------------------------------------------

def test_null_condition_means_always_required():
    validate_condition(None)
    assert evaluate(None, {}) is True


def test_leaf_condition_round_trips():
    cond = {"attr": "age_years", "op": ">=", "value": 100}
    validate_condition(cond)
    assert evaluate(cond, {"age_years": 120}) is True
    assert evaluate(cond, {"age_years": 40}) is False


def test_unknown_attribute_is_refused():
    """The acceptance case. An attribute the wizard never asks about is a rule
    that never fires, and nothing downstream would ever report it."""
    with pytest.raises(ConditionError) as exc:
        validate_condition({"attr": "colour", "op": "==", "value": "blue"})
    assert "colour" in str(exc.value)


def test_operator_must_suit_the_attribute_kind():
    # `>=` on a boolean parses fine and means nothing.
    with pytest.raises(ConditionError):
        validate_condition({"attr": "author_known", "op": ">=", "value": True})


def test_enum_attribute_rejects_a_value_outside_its_set():
    validate_condition({"attr": "purpose", "op": "==", "value": "resale"})
    with pytest.raises(ConditionError):
        validate_condition({"attr": "purpose", "op": "==", "value": "smuggling"})


def test_boolean_is_not_accepted_as_a_number():
    """`True` is an `int` in Python; without the explicit check it would store
    as a number and compare as 1."""
    with pytest.raises(ConditionError):
        validate_condition({"attr": "age_years", "op": ">=", "value": True})


def test_membership_operator_needs_a_non_empty_list():
    validate_condition({"attr": "breed", "op": "in", "value": ["bengal", "savannah"]})
    with pytest.raises(ConditionError):
        validate_condition({"attr": "breed", "op": "in", "value": "bengal"})
    with pytest.raises(ConditionError):
        validate_condition({"attr": "breed", "op": "in", "value": []})


def test_leaf_shape_is_exact():
    with pytest.raises(ConditionError):
        validate_condition({"attr": "count", "op": ">"})
    with pytest.raises(ConditionError):
        validate_condition({"attr": "count", "op": ">", "value": 1, "extra": "x"})


# --- predicates: grouping --------------------------------------------------

def test_group_of_leaves_is_allowed_both_ways():
    cond = {
        "all": [
            {"attr": "purpose", "op": "==", "value": "resale"},
            {"attr": "count", "op": ">", "value": 3},
        ]
    }
    validate_condition(cond)
    assert evaluate(cond, {"purpose": "resale", "count": 5}) is True
    assert evaluate(cond, {"purpose": "resale", "count": 2}) is False

    any_cond = {"any": cond["all"]}
    validate_condition(any_cond)
    assert evaluate(any_cond, {"purpose": "personal", "count": 5}) is True


def test_nested_groups_are_refused():
    """One level, enforced rather than documented: deeper nesting is a language,
    and a language needs a parser and a precedence table of its own."""
    with pytest.raises(ConditionError) as exc:
        validate_condition(
            {
                "all": [
                    {"attr": "count", "op": ">", "value": 1},
                    {"any": [{"attr": "count", "op": "<", "value": 9}]},
                ]
            }
        )
    assert "nested" in str(exc.value)


def test_group_holds_exactly_one_key():
    with pytest.raises(ConditionError):
        validate_condition(
            {
                "all": [{"attr": "count", "op": ">", "value": 1}],
                "any": [{"attr": "count", "op": "<", "value": 9}],
            }
        )


def test_group_size_is_bounded():
    with pytest.raises(ConditionError):
        validate_condition(
            {"all": [{"attr": "count", "op": ">", "value": i} for i in range(9)]}
        )


# --- predicates: evaluation ------------------------------------------------

def test_missing_answer_raises_instead_of_returning_false():
    """A missing answer is not the same fact as "the rule does not apply".
    Collapsing the two would drop a required document silently."""
    cond = {"attr": "purpose", "op": "==", "value": "resale"}
    with pytest.raises(ConditionAttributeMissing) as exc:
        evaluate(cond, {"count": 1})
    assert exc.value.attr == "purpose"

    # An explicit null is the same absence, not the answer "no".
    with pytest.raises(ConditionAttributeMissing):
        evaluate(cond, {"purpose": None})


def test_answer_of_the_wrong_type_is_a_bad_request_not_a_broken_rule():
    cond = {"attr": "age_years", "op": ">=", "value": 100}
    with pytest.raises(ConditionError):
        evaluate(cond, {"age_years": "ancient"})


def test_required_attributes_names_the_questions_to_ask():
    cond = {
        "all": [
            {"attr": "purpose", "op": "==", "value": "resale"},
            {"attr": "breed", "op": "in", "value": ["bengal"]},
        ]
    }
    assert required_attributes(cond) == {"purpose", "breed"}
    assert required_attributes(None) == set()
    assert required_attributes({"attr": "count", "op": ">", "value": 1}) == {"count"}


def test_every_declared_attribute_has_a_usable_operator():
    """Guards against adding an attribute kind and forgetting its operator row —
    the failure would be an attribute nobody can write a rule about."""
    for name, (kind, _allowed) in ATTRIBUTES.items():
        assert OPS_BY_KIND.get(kind), f"{name}: kind {kind} has no operators"


# --- category registry -----------------------------------------------------

async def test_art_is_a_seeded_category(session_maker):
    """The art corpus (T3.11.05) is entirely about a category that did not
    exist."""
    assert "art" in DEFAULT_CATEGORIES
    async with session_maker() as db:
        row = (
            await db.execute(select(Category).where(Category.name_key == "art"))
        ).scalar_one_or_none()
    assert row is not None and row.is_default


# --- rule sets: the published invariant ------------------------------------

@pytest.fixture
async def corridor(session_maker):
    """A private jurisdiction and category, so the invariant tests cannot trip
    over rows another test left behind."""
    suffix = uuid.uuid4().hex[:6]
    code = f"ZZ-{suffix}"
    cat_key = f"testcat-{suffix}"

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
            await db.execute(
                delete(DocumentRequirement).where(
                    DocumentRequirement.rule_set_id == rs.id
                )
            )
            sections = (
                await db.execute(
                    select(RuleSection).where(RuleSection.rule_set_id == rs.id)
                )
            ).scalars().all()
            for sec in sections:
                await db.execute(
                    delete(RuleSource).where(RuleSource.section_id == sec.id)
                )
            await db.execute(
                delete(RuleSection).where(RuleSection.rule_set_id == rs.id)
            )
        await db.execute(delete(RuleSet).where(RuleSet.jurisdiction_code == code))
        await db.execute(delete(Category).where(Category.name_key == cat_key))
        await db.execute(delete(Jurisdiction).where(Jurisdiction.code == code))
        await db.commit()


def _rule_set(code: str, cat_key: str, *, version: int, status: RuleStatus) -> RuleSet:
    return RuleSet(
        direction=RuleDirection.import_,
        jurisdiction_code=code,
        category_key=cat_key,
        version=version,
        status=status,
    )


async def test_second_published_version_is_impossible(session_maker, corridor):
    """The acceptance case. Two published sets are two answers to one question,
    and the page would render whichever row came back first."""
    code, cat_key = corridor
    async with session_maker() as db:
        db.add(_rule_set(code, cat_key, version=1, status=RuleStatus.published))
        await db.commit()

    async with session_maker() as db:
        db.add(_rule_set(code, cat_key, version=2, status=RuleStatus.published))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


async def test_superseded_versions_may_coexist_with_the_published_one(
    session_maker, corridor
):
    """The index is partial for a reason: history has to stay in the table, or
    "what did this say in March" stops being answerable."""
    code, cat_key = corridor
    async with session_maker() as db:
        db.add(_rule_set(code, cat_key, version=1, status=RuleStatus.outdated))
        db.add(_rule_set(code, cat_key, version=2, status=RuleStatus.outdated))
        db.add(_rule_set(code, cat_key, version=3, status=RuleStatus.published))
        db.add(_rule_set(code, cat_key, version=4, status=RuleStatus.draft))
        await db.commit()

        rows = (
            await db.execute(
                select(RuleSet).where(RuleSet.jurisdiction_code == code)
            )
        ).scalars().all()
    assert len(rows) == 4
    assert sum(1 for r in rows if r.status is RuleStatus.published) == 1


async def test_version_number_cannot_repeat_within_a_triple(session_maker, corridor):
    code, cat_key = corridor
    async with session_maker() as db:
        db.add(_rule_set(code, cat_key, version=1, status=RuleStatus.draft))
        await db.commit()

    async with session_maker() as db:
        db.add(_rule_set(code, cat_key, version=1, status=RuleStatus.review))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


async def test_a_set_starts_unreviewed_and_unchecked(session_maker, corridor):
    """Three dates, and none of them may be invented at creation: an unreviewed
    corpus must be distinguishable from a reviewed one."""
    code, cat_key = corridor
    async with session_maker() as db:
        rs = _rule_set(code, cat_key, version=1, status=RuleStatus.draft)
        db.add(rs)
        await db.commit()
        await db.refresh(rs)

    assert rs.reviewed_at is None
    assert rs.checked_at is None
    assert rs.needs_review is False
    assert rs.effective_from is not None


# --- requirements ----------------------------------------------------------

async def test_requirement_with_an_unknown_attribute_never_reaches_the_database(
    session_maker, corridor
):
    """Validation lives on the model, so a CLI import or a fixture cannot get
    around it the way it could get around an endpoint."""
    code, cat_key = corridor
    async with session_maker() as db:
        rs = _rule_set(code, cat_key, version=1, status=RuleStatus.draft)
        db.add(rs)
        await db.commit()
        await db.refresh(rs)

        with pytest.raises(ConditionError):
            DocumentRequirement(
                rule_set_id=rs.id,
                code="bogus",
                title="Made-up paper",
                condition={"attr": "colour", "op": "==", "value": "blue"},
            )


async def test_requirement_code_is_unique_within_a_set(session_maker, corridor):
    code, cat_key = corridor
    async with session_maker() as db:
        rs = _rule_set(code, cat_key, version=1, status=RuleStatus.draft)
        db.add(rs)
        await db.commit()
        await db.refresh(rs)
        set_id = rs.id

        db.add(
            DocumentRequirement(
                rule_set_id=set_id, code="health_cert", title="Health certificate"
            )
        )
        await db.commit()

    async with session_maker() as db:
        db.add(
            DocumentRequirement(
                rule_set_id=set_id, code="health_cert", title="Duplicate"
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


async def test_lead_time_survives_the_round_trip(session_maker, corridor):
    """`lead_time_days` is the field the checklist counts backwards from
    `depart_at`; a null here is the difference between "order it now" and
    silence."""
    code, cat_key = corridor
    async with session_maker() as db:
        rs = _rule_set(code, cat_key, version=1, status=RuleStatus.draft)
        db.add(rs)
        await db.commit()
        await db.refresh(rs)

        req = DocumentRequirement(
            rule_set_id=rs.id,
            code="export_conclusion",
            title="Conclusion on cultural value",
            issuer="Authorised expert",
            lead_time_days=21,
            valid_for_days=180,
            condition={"attr": "age_years", "op": ">=", "value": 100},
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)

    assert req.lead_time_days == 21
    assert req.condition == {"attr": "age_years", "op": ">=", "value": 100}
    assert req.is_mandatory is True


async def test_section_and_source_hang_together(session_maker, corridor):
    code, cat_key = corridor
    async with session_maker() as db:
        rs = _rule_set(code, cat_key, version=1, status=RuleStatus.draft)
        db.add(rs)
        await db.commit()
        await db.refresh(rs)

        section = RuleSection(
            rule_set_id=rs.id, anchor="overview", order=0, locale="en", title="Overview"
        )
        db.add(section)
        await db.commit()
        await db.refresh(section)

        db.add(
            RuleSource(
                section_id=section.id,
                authority="Test Authority",
                document_title="Test Regulation",
                quote="A verbatim quotation, never a paraphrase.",
            )
        )
        await db.commit()

        sources = (
            await db.execute(
                select(RuleSource).where(RuleSource.section_id == section.id)
            )
        ).scalars().all()
    assert len(sources) == 1


async def test_same_anchor_may_repeat_across_locales(session_maker, corridor):
    """Translation is per row (T3.11.13): the English and Russian `overview` are
    two rows of the same section, not two sections."""
    code, cat_key = corridor
    async with session_maker() as db:
        rs = _rule_set(code, cat_key, version=1, status=RuleStatus.draft)
        db.add(rs)
        await db.commit()
        await db.refresh(rs)

        db.add(RuleSection(rule_set_id=rs.id, anchor="overview", locale="en"))
        db.add(RuleSection(rule_set_id=rs.id, anchor="overview", locale="ru"))
        await db.commit()

        rows = (
            await db.execute(
                select(RuleSection).where(RuleSection.rule_set_id == rs.id)
            )
        ).scalars().all()
    assert {r.locale for r in rows} == {"en", "ru"}
