"""NF-FRESH2 P1 — the market-refresh CORRECTNESS BOUNDARY and the per-input as-of stamps.

Two jobs, both small, both load-bearing:

1. `should_refresh_market(season, market_refresh)` — the ONE place that decides whether a build is
   allowed to re-fetch ADP/ECR from the network. **It refuses for any season that is not the
   clock-derived `current_season()`, no matter what the caller passes.**

   ⭐ THIS IS A CORRECTNESS BOUNDARY, NOT AN OPTIMISATION (the E5.9 backfill boundary). Historical
   seasons (2019–2024) MUST keep reading their pinned market snapshot: the NF-D3 scorecard and the
   published track record grade our past projections against *the ADP that existed at the time*.
   If a refresh reached 2019–2024, every historical benchmark would silently be regraded against a
   market that did not exist when the projection was made — a hindsight benchmark, which is exactly
   the boundary `export_track_record_json.py::_CLAIM_DENYLIST` exists to defend. Putting the season
   test INSIDE the helper (rather than at each call site) means a caller that threads
   `market_refresh=True` through a whole 2017→2026 training pool still cannot refresh a historical
   season — the boundary is structural, not a convention every future caller has to remember.

2. `adp_as_of()` / `ecr_as_of()` — read the market's OWN as-of stamp out of the on-disk cache the
   build just consumed (FFC's `meta.end_date`, FantasyPros' `last_updated_ts`), so the served
   payload can carry a per-input vintage.

   ⭐ WHY PER-INPUT STAMPS EXIST (NF-FRESH1 §1.2, an honest-framing defect): the UI renders one
   `built <date>` over a row whose inputs have THREE different vintages — on 2026-08-10 the board
   showed "built 8/10" beside an ADP column from 7/25. A staleness figure must be VISIBLE, never
   inferable from a build date that is true of one column and false of the one beside it.

   ⛔ These NEVER reach the network. They read the cache file only, so calling one can neither
   trigger a second fetch nor change what the build consumed — it reports the vintage, it does not
   choose it. A missing/unparseable cache returns `None`, which the payload ships as `null` and the
   UI renders as "unknown" — an unevaluable stamp is never rendered as fresh (NF1.7(a)).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from quant_sports_intel_models.football.nfl.ingest.sources import current_season

log = logging.getLogger(__name__)

_ADP_CACHE = Path(__file__).resolve().parent / "artifacts" / "adp_cache"
_ECR_CACHE = Path(__file__).resolve().parent / "artifacts" / "ecr_cache"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The correctness boundary
# ══════════════════════════════════════════════════════════════════════════════════════════════
def should_refresh_market(season: int, market_refresh: bool, today: date | None = None) -> bool:
    """True only when the caller asked for a refresh AND `season` is the CURRENT season.

    A historical season always reads its pinned cache — see the module docstring for why that is a
    correctness boundary rather than a performance choice.

    ⚠️ THIS GOVERNS RE-FETCHING, NOT COLD-STARTING, and the difference is deliberate. With NO cache
    on disk the fetchers still go to the network for a historical season — that is the only way a
    first-ever backtest of 2019–2024 can obtain its market at all, and it is not a hindsight
    problem: FFC serves a PAST season's ARCHIVED preseason window (verified live 2026-08-15 — 2021
    returns `2021-08-31 → 2021-09-01`, 1,709 drafts, not today's re-rank). What the boundary
    forbids is OVERWRITING a snapshot a scored benchmark was already graded against. Measured on
    the same run: a 2021 build with the flag ON left the pinned 2021-09-01 snapshot byte-identical."""
    if not market_refresh:
        return False
    return int(season) == current_season(today)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-input as-of stamps (cache reads only — never the network)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _read_json(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else None
    except Exception as e:  # noqa: BLE001 — an unreadable cache is "unknown vintage", never a crash
        log.warning("market as-of: could not read %s (%s: %s)", path.name, type(e).__name__, e)
        return None


def adp_as_of(season: int, fmt: str = "ppr", teams: int = 12,
              cache_dir: str | Path | None = None) -> dict | None:
    """`{source, format, teams, as_of, window_start, window_end, drafts}` for the FFC ADP snapshot
    currently on disk for (season, fmt, teams) — or None when there is no usable cache.

    `as_of` is FFC's `meta.end_date`: the LAST day of the rolling draft window the ADP averages,
    i.e. the newest real information in the number. (`start_date` ships too, because "an average
    over 7 days ending 8/14" and "a reading taken on 8/14" are different claims and the payload
    should not blur them.)"""
    cache = Path(cache_dir or _ADP_CACHE) / f"ffc_{fmt}_{teams}_{season}.json"
    payload = _read_json(cache)
    if not payload or payload.get("status") != "Success":
        return None
    meta = payload.get("meta") or {}
    end = meta.get("end_date")
    if not end:
        return None
    return {
        "source": "ffc",
        "format": fmt,
        "teams": int(teams),
        "as_of": str(end),
        "window_start": str(meta.get("start_date")) if meta.get("start_date") else None,
        "window_end": str(end),
        "drafts": int(meta["total_drafts"]) if str(meta.get("total_drafts", "")).isdigit() else None,
    }


def ecr_as_of(season: int, scoring: str = "PPR",
              cache_dir: str | Path | None = None) -> dict | None:
    """`{source, scoring, as_of, label, experts}` for the FantasyPros ECR snapshot on disk.

    ⚠️ `as_of` is derived from `last_updated_ts` (an epoch), NOT from `last_updated` — FantasyPros
    ships that as a bare `"7/26"` with NO YEAR, which is ambiguous the moment it is read outside
    the season it was written in. The raw label rides along as `label` so the payload can be
    reconciled against FantasyPros' own page, but the DATE consumers sort and render is the
    unambiguous one."""
    scoring = scoring.upper()
    cache = Path(cache_dir or _ECR_CACHE) / f"fp_ecr_{scoring}_{season}.json"
    payload = _read_json(cache)
    if not payload or not payload.get("players"):
        return None
    ts = payload.get("last_updated_ts")
    as_of = None
    try:
        if ts is not None:
            as_of = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except Exception:  # noqa: BLE001 — a malformed stamp is "unknown vintage", never a crash
        as_of = None
    if as_of is None:
        return None
    experts = payload.get("total_experts")
    return {
        "source": "fantasypros",
        "scoring": scoring,
        "as_of": as_of,
        "label": str(payload.get("last_updated")) if payload.get("last_updated") else None,
        "experts": int(experts) if str(experts or "").isdigit() else None,
    }


def market_as_of(season: int, fmt: str = "ppr", teams: int = 12, scoring: str = "PPR",
                 adp_cache_dir: str | Path | None = None,
                 ecr_cache_dir: str | Path | None = None) -> dict:
    """Both stamps in one dict — `{"adp": {...}|None, "ecr": {...}|None}`.

    Always returns both KEYS (a present key with a null value says "we looked and could not tell",
    which is a different statement from the key being absent because an older exporter never wrote
    it — the NF-C0 additive-shape discipline, applied to a provenance field)."""
    return {
        "adp": adp_as_of(season, fmt=fmt, teams=teams, cache_dir=adp_cache_dir),
        "ecr": ecr_as_of(season, scoring=scoring, cache_dir=ecr_cache_dir),
    }
