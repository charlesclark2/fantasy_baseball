# MH2.8 — ⚠️ POST-HOC DIAGNOSIS of the two clauses that refused the run

> ⛔ **This document cannot ship anything and cannot rescue a pre-registered clause.** Both clauses below FAILED as written and stay failed. What follows is the MECHANISM, so a successor can be pre-registered against the real cause rather than a guess (NF1.8: state the null's mechanism, in the unit that grows).

## 1. Why the negative control failed

The pre-registered control reported a clean rate of **0.650** against a bar of **0.9** — on data where the incumbent Normal is TRUE, the selection picked a skew arm about a third of the time. Read literally that says the harness invents skew, which would make the whole study untrustworthy.

⭐ **The control and the ship rule test DIFFERENT bars.** `_select_on_primaries` is a bare ARGMIN with no threshold; the SHIP RULE requires a margin of ≥ `0.012`. `skewnorm_recal` carries one more fitted parameter than its foil, so on clean data it can chase PIT noise and win a TIE — without ever winning by an amount the ship rule would act on. This measures both.

| population | bare ARGMIN picks the skew arm | margin mean | margin sd | margin max | **clears the ship rule's bar** |
|---|---:|---:|---:|---:|---:|
| served-sized (n_eval 325, 150 reps) | 0.220 | -0.00474 | 0.00987 | +0.02154 | **0.047** |
| CV-sized (what the control actually ran at) (n_eval 14,813, 60 reps) | 0.333 | -0.00006 | 0.00122 | +0.00243 | **0.000** |

At the size the control actually ran at, the bare argmin picks the skew arm **0.333** of the time — reproducing the recorded 0.650 clean rate — while **0.000** of replicates produce a shippable margin. The largest clean-data margin in 60 replicates is **+0.00243**, against a bar of 0.012 and a REAL-DATA margin of **+0.0213** — about **17 clean-data SDs out**.

⇒ the control's failure is a property of its THRESHOLD-FREE TIE-BREAK, not evidence that the harness manufactures a shippable effect. ⛔ **That does not un-fail it.** The clause was pre-registered as written and it refused; re-reading a failed clause against a bar chosen after seeing it fail is exactly the E2.1-r inversion. What it licenses is a SUCCESSOR whose negative control MIRRORS THE SHIP RULE'S THRESHOLD — which is the control that should have been written, and is a defect in this study's design.

## 2. What drives DSR's `V`

The run recorded `DSR_UNREACHABLE`: the winner's per-fold Sharpe **0.460** against `SR0` **1.962**, built on `var_trials_sr` = **1.8078**. `SR0 = √V·z(N)`, so a large `V` raises the bar for arithmetic reasons rather than evidential ones (MH2.5 / NF-W6b-C).

| arm | skill mean (+ = better than incumbent) | skill sd | per-fold Sharpe | in `V`? |
|---|---:|---:|---:|---|
| `normal_recal` | -0.00573 | 0.00567 | -1.011 | ✅ |
| `climo` | +0.01132 | 0.01227 | +0.923 | ⛔ degenerate — out of V |
| `overskew` | -0.00515 | 0.02126 | -0.242 | ⛔ degenerate — out of V |
| `ngb_lognormal` | -0.00301 | 0.01170 | -0.258 | ✅ |
| `ngb_gamma` | +0.01239 | 0.00591 | +2.095 | ✅ |
| `lgbm_quantile` | -0.01108 | 0.00893 | -1.241 | ✅ |
| `skewnorm_recal` | +0.00882 | 0.01916 | +0.460 | ✅ |

Leave-one-out on the `V` pool ['normal_recal', 'ngb_lognormal', 'ngb_gamma', 'lgbm_quantile', 'skewnorm_recal'] — ⛔ **a DIAGNOSTIC, NOT a trim** (MH2.2: you PRE-REGISTER a family, you do not DISCOVER one; no figure here may be quoted as a verdict):

| arm removed | resulting `V` |
|---|---:|
| `ngb_gamma` | 0.5971 |
| `lgbm_quantile` | 1.7590 |
| `normal_recal` | 1.9766 |
| `skewnorm_recal` | 2.3256 |
| `ngb_lognormal` | 2.3808 |

⭐ **`ngb_gamma` alone accounts for most of it** — removing it takes `V` from 1.808 to 0.597. The declared field mixes SHAPE-RECALIBRATION arms, which share the incumbent's mean and therefore move together fold to fold, with LEARNED-FAMILY arms that fit their own mean. That is a HETEROGENEOUS field by construction, and it is the mechanism MH2.5 and NF-W6b-C both name.

⚠️ **And the sharpest reading is an irony, not a rescue.** `ngb_gamma`'s own per-fold Sharpe is **+2.095** — ABOVE the `SR0` of 1.962, i.e. it is the one arm in the field that WOULD clear the deflation gate. It fails clause 6 instead: its CRPS is +0.0698 against a tolerance of 0.020, three and a half times over. **It bought flatness with sharpness, which is precisely what the constraint exists to catch.** So the arm the deflation gate would pass is the one the sharpness constraint rejects, and the arm that clears every substantive clause is the one the deflation gate rejects. Neither result is a defect in the other gate.

⛔ **`field_remedy_admissible` was `None`** — not even a 2-arm field clears. That figure holds `V` FIXED, so it cannot see the `V` reduction a coherently-declared family would produce; it says field SIZE is no lever, not that field COMPOSITION is none. Acting on that distinction requires a FRESH pre-registration of a coherent family, decided on mechanistic grounds BEFORE any scoring — ⛔ never a re-cut of this scored field.

