"""Compute and persist MLB Elo ratings for all teams from 2015 onward.

Elo parameters (FiveThirtyEight MLB standard):
  - Initial rating: 1500
  - K-factor: 4 per game
  - Home field advantage: HOME_ADV = 24 Elo points
  - Season-start regression: team_elo = 0.667 * team_elo + 0.333 * 1500

Output table: baseball_data.betting.team_elo_history
  game_pk, game_date, team_abbrev, elo_before_game, elo_after_game

Only elo_before_game is used as a pre-game feature — elo_after_game
captures post-game state for rolling updates only.

⭐ E11.24 (literal-zero Snowflake) — the SF-FREE branch, gated `E11_24_ELO_SF_FREE=1`.
    WHY THIS SCRIPT: the 2026-07-29 wake census attributed **14% of all remaining COMPUTE_WH
    resumes (6/44 on 7/28)** to this script's `CREATE TABLE IF NOT EXISTS … team_elo_history`
    — a pure NO-OP DDL against an already-existing table, the exact shape of the retired
    `mlb_odds_raw` bridge. The hourly CALLER is `statcast_catchup_job`, re-fired by
    `statcast_freshness_sensor` once an hour from 04:00 ET until yesterday's Statcast lands
    (hourly `run_key`) — so on a normal morning the whole chain, this script included, runs
    ~6× and 5 of those runs can change nothing.
    Under the flag this script opens NO Snowflake connection at all: it reads
    `mart_game_results` from the S3 lakehouse via DuckDB and writes `team_elo_history`
    straight to the lakehouse parquet key.

    🚨 INC-31 WRITER-UNIQUENESS: the S3 key `baseball/lakehouse/team_elo_history/data.parquet`
    was written by TWO `SELECT *` Snowflake mirrors (`export_w8a_precursors_to_s3.py` and
    `export_features_to_s3.py`). Both SKIP the table under this flag — a retired mirror still
    writing a cut-over key is precisely the INC-31 clobber (and, because those mirrors preserve
    Snowflake's UPPERCASE identifiers, a lowercase native write would ALSO have flipped the
    column case under the readers). Hence `_LAKEHOUSE_COLUMNS` below pins the UPPERCASE
    contract the existing parquet already carries.

Usage:
  uv run python betting_ml/scripts/compute_elo.py [--start-year 2015] [--end-year 2025]
  uv run python betting_ml/scripts/compute_elo.py --dry-run
  uv run python betting_ml/scripts/compute_elo.py --check
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from typing import Any

INITIAL_ELO: float = 1500.0
K: float = 4.0
HOME_ADV: float = 24.0
REGRESSION_WEIGHT: float = 1.0 / 3.0  # fraction pulled back toward mean each season

_KEY_PATH = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH") or os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

# ── E11.24 literal-zero-Snowflake lever ────────────────────────────────────────────────
_SF_FREE_ENV = "E11_24_ELO_SF_FREE"

# The lakehouse home of team_elo_history. Kept in one place so the reader glob
# (betting_ml.utils.lakehouse_monitor.lh) and this writer can never drift apart.
_LAKEHOUSE_KEY = "team_elo_history"

# ⚠️ UPPERCASE ON PURPOSE — the existing parquet was written by a Snowflake `SELECT *` mirror
# that preserves Snowflake's UPPERCASE identifiers, and the Snowflake external table addresses
# columns as CASE-SENSITIVE `VALUE:<KEY>`. Emitting lowercase here would make every column read
# NULL through the ext table while DuckDB (case-insensitive) stayed green — the silent
# `VALUE:<key>` landmine. (name, DuckDB type) in the parquet's own column order.
_LAKEHOUSE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("GAME_PK", "BIGINT"),
    ("GAME_DATE", "DATE"),
    ("TEAM_ABBREV", "VARCHAR"),
    ("ELO_BEFORE_GAME", "DOUBLE"),
    ("ELO_AFTER_GAME", "DOUBLE"),
)


def sf_free() -> bool:
    """True when this run must never touch Snowflake (E11.24 cutover lever)."""
    return os.environ.get(_SF_FREE_ENV, "0").strip() == "1"


_DDL = """
CREATE TABLE IF NOT EXISTS baseball_data.betting.team_elo_history (
    game_pk         INTEGER NOT NULL,
    game_date       DATE    NOT NULL,
    team_abbrev     VARCHAR(10) NOT NULL,
    elo_before_game FLOAT   NOT NULL,
    elo_after_game  FLOAT   NOT NULL,
    PRIMARY KEY (game_pk, team_abbrev)
)
"""

_GAMES_QUERY = """
SELECT
    game_pk,
    game_date,
    game_year,
    home_team,
    away_team,
    home_team_won
FROM baseball_data.betting.mart_game_results
WHERE game_type = 'R'
  AND game_year >= {start_year}
  AND game_year <= {end_year}
  AND home_team_won IS NOT NULL
ORDER BY game_date ASC, game_pk ASC
"""

_MERGE_SQL = """
MERGE INTO baseball_data.betting.team_elo_history AS tgt
USING (
    SELECT
        v.game_pk::INTEGER     AS game_pk,
        v.game_date::DATE      AS game_date,
        v.team_abbrev          AS team_abbrev,
        v.elo_before::FLOAT    AS elo_before_game,
        v.elo_after::FLOAT     AS elo_after_game
    FROM (VALUES {placeholders}) AS v(game_pk, game_date, team_abbrev, elo_before, elo_after)
) AS src
ON tgt.game_pk = src.game_pk AND tgt.team_abbrev = src.team_abbrev
WHEN MATCHED THEN UPDATE SET
    game_date       = src.game_date,
    elo_before_game = src.elo_before_game,
    elo_after_game  = src.elo_after_game
WHEN NOT MATCHED THEN INSERT (game_pk, game_date, team_abbrev, elo_before_game, elo_after_game)
VALUES (src.game_pk, src.game_date, src.team_abbrev, src.elo_before_game, src.elo_after_game)
"""


def _connect():
    # Lazy import so the SF-FREE branch never even loads the Snowflake connector.
    import snowflake.connector
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    with open(_KEY_PATH, "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "IHUPICS-DP59975"),
        user=os.environ.get("SNOWFLAKE_USER", "dbt_rw"),
        private_key=pkb,
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
    )


def _expected_home(home_elo: float, away_elo: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((away_elo - home_elo - HOME_ADV) / 400.0))


def _apply_season_regression(ratings: dict[str, float]) -> dict[str, float]:
    return {
        team: (1.0 - REGRESSION_WEIGHT) * elo + REGRESSION_WEIGHT * INITIAL_ELO
        for team, elo in ratings.items()
    }


def compute_elo(
    games: list[dict[str, Any]],
) -> list[tuple[int, date, str, float, float]]:
    """Process games in chronological order, return list of (game_pk, game_date, team, before, after) rows."""
    ratings: dict[str, float] = {}
    current_season: int | None = None
    records: list[tuple[int, date, str, float, float]] = []

    for game in games:
        game_year = int(game["GAME_YEAR"])
        game_pk = int(game["GAME_PK"])
        game_date = game["GAME_DATE"]
        home_team: str = game["HOME_TEAM"]
        away_team: str = game["AWAY_TEAM"]
        home_won: bool = bool(game["HOME_TEAM_WON"])

        # Season regression at the first game of each new season
        if current_season is not None and game_year != current_season:
            ratings = _apply_season_regression(ratings)
        current_season = game_year

        # Initialize new teams at 1500
        if home_team not in ratings:
            ratings[home_team] = INITIAL_ELO
        if away_team not in ratings:
            ratings[away_team] = INITIAL_ELO

        home_before = ratings[home_team]
        away_before = ratings[away_team]

        exp_home = _expected_home(home_before, away_before)
        home_result = 1.0 if home_won else 0.0

        home_after = home_before + K * (home_result - exp_home)
        away_after = away_before + K * ((1.0 - home_result) - (1.0 - exp_home))

        ratings[home_team] = home_after
        ratings[away_team] = away_after

        records.append((game_pk, game_date, home_team, home_before, home_after))
        records.append((game_pk, game_date, away_team, away_before, away_after))

    return records


def load_games_from_lakehouse(start_year: int, end_year: int) -> list[dict[str, Any]]:
    """E11.24 SF-FREE read: `mart_game_results` from the S3 lakehouse via DuckDB.

    Returns rows keyed EXACTLY like the Snowflake DictCursor did (UPPERCASE), so
    `compute_elo()` — the pure Elo kernel — is byte-identical across both branches and the
    two paths cannot silently diverge.

    Routed through `register_lakehouse_views` rather than a hardcoded `read_parquet` glob:
    a hardcoded glob is what broke the daily job on 2026-07-20 when phase-1.5 deleted the
    legacy parquet layout out from under it (grep the PATH, not the table name).
    """
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    try:
        register_lakehouse_views(conn, ["mart_game_results"])
        cur = conn.execute(
            """
            SELECT game_pk   AS "GAME_PK",
                   game_date AS "GAME_DATE",
                   game_year AS "GAME_YEAR",
                   home_team AS "HOME_TEAM",
                   away_team AS "AWAY_TEAM",
                   home_team_won AS "HOME_TEAM_WON"
            FROM mart_game_results
            WHERE game_type = 'R'
              AND game_year >= ?
              AND game_year <= ?
              AND home_team_won IS NOT NULL
            ORDER BY game_date ASC, game_pk ASC
            """,
            [start_year, end_year],
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def write_to_lakehouse(records: list[tuple[int, date, str, float, float]]) -> int:
    """E11.24 SF-FREE write: overwrite the single `team_elo_history` lakehouse parquet.

    A FULL overwrite is the value-identical replacement for the Snowflake MERGE: this script
    always recomputes every season from `--start-year` forward, so the MERGE never had a
    partial-update semantic to preserve. One object at the existing `data.parquet` key keeps
    the `**/*.parquet` reader glob single-file (no glob-dup) and keeps the write atomic from a
    reader's point of view.

    DuckDB `COPY` is used deliberately: it authenticates through the S3 `credential_chain`,
    so the EC2 instance role resolves and there is no `aws_access_key_id=os.environ.get(...)`
    AKID footgun.
    """
    from betting_ml.utils.lakehouse_monitor import LAKEHOUSE, duck

    target = f"{LAKEHOUSE}/{_LAKEHOUSE_KEY}/data.parquet"
    ddl_cols = ", ".join(f'"{name}" {typ}' for name, typ in _LAKEHOUSE_COLUMNS)
    placeholders = ", ".join("?" for _ in _LAKEHOUSE_COLUMNS)

    conn = duck()
    try:
        conn.execute(f"CREATE OR REPLACE TEMP TABLE elo_out ({ddl_cols})")
        conn.executemany(f"INSERT INTO elo_out VALUES ({placeholders})", records)
        (staged,) = conn.execute("SELECT COUNT(*) FROM elo_out").fetchone()
        if int(staged) != len(records):
            raise RuntimeError(
                f"staged {staged:,} rows but computed {len(records):,} — refusing to publish a "
                f"partial team_elo_history (a short write silently degrades every elo feature)."
            )
        conn.execute(
            f"COPY (SELECT * FROM elo_out) TO '{target}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE 1)"
        )
    finally:
        conn.close()
    print(f"  wrote {len(records):,} rows → {target}")
    return len(records)


def _write_to_snowflake(
    conn,
    records: list[tuple[int, date, str, float, float]],
    batch_size: int = 500,
) -> int:
    cur = conn.cursor()
    cur.execute(_DDL)

    total_written = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        placeholders = ", ".join(
            f"({r[0]}, '{r[1]}', '{r[2]}', {r[3]:.4f}, {r[4]:.4f})"
            for r in batch
        )
        cur.execute(_MERGE_SQL.format(placeholders=placeholders))
        total_written += len(batch)
        print(f"  Written {total_written:,} / {len(records):,} rows...", end="\r")

    print()
    cur.close()
    return total_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute and persist MLB Elo ratings")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print last 20 Elo updates without writing to Snowflake",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print top 5 and bottom 5 teams by Elo at end of the most recent season",
    )
    args = parser.parse_args()

    lakehouse = sf_free()
    conn = None
    if lakehouse:
        print(f"[{_SF_FREE_ENV}=1] Snowflake-FREE run — S3 lakehouse via DuckDB.")
    else:
        print("Connecting to Snowflake...")
        conn = _connect()

    try:
        print(f"Loading games {args.start_year}–{args.end_year} from mart_game_results...")
        if lakehouse:
            games = load_games_from_lakehouse(args.start_year, args.end_year)
        else:
            import snowflake.connector

            cur = conn.cursor(snowflake.connector.DictCursor)
            cur.execute(
                _GAMES_QUERY.format(start_year=args.start_year, end_year=args.end_year)
            )
            games = cur.fetchall()
            cur.close()
        print(f"  {len(games):,} games loaded")

        if not games:
            print("No games found — check start/end year parameters.")
            return

        print("Computing Elo ratings...")
        records = compute_elo(games)
        print(f"  {len(records):,} team-game rows computed")

        if args.dry_run:
            print("\n--- Last 20 Elo updates (dry run, not written) ---")
            for r in records[-20:]:
                print(
                    f"  game_pk={r[0]}  date={r[1]}  team={r[2]:<4}  "
                    f"before={r[3]:.1f}  after={r[4]:.1f}  "
                    f"delta={r[4]-r[3]:+.1f}"
                )
            return

        if args.check:
            # Build final ratings from most recent season in the records
            final_ratings: dict[str, float] = {}
            most_recent_year = max(int(g["GAME_YEAR"]) for g in games)
            for r in records:
                # r = (game_pk, game_date, team, before, after)
                year = r[1].year if hasattr(r[1], "year") else int(str(r[1])[:4])
                if year == most_recent_year:
                    final_ratings[r[2]] = r[4]  # elo_after_game

            sorted_teams = sorted(final_ratings.items(), key=lambda x: x[1], reverse=True)
            print(f"\n--- End-of-{most_recent_year} Elo ratings ---")
            print("Top 5:")
            for team, elo in sorted_teams[:5]:
                print(f"  {team:<4}  {elo:.1f}")
            print("Bottom 5:")
            for team, elo in sorted_teams[-5:]:
                print(f"  {team:<4}  {elo:.1f}")
            return

        if lakehouse:
            print(f"Writing {len(records):,} rows to the S3 lakehouse team_elo_history...")
            written = write_to_lakehouse(records)
        else:
            print(f"Writing {len(records):,} rows to baseball_data.betting.team_elo_history...")
            written = _write_to_snowflake(conn, records)
        print(f"Done. {written:,} rows written.")

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
