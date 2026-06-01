"""SQLite store for the country x domain capability panel.

One row = one country's standing in one domain, from one source, as of a date.
Sources are kept distinct (gemini_research vs ats vs official) and never blended
silently — the dashboard chooses/labels. Idempotent upsert.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import taxonomy

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "jobs.db"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "research").mkdir(exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cells (
    country_iso     TEXT NOT NULL,
    country_name    TEXT,
    domain          TEXT NOT NULL,
    volume_band     TEXT,           -- key from taxonomy.VOLUME_BANDS
    volume_ord      INTEGER,        -- 0..5 ordinal for charting
    volume_estimate TEXT,           -- optional free-text range
    skill_level     INTEGER,        -- 1..5 typical complexity tier
    frontier        REAL,           -- 0..1: presence of tier-5 frontier R&D
    rationale       TEXT,
    evidence        TEXT,           -- JSON array of short source descriptors
    confidence      TEXT,           -- low|medium|high
    precision       TEXT,           -- band|partial_count|counted
    source          TEXT NOT NULL,  -- gemini_research|ats|official
    as_of           TEXT,           -- ISO date
    PRIMARY KEY (country_iso, domain, source)
);
CREATE INDEX IF NOT EXISTS idx_cells_domain  ON cells(domain);
CREATE INDEX IF NOT EXISTS idx_cells_country ON cells(country_iso);

CREATE TABLE IF NOT EXISTS ambition (
    country_iso     TEXT NOT NULL,
    country_name    TEXT,
    domain          TEXT NOT NULL,
    ambition        INTEGER,        -- 0..5 strength of national strategic intent
    target_level    INTEGER,        -- 1..5 skill/complexity tier the country aims for
    horizon         TEXT,           -- short|medium|long
    rationale       TEXT,
    evidence        TEXT,           -- JSON array: strategies, programmes, budgets
    confidence      TEXT,
    as_of           TEXT,
    PRIMARY KEY (country_iso, domain)
);
CREATE INDEX IF NOT EXISTS idx_amb_domain ON ambition(domain);

-- Longitudinal history (Phase 7): one row per (snapshot_date, country, domain,
-- source). `cells` always holds the LATEST; this table accumulates every run so
-- we can diff capability over time. Re-running on the same date overwrites that
-- date's snapshot (idempotent), so a weekly cron yields one point per week.
CREATE TABLE IF NOT EXISTS cell_history (
    snapshot_date   TEXT NOT NULL,
    country_iso     TEXT NOT NULL,
    country_name    TEXT,
    domain          TEXT NOT NULL,
    volume_ord      INTEGER,
    skill_level     INTEGER,
    frontier        REAL,
    capability      REAL,           -- precomputed 0..100 for easy trend charts
    source          TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, country_iso, domain, source)
);
CREATE INDEX IF NOT EXISTS idx_hist_date ON cell_history(snapshot_date);

-- Cross-border MNC footprint (the division-of-labour map). One row per
-- (employer, country, function): how many open roles an MNC runs of a given
-- value-chain function in a given country. Reveals e.g. R&D in US, eng in IN,
-- manufacturing/test in MY for the same parent.
CREATE TABLE IF NOT EXISTS footprint (
    employer    TEXT NOT NULL,
    sector      TEXT,
    country_iso TEXT NOT NULL,
    function    TEXT NOT NULL,
    domain      TEXT,
    n_roles     INTEGER,
    as_of       TEXT,
    PRIMARY KEY (employer, country_iso, function)
);
CREATE INDEX IF NOT EXISTS idx_fp_employer ON footprint(employer);
CREATE INDEX IF NOT EXISTS idx_fp_country  ON footprint(country_iso);

-- Patent time-series (one row per country × domain × year). The `cells` table
-- (source='patents') holds only the latest year; this keeps the full history so
-- the dashboard can chart invention momentum. Re-running a year overwrites it.
CREATE TABLE IF NOT EXISTS patent_trend (
    country_iso  TEXT NOT NULL,
    country_name TEXT,
    domain       TEXT NOT NULL,
    year         INTEGER NOT NULL,
    n_patents    INTEGER,
    PRIMARY KEY (country_iso, domain, year)
);
CREATE INDEX IF NOT EXISTS idx_pt_year ON patent_trend(year);
"""

_COLS = [
    "country_iso", "country_name", "domain", "volume_band", "volume_ord",
    "volume_estimate", "skill_level", "frontier", "rationale", "evidence",
    "confidence", "precision", "source", "as_of",
]


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DB_PATH
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_cell(self, cell: dict) -> None:
        row = dict(cell)
        if isinstance(row.get("evidence"), (list, dict)):
            row["evidence"] = json.dumps(row["evidence"])
        # derive volume_ord from band if not supplied
        if row.get("volume_ord") is None and row.get("volume_band"):
            row["volume_ord"] = taxonomy.VOLUME_KEY_TO_ORD.get(row["volume_band"])
        vals = [row.get(c) for c in _COLS]
        ph = ",".join("?" for _ in _COLS)
        upd = ",".join(f"{c}=excluded.{c}" for c in _COLS
                       if c not in ("country_iso", "domain", "source"))
        self.conn.execute(
            f"INSERT INTO cells ({','.join(_COLS)}) VALUES ({ph}) "
            f"ON CONFLICT(country_iso, domain, source) DO UPDATE SET {upd}",
            vals,
        )

    def upsert_many(self, cells: list[dict]) -> int:
        for c in cells:
            self.upsert_cell(c)
        self.conn.commit()
        return len(cells)

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM cells").fetchone()[0]

    # ---- ambition layer (Phase 6) ----
    def upsert_ambition(self, a: dict) -> None:
        row = dict(a)
        if isinstance(row.get("evidence"), (list, dict)):
            row["evidence"] = json.dumps(row["evidence"])
        cols = ["country_iso", "country_name", "domain", "ambition",
                "target_level", "horizon", "rationale", "evidence",
                "confidence", "as_of"]
        vals = [row.get(c) for c in cols]
        ph = ",".join("?" for _ in cols)
        upd = ",".join(f"{c}=excluded.{c}" for c in cols
                       if c not in ("country_iso", "domain"))
        self.conn.execute(
            f"INSERT INTO ambition ({','.join(cols)}) VALUES ({ph}) "
            f"ON CONFLICT(country_iso, domain) DO UPDATE SET {upd}", vals)

    def upsert_ambitions(self, items: list[dict]) -> int:
        for a in items:
            self.upsert_ambition(a)
        self.conn.commit()
        return len(items)

    def count_ambition(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM ambition").fetchone()[0]

    # ---- patent time-series ----
    def upsert_patent_year(self, rows: list[dict]) -> int:
        cols = ["country_iso", "country_name", "domain", "year", "n_patents"]
        upd = "n_patents=excluded.n_patents, country_name=excluded.country_name"
        for r in rows:
            self.conn.execute(
                f"INSERT INTO patent_trend ({','.join(cols)}) "
                f"VALUES ({','.join('?' for _ in cols)}) "
                f"ON CONFLICT(country_iso, domain, year) DO UPDATE SET {upd}",
                [r.get(c) for c in cols])
        self.conn.commit()
        return len(rows)

    def patent_years(self) -> list[int]:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT year FROM patent_trend ORDER BY year")]

    # ---- cross-border footprint ----
    def replace_footprint(self, rows: list[dict]) -> int:
        """Footprint is a full snapshot each run: clear then insert."""
        self.conn.execute("DELETE FROM footprint")
        cols = ["employer", "sector", "country_iso", "function", "domain",
                "n_roles", "as_of"]
        self.conn.executemany(
            f"INSERT INTO footprint ({','.join(cols)}) "
            f"VALUES ({','.join('?' for _ in cols)})",
            [[r.get(c) for c in cols] for r in rows],
        )
        self.conn.commit()
        return len(rows)

    def count_footprint(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM footprint").fetchone()[0]

    # ---- longitudinal snapshots (Phase 7) ----
    def snapshot(self, snapshot_date: str) -> int:
        """Copy the current `cells` into cell_history under snapshot_date.

        Capability mirrors the dashboard metric: 0.4*quantity + 0.4*skill +
        0.2*frontier, scaled to 0..100. Idempotent per date.
        """
        # delete-then-insert is cleanly idempotent per date and avoids the
        # INSERT...SELECT + ON CONFLICT parse ambiguity in SQLite.
        self.conn.execute("DELETE FROM cell_history WHERE snapshot_date=?",
                          (snapshot_date,))
        self.conn.execute(
            """
            INSERT INTO cell_history
                (snapshot_date, country_iso, country_name, domain, volume_ord,
                 skill_level, frontier, capability, source)
            SELECT ?, country_iso, country_name, domain,
                   volume_ord, skill_level, frontier,
                   ( 0.4 * (COALESCE(volume_ord,0) / 5.0)
                   + 0.4 * (MAX(COALESCE(skill_level,0) - 1, 0) / 4.0)
                   + 0.2 * MIN(MAX(COALESCE(frontier,0.0), 0.0), 1.0) ) * 100.0,
                   source
            FROM cells
            """,
            (snapshot_date,),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT COUNT(*) FROM cell_history WHERE snapshot_date=?",
            (snapshot_date,)).fetchone()[0]

    def snapshot_dates(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT snapshot_date FROM cell_history ORDER BY snapshot_date"
        ).fetchall()
        return [r[0] for r in rows]

    def countries(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT country_iso FROM cells ORDER BY country_iso").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
