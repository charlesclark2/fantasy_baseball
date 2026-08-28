# NF-INJ2b — re-fit the ordering learner on a per-game RATE target

**VERDICT: UNDEFINED** — a pre-registered gate was NOT COMPUTABLE at this fold count (bh_fdr, dsr, fold_consistency, ordering_not_regressed, pbo_field_level) — ⛔ not failed, not passed, and ⛔ not shippable. `best_alpha = 0`. Generated 2026-08-28T03:26:56Z in 24.4s.

> Pre-registration: `nf_inj2b_preregistration.md` (committed before any arm was scored; AMENDMENT 1 filed before any scoring). ⛔ Not edited by this run — E2.1-r.

> 🔒 DEPLOY-HELD: `nf_inj2b_rate_ordering.SERVED_ARM` is `None`, so the board serves NF-INJ2's policy (`incumbent`). Nothing here serves until the PM records a disposition.


## 1. The declared field

Folds **2024–2025** (2), inherited from NF1.5 stage-1 `score_from` — not chosen here. Declared field **10** arms; degenerates `mvp1_null`, `random_order`; reference `incumbent`.

| arm | target | assignment | CRPS | MAE | cov80 | tier ρ | coherence viol. |
|---|---|---|---|---|---|---|---|
| oracle_feasibility_clamp | — | oracle | 15.8954 | 18.5711 | 0.9790 | 0.9985 | 1 |
| oracle_incumbent | — | oracle | 15.9450 | 18.5293 | 0.9790 | 0.9992 | 16 |
| oracle_stratified | — | oracle | 17.1212 | 21.7215 | 0.9752 | 0.9958 | 6 |
| oracle_points_rate_stratified | — | oracle | 18.1022 | 23.9515 | 0.9670 | 0.9337 | 0 |
| oracle_rate_refit_stratified | — | oracle | 18.1022 | 23.9515 | 0.9670 | 0.9337 | 0 |
| oracle_points_rate_permute | — | oracle | 18.2859 | 23.9126 | 0.9655 | 0.9304 | 0 |
| oracle_rate_refit | — | oracle | 18.2859 | 23.9126 | 0.9655 | 0.9304 | 0 |
| oracle_rate_refit_reselect | — | oracle | 18.2859 | 23.9126 | 0.9655 | 0.9304 | 0 |
| rate_refit | rate | rate_by_score | 23.1707 | 33.5591 | 0.9079 | 0.3960 | 0 |
| rate_refit_stratified | rate | rate_within_strata | 23.1844 | 33.4698 | 0.9011 | 0.4029 | 0 |
| points_rate_stratified | points | rate_within_strata | 23.1963 | 33.4800 | 0.9034 | 0.4026 | 0 |
| rate_refit_reselect | rate_reselect | rate_by_score | 23.1986 | 33.5630 | 0.9048 | 0.3816 | 0 |
| points_rate_permute | points | rate_by_score | 23.2030 | 33.5876 | 0.9042 | 0.3973 | 0 |
| stratified | points | point_within_strata | 23.5649 | 33.6855 | 0.8905 | 0.4280 | 6 |
| feasibility_clamp | points | point_by_score_clamped | 23.9738 | 34.1288 | 0.8846 | 0.4231 | 0 |
| incumbent | points | point_by_score | 24.1854 | 34.4342 | 0.8846 | 0.4231 | 14 |
| mvp1_null | — | identity | 24.2773 | 34.7500 | 0.8954 | 0.3137 | 0 |
| random_order | — | random | 43.7884 | 60.1778 | 0.7317 | 0.0712 | 31 |


⛔ **CRPS selects. MAE never does** — the target is skewed and the low-availability cohort is exactly where the conditional median sits near the floor (NF-D11 / NF-D14). Disclosed, not used.


⚠️ **The coherence column is a PRECONDITION, ⛔ not a discriminator.** The pre-registration says so in advance: the `rate_*` arms satisfy it by construction, so it must not be presented as evidence that they beat anything. It is reported for EVERY arm — a constraint a degenerate satisfies is fine (the metric then eliminates it); a *criterion* a degenerate WINS is fatal (NF1.8).


## 2. Could the re-fit ACT? (NF-D20 — counted, never assumed)

The pre-registration §1b predicted this table before any scoring. A cell the re-fit cannot move is UNINFORMATIVE about the hypothesis, ⛔ never a pass.

| position | target | folds active | max abs Δscore | min ρ vs points-fit | can act |
|---|---|---|---|---|---|
| QB | rate | 2/2 | 0.876747 | 0.962163 | True |
| QB | rate_reselect | 2/2 | 2.742022 | 0.725811 | True |
| RB | rate | 0/2 | 0.000000 | 1.000000 | False |
| RB | rate_reselect | 2/2 | 1.390275 | 0.965019 | True |
| TE | rate | 2/2 | 0.106308 | 0.989759 | True |
| TE | rate_reselect | 2/2 | 0.574017 | 0.863205 | True |
| WR | rate | 2/2 | 0.476417 | 0.993830 | True |
| WR | rate_reselect | 2/2 | 0.985425 | 0.972150 | True |


## 3. The winner vs the incumbent

Winner **`rate_refit`** (lowest pooled CRPS among the declared arms that are neither a pre-registered degenerate nor the reference). Mean CRPS lift **1.0148** over 2 folds, winning **2/2**. Tie band ±0.0127 (the per-fold SE of the winner's own lift — a dispersion quantity fixed by the design, ⛔ not a threshold chosen to reach a verdict).

| fold | lift |
|---|---|
| 2024 | 1.0275 |
| 2025 | 1.0020 |


## 4. The matched pairs — WHICH factor moved it (NF-D15 g′ / NF-W7e)

| pair | factor | Δ CRPS | folds + | one-sided p | isolates |
|---|---|---|---|---|---|
| rate_refit − points_rate_permute | TARGET | 0.0323 | 2/2 | — | TARGET — the fit target is the only difference |
| rate_refit_stratified − points_rate_stratified | TARGET | 0.0118 | 1/2 | — | TARGET, inside the stratified assignment |
| rate_refit_stratified − rate_refit | ASSIGNMENT | -0.0138 | 1/2 | — | ASSIGNMENT — the stratification is the only difference |
| stratified − incumbent | ASSIGNMENT | 0.6205 | 2/2 | — | ASSIGNMENT in POINT space — the point-space control |


### The 2×2 interaction

| quantity | value |
|---|---|
| target_effect_within_by_score | 0.0323 |
| target_effect_within_stratified | 0.0118 |
| assignment_effect_within_points | 0.0067 |
| assignment_effect_within_rate | -0.0138 |
| joint_effect | 0.0185 |
| sum_of_halves | 0.0390 |
| interaction | -0.0205 |


NF-W7e: two halves that each move the metric are NOT additive. A large interaction means the halves are rescuing (or cancelling) each other, and a MARGINAL delta measured with the other half at one setting is not a measurement of the other setting. ⛔ Never recombine channels measured conditionally — the joint cell is scored here, not inferred.


## 5. Gates

| gate | value | bar | verdict |
|---|---|---|---|
| PBO (FIELD-level, eligible = the declared field) | — | < 0.2 | UNDEFINED (not computable at this n — ⛔ not a failure) |
| DSR (binding: degenerates AND reference ∉ V) | — | ≥ 0.95 | UNDEFINED (not computable at this n — ⛔ not a failure) |
| DSR (reference INCLUDED in V — reported beside it) | — | — | — |
| DSR (whole field) | — | — | — |
| fold consistency (calibrated — MH2 H8) | 2 | ≥ None wins (false-fire nan; the raw 0.60 rate would need 2 at false-fire 0.250) | UNDEFINED (not computable at this n — ⛔ not a failure) |
| BH-FDR (SINGLE hypothesis — declared §3) | — | ≤ 0.1 | UNDEFINED (not computable at this n — ⛔ not a failure) |
| ordering not regressed (draftable tier) | {"QB": [0.1813, 0.3526], "RB": [0.6411, 0.6471], "WR": [0.3799, 0.3696], "TE": [0.3816, 0.323]} | no BH-significant regression | UNDEFINED (not computable at this n — ⛔ not a failure) |
| ordering — full population (disclosed) | {"QB": [0.7754, 0.6442], "RB": [0.77, 0.7345], "WR": [0.7571, 0.7396], "TE": [0.763, 0.6341]} | ρ ≥ incumbent | True |
| coherence restored | 0 | = 0 | True |
| degenerates lose | {"mvp1_null": 24.2773, "random_order": 43.7884} | all lose | True |
| own-form peeking ceiling | 18.2859 | ACTIVE | True |


⚠️ this BH protects against a false REFUSAL, i.e. it is directionally GENEROUS to the arm. Declared in the pre-registration §3, so the generosity is on the record rather than discovered by a reader.


NF1.8 triad beside PBO — a rank statistic alone cannot tell an unstable pick from a tied one: flip distribution `{}`, Bailey performance degradation **—%**, contender spread **1.0147** against a whole-field spread of **20.6177** (the whole-field figure contains this field's own declared degenerates, so it measures the degenerates — MH2 / NF1.8).


Trial Sharpes: `{"incumbent": 0.0, "points_rate_permute": 40.8625, "rate_refit": 56.2774, "points_rate_stratified": 5.3759, "rate_refit_stratified": 4.6124, "rate_refit_reselect": 284.8197, "stratified": 2.3824, "feasibility_clamp": 3.0748, "mvp1_null": -0.1036, "random_order": -5.4241}`. `V` is measured over `feasibility_clamp`, `points_rate_permute`, `points_rate_stratified`, `rate_refit`, `rate_refit_reselect`, `rate_refit_stratified`, `stratified` — the pre-registration §3 convention: the two degenerates AND the `incumbent` REFERENCE arm are excluded (MH2.1 (a): a structural 0.0 inflates a small family's dispersion), while `n_trials` stays at the full declared 10.


## 6. The INJECTED-EFFECT POSITIVE CONTROL (pre-registered §3)

**`BLIND`** at an injected **+0.75 CRPS** and **+0.05 tier-ρ** per fold on every non-degenerate, non-reference arm.


not one arm clears even the METRIC gates at an injected effect of 0.75 — this family would return a null for a real, large effect, so a null from it is free (NF1.7 (a): a check that cannot fire is not a check that passed).


* metric gates: `beats_incumbent`, `bh_fdr`, `coherence_restored`, `degenerates_lose`, `fold_consistency`, `ordering_not_regressed`, `own_form_ceiling`
* deflation-class gates present: `dsr`
* survivors: `none`  ·  metric survivors: `none`  ·  deflation-blocked: `none`
* null-control leg ran: **True**; survivors on the NO-EFFECT payload: `[]` (any survivor here would make the family VACUOUS and every reading of this study meaningless)


⭐ **`field_level_gates_applied_per_arm` = `[]`.** EMPTY is the affirmative finding the pre-registration predicted: this study's registered per-arm gate table deliberately carries NO field-level statistic as a per-arm pass/fail. CSCV/PBO has one value for the whole field and answers whether the SELECTION overfit; reading it per-arm converts "the search was unstable" into "this arm failed", which is not a statement the statistic makes (PLAT-CVP1 defect 4(a)).


Field-level PBO, reported BESIDE the control because it is deliberately outside the per-arm table: real **—** → injected **—** (the injection moved the in-sample winner on **0/0** splits; injection inert: **False**).

the injection moved the in-sample winner on 0/0 splits, so the PBO comparison is ACTIVE. A RISE under a uniform edge is the signature of a TIE among near-clones (NF1.8), ⛔ not evidence that the field overfits.


## 7. Anchors

- Degenerates scored every run and READ, ⛔ not reasoned about: `{"mvp1_null": 24.2773, "random_order": 43.7884}` against the winner's **23.1707** ⇒ every degenerate loses: **True**.


- Own-form peeking ceiling (one PER FORM — the forms NEST, so a single field-wide ceiling would veto a legitimately better nested form, NF-D16 g‴): **18.2859**, gap **4.8848**, respected **True**. ACTIVE


⭐ A note a reader would otherwise read as a bug: the oracle REPLACES the score, which is this story's treated factor — so two arms differing only in the fit target share ONE ceiling. That is correct: the ceiling is a property of the FORM, not of the target.


## 8. The JOINT success criterion (the spec's three legs)

| leg | value | note |
|---|---|---|
| (a) ordering holds at every draftable tier | False | the target re-fit is STRUCTURALLY INACTIVE at ['RB'] — those cells are UNINFORMATIVE about the hypothesis, never a pass (NF-D20) |
| (b) give-back removed / not reintroduced | None | arm —% vs incumbent —% |
| (c) NF-INJ1 violations → 0 | None | attributable violating players: — |
| **ALL THREE** | **None** |  |


## 10. Null classification

```json
"NullVerdict(state='UNDEFINED', reason='`crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.', retest_trigger='2 more fold(s) \u2014 i.e. a window of 7 seasons', folds_have=2, folds_needed=4, extra_seasons=2, max_field_size=None, detail={'n_folds': 2, 'n_arms': 10}, field_remedy_admissible=None, pbo_application_admissible=None, lockstep=None)"
```


## 11. Reading, against the pre-registration's §6

- **UNDEFINED** — a pre-registered gate was NOT COMPUTABLE at this fold count (bh_fdr, dsr, fold_consistency, ordering_not_regressed, pbo_field_level) — ⛔ not failed, not passed, and ⛔ not shippable.


- DSR reading: winner per-fold Sharpe **56.2774** against the declared field's benchmark SR0 **161.9400** ⇒ **DSR_UNREACHABLE**. SR ≤ SR0 in THIS declared field ⇒ no fold count clears the bar (n enters only through √(n−1), which SCALES a positive gap and cannot CREATE one — NF-W8-0d's lockstep invariant). ⛔ Do NOT publish a season/fold re-test trigger for it.


- The 2×2, computed as a labelled diagnostic BEFORE naming any remedy (NF-W7f): dropping the most extreme arm in `V` (`rate_refit_reselect`, Sharpe 284.8197) collapses `V` **10577.1538 → 557.9223** and moves DSR **— → —**. ⛔ A DIAGNOSTIC, NOT A TRIM. Every arm here is DECLARED; you get to pre-register a family, you do not get to discover one (MH2.2). if V falls hard and DSR barely moves, the binding quantity is per-fold NOISE (a variance/design problem), NOT multiplicity — and prescribing a coherent re-registration would spend a successor on the wrong lever (NF-W7f)


- ⛔ **NO "more data" re-test trigger** is published. the DSR shortfall is unreachable at any n (lockstep invariant, NF-W8-0d)

