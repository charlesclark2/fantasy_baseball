"""E9.40 — "who called it" scorecard: settle the model's pick and the market's
benchmark against the final result, factually.

Pure, serving-cache-sourced derivation. The input is the game-detail blob that
already lives in the serving cache (DynamoDB → S3) — `game_score` (final score)
plus the per-market `picks` rows (model_prob + de-vigged market prob + total
line). No lakehouse / Snowflake / `mart_game_results` read (the story's hard
constraint — those marts may be mid-migration).

Win-semantics mirror the performance page (E9.26) exactly so "correct" means the
same thing everywhere:

  * The model's directional pick = the side its probability favors:
    `model_prob >= 0.5` → home / over, else away / under. One pick per game,
    per market. (We deliberately use `model_prob`, not the Layer-4 `pick_side`,
    so the call is always defined even when the served pick abstains — the same
    convention the performance win-rate uses.)
  * A pick "wins" if that side matched the outcome; "push" on an exact tie.

Market benchmark (graded the same way as the model, for symmetry):
  * h2h: the market's pick = the closing **favorite** (de-vigged implied
    prob >= 0.5). It wins if the favorite won — a genuine, gradable market call.
  * totals: the market's lean = the de-vigged consensus over/under side
    (P(over) >= 0.5 → over). Books balance a total to ~50/50, so this lean is
    near-neutral — we always surface its implied % alongside the result so the
    reader sees that, and we also report the plain facts (closing line, final
    combined total, which way it landed).

Framing is factual only: a model miss is reported as plainly as a hit. No
+EV / edge / win-rate / profit language (honest-framing guardrail).
"""

from __future__ import annotations

from app.backend.models.picks import (
    GameScorecard,
    MarketRecord,
    MarketRecordPair,
    MarketScorecard,
    ScorecardSummary,
)

# E9.26 — the pick/grade rules live in ONE canonical module so the scorecard, the
# performance page and every other surface mean the same thing by "correct".
from app.backend.services.metric_semantics import (
    SMALL_SAMPLE_N,
    aggregate_scorecard_records,
    grade_h2h as _grade_h2h,
    grade_totals as _grade_totals,
    oriented_prob as _oriented_prob,
    pick_side as _model_side,
    totals_landed as _totals_landed,
)


def _market_scorecard(
    market_type: str,
    model_prob: float | None,
    market_prob: float | None,
    home_score: int,
    away_score: int,
    total_line: float | None,
) -> MarketScorecard | None:
    """Grade one market for a Final game, or None if it isn't a market we score."""
    if market_type == "h2h":
        model_side = _model_side("h2h", model_prob)
        market_side = _model_side("h2h", market_prob)  # >= 0.5 P(home) → home favorite
        return MarketScorecard(
            market_type="h2h",
            model_side=model_side,
            model_result=_grade_h2h(model_side, home_score, away_score),
            model_prob=_oriented_prob(model_prob, model_side),
            market_side=market_side,
            market_result=_grade_h2h(market_side, home_score, away_score),
            market_prob=_oriented_prob(market_prob, market_side),
        )
    if market_type == "totals":
        final_total = home_score + away_score
        model_side = _model_side("totals", model_prob)
        market_side = _model_side("totals", market_prob)  # de-vig P(over) >= 0.5 → over lean
        landed = _totals_landed(final_total, total_line)
        return MarketScorecard(
            market_type="totals",
            model_side=model_side,
            model_result=_grade_totals(model_side, landed),
            model_prob=_oriented_prob(model_prob, model_side),
            market_side=market_side,
            market_result=_grade_totals(market_side, landed),
            market_prob=_oriented_prob(market_prob, market_side),
            total_line=total_line,
            final_total=final_total,
            landed=landed,
        )
    return None


def build_scorecard_from_detail(detail: dict, game_pk: int | None = None) -> GameScorecard | None:
    """Build a GameScorecard from a game-detail blob, or None if the game isn't Final.

    `detail` is the exact serving-cache game-detail shape (a GameDetailResponse
    dump): `game_score` (status/home_score/away_score), `picks` (per-market rows
    with model_prob / bovada_devig_prob / market_total_line), and the top-level
    team names. Only Final games with both scores produce a scorecard.
    """
    gs = detail.get("game_score") or {}
    if str(gs.get("status") or "") != "Final":
        return None
    home_score = gs.get("home_score")
    away_score = gs.get("away_score")
    if home_score is None or away_score is None:
        return None
    try:
        home_score = int(home_score)
        away_score = int(away_score)
    except (TypeError, ValueError):
        return None

    picks = detail.get("picks") or []
    markets: list[MarketScorecard] = []
    resolved_pk = game_pk
    game_date = None
    home_team = away_team = None
    # Dedup to one row per market_type (the served blob is already latest-inserted_at,
    # but guard against duplicates so a market is never double-graded).
    seen: set[str] = set()
    for p in picks:
        mt = p.get("market_type")
        if not mt or mt in seen:
            continue
        seen.add(mt)
        resolved_pk = resolved_pk or p.get("game_pk")
        game_date = game_date or p.get("game_date")
        home_team = home_team or p.get("home_team")
        away_team = away_team or p.get("away_team")
        ms = _market_scorecard(
            mt,
            p.get("model_prob"),
            p.get("bovada_devig_prob"),
            home_score,
            away_score,
            p.get("market_total_line"),
        )
        if ms is not None:
            markets.append(ms)

    if not markets:
        return None

    # Stable market order: h2h before totals.
    markets.sort(key=lambda m: 0 if m.market_type == "h2h" else 1)

    return GameScorecard(
        game_pk=resolved_pk,
        game_date=str(game_date) if game_date is not None else None,
        home_team=home_team,
        away_team=away_team,
        home_team_name=detail.get("home_team_name"),
        away_team_name=detail.get("away_team_name"),
        home_score=home_score,
        away_score=away_score,
        status="Final",
        markets=markets,
    )


def build_scorecard_summary(scorecards: list[GameScorecard]) -> ScorecardSummary:
    """Canonical per-market tally over a slate's graded scorecards (E9.26).

    The ONE definition — computed server-side from the same graded markets the
    per-game cards show — so the Results header can render a single trusted count
    instead of re-tallying client-side. Per market, pushes excluded, never combined.
    """
    finals = [s for s in scorecards if s and s.status == "Final" and s.markets]
    agg = aggregate_scorecard_records(finals)
    pairs = [
        MarketRecordPair(
            market_type=mt,
            n_games=rec["n_games"],
            model=MarketRecord(**rec["model"]),
            market=MarketRecord(**rec["market"]),
        )
        for mt, rec in agg.items()
    ]
    return ScorecardSummary(
        n_games=len(finals),
        small_sample_n=SMALL_SAMPLE_N,
        markets=pairs,
    )
