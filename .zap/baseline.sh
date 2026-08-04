#!/usr/bin/env bash
#
# T_TEST.7 pt.1 — OWASP ZAP baseline scan.
#
# Baseline is the passive scan: it crawls, reads what comes back and never
# sends an attack payload. That is why it is safe against production, and why
# the active scan (`zap-full-scan.py`) is not run from here at all — it submits
# forms and mutates parameters, which against prod means real rows in real
# deals.
#
#   ./.zap/baseline.sh https://vimana.dealvault.club
#   ZAP_ALERT=1 ./.zap/baseline.sh https://vimana.dealvault.club
#
# Reports land next to this script: `zap-report.html` to read, `zap-report.json`
# to judge. Both are gitignored — a scan result is a snapshot of one moment and
# ages badly in a repository.
#
# The pass/fail decision is NOT the ZAP exit code. `-I` keeps ZAP from failing
# the run on warnings, and `app/cli/zap_report.py` then applies our rule: any
# High is a failure, Mediums are counted and printed. One readable place beats
# a threshold split between a TSV, a CLI flag and a shell test.
set -euo pipefail

TARGET="${1:-${ZAP_TARGET:-}}"
if [[ -z "${TARGET}" ]]; then
  echo "usage: $0 <url>   (or set ZAP_TARGET)" >&2
  exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.dev.yml}"

# `stable`, not a pinned digest: unlike the relay and clamav — which run *under*
# us as services — ZAP is a tool invoked by hand against a URL. A stale scanner
# is worse than a moving one, because the whole value here is knowing about
# checks added since the last run.
IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"

echo "▸ ZAP baseline against ${TARGET}"

# `/zap/wrk` is where the image looks for `-c` and writes reports, so this
# directory is mounted as exactly that. The container runs as uid 1000; the
# reports are created there, which is why the mount is rw.
docker run --rm -t \
  -v "${HERE}:/zap/wrk:rw" \
  "${IMAGE}" \
  zap-baseline.py \
    -t "${TARGET}" \
    -c rules.tsv \
    -J zap-report.json \
    -r zap-report.html \
    -I \
  || echo "▸ ZAP exited non-zero — the report below is what decides."

if [[ ! -f "${HERE}/zap-report.json" ]]; then
  echo "no JSON report produced — scan did not complete" >&2
  exit 1
fi

# The judgement runs inside the backend container: it is the only place that
# has the Celery app, and dispatching the alert from anywhere else would mean a
# second way to send an admin message. `-T` because the report arrives on stdin.
ALERT_FLAG=()
if [[ "${ZAP_ALERT:-0}" == "1" ]]; then
  ALERT_FLAG=(--alert)
fi

${COMPOSE} exec -T backend python -m app.cli.zap_report "${ALERT_FLAG[@]}" \
  < "${HERE}/zap-report.json"
