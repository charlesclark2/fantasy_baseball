"""injury_log_source.py — NF3.3: per-player weekly injury-REPORT history + a games-missed
participation summary, for the player-page History panel.

Both reads are DISPLAY-ONLY realized history (never a model input, so there is no leakage concern —
see `season_projection.py`'s roster-status cap for the FORWARD-looking availability signal, which is
a separate, already-shipped mechanism this module does not touch or duplicate):

  load_injury_reports(con, seasons, schema=STAGING_SCHEMA) — one row per (player, season, week) the
    nflverse `injuries` feed carries a report OR practice designation for (already ingested; N0.2 /
    `stg_nfl_injuries`, 2009+, weekly in-season cadence). This is the WEEKLY GAME-REPORT status
    (Out/Doubtful/Questionable, practice participation) — genuinely different from
    `sleeper_injuries_source.py`'s current-snapshot LONG-ABSENCE tag (PUP/IR/NFI/SUS), which this
    module does not read.

  load_games_missed(con, seasons, schema=MARTS_SCHEMA) — one row per (player, season): how many of
    his team's non-bye games he did NOT record a snap/box-score line for, from `fct_player_week`'s
    `played_flag`/`is_bye` (already ingested; N0.3). ⚠️ HONEST FRAMING: this counts a game the player
    didn't play FOR ANY REASON (injury, healthy scratch, benching, roster move) — it is a
    participation count, not an injury-attributed one. It is never merged with the report-status rows
    into a single "games missed to injury" number; the UI presents the two side by side and lets the
    weekly report speak for causation where one exists.
"""
from __future__ import annotations

import pandas as pd

STAGING_SCHEMA = "main_nfl_staging"
MARTS_SCHEMA = "main_nfl_marts"

INJURY_REPORT_COLS = [
    "player_id", "season", "week",
    "report_status", "report_primary_injury", "practice_status", "date_modified",
]
GAMES_MISSED_COLS = ["player_id", "season", "games_on_roster", "games_missed"]


def load_injury_reports(con, seasons, schema: str = STAGING_SCHEMA) -> pd.DataFrame:
    """Weekly report/practice designations for every season in `seasons`. A row is included when
    EITHER the game-report status or the practice status is non-null (nflverse's `injuries` feed only
    lists players who appeared on a report at all, so this is a light extra filter, not the main
    one). Empty (with the columns) for an empty `seasons`."""
    seasons = sorted({int(s) for s in seasons})
    if not seasons:
        return pd.DataFrame(columns=INJURY_REPORT_COLS)
    season_list = ",".join(str(s) for s in seasons)
    df = con.sql(f"""
        select
            gsis_id as player_id, season, week,
            report_status, report_primary_injury, practice_status, date_modified
        from {schema}.stg_nfl_injuries
        where season in ({season_list})
          and (report_status is not null or practice_status is not null)
        order by season, week
    """).df()
    if df.empty:
        return pd.DataFrame(columns=INJURY_REPORT_COLS)
    df["player_id"] = df["player_id"].astype(str)
    return df[INJURY_REPORT_COLS]


def load_games_missed(con, seasons, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Per (player, season): `games_on_roster` (non-bye team-weeks he's in the fact table for) vs
    `games_missed` (of those, how many carry `played_flag=false`). Empty (with the columns) for an
    empty `seasons`."""
    seasons = sorted({int(s) for s in seasons})
    if not seasons:
        return pd.DataFrame(columns=GAMES_MISSED_COLS)
    season_list = ",".join(str(s) for s in seasons)
    df = con.sql(f"""
        select
            player_id, season,
            count_if(not is_bye)                    as games_on_roster,
            count_if(not is_bye and not played_flag) as games_missed
        from {schema}.fct_player_week
        where season in ({season_list}) and week > 0
        group by 1, 2
    """).df()
    if df.empty:
        return pd.DataFrame(columns=GAMES_MISSED_COLS)
    df["player_id"] = df["player_id"].astype(str)
    return df[GAMES_MISSED_COLS]


def injury_records(df: pd.DataFrame) -> dict[str, list[dict]]:
    """`load_injury_reports` output -> `{player_id: [weekly record, ...]}`, display-ready (camelCase,
    JSON-null-safe). Grouped here (not left to the caller) so `export_player_history_json.py` and any
    future consumer group identically."""
    out: dict[str, list[dict]] = {}
    if df.empty:
        return out
    for pid, grp in df.groupby("player_id"):
        out[str(pid)] = [
            {
                "season": int(r["season"]),
                "week": int(r["week"]),
                "reportStatus": None if pd.isna(r["report_status"]) else str(r["report_status"]),
                "reportPrimaryInjury": (
                    None if pd.isna(r["report_primary_injury"]) else str(r["report_primary_injury"])
                ),
                "practiceStatus": None if pd.isna(r["practice_status"]) else str(r["practice_status"]),
                "dateModified": None if pd.isna(r["date_modified"]) else str(r["date_modified"]),
            }
            for _, r in grp.iterrows()
        ]
    return out


def games_missed_records(df: pd.DataFrame) -> dict[str, list[dict]]:
    """`load_games_missed` output -> `{player_id: [{season, gamesOnRoster, gamesMissed}, ...]}`."""
    out: dict[str, list[dict]] = {}
    if df.empty:
        return out
    for pid, grp in df.groupby("player_id"):
        out[str(pid)] = [
            {
                "season": int(r["season"]),
                "gamesOnRoster": int(r["games_on_roster"]),
                "gamesMissed": int(r["games_missed"]),
            }
            for _, r in grp.sort_values("season").iterrows()
        ]
    return out
