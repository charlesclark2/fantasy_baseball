"""kdst_source.py — NF1.6 data layer for the KICKER + TEAM-DEFENSE (DST) projection universe.

The IO half of NF1.6. Every read lands one of the four frames the pure model
(`kdst_projection`) consumes, plus the PRESEASON universe each population is projected over:

  1. `load_team_defense_seasons`  — team-season DST raw counting components (sacks, INT,
     fumble recoveries, def/ST TDs, safeties, blocked kicks) from the nflverse
     `stats_team_week` Delta. 1999–2025, REG only.
  2. `load_team_points`           — team-season points FOR / AGAINST + games, and
     `load_team_game_points` the per-team-GAME points-allowed rows that the points-allowed
     DISTRIBUTION is fitted on. Both from `stg_nfl_schedules` (1999–2026 — the longest
     available spine; `dim_nfl_game`/`fct_nfl_team_game` only reach back to 2020).
  3. `load_kicker_seasons`        — kicker-season FG attempts/makes BY DISTANCE BUCKET + PAT,
     from the nflverse `stats_player_week` Delta (145 cols; the kicking block lives there and
     NOT in `fct_player_week`, which is offensive-skill only).
  4. `load_kicker_universe`       — the WEEK-1 ROSTER kicker universe for a season. This is the
     honest preseason population: it includes the camp bodies who never kick a regular-season
     ball (13.1% of week-1-rostered kickers realise ZERO fantasy points, 2006–2025), which is
     exactly the left tail an interval must price. ⭐ It is LEFT-JOINED to realized outcomes
     downstream — never inner-joined behind a games filter (NF1.9).

Plus the two FORWARD, leakage-safe environment reads both models need:
  * `load_week1_implied_points`   — each team's week-1 Vegas implied points (total/2 ± spread/2).
    Complete for every season 1999–2026, so the SAME predictor is constructible in history as
    at serve time (train/serve consistency — the predictor is never a realized-season quantity).
  * `load_schedule_opponents`     — the projection season's opponent list per team, for the
    strength-of-schedule term in the points-allowed model.

⚖️ HONEST FRAME: edge-independent (no PBO/DSR/`best_alpha`). SF-free, laptop-runnable: the raw
reads go through DuckDB `delta_scan` over the S3 sports lake (`credence-sports-lakehouse`) and the
spine/roster reads come from the already-built NFL marts DuckDB. Every lake read caches to a local
parquet so a re-run (or an offline one) is instant.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nfl.fantasy.kdst")

_ART = Path(__file__).resolve().parent / "artifacts"
_TEAM_DEF_CACHE = _ART / "kdst_team_defense_cache"
_KICKER_CACHE = _ART / "kdst_kicker_seasons_cache"

LAKE_ROOT = "s3://credence-sports-lakehouse/nfl/raw"
TEAM_WEEK_RELATION = f"delta_scan('{LAKE_ROOT}/stats_team_week')"
PLAYER_WEEK_RELATION = f"delta_scan('{LAKE_ROOT}/stats_player_week')"

MARTS_SCHEMA = "main_nfl_marts"
STAGING_SCHEMA = "main_nfl_staging"

# nflverse uses the CURRENT franchise code for 2020+ but historical rows carry the relocation
# aliases. Mirrors the `nfl_team_norm` dbt macro so every team join lands on one code space.
_TEAM_ALIASES = {"LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV"}


def norm_team(t) -> str | None:
    """Normalize an NFL team code to its canonical current franchise (`nfl_team_norm` in python)."""
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    s = str(t).strip().upper()
    if not s or s in ("NONE", "NAN"):
        return None
    return _TEAM_ALIASES.get(s, s)


def _sql_fingerprint(sql: str) -> str:
    """A short, stable digest of the QUERY TEXT, used as part of a cache filename.

    🚨 WHY THIS EXISTS (NF-C0e, 2026-08-03 — this shipped a graduated term as all-NULL to prod).
    These caches were keyed on `(lo, hi)` ALONE, so a cache file stayed valid forever no matter how
    the query changed. NF-C0e added `def_fumbles_forced` to `_TEAM_DEF_SQL`; the on-disk
    `team_defense_1999_2026.parquet` predated that edit, so the loader returned the OLD column set,
    `build_dst_training_panel` honestly SKIPPED the absent component, and `proj_def_forced_fumble`
    published 0/32 non-null — a term the story had graduated on held-out evidence, silently not
    applied.

    ⚠️ THE FAILURE IS INVISIBLE BY DESIGN, WHICH IS WHY THE KEY (NOT A WARNING) IS THE CURE. The
    absent-component path is deliberately quiet: skipping a component the history does not carry is
    the HONEST behaviour (a zero-fill would fabricate data and score as APPLIED). That correct
    fallback turns "my cache is stale" into "this league feature simply isn't available" — the same
    shape as a column that is declared everywhere and computed nowhere. A stale cache must therefore
    be impossible to READ, not merely noisy.

    ⭐ AND IT CANNOT BE CAUGHT IN A FRESH CHECKOUT: a new worktree has no `artifacts/` cache at all,
    so it rebuilds from the lake and PASSES, while a working checkout with a months-old parquet
    fails. Same class as the board-export stale-source landmine in CLAUDE.md — an on-disk artifact
    precedence bug cannot be validated where the artifact is absent.

    Digest of the SQL only: the season range stays in the filename so the cache remains readable at
    a glance, and a superseded fingerprint (including the legacy un-fingerprinted file) is pruned
    when the new one is written, so the directory cannot accumulate one parquet per historical
    edit."""
    return hashlib.sha256(" ".join(sql.split()).encode()).hexdigest()[:10]


def _read_cached_lake_query(con, sql: str, cache: Path, *, use_cache: bool, refresh: bool,
                            post) -> pd.DataFrame:
    """Run `sql` against the lake, caching to `cache` — the shared body of every cached lake read.

    One implementation so a new cached reader cannot re-introduce the stale-schema bug by copying
    the old hand-rolled read/write pair (`test_kdst_cache_invalidation.py` pins that every cached
    reader routes through here)."""
    if use_cache and not refresh and cache.exists():
        return pd.read_parquet(cache)
    _ensure_s3(con)
    df = post(con.sql(sql).df())
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
        # Drop every superseded sibling for this (reader, season-range): the legacy
        # un-fingerprinted parquet and any older fingerprint. Best-effort — a cache we failed to
        # delete is stale-but-unread, which is the safe direction.
        prefix = cache.stem.rsplit("_", 1)[0]
        for old in cache.parent.glob(f"{prefix}*.parquet"):
            if old != cache:
                try:
                    old.unlink()
                except OSError:  # noqa: PERF203 — a locked/removed file must not fail the read
                    log.warning("could not prune superseded cache file %s", old)
    return df


def _ensure_s3(con) -> None:
    """Make a plain DuckDB connection able to `delta_scan` the S3 lake (idempotent, best-effort —
    a connection that already has the extension/secret, or has no network, just proceeds).
    Mirrors `defense_source._ensure_s3` / `xfp_source._ensure_s3`."""
    for stmt in ("install delta", "load delta", "install httpfs", "load httpfs",
                 "create secret (type s3, provider credential_chain, region 'us-east-2')"):
        try:
            con.sql(stmt)
        except Exception:  # noqa: BLE001 — already loaded / secret exists / offline
            pass


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Team DEFENSE raw components (the DST stat line)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ `def_*` here are the team's OWN defense's counting stats (what its defense DID), the same
#    sign convention `stg_nfl_team_week` inherits. `fumble_recovery_opp` = recoveries of the
#    OPPONENT's fumbles, i.e. the takeaway a DST scores for (own-fumble recoveries score nothing).
#    Blocked kicks are summed across the three kick types a defense can block.
_TEAM_DEF_SQL = """
select
    season,
    team,
    count(distinct week)                                    as games,
    sum(coalesce(def_sacks, 0))::double                     as def_sacks,
    sum(coalesce(def_interceptions, 0))::double             as def_int,
    sum(coalesce(fumble_recovery_opp, 0))::double           as def_fumble_rec,
    sum(coalesce(def_tds, 0))::double                       as def_td,
    sum(coalesce(special_teams_tds, 0))::double             as st_td,
    sum(coalesce(def_safeties, 0))::double                  as def_safety,
    sum(coalesce(fg_blocked, 0) + coalesce(pat_blocked, 0)
        + coalesce(pt_blocked, 0))::double                  as def_blocked_kick,
    -- NF-C0e: `def_fumbles_forced` was in this table all along and simply never selected, so a
    -- league scoring a forced fumble had that rule CAPTURED. Distinct from `fumble_recovery_opp`
    -- (`def_fumble_rec`): a defense can force a fumble the OFFENSE recovers, and many leagues pay
    -- for both events separately.
    sum(coalesce(def_fumbles_forced, 0))::double            as def_forced_fumble
from {team_week}
where season_type = 'REG'
  and season between {lo} and {hi}
  and team is not null
group by 1, 2
"""


def load_team_defense_seasons(con, lo: int, hi: int, *,
                              relation: str = TEAM_WEEK_RELATION,
                              cache_dir: Path = _TEAM_DEF_CACHE,
                              use_cache: bool = True, refresh: bool = False) -> pd.DataFrame:
    """Team-season DST raw components for seasons `lo..hi` (REG only), one row per (season, team)."""
    sql = _TEAM_DEF_SQL.format(team_week=relation, lo=int(lo), hi=int(hi))
    cache = cache_dir / f"team_defense_{lo}_{hi}_{_sql_fingerprint(sql)}.parquet"

    def _post(df: pd.DataFrame) -> pd.DataFrame:
        df["team"] = df["team"].map(norm_team)
        return df.dropna(subset=["team"]).reset_index(drop=True)

    df = _read_cached_lake_query(con, sql, cache, use_cache=use_cache, refresh=refresh, post=_post)
    log.info("team defense seasons %d–%d: %d team-seasons", lo, hi, len(df))
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Team POINTS (for / against) — the scoring environment + the DST points-allowed target
# ══════════════════════════════════════════════════════════════════════════════════════════════
# `stg_nfl_schedules` is the spine because it is the ONLY table covering 1999–2026 (both the full
# history the regressions are fitted on AND the projection season's forward schedule).
_TEAM_GAME_POINTS_SQL = """
with sides as (
    select season, week, home_team as team, home_score as points_for, away_score as points_against
    from {staging}.stg_nfl_schedules
    where is_regular_season and home_score is not null and away_score is not null
    union all
    select season, week, away_team as team, away_score as points_for, home_score as points_against
    from {staging}.stg_nfl_schedules
    where is_regular_season and home_score is not null and away_score is not null
)
select season, week, team, points_for::double as points_for, points_against::double as points_against
from sides
where season between {lo} and {hi}
"""


def load_team_game_points(con, lo: int, hi: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """One row per completed REG (season, week, team) with that team's points for / against.

    The per-GAME grain matters: DST points-allowed scoring is applied PER GAME under a tier table,
    so the season projection needs a per-game points-allowed DISTRIBUTION, not just its mean."""
    df = con.sql(_TEAM_GAME_POINTS_SQL.format(staging=staging, lo=int(lo), hi=int(hi))).df()
    df["team"] = df["team"].map(norm_team)
    return df.dropna(subset=["team"]).reset_index(drop=True)


def load_team_points(con, lo: int, hi: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """Team-season aggregate of `load_team_game_points`: games, points_for/against + per-game rates."""
    g = load_team_game_points(con, lo, hi, staging=staging)
    ts = (g.groupby(["season", "team"], as_index=False)
            .agg(team_games=("points_for", "size"),
                 points_for=("points_for", "sum"),
                 points_against=("points_against", "sum")))
    ts["points_for_pg"] = ts["points_for"] / ts["team_games"]
    ts["points_against_pg"] = ts["points_against"] / ts["team_games"]
    return ts


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2b. Team YARDS ALLOWED — NF-C0e's tier family (the points-allowed twin)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# A team's yards ALLOWED in a game is its OPPONENT's total offense, so the frame is built by
# joining `stg_nfl_team_week` to itself through `opponent_team`.
#
# ⭐⭐ THE ONE THING THAT IS EASY TO GET WRONG HERE: `total_yards` IS **GROSS**, AND THE FANTASY
# PLATFORMS SCORE **NET**. nflverse's team `passing_yards` is gross passing yards and
# `total_yards` is exactly `passing_yards + rushing_yards` (verified: the identity holds on all
# 13,912 team-games). The NFL's official "total net yards" — which is the number in the box score
# that ESPN and Sleeper grade a D/ST on — SUBTRACTS sack yardage. Using the gross column would
# overstate every defense by ~15 yards/game and push the whole league up roughly one tier rung.
# Validated against published league averages: NET gives 331.6 yards/g in 2023 against the NFL's
# published 331.1, while GROSS gives 349.0. `sack_yards_lost` is stored NEGATIVE, hence the ADD.
_TEAM_GAME_YARDS_SQL = """
with tw as (
    select season, week, team, opponent_team,
           coalesce(passing_yards, 0)::double   as pass_yds,
           coalesce(rushing_yards, 0)::double   as rush_yds,
           coalesce(sack_yards_lost, 0)::double as sack_yds
    from {staging}.stg_nfl_team_week
    where season_type = 'REG' and team is not null and opponent_team is not null
      and season between {lo} and {hi}
)
select season, week,
       opponent_team                          as team,      -- the DEFENSE
       (pass_yds + rush_yds + sack_yds)       as yards_against
from tw
"""


def load_team_game_yards(con, lo: int, hi: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """One row per REG (season, week, team) with that team's NET yards ALLOWED.

    The per-GAME grain is required for the same reason points allowed needs it: yards-allowed
    scoring is a per-game TIER table, so the season projection needs a DISTRIBUTION, not a mean."""
    df = con.sql(_TEAM_GAME_YARDS_SQL.format(staging=staging, lo=int(lo), hi=int(hi))).df()
    df["team"] = df["team"].map(norm_team)
    return df.dropna(subset=["team"]).reset_index(drop=True)


def load_team_yards(con, lo: int, hi: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """Team-season aggregate of `load_team_game_yards`: games, yards_against + the per-game rate."""
    g = load_team_game_yards(con, lo, hi, staging=staging)
    ts = (g.groupby(["season", "team"], as_index=False)
            .agg(team_games=("yards_against", "size"), yards_against=("yards_against", "sum")))
    ts["yards_against_pg"] = ts["yards_against"] / ts["team_games"]
    return ts


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. KICKER stat lines (FG by distance bucket + PAT)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ The kicking block lives in the raw `stats_player_week` Delta (145 cols) — NOT in
#    `fct_player_week`, which conforms the OFFENSIVE-SKILL line only. nflverse splits FG
#    made/missed into 0-19 / 20-29 / 30-39 / 40-49 / 50-59 / 60+; `fg_blocked` is counted
#    separately from `fg_missed` (a blocked kick is neither made nor "missed" in the buckets),
#    so attempts are reconstructed as made + missed + blocked.
_KICKER_SQL = """
select
    season,
    player_id,
    max(player_name)                                        as player_name,
    max(team)                                               as team,
    count(distinct week)                                    as games,
    sum(coalesce(fg_att, 0))::double                        as fg_att,
    sum(coalesce(fg_made, 0))::double                       as fg_made,
    sum(coalesce(fg_blocked, 0))::double                    as fg_blocked,
    sum(coalesce(fg_made_0_19, 0) + coalesce(fg_made_20_29, 0)
        + coalesce(fg_made_30_39, 0))::double               as fg_made_0_39,
    sum(coalesce(fg_made_40_49, 0))::double                 as fg_made_40_49,
    sum(coalesce(fg_made_50_59, 0) + coalesce(fg_made_60_, 0))::double as fg_made_50_plus,
    sum(coalesce(fg_missed_0_19, 0) + coalesce(fg_missed_20_29, 0)
        + coalesce(fg_missed_30_39, 0))::double             as fg_missed_0_39,
    sum(coalesce(fg_missed_40_49, 0))::double               as fg_missed_40_49,
    sum(coalesce(fg_missed_50_59, 0) + coalesce(fg_missed_60_, 0))::double as fg_missed_50_plus,
    sum(coalesce(pat_att, 0))::double                       as pat_att,
    sum(coalesce(pat_made, 0))::double                      as pat_made
from {player_week}
where season_type = 'REG'
  and position = 'K'
  and season between {lo} and {hi}
  and player_id is not null
group by 1, 2
"""


def load_kicker_seasons(con, lo: int, hi: int, *,
                        relation: str = PLAYER_WEEK_RELATION,
                        cache_dir: Path = _KICKER_CACHE,
                        use_cache: bool = True, refresh: bool = False) -> pd.DataFrame:
    """Kicker-season FG (by distance bucket) + PAT lines for seasons `lo..hi` (REG only)."""
    sql = _KICKER_SQL.format(player_week=relation, lo=int(lo), hi=int(hi))
    cache = cache_dir / f"kicker_seasons_{lo}_{hi}_{_sql_fingerprint(sql)}.parquet"

    def _post(df: pd.DataFrame) -> pd.DataFrame:
        df["team"] = df["team"].map(norm_team)
        return df

    df = _read_cached_lake_query(con, sql, cache, use_cache=use_cache, refresh=refresh, post=_post)
    log.info("kicker seasons %d–%d: %d kicker-seasons", lo, hi, len(df))
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The PRESEASON universes
# ══════════════════════════════════════════════════════════════════════════════════════════════
_KICKER_UNIVERSE_SQL = """
select
    season,
    player_id,
    any_value(player_name)      as player_name,
    any_value(team)             as team,
    any_value(status)           as status,
    max(years_exp)              as years_exp
from {staging}.stg_nfl_weekly_rosters
where position = 'K'
  and week = 1
  and season = {season}
  and player_id is not null
group by 1, 2
"""


def load_kicker_universe(con, season: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """The WEEK-1 ROSTER kicker universe for `season` — the honest preseason population.

    ⚠️ This deliberately includes the camp bodies and the non-ACT designations. 13.1% of
    week-1-rostered kickers (2006–2025) realise ZERO regular-season fantasy points, and a band
    that never sees that population cannot price its own left tail (NF1.9). For a not-yet-started
    season the week-1 snapshot IS the current offseason roster (the same leakage-safe convention
    `run_season_projection.load_forward_roster_status` uses)."""
    df = con.sql(_KICKER_UNIVERSE_SQL.format(staging=staging, season=int(season))).df()
    df["team"] = df["team"].map(norm_team)
    df["status"] = df["status"].fillna("").astype(str).str.upper()
    return df.dropna(subset=["team"]).reset_index(drop=True)


def load_dst_universe(con, season: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """The DST universe for `season` — every team on that season's regular-season schedule, with
    its scheduled game count. Complete by construction (32 teams), so unlike the kicker universe
    it has no absence class."""
    df = con.sql(f"""
        with sides as (
            select season, home_team as team, away_team as opponent
            from {staging}.stg_nfl_schedules where is_regular_season and season = {int(season)}
            union all
            select season, away_team as team, home_team as opponent
            from {staging}.stg_nfl_schedules where is_regular_season and season = {int(season)}
        )
        select season, team, count(*) as scheduled_games from sides group by 1, 2
    """).df()
    df["team"] = df["team"].map(norm_team)
    return df.dropna(subset=["team"]).reset_index(drop=True)


def load_schedule_opponents(con, season: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """One row per (team, opponent) matchup on `season`'s regular-season schedule — the input to
    the strength-of-schedule term in the points-allowed model (a defense that faces the league's
    best offenses allows more, independent of its own quality)."""
    df = con.sql(f"""
        select season, home_team as team, away_team as opponent
        from {staging}.stg_nfl_schedules where is_regular_season and season = {int(season)}
        union all
        select season, away_team as team, home_team as opponent
        from {staging}.stg_nfl_schedules where is_regular_season and season = {int(season)}
    """).df()
    df["team"] = df["team"].map(norm_team)
    df["opponent"] = df["opponent"].map(norm_team)
    return df.dropna(subset=["team", "opponent"]).reset_index(drop=True)


def load_week1_implied_points(con, season: int, *, staging: str = STAGING_SCHEMA) -> pd.DataFrame:
    """Each team's WEEK-1 Vegas implied points for `season` → `DataFrame[team, implied_points]`.

    implied = total/2 ± spread/2 (home +, away −), i.e. the market's forward read on the team's
    scoring environment, set BEFORE any of the season's games are played. ⭐ Complete for every
    season 1999–2026, which is what makes it a train/serve-CONSISTENT predictor: the historical
    regressions are fitted on the same forward quantity that will be available at serve time,
    never on a realized-season total the projection cannot see."""
    df = con.sql(f"""
        with e as (
            select home_team as team, (total_line / 2.0 + spread_line / 2.0) as ip
            from {staging}.stg_nfl_schedules
            where is_regular_season and week = 1 and season = {int(season)}
              and total_line is not null and spread_line is not null
            union all
            select away_team as team, (total_line / 2.0 - spread_line / 2.0) as ip
            from {staging}.stg_nfl_schedules
            where is_regular_season and week = 1 and season = {int(season)}
              and total_line is not null and spread_line is not null
        )
        select team, avg(ip) as implied_points from e group by 1
    """).df()
    df["team"] = df["team"].map(norm_team)
    return df.dropna(subset=["team"]).reset_index(drop=True)
