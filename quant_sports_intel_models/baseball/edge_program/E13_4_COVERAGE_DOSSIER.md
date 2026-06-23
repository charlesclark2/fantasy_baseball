# E13.4 — Feature/Signal COVERAGE Completeness Dossier

**Status:** Inventory + gap-map COMPLETE; candidate testing PRE-REGISTERED, lift-runs handed to operator (long fits). **§7 data-integrity gate: integrity breaches CLEARED 2026-06-22 (archetype staleness fixed + 6 freshness monitors added); one documented caveat remains — the archetype-matchup structural null (§7 Issue 2b), a model-feature follow-up, not an integrity blocker.**
**Date:** 2026-06-22
**Author track:** Model-A (edge direction)
**Purpose (operator's exit criterion):** make the H2H/totals "no edge" conclusion *defensible as a coverage conclusion* — i.e. we checked the signal **axes**, not just the columns we happened to have. Until coverage is demonstrably complete, "no edge" only means "no edge given what we happened to model." This dossier closes that gap.

---

## 0. TL;DR — the headline finding (read this first)

**The story's motivating premise was half-right, and the correction is itself the most valuable deliverable.**

- **TRUE:** the FanGraphs in-season rolling leaderboard (7d/14d/30d wRC+/wOBA/discipline/exit-velo/bat-tracking) is ingested + preserved in `stg_fangraphs__hitting_leaderboard` and reaches **ZERO** modeling feature. The entire in-season hitting-leaderboard branch dead-ends (only ZiPS *projections* and season-grain Stuff+/arsenal reach features). Confirmed column-by-column (§2.3).
- **FALSE (the important correction):** the claim that "there is **NO** form/momentum/recency axis in any contract." There is, and it is **heavy** — just sourced from **Statcast**, not FanGraphs. Every champion contract carries 7/14/30d rolling windows for team scoring, team run-prevention, starters, and bullpen, plus feature-layer trend/drift deltas. The E2.1 per-side totals model (the prioritized integration target) is the **richest** contract in the repo (308 features) and already carries the most explicit `_trend`/`_drift`/`_minus` momentum deltas (§3, §4).

**Consequence for the edge conclusion:** the temporal/recency *axis* is covered. The FanGraphs window gap the story leads with is **largely redundant** with the existing Statcast team-rolling offense (`off_woba_30d`, `off_xwoba_30d`, `off_hard_hit_pct_30d`, `off_barrel_pct_30d`, `runs_per_game_7d/14d/30d` all already exist and are leak-guarded). So filling it is unlikely to move a number. The genuine, non-redundant, leak-clean, free gaps are **narrow and specific** — chiefly **times-through-order (TTO)** and two **hypothesis-driven interaction terms**. This narrows where the remaining edge search should point and makes a subsequent null **trustworthy**.

---

## 1. Method & sources audited

Inventory assembled from direct reads of: live model registry + contract JSONs; `feature_pregame_*` models; `mart_*rolling*` marts; FanGraphs staging + marts; `baseball_data_mart_inventory.md`; `sport_data_platform.md`; `gtm_strategy.md §0` (spend discipline); and the E1.1 (purged CV) / E1.4 (PBO/DSR) / E1.8 (Stuff+ leak) methodology. Leak-safety verified at the as-of-join level. Standing memory confirmations cross-checked (FanGraphs leaderboard dead-end; team-OAA no-signal; weather CLOSED as noise).

**Leak doctrine carried forward (from E1.8):** season Stuff+ leaked because it was joined on `season = year(game_date)` with no date guard against a full-season-grain source → future peek (inflated importance ~88%; the peak signal WAS the leak). **Rule for every new feature in this audit:** season-grain external features join on **prior season** or strict as-of; rolling features must flow through the existing as-of resolver (`mart.game_date < spine.game_date`), never a raw `game_pk` join. Pattern-A marts (`... and current row`) are NOT pre-game-safe on their own.

---

## 2. INVENTORY (the four-layer column census)

### 2.1 Live contracts (what actually reaches a model)

| Target | Contract file | # feats | Recency content |
|---|---|---|---|
| home_win (champion v5) | `betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json` | 211 | 72 window-flavored (30d×39, 14d×17, 7d×15) |
| run_diff (champion v5) | `betting_ml/models/run_differential/feature_columns_ngboost_tuned_2026.json` | 169 | 63 window-flavored |
| total_runs (champion v5) | `betting_ml/models/total_runs/feature_columns_ngboost_tuned_seasonnorm_2026.json` | 113 | 38 window-flavored |
| home_win pre-lineup (33.0) | `..._pre_lineup_home_win_fitted.json` | 156 | retains windows |
| run_diff pre-lineup | `..._pre_lineup_run_diff_fitted.json` | 126 | retains windows |
| total_runs pre-lineup | `..._pre_lineup_total_runs_fitted.json` | 89 | retains windows |
| **E2.1 per-side runs** (totals target) | `betting_ml/models/sub_models/totals_perside_v1/` (`train_perside_negbin.py`) | **275 num + 7 cat → 308** | **richest**; explicit `_trend`/`_delta`/`_drift`/`_minus` |
| v6 de-leaked challengers (E1.9, NOT promoted) | `..._pruned_clustered_deleaked_2026.json` | 13–19 | retains a few windows |

Registry source of truth: `betting_ml/models/model_registry.yaml` (`feature_cols` key). Market-blind enforced (CONTRACT-GUARD; `best_alpha = 0`).

**Axis coverage of the champions (all draw from `feature_pregame_game_features`):** starter/pitching aggregate (largest), offense aggregate, archetype/matchup (heavy), EB posteriors, bullpen, ELO/pythag, park, umpire, lineup. **Absent from champions:** weather (CLOSED as noise), market/odds (deliberate market-blind). **E2.1 per-side additionally covers:** weather, deep bullpen fatigue (`opp_bullpen_pitches_prev_1d/3d/7d`, `opp_closer_used_prev_1d/2d`), park dimensions, catcher framing.

### 2.2 Marts that compute recency (provenance + leak pattern)

| Mart | Entity | Windows | Leak pattern | Key metrics |
|---|---|---|---|---|
| `mart_team_rolling_offense` | team batting | 7/14/30d + std | A (current row; guarded downstream) | **runs_per_game**, woba, xwoba, k%, bb%, hard_hit, barrel |
| `mart_team_rolling_pitching` | team run-prevention (starter/bullpen split) | 7/14/30d + std | A | **runs_allowed_per_game**, woba_against, xwoba_against |
| `mart_pitcher_rolling_stats` | individual pitcher | 7/14/30d + std | A | woba/xwoba_against, k%, bb%, whiff, velo, extension |
| `mart_starting_pitcher_game_log` | starter × game | cumulative | B (strictly prior) | xwoba_against, velo, IP, runs |
| `mart_starter_csw_rolling` | starter | 3-start + season | A | csw_pct |
| `mart_starter_pitch_mix_rolling` | starter | 5-start + season | A | pitch-mix % (→ drift) |
| `mart_bullpen_effectiveness` | bullpen | 14/30d | **B (1-day-preceding baked in)** | k%, bb%, xwoba_against, EB posteriors |
| `mart_bullpen_workload/leverage/handedness` | bullpen | prev 1/2/3/7d | B | pitches/appearances, closer/HL used, leverage |
| `mart_team_base_state_splits` | team RISP/runners-on | 30d | B | woba_with_risp_30d, runs_per_baserunner_30d |
| `mart_team_pythagorean_rolling` | team | 30d | B | pythagorean_residual_30d |

**Key answer for E2.2's autocorrelation lead:** team run-**scoring** form (`runs_per_game_7d/14d/30d`) AND run-**prevention** form (`runs_allowed_per_game_7d/14d/30d`) **already exist and are leak-guarded.** The autocorrelated team-scoring signal E2.2 flagged is already feature-available on both sides. Feature-layer deltas already built: `off_woba_7d_minus_30d`, `pit_xwoba_7d_minus_30d`, `fastball_velo_trend (7d−30d)`, `velo_delta_3start`, `k_pct_7d_minus_std`, `*_drift_5start`, `starter_trailing_fip_30g`.

### 2.3 Ingested-but-UNUSED (the dead-end census)

- **`stg_fangraphs__hitting_leaderboard` — ENTIRELY unused by features** (all ~70 cols × {7d,14d,30d,season}). Includes rolling wRC+/wOBA/OBP/ISO, expected stats (xwOBA/xAVG/xSLG), bat-tracking (bat speed, attack angle, swing length, blast/squared-up%), exit-velo (EV avg/90th/max, barrel%, hard-hit%), full plate-discipline & batted-ball, baserunning (UBR, wBsR, spd). Only an **offline EB-prior script** (`fit_lineup_priors.py`) reads it, season-window only.
- **`fct_fangraphs_hitting_analytics`** — pivots `rolling_wrc_plus_7d/14d/30d`, `rolling_obp_*`, `rolling_pa_*` but is consumed by **no feature** (dead-ends at a profile mart). 12 cols unused.
- **`fct_fangraphs_pitching_analytics`** — only `proj_fip`/`proj_xfip` used; `stuff_plus`/`location_plus`/`pitching_plus`/`proj_era`/`proj_k_pct`/... unused.
- **`pitcher_times_thru_order`** (`stg_batter_pitches.sql:413` = `n_thruorder_pitcher`; surfaced in `mart_pitch_pitcher_profile.sql:69`) — **raw column exists, engineered into ZERO pre-game starter feature.** ⬅️ the cleanest true gap.
- **`mart_team_schedule_context`** computes `travel_distance_miles`, `tz_delta_hours`, `is_getaway_day` — but only `days_rest`/`games_last_7d` are wired into `feature_pregame_team_features` (the rest exist in-mart, unwired).
- Offensive baserunning (UBR staged; sprint_speed ingested) used **only defensively**, not as a lineup offensive feature.

### 2.4 External / un-ingested (domain checklist)

Ingested MLB sources: Statcast/Savant (`batter_pitches` ~140 cols incl. `n_thruorder_pitcher`), MLB StatsAPI (schedule/lineups/venues w/ dims+elevation+`park_facing_degrees`/weather/umpire/transactions/clusters), FanGraphs (Stuff+, ZiPS/Steamer, rolling leaderboard, catcher framing, team OAA/DRS), Action Network (public %), Parlay API (live odds), Odds API (historical).

| # | Signal | Verdict | Note / cost |
|---|---|---|---|
| 1 | Fielding OAA/DRS | **PARTIAL** | prior-season **team** only (`mart_team_defense_quality_rolling`); no per-game/per-player current-season OAA. FREE (Savant per-player CSV). *Team-OAA already tested = no signal.* |
| 2 | Catcher framing / battery | **PARTIAL** | season catcher aggregate only; no pitcher×catcher battery framing. FREE (derive from `batter_pitches`). |
| 3 | Park dims / handed factors | **HAVE dims / PARTIAL** | dims+elevation+factors present; missing wall heights, foul area, handedness-split factors. FREE/static. |
| 4 | Weather vector | **HAVE** | `wind_component_mph` = wind projected on park orientation. *Weather CLOSED as noise for totals.* |
| 5 | **Times-through-order** | **MISSING as feature** | raw `pitcher_times_thru_order` exists; no TTO penalty feature. **FREE (no new source).** ⬅️ top candidate |
| 6 | Baserunning value | **PARTIAL** | UBR/sprint staged but only defensive; offensive BsR not surfaced. FREE (wire). |
| 7 | Platoon splits | **HAVE** | batter vs LHP/RHP + pitcher vs LHB/RHB (prior-season grain). |
| 8 | Rest / travel | **PARTIAL** | days_rest/games_last_7d wired; travel/tz/getaway computed-but-unwired. FREE (dbt plumbing). |
| 9 | Lineup proj vs actual | **HAVE** | confirmed + expected (Epic 33.3) + SCD-2 scratch. |
| 10 | Injuries/IL | **HAVE** | SCD-2 from transactions. |
| 11 | Umpire | **HAVE** | UmpScorecards z-scores. |
| 12 | Bullpen fatigue | **HAVE** | prev-Nd pitch/appearance counts, closer/HL used, leverage. |
| 13 | Statcast pitch-level | **HAVE** | velo/spin/movement/Stuff+/Location+. |
| 14 | Schedule/situational | **HAVE** | day/night, roof/dome, series #, post-2022 rules. |

---

## 3. GAP-MAP (three categories)

### (A) TEMPORAL / recency — **axis COVERED; one narrow non-redundant slice**
- Team scoring form, run-prevention form, starter form, bullpen form, velo/csw/mix drift, form-vs-baseline deltas: **all present, leak-guarded** (§2.2). E2.1 per-side is the richest.
- **Net-new slice:** FanGraphs in-season hitting **windows** (§2.3) — but **largely redundant** with Statcast `off_woba_30d`/`off_xwoba_30d`/`off_hard_hit_pct_30d`/`off_barrel_pct_30d`. The only orthogonal sub-slice: **park/league-adjusted wRC+** (Statcast woba is unadjusted) and **individual bat-tracking form**. → test orthogonality before any build; expectation = redundant.

### (B) COMBINATORY / derived — **3 hypothesis-driven gaps (no blanket generation)**
Already built (do NOT duplicate): platoon-adjusted lineup-vs-starter (`home_lineup_vs_away_starter_xwoba_adj`), bullpen handedness matchup, pitcher-cluster & batter-archetype matchups, lineup-vs-archetype, shrunk pitcher-batter H2H, bat-speed-vs-velo, injury-adjusted lineup, home−away differentials & pct-diff encodings, season-normalized z-scores.
- **B1. TTO penalty** (also category-A-adjacent): starter expected times-through-lineup × 3rd-time xwOBA penalty. Inputs exist raw; never engineered. **Genuine.**
- **B2. Bullpen-fatigue × expected-game-length:** `bullpen_pitches_prev_3d` (or `pitchers_used_prev_3d`) × `starter_avg_ip_last_3` (inverse). Domain: a tired pen bites harder when the starter is expected to be pulled early. Both inputs exist; no product term. **Genuine.** (Trees may capture implicitly → value is mainly the GLM lane + high-order/sparse region.)
- **B3. Park-factor × team-batted-ball:** `park_hr_factor` (or run factor) × `off_barrel_pct_30d`/`off_hard_hit_pct_30d`. Domain: a barrel/FB-heavy offense gains more in a launch-friendly park. Both inputs exist; no product term. **Genuine but lower** (weather/park thread already marginal; trees capture some).

### (C) EXTERNAL / un-ingested — **few free, mostly low-value or already-tested-null**
- **C1. Per-player/positional OAA summed to posted defense** (FREE, Savant) — different from the tested team prior-season aggregate, but the **defense/weather thread is CLOSED as no-signal**; ingestion cost; LOW priority, gate on prior evidence.
- **C2. Wire existing travel/getaway** (FREE, dbt only) — hygiene; rest/travel weak in MLB; LOW.
- **C3. Battery-specific framing** (FREE, derive) — niche, small; LOW.
- Wall heights / foul area / handed park factors / air density — minor, mostly closed-as-noise neighbors. **No PAID source needed to close any gap** (spend discipline satisfied — F5/paid not implicated here).

---

## 4. RANKING (orthogonality × market-underweighting × leak-clean availability × build cost)

| Rank | Candidate | Orthogonality | Mkt-underwt? | Leak-clean free? | Build | Verdict to test |
|---|---|---|---|---|---|---|
| **1** | **B1 TTO penalty** (starter) | High (vs aggregate stuff/woba) | Plausible (3rd-TTO well-documented, books price starter aggregate) | Yes (raw col, as-of) | Low | **TEST** |
| **2** | **B2 bullpen-fatigue × exp-game-length** | Medium | Plausible (interaction, not level) | Yes | Low (1 col) | **TEST** |
| 3 | A FanGraphs in-season wRC+ form (park-adj slice only) | **Low** (redundant w/ Statcast off_woba_30d) | Weak | Yes (prior-season/as-of) | Med | **TEST orthogonality first; expect REDUNDANT** |
| 4 | B3 park × batted-ball | Low-Med | Weak | Yes | Low | TEST (low priority) |
| 5 | C1 per-player OAA → posted defense | Med | Weak | Free but needs ingest | Med | **DEFER** (defense thread CLOSED) |
| 6 | C2 travel wiring / C3 battery framing | Low | Weak | Yes | Low | **HYGIENE only** (not edge) |

**Integration-target priority (per E2.2 §4.5):** the per-side **run MEANS** (E2.1) barely separate games (between-game mean-var 0.894) and team scoring form is more autocorrelated than single-game W/L → a recency/derived signal is most likely to move a number **there**. **Order: E2.1 per-side totals-means FIRST, H2H second.**

---

## 5. PRE-REGISTRATION (hypotheses + test protocol — register BEFORE the lift run)

Each candidate's hypothesis, build, and pass/fail are fixed here so the verdict can't be retrofit. Verdicts are produced by the operator's lift runs (§6); this dossier records them as PENDING.

**Candidate B1 — TTO penalty.** *Hypothesis:* a starter's projected times-through-order × his 3rd-TTO xwOBA delta adds incremental skill to per-side opponent run mean (and home_win) beyond aggregate starter stuff/woba, because the market prices the starter's average, not his fade. *Build:* `mart_starter_tto_splits` from `batter_pitches` grouped by `pitcher_times_thru_order` (1/2/3+), prior-season + trailing-as-of grain; feature `opp_starter_tto3_xwoba_penalty = xwoba(3+) − xwoba(1)`, shrunk to league mean by BF (n<150 → regress hard). *Pass:* incremental ΔCRPS (per-side) / Δlogloss (home_win) > 0 under PurgedWalkForwardSplit AND PBO < 0.2 AND DSR > 0 AND corr with existing `*_starter_xwoba_against_std` < 0.6.

> **VERDICT — RULED OUT (clean, trustworthy null), 2026-06-23.** Ran via `incremental_lift_eval.py` (purged CV, is_cold_start-stratified, matched noise + in-contract-dup sanity controls in the same run). Data verified correct first: the prior-season penalty is real and well-formed (league tto3−tto1 ≈ **+0.018 to +0.048 wOBA** every season; served feature std ≈ 0.016 after EB-shrink). The candidate is **genuinely orthogonal, NOT redundant** (max|corr| 0.09 per-side / 0.10 home_win vs the existing contract) — so this is "orthogonal but inert," the strongest form of null. Results: **per-side CRPS** lift **+0.0006** (all & non-cold) — *below* the matched noise-control lift (+0.0019); DSR **0.394**; PBO 0.189. **home_win logloss** lift **−0.0019** (mildly hurts); DSR **0.003**; PBO 0.195. Gate fails on DSR (and lift) for both surfaces; the non-cold-start stratum matches the pooled read (cold-start handling masked nothing). Artifacts: `ablation_results/e13_4_b1_tto_perside_runs_lift.json`, `…_home_win_lift.json`. **Do not ship.** (⚠️ Build note: a Snowflake `::numeric`=`NUMBER(38,0)` integer-truncation bug in the mart silently zeroed every xwOBA-against on the first builds; caught + fixed 2026-06-23, and it's exactly what the two new silent-zero guards — the `assert_tto_splits_xwoba_not_zeroed` dbt test and the harness degenerate-candidate flag — now protect against.)

**Candidate B2 — bullpen-fatigue × expected-game-length.** *Hypothesis:* `opp_bullpen_pitches_prev_3d × (1/starter_avg_ip_last_3)` lifts the per-side run mean because fatigue matters more behind a short-leash starter. *Build:* single interaction column in `feature_pregame_game_features_raw` from existing as-of inputs. *Pass:* same gate; corr with each parent < 0.7 (must be the interaction, not a level proxy).

> **BUILT + PRE-CHECKED (2026-06-23) — lift run handed to operator.** Built `home_/away_bullpen_fatigue_short_leash = bullpen_pitches_prev_3d::float / nullif(starter_avg_ip_last_3, 0)` in `feature_pregame_game_features_raw.sql` (eval-only; **no production contract references it**; `::float` division — explicitly NOT bare `::numeric`, per the B1 truncation lesson). Both parents are in the E2.1 per-side allow-list, so the harness reads the candidate as `opp_bullpen_fatigue_short_leash` (the FACED pitching side). **Applying the B1 lesson, the warehouse was checked BEFORE the operator's long run:** (a) **data is well-formed, NOT degenerate** — per-season mean ≈ 33–37, std ≈ 15–26, ~97% non-null coverage, no zero-collapse (2021–2026); (b) **the pre-registered orthogonality gate PASSES** — corr(interaction, pen_pitches) = **0.65**, corr(interaction, starter_ip) = **−0.58** (both < 0.7), parents nearly independent (−0.04) → it carries genuine interaction variance, not a level proxy. So the operator's run is a *real* lift test, not a degenerate/redundant column. Guards: dbt `assert_bullpen_fatigue_short_leash_not_degenerate` + harness `candidate_is_degenerate`. **VERDICT (lift): PENDING operator run** (§6.2 run-order: per-side first, H2H second).

**Candidate A — FanGraphs in-season form.** *Hypothesis (skeptical):* park/league-adjusted in-season wRC+ 7/14/30d adds orthogonal lineup-form signal over Statcast `off_woba_30d`. *Build (CORRECTED 2026-06-23):* the rolling time series lives in `stg_fangraphs__hitting_leaderboard` (player × season × window_type × window_start) — NOT `fct_fangraphs_hitting_analytics`, which is player×**season** grain (latest-window snapshot only) and so cannot supply a per-date as-of form value. Both are genuine in-project dbt nodes (manifest-verified, schema `betting`); the earlier "`fct_…` rolling cols" build line was a grain error. *Pass:* FIRST gate = corr(new, `off_woba_30d`) < 0.7 (else RULE OUT as redundant, record null, do not fit). If it passes orthogonality, then the standard lift+PBO/DSR gate.

> **VERDICT — RULED OUT (clean, trustworthy null), 2026-06-23. No fit run (pre-registration: rule out on the orthogonality gate alone).** Two independent disqualifiers, both warehouse-verified on the genuine in-project `stg_fangraphs__hitting_leaderboard`:
> 1. **Orthogonality gate FAILS decisively.** corr(rolling **wRC+**_30d, rolling **wOBA**_30d) = **0.9954** (n=14,162 player-windows, PA≥20). The park/league adjustment — the *only* slice the dossier flagged as potentially orthogonal (§3 A) — does **not** reorder the 30d form signal at all. So FanGraphs in-season form is ~identical to wOBA-based form, and the model already carries the Statcast `off_woba_30d`/`off_xwoba_30d` version of exactly that. Redundant ⇒ rule out without fitting, per the pre-registered cut.
> 2. **Serving-availability disqualifier (independent of orthogonality).** The rolling-window leaderboard is **stale and far too sparse to serve**: rolling windows end **2026-05-02** (≈7 weeks stale vs the OOS edge-eval window), only **~6 distinct 30d snapshots per season** (40 across 2020–2026), `wrc_plus` is **~50% null**, and the FanGraphs `team_abbrev` (211 distinct, multi-team composites) has **zero exact match** to the 31 Statcast team codes — no in-project bridge to lineup/team grain. Even if it were orthogonal it could not be wired into a daily as-of feature in the eval window.
>
> Consistent with the standing read that the FanGraphs hitting leaderboard is a **fantasy asset, not a betting input** (it dead-ends at a profile mart). Recorded; nothing built into a contract. (No serving change, no production feature added — this candidate is closed at the orthogonality pre-check.)

**Candidate B3 — park × batted-ball.** As above; lowest priority, run only if B1/B2 land.

**Shrinkage discipline (applies to all recency candidates):** a short-window value is mostly variance — every candidate must isolate *persistent change* via regression-to-mean (empirical-Bayes shrink toward the season/league mean by sample size) before entering the model. Raw 7d deltas are disallowed.

---

## 7. DATA-INTEGRITY GATE — coverage ≠ integrity (added 2026-06-22, BLOCKS finalization)

**Why this section exists:** §0–§5 audit **coverage** (is the signal axis *represented*?). They do NOT audit **integrity** (is the data behind a present column *fresh and correct*?). A 2026-06-22 production incident (the Odds API `/events` feed died silently on 2026-06-04 and went unnoticed for 18 days — see [[project_odds_bridge_events_outage_jun2026]]) forced an integrity sweep, which found a **second** silent feed death. A degraded feature can *manufacture or mask* an edge signal, so the dossier's "clean null = trustworthy" claim is **conditional on integrity**, which was NOT established by the coverage audit.

**Findings of the 2026-06-22 freshness sweep:**
- **`check_data_freshness.py` monitors only 7 feeds** (Statcast, FanGraphs Stuff+, FanGraphs hitting, umpires ×2, transactions, schedule, Action Network). **UNMONITORED:** every odds feed, the archetype/sequential posteriors, lineups, weather. This blind spot is the root mechanism — silent deaths in unmonitored feeds are invisible.
- **Issue 1 (FIXED): Odds API `/events` dead since 2026-06-04** → `mart_odds_events` frozen → bridge `event_id` NULL → `has_odds=false` on all post-06-05 games. Repointed bridge to the live `/odds` mart. **Impact on THIS dossier: low** — models are market-blind, so odds null hit display/CLV/market-comparison, not the model contracts.
- **Issue 2 (FIXED — staleness): `mart_player_archetype_posteriors` was dead since 2026-05-31** (`compute_archetype_posteriors.py` had NO scheduled caller — unwired, last manual run 05-31). The batter-archetype × pitcher-cluster matchup block — a **heavy** home_win contract component (§2.1) — was served **frozen at 05-31 clusters** for all June games. **Resolved 2026-06-22:** backfilled `--mode backfill --season 2026` (posteriors now current to 06-21) + wired `update_archetype_posteriors_op` into the daily `statcast_catchup_job` so it can't silently re-stale.
- **Issue 2b (STRUCTURAL, pre-existing — NOT the stall): the archetype-matchup null rate is a growing seasonal coverage floor.** Post-backfill + full rebuild, `home_lineup_avg_woba_vs_cluster` null is **still ~22%** — because the null was never caused by the stall (the stall produced *stale*, not *null*, values). Weekly trend: **~7% at Opening Day → ~16% in May → 20–27% by mid-June**, both sides, present even in the pre-stall fresh window (Apr-May ≈ 15%). Mechanism: pitcher archetype posteriors cluster off **prior-season** data, so the growing pool of 2026 rookies/callups/openers has no cluster → null matchup feature — **worst in exactly the recent OOS window the edge eval uses.** This is a genuine coverage limitation of the archetype axis: nominally "covered," but null for ~1-in-5-to-4 recent games. **Candidate fix (graceful degradation):** assign uncategorized pitchers to a nearest-centroid / population-prior cluster (EB shrinkage to the global prior) so the feature degrades to a prior instead of NULL. Pre-register + test alongside §5.
- **Baseline null profile (last 14d / 190 games):** archetype ~22% (structural — Issue 2b), starter Stuff+ 13.2%, platoon-adj 12.6%, park 6.8%; elo/pythag/ump/oaa/odds clean. Stuff+ & platoon nulls are also partly **expected** (prior-season joins null first-season pitchers — the E1.8 de-leak tradeoff) — i.e. the same new-pitcher / prior-season-coverage mechanism recurs across three blocks.
- **Healthy:** Statcast `batter_pitches`, FanGraphs (hitting + Stuff+), Action Network, EB bullpen/starter/batter, player/team/matchup-cell sequential posteriors, lineups — all fresh (06-21/06-22).

**GATE (must clear before finalizing the "no edge" conclusion or running the §5 lift-tests):**
1. **Restore archetype posteriors — ✅ DONE 2026-06-22.** Backfilled `--mode backfill --season 2026` (current to 06-21) + wired `update_archetype_posteriors_op` into `statcast_catchup_job`. Staleness resolved.
2. **Close the monitoring blind spot — ✅ DONE 2026-06-22.** Added 6 monitors to `check_data_freshness.py`: `oddsapi.mlb_odds_raw` (blocking, 8h) + archetype / player-seq / team-seq / eb-bullpen posteriors (alert-only). The archetype monitor (48h) would have caught this on day 2 instead of day 18.
3. **STILL OPEN — archetype structural null (Issue 2b):** decide whether to ship the graceful-degradation fallback (nearest-centroid / population prior for uncategorized pitchers) before trusting the archetype block in the OOS edge eval. Until then, the §5 lift-tests and the "no edge" read must note the archetype axis is ~20% null (rising) in the eval window — a real coverage caveat, distinct from the now-fixed integrity breach.
4. **Run §5 lift-tests only on integrity-verified marts** — now that staleness is fixed, this is satisfied for archetype *freshness*; the structural null (item 3) remains a documented caveat, not a blocker.

**Net effect on the conclusion:** the coverage verdict in §0–§5 stands (the *axes* are checked). But "a clean null is trustworthy" is **earned only after** the integrity gate — otherwise it's "no edge given coverage we have AND given whatever silent degradation we didn't check." The user flagged exactly this risk; the two found issues confirm it is real, not hypothetical.

## 6. ⏭️ OPERATOR HANDOFF

### 6.1 Session 2026-06-23 — lift HARNESS built + Candidate B1 built (lift RUNS pending)

**What shipped this session (no long fits run — those are below):**

1. **The incremental-lift harness — `betting_ml/scripts/incremental_lift_eval.py`** (the must-ship
   deliverable). The §5/§6 lift-tests previously had **no runnable command** — the handoff above
   pointed at `rebaseline_purged_cv.py --add-features … --pbo --dsr`, which does NOT exist (that
   script only re-scores the *fixed* champion recipe across CV regimes). The new harness is the
   real thing: for ONE target it holds the recipe fixed and changes ONLY the feature set (base vs
   base+candidate) — a pure feature lift, not a recipe swap. It reports:
   - **incremental lift** (base−candidate per-game LOSS), pooled **AND stratified on `is_cold_start`**
     (the trustworthy read is the **non_cold_start** stratum — an E13.7 baseline-filled rookie row
     can't manufacture or dilute the signal);
   - **PBO** (AFML §11.4) over {base, candidates…} on a time-sliced perf matrix — gate PBO < 0.2;
   - **DSR** (AFML §14) on the per-game improvement series, deflated by the candidate count — gate DSR ≥ 0.95;
   - **orthogonality** = max|corr| of each candidate col vs the base contract (the Candidate-A redundancy pre-check).
   Two backends: **`perside_runs`** (E2.1 NegBin — the PRIORITY target; reuses `train_perside_negbin`
   assembly; CRPS/NLL; can derive `off_*`/`opp_*` candidates from the wide mart on the fly so a
   candidate stays OUT of the production per-side feature list until it earns promotion) and the
   **champions** (`home_win`/`run_diff`/`total_runs`; reuses the `promotion_gate_eval` adapters,
   same spec on both arms). Pure-logic unit-tested (`betting_ml/tests/test_incremental_lift_eval.py`,
   10 tests; PBO matrix, lift+strat, DSR mapping, EB-shrink, NegBin CRPS/NLL).

2. **Candidate B1 (TTO penalty) — built, eval-only, NOT promoted.**
   - `dbt/models/mart/mart_starter_tto_splits.sql` — per pitcher×season, xwOBA-against split by
     times-through-order (1st vs 3rd+); penalty = `tto3_xwoba_against − tto1_xwoba_against`. xwOBA
     convention mirrors `mart_pitcher_rolling_stats`; regular season only; `table` mat like the
     analogous `mart_pitcher_vs_handedness_splits`.
   - `feature_pregame_starter_features.sql` — prior-season join (`game_year − 1`, leak-clean per the
     E1.8 doctrine) + **EB shrink** toward the BF-weighted prior-season league penalty (k=150 pseudo-PA;
     a <150-BF sample regresses hard). Emits `starter_tto3_xwoba_penalty` + `starter_tto_min_bf_prior`.
   - `feature_pregame_game_features_raw.sql` — surfaces `home_/away_starter_tto3_xwoba_penalty`
     (+ `_tto_min_bf_prior`). **No production contract references these** (verified) → purely a feature-
     store add the lift harness consumes; champions/E2.1 contracts are untouched.

**CI gate (this session):** `uv run pytest betting_ml/tests/test_incremental_lift_eval.py` **GREEN**
(10/10) + full-suite **collection clean** (462 tests, no import breakage). **dbt compile/build NOT run
locally** — the local `dbt` has no Snowflake adapter (project uses dbt-fusion via the remote runner);
the two dbt-Build CI jobs are an **operator step** (see run-order #0).

### 6.2 Run-order for the operator (long fits → operator)

0. **dbt CI + build the new feature** (HALT-tier; the lift needs the column materialized):
   `dbtf build --select state:modified+` **and** `dbtf compile` (the two CI jobs). This builds
   `mart_starter_tto_splits` → `feature_pregame_starter_features` → `feature_pregame_game_features(_raw)`.
   (`mart_starter_tto_splits` scans the full pitch table — minutes; same cost class as the handedness mart.)
1. **VALIDATE THE HARNESS FIRST** (sanity configs — noise ⇒ ~0 lift/high PBO, in-contract dup ⇒ ~0
   incremental). `perside_runs` is the fastest backend:
   `uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --sanity`
   If those don't read ~null, the harness — not the feature — is the finding; stop and inspect.
2. **B1 lift — PER-SIDE FIRST** (the priority integration target, E2.2 §4.5):
   `uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --add-features opp_starter_tto3_xwoba_penalty --run-name e13_4_b1_tto`
   then **H2H second**:
   `uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win --add-features home_starter_tto3_xwoba_penalty,away_starter_tto3_xwoba_penalty --run-name e13_4_b1_tto`
   (optionally `--target run_diff` / `--target total_runs` likewise).
3. **Read the verdict on the `non_cold_start` stratum** + PBO<0.2 + DSR≥0.95. SHIP only if all hold
   (the harness prints `SHIP ✅` / `NO-SHIP (record null)`). A clean leak-tight null is itself the
   deliverable — record it; do **not** chase the main total (E13.8: empirically efficient).
4. Output JSON lands at `ablation_results/<run-name>_<target>_lift.json`. If B1 ships, integrate the
   column into the target contract(s) + retrain through the standard promotion gate; else record the null.
   B2 (bullpen-fatigue × game-length) and Candidate A (FanGraphs orthogonality pre-check) are next
   candidates — they drop into the SAME harness with no harness changes (`--add-features`).

**`git add` (this session):**
- `betting_ml/scripts/incremental_lift_eval.py`
- `betting_ml/tests/test_incremental_lift_eval.py`
- `dbt/models/mart/mart_starter_tto_splits.sql`
- `dbt/models/mart/schema.yml`
- `dbt/models/feature/feature_pregame_starter_features.sql`
- `dbt/models/feature/feature_pregame_game_features_raw.sql`
- `quant_sports_intel_models/baseball/edge_program/E13_4_COVERAGE_DOSSIER.md`

**Excluded from git:** none (the model artifact / CV JSONs are produced by the operator's lift runs).

### 6.4 Session 2026-06-23 (cont.) — Candidate B2 built + pre-checked; Candidate A orthogonality pre-check

**What shipped (no long fits run locally — operator runs the lift):**
1. **Candidate B2 (bullpen-fatigue × short-leash) — built, eval-only, NOT promoted.**
   `home_/away_bullpen_fatigue_short_leash` in `feature_pregame_game_features_raw.sql` (carried
   through by `raw.*` + `sync_all_columns` into `feature_pregame_game_features`). Warehouse-verified
   non-degenerate + orthogonality gate PASSES before handoff (see §5 B2 verdict box). Guard:
   `dbt/tests/assert_bullpen_fatigue_short_leash_not_degenerate.sql`.

**Operator run-order for B2** (long fits → operator; same harness, no harness changes):
0. **Build the feature:** `dbtf build --select state:modified+` **and** `dbtf compile` (the two CI
   jobs). Builds `feature_pregame_game_features_raw` → `_features`. The new singular test
   `assert_bullpen_fatigue_short_leash_not_degenerate` runs here (should PASS — warehouse pre-verified).
1. **B2 lift — PER-SIDE FIRST:**
   `uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --add-features opp_bullpen_fatigue_short_leash --run-name e13_4_b2_fatigue`
   then **H2H second:**
   `uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win --add-features home_bullpen_fatigue_short_leash,away_bullpen_fatigue_short_leash --run-name e13_4_b2_fatigue`
2. Read the verdict on the `non_cold_start` stratum + PBO<0.2 + DSR≥0.95. SHIP only if all hold;
   else record the null. Artifacts → `ablation_results/e13_4_b2_fatigue_<target>_lift.json`.

### 6.3 (superseded) original handoff

The original handoff command (`rebaseline_purged_cv.py --add-features … --pbo --dsr`) was aspirational —
that interface never existed; §6.2 replaces it with the real `incremental_lift_eval.py` harness.

**Honest expectation (recorded):** MLB momentum is weak, markets move on form, and the most-promoted gap (FanGraphs in-season windows) is **largely redundant** with existing Statcast rolling offense. TTO (B1) is the single candidate with a genuine orthogonality + market-underweighting case; B2/B3 are interaction terms trees may already capture (value concentrated in the GLM lane). **A clean null after these tests is the deliverable** — it lets us honestly conclude the model track's value is product-quality (calibrated projections/distributions/transparency) + fantasy, not a betting edge. This dossier is the coverage proof that makes that null defensible: we checked the axes, not just the columns.
