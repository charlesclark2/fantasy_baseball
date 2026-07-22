-- rollup_nfl_team_week_opponent_adjusted — schedule-adjusted efficiency, point-in-time (NFL-N1.0).
--
-- ⭐ THIS IS WHAT THE N1.1 STRENGTH MODEL CONSUMES. GRAIN: one row per (season, team, as_of_week) —
--   the same grain as, and a strict superset of, rollup_nfl_team_week_asof.
--
-- ⭐ WHY: even in the NFL, a team's raw EPA is entangled with WHO it played. A 0.10 off EPA/play
--   against elite defenses is worth more than 0.10 against the league's worst. The adjustment nets
--   out strength of schedule so the rating measures the team, not its opponents.
--
-- ⭐ THE ADJUSTMENT (two-pass iterative opponent-strength correction):
--     adj_off = raw_off + (league_avg_def_allowed − avg_def_allowed_by_opponents_faced)
--     adj_def = raw_def + (league_avg_off        − avg_off_by_opponents_faced)
--   Offense line: if the defenses you faced allowed LESS than league average (a hard slate), the
--   bracket is positive and your offense is credited upward. Defense line is the mirror (def EPA is
--   points ALLOWED per play — lower is better — so facing strong offenses adjusts it downward =
--   better). PASS 1 adjusts vs opponents' RAW ratings; PASS 2 re-adjusts vs opponents' pass-1
--   ratings, so opponents' schedules enter too.
--
-- ⭐⭐ THE LEAKAGE CONTRACT IS INHERITED AND PRESERVED. This team's rating, the opponent list, AND
--   each opponent's rating are all read at the SAME as_of_week — and rollup_nfl_team_week_asof
--   guarantees a week-W row sees only games with week < W. So a week-6 row uses opponents' through-
--   week-5 ratings, never season-final (the classic opponent-adjustment leak). The join pins
--   as_of_week on both sides; `assert_nfl_opponent_adjustment_is_point_in_time` fails the build if
--   that pinning breaks.
--
-- ⚠️ Early-season rows are honestly thin (an opponent with 0–1 games gives a noisy adjustment).
--   Kept (real), but `has_reliable_adjustment` flags rows where this team AND its opponents have
--   ≥3 games. Where no opponent rating resolves, the adjusted value FALLS BACK to raw and
--   `adjustment_applied` is false — never a NULL that silently drops the row from a feature join.
{{ config(materialized='table') }}

-- NB: the CTE is `wk`, not `asof` — ASOF is a DuckDB reserved word (ASOF JOIN).
with wk as (
    select * from {{ ref('rollup_nfl_team_week_asof') }}
),

-- the opponents each team had FACED as of each week (same strictly-< contract as the rollup)
opponents_faced as (
    select s.season, s.team, s.as_of_week, g.opponent
    from wk s
    join {{ ref('fct_nfl_team_game') }} g
      on g.season = s.season
     and g.team   = s.team
     and g.week   < s.as_of_week          -- ⭐ strictly before — inherited leakage contract
     and g.is_completed
),

-- league baselines, per (season, as_of_week) so they are point-in-time too
league as (
    select season, as_of_week,
           avg(off_epa_per_play)      as lg_off_epa,
           avg(def_epa_per_play)      as lg_def_epa,
           avg(off_success_rate)      as lg_off_success,
           avg(def_success_rate)      as lg_def_success,
           avg(points_for_per_game)   as lg_points_for,
           avg(points_against_per_game) as lg_points_against
    from wk where games_played > 0
    group by 1, 2
),

-- ══ PASS 1 — adjust against opponents' RAW ratings ═══════════════════════════════════
opp_raw as (
    select
        o.season, o.team, o.as_of_week,
        count(*)                        as opponents_counted,
        min(oa.games_played)            as min_opponent_games,
        avg(oa.def_epa_per_play)        as opp_def_epa,
        avg(oa.off_epa_per_play)        as opp_off_epa,
        avg(oa.def_success_rate)        as opp_def_success,
        avg(oa.off_success_rate)        as opp_off_success,
        avg(oa.points_against_per_game) as opp_points_against,
        avg(oa.points_for_per_game)     as opp_points_for
    from opponents_faced o
    join wk oa
      on oa.season = o.season and oa.team = o.opponent and oa.as_of_week = o.as_of_week
    where oa.games_played > 0
    group by 1, 2, 3
),
pass1 as (
    select
        a.season, a.team, a.as_of_week,
        a.off_epa_per_play + coalesce(l.lg_def_epa - r.opp_def_epa, 0)         as adj1_off_epa,
        a.def_epa_per_play + coalesce(l.lg_off_epa - r.opp_off_epa, 0)         as adj1_def_epa,
        a.off_success_rate + coalesce(l.lg_def_success - r.opp_def_success, 0) as adj1_off_success,
        a.def_success_rate + coalesce(l.lg_off_success - r.opp_off_success, 0) as adj1_def_success,
        a.points_for_per_game + coalesce(l.lg_points_against - r.opp_points_against, 0) as adj1_points_for,
        a.points_against_per_game + coalesce(l.lg_points_for - r.opp_points_for, 0)     as adj1_points_against,
        r.opponents_counted, r.min_opponent_games
    from wk a
    left join league l on l.season = a.season and l.as_of_week = a.as_of_week
    left join opp_raw r on r.season = a.season and r.team = a.team and r.as_of_week = a.as_of_week
),

-- ══ PASS 2 — re-adjust against opponents' PASS-1 ratings ═════════════════════════════
league1 as (
    select season, as_of_week,
           avg(adj1_off_epa) as lg1_off_epa,
           avg(adj1_def_epa) as lg1_def_epa,
           avg(adj1_off_success) as lg1_off_success,
           avg(adj1_def_success) as lg1_def_success,
           avg(adj1_points_for)     as lg1_points_for,
           avg(adj1_points_against) as lg1_points_against
    from pass1 where adj1_off_epa is not null
    group by 1, 2
),
opp_pass1 as (
    select
        o.season, o.team, o.as_of_week,
        avg(p.adj1_def_epa)        as opp_adj1_def_epa,
        avg(p.adj1_off_epa)        as opp_adj1_off_epa,
        avg(p.adj1_def_success)    as opp_adj1_def_success,
        avg(p.adj1_off_success)    as opp_adj1_off_success,
        avg(p.adj1_points_against) as opp_adj1_points_against,
        avg(p.adj1_points_for)     as opp_adj1_points_for
    from opponents_faced o
    join pass1 p on p.season = o.season and p.team = o.opponent and p.as_of_week = o.as_of_week
    group by 1, 2, 3
)

select
    'nfl'                                             as sport,
    a.season,
    a.team,
    a.as_of_week,
    a.team_week_key,
    a.games_played,
    a.has_sufficient_sample,

    -- ── the RAW inputs, carried through so adjusted vs raw are always comparable ─────
    a.off_epa_per_play                                as raw_off_epa,
    a.def_epa_per_play                                as raw_def_epa,
    a.off_success_rate                                as raw_off_success,
    a.def_success_rate                                as raw_def_success,
    a.points_for_per_game                             as raw_points_for_per_game,
    a.points_against_per_game                         as raw_points_against_per_game,

    -- ── ⭐ OPPONENT-ADJUSTED (pass 2; falls back to pass 1, then raw) ────────────────
    coalesce(a.off_epa_per_play + (l1.lg1_def_epa - o2.opp_adj1_def_epa),
             p1.adj1_off_epa, a.off_epa_per_play)     as adj_off_epa,
    coalesce(a.def_epa_per_play + (l1.lg1_off_epa - o2.opp_adj1_off_epa),
             p1.adj1_def_epa, a.def_epa_per_play)     as adj_def_epa,
    coalesce(a.off_success_rate + (l1.lg1_def_success - o2.opp_adj1_def_success),
             p1.adj1_off_success, a.off_success_rate) as adj_off_success,
    coalesce(a.def_success_rate + (l1.lg1_off_success - o2.opp_adj1_off_success),
             p1.adj1_def_success, a.def_success_rate) as adj_def_success,
    coalesce(a.points_for_per_game + (l1.lg1_points_against - o2.opp_adj1_points_against),
             p1.adj1_points_for, a.points_for_per_game)          as adj_points_for_per_game,
    coalesce(a.points_against_per_game + (l1.lg1_points_for - o2.opp_adj1_points_for),
             p1.adj1_points_against, a.points_against_per_game)  as adj_points_against_per_game,

    -- net (offense − defense) — the single-number team-strength read
    coalesce(a.off_epa_per_play + (l1.lg1_def_epa - o2.opp_adj1_def_epa), p1.adj1_off_epa, a.off_epa_per_play)
      - coalesce(a.def_epa_per_play + (l1.lg1_off_epa - o2.opp_adj1_off_epa), p1.adj1_def_epa, a.def_epa_per_play)
                                                      as adj_net_epa,

    -- ── strength of schedule (the adjustment's residual), a first-class output ───────
    p1.opponents_counted,
    p1.min_opponent_games,
    o2.opp_adj1_off_epa                               as sos_opponent_off_epa,
    o2.opp_adj1_def_epa                               as sos_opponent_def_epa,
    (o2.opp_adj1_off_epa - o2.opp_adj1_def_epa)       as sos_opponent_net_epa,

    -- ── honesty flags ────────────────────────────────────────────────────────────────
    (o2.opp_adj1_def_epa is not null or p1.adj1_off_epa is not null) as adjustment_applied,
    (a.games_played >= 3 and coalesce(p1.min_opponent_games, 0) >= 3) as has_reliable_adjustment
from wk a
left join pass1     p1 on p1.season = a.season and p1.team = a.team and p1.as_of_week = a.as_of_week
left join league1   l1 on l1.season = a.season and l1.as_of_week = a.as_of_week
left join opp_pass1 o2 on o2.season = a.season and o2.team = a.team and o2.as_of_week = a.as_of_week
