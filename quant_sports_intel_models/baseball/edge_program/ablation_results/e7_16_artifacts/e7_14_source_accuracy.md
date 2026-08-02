# E7.14 — source accuracy: NULL — no source robustly out-orders the other. The measured gap is 0.0040 against a minimum detectable 0.0245, and it does not hold its sign across folds. E7.11's EQUAL WEIGHT is the honest default; the shipped 8/3 board is CONFIRMED, not corrected.

🔒 `best_alpha = 0` — this is ORDERING ACCURACY, not edge.

## ⚠️ The asymmetry, before any number

* E7.8's stated risk; E7.13 measured the `level` leak on it. MLB Pipeline's archive scans clean (E7.16 §1).
* FanGraphs rows are stamped <season>-07-01 (E7.7's retained-board convention); MLB Pipeline rows are stamped <season>-02-01. The FanGraphs rank has seen ~5 more months of the season — an advantage TO FanGraphs, on top of the retained-board risk.
* **Both inequalities favour FanGraphs ⇒ a FanGraphs win is UNINTERPRETABLE; a Pipeline win or a tie is conservative.**

## 1. The cohort (reported before scoring)

* MLB Pipeline cohort — 7186 rows, seasons `[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]`
* FanGraphs cohort — 5245 rows, seasons `[2018, 2019, 2020, 2021, 2022]`
* **head-to-head — 3667 rows, 1790 distinct players, seasons `[2018, 2019, 2020, 2021, 2022]`**
* both org-ranked 3667; both overall-ranked 443
* by type `{'batter': 1953, 'pitcher': 1714}`; by season `{2018: 628, 2019: 731, 2020: 769, 2021: 788, 2022: 751}`
* matched support for scoring — 3207/3667 rows (87.5%), 1690 person-clusters, folds `[2018, 2019, 2020, 2021, 2022]`

## 2. Rank-IC against realized dynasty value

| arm | kind | rank-IC | by fold |
|---|---|---|---|
| `oracle_order` 🎯 ceiling | anchor | +1.0000 | `{2018: 1.0, 2019: 1.0, 2020: 1.0, 2021: 1.0, 2022: 1.0}` |
| `pipeline_grade` | contender | +0.3772 | `{2018: 0.3431, 2019: 0.3471, 2020: 0.3372, 2021: 0.4231, 2022: 0.4356}` |
| `fangraphs_fv` | contender | +0.3371 | `{2018: 0.2879, 2019: 0.3369, 2020: 0.3316, 2021: 0.3284, 2022: 0.4006}` |
| `consensus_fg25` | contender | +0.3245 | `{2018: 0.2967, 2019: 0.3408, 2020: 0.3336, 2021: 0.2706, 2022: 0.3808}` |
| `consensus_fg75` | contender | +0.3222 | `{2018: 0.275, 2019: 0.3302, 2020: 0.3226, 2021: 0.2879, 2022: 0.3954}` |
| `consensus_equal` ⚖️ incumbent | incumbent | +0.3210 | `{2018: 0.2875, 2019: 0.3339, 2020: 0.3315, 2021: 0.2684, 2022: 0.3839}` |
| `pipeline_org` | contender | +0.3167 | `{2018: 0.2958, 2019: 0.3369, 2020: 0.3326, 2021: 0.2572, 2022: 0.3611}` |
| `fangraphs_org` | contender | +0.3128 | `{2018: 0.257, 2019: 0.3187, 2020: 0.3109, 2021: 0.2891, 2022: 0.3881}` |
| `random_order` 🎲 placebo | placebo | +0.0101 | `{2018: 0.0569, 2019: 0.0341, 2020: -0.1096, 2021: 0.0323, 2022: 0.0367}` |

### Two-sided anchors

* `oracle_is_the_ceiling` = **True**
* `oracle_ic` = **1.0**
* `placebo_loses_to_every_contender` = **True**
* `placebo_ic` = **0.0101**

### Paired head-to-heads (per-fold ΔIC; positive = the arm is better)

| comparison | arm | foil | ΔIC | 95% cluster-boot CI | folds improved | sign-consistent | sign-test p |
|---|---|---|---|---|---|---|---|
| pipeline_vs_fangraphs | `pipeline_org` | `fangraphs_org` | +0.0040 | [-0.0189, +0.0272] | 3/5 | False | 1.0000 |
| consensus_vs_fangraphs | `consensus_equal` | `fangraphs_org` | +0.0083 | [-0.0032, +0.0208] | 3/5 | False | 1.0000 |
| consensus_vs_pipeline | `consensus_equal` | `pipeline_org` | +0.0043 | [-0.0088, +0.0170] | 2/5 | False | 1.0000 |
| consensus_vs_best_single | `consensus_equal` | `pipeline_org` | +0.0043 | [-0.0088, +0.0170] | 2/5 | False | 1.0000 |
| selected_vs_incumbent | `pipeline_grade` | `consensus_equal` | +0.0562 | [+0.0321, +0.0795] | 5/5 | True | 0.0625 |
| pipeline_grade_vs_fangraphs_fv | `pipeline_grade` | `fangraphs_fv` | +0.0401 | [+0.0113, +0.0697] | 5/5 | True | 0.0625 |

### Deflation + power

* PBO (contender set) — `0.0` over 10 splits; flip distribution `{'pipeline_grade': 10}`
* DSR — **UNCOMPUTABLE**. UNCOMPUTABLE at 5 folds — DSR needs >=8 observations and the observation here is the FOLD, not the row. This is a POWER limit, not a passed or a failed gate.
* contender IC spread — 0.0645
* BH-FDR — cutoff `0.010000000000000002`, rejects `[False, False, False, False, False]` over `['pipeline_vs_fangraphs', 'consensus_vs_fangraphs', 'consensus_vs_pipeline', 'selected_vs_incumbent', 'pipeline_grade_vs_fangraphs_fv']`
* 🚨 **THE MULTIPLICITY GATE IS UNATTAINABLE AT 5 FOLDS** — the sign test's smallest possible p-value is 0.0625 and BH's rank-1 cutoff over 5 tests is 0.01, so **no effect of any magnitude could clear it here**. At this fold count NO effect of any size can clear the BH-FDR family — the binding constraint is the number of overlapping board seasons, not the strength of the signal. A result reported as 'tested, nothing there' would be wrong; it is 'not certifiable until the overlap reaches 8 seasons'.
* **POWER — minimum detectable IC gap at 95% is 0.0245 (SE 0.0125, 1690 clusters, 5 folds).** A measured gap smaller than the minimum detectable one is 'cannot distinguish at this N', NOT 'the sources are equally accurate'.

## 3. ⭐ The hindsight-free E7.8 FV replication

E7.8 measured FanGraphs' FV against realized outcomes on a RETAINED board. MLB Pipeline publishes the same 20-80 Overall grade from an archived report. Same players, same label, same folds.

| cohort | FanGraphs FV rank-IC | MLB Pipeline grade rank-IC | Δ (Pipeline − FanGraphs) | n |
|---|---|---|---|---|
| **pooled** | +0.3371 | +0.3772 | +0.0401 (5/5 folds) | 3207 |
| batter | +0.3903 | +0.4376 | +0.0473 | 1734 |
| pitcher | +0.3109 | +0.3426 | +0.0317 | 1473 |

Reference (NOT a comparison — different cohort and folds): E7.13's FV-alone rank-IC was batter 0.4161 / pitcher 0.3733.

⭐ **The point-in-time grade orders realized value at least as well as the retained FV — from a source holding NEITHER structural advantage.** E7.8's FV finding therefore does not rest on retained-board hindsight: had it, the retained grade would have been the stronger one, and it is not.

## 4. Verdict — three questions, three different answers

### Which SOURCE's rank orders better?

* `pipeline_minus_fangraphs_ic` — 0.004
* `min_detectable_gap_95` — 0.0245
* `folds_improved` — 3/5
* `sign_consistent` — False
* `distinguishable` — False

**NULL — no source robustly out-orders the other. The measured gap is 0.0040 against a minimum detectable 0.0245, and it does not hold its sign across folds. E7.11's EQUAL WEIGHT is the honest default; the shipped 8/3 board is CONFIRMED, not corrected.**

### Is the CONSENSUS better than the best single source?

* `delta_ic` — 0.0043
* `folds_improved` — 2/5

**NOT EARNED — the consensus is +0.0043 over the better single source, a fifth of the detectable gap and positive in only 2 of 5 folds. E7.11's refusal to claim 'averaging is more accurate' stands; equal weight is kept because it is the honest default, NOT because it was shown to be better.**

### Does the point-in-time GRADE beat the ranks?

* `best_contender` — pipeline_grade
* `pipeline_grade_minus_fangraphs_fv_ic` — 0.0401
* `folds_improved` — 5/5
* `sign_test_p` — 0.0625
* `certifiable_at_this_fold_count` — False
* `folds_required_to_certify` — 8

**REAL BUT NOT CERTIFIABLE HERE — the point-in-time MLB Pipeline GRADE out-orders every rank arm and FanGraphs' FV in 5 of 5 folds, but at 5 overlapping board seasons the sign test's floor (0.0625) sits above the BH-FDR cutoff (0.0100), so no effect of any size could pass. This is 'underpowered, not absent': it needs 8 overlapping seasons, and the overlap grows one per year.**
