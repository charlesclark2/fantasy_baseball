# NF-INJ3b — a FRESH forward re-registration of the injury-games caps

**VERDICT: SHIP** — registered primary `hurdle_transfer`. `best_alpha = 0`. Generated 2026-08-23T05:42:13.841274+00:00 in 1.1s.

> Pre-registration: `ablation_results/nf_inj3b_preregistration.md` — committed BEFORE any arm was scored under this registration. ⛔ Not edited by this run (E2.1-r).

> 🔒 DEPLOY-HELD: `SERVED_ARM` is `"incumbent"`. Nothing here serves until the gated ship path completes AND the operator records a disposition.

## 0. ⚠️ HONESTY CLAUSE — read before the leaderboard

**This study bought a PROPERLY-REGISTERED RECORD and an HONEST BH ANSWER. It did not buy new evidence.** The direction and magnitude of this effect were already public in NF-INJ3's record, and this run re-scores the *same harness on the same data* — every per-fold, per-arm CRPS is pinned BYTE-IDENTICAL to the parent's (§1 below). ⇒ **a gate that passes here is a REPRODUCTION, not a corroboration**, and is written up as one.

⭐ The one genuinely open question was **DSR**. `V` is a SAMPLE VARIANCE and moves NON-MONOTONICALLY with the field's MEMBERSHIP, and this field is not NF-INJ3's field — so the parent's **0.973** diagnostic was **NOT inherited** and was **NOT** this study's expected value. It is reported below as what it is: a figure computed for the first time under a family declared on mechanism.

## 1. Reproduction pins — what makes "only the REGISTRATION changed" a MEASUREMENT

**Pin 1 — scoring identity vs the RECORDED parent artifact (`nf_inj3_injury_games.json`):** 42/42 per-fold × per-arm CRPS compared; max absolute difference **0.000e+00** against a tolerance of **1e-09** ⇒ **PASS**. Non-vacuous: True. Arms that diverge: `[]`.

**The two-sided CONTROL that ATTRIBUTES pin 1** — the PARENT'S OWN entrypoint re-run in THIS environment (`nf_inj3b_parent_env_control.json`), same DuckDB, same build artifacts: 42/42 compared, max absolute difference **0.000e+00** ⇒ **IDENTICAL**. (numpy 2.4.4, scipy 1.17.1, pandas 2.3.3.)

⇒ **Attribution: CLEAN — the registered pin passes.**

⛔ The control is a DIAGNOSTIC. It does not become the pin and a failing registered pin is never relabelled a pass (E2.1-r).

**Served-board identity:** **22** flagged veterans on the live 2026 board ({'RES': 14, 'PUP': 8}); **0** exceed the incumbent's ceiling; max round-trip error **0.00e+00**.

## 2. The registration, as declared (preregistration §2 / §3 / §6)

* **Field (6 arms, declared ON MECHANISM):** `incumbent`, `fitted_status`, `timing_aware`, `hurdle_transfer`, `all_zero`, `no_cap`
* **Registered PRIMARY:** `hurdle_transfer` — gates are computed on the primary, never on the field's argmin. Field argmin this run: `hurdle_transfer` (agree: **True**).
* **Matched foil for the claimed channel:** `timing_aware` — identical covariates, availability SPLIT removed and nothing else changed.
* **Excluded ON MECHANISM:** `sus_regime` — a per-status REGIME carve-out for SUS, which has 0 rows on the 2026 serving cohort and 11 eval rows all in 2019–2020 (inert on 5 of 7 folds) — a different mechanism, structurally inactive where the claim lands (NF-D20). ⚠️ The narrowing is ADVERSE by DSR-CONV's own non-monotonicity (a near-mean arm's removal WIDENS `V`), declared before scoring.
* **`V` membership:** measured over `fitted_status`, `timing_aware`, `hurdle_transfer`; EXCLUDED from `V`: `all_zero`, `no_cap`, `incumbent` (DSR-CONV degenerates + MH2.1 (a) reference). `n_trials` = **6** — every declared arm pays FULL multiplicity.
* **BH family:** `single_hypothesis` (size 1) at q = 0.1.
* **Era floor:** 2016 — a DATA-FIDELITY quantity (§8). Folds: [2019, 2020, 2021, 2022, 2023, 2024, 2025].

## 3. The field

| arm | role | CRPS | MAE | mean games | lift vs incumbent | folds beating incumbent |
|---|---|---|---|---|---|---|
| incumbent | REFERENCE | 2.3933 | 4.4698 | 5.4030 | 0.0000 | — (self) |
| fitted_status |  | 2.1756 | 3.3562 | 2.3870 | 0.2178 | 4 |
| timing_aware | matched foil | 2.1561 | 3.2290 | 2.1900 | 0.2373 | 4 |
| hurdle_transfer | **PRIMARY** | 2.1089 | 3.3554 | 2.6070 | 0.2845 | 6 |
| all_zero | DEGENERATE | 2.9478 | 2.9487 | 0.0000 | -0.5545 | 2 |
| no_cap | DEGENERATE | 4.1125 | 6.3607 | 8.5450 | -1.7192 | 0 |


⛔ **CRPS selects. MAE never does — MEASURED, not assumed.** n=418, median realized games 0.0, zero share 0.6077; the all-zero nihilist scores MAE **2.7536** against the pooled mean's **3.5228** ⇒ MAE inverted = **True** (NF-D11/NF-D14).

## 4. Gates (preregistration §5 — all nine must pass)

| gate | value | bar | verdict |
|---|---|---|---|
| 1 beats incumbent | 0.2845 | > 0 | True |
| 2 fold consistency | 6 | ≥ 6 of 7 | True |
| 3 PBO (declared field) | 0.0000 | < 0.2 | True |
| 4 DSR (registered V) | 0.9715 | ≥ 0.95 | True |
| 5 BH-FDR (single hypothesis) | 0.0501 | < q = 0.1 | True |
| 6 degenerates lose | {'all_zero': 2.9478, 'no_cap': 4.1125} | both lose | True |
| 7 own-form oracle + matched-n | per-form (NF-D16 g‴) | no arm beats its own form's peek | True |
| 8 beats permutation | 0.1147 | > 0 | True |
| 9 hurdle attributable (matched foil) | 0.0472 | > 0 | True |


**SHIP = True.** Failing gates: none.

Whole-field DSR **0.0** beside the binding registered figure **0.9715** (`V` registered 0.018589 vs whole-field 2.504349). Contender spread **2.24%** vs whole-field **95.01%** — a spread computed over a field containing its OWN nulls measures the nulls (NF1.8).

NF1.8 triad — flip distribution `{'hurdle_transfer': 5}` over 5 in-sample windows; Bailey performance degradation **0.0%**.

Trial Sharpes: `{'hurdle_transfer': 0.7338, 'timing_aware': 0.5243, 'fitted_status': 0.4779, 'incumbent': 0.0, 'all_zero': -0.8319, 'no_cap': -3.4443}`

⛔ `V`'s membership is FIXED by preregistration §3 and is not re-cut under any outcome (MH2.2). The exclusion is NON-MONOTONE and is therefore not a lever: dropping a near-mean arm WIDENS the sample variance and RAISES the bar.

## 5. The BH family — named BEFORE any p-value (preregistration §6)

**Registered family: `single_hypothesis`, size 1, q = 0.1.** Primary one-sided paired p = **0.0501** against a cutoff of **0.1** ⇒ **SURVIVES**.

*Why this family:* one MECHANISM (the injury-games level for a flagged veteran), one POPULATION (flagged non-returner veterans, 2019–2025 eval folds), no registered position or per-status axis, and the primary is REGISTERED not selected ⇒ exactly ONE hypothesis test. The field's SEARCH is deflated by DSR at N=6; applying BH across the arms as well deflates the same search a SECOND time with a second instrument.

**DISCLOSED, NOT BINDING** — the strict across-arms sensitivity — the eligible arms as parallel hypotheses (this is NOT the registered family): rank-1 cutoff 0.0333 over 3 eligible arms ⇒ primary survives = **False**. ⛔ The registered family binds whichever way this falls, including if this reading would have been kinder (`admissible_to_act_on: false`).

## 6. Where the lift comes from — matched pairs, one change per step

| channel | delta_crps | folds_positive | p_one_sided |
|---|---|---|---|
| level__incumbent_to_fitted_status | 0.2178 | 4 | 0.1265 |
| form__fitted_status_to_glm | 0.0195 | 5 | 0.1029 |
| hurdle_split__glm_to_hurdle | 0.0472 | 5 | 0.0555 |


Steps sum to **0.2845** against the primary's total lift **0.2845** (exact by construction).

**Gate 9 / the matched foil.** `hurdle_transfer` **2.1089** vs `timing_aware` **2.1561** ⇒ paired delta **0.0472** (5/7 folds positive, p = 0.0555). hurdle_transfer − timing_aware on IDENTICAL covariates = the AVAILABILITY-SPLIT attribution. A primary win this does not separate is a win for the shared in-fold fitted LEVEL, never for the hurdle (NF-D10 / NF-D15).

**Permutation anchor.** permuted **2.2236** vs primary **2.1089** ⇒ lift **0.1147** (p = 0.0223).

## 7. Anchors — a missing anchor is a FAILED check, never a pass (NF1.7 (a))

| arm | evaluable | arm_crps | own_form_oracle_crps | respects_oracle |
|---|---|---|---|---|
| incumbent | True | 2.3933 | 2.0659 | True |
| fitted_status | True | 2.1756 | 2.0659 | True |
| timing_aware | True | 2.1561 | 1.8806 | True |
| hurdle_transfer | True | 2.1089 | 1.9194 | True |


**Matched-n control** — `{"evaluable": true, "matched_n_crps": 2.1896, "oracle_beats_matched_n": true, "why": "the peeking oracle is a FLOOR only at matched family AND matched resolution (NF1.7 (b) / NF1.9 (f)) \u2014 the primary's own form on ONE prior season"}`

**Pooled-mean anchor** CRPS 2.2146.

## 8. Mechanism activity (NF-D20 — count before crediting)

| fold | n_eval | RES | PUP | NFI | SUS | timing_varies |
|---|---|---|---|---|---|---|
| 2019 | 46 | 31 | 6 | 0 | 9 | True |
| 2020 | 25 | 21 | 2 | 0 | 2 | True |
| 2021 | 58 | 58 | 0 | 0 | 0 | True |
| 2022 | 36 | 36 | 0 | 0 | 0 | True |
| 2023 | 45 | 45 | 0 | 0 | 0 | True |
| 2024 | 32 | 32 | 0 | 0 | 0 | True |
| 2025 | 41 | 41 | 0 | 0 | 0 | True |


Totals by status: `{'RES': 361, 'PUP': 26, 'NFI': 0, 'SUS': 31}`. **Inactive: `['NFI']`.** NFI has ZERO rows historically AND zero in the 2026 serving cohort — its cap is unfittable and INACTIVE; no arm may claim credit there (NF-D20).

## 9. What the primary would serve on today's board

Arm `hurdle_transfer` on the **22** flagged veterans of the live board: mean expected games **5.292 → 2.682**; 22 move DOWN, 0 move UP.

| player_name | position | status | eg | incumbent_games | arm_games | delta |
|---|---|---|---|---|---|---|
| ALEC PIERCE | WR | PUP | 15.1630 | 7.3490 | 3.6610 | -3.6880 |
| GEORGE KITTLE | TE | PUP | 15.0500 | 7.3150 | 3.3310 | -3.9840 |
| ZACH CHARBONNET | RB | PUP | 13.6800 | 6.9040 | 3.7100 | -3.1940 |
| JAYDEN HIGGINS | WR | RES | 12.8630 | 6.6590 | 4.0940 | -2.5650 |
| LUKE MUSGRAVE | TE | PUP | 12.3040 | 6.4910 | 3.1960 | -3.2950 |
| TYRELL SHAVERS | WR | PUP | 9.7140 | 5.7140 | 3.1590 | -2.5550 |
| RICKY PEARSALL | WR | RES | 9.4990 | 5.6500 | 4.0050 | -1.6450 |
| MASON TIPTON | WR | PUP | 8.7190 | 5.4160 | 3.4110 | -2.0050 |
| ROBBIE OUZTS | FB | RES | 8.6990 | 5.4100 | 1.4100 | -4.0000 |
| JULIAN HILL | TE | RES | 8.6790 | 5.4040 | 3.0280 | -2.3760 |
| JEROME FORD | RB | RES | 8.6720 | 5.4020 | 4.2180 | -1.1840 |
| ISAAC GUERENDO | RB | PUP | 7.9700 | 5.1910 | 2.0460 | -3.1450 |
| GUNNER OLSZEWSKI | WR | RES | 7.9580 | 5.1880 | 3.2540 | -1.9340 |
| TIP REIMAN | TE | PUP | 7.3460 | 5.0040 | 2.6210 | -2.3830 |
| JAMARI THRASH | WR | RES | 6.8120 | 4.8440 | 3.7040 | -1.1400 |


⚠️ Reported for the record whether or not the arm ships. A shipping arm is **level-adjacent** (MVP-1's point is `rate × games`) and additionally requires the whole-board placement read (`run_nf_tr2b_placement_read`), `run_interval_revalidation` (NF-D16 / NF-D21), NF-TR2b's caveat that the VOR shield is ADDITIVE-only and does NOT hold under the two superflex configs, and a **MEASURED** served-POINT impact (NF1.5 hands part of the availability discount back — never assume proportional).

## 10. Gate-choice sensitivity

**`cv_power.classify_null` is INAPPLICABLE, and that is NAMED rather than left silent (NF1.7 (a)).** It is the instrument for a NULL; this study cleared every registered gate, so there is no null state to classify and no re-test trigger to publish. ⛔ In particular, no fold-count / "more seasons" trigger is emitted — 28 folds is 28 NFL seasons and the era floor is a data-fidelity fact, so such a trigger would be the NF-D18 actively-misleading direction even if a gate had failed.

**NF-D15 (g″) — does the outcome rest on MY gate choice?** fails with DSR removed: False; fails with BH removed: False; fails with BOTH removed: False.

## 11. Deflation diagnostics — ⛔ REPORTED, NEVER ACTED ON

```json
{
  "parent_convention_reference_inside_v": {
    "V": 0.0961,
    "dsr": 0.871,
    "admissible_to_act_on": false,
    "why": "NF-INJ3's convention, shown on NF-INJ3b's field so the effect of naming MH2.1 (a) is legible. The REGISTERED figure binds (E2.1-r)."
  },
  "nf_w7h_drop_most_extreme": {
    "evaluable": false,
    "dropped_arm": "hurdle_transfer",
    "why": "the most extreme trial Sharpe IS the arm under test \u2014 a DSR reached by deleting it would be INADMISSIBLE (NF-W7h), so no trimmed figure is reported"
  }
}
```

They name a LEVER; they never license a re-read of a registered gate (E2.1-r / MH2.2). A DSR reached by deleting the arm under test is INADMISSIBLE and is refused rather than reported (NF-W7h).

## 12. Reading the result (hand-written; the JSON above is the machine record)

**All nine registered gates pass. The study CLEARS — and the honest word for what that buys is a RECORD, not a discovery.**

### 1. What is genuinely NEW here, stated narrowly

Exactly two things, and neither is evidence:

* **`DSR` computed for the first time under a family declared on MECHANISM: 0.9715** against the 0.95 bar. ⚠️ This is **not** the parent's 0.973 diagnostic re-appearing — that figure belonged to a DIFFERENT membership. ⭐ And the direction is the tell that the registration was honest: `V` is a SAMPLE VARIANCE, NF-INJ3b's mechanism-justified narrowing drops a NEAR-MEAN arm, and the pre-registration declared **before scoring** that this would WIDEN `V` and RAISE the bar. It did — `V` 0.018589 against the parent diagnostic's 0.0151, and DSR lands BELOW 0.973. **The narrowing cost the study DSR and it still clears.** A field chosen for its effect on this gate would have moved the other way.
* **BH gets its first honest answer.** The family is named (`single_hypothesis`, size 1, q = 0.1) and the primary's p = 0.0501 clears it. ⛔ The strict across-arms sensitivity is DISCLOSED and does **not** clear (rank-1 cutoff 0.0333); the registered family binds regardless, and it was named before any p-value existed. **A reader who thinks the across-arms reading is right should read this study as NOT clearing gate 5** — that is precisely why both are on the record.

### 2. What is NOT new, and must not be written up as though it were

Everything else. Pin 1 matches the parent's recorded artifact at **0.0e+00** over 42 comparisons — the same data, the same folds, the same shared φ, the same arm fits. Seven of the nine gates passed in NF-INJ3 and pass again here **because they are the same numbers**. ⛔ A foregone gate outcome is a REPRODUCTION. It is not fresh confirmation and it does not raise anyone's confidence in the effect beyond what NF-INJ3 already earned.

### 3. The substantive finding — unchanged from the parent, restated because it is what the operator is deciding about

The shipped caps are roughly **double** what any fitted form says. Pooled expected games: incumbent **5.403** against **2.607** for the primary. On the live board all **22 of 22** flagged veterans move DOWN (mean **5.292 → 2.682** games), **0** move up.

⚠️ **Read the fold counts, not just the means.** The primary beats the incumbent on **6/7** folds at p = 0.0501. This is a LARGE mean effect with real fold-to-fold variance, not a metronomic one. It clears the registered bar; it is not overwhelming.

**Where the lift lives.** LEVEL 0.2178 → FORM 0.0195 → HURDLE SPLIT 0.0472, summing exactly to 0.2845. The LEVEL channel dominates by an order of magnitude — **the constants, not the shape, are the defect.** Gate 9 separates the availability split from the covariates the two arms share (delta 0.0472, p = 0.0555), so the winner's FORM is attributable, but the money is in the level.

### 4. ⛔ What a pass here does NOT authorise

**Nothing serves.** A cap change is **level-adjacent** (`point = rate × games`), so the gated ship path in preregistration §5 runs first and every step of it is still deploy-held: the whole-board cross-position **placement read** against the PUBLISHED artifact; **`run_interval_revalidation`**; NF-TR2b's caveat that the VOR shield is **ADDITIVE-only** and does **not** cover the two superflex configs; and the served-**POINT** impact **MEASURED**, never assumed proportional — NF1.5's ordering step hands part of the availability discount back (NF-INJ1 / NF-INJ2 territory).

**And the parent's null STANDS exactly as recorded.** NF-INJ3 is `POWER_LIMITED` and is not re-read, re-scored or re-labelled by this study (E2.1-r). NF-INJ3b is a separate, freshly-registered study that happens to run on the same numbers.
