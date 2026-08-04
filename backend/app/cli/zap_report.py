"""T_TEST.7 pt.1 — read a ZAP baseline report and decide whether it is a failure.

Usage (see `.zap/baseline.sh`):

    python -m app.cli.zap_report [--alert] < zap-report.json

The rule, in one place: **any High fails the run.** Mediums are counted and
printed but do not fail — the acceptance criterion is "0 High, ≤ 3 documented
Medium", and which Mediums are documented is a human judgement that belongs in
`.zap/rules.tsv`, next to the reason, not in an exit code here.

ZAP's own scale tops out at High; the roadmap says "High/Critical" because most
scanners have four levels. `riskcode` is the numeric field and it is what is
read, so a future ZAP that adds a level above 3 alerts too, without an edit.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RISK_NAMES = {0: "Informational", 1: "Low", 2: "Medium", 3: "High"}
HIGH = 3
MEDIUM = 2


@dataclass
class Summary:
    counts: dict[int, int] = field(default_factory=dict)
    high: list[str] = field(default_factory=list)
    medium: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.high)

    def count(self, risk: int) -> int:
        return self.counts.get(risk, 0)


def _risk_of(alert: dict) -> int:
    """`riskcode` arrives as a string in ZAP's JSON, and sometimes decorated.

    Anything unparseable is treated as **High**, not as 0. A report we cannot
    read is not evidence of safety, and the failure mode of guessing low here
    is a silent green run.
    """
    raw = alert.get("riskcode", alert.get("risk"))
    if isinstance(raw, int):
        return raw
    text = str(raw or "").strip()
    if text.isdigit():
        return int(text)
    for value, name in RISK_NAMES.items():
        if text.lower().startswith(name.lower()):
            return value
    logger.warning("unreadable riskcode %r — treating as High", raw)
    return HIGH


def _label(alert: dict) -> str:
    name = alert.get("alert") or alert.get("name") or "(unnamed alert)"
    instances = alert.get("instances") or []
    where = ""
    if instances:
        uri = instances[0].get("uri", "")
        extra = f" (+{len(instances) - 1} more)" if len(instances) > 1 else ""
        where = f" — {uri}{extra}"
    return f"{name}{where}"


def summarise(report: dict) -> Summary:
    """Flatten `site[].alerts[]` into counts plus the lines worth printing."""
    summary = Summary()
    for site in report.get("site", []) or []:
        for alert in site.get("alerts", []) or []:
            risk = _risk_of(alert)
            summary.counts[risk] = summary.counts.get(risk, 0) + 1
            if risk >= HIGH:
                summary.high.append(_label(alert))
            elif risk == MEDIUM:
                summary.medium.append(_label(alert))
    return summary


def _render(summary: Summary) -> str:
    lines = [
        "ZAP baseline: "
        + ", ".join(
            f"{RISK_NAMES.get(risk, f'risk {risk}')}: {summary.count(risk)}"
            for risk in sorted(RISK_NAMES, reverse=True)
        )
    ]
    for item in summary.high:
        lines.append(f"  HIGH    {item}")
    for item in summary.medium:
        lines.append(f"  medium  {item}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        help="report JSON; reads stdin when omitted",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="send the admin Telegram message when a High is present",
    )
    args = parser.parse_args(argv)

    raw = open(args.path, encoding="utf-8").read() if args.path else sys.stdin.read()
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"could not parse the ZAP report: {exc}", file=sys.stderr)
        return 2

    summary = summarise(report)
    print(_render(summary))

    if summary.high and args.alert:
        from app.tasks.notifications import notify_admins_zap_findings

        try:
            notify_admins_zap_findings.delay(summary.high, summary.count(MEDIUM))
        except Exception:
            # The scan result still stands. Losing the message must not turn a
            # real finding into a passing run.
            logger.exception("could not dispatch the ZAP alert")

    return 1 if summary.failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
