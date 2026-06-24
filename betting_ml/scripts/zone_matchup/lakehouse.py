"""E13.10 lakehouse layer — duckdb reads of stg_batter_pitches from S3 (NOT Snowflake).

All heavy aggregation (7.6M pitches) happens HERE in duckdb with partition pruning on game_date,
returning compact per-(entity, hand, group, cell) RAW stat frames that the pure-logic `shrink`
module then EB-shrinks. Leak discipline: every profile read takes a half-open [start, end) date
window and pitches are filtered `game_date >= start AND game_date < end` (strictly `< end`), so a
profile built "as of game G" never sees pitch from G or later.

Writes are cost-aware: profiles are tiny relative to the raw pitch table.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grid import (GridSpec, sql_group_case, sql_in, SWING_DESCRIPTIONS, WHIFF_DESCRIPTIONS)

BUCKET = "s3://baseball-betting-ml-artifacts/baseball/lakehouse"
_STG = f"{BUCKET}/stg_batter_pitches"


def connect():
    """duckdb connection with httpfs + the lakehouse S3 secret (credential chain, us-east-2)."""
    import duckdb
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute("CREATE OR REPLACE SECRET baseball_s3 "
                "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')")
    return con


def _read(years: list[int]) -> str:
    """read_parquet() first-arg for the given year partitions. We do NOT use hive_partitioning
    (partition DEPTH is inconsistent — 2015 files sit directly under year=2015/, later seasons add
    a game_date= subdir — which trips a Hive mismatch). Restricting the glob to the window's years
    still prunes most files; the `game_date` column filter (a real column) does the fine cut."""
    import datetime as _dt
    yrs = years or [_dt.date.today().year]
    globs = ", ".join(f"'{_STG}/year={y}/**/*.parquet'" for y in yrs)
    return f"[{globs}]"


@dataclass
class Window:
    """Half-open pitch window [start, end) — `end` is the leak boundary (exclusive)."""
    start: str   # 'YYYY-MM-DD' inclusive
    end: str     # 'YYYY-MM-DD' EXCLUSIVE (= the as-of date)

    @property
    def years(self) -> list[int]:
        import datetime as _dt
        y0 = _dt.date.fromisoformat(self.start).year
        # `end` is exclusive → the last day in-window is end-1.
        y1 = (_dt.date.fromisoformat(self.end) - _dt.timedelta(days=1)).year
        return list(range(y0, y1 + 1))


def _binned_cte(grid: GridSpec, src: str, window: Window, extra_cols: str) -> str:
    """Shared CTE: filter the window, normalize z, bin to (ix, iz), classify group + swing/whiff."""
    znorm = ("(plate_z_ft - strike_zone_bot_ft) / "
             "NULLIF(strike_zone_top_ft - strike_zone_bot_ft, 0)")
    return f"""
    WITH base AS (
        SELECT {extra_cols},
               plate_x_ft, {znorm} AS znorm,
               {sql_group_case('pitch_type')} AS pgroup,
               delta_run_exp, xwoba, pitch_result_code, pitch_description
        FROM read_parquet({src}, union_by_name=true, hive_partitioning=false)
        WHERE game_date >= '{window.start}' AND game_date < '{window.end}'
          AND plate_x_ft IS NOT NULL AND plate_z_ft IS NOT NULL
          AND strike_zone_top_ft > strike_zone_bot_ft
          AND pitch_type IS NOT NULL
    ),
    binned AS (
        SELECT *,
               {grid.sql_ix('plate_x_ft')} AS ix,
               {grid.sql_iz('znorm')}      AS iz,
               ({sql_in('pitch_description', SWING_DESCRIPTIONS)})::int AS is_swing,
               ({sql_in('pitch_description', WHIFF_DESCRIPTIONS)})::int AS is_whiff,
               (pitch_result_code = 'X')::int AS is_bip
        FROM base
        WHERE pgroup IS NOT NULL
    )"""


def batter_raw(con, grid: GridSpec, window: Window):
    """Raw batter per-(batter_id, vs_p_hand, pgroup, ix, iz) stats in the window.

    vs_p_hand = the handedness of the pitcher faced (so the batter map is platoon-split).
    b_hand = the batter's own stance (varies with vs_p_hand for switch hitters — correct, that's
    the stance they actually use vs that hand). Returns a DataFrame: batter_id, b_hand, vs_p_hand,
    pgroup, ix, iz, n_pitches, raw_rv (mean delta_run_exp, batter POV), n_swings, n_whiffs, n_bip,
    raw_xwoba_con (mean xwOBA on contact).
    """
    sql = _binned_cte(grid, _read(window.years), window,
                      "batter_id, batter_hand AS b_hand, pitcher_hand AS vs_p_hand") + """
    SELECT batter_id, b_hand, vs_p_hand, pgroup, ix, iz,
           count(*)                                            AS n_pitches,
           avg(delta_run_exp)                                  AS raw_rv,
           sum(is_swing)                                       AS n_swings,
           sum(is_whiff)                                       AS n_whiffs,
           sum(is_bip)                                         AS n_bip,
           avg(CASE WHEN is_bip = 1 THEN xwoba END)            AS raw_xwoba_con
    FROM binned
    WHERE batter_id IS NOT NULL AND b_hand IN ('L', 'R') AND vs_p_hand IN ('L', 'R')
    GROUP BY 1, 2, 3, 4, 5, 6
    """
    return con.execute(sql).fetchdf()


def pitcher_raw(con, grid: GridSpec, window: Window):
    """Raw pitcher per-(pitcher_id, vs_b_hand, pgroup, ix, iz) usage counts in the window.

    vs_b_hand = the handedness of the batter faced (platoon-split arsenal/location). p_hand = the
    pitcher's own throwing hand (for the cold-start league-usage fallback). loc_x/loc_znorm are the
    MEAN pitch location in the cell (the bubble position for the viz). Returns pitcher_id, p_hand,
    vs_b_hand, pgroup, ix, iz, n_pitches, loc_x, loc_znorm.
    """
    sql = _binned_cte(grid, _read(window.years), window,
                      "pitcher_id, pitcher_hand AS p_hand, batter_hand AS vs_b_hand") + """
    SELECT pitcher_id, p_hand, vs_b_hand, pgroup, ix, iz, count(*) AS n_pitches,
           avg(plate_x_ft) AS loc_x, avg(znorm) AS loc_znorm
    FROM binned
    WHERE pitcher_id IS NOT NULL AND p_hand IN ('L', 'R') AND vs_b_hand IN ('L', 'R')
    GROUP BY 1, 2, 3, 4, 5, 6
    """
    return con.execute(sql).fetchdf()


def batter_zone_bounds(con, window: Window):
    """Per-batter mean rulebook strike-zone bounds (feet) — for rendering the zone box natively.
    Returns batter_id, sz_top, sz_bot."""
    src = _read(window.years)
    sql = f"""
        SELECT batter_id, avg(strike_zone_top_ft) AS sz_top, avg(strike_zone_bot_ft) AS sz_bot
        FROM read_parquet({src}, union_by_name=true, hive_partitioning=false)
        WHERE game_date >= '{window.start}' AND game_date < '{window.end}'
          AND batter_id IS NOT NULL
          AND strike_zone_top_ft > strike_zone_bot_ft
        GROUP BY 1
    """
    return con.execute(sql).fetchdf()


def league_raw(con, grid: GridSpec, window: Window):
    """League per-(p_hand, b_hand, pgroup, ix, iz) baselines — the EB priors + cold-start map.

    Keyed by BOTH handednesses so it serves the batter prior (group/p_hand) and the pitcher
    usage prior (group/b_hand). Returns p_hand, b_hand, pgroup, ix, iz, n_pitches, lg_rv,
    n_swings, n_whiffs, lg_xwoba_con.
    """
    sql = _binned_cte(grid, _read(window.years), window,
                      "pitcher_hand AS p_hand, batter_hand AS b_hand") + """
    SELECT p_hand, b_hand, pgroup, ix, iz,
           count(*)                                 AS n_pitches,
           avg(delta_run_exp)                       AS lg_rv,
           sum(is_swing)                            AS n_swings,
           sum(is_whiff)                            AS n_whiffs,
           avg(CASE WHEN is_bip = 1 THEN xwoba END) AS lg_xwoba_con
    FROM binned
    WHERE p_hand IN ('L', 'R') AND b_hand IN ('L', 'R')
    GROUP BY 1, 2, 3, 4, 5
    """
    return con.execute(sql).fetchdf()


def lineups_and_starters(con, season: int, first_n_innings: int = 3):
    """Leak-clean per-game lineup proxy + starters for one season, from the pitch table itself.

    The starter = each side's pitcher in inning 1 (top→home pitcher faces away; bot→away pitcher).
    The lineup proxy = the distinct batters a side sends up in the first `first_n_innings`
    (≈ the 9-man card, the first time through the order — uses only WHO batted, never outcomes).
    Returns (lineups[game_pk, side, batter_id, b_hand], starters[game_pk, side, pitcher_id,
    p_hand]). `side` is the BATTING side for lineups and the PITCHER's own side for starters.
    """
    # inning_half 'Top' → away bats / home pitches; 'Bot' → home bats / away pitches.
    common = f"""
        FROM read_parquet({_read([season])}, union_by_name=true, hive_partitioning=false)
        WHERE game_year = {season} AND game_type = 'R'
    """
    lineups = con.execute(f"""
        SELECT DISTINCT game_pk,
               CASE WHEN inning_half = 'Top' THEN 'away' ELSE 'home' END AS side,
               batter_id, batter_hand AS b_hand
        {common}
          AND inning <= {first_n_innings}
          AND batter_id IS NOT NULL AND batter_hand IN ('L', 'R')
    """).fetchdf()
    starters = con.execute(f"""
        WITH p1 AS (
            SELECT game_pk,
                   CASE WHEN inning_half = 'Top' THEN 'home' ELSE 'away' END AS side,
                   pitcher_id, pitcher_hand AS p_hand,
                   row_number() OVER (
                       PARTITION BY game_pk,
                       CASE WHEN inning_half = 'Top' THEN 'home' ELSE 'away' END
                       ORDER BY at_bat_number, pitch_number) AS rn
            {common}
              AND inning = 1 AND pitcher_id IS NOT NULL AND pitcher_hand IN ('L', 'R')
        )
        SELECT game_pk, side, pitcher_id, p_hand FROM p1 WHERE rn = 1
    """).fetchdf()
    return lineups, starters
