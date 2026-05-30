"""
fit_starter_priors.py — Empirical Bayes starter rate prior fitting (Epic 5A.1)

Fits Normal(μ, σ) priors for three per-starter rate statistics stratified
by experience band × season:

    xwOBA-against, K% per BF, BB% per BF  →  Normal-Normal  (MoM: μ, σ)

Experience bands (prior qualifying seasons before the target season — a reliable
proxy for age since pitcher birth dates are not available in the current pipeline;
correlates well with actual age given typical debut ages of 22–26):
    u25  = 0 prior qualifying seasons   (rookie / debut year)
    a25  = 1–3 prior qualifying seasons (developing)
    a30  = 4–7 prior qualifying seasons (established)
    a33  = 8+  prior qualifying seasons (veteran)

"Prior qualifying seasons" = distinct seasons before the target season in which
the pitcher had ≥ MIN_STARTS starts OR ≥ MIN_BF BF in mart_starting_pitcher_game_log.

Qualified sample per target season: starters with ≥ MIN_STARTS starts OR ≥ MIN_BF BF.
Cells with fewer than MIN_CELL_STARTERS starters fall back to the experience-band-only
prior pooled across all seasons ≤ the target season.

Sanity check: mu_xwoba[u25] > mu_xwoba[a25] (rookies allow more contact quality
on average — higher xwOBA-against is worse). A warning is logged if violated.

NOTE: Age band labels (u25 / a25 / a30 / a33) are retained in the JSON output for
API compatibility with compute_starter_posteriors.py. They represent experience bands,
not literal ages. If pitcher birth dates become available in the pipeline, replace the
_assign_experience_band() function with an actual age lookup.

Output is written to:
    betting_ml/models/eb_priors/starter_priors_{season}.json

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_starter_priors.py
    uv run python betting_ml/scripts/eb_priors/fit_starter_priors.py --season 2024
    uv run python betting_ml/scripts/eb_priors/fit_starter_priors.py --season 2021 --season 2022
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

# ── Constants ────────────────────────────────────────────────────────────────

_MIN_STARTS = 10
_MIN_BF = 150
_MIN_CELL_STARTERS = 15
_FIRST_SEASON = 2016

_METRICS = ("xwoba_against", "k_pct", "bb_pct")

# Experience band labels kept as u25/a25/a30/a33 for API compatibility with
# compute_starter_posteriors.py. Thresholds are prior qualifying seasons.
_EXPERIENCE_BANDS = [
    ("u25", 0, 0),    # 0 prior qualifying seasons (rookie)
    ("a25", 1, 3),    # 1–3 prior qualifying seasons (developing)
    ("a30", 4, 7),    # 4–7 prior qualifying seasons (established)
    ("a33", 8, 999),  # 8+ prior qualifying seasons (veteran)
]

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"


# ── Experience band assignment ────────────────────────────────────────────────

def _assign_experience_band(prior_seasons: int) -> str:
    for label, lo, hi in _EXPERIENCE_BANDS:
        if lo <= prior_seasons <= hi:
            return label
    return "a33"  # shouldn't reach here given the 999 ceiling


# ── Data loading ─────────────────────────────────────────────────────────────

def _load_starter_data(conn, max_season: int) -> list[dict]:
    """
    Load season-aggregated stats for all qualified starters from FIRST_SEASON
    through max_season. Returns one row per (pitcher_id, season).

    xwOBA-against: BF-weighted mean across starts.
    K% / BB%: season aggregate strikeouts / walks divided by total BF.
    Experience band is computed in Python from the full result set (see
    _assign_experience_bands_to_rows).
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            gl.pitcher_id,
            gl.game_year                                                AS season,
            COUNT(*)                                                    AS starts,
            SUM(gl.batters_faced)                                       AS total_bf,
            SUM(gl.strikeouts)                                          AS total_k,
            SUM(gl.walks)                                               AS total_bb,
            -- BF-weighted mean to avoid start-length bias
            SUM(gl.xwoba_against * gl.batters_faced)
                / NULLIF(SUM(gl.batters_faced), 0)                      AS season_xwoba_against
        FROM baseball_data.betting.mart_starting_pitcher_game_log gl
        WHERE gl.game_year BETWEEN %(first_season)s AND %(max_season)s
          AND gl.batters_faced > 0
        GROUP BY gl.pitcher_id, gl.game_year
        HAVING COUNT(*) >= %(min_starts)s
            OR SUM(gl.batters_faced) >= %(min_bf)s
        ORDER BY gl.pitcher_id, gl.game_year
        """,
        {
            "first_season": _FIRST_SEASON,
            "max_season": max_season,
            "min_starts": _MIN_STARTS,
            "min_bf": _MIN_BF,
        },
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()

    # Add derived columns and normalize keys to match _METRICS names
    for r in rows:
        bf = float(r["total_bf"]) if r["total_bf"] else 0.0
        r["k_pct"] = float(r["total_k"]) / bf if bf > 0 else None
        r["bb_pct"] = float(r["total_bb"]) / bf if bf > 0 else None
        r["xwoba_against"] = r.get("season_xwoba_against")

    _assign_experience_bands_to_rows(rows)
    return [r for r in rows if r.get("xwoba_against") is not None]


def _assign_experience_bands_to_rows(rows: list[dict]) -> None:
    """
    Compute each pitcher's prior qualifying seasons (seasons before target season
    where they appear in the dataset) and assign an experience band in-place.

    pitcher_id → sorted list of qualifying seasons from all_rows (the full dataset
    is passed in, so experience correctly counts only seasons before the target).
    """
    # Build a map: pitcher_id → sorted list of all qualifying seasons
    pitcher_seasons: dict[str, list[int]] = {}
    for r in rows:
        pid = str(r["pitcher_id"])
        season = int(r["season"])
        pitcher_seasons.setdefault(pid, []).append(season)
    for pid in pitcher_seasons:
        pitcher_seasons[pid].sort()

    for r in rows:
        pid = str(r["pitcher_id"])
        season = int(r["season"])
        prior_qualifying = sum(1 for s in pitcher_seasons[pid] if s < season)
        r["experience_band"] = _assign_experience_band(prior_qualifying)
        r["prior_qualifying_seasons"] = prior_qualifying


# ── Prior fitting ─────────────────────────────────────────────────────────────

def _fit_normal_mom(vals: list[float]) -> dict | None:
    """Method-of-moments Normal(μ, σ) from a list of rate values."""
    n = len(vals)
    if n < 2:
        return None
    mu = float(np.mean(vals))
    sigma = float(np.std(vals, ddof=1))
    if sigma <= 0:
        sigma = 0.001
    return {"mu": round(mu, 4), "sigma": round(sigma, 4), "n_starters": n}


def _collect_metric_vals(
    rows: list[dict],
    metric: str,
    band: str | None,
    season: int | None,
) -> list[float]:
    """
    Collect metric values from rows, optionally filtered by experience band and season.
    band=None: pool across all experience bands.
    season=None: pool across all seasons.
    """
    vals = []
    for row in rows:
        if season is not None and int(row["season"]) != season:
            continue
        if band is not None and row.get("experience_band") != band:
            continue
        v = row.get(metric)
        if v is not None:
            vals.append(float(v))
    return vals


def _build_band_only_priors(all_rows: list[dict], max_season: int) -> dict:
    """
    Fit experience-band-only priors pooled across all seasons ≤ max_season.
    Used as the fallback when a (metric, band, season) cell has < MIN_CELL_STARTERS.
    """
    rows_up_to = [r for r in all_rows if int(r["season"]) <= max_season]
    band_priors: dict = {}
    for metric in _METRICS:
        band_priors[metric] = {}
        for label, _, _ in _EXPERIENCE_BANDS:
            vals = _collect_metric_vals(rows_up_to, metric, label, season=None)
            band_priors[metric][label] = _fit_normal_mom(vals)
    return band_priors


def _build_priors(
    all_rows: list[dict],
    season: int,
    band_only_priors: dict,
) -> dict:
    """
    Fit (metric, experience_band) priors for a specific season.
    Falls back to band_only_priors when cell n < MIN_CELL_STARTERS.
    """
    priors: dict = {}
    for metric in _METRICS:
        priors[metric] = {}
        for label, _, _ in _EXPERIENCE_BANDS:
            vals = _collect_metric_vals(all_rows, metric, label, season=season)
            if len(vals) >= _MIN_CELL_STARTERS:
                priors[metric][label] = _fit_normal_mom(vals)
            else:
                fallback = (band_only_priors.get(metric) or {}).get(label)
                if fallback is not None:
                    priors[metric][label] = {
                        **fallback,
                        "n_starters": len(vals),
                        "fallback": True,
                    }
                else:
                    priors[metric][label] = None
    return priors


def _sanity_check(priors: dict, season: int) -> None:
    """
    Verify mu_xwoba[u25] > mu_xwoba[a25].
    Rookies allow more contact quality on average (experience-band proxy for age).
    """
    xwoba = priors.get("xwoba_against", {})
    u25_cell = xwoba.get("u25")
    a25_cell = xwoba.get("a25")
    if u25_cell and a25_cell:
        u25_mu = u25_cell["mu"]
        a25_mu = a25_cell["mu"]
        if u25_mu <= a25_mu:
            print(
                f"  WARNING: Monotonicity violated in {season}: "
                f"mu_xwoba[u25]={u25_mu:.4f} ≤ mu_xwoba[a25]={a25_mu:.4f}"
            )
        else:
            print(
                f"  Monotonicity OK: mu_xwoba[u25]={u25_mu:.4f} > "
                f"mu_xwoba[a25]={a25_mu:.4f}"
            )


# ── Output ────────────────────────────────────────────────────────────────────

def _write_json(priors: dict, season: int, fit_date: date) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"starter_priors_{season}.json"
    payload = {
        "season":   season,
        "fit_date": fit_date.isoformat(),
        "priors":   priors,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main(seasons: list[int]) -> None:
    max_season = max(seasons)
    conn = get_snowflake_connection()
    try:
        print(f"Loading starter data from {_FIRST_SEASON} through {max_season}...")
        all_rows = _load_starter_data(conn, max_season)
        print(f"  {len(all_rows)} pitcher-season rows loaded")
        if not all_rows:
            print("ERROR: no data returned — check mart_starting_pitcher_game_log coverage")
            return

        fit_date = date.today()
        for season in sorted(set(seasons)):
            print(f"\n── Season {season} ──────────────────────────────────")
            season_rows = [r for r in all_rows if int(r["season"]) == season]
            print(f"  {len(season_rows)} qualified starters in {season}")
            if not season_rows:
                print("  WARNING: no data — skipping season")
                continue

            band_only_priors = _build_band_only_priors(all_rows, season)
            priors = _build_priors(all_rows, season, band_only_priors)

            for metric in _METRICS:
                for label, _, _ in _EXPERIENCE_BANDS:
                    cell = priors[metric].get(label)
                    n = (cell or {}).get("n_starters", 0)
                    fb = " [FALLBACK]" if (cell or {}).get("fallback") else ""
                    if cell:
                        print(f"  {metric:18s}  {label:4s}  n={n:3d}  "
                              f"μ={cell['mu']:.4f}  σ={cell['sigma']:.4f}{fb}")
                    else:
                        print(f"  {metric:18s}  {label:4s}  n={n:3d}  NO PRIOR")

            _sanity_check(priors, season)

            out_path = _write_json(priors, season, fit_date)
            print(f"  Written → {out_path.relative_to(_PROJECT_ROOT)}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fit EB starter rate priors per age band × season"
    )
    parser.add_argument(
        "--season",
        type=int,
        action="append",
        dest="seasons",
        metavar="YEAR",
        help="Season(s) to fit (repeat for multiple). Default: all 2016–current.",
    )
    args = parser.parse_args()
    seasons = (
        args.seasons
        if args.seasons
        else list(range(_FIRST_SEASON, date.today().year + 1))
    )
    main(seasons)
