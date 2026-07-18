"""sources.py  (NFL-N0.2 — the SPORT-SPECIFIC source registry)
==============================================================
The one file that IS NFL-specific (sport_data_platform.md §2: "only `sources.py`, the dbt
models, and the schedule payload are sport-specific"). It maps every locked Phase-0 lake table
(`nfl_data_inventory.md` §7) → a fetch function + grain + partition + cadence, so `handler.py`
/ `backfill.py` are pure registry drivers.

TWO fetch shapes (unlike NCAAF, which is CFBD-JSON throughout):
  • nflverse (the whole player/team/PBP/advanced/roster/feeder stack) is read as **typed
    release Parquet directly via DuckDB `read_parquet`** and returned as a pandas DataFrame
    (`typed=True`) → landed by `s3io.write_dataframe` (typed Delta, columns preserved). NO
    `nfl_data_py` — it is abandoned (pins pandas==1.5.3, won't build on py3.12; §1 landmine).
  • Odds API feeds return a `list[dict]` (`typed=False`) → landed by `s3io.write_records`
    (raw_json Delta), because the event carries a nested bookmakers[]→markets[]→outcomes[]
    array whose shape the dbt staging flattens (mirrors the NCAAF odds path).

N0.1 GOTCHAS encoded here so they can't be rediscovered (`nfl_data_inventory.md` §1):
  • nflverse column names DIFFER BETWEEN tables — every asset was DESCRIBEd live on 2026-07-17
    (the URLs + season columns below are OBSERVED truth, not assumed). `players` (season col
    ABSENT → not season-scoped) vs `rosters`/`weekly_rosters` (season col present).
  • `stats_player_week` (145 cols, through 2025), NOT the legacy `player_stats` (53 cols,
    caps 2024).
  • advanced-feed floors differ: NGS + pbp_participation = 2016, PFR = 2018, FTN = 2022. A
    per-year read below an asset's floor 404s → treated as a clean empty slice, not an error
    (`_nflverse_seasonal` catches the 404 → returns empty; the empty-slice guard in
    `write_dataframe` then skips the write).
  • `pbp_participation` has NO `season` column (keyed `nflverse_game_id`) → the URL year is
    stamped as the partition (`write_dataframe` stamps season when absent).
  • two nflverse URL shapes: per-season files `<tag>/<prefix>_YYYY.parquet`
    (stats/rosters/snaps/pbp/…) vs single files `<tag>/<asset>.parquet` (schedules/ngs/qbr/
    draft/combine/players/officials + the pfr_advstats SEASON rollups) filtered by `season`.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

log = logging.getLogger(__name__)

SPORT = "nfl"

ODDS_SPORT_KEY = "americanfootball_nfl"
ODDS_BASE = "https://api.the-odds-api.com/v4"

# ── NFL player-prop markets (N0.4 net-new) ───────────────────────────────────────────────
# The DEEP NFL prop set N0.1 §3 ground-truthed as returning across up to 7 US books incl.
# Bovada (a non-marquee 2024 game snapshot). Curated to the markets a props / CLV / parlay
# surface actually consumes (pass/rush/rec yds+tds+attempts+receptions + anytime-TD) so the
# credit math is bounded + explicit: an event-odds call costs 10 × len(markets) × #regions.
# Props are the EVENT endpoint only — the bulk /odds feed (`odds_nfl`) carries game lines ONLY.
NFL_PROP_MARKETS: tuple[str, ...] = (
    "player_pass_yds", "player_pass_tds", "player_pass_completions", "player_pass_attempts",
    "player_pass_interceptions", "player_rush_yds", "player_rush_attempts", "player_rush_tds",
    "player_reception_yds", "player_receptions", "player_reception_tds", "player_anytime_td",
)

# Game-line markets for the historical closing-line pull (leakage-safe CLV source).
NFL_GAME_LINE_MARKETS = "h2h,spreads,totals"

# nflverse schedules release — the FREE source of season kickoff datetimes (ET) that drive the
# leakage-safe historical closing-line snapshots (read live via DuckDB, no credits, no lake dep).
NFL_SCHEDULES_URL_TMPL = "{base}/schedules/games.parquet"

# nflverse release-Parquet base (read DIRECTLY via DuckDB — nfl_data_py is abandoned).
NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

# Columns nflverse types INCONSISTENTLY across season-files → VARCHAR-pin them so the Delta
# column type is stable across every season partition (the cross-season type-drift cure; see
# `_projection`). Both live in rosters + weekly_rosters: VARCHAR ≤2015 (dirty values like '79D'),
# INTEGER 2016+ → an un-pinned merge write fails `Cannot cast string '79D' to Int32`.
_ROSTER_STR_COLS = ("jersey_number", "draft_number")


@dataclass
class Ctx:
    """Everything the fetchers need — the Odds key + a lazy DuckDB conn for the nflverse
    release reads. Built once per run (handler/backfill).

    N0.4 adds the odds-ingest config (regions / prop markets / snapshot buffer / rate-limit
    sleep / event cap) + running credit accounting (the x-requests-used/remaining headers the
    Odds API returns on every call), so the paid `/historical` backfill can budget + report."""

    odds_api_key: str | None = None
    _duck: Any = None
    # ── odds ingest config (N0.4) ──────────────────────────────────────────────────────────
    odds_regions: str = "us"                                    # US books incl. Bovada (target)
    odds_prop_markets: tuple[str, ...] = NFL_PROP_MARKETS       # DEEP prop set (N0.1 §3)
    odds_snapshot_buffer_min: int = 5                           # snapshot = kickoff − buffer (leakage-safe close)
    odds_sleep_seconds: float = 0.5                             # inter-call politeness / 429 cushion
    odds_max_events: int | None = None                         # cap events/snapshot for a small verify pull
    # running credit accounting (latest header values seen this run)
    credits_used: int | None = None
    credits_remaining: int | None = None

    def duck(self):
        """A lazy DuckDB connection with httpfs (nflverse reads over HTTPS)."""
        if self._duck is None:
            import duckdb

            con = duckdb.connect()
            con.execute("INSTALL httpfs; LOAD httpfs")
            self._duck = con
        return self._duck


# ── fetcher signature: (ctx, year, *, weeks=None) -> DataFrame | list[dict] ──────────────
FetchFn = Callable[..., Any]


@dataclass
class SourceSpec:
    """One lake table's ingest contract (`nfl_data_inventory.md` §7)."""

    name: str                       # the lake table / S3 source name
    fetch: FetchFn                  # (ctx, year, *, weeks=None) -> DataFrame | list[dict]
    tier: str                       # nflverse | odds
    grain: str                      # game | team | player | play | season
    partition: str = "season"       # "season" or "season/week"
    cadence: str = "weekly"         # weekly | seasonal | intraday
    typed: bool = True              # True = DataFrame → write_dataframe; False = list[dict] → write_records
    season_scoped: bool = True      # False = not season-grained (nflverse_players); season=0
    str_cols: tuple = ()            # columns to force to VARCHAR at read (the cross-season type-drift cure)
    on_demand: bool = False         # excluded from the default all-sources run (paid /historical, per-event
                                    #   props) — must be named explicitly (odds_backfill.py / a Dagster op)
                                    #   so a plain nflverse backfill never burns Odds-API credits (N0.4)
    notes: str = ""


# ── nflverse fetchers (typed release Parquet via DuckDB) ─────────────────────────────────
def _is_http_404(exc: Exception) -> bool:
    s = str(exc)
    return "404" in s or "HTTP GET error" in s


def _projection(con, url: str, str_cols: tuple) -> str:
    """Build the SELECT projection, casting any `str_cols` present in the file to VARCHAR — the
    CROSS-SEASON TYPE-DRIFT cure (N0.2 box backfill). nflverse types a column per-season-file:
    `jersey_number` / `draft_number` are VARCHAR ≤2015 (dirty values like '79D') but INTEGER
    2016+. Landed as separate season partitions with `schema_mode='merge'`, the first-written
    season fixes the Delta column type and a later season with the other type fails the merge
    cast (`Cannot cast string '79D' to Int32`). Forcing these id-like columns to VARCHAR for
    EVERY season makes the Delta column stably string (semantically right — jersey '00'/'79D').
    `::VARCHAR` keeps NULLs NULL and renders ints without a '.0' (unlike a pandas float cast)."""
    if not str_cols:
        return "*"
    cols = con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [url]).df().columns.tolist()
    present = [c for c in str_cols if c in cols]
    if not present:
        return "*"
    excl = ", ".join(present)
    casts = ", ".join(f"{c}::VARCHAR AS {c}" for c in present)
    return f"* EXCLUDE ({excl}), {casts}"


def _nflverse_seasonal(tag: str, file_prefix: str, *, has_season_col: bool = True,
                       str_cols: tuple = ()) -> FetchFn:
    """A per-season nflverse asset: `<tag>/<file_prefix>_YYYY.parquet` — read the ONE file for
    `year`. Below an asset's coverage floor the file 404s → returned as an empty DataFrame (a
    clean skip, not an error) so a 2016–2025 backfill doesn't ALERT on FTN 2016–2021 etc.

    ALWAYS stamps a `season` column from the URL year when the asset lacks one (`pbp_participation`
    is keyed `nflverse_game_id` with no season col — `has_season_col=False` documents the expected
    shape) so the returned DataFrame is self-describing for the season-partitioned Delta write.
    `str_cols` are cast to VARCHAR (the cross-season type-drift cure — see `_projection`)."""
    def fetch(ctx: Ctx, year: int, *, weeks=None):
        import pandas as pd

        url = f"{NFLVERSE_RELEASE}/{tag}/{file_prefix}_{int(year)}.parquet"
        con = ctx.duck()
        try:
            proj = _projection(con, url, str_cols)
            df = con.execute(f"SELECT {proj} FROM read_parquet(?)", [url]).df()
        except Exception as exc:  # noqa: BLE001
            if _is_http_404(exc):
                log.info("  [%s] season=%s not published (404) — empty slice", file_prefix, year)
                return pd.DataFrame()
            raise
        if not df.empty and "season" not in df.columns:
            df = df.assign(season=int(year))  # participation (no season col) → stamp the URL year
        return df

    fetch.__name__ = f"_nflverse_seasonal_{file_prefix}"
    return fetch


def _nflverse_single(tag: str, asset: str, season_col: str | None, *,
                     str_cols: tuple = ()) -> FetchFn:
    """A single-file nflverse asset holding ALL seasons: `<tag>/<asset>.parquet`. If `season_col`,
    filter `WHERE <season_col> = year` (one partition/season); else read the whole file (not
    season-scoped — `players`). `str_cols` cast to VARCHAR (the type-drift cure — see `_projection`)."""
    def fetch(ctx: Ctx, year: int, *, weeks=None):
        url = f"{NFLVERSE_RELEASE}/{tag}/{asset}.parquet"
        con = ctx.duck()
        proj = _projection(con, url, str_cols)
        if season_col:
            return con.execute(
                f"SELECT {proj} FROM read_parquet(?) WHERE {season_col} = ?", [url, int(year)]
            ).df()
        return con.execute(f"SELECT {proj} FROM read_parquet(?)", [url]).df()

    fetch.__name__ = f"_nflverse_single_{asset}"
    return fetch


# ── Odds API fetchers (raw_json, mirror NCAAF) ───────────────────────────────────────────
def _int_header(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC with a trailing Z (the Odds API `date` / commenceTime shape)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _odds_request(ctx: Ctx, path: str, params: dict) -> tuple[list[dict], str | None]:
    """One Odds-API GET → (records, snapshot_ts). Captures the credit headers into `ctx`
    (x-requests-used / -remaining) and unwraps the `/historical/` envelope
    ({timestamp, previous_timestamp, next_timestamp, data}) so callers always get a flat
    `list[dict]` + the actual snapshot timestamp the API served (None for live endpoints).

    A per-call `ctx.odds_sleep_seconds` sleep cushions the rate limit on the long historical
    loops. The MAIN key is required for `/historical/` — the starter tier does NOT support it."""
    import requests

    key = ctx.odds_api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError(
            "ODDS_API_KEY not set (operator provisions the MAIN key; the starter tier does "
            "NOT support the /historical/ path)."
        )
    resp = requests.get(f"{ODDS_BASE}/{path.lstrip('/')}", params={"apiKey": key, **params}, timeout=30)
    used = _int_header(resp.headers.get("x-requests-used"))
    remaining = _int_header(resp.headers.get("x-requests-remaining"))
    if used is not None:
        ctx.credits_used = used
    if remaining is not None:
        ctx.credits_remaining = remaining
    resp.raise_for_status()
    if "application/json" not in resp.headers.get("Content-Type", "").lower():
        raise RuntimeError(f"Odds API {path} non-JSON body: {resp.text[:120]!r}")
    payload = resp.json()
    snapshot_ts: str | None = None
    if isinstance(payload, dict) and "data" in payload and (
        "timestamp" in payload or "previous_timestamp" in payload
    ):
        snapshot_ts = payload.get("timestamp")           # /historical/ envelope → the served snapshot
        data = payload["data"]
    else:
        data = payload                                   # live endpoint → bare list / object
    if not isinstance(data, list):
        data = [data]
    if ctx.odds_sleep_seconds:
        time.sleep(ctx.odds_sleep_seconds)
    return data, snapshot_ts


def _odds_get(ctx: Ctx, path: str, params: dict) -> list[dict]:
    """Back-compat thin wrapper (used by the live game-line/score feeds) — drops the snapshot."""
    data, _ = _odds_request(ctx, path, params)
    return data


def _odds_nfl(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Current NFL game lines (h2h/spreads/totals) across US books (Bovada = target). Bulk
    `/odds` endpoint (10×markets credits/pull); props + alt markets are the EVENT endpoint."""
    return _odds_get(
        ctx,
        f"sports/{ODDS_SPORT_KEY}/odds",
        {"regions": ctx.odds_regions, "markets": NFL_GAME_LINE_MARKETS, "oddsFormat": "american"},
    )


def _odds_scores(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Final scores for settlement — the NFL scoreboard (daysFrom ≤ 3). The Odds API has NO
    historical scores endpoint (confirmed 2026-06-23) → historical outcomes come from the FREE
    nflverse `schedules` feed (home/away score), not here (`backfill_multisport_odds_to_s3` note)."""
    return _odds_get(ctx, f"sports/{ODDS_SPORT_KEY}/scores", {"daysFrom": 3})


# ── EVENT endpoint (player props) — current + historical (N0.4 net-new) ──────────────────
def _odds_events(ctx: Ctx, *, historical_date: str | None = None,
                 commence_from: str | None = None, commence_to: str | None = None) -> list[dict]:
    """Event list [{id, commence_time, home_team, away_team, …}]. Live (`/events`) or a
    historical snapshot (`/historical/.../events?date=…`) scoped to a kickoff window."""
    if historical_date:
        params: dict = {"date": historical_date}
        if commence_from:
            params["commenceTimeFrom"] = commence_from
        if commence_to:
            params["commenceTimeTo"] = commence_to
        data, _ = _odds_request(ctx, f"historical/sports/{ODDS_SPORT_KEY}/events", params)
        return data
    data, _ = _odds_request(ctx, f"sports/{ODDS_SPORT_KEY}/events", {})
    return data


def _event_props(ctx: Ctx, event_id: str, *, historical_date: str | None = None) -> list[dict]:
    """One event's player-prop odds (the per-event `/events/{id}/odds` endpoint — props are NOT
    on the bulk `/odds` feed). Returns the event object (bookmakers[]→markets[]→outcomes[]),
    stamped with the served snapshot ts on the historical path so a closing-line pick is
    derivable. Cost = 10 × len(prop_markets) × #regions credits per event."""
    markets = ",".join(ctx.odds_prop_markets)
    params: dict = {"regions": ctx.odds_regions, "markets": markets, "oddsFormat": "american"}
    if historical_date:
        params["date"] = historical_date
        path = f"historical/sports/{ODDS_SPORT_KEY}/events/{event_id}/odds"
    else:
        path = f"sports/{ODDS_SPORT_KEY}/events/{event_id}/odds"
    data, snap = _odds_request(ctx, path, params)
    out: list[dict] = []
    for ev in data:
        if isinstance(ev, dict) and snap:
            ev = {**ev, "_snapshot_ts": snap}
        out.append(ev)
    return out


def _odds_nfl_props(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """CURRENT NFL player props (event endpoint). One `/events` call → one `/events/{id}/odds`
    per event. `ctx.odds_max_events` caps the fan-out for a cheap verification pull. A single
    event's failure ALERT-skips (never sinks the batch — the peripheral-feed contract)."""
    events = _odds_events(ctx)
    if ctx.odds_max_events is not None:
        events = events[: ctx.odds_max_events]
    out: list[dict] = []
    for ev in events:
        eid = ev.get("id") if isinstance(ev, dict) else None
        if not eid:
            continue
        try:
            out.extend(_event_props(ctx, eid))
        except Exception as exc:  # noqa: BLE001 — per-event resilience
            log.warning("  [odds_nfl_props] event %s skipped: %s", eid, str(exc)[:120])
    return out


# ── HISTORICAL closing lines (leakage-safe CLV source) — paid /historical ────────────────
def _season_kickoffs(ctx: Ctx, year: int, *, weeks=None) -> list[datetime]:
    """The DISTINCT kickoff datetimes (UTC) of a season's games, read live+FREE from the
    nflverse `schedules` release (`gameday` date + `gametime` HH:MM in ET → UTC). These drive
    the closing-line snapshots: for each kickoff K we snapshot the market at K−buffer, so the
    captured state is strictly pre-kickoff (leakage-safe). A tight per-kickoff commence window
    then isolates exactly that window's games (the next NFL window is ≥3h away → no bleed).

    ET→UTC uses `America/New_York` (DST-correct). A game with a NULL/blank `gametime` (a
    not-yet-scheduled future game) is skipped — it has no closing line to capture."""
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
    except Exception:  # noqa: BLE001 — no tzdata → fall back to a fixed −4h offset (EDT, in-season)
        et = timezone(timedelta(hours=-4))
    url = NFL_SCHEDULES_URL_TMPL.format(base=NFLVERSE_RELEASE)
    con = ctx.duck()
    sql = ("SELECT DISTINCT gameday, gametime FROM read_parquet(?) "
           "WHERE season = ? AND gameday IS NOT NULL AND gametime IS NOT NULL AND gametime <> ''")
    params: list = [url, int(year)]
    if weeks:
        placeholders = ",".join(str(int(w)) for w in weeks)
        sql += f" AND week IN ({placeholders})"
    rows = con.execute(sql, params).fetchall()
    kicks: set[datetime] = set()
    for gameday, gametime in rows:
        day = str(gameday)[:10]
        try:
            local = datetime.strptime(f"{day} {gametime}", "%Y-%m-%d %H:%M").replace(tzinfo=et)
            kicks.add(local.astimezone(timezone.utc))
        except (ValueError, TypeError):
            continue
    return sorted(kicks)


def _season_game_count(ctx: Ctx, year: int, *, weeks=None) -> int:
    """The number of scheduled games in a season (≈ #events for the props credit estimate) —
    read FREE from nflverse schedules. Only games with a set kickoff (a real, playable slate)."""
    url = NFL_SCHEDULES_URL_TMPL.format(base=NFLVERSE_RELEASE)
    sql = ("SELECT count(*) FROM read_parquet(?) "
           "WHERE season = ? AND gameday IS NOT NULL AND gametime IS NOT NULL AND gametime <> ''")
    params: list = [url, int(year)]
    if weeks:
        sql += f" AND week IN ({','.join(str(int(w)) for w in weeks)})"
    return int(ctx.duck().execute(sql, params).fetchone()[0])


def _odds_nfl_historical(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """HISTORICAL CLOSING game lines (h2h/spreads/totals) for a season — the leakage-safe CLV
    benchmark (NOT the mis-tagged live `odds_nfl` feed). For each distinct kickoff K we call
    `/historical/.../odds?date=K−buffer` scoped to K's game window; the API returns the last
    snapshot ≤ that time = the closing line. Every event carries the API's own `commence_time`
    and we stamp `_snapshot_ts` / `_requested_snapshot`, so a downstream CLV mart enforces the
    hard leakage guard (keep only snapshot_ts < commence_time) belt-and-suspenders.

    Paid `/historical`: 10 × 3 markets × #regions credits per kickoff snapshot (~90/season)."""
    kicks = _season_kickoffs(ctx, year, weeks=weeks)
    buf = timedelta(minutes=ctx.odds_snapshot_buffer_min)
    out: list[dict] = []
    for k in kicks:
        snap = _iso(k - buf)
        params = {
            "date": snap, "regions": ctx.odds_regions, "markets": NFL_GAME_LINE_MARKETS,
            "oddsFormat": "american",
            # ±30min tolerates a small nflverse-vs-OddsAPI kickoff discrepancy without ever
            # reaching the next NFL window (≥3h away) — isolates exactly this window's games.
            "commenceTimeFrom": _iso(k - timedelta(minutes=30)),
            "commenceTimeTo": _iso(k + timedelta(minutes=30)),
        }
        try:
            data, snap_ts = _odds_request(ctx, f"historical/sports/{ODDS_SPORT_KEY}/odds", params)
        except Exception as exc:  # noqa: BLE001 — per-snapshot resilience
            log.warning("  [odds_nfl_historical] snapshot %s skipped: %s", snap, str(exc)[:120])
            continue
        for ev in data:
            if isinstance(ev, dict):
                out.append({**ev, "_snapshot_ts": snap_ts or snap, "_requested_snapshot": snap})
    return out


def _odds_nfl_props_historical(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """HISTORICAL closing player props for a season — the CLV/props backtest source. For each
    kickoff K: `/historical/.../events?date=K−buffer` (scoped to K's window) → per-event
    `/historical/.../events/{id}/odds?date=K−buffer`. Leakage-safe by the same K−buffer snapshot
    + the recorded `commence_time`.

    ⚠️ COST-HEAVY: 10 × len(prop_markets) × #regions credits PER EVENT × ~285 events/season →
    scope seasons + markets deliberately (odds_backfill.py --dry-run estimates before firing;
    `ctx.odds_max_events` caps the per-snapshot fan-out for a verification pull)."""
    kicks = _season_kickoffs(ctx, year, weeks=weeks)
    buf = timedelta(minutes=ctx.odds_snapshot_buffer_min)
    out: list[dict] = []
    for k in kicks:
        snap = _iso(k - buf)
        try:
            events = _odds_events(
                ctx, historical_date=snap,
                commence_from=_iso(k - timedelta(minutes=30)),
                commence_to=_iso(k + timedelta(minutes=30)),
            )
        except Exception as exc:  # noqa: BLE001 — per-snapshot resilience
            log.warning("  [odds_nfl_props_historical] events @ %s skipped: %s", snap, str(exc)[:120])
            continue
        if ctx.odds_max_events is not None:
            events = events[: ctx.odds_max_events]
        for ev in events:
            eid = ev.get("id") if isinstance(ev, dict) else None
            if not eid:
                continue
            try:
                out.extend(_event_props(ctx, eid, historical_date=snap))
            except Exception as exc:  # noqa: BLE001 — per-event resilience
                log.warning("  [odds_nfl_props_historical] event %s @ %s skipped: %s",
                            eid, snap, str(exc)[:120])
    return out


# ── THE REGISTRY — the locked Phase-0 lake tables (`nfl_data_inventory.md` §7) ───────────
# §7 lists 24 rows; several rows expand to multiple physical S3 tables (NGS ×3, PFR week ×4,
# PFR season ×4, QBR ×2, stats_player reg/post ×2) — each distinct S3 table is one entry here.
# Props / historical odds (§7 tables 22 & 24, event-endpoint / one-time) are N0.4, not here.
SOURCES: dict[str, SourceSpec] = {s.name: s for s in [
    # ── core player + team performance (typed) ──────────────────────────────────────────
    SourceSpec("stats_player_week", _nflverse_seasonal("stats_player", "stats_player_week"),
               "nflverse", "player", "season", "weekly", notes="145 cols; THE weekly fact (not legacy player_stats)"),
    SourceSpec("stats_player_reg", _nflverse_seasonal("stats_player", "stats_player_reg"),
               "nflverse", "player", "season", "weekly", notes="regular-season player rollup"),
    SourceSpec("stats_player_post", _nflverse_seasonal("stats_player", "stats_player_post"),
               "nflverse", "player", "season", "weekly", notes="postseason player rollup"),
    SourceSpec("stats_team_week", _nflverse_seasonal("stats_team", "stats_team_week"),
               "nflverse", "team", "season", "weekly", notes="133-col team-week mirror"),
    # ── rosters / depth / snaps / schedule (dimensions) ─────────────────────────────────
    SourceSpec("rosters", _nflverse_seasonal("rosters", "roster", str_cols=_ROSTER_STR_COLS),
               "nflverse", "player", "season", "weekly", str_cols=_ROSTER_STR_COLS,
               notes="season roster; file is roster_YYYY; jersey/draft_number VARCHAR-pinned (type-drift)"),
    SourceSpec("weekly_rosters", _nflverse_seasonal("weekly_rosters", "roster_weekly", str_cols=_ROSTER_STR_COLS),
               "nflverse", "player", "season", "weekly", str_cols=_ROSTER_STR_COLS,
               notes="point-in-time weekly roster; jersey/draft_number VARCHAR-pinned (type-drift)"),
    SourceSpec("depth_charts", _nflverse_seasonal("depth_charts", "depth_charts"),
               "nflverse", "player", "season", "weekly"),
    SourceSpec("snap_counts", _nflverse_seasonal("snap_counts", "snap_counts"),
               "nflverse", "player", "season", "weekly", notes="all-position usage; 2012+"),
    SourceSpec("schedules", _nflverse_single("schedules", "games", "season"),
               "nflverse", "game", "season", "weekly", notes="game spine + free consensus lines; 1999–2026"),
    # ── Next Gen Stats (single-file, filter season; 2016+) ──────────────────────────────
    SourceSpec("ngs_passing", _nflverse_single("nextgen_stats", "ngs_passing", "season"),
               "nflverse", "player", "season", "weekly", notes="CPOE/aDOT/time-to-throw; 2016+"),
    SourceSpec("ngs_rushing", _nflverse_single("nextgen_stats", "ngs_rushing", "season"),
               "nflverse", "player", "season", "weekly", notes="RYOE/efficiency; 2016+"),
    SourceSpec("ngs_receiving", _nflverse_single("nextgen_stats", "ngs_receiving", "season"),
               "nflverse", "player", "season", "weekly", notes="separation/cushion/YAC-oe; 2016+"),
    # ── PFR advanced (week per-year 2018+; season single-file 2018+) ────────────────────
    SourceSpec("pfr_advstats_week_pass", _nflverse_seasonal("pfr_advstats", "advstats_week_pass"),
               "nflverse", "player", "season", "weekly", notes="pressures/bad-throw; 2018+"),
    SourceSpec("pfr_advstats_week_rush", _nflverse_seasonal("pfr_advstats", "advstats_week_rush"),
               "nflverse", "player", "season", "weekly", notes="yac/ybc/broken-tackles; 2018+"),
    SourceSpec("pfr_advstats_week_rec", _nflverse_seasonal("pfr_advstats", "advstats_week_rec"),
               "nflverse", "player", "season", "weekly", notes="drops/broken-tackles; 2018+"),
    SourceSpec("pfr_advstats_week_def", _nflverse_seasonal("pfr_advstats", "advstats_week_def"),
               "nflverse", "player", "season", "weekly", notes="coverage/missed-tackles; 2018+"),
    SourceSpec("pfr_advstats_season_pass", _nflverse_single("pfr_advstats", "advstats_season_pass", "season"),
               "nflverse", "player", "season", "weekly", notes="season rollup (single file); 2018+"),
    SourceSpec("pfr_advstats_season_rush", _nflverse_single("pfr_advstats", "advstats_season_rush", "season"),
               "nflverse", "player", "season", "weekly", notes="season rollup (single file); 2018+"),
    SourceSpec("pfr_advstats_season_rec", _nflverse_single("pfr_advstats", "advstats_season_rec", "season"),
               "nflverse", "player", "season", "weekly", notes="season rollup (single file); 2018+"),
    SourceSpec("pfr_advstats_season_def", _nflverse_single("pfr_advstats", "advstats_season_def", "season"),
               "nflverse", "player", "season", "weekly", notes="season rollup (single file); 2018+"),
    # ── PBP + participation + charting (raw material) ───────────────────────────────────
    SourceSpec("pbp", _nflverse_seasonal("pbp", "play_by_play"),
               "nflverse", "play", "season", "weekly", notes="372-col nflfastR; the wide/sparse table"),
    SourceSpec("pbp_participation", _nflverse_seasonal("pbp_participation", "pbp_participation", has_season_col=False),
               "nflverse", "play", "season", "weekly", notes="personnel/coverage/route; 2016+; NO season col → stamped"),
    SourceSpec("ftn_charting", _nflverse_seasonal("ftn_charting", "ftn_charting"),
               "nflverse", "play", "season", "weekly", notes="play-action/screen/RPO/contested; 2022+"),
    # ── QBR (single-file, filter season) ────────────────────────────────────────────────
    SourceSpec("qbr_week", _nflverse_single("espn_data", "qbr_week_level", "season"),
               "nflverse", "player", "season", "weekly", notes="ESPN QBR week; 2006+"),
    SourceSpec("qbr_season", _nflverse_single("espn_data", "qbr_season_level", "season"),
               "nflverse", "player", "season", "weekly", notes="ESPN QBR season; 2006+"),
    # ── injuries (per-year; 2009+) — weekly in-season cadence (N0.4 wires the schedule) ──
    SourceSpec("injuries", _nflverse_seasonal("injuries", "injuries"),
               "nflverse", "player", "season", "weekly", notes="report/practice status; net-new NFL feed"),
    # ── feeder + reference (single-file) ────────────────────────────────────────────────
    SourceSpec("nflverse_draft_picks", _nflverse_single("draft_picks", "draft_picks", "season"),
               "nflverse", "player", "season", "seasonal", notes="feeder TARGET (car_av/…); 1980+"),
    SourceSpec("nflverse_combine", _nflverse_single("combine", "combine", "season"),
               "nflverse", "player", "season", "seasonal", notes="measurables; cfb_id slug; 2000+"),
    SourceSpec("nflverse_players", _nflverse_single("players", "players", None),
               "nflverse", "player", "season", "seasonal", season_scoped=False,
               notes="the NFL ID universe; NO season col → not season-grained (season=0)"),
    SourceSpec("officials", _nflverse_single("officials", "officials", "season"),
               "nflverse", "game", "season", "seasonal", notes="crew per game; referee tendencies; 2015+"),
    # ── Odds API — LIVE feeds (raw_json; cheap bulk /odds) ──────────────────────────────
    SourceSpec("odds_nfl", _odds_nfl, "odds", "game", "season/week", "intraday", typed=False,
               notes="CURRENT h2h/spreads/totals, US books incl. Bovada (bulk /odds; NOT closing lines)"),
    SourceSpec("odds_nfl_scores", _odds_scores, "odds", "game", "season/week", "intraday", typed=False,
               notes="live scores (daysFrom≤3); historical outcomes come FREE from nflverse schedules"),
    # ── Odds API — EVENT-endpoint props + paid /historical (N0.4 net-new; on_demand) ─────
    # on_demand=True → NEVER pulled by a plain nflverse backfill (per-event / paid-credit burn);
    # named explicitly by odds_backfill.py or a Dagster op. `odds_nfl_props` is the CURRENT
    # per-event props feed; the two `*_historical` are the leakage-safe CLV backtest sources.
    SourceSpec("odds_nfl_props", _odds_nfl_props, "odds", "player", "season/week", "intraday",
               typed=False, on_demand=True,
               notes="CURRENT player props (event endpoint): pass/rush/rec yds+tds+att+receptions+anytime-TD"),
    SourceSpec("odds_nfl_historical", _odds_nfl_historical, "odds", "game", "season/week", "seasonal",
               typed=False, on_demand=True,
               notes="paid /historical CLOSING game lines — leakage-safe close for CLV (h2h/spread/total, 2020+)"),
    SourceSpec("odds_nfl_props_historical", _odds_nfl_props_historical, "odds", "player",
               "season/week", "seasonal", typed=False, on_demand=True,
               notes="paid /historical CLOSING player props for CLV/props backtest — COST-HEAVY, scope deliberately"),
]}


def build_ctx(
    *,
    odds_key: str | None = None,
    regions: str = "us",
    prop_markets: tuple[str, ...] | None = None,
    snapshot_buffer_min: int = 5,
    sleep_seconds: float = 0.5,
    max_events: int | None = None,
) -> Ctx:
    """Construct the run context. nflverse-only runs don't need the Odds key; the odds knobs
    (regions / prop markets / snapshot buffer / rate-limit sleep / event cap) let odds_backfill
    tune the paid `/historical` pull (a verify pull caps `max_events`; a full pull uses all)."""
    return Ctx(
        odds_api_key=odds_key or os.environ.get("ODDS_API_KEY"),
        odds_regions=regions,
        odds_prop_markets=tuple(prop_markets) if prop_markets else NFL_PROP_MARKETS,
        odds_snapshot_buffer_min=snapshot_buffer_min,
        odds_sleep_seconds=sleep_seconds,
        odds_max_events=max_events,
    )


# Convenience groupings the handler/backfill/schedule payloads use.
NFLVERSE_SOURCES = [n for n, s in SOURCES.items() if s.tier == "nflverse"]
ODDS_SOURCES = [n for n, s in SOURCES.items() if s.tier == "odds"]
# Odds split by orchestration: recurring LIVE feeds vs the paid /historical CLV backfill.
ODDS_LIVE = [n for n, s in SOURCES.items() if s.tier == "odds" and not s.on_demand]
ODDS_HISTORICAL = [n for n, s in SOURCES.items() if s.tier == "odds" and s.cadence == "seasonal"]
ODDS_ON_DEMAND = [n for n, s in SOURCES.items() if s.tier == "odds" and s.on_demand]
# The advanced stack (2016–2025 floor); the box/team/roster set can extend to 1999 (§7).
NFLVERSE_WEEKLY = [n for n, s in SOURCES.items() if s.tier == "nflverse" and s.cadence == "weekly"]
NFLVERSE_SEASONAL = [n for n, s in SOURCES.items() if s.tier == "nflverse" and s.cadence == "seasonal"]
# Everything a DEFAULT (unnamed) run pulls — excludes the on_demand paid odds sources (N0.4).
DEFAULT_SOURCES = [n for n, s in SOURCES.items() if not s.on_demand]
