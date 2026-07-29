"""
ingest_mlb_pipeline_to_s3.py   (E7.11 — MLB Pipeline prospect rankings → S3 Delta lakehouse)
---------------------------------------------------------------------------------------------
Ingest **MLB Pipeline** (MLB.com) prospect rankings — the Top 100 plus all 30 organizational
Top 30s, ~900 ranked players — as a free SECOND scouting source alongside FanGraphs THE BOARD
(E7.7). SF-FREE, instance-role S3 auth, the E7.1/E7.7 Delta-write pattern.

    baseball/milb/mlb_pipeline_rankings   — one row per (as_of_date, season, list_name, rank)

⭐ WHY THIS SOURCE, AND WHY IT IS CHEAP: every ranked entry references `Person:<id>`, and that id
IS the MLBAM `person.id` — the spine `dim_player_xref` is keyed on (E7.4). So this second opinion
joins to our board with **zero name matching**, which is exactly the leg E7.4 refused to build.

🚦 ACCESS DISCIPLINE — READ `betting_ml/scripts/prospect_board/mlb_pipeline.py`'s module docstring.
Short version, verified live 2026-07-29:
  • `/prospects/…` on www.mlb.com is NOT robots-disallowed → fetched as an ordinary page read.
  • `data-graph.mlb.com` (the JSON API the page's own JS calls) IS `Disallow: /` → **never called.**
  • This script re-reads `https://www.mlb.com/robots.txt` on EVERY run and REFUSES to fetch if
    `/prospects/` becomes disallowed (`--ignore-robots` exists only so an operator can run against
    a local `--from-dir` cache without a network round-trip; it does not bypass a live fetch).
  • No credentials, no login, nothing paywalled. Paywalled sources (Baseball America, Keith Law,
    ESPN/McDaniel, Baseball Prospectus) and Prospects Live (robots: `ClaudeBot Disallow: /`) are
    handled as MANUAL hand-keyed second opinions in `build_consensus.py --manual`, never scraped.

⏳ POLITENESS: 31 page fetches (Top 100 + 30 orgs), serialized, with a delay between them
(`--delay`, default 1.5 s) → ~1 minute wall-clock. Rankings move on a weekly-ish cadence, so this
is a hand-run job, NOT a daily op — it is deliberately not wired into any Dagster schedule.

AS-OF DATING (the E7.7 contract, reused): each pull stamps `as_of_date` and partitions by
(season, as_of_date), so snapshots accumulate and a re-run on the same day is an idempotent
partition overwrite. `ingested_at_utc` is an ISO-UTC VARCHAR (INC-23: cast at the use-site).

Usage (LAPTOP; ~1 min for a full run):
    # PROBE FIRST — fetch ONE list, print the parsed shape + robots verdict, write NOTHING:
    uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026 --probe

    # Full snapshot (Top 100 + all 30 org Top 30s) → S3 Delta:
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026

    # Fetch + coverage report, no S3 write:
    uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026 --dry-run

    # Save the raw pages while fetching (then re-parse offline, no network):
    uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026 --cache-dir /tmp/pipeline_2026
    uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026 --from-dir /tmp/pipeline_2026

🕰️ HISTORICAL BACKFILL (the substrate for an accuracy study — "were these rankings any good?")
MLB serves archived rankings back to **2010**; the ranks are genuinely point-in-time (the 2015 list
opens Buxton / Bryant / Correa). Two traps, both handled — see `mlb_pipeline.py`'s docstring:
  • the page's `Person`/`Team` entities are LIVE, so age/org come back as of the FETCH → they are
    suffixed `_current` and must never be used as as-of features;
  • the bio list runs PAST the season → grades are taken from the season's own report, never a
    later one, with `bio_season` stamped as the receipt.
`--seasons` stamps each PAST season `as_of=<season>-02-01`, never today (stamping a 2015 board as
today would place it after every outcome it is meant to predict). 2010–2011 are Top **50**, not
Top 100 — absence from those lists is a weaker statement, and the run warns.

    # Top-100 history only (17 seasons × 1 page ≈ 30 s) — the accuracy-study substrate:
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py \
        --seasons 2010-2025 --lists top100

    # Full history incl. org lists (17 × 31 pages ≈ 15 min — hand this to the operator):
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py \
        --seasons 2010-2025
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))

from betting_ml.scripts.prospect_board.mlb_pipeline import (  # noqa: E402
    ORG_LIST_DEPTH_BY_ERA,
    ORG_SLUG_TO_ABBREV,
    PIPELINE_SOURCE,
    TOP100_LIST,
    PipelineParseError,
    list_slug,
    parse_rankings_page,
    robots_disallows,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

BUCKET = "baseball-betting-ml-artifacts"
REGION = "us-east-2"
S3_PREFIX = "baseball/milb"
TABLE = "mlb_pipeline_rankings"
PARTITION_COLS = ["season", "as_of_date"]

BASE_URL = "https://www.mlb.com"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

ALL_LISTS: list[str] = [TOP100_LIST, *sorted(ORG_SLUG_TO_ABBREV)]

# Columns pinned to string even when a whole pull is None. An all-None object column makes pyarrow
# infer the `null` type, Delta records it as `"void"`, and DuckDB's delta reader then hard-errors
# on the WHOLE table for every consumer — the exact failure that made THE BOARD unreadable by
# `delta_scan` (E7.4 landmine 1). Pin at the writer; one place heals every reader.
_STRING_PINNED = [
    "source", "list_name", "list_type", "mlbam_id", "player_name", "position", "org",
    "org_current", "affiliate_team_current", "parent_org_name_current", "birth_date",
    "bats", "throws", "as_of_date", "ingested_at_utc",
]

# The earliest season MLB serves a ranking for, and the seasons whose list is only 50 deep.
# Probed live 2026-07-29: 2008 → empty selection; 2010/2011 → 50 entries; 2012+ → 100.
EARLIEST_SEASON = 2010
TOP50_SEASONS = frozenset({2010, 2011})


class PipelineIngestError(RuntimeError):
    """A fetch/robots/coverage invariant failed — never a silent partial ingest."""


class PipelineListUnavailable(RuntimeError):
    """This season genuinely publishes no such list — a COVERAGE fact, not a failure.

    Distinguished from a parse failure on purpose. A 2010 backfill that finds no org Top 30s has
    learned something true about 2010; a 2026 run that finds no Orioles list has hit a bug. Only
    the second may abort the write.
    """


def parse_seasons(spec: str) -> list[int]:
    """`'2015'` → [2015] · `'2019,2021'` → [2019, 2021] · `'2012-2026'` → [2012..2026]."""
    spec = str(spec).strip()
    if "-" in spec:
        start, _, end = spec.partition("-")
        return list(range(int(start), int(end) + 1))
    return [int(part) for part in spec.split(",") if part.strip()]


def resolve_as_of_date(as_of: str | None, season: int, current_year: int,
                       today_iso: str) -> tuple[str, bool]:
    """The snapshot date to stamp. Returns `(as_of_date, is_historical_guess)`.

    🚨 A HISTORICAL PULL MUST NOT BE STAMPED WITH TODAY'S DATE. `as_of_date` is what makes these
    rankings usable for a leakage-safe as-of join — stamping a 2015 board as 2026-07-29 would place
    a decade-old opinion after every outcome it is supposed to predict, silently inverting any
    accuracy study built on it. So a past season defaults to `<season>-02-01` (MLB Pipeline
    publishes its Top 100 in the preseason) and the caller WARNS; pass `--as-of` for the list's true
    publication date when you know it. Same contract as the E7.7 FanGraphs ingest.
    """
    if as_of:
        return as_of, False
    if season != current_year:
        return f"{season}-02-01", True
    return today_iso, False


# ── Fetch (robots-gated) ─────────────────────────────────────────────────────────

def fetch_robots() -> str:
    import requests
    resp = requests.get(ROBOTS_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def assert_robots_allows(robots_txt: str, paths: list[str]) -> None:
    """HARD stop if any list path is disallowed.

    Mechanical on purpose: a note in a docstring gets skimmed, a raise does not. If MLB adds
    `/prospects/` to its Disallow list, this ingest must stop existing — not degrade, not retry
    against the API host (`data-graph.mlb.com` is `Disallow: /`).
    """
    blocked = [p for p in paths if robots_disallows(robots_txt, p)]
    if blocked:
        raise PipelineIngestError(
            f"robots.txt now DISALLOWS {blocked[:5]} (of {len(blocked)}) — this ingest is no longer "
            f"permitted and must be retired, not worked around. MLB Pipeline then becomes a MANUAL "
            f"second opinion like the paywalled sources (`build_consensus.py --manual`)."
        )


def fetch_page(season: int, list_name: str) -> str:
    import requests
    url = f"{BASE_URL}{list_slug(season, list_name)}"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp.text


def load_page(season: int, list_name: str, *, from_dir: Path | None,
              cache_dir: Path | None) -> str:
    """A page, from the offline cache if one was given, else from the network (then cached)."""
    fname = f"{season}_{list_name}.html"
    if from_dir is not None:
        path = from_dir / fname
        if not path.exists():
            raise PipelineIngestError(
                f"--from-dir is missing {path}. Re-run the fetch with --cache-dir {from_dir} first; "
                f"a missing page must NOT silently become an unranked organization."
            )
        return path.read_text(encoding="utf-8")
    html_text = fetch_page(season, list_name)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / fname).write_text(html_text, encoding="utf-8")
    return html_text


# ── Delta write ──────────────────────────────────────────────────────────────────

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


def write_partition(df: pd.DataFrame, season: int, as_of_date: str) -> int:
    from deltalake import write_deltalake
    df = df.copy()
    df["season"] = int(season)
    df["as_of_date"] = str(as_of_date)
    for col in _STRING_PINNED:
        if col in df.columns:
            df[col] = df[col].astype("string")
    table_arrow = pa.Table.from_pandas(df, preserve_index=False)
    kwargs = dict(storage_options=_storage_options())
    if not _table_exists():
        write_deltalake(_table_uri(), table_arrow, mode="overwrite",
                        partition_by=PARTITION_COLS, **kwargs)
    else:
        write_deltalake(
            _table_uri(), table_arrow, mode="overwrite",
            predicate=f"season = {int(season)} AND as_of_date = '{as_of_date}'",
            schema_mode="merge", **kwargs,
        )
    return len(df)


# ── Coverage report (the AC deliverable) ─────────────────────────────────────────

def coverage_report(rows: list[dict], season: int, as_of_date: str,
                    requested: list[str] | None = None) -> dict:
    """Per-list coverage + the id/grade population rates. Printed AND returned for the handoff."""
    frame = pd.DataFrame(rows)
    n = len(frame)
    rep: dict = {"source": PIPELINE_SOURCE, "season": int(season), "as_of_date": as_of_date,
                 "rows": int(n)}
    log.info("──────── E7.11 MLB PIPELINE COVERAGE ────────")
    log.info("  season=%d  as_of=%s  rows=%d", season, as_of_date, n)
    if not n:
        log.warning("  ZERO rows.")
        return rep

    grade_cols = [c for c in frame.columns if c.startswith("pipeline_grade_")]
    rep["lists"] = int(frame["list_name"].nunique())
    rep["orgs"] = int(frame["org"].nunique(dropna=True))
    rep["distinct_players"] = int(frame["mlbam_id"].nunique(dropna=True))
    rep["with_mlbam_id"] = int(frame["mlbam_id"].notna().sum())
    rep["with_mlbam_id_rate"] = round(rep["with_mlbam_id"] / n, 4)
    rep["with_org"] = int(frame["org"].notna().sum())
    rep["with_any_grade"] = (int(frame[grade_cols].notna().any(axis=1).sum()) if grade_cols else 0)
    rep["grade_columns"] = sorted(grade_cols)
    # Compared against what was REQUESTED, not against all 31 — a deliberate `--lists top100`
    # run is not missing 30 organizations, and a warning that cries wolf gets ignored.
    wanted = set(requested) if requested else set(ALL_LISTS)
    rep["missing_lists"] = sorted(wanted - set(frame["list_name"].unique()))
    top100 = frame[frame["list_type"] == "top100"]
    rep["top_list_depth"] = int(top100["rank"].max()) if not top100.empty else 0
    org_rows = frame[frame["list_type"] == "org"]
    # The OBSERVED depth is authoritative — a study must normalize ranks by it, not assume 30.
    rep["org_list_depth"] = int(org_rows["rank"].max()) if not org_rows.empty else 0
    # ⭐ Which year's scouting report each grade came from. On a historical pull this is the
    # anti-leakage receipt: a `bio_season` greater than `season` would mean a future report was
    # used to grade a past ranking, so it is reported rather than trusted.
    if "bio_season" in frame.columns:
        graded = frame[frame["bio_season"].notna()]
        rep["bio_season_matches_snapshot"] = int((graded["bio_season"] == season).sum())
        rep["bio_season_after_snapshot"] = int((graded["bio_season"] > season).sum())

    log.info("  lists ....................... %d / %d", rep["lists"], len(wanted))
    log.info("  published depth ............. overall top %d / org top %d   ⭐ NORMALIZE a study by "
             "THIS, not by 30", rep["top_list_depth"], rep["org_list_depth"])
    log.info("  distinct ranked players ..... %d", rep["distinct_players"])
    log.info("  with MLBAM id ............... %d (%.1f%%)  ⭐ the spine key — no name matching",
             rep["with_mlbam_id"], 100 * rep["with_mlbam_id_rate"])
    log.info("  with org (point-in-time) .... %d   [org lists only; a Top-100 entry has no org of "
             "its own — see org_current]", rep["with_org"])
    log.info("  with ≥1 scouting grade ...... %d  (parsed from PROSE, best-effort)",
             rep["with_any_grade"])
    if "bio_season_matches_snapshot" in rep:
        log.info("  grades from the season's own report: %d   (from a LATER report: %d)",
                 rep["bio_season_matches_snapshot"], rep["bio_season_after_snapshot"])
    if rep.get("bio_season_after_snapshot"):
        log.warning("  ⚠️ %d row(s) graded off a report written AFTER %d — that is hindsight in a "
                    "point-in-time row. `_select_bio` should make this impossible; investigate.",
                    rep["bio_season_after_snapshot"], season)
    if rep["missing_lists"]:
        log.warning("  ⚠️ MISSING LISTS: %s — those organizations are absent from the consensus.",
                    rep["missing_lists"])
    # The id is the whole reason this source is ingestible; a drop here is a dead bridge, not noise.
    if rep["with_mlbam_id_rate"] < 0.99:
        log.warning("  ⚠️ only %.1f%% of rows carry an MLBAM id — MLB likely changed the embedded "
                    "cache shape. Re-run --probe before trusting the consensus.",
                    100 * rep["with_mlbam_id_rate"])
    log.info("─────────────────────────────────────────────")
    return rep


# ── Run ──────────────────────────────────────────────────────────────────────────

def run(season: int, as_of_date: str, mode: str, lists: list[str], *, delay: float,
        from_dir: Path | None, cache_dir: Path | None, ignore_robots: bool) -> dict:
    ingested_at = datetime.now(timezone.utc).isoformat()

    if from_dir is None and not ignore_robots:
        robots = fetch_robots()
        assert_robots_allows(robots, [list_slug(season, ln) for ln in lists])
        log.info("robots.txt ✓ — /prospects/ is permitted for User-agent: * "
                 "(data-graph.mlb.com stays untouched: it is Disallow: /)")

    rows: list[dict] = []
    failures: list[tuple[str, str]] = []
    unavailable: list[str] = []
    for idx, list_name in enumerate(lists):
        try:
            page = load_page(season, list_name, from_dir=from_dir, cache_dir=cache_dir)
            parsed = parse_rankings_page(page, season=season, list_name=list_name)
        except PipelineParseError as exc:
            # ⚠️ TWO DIFFERENT THINGS LOOK ALIKE HERE. "This season publishes no such list" is a
            # COVERAGE FACT (MLB serves no org Top 30s before ~2012, and nothing at all before
            # 2010); "the payload moved" is a BUG. Only the second may abort the write, or a
            # historical backfill could never complete. The parser's own message distinguishes
            # them: an absent/empty selection vs a structural failure.
            message = str(exc)
            if "no ranking payload" in message or "EMPTY ranking" in message:
                unavailable.append(list_name)
                log.info("  %-12s (not published for %d)", list_name, season)
            else:
                failures.append((list_name, message[:200]))
                log.warning("  %-12s FAILED: %s", list_name, message[:200])
            if from_dir is None and idx < len(lists) - 1:
                time.sleep(delay)
            continue
        except Exception as exc:  # noqa: BLE001 — one bad list is collected, never silently skipped
            failures.append((list_name, str(exc)[:200]))
            log.warning("  %-12s FAILED: %s", list_name, str(exc)[:200])
            continue
        for row in parsed:
            row["season"] = int(season)
            row["as_of_date"] = as_of_date
            row["ingested_at_utc"] = ingested_at
        rows.extend(parsed)
        log.info("  %-12s %3d ranked", list_name, len(parsed))
        if mode == "probe":
            log.info("  PROBE — first row: %s", json.dumps(parsed[0], default=str)[:900])
            break
        if from_dir is None and idx < len(lists) - 1:
            time.sleep(delay)

    if mode == "probe":
        log.info("PROBE complete — nothing written. Robots verdict above; parsed shape printed.")
        return {"mode": "probe", "rows": len(rows), "failures": failures}

    rep = coverage_report(rows, season, as_of_date, requested=lists)
    rep["failed_lists"] = failures
    rep["unpublished_lists"] = unavailable
    if unavailable:
        log.info("  %d list(s) are not published for %d — recorded as coverage, not failure.",
                 len(unavailable), season)
    if failures:
        # A missing org is a SILENT coverage hole in the consensus (that org's players simply never
        # get a Pipeline rank and look "unranked"), so a partial run refuses to write.
        raise PipelineIngestError(
            f"{len(failures)} list(s) failed to parse: {[f[0] for f in failures]}. Refusing to "
            f"write a PARTIAL snapshot — an absent organization is indistinguishable downstream "
            f"from 'Pipeline chose not to rank these players'. Fix and re-run."
        )

    if mode == "dry-run":
        log.info("[DRY-RUN] %d row(s) built — NO S3 write.", len(rows))
        return rep

    if not rows:
        raise PipelineListUnavailable(
            f"season {season} publishes no rankings at all (MLB serves none before "
            f"{EARLIEST_SEASON}) — nothing written."
        )
    written = write_partition(pd.DataFrame(rows), season, as_of_date)
    log.info("→ wrote %d ranking row(s) to %s  (season=%d, as_of=%s)",
             written, _table_uri(), season, as_of_date)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Ingest MLB Pipeline prospect rankings → S3 Delta lakehouse (E7.11).")
    ap.add_argument("--season", type=int, default=date.today().year)
    ap.add_argument("--seasons", default=None,
                    help=f"Historical backfill: a range '{EARLIEST_SEASON}-2026' or a list "
                         f"'2015,2019' (overrides --season). Each PAST season stamps "
                         f"as_of=<season>-02-01 (the preseason publication window) so an as-of "
                         f"join stays leakage-safe. MLB serves nothing before {EARLIEST_SEASON}; "
                         f"{sorted(TOP50_SEASONS)} are Top 50, not Top 100.")
    ap.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                    help="Snapshot date stamped on the rows (default: today's US game day for the "
                         "current season; <season>-02-01 for a past one). Single --season only.")
    ap.add_argument("--lists", default=None,
                    help="Comma-separated list names (default: top100 + all 30 orgs). "
                         f"Valid: top100, {', '.join(sorted(ORG_SLUG_TO_ABBREV))}")
    ap.add_argument("--probe", action="store_true",
                    help="Fetch ONE list, print the robots verdict + parsed shape, write NOTHING.")
    ap.add_argument("--dry-run", action="store_true", help="Fetch + report, make NO S3 write.")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="Seconds between page fetches (politeness; default 1.5).")
    ap.add_argument("--cache-dir", default=None,
                    help="Also save each fetched page here (for offline re-parsing).")
    ap.add_argument("--from-dir", default=None,
                    help="Parse pages from this directory instead of fetching (no network).")
    ap.add_argument("--ignore-robots", action="store_true",
                    help="Skip the live robots re-check. ONLY for an offline --from-dir re-parse; "
                         "it does not make a disallowed fetch permitted.")
    args = ap.parse_args()

    lists = ([s.strip() for s in args.lists.split(",") if s.strip()] if args.lists else ALL_LISTS)
    unknown = [ln for ln in lists if ln != TOP100_LIST and ln not in ORG_SLUG_TO_ABBREV]
    if unknown:
        ap.error(f"unknown list name(s): {unknown}")
    if args.seasons and args.as_of:
        ap.error("--as-of applies to a single --season; a --seasons backfill resolves as_of per "
                 "season (a shared date would stamp every historical board with one timestamp).")
    seasons = parse_seasons(args.seasons) if args.seasons else [args.season]
    too_early = [s for s in seasons if s < EARLIEST_SEASON]
    if too_early:
        log.warning("MLB serves no rankings before %d — %s will be skipped as unavailable.",
                    EARLIEST_SEASON, too_early)

    try:
        from betting_ml.utils.game_day import current_game_date_iso
        today = current_game_date_iso()
    except Exception:  # noqa: BLE001 — laptop/dev without the pkg → plain today
        today = date.today().isoformat()

    mode = "probe" if args.probe else ("dry-run" if args.dry_run else "write")
    for season in seasons:
        as_of_date, is_historical_guess = resolve_as_of_date(
            args.as_of, season, date.today().year, today)
        if is_historical_guess:
            log.warning(
                "Historical season %d with no --as-of → stamping as_of=%s (MLB Pipeline's "
                "preseason publication window). NOT today's date: stamping a %d board as %s would "
                "place a decade-old opinion AFTER every outcome it is meant to predict and would "
                "silently invert any accuracy study built on it.",
                season, as_of_date, season, today)
        if season in TOP50_SEASONS:
            log.warning("Season %d publishes a Top **50**, not a Top 100 — absence from that list "
                        "means 'outside the top 50', which is NOT the same statement as the other "
                        "seasons' lists make. Record it before comparing depths across seasons.",
                        season)
        if season < 2015:
            log.warning("Season %d's ORG lists are shallower than today's Top 30 (%s) — an org rank "
                        "of 15 is not the same statement across eras, and absence means 'outside "
                        "the top N' for that era's N. See ORG_LIST_DEPTH_BY_ERA.",
                        season, ORG_LIST_DEPTH_BY_ERA)
        log.info("MLB Pipeline ingest (E7.11) — season=%d as_of=%s mode=%s lists=%d",
                 season, as_of_date, mode, len(lists))
        try:
            run(season, as_of_date, mode, lists,
                delay=args.delay,
                from_dir=Path(args.from_dir) if args.from_dir else None,
                cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                ignore_robots=args.ignore_robots)
        except PipelineListUnavailable as exc:
            log.warning("Season %d: %s", season, exc)
        except Exception as exc:  # noqa: BLE001 — one bad season must not abort a backfill
            if len(seasons) == 1:
                raise
            log.warning("Season %d FAILED (%s) — continuing backfill.", season, exc)


if __name__ == "__main__":
    main()
