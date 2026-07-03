#!/usr/bin/env python3
"""
divergence_report.py — estimate-vs-counts divergence over the capability panel.

Why this exists (CAVEATS_AND_NEXT_STEPS.md, Tier-1 caveat 1, "if you only do
three things" #1): the headline capability signal is a Gemini *estimate*, not a
measurement. Where a counted signal (publications, patents, ATS) covers the same
cell, we should flag/down-weight cells where the estimate disagrees with the
counts — and, per CLAUDE.md, "where they diverge, that gap is itself the finding
(e.g. China out-publishes the US in AI research but the US still out-patents it)."

This is a READ-ONLY report. It never writes to jobs.db and needs no API keys.

What it compares
----------------
All four sources live in one `cells` table, distinguished by `source`, and every
source stores a `volume_ord` (0-5 activity band). `volume_ord` is the ONE
dimension commensurable across all four (skill_level/frontier exist only for the
estimate and ATS), so divergence is computed on the band:

    estimate  = source='gemini_research'   (the LLM revealed-capability band)
    counted   = source in {publications, patents, ats}

    divergence(counted) = counted.volume_ord - estimate.volume_ord
        > 0  → counts run HOTTER than the model said  (model under-rates)
        < 0  → counts run COLDER than the model said  (model over-rates)

publications + patents are the two dense (30x30) counted layers; ATS is sparse
and US-heavy (~131 cells) so it is reported but kept separate from the headline
"measured band" (= mean of publications & patents ords).

Outputs (stable names, overwritten each run — diff-friendly):
    data/research/_divergence.csv          per-cell bands + divergences
    data/research/_divergence_report.md    narrative summary

Run from the project root:
    python3 divergence_report.py
    PYTHONPATH=. python3 divergence_report.py     # if taxonomy import needs it
"""
from __future__ import annotations

import csv
import datetime as dt
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# DB path + domain labels via the project's own modules, with graceful fallback.
try:
    from store import DB_PATH  # type: ignore
except Exception:
    DB_PATH = ROOT / "data" / "jobs.db"
try:
    import taxonomy  # type: ignore
    DOMAIN_LABEL = dict(getattr(taxonomy, "DOMAIN_LABELS", {}))
except Exception:
    DOMAIN_LABEL = {}

OUT_DIR = ROOT / "data" / "research"
ESTIMATE = "gemini_research"
COUNTED = ["publications", "patents", "ats"]
DENSE_COUNTED = ["publications", "patents"]  # the "measured band"

# Flag thresholds (in bands). A 2-band gap is a material disagreement.
FLAG = 2


def label(domain: str) -> str:
    return DOMAIN_LABEL.get(domain, domain)


def load_cells(conn):
    """Return {(iso,domain): {source: {ord, raw, name, as_of}}} and per-source meta."""
    cur = conn.execute(
        "SELECT country_iso, country_name, domain, source, volume_ord, "
        "volume_estimate, as_of FROM cells"
    )
    grid: dict[tuple[str, str], dict] = {}
    src_asof: dict[str, set] = {}
    names: dict[str, str] = {}
    for iso, name, domain, source, vord, vest, as_of in cur:
        names.setdefault(iso, name)
        grid.setdefault((iso, domain), {})[source] = {
            "ord": vord, "raw": vest, "as_of": as_of,
        }
        src_asof.setdefault(source, set()).add(as_of)
    return grid, src_asof, names


def build_rows(grid):
    """One record per (iso,domain) that has an estimate. Divergences vs each source."""
    rows = []
    for (iso, domain), by_src in grid.items():
        est = by_src.get(ESTIMATE)
        if not est or est["ord"] is None:
            continue
        e = est["ord"]
        rec = {
            "country_iso": iso, "domain": domain, "domain_label": label(domain),
            "est_ord": e,
        }
        counted_ords = []
        for s in COUNTED:
            c = by_src.get(s)
            o = c["ord"] if c else None
            rec[f"{s}_ord"] = o
            rec[f"{s}_raw"] = (c["raw"] if c else "") or ""
            rec[f"{s}_div"] = (o - e) if o is not None else None
            if s in DENSE_COUNTED and o is not None:
                counted_ords.append(o)
        # "measured band" = mean of the dense counted layers present (a central
        # tendency, used for systematic-bias aggregates).
        rec["measured_band"] = round(statistics.mean(counted_ords), 2) if counted_ords else None
        rec["measured_div"] = round(rec["measured_band"] - e, 2) if counted_ords else None
        # Directional gaps use MAX/MIN, not the mean, so a domain that shows up in
        # only one channel (e.g. semiconductors are patent-led, not published)
        # isn't spuriously flagged. A cell is over-rated only if the estimate
        # exceeds *every* counted signal; under-rated only if *both* exceed it.
        if counted_ords:
            rec["over_gap"] = e - max(counted_ords)     # >0: no count supports the estimate
            rec["under_gap"] = min(counted_ords) - e    # >0: both counts beat the estimate
        else:
            rec["over_gap"] = rec["under_gap"] = None
        rows.append(rec)
    return rows


def cname(names, iso):
    return names.get(iso, iso)


def fmt_div(v):
    if v is None:
        return "  · "
    return f"{v:+.1f}" if isinstance(v, float) else f"{v:+d}"


def write_csv(rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["country_iso", "domain", "domain_label", "est_ord",
            "publications_ord", "patents_ord", "ats_ord",
            "measured_band", "measured_div", "over_gap", "under_gap",
            "publications_div", "patents_div", "ats_div",
            "publications_raw", "patents_raw", "ats_raw"]
    path = OUT_DIR / "_divergence.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return path


def section_gap(rows, gapkey, names, n=12):
    """Top cells by over_gap/under_gap (both are 'severity' — larger = worse)."""
    have = [r for r in rows if r.get(gapkey) is not None and r[gapkey] > 0]
    have.sort(key=lambda r: r[gapkey], reverse=True)
    out = []
    for r in have[:n]:
        pub, pat = r.get("publications_ord"), r.get("patents_ord")
        out.append(
            f"| {cname(names, r['country_iso'])} | {r['domain_label']} | "
            f"{r['est_ord']} | {pub if pub is not None else '·'} | "
            f"{pat if pat is not None else '·'} | **{fmt_div(r[gapkey])}** |"
        )
    return out, len(have)


def group_bias(rows, groupkey, names, min_n=3):
    """Mean signed measured divergence per country or per domain."""
    buckets: dict[str, list] = {}
    disp: dict[str, str] = {}
    for r in rows:
        if r.get("measured_div") is None:
            continue
        g = r[groupkey]
        buckets.setdefault(g, []).append(r["measured_div"])
        disp[g] = cname(names, g) if groupkey == "country_iso" else r["domain_label"]
    stats = []
    for g, vals in buckets.items():
        if len(vals) < min_n:
            continue
        stats.append((disp[g], round(statistics.mean(vals), 2), len(vals)))
    stats.sort(key=lambda t: t[1])
    return stats


def pub_vs_pat(rows, names, n=10):
    """The 'gap is the finding' split: publications band vs patents band."""
    have = [r for r in rows
            if r.get("publications_ord") is not None and r.get("patents_ord") is not None]
    for r in have:
        r["_pp"] = r["publications_ord"] - r["patents_ord"]
    research_lean = sorted(have, key=lambda r: r["_pp"], reverse=True)[:n]
    patent_lean = sorted(have, key=lambda r: r["_pp"])[:n]
    return research_lean, patent_lean


def md_table(header, rows):
    line = "| " + " | ".join(header) + " |"
    sep = "| " + " | ".join("---" for _ in header) + " |"
    return "\n".join([line, sep, *rows])


def main():
    if not Path(DB_PATH).exists():
        print(f"ERROR: {DB_PATH} not found (jobs.db is gitignored; run a refresh first).")
        return 1
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    grid, src_asof, names = load_cells(conn)
    rows = build_rows(grid)
    conn.close()

    if not rows:
        print("No gemini_research cells found — nothing to compare.")
        return 1

    today = dt.date.today().isoformat()

    # coverage
    def cov(s):
        return sum(1 for r in rows if r.get(f"{s}_ord") is not None)
    n_est = len(rows)
    flagged = [r for r in rows
               if (r.get("over_gap") is not None and r["over_gap"] >= FLAG)
               or (r.get("under_gap") is not None and r["under_gap"] >= FLAG)]

    # --- console summary ---
    print(f"estimate cells (gemini_research): {n_est}")
    for s in COUNTED:
        asof = ", ".join(sorted(a for a in src_asof.get(s, []) if a))
        print(f"  {s:<13} covers {cov(s):>3}/{n_est}   as_of {asof}")
    print(f"cells with a measured band: {sum(1 for r in rows if r['measured_div'] is not None)}")
    print(f"cells flagged (over_gap or under_gap >= {FLAG}): {len(flagged)}")

    csv_path = write_csv(rows)

    # --- build markdown ---
    over, n_over = section_gap(rows, "over_gap", names)     # est exceeds every count
    under, n_under = section_gap(rows, "under_gap", names)  # both counts exceed est
    ctry_bias = group_bias(rows, "country_iso", names)
    dom_bias = group_bias(rows, "domain", names)
    research_lean, patent_lean = pub_vs_pat(rows, names)

    est_asof = ", ".join(sorted(a for a in src_asof.get(ESTIMATE, []) if a))
    lines = []
    lines.append("# Estimate-vs-counts divergence report")
    lines.append(f"_generated {today} · read-only over `data/jobs.db`_\n")
    lines.append(
        "Compares the Gemini revealed-capability **estimate** against the "
        "**counted** signals (publications, patents, ATS) on the one dimension "
        "they share — the 0-5 `volume_ord` activity band. `measured band` = mean "
        "of the publications & patents bands; `measured div` = measured − estimate "
        "(**+** = counts run hotter than the model said → likely **over-cautious** "
        "estimate; **−** = counts run colder → likely **over-rated** estimate).\n")

    lines.append("## Coverage & vintages")
    cov_rows = [f"| {ESTIMATE} (estimate) | {n_est} | {est_asof} |"]
    for s in COUNTED:
        asof = ", ".join(sorted(a for a in src_asof.get(s, []) if a))
        cov_rows.append(f"| {s} | {cov(s)} | {asof} |")
    lines.append(md_table(["source", "cells vs estimate", "as_of"], cov_rows))
    lines.append(f"\n**{len(flagged)}** cells are flagged: the estimate exceeds "
                 f"*every* counted signal (`over_gap`≥{FLAG}) — {n_over} cells with "
                 f"any positive over_gap — or *both* dense counts exceed it "
                 f"(`under_gap`≥{FLAG}) — {n_under} with any positive under_gap.\n")

    lines.append("## Most over-rated cells (estimate exceeds *every* count)")
    lines.append("_`over_gap` = estimate band − max(publications, patents). The model "
                 "claims activity no counted signal supports — the least-trustworthy "
                 "high scores. (Semiconductor cells are correctly absent: patents "
                 "back them even when publications don't.)_\n")
    lines.append(md_table(
        ["Country", "Domain", "est", "pub", "pat", "over_gap"], over))

    lines.append("\n## Most under-rated cells (both counts exceed the estimate)")
    lines.append("_`under_gap` = min(publications, patents) − estimate band. Both "
                 "measured channels outrun the model's band — candidates the estimate "
                 "is sleeping on._\n")
    lines.append(md_table(
        ["Country", "Domain", "est", "pub", "pat", "under_gap"], under))

    lines.append("\n## Systematic bias by country")
    lines.append("_Mean signed (measured − estimate) across domains. Negative = the "
                 "model is systematically more generous than the counts for that country._\n")
    lines.append(md_table(
        ["Country", "mean div", "n domains"],
        [f"| {c} | {fmt_div(v)} | {n} |" for c, v, n in ctry_bias[:10]]
        + ["| … | | |"]
        + [f"| {c} | {fmt_div(v)} | {n} |" for c, v, n in ctry_bias[-10:]]))

    lines.append("\n## Systematic bias by domain")
    lines.append(md_table(
        ["Domain", "mean div", "n countries"],
        [f"| {d} | {fmt_div(v)} | {n} |" for d, v, n in dom_bias[:8]]
        + ["| … | | |"]
        + [f"| {d} | {fmt_div(v)} | {n} |" for d, v, n in dom_bias[-8:]]))

    lines.append("\n## The gap is the finding — research vs commercialisation")
    lines.append("_publications band minus patents band, per cell. **Research-leaning** "
                 "= strong publication output relative to patents (knowledge, not yet "
                 "captured); **patent-leaning** = the reverse._\n")
    lines.append("**Research-leaning (publications ≫ patents):**\n")
    lines.append(md_table(
        ["Country", "Domain", "pub", "pat", "Δ"],
        [f"| {cname(names, r['country_iso'])} | {r['domain_label']} | "
         f"{r['publications_ord']} | {r['patents_ord']} | +{r['_pp']} |"
         for r in research_lean]))
    lines.append("\n**Patent-leaning (patents ≫ publications):**\n")
    lines.append(md_table(
        ["Country", "Domain", "pub", "pat", "Δ"],
        [f"| {cname(names, r['country_iso'])} | {r['domain_label']} | "
         f"{r['publications_ord']} | {r['patents_ord']} | {r['_pp']} |"
         for r in patent_lean]))

    lines.append("\n---")
    lines.append("_Method note: this compares activity **bands**, the only signal "
                 "common to all sources. It measures where the estimate and the counts "
                 "disagree — not which is 'right'. A cell can diverge because the "
                 "estimate is stale/biased, because publication/patent counts lag or are "
                 "language-biased, or because the domains genuinely differ in how "
                 "capability shows up. Treat large divergences as **cells to review**, "
                 "per CAVEATS Tier-1 #1._")

    md = "\n".join(lines) + "\n"
    md_path = OUT_DIR / "_divergence_report.md"
    md_path.write_text(md, encoding="utf-8")

    print(f"wrote {csv_path.relative_to(ROOT)} and {md_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
