-- Bet tracker: records individual bets placed by the user.
-- market values match daily_model_predictions: 'h2h home', 'h2h away', 'over', 'under'
-- outcome: NULL = pending, 'win', 'loss', 'push'
-- profit_loss: stake × (decimal_odds − 1) for win; −stake for loss; 0 for push; NULL if pending

CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.placed_bets (
    bet_id         VARCHAR(36) DEFAULT UUID_STRING(),
    placed_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    score_date     DATE NOT NULL,
    game_pk        INTEGER NOT NULL,
    matchup        VARCHAR(100),
    market         VARCHAR(20) NOT NULL,
    bookmaker      VARCHAR(50),
    american_odds  INTEGER NOT NULL,
    stake          FLOAT NOT NULL,
    total_line     FLOAT,
    model_prob     FLOAT,
    market_prob    FLOAT,
    ev             FLOAT,
    kelly_capped   FLOAT,
    outcome        VARCHAR(10),
    profit_loss    FLOAT,
    notes          VARCHAR(500)
);
