# Story 30.1 — Feature-Hygiene Audit & Retrain (identifier/temporal scrub)

**Status:** audit + flagger COMPLETE; ablation retrain HANDED OFF (long-running, see §3).
**Date:** 2026-06-11. **Epic 30, Track B (foundation-first).**

Per the Epic 30 operator directive, every decision below is judged FIRST on
**prediction accuracy to the true outcome** (totals/run_diff → MAE/RMSE/MedAE +
calib_80; H2H → Brier/NLL/accuracy/ECE + live corr vs the 0/1 winner). Beating
the market is reported as SECONDARY context only, never the promotion gate.

This is a **hygiene audit, not a presumed win.** Removing out-of-distribution /
memorization risk even at flat CV is a win; a CV regression beyond tolerance is a
KEEP.

---

## 1. Identifier/temporal features × target × importance rank  *(AC #1)*

### 1.1 What is in the contracts

Contract scan of all three v4 tuned contracts (`feature_cols`, 379 features each):

| Contract | identifier/temporal columns present |
|---|---|
| `home_win/feature_columns_xgb_classifier_tuned_2026.json` | `home_starter_pitcher_id`, `venue_id`, `game_year` |
| `run_differential/feature_columns_ngboost_tuned_2026.json` | `home_starter_pitcher_id`, `venue_id`, `game_year` |
| `total_runs/feature_columns_ngboost_tuned_2026.json` | `home_starter_pitcher_id`, `venue_id`, `game_year` |

`away_starter_pitcher_id` is **asymmetrically absent** from all three v4 contracts
(the feature-selection multicollinearity pass dropped it; it survives only in the
older elasticnet/SHAP eval sets). The `*_season`-suffixed columns
(`home_starter_csw_pct_season`, `away_team_oaa_prior_season`,
`home_pythagorean_residual_season`, …) are **season-aggregated statistics, not the
temporal `season` identifier** — correctly NOT flagged.

Source of truth: these three columns enter via `betting_ml/utils/feature_selection.py`
— `home_starter_pitcher_id` and `venue_id` survive the correlation/multicollinearity
filter (i.e. they correlate with the targets — the memorization signature), and
`game_year` is in `PROTECTED_FEATURES` (force-retained).

### 1.2 Importance ranks (best-available artifact per target)

> Provenance caveat: the importance artifacts predate the exact 379-feature v4
> tuned contracts and were computed on slightly different feature sets. They are
> the evidence base the story cites; the **§3 ablation on the true v4 contracts is
> the authoritative measurement.** Ranks below are reported honestly with their
> source artifact.

| Feature | Target | Artifact | Importance rank | Score | Flagged before? |
|---|---|---|---|---|---|
| `home_starter_pitcher_id` | home_win | SHAP (`feature_importance_v1.parquet`, XGB/fold2025) | **#12 / 453** | mean\|SHAP\|=0.0296 | **No** (prune=False) |
| `venue_id` | home_win | SHAP | #221 / 453 | mean\|SHAP\|=0.0088 | No |
| `game_year` | home_win | SHAP | — (excluded from that eval set) | — | — |
| `home_starter_pitcher_id` | run_differential | permutation (`run_diff_feature_importance.txt`, ngboost_tuned_2026) | **#11 / 294** | mean_imp=0.00218, **CI-lower=+0.00091** | No (not an exclusion candidate) |
| `venue_id` | run_differential | permutation | exclusion candidate | mean_imp=0.00000 | (zero-importance) |
| `game_year` | run_differential | permutation | exclusion candidate | mean_imp=0.00000 | (zero-importance) |
| `game_year` | total_runs | permutation (`total_runs_feature_importance.txt`, ngboost_decay_weighted) | exclusion candidate | mean_imp=0.00000 | (zero-importance) |
| `home_starter_pitcher_id` | home_win (elasticnet legacy) | \|coef\| | #22 / 483 | coef=−0.0199 | — |

**The memorization/leakage signature:** for `home_starter_pitcher_id` on
run_differential, the permutation **CI-lower is positive (+0.00091)** — shuffling
the column reliably *hurts* MAE, which is the fingerprint of the model memorizing
a raw entity ID rather than learning transferable pitcher skill (pitcher *skill*
is already supplied by the EB starter posteriors and rolling stats). It ranks #11
yet is **not** an exclusion candidate under the importance-only filter — exactly
the blind spot Story 30.1 closes.

**`game_year` is the worst case (train-serve skew):** it is a near-constant temporal
index (cardinality 5 over 2021–2025) that scores ~0 importance in-sample but is
**guaranteed out-of-distribution at serve time** — trained on {2021…2025}, served
as the constant **2026**. Any tree split on `game_year` routes every 2026 row to a
single branch learned on 2025, injecting a fixed, meaningless offset. This
compounds the live `home_win` zero-skill finding ([[project_prod_model_audit_jun2026]]).

---

## 2. Flagger extension  *(AC #3 — DONE & demonstrated)*

The importance-only flagger structurally **cannot** catch a memorized identifier
(`home_starter_pitcher_id` is SHAP #12, far above the `mean_abs_shap < 0.001`
prune threshold). Added a name+cardinality identifier detector.

**New shared module:** `betting_ml/utils/feature_hygiene.py`
- `is_identifier_name(col)` — regex `(_id$|_pk$|^game_year$|^season$|_cluster_id$)`.
- `flag_identifier_features(names, values=None)` — returns `identifier_risk` plus
  cardinality diagnostics.

**Design note (important):** the spec suggested "regex on name + cardinality≈n_rows",
but **cardinality≈n_rows is a poor discriminator** and is NOT used as the primary
signal. Measured on fold_2025 (n=10005): the real identifier
`home_starter_pitcher_id` has card-ratio only **0.068** (the same pitchers recur),
while the legitimate *continuous* feature `home_win_prob_consensus` has card-ratio
**0.60**. A pure cardinality≈n_rows rule would therefore *miss* the recurring IDs
and *false-positive* continuous features. The robust catch is the **name regex**;
cardinality is retained only as a reported diagnostic and as a secondary heuristic
for *unnamed* high-cardinality **integer** surrogate keys.

**Wired into both flaggers:**
- `analyze_feature_importance.py` (SHAP/`prune_candidate`/`noise_risk` source):
  adds `identifier_risk` and folds it in via `prune_candidate = importance_prune OR
  identifier_risk`. New `--reflag-only` fast path re-applies the flag to the
  existing parquet without a refit.
- `feature_importance_per_target.py` (the named file): adds `identifier_risk`
  columns + an "IDENTIFIER/TEMPORAL FEATURES" section to the home_win and
  permutation reports.

**Re-run demonstration** (`analyze_feature_importance.py --reflag-only`, 2026-06-11)
— identifier columns now flagged (all previously `prune_candidate=False`):

| feature | mean_abs_shap | cardinality | card_ratio | importance_prune | identifier_risk | **prune_candidate** |
|---|---|---|---|---|---|---|
| home_starter_pitcher_id | 0.0296 | 611 | 0.077 | False | True | **True** |
| away_starter_pitcher_id | 0.0128 | 618 | 0.077 | False | True | **True** |
| venue_id | 0.0088 | 30 | 0.004 | False | True | **True** |
| away_starter_cluster_id | 0.0034 | 6 | 0.001 | False | True | **True** |
| home_starter_cluster_id | 0.0026 | 6 | 0.001 | False | True | **True** |

---

## 3. Ablation retrain + per-target decision  *(AC #2)*

**Harness:** `betting_ml/scripts/ablation_identifier_features.py`. Controlled
ablation — holds each champion's **architecture fixed** (tuned hyperparameters
copied from the persisted `tuning_results_*.json`) and varies **only** the feature
set: champion (379) vs ablated (376, minus `home_starter_pitcher_id`, `venue_id`,
`game_year`). Mirrors the production recipe exactly (per-fold imputation pipeline,
`all_season_splits(min_train_seasons=3)`, XGB+Platt for home_win, NGBoost-Normal
n_est=500 for run_diff/total_runs).

Both feature sets are scored on:
1. **Walk-forward CV** — primary: Brier (home_win) / MAE (run_diff, total_runs),
   plus NLL/accuracy/ECE/live-corr or RMSE/MedAE/bias/calib_80.
2. **Honest 2026 OOS** — train `game_year < 2026`, eval `game_year == 2026`. This
   is the surface where `game_year`'s OOD penalty actually materializes.

**Decision rule (encoded in the script):** PROMOTE the ablated contract if there is
**no CV regression beyond tolerance** (MAE 0.01 / Brier 0.001) — because the
OOD/memorization risk is removed *structurally* by dropping `game_year` + the raw
IDs, a flat-CV ablation is still a strict hygiene win. A CV regression beyond
tolerance ⇒ KEEP + review.

### ▶ RUN COMMAND (hand-off — retrains 3 models, minutes each; needs Snowflake)

```
uv run python betting_ml/scripts/ablation_identifier_features.py --target all
```

Writes `betting_ml/evaluation/feature_selection/ablation_identifier/ablation_identifier_all.json`
and prints per-fold + live-2026 metrics and a PROMOTE/KEEP decision per target.
(Per project convention this >1-min retrain is handed to the operator to run; it
does not write to Snowflake or `daily_model_predictions`.)

### Results (run 2026-06-11)

Dataset: 10,759 games (2021–2026). **Note:** 2 of the 379 contract features are
absent from the current feature store, so the actual baseline is **377 → 374**
features (champion vs ablated). Both arms share the identical 377 baseline, so the
comparison is fair. Drop set = `home_starter_pitcher_id`, `venue_id`, `game_year`.

**Primary-metric summary** (CV = mean over folds 2024/2025/2026; tolerance: MAE 0.01 / Brier 0.001):

| Target | CV champ | CV ablated | ΔCV | Live-2026 champ | Live-2026 ablated | Decision |
|---|---|---|---|---|---|---|
| home_win | Brier 0.2002 | **0.1991** | −0.0011 (better) | Brier 0.2066 / corr 0.417 / acc 0.668 | **Brier 0.2060 / corr 0.420 / acc 0.671** | **PROMOTE** |
| run_differential | MAE 3.0820 | 3.0840 | +0.0019 (flat) | MAE 3.1210 / calib80 0.774 | **MAE 3.1195 / calib80 0.800** | **PROMOTE** |
| total_runs | MAE 3.3634 | 3.3658 | +0.0024 (flat) | MAE 3.3519 / calib80 0.815 | MAE 3.3614 / calib80 0.813 | **PROMOTE (hygiene)** |

**Per-target decisions:**

- **home_win → PROMOTE (strict win on every accuracy axis).** Ablated beats champion
  on CV Brier (−0.0011) AND on the honest 2026 surface across Brier (0.2066→0.2060),
  NLL (0.5996→0.5984), accuracy (0.668→0.671), and **live corr (0.417→0.420)**, ECE
  flat. Dropping the memorized `home_starter_pitcher_id` + OOD `game_year` *improves*
  honest skill — exactly the hygiene thesis.

- **run_differential → PROMOTE.** CV flat (+0.0019, far inside noise); the honest 2026
  surface *improves* on every accuracy axis — MAE 3.1210→3.1195, RMSE 4.131→4.128,
  MedAE 2.491→2.478 — and **calib_80 moves to nominal (0.774→0.800)**. This is the
  predicted `home_starter_pitcher_id`-memorization pattern: trivial CV cost, live gain.

- **total_runs → PROMOTE (on hygiene; live-neutral, not a live win).** CV flat (+0.0024).
  Honest 2026 is marginally *worse* (MAE 3.3519→3.3614, +0.28%) — but that is **well
  below the noise floor** on 744 games, calib_80 stays at nominal (0.815→0.813), and
  critically **no over-prediction bias is reintroduced** (mean_pred 9.05→9.12 vs actual
  8.97 — the totals directional-bias check passes). Promotion is justified by removing
  the guaranteed-OOD `game_year` constant at flat CV/live; totals is `bet_paused`, so
  the value here is purely hygiene. Honest framing: this is the one target where the
  scrub does **not** improve the honest surface — it is live-neutral.

> If you prefer a stricter bar for the live-neutral total_runs case, the fallback is to
> drop only `game_year` + `venue_id` (unambiguous OOD/zero-signal) and keep
> `home_starter_pitcher_id`; but the full drop is within noise and removes more risk.

### ⭐ Cross-story finding (re-points the live zero-skill → Story 30.3)

The honest-2026 home_win **corr is 0.42** here (champion AND ablated) — strong skill —
whereas [[project_prod_model_audit_jun2026]] measured **live corr ≈ 0.001** on the
*served* `daily_model_predictions`. Same contract, same model family, opposite skill.
**Conclusion: the model contract is NOT the cause of live zero-skill** — when trained
≤2025 and evaluated on 2026 with feature-store-served features it predicts well. The
zero-skill is a **serving-time** problem (features arriving null/misaligned at
`predict_today`), which is exactly **Story 30.3's** mandate. 30.1 hardens the contract
(hygiene); 30.3 must fix the serving path.

### Promotion mechanics — code DONE; training ≠ promotion (S3 + total_runs lineage)

The trainer code change is committed: the three production search trainers
(`run_xgb_home_win_search.py`, `run_ngboost_run_diff_search.py`,
`run_ngboost_total_runs_search.py`) now drop identifier/temporal columns via
`feature_hygiene.is_identifier_name` right after building `feature_cols`, and
`game_year` was removed from `PROTECTED_FEATURES`. Done at the **trainer level (not
globally)** on purpose: `load_retained_features()` is unchanged (still 384), so
`predict_today`'s superset and the live champions are NOT degraded before redeploy.

**⚠️ Correction (verified 2026-06-11): running a search script does NOT promote.**
`save_model()` writes only the **local** `betting_ml/models/<target>/*.pkl` + contract.
But `predict_today` loads each champion via the registry's top-level `artifact_path`,
which is an **S3 URI** (`s3://baseball-betting-ml-artifacts/...`) downloaded by
`load_artifact`. The search scripts never call `upload_artifact`. So a finished local
retrain is inert until the new `.pkl` is pushed to S3.

Deployed-champion map (registry top-level, 2026-06-11):

| Target | prod `artifact_path` (S3) | prod `feature_columns_path` | Search writes that artifact? |
|---|---|---|---|
| home_win | `…/xgb_classifier_tuned_2026.pkl` | `…/feature_columns_xgb_classifier_tuned_2026.json` | ✅ yes |
| run_differential | `…/ngboost_tuned_2026.pkl` | `…/feature_columns_ngboost_tuned_2026.json` | ✅ yes |
| total_runs | `…/**ngboost_eb_enriched_2026.pkl**` | `…/feature_columns_**eb**_2026.json` | ❌ **no** (writes `ngboost_tuned_*`) |

**home_win + run_differential — PROMOTE:**
1. Retrain (home_win search already ran 2026-06-11 18:40 → local contract is 374 feats,
   3 ID cols removed; run_diff still needs its search run). Each prints
   `Story 30.1: dropped 3 identifier/temporal cols: [...]`; the home_win search exits
   non-zero if its Brier regresses >1% vs baseline (gate).
2. **Upload to S3** (this is the actual promotion — predict_today reads the contract
   locally but the model from S3):
   `uv run python scripts/migrate_artifacts_to_s3.py`  (uploads everything under
   `betting_ml/models/` to matching keys), or `upload_artifact` for the single pkl.
3. Bump `deployed_date`/`promoted_at` in the registry.
4. **⚠️ Kill-window reset:** per the registry `model_version_policy`, promoting a new
   champion mid-kill-window RESETS `attribution_start` and restarts the n=150 count
   (Story 28.3). `automated_bets` is already false, so no live-bet risk, but the
   conviction/magnitude monitors must restart against the new model.

**total_runs — DEFERRED to the next totals unpause/promotion (decision 2026-06-11).**
Investigation findings:
- Deployed champion = **eb_enriched** lineage: `ngboost_eb_enriched_2026.pkl` (**S3-only**,
  not present locally) + `feature_columns_eb_2026.json` (**369 feats**, NGBoost Normal
  n=500, max_depth=3, market-blind, **zero sequential features**). Produced in Story 7.M,
  promoted 2026-06-02 (git `02b966d`); **no clean standing producer** (`train_total_runs_prod.py`
  writes the *market_blind* contract, not this one — the 7.M eb retrain was effectively one-off).
- It carries **all 3 identifier columns** (verified) → genuinely un-scrubbed.
- It is a **different lineage on purpose**: the 10 sequential features "add nothing for
  totals," `DO NOT PROMOTE` confirmed 3× (Epic 10.6 / 26.3 / 16.6). So repointing totals to
  the freshly-scrubbed *sequential* `tuned` model would be a (tiny) regression — the wrong fix.
- **`bet_paused: True`** — Epic 19 surfaces **zero** totals bets; informational-only. Unpause
  gate: beat prior-predictive NLL 2.8893 AND prior-naive Brier 0.248 on a rolling 60-game
  live window. So the un-scrubbed ID columns carry **no live betting exposure**.

**Decision:** do NOT re-derive a one-off paused model now. The scrub is **gated on the next
totals unpause/promotion** — at that point the champion is minted from the now-auto-scrubbing
trainers (`run_ngboost_total_runs_search.py` already drops the 3 IDs and is producing a clean
374-feat tuned totals model on the shelf for that moment). The 30.1 ablation (tuned contract)
already showed the scrub is accuracy-neutral for total_runs; both contracts carry the same 3
cols, so the conclusion transfers. **Follow-up owner: whoever unpauses totals (Epic 19) — verify
the promoted champion's contract has 0 identifier cols (`is_identifier_name`) before deploy.**

30.2 can proceed on the cleaned set regardless of promotion status.

---

## Acceptance criteria — ALL MET

- [x] **Table of identifier/temporal features × target × importance rank** — §1.2.
- [x] **Ablation results (CV + live) per target + explicit decision each** — §3 results
  table; all three PROMOTE (home_win strict win; run_diff live-win; total_runs hygiene/live-neutral).
- [x] **Flagger updated + re-run shows the identifier columns now flagged** — §2,
  demonstrated via `--reflag-only` (5 identifier columns now `prune_candidate=True`).

## Files changed
- `betting_ml/utils/feature_hygiene.py` (new) — shared identifier flagger.
- `betting_ml/scripts/model_evaluation/analyze_feature_importance.py` — identifier
  flag folded into `prune_candidate`; `--reflag-only` fast path.
- `betting_ml/scripts/model_evaluation/feature_importance_per_target.py` —
  identifier flag + report sections (home_win coef + permutation paths).
- `betting_ml/scripts/ablation_identifier_features.py` (new) — ablation harness.
- `betting_ml/evaluation/model_evaluation/feature_importance_v1.parquet` — re-flagged.
