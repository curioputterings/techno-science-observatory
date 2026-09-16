#!/bin/bash
# Phase 7 weekly cron wrapper. Installed via `crontab`. Self-contained: cd's to
# the project, runs the refresh under system python3 (stdlib-only pipeline), and
# appends to a dated cron log. Safe to run by hand any time.
set -euo pipefail

# self-locate: PROJECT_DIR is the directory this script lives in (portable)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Interpreter selection. refresh.py is a stdlib-only pipeline (Gemini/OpenAlex via
# urllib), so it needs no venv — and the venv MUST NOT be used here: under the
# com.complexity.weekly-catchup LaunchAgent, launching the venv python fails at
# startup with `PermissionError: [Errno 1] Operation not permitted:
# .venv/pyvenv.cfg` (a TCC/disk-access restriction on that agent's context) — this
# silently dropped every weekly snapshot on 2026-07-20. A non-venv interpreter
# reads its site config outside ~/Desktop and sidesteps that entirely.
#
# Pin Homebrew python@3.14 (the project's documented "system Python" and the exact
# interpreter the venv was built on) so cron matches the historically-validated
# runtime. Fall back to any python3.14, then bare python3 (Apple's /usr/bin/python3
# is 3.9 — the pipeline imports fine there, but 3.14 is preferred).
#
# DON'T just pick the first executable candidate: pinning the Homebrew path alone
# reproduced the 07-20 outage in a new place on 2026-08-03 — that path resolves
# into the Python.app framework bundle, which carries its own TCC identity and so
# gets denied ~/Desktop under the LaunchAgent, dying with
# `can't open file 'refresh.py': [Errno 1] Operation not permitted` in <1s.
# TCC verdicts differ per interpreter and can change with an OS/Homebrew update,
# so probe instead of predict: each candidate must prove it can actually open
# refresh.py from PROJECT_DIR before we accept it.
PY=""
for cand in \
  /opt/homebrew/opt/python@3.14/bin/python3.14 \
  "$(command -v python3.14 2>/dev/null)" \
  "$PROJECT_DIR/.venv/bin/python3" \
  "$(command -v python3 2>/dev/null)" \
  /usr/bin/python3; do
  [ -n "$cand" ] && [ -x "$cand" ] || continue
  if "$cand" -c "open('refresh.py').close()" >/dev/null 2>&1; then PY="$cand"; break; fi
done

LOG_DIR_EARLY="$PROJECT_DIR/data/research"
if [ -z "$PY" ]; then
  mkdir -p "$LOG_DIR_EARLY"
  echo "[$(date)] weekly_refresh ABORT: no interpreter could read refresh.py \
(TCC/disk-access denial — grant Full Disk Access to the LaunchAgent's shell)" \
    >> "$LOG_DIR_EARLY/cron.log"
  exit 1
fi

LOG_DIR="$PROJECT_DIR/data/research"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y-%m-%d_%H%M%S)"

# Arguments are forwarded to refresh.py, so the catch-up guard can invoke the
# scoped repair path (--domains a,b,c) through this same TCC-safe wrapper rather
# than picking an interpreter itself.
echo "[$(date)] weekly_refresh starting with $PY ${*:-(full refresh)}" >> "$LOG_DIR/cron.log"
# `set -e` would abort before the finish line on a non-zero refresh, hiding the rc
# in cron.log (the only place a launchd-run failure is visible) — so capture it.
rc=0
"$PY" refresh.py "$@" >> "$LOG_DIR/cron.log" 2>&1 || rc=$?
echo "[$(date)] weekly_refresh finished (rc=$rc)" >> "$LOG_DIR/cron.log"
exit "$rc"
