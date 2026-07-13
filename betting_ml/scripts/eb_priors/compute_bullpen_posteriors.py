"""
compute_bullpen_posteriors.py — Per-reliever EB posterior computation (Epic 6A.2)

For each game on a given date, computes per-reliever EB posteriors for
xwOBA-against, K%, and BB% using Normal-Normal conjugate shrinkage.

Individual output grain: (game_pk, pitcher_id) → eb_bullpen_posteriors
Team output grain:       (game_pk, team)        → eb_bullpen_team_posteriors

Normal-Normal posterior:
    posterior_mean = (μ₀/σ₀² + n·x̄/σ_meas²) / (1/σ₀² + n/σ_meas²)
    posterior_var  = 1 / (1/σ₀² + n/σ_meas²)
    σ_meas² ≈ obs_rate·(1 - obs_rate) / BF  (binomial SE approximation)

eb_data_source labels:
    prior_only   — BF = 0 before game_date; posterior = prior (μ₀, σ₀)
    full_eb      — BF > 0; EB posterior with prior shrinkage

role_changed flag:
    True when the reliever's aLI role skips more than one tier vs prior-season
    (e.g., closer_tier → low_leverage). Uses full current-season aLI — acceptable
    approximation since role_changed is informational metadata, not part of
    the posterior computation.

LEAKAGE GUARD: current-season stats use game_date < target game_date strictly.

Writes to:
    baseball_data.betting.eb_bullpen_posteriors       (game_pk, pitcher_id)
    baseball_data.betting.eb_bullpen_team_posteriors  (game_pk, team)

Usage:
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_posteriors.py
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_posteriors.py --game-date 2025-05-01
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_posteriors.py --backfill-season 2024
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_PRIORS_DIR  = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"
_MIN_APPEARANCES = 20

_METRICS   = ("xwoba_against", "k_pct", "bb_pct")
_AGE_BANDS = ("lt_26", "26_30", "31_34", "gte_35")

# Tier ordering for role_changed flag
_TIER_ORDER = {"closer_tier": 2, "high_leverage": 1, "low_leverage": 0}


# ── Role / age helpers ─────────────────────────────────────────────────────────

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


def _role_changed_flag(prior_role: str, current_ali: float | None) -> bool:
    """True when current-season aLI skips more than one tier vs prior-season role."""
    if prior_role == "no_prior_season" or current_ali is None:
        return False
    current_role = _assign_leverage_role(current_ali)
    prior_tier   = _TIER_ORDER.get(prior_role)
    current_tier = _TIER_ORDER.get(current_role)
    if prior_tier is None or current_tier is None:
        return False
    return abs(prior_tier - current_tier) > 1


# ── Prior loading ─────────────────────────────────────────────────────────────

def _load_prior(season: int) -> dict:
    path = _PRIORS_DIR / f"bullpen_priors_{season}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Prior file not found: {path}. "
            f"Run fit_bullpen_priors.py --season {season} first."
        )
    return json.loads(path.read_text())["priors"]


def _get_prior_cell(priors: dict, metric: str, role: str, age_band: str | None) -> dict | None:
    """Return prior cell for (metric, role, age_band), falling back to any age band in role."""
    role_priors = priors.get(metric, {}).get(role, {})
    if age_band and role_priors.get(age_band):
        return role_priors[age_band]
    for band in _AGE_BANDS:
        c = role_priors.get(band)
        if c:
            return c
    return None


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_normalized_ali_map(
    conn,
    season: int,
    as_of_date: date | None = None,
    duck=None,
) -> dict[int, float]:
    """
    Normalized aLI per reliever for the given season.
    as_of_date: if set, restricts to game_date < as_of_date.
    Returns {pitcher_id (int): normalized_ali}.

    E11.20 phase 1.5: when `duck` is provided (--s3), this query — the script's ONLY
    mart_pitch_play_event read — runs on DuckDB over the S3 lakehouse. Everything else
    stays on the Snowflake `conn`.
    """
    if duck is not None:
        # INC-23: parquet game_date can be VARCHAR ISO — cast ::date at the compare.
        date_filter = (f"and bp.game_date::date < DATE '{as_of_date.isoformat()}'"
                       if as_of_date else "")
    else:
        date_filter = "and bp.game_date < %(as_of_date)s" if as_of_date else ""
    sql = f"""
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
              and bp.game_year = %(season)s
              and ppe.delta_home_win_exp is not null
              {date_filter}
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
            select pitcher_id, game_pk, at_bat_number,
                sum(abs_delta) as ab_score
            from reliever_only
            group by pitcher_id, game_pk, at_bat_number
        ),
        season_avg as (
            select avg(ab_score) as season_mean_ab_score from at_bat_scores
        ),
        pitcher_season as (
            select pitcher_id,
                count(distinct game_pk) as appearances,
                avg(ab_score)           as raw_ali
            from at_bat_scores
            group by pitcher_id
        )
        select ps.pitcher_id,
               ps.raw_ali / sa.season_mean_ab_score as normalized_ali
        from pitcher_season ps
        cross join season_avg sa
        where ps.appearances >= %(min_app)s
        """
    if duck is not None:
        from betting_ml.scripts.eb_priors import _lakehouse_duck
        duck_sql = (_lakehouse_duck.rewrite(sql)
                    .replace("%(season)s", str(int(season)))
                    .replace("%(min_app)s", str(int(_MIN_APPEARANCES))))
        rows = duck.execute(duck_sql).fetchall()
    else:
        cur = conn.cursor()
        cur.execute(sql, {
            "season":     season,
            "min_app":    _MIN_APPEARANCES,
            "as_of_date": as_of_date.isoformat() if as_of_date else None,
        })
        rows = cur.fetchall()
        cur.close()
    result: dict[int, float] = {}
    for row in rows:
        if row[1] is not None:
            result[int(row[0])] = float(row[1])
    return result


def _load_game_relievers(conn, game_date: date) -> list[dict]:
    """
    All reliever appearances in games on game_date.
    Returns per-(game_pk, pitcher_id) rows with in-game aggregates.
    """
    cur = conn.cursor()
    cur.execute(
        """
        with game_pitches as (
            select
                bp.game_pk,
                bp.game_date::date                                              as game_date,
                bp.at_bat_number,
                bp.pitcher_id,
                case when bp.inning_half = 'Top'
                     then bp.home_team else bp.away_team end                     as pitching_team,
                bp.plate_appearance_event,
                bp.xwoba,
                bp.woba_value,
                bp.woba_denom,
                bp.pitcher_age
            from baseball_data.betting.stg_batter_pitches bp
            where bp.game_type = 'R'
              and bp.game_date  = %(game_date)s
        ),
        starters as (
            select game_pk, pitcher_id, pitching_team
            from baseball_data.betting.mart_starting_pitcher_game_log
            where game_date = %(game_date)s
        ),
        reliever_pitches as (
            select gp.*
            from game_pitches gp
            left join starters s
                on  s.game_pk       = gp.game_pk
                and s.pitcher_id    = gp.pitcher_id
                and s.pitching_team = gp.pitching_team
            where s.pitcher_id is null
        ),
        pa_level as (
            select
                pitcher_id,
                game_pk,
                game_date,
                pitching_team,
                at_bat_number,
                any_value(pitcher_age)                                          as pitcher_age,
                max(case when plate_appearance_event in (
                    'strikeout', 'strikeout_double_play'
                ) then 1 else 0 end)                                            as is_strikeout,
                max(case when plate_appearance_event in (
                    'walk', 'intent_walk'
                ) then 1 else 0 end)                                            as is_walk,
                max(coalesce(woba_denom, 0))                                    as woba_denom,
                sum(case when woba_denom = 1
                    then coalesce(xwoba, woba_value)
                    else 0 end)                                                 as xwoba_num,
                max(case when plate_appearance_event in (
                    'strikeout', 'strikeout_double_play',
                    'field_out', 'force_out',
                    'grounded_into_double_play', 'double_play', 'triple_play',
                    'sac_fly', 'sac_fly_double_play',
                    'sac_bunt', 'sac_bunt_double_play',
                    'fielders_choice_out',
                    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
                    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
                    'other_out'
                ) then 1 else 0 end)                                            as is_out
            from reliever_pitches
            group by pitcher_id, game_pk, game_date, pitching_team, at_bat_number
        )
        select
            pitcher_id,
            game_pk,
            game_date,
            pitching_team,
            count(*)            as batters_faced,
            sum(is_strikeout)   as strikeouts,
            sum(is_walk)        as walks,
            sum(xwoba_num)      as xwoba_numerator,
            sum(woba_denom)     as xwoba_denom,
            sum(is_out)         as outs_recorded,
            mode(pitcher_age)   as mode_age
        from pa_level
        group by pitcher_id, game_pk, game_date, pitching_team
        """,
        {"game_date": game_date.isoformat()},
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _load_season_to_date_stats(
    conn,
    pitcher_ids: list[str],
    game_date: date,
    season: int,
) -> dict[str, dict]:
    """
    Season-to-date reliever stats per pitcher, strictly < game_date.
    Excludes starters. Returns dict keyed by pitcher_id (str).
    """
    if not pitcher_ids:
        return {}
    ids_sql = ", ".join(f"'{p}'" for p in pitcher_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        with reliever_pitches as (
            select
                bp.pitcher_id,
                bp.game_pk,
                bp.at_bat_number,
                case when bp.inning_half = 'Top'
                     then bp.home_team else bp.away_team end as pitching_team,
                bp.plate_appearance_event,
                bp.xwoba,
                bp.woba_value,
                bp.woba_denom
            from baseball_data.betting.stg_batter_pitches bp
            where bp.game_type  = 'R'
              and bp.game_year  = %(season)s
              and bp.game_date  < %(game_date)s
              and bp.pitcher_id::varchar in ({ids_sql})
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
            select
                pitcher_id,
                game_pk,
                at_bat_number,
                max(case when plate_appearance_event in (
                    'strikeout', 'strikeout_double_play') then 1 else 0 end) as is_strikeout,
                max(case when plate_appearance_event in (
                    'walk', 'intent_walk') then 1 else 0 end)                as is_walk,
                max(coalesce(woba_denom, 0))                                 as woba_denom,
                sum(case when woba_denom = 1
                    then coalesce(xwoba, woba_value) else 0 end)             as xwoba_num
            from relievers
            group by pitcher_id, game_pk, at_bat_number
        )
        select
            pitcher_id,
            count(distinct game_pk)     as appearances,
            count(*)                    as batters_faced,
            sum(is_strikeout)           as strikeouts,
            sum(is_walk)                as walks,
            sum(xwoba_num)              as xwoba_numerator,
            sum(woba_denom)             as xwoba_denom
        from pa_level
        group by pitcher_id
        """,
        {"season": season, "game_date": game_date.isoformat()},
    )
    cols = [d[0].lower() for d in cur.description]
    result: dict[str, dict] = {}
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        result[str(d["pitcher_id"])] = d
    cur.close()
    return result


# ── Posterior computation ─────────────────────────────────────────────────────

def _float_or_none(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _normal_posterior(
    mu0: float,
    sigma0: float,
    bf: float,
    obs_rate: float,
) -> tuple[float, float]:
    """Normal-Normal posterior mean and std. Returns (mean, std)."""
    if bf <= 0:
        return mu0, sigma0
    sigma_meas_sq = max(obs_rate * (1.0 - obs_rate), 0.0001) / bf
    prec_prior = 1.0 / (sigma0 ** 2)
    prec_obs   = 1.0 / sigma_meas_sq
    post_mean  = (mu0 * prec_prior + obs_rate * prec_obs) / (prec_prior + prec_obs)
    post_var   = 1.0 / (prec_prior + prec_obs)
    return float(post_mean), float(np.sqrt(max(post_var, 0.0)))


def _compute_reliever_row(
    game_row: dict,
    priors: dict,
    leverage_role: str,
    age_band: str | None,
    season_stats: dict | None,
    current_ali: float | None,
    fit_date: date,
    run_id: str,
) -> dict[str, Any]:
    """Compute EB posterior for one reliever-game."""
    pid       = str(game_row["pitcher_id"])
    game_pk   = str(game_row["game_pk"])
    game_date = game_row["game_date"]
    if isinstance(game_date, str):
        game_date = datetime.strptime(game_date[:10], "%Y-%m-%d").date()

    bf        = float((season_stats or {}).get("batters_faced", 0) or 0)
    strikeouts = float((season_stats or {}).get("strikeouts", 0) or 0)
    walks     = float((season_stats or {}).get("walks", 0) or 0)
    xwoba_num = _float_or_none((season_stats or {}).get("xwoba_numerator")) or 0.0
    xwoba_den = _float_or_none((season_stats or {}).get("xwoba_denom")) or 0.0

    xwoba_obs = xwoba_num / xwoba_den if xwoba_den > 0 else None
    k_obs     = strikeouts / bf if bf > 0 else None
    bb_obs    = walks / bf if bf > 0 else None

    cell_xw = _get_prior_cell(priors, "xwoba_against", leverage_role, age_band)
    cell_k  = _get_prior_cell(priors, "k_pct",         leverage_role, age_band)
    cell_bb = _get_prior_cell(priors, "bb_pct",        leverage_role, age_band)

    def _rnd(v: float | None) -> float | None:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 4)

    if bf == 0 or cell_xw is None:
        return {
            "game_pk":              game_pk,
            "pitcher_id":           pid,
            "game_date":            game_date,
            "season":               game_date.year,
            "pitching_team":        str(game_row["pitching_team"]),
            "leverage_role":        leverage_role,
            "age_band":             age_band,
            "outs_in_game":         int(game_row.get("outs_recorded", 0) or 0),
            "current_season_bf":    0,
            "eb_xwoba_against":     _rnd(cell_xw["mu"]) if cell_xw else None,
            "eb_k_pct":             _rnd(cell_k["mu"])  if cell_k  else None,
            "eb_bb_pct":            _rnd(cell_bb["mu"]) if cell_bb else None,
            "eb_xwoba_uncertainty": _rnd(cell_xw["sigma"]) if cell_xw else None,
            "eb_data_source":       "prior_only",
            "role_changed":         False,
            "fit_date":             fit_date,
            "run_id":               run_id,
        }

    eb_xwoba, eb_xwoba_std = _normal_posterior(
        cell_xw["mu"], cell_xw["sigma"],
        bf, xwoba_obs if xwoba_obs is not None else cell_xw["mu"],
    )
    eb_k, _  = _normal_posterior(
        (cell_k  or cell_xw)["mu"], (cell_k  or cell_xw)["sigma"],
        bf, k_obs  if k_obs  is not None else (cell_k  or cell_xw)["mu"],
    )
    eb_bb, _ = _normal_posterior(
        (cell_bb or cell_xw)["mu"], (cell_bb or cell_xw)["sigma"],
        bf, bb_obs if bb_obs is not None else (cell_bb or cell_xw)["mu"],
    )

    return {
        "game_pk":              game_pk,
        "pitcher_id":           pid,
        "game_date":            game_date,
        "season":               game_date.year,
        "pitching_team":        str(game_row["pitching_team"]),
        "leverage_role":        leverage_role,
        "age_band":             age_band,
        "outs_in_game":         int(game_row.get("outs_recorded", 0) or 0),
        "current_season_bf":    int(bf),
        "eb_xwoba_against":     _rnd(eb_xwoba),
        "eb_k_pct":             _rnd(eb_k),
        "eb_bb_pct":            _rnd(eb_bb),
        "eb_xwoba_uncertainty": _rnd(eb_xwoba_std),
        "eb_data_source":       "full_eb",
        "role_changed":         _role_changed_flag(leverage_role, current_ali),
        "fit_date":             fit_date,
        "run_id":               run_id,
    }


# ── Team aggregation ──────────────────────────────────────────────────────────

def _aggregate_to_team(individual_rows: list[dict]) -> list[dict]:
    """IP-weighted aggregation of per-reliever posteriors to (game_pk, team) grain."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in individual_rows:
        groups[(r["game_pk"], r["pitching_team"])].append(r)

    team_rows = []
    for (game_pk, team), rows in groups.items():
        weights = [float(r["outs_in_game"] or 0) for r in rows]
        total_w = sum(weights)
        if total_w == 0:
            weights = [1.0] * len(rows)
            total_w = float(len(rows))

        valid_xw  = [(w, r["eb_xwoba_against"])     for w, r in zip(weights, rows) if r["eb_xwoba_against"]     is not None]
        valid_unc = [(w, r["eb_xwoba_uncertainty"]) for w, r in zip(weights, rows) if r["eb_xwoba_uncertainty"] is not None]

        team_xwoba = (
            sum(w * v for w, v in valid_xw) / sum(w for w, _ in valid_xw)
            if valid_xw else None
        )
        team_unc = (
            sum(w * v for w, v in valid_unc) / sum(w for w, _ in valid_unc)
            if valid_unc else None
        )

        n_prior_only = sum(1 for r in rows if r["eb_data_source"] == "prior_only")

        team_rows.append({
            "game_pk":                     game_pk,
            "game_date":                   rows[0]["game_date"],
            "season":                      rows[0]["season"],
            "team":                        team,
            "team_eb_bullpen_xwoba":       round(team_xwoba, 4) if team_xwoba is not None else None,
            "team_eb_bullpen_uncertainty": round(team_unc, 4)   if team_unc   is not None else None,
            "n_relievers":                 len(rows),
            "n_prior_only":                n_prior_only,
            "fit_date":                    rows[0]["fit_date"],
            "run_id":                      rows[0]["run_id"],
        })
    return team_rows


# ── Snowflake DDL ─────────────────────────────────────────────────────────────

def _ensure_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_bullpen_posteriors (
            game_pk                VARCHAR(20)  NOT NULL,
            pitcher_id             VARCHAR(20)  NOT NULL,
            game_date              DATE         NOT NULL,
            season                 INTEGER      NOT NULL,
            pitching_team          VARCHAR(10),
            leverage_role          VARCHAR(20),
            age_band               VARCHAR(10),
            outs_in_game           INTEGER,
            current_season_bf      INTEGER,
            eb_xwoba_against       FLOAT,
            eb_k_pct               FLOAT,
            eb_bb_pct              FLOAT,
            eb_xwoba_uncertainty   FLOAT,
            eb_data_source         VARCHAR(20),
            role_changed           BOOLEAN,
            fit_date               DATE,
            run_id                 VARCHAR(36)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_bullpen_team_posteriors (
            game_pk                     VARCHAR(20)  NOT NULL,
            game_date                   DATE         NOT NULL,
            season                      INTEGER      NOT NULL,
            team                        VARCHAR(10)  NOT NULL,
            team_eb_bullpen_xwoba       FLOAT,
            team_eb_bullpen_uncertainty FLOAT,
            n_relievers                 INTEGER,
            n_prior_only                INTEGER,
            fit_date                    DATE,
            run_id                      VARCHAR(36)
        )
        """
    )


# ── Snowflake writes ──────────────────────────────────────────────────────────

def _s(v: Any) -> str | None:
    """Stringify a value for VARCHAR temp table insertion."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v)


def _write_individual(conn, rows: list[dict]) -> None:
    if not rows:
        return
    cur = conn.cursor()
    _ensure_tables(cur)

    cur.execute(
        """
        CREATE OR REPLACE TEMPORARY TABLE baseball_data.betting.tmp_eb_bullpen_posteriors (
            game_pk VARCHAR, pitcher_id VARCHAR, game_date VARCHAR, season VARCHAR,
            pitching_team VARCHAR, leverage_role VARCHAR, age_band VARCHAR,
            outs_in_game VARCHAR, current_season_bf VARCHAR,
            eb_xwoba_against VARCHAR, eb_k_pct VARCHAR, eb_bb_pct VARCHAR,
            eb_xwoba_uncertainty VARCHAR, eb_data_source VARCHAR,
            role_changed VARCHAR, fit_date VARCHAR, run_id VARCHAR
        )
        """
    )

    data = [
        (
            _s(r["game_pk"]), _s(r["pitcher_id"]), _s(r["game_date"]), _s(r["season"]),
            _s(r["pitching_team"]), _s(r["leverage_role"]), _s(r["age_band"]),
            _s(r["outs_in_game"]), _s(r["current_season_bf"]),
            _s(r["eb_xwoba_against"]), _s(r["eb_k_pct"]), _s(r["eb_bb_pct"]),
            _s(r["eb_xwoba_uncertainty"]), _s(r["eb_data_source"]),
            _s(r["role_changed"]), _s(r["fit_date"]), _s(r["run_id"]),
        )
        for r in rows
    ]
    cur.executemany(
        "INSERT INTO baseball_data.betting.tmp_eb_bullpen_posteriors "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        data,
    )

    cur.execute(
        """
        MERGE INTO baseball_data.betting.eb_bullpen_posteriors tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)        AS game_pk,
                pitcher_id::VARCHAR(20)     AS pitcher_id,
                game_date::DATE             AS game_date,
                season::INTEGER             AS season,
                pitching_team::VARCHAR(10)  AS pitching_team,
                leverage_role::VARCHAR(20)  AS leverage_role,
                age_band::VARCHAR(10)       AS age_band,
                outs_in_game::INTEGER       AS outs_in_game,
                current_season_bf::INTEGER  AS current_season_bf,
                eb_xwoba_against::FLOAT     AS eb_xwoba_against,
                eb_k_pct::FLOAT             AS eb_k_pct,
                eb_bb_pct::FLOAT            AS eb_bb_pct,
                eb_xwoba_uncertainty::FLOAT AS eb_xwoba_uncertainty,
                eb_data_source::VARCHAR(20) AS eb_data_source,
                role_changed::BOOLEAN       AS role_changed,
                fit_date::DATE              AS fit_date,
                run_id::VARCHAR(36)         AS run_id
            FROM baseball_data.betting.tmp_eb_bullpen_posteriors
        ) src
        ON  tgt.game_pk    = src.game_pk
        AND tgt.pitcher_id = src.pitcher_id
        WHEN MATCHED THEN UPDATE SET
            game_date             = src.game_date,
            season                = src.season,
            pitching_team         = src.pitching_team,
            leverage_role         = src.leverage_role,
            age_band              = src.age_band,
            outs_in_game          = src.outs_in_game,
            current_season_bf     = src.current_season_bf,
            eb_xwoba_against      = src.eb_xwoba_against,
            eb_k_pct              = src.eb_k_pct,
            eb_bb_pct             = src.eb_bb_pct,
            eb_xwoba_uncertainty  = src.eb_xwoba_uncertainty,
            eb_data_source        = src.eb_data_source,
            role_changed          = src.role_changed,
            fit_date              = src.fit_date,
            run_id                = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            game_pk, pitcher_id, game_date, season, pitching_team, leverage_role,
            age_band, outs_in_game, current_season_bf,
            eb_xwoba_against, eb_k_pct, eb_bb_pct, eb_xwoba_uncertainty,
            eb_data_source, role_changed, fit_date, run_id
        ) VALUES (
            src.game_pk, src.pitcher_id, src.game_date, src.season, src.pitching_team,
            src.leverage_role, src.age_band, src.outs_in_game, src.current_season_bf,
            src.eb_xwoba_against, src.eb_k_pct, src.eb_bb_pct, src.eb_xwoba_uncertainty,
            src.eb_data_source, src.role_changed, src.fit_date, src.run_id
        )
        """
    )
    cur.close()


def _write_team(conn, rows: list[dict]) -> None:
    if not rows:
        return
    cur = conn.cursor()
    _ensure_tables(cur)

    cur.execute(
        """
        CREATE OR REPLACE TEMPORARY TABLE baseball_data.betting.tmp_eb_bullpen_team_posteriors (
            game_pk VARCHAR, game_date VARCHAR, season VARCHAR, team VARCHAR,
            team_eb_bullpen_xwoba VARCHAR, team_eb_bullpen_uncertainty VARCHAR,
            n_relievers VARCHAR, n_prior_only VARCHAR,
            fit_date VARCHAR, run_id VARCHAR
        )
        """
    )

    data = [
        (
            _s(r["game_pk"]), _s(r["game_date"]), _s(r["season"]), _s(r["team"]),
            _s(r["team_eb_bullpen_xwoba"]), _s(r["team_eb_bullpen_uncertainty"]),
            _s(r["n_relievers"]), _s(r["n_prior_only"]),
            _s(r["fit_date"]), _s(r["run_id"]),
        )
        for r in rows
    ]
    cur.executemany(
        "INSERT INTO baseball_data.betting.tmp_eb_bullpen_team_posteriors "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        data,
    )

    cur.execute(
        """
        MERGE INTO baseball_data.betting.eb_bullpen_team_posteriors tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)        AS game_pk,
                game_date::DATE             AS game_date,
                season::INTEGER             AS season,
                team::VARCHAR(10)           AS team,
                team_eb_bullpen_xwoba::FLOAT       AS team_eb_bullpen_xwoba,
                team_eb_bullpen_uncertainty::FLOAT  AS team_eb_bullpen_uncertainty,
                n_relievers::INTEGER        AS n_relievers,
                n_prior_only::INTEGER       AS n_prior_only,
                fit_date::DATE              AS fit_date,
                run_id::VARCHAR(36)         AS run_id
            FROM baseball_data.betting.tmp_eb_bullpen_team_posteriors
        ) src
        ON  tgt.game_pk = src.game_pk
        AND tgt.team    = src.team
        WHEN MATCHED THEN UPDATE SET
            game_date                   = src.game_date,
            season                      = src.season,
            team_eb_bullpen_xwoba       = src.team_eb_bullpen_xwoba,
            team_eb_bullpen_uncertainty = src.team_eb_bullpen_uncertainty,
            n_relievers                 = src.n_relievers,
            n_prior_only                = src.n_prior_only,
            fit_date                    = src.fit_date,
            run_id                      = src.run_id
        WHEN NOT MATCHED THEN INSERT (
            game_pk, game_date, season, team,
            team_eb_bullpen_xwoba, team_eb_bullpen_uncertainty,
            n_relievers, n_prior_only, fit_date, run_id
        ) VALUES (
            src.game_pk, src.game_date, src.season, src.team,
            src.team_eb_bullpen_xwoba, src.team_eb_bullpen_uncertainty,
            src.n_relievers, src.n_prior_only, src.fit_date, src.run_id
        )
        """
    )
    cur.close()


# ── Processing ────────────────────────────────────────────────────────────────

def _compute_date_rows(
    conn,
    game_date: date,
    season: int,
    priors: dict,
    prior_ali_map: dict[int, float],
    current_ali_map: dict[int, float],
) -> tuple[list[dict], list[dict]]:
    """Compute (but do NOT write) one game date's rows.

    A2.8 spend fix: returns (individual_rows, team_rows) so the backfill caller
    can accumulate across all dates and write each table ONCE, instead of a
    CREATE TEMP + INSERT + MERGE round-trip (×2 tables) per date.
    """
    fit_date = date.today()
    run_id   = str(uuid.uuid4())

    game_rows = _load_game_relievers(conn, game_date)
    if not game_rows:
        return [], []

    pitcher_ids  = list({str(r["pitcher_id"]) for r in game_rows})
    season_stats = _load_season_to_date_stats(conn, pitcher_ids, game_date, season)

    individual_rows = []
    for row in game_rows:
        pid_int = int(row["pitcher_id"])
        pid_str = str(row["pitcher_id"])

        leverage_role = (
            _assign_leverage_role(prior_ali_map[pid_int])
            if pid_int in prior_ali_map
            else "no_prior_season"
        )
        age_band    = _assign_age_band(row.get("mode_age"))
        current_ali = current_ali_map.get(pid_int)

        result = _compute_reliever_row(
            game_row=row,
            priors=priors,
            leverage_role=leverage_role,
            age_band=age_band,
            season_stats=season_stats.get(pid_str),
            current_ali=current_ali,
            fit_date=fit_date,
            run_id=run_id,
        )
        individual_rows.append(result)

    team_rows = _aggregate_to_team(individual_rows)
    return individual_rows, team_rows


# ── Main ──────────────────────────────────────────────────────────────────────

def _maybe_duck(use_s3: bool):
    """E11.20 phase 1.5: a registered DuckDB/S3 connection when --s3, else None."""
    if not use_s3:
        return None
    from betting_ml.scripts.eb_priors import _lakehouse_duck
    print("  [--s3] Reading the aLI substrate from the S3 lakehouse via DuckDB...")
    duck = _lakehouse_duck.get_duckdb()
    _lakehouse_duck.register_views(duck)
    return duck


def main(game_date: date, use_s3: bool = False) -> None:
    season = game_date.year
    run_id = str(uuid.uuid4())
    print(f"game_date={game_date}  season={season}  run_id={run_id[:8]}...")

    priors = _load_prior(season)
    duck = _maybe_duck(use_s3)

    conn = get_snowflake_connection()
    try:
        print(f"  Loading prior-season ({season - 1}) aLI map...")
        prior_ali_map = _load_normalized_ali_map(conn, season - 1, duck=duck)
        print(f"  {len(prior_ali_map)} relievers in prior-season aLI map")

        print(f"  Loading current-season ({season}) aLI (as of {game_date}) for role_changed...")
        current_ali_map = _load_normalized_ali_map(conn, season, as_of_date=game_date, duck=duck)
        print(f"  {len(current_ali_map)} relievers in current-season aLI map")

        game_rows = _load_game_relievers(conn, game_date)
        if not game_rows:
            print("  No reliever appearances found for this date — nothing to write.")
            return

        n_games = len({r["game_pk"] for r in game_rows})
        print(f"  {len(game_rows)} reliever-game rows across {n_games} games")

        pitcher_ids  = list({str(r["pitcher_id"]) for r in game_rows})
        season_stats = _load_season_to_date_stats(conn, pitcher_ids, game_date, season)
        print(f"  season-to-date stats found for {len(season_stats)}/{len(pitcher_ids)} pitchers")

        individual_rows = []
        for row in game_rows:
            pid_int = int(row["pitcher_id"])
            pid_str = str(row["pitcher_id"])
            leverage_role = (
                _assign_leverage_role(prior_ali_map[pid_int])
                if pid_int in prior_ali_map
                else "no_prior_season"
            )
            age_band    = _assign_age_band(row.get("mode_age"))
            current_ali = current_ali_map.get(pid_int)
            result = _compute_reliever_row(
                game_row=row,
                priors=priors,
                leverage_role=leverage_role,
                age_band=age_band,
                season_stats=season_stats.get(pid_str),
                current_ali=current_ali,
                fit_date=date.today(),
                run_id=run_id,
            )
            individual_rows.append(result)

        team_rows = _aggregate_to_team(individual_rows)

        # Diagnostics
        sources: dict[str, int] = {}
        for r in individual_rows:
            sources[r["eb_data_source"]] = sources.get(r["eb_data_source"], 0) + 1
        role_counts: dict[str, int] = {}
        for r in individual_rows:
            role_counts[r["leverage_role"]] = role_counts.get(r["leverage_role"], 0) + 1
        n_role_changed = sum(1 for r in individual_rows if r["role_changed"])
        n_no_age       = sum(1 for r in individual_rows if r["age_band"] is None)

        print(f"  eb_data_source:  {sources}")
        print(f"  leverage_role:   {role_counts}")
        print(f"  role_changed:    {n_role_changed}/{len(individual_rows)}")
        print(f"  age_band null:   {n_no_age}/{len(individual_rows)}")

        if individual_rows:
            sample = individual_rows[0]
            print(
                f"  sample ({sample['eb_data_source']}): "
                f"pitcher={sample['pitcher_id']}  role={sample['leverage_role']}  "
                f"age_band={sample['age_band']}  bf={sample['current_season_bf']}  "
                f"xwoba={sample['eb_xwoba_against']}  unc={sample['eb_xwoba_uncertainty']}"
            )
        if team_rows:
            t = team_rows[0]
            print(
                f"  sample team ({t['team']}): "
                f"n_rel={t['n_relievers']}  n_prior_only={t['n_prior_only']}  "
                f"team_xwoba={t['team_eb_bullpen_xwoba']}  team_unc={t['team_eb_bullpen_uncertainty']}"
            )

        print(f"Writing {len(individual_rows)} individual rows, {len(team_rows)} team rows...")
        _write_individual(conn, individual_rows)
        _write_team(conn, team_rows)
        print("Done.")
    finally:
        conn.close()


def main_backfill_season(season: int, use_s3: bool = False) -> None:
    """Process every game date in a season in chronological order."""
    print(f"\n═══ Backfill season {season} ═══")
    priors = _load_prior(season)
    duck = _maybe_duck(use_s3)

    conn = get_snowflake_connection()
    try:
        print(f"  Loading prior-season ({season - 1}) aLI map...")
        prior_ali_map = _load_normalized_ali_map(conn, season - 1, duck=duck)
        print(f"  {len(prior_ali_map)} relievers in prior-season aLI map")

        print(f"  Loading current-season ({season}) full-season aLI (approx for role_changed)...")
        current_ali_map = _load_normalized_ali_map(conn, season, duck=duck)
        print(f"  {len(current_ali_map)} relievers in current-season aLI map")

        cur = conn.cursor()
        cur.execute(
            """
            SELECT gd FROM (
                SELECT DISTINCT game_date::date AS gd
                FROM baseball_data.betting.stg_batter_pitches
                WHERE game_type = 'R' AND game_year = %(season)s
            ) ORDER BY gd
            """,
            {"season": season},
        )
        game_dates = [r[0] for r in cur.fetchall()]
        cur.close()
        print(f"  {len(game_dates)} game dates to process")

        all_individual: list[dict] = []
        all_team: list[dict] = []
        for i, gd in enumerate(game_dates, 1):
            if isinstance(gd, str):
                gd = datetime.strptime(gd[:10], "%Y-%m-%d").date()
            ind_rows, team_rows = _compute_date_rows(
                conn, gd, season, priors, prior_ali_map, current_ali_map
            )
            all_individual.extend(ind_rows)
            all_team.extend(team_rows)
            if i % 50 == 0 or i == len(game_dates):
                print(
                    f"  [{i}/{len(game_dates)}] {gd}  "
                    f"cumulative: {len(all_individual)} individual, {len(all_team)} team rows"
                )

        # A2.8 spend fix: ONE batched temp-table + INSERT + MERGE per table for
        # the whole season instead of two write round-trips per date.
        if all_individual:
            print(f"  Writing {len(all_individual)} individual + {len(all_team)} team rows (batched)...")
            _write_individual(conn, all_individual)
            _write_team(conn, all_team)
        print(f"\n  Season {season} complete — {len(all_individual)} individual, {len(all_team)} team rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute per-reliever EB posteriors and write to Snowflake (Epic 6A.2)"
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
    parser.add_argument(
        "--s3",
        action="store_true",
        help="E11.20 phase 1.5: read the aLI substrate (mart_pitch_play_event join) from "
             "the S3 lakehouse via DuckDB instead of Snowflake. REQUIRED once the SF "
             "mart_pitch_* views are dropped.",
    )
    args = parser.parse_args()

    if args.backfill_season:
        main_backfill_season(args.backfill_season, use_s3=args.s3)
    else:
        main(args.game_date or date.today(), use_s3=args.s3)
