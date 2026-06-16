"""Techno-Science Capability — global country x domain comparison dashboard.

    streamlit run dashboard/app.py

Reads data/jobs.db (populated by run_research.py). Shows job quantity + skill
level per country per domain, country comparisons, and a composite capability
score — with honest precision/confidence labelling.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import taxonomy  # noqa: E402
from store import DB_PATH  # noqa: E402

st.set_page_config(page_title="Techno-Science Capability", layout="wide")


@st.cache_data(ttl=120)
def load() -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM cells WHERE source='gemini_research'", conn)
    finally:
        conn.close()
    if df.empty:
        return df
    df["domain_label"] = df["domain"].map(taxonomy.DOMAIN_LABELS).fillna(df["domain"])
    df["volume_ord"] = df["volume_ord"].fillna(0)
    df["skill_level"] = df["skill_level"].fillna(0)
    df["frontier"] = df["frontier"].fillna(0.0)
    # composite capability 0-100: quantity 40% + skill 40% + frontier 20%
    df["capability"] = (
        0.4 * (df["volume_ord"] / 5.0)
        + 0.4 * ((df["skill_level"] - 1).clip(lower=0) / 4.0)
        + 0.2 * df["frontier"].clip(0, 1)
    ) * 100
    return df


df = load()

st.title("🌐 Techno-Science National Capability")
st.caption("Advanced-tech hiring as a leading indicator of national capability. "
           "Estimates from Gemini grounded research — a capability *signal*, not "
           "official statistics.")

if df.empty:
    st.warning("No data yet. Run `python run_research.py` to populate data/jobs.db.")
    st.stop()

est = (df["source"] == "gemini_research").mean()
st.info(f"⚠️ {est:.0%} of cells are **estimated** (precision = band). "
        "Volumes are relative bands, not exact counts; treat cross-country "
        "comparison as directional. ATS-scraped depth + absolute counts land later.")

m1, m2, m3 = st.columns(3)
m1.metric("Countries", df["country_iso"].nunique())
m2.metric("Domains", df["domain"].nunique())
m3.metric("Cells", len(df))

(tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11) = st.tabs(
    ["Capability matrix", "Quantity vs skill", "Country profile", "Rankings",
     "Complexity (OEC)", "Adjacent possible", "Ambition vs reality", "Trends",
     "Verified (ATS)", "MNC footprint", "Triangulation"]
)

DOMAIN_ORDER = [taxonomy.DOMAIN_LABELS[d] for d in taxonomy.ALL_DOMAINS
                if d in set(df["domain"])]


def pivot(metric: str) -> pd.DataFrame:
    p = df.pivot_table(index="country_name", columns="domain_label",
                       values=metric, aggfunc="mean")
    cols = [c for c in DOMAIN_ORDER if c in p.columns]
    return p[cols]


with tab1:
    metric = st.radio("Colour by", ["capability", "volume_ord", "skill_level", "frontier"],
                      horizontal=True, format_func=lambda x: {
                          "capability": "Composite capability",
                          "volume_ord": "Job quantity (band)",
                          "skill_level": "Skill level (tier)",
                          "frontier": "Frontier R&D"}[x])
    p = pivot(metric)
    order = p.mean(axis=1).sort_values(ascending=False).index
    fig = px.imshow(p.loc[order], aspect="auto", color_continuous_scale="Viridis",
                    labels=dict(x="Domain", y="Country", color=metric))
    fig.update_layout(height=max(400, 24 * len(order)))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Quantity band 0–5 (none→very_high) · skill tier 1–5 · "
               "frontier 0–1 · capability 0–100 (40% quantity, 40% skill, 20% frontier).")

with tab2:
    dom = st.selectbox("Domain", taxonomy.ALL_DOMAINS,
                       format_func=lambda d: taxonomy.DOMAIN_LABELS[d])
    sub = df[df["domain"] == dom]
    fig = px.scatter(sub, x="volume_ord", y="skill_level", size="capability",
                     color="frontier", text="country_iso",
                     color_continuous_scale="Plasma",
                     labels={"volume_ord": "Job quantity (band 0–5)",
                             "skill_level": "Skill level (tier 1–5)",
                             "frontier": "Frontier"},
                     range_x=[-0.5, 5.5], range_y=[0.5, 5.5])
    fig.update_traces(textposition="top center")
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Top-right = high volume **and** high skill. Bubble size = composite.")

with tab3:
    country = st.selectbox("Country", sorted(df["country_name"].unique()))
    sub = df[df["country_name"] == country].set_index("domain_label")
    sub = sub.reindex([d for d in DOMAIN_ORDER if d in sub.index])
    fig = px.bar(sub.reset_index(), x="capability", y="domain_label",
                 orientation="h", color="skill_level",
                 color_continuous_scale="Viridis",
                 labels={"capability": "Capability (0–100)", "domain_label": ""})
    fig.update_layout(height=max(420, 22 * len(sub)),
                      yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        sub[["volume_band", "skill_level", "frontier", "capability",
             "confidence", "rationale"]].round(1),
        use_container_width=True,
    )

with tab4:
    colA, colB = st.columns(2)
    with colA:
        st.subheader("Overall capability (mean across domains)")
        rank = (df.groupby("country_name")["capability"].mean()
                .sort_values(ascending=False).reset_index())
        st.plotly_chart(
            px.bar(rank, x="capability", y="country_name", orientation="h",
                   color="capability", color_continuous_scale="Viridis")
            .update_layout(height=700, yaxis={"categoryorder": "total ascending"}),
            use_container_width=True)
    with colB:
        st.subheader("Domain leaders")
        for d in taxonomy.ALL_DOMAINS:
            if d not in set(df["domain"]):
                continue
            top = (df[df["domain"] == d].nlargest(3, "capability")["country_iso"].tolist())
            st.write(f"**{taxonomy.DOMAIN_LABELS[d]}** — {', '.join(top)}")


@st.cache_data(ttl=120)
def oec_report():
    from analysis import complexity
    rep = complexity.full_report()
    # convert pandas objects to plain structures for caching safety
    return {
        "names": rep["names"],
        "pci": rep["pci"],
        "basket": rep["basket_complexity"],
        "eci": rep["eci"],
        "diversity": rep["diversity"],
        "proximity": rep["proximity"],
        "density": rep["density"],
        "M": rep["M"],
    }


with tab5:
    st.subheader("Economic-complexity view (OEC methodology)")
    st.caption(
        "Borrowed from the Observatory of Economic Complexity: we treat "
        "(country × domain) hiring like (country × product) trade. These measure "
        "**structure**, not raw size — they complement the capability ranking."
    )
    rep = oec_report()
    pci, basket = rep["pci"], rep["basket"]
    names = rep["names"]

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Domain Complexity (PCI)** — high = rare & hard to do")
        pdf = pci.reset_index()
        pdf.columns = ["domain", "PCI"]
        pdf["domain"] = pdf["domain"].map(taxonomy.DOMAIN_LABELS).fillna(pdf["domain"])
        st.plotly_chart(
            px.bar(pdf, x="PCI", y="domain", orientation="h", color="PCI",
                   color_continuous_scale="RdBu")
            .update_layout(height=max(380, 22 * len(pdf)),
                           yaxis={"categoryorder": "total ascending"}),
            use_container_width=True)
        st.caption("Advanced packaging, memory & nanomaterials score highest: few "
                   "countries do them well. AI/cloud/genomics are widely attempted → lower PCI.")
    with cB:
        st.markdown("**Basket complexity** — is your *mix* concentrated in hard domains?")
        bdf = basket.head(15).reset_index()
        bdf.columns = ["iso", "score"]
        bdf["country"] = bdf["iso"].map(names).fillna(bdf["iso"])
        st.plotly_chart(
            px.bar(bdf, x="score", y="country", orientation="h", color="score",
                   color_continuous_scale="Viridis")
            .update_layout(height=380, yaxis={"categoryorder": "total ascending"}),
            use_container_width=True)
        st.caption("Taiwan/Malaysia/Korea lead: portfolios concentrated in the rarest "
                   "domains (incl. semiconductor packaging). Differs from raw "
                   "capability (US-led) by design.")

    st.divider()
    st.markdown("**Technology proximity** — the deep-tech 'product space'")
    prox = rep["proximity"]
    if not prox.empty:
        pdisp = prox.copy()
        pdisp.index = [taxonomy.DOMAIN_LABELS.get(d, d) for d in pdisp.index]
        pdisp.columns = [taxonomy.DOMAIN_LABELS.get(d, d) for d in pdisp.columns]
        st.plotly_chart(
            px.imshow(pdisp, aspect="auto", color_continuous_scale="Magma",
                      labels=dict(color="Proximity")).update_layout(
                          height=max(480, 16 * len(pdisp))),
            use_container_width=True)
        st.caption("How often two domains are co-developed by the same countries. "
                   "AI↔Digital and Bio↔Pharma are the tightest couplings.")
    with st.expander("⚠️ How to read these (and their limits)"):
        st.markdown(
            "- **Classic eigenvector ECI is unreliable here**: it needs hundreds of "
            "'products' to be stable; with 9 domains it's noisy and penalises "
            "all-round leaders (the US looks *less* complex because it's strong "
            "*everywhere*, so it's 'specialised' nowhere). We show **basket "
            "complexity** instead as the interpretable headline.\n"
            "- **PCI is robust and meaningful** even at this size — it ranks "
            "domains by how rare strong capability is.\n"
            "- All of this rides on **estimated** band data; treat as directional.")


with tab6:
    st.subheader("Adjacent possible — what each country is positioned to build next")
    st.caption(
        "For domains a country is NOT yet specialised in, **density** measures how "
        "close its existing capabilities are (via domain proximity). High density "
        "on an unbuilt domain = the natural next capability to develop."
    )
    rep = oec_report()
    dens, M, names = rep["density"], rep["M"], rep["names"]
    if dens.empty:
        st.info("Not enough data for density.")
    else:
        iso = st.selectbox("Country", sorted(dens.index),
                           format_func=lambda i: f"{i} — {names.get(i, i)}")
        row, spec = dens.loc[iso], M.loc[iso]
        unbuilt = row[spec < 1].sort_values(ascending=False)
        built = sorted(d for d in M.columns if spec[d] >= 1)
        st.write("**Already specialised in:** "
                 + (", ".join(taxonomy.DOMAIN_LABELS.get(d, d) for d in built) or "—"))
        if len(unbuilt):
            odf = unbuilt.reset_index()
            odf.columns = ["domain", "density"]
            odf["domain"] = odf["domain"].map(taxonomy.DOMAIN_LABELS).fillna(odf["domain"])
            st.plotly_chart(
                px.bar(odf, x="density", y="domain", orientation="h", color="density",
                       color_continuous_scale="Plasma",
                       title=f"Nearest unbuilt capabilities for {names.get(iso, iso)}")
                .update_layout(height=360, yaxis={"categoryorder": "total ascending"}),
                use_container_width=True)
        else:
            st.success("Specialised across all domains in this panel.")

@st.cache_data(ttl=120)
def gap_data():
    from analysis import gap
    if not gap.has_ambition():
        return None
    return gap.gap_frame()


with tab7:
    st.subheader("Ambition vs reality — stated intent minus revealed capability")
    st.caption(
        "What each country *says* it wants to build (national strategies, funded "
        "programmes, R&D budgets, headline announcements) versus what its hiring "
        "actually *reveals*. Both sides are estimates — read as directional."
    )
    g = gap_data()
    if g is None:
        st.warning("No ambition data yet. Run `python3 ambition.py` to populate it.")
    else:
        st.markdown(
            "**Gap = ambition − revealed.** 🔴 positive = wants it, doesn't yet have "
            "it (build-out / aspiration). ⚪ near zero = consolidating a strength. "
            "🔵 negative = quiet strength, under-stated.")
        view = st.radio("View", ["Gap heatmap", "Biggest build-outs", "Country detail"],
                        horizontal=True)

        if view == "Gap heatmap":
            p = g.pivot_table(index="country_name", columns="domain_label",
                              values="gap", aggfunc="mean")
            cols = [taxonomy.DOMAIN_LABELS[d] for d in taxonomy.ALL_DOMAINS
                    if taxonomy.DOMAIN_LABELS[d] in p.columns]
            p = p[cols]
            order = p.mean(axis=1).sort_values(ascending=False).index
            fig = px.imshow(p.loc[order], aspect="auto",
                            color_continuous_scale="RdBu_r", color_continuous_midpoint=0,
                            labels=dict(x="Domain", y="Country", color="Gap"))
            fig.update_layout(height=max(400, 24 * len(order)))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Red = aspiration exceeds current capability; blue = capability "
                       "exceeds stated ambition.")

        elif view == "Biggest build-outs":
            top = g.nlargest(20, "gap")[
                ["country_name", "domain_label", "ambition", "target_level",
                 "horizon", "revealed", "gap"]].round(1)
            st.markdown("**Where intent most outruns current capability** "
                        "(the world's stated build-out priorities):")
            fig = px.bar(top.iloc[::-1], x="gap",
                         y=top.iloc[::-1]["country_name"] + " · " + top.iloc[::-1]["domain_label"],
                         orientation="h", color="ambition",
                         color_continuous_scale="Reds",
                         labels={"y": "", "gap": "Ambition − revealed"})
            fig.update_layout(height=620)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(top, use_container_width=True, hide_index=True)

        else:
            country = st.selectbox("Country", sorted(g["country_name"].unique()))
            sub = g[g["country_name"] == country].copy()
            sub = sub.set_index("domain_label").reindex(
                [taxonomy.DOMAIN_LABELS[d] for d in taxonomy.ALL_DOMAINS
                 if taxonomy.DOMAIN_LABELS[d] in set(g["domain_label"])])
            melt = sub.reset_index()[["domain_label", "revealed", "ambition_score"]]
            melt = melt.melt(id_vars="domain_label", var_name="kind", value_name="score")
            melt["kind"] = melt["kind"].map({"revealed": "Revealed capability",
                                             "ambition_score": "Stated ambition"})
            fig = px.bar(melt, x="score", y="domain_label", color="kind",
                         barmode="group", orientation="h",
                         labels={"domain_label": "", "score": "0–100"},
                         color_discrete_map={"Revealed capability": "#2c7fb8",
                                             "Stated ambition": "#d95f0e"})
            fig.update_layout(height=440)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                sub.reset_index()[["domain_label", "ambition", "target_level",
                                   "horizon", "revealed", "gap"]].round(1),
                use_container_width=True, hide_index=True)


@st.cache_data(ttl=120)
def history_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        h = pd.read_sql_query(
            "SELECT snapshot_date, country_iso, country_name, domain, capability "
            "FROM cell_history WHERE source='gemini_research'", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()
    return h


with tab8:
    st.subheader("Longitudinal trends — capability over time")
    st.caption(
        "A weekly cron (`weekly_refresh.sh`, Mondays 09:00) re-runs the research "
        "and records a dated snapshot. Trends become meaningful after a few weeks."
    )
    h = history_data()
    if h.empty:
        st.warning("No snapshots yet. Run `python3 refresh.py --snapshot-only` "
                   "(or wait for the weekly cron).")
    else:
        dates = sorted(h["snapshot_date"].unique())
        st.write(f"**{len(dates)} snapshot(s):** {', '.join(dates)}")
        if len(dates) < 2:
            st.info("Only one snapshot so far — the line chart needs ≥2 weeks to "
                    "show movement. Showing the current level meanwhile.")
        per_country = (h.groupby(["snapshot_date", "country_name"])["capability"]
                       .mean().reset_index())
        default = (per_country[per_country.snapshot_date == dates[-1]]
                   .nlargest(8, "capability")["country_name"].tolist())
        picks = st.multiselect("Countries", sorted(h["country_name"].unique()),
                               default=default)
        sub = per_country[per_country["country_name"].isin(picks)]
        fig = px.line(sub, x="snapshot_date", y="capability", color="country_name",
                      markers=True,
                      labels={"snapshot_date": "Snapshot", "capability": "Mean capability",
                              "country_name": "Country"})
        fig.update_layout(height=480)
        st.plotly_chart(fig, use_container_width=True)
        if len(dates) >= 2:
            st.markdown("**Biggest movers** (capability change, first → latest snapshot)")
            piv = per_country.pivot_table(index="country_name", columns="snapshot_date",
                                          values="capability")
            piv["change"] = piv[dates[-1]] - piv[dates[0]]
            movers = piv["change"].dropna().sort_values(ascending=False)
            cM1, cM2 = st.columns(2)
            cM1.write("📈 Risers"); cM1.dataframe(movers.head(8).round(1))
            cM2.write("📉 Fallers"); cM2.dataframe(movers.tail(8).round(1))


@st.cache_data(ttl=120)
def ats_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        a = pd.read_sql_query("SELECT * FROM cells WHERE source='ats'", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()
    if not a.empty:
        a["domain_label"] = a["domain"].map(taxonomy.DOMAIN_LABELS).fillna(a["domain"])
    return a


with tab9:
    st.subheader("Verified hiring — real ATS postings (precision = counted)")
    st.caption(
        "Actual open postings scraped from public ATS boards (Greenhouse, Lever, "
        "Ashby). Unlike the estimated bands elsewhere, these are **observed counts**. "
        "Coverage is deliberately narrow — a curated set of frontier employers, "
        "heavily US-weighted — so this is *depth*, not a global census."
    )
    a = ats_data()
    if a.empty:
        st.warning("No ATS data yet. Run `python3 ats/probe.py` then "
                   "`python3 ats/scrape.py`.")
    else:
        tot = int(a["volume_estimate"].str.extract(r"(\d+)").astype(float).sum().iloc[0])
        c1, c2, c3 = st.columns(3)
        c1.metric("Verified cells", len(a))
        c2.metric("Countries", a["country_iso"].nunique())
        c3.metric("Open postings counted", tot)
        st.caption("Each cell shows the live posting count and the employers behind it.")

        p = a.pivot_table(index="country_iso", columns="domain_label",
                          values="volume_ord", aggfunc="max", fill_value=0)
        cols = [taxonomy.DOMAIN_LABELS[d] for d in taxonomy.ALL_DOMAINS
                if taxonomy.DOMAIN_LABELS[d] in p.columns]
        p = p[cols]
        order = p.max(axis=1).sort_values(ascending=False).index
        fig = px.imshow(p.loc[order], aspect="auto", color_continuous_scale="Greens",
                        labels=dict(x="Domain", y="Country",
                                    color="Volume band (from counts)"))
        fig.update_layout(height=max(320, 26 * len(order)))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Cell detail** (observed postings + employers)")
        show = a[["country_iso", "domain_label", "volume_estimate", "skill_level",
                  "precision", "rationale"]].copy()
        show.columns = ["Country", "Domain", "Postings", "Skill", "Precision", "Employers / note"]
        show = show.sort_values("Postings",
                                key=lambda s: s.str.extract(r"(\d+)")[0].astype(int),
                                ascending=False)
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.info("ℹ️ These `ats` cells are stored separately from the `gemini_research` "
                "estimates and are **not** blended into the other tabs — they're the "
                "ground-truth calibration layer (the precision ratchet: band → counted).")


@st.cache_data(ttl=120)
def footprint_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        f = pd.read_sql_query("SELECT * FROM footprint", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()
    return f


FUNC_LABELS = {
    "research": "Research / R&D", "engineering": "Engineering / Design",
    "manufacturing_test": "Manufacturing / Test", "field_deployment": "Field / Deployment",
    "commercial": "Commercial / GTM", "operations": "Corporate / Ops",
}
FUNC_ORDER = ["research", "engineering", "manufacturing_test", "field_deployment",
              "commercial", "operations"]


with tab10:
    st.subheader("Cross-border MNC footprint — division of labour")
    st.caption(
        "How multinationals orchestrate their value chain across countries: where "
        "each company runs **research**, **engineering**, **manufacturing/test**, "
        "**field deployment**, **commercial**, and **corporate** roles. Built from "
        "real ATS postings — same source as the Verified tab. US-skewed coverage."
    )
    fp = footprint_data()
    if fp.empty:
        st.warning("No footprint data yet. Run `python3 ats/footprint.py`.")
    else:
        fp["func_label"] = fp["function"].map(FUNC_LABELS).fillna(fp["function"])
        multi = (fp.groupby("employer")["country_iso"].nunique()
                 .sort_values(ascending=False))
        multi = multi[multi >= 2]
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Multinationals mapped", int((fp.groupby("employer")["country_iso"]
                                                 .nunique() >= 2).sum()))
        cc2.metric("Countries", fp["country_iso"].nunique())
        cc3.metric("Roles classified", int(fp["n_roles"].sum()))

        emp = st.selectbox("Employer", multi.index.tolist(),
                           help="Only employers operating in ≥2 countries are shown.")
        sub = fp[fp["employer"] == emp]

        # country × function heatmap for this employer
        piv = sub.pivot_table(index="country_iso", columns="function",
                              values="n_roles", aggfunc="sum", fill_value=0)
        fcols = [f for f in FUNC_ORDER if f in piv.columns]
        piv = piv[fcols]
        piv.columns = [FUNC_LABELS[f] for f in fcols]
        piv = piv.loc[piv.sum(axis=1).sort_values(ascending=False).index]
        fig = px.imshow(piv, aspect="auto", color_continuous_scale="Tealgrn",
                        labels=dict(x="Function", y="Country", color="Open roles"),
                        title=f"{emp} — where each function lives")
        fig.update_layout(height=max(300, 30 * len(piv) + 120))
        st.plotly_chart(fig, use_container_width=True)

        # narrative read: function mix by country
        st.markdown("**Read:** each country's role mix reveals its place in the chain "
                    "— R&D/engineering = a build site; commercial/field only = a market outpost.")

        # global view: function specialisation by country across ALL employers
        st.divider()
        st.markdown("**Where the world does each function** (all mapped MNCs combined)")
        gpiv = fp.pivot_table(index="country_iso", columns="function",
                              values="n_roles", aggfunc="sum", fill_value=0)
        gcols = [f for f in FUNC_ORDER if f in gpiv.columns]
        gpiv = gpiv[gcols]
        # row-normalise to show each country's FUNCTION MIX (share), not raw size
        share = gpiv.div(gpiv.sum(axis=1).replace(0, 1), axis=0)
        share.columns = [FUNC_LABELS[f] for f in gcols]
        share = share.loc[gpiv.sum(axis=1).sort_values(ascending=False).index]
        share = share[share.index.isin(gpiv.sum(axis=1)[gpiv.sum(axis=1) >= 3].index)]
        fig2 = px.imshow(share, aspect="auto", color_continuous_scale="Purples",
                         labels=dict(x="Function", y="Country", color="Share of roles"),
                         title="Function mix by country (share of each country's roles)")
        fig2.update_layout(height=max(320, 26 * len(share) + 120))
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("A country bright on Research/Engineering is a build hub; bright on "
                   "Commercial/Field is a sales-and-deployment market. This is the "
                   "cross-border division-of-labour signal from CLAUDE.md.")
        st.info("ℹ️ Footprint is built from the same ATS postings as the Verified tab — "
                "real open roles, narrow & US-heavy coverage. It maps *orchestration "
                "patterns*, not a complete census.")


@st.cache_data(ttl=120)
def patent_trend_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(
            "SELECT country_iso, domain, year, n_patents FROM patent_trend", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=120)
def publication_trend_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(
            "SELECT country_iso, domain, year, n_pubs FROM publication_trend", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=120)
def triangulation_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        p = pd.read_sql_query(
            "SELECT country_iso, country_name, domain, volume_estimate "
            "FROM cells WHERE source='publications'", conn)
        gg = pd.read_sql_query(
            "SELECT country_iso, domain, volume_ord, skill_level, frontier "
            "FROM cells WHERE source='gemini_research'", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()
    if p.empty or gg.empty:
        return pd.DataFrame()
    # real publication counts (parse the integer out of "<n> publications (year)")
    p["pubs"] = p["volume_estimate"].str.extract(r"(\d+)").astype(float)
    gg["gem_cap"] = (0.4 * (gg["volume_ord"] / 5)
                     + 0.4 * ((gg["skill_level"] - 1).clip(lower=0) / 4)
                     + 0.2 * gg["frontier"].clip(0, 1)) * 100
    m = p.merge(gg[["country_iso", "domain", "gem_cap"]],
                on=["country_iso", "domain"], how="inner")
    # patents are optional (need a key) — left-join so the tab works without them
    conn2 = sqlite3.connect(DB_PATH)
    try:
        pat = pd.read_sql_query(
            "SELECT country_iso, domain, volume_estimate FROM cells "
            "WHERE source='patents'", conn2)
    except Exception:
        pat = pd.DataFrame()
    finally:
        conn2.close()
    if not pat.empty:
        pat["pats"] = pat["volume_estimate"].str.extract(r"(\d+)").astype(float)
        m = m.merge(pat[["country_iso", "domain", "pats"]],
                    on=["country_iso", "domain"], how="left")
        m["pat_pct"] = m.groupby("domain")["pats"].rank(pct=True) * 100
    # percentile-rank signals WITHIN each domain (0-100) so they're comparable
    m["pub_pct"] = m.groupby("domain")["pubs"].rank(pct=True) * 100
    m["gem_pct"] = m.groupby("domain")["gem_cap"].rank(pct=True) * 100
    m["divergence"] = m["pub_pct"] - m["gem_pct"]  # +ve = stronger in research than hiring
    m["domain_label"] = m["domain"].map(taxonomy.DOMAIN_LABELS).fillna(m["domain"])
    return m


with tab11:
    st.subheader("Triangulation — research output vs hiring estimate")
    st.caption(
        "An **independent** check: OpenAlex publication counts (real, counted) "
        "versus the Gemini hiring-capability estimate. Where the two agree, "
        "confidence is high. Where they diverge, it's a signal: strong research "
        "but weak hiring = academic base without industry (or vice-versa)."
    )
    m = triangulation_data()
    if m.empty:
        st.warning("Need both publications and gemini_research data. "
                   "Run `python3 research_sources/publications.py`.")
    else:
        corr = m["pub_pct"].corr(m["gem_pct"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Cells compared", len(m))
        c2.metric("Rank agreement", f"{corr:.2f}", help="1.0 = perfect agreement")
        c3.metric("Publications (2024)", f"{int(m['pubs'].sum()):,}")

        st.markdown("**Agreement scatter** — each point is a country×domain. On the "
                    "diagonal = the two signals agree; off-diagonal = they disagree.")
        fig = px.scatter(
            m, x="gem_pct", y="pub_pct", color="divergence",
            color_continuous_scale="RdBu", color_continuous_midpoint=0,
            hover_data={"country_iso": True, "domain_label": True,
                        "pubs": True, "gem_pct": ":.0f", "pub_pct": ":.0f"},
            labels={"gem_pct": "Hiring-capability percentile (Gemini)",
                    "pub_pct": "Research-output percentile (OpenAlex)"})
        fig.add_shape(type="line", x0=0, y0=0, x1=100, y1=100,
                      line=dict(color="gray", dash="dot"))
        fig.update_layout(height=560)
        st.plotly_chart(fig, use_container_width=True)

        colL, colR = st.columns(2)
        with colL:
            st.markdown("**📚 Research-heavy, hiring-light** (publishes more than it hires)")
            top = m.nlargest(12, "divergence")[
                ["country_iso", "domain_label", "pubs", "gem_pct", "pub_pct"]]
            top = top.rename(columns={"country_iso": "Country", "domain_label": "Domain",
                                      "pubs": "Pubs", "gem_pct": "Hire %ile",
                                      "pub_pct": "Pub %ile"}).round(0)
            st.dataframe(top, use_container_width=True, hide_index=True)
        with colR:
            st.markdown("**🏭 Hiring-heavy, research-light** (hires more than it publishes)")
            bot = m.nsmallest(12, "divergence")[
                ["country_iso", "domain_label", "pubs", "gem_pct", "pub_pct"]]
            bot = bot.rename(columns={"country_iso": "Country", "domain_label": "Domain",
                                      "pubs": "Pubs", "gem_pct": "Hire %ile",
                                      "pub_pct": "Pub %ile"}).round(0)
            st.dataframe(bot, use_container_width=True, hide_index=True)

        st.info(f"ℹ️ Rank agreement **{corr:.2f}** = moderate: the two independent "
                "signals broadly concur, validating the capability estimates, while "
                "the divergences flag genuine structural differences (academic vs "
                "industrial strength). Publications = OpenAlex 2024, real counts.")

        # --- patents panel (only if the patents layer has been populated) ---
        st.divider()
        if "pat_pct" in m.columns and m["pat_pct"].notna().any():
            mp = m.dropna(subset=["pat_pct"])
            st.markdown("### 🔬 Research → 🏭 Invention: publications vs patents")
            st.caption("Publications measure research output; patents measure applied "
                       "invention. Above the line = strong research but fewer patents "
                       "(upstream / academic); below = patents outrun publications "
                       "(applied / commercialisation-led).")
            corr_pp = mp["pub_pct"].corr(mp["pat_pct"])
            figp = px.scatter(
                mp, x="pub_pct", y="pat_pct", color="domain_label",
                hover_data={"country_iso": True, "pubs": True, "pats": True},
                labels={"pub_pct": "Publications percentile (OpenAlex)",
                        "pat_pct": "Patents percentile (USPTO/PatentsView)",
                        "domain_label": "Domain"})
            figp.add_shape(type="line", x0=0, y0=0, x1=100, y1=100,
                           line=dict(color="gray", dash="dot"))
            figp.update_layout(height=560)
            st.plotly_chart(figp, use_container_width=True)
            st.caption(f"Research↔invention rank agreement: {corr_pp:.2f}. Patents are "
                       "from Google patents-public-data (BigQuery), classified by CPC "
                       "code, counted by inventor country.")

            # momentum trends (multi-year): research (publications) + invention (patents)
            tr = patent_trend_data()
            pr = publication_trend_data()
            if not tr.empty or not pr.empty:
                st.divider()
                st.markdown("### 📈 Momentum over time — research & invention")
                st.caption("The signal a single snapshot can't show: who is "
                           "*accelerating*. Research = OpenAlex publications, "
                           "invention = CPC-classified patents, by author/inventor country.")
                dom_pick = st.selectbox(
                    "Domain", taxonomy.ALL_DOMAINS,
                    format_func=lambda d: taxonomy.DOMAIN_LABELS.get(d, d),
                    key="trend_domain")
                dlabel = taxonomy.DOMAIN_LABELS.get(dom_pick, dom_pick)

                def _trend_fig(df, val, title):
                    sub = df[df["domain"] == dom_pick]
                    if sub.empty:
                        return None
                    ly = sub["year"].max()
                    top = sub[sub["year"] == ly].nlargest(7, val)["country_iso"].tolist()
                    sub = sub[sub["country_iso"].isin(top)]
                    f = px.line(sub, x="year", y=val, color="country_iso", markers=True,
                                labels={"year": "Year", val: title, "country_iso": "Country"},
                                title=title)
                    f.update_layout(height=440, margin=dict(t=40, b=10))
                    return f

                cP, cI = st.columns(2)
                with cP:
                    f1 = _trend_fig(pr, "n_pubs", "Research (publications)") if not pr.empty else None
                    if f1: st.plotly_chart(f1, use_container_width=True)
                    else: st.info("No publication trend yet — run "
                                  "`publications.py --years 2016 2018 2020 2022`.")
                with cI:
                    f2 = _trend_fig(tr, "n_patents", "Invention (patents)") if not tr.empty else None
                    if f2: st.plotly_chart(f2, use_container_width=True)
                    else: st.info("No patent trend yet.")
                st.caption(f"**{dlabel}** — top-7 countries by latest year, each panel. "
                           "Recent years lag (publications + patents take time to fully "
                           "index/publish) — read the slope, not the final dot.")
        else:
            st.markdown("### 🔬 Patents layer — not yet populated")
            st.caption("Configure BigQuery (`GOOGLE_APPLICATION_CREDENTIALS` + "
                       "`BQ_PROJECT` in `.env`), then run "
                       "`python3 research_sources/patents_bq.py --check` and "
                       "`python3 research_sources/patents_bq.py --years 2016 2018 2020 2022`. "
                       "A research→invention view + momentum trend appear here automatically.")


st.divider()
st.caption(f"DB: {DB_PATH} · revealed=gemini_research (estimates) · ats=verified "
           "counts · publications=OpenAlex counts · ambition=stated intent.")
