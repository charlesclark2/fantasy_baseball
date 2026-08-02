# E2.6 — Derivative pricing + validation gates: PRE-REGISTRATION

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "explicitly a PRE-REGISTRATION, written before any arm was scored \u2014 by definition carries no verdict yet; the results (when run) land in e2_6_derivative_gates.md, which the header regex already extracts.",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->


_Markets, strategies, metrics, and pass/fail thresholds fixed BEFORE looking at any real
outcome (§0.5 discipline). The operator run (`--build-cache` → eval) fills in the numbers; this
document is the commitment they are scored against, so a null cannot be retrofitted into a survivor._

## Thesis (angle 3 — the model-vs-market gate)

E13.13 asked whether the derivative market is efficient **vs its own de-vigged price** (angles 1+2,
NO model → CLEAN NULL). **E2.6 asks the different, harder question:** does our **market-blind** model
— the E2.5 `totals_generative_v1` per-side NegBin marginals (LightGBM-Poisson μ + E2.3 held-out
dispersion `r_home` 4.06 / `r_away` 3.40), convolved independently (E2.2 ρ≈0) into the honest
game-total distribution — **disagree with the derivative's CLOSING line in a way a beat-the-close
backtest rewards?**

`best_alpha = 0`. Beating the CLOSE is the strictest cashability test (the close is the sharpest
number the book posts). With MLB main-market efficiency (E13.8), the E5.4 prop-edge null and the
E13.13 derivative-efficiency null already on record, **a CLEAN NULL (no derivative beats its own
close after deflation) is the LIKELY and fully-valid outcome.** We report the deflated number
honestly; we never manufacture a survivor.

## Markets gated (fixed before outcomes)

| market | model price source | close source | realized |
|---|---|---|---|
| `team_totals` | per-side marginal P(that team's runs > line) | `mart_derivative_closes` (E2.0) | that team's final runs (`mart_game_results`) |
| `alternate_totals` | convolved total P(game total > alt line) | `mart_derivative_closes` (E2.0) | game total runs |
| `totals` (main, anchor) | convolved total P(game total > line) | (distributional leg / E2.3) | game total runs |

**F5 (`totals_1st_5_innings` / `h2h_1st_5_innings`) and NRFI are HELD OUT of this gate.** The
historical F5 closes exist in S3 (E5.1 props store, 2023–2026), but our E2.5 **served** model only
produces **full-game** per-side μ — the E2.4 `f5_generative_v1` distribution is built but **not yet
registered as a served per-side-μ signal** (that is a small E2.5-follow-on). The harness is
F5-ready; F5 is gated once its μ is served. This is the model side being unready, not the data side.

## Model→market→outcome join (leakage-safe)

- Model μ read from the E2.5 signal store filtered **`where is_oos`** (a game is OOS only when BOTH
  sides were scored by a model that did NOT train on that season — walk-forward, per
  `project_layer3_signal_leakage`). Never score a season the model saw in-sample.
- Market data enters **only here**, at the eval/CLV layer. The model matrix is market-blind
  (architecture Principle 3) — the closes are never model features.

## The bet + the metric (fixed)

- **Selection (pure, outcome-blind):** bet OVER when `model_p_over − fair_close_p ≥ τ`, UNDER when
  `fair_close_p − model_p_over ≥ τ`, where `fair_close_p` is the de-vigged (additive) closing prob.
- **Settlement:** realized PnL **at the close's American price** (net of the derivative's own vig) —
  a strict beat-the-close test. (History has only closes; true bet-time-vs-close CLV runs on the
  E2.0b forward stream with the SAME harness once accumulated.)
- **⚠️ GAME-LEVEL scoring (mandatory, the E13.13 lesson):** collapse correlated book-quotes to ONE
  return per `game_pk` BEFORE any significance / PBO / DSR. 15 books on one game are one correlated
  bet, not 15 — counting quotes manufactures a fake edge out of the multiple-comparison surface.

## Pre-registered config grid (deterministic; every cell counts toward deflation)

`market × book_group{all,pinnacle,soft,majors,<each book>} × line_bucket{all,low≤7.5,mid 8–9.5,
high≥10} × τ{0.02,0.03,0.04,0.06,0.08}`. Selectable = ≥ 50 unique games; FRAGILE < 250 games.

## Pass/fail thresholds (a market is a CANDIDATE only if ALL clear)

1. Game-level **ROI > 0 net of the derivative's own vig**.
2. **Season-sign-consistent** (every season's game-level ROI same sign).
3. Survives **BH-FDR** (q = 0.10) across the whole config grid's ROI tests (multiple-comparison
   control).
4. **PBO < 0.2** (CSCV over year-month slices × selectable configs — E1.4). _Reading discipline:
   a HIGH PBO over a TIED field of correlated winners is the NULL, not evidence against a specific
   edge (§0.5); the deflation refuses to certify "which tied config wins" = noise._
5. **DSR ≥ 0.95** on the in-sample-best config, deflated by the selectable-config count (E1.4).

## Distributional-accuracy leg (secondary, over the E2.3 surface)

Convolved-total `crps_ensemble` vs the `total_runs` champion `crps_normal`, via `evaluate_promotion`
(a `PredictiveOutput.from_samples` adapter — no gate changes). Runs when the operator supplies
champion (μ, σ) predictions; PROMOTE ⇒ the convolved distribution is at least as sharp/calibrated as
the incumbent total model. This is a product-quality check, not the edge gate.

## What a clean null means (pre-committed reading)

If no market clears all five legs: with E5.4 + E13.13, this **closes the derivative-edge hope on the
historical closes.** The value of E2 is then **product-quality calibrated distributions +
transparency** (the E2.7 UX), not a cashable derivative edge — and that is a legitimate, honestly
framed result, not a failure to be re-run until green.

_Harness: `betting_ml/utils/derivative_model_gate.py` + `betting_ml/scripts/derivative_eval/
eval_derivative_model_gate.py` + `betting_ml/tests/test_derivative_model_gate.py`. Smoke proof
(synthetic, banner-marked): `e2_6_derivative_gates_smoke.md` (efficient books → clean null) and
`e2_6_derivative_gates_smoke_mispriced.md` (a shaded corner lights up the detection legs while PBO
tie-conservatism correctly holds the candidate)._
