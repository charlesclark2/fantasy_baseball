# NF-W6d Phase C — calibrated DEFAULT distributions for the no-winner cells

**Generated:** 2026-08-15T19:43:18+00:00 · **folds:** 2 (2025H1…2025H2) · **rows:** 84553 · **cells:** 4

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**. A default is chosen by pre-registered ORDER + calibration gates (one-sided coverage floor ∧ randomized-PIT max-decile-deviation ≤ 0.03); ⛔ NOT a bake-off winner, NOT selected on CRPS. The nihilist is scored against every default (NF-D14). A distribution here is a calibrated RANGE, never an edge or win-rate claim.

## Verdict: **DEFAULTS 4 cells → {'count_negbin': 4}; 0 uncalibrated (flagged)**

| cell | kind | order | chosen | cov80 | PIT max-dev | calibrated | nihilist loses | CRPS | pred P(0) / real P(0) | warning |
|---|---|---|---|---|---|---|---|---|---|---|
| QB|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9745 | 0.02566 | True | True | 0.03345 | 0.9742 / 0.9687 | — |
| RB|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.993 | 0.00728 | True | True | 0.00741 | 0.9939 / 0.9925 | — |
| TE|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9948 | 0.01128 | True | True | 0.00515 | 0.9965 / 0.9948 | — |
| WR|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9913 | 0.01049 | True | True | 0.00865 | 0.9946 / 0.9913 | — |

## Per-cell reads (every form in the order, so the choice is auditable)

### QB|two_pt

- `count_negbin`: cov80 0.9745 (floor ok True, SE 0.0108, structural 0.9969) · PIT max-dev 0.02566 (flat ok True) deciles [0.09913, 0.09548, 0.10714, 0.07434, 0.10058, 0.09402, 0.0984, 0.11516, 0.10496, 0.11079] · CRPS 0.03345 vs nihilist 0.03438 · pred P(0) 0.9742 vs real 0.9687 · n 1372
- `climatology`: cov80 0.9687 (floor ok True, SE 0.0108, structural 0.9969) · PIT max-dev 0.01589 (flat ok True) deciles [0.09257, 0.09548, 0.11443, 0.10131, 0.09767, 0.09257, 0.09038, 0.09475, 0.10496, 0.11589] · CRPS 0.03354 vs nihilist 0.03438 · pred P(0) 0.9698 vs real 0.9687 · n 1372

### RB|two_pt

- `count_negbin`: cov80 0.993 (floor ok True, SE 0.0086, structural 0.9993) · PIT max-dev 0.00728 (flat ok True) deciles [0.10308, 0.09562, 0.10401, 0.10354, 0.09981, 0.10728, 0.09468, 0.09841, 0.09841, 0.09515] · CRPS 0.00741 vs nihilist 0.00744 · pred P(0) 0.9939 vs real 0.9925 · n 2144
- `climatology`: cov80 0.9925 (floor ok True, SE 0.0086, structural 0.9993) · PIT max-dev 0.018 (flat ok True) deciles [0.09655, 0.11147, 0.09422, 0.09375, 0.09935, 0.08582, 0.10774, 0.118, 0.09841, 0.09468] · CRPS 0.00741 vs nihilist 0.00744 · pred P(0) 0.995 vs real 0.9925 · n 2144

### TE|two_pt

- `count_negbin`: cov80 0.9948 (floor ok True, SE 0.0091, structural 0.9995) · PIT max-dev 0.01128 (flat ok True) deciles [0.09325, 0.10046, 0.10252, 0.09531, 0.09943, 0.1051, 0.09325, 0.11128, 0.10459, 0.0948] · CRPS 0.00515 vs nihilist 0.00516 · pred P(0) 0.9965 vs real 0.9948 · n 1941
- `climatology`: cov80 0.9948 (floor ok True, SE 0.0091, structural 0.9995) · PIT max-dev 0.01448 (flat ok True) deciles [0.10613, 0.10046, 0.0984, 0.09686, 0.10149, 0.08552, 0.10149, 0.10098, 0.11128, 0.09737] · CRPS 0.00516 vs nihilist 0.00516 · pred P(0) 0.995 vs real 0.9948 · n 1941

### WR|two_pt

- `count_negbin`: cov80 0.9913 (floor ok True, SE 0.007, structural 0.9991) · PIT max-dev 0.01049 (flat ok True) deciles [0.10183, 0.10214, 0.10121, 0.09873, 0.11049, 0.09316, 0.09347, 0.09687, 0.10368, 0.09842] · CRPS 0.00865 vs nihilist 0.00867 · pred P(0) 0.9946 vs real 0.9913 · n 3231
- `climatology`: cov80 0.9913 (floor ok True, SE 0.007, structural 0.9991) · PIT max-dev 0.01024 (flat ok True) deciles [0.09811, 0.09997, 0.09935, 0.10399, 0.10647, 0.08976, 0.09687, 0.10214, 0.10368, 0.09966] · CRPS 0.00863 vs nihilist 0.00867 · pred P(0) 0.995 vs real 0.9913 · n 3231

## Pre-registration

- order: {'modeled': ['count_negbin', 'climatology'], 'minor': ['climatology']}; PIT max-decile-dev ≤ 0.03; coverage floor 0.8 (one-sided, 3.0 SE); cells = substrate − served (4).

_Runtime: 11.3s · seed 20260817 · matrix key 26c34fbe778c9d87_