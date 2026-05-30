-- =============================================================================
-- eb_park_factors_granular_raw
-- Grain: one row per (venue_id, season).
-- Empirical Bayes smoothed granular park factors (HR, 2B/3B, 1B, BB, SO,
-- wOBA) derived from Baseball Savant statcast-park-factors data.
-- Written by betting_ml/scripts/eb_priors/fit_granular_park_priors.py.
-- MERGE-upserted on (venue_id, season) each run.
-- All factor values are ratios (1.0 = league average). Savant index / 100.
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.betting.eb_park_factors_granular_raw (

    -- ── Grain ───────────────────────────────────────────────────────────────
    venue_id                            INTEGER         NOT NULL,
    season                              INTEGER         NOT NULL,

    -- ── Sample ──────────────────────────────────────────────────────────────
    n_pa                                INTEGER,

    -- ── Raw Savant factors (ratio; 1.0 = league average) ────────────────────
    raw_hr_factor                       FLOAT,
    raw_doubles_triples_factor          FLOAT,
    raw_singles_factor                  FLOAT,
    raw_bb_factor                       FLOAT,
    raw_so_factor                       FLOAT,
    raw_woba_factor                     FLOAT,

    -- ── EB-smoothed factors ──────────────────────────────────────────────────
    eb_hr_factor                        FLOAT,
    eb_doubles_triples_factor           FLOAT,
    eb_singles_factor                   FLOAT,
    eb_bb_factor                        FLOAT,
    eb_so_factor                        FLOAT,
    eb_woba_factor                      FLOAT,

    -- ── Shrinkage (per factor; 0=no shrink, 1=all prior) ────────────────────
    shrinkage_hr                        FLOAT,
    shrinkage_doubles_triples           FLOAT,
    shrinkage_singles                   FLOAT,
    shrinkage_bb                        FLOAT,
    shrinkage_so                        FLOAT,

    -- ── Prior params (shared per season fit) ────────────────────────────────
    prior_mean_hr                       FLOAT,
    prior_variance_hr                   FLOAT,
    prior_mean_doubles_triples          FLOAT,
    prior_variance_doubles_triples      FLOAT,

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    fit_date                            DATE            NOT NULL,
    run_id                              VARCHAR(64)     NOT NULL,

    CONSTRAINT pk_eb_park_factors_granular PRIMARY KEY (venue_id, season)
);
