# Story 30.4 — Complete market-blindness + dead-weight prune (contract cleanup)

**Status:** code COMPLETE; ablation DONE (2026-06-12) — **all 3 targets PROMOTE cleaned**;
dead-weight artifacts persisted; **champion retrain + S3 promotion handed off** (home_win
+ run_diff; total_runs is shelf-only / bet_paused). **Date:** 2026-06-12. **Epic 30, Track
B (foundation-first).** Un-gates Story 30.6.

Per the Epic 30 operator directive, every decision below is judged FIRST on
**prediction accuracy to the true outcome** (run_diff/total_runs → MAE/RMSE/MedAE +
calib_80; home_win → Brier/NLL/accuracy/ECE + live corr vs the 0/1 winner). Beating
the market is reported as SECONDARY context only — and for the market-blind half it is
not even measurable here (removing the market cols removes the comparison), so the
market decision turns on the **accuracy cost** vs the **edge-validity gain**.

Two sub-stories, applied together in a single retrain per target:
- **30.4a — complete market-blindness:** the trainers were only
  *consensus-and-moneyline-blind*; 9 market-derived cols leaked into every contract.
- **30.4b — dead-weight prune:** drop the features whose 2026-OOS permutation
  importance is ≤0 (shuffling them doesn't hurt) — shrinks the serving-skew surface.

---

## 1. The market leak is 9 columns, not 6  *(AC #1, market half)*

The 30.4 spec named **6** leaked cols. A full scan of the three deployed `*_tuned_2026`
contracts (all identical, 376 feats = 374 base + the 2 imputation indicators) found
**9** market-derived columns absent from `_MARKET_COLS_TO_EXCLUDE`:

| # | leaked col | source | family | named in spec? |
|---|---|---|---|---|
| 1 | `over_prob_consensus` | totals consensus | totals-market | ✅ (also in PROTECTED) |
| 2 | `under_implied_prob` | totals odds → implied P | totals-market | ✅ |
| 3 | `total_line_movement` | totals line open→close | line movement | ✅ |
| 4 | `home_ml_money_pct` | public betting (8.R) | public % | ✅ |
| 5 | `over_ticket_pct` | public betting (8.R) | public % | ✅ |
| 6 | `market_bookmaker_count` | book availability | market meta | ✅ (also in PROTECTED) |
| 7 | `over_american` | raw totals odds price | odds price | ⚠ spec UPDATE — confirm in-contract → **yes** |
| 8 | `under_american` | raw totals odds price | odds price | ⚠ spec UPDATE — confirm in-contract → **yes** |
| 9 | `total_line_std` | `mart_odds_consensus` stddev(total_line) | totals-market dispersion | ❌ **NEW finding** |

**The 9th (`total_line_std`) is a name-collision leak.** The exclude set strips
`totals_line_std` / `totals_line_range` (plural, from `mart_bookmaker_disagreement`),
but `total_line_std` (singular, the **consensus** stddev of the betting total from
`mart_odds_consensus`, surfaced via `feature_pregame_odds_features` →
`feature_pregame_game_features`) slipped through the near-identical name. It is just as
market-derived as `total_line_consensus` (which IS excluded) and is a residual
circularity risk for any totals model-vs-market claim.

Verification (2026-06-12):
```
elasticnet/run_diff/total exclude sets — identical, 42 cols each (33 + 9)  ✓
all 9 leaks present in home_win/run_diff/total tuned contracts (376)        ✓
over_prob_consensus, market_bookmaker_count removed from PROTECTED_FEATURES  ✓
```
The 3 cols 30.3's `[FEATURE-ALIGN]` flagged "all-null at serve" reduce to exactly the
odds-price market cols `over_american` / `under_american` / `under_implied_prob` (the
umpire pair was fixed by 30.5) — removing them here also clears that serve noise.

### Dead-weight classification *(AC #1, dead-weight half)*

Produced by `influence_report.py --target all` (permutation importance on the honest
2026 OOS surface; `all_features[*].tier ∈ {strong, moderate, weak, dead}`). **Run
2026-06-12** on the freshly-scrubbed local champions (after the `_PermAdapter` fix that
lets `permutation_importance` accept the pre-fitted `PlattCalibratedXGBClassifier`):

| Target | baseline | dead-weight | will-prune (after guards) | cleaned ≈ |
|---|---|---|---|---|
| home_win | Brier 0.2031 | 167/376 (44%) | **156** | 376 − 9 mkt − 156 ≈ **211** |
| run_differential | MAE 3.1888 | 207/376 (55%) | **198** | ≈ **169** |
| total_runs | MAE 3.3560 | 270/376 (72%) | **254** | ≈ **113** |

**⭐ The signal is concentrated, not diffuse (revises the stale INFLUENCE_REPORT.md
headline).** The bullpen EB-posterior pair `home_bp_eb_xwoba` / `away_bp_eb_xwoba` is
**#1/#2 on all three targets** (home_win 35%+32% of importance; run_diff 27%+21%;
total_runs 25%+21%), with the bullpen EB family (xwoba + coverage_pct + uncertainty)
carrying the majority of run_diff/total signal. (Caveat: computed on the raw
`fillna(0.0)` surface, not `build_imputation_pipeline` — magnitudes are approximate, but
the dead/strong tiers are robust and that is all the prune consumes.)

**Guards verified against the JSON (do-not-prune kept, never silently dropped):**
- `ump_run_impact_zscore` / `ump_accuracy_zscore` tier **dead** on 2026 even though
  30.5 just fixed their serving — the exact "mis-served → mislabeled dead" case; KEPT
  on all three targets (give the now-served feed a fair shot before any prune).
- imputation indicators (`has_starter_platoon_data`/`is_new_venue`) KEPT on all three.
- dead sequential posteriors (`*_sequential_woba`, `*_sequential_bullpen_xwoba`) KEPT
  (model-derived; flat 2026 permutation ≠ no live value).

**Where the market-blind cost will land:** for **total_runs all 9 leaks are dead**
(removing them costs ~nothing — clean win). For **home_win / run_diff, 4 leaks remain
influential** (`over_prob_consensus`, `under_implied_prob`, `home_ml_money_pct`, and
`over_ticket_pct`/`under_american`/`total_line_movement` resp.) — so the accuracy cost of
completing market-blindness, if any, shows up on these two and is the operator
accept/reject call (§3). The ablation `market_blind` arm quantifies it.

> Cross-check (per spec): the dead-weight prune is restricted to the already-market-blind
> base and explicitly **protects** mis-served / model-derived features from being
> mislabeled dead — `ump_*_zscore` (fixed in 30.5), the imputation indicators, and the
> sequential posteriors. The harness logs any overlap; it never silently prunes them.

---

## 2. Code changes (deterministic regeneration) — DONE

| File | Change |
|---|---|
| `betting_ml/scripts/train_elasticnet_prod.py` | +9 cols in `_MARKET_COLS_TO_EXCLUDE` (33→42) |
| `betting_ml/scripts/train_run_diff_prod.py` | +9 cols (33→42) |
| `betting_ml/scripts/train_total_runs_prod.py` | +9 cols (33→42) |
| `betting_ml/utils/feature_selection.py` | drop `over_prob_consensus` + `market_bookmaker_count` from `PROTECTED_FEATURES` (mirrors the 30.1 `game_year` un-protect) |
| `betting_ml/utils/feature_hygiene.py` | new `load_dead_weight_exclude(target)` — reads the promoted prune artifact (no-op until written) |
| `betting_ml/scripts/run_xgb_home_win_search.py` · `run_ngboost_run_diff_search.py` · `run_ngboost_total_runs_search.py` | Story 30.4b hook: drop `load_dead_weight_exclude(...)` cols right after the 30.1 identifier scrub, before fold-building (so the regenerated contract auto-excludes them) |
| `betting_ml/scripts/ablation_market_deadweight.py` | new — the 3-arm ablation harness (§4) |

**Why this regenerates cleanly:** the search trainers build `feature_cols`, strip
`_MARKET_COLS_TO_EXCLUDE` (now market-blind), strip identifiers (30.1), then strip
dead-weight (30.4b), and write the contract from the **post-imputation**
`list(last_fold["X_train"].columns)` — so the new contract includes the 2 imputation
indicators (avoids the `predict_today` CONTRACT-GUARD 374-vs-376 IndexError) and
excludes all of the above. Market-blindness needs no per-target list; dead-weight is
driven by the committed `dead_weight_exclude.json` artifact (written on a PROMOTE).

---

## 3. The built-in tradeoff (market half)

Market features HELP raw accuracy (the book is sharp) but INVALIDATE any model-vs-market
edge measurement (circularity). Epic 30's PRIMARY metric is accuracy-to-truth, so the
9-col removal **may cost a little accuracy** — this is NOT an automatic remove. The
ablation isolates the cost in the `market_blind` arm; the decision rule (§4) ACCEPTS a
small accuracy regression for the edge-validity gain (operator call, surfaced) but
treats the dead-weight prune as pure hygiene (PROMOTE iff no regression). If the 9 cols
turn out highly influential, that itself is the finding (the base models lean on the
book more than the architecture intends).

Note `best_alpha=0` right now: the alpha tuner gives the base model zero weight vs
market, so live edges/Kelly are ~0 regardless — completing market-blindness will not
move edge until alpha re-tunes (expected; judge 30.4 on accuracy-to-truth).

---

## 4. Ablation harness  *(AC #2)*

`betting_ml/scripts/ablation_market_deadweight.py` — same controlled recipe as the 30.1
harness (architecture fixed at the tuned champion hyperparameters; only the feature set
varies). **Three arms per target**, scored on walk-forward CV + honest 2026 OOS:

```
champion      = current *_tuned_2026 contract                       (374 df-present + 2 indicators)
market_blind  = champion − the 9 market leaks present               (isolates the market-blind cost)
cleaned       = market_blind − dead-weight (influence tier=="dead") (the proposed new contract)
```

Reported per target: CV + live-2026 primary metrics for all three arms, `ΔCV(market_blind)`
(the accuracy cost of market-blindness), `ΔCV(dead_weight)` (the prune cost), and a
per-target decision. **Decision rule (encoded):**
- dead-weight prune regresses CV beyond tol (MAE 0.01 / Brier 0.001) → **KEEP market_blind** (review prune list);
- else market-blind regresses beyond tol → **PROMOTE cleaned w/ ACCEPTED market-blind accuracy cost** (edge-validity gain, flagged);
- else → **PROMOTE cleaned** (strict hygiene + market-blindness win).

`--write-exclude` persists the promoted dead-weight list to
`betting_ml/models/<target>/dead_weight_exclude.json` so the trainer regenerates the
pruned contract deterministically.

### ▶ RUN COMMANDS (hand-off — >1 min, needs Snowflake; retrains 3 models × 3 arms)

```
# Task 1 — refresh the dead-weight tiers on the local champions (writes influence_all.json):
uv run python betting_ml/scripts/influence_report.py --target all

# Task 2 — the 3-arm market-blind + dead-weight ablation. Run ONE TARGET PER INVOCATION
# (NGBoost retrains are minutes each; parallelizable across shells — the serial
# `--target all` loop is slow). Writes a per-target market_deadweight_<t>.json sidecar.
uv run python betting_ml/scripts/ablation_market_deadweight.py --target home_win
uv run python betting_ml/scripts/ablation_market_deadweight.py --target run_diff
uv run python betting_ml/scripts/ablation_market_deadweight.py --target total_runs

# Task 3 — inspect decisions, THEN persist the dead-weight lists for PROMOTE targets
# WITHOUT retraining (reads the saved JSON; no Snowflake):
uv run python betting_ml/scripts/ablation_market_deadweight.py --target all --persist-only
```
Writes `…/influence_report/influence_all.json` and
`…/market_deadweight/market_deadweight_all.json`. Neither writes to Snowflake or
`daily_model_predictions`.

---

## 5. Results  *(AC #2 — TO FILL after the operator run)*

> Run 2026-06-12. Tolerance: MAE 0.01 / Brier 0.001. (CV champ uses the 374 df-present
> base + 2 imputation indicators; "cleaned" = market_blind − dead-weight.)

| Target | CV champ | CV market_blind (Δ) | CV cleaned (Δdead) | Live champ | Live cleaned | n_feat | Decision |
|---|---|---|---|---|---|---|---|
| home_win | Brier 0.1991 | 0.1995 (+0.0005) | 0.2000 (+0.0005) | Brier 0.2059 / corr 0.420 / acc 0.667 | **Brier 0.2036 / corr 0.431 / acc 0.671** | 376→**209** | **PROMOTE cleaned** |
| run_differential | MAE 3.0831 | 3.0818 (−0.0013) | 3.0691 (−0.0127) | MAE 3.1199 / RMSE 4.129 / calib80 0.800 | **MAE 3.0815 / RMSE 4.099 / calib80 0.806** | 376→**167** | **PROMOTE cleaned** |
| total_runs | MAE 3.3657 | 3.3658 (+0.0002) | 3.3643 (−0.0015) | MAE 3.3618 / RMSE 4.185 / calib80 0.815 | **MAE 3.3367 / RMSE 4.174 / calib80 0.806** | 376→**111** | **PROMOTE cleaned (shelf — bet_paused)** |

Dead-weight prune lists persisted (no retrain) to `betting_ml/models/<t>/dead_weight_exclude.json`:
home_win **156**, run_differential **198**, total_runs **254** cols.

**home_win → PROMOTE via CORRECTNESS OVERRIDE (not an accuracy win).** ⚠ Corrected by the
codified promotion gate (Case 3, `promotion_gate_eval.py`, 2026-06-12): on the **completed
held-out seasons (2024+2025)** the cleaned challenger (retuned, 209f) vs the deployed
champion (374f, still market-leaking) is **pooled ΔBrier −0.0016 — below the 0.002 noise
floor and NOT bootstrap-significant** (CI [−0.0035, +0.0004]). The earlier "strict win"
read leaned on the **partial 2026** surface (ΔBrier −0.0076), which the gate treats as
corroboration only. So this is **NOT an accuracy win** — it's accuracy **parity** (the
champion's leaks inflate its in-sample accuracy, so matching it while market-blind *is* the
30.4a result). **Operator decision (2026-06-12): PROMOTE on the correctness override —
market/identifier leakage is a Principle-3 violation that must be removed regardless of an
accuracy win.** The gate confirmed accuracy **non-regression** (consistency_pass; no
completed-season regression), which the override requires. Record: removes 9 market leaks +
3 identifiers; 374→209 features; smaller serving surface. Re-run for the recorded artifact:
`promotion_gate_eval.py --target home_win --correctness-override "30.4: removes 9 market leaks
+ 3 identifiers (architecture Principle 3); gate-confirmed accuracy non-regression"`.

**run_differential → PROMOTE cleaned (the standout win).** The 198-col dead-weight prune
(376→167, a 55% contract reduction) *lowers* CV MAE by 0.0127 AND live MAE by 0.038
(3.120→3.082), with RMSE 4.129→4.099 and calib_80 moving to nominal (0.800→0.806). The
market-blind half is flat (−0.0013 CV; +0.0025 live MAE, noise). The big dead-weight set
was actively adding variance — removing it is a clear accuracy + serving-surface win.

**total_runs → PROMOTE cleaned (accuracy win; stays bet_paused).** Most aggressive prune
(254 cols, 376→111 — a 70% reduction). Market-blind is exactly flat (+0.0002 CV — all 9
leaks were already dead for totals, confirming the §1 prediction); dead-weight prune
improves CV (−0.0015) and live MAE (3.362→3.337) + RMSE. calib_80 slips 0.815→0.806 (both
nominal, well inside noise on 744 games) and the directional-bias check holds (no
over-prediction reintroduced). **Caveat (per 30.1):** the deployed totals champion is the
S3-only `eb_enriched` (369-feat) lineage, NOT this `tuned` model — so this PROMOTE applies
to the *shelf* tuned model and its `dead_weight_exclude.json` feeds
`run_ngboost_total_runs_search.py` for whenever Epic 19 unpauses totals. Do NOT push to S3
now (bet_paused; no live exposure).

> **⚠ Shelf-model distribution switched at retrain (2026-06-12):** the `total_runs`
> search selected **LogNormal** n=500 (CV MAE 3.3531) over Normal (3.3617) — but the
> 30.4 ablation only validated **Normal** (calib_80 0.806). The cleaned *contract*
> (111 feats → 113 w/ indicators) is exactly what 30.4 promotes; the predictive
> *distribution* is now LogNormal, whose calib_80 / PI coverage + the totals
> directional-bias check (AVG pred vs AVG actual, pct_over_edge) are UNVALIDATED.
> Shelf-only (bet_paused; deployed champion is eb_enriched/Normal), so no live impact —
> but the Epic 19 unpause owner MUST re-check LogNormal calibration + directional bias
> before any totals go-live. (run_diff keeps Normal — LogNormal is invalid there.)

**Per-target narrative (to write):** state the market-blind accuracy cost and the
edge-validity gain explicitly for each; for the dead-weight prune, the new feature count
and the reduced serving surface; tie home_win/run_diff back to the honest live re-measure
(§7). For total_runs note it is `bet_paused` (eb_enriched is the deployed champion;
`tuned` is the local proxy) — the cleanup is hygiene + the 30.4a circularity fix.

### ⚠️ Retrain "baseline Brier" is a NO-SKILL FLOOR, not the champion (+ follow-up)

The home_win retrain printed `Baseline XGBoost Platt Brier: 0.2459` → `Tuned: 0.1952`
→ "+20.60% IMPROVED". **Do NOT read 0.2459 as the prior champion.** It comes from
`_load_baseline_brier()`:
```sql
SELECT AVG(brier_score) FROM baseball_data.betting_ml.cv_results_win_outcome WHERE model = 'xgb_platt'
```
That table holds the **baseline-model CV results** (`train_win_outcome_baselines.py`),
6 rows (folds 2024–2026). Every baseline there clusters at 0.241–0.249 — barely below
the `naive_baseline` (0.2494 = the home-field base-rate prior), i.e. **~zero skill**. So
the "+20.6%" is the tuned model beating a coinflip floor — a sanity gate (the search
exits non-zero only if it regresses >1% vs this floor), **not** a champion-vs-challenger
result. The number that actually judges 30.4 home_win is the tuned CV Brier **0.1952** vs
the **prior champion** (~0.199 in the 30.1 ablation; the 30.4 fixed-hp cleaned arm = 0.200)
— a genuine but small improvement. The floor is static (populated once; never refreshed
per retrain), so it stays ~0.246 no matter how good the champion gets.

**⭐ FOLLOW-UP (behavior change needed — this floor-comparison is misleading):** the
search trainers (`run_xgb_home_win_search.py` baseline-Brier; the run_diff/total_runs
baseline-MAE equivalents) headline "+X% IMPROVED vs baseline" against a no-skill floor,
which reads as a far bigger win than it is and can mask a real regression vs the deployed
champion (a tuned model could *beat the floor* while *losing to the current champion* and
still print "IMPROVED ✓"). Change the comparison to the **prior/deployed champion's CV
metric** (and/or report BOTH: vs-floor as a sanity gate + vs-champion as the real delta),
and gate promotion on the champion delta, not the floor. Tracked as a small Epic 30
cleanup item.

---

## 6. Promotion mechanics (training ≠ promotion)

Same as 30.1 — running a search script writes only the **local** pkl + contract;
`predict_today` loads the model from **S3**. To promote a cleaned champion:
1. `--write-exclude` the promoted dead-weight list (§4), then re-run the search trainer
   (`run_xgb_home_win_search.py` / `run_ngboost_run_diff_search.py`) — it prints
   `Story 30.4b: dropped N dead-weight cols` and regenerates the pruned, market-blind contract.
2. Upload to S3 (the actual promotion): `uv run python scripts/migrate_artifacts_to_s3.py`.
3. Bump `deployed_date`/`promoted_at` in the registry; consult `docs/model_promotion_runbook.md`.
4. **Kill-window reset (home_win):** promoting a new champion resets the 28.3 + 28.6b
   kill-windows — reset `attribution_start` in the registry block AND in the monitor
   scripts. `automated_bets` is already false, so no live-bet risk.
- **total_runs:** DEFERRED with 30.1 — `bet_paused`, deployed champion is the S3-only
  `eb_enriched` lineage with no standing producer. The 30.4a market scrub still applies
  the moment totals is re-minted from the auto-scrubbing trainer (Epic 19 unpause owner
  verifies 0 market leaks + 0 identifiers before deploy).

---

## 7. Re-measure on BOTH surfaces (post 30.3)

Per the 30.3 resolution, measure each retrain on **both** the offline CEILING
(`load_features`, post-game-dense — NOT the live target) AND the honest LIVE surface
(`betting_ml/scripts/honest_live_skill.py`, scores actually-served
`daily_model_predictions` vs truth). Do not declare a live verdict on <30 settled
post_lineup/feature_store games. The ablation's "live 2026" arm is the offline CEILING;
`honest_live_skill.py` is the live truth.

---

## 8. Un-gates Story 30.6 (AS-OF snapshot) — forward-capture companion

This retrain is the "base-model retrain queued" that un-gates 30.6. The 30.6
forward-capture (a Dagster op appending today's as-served `feature_pregame_game_features`
rows to a dated `*_asof` snapshot, + `load_features_asof()`) should be stood up **now**
so the snapshot clock starts (forward-only; the past is unrecoverable) — but it is
genuinely separate pipeline infra and its point-in-time retrain only pays off after ≥1
season of snapshots. **Scope decision (2026-06-12): DEFERRED to Story 30.6** — the
snapshot pays off only after ≥1 season AND a point-in-time retrain, and 30.3's
`honest_live_skill.py` already covers the eval-honesty need; building the live-pipeline
snapshot infra now would be speculative. 30.4's retrain remains the trigger that
un-gates 30.6.

---

## Acceptance criteria

- [x] Per-target feature-classification approach (market-leak / dead-weight / strong)
  wired via `influence_report.py` + the 3-arm ablation; **market-leak table is §1 (9 cols)**.
  Dead-weight table fills from the operator `influence_report.py` run.
- [x] Ablation results (CV + 2026 OOS) for market-blind-completion AND dead-weight-prune
  per target + explicit promote/keep decision + the accuracy-vs-edge-validity tradeoff —
  §5. All three PROMOTE cleaned (run 2026-06-12); market-blind cost negligible everywhere,
  dead-weight prune *improves* the honest surface (run_diff −0.038 live MAE the standout).
- [x] Updated `_MARKET_COLS_TO_EXCLUDE` (×3) + `PROTECTED_FEATURES` edit + the trainer
  dead-weight hook; pruned contracts regenerate deterministically; reduced feature count
  + smaller serving surface documented (§1–§2), tied to the 30.3 live re-measure (§7).

## Files changed
- `betting_ml/scripts/train_elasticnet_prod.py`, `train_run_diff_prod.py`, `train_total_runs_prod.py` — +9 market cols.
- `betting_ml/utils/feature_selection.py` — un-protect the 2 market cols.
- `betting_ml/utils/feature_hygiene.py` — `load_dead_weight_exclude()`.
- `betting_ml/scripts/run_xgb_home_win_search.py`, `run_ngboost_run_diff_search.py`, `run_ngboost_total_runs_search.py` — 30.4b prune hook.
- `betting_ml/scripts/ablation_market_deadweight.py` (new) — 3-arm ablation harness.
