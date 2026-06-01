#!/bin/bash
# Phase 7 weekly cron wrapper. Installed via `crontab`. Self-contained: cd's to
# the project, runs the refresh under system python3 (stdlib-only pipeline), and
# appends to a dated cron log. Safe to run by hand any time.
set -euo pipefail

PROJECT_DIR="$PROJECT_DIR"
cd "$PROJECT_DIR"

# Prefer venv python if present (harmless), else system python3.
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PY="$PROJECT_DIR/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

LOG_DIR="$PROJECT_DIR/data/research"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y-%m-%d_%H%M%S)"

echo "[$(date)] weekly_refresh starting with $PY" >> "$LOG_DIR/cron.log"
"$PY" refresh.py >> "$LOG_DIR/cron.log" 2>&1
echo "[$(date)] weekly_refresh finished (rc=$?)" >> "$LOG_DIR/cron.log"
