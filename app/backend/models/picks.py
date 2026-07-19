from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator


# ---------------------------------------------------------------------------
# Loose-timestamp tolerance (INC-23 class) — DEFENSIVE, do not remove.
#
# In --s3 (DuckDB/lakehouse) mode a TIMESTAMP column can be stored/returned as a VARCHAR like
# '2026-07-12 17:35:00+00' (space separator, 2-digit '+00' offset). Pydantic's strict datetime
# parser REJECTS that form. Because the routers wrap `Model(**blob)` in a try/except that falls
# through to an (often empty) last-resort read, ONE malformed timestamp silently blanked the whole
# EV Tracker for a date (observed 2026-07-04 and 2026-07-12).
#
# `datetime.fromisoformat` (3.11+) accepts the loose forms, so coerce before validation. The writer
# is also fixed to emit canonical ISO (write_serving_store._ts) — this is the belt-and-braces half:
# it heals blobs ALREADY written with the loose form, with no backfill required.
# ---------------------------------------------------------------------------

def _coerce_loose_ts(v: Any) -> Any:
    """Coerce a loose ISO-ish timestamp string into a datetime; pass anything else through."""
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.strip())
        except ValueError:
            return v  # let pydantic raise its normal error for a genuinely bad value
    return v


# A datetime field that tolerates the loose lakehouse/VARCHAR timestamp forms.
LooseDatetime = Annotated[datetime, BeforeValidator(_coerce_loose_ts)]


# ---------------------------------------------------------------------------
# Pick explanation models (Story 30.15)
# ---------------------------------------------------------------------------

class PickDriver(BaseModel):
    feature: str
    label: str
    family: str
    family_key: str
    contribution: float
    direction: str  # "increases" | "decreases"
    toward: str


class PickExplanationTarget(BaseModel):
    method: str
    units: str = ""
    base_value: float | None = None
    prediction: float | None = None
    toward: str = ""
    drivers: list[PickDriver] = []
    note: str | None = None  # deferred/error path


class PickExplanationPayload(BaseModel):
    served_tier: str | None = None
    basis: str = "model_reasoning"
    disclaimer: str = ""
    targets: dict[str, PickExplanationTarget] = {}


class DataQuality(BaseModel):
    signal_completeness_score: float | None = None
    last_updated_at: LooseDatetime | None = None
    pipeline_status: str = "unknown"


class Pick(BaseModel):
    game_pk: int
    game_date: date | None = None
    market_type: str
    model_prob: float | None = None
    bovada_devig_prob: float | None = None
    edge: float | None = None
    game_conviction_score: float | None = None
    gate_signals_met: int | None = None
    win_prob_ci_low: float | None = None
    win_prob_ci_high: float | None = None
    win_prob_ci_width: float | None = None
    # CLV meta-model confidence (A0.4.34): H2H from meta_*, totals from totals_meta_*
    # Both mapped to the same field names; market_type tells the frontend which model produced them
    meta_p_clv_positive: float | None = None
    meta_ci_low: float | None = None
    meta_ci_high: float | None = None
    lineup_confirmed: bool | None = None
    home_team: str | None = None
    away_team: str | None = None
    pick_side: str | None = None
    game_start_utc: LooseDatetime | None = None
    model_total_runs: float | None = None
    market_total_line: float | None = None
    predicted_at: LooseDatetime | None = None


class TodayPicksResponse(BaseModel):
    picks: list[Pick]
    data_quality: DataQuality
    is_preliminary: bool = False


class FeaturedYesterday(BaseModel):
    matchup: str
    market_type: str
    outcome: str
    # win | loss | pending — drives the green/red/Clock styling on the home featured card.
    # Was omitted (2026-07-19): the writer + heal both stamp status into DynamoDB, but this
    # model dropped it on serialization, so the recap always fell through to the pending
    # Clock icon even when the pick had settled Won/Lost.
    status: str | None = None


class FeaturedPickResponse(BaseModel):
    game_pk: int | None = None
    matchup: str | None = None
    game_time_et: str | None = None
    market_type: str | None = None
    edge: float | None = None
    model_prob: float | None = None
    market_prob: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    conviction_label: str | None = None
    ai_summary: str | None = None
    yesterday: FeaturedYesterday | None = None
    is_stale: bool = False
    is_preliminary: bool = False
    pick_date: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    pick_side: str | None = None  # 'home'|'away' for h2h; 'over'|'under' for totals
    # Story 30.15 — model explanation
    model_narrative: str | None = None
    top_drivers: list[PickDriver] | None = None
    top_drivers_h2h: list[PickDriver] | None = None
    top_drivers_totals: list[PickDriver] | None = None
    served_tier: str | None = None


class HistoricalPick(Pick):
    clv: float | None = None
    clv_positive: bool | None = None
    actual_outcome: int | None = None


class HistoryPicksResponse(BaseModel):
    picks: list[HistoricalPick]
    total: int


class EVPick(BaseModel):
    game_pk: int
    game_date: date | None = None
    game_start_utc: LooseDatetime | None = None
    market_type: str
    model_prob: float | None = None
    bovada_devig_prob: float | None = None
    edge: float | None = None
    game_conviction_score: float | None = None
    lineup_confirmed: bool | None = None
    qualified_bet: bool | None = None
    home_team: str | None = None
    away_team: str | None = None
    kelly_fraction: float | None = None
    total_line_consensus: float | None = None
    pred_total_runs: float | None = None


class EVPicksResponse(BaseModel):
    picks: list[EVPick]
    total: int
    is_preliminary: bool = False


class GamePicksResponse(BaseModel):
    picks: list[Pick]
    total: int


class StarterStartLog(BaseModel):
    """E9.36 — one prior start in a pitcher's last-3 game log (context only)."""
    date: str | None = None
    opp: str | None = None
    home_away: str | None = None
    ip: str | None = None
    k: int | None = None
    bb: int | None = None
    h: int | None = None
    r: int | None = None
    hr: int | None = None


class StarterStats(BaseModel):
    pitcher_id: int | None = None
    name: str | None = None
    is_opener: bool = False
    # Current season (season-to-date, before game date — point-in-time accurate)
    season: int | None = None
    starts: int | None = None
    ra9: float | None = None
    whip: float | None = None
    k_pct: float | None = None
    # Prior full season — surfaced when current-season starts are sparse (< 8)
    prior_season: int | None = None
    prior_starts: int | None = None
    prior_ra9: float | None = None
    prior_whip: float | None = None
    prior_k_pct: float | None = None
    # E9.36 — last 3 completed starts before this game (context/navigation, no edge claim)
    last_3_starts: list[StarterStartLog] = []


class GameStarters(BaseModel):
    home: StarterStats | None = None
    away: StarterStats | None = None


class BovadaH2H(BaseModel):
    home_american: int | None = None
    away_american: int | None = None
    snapshot_utc: str | None = None


class BovadaTotals(BaseModel):
    line: float | None = None
    over_american: int | None = None
    under_american: int | None = None
    snapshot_utc: str | None = None


class BovadaLines(BaseModel):
    h2h: BovadaH2H | None = None
    totals: BovadaTotals | None = None


class TeamPerfStats(BaseModel):
    off_woba_30d: float | None = None
    off_xwoba_30d: float | None = None
    off_runs_per_game_30d: float | None = None
    starter_xwoba_against_30d: float | None = None
    starter_k_pct_30d: float | None = None
    starter_hand: str | None = None
    lineup_vs_sp_xwoba_adj: float | None = None
    bp_xwoba_against_14d: float | None = None
    bp_innings_pitched_14d: float | None = None
    days_rest: float | None = None


class GamePerfFeatures(BaseModel):
    home: TeamPerfStats | None = None
    away: TeamPerfStats | None = None
    park_run_factor: float | None = None
    elo_diff: float | None = None


class GameScore(BaseModel):
    home_score: int | None = None
    away_score: int | None = None
    status: str = "Preview"
    # Pre-game record (adjusted from post-game when game is Final)
    home_wins: int | None = None
    home_losses: int | None = None
    away_wins: int | None = None
    away_losses: int | None = None
    # 30-day rolling Pythagorean win expectation
    home_pyth_pct: float | None = None
    home_pyth_residual: float | None = None
    away_pyth_pct: float | None = None
    away_pyth_residual: float | None = None


class LineupPlayer(BaseModel):
    slot: int
    player_id: int | None = None
    player_name: str | None = None
    position: str | None = None
    season_ops: float | None = None
    season_xwoba: float | None = None
    # Box score columns — only populated for completed games
    game_pa: int | None = None
    game_ab: int | None = None
    game_h: int | None = None
    game_k: int | None = None
    game_bb: int | None = None
    game_hr: int | None = None
    game_xwoba: float | None = None


class GameLineups(BaseModel):
    home: list[LineupPlayer] = []
    away: list[LineupPlayer] = []


class WeatherInfo(BaseModel):
    temp_f: float | None = None
    wind_speed_mph: float | None = None
    # positive = tailwind (ball carries out), negative = headwind (suppresses runs)
    wind_component_mph: float | None = None
    is_dome: bool = False
    observation_type: str | None = None


class PublicBetting(BaseModel):
    home_ml_money_pct: float | None = None
    away_ml_money_pct: float | None = None
    home_ml_ticket_pct: float | None = None
    away_ml_ticket_pct: float | None = None
    over_money_pct: float | None = None
    under_money_pct: float | None = None
    over_ticket_pct: float | None = None
    under_ticket_pct: float | None = None
    ml_sharp_signal: float | None = None
    total_sharp_signal: float | None = None


class LineMovement(BaseModel):
    open_home_win_prob: float | None = None
    pregame_home_win_prob: float | None = None
    # pregame − open; positive = home shortened (more backed), negative = home lengthened
    h2h_line_movement: float | None = None
    open_total_line: float | None = None
    pregame_total_line: float | None = None
    total_line_movement: float | None = None


# E9.37 — per-book, per-market line-movement time series (open→current). Market
# context only — NOT an edge claim (our h2h/totals models show no demonstrated
# edge). E9.37b: multi-book (was Bovada-only); h2h is de-vigged.
class LineMovementSeriesH2HPoint(BaseModel):
    ts: str
    home_win_prob: float | None = None


class LineMovementSeriesTotalsPoint(BaseModel):
    ts: str
    line: float | None = None
    # E9.37c — de-vigged Over probability at this snapshot (captures juice moves
    # when the line is sticky). None when only one side was posted.
    over_prob: float | None = None


class LineMovementSeriesBook(BaseModel):
    h2h: list[LineMovementSeriesH2HPoint] = []
    totals: list[LineMovementSeriesTotalsPoint] = []


class LineMovementSeries(BaseModel):
    # Canonical book keys present, in display order (pinnacle, betmgm, …).
    books: list[str] = []
    series: dict[str, LineMovementSeriesBook] = {}


class UmpireInfo(BaseModel):
    name: str | None = None
    k_pct_zscore: float | None = None
    runs_per_game_zscore: float | None = None
    run_impact_zscore: float | None = None
    bb_pct_zscore: float | None = None
    games_sample: int | None = None


class TeamRecentForm(BaseModel):
    l5_wins: int | None = None
    l5_losses: int | None = None
    l5_games: int | None = None
    l10_wins: int | None = None
    l10_losses: int | None = None
    l10_games: int | None = None


class H2HRecord(BaseModel):
    home_wins: int | None = None
    away_wins: int | None = None
    games_played: int | None = None
    avg_total_runs: float | None = None


class GameContext(BaseModel):
    home_form: TeamRecentForm | None = None
    away_form: TeamRecentForm | None = None
    h2h: H2HRecord | None = None


# ---------------------------------------------------------------------------
# E9.40 — "who called it" scorecard (final result + model/market benchmark)
# ---------------------------------------------------------------------------

class MarketScorecard(BaseModel):
    """Per-market settle of a completed game — factual, no profitability framing.

    Both the model's pick and the market's benchmark are graded against the
    outcome: h2h against the winner (market = the closing favorite), totals
    against the line (market = the de-vigged over/under lean — near-neutral, so
    its implied % is always surfaced). Win-semantics mirror the performance page
    (E9.26): the pick is the side the probability favors (>= 0.5 → home/over),
    one per market; "push" on an exact tie.
    """
    market_type: str                    # "h2h" | "totals"
    # Model's directional pick (from model_prob >= 0.5)
    model_side: str | None = None       # "home"|"away"|"over"|"under"
    model_result: str | None = None     # "win"|"loss"|"push"
    model_prob: float | None = None     # oriented to the picked side
    # Market benchmark — h2h: closing favorite; totals: de-vigged over/under lean
    market_side: str | None = None      # "home"|"away"|"over"|"under"
    market_result: str | None = None    # "win"|"loss"|"push"
    market_prob: float | None = None    # oriented to the market's side
    # totals line context (factual)
    total_line: float | None = None
    final_total: int | None = None
    landed: str | None = None           # "over"|"under"|"push" (totals only)


class GameScorecard(BaseModel):
    """Final result + per-market "who called it" for one completed game."""
    game_pk: int | None = None
    game_date: str | None = None
    home_team: str | None = None        # abbreviation
    away_team: str | None = None
    home_team_name: str | None = None   # full name
    away_team_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    status: str = "Final"
    markets: list[MarketScorecard] = []


class MarketRecord(BaseModel):
    """Canonical per-market record (E9.26). One call per game; pushes excluded
    from the rate denominator; `low_sample` flags a rate below the trust floor."""
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    decisive: int = 0          # wins + losses (the win_rate denominator)
    win_rate: float | None = None
    low_sample: bool = True


class MarketRecordPair(BaseModel):
    """Model vs market benchmark record for one market_type."""
    market_type: str
    n_games: int = 0
    model: MarketRecord
    market: MarketRecord


class ScorecardSummary(BaseModel):
    """Server-computed canonical tally for a slate — the ONE definition the
    frontend Results header renders (never a market-combined count)."""
    n_games: int = 0
    small_sample_n: int = 0     # the low_sample threshold, surfaced for honest copy
    markets: list[MarketRecordPair] = []


class ScorecardListResponse(BaseModel):
    """GET /picks/scorecard?date= — per-game scorecards for completed games on a date."""
    scorecards: list[GameScorecard] = []
    total: int = 0
    summary: ScorecardSummary | None = None


class GameDetailResponse(BaseModel):
    picks: list[Pick]
    total: int
    home_team_name: str | None = None
    away_team_name: str | None = None
    game_score: GameScore | None = None
    starters: GameStarters | None = None
    bovada_lines: BovadaLines | None = None
    team_features: GamePerfFeatures | None = None
    lineups: GameLineups | None = None
    weather: WeatherInfo | None = None
    public_betting: PublicBetting | None = None
    line_movement: LineMovement | None = None
    # E9.37 — per-market open→current line-movement series (additive payload field)
    line_movement_series: LineMovementSeries | None = None
    umpire: UmpireInfo | None = None
    game_context: GameContext | None = None
    # Story 30.15 — model explanation
    pick_explanation: PickExplanationPayload | None = None
    pick_narrative: str | None = None
    # E9.40 — "who called it" scorecard (populated only for Final games)
    scorecard: GameScorecard | None = None


# ---------------------------------------------------------------------------
# A0.4.32 — Per-book odds comparison
# ---------------------------------------------------------------------------

class BookOddsH2H(BaseModel):
    """Per-book h2h comparison row."""
    book_key: str
    book_name: str
    is_sharp_reference: bool = False   # True for Pinnacle
    home_american: int | None = None
    away_american: int | None = None
    home_decimal: float | None = None
    away_decimal: float | None = None
    # De-vigged (no-vig) implied probability — home side
    market_bet_pct_home: float | None = None
    # Model calibrated_win_prob (home)
    model_prob_home: float | None = None
    # EV per $1 on home side: p_model*(dec-1)-(1-p_model)
    ev_home: float | None = None
    # p_model - market_bet_pct (home)
    edge_home: float | None = None
    kelly_home: float | None = None
    # ISO timestamp of the snapshot these prices came from
    odds_as_of: str | None = None
    # E9.1 — breakeven American price at which EV=0 (model-relative, not a bet rec)
    breakeven_american_home: int | None = None
    breakeven_american_away: int | None = None


class BookOddsTotals(BaseModel):
    """Per-book totals comparison row."""
    book_key: str
    book_name: str
    is_sharp_reference: bool = False
    line: float | None = None
    over_american: int | None = None
    under_american: int | None = None
    over_decimal: float | None = None
    under_decimal: float | None = None
    # De-vigged implied P(over)
    market_bet_pct_over: float | None = None
    # Model P(over) re-computed at THIS book's line via NegBin CDF
    model_prob_over: float | None = None
    model_prob_under: float | None = None
    p_push: float | None = None
    ev_over: float | None = None
    ev_under: float | None = None
    edge_over: float | None = None
    kelly_over: float | None = None
    # ISO timestamp of the snapshot these prices came from
    odds_as_of: str | None = None
    # E9.1 — breakeven American price at which EV=0 (model-relative, not a bet rec)
    breakeven_american_over: int | None = None
    breakeven_american_under: int | None = None


class BestPriceH2H(BaseModel):
    """Best US-bettable price for one h2h side (home or away). Pinnacle excluded."""
    book_key: str
    book_name: str
    american: int
    decimal: float | None = None
    # De-vigged implied probability for this side
    market_bet_pct: float | None = None
    ev: float | None = None
    # model_prob - market_bet_pct
    edge: float | None = None
    # E9.1 breakeven American price at which EV=0
    breakeven_american: int | None = None


class BestPriceTotals(BaseModel):
    """Best US-bettable price for one totals side (over or under). Pinnacle excluded."""
    book_key: str
    book_name: str
    line: float
    american: int
    decimal: float | None = None
    market_bet_pct: float | None = None
    model_prob: float | None = None
    ev: float | None = None
    edge: float | None = None
    breakeven_american: int | None = None


class BookOddsComparison(BaseModel):
    """Full per-book comparison for one game (h2h + totals, all seven books)."""
    game_pk: int
    home_team: str | None = None
    away_team: str | None = None
    # Champion model distribution params used for P(over) recomputation (transparency)
    pred_total_runs: float | None = None
    pred_total_runs_scale: float | None = None
    h2h: list[BookOddsH2H] = []
    totals: list[BookOddsTotals] = []
    # E9.11 — best US-bettable price per side (Pinnacle excluded; sorted highest American first)
    best_h2h_home: BestPriceH2H | None = None
    best_h2h_away: BestPriceH2H | None = None
    best_totals_over: BestPriceTotals | None = None
    best_totals_under: BestPriceTotals | None = None


# ---------------------------------------------------------------------------
# E9.11 — Line-shopping / +EV plays view
# ---------------------------------------------------------------------------

class LineshoppingPlay(BaseModel):
    """One play in the E9.11 best-price / line-shopping view.

    A play is model-relative: model_prob > best US book de-vigged prob.
    This is a line-shopping transparency aid — not a bet recommendation.
    best_alpha=0; no demonstrated market edge.
    """
    game_pk: int
    game_date: str
    game_start_utc: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    market_type: str          # "h2h" or "totals"
    side: str                 # "home" | "away" | "over" | "under"
    model_prob: float
    best_book_key: str
    best_book_name: str
    best_american: int
    best_devigged_prob: float
    # model_prob - best_devigged_prob (always > 0 — negative-edge plays are excluded)
    edge: float
    ev: float | None = None
    breakeven_american: int | None = None  # E9.1
    # Pinnacle de-vigged fair value anchor (not US-bettable)
    pinnacle_devigged_prob: float | None = None


class LineshoppingResponse(BaseModel):
    """Response for GET /picks/line-shopping — sorted by edge desc."""
    plays: list[LineshoppingPlay] = []
    total: int = 0
    is_preliminary: bool = False
