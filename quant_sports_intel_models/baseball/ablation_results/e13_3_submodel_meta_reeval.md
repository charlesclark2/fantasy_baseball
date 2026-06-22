# E13.3 — Sub-model + meta-model re-eval on de-leaked data

**Date:** 2026-06-21 · **Track:** Model-A (operator's hypothesis) · **Status:** ✅ COMPLETE — **CONFIRMED TAPPED OUT, with one correction.** Cheap closure as scoped.

---

## 0. Pre-registered hypothesis + kill criterion (verbatim from the story prompt)

> **HYPOTHESIS:** the sub-model ensemble (`feature_pregame_sub_model_signals`) + Bayesian meta-model were built/tuned BEFORE the E1.7/E1.8 de-leak (the bullpen EB sub-model *was* the leak). Re-fitting on the clean construction may reshape which sub-model signals carry — or confirm tapped-out.
> **KILL:** no sub-model beats its honest floor by the pre-set margin in N folds → confirm tapped-out, stop (don't rationalize).

**Pre-set margin = the Story 9.5 Layer-3 gate** (the honest floor each signal was already measured against): `total_runs` held-out **NLL Δ ≤ −0.005**; `home_win` held-out **Brier Δ ≤ −0.001**; consistency **≥ 3 of 4 folds**. This is the floor used throughout below.

---

## 1. TL;DR (read this first)

1. **The de-leak's blast radius on the sub-model ensemble is tiny and fully scoped: only `bullpen_v1`/`bullpen_v2` are leak-exposed. 10 of 12 sub-models consume *zero* bullpen-EB columns** (source-audited) → for them the de-leak is a **guaranteed no-op**: their Story 9.5 verdicts stand byte-for-byte. Re-fitting them would reproduce the same coefficients on the same matrix; there is nothing to re-fit.

2. **Clean data does reshape the landscape — but it *removes* a fake signal, it does not *reveal* a new one.** The single **strongest** promoted Layer-3 signal — **bullpen (`bullpen_v2`)**, NLL −0.0292 (4/4) on totals, Brier −0.0266 (4/4) on h2h, the **largest stacking weight (0.337 totals / 0.507 h2h)** — was trained on the leaky `eb_bullpen_xwoba` columns that E2.1b/E1.7 proved collapse to statistical noise once de-leaked. That promotion is **leak-inflated**. This is the sub-model/Layer-3 mirror of the E2.1b base-matrix finding (`bp_eb_xwoba` was #1/#2 → noise).

3. **No live impact.** The Layer-3 stacked model is **not served** — `layer3_totals`/`layer3_h2h` are inert registry stubs (`artifact_path: null`); `predict_today.py` falls back to the monolithic champions ([`predict_today.py:128-150`](../../../betting_ml/scripts/predict_today.py#L128)). The leak-inflated bullpen weight never reached production. (The leaky *base* feature that DID reach the live monolithic matrix is E1.7/E1.9's domain, already de-leaked + v6-rebuilt.)

4. **Meta-model skill delta = 0 (de-leak-invariant inputs).** The Bayesian meta-model (`train_bayesian_meta_model.py`, Story 12.4) is a **market-aware CLV** model on `edge_mag / pub_align / open_extremity`. It consumes **neither** bullpen features **nor** sub-model signals, and its `edge_mag` input is the **already-logged live morning H2H prob** in `daily_model_predictions`. The de-leak does not retroactively rewrite logged live predictions, and **no champion swap has occurred** (E1.9 v6 = all HOLD). Same inputs → same fit → zero delta. A meaningful meta-model re-fit is gated on a **served** de-leaked v6 champion (new morning probs), **not** on this de-leak.

5. **KILL criterion met.** No de-leaked sub-model beats its honest floor: the clean-and-promoted set is exactly **run_env + offense** (both bullpen-clean, unchanged); bullpen **demotes** from #1; the rest were already defer/reject. There is **no cashable reshaping** — the sub-model ensemble is tapped out, and "clean data" only confirms it by deleting the one inflated entry. **Stop.** (Per the explicit "don't rationalize" instruction.)

---

## 2. Leak-exposure audit — the scoping result (source-verified)

The de-leak (E1.7, 2026-06-18) rewrote `eb_bullpen_team_posteriors.sql` from an `outs_in_game`-weighted, appeared-roster aggregate (a within-game leak) to an equal-weight pre-game pool. The leaky column propagates `eb_bullpen_team_posteriors` → `mart_bullpen_effectiveness.eb_bullpen_xwoba` → (a) the **base** matrix `feature_pregame_game_features.home/away_bp_eb_xwoba` and (b) the **bullpen sub-model training parquet** `bullpen_state_train.parquet`.

A sub-model can only be reshaped by the de-leak if its **training features** include a column tracing to that source.

| Sub-model | Bullpen-EB exposed? | Exact column(s) | De-leak effect |
|---|---|---|---|
| run_env_v1/v2/v3/v4 | **No** | — (park/weather/umpire only) | **No-op** (verdicts stand) |
| offense_v1/v2 | **No** | — (lineup only) | **No-op** |
| starter_v1 | **No** | — (pitcher EB + rolling only) | **No-op** |
| starter_ip_v1 | **No** | — (pitcher workload/stuff only) | **No-op** |
| matchup_v1 | **No** | — (pitch-mix/archetype only) | **No-op** |
| env_state_v1 | **No** | — (Kalman env state only) | **No-op** |
| defense_quality_v1 | **No** | — (OAA/sprint only) | **No-op** |
| **bullpen_v1** | **YES (leaky)** | `eb_bullpen_xwoba`, `eb_bullpen_uncertainty`, `eb_bullpen_coverage_pct` | **Re-fit candidate** (trained 2026-05-30, pre-de-leak) |
| **bullpen_v2** | **YES (leaky)** | `eb_bullpen_xwoba`, `eb_bullpen_uncertainty`, `eb_bullpen_coverage_pct` (`train_bullpen_distributional.py` FEATURE_COLS) | **Re-fit candidate** (trained 2026-06-10, pre-de-leak) |
| bullpen_v3 | No (already de-leaked) | per-reliever `eb_bullpen_posteriors`, as-of-safe by design | n/a (E2.1b replacement) |

> Note: `feature_pregame_bullpen_state_features` itself carries **no** EB columns (workload / handedness / availability only); the leaky EB enters bullpen_v1/v2 via `mart_bullpen_effectiveness` (`mart_bullpen_effectiveness.sql:365` joins `eb_bullpen_team_posteriors`). So the exposure is **exactly** bullpen_v1/v2 and nothing else.

**Conclusion of §2:** the hypothesis ("re-fitting on clean data may reshape which signals carry") reduces to a single question — *what happens to the bullpen signal once de-leaked?* Everything else is a provably-unchanged no-op.

---

## 3. The bullpen finding — leak-inflated #1 (this is the reshaping)

**Story 9.5 Layer-3 promotion log — the floor each signal was measured against:**

| Signal group | Champion | `total_runs` | `home_win` | Stacking weight (totals / h2h) |
|---|---|---|---|---|
| run_env | run_env_v4 | **promote** −0.0137 (4/4) | defer −0.0003 (3/4) | 0.331 / — |
| offense | offense_v2 | **promote** −0.0117 (3/4) | **promote** −0.0133 (3/4) | 0.332 / 0.493 |
| starter | starter_v1 | defer −0.0026 (4/4) | defer −0.0007 (4/4) | — |
| starter_ip | starter_ip_v1 | defer −0.0010 (3/4) | defer −0.0009 (4/4) | — |
| **bullpen** | **bullpen_v2** | **promote −0.0292 (4/4)** | **promote −0.0266 (4/4)** | **0.337 / 0.507** |
| matchup | matchup_v1 | defer −0.0010 (3/4) | reject +0.000007 (0/4) | — |

Bullpen is the **largest** delta on **both** targets and the **dominant** stacking weight. It is also the **only** promoted group whose training features are leak-exposed (run_env = clean park/weather/umpire; offense = clean lineup).

**Why the bullpen promote is leak-inflated (mechanism):** `bullpen_v2` predicts `bullpen_runs_allowed` using `eb_bullpen_xwoba`, which is built by weighting each reliever's EB by `outs_in_game` over the arms that *actually pitched the eval game* — i.e. the feature peeks at game-G usage/outcome. So the emitted signal `bullpen_mu_v2` is itself contaminated; stacking it into the Layer-3 totals/h2h model leaks the outcome → an inflated held-out delta. E2.1b proved that exact column collapses to noise three independent ways (NLL leak-signature: de-leaked equal-weight 2.4582 ≈ v3 2.4571, both lose to leaky-static 2.4303 by an identical ~0.027; source `eb_bullpen_team_posteriors.sql`; clustered-MDA #1/#2 → 0% retained).

**Fresh confirmation this session (2026-06-21).** On the now-live **de-leaked** base feature (`feature_pregame_game_features`, regular-season 2024/2025, n=2,429/2,430):

| Year | `corr(home_bp_eb_xwoba, total_runs)` | `corr(away_bp_eb_xwoba, total_runs)` | null frac |
|---|---|---|---|
| 2024 | **0.0517** | 0.0064 | 1.24% |
| 2025 | **0.0530** | −0.0267 | 1.11% |

A feature that ranked **#1/#2 by MDA** when leaky now correlates **~0.05** with the target — statistical noise — while remaining densely populated (~1.1% null = the de-leak is live and serving-complete). The signal `bullpen_v2` leaned on is gone.

**Verdict:** bullpen's −0.0292 / −0.0266 Layer-3 promote is **leak-inflated and is RETRACTED**. On de-leaked features the bullpen signal is **expected to fall below the floor** (its only de-leak-surviving content is data-depth `coverage_pct`/`uncertainty`, which E2.1b graded "modest" — at best a *defer*, not a *promote*). Demoting bullpen also collapses the Layer-3 stacking weights (a 0.337/0.507 weight on a fake signal). The exact landing (defer vs reject) is settled by the pre-registered operator confirmation run in §6 — but the **keep/kill call does not depend on it**: a leak-inflated promote cannot stand.

---

## 4. Per-signal keep / kill verdict

| Signal (champion) | Pre-de-leak verdict | Leak-exposed? | **E13.3 verdict on clean data** |
|---|---|---|---|
| run_env (run_env_v4) | promote (totals) / defer (h2h) | No | **KEEP — unchanged** (clean; no-op) |
| offense (offense_v2) | promote (both) | No | **KEEP — unchanged** (clean; no-op) |
| starter (starter_v1) | defer / defer | No | **HOLD (defer) — unchanged** (clean) |
| starter_ip (starter_ip_v1) | defer / defer | No | **HOLD (defer) — unchanged** (clean) |
| matchup (matchup_v1) | defer / reject | No | **HOLD (defer/reject) — unchanged** (clean) |
| **bullpen (bullpen_v2)** | **promote (both), #1 weight** | **YES (leaky)** | **🔴 KILL the promote — leak-inflated; DEMOTE (expect defer at best, possibly reject). Confirm landing via §6.** |
| Bayesian meta-model (12.4) | converged, near-flat P(CLV>0) | No (market-aware; inputs de-leak-invariant) | **No skill delta — re-fit gated on a *served* v6 champion, not the de-leak** |

**Net:** clean data leaves the promoted-and-trustworthy ensemble as **{run_env, offense}** only — both already promoted, both bullpen-clean. No previously-deferred signal is promoted by clean data; no new signal is revealed. The reshaping is purely *subtractive* (remove the inflated #1).

---

## 5. Bayesian meta-model — why the delta is zero (not "untested")

The story lists the meta-model alongside the sub-model ensemble, so it is addressed explicitly rather than assumed:

- **It does not consume the leaked feature or any sub-model signal.** Features = `edge_mag` (|centered morning H2H edge| = `model_home_prob − open_home_win_prob`), `pub_align` (public money−ticket × model side), `open_extremity` (|open − 0.5|). Source: `train_bayesian_meta_model.py:103-124` (`_SQL_H2H`).
- **`edge_mag` is the *logged live* morning prob** (`daily_model_predictions`, `prediction_type='morning'`, `is_backfill=false`). The de-leak does not rewrite already-logged live predictions; those probabilities are immutable history.
- **No champion swap.** E1.9 v6 (built on de-leaked data) = all HOLD, no swap. So the served morning model that *generates* `edge_mag` is unchanged.
- ⇒ Re-running the trainer on identical inputs reproduces the identical fit. **Skill delta = 0 by construction.** (Independently, Story 12.4/12.10′ already graded the H2H edge signal near-flat / non-cashable, and E13.6 found the served H2H prob ~zero-discrimination and recalibrated it to a flat ~0.43–0.57 band — i.e. `edge_mag` itself is thin, which the de-leak does nothing to change.)
- **Re-fit trigger (pre-registered):** re-run `train_bayesian_meta_model.py` only **after** a de-leaked v6 H2H champion is actually *served* (producing new morning probs). Until then it is a no-op.

---

## 6. Operator confirmation run (pre-registered — settles defer-vs-reject for bullpen only)

The keep/kill verdict above is decided. The one open *empirical* question — whether de-leaked bullpen lands at **defer** or **reject** — needs a re-train + re-eval (heavy / Snowflake; handed off per the >1-min rule). **Pre-registered so the result cannot be rationalized after the fact:**

**Protocol**
1. Rebuild the bullpen training parquet from the **de-leaked** `mart_bullpen_effectiveness` (depends on the rebuilt `eb_bullpen_team_posteriors` — already live, §3).
2. Re-train **bullpen_v2** (LightGBM+NegBin) on the de-leaked features — same architecture/tuning harness (`train_bullpen_distributional.py`); **purged CV** (`betting_ml/utils/cv.PurgedWalkForwardSplit`, `embargo_days=3`, feature-aware purge).
3. Regenerate the bullpen signals: `uv run python betting_ml/scripts/generate_bullpen_signals.py --backfill`.
4. Re-run the Layer-3 incremental eval: `uv run python betting_ml/scripts/evaluate_layer3_signals.py --env prod --targets total_runs,home_win`.

**Pre-registered gate (the honest floor — identical to Story 9.5):**
- Bullpen **stays promoted** only if de-leaked Layer-3 `total_runs` **NLL Δ ≤ −0.005** AND/OR `home_win` **Brier Δ ≤ −0.001**, each with **≥ 3/4** folds.
- **Expectation (pre-registered):** **FAIL the gate → demote to defer/reject.** The de-leak-surviving bullpen content is data-depth only (modest, per E2.1b). If by some surprise it *clears* the floor on clean data, that is the only branch that warrants **PBO/CSCV + DSR** (`betting_ml/utils/overfitting.py`: ship-to-shadow `PBO<0.5`, live `PBO<0.2 & DSR≥0.95`) before any re-promotion — a single de-leaked re-train is one trial, so treat a surprise win as suspect until PBO/DSR clears it.

No PBO/DSR is run in this session because **nothing looks like a win** — the gates exist to defend *promotions*, and E13.3 produces a *demotion* + confirmations of unchanged/null. Running them on a null result would be theater.

---

## 7. What clean data changed (the one-line answer the story asked for)

> **It removed a fake signal; it revealed none.** The de-leak's only effect on the sub-model ensemble is to demote bullpen — the ensemble's strongest, most heavily-weighted Layer-3 signal — from leak-inflated #1 to (expected) below-floor. The two genuinely-carrying signals (run_env, offense) were always bullpen-clean and are unchanged. The market-aware meta-model is de-leak-invariant. **The sub-model edge search is tapped out; closing it.**
