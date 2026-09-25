"""T_UX.31 — every button in a letter leads to an address the app has.

Ревизия путей 2026-09-23 found two letters pointing nowhere: the arbiter's
«you were picked» linked to `/admin`, which the app does not route, and the
corridor letter promised «Открыть рейс» and carried no link at all. Neither
could fail a test, because nothing compared the letters with the app.

This is that comparison, done statically: the buttons are `cta_url=f"{base}/…"`
in `tasks/notifications.py`, and each path must match one of the addresses the
frontend routes (`frontend/src/App.tsx`). A new letter pointing somewhere new
adds its address here, next to the route that serves it — the list is short on
purpose, so that adding to it is a decision rather than a habit.
"""
from __future__ import annotations

import re
from pathlib import Path

# Addresses a letter may open, as `App.tsx` routes them. `{…}` placeholders in
# the f-string are compared as a single path segment.
APP_PATHS = (
    r"/deals/[^/]+/vault",
    r"/trips/[^/]+/respond",
    r"/disputes",
    r"/profile",
    r"/profile/keys",
    r"/login",
    r"/reset-password",
)


def _letter_targets() -> list[str]:
    from app.tasks import notifications

    source = Path(notifications.__file__).read_text(encoding="utf-8")
    # The path up to a query string: `/reset-password?token=…` routes as
    # `/reset-password`.
    return re.findall(r'cta_url=f"\{base\}(/[^"?]*)', source)


def test_the_scan_still_finds_the_letters():
    """Guards the pattern itself: a scan that finds nothing passes everything."""
    assert len(_letter_targets()) >= 5


def test_every_letter_button_leads_somewhere_the_app_has():
    for target in _letter_targets():
        normalised = re.sub(r"\{[^}]+\}", "X", target)
        assert any(re.fullmatch(p, normalised) for p in APP_PATHS), (
            f"a letter links to {target!r}, which the app does not route"
        )
