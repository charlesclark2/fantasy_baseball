from __future__ import annotations

from pydantic import BaseModel


class PerformanceSummary(BaseModel):
    total_bets: int = 0
    wins: int = 0
    win_rate: float | None = None
    mean_clv: float | None = None
    net_pnl_flat: float | None = None
    net_pnl_kelly: float | None = None
    sharpe_ratio: float | None = None
    source: str = "mart_clv_labeled_games"


class ModelBreakdown(BaseModel):
    market_type: str
    signal_group: str | None = None
    total_bets: int = 0
    wins: int = 0
    win_rate: float | None = None
    mean_clv: float | None = None
    net_pnl_flat: float | None = None


class PerformanceByModelResponse(BaseModel):
    breakdown: list[ModelBreakdown]


# ── C1: model skill metrics ───────────────────────────────────────────────────

class MarketMetrics(BaseModel):
    season: int
    market_type: str
    n_predictions: int
    brier_score: float | None = None
    avg_clv: float | None = None
    clv_positive_pct: float | None = None
    win_rate: float | None = None


class ModelMetricsResponse(BaseModel):
    season: int | None
    markets: list[MarketMetrics]


# ── C1: per-user settled bets ─────────────────────────────────────────────────

class PerformanceBet(BaseModel):
    bet_id: str
    game_pk: int
    score_date: str
    matchup: str | None = None
    market: str
    bookmaker: str | None = None
    american_odds: int | None = None
    stake: float
    outcome: str | None = None
    profit_loss: float | None = None
    ev: float | None = None
    model_prob: float | None = None
    placed_at: str


class PerformanceBetsResponse(BaseModel):
    season: int | None
    bets: list[PerformanceBet]
    total: int
    settled_count: int
    net_pnl: float | None = None
