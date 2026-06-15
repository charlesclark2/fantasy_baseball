-- Railway PostgreSQL — Credence Sports serving store (Story A2.12)
-- Idempotent: safe to re-run; existing data is preserved.
-- Run once on first provision:  psql $DATABASE_URL -f infrastructure/pg/create_serving_tables.sql

-- ── Blob cache (analogous to S3 api-cache; replaces S3 as primary read path) ──
-- cache_key examples: 'picks/today', 'picks/ev', 'picks/history',
--                     'performance/summary', 'picks/game/746123'
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key    TEXT         NOT NULL,
    cache_date   DATE         NOT NULL,
    payload      JSONB        NOT NULL,
    is_permanent BOOLEAN      DEFAULT FALSE,
    updated_at   TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (cache_key, cache_date)
);
-- Partial index for permanent (Final-game) lookups
CREATE INDEX IF NOT EXISTS api_cache_permanent_idx
    ON api_cache (cache_key)
    WHERE is_permanent = TRUE;

-- ── Individual pick rows (enables server-side portfolio filtering) ────────────
CREATE TABLE IF NOT EXISTS daily_picks (
    id                    SERIAL PRIMARY KEY,
    game_pk               INTEGER      NOT NULL,
    prediction_date       DATE         NOT NULL,
    market                VARCHAR(20)  NOT NULL,   -- 'h2h' | 'totals'
    home_team             VARCHAR(100),
    away_team             VARCHAR(100),
    game_time_utc         TIMESTAMPTZ,
    model_prob            FLOAT,
    bovada_prob           FLOAT,
    edge                  FLOAT,
    ev                    FLOAT,
    kelly_fraction        FLOAT,
    qualified_bet         BOOLEAN,
    model_version         VARCHAR(30),
    game_conviction_score FLOAT,
    lineup_confirmed      BOOLEAN,
    pick_side             VARCHAR(20),
    model_total_runs      FLOAT,
    market_total_line     FLOAT,
    total_line_consensus  FLOAT,
    pred_total_runs       FLOAT,
    is_final              BOOLEAN      DEFAULT FALSE,
    created_at            TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (game_pk, market, prediction_date)
);
CREATE INDEX IF NOT EXISTS daily_picks_date_ev_idx
    ON daily_picks (prediction_date, ev DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS daily_picks_market_idx
    ON daily_picks (market);

-- ── Per-user portfolio preferences ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_portfolios (
    user_id             VARCHAR(200) PRIMARY KEY,   -- Cognito sub
    min_ev_threshold    FLOAT        DEFAULT 0.02,
    markets             JSONB        DEFAULT '["h2h","totals"]',
    bankroll            FLOAT,
    max_kelly_fraction  FLOAT        DEFAULT 0.05,
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);
