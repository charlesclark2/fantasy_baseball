# MH2.2 — the trajectory family as its OWN pre-registered field (batter side)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": "leave-one-MLB-debut-cohort-out (n_cohorts)",
 "gates": {
  "FDR_ALPHA": 0.1,
  "MIN_DSR": 0.95,
  "fold_consistency_wins_required": 8
 },
 "n_arms": 3,
 "n_folds": 11,
 "per_metric": [
  {
   "dsr": 0.2849667461052918,
   "metric": "woba",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "GENUINE_ABSENCE",
   "pbo": 0.9571428571428572,
   "verdict": "DROP"
  },
  {
   "dsr": 0.7481110654767215,
   "metric": "k_pct",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "POWER_LIMITED",
   "pbo": 0.35714285714285715,
   "verdict": "DROP"
  },
  {
   "dsr": 0.8492718634120231,
   "metric": "bb_pct",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "POWER_LIMITED",
   "pbo": 0.0,
   "verdict": "DROP"
  },
  {
   "dsr": 0.7587141084157905,
   "metric": "iso",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "POWER_LIMITED",
   "pbo": 0.0,
   "verdict": "DROP"
  }
 ],
 "primary_contrast": "the DECLARED 3-arm trajectory family vs the shipped E7.12-S1 foil",
 "reason": null,
 "schema": 1,
 "source_artifact": "mh2_2_trajectory_family.md",
 "status": "recorded",
 "verdict": "woba=DROP, k_pct=DROP, bb_pct=DROP, iso=DROP"
}
-->


_generated 2026-08-03T21:53:37.727442+00:00 · declared field = `T1_traj_ladder`, `T2_traj_raw`, `T3_tenure` · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> Pre-registration (written before any arm was scored): `mh2_2_preregistration.md`.

> ⚠️ **A projection, not an edge claim.** Nothing here is emitted to the served board.


## 0. What this run retires

E7.15-H3 recorded the trajectory arms as clearing **DSR 0.998** over a 2-arm field. That field is **POST-HOC** — H3's own pre-registration names THREE trajectory arms and the 0.998 drops `T3_tenure`, *the arm that lost*. This run scores the family **as declared**.

⛔ **You get to pre-register a family; you do not get to discover one.**


## 1. Reproduction anchor — is this the SAME evidence as E7.15-H3?

**OK** — every shared arm reproduces E7.15-H3's recorded per-fold MAE — the two runs are the SAME evidence, so the field-definition comparison is valid.

| metric   |   n_shared_arms |   n_cells_compared |   max_abs_mae_gap_vs_h3 | status   |
|:---------|----------------:|-------------------:|------------------------:|:---------|
| woba     |               7 |                 77 |                       0 | OK       |
| k_pct    |               7 |                 77 |                       0 | OK       |
| bb_pct   |               7 |                 77 |                       0 | OK       |
| iso      |               7 |                 77 |                       0 | OK       |

## 2. Verdicts (declared 3-arm field)

| metric   | verdict   | winner   | best_arm       |   pct_lift_vs_foil | BH-FDR   |   PBO(eligible) |   DSR(declared 3-arm) | null_state      |
|:---------|:----------|:---------|:---------------|-------------------:|:---------|----------------:|----------------------:|:----------------|
| woba     | DROP      | L0_foil  | T2_traj_raw    |             -0.255 | False    |        0.957143 |                0.285  | GENUINE_ABSENCE |
| k_pct    | DROP      | L0_foil  | T1_traj_ladder |              1.183 | False    |        0.357143 |                0.7481 | POWER_LIMITED   |
| bb_pct   | DROP      | L0_foil  | T2_traj_raw    |              1.404 | True     |        0        |                0.8493 | POWER_LIMITED   |
| iso      | DROP      | L0_foil  | T1_traj_ladder |              1.418 | True     |        0        |                0.7587 | POWER_LIMITED   |

## 3. 🔒 The pre-registered bar — stated in per-fold Sharpe, not as a p-decimal

`required_sr` is `cv_power.dsr_required_sr`: the per-fold skill Sharpe an arm MUST post to reach DSR ≥ 0.95 **in this 3-arm field**. It is a property of the DESIGN and is readable before any arm is fitted.

| metric   | arm            |   n_folds |   observed_sr |   required_sr_for_dsr_gate |   sr_shortfall |   folds_needed_for_dsr |   extra_debut_cohorts_needed |   dsr_ceiling_at_this_n_obs |   var_trials_sr |
|:---------|:---------------|----------:|--------------:|---------------------------:|---------------:|-----------------------:|-----------------------------:|----------------------------:|----------------:|
| woba     | T2_traj_raw    |        11 |       -0.1574 |                     0.9534 |         1.1108 |                    nan |                          nan |                      0.9989 |        1.7e-05  |
| k_pct    | T1_traj_ladder |        11 |        0.4236 |                     1.0793 |         0.6558 |                     62 |                           51 |                      0.9998 |        0.032822 |
| bb_pct   | T2_traj_raw    |        11 |        1.0061 |                     1.2335 |         0.2274 |                     27 |                           16 |                      1      |        0.593058 |
| iso      | T1_traj_ladder |        11 |        0.9098 |                     1.4368 |         0.527  |                     56 |                           45 |                      1      |        0.523172 |

**Fold-consistency clause (MH2/H8, calibrated):** at 11 folds it requires **8/11** wins at α=0.2 (null false-fire 0.113) against the legacy `≥60%` bar's 7 wins (null false-fire 0.274). It is weakly STRICTER, so it can only ever prevent a false ADD — never manufacture one.


## 4. ⭐ What the retired post-hoc 2-arm field actually bought

Shrinking a field moves TWO things and only one is 'multiplicity': the trial COUNT `N`, and the cross-trial Sharpe DISPERSION `V` — because the arm you drop is the one far from the winner (`cv_power.decompose_field_size`). **The dispersion channel is the dominant one here**, i.e. the 0.998 was bought by deleting a LOSER's spread, not by an honest multiplicity reduction.

| metric   | dropped   |   DSR_declared_3arm |   DSR_posthoc_2arm |   if_only_N_shrank |   if_only_V_shrank |   V_declared |   V_posthoc |   V_collapse_ratio |
|:---------|:----------|--------------------:|-------------------:|-------------------:|-------------------:|-------------:|------------:|-------------------:|
| woba     | T3_tenure |              0.285  |             0.2878 |             0.2866 |             0.2869 |     1.74e-05 |  5.15e-06   |                3.4 |
| k_pct    | T3_tenure |              0.7481 |             0.8404 |             0.7935 |             0.8315 |     0.032822 |  0.0018983  |               17.3 |
| bb_pct   | T3_tenure |              0.8493 |             0.9985 |             0.9634 |             0.9985 |     0.593058 |  2.975e-05  |            19938   |
| iso      | T3_tenure |              0.7587 |             0.9812 |             0.8997 |             0.978  |     0.523172 |  0.00657763 |               79.5 |

## 5. Null classification (`cv_power.classify_null`) and the re-test trigger

| metric   | state           |   folds_have |   folds_needed |   extra_debut_cohorts |   max_field_size | retest_trigger                                                                    |
|:---------|:----------------|-------------:|---------------:|----------------------:|-----------------:|:----------------------------------------------------------------------------------|
| woba     | GENUINE_ABSENCE |           11 |            nan |                   nan |              nan |                                                                                   |
| k_pct    | POWER_LIMITED   |           11 |             62 |                    51 |                0 | +51 folds for the DSR gate — field size alone cannot rescue it at this dispersion |
| bb_pct   | POWER_LIMITED   |           11 |             27 |                    16 |                2 | +16 folds for the DSR gate, OR a field of ≤2 arms at the CURRENT fold count       |
| iso      | POWER_LIMITED   |           11 |             56 |                    45 |                0 | +45 folds for the DSR gate — field size alone cannot rescue it at this dispersion |

⚠️ **Folds here ARE MLB debut cohorts — one per season — and the MLB label substrate (`mart_batter_rolling_stats`, `stg_batter_pitches`) begins in 2015.** So 11 folds is the MAXIMUM available today on both sides, and every fold-count trigger above is **CALENDAR-BOUND: +1 fold per MLB season**, not a window widening that could be done now (MH2 rule (b)). See `mh2_2_preregistration.md` §8 for the one lever that IS reachable today.


🪤 **READ THE `max_field_size` LEG OF THOSE TRIGGERS WITH CARE — FOR `bb_pct` (≤2 arms) IT PRESCRIBES EXACTLY THE THING THIS STORY RETIRES.** `cv_power.classify_null` offers 'a field of ≤N arms at the CURRENT fold count' as a generic remedy, and it is a correct statement of the arithmetic. But the ≤2-arm field on this family **is the post-hoc one** — the arithmetic is satisfied by dropping `T3_tenure`, i.e. by dropping the arm that lost. **A smaller field is a legitimate remedy ONLY when the smaller family is declared in advance on MECHANISTIC grounds; it is never a licence to re-cut a field you have already scored.** Taken literally here it would re-commit the selection bias in a badge that reads like a re-test trigger.


## woba

_shipped foil: `levelenv` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| L0_foil           | foil   | False        | True     | 0.0287905 |           0        |        0        |    nan        |             0    |                   |                nan |                nan |
| A_weight_identity | anchor | False        | False    | 0.0287905 |           0        |        0        |    nan        |             0    |                   |                  1 |                  1 |
| A_traj_shuffled   | anchor | False        | True     | 0.0288575 |          -0.232817 |        0.727273 |      0.648806 |            69.58 |                   |                nan |                nan |
| T2_traj_raw       | player | True         | True     | 0.028864  |          -0.255338 |        0.454545 |      0.693462 |            69.58 |                   |                nan |                nan |
| T1_traj_ladder    | player | True         | True     | 0.0289315 |          -0.489738 |        0.545455 |      0.697022 |            69.58 |                   |                nan |                nan |
| T3_tenure         | player | True         | True     | 0.0289659 |          -0.609223 |        0.454545 |      0.7026   |            41.2  |                   |                nan |                nan |
| A_degenerate_mean | anchor | False        | True     | 0.0290349 |          -0.848671 |        0.363636 |      0.753329 |             0    |                   |                nan |                nan |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": -0.1606, "T2_traj_raw": -0.1574, "T3_tenure": -0.1656}


**Reasons**

- 🟡 no arm clears: best eligible `T2_traj_raw` MAE 0.02886 vs foil 0.02879 (-0.26%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## k_pct

_shipped foil: `park:exposure+levelenv+rel:0.5k` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| T1_traj_ladder    | player | True         | True     | 0.03798   |          1.18278   |        0.818182 |     0.0951929 |            69.58 |                   |                nan |                nan |
| T2_traj_raw       | player | True         | True     | 0.0380067 |          1.11338   |        0.818182 |     0.128824  |            69.58 |                   |                nan |                nan |
| T3_tenure         | player | True         | True     | 0.0383719 |          0.163151  |        0.636364 |     0.393709  |            41.2  |                   |                nan |                nan |
| A_traj_shuffled   | anchor | False        | True     | 0.0384294 |          0.0134277 |        0.636364 |     0.488439  |            69.58 |                   |                nan |                nan |
| L0_foil           | foil   | False        | True     | 0.0384346 |          0         |        0        |   nan         |             0    |                   |                nan |                nan |
| A_weight_identity | anchor | False        | False    | 0.0384346 |          0         |        0        |   nan         |             0    |                   |                  1 |                  1 |
| A_degenerate_mean | anchor | False        | True     | 0.0499488 |        -29.9579    |        0        |     0.999999  |             0    |                   |                nan |                nan |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": 0.4236, "T2_traj_raw": 0.3619, "T3_tenure": 0.0835}


**Reasons**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.357 ≥ 0.2. The contender spread is 1.032%, WIDE relative to the margin, and the in-sample winners are spread thinly (T2_traj_raw 42% (+0.070%), T1_traj_ladder 36% (+0.000%), T3_tenure 15% (+1.032%)) — this is genuine instability, a search that learnt nothing, not a tie (NF1.8). Either way it does not ship.

## bb_pct

_shipped foil: `park:exposure+levelenv+rel:2k` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| T2_traj_raw       | player | True         | True     | 0.0177052 |          1.40384   |       0.818182  |    0.00376528 |            69.58 |                   |                nan |                nan |
| T1_traj_ladder    | player | True         | True     | 0.0177371 |          1.22644   |       0.909091  |    0.00393133 |            69.58 |                   |                nan |                nan |
| A_traj_shuffled   | anchor | False        | True     | 0.0179539 |          0.0187547 |       0.454545  |    0.422456   |            69.58 |                   |                nan |                nan |
| L0_foil           | foil   | False        | True     | 0.0179573 |          0         |       0         |  nan          |             0    |                   |                nan |                nan |
| A_weight_identity | anchor | False        | False    | 0.0179573 |          0         |       0         |  nan          |             0    |                   |                  1 |                  1 |
| T3_tenure         | player | True         | True     | 0.0180613 |         -0.579206  |       0.454545  |    0.851406   |            41.2  |                   |                nan |                nan |
| A_degenerate_mean | anchor | False        | True     | 0.0207667 |        -15.645     |       0.0909091 |    0.999826   |             0    |                   |                nan |                nan |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": 0.9984, "T2_traj_raw": 1.0061, "T3_tenure": -0.3316}


**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.849 < 0.95 (n_trials=3). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## iso

_shipped foil: `park:exposure+levelenv+rel:2k` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| T1_traj_ladder    | player | True         | True     | 0.0379241 |           1.41832  |       0.818182  |    0.00647658 |            69.58 |                   |                nan |                nan |
| T2_traj_raw       | player | True         | True     | 0.0379515 |           1.34701  |       0.818182  |    0.0124312  |            69.58 |                   |                nan |                nan |
| L0_foil           | foil   | False        | True     | 0.0384697 |           0        |       0         |  nan          |             0    |                   |                nan |                nan |
| A_weight_identity | anchor | False        | False    | 0.0384697 |           0        |       0         |  nan          |             0    |                   |                  1 |                  1 |
| A_traj_shuffled   | anchor | False        | True     | 0.0385671 |          -0.253267 |       0.272727  |    0.828503   |            69.58 |                   |                nan |                nan |
| T3_tenure         | player | True         | True     | 0.0391883 |          -1.86813  |       0.363636  |    0.891037   |            41.2  |                   |                nan |                nan |
| A_degenerate_mean | anchor | False        | True     | 0.0431384 |         -12.1362   |       0.0909091 |    0.999271   |             0    |                   |                nan |                nan |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": 0.9098, "T2_traj_raw": 0.7951, "T3_tenure": -0.3964}


**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.759 < 0.95 (n_trials=3). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## 6. Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)

**Binding constraint: the deflation gates — at least one arm would ship without them**

| metric   | arm            |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind                                                             |   folds_have |   folds_needed_BH |   folds_needed_DSR | unreachable_gates   |   extra_seasons_needed |
|:---------|:---------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-----------------------------------------------------------------|-------------:|------------------:|-------------------:|:--------------------|-----------------------:|
| woba     | T2_traj_raw    |            -0.2553 |        0.454545 |    0.693462   | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan | []                  |                    nan |
| k_pct    | T1_traj_ladder |             1.1828 |        0.818182 |    0.0951929  | True         | True              | False        | False        | False             | underpowered                                                     |           11 |                24 |                 62 | []                  |                     51 |
| bb_pct   | T2_traj_raw    |             1.4038 |        0.818182 |    0.00376528 | True         | True              | True         | False        | True              | underpowered                                                     |           11 |                11 |                 27 | []                  |                     16 |
| iso      | T1_traj_ladder |             1.4183 |        0.818182 |    0.00647658 | True         | True              | True         | False        | True              | underpowered                                                     |           11 |                11 |                 56 | []                  |                     45 |

## Reading notes

- **🔒 LOCK 1 — `T3_tenure` is in the field BECAUSE it lost last time.** Dropping an arm for losing is not a field definition, it is a selection, and it is the second layer of the very bias DSR exists to deflate.

- **🔒 LOCK 2 — this is the TRAJECTORY family only.** The player-structure arms (`P1`/`P2`/`P3`/`P4`) keep E7.15-H3's verdict. The pitcher side's largest H3 lift (`k_pct` +1.713%) is `P4_re_dedup` — PLAYER STRUCTURE — and crediting trajectory with it would mis-attribute the result. **Batter and pitcher are separate verdicts and are never pooled: the batter side is where the lead is; the pitcher trajectory arms are NEGATIVE on `k_pct`, `bb_pct` and `hr_rate`.**

- **🔒 LOCK 5 — `A_re_shuffled` is deliberately ABSENT.** It is a matched foil for the player random intercept, which lock 2 removed from the field, so it has no defender here. An anchor without its defender can neither pass nor fail meaningfully (NF1.7 (a)) and re-pointing it at the current leader would veto an innocent arm for another mechanism's sin (NF-D16 g‴).

- **A diagnostic anchor is NEVER a trial (MH2.1 (a))** — the DSR field is the 3 selectable arms; the foil and all anchors are excluded from `n_trials` and from the dispersion `V`. Asserted mechanically by `_assert_declared_field`, not assumed.

- 🪤 **`classify_null`'s `max_field_size` re-test trigger is UNSAFE ADVICE once a field is already pre-registered — a finding about the INSTRUMENT, surfaced because MH2.2 is the first story to run it against a declared family.** 'Re-run in a field of ≤N arms' is arithmetically correct and, on this family, is satisfied by dropping the arm that lost. The remedy is only legitimate when the smaller family is declared in advance on mechanistic grounds. `classify_null` cannot tell the two apart, so the CALLER must — which is what §5's callout does.

- **The `folds_needed` figures here supersede `mh2_2_preregistration.md` §4's.** The pre-registration computed `dsr_required_sr`/`folds_to_clear_dsr` under NORMAL moments while this run threads the winner's EMPIRICAL skew and kurtosis — the same moments the DSR gate itself uses. Every DSR value, every verdict and all nine null STATES are unchanged (the pre-registered DSRs came from `deflated_sharpe`, which was already empirical); only the derived bar and fold counts move. It is a live instance of `cv_power`'s own 'same moments everywhere, or nowhere' warning, recorded rather than quietly corrected.

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

