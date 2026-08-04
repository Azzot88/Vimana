"""T_TEST.7 pt.1 — the part of the ZAP pipeline that has a decision in it.

The scan itself is a container run by hand; there is nothing here to test about
it. What is worth a test is the judgement: which report fails the run, and what
happens to a report that cannot be read.
"""
from __future__ import annotations

import json

from app.cli.zap_report import MEDIUM, summarise


def _report(*alerts: dict) -> dict:
    return {"site": [{"@name": "https://example.test", "alerts": list(alerts)}]}


def _alert(risk, name="Something", uri="https://example.test/") -> dict:
    return {"alert": name, "riskcode": risk, "instances": [{"uri": uri}]}


def test_clean_report_passes():
    summary = summarise(_report())
    assert summary.high == []
    assert not summary.failed


def test_high_fails_and_is_named():
    summary = summarise(_report(_alert("3", "SQL Injection", "https://example.test/api")))
    assert summary.failed
    assert summary.high == ["SQL Injection — https://example.test/api"]


def test_medium_is_counted_but_does_not_fail():
    summary = summarise(_report(_alert("2", "Cookie without SameSite")))
    assert not summary.failed
    assert summary.count(MEDIUM) == 1
    assert summary.medium == ["Cookie without SameSite — https://example.test/"]


def test_riskcode_may_be_an_int_or_a_word():
    assert summarise(_report(_alert(3))).failed
    assert summarise(_report({"alert": "X", "risk": "High"})).failed
    assert not summarise(_report({"alert": "X", "risk": "Low"})).failed


def test_unreadable_risk_is_treated_as_high():
    """The one decision worth writing down.

    A report field we cannot parse is not evidence that nothing was found. The
    failure mode of the opposite default is a green run that means nothing, and
    it is silent.
    """
    summary = summarise(_report({"alert": "Weird", "riskcode": "banana"}))
    assert summary.failed


def test_many_instances_are_summarised_not_repeated():
    alert = {
        "alert": "Missing Header",
        "riskcode": "3",
        "instances": [{"uri": "https://example.test/a"}, {"uri": "https://example.test/b"}],
    }
    summary = summarise(_report(alert))
    assert summary.high == ["Missing Header — https://example.test/a (+1 more)"]


def test_main_exit_code_follows_the_high_count(tmp_path, capsys):
    from app.cli.zap_report import main

    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps(_report(_alert("1", "Low thing"))), encoding="utf-8")
    assert main([str(clean)]) == 0

    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps(_report(_alert("3", "High thing"))), encoding="utf-8")
    assert main([str(dirty)]) == 1

    printed = capsys.readouterr().out
    assert "High thing" in printed


def test_broken_json_exits_two_rather_than_passing(tmp_path):
    from app.cli.zap_report import main

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert main([str(broken)]) == 2


def test_alert_is_dispatched_only_on_high(tmp_path, monkeypatch):
    from app.cli.zap_report import main
    from app.tasks import notifications

    sent: list[tuple] = []

    class _Fake:
        @staticmethod
        def delay(*args):
            sent.append(args)

    monkeypatch.setattr(notifications, "notify_admins_zap_findings", _Fake)

    low = tmp_path / "low.json"
    low.write_text(json.dumps(_report(_alert("2", "Medium thing"))), encoding="utf-8")
    main([str(low), "--alert"])
    assert sent == []

    high = tmp_path / "high.json"
    high.write_text(json.dumps(_report(_alert("3", "High thing"))), encoding="utf-8")
    main([str(high), "--alert"])
    assert len(sent) == 1
    assert sent[0][0] == ["High thing — https://example.test/"]
