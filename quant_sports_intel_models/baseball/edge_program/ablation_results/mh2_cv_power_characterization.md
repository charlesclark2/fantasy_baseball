# MH2 — CV-power characterization for §0.5 bake-offs

> 🔒 **DIAGNOSTIC OF THE EVAL, NOT A MODEL.** `best_alpha = 0`. Nothing here re-fits an arm, re-scores a metric or changes a recorded verdict — every ADD and DROP in the record stands exactly as scored. What changes is how a null may be READ.

_Generated 2026-08-02T06:28:14+00:00 from stored artifacts only (no Snowflake, no re-fit)._

## 0. The finding, in one paragraph

Three of the four §0.5 gates have a **stringency that moves with the design rather than with the evidence**, and the program has been reading them as if they were fixed bars. The fold-consistency clause fires on a true lift of ZERO **49.7% of the time at 3 folds and 27.4% at 11**; PBO is not merely failed but **UNDEFINED** below 4 folds; the fold-sign floor `2⁻ⁿ` can sit ABOVE the BH cutoff, so that **no effect of any size could pass**; and DSR's bar rises with the FIELD SIZE, so the same winner on the same folds clears at 2 arms and fails at 7. Consequently a §0.5 null means one of **five** different things, not two — and the single most actionable output below is that the **MLB game model's 3-fold ceiling is a WINDOW CHOICE, not a data limit**: the served feature store already holds 2016–2026.

## 1. Validation — reproduce the record before believing the instrument

A power diagnostic that cannot reproduce results already on file is not evidence about anything. Every number in this report comes from the same module that produced these.

| case                                                           | recorded                                                                 | reproduced                                                                       | agrees   |
|:---------------------------------------------------------------|:-------------------------------------------------------------------------|:---------------------------------------------------------------------------------|:---------|
| E7.9 — achievable folds from the window                        | 3 purged/embargoed folds on a 2021-04-18 → 2026-07-27 matrix (6 seasons) | achievable_folds(6) = 3                                                          | True     |
| E7.12-S6 — fold-clause false-fire at 3 folds (H8's diagnosis)  | 0.4968 (simulated, `fold_gate_false_fire_at_zero_lift`)                  | exact binomial P(Bin(3,½) ≥ 2) = 0.5000                                          | True     |
| E7.14 — fold-sign certifiability floor                         | sign_test_p floor 0.0625 at 5 folds; `folds_required_to_certify` = 8     | sign_test_floor(5, two_sided) = 0.0625; folds_for_sign_certifiability(0.010) = 8 | True     |
| E7.15-H3 `bb_pct` — SAME winner/folds/effect, field 7 → 2 arms | DSR 0.6065 (7 arms) → ~0.998 (2-arm trajectory family)                   | DSR 0.6065 → 0.9985  (SR 1.0061 held fixed; SR0 0.9147 → 0.0028)                 | True     |
| E7.15-H3 `iso` — SAME winner/folds/effect, field 7 → 2 arms    | DSR 0.6573 (7 arms) → ~0.981 (2-arm trajectory family)                   | DSR 0.6573 → 0.9812  (SR 0.9098 held fixed; SR0 0.7408 → 0.0422)                 | True     |

**Field-size decomposition — E7.15-H3 `bb_pct` — SAME winner/folds/effect, field 7 → 2 arms**

```
{
 "dsr_wide_field": 0.6065,
 "dsr_narrow_field": 0.9985,
 "dsr_if_only_trial_count_shrank": 0.9751,
 "dsr_if_only_dispersion_shrank": 0.9984,
 "dsr_ceiling_at_this_n_obs": 1.0,
 "sr0_wide": 0.9147,
 "sr0_narrow": 0.0028,
 "share_from_trial_count": 0.94,
 "share_from_dispersion": 1.0,
 "passes_wide": false,
 "passes_narrow": true
}
```
- Largest field this effect still clears at the OBSERVED dispersion: **2 arms**.
- Folds needed to clear DSR *in the wide field*: **372** (`null_analysis` recorded 140 — see §5, defect 3).

**Field-size decomposition — E7.15-H3 `iso` — SAME winner/folds/effect, field 7 → 2 arms**

```
{
 "dsr_wide_field": 0.6573,
 "dsr_narrow_field": 0.9812,
 "dsr_if_only_trial_count_shrank": 0.9351,
 "dsr_if_only_dispersion_shrank": 0.972,
 "dsr_ceiling_at_this_n_obs": 1.0,
 "sr0_wide": 0.7408,
 "sr0_narrow": 0.0422,
 "share_from_trial_count": 0.858,
 "share_from_dispersion": 0.972,
 "passes_wide": false,
 "passes_narrow": true
}
```
- Largest field this effect still clears at the OBSERVED dispersion: **0 arms**.
- Folds needed to clear DSR *in the wide field*: **166** (`null_analysis` recorded 120 — see §5, defect 3).

### ⚠️⚠️ THE FIELD-SIZE CASE DOES NOT SUPPORT THE HEADLINE IT WAS BEING USED FOR

The recorded flip is real and reproduces exactly — but **the "2-arm trajectory family" is a POST-HOC field.** H3's own pre-registration names THREE trajectory arms (`T1_traj_ladder`, `T2_traj_raw`, `T3_tenure`); the 0.998 figure drops `T3_tenure`. Restore it and the SAME winner on the SAME folds reaches **0.849**, not 0.95.

Scoring each mechanism's best arm against its OWN pre-registered family:

| side    | metric        | family           |   arms | best arm       |   %lift | folds   | clause   |   DSR in its OWN family | clears   |
|:--------|:--------------|:-----------------|-------:|:---------------|--------:|:--------|:---------|------------------------:|:---------|
| batter  | woba          | trajectory       |      3 | T2_traj_raw    |  -0.255 | 5/11    | fail     |                   0.285 | False    |
| batter  | woba          | player-structure |      4 | P3_player_re   |   0.841 | 7/11    | fail     |                   0.528 | False    |
| batter  | k_pct         | trajectory       |      3 | T1_traj_ladder |   1.183 | 9/11    | pass     |                   0.748 | False    |
| batter  | k_pct         | player-structure |      4 | P2_dedup_sqrt  |  -0.238 | 5/11    | fail     |                   0.072 | False    |
| batter  | bb_pct        | trajectory       |      3 | T2_traj_raw    |   1.404 | 9/11    | pass     |                   0.849 | False    |
| batter  | bb_pct        | player-structure |      4 | P2_dedup_sqrt  |  -0.213 | 5/11    | fail     |                   0.045 | False    |
| batter  | iso           | trajectory       |      3 | T1_traj_ladder |   1.418 | 9/11    | pass     |                   0.759 | False    |
| batter  | iso           | player-structure |      4 | P2_dedup_sqrt  |  -0.133 | 5/11    | fail     |                   0.16  | False    |
| pitcher | k_pct         | trajectory       |      3 | T1_traj_ladder |  -0.257 | 6/11    | fail     |                   0.12  | False    |
| pitcher | k_pct         | player-structure |      4 | P4_re_dedup    |   1.713 | 9/11    | pass     |                   0.695 | False    |
| pitcher | bb_pct        | trajectory       |      3 | T1_traj_ladder |  -0.335 | 8/11    | pass     |                   0.137 | False    |
| pitcher | bb_pct        | player-structure |      4 | P4_re_dedup    |   0.438 | 6/11    | fail     |                   0.423 | False    |
| pitcher | hr_rate       | trajectory       |      3 | T2_traj_raw    |   0.013 | 5/11    | fail     |                   0.089 | False    |
| pitcher | hr_rate       | player-structure |      4 | P4_re_dedup    |   0.107 | 6/11    | fail     |                   0.521 | False    |
| pitcher | gb_pct        | trajectory       |      3 | T1_traj_ladder |   1.209 | 9/11    | pass     |                   0.564 | False    |
| pitcher | gb_pct        | player-structure |      4 | P2_dedup_sqrt  |  -0.245 | 2/11    | fail     |                   0     | False    |
| pitcher | xwoba_against | trajectory       |      3 | T1_traj_ladder |   0     | 1/4     | fail     |                   0.497 | False    |
| pitcher | xwoba_against | player-structure |      4 | P4_re_dedup    |   0.773 | 3/4     | fail     |                   0.771 | False    |

⭐ **At the honestly pre-registered family sizes, NOTHING in E7.15-H3 clears.** That is the number a successor has to beat, and it is a materially different starting point from "0.998, basically there".

⚖️ **So the field-size rule is TWO-SIDED and both halves bind.** Bundling unrelated mechanisms OVER-taxes a real finding (the 7-arm reading, DSR 0.607, is too harsh) — but a family trimmed AFTER the fact UNDER-taxes it (the 2-arm reading is too generous), because the arm you drop is chosen precisely because it lost. That is a second layer of exactly the selection bias DSR exists to deflate. **You get to pre-register a family; you do not get to discover one.** The corollary for any successor: declare the family in the pre-registration, and if an arm in it turns out to be weak, that is a cost you have already agreed to pay.

(This also re-reads the H3 record itself: the pitcher side's largest lift — `k_pct` +1.713% — belongs to the PLAYER-STRUCTURE family (`P4_re_dedup`), not to the trajectory mechanism at all, and its own-family DSR is 0.695. A story that carries "H3's trajectory arms are a real effect" forward without splitting the families would attribute a player-structure result to trajectory.)

### ⚠️ A correction to the story prompt's framing of this case

The prompt states the validation case as *"iso +1.418%, 9/11 folds … FAILED DSR at 0.607 … CLEAR at 0.998"*. Read off the stored artifact those are **two different metrics of the same 7-arm field**: the `+1.418% / 9-of-11` effect is `iso` (DSR **0.657 → 0.981**) and the `0.607 → 0.998` pair is `bb_pct` (`+1.404%`, also 9 of 11). The *shape* the prompt describes — same winner, same folds, same effect, only the field size changed — is exactly right and holds for both, so both are reproduced above rather than one being silently chosen.

## 2. The power table — per (tier × window), per STAT

⚠️ **The fold RULE itself differs per tier, and it is a first-order driver nobody had written down.** `PurgedWalkForwardSplit` burns `min_train_seasons = 3` before it emits a single fold; leave-one-cohort-out emits one per cohort. So **the tier with the longest calendar history has the FEWEST folds** — the MLB game model, which is the *serving* path, has the least statistical resolution in the entire program.

| tier                             | window            | fold_rule                                             |   periods |   folds |   typical_arms | primary_contrast                                  | PBO_evaluable   | sign_floor            | sign_floor_vs_BH_rank1                                      | legacy_clause           | calibrated_clause       |   DSR_ceiling_at_any_effect |   DSR_required_SR@typical_arms |   DSR_required_SR@4_arms |   MDE_sd_legacy |   MDE_sd_calibrated | metric_family            | lever                                                              |
|:---------------------------------|:------------------|:------------------------------------------------------|----------:|--------:|---------------:|:--------------------------------------------------|:----------------|:----------------------|:------------------------------------------------------------|:------------------------|:------------------------|----------------------------:|-------------------------------:|-------------------------:|----------------:|--------------------:|:-------------------------|:-------------------------------------------------------------------|
| MLB game model — post_lineup     | 2021–2026         | PurgedWalkForwardSplit (n_seasons − 3)                |         6 |       3 |             28 | noise-floor margin (no fold clause, no BH family) | False           | n/a (not a sign test) | n/a                                                         | 2/3 (false-fire 0.500)  | 3/3 (false-fire 0.125)  |                      0.9772 |                           7.28 |                     4.44 |            1.65 |                1.65 | crps_game_model          | ⭐ WINDOW, available NOW — see the served-store measurement below. |
| MLB game model — pre_lineup      | 2021–2026         | PurgedWalkForwardSplit (n_seasons − 3)                |         6 |       3 |             24 | noise-floor margin (no fold clause, no BH family) | False           | n/a (not a sign test) | n/a                                                         | 2/3 (false-fire 0.500)  | 3/3 (false-fire 0.125)  |                      0.9772 |                           7.08 |                     4.44 |            1.65 |                1.65 | crps_game_model          | ⭐ WINDOW, available NOW.                                          |
| MiLB→MLB translation (batter)    | 2016–2026         | leave-one-MLB-debut-cohort-out (n_cohorts)            |        11 |      11 |              7 | paired-t                                          | True            | n/a (not a sign test) | n/a                                                         | 7/11 (false-fire 0.274) | 8/11 (false-fire 0.113) |                      1      |                           1.07 |                     0.94 |            0.95 |                1    | mae_pct_lift_translation | calendar only: +1 fold per completed debut cohort.                 |
| MiLB→MLB translation (pitcher)   | 2016–2026         | leave-one-MLB-debut-cohort-out (n_cohorts)            |        11 |      11 |              7 | paired-t                                          | True            | n/a (not a sign test) | n/a                                                         | 7/11 (false-fire 0.274) | 8/11 (false-fire 0.113) |                      1      |                           1.07 |                     0.94 |            0.95 |                1    | mae_pct_lift_translation | calendar only: +1 fold per completed debut cohort.                 |
| Prospect comps — strict maturity | 2015–2022 boards  | forward, 3-season outcome horizon matured             |         8 |       4 |             12 | paired-t                                          | True            | n/a (not a sign test) | n/a                                                         | 3/4 (false-fire 0.312)  | 4/4 (false-fire 0.062)  |                      0.9928 |                           3.15 |                     2.39 |            2.15 |                2.15 | crps_game_model          | calendar only: the 3-season horizon must mature.                   |
| Prospect comps — relaxed context | 2015–2022 boards  | forward, relaxed maturity                             |         8 |       7 |             12 | paired-t                                          | True            | n/a (not a sign test) | n/a                                                         | 5/7 (false-fire 0.227)  | 6/7 (false-fire 0.062)  |                      0.9997 |                           1.67 |                     1.31 |            1.3  |                1.35 | crps_game_model          | already the widest reading of the same data.                       |
| Prospect source head-to-head     | 2018–2022 overlap | per board season on matched support                   |         5 |       5 |              9 | fold-SIGN test (two-sided)                        | True            | 0.0625                | ⛔ ABOVE (0.0625 > 0.0100) — no effect of any size can pass | 3/5 (false-fire 0.500)  | 4/5 (false-fire 0.188)  |                      0.9977 |                           2.2  |                     1.8  |            2.2  |                2.2  | rank_ic_board            | calendar only: +1 overlapping season per year.                     |
| AAA-Statcast translation         | 2022– coverage    | leave-one-debut-cohort-out, ≥30 covered held-out rows |         3 |       3 |              4 | paired-t                                          | False           | n/a (not a sign test) | n/a                                                         | 2/3 (false-fire 0.500)  | 3/3 (false-fire 0.125)  |                      0.9772 |                           4.44 |                     4.44 |            3.3  |                3.3  | mae_pct_lift_translation | calendar only: one usable cohort per completed season.             |

- `MDE_sd_*` = the true per-fold lift, in units of the per-fold delta SD, that the FULL composite rule detects with 80% power against a 4-metric BH family. `<NA>`/`None` means the design cannot reach 80% power at ANY effect size — a materially different finding from "the effect must be large".
- `DSR_required_SR` is quoted at the asymptotic dispersion `V = 1/n_obs` so the columns are comparable across tiers; a real run's `V` is measured from its own trial field and is usually LARGER, which raises the bar further.

### 2b. ⭐ The field-size axis as a design table

The per-fold Sharpe a winner must post to clear `DSR ≥ 0.95`. **Read this before choosing a field, not after running it.**

|   folds |   2 arms |   4 arms |   7 arms |   12 arms |   20 arms |   28 arms |
|--------:|---------:|---------:|---------:|----------:|----------:|----------:|
|       3 |     3.11 |     4.44 |     5.36 |      6.16 |      6.85 |      7.28 |
|       5 |     1.38 |     1.8  |     2.09 |      2.33 |      2.54 |      2.67 |
|       8 |     0.93 |     1.18 |     1.35 |      1.49 |      1.62 |      1.69 |
|      11 |     0.74 |     0.94 |     1.07 |      1.18 |      1.27 |      1.33 |

The row that matters: at **3 folds** the bar roughly **doubles** going from a 4-arm family to a 28-arm grid. E7.9 ran 24–28 arms on 3 folds. That is the most demanding cell in the table, and it is where the program's *serving* models are evaluated.

## 3. The pre-registered practically-meaningful effect, per metric family

Readiness lock 3: a power table against an invented effect size answers a question nobody asked. Every row below is read off a decision the program has **already** made.

| family                   | unit                |   value | derivation                                                                                                                                                                                                                                                                                                                                                                   |
|:-------------------------|:--------------------|--------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| crps_game_model          | CRPS (runs)         |   0.02  | `promotion_gate.NOISE_FLOOR['crps']` — the program's PRE-EXISTING pre-registered noise floor for the runs targets. A margin below it is defined by the program itself as a TIE that ships nothing, so it IS the smallest serving-decision-changing effect. Not chosen here; read off the gate that already binds.                                                            |
| mae_pct_lift_translation | % held-out MAE lift |   1     | The SMALLEST lift that has ever actually changed a served MiLB→MLB configuration: E7.12 slice 1's `woba` ADD at +0.932%. Rounded UP to 1.0% so the bar is not set by the single luckiest shipped case. An empirical decision anchor from the record, not a convention.                                                                                                       |
| rank_ic_board            | Spearman rank-IC    |   0.04  | The median ACROSS-SEASON SD of a single source's own rank-IC on E7.14's cohort (0.041–0.048 over 7 sources). A between-source gap smaller than one source's own year-to-year wobble cannot justify re-weighting a board, so this is the ordering delta that would actually change a board decision. A noise property of the design, computable before any comparison is run. |
| nll_pricing              | NLL (nats)          |   0.01  | `promotion_gate.NOISE_FLOOR['nll']`, same standing as the CRPS row.                                                                                                                                                                                                                                                                                                          |
| brier_classification     | Brier               |   0.002 | `promotion_gate.NOISE_FLOOR['brier']`, same standing as the CRPS row.                                                                                                                                                                                                                                                                                                        |

These are **registered by MH2 now and are forward-effective**. Applied to the existing record they change only how a null is READ, never what it decided.

## 4. The mechanical null inventory

Corpus census: **75 markdown reports**, **270 JSON artifacts**, **251 story-prompt entries**. the JSON count includes per-Optuna-trial artifacts, which are trial records rather than verdicts and carry no gate to classify.

⚠️ **No silent caps.** 46 markdown reports state no fold count, PBO or DSR in their header and are therefore **not classifiable from the corpus at all** — they are counted here rather than dropped, because an inventory that reports only what it could parse looks like full coverage of a smaller corpus. Most predate the current header convention. Naming them is itself a finding: a report without its design line cannot have its null read by anyone, now or later.

**53 metric-level rows** carry enough stored per-fold detail to be classified fully; **29** more are classified at report-header resolution.

### 4a. State distribution

| null_state                   |   rows |
|:-----------------------------|-------:|
| POWER_LIMITED                |     29 |
| not-classifiable-from-header |     23 |
| GENUINE_ABSENCE              |      9 |
| UNKNOWN                      |      9 |
| SHIPPED (not a null)         |      6 |
| UNDEFINED                    |      4 |
| INACTIVE                     |      1 |
| DSR_UNREACHABLE              |      1 |

### 4b. What actually BOUND each run

The column the record was missing. A report says "DROP" and a reader infers the mechanism failed; often the run died on a multiplicity cutoff no effect size could clear, or on a statistic that was never computable.

| bound_by                                                           |   rows |
|:-------------------------------------------------------------------|-------:|
| unknown — the artifact records no fold structure                   |     32 |
| fold-consistency clause                                            |     11 |
| PBO                                                                |     10 |
| point estimate (best arm loses on average)                         |      9 |
| nothing — this arm SHIPPED under its own study's gate              |      6 |
| DSR                                                                |      6 |
| unattributed (the recorded stats do not identify a binding clause) |      3 |
| PBO UNDEFINED (<4 folds)                                           |      3 |
| n/a — the mechanism cannot act on this population                  |      1 |
| anchor/plumbing (BLOCKED — no verdict was reached)                 |      1 |

### 4c. The fully-classified rows

| study                  | metric        | verdict   |   n_folds |   n_arms |   pct_lift_vs_foil |       pbo |           dsr | bound_by                                              | null_state           | retest_trigger                                                                                                                                                                                      |
|:-----------------------|:--------------|:----------|----------:|---------:|-------------------:|----------:|--------------:|:------------------------------------------------------|:---------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| e7_15_h4 (pitcher)     | bb_pct        | DROP      |        11 |        3 |          0.127408  | 0.785714  |   0.441908    | fold-consistency clause                               | DSR_UNREACHABLE      | NOT rescuable by field size either — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric) |
| e7_15_h1 (batter)      | k_pct         | DROP      |        11 |        5 |         -0.0366593 | 0.628571  |   0.160942    | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h1 (batter)      | woba          | DROP      |        11 |        5 |         -0.0385185 | 0.442857  |   0.0242823   | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h2 (pitcher)     | bb_pct        | DROP      |        11 |        4 |         -0.106417  | 0.585714  |   0.189756    | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h4 (batter)      | bb_pct        | DROP      |        11 |        3 |         -0.896262  | 0.171429  |   0.178157    | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h4 (batter)      | iso           | DROP      |        11 |        3 |         -0.429154  | 0.128571  |   0.217962    | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h4 (batter)      | k_pct         | DROP      |        11 |        3 |         -0.0795516 | 0.228571  |   0.209508    | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h4 (batter)      | woba          | DROP      |        11 |        3 |         -0.307013  | 0.457143  |   0.2984      | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h4 (pitcher)     | gb_pct        | DROP      |        11 |        3 |         -0.503079  | 0.0428571 |   0.0357433   | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h4 (pitcher)     | hr_rate       | DROP      |        11 |        3 |         -1.33411   | 0         |   0.000220865 | point estimate (best arm loses on average)            | GENUINE_ABSENCE      |                                                                                                                                                                                                     |
| e7_15_h1 (pitcher)     | xwoba_against | DROP      |         4 |        5 |        nan         | 0.166667  | nan           | n/a — the mechanism cannot act on this population     | INACTIVE             | a population on which the mechanism can act at all                                                                                                                                                  |
| e7_12_slice1 (pitcher) | gb_pct        | DROP      |        11 |       14 |          0.30741   | 0         | nan           | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_12_slice1 (pitcher) | k_pct         | DROP      |        11 |       14 |          1.05738   | 0.414286  | nan           | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_12_slice1 (pitcher) | xwoba_against | DROP      |         4 |       14 |          1.33987   | 0.5       | nan           | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h1 (batter)      | bb_pct        | DROP      |        11 |        5 |          0.517301  | 0.514286  |   0.843985    | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h1 (batter)      | iso           | DROP      |        11 |        5 |          0.0516303 | 0.7       |   0.704483    | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h1 (pitcher)     | bb_pct        | DROP      |        11 |        5 |          0.298076  | 0.814286  |   0.48941     | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h1 (pitcher)     | gb_pct        | DROP      |        11 |        5 |          0.248201  | 0.642857  |   0.371654    | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h1 (pitcher)     | hr_rate       | DROP      |        11 |        5 |          0.104015  | 0.142857  |   0.602113    | DSR                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h1 (pitcher)     | k_pct         | DROP      |        11 |        5 |          0.116345  | 0.671429  |   0.85698     | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (batter)      | bb_pct        | DROP      |        11 |        4 |          0.255299  | 0.771429  |   0.63103     | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (batter)      | iso           | DROP      |        11 |        4 |          0.0359119 | 0.6       |   0.348569    | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (batter)      | k_pct         | DROP      |        11 |        4 |          0.0651861 | 0.485714  |   0.226544    | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (batter)      | woba          | DROP      |        11 |        4 |          0.0393167 | 0.485714  |   0.252738    | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (pitcher)     | gb_pct        | DROP      |        11 |        4 |          0.0490196 | 0.414286  |   0.334989    | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (pitcher)     | hr_rate       | DROP      |        11 |        4 |          0.147046  | 0.628571  |   0.800074    | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h2 (pitcher)     | k_pct         | DROP      |        11 |        4 |          0.0775204 | 0.985714  |   0.384834    | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (batter)      | bb_pct        | DROP      |        11 |        7 |          1.40384   | 0.0142857 |   0.606518    | DSR                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (batter)      | iso           | DROP      |        11 |        7 |          1.41832   | 0.0857143 |   0.657296    | DSR                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (batter)      | k_pct         | DROP      |        11 |        7 |          1.18278   | 0.171429  |   0.36036     | DSR                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (batter)      | woba          | DROP      |        11 |        7 |          0.84066   | 0.485714  |   0.498835    | PBO                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (pitcher)     | bb_pct        | DROP      |        11 |        7 |          0.438126  | 0.914286  |   0.158651    | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (pitcher)     | gb_pct        | DROP      |        11 |        7 |          1.20883   | 0         |   0.0783531   | DSR                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (pitcher)     | hr_rate       | DROP      |        11 |        7 |          0.106521  | 0.771429  |   0.0788192   | fold-consistency clause                               | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h3 (pitcher)     | k_pct         | DROP      |        11 |        7 |          1.71299   | 0.0571429 |   0.517616    | DSR                                                   | POWER_LIMITED        |                                                                                                                                                                                                     |
| e7_15_h4 (pitcher)     | k_pct         | DROP      |        11 |        3 |          1.47601   | 0.2       |   0.92671     | PBO                                                   | POWER_LIMITED        | +3 folds for the DSR gate — field size alone cannot rescue it at this dispersion                                                                                                                    |
| e7_15_h4 (pitcher)     | xwoba_against | DROP      |         4 |        3 |          1.09724   | 0.666667  |   0.693401    | fold-consistency clause                               | POWER_LIMITED        | +29 folds for the DSR gate — field size alone cannot rescue it at this dispersion                                                                                                                   |
| e7_12_slice1 (batter)  | bb_pct        | ADD       |        11 |       11 |          3.33678   | 0.0142857 | nan           | nothing — this arm SHIPPED under its own study's gate | SHIPPED (not a null) |                                                                                                                                                                                                     |
| e7_12_slice1 (batter)  | iso           | ADD       |        11 |       11 |          5.06007   | 0         | nan           | nothing — this arm SHIPPED under its own study's gate | SHIPPED (not a null) |                                                                                                                                                                                                     |
| e7_12_slice1 (batter)  | k_pct         | ADD       |        11 |       11 |          3.50047   | 0.3       | nan           | nothing — this arm SHIPPED under its own study's gate | SHIPPED (not a null) |                                                                                                                                                                                                     |
| e7_12_slice1 (batter)  | woba          | ADD       |        11 |       11 |          0.931908  | 0.271429  | nan           | nothing — this arm SHIPPED under its own study's gate | SHIPPED (not a null) |                                                                                                                                                                                                     |
| e7_12_slice1 (pitcher) | bb_pct        | ADD       |        11 |       14 |          3.11645   | 0.328571  | nan           | nothing — this arm SHIPPED under its own study's gate | SHIPPED (not a null) |                                                                                                                                                                                                     |
| e7_12_slice1 (pitcher) | hr_rate       | ADD       |        11 |       14 |          1.27627   | 0.171429  | nan           | nothing — this arm SHIPPED under its own study's gate | SHIPPED (not a null) |                                                                                                                                                                                                     |
| e7_15_h3 (pitcher)     | xwoba_against | BLOCKED   |         4 |        7 |          0.773212  | 0.833333  |   0.413699    | anchor/plumbing (BLOCKED — no verdict was reached)    | UNDEFINED            | fix or re-scope the blocking anchor, then re-run                                                                                                                                                    |
| milb_mle (batter)      | bb_pct        | ?         |       nan |      nan |        nan         | 0         |   0.989474    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (batter)      | iso           | ?         |       nan |      nan |        nan         | 0.0428571 |   0.679344    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (batter)      | k_pct         | ?         |       nan |      nan |        nan         | 0         |   0.999733    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (batter)      | woba          | ?         |       nan |      nan |        nan         | 0.242857  |   0.0324553   | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (pitcher)     | bb_pct        | ?         |       nan |      nan |        nan         | 0         |   0.946897    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (pitcher)     | gb_pct        | ?         |       nan |      nan |        nan         | 0         |   0.999962    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (pitcher)     | hr_rate       | ?         |       nan |      nan |        nan         | 0.9       |   0.130204    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (pitcher)     | k_pct         | ?         |       nan |      nan |        nan         | 0.0142857 |   0.785519    | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |
| milb_mle (pitcher)     | xwoba_against | ?         |       nan |      nan |        nan         | 1         |   0.02994     | unknown — the artifact records no fold structure      | UNKNOWN              | record the fold structure in the artifact, then re-classify                                                                                                                                         |

## 5. Three defects found in the shared power instruments

**Defect 1 — `h_harness.null_analysis`'s DSR extrapolation does not hold the effect size fixed, though its docstring says it does.** It resizes the winner's per-fold skill series with `np.resize`, i.e. TILING. Tiling preserves the population SD but the Sharpe is computed with `ddof=1`, so the resized series' Sharpe is inflated by ≈`√(n/(n−1))` — 4.9% at n=11 — and the partial final tile makes the inflation NON-MONOTONE in `k`, so the `next(...)` search can stop early on a wobble. Measured consequence on the live record: E7.15-H3 `bb_pct` recorded `folds_needed_DSR = 140`; holding the Sharpe genuinely fixed the answer is **372**. The re-test triggers were systematically **optimistic**. This is the THIRD defect in the same function, after the two E7.15-H3 found (an easier benchmark, and an `or 0` that collapsed UNREACHABLE into ALREADY-SATISFIED). **Fixed** — `null_analysis` now calls `cv_power.folds_to_clear_dsr`, which is closed-form and cannot drift from its own gate.

A **fourth facet of the same defect**, found while fixing it: the old search passed a single-element `trial_sharpes`, which `deflated_sharpe` rejects, so `V` fell back to `1/n_obs` **computed on the RESIZED length** — i.e. the deflation benchmark melted away as folds were added. The closed form branches as the gate does: `V` is held FIXED when it is a measured cross-trial dispersion, and scales as `1/k` only when it is the asymptotic fallback. Because the resize perturbs the series' skew/kurtosis too, the old error was **non-monotone in `k` and not signed** — which is why the corrections below run in both directions rather than uniformly one way.

**Every re-test trigger the record carries, recomputed.** These are the numbers other stories act on — a re-test trigger IS the output of an underpowered null:

| study              | metric        |   folds_have |   recorded folds_needed_DSR | corrected (closed form)   |
|:-------------------|:--------------|-------------:|----------------------------:|:--------------------------|
| e7_15_h1 (pitcher) | k_pct         |           11 |                          15 | 25                        |
| e7_15_h1 (pitcher) | bb_pct        |           11 |                          35 | UNREACHABLE at any n      |
| e7_15_h1 (pitcher) | hr_rate       |           11 |                          15 | 405                       |
| e7_15_h1 (pitcher) | gb_pct        |           11 |                          45 | UNREACHABLE at any n      |
| e7_15_h1 (batter)  | bb_pct        |           11 |                          35 | 28                        |
| e7_15_h1 (batter)  | iso           |           11 |                          37 | 95                        |
| e7_15_h2 (pitcher) | k_pct         |           11 |                         247 | UNREACHABLE at any n      |
| e7_15_h2 (pitcher) | hr_rate       |           11 |                          42 | 40                        |
| e7_15_h2 (pitcher) | gb_pct        |           11 |                         496 | UNREACHABLE at any n      |
| e7_15_h2 (batter)  | woba          |           11 |                        1231 | UNREACHABLE at any n      |
| e7_15_h2 (batter)  | k_pct         |           11 |                          38 | UNREACHABLE at any n      |
| e7_15_h2 (batter)  | bb_pct        |           11 |                          70 | 243                       |
| e7_15_h2 (batter)  | iso           |           11 |                         348 | UNREACHABLE at any n      |
| e7_15_h3 (pitcher) | k_pct         |           11 |                        2010 | UNREACHABLE at any n      |
| e7_15_h3 (batter)  | bb_pct        |           11 |                         140 | 372                       |
| e7_15_h3 (batter)  | iso           |           11 |                         120 | 166                       |
| e7_15_h4 (pitcher) | xwoba_against |            4 |                          17 | 33                        |

⚠️ **8 of these 17 are not "more seasons" at all but UNREACHABLE at any n** — the winner's Sharpe sits below its field's deflated benchmark, so `n` has nothing to scale, and every one of them carried a finite season count in the record. For two (`h1` pitcher `bb_pct` / `gb_pct`) E7.15's own prose correction had already reached that conclusion by another route, which is a useful agreement; the stored JSON still carries the old finite figures. **No verdict is affected — every one of these metrics DROPped either way — but the recorded re-test TRIGGERS were wrong, and this table supersedes them.**

The scale of the correction is the point: of the 17 triggers on record that move, **8 were dead ends reported as future re-tests** and the rest shift by factors of up to ~27× (h1 pitcher `hr_rate` 15 → 405). A re-test trigger is the entire actionable output of an underpowered null, so a systematically wrong one is not a cosmetic defect — it is the finding.

**Defect 2 — the same gate NAME is computed two different ways across the program.** `h_harness.dsr_report` passes the measured per-arm `trial_sharpes` and uses FOLDS as the observation series. `e7_9_train_serve_consistency` passes **neither** — its DSR series is per **year-month bucket** (~19 observations across 3 folds) and it omits `trial_sharpes`, so `V` falls back to the asymptotic `1/n_obs`. Both differences push the SAME way: months inside a season are not independent draws, so `√(n_obs−1)` is inflated ~3× (√18 vs √2), and an asymptotic `V` understates a real trial field's dispersion, understating `SR0`. ⇒ **E7.9's `DSR 0.842` is, if anything, GENEROUS**; at the honest 3-fold resolution the effect is even less detectable than recorded. That strengthens its "underpowered, not dead" reading rather than weakening it. Recorded here as a finding; E7.9's verdict is untouched.

**Defect 3 (H8) — the fold-consistency clause. Diagnosed and FIXED; see §6.**

## 6. H8 — the fold-count clause: diagnosis and fix

**Diagnosis.** Under the null the per-fold sign is a fair coin, so `fold_win_rate ≥ 0.60` fires with probability `P(Bin(n, ½) ≥ ⌈0.6n⌉)` — computed exactly rather than simulated:

|   folds |   legacy k |   legacy false-fire |   calibrated k |   calibrated false-fire |   calibrated equiv. rate |
|--------:|-----------:|--------------------:|---------------:|------------------------:|-------------------------:|
|       3 |          2 |              0.5    |              3 |                  0.125  |                    1     |
|       4 |          3 |              0.3125 |              4 |                  0.0625 |                    1     |
|       5 |          3 |              0.5    |              4 |                  0.1875 |                    0.8   |
|       6 |          4 |              0.3438 |              5 |                  0.1094 |                    0.833 |
|       7 |          5 |              0.2266 |              6 |                  0.0625 |                    0.857 |
|       8 |          5 |              0.3633 |              6 |                  0.1445 |                    0.75  |
|       9 |          6 |              0.2539 |              7 |                  0.0898 |                    0.778 |
|      10 |          6 |              0.377  |              7 |                  0.1719 |                    0.7   |
|      11 |          7 |              0.2744 |              8 |                  0.1133 |                    0.727 |
|      12 |          8 |              0.1938 |              8 |                  0.1938 |                    0.667 |

This reproduces E7.12-S6's simulated 0.4968 in closed form, and explains E7.12-S5 from the other side: a permuted-bucket placebo clearing the clause 9 times in 11 is unremarkable at ~27% per shot. **A clause whose meaning moves by a factor of two across the fold counts a program actually runs is not a gate; it is a fold-count-dependent tax.**

**Fix (`cv_power.fold_consistency_clause`).** Hold the FALSE-FIRE RATE fixed at `α = 0.2` and let the required win COUNT move with `n`. Three properties the legacy clause lacks:

1. **Stable meaning** — the null false-fire rate is ≤ α at every fold count instead of drifting 0.50 → 0.27.
2. **It says when it cannot be evaluated** — the smallest attainable rate at `n` folds is `2⁻ⁿ` (unanimity), so below `n = ⌈log₂(1/α)⌉` the clause is **UNDEFINED, not passed**, the same honesty `pbo_evaluable` already applies to CSCV.
3. **Weakly stricter than the legacy clause at every fold count** (pinned by a test) — so adopting it can only ever prevent a false ADD and can never manufacture one.

**Why α = 0.2, derived from DESIGN quantities and not from any arm's score** (NF1.8: a floor reverse-engineered from the answer is not a floor). Two independent derivations land on the same number: (a) at the fold counts this program runs (n = 3…11) the legacy clause's own operating range is 0.497 down to 0.274, and pinning the level at the TIGHTEST end makes the clause **no looser than it has ever been at any fold count** while making it uniform — a re-calibration, not a tightening; (b) 0.20 is already the program's "this much selection noise is tolerable" constant (`MAX_PBO`), and a consistency clause sitting INSIDE a composite gate that already carries a BH-FDR-corrected paired t should not also carry a primary-analysis alpha — that double-counts the same evidence.

**Verdict-neutrality, verified mechanically rather than asserted.** All 8 recorded ADDs in the corpus sit at fold-win rates 0.73 / 0.82 / 0.91 on 11 folds — i.e. 8, 9 and 10 wins — and the calibrated clause requires 8. **None is re-decided.**

**And the sensitivity that makes the choice visible rather than hidden:** at α = 0.10 the clause would require **9 of 11**, which would re-decide **4 of the 8 recorded ADDs** (E7.12-S1 `woba` and `k_pct`, E7.12-S2 `bb_pct` and `hr_rate`, all at 8/11). That is precisely why the α is stated and derived rather than assumed — and why MH2 does not retro-apply it.

## 7. ⭐ The single most actionable finding — the MLB game model's 3 folds are a WINDOW CHOICE, not a data limit

E7.9 ran on `2021-04-18 → 2026-07-27` = 6 seasons ⇒ 3 folds, and recorded the binding caveat *"3 purged folds. This can rule out a LARGE effect, not a small one."* Measured on the served store (`s3://…/lakehouse/feature_pregame_game_features/data.parquet`, 2026-08-01):

| season | rows | mean non-null coverage of the served 13-col `total_runs/post_lineup` contract |
|---:|---:|---:|
| 2015 | 2,429 | 0.449 |
| 2016 | 2,428 | 0.828 |
| 2017 | 2,430 | 0.827 |
| 2018 | 2,431 | 0.834 |
| 2019 | 2,429 | 0.829 |
| 2020 | 898 | 0.885 |
| 2021 | 2,429 | 0.901 |
| 2022 | 2,430 | 0.906 |
| 2023 | 2,430 | 0.939 |
| 2024 | 2,429 | 0.982 |
| 2025 | 2,430 | 0.982 |
| 2026 | 1,690 | 0.979 |

The store holds **26,883 rows over 12 seasons**. E7.9 used 11,858 rows over 6. A **2016–2026** window (dropping 2015, whose contract coverage is only 0.449, and keeping the short 2020 season) is **11 seasons ⇒ 8 folds** at ≥0.827 contract coverage — **8 folds vs 3, available TODAY, with no calendar wait.**

What that buys, at the design level (required per-fold Sharpe to clear `DSR ≥ 0.95`, asymptotic `V`):

| design                                                  |   folds |   arms |   required per-fold SR |
|:--------------------------------------------------------|--------:|-------:|-----------------------:|
| as E7.9 ran it — 3 folds × 28 arms                      |       3 |     28 |                   7.28 |
| wider window, same field — 8 folds × 28 arms            |       8 |     28 |                   1.69 |
| wider window + pre-registered family — 8 folds × 4 arms |       8 |      4 |                   1.18 |

⚠️ **Stated honestly, and NOT acted on here.** This is a *feasibility* measurement, not a re-run and not a promise: (a) 2016–2020 sit at ~0.83 contract coverage against ~0.98 for 2024+, so the earlier folds are thinner and imputation carries more of them; (b) 2020 is a **898-game COVID season** — structurally atypical, and whether it enters as a fold is a design decision that must be pre-registered, not discovered; (c) the offline matrix is **not point-in-time** (E7.9's own caveat), and widening the window widens that exposure too. The deliverable is that E7.9's `plus_eb`-on-`total_runs` follow-up is **reachable now via the window and the field size**, not only by waiting for seasons — which is the difference between a live re-test and a 2029 calendar note.

## 8. The rule for reading a §0.5 null (the durable artifact)

Landed in the §0.5 canon (`CLAUDE.md` + `edge_program_implementation_guide.md`). Restated here so this report is self-contained:

> **A §0.5 null is in one of SEVEN states, and a report must name which.** Two states do not cover the cases, and four of the seven are routinely mislabelled as "the mechanism failed".

| state | test | remedy | do NOT |
|---|---|---|---|
| **INACTIVE** | the mechanism has no rows it can move (zero transitions / zero coverage) | a different population | hunt for a defect; wait for seasons |
| **UNKNOWN** | the artifact records no fold structure — unread, not underpowered | record the design in the artifact | classify it at all |
| **UNDEFINED** | a required stat was not COMPUTABLE (PBO < 4 folds; a consistency clause whose α is unattainable), or the run was anchor-BLOCKED | more folds / fix the anchor | record it as a failed gate |
| **GENUINE ABSENCE** | the best arm loses to the foil ON AVERAGE | none — do not re-test | state a re-test trigger |
| **DSR-UNREACHABLE** | beats the foil, but `SR ≤ SR0` in THIS field ⇒ no `n` ever clears | a SMALLER pre-registered field | report it as "needs N more seasons" |
| **POWER-LIMITED** | every gate reachable, MDE > the meaningful effect | more folds and/or fewer arms — state which, in the unit that grows | call it dead |
| **TRUSTWORTHY DEAD** | MDE ≤ the pre-registered meaningful effect, and nothing showed | none — the mechanism is ruled out at the size that would matter | over-claim beyond that size |

And the two axis rules the program did not have:

1. **A FAMILY GETS ITS OWN PRE-REGISTERED FIELD.** Bundling unrelated mechanisms into one bake-off taxes a real finding with their multiplicity — and the tax is bigger than it looks, because `SR0 = √V · z(N)` moves through TWO channels: the trial COUNT `N` *and* the cross-trial Sharpe DISPERSION `V`, which the far-away arms inflate. On E7.15-H3 the dispersion channel is the dominant one (`V` falls ~65× going 7 arms → 2, against ~2.5× for `z`). ⇒ "just run fewer arms" is the wrong lesson; **run a coherent family**.
2. **STATE THE MARGIN IN THE UNIT THAT GROWS, AND SAY WHETHER IT IS REACHABLE NOW.** Folds, seasons, cohorts, rows — never p-decimals. A trigger reachable by a WIDER WINDOW or a SMALLER FIELD is a live re-test; only a trigger that needs calendar time is a future note. §7 is the worked example: the same null read one way is "wait for 2029" and read correctly is "re-runnable this week".
