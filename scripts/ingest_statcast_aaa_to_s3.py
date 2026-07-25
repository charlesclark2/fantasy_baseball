"""
ingest_statcast_aaa_to_s3.py   (E7.2 — AAA Statcast ingestion (Hawk-Eye) → S3 Delta lakehouse)
------------------------------------------------------------------------------------------------
Land AAA (Triple-A) Statcast/Hawk-Eye data as a level-tagged Delta table alongside E7.1's MiLB
tables (SF-FREE, instance-role S3 auth):

    baseball/milb/statcast_aaa   — one row per (player_id, game_pk, player_type)

⭐ API reality (probed LIVE 2026-07-25, not coded to docs — the E7/P0.1/N0.x discipline):
  • There is NO public pitch-level ("raw event") Statcast export for the minors. The main MLB
    endpoint (baseballsavant.mlb.com/statcast_search/csv, `type=details`) silently ignores any
    minor-league filter and always returns MLB rows. The real minors surface is a SEPARATE tool,
    baseballsavant.mlb.com/statcast-search-minors, which is an AGGREGATE LEADERBOARD builder
    (its own `group_by` dropdown offers Player/Player&Game/Player&Month/.../Level/Org — never a
    "one row per pitch" option). So a literal pitch-level schema match to MLB's `stg_batter_pitches`
    is NOT achievable from this public source — this is exactly the "probe live before assuming a
    shape" outcome the story called for, documented here rather than silently forced.
  • The finest grain the tool exposes is `group_by=name-date`: one row per (player_id, game_pk)
    with Statcast SUMMARY metrics for that player's plate appearances (batter) or pitches thrown
    (pitcher) in that game — exit velocity, launch angle, spin rate, xwOBA/xBA/xSLG, bat speed,
    swing length, attack angle, barrels%, hard-hit%, etc. This is a *game-average*, not a per-pitch
    value (columns are prefixed `avg_` below to say so honestly) — but it is exactly the per-
    player-per-game grain E7.1's `player_game_logs` already uses, and exactly the rate/summary
    shape E7.3's MLE needs ("wOBA, K%, BB%, ISO + AAA Statcast where present").
  • CSV endpoint: `https://baseballsavant.mlb.com/statcast-search-minors/csv`. The single most
    important undocumented parameter is `minors=true` — omit it and the endpoint 200s with a
    Statcast-shaped header but ZERO rows, every time (looks like "no data," is actually "wrong
    endpoint mode"). Level filter: `hfLevel=AAA|` (the site's own level dropdown offers only
    `A` and `AAA` — AA/High-A have no Hawk-Eye tracking at all, confirmed from the live page).
  • Month filter: use `hfMo=<1-12>|` (+ `hfSea=<year>|`), NOT `game_date_gt`/`game_date_lt`. Live
    probing found `game_date_gt`/`game_date_lt` UNRELIABLE on this endpoint — for 2022 data a
    date-bounded request silently returned the WHOLE SEASON (min/max dates spanned March–September
    regardless of the requested window) capped at the row limit below. `hfMo` scoped correctly in
    every season tested (2022–2026).
  • ⚠️ UNDOCUMENTED HARD ROW CAP: the CSV export silently truncates at 10,000 rows (confirmed: a
    2022 whole-season request and several single-month requests all returned exactly 10000 rows),
    keeping the rows the *requested sort* ranks highest (`sort_col=pitches&sort_order=desc` here)
    — i.e. a truncated response is NOT a random sample, it systematically drops the lowest-workload
    players (early call-ups, rehab stints, spot appearances) first. (season, level, month,
    player_type) requests stay well under the cap in every season/month probed (peak observed
    ~7,670 of 10,000 in a single month) but `fetch_month` still asserts on it and logs a loud
    ALERT if a response ever lands at/above TRUNCATION_WARN_THRESHOLD, so a future high-volume
    month can't silently ship a truncated slice.
  • Season floor, PROBED not assumed: 2019/2020/2021 return zero rows for level=AAA (pre-Hawk-Eye).
    2022 was INITIALLY assumed partial (Triple-A Charlotte + Pacific Coast League only, per public
    reporting about the "2023 league-wide expansion") — but the FULL backfill's coverage report
    (2026-07-25, operator-run) refuted that: 2022 shows 96–100% per-park coverage at essentially
    EVERY AAA venue, statistically indistinguishable from 2023–2026, confirmed league-wide from
    Opening Day (341 distinct April-2022 games spanning all 30 AAA parks, not a Charlotte/PCL
    subset). The public-reporting summary was wrong (or described a narrower "started tracking
    mid-2022" caveat that doesn't show up in the leaderboard's actual coverage) — trust the
    per-park read-through over the secondhand summary. EARLIEST_SEASON=2022 pins the true floor.
    The REAL, small (~1–8% per park), CONSISTENT gap is structural, not a rollout gradient: Savant's
    minors leaderboard has ZERO rows for AAA in **October, in every season checked (2022–2025)** —
    a handful of regular-season-ending games each year land in early October and are simply absent
    from this source (verified: the missing Las Vegas Ballpark 2022 games are exactly its final 3,
    2022-09-30/10-01/10-02). Plus two known one-off outliers: "Minute Maid Park" (2023, Houston's
    MLB park) and "Daikin Park" (2025/2026, same park renamed) each show 1–2 games/season at 0% —
    the Sugar Land Space Cowboys' annual novelty home game hosted at their parent club's stadium,
    which predictably carries no Hawk-Eye AAA leaderboard rows. --coverage-report quantifies both.
  • Spot-checked (per the operator's prompt) whether Hawk-Eye coverage extends to levels other than
    the site's advertised `A`/`AAA` pair: direct CSV probes with `hfLevel=AA|`/`A+|`/`R|`/`ROK|`/
    `DSL|` all returned ZERO rows (2024 batter, July) — confirms AA/High-A/Rookie genuinely have no
    Hawk-Eye tracking on this endpoint; the dropdown's two values were not an incomplete list.
  • `game_pk` / `player_id` verified LIVE against the MLB Stats API: a sampled game_pk resolved to
    a real AAA (sportId=11) game via `schedule?sportId=11&gamePk=<pk>`, and a sampled player_id
    resolved to the correct MLBAM person via `people/<id>`. Both are the SAME MLBAM identifiers
    E7.1's `schedule`/`player_game_logs` tables use — this table joins cleanly to both on
    (game_pk) / (player_id, game_pk) with no id-space translation needed.

Storage / idempotency (mirrors E7.1 exactly):
  • Delta-aware, SF-FREE. Written via delta-rs (deltalake==1.6) through
    scripts/utils/delta_lake.storage_options() — the instance-role-safe S3 auth that dodges the
    AKID / empty-env-var landmine (CLAUDE.md boto3 + delta-rs object_store).
  • Partitioned by (season, level, month) — level is carried as a partition column (not just a data
    column) even though this story only backfills AAA, so a future `--levels A` extension (the
    Low-A/complex-park Hawk-Eye coverage discovered live alongside AAA — see coverage report) adds
    partitions without touching existing ones.
  • Idempotent partition-skip: a (season, level, month) partition already present is SKIPPED on
    backfill unless --force. The CURRENT month is always re-pulled (absorbs late Statcast
    revisions — xwOBA etc. — and newly-played games), mirroring E7.1 / ingest_statcast_to_s3.py.
  • Every row carries a leakage-safe ingestion_ts (ISO-UTC VARCHAR — the lakehouse_raw convention;
    a downstream as-of join filters ingestion_ts <= decision_time).
  • NOT the E11.20 W1 pitch-mart Delta registry (`baseball/lakehouse_delta/...`) — MiLB is a
    disjoint surface living under `baseball/milb/...`, per E7.1's architecture decision.

Usage (all SF-FREE — AWS creds via the instance role / env only):
    # Verification stub — one season, one month, no write:
    uv run python scripts/ingest_statcast_aaa_to_s3.py --seasons 2024 \
        --start-month 2024-06 --end-month 2024-06 --dry-run

    # Real small slice (one season, one month):
    uv run python scripts/ingest_statcast_aaa_to_s3.py --seasons 2024 \
        --start-month 2024-06 --end-month 2024-06

    # Incremental (current season, current + prior month) — the daily op:
    uv run python scripts/ingest_statcast_aaa_to_s3.py --incremental

    # FULL historical backfill (>1 min — HAND TO OPERATOR, resumable):
    uv run python scripts/ingest_statcast_aaa_to_s3.py --seasons 2022-2026

    # Coverage-by-park-by-season report (reads this table + E7.1's schedule table via DuckDB):
    uv run python scripts/ingest_statcast_aaa_to_s3.py --coverage-report
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

BUCKET = "baseball-betting-ml-artifacts"
REGION = "us-east-2"
MILB_S3_PREFIX = "baseball/milb"
TABLE = "statcast_aaa"

SAVANT_MINORS_CSV_URL = "https://baseballsavant.mlb.com/statcast-search-minors/csv"

# The Minors Search page's own `hfLevel` dropdown offers exactly these two values (probed live
# 2026-07-25) — AA and High-A carry NO Hawk-Eye tracking at all. This story scopes to AAA only
# (DEFAULT_LEVELS); "A" (Low-A/complex-park rehab sites sharing spring-training Hawk-Eye rigs) is
# a documented, available, NOT-backfilled-by-default extension — see the coverage report.
LEVELS: dict[str, str] = {
    "AAA": "Triple-A",
    "A": "Single-A / complex (Florida State League + rehab sites)",
}
DEFAULT_LEVELS = ["AAA"]

PLAYER_TYPES = ["batter", "pitcher"]

# PROBED live 2026-07-25: 2019/2020/2021 hfLevel=AAA returns zero rows for every month tried.
# EARLIEST_SEASON pins the true floor, not the story title's "2023+" shorthand — the full
# backfill's coverage report (--coverage-report, run by the operator 2026-07-25) showed 2022
# already has 96-100% per-park coverage league-wide, statistically indistinguishable from
# 2023-2026 (confirmed from Opening Day: 341 distinct April-2022 games across all 30 AAA parks).
# There is no meaningful "2023 full rollout" dividing line in the actual data — public reporting
# describing a partial 2022 (Charlotte/PCL only) does not match what this endpoint serves; trust
# the per-park read-through over that secondhand summary. No FULL_ROLLOUT_SEASON constant: the
# real, small, consistent gap is structural (Savant's minors leaderboard has zero AAA rows for
# October in every season checked) plus two known one-off park outliers — see coverage report.
EARLIEST_SEASON = 2022

# Undocumented hard cap on the CSV export (probed live: a 2022 whole-season request and several
# single-month requests all returned exactly 10000 rows, sorted by the request's sort_col desc —
# a truncated response silently drops the LOWEST-workload players/games, not a random sample).
ROW_CAP = 10_000
TRUNCATION_WARN_THRESHOLD = 9_000

STATSAPI = "https://statsapi.mlb.com/api/v1"
REQUEST_TIMEOUT = 60
REQUEST_DELAY = 1.5  # polite delay between Savant requests
MAX_RETRIES = 3
RETRY_BACKOFF = 8

SAVANT_BASE_PARAMS = {
    "minors": "true",
    "hfGT": "R|",              # Regular Season only
    "group_by": "name-date",   # finest available grain: one row per (player, game)
    "min_pitches": "0",
    "min_pas": "0",
    "min_results": "0",
    "sort_col": "pitches",
    "sort_order": "desc",
}


# ── Column mapping: raw Savant Minors leaderboard column → (staged name, dtype) ────────────────
# The Minors Search returns the SAME 79-column leaderboard header for both player_type=batter and
# player_type=pitcher (verified live). These are per-GAME AVERAGES/rates, not per-pitch values —
# physical/positional columns get an `avg_` prefix so that's never ambiguous; counting + rate stats
# (already unambiguous at this grain) keep their natural name. Units/vocabulary mirror
# ingest_statcast_to_s3.py's RENAME_MAP (MLB Statcast staged names) wherever the concept overlaps,
# so a downstream reader recognizes the same metric across MLB and AAA even though the grain
# differs (pitch-event vs. player-game). `pitches` (the leaderboard's leading column) is dropped —
# verified identical to `total_pitches` in every sampled row (a Savant leaderboard quirk).
COLUMN_RENAME: dict[str, tuple[str, str]] = {
    "player_id":                                  ("player_id",                       "Int64"),
    "player_name":                                ("player_name",                      "str"),
    "game_date":                                  ("game_date",                        "str"),
    "game_pk":                                     ("game_pk",                          "Int64"),
    "total_pitches":                               ("total_pitches",                    "Int64"),
    "pitch_percent":                               ("pitch_percent",                    "float64"),
    "ba":                                          ("batting_avg",                      "float64"),
    "iso":                                         ("iso_value",                        "float64"),
    "babip":                                       ("babip_value",                      "float64"),
    "slg":                                         ("slg",                              "float64"),
    "woba":                                        ("woba",                             "float64"),
    "xwoba":                                       ("xwoba",                            "float64"),
    "xba":                                         ("xba",                              "float64"),
    "hits":                                        ("hits",                             "Int64"),
    "abs":                                         ("at_bats",                          "Int64"),
    "launch_speed":                                ("avg_exit_velocity_mph",            "float64"),
    "launch_angle":                                ("avg_launch_angle_degrees",         "float64"),
    "spin_rate":                                   ("avg_spin_rate_rpm",                "float64"),
    "velocity":                                    ("avg_pitch_velocity_mph",           "float64"),
    "effective_speed":                             ("avg_effective_speed_mph",          "float64"),
    "whiffs":                                      ("whiffs",                           "Int64"),
    "swings":                                      ("swings",                           "Int64"),
    "takes":                                       ("takes",                            "Int64"),
    "eff_min_vel":                                 ("eff_min_vel",                      "float64"),
    "release_extension":                           ("avg_release_extension_ft",         "float64"),
    "pos3_int_start_distance":                     ("pos3_int_start_distance",          "float64"),
    "pos4_int_start_distance":                     ("pos4_int_start_distance",          "float64"),
    "pos5_int_start_distance":                     ("pos5_int_start_distance",          "float64"),
    "pos6_int_start_distance":                     ("pos6_int_start_distance",          "float64"),
    "pos7_int_start_distance":                     ("pos7_int_start_distance",          "float64"),
    "pos8_int_start_distance":                     ("pos8_int_start_distance",          "float64"),
    "pos9_int_start_distance":                     ("pos9_int_start_distance",          "float64"),
    "pitcher_run_exp":                             ("pitcher_run_exp",                  "float64"),
    "run_exp":                                     ("run_exp",                          "float64"),
    "bat_speed":                                   ("avg_bat_speed_mph",                "float64"),
    "swing_length":                                ("avg_swing_length_ft",              "float64"),
    "miss_distance":                               ("avg_miss_distance",                "float64"),
    "pa":                                          ("plate_appearances",                "Int64"),
    "bip":                                         ("balls_in_play",                    "Int64"),
    "singles":                                     ("singles",                          "Int64"),
    "doubles":                                     ("doubles",                          "Int64"),
    "triples":                                     ("triples",                          "Int64"),
    "hrs":                                         ("home_runs",                        "Int64"),
    "so":                                          ("strikeouts",                       "Int64"),
    "k_percent":                                   ("k_percent",                        "float64"),
    "bb":                                          ("walks",                            "Int64"),
    "bb_percent":                                  ("bb_percent",                       "float64"),
    "api_break_z_with_gravity":                    ("avg_api_break_z_with_gravity_in",  "float64"),
    "api_break_z_induced":                         ("avg_api_break_z_induced_in",       "float64"),
    "api_break_x_arm":                             ("avg_api_break_x_arm_in",           "float64"),
    "api_break_x_batter_in":                       ("avg_api_break_x_batter_in",        "float64"),
    "hyper_speed":                                 ("hyper_speed",                      "float64"),
    "bbdist":                                      ("avg_hit_distance_ft",              "float64"),
    "hardhit_percent":                             ("hardhit_percent",                  "float64"),
    "barrels_per_bbe_percent":                     ("barrels_per_bbe_percent",          "float64"),
    "barrels_per_pa_percent":                      ("barrels_per_pa_percent",           "float64"),
    "release_pos_z":                               ("avg_release_pos_z_ft",             "float64"),
    "release_pos_x":                               ("avg_release_pos_x_ft",             "float64"),
    "plate_x":                                     ("avg_plate_x_ft",                   "float64"),
    "plate_z":                                     ("avg_plate_z_ft",                   "float64"),
    "obp":                                         ("obp",                              "float64"),
    "barrels_total":                               ("barrels_total",                    "Int64"),
    "batter_run_value_per_100":                    ("batter_run_value_per_100",         "float64"),
    "xobp":                                        ("xobp",                             "float64"),
    "xslg":                                        ("xslg",                             "float64"),
    "pitcher_run_value_per_100":                   ("pitcher_run_value_per_100",        "float64"),
    "xbadiff":                                     ("xbadiff",                          "float64"),
    "xobpdiff":                                    ("xobpdiff",                         "float64"),
    "xslgdiff":                                    ("xslgdiff",                         "float64"),
    "wobadiff":                                    ("wobadiff",                         "float64"),
    "swing_miss_percent":                          ("swing_miss_percent",               "float64"),
    "arm_angle":                                   ("avg_arm_angle_degrees",            "float64"),
    "attack_angle":                                ("avg_attack_angle_degrees",         "float64"),
    "attack_direction":                            ("avg_attack_direction_degrees",     "float64"),
    "swing_path_tilt":                             ("avg_swing_path_tilt_degrees",      "float64"),
    "rate_ideal_attack_angle":                     ("rate_ideal_attack_angle",          "float64"),
    "intercept_ball_minus_batter_pos_x_inches":    ("avg_intercept_offset_x_inches",    "float64"),
    "intercept_ball_minus_batter_pos_y_inches":    ("avg_intercept_offset_y_inches",    "float64"),
}


# ── Savant fetch ───────────────────────────────────────────────────────────────

def fetch_month(
    session: requests.Session, season: int, month: int, level: str, player_type: str,
) -> pd.DataFrame:
    """One (season, level, month, player_type) leaderboard slice, raw (un-renamed) columns.
    Empty df if no games. Retries transport errors; does NOT retry a truncated-but-200 response
    (that's a data-shape fact, not a transport failure) — callers see it via row count."""
    params = {
        **SAVANT_BASE_PARAMS,
        "hfSea": f"{season}|",
        "hfLevel": f"{level}|",
        "hfMo": f"{month}|",
        "player_type": player_type,
    }
    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(SAVANT_MINORS_CSV_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text or text.lower() == "null":
                return pd.DataFrame()
            df = pd.read_csv(
                io.StringIO(text), dtype=str, encoding_errors="replace", encoding="utf-8-sig",
            )
            df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
            if "player_id" in df.columns:
                df = df[df["player_id"].notna()].copy()
            if len(df) >= TRUNCATION_WARN_THRESHOLD:
                log.warning(
                    "[ALERT] %d %s %04d-%02d %s: %d rows (cap=%d) — POSSIBLY TRUNCATED; the "
                    "Savant Minors CSV export silently caps at %d rows sorted by pitches desc, "
                    "dropping the lowest-workload players first. Narrow this request (e.g. a "
                    "team/affiliate filter) if this recurs.",
                    season, level, season, month, player_type, len(df), ROW_CAP, ROW_CAP,
                )
            return df
        except requests.Timeout:
            log.warning("  [%d/%d] Timeout", attempt, MAX_RETRIES)
        except requests.HTTPError as exc:
            log.warning("  [%d/%d] HTTP %s", attempt, MAX_RETRIES, exc.response.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("  [%d/%d] Error: %s", attempt, MAX_RETRIES, exc)
        if attempt < MAX_RETRIES:
            log.info("  Retry in %ds…", backoff)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(
        f"Savant minors fetch failed for season={season} level={level} month={month} "
        f"player_type={player_type} after {MAX_RETRIES} attempts (transport error)"
    )


# ── Transform: raw leaderboard CSV → staged schema ──────────────────────────────

def transform(
    raw: pd.DataFrame, *, season: int, month: int, level: str, player_type: str, ingestion_ts: str,
) -> pd.DataFrame:
    """Apply COLUMN_RENAME + type casts + identity/grain columns. Returns staged df."""
    if raw.empty:
        return raw

    known_raw_cols = set(COLUMN_RENAME) | {"pitches"}  # `pitches` intentionally dropped, see above
    dropped = [c for c in raw.columns if c not in known_raw_cols]
    if dropped:
        banner = (
            "\n" + "=" * 72 + "\n"
            "ACTION NEEDED — NEW SAVANT MINORS COLUMN(S) NOT IN COLUMN_RENAME:\n"
            f"  {dropped}\n"
            "  Add to COLUMN_RENAME in ingest_statcast_aaa_to_s3.py.\n"
            + "=" * 72 + "\n"
        )
        print(banner, file=sys.stderr)
        log.warning("Dropping %d unknown column(s) not in COLUMN_RENAME: %s", len(dropped), dropped)

    keep = [c for c in raw.columns if c in COLUMN_RENAME]
    df = raw[keep].copy()
    df.rename(columns={r: s for r, (s, _) in COLUMN_RENAME.items() if r in df.columns}, inplace=True)

    for raw_col, (staged_col, dtype) in COLUMN_RENAME.items():
        if staged_col not in df.columns:
            continue
        if dtype == "str":
            df[staged_col] = df[staged_col].where(df[staged_col].notna(), None).astype("object")
        elif dtype == "Int64":
            df[staged_col] = pd.to_numeric(df[staged_col], errors="coerce").astype("Int64")
        elif dtype == "float64":
            df[staged_col] = pd.to_numeric(df[staged_col], errors="coerce").astype("float64")

    df["level"] = level
    df["player_type"] = player_type
    df["season"] = int(season)
    df["month"] = int(month)
    df["ingestion_ts"] = ingestion_ts

    dup_key = ["player_id", "game_pk", "player_type"]
    n_dupes = int(df.duplicated(subset=dup_key).sum())
    if n_dupes:
        log.warning(
            "%d duplicate (player_id, game_pk, player_type) row(s) in season=%d level=%s "
            "month=%02d %s — keeping the Savant response as-is (not deduped); investigate if "
            "this recurs.", n_dupes, season, level, month, player_type,
        )

    return df


# ── Delta write layer (instance-role-safe S3 auth) — mirrors ingest_milb_to_s3.py ─────────────

PARTITION_COLS = ["season", "level", "month"]


def _table_uri() -> str:
    return f"s3://{BUCKET}/{MILB_S3_PREFIX}/{TABLE}"


def _storage_options() -> dict:
    try:
        from utils.delta_lake import storage_options
    except ImportError:  # pragma: no cover
        from scripts.utils.delta_lake import storage_options
    return storage_options()


def _delta_table():
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError
    try:
        return DeltaTable(_table_uri(), storage_options=_storage_options())
    except TableNotFoundError:
        return None


def existing_partitions() -> set[tuple[int, str, int]]:
    """The (season, level, month) partitions already present in the Delta table."""
    dt = _delta_table()
    if dt is None:
        return set()
    out: set[tuple[int, str, int]] = set()
    for p in dt.partitions():
        try:
            out.add((int(p["season"]), str(p["level"]), int(p["month"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def write_partition(df: pd.DataFrame, season: int, level: str, month: int) -> int:
    """Idempotently write ONE (season, level, month) partition (overwrite predicate pins all
    three cols → O(one partition), re-runnable). schema_mode='merge' makes an additive column
    change a metadata commit, not a rebuild."""
    from deltalake import write_deltalake

    df = df.copy()
    df["season"] = int(season)
    df["level"] = level
    df["month"] = int(month)
    table_arrow = pa.Table.from_pandas(df, preserve_index=False)
    uri = _table_uri()
    exists = _delta_table() is not None
    kwargs = dict(storage_options=_storage_options())
    if not exists:
        write_deltalake(uri, table_arrow, mode="overwrite", partition_by=PARTITION_COLS, **kwargs)
    else:
        write_deltalake(
            uri, table_arrow, mode="overwrite",
            predicate=f"season = {int(season)} AND level = '{level}' AND month = {int(month)}",
            schema_mode="merge", **kwargs,
        )
    return len(df)


# ── Month iteration (shared with ingest_milb_to_s3.py's convention) ────────────

def iter_months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    ey, em = end
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


# ── Main run ─────────────────────────────────────────────────────────────────────

def run(
    seasons: list[int],
    levels: list[str],
    start_month: tuple[int, int] | None,
    end_month: tuple[int, int] | None,
    force: bool,
    dry_run: bool,
    current_month: tuple[int, int],
) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "credence-statcast-aaa-ingest/1.0 (research)"})

    done = set() if (force or dry_run) else existing_partitions()
    fire_ts = datetime.now(timezone.utc).isoformat()
    grand_rows = 0

    for season in seasons:
        start_mo = start_month[1] if (start_month and start_month[0] == season) else 3
        end_mo = end_month[1] if (end_month and end_month[0] == season) else 10

        for level in levels:
            for (yr, mo) in iter_months((season, start_mo), (season, end_mo)):
                part = (season, level, mo)
                is_current = (yr, mo) == current_month
                if part in done and not is_current and not force:
                    log.info("[%d %s %04d-%02d] partition present — SKIP (idempotent)",
                             season, level, yr, mo)
                    continue

                log.info("[%d %s %04d-%02d] fetching batter + pitcher leaderboards…",
                         season, level, yr, mo)
                frames: list[pd.DataFrame] = []
                for player_type in PLAYER_TYPES:
                    if dry_run:
                        log.info("    (dry-run) player_type=%s", player_type)
                        continue
                    try:
                        raw = fetch_month(session, season, mo, level, player_type)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("  %s fetch failed: %s — skipping", player_type, exc)
                        continue
                    time.sleep(REQUEST_DELAY)
                    if raw.empty:
                        continue
                    frames.append(transform(
                        raw, season=season, month=mo, level=level,
                        player_type=player_type, ingestion_ts=fire_ts,
                    ))

                if dry_run:
                    continue

                if not frames:
                    log.info("  no rows (off-season or pre-Hawk-Eye month) — nothing to write")
                    continue

                month_df = pd.concat(frames, ignore_index=True)
                n = write_partition(month_df, season, level, mo)
                grand_rows += n
                log.info("  → wrote %d row(s)", n)

    log.info(
        "DONE — %d row(s) written%s", grand_rows, "  [DRY-RUN — no writes]" if dry_run else "",
    )


# ── Coverage report (AC: coverage-by-park-by-season, explicit gaps) ────────────

# E7.1's `schedule` table keys its level by Stats API minor sportId, not Savant's `hfLevel`
# string — and only AAA maps 1:1 (sport_id=11). Savant's "A" bucket (Low-A/FSL/complex/rehab)
# spans multiple E7.1 sport_ids inconsistently, so it has no clean single-sport_id join; report
# on it separately (row counts only, no venue join) rather than silently mis-joining it to one.
LEVEL_TO_SPORT_ID: dict[str, int] = {"AAA": 11}


def print_coverage_report(seasons: list[int], levels: list[str]) -> None:
    """Joins this table's distinct games against E7.1's `schedule` table (same MLBAM game_pk
    space) via DuckDB delta_scan, per (season, venue): how many Final scheduled games have a
    matching Statcast game_pk here, vs. how many don't. SF-free; reads both Delta tables
    directly off S3."""
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("INSTALL delta; LOAD delta")
    conn.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )

    statcast_uri = _table_uri()
    schedule_uri = f"s3://{BUCKET}/{MILB_S3_PREFIX}/schedule"
    season_list = ", ".join(str(s) for s in seasons)

    joinable_levels = [lv for lv in levels if lv in LEVEL_TO_SPORT_ID]
    unjoinable_levels = [lv for lv in levels if lv not in LEVEL_TO_SPORT_ID]
    if unjoinable_levels:
        log.warning(
            "Level(s) %s have no 1:1 Stats-API sport_id in E7.1's schedule table (Savant's "
            "own level bucket doesn't map cleanly) — reporting row counts for them separately, "
            "not a venue join.", unjoinable_levels,
        )

    if joinable_levels:
        sport_ids = ", ".join(str(LEVEL_TO_SPORT_ID[lv]) for lv in joinable_levels)
        level_list = ", ".join(f"'{lv}'" for lv in joinable_levels)
        sql = f"""
            with sched as (
                select season, level_name, venue_name, game_pk
                from delta_scan('{schedule_uri}')
                where status_abstract = 'Final'
                  and sport_id in ({sport_ids})
                  and season in ({season_list})
            ),
            statcast as (
                select distinct season, level, game_pk
                from delta_scan('{statcast_uri}')
                where level in ({level_list})
                  and season in ({season_list})
            )
            select
                sched.season,
                sched.venue_name,
                count(distinct sched.game_pk)                                    as final_games,
                count(distinct statcast.game_pk)                                 as statcast_games,
                round(100.0 * count(distinct statcast.game_pk)
                      / nullif(count(distinct sched.game_pk), 0), 1)             as coverage_pct
            from sched
            left join statcast
              on statcast.game_pk = sched.game_pk and statcast.season = sched.season
            group by 1, 2
            order by 1, 5 asc, 2
        """
        try:
            rows = conn.execute(sql).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.error(
                "Coverage report query failed (%s) — is E7.1's schedule table backfilled for "
                "these seasons, and has this table been written yet?", exc,
            )
            conn.close()
            return
    else:
        rows = []

    print(f"\n{'season':>6}  {'venue':<40}  {'final_games':>11}  {'statcast_games':>14}  {'coverage_%':>10}")
    print("-" * 92)
    for season, venue, final_games, statcast_games, pct in rows:
        print(f"{season:>6}  {(venue or '(unknown)'):<40}  {final_games:>11}  {statcast_games:>14}  {(pct if pct is not None else 0):>9.1f}%")

    if unjoinable_levels:
        level_list = ", ".join(f"'{lv}'" for lv in unjoinable_levels)
        counts = conn.execute(f"""
            select season, level, count(distinct game_pk) as statcast_games
            from delta_scan('{statcast_uri}')
            where level in ({level_list}) and season in ({season_list})
            group by 1, 2 order by 1, 2
        """).fetchall()
        print(f"\n(no schedule/venue join available for {unjoinable_levels} — row counts only)")
        for season, level, n in counts:
            print(f"  {season}  {level:<6}  {n} distinct game(s) with Statcast rows")

    conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in spec.split(",") if s.strip()]


def _parse_month(spec: str | None) -> tuple[int, int] | None:
    if not spec:
        return None
    y, m = spec.split("-")
    return int(y), int(m)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Ingest AAA (Hawk-Eye) Statcast leaderboard data → S3 Delta lakehouse."
    )
    ap.add_argument("--seasons", default=None,
                    help="Season(s): '2024', '2022,2024', or a range '2022-2026'. "
                         f"Backfill floor is {EARLIEST_SEASON} (probed live — pre-Hawk-Eye "
                         "seasons return nothing).")
    ap.add_argument("--levels", default=None,
                    help=f"Comma list of level codes (default: {','.join(DEFAULT_LEVELS)}). "
                         f"Valid: {','.join(LEVELS)}.")
    ap.add_argument("--start-month", default=None, metavar="YYYY-MM",
                    help="First month (default: March of each season).")
    ap.add_argument("--end-month", default=None, metavar="YYYY-MM",
                    help="Last month (default: October of each season).")
    ap.add_argument("--incremental", action="store_true",
                    help="Current season, AAA, current + prior month (the daily op). Always "
                         "re-pulls (absorbs late Statcast revisions + newly-played games).")
    ap.add_argument("--force", action="store_true",
                    help="Re-pull + overwrite even partitions already present.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Log the (season, level, month) partitions that would be fetched; "
                         "make NO Savant requests and NO S3 writes.")
    ap.add_argument("--coverage-report", action="store_true",
                    help="Print a coverage-by-venue-by-season report joining this table against "
                         "E7.1's schedule table, then exit (no ingest).")
    args = ap.parse_args()

    today = date.today()
    current_month = (today.year, today.month)

    if args.coverage_report:
        seasons = _parse_seasons(args.seasons) if args.seasons else list(range(EARLIEST_SEASON, today.year + 1))
        levels = [lv.strip().upper() for lv in args.levels.split(",")] if args.levels else DEFAULT_LEVELS
        print_coverage_report(seasons, levels)
        return

    if args.incremental:
        include_prior = today.day <= 3 and today.month > 1
        seasons = [today.year]
        levels = DEFAULT_LEVELS
        start_month = (today.year, today.month - 1) if include_prior else current_month
        end_month = current_month
        force = True
    else:
        if not args.seasons:
            ap.error("--seasons is required unless --incremental or --coverage-report")
        seasons = [s for s in _parse_seasons(args.seasons) if s >= EARLIEST_SEASON]
        dropped = [s for s in _parse_seasons(args.seasons) if s < EARLIEST_SEASON]
        if dropped:
            log.warning("Seasons < %d dropped (no Hawk-Eye AAA coverage): %s", EARLIEST_SEASON, dropped)
        if not seasons:
            ap.error(f"No seasons >= {EARLIEST_SEASON} to ingest.")
        levels = [lv.strip().upper() for lv in args.levels.split(",")] if args.levels else DEFAULT_LEVELS
        start_month = _parse_month(args.start_month)
        end_month = _parse_month(args.end_month)
        force = args.force

    bad = [lv for lv in levels if lv not in LEVELS]
    if bad:
        ap.error(f"Unknown level(s) {bad}; valid: {sorted(LEVELS)}")

    log.info(
        "AAA Statcast ingest — seasons=%s levels=%s months=%s..%s force=%s dry_run=%s",
        seasons, levels, args.start_month or "Mar", args.end_month or "Oct", force, args.dry_run,
    )
    run(seasons, levels, start_month, end_month, force, args.dry_run, current_month)


if __name__ == "__main__":
    main()
