# NF-INJ2b — re-fit the ordering learner on a per-game RATE target

**VERDICT: NULL** — the arm does not restore coherence, which is the correctness constraint the whole story exists to satisfy — §6 branch 3. `best_alpha = 0`. Generated 2026-08-29T21:38:54Z in 48.5s.

> Pre-registration: `nf_inj2b_preregistration.md` (committed before any arm was scored; AMENDMENT 1 filed before any scoring). ⛔ Not edited by this run — E2.1-r.

> 🔒 DEPLOY-HELD: `nf_inj2b_rate_ordering.SERVED_ARM` is `None`, so the board serves NF-INJ2's policy (`incumbent`). Nothing here serves until the PM records a disposition.


## 1. The declared field

Folds **2019–2025** (7), inherited from NF1.5 stage-1 `score_from` — not chosen here. Declared field **10** arms; degenerates `mvp1_null`, `random_order`; reference `incumbent`.

| arm | target | assignment | CRPS | MAE | cov80 | tier ρ | coherence viol./fold | folds w/ ≥1 |
|---|---|---|---|---|---|---|---|---|
| oracle_incumbent | — | oracle | 18.3783 | 23.0032 | 0.9811 | 0.9981 | 21.0000 | 7/7 |
| oracle_feasibility_clamp | — | oracle | 18.5021 | 23.3939 | 0.9796 | 0.9933 | 1.8571 | 7/7 |
| oracle_stratified | — | oracle | 20.2010 | 26.7027 | 0.9720 | 0.9859 | 10.1429 | 7/7 |
| oracle_points_rate_permute | — | oracle | 21.4692 | 29.1842 | 0.9636 | 0.8944 | 0.4286 | 3/7 |
| oracle_rate_refit | — | oracle | 21.4692 | 29.1842 | 0.9636 | 0.8944 | 0.4286 | 3/7 |
| oracle_rate_refit_reselect | — | oracle | 21.4692 | 29.1842 | 0.9636 | 0.8944 | 0.4286 | 3/7 |
| oracle_points_rate_stratified | — | oracle | 21.5314 | 29.4966 | 0.9620 | 0.8969 | 0.5714 | 4/7 |
| oracle_rate_refit_stratified | — | oracle | 21.5314 | 29.4966 | 0.9620 | 0.8969 | 0.5714 | 4/7 |
| stratified | points | point_within_strata | 26.0576 | 37.1596 | 0.9019 | 0.5584 | 8.5714 | 7/7 |
| points_rate_permute | points | rate_by_score | 26.1882 | 37.6075 | 0.9063 | 0.5241 | 0.2857 | 1/7 |
| points_rate_stratified | points | rate_within_strata | 26.2051 | 37.6015 | 0.9056 | 0.5237 | 0.2857 | 1/7 |
| rate_refit_stratified | rate | rate_within_strata | 26.2442 | 37.6658 | 0.9041 | 0.5248 | 0.2857 | 2/7 |
| rate_refit | rate | rate_by_score | 26.2755 | 37.7249 | 0.9058 | 0.5213 | 0.1429 | 1/7 |
| rate_refit_reselect | rate_reselect | rate_by_score | 26.2828 | 37.7287 | 0.9071 | 0.5134 | 0.1429 | 1/7 |
| feasibility_clamp | points | point_by_score_clamped | 26.3486 | 37.4490 | 0.8950 | 0.5553 | 1.1429 | 4/7 |
| incumbent | points | point_by_score | 26.5028 | 37.6858 | 0.8953 | 0.5555 | 19.1429 | 7/7 |
| mvp1_null | — | identity | 27.5071 | 39.5893 | 0.8923 | 0.3913 | 0.0000 | 0/7 |
| random_order | — | random | 45.3578 | 62.8817 | 0.7456 | 0.1447 | 36.0000 | 7/7 |


⛔ **CRPS selects. MAE never does** — the target is skewed and the low-availability cohort is exactly where the conditional median sits near the floor (NF-D11 / NF-D14). Disclosed, not used.


⚠️ **The coherence column is a PRECONDITION, ⛔ not a discriminator.** The pre-registration says so in advance: the `rate_*` arms satisfy it by construction, so it must not be presented as evidence that they beat anything. It is reported for EVERY arm — a constraint a degenerate satisfies is fine (the metric then eliminates it); a *criterion* a degenerate WINS is fatal (NF1.8).


⭐ **AND THE PRE-REGISTRATION'S "by construction" IS REFUTED BY THIS COLUMN, at the edge.** The value is a per-fold MEAN, and no arm reaches exactly 0: `rate_refit` carries one violating player in ONE of seven folds. The `coherence_restored` gate demands `= 0`, so it reads **False for every arm in the field** — which is why the injected-effect control below can only return `BLIND`, and it is a fact about a deterministic constraint, ⛔ not about the family's statistical sensitivity. Recorded as it fell (E2.1-r); the remedy is a successor whose coherence clause declares its attribution and its tolerance FORWARD.


## 2. Could the re-fit ACT? (NF-D20 — counted, never assumed)

The pre-registration §1b predicted this table before any scoring. A cell the re-fit cannot move is UNINFORMATIVE about the hypothesis, ⛔ never a pass.

| position | target | folds active | max abs Δscore | min ρ vs points-fit | can act |
|---|---|---|---|---|---|
| QB | rate | 7/7 | 0.876747 | 0.942362 | True |
| QB | rate_reselect | 7/7 | 3.224539 | 0.723962 | True |
| RB | rate | 0/7 | 0.000000 | 1.000000 | False |
| RB | rate_reselect | 5/7 | 2.799537 | 0.943233 | False |
| TE | rate | 7/7 | 0.199015 | 0.983239 | True |
| TE | rate_reselect | 7/7 | 0.750929 | 0.866265 | True |
| WR | rate | 7/7 | 1.021714 | 0.982850 | True |
| WR | rate_reselect | 7/7 | 1.021714 | 0.971652 | True |


## 3. The winner vs the incumbent

Winner **`stratified`** (lowest pooled CRPS among the declared arms that are neither a pre-registered degenerate nor the reference). Mean CRPS lift **0.4452** over 7 folds, winning **7/7**. Tie band ±0.0837 (the per-fold SE of the winner's own lift — a dispersion quantity fixed by the design, ⛔ not a threshold chosen to reach a verdict).

| fold | lift |
|---|---|
| 2019 | 0.3286 |
| 2020 | 0.0696 |
| 2021 | 0.4391 |
| 2022 | 0.5976 |
| 2023 | 0.4959 |
| 2024 | 0.4055 |
| 2025 | 0.7803 |


## 4. The matched pairs — WHICH factor moved it (NF-D15 g′ / NF-W7e)

| pair | factor | Δ CRPS | folds + | one-sided p | isolates |
|---|---|---|---|---|---|
| rate_refit − points_rate_permute | TARGET | -0.0873 | 1/7 | 0.9767 | TARGET — the fit target is the only difference |
| rate_refit_stratified − points_rate_stratified | TARGET | -0.0391 | 1/7 | 0.9441 | TARGET, inside the stratified assignment |
| rate_refit_stratified − rate_refit | ASSIGNMENT | 0.0313 | 4/7 | 0.2971 | ASSIGNMENT — the stratification is the only difference |
| stratified − incumbent | ASSIGNMENT | 0.4452 | 7/7 | 0.0009 | ASSIGNMENT in POINT space — the point-space control |


### The 2×2 interaction

| quantity | value |
|---|---|
| target_effect_within_by_score | -0.0873 |
| target_effect_within_stratified | -0.0391 |
| assignment_effect_within_points | -0.0169 |
| assignment_effect_within_rate | 0.0313 |
| joint_effect | -0.0560 |
| sum_of_halves | -0.1042 |
| interaction | 0.0482 |


NF-W7e: two halves that each move the metric are NOT additive. A large interaction means the halves are rescuing (or cancelling) each other, and a MARGINAL delta measured with the other half at one setting is not a measurement of the other setting. ⛔ Never recombine channels measured conditionally — the joint cell is scored here, not inferred.


## 5. Gates

| gate | value | bar | verdict |
|---|---|---|---|
| PBO (FIELD-level, eligible = the declared field) | 0.0857 | < 0.2 | True |
| DSR (binding: degenerates AND reference ∉ V) | 0.9325 | ≥ 0.95 | False |
| DSR (reference INCLUDED in V — reported beside it) | 0.9281 | — | — |
| DSR (whole field) | 0.0000 | — | — |
| fold consistency (calibrated — MH2 H8) | 7 | ≥ 6 wins (false-fire 0.062; the raw 0.60 rate would need 5 at false-fire 0.227) | True |
| BH-FDR (SINGLE hypothesis — declared §3) | 0.0009 | ≤ 0.1 | True |
| ordering not regressed (draftable tier) | {"QB": [0.4894, 0.4807], "RB": [0.6551, 0.6564], "WR": [0.5771, 0.5745], "TE": [0.5119, 0.5105]} | no BH-significant regression | True |
| ordering — full population (disclosed) | {"QB": [0.6998, 0.6497], "RB": [0.7307, 0.7046], "WR": [0.7115, 0.6888], "TE": [0.6602, 0.5594]} | ρ ≥ incumbent | True |
| coherence restored | 9 | = 0 | False |
| degenerates lose | {"mvp1_null": 27.5071, "random_order": 45.3578} | all lose | True |
| own-form peeking ceiling | 20.2010 | ACTIVE | True |


⚠️ this BH protects against a false REFUSAL, i.e. it is directionally GENEROUS to the arm. Declared in the pre-registration §3, so the generosity is on the record rather than discovered by a reader.


NF1.8 triad beside PBO — a rank statistic alone cannot tell an unstable pick from a tied one: flip distribution `{"stratified": 0.7429, "points_rate_permute": 0.2, "points_rate_stratified": 0.0286, "rate_refit_stratified": 0.0286}`, Bailey performance degradation **0.000%**, contender spread **0.4452** against a whole-field spread of **19.3002** (the whole-field figure contains this field's own declared degenerates, so it measures the degenerates — MH2 / NF1.8).


Trial Sharpes: `{"incumbent": 0.0, "points_rate_permute": 0.5983, "rate_refit": 0.3793, "points_rate_stratified": 0.5075, "rate_refit_stratified": 0.4076, "rate_refit_reselect": 0.3684, "stratified": 2.0101, "feasibility_clamp": 0.8691, "mvp1_null": -1.3093, "random_order": -10.7846}`. `V` is measured over `feasibility_clamp`, `points_rate_permute`, `points_rate_stratified`, `rate_refit`, `rate_refit_reselect`, `rate_refit_stratified`, `stratified` — the pre-registration §3 convention: the two degenerates AND the `incumbent` REFERENCE arm are excluded (MH2.1 (a): a structural 0.0 inflates a small family's dispersion), while `n_trials` stays at the full declared 10.


## 6. The INJECTED-EFFECT POSITIVE CONTROL (pre-registered §3)

**`BLIND`** at an injected **+0.75 CRPS** and **+0.05 tier-ρ** per fold on every non-degenerate, non-reference arm.


not one arm clears even the METRIC gates at an injected effect of 0.75 — this family would return a null for a real, large effect, so a null from it is free (NF1.7 (a): a check that cannot fire is not a check that passed).


* metric gates: `beats_incumbent`, `bh_fdr`, `coherence_restored`, `degenerates_lose`, `fold_consistency`, `ordering_not_regressed`, `own_form_ceiling`
* deflation-class gates present: `dsr`
* survivors: `none`  ·  metric survivors: `none`  ·  deflation-blocked: `none`
* null-control leg ran: **True**; survivors on the NO-EFFECT payload: `[]` (any survivor here would make the family VACUOUS and every reading of this study meaningless)


⭐ **`field_level_gates_applied_per_arm` = `[]`.** EMPTY is the affirmative finding the pre-registration predicted: this study's registered per-arm gate table deliberately carries NO field-level statistic as a per-arm pass/fail. CSCV/PBO has one value for the whole field and answers whether the SELECTION overfit; reading it per-arm converts "the search was unstable" into "this arm failed", which is not a statement the statistic makes (PLAT-CVP1 defect 4(a)).


Field-level PBO, reported BESIDE the control because it is deliberately outside the per-arm table: real **0.0857** → injected **0.0857** (the injection moved the in-sample winner on **0/35** splits; injection inert: **True**).

⚠️ MEASURED STRUCTURALLY INERT: the injection moved the in-sample winner on 0/35 splits, so the field-level PBO under injection is a property of the UNIFORM ADDITIVE injection (CSCV is rank-based; a common shift cannot re-order the treated arms among themselves), ⛔ NOT evidence about this field. MLB-HV2-1's PBO rose because its injection was a bias on the DATA that each arm responded to differently — a different object. Reported because a mechanism that CANNOT act is a finding, not an omission (NF1.9 / NF-D20).


## 7. Anchors

- Degenerates scored every run and READ, ⛔ not reasoned about: `{"mvp1_null": 27.5071, "random_order": 45.3578}` against the winner's **26.0576** ⇒ every degenerate loses: **True**.


- Own-form peeking ceiling (one PER FORM — the forms NEST, so a single field-wide ceiling would veto a legitimately better nested form, NF-D16 g‴): **20.2010**, gap **5.8566**, respected **True**. ACTIVE


⭐ A note a reader would otherwise read as a bug: the oracle REPLACES the score, which is this story's treated factor — so two arms differing only in the fit target share ONE ceiling. That is correct: the ceiling is a property of the FORM, not of the target.


## 8. The JOINT success criterion (the spec's three legs)

| leg | value | note |
|---|---|---|
| (a) ordering holds at every draftable tier | True | not a target-re-fit arm — the activity question does not apply |
| (b) give-back removed / not reintroduced | True | arm 27.85% vs incumbent 82.70% |
| (c) NF-INJ1 violations → 0 | False | attributable violating players: 7 |
| **ALL THREE** | **False** |  |


## 9. The 2026 board — the CURRENT served (flip-board) vintage

Built off `generated_at` **2026-08-29T21:36:59.38158**. Injury-capped cohort n=**29** (load_forward_roster_status(2026).proj_status ∈ ['NFI', 'PUP', 'RES', 'SUS'] — the cap's own input).


**Baseline vintage, verified from INSIDE the served artifact before any measurement** (the NF-INJ3b-SHIP lesson): local MVP-1 `2026-08-29 21:36:59.381588+00:00` vs the SERVED board `2026-08-29T14:19:08.047877+00:00` = **7.30h** against a 48.0h bar; the served board's own injury-input verdict is **OK** (0.8h). Injury-games stamp on the served board: **FLIPPED_AND_MOVED**; adopted reported-absence overrides: **0**.


**Reproduction pin:** the incumbent arm rebuilt through this story's code matches the SERVED artifact to **40.6** over 797 rows (tolerance 0.05) ⇒ **False**. the incumbent arm rebuilt through this story's code vs the PUBLISHED 2026 artifact. If this does not hold, every arm delta is measured against a board nobody is served (the CLV / NF-INJ1 stale-vintage trap).

| arm | target | impossible rows | …attributable | give-back % | median ratio | ρ(games, ratio) | clamp hi/lo |
|---|---|---|---|---|---|---|---|
| incumbent | points | 10 | 9 | 82.70 | 1.9848 | -0.2598 | 15/26 |
| points_rate_permute | points | 1 | 0 | -16.31 | 0.9153 | 0.1781 | 1/7 |
| rate_refit | rate | 1 | 0 | -7.85 | 1.0000 | 0.1737 | 0/6 |
| points_rate_stratified | points | 1 | 0 | -8.02 | 1.0069 | 0.0433 | 0/5 |
| rate_refit_stratified | rate | 1 | 0 | 0.41 | 1.0432 | 0.0663 | 0/5 |
| rate_refit_reselect | rate_reselect | 1 | 0 | -10.49 | 0.8979 | 0.2352 | 0/2 |
| stratified | points | 8 | 7 | 27.85 | 1.4197 | -0.0696 | 4/12 |
| feasibility_clamp | points | 4 | 3 | 82.70 | 1.9848 | -0.2562 | 13/26 |
| mvp1_null | points | 1 | 0 | 0.00 | 1.0000 | — | 0/0 |
| random_order | points | 33 | 32 | 120.18 | 3.4973 | -0.6000 | 148/159 |


⭐ **ATTRIBUTION BY CONTROL, not by scope declaration.** violations also produced by `mvp1_null` (the ordering step OFF) are subtracted — a defect present with the mechanism disabled is not caused by the mechanism


## 10. Null classification

```json
"NullVerdict(state='POWER_LIMITED', reason='`crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 8 folds against 7 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.', retest_trigger=\"+1 folds for the DSR gate. On field size \u2014 \u26d4 **NOT A REMEDY \u2014 ARITHMETIC ONLY.** The effect clears only in a field of \u22647 arm(s), which is BELOW the declared family of 10. Shrinking a field below what was pre-registered means dropping arms BECAUSE THEY LOST \u2014 the very selection bias DSR exists to deflate, and on MH2.2's `bb_pct` that move bought its whole apparent gain through a 19,938\u00d7 collapse in the cross-trial dispersion `V`, not through honest multiplicity. A smaller field is a legitimate remedy ONLY if that smaller family was itself declared in advance on MECHANISTIC grounds. \u21d2 the \u22647 figure is reported as a DESIGN QUANTITY, never as advice.\", folds_have=7, folds_needed=8, extra_seasons=1, max_field_size=7, detail={'n_folds': 7, 'n_arms': 10, 'observed_sr': 2.0101, 'sr0': 0.9276, 'var_trials_sr': 0.3470686023809524, 'degenerates_excluded_from_v': True, 'var_trials_sr_with_degenerates': 13.227076569333333, 'v_inflation_factor_from_degenerates': 38.1108, 'lockstep_closed': False, 'lockstep_gap': 1.0824290981766838, 'lockstep_sign_invariant': True, 'declared_field_size': 10, 'declared_field_size_source': 'stated', 'field_remedy_admissible': False, 'pbo': 0.0857, 'pbo_gate': 0.2, 'pbo_pass': True, 'pbo_application': 'field', 'pbo_application_admissible': True}, field_remedy_admissible=False, pbo_application_admissible=True, lockstep=LockstepReport(closed=False, sr=2.0100647724932577, sr0=0.9276356743165739, gap=1.0824290981766838, sign_invariant=True, dsr_falls_as_design_sharpens=False, ladder=({'dispersion_factor': 1.0, 'winner_sharpe': 2.0100647724932577, 'sr0': 0.9276356743165739, 'sr_minus_sr0': 1.0824290981766838, 'dsr': 0.9364531116540097}, {'dispersion_factor': 0.5, 'winner_sharpe': 4.020129544986515, 'sr0': 1.8552713486331478, 'sr_minus_sr0': 2.1648581963533675, 'dsr': 0.9607728169208548}, {'dispersion_factor': 0.25, 'winner_sharpe': 8.04025908997303, 'sr0': 3.7105426972662956, 'sr_minus_sr0': 4.329716392706735, 'dsr': 0.9669121073902214}, {'dispersion_factor': 0.1, 'winner_sharpe': 20.100647724932575, 'sr0': 9.276356743165739, 'sr_minus_sr0': 10.824290981766836, 'dsr': 0.9686162365140565}, {'dispersion_factor': 0.01, 'winner_sharpe': 201.00647724932577, 'sr0': 92.76356743165738, 'sr_minus_sr0': 108.24290981766839, 'dsr': 0.9689365115819538})))"
```


## 11. Reading, against the pre-registration's §6

- **NULL** — the arm does not restore coherence, which is the correctness constraint the whole story exists to satisfy — §6 branch 3.


- DSR reading: winner per-fold Sharpe **2.0101** against the declared field's benchmark SR0 **0.9276** ⇒ **REACHABLE**. a positive SR − SR0 gap exists; more folds would scale it


- The DSR 2×2 is **not reported**: the most extreme trial Sharpe IS the winner — a DSR reached by deleting it would be inadmissible (NF-W7h), so no trimmed figure is reported


- ⛔ **NO "more data" re-test trigger** is published. a negative point estimate is not rescued by n (NF-D15 g″)

