"""T3.11.07 — monthly check that the vendored payment catalogue still matches.

Checks and reports. It does **not** write, ever, and that is the whole design:
the catalogue was vendored so that changes to it are reviewable, and a copy that
rewrites itself on a schedule is a copy nobody has read. What this task produces
is an offer — "there are seventeen differences, here they are" — and a person
decides whether to accept it by running
`python -m app.cli.refresh_payment_systems --write`.

Monthly, because a list of payment services moves at the speed of the payments
industry, not of our deploys. Owner's decision 2026-09-06.

Failure is not an error here. The stored copy is still serving every request,
which is the entire reason it is stored; an unreachable third party is a fact
worth one log line, not a red pipeline.
"""
from __future__ import annotations

import json
import logging

import httpx

from app.core.directories import HODLHODL_PATH
from app.worker import celery_app

logger = logging.getLogger(__name__)

SOURCE_URL = "https://hodlhodl.com/api/v1/payment_methods"
# Long enough that a slow third party does not hold a worker, short enough that
# a hung connection does not sit there until the next monthly tick.
TIMEOUT_SECONDS = 30.0


@celery_app.task(name="app.tasks.directories.check_payment_catalogue")
def check_payment_catalogue() -> dict:
    """Compare the stored catalogue against upstream and log the difference.

    Returns the counts so a caller — or a test — can assert on them without
    parsing logs.

    Called by: celery beat (`worker.beat_schedule`), `tests/test_directories.py`.
    """
    stored = json.loads(HODLHODL_PATH.read_text(encoding="utf-8"))
    old = {str(m["id"]): m for m in stored.get("payment_methods", [])}

    try:
        response = httpx.get(
            SOURCE_URL,
            timeout=TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        fresh = response.json()
    except Exception as exc:  # noqa: BLE001 — the operator wants the reason
        logger.warning("payment catalogue check: could not reach upstream: %s", exc)
        return {"reachable": False}

    new = {str(m["id"]): m for m in fresh.get("payment_methods", [])}
    added = sorted(new[i]["name"] for i in new.keys() - old.keys())
    removed = sorted(old[i]["name"] for i in old.keys() - new.keys())
    renamed = sorted(
        f"{old[i]['name']} → {new[i]['name']}"
        for i in old.keys() & new.keys()
        if old[i]["name"] != new[i]["name"]
    )

    result = {
        "reachable": True,
        "stored": len(old),
        "upstream": len(new),
        "added": added,
        "removed": removed,
        "renamed": renamed,
    }

    if not (added or removed or renamed):
        logger.info("payment catalogue check: unchanged (%d methods)", len(old))
        return result

    # WARNING rather than INFO: this is the one line that asks somebody to do
    # something, and it should not sit at the level everything else is at.
    logger.warning(
        "payment catalogue check: %d added, %d removed, %d renamed — "
        "review and run `python -m app.cli.refresh_payment_systems --write`. "
        "added=%s removed=%s renamed=%s",
        len(added),
        len(removed),
        len(renamed),
        added[:20],
        removed[:20],
        renamed[:20],
    )
    return result
