-- E13.4 SILENT-ZERO GUARD (lift-study integrity).
--
-- A dbt build silently materialized mart_starter_tto_splits with every xwOBA-against = 0
-- (a stale-parse-cache / corrupt-snapshot build), which collapsed the TTO feature to a
-- constant and would have recorded a FALSE "no edge" in the incremental-lift study. The
-- whole point of E13.4 is that a null is only trustworthy if the data behind it is real, so
-- a silently-zeroed feature MUST fail loudly rather than flow into a lift verdict.
--
-- League starter xwOBA-against is ~0.30 every season; a per-season MEAN cannot legitimately
-- collapse near 0. This test fails (returns rows) whenever it does — for ANY root cause
-- (fusion bug, cache, corrupt stg). It is an aggregate/grain check, so per-row small-sample
-- noise can't trip it. Pairs with the harness-side degenerate-candidate guard
-- (incremental_lift_eval.candidate_is_degenerate), which catches the same failure at eval time.

select
    season,
    round(avg(tto1_xwoba_against), 4) as avg_tto1_xwoba_against,
    round(avg(tto3_xwoba_against), 4) as avg_tto3_xwoba_against,
    count(*)                          as pitcher_seasons
from {{ ref('mart_starter_tto_splits') }}
group by season
having avg(tto1_xwoba_against) < 0.20
    or avg(tto3_xwoba_against) < 0.20
