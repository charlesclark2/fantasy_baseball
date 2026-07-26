"""espn_source.py — NF-D3: ESPN PPR draft-rank as a competitor benchmark (4th system).

ESPN's fantasy read API exposes, per season, each player's PPR DRAFT RANK (`draftRanksByRankType.PPR`)
— ESPN's preseason consensus draft ordering. We grade it as a RANKING (like ADP/ECR), score = −rank.

⚠️ CAVEATS (why this is the fragile / lower-confidence benchmark):
  • UNOFFICIAL read API (`lm-api-reads.fantasy.espn.com`) — no auth for public player data, but it can
    change/break without notice. Treat an outage as "NULL this system," never fabricate.
  • The payload is large (~25 MB/season, all players) — an offline once-a-year ingest, not a hot path.
  • Leakage: a DRAFT RANK is inherently a PRESEASON artifact, so historically it is reasonably
    leakage-safe — but unlike ADP (dated week-before-Week-1) and ECR (dated early-Sept snapshot), ESPN
    does not stamp the rank's as-of date in this response, so it is LESS-verified than those two. We use
    the draft RANK (not ESPN's projected points, which need a scoring config applied and returned NULL
    in the plain view).

Endpoint (public read):
  https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/players?scoringPeriodId=0&view=kona_player_info
  + header  x-fantasy-filter: {"players":{"sortDraftRanks":{"sortPriority":100,"sortAsc":true,"value":"PPR"}}}

Public API (mirrors the other benchmark sources):
  fetch_espn_draftranks(season, cache_dir)  -> normalized rank DataFrame
  attach_gsis(con, df, season)              -> ⋈ our gsis `player_id` via the shared name crosswalk
  load_espn_for_season(con, season)         -> fetch + crosswalk (consumer entry point)
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

log = logging.getLogger("nfl.fantasy.espn")

_URL = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players"
        "?scoringPeriodId=0&view=kona_player_info")
_FILTER = '{"players":{"sortDraftRanks":{"sortPriority":100,"sortAsc":true,"value":"PPR"}}}'
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "espn_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
# ESPN defaultPositionId → position
_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
_SKILL = ("QB", "RB", "WR", "TE")

_COLS = ["season", "source", "player_name", "position", "espn_id", "ppr_draft_rank"]


def fetch_espn_draftranks(
    season: int, cache_dir: str | Path | None = None, refresh: bool = False, timeout: int = 45,
) -> pd.DataFrame:
    """Fetch + normalize one season of ESPN PPR draft ranks. Returns `season, source, player_name,
    position, espn_id, ppr_draft_rank` (skill positions with a real PPR rank). Empty on no-data.
    Caches the raw JSON."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"espn_{season}.json"

    payload = None
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            payload = None
    if payload is None:
        req = urllib.request.Request(_URL.format(season=season),
                                     headers={"User-Agent": _UA, "x-fantasy-filter": _FILTER})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            payload = json.loads(resp.read().decode())
        cache.write_text(json.dumps(payload))

    players = payload if isinstance(payload, list) else (payload or {}).get("players") or []
    if not players:
        log.warning("ESPN draft ranks %s: no data", season)
        return pd.DataFrame(columns=_COLS)

    rows = []
    for p in players:
        pos = _POS.get(p.get("defaultPositionId"))
        rank = ((p.get("draftRanksByRankType") or {}).get("PPR") or {}).get("rank")
        rank = pd.to_numeric(rank, errors="coerce")
        if pos is None or pd.isna(rank) or rank <= 0:
            continue
        rows.append({
            "season": int(season), "source": "espn",
            "player_name": p.get("fullName"), "position": pos, "espn_id": p.get("id"),
            "ppr_draft_rank": float(rank),
        })
    df = pd.DataFrame(rows, columns=_COLS)
    return df[df["position"].isin(_SKILL)].reset_index(drop=True)


def attach_gsis(con, df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Add our gsis `player_id` via the SHARED `adp_source` (normalized-name, position) crosswalk."""
    return A.attach_gsis(con, df, season, schema=schema)


def load_espn_for_season(
    con, season: int, cache_dir: str | Path | None = None, refresh: bool = False,
    schema: str = "main_nfl_marts",
) -> pd.DataFrame:
    """Consumer entry point: fetch ESPN PPR draft ranks for `season` + crosswalk to gsis."""
    df = fetch_espn_draftranks(season, cache_dir=cache_dir, refresh=refresh)
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
