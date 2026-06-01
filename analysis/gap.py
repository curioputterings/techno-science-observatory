"""Ambition-vs-revealed gap (Phase 6).

Joins the stated-ambition table to revealed capability and computes, per
(country, domain), the gap between intent and reality:

    revealed   0..100  capability score (quantity x skill x frontier), as in the
                       dashboard's capability metric
    ambition   0..100  stated intent, = (ambition/5)*100
    gap        ambition - revealed

Reading the gap:
  + large   strong stated intent, weak current capability -> aspiration / build-out
            (opportunity if backed by funding; overreach if not)
  ~ 0       intent matches capability -> consolidating an existing strength
  - large   capability exceeds stated intent -> a quiet strength, under-marketed

This is a deliberately simple, transparent diff — both sides are estimates, so it
is a *directional* signal, not a forecast.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import taxonomy  # noqa: E402
from store import DB_PATH  # noqa: E402


def _capability(row) -> float:
    vol = (row["volume_ord"] or 0) / 5.0
    skill = max(0, (row["skill_level"] or 0) - 1) / 4.0
    fr = min(1.0, max(0.0, row["frontier"] or 0.0))
    return (0.4 * vol + 0.4 * skill + 0.2 * fr) * 100


def gap_frame(db_path=None) -> pd.DataFrame:
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        rev = pd.read_sql_query(
            "SELECT country_iso, country_name, domain, volume_ord, skill_level, "
            "frontier FROM cells WHERE source='gemini_research'", conn)
        amb = pd.read_sql_query(
            "SELECT country_iso, domain, ambition, target_level, horizon, "
            "confidence AS amb_confidence FROM ambition", conn)
    finally:
        conn.close()
    if rev.empty:
        return pd.DataFrame()
    rev["revealed"] = rev.apply(_capability, axis=1)
    df = rev.merge(amb, on=["country_iso", "domain"], how="left")
    df["ambition"] = df["ambition"].fillna(0)
    df["target_level"] = df["target_level"].fillna(0)
    df["ambition_score"] = (df["ambition"] / 5.0) * 100
    df["gap"] = df["ambition_score"] - df["revealed"]
    df["domain_label"] = df["domain"].map(taxonomy.DOMAIN_LABELS).fillna(df["domain"])
    return df


def has_ambition(db_path=None) -> bool:
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        n = conn.execute("SELECT COUNT(*) FROM ambition").fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    finally:
        conn.close()
    return n > 0
