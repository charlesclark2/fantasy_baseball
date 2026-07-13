"""
fit_bullpen_priors.py — Empirical Bayes bullpen quality prior fitting (Epic 6A.1)

Fits conjugate priors for three per-reliever rate statistics stratified by
leverage role × age band × season:

    xwOBA-against, K%, BB%  →  Normal-Normal  (method of moments: μ₀, σ₀)

Leverage role buckets (based on prior-season average Leverage Index):
    closer_tier:       aLI ≥ 1.5
    high_leverage:     1.0 ≤ aLI < 1.5
    low_leverage:      aLI < 1.0
    no_prior_season:   relievers with no prior-season MLB appearances
                       (use age-band-only prior)

Age bands (reliever aging curves are steeper than starters):
    lt_26, 26_30, 31_34, gte_35

Minimum sample to qualify for role assignment:
    ≥ 20 appearances OR ≥ 25 IP in the prior season

Cells with n_relievers < MIN_CELL_RELIEVERS fall back to the
leverage-role-only prior (age band collapsed) and are flagged.

Output:
    betting_ml/models/eb_priors/bullpen_priors_{season}.json

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_bullpen_priors.py
    uv run python betting_ml/scripts/eb_priors/fit_bullpen_priors.py --season 2024
    uv run python betting_ml/scripts/eb_priors/fit_bullpen_priors.py --season 2021 --season 2022
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

# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_APPEARANCES = 20       # ≥ 20 games OR ≥ 25 IP to qualify for role assignment
_MIN_IP = 25
_MIN_BF_FOR_STATS = 30      # minimum batters faced in target season to be included in prior fit
_MIN_CELL_RELIEVERS = 10    # minimum relievers to fit a stratified cell (else fall back)

_LEVERAGE_ROLES = ("closer_tier", "high_leverage", "low_leverage", "no_prior_season")

_AGE_BANDS = ("lt_26", "26_30", "31_34", "gte_35")

_METRICS = ("xwoba_against", "k_pct", "bb_pct")

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_prior_season_ali(conn, prior_season: int, duck=None) -> dict[int, dict]:
    """
    Return per-reliever normalized aLI (average Leverage Index) for the prior season.

    Raw aLI = mean of sum(|delta_home_win_exp|) per at-bat.
    Normalized aLI = raw_aLI / season_mean_raw_aLI, putting it on the traditional
    LI scale (1.0 = league-average situation, ≥1.5 = closer-tier).

    Starters are excluded using mart_starting_pitcher_game_log.
    Minimum qualification: ≥ MIN_APPEARANCES games in the prior season.

    Returns dict: {pitcher_id: {"ali": float (normalized), "appearances": int}}

    E11.20 phase 1.5: when `duck` is provided (--s3), this query — the script's ONLY
    mart_pitch_play_event read — runs on DuckDB over the S3 lakehouse.
    """
    sql = """
        with reliever_at_bats as (
            select
                bp.game_pk,
                bp.at_bat_number,
                bp.pitcher_id,
                case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end
                    as pitching_team,
                abs(ppe.delta_home_win_exp) as abs_delta
            from baseball_data.betting.stg_batter_pitches bp
            join baseball_data.betting.mart_pitch_play_event ppe
                on ppe.pitch_sk = bp.pitch_sk
            where bp.game_type = 'R'
              and bp.game_year  = %(season)s
              and ppe.delta_home_win_exp is not null
        ),
        starters as (
            select game_pk, pitcher_id, pitching_team
            from baseball_data.betting.mart_starting_pitcher_game_log
            where game_year = %(season)s
        ),
        reliever_only as (
            select rab.*
            from reliever_at_bats rab
            left join starters s
                on  s.game_pk       = rab.game_pk
                and s.pitcher_id    = rab.pitcher_id
                and s.pitching_team = rab.pitching_team
            where s.pitcher_id is null
        ),
        at_bat_scores as (
            select
                pitcher_id,
                game_pk,
                at_bat_number,
                sum(abs_delta) as ab_score
            from reliever_only
            group by pitcher_id, game_pk, at_bat_number
        ),
        -- Season-average at-bat score used for normalization
        season_avg as (
            select avg(ab_score) as season_mean_ab_score
            from at_bat_scores
        ),
        pitcher_season as (
            select
                pitcher_id,
                count(distinct game_pk) as appearances,
                avg(ab_score)           as raw_ali
            from at_bat_scores
            group by pitcher_id
        )
        select
            ps.pitcher_id,
            ps.appearances,
            ps.raw_ali / sa.season_mean_ab_score as normalized_ali
        from pitcher_season ps
        cross join season_avg sa
        where ps.appearances >= %(min_app)s
        """
    if duck is not None:
        from betting_ml.scripts.eb_priors import _lakehouse_duck
        duck_sql = (_lakehouse_duck.rewrite(sql)
                    .replace("%(season)s", str(int(prior_season)))
                    .replace("%(min_app)s", str(int(_MIN_APPEARANCES))))
        rows = duck.execute(duck_sql).fetchall()
    else:
        cur = conn.cursor()
        cur.execute(sql, {
            "season": prior_season,
            "min_app": _MIN_APPEARANCES,
        })
        rows = cur.fetchall()
        cur.close()
    result = {}
    for row in rows:
        result[int(row[0])] = {
            "ali": float(row[2]) if row[2] is not None else 0.0,
            "appearances": int(row[1]),
        }
    return result


def _load_season_reliever_stats(conn, season: int) -> list[dict]:
    """
    Season-level reliever stats for fitting priors.

    Returns one row per reliever with:
        pitcher_id, xwoba_against, k_pct, bb_pct, batters_faced, mode_age
    """
    cur = conn.cursor()
    cur.execute(
        """
        with reliever_pitches as (
            select
                bp.game_pk,
                bp.game_date,
                bp.pitcher_id,
                bp.at_bat_number,
                bp.pitcher_age,
                bp.plate_appearance_event,
                bp.xwoba,
                bp.woba_value,
                bp.woba_denom,
                case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end
                    as pitching_team
            from baseball_data.betting.stg_batter_pitches bp
            where bp.game_type = 'R'
              and bp.game_year  = %(season)s
        ),
        starters as (
            select game_pk, pitcher_id, pitching_team
            from baseball_data.betting.mart_starting_pitcher_game_log
            where game_year = %(season)s
        ),
        relievers as (
            select rp.*
            from reliever_pitches rp
            left join starters s
                on  s.game_pk       = rp.game_pk
                and s.pitcher_id    = rp.pitcher_id
                and s.pitching_team = rp.pitching_team
            where s.pitcher_id is null
        ),
        pa_level as (
            -- Collapse to plate-appearance level for rate stat computation
            select
                pitcher_id,
                game_pk,
                at_bat_number,
                any_value(pitcher_age)              as pitcher_age,
                max(case when plate_appearance_event in (
                    'strikeout', 'strikeout_double_play'
                ) then 1 else 0 end)                as is_strikeout,
                max(case when plate_appearance_event in (
                    'walk', 'intent_walk'
                ) then 1 else 0 end)                as is_walk,
                max(coalesce(woba_denom, 0))        as woba_denom,
                sum(case when woba_denom = 1
                    then coalesce(xwoba, woba_value)
                    else 0 end)                     as xwoba_numerator
            from relievers
            group by pitcher_id, game_pk, at_bat_number
        ),
        season_stats as (
            select
                pitcher_id,
                count(*)                                    as batters_faced,
                sum(is_strikeout)                           as strikeouts,
                sum(is_walk)                                as walks,
                sum(xwoba_numerator)                        as xwoba_numerator,
                sum(woba_denom)                             as xwoba_denom,
                mode(pitcher_age)                           as mode_age
            from pa_level
            group by pitcher_id
        )
        select
            pitcher_id,
            batters_faced,
            iff(xwoba_denom > 0, xwoba_numerator / xwoba_denom, null) as xwoba_against,
            iff(batters_faced > 0, strikeouts / batters_faced, null)  as k_pct,
            iff(batters_faced > 0, walks / batters_faced, null)       as bb_pct,
            mode_age
        from season_stats
        where batters_faced >= %(min_bf)s
          and xwoba_denom   > 0
        """,
        {"season": season, "min_bf": _MIN_BF_FOR_STATS},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


# ── Prior fitting ─────────────────────────────────────────────────────────────

def _assign_leverage_role(ali: float) -> str:
    if ali >= 1.5:
        return "closer_tier"
    if ali >= 1.0:
        return "high_leverage"
    return "low_leverage"


def _assign_age_band(age: int | float | None) -> str | None:
    if age is None:
        return None
    age = int(age)
    if age < 26:
        return "lt_26"
    if age <= 30:
        return "26_30"
    if age <= 34:
        return "31_34"
    return "gte_35"


def _fit_normal_mom(vals: list[float]) -> dict | None:
    n = len(vals)
    if n < 2:
        return None
    mu = float(np.mean(vals))
    sigma = float(np.std(vals, ddof=1))
    if sigma <= 0:
        sigma = 0.001
    return {"mu": round(mu, 5), "sigma": round(sigma, 5), "n_relievers": n}


def _build_priors(
    season_rows: list[dict],
    prior_ali_map: dict[int, dict],
) -> dict:
    """
    Fit Normal(μ, σ²) priors for each (metric, leverage_role, age_band) cell.

    Falls back to role-pooled (age-band collapsed) prior when a cell has
    fewer than MIN_CELL_RELIEVERS observations, flagged with "fallback": True.
    """
    # Collect values by (metric, role, age_band) and by (metric, role) for fallback
    cell_vals: dict[tuple, list[float]] = {}
    role_vals: dict[tuple, list[float]] = {}

    for row in season_rows:
        pid = int(row["pitcher_id"])
        age = row.get("mode_age")
        age_band = _assign_age_band(age)
        if age_band is None:
            continue

        # Assign leverage role from prior-season aLI
        if pid in prior_ali_map:
            role = _assign_leverage_role(prior_ali_map[pid]["ali"])
        else:
            role = "no_prior_season"

        for metric in _METRICS:
            v = row.get(metric)
            if v is None:
                continue
            v = float(v)
            if not (0.0 <= v <= 1.5):  # sanity gate — xwOBA can exceed 1.0 rarely
                continue
            cell_vals.setdefault((metric, role, age_band), []).append(v)
            role_vals.setdefault((metric, role), []).append(v)

    priors: dict = {}
    for metric in _METRICS:
        priors[metric] = {}
        for role in _LEVERAGE_ROLES:
            priors[metric][role] = {}
            role_prior = _fit_normal_mom(role_vals.get((metric, role), []))
            for age_band in _AGE_BANDS:
                cell = cell_vals.get((metric, role, age_band), [])
                if len(cell) >= _MIN_CELL_RELIEVERS:
                    fitted = _fit_normal_mom(cell)
                else:
                    fitted = role_prior
                    if fitted is not None:
                        fitted = {**fitted, "n_relievers": len(cell), "fallback": True}
                priors[metric][role][age_band] = fitted

    return priors


def _sanity_check(priors: dict, season: int) -> bool:
    """
    Verify xwOBA monotonicity: closer_tier < high_leverage < low_leverage.
    Better arms allow lower xwOBA. Warns but does not abort.
    """
    ok = True
    for age_band in _AGE_BANDS:
        closer = (priors.get("xwoba_against", {})
                       .get("closer_tier", {})
                       .get(age_band) or {}).get("mu")
        high   = (priors.get("xwoba_against", {})
                       .get("high_leverage", {})
                       .get(age_band) or {}).get("mu")
        low    = (priors.get("xwoba_against", {})
                       .get("low_leverage", {})
                       .get(age_band) or {}).get("mu")
        if closer is None or high is None or low is None:
            continue
        if not (closer <= high <= low):
            print(
                f"  WARNING [{season}] xwOBA monotonicity violated for age_band={age_band}: "
                f"closer={closer:.4f}  high={high:.4f}  low={low:.4f}"
            )
            ok = False
    return ok


# ── Output ────────────────────────────────────────────────────────────────────

def _write_json(priors: dict, season: int, fit_date: date, prior_season: int) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"bullpen_priors_{season}.json"
    payload = {
        "season":       season,
        "prior_season": prior_season,
        "fit_date":     fit_date.isoformat(),
        "priors":       priors,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main(seasons: list[int], use_s3: bool = False) -> None:
    duck = None
    if use_s3:
        # E11.20 phase 1.5: the aLI substrate reads from the S3 lakehouse via DuckDB.
        from betting_ml.scripts.eb_priors import _lakehouse_duck
        print("[--s3] Reading the aLI substrate from the S3 lakehouse via DuckDB...")
        duck = _lakehouse_duck.get_duckdb()
        _lakehouse_duck.register_views(duck)
    conn = get_snowflake_connection()
    try:
        for season in seasons:
            prior_season = season - 1
            print(f"\n── Season {season} (role assignments from {prior_season}) ─────────────")

            print(f"  Loading prior-season ({prior_season}) aLI per reliever...")
            prior_ali_map = _load_prior_season_ali(conn, prior_season, duck=duck)
            print(f"  {len(prior_ali_map)} relievers qualified for role assignment")

            print(f"  Loading season {season} reliever stats...")
            season_rows = _load_season_reliever_stats(conn, season)
            print(f"  {len(season_rows)} relievers with ≥{_MIN_BF_FOR_STATS} BF loaded")

            if not season_rows:
                print("  WARNING: no data — skipping season")
                continue

            # Role assignment diagnostics
            role_counts: dict[str, int] = {r: 0 for r in _LEVERAGE_ROLES}
            for row in season_rows:
                pid = int(row["pitcher_id"])
                role = (
                    _assign_leverage_role(prior_ali_map[pid]["ali"])
                    if pid in prior_ali_map
                    else "no_prior_season"
                )
                role_counts[role] += 1
            for role, cnt in role_counts.items():
                print(f"    {role:20s}: {cnt}")

            priors = _build_priors(season_rows, prior_ali_map)

            # Diagnostic: cell sizes and mu values
            for metric in _METRICS:
                for role in _LEVERAGE_ROLES:
                    for age_band in _AGE_BANDS:
                        cell = (priors.get(metric, {})
                                      .get(role, {})
                                      .get(age_band))
                        if cell:
                            flag = " [fallback]" if cell.get("fallback") else ""
                            print(
                                f"  {metric:15s}  {role:20s}  {age_band:6s}  "
                                f"n={cell['n_relievers']:3d}  mu={cell['mu']:.4f}  "
                                f"σ={cell['sigma']:.4f}{flag}"
                            )

            _sanity_check(priors, season)

            out_path = _write_json(priors, season, date.today(), prior_season)
            print(f"  Written → {out_path.relative_to(_PROJECT_ROOT)}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fit EB bullpen quality priors per leverage role × age band × season (Epic 6A.1)"
    )
    parser.add_argument(
        "--season",
        type=int,
        action="append",
        dest="seasons",
        metavar="YEAR",
        help="Season(s) to fit (repeat for multiple). Default: current year.",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="E11.20 phase 1.5: read the aLI substrate (mart_pitch_play_event join) from "
             "the S3 lakehouse via DuckDB instead of Snowflake. REQUIRED once the SF "
             "mart_pitch_* views are dropped.",
    )
    args = parser.parse_args()
    seasons = args.seasons if args.seasons else [date.today().year]
    main(seasons, use_s3=args.s3)
