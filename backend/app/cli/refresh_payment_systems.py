"""T3.11.07 — refresh the vendored HodlHodl payment catalogue.

    docker compose -f docker-compose.dev.yml exec -T backend \
        python -m app.cli.refresh_payment_systems
    docker compose -f docker-compose.dev.yml exec -T backend \
        python -m app.cli.refresh_payment_systems --write

Reports first and writes only when asked. A catalogue that silently rewrites
itself on a schedule is a catalogue nobody has read: the point of vendoring it
was that changes are reviewable, and a diff nobody looks at is the same as no
copy at all.

What it prints is what a reviewer needs and nothing else — how many entries
appeared, disappeared and were renamed, by name. The full file is 432 rows; a
line-by-line dump would bury the four that changed.

Owner's decision 2026-09-06 to vendor this catalogue at all. The legal footing
is written into the file's own `_source` block rather than here, so it travels
with the data.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timezone, datetime
from pathlib import Path

import httpx

SOURCE_URL = "https://hodlhodl.com/api/v1/payment_methods"
TARGET = Path(__file__).parent.parent / "data" / "payment_systems_hodlhodl.json"


def _index(methods: list[dict]) -> dict[str, dict]:
    return {str(m["id"]): m for m in methods}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the new catalogue; without it nothing is changed",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    current = json.loads(TARGET.read_text(encoding="utf-8"))
    try:
        response = httpx.get(
            SOURCE_URL, timeout=args.timeout, headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        fresh = response.json()
    except Exception as exc:  # noqa: BLE001 — the operator wants the reason, plainly
        print(f"could not fetch {SOURCE_URL}: {exc}", file=sys.stderr)
        # Not an error worth failing a pipeline over: the stored copy is still
        # serving, which is the entire reason it is stored.
        return 0

    old = _index(current.get("payment_methods", []))
    new = _index(fresh.get("payment_methods", []))

    added = [new[i]["name"] for i in new.keys() - old.keys()]
    removed = [old[i]["name"] for i in old.keys() - new.keys()]
    renamed = [
        f"{old[i]['name']} → {new[i]['name']}"
        for i in old.keys() & new.keys()
        if old[i]["name"] != new[i]["name"]
    ]
    recountried = [
        new[i]["name"]
        for i in old.keys() & new.keys()
        if sorted(old[i].get("country_codes") or [])
        != sorted(new[i].get("country_codes") or [])
    ]

    print(f"stored: {len(old)} methods · upstream: {len(new)}")
    for label, items in (
        ("added", added),
        ("removed", removed),
        ("renamed", renamed),
        ("countries changed", recountried),
    ):
        if items:
            print(f"\n{label} ({len(items)}):")
            for item in sorted(items):
                print(f"  {item}")
    if not (added or removed or renamed or recountried):
        print("no changes")
        return 0

    if not args.write:
        print("\nnothing written — rerun with --write to accept")
        return 0

    countries = {
        iso for m in new.get("payment_methods", []) for iso in (m.get("country_codes") or [])
    }
    source = dict(current.get("_source", {}))
    source["fetched_at"] = date.today().isoformat()
    source["counts"] = {
        "methods": len(new.get("payment_methods", [])),
        "countries": len(countries),
    }
    source["refreshed_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    TARGET.write_text(
        json.dumps(
            {"_source": source, "payment_methods": new.get("payment_methods", [])},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwritten: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
