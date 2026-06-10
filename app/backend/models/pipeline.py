"""Pipeline status response model (A1.4 — prediction freshness indicator)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class PipelineStatus(BaseModel):
    # Core freshness signals the frontend dot/tooltip render from.
    run_date: date | None = None
    predictions_ready: bool = False
    lineup_confirmed: bool = False
    last_updated_at: datetime | None = None

    # Detail surfaced in the badge / tooltip.
    n_games_scored: int = 0
    n_qualified_bets: int = 0
    signal_completeness_score: float | None = None
    avg_feature_coverage_score: float | None = None
    pipeline_status: str = "missing"

    # Derived UI state so every client renders the dot identically.
    # green  = predictions ready AND lineups confirmed
    # yellow = predictions ready, lineups not yet confirmed (projected)
    # red    = predictions not ready (pipeline running / missing)
    indicator: str = "red"
    message: str = "Pipeline running — check back in a few minutes"
