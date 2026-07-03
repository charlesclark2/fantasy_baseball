# E1.11 Phase 3 — deflation-honest lift re-test: RESULTS (CLEAN NULL)

**Run 2026-07-03 (Opus) on the corrected + enriched substrate** (Phase 1 correctness fixes + Phase 2 traded
enrichment, both prod-verified; bp_eb 6/30–7/2 backfilled + umpire block recovered before the run). Instrument =
`incremental_lift_eval.py` suite-mode (E13.4 harness), pre-registered per `E1_11_phase3_preregistration.md`.
Outputs: `ablation_results/e1_11_phase3_{perside_runs,home_win}_lift.json`.

## Verdict: CLEAN NULL — 0 of 5 configs ship, on BOTH priority surfaces.

Purged walk-forward CV (embargo 3d, folds 2024/2025/2026), min_year=2021, N=5 configs deflated together
(PBO over 6, DSR n_trials=5). Every config on every target: `PBO<0.2=False AND DSR≥0.95=False` ⇒ NO-SHIP.
No candidate cleared the gate; not a single degenerate/invalid read (all coverage 98.6–100%), so these are
**real nulls, not measurement failures** — exactly the honest outcome pre-registration exists to license.

### perside_runs (CRPS, n_eval=11,660) — PBO=0.510
| config | lift (all) | lift (non-cold) | DSR | note |
|---|---|---|---|---|
| f1_startform | +0.07% | +0.08% | 0.45 | collinear 0.81–0.86 vs `opp_starter_*_14d` |
| f1_staleness | −0.03% | −0.03% | 0.04 | negative lift |
| traded_pitcher | −0.01% | −0.02% | 0.09 | orthogonal (0.07–0.10) but inert/negative |
| traded_lineup | +0.03% | +0.06% | 0.24 | cold-start negative |
| all_enriched | +0.03% | +0.07% | 0.24 | cold-start −0.19% |

### home_win (NLL, n_eval=5,043) — PBO=0.642
| config | lift (all) | lift (non-cold) | DSR | note |
|---|---|---|---|---|
| f1_startform | +0.20% | +0.11% | 0.58 | collinear 0.73–0.86 vs calendar block |
| f1_staleness | +0.20% | +0.29% | 0.58 | — |
| traded_pitcher | +0.08% | +0.12% | 0.27 | orthogonal (0.08–0.18) but inert |
| traded_lineup | +0.08% | +0.14% | 0.26 | orthogonal but inert |
| all_enriched | +0.17% | +0.15% | 0.50 | — |

## Two mechanistic reads (why the null is *informative*, not a shrug)
1. **The F1 start-form fix is ~80% redundant as a PREDICTOR.** The gap-immune last-3-start form is
   **0.73–0.86 collinear** with the champion's existing calendar block (`k_pct_30d`, `bb_pct_14d`,
   `xwoba_against_14d` / `opp_` equivalents). F1 was a genuine *correctness* bug, but the stale-calendar
   approximation already carried nearly all the same predictive signal — fixing it adds essentially no
   incremental discrimination (lift ≤0.2%, DSR ≤0.58, PBO 0.51–0.64 = selection noise). **Correctness ≠ new
   information.** The fix is still worth keeping (it's *right*, and it removes the Teheran-class 189-day-stale
   artifact), but it does not move the number.
2. **The traded-enrichment flags are new information but INERT.** `traded_pitcher`/`traded_lineup` are
   genuinely orthogonal to the champion (max|corr| 0.07–0.18 — the model didn't have this), yet carry
   zero-to-negative lift (DSR 0.04–0.27). The trade-mispricing hypothesis — "recently-acquired
   starters/lineups are mispriced" — is **false** at the population level for both run-means and win-prob:
   the market and the champion already price the transition fine.

## Decision
- **`total_runs` / `run_diff` (#3, #4) SKIPPED** — per pre-registration §6, both priority surfaces nulled on
  all five configs; the MAE targets are optional confirmations that cannot change the E1.11 verdict. Not run
  (documented skip, not silent).
- **Nothing ships to serving.** No champion retrain is triggered (a retrain was gated on a config clearing the
  gate; none did). The Phase-1 correctness fixes + Phase-2 enrichment REMAIN deployed on their own merit
  (they are correct, guarded, and prod-verified) — Phase 3 only tested whether they buy *incremental
  predictive lift*, and they do not.
- **Consistent with the standing `best_alpha=0` posture:** on a now-clean, correctness-audited substrate,
  the model still shows no cashable incremental edge from these signals. This is the trustworthy version of
  the "no edge" finding the audit was gating — measured on corrected inputs, it holds.

## Follow-up left open (documented, not pursued)
- **Within-cohort study (conditional cols):** the <50%-coverage same-team form / days-on-team columns were
  excluded from this population suite by design. IF a future angle motivates it, they'd be tested in a
  *within recently-acquired stratum* eval (a separate, smaller study) — but given the traded flags are inert
  at population level, the prior on that paying off is low.
- **`home_team_sequential_bullpen_xwoba`** (sequential sub-model bullpen signal, INC-25 chain) was all-null →
  constant-imputed on 6/30 & 7/2 during the outage window; a separate backfill from bp_eb, out of scope here.
