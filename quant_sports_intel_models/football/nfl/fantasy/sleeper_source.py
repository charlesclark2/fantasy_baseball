"""sleeper_source.py — NF-D3: Sleeper (Rotowire) season projections as a competitor benchmark.

The THIRD benchmark system, and the first that is a real POINT-projection system rather than a ranking:
Sleeper serves Rotowire's full-season projected stat line (incl. `pts_ppr` + projected games) from a
free, no-auth public endpoint, 2019→present. Being an actual projection makes it a natural
head-to-head for our projection product.

⭐ WHY IT CLEARS THE HONESTY BAR (leakage — verified by a concrete test): Sleeper's HISTORICAL season
  projection is the FROZEN PRESEASON projection, NOT a hindsight-updated one. Proof: 2021 Christian
  McCaffrey (who actually played only 7 games that year, injured) is projected at gp=17.0 / 363 pts —
  the full-season preseason ceiling; every player's projected games is the full slate. A leaked
  projection would show his realized ~7 games. So it is leakage-safe as a forward signal for the
  projection season. (Provider: `company="rotowire"`.)

Endpoint (public, no key):
  https://api.sleeper.app/projections/nfl/{season}?season_type=regular&position[]=QB&…&order_by=pts_ppr
Each row embeds `player` (first/last name, position), `player_id` (Sleeper's), and `stats` (`pts_ppr`,
`pts_half_ppr`, `pts_std`, `gp`, and the raw projected stat line).

Public API (mirrors `adp_source`/`fantasypros_source`):
  fetch_sleeper_proj(season, cache_dir)  -> normalized projection DataFrame
  attach_gsis(con, df, season)           -> ⋈ our gsis `player_id` via the shared name crosswalk
  load_sleeper_for_season(con, season)   -> fetch + crosswalk (consumer entry point)

Dependency-light (urllib + pandas), caches the raw JSON so a run is reproducible offline once primed.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

log = logging.getLogger("nfl.fantasy.sleeper")

_BASE = "https://api.sleeper.app/projections/nfl/{season}"
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "sleeper_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
_SKILL = ("QB", "RB", "WR", "TE")

_COLS = ["season", "source", "provider", "player_name", "position", "team",
         "proj_pts_ppr", "proj_pts_half", "proj_pts_std", "proj_games", "sleeper_id"]


def fetch_sleeper_proj(
    season: int, cache_dir: str | Path | None = None, refresh: bool = False, timeout: int = 30,
) -> pd.DataFrame:
    """Fetch + normalize one season of Sleeper (Rotowire) season projections for the skill positions.
    Returns one row per projected player: `season, source, provider, player_name, position, team,
    proj_pts_ppr, proj_pts_half, proj_pts_std, proj_games, sleeper_id`. Empty DataFrame (with the
    columns) when Sleeper has no data. Caches the raw JSON."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"sleeper_{season}.json"

    payload = None
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text())
        except Exception:  # noqa: BLE001 — a corrupt cache just re-fetches
            payload = None
    if payload is None:
        q = [("season_type", "regular"), ("order_by", "pts_ppr")] + [("position[]", p) for p in _SKILL]
        url = _BASE.format(season=season) + "?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            payload = json.loads(resp.read().decode())
        cache.write_text(json.dumps(payload))

    if not payload:
        log.warning("Sleeper projections %s: no data", season)
        return pd.DataFrame(columns=_COLS)

    rows = []
    for r in payload:
        pl = r.get("player") or {}
        pos = (pl.get("position") or "").upper()
        st = r.get("stats") or {}
        nm = " ".join(x for x in [pl.get("first_name"), pl.get("last_name")] if x).strip()
        rows.append({
            "season": int(season), "source": "sleeper", "provider": r.get("company"),
            "player_name": nm, "position": pos, "team": r.get("team"),
            "proj_pts_ppr": pd.to_numeric(st.get("pts_ppr"), errors="coerce"),
            "proj_pts_half": pd.to_numeric(st.get("pts_half_ppr"), errors="coerce"),
            "proj_pts_std": pd.to_numeric(st.get("pts_std"), errors="coerce"),
            "proj_games": pd.to_numeric(st.get("gp"), errors="coerce"),
            "sleeper_id": r.get("player_id"),
        })
    df = pd.DataFrame(rows, columns=_COLS)
    return df[df["position"].isin(_SKILL)].reset_index(drop=True)


def attach_gsis(con, df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Add our gsis `player_id` via the SHARED `adp_source` (normalized-name, position) crosswalk."""
    return A.attach_gsis(con, df, season, schema=schema)


def load_sleeper_for_season(
    con, season: int, cache_dir: str | Path | None = None, refresh: bool = False,
    schema: str = "main_nfl_marts",
) -> pd.DataFrame:
    """Consumer entry point: fetch Sleeper (Rotowire) projections for `season` + crosswalk to gsis."""
    df = fetch_sleeper_proj(season, cache_dir=cache_dir, refresh=refresh)
    return attach_gsis(con, df, season, schema=schema)


def coverage(df: pd.DataFrame) -> dict:
    skill = df[df["position"].isin(_SKILL)]
    matched = skill["player_id"].notna().sum() if "player_id" in skill else 0
    return {
        "n_rows": int(len(df)),
        "n_skill": int(len(skill)),
        "n_matched": int(matched),
        "pct_matched": round(100.0 * matched / max(1, len(skill)), 1),
        "by_position": {k: int(v) for k, v in df.groupby("position").size().items()},
    }
