"""run_nf_w7_kdst_weekly.py — NF-W7 §0.5 bake-off: weekly KICKER + DST distributional
projections with exact tier scoring as expected-bucket probabilities.

Everything decidable in advance lives as a CONSTANT in `kdst_weekly.py`; this runner READS it
(NF-D16). The narrative pre-registration is committed at `ablation_results/nf_w7_preregistration.md`
BEFORE the full run.

PIPELINE
  LAYER A (components): 12 legs — kicker attempt volume / XP volume / distance-conditional make /
  band allocation; DST sacks / INT / fumble recoveries / rare events (TD, safety, block) /
  PA-bucket / YA-bucket probabilities — each a declared arm family vs its climatology + entity
  foils, with degenerates, a permutation control, per-form peeking oracles floored at matched n.
  LAYER B (THE GATE): the assembled fantasy-point distribution (components → exact tier scoring)
  vs the honest K+DST climatology null, the board-EB weekly read, and the direct-learned points
  foil, per target (k_points / dst_points), on the same 8-fold axis. CRPS on the dense 199-level
  grid everywhere a bank is scored.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7_kdst_weekly --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7_kdst_weekly
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7_kdst_weekly --rewrite-report
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_w7")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"

# ── Source SQL (every literal is scanned against the deferred contract, comments stripped) ──────
SCHED_SQL = """
select season, week, home_team, away_team, gameday, div_game, roof,
       home_score, away_score
from {sched}
where season between {lo} and {hi} and game_type = 'REG'
"""

TEAM_WEEK_SQL = """
select season, week, team, opponent_team,
       coalesce(def_sacks, 0)::double                        as def_sacks,
       coalesce(def_interceptions, 0)::double                as def_int,
       coalesce(fumble_recovery_opp, 0)::double              as def_fumble_rec,
       (coalesce(def_tds, 0) + coalesce(special_teams_tds, 0))::double as dst_td,
       coalesce(def_safeties, 0)::double                     as def_safety,
       (coalesce(fg_blocked, 0) + coalesce(pat_blocked, 0)
        + coalesce(pt_blocked, 0))::double                   as def_blocked_kick,
       coalesce(def_qb_hits, 0)::double                      as def_qb_hits,
       coalesce(def_tackles_for_loss, 0)::double             as def_tfl,
       coalesce(sacks_suffered, 0)::double                   as sacks_taken,
       (coalesce(passing_interceptions, 0)
        + coalesce(fumbles_lost_total, 0))::double           as giveaways,
       (coalesce(passing_yards, 0) + coalesce(rushing_yards, 0)
        + coalesce(sack_yards_lost, 0))::double              as off_net_yards,
       coalesce(passing_yards, 0)::double                    as off_pass_yards
from {team_week}
where season_type = 'REG' and season between {lo} and {hi} and team is not null
"""

KICKER_WEEK_SQL = """
select season, week, player_id, max(player_name) as player_name, max(team) as team,
       sum(coalesce(fg_att, 0))::double  as fg_att,
       sum(coalesce(pat_att, 0))::double as xp_att,
       sum(coalesce(pat_made, 0))::double as pat_made,
       sum(coalesce(fg_made_0_19, 0) + coalesce(fg_made_20_29, 0)
           + coalesce(fg_made_30_39, 0))::double as fg_made_0_39,
       sum(coalesce(fg_made_40_49, 0))::double   as fg_made_40_49,
       sum(coalesce(fg_made_50_59, 0) + coalesce(fg_made_60_, 0))::double as fg_made_50p
from {player_week}
where season_type = 'REG' and position = 'K' and season between {lo} and {hi}
  and player_id is not null
group by 1, 2, 3
"""

ROSTER_K_SQL = """
select season, week, team, gsis_id as player_id, full_name as player_name
from {rosters}
where position = 'K' and status = 'ACT' and game_type = 'REG'
  and season between {lo} and {hi} and gsis_id is not null
"""

TEAM_PBP_BOX_SQL = """
select season, week, posteam as team,
       count(distinct fixed_drive)                                          as drives,
       max(posteam_score_post)                                              as points,
       avg(epa)  filter (where play_type in ('pass','run'))                 as epa_per_play,
       count(distinct fixed_drive) filter (where yardline_100 <= 20)        as rz_trips,
       count(distinct fixed_drive)
           filter (where yardline_100 <= 20
                   and fixed_drive_result = 'Touchdown')                    as rz_td_drives,
       count(distinct fixed_drive) filter (where yardline_100 <= 35)        as fgrange_trips,
       count(*) filter (where field_goal_attempt = 1)                       as team_fg_att
from {pbp}
where season_type = 'REG' and season between {lo} and {hi} and posteam is not null
group by 1, 2, 3
"""

ATTEMPT_SQL = """
select season, week, posteam as team, play_id,
       kicker_player_id, kick_distance::double as kick_distance,
       case when field_goal_result = 'made' then 1.0 else 0.0 end as made
from {pbp}
where season_type = 'REG' and season between {lo} and {hi}
  and field_goal_attempt = 1 and kick_distance is not null
  and kicker_player_id is not null
"""


# ── Sources ─────────────────────────────────────────────────────────────────────────────────────
def _load(seasons: tuple[int, int]) -> dict[str, pd.DataFrame]:
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q
    lo, hi = seasons
    sqls = {
        "sched": SCHED_SQL.format(sched=delta("schedules"), lo=lo, hi=hi),
        "team_week": TEAM_WEEK_SQL.format(team_week=delta("stats_team_week"), lo=lo, hi=hi),
        "kicker_week": KICKER_WEEK_SQL.format(player_week=delta("stats_player_week"), lo=lo, hi=hi),
        "roster": ROSTER_K_SQL.format(rosters=delta("weekly_rosters"), lo=lo, hi=hi),
        "team_box": TEAM_PBP_BOX_SQL.format(pbp=delta("pbp"), lo=lo, hi=hi),
        "attempts": ATTEMPT_SQL.format(pbp=delta("pbp"), lo=lo, hi=hi),
    }
    for name, sql in sqls.items():
        KW.assert_source_query_is_clean(sql)
    return {name: q(sql) for name, sql in sqls.items()}


def _sides(sched: pd.DataFrame) -> pd.DataFrame:
    # ⚠️ the NF-W3 measured defect, new spot: `schedules` carries ERA franchise codes (OAK/SD/STL)
    # while pbp + our canonicalized roster carry CURRENT codes — canonicalize ONCE here so every
    # frame joins on one code space (the first smoke silently lost era-team kicker-weeks to the
    # bye filter and PIT-dropped 3,521 attempt rows through exactly this).
    sched = KW.canonicalize_team_codes(sched, ("home_team", "away_team"))
    home = sched.rename(columns={"home_team": "team", "away_team": "opponent",
                                 "home_score": "points_for", "away_score": "points_against"})
    away = sched.rename(columns={"away_team": "team", "home_team": "opponent",
                                 "away_score": "points_for", "home_score": "points_against"})
    home, away = home.assign(is_home=1), away.assign(is_home=0)
    cols = ["season", "week", "team", "opponent", "is_home", "gameday", "div_game", "roof",
            "points_for", "points_against"]
    tw = pd.concat([home[cols], away[cols]], ignore_index=True)
    for c in ("season", "week"):
        tw[c] = tw[c].astype("int64")
    tw["gameday"] = pd.to_datetime(tw["gameday"])
    #: the STRUCTURAL stadium attribute — the stadium has a roof; never the realized game-day
    #: open/closed state of a retractable roof (that is realized information).
    tw["roofed_stadium"] = tw["roof"].astype(str).str.lower().isin(
        ("dome", "closed", "open")).astype(float)
    return tw.drop(columns=["roof"])


def _prior_season_agg(df: pd.DataFrame, key: str, cols: list[str]) -> pd.DataFrame:
    agg = df.groupby([key, "season"], as_index=False).agg(
        **{f"_{c}": (c, "mean") for c in cols}, _g=(cols[0], "size"))
    agg["season"] = agg["season"] + 1
    return agg


def _bye_filter(df: pd.DataFrame, sides: pd.DataFrame) -> pd.DataFrame:
    """Drop rows whose team has no scheduled game that week (a bye is a deterministic zero,
    excluded from scoring as in NF-W1)."""
    keys = sides[["season", "week", "team"]].drop_duplicates()
    return df.merge(keys, on=["season", "week", "team"], how="inner")


# ── DST frame ───────────────────────────────────────────────────────────────────────────────────
def build_dst_frame(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sides = _sides(raw["sched"])
    tw = KW.canonicalize_team_codes(raw["team_week"], ("team", "opponent_team"))
    sides = KW.canonicalize_team_codes(sides, ("team", "opponent"))
    for c in ("season", "week"):
        tw[c] = tw[c].astype("int64")
    played = sides[sides["points_for"].notna()]
    df = tw.merge(played, on=["season", "week", "team"], how="inner")
    KW.assert_no_nan_join_keys(df, ["team", "opponent"], "dst_frame")

    df["pa"] = pd.to_numeric(df["points_against"], errors="coerce")
    # NET yards allowed = the OPPONENT's net offense (the NF-C0e gross-vs-net lesson)
    opp_off = tw[["season", "week", "team", "off_net_yards"]].rename(
        columns={"team": "opponent", "off_net_yards": "ya"})
    df = df.merge(opp_off, on=["season", "week", "opponent"], how="left")

    df["pa_bucket"] = KW.bucket_index(df["pa"], KW.PA_EDGES).astype(float)
    df["ya_bucket"] = KW.bucket_index(df["ya"], KW.YA_EDGES).astype(float)
    df["dst_points"] = (
        sum(w * df[leg] for leg, w in KW.DST_LINEAR_POINTS.items())
        + np.asarray(KW.PA_TIER_POINTS, float)[df["pa_bucket"].astype(int)])

    gw = WP._global_week_index(raw["sched"])
    df = df.merge(gw, on=["season", "week"], how="left").sort_values(["team", "gw"]).reset_index(drop=True)

    own = [("def_sacks", "sacks_l4", 4), ("def_sacks", "sacks_l8", 8),
           ("def_qb_hits", "qb_hits_l4", 4), ("def_tfl", "tfl_l4", 4),
           ("def_int", "int_l4", 4), ("def_int", "int_l8", 8),
           ("def_fumble_rec", "fr_l4", 4), ("dst_td", "dsttd_l16", 16),
           ("def_safety", "safety_l16", 16), ("def_blocked_kick", "block_l16", 16),
           ("pa", "pa_l4", 4), ("pa", "pa_l8", 8), ("ya", "ya_l4", 4), ("ya", "ya_l8", 8)]
    for src, name, win in own:
        df[f"team_environment__{name}"] = KW.lagged_mean(df, "team", src, win)
    df["team_environment__sacks_ewm"] = KW.lagged_ewm(df, "team", "def_sacks")
    df["_takeaways"] = df["def_int"] + df["def_fumble_rec"]
    df["team_environment__takeaways_l8"] = KW.lagged_mean(df, "team", "_takeaways", 8)

    for src, name in (("def_sacks", "sacks"), ("def_int", "int"), ("def_fumble_rec", "fr"),
                      ("dst_td", "dsttd"), ("def_safety", "safety"),
                      ("def_blocked_kick", "block"), ("pa", "pa")):
        df[f"team_environment__{name}_s2d"] = KW.s2d_mean(df, ["team", "season"], src)
    prior_cols = ["def_sacks", "def_int", "def_fumble_rec", "dst_td", "def_safety",
                  "def_blocked_kick", "pa"]
    pri = _prior_season_agg(df, "team", prior_cols)
    ren = {"_def_sacks": "team_environment__sacks_prior_season",
           "_def_int": "team_environment__int_prior_season",
           "_def_fumble_rec": "team_environment__fr_prior_season",
           "_dst_td": "team_environment__dsttd_prior_season",
           "_def_safety": "team_environment__safety_prior_season",
           "_def_blocked_kick": "team_environment__block_prior_season",
           "_pa": "team_environment__pa_prior_season",
           "_g": "team_environment__games_prior_season"}
    df = df.merge(pri.rename(columns=ren), on=["team", "season"], how="left")

    # the OFFENSE faced: the opponent's own lagged offensive series
    off = df[["season", "week", "gw", "team", "points_for", "sacks_taken", "giveaways",
              "off_net_yards", "off_pass_yards"]].sort_values(["team", "gw"]).copy()
    for src, name, win in (("points_for", "opp_points_l4", 4), ("points_for", "opp_points_l8", 8),
                           ("sacks_taken", "opp_sacks_taken_l4", 4),
                           ("sacks_taken", "opp_sacks_taken_l8", 8),
                           ("giveaways", "opp_giveaways_l4", 4),
                           ("giveaways", "opp_giveaways_l8", 8),
                           ("off_net_yards", "opp_off_yards_l4", 4),
                           ("off_pass_yards", "opp_pass_yards_l4", 4)):
        off[f"opponent_matchup__{name}"] = KW.lagged_mean(off, "team", src, win)
    opp_pri = _prior_season_agg(off, "team", ["points_for"]).rename(
        columns={"_points_for": "opponent_matchup__opp_points_prior_season", "_g": "_opp_g"})
    off = off.merge(opp_pri.drop(columns=["_opp_g"]), on=["team", "season"], how="left")
    opp_block = off[["season", "week", "team"]
                    + [c for c in off.columns if c.startswith("opponent_matchup__")]].rename(
        columns={"team": "opponent"})
    df = df.merge(opp_block, on=["season", "week", "opponent"], how="left")

    df["game_context__is_home"] = pd.to_numeric(df["is_home"], errors="coerce")
    df["game_context__div_game"] = pd.to_numeric(df["div_game"], errors="coerce")
    df["game_context__week_index"] = df["week"].astype(float)
    ds = df.sort_values(["team", "gw"]).groupby("team")["gameday"].diff().dt.days
    df["game_context__days_since_last_game"] = pd.to_numeric(ds, errors="coerce")

    df = KW.attach_week_meta(df.drop(columns=["gw"]), raw["sched"])
    df["_target_gameday"] = df["gameday"]
    return df.reset_index(drop=True)


# ── Kicker + team-environment frames ────────────────────────────────────────────────────────────
def _team_env_block(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Lagged team offense environment + the defense-faced block, at (season, week, team)."""
    sides = _sides(raw["sched"])
    box = KW.canonicalize_team_codes(raw["team_box"], ("team",))
    for c in ("season", "week"):
        box[c] = box[c].astype("int64")
    gw = WP._global_week_index(raw["sched"])
    box = box.merge(gw, on=["season", "week"], how="left")
    box = box.merge(sides[["season", "week", "team", "opponent"]], on=["season", "week", "team"],
                    how="left")
    KW.assert_no_nan_join_keys(box.dropna(subset=["opponent"]), ["team"], "team_env_block")
    box["rz_tdrate"] = (pd.to_numeric(box["rz_td_drives"], errors="coerce")
                        / pd.to_numeric(box["rz_trips"], errors="coerce").replace(0, np.nan))
    box = box.sort_values(["team", "gw"]).reset_index(drop=True)
    for src, name, win in (("points", "points_l4", 4), ("points", "points_l8", 8),
                           ("drives", "drives_l4", 4), ("rz_trips", "rz_trips_l4", 4),
                           ("rz_tdrate", "rz_tdrate_l4", 4),
                           ("fgrange_trips", "fgrange_trips_l4", 4),
                           ("team_fg_att", "team_fg_att_l4", 4),
                           ("epa_per_play", "epa_per_play_l4", 4)):
        box[f"team_environment__{name}"] = KW.lagged_mean(box, "team", src, win)
    pri = _prior_season_agg(box, "team", ["points"]).rename(
        columns={"_points": "team_environment__points_prior_season",
                 "_g": "team_environment__games_prior_season"})
    box = box.merge(pri, on=["team", "season"], how="left")

    # what the DEFENSE this offense faces has allowed (lagged, keyed by the defending team)
    faced = box[["season", "week", "gw", "opponent", "points", "rz_tdrate", "team_fg_att",
                 "epa_per_play", "drives"]].rename(columns={"opponent": "def_team"})
    faced = faced.dropna(subset=["def_team"]).sort_values(["def_team", "gw"])
    for src, name in (("points", "def_points_allowed_l4"),
                      ("rz_tdrate", "def_rz_tdrate_allowed_l4"),
                      ("team_fg_att", "def_fgatt_faced_l4"),
                      ("epa_per_play", "def_epa_allowed_l4"),
                      ("drives", "def_drives_faced_l4")):
        faced[f"opponent_matchup__{name}"] = KW.lagged_mean(faced, "def_team", src, 4)
    box = box.merge(
        faced[["season", "week", "def_team"]
              + [c for c in faced.columns if c.startswith("opponent_matchup__")]]
        .rename(columns={"def_team": "opponent"}),
        on=["season", "week", "opponent"], how="left")
    keep = (["season", "week", "team"]
            + [c for c in box.columns if c.startswith(("team_environment__", "opponent_matchup__"))])
    return box[keep]


def _kicker_priors(df: pd.DataFrame) -> pd.DataFrame:
    """Career-to-date kicker EB rates with an EXPANDING league prior (both strictly prior)."""
    df = df.sort_values(["gw", "player_id"]).reset_index(drop=True)
    df["_made_all"] = df["fg_made_0_39"] + df["fg_made_40_49"] + df["fg_made_50p"]
    per_gw = df.groupby("gw")[["fg_att", "_made_all", "fg_made_40_49", "fg_made_50p"]].sum()
    cum = per_gw.cumsum().shift(1)
    league = pd.DataFrame({
        "_lg_make": (cum["_made_all"] / cum["fg_att"].replace(0, np.nan)),
        "_lg_s50": (cum["fg_made_50p"] / cum["_made_all"].replace(0, np.nan)),
        "_lg_s40": (cum["fg_made_40_49"] / cum["_made_all"].replace(0, np.nan)),
    }).rename_axis("gw").reset_index()
    df = df.merge(league, on="gw", how="left")
    for c, default in (("_lg_make", 0.84), ("_lg_s50", 0.10), ("_lg_s40", 0.25)):
        df[c] = df[c].fillna(default)
    df = df.sort_values(["player_id", "gw"]).reset_index(drop=True)
    att = KW.prior_cum(df, "player_id", "fg_att")
    made = KW.prior_cum(df, "player_id", "_made_all")
    m50 = KW.prior_cum(df, "player_id", "fg_made_50p")
    m40 = KW.prior_cum(df, "player_id", "fg_made_40_49")
    df["prior_week_box__kicker_prior_att"] = att
    df["prior_week_box__kicker_prior_makerate_eb"] = (
        (made + KW.EB_KAPPA_ATT * df["_lg_make"]) / (att + KW.EB_KAPPA_ATT))
    df["prior_week_box__kicker_prior_share50_eb"] = (
        (m50 + KW.EB_KAPPA_BAND * df["_lg_s50"]) / (made + KW.EB_KAPPA_BAND))
    df["prior_week_box__kicker_prior_share40_eb"] = (
        (m40 + KW.EB_KAPPA_BAND * df["_lg_s40"]) / (made + KW.EB_KAPPA_BAND))
    df["prior_week_box__fg_makerate_prior"] = df["prior_week_box__kicker_prior_makerate_eb"]
    df["prior_week_box__share50_prior"] = df["prior_week_box__kicker_prior_share50_eb"]
    return df.drop(columns=["_lg_make", "_lg_s50", "_lg_s40"])


def build_kicker_frame(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sides = _sides(raw["sched"])
    roster = KW.canonicalize_team_codes(raw["roster"], ("team",))
    stats = KW.canonicalize_team_codes(raw["kicker_week"], ("team",))
    for f in (roster, stats):
        for c in ("season", "week"):
            f[c] = f[c].astype("int64")
    roster = roster.drop_duplicates(subset=["season", "week", "player_id"])
    roster = _bye_filter(roster, sides[sides["points_for"].notna()])

    stat_cols = ["fg_att", "xp_att", "pat_made", "fg_made_0_39", "fg_made_40_49", "fg_made_50p"]
    df = roster.merge(stats[["season", "week", "player_id"] + stat_cols],
                      on=["season", "week", "player_id"], how="left")
    # ⚠️ NOT a feature fillna: an ACT-rostered kicker on a team that PLAYED, with no kicking stat
    # row, attempted zero kicks — a measured realized outcome (the NF-W1 retained-zeros
    # convention). Features stay NaN-honest; only realized event LABELS are zero-completed.
    df[stat_cols] = df[stat_cols].fillna(0.0)
    df["k_points"] = (KW.BAND_POINTS[0] * df["fg_made_0_39"]
                      + KW.BAND_POINTS[1] * df["fg_made_40_49"]
                      + KW.BAND_POINTS[2] * df["fg_made_50p"] + df["pat_made"])

    gw = WP._global_week_index(raw["sched"])
    df = df.merge(gw, on=["season", "week"], how="left")
    df = df.sort_values(["player_id", "gw"]).reset_index(drop=True)
    for src, name, win in (("fg_att", "fg_att_l4", 4), ("fg_att", "fg_att_l8", 8),
                           ("xp_att", "pat_att_l4", 4), ("xp_att", "pat_att_l8", 8)):
        df[f"prior_week_box__{name}"] = KW.lagged_mean(df, "player_id", src, win)
    df["prior_week_box__fg_att_ewm"] = KW.lagged_ewm(df, "player_id", "fg_att")
    df["prior_week_box__fg_att_s2d"] = KW.s2d_mean(df, ["player_id", "season"], "fg_att")
    df["prior_week_box__pat_att_s2d"] = KW.s2d_mean(df, ["player_id", "season"], "xp_att")
    pri = _prior_season_agg(df, "player_id", ["fg_att", "xp_att"]).rename(
        columns={"_fg_att": "prior_week_box__fg_att_prior_season",
                 "_xp_att": "prior_week_box__pat_att_prior_season",
                 "_g": "prior_week_box__kicker_games_prior_season"})
    df = df.merge(pri, on=["player_id", "season"], how="left")
    df = _kicker_priors(df)

    env = _team_env_block(raw)
    df = df.merge(env, on=["season", "week", "team"], how="left")
    game = sides[["season", "week", "team", "opponent", "is_home", "gameday", "div_game",
                  "roofed_stadium"]]
    df = df.merge(game, on=["season", "week", "team"], how="left")
    KW.assert_no_nan_join_keys(df, ["team", "gameday"], "kicker_frame")

    df["game_context__is_home"] = pd.to_numeric(df["is_home"], errors="coerce")
    df["game_context__div_game"] = pd.to_numeric(df["div_game"], errors="coerce")
    df["game_context__week_index"] = df["week"].astype(float)
    df["game_context__roofed_stadium"] = pd.to_numeric(df["roofed_stadium"], errors="coerce")
    ds = df.sort_values(["player_id", "gw"]).groupby("player_id")["gameday"].diff().dt.days
    df["game_context__days_since_last_game"] = pd.to_numeric(ds, errors="coerce")

    df = KW.attach_week_meta(df.drop(columns=["gw"]), raw["sched"])
    df["_target_gameday"] = df["gameday"]
    return df.reset_index(drop=True)


def build_attempt_frame(raw: dict[str, pd.DataFrame], kicker: pd.DataFrame) -> pd.DataFrame:
    """FG attempts with exact kick distance; kicker priors joined from the WEEK-grain frame (the
    same strictly-prior semantics assembly uses, so train and assembly read one definition)."""
    sides = _sides(raw["sched"])
    att = KW.canonicalize_team_codes(raw["attempts"], ("team",))
    for c in ("season", "week"):
        att[c] = att[c].astype("int64")
    att["band"] = KW.band_index(att["kick_distance"]).astype(float)
    att["game_context__kick_distance"] = pd.to_numeric(att["kick_distance"], errors="coerce")
    pri_cols = ["prior_week_box__kicker_prior_att", "prior_week_box__kicker_prior_makerate_eb",
                "prior_week_box__kicker_prior_share50_eb",
                "prior_week_box__kicker_prior_share40_eb"]
    pri = kicker[["season", "week", "player_id"] + pri_cols].rename(
        columns={"player_id": "kicker_player_id"})
    df = att.merge(pri, on=["season", "week", "kicker_player_id"], how="left")
    game = sides[["season", "week", "team", "gameday", "roofed_stadium"]]
    df = df.merge(game, on=["season", "week", "team"], how="left")
    KW.assert_no_nan_join_keys(df, ["gameday"], "attempt_frame")
    df["game_context__roofed_stadium"] = pd.to_numeric(df["roofed_stadium"], errors="coerce")
    df = KW.attach_week_meta(df, raw["sched"])
    df["_target_gameday"] = df["gameday"]
    return df.reset_index(drop=True)


# ── Assembly-boundary: engineer → provenance → PIT gate → cache ─────────────────────────────────
def build_frames(seasons: tuple[int, int], *, rebuild_cache: bool = False):
    """⭐ The PIT gate runs on EVERY build, cache hit or not (the NF-C0e wired-≠-invoked shape)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    specs = {
        "dst": (KW.FEATURES_D, "team", "nflverse_lake_dst_team_week"),
        "kicker": (KW.FEATURES_K, "player_id", "nflverse_lake_kicker_week"),
        "attempt": (KW.FEATURES_MAKE, "play_id", "nflverse_lake_fg_attempt"),
    }
    paths = {n: _ARTIFACTS / f"nf_w7_{n}_{KW.matrix_key(n, seasons, feats)}.parquet"
             for n, (feats, _, _) in specs.items()}
    if all(p.exists() for p in paths.values()) and not rebuild_cache:
        frames = {n: pd.read_parquet(p) for n, p in paths.items()}
        log.info("frame caches HIT — re-running the PIT gate over all three")
    else:
        raw = _load(seasons)
        frames = {"dst": build_dst_frame(raw)}
        frames["kicker"] = build_kicker_frame(raw)
        frames["attempt"] = build_attempt_frame(raw, frames["kicker"])
        for n, p in paths.items():
            frames[n].to_parquet(p, index=False)
    KW.assert_feature_provenance_w7(KW.FEATURES_K)
    KW.assert_feature_provenance_w7(KW.FEATURES_D)
    KW.assert_feature_provenance_w7(KW.FEATURES_MAKE)
    KW.assert_feature_provenance_w7(KW.FEATURES_BAND)
    audits = {}
    for n, (feats, subject, source) in specs.items():
        audit = KW.run_pit_gate(frames[n], subject, source)
        frames[n] = frames[n].loc[audit.pop("kept_index")].reset_index(drop=True)
        audits[n] = audit
        log.info("frame %s: %d rows (PIT %d weeks / %d records, %d rows dropped)",
                 n, len(frames[n]), audit["weeks_checked"], audit["records_checked"],
                 audit["rows_dropped"])
    return frames, audits


# ── Generic Layer-A leg engines ─────────────────────────────────────────────────────────────────
def _frame_of(leg: str) -> str:
    if leg in ("fg_att", "xp_att"):
        return "kicker"
    if leg in KW.ATTEMPT_LEGS:
        return "attempt"
    return "dst"


def _fit_bank(leg: str, arm: str, train, test, *, y_train=None):
    feats = KW.LEG_FEATURES[leg]
    if leg in (*KW.COUNT_LEGS, *KW.RARE_LEGS):
        return KW.COUNT_FITTERS[arm](train, test, feats, leg, y_train=y_train)
    if leg == "fg_make":
        return KW.MAKE_FITTERS[arm](train, test, feats, "made", y_train=y_train)
    if leg == "fg_band":
        return KW.BAND_FITTERS[arm](train, test, feats, "band", y_train=y_train)
    return KW.BUCKET_FITTERS[arm](train, test, feats, leg, y_train=y_train)


def _score(leg: str, pred, test) -> np.ndarray:
    metric = KW.LEG_METRIC[leg]
    if metric == "crps_q199":
        return KW.crps_dense(pred, test[leg].to_numpy(float))
    if metric == "log_loss":
        return KW.log_loss_binary(pred, test["made"].to_numpy(float))
    if metric == "log_loss_multiclass":
        return KW.log_loss_multiclass(pred, test["band"].to_numpy())
    return KW.rps(pred, test[leg].to_numpy())


def _label_col(leg: str) -> str:
    return {"fg_make": "made", "fg_band": "band"}.get(leg, leg)


def _permute_y(leg: str, train: pd.DataFrame) -> np.ndarray:
    """The permutation control's labels: shuffled within global week (within distance BIN for the
    make leg, so the distance marginal is preserved exactly)."""
    if leg == "fg_make":
        d = pd.to_numeric(train["game_context__kick_distance"], errors="coerce").to_numpy(float)
        groups = np.digitize(d, KW._MAKE_BINS)
    else:
        groups = train["gw"].to_numpy()
    # the label the PERMUTED FAMILY fits on: the bucket INDEX for the bucket legs (their permuted
    # family is mnlogit, a classifier), the leg label everywhere else
    return KW.permute_within_group(train[_label_col(leg)].to_numpy(), groups)


def _anchor_preds(leg: str, train, test, qshape) -> dict[str, np.ndarray]:
    metric = KW.LEG_METRIC[leg]
    if metric == "crps_q199":
        y = train[leg].to_numpy(float)
        y = y[np.isfinite(y)]
        clim = KW.marginal_bank(y, len(test))
        med = np.quantile(y, 0.5)
        return {
            "nihilist_zero": np.zeros((len(test), len(KW.EVAL_LEVELS))),
            "zero_width": np.full((len(test), len(KW.EVAL_LEVELS)), med),
            "max_width": med + 3.0 * (clim - med),
        }
    ycol = _label_col(leg)
    if metric == "log_loss":
        return {"all_event": np.full(len(test), 0.999), "uniform": np.full(len(test), 0.5)}
    n_classes = 3 if leg == "fg_band" else 9
    y = train[ycol].to_numpy()
    modal = int(pd.Series(y).mode().iloc[0])
    return {"point_mass_modal": KW.anchor_point_mass((len(test), n_classes), modal),
            "uniform": KW.anchor_uniform((len(test), n_classes))}


def run_leg_fold(leg: str, fold: WP.Fold, frame: pd.DataFrame) -> dict:
    train, test = frame.loc[fold.train_idx], frame.loc[fold.test_idx]
    t0 = time.time()
    preds: dict[str, np.ndarray] = {}
    for label in (*KW.REAL_ARMS[leg], *KW.FOILS[leg]):
        preds[label] = _fit_bank(leg, label, train, test)
        preds[KW.oracle_of(label)] = _fit_bank(leg, label, test, test)
    for arm in KW.REAL_ARMS[leg]:
        preds[KW.matched_n_of(arm)] = _fit_bank(leg, arm, KW.matched_n_train(train, test), test)
    preds["permuted_control"] = _fit_bank(leg, KW.PERMUTED_FAMILY[leg], train, test,
                                          y_train=_permute_y(leg, train))
    preds.update(_anchor_preds(leg, train, test, None))
    scores = {}
    for label, pred in preds.items():
        KW.assert_finite_predictive(pred, f"{leg}/{label}")
        scores[label] = float(np.mean(_score(leg, pred, test)))
    extra = {}
    if KW.LEG_METRIC[leg] == "crps_q199":
        winner_now = min(KW.REAL_ARMS[leg], key=lambda a: scores[a])
        extra["pit_flatness_best_arm"] = KW.pit_flatness(
            KW.randomized_pit_from_bank(preds[winner_now], test[leg].to_numpy(float)))
    log.info("[A/%s] fold %s in %.1fs (train %d / test %d)",
             leg, fold.label, time.time() - t0, len(train), len(test))
    return {"label": fold.label, "scores": scores, "n_train": int(len(train)),
            "n_test": int(len(test)), **extra}


def select_leg(leg: str, fold_results: list[dict], n_folds: int,
               fold_seasons: dict[str, int]) -> dict:
    mat = pd.DataFrame({fr["label"]: fr["scores"] for fr in fold_results}).T
    mean_s = mat.mean(axis=0)
    arms = list(KW.REAL_ARMS[leg])
    winner = str(mean_s[arms].idxmin())
    best_foil = str(mean_s[list(KW.FOILS[leg])].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)
    eligible = KW.eligible_labels(leg)
    defl = NF18.deflate(mat[eligible], subset=eligible)
    trial_srs = []
    for arm in arms:
        d = (mat[best_foil] - mat[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)
    perm_lift = (mat[best_foil] - mat["permuted_control"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    degenerate_labels = ([a for a in ("nihilist_zero", "zero_width", "max_width")
                          if a in mat.columns]
                         + [a for a in ("all_event", "uniform", "point_mass_modal")
                            if a in mat.columns])
    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in degenerate_labels)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in degenerate_labels},
        "winner_beats_permuted": bool(mean_s["permuted_control"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "no_arm_beats_own_oracle": bool(all(
            mean_s[a] > mean_s[KW.oracle_of(a)] for a in arms)),
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_s[a] > mean_s[KW.oracle_of(a)])
            or (mean_s[KW.oracle_of(a)] < mean_s[KW.matched_n_of(a)])
            for a in arms)),
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[KW.oracle_of(f)] for f in KW.FOILS[leg])),
    }
    oracle_detail = {
        a: {"arm": round(float(mean_s[a]), 4),
            "own_form_oracle": round(float(mean_s[KW.oracle_of(a)]), 4),
            "matched_n": round(float(mean_s[KW.matched_n_of(a)]), 4)}
        for a in arms
    }
    era_deltas = {fr_label: round(float(d), 4) for fr_label, d in zip(mat.index, deltas)
                  if fold_seasons.get(fr_label) == KW.CAPTURE_ERA_SEASON}
    sd = float(np.nanstd(deltas, ddof=1))
    pit_reports = [fr.get("pit_flatness_best_arm") for fr in fold_results
                   if fr.get("pit_flatness_best_arm")]
    return {
        "leg": leg, "metric": KW.LEG_METRIC[leg], "winner": winner, "best_foil": best_foil,
        "mean_scores": {k: round(float(v), 4) for k, v in mean_s.items()},
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "mean_delta": None if mean_d is None else round(mean_d, 4),
        "ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval, "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": round(float(np.nanmean(deltas)) / sd, 3) if sd > 1e-12 else None,
        "var_trials_sr": (round(float(np.var(np.asarray(trial_srs), ddof=1)), 5)
                          if len(trial_srs) > 1 else None),
        "anchors": anchors, "oracle_detail": oracle_detail,
        "permutation_detail": {"permuted_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 4),
                               "permuted_lift_p_one_sided": p_perm},
        "capture_era_deltas_report_only": era_deltas,
        "pit_flatness_report_only": pit_reports,
    }


# ── Layer B: assembly + the gate ────────────────────────────────────────────────────────────────
def _band_rep_distances(att_train: pd.DataFrame) -> np.ndarray:
    d = pd.to_numeric(att_train["game_context__kick_distance"], errors="coerce").to_numpy(float)
    b = KW.band_index(d)
    return np.array([float(np.nanmean(d[b == i])) if (b == i).any() else m
                     for i, m in enumerate((30.0, 44.0, 53.0))])


def _assembled_k(winners: dict[str, str], k_train, k_test, att_train) -> np.ndarray:
    att_bank = _fit_bank("fg_att", winners["fg_att"], k_train, k_test)
    xp_bank = _fit_bank("xp_att", winners["xp_att"], k_train, k_test)
    p_band = KW.BAND_FITTERS[winners["fg_band"]](att_train, k_test, KW.FEATURES_BAND, "band")
    reps = _band_rep_distances(att_train)
    p_make = np.column_stack([
        KW.MAKE_FITTERS[winners["fg_make"]](
            att_train, k_test.assign(game_context__kick_distance=reps[b]),
            KW.FEATURES_MAKE, "made")
        for b in range(len(KW.BANDS))])
    xp_att = k_train["xp_att"].to_numpy(float)
    xp_made = k_train["pat_made"].to_numpy(float)
    xp_rate = float(np.nansum(xp_made) / max(np.nansum(xp_att), 1.0))
    return KW.assemble_k_bank(att_bank, xp_bank, p_band, p_make, xp_rate)


def _assembled_dst(winners: dict[str, str], d_train, d_test) -> np.ndarray:
    count_banks = {leg: _fit_bank(leg, winners[leg], d_train, d_test)
                   for leg in KW.DST_LINEAR_POINTS}
    pa_proba = _fit_bank("pa_bucket", winners["pa_bucket"], d_train, d_test)
    return KW.assemble_dst_bank(count_banks, pa_proba)


def run_layer_b_fold(target: str, fold_by_frame: dict[str, WP.Fold],
                     frames: dict[str, pd.DataFrame], winners: dict[str, str]) -> dict:
    t0 = time.time()
    if target == "k_points":
        frame, feats, entity = frames["kicker"], KW.FEATURES_K, "player_id"
        fold = fold_by_frame["kicker"]
        att_fold = fold_by_frame["attempt"]
        att_train = frames["attempt"].loc[att_fold.train_idx]
        att_test = frames["attempt"].loc[att_fold.test_idx]
    else:
        frame, feats, entity = frames["dst"], KW.FEATURES_D, "team"
        fold = fold_by_frame["dst"]
        att_train = att_test = None
    train, test = frame.loc[fold.train_idx], frame.loc[fold.test_idx]
    y_te = test[target].to_numpy(float)

    def assemble(tr, te, att_tr):
        return (_assembled_k(winners, tr, te, att_tr) if target == "k_points"
                else _assembled_dst(winners, tr, te))

    banks: dict[str, np.ndarray] = {
        "assembled": assemble(train, test, att_train),
        "foil_climatology": KW.foil_climatology_bank(train, test, target),
        "foil_board_eb": KW.foil_board_eb_points(train, test, target, entity),
        "foil_direct": KW.fit_direct_points(train, test, feats, target),
        # anchors
        "nihilist_zero": np.zeros((len(test), len(KW.EVAL_LEVELS))),
        "permuted_direct": KW.fit_direct_points(
            train, test, feats, target,
            y_train=KW.permute_within_group(train[target].to_numpy(float),
                                            train["gw"].to_numpy())),
        "oracle__assembled": assemble(test, test, att_test),
        "matched_n__assembled": assemble(KW.matched_n_train(train, test), test, att_train),
        "oracle__foil_climatology": KW.foil_climatology_bank(test, test, target),
        "oracle__foil_board_eb": KW.foil_board_eb_points(test, test, target, entity),
        "oracle__foil_direct": KW.fit_direct_points(test, test, feats, target),
    }
    y_tr = train[target].to_numpy(float)
    y_tr = y_tr[np.isfinite(y_tr)]
    med = float(np.quantile(y_tr, 0.5))
    clim = banks["foil_climatology"]
    banks["zero_width"] = np.full_like(clim, med)
    banks["max_width"] = med + 3.0 * (clim - med)

    scores, coverage = {}, {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{target}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    coverage["assembled"] = KW.coverage80_dense(banks["assembled"], y_te)
    pit = KW.pit_flatness(KW.randomized_pit_from_bank(banks["assembled"], y_te))
    log.info("[B/%s] fold %s in %.1fs (train %d / test %d)",
             target, fold.label, time.time() - t0, len(train), len(test))
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "pit_flatness": pit, "n_train": int(len(train)), "n_test": int(len(test))}


def select_layer_b(target: str, fold_results: list[dict], n_folds: int,
                   fold_seasons: dict[str, int]) -> dict:
    mat = pd.DataFrame({fr["label"]: fr["scores"] for fr in fold_results}).T
    mean_s = mat.mean(axis=0)
    winner = "assembled"
    best_foil = str(mean_s[list(KW.LAYER_B_FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)
    eligible = list(KW.LAYER_B_ELIGIBLE)
    defl = NF18.deflate(mat[eligible], subset=eligible)
    d = deltas
    sd = float(np.nanstd(d, ddof=1))
    trial_srs = [float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0]
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)
    perm_lift = (mat[best_foil] - mat["permuted_direct"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    anchors = {
        "degenerates_lose": bool(all(mean_s[a] > mean_s[winner]
                                     for a in ("nihilist_zero", "zero_width", "max_width"))),
        "degenerate_detail": {a: round(float(mean_s[a]), 4)
                              for a in ("nihilist_zero", "zero_width", "max_width")},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "no_arm_beats_own_oracle": bool(mean_s[winner] > mean_s["oracle__assembled"]),
        "oracle_floors_respected_at_matched_n": bool(
            (mean_s[winner] > mean_s["oracle__assembled"])
            or (mean_s["oracle__assembled"] < mean_s["matched_n__assembled"])),
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[KW.oracle_of(f)] for f in KW.LAYER_B_FOILS)),
    }
    covs = [fr["coverage"]["assembled"] for fr in fold_results]
    n_tot = sum(c["n"] for c in covs)
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = float(np.sqrt(KW.COVERAGE_FLOOR * (1 - KW.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")
    era_deltas = {lbl: round(float(dd), 4) for lbl, dd in zip(mat.index, deltas)
                  if fold_seasons.get(lbl) == KW.CAPTURE_ERA_SEASON}
    return {
        "target": target, "winner": winner, "best_foil": best_foil,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_s.items()},
        "deltas_by_fold": [round(float(dd), 4) for dd in deltas],
        "mean_delta": None if mean_d is None else round(mean_d, 4),
        "ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval,
        "observed_sr": round(float(np.nanmean(deltas)) / sd, 3) if sd > 1e-12 else None,
        "var_trials_sr": None,
        "anchors": anchors,
        "permutation_detail": {"permuted_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 4),
                               "permuted_lift_p_one_sided": p_perm},
        "coverage": {"winner_coverage_80": round(cov, 4), "n_rows": int(n_tot),
                     "binomial_se": round(se, 4),
                     "blocking_shortfall": bool(n_tot and (KW.COVERAGE_FLOOR - cov)
                                                > KW.COVERAGE_BLOCK_SE * se)},
        "pit_flatness_report_only": [fr["pit_flatness"] for fr in fold_results],
        "capture_era_deltas_report_only": era_deltas,
    }


# ── Multiplicity (two declared families; the stricter binds — the W3 mechanism) ─────────────────
def fdr_two_families(component_p: dict[str, float | None],
                     downstream_p: dict[str, float | None]) -> dict:
    own = {**M14.bh_fdr(component_p, q=KW.FDR_Q), **M14.bh_fdr(downstream_p, q=KW.FDR_Q)}
    pooled_in = {f"component::{k}": v for k, v in component_p.items()}
    pooled_in.update({f"downstream::{k}": v for k, v in downstream_p.items()})
    pooled_raw = M14.bh_fdr(pooled_in, q=KW.FDR_Q)
    pooled = {k.split("::", 1)[1]: v for k, v in pooled_raw.items()}
    binding = {k: bool(own.get(k) and pooled.get(k)) for k in own}
    return {"own_family": own, "pooled": pooled, "binding": binding}


def _classify_leg(leg: str, sel: dict, n_folds: int, checks: dict) -> dict:
    hand = KW.hand_classify_refusal(checks)
    if hand is not None:
        return hand
    v = cv_power.classify_null(
        metric=f"nf_w7_{leg}", n_folds=n_folds, n_arms=len(KW.REAL_ARMS[leg]),
        beats_foil=sel["beats_foil"], observed_sr=sel["observed_sr"],
        var_trials_sr=sel["var_trials_sr"], fold_wins=sel["fold_wins"],
        p_one_sided=sel["p_one_sided"], bh_cutoff=KW.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    return KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger},
        len(KW.REAL_ARMS[leg]))


def _classify_layer_b(target: str, sel: dict, n_folds: int, checks: dict) -> dict:
    v = cv_power.classify_null(
        metric=f"nf_w7_downstream_{target}", n_folds=n_folds,
        n_arms=len(KW.LAYER_B_REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=KW.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    out = KW.classify_layer_b(
        sel, n_folds=n_folds,
        instrument_verdict={"state": v.state, "reason": v.reason,
                            "retest_trigger": v.retest_trigger})
    # ⚠️ unlike NF-W3's Layer B, THIS eligible field has 4 configs (arm + 3 foils), so PBO IS
    # computed and gated; only the DSR trial field is the single pre-registered arm (sr0=0).
    out["pbo_state"] = (
        "EVALUABLE — PBO is computed over the 4-config eligible field (assembled + 3 foils); "
        "the DSR trial field is the single pre-registered arm (sr0=0, a plain PSR), declared in "
        "the pre-registration §7.")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored selections — no refit (the NF-W2e/W3
    derive-not-store rule; correcting a classifier defect must cost seconds, not a re-run)."""
    n_folds = out["n_folds"]
    component_p = {leg: out["layer_a"][leg]["p_one_sided"] for leg in out["legs"]}
    downstream_p = {t: out["layer_b"][t]["p_one_sided"] for t in out.get("layer_b", {})}
    fdr = fdr_two_families(component_p, downstream_p)
    gates_a = {leg: KW.compose_gate(out["layer_a"][leg], fdr["binding"].get(leg, False))
               for leg in out["legs"]}
    gates_b = {t: KW.compose_gate(out["layer_b"][t], fdr["binding"].get(t, False), coverage=True)
               for t in out.get("layer_b", {})}
    null_states: dict[str, dict] = {}
    for leg in out["legs"]:
        if not gates_a[leg]["ship"]:
            null_states[f"layer_a::{leg}"] = _classify_leg(
                leg, out["layer_a"][leg], n_folds, gates_a[leg]["checks"])
    for t in out.get("layer_b", {}):
        if not gates_b[t]["ship"]:
            null_states[f"layer_b::{t}"] = _classify_layer_b(
                t, out["layer_b"][t], n_folds, gates_b[t]["checks"])
    verdict = {
        "layer_a": {leg: ("SHIP" if gates_a[leg]["ship"]
                          else null_states.get(f"layer_a::{leg}", {}).get("state", "NULL"))
                    for leg in out["legs"]},
        "layer_b": {t: ("SHIP" if gates_b[t]["ship"]
                        else null_states.get(f"layer_b::{t}", {}).get("state", "NULL"))
                    for t in out.get("layer_b", {})},
    }
    headline = ("A[" + " ".join(f"{k}:{v}" for k, v in verdict["layer_a"].items()) + "] "
                "B[" + " ".join(f"{k}:{v}" for k, v in verdict["layer_b"].items()) + "]")
    return {"fdr": fdr, "gates_a": gates_a, "gates_b": gates_b,
            "null_states": null_states, "verdict": verdict, "headline": headline}


# ── Report (every verdict word DERIVED at report time — NF-W2e) ─────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W7 — weekly Kicker + DST projections, exact tier scoring as bucket probabilities "
      "(§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**kicker-weeks:** {out['n_rows']['kicker']} · **team-weeks:** {out['n_rows']['dst']} · "
      f"**FG attempts:** {out['n_rows']['attempt']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (serving "
      "is the weekly path / NF-C6, an operator decision). Selection is `crps_q199` on the dense "
      "grid for banks, log-loss / RPS for the categorical legs; MAE never selects. Every "
      "direction word is three-way and derived at report time, failing closed to `TIES` "
      "(NF-W2e).")
    p("")
    for name, audit in out["pit_audits"].items():
        p(f"**PIT gate ({name}):** {audit['weeks_checked']} weeks / {audit['records_checked']} "
          f"records; {audit['rows_dropped']} rows dropped fail-closed.")
    p("")
    p("## ⭐ Headline")
    p("")
    lb = out["verdict"].get("layer_b") or {}
    p("- **Layer B (the gate — does the component chain beat the climatology null, the board-EB "
      "read and the direct-points foil?)** — "
      + (" · ".join(f"{t}: **{lb[t]}**" for t in lb) if lb else "**NOT RUN**"))
    p("- **Layer A (components)** — "
      + " · ".join(f"{leg}: **{out['verdict']['layer_a'][leg]}**" for leg in out["legs"]))
    p("")
    p("## ⭐ Layer B — the assembled fantasy-point distributions")
    p("")
    for t in lb:
        sel, gate = out["layer_b"][t], out["gates_b"][t]
        p(f"### `{t}` — **{out['verdict']['layer_b'][t]}**")
        p("")
        p(KW.verdict_sentence("assembled", sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps_q199": v} for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps_q199").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR(=PSR, 1 arm) {sel['dsr']} "
          f"· p {sel['p_one_sided']} · BH own-family {out['fdr']['own_family'].get(t)} / pooled "
          f"{out['fdr']['pooled'].get(t)} (binding {out['fdr']['binding'].get(t)})")
        p(f"- anchors: {sel['anchors']}")
        p(f"- permutation: {sel['permutation_detail']} · coverage(80) {sel['coverage']}")
        p(f"- randomized-PIT flatness by fold (report-only): {sel['pit_flatness_report_only']}")
        p(f"- capture-era (2025) fold deltas, report-only (NF-W2d): "
          f"{sel['capture_era_deltas_report_only']}")
        p(f"- gate: {gate['checks']}")
        ns = out["null_states"].get(f"layer_b::{t}", {})
        if ns:
            p(f"- null state: **{ns.get('state')}** — {ns.get('reason')} Re-test: "
              f"{ns.get('retest_trigger')}")
            if ns.get("hand_corrected"):
                p(f"- 🩹 hand-corrected from the instrument verdict {ns.get('instrument_verdict')}"
                  f" (the known classify_null n_arms=1 mis-render).")
        p("")
    p("## Layer A — the component legs")
    p("")
    for leg in out["legs"]:
        sel, gate = out["layer_a"][leg], out["gates_a"][leg]
        p(f"### `{leg}` ({sel['metric']}) — **{out['verdict']['layer_a'][leg]}**")
        p("")
        p(KW.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_score": v} for k, v in sel["mean_scores"].items()])
          .sort_values("mean_score").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} · "
          f"p {sel['p_one_sided']} · BH own/pooled/binding "
          f"{out['fdr']['own_family'].get(leg)}/{out['fdr']['pooled'].get(leg)}/"
          f"{out['fdr']['binding'].get(leg)}")
        p(f"- anchors: {sel['anchors']}")
        p(f"- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {sel['oracle_detail']}")
        p(f"- era deltas (2025, report-only): {sel['capture_era_deltas_report_only']}")
        p(f"- gate: {gate['checks']}")
        ns = out["null_states"].get(f"layer_a::{leg}", {})
        if ns:
            p(f"- null state: **{ns.get('state')}** — {ns.get('reason')}")
            if ns.get("field_shrink_flag"):
                f = ns["field_shrink_flag"]
                p(f"- ⚠️ field-shrink remedy is {f['status']} — {f['note']}")
        p("")
    p("## Null-state classification")
    p("")
    p("```json")
    p(json.dumps(out["null_states"], indent=2, default=str))
    p("```")
    p("")
    p("## Pre-registration echo")
    p("")
    p("```json")
    p(json.dumps(out["preregistration"], indent=2, default=str))
    p("```")
    path.write_text("\n".join(a))


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W7 weekly K+DST bake-off")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--skip-layer-b", action="store_true",
                    help="Layer A only (development aid — NOT a verdict)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive gates/verdicts from the stored JSON — no refit (NF-W2e)")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w7_kdst_weekly{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: {p_: (before.get(k, {}).get(p_), v) for p_, v in out["verdict"][k].items()
                     if before.get(k, {}).get(p_) != v} for k in out["verdict"]}
        moved = {k: v for k, v in moved.items() if v}
        if moved:
            out["verdict_corrected_from"] = before
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w7_kdst_weekly{suffix}.md")
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2))
        return 0

    t_start = time.time()
    frames, pit_audits = build_frames(KW.SEASONS, rebuild_cache=args.rebuild_cache)
    folds_by_frame = {n: WP.build_folds(f) for n, f in frames.items()}
    if args.smoke:
        folds_by_frame = {n: fl[-2:] for n, fl in folds_by_frame.items()}
    labels = [f.label for f in folds_by_frame["dst"]]
    for n, fl in folds_by_frame.items():
        assert [f.label for f in fl] == labels, (
            f"frame `{n}` produced a different fold axis — Layer A/B would not be a matched test")
    n_folds = len(labels)
    fold_seasons = {f.label: f.test_season for f in folds_by_frame["dst"]}

    layer_a, a_folds = {}, {}
    for leg in KW.ALL_LEGS:
        fname = _frame_of(leg)
        frs = [run_leg_fold(leg, f, frames[fname]) for f in folds_by_frame[fname]]
        a_folds[leg] = frs
        layer_a[leg] = select_leg(leg, frs, n_folds, fold_seasons)
    winners = {leg: layer_a[leg]["winner"] for leg in KW.ALL_LEGS}
    log.info("Layer-A winners → assembly forms: %s", winners)

    layer_b, b_folds = {}, {}
    if not args.skip_layer_b:
        for target in KW.LAYER_B_TARGETS:
            fold_sets = list(zip(*[folds_by_frame[n] for n in ("dst", "kicker", "attempt")]))
            frs = []
            for dst_f, k_f, att_f in fold_sets:
                fold_by_frame = {"dst": dst_f, "kicker": k_f, "attempt": att_f}
                frs.append(run_layer_b_fold(target, fold_by_frame, frames, winners))
            b_folds[target] = frs
            layer_b[target] = select_layer_b(target, frs, n_folds, fold_seasons)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": KW.STORY, "smoke": bool(args.smoke), "skip_layer_b": bool(args.skip_layer_b),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": KW.SELECTION_METRIC,
        "legs": list(KW.ALL_LEGS), "n_folds": n_folds, "fold_labels": labels,
        "n_rows": {n: int(len(f)) for n, f in frames.items()},
        "pit_audits": pit_audits, "winners": winners,
        "preregistration": {
            "real_arms": {k: list(v) for k, v in KW.REAL_ARMS.items()},
            "foils": {k: list(v) for k, v in KW.FOILS.items()},
            "leg_metrics": dict(KW.LEG_METRIC),
            "layer_b_eligible": list(KW.LAYER_B_ELIGIBLE),
            "layer_b_anchors": list(KW.LAYER_B_ANCHORS),
            "test_blocks": [list(t) for t in KW.TEST_BLOCKS], "purge_weeks": KW.PURGE_WEEKS,
            "pbo_max": KW.PBO_MAX, "dsr_min": KW.DSR_MIN, "fdr_q": KW.FDR_Q,
            "fdr_families": {k: list(v) for k, v in KW.FDR_FAMILIES.items()},
            "coverage_floor": KW.COVERAGE_FLOOR,
            "features_k": list(KW.FEATURES_K), "features_d": list(KW.FEATURES_D),
            "features_make": list(KW.FEATURES_MAKE), "features_band": list(KW.FEATURES_BAND),
            "assembly_draws": KW.ASSEMBLY_DRAWS, "eb_kappa_games": KW.EB_KAPPA_GAMES,
            "pa_edges": list(KW.PA_EDGES), "ya_edges": list(KW.YA_EDGES),
            "pa_tier_points": list(KW.PA_TIER_POINTS),
            "band_points": list(KW.BAND_POINTS),
            "era_forbidden_tokens": list(KW.ERA_FORBIDDEN_TOKENS),
            "banned_source_tokens": list(KW.BANNED_SOURCE_TOKENS),
        },
        "layer_a": layer_a, "layer_b": layer_b,
        "fold_results_a": {leg: [{k: fr[k] for k in ("label", "scores", "n_train", "n_test")}
                                 for fr in frs] for leg, frs in a_folds.items()},
        "fold_results_b": {t: [{"label": fr["label"], "scores": fr["scores"]} for fr in frs]
                           for t, frs in b_folds.items()},
    }
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w7_kdst_weekly{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
