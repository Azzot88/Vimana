"""T3.11.04 / T3.11.05 — load a corridor corpus from a file, always as a draft.

    docker compose -f docker-compose.dev.yml exec -T backend \
        python -m app.cli.load_rules app/data/rules/us-animal-import.json --dry-run
    docker compose -f docker-compose.dev.yml exec -T backend \
        python -m app.cli.load_rules app/data/rules/us-animal-import.json
    docker compose -f docker-compose.dev.yml exec -T backend \
        python -m app.cli.load_rules app/data/rules/us-animal-import.json --replace

**Why a file and not the editor screen.** A corpus is a dozen sections, each
with a citation, plus a dozen documents with their predicates. Typing that
through eight endpoints is a morning's work and an untracked one — nobody can
review it, and the second corridor starts from nothing. A file in the
repository is reviewable in a diff, which is exactly what the owner has to do
before any of it is published.

**Never publishes. Not once, not with a flag.** The loader writes drafts; a
human moves them through review to published in the editor. That is not
ceremony: publication is the moment the platform starts making a checkable
statement about somebody else's law, and a script that could take that step is
a script that eventually takes it by accident. The publication gate
(`core/rule_status`) stays the only door.

**Two validations happen here, before anything is written.**

*A claim needs a citation.* A section with a body and no source is refused —
the whole file, not the section. The publication gate would catch it later, but
"later" means a corpus that cannot be published sitting in the database while
whoever wrote it has forgotten what it was.

*An admitted gap is not a claim.* A section marked `"placeholder": true` may
have no source, and must have no body. That is how the state-by-state layer
lands: one set per state, each saying out loud that it has nothing in it yet.
It cannot be published — it has a section without a citation — which is the
correct outcome and the visible one.

Functions (PROJECT §6.2a):
- `load(db, corpus, replace)` — the whole import, in one transaction.
  Called by: `main`.
- `validate(corpus)` — every reason the file cannot be loaded, as sentences.
  Called by: `load`, and by `main` for `--dry-run`.
- `main(argv)` — CLI entry. Called by: `python -m app.cli.load_rules`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.rule_conditions import ConditionError, validate_condition
from app.core.rule_status import next_version
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    ObtainedBy,
    RuleDirection,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
    RuleStatusEvent,
)


class CorpusError(ValueError):
    """The file cannot be loaded. Every reason, not the first one."""


def validate(corpus: dict) -> list[str]:
    """Every reason this corpus cannot be loaded. Empty list means it can."""
    problems: list[str] = []

    for node in corpus.get("jurisdictions", []):
        try:
            JurisdictionKind(node["kind"])
        except (KeyError, ValueError):
            problems.append(f"jurisdiction `{node.get('code')}`: unknown kind {node.get('kind')!r}")

    for i, rule_set in enumerate(corpus.get("sets", [])):
        where = f"set #{i} ({rule_set.get('category')}/{rule_set.get('direction')}/{rule_set.get('jurisdiction')})"
        try:
            RuleDirection(rule_set["direction"])
        except (KeyError, ValueError):
            problems.append(f"{where}: unknown direction {rule_set.get('direction')!r}")

        sections = rule_set.get("sections", [])
        if not sections:
            problems.append(f"{where}: no sections")

        for section in sections:
            anchor = section.get("anchor", "?")
            placeholder = bool(section.get("placeholder"))
            has_source = bool(section.get("sources"))
            body = (section.get("body") or "").strip()

            if placeholder:
                # An admitted gap. It must not carry text: a placeholder with a
                # body is a claim wearing a label that says it is not one.
                if body or has_source:
                    problems.append(
                        f"{where}, section `{anchor}`: marked placeholder but has "
                        f"a body or a source — a gap that says something is not a gap"
                    )
                continue

            if not has_source:
                problems.append(
                    f"{where}, section `{anchor}`: a claim with no source. Add a "
                    f"citation, or mark it `\"placeholder\": true` and empty the body"
                )
            for src in section.get("sources", []):
                if not (src.get("quote") or "").strip():
                    problems.append(
                        f"{where}, section `{anchor}`: source "
                        f"{src.get('document_title')!r} has no quotation"
                    )
                if not (src.get("authority") or "").strip():
                    problems.append(
                        f"{where}, section `{anchor}`: a source with no authority"
                    )

        codes = [r.get("code") for r in rule_set.get("requirements", [])]
        if len(codes) != len(set(codes)):
            problems.append(f"{where}: duplicate requirement codes")

        for req in rule_set.get("requirements", []):
            try:
                validate_condition(req.get("condition"))
            except ConditionError as exc:
                problems.append(f"{where}, document `{req.get('code')}`: {exc}")
            try:
                ObtainedBy(req.get("obtained_by", "sender"))
            except ValueError:
                problems.append(
                    f"{where}, document `{req.get('code')}`: unknown obtained_by "
                    f"{req.get('obtained_by')!r}"
                )

    return problems


def _as_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


async def load(db, corpus: dict, replace: bool) -> dict:
    """Write the corpus as drafts. One transaction: a half-loaded corpus is
    worse than none, because it looks like a corpus."""
    problems = validate(corpus)
    if problems:
        raise CorpusError("\n".join(problems))

    counts = {"jurisdictions": 0, "sets": 0, "sections": 0, "sources": 0, "documents": 0}

    for node in corpus.get("jurisdictions", []):
        if await db.get(Jurisdiction, node["code"]) is not None:
            continue
        db.add(
            Jurisdiction(
                code=node["code"],
                kind=JurisdictionKind(node["kind"]),
                parent_code=node.get("parent_code"),
                name=node.get("name", ""),
            )
        )
        counts["jurisdictions"] += 1
    await db.flush()

    for spec in corpus["sets"]:
        direction = RuleDirection(spec["direction"])
        code, category = spec["jurisdiction"], spec["category"]

        if await db.get(Jurisdiction, code) is None:
            # Not created silently: a typo in a code would otherwise become a
            # corridor, and a corridor nobody meant to make is a page nobody
            # can find and nobody deletes.
            raise CorpusError(
                f"unknown jurisdiction `{code}` — declare it in `jurisdictions` "
                f"or fix the code"
            )

        # Both unpublished states, not `draft` alone.
        #
        # Matching only drafts had a failure that looked like a broken button:
        # a corpus already sent to review was left alone, a *second* set was
        # created beside it, and the editor went on looking at the old one —
        # publishing blocked by placeholders they had just removed from the
        # file. `--replace` means "this file is the corpus now", and a set
        # waiting for review is still a set this file supersedes.
        existing = (
            await db.execute(
                select(RuleSet).where(
                    RuleSet.direction == direction,
                    RuleSet.jurisdiction_code == code,
                    RuleSet.category_key == category,
                    RuleSet.status.in_((RuleStatus.draft, RuleStatus.review)),
                )
            )
        ).scalars().all()
        if existing and not replace:
            statuses = ", ".join(sorted({s.status.value for s in existing}))
            raise CorpusError(
                f"an unpublished set already exists for "
                f"{category}/{direction.value}/{code} ({statuses}). "
                f"Re-run with --replace to discard it, or publish it first."
            )
        for old in existing:
            sections = (
                await db.execute(
                    select(RuleSection).where(RuleSection.rule_set_id == old.id)
                )
            ).scalars().all()
            for section in sections:
                await db.execute(
                    delete(RuleSource).where(RuleSource.section_id == section.id)
                )
            await db.execute(
                delete(RuleSection).where(RuleSection.rule_set_id == old.id)
            )
            await db.execute(
                delete(DocumentRequirement).where(
                    DocumentRequirement.rule_set_id == old.id
                )
            )
            await db.execute(
                delete(RuleStatusEvent).where(RuleStatusEvent.rule_set_id == old.id)
            )
            await db.delete(old)
        await db.flush()

        rule_set = RuleSet(
            direction=direction,
            jurisdiction_code=code,
            category_key=category,
            title=spec.get("title", ""),
            status=RuleStatus.draft,
            version=await next_version(db, direction, code, category),
        )
        db.add(rule_set)
        await db.flush()
        counts["sets"] += 1

        db.add(
            RuleStatusEvent(
                rule_set_id=rule_set.id,
                to_status=RuleStatus.draft,
                # No actor: this came from a file, not from a person pressing a
                # button. Saying otherwise would put a name on a decision that
                # nobody made at that moment.
                note=f"Loaded from corpus file by `load_rules`.",
            )
        )

        for order, section in enumerate(spec.get("sections", [])):
            row = RuleSection(
                rule_set_id=rule_set.id,
                anchor=section["anchor"],
                locale=section.get("locale", "en"),
                order=section.get("order", order),
                title=section.get("title", ""),
                body=section.get("body", ""),
            )
            db.add(row)
            await db.flush()
            counts["sections"] += 1

            for src in section.get("sources", []):
                db.add(
                    RuleSource(
                        section_id=row.id,
                        authority=src["authority"],
                        document_title=src["document_title"],
                        document_date=_as_date(src.get("document_date")),
                        url=src.get("url", ""),
                        quote=src["quote"],
                    )
                )
                counts["sources"] += 1

        for req in spec.get("requirements", []):
            db.add(
                DocumentRequirement(
                    rule_set_id=rule_set.id,
                    code=req["code"],
                    title=req["title"],
                    issuer=req.get("issuer", ""),
                    obtained_by=ObtainedBy(req.get("obtained_by", "sender")),
                    is_mandatory=req.get("is_mandatory", True),
                    condition=req.get("condition"),
                    valid_for_days=req.get("valid_for_days"),
                    lead_time_days=req.get("lead_time_days"),
                    cost_estimate=req.get("cost_estimate"),
                    currency=req.get("currency", "USD"),
                    notes=req.get("notes", ""),
                )
            )
            counts["documents"] += 1

    await db.commit()
    return counts


async def _run(path: Path, replace: bool, dry_run: bool) -> int:
    corpus = json.loads(path.read_text(encoding="utf-8"))

    problems = validate(corpus)
    if problems:
        print(f"load_rules: {path} cannot be loaded:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    if dry_run:
        sets = corpus.get("sets", [])
        print(f"load_rules: {path} is loadable — {len(sets)} set(s), nothing written")
        for spec in sets:
            placeholders = sum(1 for s in spec.get("sections", []) if s.get("placeholder"))
            print(
                f"  {spec['category']}/{spec['direction']}/{spec['jurisdiction']}: "
                f"{len(spec.get('sections', []))} section(s) "
                f"({placeholders} placeholder), "
                f"{len(spec.get('requirements', []))} document(s)"
            )
        return 0

    async with AsyncSessionLocal() as db:
        counts = await load(db, corpus, replace)

    print(
        "load_rules: loaded as DRAFT — "
        + ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    )
    # Said every time, because the next question is always "is it live?".
    print(
        "load_rules: nothing is published. Open /admin/rules, read it, send it "
        "to review, and publish it there."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load a corridor rules corpus from JSON. Always as a draft."
    )
    parser.add_argument("path", type=Path, help="corpus JSON file")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="discard an existing draft or set on review for the same corridor and load again",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report, write nothing",
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"load_rules: {args.path} does not exist", file=sys.stderr)
        return 1

    try:
        return asyncio.run(_run(args.path, args.replace, args.dry_run))
    except CorpusError as exc:
        print(f"load_rules: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
