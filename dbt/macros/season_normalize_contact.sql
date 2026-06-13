-- =============================================================================
-- season_normalize_contact.sql  (Story 27.7)
--
-- Shared machinery for season-normalizing the contact-quality feature family.
--
-- WHY: the totals 2025 over-bias (+0.67) is a REAL contact->runs CONVERSION
-- regime — 2025 contact got harder (hard-hit% +1.6pts, K% down, xwOBA up) but
-- league runs stayed flat (a ball-carry/drag change). So the contact-quality
-- feature LEVEL inflated without more runs, and the models read that level as
-- "more scoring." Re-centering each contact feature to its own season league
-- distribution (a within-season z-score) removes the spurious level shift while
-- preserving within-season relative skill. Validated offline in
-- betting_ml/scripts/regime/totals_season_norm_fix.py (pooled bias +0.367 -> +0.111).
--
-- LEAKAGE: the offline prototype z-scored against each season's FULL mean/std —
-- valid only to prove the mechanism. Production uses a STRICTLY-PRIOR, AS-OF
-- current-season league baseline (no same-day or future games), shrunk toward
-- the PRIOR season's full stats early so live serving has a baseline before the
-- season accrues (same as-of + prior-anchor methodology as the Task-1 league
-- run-environment monitor, run_env_regime_monitor.py). Detection lag early in a
-- season (~2 wks per the monitor) means a fresh regime is reflected with a lag —
-- documented, accepted.
--
-- SINGLE SOURCE OF TRUTH: `contact_quality_columns()` is the canonical 34-name
-- list (matches the validated _CONTACT_RE set in the prototype). It is consumed
-- by feature_league_contact_baseline (stats) and feature_pregame_game_features
-- (application) so the two can never drift.
-- =============================================================================

{% macro contact_quality_columns() %}
    {{ return([
        'home_bp_eb_xwoba',
        'away_bp_eb_xwoba',
        'away_pit_xwoba_against_30d',
        'home_lineup_avg_xwoba_vs_cluster',
        'away_starter_xwoba_against_std',
        'away_xwoba_with_runners_on_30d',
        'away_off_hard_hit_pct_std',
        'home_starter_xwoba_against_30d',
        'home_starter_xwoba_against_7d',
        'away_vs_lhp_xwoba_30d',
        'home_off_xwoba_30d',
        'away_xwoba_with_risp_30d',
        'home_lineup_vs_away_starter_xwoba_adj',
        'home_bp_xwoba_against_30d',
        'home_pit_xwoba_against_7d',
        'away_lineup_vs_home_starter_xwoba_adj',
        'home_off_barrel_pct_30d',
        'away_off_hard_hit_pct_7d',
        'home_pit_hard_hit_pct_30d',
        'home_pit_hard_hit_pct_7d',
        'home_bp_xwoba_against_14d',
        'home_pit_barrel_pct_30d',
        'away_starter_eb_xwoba_uncertainty',
        'home_starter_xwoba_7d_minus_std',
        'home_bp_hard_hit_pct_14d',
        'home_bp_hard_hit_pct_30d',
        'away_starter_hard_hit_pct_std',
        'away_starter_xwoba_vs_lhb',
        'home_starter_barrel_pct_std',
        'away_starter_hard_hit_pct_7d',
        'home_team_sequential_bullpen_xwoba',
        'away_team_sequential_bullpen_xwoba',
        'home_starter_eb_xwoba_against_sequential',
        'away_starter_eb_xwoba_against_sequential'
    ]) }}
{% endmacro %}


-- -----------------------------------------------------------------------------
-- as_of_contact_baseline(upstream_ref)
--
-- Emits the full SQL for feature_league_contact_baseline: one row per
-- (game_year, game_date) carrying, for every contact-quality column, the
-- strictly-prior AS-OF league mean (`<col>__mu`) and std (`<col>__sd`),
-- shrunk toward the prior season's full-season stats with pseudo-count K
-- (var `contact_baseline_shrinkage_k`, default 200 ~= first ~3 weeks anchored
-- to the prior season, then the current season takes over).
--
--   mu = (cn*mu_asof + K*mu_prior) / (cn + K)
--   sd = (cn*sd_asof + K*sd_prior) / (cn + K)
-- where (mu_asof, sd_asof) are computed over all STRICTLY-PRIOR game_dates in
-- the same season (window frame excludes the current date -> no same-day leak),
-- and (mu_prior, sd_prior) is the PRIOR season's full-season league stat. The
-- earliest season (no prior) falls back to its OWN season-full stat — a minor,
-- documented in-sample touch limited to 2021, which is never a live-serve season.
-- -----------------------------------------------------------------------------
{% macro as_of_contact_baseline(upstream_ref) %}
    {%- set cc = contact_quality_columns() -%}
    {%- set K = var('contact_baseline_shrinkage_k', 200) -%}
    with daily as (
        -- league daily moments per contact column (count / sum / sum-of-squares)
        select
            game_year,
            game_date,
            {%- for c in cc %}
            count({{ c }})            as n__{{ c }},
            sum({{ c }})              as s__{{ c }},
            sum({{ c }} * {{ c }})    as ss__{{ c }}{{ "," if not loop.last }}
            {%- endfor %}
        from {{ upstream_ref }}
        group by game_year, game_date
    ),
    asof_cum as (
        -- cumulative over STRICTLY-PRIOR dates in the season (frame excludes today).
        -- (NOT named `asof` — ASOF is a reserved keyword in Snowflake.)
        -- Window spec is inlined (not a named WINDOW clause) for parser portability.
        {%- set wframe = "over (partition by game_year order by game_date rows between unbounded preceding and 1 preceding)" %}
        select
            game_year,
            game_date,
            {%- for c in cc %}
            sum(n__{{ c }})  {{ wframe }} as cn__{{ c }},
            sum(s__{{ c }})  {{ wframe }} as cs__{{ c }},
            sum(ss__{{ c }}) {{ wframe }} as css__{{ c }}{{ "," if not loop.last }}
            {%- endfor %}
        from daily
    ),
    season_full as (
        -- full-season league mean/std per column (becomes the NEXT season's anchor)
        select
            game_year,
            {%- for c in cc %}
            avg({{ c }})                          as fmu__{{ c }},
            coalesce(stddev_samp({{ c }}), 0)     as fsd__{{ c }}{{ "," if not loop.last }}
            {%- endfor %}
        from {{ upstream_ref }}
        group by game_year
    ),
    prior as (
        -- shift each season's full stats forward one year -> prior-season anchor
        select
            game_year + 1 as game_year,
            {%- for c in cc %}
            fmu__{{ c }} as pmu__{{ c }},
            fsd__{{ c }} as psd__{{ c }}{{ "," if not loop.last }}
            {%- endfor %}
        from season_full
    )
    select
        a.game_year,
        a.game_date,
        -- min as-of count across columns: 0/NULL on the first game_date of a season
        -- (used by the leakage assertion test)
        least(
            {%- for c in cc %}
            coalesce(a.cn__{{ c }}, 0){{ "," if not loop.last }}
            {%- endfor %}
        ) as n_asof_min,
        {%- for c in cc %}
        (
            coalesce(a.cn__{{ c }}, 0) * (a.cs__{{ c }} / nullif(a.cn__{{ c }}, 0))
            + {{ K }} * coalesce(pr.pmu__{{ c }}, sf.fmu__{{ c }})
        ) / (coalesce(a.cn__{{ c }}, 0) + {{ K }}) as {{ c }}__mu,
        (
            coalesce(a.cn__{{ c }}, 0) * sqrt(greatest(
                a.css__{{ c }} / nullif(a.cn__{{ c }}, 0)
                - power(a.cs__{{ c }} / nullif(a.cn__{{ c }}, 0), 2), 0))
            + {{ K }} * coalesce(pr.psd__{{ c }}, sf.fsd__{{ c }})
        ) / (coalesce(a.cn__{{ c }}, 0) + {{ K }}) as {{ c }}__sd{{ "," if not loop.last }}
        {%- endfor %}
    from asof_cum a
    left join prior       pr on pr.game_year = a.game_year
    left join season_full sf on sf.game_year = a.game_year
{% endmacro %}
