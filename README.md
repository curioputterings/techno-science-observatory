# Techno-Science Capability Observatory

Global, country-by-country view of leading-edge industries: **job quantity +
skill/complexity level** per country per domain, compared across countries, with
OEC-style complexity analysis to follow. See `ARCHITECTURE.md` / `ROADMAP.md`.

**🌐 Live site:** https://curioputterings.github.io/techno-science-observatory/

If you find this useful, you can support the work:
**☕ [Buy me a coffee](https://buymeacoffee.com/curioputterings)**

## Status — all 7 phases built & verified
Working end to end in `data/jobs.db`:
- **270 capability cells + 270 ambition cells** (9 domains × 30 countries, incl.
  CN & IN) from Gemini grounded research (estimates).
- **65 verified ATS cells** (21 countries, all 9 domains) from **3,722 real open
  postings** across 14 live Greenhouse/Lever/Ashby boards — `precision=counted`.
- 9-tab dashboard boots clean (HTTP 200): capability matrix, quantity×skill,
  country profile, rankings, OEC complexity, adjacent-possible, ambition-gap,
  trends, **verified (ATS)**. Estimated vs verified sources kept strictly separate.
- Weekly cron (Mondays 09:00) records longitudinal snapshots.

Rankings face-valid (US > China > DE/JP/KR…; semiconductors led by US/TW/KR/NL).

## Pipeline
```
run_research.py ──(Gemini API)──▶ data/research/<domain>.json ──▶ data/jobs.db
                                                                      │
                                                        dashboard/app.py (Streamlit)
```
- `taxonomy.py` — the 9 domains, 5 skill tiers, volume bands (shared spine).
- `gemini_client.py` — stdlib Gemini REST client (reads `.env`).
- `research.py` — prompts, schema, 30 target countries, ingest → SQLite.
- `run_research.py` — generate all 9 domains and load the DB.
- `store.py` — SQLite `cells` table (country × domain × source).
- `analysis/complexity.py` — OEC engine: RCA, PCI, basket complexity, proximity,
  density (adjacent possible). `verify_complexity.py` prints a text report.
- `ambition.py` — Gemini policy research → stated national intent (`ambition` table).
- `analysis/gap.py` — ambition vs revealed capability (the build-out gap).
- `analysis/gap.py` — ambition vs revealed capability (the build-out gap).
- `refresh.py` + `weekly_refresh.sh` — weekly snapshot cron (Phase 7).
- `ats/probe.py` — verify which candidate ATS boards are live → `ats_registry.json`.
- `ats/classify.py` — map a posting → domain + complexity tier + country.
- `ats/scrape.py` — fetch live boards → classify → aggregate → `source='ats'`,
  `precision=counted` cells (verified depth layer, L0a).
- `ats/footprint.py` — cross-border MNC division-of-labour map: classifies each
  posting by business **function** (research / engineering / manufacturing-test /
  field / commercial / corporate) → `employer × country × function` table.
- `dashboard/app.py` — comparison dashboard (9 tabs incl. OEC, adjacent possible,
  ambition vs reality, trends, verified ATS).
- `my_technoscience_scraper.py` — original SEA-focused ATS scraper (reference).

## Run it

```bash
cd ~/Desktop/tech_sci_jobs

# 1. generate the global table with Gemini (uses .env key; ~9 API calls each)
python3 run_research.py                 # revealed capability — all 9 domains
python3 ambition.py                     # stated national ambition — all 9 domains
#   one domain to test first:  python3 run_research.py quantum
#   check: cat data/research/run.log   and   ls data/research/

# verified depth — real ATS postings (no key, ~$0):
python3 ats/probe.py                    # find live boards -> data/ats_registry.json
python3 ats/scrape.py                   # scrape -> classify -> counted cells
python3 ats/footprint.py                # cross-border MNC division-of-labour map

# 2. dashboard  (a .venv is already set up with deps)
.venv/bin/streamlit run dashboard/app.py
#   then open http://localhost:8501

# quick text summaries without the UI:
python3 verify_panel.py                 # capability ranking + domain leaders
.venv/bin/python verify_complexity.py   # OEC: PCI, basket complexity, adjacency
```

`run_research.py` writes each domain's cited JSON to `data/research/` and logs to
`data/research/run.log`. Re-running is idempotent (upsert by country+domain+source).

## Weekly automation (Phase 7)
`weekly_refresh.sh` re-runs the Gemini research + ambition passes and appends a
dated snapshot to `cell_history`, so the dashboard's **Trends** tab fills in over
time. Intended cadence: every **Monday 09:00**.

**Installed and verified:** the crontab entry is active —
```
0 9 * * 1 $PROJECT_DIR/weekly_refresh.sh
```
To view / re-install / remove:
```bash
crontab -l        # view (should show the line above)
# re-install (idempotent):
( crontab -l 2>/dev/null | grep -v 'tech_sci_jobs weekly refresh'; \
  echo '0 9 * * 1 $PROJECT_DIR/weekly_refresh.sh  # tech_sci_jobs weekly refresh' ) | crontab -
crontab -e        # remove: delete the tech_sci_jobs line
```

Manual / test commands:
```bash
python3 refresh.py --snapshot-only      # snapshot current cells, no API cost
python3 refresh.py --trends             # text trend summary
python3 refresh.py                      # full refresh now (~18 Gemini calls)
./weekly_refresh.sh                      # exactly what cron runs
```

**macOS notes:** cron fires only while the Mac is awake (a missed Monday is
skipped, not caught up); if the job can't read files, grant **Full Disk Access**
to `/usr/sbin/cron` in System Settings → Privacy & Security. If you'd prefer a
scheduler that survives reboots and catches up missed runs, switch to a
**launchd** agent (`~/Library/LaunchAgents/`, `StartCalendarInterval` Weekday=1
Hour=9) — ask and I'll regenerate the `.plist`.

## Configuration
`.env` (gitignored) holds:
```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

## Notes / honesty
- Volumes are **estimated bands**, not exact counts — a capability *signal*. The
  precision ratchet (band → partial_count → counted) upgrades cells as the ATS
  layer and official sources are added.
- **Two complementary rankings, by design:** *capability* (raw quantity × skill,
  US-led) answers "who does the most/deepest work"; *basket complexity* (PCI-
  weighted, TW/KR/NL-led) answers "whose mix is concentrated in the rarest, hardest
  domains." Classic eigenvector ECI is intentionally not used as a headline — it's
  unstable at 9 domains and penalises all-round leaders.
- The Gemini **MCP** server is pinned to a retired model (`gemini-3-pro-preview`,
  404) and is unusable; this build calls the Gemini **REST API** directly instead.
- Each cell stores `confidence` and `evidence` (auditable anchors).
