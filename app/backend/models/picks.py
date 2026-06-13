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
    pick_side: str | None = None
    game_start_utc: datetime | None = None
    model_total_runs: float | None = None
    market_total_line: float | None = None
    predicted_at: datetime | None = None


class TodayPicksResponse(BaseModel):
    picks: list[Pick]
    data_quality: DataQuality


class FeaturedYesterday(BaseModel):
    matchup: str
    market_type: str
    outcome: str


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
    game_start_utc: datetime | None = None
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


class GamePicksResponse(BaseModel):
    picks: list[Pick]
    total: int


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
    umpire: UmpireInfo | None = None
    game_context: GameContext | None = None
