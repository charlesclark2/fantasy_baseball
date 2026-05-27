"""
fit_park_priors.py — Empirical Bayes park run factor smoothing (Epic 3A.1)

Fits a Normal-Normal conjugate EB model over venue-level run environments and
writes smoothed park run factors to baseball_data.betting.eb_park_factors_raw.

The prior μ₀, σ₀² is fit from established venues (≥ 40 games/season). For
every (venue_id, season) row in mart_park_run_factors the posterior mean
replaces the raw 3yr average, with shrinkage proportional to sample size:

    shrinkage = (σ²_game / n) / (σ₀² + σ²_game / n)
    μ_post    = (1 - shrinkage) × x̄ + shrinkage × μ₀

This eliminates league-mean null imputation for low-sample venues: even a
venue with n=21 games gets a principled estimate rather than a global mean.

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_park_priors.py
    uv run python betting_ml/scripts/eb_priors/fit_park_priors.py --season 2025
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

# Venues must have at least this many games/season to contribute to prior fitting.
# Excludes COVID-shortened seasons, neutral-site games, and first-year venues.
_PRIOR_FIT_MIN_GAMES = 40


def _compute_game_variance(conn) -> float:
    """Variance of total runs per game across all regular-season completed games."""
    cur = conn.cursor()
    cur.execute(
        "SELECT variance(home_final_score + away_final_score) "
        "FROM baseball_data.betting.mart_game_results "
        "WHERE game_type = 'R' "
        "  AND home_final_score IS NOT NULL "
        "  AND away_final_score IS NOT NULL"
    )
    val = cur.fetchone()[0]
    cur.close()
    return float(val)


def _load_park_factors(conn, season: int) -> list[dict]:
    """Load park factors with 3yr cumulative game counts through `season`.

    n_games_3yr is the sum of game_count over the 3yr rolling window, matching
    the denominator used to compute park_run_factor_3yr.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            venue_id,
            venue_name,
            game_year,
            game_count,
            runs_per_game_at_park,
            park_run_factor_3yr,
            SUM(game_count) OVER (
                PARTITION BY venue_id
                ORDER BY game_year
                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            ) AS n_games_3yr
        FROM baseball_data.betting.mart_park_run_factors
        WHERE game_year <= %(season)s
        ORDER BY venue_id, game_year
        """,
        {"season": season},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _fit_prior(rows: list[dict]) -> tuple[float, float]:
    """Fit cross-park Normal prior μ₀, σ₀² from established venues."""
    vals = [
        float(r["park_run_factor_3yr"])
        for r in rows
        if r["game_count"] is not None
        and int(r["game_count"]) >= _PRIOR_FIT_MIN_GAMES
        and r["park_run_factor_3yr"] is not None
    ]
    if not vals:
        raise ValueError("No qualifying venues found for prior fitting.")
    μ0 = float(np.mean(vals))
    σ0_sq = float(np.var(vals, ddof=1))
    return μ0, σ0_sq


def _compute_posteriors(
    rows: list[dict],
    μ0: float,
    σ0_sq: float,
    σ_game_sq: float,
) -> list[dict]:
    """Compute EB posterior for every (venue_id, season) row."""
    results = []
    for r in rows:
        n = int(r["n_games_3yr"]) if r["n_games_3yr"] is not None else 0
        x_bar = float(r["park_run_factor_3yr"]) if r["park_run_factor_3yr"] is not None else None

        if n == 0 or x_bar is None:
            # No observations: posterior collapses to prior
            μ_post = μ0
            shrinkage = 1.0
            posterior_var = σ0_sq
        else:
            se_sq = σ_game_sq / n
            shrinkage = se_sq / (σ0_sq + se_sq)
            μ_post = (1.0 - shrinkage) * x_bar + shrinkage * μ0
            posterior_var = 1.0 / (1.0 / σ0_sq + n / σ_game_sq)

        results.append({
            "venue_id":                       int(r["venue_id"]),
            "season":                         int(r["game_year"]),
            "eb_park_run_factor":             round(μ_post, 4),
            "eb_park_run_factor_uncertainty": round(float(np.sqrt(posterior_var)), 4),
            "n_games":                        n,
            "raw_park_run_factor":            round(x_bar, 4) if x_bar is not None else round(μ0, 4),
            "shrinkage_factor":               round(shrinkage, 4),
            "prior_mean":                     round(μ0, 4),
            "prior_variance":                 round(σ0_sq, 4),
        })
    return results


def _write_to_snowflake(conn, rows: list[dict], fit_date: date, run_id: str) -> None:
    """MERGE results into eb_park_factors_raw via VARCHAR temp table."""
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TEMPORARY TABLE baseball_data.betting.tmp_eb_park_factors (
            venue_id                          VARCHAR,
            season                            VARCHAR,
            eb_park_run_factor                VARCHAR,
            eb_park_run_factor_uncertainty    VARCHAR,
            n_games                           VARCHAR,
            raw_park_run_factor               VARCHAR,
            shrinkage_factor                  VARCHAR,
            prior_mean                        VARCHAR,
            prior_variance                    VARCHAR,
            fit_date                          VARCHAR,
            run_id                            VARCHAR
        )
        """
    )

    data = [
        (
            str(r["venue_id"]),
            str(r["season"]),
            str(r["eb_park_run_factor"]),
            str(r["eb_park_run_factor_uncertainty"]),
            str(r["n_games"]),
            str(r["raw_park_run_factor"]),
            str(r["shrinkage_factor"]),
            str(r["prior_mean"]),
            str(r["prior_variance"]),
            fit_date.isoformat(),
            run_id,
        )
        for r in rows
    ]
    cur.executemany(
        "INSERT INTO baseball_data.betting.tmp_eb_park_factors VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        data,
    )

    cur.execute(
        """
        MERGE INTO baseball_data.betting.eb_park_factors_raw tgt
        USING (
            SELECT
                venue_id::INTEGER                     AS venue_id,
                season::INTEGER                       AS season,
                eb_park_run_factor::FLOAT             AS eb_park_run_factor,
                eb_park_run_factor_uncertainty::FLOAT AS eb_park_run_factor_uncertainty,
                n_games::INTEGER                      AS n_games,
                raw_park_run_factor::FLOAT            AS raw_park_run_factor,
                shrinkage_factor::FLOAT               AS shrinkage_factor,
                prior_mean::FLOAT                     AS prior_mean,
                prior_variance::FLOAT                 AS prior_variance,
                fit_date::DATE                        AS fit_date,
                run_id::VARCHAR                       AS run_id
            FROM baseball_data.betting.tmp_eb_park_factors
        ) src ON tgt.venue_id = src.venue_id AND tgt.season = src.season
        WHEN MATCHED THEN UPDATE SET
            eb_park_run_factor            = src.eb_park_run_factor,
            eb_park_run_factor_uncertainty = src.eb_park_run_factor_uncertainty,
            n_games                       = src.n_games,
            raw_park_run_factor           = src.raw_park_run_factor,
            shrinkage_factor              = src.shrinkage_factor,
            prior_mean                    = src.prior_mean,
            prior_variance                = src.prior_variance,
            fit_date                      = src.fit_date,
            run_id                        = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            venue_id, season, eb_park_run_factor, eb_park_run_factor_uncertainty,
            n_games, raw_park_run_factor, shrinkage_factor, prior_mean, prior_variance,
            fit_date, run_id
        ) VALUES (
            src.venue_id, src.season, src.eb_park_run_factor,
            src.eb_park_run_factor_uncertainty, src.n_games, src.raw_park_run_factor,
            src.shrinkage_factor, src.prior_mean, src.prior_variance,
            src.fit_date, src.run_id
        )
        """
    )
    cur.close()


def main(season: int) -> None:
    conn = get_snowflake_connection()
    try:
        print("Computing within-game run variance...")
        σ_game_sq = _compute_game_variance(conn)
        print(f"  σ²_game = {σ_game_sq:.4f}")

        print(f"Loading park factors through season {season}...")
        rows = _load_park_factors(conn, season)
        print(f"  {len(rows)} venue-season rows")

        print("Fitting cross-park prior...")
        μ0, σ0_sq = _fit_prior(rows)
        print(f"  μ₀ = {μ0:.4f}, σ₀² = {σ0_sq:.4f}")

        print("Computing EB posteriors...")
        results = _compute_posteriors(rows, μ0, σ0_sq, σ_game_sq)

        print("Sample shrinkage values:")
        for r in sorted(results, key=lambda x: x["n_games"]):
            if r["n_games"] <= 25 or r["n_games"] >= 200:
                print(
                    f"  n={r['n_games']:3d}  shrinkage={r['shrinkage_factor']:.4f}  "
                    f"raw={r['raw_park_run_factor']:.3f} → eb={r['eb_park_run_factor']:.3f}"
                )

        fit_date = date.today()
        run_id = str(uuid.uuid4())
        print(f"Writing {len(results)} rows (fit_date={fit_date}, run_id={run_id[:8]}...)...")
        _write_to_snowflake(conn, results, fit_date, run_id)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fit EB park run factor priors and write to Snowflake")
    parser.add_argument(
        "--season",
        type=int,
        default=date.today().year,
        help="Most recent season to include in the fit (default: current year)",
    )
    args = parser.parse_args()
    main(args.season)
