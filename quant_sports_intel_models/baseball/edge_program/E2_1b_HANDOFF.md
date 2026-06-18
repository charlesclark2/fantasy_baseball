# Story E2.1b — Bullpen model deepening (`bullpen_v3`) — Hand-off to PM session

**Date:** 2026-06-18 · **Status:** ✅ COMPLETE (gate FAIL by design — the failure is the finding) · **Author:** model session (Edge Program E2.1b)

---

## 1. TL;DR (read this first)

E2.1b set out to *deepen* the bullpen input the E1.3 audit ranked **#1/#2 on every target** (`home/away_bp_eb_xwoba`) and prove a measured lift vs the current feature on per-side-runs NLL under purged CV.

**The measured answer is: no lift — because the "current input" was never pre-game skill. It is a within-game data leak.** The dominant feature `bp_eb_xwoba` is built by weighting each reliever's EB by `outs_in_game` (the outs they recorded *in the very game being predicted*), over the roster of arms that *actually pitched that game*. Both the roster and the weights read the eval-game outcome. Purged CV does not catch this (it guards temporal/cross-fold leakage, not a feature that peeks at its own row).

This was confirmed **three independent ways**, the last being the audit's own tool turned on the de-leaked feature: its importance collapses from **#1/#2 to statistical noise (0% retained).**

**So the E2.1b deliverable is not "v3 beats static." It is: (a) the discovery + proof that the program's #1 feature leaks, (b) a leakage-safe drop-in replacement, and (c) a recommended follow-up to de-leak the *production* feature that feeds the live champions.** That is a more valuable result than a tuned lift, and it is exactly what E1's anti-overfitting discipline exists to surface.

---

## 2. The finding, proven three ways

### Proof 1 — the leaky construction (source-verified)
`dbt/models/eb_posteriors/eb_bullpen_team_posteriors.sql:33`:
```sql
case when t.total_outs > 0 then b.outs_in_game else 1 end as w   -- weight = outs IN THE EVAL GAME
```
The roster (`base` = `eb_bullpen_posteriors`) is the set of relievers who appeared in game G; the weight is the outs each recorded in game G. The model header literally says *"Outs-in-game weighted average."* This feeds `feature_pregame_team_features.bp_eb_xwoba` → `feature_pregame_game_features.home/away_bp_eb_xwoba`. It **cannot be computed before first pitch** (you don't know who pitches or for how long), so its backfilled values encode game-G usage.

### Proof 2 — the NLL leak signature (purged-CV A/B)
Per-side NegBin NLL, E2.1 surface held fixed, only the bullpen channel swapped (2024/2025 eval folds, 12,711 games):

| variant | per-side NegBin NLL | vs leaky |
|---|---|---|
| **LEAKY-STATIC** (incumbent) | **2.4303** | — |
| DE-LEAKED equal-weight (leakage-safe control) | 2.4582 | +0.0279 |
| V3-LEAKFIX (leakage-safe + leverage×availability) | 2.4571 | +0.0268 |
| V3-PENSTATE (+ platoon + availability features) | 2.4574 | +0.0271 |

The two **leakage-safe** variants land within **0.001** of each other and both lose to leaky-static by an **identical ~0.027**. That is only possible if the incumbent's entire edge is the peek — there is no pre-game-knowable signal in that 0.027. (The harness prints an automatic `LEAK SIGNATURE` verdict.)

### Proof 3 — the MDA collapse (the audit's own tool, de-leaked)
E1.3 clustered MDA on `total_runs`, static vs de-leaked (`--bullpen-version v3`):

| feature | static rank / importance | de-leaked rank / importance | retained |
|---|---|---|---|
| `home_bp_eb_xwoba` | **#1** / +0.0781 | **#40** / +0.0002 (CI crosses 0 → **noise**) | **0%** |
| `away_bp_eb_xwoba` | **#2** / +0.0655 | **#39** / +0.0003 (**noise**) | **0%** |
| `home_bp_eb_uncertainty` | #4 / +0.0263 | #5 / +0.0072 | 28% |
| `bp_eb_coverage_pct` (h/a) | #5–6 / ~+0.025 | **#1–2** / ~+0.054 | rises |

The xwOBA **point estimate** was ~100% leak. The only residual *pre-game* bullpen signal is in **`coverage_pct`** (data depth — which rises once the leaky xwOBA stops dominating) and **`uncertainty`** (~28% retained). The "value" of the bullpen was *how much data backed the estimate*, not the estimate itself.

> Run for `total_runs` (decisive). **Recommended for completeness:** the same `--bullpen-version v3` MDA for `home_win` and `run_diff` (each independent/parallelizable). Expected to show the same collapse — the feature and the leak mechanism are target-agnostic — but they have not been run yet.

---

## 3. Implications (why this matters beyond E2)

1. **E1.3's headline is leak-inflated.** "Bullpen EB quality dominates every target" was the #1 signal-investment finding of the whole Edge Program. The dominant channel (`bp_eb_xwoba`) carried ~0 pre-game skill; its rank was the peek. The *coverage/uncertainty* channels are the real (modest) bullpen signal.

2. **Named mechanism for the offline→live skill collapse.** `home/away_bp_eb_xwoba` is in the **training matrix of the live home_win / run_diff / total_runs champions** (`feature_pregame_game_features`). It peeks offline and is imputed/null at serve time → this is a concrete, named contributor to the [prod audit](project_prod_model_audit_jun2026) finding (offline corr 0.42 → live 0.001) previously attributed broadly to "serving skew." Same root, now with a mechanism.

3. **The leverage/availability sophistication is neutral.** v3 (leverage×availability weighting) beats plain equal-weight by 0.001 — noise. Per "validated-better, not most elaborate," the **simplest leakage-safe aggregate is the right replacement.** There is **no case for Experiment B** (per-reliever × handedness EB) — zero measured headroom; pursuing it would be the multiple-testing trap.

---

## 4. The E2.1b verdict & what it means downstream

- **Gate:** FAIL on the AC as literally written ("beat the static team EB on per-side NLL"). This is the **correct** outcome — the AC unknowingly compared a clean feature to a contaminated incumbent.
- **`bullpen_v3` is NOT promoted** (`promotion_status: pending` in the registry; `--write` of the team table was deliberately **not** run — there is no lift to promote on).
- **For E2.1 (per-side totals):** when E2.1 next consumes a bullpen channel, it should use a **leakage-safe** aggregate (equal-weight or v3 — equivalent), **not** because it improves NLL but because the leaky feature is not computable live and inflates offline metrics. Do not wire the leaky `bp_eb_xwoba` into a model intended to serve.
- **Do not** chase a v3 variant that "beats" leaky-static. That would be optimizing toward the leak.

---

## 5. ⭐ Recommended follow-up card (the real actionable item)

**De-leak the production bullpen EB feature.** Scope:

- **Fix:** in `eb_bullpen_team_posteriors.sql`, replace the `outs_in_game` weight (and the appeared-in-game roster) with a **leakage-safe** aggregate — the simplest being equal-weight over a pre-game pool (the `weight_mode='equal'` logic in `aggregate_team_v3`), or the v3 expected-leverage weighting (equivalent on NLL). The per-reliever EBs themselves are already as-of-safe; only the **weighting + roster** leak.
- **Blast radius:** this column feeds the **live home_win / run_diff / total_runs base champions'** training matrices. Re-training/re-evaluating those on the de-leaked matrix is part of the card.
- **⚠️ Validation gotcha (critical):** the de-leaked feature **will look worse on offline NLL/Brier/importance** — that is *expected and correct* (you removed a peek). It must **not** be read as a regression. The honest validation is **live/forward performance** (does serve-time skill rise toward the offline number once the offline number is no longer leak-inflated?) and the serving-parity harness — **not** offline metrics, which reward the leak. This is the same trap that makes the current champions look good offline and fail live.
- **Tie-ins:** [project_epic30_3_status](serving skew), [project_prod_model_audit_jun2026], [project_search_baseline_misleading] (champion-delta gating). This is arguably a Tier-0 correctness item, not an "edge" item.

**Open decision for PM:** whether to (a) spin this as a standalone production-correctness card now (recommended — it touches live champions), or (b) fold it into the existing serving-skew / Epic 30.3 thread. Also: run the `home_win` + `run_diff` MDA re-checks to document the collapse on all three targets before the card.

---

## 6. Artifacts (what shipped this session)

**New code**
- `betting_ml/scripts/eb_priors/compute_bullpen_v3.py` — leakage-safe team bullpen posterior. Heavy Snowflake query ONCE → per-reliever parquet cache (`betting_ml/models/sub_models/bullpen_v3/per_reliever_<season>.parquet`, built for 2021–2026); pure-Python `aggregate_team_v3(cache, k, weight_mode)` (`weight_mode='expected'` = v3, `'equal'` = de-leaked control); CONTRACT-GUARD on outputs; writes `eb_bullpen_team_posteriors_v3` via MERGE (only on `--write`, **not run**). Slate from `mart_game_spine` (handles today's scheduled games for a daily op).
- `betting_ml/scripts/totals_generative/eval_bullpen_v3_cv.py` — the gate: leaky-static vs de-leaked-equal vs V3-LEAKFIX(k-sweep) vs V3-PENSTATE on per-side NegBin NLL (purged CV) + automatic leak-signature detector.
- `betting_ml/tests/test_bullpen_v3.py` — 16 passing (EB-`k` math/parity with the static `_normal_posterior`, availability down-weight, leverage weighting, equal-weight control, platoon carry, market-blind guard).

**Modified**
- `betting_ml/scripts/clustered_feature_importance.py` — added `--bullpen-version {static,v3}` + `--shrinkage-k`; default `static` unchanged; `v3` swaps the de-leaked column and writes `*_bullpen_v3` outputs.
- `betting_ml/sub_model_registry.yaml` — registered `bullpen_v3` (`promotion_status: pending`; lineage note that it is an EB-team-posterior upgrade, **not** a successor to the bullpen_v1/v2 runs/quality models).
- `quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md` (§4 E2.1b) + `story_prompts.md` — updated to the honest verdict.

**Results**
- `quant_sports_intel_models/baseball/edge_program/ablation_results/e2_1b_bullpen_v3_cv.json` — gate output (leak signature).
- `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_total_runs_bullpen_v3.json` (+ `.md` report) — the de-leaked MDA.

**Not done (by design / pending)**
- `compute_bullpen_v3.py --write` (no lift to materialise; the value is the finding + the de-leak follow-up).
- `home_win` / `run_diff` MDA re-checks (recommended for completeness).
- Experiment B (per-reliever × handedness EB) — explicitly **not** pursued (no headroom).

**Repo note:** no git commits/pushes (per project convention — operator handles git).

---

## 7. Caveats (stated honestly)

- **CV had 2 eval folds** (2024, 2025; purged walk-forward with `min_train_seasons=3` from 2021 data, 2026 excluded as partial). Few folds — but the leak signature (equal ≈ v3 to 0.001) and the MDA collapse (0% retention) are decisive regardless of fold count.
- The MDA collapse is shown for **total_runs only** so far; home_win/run_diff expected-same but unconfirmed.
- The leakage-safe replacement is a *correctness* improvement, not an edge — it will (correctly) lower offline metrics. Do not gate it on offline NLL.
