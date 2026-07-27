"""
ingest_fangraphs_prospects_to_s3.py   (E7.7 — FanGraphs THE BOARD → S3 Delta lakehouse)
---------------------------------------------------------------------------------------
Ingest the FanGraphs **prospect board** (Future Value / rank / ETA / level / org, each row
carrying BOTH the FanGraphs id `fg_minor_id` AND the MLBAM id) and land it as a Delta table
on S3 — SF-FREE, instance-role S3 auth (the E7.1 `ingest_milb_to_s3.py` pattern).

    baseball/milb/the_board   — one row per (as_of_date, season, fg_minor_id) prospect snapshot

WHY (E7.7 → E7.4 xref + ⭐ E8.0 draft board): `fg_minor_id` — the stable prospect id — and the
FV/rank signal do NOT exist anywhere else in the repo. This id (+ the MLBAM id the board also
carries) is what lets a prospect reconcile to his MLBAM spine and join to the E7.3 MLE
projections (`baseball/milb/derived/mle_projections`, MLBAM-keyed) WITHOUT a fragile name-match.

🚨 CLOUDFLARE (CLAUDE.md INC-16/INC-26): FanGraphs fronts the whole site with a Cloudflare JS
challenge — a naive `requests.get` returns HTTP 403 (`cf-mitigated: challenge`, verified live
2026-07-27). We route THROUGH the box's FlareSolverr proxy via the proven `fangraphs_client`
path (needs FLARESOLVERR_URL on the box). No FlareSolverr → the fetch raises; use `--from-csv`
with a manual Board export as the operator fallback (an accepted 8/3 path).

🧬 COLUMN-NAME REALITY (P0.1 / N0.1 discipline): The Board is a JS-rendered/API-backed page —
its exact field CASING can drift. So every row is stored with its FULL raw JSON (`raw_json`),
and the typed columns are extracted by CASE-INSENSITIVE alias lookup. A key we can't find is
logged in the coverage report (never silently zeroed), and `raw_json` guarantees nothing is
lost even if an alias misses. Run `--probe` FIRST (the ONE real pull): it prints the real field
names + sample rows and writes NOTHING, so the extraction is confirmed against reality before a
real write.

AS-OF DATING: a prospect's FV/rank is a TIME SERIES. Each pull stamps `as_of_date` (the snapshot
date) and partitions by (season, as_of_date), so historical snapshots accumulate as distinct
partitions → E7.8 can do leakage-safe as-of joins. Re-running the same day is idempotent (the
partition is overwritten). `ingested_at_utc` is a full ISO-UTC VARCHAR (leakage-safe provenance;
VARCHAR dodges the INC-23 binary-timestamp bite — cast at the use-site).

Usage (all SF-FREE — AWS creds via the instance role / env only):
    # THE ONE REAL PULL — probe the live board: print field names + samples, write NOTHING.
    uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2026 --probe

    # Real snapshot of the current (2026) board → S3 Delta (the 8/3 hard requirement):
    uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2026

    # Fetch full board but DON'T write (coverage report only):
    uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2026 --dry-run

    # Operator fallback if the endpoint is genuinely blocked — a manual Board CSV export:
    uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2026 --from-csv board.csv

    # Historical board snapshot (E7.8 "do rankings translate to MLB success?" research): pass the
    # past --season (+ --as-of for the board's true date; else it stamps <season>-07-01 + warns —
    # never today). PROBE a past season first to confirm the slug returns historical data:
    uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2020 --probe
    uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2020 --as-of 2020-02-15
    #   (backfill many seasons: bash loop `for y in $(seq 2016 2025); do … --season $y …; done`)
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

# scripts/utils for the FanGraphs client + the instance-role-safe Delta S3 auth.
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
# Co-located under the E7.1 milb/ prefix (isolated from baseball/lakehouse/ — no ext-table
# glob touches milb/, so no glob-dup risk). The Delta table dir lives directly under it.
S3_PREFIX = "baseball/milb"
TABLE = "the_board"
PARTITION_COLS = ["season", "as_of_date"]

# CASE-INSENSITIVE alias sets (lowercased) → the typed column. First match wins. The raw
# record is preserved in `raw_json` regardless, so a miss loses nothing (column-name-reality).
# Verified against the LIVE board probe (2026-07-27, box FlareSolverr, 1290 rows). Key realities:
#  • The STABLE prospect id is `minorMasterId` (always `sa`-prefixed, e.g. 'sa3065496') — it MUST
#    win over `PlayerId`/`UPID`, which for a graduated player is the numeric MLB FG id (e.g.
#    '35376'), NOT the stable minor id. `fg_player_id` keeps the FG unified id separately (the
#    numeric id bridges to xMLBAMID via other FG feeds / E7.4 xref).
#  • THE BOARD does NOT expose an MLBAM id — `mlbam_id` resolves None here BY DESIGN; the MLBAM
#    bridge comes via the MiLB leaderboard feed + E7.4 xref (that is WHY the population feed exists).
FIELD_ALIASES: dict[str, list[str]] = {
    # ⭐ the join keys E7.4 / E8.0 need
    "fg_minor_id":  ["minormasterid", "prospectid", "playerid", "player_id"],
    "fg_player_id": ["upid", "playerid", "player_id"],
    "mlbam_id":     ["xmlbamid", "mlbamid", "mlbam_id", "mlbamplayerid"],
    # identity / context
    "player_name":  ["playername", "name", "player", "fullname"],
    "org":          ["team", "org", "corg", "organization", "orgname"],
    "position":     ["position", "positiondb", "pos", "minorpos", "primaryposition"],
    "level":        ["mlevel", "llevel", "current level", "currentlevel", "level", "toplevel"],
    "age":          ["age", "cur_age", "currentage"],
    # the FV / rank / ETA signal E7.8 tests
    "fv":           ["fv_current", "cfv", "fv", "futurevalue", "current_fv"],
    "risk":         ["crisk", "risk"],
    "eta":          ["eta_current", "ceta", "eta", "etayear", "eta_year"],
    "overall_rank": ["ovr_rank", "covr", "top100", "overall_rank", "overallrank", "rank"],
    "org_rank":     ["org_rank", "corg_rank", "orgrank", "org_top"],
    # high-value for the 8/3 draft board (FanGraphs' own fantasy ranks + one-line scouting tag)
    "fantasy_dynasty_rank": ["fantasy_dynasty"],
    "fantasy_redraft_rank": ["fantasy_redraft"],
    "tldr":         ["tldr"],
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


# ── Extraction (tolerant, case-insensitive) ──────────────────────────────────────

def _clean_str(v) -> str | None:
    """Coerce to a trimmed str, stripping any embedded HTML anchors (FanGraphs wraps some
    string fields — Team/Name — in <a> tags). None/empty → None."""
    if v is None:
        return None
    s = _HTML_TAG_RE.sub("", str(v)).strip()
    return s or None


def _to_float(v) -> float | None:
    """Best-effort numeric parse (handles a trailing '+'/'-' FV grade like '50+')."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def _to_int(v) -> int | None:
    f = _to_float(v)
    return int(f) if f is not None else None


def _lc_map(row: dict) -> dict:
    """{lowercased_key: value} for a raw board row (case-insensitive lookup)."""
    return {str(k).lower(): v for k, v in row.items()}


def _pick(lc: dict, aliases: list[str]):
    for a in aliases:
        if a in lc and lc[a] not in (None, ""):
            return lc[a]
    return None


def extract_row(raw: dict, season: int, as_of_date: str, board_slug: str, ingested_at: str) -> dict:
    """One raw board record → a typed, self-contained prospect row (+ raw_json fallback)."""
    lc = _lc_map(raw)
    return {
        "fg_minor_id":   _clean_str(_pick(lc, FIELD_ALIASES["fg_minor_id"])),
        "fg_player_id":  _clean_str(_pick(lc, FIELD_ALIASES["fg_player_id"])),
        "mlbam_id":      _clean_str(_pick(lc, FIELD_ALIASES["mlbam_id"])),
        "player_name":   _clean_str(_pick(lc, FIELD_ALIASES["player_name"])),
        "org":           _clean_str(_pick(lc, FIELD_ALIASES["org"])),
        "position":      _clean_str(_pick(lc, FIELD_ALIASES["position"])),
        "level":         _clean_str(_pick(lc, FIELD_ALIASES["level"])),
        "age":           _to_float(_pick(lc, FIELD_ALIASES["age"])),
        "fv":            _to_float(_pick(lc, FIELD_ALIASES["fv"])),
        "fv_raw":        _clean_str(_pick(lc, FIELD_ALIASES["fv"])),
        "risk":          _clean_str(_pick(lc, FIELD_ALIASES["risk"])),
        "eta":           _to_int(_pick(lc, FIELD_ALIASES["eta"])),
        "overall_rank":  _to_int(_pick(lc, FIELD_ALIASES["overall_rank"])),
        "org_rank":      _to_int(_pick(lc, FIELD_ALIASES["org_rank"])),
        "fantasy_dynasty_rank": _to_int(_pick(lc, FIELD_ALIASES["fantasy_dynasty_rank"])),
        "fantasy_redraft_rank": _to_int(_pick(lc, FIELD_ALIASES["fantasy_redraft_rank"])),
        "tldr":          _clean_str(_pick(lc, FIELD_ALIASES["tldr"])),
        "board_slug":    board_slug,
        "season":        int(season),
        "as_of_date":    as_of_date,
        "ingested_at_utc": ingested_at,
        # full raw record — nothing is ever lost even if an alias missed (column-name-reality).
        "raw_json":      json.dumps(raw, default=str, sort_keys=True),
    }


# ── Delta write layer (instance-role-safe S3 auth, mirrors ingest_milb_to_s3.py) ─

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


# Columns that are ALWAYS strings, even when every value in a pull is None. Pinned because an
# all-None object column makes pyarrow infer the `null` type, which Delta records as `"void"` —
# and DuckDB's delta reader then hard-errors `Unsupported Delta table type: 'void'` on the WHOLE
# table, for every consumer (E7.4 hit exactly this: `mlbam_id` is 100% NULL on THE BOARD by
# design, which made `delta_scan` unable to read the board at all). The same class as the
# INC-17 nullable-int→DOUBLE mirror poisoning: an all-null column silently picks a type nobody
# wants. Pin the type at the writer — one place heals every consumer.
_STRING_PINNED = [
    "fg_minor_id", "fg_player_id", "mlbam_id", "player_name", "org", "position", "level",
    "fv_raw", "risk", "board_slug", "as_of_date", "ingested_at_utc", "raw_json", "tldr",
]


def write_partition(df: pd.DataFrame, season: int, as_of_date: str) -> int:
    """Idempotently write ONE (season, as_of_date) partition (overwrite predicate pins both
    cols → re-running the same day is a clean rewrite, historical snapshots accumulate)."""
    from deltalake import write_deltalake
    df = df.copy()
    df["season"] = int(season)
    df["as_of_date"] = str(as_of_date)
    for col in _STRING_PINNED:
        if col in df.columns:
            df[col] = df[col].astype("string")
    table_arrow = pa.Table.from_pandas(df, preserve_index=False)
    uri = _table_uri()
    kwargs = dict(storage_options=_storage_options())
    if not _table_exists():
        write_deltalake(uri, table_arrow, mode="overwrite", partition_by=PARTITION_COLS, **kwargs)
    else:
        write_deltalake(
            uri, table_arrow, mode="overwrite",
            predicate=f"season = {int(season)} AND as_of_date = '{as_of_date}'",
            schema_mode="merge", **kwargs,
        )
    return len(df)


# ── Coverage report (the AC deliverable) ─────────────────────────────────────────

def coverage_report(rows: list[dict], season: int, as_of_date: str, board_slug: str) -> None:
    n = len(rows)
    def _cnt(col: str) -> int:
        return sum(1 for r in rows if r.get(col) not in (None, ""))
    orgs = {r["org"] for r in rows if r.get("org")}
    positions = {r["position"] for r in rows if r.get("position")}
    log.info("──────── COVERAGE REPORT ────────")
    log.info("  board=%s  season=%d  as_of=%s", board_slug, season, as_of_date)
    log.info("  prospects (rows) ............ %d", n)
    if n:
        log.info("  with fg_minor_id ............ %d (%.0f%%)  ⭐ join key (→ leaderboard xMLBAMID / E7.4 xref)", _cnt("fg_minor_id"), 100 * _cnt("fg_minor_id") / n)
        log.info("  with mlbam_id ............... %d (%.0f%%)  (THE BOARD carries none by design — bridge via the leaderboard feed's xMLBAMID)", _cnt("mlbam_id"), 100 * _cnt("mlbam_id") / n)
        log.info("  with player_name ............ %d (%.0f%%)", _cnt("player_name"), 100 * _cnt("player_name") / n)
        log.info("  with FV ..................... %d (%.0f%%)", _cnt("fv"), 100 * _cnt("fv") / n)
        log.info("  with overall_rank / org_rank  %d / %d  (overall rank only for the top tier)",
                 _cnt("overall_rank"), _cnt("org_rank"))
        log.info("  with ETA .................... %d", _cnt("eta"))
        log.info("  with level .................. %d", _cnt("level"))
        log.info("  distinct orgs / positions ... %d / %d", len(orgs), len(positions))
    # Loud flag ONLY on the truly join-critical id (never silently zero — column-name-reality).
    # `mlbam_id` is EXPECTED-ABSENT on THE BOARD (it exposes no MLBAM id — verified 2018-2026), so it
    # is NOT flagged here (that warning was a false alarm every run); the MLBAM bridge is the
    # leaderboard feed's xMLBAMID joined on minorMasterId (or E7.4's xref).
    if n and _cnt("fg_minor_id") == 0:
        log.warning(
            "  ⚠️  fg_minor_id resolved 0/%d rows — the FanGraphs field casing likely changed. "
            "Inspect `raw_json` (or run --probe) and update FIELD_ALIASES['fg_minor_id'].", n,
        )
    log.info("─────────────────────────────────")


def probe(rows: list[dict]) -> None:
    """--probe: the ONE real pull. Print the real field names + 2 sample rows, write NOTHING —
    confirms the extraction against reality before any write (P0.1/N0.1 discipline)."""
    log.info("──────── PROBE (no write) ────────")
    log.info("  fetched %d raw prospect row(s)", len(rows))
    if not rows:
        log.warning("  ZERO rows — check draft slug / season / FLARESOLVERR_URL.")
        return
    keys = sorted({k for r in rows for k in r.keys()})
    log.info("  %d distinct field name(s) on the board:", len(keys))
    log.info("    %s", ", ".join(keys))
    for i, r in enumerate(rows[:2]):
        log.info("  sample row %d: %s", i, json.dumps(r, default=str)[:1200])
    # Show which alias each typed column would resolve to on this real payload.
    lc0 = _lc_map(rows[0])
    log.info("  alias resolution on row 0:")
    for col, aliases in FIELD_ALIASES.items():
        hit = next((a for a in aliases if a in lc0 and lc0[a] not in (None, "")), None)
        log.info("    %-14s → %s", col, f"{hit!r} = {lc0[hit]!r}" if hit else "‹NO MATCH — inspect keys above›")
    log.info("──────────────────────────────────")


# ── Fetch sources ────────────────────────────────────────────────────────────────

def fetch_board(season: int, draft: str | None) -> list[dict]:
    """Live board via the FlareSolverr-routed FanGraphs client."""
    try:
        from fangraphs_client import fetch_prospects_board
    except ImportError:  # pragma: no cover
        from utils.fangraphs_client import fetch_prospects_board
    result = fetch_prospects_board(season=season, draft=draft)
    return result["data"]


def fetch_from_csv(path: str) -> list[dict]:
    """Operator fallback: a manual Board CSV export → raw row dicts (same extraction applies)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.to_dict(orient="records")


def resolve_as_of_date(as_of: str | None, season: int, current_year: int,
                       current_game_date: str | None) -> tuple[str, bool]:
    """Resolve the snapshot date to stamp on the rows (E7.8 leakage-safe as-of dating).

    Returns ``(as_of_date, is_historical_guess)``:
      • explicit ``--as-of``  → use it verbatim (is_historical_guess=False).
      • CURRENT season, no --as-of → today's US game day (the daily-op case).
      • a PAST season with no --as-of → `<season>-07-01` (mid-season approx) + is_historical_guess
        True so main() WARNS. This is the safeguard: a historical `--season 2020` pull must NOT
        silently stamp TODAY (2026) — that poisons the very time-series E7.8's translation study
        needs. (FanGraphs serves the RETAINED version of a past board, not a true point-in-time
        snapshot; pass an explicit --as-of for the board's real date when known.)
    """
    if as_of:
        return as_of, False
    if season != current_year:
        return f"{season}-07-01", True
    return (current_game_date or date.today().isoformat()), False


# ── Main run ─────────────────────────────────────────────────────────────────────

def run(season: int, draft: str | None, as_of_date: str, mode: str, csv_path: str | None) -> None:
    ingested_at = datetime.now(timezone.utc).isoformat()

    if csv_path:
        log.info("Reading board from CSV: %s", csv_path)
        raw_rows = fetch_from_csv(csv_path)
    else:
        board_slug = draft or f"{season}prospect"
        log.info("Fetching THE BOARD via FanGraphs client — season=%d draft=%s", season, board_slug)
        raw_rows = fetch_board(season, draft)

    board_slug = draft or f"{season}prospect"

    if mode == "probe":
        probe(raw_rows)
        return

    rows = [extract_row(r, season, as_of_date, board_slug, ingested_at) for r in raw_rows]
    coverage_report(rows, season, as_of_date, board_slug)

    if mode == "dry-run":
        log.info("[DRY-RUN] %d row(s) built — NO S3 write.", len(rows))
        return

    if not rows:
        log.warning("No rows to write — skipping S3 write (empty board).")
        return

    n = write_partition(pd.DataFrame(rows), season, as_of_date)
    log.info("→ wrote %d prospect row(s) to %s  (season=%d, as_of=%s)",
             n, _table_uri(), season, as_of_date)


def parse_seasons(spec: str) -> list[int]:
    """'2020' → [2020]; '2019,2021' → [2019,2021]; '2018-2026' → [2018..2026]."""
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in spec.split(",") if s.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest FanGraphs THE BOARD → S3 Delta lakehouse (E7.7).")
    ap.add_argument("--season", type=int, default=date.today().year,
                    help="Board season year (default: current year).")
    ap.add_argument("--seasons", default=None,
                    help="Historical backfill: a range '2018-2026' or list '2019,2021' (overrides "
                         "--season). Each past season stamps as_of=<season>-07-01 (E7.8 as-of).")
    ap.add_argument("--draft", default=None,
                    help="Board slug (default: '<season>prospect', the main prospect board). "
                         "e.g. '2026mlb' for the draft board, '<season>int' for international.")
    ap.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                    help="Snapshot date stamped on the rows (default: today's US game day for the "
                         "current season; <season>-07-01 for a past season). Applies to --season "
                         "only (a --seasons backfill resolves as_of per season).")
    ap.add_argument("--probe", action="store_true",
                    help="THE ONE REAL PULL: print the live board's field names + sample rows and "
                         "the alias resolution, write NOTHING. Run this first.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch + extract + coverage report, but make NO S3 write.")
    ap.add_argument("--from-csv", default=None, metavar="PATH",
                    help="Operator fallback: read a manual Board CSV export instead of the API.")
    args = ap.parse_args()

    if args.seasons and args.as_of:
        ap.error("--as-of applies to a single --season; a --seasons backfill resolves as_of per season.")
    seasons = parse_seasons(args.seasons) if args.seasons else [args.season]

    try:
        from betting_ml.utils.game_day import current_game_date_iso
        game_date = current_game_date_iso()
    except Exception:  # noqa: BLE001 — laptop/dev without the pkg → plain today
        game_date = date.today().isoformat()

    mode = "probe" if args.probe else ("dry-run" if args.dry_run else "write")
    for season in seasons:
        # as_of: explicit → verbatim; current season → US game day; past season → mid-season approx.
        as_of_date, is_historical_guess = resolve_as_of_date(
            args.as_of, season, date.today().year, game_date)
        if is_historical_guess:
            log.warning(
                "Historical season %d with no --as-of → stamping as_of=%s (mid-season approximation). "
                "FanGraphs serves the RETAINED version of a past board, not a point-in-time snapshot; "
                "pass --as-of (single --season) for the board's true date (E7.8 leakage-safe joins).",
                season, as_of_date)
        log.info("FanGraphs prospect ingest (E7.7) — season=%d as_of=%s mode=%s%s",
                 season, as_of_date, mode, f" from-csv={args.from_csv}" if args.from_csv else "")
        try:
            run(season, args.draft, as_of_date, mode, args.from_csv)
        except Exception as exc:  # noqa: BLE001 — one bad season must not abort a multi-season backfill
            if len(seasons) == 1:
                raise
            log.warning("Season %d FAILED (%s) — continuing backfill.", season, exc)


if __name__ == "__main__":
    main()
