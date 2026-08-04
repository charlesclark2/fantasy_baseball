# Production model state — MLB Totals (game total runs, Over/Under)

_PROD-STATE-1a · written 2026-08-04 · grounded in a LIVE read of the served `daily_model_predictions` (DuckDB-over-S3 lakehouse, laptop, 2026-08-04T23:3x–23:4xZ), `betting_ml/models/model_registry.yaml`, `betting_ml/sub_model_registry.yaml`, the E2.x / E13.x / MH2.x ablation memos, and the serving code — NOT roadmap prose. `best_alpha = 0`, `bet_paused = true`._

> **One-line state:** the served totals number is the **v6 NGBoost `Normal` point-and-scale model** (`ngboost_normal_deleaked`, E1.9 clean-slate rebuild, deployed by E13.11 on integrity grounds), on a **15-column post-lineup / 16-column pre-lineup** de-leaked contract. `P(over)` is the **raw Normal survival function** `norm.sf(line, loc, scale)` with **no serve-time calibrator** — measured **ECE ≈ 0.060** (~2× the moneyline's 0.029), with a consistent lean toward the OVER. The model is a **projection/pricing product only**: `best_alpha = 0` (the served posterior *is* the market) **and** `bet_paused = true` (the registry's unpause conditions have never been met), so **no edge, win-rate, or ROI claim rides on this model anywhere**. Two separate, better-calibrated totals distributions exist offline (E2.3 per-side NegBin convolution, E2.4 F5 Beta-Binomial) — **neither is the served totals probability**; the E2.3 object reaches the app only as a *transparency panel* and, via `prop_pricing`, as the K-props pricing engine.

---

## ⭐ Version authority + served reconciliation (the field-7 headline)

**Version authority, named first (umbrella lesson 2).** For totals it is **`betting_ml/models/model_registry.yaml → total_runs.model_version`** (and `.pre_lineup_model_version` for the morning tier).

- ⛔ **NOT `sub_model_registry.yaml`.** That file exists (at **`betting_ml/sub_model_registry.yaml`**, *not* `betting_ml/models/…` — the task brief's path) and it *does* carry a totals entry — but `totals_generative_v1` is the **E2.1-r per-side LightGBM-Poisson count model**, a *different* model that does not produce the served `P(over)`. Reading it as the totals version-of-record would name the wrong architecture entirely. (Same correction 1b made for `home_win`.)
- ⚠️ **`daily_model_predictions.model_version` is HOME_WIN-ONLY.** `scripts/predict_today.py:2289` stamps `MODEL_VERSION` from `_registry["home_win"]`; **totals has its own column**, `totals_model_version`, stamped at `predict_today.py:2290` (`_registry["total_runs"]["model_version"]`), re-resolved to `pre_lineup_<v>` at `:2332` when the totals tier resolves pre-lineup, and bound into the INSERT at `:1451`. The column was added *by* MH2.1 precisely because a totals-only champion swap is invisible in the bundle stamp.

**Live served read (laptop DuckDB over the S3 lakehouse, 2026-08-04 ≈23:35Z) — ✅ MATCH:**

| game_date | tier (`prediction_type`) | `model_version` (home_win bundle) | **`totals_model_version`** | n rows | last write (UTC) |
|---|---|---|---|---|---|
| **2026-08-04** | morning | `pre_lineup_v6` | **`pre_lineup_v6`** | 15 | 08-04 13:00:42 |
| **2026-08-04** | post_lineup | `v6` | **`v6`** | 15 | 08-04 23:17:23 |
| 2026-08-03 | morning | `pre_lineup_v6` | `pre_lineup_v6` | 16 | 08-03 13:08:15 |
| 2026-08-03 | post_lineup | `v6` | `v6` | 7 | 08-03 23:43:31 |
| 2026-08-02 | morning | `pre_lineup_v6` | `NULL` (pre-column) | 30 | 08-02 13:35:55 |
| **2026-08-02** | post_lineup | `v6` | **`mh2_1`** ⟵ the rollback window | 15 | 08-02 19:48:30 |

Registry: `total_runs.model_version: v6`, `total_runs.pre_lineup_model_version: v6`. **Registry and served agree on TODAY's slate, both tiers — the match is measured, not assumed.**

Three corroborations for the umbrella index:

1. **The MH2.1 boundary is live-visible and exactly bounded.** `totals_model_version = 'mh2_1'` appears on **1,377 rows in total, of which exactly 15 were live-served** — `2026-08-02`, `post_lineup`, written 19:42:47→19:48:30Z. The other **1,362 are `prediction_type='backfill'`** rows dated 2026-04-12→08-01 (the `mh2_1_backtest` re-scoring, written in one batch at 08-02 20:13:10Z, with the matching `v6_baseline_refit` batch at 20:35:08Z) — the same 1,362 games MH2.1's own rollback check re-scored. This **confirms the registry's `served_live_rows: "VERIFY"` note**: the answer is **15**, and they are separable exactly as designed. `best_alpha = 0` and `bet_paused = true` held throughout, so nothing needs correcting in those rows (the registry's standing decision: they stay as written).
2. **The bundle-stamp landmine, measured.** On 08-02 `model_version` read `v6` while `totals_model_version` read `mh2_1` **on the same rows** — a totals-only champion swap that a bundle read would have shown as "no change." This is the CLAUDE.md MH2.1 landmine, live-verified (1b observed the same boundary from the H2H side).
3. **The column is inert before 08-02.** `totals_model_version` is NULL on all 55,934 rows from 2021-04-01 → 2026-08-02 morning; it starts populating with the MH2.1 deploy. So *any* totals-version reconciliation on a slate before 2026-08-02 must fall back to the registry — there is no served stamp to read. (`app/backend/routers/admin.py:258-296` already encodes this fallback.)

### Reconciliation verdict

| item | verdict |
|---|---|
| registry `total_runs` vs served `totals_model_version`, 2026-08-04, both tiers | ✅ **MATCH** (`v6` / `pre_lineup_v6`) |
| `sub_model_registry.yaml → totals_generative_v1.promotion_status: pending` vs the signal being read by the serving writer | ⚠️ **DIFFERENCE — see finding ② below.** Not a version mismatch; a promotion-status/coverage question |
| `total_runs.totals_serving_calibration.status: CANDIDATE_PART_A` vs no calibrator in the serving path | ✅ **consistent** — the registry says CANDIDATE, and nothing is wired. Correct-by-decision (E13.6b Part B is explicitly HELD) |
| `total_runs.mh2_1_promotion.status: ROLLED_BACK` vs served | ✅ **consistent** — served is `v6` again; the 15 challenger rows are dated and separable |

---

## 🔎 Headline findings (beyond the ✅ match)

**① The served `P(over)` has no calibrator, and this is a measured defect with an approved-but-unshipped fix.**
`predict_today` applies `_apply_calibrator` to **h2h only**; totals is the raw distributional CDF (`betting_ml/models/total_runs_trainer.py:166` = `stats.norm.sf`). Measured served ECE: **0.079** (E9.26, n≈852) → **0.0595** (E13.6b Part A, n=1,110, 2026-04-17..07-17) → **0.102 on the since-Jul-1 window** (E2.3-d re-measure) — against **~0.029** for the moneyline, with a systematic OVER lean (mean_pred 0.52–0.55 vs base-rate 0.42–0.50) in *every* window. The fix (E13.6b Part B) is PM-approved but **HELD**, and its frozen isotonic candidate is **explicitly stale** — Part B must **re-select the method on a fresh pooled OOF at wire time** (on the 7/21 refresh isotonic's proper scores blew up and the pick flipped to temperature T≈1.53). This is the single largest open quality item on the model.

**② The E2.7 predictive-distribution panel has NO per-side input for the CURRENT slate (live-verified; flagged operator-verifiable, not asserted as a defect).**
`write_serving_store._PERSIDE_MU_BATCH` reads `feature_pregame_sub_model_signals.totals_perside_mu_v1` for the slate's `game_pk`s. Read at 2026-08-04T23:4xZ over the S3 consumer parquet (`baseball/lakehouse/feature_pregame_sub_model_signals/data.parquet`, **LastModified 2026-08-04T12:54:52Z** via boto3 = true UTC, i.e. rebuilt during today's daily job *before* the 13:00Z morning predict):

| game_date | games in `daily_model_predictions` | games with a per-side μ |
|---|---:|---:|
| **2026-08-04** | 15 | **0** |
| 2026-08-03 | 8 | 8 |
| 2026-08-02 | 15 | 15 |
| … through 2026-07-21 | 15/16/12/… | 100% every slate |

Store-wide the signal is healthy (26,524 of 27,677 rows carry a μ; `_available=False` on only 1,153). The shape — **100% on every prior slate, 0% on today's** — is consistent with the store trailing the current slate by one build cycle. Consequence: the E2.7 distribution panel would be **omitted for the live slate** and appear only once the slate is a day old. **Blast radius is cosmetic**: the read is WARN-tier (`log.warning`, distribution skipped), the panel is pure transparency, `best_alpha=0`, and the *served pick* comes from the NGBoost champion which is unaffected. ⚠️ I read the **S3 parquet**; the serving writer reads the Snowflake consumer (`baseball_data.betting_features.feature_pregame_sub_model_signals`), which I could not query (Snowflake MCP unauthenticated in this session) — **operator-verifiable**. Related open items: E2.5's `promotion_status: pending` (backfill + box deploy never confirmed) and E2.7's own unmet runtime gate.

**③ Three factual corrections to the task brief (umbrella lesson 3 — stated here and in the PR body).**

| brief said | actual |
|---|---|
| "the negbin **gaussian-copula** distribution" | **There is no copula in anything served or shipped.** E2.2 measured residual Gaussian-copula **ρ = −0.0035** (Kendall-τ implied −0.0046) and concluded the copula is **unnecessary**; E2.3 convolves the two per-side NegBin marginals **independently (ρ=0)**, and `totals_distribution_v1.json` literally stores `rho = 0.0`. The variance gap E2.2 was chasing lived in the **marginal dispersion**, not the dependence. |
| "**MH2.2** wide-window SHIP_CHALLENGER" | The wide-window `SHIP_CHALLENGER` was **MH2.1** (`total_runs` / `post_lineup`, 2016–2026, 8 folds). **MH2.2 is not a totals story at all** — it is the MiLB→MLB **trajectory feature family** re-scored as its own pre-registered field (fold rule: leave-one-MLB-debut-cohort-out), a pre-registered NULL on the prospect track. |
| version authority = `sub_model_registry.yaml` | `betting_ml/models/model_registry.yaml` (see above). `betting_ml/sub_model_registry.yaml` registers a *different* totals model (`totals_generative_v1`). |

---

## (1) What it predicts + the market/output

- **Target:** `total_runs` = home + away final runs, full game. Label from `mart_game_results`.
- **Served predictive:** a **Normal** `(loc, scale)` per game — stored as `pred_total_runs` (μ) and `pred_total_runs_scale` (σ). Today's slate: post_lineup μ̄ 9.02 / σ̄ 4.40; morning μ̄ 8.86 / σ̄ 4.17 (n=15 each).
- **Served probability:** `p_over_ngboost` = `totals_model_prob` = `norm.sf(total_line_consensus, loc, scale)` — **no calibration layer**. `totals_posterior_prob` = `compute_posterior(p_over, market_over_prob, best_alpha=0)` ⇒ **identically the de-vigged market probability**.
- **Market:** game **Over/Under (totals)**, compared against `over_prob_consensus` / `bovada_devig_over_prob` (Bovada = the standing target book).
- **Surfaces:** the picks list / pick-detail pages (`app/backend/routers/picks.py` — `totals` CTE serves `totals_model_prob AS model_prob`, gated on `layer4_totals_decision IN ('over','under')`), the EV-tracker / performance / scorecard tallies (per-market, never combined — E9.26 semantics), the **E2.7 "Predictive distribution" panel** on the totals pick-detail page (a *different* model — see (6)), and the Story-12.12 totals CLV meta columns (`totals_meta_*`, morning-only, open-line-gated).
- **Derived consumers:** `layer4_totals_over_signal` (= `pred_total_runs − total_line_consensus`), `layer4_totals_decision` (over/under/abstain at a 1.0-run threshold), σ-tier selection (Story 22.4), and the bullpen-OOD bet-permission gate (Epic 19).

## (2) Architecture — champion + why it won

**Champion: `ngboost_normal_deleaked`, v6** — NGBoost with a `Normal` distributional head.

| | post_lineup | pre_lineup |
|---|---|---|
| artifact (S3) | `total_runs/ngboost_normal_deleaked_v6_post_lineup_2026.pkl` | `total_runs/ngboost_normal_deleaked_v6_pre_lineup_2026.pkl` |
| contract → served | 13 → **15** (+2 imputation indicators) | 14 → **16** |
| hyperparameters (served sidecar `_provenance.config`) | `n_estimators=400, learning_rate=0.01, minibatch_frac=1.0, dist=Normal` (registry also records `max_depth=3`) | identical |
| fit by | `betting_ml/scripts/finalize_v6_champion.py --target total_runs --tier <tier>` (E13.11, 2026-06-23) | same |
| rollback | v5 `ngboost_tuned_seasonnorm_2026.pkl` (113-feat) → v4 `ngboost_eb_enriched_2026.pkl` (369-feat) | v5 `ngboost_pre_lineup_2026.pkl` |

**How it was selected (E1.9 step 1, `bakeoff_total_runs_post_lineup.md`; CRPS, 13 feats, 3 purged folds, n=4,857, seed 42, PBO 0.070 ✅):**

| rank | candidate | CRPS | NLL | MAE | calibration (PIT-KS) |
|---|---|---|---|---|---|
| — | **`floor_market`** (reference floor) | **2.4182** | 2.8872 | 3.4055 | — |
| 1 | **`ngboost_normal`** | 2.4201 | 2.8865 | 3.4264 | 0.0629 |
| 2 | `ngboost_lognormal` | 2.4244 | 2.8963 | 3.4340 | 0.0677 |
| 3 | `glm_elasticnet` | 2.4298 | **2.8867** | 3.4447 | **0.0575** |
| 4 | `catboost` | 2.4621 | 2.9032 | 3.4927 | 0.0727 |
| 5 | `stack_mean` | 2.4743 | 2.9304 | 3.4893 | 0.0903 |
| — | `floor_no_skill` | 2.4807 | 2.9065 | 3.5124 | 0.1081 |
| 6 | `xgboost` | 2.5053 | 2.9448 | 3.5298 | 0.0948 |
| 7 | `lightgbm` | 2.6181 | 3.1371 | 3.5961 | 0.1327 |

⚠️ **Two things an auditor must read correctly here.**

- **The market floor ranked FIRST.** No candidate beat `floor_market` on CRPS. That is the honest headline of the whole totals program and it is consistent with E13.8 (the main total's price is efficient) — the champion is selected as *the best available honest projection*, not as something that beats the price.
- **The bake-off's auto-pick printed `glm_elasticnet`; the shipped class is `ngboost_normal`.** The three leaders sit inside the 0.02 CRPS noise floor (0.0097 apart), so the auto-picker tie-broke on calibration and named glm. `ngboost_normal` is (a) the **primary CRPS leader** among non-floor candidates, (b) the class the contract itself was derived under (`feature_columns_ngboost_pruned_clustered_deleaked_2026.json`), (c) the class carried into Optuna and recorded in the registry (`challengers[0].model_class: ngboost_normal`, `config: "Optuna HPO (post)"`), and (d) **structurally required by the serving path**: `p_over_line` needs a per-game `(loc, scale)`, and a `Pipeline(StandardScaler, ElasticNet)` has **no `pred_dist`**. The sibling pre-lineup memo makes the override explicit as an option ("operator/PM may override toward the primary-leader or simplest class before HPO — all are statistically tied here"); the pre-lineup auto-pick *was* `ngboost_normal` outright. **This is exactly the constraint MH2.1 later re-discovered** (a promoted point learner had to be wrapped in a `HomoscedasticNormalRegressor` to serve at all — CLAUDE.md's MH2.1 landmine (b)). I record the tie and the mechanism rather than asserting a documented decision memo exists; **no memo states the override in words** — the evidence is the registry + contract + serving requirement.
- **Pre-lineup** (`bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb.md`): auto-winner `ngboost_normal` (CRPS 2.3774) over a 4-way tie; the winner-conditioned **re-prune fixed a real overfit** — the unpruned 87-feature morning contract posted **PBO 0.543**, the 14-feature re-prune **0.054**.

**Why v6 shipped at all (E13.11, 2026-06-23) — integrity, not edge.** The v6-vs-v5 promotion gate returned **HOLD on both tiers** (post Δ MAE −0.018, just short of the 0.02 floor, with 2026-partial regressing +0.0309; pre Δ +0.0063 with CI [−0.0150, +0.0283] spanning 0). v6 deployed anyway as part of the **all-three-target de-leak rollout**: production was serving a leaky v5 whose explanations were dominated by a within-game bullpen leak. v6's value is **~28× leanness (13 vs 367 features) + leak-clean correctness**, explicitly *not* an offline edge. `bet_paused` stayed `true` through the swap.

**Not the champion (but frequently confused with it) — three other totals models exist:**

| model | what it is | status |
|---|---|---|
| `totals_generative_v1` / `totals_perside_v1` (E2.1-r) | **LightGBM Poisson** per-side mean + E2.3 held-out NegBin dispersion (r_home 4.0645 / r_away 3.3977) | Registered in `sub_model_registry.yaml`, `promotion_status: pending`. Feeds the E2.7 panel + (via `prop_pricing`) the K-props surface. **Not** the served `P(over)`. |
| `f5_generative_v1` (E2.4) | per-side **Beta-Binomial** (s≈15.4/15.6, n_cap 25, ρ=0) for innings 1–5 | Built + calibrated; **never registered as a served signal** (E2.5b backlogged) |
| `layer3_totals` (Story 10.2) | LightGBM + NegBin Layer-3 challenger | registry `promotion_status: champion`, `deployment_mode: informational_manual_review`; **never became the production totals source** (Story 10.6 → 29.1 downgraded it) |

## (3) Feature contract (served)

**Market-blind by contract.** `_assert_market_blind` (`_MARKET_STEMS`) + identifier hygiene are re-asserted at fit time in `finalize_v6_champion.py`. Market data enters only downstream (the market comparison and the α-blend, both outside the model). Certified leak-clean by the E1.8 sweep after the **Stuff+ de-leak** — which mattered *specifically* for totals: `home_starter_stuff_plus` and `away_starter_avg_fastball_velo` were season-to-date-leaky and **dropped to noise once de-leaked**, taking the contract from 21 → **13 FINAL** (`derive_clustered_contract.py`, which refuses to derive from a leaky ranking).

### Post-lineup served columns (15 = 13 contract + 2 indicators) — per-column dictionary

| column | block | definition (per `dbt/models/**/schema.yml` + mart SQL) |
|---|---|---|
| `home_pit_woba_against_14d` | team pitching staff | Home staff wOBA allowed, trailing 14 days |
| `home_pit_woba_against_30d` | team pitching staff | Home staff wOBA allowed, trailing 30 days |
| `home_pit_woba_against_std` | team pitching staff | Home staff wOBA allowed, season-to-date (`_std` = season-to-date cumulative, **not** "standardized") |
| `home_starter_proj_fip` | starter | Home starter **projected FIP** (forward-looking FIP from component rates) ⚠️ structurally absent pre-2020 |
| `home_starter_avg_ip_season` | starter workload | Season-to-date average decimal IP per start (current-season prior starts only); NULL without same-season history |
| `home_bp_eb_uncertainty` | bullpen EB | Home bullpen EB posterior standard deviation (higher = less confident, closer to prior). ⚠️ registry-documented **stub/placeholder** column |
| `away_bp_eb_uncertainty` | bullpen EB | Away equivalent — same stub caveat |
| `home_bp_eb_coverage_pct` | bullpen EB meta | Fraction of home bullpen innings covered by pitchers with enough data for a reliable EB estimate — a **data-depth** signal |
| `away_bp_eb_coverage_pct` | bullpen EB meta | Away equivalent |
| `away_lineup_bat_speed_vs_starter_velo` | lineup (Statcast bat-tracking) | Away lineup mean bat speed − home starter mean fastball velocity (mph); positive = batters faster than the heater. ⚠️ **structurally absent before 2023** (bat-tracking era) |
| `park_run_factor_3yr` | park | 3-year rolling mean of runs/game at the park, ending `game_year − 1`. NULL for a venue with <10 prior-season games |
| `away_wins` | standings | Away team cumulative wins in their league record at game time (`stg_statsapi_games`) |
| `away_losses` | standings | Away team cumulative losses at game time (`stg_statsapi_games`) |
| `has_starter_platoon_data` | imputation indicator | True when BOTH starters have prior-season platoon splits (vs LHB and RHB); False for debut/first-season starters |
| `is_new_venue` | imputation indicator | 1 when the venue opened this season (no prior-season park-factor history) |

*(Note the asymmetry — the post contract carries `home_pit_*`/`home_starter_*` and `away_wins`/`away_losses`/`away_lineup_*` but not their mirrors. That is what the clustered-MDA prune produced on the de-leaked matrix; it is not an omission.)*

### Pre-lineup served columns (16 = 14 contract + 2 indicators) — per-column dictionary

Shared with the post table: `away_bp_eb_coverage_pct`, `away_bp_eb_uncertainty`, `home_bp_eb_uncertainty`, `away_wins`, `away_losses`, `has_starter_platoon_data`, `is_new_venue`. The 9 pre-only columns — **6 of them `_seasonnorm`**, defined as `(<raw col> − as-of league mean) / as-of league std` (`feature_pregame_game_features.sql:15`):

| column | block | definition |
|---|---|---|
| `home_bp_eb_xwoba_seasonnorm` | bullpen EB | Home bullpen Empirical-Bayes posterior xwOBA-against (E1.7-de-leaked, pre-game pool), season-normalized |
| `away_bp_eb_xwoba_seasonnorm` | bullpen EB | Away equivalent |
| `away_team_sequential_bullpen_xwoba_seasonnorm` | Epic-16 sequential | Away bullpen sequential-Bayes xwOBA-against belief entering the game (`prior_mu`, strict `<` = as-of-safe), season-normalized |
| `home_bp_hard_hit_pct_30d_seasonnorm` | bullpen rolling | Home bullpen hard-hit rate allowed, trailing 30d, season-normalized |
| `home_off_xwoba_30d_seasonnorm` | team rolling offense | Home team offense xwOBA, trailing 30d, season-normalized |
| `home_pit_hard_hit_pct_30d_seasonnorm` | team pitching staff | Home staff hard-hit rate allowed, trailing 30d, season-normalized |
| `home_team_sequential_woba` | Epic-16 sequential | Home team's sequential offensive belief — the `off_xwoba` posterior **entering** this game (leakage-safe); tracks within-season run-environment drift the static rolling/EB features miss |
| `home_starter_whiff_rate_14d` | starter rolling | Home starter swing-and-miss rate, trailing 14 days |
| `home_starter_slider_stuff_plus` | starter arsenal | Home starter Stuff+ for the slider (100 = league average). **Prior-season as-of** post-E1.8 de-leak |

🚩 **A totals-specific serving-blindness, documented in the dbt source itself** (`feature_pregame_game_features.sql:63-78`, from E9.53): the `_seasonnorm` `coalesce(..., 0)` cannot distinguish a missing *baseline* (z=0 is correct) from a missing *raw feature* (z=0 is a fabrication), so **a `_seasonnorm` column reads 100% NOT-NULL straight through a total outage of its own block.** The source names this contract by name: `feature_columns_v6_total_runs_pre_lineup_served.json` carries `away_bp_eb_xwoba_seasonnorm` + `away_team_sequential_bullpen_xwoba_seasonnorm` + `home_bp_eb_xwoba_seasonnorm` = **3 of its 7 core discriminative features**, and a never-NULL column can never be flagged imputed ⇒ **a total `bullpen_eb` / `team_sequential` outage is invisible to `discriminative_coverage` / `is_degraded` on the morning totals model.** The store-level per-DATE `check_feature_block_coverage.py` (which asserts on the RAW twins and *refuses* to be configured with a `_seasonnorm` column) is the detector until E1.12.

**Served vs tried-and-dropped — the feature space WAS explored, by removal AND by addition (umbrella lesson 5).**
- **By removal:** 374 raw → E1.3/E1.7 clustered prune 21 → **E1.8 re-derivation 13 FINAL** on the both-de-leak matrix; morning 87 (unpruned, PBO 0.543) → **14 re-pruned** (PBO 0.054). Instrument: `derive_clustered_contract.py` (season-stratified paired-bootstrap 95% CI excluding 0, per cluster).
- **By addition:** yes, and repeatedly — every attempt is a recorded null. E7.9 tested `plus_gb` / `plus_eb` / `plus_both` (MiLB-MLE-corrected block + `eb_gb_pct`) across 7 learners; MH2.1 re-tested `plus_eb` on 8 folds; E13.4 tested TTO / bullpen-fatigue×short-leash / FanGraphs wRC+. **No feature addition has ever cleared the deflated gate for the served totals champion.** See ledger (10). `incremental_lift_eval.py` is the sanctioned ADD path.

## (4) Training data — source, window, CV

- **Source:** `betting_ml/utils/data_loader.load_features()` → the wide `feature_pregame_game_features` mart joined to final scores, filtered `has_full_data` + `min_games_played=15`; wrapped by `model_bakeoff.load_clean_matrix()` which applies the two E1 de-leak swaps in memory (`_swap_bullpen_v3`, `_swap_stuff_plus_deleaked`). Post-E11.1/E11.20 the mart is served from the **S3 lakehouse (DuckDB)**, not Snowflake.
- **Window:** registry `training_cutoff: 2021+`, `training_rows: 10264`, `eval_year: 2026`. The E1.9 bake-off ran **3 purged folds on n=4,857** (post) — a window choice, not a data limit: the mart is populated back to **2015** and MH2.1 demonstrated **8 folds on 2016–2026 (21,006 rows)**. Pre-2021 rows carry NULL Epic-16 sequential posteriors and FanGraphs Stuff+ (2020+).
- **CV:** E1.1 `PurgedWalkForwardSplit` (purge + embargo; `make_gate_splitter(..., embargo_days=…)`), season-stratified; PBO by CSCV (E1.4).
- ⚠️ **NOT point-in-time — every offline number is a CEILING.** `load_features` reads each game's row *as it exists now* (post-game backfilled and dense); the live serve only ever saw the sparse pre-game row. MH2.1 states the corollary explicitly: **widening the window WIDENS this exposure** (older rows have had longest to backfill). The honest live figure comes from scoring the actually-served rows (`honest_live_skill.py`), never from this matrix.

## (5) Validation — the §0.5 gate it passed

| gate | E1.9 (the selection that ships) | result |
|---|---|---|
| selection metric | **CRPS** (proper, distributional), calibration = PIT-KS | ngboost_normal 2.4201 (post) / 2.3774 (pre re-prune) |
| purged/embargoed CV | 3 folds (post, n=4,857) / re-pruned pre | ✅ |
| **PBO < 0.2** | 0.070 (post) · **0.054** (pre re-prune, from 0.543 unpruned) | ✅ |
| DSR | not the binding gate at E1.9 (see below) | — |
| promotion gate v6 vs v5 (MAE) | post Δ −0.018 · pre Δ +0.0063 | **HOLD both tiers** — deployed on integrity (E13.11), not on this gate |
| honest floors | `floor_market` (2.4182) and `floor_no_skill` (2.4807) scored as **reference floors, not candidates** | market floor ranked #1 |

**The two later, better-powered re-tests of this same champion — read them together:**

- **E7.9** (2026-07-29): `INCUMBENT_STANDS`. 28 arms × **3** folds, 11,858 rows. Leader `plus_both::glm_elasticnet` CRPS 2.4714 vs incumbent 2.4921 (margin +0.0206, floor 0.02) — **PBO 0.000 ✅ but DSR 0.842 ❌** at the 0.95 gate. Margin decomposition: **74% is the learner swap** (+0.0153), only **26% the added features** (+0.0053). Null state per `mh2_null_inventory.csv`: **`UNDEFINED`** — *PBO is not computable below 4 folds*, so the recorded 0.000 says nothing, and the DSR was later shown to be an **overstatement** (E7.9 computed it on ~19 year-month buckets and passed no `trial_sharpes`; both biases inflate it).
- **MH2.1** (2026-08-02): `SHIP_CHALLENGER` → **promoted → ROLLED BACK the same day.** Same target/tier on **2016–2026, 8 purged folds, 21,006 rows**, a **pre-registered 4-arm family** (`{incumbent, plus_eb} × {ngboost_normal, glm_elasticnet}`), under the FIXED DSR convention (per-fold observations + measured `trial_sharpes`). Leader `plus_eb::glm_elasticnet` CRPS 2.4908 vs 2.5205 — **margin +0.0297, PBO 0.010, DSR 1.000, lift in 8/8 folds, oracle floor respected.** The design table is the durable lesson: at 3 folds × 28 arms the required per-fold Sharpe for DSR≥0.95 was **7.279** (DSR ceiling 0.9772 at *any* effect); at 8 folds × 4 arms it was **1.182**. **The 3-fold ceiling was a WINDOW choice, not a data limit.**
  - Margin decomposition (mandatory, and it matters): **learner swap +0.0175 / `plus_eb` block +0.0122 — neither clears the 0.02 noise floor alone; only their SUM does.**
  - Per-fold coverage was reported beside per-fold score: **only 3 of 8 folds actually test the served contract** — `away_lineup_bat_speed_vs_starter_velo` is structurally absent in folds 1–4 and `home_starter_proj_fip` in fold 1. Those folds score a structurally *smaller* model.
  - **Why it was rolled back:** the promotion was argued on **conditional calibration**, not the CRPS margin — and that evidence came from an **UNVALIDATED STRATIFIER** (it binned by the σ of `plus_eb::ngboost_normal`, the field's *worst*-calibrated arm). Re-scored against the served v6's own σ — which demonstrably separates realized dispersion (realized SD rises 3.671 → 4.973 across deciles, ρ≈0.66) — **the ordering flipped and the incumbent won in every window** (in-sample-for-v6 n=903: 0.1228 vs 0.1829; **out-of-sample for v6** n=459: **0.2275 vs 0.2519**, under a bias that *favours* the challenger). Pooled MAE 3.5401 (v6) vs 3.56. The CRPS bake-off result **stands** — it simply was not the basis the promotion was argued on.
  - **Re-promotion bar (registry, binding):** a validated stratifier; the challenger ahead on conditional calibration over **forward live-served rows it never saw**; ⛔ **not another 2026 backtest** (it cannot settle this while the challenger is fit through 08-01).

**Distribution-side validation (offline, not the served path):**

| study | gate | result |
|---|---|---|
| **E2.1-r** per-side count bake-off (16 configs, 20 CV buckets) | Σ PIT max-decile-dev over {total, home_total, away_total}; `calib_80 ≥ 0.80` a **FLOOR, not a target** | `PROMOTE_MINIMAL_FIX` — `lgbm_poisson__full__heldout`; incumbent (`__train` dispersion) **DISQUALIFIED** on the floor (0.778). Full-search **PBO 0.233 (fail)** — correctly read as a **tied learner cluster (a learner NULL)**, not overfitting; minimal-fix **DSR 1.000** |
| **E2.2** dependence | reproduce empirical corr + realized variance | ρ = **−0.0035** ⇒ **copula unnecessary**; the variance gap is **marginal dispersion** (train-fit r 8.541 → rel. err 0.2425; **held-out r 3.714 → 0.0382**). Gate formally **NOT MET** and recorded as an honest finding (with ρ≈0 the tail AC *cannot* pass) |
| **E2.3** convolution | total calib_80 ≥ 0.80 + PIT-flat; run-diff + team-total PIT | total **0.838 / PIT-flat ✅**, home_total ✅, away_total ✅, **run_diff ❌** ⇒ overall **NOT MET**. Served per-side r: **home 4.0645 / away 3.3977** |
| **E2.4** F5 per-side (192 configs, 20 buckets) | same metric family | `INCUMBENT_STANDS` — **PBO 0.202** (missed <0.20 by 0.002), minimal-fix **DSR 0.396**. Beta-Binomial swept the top; **Poisson failed the floor outright (0.69) — F5 IS overdispersed**. Shipped betabinom on a recorded **product-quality override** at zero mean-model risk. Null state: **`POWER_LIMITED`** |
| **E2.6** derivative model-vs-market | PBO<0.2 + DSR≥0.95 + BH-FDR q=0.1, **GAME-level**, net of vig | **CLEAN NULL** — 937,947 closing quotes / 5,394 games / 24 books. `team_totals` PBO 0.299 / DSR 0.911 / **0 of 239** survive; `alternate_totals` PBO 0.057 / DSR 0.592 / **0 of 468**. **Placebo negative control fired 0 candidates on both** (the gate does not manufacture edge) |

⚠️ **The E2.1-r metric-inversion lesson originates here and governs every totals interval number.** `calib_80` is an **inclusive-integer** coverage figure; for a discrete count predictive a correctly-specified oracle covers **~0.82–0.86**, so a `|calib_80 − 0.80|` *target* would **REWARD UNDER-DISPERSION**. Every totals/F5 selection therefore gates on **randomized-PIT max-decile-deviation** with `calib_80` kept as a **FLOOR**, and every form carries a per-form `test_oracle_is_the_scoring_floor` guard. E2.3-d applies the same skepticism reflexively to E2.3's own headline: "0.838" is the *biased* figure; its **PIT-flatness (0.0068) is the trustworthy part**.

## (6) Serving path — registry → predict → serving store → API

```
betting_ml/models/model_registry.yaml['total_runs']
  → predict_today.py:2290  TOTALS_MODEL_VERSION = registry.model_version   (:2332 → pre_lineup_<v> when the totals tier resolves pre-lineup)
  → :2331   per-target tier resolution (total_runs resolves its OWN tier — a bundle read cannot)
  → :2393   _load_model_cached("total_runs", tier)  ← S3 .pkl
  → :2244+  pred_dist(X_tot) → loc_tot / scale_tot
  → p_over_line(dist="Normal", {loc, scale}, total_line)  = scipy.stats.norm.sf   ← NO CALIBRATOR
  → compute_posterior(p_over, market_over_prob, best_alpha=0)  ⇒ posterior == market
  → daily_model_predictions  (pred_total_runs, pred_total_runs_scale, p_over_ngboost,
                              totals_model_prob, totals_posterior_prob, totals_edge,
                              totals_kelly_fraction, layer4_totals_*, totals_meta_*,
                              totals_model_version)
  → write_serving_store.py:1441 _MODEL_DIST_BATCH reads (loc, scale) BACK OUT
      → :1817  norm.sf(line, loc, scale)  per book/line  ← the same Normal CDF, re-derived
      → Railway PostgreSQL (primary) → S3 api-cache (fallback)
  → app/backend/routers/picks.py  (totals CTE; model_prob = totals_model_prob;
                                   gated on layer4_totals_decision IN ('over','under'))
  → frontend/app/picks/[game_pk]/page.tsx + the picks list / EV tracker / scorecard
```

**Tiers.** `morning` (pre_lineup, ~13:0x UTC daily) and `post_lineup` (lineup-monitor re-score, ~23:1x–23:4x UTC, one-and-done per game). Both write a `totals_model_version`.

**A separate, parallel path for the E2.7 transparency panel** (do not conflate it with the pick):
`feature_pregame_sub_model_signals.totals_perside_mu_v1/_dispersion_v1` → `write_serving_store._PERSIDE_MU_BATCH` → `betting_ml/utils/totals_serving.build_totals_distribution_payload` (independent ρ=0 NegBin convolution using the committed `betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json`) → the `totals_distribution` key on the game-detail blob → `GameDetailResponse` → `frontend/components/totals-distribution.tsx`. **WARN-tier throughout** (both the read and the compute are `try/except`ed; a failure degrades the panel to absent and never HALTs the serving-critical write). It carries its own **plausibility guard** — `distribution_is_plausible` suppresses the panel when a side μ < 2.5 or the convolved total diverges > 4 runs from the champion (≈5.3% of games), because the two panels are **two different totals models** and would otherwise contradict each other on the same page.

**Op tiers touching totals:** `predict_today_morning` / `lineup_predict` = **HALT**; `write_serving_store_op` / `write_api_cache_op` = **HALT**; `signal_freshness_check` = **HALT**; the E2.7 per-side read = **WARN**.

## (7) Version + last retrain + retrain cadence

| | value |
|---|---|
| **served version** (live-verified 2026-08-04, both tiers) | **`v6` / `pre_lineup_v6`** |
| model name | `ngboost_normal_deleaked` |
| selected at | 2026-06-19 (E1.9 bake-off) · registry `selected_at: 2026-06-13T00:00:00Z` (v5-era field, stale) |
| **fit + deployed** | **2026-06-23** (`finalize_v6_champion.py`, E13.11) — `promoted_at: 2026-06-23T00:00:00Z` |
| days since fit (as of 2026-08-04) | **42** |
| training rows / cutoff | 10,264 / 2021+ |
| calibrator | **NONE served.** `totals_serving_calibration.status: CANDIDATE_PART_A` (isotonic candidate, fit 2026-04-17..07-17, OOF ECE 0.0145 vs raw 0.0595) — **not wired** |
| **retrain cadence** | ⛔ **NONE. There is no scheduled retrain for the totals champion.** Every retrain to date has been story-triggered (E1.9 → E13.11; E7.9; MH2.1). This mirrors the H2H gap (open story E1.10) |
| refit triggers that DO exist | `totals_serving_calibration.refit_required_after: [total_runs_model_rebuild]` — **fired 2026-08-02** by the MH2.1 swap, **stood down** the same day when it rolled back; the trigger stays armed |
| rollback chain | v6 → v5 `ngboost_tuned_seasonnorm` (113-feat) → v4 `ngboost_eb_enriched` (369-feat); MH2.1 machinery retained but not champion (`mh2_1_artifact_path`, `finalize_mh2_1_champion.py`, `homoscedastic_regressor.py`) |

## (8) Honest-framing status — `best_alpha = 0` ✅ CONFIRMED (and totals carries a SECOND, stricter brake)

**Confirmed on served rows, not asserted.** Live read over the trailing 7 days:

| tier | rows | `alpha` min/max | max \|`totals_edge`\| | max \|`totals_kelly_fraction`\| |
|---|---:|---|---|---|
| morning | 459 | **0.0 / 0.0** | 5.55e-17 | 2.76e-17 |
| post_lineup | 108 | **0.0 / 0.0** | 1.11e-16 | 5.65e-17 |

The stored edge and Kelly fraction are **machine epsilon** — presence flags, not quantities (read them `IS NOT NULL`, never by value). With `best_alpha = 0`, `compute_posterior(p_over, market, 0)` returns the market ⇒ **`totals_posterior_prob` IS the de-vigged market probability** (observed avg 0.4970–0.5008 against a model prob of 0.531–0.532). **No edge, win-rate, or ROI claim rides on the totals model anywhere.**

**Totals additionally carries `bet_paused: true`** — a second, independent brake the other MLB models do not have. The registry's `unpause_conditions` ("beat prior-predictive NLL 2.8893 AND prior-naive Brier 0.248 on a rolling 60-game live window") have **never been met** (`layer3_totals.unpause_conditions.status: not_met`), and the pause has been independently re-confirmed **three times** (Epic 10.6 CV, Epic 26.3 Layer-4 backtest, Epic 16.6 production harness).

**Three framing traps an auditor should know about:**

1. **`best_alpha.json` contains a `totals_alpha: 0.7`** (Story 10.5, log-loss-optimal on a 4,580-game walk-forward surface). **It is NOT served** — `predict_today._load_best_alpha()` returns the single `best_alpha` (0.0) and applies it to both markets; `totals_alpha` appears nowhere in the serving path. Quoting it as the live blend would be wrong by construction.
2. **`layer4_totals_decision` still emits `over`/`under`** and the picks API surfaces those rows. That is the **informational/manual-review** Layer-4 decision (a 1.0-run threshold vs the model μ), not a bet recommendation: `bet_paused` is true, α is 0, and the Epic-19 bullpen-OOD gate can hard-veto `qualified_bet` regardless.
3. **`prediction_type='backfill'` rows carry REAL, non-zero `totals_edge`** (max 0.245 in the last 7 days) — those are the MH2.1 backtest / `v6_baseline_refit` re-scoring rows, written by `backfill_predictions.py`, **not served**. An edge query that does not filter `prediction_type` will report edge that was never shown to anyone.

## (9) Known limitations + open follow-ups

**Structural limitations (properties of the model, not bugs to fix):**

1. **The market beats the model on the main line, and this is settled from four directions.** `floor_market` ranked #1 in the E1.9 bake-off; E13.8's benchmark found the totals price is a coin-flip whose value is in *the number*, already near the variance floor; Story 29.1 measured model RMSE **4.2596 vs Bovada 3.7298** (gap +0.5297) → `DOWNGRADE`; E2.6 found **no derivative** beats its own close after deflation. ⇒ **do not re-open "does the totals model beat the market."**
2. **Served `P(over)` is uncalibrated and over-leans** — ECE 0.0595 (window) / 0.102 (recent), vs 0.029 for moneyline. See open item #1.
3. **Per-game σ generalizes only weakly.** RMS |Var(z)−1| ≈ **0.12–0.18 in-sample → 0.23–0.25 out of sample** for *both* the served v6 and its flat-σ alternative. Heteroscedasticity is real and **under-expressed**: realized SD rises **+35%** across the served σ's own deciles while σ rises only **+23%**. CRPS is mean-dominated and PIT-KS is marginal ⇒ **both are structurally blind to this**, which is why a conditional-calibration check exists at all.
4. **The `_seasonnorm` blindness** — 3 of the 7 core pre-lineup discriminative features are never-NULL by construction, so a total `bullpen_eb`/`team_sequential` outage cannot be flagged by `discriminative_coverage` on the morning totals model (see (3)).
5. **`*_bp_eb_uncertainty` are documented stub/placeholder columns** and 2 of the 15 post-lineup served features.
6. **Every offline number is a dense-re-read CEILING** (§4), and only **3 of MH2.1's 8 folds** actually test the served contract.
7. **The E2.7 panel and the served pick come from two different totals models** — reconciled today only by a suppression guard that hides ~5.3% of games.

**Open follow-ups — 13 open, 8 settled. Counted and separated.**

**🔴 OPEN (model / serving):**

| # | item | state | note |
|---|---|---|---|
| 1 | **E13.6b Part B** — wire a totals `P(over)` calibrator | **HELD** (Part A ✅ 2026-07-17, PM-approved) | ⭐ **highest-value open item.** ⚠️ the frozen isotonic candidate is **stale — re-select the method on a fresh pooled OOF at wire time**; box ECE re-measure is a HARD ship gate. 🔒 exactly ONE totals-calibration mechanism ever (if E2.3 ships at source it RETIRES this, never stacks) |
| 2 | **MH2.5** — make per-game σ generalize + widen its dynamic range | ✅ COMMITTED (PM 2026-08-02), unstarted | Re-scoped by the rollback: the premise "the served σ is actively wrong / flatten it" is **RETRACTED**; flat-σ is a **null to beat**. Method lock: publish the realized-SD-per-bin table + ρ + per-bin SE **before** reading any Var(z) |
| 3 | **MH2.6** — the run_diff/post_lineup arm of the MH2.1 bake-off | ✅ COMMITTED, unstarted | Offered under MH2.1 Lock 1, never run; completes the totals picture |
| 4 | **MH2.7** — fix `cv_power.classify_null`'s `max_field_size` re-test trigger | 🟢 READY | It currently prescribes the **retired post-hoc field** as a remedy — a selection-bias inversion inside a badge that reads like a fix. Affects how every totals null above is re-read |
| 5 | **E2.8** — per-side μ plausibility fix + one-totals-model convergence | ⏸️ non-urgent (app guard hides the symptom) | ~2.6% of 2026 games (336/13,150) have a side μ < 2.5 runs; the guard suppresses ~5.3% |
| 6 | **E2.5** — operator leakage-safe backfill + box deploy | `promotion_status: pending`, `promoted_at: null` | The registry has said "pending" since 2026-07-26 while the signal is read by the serving writer — see finding ② |
| 7 | **E2.7 runtime gate** + the live-slate coverage gap (finding ②) | unmet / newly observed | Operator: run `write_serving_store.py --game-detail` once and confirm `totals_distribution` populates for a **current** slate |
| 8 | **E2.0c** — F5 historical odds source | 🅿️ PAUSED, kill criterion **pre-registered but unexecuted** | Two sales inquiries outstanding since 2026-06-18. Kill if both come back no-F5 OR no history ≥2021 OR >$400/mo → then formally strip the F5 gate from E2.4/E2.6 |
| 9 | **E2.5b** — register `f5_generative_v1` as a served signal | backlogged | E2.6 **held F5 out** because the served signal produces only full-game μ; the harness is F5-ready |
| 10 | **E1.12** — regime-conditioned specialization (and the `_seasonnorm` detector gap it closes) | anchor story, unstarted | Until then `check_feature_block_coverage.py` (RAW columns, per-date) is the only detector for limitation #4 |
| 11 | **E1.13** — injury-feature correction → served-model revalidation/retrain | open | The E9.48/E9.53 downstream; totals is in scope |
| 12 | **No scheduled retrain cadence** for the totals champion | open, uncarded for totals | Same gap as H2H's E1.10. 42 days since fit at time of writing |
| 13 | **TD3** — champion-promotion safety audit | 🟢 READY | `mart_clv_labeled_games` is hardcoded `model_version='v6'`; a totals-only promotion is exactly the case the bundle stamp cannot express (MH2.1 named three such bundle-assuming consumers) |

**✅ SETTLED (do not re-open without new evidence):** E2.2 (copula unnecessary, ρ≈0) · E2.3 (dispersion is the lever; gate NOT MET recorded honestly) · E2.3-d (the served path is NGBoost-Normal; `totals_distribution_v1.json` is **orphaned** w.r.t. totals serving) · E2.6 (derivative edge = clean null, placebo-validated) · MH2.1 (rolled back, with a binding re-promotion bar) · E13.8 (main-line efficiency) · E1.8 (Stuff+ de-leak → contract re-derived 21→13) · MH2.3 (bake-off design blocks made machine-readable).

**⚠️ There is no automated drift/calibration monitor for the totals model.** ECE has been measured by story (E9.26 → E13.6b Part A → E2.3-d), never on a cadence. Nothing pages if the served `P(over)` calibration degrades. (K-props found the same gap — PROD-STATE-1d, KP-V2.0.)

## (10) ⭐ TRIED & RESULT LEDGER — what has already been tested, and how it came out

> Null states use `cv_power.classify_null`'s taxonomy where the artifact supports one; where the recorded artifact cannot support a classification, that is stated rather than guessed (an unclassifiable header is `UNKNOWN`, not a pass). Rows sourced from `mh2_null_inventory.csv` are marked ⓘ.

### A. Architecture / learner class

| when | candidate | result | null state | source |
|---|---|---|---|---|
| 2026-06-19 | **E1.9 clean-slate bake-off, post_lineup** — ngboost_normal / ngboost_lognormal / glm_elasticnet / catboost / xgboost / lightgbm / stack_mean vs `floor_market` + `floor_no_skill`, CRPS, 3 purged folds, n=4,857 | **`ngboost_normal` SHIPPED** (via E13.11). 3-way tie inside the 0.02 floor; **`floor_market` outranked every candidate** | — (a shipped selection) | `bakeoff_total_runs_post_lineup.md`, PBO 0.070 |
| 2026-06-19 | **E1.9 pre_lineup** + winner-conditioned re-prune | `ngboost_normal` shipped; **re-prune fixed a real overfit (PBO 0.543 → 0.054)** | — | `bakeoff_total_runs_pre_lineup*.md` |
| 2026-06-19 | v6 vs v5 **promotion gate** (MAE), both tiers | **HOLD both** (post −0.018 short of floor; pre +0.0063, CI spans 0). Deployed anyway on **integrity** (E13.11) | — | registry `challengers[0].tiers` |
| 2026-06-04 | **Epic 16.6 sequential-enriched retrain** (10 Epic-16 sequential cols) | **DO NOT PROMOTE** — third independent confirmation of the pause. Both arms clear L1 marginally; **both FAIL L3** (blended Brier 0.2697/0.2702 vs market 0.2297) and L4 (negative ROI at every threshold). "The 10 sequential features add nothing for totals" | genuine absence (challenger ≈ champion, worse on CV MAE) | registry `sequential_retrain_verdict`; `production_bayesian_total_runs.md` |
| 2026-05/06 | **Story 10.2 → 10.6 LightGBM+NegBin Layer-3 challenger** | 10.2 won its own head-to-head (NLL 2.7850 vs Ridge 2.9663 / GLM floor 2.8503); 10.6 `PROMOTE_WITH_MONITORING` (MAE −0.066, NLL −0.050, variance gate passed) — **but it never became the totals source**; 29.1 downgraded the whole track | superseded | `totals_v1_architecture_comparison.md`, `totals_champion_vs_challenger.md` |
| 2026-05-08 | **Card 8.P LightGBM quantile regression** | **REJECTED** — MAE gate passed (3.4791 < 3.5107) but std(q50) 0.9325 < 1.5 and mean residual −0.5951 failed. Same variance-shrinkage ceiling as NGBoost | genuine absence (architecture-independent — the feature set cannot produce the spread) | registry `challengers` |
| 2026-06 | **Story 10.10 quantile-regression Layer-3** (direct conditional quantiles, no `exp()` log-link) | **Jensen floor REMOVED ✅** (May-2026 mean pred 8.5314 vs the 8.81 threshold) — but **calib_80 0.6857 ❌** (gate 0.75–0.85) and Brier 0.3053 vs market 0.2292, naive 0.2500 → beats neither | genuine absence on the verdict surface | `totals_quantile_layer3_10_10.md` |
| 2026-06-03 | **Epic 9 pseudo-BMA stacking combiner** (bullpen/offense/run_env → NB2) | **Beats the market in NO season** (pooled model 0.2620 vs market 0.2431) | genuine absence | `totals_v2_leakage_free.md` |
| 2026-07-29 | **E7.9 retrain bake-off** — 28 arms (7 learners × 4 contract variants), 3 folds, 11,858 rows | **`INCUMBENT_STANDS`.** Leader margin +0.0206 (floor 0.02) but **DSR 0.842 < 0.95**; PBO 0.000 is **not computable at 3 folds**. 74% of the margin was the learner swap | ⓘ **`UNDEFINED`** (PBO undefined below 4 folds) — *and* the DSR was later shown inflated by the legacy convention | `e7_9_retrain_total_runs_post_lineup.md` |
| 2026-08-02 | **MH2.1 wide-window retrain** — 4 pre-registered arms, **8 folds**, 21,006 rows, fixed DSR convention | **`SHIP_CHALLENGER`** (CRPS +0.0297, PBO 0.010, DSR 1.000, 8/8 folds) → **promoted → ROLLED BACK the same day** (15 live rows). The CRPS result **stands**; the promotion's stated basis does not | **ROLLED BACK** — decision reversed on an unvalidated stratifier, not on the metric | `mh2_1_retrain_…_w2016.md`, `mh2_1_rollback.md` |
| 2026-08-02 | MH2.1 **`plus_eb::ngboost_normal`** and **`incumbent::glm_elasticnet`** (the other two arms) | lost to the leader; trial Sharpes 0.449 and 0.842 vs the leader's 1.045 | genuine absence within the declared family | same |

### B. Feature families and contract changes

| when | candidate | result | null state | source |
|---|---|---|---|---|
| 2026-06-18/19 | **E1.8 Stuff+ de-leak → contract re-derivation** | `home_starter_stuff_plus` + `away_starter_avg_fastball_velo` **dropped to noise once de-leaked** (confirming the season-to-date peek); contract **21 → 13 FINAL** | a shipped correction | `feature_leakage_audit.md`; `derive_clustered_contract.py` |
| 2026-07-29 | **E7.9 `plus_gb`** (`eb_gb_pct`) — feature effect at fixed learner | **+0.0000 to +0.0073 CRPS** across 7 learners; negative for one. Well inside noise | genuine absence | `e7_9_retrain_total_runs_post_lineup.md` |
| 2026-07-29 | **E7.9 `plus_eb`** (MiLB-MLE-corrected block) at fixed learner | +0.0053 (glm) … +0.0373 (xgboost); **−0.0095 for lightgbm**. Under the *served* learner (ngboost_normal) **+0.0107 — under the 0.02 floor** | power-limited at 3 folds; **re-tested by MH2.1** | same |
| 2026-08-02 | **MH2.1 `plus_eb`, 8 folds** — the properly-powered re-test | **+0.0122 alone — still under the 0.02 floor.** Only `learner swap (+0.0175) + block (+0.0122)` together clear it | **the block alone is a null**; the bundle shipped then rolled back | `mh2_1_retrain_…_w2016.md` §Margin attribution |
| 2026-06-23 | **E13.4** — TTO (times-through-order), bullpen-fatigue × short-leash, FanGraphs wRC+ | **ALL NULL** (wRC+ redundant; B3 gated off) → "no betting edge" became an **earned coverage conclusion**, not an assumption. Built `incremental_lift_eval.py` and found 2 silent data bugs en route | genuine absence | `E13_4_COVERAGE_DOSSIER.md` |
| 2026-05-10 | **Epic 1 market-blind retrain** — removing 33 market cols (incl. `total_line_consensus`, then the #1 feature at imp 0.064) | PROMOTED. The honest market-blind baseline is **CV MAE 3.5521**; the earlier 3.5107 "gate" had benefited from **market circularity** | a shipped correction | registry `challengers` |
| 2026-06-13 | **Story 27.7 / 30.10 `_seasonnorm` swap** (34 contact-quality cols → leakage-safe season-normalized) | PROMOTED — fixed the contact→runs conversion-regime over-bias (2025 fold bias +0.703 → +0.190, **no** 2024 tax). CV MAE 3.4008 → **3.3251** | a shipped correction | registry `notes` (v5 provenance) |
| — | **feature ADDITIONS beyond the above** | ⛔ **No feature addition has ever cleared the deflated gate for the served totals champion.** The feature space has been explored in both directions and is, on current evidence, **exhausted at this architecture** | — | rows above |

### C. Distribution / dependence structure

| when | candidate | result | null state | source |
|---|---|---|---|---|
| 2026-06-22 | **Gaussian copula for home/away run dependence (E2.2)** | **ρ = −0.0035** ⇒ **the copula is UNNECESSARY**; independent convolution is adequate for the *dependence*. The ~24% total-variance shortfall lives in the **marginal dispersion** | **INACTIVE** — a mechanism with nothing to act on (the tail AC *cannot* pass at ρ≈0; recorded as a finding, not an omission) | `e2_2_copula_decision.md` |
| 2026-06-22 | **Period-conditioned dispersion `r`** (the "r drifts 33→8" reading) | **REFUTED as an ESTIMATION ARTIFACT** — train-fit `r` drifts 9.3-wide while held-out `r` is stable (spread 0.53, CV 0.054). ⇒ a single global held-out `r` | refuted hypothesis | same |
| 2026-06-24 | **E2.3 per-side held-out dispersion calibration** | total **calib_80 0.838, PIT-flat ✅**; run_diff PIT ❌ ⇒ gate NOT MET. Served r_home 4.0645 / r_away 3.3977. ⚠️ **never wired into totals serving** | offline win, **orphaned** w.r.t. the totals path | `e2_3_convolution_calibration.md`, `e2_3d_totals_serving_path.md` |
| 2026-07-20 | **E2.1-r per-side count bake-off** (16 configs) — NGBoost vs GBM-Poisson × 3 contracts × dispersion source | **NGBoost DROPPED** (under-dispersed, 3–5× slower); `lgbm_poisson__full__heldout` carries. Incumbent train-fit dispersion **DISQUALIFIED on the calib_80 floor (0.778)** | **learner NULL** (PBO 0.233 read correctly as a tied cluster); minimal fix DSR 1.000 | `e2_1r_bakeoff.md` |
| 2026-07-23 | **E2.4 F5 form bake-off** (192 configs) — poisson / negbin / betabinom / native | **"low mean ⇒ Poisson suffices" REFUTED** (Poisson failed the floor 0.69 on all 4 — F5 IS overdispersed). **Beta-Binomial swept the top 3** at ~½ the carried NegBin's PIT deviation. Strict verdict `INCUMBENT_STANDS` (PBO 0.202, missing 0.20 by 0.002) → shipped betabinom on a recorded product-quality override | ⓘ **`POWER_LIMITED`** | `e2_4_f5_bakeoff.md`, `e2_4_f5_calibration.md` |
| 2026-07-26 | **E2.5** registration of `totals_generative_v1` | Registered. Two corrections recorded: the learner is **LightGBM Poisson, not NGBoost** ("the NGBoost winner" was stale), and the served `r` is **E2.3's held-out (4.0645/3.3977), not the artifact's train-fit 7.449** | registration, not a bake-off (design-block `exempt`) | `e2_5_signal_registration.md` |

### D. Market-facing / edge

| when | candidate | result | null state | source |
|---|---|---|---|---|
| 2026-07-26 | **E2.6 derivative model-vs-market** — alternate_totals + team_totals vs their OWN de-vigged closes, game-level, net of vig | **CLEAN NULL.** 0 of 239 (team_totals) and 0 of 468 (alternate_totals) candidates survive BH-FDR. **Placebo control fired 0 on both** — the gate does not manufacture edge. `totals` market ABSENT (no closes in S3). **F5 held out** (the served signal produces only full-game μ) | genuine absence on historical closes; **forward CLV on the E2.0b live stream can still re-open it via the same harness** | `e2_6_derivative_gates.md` |
| 2026-06-30 | **E13.14 cross-market coherence** — R2 team-totals → game-total | `info_gain` **−0.024** (the posted line predicts the outcome better than the other market's implied quantity). PBO 0.487 ≈ 0.5; the biggest in-sample "edge" was the **negative control** | genuine absence (with the proxy-CLV caveat) | `E13.14` catalog entry |
| 2026-06-23 | **E13.8 market-accuracy benchmark** | The main total's price is a **coin-flip**; any value is in *the number*, already near the variance floor | establishes the ceiling | E13.8 |
| 2026-06 | **Story 29.1 point-accuracy benchmark** vs the Bovada line | **DOWNGRADE** — best model RMSE **4.2596** vs Bovada **3.7298** (+0.5297); MAE gap +0.7404. "No central-estimate edge; totals stay product-only" | genuine absence | `totals_point_accuracy_29_1.md` |
| 2026-06-03 | **Story 10.5 totals α re-calibration** | log-loss-optimal **α = 0.70** on a 4,580-game walk-forward surface | ⛔ **NOT SERVED** — the serving path uses `best_alpha = 0`. Present in `best_alpha.json` as a trap for the unwary | `totals_alpha_tuning.md` |
| 2026-06 | **Epic 26.3 / Layer-4 selective strategy** on totals | negative ROI at every threshold; **second** independent confirmation of the pause | genuine absence | `layer4_selective_strategy.md`, registry |
| 2026-06 | **Story 12.12/12.13 totals CLV meta-model** (`edge_mag`, `pub_align`, `open_extremity`, `edge_sigma`) | **All 3 convergence gates PASS, v0 converged** (top−bottom quartile CLV+ spread +0.1545). ⚠️ in-sample AUC 0.571 but **temporal-split AUC 0.448** — an honest generalization warning, not a gate | converged but generalization-suspect | `bayesian_meta_model_12_13_totals_plus_layer4.md` |
| 2026-06 | **2026 OOS failure analysis** (post-10.6) | The 2026 Brier sign-change is **structural, not fixable at the margin** — challenger 0.3072 at coverage ≥0.8 vs a 2023–25 baseline of 0.2231 | diagnostic | `totals_2026_failure_analysis.md` |

### E. Calibration of the SERVED probability

| when | candidate | result | null state | source |
|---|---|---|---|---|
| 2026-07-16 | **E9.26 measurement** | Served totals **ECE 0.079** vs moneyline 0.029 (n≈852) — "the served totals `P(over)` has NO calibration applied at serve time" | a measured defect | `calibration_e9_26.md` |
| 2026-07-17 | **E13.6b Part A bake-off** — {identity, Platt, isotonic, temperature} on a pooled walk-forward OOF (664 preds / 6 blocks, embargo 1d), 0.03 discrimination floor | **ISOTONIC** — the only method that both clears the discrimination floor (OOF spread 0.0465 vs Platt 0.009 / temperature 0.012, which **collapse P(over) to a constant** — the degenerate-solution trap, correctly rejected) and materially improves calibration (**0.0595 → 0.0145**) | approved, **Part B HELD** | `totals_calibration_e13_6b.md` |
| 2026-07-20/21 | **E13.6b Part-A pick, re-validated on a fresh 7/21 OOF** | 🚨 **DOES NOT REPRODUCE** — isotonic's proper scores blow up (LL 0.89 = overfit), Platt collapses spread, and the spread-floor pick **flips to TEMPERATURE (T≈1.53)**. ⇒ **the frozen artifact is stale; Part B must re-select at wire time.** A live instance of the E2.1-r "re-validate on a fresh fold, don't trust a frozen artifact" lesson | the *machinery* stands, the *pick* does not | `e2_3d_totals_serving_path.md` |
| 2026-07-20 | **E2.3-deploy vs E13.6b** (which totals-calibration path to take) | **E13.6b greenlit; E2.3-deploy NOT run alongside it.** 🔒 standing guard: exactly ONE totals-calibration mechanism ever — if E2.3 ever ships at source it **RETIRES** the calibrator, never stacks | a settled decision | same |
| 2026-08-02 | **MH2.1 conditional calibration** (RMS \|Var(z)−1\| by σ-decile) | 🚨 **RETRACTED — do NOT cite 0.158 / 0.050 / 0.180→0.107 / "Var(z)=1.44 in the calmest decile".** The stratifier binned by the field's worst-calibrated arm and was never validated. Re-scored on a validated stratifier the ordering **flips** | **retracted result** | `mh2_1_rollback.md` §3 |
| 2026-08-02 | **flat-σ (homoscedastic) control** | On a validated stratifier it **LOSES** (0.2519 vs 0.2275 out of sample). ⇒ flattening is a **null to beat**, not a proven improvement | genuine absence | same |

### F. Method-level findings this model produced (they now govern other programs)

- **E2.1-r — the interval-coverage metric inversion.** `|calib_80 − 0.80|` looks principled and is **biased for discrete predictives**: inclusive integer bounds inflate a *correctly specified* count model's coverage to ~0.82–0.86, so the term **rewards under-dispersion**. Cure: gate on **randomized-PIT flatness**, keep coverage a **FLOOR**; sanity-check every selection metric against an **oracle floor** (`test_oracle_is_the_scoring_floor`). Now applied across E2.3/E2.4/E5.2 and the NCAAF/NFL legs.
- **E2.1-r — pricing-optimal ≠ discrimination-optimal.** NGBoost traded mean sharpness for honest variance. A model selected for *calibration* is not automatically right for *edge detection*; any later edge story must **re-select**, never inherit. (MH2.1's registry entry repeats this as a caveat on its own selection basis.)
- **MH2.1 → the conditional-calibration partition lesson.** **A conditional-calibration result is a property of its STRATIFIER.** Before reading any Var(z)-by-stratum / coverage-by-bucket number, **publish the realized-SD-per-bin table with its rank correlation and per-bin SE and prove the bins separate realized dispersion.** A σ-CV floor, a matched heteroscedastic foil, a flattened positive control and a 400-permutation null — MH2.1 ran **all four** — ask "can the instrument detect a known defect?"; **none** asks "does the partition mean anything."
- **MH2.1 → the fold/field design lesson.** The same winner on the same folds clears or fails DSR depending on **field size** and **fold count**; the E7.9 3-fold ceiling was a **window choice, not a data limit** (2015+ is available). Also: a **diagnostic anchor is never a trial** (the `oracle_floor` had leaked into the DSR trial field, setting the gate's own bar).
- **MH2.1 → promotion-mechanics landmines** (all three inherited by any future single-target MLB promotion): a one-target swap breaks **bundle-assuming consumers** (`model_version` is home_win-only; the backfill idempotency key; `mart_clv_labeled_games` hardcoded to `'v6'`); **serve the object that was validated** (a point learner has no `pred_dist`); and a registry change **ships with the box image on merge to `main`** — there is currently **no promotion gate** between merge and serve.
- **E2.2/E2.3 → "a mechanism that cannot act is a finding, not an omission"** (ρ≈0 makes the copula's tail AC unpassable by construction).

---

## Appendix — how to reproduce the served read (laptop, read-only)

```bash
cd <repo-root>
export AWS_DEFAULT_REGION=us-east-2
uv run python - <<'EOF'
import sys; sys.path.insert(0, '.')
from scripts.utils.lakehouse_read import duck_connect, register_views
conn = duck_connect(); register_views(conn, ["daily_model_predictions"])
q = """
select game_date, prediction_type, model_version, totals_model_version,
       count(*) n, max(inserted_at) last_write
from daily_model_predictions
where game_date >= current_date - 8
group by 1,2,3,4 order by 1 desc, 2
"""
for r in conn.execute(q).fetchall(): print(r)
EOF
```

`prediction_type='backfill'` rows are **research re-scorings, not served** — filter them out of any served-state question.
