CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.model_health_log (
    run_date     DATE         NOT NULL,
    target       VARCHAR(50)  NOT NULL,
    window_days  INT,
    ece          FLOAT,
    brier        FLOAT,
    sample_n     INT,
    alert_fired  BOOLEAN      DEFAULT FALSE,
    created_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
);
