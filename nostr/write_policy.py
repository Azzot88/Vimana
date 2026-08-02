#!/usr/bin/env python3
"""strfry writePolicy plugin — WoT-gate.

Reads one request-JSON per line on stdin, writes one decision-JSON per line
on stdout. Whitelist file is refreshed from Postgres by the backend Celery
task `nostr_whitelist.refresh_allowed_pubkeys`.

Requests (per strfry writePolicy plugin spec):
    {"type": "new", "event": {...}, "receivedAt": ..., "sourceType": "...", "sourceInfo": "..."}
Decisions:
    {"id": "<event_id>", "action": "accept"|"reject"|"shadowReject", "msg": "..."}

Simple hot-reload: file mtime is checked once per request. Cheap for the
strfry-scale ingest rate (thousands of events/hour) and avoids inotify deps.
"""
from __future__ import annotations

import json
import os
import sys

ALLOWED_FILE = os.environ.get("NOSTR_ALLOWED_PUBKEYS_FILE", "/data/allowed_pubkeys.txt")

_cached: set[str] = set()
_cached_mtime: float = 0.0


def _reload_if_changed() -> set[str]:
    global _cached, _cached_mtime
    try:
        mtime = os.path.getmtime(ALLOWED_FILE)
    except OSError:
        return _cached
    if mtime > _cached_mtime:
        try:
            with open(ALLOWED_FILE) as f:
                _cached = {ln.strip() for ln in f if ln.strip()}
            _cached_mtime = mtime
        except OSError:
            pass
    return _cached


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        event = req.get("event", {}) or {}
        pubkey = event.get("pubkey", "")
        allowed = _reload_if_changed()
        if pubkey in allowed:
            result = {"id": event.get("id", ""), "action": "accept", "msg": ""}
        else:
            result = {
                "id": event.get("id", ""),
                "action": "reject",
                "msg": "blocked: pubkey not in Vimana WoT",
            }
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
