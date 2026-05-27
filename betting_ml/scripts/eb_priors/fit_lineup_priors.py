"""
fit_lineup_priors.py — Empirical Bayes lineup rate prior fitting (Epic 4A.1)

Fits conjugate priors for four per-batter rate statistics stratified by
role × handedness × season:

    wOBA, K%, BB%  →  Beta-Binomial   (method of moments: α, β)
    ISO            →  Normal-Normal   (method of moments: μ₀, σ₀)

Role buckets:
    top    = batting slots 1–3
    middle = batting slots 4–6
    bottom = batting slots 7–9

Each (metric, role, handedness, season) cell is fit from batters whose
mode batting slot falls in that role bucket and whose mode handedness is
that hand.  Cells with fewer than MIN_CELL_BATTERS observations fall back
to the parent role prior (handedness-pooled).

Output is written to:
    betting_ml/models/eb_priors/lineup_priors_{season}.json

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_lineup_priors.py
    uv run python betting_ml/scripts/eb_priors/fit_lineup_priors.py --season 2024
    uv run python betting_ml/scripts/eb_priors/fit_lineup_priors.py --season 2021 --season 2022
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

_PA_MIN = 100          # minimum PA in FG leaderboard season row
_MIN_CELL_BATTERS = 10  # minimum batters to fit a stratified cell prior
_ROLES = {
    "top":    (1, 3),
    "middle": (4, 6),
    "bottom": (7, 9),
}
_HANDS = ("R", "L", "S")
_METRICS_BETA = ("woba", "k_pct", "bb_pct")
_METRIC_NORMAL = "iso"

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"


# ── Data loading ─────────────────────────────────────────────────────────────

def _load_batter_data(conn, season: int) -> list[dict]:
    """Pull season stats + mode batting slot + mode handedness for one season."""
    cur = conn.cursor()
    cur.execute(
        """
        WITH season_stats AS (
            SELECT
                mlbam_batter_id,
                pa,
                woba,
                k_pct,
                bb_pct,
                iso
            FROM baseball_data.betting.stg_fangraphs__hitting_leaderboard
            WHERE window_type = 'season'
              AND season       = %(season)s
              AND pa           >= %(pa_min)s
              AND mlbam_batter_id IS NOT NULL
              AND woba IS NOT NULL
              AND k_pct IS NOT NULL
              AND bb_pct IS NOT NULL
              AND iso IS NOT NULL
        ),
        batting_slots AS (
            SELECT
                player_id                    AS batter_id,
                mode(batting_order)          AS mode_batting_slot
            FROM baseball_data.betting.stg_statsapi_lineups
            WHERE year(official_date) = %(season)s
            GROUP BY player_id
        ),
        batter_hand AS (
            SELECT
                batter_id,
                mode(batter_hand)            AS mode_batter_hand
            FROM baseball_data.betting.mart_batter_rolling_stats
            WHERE game_year = %(season)s
            GROUP BY batter_id
        )
        SELECT
            ss.mlbam_batter_id,
            ss.pa,
            ss.woba,
            ss.k_pct,
            ss.bb_pct,
            ss.iso,
            bs.mode_batting_slot,
            bh.mode_batter_hand
        FROM season_stats ss
        JOIN batting_slots bs ON ss.mlbam_batter_id = bs.batter_id
        JOIN batter_hand   bh ON ss.mlbam_batter_id = bh.batter_id
        WHERE bs.mode_batting_slot IS NOT NULL
          AND bh.mode_batter_hand  IS NOT NULL
          AND bh.mode_batter_hand  IN ('R', 'L', 'S')
        """,
        {"season": season, "pa_min": _PA_MIN},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


# ── Prior fitting ─────────────────────────────────────────────────────────────

def _slot_to_role(slot: int) -> str | None:
    for role, (lo, hi) in _ROLES.items():
        if lo <= slot <= hi:
            return role
    return None


def _fit_beta_mom(vals: list[float]) -> dict | None:
    """Method-of-moments Beta(α, β) from a list of proportions in [0, 1]."""
    n = len(vals)
    if n < 2:
        return None
    p_bar = float(np.mean(vals))
    s_sq = float(np.var(vals, ddof=1))
    if s_sq <= 0 or p_bar <= 0 or p_bar >= 1:
        return None
    denom = p_bar * (1.0 - p_bar) / s_sq - 1.0
    if denom <= 0:
        # Over-dispersed relative to Beta — use very diffuse prior
        denom = 0.1
    alpha = p_bar * denom
    beta = (1.0 - p_bar) * denom
    return {"alpha": round(alpha, 4), "beta": round(beta, 4), "n_batters": n}


def _fit_normal_mom(vals: list[float]) -> dict | None:
    """Method-of-moments Normal(μ₀, σ₀) from a list of ISO values."""
    n = len(vals)
    if n < 2:
        return None
    mu = float(np.mean(vals))
    sigma = float(np.std(vals, ddof=1))
    if sigma <= 0:
        sigma = 0.01  # degenerate — use small floor
    return {"mu": round(mu, 4), "sigma": round(sigma, 4), "n_batters": n}


def _fit_cell(vals: list[float], metric: str) -> dict | None:
    if not vals:
        return None
    if metric in _METRICS_BETA:
        return _fit_beta_mom(vals)
    return _fit_normal_mom(vals)


def _build_priors(rows: list[dict]) -> dict:
    """
    Fit priors for every (metric, role, handedness) cell.

    Falls back to the role-level (handedness-pooled) prior when a
    stratified cell has fewer than MIN_CELL_BATTERS observations.
    """
    # Organise values by (metric, role, hand)
    cell_vals: dict[tuple, list[float]] = {}
    role_vals: dict[tuple, list[float]] = {}  # (metric, role) — pooled across hand

    for row in rows:
        slot = row.get("mode_batting_slot")
        hand = row.get("mode_batter_hand")
        role = _slot_to_role(int(slot)) if slot is not None else None
        if role is None or hand not in _HANDS:
            continue
        for metric in (*_METRICS_BETA, _METRIC_NORMAL):
            v = row.get(metric)
            if v is None:
                continue
            v = float(v)
            cell_vals.setdefault((metric, role, hand), []).append(v)
            role_vals.setdefault((metric, role), []).append(v)

    priors: dict = {}
    for metric in (*_METRICS_BETA, _METRIC_NORMAL):
        priors[metric] = {}
        for role in _ROLES:
            priors[metric][role] = {}
            role_prior = _fit_cell(role_vals.get((metric, role), []), metric)
            for hand in _HANDS:
                cell = cell_vals.get((metric, role, hand), [])
                if len(cell) >= _MIN_CELL_BATTERS:
                    fitted = _fit_cell(cell, metric)
                else:
                    # Not enough data — fall back to role-pooled prior
                    fitted = role_prior
                    if fitted is not None:
                        fitted = {**fitted, "n_batters": len(cell), "fallback": True}
                priors[metric][role][hand] = fitted

    return priors


# ── Output ────────────────────────────────────────────────────────────────────

def _write_json(priors: dict, season: int, fit_date: date) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"lineup_priors_{season}.json"
    payload = {
        "season":   season,
        "fit_date": fit_date.isoformat(),
        "priors":   priors,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main(seasons: list[int]) -> None:
    conn = get_snowflake_connection()
    try:
        for season in seasons:
            print(f"\n── Season {season} ──────────────────────────────────")
            rows = _load_batter_data(conn, season)
            print(f"  {len(rows)} qualified batters loaded")
            if not rows:
                print("  WARNING: no data — skipping season")
                continue

            priors = _build_priors(rows)

            # Diagnostic printout
            for metric in (*_METRICS_BETA, _METRIC_NORMAL):
                for role in _ROLES:
                    counts = {
                        h: (priors[metric][role][h] or {}).get("n_batters", 0)
                        for h in _HANDS
                    }
                    total = sum(counts.values())
                    print(f"  {metric:6s}  {role:6s}  n={total}  "
                          + "  ".join(f"{h}:{counts[h]}" for h in _HANDS))

            fit_date = date.today()
            out_path = _write_json(priors, season, fit_date)
            print(f"  Written → {out_path.relative_to(_PROJECT_ROOT)}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fit EB lineup rate priors per role × handedness × season"
    )
    parser.add_argument(
        "--season",
        type=int,
        action="append",
        dest="seasons",
        metavar="YEAR",
        help="Season(s) to fit (repeat for multiple). Default: current year.",
    )
    args = parser.parse_args()
    seasons = args.seasons if args.seasons else [date.today().year]
    main(seasons)
