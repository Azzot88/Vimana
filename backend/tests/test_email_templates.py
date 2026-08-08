"""T_UX.9 — six locales, one layout, and the guarantees that keep them together."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli.email_preview import sample_context
from app.core.email_templates import (
    DEFAULT_LOCALE,
    LOCALES,
    _LETTERS,
    _LOCALES_DIR,
    render,
)

ALL_KINDS = sorted(_LETTERS)


def _catalogue(locale: str) -> dict:
    return json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", LOCALES)
def test_every_locale_file_exists(locale):
    assert (_LOCALES_DIR / f"{locale}.json").exists()


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != DEFAULT_LOCALE])
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_no_locale_is_missing_a_letter(locale, kind):
    """The guard against «we'll translate it later» reaching production."""
    assert kind in _catalogue(locale), f"{locale}.json has no `{kind}`"


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != DEFAULT_LOCALE])
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_no_letter_is_missing_a_key(locale, kind):
    reference = set(_catalogue(DEFAULT_LOCALE)[kind])
    translated = set(_catalogue(locale)[kind])
    assert not reference - translated, (
        f"{locale}.json `{kind}` is missing: {sorted(reference - translated)}"
    )


def test_deal_status_labels_cover_every_status():
    """A status without a label renders as its raw enum value in someone's inbox."""
    reference = set(_catalogue(DEFAULT_LOCALE)["deal_status"]["labels"])
    for locale in LOCALES:
        labels = set(_catalogue(locale)["deal_status"]["labels"])
        assert reference == labels, f"{locale}: {reference ^ labels}"


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_letter_renders_in_every_locale(locale, kind):
    letter = render(kind, locale, **sample_context(kind))
    assert letter.subject.strip()
    assert letter.text.strip()
    assert "<table" in letter.html, "email HTML must be table-based"
    assert "{{" not in letter.html, "an unrendered placeholder reached the letter"
    assert "{{" not in letter.text


def test_unknown_locale_falls_back_to_english():
    """A letter in the wrong language is a flaw; one that fails to render is an outage."""
    fallback = render("verification_code", "kl", code="000000")
    english = render("verification_code", "en", code="000000")
    assert fallback.subject == english.subject


def test_none_locale_falls_back_to_english():
    assert render("waitlist_confirmation", None).subject == render(
        "waitlist_confirmation", "en"
    ).subject


def test_regional_tag_is_narrowed_to_language():
    assert render("waitlist_confirmation", "ru-RU").subject == render(
        "waitlist_confirmation", "ru"
    ).subject


def test_locales_actually_differ():
    """Guards the guard: identical output would make every test above vacuous."""
    subjects = {render("verification_code", loc, code="1").subject for loc in LOCALES}
    assert len(subjects) == len(LOCALES)


def test_code_reaches_both_parts():
    letter = render("verification_code", "ru", code="418305")
    assert "418305" in letter.html
    assert "418305" in letter.text


def test_text_part_carries_no_markup():
    """The text part is built from the catalogue, not stripped out of the HTML."""
    letter = render("archive_window_opened", "fr", deadline="2026-11-06")
    assert "<" not in letter.text
    assert "2026-11-06" in letter.text


def test_deal_status_heading_is_the_localised_label():
    ru = render("deal_status", "ru", status="in_transit")
    assert "Груз в пути" in ru.subject
    es = render("deal_status", "es", status="in_transit")
    assert "camino" in es.subject


def test_unknown_status_degrades_to_its_own_name():
    letter = render("deal_status", "en", status="teleported")
    assert "teleported" in letter.subject


def test_facts_skip_empty_values():
    """An empty row would render as a label with nothing under it."""
    letter = render("waitlist_admin", "en", email="a@b.test", name="", source="landing")
    assert "a@b.test" in letter.html
    assert ">name<" not in letter.html


def test_preheader_is_hidden_but_present():
    letter = render("waitlist_confirmation", "en")
    assert "display:none" in letter.html


def test_html_escapes_hostile_values():
    """Values come from user input — a name is not markup."""
    letter = render("waitlist_admin", "en", email="x@y.test", name="<script>alert(1)</script>")
    assert "<script>" not in letter.html
    assert "&lt;script&gt;" in letter.html


def test_preview_writes_files(tmp_path):
    from app.cli.email_preview import main

    assert main(["--out", str(tmp_path), "--locale", "ru", "--kind", "verification_code"]) == 0
    assert (tmp_path / "verification_code.ru.html").exists()
    assert (tmp_path / "verification_code.ru.txt").exists()
    assert (tmp_path / "index.html").exists()


def test_sample_context_covers_every_kind():
    """Otherwise the preview command breaks the moment a letter is added."""
    for kind in ALL_KINDS:
        assert isinstance(sample_context(kind), dict)


def test_send_email_builds_multipart(monkeypatch):
    """HTML present → two parts, text first: clients render the last one they can."""
    import smtplib

    from app.core.config import settings

    sent = {}

    class _Fake:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def sendmail(self, sender, to, raw):
            sent["raw"] = raw

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: _Fake())
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.example.test")
    monkeypatch.setattr(settings, "SMTP_USER", "vimana@example.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "SMTP_PORT", 465)

    from email import message_from_string

    from app.core.email import send_email

    assert send_email("who@example.test", "subj", "plain body", "<p>rich</p>") is True
    msg = message_from_string(sent["raw"])
    assert msg.get_content_type() == "multipart/alternative"
    parts = [p.get_content_type() for p in msg.walk() if not p.is_multipart()]
    assert parts == ["text/plain", "text/html"], (
        "text must come first — a client picks the last part it can render"
    )


def test_send_email_stays_plain_without_html(monkeypatch):
    import smtplib

    from app.core.config import settings

    sent = {}

    class _Fake:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def sendmail(self, sender, to, raw):
            sent["raw"] = raw

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: _Fake())
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.example.test")
    monkeypatch.setattr(settings, "SMTP_USER", "vimana@example.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "SMTP_PORT", 465)

    from email import message_from_string

    from app.core.email import send_email

    send_email("who@example.test", "subj", "plain only")
    assert message_from_string(sent["raw"]).get_content_type() == "text/plain"


def test_layout_has_no_external_requests():
    """A remote image is a read receipt, and most clients block it anyway."""
    layout = (Path(_LOCALES_DIR).parent / "layout.html").read_text(encoding="utf-8")
    assert "http://" not in layout
    assert "https://" not in layout
