"""Parlay decision-support calculator — Edge Program Story E10.1 (honest MVP).

A STATELESS calculator that tells the user the TRUTH about a parlay they build: our model's estimate
of its true combined probability (same-game legs correlation-adjusted, never the naive product) next
to the book's implied probability from the parlay price, the expected value, and a plain-language
verdict. Education / transparency — NOT a bet recommendation (that is E10.3, hard-gated behind a
proven edge we do not have; `best_alpha = 0` holds).

Endpoints:
  GET  /parlay/legs      — the leg universe for a slate (games × markets × sides that carry a served
                           model probability), read from the SERVING CACHE.
  POST /parlay/evaluate  — evaluate a user-built parlay: re-resolve each leg's model probability from
                           the serving cache, then compute combined true prob + implied + EV + verdict.

🔒 SERVING-CACHE ONLY. Per-leg model probabilities come from the DynamoDB → S3 serving cache
(`picks/today`, `pitcher_k_projection/index`) — the same blobs the picks/props pages read, deduped to
latest per game by `write_serving_store`. No `daily_model_predictions` / mart / lakehouse query, so
the calculator is insulated from the E11.20 Delta migration. No serving-store write, no dbt, no box.

🔒 HONEST FRAMING. Every response carries `best_alpha = 0`, `is_bet_recommendation = False`, and the
"most parlays are −EV after vig" disclaimer (baked in `parlay_calc`). The banned-language guard
(test_parlay_serving.py) fails the build on any +EV/value/edge/bet-rec wording here or on the frontend.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day

from app.backend.dependencies import get_user_id
from app.backend.models.parlay import ParlayEvaluateRequest
from app.backend.services import parlay_calc as pm  # pure-stdlib math (no numpy/scipy — Lambda-safe)
from app.backend.services import serving_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parlay", tags=["parlay"])

_VALID_SIDES = {
    "h2h": {"home", "away"},
    "totals": {"over", "under"},
    "strikeouts": {"over", "under"},
}


# ---------------------------------------------------------------------------
# Serving-cache lookups (DynamoDB → S3). Dedup-to-latest per (game_pk, market_type).
# ---------------------------------------------------------------------------

def _picks_blob(date: str) -> list[dict]:
    """Today's served picks for `date` (the `picks/today` blob), deduped to one row per
    (game_pk, market_type). Latest-inserted wins (the blob is already latest-written; dedup guards)."""
    blob = serving_cache.get_cache("picks/today", date) or {}
    picks = blob.get("picks") or []
    seen: dict[tuple, dict] = {}
    for p in picks:
        key = (p.get("game_pk"), p.get("market_type"))
        if key[0] is None or key[1] is None:
            continue
        seen.setdefault(key, p)  # first (already latest) wins
    return list(seen.values())


def _k_index(date: str) -> list[dict]:
    """The K-projection index rows for `date` (or the latest available). Each carries pitcher_id,
    game_pk, primary_line, model_p_over — enough for a same-game-groupable strikeouts leg."""
    payload = serving_cache.get_cache("pitcher_k_projection/index", date)
    if not payload:
        payload = serving_cache.get_cache_latest("pitcher_k_projection/index")
    return (payload or {}).get("pitchers") or []


# ---------------------------------------------------------------------------
# GET /parlay/legs — leg universe
# ---------------------------------------------------------------------------

@router.get("/legs")
def get_parlay_legs(date: str | None = None, _: str = Depends(get_user_id)) -> dict:
    """Return the selectable parlay legs for a slate — games × markets × sides that carry a served
    model probability, grouped by game so the UI can offer same-game combinations.

    Read order: DynamoDB serving cache → S3. Markets: moneyline (h2h) + total runs (totals) from
    `picks/today`; pitcher strikeouts (E5.5) from the K-projection index when a per-line prob exists.
    The user supplies each leg's book odds (they aren't in the picks cache); the leg universe just
    exposes the model probability + identity. Honest framing: best_alpha=0, is_bet_recommendation=False.
    """
    slate = date or current_game_date_iso()
    games: dict[int, dict] = {}

    def _game(game_pk: int, home: str | None, away: str | None, start_utc=None) -> dict:
        g = games.get(game_pk)
        if g is None:
            g = {
                "game_pk": game_pk,
                "home_team": home,
                "away_team": away,
                "game_start_utc": start_utc,
                "markets": [],
            }
            games[game_pk] = g
        return g

    # h2h + totals from picks/today
    for p in _picks_blob(slate):
        gp = p.get("game_pk")
        mt = p.get("market_type")
        mp = p.get("model_prob")
        if gp is None or mp is None or mt not in ("h2h", "totals"):
            continue
        g = _game(gp, p.get("home_team"), p.get("away_team"), p.get("game_start_utc"))
        if mt == "h2h":
            g["markets"].append({
                "market_type": "h2h",
                "label": "Moneyline",
                "line": None,
                "sides": [
                    {"side": "home", "team": p.get("home_team"),
                     "model_prob": round(float(mp), 4)},
                    {"side": "away", "team": p.get("away_team"),
                     "model_prob": round(1.0 - float(mp), 4)},
                ],
            })
        else:  # totals
            line = p.get("market_total_line")
            g["markets"].append({
                "market_type": "totals",
                "label": "Total Runs",
                "line": line,
                "sides": [
                    {"side": "over", "model_prob": round(float(mp), 4)},
                    {"side": "under", "model_prob": round(1.0 - float(mp), 4)},
                ],
            })

    # strikeouts (E5.5) — one leg pair per starter at the primary posted line, when a prob exists
    for row in _k_index(slate):
        gp = row.get("game_pk")
        line = row.get("primary_line")
        p_over = row.get("model_p_over")
        if gp is None or line is None or p_over is None:
            continue
        g = _game(gp, None, None, row.get("game_datetime"))
        g["markets"].append({
            "market_type": "strikeouts",
            "label": f"{row.get('full_name') or 'Pitcher'} Strikeouts",
            "pitcher_id": row.get("pitcher_id"),
            "pitcher_name": row.get("full_name"),
            "line": float(line),
            "sides": [
                {"side": "over", "model_prob": round(float(p_over), 4)},
                {"side": "under", "model_prob": round(1.0 - float(p_over), 4)},
            ],
        })

    ordered = sorted(games.values(), key=lambda g: (str(g.get("game_start_utc") or "~"), g["game_pk"]))
    return {
        "date": slate,
        "games": ordered,
        "caption": pm.CAPTION,
        "disclaimer": pm.DISCLAIMER,
        "best_alpha": 0,
        "is_bet_recommendation": False,
    }


# ---------------------------------------------------------------------------
# POST /parlay/evaluate — evaluate a user-built parlay
# ---------------------------------------------------------------------------

def _resolve_hit_prob(
    leg, picks_by_key: dict[tuple, dict], k_by_pitcher: dict[int, dict]
) -> tuple[float | None, dict]:
    """Resolve a leg's oriented hit probability from the serving cache + a display dict.

    Returns (hit_prob | None, extras) where extras carries display fields (team names, line, …).
    A leg whose model probability isn't in the cache resolves to (None, …) and is handled gracefully.
    """
    mt = leg.market_type
    side = (leg.side or "").lower()
    extras: dict = {}
    if mt in ("h2h", "totals"):
        p = picks_by_key.get((leg.game_pk, mt))
        if not p:
            return None, extras
        extras["home_team"] = p.get("home_team")
        extras["away_team"] = p.get("away_team")
        if mt == "totals":
            extras["line"] = p.get("market_total_line")
        return pm.oriented_hit_prob(mt, side, p.get("model_prob")), extras
    if mt == "strikeouts":
        row = k_by_pitcher.get(leg.pitcher_id) if leg.pitcher_id is not None else None
        if not row or row.get("model_p_over") is None:
            return None, extras
        # MVP: only the primary posted line carries a served per-line prob.
        primary = row.get("primary_line")
        extras["pitcher_name"] = row.get("full_name")
        extras["line"] = primary
        if leg.line is not None and primary is not None and float(leg.line) != float(primary):
            return None, extras  # a non-primary line has no served prob → handled gracefully
        return pm.oriented_hit_prob("strikeouts", side, row.get("model_p_over")), extras
    return None, extras


@router.post("/evaluate")
def evaluate_parlay(req: ParlayEvaluateRequest, _: str = Depends(get_user_id)) -> dict:
    """Evaluate a user-built parlay. Re-resolves each leg's MODEL probability from the serving cache
    (authoritative — a client-supplied prob is ignored), then returns the true combined probability
    (same-game legs correlation-adjusted + source-stamped), the book-implied probability + expected
    value from the parlay price, and an honest plain-language verdict.

    Cross-game price is computed from the leg odds; a same-game parlay's price must be entered
    (`parlay_odds_american`) — the book prices it with its own correlation model (E10.2 gap).
    """
    if not req.legs:
        raise HTTPException(status_code=400, detail="At least one leg is required.")
    for leg in req.legs:
        if leg.market_type not in _VALID_SIDES:
            raise HTTPException(status_code=400, detail=f"Unknown market_type: {leg.market_type!r}")
        if (leg.side or "").lower() not in _VALID_SIDES[leg.market_type]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid side {leg.side!r} for market {leg.market_type!r}",
            )

    slate = req.date or current_game_date_iso()
    picks_by_key = {(p.get("game_pk"), p.get("market_type")): p for p in _picks_blob(slate)}
    k_by_pitcher = {r.get("pitcher_id"): r for r in _k_index(slate) if r.get("pitcher_id") is not None}

    math_legs: list[dict] = []
    for leg in req.legs:
        hit_prob, extras = _resolve_hit_prob(leg, picks_by_key, k_by_pitcher)
        math_legs.append({
            "game_pk": leg.game_pk,
            "market_type": leg.market_type,
            "side": (leg.side or "").lower(),
            "hit_prob": hit_prob,
            "book_odds_american": leg.book_odds_american,
            "pitcher_id": leg.pitcher_id,
            "line": leg.line if leg.line is not None else extras.get("line"),
            "label": leg.label,
            "home_team": extras.get("home_team"),
            "away_team": extras.get("away_team"),
            "pitcher_name": extras.get("pitcher_name"),
        })

    return pm.evaluate_parlay(math_legs, user_parlay_american=req.parlay_odds_american)
