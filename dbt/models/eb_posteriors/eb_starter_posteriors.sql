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
        end as age_band
    from starters s
    left join prior_seasons ps
      on ps.pitcher_id = s.pitcher_id and ps.season = s.season
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
        (coalesce(cs.starts, 0) < 3 and coalesce(pr.prior_starts, 0) >= 10) as is_il
    from starter_band sb
    left join current_stats cs on cs.game_pk = sb.game_pk and cs.pitcher_id = sb.pitcher_id
    left join prior_stats   pr on pr.game_pk = sb.game_pk and pr.pitcher_id = sb.pitcher_id
    left join prior_cells   pc on pc.game_pk = sb.game_pk and pc.pitcher_id = sb.pitcher_id
    left join seq           sq on sq.game_pk = sb.game_pk and sq.pitcher_id = sb.pitcher_id
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
        else mu_bb end as postm_bb
    from calc c
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

        -- eb_k_pct
        round(case
            when current_bf = 0 and not is_il then mu_k
            when is_il then case when pobs_k is not null then 0.5*postm_k + 0.5*pobs_k else postm_k end
            else postm_k
        end, 4) as eb_k_pct,

        -- eb_bb_pct
        round(case
            when current_bf = 0 and not is_il then mu_bb
            when is_il then case when pobs_bb is not null then 0.5*postm_bb + 0.5*pobs_bb else postm_bb end
            else postm_bb
        end, 4) as eb_bb_pct,

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
    from post
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
    eb_xwoba_uncertainty::double as eb_xwoba_uncertainty,
    eb_xwoba_against_sequential::double as eb_xwoba_against_sequential,
    posterior_source,
    prior_age_days,
    fit_date,
    run_id
from final
-- TYPE-PIN-END
{% else %}

{{ config(materialized='incremental', unique_key=['game_pk', 'pitcher_id'], incremental_strategy='merge') }}

select * from baseball_data.lakehouse_ext.eb_starter_posteriors
{% if is_incremental() %}
  where game_date >= dateadd('day', -7, current_date())
{% endif %}

{% endif %}
