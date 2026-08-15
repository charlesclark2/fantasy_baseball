"""sleeper_injuries_source.py — NF-D5: Sleeper's player feed as an EARLIER, offseason-covering
forward-availability source (continues NF-D2 slice 5's roster-status unavailability flag).

NF-D2 slice 5 shipped a projection-season roster-status cap (RES/PUP/NFI/SUS →
`_INJURY_STATUS_GAMES_CAP` in `season_projection.py`) sourced from nflverse's weekly rosters. That
source is IN-LAKEHOUSE but LAGS: nflverse's injury report is in-season-only and the offseason roster
`status` column doesn't reliably surface a fresh PUP/IR/surgery designation until camp. Sleeper's free
`v1/players/nfl` snapshot (~11k players, no auth) carries `injury_status`/`injury_body_part` that is
updated as news breaks — MONTHS earlier for offseason surgeries.

⭐ THIS IS A DIFFERENT ENDPOINT than `sleeper_source.py` (NF-D3's `projections/nfl/{season}` full-
season point-projection benchmark) — that module is unrelated to this one; do not conflate them.

⚠️ Sleeper's `injury_status` mixes TWO kinds of tag: long-absence roster designations (PUP/IR/NFI/
Suspended — what we want) and weekly game-report tags (Questionable/Doubtful/Out — the channel NF-D2
slice 5 already found weak/confounded as a projection signal, deliberately NOT used). `map_injury_status`
maps ONLY the long-absence set onto the shared RES/PUP/NFI/SUS vocabulary `injury_availability_games`
already consumes; the weekly tags map to None (no-op) so this feed never re-introduces that rejected
channel.

Public API (mirrors `adp_source`/`sleeper_source`):
  fetch_sleeper_players(cache_dir, refresh, as_of)  -> normalized DataFrame (pre-gsis-crosswalk)
  attach_gsis(con, df, season)                      -> resolves `player_id`: Sleeper's own NATIVE
                                                        `gsis_id` first, a deterministic (name,
                                                        position) crosswalk fallback (shared with
                                                        `adp_source.attach_gsis` — played_flag TIEBREAK,
                                                        never a filter; sport_data_platform.md's NF-D2
                                                        #6 landmine) only where it's null
  load_sleeper_injuries(con, season, ...)            -> fetch + crosswalk + stamp (ingest entry point;
                                                        `run_sleeper_injuries_ingest.py` lands this to
                                                        `nfl/raw/sleeper_injuries`)
  load_sleeper_injuries_with_coverage(con, season)   -> the same frame PLUS the coverage measured
                                                        BEFORE the unresolved-row drop — the only
                                                        place a collapsed crosswalk is visible
                                                        (NF-INFRA1); use this for anything that WRITES
  classify_land(coverage, ...)                       -> PURE land verdict: may this snapshot be
                                                        written, or would it overwrite a good
                                                        partition with a degraded one?

Dependency-light (urllib + pandas), caches the raw JSON per calendar day so a run is reproducible
offline once primed and a daily recurring capture naturally refetches a new snapshot.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

log = logging.getLogger("nfl.fantasy.sleeper_injuries")

_BASE = "https://api.sleeper.app/v1/players/nfl"
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "sleeper_injuries_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

# The skill positions the projection product covers (mirrors adp_source/sleeper_source's _SKILL) —
# Sleeper's players feed carries every position/unit; scope to what the board projects.
_SKILL = ("QB", "RB", "WR", "TE")

# Sleeper injury_status (free text) → the shared forward-unavailability vocabulary
# `_INJURY_STATUS_GAMES_CAP` (season_projection.py) expects. Only the LONG-ABSENCE designations map;
# weekly game-report tags (Questionable/Doubtful/Out/etc.) are deliberately left unmapped (None).
_STATUS_MAP = {
    "PUP": "PUP",
    "IR": "RES",
    "RESERVE": "RES",
    "INJURED RESERVE": "RES",
    "NFI": "NFI",
    "NON FOOTBALL INJURY": "NFI",
    "SUS": "SUS",
    "SUSPENDED": "SUS",
}

_FETCH_COLS = ["sleeper_player_id", "player_name", "position", "team", "gsis_id",
               "injury_status", "injury_body_part", "proj_status"]
_ASSET_COLS = ["season", "sleeper_player_id", "player_id", "player_name", "position", "team",
               "gsis_id", "injury_status", "injury_body_part", "proj_status", "ingested_at"]


def map_injury_status(injury_status) -> "str | None":
    """Pure — Sleeper's free-text `injury_status` → RES/PUP/NFI/SUS (or None for a weekly
    game-report tag / unknown value / null, i.e. no override)."""
    if injury_status is None:
        return None
    hit = _STATUS_MAP.get(str(injury_status).strip().upper())
    return hit


def fetch_sleeper_players(
    cache_dir: "str | Path | None" = None, refresh: bool = False, timeout: int = 30,
    as_of: "str | None" = None,
) -> pd.DataFrame:
    """Fetch + normalize Sleeper's full `v1/players/nfl` snapshot (free, no key; ~11k players),
    filtered to skill positions. Returns one row per player: `sleeper_player_id, player_name,
    position, team, gsis_id, injury_status, injury_body_part, proj_status` (the last one mapped via
    `map_injury_status`). Empty DataFrame (with the columns) when Sleeper has no data. Caches the raw
    JSON per calendar day (`as_of`, default today) — a daily recurring capture naturally gets a fresh
    snapshot; re-running the same day is offline-reproducible."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    as_of = as_of or date.today().isoformat()
    cache = cache_dir / f"sleeper_players_{as_of}.json"

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
        if pos not in _SKILL:
            continue
        nm = pl.get("full_name") or " ".join(
            x for x in [pl.get("first_name"), pl.get("last_name")] if x).strip()
        rows.append({
            "sleeper_player_id": sid, "player_name": nm, "position": pos, "team": pl.get("team"),
            "gsis_id": pl.get("gsis_id"),
            "injury_status": pl.get("injury_status"), "injury_body_part": pl.get("injury_body_part"),
        })
    df = pd.DataFrame(rows, columns=_FETCH_COLS[:-1])
    df["proj_status"] = df["injury_status"].map(map_injury_status) if not df.empty else pd.Series(dtype="object")
    return df.reset_index(drop=True)


def attach_gsis(con, df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Resolve `player_id`: PREFER Sleeper's own native `gsis_id` (present for most players — verified
    live 2026-07-26); for rows where it's null, fall back to the SHARED deterministic (name, position)
    crosswalk (`adp_source.attach_gsis` — group-by + a played_flag TIEBREAK, never a filter, so a
    not-yet-started season's all-`played_flag=false` rosters still resolve; sport_data_platform.md's
    NF-D2 #6 landmine) off `fct_player_week` for `season`. Rows that still don't resolve keep NA."""
    out = df.copy()
    out["player_id"] = pd.array([pd.NA] * len(out), dtype="string")
    if out.empty:
        return out
    out["player_id"] = out["gsis_id"].astype("string")
    missing = out["player_id"].isna() | (out["player_id"].str.strip() == "")
    if missing.any():
        crosswalked = A.attach_gsis(con, out.loc[missing], season, schema=schema)
        out.loc[missing, "player_id"] = crosswalked["player_id"].values
    return out


def load_sleeper_injuries_with_coverage(
    con, season: int, cache_dir: "str | Path | None" = None, refresh: bool = False,
    schema: str = "main_nfl_marts", timeout: int = 30,
) -> "tuple[pd.DataFrame, dict]":
    """The ingest entry point, plus the coverage measured **BEFORE** the unresolved-row drop.

    ⭐ WHY THE PRE-DROP MEASUREMENT EXISTS (NF-INFRA1). `load_sleeper_injuries` drops rows that
    never resolve a `player_id`, so `coverage()` on its OUTPUT reports `pct_matched = 100.0` **by
    construction** — it cannot distinguish a healthy crosswalk from a collapsed one. That is not a
    hypothetical blind spot: NF-FRESH1 measured that Sleeper's own NATIVE `gsis_id` covers only
    16.7% of rostered players and 22.1% of FLAGGED ones, so a run whose crosswalk source is
    missing still lands a plausible-looking, 100%-matched frame that has silently DROPPED 95 of
    122 flagged players (Waddle, Pacheco among them) — strictly worse than an unambiguous break,
    because it overwrites the good Delta partition and reports SUCCESS.

    So the ratio that matters is `n_resolved / n_fetched`, and it is only observable here.
    Returns `(landing_frame, coverage)`; feed the coverage to `classify_land` and DO NOT WRITE
    unless it says so.
    """
    fetched = fetch_sleeper_players(cache_dir=cache_dir, refresh=refresh, timeout=timeout)
    n_fetched = int(len(fetched))
    if n_fetched:
        native = fetched["gsis_id"].notna() & (fetched["gsis_id"].astype(str).str.strip() != "")
    else:
        native = pd.Series([], dtype=bool)

    df = attach_gsis(con, fetched, season, schema=schema)
    resolved = (df["player_id"].notna() & (df["player_id"].astype(str).str.strip() != "")
                if n_fetched else pd.Series([], dtype=bool))
    landed = df.loc[resolved].copy() if n_fetched else df.copy()
    landed["season"] = int(season)
    landed["ingested_at"] = datetime.now(timezone.utc).isoformat()
    landed = landed.reindex(columns=_ASSET_COLS).reset_index(drop=True)

    n_resolved = int(len(landed))
    cov = {
        "n_fetched": n_fetched,
        "n_resolved": n_resolved,
        "pct_resolved": round(100.0 * n_resolved / n_fetched, 1) if n_fetched else 0.0,
        # The crosswalk's own contribution — the quantity that goes to ~0 when the sports DuckDB
        # or `fct_player_week` is unavailable, which is precisely the degradation to refuse.
        "n_native_gsis": int((native & resolved).sum()) if n_fetched else 0,
        "n_crosswalk_resolved": int((~native & resolved).sum()) if n_fetched else 0,
        "n_flagged": int(landed["proj_status"].notna().sum()) if n_resolved else 0,
        "by_injury_status": ({k: int(v) for k, v in
                              landed["injury_status"].value_counts(dropna=True).items()}
                             if n_resolved else {}),
    }
    return landed, cov


def load_sleeper_injuries(
    con, season: int, cache_dir: "str | Path | None" = None, refresh: bool = False,
    schema: str = "main_nfl_marts",
) -> pd.DataFrame:
    """Ingest entry point: fetch Sleeper's player feed, resolve `player_id` (native gsis_id + the
    deterministic name/pos fallback), stamp `season`/`ingested_at`. Rows that never resolve a
    `player_id` are dropped (nothing for the lake/projection join to use). Returns the
    `run_sleeper_injuries_ingest.py` landing frame (`_ASSET_COLS`).

    Thin wrapper over `load_sleeper_injuries_with_coverage` — prefer that one for anything that
    WRITES, so the land can be gated on `classify_land` (see its docstring)."""
    landed, _ = load_sleeper_injuries_with_coverage(
        con, season, cache_dir=cache_dir, refresh=refresh, schema=schema)
    return landed


# ── The land verdict (PURE — no IO, unit-tested offline) ────────────────────────────────────
# The resolution rate separates two REGIMES, and the floor is set from those regimes rather than
# reverse-engineered from a run's answer (the NF1.8 rule). ⭐ BOTH ARE NOW MEASURED — on the first
# healthy land after NF-INFRA1 (box, 2026-08-15, season 2026, 4,038 fetched):
#   * crosswalk WORKING  — n_resolved/n_fetched = 2,501/4,038 = 61.9%; the crosswalk roughly DOUBLES
#                          resolution (1,259 native → 2,501 total), and 2,501 landed rows matches
#                          the last-known-good 2,499 of 2026-07-26.
#   * crosswalk ABSENT   — only Sleeper's own native `gsis_id` resolves: 1,259/4,038 = 31.2%.
# ⚠️ NF-FRESH1's "16.7% of rostered / 22.1% of flagged" is a DIFFERENT DENOMINATOR (of rostered /
# of flagged players, not of fetched rows) and must not be compared to this ratio directly. The
# figure that binds here is 31.2%.
# ⚠️ AND THE MARGIN IS ~12pp ON THE HEALTHY SIDE, NOT "wide": an earlier version of this comment
# put the working regime at ~89-100%, which was the POST-DROP rate — i.e. the statistic
# `load_sleeper_injuries_with_coverage` exists to replace, since it is 100% by construction. Do not
# re-derive this floor from `coverage()` on a landed frame.
# ⇒ 50% stays: it refuses a native-only land (31.2%) and admits the observed healthy rate (61.9%).
# It should NOT be tightened toward 61.9 on this single observation — one measurement cannot bound
# the seasonal variation in how many non-rostered players Sleeper's feed carries (the denominator
# moves), and a floor that false-refuses is strictly worse than one that is generous. Revisit with
# several months of the `pct_resolved` this now logs every run.
DEFAULT_MIN_PCT_RESOLVED = 50.0

# `n_flagged == 0` is suspicious, not impossible — Sleeper legitimately carries no long-absence
# designations at some points in the calendar. It WARNs and still lands (the magnitude is in the
# log), because refusing the write there would discard a real snapshot on a survivable signal.


def classify_land(coverage: dict, min_pct_resolved: float = DEFAULT_MIN_PCT_RESOLVED) -> dict:
    """PURE — decide whether a fetched Sleeper snapshot may be written, from `coverage`.

    ⛔ A run that produced nothing must be RED, never a green run over a stale artifact
    (NF-FRESH1). ⛔ And a DEGRADED run must not write at all: the Delta write is a whole-partition
    overwrite, so landing a crosswalk-less frame destroys the good snapshot and looks healthy.

    Returns `{verdict, should_write, severity, reason}` where `severity is None` means healthy.
    """
    n_fetched = int(coverage.get("n_fetched", 0) or 0)
    n_resolved = int(coverage.get("n_resolved", 0) or 0)
    pct = float(coverage.get("pct_resolved", 0.0) or 0.0)
    n_flagged = int(coverage.get("n_flagged", 0) or 0)

    if n_fetched <= 0:
        return {"verdict": "EMPTY_FEED", "should_write": False, "severity": "CRITICAL",
                "reason": ("Sleeper's v1/players/nfl returned ZERO skill-position players. That is "
                           "an upstream outage or a changed payload shape, never a quiet day — the "
                           "previous Delta commit is left untouched.")}
    if n_resolved <= 0:
        return {"verdict": "CROSSWALK_DEGRADED", "should_write": False, "severity": "CRITICAL",
                "reason": (f"fetched {n_fetched} players and resolved a player_id for NONE of them. "
                           "The (name, position) crosswalk off `fct_player_week` is unavailable — "
                           "check the sports DuckDB and that the NFL marts are built.")}
    if pct < float(min_pct_resolved):
        return {"verdict": "CROSSWALK_DEGRADED", "should_write": False, "severity": "CRITICAL",
                "reason": (f"only {n_resolved}/{n_fetched} ({pct}%) of fetched players resolved a "
                           f"player_id, under the {min_pct_resolved}% floor "
                           f"(native gsis {coverage.get('n_native_gsis')}, crosswalk "
                           f"{coverage.get('n_crosswalk_resolved')}). Landing this would OVERWRITE "
                           "the good partition with a frame missing most flagged players while "
                           "reporting success — refusing the write instead.")}
    if n_flagged <= 0:
        return {"verdict": "PARTIAL", "should_write": True, "severity": "WARN",
                "reason": (f"landed {n_resolved}/{n_fetched} ({pct}%) players but ZERO carry a "
                           "long-absence designation (PUP/RES/NFI/SUS). Possible upstream vocabulary "
                           "change; the snapshot is still written.")}
    return {"verdict": "OK", "should_write": True, "severity": None,
            "reason": (f"landed {n_resolved}/{n_fetched} ({pct}%) players, {n_flagged} flagged "
                       f"(native gsis {coverage.get('n_native_gsis')}, crosswalk "
                       f"{coverage.get('n_crosswalk_resolved')}).")}


def coverage(df: pd.DataFrame) -> dict:
    """Quick match/flag diagnostics for a crosswalked frame (for logs / the ingest report)."""
    n = len(df)
    matched = int(df["player_id"].notna().sum()) if "player_id" in df else 0
    flagged = int(df["proj_status"].notna().sum()) if "proj_status" in df else 0
    by_status = ({k: int(v) for k, v in df["injury_status"].value_counts(dropna=True).items()}
                 if "injury_status" in df and n else {})
    return {
        "n_rows": int(n), "n_matched": matched,
        "pct_matched": round(100.0 * matched / max(1, n), 1),
        "n_flagged": flagged, "by_injury_status": by_status,
    }
