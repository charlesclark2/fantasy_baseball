# E1.11 Phase 3 — deflation-honest lift re-test (PRE-REGISTRATION)

**Locked before any run.** Phase 1 fixed feature CORRECTNESS (F1 start-indexed starter form; F2 umpire/odds
ext-DDL restoration; Defect-3 odds-bridge freeze). Phase 2 added the traded-player enrichment. Phase 3 answers
the only question those phases deferred: **on the corrected + enriched substrate, does any of the new signal buy a
*trustworthy* incremental lift over the deployed champion contracts** — under purged/embargoed CV with the
§0.5 deflation gate (PBO<0.2 / DSR≥0.95)? A clean null is a first-class deliverable; the point of pre-registering is
that the null (or the edge) is honest because the candidate set, gate, and trial count were fixed in advance.

## Instrument
`betting_ml/scripts/incremental_lift_eval.py` (the E13.4 harness), **suite mode** (`--config-json`): all named
configs are scored against the ONE shared base **in a single run per target**, so PBO ranks the whole set
{base, c1…cN} and DSR deflates by the full config count (N=5), not 1. Running the groups as separate invocations
would deflate by 1 each and hide the multiple-testing burden — the exact §0.5 violation this mode exists to prevent.

- Base = the deployed champion contract for the target (reconstructed by the harness).
- Recipe held FIXED across all configs (only the feature set changes) — isolates feature value from HPO.
- Purged walk-forward CV, embargo=3d, min_year=2021 (the trustable dense window per the audit §4).
- Cold-start stratified: lift is read pooled AND on the non-cold-start subset (E13.7) — an imputed rookie row can
  neither manufacture nor dilute the signal.

## Coverage gate on candidate columns (why the suite is narrower than the 22 surfaced cols)
The harness's degenerate-guard INVALIDATES (does not "null") any candidate that is non-null on <50% of eval games —
a whole-population lift on a mostly-imputed column is ill-posed. These Phase-2 columns are **conditional** (defined
only for the small recently-acquired cohort) and are therefore **EXCLUDED from the population suite**, by design:

| Excluded (conditional, <50% coverage) | Why |
|---|---|
| `*_starter_days_on_team` | NULL unless a team-change txn ≤400d exists |
| `*_starter_sp_{k,bb}_pct_l3_same_team`, `*_sp_xwoba_against_l3_same_team` | NULL until a post-acquisition start exists (honest) |
| `*_lineup_min_days_on_team`, `*_lineup_avg_days_on_team_recent` | NULL unless ≥1 slot recently acquired |
| `*_lineup_pct_recently_acquired` | exact collinear with `_count` (=count/9) — redundant, use count |

Their value is **conditional on the flag firing**, not population-wide. If the flags (below) show lift, the
same-team CORRECTED form is the natural follow-up in a *within-cohort* eval (the recently-acquired stratum) — a
separate, smaller study, not this one. Recorded here so their omission is a documented decision, not an oversight.

## Pre-registered candidate configs (N=5 per target; full-coverage only)
Files: `phase3_configs/champion_suite.json` (home_/away_ pairs — home_win/total_runs/run_diff),
`phase3_configs/perside_suite.json` (opp_ faced-starter / off_ own-lineup — perside_runs).

| Config | Columns (champion / per-side) | Hypothesis |
|---|---|---|
| **f1_startform** | `sp_k_pct_l3`, `sp_bb_pct_l3`, `sp_xwoba_against_l3` | The gap-immune true last-3-start form beats the stale calendar `*_7d/_30d` block the champion currently trusts (F1 miscalc). |
| **f1_staleness** | `form_stale`, `long_layoff`, `form_source_age_days` | Exposing the calendar block's staleness lets the tree down-weight/gate it where it's stale (~9.4% of starter-rows). |
| **traded_pitcher** | `is_recently_acquired`, `form_spans_team_change`, `starts_since_acquired` | Recently-acquired starters carry blended old+new-team form; the flag lets the model distrust it (mispricing hypothesis). |
| **traded_lineup** | `lineup_recently_acquired_count` (per-side: `off_`) | A lineup with recently-acquired bats has blended rolling wOBA → its offence is harder to price; the count gates that. |
| **all_enriched** | union of the four above | The headline: does the FULL corrected+enriched block move the number vs the deployed contract? |

## Targets & run order (§6: per-side run-MEANS first, champions second)
1. `perside_runs` (CRPS) — E2.1 per-side NegBin marginal, the priority integration surface.
2. `home_win` (logloss).
3. `total_runs` (MAE).
4. `run_diff` (MAE).

Each is ONE invocation running the full 5-config suite (per the retrain-per-target discipline). If per-side AND
home_win both null on all five configs, total_runs/run_diff are optional confirmations (the prior-cycle pattern).

## GATE (pre-registered; a config SHIPS only if ALL hold, else record the null)
`incremental lift > 0 (pooled AND non-cold-start)` **AND** `PBO < 0.2` **AND** `DSR ≥ 0.95` **AND** not degenerate.
Deflation is over N=5 configs per target (DSR n_trials=5; PBO over 6 configs). A degenerate/low-coverage read is
INVALID, not a null — re-check the build, do not bank it.

## Operator run commands (multi-minute each — HAND OFF; writes only to `ablation_results/`)
```
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \
  --config-json quant_sports_intel_models/baseball/edge_program/phase3_configs/perside_suite.json \
  --run-name e1_11_phase3
uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \
  --config-json quant_sports_intel_models/baseball/edge_program/phase3_configs/champion_suite.json \
  --run-name e1_11_phase3
uv run python betting_ml/scripts/incremental_lift_eval.py --target total_runs \
  --config-json quant_sports_intel_models/baseball/edge_program/phase3_configs/champion_suite.json \
  --run-name e1_11_phase3
uv run python betting_ml/scripts/incremental_lift_eval.py --target run_diff \
  --config-json quant_sports_intel_models/baseball/edge_program/phase3_configs/champion_suite.json \
  --run-name e1_11_phase3
```
Outputs → `ablation_results/e1_11_phase3_<target>_lift.json`. After the runs return, the verdict (ship-or-null,
per config) gets recorded back into the roadmap + a Phase-3 results note; a SHIP additionally requires a champion
retrain that consumes the winning columns (promotion runbook) before it touches serving.
