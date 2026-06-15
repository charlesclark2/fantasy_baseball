-- =============================================================================
-- eb_batter_posteriors_raw_dbt.sql  —  Story A2.11
-- Grain: one row per (game_pk, batting_slot, batter_id) for confirmed lineups.
--
-- Replaces compute_lineup_posteriors.py. Beta-Binomial EB for wOBA/K%/BB% and
-- Normal-Normal for ISO, blended with ZiPS at low PA, plus the Epic-16.2 as-of
-- sequential wOBA column.
--
-- NOTE vs starter: sourced from stg_statsapi_lineups (CONFIRMED lineups), which
-- only exist ~3h pre-game — so there is NO future-game spine benefit here (unlike
-- the starter residual fix). This migration is pure cost cleanup + train/serve
-- skew removal.
--
-- ZiPS DRIFT (validation caveat): the ZiPS join takes the LATEST snapshot by
-- ingestion_ts, which may differ from the snapshot the Python used when it wrote
-- the table. Expect byte-for-byte diffs concentrated on zips_blend rows; full_eb
-- rows (ZiPS-independent) must match exactly. Pin/segment ZiPS in validation.
--
-- Beta-Binomial: post_mean=(α+obs·PA)/(α+β+PA); prior_mean=α/(α+β);
--   post_std=sqrt(a·b/(n²(n+1))) with a=α+obs·PA, b=β+(PA−obs·PA), n=α+β+PA.
-- Normal (ISO): σ_meas²=max(obs(1-obs),1e-3)/PA; standard precision-weighted mean.
-- ZiPS blend: w=min(PA/150,1); final=w·eb+(1-w)·zips when 0<w<1 and zips present.
-- eb_data_source (from the wOBA metric): prior_only | zips_blend | full_eb.
-- =============================================================================

-- No custom schema → target.schema (betting), matching the Python table.
-- Story A2.11: incremental (merge on grain) — daily rebuild recomputes only recent
-- games; rolling_asof still reads full mart for those games (values exact).
{{ config(materialized='incremental', unique_key=['game_pk', 'batting_slot', 'batter_id'], incremental_strategy='merge') }}

with lineups as (
    select
        game_pk::varchar               as game_pk,
        batting_order::integer         as batting_slot,
        player_id::varchar             as batter_id,
        official_date::date            as game_date,
        year(official_date)            as season,
        case when batting_order <= 3 then 'top'
             when batting_order <= 6 then 'middle'
             else 'bottom' end         as role
    from {{ ref('stg_statsapi_lineups') }}
    where batting_order between 1 and 9
      and year(official_date) between 2015 and year(current_date())
    {% if is_incremental %}
      and official_date >= (select dateadd('day', -7, max(game_date)) from {{ this }})
    {% endif %}
),

-- Latest cumulative-season rolling row per batter strictly before the game
rolling_asof as (
    select
        l.game_pk, l.batter_id,
        r.woba_std       as obs_woba,
        r.k_pct_std      as obs_k,
        r.bb_pct_std     as obs_bb,
        r.iso_std        as obs_iso,
        coalesce(r.pa_count_std, 0) as pa,
        coalesce(r.batter_hand, 'R') as hand
    from lineups l
    join {{ ref('mart_batter_rolling_stats') }} r
      on  r.batter_id  = l.batter_id
      and r.game_year  = l.season
      and r.game_date::date < l.game_date          -- LEAKAGE GUARD
    qualify row_number() over (
        partition by l.game_pk, l.batter_id order by r.game_date desc
    ) = 1
),

-- Latest ZiPS DC projection per batter-season (ingestion_ts drift caveat above)
zips as (
    select
        mlbam_batter_id::varchar as batter_id, season,
        proj_woba, proj_k_pct, proj_bb_pct, proj_iso
    from {{ ref('stg_fangraphs__zips_hitting') }}
    where projection_type = 'zips'
    qualify row_number() over (
        partition by mlbam_batter_id, season order by ingestion_ts desc
    ) = 1
),

-- Priors pivoted to one row per (season, role, hand)
priors_wide as (
    select season, role, batter_hand,
        max(case when metric='woba'   then alpha end) as woba_alpha,
        max(case when metric='woba'   then beta  end) as woba_beta,
        max(case when metric='k_pct'  then alpha end) as k_alpha,
        max(case when metric='k_pct'  then beta  end) as k_beta,
        max(case when metric='bb_pct' then alpha end) as bb_alpha,
        max(case when metric='bb_pct' then beta  end) as bb_beta,
        max(case when metric='iso'    then mu    end) as iso_mu,
        max(case when metric='iso'    then sigma end) as iso_sigma
    from {{ ref('ref_eb_lineup_priors') }}
    group by season, role, batter_hand
),

-- Epic 16.2 as-of sequential wOBA posterior (player_type=batter, metric=xwoba)
seq as (
    select l.game_pk, l.batter_id, sp.posterior_mu, sp.game_date as seq_game_date
    from lineups l
    join baseball_data.betting.player_sequential_posteriors sp
      on  sp.player_id::varchar = l.batter_id
      and sp.player_type = 'batter'
      and sp.metric      = 'xwoba'
      and sp.season      = l.season
      and sp.game_date   < l.game_date
    qualify row_number() over (
        partition by l.game_pk, l.batter_id order by sp.game_date desc
    ) = 1
),

assembled as (
    select
        l.game_pk, l.batting_slot, l.batter_id, l.season, l.game_date, l.role,
        coalesce(ra.pa, 0) as pa,
        coalesce(ra.hand, 'R') as hand,
        ra.obs_woba, ra.obs_k, ra.obs_bb, ra.obs_iso,
        z.proj_woba, z.proj_k_pct, z.proj_bb_pct, z.proj_iso,
        -- prior cells with hand→R fallback
        coalesce(pw.woba_alpha, pr.woba_alpha) as woba_alpha,
        coalesce(pw.woba_beta,  pr.woba_beta)  as woba_beta,
        coalesce(pw.k_alpha,    pr.k_alpha)    as k_alpha,
        coalesce(pw.k_beta,     pr.k_beta)     as k_beta,
        coalesce(pw.bb_alpha,   pr.bb_alpha)   as bb_alpha,
        coalesce(pw.bb_beta,    pr.bb_beta)    as bb_beta,
        coalesce(pw.iso_mu,     pr.iso_mu)     as iso_mu,
        coalesce(pw.iso_sigma,  pr.iso_sigma)  as iso_sigma,
        sq.posterior_mu as seq_mu, sq.seq_game_date
    from lineups l
    left join rolling_asof ra on ra.game_pk = l.game_pk and ra.batter_id = l.batter_id
    left join zips z          on z.batter_id = l.batter_id and z.season = l.season
    left join priors_wide pw  on pw.season = l.season and pw.role = l.role and pw.batter_hand = coalesce(ra.hand, 'R')
    left join priors_wide pr  on pr.season = l.season and pr.role = l.role and pr.batter_hand = 'R'
    left join seq sq          on sq.game_pk = l.game_pk and sq.batter_id = l.batter_id
),

calc as (
    select
        a.*,
        least(pa / 150.0, 1.0) as eb_weight,
        -- prior means
        woba_alpha / nullif(woba_alpha + woba_beta, 0) as pm_woba,
        k_alpha    / nullif(k_alpha + k_beta, 0)       as pm_k,
        bb_alpha   / nullif(bb_alpha + bb_beta, 0)     as pm_bb,
        iso_mu                                         as pm_iso,
        -- EB posteriors (guarded so the iso division never sees pa=0)
        case when obs_woba is not null then (woba_alpha + obs_woba*pa)/(woba_alpha + woba_beta + pa) end as eb_woba_raw,
        case when obs_k    is not null then (k_alpha    + obs_k*pa)   /(k_alpha + k_beta + pa)       end as eb_k_raw,
        case when obs_bb   is not null then (bb_alpha   + obs_bb*pa)  /(bb_alpha + bb_beta + pa)     end as eb_bb_raw,
        case when pa > 0 and obs_iso is not null then
            (iso_mu*(1.0/(iso_sigma*iso_sigma)) + obs_iso*(pa/greatest(obs_iso*(1-obs_iso), 0.001)))
            / ((1.0/(iso_sigma*iso_sigma)) + (pa/greatest(obs_iso*(1-obs_iso), 0.001)))
        end as eb_iso_raw
    from assembled a
),

final as (
    select
        game_pk,
        batting_slot,
        batter_id,
        season,
        game_date,

        -- eb_data_source from the wOBA metric
        case
            when woba_alpha is null then 'prior_only'
            when (pa = 0 or obs_woba is null) then (case when proj_woba is not null then 'zips_blend' else 'prior_only' end)
            when eb_weight >= 1.0 then 'full_eb'
            when proj_woba is not null then 'zips_blend'
            else 'full_eb'
        end as eb_data_source,

        round(case
            when woba_alpha is null then null
            when (pa = 0 or obs_woba is null) then coalesce(proj_woba, pm_woba)
            when eb_weight >= 1.0 then eb_woba_raw
            when proj_woba is not null then eb_weight*eb_woba_raw + (1-eb_weight)*proj_woba
            else eb_woba_raw
        end, 4) as eb_woba,

        round(case
            when k_alpha is null then null
            when (pa = 0 or obs_k is null) then coalesce(proj_k_pct, pm_k)
            when eb_weight >= 1.0 then eb_k_raw
            when proj_k_pct is not null then eb_weight*eb_k_raw + (1-eb_weight)*proj_k_pct
            else eb_k_raw
        end, 4) as eb_k_pct,

        round(case
            when bb_alpha is null then null
            when (pa = 0 or obs_bb is null) then coalesce(proj_bb_pct, pm_bb)
            when eb_weight >= 1.0 then eb_bb_raw
            when proj_bb_pct is not null then eb_weight*eb_bb_raw + (1-eb_weight)*proj_bb_pct
            else eb_bb_raw
        end, 4) as eb_bb_pct,

        round(case
            when iso_mu is null then null
            when (pa = 0 or obs_iso is null) then coalesce(proj_iso, pm_iso)
            when eb_weight >= 1.0 then eb_iso_raw
            when proj_iso is not null then eb_weight*eb_iso_raw + (1-eb_weight)*proj_iso
            else eb_iso_raw
        end, 4) as eb_iso,

        -- wOBA uncertainty: Beta-Binomial posterior std (or prior std at PA=0)
        round(case
            when woba_alpha is null then null
            when pa > 0 and obs_woba is not null then
                sqrt( (woba_alpha + obs_woba*pa) * (woba_beta + (pa - obs_woba*pa))
                      / (power(woba_alpha + woba_beta + pa, 2) * (woba_alpha + woba_beta + pa + 1)) )
            else
                sqrt( woba_alpha * woba_beta
                      / (power(woba_alpha + woba_beta, 2) * (woba_alpha + woba_beta + 1)) )
        end, 4) as eb_woba_uncertainty,

        round(least(pa / 150.0, 1.0), 4) as pa_weight,

        -- Epic 16.2 sequential parallel column + provenance
        round(seq_mu, 4) as eb_woba_sequential,
        case
            when seq_mu is not null then 'sequential'
            when (woba_alpha is null
                  or (pa = 0 or obs_woba is null) and proj_woba is null) then 'prior_only'
            else 'season_eb'
        end as posterior_source,
        case when seq_mu is not null then datediff('day', seq_game_date, game_date) end as prior_age_days,

        current_date()        as fit_date,
        '{{ invocation_id }}' as run_id
    from calc
)

select * from final
