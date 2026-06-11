"""
compute_lineup_posteriors.py — Per-batter EB posterior computation (Epic 4A.2)

For each game on a given date, computes per-batter-slot EB posteriors for
wOBA, K%, BB% (Beta-Binomial) and ISO (Normal-Normal), then blends with
ZiPS projections at low sample sizes.

ZiPS blend rule:
    eb_weight = min(PA / 150.0, 1.0)
    final_stat = eb_weight * eb_posterior + (1 - eb_weight) * zips_stat

eb_data_source labels:
    prior_only  — PA = 0 and ZiPS not available; uses prior mean
    zips_blend  — PA < 150 and ZiPS available; weighted blend
    full_eb     — PA ≥ 150; pure EB posterior

LEAKAGE GUARD: rolling stats joined with game_date < game_date (strictly
less than), matching the guard used in feature_pregame_lineup_features.sql.

Writes to baseball_data.betting.eb_batter_posteriors_raw via VARCHAR temp
table + MERGE on (game_pk, batting_slot, batter_id).

Usage:
    uv run python betting_ml/scripts/eb_priors/compute_lineup_posteriors.py
    uv run python betting_ml/scripts/eb_priors/compute_lineup_posteriors.py --game-date 2025-05-01
    uv run python betting_ml/scripts/eb_priors/compute_lineup_posteriors.py --backfill-season 2019
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
from betting_ml.scripts.sequential_bayes.asof_lookup import (
    load_seq_posteriors_asof, resolve_posterior_source,
)

_PRIORS_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"
_ZIPS_PROJ_TYPE = "zips"
_EB_PA_THRESHOLD = 150.0
# Epic 16.2 — batter sequential posterior chain tracks expected wOBA (xwOBA,
# denominated in wOBA units → scale-consistent with eb_woba). Injected as a
# PARALLEL column (eb_woba_sequential), never overwriting eb_woba.
_SEQ_PLAYER_TYPE = "batter"
_SEQ_METRIC = "xwoba"

# ── Prior loading ─────────────────────────────────────────────────────────────

def _load_prior(season: int) -> dict:
    path = _PRIORS_DIR / f"lineup_priors_{season}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Prior file not found: {path}. "
            f"Run fit_lineup_priors.py --season {season} first."
        )
    return json.loads(path.read_text())["priors"]


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_lineups(conn, game_date: date) -> list[dict]:
    """Return one row per (game_pk, batting_slot, player_id) for the date."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            game_pk,
            batting_order   AS batting_slot,
            player_id       AS batter_id
        FROM baseball_data.betting.stg_statsapi_lineups
        WHERE official_date = %(game_date)s
          AND batting_order BETWEEN 1 AND 9
        ORDER BY game_pk, batting_order
        """,
        {"game_date": game_date.isoformat()},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _load_rolling_stats(conn, batter_ids: list[str], game_date: date, season: int) -> dict[str, dict]:
    """
    Latest cumulative-season stats row per batter strictly before game_date.
    Returns dict keyed by batter_id.
    """
    if not batter_ids:
        return {}
    ids_sql = ", ".join(f"'{b}'" for b in batter_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            batter_id,
            woba_std        AS woba,
            k_pct_std       AS k_pct,
            bb_pct_std      AS bb_pct,
            iso_std         AS iso,
            pa_count_std    AS pa,
            batter_hand
        FROM baseball_data.betting.mart_batter_rolling_stats
        WHERE batter_id IN ({ids_sql})
          AND game_date::date  < %(game_date)s
          AND game_year        = %(season)s
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY batter_id
            ORDER BY game_date DESC
        ) = 1
        """,
        {"game_date": game_date.isoformat(), "season": season},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = {str(r["batter_id"]): r for r in (dict(zip(cols, row)) for row in cur.fetchall())}
    cur.close()
    return rows


def _load_zips(conn, batter_ids: list[str], season: int) -> dict[str, dict]:
    """ZiPS DC projections for the season. Returns dict keyed by mlbam_batter_id."""
    if not batter_ids:
        return {}
    ids_sql = ", ".join(f"'{b}'" for b in batter_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            mlbam_batter_id,
            proj_woba,
            proj_k_pct,
            proj_bb_pct,
            proj_iso
        FROM baseball_data.betting.stg_fangraphs__zips_hitting
        WHERE season            = %(season)s
          AND projection_type   = %(proj_type)s
          AND mlbam_batter_id   IN ({ids_sql})
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY mlbam_batter_id
            ORDER BY ingestion_ts DESC
        ) = 1
        """,
        {"season": season, "proj_type": _ZIPS_PROJ_TYPE},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = {str(r["mlbam_batter_id"]): r for r in (dict(zip(cols, row)) for row in cur.fetchall())}
    cur.close()
    return rows


# ── Posterior computation ─────────────────────────────────────────────────────

def _slot_to_role(slot: int) -> str:
    if slot <= 3:
        return "top"
    if slot <= 6:
        return "middle"
    return "bottom"


def _get_prior_cell(priors: dict, metric: str, slot: int, hand: str) -> dict | None:
    role = _slot_to_role(slot)
    return (priors.get(metric, {}).get(role, {}).get(hand)
            or priors.get(metric, {}).get(role, {}).get("R"))  # R fallback for missing hand


def _beta_posterior_mean(alpha: float, beta: float, pa: float, obs_rate: float) -> float:
    """Beta-Binomial posterior mean given prior (α, β) and (PA, observed rate)."""
    successes = obs_rate * pa
    return (alpha + successes) / (alpha + beta + pa)


def _beta_posterior_uncertainty(alpha: float, beta: float, pa: float, obs_rate: float) -> float:
    """Posterior std of Beta-Binomial (used for wOBA uncertainty column)."""
    successes = obs_rate * pa
    a = alpha + successes
    b = beta + (pa - successes)
    n = a + b
    var = (a * b) / (n * n * (n + 1))
    return float(np.sqrt(max(var, 0.0)))


def _normal_posterior_mean(mu0: float, sigma0: float, pa: float, obs_iso: float) -> float:
    """Normal-Normal posterior mean for ISO."""
    if pa <= 0:
        return mu0
    # Measurement noise per PA: approximate as sqrt(iso*(1-iso)/pa)
    sigma_meas_sq = max(obs_iso * (1.0 - obs_iso), 0.001) / pa
    prec_prior = 1.0 / (sigma0 ** 2)
    prec_obs = 1.0 / sigma_meas_sq
    return (mu0 * prec_prior + obs_iso * prec_obs) / (prec_prior + prec_obs)


def _prior_mean(cell: dict, metric: str) -> float:
    if metric == "iso":
        return float(cell["mu"])
    return float(cell["alpha"]) / (float(cell["alpha"]) + float(cell["beta"]))


def _compute_batter_posterior(
    metric: str,
    prior_cell: dict | None,
    pa: float,
    obs_val: float | None,
    zips_val: float | None,
) -> tuple[float | None, str]:
    """
    Returns (posterior_value, eb_data_source).
    """
    if prior_cell is None:
        return None, "prior_only"

    eb_weight = min(pa / _EB_PA_THRESHOLD, 1.0)

    # Prior mean (zero-data estimate)
    prior_mu = _prior_mean(prior_cell, metric)

    if pa == 0 or obs_val is None:
        # No in-season data
        if zips_val is not None:
            # Use ZiPS directly (weight=0 toward EB means pure ZiPS)
            return float(zips_val), "zips_blend"
        return float(prior_mu), "prior_only"

    # Compute EB posterior
    if metric == "iso":
        eb_post = _normal_posterior_mean(prior_mu, float(prior_cell["sigma"]), pa, obs_val)
    else:
        eb_post = _beta_posterior_mean(
            float(prior_cell["alpha"]), float(prior_cell["beta"]), pa, obs_val
        )

    if eb_weight >= 1.0:
        return float(eb_post), "full_eb"

    # Blend with ZiPS
    if zips_val is not None:
        blended = eb_weight * eb_post + (1.0 - eb_weight) * float(zips_val)
        return float(blended), "zips_blend"

    # ZiPS not available — use EB posterior even at low PA
    return float(eb_post), "full_eb"


def _compute_row(
    game_pk: str,
    batting_slot: int,
    batter_id: str,
    season: int,
    game_date: date,
    priors: dict,
    rolling: dict | None,
    zips: dict | None,
    fit_date: date,
    run_id: str,
    seq: dict | None = None,
) -> dict[str, Any]:
    pa = float(rolling["pa"]) if rolling and rolling.get("pa") is not None else 0.0
    hand = (rolling.get("batter_hand") or "R") if rolling else "R"

    def _val(key: str) -> float | None:
        if rolling and rolling.get(key) is not None:
            return float(rolling[key])
        return None

    def _zval(key: str) -> float | None:
        if zips and zips.get(key) is not None:
            return float(zips[key])
        return None

    woba_post, woba_src = _compute_batter_posterior(
        "woba", _get_prior_cell(priors, "woba", batting_slot, hand),
        pa, _val("woba"), _zval("proj_woba"),
    )
    k_post, _ = _compute_batter_posterior(
        "k_pct", _get_prior_cell(priors, "k_pct", batting_slot, hand),
        pa, _val("k_pct"), _zval("proj_k_pct"),
    )
    bb_post, _ = _compute_batter_posterior(
        "bb_pct", _get_prior_cell(priors, "bb_pct", batting_slot, hand),
        pa, _val("bb_pct"), _zval("proj_bb_pct"),
    )
    iso_post, _ = _compute_batter_posterior(
        "iso", _get_prior_cell(priors, "iso", batting_slot, hand),
        pa, _val("iso"), _zval("proj_iso"),
    )

    # wOBA uncertainty — posterior std from Beta-Binomial
    woba_cell = _get_prior_cell(priors, "woba", batting_slot, hand)
    if woba_cell and pa > 0 and _val("woba") is not None:
        woba_uncertainty = _beta_posterior_uncertainty(
            float(woba_cell["alpha"]), float(woba_cell["beta"]), pa, float(_val("woba"))  # type: ignore[arg-type]
        )
    elif woba_cell:
        a, b = float(woba_cell["alpha"]), float(woba_cell["beta"])
        n = a + b
        woba_uncertainty = float(np.sqrt(a * b / (n * n * (n + 1))))
    else:
        woba_uncertainty = None

    # Epic 16.2 — as-of sequential posterior (parallel column; never overwrites eb_woba).
    posterior_source, prior_age_days = resolve_posterior_source(seq, woba_src, game_date)
    eb_woba_sequential = (
        round(float(seq["posterior_mu"]), 4)
        if seq is not None and seq.get("posterior_mu") is not None else None
    )

    return {
        "game_pk":             game_pk,
        "batting_slot":        batting_slot,
        "batter_id":           batter_id,
        "season":              season,
        "game_date":           game_date,
        "eb_woba":             round(woba_post, 4) if woba_post is not None else None,
        "eb_k_pct":            round(k_post, 4) if k_post is not None else None,
        "eb_bb_pct":           round(bb_post, 4) if bb_post is not None else None,
        "eb_iso":              round(iso_post, 4) if iso_post is not None else None,
        "eb_woba_uncertainty": round(woba_uncertainty, 4) if woba_uncertainty is not None else None,
        "pa_weight":           round(min(pa / _EB_PA_THRESHOLD, 1.0), 4),
        "eb_data_source":      woba_src,
        "eb_woba_sequential":  eb_woba_sequential,
        "posterior_source":    posterior_source,
        "prior_age_days":      prior_age_days,
        "fit_date":            fit_date,
        "run_id":              run_id,
    }


# ── Snowflake write ───────────────────────────────────────────────────────────

def _write_to_snowflake(conn, rows: list[dict]) -> None:
    """MERGE results into eb_batter_posteriors_raw via VARCHAR temp table."""
    cur = conn.cursor()

    cur.execute(
        """
        CREATE OR REPLACE TEMPORARY TABLE baseball_data.betting.tmp_eb_batter_posteriors (
            game_pk              VARCHAR,
            batting_slot         VARCHAR,
            batter_id            VARCHAR,
            season               VARCHAR,
            game_date            VARCHAR,
            eb_woba              VARCHAR,
            eb_k_pct             VARCHAR,
            eb_bb_pct            VARCHAR,
            eb_iso               VARCHAR,
            eb_woba_uncertainty  VARCHAR,
            pa_weight            VARCHAR,
            eb_data_source       VARCHAR,
            eb_woba_sequential   VARCHAR,
            posterior_source     VARCHAR,
            prior_age_days       VARCHAR,
            fit_date             VARCHAR,
            run_id               VARCHAR
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
            _s(r["batting_slot"]),
            _s(r["batter_id"]),
            _s(r["season"]),
            _s(r["game_date"]),
            _s(r["eb_woba"]),
            _s(r["eb_k_pct"]),
            _s(r["eb_bb_pct"]),
            _s(r["eb_iso"]),
            _s(r["eb_woba_uncertainty"]),
            _s(r["pa_weight"]),
            _s(r["eb_data_source"]),
            _s(r["eb_woba_sequential"]),
            _s(r["posterior_source"]),
            _s(r["prior_age_days"]),
            _s(r["fit_date"]),
            _s(r["run_id"]),
        )
        for r in rows
    ]
    cur.executemany(
        "INSERT INTO baseball_data.betting.tmp_eb_batter_posteriors VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        data,
    )

    cur.execute(
        """
        MERGE INTO baseball_data.betting.eb_batter_posteriors_raw tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)        AS game_pk,
                batting_slot::INTEGER       AS batting_slot,
                batter_id::VARCHAR(20)      AS batter_id,
                season::INTEGER             AS season,
                game_date::DATE             AS game_date,
                eb_woba::FLOAT              AS eb_woba,
                eb_k_pct::FLOAT             AS eb_k_pct,
                eb_bb_pct::FLOAT            AS eb_bb_pct,
                eb_iso::FLOAT               AS eb_iso,
                eb_woba_uncertainty::FLOAT  AS eb_woba_uncertainty,
                pa_weight::FLOAT            AS pa_weight,
                eb_data_source::VARCHAR(20) AS eb_data_source,
                eb_woba_sequential::FLOAT   AS eb_woba_sequential,
                posterior_source::VARCHAR(20) AS posterior_source,
                prior_age_days::INTEGER     AS prior_age_days,
                fit_date::DATE              AS fit_date,
                run_id::VARCHAR(36)         AS run_id
            FROM baseball_data.betting.tmp_eb_batter_posteriors
        ) src
        ON  tgt.game_pk      = src.game_pk
        AND tgt.batting_slot = src.batting_slot
        AND tgt.batter_id    = src.batter_id
        WHEN MATCHED THEN UPDATE SET
            season              = src.season,
            game_date           = src.game_date,
            eb_woba             = src.eb_woba,
            eb_k_pct            = src.eb_k_pct,
            eb_bb_pct           = src.eb_bb_pct,
            eb_iso              = src.eb_iso,
            eb_woba_uncertainty = src.eb_woba_uncertainty,
            pa_weight           = src.pa_weight,
            eb_data_source      = src.eb_data_source,
            eb_woba_sequential  = src.eb_woba_sequential,
            posterior_source    = src.posterior_source,
            prior_age_days      = src.prior_age_days,
            fit_date            = src.fit_date,
            run_id              = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            game_pk, batting_slot, batter_id, season, game_date,
            eb_woba, eb_k_pct, eb_bb_pct, eb_iso, eb_woba_uncertainty,
            pa_weight, eb_data_source, eb_woba_sequential, posterior_source, prior_age_days,
            fit_date, run_id
        ) VALUES (
            src.game_pk, src.batting_slot, src.batter_id, src.season, src.game_date,
            src.eb_woba, src.eb_k_pct, src.eb_bb_pct, src.eb_iso, src.eb_woba_uncertainty,
            src.pa_weight, src.eb_data_source, src.eb_woba_sequential, src.posterior_source,
            src.prior_age_days, src.fit_date, src.run_id
        )
        """
    )
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def _compute_date_rows(conn, game_date: date, priors: dict) -> list[dict]:
    """Compute (but do NOT write) all posterior rows for one game date.

    A2.8 spend fix: the backfill used to write per date (CREATE TEMP + INSERT +
    MERGE round-trip × N dates). This returns the rows so the caller can
    accumulate across all dates and write ONCE. The reads stay per-date (each
    date needs rolling stats strictly before game_date).
    """
    season = game_date.year
    fit_date = date.today()
    run_id = str(uuid.uuid4())

    lineups = _load_lineups(conn, game_date)
    if not lineups:
        return []

    batter_ids = list({str(r["batter_id"]) for r in lineups})
    rolling_map = _load_rolling_stats(conn, batter_ids, game_date, season)
    zips_map = _load_zips(conn, batter_ids, season)
    seq_map = load_seq_posteriors_asof(conn, batter_ids, _SEQ_PLAYER_TYPE, _SEQ_METRIC, game_date, season)

    results = []
    for lr in lineups:
        bid = str(lr["batter_id"])
        row = _compute_row(
            game_pk=str(lr["game_pk"]),
            batting_slot=int(lr["batting_slot"]),
            batter_id=bid,
            season=season,
            game_date=game_date,
            priors=priors,
            rolling=rolling_map.get(bid),
            zips=zips_map.get(bid),
            fit_date=fit_date,
            run_id=run_id,
            seq=seq_map.get(bid),
        )
        results.append(row)

    return results


def main(game_date: date) -> None:
    season = game_date.year
    fit_date = date.today()
    run_id = str(uuid.uuid4())

    print(f"game_date={game_date}  season={season}  run_id={run_id[:8]}...")

    priors = _load_prior(season)

    conn = get_snowflake_connection()
    try:
        lineups = _load_lineups(conn, game_date)
        if not lineups:
            print("No lineup rows found for this date — nothing to write.")
            return
        print(f"  {len(lineups)} batter-slot rows across "
              f"{len(set(r['game_pk'] for r in lineups))} games")

        batter_ids = list({str(r["batter_id"]) for r in lineups})
        rolling_map = _load_rolling_stats(conn, batter_ids, game_date, season)
        zips_map = _load_zips(conn, batter_ids, season)
        seq_map = load_seq_posteriors_asof(conn, batter_ids, _SEQ_PLAYER_TYPE, _SEQ_METRIC, game_date, season)

        results = []
        for lr in lineups:
            bid = str(lr["batter_id"])
            rolling = rolling_map.get(bid)
            zips = zips_map.get(bid)
            row = _compute_row(
                game_pk=str(lr["game_pk"]),
                batting_slot=int(lr["batting_slot"]),
                batter_id=bid,
                season=season,
                game_date=game_date,
                priors=priors,
                rolling=rolling,
                zips=zips,
                fit_date=fit_date,
                run_id=run_id,
                seq=seq_map.get(bid),
            )
            results.append(row)

        # Diagnostics
        sources = {}
        for r in results:
            sources[r["eb_data_source"]] = sources.get(r["eb_data_source"], 0) + 1
        rolling_hit = sum(1 for r in results if r["pa_weight"] > 0)
        zips_hit = sum(1 for lr in lineups if zips_map.get(str(lr["batter_id"])))
        psrc: dict[str, int] = {}
        for r in results:
            psrc[r["posterior_source"]] = psrc.get(r["posterior_source"], 0) + 1
        print(f"  rolling stats found: {rolling_hit}/{len(results)}")
        print(f"  ZiPS found:          {zips_hit}/{len(results)}")
        print(f"  eb_data_source:      {sources}")
        print(f"  posterior_source:    {psrc}  (Epic 16.2)")

        sample = next(
            (r for r in results if r["eb_data_source"] == "full_eb"), results[0]
        )
        print(f"  sample ({sample['eb_data_source']}): "
              f"batter={sample['batter_id']}  slot={sample['batting_slot']}  "
              f"woba={sample['eb_woba']}  k%={sample['eb_k_pct']}  "
              f"iso={sample['eb_iso']}  pa_w={sample['pa_weight']}")

        print(f"Writing {len(results)} rows to eb_batter_posteriors_raw...")
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
            SELECT DISTINCT official_date
            FROM baseball_data.betting.stg_statsapi_lineups
            WHERE year(official_date) = %(season)s
              AND batting_order BETWEEN 1 AND 9
            ORDER BY official_date
            """,
            {"season": season},
        )
        game_dates = [r[0] for r in cur.fetchall()]
        cur.close()

        print(f"  {len(game_dates)} game dates to process")
        all_rows: list[dict] = []
        for i, gd in enumerate(game_dates, 1):
            gd_obj = gd if isinstance(gd, date) else datetime.strptime(str(gd)[:10], "%Y-%m-%d").date()
            all_rows.extend(_compute_date_rows(conn, gd_obj, priors))
            if i % 50 == 0 or i == len(game_dates):
                print(f"  [{i}/{len(game_dates)}] {gd_obj}  cumulative rows={len(all_rows)}")

        # A2.8 spend fix: ONE batched temp-table + INSERT + MERGE for the whole
        # season instead of a write round-trip per date.
        if all_rows:
            print(f"  Writing {len(all_rows)} rows in a single batched MERGE...")
            _write_to_snowflake(conn, all_rows)
        print(f"\n  Season {season} complete — {len(all_rows)} total rows written.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute per-batter-slot EB posteriors and write to Snowflake"
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
        help="Backfill all game dates in the given season (requires prior JSON for that season)",
    )
    args = parser.parse_args()

    if args.backfill_season:
        main_backfill_season(args.backfill_season)
    else:
        main(args.game_date or date.today())
