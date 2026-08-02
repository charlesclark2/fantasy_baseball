"""sleeper_players_source.py — NF-C0c: the Sleeper player-id → name/position/team bridge.

NF-C0's Sleeper import returns rosters as bare player ids (`["11599","5846",…]`) — Sleeper's roster
endpoint carries no names, and resolving them needs `v1/players/nfl`, a ~11k-player dump Sleeper's
own guidance says to fetch AT MOST ONCE A DAY. That is too heavy for a request path (an import
preview would pull ~5 MB of unread metadata on every call), so this module is the OFFLINE half: a
daily-ish job (`run_sleeper_player_ingest.py`) fetches the dump, resolves each player onto OUR
`gsis_id` where possible, and stages a SLIM artifact for the API to read (see that script + the
backend's `app.backend.services.platform_import.sleeper_players` for the narrow, memoized read side).

⭐ THE BRIDGE TARGET IS `gsis_id`, DIRECT — not a generic external-id search. Our projection keys on
`gsis_id` (`season_projection.py`, `export_draft_board_json.py`), and Sleeper's own player rows carry
`gsis_id` natively, so the common case is a straight `sleeper.gsis_id == our gsis_id` join with no
fuzzy leg at all. The name+position crosswalk fallback below exists ONLY for the cohort where one
side lacks a `gsis_id` — nflverse ships null/late `gsis_id` for ROOKIES/IDPs (the NF-D12 lesson),
which is exactly the draft-relevant cohort, so `coverage()` reports the fallback's match rate
separately for rookies rather than folding it into one overall number that would hide the weak spot.

Scope is intentionally NOT filtered to skill positions the way `adp_source`/`sleeper_source`/
`sleeper_injuries_source` are: an imported ROSTER can carry a kicker, a team defense, or an IDP slot
(see `sleeper.ROSTER_SLOT_MAP`), and every one of those needs a readable NAME even though only
QB/RB/WR/TE get a `gsis_id` crosswalk attempt (K/DST/IDP aren't in our projection universe —
`fct_player_week` has nothing to crosswalk them against, and Sleeper's own `gsis_id` is used as-is
when present). "Slim" here means dropping the ~90% of Sleeper's per-player FIELDS we never read
(age, college, injury notes, every other platform's id, headshot, …), not dropping players.

Public API (mirrors `sleeper_injuries_source`'s shape):
  fetch_all_sleeper_players(cache_dir, refresh, as_of)  -> normalized DataFrame (pre-gsis-crosswalk)
  attach_gsis(con, df, season)                          -> resolves `gsis_id`: Sleeper's own NATIVE
                                                            value first; for skill positions only,
                                                            a deterministic (name, position) crosswalk
                                                            fallback (`adp_source.attach_gsis`,
                                                            played_flag TIEBREAK never a filter) where
                                                            it's null
  slim_artifact(df)                                     -> {sleeper_player_id: {name, position, team,
                                                             gsis_id?}} — the JSON actually published
  coverage(df)                                          -> match-rate diagnostics, skill players
                                                             overall AND rookies (years_exp==0) alone

Dependency-light (urllib + pandas), caches the raw JSON per calendar day so a run is reproducible
offline once primed.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

log = logging.getLogger("nfl.fantasy.sleeper_players")

_BASE = "https://api.sleeper.app/v1/players/nfl"
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "sleeper_players_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

# Only these positions have a `gsis_id` crosswalk fallback attempted (our projection universe —
# `fct_player_week` carries no K/DST/IDP rows to crosswalk against). Mirrors adp_source/
# sleeper_injuries_source's `_SKILL`.
_SKILL = ("QB", "RB", "WR", "TE")

_FETCH_COLS = ["sleeper_player_id", "player_name", "position", "team", "gsis_id", "years_exp"]


def fetch_all_sleeper_players(
    cache_dir: "str | Path | None" = None, refresh: bool = False, timeout: int = 30,
    as_of: "str | None" = None,
) -> pd.DataFrame:
    """Fetch + normalize Sleeper's full `v1/players/nfl` snapshot (free, no key; ~11k entries).
    UNFILTERED by position — an imported roster can hold any slot Sleeper deals in (K, DEF, IDP,
    not just QB/RB/WR/TE), and every one needs a name. Returns one row per player: `sleeper_player_id,
    player_name, position, team, gsis_id, years_exp`. Empty DataFrame (with the columns) when Sleeper
    has no data. Caches the raw JSON per calendar day (`as_of`, default today)."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    as_of = as_of or date.today().isoformat()
    cache = cache_dir / f"sleeper_players_full_{as_of}.json"

    payload = None
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text())
        except Exception:  # noqa: BLE001 — a corrupt cache just re-fetches
            payload = None
    if payload is None:
        req = urllib.request.Request(_BASE, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            payload = json.loads(resp.read().decode())
        cache.write_text(json.dumps(payload))

    if not payload:
        log.warning("Sleeper players feed: no data")
        return pd.DataFrame(columns=_FETCH_COLS)

    rows = []
    for sid, pl in (payload or {}).items():
        pl = pl or {}
        pos = (pl.get("position") or "").upper()
        nm = (
            pl.get("full_name")
            or " ".join(x for x in [pl.get("first_name"), pl.get("last_name")] if x).strip()
            or pl.get("team")
            or ""
        )
        if not nm:
            continue  # nothing to display — not worth an artifact entry
        years_exp = pl.get("years_exp")
        rows.append({
            "sleeper_player_id": str(sid), "player_name": nm, "position": pos or None,
            "team": pl.get("team"), "gsis_id": pl.get("gsis_id"),
            "years_exp": years_exp if isinstance(years_exp, (int, float)) else np.nan,
        })
    return pd.DataFrame(rows, columns=_FETCH_COLS).reset_index(drop=True)


def attach_gsis(con, df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Resolve `gsis_id`: keep Sleeper's own NATIVE value where present; for SKILL-position rows
    (QB/RB/WR/TE) whose native value is null, fall back to the SHARED deterministic (name, position)
    crosswalk (`adp_source.attach_gsis`) off `fct_player_week` for `season`. K/DST/IDP rows are never
    crosswalked (nothing to crosswalk against) and keep whatever Sleeper gave them (often null)."""
    out = df.copy()
    if out.empty:
        out["gsis_id"] = pd.array([], dtype="string")
        return out
    out["gsis_id"] = out["gsis_id"].astype("string")
    missing = out["gsis_id"].isna() | (out["gsis_id"].str.strip() == "")
    skill = out["position"].isin(_SKILL)
    fallback_rows = missing & skill
    if fallback_rows.any():
        crosswalked = A.attach_gsis(con, out.loc[fallback_rows], season, schema=schema)
        out.loc[fallback_rows, "gsis_id"] = crosswalked["player_id"].values
    return out


def slim_artifact(df: pd.DataFrame) -> dict:
    """The actual published JSON: `{sleeper_player_id: {name, position, team, gsis_id?}}`. Drops
    `years_exp` (ingest-time diagnostic only) and every field `fetch_all_sleeper_players` never
    fetched in the first place — this IS the ~90%-smaller artifact the story asks for."""
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        pid = str(r.get("sleeper_player_id") or "").strip()
        name = str(r.get("player_name") or "").strip()
        if not pid or not name:
            continue
        entry: dict = {
            "name": name,
            "position": (str(r["position"]).strip() or None) if pd.notna(r.get("position")) else None,
            "team": (str(r["team"]).strip() or None) if pd.notna(r.get("team")) else None,
        }
        gsis = r.get("gsis_id")
        if gsis is not None and pd.notna(gsis) and str(gsis).strip():
            entry["gsis_id"] = str(gsis).strip()
        out[pid] = entry
    return out


def coverage(df: pd.DataFrame) -> dict:
    """Match-rate diagnostics for the ingest report — skill positions only (the only cohort a
    `gsis_id` crosswalk is even attempted for), split overall vs. rookies-only. Rookies are reported
    separately because that is where the fallback is weakest (nflverse's null/late `gsis_id` for
    first-year players — NF-D12) and where an imported roster/draft board cares most."""
    def _rate(frame: pd.DataFrame) -> dict:
        n = int(len(frame))
        if n == 0 or "gsis_id" not in frame:
            return {"n": n, "n_matched": 0, "pct_matched": 0.0}
        matched = int((frame["gsis_id"].notna() & (frame["gsis_id"].astype(str).str.strip() != "")).sum())
        return {"n": n, "n_matched": matched, "pct_matched": round(100.0 * matched / max(1, n), 1)}

    skill = df[df["position"].isin(_SKILL)] if "position" in df else df.iloc[0:0]
    rookies = (
        skill[pd.to_numeric(skill.get("years_exp"), errors="coerce").fillna(-1).astype(int) == 0]
        if "years_exp" in skill else skill.iloc[0:0]
    )
    return {
        "n_rows": int(len(df)),
        "skill_overall": _rate(skill),
        "skill_rookies": _rate(rookies),
    }
