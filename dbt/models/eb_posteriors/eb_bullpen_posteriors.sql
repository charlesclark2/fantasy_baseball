-- =============================================================================
-- eb_bullpen_posteriors_dbt.sql  —  Story A2.11
-- Grain: one row per (game_pk, pitcher_id) for relievers who appeared in a game.
--
-- Replaces compute_bullpen_posteriors.py (individual grain). Normal-Normal EB
-- shrinkage of season-to-date xwOBA-against / K% / BB% toward (leverage_role ×
-- age_band) priors. Retrospective: the reliever set = who actually pitched in
-- relief (from stg_batter_pitches), so there is NO future-game spine (unlike
-- starter). Pure cost cleanup + train/serve-skew removal.
--
-- leverage_role from prior-season (season-1) aLI; role_changed from full
-- current-season aLI (matches the BACKFILL path — see int_bullpen_ali_by_season).
-- LEAKAGE GUARD: season-to-date stats sum only the pitcher's prior games
-- (pl.game_date < this game's date) in the same season.
-- eb_data_source: prior_only (bf=0 or no prior cell) | full_eb.
-- =============================================================================

-- Story A2.11: incremental (merge on grain). In incremental runs the pitch scan is
-- limited to current+prior season (game_pitches) so season-to-date is still complete
-- for the recent games, and the OUTPUT spine (game_relievers) is scoped to the recent
-- window — the as-of season-to-date join therefore only computes for recent games.

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

with game_pitches as (
    select
        bp.game_pk,
        bp.game_date::date as game_date,
        bp.game_year       as season,
        bp.at_bat_number,
        bp.pitcher_id,
        case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end as pitching_team,
        bp.plate_appearance_event,
        bp.xwoba, bp.woba_value, bp.woba_denom, bp.pitcher_age
    from stg_batter_pitches bp
    where bp.game_type = 'R'
      and bp.game_year between 2016 and year(current_date())
    {% if is_incremental() %}
      -- current+prior season covers any recent game's full season-to-date
      and bp.game_year >= year(current_date()) - 1
    {% endif %}
),

game_starters as (
    select game_pk, pitcher_id, pitching_team
    from mart_starting_pitcher_game_log
),

reliever_pitches as (
    select gp.*
    from game_pitches gp
    left join game_starters s
      on  s.game_pk = gp.game_pk and s.pitcher_id = gp.pitcher_id and s.pitching_team = gp.pitching_team
    where s.pitcher_id is null
),

-- PA-level rollup (mirrors the Python pa_level CTE)
pa_level as (
    select
        pitcher_id, game_pk, game_date, season, pitching_team, at_bat_number,
        any_value(pitcher_age) as pitcher_age,
        max(case when plate_appearance_event in ('strikeout','strikeout_double_play') then 1 else 0 end) as is_strikeout,
        max(case when plate_appearance_event in ('walk','intent_walk') then 1 else 0 end) as is_walk,
        max(coalesce(woba_denom, 0)) as woba_denom,
        sum(case when woba_denom = 1 then coalesce(xwoba, woba_value) else 0 end) as xwoba_num,
        max(case when plate_appearance_event in (
            'strikeout','strikeout_double_play','field_out','force_out',
            'grounded_into_double_play','double_play','triple_play',
            'sac_fly','sac_fly_double_play','sac_bunt','sac_bunt_double_play',
            'fielders_choice_out','caught_stealing_2b','caught_stealing_3b','caught_stealing_home',
            'pickoff_1b','pickoff_2b','pickoff_3b','other_out'
        ) then 1 else 0 end) as is_out
    from reliever_pitches
    group by pitcher_id, game_pk, game_date, season, pitching_team, at_bat_number
),

-- The reliever set + in-game metadata (pitching_team, outs, age)
game_relievers as (
    select
        pitcher_id::varchar as pitcher_id, game_pk::varchar as game_pk,
        game_date, season, pitching_team,
        sum(is_out)        as outs_recorded,
        mode(pitcher_age)  as mode_age
    from pa_level
    {% if is_incremental() %}
      -- output spine scoped to recent games; pitcher_game_lines (below) stays full
      -- season so the as-of season-to-date sum remains complete
      where game_date >= (select dateadd('day', -7, max(game_date)) from {{ this }})
    {% endif %}
    group by pitcher_id, game_pk, game_date, season, pitching_team
),

-- Per (pitcher, game) stat line, then as-of season-to-date sum (strict prior games)
pitcher_game_lines as (
    select
        pitcher_id::varchar as pitcher_id, season, game_date,
        count(*)            as bf,
        sum(is_strikeout)   as k,
        sum(is_walk)        as bb,
        sum(xwoba_num)      as xwoba_num,
        sum(woba_denom)     as xwoba_den
    from pa_level
    group by pitcher_id, season, game_date
),

season_to_date as (
    select
        gr.game_pk, gr.pitcher_id,
        coalesce(sum(pl.bf), 0)        as bf,
        coalesce(sum(pl.k), 0)         as strikeouts,
        coalesce(sum(pl.bb), 0)        as walks,
        coalesce(sum(pl.xwoba_num), 0) as xwoba_numerator,
        coalesce(sum(pl.xwoba_den), 0) as xwoba_denom
    from game_relievers gr
    left join pitcher_game_lines pl
      on  pl.pitcher_id = gr.pitcher_id
      and pl.season     = gr.season
      and pl.game_date  < gr.game_date          -- LEAKAGE GUARD
    group by gr.game_pk, gr.pitcher_id
),

ali as (select season, pitcher_id, normalized_ali from int_bullpen_ali_by_season),

-- Roles + age band + season-to-date assembled per reliever-game
band_assigned as (
    select
        gr.game_pk, gr.pitcher_id, gr.game_date, gr.season, gr.pitching_team,
        coalesce(gr.outs_recorded, 0) as outs_in_game,
        std.bf, std.strikeouts, std.walks, std.xwoba_numerator, std.xwoba_denom,
        -- leverage_role from prior-season (season-1) aLI
        case
            when pa.normalized_ali is null then 'no_prior_season'
            when pa.normalized_ali >= 1.5 then 'closer_tier'
            when pa.normalized_ali >= 1.0 then 'high_leverage'
            else 'low_leverage'
        end as leverage_role,
        ca.normalized_ali as current_ali,
        case
            when gr.mode_age is null then null
            when floor(gr.mode_age) < 26 then 'lt_26'
            when floor(gr.mode_age) <= 30 then '26_30'
            when floor(gr.mode_age) <= 34 then '31_34'
            else 'gte_35'
        end as age_band
    from game_relievers gr
    left join season_to_date std on std.game_pk = gr.game_pk and std.pitcher_id = gr.pitcher_id
    left join ali pa on pa.pitcher_id = gr.pitcher_id and pa.season = gr.season - 1
    left join ali ca on ca.pitcher_id = gr.pitcher_id and ca.season = gr.season
),

-- Prior cells with age-band fallback (lowest band_rank per season×metric×role), per metric
priors_long as (
    select season, metric, role, age_band, band_rank, mu, sigma
    from ref_eb_bullpen_priors
),
priors_fb as (
    select season, metric, role, mu, sigma
    from (
        select season, metric, role, mu, sigma,
               row_number() over (partition by season, metric, role order by band_rank) as rn
        from priors_long
    ) where rn = 1
),
reliever_metric as (
    select
        b.game_pk, b.pitcher_id, m.metric,
        coalesce(ex.mu,    fb.mu)    as mu0,
        coalesce(ex.sigma, fb.sigma) as sigma0
    from band_assigned b
    cross join (values ('xwoba_against'), ('k_pct'), ('bb_pct')) as m(metric)
    left join priors_long ex
      on ex.season = b.season and ex.metric = m.metric and ex.role = b.leverage_role and ex.age_band = b.age_band
    left join priors_fb fb
      on fb.season = b.season and fb.metric = m.metric and fb.role = b.leverage_role
),
reliever_cells as (
    select
        game_pk, pitcher_id,
        max(case when metric='xwoba_against' then mu0    end) as mu_xw,
        max(case when metric='xwoba_against' then sigma0 end) as sigma_xw,
        max(case when metric='k_pct'         then mu0    end) as mu_k,
        max(case when metric='k_pct'         then sigma0 end) as sigma_k,
        max(case when metric='bb_pct'        then mu0    end) as mu_bb,
        max(case when metric='bb_pct'        then sigma0 end) as sigma_bb
    from reliever_metric
    group by game_pk, pitcher_id
),

calc as (
    select
        b.*,
        c.mu_xw, c.sigma_xw,
        coalesce(c.mu_k,  c.mu_xw)    as mu_k_eff,   -- Python: (cell_k or cell_xw)
        coalesce(c.sigma_k,  c.sigma_xw) as sigma_k_eff,
        coalesce(c.mu_bb, c.mu_xw)    as mu_bb_eff,
        coalesce(c.sigma_bb, c.sigma_xw) as sigma_bb_eff,
        -- observed season-to-date rates
        case when b.xwoba_denom > 0 then b.xwoba_numerator / b.xwoba_denom end as xwoba_obs,
        case when b.bf > 0 then b.strikeouts / b.bf end as k_obs,
        case when b.bf > 0 then b.walks / b.bf end as bb_obs,
        -- role_changed
        case
            when b.leverage_role = 'no_prior_season' or b.current_ali is null then false
            else abs(
                (case b.leverage_role when 'closer_tier' then 2 when 'high_leverage' then 1 when 'low_leverage' then 0 end)
                - (case when b.current_ali >= 1.5 then 2 when b.current_ali >= 1.0 then 1 else 0 end)
            ) > 1
        end as role_changed
    from band_assigned b
    left join reliever_cells c on c.game_pk = b.game_pk and c.pitcher_id = b.pitcher_id
),

final as (
    select
        game_pk,
        pitcher_id,
        game_date,
        season,
        pitching_team,
        leverage_role,
        age_band,
        outs_in_game,
        case when bf = 0 or mu_xw is null then 0 else bf::integer end as current_season_bf,
        case when bf = 0 or mu_xw is null then 'prior_only' else 'full_eb' end as eb_data_source,
        role_changed,

        -- EB posteriors (obs = actual rate, falling back to the prior mean → posterior = μ₀)
        round(case
            when bf = 0 or mu_xw is null then mu_xw
            else _eb.mean_xw
        end, 4) as eb_xwoba_against,
        round(case
            when bf = 0 or mu_xw is null then mu_k_eff
            else _eb.mean_k
        end, 4) as eb_k_pct,
        round(case
            when bf = 0 or mu_xw is null then mu_bb_eff
            else _eb.mean_bb
        end, 4) as eb_bb_pct,
        round(case
            when bf = 0 or mu_xw is null then sigma_xw
            else _eb.std_xw
        end, 4) as eb_xwoba_uncertainty,

        current_date()        as fit_date,
        '{{ invocation_id }}' as run_id
    from calc,
    lateral (
        select
            -- xwOBA: obs_used = coalesce(xwoba_obs, mu_xw)
            (mu_xw*(1.0/(sigma_xw*sigma_xw)) + coalesce(xwoba_obs, mu_xw)*(bf/greatest(coalesce(xwoba_obs, mu_xw)*(1-coalesce(xwoba_obs, mu_xw)), 0.0001)))
              / ((1.0/(sigma_xw*sigma_xw)) + (bf/greatest(coalesce(xwoba_obs, mu_xw)*(1-coalesce(xwoba_obs, mu_xw)), 0.0001))) as mean_xw,
            sqrt(1.0 / ((1.0/(sigma_xw*sigma_xw)) + (bf/greatest(coalesce(xwoba_obs, mu_xw)*(1-coalesce(xwoba_obs, mu_xw)), 0.0001)))) as std_xw,
            (mu_k_eff*(1.0/(sigma_k_eff*sigma_k_eff)) + coalesce(k_obs, mu_k_eff)*(bf/greatest(coalesce(k_obs, mu_k_eff)*(1-coalesce(k_obs, mu_k_eff)), 0.0001)))
              / ((1.0/(sigma_k_eff*sigma_k_eff)) + (bf/greatest(coalesce(k_obs, mu_k_eff)*(1-coalesce(k_obs, mu_k_eff)), 0.0001))) as mean_k,
            (mu_bb_eff*(1.0/(sigma_bb_eff*sigma_bb_eff)) + coalesce(bb_obs, mu_bb_eff)*(bf/greatest(coalesce(bb_obs, mu_bb_eff)*(1-coalesce(bb_obs, mu_bb_eff)), 0.0001)))
              / ((1.0/(sigma_bb_eff*sigma_bb_eff)) + (bf/greatest(coalesce(bb_obs, mu_bb_eff)*(1-coalesce(bb_obs, mu_bb_eff)), 0.0001))) as mean_bb
    ) _eb
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
-- against dbt/type_contracts/eb_bullpen_posteriors.types.json. If you ADD a column or
-- INTEND a type change, update BOTH this block AND that manifest in the SAME PR
-- (regenerate via scripts/gen_type_contract.py --write) or CI goes red. A new
-- numeric column that can ever be FLOAT MUST be ::double-pinned here.
-- NOTE: the explicit outer select is intentional — a column added to `final` but
-- not added here is DROPPED; the guard's set-equality check catches that too.
-- TYPE-PIN-START (generated; do not hand-edit individual lines)
select
    game_pk,
    pitcher_id,
    game_date,
    season,
    pitching_team,
    leverage_role,
    age_band,
    outs_in_game,
    current_season_bf,
    eb_data_source,
    role_changed,
    eb_xwoba_against::double as eb_xwoba_against,
    eb_k_pct::double as eb_k_pct,
    eb_bb_pct::double as eb_bb_pct,
    eb_xwoba_uncertainty::double as eb_xwoba_uncertainty,
    fit_date,
    run_id
from final
-- TYPE-PIN-END
{% else %}

{{ config(materialized='incremental', unique_key=['game_pk', 'pitcher_id'], incremental_strategy='merge') }}

select * from baseball_data.lakehouse_ext.eb_bullpen_posteriors
{% if is_incremental() %}
  where game_date >= (select dateadd('day', -7, max(game_date)) from {{ this }})
{% endif %}

{% endif %}
