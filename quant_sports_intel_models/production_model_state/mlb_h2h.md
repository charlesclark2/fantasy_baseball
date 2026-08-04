# Production model state — MLB H2H (home_win moneyline)

_PROD-STATE-1b · written 2026-08-04 · grounded in a LIVE read of the served `daily_model_predictions` (DuckDB-over-S3 lakehouse, laptop, 2026-08-04T07:33Z), `betting_ml/models/model_registry.yaml`, the E1.x/E13.x ablation memos, and the serving code — NOT roadmap prose. best_alpha = 0._

> **One-line state:** the served H2H probability is a **50/50 consensus of two models** — the `home_win` champion classifier (**v6 `glm_elasticnet_deleaked`**, E1.9 clean-slate winner, de-leaked via E1.7+E1.8, 19-feature post-lineup contract) and the run-diff NGBoost's P(diff > 0) — passed through a **TemperatureCalibrator (T = 1.6441)**. It is an **honest, calibrated win-probability product** (served ECE 0.033) on a **confirmed thin-signal target** (corr ≈ 0.08; the market's Brier 0.2475 still beats the served 0.2489). `best_alpha = 0` ⇒ the posterior equals the market and the stored edge/Kelly are structurally ≈ 0 — **no edge, win-rate, or beat-the-market claim rides on this model anywhere**, and both kill-criterion monitors (28.3/28.6b) are shadow/informational with `automated_bets: false`.

---

## ⭐ Version authority + served reconciliation (the field-7 headline)

**Version authority (named first, per the umbrella lesson):** `betting_ml/models/model_registry.yaml` → `home_win.model_version` — **NOT** `sub_model_registry.yaml` (that file registers the Layer-2 *sub-model signals*; the task brief pointed at it, corrected here per cross-session lesson 3). `scripts/predict_today.py:2289` stamps `MODEL_VERSION = _registry["home_win"]["model_version"]` onto every served row, so `daily_model_predictions.model_version` **is** the H2H served version (and *only* the H2H version — see the bundle-stamping landmine in (9)).

**Live served read (laptop DuckDB over the S3 lakehouse, 2026-08-04T07:33Z), reconciled — ✅ MATCH:**

| game_date | tier (`prediction_type`) | served `model_version` | n rows | last write (UTC) |
|---|---|---|---|---|
| 2026-08-03 | morning | `pre_lineup_v6` | 16 | 08-03 13:08 |
| 2026-08-03 | post_lineup | `v6` | 7 | 08-03 23:43 |
| 2026-08-02 | morning | `pre_lineup_v6` | 30 | 08-02 13:35 |
| 2026-08-02 | post_lineup | `v6` | 15 | 08-02 19:48 |

Registry: `model_version: v6`, `pre_lineup_model_version: v6` (served as `pre_lineup_v6` on the morning tier) — **registry and served agree; the match is the proof, not an assumption.** At read time (07:33Z) the 2026-08-04 slate had **no rows yet** — the morning op fires ~13:0x–13:35 UTC daily (visible in the last-write times above), so "no 08-04 rows before 13:00 UTC" is the normal cadence, not an outage; 08-03 is the latest served slate.

Two corroborations worth recording for the umbrella index:
- **`model_version` is home_win-only, live-verified:** on 08-02 the *totals* column `totals_model_version` briefly read `mh2_1` (the rolled-back MH2.1 totals promotion) while `model_version` stayed `v6` — confirming the CLAUDE.md landmine that `model_version` is stamped from `registry["home_win"]` alone and says nothing about the other targets.
- **Registry-internal inconsistency (cosmetic, flagged not fixed — read-only story):** `calibrator_temperature_T: 1.6441` vs `calibrator_refit_status: "…T=1.6953…"` in the same file. Not drift: **1.6953 was the hold-out *selection* T; 1.6441 is the deployed full-window refit** (`h2h_calibration_audit_e13_6.py` selects on a 75/25 hold-out then refits the winner on all n=1167; the registry comment on the `calibrator_temperature_T` line says exactly this). The `calibrator_refit_status` prose quotes the selection T — a difference-by-design plus one stale prose field, not a defect in what serves.

---

## (1) What it predicts + market/output

- **Target:** P(home team wins) for each MLB game — the **moneyline (H2H)** market. Binary label `home_final_score > away_final_score` from `mart_game_results`.
- **Served probability:** `calibrated_win_prob` = TemperatureCalibrator(T=1.6441) applied to `consensus_win_prob` = **0.5 × p_home_win_ngboost + 0.5 × p_home_win_classifier** (hard-coded 50/50; `predict_today.py:1279`, `:2562`). `p_home_win_ngboost` is **not a classifier** — it is the run-diff NGBoost Normal distribution integrated above 0 (`p_over_line(…, total_line=0)`, `predict_today.py:2504-2509`; that model is PROD-STATE-1c's subject). `p_home_win_classifier` is this model — the v6 GLM.
- **Market context:** compared against the de-vigged consensus `h2h_market_implied_prob` and graded/tracked at the target book's actual prices (`layer4_h2h_bovada_ml_home/away`, Bovada per the standing target-book decision).
- **Output surfaces:** the front page + pick detail (`frontend/app/page.tsx`, `frontend/app/picks/[game_pk]/page.tsx` — `model_prob` is always P(home) for h2h; away side rendered as `1 − model_prob`), the EV tracker / performance / bet-log pages, `GET /picks/*` in `app/backend/routers/picks.py` (serves `calibrated_win_prob AS model_prob`; edge display = `|calibrated_win_prob − h2h_market_implied_prob|`), win-probability CI bands (`win_prob_ci_low/high`), and per-pick linear-SHAP drivers (`top_drivers_h2h`). Post-lineup picks are the only actionable tier (`--notify` fires only from the lineup-monitor's `lineup_predict`; the morning email was retired by E9.50, and a pre-lineup game defers its edge to the post-lineup re-score, `predict_today.py:1295-1299`).

## (2) Architecture — champion + why it won

- **Champion (`home_win` classifier leg): v6 `glm_elasticnet_deleaked`** — `make_pipeline(StandardScaler(), LogisticRegression(penalty="elasticnet", l1_ratio=0.5, C=0.5, solver="saga", max_iter=3000, random_state=42))`, wrapped in `PlattCalibratedLinearClassifier` (Platt layer fit on **out-of-fold** `cross_val_predict` probs, KFold(5, shuffle, seed 42), then the pipeline re-fit on all rows). Fit + persisted by `betting_ml/scripts/finalize_v6_champion.py` (E13.11, 2026-06-23 — v6 was never persisted at E1.9; `artifact_path` was null until this script existed). Artifacts: `s3://baseball-betting-ml-artifacts/home_win/glm_elasticnet_deleaked_v6_{post_lineup,pre_lineup}_2026.pkl`; v5 (`xgb_classifier_market_blind_2026.pkl`, 211 feats) retained as one-step rollback.
- **⚠️ Brief correction (lesson 3):** the task brief said "champion = v6 NGBoost". Wrong for H2H — **NGBoost is the run-diff/totals family's winner**; the E1.9 classifier branch for `home_win` fielded xgboost / lightgbm / catboost / glm_elasticnet / stack_mean (+ `floor_no_skill` and `floor_market` as floors, not candidates), and **glm_elasticnet won**. NGBoost enters H2H only as the 50 % run-diff leg of the consensus.
- **E1.9 clean-slate bake-off (2026-06-19/21; `model_bakeoff.py`; Brier gate metric, E1.1 purged CV, 3 folds, seed 42).** Post-lineup, 19-feat FINAL contract, n = 4,857 (`quant_sports_intel_models/baseball/ablation_results/bakeoff_home_win_post_lineup.md`):

  | rank | candidate | Brier | NLL | ECE |
  |---|---|---|---|---|
  | 1 | **glm_elasticnet** | **0.2380** | 0.6685 | 0.0190 |
  | 2 | stack_mean | 0.2382 | 0.6690 | 0.0210 |
  | 3 | catboost | 0.2399 | 0.6723 | 0.0188 |
  | 4 | xgboost | 0.2400 | 0.6727 | 0.0168 |
  | 5 | lightgbm | 0.2407 | 0.6741 | 0.0169 |
  | — | floor_market | 0.2422 | 0.6771 | 0.0215 |
  | — | floor_no_skill | 0.2491 | 0.6914 | 0.0088 |

  A 4-way tie inside the 0.002 noise floor (auto-pick printed `xgboost` on best-ECE; the shipped choice = the primary leader **and** simplest class, glm). Pre-lineup on the 36-feat winner-conditioned re-prune: glm 0.2412 beats `floor_market` 0.2422 (+0.0010) — **the program's first-ever offline PROMOTE** (gate Δ −0.0038, CI [−0.0055, −0.0021]). Selection deflation: **PBO 0.046 (post/19) and 0.013 (pre/36)**, both < 0.2. A 42-feat post-lineup re-prune variant scored better (0.2371) but posted **PBO 0.233 ≥ 0.2 and was NOT shipped** — the deflation gate doing its job.
- **Why the GLM won / why default config:** `home_win` is a **confirmed thin-signal target** — "tree/HPO overfits on lean contracts, so the winner is glm_elasticnet at default config both tiers" (registry E1.9 note). Optuna HPO on the lean contracts posted **PBO 0.372–0.375** ⇒ `--default-config` was the pre-registered resolution ("no search ⇒ no multiple-testing surface ⇒ the overfit gate is N/A, not FAIL", `optuna_hpo.py:192-195`). v6's value = **radical leanness (19/36 vs 374/154 feats) + de-leak correctness, NOT an offline edge** (the post tier is a sub-noise tie).
- **Deploy rationale (E13.0 HOLD → E13.11 reversal):** E13.0 (2026-06-21) HELD deploy — "a 3rd-decimal edge isn't worth bespoke forward infra." E13.11 (2026-06-23) **reversed the HOLD on integrity, not edge**: production was still serving the leaky v5 whose SHAP drivers were dominated by the within-game bullpen leak (`bp_eb_xwoba`) — every pick told users "bullpen is the key driver," misrepresenting the methodology. Post-swap AC met: drivers now `elo_diff` (+0.20, ~2.4× next) → pythagorean → de-leaked bullpen secondary with correct sign. The swap required net-new **exact linear SHAP** (`pick_explanations.home_win_linear_shap`) — TreeSHAP throws on a linear model and would have deferred every explanation.
- **Calibration layer:** `TemperatureCalibrator` (`p' = sigmoid(logit(p)/T)`), **T = 1.6441** (temperature_v2, full-window refit on the n=1,167 v6 backfill, 2026-06-23; hold-out selection T = 1.6953). Loaded from S3 (`calibrator_artifact`), local joblib as fallback, uncalibrated-consensus as loud last resort. Applied to the consensus, not the GLM alone. The prior v5 calibrator (T = 6.2998, temperature_v1) was fit on the leaky v5's overconfident output; re-fit was a mandatory E13.11 gate (`calibrator_refit_required_after: e1_9_v6_promotion` — fired + resolved).

## (3) Feature contract (served)

**Market-blind by contract** — `_assert_market_blind` (`_MARKET_STEMS` guard) + identifier hygiene (`is_identifier_name`) are re-asserted at fit time in `finalize_v6_champion.py:106-109`; market data enters only downstream (the market-implied comparison and the α-blend, both outside the model). Certified leak-clean by the E1.8 full sweep: **"home_win (21) — ALL AS-OF-SAFE"**; "The H2H and run_diff contracts are fully clean" (`ablation_results/feature_leakage_audit.md:107,113`).

**Contract vs served:** post_lineup contract = **19 FINAL** (`feature_columns_xgb_classifier_pruned_clustered_deleaked_2026.json`) → **21 served** (+2 imputation indicators `has_starter_platoon_data`, `is_new_venue`); pre_lineup contract = **36** (`feature_columns_pre_lineup_home_win_reprune_glm.json`, the E1.9 winner-conditioned glm-scored re-prune) → **38 served**. Served sidecars (`feature_columns_v6_home_win_{post,pre}_lineup_served.json`) carry their own `_provenance` (story E13.11, config `{l1_ratio: 0.5, C: 0.5}`) and are derived **post-imputation** so the artifact's `n_features_in_` is guarded against the sidecar length at fit. The pre_lineup contract is guarded to carry **zero lineup-gated features** (regex guard in `finalize_v6_champion.py:273-278`).

**Post-lineup served columns (21) — per-column dictionary** (naming conventions: `_std` = **season-to-date** cumulative within team-season — *not* "standardized"; `_7d/_14d/_30d` = trailing calendar windows; `_30g` = trailing 30 games; all windows leak-safe strict-`<` per E1.8):

| column | block | definition |
|---|---|---|
| `elo_diff` | team strength | home ELO − away ELO (the #1 served driver post-de-leak) |
| `pythagorean_win_exp_diff` | team strength | home − away pythagorean win expectancy |
| `home_avg_xwoba_30d`, `home_avg_xwoba_std` | team rolling offense | home team trailing-30d / season-to-date average xwOBA |
| `home_woba_with_risp_30d` | team rolling offense | home wOBA with runners in scoring position, trailing 30d |
| `away_avg_barrel_pct_std` | team rolling offense | away season-to-date barrel % |
| `away_off_k_pct_std` | team rolling offense | away offense season-to-date strikeout % |
| `away_lineup_avg_attack_angle` | lineup (Statcast bat-tracking) | posted away lineup's average attack angle |
| `home_starter_k_pct_30d` | starter rolling | home starter trailing-30d K% |
| `home_starter_appearances_30d` | starter rolling | home starter appearances in last 30d (workload/freshness) |
| `home_starter_trailing_ra9_30g` | starter rolling | home starter runs-allowed/9 over trailing 30 games |
| `home_starter_whiff_rate_vs_lhb` | starter platoon | home starter whiff rate vs left-handed batters |
| `home_bp_eb_xwoba` | bullpen EB (de-leaked E1.7) | home bullpen equal-weight EB xwOBA posterior, trailing-30d **pre-game** pool (`appearance_date < game_date`) |
| `home_bp_hard_hit_pct_14d` | bullpen rolling | home bullpen hard-hit % allowed, trailing 14d |
| `away_bp_xwoba_against_14d` | bullpen rolling | away bullpen xwOBA against, trailing 14d |
| `home_bp_eb_coverage_pct`, `away_bp_eb_coverage_pct` | bullpen EB meta | share of the pen with real (non-prior) EB posteriors — a data-depth signal that rose to MDA #1/#2 once the leak was removed |
| `home_team_sequential_bullpen_xwoba` | Epic-16 sequential | home bullpen sequential-Bayes posterior (consumer reads `prior_mu`, strict `<` — as-of-safe) |
| `elevation_ft` | park | venue elevation |
| `has_starter_platoon_data` | imputation indicator | 1 if starter platoon splits were present pre-imputation |
| `is_new_venue` | imputation indicator | 1 if the venue lacks history (park factors imputed) |

**Pre-lineup served columns (38):** same blocks minus everything lineup-gated, plus morning-safe additions — full ELO levels (`home_elo`, `away_elo`), both pythagorean levels, `home_games_back` (standings), team rolling offense/pitching aggregates (`away_off_runs_per_game_std`, `home_off_runs_per_game_14d`, `home_off_hard_hit_pct_7d`, `away_pit_k_pct_7d`, `home_pit_k_pct_7d`, `home_pit_k_pct_std`, `away_pit_bb_pct_7d`, `away_pit_woba_against_30d/_std`, `home_pit_woba_against_std`), starter form/workload (`home_starter_bb_pct_14d/_30d/_std`, `home_starter_trailing_fip_30g`, `home_starter_avg_ip_season`, `away_starter_avg_ip_last_3`), platoon/situational splits (`away_vs_lhp_xwoba_std`, `away_woba_with_risp_30d`, `away_xwoba_with_runners_on_30d`), sequential win-prob posteriors (`home/away_team_sequential_win_prob`, `home_team_sequential_bullpen_xwoba`), home-vs-away percent-diff composites (`home_away_bp_xwoba_against_30d_pct_diff`, `home_away_off_woba_30d_pct_diff`, `home_away_starter_k_pct_std_pct_diff`), park (`left_center_ft`), and the same 2 imputation indicators.

**Served vs tried — the feature space WAS explored, by removal (lesson 5):** the contract trajectory is 369/376 raw → E1.3 clustered prune 31 → E1.7 interim 21 (near-total turnover: 26 dropped / 16 added once the bullpen leak was removed; `elo_diff` + `pythagorean_win_exp_diff` *entered* here) → E1.8 FINAL 19 (8 dropped / 6 added — re-derivation vindicated vs trusting the stale prune). Instrument: `derive_clustered_contract.py` — keeps every member of every cluster whose season-stratified paired-bootstrap 95 % CI excludes 0; **158/174 clusters (~92 % of dimensionality) were noise** on the de-leaked MDA. It refuses to derive from a leaky ranking (`bullpen_version=v3` + `stuff_plus_version=deleaked` required) — the codified fix for the E1.8 **stale-ranking bug** (prior contracts had been hand-derived off importance JSONs that each still contained one of the two leaks). Feature **additions** were separately explored and exhausted at the sub-model/signal level — see ledger entries E13.2b/E13.4/E13.10/E1.11 phase-3, all recorded H2H nulls; `incremental_lift_eval.py` is the sanctioned ADD path.

## (4) Training data

- **Source:** `baseball_data.betting_features.feature_pregame_game_features` JOIN `mart_game_results` (label). Loaded via `load_clean_matrix()` (`model_bakeoff.py:316-338`) = cached `load_features(min_year=2021)` + **both de-leak swaps applied in memory** (`_swap_bullpen_v3`, `_swap_stuff_plus_deleaked`). Filters: `has_full_data = TRUE`, both teams ≥ 15 games played, `game_year >= 2021`. Registry stamps: `training_cutoff: 2021+`, `training_rows: 10,272`. Fit with `--refresh-cache` so the E13.7 cold-start convention (league-baseline fills for rookie/call-up NULLs) is in the training frame — the served model was trained under the same cold-start convention it serves under.
- **Standing caveat (documented in the loader itself):** the training read is **NOT point-in-time** (Story 30.3) — offline skill (the old corr 0.42) is a dense-re-read **ceiling**, not the achievable live number. E12 established there is no *structural* train/serve misalignment; the offline-vs-live gap is value-completeness at serve time.
- **CV scheme (selection/gates, not the final fit):** `PurgedWalkForwardSplit` — season walk-forward, `min_train_seasons=3`, `embargo_days=3`, **feature-aware purge band** derived per fold from `max_feature_window(feature_cols)` and anchored to the last *training* game-date (catches prior-season rolling-window tails across the offseason). The final champion is re-fit on ALL rows; CV is the selection instrument.

## (5) Validation — the §0.5 gate it passed

Selection and calibration verdicts, deliberately separated from any edge claim:

- **Bake-off + deflation (selection):** Brier gate under purged/embargoed CV; **PBO 0.046 (post/19), 0.013 (pre/36)** — both pass < 0.2; the better-scoring 42-feat variant failed PBO (0.233) and was rejected; Optuna on lean contracts failed PBO (0.372–0.375) → default config shipped. The one tuned run that passed (pre/154, PBO 0.002, DSR 0.99999) was made moot by the re-prune. Floors: beats `floor_no_skill` by +0.0091 (post); beats `floor_market` only on the pre-tier re-prune (+0.0010) — the post tier is a statistical tie with the market.
- **Promotion gates vs v5:** post_lineup **HOLD** (Δ −0.0011 < 0.002 floor, CI includes 0 — v6 deployed anyway via the E13.11 integrity re-decision, with the gate confirming accuracy non-regression on all 3 seasons); pre_lineup **PROMOTE** (pass 1 Δ −0.00383, CI [−0.00545, −0.00211]; pass 2 Δ −0.00300 — noting the 2024 edge halved on re-pull because feature restatement helped the richer baseline, "not a clean 2nd window").
- **Served calibration (the operative product gate; `served_calibration_v6.json`, n = 1,167 v6-scored 2026 games):** Brier 0.2489 · log-loss 0.691 · **ECE 0.0327** · spread 0.012 · mean_pred 0.5044 vs base rate 0.5338 · **corr 0.0788**. Calibrator selection on the 292-game hold-out: temperature (Brier 0.2481 / ECE 0.0428 / spread 0.0352) won both the Brier-pick and ECE-pick; Platt had better Brier/ECE but was **rejected on the 0.03 spread floor** (0.0185 — a spread-crushed calibrator is the "constant 0.50" failure the floor exists to block); isotonic lost outright. Reliability table: only 2 bins populated (0.4–0.5: pred 0.493 / actual 0.489; 0.5–0.6: pred 0.511 / actual 0.562) — the honest picture of a narrow-band, slightly-underconfident-on-favorites model.
- **The honest market comparison (recorded, not hidden):** on the 918 market-priced games, `market_implied` Brier **0.2475** / ECE 0.0118 / corr 0.1012 vs the served model's 0.2491 / 0.0283 / 0.0708 — **the market still beats the model**. This is why `best_alpha = 0` is the trustworthy setting (E1.11: "the model-DISCRIMINATION edge is genuinely CLOSED on clean inputs").
- **No DSR/BH-FDR claim attaches to the champion itself** — the §0.5 deflation instruments gated the *selection* (PBO) and the HPO decision; the deployment was an integrity re-decision explicitly not predicated on clearing an edge gate.

## (6) Serving path

```
model_registry.yaml (home_win: v6 pkls + calibrator S3 URIs)
  → scripts/predict_today.py            (daily_ingestion_job s19 "morning"; lineup_monitor sensor → lineup_predict "post_lineup")
      GLM P(home) ⊕ run-diff NGBoost P(diff>0)  → 0.5/0.5 consensus → TemperatureCalibrator → calibrated_win_prob
      → INSERT daily_model_predictions   (Snowflake; model_version stamped from registry["home_win"])
  → generate_pick_narratives_op → write_serving_store(.py| _intraday_op) → DynamoDB serving cache (+ S3 fallback)
  → write_api_cache_op → S3 api-cache/{date}/picks/*.json
  → app/backend/routers/picks.py (DynamoDB→S3 read order) → frontend (front page, pick detail, EV tracker, performance)
```

- **Two tiers:** `morning` (pre_lineup model, no notifications — a preview; actionable edge explicitly deferred, `_n_lineup_deferred`) and `post_lineup` (re-score per game once **both sides post a complete 9-slot order** — the INC-32 readiness gate; `--notify` here is the sole pick-alert trigger). Tier dedup at read time prefers a market-data-bearing post_lineup row, else morning (`picks.py` ROW_NUMBER pattern, 6 sites).
- **Gates on the path:** Story 30.13 serve-time freshness gate (slate-level; abstains actionable picks on stale features — HALT-adjacent; had one 6-day false-stale incident from the phase-2b LTZ/NTZ cast bug, fixed 2026-07-29 with a two-sided live proof now required for boolean gates) · `signal_freshness_check` (HALT) · `check_served_prediction_integrity_op` + `check_intraday_fallback_op` (ALERT, page via send_alert — E11.30) · `check_prediction_coverage` (HALT, ≥90 % slate).
- **Deploy mechanics (the standing landmine, not fixed here):** the model registry ships with the box image on merge to `main` (`orchestration_cd.yml` `COPY . .`) — **merging a promotion PR IS the deploy; there is no promotion gate** (operator decision open since 2026-08-02). The E13.11 cutover itself was staged: live daily v6 scoring only began after the merge + Dagster pipeline redeploy — production silently scored v5 for hours while the read-path claimed v6. The captured promotion runbook: merge + Dagster redeploy → calibrator re-fit → permanent-cache invalidation → narratives → serving-store rewrite → verify served drivers/version on a live row.

## (7) Version + last retrain + retrain cadence

- **Served version:** `v6` (post_lineup) / `pre_lineup_v6` (morning) — **reconciled against the live served rows above**. `model_name: glm_elasticnet_deleaked`; `deployed_date/promoted_at: 2026-06-12` (the v5-era registry stamp; the v6 swap `selected_at: 2026-06-23`), `calibrator_last_fit_date: 2026-06-23`.
- **Last champion (re)train:** **2026-06-23** — `finalize_v6_champion.py` (the E13.11 fit-and-persist; v6 had never been persisted at E1.9). That is the *only* champion retrain event since the 30.4 v5 re-promotion (2026-06-12).
- **Retrain cadence: there is NO scheduled champion retrain.** ⚠️ Brief correction (lesson 3): "weekly retrain (INC-1 history)" conflates two things — the **weekly** job is the **Bayesian CLV meta-model** retrain (`weekly_ml_job`, Mondays 10:00 UTC, Story 12.4 — the confidence bar, not the champion), and **INC-1** (resolved 2026-06-18) was *that* job failing on missing `pymc`/`h5py` in the Dagster image. The champion refit is trigger-driven and operator-run; the modernized cadence (triggers: mid-season / All-Star / post-season, each refit a §0.5 bake-off vs the incumbent) is **open story E1.10** (migrated from legacy 7D, in Backlog). Zero `calibrator` references exist in `pipeline/` — calibrator refits are honored by the registry's `calibrator_refit_required_after` triggers and human discipline only.
- **Weekly monitors (not retrains):** `magnitude_monitor_job` (Mondays 12:00 UTC) runs both kill-criterion monitors (28.3 magnitude, 28.6b conviction), read-only WARN-tier reports; attribution windows reset to **2026-06-23** at the v6 swap per the registry's `model_version_policy` ("do not mix bets scored under different champion versions in one kill window").
- **`retrain_tag` semantics:** a versioning discriminator beside `model_version` (CLV dedup partitions on `(game_pk, score_date, model_version, COALESCE(retrain_tag,''))`; `_baseline` = untagged rows). It is part of the backfill idempotency key and hard-coded in places — the MH2.1 promotion-mechanics landmine (audit every bundle-assuming consumer before any single-target promotion) applies verbatim to the next H2H swap.

## (8) Honest-framing status — `best_alpha = 0`, verified on served rows

**Confirmed: no edge / win-rate / beat-the-market claim rides on this model.**

- **Live-read proof (last 7 days of served rows):** `alpha` = **0.0 on every row** (morning n=444, post_lineup n=93); `h2h_edge` ∈ [−1.1e−16, 5.6e−17] on live tiers — machine-epsilon zero, a **presence flag** (read `IS NOT NULL`, never the value, per CLAUDE.md); `calibrated_win_prob` spread 0.409–0.593 (the calibrator is not crushing to a constant — the E13.11 refit working).
- **Mechanism:** α enters *after* calibration, on the market blend only — `posterior = sigmoid(α·logit(model) + (1−α)·logit(market))`; α=0 ⇒ posterior ≡ market ⇒ `compute_actionable_edge` ≈ 0 ⇒ Kelly ≈ 0 (the A2.5 edge-artifact guard). The UI's displayed "edge" is the *diagnostic* gap `calibrated_win_prob − h2h_market_implied_prob` (`layer4_h2h_edge`), a transparency number, not a bet signal. `best_alpha=0` is post-E1.11 **trustworthy**, not provisional: the discrimination edge is genuinely closed on clean inputs.
- **Posture:** `bet_posture: evaluation-pending`, `automated_bets: false`; the 28.6b registry block states **"MANUAL-ONLY ALWAYS … No automated_bets flag ever flips true."** Both kill-criterion monitors are shadow/informational; no CONFIRM has fired since the 2026-06-23 reset. The registry's own framing: the calibrator "makes the weak prob **HONEST, not skillful**" — a thin-signal target (corr ≈ 0.08, Brier ≈ base rate, market still ahead).
- **What the product legitimately is:** a calibrated, leak-free, explainable win probability (ECE 0.033; linear-SHAP drivers led by `elo_diff`/pythagorean) with honest CI bands — a **calibration/transparency product**, finished as such by design, with the edge question deliberately parked at α=0.

## (9) Known limitations + open follow-ups (counted)

**How close to "finished" (= STABLE / TRUSTWORTHY / CALIBRATED, not edge):** effectively finished as a calibration product. The champion, de-leak, contract, calibrator, serving parity, and honest framing are all closed; what remains is maintenance discipline and serving-layer polish, not model work. **Open model-adjacent follow-ups: 8** (of which only #1–#3 touch the model itself; none blocks the "honest calibrated product" claim):

1. **E1.10 — champion retraining cadence (Backlog, open):** no scheduled refit exists; drift accrues until an operator-triggered §0.5 bake-off. The main genuine *model* gap.
2. **Pre-lineup tier calibrator un-fit (registry `calibrator_pre_lineup_status: DEFERRED`):** the morning tier serves the post_lineup-fit temperature; fit its own T once ~150 settled live pre-lineup games accrue. (E13.11 follow-up #1.)
3. **28.3 / 28.6b kill windows still accruing** (n → 150 / 60 since 2026-06-23): the forward real-book test that would CONFIRM or KILL the magnitude/conviction hypotheses hasn't resolved; E13.5 (generic shadow-serve infra, the E13.0 tiebreaker) was never built. Note a structural nit for whenever 28.6b resolves: the conviction gate compares `calibrated_win_prob` against `P_run_diff(home)`, but the former already contains the latter at weight 0.5 — the two "independent estimators" are not independent.
4. **Story 19.3 — qualified-pick gate (open, serving-layer, NOT the model):** the de-facto prod selector is Layer-4 non-abstain; the 3-of-5 `bet_gate` is structurally always-False (4 of 5 criteria are stubs). 19.3 rewires `qualified_bet` = Layer-4 ∧ meta-model P(CLV>0), CLV-tuned; 19.4/19.5 blocked behind it; 19.6 conviction/gate columns NULL on live rows.
5. **No promotion gate (operator decision open 2026-08-02):** merging a registry PR is the deploy. Harmless today only because α=0; must close before any non-zero-α future.
6. **Registry/comment hygiene (cosmetic, 3 items):** `calibrator_refit_status` quotes the hold-out T (1.6953) beside the deployed 1.6441; `model_health_metrics.py` justifies `MIN_SPREAD_PROB=0.025` from the retired T=6.30 regime (the flat-output guard's rationale is stale, though the threshold itself still passed the live spread ~0.03–0.06); `predict_today.py:290`'s DDL comment still says "XGBoost + Platt" for the GLM.
7. **Consensus weights are duplicated magic numbers** (0.5/0.5 at `predict_today.py:1279` and `:2562`) — no single source of truth; a one-sided edit would silently desync the audit column from the served rows.
8. **Per-target `model_version` column / parameterized `retrain_tag`** (the MH2.1 landmine): `model_version` is home_win-only; the next single-target promotion must audit every bundle-assuming consumer (backfill idempotency key, `mart_clv_labeled_games` hard-codes `v6`).

**Known limitations (inherent, documented, not follow-ups):** thin-signal target — served corr ≈ 0.08, spread 0.012, Brier statistically at the base-rate floor, market Brier better (0.2475 vs 0.2489); reliability observable over only 2 probability bins (the model rarely leaves [0.4, 0.6]); offline skill numbers (corr 0.42 era) are dense-re-read ceilings, not live expectations (30.3/E12); the morning tier is a preview (~30 % imputed matrix) whose actionable edge defers to post_lineup by design.

## (10) ⭐ Tried & result ledger

_Everything tested against the `home_win` target with its recorded outcome — so a future audit never re-runs a dead learner class or re-leaks a fixed leak. Null states per `cv_power.classify_null` where recorded._

**Reading rules for this ledger (apply before citing any number):**
- **The de-leak (E1.7/E1.8, 2026-06-18) is the dividing line.** Anything reporting home_win Brier ≈ 0.18–0.22 (Epic 11, Epic 28, Epic 30, the legacy XGB Optuna 0.1951) is **pre-de-leak and leak-inflated**. Post-de-leak honest Brier = **0.241–0.249**, vs no-skill 0.2491 and market 0.2422.
- **Zero home_win feature candidate has ever passed DSR** (best observed 0.580, `f1_startform`, vs the 0.95 gate); best PBO 0.142 (`zone_profile`) had *negative* lift.
- **Only one thing ever cleared a home_win gate on clean data:** the `offense_v2` Layer-3 signal (ΔBrier −0.0133, 3/4 folds) — and the Layer-3 stack is **not served** (`layer3_h2h` is an inert stub; `predict_today` uses the monolithic champion). `stacking_weights.json` still carries the retracted bullpen weights 0.337/0.507 — a known stale artifact.
- **`best_alpha = 0` dominates:** the live posterior is pure market, so every H2H model improvement has zero live *bet* payoff (it retired Story 12.5 + Epic 19 outright); improvements are judged as calibration/transparency work.

### A. Learner / architecture classes

| candidate | when | result | source |
|---|---|---|---|
| **E1.9 bake-off, post_lineup/19f:** glm_elasticnet · stack_mean · catboost · xgboost · lightgbm (+2 floors) | 2026-06 | **glm_elasticnet WON** (0.2380; 4-way tie in the 0.002 noise floor; beats market +0.0022, no-skill +0.0091; PBO 0.046) — trees + stack are dead ends on this contract | `ablation_results/bakeoff_home_win_post_lineup.md` |
| **E1.9 bake-off, pre_lineup/154f** | 2026-06 | **`floor_market` ranked #1 (0.2422)** — every candidate LOST to the market on the wide morning contract (winner margin −0.0013); PBO 0.052 | `…/bakeoff_home_win_pre_lineup.md` |
| **E1.9 re-prune bake-off, pre_lineup/36f** | 2026-06 | glm_elasticnet 0.2412 **beats market +0.0010** — the program's first offline PROMOTE; PBO 0.013 | `…/bakeoff_home_win_pre_lineup_pre_lineup_home_win_reprune_glm.md` |
| **Optuna HPO on the lean v6 contracts** | 2026-06 | **REJECTED — PBO 0.372–0.375** (HPO overfits the thin signal); post tier shipped `--default-config` (n_trials=0, "no search ⇒ no multiple-testing surface"). The pre/154 tuned run passed (PBO 0.002, DSR 0.99999) but was mooted by the re-prune | `tuning_results_v6_glm_elasticnet_home_win_*.json`; registry E1.9 note |
| **Legacy Optuna XGBoost** (50 trials, tuned CV Brier 0.19512, "+20.6%") | pre-2026-06-18 | **Leak-inflated** — the honest post-de-leak equivalent is ~0.241–0.244; do not cite | `tuning_results_xgb_home_win.json` |
| **28.5 Hierarchical Bayesian Bradley-Terry** | Epic 28 | **LOSES** to the champion (Brier 0.2241 vs 0.2231, both far behind market 0.1815 pre-de-leak regime); converged cleanly (R-hat 1.0000) — a real, well-fit, worse model | `ablation_results/h2h_bradley_terry_28_5.md` |
| **11.3 direct Layer-3 classifier (Approach B)** | Epic 11 | **No edge**; mean-CV declared INVALID (sub-model in-sample leakage); only clean season: model 0.2220 vs market 0.1967 | `ablation_results/h2h_v2_approach_b.md`, `h2h_v2_leakage_free.md` |
| **16B.7 run-diff-derived H2H** (Φ(μ/σ) from the NGBoost run-diff posterior alone) | 2026-06-04 | Loses to the direct classifier on NLL (0.6023 vs 0.5957), wins ECE (0.0250 vs 0.0430) — why the serve blends both rather than picking one | `ablation_results/run_diff_derived_h2h_16b7.md` |
| **Epic-12 sequential-enriched challenger → champion** | 2026-06 | Adopted on **calibration only** (ECE 0.043 passes ≤0.05; incumbent 0.063 fails) while losing NLL/raw-Brier — the program's first explicit "calibration is the operative property" promotion (H2H precedent for the E2.1-r pricing-vs-discrimination distinction) | `ablation_results/production_bayesian_home_win.md`; registry notes |
| **30.9 learned ensemble stack vs the 50/50 blend** | Epic 30 | **PROMOTE on paper (Δ −0.0037) but SHELVED** — `best_alpha=0` gives the blend weight no live payoff; the winning variant just picked the classifier (`convex_w_on_clf = 1.0`) | `ablation_results/h2h_stack_eval_30_9.md` |

### B. Leakage classes swept (fixed — do not re-leak)

| leak | found/fixed | mechanism + outcome | source |
|---|---|---|---|
| **Within-game bullpen leak (`bp_eb_xwoba`)** — E1.7 | 2026-06-17/18 | TWO leaks in one feature: reliever EB weighted by `outs_in_game` (within-row peek, invisible to purged CV) + roster-spine leak (rows only for completed games ⇒ serving-null). MDA proof: the feature's value was **~100 % leak** (#1/+0.0352 static → #10/+0.0002 de-leaked; `coverage_pct` rose to #1/#2). Fix: equal-weight trailing-30d strict-`<` pre-game pool; 37/37 games now populate at serve | `E1_7_HANDOFF.md` |
| **FanGraphs Stuff+/arsenal season-to-date join** — E1.8 🟥 | 2026-06-18, commit `eb00a5d` | `season = year(game_date)` with no `< game_date` guard ⇒ full-season value embeds game-G-and-later pitches. Hit 2 *totals* slots; **noise on home_win**. Fixed via prior-season repoint | `ablation_results/feature_leakage_audit.md` |
| **Catcher framing current-season blend** — E1.8 🟨 | 2026-06-18 | Latest-snapshot season total at 70 % weight; noise-ranked, in no contract; documented, low-severity | same |
| **Market columns (9) + name-collision `total_line_std`** — 30.4 | 2026-06-12 | Top-2 market cols were 35 %+32 % of home_win importance — pure market echo. Removed; `_MARKET_STEMS` guard enforces permanently. Promoted via **correctness override** (CV Brier +0.0005 *worse* — accuracy non-regression, compliance mandatory) | `story_30_4_market_blind_deadweight.md` |
| **Identifiers (`home_starter_pitcher_id` #12/453, `venue_id`, `game_year`)** — 30.1 | 2026-06-11 | Memorization/train-serve skew; drop was a **strict accuracy win** (CV 0.2002→0.1991). `is_identifier_name` guard permanent | `story_30_1_identifier_hygiene.md` |
| **E1.8 stale-ranking bug (process leak)** | 2026-06-19 | Prior contracts were hand-derived off importance JSONs that each still contained one leak → `derive_clustered_contract.py` refuses leaky inputs; hand-pruning banned | `build_roadmap.md:123` |
| **Bullpen Layer-3 promote RETRACTED** — E13.3 | 2026-06-21 | The leaky read gave `bullpen_v2` ΔBrier −0.0266 (4/4) and the largest stacking weight (0.507 h2h); on clean data **+0.0001, 2/4 → CONFIRMED REJECT** — "the entire prior lift was the within-game peek" | `sub_model_registry.yaml:492-524`; `e13_3_submodel_meta_reeval.md` |

### C. Feature-family ADDITIONS tried (all recorded H2H nulls — the ADD space is explored, not untried)

All via `incremental_lift_eval.py` (gate: lift>0 on all+non-cold, PBO<0.2, DSR≥0.95):

| family | when | result | source |
|---|---|---|---|
| E1.11 ph-3 `f1_startform` (last-3-start K%/BB%/xwOBA, 6 cols) | 2026-07-02 | NULL — lift +0.0014, PBO 0.642, **DSR 0.580 (the best any home_win add ever posted)**; collinear 0.73–0.86 with existing 14d/30d cols | `e1_11_phase3_home_win_lift.json` |
| E1.11 `f1_staleness` / `traded_pitcher` / `traded_lineup` / `all_enriched` | 2026-07-02 | NULL ×4 — DSR 0.575 / 0.272 / 0.260 / 0.504; trade features *negative* on cold-start games | same |
| E13.2b zone-profile (12 arsenal-shape cols) | 2026-06/07 | NULL — the only add to clear PBO (0.142) but lift **negative** on all strata, DSR 0.073 | `e13_2b_zone_profile_home_win_lift.json`; MH2 null-state row: recorded NULL |
| E13.2b miss-distance | 2026-06/07 | **INVALID, not a null** — candidate column ~constant on eval (n_eval=0, collapsed feature); MH2 null-state: **UNKNOWN** (no fold structure) — an unread result, would need a re-run to become a null | `e13_2b_miss_distance_home_win_lift.json`; `mh2_null_inventory.csv:71` |
| E13.4-B1 TTO-3 penalty | 2026-06-23 | NULL — orthogonal (corr 0.107) but inert; lift −0.0019, DSR 0.003. Negative controls (`sanity_noise`, `sanity_dup`) behaved correctly — the harness is sound | `e13_4_b1_tto_home_win_lift.json` |
| E13.4-B2 bullpen-fatigue × short-leash | 2026-06-23 | NULL — PBO 0.963; GBMs already split on the parent features | `e13_4_b2_fatigue_home_win_lift.json` |
| E13.4-A FanGraphs in-season wRC+ | 2026-06-23 | NULL at the fit-free pre-check — corr(wRC+, wOBA) = 0.9954, fully redundant; never lift-tested. B3 (park × batted-ball) NOT RUN (pre-gated on B1/B2) | `build_roadmap.md:242` |
| E13.10 zone-overlap scalar | 2026-06-24 | NULL — negative lift on non-cold, PBO 0.837 | `e13_10_zone_home_win_lift.json` |
| 28.4 travel/fatigue + starter×offense interactions (11 cols) | Epic 28 | ❌ gate not met — orthogonality FAIL (0.71–0.81) + Brier miss (pre-de-leak numbers) | `h2h_features_28_4.md` |
| 33.5 `exp_*` projected-lineup features (pre-tier) | 2026-06-16 | HOLD — Δ +0.0003 (no-op); projection reconstructs the lineup (corr 0.78) but adds nothing over team-level Class-A features | `pre_lineup_proj_gate_home_win.json` |
| 33.7 actual lineup vs projection | 2026-06-16 | HOLD — Δ +0.0002; **floor ≈ projected ≈ confirmed** ⇒ the lineup-offense block adds ~zero over the team floor; Bayesian prior→posterior lineup idea MOOT, thread closed | `lineup_actual_vs_projected_home_win.json` |
| **E7.9 MiLB-MLE EB blocks (`eb_gb_pct`, `plus_eb`) on home_win** | 2026-07-28/29 | **NOT TESTED — deliberately deferred** (harness not extended to classification; neither served home_win contract touches MLE cols). "home_win's next natural retrain IS that test" — a known deferred gap, the standing candidate for the E1.10 refit. (On the tested targets: 3× `INCUMBENT_STANDS`; MH2 null-states UNDEFINED — PBO uncomputable at <4 folds) | `e7_9_retrain_verdict_summary.md:70-72`; `mh2_null_inventory.csv:143-146` |

### D. Sub-model Layer-3 signals vs home_win (Story 9.5 gate: Δ ≤ −0.001, ≥3/4 folds; de-leaked 2026-06-21 re-eval is authoritative)

| domain | verdict | ΔBrier (clean) | note |
|---|---|---|---|
| `offense_v2` | **✅ promote** (the only clean pass) | −0.0133 | consumed by `layer3_h2h` — which is **unserved** |
| `starter_v1` | defer | −0.0007 | |
| `starter_ip_v1` | defer | −0.0007 | |
| `run_env_v4` | defer | −0.0003 | |
| `defense_quality` | defer | −0.00002 | |
| `bullpen_v2` | **reject (retracted promote)** | +0.0001 | see ledger B |
| `matchup_v1` (archetype) | **reject** | +0.000007, 0/4 | re-eval only after a material Epic-8 architecture change |

### E. Market-interaction / edge mechanisms (the "is there a bet here" question — all dead or shadow)

| candidate | when | result | source |
|---|---|---|---|
| **E13.1 market-anchored residual** | KILLED 2026-06-21 | Anchoring to the line + learning the residual is **strictly worse** (destroys signal); ROI net-vig −1.48 % post tier; DSR excess 0.000 both tiers ⇒ H2H straight-bet edge dead from a **4th** angle (E3.1, E4, E1.9, E13.1) | `edge_residual_home_win_*.json` |
| **E13.8 market-accuracy benchmark** | 2026-06-23 | **No headroom exists:** Pinnacle's close beats the no-skill floor by only 0.002–0.005 Brier *and not every season* — "target calibration-parity with the close, do not chase Brier below the floor" | `e13_8_market_accuracy_benchmark.md` |
| **E13.13 derivative efficiency (h2h_1st_5)** | 2026-07 | CLEAN NULL — all derivative H2H markets mechanically efficient | `e13_13_derivative_efficiency.md` |
| **E13.14 cross-market coherence** | 2026-07 | CLEAN NULL — the market constellation is internally coherent | `e13_14_cross_market_coherence.md` |
| **E13.16 line microstructure** | 2026-07-05 | **METHOD CHECK FAILED** — the placebo control produced a "candidate" (the harness manufactures CLV); H2H arms recorded as untrustworthy/fragile (n=64), forward-accruing only | `e13_16_line_microstructure.md` |
| **28.1 α re-calibration** | 2026-06-10 | Best α=0.1 by log-loss (Δ 0.002) but collapses the magnitude gap −91.5 % → Layer-4 unusable; α=0 stands | `h2h_alpha_recal_seq.md` |
| **28.2 disagreement/conviction gate** | Epic 28 | Full-slate: no mix beats the market. Survivor = the *selective* gate (both estimators within 0.02) — n=85 subset beat market Brier + roi_devig +0.68, **vig-free and within noise** ⇒ shadow-only | `h2h_ensemble_eval_28_2.md` |
| **28.6a real-book ROI check** | Epic 28 | GO for a *forward* test (n=65, Bovada-odds ROI +0.54, CI [+0.16, +1.02]) with its own caveat: the Brier edge is ~68 % confidence, not significant | `h2h_conviction_gate_28_6a.md` |
| **28.3 / 28.6b forward kill windows** | live, reset 2026-06-23 | Accruing; weekly read-only monitors; no CONFIRM. Windows reset on every champion swap (registry `model_version_policy`) | `monitor_{magnitude,conviction}_h2h.py` |
| **30.2 Bayesian-leverage enrichment** | Epic 30 | **REJECT — the classic CV-vs-live inversion:** CV Δ −0.0100 (looked great), live-2026 Δ **+0.0076** (regressed) | `bayesian_leverage_home_win.json` |
| **Epic-28 program verdict** | — | "Head-on point models are exhausted" (4× no-edge); superseded by the `best_alpha=0` pivot which retired 9 mechanism nulls and killed Story 12.5 + Epic 19 | `implementation_guide.md:15991`; `build_roadmap.md:223` |

### F. Calibration arms

| candidate | when | result | source |
|---|---|---|---|
| A2.9 identity (raw consensus) | 2026-06-10 | Selected over the then-live calibrator (spread-crushed); later reversed for the leaky v5 surface | `calibrator_refit_meta.json` |
| **E13.6 TemperatureCalibrator T=6.2998** on v5 | 2026-06-21/22 | v5 was badly overconfident (ECE 0.154; "75 %" picks won 56 %; Brier 0.276 > no-skill) — **uniform across segments incl. dense post_lineup (corr −0.04) ⇒ intrinsic, not serving-sparsity**. T=6.30 → ECE 0.033 | `h2h_calibration_e13_6.md` |
| **E13.11 refit on v6:** temperature vs Platt vs isotonic vs identity | 2026-06-23 | **Temperature won** (hold-out Brier 0.2481/ECE 0.0428/spread 0.0352); **Platt rejected on the 0.03 spread floor** (0.0185 — better Brier/ECE but a near-constant band); isotonic lost. Deployed full-window **T=1.6441** | `served_calibration_v6.json`; `h2h_calibration_audit_e13_6.py` |
| Pre-lineup tier's own temperature | — | **NEVER FIT** (3 settled live games at fit time) — open follow-up (9)#2 | registry `calibrator_pre_lineup_status` |

---

### Brief-vs-verified corrections (cross-session lesson 3 — recorded for the umbrella)

1. **Version authority** is `betting_ml/models/model_registry.yaml['home_win']`, not `sub_model_registry.yaml` (that registers Layer-2 sub-model signals).
2. **The champion is v6 `glm_elasticnet_deleaked`, not "v6 NGBoost"** — NGBoost is the run-diff/totals winner; it reaches H2H only as the 50 % consensus leg (and the E2.1-r "calibration/pricing not discrimination" note the brief cited is a *per-side runs* finding, ledgered here only as family context).
3. **"Weekly retrain (INC-1)" is the CLV meta-model**, not the champion; the champion has no scheduled retrain (open E1.10).
4. **"~19 FINAL" is correct for the post_lineup contract only** (pre_lineup is 36; served 21/38 post-imputation).
