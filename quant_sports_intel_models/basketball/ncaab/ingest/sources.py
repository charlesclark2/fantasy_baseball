"""sources.py — the NCAAB lake table registry (NCAAB-P0 node 3).

The ONE NCAAB-specific file in the ingest package: source -> fetch fn -> grain -> partition ->
cadence. Everything else (the Delta write layer, the DuckDB lake auth) is imported through
`lake.py` from the shared owner — see this package's `__init__` for why nothing is copied.

FEED CHOICES, and the measurements behind them (`ablation_results/ncaab_p0_source_audit.json`):

  hoopR (sportsdataverse/hoopR-mbb-data) is the spine. Measured: 24 fully-scored seasons
  (2003-2026) plus 2027 already populated; 366 distinct D-I home teams in 2026, corroborated
  INDEPENDENTLY by ESPN's core API D-I group returning exactly 366; every NCAAF-parity MVP
  field present; the possession identity's four operands present from 2003. Licensed CC BY 4.0
  (attribution required — see ATTRIBUTION). It is published as raw parquet on
  raw.githubusercontent.com, so it reads exactly like nflverse does: DuckDB over HTTPS, no
  package dependency (the `nfl_data_py` lesson).

  The Odds API supplies the market. NCAAB futures are live NOW and game lines post as the
  season approaches. Unit prices are measured in `budget.py`, not quoted.

⏱️ THE POINT-IN-TIME PROPERTY IS OURS TO CREATE, and it is the reason every fetcher here
stamps `capture_timestamp` itself. hoopR offers no as-of and no vintage: a completed season's
file is stable, but the CURRENT season's file is REWRITTEN IN PLACE continuously (measured:
>=100 commits to the 2026 schedule across one season). So "what did the schedule say on
December 3rd" is unanswerable from the source and answerable from OUR lake, because each
ingest lands a content-timestamped Delta version and Delta time-travel is then the as-of.
⛔ The stamp is the FETCH time, never a file mtime — an mtime is a property of the copy, not
of the content, and a re-mirror refreshes it while the data stands still (INC-41).

🚨 ZERO ROWS ON AN EXPECTED-DATA DAY IS AN ESCALATION, NOT A SKIP. `expect_rows` marks the
sources for which an empty landing during the active season is a defect. The repo's signature
failure is "0 rows, no error", and a registry that let an empty parquet land quietly would
reproduce it on day one of a new vertical.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from . import budget
from .lake import SPORT  # noqa: F401 — re-exported; the sport prefix has one owner

log = logging.getLogger(__name__)

ODDS_BASE = "https://api.the-odds-api.com/v4"
HOOPR_RAW = "https://raw.githubusercontent.com/sportsdataverse/hoopR-mbb-data/main/mbb"

#: CC BY 4.0 requires attribution wherever the data is displayed. Carried here so the serving
#: story (P3) inherits an obligation it cannot discover by reading a licence file it never opens.
ATTRIBUTION = ("Game data via hoopR (sportsdataverse/hoopR-mbb-data), CC BY 4.0. "
               "Market data via The Odds API.")

#: The earliest season hoopR publishes. Measured, not assumed.
FIRST_HOOPR_SEASON = 2003
#: `neutral_site` is identically 0 before this season — an ABSENCE, not a False. Any training
#: window reaching earlier must treat the flag as missing (the MH2.1 per-column-absence rule).
FIRST_SEASON_WITH_NEUTRAL_SITE = 2008


class IngestRefusal(RuntimeError):
    """A fetch refused to proceed. Loud, never a silent empty."""


class NotYetPublished(IngestRefusal):
    """The upstream file for this season does not exist YET.

    ⭐ A THIRD STATE, and the run that produced it is why it exists. hoopR publishes
    `mbb_schedule_<season>.parquet` as soon as a schedule is announced but does not publish
    `team_box_<season>.parquet` until games have actually been played, so between roughly July
    and the first tip the box-score file 404s every single day. That is not an outage, and the
    daily job must not page about it for four months — a monitor that cries wolf all pre-season
    is a monitor that gets muted before the season it exists to watch.

    But collapsing it into "fine" is the opposite error: the SAME 404 in February is a real
    feed failure. So it is its own state, and `check_landing` decides by the calendar which
    one is in front of it.
    """


@dataclass
class Ctx:
    """Run configuration + a lazy DuckDB connection for the hoopR parquet reads."""

    odds_api_key: str | None = None
    odds_regions: str = "us"
    odds_sleep_seconds: float = 0.34
    #: The per-event fan-out ceiling. Enforced by budget.guard_fan_out — see budget.py for why
    #: a per-event loop over an NCAAB board is 105x the price of the bulk call.
    fan_out_ceiling: int = budget.DEFAULT_FAN_OUT_CEILING
    credits_used: int | None = None
    credits_remaining: int | None = None
    _duck: Any = None

    def duck(self):
        if self._duck is None:
            import duckdb

            con = duckdb.connect()
            con.execute("INSTALL httpfs; LOAD httpfs")
            self._duck = con
        return self._duck


@dataclass
class SourceSpec:
    """One lake table's ingest contract."""

    name: str
    fetch: Callable[..., Any]
    tier: str                      # hoopr | odds
    grain: str                     # game | team_game | board
    typed: bool = False            # True -> a DataFrame path (write_dataframe)
    cadence: str = "daily"         # daily | intraday | seasonal
    on_demand: bool = False        # excluded from a default run (the paid /historical feeds)
    expect_rows: bool = True       # an empty landing in-season is an ESCALATION
    freshness_hours: int | None = None
    notes: str = ""


def now_iso() -> str:
    """The capture stamp. UTC, ISO, second resolution — a CONTENT timestamp, never an mtime."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── season semantics ────────────────────────────────────────────────────────────────────
def season_for(d: date | None = None) -> int:
    """hoopR's season label for a calendar date.

    NCAAB spans a calendar-year boundary and hoopR labels a season by the year it ENDS: the
    2026-27 season is `2027`. Getting this backwards silently ingests the wrong file, and the
    file exists either way, so nothing errors — it just quietly loads last season. The cut is
    taken at June 30: everything from July onward belongs to the season ending next year.
    """
    d = d or datetime.now(timezone.utc).date()
    return d.year + 1 if d.month >= 7 else d.year


def in_season(d: date | None = None) -> bool:
    """Is the D-I season active? Used to decide whether an empty landing is a defect.

    November through early April. Deliberately generous at both ends: the cost of calling a
    quiet day "in season" is one investigated warning, and the cost of the reverse is a silent
    hole on a real game day.
    """
    d = d or datetime.now(timezone.utc).date()
    return d.month in (11, 12, 1, 2, 3) or (d.month == 4 and d.day <= 10)


# ── hoopR fetchers (typed parquet over HTTPS — the nflverse pattern) ────────────────────
def _hoopr_parquet(ctx: Ctx, url: str, label: str):
    """Read one hoopR parquet into a DataFrame and stamp the capture time.

    Per-source parser by construction: the URL and the expected shape belong to this feed and
    nothing else reuses them. A reader shared across feeds is how a silently-zero-row parse
    happens (the reused-regex class).
    """
    con = ctx.duck()
    try:
        df = con.execute(f"SELECT * FROM read_parquet('{url}')").df()
    except Exception as exc:  # noqa: BLE001
        # A 404 means the file is ABSENT, which is a different fact from a read that failed —
        # and the two must not be reported alike. Matching on the status token rather than on
        # the whole message so a DuckDB wording change cannot silently reclassify an absence
        # as an outage (or vice versa).
        if "404" in str(exc):
            raise NotYetPublished(
                f"{label}: {url} is not published yet (HTTP 404)."
            ) from exc
        raise IngestRefusal(f"{label}: could not read {url} — {type(exc).__name__}: {exc}") from exc
    df["capture_timestamp"] = now_iso()
    df["source_url"] = url
    return df


def hoopr_schedule(ctx: Ctx, season: int):
    return _hoopr_parquet(ctx, f"{HOOPR_RAW}/schedules/parquet/mbb_schedule_{season}.parquet",
                          f"hoopr_schedule[{season}]")


def hoopr_team_crosswalk(ctx: Ctx, season: int):
    """hoopR's team crosswalk — the D-I universe WITH conference NAMES, and the keys to the
    efficiency sources the roadmap assumed might have to be bought.

    Measured (2026): 362 rows x 21 cols carrying `espn_team_id`, `espn_display_name`,
    `espn_conference` (the conference NAME, which the per-game feed gives only as a numeric
    id), and — the part that changes the spend conversation — `kp_team`/`kp_conf` and
    `bart_team`/`bart_conf`, i.e. ready join keys to KenPom and Bart Torvik. So if the operator
    ever does buy an efficiency source, the crosswalk to it already exists and is CC BY 4.0;
    and until then, conference names come from a licensed feed rather than from ESPN's
    undeclared-terms API or a hardcoded map that would rot at the next realignment.

    ⚠️ Published for the CURRENT season only (one file, no history). Historical conference
    membership therefore comes from the per-season ids on the schedule feed, with this file
    supplying the id -> name resolution. Do not assume a season's file exists.
    """
    return _hoopr_parquet(
        ctx, f"{HOOPR_RAW}/crosswalk/parquet/mbb_team_crosswalk_{season}.parquet",
        f"hoopr_team_crosswalk[{season}]")


def hoopr_team_box(ctx: Ctx, season: int):
    return _hoopr_parquet(ctx, f"{HOOPR_RAW}/team_box/parquet/team_box_{season}.parquet",
                          f"hoopr_team_box[{season}]")


# ── Odds API fetchers ───────────────────────────────────────────────────────────────────
def _odds_get(ctx: Ctx, path: str, params: dict) -> tuple[list[dict], dict]:
    """One Odds-API GET -> (records, meta). Records the credit headers onto `ctx`."""
    import requests

    key = ctx.odds_api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        raise IngestRefusal(
            "ODDS_API_KEY is not set — refusing rather than landing an empty odds partition "
            "that would be indistinguishable from a quiet market.")
    resp = requests.get(f"{ODDS_BASE}/{path.lstrip('/')}",
                        params={"apiKey": key, **params}, timeout=30)
    meta = {
        "http_status": resp.status_code,
        "x_requests_last": resp.headers.get("x-requests-last"),
        "x_requests_remaining": resp.headers.get("x-requests-remaining"),
        "x_requests_used": resp.headers.get("x-requests-used"),
    }
    try:
        ctx.credits_remaining = int(meta["x_requests_remaining"])
        ctx.credits_used = int(meta["x_requests_used"])
    except (TypeError, ValueError):
        pass
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and "data" in payload:
        meta["snapshot_timestamp"] = payload.get("timestamp")
        meta["previous_timestamp"] = payload.get("previous_timestamp")
        data = payload["data"]
    else:
        data = payload
    if not isinstance(data, list):
        data = [data]
    if ctx.odds_sleep_seconds:
        time.sleep(ctx.odds_sleep_seconds)
    return data, meta


def _wrap_odds(records: list[dict], meta: dict, market_tier: str) -> list[dict]:
    """Stamp every odds record with OUR capture time and the credit receipt.

    The receipt rides WITH the data on purpose: a budget question six months from now
    ("what did this cost and when did we look?") is then answerable from the lake rather than
    from a log nobody retained.
    """
    stamp = now_iso()
    out = []
    for r in records:
        out.append({
            "capture_timestamp": stamp,
            "market_tier": market_tier,
            # The event id is lifted OUT of the payload into its own column: it is half the
            # merge key, and a key that has to parse a JSON blob to exist is a key that goes
            # missing the moment the blob shape changes.
            "event_id": str(r.get("id")) if isinstance(r, dict) and r.get("id") else None,
            "snapshot_timestamp": meta.get("snapshot_timestamp"),
            "x_requests_last": str(meta.get("x_requests_last") or ""),
            "x_requests_remaining": str(meta.get("x_requests_remaining") or ""),
            "payload": json.dumps(r, default=str),
        })
    return out


def odds_futures(ctx: Ctx, season: int) -> list[dict]:
    """LIVE title futures (`basketball_ncaab_championship_winner`, outrights).

    Measured at 1 credit a call — a whole season of DAILY futures capture costs less than one
    historical Saturday. There is NO conference-winner sport key at this vendor (measured
    against the live `/sports` list), so "futures" here means the national title board only.
    """
    recs, meta = _odds_get(ctx, f"sports/{budget_sport_futures()}/odds",
                           {"regions": ctx.odds_regions, "markets": "outrights",
                            "oddsFormat": "american"})
    return _wrap_odds(recs, meta, "title_futures")


def odds_game_lines(ctx: Ctx, season: int) -> list[dict]:
    """LIVE game lines (h2h/spreads/totals) for the WHOLE upcoming board.

    ⭐ ONE call returns the entire board regardless of its size (measured up to 105 events),
    so cadence — not slate size — is the only lever on cost. That is exactly why the per-event
    path is guarded: it buys the same rows at 105x the price.
    """
    recs, meta = _odds_get(ctx, f"sports/{budget_sport_game_lines()}/odds",
                           {"regions": ctx.odds_regions,
                            "markets": ",".join(budget.GAME_LINE_MARKETS),
                            "oddsFormat": "american"})
    return _wrap_odds(recs, meta, "game_lines")


def odds_historical_snapshot(ctx: Ctx, season: int, *, at: str) -> list[dict]:
    """ONE paid `/historical` board snapshot. on_demand — never part of a routine run."""
    recs, meta = _odds_get(ctx, f"historical/sports/{budget_sport_game_lines()}/odds",
                           {"date": at, "regions": ctx.odds_regions,
                            "markets": ",".join(budget.GAME_LINE_MARKETS),
                            "oddsFormat": "american"})
    return _wrap_odds(recs, meta, "game_lines_historical")


def budget_sport_game_lines() -> str:
    from .credit_probe import SPORT_GAME_LINES

    return SPORT_GAME_LINES


def budget_sport_futures() -> str:
    from .credit_probe import SPORT_TITLE_FUTURES

    return SPORT_TITLE_FUTURES


# ── the registry ────────────────────────────────────────────────────────────────────────
SOURCES: dict[str, SourceSpec] = {
    "schedules": SourceSpec(
        name="schedules", fetch=hoopr_schedule, tier="hoopr", grain="game", typed=True,
        cadence="daily", freshness_hours=36,
        notes="hoopR mbb_schedule_<season>.parquet — 86 cols incl. neutral_site, venue, "
              "conference ids, scores. The spine."),
    "team_box": SourceSpec(
        name="team_box", fetch=hoopr_team_box, tier="hoopr", grain="team_game", typed=True,
        cadence="daily", freshness_hours=36,
        notes="hoopR team_box_<season>.parquet — 59 cols; carries all four possession "
              "operands (FGA/ORB/TO/FTA), so tempo is computable without a paid source."),
    "team_crosswalk": SourceSpec(
        name="team_crosswalk", fetch=hoopr_team_crosswalk, tier="hoopr", grain="team",
        typed=True, cadence="seasonal", freshness_hours=24 * 14, expect_rows=True,
        notes="hoopR mbb_team_crosswalk_<season>.parquet — 362 D-I teams with conference "
              "NAMES + KenPom/Torvik/Fox/Yahoo join keys. CURRENT SEASON ONLY."),
    "odds_futures": SourceSpec(
        name="odds_futures", fetch=odds_futures, tier="odds", grain="board",
        cadence="daily", freshness_hours=36, expect_rows=True,
        notes="1 credit/call (measured). Live NOW — the title board is the only NCAAB "
              "futures key the vendor offers."),
    "odds_game_lines": SourceSpec(
        name="odds_game_lines", fetch=odds_game_lines, tier="odds", grain="board",
        cadence="intraday", freshness_hours=6, expect_rows=False,
        notes="3 credits/call (derived from the measured 10x historical multiplier). Whole "
              "board per call. expect_rows=False because an EMPTY board out of season is the "
              "correct off-season state AND is free — the in-season check is the job of the "
              "freshness contract, not of this flag."),
    "odds_historical": SourceSpec(
        name="odds_historical", fetch=odds_historical_snapshot, tier="odds", grain="board",
        cadence="seasonal", on_demand=True, expect_rows=False, freshness_hours=None,
        notes="PAID /historical, 30 credits per 3-market snapshot (measured). on_demand so a "
              "routine run can never burn the balance. Archive floor 2020-11-16T09:15:00Z; "
              "5-minute granularity from 2022-23, 10-minute before."),
}

#: Sources a plain (unnamed) run executes. The paid feeds must be asked for by name.
DEFAULT_SOURCES = [n for n, s in SOURCES.items() if not s.on_demand]


def classify_absence(spec: SourceSpec, season: int, *, when: date | None = None) -> str | None:
    """An upstream file 404'd. Is that expected, or an escalation? Returns None if expected.

    The discriminator is whether THIS season has started. Before the first tip, a box-score
    file that does not exist is the normal state of the world; once the season is running, the
    same 404 means a feed we depend on has gone missing.
    """
    when = when or datetime.now(timezone.utc).date()
    if season > season_for(when):
        return None                       # a future season — nothing is published yet
    if season == season_for(when) and not in_season(when):
        return None                       # this season, but it has not tipped off
    return (f"🚨 {spec.name}[{season}]: the upstream file is ABSENT (404) during the active "
            f"season. Before the first tip this is the normal pre-season state; in-season it "
            f"means the feed has gone missing. Investigate before re-running.")


def check_landing(spec: SourceSpec, n_rows: int, *, when: date | None = None) -> str | None:
    """Classify a landing. Returns an ESCALATION message, or None if the landing is fine.

    Three states, because two are not enough: a legitimate off-season empty, an in-season
    empty (a DEFECT — the repo's silent-empty signature), and a healthy landing. Collapsing
    the first two would either page every summer day or hide a real outage in February.
    """
    if n_rows > 0:
        return None
    if not spec.expect_rows:
        return None
    if in_season(when):
        return (f"🚨 {spec.name}: ZERO ROWS landed on an IN-SEASON day ({when or 'today'}). "
                f"This source is expected to carry rows whenever the D-I season is active, so "
                f"an empty landing is a DEFECT, not a quiet day. Do not let this partition "
                f"overwrite a good one — investigate the feed before re-running.")
    return None
