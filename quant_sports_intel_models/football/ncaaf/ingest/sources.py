"""sources.py  (NCAAF-P0.2 — the SPORT-SPECIFIC source registry)
================================================================
The one file that IS NCAAF-specific (sport_data_platform.md §2: "only `sources.py`, the
dbt models, and the schedule payload are sport-specific"). It maps every locked Phase-0
lake table (ncaaf_data_inventory.md §8, 24 tables + `coaches` added by P0.5 = 25) → a fetch
function + grain + partition +
cadence, so `handler.py` / `backfill.py` are pure registry drivers.

Every fetcher returns a flat `list[dict]` of raw records for ONE season (the handler writes
the whole season as one Delta partition — the platform §3 idempotent-per-season contract).
Week-grained and per-game endpoints loop INTERNALLY and tag each record with its week/game;
callers never manage the loop. A `weeks=` kwarg scopes the pull (the smoke/dev path) without
changing the registry shape.

P0.1 call-shape rules are encoded in the fetchers so they can't be rediscovered:
  • `/plays` requires week → `_plays` loops weeks.
  • `/plays/stats` is 2,000-capped → `_play_stats` pulls per gameId (the dominant cost).
  • `/game/box/advanced` takes id= → `_box_advanced` pulls per gameId.
  • year-only endpoints (roster/usage/ppa-season/returning/recruiting/talent/portal/…) are
    ONE call/season — never a 136-team loop.
  • nflverse is read as release Parquet directly (nfl_data_py is abandoned on py3.12).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .cfbd_client import CFBDClient

log = logging.getLogger(__name__)

SPORT = "ncaaf"

# The FBS-only modelling universe (ncaaf_data_inventory.md §9 open-gap 8: CFBD covers FCS
# unevenly). CFBD week-grained endpoints default to FBS; we keep the season pulls whole.
ODDS_SPORT_KEY = "americanfootball_ncaaf"
ODDS_BASE = "https://api.the-odds-api.com/v4"

# Game-line markets for the live feed AND the leakage-safe historical CLOSING-line pull (P0.6).
NCAAF_GAME_LINE_MARKETS = "h2h,spreads,totals"

# The Odds-API historical FLOOR for NCAAF FEATURED game lines (h2h/spreads/totals) — 2020
# (P0.1 §3, N0.4-confirmed live 2026-07-18: the FEATURED markets reach 2020 across the football
# keys). A season < this floor has NO historical odds coverage → a below-floor pull would 422 on
# every snapshot, so `odds_ncaaf_historical` skips it whole (a clean empty slice, 0 credits).
# ⚠️ NCAAF player PROPS have a HARDER 2023 vendor floor AND are THIN → NOT pulled here (P0.6 is
# GAME LINES ONLY: h2h/spread/total); the props floor is moot for this source.
NCAAF_HISTORICAL_FLOOR = 2020


def last_completed_season(today: "date | None" = None) -> int:
    """The most recent NCAAF season whose games are ALL played — the clock-derived upper bound
    for a historical backfill (never hardcode it; a pinned year silently rots — P0.6 shipped with
    `2020-2024` and was already stale by one season the day it merged).

    A season YYYY runs Aug YYYY → mid-Jan YYYY+1. So from FEBRUARY onward the season that began
    LAST calendar year is complete. During JANUARY the prior season's bowls/CFP are still being
    played, so we conservatively fall back one further — defaulting into an IN-PROGRESS season
    would land a PARTIAL partition, which `--skip-existing` then protects forever (the P0.6
    2024-stub trap). An operator wanting the just-finishing season passes `--seasons` explicitly.

    Self-contained stdlib only: this package ships as a LEAN image (its Dockerfile COPYs just
    `ncaaf/ingest/` + its own requirements) — importing `betting_ml.utils.game_day` here would
    ImportError at runtime. Injectable `today` keeps it unit-testable.
    """
    d = today or datetime.now(timezone.utc).date()
    return d.year - 1 if d.month >= 2 else d.year - 2


def default_backfill_seasons(today: "date | None" = None) -> str:
    """`<floor>-<last completed season>` — the clock-derived default season range (a string in
    the `_parse_seasons` A-B shape) shared by odds_backfill.py and verify_odds_historical.py."""
    return f"{NCAAF_HISTORICAL_FLOOR}-{last_completed_season(today)}"


def current_season(today: "date | None" = None) -> int:
    """The UPCOMING-or-in-progress NCAAF season — the P0.7 season-roll-forward TARGET (the
    season the pre-season futures board + live game-model board are built FOR), the complement
    of `last_completed_season`.

    A season YYYY runs Aug YYYY → mid-Jan YYYY+1. So from FEBRUARY onward the season that will
    START this calendar year is the current target; during JANUARY the season that began LAST
    year is still finishing its bowls/CFP, so IT is still current (the next roll-forward, to the
    Aug-of-this-year season, happens in the summer). That is exactly `last_completed_season() + 1`
    at every point on the calendar — a single clock-derived definition, never a pinned year (the
    P0.6 stale-by-a-season landmine: a pinned target silently rots the day the calendar turns, so
    the whole roll-forward chain must clock-derive its season and be re-runnable next August
    unchanged).

    Injectable `today` keeps it unit-testable; stdlib-only so the lean ingest image can import it.
    """
    return last_completed_season(today) + 1

# nflverse release-Parquet asset URLs (read DIRECTLY via DuckDB — nfl_data_py is abandoned;
# it pins pandas==1.5.3 which won't build on py3.12. P0.1 §1 landmine).
NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
NFLVERSE_ASSETS = {
    "nflverse_draft_picks": f"{NFLVERSE_RELEASE}/draft_picks/draft_picks.parquet",
    "nflverse_combine": f"{NFLVERSE_RELEASE}/combine/combine.parquet",
    "nflverse_players": f"{NFLVERSE_RELEASE}/players/players.parquet",
}


@dataclass
class Ctx:
    """Everything the fetchers need — one CFBD client, the Odds key, a lazy DuckDB conn for
    the nflverse release reads. Built once per run (handler/backfill).

    P0.6 adds the odds-ingest config (regions / snapshot buffer / rate-limit sleep) + running
    credit accounting (the x-requests-used/-remaining headers the Odds API returns on every
    call), so the paid `/historical` closing-line backfill can budget + report its burn."""

    cfbd: CFBDClient | None = None
    odds_api_key: str | None = None
    _duck: Any = None
    # ── odds ingest config (P0.6 — the paid /historical closing-line pull) ───────────────────
    odds_regions: str = "us"                    # US books incl. Bovada (target); 11 books on /historical
    odds_snapshot_buffer_min: int = 5           # snapshot = kickoff − buffer (leakage-safe close)
    odds_sleep_seconds: float = 0.5             # inter-call politeness / 429 cushion on the long loops
    odds_max_events: int | None = None          # cap kickoffs/season for a cheap verification pull
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


# ── fetcher signature: (ctx, year, *, weeks=None) -> list[dict] ─────────────────────────
FetchFn = Callable[..., list]


@dataclass
class SourceSpec:
    """One lake table's ingest contract (ncaaf_data_inventory.md §8)."""

    name: str                       # the lake table / S3 source name
    fetch: FetchFn                  # (ctx, year, *, weeks=None) -> list[dict]
    tier: str                       # cfbd | odds | nflverse
    grain: str                      # game | team | player | play | season
    partition: str = "season"       # "season" or "season/week"
    cadence: str = "weekly"         # weekly | seasonal | intraday
    season_scoped: bool = True      # False = not season-grained (nflverse_players); season=0
    on_demand: bool = False         # excluded from the default (unnamed) run — the paid /historical
                                    #   odds pull; named explicitly (odds_backfill.py / a Dagster op)
                                    #   so a plain CFBD/nflverse backfill never burns Odds credits (P0.6)
    notes: str = ""


# ── CFBD fetchers ───────────────────────────────────────────────────────────────────────
def _default_weeks() -> list[int]:
    # 15 regular-season week-units + postseason; CFBD ignores empty weeks cheaply.
    return list(range(1, 16))


def _tag(records: list[dict], **extra) -> list[dict]:
    for r in records:
        r.update(extra)
    return records


def _games(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """/games — whole season (year-only is accepted; week tag added when we scope)."""
    if weeks is None:
        return ctx.cfbd.get_games(year)
    out: list[dict] = []
    for wk in weeks:
        out.extend(_tag(ctx.cfbd.get_games(year, week=wk), _week=wk))
    return out


def _game_team_stats(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    # /games/teams REQUIRES a filter — "either week, team, or conference are required"
    # (verified live 2026-07-15; year-only 400s). Always loop weeks (never year-only).
    out: list[dict] = []
    for wk in (weeks or _default_weeks()):
        out.extend(_tag(ctx.cfbd.get_game_team_stats(year, week=wk), _week=wk))
    return out


def _game_player_stats(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    # /games/players REQUIRES a filter too (same 400 as /games/teams). Per-week loop.
    out: list[dict] = []
    for wk in (weeks or _default_weeks()):
        out.extend(_tag(ctx.cfbd.get_game_player_stats(year, week=wk), _week=wk))
    return out


def _plays(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """/plays REQUIRES week → always a per-week loop (P0.1 §1)."""
    out: list[dict] = []
    for wk in (weeks or _default_weeks()):
        out.extend(_tag(ctx.cfbd.get_plays(year, wk), _week=wk))
    return out


def _drives(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    out: list[dict] = []
    for wk in (weeks or _default_weeks()):
        out.extend(_tag(ctx.cfbd.get_drives(year, week=wk), _week=wk))
    return out


def _is_fbs_game(g: dict) -> bool:
    """A game involving ≥1 FBS team — the modelling universe (ncaaf_data_inventory.md §9
    gap 8). /games year-only returns ALL divisions (~3,800/season incl DII/NAIA); the
    per-GAME endpoints must NOT iterate those or the call budget blows up (§6 assumes
    ~60 FBS games/week). CFBD marks the division on each side as home/awayClassification."""
    return g.get("homeClassification") == "fbs" or g.get("awayClassification") == "fbs"


def _game_ids(ctx: Ctx, year: int, weeks=None, *, fbs_only: bool = True) -> list[int]:
    """Game ids for the per-GAME endpoints (play_stats / box_advanced). FBS-only by default
    so the ~960-call/season budget (§6) holds — an unfiltered list is ~4× larger and mostly
    non-FBS junk. Bulk week-grained pulls (games/plays/drives) land ALL divisions cheaply and
    are FBS-filtered downstream in dbt (is_fbs_matchup) — only the per-game fan-out is gated here."""
    games = _games(ctx, year, weeks=weeks)
    return [
        int(g["id"]) for g in games
        if g.get("id") is not None and (not fbs_only or _is_fbs_game(g))
    ]


def _iter_games_safe(gids, fetch_one, label: str, *, early_abort: int = 15) -> list[dict]:
    """Run a per-GAME fetch over gids, SKIPPING (not aborting on) a single game's failure.

    A per-game endpoint must not let one bad game sink the whole season — older games can
    500 on /game/box/advanced (no advanced box exists), and a residual 429 after retries
    should cost one game, not the partition. Each skip is logged; a summary count surfaces
    the gap so the operator can spot + re-run a heavily-skipped season.

    CIRCUIT BREAKER: if the FIRST `early_abort` games all fail with ZERO successes, the
    endpoint is unavailable for this season (e.g. box_advanced pre-~2015 → every game 500s)
    → bail instead of grinding through ~900 games × 6 retries of wasted calls/time."""
    out: list[dict] = []
    skipped: list[int] = []
    consecutive = 0
    for i, gid in enumerate(gids):
        try:
            out.extend(fetch_one(gid))
            consecutive = 0
        except Exception as exc:  # noqa: BLE001 — per-game resilience
            skipped.append(gid)
            consecutive += 1
            log.warning("  [%s] gameId=%s skipped: %s", label, gid, str(exc)[:120])
            if consecutive >= early_abort and not out:
                log.warning("  [%s] first %d games all failed (0 successes) — endpoint "
                            "unavailable for this season; ABORTING (skipping remaining %d games "
                            "to avoid wasted calls)", label, consecutive, len(gids) - i - 1)
                break
    if skipped:
        log.warning("  [%s] %d/%d games skipped (data gap — re-run to backfill)",
                    label, len(skipped), len(gids))
    return out


def _play_stats(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """/plays/stats — 2,000-row cap ⇒ per gameId (the ~960-call/season dominant cost).
    Scoped by `weeks` (via the games list) for the smoke; whole season otherwise. FBS-only."""
    gids = _game_ids(ctx, year, weeks=weeks)
    return _iter_games_safe(
        gids, lambda g: _tag(ctx.cfbd.get_play_stats_by_game(g), _game_id=g), "play_stats")


def _box_advanced(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """/game/box/advanced takes id= (not gameId=) ⇒ per gameId (P0.1 §1). FBS-only."""
    gids = _game_ids(ctx, year, weeks=weeks)

    def one(gid: int) -> list[dict]:
        rec = ctx.cfbd.get_box_advanced(gid)
        if isinstance(rec, dict):
            rec["_game_id"] = gid
            return [rec]
        return []

    return _iter_games_safe(gids, one, "box_advanced")


def _per_week(path: str, *, season_type: str | None = None) -> FetchFn:
    """Build a fetcher for a WEEK-GRAINED endpoint that REQUIRES `week` (a per-week loop).
    e.g. /ppa/players/games 400s on year-only ("week is required") — verified live 2026-07-15.
    (Contrast the year-only endpoints below, which take year with no filter.)"""
    def fetch(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
        out: list[dict] = []
        for wk in (weeks or _default_weeks()):
            params = {"year": year, "week": wk}
            if season_type:
                params["seasonType"] = season_type
            rows = ctx.cfbd.get(path, params)
            out.extend(_tag(rows if isinstance(rows, list) else [rows], _week=wk))
        return out
    fetch.__name__ = f"_per_week{path.replace('/', '_')}"
    return fetch


def _year_only(path: str) -> FetchFn:
    """Build a fetcher for a YEAR-ONLY endpoint — ONE call/season, no team loop (P0.1 §1)."""
    def fetch(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
        rows = ctx.cfbd.get_year_only(path, year)
        return rows if isinstance(rows, list) else [rows]
    fetch.__name__ = f"_year_only{path.replace('/', '_')}"
    return fetch


# ── Odds API fetchers ───────────────────────────────────────────────────────────────────
def _int_header(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC with a trailing Z (the Odds API `date` / commenceTime shape)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp (trailing Z, optional fractional seconds — CFBD
    `startDate` and the Odds-API `commence_time` shape) → a tz-aware UTC datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _odds_request(ctx: Ctx, path: str, params: dict) -> tuple[list[dict], str | None]:
    """One Odds-API GET → (records, snapshot_ts). Captures the credit headers into `ctx`
    (x-requests-used / -remaining) and unwraps the `/historical/` envelope
    ({timestamp, previous_timestamp, next_timestamp, data}) so callers always get a flat
    `list[dict]` + the actual snapshot timestamp the API served (None for the live endpoints).

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


def _odds_get(ctx: Ctx, path: str, params: dict) -> list:
    """Back-compat thin wrapper (the live game-line/score feeds) — drops the snapshot ts."""
    data, _ = _odds_request(ctx, path, params)
    return data


def _odds_ncaaf(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """CURRENT NCAAF game lines (h2h/spreads/totals) across US books (Bovada = target). This is
    the LIVE bulk `/odds` feed — NOT closing lines (that's `odds_ncaaf_historical`, P0.6)."""
    return _odds_get(
        ctx,
        f"sports/{ODDS_SPORT_KEY}/odds",
        {"regions": ctx.odds_regions, "markets": NCAAF_GAME_LINE_MARKETS, "oddsFormat": "american"},
    )


def _odds_scores(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Final scores for settlement (daysFrom ≤ 3)."""
    return _odds_get(ctx, f"sports/{ODDS_SPORT_KEY}/scores", {"daysFrom": 3})


# ── HISTORICAL closing lines (leakage-safe CLV source) — paid /historical (P0.6) ─────────
def _season_kickoffs(ctx: Ctx, year: int, *, weeks=None) -> list[datetime]:
    """The DISTINCT kickoff datetimes (UTC) of a season's FBS games, read from CFBD `/games`.

    These drive the closing-line snapshots: for each kickoff K we snapshot the market at
    K−buffer, so the captured state is strictly pre-kickoff (leakage-safe). A tight per-kickoff
    commence window then isolates exactly that window's games.

    CFBD `/games.startDate` is already an ISO-8601 UTC instant (e.g. `2024-08-24T16:00:00.000Z`)
    — parsed directly (NO ET→UTC conversion, unlike the NFL nflverse-schedules path). A game with
    `startTimeTBD=true` (a not-yet-scheduled time → a placeholder startDate) or a NULL/unparseable
    startDate is skipped — it has no real kickoff to snapshot. FBS-only (the modelling universe +
    the `americanfootball_ncaaf` Odds coverage) keeps the distinct-kickoff / credit count bounded;
    the full non-FBS slate would ~4× it for windows the book doesn't even price."""
    games = _games(ctx, year, weeks=weeks)
    kicks: set[datetime] = set()
    for g in games:
        if not _is_fbs_game(g):
            continue
        if g.get("startTimeTBD") in (True, "true"):
            continue
        sd = g.get("startDate")
        if not sd:
            continue
        try:
            kicks.add(_parse_iso(str(sd)).astimezone(timezone.utc))
        except (ValueError, TypeError):
            continue
    return sorted(kicks)


def _odds_ncaaf_historical(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """HISTORICAL CLOSING game lines (h2h/spreads/totals) for a season — the leakage-safe CLV
    benchmark (NOT the mis-tagged live `odds_ncaaf` feed). For each distinct kickoff K we call
    `/historical/.../odds?date=K−buffer` scoped to K's game window; the API returns the last
    snapshot ≤ that time = the closing line. Every event carries the API's own `commence_time`
    and we stamp `_snapshot_ts` / `_requested_snapshot`, so a downstream CLV mart enforces the
    hard leakage guard (keep only snapshot_ts < commence_time) belt-and-suspenders.

    ⛔ BELOW-FLOOR SKIP: FEATURED historical coverage starts season `NCAAF_HISTORICAL_FLOOR`
    (2020). A pre-floor season returns an empty slice (a clean skip, ALERT-loud) — no 422
    grinding, no wasted credits.

    Paid `/historical`: 10 × 3 markets × #regions credits per kickoff snapshot. NCAAF slates are
    DENSER than the NFL (many staggered college start times), so the per-season kickoff count —
    hence credit cost — is materially higher; ALWAYS `--dry-run` first."""
    if int(year) < NCAAF_HISTORICAL_FLOOR:
        log.warning("ALERT [odds_ncaaf_historical] season %s < historical floor %s — no "
                    "historical closing lines exist (empty slice, no credits spent).",
                    year, NCAAF_HISTORICAL_FLOOR)
        return []
    kicks = _season_kickoffs(ctx, year, weeks=weeks)
    if ctx.odds_max_events is not None:
        kicks = kicks[: ctx.odds_max_events]     # cheap verification pull (cap snapshots)
    buf = timedelta(minutes=ctx.odds_snapshot_buffer_min)
    out: list[dict] = []
    for k in kicks:
        snap = _iso(k - buf)
        params = {
            "date": snap, "regions": ctx.odds_regions, "markets": NCAAF_GAME_LINE_MARKETS,
            "oddsFormat": "american",
            # ±30min brackets K's games while tolerating a small CFBD-vs-OddsAPI kickoff
            # discrepancy. Denser college slates can put another distinct kickoff inside this
            # window → the same game may land under two snapshots; that is fine (leakage-safe,
            # deduped downstream by (event, snapshot_ts) — extra rows, NOT extra API calls).
            "commenceTimeFrom": _iso(k - timedelta(minutes=30)),
            "commenceTimeTo": _iso(k + timedelta(minutes=30)),
        }
        try:
            data, snap_ts = _odds_request(ctx, f"historical/sports/{ODDS_SPORT_KEY}/odds", params)
        except Exception as exc:  # noqa: BLE001 — per-snapshot resilience
            log.warning("  [odds_ncaaf_historical] snapshot %s skipped: %s", snap, str(exc)[:120])
            continue
        for ev in data:
            if isinstance(ev, dict):
                out.append({**ev, "_snapshot_ts": snap_ts or snap, "_requested_snapshot": snap})
    return out


# ── nflverse fetchers (release Parquet via DuckDB — the feeder universe) ─────────────────
def _nflverse(asset_key: str, season_col: str | None) -> FetchFn:
    def fetch(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
        url = NFLVERSE_ASSETS[asset_key]
        con = ctx.duck()
        if season_col:
            df = con.execute(
                f"SELECT * FROM read_parquet(?) WHERE {season_col} = ?", [url, int(year)]
            ).df()
        else:
            df = con.execute("SELECT * FROM read_parquet(?)", [url]).df()
        return df.to_dict("records")
    fetch.__name__ = f"_nflverse_{asset_key}"
    return fetch


# ── THE REGISTRY — the 24 locked Phase-0 lake tables (ncaaf_data_inventory.md §8) + the
# `coaches` source added by P0.5 (HC history w/ SP+ splits; §11) = 25 sources ──────────────
SOURCES: dict[str, SourceSpec] = {s.name: s for s in [
    # 1–9 week-grained CFBD (the modelling core)
    SourceSpec("games", _games, "cfbd", "game", "season/week", "weekly"),
    SourceSpec("game_team_stats", _game_team_stats, "cfbd", "team", "season/week", "weekly"),
    SourceSpec("game_player_stats", _game_player_stats, "cfbd", "player", "season/week", "weekly"),
    SourceSpec("plays", _plays, "cfbd", "play", "season/week", "weekly",
               notes="/plays REQUIRES week"),
    SourceSpec("play_stats", _play_stats, "cfbd", "player", "season/week", "weekly",
               notes="2000-row cap → per gameId; ~960 calls/season, THE target-share source"),
    SourceSpec("drives", _drives, "cfbd", "game", "season/week", "weekly"),
    SourceSpec("game_advanced", _year_only("/stats/game/advanced"), "cfbd", "team",
               "season", "weekly", notes="year-accepting; the per-game advanced modelling grain"),
    SourceSpec("box_advanced", _box_advanced, "cfbd", "team", "season/week", "weekly",
               notes="id= param; overlaps game_advanced (optional)"),
    SourceSpec("ppa_players_games", _per_week("/ppa/players/games"), "cfbd", "player",
               "season/week", "weekly", notes="2014+ only; /ppa/players/games REQUIRES week"),
    # 10–13 season-grained CFBD (year-only — ONE call/season)
    SourceSpec("player_usage", _year_only("/player/usage"), "cfbd", "player", "season", "weekly"),
    SourceSpec("roster", _year_only("/roster"), "cfbd", "player", "season", "weekly"),
    SourceSpec("team_advanced_season", _year_only("/stats/season/advanced"), "cfbd", "team",
               "season", "weekly"),
    SourceSpec("ratings_sp", _year_only("/ratings/sp"), "cfbd", "team", "season", "weekly"),
    # 14–17 seasonal reference / recruiting / draft
    SourceSpec("talent", _year_only("/talent"), "cfbd", "team", "season", "seasonal"),
    SourceSpec("recruiting_players", _year_only("/recruiting/players"), "cfbd", "player",
               "season", "seasonal"),
    SourceSpec("transfer_portal", _year_only("/player/portal"), "cfbd", "player", "season", "seasonal"),
    SourceSpec("returning_production", _year_only("/player/returning"), "cfbd", "team",
               "season", "seasonal"),
    SourceSpec("teams", _year_only("/teams/fbs"), "cfbd", "season", "season", "seasonal"),
    SourceSpec("coaches", _year_only("/coaches"), "cfbd", "team", "season", "seasonal",
               notes="HC↔school↔year history WITH per-coach-year SP+ splits (P0.5). Year-only "
                     "(1 call/season) — a year= pull returns each coach with THAT season's row; "
                     "dbt reads all partitions to reconstruct the full coach-school-year grid + "
                     "each HC's prior-season SP+ track record. OC/DC not in CFBD (inventory §11)."),
    SourceSpec("cfbd_draft_picks", _year_only("/draft/picks"), "cfbd", "player", "season",
               "seasonal", notes="the CFBD side of the NFL-feeder draft-slot key (P0.3)"),
    # 18–21 Odds API
    SourceSpec("odds_ncaaf", _odds_ncaaf, "odds", "game", "season/week", "intraday",
               notes="CURRENT h2h/spreads/totals, US books incl. Bovada (live /odds — NOT closing lines)"),
    SourceSpec("odds_ncaaf_scores", _odds_scores, "odds", "game", "season/week", "intraday"),
    # inventory §8 table #21 — paid /historical CLOSING lines (P0.6; on_demand → never in a
    # default backfill). The leakage-safe CLV benchmark that GATES P1.4 vs-market + all Phase 2.
    SourceSpec("odds_ncaaf_historical", _odds_ncaaf_historical, "odds", "game", "season/week",
               "seasonal", on_demand=True,
               notes="paid /historical CLOSING game lines — leakage-safe close for CLV "
                     "(h2h/spread/total, 11 US books incl. Bovada, 2020+)"),
    # 22–24 nflverse (the feeder universe; release Parquet directly)
    SourceSpec("nflverse_draft_picks", _nflverse("nflverse_draft_picks", "season"), "nflverse",
               "player", "season", "seasonal", notes="feeder TARGET (car_av/w_av/…) already here"),
    SourceSpec("nflverse_combine", _nflverse("nflverse_combine", "season"), "nflverse", "player",
               "season", "seasonal"),
    SourceSpec("nflverse_players", _nflverse("nflverse_players", None), "nflverse", "player",
               "season", "seasonal", season_scoped=False, notes="the NFL ID universe; not season-grained"),
]}


def build_ctx(
    *,
    cfbd_key: str | None = None,
    odds_key: str | None = None,
    regions: str = "us",
    snapshot_buffer_min: int = 5,
    sleep_seconds: float = 0.5,
    max_events: int | None = None,
) -> Ctx:
    """Construct the run context. CFBD client is built lazily-lenient: nflverse/odds-only
    runs don't need a CFBD key (but `_season_kickoffs` — hence the paid /historical pull — DOES,
    it reads CFBD `/games` for kickoff times). The odds knobs (regions / snapshot buffer /
    rate-limit sleep / snapshot cap) let odds_backfill tune the paid `/historical` pull (a verify
    pull caps `max_events`; a full pull uses all kickoffs). P0.6."""
    cfbd = None
    if cfbd_key or os.environ.get("CFBD_API_KEY"):
        cfbd = CFBDClient(api_key=cfbd_key)
    return Ctx(
        cfbd=cfbd,
        odds_api_key=odds_key or os.environ.get("ODDS_API_KEY"),
        odds_regions=regions,
        odds_snapshot_buffer_min=snapshot_buffer_min,
        odds_sleep_seconds=sleep_seconds,
        odds_max_events=max_events,
    )


# Convenience groupings the handler/backfill/schedule payloads use.
CFBD_WEEKLY = [n for n, s in SOURCES.items() if s.tier == "cfbd" and s.cadence == "weekly"]
CFBD_SEASONAL = [n for n, s in SOURCES.items() if s.tier == "cfbd" and s.cadence == "seasonal"]
ODDS_SOURCES = [n for n, s in SOURCES.items() if s.tier == "odds"]
NFLVERSE_SOURCES = [n for n, s in SOURCES.items() if s.tier == "nflverse"]
# Odds split by orchestration: recurring LIVE feeds vs the paid /historical CLV backfill (P0.6).
ODDS_LIVE = [n for n, s in SOURCES.items() if s.tier == "odds" and not s.on_demand]
ODDS_ON_DEMAND = [n for n, s in SOURCES.items() if s.tier == "odds" and s.on_demand]
# Everything a DEFAULT (unnamed) run pulls — excludes the on_demand paid odds source (P0.6).
DEFAULT_SOURCES = [n for n, s in SOURCES.items() if not s.on_demand]

# ── The PRE-SEASON ROLL-FORWARD source set (NCAAF-P0.7) ──────────────────────────────────
# The feeds `roll_forward.py` refreshes on a recurring PRE-SEASON cadence so the upcoming
# season's futures board + live game-model board can RUN before kickoff — the SCHEDULE + the
# pre-season COVARIATE priors P1.2 fits its week-1 strength on, and nothing else:
#   • games   — THE 2026 game list (home/away/neutral + conference flags → dim_ncaaf_game).
#               DYNAMIC: pre-season schedules churn (games added/moved/cancelled) all summer →
#               this is the reason the cadence is RECURRING, not a one-time pull.
#   • teams   — FBS membership + the conference structure the CCG/CFP bookkeeping needs.
#   • returning_production / transfer_portal / roster / talent — the P0.4 roster-continuity
#     covariates; coaches — the P0.5 coaching-change covariate; recruiting_players — the P1.2b
#     freshman-production prior. These publish on a ROLLING basis through spring→fall camp
#     (verified live 2026-07-24: games/portal/recruiting/teams already published for 2026, but
#     returning/talent/coaches/roster still returned 0 rows — a second reason the pull must
#     RECUR until kickoff, filling covariates in as CFBD posts them).
# DELIBERATELY EXCLUDED: the per-GAME endpoints (plays / play_stats / box_advanced — the
# ~960-call/season cost that only exists once games are PLAYED) and every odds source (game
# lines are P0.6b's recurring capture, on its own credit budget). So a roll-forward refresh is
# ~8 cheap CFBD calls — trivially affordable weekly. All members are non-paid CFBD sources.
ROLL_FORWARD_SOURCES = [
    "games",
    "teams",
    "returning_production",
    "transfer_portal",
    "roster",
    "talent",
    "coaches",
    "recruiting_players",
]
# Registry-integrity: every roll-forward source must exist, be a (free) CFBD source, and never
# be an on_demand/paid pull — a routine pre-season refresh must not burn Odds credits or fan out
# a per-game endpoint. Enforced here (and in test_ncaaf_roll_forward) so a future edit can't
# silently slip a paid/expensive source into the recurring cadence.
assert all(n in SOURCES for n in ROLL_FORWARD_SOURCES), "ROLL_FORWARD_SOURCES has an unknown source"
assert all(SOURCES[n].tier == "cfbd" and not SOURCES[n].on_demand for n in ROLL_FORWARD_SOURCES), (
    "ROLL_FORWARD_SOURCES must be free (non-on_demand) CFBD sources only"
)
