"""sources.py  (NCAAF-P0.2 — the SPORT-SPECIFIC source registry)
================================================================
The one file that IS NCAAF-specific (sport_data_platform.md §2: "only `sources.py`, the
dbt models, and the schedule payload are sport-specific"). It maps every locked Phase-0
lake table (ncaaf_data_inventory.md §8, 24 tables) → a fetch function + grain + partition +
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
from dataclasses import dataclass, field
from typing import Any, Callable

from .cfbd_client import CFBDClient

log = logging.getLogger(__name__)

SPORT = "ncaaf"

# The FBS-only modelling universe (ncaaf_data_inventory.md §9 open-gap 8: CFBD covers FCS
# unevenly). CFBD week-grained endpoints default to FBS; we keep the season pulls whole.
ODDS_SPORT_KEY = "americanfootball_ncaaf"
ODDS_BASE = "https://api.the-odds-api.com/v4"

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
    the nflverse release reads. Built once per run (handler/backfill)."""

    cfbd: CFBDClient | None = None
    odds_api_key: str | None = None
    _duck: Any = None

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


def _iter_games_safe(gids, fetch_one, label: str) -> list[dict]:
    """Run a per-GAME fetch over gids, SKIPPING (not aborting on) a single game's failure.

    A per-game endpoint must not let one bad game sink the whole season — older games can
    500 on /game/box/advanced (no advanced box exists), and a residual 429 after retries
    should cost one game, not the partition. Each skip is logged; a summary count surfaces
    the gap so the operator can spot + re-run a heavily-skipped season."""
    out: list[dict] = []
    skipped: list[int] = []
    for gid in gids:
        try:
            out.extend(fetch_one(gid))
        except Exception as exc:  # noqa: BLE001 — per-game resilience
            skipped.append(gid)
            log.warning("  [%s] gameId=%s skipped: %s", label, gid, str(exc)[:120])
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
def _odds_get(ctx: Ctx, path: str, params: dict) -> list:
    import requests

    key = ctx.odds_api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY not set (operator provisions it).")
    resp = requests.get(f"{ODDS_BASE}/{path.lstrip('/')}", params={"apiKey": key, **params}, timeout=30)
    resp.raise_for_status()
    if "application/json" not in resp.headers.get("Content-Type", "").lower():
        raise RuntimeError(f"Odds API {path} non-JSON body: {resp.text[:120]!r}")
    data = resp.json()
    return data if isinstance(data, list) else [data]


def _odds_ncaaf(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Current NCAAF game lines (h2h/spreads/totals) across US books (Bovada = target)."""
    return _odds_get(
        ctx,
        f"sports/{ODDS_SPORT_KEY}/odds",
        {"regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"},
    )


def _odds_scores(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Final scores for settlement (daysFrom ≤ 3)."""
    return _odds_get(ctx, f"sports/{ODDS_SPORT_KEY}/scores", {"daysFrom": 3})


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


# ── THE REGISTRY — the 24 locked Phase-0 lake tables (ncaaf_data_inventory.md §8) ────────
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
    SourceSpec("cfbd_draft_picks", _year_only("/draft/picks"), "cfbd", "player", "season",
               "seasonal", notes="the CFBD side of the NFL-feeder draft-slot key (P0.3)"),
    # 18–21 Odds API
    SourceSpec("odds_ncaaf", _odds_ncaaf, "odds", "game", "season/week", "intraday",
               notes="h2h/spreads/totals, 11 US books incl. Bovada"),
    SourceSpec("odds_ncaaf_scores", _odds_scores, "odds", "game", "season/week", "intraday"),
    # 22–24 nflverse (the feeder universe; release Parquet directly)
    SourceSpec("nflverse_draft_picks", _nflverse("nflverse_draft_picks", "season"), "nflverse",
               "player", "season", "seasonal", notes="feeder TARGET (car_av/w_av/…) already here"),
    SourceSpec("nflverse_combine", _nflverse("nflverse_combine", "season"), "nflverse", "player",
               "season", "seasonal"),
    SourceSpec("nflverse_players", _nflverse("nflverse_players", None), "nflverse", "player",
               "season", "seasonal", season_scoped=False, notes="the NFL ID universe; not season-grained"),
]}


def build_ctx(*, cfbd_key: str | None = None, odds_key: str | None = None) -> Ctx:
    """Construct the run context. CFBD client is built lazily-lenient: nflverse/odds-only
    runs don't need a CFBD key."""
    cfbd = None
    if cfbd_key or os.environ.get("CFBD_API_KEY"):
        cfbd = CFBDClient(api_key=cfbd_key)
    return Ctx(cfbd=cfbd, odds_api_key=odds_key or os.environ.get("ODDS_API_KEY"))


# Convenience groupings the handler/backfill/schedule payloads use.
CFBD_WEEKLY = [n for n, s in SOURCES.items() if s.tier == "cfbd" and s.cadence == "weekly"]
CFBD_SEASONAL = [n for n, s in SOURCES.items() if s.tier == "cfbd" and s.cadence == "seasonal"]
ODDS_SOURCES = [n for n, s in SOURCES.items() if s.tier == "odds"]
NFLVERSE_SOURCES = [n for n, s in SOURCES.items() if s.tier == "nflverse"]
