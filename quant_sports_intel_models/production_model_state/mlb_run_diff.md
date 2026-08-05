# Production model state — MLB Run Differential (`run_differential`)

_PROD-STATE-1c · written 2026-08-04 · grounded in a LIVE read of the served `daily_model_predictions` + the served api-cache game-detail blobs + the S3 champion artifacts (DuckDB-over-S3 lakehouse and `aws s3`, laptop, 2026-08-04T23:5xZ), `betting_ml/models/model_registry.yaml`, the E1.x / E13.x / E2.x / E7.9 ablation memos, and the serving code — NOT roadmap prose. best_alpha = 0._

> **One-line state:** run-diff is the program's only **non-user-facing** production model. Two *independent* run-diff producers serve today, and neither is bet: **(A)** the champion **v6 `ngboost_normal_deleaked`** (Normal(μ, σ) over home−away runs; 13-feature post / 124-feature pre contracts) whose `Φ(μ/σ)` is **exactly 50 % of the served H2H win probability** — see [`mlb_h2h.md`](mlb_h2h.md) — and which also drives the served win-probability CI bands and the 28.6b conviction monitor; and **(B)** the **E2.3 joint-derived marginal** (`home_samples − away_samples` off the same per-side NegBin convolution that produces Totals), which is code-complete and wired to the front end but **`null` in every served blob sampled** ⇒ rendering nothing today. `run_diff` has **no market of its own** — the MLB run line has never been ingested (`mart_odds_outcomes` carries only `h2h` / `totals` / `h2h_lay`, live-verified) — so it carries no edge, win-rate, or beat-the-market claim anywhere, and `best_alpha = 0` makes its H2H contribution payoff-free by construction.

---

## ⭐ Version authority + served reconciliation (the field-7 headline)

**Version authority (named first, per umbrella lesson 2) — and the headline finding: run-diff has NO served version stamp at all.**

| producer | version-of-record | served stamp to reconcile against |
|---|---|---|
| **(A) NGBoost champion** | `betting_ml/models/model_registry.yaml` → `run_differential.model_version` (+ `pre_lineup_model_version`) and the S3 `artifact_path` | ⛔ **NONE.** `daily_model_predictions` has `model_version` (home_win-only) and `totals_model_version` (added by MH2.1) — **there is no `run_diff_model_version` column** |
| **(B) E2.3 joint-derived marginal** | `betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json` → `version: "totals_distribution_v1"` (a code/artifact constant, registry-absent — the K-props shape from lesson 2) | the `totals_distribution.version` key inside the served game-detail blob — **currently `null` because the whole block is absent** |

⚠️ **This is a genuine reconciliation GAP, not a mismatch.** `predict_today.py:2289` stamps `MODEL_VERSION = _registry["home_win"]["model_version"]` and MH2.1 added `TOTALS_MODEL_VERSION` beside it *precisely because* the bundle stamp is per-target-blind — but **run-diff was never given the same treatment**. So of the three MLB game targets, run-diff is the only one whose served rows cannot be checked against its registry entry. The `v6` visible on a run-diff row is the **home_win** version that happened to be stamped on the same row. (Registry and code agree that run-diff v6 was promoted in the *same* E13.11 change as home_win v6, so the two have never diverged — but that is a fact about history, not something the served data can prove.)

**What CAN be reconciled, and was — three independent live corroborations:**

1. **The champion artifacts are present and dated to the recorded promotion** (`aws s3 ls`, 2026-08-04):
   `ngboost_normal_deleaked_v6_post_lineup_2026.pkl` — 2026-06-23 **20:07:46**; `ngboost_normal_deleaked_v6_pre_lineup_2026.pkl` — 2026-06-23 **20:11:17**. Both match `promoted_at: 2026-06-23` / `selected_at: 2026-06-23T00:00:00Z`. The v5 rollback (`ngboost_tuned_market_blind_2026.pkl`, 2026-06-12) and the `pre_lineup_v1` rollback are both still on S3 as recorded.
2. **The served columns are populated on today's slate, both tiers** (live DuckDB-over-S3):

   | game_date | tier | n | `pred_run_diff_loc` non-null | mean σ (`scale`) | last write (UTC) |
   |---|---|---|---|---|---|
   | 2026-08-04 | morning | 15 | 15 | 4.291 | 08-04 13:00 |
   | 2026-08-04 | post_lineup | 15 | 15 | 4.330 | 08-04 23:17 |
   | 2026-08-03 | morning | 16 | 16 | 4.228 | 08-03 13:08 |
   | 2026-08-03 | post_lineup | 7 | 7 | 4.269 | 08-03 23:43 |

3. **⭐ The consensus identity reproduces EXACTLY on served rows — the strongest available proof that this model is the H2H leg.** For all 8 sampled 2026-08-04 post_lineup games, the stored `layer4_h2h_conviction_disagree` equals a hand-recomputed `|calibrated_win_prob − Φ(loc/scale)|` **to 4 decimal places** (e.g. gp 822865: loc +0.374, σ 4.306 → P(rd>0) 0.5346 vs `calibrated_win_prob` 0.5162 → 0.0183 stored *and* recomputed; gp 823432: 0.0485/0.0485). `alpha = 0.0` and `h2h_edge` ∈ {0, ±1.1e−16} on every row.

**Registry-hygiene items (cosmetic; flagged not fixed — read-only story). All three are v5-era values left on the v6 entry:**
- **`cv_mae: 3.066` is a LEAK-ERA number on a de-leaked entry.** v6's honest bake-off scores are **CRPS 2.3841 / MAE 3.3603**; 3.066 matches the pre-de-leak / E1.5 purged-CV re-baseline regime (standard 3.0682 / purged 3.0758) of the 374-feature v5. Anyone reading the registry today gets a figure ~0.30 MAE better than the model actually is (see the reading rule in §10).
- **`mlflow_run_id: d53106eca441428a814d477c73ae8d83`** is the Epic-16 *sequential retrain's* run id, per this entry's own retained provenance prose — not a v6 fit.
- **`deployed_date: '2026-06-12'`** is the v5 stamp (v6's own dates are `promoted_at`/`selected_at` = 2026-06-23).

---

## (1) What it predicts + market/output

- **Target:** `run_differential` = `home_final_score − away_final_score` — the home margin. Label from `mart_game_results`. **D4 sign convention (locked 2026-06-04):** μ > 0 ⇒ home favoured; `P(home win) = 1 − Normal.cdf(0; μ, σ) = Φ(μ/σ)`.
- **Output:** a full predictive **distribution**, not a point estimate — `pred_dist(X).params` → `loc` (μ) and `scale` (σ), stored as `daily_model_predictions.pred_run_diff_loc` / `.pred_run_diff_scale`.
- **⛔ Market: NONE. run-diff is not bet, and cannot be — the market it would price does not exist in our data.** `predict_today` emits exactly two markets (`"h2h"` at `:2568`, `"totals"` at `:2583`); there is no run-line/spread market row. `scripts/odds_api_ingestion.py` sets `DEFAULT_MARKETS = ["h2h", "totals"]`, and a live read of `mart_odds_outcomes` returns only `h2h` (3,218,785), `totals` (2,578,180), `h2h_lay` (127,616) — **zero `spreads` rows, ever**. The derivative programmes (E13.13, E2.6) covered `h2h_1st_5_innings`, `totals_1st_1/1st_5_innings`, `alternate_totals`, `team_totals` — the run line was in none of them.
- **⇒ What it is FOR: four in-process consumers, all downstream of H2H or of monitoring.**
  1. **50 % of the served H2H win probability** — `p_home_win_ngboost = p_over_line(Normal, {loc, scale}, total_line=0)`, hard-coded 0.5/0.5 with the classifier leg (`predict_today.py:1279`, `:2562`), then temperature-calibrated. This is the model's principal job. → [`mlb_h2h.md`](mlb_h2h.md) §(2).
  2. **The served win-probability CI bands** (Story 19.7) — `compute_win_prob_beta(cal_win, [ngb_win, clf_win])` uses the *dispersion between* the run-diff leg and the classifier as its per-game σ (plus a 0.03 irreducible base), producing `win_prob_ci_low/high/width`. These **do** render in the app, so run-diff reaches the user indirectly, as interval width.
  3. **The 28.6b conviction kill-criterion** — `layer4_h2h_conviction_flag` = `|calibrated_win_prob − Φ(μ/σ)| ≤ 0.02`, plus the Story 22.4 σ-gate, which consumes `p_home_win_ngboost`.
  4. **Monitoring / audit** — `check_served_prediction_integrity` (flat-output spread guard), `compute_model_health` (`run_differential → run_diff`), `compare_model_versions` (`run_diff_mae`), `backfill_prediction_snapshots`.
  Nothing in `write_serving_store.py`, `app/backend/`, or `frontend/` reads `pred_run_diff_loc`/`_scale` (grep-verified): **the run-diff number itself is never shown to a user.**
- **Producer (B) — the joint-derived marginal.** `betting_ml/utils/totals_distribution.derive_distributions` maps the same independent (home, away) NegBin draws that give Totals into four marginals: `total = home + away`, **`run_diff = home − away`**, and the two team totals. `totals_serving.build_totals_distribution_payload` emits a `run_diff` block (μ, P05…P95 quantile grid, integer PMF, `p_home = P(margin > 0)`), which `frontend/components/totals-distribution.tsx` renders as a margin density with `p_home` called out. **This is a second, architecturally independent estimate of the same quantity** — a Monte-Carlo convolution rather than a direct regression — and it is **not** what the H2H consensus uses.

## (2) Architecture — champion + why it won

### (A) The served champion: v6 `ngboost_normal_deleaked`

- **Learner:** NGBoost with a **Normal** distribution head (`dist: Normal`), raw `NGBRegressor` — `predict_today` calls `.pred_dist(X).params` directly (the MH2.1 landmine: serve the object that was validated; a point learner has no `pred_dist`). **LogNormal is permanently excluded — run-diff can be negative** (stated in the registry across every generation).
- **Served hyperparameters (both tiers, from the served sidecars' `_provenance.config`):** `n_estimators = 400`, `learning_rate = 0.01`, `minibatch_frac = 1.0`, `dist = "Normal"`. Fit + persisted by `betting_ml/scripts/finalize_v6_champion.py --target run_diff --tier {post_lineup,pre_lineup} --refresh-cache` (2026-06-23).
- **Why NGBoost won its bake-off — E1.9 step 1, selection metric CRPS, 3 purged folds, seed 42** (`ablation_results/bakeoff_run_diff_post_lineup.md`; PBO across slate **0.000** ✅):

  | rank | candidate | CRPS | NLL | MAE | PIT-KS | floor? |
  |---|---|---|---|---|---|---|
  | 1 | **`ngboost_normal`** | **2.3841** | 2.8620 | 3.3603 | 0.0314 | |
  | 2 | `catboost` | 2.4001 | 2.8920 | 3.3642 | 0.0324 | |
  | 3 | `stack_mean` | 2.4153 | 2.9145 | 3.3727 | 0.0460 | |
  | 4 | `glm_elasticnet` | 2.4191 | 2.8906 | 3.3844 | 0.0287 | |
  | 5 | `xgboost` | 2.4361 | 2.9431 | 3.3943 | 0.0481 | |
  | — | `floor_no_skill` | 2.5080 | 2.9246 | 3.5610 | 0.1104 | ✅ |
  | 7 | `lightgbm` | 2.5333 | 3.1882 | 3.4323 | 0.0971 | |

  A **2-way tie inside the 0.02 CRPS noise floor, broken on calibration**. The registry's own summary: *"run_diff WON cleanly with the incumbent learner class — no winner-conditioned re-prune needed (its contracts were already MDA-pruned)."* This is the **opposite** of H2H, where the incumbent tree class *lost* to a GLM.
- **Pre-lineup tier — a documented anomaly worth carrying forward:** on the 124-feature morning contract the memo's header declares the winner **`glm_elasticnet`** while the table ranks `ngboost_normal` #1 on CRPS (2.4478 vs 2.4496 — a 0.0018 gap, ~9 % of the noise floor); the header note is *"tie within 0.02 noise floor among 3 → broke on calibration"* and glm's PIT-KS is better (0.0311 vs 0.0333). **What actually SHIPPED on the morning tier is `ngboost_normal`** (registry `pre_lineup: …ngboost_normal_deleaked_v6_pre_lineup_2026.pkl`; the served sidecar's `_provenance.model_class = "ngboost_normal"`). So the pre-tier serves the CRPS leader, not the memo header's calibration-tiebreak winner — a deliberate consistency choice (one learner class across both tiers) that the record does not state explicitly. **Not a defect; an under-documented decision.** (It also foreshadows E7.9 Q4, §10-E: glm_elasticnet beat ngboost_normal on CRPS across all three targets, and the PM ruled NOTE ONLY / DO NOT ACT — a CRPS win is not grounds to swap a learner selected for pricing calibration.)
- **Optuna HPO — a second sharp contrast with H2H.** run-diff's HPO **PASSED both deflation gates on both tiers** (post: PBO 0.086, DSR 0.9983; pre: PBO 0.099, DSR 0.99999; 50 trials, seed 42, CRPS) — where home_win's failed outright at PBO 0.372–0.375. Yet the **tuned gains were sub-noise** (post best CV CRPS 2.3796 tuned vs 2.3841 default = Δ 0.0045, ~22 % of the 0.02 floor; best params `n_estimators 460 / lr 0.00978 / minibatch 0.806`), so the registry shipped **bake-off defaults** anyway: *"config: Optuna HPO (PBO-clean both tiers; gains sub-noise → v6 ≈ bake-off defaults)."* ⇒ for run-diff the "default config" choice is a **sub-noise-gain** decision, not an overfit-gate failure. Do not carry H2H's "HPO overfits this target" story onto run-diff.
- **Promotion gates vs the prior champion — BOTH tiers returned `HOLD`, and v6 shipped anyway on the E13.11 integrity re-decision** (the same call as H2H; run-diff shares the v5 bullpen-leak integrity problem because it feeds the consensus *and* its own driver explanations):

  | tier | baseline | Δ MAE | 95 % bootstrap CI | decision | reading |
  |---|---|---|---|---|---|
  | post_lineup | dense v5 champion (374 feats) | **+0.0012** | [−0.0140, +0.0177] | HOLD | a **~29× leaner (13 vs 374), leak-clean EQUAL** of v5 |
  | pre_lineup | 33.0 morning baseline (124 feats) | **−0.0150** | [−0.0252, −0.0049] | HOLD | *"the STRONGEST sub-floor result in the program"* — **significant** (CI entirely < 0), all folds consistent, HOLD only on the 0.02 effect-size floor |

  Neither tier regressed on any completed season; 2026 corroborated both (−0.0066 / −0.0061). The pre-tier result also vindicates re-pointing the morning gate at the 33.0 baseline (against dense v5 it reads as a wash).
- **⛔ Calibration layer: there is NONE on run-diff.** The `TemperatureCalibrator` (T = 1.6441) is applied to the H2H **consensus**, downstream of the 0.5/0.5 blend — it never touches `pred_run_diff_loc`/`_scale`. The served run-diff distribution is the raw NGBoost predictive, and its honesty rests entirely on NGBoost's own likelihood fit (see §5 for the live coverage check).

### (B) The joint-derived marginal (E2.1 → E2.2 → E2.3 → E2.7)

- **Not a fitted run-diff model.** It is a *derived quantity*: fit two per-side NegBin marginals over runs scored (E2.1/E2.5 `totals_perside_v1`), establish that home/away runs are essentially independent (E2.2 residual Gaussian-copula **ρ = −0.0035**), then draw and subtract. The dependence layer is a `ρ = 0` special case of the E2.2 `sample_gaussian_copula_negbin` sampler, reused rather than forked.
- **The run-diff marginal is why the dispersion is PER-SIDE.** E2.3 stores `r_home = 4.0645` / `r_away = 3.3977` — deliberately *not* a single shared `r` — because, in the module's own words, *"the run-diff calibration is sensitive to the home/away dispersion asymmetry the sum is blind to."* The run-diff leg is therefore the reason the served Totals contract has the shape it has, even though the run-diff leg itself is the one that fails its gate (§5).
- **Architecturally independent of (A).** Different data (per-side runs vs a game-level matrix), different learner (LightGBM-mean + NegBin dispersion vs NGBoost), different distributional family (discrete NegBin difference — an integer-supported PMF — vs a continuous Normal), different serving path. Its `p_home` and (A)'s `Φ(μ/σ)` are two independent estimates of the same probability, **never reconciled against each other anywhere in the code.**

## (3) Feature contract (served)

**Market-blind by contract, and certified leak-clean.** `finalize_v6_champion._assert_market_blind` (`_MARKET_STEMS`) + `is_identifier_name` are re-asserted at fit time for run-diff exactly as for home_win, and the fit refuses a contract column missing from the clean matrix. E1.8's full sweep: **"`run_diff` (15) — ALL AS-OF-SAFE"**; *"The H2H and run_diff contracts are fully clean"* (`feature_leakage_audit.md:115,117`). `home_starter_csw_pct_season`, despite the "season" name, is strict-`<`-guarded.

**Contract vs served:** post_lineup **13 contract → 15 served** (+2 imputation indicators); pre_lineup **124 contract → 126 served**. Served sidecars carry their own `_provenance` (story E13.11, `model_class: ngboost_normal`, the config above) and are derived **post-imputation**.

### Post-lineup served columns (15) — per-column dictionary

Naming conventions match [`mlb_h2h.md`](mlb_h2h.md) §(3): `_std` = **season-to-date** cumulative (not "standardized"); `_7d/_14d/_30d` = trailing calendar windows; `_30g` = trailing 30 games; all windows leak-safe strict-`<` per E1.8.

| column | block | definition (per `dbt/models/feature/schema.yml` + mart SQL) |
|---|---|---|
| `home_bp_eb_coverage_pct` | bullpen EB meta | Fraction of home bullpen innings covered by pitchers with enough data for a reliable EB estimate. **The #1 MDA cluster on this target** (+0.10935) |
| `away_bp_eb_coverage_pct` | bullpen EB meta | Same for the away bullpen. **#2** (+0.07734) |
| `elo_diff` | team strength | Home ELO − away ELO; positive favours home. Shares cluster C4 (**#3**, +0.04392) with the next row |
| `pythagorean_win_exp_diff` | team strength | Home − away Pythagorean expected win % from season runs scored/allowed to date |
| `home_bp_eb_uncertainty` | bullpen EB meta | Home bullpen EB posterior standard deviation (higher = less confident, closer to prior). Cluster C3 with its away twin (**#6**, +0.00254) |
| `away_bp_eb_uncertainty` | bullpen EB meta | Away bullpen EB posterior SD |
| `home_bp_eb_xwoba` | bullpen EB (de-leaked E1.7) | Home bullpen Empirical-Bayes posterior xwOBA-against, shrunk toward league prior; equal-weight trailing-30d **pre-game** pool (`appearance_date < game_date`). **Was #1 pre-de-leak (+0.21385); now #17 (+0.00117)** |
| `home_team_sequential_bullpen_xwoba` | Epic-16 sequential | Home bullpen sequential-Bayes xwOBA-against belief (`prior_mu`, entering-the-game, strict `<`). Clustered with the row above; may lag NULL on the newest games (reliever identification via EB-bullpen membership lags ~3 days) |
| `away_vs_lhp_bb_pct_30d` | team platoon offense | Away **team-level** walk rate vs LHP, trailing 30 d — a team aggregate, **not** confirmed-lineup-gated (**#5**, +0.00443) |
| `home_starter_avg_ip_last_3` | starter workload | Home starter's average decimal IP over their 3 most recent prior starts (any season, strictly `< game_date`); a depth / expected-bullpen-load proxy. NULL when `has_ip_history = false` (**#9**, +0.00186) |
| `away_starter_avg_fastball_velo` | starter stuff | Away starter average fastball velocity (mph), trailing Statcast (**#20**, +0.00097) |
| `home_starter_csw_pct_season` | starter rolling | Home starter's season-to-date called-strike-plus-whiff rate (CSW% = called strikes + whiffs / pitches); strict-`<`-guarded despite the name. NULL for debut starters (**#23**, +0.00077) |
| `away_games_back` | standings | Away team's games behind the division leader as of the day before `game_date` |
| `has_starter_platoon_data` | imputation indicator | True when BOTH starters have prior-season platoon splits (vs LHB and RHB); False for debut/first-season starters |
| `is_new_venue` | imputation indicator | 1 when the venue opened this season (no prior-season park-factor history) |

**⭐ Two structural facts about this contract that an auditor will not guess:**
1. **It is almost entirely a BULLPEN-QUALITY + TEAM-STRENGTH model.** 7 of the 13 contract columns are bullpen EB / sequential-bullpen; 2 are team strength; the top three MDA clusters (coverage_pct ×2, then elo/pythagorean) account for essentially all measurable signal. Starter and offense enter only at the ≤ +0.002 Δmae level. There is **no lineup-offense block at all** — no `*_avg_*` (confirmed-batter) column appears.
2. **The post_lineup champion carries exactly ONE lineup-gated feature, and it is not a batting-order feature.** Cross-checking the 15 served columns against Story 30.8's 81-member Class-B list returns `['home_bp_eb_coverage_pct']` — and the pre-lineup contract's Class-B intersection is **empty** (guard-enforced). The Class-B classification of `home_bp_eb_coverage_pct` is a *data-availability* artifact of the bullpen-EB roster spine (the same spine E1.7 de-leaked on `bp_eb_xwoba`), not lineup information in the batting-order sense. ⇒ **a post-lineup re-score moves the run-diff prediction almost entirely through feature refresh and the model swap, not through the confirmed lineup.**

### Pre-lineup served columns (126) — block composition

The pre contract is a **superset**: it contains **14 of the 15 post-lineup served columns** — everything except `home_bp_eb_coverage_pct` (the one Class-B column). So the two tiers are not different *feature families*, they are the same family at two resolutions (124-wide morning vs a 13-column MDA-pruned slim set). Blocks, generated from the served sidecar (**per-column definitions for every one of these live in the full tested-candidate dictionary below** — every pre-served column is a member of the 169-column pool, so no column is left undescribed):

| block | n | columns |
|---|---:|---|
| starter (rolling / platoon / workload / stuff) | 38 | `away_starter_avg_fastball_velo`, `away_starter_batter_chase_rate_30d`, `away_starter_bb_pct_std`, `away_starter_changeup_stuff_plus`, `away_starter_csw_pct_season`, `away_starter_curveball_stuff_plus`, `away_starter_hard_hit_pct_std`, `away_starter_k_pct_vs_lhb`, `away_starter_k_pct_vs_rhb`, `away_starter_stuff_plus`, `away_starter_whiff_rate_14d`, `away_starter_whiff_rate_std`, `away_starter_whiff_rate_vs_rhb`, `away_starter_xwoba_against_std`, `home_away_starter_k_pct_std_pct_diff`, `home_away_starter_xwoba_against_std_pct_diff`, `home_starter_appearances_30d`, `home_starter_avg_fastball_velo`, `home_starter_avg_ip_last_3`, `home_starter_avg_ip_season`, `home_starter_barrel_pct_7d`, `home_starter_barrel_pct_std`, `home_starter_batter_chase_rate_7d`, `home_starter_batter_chase_rate_std`, `home_starter_bb_pct_30d`, `home_starter_bb_pct_vs_rhb`, `home_starter_changeup_stuff_plus`, `home_starter_csw_pct_season`, `home_starter_hard_hit_pct_14d`, `home_starter_hard_hit_pct_30d`, `home_starter_k_pct_30d`, `home_starter_trailing_fip_30g`, `home_starter_trailing_ra9_30g`, `home_starter_whiff_rate_vs_rhb`, `home_starter_xwoba_7d_minus_std`, `home_starter_xwoba_against_7d`, `home_starter_xwoba_vs_lhb`, `home_starter_xwoba_vs_rhb` |
| team rolling offense | 18 | `away_off_barrel_pct_30d`, `away_off_bb_pct_std`, `away_off_hard_hit_pct_7d`, `away_off_k_pct_std`, `away_off_runs_per_game_std`, `home_off_barrel_pct_30d`, `home_off_bb_pct_30d`, `home_off_bb_pct_7d`, `home_off_bb_pct_std`, `home_off_hard_hit_pct_std`, `home_off_runs_per_game_14d`, `home_off_runs_per_game_30d`, `home_off_runs_per_game_7d`, `home_off_runs_per_game_std`, `home_off_xwoba_14d`, `home_off_xwoba_30d`, `home_off_xwoba_7d`, `home_woba_with_risp_30d` |
| team pitching staff | 17 | `away_pit_barrel_pct_30d`, `away_pit_bb_pct_7d`, `away_pit_woba_against_14d`, `away_pit_woba_against_7d`, `away_pit_woba_against_std`, `away_pit_xwoba_7d_minus_30d`, `away_pit_xwoba_against_14d`, `away_pit_xwoba_against_7d`, `home_pit_barrel_pct_30d`, `home_pit_bb_pct_std`, `home_pit_hard_hit_pct_7d`, `home_pit_hard_hit_pct_std`, `home_pit_k_pct_std`, `home_pit_woba_against_30d`, `home_pit_xwoba_against_14d`, `home_pit_xwoba_against_30d`, `home_pit_xwoba_against_7d` |
| bullpen rolling | 9 | `away_bp_bb_pct_14d`, `home_bp_hard_hit_pct_30d`, `home_bp_innings_pitched_30d`, `home_bp_k_pct_14d`, `home_bp_k_pct_30d`, `home_bp_whiff_rate_14d`, `home_bp_whiff_rate_30d`, `home_bp_xwoba_against_14d`, `home_bp_xwoba_against_30d` |
| team platoon offense | 8 | `away_vs_lhp_bb_pct_30d`, `away_vs_lhp_k_pct_30d`, `away_vs_lhp_woba_30d`, `away_vs_lhp_xwoba_30d`, `away_vs_lhp_xwoba_std`, `home_vs_lhp_slugging_30d`, `home_vs_lhp_woba_std`, `home_vs_rhp_slugging_30d` |
| bullpen EB / sequential-bullpen | 7 | `away_bp_eb_coverage_pct`, `away_bp_eb_uncertainty`, `away_bp_eb_xwoba`, `away_team_sequential_bullpen_xwoba`, `home_bp_eb_uncertainty`, `home_bp_eb_xwoba`, `home_team_sequential_bullpen_xwoba` |
| team strength | 6 | `away_elo`, `elo_diff`, `home_elo`, `home_pythagorean_residual_season`, `home_pythagorean_win_exp`, `pythagorean_win_exp_diff` |
| **starter EB / MiLB-MLE-corrected** | 6 | `away_starter_eb_bb_pct`, `away_starter_eb_k_pct`, `away_starter_eb_xwoba_against_sequential`, `home_starter_eb_k_pct`, `home_starter_eb_xwoba_against`, `home_starter_eb_xwoba_uncertainty` |
| Epic-16 sequential (team) | 4 | `away_team_sequential_win_prob`, `away_team_sequential_woba`, `home_team_sequential_win_prob`, `home_team_sequential_woba` |
| park | 3 | `left_ft`, `right_line_ft`, `runs_per_game_at_park` |
| bullpen usage / fatigue | 3 | `away_bullpen_pitches_prev_7d`, `away_closer_used_prev_1d`, `away_high_leverage_used_prev_2d` |
| matchup composite (pct-diff) | 2 | `home_away_bp_xwoba_against_30d_pct_diff`, `home_away_off_woba_30d_pct_diff` |
| imputation indicator | 2 | `has_starter_platoon_data`, `is_new_venue` |
| standings | 1 | `away_games_back` |
| team defense (OAA) | 1 | `away_team_oaa_prior_season` |
| schedule context | 1 | `series_game_number` |

⚠️ **The pre-tier is the program's only served contract carrying MiLB-MLE-moved columns.** E7.9 measured this precisely: *"only run_diff / pre_lineup carries an MLE-moved column (`home_/away_starter_eb_k_pct` + `away_starter_eb_bb_pct`, 3 of 124). The v6 post_lineup champions are 13-feature slim sets with NO `starter_eb_*` or `avg_eb_*` at all."* Exposure where it applies: 20.3 % of starter rows moved; mean `|Δ eb_k_pct|` 0.022–0.030. → cross-reference [`milb_prospect.md`](milb_prospect.md).

### Served vs tried — the feature space was explored by REMOVAL, and (almost) never by ADDITION

- **Removal is thorough, reproducible, and the tested pool is exactly known.** The E1.8 de-leaked clustered-MDA candidate pool is **byte-identical to the v5 champion's 169-column served contract** (`feature_columns_ngboost_tuned_2026.json` — set-equality verified this session), i.e. **every feature the v5 model served was individually tested for signal on the de-leaked matrix, and nothing else was**. The memo header's "167 features" is the same pool minus the 2 imputation indicators (which the MDA JSON carries as members). 169 members in 144 clusters → **13 FINAL** post-lineup, derived by `derive_clustered_contract.py` (keeps every member of every cluster whose season-stratified paired-bootstrap 95 % CI excludes 0; hand-pruning banned after the E1.8 stale-ranking bug). **134 of 144 clusters covering 156 members were noise — a ~93 % dimensionality cut with no expected accuracy loss**, the most aggressive of the three MLB targets. The complete pool, with each column's served status, MDA verdict and definition, is the dictionary below.
- **⭐ ADDITION was tried EXACTLY ONCE, and an auditor must know this (umbrella lesson 5).** The entire E1.11 / E13.x `incremental_lift_eval.py` ADD programme ran against **`home_win` and `perside_runs` only** — file-level proof: every lift artifact is `*_home_win_lift.json` or `*_perside_runs_lift.json`; **there is no `*_run_diff_lift.json` in the repo.** So zone-profile, miss-distance, TTO-3, bullpen-fatigue×short-leash, zone-overlap, in-season wRC+, `f1_startform`/staleness/traded-player were **never tested against run-diff**. The single exception is **E7.9** (§10-C), which did run both run-diff tiers directly. ⇒ **the run-diff ADD space is largely UNTRIED, not exhausted** — materially different from H2H, where the ADD space is genuinely explored and closed.
- **Cosmetic doc-drift found while building this dictionary (flagged, not fixed):** `dbt/models/feature/schema.yml` describes both `home_bp_eb_uncertainty` and `away_bp_eb_uncertainty` as *"Stub/placeholder; see reference note on sub-model uncertainty columns."* A live read of `feature_pregame_game_features` shows they are **not** stubs — 319/309 distinct values, range 0.0243–0.0595, mean 0.0369 over 26,924 rows. The stub warning was retired by Story 9.7 (for the sibling `feature_pregame_sub_model_signals.*_uncertainty` columns) and the prose here was never updated. Both columns sit in the served 13-feature contract, so the stale wording invites a future session to drop a real feature.


### ⭐ Full tested-candidate dictionary — all 169 columns ever screened for run-diff (the E1.8 MDA pool = the v5 served contract)

_This is the complete answer to "which features were tested during model development." Pool provenance: the 169 columns below are exactly the v5 champion's served contract (`feature_columns_ngboost_tuned_2026.json` — set-equality verified this session), screened feature-by-feature by the de-leaked clustered MDA (`clustered_importance_run_diff_bullpen_v3_stuffplus_deleaked.json` — 144 clusters, 3 permutations/fold, purged CV, season-stratified paired-bootstrap 95 % CI). **served** = which live contract carries the column today (POST = 15-col post_lineup, PRE = 126-col pre_lineup/morning, — = tested and serving nowhere). **verdict** = the MDA screen: ✅ signal (CI excludes 0 → kept in the 13-col post contract) / 🟡 noise (CI crosses 0 → dropped from the post contract; a 🟡 column marked PRE still serves on the morning tier, whose contract predates this screen — it was Class-A-filtered from the same 169 by Story 30.8, not MDA-pruned). Δmae = the cluster's pooled importance (score degradation when the whole cluster is shuffled; a member inherits its cluster's figure). Definitions from `dbt/models/feature/schema.yml` / the mart SQL; naming conventions as in the post table (`_std` = season-to-date, `_7d/_14d/_30d` = trailing calendar windows, `_30g` = trailing 30 games; all strict-`<` leak-safe per E1.8). ⚠️ the two `*_bp_eb_uncertainty` "Stub/placeholder" descriptions below are STALE schema prose — the columns are real (see the doc-drift note above)._

**Reading the block structure:** the "lineup (confirmed batters / archetypes)" block — 37 columns, the largest — was tested and **every member was dropped as noise**; none serves on either tier. Same for the umpire (2) and injury (2) blocks. That is the file-level proof of §3's structural fact: run-diff's signal lives in bullpen-EB metadata and team strength, not in who bats.

**bullpen EB / sequential-bullpen**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `home_bp_eb_coverage_pct` | POST | ✅ signal (+0.1094) | Home bullpen Empirical Bayes coverage percentage — fraction of bullpen innings covered by pitchers with enough data for a reliable EB estimate. |
| `away_bp_eb_coverage_pct` | POST+PRE | ✅ signal (+0.0773) | Away bullpen Empirical Bayes coverage percentage — fraction of bullpen innings covered by pitchers with enough data to receive a reliable EB estimate. |
| `away_bp_eb_uncertainty` | POST+PRE | ✅ signal (+0.0025) | Away bullpen Empirical Bayes posterior standard deviation (higher = less confident, closer to prior). Stub/placeholder; see reference note on sub-model uncertainty columns. |
| `home_bp_eb_uncertainty` | POST+PRE | ✅ signal (+0.0025) | Home bullpen Empirical Bayes posterior standard deviation (higher = less confident, closer to prior). Stub/placeholder; see reference note on sub-model uncertainty columns. |
| `home_bp_eb_xwoba` | POST+PRE | ✅ signal (+0.0012) | Home bullpen Empirical Bayes posterior xwOBA-against, shrunk toward league prior. Decimal. |
| `home_team_sequential_bullpen_xwoba` | POST+PRE | ✅ signal (+0.0012) | Home bullpen sequential xwOBA-against belief (prior_mu, leakage-safe). May be null for the most recent games until the bullpen posterior catches up (reliever identification via eb_bullpen membership lags ~3 days). |
| `away_bp_eb_xwoba` | PRE | 🟡 noise → dropped (+0.0005) | Away bullpen Empirical Bayes posterior xwOBA-against, shrunk toward league prior. Decimal. |
| `away_team_sequential_bullpen_xwoba` | PRE | 🟡 noise → dropped (+0.0005) | Away bullpen sequential xwOBA-against belief (prior_mu). Same ~3-day lag caveat as home_team_sequential_bullpen_xwoba. |

**bullpen rolling**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_bp_bb_pct_14d` | PRE | 🟡 noise → dropped (+0.0024) | Away bullpen walk rate over the trailing 14 days. Decimal. |
| `home_bp_k_pct_14d` | PRE | 🟡 noise → dropped (+0.0010) | Home bullpen strikeout rate over the trailing 14 days. Decimal. |
| `home_bp_k_pct_30d` | PRE | 🟡 noise → dropped (+0.0010) | Home bullpen strikeout rate over the trailing 30 days. Decimal. |
| `home_bp_hard_hit_pct_30d` | PRE | 🟡 noise → dropped (+0.0004) | Home bullpen hard-hit rate allowed over the trailing 30 days. Decimal. |
| `home_bp_whiff_rate_14d` | PRE | 🟡 noise → dropped (+0.0000) | Home bullpen swing-and-miss rate over the trailing 14 days. Decimal. |
| `home_bp_whiff_rate_30d` | PRE | 🟡 noise → dropped (+0.0000) | Home bullpen swing-and-miss rate over the trailing 30 days. Decimal. |
| `home_bp_innings_pitched_30d` | PRE | 🟡 noise → dropped (-0.0000) | Total innings pitched by the home bullpen over the trailing 30 days. Decimal. |
| `home_bp_xwoba_against_30d` | PRE | 🟡 noise → dropped (-0.0004) | Home bullpen xwOBA allowed over the trailing 30 days. Decimal. |
| `home_bp_xwoba_against_14d` | PRE | 🟡 noise → dropped (-0.0007) | Home bullpen xwOBA allowed over the trailing 14 days. Decimal. |

**bullpen usage/fatigue**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_bullpen_pitches_prev_7d` | PRE | 🟡 noise → dropped (+0.0012) | Total pitches thrown by the away bullpen in the 7 days before game_date (cumulative workload proxy). Integer. |
| `away_closer_used_prev_1d` | PRE | 🟡 noise → dropped (-0.0000) | Flag (1/0) indicating the away team's closer pitched the day before game_date. |
| `away_high_leverage_used_prev_2d` | PRE | 🟡 noise → dropped (-0.0001) | Flag (1/0) indicating the away team used a high-leverage reliever in the 2 days before game_date. |

**Epic-16 sequential (team)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `home_team_sequential_woba` | PRE | 🟡 noise → dropped (+0.0001) | Home team's sequential offensive belief — the off_xwoba posterior ENTERING this game (prior_mu = posterior after the team's previous game, so it is leakage-safe). Tracks within-season run-environment drift the static rolling/EB features miss. Non-null for all 2021+ regular-season games (a team's season opener carries the cold-start league prior ≈0.324). tests: # Populated for ~all 2021+ games; tolerates the small recency lag (recent # games not yet in team_sequential_posteriors) + rare win_prob gaps # (NULL home_team_won). A systematic join/abbrev break would tank this. - dbt_utils.not_null_proportion: arguments: at_least: 0.97 config: where: "game_year >= 2021" |
| `away_team_sequential_woba` | PRE | 🟡 noise → dropped (-0.0001) | Away team's sequential offensive belief (off_xwoba prior_mu, leakage-safe pre-game). See home_team_sequential_woba. tests: # Populated for ~all 2021+ games; tolerates the small recency lag (recent # games not yet in team_sequential_posteriors) + rare win_prob gaps # (NULL home_team_won). A systematic join/abbrev break would tank this. - dbt_utils.not_null_proportion: arguments: at_least: 0.97 config: where: "game_year >= 2021" |
| `away_team_sequential_win_prob` | PRE | 🟡 noise → dropped (-0.0010) | Away team Beta-Binomial win-probability posterior (prior_mu). See home_team_sequential_win_prob. tests: # Populated for ~all 2021+ games; tolerates the small recency lag (recent # games not yet in team_sequential_posteriors) + rare win_prob gaps # (NULL home_team_won). A systematic join/abbrev break would tank this. - dbt_utils.not_null_proportion: arguments: at_least: 0.97 config: where: "game_year >= 2021" |
| `home_team_sequential_win_prob` | PRE | 🟡 noise → dropped (-0.0062) | Home team Beta-Binomial win-probability posterior entering this game (prior_mu — the Pythagorean-win analogue). Non-null for 2021+ games (cold-start Beta(4,4)=0.500 on the season opener). tests: # Populated for ~all 2021+ games; tolerates the small recency lag (recent # games not yet in team_sequential_posteriors) + rare win_prob gaps # (NULL home_team_won). A systematic join/abbrev break would tank this. - dbt_utils.not_null_proportion: arguments: at_least: 0.97 config: where: "game_year >= 2021" |

**imputation indicator**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `has_starter_platoon_data` | POST+PRE | 🟡 noise → dropped (+0.0000) | True when both home and away starters have prior-season xwOBA-against platoon splits (vs LHB and vs RHB) available. False when either starter is a debut or first-season pitcher with no prior-season data; used to flag whether the platoon-adjusted lineup features are populated. |
| `is_new_venue` | POST+PRE | 🟡 noise → dropped (+0.0000) | Flag (1/0) indicating the game is at a venue that opened this season; no prior-season park factor history available. |

**injury (dropped block)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_injured_player_count` | — | 🟡 noise → dropped (+0.0008) | Count of away team players on the injured list (IL) as of game_date. |
| `home_injured_player_count` | — | 🟡 noise → dropped (-0.0000) | Count of home team players on the injured list (IL) as of game_date. |

**lineup (confirmed batters / archetypes — POST-candidate only, all dropped)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_lineup_archetype_pa_coverage` | — | 🟡 noise → dropped (+0.0018) | Fraction of away lineup slots (0–1) that have a prior-season plate-appearance archetype cluster assignment. |
| `away_avg_whiff_rate_30d` | — | 🟡 noise → dropped (+0.0015) | Away lineup average swing-and-miss rate over the trailing 30 days. Decimal. |
| `home_avg_xwoba_30d` | — | 🟡 noise → dropped (+0.0014) | Home lineup average xwOBA over the trailing 30 days. Decimal. |
| `home_avg_woba_vs_rhp` | — | 🟡 noise → dropped (+0.0011) | Home lineup average wOBA vs right-handed pitchers (prior season platoon split). Decimal. |
| `home_lineup_archetype_pa_coverage` | — | 🟡 noise → dropped (+0.0008) | Fraction of home lineup slots (0–1) that have a prior-season plate-appearance archetype cluster assignment. |
| `home_avg_hard_hit_pct_vs_lhp` | — | 🟡 noise → dropped (+0.0007) | Home lineup average hard-hit rate vs left-handed pitchers (prior season platoon split). Decimal. |
| `home_lineup_bat_speed_vs_starter_velo` | — | 🟡 noise → dropped (+0.0007) | Home lineup average bat speed minus the away starter's average fastball velocity (mph); positive means batters are faster than the starter's heater. |
| `away_avg_woba_30d` | — | 🟡 noise → dropped (+0.0005) | Away lineup average wOBA over the trailing 30 days. Decimal. |
| `away_avg_woba_std` | — | 🟡 noise → dropped (+0.0005) | Away lineup average wOBA, season-to-date. Decimal. |
| `away_avg_bb_pct_30d` | — | 🟡 noise → dropped (+0.0005) | Away lineup average walk rate over the trailing 30 days. Decimal. |
| `away_avg_bb_pct_std` | — | 🟡 noise → dropped (+0.0005) | Away lineup average walk rate, season-to-date. Decimal. |
| `away_lineup_iso_vs_starter_archetype` | — | 🟡 noise → dropped (+0.0004) | Away lineup isolated power (ISO) against the home starter's pitcher archetype cluster (prior season). Decimal. |
| `away_avg_k_pct_vs_rhp` | — | 🟡 noise → dropped (+0.0003) | Away lineup average strikeout rate vs right-handed pitchers (prior season platoon split). Decimal. |
| `home_avg_chase_rate_30d` | — | 🟡 noise → dropped (+0.0003) | Home lineup average chase rate (swings on pitches outside the zone) over the trailing 30 days. Decimal. |
| `home_avg_hard_hit_pct_vs_rhp` | — | 🟡 noise → dropped (+0.0002) | Home lineup average hard-hit rate vs right-handed pitchers (prior season platoon split). Decimal. |
| `away_lineup_xwoba_vs_starter_archetype` | — | 🟡 noise → dropped (+0.0001) | Away lineup xwOBA against the home starter's pitcher archetype cluster (prior season). Decimal. |
| `home_n_power_pull` | — | 🟡 noise → dropped (+0.0001) | Count of home lineup batters classified as "power pull" archetype (high pull rate, power-oriented swing). |
| `home_avg_hard_hit_pct_std` | — | 🟡 noise → dropped (+0.0001) | Home lineup average hard-hit rate (exit velo ≥ 95 mph), season-to-date. Decimal. |
| `home_lineup_k_pct_vs_starter_archetype` | — | 🟡 noise → dropped (+0.0000) | Home lineup strikeout rate against the away starter's pitcher archetype cluster (prior season). Decimal. |
| `away_n_high_whiff` | — | 🟡 noise → dropped (+0.0000) | Count of away lineup batters classified as "high-whiff" archetype based on prior-season Statcast profile. |
| `away_avg_eb_bb_pct` | — | 🟡 noise → dropped (+0.0000) | Away lineup Empirical Bayes posterior walk rate (shrinks per-batter raw BB% toward league prior). Decimal. |
| `away_avg_eb_iso` | — | 🟡 noise → dropped (+0.0000) | Away lineup Empirical Bayes posterior isolated power (ISO = SLG - AVG), shrunk toward league prior. Decimal. |
| `away_avg_eb_woba_sequential` | — | 🟡 noise → dropped (+0.0000) | Away lineup sequential Bayesian posterior wOBA entering this game, updated game-by-game within season. Leakage-safe. Decimal. |
| `home_avg_eb_bb_pct` | — | 🟡 noise → dropped (+0.0000) | Home lineup Empirical Bayes posterior walk rate, shrunk toward league prior. Decimal. |
| `home_avg_eb_iso` | — | 🟡 noise → dropped (+0.0000) | Home lineup Empirical Bayes posterior isolated power (ISO), shrunk toward league prior. Decimal. |
| `home_avg_eb_woba` | — | 🟡 noise → dropped (+0.0000) | Home lineup Empirical Bayes posterior wOBA, shrunk toward league prior. Decimal. |
| `away_avg_hard_hit_pct_std` | — | 🟡 noise → dropped (-0.0001) | Away lineup average hard-hit rate (exit velo ≥ 95 mph), season-to-date. Decimal. |
| `home_avg_xwoba_vs_lhp` | — | 🟡 noise → dropped (-0.0001) | Home lineup average xwOBA vs left-handed pitchers (prior season platoon split). Decimal. |
| `away_lineup_vs_home_starter_k_pct_adj` | — | 🟡 noise → dropped (-0.0001) | Weighted average of the home starter's prior-season K% platoon splits, weighted by away lineup handedness composition. Null when home starter platoon splits are null. |
| `home_avg_woba_30d` | — | 🟡 noise → dropped (-0.0002) | Home lineup average wOBA over the trailing 30 days. Decimal. |
| `away_avg_woba_vs_rhp` | — | 🟡 noise → dropped (-0.0005) | Away lineup average wOBA vs right-handed pitchers (prior season platoon split). Decimal. |
| `away_lineup_vs_home_starter_h2h_xwoba` | — | 🟡 noise → dropped (-0.0007) | Lineup-average Bayesian-shrunk xwOBA against the home starter. |
| `away_avg_xwoba_30d` | — | 🟡 noise → dropped (-0.0008) | Away lineup average xwOBA over the trailing 30 days. Decimal. |
| `away_avg_xwoba_std` | — | 🟡 noise → dropped (-0.0008) | Away lineup average xwOBA, season-to-date. Decimal. |
| `away_lineup_avg_woba_vs_cluster` | — | 🟡 noise → dropped (-0.0012) | Average shrinkage-adjusted wOBA of the away lineup batters vs. the home starter's pitcher cluster. Null when no cluster or batter coverage. tests: - dbt_utils.accepted_range: arguments: min_value: 0 max_value: 1 config: where: "away_lineup_avg_woba_vs_cluster is not null" |
| `home_lineup_vs_away_starter_bb_pct_adj` | — | 🟡 noise → dropped (-0.0012) | Weighted average of the away starter's prior-season BB% platoon splits, weighted by home lineup handedness composition. Null when away starter platoon splits are null. |
| `home_lineup_vs_away_starter_h2h_woba` | — | 🟡 noise → dropped (-0.0027) | Lineup-average Bayesian-shrunk wOBA the home lineup has produced against the away starter across prior PA. Returns the league prior (0.320) for batters with no prior PA against this starter. |

**matchup composite (pct-diff)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `home_away_starter_k_pct_std_pct_diff` | PRE | 🟡 noise → dropped (+0.0015) | Percentage difference in season-to-date starter strikeout rate between home and away starters; (home - away) / mean(home, away). |
| `home_away_bp_xwoba_against_30d_pct_diff` | PRE | 🟡 noise → dropped (+0.0012) | Percentage difference in 30-day bullpen xwOBA-against between home and away teams; (home - away) / mean(home, away). Positive = home bullpen allowing more contact quality. |
| `home_away_off_woba_30d_pct_diff` | PRE | 🟡 noise → dropped (-0.0000) | Percentage difference in 30-day offense wOBA between home and away teams; (home - away) / mean(home, away). |
| `home_away_injury_adj_avg_woba_30d_pct_diff` | — | 🟡 noise → dropped (-0.0002) | Percentage difference in injury-adjusted 30-day lineup wOBA between home and away teams; (home - away) / mean(home, away). |
| `home_away_starter_xwoba_against_std_pct_diff` | PRE | 🟡 noise → dropped (-0.0008) | Percentage difference in season-to-date starter xwOBA-against between home and away starters; (home - away) / mean(home, away). |

**park**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `right_line_ft` | PRE | 🟡 noise → dropped (+0.0004) | Right-field foul-line fence distance (ft), from the Stats API venue fieldInfo (stg_statsapi_venues; no schema.yml description) |
| `runs_per_game_at_park` | PRE | 🟡 noise → dropped (+0.0002) | Prior-season average total runs per game at this venue (both teams combined). Null for 2015 games (no 2014 history) and for venues with fewer than 10 games in the prior season. tests: - not_null: config: warn_if: ">= 100" error_if: ">= 10000" |
| `left_ft` | PRE | 🟡 noise → dropped (-0.0005) | Left-field foul-line fence distance (ft), from the Stats API venue fieldInfo (stg_statsapi_venues; no schema.yml description) |

**schedule context**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `series_game_number` | PRE | 🟡 noise → dropped (+0.0001) | Position of this game within the current series (1, 2, 3, or 4+), from stg_statsapi_games. Relevant for bullpen deployment modeling — games 2 and 3 of a series deplete bullpens from prior outings. Non-null for all regular season games with schedule data. |

**standings**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_games_back` | POST+PRE | ✅ signal (-0.0003) | Away team's games behind the division leader in the standings as of the day before game_date. |

**starter (rolling/platoon/workload/stuff)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `home_starter_avg_ip_last_3` | POST+PRE | ✅ signal (+0.0019) | Average decimal innings pitched by the home starter over their 3 most recent prior starts (any season, strictly < game_date). Proxy for expected depth and bullpen workload — a low value signals the bullpen is likely to throw more innings. Null when has_ip_history = false. |
| `away_starter_avg_fastball_velo` | POST+PRE | ✅ signal (+0.0010) | Away starter average fastball velocity in mph (trailing Statcast data). |
| `home_starter_csw_pct_season` | POST+PRE | ✅ signal (+0.0008) | Home starter's season-to-date called-strike-plus-whiff rate (CSW%; pitches ending in a called strike or swinging strike / total pitches). Null for debut starters with no current-season appearances. |
| `away_starter_bb_pct_std` | PRE | 🟡 noise → dropped (+0.0007) | Away starter walk rate, season-to-date. Decimal. |
| `home_starter_changeup_stuff_plus` | PRE | 🟡 noise → dropped (+0.0006) | Home starter Stuff+ score for the changeup (100 = league average; higher is better for pitcher). |
| `away_starter_whiff_rate_14d` | PRE | 🟡 noise → dropped (+0.0006) | Away starter swing-and-miss rate over the trailing 14 days. Decimal. |
| `away_starter_whiff_rate_std` | PRE | 🟡 noise → dropped (+0.0006) | Away starter swing-and-miss rate, season-to-date. Decimal. |
| `away_starter_csw_pct_season` | PRE | 🟡 noise → dropped (+0.0005) | Away starter's season-to-date CSW% (called strikes + whiffs / total pitches). Null for debut starters with no current-season appearances. |
| `home_starter_xwoba_7d_minus_std` | PRE | 🟡 noise → dropped (+0.0005) | Home starter xwOBA-against (7-day) minus xwOBA-against (season-to-date); positive means recent form is worse than season average. |
| `home_starter_xwoba_against_7d` | PRE | 🟡 noise → dropped (+0.0005) | Home starter xwOBA allowed over the trailing 7 days. Decimal. |
| `away_starter_hard_hit_pct_std` | PRE | 🟡 noise → dropped (+0.0005) | Away starter hard-hit rate allowed, season-to-date. Decimal. |
| `home_starter_k_pct_30d` | PRE | 🟡 noise → dropped (+0.0004) | Home starter's 30-day rolling strikeout rate (K/batters faced) ending strictly before game_date. Null for debut pitchers or early-season games with insufficient history. |
| `home_starter_barrel_pct_std` | PRE | 🟡 noise → dropped (+0.0003) | Home starter barrel rate allowed, season-to-date. Decimal. |
| `away_starter_batter_chase_rate_30d` | PRE | 🟡 noise → dropped (+0.0003) | Away starter opponent chase rate (swings on pitches outside the zone) over the trailing 30 days. Decimal. |
| `home_starter_bb_pct_30d` | PRE | 🟡 noise → dropped (+0.0002) | Home starter walk rate over the trailing 30 days. Decimal. |
| `home_starter_xwoba_vs_lhb` | PRE | 🟡 noise → dropped (+0.0001) | Home starter xwOBA allowed vs left-handed batters (prior season platoon split). Decimal. |
| `home_starter_xwoba_vs_rhb` | PRE | 🟡 noise → dropped (+0.0001) | Home starter xwOBA allowed vs right-handed batters (prior season platoon split). Decimal. |
| `away_starter_whiff_rate_vs_rhb` | PRE | 🟡 noise → dropped (+0.0001) | Away starter swing-and-miss rate vs right-handed batters (prior season platoon split). Decimal. |
| `away_starter_k_pct_vs_lhb` | PRE | 🟡 noise → dropped (+0.0001) | Away starter strikeout rate vs left-handed batters (prior season platoon split). Decimal. |
| `home_starter_avg_fastball_velo` | PRE | 🟡 noise → dropped (-0.0000) | Home starter average fastball velocity in mph (trailing Statcast data). |
| `home_starter_batter_chase_rate_std` | PRE | 🟡 noise → dropped (-0.0001) | Home starter opponent chase rate, season-to-date. Decimal. |
| `away_starter_changeup_stuff_plus` | PRE | 🟡 noise → dropped (-0.0002) | Away starter Stuff+ score for the changeup (100 = league average; higher is better for pitcher). |
| `home_starter_trailing_fip_30g` | PRE | 🟡 noise → dropped (-0.0002) | Home starter trailing FIP over the last 30 games started. |
| `home_starter_avg_ip_season` | PRE | 🟡 noise → dropped (-0.0002) | Season-to-date average decimal innings pitched per start for the home starter, using only starts in the current season before this game. Stable seasonal baseline. Null when the starter has no same-season prior starts. |
| `home_starter_whiff_rate_vs_rhb` | PRE | 🟡 noise → dropped (-0.0002) | Home starter swing-and-miss rate vs right-handed batters (prior season platoon split). Decimal. |
| `home_starter_trailing_ra9_30g` | PRE | 🟡 noise → dropped (-0.0003) | Home starter trailing runs allowed per 9 innings over the last 30 games started. |
| `home_starter_batter_chase_rate_7d` | PRE | 🟡 noise → dropped (-0.0003) | Home starter opponent chase rate over the trailing 7 days. Decimal. |
| `away_starter_k_pct_vs_rhb` | PRE | 🟡 noise → dropped (-0.0003) | Away starter strikeout rate vs right-handed batters (prior season platoon split). Decimal. |
| `home_starter_appearances_30d` | PRE | 🟡 noise → dropped (-0.0004) | Number of appearances (starts) by the home starter in the trailing 30 days. |
| `home_starter_bb_pct_vs_rhb` | PRE | 🟡 noise → dropped (-0.0004) | Home starter walk rate vs right-handed batters (prior season platoon split). Decimal. |
| `home_starter_hard_hit_pct_14d` | PRE | 🟡 noise → dropped (-0.0005) | Home starter hard-hit rate allowed over the trailing 14 days. Decimal. |
| `home_starter_hard_hit_pct_30d` | PRE | 🟡 noise → dropped (-0.0005) | Home starter hard-hit rate allowed over the trailing 30 days. Decimal. |
| `home_starter_barrel_pct_7d` | PRE | 🟡 noise → dropped (-0.0005) | Home starter barrel rate allowed over the trailing 7 days. Decimal. |
| `away_starter_curveball_stuff_plus` | PRE | 🟡 noise → dropped (-0.0009) | Away starter's Stuff+ score for their curveball (100 = league average). Null when the pitcher does not throw a curveball or Stuff+ data is unavailable. |
| `away_starter_xwoba_against_std` | PRE | 🟡 noise → dropped (-0.0009) | Away starter xwOBA allowed, season-to-date. Decimal. |
| `away_starter_stuff_plus` | PRE | 🟡 noise → dropped (-0.0010) | Away starter overall Stuff+ score across all pitch types (100 = league average; higher is better for pitcher). |

**starter EB / MLE-corrected**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_starter_eb_bb_pct` | PRE | 🟡 noise → dropped (+0.0000) | Away starter Empirical Bayes posterior walk rate, shrunk toward league prior. Decimal. |
| `away_starter_eb_k_pct` | PRE | 🟡 noise → dropped (+0.0000) | Away starter Empirical Bayes posterior strikeout rate, shrunk toward league prior. Decimal. |
| `away_starter_eb_xwoba_against_sequential` | PRE | 🟡 noise → dropped (+0.0000) | Away starter sequential Bayesian posterior xwOBA-against entering this game, updated game-by-game within season. Leakage-safe. Decimal. |
| `home_starter_eb_k_pct` | PRE | 🟡 noise → dropped (+0.0000) | Home starter Empirical Bayes posterior strikeout rate, shrunk toward league prior. Decimal. |
| `home_starter_eb_xwoba_against` | PRE | 🟡 noise → dropped (+0.0000) | Home starter Empirical Bayes posterior xwOBA-against, shrunk toward league prior. Decimal. |
| `home_starter_eb_xwoba_uncertainty` | PRE | 🟡 noise → dropped (+0.0000) | Home starter Empirical Bayes posterior standard deviation for xwOBA-against (higher = less confident, closer to prior). |

**team defense (OAA)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_team_oaa_prior_season` | PRE | 🟡 noise → dropped (+0.0001) | Away team Outs Above Average (OAA) from the prior season (0 = league average; positive = above-average defense). |

**team pitching staff**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `home_pit_bb_pct_std` | PRE | 🟡 noise → dropped (+0.0044) | Home team pitching staff walk rate, season-to-date. Decimal. |
| `home_pit_hard_hit_pct_7d` | PRE | 🟡 noise → dropped (+0.0013) | Home team pitching staff hard-hit rate allowed over the trailing 7 days. Decimal. |
| `away_pit_xwoba_7d_minus_30d` | PRE | 🟡 noise → dropped (+0.0008) | Away pitching staff xwOBA allowed (7-day) minus xwOBA allowed (30-day); positive means recent form is worse than the 30-day trend. |
| `home_pit_xwoba_against_7d` | PRE | 🟡 noise → dropped (+0.0008) | Home team pitching staff xwOBA allowed over the trailing 7 days. Decimal. |
| `away_pit_woba_against_14d` | PRE | 🟡 noise → dropped (+0.0006) | Away team pitching staff wOBA allowed over the trailing 14 days. Decimal. |
| `away_pit_woba_against_7d` | PRE | 🟡 noise → dropped (+0.0006) | Away team pitching staff wOBA allowed over the trailing 7 days. Decimal. |
| `home_pit_barrel_pct_30d` | PRE | 🟡 noise → dropped (+0.0002) | Home team pitching staff barrel rate allowed over the trailing 30 days. Decimal. |
| `home_pit_hard_hit_pct_std` | PRE | 🟡 noise → dropped (+0.0001) | Home team pitching staff hard-hit rate allowed, season-to-date. Decimal. |
| `away_pit_bb_pct_7d` | PRE | 🟡 noise → dropped (+0.0000) | Away team pitching staff walk rate over the trailing 7 days. Decimal. |
| `home_pit_k_pct_std` | PRE | 🟡 noise → dropped (-0.0000) | Home team pitching staff strikeout rate, season-to-date. Decimal. |
| `away_pit_barrel_pct_30d` | PRE | 🟡 noise → dropped (-0.0003) | Away team pitching staff barrel rate allowed over the trailing 30 days. Decimal. |
| `away_pit_woba_against_std` | PRE | 🟡 noise → dropped (-0.0004) | Away team pitching staff wOBA allowed, season-to-date. Decimal. |
| `away_pit_xwoba_against_14d` | PRE | 🟡 noise → dropped (-0.0007) | Away team pitching staff xwOBA allowed over the trailing 14 days. Decimal. |
| `away_pit_xwoba_against_7d` | PRE | 🟡 noise → dropped (-0.0007) | Away team pitching staff xwOBA allowed over the trailing 7 days. Decimal. |
| `home_pit_woba_against_30d` | PRE | 🟡 noise → dropped (-0.0009) | Home team pitching staff wOBA allowed over the trailing 30 days. Decimal. |
| `home_pit_xwoba_against_14d` | PRE | 🟡 noise → dropped (-0.0010) | Home team pitching staff xwOBA allowed over the trailing 14 days. Decimal. |
| `home_pit_xwoba_against_30d` | PRE | 🟡 noise → dropped (-0.0010) | Home team pitching staff xwOBA allowed over the trailing 30 days. Decimal. |

**team platoon offense**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `away_vs_lhp_bb_pct_30d` | POST+PRE | ✅ signal (+0.0044) | Away lineup walk rate vs left-handed pitchers over the trailing 30 days. Decimal. |
| `home_vs_lhp_slugging_30d` | PRE | 🟡 noise → dropped (+0.0002) | Home lineup slugging percentage vs left-handed pitchers over the trailing 30 days. Decimal. |
| `home_vs_lhp_woba_std` | PRE | 🟡 noise → dropped (+0.0002) | Home lineup wOBA vs left-handed pitchers, season-to-date. Decimal. |
| `away_vs_lhp_woba_30d` | PRE | 🟡 noise → dropped (-0.0001) | Away lineup wOBA vs left-handed pitchers over the trailing 30 days. Decimal. |
| `away_vs_lhp_k_pct_30d` | PRE | 🟡 noise → dropped (-0.0001) | Away lineup's 30-day rolling strikeout rate (K/PA) vs left-handed pitchers ending strictly before game_date. Null when no away batters have plate appearances vs LHP in the rolling window. |
| `away_vs_lhp_xwoba_30d` | PRE | 🟡 noise → dropped (-0.0006) | Away lineup xwOBA vs left-handed pitchers over the trailing 30 days. Decimal. |
| `away_vs_lhp_xwoba_std` | PRE | 🟡 noise → dropped (-0.0006) | Away lineup xwOBA vs left-handed pitchers, season-to-date. Decimal. |
| `home_vs_rhp_slugging_30d` | PRE | 🟡 noise → dropped (-0.0006) | Home lineup slugging percentage vs right-handed pitchers over the trailing 30 days. Decimal. |

**team rolling/situational offense**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `home_off_bb_pct_30d` | PRE | 🟡 noise → dropped (+0.0022) | Home team offense walk rate over the trailing 30 days. Decimal. |
| `home_off_bb_pct_std` | PRE | 🟡 noise → dropped (+0.0022) | Home team offense walk rate, season-to-date. Decimal. |
| `away_off_hard_hit_pct_7d` | PRE | 🟡 noise → dropped (+0.0005) | Away team offense hard-hit rate over the trailing 7 days. Decimal. |
| `home_off_xwoba_14d` | PRE | 🟡 noise → dropped (+0.0003) | Home team offense xwOBA over the trailing 14 days. Decimal. |
| `home_off_xwoba_7d` | PRE | 🟡 noise → dropped (+0.0003) | Home team offense xwOBA over the trailing 7 days. Decimal. |
| `home_off_barrel_pct_30d` | PRE | 🟡 noise → dropped (+0.0001) | Home team offense barrel rate over the trailing 30 days. Decimal. |
| `home_off_xwoba_30d` | PRE | 🟡 noise → dropped (+0.0001) | Home team offense xwOBA over the trailing 30 days. Decimal. |
| `away_off_barrel_pct_30d` | PRE | 🟡 noise → dropped (+0.0001) | Away team offense barrel rate over the trailing 30 days. Decimal. |
| `home_off_hard_hit_pct_std` | PRE | 🟡 noise → dropped (-0.0001) | Home team offense hard-hit rate, season-to-date. Decimal. |
| `away_off_bb_pct_std` | PRE | 🟡 noise → dropped (-0.0001) | Away team offense walk rate, season-to-date. Decimal. |
| `home_woba_with_risp_30d` | PRE | 🟡 noise → dropped (-0.0001) | Home team offense wOBA with runners in scoring position over the trailing 30 days. Decimal. |
| `away_off_k_pct_std` | PRE | 🟡 noise → dropped (-0.0002) | Away team offense strikeout rate, season-to-date. Decimal. |
| `home_off_runs_per_game_30d` | PRE | 🟡 noise → dropped (-0.0002) | Home team runs scored per game over the trailing 30 days. |
| `home_off_runs_per_game_std` | PRE | 🟡 noise → dropped (-0.0002) | Home team runs scored per game, season-to-date. |
| `away_off_runs_per_game_std` | PRE | 🟡 noise → dropped (-0.0002) | Away team runs scored per game, season-to-date. |
| `home_off_runs_per_game_14d` | PRE | 🟡 noise → dropped (-0.0004) | Home team runs scored per game over the trailing 14 days. |
| `home_off_runs_per_game_7d` | PRE | 🟡 noise → dropped (-0.0004) | Home team runs scored per game over the trailing 7 days. |
| `home_off_bb_pct_7d` | PRE | 🟡 noise → dropped (-0.0008) | Home team offense walk rate over the trailing 7 days. Decimal. |

**team strength**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `elo_diff` | POST+PRE | ✅ signal (+0.0439) | Home team Elo rating minus away team Elo rating; positive values favor the home team. |
| `pythagorean_win_exp_diff` | POST+PRE | ✅ signal (+0.0439) | Home team Pythagorean expected win% minus away team Pythagorean expected win%; positive favors the home team. |
| `home_pythagorean_residual_season` | PRE | 🟡 noise → dropped (-0.0007) | Home team actual win% minus Pythagorean expected win% for the season to date; positive = outperforming run differential (luck/clutch indicator). |
| `away_elo` | PRE | 🟡 noise → dropped (-0.0010) | Away team Elo rating entering this game (~1500 = league average; higher is stronger). |
| `home_elo` | PRE | 🟡 noise → dropped (-0.0062) | Home team Elo rating entering this game (~1500 = league average; higher is stronger). |
| `home_pythagorean_win_exp` | PRE | 🟡 noise → dropped (-0.0062) | Home team Pythagorean expected win percentage based on season runs scored and allowed to date. |

**umpire (dropped block)**

| column | served | E1.8 MDA verdict (Δmae) | definition |
|---|---|---|---|
| `ump_accuracy_zscore` | — | 🟡 noise → dropped (-0.0005) | Accuracy Above Expected z-score — how accurately this umpire calls the zone. |
| `ump_run_impact_zscore` | — | 🟡 noise → dropped (-0.0005) | Total Run Impact z-score — direct measure of umpire zone effect on run expectancy. |

## (4) Training data

- **Source:** `baseball_data.betting_features.feature_pregame_game_features` JOIN `mart_game_results` (label = `home_final_score − away_final_score`), via `load_clean_matrix()` (`model_bakeoff.py:316-338`) = cached `load_features(min_year=2021)` with **both de-leak swaps applied in memory** (`_swap_bullpen_v3`, `_swap_stuff_plus_deleaked`). Filters: `has_full_data = TRUE`, both teams ≥ 15 games played, `game_year >= 2021`.
- **Registry stamps:** `training_cutoff: 2021+`, `training_rows: 10,256` (home_win's is 10,272 — the small difference is per-target row eligibility, not a different window). Fit with `--refresh-cache` so the E13.7 cold-start convention (league-baseline fills for rookie/call-up NULLs) is in the training frame — **the served model was trained under the same cold-start convention it serves under.**
- **CV scheme (selection/gates, not the final fit):** `PurgedWalkForwardSplit` — season walk-forward, `min_train_seasons = 3`, `embargo_days = 3`, feature-aware purge band from `max_feature_window(feature_cols)` anchored to the last *training* game-date. Measured purge cost on run-diff (E1.5): 6.2 % of rows dropped on the 2024 fold, 4.5 % on 2025, 3.7 % on 2026. The champion is re-fit on ALL rows; CV is the selection instrument.
- **E1.5 purged-CV re-baseline — run-diff was NOT flagged for leakage-by-CV-regime:** standard 3.0682 → purged 3.0758 (**+0.0076**, under the 0.02 MAE noise floor ⇒ not flagged); `purged+wt` (AFML sample-uniqueness weights) 3.0916. ⚠️ these are **pre-de-leak** numbers — see the §10 reading rule.
- **Standing caveat (inherited, documented in the loader):** the training read is **not point-in-time** (Story 30.3) — offline skill is a dense-re-read *ceiling*, not the achievable live number. E12 established there is no *structural* train/serve misalignment; the gap is value-completeness at serve time.
- **Producer (B)'s training data is entirely different** — per-side runs scored from the E2.1/E2.5 `totals_perside_v1` marginals, with the dispersion `r` calibrated on **held-out** residuals under a leakage-safe expanding window (season T sees only seasons < T). **PROD-STATE-1a (MLB Totals) owns that lineage**; this doc records only its run-diff-specific outcomes.

## (5) Validation — the §0.5 gate it passed

Selection, calibration, and live-served verdicts, deliberately separated from any edge claim.

**Selection + deflation (producer A):**
- Bake-off on **CRPS** (the honest metric for a predictive distribution), 3 purged folds, seed 42. **PBO 0.000 on both tiers** ✅ (< 0.2).
- Optuna HPO **passed both deflation gates on both tiers** — post PBO 0.086 / DSR 0.9983; pre PBO 0.099 / DSR 0.99999 — but the gains were sub-noise, so **defaults shipped** (§2).
- Promotion gates: **HOLD / HOLD**; deployed on the E13.11 integrity re-decision, with the gate confirming accuracy non-regression on every completed season (§2 table).
- Floors: the bake-off's `floor_no_skill` (CRPS 2.5080 / MAE 3.5610) is beaten by **+0.124 CRPS / +0.201 MAE**. There is **no `floor_market`** in the run-diff bake-off — because there is no run-diff market (§1).

**Predictive-distribution calibration (producer A) — the operative product gate:**
- **Story 9.8 served-calibration audit (2026-06-16, v5 era):** run_diff champion 2026 `cov80` **0.776** (gap −0.024, inside tolerance), `cov90` 0.877, **PIT-KS 0.019**, bias −0.008 → **calibrated ✓**; pre_lineup tier PIT-KS 0.030, bias −0.114 → **calibrated ✓**. The one ⚠ flag is a 2024 fold (cov80 ~0.715, intervals ~8 pts too tight in a high-variance run-environment season) — historical, not current serving.
- **Epic-16 production-Bayesian three-layer eval:** prior-predictive Normal(μ=0.042, σ=4.482) → NLL 2.9334; model NLL (discretized PMF) **2.7612** ✅ beats prior; `calib_80` **0.776** ✅ inside the [0.75, 0.85] gate. Both the champion and the sequential challenger cleared both layers; the challenger won head-to-head on NLL.
- **⭐ LIVE-MEASURED, v6 ERA — the honest served numbers** (this session: served `pred_run_diff_loc/scale` joined to realized `mart_game_results` scores, latest row per game, `game_date ≥ 2026-06-23` = the v6 promotion date):

  | tier | n | MAE | RMSE | `calib_80` | bias | mean σ | corr(μ, realized) |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | post_lineup | 504 | **3.5315** | 4.7386 | **0.7937** | −0.077 | 4.280 | 0.139 |
  | morning | 521 | **3.5730** | 4.7588 | **0.7946** | −0.006 | 4.272 | 0.140 |

  **Both tiers sit inside the [0.75, 0.85] `calib_80` gate and are essentially level-unbiased.** No-skill reference on the same games: predicting the constant mean gives MAE 3.6369 ⇒ the model buys **0.105 MAE** over no-skill on the post tier. This is a **thin-signal target** (corr 0.14) whose served predictive distribution is nonetheless **honestly calibrated** — the same shape as H2H.

**⭐ The run-diff marginal is the ONE E2.3 distribution that FAILS its gate (producer B):**

| distribution | `calib_80` | PIT mean | max decile dev | PIT flat? |
|---|---|---|---|---|
| total | 0.838 | 0.4957 | 0.0068 | ✅ |
| **run_diff** | **0.839** | **0.5035** | **0.0303** | **❌** |
| home_total | 0.863 | 0.4995 | 0.0091 | ✅ |
| away_total | 0.847 | 0.4945 | 0.0138 | ✅ |

E2.3's **overall gate reads NOT MET, and the run-diff marginal is the sole reason.** Note *which* criterion fails: coverage is fine (0.839) — it is **PIT flatness** (max decile deviation 0.0303 vs the 0.025 band). This is exactly the E2.1-r discipline in action: for a discrete/count-derived predictive, gate on **randomized-PIT flatness** and treat coverage as a **floor**, never a target. A coverage-only reading would have passed this distribution.

**Deflation status, stated honestly:** PBO gated the *selection* (0.000 both tiers) and DSR gated the *HPO* (0.998/0.99999). **No DSR/BH-FDR claim attaches to the champion as a forecaster** — the deployment was an integrity re-decision explicitly not predicated on clearing an edge gate, and there is no market to clear one against. The only §0.5-style *challenge* since is E7.9, whose MH2 null-state is **`UNDEFINED`** (PBO uncomputable at 3 folds) — §10-C.

## (6) Serving path

```
model_registry.yaml (run_differential: v6 ngboost_normal_deleaked pkls, post + pre)
  → scripts/predict_today.py            (daily_ingestion_job s19 "morning"; lineup_monitor sensor → lineup_predict "post_lineup")
      ngb_diff.pred_dist(X_diff).params → loc, scale
        ├─ p_home_win_ngboost = p_over_line(Normal, {loc,scale}, total_line=0)  ── 50 % ─┐
        │                                                                                ├─ consensus → TemperatureCalibrator → calibrated_win_prob
        │                          home_win v6 GLM P(home) ─────────────────── 50 % ─────┘        (→ mlb_h2h.md)
        ├─ compute_win_prob_beta(cal_win, [ngb_win, clf_win]) → win_prob_ci_low/high/width   (Story 19.7 — RENDERS in the app)
        ├─ layer4_h2h_conviction_flag/_disagree = |cal_win − Φ(μ/σ)| ≤ 0.02                 (28.6b monitor)
        ├─ evaluate_sigma_gate({… p_home_win_ngboost …})                                    (Story 22.4)
        └─ INSERT daily_model_predictions.pred_run_diff_loc / _scale                        (⛔ no run-diff version column)
  ⛔ write_serving_store / app/backend / frontend NEVER read pred_run_diff_* — the number is not user-facing

(B) E2.5 per-side μ (feature_pregame_sub_model_signals.totals_perside_mu_v1)
  → write_serving_store.py  _PERSIDE_MU_BATCH  +  totals_distribution_v1.json (r_home 4.0645 / r_away 3.3977)
  → totals_serving.build_totals_distribution_payload → {"run_diff": {mu, quantiles, pmf, p_home}}
  → DynamoDB picks/game/<pk> (+ S3 api-cache mirror) → app/backend/models/picks.RunDiffDistribution
  → frontend/components/totals-distribution.tsx  (margin density + P(home))     ⚠️ CURRENTLY NULL — see below
```

- **Two tiers** (identical mechanics to H2H): `morning` = the 126-feature pre_lineup model, no notifications, actionable edge deferred; `post_lineup` = the 15-feature model, re-scored per game once both sides post a complete 9-slot order (the INC-32 readiness gate). ⚠️ per §3, **run-diff itself barely uses the lineup** — the tier difference is a model swap and a feature refresh, not lineup information.
- **Gates on the path (all inherited from the shared predict/serve chain, none run-diff-specific):** Story 30.13 serve-time freshness gate · `signal_freshness_check` (HALT) · `check_served_prediction_integrity_op` + `check_intraday_fallback_op` (ALERT, page via `send_alert` since E11.30) · `check_prediction_coverage` (HALT, ≥ 90 % slate).
- **Deploy mechanics (standing landmine, unchanged):** the model registry ships with the box image on merge to `main` (`orchestration_cd.yml` `COPY . .`) — **merging a promotion PR IS the deploy; there is no promotion gate** (operator decision open since 2026-08-02). Harmless today only because α = 0.

**🔴 LIVE FINDING — producer (B) is wired end-to-end and serving nothing.** Reading the actual served artifacts (umbrella lesson 1), `totals_distribution` is **`null` in every game-detail blob sampled**: 2026-08-04 (4 games), 2026-08-03, 2026-08-02 (3 games, both the date-scoped *and* the `permanent` key), 2026-07-28. The frontend renders the margin panel only under `data?.totals_distribution &&`, so **the run-diff density and its `p_home` are simply absent from the product.** Two contributing conditions confirmed, and they do not fully explain it:
- **(i) An intermittent per-side μ collapse, correctly suppressed.** On 2026-08-03 the served `totals_perside_mu_v1` reads **~1.4–1.8 runs per side** (slate mean 1.561) against a champion total of ~8.9 — and `distribution_is_plausible` returns **False on all 8 games**, so the guard suppresses the block exactly as designed. The collapse is intermittent, not permanent: slate-mean μ by date — 08-03 **1.561**, 08-02 4.506, 08-01 4.512, 07-31 4.839, 07-30 5.102, 07-29 4.925, **07-28 1.792**, **07-27 1.489**, **07-26 1.544**, 07-25 4.409.
- **(ii) But the block is ALSO null on slates where μ is healthy** (08-02, mean 4.506, 14/15 games covered) ⇒ plausibility suppression is **not** the whole cause. The remaining candidates are the WARN-tier degrades in `write_serving_store` — the `_PERSIDE_MU_BATCH` read failing under `--s3`, or `_load_totals_dist_params` failing to resolve the committed json on the box image — both of which `log.warning` and continue by design, so naming the branch requires the **box step log**.
- ⇒ **flagged OPERATOR-VERIFIABLE, and owned by PROD-STATE-1a (MLB Totals)** — the per-side μ block and the `totals_distribution` payload are that model's surface; run-diff is a passenger on it. Recorded here because it is the reason run-diff's second producer has zero user-facing output, and because the E2.3 record ("derives … run-diff … the totals pick detail renders") reads as live when it is not — the repo's documented-≠-served class.

## (7) Version + last retrain + retrain cadence

- **Served version:** **`v6`** both tiers (`model_version: v6`, `pre_lineup_model_version: v6`), `model_name: ngboost_normal_deleaked`. **Reconciled as far as the data allows** — S3 artifacts present and dated to the promotion; served columns populated and consensus-identity-verified — but **⛔ NOT reconcilable against a served version stamp, because run-diff has none** (see the headline block). The `v6` / `pre_lineup_v6` visible on a run-diff row is home_win's stamp.
- **Last champion (re)train: 2026-06-23** — `finalize_v6_champion.py --target run_diff --tier {post_lineup,pre_lineup} --refresh-cache`, the E13.11 fit-and-persist (v6 had never been persisted at E1.9; the registry carries the explicit `⚠️ OPERATOR PREREQ` to run it before deploy). Corroborated by the S3 object timestamps (20:07:46 / 20:11:17 UTC). That is the **only** run-diff champion retrain since the 30.4 v5 re-promotion (2026-06-12).
- **Retrain cadence: there is NO scheduled champion retrain** — identical to H2H, and the same open story **E1.10** (Backlog) covers both. The one *challenge* since promotion was **E7.9** (operator-run 2026-07-28), which returned `INCUMBENT_STANDS` on both run-diff tiers ⇒ no champion change, no prediction backfill.
- **Rollbacks retained:** v5 `ngboost_tuned_market_blind_2026.pkl` (169-feature contract) post-tier; `ngboost_pre_lineup_2026.pkl` (`pre_lineup_v1`) morning tier. Both verified present on S3.
- **⚠️ A run-diff promotion resets the 28.6b conviction window.** Stated in the registry across every generation — *"run_diff is not bet directly; it feeds the h2h consensus, so its promotion also resets the conviction (28.6b) window"* — and the registry's `attribution_start: '2026-06-23'` records that E13.11 reset it for both models at once. **The MH2.1 single-target-promotion landmine applies with extra force here**: a run-diff-only swap would move the served H2H probability *and* the CI bands *and* invalidate the conviction window while leaving `model_version` (and therefore Admin → Model Freshness, the CLV mart's hard-coded `v6`, and the backfill idempotency key) completely unchanged. **There is currently no mechanism that would make such a swap visible in the served data.**
- **Producer (B) version:** `totals_distribution_v1`, fit params committed at `betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json` (`r_home 4.0645`, `r_away 3.3977`, `rho 0.0`, `n_draws 10000`, P05…P95 grid). **Registry-absent** (the K-props shape). No scheduled refit; unchanged since E2.3.

## (8) Honest-framing status — `best_alpha = 0`, verified on served rows

**Confirmed: no edge, win-rate, or beat-the-market claim rides on this model — and structurally it is the model least able to carry one, because it has no market.**

- **Live-read proof:** on every 2026-08-04 post_lineup row, `alpha = 0.0` and `h2h_edge` ∈ {0.0, ±1.1e−16} — machine-epsilon zero, a **presence flag** (read `IS NOT NULL`, never the value, per CLAUDE.md). Run-diff has no `edge`/Kelly column of its own at all.
- **No market to beat.** `mart_odds_outcomes` carries no `spreads` rows in any season (live-verified). The run line has never been ingested, priced, backtested, or gated. Any future statement of the form "our run-diff model beats the run line" would require net-new odds ingestion before it could even be *measured*.
- **Its one live pathway to a bet is neutralised by α = 0.** The consensus it half-owns feeds `calibrated_win_prob`, but α enters *after* calibration on the market blend only — `posterior = sigmoid(α·logit(model) + (1−α)·logit(market))` — so α = 0 ⇒ posterior ≡ market ⇒ edge ≈ 0 ⇒ Kelly ≈ 0.
- **The E2.3 payload carries its own honesty statement in code:** *"All quantities are DESCRIPTIVE (a calibrated distribution) — no EV / value / win-rate is produced (best_alpha=0)"* (`totals_serving.py`).
- **16B.7's Layer-4 ROI table must not be mis-cited.** `run_diff_derived` posts `roi_devig +0.2094` at n=471 in that memo — **this is not an edge result.** It is a pre-de-leak (2026-06-04) *diagnostic* whose own header states α = 0.00 makes the blended posterior identically the market, and whose verdict is **NO CHANGE — "does NOT beat the 2026 Bovada market on L3 Brier."** The whole memo sits in the leak-inflated regime (§10 reading rule).
- **What the product legitimately is:** an honestly-calibrated predictive distribution over the home margin (live `calib_80` 0.794 both tiers, bias ≈ 0, PIT-KS 0.019–0.030) that supplies half of a calibrated win probability and the width of the CI bands the app renders. A **calibration/transparency component**, not a bet signal.

## (9) Known limitations + open follow-ups (counted)

**How close to "finished" (= STABLE / TRUSTWORTHY / CALIBRATED, not edge):** the champion, its de-leak, its contract derivation, its serving wiring, and its honest framing are all closed. What is genuinely open divides into (a) **governance gaps that are specific to this model** — and they are the sharpest in the MLB family, because run-diff is the only target with no served version stamp and no market — and (b) items shared with H2H/Totals. **Open follow-ups: 8.**

**Run-diff-specific (5):**
1. **⭐ No per-target `run_diff_model_version` column.** MH2.1 added `totals_model_version` for exactly this reason and stopped there. Consequence: a run-diff champion swap is **invisible in the served data** while moving the served H2H probability, the CI bands, and the 28.6b window. This is the single highest-value cheap fix for this model, and it is a prerequisite for any future run-diff promotion being auditable. (Sibling of [`mlb_h2h.md`](mlb_h2h.md) §(9)#8.)
2. **⭐ Producer (B) serves nothing** — `totals_distribution` `null` in every blob sampled ⇒ the run-diff margin density and `p_home` never render. Cause partly identified (intermittent per-side μ collapse + a second, unidentified WARN-tier degrade); **operator-verifiable via the box step log; owned by PROD-STATE-1a.** §(6).
3. **⭐ The E2.3 run-diff marginal fails its PIT-flatness gate** (max decile dev 0.0303 vs 0.025) and is the *sole* reason E2.3's overall gate reads NOT MET. Un-remediated since E2.3. Coverage (0.839) is fine — the failure is shape, which is the criterion that matters for a discrete predictive (E2.1-r).
4. **⭐ The `MIN_SPREAD_RUNDIFF = 0.50` flat-output floor appears mis-calibrated for the v6 slim models.** Reconstructing the guard's own arithmetic over served rows (latest row per game, slates with n ≥ 12, since the 2026-06-23 promotion): the morning tier's `stddev(pred_run_diff_loc)` falls below 0.50 on **8 of 33 slates (24 %)** and post_lineup on **4 of 32 (13 %)** — minimum 0.157 / 0.445, median 0.682 / 0.640. The floor was set in the v5 era (a 374-feature dense model with a wider slate spread); the 13/124-feature v6 models are structurally narrower. Since `check_served_prediction_integrity_op` pages CRITICAL on `served_integrity_problem_count > 0` (E11.30), this is a candidate **chronic false-positive on a paging guard** — the "over-paging monitor gets muted" failure mode. ⚠️ this is a *reconstruction* from the served table, not a reading of the op's step log ⇒ **operator-verifiable before acting**; the fix, if confirmed, is to recalibrate the floor to the v6 output scale (the INC-17-P3 precedent, where `MIN_SPREAD_PROB` was moved 0.016→0.025 for the same reason), **not** to widen the model.
5. **The pre-lineup bake-off's header winner (`glm_elasticnet`) and what actually ships (`ngboost_normal`) differ** (§2). Benign and defensible, but undocumented in the record — a future session reading `bakeoff_run_diff_pre_lineup.md` will conclude the wrong learner is deployed.

**Shared with the MLB family (3):**
6. **E1.10 — champion retraining cadence (Backlog, open).** No scheduled refit for run-diff either; drift accrues until an operator-triggered §0.5 bake-off. E7.9 (2026-07-28) is the only challenge since promotion.
7. **No promotion gate** (operator decision open 2026-08-02) — merging a registry PR is the deploy. Compounded for run-diff by #1: a swap would be both un-gated *and* un-stamped.
8. **Registry hygiene (3 cosmetic items)** — the leak-era `cv_mae: 3.066`, the Epic-16 `mlflow_run_id`, and the v5 `deployed_date` all sit on the v6 entry (headline block).

**Known limitations (inherent, documented, not follow-ups):**
- **Thin-signal target.** Live corr(μ, realized) ≈ 0.14; the model buys ~0.105 MAE over a constant-mean no-skill baseline (3.5315 vs 3.6369). Baseball run margin is close to irreducibly noisy; σ ≈ 4.28 runs against a mean |margin| of ~3.5.
- **Almost no lineup content.** The post_lineup champion's only Class-B column is a bullpen-EB *coverage* metric (§3). Do not expect a post-lineup re-score to meaningfully re-rate the margin.
- **No calibration layer of its own.** The temperature calibrator sits on the H2H consensus; the run-diff predictive is raw NGBoost.
- **The 28.6b conviction gate is structurally non-independent, on TWO counts.** (a) It compares `calibrated_win_prob` against `Φ(μ/σ)`, but the former *contains* the latter at weight 0.5 (recorded identically in [`mlb_h2h.md`](mlb_h2h.md) §(9)#3). (b) **The two "independent" estimators also share 8 of run-diff's 15 served features with home_win's 21** — `elo_diff`, `pythagorean_win_exp_diff`, `home_bp_eb_xwoba`, `home_team_sequential_bullpen_xwoba`, `home_bp_eb_coverage_pct`, `away_bp_eb_coverage_pct` and both imputation indicators. Any future reading of a conviction/disagreement statistic must account for both.
- **Offline skill numbers from the leak era are not comparable to today's** — see the §10 reading rule.
- **The two producers are never reconciled.** (A)'s `Φ(μ/σ)` and (B)'s `p_home` estimate the same probability by different means, and no code, test, or monitor ever compares them. A cheap, high-information consistency check that does not exist.

## (10) ⭐ Tried & result ledger

_Everything tested against `run_differential` with its recorded outcome — so a future audit never re-runs a dead learner class or re-leaks a fixed leak. Null states per `cv_power.classify_null` where recorded. Entries are marked **OWN** (run-diff was the tested target) or **INHERITED** (established on Totals/H2H and carried here by the shared matrix, the shared joint distribution, or the consensus)._

**Reading rules for this ledger (apply before citing any number):**
- **⭐ The de-leak (E1.7/E1.8, 2026-06-18) is the dividing line, and it is LARGER on run-diff than on H2H.** The clustered-MDA pooled baseline moved **MAE 3.0620 (leaky) → 3.3880 (bullpen_v3) → 3.3961 (+ Stuff+ de-leaked)** — i.e. **~0.33 MAE of the pre-de-leak accuracy was leak.** Any run-diff MAE in the **3.06–3.10** band (the registry's own `cv_mae: 3.066`, E1.5's 3.0682/3.0758, the 7.M-era 3.1041) is **leak-inflated — do not cite as current skill.** Honest post-de-leak: **CV MAE ≈ 3.36–3.40 / CRPS 2.3841**; live-served **MAE 3.53**.
- **Any H2H Brier in the 0.18–0.21 band is likewise pre-de-leak** (16B.7, 30.9, the production-Bayesian memos). Post-de-leak honest H2H Brier is 0.241–0.249.
- **The de-leak inverted this model's importance ranking.** Pre-de-leak MDA #1/#2 were `home_bp_eb_xwoba` (+0.21385) and `away_bp_eb_xwoba` (+0.16712); post-de-leak they collapse (the pair drops to rank 17 at +0.00117) and the **coverage** metrics take #1/#2 (+0.10935/+0.07734) — the same signature as H2H, where a data-depth indicator replaced the leaked value. Treat any pre-2026-06-18 statement that "bullpen quality drives run differential" as an artifact.
- **`best_alpha = 0` dominates, and run-diff has no market at all** ⇒ every run-diff improvement has zero live bet payoff by two independent mechanisms. Improvements are judged as calibration/consensus/transparency work.
- **⭐ The ADD space is largely UNTRIED, not exhausted** (§3). Absence of a run-diff entry below usually means *never tested*, not *tested and dead* — the opposite of the H2H ledger's default reading.

### A. Learner / architecture classes — **OWN**

| candidate | when | result | source |
|---|---|---|---|
| **E1.9 bake-off, post_lineup/13f:** ngboost_normal · catboost · stack_mean · glm_elasticnet · xgboost · lightgbm (+ `floor_no_skill`) | 2026-06 | **`ngboost_normal` WON** (CRPS 2.3841; 2-way tie inside the 0.02 floor, broken on PIT-KS; beats no-skill +0.124 CRPS / +0.201 MAE; **PBO 0.000**). Trees, the GLM and the mean-stack are all dead ends on this contract | `ablation_results/bakeoff_run_diff_post_lineup.md` |
| **E1.9 bake-off, pre_lineup/124f** | 2026-06 | `ngboost_normal` CRPS 2.4478 #1, `glm_elasticnet` 2.4496 #2 (0.0018 apart); memo header declares glm on the calibration tiebreak but **`ngboost_normal` is what ships**. PBO 0.000. `lightgbm` is a distant last (2.7270) on both tiers | `…/bakeoff_run_diff_pre_lineup.md`; registry `pre_lineup` |
| **Optuna HPO on the v6 contracts** | 2026-06 | **PASSED both gates both tiers** (PBO 0.086/0.099, DSR 0.9983/0.99999) — unlike home_win — but **gains sub-noise** (post 2.3796 tuned vs 2.3841 default, ~22 % of the floor) ⇒ bake-off defaults shipped | `tuning_results_v6_ngboost_normal_run_diff_{post,pre}_lineup.json` |
| **LogNormal distribution head** | pre-2026 (standing) | **PERMANENTLY EXCLUDED — run-diff can be negative.** Stated in every registry generation; Normal is the only admissible NGBoost head | `model_registry.yaml` |
| **Epic-16 sequential-enriched retrain (377 feats) vs the 369-feat non-sequential champion** | 2026-06-04 | **PROMOTE** — challenger beats champion on every applicable layer: L1 NLL 2.7612 < 2.7757 < prior 2.9334; L2 `calib_80` 0.776 vs 0.768, both inside [0.75, 0.85]. *"The clean win of the sequential retrain."* No L3/L4 (no direct market) | `ablation_results/production_bayesian_run_differential.md` |
| **16B.7 run-diff-derived H2H** (Φ(μ/σ) alone vs the direct classifier) | 2026-06-04 | Loses NLL (0.6023 vs 0.5957) and raw Brier (0.2089 vs 0.2044); **wins ECE (0.0250 vs 0.0430)**. Verdict **NO CHANGE** — informative (beats the Bernoulli prior) but does not beat the market (0.1820). **This is why the serve BLENDS both legs rather than picking one.** ⚠️ pre-de-leak throughout | `ablation_results/run_diff_derived_h2h_16b7.md` |
| **30.9 learned ensemble stack vs the 50/50 blend** | Epic 30 | **PROMOTE on paper (Δ −0.0037) but SHELVED** — α=0 gives the blend weight no live payoff. Status-quo table (pre-de-leak): 50/50 pooled Brier 0.1964, clf-only 0.1939, **run-diff-only 0.2044** ⇒ the winning variant picked the classifier outright (`convex_w_on_clf = 1.0`) | `ablation_results/h2h_stack_eval_30_9.md` |
| **⭐ Consensus-weight question, RE-OPENED by a live v6-era measurement (this session — an OBSERVATION, not a result)** | 2026-08-04 | On served post_lineup rows since the v6 promotion (n = 504), the **run-diff leg alone** posts Brier **0.2424** vs the served consensus **0.2454** and the market **0.2449**; corr 0.185 vs 0.167; spread sd 0.0615 vs 0.0351. Paired bootstrap: **rd-leg − consensus ΔBrier −0.0030, 95 % CI [−0.0055, −0.0004] (significant on this window)**; **rd-leg − market −0.0025, CI [−0.0074, +0.0023] (NOT significant)**. ⚠️ **This is one un-deflated 6-week forward window, not a §0.5 result** — no PBO/DSR, no pre-registration, and the calibrator was fit on the *consensus* not the leg, which alone could explain the gap. It **reverses 30.9's ordering**, which was measured pre-de-leak on the v5 pair. ⇒ record as an **open, re-testable question with a natural accrual trigger**, not a finding; α = 0 makes it payoff-free either way | this doc; `daily_model_predictions` × `mart_game_results` |
| **28.5 Hierarchical Bayesian Bradley-Terry** | Epic 28 | **INHERITED (H2H-only)** — a real, well-fit, worse H2H model; never run against run-diff | `ablation_results/h2h_bradley_terry_28_5.md` |

### B. Leakage classes swept (fixed — do not re-leak) — **OWN unless noted**

| leak | found/fixed | mechanism + run-diff-specific outcome | source |
|---|---|---|---|
| **Within-game bullpen leak (`bp_eb_xwoba`)** — E1.7 | 2026-06-17/18 | TWO leaks in one feature: reliever EB weighted by `outs_in_game` (within-row peek, invisible to purged CV) + a roster-spine leak (rows only for completed games ⇒ serving-null). **On run-diff this was the single largest correctness event in the model's history** — pooled MDA baseline MAE 3.0620 → 3.3880 and the #1/#2 features collapsed to rank ~17. Fix: equal-weight trailing-30d strict-`<` pre-game pool | `E1_7_HANDOFF.md`; `clustered_feature_importance_run_diff{,_bullpen_v3}.md` |
| **FanGraphs Stuff+/arsenal season-to-date join** — E1.8 🟥 | 2026-06-18 (`eb00a5d`) | `season = year(game_date)` with no `< game_date` guard. Hit 2 *totals* contract slots; **NOISE on run_diff** (Stuff+ is noise-ranked here and absent from the post contract). Fixed via prior-season repoint; run-diff's de-leaked MDA re-run moved the pooled baseline only 3.3880 → 3.3961 | `feature_leakage_audit.md:51,151` |
| **Market columns (9) + `total_line_std` name collision** — 30.4 | 2026-06-12 | Removed from the run-diff contract (376 → 169) alongside the identifiers. **Promoted via CORRECTNESS OVERRIDE**: the gate HELD on accuracy (pooled ΔMAE +0.0001, flat/sub-noise; 2024 −0.0086 win, 2025 +0.0087 within tolerance) but market leakage is a hard compliance violation. `_MARKET_STEMS` now enforced at fit time | `model_registry.yaml`; `promotion_gate_run_diff.json` |
| **Identifiers (`home_starter_pitcher_id`, `venue_id`, `game_year`)** — 30.1 | 2026-06-11 | Dropped. Ablation = **PROMOTE**: CV flat (MAE 3.0820→3.0840, inside noise) while honest-2026 improved on **every** axis (MAE 3.1210→3.1195, RMSE 4.131→4.128, MedAE 2.491→2.478) **and `calib_80` moved to nominal (0.774→0.800)** — a calibration win, not just an accuracy one. `is_identifier_name` guard permanent | `model_registry.yaml` (30.1 provenance) |
| **E1.8 stale-ranking bug (process leak)** | 2026-06-19 | Contracts had been hand-derived off importance JSONs that each still contained one leak. `derive_clustered_contract.py` now REFUSES a leaky ranking (`bullpen_version=v3` + `stuff_plus_version=deleaked` required); hand-pruning banned. The run-diff 13-feature contract is a product of this fix | `build_roadmap.md`; contract `_provenance` |
| **E1.5 purged-CV re-baseline** | 2026-06 | run-diff **NOT flagged** — leakage-by-CV-regime (purged − standard) = **+0.0076**, under the 0.02 MAE floor. (Totals was +0.0179, also unflagged; home_win −0.0005.) ⚠️ measured pre-de-leak on the 374-feature champion | `ablation_results/purged_cv_recalibration.md` |

### C. Feature-family ADDITIONS tried against run-diff — **exactly one study**

| family | when | result | null state | source |
|---|---|---|---|---|
| **E7.9 — MiLB-MLE EB blocks (`plus_eb`) + the `eb_gb_pct` join, BOTH tiers, 24 arms each** | 2026-07-28 (operator, laptop, S3-native matrix 11,858 × 792) | **`INCUMBENT_STANDS` on both tiers.** pre_lineup: leader `plus_eb::glm_elasticnet`, margin **+0.0053** vs the 0.02 floor ❌, PBO 0.000, **DSR 0.218**. post_lineup: margin **+0.0127** ❌, PBO 0.000, **DSR 0.724**. E2.1-r oracle-floor sanity passed (no candidate beat a target-seeing oracle ⇒ the metric is not inverted). ⚠️ **the margin CONFLATES contract and learner** — 77 % (pre) / 53 % (post) of it is the `ngboost_normal → glm_elasticnet` swap, which E7.9 was not chartered to change | **`UNDEFINED`** — PBO uncomputable at < 4 folds (`mh2_null_inventory.csv`) | `edge_program/ablation_results/e7_9_retrain_verdict_summary.md`; `e7_9_retrain_run_diff_{post,pre}_lineup.md` |
| **`eb_gb_pct` (the E7.9 join) in isolation, holding the learner fixed** | 2026-07-28 | **CLEAN NULL with a target-dependent SIGN**: weakly POSITIVE for total_runs (6 of 7 learners, max +0.0073), **NEGATIVE for run_diff on all 6 learners**. Mechanistically sensible — ground-ball rate suppresses home runs, which moves a **total** more than a **differential** — but every magnitude ≤ ¼ of the noise floor. E7.3p's −23 % cold-start MAE lift on GB% is real at the pitcher-metric level and **does not propagate to game-level skill**. `eb_gb_pct` stays served + tested but enters **no** model contract (PM ruling Q6) | clean null, closed (PM Q5) | same |
| **`plus_eb` in isolation** | 2026-07-28 | Clearly positive for total_runs (+0.0373 xgboost / +0.0259 catboost / +0.0107 ngboost), **mixed for run_diff** — *"batter K%/BB%/ISO and starter K%/BB% are rate stats that predict RUNS SCORED, whereas run differential is largely absorbed by `elo_diff` / `pythagorean_win_exp_diff`, which the incumbent contract already carries."* **This is the mechanism to remember before proposing any rate-stat family for run-diff** | sub-threshold | same |
| **`calibration_not_degraded` sub-gate** | 2026-07-28 | Fired on run_diff/pre_lineup at **PIT-KS 0.0294 vs 0.0293** — a 1e-4 difference. Recorded as a gate-sensitivity artifact, not a calibration regression | — | same |
| ⛔ **Every other E1.11 / E13.x ADD family** (zone-profile, miss-distance, TTO-3, bullpen-fatigue×short-leash, zone-overlap, in-season wRC+, `f1_startform`/`f1_staleness`/traded-pitcher/traded-lineup, 28.4 travel/fatigue, 33.5/33.7 projected-vs-actual lineup) | 2026-06/07 | **NEVER TESTED AGAINST RUN-DIFF.** File-level proof: every lift artifact is `*_home_win_lift.json` or `*_perside_runs_lift.json`; **no `*_run_diff_lift.json` exists.** Their H2H/per-side nulls are in [`mlb_h2h.md`](mlb_h2h.md) §10-C and PROD-STATE-1a — ⚠️ **do NOT transfer those nulls to run-diff without re-running**; the `plus_eb` sign flip above shows the targets genuinely differ | n/a — untested | repo file inventory |

### D. Sub-model Layer-3 signals vs run-diff — **OWN, but the authoritative de-leaked re-eval SKIPPED this target**

⚠️ **The 2026-06-21 de-leaked Layer-3 re-evaluation covers `total_runs` and `home_win` ONLY** (`layer3_signal_evaluation_20260621_231932.md`) — **run_diff has no de-leaked Layer-3 verdict.** The only run-diff numbers are the pre-de-leak per-signal ablations:

| signal | when | run-diff result | note |
|---|---|---|---|
| `starter_v1` (suppression μ + signal) | Epic 4/9 | **CLEAR**, ΔMAE **−0.0067** mean (3/3 folds: −0.0034 / −0.0071 / −0.0096); the two signals rank Ridge \|coef\| **#1 and #2** | pre-de-leak; the strongest sub-model result on this target |
| `matchup_v1` (archetype) | Epic 8/9 | **+0.0007** mean, **0/3 folds improved**; Ridge \|coef\| ranks #240/#255 — inert | pre-de-leak; matches the H2H `reject` |
| `bullpen_v2` | Epic 9 → E13.3 | ⚠️ **INHERITED**: the leaky read gave bullpen the largest H2H stacking weight (0.507), and the de-leaked re-eval turned it into a **CONFIRMED REJECT** (+0.0001). Run-diff was never re-evaluated, but it consumed the same leaked bullpen block ⇒ **treat any pre-2026-06-21 bullpen-signal claim on run-diff as retracted-by-analogy, and re-run before trusting it** | `e13_3_submodel_meta_reeval.md` |
| Story 4.4 early ablation | 2026-05-28 | run_diff Δ = −0.0097 (Ridge, 3 folds, 564-feature baseline); April Δ −0.0078. Gate clear. *"Near-zero delta expected; true integration at Epic 9 Layer 3"* | pre-de-leak, pre-Layer-3 |
| **The Layer-3 stack is UNSERVED regardless** | — | `layer3_h2h` is an inert stub; `predict_today` uses the monolithic champions. `stacking_weights.json` still carries the retracted bullpen weights — a known stale artifact | INHERITED from [`mlb_h2h.md`](mlb_h2h.md) §10 |

### E. The joint-distribution lineage (producer B) — **INHERITED from Totals, with run-diff-specific outcomes**

_Run-diff is a derived marginal of the E2.x per-side stack, so this whole lineage is shared with PROD-STATE-1a. Only the run-diff-specific outcomes are recorded here._

| candidate | when | run-diff-specific result | source |
|---|---|---|---|
| **E2.2 Gaussian copula over the two per-side NegBin marginals** | 2026-07 | **NEGLIGIBLE dependence — residual ρ = −0.0035** ⇒ home/away runs are treated as INDEPENDENT (ρ = 0). *"Forcing one would be coupling the data does not support."* Because run-diff is a **difference**, it is the marginal most exposed to a dependence error — and the answer is that there is none to model | `e2_2_copula_decision.md`; `betting_ml/utils/copula.py` |
| **E2.3 per-side vs shared dispersion `r`** | 2026-07 | **PER-SIDE WON, and the run-diff marginal is the REASON** — *"the run-diff calibration is sensitive to the home/away dispersion asymmetry the sum is blind to."* Served `r_home = 4.0645` / `r_away = 3.3977`, calibrated on held-out residuals via a leakage-safe expanding window (E2.1's train-fit `r ≈ 8.527` was ~24 % under-dispersed). The held-out `r` is stable across seasons (CV 0.054) ⇒ a single global per-side `r`, not a period-conditioned one | `e2_3_convolution_calibration.md/.json` |
| **⭐ E2.3 calibration gate on the run-diff marginal** | 2026-07 | **FAILED — the only one of the four marginals that does.** `calib_80` 0.839 ✅ but PIT max decile deviation **0.0303 > 0.025** ⇒ `run_diff_pit_flat: false`, and E2.3's overall gate reads **NOT MET** solely because of it. **UN-REMEDIATED** | same |
| **E2.6 derivative pricing gates** (this joint distribution vs the market) | 2026-07 | **CLEAN NULL** — no derivative beats its own close after deflation (`team_totals` PBO 0.299 / DSR 0.911, 0/239 survive FDR; `alternate_totals` PBO 0.057 / DSR 0.592, 0/468). ⚠️ **the run line was NOT among the markets priced** — it has no closes in S3 | `e2_6_derivative_gates.md` |
| **E13.13 derivative efficiency** | 2026-07 | **CLEAN NULL** across `h2h_1st_5_innings`, `totals_1st_1/1st_5_innings`. **Again, no run line** | `e13_13_derivative_efficiency.md` |
| **E13.8 market-accuracy benchmark** | 2026-06-23 | **INHERITED (H2H):** no headroom exists — Pinnacle's close beats the no-skill floor by only 0.002–0.005 Brier, and not every season. *"Target calibration-parity with the close, do not chase Brier below the floor."* Directly relevant to any future run-line ambition | `e13_8_market_accuracy_benchmark.md` |

### F. Calibration / uncertainty arms touching run-diff

| candidate | when | result | source |
|---|---|---|---|
| **Story 9.8 served predictive-distribution audit** | 2026-06-16 | run-diff **calibrated ✓ on 2026 both tiers** (champion cov80 0.776 / PIT-KS 0.019 / bias −0.008; pre_lineup PIT-KS 0.030 / bias −0.114). The one ⚠ is a 2024 fold (cov80 ~0.715, intervals ~8 pts too tight) — a high-variance run-environment season, **historical not current**. **MEASURE-ONLY, no model change** | `ablation_results/served_calibration_9_8.md` |
| **Story 22.4 σ-aware selection/sizing** | 2026 | **GREEN-LIT** to consume the run-diff predictive σ on the strength of that audit (`sigma_gate.py` header cites *"run_diff champion: cov80 0.776, calibrated ✓"*). Live: `evaluate_sigma_gate` consumes `p_home_win_ngboost` | `ablation_results/sigma_gate_22_4.md`; `betting_ml/utils/sigma_gate.py` |
| **Story 9.7 `combined_sigma` / `run_diff_sigma`** | 2026-06-10 | `load_layer3_features._compute_run_diff_sigma` = `sqrt(Var(home_runs) + Var(away_runs))` — a **third** run-diff-uncertainty construction, built for the 28.4 conviction feature. ⚠️ lives in the **unserved** Layer-3 path; `predict_today` does not compute `combined_sigma` and instead uses the across-estimator dispersion (Story 19.7) | `betting_ml/scripts/load_layer3_features.py:1279`; `betting_ml/utils/win_prob_uncertainty.py` |
| **⛔ A dedicated run-diff calibrator** | — | **NEVER BUILT and never proposed.** The temperature calibrator operates on the H2H consensus only. The live `calib_80` (0.794 both tiers) suggests none is needed today | this doc §5 |

---

### Brief-vs-verified corrections (cross-session lesson 3 — recorded for the umbrella)

1. **"the served run_diff version (its own column)" is WRONG — there is NO run-diff version column.** `daily_model_predictions` carries `model_version` (home_win-only) and `totals_model_version` (MH2.1); run-diff was never given one. The version authority is `model_registry.yaml['run_differential']` + the S3 artifact path, and **it cannot be reconciled against served data** — the closest available proofs are the artifact timestamps and the exact reproduction of the consensus identity on live rows (headline block). This is a **gap**, not a mismatch: registry and code agree, and run-diff v6 was promoted in the same E13.11 change as home_win v6.
2. **"Run-diff is a DERIVED MARGINAL of the same joint distribution as Totals" is CORRECT but describes producer (B), which is NOT the H2H consensus leg and is NOT currently serving.** The consensus leg is a **direct NGBoost Normal regression** on the run-diff target — a separate model with its own contracts, artifacts and registry entry. Both exist; §1 separates them. The E2.3 marginal is `null` in every served blob sampled (§6).
3. **The brief's framing that fields 2/3 "largely REFERENCE 1b, not a standalone build" understates it.** run-diff has its **own** bake-off, its **own** Optuna study (which, unlike H2H's, PASSED its deflation gates), its **own** two contracts, its **own** promotion gates, and its **own** de-leak history — in which the leak was **larger** than H2H's. Fields 2/3 are filled from run-diff's own record; only the consensus/calibration/α wiring is inherited. (The two consensus legs *do* overlap substantially at the feature level — **8 of run-diff's 15 served post-lineup columns also appear in home_win's 21**: `elo_diff`, `pythagorean_win_exp_diff`, `home_bp_eb_xwoba`, `home_team_sequential_bullpen_xwoba`, `home_bp_eb_coverage_pct`, `away_bp_eb_coverage_pct`, `has_starter_platoon_data`, `is_new_venue` — which is a second, feature-level reason the 28.6b "two independent estimators" framing is strained, beyond the weight-0.5 containment noted in §9.)
4. **Field 9 is NOT shorter than H2H's — it is differently weighted.** Both count 8 open items, but 5 of run-diff's are run-diff-specific governance/serving gaps (no version column; producer B dark; the failed PIT gate; the mis-calibrated flat-output floor; the bake-off-header discrepancy) rather than modelling work. **Field 10 is shorter than H2H's for a real and important reason: the ADD space was never explored** (§3, §10-C) — that shortness is a *finding an audit must act on*, not an absence of history.
5. **16B.7's `roi_devig +0.2094` must not be read as an edge result** — it is a pre-de-leak α=0 diagnostic whose own verdict is NO CHANGE (§8).
