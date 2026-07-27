"""
ingest_fangraphs_milb_leaderboards_to_s3.py   (E7.7 — FanGraphs MiLB leaderboards → S3 Delta)
---------------------------------------------------------------------------------------------
Ingest the FanGraphs **minor-league statistical leaderboards** (batting + pitching) and land
them as a Delta table on S3 — SF-FREE, instance-role auth (the E7.1 pattern).

    baseball/milb/fg_leaderboards   — one row per (season, stats, as_of_date, fg_minor_id)

WHY THIS EXISTS (operator, 2026-07-27): THE BOARD (E7.7's other feed) only covers RANKED/graded
prospects (~1,300). But deep dynasty leagues roster many UNRANKED minor leaguers (a 12-team
league can keep 8 minors each ⇒ ~100 rostered, most with no Board FV). The MiLB leaderboards
enumerate EVERY minor leaguer with a stat line — so THIS is the population feed that gives a
`fg_minor_id` (+ MLBAM id) for all of them, the id coverage E7.4's xref + the E8.0 draft board
need so no rostered player is missing.

🚨 CLOUDFLARE (CLAUDE.md INC-16/INC-26): FanGraphs is CF-gated (HTTP 403 to any direct client).
We route THROUGH the box's FlareSolverr proxy via `fangraphs_client.fetch_minor_leaderboard`
(paginated, INC-26-hardened). No FlareSolverr → the fetch raises; `--from-csv` is the fallback.

🧬 COLUMN-NAME REALITY (P0.1/N0.1): each row stores its FULL raw JSON (`raw_json`) + typed cols
via CASE-INSENSITIVE alias lookup. `--probe` prints the live board's real field names + alias
resolution and writes nothing (the ONE real pull confirms extraction before any write).

AS-OF DATING: a leaderboard stat line grows through the season → each pull stamps `as_of_date`
and partitions by (season, stats, as_of_date) so snapshots accumulate for leakage-safe as-of
joins (E7.8). Re-running the same day is idempotent. `ingested_at_utc` = ISO-UTC VARCHAR.

Usage (SF-FREE — AWS creds via instance role / env):
    # THE ONE REAL PULL — probe the live batting board (field names + samples, NO write):
    uv run python scripts/ingest_fangraphs_milb_leaderboards_to_s3.py --season 2026 --stats bat --probe

    # Real snapshot of the current (2026) batting + pitching boards → S3 Delta:
    uv run python scripts/ingest_fangraphs_milb_leaderboards_to_s3.py --season 2026

    # Coverage report only (no write):
    uv run python scripts/ingest_fangraphs_milb_leaderboards_to_s3.py --season 2026 --dry-run

    # Operator fallback (endpoint blocked) — a manual CSV export (pass --stats to tag it):
    uv run python scripts/ingest_fangraphs_milb_leaderboards_to_s3.py --season 2026 --stats bat --from-csv board.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

BUCKET = "baseball-betting-ml-artifacts"
REGION = "us-east-2"
S3_PREFIX = "baseball/milb"
TABLE = "fg_leaderboards"
PARTITION_COLS = ["season", "stats", "as_of_date"]
VALID_STATS = ("bat", "pit")

# CASE-INSENSITIVE alias sets (lowercased) → typed column. First match wins; `raw_json` keeps
# the FULL stat line regardless, so a miss loses nothing (column-name-reality).
FIELD_ALIASES: dict[str, list[str]] = {
    # `minorMasterId` is the STABLE `sa`-prefixed minor id → wins over PlayerId/UPID (which can be
    # the numeric MLB FG id for a graduate); `xMLBAMID` (present on the leaderboards per fungo) is
    # the MLBAM bridge THE BOARD lacks. `fg_player_id` keeps the FG unified id separately.
    "fg_minor_id":  ["minormasterid", "playerid", "player_id"],
    "fg_player_id": ["upid", "playerid", "player_id"],
    "mlbam_id":     ["xmlbamid", "mlbamid", "mlbam_id"],
    "player_name":  ["playername", "name", "player", "fullname"],
    # prefer the clean abbreviation `TeamName` ("CHC (AAA)") over `Team` (an HTML <a> anchor);
    # `AffAbbName` is the parent MLB org.
    "team":         ["teamname", "affabbname", "team", "org", "organization"],
    "level":        ["alevel", "level", "mlevel", "current level", "minorlevelid"],
    "age":          ["age", "cur_age"],
    # a few universal-ish rate stats extracted for legibility; the rest lives in raw_json.
    "pa":           ["pa", "ab"],
    "ip":           ["ip"],
    "k_pct":        ["k%", "kpct", "k_pct"],
    "bb_pct":       ["bb%", "bbpct", "bb_pct"],
    "wrc_plus":     ["wrc+", "wrcplus"],
    "era":          ["era"],
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


# ── Tolerant extraction ──────────────────────────────────────────────────────────

def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = _HTML_TAG_RE.sub("", str(v)).strip()
    return s or None


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def _lc_map(row: dict) -> dict:
    return {str(k).lower(): v for k, v in row.items()}


def _pick(lc: dict, aliases: list[str]):
    for a in aliases:
        if a in lc and lc[a] not in (None, ""):
            return lc[a]
    return None


def extract_row(raw: dict, season: int, stats: str, as_of_date: str, ingested_at: str) -> dict:
    lc = _lc_map(raw)
    return {
        "fg_minor_id":   _clean_str(_pick(lc, FIELD_ALIASES["fg_minor_id"])),
        "fg_player_id":  _clean_str(_pick(lc, FIELD_ALIASES["fg_player_id"])),
        "mlbam_id":      _clean_str(_pick(lc, FIELD_ALIASES["mlbam_id"])),
        "player_name":   _clean_str(_pick(lc, FIELD_ALIASES["player_name"])),
        "team":          _clean_str(_pick(lc, FIELD_ALIASES["team"])),
        "level":         _clean_str(_pick(lc, FIELD_ALIASES["level"])),
        "age":           _to_float(_pick(lc, FIELD_ALIASES["age"])),
        "pa":            _to_float(_pick(lc, FIELD_ALIASES["pa"])),
        "ip":            _to_float(_pick(lc, FIELD_ALIASES["ip"])),
        "k_pct":         _to_float(_pick(lc, FIELD_ALIASES["k_pct"])),
        "bb_pct":        _to_float(_pick(lc, FIELD_ALIASES["bb_pct"])),
        "wrc_plus":      _to_float(_pick(lc, FIELD_ALIASES["wrc_plus"])),
        "era":           _to_float(_pick(lc, FIELD_ALIASES["era"])),
        "stats":         stats,
        "season":        int(season),
        "as_of_date":    as_of_date,
        "ingested_at_utc": ingested_at,
        "raw_json":      json.dumps(raw, default=str, sort_keys=True),
    }


# ── Delta write layer (instance-role-safe S3 auth) ──────────────────────────────

def _table_uri() -> str:
    return f"s3://{BUCKET}/{S3_PREFIX}/{TABLE}"


def _storage_options() -> dict:
    try:
        from utils.delta_lake import storage_options
    except ImportError:  # pragma: no cover
        from scripts.utils.delta_lake import storage_options
    return storage_options()


def _table_exists() -> bool:
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError
    try:
        DeltaTable(_table_uri(), storage_options=_storage_options())
        return True
    except TableNotFoundError:
        return False


def write_partition(df: pd.DataFrame, season: int, stats: str, as_of_date: str) -> int:
    """Idempotently write ONE (season, stats, as_of_date) partition (overwrite predicate pins
    all three → re-running the same day is a clean rewrite; snapshots accumulate)."""
    from deltalake import write_deltalake
    df = df.copy()
    df["season"] = int(season)
    df["stats"] = str(stats)
    df["as_of_date"] = str(as_of_date)
    table_arrow = pa.Table.from_pandas(df, preserve_index=False)
    uri = _table_uri()
    kwargs = dict(storage_options=_storage_options())
    if not _table_exists():
        write_deltalake(uri, table_arrow, mode="overwrite", partition_by=PARTITION_COLS, **kwargs)
    else:
        write_deltalake(
            uri, table_arrow, mode="overwrite",
            predicate=f"season = {int(season)} AND stats = '{stats}' AND as_of_date = '{as_of_date}'",
            schema_mode="merge", **kwargs,
        )
    return len(df)


# ── Coverage / probe ─────────────────────────────────────────────────────────────

def coverage_report(rows: list[dict], season: int, stats: str, as_of_date: str) -> None:
    n = len(rows)
    def _cnt(col: str) -> int:
        return sum(1 for r in rows if r.get(col) not in (None, ""))
    teams = {r["team"] for r in rows if r.get("team")}
    levels = {r["level"] for r in rows if r.get("level")}
    log.info("──────── COVERAGE (%s) ────────", stats)
    log.info("  season=%d  stats=%s  as_of=%s", season, stats, as_of_date)
    log.info("  minor leaguers (rows) ....... %d", n)
    if n:
        log.info("  with fg_minor_id ............ %d (%.0f%%)  ⭐ population id feed", _cnt("fg_minor_id"), 100 * _cnt("fg_minor_id") / n)
        log.info("  with mlbam_id ............... %d (%.0f%%)  ⭐ E8.0 join key", _cnt("mlbam_id"), 100 * _cnt("mlbam_id") / n)
        log.info("  with player_name ............ %d (%.0f%%)", _cnt("player_name"), 100 * _cnt("player_name") / n)
        log.info("  with level .................. %d", _cnt("level"))
        log.info("  distinct teams / levels ..... %d / %s", len(teams), sorted(levels))
    for key in ("fg_minor_id", "mlbam_id"):
        if n and _cnt(key) == 0:
            log.warning(
                "  ⚠️  %s resolved 0/%d rows — FanGraphs field casing likely changed. "
                "Inspect `raw_json` (or --probe) and update FIELD_ALIASES[%r].", key, n, key,
            )
    log.info("────────────────────────────────")


def probe(rows: list[dict], stats: str) -> None:
    log.info("──────── PROBE %s (no write) ────────", stats)
    log.info("  fetched %d raw row(s)", len(rows))
    if not rows:
        log.warning("  ZERO rows — check season / stats / FLARESOLVERR_URL.")
        return
    keys = sorted({k for r in rows for k in r.keys()})
    log.info("  %d distinct field name(s):", len(keys))
    log.info("    %s", ", ".join(keys))
    for i, r in enumerate(rows[:2]):
        log.info("  sample row %d: %s", i, json.dumps(r, default=str)[:1200])
    lc0 = _lc_map(rows[0])
    log.info("  alias resolution on row 0:")
    for col, aliases in FIELD_ALIASES.items():
        hit = next((a for a in aliases if a in lc0 and lc0[a] not in (None, "")), None)
        log.info("    %-12s → %s", col, f"{hit!r} = {lc0[hit]!r}" if hit else "‹NO MATCH — inspect keys above›")
    log.info("──────────────────────────────────────")


# ── Fetch sources ────────────────────────────────────────────────────────────────

def fetch_board(season: int, stats: str, *, endpoint: str | None = None,
                stat_type: int | str = 0, extra_params: dict | None = None) -> list[dict]:
    try:
        from fangraphs_client import fetch_minor_leaderboard
    except ImportError:  # pragma: no cover
        from utils.fangraphs_client import fetch_minor_leaderboard
    return fetch_minor_leaderboard(
        stats=stats, season=season, stat_type=stat_type,
        url=endpoint, extra_params=extra_params,
    )["data"]


def fetch_from_csv(path: str) -> list[dict]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.to_dict(orient="records")


# ── Main run ─────────────────────────────────────────────────────────────────────

def run(season: int, stats_groups: list[str], as_of_date: str, mode: str, csv_path: str | None,
        endpoint: str | None = None, stat_type: int | str = 0, extra_params: dict | None = None) -> None:
    ingested_at = datetime.now(timezone.utc).isoformat()

    for stats in stats_groups:
        if csv_path:
            log.info("Reading %s board from CSV: %s", stats, csv_path)
            raw_rows = fetch_from_csv(csv_path)
        else:
            log.info("Fetching MiLB %s leaderboard — season=%d", stats, season)
            raw_rows = fetch_board(season, stats, endpoint=endpoint,
                                   stat_type=stat_type, extra_params=extra_params)

        if mode == "probe":
            probe(raw_rows, stats)
            continue

        rows = [extract_row(r, season, stats, as_of_date, ingested_at) for r in raw_rows]
        coverage_report(rows, season, stats, as_of_date)

        if mode == "dry-run":
            log.info("[DRY-RUN] %s: %d row(s) built — NO S3 write.", stats, len(rows))
            continue
        if not rows:
            log.warning("%s: no rows to write — skipping.", stats)
            continue
        n = write_partition(pd.DataFrame(rows), season, stats, as_of_date)
        log.info("→ wrote %d %s row(s) to %s  (season=%d, as_of=%s)",
                 n, stats, _table_uri(), season, as_of_date)


def parse_seasons(spec: str) -> list[int]:
    """'2020' → [2020]; '2019,2021' → [2019,2021]; '2018-2026' → [2018..2026]."""
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in spec.split(",") if s.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest FanGraphs MiLB leaderboards → S3 Delta (E7.7).")
    ap.add_argument("--season", type=int, default=date.today().year,
                    help="Season year (default: current year).")
    ap.add_argument("--seasons", default=None,
                    help="Historical backfill: a range '2018-2026' or list '2019,2021' (overrides "
                         "--season). Each past season stamps as_of=<season>-07-01.")
    ap.add_argument("--stats", default="bat,pit",
                    help="Comma list of stat groups: bat, pit (default: both).")
    ap.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                    help="Snapshot date on the rows (default: today's game day; <season>-07-01 for a "
                         "past season). Applies to --season only (a --seasons backfill resolves per season).")
    ap.add_argument("--probe", action="store_true",
                    help="THE ONE REAL PULL: print field names + samples + alias resolution, NO write.")
    ap.add_argument("--dry-run", action="store_true", help="Fetch + coverage report, NO S3 write.")
    ap.add_argument("--from-csv", default=None, metavar="PATH",
                    help="Operator fallback: read a manual CSV export instead of the API.")
    # Probe-driven overrides for the fragile minor endpoint (no code change needed to finalize):
    ap.add_argument("--endpoint", default=None,
                    help="Override the minor-leaderboard API URL (default: the built-in path). "
                         "Use to point at the exact URL confirmed from the /leaders/minor-league "
                         "network tab if the default 404s.")
    ap.add_argument("--stat-type", default="0",
                    help="FanGraphs minor column-set id (default 0; the major board's 8 404s).")
    ap.add_argument("--extra-param", action="append", default=[], metavar="KEY=VALUE",
                    help="Merge/override a single query param (repeatable), e.g. --extra-param lg=2,4,5.")
    args = ap.parse_args()

    stats_groups = [s.strip() for s in args.stats.split(",") if s.strip()]
    bad = [s for s in stats_groups if s not in VALID_STATS]
    if bad:
        ap.error(f"Invalid stats group(s) {bad}; valid: {VALID_STATS}")

    if args.seasons and args.as_of:
        ap.error("--as-of applies to a single --season; a --seasons backfill resolves as_of per season.")
    seasons = parse_seasons(args.seasons) if args.seasons else [args.season]

    extra_params: dict = {}
    for kv in args.extra_param:
        if "=" not in kv:
            ap.error(f"--extra-param must be KEY=VALUE, got: {kv!r}")
        k, v = kv.split("=", 1)
        extra_params[k.strip()] = v.strip()

    try:
        from betting_ml.utils.game_day import current_game_date_iso
        game_date = current_game_date_iso()
    except Exception:  # noqa: BLE001
        game_date = date.today().isoformat()

    mode = "probe" if args.probe else ("dry-run" if args.dry_run else "write")
    for season in seasons:
        # as_of: explicit → verbatim; current season → US game day; past season → mid-season approx.
        if args.as_of:
            as_of_date = args.as_of
        elif season != date.today().year:
            as_of_date = f"{season}-07-01"
            log.warning("Historical season %d with no --as-of → stamping as_of=%s (mid-season approx); "
                        "pass --as-of (single --season) for the true date (E7.8 as-of joins).",
                        season, as_of_date)
        else:
            as_of_date = game_date
        log.info("FanGraphs MiLB leaderboard ingest (E7.7) — season=%d stats=%s as_of=%s mode=%s%s%s",
                 season, stats_groups, as_of_date, mode,
                 f" from-csv={args.from_csv}" if args.from_csv else "",
                 f" endpoint={args.endpoint}" if args.endpoint else "")
        try:
            run(season, stats_groups, as_of_date, mode, args.from_csv,
                endpoint=args.endpoint, stat_type=args.stat_type, extra_params=extra_params or None)
        except Exception as exc:  # noqa: BLE001 — one bad season must not abort a multi-season backfill
            if len(seasons) == 1:
                raise
            log.warning("Season %d FAILED (%s) — continuing backfill.", season, exc)


if __name__ == "__main__":
    main()
