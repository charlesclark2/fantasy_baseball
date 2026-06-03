CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_batter_posteriors_raw (
    game_pk              VARCHAR(20)   NOT NULL,
    batting_slot         INTEGER       NOT NULL,
    batter_id            VARCHAR(20)   NOT NULL,
    season               INTEGER       NOT NULL,
    game_date            DATE          NOT NULL,
    eb_woba              FLOAT,
    eb_k_pct             FLOAT,
    eb_bb_pct            FLOAT,
    eb_iso               FLOAT,
    eb_woba_uncertainty  FLOAT,
    pa_weight            FLOAT,
    eb_data_source       VARCHAR(20),
    eb_woba_sequential   FLOAT,            -- Epic 16.2: as-of sequential xwOBA posterior (parallel; never overwrites eb_woba)
    posterior_source     VARCHAR(20),      -- Epic 16.2: sequential | season_eb | prior_only
    prior_age_days       INTEGER,          -- Epic 16.2: days since the as-of sequential posterior was last updated (NULL when not sequential)
    fit_date             DATE,
    run_id               VARCHAR(36),
    ingestion_ts         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_eb_batter_posteriors PRIMARY KEY (game_pk, batting_slot, batter_id)
);
