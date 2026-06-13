-- Story 27.7 leakage guard for the season-normalization baseline.
--
-- The contact-quality season-normalization baseline must be STRICTLY PRIOR: the
-- first game_date of each season has no prior same-season games, so its as-of
-- count must be 0/NULL. If any season's earliest date carries a positive as-of
-- count, the window frame is leaking same-day (or future) games into the
-- normalization — fail.
--
-- Returns offending rows (test passes when empty).

with first_date_per_season as (
    select
        game_year,
        min(game_date) as first_game_date
    from {{ ref('feature_league_contact_baseline') }}
    group by game_year
)
select
    b.game_year,
    b.game_date,
    b.n_asof_min
from {{ ref('feature_league_contact_baseline') }} b
join first_date_per_season f
    on  f.game_year = b.game_year
    and f.first_game_date = b.game_date
where coalesce(b.n_asof_min, 0) > 0
