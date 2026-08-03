"""
ingest_mlb_season_hitting_to_s3.py   (E8.3 — the MLB-side RUNNING label → S3 Delta)
----------------------------------------------------------------------------------
Land one Delta table on S3 (SF-FREE, instance-role S3 auth):

    baseball/mlb/season_hitting  — one row per (season, player_id): the realized MLB
                                   season hitting line, including STOLEN BASES and
                                   CAUGHT STEALING.

⭐ WHY THIS EXISTS (the E8.3 blocker, found by inspection before any modelling).
E7.3's MLE label side reads `mart_batter_rolling_stats`, which is **Statcast-derived**
and carries only `woba/k_pct/bb_pct/iso` + PA. **There is no stolen-base column
anywhere in the served lakehouse** — `grep -rn 'stolen'` over `dbt/` returns only
catcher-framing and bullpen models, none of them a batter's running line. So the MiLB
feature side of an SB translation exists (E7.1's `bat_stolen_bases` /
`bat_caught_stealing`, populated 2005-2026 at all four levels, 0% null) while the MLB
LABEL side does not exist at all. Without this table an SB translation cannot be
fit, scored, or falsified — it would be UNDEFINED in the `cv_power` sense, which is
not a finding about running ability.

⭐ API reality (probed live 2026-08-02, not coded-to-docs — the E7.2/NF-D4 discipline):
  • `GET /api/v1/stats?stats=season&group=hitting&season=<Y>&sportId=1&playerPool=All`
    returns one split per player with `player.id`, `player.fullName`, and a `stat`
    block carrying `plateAppearances, atBats, hits, doubles, triples, homeRuns,
    baseOnBalls, hitByPitch, stolenBases, caughtStealing, gamesPlayed` — everything
    the SB-opportunity denominator needs, in ONE paged call per season.
  • `playerPool=All` is load-bearing: the default pool is QUALIFIED batters only, which
    would silently drop exactly the part-time speed players this story is about.
  • `limit`/`offset` page it; the API caps a page well below a full season's ~1,400
    batters, so the fetch pages until a short page comes back.
  • `stolenBasePercentage` is a STRING (".---" when the denominator is 0) — never
    parsed; the ratio is derived downstream from the two integer counts instead.

⚠️ THIS IS A SEASON-GRAIN TABLE, NOT A GAME LOG. That is deliberate and sufficient:
`build_graduated_pairs` already aggregates its MLB label at SEASON grain (the
season-to-date line at each season's last game, PA-weighted over the first
`label_window` seasons), so a season-grain running line joins at exactly the grain the
label is consumed on. A game-log ingest would be ~27k boxscore calls for information
the label never uses.

Storage / idempotency:
  • Delta via delta-rs through `scripts/utils/delta_lake.storage_options()` — the
    instance-role-safe S3 auth that dodges the AKID / empty-env-var landmine
    (CLAUDE.md boto3 + delta-rs object_store landmine).
  • Partitioned by `season`; a season is written with an overwrite predicate pinning
    it → idempotent + resumable at season grain. An already-present season is SKIPPED
    on backfill unless `--force`; the CURRENT season is always re-pulled (it is still
    accruing), mirroring the E7.1 trailing-lookback pattern.
  • Every row carries an ISO-UTC VARCHAR `ingestion_ts` (the lakehouse_raw convention;
    stored as VARCHAR so no binary-timestamp scale bite — INC-23. Cast at the use-site).

Usage (all SF-FREE — AWS creds via the instance role / env only):
    # Verification stub — one season, no write:
    uv run python scripts/ingest_mlb_season_hitting_to_s3.py --seasons 2024 --dry-run

    # Real single season:
    uv run python scripts/ingest_mlb_season_hitting_to_s3.py --seasons 2024

    # The E8.3 label window (LAPTOP; ~1 request-page per season, well under a minute):
    uv run python scripts/ingest_mlb_season_hitting_to_s3.py --seasons 2015-2026
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# scripts/utils reused for the instance-role-safe Delta S3 auth.
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
MLB_S3_PREFIX = "baseball/mlb"
SEASON_HITTING_TABLE = "season_hitting"

API = "https://statsapi.mlb.com/api/v1"
MLB_SPORT_ID = 1
PAGE_LIMIT = 1000
REQUEST_TIMEOUT = 60
RETRY_SLEEPS = (1, 3, 8)

# Statcast-era floor. The E7.3 label side keys debut cohorts off
# `mart_batter_rolling_stats`, which itself starts in 2015 — pulling deeper here would
# create graduates whose "debut cohort" is a censoring artifact rather than a debut.
EARLIEST_SEASON = 2015

# Stats API `stat` keys kept, camelCase → snake. Every one is an integer count; ratios
# are derived downstream so a ".---" string can never reach a numeric column.
HITTING_FIELDS: dict[str, str] = {
    "gamesPlayed": "games_played",
    "plateAppearances": "plate_appearances",
    "atBats": "at_bats",
    "runs": "runs",
    "hits": "hits",
    "doubles": "doubles",
    "triples": "triples",
    "homeRuns": "home_runs",
    "rbi": "rbi",
    "baseOnBalls": "walks",
    "intentionalWalks": "intentional_walks",
    "hitByPitch": "hit_by_pitch",
    "strikeOuts": "strike_outs",
    "stolenBases": "stolen_bases",
    "caughtStealing": "caught_stealing",
    "sacBunts": "sac_bunts",
    "sacFlies": "sac_flies",
    "groundIntoDoublePlay": "gidp",
    "totalBases": "total_bases",
}

PARTITION_COLS = ["season"]


# ── HTTP ───────────────────────────────────────────────────────────────────────


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "User-Agent": "credence-e8.3/1.0"})
    return s


def _get(session: requests.Session, path: str, params: dict) -> dict:
    """GET with bounded retries. Raises after the last attempt — an ingest that
    silently returns {} would land an EMPTY season partition over a good one."""
    url = f"{API}/{path}"
    last: Exception | None = None
    for i, sleep_s in enumerate((*RETRY_SLEEPS, None)):
        try:
            r = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 - retry on any transport/5xx failure
            last = e
            if sleep_s is None:
                break
            log.warning("GET %s attempt %d failed (%s) — retrying in %ss", path, i + 1, e, sleep_s)
            time.sleep(sleep_s)
    raise RuntimeError(f"GET {url} failed after {len(RETRY_SLEEPS) + 1} attempts: {last}")


def _int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ── Fetch + flatten ────────────────────────────────────────────────────────────


def fetch_season(session: requests.Session, season: int) -> list[dict]:
    """Every MLB batter's season hitting line for `season`, paged to exhaustion.

    ⚠️ `playerPool=All` is required — the API's default pool is QUALIFIED batters, which
    would drop the part-time / pinch-runner population that carries much of the league's
    stolen-base volume. Dropping them would bias the label toward everyday regulars and
    make the translation look better-behaved than it is.
    """
    rows: list[dict] = []
    seen: set[int] = set()
    offset = 0
    while True:
        payload = _get(session, "stats", {
            "stats": "season", "group": "hitting", "season": season,
            "sportId": MLB_SPORT_ID, "playerPool": "All",
            "limit": PAGE_LIMIT, "offset": offset,
        })
        splits = (payload.get("stats") or [{}])[0].get("splits") or []
        if not splits:
            break
        for sp in splits:
            row = _flatten_split(sp, season)
            if row is None or row["player_id"] in seen:
                continue
            seen.add(row["player_id"])
            rows.append(row)
        if len(splits) < PAGE_LIMIT:
            break
        offset += len(splits)
    log.info("season %d: %d batter season lines", season, len(rows))
    return rows


def _flatten_split(sp: dict, season: int) -> dict | None:
    person = sp.get("player") or {}
    pid = _int(person.get("id"))
    if pid is None:
        return None
    stat = sp.get("stat") or {}
    team = sp.get("team") or {}
    row: dict = {
        "season": int(season),
        "player_id": pid,
        "player_name": person.get("fullName"),
        "team_id": _int(team.get("id")),
        "team_name": team.get("name"),
        "position_abbrev": (sp.get("position") or {}).get("abbreviation"),
        "ingestion_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for api_col, staged in HITTING_FIELDS.items():
        row[staged] = _int(stat.get(api_col))
    return row


# ── Delta write layer (instance-role-safe S3 auth) ─────────────────────────────


def _table_uri(table: str) -> str:
    return f"s3://{BUCKET}/{MLB_S3_PREFIX}/{table}"


def _storage_options() -> dict:
    """delta-rs S3 storage_options with concrete resolved creds.

    ⚠️ Do NOT hand delta-rs the raw AWS_* env vars: object_store reads them itself, and
    compose interpolation of an unset host var lands an EMPTY STRING it signs with
    verbatim (empty AKID → 400). The shared resolver walks the botocore chain and passes
    explicit creds. CLAUDE.md delta-rs/Rust-object_store landmine.
    """
    try:
        from utils.delta_lake import storage_options
    except ImportError:  # pragma: no cover - path shape differs by caller
        from scripts.utils.delta_lake import storage_options
    return storage_options()


def existing_seasons(table: str) -> set[int]:
    """Seasons already present in the Delta table (empty if the table does not exist)."""
    from deltalake import DeltaTable

    try:
        dt = DeltaTable(_table_uri(table), storage_options=_storage_options())
    except Exception:  # noqa: BLE001 - a missing table is the normal first-run case
        return set()
    out: set[int] = set()
    for p in dt.partitions():
        try:
            out.add(int(p["season"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def write_season(table: str, df: pd.DataFrame, season: int) -> int:
    """Idempotently write ONE season partition (overwrite predicate pins the season)."""
    from deltalake import write_deltalake

    if df.empty:
        log.warning("season %d: nothing to write", season)
        return 0
    df = df.copy()
    df["season"] = int(season)
    write_deltalake(
        _table_uri(table), df, mode="overwrite",
        partition_by=PARTITION_COLS,
        predicate=f"season = {int(season)}",
        schema_mode="merge",
        storage_options=_storage_options(),
    )
    return len(df)


# ── CLI ────────────────────────────────────────────────────────────────────────


def parse_seasons(spec: str) -> list[int]:
    """`2024` or `2015-2026` → an inclusive season list, clamped to the API's floor."""
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        seasons = list(range(int(a), int(b) + 1))
    else:
        seasons = [int(spec)]
    keep = [s for s in seasons if s >= EARLIEST_SEASON]
    if len(keep) != len(seasons):
        log.warning("clamped seasons below %d (the Statcast-era label floor)", EARLIEST_SEASON)
    return keep


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="E8.3 — ingest MLB season hitting lines (incl. SB/CS) to the S3 Delta lakehouse")
    p.add_argument("--seasons", default=f"{EARLIEST_SEASON}-{datetime.now(timezone.utc).year}",
                   help="season or inclusive range, e.g. 2024 or 2015-2026")
    p.add_argument("--force", action="store_true",
                   help="re-pull seasons already present (a present season is skipped by default)")
    p.add_argument("--dry-run", action="store_true", help="fetch + summarize, write nothing")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    if args.verbose:
        log.setLevel(logging.DEBUG)

    seasons = parse_seasons(args.seasons)
    if not seasons:
        log.error("no seasons to ingest")
        return 1

    current_season = datetime.now(timezone.utc).year
    present = set() if (args.force or args.dry_run) else existing_seasons(SEASON_HITTING_TABLE)
    session = _session()
    total = 0
    for season in seasons:
        # the current season is always re-pulled: it is still accruing
        if season in present and season != current_season:
            log.info("season %d already present — skipping (use --force to re-pull)", season)
            continue
        rows = fetch_season(session, season)
        df = pd.DataFrame(rows)
        if args.dry_run:
            if not df.empty:
                sb = int(pd.to_numeric(df["stolen_bases"], errors="coerce").fillna(0).sum())
                cs = int(pd.to_numeric(df["caught_stealing"], errors="coerce").fillna(0).sum())
                log.info("DRY-RUN season %d: %d players, %d SB, %d CS", season, len(df), sb, cs)
            continue
        n = write_season(SEASON_HITTING_TABLE, df, season)
        total += n
        log.info("season %d: wrote %d rows to %s", season, n, _table_uri(SEASON_HITTING_TABLE))

    log.info("done — %d rows written across %d season(s)", total, len(seasons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
