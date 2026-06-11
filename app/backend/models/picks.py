from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DataQuality(BaseModel):
    signal_completeness_score: float | None = None
    last_updated_at: datetime | None = None
    pipeline_status: str = "unknown"


class Pick(BaseModel):
    game_pk: int
    game_date: date | None = None
    market_type: str
    model_prob: float | None = None
    bovada_devig_prob: float | None = None
    edge: float | None = None
    game_conviction_score: float | None = None
    win_prob_ci_low: float | None = None
    win_prob_ci_high: float | None = None
    lineup_confirmed: bool | None = None
    home_team: str | None = None
    away_team: str | None = None


class TodayPicksResponse(BaseModel):
    picks: list[Pick]
    data_quality: DataQuality


class HistoricalPick(Pick):
    clv: float | None = None
    clv_positive: bool | None = None
    actual_outcome: int | None = None


class HistoryPicksResponse(BaseModel):
    picks: list[HistoricalPick]
    total: int
