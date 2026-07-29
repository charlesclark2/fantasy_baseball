"""prospect_savant.py — MLB Edge-E8.0: the OPTIONAL third view (Prospect Savant expected stats).

**Their** MiLB-Statcast expected stats, from the "Minor League Savant" JSON API. Fetched as a
ONE-TIME SNAPSHOT for the 8/3 draft board, cached to disk, and merged in under an explicit `ps_`
prefix so nothing on the board can mistake their derived stat for ours.

🚦 THIS IS AN UNOFFICIAL HOBBYIST ENDPOINT (PythonAnywhere). Treat it accordingly:
  * **Opt-in only** (`--prospect-savant`), never on a scheduled/serving path, never a HALT.
  * **Cached** — the snapshot lands on disk and re-runs read the cache; the network is touched once.
  * **Polite** — a descriptive User-Agent, a serial fetch with a delay between calls, 8 requests
    total for a whole board.
  * **Display input ONLY.** There is no as-of history here, so it can never be an E7.8 backtest
    feature — a today-snapshot joined to a past board season is look-ahead by construction.
  * A failure is a WARNING and an absent column, never a failed board. The draft does not wait on
    a hobby API.

📡 THE ROUTE SHAPE — PROBED LIVE, NOT READ OFF A DOC (2026-07-27; the E7.2 don't-code-to-docs rule):

    /leaders/{hitters|pitchers}/{level}/{season}/{min_pitches}/{age_min}/{age_max}

  verified by varying each param and re-reading the response:
    * `hitters` / `pitchers` — `batters` and `batter` both 404.
    * level ∈ {AAA, AA, A+, A}; `CPX` returns an EMPTY list (no Statcast below full-season ball —
      the same coverage wall E7.2 hit), so the complex/DSL half of the board is out of reach here.
    * param 5 = a MIN-WORKLOAD floor in PITCHES: 100 → smallest returned TBF 24, 25 → smallest 4.
    * params 6/7 = an inclusive AGE window: `.../22/24` returned exactly ages 22–24.
  The payload is `{"data": [...]}` with ~162 fields per player, including **`MinorMasterId`** (the
  FanGraphs minor-master id = our `fg_minor_id`) and `MLBAMId` — so the join is DETERMINISTIC on a
  vendor-published id pair, with no name matching anywhere (E7.4 landmine 4).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

log = logging.getLogger("e8_0.prospect_savant")

BASE_URL = "https://oriolebird.pythonanywhere.com/leaders"
# Only the levels the endpoint actually serves — CPX/DSL come back empty (probed).
LEVELS: tuple[str, ...] = ("AAA", "AA", "A+", "A")
PLAYER_TYPES: tuple[str, ...] = ("hitters", "pitchers")
DEFAULT_MIN_PITCHES = 100
DEFAULT_AGE_MIN, DEFAULT_AGE_MAX = 16, 30
REQUEST_DELAY_SECONDS = 2.0
USER_AGENT = ("credence-prospect-board/1.0 (one-time dynasty draft snapshot; "
              "contact via github issue)")

# THEIR field -> OUR column. Prefixed `ps_` without exception: on a board that already shows a
# FanGraphs grade and our own MLE, an unprefixed `xwoba` is a provenance bug waiting to be quoted
# as ours.
_HITTER_FIELDS = {
    "xwoba": "ps_xwoba", "xwoba_p": "ps_xwoba_pctile", "ev": "ps_ev",
    "barrelpa": "ps_barrel_pct", "hhrate": "ps_hardhit_pct", "chaserate": "ps_chase_pct",
    "whiffrate": "ps_whiff_pct", "krate": "ps_k_pct", "bbrate": "ps_bb_pct",
    "gbrate": "ps_gb_pct", "pa": "ps_pa",
}
_PITCHER_FIELDS = {
    "xwoba": "ps_xwoba", "xwoba_p": "ps_xwoba_pctile", "velo": "ps_velo", "xfip": "ps_xfip",
    "whiffrate": "ps_whiff_pct", "chaserate": "ps_chase_pct", "krate": "ps_k_pct",
    "bbrate": "ps_bb_pct", "gbrate": "ps_gb_pct", "ev": "ps_ev", "hhrate": "ps_hardhit_pct",
    "tbf": "ps_pa",
}
# `bat_speed` is deliberately NOT mapped: it comes back 0.0 for every player at every level,
# including AAA — the MiLB feed does not carry it. An all-zero column on a draft board is worse
# than no column.

# 🚨 THE FEED ENCODES "NOT TRACKED AT THIS LEVEL" AS THE NUMBER 0, NOT AS NULL.
# Below Triple-A there is no Hawk-Eye batted-ball tracking (the same coverage wall E7.2 hit), and
# the payload fills those fields with 0.0 rather than omitting them: every AA pitcher row carries
# `xwoba = 0.0`, `ev = 0.0`, `velo = 0.0`, `hhrate = 0.0`. Shipped verbatim that reads as a
# PERFECT expected-wOBA-against on a draft board — a sentinel silently rendered as an elite grade.
# So a 0 in any of these physically-impossible-at-zero fields becomes NULL, and the tracking-gated
# group is nulled TOGETHER (keyed on `ev`, the tell) so a lone surviving 0 can't imply the rest.
_ZERO_IS_MISSING = ("ps_xwoba", "ps_xwoba_pctile", "ps_ev", "ps_velo", "ps_hardhit_pct")
_BATTED_BALL_GROUP = ("ps_xwoba", "ps_xwoba_pctile", "ps_ev", "ps_barrel_pct", "ps_hardhit_pct")


def _blank_untracked(rec: dict[str, Any]) -> dict[str, Any]:
    """Turn the feed's 0-as-missing sentinels into real NULLs. See `_ZERO_IS_MISSING` above."""
    # `ev == 0` is the tell that the level has no batted-ball tracking at all. Gated on the value
    # actually BEING zero, not on it being absent — a payload that simply omits `ev` says nothing
    # about whether the other fields were measured.
    untracked_level = rec.get("ps_ev") == 0
    for col in _ZERO_IS_MISSING:
        if rec.get(col) == 0:
            rec[col] = None
    if untracked_level:
        for col in _BATTED_BALL_GROUP:
            rec[col] = None
    return rec


class ProspectSavantError(RuntimeError):
    """Raised only by `probe()`; the board path degrades to a warning instead."""


def leaders_url(player_type: str, level: str, season: int, *,
                min_pitches: int = DEFAULT_MIN_PITCHES,
                age_min: int = DEFAULT_AGE_MIN, age_max: int = DEFAULT_AGE_MAX) -> str:
    if player_type not in PLAYER_TYPES:
        raise ProspectSavantError(
            f"player_type must be one of {PLAYER_TYPES} — the endpoint 404s on anything else "
            "(`batters` and `batter` were both probed and both 404)."
        )
    return (f"{BASE_URL}/{player_type}/{level}/{int(season)}/{int(min_pitches)}"
            f"/{int(age_min)}/{int(age_max)}")


def _cache_path(cache_dir: Path, player_type: str, level: str, season: int) -> Path:
    return cache_dir / f"ps_{player_type}_{level.replace('+', 'plus')}_{season}.json"


def _fetch_json(url: str, timeout: float = 60.0) -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
        return json.loads(resp.read().decode("utf-8"))


def normalize_rows(rows: Iterable[dict], player_type: str, level: str) -> pd.DataFrame:
    """Their payload → the `ps_*` columns, keyed on `fg_minor_id` (their `MinorMasterId`).

    Rows without a `MinorMasterId` are dropped: without the vendor id pair there is no deterministic
    join, and a name join is exactly the false-positive leg E7.4 refused.
    """
    fields = _HITTER_FIELDS if player_type == "hitters" else _PITCHER_FIELDS
    out = []
    for r in rows:
        minor_id = r.get("MinorMasterId")
        if not minor_id:
            continue
        rec: dict[str, Any] = {
            "fg_minor_id": str(minor_id),
            "ps_mlbam_id": (None if r.get("MLBAMId") in (None, 0, 0.0)
                            else str(int(float(r["MLBAMId"])))),
            "ps_level": level,
            "ps_player_type": "batter" if player_type == "hitters" else "pitcher",
        }
        for src, dst in fields.items():
            rec[dst] = r.get(src)
        out.append(_blank_untracked(rec))
    return pd.DataFrame(out)


def _pick_highest_level(df: pd.DataFrame) -> pd.DataFrame:
    """One row per player: the HIGHEST level he appears at — same rule as the MLE line, so the two
    statistical views on a row describe the same stage of his career."""
    if df.empty:
        return df
    from betting_ml.scripts.prospect_board.board_assembly import level_rank

    df = df.copy()
    df["_rank"] = df["ps_level"].map(level_rank)
    df = df.sort_values(["fg_minor_id", "_rank", "ps_pa"], na_position="first")
    return df.groupby("fg_minor_id", as_index=False).tail(1).drop(columns=["_rank"])


def fetch_snapshot(season: int, cache_dir: Path, *, refresh: bool = False,
                   levels: Iterable[str] = LEVELS,
                   min_pitches: int = DEFAULT_MIN_PITCHES) -> pd.DataFrame:
    """The one-time snapshot: 8 cached GETs (2 player types × 4 levels) → one `fg_minor_id` frame.

    Any single call failing degrades that level/type to absent and logs a WARNING — the remaining
    levels still land. An entirely empty result returns an empty frame, and the board is built
    without the `ps_*` columns.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    for player_type in PLAYER_TYPES:
        for level in levels:
            path = _cache_path(cache_dir, player_type, level, season)
            payload: dict[str, Any] | None = None
            if path.exists() and not refresh:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    log.info("prospect-savant %s/%s: cache hit (%s)", player_type, level, path.name)
                except ValueError:
                    log.warning("prospect-savant cache %s is corrupt — refetching", path)
                    payload = None
            if payload is None:
                url = leaders_url(player_type, level, season, min_pitches=min_pitches)
                try:
                    payload = _fetch_json(url)
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    log.info("prospect-savant %s/%s: fetched %d rows", player_type, level,
                             len(payload.get("data", [])))
                except Exception as e:  # noqa: BLE001 — an unofficial API must never fail the board
                    log.warning("prospect-savant %s/%s FAILED (%s) — that slice is omitted; the "
                                "board still builds", player_type, level, e)
                    continue
                finally:
                    time.sleep(REQUEST_DELAY_SECONDS)   # politeness, not rate-limit avoidance
            frame = normalize_rows(payload.get("data", []), player_type, level)
            if not frame.empty:
                frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["fg_minor_id", "ps_level"])
    return _pick_highest_level(pd.concat(frames, ignore_index=True)).reset_index(drop=True)


def probe(season: int, player_type: str = "pitchers", level: str = "AAA") -> dict[str, Any]:
    """Live shape check — what the `--probe` flag runs. Raises on a dead route (this one is meant
    to be loud: a probe exists to tell you the endpoint changed)."""
    url = leaders_url(player_type, level, season)
    payload = _fetch_json(url)
    rows = payload.get("data", [])
    if not rows:
        raise ProspectSavantError(f"{url} returned no rows — the route or the level vocabulary "
                                  "changed, or that level has no Statcast coverage.")
    sample = rows[0]
    return {
        "url": url,
        "rows": len(rows),
        "has_minor_master_id": "MinorMasterId" in sample,
        "has_mlbam_id": "MLBAMId" in sample,
        "n_fields": len(sample),
        "sample_fields": sorted(sample)[:40],
    }
