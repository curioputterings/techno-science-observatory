#!/bin/bash
# One-time July review of the Techno-Science Capability Observatory.
# Refreshes all data, regenerates the static site, checks that the weekly cron
# snapshots have accumulated, and writes a change report vs the June 1 baseline.
# Runs LOCALLY (needs .env Gemini key + local data/jobs.db). Self-disables after
# it fires by removing its own cron line.
set -uo pipefail

# self-locate: PROJECT_DIR is the directory this script lives in (portable)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then PY="$PROJECT_DIR/.venv/bin/python"; else PY="$(command -v python3)"; fi
STAMP="$(date +%Y-%m-%d_%H%M%S)"
REPORT="$PROJECT_DIR/data/research/JULY_REVIEW_${STAMP}.md"
mkdir -p "$PROJECT_DIR/data/research"

{
  echo "# July review — Techno-Science Capability Observatory"
  echo "_generated $(date)_"
  echo

  echo "## 1. Repo sync"
  git pull --rebase 2>&1 | sed 's/^/    /'
  echo

  echo "## 2. Snapshot history BEFORE refresh (the weekly-cron check)"
  "$PY" - <<'PY' 2>&1 | sed 's/^/    /'
import sqlite3
from store import DB_PATH
c=sqlite3.connect(DB_PATH)
dates=[r[0] for r in c.execute("SELECT DISTINCT snapshot_date FROM cell_history ORDER BY snapshot_date")]
print(f"cell_history dates ({len(dates)}): {dates}")
if len(dates) < 2:
    print("WARNING: <2 snapshots — the weekly cron may not have been firing "
          "(Mac asleep on Mondays?). Trends need >=2 weeks.")
else:
    print(f"OK: {len(dates)} weekly snapshots accumulated since baseline.")
c.close()
PY
  echo

  echo "## 3. Capture June-baseline capability (from current DB before refresh)"
  "$PY" - <<'PY' 2>&1 | sed 's/^/    /'
import sqlite3, json
from store import DB_PATH
c=sqlite3.connect(DB_PATH)
rows=c.execute("SELECT country_name, AVG(0.4*(COALESCE(volume_ord,0)/5.0)"
  "+0.4*(MAX(COALESCE(skill_level,0)-1,0)/4.0)"
  "+0.2*MIN(MAX(COALESCE(frontier,0.0),0.0),1.0))*100 "
  "FROM cells WHERE source='gemini_research' GROUP BY country_iso").fetchall()
json.dump({r[0]: round(r[1],1) for r in rows}, open('/tmp/_june_cap.json','w'))
print("captured", len(rows), "country baselines")
c.close()
PY
  echo

  echo "## 4. Refresh all data (Gemini research + ambition + ATS)"
  echo "### 4a. Gemini revealed-capability + ambition + snapshot"
  "$PY" refresh.py 2>&1 | sed 's/^/    /'
  echo "### 4b. ATS verified scrape"
  "$PY" ats/probe.py 2>&1 | tail -3 | sed 's/^/    /'
  "$PY" ats/scrape.py 2>&1 | tail -3 | sed 's/^/    /'
  echo

  echo "## 5. Regenerate static site"
  "$PY" export_site.py 2>&1 | sed 's/^/    /'
  echo

  echo "## 6. What changed since June 1 (capability deltas)"
  "$PY" - <<'PY' 2>&1 | sed 's/^/    /'
import sqlite3, json, os
from store import DB_PATH
base=json.load(open('/tmp/_june_cap.json')) if os.path.exists('/tmp/_june_cap.json') else {}
c=sqlite3.connect(DB_PATH)
rows=c.execute("SELECT country_name, AVG(0.4*(COALESCE(volume_ord,0)/5.0)"
  "+0.4*(MAX(COALESCE(skill_level,0)-1,0)/4.0)"
  "+0.2*MIN(MAX(COALESCE(frontier,0.0),0.0),1.0))*100 "
  "FROM cells WHERE source='gemini_research' GROUP BY country_iso").fetchall()
now={r[0]: round(r[1],1) for r in rows}
deltas=sorted(((now[k]-base.get(k,now[k]), k) for k in now), reverse=True)
print("Biggest risers:")
for d,k in deltas[:8]:
    if abs(d)>=0.1: print(f"  +{d:5.1f}  {k}  ({base.get(k,'-')} -> {now[k]})")
print("Biggest fallers:")
for d,k in deltas[-8:]:
    if abs(d)>=0.1: print(f"  {d:6.1f}  {k}  ({base.get(k,'-')} -> {now[k]})")
ats=c.execute("SELECT COUNT(*) FROM cells WHERE source='ats'").fetchone()[0]
print(f"ATS verified cells now: {ats}")
c.close()
PY
  echo

  echo "## 7. Suggested next step"
  echo "    Review this report, then: git add -A && git commit -m 'July refresh' && git push"
  echo "    (pushing docs/ redeploys the live GitHub Pages site)"
} > "$REPORT" 2>&1

echo "July review written to $REPORT"
# macOS desktop notification
osascript -e "display notification \"July review complete — see data/research/\" with title \"Techno-Science Observatory\"" 2>/dev/null || true

# self-disable: remove this job from crontab so it only fires once
( crontab -l 2>/dev/null | grep -v "july_review.sh" ) | crontab - 2>/dev/null || true
