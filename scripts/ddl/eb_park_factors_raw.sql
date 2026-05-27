-- DDL: baseball_data.betting.eb_park_factors_raw
-- Stores Empirical Bayes smoothed park run factors.
-- Written by betting_ml/scripts/eb_priors/fit_park_priors.py.
-- Grain: one row per (venue_id, season). MERGE-upserted on each run.

CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_park_factors_raw (
    venue_id                          INTEGER       NOT NULL,
    season                            INTEGER       NOT NULL,
    eb_park_run_factor                FLOAT         NOT NULL,
    eb_park_run_factor_uncertainty    FLOAT         NOT NULL,
    n_games                           INTEGER       NOT NULL,
    raw_park_run_factor               FLOAT         NOT NULL,
    shrinkage_factor                  FLOAT         NOT NULL,
    prior_mean                        FLOAT         NOT NULL,
    prior_variance                    FLOAT         NOT NULL,
    fit_date                          DATE          NOT NULL,
    run_id                            VARCHAR(64)   NOT NULL,

    CONSTRAINT pk_eb_park_factors PRIMARY KEY (venue_id, season)
);
