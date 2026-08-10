-- =============================================================================
-- eb_starter_posteriors_dbt.sql  —  Story A2.11
-- Grain: one row per (game_pk, pitcher_id) for confirmed probable starters.
--
-- Replaces betting_ml/scripts/eb_priors/compute_starter_posteriors.py. The
-- per-starter math is 100% closed-form (Normal-Normal conjugate shrinkage of
-- season-to-date xwOBA-against / K% / BB% toward experience-band priors), so it
-- expresses directly as a dbt model — removing the daily Python warehouse path
-- and any train/serve skew between the Python and SQL surfaces.
--
-- ⭐ 30.6 RESIDUAL: sourced from stg_statsapi_probable_pitchers (same as fix-a
-- feature_pregame_starter_features), so it ranges over the FULL schedule spine
-- including +1/+2-day games. The Python was game_pk-scoped to today's slate
-- (--game-date today), leaving future games' starter-EB NULL at serve. A dbt
-- model materializes over its entire input relation → future games populate by
-- construction.
--
-- VALIDATION: built under the _dbt suffix and compared byte-for-byte against the
-- Python-written baseball_data.betting.eb_starter_posteriors on closed season
-- 2025 before any cutover. On green: rename → eb_starter_posteriors, drop the
-- sources.yml entry, and rewire feature_pregame_starter_features to ref() it.
--
-- Normal-Normal posterior (per metric, when current_bf > 0 and obs is present):
--   σ_meas² = max(obs·(1-obs), 1e-4) / BF
--   post_mean = (μ₀/σ₀² + obs/σ_meas²) / (1/σ₀² + 1/σ_meas²)
--   post_std  = sqrt( 1 / (1/σ₀² + 1/σ_meas²) )
-- eb_data_source:
--   prior_only      — current_bf = 0 and NOT IL-return → posterior = prior mean
--   il_return_blend — current_starts < 3 and prior_starts ≥ 10 → 0.5·post + 0.5·prior_obs
--   full_eb         — otherwise
-- LEAKAGE GUARD: season-to-date stats joined with game_date < starter.game_date
-- (strict), mirroring compute_starter_posteriors.py + feature_pregame_starter_features.
--
-- ⭐ E7.5p (2026-07-27) — the PITCHER MiLB→MLB MLE cold-start prior (milb_mle_pitcher_prior_v1),
-- the pitcher sibling of E7.5's batter wiring. A debuting rookie starter used to get the GENERIC
-- experience-band prior; he now gets his MLE-translated minor-league line for the metrics E7.3p
-- proved TRANSLATE, and the existing BF-accrual shrink runs off THAT prior instead:
--   • gb_pct  — ✅ STRONG feeder (OOS corr 0.551, PBO 0.000, DSR 1.000). NEW served column
--               `eb_gb_pct` (the table carried no ground-ball metric at all).
--   • k_pct   — 🟡 weak-but-real (corr 0.366, DSR 0.786) — WIDE recalibrated prior.
--   • bb_pct  — 🟡 weak-but-real (corr 0.367, DSR 0.947).
--   • hr_rate / xwoba_against — ⛔ NOT wired (E7.3p tied-field null / no-signal). eb_xwoba_against
--               keeps its experience-band prior verbatim.
-- COLD-START GATE (stricter than the batter sibling, on purpose): the MLE applies only when
-- n_prior_seasons = 0 (⇔ age_band 'u25' — under 10 career prior starts AND under 150 career prior
-- BF). The E7.3p map is calibrated on a pitcher's FIRST TWO MLB seasons; feeding an established
-- starter his 2015 minor line would be out-of-distribution.
-- κ-BLEND, NEVER NORMAL-NORMAL: every wired metric is a bounded rate, so the MLE update is the
-- pseudo-count blend (m·κ + obs·n)/(κ + n) — the E7.5 ISO blow-up lesson applied pre-emptively (a
-- measurement-variance floor cannot stop a tiny-sample extreme obs from overwhelming the prior).
-- κ is in the metric's OWN evidence units: BF for K%/BB%, balls-in-play for GB%.
-- The prior arrives as the FAIL-SAFE `milb_mle_pitcher_prior` W8a precursor view — absent parquet ⇒
-- empty typed view ⇒ all-NULL MLE columns ⇒ the generic prior everywhere (never a HALT).
-- ⚠️ EXPECTATION: pitcher K% translates far more weakly than batter K% (0.366 vs 0.637), so the
-- lift here is MODEST and concentrated in GB%. best_alpha = 0 — a calibration fix, not an edge.
-- =============================================================================

-- No custom schema → defaults to target.schema (betting on prod), matching the
-- mart_* models and the existing Python-written eb_starter_posteriors.
-- Story A2.11: incremental (merge on grain) so the daily rebuild only recomputes
-- recent games — matching the Python's idempotent per-day MERGE. The season-to-date
-- joins still read full source for the recent games (values stay exact); only the
-- OUTPUT spine (starters) is scoped to the recent window.

-- E11.1-W8a: dual-branch. DuckDB branch (real compute -> S3, run_w1_lakehouse._build_w8a)
-- reads the migrated upstream marts/staging (registered DuckDB views) + the S3-mirrored
-- player_sequential_posteriors where applicable; is_incremental blocks are stripped by
-- extract_duckdb_sql (DuckDB = full rebuild -> COPY). The TYPE-PIN block (gen_type_contract
-- --write) casts every FLOAT output ::double (INC-19 cure) so the S3 parquet / lakehouse_ext
-- type is stable; guarded by test_type_contract_guard.py. The Snowflake (else) branch MERGEs
-- from the lakehouse_ext external table; at cutover the operator DROPs+rebuilds this
-- incremental so the stored NUMBER cols adopt the FLOAT type (INC-19).

{% if target.name == 'duckdb' %}

{{ config(materialized='incremental', unique_key=['game_pk', 'pitcher_id'], incremental_strategy='merge', tags=['w8a_lakehouse']) }}

with probable as (
    select game_pk, game_date, side, probable_pitcher_id as pitcher_id
    from (
        select game_pk, game_date, side, probable_pitcher_id,
               row_number() over (
                   partition by game_pk, side order by ingestion_ts desc nulls last
               ) as rn
        from stg_statsapi_probable_pitchers
        where probable_pitcher_id is not null
    )
    where rn = 1
),

starters as (
    select
        game_pk::varchar     as game_pk,
        side::varchar        as side,
        pitcher_id::varchar  as pitcher_id,
        game_date::date      as game_date,
        year(game_date)      as season
    from probable
    where year(game_date) between 2016 and year(current_date())
    {% if is_incremental() %}
      -- Anchor the incremental window to PROCESSING time, NOT max(game_date).
      -- Incident 2026-06-15: the spine (stg_statsapi_probable_pitchers) carries a
      -- handful of far-future ANNOUNCED starters (marquee games months out), so
      -- max(game_date) ran to 2026-09-22 and `max-7` = 2026-09-15 — every
      -- incremental run skipped TODAY's slate entirely. The table held only 12
      -- stray future-dated rows; today's 20 starters had no posterior →
      -- home/away_starter_eb_xwoba_against served 100% NULL, re-breaking the exact
      -- serving block Story 30.6 fixed. (The batter/bullpen EB models use the same
      -- pattern but their spines are SETTLED game logs, so max(game_date) ≈ the
      -- latest completed game and the window is correct — only the forward-looking
      -- probable-pitcher spine poisons it.) current_date()-7 always recomputes the
      -- recent window + all upcoming announced starters.
      and game_date >= dateadd('day', -7, current_date())
    {% endif %}
),

gamelog as (
    select
        pitcher_id::varchar as pitcher_id,
        game_date::date     as game_date,
        game_year,
        batters_faced, strikeouts, walks, xwoba_against
    from mart_starting_pitcher_game_log
    where batters_faced > 0
),

-- Season-to-date (strictly before the start) — current season
current_stats as (
    select
        s.game_pk, s.pitcher_id,
        count(*)                 as starts,
        sum(g.batters_faced)     as total_bf,
        sum(g.strikeouts)        as total_k,
        sum(g.walks)             as total_bb,
        sum(g.xwoba_against * g.batters_faced) / nullif(sum(g.batters_faced), 0) as season_xwoba
    from starters s
    join gamelog g
      on  g.pitcher_id = s.pitcher_id
      and g.game_year  = s.season
      and g.game_date  < s.game_date          -- LEAKAGE GUARD
    group by s.game_pk, s.pitcher_id
),

-- Full prior season (season - 1) — for IL-return detection + blend
prior_stats as (
    select
        s.game_pk, s.pitcher_id,
        count(*)                 as prior_starts,
        sum(g.batters_faced)     as prior_bf,
        sum(g.strikeouts)        as prior_k,
        sum(g.walks)             as prior_bb,
        sum(g.xwoba_against * g.batters_faced) / nullif(sum(g.batters_faced), 0) as prior_xwoba
    from starters s
    join gamelog g
      on  g.pitcher_id = s.pitcher_id
      and g.game_year  = s.season - 1
    group by s.game_pk, s.pitcher_id
),

-- Qualifying prior-season count → experience band (matches _load_pitcher_prior_seasons)
prior_seasons as (
    select sp.pitcher_id, sp.season,
           count(distinct g.game_year) as n_prior_seasons
    from (select distinct pitcher_id, season from starters) sp
    join gamelog g
      on  g.pitcher_id = sp.pitcher_id
      and g.game_year  < sp.season
    group by sp.pitcher_id, sp.season
    having count(*) >= 10 or sum(g.batters_faced) >= 150
),

starter_band as (
    select
        s.game_pk, s.side, s.pitcher_id, s.game_date, s.season,
        case
            when coalesce(ps.n_prior_seasons, 0) = 0 then 'u25'
            when ps.n_prior_seasons <= 3 then 'a25'
            when ps.n_prior_seasons <= 7 then 'a30'
            else 'a33'
        end as age_band,
        -- E7.5p COLD-START GATE. n_prior_seasons = 0 means the pitcher has no QUALIFYING prior MLB
        -- experience (under 10 career prior starts AND under 150 career prior BF — the `prior_seasons`
        -- HAVING). That is exactly the population the E7.3p map is calibrated on (a pitcher's first two
        -- MLB seasons), and exactly the population the generic band prior serves worst. An established
        -- starter is deliberately EXCLUDED: his 2015 minor-league line is out-of-distribution for 2026.
        (coalesce(ps.n_prior_seasons, 0) = 0) as is_cold_start
    from starters s
    left join prior_seasons ps
      on ps.pitcher_id = s.pitcher_id and ps.season = s.season
),

-- ── E7.5p: the PITCHER MiLB→MLB MLE cold-start prior (milb_mle_pitcher_prior_v1) ────────────
-- One row per pitcher (MLBAM) at the HIGHEST reached MiLB level, carrying the E7.3p MLE-translated
-- MLB-equivalent rate + the E13.6-recalibrated prior STRENGTH as a pseudo-count κ (the equivalent
-- number of MLB batters-faced / balls-in-play the prior is worth). Static precursor, rebuilt when the
-- MLE is retrained, read as a FAIL-SAFE W8a precursor view over S3 (absent ⇒ empty typed view ⇒ the
-- generic prior everywhere). LEAKAGE: only pre-debut minor stats enter the MLE (the E7.3p as-of guard).
-- hr_rate / xwoba_against are DELIBERATELY absent — E7.3p graded them tied-field-null / no-signal.
mle_pitcher_prior as (
    select
        pitcher_id::varchar as pitcher_id,
        mle_gb_pct, gb_pct_prior_kappa,
        mle_k_pct,  k_pct_prior_kappa,
        mle_bb_pct, bb_pct_prior_kappa
    from milb_mle_pitcher_prior
    qualify row_number() over (
        partition by pitcher_id order by gb_pct_prior_kappa desc nulls last
    ) = 1
),

-- ── E7.5p: the observed GB% component (prior season) ────────────────────────────────────────
-- `mart_pitcher_batted_ball_profile` is SEASON-grain, so the leakage-safe join is game_year = season−1
-- — the same doctrine every other batted-ball / platoon / TTO consumer here uses. A cold-start rookie
-- has NO prior-season row, which is precisely why his GB% collapses to a prior and why the MLE matters.
-- try_cast to BIGINT on both sides: a DOUBLE-typed id rendered ::varchar becomes '664983.0' and matches
-- nothing (the INC-17 mirror-poisoning class); an integer key sidesteps it entirely.
gb_prior_season as (
    select
        s.game_pk,
        s.pitcher_id,
        b.gb_pct                as pobs_gb,
        b.total_batted_balls    as pobs_bip
    from starters s
    join mart_pitcher_batted_ball_profile b
      on  try_cast(b.pitcher_id as bigint) = try_cast(s.pitcher_id as bigint)
      and b.game_year = s.season - 1
    where b.gb_pct is not null
),

-- League GB% anchor for a starter with NO MLE prior — the generic prior the MLE replaces for rookies.
-- Restricted to pitchers who actually STARTED (the mart covers relievers too, whose GB mix differs),
-- BIP-weighted, and offset to `season` so a game in year Y reads year Y−1 (leakage-safe by construction).
-- κ_generic inverts the between-pitcher spread the same way the MLE κ inverts σ_resid, clipped to the
-- same [20, 400] band so neither prior can freeze a starter's own observed line.
gb_league_prior as (
    select
        b.game_year + 1 as season,
        sum(b.gb_pct * b.total_batted_balls) / nullif(sum(b.total_batted_balls), 0) as league_gb_mu,
        stddev_samp(b.gb_pct)                                                       as league_gb_sd
    from mart_pitcher_batted_ball_profile b
    join (select distinct pitcher_id, game_year from gamelog) g
      on  try_cast(g.pitcher_id as bigint) = try_cast(b.pitcher_id as bigint)
      and g.game_year = b.game_year
    where b.gb_pct is not null
    group by b.game_year
),
gb_league_all as (
    -- pooled all-seasons fallback for the earliest year (no prior season to anchor on)
    select
        sum(b.gb_pct * b.total_batted_balls) / nullif(sum(b.total_batted_balls), 0) as league_gb_mu_all,
        stddev_samp(b.gb_pct)                                                       as league_gb_sd_all
    from mart_pitcher_batted_ball_profile b
    join (select distinct pitcher_id, game_year from gamelog) g
      on  try_cast(g.pitcher_id as bigint) = try_cast(b.pitcher_id as bigint)
      and g.game_year = b.game_year
    where b.gb_pct is not null
),

-- ── Prior cells with band fallback (lowest band_rank per season×metric) ──────
priors as (
    select season, metric, age_band, band_rank, mu, sigma
    from ref_eb_starter_priors
),
priors_fallback as (
    select season, metric, mu, sigma
    from (
        select season, metric, mu, sigma,
               row_number() over (partition by season, metric order by band_rank) as rn
        from priors
    ) where rn = 1
),
prior_resolved as (
    select
        sb.game_pk, sb.pitcher_id, m.metric,
        coalesce(ex.mu,    fb.mu)    as mu0,
        coalesce(ex.sigma, fb.sigma) as sigma0
    from starter_band sb
    cross join (values ('xwoba_against'), ('k_pct'), ('bb_pct')) as m(metric)
    left join priors ex
      on ex.season = sb.season and ex.metric = m.metric and ex.age_band = sb.age_band
    left join priors_fallback fb
      on fb.season = sb.season and fb.metric = m.metric
),
prior_cells as (
    select
        game_pk, pitcher_id,
        max(case when metric = 'xwoba_against' then mu0    end) as mu_xwoba,
        max(case when metric = 'xwoba_against' then sigma0 end) as sigma_xwoba,
        max(case when metric = 'k_pct'         then mu0    end) as mu_k,
        max(case when metric = 'k_pct'         then sigma0 end) as sigma_k,
        max(case when metric = 'bb_pct'        then mu0    end) as mu_bb,
        max(case when metric = 'bb_pct'        then sigma0 end) as sigma_bb
    from prior_resolved
    group by game_pk, pitcher_id
),

-- ── Epic 16.2 as-of sequential posterior (parallel column; never overwrites) ─
-- Reads the Python-managed player_sequential_posteriors as a source (out of
-- A2.11 scope); strict game_date < start mirrors asof_lookup.py.
seq as (
    select s.game_pk, s.pitcher_id, sp.posterior_mu, sp.game_date as seq_game_date
    from starter_band s
    join player_sequential_posteriors sp
      on  sp.player_id::varchar = s.pitcher_id
      and sp.player_type = 'starter'
      and sp.metric      = 'xwoba_against'
      and sp.season      = s.season
      and sp.game_date   < s.game_date
    qualify row_number() over (
        partition by s.game_pk, s.pitcher_id order by sp.game_date desc
    ) = 1
),

-- ── Assemble + observed rates + IL flag ─────────────────────────────────────
calc as (
    select
        sb.game_pk, sb.side, sb.pitcher_id, sb.season, sb.game_date, sb.age_band,
        coalesce(cs.total_bf, 0) as current_bf,
        coalesce(cs.starts, 0)   as current_starts,
        coalesce(pr.prior_starts, 0) as prior_starts,
        cs.season_xwoba                              as obs_xwoba,
        cs.total_k  / nullif(cs.total_bf, 0)         as obs_k,
        cs.total_bb / nullif(cs.total_bf, 0)         as obs_bb,
        pr.prior_xwoba                               as pobs_xwoba,
        pr.prior_k  / nullif(pr.prior_bf, 0)         as pobs_k,
        pr.prior_bb / nullif(pr.prior_bf, 0)         as pobs_bb,
        pc.mu_xwoba, pc.sigma_xwoba, pc.mu_k, pc.sigma_k, pc.mu_bb, pc.sigma_bb,
        sq.posterior_mu as seq_mu, sq.seq_game_date,
        (coalesce(cs.starts, 0) < 3 and coalesce(pr.prior_starts, 0) >= 10) as is_il,
        -- ── E7.5p MiLB MLE cold-start prior (NULL for an experienced starter or one with no minor
        -- line → every branch below falls back to the incumbent generic prior for that metric) ──
        case when sb.is_cold_start then mp.mle_gb_pct end          as mle_gb_pct,
        case when sb.is_cold_start then mp.gb_pct_prior_kappa end  as gb_prior_kappa,
        case when sb.is_cold_start then mp.mle_k_pct end           as mle_k_pct,
        case when sb.is_cold_start then mp.k_pct_prior_kappa end   as k_prior_kappa,
        case when sb.is_cold_start then mp.mle_bb_pct end          as mle_bb_pct,
        case when sb.is_cold_start then mp.bb_pct_prior_kappa end  as bb_prior_kappa,
        -- observed prior-season GB% (+ its balls-in-play evidence count) and the league GB% anchor
        gb.pobs_gb, gb.pobs_bip,
        coalesce(gl.league_gb_mu, ga.league_gb_mu_all) as league_gb_mu,
        coalesce(gl.league_gb_sd, ga.league_gb_sd_all) as league_gb_sd
    from starter_band sb
    left join current_stats  cs on cs.game_pk = sb.game_pk and cs.pitcher_id = sb.pitcher_id
    left join prior_stats    pr on pr.game_pk = sb.game_pk and pr.pitcher_id = sb.pitcher_id
    left join prior_cells    pc on pc.game_pk = sb.game_pk and pc.pitcher_id = sb.pitcher_id
    left join seq            sq on sq.game_pk = sb.game_pk and sq.pitcher_id = sb.pitcher_id
    -- integer-key join (not ::varchar): a float-rendered id would read '664983.0' and match nothing
    left join mle_pitcher_prior mp
      on try_cast(mp.pitcher_id as bigint) = try_cast(sb.pitcher_id as bigint)
    left join gb_prior_season   gb on gb.game_pk = sb.game_pk and gb.pitcher_id = sb.pitcher_id
    left join gb_league_prior   gl on gl.season = sb.season
    cross join gb_league_all    ga
),

-- ── Normal-Normal posteriors (per metric) ───────────────────────────────────
post as (
    select
        c.*,
        -- xwOBA-against posterior mean + std (std only needed for xwoba uncertainty)
        case when current_bf > 0 and obs_xwoba is not null then
            (mu_xwoba * (1.0/(sigma_xwoba*sigma_xwoba)) + obs_xwoba * (current_bf/greatest(obs_xwoba*(1-obs_xwoba), 0.0001)))
            / ((1.0/(sigma_xwoba*sigma_xwoba)) + (current_bf/greatest(obs_xwoba*(1-obs_xwoba), 0.0001)))
        else mu_xwoba end as postm_xwoba,
        case when current_bf > 0 and obs_xwoba is not null then
            sqrt(1.0 / ((1.0/(sigma_xwoba*sigma_xwoba)) + (current_bf/greatest(obs_xwoba*(1-obs_xwoba), 0.0001))))
        else sigma_xwoba end as posts_xwoba,
        case when current_bf > 0 and obs_k is not null then
            (mu_k * (1.0/(sigma_k*sigma_k)) + obs_k * (current_bf/greatest(obs_k*(1-obs_k), 0.0001)))
            / ((1.0/(sigma_k*sigma_k)) + (current_bf/greatest(obs_k*(1-obs_k), 0.0001)))
        else mu_k end as postm_k,
        case when current_bf > 0 and obs_bb is not null then
            (mu_bb * (1.0/(sigma_bb*sigma_bb)) + obs_bb * (current_bf/greatest(obs_bb*(1-obs_bb), 0.0001)))
            / ((1.0/(sigma_bb*sigma_bb)) + (current_bf/greatest(obs_bb*(1-obs_bb), 0.0001)))
        else mu_bb end as postm_bb,

        -- ── E7.5p: the MLE cold-start path — a PSEUDO-COUNT (κ) blend, never Normal-Normal ──────
        -- post = (m·κ + obs·n)/(κ + n): at n=0 it is exactly the MLE mean, and it converges to the
        -- rookie's own line as n accrues (κ = the equivalent BF the prior is worth, ≈80 for K%, ≈146
        -- for BB% off the recalibrated σ_resid). Mirrors mle_prior_pitcher.kappa_blend_posterior_mean
        -- EXACTLY — the wiring test asserts SQL↔Python agreement. Unlike the Normal-Normal branch
        -- above, no measurement-variance floor exists for a tiny-sample extreme obs to exploit
        -- (the E7.5 ISO blow-up, pre-empted).
        case when mle_k_pct is not null and current_bf > 0 and obs_k is not null then
            (mle_k_pct * k_prior_kappa + obs_k * current_bf) / (k_prior_kappa + current_bf)
        else mle_k_pct end as postm_k_mle,
        case when mle_bb_pct is not null and current_bf > 0 and obs_bb is not null then
            (mle_bb_pct * bb_prior_kappa + obs_bb * current_bf) / (bb_prior_kappa + current_bf)
        else mle_bb_pct end as postm_bb_mle,

        -- ── E7.5p: eb_gb_pct — the NEW ground-ball posterior (E7.3p's STRONGEST translation) ────
        -- Prior mean/strength = the MLE line for a cold-start starter, else the prior-season league
        -- GB% anchor with κ inverted from its between-pitcher spread (same [20,400] clip). Evidence =
        -- the pitcher's PRIOR-SEASON GB% weighted by balls in play (the mart is season-grain, so
        -- season−1 is the leakage-safe join — a within-season as-of GB% would need a pitch-level
        -- re-aggregation). A rookie has no prior-season row → n=0 → the posterior IS the MLE mean,
        -- which is the whole point of the story.
        coalesce(mle_gb_pct, league_gb_mu) as gb_prior_mu,
        coalesce(
            gb_prior_kappa,
            least(greatest(
                league_gb_mu * (1 - league_gb_mu) / greatest(league_gb_sd * league_gb_sd, 1e-9) - 1,
                20.0), 400.0)
        ) as gb_prior_kappa_eff
    from calc c
),

-- Second pass so the GB posterior can read the resolved prior (DuckDB has no lateral column refs).
post_gb as (
    select
        p.*,
        case
            when coalesce(p.gb_prior_mu, -1) < 0 then null            -- no MLE and no league anchor
            when p.pobs_bip > 0 and p.pobs_gb is not null then
                (p.gb_prior_mu * p.gb_prior_kappa_eff + p.pobs_gb * p.pobs_bip)
                / (p.gb_prior_kappa_eff + p.pobs_bip)
            else p.gb_prior_mu
        end as postm_gb
    from post p
),

final as (
    select
        game_pk,
        side,
        pitcher_id,
        season,
        game_date,
        age_band,
        current_bf::integer       as current_season_bf,
        current_starts::integer   as current_season_starts,

        -- eb_data_source label
        case
            when current_bf = 0 and not is_il then 'prior_only'
            when is_il then 'il_return_blend'
            else 'full_eb'
        end as eb_data_source,

        -- eb_xwoba_against
        round(case
            when current_bf = 0 and not is_il then mu_xwoba
            when is_il then case when pobs_xwoba is not null then 0.5*postm_xwoba + 0.5*pobs_xwoba else postm_xwoba end
            else postm_xwoba
        end, 4) as eb_xwoba_against,

        -- eb_k_pct — E7.5p: the MLE κ-blend takes precedence for a COLD-START starter who has one
        -- (postm_k_mle already collapses to the MLE mean at BF=0 and to his own line as BF accrues).
        -- Everyone else keeps the incumbent band-prior path byte-for-byte. Note the MLE branch and the
        -- IL branch are mutually exclusive by construction: is_il needs ≥10 prior-season starts, which
        -- makes n_prior_seasons ≥ 1, which clears is_cold_start.
        round(case
            when mle_k_pct is not null then postm_k_mle
            when current_bf = 0 and not is_il then mu_k
            when is_il then case when pobs_k is not null then 0.5*postm_k + 0.5*pobs_k else postm_k end
            else postm_k
        end, 4) as eb_k_pct,

        -- eb_bb_pct — same structure as eb_k_pct
        round(case
            when mle_bb_pct is not null then postm_bb_mle
            when current_bf = 0 and not is_il then mu_bb
            when is_il then case when pobs_bb is not null then 0.5*postm_bb + 0.5*pobs_bb else postm_bb end
            else postm_bb
        end, 4) as eb_bb_pct,

        -- eb_gb_pct — E7.5p NEW column. Populated for EVERY starter: the MLE ground-ball line for a
        -- cold-start rookie, the prior-season league anchor otherwise, both shrunk toward the pitcher's
        -- own prior-season GB% by balls in play. NULL only when neither an MLE nor a league anchor
        -- exists (the fail-safe empty-view case in the earliest season) — hence no not_null test.
        round(postm_gb, 4) as eb_gb_pct,

        -- eb_xwoba_uncertainty (prior sigma in prior_only, else posterior std)
        round(case
            when current_bf = 0 and not is_il then sigma_xwoba
            else posts_xwoba
        end, 4) as eb_xwoba_uncertainty,

        -- Epic 16.2 sequential parallel column + provenance
        round(seq_mu, 4) as eb_xwoba_against_sequential,
        case
            when seq_mu is not null then 'sequential'
            when (current_bf = 0 and not is_il) then 'prior_only'
            else 'season_eb'
        end as posterior_source,
        case when seq_mu is not null then datediff('day', seq_game_date, game_date) end as prior_age_days,

        current_date()        as fit_date,
        '{{ invocation_id }}' as run_id
    from post_gb
)

-- ============================================================================
-- INC-19 DURABLE TYPE-PIN (2026-06-29) — see CLAUDE.md "type-contract guard".
-- Every FLOAT output column is cast to an explicit ::double so an upstream
-- NUMBER<->FLOAT migration (a lakehouse dual-branch flip) can NEVER drift this
-- incremental's stored column type again — the recurring HALT class that fired
-- 5x (INC-15 / W1d / INC-16-P0 / INC-19 / INC-19-recurrence). ::double (NOT
-- ::float = 32-bit in DuckDB) is value-preserving 64-bit; it ADOPTS the FLOAT
-- types the table already holds, so this is a no-op incremental (no type ALTER).
--
-- This pinned set is contract-checked by betting_ml/tests/test_type_contract_guard.py
-- against dbt/type_contracts/eb_starter_posteriors.types.json. If you ADD a column or
-- INTEND a type change, update BOTH this block AND that manifest in the SAME PR
-- (regenerate via scripts/gen_type_contract.py --write) or CI goes red. A new
-- numeric column that can ever be FLOAT MUST be ::double-pinned here.
-- NOTE: the explicit outer select is intentional — a column added to `final` but
-- not added here is DROPPED; the guard's set-equality check catches that too.
-- TYPE-PIN-START (generated; do not hand-edit individual lines)
select
    game_pk,
    side,
    pitcher_id,
    season,
    game_date,
    age_band,
    current_season_bf,
    current_season_starts,
    eb_data_source,
    eb_xwoba_against::double as eb_xwoba_against,
    eb_k_pct::double as eb_k_pct,
    eb_bb_pct::double as eb_bb_pct,
    eb_gb_pct::double as eb_gb_pct,
    eb_xwoba_uncertainty::double as eb_xwoba_uncertainty,
    eb_xwoba_against_sequential::double as eb_xwoba_against_sequential,
    posterior_source,
    prior_age_days,
    fit_date,
    run_id
from final
-- TYPE-PIN-END
{% else %}

-- E11.24 TARGET-6 SUCCESSOR (2026-08-08) — incremental MERGE → VIEW. This branch is a pure
-- ext-table COPY, and its MERGE was re-run on EVERY intraday lineup tick (lineup_dbt_feature_rebuild)
-- plus once in dbt_umpire_feature_rebuild. A MERGE RESUMES COMPUTE_WH; `create or replace view` is
-- metadata-only and never does. Measured on the clean 2026-08-07 tick band (14-23 UTC): this MERGE
-- and its eb_batter_posteriors_raw sibling were 6 of the 9 remaining waits.
--
-- SAFE ONLY BECAUSE THE READER REPOINT SHIPS WITH IT — this is the ordering that matters:
--   • Every dbt ref() to this model lives in the DuckDB branch of its consumer
--     (feature_pregame_starter_features), which on Snowflake reads its OWN ext table.
--   • betting_ml/scripts/sequential_bayes/update_player_posteriors.py was the one Snowflake
--     reader whose consumption spans the WHOLE accumulated history (the season-first-appearance
--     cold-start prior + the pitcher-role map). It now reads the S3 parquet under --s3
--     (W7A_LAKEHOUSE_S3=1, in env.required) — the PRECONDITION for this flip.
--   • The remaining Snowflake readers are date-scoped and a view serves them unchanged:
--     dbt/tests/assert_eb_starter_posteriors_covers_today.sql (WARN-tier, `game_date = current_date()`)
--     and scripts/predict_today.py's _FRESHNESS_QUERY.
--     ⚠️ CORRECTED 2026-08-09 — an earlier draft of this comment claimed _FRESHNESS_QUERY was
--     "already DEAD in prod (W8B_FRESHNESS_S3=1)". IT IS NOT. Measured on MONITOR_WH: that exact
--     shape executed on COMPUTE_WH on 08-02, 08-05, 08-08 and 08-09 (1×/day, 0 waits). The flag is
--     NOT in services/dagster/aws/env.required, and .env.example documents it as 0 — i.e. nothing
--     forces it on, and the observed traffic says it is off (this repo's "documented cutover ≠
--     actually set on the box" class; CLAUDE.md E11.20-COST). ⇒ treat the SF probe as LIVE.
--     THE FLIP IS SAFE ANYWAY, and for a reason that does not depend on the flag: the probe is
--     date-scoped AND ghost-immune. Its probe side `p` is today's CURRENT probables from
--     stg_statsapi_probable_pitchers; a ghost row here belongs to a SUPERSEDED probable, which is
--     by construction no longer in `p`, so it can never satisfy that LEFT JOIN. `starter_missing`
--     is therefore identical against the table and against the view.
--
-- ⚠️ NOT CONTENT-NEUTRAL, unlike the target-6 view flips — and that is the POINT. A `merge`
-- incremental never DELETES, so the table was an ACCUMULATING SUPERSET carrying rows for
-- probable-starter snapshots a later rebuild superseded (#662 measured +3). A view returns exactly
-- the current rebuild. It can only DROP superseded rows, never add anything.
--
-- 🧭 PM DESIGN CALL (deliberate): a VIEW, not `enabled=false`. Once nothing on Snowflake reads a
-- model, `enabled=false` is the cleaner end state — it deletes the object rather than leaving a
-- shell. It is NOT taken here because two Snowflake readers above still resolve this name, and a
-- disabled model makes `ref()` unresolvable and DROPs nothing (the relation lingers, stale, as a
-- table nobody rebuilds — the silent-staleness bomb this program keeps paying for). The view is
-- the ESTABLISHED shape for this exact case on this target (stg_statsapi_games,
-- stg_statsapi_probable_pitchers, mart_odds_outcomes, mart_game_odds_bridge, and the four
-- target-6 / #662 pregame models). `enabled=false` becomes correct only after those two readers
-- are themselves repointed — a separate story, not a rider on a serving flip.
{{ config(materialized='view') }}

select * from baseball_data.lakehouse_ext.eb_starter_posteriors

{% endif %}
