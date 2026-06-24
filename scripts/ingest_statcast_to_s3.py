"""
ingest_statcast_to_s3.py
------------------------
Fetch Statcast pitch data from Baseball Savant and write directly to S3 Parquet,
applying all column renames/casts from stg_batter_pitches.sql in Python.

This is the primary data source for the lakehouse pipeline — it replaces the
Snowflake → export_statcast_to_s3.py path:

    Baseball Savant API → ingest_statcast_to_s3.py → S3 stg_batter_pitches/
                                                    → run_w1_lakehouse.py
                                                    → S3 mart_pitch_* parquets

S3 layout (game_date sub-partitions for incremental refresh):
    s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_batter_pitches/
        year=2026/game_date=2026-06-22/part-0.parquet
        year=2026/game_date=2026-06-21/part-0.parquet
        ...

Historical years (2015-2025) remain as year-level parquets written by
export_statcast_to_s3.py. The stg_batter_pitches view reads both via
glob `**/*.parquet` with union_by_name=True.

Surrogate key (pitch_sk): SHA-256 hex of
    game_pk | at_bat_number | batter_id | pitch_number | pitcher_id | inning_half
Same composite fields as the Snowflake md5_number_upper64 key; VARCHAR not INT64.
Collision probability at 7.6M rows: effectively zero (birthday paradox needs
~1.8e38 rows for SHA-256).

Incremental detection: scans S3 game_date= sub-partitions for the max loaded date.
No Snowflake dependency for reads.

Lookback: re-fetches and overwrites the trailing 14 days on every run to absorb
late Statcast revisions (xwOBA, bat tracking, etc.).

Usage:
    python3 scripts/ingest_statcast_to_s3.py            # incremental (auto-detect)
    python3 scripts/ingest_statcast_to_s3.py --start-date 2026-06-01
    python3 scripts/ingest_statcast_to_s3.py --date 2026-06-22   # single day
    python3 scripts/ingest_statcast_to_s3.py --dry-run           # print dates, no fetch/write

Note: after the parallel-run validation period, delete the current-year full-parquet
that was written by export_statcast_to_s3.py to avoid duplicates:
    aws s3 rm s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_batter_pitches/year=2026/part-0.parquet
"""

import argparse
import hashlib
import io
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

BUCKET          = "baseball-betting-ml-artifacts"
S3_PREFIX       = "baseball/lakehouse/stg_batter_pitches"
REGION          = "us-east-2"

SAVANT_CSV_URL  = "https://baseballsavant.mlb.com/statcast_search/csv"
REQUEST_TIMEOUT = 90
REQUEST_DELAY   = 2.0
MAX_RETRIES     = 3
RETRY_BACKOFF   = 10
LOOKBACK_DAYS   = 14

SAVANT_BASE_PARAMS = {
    "all":         "true",
    "hfGT":        "R|",
    "player_type": "pitcher",
    "type":        "details",
    "min_pitches": "0",
    "min_results": "0",
    "min_pas":     "0",
    "sort_col":    "pitches",
    "sort_order":  "desc",
}


# ── Column mapping: raw Savant name → (staged name, pandas dtype) ──────────────
# Mirrors the SELECT in stg_batter_pitches.sql's renamed CTE exactly.
# Columns not listed here are dropped (new Savant fields not yet in schema).

RENAME_MAP: dict[str, tuple[str, str]] = {
    # game identifiers
    "game_pk":                                    ("game_pk",                          "Int64"),
    "game_date":                                  ("game_date",                         "str"),
    "game_year":                                  ("game_year",                         "Int64"),
    "game_type":                                  ("game_type",                         "str"),
    "home_team":                                  ("home_team",                         "str"),
    "away_team":                                  ("away_team",                         "str"),
    "inning":                                     ("inning",                            "Int64"),
    "inning_topbot":                              ("inning_half",                        "str"),
    # plate appearance context
    "at_bat_number":                              ("at_bat_number",                     "Int64"),
    "pitch_number":                               ("pitch_number",                      "Int64"),
    "balls":                                      ("balls",                             "Int64"),
    "strikes":                                    ("strikes",                           "Int64"),
    "outs_when_up":                               ("outs_when_up",                      "Int64"),
    "on_1b":                                      ("runner_on_1b_id",                   "Int64"),
    "on_2b":                                      ("runner_on_2b_id",                   "Int64"),
    "on_3b":                                      ("runner_on_3b_id",                   "Int64"),
    # players
    "batter":                                     ("batter_id",                         "Int64"),
    "pitcher":                                    ("pitcher_id",                        "Int64"),
    "player_name":                                ("player_name",                       "str"),
    "stand":                                      ("batter_hand",                       "str"),
    "p_throws":                                   ("pitcher_hand",                      "str"),
    # fielder ids
    "fielder_2":                                  ("catcher_id",                        "Int64"),
    "fielder_3":                                  ("first_base_id",                     "Int64"),
    "fielder_4":                                  ("second_base_id",                    "Int64"),
    "fielder_5":                                  ("third_base_id",                     "Int64"),
    "fielder_6":                                  ("shortstop_id",                      "Int64"),
    "fielder_7":                                  ("left_field_id",                     "Int64"),
    "fielder_8":                                  ("center_field_id",                   "Int64"),
    "fielder_9":                                  ("right_field_id",                    "Int64"),
    # pitch classification
    "pitch_type":                                 ("pitch_type",                        "str"),
    "pitch_name":                                 ("pitch_name",                        "str"),
    # pitch result
    "type":                                       ("pitch_result_code",                 "str"),
    "description":                                ("pitch_description",                 "str"),
    "events":                                     ("plate_appearance_event",            "str"),
    "des":                                        ("plate_appearance_description",      "str"),
    "zone":                                       ("pitch_zone",                        "Int64"),
    # pitch physics — release
    "release_speed":                              ("release_speed_mph",                 "float64"),
    "effective_speed":                            ("effective_speed_mph",               "float64"),
    "release_pos_x":                              ("release_pos_x_ft",                 "float64"),
    "release_pos_y":                              ("release_pos_y_ft",                 "float64"),
    "release_pos_z":                              ("release_pos_z_ft",                 "float64"),
    "release_extension":                          ("release_extension_ft",              "float64"),
    "release_spin_rate":                          ("release_spin_rate_rpm",             "Int64"),
    "spin_axis":                                  ("spin_axis_degrees",                 "Int64"),
    # pitch physics — movement & trajectory
    "pfx_x":                                      ("pitch_movement_x_ft",              "float64"),
    "pfx_z":                                      ("pitch_movement_z_ft",              "float64"),
    "plate_x":                                    ("plate_x_ft",                       "float64"),
    "plate_z":                                    ("plate_z_ft",                       "float64"),
    "sz_top":                                     ("strike_zone_top_ft",               "float64"),
    "sz_bot":                                     ("strike_zone_bot_ft",               "float64"),
    "vx0":                                        ("vx0_fps",                          "float64"),
    "vy0":                                        ("vy0_fps",                          "float64"),
    "vz0":                                        ("vz0_fps",                          "float64"),
    "ax":                                         ("ax_fps2",                          "float64"),
    "ay":                                         ("ay_fps2",                          "float64"),
    "az":                                         ("az_fps2",                          "float64"),
    "api_break_z_with_gravity":                   ("api_break_z_with_gravity_in",      "float64"),
    "api_break_x_arm":                            ("api_break_x_arm_in",               "float64"),
    "api_break_x_batter_in":                      ("api_break_x_batter_in",            "float64"),
    "arm_angle":                                  ("pitcher_arm_angle_degrees",         "float64"),
    # batted ball
    "hc_x":                                       ("hit_coord_x",                      "float64"),
    "hc_y":                                       ("hit_coord_y",                      "float64"),
    "hit_location":                               ("hit_location_fielder",              "Int64"),
    "bb_type":                                    ("batted_ball_type",                  "str"),
    "hit_distance_sc":                            ("hit_distance_ft",                  "float64"),
    "launch_speed":                               ("exit_velocity_mph",                "float64"),
    "launch_angle":                               ("launch_angle_degrees",              "float64"),
    "launch_speed_angle":                         ("launch_speed_angle_zone",           "Int64"),
    # expected / advanced metrics
    "estimated_ba_using_speedangle":              ("xba",                              "float64"),
    "estimated_woba_using_speedangle":            ("xwoba",                            "float64"),
    "estimated_slg_using_speedangle":             ("xslg",                             "float64"),
    "woba_value":                                 ("woba_value",                       "float64"),
    "woba_denom":                                 ("woba_denom",                       "float64"),
    "babip_value":                                ("babip_value",                      "float64"),
    "iso_value":                                  ("iso_value",                        "float64"),
    # win/run expectancy
    "home_win_exp":                               ("pre_pitch_home_win_exp",            "float64"),
    "bat_win_exp":                                ("pre_pitch_bat_win_exp",             "float64"),
    "delta_home_win_exp":                         ("delta_home_win_exp",               "float64"),
    "delta_run_exp":                              ("delta_run_exp",                    "float64"),
    # score context
    "home_score":                                 ("pre_pitch_home_score",              "Int64"),
    "away_score":                                 ("pre_pitch_away_score",              "Int64"),
    "bat_score":                                  ("pre_pitch_bat_score",               "Int64"),
    "fld_score":                                  ("pre_pitch_fld_score",               "Int64"),
    "post_home_score":                            ("post_pitch_home_score",             "Int64"),
    "post_away_score":                            ("post_pitch_away_score",             "Int64"),
    "post_bat_score":                             ("post_pitch_bat_score",              "Int64"),
    "post_fld_score":                             ("post_pitch_fld_score",              "Int64"),
    "home_score_diff":                            ("home_score_diff",                   "Int64"),
    "bat_score_diff":                             ("bat_score_diff",                    "Int64"),
    # bat tracking (2023+)
    "bat_speed":                                  ("bat_speed_mph",                    "float64"),
    "swing_length":                               ("swing_length_ft",                  "float64"),
    "attack_angle":                               ("attack_angle_degrees",              "float64"),
    "attack_direction":                           ("attack_direction_degrees",           "float64"),
    "swing_path_tilt":                            ("swing_path_tilt_degrees",           "float64"),
    "hyper_speed":                                ("hyper_speed",                      "float64"),
    # miss distance (2026+) — bat-to-ball whiff severity; populated only on
    # swinging_strike / swinging_strike_blocked; null on all other outcomes.
    # Candidate: E5.2 (K props) + E13.10 (matchup viz).
    "miss_distance":                              ("miss_distance",                    "float64"),
    # batter intercept (2024+)
    "intercept_ball_minus_batter_pos_x_inches":   ("intercept_offset_x_inches",        "float64"),
    "intercept_ball_minus_batter_pos_y_inches":   ("intercept_offset_y_inches",        "float64"),
    # fielding alignment
    "if_fielding_alignment":                      ("if_fielding_alignment",             "str"),
    "of_fielding_alignment":                      ("of_fielding_alignment",             "str"),
    # age & usage
    "age_pit":                                    ("pitcher_age",                       "Int64"),
    "age_bat":                                    ("batter_age",                        "Int64"),
    "age_pit_legacy":                             ("pitcher_age_legacy",                "Int64"),
    "age_bat_legacy":                             ("batter_age_legacy",                 "Int64"),
    "n_thruorder_pitcher":                        ("pitcher_times_thru_order",          "Int64"),
    "n_priorpa_thisgame_player_at_bat":           ("batter_prior_pas_this_game",        "Int64"),
    "pitcher_days_since_prev_game":               ("pitcher_days_since_prev_game",      "Int64"),
    "batter_days_since_prev_game":                ("batter_days_since_prev_game",       "float64"),
    "pitcher_days_until_next_game":               ("pitcher_days_until_next_game",      "float64"),
    "batter_days_until_next_game":                ("batter_days_until_next_game",       "float64"),
}


# ── Surrogate key ──────────────────────────────────────────────────────────────

def compute_pitch_sk(df: pd.DataFrame) -> pd.Series:
    """
    SHA-256 hex of game_pk|at_bat_number|batter_id|pitch_number|pitcher_id|inning_half.

    Same composite fields as the Snowflake md5_number_upper64 key.
    The | delimiter prevents cross-field collisions (game_pk=12,at_bat=34
    must not hash the same as game_pk=1234,at_bat=...).
    """
    def _hash(row) -> str:
        key = "|".join([
            str(int(row["game_pk"])),
            str(int(row["at_bat_number"])),
            str(int(row["batter_id"])),
            str(int(row["pitch_number"])),
            str(int(row["pitcher_id"])),
            str(row["inning_half"]) if pd.notna(row["inning_half"]) else "",
        ])
        return hashlib.sha256(key.encode()).hexdigest()

    return df.apply(_hash, axis=1)


# ── Transform: raw CSV → staged schema ────────────────────────────────────────

def transform(raw: pd.DataFrame) -> pd.DataFrame:
    """Apply column renames, type casts, and derived columns. Returns staged df."""
    keep = [c for c in raw.columns if c in RENAME_MAP]
    dropped = [c for c in raw.columns if c not in RENAME_MAP and not c.startswith("Unnamed")]
    if dropped:
        import sys
        banner = (
            "\n" + "=" * 72 + "\n"
            "ACTION NEEDED — NEW SAVANT COLUMN(S) NOT IN RENAME_MAP (S3 path):\n"
            f"  {dropped}\n"
            "  Add to RENAME_MAP in ingest_statcast_to_s3.py, then\n"
            "  add to stg_batter_pitches.sql (duckdb branch) before capturing.\n"
            + "=" * 72 + "\n"
        )
        print(banner, file=sys.stderr)
        log.warning("Dropping %d unknown column(s) not in RENAME_MAP: %s", len(dropped), dropped)

    df = raw[keep].copy()
    df.rename(columns={raw_col: staged for raw_col, (staged, _) in RENAME_MAP.items() if raw_col in df.columns}, inplace=True)

    # Cast types
    for raw_col, (staged_col, dtype) in RENAME_MAP.items():
        if staged_col not in df.columns:
            continue
        if dtype == "str":
            df[staged_col] = df[staged_col].where(df[staged_col].notna(), None).astype("object")
        elif dtype == "Int64":
            df[staged_col] = pd.to_numeric(df[staged_col], errors="coerce").astype("Int64")
        elif dtype == "float64":
            df[staged_col] = pd.to_numeric(df[staged_col], errors="coerce").astype("float64")

    # Derived: delta_pitcher_run_exp = delta_run_exp * -1
    if "delta_run_exp" in df.columns:
        df["delta_pitcher_run_exp"] = df["delta_run_exp"] * -1.0

    # Deprecated null aliases (retained for schema parity)
    for col in (
        "_deprecated_spin_dir", "_deprecated_spin_rate", "_deprecated_break_angle",
        "_deprecated_break_length", "_deprecated_tfs", "_deprecated_tfs_zulu",
        "_deprecated_umpire", "_deprecated_sv_id",
    ):
        df[col] = None

    # Surrogate key — prepend as first column to match stg_batter_pitches column order
    sk = compute_pitch_sk(df)
    df.insert(0, "pitch_sk", sk)

    return df


# ── S3 helpers ─────────────────────────────────────────────────────────────────

def make_s3_client():
    return boto3.client("s3", region_name=REGION)


def s3_key(game_date: date) -> str:
    return f"{S3_PREFIX}/year={game_date.year}/game_date={game_date}/part-0.parquet"


def get_last_loaded_date_from_s3(s3_client) -> date | None:
    """Scan S3 game_date= sub-partitions and return the most recent loaded date."""
    paginator = s3_client.get_paginator("list_objects_v2")
    max_date: date | None = None

    # List year= prefixes
    for page in paginator.paginate(Bucket=BUCKET, Prefix=S3_PREFIX + "/", Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            year_prefix = cp["Prefix"]
            # List game_date= sub-prefixes within each year
            for page2 in paginator.paginate(Bucket=BUCKET, Prefix=year_prefix, Delimiter="/"):
                for cp2 in page2.get("CommonPrefixes", []):
                    last_part = cp2["Prefix"].rstrip("/").split("/")[-1]
                    if last_part.startswith("game_date="):
                        ds = last_part[len("game_date="):]
                        try:
                            d = date.fromisoformat(ds)
                            if max_date is None or d > max_date:
                                max_date = d
                        except ValueError:
                            pass

    return max_date


def delete_day_from_s3(s3_client, game_date: date) -> None:
    """Delete all objects for a given game_date partition (before rewriting)."""
    prefix = f"{S3_PREFIX}/year={game_date.year}/game_date={game_date}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            s3_client.delete_object(Bucket=BUCKET, Key=obj["Key"])


def write_day_to_s3(s3_client, df: pd.DataFrame, game_date: date) -> None:
    """Write a single day's staged dataframe to S3 as Parquet."""
    key = s3_key(game_date)
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    log.info("  Wrote %d rows → s3://%s/%s", len(df), BUCKET, key)


# ── Savant fetch ───────────────────────────────────────────────────────────────

def fetch_day(session: requests.Session, game_date: date) -> pd.DataFrame:
    """Fetch one day from Baseball Savant. Returns empty df if no games."""
    ds = str(game_date)
    params = {
        **SAVANT_BASE_PARAMS,
        "hfSea":        f"{game_date.year}|",
        "game_date_gt": ds,
        "game_date_lt": ds,
    }
    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(SAVANT_CSV_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text or text.lower() == "null":
                return pd.DataFrame()
            df = pd.read_csv(
                io.StringIO(text),
                dtype=str,
                encoding_errors="replace",
                encoding="utf-8-sig",
            )
            df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
            df = df[df["game_pk"].notna()].copy()
            return df
        except requests.Timeout:
            log.warning("  [%d/%d] Timeout", attempt, MAX_RETRIES)
        except requests.HTTPError as exc:
            log.warning("  [%d/%d] HTTP %s", attempt, MAX_RETRIES, exc.response.status_code)
        except Exception as exc:
            log.warning("  [%d/%d] Error: %s", attempt, MAX_RETRIES, exc)
        if attempt < MAX_RETRIES:
            log.info("  Retry in %ds…", backoff)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(
        f"Savant fetch failed for {game_date} after {MAX_RETRIES} attempts (transport error)"
    )


# ── Date iteration ─────────────────────────────────────────────────────────────

def date_range(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ── Main run ───────────────────────────────────────────────────────────────────

def run(start_date: date, end_date: date, dry_run: bool = False) -> None:
    s3 = make_s3_client()
    session = requests.Session()
    session.headers.update({"User-Agent": "baseball-ingest/1.0 (research)"})

    log.info(
        "Statcast → S3 ingest  [%s → %s]  dry_run=%s",
        start_date, end_date, dry_run,
    )

    loaded = skipped = total_rows = 0
    for game_date in date_range(start_date, end_date):
        log.info("[%s] Fetching…", game_date)
        if dry_run:
            log.info("[%s]   (dry-run — skipping fetch/write)", game_date)
            continue

        raw = fetch_day(session, game_date)
        if raw.empty:
            log.info("[%s] No data — skipping", game_date)
            skipped += 1
            time.sleep(REQUEST_DELAY)
            continue

        staged = transform(raw)
        delete_day_from_s3(s3, game_date)
        write_day_to_s3(s3, staged, game_date)
        loaded += 1
        total_rows += len(staged)
        time.sleep(REQUEST_DELAY)

    log.info(
        "Done — %d day(s) written | %d skipped (no data) | %d total rows",
        loaded, skipped, total_rows,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Ingest Statcast pitch data from Baseball Savant directly to S3 Parquet."
    )
    ap.add_argument(
        "--start-date", metavar="YYYY-MM-DD",
        help="First date to ingest. Defaults to max(last S3 date) - LOOKBACK_DAYS.",
    )
    ap.add_argument(
        "--date", metavar="YYYY-MM-DD",
        help="Ingest a single date (overrides --start-date / --end-date).",
    )
    ap.add_argument(
        "--end-date", metavar="YYYY-MM-DD",
        help="Last date to ingest. Defaults to yesterday.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print the date range that would be fetched; make no S3 writes.",
    )
    args = ap.parse_args()

    yesterday = date.today() - timedelta(days=1)

    if args.date:
        start = end = date.fromisoformat(args.date)
    else:
        end = date.fromisoformat(args.end_date) if args.end_date else yesterday

        if args.start_date:
            start = date.fromisoformat(args.start_date)
        else:
            s3 = make_s3_client()
            last_loaded = get_last_loaded_date_from_s3(s3)
            if last_loaded:
                start = last_loaded - timedelta(days=LOOKBACK_DAYS)
                log.info(
                    "Last S3 date: %s → start from %s (%d-day lookback)",
                    last_loaded, start, LOOKBACK_DAYS,
                )
            else:
                # No game_date partitions yet — start from 14 days ago
                start = yesterday - timedelta(days=LOOKBACK_DAYS)
                log.info(
                    "No game_date partitions found in S3 → starting from %s", start
                )

    if start > end:
        log.info("Nothing to ingest: %s > %s", start, end)
        return

    run(start, end, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
