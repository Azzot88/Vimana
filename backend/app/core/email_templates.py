"""T_UX.9 — render a letter in one of six languages, as HTML and as text.

One layout (`app/emails/layout.html`), one string catalogue per locale
(`app/emails/locales/*.json`), and a small descriptor per letter here. Six HTML
files would have drifted apart by the third edit; this way a change to the
frame is one change.

**The text part is built from the catalogue, not from the HTML.** Stripping
tags out of a rendered table produces something that technically parses and
reads like debris — and the text part is what spam filters and a share of
clients actually read. Same strings, two renderers.

`en` is the fallback and the reference: a missing locale file, an unknown
language tag and a key that only exists in English all resolve there rather
than raising. A letter that arrives in the wrong language is a flaw; a letter
that does not arrive because a translator missed a key is an outage.

New letter → add a `_LETTERS` entry here and the same key to **all six**
catalogues. `test_email_templates.py` fails on a catalogue missing a key, which
is how "we'll translate it later" is prevented from shipping.

Functions (PROJECT §6.2a):
- `render(kind, locale, **ctx) -> Rendered` — the only public entry point.
  Called by: `tasks/notifications.py` (all six letters), `cli/email_preview.py`.
- `available_locales()` — the six tags, for tests and the preview command.
  Called by: `cli/email_preview.py`, `tests/test_email_templates.py`.
- `_catalogue(locale)` — loads and caches one locale's JSON. Called by `render`.
- `_fill(value, ctx)` — renders `{{ … }}` inside a catalogue string.
  Called by `render`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

_EMAILS_DIR = Path(__file__).resolve().parent.parent / "emails"
_LOCALES_DIR = _EMAILS_DIR / "locales"

DEFAULT_LOCALE = "en"
LOCALES: tuple[str, ...] = ("en", "ru", "ua", "pl", "fr", "es")

# Which optional blocks each letter uses. The layout renders whatever it is
# given; this says what to give it, so a letter's shape lives in one line
# rather than scattered across the call sites.
_LETTERS: dict[str, dict[str, Any]] = {
    "verification_code": {"code": True},
    "recovery_code_used": {"facts": ["remaining"]},
    "platform_copy_deleted": {},
    "archive_window_opened": {"facts": ["deadline"]},
    "waitlist_confirmation": {},
    "waitlist_admin": {
        "facts": ["email", "name", "source", "when", "total", "confirmation"]
    },
    "deal_status": {},
    "deadline_reminder": {},
}

_env = Environment(
    loader=FileSystemLoader(str(_EMAILS_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


CHAT_KINDS: tuple[str, ...] = ("linked", "stale", "hello")


def chat_message(kind: str, locale: str | None) -> str:
    """Plain localised text for a chat transport (Telegram today).

    Separate from `render` on purpose. A letter has a subject, a layout and two
    MIME parts; a chat message is a string. Passing one through the other would
    have meant a footer inviting the reader to reply to an email, inside a bot
    that cannot be replied to.

    Same six catalogues though, and the same fallback rule — one place where a
    translation lives, whichever pipe it eventually goes down.

    Called by: `tasks/notifications.send_telegram_chat`.
    """
    tag = (locale or DEFAULT_LOCALE).split("-")[0].lower()
    if tag not in LOCALES:
        tag = DEFAULT_LOCALE
    block = {**_catalogue(DEFAULT_LOCALE).get("chat", {}), **_catalogue(tag).get("chat", {})}
    return block[kind]


def sample_context(kind: str) -> dict[str, Any]:
    """Plausible values for one letter's placeholders.

    Deliberately awkward rather than "Test User": a long name with an em dash,
    a timezone-aware date, a plus-addressed mailbox. Placeholder data that is
    too tidy is how layouts that break on real content get signed off.

    Called by: `cli/email_preview.main`, `api/admin.email_templates`, tests.
    """
    from datetime import datetime, timezone

    when = datetime(2026, 8, 8, 20, 28, 52, tzinfo=timezone.utc)
    samples: dict[str, dict[str, Any]] = {
        "verification_code": {"code": "418305"},
        "recovery_code_used": {"remaining": 7},
        "platform_copy_deleted": {},
        "archive_window_opened": {"deadline": "2026-11-06"},
        "waitlist_confirmation": {},
        "waitlist_admin": {
            "email": "alan.cherkasov+waitlist@example.com",
            "name": "Alan Cherkasov — Дубай",
            "source": "landing",
            "when": when,
            "total": 3,
            "confirmation": "—",
        },
        "deal_status": {"status": "in_transit"},
        "deadline_reminder": {},
    }
    return samples[kind]


@dataclass(frozen=True)
class Rendered:
    subject: str
    html: str
    text: str


def available_locales() -> tuple[str, ...]:
    return LOCALES


@lru_cache(maxsize=len(LOCALES) + 1)
def _catalogue(locale: str) -> dict[str, Any]:
    path = _LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        path = _LOCALES_DIR / f"{DEFAULT_LOCALE}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _fill(value: str, ctx: dict[str, Any]) -> str:
    """Render `{{ placeholders }}` inside a catalogue string.

    Jinja rather than `str.format`: a translator writing a literal brace should
    not break delivery, and `{{ }}` is the syntax already used in the layout.
    """
    return Template(value).render(**ctx)


def render(kind: str, locale: str | None, **ctx: Any) -> Rendered:
    """Build one letter. `locale` may be None, unknown, or a full tag like `ru-RU`."""
    tag = (locale or DEFAULT_LOCALE).split("-")[0].lower()
    if tag not in LOCALES:
        tag = DEFAULT_LOCALE

    cat = _catalogue(tag)
    fallback = _catalogue(DEFAULT_LOCALE)
    strings: dict[str, Any] = {**fallback.get(kind, {}), **cat.get(kind, {})}
    shape = _LETTERS[kind]

    # `deal_status` names itself: the heading *is* the status label, and the
    # label is per-locale. Resolved before the strings are filled so that
    # `{{ label }}` in subject/heading/preheader all see the same word.
    if kind == "deal_status":
        labels = strings.get("labels", {})
        status = ctx.get("status", "")
        ctx = {**ctx, "label": labels.get(status, status)}

    subject = _fill(strings["subject"], ctx)
    heading = _fill(strings["heading"], ctx)
    preheader = _fill(strings.get("preheader", ""), ctx)
    body = [_fill(p, ctx) for p in strings.get("body", [])]
    note = _fill(strings["note"], ctx) if strings.get("note") else ""
    footer = cat.get("footer", fallback["footer"])

    code = str(ctx["code"]) if shape.get("code") and ctx.get("code") else ""
    code_label = strings.get("code_label", "") if code else ""

    facts: list[tuple[str, str]] = []
    for name in shape.get("facts", []):
        value = ctx.get(name)
        if value is None or value == "":
            continue
        label = strings.get(f"facts_{name}", name)
        facts.append((label, str(value)))

    html = _env.get_template("layout.html").render(
        preheader=preheader,
        heading=heading,
        body=body,
        code=code,
        code_label=code_label,
        facts=facts,
        cta_url=ctx.get("cta_url", ""),
        cta_label=ctx.get("cta_label", ""),
        note=note,
        footer=footer,
    )

    lines: list[str] = [heading, ""]
    lines.extend(body)
    if code:
        lines += ["", f"{code}" + (f"  ({code_label})" if code_label else "")]
    if facts:
        lines.append("")
        lines += [f"{label}: {value}" for label, value in facts]
    if ctx.get("cta_url"):
        lines += ["", str(ctx["cta_url"])]
    if note:
        lines += ["", note]
    lines += ["", "—", footer]
    text = "\n".join(lines).strip() + "\n"

    return Rendered(subject=subject, html=html, text=text)
