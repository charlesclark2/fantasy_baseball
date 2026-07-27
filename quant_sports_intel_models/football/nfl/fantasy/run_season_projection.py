"""run_season_projection.py — NF-FASTPATH CLI: build the 2026 season raw-stat-line projection.

Reads the built NFL marts from the sports dbt DuckDB (SF-free, no box) + the NCAAF-P1A rookie
parquet, runs the pure `season_projection` model for veterans + the incoming rookie class, validates
(coverage report + face-validity + a holdout-season rank-correlation sanity check), lands the raw
projections to the S3 sports lake under `nfl/fantasy/derived/season_projections/`, and writes a
readable ranked output + a markdown report.

⭐ RUN ON THE LAPTOP (like NCAAF-P1A). The sports lake is a SEPARATE bucket from MLB's; a laptop run
is laptop compute + S3 I/O, ZERO shared-box CPU/RAM — it cannot contend with the live MLB pipeline.
SF-free throughout; `SPORTS_LAKE_REGION=us-east-2` for the S3 read/write.

Prereq — the NFL marts must be built into the DuckDB first (dbt-core, NOT dbtf; the delta_scan
staging segfaults fusion). From `quant_sports_intel_models/sports_dbt`:
    export SPORTS_LAKE_REGION=us-east-2
    python -m dbt.cli.main run --select nfl.staging --threads 1
    python -m dbt.cli.main run --select nfl.marts --threads 1

Then (laptop):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_season_projection \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --s3

Outputs:
  * <out-dir>/nfl_fantasy_season_projections_<year>.parquet   — the raw stat-line projection
  * <out-dir>/nfl_fantasy_season_projections_<year>_ranked.csv — a readable ranked board
  * s3://credence-sports-lakehouse/nfl/fantasy/derived/season_projections/season=<year>/  (--s3)
  * quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_fastpath_season_projection.md
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy.season_projection import (  # noqa: E402
    MODEL_VERSION,
    RAW_STAT_COLS,
    ROOKIE_POSITIONS,
    fit_rookie_slot_curves,
    positional_pergame_priors,
    project_rookies,
    project_veterans,
    role_volume_prior,
)
from quant_sports_intel_models.football.nfl.fantasy import season_projection as _SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import win_total_source  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import xfp_source  # noqa: E402

log = logging.getLogger("nfl.fantasy.fastpath")

MARTS_SCHEMA = "main_nfl_marts"
STAGING_SCHEMA = "main_nfl_staging"
_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_fastpath_season_projection.md"
)
_ROOKIE_PARQUET = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/ncaaf/models/artifacts/ncaaf_nfl_rookie_projections.parquet"
)

# The final emitted schema (the input contract for MVP-2 / NF-C1). Ordered for readability.
OUTPUT_COLS = [
    "sport", "projection_season", "base_season", "player_id", "player_name", "position",
    "team_id", "source", "is_rookie", "draft_overall", "confidence",
    *RAW_STAT_COLS,
    "proj_fp_std", "proj_fp_half", "proj_fp_ppr",
    "fp_ppr_sd", "fp_ppr_p10", "fp_ppr_p90", "uncertainty_type",
    "model_version", "generated_at",
]

# ── The per-player base-season raw line. Realized season totals ÷ played games → per-game counting
#    stats, plus game-to-game PPR sd, current depth-chart rank/team, and position. All from the
#    already-built NFL marts (SF-free). `week > 0` = regular+post; a played game = played_flag & not
#    bye (matches mart_player_season's games_played).
# Per-player-PER-SEASON realized line over a multi-year window. The weighting into a single
# per-game line (recency + games) happens in pandas — see load_base_season. `week > 0` = reg+post.
_MULTI_SEASON_SQL = """
with wk as (
    select season, week, player_id, player_name, team_id, position, week_start_et,
           (played_flag and not is_bye) as g,
           pass_attempts, pass_completions, passing_yards, passing_touchdowns, interceptions,
           rushing_carries, rushing_yards, rushing_touchdowns,
           receiving_targets, receptions, receiving_yards, receiving_touchdowns,
           fantasy_points_ppr,
           offense_pct, target_share, carry_share
    from {schema}.fct_player_week
    where season between {lo} and {season} and week > 0
)
select
    player_id, season,
    count_if(g) as games_played,
    max(position) as position,
    sum(case when g then pass_attempts else 0 end)::double        as pass_att_tot,
    sum(case when g then pass_completions else 0 end)::double      as pass_cmp_tot,
    sum(case when g then passing_yards else 0 end)::double         as pass_yds_tot,
    sum(case when g then passing_touchdowns else 0 end)::double    as pass_td_tot,
    sum(case when g then interceptions else 0 end)::double         as pass_int_tot,
    sum(case when g then rushing_carries else 0 end)::double       as rush_att_tot,
    sum(case when g then rushing_yards else 0 end)::double         as rush_yds_tot,
    sum(case when g then rushing_touchdowns else 0 end)::double    as rush_td_tot,
    sum(case when g then receiving_targets else 0 end)::double     as targets_tot,
    sum(case when g then receptions else 0 end)::double            as rec_tot,
    sum(case when g then receiving_yards else 0 end)::double       as rec_yds_tot,
    sum(case when g then receiving_touchdowns else 0 end)::double  as rec_td_tot,
    stddev_samp(case when g then fantasy_points_ppr end)          as fp_ppr_sd,
    -- NF-D2 slice 1: base-season USAGE-SHARE role signals (per-game rates → season averages over
    -- played games). snap share only counts games the player was actually on the field (>0);
    -- target/carry share are box-derived and defined for every played game.
    avg(offense_pct) filter (where g and offense_pct > 0)         as snap_share,
    avg(target_share) filter (where g)                            as target_share,
    avg(carry_share) filter (where g)                             as carry_share
from wk group by 1, 2 having count_if(g) > 0
"""

_PERGAME_MAP = {
    "pass_att": "pass_att_tot", "pass_cmp": "pass_cmp_tot", "pass_yds": "pass_yds_tot",
    "pass_td": "pass_td_tot", "pass_int": "pass_int_tot",
    "rush_att": "rush_att_tot", "rush_yds": "rush_yds_tot", "rush_td": "rush_td_tot",
    "targets": "targets_tot", "rec": "rec_tot", "rec_yds": "rec_yds_tot", "rec_td": "rec_td_tot",
}

# Multi-year regression: a season's weight decays by recency and scales by that season's games, so a
# 3-yr window regresses a CAREER-YEAR (or a down/injured year) toward the player's own baseline. This
# is the fix for single-season recency bias — the noisy spike stats (esp. rushing TDs) mean-revert
# instead of anchoring the projection (the Trevor-Lawrence-as-QB2 failure).
_RECENCY_DECAY = 0.6   # weight of a season one year older than the base season
_WINDOW_YEARS = 3      # base season + the two prior


def load_base_season(
    con, season: int, schema: str = MARTS_SCHEMA, staging_schema: str = STAGING_SCHEMA
) -> pd.DataFrame:
    lo = season - (_WINDOW_YEARS - 1)
    per_season = con.sql(_MULTI_SEASON_SQL.format(schema=schema, season=season, lo=lo)).df()
    if per_season.empty:
        return per_season

    # per-season per-game rates
    gps = per_season["games_played"].clip(lower=1)
    for base, tot in _PERGAME_MAP.items():
        per_season[base + "_pg"] = per_season[tot] / gps
    # season weight = decay^(age) × games (an injury-shortened year contributes less)
    age = season - per_season["season"]
    per_season["_w"] = (_RECENCY_DECAY ** age) * per_season["games_played"]

    pg_cols = [b + "_pg" for b in _PERGAME_MAP]
    # NF-D2 slice 1: base-season usage-share role signals, window-blended on the SAME recency×games
    # weights as the per-game line. NaN-aware — a season with no snap-count coverage (an older season,
    # or a player with a snap-data gap) simply drops out of that player's weighted share.
    usage_cols = [c for c in ("snap_share", "target_share", "carry_share") if c in per_season.columns]

    def _blend(g: pd.DataFrame) -> pd.Series:
        w = g["_w"].to_numpy()
        wsum = w.sum() or 1.0
        out = {c: float((g[c].to_numpy() * w).sum() / wsum) for c in pg_cols}
        for c in usage_cols:
            v = pd.to_numeric(g[c], errors="coerce").to_numpy()
            m = np.isfinite(v)
            wm = w[m].sum()
            out[c] = float((v[m] * w[m]).sum() / wm) if wm > 0 else np.nan
        return pd.Series(out)

    weighted = per_season.groupby("player_id").apply(_blend, include_groups=False)

    # anchor on the BASE SEASON: a player must have appeared in the season we project off to be
    # draft-relevant for the upcoming one (excludes retired / out-of-league players the multi-year
    # window would otherwise sweep in). Role/team/sd/durability all come from that base season.
    base = per_season[per_season["season"] == season].set_index("player_id")
    weighted = weighted.join(base[["games_played", "fp_ppr_sd", "position"]], how="inner")
    df = weighted.reset_index()

    # team + display name from the most-recent base-season week
    meta = con.sql(f"""
        select player_id, team_id, player_name
        from {schema}.fct_player_week
        where season = {season} and week > 0
        qualify row_number() over (partition by player_id order by week desc, week_start_et desc) = 1
    """).df()
    df = df.merge(meta, on="player_id", how="left")

    # current depth-chart rank (role signal for expected games). NF-D1 cold-start fix
    # (2026-07-25): prefer `stg_nfl_depth_charts_current` — the freshest known ESPN snapshot for
    # the season being PROJECTED — over `dim_player_role`'s in-season SCD "current" record.
    # `dim_player_role` is built off `stg_nfl_depth_charts`'s week-ASOF map, which only covers
    # weeks a season has actually PLAYED; for an upcoming season with a schedule but zero elapsed
    # weeks (the normal state during the whole Mar-Aug roll-forward window), its "current" record
    # stays pinned to the prior season's final week even though nflverse/ESPN is already
    # publishing fresh camp-battle depth. `stg_nfl_depth_charts_current` has no such gap — it is
    # keyed straight off the raw snapshot with no week requirement. A player absent from the
    # current-season snapshot (not yet on any team's depth chart) falls back to the SCD record.
    role = con.sql(f"""
        with current_preseason as (
            -- one row per player = the FRESHEST forward depth snapshot. Read both the base-season and
            -- the projection-season (base+1) partitions and keep the latest `snap_ts` so a 2026
            -- post-free-agency/draft snapshot (stored under the season=base+1 partition) WINS over a
            -- stale pre-free-agency one under season=base — otherwise the forward role/team is pinned
            -- to March and misses the offseason moves NF-D2 slice 3 exists to catch. A multi-position
            -- player (Taysom Hill at QB AND TE) is deduped to his best (lowest) rank so the role join
            -- stays 1:1. `player_team` = the PROJECTION-season (forward) team — slice 3 compares it to
            -- the base-season team to detect a team change. (For a backtest the base+1 partition does
            -- not exist ⇒ this is a no-op that reads only season=base, exactly as before.)
            select player_id, depth_chart_position_rank, player_team
            from {staging_schema}.stg_nfl_depth_charts_current
            where season in ({season}, {season} + 1)
            qualify row_number() over (
                partition by player_id
                order by snap_ts desc nulls last, depth_chart_position_rank asc nulls last
            ) = 1
        ),
        scd_current as (
            select player_id, depth_chart_position_rank, player_team
            from {schema}.dim_player_role where current_record_indicator = 'Y'
            qualify row_number() over (partition by player_id order by record_effective_ts desc) = 1
        )
        select
            coalesce(p.player_id, s.player_id)                                as player_id,
            coalesce(p.depth_chart_position_rank, s.depth_chart_position_rank) as depth_chart_position_rank,
            coalesce(p.player_team, s.player_team)                            as proj_team
        from scd_current s
        full outer join current_preseason p using (player_id)
    """).df()
    df = df.merge(role, on="player_id", how="left")

    # NF-D2 slice 3: team-change detection. `base_team` = the base-season team (the `team_id` from the
    # most-recent base-season week); `proj_team` = the forward team from the current depth-chart
    # snapshot (populated for the live board via `stg_nfl_depth_charts_current`; NULL for older
    # backtest seasons whose forward role falls back to the SCD — the mover step then no-ops). Set the
    # displayed `team_id` to the forward team when known, so a team-changer's board row shows the team
    # they're actually projected on.
    df["base_team"] = df["team_id"]
    if "proj_team" not in df.columns:
        df["proj_team"] = pd.NA
    df["team_id"] = df["proj_team"].where(df["proj_team"].notna(), df["base_team"])
    return df


def load_team_week1_env(con, projection_season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """NF-D2 slice 4 — each team's WEEK-1 implied points for the PROJECTION season = a leakage-safe
    forward read on its offensive environment (a Week-1 line is set before any of the season's games
    are played). implied points = total/2 ± spread/2 (home +, away −). Keyed by team → `team_env` for
    a join on the projected player's projection-season team. Empty when no Week-1 lines are posted yet."""
    return con.sql(f"""
        with e as (
            select home_team as team, (total_line/2.0 + spread_line/2.0) as ip
            from {schema}.dim_nfl_game
            where is_regular_season and week = 1 and season = {projection_season} and total_line is not null
            union all
            select away_team as team, (total_line/2.0 - spread_line/2.0) as ip
            from {schema}.dim_nfl_game
            where is_regular_season and week = 1 and season = {projection_season} and total_line is not null
        )
        select team as proj_team, avg(ip) as team_env from e group by 1
    """).df()


def load_forward_roster_status(con, projection_season: int, staging_schema: str = STAGING_SCHEMA) -> pd.DataFrame:
    """NF-D2 slice 5 (+ NF-D5) — each player's PROJECTION-season roster status from the EARLIEST
    available week (leakage-safe: a Week-1 / preseason designation is set before any of the season's
    games; for a not-yet-started season the earliest snapshot is the current offseason roster).
    `proj_status` feeds the injury/availability cap (RES/PUP/NFI/SUS). ⭐ NF-D5: COALESCED with
    Sleeper's `v1/players/nfl` forward-availability snapshot (`stg_nfl_sleeper_injuries`) — Sleeper
    PREFERRED (fresher + offseason-covering; nflverse's roster `status` lags to camp), nflverse the
    fallback. A not-yet-built Sleeper staging model (the ingest hasn't landed/rebuilt yet) degrades
    cleanly to nflverse-only (WARN-tier — this feed is advisory, never serving-critical)."""
    nflverse = con.sql(f"""
        select player_id, first(status order by week asc) as proj_status_nflverse
        from {staging_schema}.stg_nfl_weekly_rosters
        where season = {projection_season} and player_id is not null
        group by 1
    """).df()
    try:
        sleeper = con.sql(f"""
            select player_id, first(proj_status order by ingested_at desc) as proj_status_sleeper
            from {staging_schema}.stg_nfl_sleeper_injuries
            where season = {projection_season} and player_id is not null and proj_status is not null
            group by 1
        """).df()
    except Exception:  # noqa: BLE001 — WARN-tier: advisory feed, never blocks the projection
        log.warning("NF-D5: stg_nfl_sleeper_injuries not available (run run_sleeper_injuries_ingest.py "
                    "+ rebuild nfl.staging) — forward roster status falls back to nflverse-only.")
        sleeper = pd.DataFrame(columns=["player_id", "proj_status_sleeper"])
    return _coalesce_forward_status(nflverse, sleeper)


def _coalesce_forward_status(nflverse: pd.DataFrame, sleeper: pd.DataFrame) -> pd.DataFrame:
    """NF-D5 — pure merge: PREFER `sleeper`'s mapped status over `nflverse`'s when both are present
    for a player, falling back to nflverse when Sleeper has none (and vice versa — a player only
    Sleeper has flagged, e.g. an offseason case nflverse hasn't caught up to, still surfaces). Either
    frame may be empty (no rosters landed yet / Sleeper not ingested) — a clean no-op in that case."""
    if sleeper is None or sleeper.empty:
        return nflverse.rename(columns={"proj_status_nflverse": "proj_status"})
    if nflverse is None or nflverse.empty:
        return sleeper.rename(columns={"proj_status_sleeper": "proj_status"})[["player_id", "proj_status"]]
    merged = nflverse.merge(sleeper, on="player_id", how="outer")
    merged["proj_status"] = merged["proj_status_sleeper"].where(
        merged["proj_status_sleeper"].notna(), merged["proj_status_nflverse"])
    return merged[["player_id", "proj_status"]]


def load_rookie_training(con, upto_season: int, schema: str = MARTS_SCHEMA,
                         include_zero_game: bool = False) -> pd.DataFrame:
    """Historical drafted rookies (skill positions, draft_year ≤ base season) joined to their
    rookie-year raw stat TOTALS — the training base for the draft-slot production curves.

    `include_zero_game` (NF1.4) returns the FULL DRAFTED POPULATION: every drafted skill rookie,
    with the ~15% who never played a snap (35% at QB) carried as a real `rookie_fp_ppr = 0` instead
    of dropped. That population is what `fit_rookie_slot_curves(..., band_hist=...)` needs to
    calibrate an honest 80% interval — a band fitted on survivors only claims 80% and covers 68%
    (44% at QB). The POINT curve keeps the default survivor-filtered history: NF1.4 measured the
    zero-inclusive fit walk-forward and it did NOT improve held-out accuracy at any position (see
    `ablation_results/nf1_4_rookie.md`), so only the interval changes."""
    rk = pd.read_parquet(_ROOKIE_PARQUET)
    rk = rk[
        rk["position_group"].isin(ROOKIE_POSITIONS)
        & pd.to_numeric(rk["draft_overall"], errors="coerce").notna()
        & (pd.to_numeric(rk["draft_year"], errors="coerce") <= upto_season)
    ][["gsis_id", "position_group", "draft_overall", "draft_year"]].copy()
    con.register("rk_train", rk)
    join, having = ("left join", "") if include_zero_game else ("join", "where games > 0")
    hist = con.sql(f"""
        with ry as (
            select r.gsis_id, r.position_group, r.draft_overall,
                coalesce(count_if(f.played_flag and not f.is_bye), 0) as games,
                sum(case when f.played_flag then f.pass_attempts else 0 end)::double as pass_att,
                sum(case when f.played_flag then f.pass_completions else 0 end)::double as pass_cmp,
                sum(case when f.played_flag then f.passing_yards else 0 end)::double as pass_yds,
                sum(case when f.played_flag then f.passing_touchdowns else 0 end)::double as pass_td,
                sum(case when f.played_flag then f.interceptions else 0 end)::double as pass_int,
                sum(case when f.played_flag then f.rushing_carries else 0 end)::double as rush_att,
                sum(case when f.played_flag then f.rushing_yards else 0 end)::double as rush_yds,
                sum(case when f.played_flag then f.rushing_touchdowns else 0 end)::double as rush_td,
                sum(case when f.played_flag then f.receiving_targets else 0 end)::double as targets,
                sum(case when f.played_flag then f.receptions else 0 end)::double as rec,
                sum(case when f.played_flag then f.receiving_yards else 0 end)::double as rec_yds,
                sum(case when f.played_flag then f.receiving_touchdowns else 0 end)::double as rec_td,
                coalesce(sum(case when f.played_flag then f.fantasy_points_ppr else 0 end), 0)::double as rookie_fp_ppr
            from rk_train r
            {join} {schema}.fct_player_week f
              on f.player_id = r.gsis_id and f.season = r.draft_year and f.week > 0
            group by 1,2,3
        )
        select * from ry {having}
    """).df()
    return hist


def load_realized_season(con, season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Realized convenience PPR total for a season (for the holdout backtest)."""
    return con.sql(f"""
        select player_id, count_if(played_flag and not is_bye) as g,
               sum(case when played_flag then fantasy_points_ppr else 0 end) as real_fp_ppr
        from {schema}.fct_player_week where season = {season} and week > 0
        group by 1 having g > 0
    """).df()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Projection assembly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_projection(con, base_season: int, projection_season: int, schema: str,
                     usage_role_blend: float | None = None,
                     mover_opportunity_blend: float | None = None,
                     env_tilt_blend: float | None = None,
                     injury_override_blend: float | None = None,
                     xfp_td_blend: float | None = None) -> pd.DataFrame:
    base = load_base_season(con, base_season, schema)
    # NF-D2 slice 4 / NF-D4: attach the projection-season team's forward Vegas environment on the
    # forward team, for the QB environment tilt. Base = the Week-1 implied points (leakage-safe); NF-D4
    # AUGMENTS it with the preseason WIN TOTAL — a team-level 0.5/0.5 z-blend (a season-level team-
    # quality read that STABILISES the noisy single Week-1 game line; it beat the Week-1-only baseline on
    # held-out QB ρ). `blend_env_with_win_total` falls back to Week-1-only when the projection season's
    # win totals aren't backfilled. A NULL join (unknown forward team / no Week-1 line) → tilt no-op.
    env = load_team_week1_env(con, projection_season, schema)
    env = win_total_source.blend_env_with_win_total(env, projection_season)
    if not env.empty and "proj_team" in base.columns:
        base = base.merge(env, on="proj_team", how="left")
    # NF-D2 slice 5: attach the projection-season forward roster status (leakage-safe) for the injury/
    # availability cap. A NULL join (no rosters landed yet) makes the cap a no-op.
    status = load_forward_roster_status(con, projection_season)
    if not status.empty:
        base = base.merge(status, on="player_id", how="left")
    # NF-D7: TD-regression expected per-game rates (leakage-safe base-season-window opportunity), joined
    # for the TD-regression step in project_veterans. Only loaded when the blend is ON (default OFF ⇒ no
    # play-by-play read on the baseline board); a cache miss / empty join makes the regression a no-op.
    _xfp_blend = _SP._XFP_TD_BLEND if xfp_td_blend is None else xfp_td_blend
    if _xfp_blend and _xfp_blend > 0:
        xfp = xfp_source.load_xfp_features(con, base_season, schema)
        if not xfp.empty:
            base = base.merge(xfp[["player_id", "xrush_td_pg", "xrec_td_pg"]], on="player_id", how="left")
    priors = positional_pergame_priors(base)
    kw = {} if usage_role_blend is None else {"usage_role_blend": usage_role_blend}
    # NF-D2 slice 3: the role→volume prior (in-fold from the base season) drives the team-changer
    # rescale. Passing it in turns the mover step ON (build the live board with it); the ablation
    # harness passes mover_opportunity_blend=0 for the "off" baseline arm.
    kw["role_vol_prior"] = role_volume_prior(base)
    if mover_opportunity_blend is not None:
        kw["mover_opportunity_blend"] = mover_opportunity_blend
    if env_tilt_blend is not None:
        kw["env_tilt_blend"] = env_tilt_blend
    if injury_override_blend is not None:
        kw["injury_override_blend"] = injury_override_blend
    if xfp_td_blend is not None:
        kw["xfp_td_blend"] = xfp_td_blend
    vets = project_veterans(base, priors, projection_season, **kw)

    rookies_all = pd.read_parquet(_ROOKIE_PARQUET)
    incoming = rookies_all[pd.to_numeric(rookies_all["draft_year"], errors="coerce") == projection_season]
    # NF1.4: the point curve fits the survivor-filtered history (unchanged); `band_hist` is
    # the FULL drafted population (zero-game rookies included) and calibrates the 80% rookie
    # interval, which the legacy `fp × cv` width missed badly (0.678 coverage, 0.444 at QB).
    curve = fit_rookie_slot_curves(
        load_rookie_training(con, base_season, schema),
        band_hist=load_rookie_training(con, base_season, schema, include_zero_game=True))
    rks = project_rookies(incoming, curve, projection_season) if not incoming.empty else pd.DataFrame()

    proj = pd.concat([vets, rks], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["base_season"] = int(base_season)
    proj["model_version"] = MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    # keep only draft-relevant offensive positions (drop K/DEF/defensive rows with no fantasy line)
    proj = proj[proj["position"].isin(("QB", "RB", "WR", "TE", "FB"))].copy()
    for c in OUTPUT_COLS:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[OUTPUT_COLS].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    # grain guard: exactly ONE row per player. An upstream join fan (e.g. a multi-position current
    # depth-chart row) must never duplicate a player on the board — keep the highest-fp row and warn
    # loudly if any were dropped so the fan gets investigated at the source.
    before = len(proj)
    proj = proj.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    if len(proj) < before:
        log.warning("grain guard dropped %d duplicate player_id row(s) — an upstream join fanned a "
                    "player; investigate (the role/depth-chart merge is the usual culprit)", before - len(proj))
    return proj


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Validation — coverage + face-validity + holdout sanity (the edge-independent gate)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def coverage_report(proj: pd.DataFrame, base: pd.DataFrame) -> dict:
    by_pos = proj.groupby("position").size().to_dict()
    vets = proj[~proj["is_rookie"]]
    rks = proj[proj["is_rookie"]]
    # draft-relevant base-season players that did NOT get a projection (gap)
    projected_ids = set(proj["player_id"])
    relevant = base[base["games_played"] >= 4]
    gap = relevant[~relevant["player_id"].isin(projected_ids)]
    return {
        "n_total": int(len(proj)),
        "n_veterans": int(len(vets)),
        "n_rookies": int(len(rks)),
        "by_position": {k: int(v) for k, v in sorted(by_pos.items())},
        "n_rookies_by_pos": {k: int(v) for k, v in rks.groupby("position").size().items()},
        "n_base_relevant_players_ge4g": int(len(relevant)),
        "n_relevant_gap": int(len(gap)),
        "pct_relevant_covered": round(100.0 * (1 - len(gap) / max(1, len(relevant))), 1),
    }


def holdout_backtest(con, base_season: int, target_season: int, schema: str,
                     usage_role_blend: float | None = None) -> dict:
    """Replicate the VETERAN method for an earlier base season and score its projected PPR ranking
    against the realized next season. The behavioural sanity check that the method has signal (rank
    correlation), not a calibration claim."""
    base = load_base_season(con, base_season, schema)
    priors = positional_pergame_priors(base)
    kw = {} if usage_role_blend is None else {"usage_role_blend": usage_role_blend}
    vets = project_veterans(base, priors, target_season, **kw)
    vets = vets[vets["position"].isin(("QB", "RB", "WR", "TE", "FB"))]
    real = load_realized_season(con, target_season, schema)
    m = vets.merge(real, on="player_id", how="inner")
    m = m[m["g"] >= 6]  # players who actually played the target season
    if len(m) < 30:
        return {"n": int(len(m)), "note": "insufficient overlap for a stable read"}
    sp = m[["proj_fp_ppr", "real_fp_ppr"]].corr(method="spearman").iloc[0, 1]
    pr = m[["proj_fp_ppr", "real_fp_ppr"]].corr(method="pearson").iloc[0, 1]
    mae = float((m["proj_fp_ppr"] - m["real_fp_ppr"]).abs().mean())
    # top-24 overlap (a "did we identify the studs" read)
    top_proj = set(m.nlargest(24, "proj_fp_ppr")["player_id"])
    top_real = set(m.nlargest(24, "real_fp_ppr")["player_id"])
    return {
        "base_season": base_season, "target_season": target_season, "n": int(len(m)),
        "spearman": round(float(sp), 3), "pearson": round(float(pr), 3), "mae_ppr": round(mae, 1),
        "top24_overlap": len(top_proj & top_real), "top24_of": 24,
    }


def score_vs_realized(con, proj: pd.DataFrame, target_season: int, schema: str) -> dict:
    """Grade a FULL emitted projection (veterans + rookies) against the realized target season —
    overall + per-position Spearman (rank), MAE, and realized-top-24 hit rate. Only valid for a
    COMPLETED season (realized exists). This is the multi-season backtest the MVP is judged on."""
    real = load_realized_season(con, target_season, schema)
    m = proj.merge(real, on="player_id", how="inner")
    m = m[m["g"] >= 6]
    if len(m) < 30:
        return {"projection_season": target_season, "n": int(len(m)), "note": "thin overlap"}

    def _sp(d):
        return float(d[["proj_fp_ppr", "real_fp_ppr"]].corr(method="spearman").iloc[0, 1])

    top = min(24, len(m))
    hit = len(set(m.nlargest(top, "proj_fp_ppr")["player_id"]) & set(m.nlargest(top, "real_fp_ppr")["player_id"]))
    out = {"projection_season": target_season, "n": int(len(m)),
           "spearman_all": round(_sp(m), 3), "mae_ppr": round(float((m["proj_fp_ppr"] - m["real_fp_ppr"]).abs().mean()), 1),
           f"top{top}_hit": f"{hit}/{top}"}
    for pos in ("QB", "RB", "WR", "TE"):
        d = m[m["position"] == pos]
        if len(d) >= 10 and d["proj_fp_ppr"].std() > 0 and d["real_fp_ppr"].std() > 0:
            out[f"sp_{pos}"] = round(_sp(d), 3)
    return out


def _md_table(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".1f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(proj: pd.DataFrame, cov: dict, backtests: list[dict], path: Path,
                 base_season: int, projection_season: int, face: dict | None = None) -> None:
    a = []
    p = a.append
    p(f"# NF-FASTPATH — {projection_season} NFL fantasy season projections (raw stat-line, MVP-1)")
    p("")
    p(f"**Model:** `{MODEL_VERSION}` · **base season:** {base_season} → **projects:** {projection_season} "
      f"· **generated:** {datetime.now(timezone.utc).isoformat()}")
    p("")
    p("> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the "
      "betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity "
      "check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` "
      "points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / "
      "NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not "
      "hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + "
      "P1A) and must be recalibrated before pricing.")
    p("")
    p("## 1. The projection method (honest framing)")
    p("")
    p("- **Veterans** — a **3-year recency+games-weighted** per-game line (weight = 0.6^age × games, "
      "so a career year or a down/injured year regresses toward the player's own baseline — the fix "
      "for single-season recency bias, esp. the spiky rushing-TD stat that ranked Trevor Lawrence "
      "QB2 off a fluke 9-rush-TD 2025), shrunk toward a conservative positional prior (position "
      "median) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 "
      "blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve "
      "`per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` "
      "(Malik Willis was its #1).")
    p("- **Usage-share role signal (NF-D2 slice 1)** — expected games is further refined by the "
      "base-season USAGE share (snap share for RB/WR, target share for TE; QB untouched), the "
      "volume-earner-vs-depth-body separator. Ablated for held-out within-position ρ lift over the "
      "MVP-1 baseline (RB +0.009 / WR +0.009 / TE +0.007 / QB +0.000, 2019–2025) — see "
      "`ablation_results/nf_d2_snap_role_ablation.md`. Leakage-safe (a realized base-season quantity) "
      "and non-double-counting (it moves only playing-time, not the per-game production line).")
    p("- **Team-change / depth-jump opportunity (NF-D2 slice 3)** — for a player who CHANGES teams "
      "(base-season team ≠ projection-season team) at RB/WR/TE, the per-game line is rescaled toward "
      "the NEW role's volume level (a stale old-team line understates a role UPGRADE, overstates a "
      "player buried on a new depth chart). Ablated held-out lift over slice-1: RB +0.008 / WR +0.006 "
      "/ TE +0.007 / QB +0.000, with the MOVER subpopulation +~0.03 — see "
      "`ablation_results/nf_d2_team_context_ablation.md`. Leakage-safe (the forward team + role are "
      "read from the freshest preseason depth-chart snapshot). Fires only where the depth feed has "
      "captured the move, so re-run as the offseason depth charts refresh through camp.")
    p("- **Vegas team environment — QB (NF-D2 slice 4)** — a QB's projection is tilted (≤±10%) by the "
      "projection-season team's WEEK-1 implied points, a LEAKAGE-SAFE forward read on the offense (a "
      "Week-1 line is set before any of the season's games). Ablated held-out QB ρ lift +0.012 "
      "(2020–2025) — see `ablation_results/nf_d2_team_context_ablation.md`. QB-scoped (RB/WR/TE carry "
      "team context via their own usage line). A richer forward-Vegas signal (preseason win totals) "
      "would grow this toward its +0.06 leaky ceiling.")
    p("- **Injury / availability (NF-D2 slice 5)** — a player flagged unavailable in the "
      "projection-season roster (reserve/IR, PUP, NFI, suspension) has expected games CAPPED toward "
      "the empirical status level (RES→3.7 g, PUP→2.4 vs ACT→13.2), so a shelved player is not ranked "
      "as startable. Leakage-safe (a preseason designation). The measured ρ lift is small (the eval "
      "excludes players with <6 realized games — the very ones this fixes) — it is a CORRECTNESS fix. "
      "⚠️ The nflverse injury REPORT is in-season only and 2026 is unpublished; the roster PUP/IR flag "
      "is the forward source and populates through camp, so re-run as designations land (a live "
      "injury-news feed would surface offseason-surgery cases earlier).")
    p("- **ADP market consensus (NF-D2 #6 / NF-D3) — tested; ships OFF, kept as the BENCHMARK.** "
      "Preseason ADP (Fantasy Football Calculator real-draft consensus, leakage-safe) is the strongest "
      "single forward ordering signal, but it is the MARKET's output, not orthogonal information. "
      "Ablated 2019–2024, a clean POSITION SPLIT emerged: at QB/RB the market OUT-ORDERS the box-score "
      "model (covered-tier ρ QB 0.48 vs 0.33, RB 0.62 vs 0.52) and the model's fades are noise; at "
      "WR/TE the model TIES/BEATS ADP and — crucially — where model and ADP most disagree the MODEL "
      "predicts the realized finish better (overall 0.51 vs 0.28). A blanket blend is net-negative on "
      "the board and would erase that disagreement edge, so this NON-MARKET projection stays independent "
      "(`_ADP_PRIOR_BLEND=0.0`). ADP is delivered as the NF-D3 benchmark asset (`run_adp_ingest.py` → "
      "`nfl/fantasy/benchmarks/`) + an optional evidence-backed QB/RB-scoped prior "
      "(`blend_adp_prior`). See `ablation_results/nf_d2_adp_ablation.md`.")
    p("- **Rookies (QB/RB/WR/TE)** — a historical draft-slot → rookie-year production curve (power-law "
      "per position, fit on prior classes) nudged by the **NCAAF-P1A residual** (`projected_nfl_z` vs "
      "the slot-expected z — talent the draft board disagreed with), with deliberately wide intervals. "
      "Defensive/OL rookies carry no fantasy line and are excluded (≈0, per P1A).")
    p("")
    p("## 2. Coverage report")
    p("")
    p("```json")
    p(json.dumps(cov, indent=2))
    p("```")
    p("")
    p("## 3. Multi-season backtest — this model vs realized outcomes")
    p("")
    p("Each PRIOR season below was projected with the SAME model (base = season−1, 3-yr regression) and "
      "scored against what actually happened — the FULL projection (veterans + rookies), over players "
      "who played ≥6 games. `spearman_all` (rank) is the headline; `sp_<POS>` is within-position rank "
      "correlation (what matters for drafting); `topN_hit` = of the realized top-24, how many the model "
      "ranked top-24. A signal check across seasons, not a calibration claim.")
    p("")
    if backtests:
        p(_md_table(pd.DataFrame(backtests)))
    p("")
    p("## 4. Face validity — top 25 overall (projected PPR)")
    p("")
    show = ["player_name", "position", "team_id", "source", "proj_games",
            "proj_fp_ppr", "fp_ppr_p10", "fp_ppr_p90"]
    p(_md_table(proj.head(25)[show]))
    p("")
    for pos in ("QB", "RB", "WR", "TE"):
        p(f"### Top 12 {pos}")
        p("")
        p(_md_table(proj[proj["position"] == pos].head(12)[show]))
        p("")
    p("## 5. Face validity — top 15 ROOKIES (P1A-attached)")
    p("")
    if face is not None:
        p("**NF1.4 rookie over-placement gate** (advisory — a genuinely exceptional class may trip "
          "it): the #1 overall slot must be a veteran, no rookie inside the overall top 10, and no "
          "rookie projected above the Q90 of realized rookie seasons at his position over the FULL "
          "drafted population.")
        p("")
        p("```json")
        p(json.dumps(face, indent=2, default=float))
        p("```")
        p("")
    rk = proj[proj["is_rookie"]].head(15)[
        ["player_name", "position", "draft_overall", "proj_games", "proj_fp_ppr", "fp_ppr_p10", "fp_ppr_p90"]
    ]
    p(_md_table(rk))
    p("")
    p("## 6. Limitations")
    p("")
    p("- **First-pass MVP** — the full NF1 model (posterior-predictive, weekly, §0.5 bake-off) refines "
      "this. The gate here is face-validity + coverage, not a selected model.")
    p("- **Expected-games is a role heuristic, not a depth-chart oracle** — offseason moves (trades, "
      "signings, camp battles, holdouts) are not yet ingested; a base-season backup who wins a 2026 "
      "job is under-projected until depth charts refresh. Surfaced via the wide games interval.")
    p("- **Rookie uncertainty is PARAMETER uncertainty** (slot curve + P1A `sd`), not a calibrated "
      "predictive interval — NF-C1/pricing must recalibrate (the E13.6 pattern).")
    p("- **Rookie team = NULL** (2026 draftees are not in the base-season role dimension) — kept NULL, "
      "not guessed.")
    p("- **Two-point conversions kept NULL** (rare/idiosyncratic); fumbles-lost is a modest per-touch "
      "estimate. Both are small scoring nuisance terms.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-FASTPATH — 2026 NFL fantasy season projections")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-season", type=int, default=None,
                    help="completed base season (default: max(season) in fct_player_week)")
    ap.add_argument("--projection-season", type=int, default=None,
                    help="the primary (forward) season to project (default: base_season + 1)")
    ap.add_argument("--backtest-from", type=int, default=None,
                    help="ALSO emit projections for every prior season from this year through the "
                         "primary season (each projected off its own season-1 with the multi-year "
                         "model), and score each completed one vs realized. E.g. --backtest-from 2019")
    ap.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    ap.add_argument("--s3", action="store_true", help="also land the projection(s) to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first (see module docstring)")

    import duckdb

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        # NF-D1 cold-start fix (2026-07-25): `fct_player_week` is a roster×schedule CALENDAR
        # spine, not a played-games table — as soon as an upcoming season's schedule + rosters
        # land (the roll-forward cadence), that season enters the calendar with `played_flag`
        # false for every row (0 games actually played yet). A bare `max(season)` therefore
        # auto-detects the UPCOMING season as the "base," not the last one actually played,
        # which then projects a season with no real base data to train off. Gate on
        # `played_flag` so auto-detection only ever picks a season that has REALIZED games —
        # a no-op for every season before a schedule-only roll-forward existed.
        base_season = args.base_season or int(
            con.sql(
                f"select max(season) from {args.schema}.fct_player_week where played_flag"
            ).fetchone()[0])
        primary_season = args.projection_season or (base_season + 1)
        # the set of projection seasons to emit — the forward one, plus any backtest history
        seasons = [primary_season]
        if args.backtest_from:
            seasons = sorted(set(range(args.backtest_from, primary_season + 1)) | {primary_season})
        log.info("emitting projection seasons: %s", seasons)

        primary_proj = primary_cov = None
        face_validity: dict | None = None
        backtests: list[dict] = []
        for y in seasons:
            base_y = y - 1
            proj = build_projection(con, base_y, y, args.schema)
            log.info("  %d (base %d): %d players (%d vets, %d rookies)", y, base_y, len(proj),
                     int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()))

            # local artifacts per season
            proj.to_parquet(out_dir / f"nfl_fantasy_season_projections_{y}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(out_dir / f"nfl_fantasy_season_projections_{y}_ranked.csv", index=False)

            # land the Delta partition (season = projection year)
            if args.s3 or args.lake_root:
                n = s3io.write_dataframe(
                    proj.assign(season=int(y)), sport="nfl", source="season_projections",
                    season=int(y), tier="fantasy/derived", local_root=args.lake_root)
                log.info("    landed %d rows → nfl/fantasy/derived/season_projections season=%d", n, y)

            # score vs realized for completed seasons (the backtest)
            if y <= base_season:
                acc = score_vs_realized(con, proj, y, args.schema)
                log.info("    backtest %d: %s", y, acc)
                backtests.append(acc)

            if y == primary_season:
                primary_proj = proj
                primary_cov = coverage_report(proj, load_base_season(con, base_y, args.schema))
                log.info("  primary %d coverage: %s", y, primary_cov)
                # NF1.4 rookie over-placement gate (advisory) — measured against the FULL drafted
                # rookie population, so "what rookies actually do" includes the ones who never
                # played. A trip logs loudly; it never blocks the projection (this is a projection
                # product, and an exceptional class is allowed to be exceptional).
                face_validity = _SP.rookie_board_face_validity(
                    proj, load_rookie_training(con, base_y, args.schema, include_zero_game=True))
                if not face_validity["pass"]:
                    log.warning("NF1.4 rookie face-validity gate TRIPPED: %s", face_validity)
                else:
                    log.info("  NF1.4 rookie face-validity: pass")
    finally:
        con.close()

    (out_dir / "nfl_fantasy_projections_summary.json").write_text(
        json.dumps({"model_version": MODEL_VERSION, "primary_season": primary_season,
                    "seasons_emitted": seasons, "coverage": primary_cov,
                    "backtest_vs_realized": backtests,
                    "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2, default=float))
    dest = f"local lake {args.lake_root}" if args.lake_root else (
        "the S3 sports lake" if args.s3 else "(local only — no --s3)")
    log.info("done. landed to %s", dest)

    if not args.no_report and primary_proj is not None:
        write_report(primary_proj, primary_cov, backtests, _REPORT_PATH,
                     primary_season - 1, primary_season, face=face_validity)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
