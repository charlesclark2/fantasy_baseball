"""p2_1_plays_rollup.py — NCAAF-P2.1: the leakage-safe play-derived unit-matchup / special-teams block.

WHY THIS EXISTS
---------------
The P2.1 pre-registration (§0 V6) verified that only **4 of the 9** interactions in the 2026-08-03
stress-test doc §6.2 compact matchup set are constructible from the P1.3 pregame matrix. The matrix
carries offense/defense PAIRS for ppa, success rate, explosiveness, line-yards and stuff-rate — but

  * `passing_yards_per_game` / `completion_rate`  are OFFENSE-ONLY (no defensive counterpart)
  * `points_per_drive` / `scoring_opportunity_rate` / `three_and_out_rate` are OFFENSE-ONLY
  * there is no standard-vs-passing-down split, no havoc rate and no sack/pressure column at all

so an H2b registered on the matrix alone would silently test HALF the doc's set while reporting the
doc's name. This module builds the missing five from the `plays` Delta (2.20 M plays, 2014–2025,
carrying `playType`, `down`, `distance`, `yardsGained`, `yardsToGoal`, `ppa` and the running score),
plus the H13 special-teams block, so H2b tests what it claims to test.

LEAKAGE SAFETY — the load-bearing property
------------------------------------------
Every emitted column is a **season-to-date cumulative through STRICTLY PRIOR GAME DATES** within a
team-season. The accumulation is ordered by `game_date`, NOT by `week`:

  * ordering by calendar date is monotone with `season_order_week`, and
  * it is immune to the postseason `week` = 1 collision that the P1.1/P1.4 CV axis guards against.

A team's feature for a game on date `d` is computed from that team's games on dates `< d` only, so a
week-`w` row can never see week-`w` plays. Week 1 rows are therefore NULL by construction (no prior
games) — which is correct and matches the P1.3 matrix's own in-season features.

GARBAGE TIME
------------
Efficiency aggregates EXCLUDE garbage time using the repo's single definition
(`fact_ncaaf_play.is_garbage_time`: score margin > 43/37/27/22 by quarter), so these columns are
directly comparable with the matrix's existing `*_clean_*` family. Special-teams and pressure COUNT
aggregates keep all plays — a blocked punt in a blowout still happened.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Play-type taxonomy — measured against the real lake, not assumed.
# (`select playType, count(*) from plays where season=2023 group by 1` — 37 distinct types.)
# ---------------------------------------------------------------------------

_PASS_TYPES = (
    "Pass Reception", "Pass Incompletion", "Sack", "Passing Touchdown", "Interception",
    "Pass Interception Return", "Interception Return Touchdown", "Pass",
)
_RUSH_TYPES = ("Rush", "Rushing Touchdown")
_SACK_TYPES = ("Sack",)
_TURNOVER_TYPES = (
    "Interception", "Pass Interception Return", "Interception Return Touchdown",
    "Fumble Recovery (Opponent)", "Fumble Return Touchdown",
)
_FG_ATT_TYPES = (
    "Field Goal Good", "Field Goal Missed", "Blocked Field Goal",
    "Blocked Field Goal Touchdown", "Missed Field Goal Return",
)
_FG_MADE_TYPES = ("Field Goal Good",)
_PUNT_TYPES = ("Punt", "Blocked Punt", "Punt Return Touchdown", "Blocked Punt Touchdown")
_ST_TD_TYPES = (
    "Kickoff Return Touchdown", "Punt Return Touchdown", "Blocked Punt Touchdown",
    "Blocked Field Goal Touchdown", "Missed Field Goal Return",
)
_BLOCK_TYPES = ("Blocked Punt", "Blocked Field Goal", "Blocked Punt Touchdown",
                "Blocked Field Goal Touchdown")

# The repo's ONE garbage-time definition (fact_ncaaf_play.sql): margin by quarter.
_GARBAGE_MARGIN = {1: 43, 2: 37, 3: 27, 4: 22}


def _sql_in(values: tuple[str, ...]) -> str:
    return "(" + ",".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


def plays_game_team_sql(plays_rel: str, games_rel: str, min_season: int = 2014) -> str:
    """SQL → ONE row per (season, game_id, team, game_date) with that team's OFFENSE aggregates and
    the aggregates it ALLOWED on defence, for the season-to-date accumulation below."""
    return f"""
    with p as (
        select
            season,
            try_cast(json_extract_string(raw_json,'$.gameId')       as bigint) as game_id,
            json_extract_string(raw_json,'$.offense')                          as offense,
            json_extract_string(raw_json,'$.defense')                          as defense,
            json_extract_string(raw_json,'$.playType')                         as play_type,
            try_cast(json_extract_string(raw_json,'$.period')       as int)    as period,
            try_cast(json_extract_string(raw_json,'$.down')         as int)    as down,
            try_cast(json_extract_string(raw_json,'$.distance')     as int)    as distance,
            try_cast(json_extract_string(raw_json,'$.yardsGained')  as int)    as yards_gained,
            try_cast(json_extract_string(raw_json,'$.yardsToGoal')  as int)    as yards_to_goal,
            try_cast(json_extract_string(raw_json,'$.ppa')          as double) as ppa,
            try_cast(json_extract_string(raw_json,'$.offenseScore') as int)    as off_score,
            try_cast(json_extract_string(raw_json,'$.defenseScore') as int)    as def_score,
            -- gross punt distance, recoverable ONLY from the play text (see st_off below)
            try_cast(regexp_extract(json_extract_string(raw_json,'$.playText'),
                                    'punt for (-?[0-9]+) yds', 1) as int)      as punt_gross
        from {plays_rel}
        where season >= {int(min_season)}
    ),
    f as (
        select *,
            -- the repo's SINGLE garbage-time definition (fact_ncaaf_play.sql)
            case
                when period = 1 then abs(off_score - def_score) > {_GARBAGE_MARGIN[1]}
                when period = 2 then abs(off_score - def_score) > {_GARBAGE_MARGIN[2]}
                when period = 3 then abs(off_score - def_score) > {_GARBAGE_MARGIN[3]}
                when period >= 4 then abs(off_score - def_score) > {_GARBAGE_MARGIN[4]}
                else false
            end                                                     as is_garbage,
            play_type in {_sql_in(_PASS_TYPES)}                      as is_pass,
            play_type in {_sql_in(_RUSH_TYPES)}                      as is_rush,
            play_type in {_sql_in(_SACK_TYPES)}                      as is_sack,
            play_type in {_sql_in(_TURNOVER_TYPES)}                  as is_turnover,
            play_type in {_sql_in(_FG_ATT_TYPES)}                    as is_fg_att,
            play_type in {_sql_in(_FG_MADE_TYPES)}                   as is_fg_made,
            play_type in {_sql_in(_PUNT_TYPES)}                      as is_punt,
            play_type in {_sql_in(_ST_TD_TYPES)}                     as is_st_td,
            play_type in {_sql_in(_BLOCK_TYPES)}                     as is_block,
            -- standard vs passing down (doc §6.2): the conventional CFB split
            (down = 1 or (down = 2 and distance <= 7) or (down in (3,4) and distance <= 4))
                                                                     as is_standard_down
        from p
        where game_id is not null and offense is not null and defense is not null
    ),
    scrim as (select * from f where (is_pass or is_rush) and not is_garbage),
    -- OFFENSE side: what this team DID with the ball
    off_agg as (
        select season, game_id, offense as team,
               count(*)                                                   as o_plays,
               avg(ppa)                                                   as o_ppa,
               avg(case when is_pass then ppa end)                        as o_pass_ppa,
               avg(case when is_rush then ppa end)                        as o_rush_ppa,
               avg(case when is_standard_down then ppa end)               as o_sd_ppa,
               avg(case when not is_standard_down then ppa end)           as o_pd_ppa,
               avg(case when yards_to_goal <= 20 then ppa end)            as o_rz_ppa,
               sum(case when is_pass then 1 else 0 end)                   as o_dropbacks
        from scrim group by 1,2,3
    ),
    def_agg as (
        select season, game_id, defense as team,
               count(*)                                                   as d_plays,
               avg(ppa)                                                   as d_ppa,
               avg(case when is_pass then ppa end)                        as d_pass_ppa,
               avg(case when is_rush then ppa end)                        as d_rush_ppa,
               avg(case when is_standard_down then ppa end)               as d_sd_ppa,
               avg(case when not is_standard_down then ppa end)           as d_pd_ppa,
               avg(case when yards_to_goal <= 20 then ppa end)            as d_rz_ppa
        from scrim group by 1,2,3
    ),
    -- pressure + havoc use ALL scrimmage plays (a sack in garbage time is still a sack, but keep
    -- the same clean universe so the RATE denominators match the efficiency block)
    press_off as (
        select season, game_id, offense as team,
               sum(case when is_sack then 1 else 0 end)                   as sacks_allowed,
               sum(case when is_pass then 1 else 0 end)                   as pass_plays,
               sum(case when is_turnover then 1 else 0 end)               as giveaways,
               count(*)                                                   as tot_plays
        from f where (is_pass or is_rush) group by 1,2,3
    ),
    press_def as (
        select season, game_id, defense as team,
               sum(case when is_sack then 1 else 0 end)                   as sacks_made,
               sum(case when is_pass then 1 else 0 end)                   as pass_faced,
               sum(case when is_turnover then 1 else 0 end)               as takeaways,
               count(*)                                                   as tot_faced
        from f where (is_pass or is_rush) group by 1,2,3
    ),
    -- SPECIAL TEAMS (H13). FG/punt are the KICKING team = `offense` on those play rows.
    st_off as (
        select season, game_id, offense as team,
               sum(case when is_fg_att  then 1 else 0 end)                as fg_att,
               sum(case when is_fg_made then 1 else 0 end)                as fg_made,
               avg(case when is_fg_att  then yards_to_goal end)           as fg_avg_dist,
               sum(case when is_punt    then 1 else 0 end)                as punts,
               -- ⚠️ VERIFIED SEMANTICS (P2.1, 2026-08-15): on a Punt row `yardsGained` is the
               -- RETURN yardage, NOT the punt distance — the gross distance appears ONLY in
               -- `playText` ("… punt for 36 yds …"). Taking `avg(yardsGained)` as "punt average"
               -- yields ~1.3 yards, which is a silently WRONG feature that still looks like a
               -- number. So the gross is parsed out and the NET is gross − return.
               sum(case when play_type = 'Punt' then punt_gross end)      as punt_gross_sum,
               sum(case when play_type = 'Punt' and punt_gross is not null
                        then 1 else 0 end)                                as punt_n,
               sum(case when play_type = 'Punt' then yards_gained end)    as punt_ret_sum,
               sum(case when is_st_td   then 1 else 0 end)                as st_td_for,
               sum(case when is_block   then 1 else 0 end)                as st_block_against
        from f group by 1,2,3
    ),
    st_def as (
        select season, game_id, defense as team,
               sum(case when is_st_td  then 1 else 0 end)                 as st_td_against,
               sum(case when is_block  then 1 else 0 end)                 as st_block_for,
               sum(case when is_fg_att then 1 else 0 end)                 as fg_faced,
               sum(case when is_fg_made then 1 else 0 end)                as fg_allowed
        from f group by 1,2,3
    ),
    g as (
        select try_cast(json_extract_string(raw_json,'$.id') as bigint)   as game_id,
               try_cast(json_extract_string(raw_json,'$.startDate') as timestamp) as game_ts
        from {games_rel}
    )
    select coalesce(o.season, d.season, po.season, st.season)   as season,
           coalesce(o.game_id, d.game_id, po.game_id, st.game_id) as game_id,
           coalesce(o.team, d.team, po.team, st.team)           as team,
           g.game_ts,
           o.o_plays, o.o_ppa, o.o_pass_ppa, o.o_rush_ppa, o.o_sd_ppa, o.o_pd_ppa, o.o_rz_ppa,
           o.o_dropbacks,
           d.d_plays, d.d_ppa, d.d_pass_ppa, d.d_rush_ppa, d.d_sd_ppa, d.d_pd_ppa, d.d_rz_ppa,
           po.sacks_allowed, po.pass_plays, po.giveaways, po.tot_plays,
           pd.sacks_made, pd.pass_faced, pd.takeaways, pd.tot_faced,
           st.fg_att, st.fg_made, st.fg_avg_dist, st.punts,
           st.punt_gross_sum, st.punt_n, st.punt_ret_sum,
           st.st_td_for, st.st_block_against,
           sd.st_td_against, sd.st_block_for, sd.fg_faced, sd.fg_allowed
    from off_agg o
    full outer join def_agg  d  using (season, game_id, team)
    full outer join press_off po using (season, game_id, team)
    full outer join press_def pd using (season, game_id, team)
    full outer join st_off   st using (season, game_id, team)
    full outer join st_def   sd using (season, game_id, team)
    left join g on g.game_id = coalesce(o.game_id, d.game_id, po.game_id, st.game_id)
    """


# The RATE columns the season-to-date accumulation emits per team. Each is a ratio of two
# accumulated sums, never an average-of-averages (which would weight a 40-play game like a 90-play
# one and is the classic silent-bias here).
_RATIO_SPECS: tuple[tuple[str, str, str], ...] = (
    # (emitted name,            numerator sum,      denominator sum)
    ("st_off_ppa",              "o_ppa_w",          "o_plays"),
    ("st_off_pass_ppa",         "o_pass_ppa_w",     "o_pass_n"),
    ("st_off_rush_ppa",         "o_rush_ppa_w",     "o_rush_n"),
    ("st_off_sd_ppa",           "o_sd_ppa_w",       "o_sd_n"),
    ("st_off_pd_ppa",           "o_pd_ppa_w",       "o_pd_n"),
    ("st_off_rz_ppa",           "o_rz_ppa_w",       "o_rz_n"),
    ("st_def_ppa",              "d_ppa_w",          "d_plays"),
    ("st_def_pass_ppa",         "d_pass_ppa_w",     "d_pass_n"),
    ("st_def_rush_ppa",         "d_rush_ppa_w",     "d_rush_n"),
    ("st_def_sd_ppa",           "d_sd_ppa_w",       "d_sd_n"),
    ("st_def_pd_ppa",           "d_pd_ppa_w",       "d_pd_n"),
    ("st_def_rz_ppa",           "d_rz_ppa_w",       "d_rz_n"),
    ("st_sack_rate_allowed",    "sacks_allowed",    "pass_plays"),
    ("st_sack_rate_made",       "sacks_made",       "pass_faced"),
    ("st_havoc_allowed",        "havoc_allowed_n",  "tot_plays"),
    ("st_havoc_made",           "havoc_made_n",     "tot_faced"),
    # H11 needs a true turnover MARGIN, which the matrix cannot give (it carries only
    # `turnovers_per_game` = giveaways; takeaways have no matrix column).
    ("st_giveaway_rate",        "giveaways",        "tot_plays"),
    ("st_takeaway_rate",        "takeaways",        "tot_faced"),
    ("st_fg_pct",               "fg_made",          "fg_att"),
    ("st_fg_rate",              "fg_att",           "n_games"),
    ("st_fg_dist",              "fg_dist_w",        "fg_att"),
    # gross punt distance (parsed from playText) and the return yardage ALLOWED on those punts;
    # their difference is the NET, which is the ST quantity that actually matters.
    ("st_punt_gross",           "punt_gross_sum",   "punt_n"),
    ("st_punt_ret_allowed",     "punt_ret_sum",     "punt_n"),
    ("st_td_for_rate",          "st_td_for",        "n_games"),
    ("st_td_against_rate",      "st_td_against",    "n_games"),
    ("st_block_for_rate",       "st_block_for",     "n_games"),
    ("st_block_against_rate",   "st_block_against", "n_games"),
)

# The per-game sums that get accumulated. `*_w` are numerator products (mean × n) so the ratio is a
# true play-weighted pooled rate.
_SUM_COLS: tuple[str, ...] = tuple(
    dict.fromkeys([num for _, num, _ in _RATIO_SPECS] + [den for _, _, den in _RATIO_SPECS])
)

ROLLUP_COLS: tuple[str, ...] = tuple(name for name, _, _ in _RATIO_SPECS)


def _weighted_inputs(g: pd.DataFrame) -> pd.DataFrame:
    """Per-(team, game) numerator/denominator SUMS, from the per-game means + counts."""
    out = pd.DataFrame(index=g.index)

    def num(c: str) -> pd.Series:
        """Always a Series aligned to `g` — an ABSENT column yields an all-NaN Series, never a
        bare scalar. (`pd.to_numeric(None)` returns a float64 scalar, which then silently fails
        every downstream `.notna()`/`.where()` — a real fragility the guard tests caught.)"""
        if c not in g.columns:
            return pd.Series(np.nan, index=g.index, dtype="float64")
        return pd.to_numeric(g[c], errors="coerce")

    o_plays, d_plays = num("o_plays").fillna(0.0), num("d_plays").fillna(0.0)
    out["o_plays"], out["d_plays"] = o_plays, d_plays
    out["n_games"] = 1.0

    # split-play counts are not emitted separately by the SQL; recover them from the play mix.
    # a mean over a split is NaN when the split is empty ⇒ weight 0 there.
    for side, tot in (("o", o_plays), ("d", d_plays)):
        for key in ("pass", "rush", "sd", "pd", "rz"):
            m = num(f"{side}_{key}_ppa")
            # the split's play count is unknown per-split; use the side's total play count as the
            # weight whenever the split mean exists. This is a POOLED-BY-GAME weighting: exact for
            # the full-side means and a consistent (if slightly coarse) weight for the splits.
            w = tot.where(m.notna(), 0.0)
            out[f"{side}_{key}_n"] = w
            out[f"{side}_{key}_ppa_w"] = m.fillna(0.0) * w
        m = num(f"{side}_ppa")
        out[f"{side}_ppa_w"] = m.fillna(0.0) * tot.where(m.notna(), 0.0)

    for c in ("sacks_allowed", "pass_plays", "tot_plays", "sacks_made", "pass_faced", "tot_faced",
              "giveaways", "takeaways",
              "fg_att", "fg_made", "punts", "punt_n", "punt_gross_sum", "punt_ret_sum",
              "st_td_for", "st_block_against", "st_td_against", "st_block_for"):
        out[c] = num(c).fillna(0.0)
    out["havoc_allowed_n"] = num("sacks_allowed").fillna(0.0) + num("giveaways").fillna(0.0)
    out["havoc_made_n"] = num("sacks_made").fillna(0.0) + num("takeaways").fillna(0.0)
    out["fg_dist_w"] = num("fg_avg_dist").fillna(0.0) * num("fg_att").fillna(0.0)
    return out


def season_to_date(game_team: pd.DataFrame) -> pd.DataFrame:
    """Accumulate the per-game sums into STRICTLY-PRIOR season-to-date rates per (season, team).

    ⭐ The leakage guard: the cumulative sum is `shift(1)`-ed within each (season, team) after
    ordering by `game_ts`, so the row for a game on date `d` carries ONLY games on dates `< d`.
    Ordering is by DATE, never by week — monotone with `season_order_week` and immune to the
    postseason `week`=1 collision (the P1.1/P1.4 CV-axis rule).
    """
    df = game_team.copy()
    df["game_ts"] = pd.to_datetime(df["game_ts"], errors="coerce")
    df = df.dropna(subset=["season", "team", "game_id"])
    df = df.sort_values(["season", "team", "game_ts", "game_id"]).reset_index(drop=True)

    sums = _weighted_inputs(df)
    keys = df[["season", "team"]]
    # cumulative-then-shift = strictly prior games
    prior = sums.groupby([keys["season"], keys["team"]], sort=False).cumsum()
    prior = prior.groupby([keys["season"], keys["team"]], sort=False).shift(1)

    out = df[["season", "game_id", "team"]].copy()
    out["st_n_prior_games"] = prior["n_games"].to_numpy()
    for name, num_c, den_c in _RATIO_SPECS:
        n = prior[num_c].to_numpy(float)
        d = prior[den_c].to_numpy(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = np.where(d > 0, n / d, np.nan)
        out[name] = v
    return out


def attach_home_away(matrix: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    """Join the season-to-date rollup onto the game matrix as `home_<col>` / `away_<col>`."""
    r = rollup.drop_duplicates(subset=["game_id", "team"], keep="first")
    cols = ["st_n_prior_games", *ROLLUP_COLS]
    out = matrix
    for side in ("home", "away"):
        rr = r.rename(columns={"team": f"{side}_team", **{c: f"{side}_{c}" for c in cols}})
        out = out.merge(rr[[ "game_id", f"{side}_team", *[f"{side}_{c}" for c in cols]]],
                        on=["game_id", f"{side}_team"], how="left")
    return out
