# E7.16 — comps on the point-in-time Pipeline archive: SPLIT

**Cohort** — `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/quant_sports_intel_models/baseball/edge_program/ablation_results/e7_16_artifacts/pipeline_comp_cohort.parquet` built 2026-08-02T01:55:58+00:00
**Target** — fantasy_points over the 3 seasons after the board (0 for a prospect who never reached MLB)
**Primary metric** — CRPS (proper — the target is ~57% exact zeros; MAE inverts here)
**Incumbent** — fv_bucket (the empirical outcome distribution of same-grade, same-position historical prospects — here the grade is MLB Pipeline's published Overall)

## 1. Leakage scan (as-of columns vs the realized outcome)

**Positive control fired** — E7.8's `level`: AUC nan, largest one-sided bin 883 rows (16.8% of the cohort) at debut rate 0.0. Negative control `fv`: AUC 0.7005, flag `False`.

**Pipeline cohort flagged columns: `[]`**

| column | kind | n | AUC vs outcome | largest one-sided bin | share | its debut rate | flag |
|---|---|---|---|---|---|---|---|
| `fv` | numeric | 6577 | 0.6789 | `None` | 0.0 | nan | clean |
| `age` | numeric | 7186 | 0.6782 | `None` | 0.0 | nan | clean |
| `position` | categorical | 7186 | nan | `1B/2B/3B` | 0.0006 | 1.0 | clean |
| `top_level_pre_board` | categorical | 5225 | nan | `None` | 0.0 | nan | clean |
| `pro_experience_years` | numeric | 5225 | 0.6169 | `None` | 0.0 | nan | clean |
| `minor_k_pct` | numeric | 5218 | 0.4491 | `None` | 0.0 | nan | clean |
| `minor_bb_pct` | numeric | 5218 | 0.4892 | `None` | 0.0 | nan | clean |
| `minor_iso` | numeric | 2596 | 0.6096 | `None` | 0.0 | nan | clean |
| `minor_gb_pct` | numeric | 2622 | 0.508 | `None` | 0.0 | nan | clean |
| `minor_start_share` | numeric | 2622 | 0.5476 | `None` | 0.0 | nan | clean |
| `minor_pa` | numeric | 7186 | 0.727 | `None` | 0.0 | nan | clean |
| `pre_board_mlb_exposure` | numeric | 7186 | 0.5684 | `None` | 0.0 | nan | clean |
| `overall_rank` | numeric | 798 | 0.3564 | `None` | 0.0 | nan | clean |
| `org_rank` | numeric | 7183 | 0.3287 | `(missing)` | 0.0004 | 1.0 | clean |
| `eta` | numeric | 3994 | 0.3203 | `(2025.0, 2028.0]` | 0.0324 | 0.0172 | clean |
| `draft_year` | numeric | 4910 | 0.4084 | `None` | 0.0 | nan | clean |
| `org` | categorical | 7183 | nan | `(missing)` | 0.0004 | 1.0 | clean |
| `bio_season` | numeric | 7121 | 0.4784 | `None` | 0.0 | nan | clean |
| `milb_games` | numeric | 5225 | 0.6035 | `None` | 0.0 | nan | clean |
| `last_milb_season` | numeric | 5225 | 0.4799 | `None` | 0.0 | nan | clean |

## 2. The fold census — read before any score

Board seasons `[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]`, 7186 rows, 3202 distinct players, horizon 3.

| type | pool rows | bust share | **strictly-matured folds** | relaxed folds | CSCV computable |
|---|---|---|---|---|---|
| batter | 3756 | 0.5841 | **4** | 7 | True |
| pitcher | 3430 | 0.5554 | **4** | 7 | True |

The BINDING bound on the fold count is our realized-outcome substrate, not the Pipeline archive (17 seasons) and not the MiLB game logs (2005+). A board season earlier than 2015 opens its 3-season outcome window before the marts begin, so a real player would be scored as a partial bust.

**Primary fold rule: `strict`.**

## 3. Batters — projection: BLEND_WIRE

Pool 3756 rows, non-debut share **0.5841**. 1279/1938 rows scoreable by every contender. Folds: `[2019, 2020, 2021, 2022]`.

| arm | kind | CRPS | PIT max-decile-dev | p10–p90 coverage |
|---|---|---|---|---|
| `oracle_k15` 🎯 floor | anchor | 10.53 | 0.1439 | 0.934 |
| `comp_gower_k25` | comp | 77.60 | 0.0320 | 0.869 |
| `comp_gower_k15` | comp | 77.66 | 0.0515 | 0.842 |
| `blend_comp_fv` | blend | 79.16 | 0.0203 | 0.857 |
| `comp_gower_k10` | comp | 79.53 | 0.0914 | 0.877 |
| `comp_mahalanobis_k15` | comp | 80.75 | 0.0390 | 0.836 |
| `comp_gower_k15_simweighted` | comp | 82.30 | 0.0634 | 0.754 |
| `fv_bucket` | bucket | 85.91 | 0.0314 | 0.833 |
| `comp_no_fv_k15` | comp | 86.75 | 0.0429 | 0.849 |
| `comp_components_only_k15` | comp | 92.68 | 0.0421 | 0.855 |
| `marginal` 🚧 ceiling | degenerate | 93.05 | 0.0304 | 0.846 |
| `random_k15` 🎲 placebo | placebo | 98.62 | 0.0468 | 0.835 |
| `all_zero` 🚧 ceiling | degenerate | 129.67 | 0.5818 | 0.317 |

**Best contender** — `comp_gower_k25`

### Two-sided anchors

* `oracle_is_the_floor` = **True**
* `oracle_crps` = **10.532**
* `all_zero_loses` = **True**
* `all_zero_crps` = **129.667**
* `marginal_loses` = **True**
* `marginal_crps` = **93.047**
* `placebo_loses` = **True**
* `placebo_crps` = **98.615**
* `all_pass` = **True**

### Matched foils (paired ΔCRPS, negative = the arm is better)

| comparison | arm | foil | ΔCRPS | 95% CI | p | arm better |
|---|---|---|---|---|---|---|
| selected_vs_incumbent | `comp_gower_k25` | `fv_bucket` | -8.31 | [-11.26, -5.57] | 0.0000 | True |
| comp_vs_incumbent | `comp_gower_k15` | `fv_bucket` | -8.25 | [-11.50, -5.12] | 0.0000 | True |
| blend_vs_incumbent | `blend_comp_fv` | `fv_bucket` | -6.75 | [-8.55, -5.08] | 0.0000 | True |
| blend_vs_comp | `blend_comp_fv` | `comp_gower_k15` | +1.50 | [-0.00, +3.01] | 0.0530 | False |
| fv_channel | `comp_gower_k15` | `comp_no_fv_k15` | -9.09 | [-12.52, -5.93] | 0.0000 | True |
| structural_channel | `comp_gower_k15` | `comp_components_only_k15` | -15.02 | [-18.75, -11.54] | 0.0000 | True |
| similarity_channel | `comp_gower_k15` | `random_k15` | -20.95 | [-25.05, -16.96] | 0.0000 | True |
| kernel_channel | `comp_gower_k15` | `comp_gower_k15_simweighted` | -4.64 | [-7.04, -2.33] | 0.0000 | True |

### Deflation

* PBO (contender set) — `0.0` over 6 splits; whole field `0.0`
* Performance degradation — `0.0`
* Flip distribution — `{'comp_gower_k15': 1, 'comp_gower_k25': 5}`
* DSR — contender set `1.0`, whole field `1.0` (n = 734 CLUSTERS, not 1279 rows)
* Spread — contender 19.44%, whole field 1131.2%
* BH-FDR — cutoff `0.05`, rejects `[True, True, True, True, True, True, True]`

### Gates

* `anchors_pass` — **PASS**
* `beats_incumbent` — **PASS**
* `pbo_lt_0_2` — **PASS**
* `dsr_contender_ge_0_95` — **PASS**
* `pit_flat` — **PASS**
* `fdr_survives` — **PASS**

## 3. Pitchers — projection: DISPLAY_ONLY

Pool 3430 rows, non-debut share **0.5554**. 1021/1655 rows scoreable by every contender. Folds: `[2019, 2020, 2021, 2022]`.

| arm | kind | CRPS | PIT max-decile-dev | p10–p90 coverage |
|---|---|---|---|---|
| `oracle_k15` 🎯 floor | anchor | 5.40 | 0.1693 | 0.971 |
| `comp_mahalanobis_k15` | comp | 114.28 | 0.0373 | 0.845 |
| `blend_comp_fv` | blend | 114.37 | 0.0187 | 0.871 |
| `comp_gower_k25` | comp | 114.56 | 0.0334 | 0.859 |
| `fv_bucket` | bucket | 117.10 | 0.0518 | 0.869 |
| `comp_gower_k15` | comp | 118.31 | 0.0491 | 0.839 |
| `comp_gower_k10` | comp | 123.06 | 0.0980 | 0.882 |
| `marginal` 🚧 ceiling | degenerate | 123.81 | 0.0371 | 0.882 |
| `comp_no_fv_k15` | comp | 128.86 | 0.0499 | 0.867 |
| `random_k15` 🎲 placebo | placebo | 133.07 | 0.0461 | 0.870 |
| `comp_gower_k15_simweighted` | comp | 133.34 | 0.0714 | 0.745 |
| `comp_components_only_k15` | comp | 134.20 | 0.0461 | 0.870 |
| `all_zero` 🚧 ceiling | degenerate | 179.45 | 0.6287 | 0.277 |

**Best contender** — `comp_mahalanobis_k15`

### Two-sided anchors

* `oracle_is_the_floor` = **True**
* `oracle_crps` = **5.399**
* `all_zero_loses` = **True**
* `all_zero_crps` = **179.451**
* `marginal_loses` = **True**
* `marginal_crps` = **123.815**
* `placebo_loses` = **True**
* `placebo_crps` = **133.07**
* `all_pass` = **True**

### Matched foils (paired ΔCRPS, negative = the arm is better)

| comparison | arm | foil | ΔCRPS | 95% CI | p | arm better |
|---|---|---|---|---|---|---|
| selected_vs_incumbent | `comp_mahalanobis_k15` | `fv_bucket` | -2.82 | [-7.19, +1.40] | 0.1855 | True |
| comp_vs_incumbent | `comp_gower_k15` | `fv_bucket` | +1.21 | [-2.66, +5.07] | 0.5265 | False |
| blend_vs_incumbent | `blend_comp_fv` | `fv_bucket` | -2.73 | [-4.71, -0.81] | 0.0045 | True |
| blend_vs_comp | `blend_comp_fv` | `comp_gower_k15` | -3.94 | [-5.92, -1.98] | 0.0000 | True |
| fv_channel | `comp_gower_k15` | `comp_no_fv_k15` | -10.55 | [-15.93, -4.58] | 0.0000 | True |
| structural_channel | `comp_gower_k15` | `comp_components_only_k15` | -15.89 | [-21.81, -9.33] | 0.0000 | True |
| similarity_channel | `comp_gower_k15` | `random_k15` | -14.76 | [-20.93, -8.22] | 0.0000 | True |
| kernel_channel | `comp_gower_k15` | `comp_gower_k15_simweighted` | -15.02 | [-19.34, -10.76] | 0.0000 | True |

### Deflation

* PBO (contender set) — `0.0` over 6 splits; whole field `0.0`
* Performance degradation — `1.3188392503135304`
* Flip distribution — `{'comp_gower_k25': 1, 'comp_mahalanobis_k15': 2, 'blend_comp_fv': 3}`
* DSR — contender set `0.3789`, whole field `0.3091` (n = 663 CLUSTERS, not 1021 rows)
* Spread — contender 17.43%, whole field 3223.89%
* BH-FDR — cutoff `0.03571428571428572`, rejects `[False, False, True, True, True, True, True]`

### Gates

* `anchors_pass` — **PASS**
* `beats_incumbent` — **PASS**
* `pbo_lt_0_2` — **PASS**
* `dsr_contender_ge_0_95` — **FAIL**
* `pit_flat` — **PASS**
* `fdr_survives` — **FAIL**

### Is the null OURS or the data's? (gate sensitivity)

* failing gates — `['dsr_contender_ge_0_95', 'fdr_survives']`
* would it pass with the DSR gate REMOVED — **False** ⇒ binding constraint `not_dsr_alone`
* the selection was resolved inside a **0.081%** gap (`comp_mahalanobis_k15` over `blend_comp_fv`); that runner-up's own paired test against the incumbent sits at p = 0.0045
* The pre-registered selection (min CRPS over the contender set) is reported as-run and NOT revisited; this block exists so the null is attributable, not so the pick can be changed after seeing the p-values.

## 4. Ordering — may a comp term touch the board's RANKING?

⚖️ **Every arm is scored on MATCHED SUPPORT** (the rows on which all arms are defined) — see the E7.16 fix in `_ordering_study`. The unmatched column is shown beside it because the gap between them IS the finding: it is the comped subpopulation being easier to order, not the comp term ordering it better.

### Batters — `comp_mean_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0518**, improved in 4/4 folds (per fold [0.0432, 0.0354, 0.0514, 0.0773]). PBO `0.0`. Anchors: oracle-is-ceiling `True`, placebo IC `0.0058`. Matched support 1052/1863 rows (56.5%); 68.7% of rows have comps at all.

| arm | rank-IC (matched support) | rank-IC (unmatched — context only) |
|---|---|---|
| `oracle_order` | +1.0000 | +1.0000 |
| `board_plus_comp_w40` | +0.5732 | +0.4752 |
| `board_plus_comp_w30` | +0.5688 | +0.4753 |
| `board_plus_comp_w20` | +0.5595 | +0.4668 |
| `comp_only` | +0.5507 | +0.5458 |
| `board_plus_comp_w10` | +0.5446 | +0.4561 |
| `board_proxy` | +0.5213 | +0.4385 |
| `fv_only` | +0.4938 | +0.4450 |
| `random_order` | +0.0058 | -0.0129 |

### Batters — `comp_median_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w30`, ΔIC vs the board's own formula **+0.0363**, improved in 4/4 folds (per fold [0.0011, 0.0308, 0.0567, 0.0565]). PBO `0.0`. Anchors: oracle-is-ceiling `True`, placebo IC `0.0053`. Matched support 1056/1863 rows (56.7%); 68.7% of rows have comps at all.

| arm | rank-IC (matched support) | rank-IC (unmatched — context only) |
|---|---|---|
| `oracle_order` | +1.0000 | +1.0000 |
| `board_plus_comp_w30` | +0.5521 | +0.4622 |
| `board_plus_comp_w40` | +0.5516 | +0.4643 |
| `board_plus_comp_w20` | +0.5489 | +0.4615 |
| `board_plus_comp_w10` | +0.5362 | +0.4501 |
| `comp_only` | +0.5269 | +0.5241 |
| `board_proxy` | +0.5158 | +0.4385 |
| `fv_only` | +0.4926 | +0.4450 |
| `random_order` | +0.0053 | -0.0111 |

### Pitchers — `comp_mean_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0593**, improved in 4/4 folds (per fold [0.0526, 0.054, 0.0815, 0.0491]). PBO `0.16666666666666666`. Anchors: oracle-is-ceiling `True`, placebo IC `0.0026`. Matched support 1001/1607 rows (62.3%); 63.5% of rows have comps at all.

| arm | rank-IC (matched support) | rank-IC (unmatched — context only) |
|---|---|---|
| `oracle_order` | +1.0000 | +1.0000 |
| `board_plus_comp_w40` | +0.4146 | +0.3246 |
| `board_plus_comp_w30` | +0.4092 | +0.3213 |
| `comp_only` | +0.4081 | +0.3924 |
| `board_plus_comp_w20` | +0.4017 | +0.3143 |
| `fv_only` | +0.3899 | +0.3427 |
| `board_plus_comp_w10` | +0.3812 | +0.3055 |
| `board_proxy` | +0.3553 | +0.2933 |
| `random_order` | +0.0026 | -0.0144 |

### Pitchers — `comp_median_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0510**, improved in 4/4 folds (per fold [0.0718, 0.034, 0.0682, 0.0302]). PBO `0.16666666666666666`. Anchors: oracle-is-ceiling `True`, placebo IC `0.0047`. Matched support 999/1607 rows (62.2%); 63.5% of rows have comps at all.

| arm | rank-IC (matched support) | rank-IC (unmatched — context only) |
|---|---|---|
| `oracle_order` | +1.0000 | +1.0000 |
| `board_plus_comp_w40` | +0.3821 | +0.3236 |
| `board_plus_comp_w30` | +0.3816 | +0.3196 |
| `board_plus_comp_w20` | +0.3751 | +0.3133 |
| `comp_only` | +0.3658 | +0.3735 |
| `fv_only` | +0.3615 | +0.3427 |
| `board_plus_comp_w10` | +0.3554 | +0.3044 |
| `board_proxy` | +0.3311 | +0.2933 |
| `random_order` | +0.0047 | +0.0197 |
