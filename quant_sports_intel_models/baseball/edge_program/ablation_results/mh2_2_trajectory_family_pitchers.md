# MH2.2 — the trajectory family as its OWN pre-registered field (pitcher side)

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
   "dsr": 0.12005594740312975,
   "metric": "k_pct",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "GENUINE_ABSENCE",
   "pbo": 0.4857142857142857,
   "verdict": "DROP"
  },
  {
   "dsr": 0.1369496266306277,
   "metric": "bb_pct",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "GENUINE_ABSENCE",
   "pbo": 0.9857142857142858,
   "verdict": "DROP"
  },
  {
   "dsr": 0.08941111461671336,
   "metric": "hr_rate",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "DSR_UNREACHABLE",
   "pbo": 0.07142857142857142,
   "verdict": "DROP"
  },
  {
   "dsr": 0.5641297946607979,
   "metric": "gb_pct",
   "n_arms": 3,
   "n_folds": 11,
   "null_state": "POWER_LIMITED",
   "pbo": 0.12857142857142856,
   "verdict": "DROP"
  }
 ],
 "primary_contrast": "the DECLARED 3-arm trajectory family vs the shipped E7.12-S1 foil",
 "reason": null,
 "schema": 1,
 "source_artifact": "mh2_2_trajectory_family_pitchers.md",
 "status": "recorded",
 "verdict": "k_pct=DROP, bb_pct=DROP, hr_rate=DROP, gb_pct=DROP"
}
-->


_generated 2026-08-03T21:54:02.906084+00:00 · declared field = `T1_traj_ladder`, `T2_traj_raw`, `T3_tenure` · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> Pre-registration (written before any arm was scored): `mh2_2_preregistration.md`.

> ⚠️ **A projection, not an edge claim.** Nothing here is emitted to the served board.


## 0. What this run retires

E7.15-H3 recorded the trajectory arms as clearing **DSR 0.998** over a 2-arm field. That field is **POST-HOC** — H3's own pre-registration names THREE trajectory arms and the 0.998 drops `T3_tenure`, *the arm that lost*. This run scores the family **as declared**.

⛔ **You get to pre-register a family; you do not get to discover one.**


## 1. Reproduction anchor — is this the SAME evidence as E7.15-H3?

**OK** — every shared arm reproduces E7.15-H3's recorded per-fold MAE — the two runs are the SAME evidence, so the field-definition comparison is valid.

| metric   |   n_shared_arms |   n_cells_compared |   max_abs_mae_gap_vs_h3 | status   |
|:---------|----------------:|-------------------:|------------------------:|:---------|
| k_pct    |               7 |                 77 |                       0 | OK       |
| bb_pct   |               7 |                 77 |                       0 | OK       |
| hr_rate  |               7 |                 77 |                       0 | OK       |
| gb_pct   |               7 |                 77 |                       0 | OK       |

## 2. Verdicts (declared 3-arm field)

| metric   | verdict   | winner   | best_arm       |   pct_lift_vs_foil | BH-FDR   |   PBO(eligible) |   DSR(declared 3-arm) | null_state      |
|:---------|:----------|:---------|:---------------|-------------------:|:---------|----------------:|----------------------:|:----------------|
| k_pct    | DROP      | L0_foil  | T1_traj_ladder |             -0.257 | False    |       0.485714  |                0.1201 | GENUINE_ABSENCE |
| bb_pct   | DROP      | L0_foil  | T1_traj_ladder |             -0.335 | False    |       0.985714  |                0.1369 | GENUINE_ABSENCE |
| hr_rate  | DROP      | L0_foil  | T2_traj_raw    |              0.013 | False    |       0.0714286 |                0.0894 | DSR_UNREACHABLE |
| gb_pct   | DROP      | L0_foil  | T1_traj_ladder |              1.209 | False    |       0.128571  |                0.5641 | POWER_LIMITED   |

- 🕳️ **`xwoba_against` — INACTIVE (declared before the run).** `xwoba_against`'s minor-league feature is a TRIPLE-A-ONLY Statcast summary, so a player carries it at one level at most and the trajectory delta has ZERO within-player transitions to act on. E7.15-H3 recorded `T1_traj_ladder` and `T2_traj_raw` at EXACTLY 0.000% lift here — the signature of an arm byte-identical to the foil. INACTIVE is a statement about the population's scope, not about the effect; the remedy is a different population, never more seasons (E7.15/NF1.9/MH2).


## 3. 🔒 The pre-registered bar — stated in per-fold Sharpe, not as a p-decimal

`required_sr` is `cv_power.dsr_required_sr`: the per-fold skill Sharpe an arm MUST post to reach DSR ≥ 0.95 **in this 3-arm field**. It is a property of the DESIGN and is readable before any arm is fitted.

| metric   | arm            |   n_folds |   observed_sr |   required_sr_for_dsr_gate |   sr_shortfall |   folds_needed_for_dsr |   extra_debut_cohorts_needed |   dsr_ceiling_at_this_n_obs |   var_trials_sr |
|:---------|:---------------|----------:|--------------:|---------------------------:|---------------:|-----------------------:|-----------------------------:|----------------------------:|----------------:|
| k_pct    | T1_traj_ladder |        11 |       -0.1566 |                     1.6874 |         1.844  |                    nan |                          nan |                      0.9958 |        0.033119 |
| bb_pct   | T1_traj_ladder |        11 |       -0.0821 |                     2.1315 |         2.2136 |                    nan |                          nan |                      0.9935 |        0.07342  |
| hr_rate  | T2_traj_raw    |        11 |        0.0177 |                     0.9603 |         0.9426 |                    nan |                          nan |                      1      |        0.268653 |
| gb_pct   | T1_traj_ladder |        11 |        0.4216 |                     1.1583 |         0.7366 |                   1039 |                         1028 |                      0.9995 |        0.183992 |

**Fold-consistency clause (MH2/H8, calibrated):** at 11 folds it requires **8/11** wins at α=0.2 (null false-fire 0.113) against the legacy `≥60%` bar's 7 wins (null false-fire 0.274). It is weakly STRICTER, so it can only ever prevent a false ADD — never manufacture one.


## 4. ⭐ What the retired post-hoc 2-arm field actually bought

Shrinking a field moves TWO things and only one is 'multiplicity': the trial COUNT `N`, and the cross-trial Sharpe DISPERSION `V` — because the arm you drop is the one far from the winner (`cv_power.decompose_field_size`). **The dispersion channel is the dominant one here**, i.e. the 0.998 was bought by deleting a LOSER's spread, not by an honest multiplicity reduction.

| metric   | dropped   |   DSR_declared_3arm |   DSR_posthoc_2arm |   if_only_N_shrank |   if_only_V_shrank |   V_declared |   V_posthoc |   V_collapse_ratio |
|:---------|:----------|--------------------:|-------------------:|-------------------:|-------------------:|-------------:|------------:|-------------------:|
| k_pct    | T3_tenure |              0.1201 |             0.249  |             0.172  |             0.2315 |    0.0331189 |  0.00201065 |       16.5         |
| bb_pct   | T3_tenure |              0.1369 |             0.376  |             0.218  |             0.3689 |    0.0734203 |  0.00025991 |      282.5         |
| hr_rate  | T3_tenure |              0.0894 |             0.3115 |             0.2126 |             0.1997 |    0.268653  |  0.110668   |        2.4         |
| gb_pct   | T3_tenure |              0.5641 |             0.8885 |             0.7172 |             0.8884 |    0.183992  |  1e-07      |        1.86188e+06 |

## 5. Null classification (`cv_power.classify_null`) and the re-test trigger

| metric        | state           |   folds_have |   folds_needed |   extra_debut_cohorts |   max_field_size | retest_trigger                                                                                                                                                                                      |
|:--------------|:----------------|-------------:|---------------:|----------------------:|-----------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| k_pct         | GENUINE_ABSENCE |           11 |            nan |                   nan |              nan |                                                                                                                                                                                                     |
| bb_pct        | GENUINE_ABSENCE |           11 |            nan |                   nan |              nan |                                                                                                                                                                                                     |
| hr_rate       | DSR_UNREACHABLE |           11 |            nan |                   nan |                0 | NOT rescuable by field size either — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric) |
| gb_pct        | POWER_LIMITED   |           11 |           1039 |                  1028 |                0 | +1028 folds for the DSR gate — field size alone cannot rescue it at this dispersion                                                                                                                 |
| xwoba_against | INACTIVE        |          nan |            nan |                   nan |              nan | a population on which the mechanism can act at all                                                                                                                                                  |

⚠️ **Folds here ARE MLB debut cohorts — one per season — and the MLB label substrate (`mart_batter_rolling_stats`, `stg_batter_pitches`) begins in 2015.** So 11 folds is the MAXIMUM available today on both sides, and every fold-count trigger above is **CALENDAR-BOUND: +1 fold per MLB season**, not a window widening that could be done now (MH2 rule (b)). See `mh2_2_preregistration.md` §8 for the one lever that IS reachable today.


## k_pct

_shipped foil: `baseline` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| L0_foil           | foil   | False        | True     | 0.0356208 |          0         |        0        |    nan        |             0    |                   |                nan |                nan |
| A_weight_identity | anchor | False        | False    | 0.0356208 |          0         |        0        |    nan        |             0    |                   |                  1 |                  1 |
| A_traj_shuffled   | anchor | False        | True     | 0.0356542 |         -0.0936699 |        0.454545 |      0.743198 |            68.89 |                   |                nan |                nan |
| T1_traj_ladder    | player | True         | True     | 0.0357124 |         -0.257138  |        0.545455 |      0.692596 |            68.89 |                   |                nan |                nan |
| T2_traj_raw       | player | True         | True     | 0.0357617 |         -0.395572  |        0.545455 |      0.758837 |            68.89 |                   |                nan |                nan |
| T3_tenure         | player | True         | True     | 0.0358676 |         -0.692666  |        0.454545 |      0.935431 |            47.42 |                   |                nan |                nan |
| A_degenerate_mean | anchor | False        | True     | 0.0373594 |         -4.88088   |        0.181818 |      0.977395 |             0    |                   |                nan |                nan |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": -0.1566, "T2_traj_raw": -0.22, "T3_tenure": -0.4987}


**Reasons**

- 🟡 no arm clears: best eligible `T1_traj_ladder` MAE 0.03571 vs foil 0.03562 (-0.26%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## bb_pct

_shipped foil: `park:exposure+levelenv+rel:1k+w:mlb_pa` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| L0_foil           | foil   | False        | True     | 0.0190711 |           0        |       0         |    nan        |             0    |                   |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0190711 |           0        |       0         |    nan        |             0    |                   |           0.387543 |            2.25484 |
| T1_traj_ladder    | player | True         | True     | 0.019135  |          -0.335158 |       0.727273  |      0.604542 |            68.89 |                   |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0191426 |          -0.374987 |       0.363636  |      0.954144 |            47.42 |                   |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | True     | 0.0191538 |          -0.433729 |       0.363636  |      0.870048 |            68.89 |                   |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.0191759 |          -0.549406 |       0.818182  |      0.63245  |            68.89 |                   |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0212479 |         -11.414    |       0.0909091 |      0.999382 |             0    |                   |         nan        |          nan       |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": -0.0821, "T2_traj_raw": -0.1049, "T3_tenure": -0.5624}


**Reasons**

- 🟡 no arm clears: best eligible `T1_traj_ladder` MAE 0.01914 vs foil 0.01907 (-0.34%, fold win rate 73%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## hr_rate

_shipped foil: `park:exposure+levelenv+rel:1k+w:mlb_pa` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |    oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|-----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| T2_traj_raw       | player | True         | True     | 0.00977309 |          0.0130464 |       0.454545  |      0.477108 |            68.89 |                   |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.00977437 |          0         |       0         |    nan        |             0    |                   |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.00977437 |          0         |       0         |    nan        |             0    |                   |           0.387543 |            2.25484 |
| T1_traj_ladder    | player | True         | True     | 0.0097935  |         -0.195786  |       0.454545  |      0.917935 |            68.89 |                   |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | True     | 0.00980937 |         -0.358066  |       0.0909091 |      0.999427 |            68.89 |                   |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.00991537 |         -1.44261   |       0.0909091 |      0.996466 |            47.42 |                   |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.00992128 |         -1.50304   |       0.181818  |      0.975152 |             0    |                   |         nan        |          nan       |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": -0.4527, "T2_traj_raw": 0.0177, "T3_tenure": -1.0175}


**Reasons**

- 🟡 no arm clears: best eligible `T2_traj_raw` MAE 0.00977 vs foil 0.00977 (0.01%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## gb_pct

_shipped foil: `baseline` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved | n_player_blocks   |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|:------------------|-------------------:|-------------------:|
| T1_traj_ladder    | player | True         | True     | 0.0472568 |           1.20883  |        0.818182 |     0.0961093 |            68.89 |                   |                nan |                nan |
| T2_traj_raw       | player | True         | True     | 0.0472865 |           1.14675  |        0.818182 |     0.0963243 |            68.89 |                   |                nan |                nan |
| L0_foil           | foil   | False        | True     | 0.0478351 |           0        |        0        |   nan         |             0    |                   |                nan |                nan |
| A_weight_identity | anchor | False        | False    | 0.0478351 |           0        |        0        |   nan         |             0    |                   |                  1 |                  1 |
| A_traj_shuffled   | anchor | False        | True     | 0.0480963 |          -0.546192 |        0.363636 |     0.803082  |            68.89 |                   |                nan |                nan |
| T3_tenure         | player | True         | True     | 0.0483876 |          -1.15517  |        0.454545 |     0.844341  |            47.42 |                   |                nan |                nan |
| A_degenerate_mean | anchor | False        | True     | 0.0573124 |         -19.8125   |        0        |     0.999983  |             0    |                   |                nan |                nan |

**Anchors**


- `A_weight_identity` byte-no-op: True (max |Δ| = 0.0)

**Per-arm trial Sharpes (the DSR field):** {"T1_traj_ladder": 0.4216, "T2_traj_raw": 0.4212, "T3_tenure": -0.3215}


**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.564 < 0.95 (n_trials=3). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## 6. Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)

**Binding constraint: BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing**

| metric   | arm            |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind                                                             |   folds_have |   folds_needed_BH |   folds_needed_DSR | unreachable_gates   |   extra_seasons_needed |
|:---------|:---------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-----------------------------------------------------------------|-------------:|------------------:|-------------------:|:--------------------|-----------------------:|
| k_pct    | T1_traj_ladder |            -0.2571 |        0.545455 |     0.692596  | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan | []                  |                    nan |
| bb_pct   | T1_traj_ladder |            -0.3352 |        0.727273 |     0.604542  | False        | True              | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan | []                  |                    nan |
| hr_rate  | T2_traj_raw    |             0.013  |        0.454545 |     0.477108  | True         | False             | True         | False        | False             | underpowered                                                     |           11 |               nan |                nan | ['BH-FDR', 'DSR']   |                    nan |
| gb_pct   | T1_traj_ladder |             1.2088 |        0.818182 |     0.0961093 | True         | True              | True         | False        | False             | underpowered                                                     |           11 |                25 |               1039 | []                  |                   1028 |

## Reading notes

- **🔒 LOCK 1 — `T3_tenure` is in the field BECAUSE it lost last time.** Dropping an arm for losing is not a field definition, it is a selection, and it is the second layer of the very bias DSR exists to deflate.

- **🔒 LOCK 2 — this is the TRAJECTORY family only.** The player-structure arms (`P1`/`P2`/`P3`/`P4`) keep E7.15-H3's verdict. The pitcher side's largest H3 lift (`k_pct` +1.713%) is `P4_re_dedup` — PLAYER STRUCTURE — and crediting trajectory with it would mis-attribute the result. **Batter and pitcher are separate verdicts and are never pooled: the batter side is where the lead is; the pitcher trajectory arms are NEGATIVE on `k_pct`, `bb_pct` and `hr_rate`.**

- **🔒 LOCK 5 — `A_re_shuffled` is deliberately ABSENT.** It is a matched foil for the player random intercept, which lock 2 removed from the field, so it has no defender here. An anchor without its defender can neither pass nor fail meaningfully (NF1.7 (a)) and re-pointing it at the current leader would veto an innocent arm for another mechanism's sin (NF-D16 g‴).

- **A diagnostic anchor is NEVER a trial (MH2.1 (a))** — the DSR field is the 3 selectable arms; the foil and all anchors are excluded from `n_trials` and from the dispersion `V`. Asserted mechanically by `_assert_declared_field`, not assumed.

- 🪤 **`classify_null`'s `max_field_size` re-test trigger is UNSAFE ADVICE once a field is already pre-registered — a finding about the INSTRUMENT, surfaced because MH2.2 is the first story to run it against a declared family.** 'Re-run in a field of ≤N arms' is arithmetically correct and, on this family, is satisfied by dropping the arm that lost. The remedy is only legitimate when the smaller family is declared in advance on mechanistic grounds. `classify_null` cannot tell the two apart, so the CALLER must — which is what §5's callout does.

- **The `folds_needed` figures here supersede `mh2_2_preregistration.md` §4's.** The pre-registration computed `dsr_required_sr`/`folds_to_clear_dsr` under NORMAL moments while this run threads the winner's EMPIRICAL skew and kurtosis — the same moments the DSR gate itself uses. Every DSR value, every verdict and all nine null STATES are unchanged (the pre-registered DSRs came from `deflated_sharpe`, which was already empirical); only the derived bar and fold counts move. It is a live instance of `cv_power`'s own 'same moments everywhere, or nowhere' warning, recorded rather than quietly corrected.

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

