-- rollup_ncaaf_team_week_opponent_adjusted — schedule-adjusted efficiency, point-in-time
-- (NCAAF-P1.1).
--
-- GRAIN: one row per (season, team_id, as_of_week) — the same grain as, and a strict superset of,
-- rollup_ncaaf_team_week_asof.
--
-- ⭐ WHY THIS EXISTS — raw efficiency is nearly meaningless in college football. The sport has
-- 136 FBS teams playing ~12 games with almost no schedule overlap, and the talent spread between
-- the best and worst is enormous. A team averaging 0.25 PPA against the SEC's top defenses is
-- far better than one averaging 0.30 against the Sun Belt's worst. Comparing RAW numbers across
-- teams is comparing different questions. Nearly every real signal here is opponent-adjusted;
-- an unadjusted model is mostly measuring strength of schedule and calling it team quality.
--
-- ⭐ THE ADJUSTMENT (an iterative opponent-strength correction, 2 passes):
--     adj_off = raw_off + (league_avg_def_allowed − avg_def_allowed_by_opponents_faced)
--     adj_def = raw_def + (league_avg_off       − avg_off_by_opponents_faced)
--   Read the offense line: if the defenses you faced allowed LESS than league average (a hard
--   schedule), the bracket is positive and your offense is credited upward. The defense line is
--   the mirror: if the offenses you faced were weak, your defense is marked down.
--   PASS 1 adjusts against opponents' RAW ratings. PASS 2 re-adjusts against opponents' PASS-1
--   ratings — so "who did your opponents play" enters too. Two passes captures most of the
--   convergence of a full iterative solve at a fraction of the complexity; the residual movement
--   after pass 2 is small relative to the noise in a ≤12-game sample.
--
-- ⭐⭐ THE LEAKAGE CONTRACT IS INHERITED AND PRESERVED. Every input — this team's raw rating, the
-- opponent list, AND each opponent's rating — is read at the SAME as_of_week, and
-- rollup_ncaaf_team_week_asof guarantees a week-W row contains only games with week < W. So an
-- opponent's rating used in a week-6 row reflects that opponent through week 5 only. It is NOT
-- their end-of-season rating. Adjusting with a season-final opponent rating is the classic
-- opponent-adjustment leak — it looks harmless because the opponent's future is "not about us,"
-- but it encodes information that did not exist at kickoff. The join below pins as_of_week on
-- both sides; the `assert_opponent_adjustment_is_point_in_time` test in _ncaaf_marts.yml fails
-- the build if that pinning is ever broken.
--
-- ⚠️ Early-season rows are honestly thin: at as_of_week ≤ 2 an opponent has 0–1 games, so the
-- adjustment is noise. Those rows are KEPT (they are real and a consumer may shrink them) but
-- `has_reliable_adjustment` flags rows where both this team and its opponents have ≥3 games.
-- Where no opponent rating exists at all, the adjusted value FALLS BACK to the raw value and
-- `adjustment_applied` is false — never a NULL that silently drops the row from a feature join.
{{ config(materialized='table') }}

-- NB: the CTE is `wk`, not `asof` — ASOF is a DuckDB reserved word (ASOF JOIN).
with wk as (
    select * from {{ ref('rollup_ncaaf_team_week_asof') }}
),

-- ── the opponents each team had FACED as of each week (same < contract as the rollup) ──
opponents_faced as (
    select
        s.season,
        s.team_id,
        s.as_of_week,
        g.opponent_team_id,
        g.week as game_week
    from wk s
    join {{ ref('fact_ncaaf_team_game') }} g
      on g.season  = s.season
     and g.team_id = s.team_id
     and g.season_order_week < s.as_of_week   -- ⭐ strictly before — inherited leakage contract
     and g.is_completed
),

-- ── league baselines, computed PER (season, as_of_week) so they are point-in-time too ──
league as (
    select
        season,
        as_of_week,
        avg(off_clean_ppa)          as lg_off_clean_ppa,
        avg(def_clean_ppa)          as lg_def_clean_ppa,
        avg(off_clean_success_rate) as lg_off_success_rate,
        avg(def_clean_success_rate) as lg_def_success_rate,
        avg(points_for_per_game)    as lg_points_for_per_game,
        avg(points_against_per_game) as lg_points_against_per_game
    from wk
    where games_played > 0
    group by 1, 2
),

-- ══ PASS 1 — adjust against opponents' RAW ratings ═════════════════════════════════════
opp_raw as (
    select
        o.season, o.team_id, o.as_of_week,
        count(*)                    as opponents_counted,
        avg(oa.def_clean_ppa)       as opp_def_clean_ppa,
        avg(oa.off_clean_ppa)       as opp_off_clean_ppa,
        avg(oa.def_clean_success_rate) as opp_def_success_rate,
        avg(oa.off_clean_success_rate) as opp_off_success_rate,
        avg(oa.points_against_per_game) as opp_points_against_per_game,
        avg(oa.points_for_per_game)     as opp_points_for_per_game,
        min(oa.games_played)        as min_opponent_games
    from opponents_faced o
    -- ⭐ the opponent is read AT THE SAME as_of_week — not their season-final rating
    join wk oa
      on oa.season     = o.season
     and oa.team_id    = o.opponent_team_id
     and oa.as_of_week = o.as_of_week
    where oa.games_played > 0
    group by 1, 2, 3
),

pass1 as (
    select
        a.season, a.team_id, a.as_of_week,
        -- offense credited for facing tough defenses (and vice-versa)
        a.off_clean_ppa + coalesce(l.lg_def_clean_ppa - r.opp_def_clean_ppa, 0) as adj1_off_ppa,
        a.def_clean_ppa + coalesce(l.lg_off_clean_ppa - r.opp_off_clean_ppa, 0) as adj1_def_ppa,
        a.off_clean_success_rate
            + coalesce(l.lg_def_success_rate - r.opp_def_success_rate, 0)       as adj1_off_success_rate,
        a.def_clean_success_rate
            + coalesce(l.lg_off_success_rate - r.opp_off_success_rate, 0)       as adj1_def_success_rate,
        a.points_for_per_game
            + coalesce(l.lg_points_against_per_game - r.opp_points_against_per_game, 0) as adj1_points_for,
        a.points_against_per_game
            + coalesce(l.lg_points_for_per_game - r.opp_points_for_per_game, 0)         as adj1_points_against,
        r.opponents_counted,
        r.min_opponent_games
    from wk a
    left join league  l on l.season = a.season and l.as_of_week = a.as_of_week
    left join opp_raw r on r.season = a.season and r.team_id = a.team_id
                       and r.as_of_week = a.as_of_week
),

-- ══ PASS 2 — re-adjust against opponents' PASS-1 ratings ═══════════════════════════════
league1 as (
    select season, as_of_week,
           avg(adj1_off_ppa) as lg1_off_ppa,
           avg(adj1_def_ppa) as lg1_def_ppa,
           avg(adj1_off_success_rate) as lg1_off_success_rate,
           avg(adj1_def_success_rate) as lg1_def_success_rate,
           avg(adj1_points_for)     as lg1_points_for,
           avg(adj1_points_against) as lg1_points_against
    from pass1
    where adj1_off_ppa is not null
    group by 1, 2
),

opp_pass1 as (
    select
        o.season, o.team_id, o.as_of_week,
        avg(p.adj1_def_ppa)          as opp_adj1_def_ppa,
        avg(p.adj1_off_ppa)          as opp_adj1_off_ppa,
        avg(p.adj1_def_success_rate) as opp_adj1_def_success_rate,
        avg(p.adj1_off_success_rate) as opp_adj1_off_success_rate,
        avg(p.adj1_points_against)   as opp_adj1_points_against,
        avg(p.adj1_points_for)       as opp_adj1_points_for
    from opponents_faced o
    join pass1 p
      on p.season     = o.season
     and p.team_id    = o.opponent_team_id
     and p.as_of_week = o.as_of_week        -- ⭐ point-in-time pinning, again
    group by 1, 2, 3
)

select
    'ncaaf'                                       as sport,
    a.season,
    a.team_id,
    a.team,
    a.conference,
    a.as_of_week,
    a.team_week_key,
    a.games_played,
    a.has_sufficient_sample,

    -- ── the RAW inputs, carried through so adjusted and raw are always comparable ─────
    a.off_clean_ppa                               as raw_off_ppa,
    a.def_clean_ppa                               as raw_def_ppa,
    a.off_clean_success_rate                      as raw_off_success_rate,
    a.def_clean_success_rate                      as raw_def_success_rate,
    a.points_for_per_game                         as raw_points_for_per_game,
    a.points_against_per_game                     as raw_points_against_per_game,

    -- ── ⭐ OPPONENT-ADJUSTED (pass 2; falls back to pass 1, then to raw) ──────────────
    coalesce(a.off_clean_ppa + (l1.lg1_def_ppa - o2.opp_adj1_def_ppa),
             p1.adj1_off_ppa, a.off_clean_ppa)    as adj_off_ppa,
    coalesce(a.def_clean_ppa + (l1.lg1_off_ppa - o2.opp_adj1_off_ppa),
             p1.adj1_def_ppa, a.def_clean_ppa)    as adj_def_ppa,
    coalesce(a.off_clean_success_rate + (l1.lg1_def_success_rate - o2.opp_adj1_def_success_rate),
             p1.adj1_off_success_rate, a.off_clean_success_rate) as adj_off_success_rate,
    coalesce(a.def_clean_success_rate + (l1.lg1_off_success_rate - o2.opp_adj1_off_success_rate),
             p1.adj1_def_success_rate, a.def_clean_success_rate) as adj_def_success_rate,
    coalesce(a.points_for_per_game + (l1.lg1_points_against - o2.opp_adj1_points_against),
             p1.adj1_points_for, a.points_for_per_game)          as adj_points_for_per_game,
    coalesce(a.points_against_per_game + (l1.lg1_points_for - o2.opp_adj1_points_for),
             p1.adj1_points_against, a.points_against_per_game)  as adj_points_against_per_game,

    -- net (offense minus defense) — the single-number team-strength read
    coalesce(a.off_clean_ppa + (l1.lg1_def_ppa - o2.opp_adj1_def_ppa), p1.adj1_off_ppa, a.off_clean_ppa)
      - coalesce(a.def_clean_ppa + (l1.lg1_off_ppa - o2.opp_adj1_off_ppa), p1.adj1_def_ppa, a.def_clean_ppa)
                                                  as adj_net_ppa,

    -- ── strength of schedule, as a first-class output (it is the adjustment's residual) ─
    p1.opponents_counted,
    p1.min_opponent_games,
    o2.opp_adj1_off_ppa                           as sos_opponent_off_ppa,
    o2.opp_adj1_def_ppa                           as sos_opponent_def_ppa,
    (o2.opp_adj1_off_ppa - o2.opp_adj1_def_ppa)   as sos_opponent_net_ppa,

    -- ── honesty flags ─────────────────────────────────────────────────────────────────
    (o2.opp_adj1_def_ppa is not null or p1.adj1_off_ppa is not null) as adjustment_applied,
    (a.games_played >= 3 and coalesce(p1.min_opponent_games, 0) >= 3) as has_reliable_adjustment
from wk a
left join pass1    p1 on p1.season = a.season and p1.team_id = a.team_id
                     and p1.as_of_week = a.as_of_week
left join league1  l1 on l1.season = a.season and l1.as_of_week = a.as_of_week
left join opp_pass1 o2 on o2.season = a.season and o2.team_id = a.team_id
                      and o2.as_of_week = a.as_of_week
