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
for cand in \
  /opt/homebrew/opt/python@3.14/bin/python3.14 \
  "$(command -v python3.14 2>/dev/null)" \
  "$(command -v python3 2>/dev/null)"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then PY="$cand"; break; fi
done

LOG_DIR="$PROJECT_DIR/data/research"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y-%m-%d_%H%M%S)"

echo "[$(date)] weekly_refresh starting with $PY" >> "$LOG_DIR/cron.log"
"$PY" refresh.py >> "$LOG_DIR/cron.log" 2>&1
echo "[$(date)] weekly_refresh finished (rc=$?)" >> "$LOG_DIR/cron.log"
