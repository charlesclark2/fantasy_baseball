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
