-- =============================================================================
-- eb_bullpen_team_posteriors_dbt.sql  —  Story A2.11
-- Grain: one row per (game_pk, team) — outs-weighted bullpen aggregate.
--
-- Replaces compute_bullpen_posteriors._aggregate_to_team. Outs-in-game weighted
-- average of the per-reliever EB xwOBA / uncertainty. When a team's total outs
-- are 0, all relievers are weighted equally (mirrors the Python fallback).
-- =============================================================================

-- Story A2.11: incremental (merge on grain), scoped to recent games to match the
-- per-reliever model's daily window.
{{ config(materialized='incremental', unique_key=['game_pk', 'team'], incremental_strategy='merge') }}

with base as (
    select * from {{ ref('eb_bullpen_posteriors') }}
    {% if is_incremental %}
    where game_date >= (select dateadd('day', -7, max(game_date)) from {{ this }})
    {% endif %}
),

team_outs as (
    select game_pk, pitching_team, sum(outs_in_game) as total_outs
    from base
    group by game_pk, pitching_team
),

weighted as (
    select
        b.game_pk,
        b.pitching_team as team,
        b.game_date,
        b.season,
        case when t.total_outs > 0 then b.outs_in_game else 1 end as w,
        b.eb_xwoba_against,
        b.eb_xwoba_uncertainty,
        b.eb_data_source
    from base b
    join team_outs t on t.game_pk = b.game_pk and t.pitching_team = b.pitching_team
)

select
    game_pk,
    any_value(game_date) as game_date,
    any_value(season)    as season,
    team,
    round(sum(case when eb_xwoba_against is not null then w * eb_xwoba_against end)
          / nullif(sum(case when eb_xwoba_against is not null then w end), 0), 4) as team_eb_bullpen_xwoba,
    round(sum(case when eb_xwoba_uncertainty is not null then w * eb_xwoba_uncertainty end)
          / nullif(sum(case when eb_xwoba_uncertainty is not null then w end), 0), 4) as team_eb_bullpen_uncertainty,
    count(*)                                                  as n_relievers,
    sum(case when eb_data_source = 'prior_only' then 1 else 0 end) as n_prior_only,
    current_date()        as fit_date,
    '{{ invocation_id }}' as run_id
from weighted
group by game_pk, team
