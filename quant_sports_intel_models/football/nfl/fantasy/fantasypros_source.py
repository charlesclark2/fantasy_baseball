"""fantasypros_source.py — NF-D3: FantasyPros Expert Consensus Rankings (ECR) benchmark.

The SECOND competitor-projection benchmark (after ADP, NF-D2 #6). FantasyPros ECR is the aggregate
of 80–240 human experts' preseason draft rankings — the single most-cited public fantasy consensus.
It is a RANKING system (not a point projection), so it grades apples-to-apples with us on ORDERING
(within-position Spearman ρ + rank-MAE), the metric that actually wins drafts.

⭐ WHY IT CLEARS THE HONESTY BAR (the leakage cardinal sin):
  FantasyPros archives the FINAL PRESEASON consensus per year at a public partners JSON endpoint.
  Every historical year's `last_updated` lands in early September of THAT year (2019 → 9/08, 2024 →
  9/06, …) — i.e. the ranking is FROZEN right before Week 1, before any of that season's games are
  played ⇒ LEAKAGE-SAFE as a forward signal for the projection season. And each year returns its OWN
  era's #1 (2019 Saquon Barkley, 2024 CMC, 2025 Ja'Marr Chase — the real preseason consensus of that
  year), NOT today's re-rank, which is the tell that these are archived snapshots and not live data.

⭐ COVERAGE ADVANTAGE OVER ADP: 2019–2026 inclusive — including **2025**, the one season FFC ADP is
  missing. So ECR is the benchmark that lets the scorecard grade a 2025 holdout.

Endpoint (public, no key):
  https://partners.fantasypros.com/api/v1/consensus-rankings.php?sport=NFL&year=Y&position=ALL&scoring=PPR&type=draft
Fields used: `rank_ecr` (the consensus rank, lower=better), `rank_ave`/`rank_std`/`rank_min`/`rank_max`
(the expert dispersion), `pos_rank` (e.g. "RB1"), `player_position_id`, `player_name`, `player_team_id`.

Public API (mirrors `adp_source`):
  fetch_fp_ecr(season, scoring, cache_dir)  -> normalized ECR DataFrame
  attach_gsis(con, ecr_df, season)          -> ECR ⋈ our gsis `player_id` (reuses `adp_source`'s
                                               season-accurate (normalized-name, position) crosswalk)
  load_ecr_for_season(con, season, ...)      -> fetch + crosswalk in one call (consumer entry point)

Dependency-light (urllib + pandas). The network fetch caches the raw JSON so a run is reproducible
offline once primed. The lake-landing CLI is `run_ecr_ingest.py`; the standing scorecard
(`benchmark_scorecard.py`) calls these helpers directly.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

import pandas as pd

# Reuse the ADP crosswalk verbatim — the (normalized-name, position) → gsis join is source-agnostic,
# and sharing it keeps ONE crosswalk to maintain (and one alias map) across every benchmark system.
from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

log = logging.getLogger("nfl.fantasy.ecr")

_FP_URL = ("https://partners.fantasypros.com/api/v1/consensus-rankings.php"
           "?sport=NFL&year={season}&position=ALL&scoring={scoring}&type=draft")
_DEFAULT_CACHE = Path(__file__).resolve().parent / "artifacts" / "ecr_cache"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

# The skill positions the projection product covers (FP also ranks K/DST — kept in the raw asset,
# excluded from the gsis crosswalk since we do not project them). Mirrors `adp_source._SKILL`.
_SKILL = ("QB", "RB", "WR", "TE")
_POS_FIX = {"PK": "K", "DST": "DEF", "D/ST": "DEF"}

_COLS = ["season", "source", "scoring", "player_name", "position", "team",
         "rank_ecr", "rank_ave", "rank_std", "rank_min", "rank_max", "pos_rank",
         "tier", "total_experts", "last_updated"]


def _read_cached_payload(cache: Path) -> dict | None:
    """The cache file, or None when it is absent/corrupt (a corrupt cache just re-fetches)."""
    if not cache.exists():
        return None
    try:
        return json.loads(cache.read_text())
    except Exception:  # noqa: BLE001
        return None


def _fp_payload(season: int, *, scoring: str, cache_dir: str | Path | None,
                refresh: bool, timeout: int) -> dict | None:
    """The raw FantasyPros payload: cache-first, or network-first when `refresh` is set.

    ⭐ NF-FRESH2 P1 — like `adp_source._ffc_payload`, A FAILED REFRESH FALLS BACK TO THE CACHE,
    LOUDLY, rather than degrading the season to market-blind. ECR feeds the served RANKING (the
    market-led/market-blend lean, NF-FRESH1 §2.3), so a transient FantasyPros outage must not be
    able to reorder the board. The `ecr_as_of` stamp is read from the same cache file, so a bound
    fallback ships the OLD date — the fallback announces itself instead of hiding."""
    scoring = scoring.upper()
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"fp_ecr_{scoring}_{season}.json"

    if not refresh:
        cached = _read_cached_payload(cache)
        if cached is not None:
            return cached

    url = _FP_URL.format(season=season, scoring=scoring)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            payload = json.loads(resp.read().decode())
    except Exception as e:  # noqa: BLE001
        cached = _read_cached_payload(cache) if refresh else None
        if cached is not None:
            log.warning("⚠️ FantasyPros ECR %s %s REFRESH FAILED (%s: %s) — falling back to the "
                        "cached snapshot (last_updated %s). The served ecr_as_of stamp will show "
                        "that older date.", season, scoring, type(e).__name__, e,
                        cached.get("last_updated"))
            return cached
        raise

    # Only cache a payload that actually carries rankings — an empty/error body must not be able to
    # persist as "no data" (the NF-D16 lesson `adp_source` already carries).
    if (payload or {}).get("players"):
        cache.write_text(json.dumps(payload))
        return payload

    log.warning("FantasyPros ECR %s %s: NOT caching a payload with no players — the next run will "
                "re-fetch", season, scoring)
    if refresh:
        cached = _read_cached_payload(cache)
        if cached is not None and cached.get("players"):
            log.warning("⚠️ FantasyPros ECR %s %s refresh returned no players — falling back to the "
                        "cached snapshot (last_updated %s).", season, scoring,
                        cached.get("last_updated"))
            return cached
    return payload


def fetch_fp_ecr(
    season: int, scoring: str = "PPR", cache_dir: str | Path | None = None,
    refresh: bool = False, timeout: int = 30,
) -> pd.DataFrame:
    """Fetch + normalize one season of FantasyPros ECR (draft, preseason snapshot). Returns one row
    per ranked player with `season, source, scoring, player_name, position, team, rank_ecr, rank_ave,
    rank_std, rank_min, rank_max, pos_rank, tier, total_experts, last_updated`. Empty DataFrame (with
    the columns) when FP has no data for the season. Caches the raw JSON so subsequent runs are
    offline-reproducible."""
    scoring = scoring.upper()  # the `scoring` COLUMN below must stay canonical, not caller-cased
    payload = _fp_payload(season, scoring=scoring, cache_dir=cache_dir, refresh=refresh,
                          timeout=timeout)

    players = (payload or {}).get("players")
    if not players:
        log.warning("FantasyPros ECR %s %s: no data", season, scoring)
        return pd.DataFrame(columns=_COLS)

    experts = pd.to_numeric((payload or {}).get("total_experts"), errors="coerce")
    updated = (payload or {}).get("last_updated")
    rows = []
    for p in players:
        raw_pos = (p.get("player_position_id") or p.get("player_positions") or "").upper()
        pos = _POS_FIX.get(raw_pos, raw_pos)
        rows.append({
            "season": int(season), "source": "fantasypros", "scoring": scoring,
            "player_name": p.get("player_name"), "position": pos, "team": p.get("player_team_id"),
            "rank_ecr": pd.to_numeric(p.get("rank_ecr"), errors="coerce"),
            "rank_ave": pd.to_numeric(p.get("rank_ave"), errors="coerce"),
            "rank_std": pd.to_numeric(p.get("rank_std"), errors="coerce"),
            "rank_min": pd.to_numeric(p.get("rank_min"), errors="coerce"),
            "rank_max": pd.to_numeric(p.get("rank_max"), errors="coerce"),
            "pos_rank": p.get("pos_rank"), "tier": pd.to_numeric(p.get("tier"), errors="coerce"),
            "total_experts": experts, "last_updated": updated,
        })
    return pd.DataFrame(rows, columns=_COLS)


def attach_gsis(con, ecr_df: pd.DataFrame, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Add our gsis `player_id` to an ECR frame via the SHARED `adp_source` (normalized-name, position)
    crosswalk off `fct_player_week`. Skill positions only; unmatched / non-skill rows get NA. Returns
    ecr_df + `player_id`."""
    return A.attach_gsis(con, ecr_df, season, schema=schema)


def load_ecr_for_season(
    con, season: int, scoring: str = "PPR", cache_dir: str | Path | None = None,
    refresh: bool = False, schema: str = "main_nfl_marts",
) -> pd.DataFrame:
    """Consumer entry point: fetch FantasyPros ECR for `season` + crosswalk to our gsis `player_id`.
    Returns the normalized ECR frame + `player_id` (NA where unmatched / non-skill). Empty when FP has
    no data for the season."""
    ecr = fetch_fp_ecr(season, scoring=scoring, cache_dir=cache_dir, refresh=refresh)
    return attach_gsis(con, ecr, season, schema=schema)


def coverage(ecr_df: pd.DataFrame) -> dict:
    """Match diagnostics for a crosswalked ECR frame (for logs / the ingest report)."""
    skill = ecr_df[ecr_df["position"].isin(_SKILL)]
    matched = skill["player_id"].notna().sum() if "player_id" in skill else 0
    return {
        "n_rows": int(len(ecr_df)),
        "n_skill": int(len(skill)),
        "n_matched": int(matched),
        "pct_matched": round(100.0 * matched / max(1, len(skill)), 1),
        "by_position": {k: int(v) for k, v in ecr_df.groupby("position").size().items()},
    }
