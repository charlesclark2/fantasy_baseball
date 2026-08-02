"""mfl_adp_source.py — NF3.2: MyFantasyLeague (MFL) as a SECOND real-draft ADP source.

Registered for two purposes: (1) an independent cross-validation system in the NF-D3 scorecard,
scored alongside FFC across ALL 7 backtest seasons (2019-2025) — does our claimed edge over ADP hold
up against a SEPARATE crowd-sourced draft consensus, not just FFC's? (2) the fallback for the public
track-record page's per-player ADP column specifically for a season FFC has no archive for at all
(2025, confirmed via FFC's live API returning `{"status":"Error"}` across every teams/format
combination) — see `benchmark_scorecard.player_track_record_frame`'s `fallback_adp_fn` param.

Free, no-auth, reproducible historical ADP from MFL's public export API
(`api.myfantasyleague.com/{season}/export?TYPE=adp`). Confirmed genuinely YEAR-SCOPED, not a
live-only snapshot the way FantasyPros' public ADP page is: 2019 rank-1 is Saquon Barkley (correct —
his post-rookie-year hype), 2025 rank-1 is Ja'Marr Chase (correct for that draft season); id `13604`
(Barkley) is independently rank-1 in 2019 and rank-4 in 2025, consistent with his real career arc
(2018 Giants rookie sensation -> 2024 Eagles resurgence). Player identity comes back as a bare numeric
MFL id; a companion `TYPE=players` call (the full player database, ~2.8k rows, ONE call covers every
season since MFL ids are persistent) resolves id -> name/position/team, in "Last, First" order —
reversed here to "First Last" before the SHARED `adp_source.attach_gsis` crosswalk runs (never a
re-derived parallel name-normalization).

Public API (mirrors adp_source.py / sleeper_source.py):
  fetch_mfl_adp(season, fmt, teams, cache_dir)  -> normalized ADP DataFrame (name/pos/team/adp/…),
                                                    the SAME columns adp_source.fetch_ffc_adp returns
  attach_gsis(con, adp_df, season)              -> delegates to the SHARED adp_source.attach_gsis
  load_adp_for_season(con, season, ...)         -> fetch + crosswalk (consumer entry point)

Dependency-light (urllib + pandas). Caches both the raw ADP JSON and the player-directory JSON per
season under `cache_dir` so a run is reproducible offline once primed.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

log = logging.getLogger("nfl.fantasy.mfl_adp")

_MFL_ADP_URL = "https://api.myfantasyleague.com/{season}/export?TYPE=adp&FCOUNT={teams}&IS_PPR={is_ppr}&JSON=1"
_MFL_PLAYERS_URL = "https://api.myfantasyleague.com/{season}/export?TYPE=players&JSON=1"
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "mfl_adp_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

_COLS = ["season", "source", "adp_format", "player_name", "position", "team",
         "adp", "adp_stdev", "adp_high", "adp_low", "times_drafted"]


def _fetch_json(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _load_player_directory(
    season: int, cache_dir: Path, refresh: bool, timeout: int,
) -> dict[str, tuple[str, str, str | None]]:
    """MFL id -> (player_name in 'First Last' order, position, team). ONE call per season (MFL scopes
    the export by season path even though the underlying pool is nearly identical year to year — cache
    per season rather than assume it never changes, e.g. a mid-career name change or a late add)."""
    cache = cache_dir / f"mfl_players_{season}.json"
    payload = None
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text())
        except Exception:  # noqa: BLE001 — a corrupt cache just re-fetches
            payload = None
    if payload is None:
        payload = _fetch_json(_MFL_PLAYERS_URL.format(season=season), timeout)
        if (payload.get("players") or {}).get("player"):
            cache.write_text(json.dumps(payload))
        else:
            log.warning("MFL players %s: empty response — the next run will re-fetch", season)

    directory: dict[str, tuple[str, str, str | None]] = {}
    for p in (payload.get("players") or {}).get("player") or []:
        raw_name = p.get("name") or ""
        last, sep, first = raw_name.partition(", ")
        display = f"{first} {last}".strip() if sep else raw_name
        directory[p.get("id")] = (display, (p.get("position") or "").upper(), p.get("team"))
    return directory


def fetch_mfl_adp(
    season: int, fmt: str = "ppr", teams: int = 12, cache_dir: str | Path | None = None,
    refresh: bool = False, timeout: int = 30,
) -> pd.DataFrame:
    """Fetch + normalize one season of MyFantasyLeague ADP. Returns one row per drafted player with:
    `season, source, adp_format, player_name, position, team, adp, adp_stdev, adp_high, adp_low,
    times_drafted` — the SAME columns `adp_source.fetch_ffc_adp` returns, so both sources are
    interchangeable to any consumer. Empty DataFrame (with the columns) on a genuinely empty response
    (never observed live for MFL at the time this was written, unlike FFC's 2025 gap — but handled the
    same defensive way regardless)."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    is_ppr = 1 if fmt == "ppr" else 0
    cache = cache_dir / f"mfl_{fmt}_{teams}_{season}.json"

    payload = None
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text())
        except Exception:  # noqa: BLE001 — a corrupt cache just re-fetches
            payload = None
    if payload is None:
        payload = _fetch_json(_MFL_ADP_URL.format(season=season, teams=teams, is_ppr=is_ppr), timeout)
        if (payload.get("adp") or {}).get("player"):
            cache.write_text(json.dumps(payload))
        else:
            log.warning("MFL ADP %s %s: empty response — the next run will re-fetch", season, fmt)

    players = (payload.get("adp") or {}).get("player") or []
    if not players:
        log.warning("MFL ADP %s %s: no data", season, fmt)
        return pd.DataFrame(columns=_COLS)

    directory = _load_player_directory(season, cache_dir, refresh, timeout)
    rows = []
    for p in players:
        name, pos, team = directory.get(p.get("id"), (None, None, None))
        if name is None:
            continue  # id absent from the player directory — cannot crosswalk, skip rather than guess
        rows.append({
            "season": int(season), "source": "mfl", "adp_format": fmt,
            "player_name": name, "position": pos, "team": team,
            "adp": pd.to_numeric(p.get("averagePick"), errors="coerce"),
            "adp_stdev": None,  # MFL does not publish a stdev, unlike FFC
            "adp_high": pd.to_numeric(p.get("maxPick"), errors="coerce"),
            "adp_low": pd.to_numeric(p.get("minPick"), errors="coerce"),
            "times_drafted": pd.to_numeric(p.get("draftsSelectedIn"), errors="coerce"),
        })
    return pd.DataFrame(rows, columns=_COLS)


def attach_gsis(con, adp_df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Delegates to the SHARED `adp_source.attach_gsis` crosswalk (normalized-name, position) —
    same pattern `sleeper_source.py` uses. Never a re-derived parallel crosswalk."""
    return A.attach_gsis(con, adp_df, season, schema=schema)


def load_adp_for_season(
    con, season: int, fmt: str = "ppr", teams: int = 12,
    cache_dir: str | Path | None = None, refresh: bool = False, schema: str = "main_nfl_marts",
) -> pd.DataFrame:
    """Consumer entry point: fetch MFL ADP for `season` and crosswalk it to our gsis `player_id`.
    Returns the normalized ADP frame + `player_id` (NA where unmatched / non-skill)."""
    adp = fetch_mfl_adp(season, fmt=fmt, teams=teams, cache_dir=cache_dir, refresh=refresh)
    return attach_gsis(con, adp, season, schema=schema)
