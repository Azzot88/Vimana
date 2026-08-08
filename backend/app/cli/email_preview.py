"""T_UX.9 — render every letter to a file, so it can be looked at before anyone gets it.

    docker compose exec -T backend python -m app.cli.email_preview
    docker compose exec -T backend python -m app.cli.email_preview --locale ru
    docker compose exec -T backend python -m app.cli.email_preview --kind verification_code

Writes `<out>/<kind>.<locale>.html` plus an `index.html` linking them all, and
prints the paths. Nothing is sent and no SMTP is contacted — this is the
cheapest loop for working on wording and layout.

It is not a substitute for Mailpit, and the two answer different questions. A
browser shows the ideal case: it renders the HTML as written. Mailpit shows
what actually left over SMTP — headers, both MIME parts, encoding — which is
where the interesting failures live. Use this while writing, Mailpit before
believing.

Sample values are deliberately awkward (a long name, a date with a timezone,
an em dash) rather than "Test User": placeholder data that is too tidy is how
layouts that break on real content get signed off.

Functions (PROJECT §6.2a):
- `main(argv)` — CLI entry. Called by: `python -m app.cli.email_preview`.
  Sample values live in `core.email_templates.sample_context`, shared with the
  admin preview page — one set of examples, not two that drift.
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from app.core.email_templates import LOCALES, _LETTERS, render, sample_context

DEFAULT_OUT = Path("/tmp/vimana-email-preview")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Vimana emails to HTML files")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--locale", action="append", choices=list(LOCALES))
    parser.add_argument("--kind", action="append", choices=list(_LETTERS))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    locales = args.locale or list(LOCALES)
    kinds = args.kind or list(_LETTERS)

    rows: list[str] = []
    for kind in kinds:
        for locale in locales:
            letter = render(kind, locale, **sample_context(kind))
            name = f"{kind}.{locale}.html"
            (out / name).write_text(letter.html, encoding="utf-8")
            (out / f"{kind}.{locale}.txt").write_text(letter.text, encoding="utf-8")
            rows.append(
                f'<li><code>{locale}</code> · <a href="{name}">{html.escape(letter.subject)}</a>'
                f' · <a href="{kind}.{locale}.txt">text</a></li>'
            )
            print(out / name)

    (out / "index.html").write_text(
        "<meta charset='utf-8'><title>Vimana · email preview</title>"
        "<body style='font-family:system-ui;padding:24px;line-height:1.7'>"
        f"<h1>Vimana · email preview</h1><ul>{''.join(rows)}</ul></body>",
        encoding="utf-8",
    )
    print(out / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
