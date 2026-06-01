#!/usr/bin/env python3
"""
Malaysia advanced-technoscience job-posting scraper — preliminary / starter.

Design notes
------------
Two collection tiers, both on the OPEN side of the defense line:

  A. ATS adapters (Greenhouse / Lever / Ashby): public JSON-by-design.
     This is the scalable path — most MNC design houses and deep-tech
     startups route reqs through one of these. Detect once, pull forever.

  B. Custom career-page parsers (e.g. ViTrox): server-rendered HTML, no auth,
     no bot defense. One parser per employer, but the employer set is small.

Deliberately EXCLUDED: JobStreet/SEEK, LinkedIn, Hiredly, Indeed-MY.
These are defended and ToS-encumbered. Use them BY EYE to populate the
employer registry below — never scrape them.

Note on Workday (the MNC fabs: Intel, Micron, Infineon, Lam, KLA...):
their listings live at a `cxs` endpoint that requires a POST with a JSON
body (location/keyword facets), not a GET. Add a WorkdayAdapter when you
need that tier; pattern is:
  POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  body: {"appliedFacets": {...}, "limit": 20, "offset": 0, "searchText": ""}

Privacy / ethics: job POSTINGS are not personal data — fine to collect.
Applicant data (which ViTrox's PDPA notice covers) is out of scope and
must never be touched. Respect robots.txt, rate-limit, identify your agent.
"""

from __future__ import annotations
import csv
import datetime as dt
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Callable

import requests
from bs4 import BeautifulSoup

UA = "technoscience-foresight-research/0.1 (contact: you@example.org)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})
POLITE_DELAY_S = 2.0  # be a good citizen

# --- skill / convergence taxonomy -------------------------------------------
# The frontier-formation signal concentrates in cross-domain ("convergence")
# reqs. Flagging these is the analytically interesting extraction.
SKILL_PATTERNS = {
    "ai_ml":        r"\b(machine learning|deep learning|\bAI\b|neural|LLM|computer vision|big data)\b",
    "rtl_design":   r"\b(RTL|verilog|systemverilog|VHDL|design verification|physical design|ASIC|FPGA)\b",
    "photonics":    r"\b(photonic|silicon photonics|optical|laser)\b",
    "advanced_pkg": r"\b(advanced packaging|chiplet|wafer|2\.5D|3D IC|fan-?out|TSV)\b",
    "synbio":       r"\b(synthetic biology|bioprocess|CRISPR|fermentation|bioinformatics)\b",
    "quantum":      r"\b(quantum|qubit|cryogenic)\b",
    "nuclear":      r"\b(nuclear|radiation|reactor|isotope)\b",
    "cleared_dual_use": r"\b(security clearance|ITAR|export control|US persons)\b",
}


def tag_skills(text: str) -> list[str]:
    t = text.lower()
    return [k for k, pat in SKILL_PATTERNS.items() if re.search(pat, t, re.I)]


# --- common schema ----------------------------------------------------------
@dataclass
class Posting:
    employer: str
    sector: str
    source_type: str          # "greenhouse" | "lever" | "ashby" | "custom"
    job_id: str
    title: str
    locations: list[str]
    career_level: str = ""
    qualification: str = ""
    years_exp: str = ""
    job_type: str = ""
    skill_flags: list[str] = field(default_factory=list)
    url: str = ""
    snapshot_date: str = dt.date.today().isoformat()


# --- employer registry ------------------------------------------------------
# Populate by eye from InvestPenang / MIDA / recruitment-day rosters.
# 'kind' selects the adapter; 'ref' is the ATS token/handle or career URL.
EMPLOYERS = [
    {"name": "ViTrox",      "sector": "ate_machine_vision", "kind": "vitrox",
     "ref": "https://jobs.vitrox.com/career-explore/index.php",
     "categories": ["mfg", "research-development", "business-development", "share-service"]},
    # Examples of the scalable ATS tier — confirm tokens before running:
    # {"name": "SomeFablessCo", "sector": "ic_design", "kind": "greenhouse", "ref": "<board_token>"},
    # {"name": "SomeDeepTech",  "sector": "biotech",    "kind": "lever",      "ref": "<company_handle>"},
    # {"name": "SomeStartup",   "sector": "quantum",    "kind": "ashby",      "ref": "<org_slug>"},
]


# --- ATS adapters (clean JSON) ----------------------------------------------
def fetch_greenhouse(emp) -> list[Posting]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{emp['ref']}/jobs?content=true"
    data = SESSION.get(url, timeout=30).json()
    out = []
    for j in data.get("jobs", []):
        text = BeautifulSoup(j.get("content", ""), "html.parser").get_text(" ")
        out.append(Posting(
            employer=emp["name"], sector=emp["sector"], source_type="greenhouse",
            job_id=str(j["id"]), title=j["title"],
            locations=[j.get("location", {}).get("name", "")],
            skill_flags=tag_skills(j["title"] + " " + text), url=j["absolute_url"],
        ))
    return out


def fetch_lever(emp) -> list[Posting]:
    url = f"https://api.lever.co/v0/postings/{emp['ref']}?mode=json"
    out = []
    for j in SESSION.get(url, timeout=30).json():
        text = j.get("descriptionPlain", "")
        out.append(Posting(
            employer=emp["name"], sector=emp["sector"], source_type="lever",
            job_id=j["id"], title=j["text"],
            locations=[j.get("categories", {}).get("location", "")],
            skill_flags=tag_skills(j["text"] + " " + text), url=j["hostedUrl"],
        ))
    return out


def fetch_ashby(emp) -> list[Posting]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{emp['ref']}?includeCompensation=true"
    out = []
    for j in SESSION.get(url, timeout=30).json().get("jobs", []):
        out.append(Posting(
            employer=emp["name"], sector=emp["sector"], source_type="ashby",
            job_id=j["id"], title=j["title"], locations=[j.get("location", "")],
            job_type=j.get("employmentType", ""),
            skill_flags=tag_skills(j["title"] + " " + j.get("descriptionPlain", "")),
            url=j.get("jobUrl", ""),
        ))
    return out


# --- custom parser: ViTrox --------------------------------------------------
# Reflects the live DOM observed 2026-05: each posting is a card whose detail
# carries title (h4/h5), location lines, a spec table (level/qual/exp/type),
# and a stable integer id via ?job=<id>. Selectors may need light tuning;
# verify against the page source before a production run.
def fetch_vitrox(emp) -> list[Posting]:
    out, seen = [], set()
    for cat in emp.get("categories", ["mfg"]):
        url = f"{emp['ref']}?cat={cat}"
        soup = BeautifulSoup(SESSION.get(url, timeout=30).text, "html.parser")
        for share in soup.select('a[href*="?job="]'):
            m = re.search(r"job=(\d+)", share.get("href", ""))
            if not m:
                continue
            jid = m.group(1)
            if jid in seen:
                continue
            seen.add(jid)
            block = share.find_parent(["div", "section"]) or share
            title_el = block.find(["h4", "h5", "h3"])
            title = title_el.get_text(strip=True) if title_el else ""
            # spec table: Career Level | Qualification | Years | Job Type
            level = qual = years = jtype = ""
            tbl = block.find("table")
            if tbl:
                rows = [r.get_text(" ", strip=True) for r in tbl.find_all("tr")]
                if len(rows) >= 2:
                    cells = [c.get_text(strip=True) for c in tbl.find_all("td")]
                    if len(cells) >= 4:
                        level, qual, years, jtype = cells[:4]
            text = block.get_text(" ", strip=True)
            locs = re.findall(r"(Batu Kawan, Penang|Penang|Melaka|Negeri Sembilan|"
                              r"Bangkok, Thailand|Austin, Texas|[A-Z][a-z]+, India)", text)
            out.append(Posting(
                employer=emp["name"], sector=emp["sector"], source_type="custom",
                job_id=jid, title=title, locations=sorted(set(locs)) or [""],
                career_level=level, qualification=qual, years_exp=years, job_type=jtype,
                skill_flags=tag_skills(text),
                url=f"{emp['ref']}?cat={cat}&job={jid}",
            ))
        time.sleep(POLITE_DELAY_S)
    return out


ADAPTERS: dict[str, Callable] = {
    "greenhouse": fetch_greenhouse, "lever": fetch_lever,
    "ashby": fetch_ashby, "vitrox": fetch_vitrox,
}


def run() -> list[Posting]:
    rows: list[Posting] = []
    for emp in EMPLOYERS:
        adapter = ADAPTERS.get(emp["kind"])
        if not adapter:
            print(f"[skip] no adapter for {emp['name']} ({emp['kind']})")
            continue
        try:
            got = adapter(emp)
            rows.extend(got)
            print(f"[ok] {emp['name']}: {len(got)} postings")
        except Exception as e:  # noqa: BLE001
            print(f"[err] {emp['name']}: {e}")
        time.sleep(POLITE_DELAY_S)
    return rows


def write_csv(rows: list[Posting], path: str = "my_technoscience_snapshot.csv") -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            d = asdict(r)
            d["locations"] = "; ".join(d["locations"])
            d["skill_flags"] = "; ".join(d["skill_flags"])
            w.writerow(d)
    print(f"wrote {len(rows)} rows -> {path}")


# Longitudinal panel: run on a weekly cron, append snapshots, then diff on
# (employer, job_id) across snapshot_date to derive openings/closings (flow),
# tenure-on-board, and skill-flag drift over time.
if __name__ == "__main__":
    write_csv(run())
