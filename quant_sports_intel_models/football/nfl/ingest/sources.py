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
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

SPORT = "nfl"

ODDS_SPORT_KEY = "americanfootball_nfl"
ODDS_BASE = "https://api.the-odds-api.com/v4"

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
    release reads. Built once per run (handler/backfill)."""

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
def _odds_get(ctx: Ctx, path: str, params: dict) -> list[dict]:
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


def _odds_nfl(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Current NFL game lines (h2h/spreads/totals) across US books (Bovada = target). Bulk
    `/odds` endpoint (3 credits/pull); props + alt markets are the EVENT endpoint (N0.4)."""
    return _odds_get(
        ctx,
        f"sports/{ODDS_SPORT_KEY}/odds",
        {"regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"},
    )


def _odds_scores(ctx: Ctx, year: int, *, weeks=None) -> list[dict]:
    """Final scores for settlement (daysFrom ≤ 3)."""
    return _odds_get(ctx, f"sports/{ODDS_SPORT_KEY}/scores", {"daysFrom": 3})


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
    # ── Odds API (raw_json) ─────────────────────────────────────────────────────────────
    SourceSpec("odds_nfl", _odds_nfl, "odds", "game", "season/week", "intraday", typed=False,
               notes="h2h/spreads/totals, 11 US books incl. Bovada"),
    SourceSpec("odds_nfl_scores", _odds_scores, "odds", "game", "season/week", "intraday", typed=False),
]}


def build_ctx(*, odds_key: str | None = None) -> Ctx:
    """Construct the run context. nflverse-only runs don't need the Odds key."""
    return Ctx(odds_api_key=odds_key or os.environ.get("ODDS_API_KEY"))


# Convenience groupings the handler/backfill/schedule payloads use.
NFLVERSE_SOURCES = [n for n, s in SOURCES.items() if s.tier == "nflverse"]
ODDS_SOURCES = [n for n, s in SOURCES.items() if s.tier == "odds"]
# The advanced stack (2016–2025 floor); the box/team/roster set can extend to 1999 (§7).
NFLVERSE_WEEKLY = [n for n, s in SOURCES.items() if s.tier == "nflverse" and s.cadence == "weekly"]
NFLVERSE_SEASONAL = [n for n, s in SOURCES.items() if s.tier == "nflverse" and s.cadence == "seasonal"]
