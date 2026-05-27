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
    fit_date             DATE,
    run_id               VARCHAR(36),
    ingestion_ts         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_eb_batter_posteriors PRIMARY KEY (game_pk, batting_slot, batter_id)
);
