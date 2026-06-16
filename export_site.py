"""Export the key dashboard views to a self-contained static site (docs/index.html).

GitHub Pages can't run Streamlit (it needs a live Python server), so this renders
the headline charts to a single static HTML file with interactive Plotly figures
embedded. No live data refresh — it's a snapshot of the current DB.

Run under the venv:  .venv/bin/python export_site.py
Output:              docs/index.html  (Pages serves from /docs)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.io as pio

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import taxonomy  # noqa: E402
from store import DB_PATH  # noqa: E402
from analysis import complexity  # noqa: E402

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

CAP_W = dict(volume=0.4, skill=0.4, frontier=0.2)


def capability(df: pd.DataFrame) -> pd.Series:
    return (CAP_W["volume"] * (df["volume_ord"] / 5)
            + CAP_W["skill"] * ((df["skill_level"] - 1).clip(lower=0) / 4)
            + CAP_W["frontier"] * df["frontier"].clip(0, 1)) * 100


# Embed Plotly's own JS in the FIRST figure only, so the bundled library always
# matches the exact version that encoded the figures' typed-array (bdata) data.
# A mismatched CDN version silently fails to decode bdata -> blank heatmaps.
_PLOTLY_JS_EMITTED = {"done": False}


def fig_html(fig, height=480) -> str:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      template="plotly_white")
    include = "inline" if not _PLOTLY_JS_EMITTED["done"] else False
    _PLOTLY_JS_EMITTED["done"] = True
    return pio.to_html(fig, include_plotlyjs=include, full_html=False,
                       config={"displayModeBar": False})


def main():
    conn = sqlite3.connect(DB_PATH)
    g = pd.read_sql_query("SELECT * FROM cells WHERE source='gemini_research'", conn)
    try:
        ats = pd.read_sql_query("SELECT * FROM cells WHERE source='ats'", conn)
    except Exception:
        ats = pd.DataFrame()
    try:
        amb = pd.read_sql_query("SELECT * FROM ambition", conn)
    except Exception:
        amb = pd.DataFrame()
    try:
        fp = pd.read_sql_query("SELECT * FROM footprint", conn)
    except Exception:
        fp = pd.DataFrame()
    try:
        pub = pd.read_sql_query(
            "SELECT country_iso, domain, volume_estimate FROM cells "
            "WHERE source='publications'", conn)
    except Exception:
        pub = pd.DataFrame()
    conn.close()

    g["capability"] = capability(g)
    g["domain_label"] = g["domain"].map(taxonomy.DOMAIN_LABELS)

    blocks = []

    # 1. Overall capability ranking
    rank = (g.groupby("country_name")["capability"].mean()
            .sort_values(ascending=False).reset_index())
    f = px.bar(rank, x="capability", y="country_name", orientation="h",
               color="capability", color_continuous_scale="Viridis",
               title="National techno-science capability (mean across 9 domains)")
    f.update_layout(yaxis={"categoryorder": "total ascending"})
    blocks.append(("Capability ranking", fig_html(f, height=720),
                   "Quantity × skill × frontier, averaged across all nine domains. "
                   "A capability <em>signal</em> from estimated data — not an official statistic."))

    # 2. Capability heatmap
    piv = g.pivot_table(index="country_name", columns="domain_label",
                        values="capability", aggfunc="mean")
    cols = [taxonomy.DOMAIN_LABELS[d] for d in taxonomy.ALL_DOMAINS
            if taxonomy.DOMAIN_LABELS[d] in piv.columns]
    piv = piv[cols]
    order = piv.mean(axis=1).sort_values(ascending=False).index
    f = px.imshow(piv.loc[order], aspect="auto", color_continuous_scale="Viridis",
                  title="Capability heatmap — country × domain")
    blocks.append(("Capability matrix", fig_html(f, height=760),
                   "Each cell is a country's capability score in one domain."))

    # 3. OEC: PCI + basket complexity
    rep = complexity.full_report()
    pci = rep["pci"].reset_index(); pci.columns = ["domain", "PCI"]
    pci["domain"] = pci["domain"].map(taxonomy.DOMAIN_LABELS)
    f = px.bar(pci, x="PCI", y="domain", orientation="h", color="PCI",
               color_continuous_scale="RdBu",
               title="Domain complexity (PCI) — high = rare & hard")
    f.update_layout(yaxis={"categoryorder": "total ascending"})
    blocks.append(("Domain complexity (OEC)", fig_html(f, height=max(420, 22 * len(pci))),
                   "Advanced packaging, memory, nanomaterials & fab equipment score "
                   "highest: few countries do them well. AI/cloud/genomics are widely "
                   "attempted, so lower PCI."))

    basket = rep["basket_complexity"].head(15).reset_index()
    basket.columns = ["iso", "score"]
    names = rep["names"]
    basket["country"] = basket["iso"].map(names).fillna(basket["iso"])
    f = px.bar(basket, x="score", y="country", orientation="h", color="score",
               color_continuous_scale="Viridis",
               title="Basket complexity — concentration in the rarest domains")
    f.update_layout(yaxis={"categoryorder": "total ascending"})
    blocks.append(("Basket complexity (OEC)", fig_html(f, height=440),
                   "Taiwan/Malaysia/Korea lead — portfolios concentrated in the "
                   "hardest domains (incl. semiconductor packaging). Differs from raw "
                   "capability (US-led) by design."))

    # 4. Ambition gap (if present)
    if not amb.empty:
        a = amb.rename(columns={"ambition": "amb"})
        a["amb_score"] = (a["amb"] / 5) * 100
        gg = g[["country_iso", "country_name", "domain", "capability"]].merge(
            a[["country_iso", "domain", "amb_score"]], on=["country_iso", "domain"], how="left")
        gg["amb_score"] = gg["amb_score"].fillna(0)
        gg["gap"] = gg["amb_score"] - gg["capability"]
        gg["domain_label"] = gg["domain"].map(taxonomy.DOMAIN_LABELS)
        top = gg.nlargest(20, "gap").iloc[::-1]
        f = px.bar(top, x="gap", y=top["country_name"] + " · " + top["domain_label"],
                   orientation="h", color="gap", color_continuous_scale="Reds",
                   title="Biggest build-outs — stated ambition far exceeds current capability")
        blocks.append(("Ambition vs reality", fig_html(f, height=620),
                       "Where national intent most outruns today's capability — "
                       "Saudi Arabia, UAE, India, Spain, Vietnam building toward AI, "
                       "semiconductors, digital & quantum."))

    # 5. Verified ATS counts
    if not ats.empty:
        ats["n"] = ats["volume_estimate"].str.extract(r"(\d+)").astype(float)
        ats["domain_label"] = ats["domain"].map(taxonomy.DOMAIN_LABELS)
        tv = ats.nlargest(20, "n")[["country_iso", "domain_label", "n"]].iloc[::-1]
        f = px.bar(tv, x="n", y=tv["country_iso"] + " · " + tv["domain_label"],
                   orientation="h", color="n", color_continuous_scale="Greens",
                   title="Verified hiring — real open ATS postings (counted, not estimated)")
        blocks.append(("Verified counts (ATS)", fig_html(f, height=620),
                       "Actual open postings scraped from 14 live Greenhouse/Lever/Ashby "
                       "boards (SpaceX, OpenAI, Anthropic, Mistral, IonQ, PsiQuantum…). "
                       "Coverage is narrow & US-heavy by design — depth, not breadth."))

    # 6. Cross-border MNC footprint — division of labour
    if not fp.empty:
        FL = {"research": "Research", "engineering": "Engineering",
              "manufacturing_test": "Manufacturing/Test", "field_deployment": "Field",
              "commercial": "Commercial", "operations": "Corporate"}
        ford = ["research", "engineering", "manufacturing_test", "field_deployment",
                "commercial", "operations"]
        # function mix by country (share), across all mapped MNCs
        gp = fp.pivot_table(index="country_iso", columns="function",
                            values="n_roles", aggfunc="sum", fill_value=0)
        gp = gp[[c for c in ford if c in gp.columns]]
        big = gp.sum(axis=1)[gp.sum(axis=1) >= 3].index
        share = gp.loc[big].div(gp.loc[big].sum(axis=1), axis=0)
        share.columns = [FL[c] for c in gp.columns]
        share = share.loc[gp.loc[big].sum(axis=1).sort_values(ascending=False).index]
        f = px.imshow(share, aspect="auto", color_continuous_scale="Purples",
                      labels=dict(x="Function", y="Country", color="Share of roles"),
                      title="Division of labour — each country's function mix (all MNCs)")
        n_multi = int((fp.groupby("employer")["country_iso"].nunique() >= 2).sum())
        blocks.append(("Cross-border footprint", fig_html(f, height=560),
                       f"How {n_multi} multinationals split their value chain across "
                       "borders. Countries bright on Research/Engineering are build "
                       "hubs; bright on Commercial/Field are market outposts (sell &"
                       " deploy, don't build). The original project thesis — where each "
                       "economy sits in the global value chain — from real hiring."))

    # 7. Triangulation — publications vs hiring estimate (independent validation)
    if not pub.empty:
        pub = pub.copy()
        pub["pubs"] = pub["volume_estimate"].str.extract(r"(\d+)").astype(float)
        gcap = g.groupby(["country_iso", "domain"])["capability"].mean().reset_index()
        m = pub.merge(gcap, on=["country_iso", "domain"], how="inner")
        m["pub_pct"] = m.groupby("domain")["pubs"].rank(pct=True) * 100
        m["gem_pct"] = m.groupby("domain")["capability"].rank(pct=True) * 100
        m["divergence"] = m["pub_pct"] - m["gem_pct"]
        m["domain_label"] = m["domain"].map(taxonomy.DOMAIN_LABELS)
        corr = m["pub_pct"].corr(m["gem_pct"])
        f = px.scatter(
            m, x="gem_pct", y="pub_pct", color="divergence",
            color_continuous_scale="RdBu", color_continuous_midpoint=0,
            hover_data={"country_iso": True, "domain_label": True, "pubs": True},
            labels={"gem_pct": "Hiring-capability percentile (estimate)",
                    "pub_pct": "Research-output percentile (OpenAlex, real)"},
            title="Triangulation — research output vs hiring estimate")
        f.add_shape(type="line", x0=0, y0=0, x1=100, y1=100,
                    line=dict(color="gray", dash="dot"))
        blocks.append(("Triangulation", fig_html(f, height=560),
                       f"An independent cross-check: real OpenAlex publication counts "
                       f"(2024) vs the hiring-capability estimate. Rank agreement "
                       f"<strong>{corr:.2f}</strong> — moderate, so the estimates are "
                       "broadly corroborated. Points above the line publish more than "
                       "they hire (academic strength); below the line hire more than "
                       "they publish (industrial base)."))

    # assemble
    n_countries = g["country_iso"].nunique()
    n_ats = len(ats) if not ats.empty else 0
    nav = "".join(f'<a href="#s{i}">{t}</a>' for i, (t, _, _) in enumerate(blocks))
    sections = "".join(
        f'<section id="s{i}"><h2>{t}</h2><p class="cap">{cap}</p>{html}</section>'
        for i, (t, html, cap) in enumerate(blocks))

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Techno-Science Capability Observatory</title>
<style>
  :root {{ --bg:#0d1117; --fg:#e6edf3; --mut:#8b949e; --card:#161b22; --acc:#2f81f7; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
         font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  header {{ padding:48px 24px 24px; max-width:1000px; margin:0 auto; }}
  h1 {{ font-size:2.1rem; margin:0 0 8px; }}
  .sub {{ color:var(--mut); font-size:1.05rem; max-width:70ch; }}
  .stats {{ display:flex; gap:28px; margin:24px 0 8px; flex-wrap:wrap; }}
  .stat b {{ font-size:1.7rem; color:var(--acc); display:block; }}
  .stat span {{ color:var(--mut); font-size:.85rem; }}
  nav {{ position:sticky; top:0; background:rgba(13,17,23,.92); backdrop-filter:blur(6px);
         padding:12px 24px; border-bottom:1px solid #21262d; z-index:10; }}
  nav a {{ color:var(--mut); text-decoration:none; margin-right:18px; font-size:.9rem; }}
  nav a:hover {{ color:var(--acc); }}
  section {{ max-width:1000px; margin:0 auto; padding:36px 24px;
             border-bottom:1px solid #21262d; }}
  h2 {{ font-size:1.4rem; }}
  .cap {{ color:var(--mut); max-width:75ch; }}
  .plotly-graph-div {{ background:var(--card); border-radius:10px; padding:8px; }}
  footer {{ max-width:1000px; margin:0 auto; padding:40px 24px 80px; color:var(--mut);
            font-size:.85rem; }}
  .warn {{ background:#1c2128; border:1px solid #30363d; border-left:3px solid #d29922;
           padding:12px 16px; border-radius:8px; margin:16px 0; color:#e6edf3; }}
  code {{ background:#1c2128; padding:2px 6px; border-radius:4px; font-size:.85em; }}
  a.gh {{ color:var(--acc); }}
  a.bmac {{ display:inline-block; background:#FFDD00; color:#000; font-weight:600;
            padding:8px 16px; border-radius:8px; text-decoration:none; margin-top:6px; }}
  a.bmac:hover {{ background:#ffe533; }}
</style></head><body>
<header>
  <h1>🌐 Techno-Science Capability Observatory</h1>
  <p class="sub">A global, country-by-country view of leading-edge industries —
  semiconductors, quantum, AI, precision engineering, advanced materials, biomedical,
  pharmaceuticals, digital and other frontier fields — measured by hiring
  <strong>quantity × skill level</strong>, with economic-complexity analysis.</p>
  <div class="stats">
    <div class="stat"><b>{n_countries}</b><span>countries</span></div>
    <div class="stat"><b>9</b><span>frontier domains</span></div>
    <div class="stat"><b>270</b><span>capability estimates</span></div>
    <div class="stat"><b>{n_ats}</b><span>verified ATS cells</span></div>
  </div>
  <div class="warn">⚠️ <strong>Read me first:</strong> the colourful charts are a
  capability <em>signal</em> built from Gemini grounded-research <em>estimates</em>
  (relative volume bands, not exact counts). The “Verified counts (ATS)” section is
  the only one with real observed numbers. Treat cross-country comparison as
  directional, not authoritative.</div>
</header>
<nav>{nav}</nav>
{sections}
<footer>
  Built with Gemini grounded research + public ATS data (Greenhouse/Lever/Ashby).
  Methodology: OEC-style economic complexity (RCA, PCI, basket complexity,
  adjacent-possible) over a country×domain hiring panel. Static snapshot — the
  live interactive dashboard runs locally via <code>streamlit run dashboard/app.py</code>.
  <br><br>Source &amp; method:
  <a class="gh" href="https://github.com/curioputterings/techno-science-observatory">
  github.com/curioputterings/techno-science-observatory</a>
  <br><br>
  <a class="bmac" href="https://buymeacoffee.com/curioputterings">☕ Buy me a coffee</a>
  &nbsp;·&nbsp; if this is useful to you.
</footer>
</body></html>"""

    out = DOCS / "index.html"
    out.write_text(page)
    print(f"wrote {out}  ({len(blocks)} sections, {out.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
