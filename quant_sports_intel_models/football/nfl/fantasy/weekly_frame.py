"""weekly_frame.py — NF-W0: the leak-clean point-in-time weekly training + serving frame.

⭐ WHY THIS MODULE EXISTS AT ALL. NF-W1 wants to fit a weekly player model. The tempting frame is
`stats_player_week` — one row per player-week, already carrying `fantasy_points_ppr`. **That frame is
structurally wrong, and wrong in the one direction that flatters a model.** Measured on the live lake
(2024 week 1, skill positions): 983 players sat on a game-day roster and only 346 of them have a
`stats_player_week` row. Every one of the ~637 missing rows is a REAL ZERO — inactive, healthy
scratch, or dressed-and-played-no-snaps. Fitting on the stats table alone therefore silently deletes
the entire zero atom and trains a model on the conditional-on-playing population while SERVING it to
a user asking "should I start this guy?", whose whole risk is that the guy does not play.

That is the NF-D11 zero-inflation class in its most literal form, so the spine is built the other way
round: **roster-first, stats LEFT-joined, zeros RETAINED and labelled** — never stats-first.

Three further things this module is deliberately built to make impossible:

  1. **A REALIZED value masquerading as a forecast.** `schedules.temp` / `.wind` are populated only
     for games that have been PLAYED (measured: 0 of 177 unplayed 2026 games carry a temp, vs 173 of
     178 played 2024 games). They are game-book conditions, not forecasts — so using them as a weekly
     feature injects the future. They are in `DEFERRED_FEATURE_CONTRACT`, and `assert_no_leakage`
     rejects any frame carrying them.
  2. **A LABEL-side field used as a FEATURE.** `weekly_rosters.status == 'INA'` is the game-day
     inactive designation, published ~90 minutes before kickoff. It is a fine LABEL and a leak as a
     Tuesday FEATURE. The pre-kickoff, honestly-available signal is the injury report's
     `report_status == 'Out'`, which is a different (and weaker) thing.
  3. **A silent train/serve schema break.** nflverse REPLACED the `depth_charts` schema between 2024
     and 2025: through 2024 it is (season, week, depth_team) at ~37k rows/season; from 2025 `week`
     and `depth_team` are 100% NULL and the table is a ~554k-row near-daily snapshot series keyed on
     a new `dt` capture timestamp. A model trained on the old shape cannot be served from the new
     one. `train_serve_parity` exists to make that class of break a RED TEST rather than a silently
     all-NULL feature in production.

Pure + IO-free (pandas in, dict/DataFrame out) so the fast gate covers every rule here; the lake
reads live in `run_nf_w0_audit.py`. Nothing in this module fits a model — NF-W0 is a gate, not a
modelling story.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

log = logging.getLogger("nfl.fantasy.weekly_frame")

# ── Population definition ────────────────────────────────────────────────────────────────────────
# The GAME-DAY roster. 'ACT' dressed, 'INA' declared inactive. Everything else is off the game-day
# 53 and is NOT a fantasy-startable population: 'CUT' (waived), 'DEV' (practice squad), 'RES'
# (IR/reserve), 'RET' (retired). Measured 2024 wk1 skill: of 983 roster rows, ACT=450 (346 with
# stats) and INA=59; CUT/DEV/RES/RET contributed 474 rows and ZERO stats rows, which is the
# empirical justification for excluding them rather than carrying 474 uninformative zeros.
GAMEDAY_STATUSES: tuple[str, ...] = ("ACT", "INA")

# The positions the weekly fantasy product projects. K and DST are modelled separately (v3 §4A) and
# have their own frames; they are not player-week rows here.
SKILL_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "FB")

# ── Label vocabulary ─────────────────────────────────────────────────────────────────────────────
# `played`   — on the game-day roster, team had a game, and the player recorded a stat line or a snap
# `dressed_no_stat` — ACT, team played, but no stat line AND no offensive snap (a true zero we KEEP)
# `inactive` — declared inactive (roster status INA); a structural zero
# `bye`      — the player's team had no game that week; a structural zero of a DIFFERENT kind
LABEL_PLAYED = "played"
LABEL_DRESSED_NO_STAT = "dressed_no_stat"
LABEL_INACTIVE = "inactive"
LABEL_BYE = "bye"

# The three zero classes are kept DISTINCT rather than collapsed to "0". A bye is deterministic and
# knowable at schedule release; an inactive is a Sunday-morning event; a dressed-no-stat is a
# coaching decision. A model that cannot tell them apart cannot express start/sit risk honestly.
ZERO_LABELS: tuple[str, ...] = (LABEL_DRESSED_NO_STAT, LABEL_INACTIVE, LABEL_BYE)


# ── Point-in-time feature contract ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FeatureSpec:
    """One feature family, with the audit facts that decide whether NF-W1 may use it.

    `pit_fidelity` is the v3 §14 label and is deliberately a THREE-valued judgement, not a boolean:

      retrospective        — reconstructible from the historical record because the underlying value
                             is immutable once the prior game ended (a completed game's box score
                             cannot change what was knowable on the following Tuesday).
      prospective_shadow   — only honest going FORWARD, from our own capture; the historical table is
                             a backfill and does not record what was known at the time.
      not_pit_validated    — cannot be reconstructed as-of, and must not enter a backtest.
    """

    name: str
    source: str
    tier: int                      # 0 free/public · 1 self-service paid · 2 contracted charting
    license: str
    availability: str              # when the value exists relative to the projection timestamp
    history: str
    pit_fidelity: str
    point_in_time_safe: bool
    fallback: str
    notes: str = ""


PIT_RETROSPECTIVE = "retrospective"
PIT_PROSPECTIVE_SHADOW = "prospective_shadow"
PIT_NOT_VALIDATED = "not_pit_validated"

# ── ALLOWED — what NF-W1 may fit on (the free-data minimum-viable set) ───────────────────────────
# Everything here is Tier-0, resolves to weeks <= w-1, and is immutable once the prior game ended.
ALLOWED_FEATURE_CONTRACT: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        "game_context", "nflverse schedules", 0, "free/public",
        "known at schedule release (months ahead)", "1999+", PIT_RETROSPECTIVE, True,
        "none needed",
        "home/away, opponent, rest days, div_game, roof, surface, kickoff. Immutable pre-season. "
        "⛔ EXCLUDES temp/wind — those are realized, see DEFERRED.",
    ),
    FeatureSpec(
        "prior_week_box", "nflverse stats_player_week (lagged)", 0, "free/public",
        "postgame; complete for Sun games by Tue, MNF lands Tue AM", "1999+", PIT_RETROSPECTIVE, True,
        "derive from PBP",
        "carries/targets/receptions/yards/TDs/air yards + native target_share, air_yards_share, wopr.",
    ),
    FeatureSpec(
        "snap_share", "nflverse snap_counts (lagged)", 0, "free/public (PFR-sourced)",
        "postgame", "2012+", PIT_RETROSPECTIVE, True,
        "PBP participation proxy",
        "offense_pct is the workload backbone. Upstream is PFR — a licensing re-read is warranted "
        "before commercial display, not before fitting.",
    ),
    FeatureSpec(
        "participation_proxies", "nflverse pbp_participation offense_players (lagged)", 0,
        "free/public", "postgame", "2016+", PIT_RETROSPECTIVE, True,
        "snap_counts only",
        "players_on_play is 100% non-null every season 2016-2025 ⇒ per-player DROPBACK participation, "
        "red-zone / goal-line / third-down / two-minute participation are all derivable. This is the "
        "honest substitute for route participation — an upper bound (blockers included), not routes.",
    ),
    FeatureSpec(
        "team_environment", "nflverse pbp (lagged)", 0, "free/public",
        "postgame", "1999+ (modern PBP fields 2006+)", PIT_RETROSPECTIVE, True, "none needed",
        "pace, seconds/snap, PROE, no-huddle, early-down pass rate, 4th-down aggressiveness, drive "
        "success, team EPA, red-zone tendencies.",
    ),
    FeatureSpec(
        "opponent_matchup", "nflverse pbp + pbp_participation (lagged)", 0, "free/public",
        "postgame", "1999+ / 2016+ for the participation half", PIT_RETROSPECTIVE, True,
        "none needed",
        "defensive EPA/success/explosive allowed, defensive aDOT, YAC allowed, pressure rate "
        "(was_pressure), man/zone rate, coverage shell, box counts. ⭐ Appendix A calls the last "
        "four GATED; for NFL they are FREE — see the audit doc's correction table.",
    ),
    FeatureSpec(
        "pfr_advanced", "nflverse pfr_advstats_week_* (lagged)", 0, "free/public (PFR-sourced)",
        "postgame", "2018+", PIT_RETROSPECTIVE, True, "PBP proxies",
        "pressures/hurries/blitzed, yards before+after contact, broken tackles, drops, and the "
        "defender-in-coverage block (def_completion_pct, def_passer_rating_allowed, def_adot).",
    ),
    FeatureSpec(
        "ngs_qualifying", "nflverse nextgen_stats (lagged)", 0, "free/public",
        "postgame", "2016+", PIT_RETROSPECTIVE, True, "PBP-derived proxies",
        "separation, cushion, YAC-over-expected, intended air yards (aDOT), CPOE, RYOE. ⚠️ QUALIFYING "
        "PLAYERS ONLY — ~58 receivers/week, so this is a SPARSE overlay with structural missingness, "
        "not a population feature. Must carry an explicit present/absent flag, never impute 0.",
    ),
    FeatureSpec(
        "injury_report", "nflverse injuries (lagged + current week)", 0, "free/public",
        "Wed-Fri publication; current-week rows ARE pre-kickoff", "2009+",
        PIT_PROSPECTIVE_SHADOW, True, "designation-only model",
        "⚠️ SPLIT FIDELITY: 2009-2024 carry a real `date_modified` as-of timestamp (retrospective). "
        "nflverse DROPPED the column in 2025 ⇒ from 2025 the as-of time must come from OUR capture "
        "⇒ prospective_shadow. Also `report_status` is only ~46% non-null: NULL means 'on the report, "
        "no designation yet', NOT 'healthy'.",
    ),
    FeatureSpec(
        "injury_rate", "nflverse injuries (group aggregate of injury_report)", 0, "free/public",
        "Wed-Fri publication; aggregates only rows stamped before the target row's own gameday",
        "2009+", PIT_PROSPECTIVE_SHADOW, True, "designation-only model",
        "NF-W2b: week×position GROUP rates (no player linkage) of the injury_report family — the "
        "marginal-listing-rate channel absorbed into the base foil. Same source rows, same "
        "fail-closed date_modified admissibility, aggregated strictly before each row's own "
        "gameday 00:00 UTC (a whole-week rate would leak into Thursday games). Inherits the "
        "SPLIT FIDELITY: 2025+ has no date_modified ⇒ NaN + observed=0, never fillna(0).",
    ),
    FeatureSpec(
        "prior_season_priors", "nflverse rosters / draft_picks / combine / players", 0, "free/public",
        "pre-season", "all-time", PIT_RETROSPECTIVE, True, "none needed",
        "age, experience, draft capital, athletic measurables — the NF1 season-model prior surface.",
    ),
    FeatureSpec(
        "availability_projection", "derived in-fold from certified families (no new source)", 0,
        "free/public (derived)",
        "computable at the projection timestamp — a model output over already-certified inputs",
        "2016+", PIT_PROSPECTIVE_SHADOW, True, "climatology form",
        "NF-W4: the availability-mixture projections (P(played), conditional snap share, their "
        "product, and the share spread) injected into the champion's feature matrix. DERIVED "
        "family: consumes ONLY certified columns (prior_week_box / snap_share / injury_report / "
        "injury_rate / game_context / prior_season_priors), fit strictly in-fold, so its as-of "
        "rule is inherited from its inputs and no new PIT record class exists. Inherits the "
        "injury families' SPLIT FIDELITY (2025 = capture-based) ⇒ prospective_shadow.",
    ),
)

# ── DEFERRED — what NF-W1 may NOT fit on, and exactly why ────────────────────────────────────────
DEFERRED_FEATURE_CONTRACT: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        "route_participation", "FTN / PFF B2B / SIS", 2, "contracted charting",
        "postgame, SLA contractual", "vendor-dependent", PIT_NOT_VALIDATED, False,
        "dropback participation proxy (ALLOWED: participation_proxies)",
        "VERIFIED GATED. nflverse pbp_participation carries a single play-level `route` string for "
        "the TARGETED receiver only (~41% of plays, 14 route names) — it is NOT per-player route "
        "attribution, so true routes-run / TPRR / YPRR remain unavailable free.",
    ),
    FeatureSpec(
        "first_read_share", "FTN / PFF / SIS", 2, "contracted charting", "postgame",
        "recent charted seasons", PIT_NOT_VALIDATED, False, "exclude",
        "No free proxy. Excluded from V1 per v3 §6.",
    ),
    FeatureSpec(
        "individual_ol_grades", "PFF B2B", 2, "contracted charting", "postgame",
        "vendor-dependent", PIT_NOT_VALIDATED, False,
        "unit-level: snap continuity + team pressure rate + YBC",
        "The one genuine NFL charting gap (N0.1 §8). A consumer PFF+ subscription does NOT include "
        "API/product rights (v3 A.1).",
    ),
    FeatureSpec(
        "weather_forecast", "NOT INGESTED (reuse MLB's scripts/ingest_weather.py mechanism)", 0,
        "free (Open-Meteo, no key)",
        "forecast available 7-15 days ahead — but we capture NONE of it today", "none",
        PIT_NOT_VALIDATED, False,
        "roof/surface only (those ARE known pre-season and are in game_context)",
        "🚨 THE TRAP: `schedules.temp`/`.wind` LOOK like weather and are REALIZED game-book "
        "conditions — measured 0 of 177 unplayed 2026 games carry a temp vs 173 of 178 played 2024 "
        "games. Using them is a hard leak. CURE = the MLB mechanism, which already has exactly the "
        "two legs NFL needs: `forecast_pregame` (the weekly-build feature) + `forecast_intraday` at "
        "fixed hours-to-kickoff checkpoints (the right-before-kickoff feature). Stadium coordinates "
        "are ALREADY BUILT (`stg_nfl_team_geo`, 32 teams, from N1.0's travel feature). ⚠️ A forecast "
        "CANNOT be backfilled — only forward capture makes this PIT-safe, so every uncaptured week "
        "is permanently lost.",
    ),
    FeatureSpec(
        "market_context", "The Odds API (landed 2020-2024 only)", 1, "existing paid sub",
        "continuous pre-kickoff", "game lines 2020-2024; props 2023-2024", PIT_PROSPECTIVE_SHADOW,
        False, "omit from V1",
        "Landed snapshots are taken at kickoff-minus-5min = CLOSING, not Tuesday. A Tuesday model "
        "may not use a closing line (v3 §13). 2025 is NOT landed at all. ⇒ deferred until a "
        "Tuesday-timestamped capture exists.",
    ),
    FeatureSpec(
        "player_props", "The Odds API event endpoint", 1, "existing paid sub, credit-heavy",
        "1-5 days ahead, sparse early", "2023-2024 closing only", PIT_NOT_VALIDATED, False,
        "omit from V1",
        "~34.2k credits/season to backfill. Closing props must never be backfilled onto an earlier "
        "projection (v3 §13).",
    ),
    FeatureSpec(
        "depth_chart_rank", "nflverse depth_charts", 0, "free but source-fragile",
        "≤2024 weekly; 2025+ near-daily dt snapshots", "2001+ (schema REPLACED at 2025)",
        PIT_NOT_VALIDATED, False, "usage-derived role (snap / carry / target share)",
        "🚨 DEFERRED FOR A MEASURED SEMANTIC SHIFT, NOT A PLUMBING GAP. nflverse replaced the feed "
        "at 2025: through 2024 it is a weekly team depth chart keyed (season, week, depth_team), "
        "~37k rows/season, NO capture timestamp (backfilled ⇒ not PIT-reconstructible); from 2025 "
        "`week`/`depth_team` are 100% NULL and it is a ~554k-row ESPN near-daily snapshot series on "
        "a `dt` VARCHAR capture stamp (221 captures in 2025 — genuinely PIT). A translation layer "
        "ALREADY EXISTS and works (`stg_nfl_depth_charts` ASOF-buckets dt→week; verified ~590 skill "
        "players/week for 2025). What is NOT established is COMPARABILITY: measured RB depth ranks "
        "run 1-3 in 2024 (≈1.08 rank-1 RBs per team-week) but 1-6+ in 2025, so 'rank 3' denotes a "
        "different player in each era and ranks 4-6 are unseen in training. ⇒ the remaining work is "
        "a cross-era comparability/recalibration check, not more plumbing.",
    ),
    FeatureSpec(
        "gameday_inactive_status", "nflverse weekly_rosters.status == 'INA'", 0, "free/public",
        "~90 min pre-kickoff", "2002+", PIT_NOT_VALIDATED, False,
        "injury_report report_status == 'Out' (ALLOWED)",
        "LABEL-SIDE ONLY. Available ~90 min pre-kickoff, so it is a leak in any Tue/Fri build and is "
        "only admissible in a Sunday-morning model. Used here to BUILD the label, never as a feature.",
    ),
)

# Feature/column families that must never appear in a weekly frame's feature set. Kept as substrings
# because the leak is in the SOURCE COLUMN, whatever a builder renames it to downstream.
LEAKY_COLUMNS: tuple[str, ...] = (
    "temp", "wind",                      # realized game-book conditions (see weather_forecast)
    "result", "total", "home_score", "away_score",   # the game outcome itself
    "fantasy_points", "fantasy_points_ppr",          # the label
)


def contract_as_frame(specs: tuple[FeatureSpec, ...] = ALLOWED_FEATURE_CONTRACT) -> pd.DataFrame:
    """The feature contract as a DataFrame — the audit doc's table and the serving guard read this."""
    return pd.DataFrame([spec.__dict__ for spec in specs])


# ── Spine ────────────────────────────────────────────────────────────────────────────────────────
def build_spine(
    rosters: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    positions: tuple[str, ...] = SKILL_POSITIONS,
    statuses: tuple[str, ...] = GAMEDAY_STATUSES,
) -> pd.DataFrame:
    """One row per (season, week, player) for every game-day-rostered skill player, PLUS bye rows.

    `rosters` is nflverse weekly_rosters (season, week, team, position, status, gsis_id);
    `schedule` is nflverse schedules (season, week, home_team, away_team).

    ⭐ BYES ARE CONSTRUCTED, NOT READ. Measured on 2024 REG: weekly_rosters holds 544 team-weeks and
    the schedule holds exactly 544 team-week games (32 teams x 18 weeks - 32 byes) — i.e. the roster
    feed emits NO ROW AT ALL for a team's bye week. So a spine built straight off the roster feed
    silently drops every bye, and the model never learns that a bye is a deterministic zero it could
    have known about at schedule release. We therefore carry each player across his team's bye and
    label it, rather than letting the absence speak for itself.
    """
    req_r = {"season", "week", "team", "position", "status", "gsis_id"}
    req_s = {"season", "week", "home_team", "away_team"}
    if missing := req_r - set(rosters.columns):
        raise ValueError(f"rosters missing columns: {sorted(missing)}")
    if missing := req_s - set(schedule.columns):
        raise ValueError(f"schedule missing columns: {sorted(missing)}")

    ros = rosters[
        rosters["position"].isin(positions) & rosters["status"].isin(statuses)
    ].copy()
    ros["week"] = ros["week"].astype("int64")
    ros["season"] = ros["season"].astype("int64")

    # team-weeks that actually have a game
    played = pd.concat(
        [
            schedule[["season", "week", "home_team"]].rename(columns={"home_team": "team"}),
            schedule[["season", "week", "away_team"]].rename(columns={"away_team": "team"}),
        ],
        ignore_index=True,
    ).drop_duplicates()
    played["week"] = played["week"].astype("int64")
    played["season"] = played["season"].astype("int64")
    played["_has_game"] = True

    spine = ros.merge(played, on=["season", "week", "team"], how="left")
    spine["_has_game"] = spine["_has_game"].isin([True]).astype(bool)

    bye = _bye_rows(spine, played)
    out = pd.concat([spine, bye], ignore_index=True) if len(bye) else spine
    return out.sort_values(["season", "week", "team", "gsis_id"]).reset_index(drop=True)


def _bye_rows(spine: pd.DataFrame, played: pd.DataFrame) -> pd.DataFrame:
    """Carry each (season, player, team) across the team-weeks that team had NO game.

    A bye row is attributed only for weeks INSIDE the player's own observed roster tenure with that
    team (first..last rostered week). That bound is deliberate: without it a player traded in week 10
    would be handed a phantom bye row for his new team's week-5 bye, inventing a zero he could never
    have been asked to start."""
    if spine.empty:
        return spine.iloc[0:0]
    season_weeks = (
        played.groupby("season")["week"].agg(["min", "max"]).reset_index()
        .rename(columns={"min": "_wk_lo", "max": "_wk_hi"})
    )
    all_team_weeks = []
    for _, row in season_weeks.iterrows():
        wks = range(int(row["_wk_lo"]), int(row["_wk_hi"]) + 1)
        teams = played.loc[played["season"] == row["season"], "team"].unique()
        all_team_weeks.append(
            pd.DataFrame([(row["season"], w, t) for w in wks for t in teams],
                         columns=["season", "week", "team"])
        )
    if not all_team_weeks:
        return spine.iloc[0:0]
    grid = pd.concat(all_team_weeks, ignore_index=True)
    grid["season"] = grid["season"].astype("int64")
    byes = grid.merge(played, on=["season", "week", "team"], how="left")
    byes = byes[byes["_has_game"].isna()][["season", "week", "team"]]
    if byes.empty:
        return spine.iloc[0:0]

    tenure = (
        spine.groupby(["season", "gsis_id", "team", "position"])["week"]
        .agg(["min", "max"]).reset_index().rename(columns={"min": "_lo", "max": "_hi"})
    )
    out = tenure.merge(byes, on=["season", "team"], how="inner")
    out = out[(out["week"] >= out["_lo"]) & (out["week"] <= out["_hi"])]
    if out.empty:
        return spine.iloc[0:0]
    out = out[["season", "week", "team", "gsis_id", "position"]].copy()
    out["status"] = "ACT"
    out["_has_game"] = False
    return out


# ── Labels ───────────────────────────────────────────────────────────────────────────────────────
def attach_labels(
    spine: pd.DataFrame,
    stats: pd.DataFrame,
    *,
    label_version: str,
    label_as_of_timestamp: str,
    scoring_system_id: str = "ppr",
    stat_source: str = "nflverse.stats_player_week",
    snaps: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """LEFT-join the stat line onto the spine and RETAIN every zero, labelled by its cause.

    ⛔ The join direction is the whole point. `stats` is the RIGHT side and a missing match becomes a
    retained zero, never a dropped row. `label_version` / `label_as_of_timestamp` are stamped on
    every row because a fantasy label is itself point-in-time data (v3 §12B) — official stats are
    corrected after the game, and re-scoring an old leaderboard against a later label silently
    changes model rankings.
    """
    if "player_id" not in stats.columns:
        raise ValueError("stats must carry player_id")
    pts_col = "fantasy_points_ppr" if scoring_system_id == "ppr" else "fantasy_points"
    if pts_col not in stats.columns:
        raise ValueError(f"stats must carry {pts_col} for scoring_system_id={scoring_system_id!r}")

    keep = ["season", "week", "player_id", pts_col]
    for opt in ("carries", "targets", "attempts", "receptions"):
        if opt in stats.columns:
            keep.append(opt)
    s = stats[keep].rename(columns={"player_id": "gsis_id", pts_col: "fantasy_points"})
    s["season"] = s["season"].astype("int64")
    s["week"] = s["week"].astype("int64")
    s["_has_stat_row"] = True

    out = spine.merge(s, on=["season", "week", "gsis_id"], how="left")
    out["_has_stat_row"] = out["_has_stat_row"].isin([True]).astype(bool)

    if snaps is not None and not snaps.empty and {"season", "week", "gsis_id"} <= set(snaps.columns):
        sn = snaps[["season", "week", "gsis_id", "offense_snaps"]].copy()
        sn["season"] = sn["season"].astype("int64")
        sn["week"] = sn["week"].astype("int64")
        out = out.merge(sn, on=["season", "week", "gsis_id"], how="left")
    else:
        out["offense_snaps"] = pd.NA

    # ⭐ ZERO RETENTION: a player with no stat line scores 0.0, he does not vanish.
    out["fantasy_points"] = out["fantasy_points"].fillna(0.0).astype(float)

    snap_pos = pd.to_numeric(out["offense_snaps"], errors="coerce").fillna(0) > 0
    out["label"] = LABEL_DRESSED_NO_STAT
    out.loc[~out["_has_game"], "label"] = LABEL_BYE
    out.loc[out["_has_game"] & (out["status"] == "INA"), "label"] = LABEL_INACTIVE
    out.loc[out["_has_game"] & (out["_has_stat_row"] | snap_pos), "label"] = LABEL_PLAYED
    # A player carrying a stat line while flagged INA is a data conflict, not a played game; the
    # stat line wins (he demonstrably appeared) and the conflict is counted in the status report.
    out["label_conflict"] = out["_has_game"] & (out["status"] == "INA") & out["_has_stat_row"]
    out.loc[out["label_conflict"], "label"] = LABEL_PLAYED

    out["label_version"] = label_version
    out["label_as_of_timestamp"] = label_as_of_timestamp
    out["scoring_system_id"] = scoring_system_id
    out["stat_source"] = stat_source
    out["is_zero"] = out["fantasy_points"] == 0.0
    return out


# ── Coverage ─────────────────────────────────────────────────────────────────────────────────────
def coverage_by_year_position(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows, label mix, and the zero share per (season, position) — the AC's coverage report.

    The zero share is reported because it is the number that decides NF-W1's scoring rule: a
    population that is ~40% zeros has its conditional median at or near the floor, which is exactly
    where MAE inverts and pays for pessimism (NF-D11). The frame is built to make CRPS the honest
    primary metric; this table is the evidence for that choice.
    """
    g = frame.groupby(["season", "position"], dropna=False)
    out = g.agg(
        n_rows=("gsis_id", "size"),
        n_players=("gsis_id", "nunique"),
        n_played=("label", lambda s: int((s == LABEL_PLAYED).sum())),
        n_inactive=("label", lambda s: int((s == LABEL_INACTIVE).sum())),
        n_bye=("label", lambda s: int((s == LABEL_BYE).sum())),
        n_dressed_no_stat=("label", lambda s: int((s == LABEL_DRESSED_NO_STAT).sum())),
        n_zero=("is_zero", "sum"),
        mean_points=("fantasy_points", "mean"),
        median_points=("fantasy_points", "median"),
    ).reset_index()
    out["zero_share"] = (out["n_zero"] / out["n_rows"]).round(4)
    out["played_share"] = (out["n_played"] / out["n_rows"]).round(4)
    out["mean_points"] = out["mean_points"].round(3)
    return out.sort_values(["season", "position"]).reset_index(drop=True)


# ── Leakage guard (fail-closed, v3 §13) ──────────────────────────────────────────────────────────
class LeakageError(AssertionError):
    """Raised when a frame would carry a value not knowable at the projection timestamp."""


def assert_no_leakage(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    projection_week: int,
    source_week_column: str | None = None,
) -> None:
    """Reject the build rather than degrade it (v3 §13 fail-closed).

    Three rejections, each one a leak this repo has actually seen the shape of elsewhere:
      1. a feature column matching a known-leaky source column (realized weather, the game result,
         the label itself);
      2. a feature whose underlying source week is >= the projection week — a rolling window that
         contains the target game;
      3. a feature column that is not in the ALLOWED contract at all (unknown provenance is a
         rejection, not a warning — an unaudited feature has no as-of rule by definition).
    """
    allowed_names = {s.name for s in ALLOWED_FEATURE_CONTRACT}

    leaky = [
        c for c in feature_columns
        if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_") for tok in LEAKY_COLUMNS)
    ]
    if leaky:
        raise LeakageError(
            f"leaky feature columns reject the build: {sorted(leaky)} — these are realized/outcome "
            f"values not knowable at the week-{projection_week} projection timestamp"
        )

    unknown = [c for c in feature_columns if c not in allowed_names]
    if unknown:
        raise LeakageError(
            f"features not in ALLOWED_FEATURE_CONTRACT reject the build: {sorted(unknown)} — an "
            f"unaudited feature has no as-of rule (v3 §13: missing point-in-time provenance)"
        )

    if source_week_column and source_week_column in frame.columns:
        bad = pd.to_numeric(frame[source_week_column], errors="coerce") >= projection_week
        if bool(bad.any()):
            raise LeakageError(
                f"{int(bad.sum())} rows carry {source_week_column} >= projection week "
                f"{projection_week} — a rolling window contains the target or a future game"
            )


# ── Train/serve parity ───────────────────────────────────────────────────────────────────────────
def train_serve_parity(
    training_frame: pd.DataFrame,
    serving_frame: pd.DataFrame,
    *,
    key: tuple[str, ...] = ("season", "week", "gsis_id"),
    compare_columns: list[str] | None = None,
    tolerance: float = 1e-9,
) -> dict:
    """Does the training frame equal what serving assembles at the projection timestamp?

    ⭐ This is the check the depth-chart break would have failed silently. A schema replacement
    upstream does not raise — it produces an all-NULL column on one side, which every downstream
    aggregate happily swallows. So parity compares the KEY SET and the VALUES, and reports a column
    present on one side only as a hard failure rather than a coverage note.
    """
    result: dict = {"train_serve_parity": "PASS", "failures": []}

    t_cols, s_cols = set(training_frame.columns), set(serving_frame.columns)
    if only_train := sorted(t_cols - s_cols):
        result["failures"].append(f"columns in TRAINING only: {only_train}")
    if only_serve := sorted(s_cols - t_cols):
        result["failures"].append(f"columns in SERVING only: {only_serve}")

    missing_key = [k for k in key if k not in t_cols or k not in s_cols]
    if missing_key:
        result["failures"].append(f"key columns absent: {missing_key}")
        result["train_serve_parity"] = "FAIL"
        return result

    t_keys = set(map(tuple, training_frame[list(key)].to_numpy().tolist()))
    s_keys = set(map(tuple, serving_frame[list(key)].to_numpy().tolist()))
    result["n_train_rows"] = len(t_keys)
    result["n_serve_rows"] = len(s_keys)
    result["n_key_only_train"] = len(t_keys - s_keys)
    result["n_key_only_serve"] = len(s_keys - t_keys)
    if t_keys != s_keys:
        result["failures"].append(
            f"key sets differ: {len(t_keys - s_keys)} train-only, {len(s_keys - t_keys)} serve-only"
        )

    cols = compare_columns if compare_columns is not None else sorted(
        (t_cols & s_cols) - set(key)
    )
    shared = sorted(t_keys & s_keys)
    if shared and cols:
        t = training_frame.set_index(list(key)).sort_index()
        s = serving_frame.set_index(list(key)).sort_index()
        idx = pd.MultiIndex.from_tuples(shared, names=list(key))
        mismatched = []
        for c in cols:
            if c not in t.columns or c not in s.columns:
                continue
            tv, sv = t.loc[idx, c], s.loc[idx, c]
            if pd.api.types.is_numeric_dtype(tv) and pd.api.types.is_numeric_dtype(sv):
                diff = (tv.fillna(0) - sv.fillna(0)).abs() > tolerance
                both_na = tv.isna() & sv.isna()
                bad = int((diff & ~both_na).sum())
            else:
                bad = int((tv.astype(str) != sv.astype(str)).sum())
            if bad:
                mismatched.append(f"{c}({bad} rows)")
        if mismatched:
            result["failures"].append(f"value mismatches: {mismatched}")

    result["train_serve_parity"] = "FAIL" if result["failures"] else "PASS"
    return result


# ── Status report (the AC's emitted fields) ──────────────────────────────────────────────────────
@dataclass
class FrameStatus:
    weekly_training_frame_status: str
    weekly_serving_frame_status: str
    point_in_time_safe: dict = field(default_factory=dict)
    train_serve_parity: str = "NOT_RUN"
    known_missingness: dict = field(default_factory=dict)
    allowed_feature_contract: list = field(default_factory=list)
    deferred_feature_contract: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "weekly_training_frame_status": self.weekly_training_frame_status,
            "weekly_serving_frame_status": self.weekly_serving_frame_status,
            "point_in_time_safe": self.point_in_time_safe,
            "train_serve_parity": self.train_serve_parity,
            "known_missingness": self.known_missingness,
            "allowed_feature_contract": self.allowed_feature_contract,
            "deferred_feature_contract": self.deferred_feature_contract,
        }


def build_status(
    frame: pd.DataFrame,
    parity: dict,
    *,
    training_status: str,
    serving_status: str,
    known_missingness: dict | None = None,
) -> FrameStatus:
    """Assemble the seven status fields the epic names, from measured frame facts."""
    miss = dict(known_missingness or {})
    if not frame.empty:
        miss.setdefault(
            "label_conflicts_ina_with_stats",
            int(frame["label_conflict"].sum()) if "label_conflict" in frame else 0,
        )
        miss.setdefault("zero_share_overall", round(float(frame["is_zero"].mean()), 4))
    return FrameStatus(
        weekly_training_frame_status=training_status,
        weekly_serving_frame_status=serving_status,
        point_in_time_safe={s.name: s.point_in_time_safe for s in
                            ALLOWED_FEATURE_CONTRACT + DEFERRED_FEATURE_CONTRACT},
        train_serve_parity=parity.get("train_serve_parity", "NOT_RUN"),
        known_missingness=miss,
        allowed_feature_contract=[s.name for s in ALLOWED_FEATURE_CONTRACT],
        deferred_feature_contract=[s.name for s in DEFERRED_FEATURE_CONTRACT],
    )
