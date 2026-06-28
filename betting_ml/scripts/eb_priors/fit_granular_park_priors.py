"""
fit_granular_park_priors.py — Epic 3A.2

Empirical Bayes smoothing for granular park factors (HR, 2B/3B, 1B, BB, SO,
wOBA). Reads from baseball_data.fangraphs.savant_park_factors_raw and writes
EB-smoothed posteriors to baseball_data.betting.eb_park_factors_granular_raw.

Prior structure: Normal-Normal conjugate, same as fit_park_priors.py (3A.1).
  - Prior μ₀, σ₀² fit from cross-venue distribution of the 3yr rolling factor.
  - Likelihood precision: σ²_ε / n_pa, where σ²_ε is the per-PA within-venue
    variance for each event type (derived from Bernoulli approximation).
  - Shrinkage = (σ²_ε/n_pa) / (σ₀² + σ²_ε/n_pa)

Per-event σ²_ε (Bernoulli variance (1−p)/p at typical MLB base rates):
  HR:            30.25  (p ≈ 3.2%)
  Doubles+Trips: 15.67  (p ≈ 6.0%)
  Singles:        5.67  (p ≈ 15.0%)
  BB:            10.90  (p ≈ 8.4%)
  SO:             3.44  (p ≈ 22.5%)

Venues with n_pa < _PRIOR_FIT_MIN_PA are shrunk toward prior more aggressively.
New stadiums or neutral-site venues converge to league-mean by design.

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_granular_park_priors.py
    uv run python betting_ml/scripts/eb_priors/fit_granular_park_priors.py --season 2025
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_PRIOR_FIT_MIN_PA = 5_000     # venues with < 5k PAs excluded from prior fit
_OUTPUT_TABLE     = "baseball_data.betting.eb_park_factors_granular_raw"

# ── E11.1-W4 lakehouse: build-on-DuckDB I/O ───────────────────────────────────
# `--s3` mode reads savant_park_factors_raw from the S3 parquet (exported by
# scripts/export_w4_raw_to_s3.py) and writes the EB posteriors to S3 parquet,
# so the BUILD runs on DuckDB with NO Snowflake compute (the numpy EB math is
# unchanged → value-identical). The Snowflake MERGE path below is retained for
# rollback. The mart_park_factors_granular duckdb branch reads the output parquet
# via read_parquet(lakehouse_loc("eb_park_factors_granular_raw")).
_S3_BUCKET = "baseball-betting-ml-artifacts"
_LAKEHOUSE = f"s3://{_S3_BUCKET}/baseball/lakehouse"
_S3_INPUT  = f"{_LAKEHOUSE}/savant_park_factors_raw/**/*.parquet"
_S3_OUTPUT = f"{_LAKEHOUSE}/eb_park_factors_granular_raw/data.parquet"

# Output column order — matches eb_park_factors_granular_raw (scripts/ddl/eb_park_factors_granular_raw.sql)
# so the generated external table + the mart's reads line up.
_OUTPUT_COLS = [
    "venue_id", "season", "n_pa",
    "raw_hr_factor", "raw_doubles_triples_factor", "raw_singles_factor",
    "raw_bb_factor", "raw_so_factor", "raw_woba_factor",
    "eb_hr_factor", "eb_doubles_triples_factor", "eb_singles_factor",
    "eb_bb_factor", "eb_so_factor", "eb_woba_factor",
    "shrinkage_hr", "shrinkage_doubles_triples", "shrinkage_singles",
    "shrinkage_bb", "shrinkage_so",
    "prior_mean_hr", "prior_variance_hr",
    "prior_mean_doubles_triples", "prior_variance_doubles_triples",
    "fit_date", "run_id",
]


def _get_duckdb():
    """DuckDB connection with S3 credential-chain auth (mirrors run_w1_lakehouse.py)."""
    import duckdb
    duck = duckdb.connect()
    duck.execute("INSTALL httpfs; LOAD httpfs")
    duck.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    return duck


def _load_savant_s3(duck, season: int) -> list[dict]:
    """S3/DuckDB analogue of _load_savant — same projection, filter, and order."""
    cur = duck.execute(
        f"""
        SELECT venue_id, venue_name, season, n_pa,
               index_runs, index_hr, index_1b, index_2b, index_3b,
               index_bb, index_so, index_woba
        FROM read_parquet('{_S3_INPUT}', union_by_name=true)
        WHERE season = {int(season)}
          AND bat_side = 'All'
          AND num_years_rolling = 3
        ORDER BY venue_id
        """
    )
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _write_s3(duck, rows: list[dict]) -> int:
    """Write all-season posteriors to S3 parquet (full rebuild; replaces the
    per-season MERGE). value-identical content — the EB math is unchanged."""
    if not rows:
        print("  no rows to write — skipping S3 write")
        return 0
    import pandas as pd
    df = pd.DataFrame(rows, columns=_OUTPUT_COLS)
    duck.register("_eb_granular_out", df)
    duck.execute(f"COPY _eb_granular_out TO '{_S3_OUTPUT}' (FORMAT PARQUET)")
    print(f"  wrote {len(df):,} rows → {_S3_OUTPUT}")
    return len(df)

# Per-event Bernoulli within-venue variance: (1 - p_event) / p_event
_SIGMA_SQ_HR    = 30.25   # p ≈ 3.2%
_SIGMA_SQ_D3    = 15.67   # p ≈ 6.0%  (doubles + triples combined)
_SIGMA_SQ_1B    = 5.67    # p ≈ 15.0%
_SIGMA_SQ_BB    = 10.90   # p ≈ 8.4%
_SIGMA_SQ_SO    = 3.44    # p ≈ 22.5%
_SIGMA_SQ_WOBA  = 10.0    # wOBA: composite, use conservative estimate

# Maps factor name → (raw_ratio_col, sigma_sq)
_FACTORS: dict[str, tuple[str, float]] = {
    "hr":             ("raw_hr_factor",             _SIGMA_SQ_HR),
    "doubles_triples":("raw_doubles_triples_factor", _SIGMA_SQ_D3),
    "singles":        ("raw_singles_factor",          _SIGMA_SQ_1B),
    "bb":             ("raw_bb_factor",               _SIGMA_SQ_BB),
    "so":             ("raw_so_factor",               _SIGMA_SQ_SO),
}


def _load_savant(conn, season: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            venue_id,
            venue_name,
            season,
            n_pa,
            index_runs,
            index_hr,
            index_1b,
            index_2b,
            index_3b,
            index_bb,
            index_so,
            index_woba
        FROM baseball_data.fangraphs.savant_park_factors_raw
        WHERE season = %(season)s
          AND bat_side = 'All'
          AND num_years_rolling = 3
        ORDER BY venue_id
        """,
        {"season": season},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _to_ratio(index_val) -> float | None:
    """Convert Savant index (100 = avg) to ratio (1.0 = avg)."""
    if index_val is None:
        return None
    return float(index_val) / 100.0


def _prep_factors(rows: list[dict]) -> list[dict]:
    """Add ratio columns for each factor."""
    prepped = []
    for r in rows:
        n_pa = int(r["n_pa"]) if r["n_pa"] is not None else 0
        # doubles_triples: combine using the geometric mean of 2B and 3B indices
        idx_2b = r.get("index_2b")
        idx_3b = r.get("index_3b")
        if idx_2b is not None and idx_3b is not None:
            d3_ratio = (float(idx_2b) * float(idx_3b)) ** 0.5 / 100.0
        elif idx_2b is not None:
            d3_ratio = float(idx_2b) / 100.0
        elif idx_3b is not None:
            d3_ratio = float(idx_3b) / 100.0
        else:
            d3_ratio = None

        prepped.append({
            "venue_id":                    int(r["venue_id"]),
            "venue_name":                  str(r.get("venue_name", "")),
            "season":                      int(r["season"]),
            "n_pa":                        n_pa,
            "raw_hr_factor":               _to_ratio(r.get("index_hr")),
            "raw_doubles_triples_factor":  d3_ratio,
            "raw_singles_factor":          _to_ratio(r.get("index_1b")),
            "raw_bb_factor":               _to_ratio(r.get("index_bb")),
            "raw_so_factor":               _to_ratio(r.get("index_so")),
            "raw_woba_factor":             _to_ratio(r.get("index_woba")),
        })
    return prepped


def _fit_prior(prepped: list[dict], col: str) -> tuple[float, float]:
    """Fit cross-venue Normal prior μ₀, σ₀² from established venues."""
    vals = [
        float(r[col])
        for r in prepped
        if r["n_pa"] >= _PRIOR_FIT_MIN_PA and r[col] is not None
    ]
    if not vals:
        raise ValueError(f"No qualifying venues for prior fitting on {col}")
    μ0 = float(np.mean(vals))
    σ0_sq = float(np.var(vals, ddof=1))
    return μ0, σ0_sq


def _shrink(x_bar: float | None, n_pa: int, μ0: float, σ0_sq: float, σ_e_sq: float) -> tuple[float, float]:
    """Compute EB posterior mean and shrinkage factor."""
    if x_bar is None or n_pa == 0:
        return μ0, 1.0
    se_sq = σ_e_sq / n_pa
    shrinkage = se_sq / (σ0_sq + se_sq)
    μ_post = (1.0 - shrinkage) * x_bar + shrinkage * μ0
    return float(μ_post), float(shrinkage)


def _compute_posteriors(prepped: list[dict]) -> list[dict]:
    # Fit priors for each factor
    priors: dict[str, tuple[float, float]] = {}
    for name, (col, _) in _FACTORS.items():
        try:
            μ0, σ0_sq = _fit_prior(prepped, col)
            priors[name] = (μ0, σ0_sq)
            print(f"  Prior [{name}]: μ₀={μ0:.4f}  σ₀={σ0_sq**0.5:.4f}")
        except ValueError as exc:
            print(f"  WARNING: {exc}; using defaults μ₀=1.0 σ₀²=0.005")
            priors[name] = (1.0, 0.005)

    # wOBA prior (not in _FACTORS loop, handled separately)
    try:
        μ0_woba, σ0_sq_woba = _fit_prior(prepped, "raw_woba_factor")
    except ValueError:
        μ0_woba, σ0_sq_woba = 1.0, 0.003

    results = []
    for r in prepped:
        n = r["n_pa"]
        row: dict = {
            "venue_id":                   r["venue_id"],
            "season":                     r["season"],
            "n_pa":                       n,
            "raw_hr_factor":              r["raw_hr_factor"],
            "raw_doubles_triples_factor": r["raw_doubles_triples_factor"],
            "raw_singles_factor":         r["raw_singles_factor"],
            "raw_bb_factor":              r["raw_bb_factor"],
            "raw_so_factor":              r["raw_so_factor"],
            "raw_woba_factor":            r["raw_woba_factor"],
        }

        for name, (col, σ_e_sq) in _FACTORS.items():
            μ0, σ0_sq = priors[name]
            eb_val, shrinkage = _shrink(r[col], n, μ0, σ0_sq, σ_e_sq)
            row[f"eb_{name}_factor"] = round(eb_val, 4)
            row[f"shrinkage_{name}"] = round(shrinkage, 4)

        # wOBA
        eb_woba, _ = _shrink(r["raw_woba_factor"], n, μ0_woba, σ0_sq_woba, _SIGMA_SQ_WOBA)
        row["eb_woba_factor"] = round(eb_woba, 4)

        # Prior params for auditability (use HR as representative)
        row["prior_mean_hr"]                  = round(priors["hr"][0], 4)
        row["prior_variance_hr"]              = round(priors["hr"][1], 6)
        row["prior_mean_doubles_triples"]     = round(priors["doubles_triples"][0], 4)
        row["prior_variance_doubles_triples"] = round(priors["doubles_triples"][1], 6)

        results.append(row)

    return results


def _upsert(rows: list[dict], conn, run_id: str, fit_date: date) -> int:
    """MERGE results into eb_park_factors_granular_raw via VARCHAR temp table."""
    if not rows:
        return 0
    cur = conn.cursor()

    cur.execute("""
        CREATE TEMPORARY TABLE IF NOT EXISTS _tmp_eb_granular (
            venue_id                            VARCHAR,
            season                              VARCHAR,
            n_pa                                VARCHAR,
            raw_hr_factor                       VARCHAR,
            raw_doubles_triples_factor          VARCHAR,
            raw_singles_factor                  VARCHAR,
            raw_bb_factor                       VARCHAR,
            raw_so_factor                       VARCHAR,
            raw_woba_factor                     VARCHAR,
            eb_hr_factor                        VARCHAR,
            eb_doubles_triples_factor           VARCHAR,
            eb_singles_factor                   VARCHAR,
            eb_bb_factor                        VARCHAR,
            eb_so_factor                        VARCHAR,
            eb_woba_factor                      VARCHAR,
            shrinkage_hr                        VARCHAR,
            shrinkage_doubles_triples           VARCHAR,
            shrinkage_singles                   VARCHAR,
            shrinkage_bb                        VARCHAR,
            shrinkage_so                        VARCHAR,
            prior_mean_hr                       VARCHAR,
            prior_variance_hr                   VARCHAR,
            prior_mean_doubles_triples          VARCHAR,
            prior_variance_doubles_triples      VARCHAR,
            fit_date                            VARCHAR,
            run_id                              VARCHAR
        )
    """)
    cur.execute("TRUNCATE TABLE _tmp_eb_granular")

    def _s(v) -> str | None:
        return str(v) if v is not None else None

    for r in rows:
        cur.execute(
            """
            INSERT INTO _tmp_eb_granular VALUES (
                %(venue_id)s, %(season)s, %(n_pa)s,
                %(raw_hr_factor)s, %(raw_doubles_triples_factor)s,
                %(raw_singles_factor)s, %(raw_bb_factor)s, %(raw_so_factor)s,
                %(raw_woba_factor)s,
                %(eb_hr_factor)s, %(eb_doubles_triples_factor)s,
                %(eb_singles_factor)s, %(eb_bb_factor)s, %(eb_so_factor)s,
                %(eb_woba_factor)s,
                %(shrinkage_hr)s, %(shrinkage_doubles_triples)s,
                %(shrinkage_singles)s, %(shrinkage_bb)s, %(shrinkage_so)s,
                %(prior_mean_hr)s, %(prior_variance_hr)s,
                %(prior_mean_doubles_triples)s, %(prior_variance_doubles_triples)s,
                %(fit_date)s, %(run_id)s
            )
            """,
            {k: _s(v) for k, v in {
                **r,
                "fit_date": fit_date.isoformat(),
                "run_id":   run_id,
            }.items()},
        )

    cur.execute(f"""
        MERGE INTO {_OUTPUT_TABLE} AS tgt
        USING (
            SELECT
                TRY_CAST(venue_id AS INTEGER)                   AS venue_id,
                TRY_CAST(season AS INTEGER)                     AS season,
                TRY_CAST(n_pa AS INTEGER)                       AS n_pa,
                TRY_CAST(raw_hr_factor AS FLOAT)                AS raw_hr_factor,
                TRY_CAST(raw_doubles_triples_factor AS FLOAT)   AS raw_doubles_triples_factor,
                TRY_CAST(raw_singles_factor AS FLOAT)           AS raw_singles_factor,
                TRY_CAST(raw_bb_factor AS FLOAT)                AS raw_bb_factor,
                TRY_CAST(raw_so_factor AS FLOAT)                AS raw_so_factor,
                TRY_CAST(raw_woba_factor AS FLOAT)              AS raw_woba_factor,
                TRY_CAST(eb_hr_factor AS FLOAT)                 AS eb_hr_factor,
                TRY_CAST(eb_doubles_triples_factor AS FLOAT)    AS eb_doubles_triples_factor,
                TRY_CAST(eb_singles_factor AS FLOAT)            AS eb_singles_factor,
                TRY_CAST(eb_bb_factor AS FLOAT)                 AS eb_bb_factor,
                TRY_CAST(eb_so_factor AS FLOAT)                 AS eb_so_factor,
                TRY_CAST(eb_woba_factor AS FLOAT)               AS eb_woba_factor,
                TRY_CAST(shrinkage_hr AS FLOAT)                 AS shrinkage_hr,
                TRY_CAST(shrinkage_doubles_triples AS FLOAT)    AS shrinkage_doubles_triples,
                TRY_CAST(shrinkage_singles AS FLOAT)            AS shrinkage_singles,
                TRY_CAST(shrinkage_bb AS FLOAT)                 AS shrinkage_bb,
                TRY_CAST(shrinkage_so AS FLOAT)                 AS shrinkage_so,
                TRY_CAST(prior_mean_hr AS FLOAT)                AS prior_mean_hr,
                TRY_CAST(prior_variance_hr AS FLOAT)            AS prior_variance_hr,
                TRY_CAST(prior_mean_doubles_triples AS FLOAT)   AS prior_mean_doubles_triples,
                TRY_CAST(prior_variance_doubles_triples AS FLOAT) AS prior_variance_doubles_triples,
                TRY_CAST(fit_date AS DATE)                      AS fit_date,
                run_id
            FROM _tmp_eb_granular
        ) AS src
        ON tgt.venue_id = src.venue_id AND tgt.season = src.season
        WHEN MATCHED THEN UPDATE SET
            n_pa                            = src.n_pa,
            raw_hr_factor                   = src.raw_hr_factor,
            raw_doubles_triples_factor      = src.raw_doubles_triples_factor,
            raw_singles_factor              = src.raw_singles_factor,
            raw_bb_factor                   = src.raw_bb_factor,
            raw_so_factor                   = src.raw_so_factor,
            raw_woba_factor                 = src.raw_woba_factor,
            eb_hr_factor                    = src.eb_hr_factor,
            eb_doubles_triples_factor       = src.eb_doubles_triples_factor,
            eb_singles_factor               = src.eb_singles_factor,
            eb_bb_factor                    = src.eb_bb_factor,
            eb_so_factor                    = src.eb_so_factor,
            eb_woba_factor                  = src.eb_woba_factor,
            shrinkage_hr                    = src.shrinkage_hr,
            shrinkage_doubles_triples       = src.shrinkage_doubles_triples,
            shrinkage_singles               = src.shrinkage_singles,
            shrinkage_bb                    = src.shrinkage_bb,
            shrinkage_so                    = src.shrinkage_so,
            prior_mean_hr                   = src.prior_mean_hr,
            prior_variance_hr               = src.prior_variance_hr,
            prior_mean_doubles_triples      = src.prior_mean_doubles_triples,
            prior_variance_doubles_triples  = src.prior_variance_doubles_triples,
            fit_date                        = src.fit_date,
            run_id                          = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            venue_id, season, n_pa,
            raw_hr_factor, raw_doubles_triples_factor, raw_singles_factor,
            raw_bb_factor, raw_so_factor, raw_woba_factor,
            eb_hr_factor, eb_doubles_triples_factor, eb_singles_factor,
            eb_bb_factor, eb_so_factor, eb_woba_factor,
            shrinkage_hr, shrinkage_doubles_triples, shrinkage_singles,
            shrinkage_bb, shrinkage_so,
            prior_mean_hr, prior_variance_hr,
            prior_mean_doubles_triples, prior_variance_doubles_triples,
            fit_date, run_id
        ) VALUES (
            src.venue_id, src.season, src.n_pa,
            src.raw_hr_factor, src.raw_doubles_triples_factor, src.raw_singles_factor,
            src.raw_bb_factor, src.raw_so_factor, src.raw_woba_factor,
            src.eb_hr_factor, src.eb_doubles_triples_factor, src.eb_singles_factor,
            src.eb_bb_factor, src.eb_so_factor, src.eb_woba_factor,
            src.shrinkage_hr, src.shrinkage_doubles_triples, src.shrinkage_singles,
            src.shrinkage_bb, src.shrinkage_so,
            src.prior_mean_hr, src.prior_variance_hr,
            src.prior_mean_doubles_triples, src.prior_variance_doubles_triples,
            src.fit_date, src.run_id
        )
    """)
    return cur.rowcount


def fit_season(conn, season: int) -> int:
    print(f"\nFitting granular park priors for season={season}")
    rows = _load_savant(conn, season)
    if not rows:
        print(f"  No Savant data for season={season}; skipping")
        return 0

    prepped = _prep_factors(rows)
    posteriors = _compute_posteriors(prepped)

    # Spot-check Coors
    coors = next((r for r in posteriors if r["venue_id"] == 19), None)
    if coors:
        print(f"  Coors Field: n_pa={coors['n_pa']:,}  "
              f"eb_hr={coors['eb_hr_factor']:.3f}  shrinkage_hr={coors['shrinkage_hr']:.3f}  "
              f"eb_d3={coors['eb_doubles_triples_factor']:.3f}")

    run_id = str(uuid.uuid4())
    upserted = _upsert(posteriors, conn, run_id, date.today())
    print(f"  Upserted {upserted} rows for season={season}")
    return upserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit EB granular park factor priors and write posteriors to Snowflake"
    )
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--start-season", type=int, default=None)
    parser.add_argument("--end-season", type=int, default=None)
    parser.add_argument(
        "--s3", action="store_true",
        help="E11.1-W4: build on DuckDB — read savant_park_factors_raw from S3 parquet "
             "and write eb_park_factors_granular_raw posteriors to S3 parquet (no Snowflake).",
    )
    args = parser.parse_args()

    current_year = date.today().year
    if args.start_season:
        seasons = list(range(args.start_season, (args.end_season or current_year) + 1))
    elif args.season:
        seasons = [args.season]
    else:
        seasons = [current_year]

    if args.s3:
        # E11.1-W4 build-on-DuckDB: read S3 → compute (unchanged numpy) → write S3 parquet.
        # FULL rebuild across the requested seasons (replaces the per-season MERGE upsert):
        # the mart reads all rows, so write one parquet holding every season fit this run.
        duck = _get_duckdb()
        run_id = str(uuid.uuid4())
        fit_date = date.today()
        all_rows: list[dict] = []
        for s in seasons:
            print(f"\nFitting granular park priors (S3) for season={s}")
            rows = _load_savant_s3(duck, s)
            if not rows:
                print(f"  No Savant data for season={s}; skipping")
                continue
            posteriors = _compute_posteriors(_prep_factors(rows))
            for r in posteriors:
                r["fit_date"] = fit_date.isoformat()
                r["run_id"] = run_id
            all_rows.extend(posteriors)
            print(f"  computed {len(posteriors)} venue rows for season={s}")
        total = _write_s3(duck, all_rows)
        duck.close()
        print(f"\nDone (S3). {total} total rows written across {len(seasons)} season(s).")
        return

    conn = get_snowflake_connection(schema="betting")
    try:
        total = 0
        for s in seasons:
            total += fit_season(conn, s)
        print(f"\nDone. {total} total rows upserted across {len(seasons)} season(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
