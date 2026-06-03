# Layer 3 H2H Dataset Audit (Story 11.1)

- Source: `load_layer3_features_for_training(target='home_win')` / `build_h2h_dataset`, start_date=2021-01-01, completeness ≥ 0.4.
- Games (completeness-filtered): **11661**.
- Leakage guards: target columns **0**, raw-feature violations **0** (validated — raises otherwise); `bovada_devig_home_prob` asserted absent from `X`.

## Target — `home_win`

| metric | value |
|---|---|
| n | 11661 |
| base rate | **0.5315** |
| expected range | [0.52, 0.56] |
| in expected range | **True** |

_Home win rate within the expected MLB home-field-advantage band._

## Signal completeness (identical game set to the totals dataset)

- mean **0.9922**, median 1.0, p25 1.0, min 0.6 (floor 0.4). Same target-agnostic matrix rows as `build_totals_dataset`.

## Eval-only de-vigged Bovada P(home win) coverage

- Games with a market prob: **8656/11661** (74.2%).
- Bovada-specific (closing h2h, additive de-vig): **6990**.
- Consensus fallback (`close_vf_home`): **1666**.

_The de-vigged home probability is evaluation-only (11.2/11.5/11.7) and never enters the training matrix._

