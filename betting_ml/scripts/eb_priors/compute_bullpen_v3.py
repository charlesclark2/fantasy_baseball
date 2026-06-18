"""compute_bullpen_v3.py — Story E2.1b: deepened bullpen team posterior (`bullpen_v3`).

WHY (the ⭐ E1 finding)
----------------------
The E1.3 clustered-importance audit (2026-06-18) ranked bullpen EB quality
(`home/away_bp_eb_xwoba`) #1/#2 on EVERY target. That dominant feature is today the
STATIC team EB from `eb_bullpen_team_posteriors` (compute_bullpen_posteriors.py), which
aggregates per-reliever EB posteriors **weighted by `outs_in_game` = the outs each
reliever actually recorded THAT night.** The EB *values* are as-of-safe (season-to-date
< game_date), but the **weighting uses tonight's realized usage**, which is unknown
pre-game — a subtle leak in the program's single most important feature.

`bullpen_v3` replaces those leaky weights with an **expected** composition weight:

    w_i = expected_leverage_i (trailing-30d aLI/leverage, as-of) × availability_i(rest/fatigue)

so the team posterior reflects the pen *likely to actually pitch* tonight — closers/
high-leverage arms up, projected-unavailable (back-to-back / fatigued) arms down — using
ONLY information available before first pitch. The leak fix IS the composition weighting
(per the E2.1b design decision). It also carries the available pen's **L/R platoon split**
(team handedness channel) and availability diagnostics for E2.1 / E6.3.

DESIGN (cost-aware, §6)
-----------------------
The heavy pitch-level rollup runs ONCE per backfill and produces a **per-reliever cache**
(`build_per_reliever_frame` → parquet): for each (game_pk, team, reliever) it stores the
inputs needed to form an EB posterior at ANY shrinkage `k` — prior (μ₀, σ₀), batters-faced,
observed rate, expected-leverage weight, rest/fatigue. A pure-Python `aggregate_team_v3`
then forms the team posterior for any `k`/availability profile with NO further Snowflake —
so the E1.1 purged-CV `k`-sweep (eval_bullpen_v3_cv.py) is cheap and the writer materialises
only the chosen `k`.

LEAKAGE GUARD: every pitch-level window is strictly `game_date < this game's date`. The
expected-leverage pool is the team's trailing-30d relief appearances; no tonight-usage
column enters the weight.

CONTRACT-GUARD: the emitted columns are baseball-only (market-blind, Principle 3); asserted
via `betting_ml.utils.market_blind.assert_market_blind`.

Writes:
    baseball_data.betting.eb_bullpen_team_posteriors_v3   (game_pk, team)

Usage:
    # 1. heavy: build the per-reliever cache for a season (operator, >1 min Snowflake)
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_v3.py --backfill-season 2024
    # 2. (after the CV k-sweep picks k) write the team table at the chosen k:
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_v3.py --backfill-season 2024 --shrinkage-k 1.0 --write
    # single live date (daily Dagster op scores only the upcoming slate):
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_v3.py --game-date 2026-06-18 --write
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.market_blind import assert_market_blind
from betting_ml.scripts.eb_priors.compute_bullpen_posteriors import (
    _assign_age_band,
    _assign_leverage_role,
    _get_prior_cell,
    _load_normalized_ali_map,
    _load_prior,
)

# Local cache for the per-reliever frame (the heavy-query output → fast k-sweep input).
_CACHE_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v3"
_MODEL_VERSION = "bullpen_v3"

_MIN_BF = 0  # pool relievers with 0 season-to-date BF fall back to prior_only (prior μ)

# ── Availability profile (rest/fatigue → weight multiplier, in [0, 1]) ──────────
# Pre-game only. rest_days = datediff(last relief appearance, this game) ≥ 1 (strictly
# prior). Projected-unavailable arms are DOWN-weighted, not dropped, so the pen is a soft
# expectation rather than a hard roster guess (we cannot know the manager's actual card).
_REST_AVAIL = {
    # rest_days: multiplier
    1: 0.45,   # pitched yesterday (back-to-back risk)
    2: 0.90,   # one day of rest
}
_REST_AVAIL_DEFAULT = 1.0      # ≥3 days rest, or no appearance in the trailing 30d (fresh)
# Extra fatigue penalty: worked ≥2 of the prior 3 days (heavy recent usage).
_HEAVY_USE_PENALTY = 0.70      # multiply availability by this when appearances_prev_3d ≥ 2
_PROJ_UNAVAIL_THRESHOLD = 0.50  # availability below this counts as "projected unavailable"


def _availability_factor(rest_days: float | None, appearances_prev_3d: float | None) -> float:
    """Pre-game availability multiplier in [0, 1] from rest + recent-usage fatigue."""
    rd = None if rest_days is None or (isinstance(rest_days, float) and np.isnan(rest_days)) else int(rest_days)
    base = _REST_AVAIL.get(rd, _REST_AVAIL_DEFAULT) if rd is not None else _REST_AVAIL_DEFAULT
    ap3 = 0 if appearances_prev_3d is None or (isinstance(appearances_prev_3d, float) and np.isnan(appearances_prev_3d)) else int(appearances_prev_3d)
    if ap3 >= 2:
        base *= _HEAVY_USE_PENALTY
    return float(max(0.0, min(1.0, base)))


# ── EB posterior at an arbitrary shrinkage k (vectorised) ──────────────────────

def _eb_posterior_k(
    mu0: np.ndarray,
    sigma0: np.ndarray,
    bf: np.ndarray,
    obs_rate: np.ndarray,
    k: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Normal-Normal EB posterior with prior precision scaled by `k` (vectorised).

    k > 1 ⇒ stronger prior ⇒ more shrinkage toward μ₀; k = 1 reproduces the
    compute_bullpen_posteriors.py default. Where bf == 0 the posterior is the prior.
    sigma_meas² ≈ obs_rate·(1-obs_rate)/bf (binomial SE), matching the static model.
    """
    mu0 = np.asarray(mu0, float)
    sigma0 = np.asarray(sigma0, float)
    bf = np.asarray(bf, float)
    obs_rate = np.asarray(obs_rate, float)

    out_mean = mu0.copy()
    out_std = sigma0.copy()
    has_obs = bf > 0
    if np.any(has_obs):
        sig0 = np.clip(sigma0[has_obs], 1e-6, None)
        rate = obs_rate[has_obs]
        n = bf[has_obs]
        sig_meas_sq = np.clip(rate * (1.0 - rate), 1e-4, None) / n
        prec_prior = k / (sig0 ** 2)
        prec_obs = 1.0 / sig_meas_sq
        post_mean = (mu0[has_obs] * prec_prior + rate * prec_obs) / (prec_prior + prec_obs)
        post_var = 1.0 / (prec_prior + prec_obs)
        out_mean[has_obs] = post_mean
        out_std[has_obs] = np.sqrt(np.clip(post_var, 0.0, None))
    return out_mean, out_std


# ── Pure-Python team aggregation (no Snowflake; importable + testable) ──────────

_V3_VALUE_COLS = [
    "team_eb_bullpen_xwoba_v3",
    "team_eb_bullpen_uncertainty_v3",
    "team_eb_bullpen_xwoba_vs_lhb_v3",
    "team_eb_bullpen_xwoba_vs_rhb_v3",
    "pen_available_arms",
    "pen_projected_unavailable_arms",
    "pen_effective_size",
    "pen_avg_rest_days",
]


def aggregate_team_v3(
    per_reliever: pd.DataFrame,
    shrinkage_k: float = 1.0,
    weight_mode: str = "expected",
) -> pd.DataFrame:
    """Aggregate per-reliever EB rows → per (game_pk, team) `bullpen_v3` posterior.

    `weight_mode`:
      - "expected" (default, the v3 model): w = expected_leverage × availability(rest, fatigue)
        — the leakage-safe analogue of the incumbent's outs weighting.
      - "equal": w = 1 for every pool arm — the DE-LEAKED CONTROL. Same leakage-safe roster +
        per-reliever EBs as v3, but a plain average instead of leverage/availability weighting.
        Isolates how much of any static-vs-v3 NLL gap is the incumbent's within-game leak
        (roster+outs peek the eval game) vs. v3's weighting choice. If equal ≈ expected ≪
        leaky-static, the gap is the leak, not v3.
    The team xwOBA/uncertainty are w-weighted means of the per-reliever EB posteriors recomputed
    at `shrinkage_k`. PURE — no Snowflake — so the CV `k`-sweep / control arm are cheap.

    Required `per_reliever` columns:
        game_pk, game_date, season, team, pitcher_id,
        prior_mu_xwoba, prior_sigma_xwoba, bf, xwoba_obs,
        expected_leverage, rest_days, appearances_prev_3d,
        bp_xwoba_vs_lhb_30d, bp_xwoba_vs_rhb_30d   (team-level handedness, repeated per row)
    """
    if per_reliever.empty:
        return pd.DataFrame(columns=["game_pk", "game_date", "season", "team", "n_relievers"] + _V3_VALUE_COLS)

    df = per_reliever.copy()
    eb_mean, eb_std = _eb_posterior_k(
        df["prior_mu_xwoba"].to_numpy(float),
        df["prior_sigma_xwoba"].to_numpy(float),
        df["bf"].to_numpy(float),
        df["xwoba_obs"].fillna(df["prior_mu_xwoba"]).to_numpy(float),
        shrinkage_k,
    )
    df["_eb_xwoba"] = eb_mean
    df["_eb_unc"] = eb_std
    df["_avail"] = [
        _availability_factor(r, a)
        for r, a in zip(df["rest_days"], df["appearances_prev_3d"])
    ]
    if weight_mode == "equal":
        # De-leaked control: equal weight over the leakage-safe pool (availability still
        # reported in the diagnostics, but not used to weight).
        df["_w"] = 1.0
    elif weight_mode == "expected":
        lev = df["expected_leverage"].to_numpy(float)
        lev = np.where(np.isfinite(lev) & (lev > 0), lev, 0.0)
        df["_w"] = lev * df["_avail"].to_numpy(float)
    else:
        raise ValueError(f"unknown weight_mode {weight_mode!r} (expected 'expected' or 'equal')")

    rows: list[dict] = []
    for (game_pk, team), g in df.groupby(["game_pk", "team"], sort=False):
        w = g["_w"].to_numpy(float)
        sw = w.sum()
        if sw <= 0:                       # no expected-leverage signal → equal-weight fallback
            w = np.ones(len(g))
            sw = float(len(g))
        xw = np.average(g["_eb_xwoba"].to_numpy(float), weights=w)
        unc = np.average(g["_eb_unc"].to_numpy(float), weights=w)
        eff = float(sw ** 2 / np.sum(w ** 2)) if np.sum(w ** 2) > 0 else float(len(g))
        avail = g["_avail"].to_numpy(float)
        n_avail = int(np.sum(avail >= _PROJ_UNAVAIL_THRESHOLD))
        n_unavail = int(np.sum(avail < _PROJ_UNAVAIL_THRESHOLD))
        rest = pd.to_numeric(g["rest_days"], errors="coerce")
        rows.append({
            "game_pk": game_pk,
            "game_date": g["game_date"].iloc[0],
            "season": int(g["season"].iloc[0]),
            "team": team,
            "n_relievers": int(len(g)),
            "team_eb_bullpen_xwoba_v3": round(float(xw), 4),
            "team_eb_bullpen_uncertainty_v3": round(float(unc), 4),
            # Platoon channel (a): leakage-safe team L/R 30d xwOBA carried onto the v3 row.
            "team_eb_bullpen_xwoba_vs_lhb_v3": _round_or_none(g["bp_xwoba_vs_lhb_30d"].iloc[0]),
            "team_eb_bullpen_xwoba_vs_rhb_v3": _round_or_none(g["bp_xwoba_vs_rhb_30d"].iloc[0]),
            "pen_available_arms": n_avail,
            "pen_projected_unavailable_arms": n_unavail,
            "pen_effective_size": round(eff, 3),
            "pen_avg_rest_days": _round_or_none(rest.mean()),
        })
    return pd.DataFrame(rows)


def _round_or_none(v: Any, nd: int = 4) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, nd)


# ── Heavy Snowflake loader: per-reliever expected-pen frame ────────────────────

def _load_expected_pen(conn, game_date: date, season: int) -> pd.DataFrame:
    """Per (game_pk, pitching_team, pitcher_id) trailing-30d relief pool for games on
    `game_date`, with expected-leverage weight, rest_days, recent-usage fatigue, age.

    Pool = relievers with ≥1 relief appearance in the prior 30 days for that team
    (leakage guard: appearance date STRICTLY < the game's date). This mirrors
    mart_reliever_top3_availability's `rolling` CTE but keeps ALL arms (not just top-3).
    """
    cur = conn.cursor()
    cur.execute(
        """
        with target_games as (
            -- mart_game_spine = completed + today's SCHEDULED games (A1.11), so the daily
            -- live op scores the upcoming slate (whose games are not yet in stg_batter_pitches).
            select distinct game_pk, game_date::date as game_date, home_team, away_team
            from baseball_data.betting.mart_game_spine
            where game_type = 'R' and game_date = %(game_date)s
        ),
        reliever_pitches as (
            select
                bp.game_pk,
                bp.game_date::date as game_date,
                bp.pitcher_id,
                case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end as pitching_team,
                bp.pitcher_age,
                abs(ppe.delta_home_win_exp) as abs_delta
            from baseball_data.betting.stg_batter_pitches bp
            join baseball_data.betting.mart_pitch_play_event ppe on ppe.pitch_sk = bp.pitch_sk
            left join baseball_data.betting.mart_starting_pitcher_game_log s
                on  s.game_pk = bp.game_pk and s.pitcher_id = bp.pitcher_id
                and s.pitching_team = (case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end)
            where bp.game_type = 'R'
              and bp.game_year between %(season)s - 1 and %(season)s
              and ppe.delta_home_win_exp is not null
              and s.pitcher_id is null
        ),
        reliever_day as (
            select pitching_team, pitcher_id, game_date,
                   sum(abs_delta)        as day_leverage,
                   count(*)              as day_pitches,
                   mode(pitcher_age)     as pitcher_age
            from reliever_pitches
            group by pitching_team, pitcher_id, game_date
        ),
        -- one (target game) × (every prior-30d relief day for that team) edge
        pool as (
            select
                tg.game_pk,
                tg.game_date,
                rd.pitching_team,
                rd.pitcher_id,
                rd.game_date as appearance_date,
                rd.day_leverage,
                rd.day_pitches,
                rd.pitcher_age
            from target_games tg
            join reliever_day rd
                on  rd.pitching_team in (tg.home_team, tg.away_team)
                and rd.game_date <  tg.game_date
                and rd.game_date >= dateadd('day', -30, tg.game_date)
        )
        select
            game_pk,
            game_date,
            pitching_team,
            pitcher_id,
            mode(pitcher_age)                                               as pitcher_age,
            sum(day_leverage)                                              as expected_leverage,
            datediff('day', max(appearance_date), game_date)              as rest_days,
            count(distinct case when appearance_date >= dateadd('day', -3, game_date)
                                then appearance_date end)                  as appearances_prev_3d,
            sum(case when appearance_date >= dateadd('day', -2, game_date)
                     then day_pitches else 0 end)                         as pitches_prev_2d
        from pool
        group by game_pk, game_date, pitching_team, pitcher_id
        """,
        {"game_date": game_date.isoformat(), "season": season},
    )
    cols = [d[0].lower() for d in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    cur.close()
    return df


def _load_season_to_date_xwoba(conn, pitcher_ids: list[str], game_date: date, season: int) -> dict[str, dict]:
    """Season-to-date relief xwOBA (numerator/denominator) + BF per reliever, strictly
    < game_date. Reused weight-free shape of compute_bullpen_posteriors._load_season_to_date_stats."""
    if not pitcher_ids:
        return {}
    ids_sql = ", ".join(f"'{p}'" for p in pitcher_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        with reliever_pitches as (
            select bp.pitcher_id, bp.game_pk, bp.at_bat_number,
                   bp.plate_appearance_event, bp.xwoba, bp.woba_value, bp.woba_denom
            from baseball_data.betting.stg_batter_pitches bp
            left join baseball_data.betting.mart_starting_pitcher_game_log s
                on  s.game_pk = bp.game_pk and s.pitcher_id = bp.pitcher_id
                and s.pitching_team = (case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end)
            where bp.game_type = 'R' and bp.game_year = %(season)s
              and bp.game_date < %(game_date)s
              and s.pitcher_id is null
              and bp.pitcher_id::varchar in ({ids_sql})
        ),
        pa_level as (
            select pitcher_id, game_pk, at_bat_number,
                max(coalesce(woba_denom, 0)) as woba_denom,
                sum(case when woba_denom = 1 then coalesce(xwoba, woba_value) else 0 end) as xwoba_num
            from reliever_pitches
            group by pitcher_id, game_pk, at_bat_number
        )
        select pitcher_id, count(*) as batters_faced,
               sum(xwoba_num) as xwoba_numerator, sum(woba_denom) as xwoba_denom
        from pa_level group by pitcher_id
        """,
        {"season": season, "game_date": game_date.isoformat()},
    )
    cols = [d[0].lower() for d in cur.description]
    out: dict[str, dict] = {}
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        out[str(d["pitcher_id"])] = d
    cur.close()
    return out


def _load_handedness(conn, game_date: date) -> dict[tuple[str, str], dict]:
    """Team-level rolling-30d bullpen L/R xwOBA per (game_pk, team) for games on game_date."""
    cur = conn.cursor()
    cur.execute(
        """
        select game_pk::varchar as game_pk, team_abbrev,
               bp_xwoba_vs_lhb_30d, bp_xwoba_vs_rhb_30d
        from baseball_data.betting.mart_bullpen_handedness_splits
        where game_date = %(game_date)s
        """,
        {"game_date": game_date.isoformat()},
    )
    out: dict[tuple[str, str], dict] = {}
    for gp, team, lhb, rhb in cur.fetchall():
        out[(str(gp), team)] = {
            "bp_xwoba_vs_lhb_30d": float(lhb) if lhb is not None else None,
            "bp_xwoba_vs_rhb_30d": float(rhb) if rhb is not None else None,
        }
    cur.close()
    return out


def build_per_reliever_frame(
    conn,
    game_date: date,
    season: int,
    priors: dict,
    prior_ali_map: dict[int, float],
) -> pd.DataFrame:
    """Assemble the per-(game_pk, team, reliever) cache row for one game date.

    Joins: expected-pen pool (leverage/rest/fatigue/age) ⋈ season-to-date xwOBA ⋈ prior
    cell (role from prior-season aLI + age band) ⋈ team handedness splits. The output is
    k-agnostic — aggregate_team_v3 forms the posterior for any shrinkage k.
    """
    pool = _load_expected_pen(conn, game_date, season)
    if pool.empty:
        return pool

    pool["pitcher_id"] = pool["pitcher_id"].astype(str)
    pids = pool["pitcher_id"].unique().tolist()
    std = _load_season_to_date_xwoba(conn, pids, game_date, season)
    hand = _load_handedness(conn, game_date)

    recs: list[dict] = []
    for r in pool.itertuples(index=False):
        pid = str(r.pitcher_id)
        pid_int = int(float(pid))
        role = _assign_leverage_role(prior_ali_map[pid_int]) if pid_int in prior_ali_map else "no_prior_season"
        age_band = _assign_age_band(r.pitcher_age)
        cell = _get_prior_cell(priors, "xwoba_against", role, age_band)
        if cell is None:
            continue  # no usable prior for this (role, age) — skip (rare)

        s = std.get(pid, {})
        bf = float(s.get("batters_faced", 0) or 0)
        xnum = float(s.get("xwoba_numerator", 0) or 0)
        xden = float(s.get("xwoba_denom", 0) or 0)
        xwoba_obs = xnum / xden if xden > 0 else None

        h = hand.get((str(r.game_pk), r.pitching_team), {})
        recs.append({
            "game_pk": str(r.game_pk),
            "game_date": r.game_date,
            "season": season,
            "team": r.pitching_team,
            "pitcher_id": pid,
            "leverage_role": role,
            "age_band": age_band,
            "prior_mu_xwoba": float(cell["mu"]),
            "prior_sigma_xwoba": float(cell["sigma"]),
            "bf": bf,
            "xwoba_obs": xwoba_obs,
            "expected_leverage": float(r.expected_leverage or 0.0),
            "rest_days": (None if r.rest_days is None else float(r.rest_days)),
            "appearances_prev_3d": float(r.appearances_prev_3d or 0),
            "pitches_prev_2d": float(r.pitches_prev_2d or 0),
            "bp_xwoba_vs_lhb_30d": h.get("bp_xwoba_vs_lhb_30d"),
            "bp_xwoba_vs_rhb_30d": h.get("bp_xwoba_vs_rhb_30d"),
        })
    return pd.DataFrame(recs)


# ── Snowflake DDL + write (team v3 table) ──────────────────────────────────────

def _ensure_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_bullpen_team_posteriors_v3 (
            game_pk                          VARCHAR(20) NOT NULL,
            game_date                        DATE        NOT NULL,
            season                           INTEGER     NOT NULL,
            team                             VARCHAR(10) NOT NULL,
            n_relievers                      INTEGER,
            team_eb_bullpen_xwoba_v3         FLOAT,
            team_eb_bullpen_uncertainty_v3   FLOAT,
            team_eb_bullpen_xwoba_vs_lhb_v3  FLOAT,
            team_eb_bullpen_xwoba_vs_rhb_v3  FLOAT,
            pen_available_arms               INTEGER,
            pen_projected_unavailable_arms   INTEGER,
            pen_effective_size               FLOAT,
            pen_avg_rest_days                FLOAT,
            shrinkage_k                      FLOAT,
            fit_date                         DATE,
            run_id                           VARCHAR(36)
        )
        """
    )


def _s(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return str(v)


def _write_team_v3(conn, team_df: pd.DataFrame, shrinkage_k: float) -> None:
    if team_df.empty:
        print("  nothing to write (empty team frame).")
        return
    run_id = str(uuid.uuid4())
    fit_date = date.today().isoformat()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        """
        CREATE OR REPLACE TEMPORARY TABLE baseball_data.betting.tmp_eb_bullpen_team_v3 (
            game_pk VARCHAR, game_date VARCHAR, season VARCHAR, team VARCHAR,
            n_relievers VARCHAR, team_eb_bullpen_xwoba_v3 VARCHAR,
            team_eb_bullpen_uncertainty_v3 VARCHAR, team_eb_bullpen_xwoba_vs_lhb_v3 VARCHAR,
            team_eb_bullpen_xwoba_vs_rhb_v3 VARCHAR, pen_available_arms VARCHAR,
            pen_projected_unavailable_arms VARCHAR, pen_effective_size VARCHAR,
            pen_avg_rest_days VARCHAR, shrinkage_k VARCHAR, fit_date VARCHAR, run_id VARCHAR
        )
        """
    )
    data = [
        (
            _s(r.game_pk), _s(r.game_date), _s(r.season), _s(r.team),
            _s(r.n_relievers), _s(r.team_eb_bullpen_xwoba_v3),
            _s(r.team_eb_bullpen_uncertainty_v3), _s(r.team_eb_bullpen_xwoba_vs_lhb_v3),
            _s(r.team_eb_bullpen_xwoba_vs_rhb_v3), _s(r.pen_available_arms),
            _s(r.pen_projected_unavailable_arms), _s(r.pen_effective_size),
            _s(r.pen_avg_rest_days), _s(shrinkage_k), fit_date, run_id,
        )
        for r in team_df.itertuples(index=False)
    ]
    cur.executemany(
        "INSERT INTO baseball_data.betting.tmp_eb_bullpen_team_v3 "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        data,
    )
    cur.execute(
        """
        MERGE INTO baseball_data.betting.eb_bullpen_team_posteriors_v3 tgt
        USING (
            SELECT game_pk::VARCHAR(20) game_pk, game_date::DATE game_date, season::INTEGER season,
                   team::VARCHAR(10) team, n_relievers::INTEGER n_relievers,
                   team_eb_bullpen_xwoba_v3::FLOAT team_eb_bullpen_xwoba_v3,
                   team_eb_bullpen_uncertainty_v3::FLOAT team_eb_bullpen_uncertainty_v3,
                   team_eb_bullpen_xwoba_vs_lhb_v3::FLOAT team_eb_bullpen_xwoba_vs_lhb_v3,
                   team_eb_bullpen_xwoba_vs_rhb_v3::FLOAT team_eb_bullpen_xwoba_vs_rhb_v3,
                   pen_available_arms::INTEGER pen_available_arms,
                   pen_projected_unavailable_arms::INTEGER pen_projected_unavailable_arms,
                   pen_effective_size::FLOAT pen_effective_size,
                   pen_avg_rest_days::FLOAT pen_avg_rest_days,
                   shrinkage_k::FLOAT shrinkage_k, fit_date::DATE fit_date, run_id::VARCHAR(36) run_id
            FROM baseball_data.betting.tmp_eb_bullpen_team_v3
        ) src
        ON tgt.game_pk = src.game_pk AND tgt.team = src.team
        WHEN MATCHED THEN UPDATE SET
            game_date = src.game_date, season = src.season, n_relievers = src.n_relievers,
            team_eb_bullpen_xwoba_v3 = src.team_eb_bullpen_xwoba_v3,
            team_eb_bullpen_uncertainty_v3 = src.team_eb_bullpen_uncertainty_v3,
            team_eb_bullpen_xwoba_vs_lhb_v3 = src.team_eb_bullpen_xwoba_vs_lhb_v3,
            team_eb_bullpen_xwoba_vs_rhb_v3 = src.team_eb_bullpen_xwoba_vs_rhb_v3,
            pen_available_arms = src.pen_available_arms,
            pen_projected_unavailable_arms = src.pen_projected_unavailable_arms,
            pen_effective_size = src.pen_effective_size, pen_avg_rest_days = src.pen_avg_rest_days,
            shrinkage_k = src.shrinkage_k, fit_date = src.fit_date, run_id = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            game_pk, game_date, season, team, n_relievers, team_eb_bullpen_xwoba_v3,
            team_eb_bullpen_uncertainty_v3, team_eb_bullpen_xwoba_vs_lhb_v3,
            team_eb_bullpen_xwoba_vs_rhb_v3, pen_available_arms, pen_projected_unavailable_arms,
            pen_effective_size, pen_avg_rest_days, shrinkage_k, fit_date, run_id
        ) VALUES (
            src.game_pk, src.game_date, src.season, src.team, src.n_relievers,
            src.team_eb_bullpen_xwoba_v3, src.team_eb_bullpen_uncertainty_v3,
            src.team_eb_bullpen_xwoba_vs_lhb_v3, src.team_eb_bullpen_xwoba_vs_rhb_v3,
            src.pen_available_arms, src.pen_projected_unavailable_arms,
            src.pen_effective_size, src.pen_avg_rest_days, src.shrinkage_k, src.fit_date, src.run_id
        )
        """
    )
    cur.close()
    print(f"  wrote {len(team_df)} (game_pk, team) v3 rows (k={shrinkage_k}).")


# ── Cache I/O ──────────────────────────────────────────────────────────────────

def _cache_path(season: int) -> Path:
    return _CACHE_DIR / f"per_reliever_{season}.parquet"


# ── Orchestration ──────────────────────────────────────────────────────────────

def _game_dates_for_season(conn, season: int) -> list[date]:
    cur = conn.cursor()
    cur.execute(
        """
        select distinct game_date::date gd
        from baseball_data.betting.stg_batter_pitches
        where game_type = 'R' and game_year = %(season)s order by gd
        """,
        {"season": season},
    )
    out = [r[0] if isinstance(r[0], date) else datetime.strptime(str(r[0])[:10], "%Y-%m-%d").date()
           for r in cur.fetchall()]
    cur.close()
    return out


def run_backfill_season(season: int, shrinkage_k: float, write: bool) -> None:
    print(f"\n═══ bullpen_v3 per-reliever cache — season {season} ═══")
    priors = _load_prior(season)
    conn = get_snowflake_connection()
    try:
        print(f"  loading prior-season ({season - 1}) aLI map (leverage roles)...")
        prior_ali_map = _load_normalized_ali_map(conn, season - 1)
        print(f"  {len(prior_ali_map)} relievers in prior-season aLI map")

        dates = _game_dates_for_season(conn, season)
        print(f"  {len(dates)} game dates to process")
        frames: list[pd.DataFrame] = []
        for i, gd in enumerate(dates, 1):
            frames.append(build_per_reliever_frame(conn, gd, season, priors, prior_ali_map))
            if i % 50 == 0 or i == len(dates):
                tot = sum(len(f) for f in frames)
                print(f"  [{i}/{len(dates)}] {gd}  cumulative reliever-rows: {tot:,}")

        per_reliever = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        per_reliever.to_parquet(_cache_path(season))
        print(f"\n  cached {len(per_reliever):,} per-reliever rows → {_cache_path(season).relative_to(_PROJECT_ROOT)}")

        # CONTRACT-GUARD: the emitted team columns are baseball-only.
        team = aggregate_team_v3(per_reliever, shrinkage_k=shrinkage_k)
        assert_market_blind(team.columns, context=f"{_MODEL_VERSION} team output (season {season})")
        print(f"  CONTRACT-GUARD: market-blind ✅  ({len(team)} team-game rows)")
        if not team.empty:
            print(f"  v3 team xwOBA: mean={team['team_eb_bullpen_xwoba_v3'].mean():.4f}  "
                  f"avg available arms={team['pen_available_arms'].mean():.2f}  "
                  f"avg unavailable={team['pen_projected_unavailable_arms'].mean():.2f}  "
                  f"avg eff size={team['pen_effective_size'].mean():.2f}")

        if write:
            _write_team_v3(conn, team, shrinkage_k)
        else:
            print("  [no --write] cache written; team table NOT materialised "
                  "(run the CV k-sweep first, then re-run with --write --shrinkage-k <k>).")
    finally:
        conn.close()


def run_single_date(game_date: date, shrinkage_k: float, write: bool) -> None:
    season = game_date.year
    priors = _load_prior(season)
    conn = get_snowflake_connection()
    try:
        prior_ali_map = _load_normalized_ali_map(conn, season - 1)
        per_reliever = build_per_reliever_frame(conn, game_date, season, priors, prior_ali_map)
        if per_reliever.empty:
            print(f"  no relief pool for {game_date} — nothing to write.")
            return
        team = aggregate_team_v3(per_reliever, shrinkage_k=shrinkage_k)
        assert_market_blind(team.columns, context=f"{_MODEL_VERSION} team output ({game_date})")
        print(f"  {game_date}: {len(team)} team-game v3 rows (k={shrinkage_k})")
        if write:
            _write_team_v3(conn, team, shrinkage_k)
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Story E2.1b — bullpen_v3 deepened team posterior")
    ap.add_argument("--game-date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    ap.add_argument("--backfill-season", type=int, dest="backfill_season", metavar="YEAR", default=None)
    ap.add_argument("--shrinkage-k", type=float, default=1.0,
                    help="Prior-precision multiplier for the per-reliever EB (k>1 ⇒ more shrink). "
                         "Default 1.0 = compute_bullpen_posteriors parity. Pick via eval_bullpen_v3_cv.py.")
    ap.add_argument("--write", action="store_true", help="Materialise the team table (MERGE).")
    args = ap.parse_args()

    if args.backfill_season:
        run_backfill_season(args.backfill_season, args.shrinkage_k, args.write)
    else:
        run_single_date(args.game_date or date.today(), args.shrinkage_k, args.write)


if __name__ == "__main__":
    main()
