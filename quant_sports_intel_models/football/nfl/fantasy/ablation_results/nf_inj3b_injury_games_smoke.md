# NF-INJ3b — a FRESH forward re-registration of the injury-games caps

**VERDICT: UNDEFINED** — registered primary `hurdle_transfer`. `best_alpha = 0`. Generated 2026-08-23T05:39:53.091422+00:00 in 0.6s.

> Pre-registration: `ablation_results/nf_inj3b_preregistration.md` — committed BEFORE any arm was scored under this registration. ⛔ Not edited by this run (E2.1-r).

> 🔒 DEPLOY-HELD: `SERVED_ARM` is `"incumbent"`. Nothing here serves until the gated ship path completes AND the operator records a disposition.

## 0. ⚠️ HONESTY CLAUSE — read before the leaderboard

**This study bought a PROPERLY-REGISTERED RECORD and an HONEST BH ANSWER. It did not buy new evidence.** The direction and magnitude of this effect were already public in NF-INJ3's record, and this run re-scores the *same harness on the same data* — every per-fold, per-arm CRPS is pinned BYTE-IDENTICAL to the parent's (§1 below). ⇒ **a gate that passes here is a REPRODUCTION, not a corroboration**, and is written up as one.

⭐ The one genuinely open question was **DSR**. `V` is a SAMPLE VARIANCE and moves NON-MONOTONICALLY with the field's MEMBERSHIP, and this field is not NF-INJ3's field — so the parent's **0.973** diagnostic was **NOT inherited** and was **NOT** this study's expected value. It is reported below as what it is: a figure computed for the first time under a family declared on mechanism.

## 1. Reproduction pins — what makes "only the REGISTRATION changed" a MEASUREMENT

**Pin 1 — scoring identity vs the RECORDED parent artifact (`nf_inj3_injury_games_smoke.json`):** 18/18 per-fold × per-arm CRPS compared; max absolute difference **1.010e-02** against a tolerance of **1e-09** ⇒ **FAIL AS REGISTERED**. Non-vacuous: True. Arms that diverge: `['hurdle_transfer', 'timing_aware']`.

⚠️ **The attribution control is NOT EVALUABLE** — no --parent-control artifact supplied — the attribution of a pin miss is NOT evaluable (NF1.7 (a)); it is not scored as clean. A pin miss therefore cannot be attributed, and is NOT scored as clean (NF1.7 (a)).

⛔ The control is a DIAGNOSTIC. It does not become the pin and a failing registered pin is never relabelled a pass (E2.1-r).

**Served-board identity:** **22** flagged veterans on the live 2026 board ({'RES': 14, 'PUP': 8}); **0** exceed the incumbent's ceiling; max round-trip error **0.00e+00**.

## 2. The registration, as declared (preregistration §2 / §3 / §6)

* **Field (6 arms, declared ON MECHANISM):** `incumbent`, `fitted_status`, `timing_aware`, `hurdle_transfer`, `all_zero`, `no_cap`
* **Registered PRIMARY:** `hurdle_transfer` — gates are computed on the primary, never on the field's argmin. Field argmin this run: `hurdle_transfer` (agree: **True**).
* **Matched foil for the claimed channel:** `timing_aware` — identical covariates, availability SPLIT removed and nothing else changed.
* **Excluded ON MECHANISM:** `sus_regime` — a per-status REGIME carve-out for SUS, which has 0 rows on the 2026 serving cohort and 11 eval rows all in 2019–2020 (inert on 5 of 7 folds) — a different mechanism, structurally inactive where the claim lands (NF-D20). ⚠️ The narrowing is ADVERSE by DSR-CONV's own non-monotonicity (a near-mean arm's removal WIDENS `V`), declared before scoring.
* **`V` membership:** measured over `fitted_status`, `timing_aware`, `hurdle_transfer`; EXCLUDED from `V`: `all_zero`, `no_cap`, `incumbent` (DSR-CONV degenerates + MH2.1 (a) reference). `n_trials` = **6** — every declared arm pays FULL multiplicity.
* **BH family:** `single_hypothesis` (size 1) at q = 0.1.
* **Era floor:** 2016 — a DATA-FIDELITY quantity (§8). Folds: [2023, 2024, 2025].

## 3. The field

| arm | role | CRPS | MAE | mean games | lift vs incumbent | folds beating incumbent |
|---|---|---|---|---|---|---|
| incumbent | REFERENCE | 2.4637 | 4.4722 | 5.3170 | 0.0000 | — (self) |
| fitted_status |  | 2.4280 | 3.8965 | 2.8510 | 0.0357 | 2 |
| timing_aware | matched foil | 2.4303 | 3.7127 | 2.4840 | 0.0334 | 2 |
| hurdle_transfer | **PRIMARY** | 2.3647 | 3.8200 | 2.9560 | 0.0990 | 3 |
| all_zero | DEGENERATE | 3.4549 | 3.4559 | 0.0000 | -0.9912 | 0 |
| no_cap | DEGENERATE | 3.7901 | 5.8595 | 8.4610 | -1.3264 | 0 |


⛔ **CRPS selects. MAE never does — MEASURED, not assumed.** n=418, median realized games 0.0, zero share 0.6077; the all-zero nihilist scores MAE **2.7536** against the pooled mean's **3.5228** ⇒ MAE inverted = **True** (NF-D11/NF-D14).

## 4. Gates (preregistration §5 — all nine must pass)

| gate | value | bar | verdict |
|---|---|---|---|
| 1 beats incumbent | 0.0990 | > 0 | True |
| 2 fold consistency | 3 | ≥ 3 of 3 | True |
| 3 PBO (declared field) |  | < 0.2 |  |
| 4 DSR (registered V) | 0.8555 | ≥ 0.95 | False |
| 5 BH-FDR (single hypothesis) | 0.0635 | < q = 0.1 | True |
| 6 degenerates lose | {'all_zero': 3.4549, 'no_cap': 3.7901} | both lose | True |
| 7 own-form oracle + matched-n | per-form (NF-D16 g‴) | no arm beats its own form's peek | True |
| 8 beats permutation | 0.1883 | > 0 | True |
| 9 hurdle attributable (matched foil) | 0.0656 | > 0 | True |


**SHIP = False.** Failing gates: ['pbo_ok', 'dsr_ok'].

Whole-field DSR **0.0** beside the binding registered figure **0.8555** (`V` registered 0.377451 vs whole-field 9.674953). Contender spread **2.68%** vs whole-field **60.28%** — a spread computed over a field containing its OWN nulls measures the nulls (NF1.8).

NF1.8 triad — flip distribution `{'hurdle_transfer': 3}` over 3 in-sample windows; Bailey performance degradation **None%**.

Trial Sharpes: `{'hurdle_transfer': 1.463, 'fitted_status': 0.4012, 'timing_aware': 0.3966, 'incumbent': 0.0, 'all_zero': -5.1463, 'no_cap': -5.6086}`

⛔ `V`'s membership is FIXED by preregistration §3 and was not re-cut. ⛔ `V`'s membership is FIXED by preregistration §3 and is not re-cut under any outcome (MH2.2). The exclusion is NON-MONOTONE and is therefore not a lever: dropping a near-mean arm WIDENS the sample variance and RAISES the bar.

## 5. The BH family — named BEFORE any p-value (preregistration §6)

**Registered family: `single_hypothesis`, size 1, q = 0.1.** Primary one-sided paired p = **0.0635** against a cutoff of **0.1** ⇒ **SURVIVES**.

*Why this family:* one MECHANISM (the injury-games level for a flagged veteran), one POPULATION (flagged non-returner veterans, 2019–2025 eval folds), no registered position or per-status axis, and the primary is REGISTERED not selected ⇒ exactly ONE hypothesis test. The field's SEARCH is deflated by DSR at N=6; applying BH across the arms as well deflates the same search a SECOND time with a second instrument.

**DISCLOSED, NOT BINDING** — the strict across-arms sensitivity — the eligible arms as parallel hypotheses (this is NOT the registered family): rank-1 cutoff 0.0333 over 3 eligible arms ⇒ primary survives = **False**. ⛔ The registered family binds whichever way this falls, including if this reading would have been kinder (`admissible_to_act_on: false`).

## 6. Where the lift comes from — matched pairs, one change per step

| channel | delta_crps | folds_positive | p_one_sided |
|---|---|---|---|
| level__incumbent_to_fitted_status | 0.0357 | 2 | 0.2795 |
| form__fitted_status_to_glm | -0.0023 | 2 | 0.5910 |
| hurdle_split__glm_to_hurdle | 0.0656 | 3 | 0.0104 |


Steps sum to **0.099** against the primary's total lift **0.099** (exact by construction).

**Gate 9 / the matched foil.** `hurdle_transfer` **2.3647** vs `timing_aware` **2.4303** ⇒ paired delta **0.0656** (3/3 folds positive, p = 0.0104). hurdle_transfer − timing_aware on IDENTICAL covariates = the AVAILABILITY-SPLIT attribution. A primary win this does not separate is a win for the shared in-fold fitted LEVEL, never for the hurdle (NF-D10 / NF-D15).

**Permutation anchor.** permuted **2.553** vs primary **2.3647** ⇒ lift **0.1883** (p = 0.0829).

## 7. Anchors — a missing anchor is a FAILED check, never a pass (NF1.7 (a))

| arm | evaluable | arm_crps | own_form_oracle_crps | respects_oracle |
|---|---|---|---|---|
| incumbent | True | 2.4637 | 2.3570 | True |
| fitted_status | True | 2.4280 | 2.3570 | True |
| timing_aware | True | 2.4303 | 2.0792 | True |
| hurdle_transfer | True | 2.3647 | 2.1207 | True |


**Matched-n control** — `{"evaluable": true, "matched_n_crps": 2.5035, "oracle_beats_matched_n": true, "why": "the peeking oracle is a FLOOR only at matched family AND matched resolution (NF1.7 (b) / NF1.9 (f)) \u2014 the primary's own form on ONE prior season"}`

**Pooled-mean anchor** CRPS 2.527.

## 8. Mechanism activity (NF-D20 — count before crediting)

| fold | n_eval | RES | PUP | NFI | SUS | timing_varies |
|---|---|---|---|---|---|---|
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

## 10. Null classification

```json
{
  "state": "UNDEFINED",
  "reason": "`nf_inj3b_crps_hurdle_transfer`: 3 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
  "retest_trigger": "1 more fold(s) \u2014 i.e. a window of 7 seasons",
  "folds_have": 3,
  "folds_needed": 4,
  "extra_seasons": 1,
  "max_field_size": null,
  "detail": {
    "n_folds": 3,
    "n_arms": 6
  },
  "field_remedy_admissible": null
}
```

⚠️ Read the machine flag `field_remedy_admissible`, **never the prose** (MH2.7).

**NF-D15 (g″) — does the outcome rest on MY gate choice?** fails with DSR removed: True; fails with BH removed: True; fails with BOTH removed: True.

## 11. Deflation diagnostics — ⛔ REPORTED, NEVER ACTED ON

```json
{
  "parent_convention_reference_inside_v": {
    "V": 0.393614,
    "dsr": 0.8493,
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
