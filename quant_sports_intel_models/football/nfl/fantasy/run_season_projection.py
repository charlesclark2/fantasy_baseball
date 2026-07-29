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
    # NF-D11 provenance: which season anchors this row's role/durability, and how many seasons the
    # player missed (0 = a normal base-season player; ≥1 = rescued + availability-discounted).
    "anchor_season", "seasons_missed",
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
    -- NF-D11: the season's realized convenience PPR TOTAL. Not a projection input — it is the
    -- prior-production signal the return-from-absence availability prior tiers a rescued player on.
    sum(case when g then fantasy_points_ppr else 0 end)::double    as fp_ppr_tot,
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


# ── NF-D11: the statuses that mean "no longer a football player" on the projection-season roster
#    snapshot. Everything else (ACT / RES / PUP / NFI / SUS / practice-squad codes) is a player who is
#    still in the league — exactly the population the base-anchor was wrongly deleting.
_OUT_OF_LEAGUE_STATUSES = ("RET", "CUT")


def resolve_base_anchor(
    per_season: pd.DataFrame, season: int, forward_ids: set | None = None
) -> pd.DataFrame:
    """NF-D11 — decide, per player, WHICH season anchors his role / durability / game-to-game sd.

    The projection needs a single "this is what the player was last doing" season. The MVP-1 rule was
    an inner join on the BASE season, whose stated purpose (keep retired / out-of-league players that
    the 3-year window would otherwise sweep in OUT of the board) is sound — but a whole-season INJURY
    is indistinguishable from retirement under that rule, so it silently DELETED productive,
    actively-drafted players (2026: Brandon Aiyuk, Tank Dell, Jonathon Brooks, MarShawn Lloyd).

    The rule now has two branches:
      • `base_season`         — the player played in the base season ⇒ anchor there (UNCHANGED; every
                                incumbent player's anchor row is bit-identical to MVP-1's).
      • `most_recent_played`  — the player has NO base-season row but the window holds real
                                production AND `forward_ids` proves he is on a PROJECTION-SEASON
                                roster / depth chart ⇒ anchor on his most-recent PLAYED season and
                                stamp `seasons_missed` so the return-from-absence availability prior
                                discounts him.
      • dropped               — no base-season row and no forward roster evidence ⇒ still excluded
                                (retired / out of the league — the anchor's original purpose).

    `forward_ids = None` or an EMPTY set means "no forward roster evidence is available" (e.g. a
    backtest season with no roster snapshot) and DISABLES the rescue entirely — degrading to exactly
    the MVP-1 universe rather than guessing. Pure (no IO).

    Returns one row per retained player: `player_id, games_played, fp_ppr_sd, position,
    anchor_season, seasons_missed, prior_best_fp, base_anchor`.
    """
    cols = ["player_id", "games_played", "fp_ppr_sd", "position", "anchor_season",
            "seasons_missed", "prior_best_fp", "base_anchor"]
    if per_season is None or per_season.empty:
        return pd.DataFrame(columns=cols)

    ps = per_season.copy()
    ps["fp_ppr_tot"] = pd.to_numeric(ps.get("fp_ppr_tot"), errors="coerce")
    # the best single season in the window — the prior-production signal the availability prior tiers on
    best_fp = ps.groupby("player_id")["fp_ppr_tot"].max().rename("prior_best_fp")

    keep = ["player_id", "games_played", "fp_ppr_sd", "position", "season"]
    base = ps[ps["season"] == season][keep].copy()
    base["base_anchor"] = "base_season"

    absent = ps[~ps["player_id"].isin(set(base["player_id"]))]
    if forward_ids:
        absent = absent[absent["player_id"].isin(set(forward_ids))]
    else:
        absent = absent.iloc[0:0]
    if not absent.empty:
        # the MOST-RECENT PLAYED season is the fallback anchor (role/durability/sd all come from it)
        idx = absent.groupby("player_id")["season"].idxmax()
        fallback = absent.loc[idx, keep].copy()
        fallback["base_anchor"] = "most_recent_played"
        out = pd.concat([base, fallback], ignore_index=True)
    else:
        out = base
    out = out.rename(columns={"season": "anchor_season"})
    out["seasons_missed"] = (int(season) - pd.to_numeric(out["anchor_season"], errors="coerce")).astype(float)
    out = out.merge(best_fp.reset_index(), on="player_id", how="left")
    return out[cols]


def load_forward_roster_ids(
    con, projection_season: int, schema: str = MARTS_SCHEMA, staging_schema: str = STAGING_SCHEMA
) -> set:
    """NF-D11 — the set of players with PROJECTION-SEASON roster evidence: still in the league, so a
    base-season absence is an INJURY (rescue him), not a retirement (leave him out).

    Two independent, leakage-safe sources, UNIONed because neither is complete on its own:
      • `stg_nfl_depth_charts_current` (season = projection season) — the freshest ESPN forward depth
        snapshot. This is the one that carries e.g. Brandon Aiyuk (SF, rank 8, 2026-07-24 snapshot),
        whom the nflverse offseason roster pull does not yet list.
      • `stg_nfl_weekly_rosters` at the EARLIEST available week of the projection season, minus the
        `RET`/`CUT` statuses. This is the branch that exists for HISTORICAL seasons, so it is what
        the NF-D11 ablation measures on.

    Returns an EMPTY set on any read failure — which disables the rescue (a strictly conservative
    degrade back to the MVP-1 universe), never a silent half-populated gate. WARN-tier: this feed is
    a universe gate, not a serving-critical path."""
    ids: set = set()
    try:
        dc = con.sql(f"""
            select distinct player_id from {staging_schema}.stg_nfl_depth_charts_current
            where season = {int(projection_season)} and player_id is not null
        """).df()
        ids |= set(dc["player_id"].dropna())
    except Exception as exc:  # noqa: BLE001 — WARN-tier; the roster branch below may still populate
        log.warning("NF-D11: forward depth-chart snapshot unavailable for %s (%s) — "
                    "the rescue falls back to the weekly-roster branch only", projection_season, exc)
    try:
        ros = con.sql(f"""
            select player_id, first(status order by week asc) as status
            from {staging_schema}.stg_nfl_weekly_rosters
            where season = {int(projection_season)} and player_id is not null
            group by 1
        """).df()
        ros = ros[~ros["status"].astype("string").str.upper().isin(_OUT_OF_LEAGUE_STATUSES)]
        ids |= set(ros["player_id"].dropna())
    except Exception as exc:  # noqa: BLE001 — WARN-tier
        log.warning("NF-D11: projection-season weekly rosters unavailable for %s (%s)",
                    projection_season, exc)
    if not ids:
        log.warning("NF-D11: NO forward roster evidence for %s — the base-season-absent rescue is "
                    "DISABLED for this run (the projection universe degrades to the MVP-1 rule)",
                    projection_season)
    return ids


def load_base_season(
    con, season: int, schema: str = MARTS_SCHEMA, staging_schema: str = STAGING_SCHEMA,
    projection_season: int | None = None, rescue_absent: bool = True,
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

    # NF-D11: anchor each player on the base season where he has one, else (when projection-season
    # roster evidence proves he is still in the league) on his MOST-RECENT PLAYED season. See
    # `resolve_base_anchor` — role/team/sd/durability all come from the anchor season, and
    # `seasons_missed` marks a rescued player for the return-from-absence availability prior.
    proj_season = int(projection_season) if projection_season is not None else int(season) + 1
    forward_ids = load_forward_roster_ids(con, proj_season, schema, staging_schema) if rescue_absent else set()
    anchor = resolve_base_anchor(per_season, season, forward_ids).set_index("player_id")
    weighted = weighted.join(anchor, how="inner")
    df = weighted.reset_index()
    n_rescued = int((df["base_anchor"] == "most_recent_played").sum())
    if n_rescued:
        log.info("NF-D11: %d base-season-absent player(s) RESCUED via the most-recent-played anchor "
                 "(forward roster evidence for %d)", n_rescued, proj_season)

    # team + display name from the most-recent week IN THE WINDOW. NF-D11: window-wide (was
    # base-season-only) so a rescued player — who has no base-season PLAYED row but is still on the
    # roster×schedule calendar — gets a name and a team instead of a blank board row. For a
    # base-anchored player this resolves to the same base-season row as before (max season wins).
    meta = con.sql(f"""
        select player_id, team_id, player_name
        from {schema}.fct_player_week
        where season between {lo} and {season} and week > 0 and player_id is not null
        qualify row_number() over (
            partition by player_id order by season desc, week desc, week_start_et desc) = 1
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


# The historical returner population is the SAME query for every arm / every projected season, so it
# is read ONCE per (connection, schema) and filtered to the in-fold target seasons in pandas.
_ABSENCE_HISTORY_CACHE: dict = {}


def load_absence_return_history(con, schema: str = MARTS_SCHEMA,
                                staging_schema: str = STAGING_SCHEMA) -> pd.DataFrame:
    """NF-D11 — the historical RETURN-FROM-ABSENCE population the availability prior is fit on.

    One row per (target season Y, player) where the player (a) played ZERO games in Y−1, (b) has real
    production somewhere in Y−3..Y−2, and (c) carries a Y roster row that is not RET/CUT — i.e. the
    exact population `resolve_base_anchor` now rescues, reconstructed for every season we have data
    for. Each row carries the preseason-known predictors (`prior_games`, `prior_best_fp`,
    `seasons_missed`, `position`) and the OUTCOME (`realized_games`, `realized_fp_ppr`), plus the
    season's base-anchored mean games (`healthy_mean_games`) as the `ratio` family's denominator.

    ⚠️ The caller MUST filter to `target_season <= base_season` before fitting — that is what keeps
    the prior in-fold. Cached per (connection, schema): the query is season-agnostic."""
    # keyed on the live connection; the cache VALUE holds a reference to `con` so the object cannot
    # be collected and its id() re-used by a later connection (a stale-cache hazard, not a leak —
    # a run opens one connection).
    key = (id(con), schema, staging_schema)
    if key in _ABSENCE_HISTORY_CACHE:
        return _ABSENCE_HISTORY_CACHE[key][1].copy()
    sql = f"""
    with pg as (
        select season, player_id, max(position) as position,
               count_if(played_flag and not is_bye) as games,
               sum(case when played_flag then fantasy_points_ppr else 0 end)::double as fp_ppr
        from {schema}.fct_player_week where week > 0 and player_id is not null
        group by 1, 2
    ),
    played as (select * from pg where games > 0),
    ros as (
        select season, player_id, first(status order by week asc) as status
        from {staging_schema}.stg_nfl_weekly_rosters where player_id is not null group by 1, 2
    ),
    cand as (
        select r.season as target_season, r.player_id
        from ros r
        where upper(coalesce(r.status, 'ACT')) not in ('RET', 'CUT')
    ),
    win as (
        select c.target_season, c.player_id,
               max(case when p.season = c.target_season - 1 then p.games end)   as base_games,
               max(case when p.season between c.target_season - 3
                             and c.target_season - 2 then p.season end)          as anchor_season,
               max(case when p.season between c.target_season - 3
                             and c.target_season - 2 then p.fp_ppr end)          as prior_best_fp
        from cand c
        join played p on p.player_id = c.player_id
                     and p.season between c.target_season - 3 and c.target_season - 1
        group by 1, 2
    ),
    returners as (
        select w.target_season, w.player_id, w.anchor_season, w.prior_best_fp,
               w.target_season - w.anchor_season as seasons_missed
        from win w
        where w.base_games is null and w.anchor_season is not null
    ),
    healthy as (
        -- the season's BASE-ANCHORED comparison level: mean realized games among players who DID
        -- play the base season (the `ratio` family's denominator + the honest contrast in the report)
        select p.season + 1 as target_season, avg(coalesce(n.games, 0)) as healthy_mean_games
        from played p
        left join pg n on n.player_id = p.player_id and n.season = p.season + 1
        where p.position in ('QB', 'RB', 'WR', 'TE', 'FB')
        group by 1
    )
    select r.target_season, r.player_id, r.anchor_season, r.seasons_missed,
           coalesce(r.prior_best_fp, 0.0) as prior_best_fp,
           a.position, a.games as prior_games,
           coalesce(n.games, 0) as realized_games,
           coalesce(n.fp_ppr, 0.0) as realized_fp_ppr,
           h.healthy_mean_games
    from returners r
    join played a on a.player_id = r.player_id and a.season = r.anchor_season
    left join pg n on n.player_id = r.player_id and n.season = r.target_season
    left join healthy h on h.target_season = r.target_season
    where a.position in ('QB', 'RB', 'WR', 'TE', 'FB')
    """
    try:
        hist = con.sql(sql).df()
    except Exception as exc:  # noqa: BLE001 — WARN-tier: no history ⇒ the prior falls back to the
        log.warning("NF-D11: return-from-absence history unavailable (%s) — the availability prior "
                    "falls back to its pooled empirical constants", exc)
        hist = pd.DataFrame(columns=["target_season", "player_id", "anchor_season", "seasons_missed",
                                     "prior_best_fp", "position", "prior_games", "realized_games",
                                     "realized_fp_ppr", "healthy_mean_games"])
    _ABSENCE_HISTORY_CACHE[key] = (con, hist)
    return hist.copy()


def fit_absence_prior_for(con, base_season: int, family: str = _SP._ABSENCE_PRIOR_FAMILY,
                          schema: str = MARTS_SCHEMA, staging_schema: str = STAGING_SCHEMA):
    """NF-D11 — the IN-FOLD availability prior for a board projected off `base_season`: fit on
    returner cohorts whose RETURN YEAR is already complete (`target_season <= base_season`), so no
    fit ever sees the season being projected."""
    hist = load_absence_return_history(con, schema, staging_schema)
    in_fold = hist[pd.to_numeric(hist["target_season"], errors="coerce") <= int(base_season)]
    prior = _SP.fit_absence_return_prior(in_fold, family=family)
    log.debug("NF-D11 absence prior (%s) fit on %d in-fold returners ≤ %s: levels=%s",
              family, prior.n_fit, base_season, prior.levels)
    return prior


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
    `ablation_results/nf1_4_rookie.md`), so only the interval changes.

    🚨 NF1.7 — `projected_nfl_z` / `projected_nfl_z_sd` are carried DELIBERATELY, and dropping them
    would degrade the per-player band SILENTLY, in two separate ways:
      * without `projected_nfl_z`, `rookie_point_projection` rebuilds each historical rookie's point
        WITHOUT the P1A residual nudge — so the band would be fitted against a conditioning variable
        that differs from the one it is pasted onto: the class-level defect in a new disguise;
      * without `projected_nfl_z_sd`, the `z_sd` column of the shipped quantile regression's design
        matrix is a CONSTANT ZERO at fit time, so its coefficient fits to ~0 and the feature is
        quietly discarded — while at serve time the live P1A rows DO carry a real sd.
    Neither failure raises. Guard: `betting_ml/tests/test_nf1_7_rookie_intervals.py`."""
    rk = pd.read_parquet(_ROOKIE_PARQUET)
    keep = ["gsis_id", "position_group", "draft_overall", "draft_year",
            "projected_nfl_z", "projected_nfl_z_sd"]
    rk = rk[
        rk["position_group"].isin(ROOKIE_POSITIONS)
        & pd.to_numeric(rk["draft_overall"], errors="coerce").notna()
        & (pd.to_numeric(rk["draft_year"], errors="coerce") <= upto_season)
    ][[c for c in keep if c in rk.columns]].copy()
    con.register("rk_train", rk)
    join, having = ("left join", "") if include_zero_game else ("join", "where games > 0")
    hist = con.sql(f"""
        with ry as (
            select r.gsis_id, r.position_group, r.draft_overall, r.draft_year,
                any_value(r.projected_nfl_z) as projected_nfl_z,
                any_value(r.projected_nfl_z_sd) as projected_nfl_z_sd,
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
            group by 1,2,3,4
        )
        select * from ry {having}
    """).df()
    return hist


def load_realized_season(con, season: int, schema: str = MARTS_SCHEMA,
                         include_zero_game: bool = False) -> pd.DataFrame:
    """Realized convenience PPR total for a season (for the holdout backtest).

    `include_zero_game` (NF-D11) keeps players who ended up playing ZERO games. The default
    survivor-filtered view is right for the ρ backtest, but it is exactly WRONG for grading an
    AVAILABILITY prior: ~43% of returners play no games, so filtering them out would score the prior
    only on the cases where it was least needed."""
    having = "" if include_zero_game else "having g > 0"
    return con.sql(f"""
        select player_id, count_if(played_flag and not is_bye) as g,
               sum(case when played_flag then fantasy_points_ppr else 0 end) as real_fp_ppr
        from {schema}.fct_player_week where season = {season} and week > 0
        group by 1 {having}
    """).df()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Projection assembly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_projection(con, base_season: int, projection_season: int, schema: str,
                     usage_role_blend: float | None = None,
                     mover_opportunity_blend: float | None = None,
                     env_tilt_blend: float | None = None,
                     injury_override_blend: float | None = None,
                     xfp_td_blend: float | None = None,
                     rescue_absent: bool = True,
                     absence_prior_family: str | None = None,
                     absence_prior_blend: float | None = None) -> pd.DataFrame:
    base = load_base_season(con, base_season, schema, projection_season=projection_season,
                            rescue_absent=rescue_absent)
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
    # NF-D11: the return-from-absence availability prior, fit IN-FOLD (return years ≤ base_season)
    # and applied to the rows the base-anchor fallback rescued. Skipped entirely when nothing was
    # rescued (the historical-backtest seasons with no roster snapshot) so it can never touch an
    # incumbent player.
    a_blend = _SP._ABSENCE_PRIOR_BLEND if absence_prior_blend is None else absence_prior_blend
    kw["absence_prior_blend"] = a_blend
    if a_blend > 0 and "seasons_missed" in base.columns and (base["seasons_missed"] >= 1).any():
        kw["absence_prior"] = fit_absence_prior_for(
            con, base_season, family=absence_prior_family or _SP._ABSENCE_PRIOR_FAMILY, schema=schema)
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
    # NF-D11: how many rows the most-recent-played fallback rescued, and who the most productive of
    # them are — the standing visibility on a universe rule that used to delete players silently.
    sm = pd.to_numeric(proj.get("seasons_missed"), errors="coerce") if "seasons_missed" in proj else None
    resc = proj[sm >= 1] if sm is not None else proj.iloc[0:0]
    top_resc = resc.nlargest(min(10, len(resc)), "proj_fp_ppr") if len(resc) else resc
    return {
        "n_total": int(len(proj)),
        "n_veterans": int(len(vets)),
        "n_rookies": int(len(rks)),
        "n_returning_from_absence": int(len(resc)),
        "top_returning_from_absence": [
            {"player": r["player_name"], "pos": r["position"], "anchor_season": r.get("anchor_season"),
             "proj_fp_ppr": round(float(r["proj_fp_ppr"]), 1),
             "p10_p90": [float(r["fp_ppr_p10"]), float(r["fp_ppr_p90"])]}
            for _, r in top_resc.iterrows()
        ],
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


# The ADP samples the shipped boards actually reference (`export_draft_board_json.PRESET_ADP_FORMAT`
# × the two league sizes). The audit runs over ALL of them, not one board: ADP is format-specific
# (Josh Allen is 28.1 in PPR and 1.5 in superflex), so a universe gap can be invisible in one sample
# and a first-round hole in another.
_ADP_AUDIT_SAMPLES = (("ppr", 12), ("ppr", 10), ("half-ppr", 12), ("half-ppr", 10),
                      ("standard", 12), ("standard", 10), ("2qb", 12), ("2qb", 10))


def adp_coverage_check(con, proj: pd.DataFrame, projection_season: int,
                       samples: tuple = _ADP_AUDIT_SAMPLES, schema: str = MARTS_SCHEMA) -> dict:
    """NF-D11 — the STANDING coverage diagnostic, run at the end of every board build: diff the
    market's ADP census against the projection's own universe, across every shipped ADP sample, and
    log/return the two failure classes SEPARATELY (a name-alias miss vs a genuine universe absence,
    which route to completely different fixes). See `projection_coverage`.

    WARN-tier and best-effort by construction: FFC is a network fetch, so a failure on one sample
    logs and is skipped — a coverage AUDIT must never be able to fail a board build."""
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A
    from quant_sports_intel_models.football.nfl.fantasy import projection_coverage as PC
    by_sample: dict[str, dict] = {}
    for fmt, teams in samples:
        key = f"{fmt}/{teams}"
        try:
            adp = A.fetch_ffc_adp(projection_season, fmt=fmt, teams=teams)
        except Exception as exc:  # noqa: BLE001 — WARN-tier: the audit is advisory, never a gate
            log.warning("NF-D11 ADP coverage: sample %s skipped — FFC fetch failed (%s)", key, exc)
            continue
        if adp is None or adp.empty:
            log.warning("NF-D11 ADP coverage: sample %s has no ADP data for %s", key, projection_season)
            continue
        by_sample[key] = PC.audit_adp_coverage(adp, proj)
    if not by_sample:
        log.warning("NF-D11 ADP coverage audit produced NO samples — the universe went unaudited "
                    "this run (check FFC reachability)")
        return {"skipped": True, "season": int(projection_season)}
    audit = PC.merge_sample_audits(by_sample)
    audit["season"] = int(projection_season)
    PC.log_adp_coverage(audit, label=f"{projection_season} · {len(by_sample)} ADP samples")
    if audit.get("n_actionable_true_absences"):
        log.warning("NF-D11: %d ADP player(s) inside the draftable range are ABSENT from the %s "
                    "projection universe — investigate the player spine before the board ships",
                    audit["n_actionable_true_absences"], projection_season)
    else:
        log.info("NF-D11 ADP coverage: no draftable-range universe gaps across %d samples "
                 "(min sample match %.1f%%)", audit["n_samples"], audit.get("pct_matched_min") or 0.0)
    return audit


def write_report(proj: pd.DataFrame, cov: dict, backtests: list[dict], path: Path,
                 base_season: int, projection_season: int, face: dict | None = None,
                 adp_audit: dict | None = None) -> None:
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
    p("## 6. NF-D11 — projection UNIVERSE (injured-all-year rescue) + the ADP coverage audit")
    p("")
    p("The base-season anchor used to DELETE any player who missed the entire base season — a "
      "whole-season injury was indistinguishable from retirement — so productive, actively-drafted "
      "players (2026: Brandon Aiyuk, Tank Dell, Jonathon Brooks, MarShawn Lloyd) had no board row at "
      "all. They are now anchored on their MOST-RECENT PLAYED season, gated on projection-season "
      "roster/depth-chart evidence (retired / out-of-league players stay excluded), and discounted by "
      "the RETURN-FROM-ABSENCE availability prior: expected games capped toward the empirical return "
      "level (historically a returner plays ~4.1 games vs ~10.4 for a base-season-present player; "
      "~43% play ZERO) with the games band widened to the empirical returner SD. **Honest by "
      "construction — a returning player carries a WIDE band and `confidence = low`, never a rosy "
      "point.** See `ablation_results/nf_d11_absence_prior.md` for the §0.5 bake-off.")
    p("")
    resc = proj[pd.to_numeric(proj.get("seasons_missed"), errors="coerce") >= 1] \
        if "seasons_missed" in proj.columns else proj.iloc[0:0]
    p(f"**Rescued this run: {len(resc)}** (rows anchored on a prior played season).")
    p("")
    if len(resc):
        p(_md_table(resc.head(15)[["player_name", "position", "team_id", "anchor_season",
                                   "proj_games", "proj_fp_ppr", "fp_ppr_p10", "fp_ppr_p90",
                                   "confidence"]]))
        p("")
    if adp_audit:
        p("### Standing ADP coverage audit (the check that found this)")
        p("")
        p("Every ADP name is normalized and diffed against the projection's own (name, position) set, "
          "with the projection ALSO indexed by SURNAME so the two failure classes stay separable: an "
          "`alias_candidate` (surname present at that position ⇒ a name-map miss) vs a `true_absence` "
          "(genuinely not in our universe ⇒ a MODEL/universe gap). One diff caught both a join bug "
          "and this model gap.")
        p("")
        p("```json")
        p(json.dumps({k: v for k, v in adp_audit.items() if k != "alias_candidates"} if
                     len(adp_audit.get("alias_candidates", [])) > 25 else adp_audit,
                     indent=2, default=float))
        p("```")
        p("")
    p("## 7. Limitations")
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
    p("- **A rescued (NF-D11) player's per-game LINE is stale by a full season** — the availability "
      "prior discounts his GAMES, but the production line itself is his last healthy year's, blended "
      "over the recency window. Age/scheme/role change since then is not modelled; the wide band and "
      "`confidence = low` are the honest surface for that.")
    p("- **The rescue gate is only as good as the roster feed** — a player the projection-season "
      "depth-chart/roster snapshot has not caught up to stays excluded until it refreshes (the same "
      "re-run-through-camp cadence the mover/injury slices need).")
    p("- **A rescued player is FADED vs his ADP, by design** — the fitted availability haircut is "
      "harsher than draft-room optimism (2026: Tank Dell WR95 vs ~157 ADP, Brandon Aiyuk WR112 vs "
      "~148). 431 historical returners say a full-season absence costs far more availability than a "
      "draft board prices. It is an open fade, not a hidden claim: the ADP column renders beside our "
      "rank, the p90 still covers a healthy season, and `confidence = low` marks the row.")
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
    ap.add_argument("--no-adp-audit", action="store_true",
                    help="skip the NF-D11 standing ADP coverage diagnostic (it needs a network fetch "
                         "of the FFC ADP sample; the audit is advisory and never gates the build)")
    ap.add_argument("--no-rescue-absent", action="store_true",
                    help="NF-D11 escape hatch: rebuild with the MVP-1 universe rule (delete every "
                         "player who missed the whole base season). Diagnostic only.")
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
        adp_audit: dict | None = None
        backtests: list[dict] = []
        for y in seasons:
            base_y = y - 1
            proj = build_projection(con, base_y, y, args.schema,
                                    rescue_absent=not args.no_rescue_absent)
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
                primary_cov = coverage_report(
                    proj, load_base_season(con, base_y, args.schema, projection_season=y))
                log.info("  primary %d coverage: %s", y, primary_cov)
                # NF-D11 standing coverage diagnostic — the market's ADP census vs our universe.
                # WARN-tier: a network fetch failure logs and yields an empty audit, never a failure.
                if not args.no_adp_audit:
                    adp_audit = adp_coverage_check(con, proj, y, schema=args.schema)
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
                    "adp_coverage_audit": adp_audit,
                    "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2, default=float))
    dest = f"local lake {args.lake_root}" if args.lake_root else (
        "the S3 sports lake" if args.s3 else "(local only — no --s3)")
    log.info("done. landed to %s", dest)

    if not args.no_report and primary_proj is not None:
        write_report(primary_proj, primary_cov, backtests, _REPORT_PATH,
                     primary_season - 1, primary_season, face=face_validity, adp_audit=adp_audit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
