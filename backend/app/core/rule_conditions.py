"""T3.11.01 — predicates that decide whether a document is required.

A rule says "this paper is needed if the object is older than a hundred years"
or "if the animal is brought in for resale". That sentence has to be **computed**,
not read: the checklist (T3.11.06) and the MCP tool (T3.11.12) both turn a set
of answers into a list of documents, and a sentence in prose turns into nothing.

Three properties are the whole design, and each one is a refusal:

**No expression language.** A condition is data — a dict with a closed set of
keys — and it is walked by the interpreter below. There is no `eval`, no
`compile`, no attribute lookup by string on an object. The rule editor is a
privileged screen but not a shell, and a compliance editor typing a predicate is
not typing Python.

**A closed list of attributes.** `ATTRIBUTES` is the whole vocabulary. An
attribute outside it cannot be saved, because an attribute the wizard never asks
about is a rule that never fires — and it looks accounted for while doing
nothing. That failure mode is silent by construction, which is why it is blocked
at write time rather than reported at read time.

**One level of grouping, and no more.** A leaf is `{"attr", "op", "value"}`;
`{"all": [...]}` and `{"any": [...]}` may hold leaves only. Real requirements do
need conjunction — "for resale" *and* "younger than six months" is one document,
not two — but arbitrary nesting is a language, and a language needs a parser, a
precedence table and a test suite of its own. Two levels answer the rules we
have; the third is where this stops being data.

Functions:
- `validate_condition(condition)` — raise `ConditionError` if it cannot be stored.
  Called by: `models.rules.DocumentRequirement` validator, and the rule editor
  (T3.11.02) before publication.
- `evaluate(condition, attrs)` — True if the document is required for these
  answers. Raises `ConditionAttributeMissing` rather than guessing.
  Called by: the checklist builder (T3.11.06) and `build_checklist` (T3.11.12).
- `required_attributes(condition)` — which questions the wizard must ask for
  this condition to be answerable at all. Called by: T3.11.06.
"""
from __future__ import annotations

from typing import Any

# --- vocabulary ------------------------------------------------------------

NUMBER = "number"
INTEGER = "integer"
BOOLEAN = "boolean"
STRING = "string"
ENUM = "enum"

# name -> (kind, allowed values or None)
#
# Fixed by IMPLEMENTATIONPLAN §3.11.2 under the two first corpora. It grows by a
# code change plus a migration of the affected rules, never by free input from
# the editor screen.
ATTRIBUTES: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "age_years": (INTEGER, None),          # age of the object, art corpus
    "declared_value": (NUMBER, None),      # declared value in the deal currency
    "author_known": (BOOLEAN, None),       # art: attributed to a known author
    "species": (STRING, None),             # animal corpus
    "breed": (STRING, None),               # animal corpus: bengal, savannah, …
    "generation": (STRING, None),          # hybrid generation: F1 … F5, unknown
    "purpose": (ENUM, ("personal", "resale")),
    "count": (INTEGER, None),              # how many objects / animals
}

ORDERED_OPS = ("==", "!=", ">", ">=", "<", "<=")
MEMBERSHIP_OPS = ("in", "not_in")
EQUALITY_OPS = ("==", "!=")

# Which operators make sense for which kind of attribute. `>=` on a boolean is
# not a stricter rule, it is a mistake that happens to parse.
OPS_BY_KIND: dict[str, tuple[str, ...]] = {
    NUMBER: ORDERED_OPS + MEMBERSHIP_OPS,
    INTEGER: ORDERED_OPS + MEMBERSHIP_OPS,
    BOOLEAN: EQUALITY_OPS,
    STRING: EQUALITY_OPS + MEMBERSHIP_OPS,
    ENUM: EQUALITY_OPS + MEMBERSHIP_OPS,
}

GROUP_KEYS = ("all", "any")
MAX_GROUP_SIZE = 8


class ConditionError(ValueError):
    """The condition cannot be stored: shape, attribute or operator is wrong."""


class ConditionAttributeMissing(LookupError):
    """The answers do not contain an attribute the condition asks about.

    Deliberately an exception rather than a False. A missing answer is not the
    same fact as "the rule does not apply", and collapsing the two would drop a
    required document silently — the one failure this whole subsystem exists to
    prevent. The caller decides, and IMPLEMENTATIONPLAN §3.11.6 tells it to
    decide strictly: unknown means include the document.
    """

    def __init__(self, attr: str) -> None:
        super().__init__(attr)
        self.attr = attr


# --- validation ------------------------------------------------------------

def validate_condition(condition: Any) -> None:
    """Raise `ConditionError` unless `condition` is a storable predicate.

    `None` is valid and means "always required" — most documents are
    unconditional, and forcing a tautology onto them would be noise.
    """
    if condition is None:
        return
    if not isinstance(condition, dict):
        raise ConditionError("condition must be an object or null")

    group_key = _group_key(condition)
    if group_key is None:
        _validate_leaf(condition)
        return

    members = condition[group_key]
    if not isinstance(members, list) or not members:
        raise ConditionError(f"`{group_key}` must be a non-empty list")
    if len(members) > MAX_GROUP_SIZE:
        raise ConditionError(f"`{group_key}` holds at most {MAX_GROUP_SIZE} conditions")
    for member in members:
        if not isinstance(member, dict):
            raise ConditionError("group members must be objects")
        if _group_key(member) is not None:
            # The one-level rule, enforced rather than documented.
            raise ConditionError("groups cannot be nested")
        _validate_leaf(member)


def _group_key(condition: dict) -> str | None:
    present = [k for k in GROUP_KEYS if k in condition]
    if not present:
        return None
    if len(present) > 1 or len(condition) != 1:
        raise ConditionError("a group holds exactly one of `all` / `any` and nothing else")
    return present[0]


def _validate_leaf(leaf: dict) -> None:
    if set(leaf) != {"attr", "op", "value"}:
        raise ConditionError("a condition is exactly {attr, op, value}")

    attr, op, value = leaf["attr"], leaf["op"], leaf["value"]
    if attr not in ATTRIBUTES:
        raise ConditionError(
            f"unknown attribute `{attr}`; the wizard never asks it, so the rule "
            f"would never fire. Known: {', '.join(sorted(ATTRIBUTES))}"
        )
    kind, allowed = ATTRIBUTES[attr]
    if op not in OPS_BY_KIND[kind]:
        raise ConditionError(f"operator `{op}` does not apply to a {kind} attribute")

    if op in MEMBERSHIP_OPS:
        if not isinstance(value, list) or not value:
            raise ConditionError(f"`{op}` needs a non-empty list")
        for item in value:
            _validate_value(attr, kind, allowed, item)
    else:
        _validate_value(attr, kind, allowed, value)


def _validate_value(attr: str, kind: str, allowed: tuple[str, ...] | None, value: Any) -> None:
    if kind in (NUMBER, INTEGER):
        # bool is an int in Python; accepting it here would let `True` pass as a
        # number and compare as 1.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConditionError(f"`{attr}` expects a number")
        if kind == INTEGER and not isinstance(value, int):
            raise ConditionError(f"`{attr}` expects a whole number")
    elif kind == BOOLEAN:
        if not isinstance(value, bool):
            raise ConditionError(f"`{attr}` expects true or false")
    elif kind in (STRING, ENUM):
        if not isinstance(value, str) or not value:
            raise ConditionError(f"`{attr}` expects a non-empty string")
        if allowed is not None and value not in allowed:
            raise ConditionError(
                f"`{attr}` accepts only {', '.join(allowed)}"
            )


# --- evaluation ------------------------------------------------------------

def evaluate(condition: Any, attrs: dict[str, Any]) -> bool:
    """True if a document carrying this condition is required for `attrs`.

    Raises `ConditionAttributeMissing` when an answer the condition needs is not
    there. Callers must not swallow it into False — see the exception's docstring.
    """
    if condition is None:
        return True

    group_key = _group_key(condition)
    if group_key is None:
        return _evaluate_leaf(condition, attrs)

    results = [_evaluate_leaf(member, attrs) for member in condition[group_key]]
    return all(results) if group_key == "all" else any(results)


def _evaluate_leaf(leaf: dict, attrs: dict[str, Any]) -> bool:
    attr, op, value = leaf["attr"], leaf["op"], leaf["value"]
    if attr not in attrs or attrs[attr] is None:
        raise ConditionAttributeMissing(attr)
    actual = attrs[attr]

    if op == "==":
        return actual == value
    if op == "!=":
        return actual != value
    if op == "in":
        return actual in value
    if op == "not_in":
        return actual not in value

    # Ordered comparison. The stored predicate is validated, the *answers* are
    # not — they arrive from a public wizard — so a wrong type here is a bad
    # request, not a broken rule.
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        raise ConditionError(f"`{attr}` must be a number to compare with `{op}`")
    if op == ">":
        return actual > value
    if op == ">=":
        return actual >= value
    if op == "<":
        return actual < value
    return actual <= value


def required_attributes(condition: Any) -> set[str]:
    """Which answers the wizard must collect for this condition to be decidable.

    The union over every requirement in a corridor is exactly the questionnaire
    T3.11.06 has to ask. Computing it beats maintaining a second list by hand,
    which would drift the first time a rule gained a clause.
    """
    if condition is None:
        return set()
    group_key = _group_key(condition)
    if group_key is None:
        return {condition["attr"]}
    return {member["attr"] for member in condition[group_key]}
