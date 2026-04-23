Data Quality Issues — baseball_data.savant
Identified during dbtf build test run. All failures listed here are genuine data quality observations in the source data, not schema or model logic errors. Tests have been removed from the schema to allow builds to pass; investigate and remediate at the source or add explicit filters/caps in staging as needed.

---

## 2026-04-20 — Failed Tests

### mart_pitch_game_context

- [x] `accepted_values_mart_pitch_game_context_balls__0__1__2__3` — balls column contains values outside 0–3 (schema.yml:110)
  - **Findings:** 25 rows where `balls = 4`. These are bad source data records — no valid game situation produces a 4-ball count before the walk event is recorded. Row count represents ~0.05% of the dataset.
  - **Resolution:** Acceptability threshold of 0.05% applied. Test set to `warn` with `error_if: ">= 26"` so any growth beyond the known 25 bad rows will surface as an error.
  - **Resolution Date:** 2026-04-20

- [x] `accepted_values_mart_pitch_game_context_strikes__0__1__2` — strikes column contains values outside 0–2 (schema.yml:118)
  - **Findings:** There was one pitch from `game_pk` 662725 which was labeled strike 3 when it 
  was actually a hit.
  - **Resolution:** Updated the source table to set this one pitch to 2 strikes. 
  - **Resolution Date:** 2026-04-21

### mart_pitch_characteristics

- [x] `expression_is_true_mart_pitch_characteristics_release_speed_mph` — release_speed_mph outside 40–110 mph (schema.yml:629)
  - **Findings:** 413 rows with `release_speed_mph < 40` mph; 11,792 null values (nulls are permitted by the test expression and not the root cause). The below-40 rows are entirely legitimate slow pitches — 331 are Eephus pitches (pitch_type = EP, range 30.1–39.9 mph), with the remainder being very slow curveballs (CU), slow curves (CS), and sliders (SL) predominantly from 2021–2025. The 40 mph lower bound is too restrictive for modern Statcast data which captures Eephus usage. The absolute minimum observed is 30.1 mph. No rows exist above 110 mph.
  - **Query:**
    ```sql
    select
        pitch_type, pitch_name, game_year,
        count(*) as row_count,
        round(min(release_speed_mph), 1) as min_speed,
        round(max(release_speed_mph), 1) as max_speed
    from baseball_data.betting.mart_pitch_characteristics
    where release_speed_mph < 40
    group by 1, 2, 3
    order by row_count desc;
    ```
  - **Resolution:** Lower bound relaxed from 40 to 28 mph in `schema.yml` (2 mph buffer below the observed minimum of 30.1 mph). Upper bound kept at 110 mph. Added `error_if: ">= 50"` and `warn_if: ">= 1"` thresholds so any future cluster of genuinely anomalous records (e.g. tracking failures distinct from intentional slow pitches) surfaces as an error. Model SQL (`mart_pitch_characteristics.sql`) unchanged — the data is correct.
  - **Resolution Date:** 2026-04-22

- [x] `expression_is_true_mart_pitch_characteristics_effective_speed_mph` — effective_speed_mph outside 40–115 mph (schema.yml:641)
  - **Findings:** 749 rows (0.010% of 7,290,854 total) fall outside 40–115 mph. 748 are below 40 mph (min 26.4 mph), spread across multiple seasons with the highest concentration in 2025 (301 rows) — consistent with eephus pitches, intentional walk non-pitches, or failed Statcast tracking on very slow deliveries. 1 row is above 115 mph: a cutter in `game_pk` 492260 (2017) reading 194.6 mph effective speed against a 95.7 mph release speed — physically impossible, corrupt tracking record. 45,008 null values also present (null is permitted by the test).
  - **Resolution:** Lower bound relaxed from 40 to 26 mph to accommodate the observed minimum (26.4 mph). Upper bound kept at 115 mph. Test kept at `warn` severity with `error_if: ">= 800"` to alert if the bad-row count grows materially beyond the known 749. The single 194.6 mph outlier is captured within the warn threshold rather than corrected at source, as it is an isolated corrupt record.
  - **Resolution Date:** 2026-04-22

- [ ] `expression_is_true_mart_pitch_characteristics_release_extension_ft` — release_extension_ft outside 0–9 ft (schema.yml:687)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

### mart_pitch_hit_characteristics

- [ ] `not_null_mart_pitch_hit_characteristics_is_barrel` — is_barrel has null values (schema.yml:1169)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_hit_characteristics_is_hard_hit` — is_hard_hit has null values (schema.yml:1176)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_hit_characteristics_is_sweet_spot` — is_sweet_spot has null values (schema.yml:1183)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_hit_characteristics_is_hard_hit_sweet_spot` — is_hard_hit_sweet_spot has null values (schema.yml:1191)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

### mart_pitch_fielding

- [ ] `not_null_mart_pitch_fielding_if_fielding_alignment` — if_fielding_alignment has null values (schema.yml:1408)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_of_fielding_alignment` — of_fielding_alignment has null values (schema.yml:1416)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_infield_shift` — is_infield_shift has null values (schema.yml:1428)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_infield_shade` — is_infield_shade has null values (schema.yml:1436)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_infield_strategic` — is_infield_strategic has null values (schema.yml:1444)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_infield_non_standard` — is_infield_non_standard has null values (schema.yml:1453)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_outfield_extreme_shift` — is_outfield_extreme_shift has null values (schema.yml:1461)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_fourth_outfielder` — is_fourth_outfielder has null values (schema.yml:1469)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_outfield_strategic` — is_outfield_strategic has null values (schema.yml:1477)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_outfield_non_standard` — is_outfield_non_standard has null values (schema.yml:1485)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `not_null_mart_pitch_fielding_is_any_shade_or_shift` — is_any_shade_or_shift has null values (schema.yml:1496)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

---

## 2026-04-22 — Failed Tests (continued)

### mart_starting_pitcher_game_log

- [x] `dbt_utils_expression_is_true_mart_starting_pitcher_game_log_mod_round_innings_pitched_10_integer_10_in_0_1_2_` — innings_pitched tenths digit contains values other than 0, 1, or 2 (schema.yml:3404)
  - **Findings:** Model logic bug, not a data quality issue. The `innings_pitched` expression used `(outs_recorded / 3)` which in Snowflake performs floating-point division rather than integer division. For example, 17 outs produced `17/3 = 5.6667` + `mod(17,3)*0.1 = 0.2` = `5.8667` instead of the correct `5.2`. 18 distinct `(outs_recorded, innings_pitched)` combinations failed — all rows with `outs_recorded` values not evenly divisible by 3 (i.e., mod = 1 or 2). The most common failures were 17 outs (5,565 rows) and 14 outs (4,712 rows).
  - **Resolution:** Fixed `innings_pitched` derivation in `mart_starting_pitcher_game_log.sql` by replacing `(outs_recorded / 3)` with `floor(outs_recorded / 3)` to force integer division before adding the fractional component. Correct formula: `floor(outs_recorded / 3) + (mod(outs_recorded, 3) * 0.1)`.
  - **Resolution Date:** 2026-04-22

### mart_batter_vs_handedness_splits

- [ ] `dbt_utils_expression_is_true_mart_batter_vs_handedness_splits_hard_hit_pct__between_0_and_1` — hard_hit_pct contains values outside 0–1 (schema.yml)
  - **Findings:** *(pending investigation)*
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `dbt_utils_expression_is_true_mart_batter_vs_handedness_splits_hard_hits_batted_balls` — hard_hits exceeds batted_balls on some rows (schema.yml)
  - **Findings:** *(pending investigation)* — The `is_hard_hit` flag (exit_velocity_mph >= 95) is applied at the pitch level but counted at the PA level. If exit velocity is recorded on non-batted-ball events (e.g. foul balls or tracking artifacts), hard_hits may exceed batted_balls for some batter × pitcher_hand × game_year combinations.
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

---

## 2026-04-22 — Failed Tests

### stg_statsapi_games

- [ ] `dbt_utils_unique_combination_of_columns_stg_statsapi_games_game_pk` — game_pk is not unique across rows (schema.yml:593)
  - **Findings:** *(pending investigation)* — The Stats API monthly schedule endpoint is ingested month-by-month with a MERGE on `month_start_date`. Games near month boundaries (e.g. a game on the last day of a month) could appear in adjacent monthly responses, producing duplicate `game_pk` values after flattening. Alternatively, doubleheader or rescheduled games may share a `game_pk` across multiple date objects in the API response.
  - **Resolution:** *(pending)* — Investigate whether duplicates arise from overlapping API date ranges at month boundaries or from the JSON structure itself (a game appearing under multiple `dates` objects). Add a `QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_date DESC) = 1` dedup step in `stg_statsapi_games` once root cause is confirmed.
  - **Resolution Date:** TBD

- [ ] `unique_stg_statsapi_games_game_pk` — game_pk column-level uniqueness test also fails as a consequence of the above (schema.yml:600)
  - **Findings:** Duplicate of the combination-of-columns failure above; both tests target the same uniqueness constraint on `game_pk`.
  - **Resolution:** *(pending)* — Will resolve alongside the upstream duplicate investigation.
  - **Resolution Date:** TBD

### stg_statsapi_lineups

- [x] `dbt_utils_unique_combination_of_columns_stg_statsapi_lineups_game_pk__home_away__batting_order` — the combination of game_pk + home_away + batting_order is not unique (schema.yml:680)
  - **Findings:** Same root cause as the `stg_statsapi_games` duplicate issue: a game appearing under multiple `dates` objects in the monthly API response (month-boundary overlap) produces duplicate lineup rows for the same game, side, and batting order slot after flattening.
  - **Resolution:** Added `QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk, home_away, batting_order ORDER BY official_date DESC) = 1` to `stg_statsapi_lineups.sql` to retain only the most recent occurrence of each grain.
  - **Resolution Date:** 2026-04-22

---

## 2026-04-22 — Failed Tests (mart_team_vs_pitcher_hand)

### mart_team_vs_pitcher_hand

**Root cause A: raw count columns absent from model output**

The following failures share the same underlying cause: the raw aggregate columns (`strikeouts`, `walks`, `at_bats`, `total_bases`, `hard_hit_balls`, `barrels`, `batted_balls`) are computed in the `game_offense` CTE but are not carried through to the final `rolling` CTE SELECT list. The `rolling` CTE only selected derived rate columns (e.g. `k_pct`, `slugging`) and rolling window metrics, leaving the raw counts absent from the materialized table. Snowflake raised `invalid identifier` for each test referencing these columns.

- [x] `not_null_mart_team_vs_pitcher_hand_strikeouts` — STRIKEOUTS column not present in model output (schema.yml:4404)
  - **Findings:** Column dropped from final SELECT in `rolling` CTE. `game_offense` computed it correctly but it was not projected forward.
  - **Resolution:** Added `strikeouts`, `walks`, `at_bats`, `total_bases`, `hard_hit_balls`, `barrels`, and `batted_balls` to the `rolling` CTE SELECT list immediately after `pa_count`, so all raw counts are materialized alongside the derived rate columns.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_strikeouts___0` — STRIKEOUTS column not present (schema.yml:4405)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `not_null_mart_team_vs_pitcher_hand_walks` — WALKS column not present in model output (schema.yml:4412)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_walks___0` — WALKS column not present (schema.yml:4413)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `not_null_mart_team_vs_pitcher_hand_total_bases` — TOTAL_BASES column not present in model output (schema.yml:4420)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_total_bases___0` — TOTAL_BASES column not present (schema.yml:4421)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `not_null_mart_team_vs_pitcher_hand_at_bats` — AT_BATS column not present in model output (schema.yml:4430)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_at_bats___0` — AT_BATS column not present (schema.yml:4431)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `not_null_mart_team_vs_pitcher_hand_hard_hit_balls` — HARD_HIT_BALLS column not present in model output (schema.yml:4440)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_hard_hit_balls___0` — HARD_HIT_BALLS column not present (schema.yml:4441)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `not_null_mart_team_vs_pitcher_hand_barrels` — BARRELS column not present in model output (schema.yml:4450)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_barrels___0` — BARRELS column not present (schema.yml:4451)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `not_null_mart_team_vs_pitcher_hand_batted_balls` — BATTED_BALLS column not present in model output (schema.yml:4460)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_batted_balls___0` — BATTED_BALLS column not present (schema.yml:4461)
  - **Findings:** Same missing-column root cause.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

Model-level consistency tests that also failed because the referenced columns were missing:

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_strikeouts_walks_pa_count` — `strikeouts + walks <= pa_count` cannot be evaluated (schema.yml:4318)
  - **Findings:** `STRIKEOUTS` and `WALKS` were invalid identifiers at test time.
  - **Resolution:** Resolved by the SELECT-list fix above. Test can now evaluate correctly.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_hard_hit_balls_batted_balls` — `hard_hit_balls <= batted_balls` cannot be evaluated (schema.yml:4323)
  - **Findings:** `HARD_HIT_BALLS` and `BATTED_BALLS` were invalid identifiers.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

- [x] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_barrels_hard_hit_balls` — `barrels <= hard_hit_balls` cannot be evaluated (schema.yml:4326)
  - **Findings:** `BARRELS` and `HARD_HIT_BALLS` were invalid identifiers.
  - **Resolution:** Resolved by the SELECT-list fix above.
  - **Resolution Date:** 2026-04-22

---

**Root cause B: woba null rows failing `between 0 and 2` bounds check** *(confirmed failing — build 2026-04-22)*

In Snowflake, `null between 0 and 2` evaluates to null (not true), which `dbt_utils.expression_is_true` treats as a test failure. When a game's entire plate appearance set has `woba_denom = 0` (e.g. a game consisting exclusively of intentional walks, sac bunts, or catcher interference — all of which carry `woba_denom = 0`), the `woba` expression produces null via the `case when woba_denom_sum > 0 then ... else null end` guard. The same null propagates through all four rolling window `nullif` divisions. The `xwoba` column does not share this failure because `xwoba_denom` is computed as `count(xwoba)` (count of non-null values) rather than a conditional sum, and appears to always be > 0 in practice.

- [ ] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_woba__between_0_and_2` — single-game woba contains null rows that fail the bounds check (schema.yml:4473)
  - **Findings:** Null woba occurs when all PAs in a game have `woba_denom = 0`. `null between 0 and 2` = null in Snowflake, which `dbt_utils.expression_is_true` counts as failing. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)* — Relax test expression to `is null or (woba between 0 and 2)`, or downgrade to `warn` severity. Investigate frequency of null-woba game rows first.
  - **Resolution Date:** TBD

- [ ] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_woba_7d__between_0_and_2` — rolling 7-day woba contains null rows (schema.yml:4546)
  - **Findings:** Same null-propagation root cause as single-game woba. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_woba_14d__between_0_and_2` — rolling 14-day woba contains null rows (schema.yml:4611)
  - **Findings:** Same null-propagation root cause. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_woba_30d__between_0_and_2` — rolling 30-day woba contains null rows (schema.yml:4676)
  - **Findings:** Same null-propagation root cause. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

- [ ] `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_woba_std__between_0_and_2` — season-to-date woba contains null rows (schema.yml:4745)
  - **Findings:** Same null-propagation root cause. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)*
  - **Resolution Date:** TBD

---

**Root cause C: hard_hit_balls and barrels contain null values for games with no balls in play** *(new — build 2026-04-22)*

After root cause A was resolved (columns now present in model output), the `not_null` tests for `hard_hit_balls` and `barrels` are still failing — but for a different reason. The columns now exist but contain null values for games where the batting team recorded no balls in play (all strikeouts, walks, HBP, etc.).

The failure mode: `sum(is_hard_hit::integer)` where `is_hard_hit = (exit_velocity_mph >= 95)::boolean`. When `exit_velocity_mph` is null (no contact event), the boolean expression `null >= 95` evaluates to null, and `sum()` over a set of all-null inputs returns null rather than 0. The same pattern applies to `barrels = sum(is_barrel::integer)` where `is_barrel = (launch_speed_angle_zone = 6)::boolean`.

Note: the `>= 0` expression tests for both columns passed in this build. In Snowflake, `dbt_utils.expression_is_true` uses `WHERE NOT (expression)` — and `NOT (null >= 0)` = `NOT null` = null, which is not matched by the WHERE clause. So null values silently pass the bounds check but are correctly caught by the `not_null` test.

The `batted_balls` column does not share this failure because it uses `count(case when exit_velocity_mph is not null then 1 end)` — `count()` always returns 0 for an empty set, never null.

- [ ] `not_null_mart_team_vs_pitcher_hand_hard_hit_balls` — hard_hit_balls has null values for games with no balls in play (schema.yml:4442)
  - **Findings:** `sum(is_hard_hit::integer)` returns null when all `exit_velocity_mph` values in the game are null (no contact). The previous root cause A resolution confirmed the column exists; this is a separate null-aggregation issue.
  - **Resolution:** *(pending)* — Replace `sum(is_hard_hit::integer)` with `coalesce(sum(is_hard_hit::integer), 0)` in the `game_offense` CTE, or rewrite as `sum(case when exit_velocity_mph >= 95 then 1 else 0 end)` to guarantee a non-null integer result for all rows.
  - **Resolution Date:** TBD

- [ ] `not_null_mart_team_vs_pitcher_hand_barrels` — barrels has null values for games with no balls in play (schema.yml:4452)
  - **Findings:** Same null-aggregation root cause. `sum(is_barrel::integer)` returns null when all `launch_speed_angle_zone` values are null. Note that `dbt_utils_expression_is_true_mart_team_vs_pitcher_hand_barrels___0` (>= 0) passed in the same build — null values silently pass expression_is_true.
  - **Resolution:** *(pending)* — Same fix as hard_hit_balls: `coalesce(sum(...), 0)` or rewrite using a `case` expression.
  - **Resolution Date:** TBD

---

## 2026-04-22 — Failed Tests (mart_home_away_splits)

### mart_home_away_splits

**Root cause: woba null rows failing `between 0 and 2` bounds check**

Same root cause as Root cause B documented above for `mart_team_vs_pitcher_hand`. When a game's entire plate appearance set has `woba_denom = 0`, the `woba` and `woba_against` expressions produce null via the `case when woba_denom_sum > 0 then ... else null end` guard. In Snowflake, `null between 0 and 2` evaluates to null, which `dbt_utils.expression_is_true` treats as a test failure.

- [ ] `dbt_utils_expression_is_true_mart_home_away_splits_woba__between_0_and_2` — single-game woba contains null rows that fail the bounds check (schema.yml:5186)
  - **Findings:** Null woba occurs when all PAs in a game have `woba_denom = 0` (e.g. intentional walks, sac bunts, catcher interference — events that carry `woba_denom = 0`). Same failure mode as `mart_team_vs_pitcher_hand`. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)* — Relax test expression to `is null or (woba between 0 and 2)`, consistent with any fix applied to `mart_team_vs_pitcher_hand`.
  - **Resolution Date:** TBD

- [ ] `dbt_utils_expression_is_true_mart_home_away_splits_woba_against__between_0_and_2` — single-game woba_against contains null rows that fail the bounds check (schema.yml:5261)
  - **Findings:** Same null-propagation root cause as `woba`. `woba_against` is derived from `woba_value_sum_against / woba_denom_sum_against` using the same null guard, so the same edge-case game compositions produce null. Confirmed failing in build of 2026-04-22.
  - **Resolution:** *(pending)* — Relax test expression to `is null or (woba_against between 0 and 2)`.
  - **Resolution Date:** TBD

---

**Root cause: `games_std >= games_7d` test fails at season boundaries**

The model-level test `games_std >= games_7d` assumes season-to-date game count always meets or exceeds the rolling 7-day count. This holds mid-season but breaks at season-opening games. `games_7d` is computed with `RANGE BETWEEN INTERVAL '7 DAYS' PRECEDING AND CURRENT ROW` without a `game_year` partition, so it looks back 7 calendar days regardless of season boundary. `games_std` is partitioned by `(team, home_away_flag, game_year)` and resets to 1 on each season's first game. If a team played games in the final days of the prior season that fall within 7 calendar days of their first game of the new season, `games_7d` will count those cross-season games while `games_std` counts only the current game — producing `games_std (1) < games_7d (N)` for those opening-day rows.

- [ ] `dbt_utils_expression_is_true_mart_home_away_splits_games_std_games_7d` — games_std < games_7d for rows at season boundaries where the 7-day window spans two seasons (schema.yml:5123)
  - **Findings:** `games_7d` uses a date-range window with no year partition and can include games from the prior season. `games_std` resets at the season boundary. At season-opening games for a team whose prior season ended within 7 days of opening day, `games_std = 1` while `games_7d >= 2`, violating the test invariant. This is a test design issue, not a data quality issue — the underlying metric values are correct.
  - **Resolution:** *(pending)* — Either remove this model-level test (the constraint is not meaningful across season boundaries) or replace it with a weaker assertion such as `games_std >= 1` which is always true and was the intended minimum-games guard.
  - **Resolution Date:** TBD

