-- Epic 16.2 — sequential-posterior columns on the EB posterior tables (prod + dev).
--
-- Parallel columns (they do NOT overwrite eb_woba / eb_xwoba_against). Populated by
-- the leakage-safe as-of lookup in betting_ml/scripts/sequential_bayes/asof_lookup.py
-- (latest player_sequential_posteriors row with game_date < scoring_date — STRICT
-- inequality, never is_current, which would inject the season-final posterior into
-- mid-season games and reintroduce leakage).
--
--   eb_woba_sequential          (batter)  — posterior_mu from the as-of sequential xwOBA chain
--   eb_xwoba_against_sequential (starter) — posterior_mu from the as-of sequential xwOBA-against chain
--   posterior_source            — {sequential | season_eb | prior_only}
--   prior_age_days              — scoring_date − last sequential update (NULL unless sequential); >7 flags stale beliefs
--
-- NOTE: bullpen sequential beliefs are NOT injected here — eb_bullpen_team_posteriors
-- is team-grain (not per-pitcher), so bullpen propagation happens at team level via
-- Epic 16.3 (team_sequential_bullpen_xwoba in feature_pregame_game_features).
--
-- Idempotent (ADD COLUMN IF NOT EXISTS). Run in BOTH prod and dev.

-- ── prod: baseball_data.betting ──────────────────────────────────────────────
alter table baseball_data.betting.eb_batter_posteriors_raw add column if not exists eb_woba_sequential float;
alter table baseball_data.betting.eb_batter_posteriors_raw add column if not exists posterior_source   varchar(20);
alter table baseball_data.betting.eb_batter_posteriors_raw add column if not exists prior_age_days      integer;

alter table baseball_data.betting.eb_starter_posteriors add column if not exists eb_xwoba_against_sequential float;
alter table baseball_data.betting.eb_starter_posteriors add column if not exists posterior_source           varchar(20);
alter table baseball_data.betting.eb_starter_posteriors add column if not exists prior_age_days             integer;

-- ── dev: baseball_data.dev_betting ───────────────────────────────────────────
alter table baseball_data.dev_betting.eb_batter_posteriors_raw add column if not exists eb_woba_sequential float;
alter table baseball_data.dev_betting.eb_batter_posteriors_raw add column if not exists posterior_source   varchar(20);
alter table baseball_data.dev_betting.eb_batter_posteriors_raw add column if not exists prior_age_days      integer;

alter table baseball_data.dev_betting.eb_starter_posteriors add column if not exists eb_xwoba_against_sequential float;
alter table baseball_data.dev_betting.eb_starter_posteriors add column if not exists posterior_source           varchar(20);
alter table baseball_data.dev_betting.eb_starter_posteriors add column if not exists prior_age_days             integer;
