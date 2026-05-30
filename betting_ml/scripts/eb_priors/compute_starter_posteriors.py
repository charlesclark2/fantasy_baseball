"""
compute_starter_posteriors.py — Per-starter EB posterior computation (Epic 5A.2)

For each game on a given date, computes per-starter EB posteriors for
xwOBA-against, K%, and BB% using Normal-Normal conjugate shrinkage.

Normal-Normal posterior:
    posterior_mean     = (μ₀/σ₀² + n·x̄/σ_meas²) / (1/σ₀² + n/σ_meas²)
    posterior_variance = 1 / (1/σ₀² + n/σ_meas²)
    where σ_meas² ≈ obs_rate·(1 - obs_rate) / BF  (binomial SE approximation)

IL-return blend rule:
    If current_season_starts < 3 AND prior_season_starts ≥ 10:
        final_estimate = 0.5·current_season_posterior + 0.5·prior_season_observed_rate
        eb_data_source = "il_return_blend"

eb_data_source labels:
    prior_only      — BF = 0; posterior = prior mean
    il_return_blend — sparse current season (< 3 starts) + rich prior season (≥ 10 starts)
    full_eb         — BF > 0, not IL-return case; EB posterior with prior shrinkage

LEAKAGE GUARD: all rolling stats joined with game_date < target game_date (strictly
less than), matching the guard in feature_pregame_starter_features.sql.

Writes to baseball_data.betting.eb_starter_posteriors via VARCHAR temp
table + MERGE on (game_pk, pitcher_id).

Usage:
    uv run python betting_ml/scripts/eb_priors/compute_starter_posteriors.py
    uv run python betting_ml/scripts/eb_priors/compute_starter_posteriors.py --game-date 2025-05-01
    uv run python betting_ml/scripts/eb_priors/compute_starter_posteriors.py --backfill-season 2021
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_PRIORS_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"
_IL_RETURN_CURRENT_STARTS_THRESHOLD = 3
_IL_RETURN_PRIOR_STARTS_THRESHOLD = 10

_METRICS = ("xwoba_against", "k_pct", "bb_pct")


# ── Experience band assignment ────────────────────────────────────────────────
# Labels match fit_starter_priors.py's _EXPERIENCE_BANDS (u25/a25/a30/a33).

def _assign_experience_band(prior_seasons: int) -> str:
    if prior_seasons == 0:
        return "u25"
    if prior_seasons <= 3:
        return "a25"
    if prior_seasons <= 7:
        return "a30"
    return "a33"


# ── Prior loading ─────────────────────────────────────────────────────────────

def _load_prior(season: int) -> dict:
    path = _PRIORS_DIR / f"starter_priors_{season}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Prior file not found: {path}. "
            f"Run fit_starter_priors.py --season {season} first."
        )
    return json.loads(path.read_text())["priors"]


def _get_prior_cell(priors: dict, metric: str, age_band: str | None) -> dict | None:
    """Return the prior cell for (metric, age_band), falling back across bands."""
    metric_priors = priors.get(metric, {})
    if age_band and age_band in metric_priors:
        cell = metric_priors[age_band]
        if cell:
            return cell
    # Fallback: return the first non-null cell (population mean)
    for label in ("u25", "a25", "a30", "a33"):
        cell = metric_priors.get(label)
        if cell:
            return cell
    return None


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_starters(conn, game_date: date) -> list[dict]:
    """Return one row per (game_pk, pitcher_id) for confirmed probable starters."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            game_pk,
            side,
            starter_player_id AS pitcher_id
        FROM baseball_data.betting_features.feature_pregame_starter_status
        WHERE game_date      = %(game_date)s
          AND is_current     = true
          AND starter_player_id IS NOT NULL
        ORDER BY game_pk, side
        """,
        {"game_date": game_date.isoformat()},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _load_current_season_stats(
    conn, pitcher_ids: list[str], game_date: date, season: int
) -> dict[str, dict]:
    """
    Season-to-date aggregated stats for each pitcher strictly before game_date.
    Returns dict keyed by pitcher_id.
    """
    if not pitcher_ids:
        return {}
    ids_sql = ", ".join(f"'{p}'" for p in pitcher_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            pitcher_id,
            COUNT(*)                                                    AS starts,
            SUM(batters_faced)                                          AS total_bf,
            SUM(strikeouts)                                             AS total_k,
            SUM(walks)                                                  AS total_bb,
            SUM(xwoba_against * batters_faced)
                / NULLIF(SUM(batters_faced), 0)                         AS season_xwoba_against
        FROM baseball_data.betting.mart_starting_pitcher_game_log
        WHERE pitcher_id IN ({ids_sql})
          AND game_date::date  < %(game_date)s
          AND game_year        = %(season)s
          AND batters_faced    > 0
        GROUP BY pitcher_id
        """,
        {"game_date": game_date.isoformat(), "season": season},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = {str(r["pitcher_id"]): r for r in (dict(zip(cols, row)) for row in cur.fetchall())}
    cur.close()
    return rows


def _load_prior_season_stats(
    conn, pitcher_ids: list[str], season: int
) -> dict[str, dict]:
    """
    Full prior-season stats for IL-return detection.
    Returns dict keyed by pitcher_id.
    """
    if not pitcher_ids:
        return {}
    ids_sql = ", ".join(f"'{p}'" for p in pitcher_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            pitcher_id,
            COUNT(*)                                                    AS starts,
            SUM(batters_faced)                                          AS total_bf,
            SUM(strikeouts)                                             AS total_k,
            SUM(walks)                                                  AS total_bb,
            SUM(xwoba_against * batters_faced)
                / NULLIF(SUM(batters_faced), 0)                         AS season_xwoba_against
        FROM baseball_data.betting.mart_starting_pitcher_game_log
        WHERE pitcher_id IN ({ids_sql})
          AND game_year    = %(prior_season)s
          AND batters_faced > 0
        GROUP BY pitcher_id
        """,
        {"prior_season": season - 1},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = {str(r["pitcher_id"]): r for r in (dict(zip(cols, row)) for row in cur.fetchall())}
    cur.close()
    return rows


def _load_pitcher_prior_seasons(
    conn, pitcher_ids: list[str], season: int
) -> dict[str, int]:
    """
    Count of distinct qualifying seasons (≥ MIN_STARTS or ≥ MIN_BF) strictly before
    the target season for each pitcher. Used to assign experience bands matching
    the labels in fit_starter_priors.py.

    Returns dict[pitcher_id → prior_qualifying_season_count].
    """
    if not pitcher_ids:
        return {}
    ids_sql = ", ".join(f"'{p}'" for p in pitcher_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            pitcher_id,
            COUNT(DISTINCT game_year) AS prior_seasons
        FROM baseball_data.betting.mart_starting_pitcher_game_log
        WHERE pitcher_id IN ({ids_sql})
          AND game_year < %(season)s
        GROUP BY pitcher_id
        HAVING COUNT(*) >= 10 OR SUM(batters_faced) >= 150
        """,
        {"season": season},
    )
    result = {}
    for row in cur.fetchall():
        result[str(row[0])] = int(row[1])
    cur.close()
    return result


# ── Posterior computation ─────────────────────────────────────────────────────

def _normal_posterior(
    mu0: float,
    sigma0: float,
    bf: float,
    obs_rate: float,
) -> tuple[float, float]:
    """
    Normal-Normal posterior mean and std.
    Measurement noise: σ_meas² = obs_rate·(1 - obs_rate) / BF (binomial SE approx).
    Returns (posterior_mean, posterior_std).
    """
    if bf <= 0:
        return mu0, sigma0

    sigma_meas_sq = max(obs_rate * (1.0 - obs_rate), 0.0001) / bf
    prec_prior = 1.0 / (sigma0 ** 2)
    prec_obs = 1.0 / sigma_meas_sq
    post_mean = (mu0 * prec_prior + obs_rate * prec_obs) / (prec_prior + prec_obs)
    post_var = 1.0 / (prec_prior + prec_obs)
    return float(post_mean), float(np.sqrt(max(post_var, 0.0)))


def _observed_rate(season_stats: dict | None, metric: str) -> float | None:
    """Extract observed rate for the given metric from aggregated season stats."""
    if not season_stats:
        return None
    if metric == "xwoba_against":
        return _float_or_none(season_stats.get("season_xwoba_against"))
    bf = _float_or_none(season_stats.get("total_bf")) or 0.0
    if bf <= 0:
        return None
    if metric == "k_pct":
        k = _float_or_none(season_stats.get("total_k")) or 0.0
        return k / bf
    if metric == "bb_pct":
        bb = _float_or_none(season_stats.get("total_bb")) or 0.0
        return bb / bf
    return None


def _float_or_none(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _compute_starter_row(
    game_pk: str,
    side: str,
    pitcher_id: str,
    season: int,
    game_date: date,
    priors: dict,
    age_band: str | None,
    current: dict | None,
    prior_season: dict | None,
    fit_date: date,
    run_id: str,
) -> dict[str, Any]:
    current_starts = int((current or {}).get("starts", 0) or 0)
    current_bf = float((current or {}).get("total_bf", 0) or 0)
    prior_starts = int((prior_season or {}).get("starts", 0) or 0)

    is_il_return = (
        current_starts < _IL_RETURN_CURRENT_STARTS_THRESHOLD
        and prior_starts >= _IL_RETURN_PRIOR_STARTS_THRESHOLD
    )

    eb_xwoba: float | None = None
    eb_k: float | None = None
    eb_bb: float | None = None
    eb_uncertainty: float | None = None
    eb_source: str

    if current_bf == 0 and not is_il_return:
        # True debut or start of season with no prior season — use prior mean
        cell = _get_prior_cell(priors, "xwoba_against", age_band)
        eb_xwoba = float(cell["mu"]) if cell else None
        cell_k = _get_prior_cell(priors, "k_pct", age_band)
        eb_k = float(cell_k["mu"]) if cell_k else None
        cell_bb = _get_prior_cell(priors, "bb_pct", age_band)
        eb_bb = float(cell_bb["mu"]) if cell_bb else None
        eb_uncertainty = float(cell["sigma"]) if cell else None
        eb_source = "prior_only"
    else:
        # Compute EB posterior for each metric
        results: dict[str, tuple[float, float]] = {}
        for metric in _METRICS:
            cell = _get_prior_cell(priors, metric, age_band)
            if cell is None:
                results[metric] = (float("nan"), float("nan"))
                continue
            mu0 = float(cell["mu"])
            sigma0 = float(cell["sigma"])
            obs = _observed_rate(current, metric) if current_bf > 0 else None
            if obs is None:
                results[metric] = (mu0, sigma0)
            else:
                results[metric] = _normal_posterior(mu0, sigma0, current_bf, obs)

        eb_xwoba_post, eb_xwoba_std = results["xwoba_against"]
        eb_k_post, _ = results["k_pct"]
        eb_bb_post, _ = results["bb_pct"]

        if is_il_return:
            # Blend 50% current-season posterior with 50% prior-season observed rate
            prior_xwoba = _observed_rate(prior_season, "xwoba_against")
            prior_k = _observed_rate(prior_season, "k_pct")
            prior_bb = _observed_rate(prior_season, "bb_pct")

            eb_xwoba = (
                0.5 * eb_xwoba_post + 0.5 * prior_xwoba
                if prior_xwoba is not None else eb_xwoba_post
            )
            eb_k = (
                0.5 * eb_k_post + 0.5 * prior_k
                if prior_k is not None else eb_k_post
            )
            eb_bb = (
                0.5 * eb_bb_post + 0.5 * prior_bb
                if prior_bb is not None else eb_bb_post
            )
            eb_uncertainty = eb_xwoba_std
            eb_source = "il_return_blend"
        else:
            eb_xwoba = eb_xwoba_post
            eb_k = eb_k_post
            eb_bb = eb_bb_post
            eb_uncertainty = eb_xwoba_std
            eb_source = "full_eb"

    def _round(v: float | None) -> float | None:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(v, 4)

    return {
        "game_pk":              game_pk,
        "side":                 side,
        "pitcher_id":           pitcher_id,
        "season":               season,
        "game_date":            game_date,
        "age_band":             age_band,
        "current_season_bf":    int(current_bf),
        "current_season_starts": current_starts,
        "eb_xwoba_against":     _round(eb_xwoba),
        "eb_k_pct":             _round(eb_k),
        "eb_bb_pct":            _round(eb_bb),
        "eb_xwoba_uncertainty": _round(eb_uncertainty),
        "eb_data_source":       eb_source,
        "fit_date":             fit_date,
        "run_id":               run_id,
    }


# ── Snowflake write ───────────────────────────────────────────────────────────

def _ensure_table(cur) -> None:
    """Create eb_starter_posteriors if it doesn't exist yet."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_starter_posteriors (
            game_pk                 VARCHAR(20)  NOT NULL,
            side                    VARCHAR(10)  NOT NULL,
            pitcher_id              VARCHAR(20)  NOT NULL,
            season                  INTEGER      NOT NULL,
            game_date               DATE         NOT NULL,
            age_band                VARCHAR(10),
            current_season_bf       INTEGER,
            current_season_starts   INTEGER,
            eb_xwoba_against        FLOAT,
            eb_k_pct                FLOAT,
            eb_bb_pct               FLOAT,
            eb_xwoba_uncertainty    FLOAT,
            eb_data_source          VARCHAR(20),
            fit_date                DATE,
            run_id                  VARCHAR(36)
        )
        """
    )


def _write_to_snowflake(conn, rows: list[dict]) -> None:
    """MERGE results into eb_starter_posteriors via VARCHAR temp table."""
    cur = conn.cursor()

    _ensure_table(cur)

    cur.execute(
        """
        CREATE OR REPLACE TEMPORARY TABLE baseball_data.betting.tmp_eb_starter_posteriors (
            game_pk                 VARCHAR,
            side                    VARCHAR,
            pitcher_id              VARCHAR,
            season                  VARCHAR,
            game_date               VARCHAR,
            age_band                VARCHAR,
            current_season_bf       VARCHAR,
            current_season_starts   VARCHAR,
            eb_xwoba_against        VARCHAR,
            eb_k_pct                VARCHAR,
            eb_bb_pct               VARCHAR,
            eb_xwoba_uncertainty    VARCHAR,
            eb_data_source          VARCHAR,
            fit_date                VARCHAR,
            run_id                  VARCHAR
        )
        """
    )

    def _s(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, date):
            return v.isoformat()
        return str(v)

    data = [
        (
            _s(r["game_pk"]),
            _s(r["side"]),
            _s(r["pitcher_id"]),
            _s(r["season"]),
            _s(r["game_date"]),
            _s(r["age_band"]),
            _s(r["current_season_bf"]),
            _s(r["current_season_starts"]),
            _s(r["eb_xwoba_against"]),
            _s(r["eb_k_pct"]),
            _s(r["eb_bb_pct"]),
            _s(r["eb_xwoba_uncertainty"]),
            _s(r["eb_data_source"]),
            _s(r["fit_date"]),
            _s(r["run_id"]),
        )
        for r in rows
    ]
    cur.executemany(
        "INSERT INTO baseball_data.betting.tmp_eb_starter_posteriors "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        data,
    )

    cur.execute(
        """
        MERGE INTO baseball_data.betting.eb_starter_posteriors tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)    AS game_pk,
                side::VARCHAR(10)       AS side,
                pitcher_id::VARCHAR(20) AS pitcher_id,
                season::INTEGER         AS season,
                game_date::DATE         AS game_date,
                age_band::VARCHAR(10)   AS age_band,
                current_season_bf::INTEGER      AS current_season_bf,
                current_season_starts::INTEGER  AS current_season_starts,
                eb_xwoba_against::FLOAT         AS eb_xwoba_against,
                eb_k_pct::FLOAT                 AS eb_k_pct,
                eb_bb_pct::FLOAT                AS eb_bb_pct,
                eb_xwoba_uncertainty::FLOAT     AS eb_xwoba_uncertainty,
                eb_data_source::VARCHAR(20)     AS eb_data_source,
                fit_date::DATE                  AS fit_date,
                run_id::VARCHAR(36)             AS run_id
            FROM baseball_data.betting.tmp_eb_starter_posteriors
        ) src
        ON  tgt.game_pk    = src.game_pk
        AND tgt.pitcher_id = src.pitcher_id
        WHEN MATCHED THEN UPDATE SET
            side                  = src.side,
            season                = src.season,
            game_date             = src.game_date,
            age_band              = src.age_band,
            current_season_bf     = src.current_season_bf,
            current_season_starts = src.current_season_starts,
            eb_xwoba_against      = src.eb_xwoba_against,
            eb_k_pct              = src.eb_k_pct,
            eb_bb_pct             = src.eb_bb_pct,
            eb_xwoba_uncertainty  = src.eb_xwoba_uncertainty,
            eb_data_source        = src.eb_data_source,
            fit_date              = src.fit_date,
            run_id                = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            game_pk, side, pitcher_id, season, game_date,
            age_band, current_season_bf, current_season_starts,
            eb_xwoba_against, eb_k_pct, eb_bb_pct, eb_xwoba_uncertainty,
            eb_data_source, fit_date, run_id
        ) VALUES (
            src.game_pk, src.side, src.pitcher_id, src.season, src.game_date,
            src.age_band, src.current_season_bf, src.current_season_starts,
            src.eb_xwoba_against, src.eb_k_pct, src.eb_bb_pct, src.eb_xwoba_uncertainty,
            src.eb_data_source, src.fit_date, src.run_id
        )
        """
    )
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def _process_date(conn, game_date: date, priors: dict) -> int:
    """Process one game date. Returns number of rows written."""
    season = game_date.year
    fit_date = date.today()
    run_id = str(uuid.uuid4())

    starters = _load_starters(conn, game_date)
    if not starters:
        return 0

    pitcher_ids = list({str(r["pitcher_id"]) for r in starters})
    current_stats = _load_current_season_stats(conn, pitcher_ids, game_date, season)
    prior_stats = _load_prior_season_stats(conn, pitcher_ids, season)
    prior_seasons_map = _load_pitcher_prior_seasons(conn, pitcher_ids, season)

    results = []
    for s in starters:
        pid = str(s["pitcher_id"])
        prior_seasons = prior_seasons_map.get(pid, 0)
        age_band = _assign_experience_band(prior_seasons)
        row = _compute_starter_row(
            game_pk=str(s["game_pk"]),
            side=str(s["side"]),
            pitcher_id=pid,
            season=season,
            game_date=game_date,
            priors=priors,
            age_band=age_band,
            current=current_stats.get(pid),
            prior_season=prior_stats.get(pid),
            fit_date=fit_date,
            run_id=run_id,
        )
        results.append(row)

    _write_to_snowflake(conn, results)
    return len(results)


def main(game_date: date) -> None:
    season = game_date.year
    run_id = str(uuid.uuid4())
    print(f"game_date={game_date}  season={season}  run_id={run_id[:8]}...")

    priors = _load_prior(season)

    conn = get_snowflake_connection()
    try:
        starters = _load_starters(conn, game_date)
        if not starters:
            print("No probable starters found for this date — nothing to write.")
            return
        n_games = len({r["game_pk"] for r in starters})
        print(f"  {len(starters)} starter-side rows across {n_games} games")

        pitcher_ids = list({str(r["pitcher_id"]) for r in starters})
        current_stats = _load_current_season_stats(conn, pitcher_ids, game_date, season)
        prior_stats = _load_prior_season_stats(conn, pitcher_ids, season)
        prior_seasons_map = _load_pitcher_prior_seasons(conn, pitcher_ids, season)

        results = []
        for s in starters:
            pid = str(s["pitcher_id"])
            prior_seasons = prior_seasons_map.get(pid, 0)
            age_band = _assign_experience_band(prior_seasons)
            row = _compute_starter_row(
                game_pk=str(s["game_pk"]),
                side=str(s["side"]),
                pitcher_id=pid,
                season=season,
                game_date=game_date,
                priors=priors,
                age_band=age_band,
                current=current_stats.get(pid),
                prior_season=prior_stats.get(pid),
                fit_date=date.today(),
                run_id=run_id,
            )
            results.append(row)

        # Diagnostics
        sources: dict[str, int] = {}
        for r in results:
            sources[r["eb_data_source"]] = sources.get(r["eb_data_source"], 0) + 1
        il_returns = sum(1 for r in results if r["eb_data_source"] == "il_return_blend")
        band_dist: dict[str, int] = {}
        for r in results:
            band_dist[r["age_band"]] = band_dist.get(r["age_band"], 0) + 1
        print(f"  current_stats found: {len(current_stats)}/{len(pitcher_ids)}")
        print(f"  prior_season found:  {len(prior_stats)}/{len(pitcher_ids)}")
        print(f"  experience bands:    {band_dist}")
        print(f"  IL-return blend:     {il_returns}/{len(results)}")
        print(f"  eb_data_source:      {sources}")

        sample = results[0]
        print(
            f"  sample ({sample['eb_data_source']}): "
            f"pitcher={sample['pitcher_id']}  age_band={sample['age_band']}  "
            f"bf={sample['current_season_bf']}  "
            f"xwoba={sample['eb_xwoba_against']}  k%={sample['eb_k_pct']}  "
            f"unc={sample['eb_xwoba_uncertainty']}"
        )

        print(f"Writing {len(results)} rows to eb_starter_posteriors...")
        _write_to_snowflake(conn, results)
        print("Done.")
    finally:
        conn.close()


def main_backfill_season(season: int) -> None:
    """Process every game date in a season in chronological order."""
    print(f"\n═══ Backfill season {season} ═══")
    priors = _load_prior(season)

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT game_date::date AS game_date
            FROM baseball_data.betting_features.feature_pregame_starter_status
            WHERE year(game_date)  = %(season)s
              AND is_current       = true
              AND starter_player_id IS NOT NULL
            ORDER BY game_date
            """,
            {"season": season},
        )
        game_dates = [r[0] for r in cur.fetchall()]
        cur.close()

        print(f"  {len(game_dates)} game dates to process")
        total_rows = 0
        for i, gd in enumerate(game_dates, 1):
            gd_obj = (
                gd if isinstance(gd, date)
                else datetime.strptime(str(gd)[:10], "%Y-%m-%d").date()
            )
            n = _process_date(conn, gd_obj, priors)
            total_rows += n
            if i % 50 == 0 or i == len(game_dates):
                print(f"  [{i}/{len(game_dates)}] {gd_obj}  cumulative rows={total_rows}")

        print(f"\n  Season {season} complete — {total_rows} total rows written.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute per-starter EB posteriors and write to Snowflake"
    )
    parser.add_argument(
        "--game-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Single game date to process (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--backfill-season",
        type=int,
        dest="backfill_season",
        metavar="YEAR",
        help="Backfill all game dates in the given season",
    )
    args = parser.parse_args()

    if args.backfill_season:
        main_backfill_season(args.backfill_season)
    else:
        main(args.game_date or date.today())
