"""adp_source.py — NF-D2 #6 / NF-D3: market-consensus ADP (Fantasy Football Calculator).

The ADP source for BOTH uses the operator asked for: a projection FEATURE/PRIOR (NF-D2 #6) and the
COMPETITOR BENCHMARK (NF-D3). Free, no-auth, reproducible historical + current ADP from Fantasy
Football Calculator's public API (`fantasyfootballcalculator.com/api/v1/adp`). It is a REAL-DRAFT
consensus (thousands of drafts per season — 2018: 2,494 … 2026: 3,091) snapshotted the week before
Week 1, so as a forward signal for the projection season it is **LEAKAGE-SAFE** (the ADP is set
before any of that season's games are played).

Why FFC and not FantasyPros: FantasyPros' ADP table is JS/API-key-gated (the public HTML ships only a
5-row preview), whereas FFC exposes a clean public JSON endpoint with per-player `adp`/`stdev`/`high`/
`low`/`times_drafted`, 2018→present. (2025 is the one gap — FFC returns "No ADP data found" for it;
the backtest simply skips that target season.)

Public API:
  fetch_ffc_adp(season, fmt, teams, cache_dir)  -> normalized ADP DataFrame (name/pos/team/adp/…)
  attach_gsis(con, adp_df, season)              -> ADP joined to our gsis `player_id` via a
                                                   season-accurate (normalized-name, position)
                                                   crosswalk off `fct_player_week` (97–100% of skill
                                                   players match; unmatched → NaN player_id, dropped
                                                   by the consumer)
  load_adp_for_season(con, season, ...)         -> fetch + crosswalk in one call (consumer entry point)

Dependency-light (urllib + pandas). The network fetch caches the raw JSON to `cache_dir` so a run is
reproducible offline once primed. The lake-landing CLI is `run_adp_ingest.py` (lands the NF-D3
`nfl/fantasy/benchmarks/` asset); the ablation harness + the live-board build call these helpers
directly (no lake round-trip required).
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nfl.fantasy.adp")

_FFC_URL = "https://fantasyfootballcalculator.com/api/v1/adp/{fmt}?teams={teams}&year={season}&position=all"
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "adp_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

# The skill positions the projection product covers (FFC also emits PK/DEF — kept in the raw asset,
# excluded from the gsis crosswalk since we do not project them).
_SKILL = ("QB", "RB", "WR", "TE")
_POS_FIX = {"PK": "K", "DST": "DEF", "D/ST": "DEF"}

# Nickname / display-name aliases FFC uses that differ from the nflverse `player_name` — applied AFTER
# normalization (both sides normalized, then the FFC form is rewritten to the nflverse form). Small and
# explicit by design: the (name, position) crosswalk already matches 97–100% of skill players; these
# recover the handful of recurring nickname misses (e.g. FFC "Hollywood Brown" = "Marquise Brown").
_NAME_ALIASES = {
    "hollywood brown": "marquise brown",
    "gabe davis": "gabriel davis",
    "chig okonkwo": "chigoziem okonkwo",
    "cam akers": "cameron akers",
    "joshua palmer": "josh palmer",
    "mike thomas": "michael thomas",
}


def _normalize_name(name: str) -> str:
    """Lower-case ASCII fold, strip generational suffixes + punctuation, collapse whitespace, then
    apply the FFC→nflverse nickname alias map. The crosswalk key builder for both sides."""
    if not name or (isinstance(name, float) and np.isnan(name)):
        return ""
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    n = n.lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    n = re.sub(r"[^a-z ]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return _NAME_ALIASES.get(n, n)


def fetch_ffc_adp(
    season: int, fmt: str = "ppr", teams: int = 12, cache_dir: str | Path | None = None,
    refresh: bool = False, timeout: int = 30,
) -> pd.DataFrame:
    """Fetch + normalize one season of Fantasy Football Calculator ADP. Returns one row per drafted
    player with: `season, source, adp_format, player_name, position, team, adp, adp_stdev, adp_high,
    adp_low, times_drafted`. Empty DataFrame (with the columns) when FFC has no data for the season
    (e.g. 2025). Caches the raw JSON under `cache_dir` so subsequent runs are offline-reproducible."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"ffc_{fmt}_{teams}_{season}.json"

    payload = None
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text())
        except Exception:  # noqa: BLE001 — a corrupt cache just re-fetches
            payload = None
    if payload is None:
        url = _FFC_URL.format(fmt=fmt, teams=teams, season=season)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            payload = json.loads(resp.read().decode())
        cache.write_text(json.dumps(payload))

    cols = ["season", "source", "adp_format", "player_name", "position", "team",
            "adp", "adp_stdev", "adp_high", "adp_low", "times_drafted"]
    if (payload or {}).get("status") != "Success" or not payload.get("players"):
        log.warning("FFC ADP %s %s: no data (status=%s)", season, fmt, (payload or {}).get("status"))
        return pd.DataFrame(columns=cols)

    rows = []
    for p in payload["players"]:
        pos = _POS_FIX.get((p.get("position") or "").upper(), (p.get("position") or "").upper())
        rows.append({
            "season": int(season), "source": "ffc", "adp_format": fmt,
            "player_name": p.get("name"), "position": pos, "team": p.get("team"),
            "adp": pd.to_numeric(p.get("adp"), errors="coerce"),
            "adp_stdev": pd.to_numeric(p.get("stdev"), errors="coerce"),
            "adp_high": pd.to_numeric(p.get("high"), errors="coerce"),
            "adp_low": pd.to_numeric(p.get("low"), errors="coerce"),
            "times_drafted": pd.to_numeric(p.get("times_drafted"), errors="coerce"),
        })
    return pd.DataFrame(rows, columns=cols)


def attach_gsis(con, adp_df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Add our gsis `player_id` to an FFC ADP frame via a season-accurate (normalized-name, position)
    crosswalk off `fct_player_week` (which carries `player_name`, `position`, `player_id`, `season`).
    A unique name-only fallback catches a position label mismatch. Skill positions only (QB/RB/WR/TE);
    PK/DEF rows and unmatched players get `player_id = NA`. Returns adp_df + `player_id`."""
    out = adp_df.copy()
    out["player_id"] = pd.array([pd.NA] * len(out), dtype="string")
    if out.empty:
        return out

    # Rank each player's (name, position) by realized games that season so a normalized-name COLLISION
    # (two players sharing a normalized name) resolves DETERMINISTICALLY to the more-established player,
    # and ORDER the scan so the crosswalk is reproducible run-to-run (a bare `select distinct` has no
    # ordering ⇒ last-write-wins would pick a different gsis per run for a colliding name).
    # played-games is a deterministic TIEBREAK, never a filter — the current (not-yet-started) season's
    # roster rows all have played_flag = false but must still crosswalk (the live board), so keep every
    # distinct (player_id, name, position) and just order the more-established player first.
    ref = con.sql(f"""
        select player_id, player_name, position,
               count(*) filter (where coalesce(played_flag, false)) as g_played
        from {schema}.fct_player_week
        where season = {int(season)} and player_id is not null
        group by 1, 2, 3
        order by g_played desc, player_id asc
    """).df()
    by_name_pos: dict[tuple[str, str], str] = {}
    by_name: dict[str, list[str]] = {}
    for _, r in ref.iterrows():
        nn = _normalize_name(r["player_name"])
        pos = (r["position"] or "").upper()
        by_name_pos.setdefault((nn, pos), r["player_id"])   # first (most games) wins; deterministic
        by_name.setdefault(nn, []).append(r["player_id"])

    pid = []
    for _, r in out.iterrows():
        pos = (r["position"] or "").upper()
        if pos not in _SKILL:
            pid.append(pd.NA)
            continue
        nn = _normalize_name(r["player_name"])
        hit = by_name_pos.get((nn, pos))
        if hit is None:
            uniq = sorted(set(by_name.get(nn, [])))   # dedup a multi-position player to one gsis
            hit = uniq[0] if len(uniq) == 1 else None
        pid.append(hit if hit is not None else pd.NA)
    out["player_id"] = pd.array(pid, dtype="string")
    return out


def load_adp_for_season(
    con, season: int, fmt: str = "ppr", teams: int = 12,
    cache_dir: str | Path | None = None, refresh: bool = False, schema: str = "main_nfl_marts",
) -> pd.DataFrame:
    """Consumer entry point: fetch FFC ADP for `season` and crosswalk it to our gsis `player_id`.
    Returns the normalized ADP frame + `player_id` (NA where unmatched / non-skill). Empty when FFC
    has no data for the season."""
    adp = fetch_ffc_adp(season, fmt=fmt, teams=teams, cache_dir=cache_dir, refresh=refresh)
    return attach_gsis(con, adp, season, schema=schema)


def coverage(adp_df: pd.DataFrame) -> dict:
    """Quick match diagnostics for a crosswalked frame (for logs / the ingest report)."""
    skill = adp_df[adp_df["position"].isin(_SKILL)]
    matched = skill["player_id"].notna().sum() if "player_id" in skill else 0
    return {
        "n_rows": int(len(adp_df)),
        "n_skill": int(len(skill)),
        "n_matched": int(matched),
        "pct_matched": round(100.0 * matched / max(1, len(skill)), 1),
        "by_position": {k: int(v) for k, v in adp_df.groupby("position").size().items()},
    }
