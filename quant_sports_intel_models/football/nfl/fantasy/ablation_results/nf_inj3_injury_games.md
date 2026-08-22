# NF-INJ3 — a designation-timing-aware injury-games model (replacing the hardcoded caps)

**VERDICT: POWER_LIMITED** — winner `hurdle_transfer`. `best_alpha = 0`. Generated 2026-08-22T07:12:05.553599+00:00 in 1.2s.

> Pre-registration: `ablation_results/nf_inj3_preregistration.md` — committed BEFORE any arm was scored. ⛔ Not edited by this run (E2.1-r).

> 🔒 DEPLOY-HELD: `run_nf_inj3_injury_games.SERVED_ARM` is still `"incumbent"`. Nothing here serves until the PM records a disposition.

## 0. ⚠️ The registered covariate does not exist — read this before the leaderboard

The story asks for games as a function of status and **when the designation landed relative to kickoff**. Measured before the field was declared: **there is no designation DATE in this stack**. The weekly roster feed has no preseason weeks (a week-1 `RES` row is a STATE, not an EVENT); the Sleeper ingest OVERWRITES its Delta partition every capture so exactly ONE snapshot exists; the nflverse injury report has no `PRE` rows and no 2026 rows; there is no transactions feed. So the hypothesis is tested through the declared ONSET proxy (`onset_carryover, weeks_since_last_game`) and **every result below is scoped to that proxy** — it is NOT evidence about a designation date.

## 1. Reproduction pin — the incumbent IS the served board

**22** flagged veterans on the live 2026 board ({'RES': 14, 'PUP': 8}); **0** exceed the incumbent's ceiling; max round-trip error **0.00e+00**. 0 above the ceiling and a round-trip error at machine precision ⇒ the served board is on the incumbent cap path (blend 0.7, caps 4/4/4/7)

⭐ **Structural finding, out of scope, recorded for carding:** the cap never reaches a ROOKIE — `injury_availability_games` runs inside `project_veterans` while `project_rookies` is concatenated afterwards. Measured over the historical builds: **50 of 60** flagged rookies project ABOVE the incumbent's own ceiling, against **0 of 496** veterans.

## 2. The field, as declared

Folds **2019–2025** (7), expanding window, fit on 2016…Y−1. Declared field **7** arms + the matched foil `timing_aware_minus_timing`; pre-registered degenerates `all_zero`, `no_cap`. Excluded by registration: **60** rookies, **78** returners.

| arm | role | CRPS | MAE | mean games | lift vs incumbent | folds beating incumbent |
|---|---|---|---|---|---|---|
| hurdle_transfer |  | 2.1089 | 3.3554 | 2.6070 | 0.2845 | 6 |
| timing_aware |  | 2.1561 | 3.2290 | 2.1900 | 0.2373 | 4 |
| fitted_status |  | 2.1756 | 3.3562 | 2.3870 | 0.2178 | 4 |
| sus_regime |  | 2.1810 | 3.3692 | 2.4050 | 0.2123 | 4 |
| timing_aware_minus_timing | matched foil | 2.1812 | 3.2130 | 2.0930 | 0.2121 | 4 |
| incumbent | incumbent | 2.3933 | 4.4698 | 5.4030 | 0.0000 | — (self) |
| all_zero | DEGENERATE | 2.9478 | 2.9487 | 0.0000 | -0.5545 | 2 |
| no_cap | DEGENERATE | 4.1125 | 6.3607 | 8.5450 | -1.7192 | 0 |

⛔ The incumbent's own "folds beating incumbent" cell is a self-comparison and is rendered `— (self)` rather than `0`: a literal 0 there reads as "the incumbent never wins a fold", which is FALSE and overstates the evidence.
⛔ **CRPS selects. MAE never does — and that is MEASURED here, not assumed.**
On this cohort (n=418, median realized games **0**, zero share 0.608) the all-zero nihilist scores MAE **2.7536** against the pooled mean's **3.5228** ⇒ MAE inverted = **True**. MAE is minimised at the conditional median, which sits AT the floor here ⇒ MAE pays for pessimism and CANNOT select. CRPS is primary (NF-D11/NF-D14).

## 3. Mechanism activity (NF-D20 — count before crediting)

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

## 4. Gates

| gate | value | bar | verdict |
|---|---|---|---|
| beats incumbent | 0.2845 | > 0 | True |
| fold consistency | 6 | ≥ 6 of 7 | True |
| PBO (declared field) | 0.0000 | < 0.2 | True |
| DSR (DSR-CONV) | 0.8913 | ≥ 0.95 | False |
| BH-FDR | 0.0501 | q = 0.1 | False |
| degenerates lose | {"all_zero": 2.9478, "no_cap": 4.1125} | both lose | True |
| own-form oracle respected | per-form (NF-D16 g‴) | no arm beats its own form's peek | True |
| beats permutation | 0.0675 | > 0 | True |
| timing attributable (matched foil) | 0.0252 | > 0 | True |

Whole-field DSR **0.0** beside the binding DSR-CONV figure **0.8913** (V excl. degenerates 0.0724 vs whole-field 2.2023). Contender spread 2.24% vs whole-field 95.01% — a spread computed over a field containing its OWN nulls measures the nulls (NF1.8).

Trial Sharpes: `{'hurdle_transfer': 0.7338, 'timing_aware': 0.5243, 'fitted_status': 0.4779, 'sus_regime': 0.475, 'incumbent': 0.0, 'all_zero': -0.8319, 'no_cap': -3.4443}`

⚠️ The exclusion is NON-MONOTONE and is therefore not a lever: dropping a near-mean arm WIDENS the sample variance and RAISES the bar. It applies to the two arms named degenerate before any score, and to nothing else (DSR-CONV).

## 5. The matched foil — is the win TIMING, or the covariates it shares?

`timing_aware` CRPS **2.1561** vs `timing_aware_minus_timing` **2.1812** ⇒ paired delta **0.0252** (5/7 folds positive, p = 0.098). timing_aware − timing_aware_minus_timing = the TIMING attribution. A primary win this does not separate is a win for the covariates the two SHARE, never for timing (NF-D10 / NF-D15).

Permutation anchor (`onset_carryover, weeks_since_last_game` shuffled within status × season): permuted CRPS **2.2236** vs primary **2.1561** ⇒ lift **0.0675** (p = 0.0808).

## 5b. Channel decomposition — WHERE the lift comes from

| channel | Δ CRPS | folds + | p |
|---|---|---|---|
| level__incumbent_to_fitted_status | 0.2178 | 4 | 0.1265 |
| form__fitted_status_to_glm_no_timing | -0.0057 | 4 | 0.5911 |
| timing__glm_no_timing_to_timing_aware | 0.0252 | 5 | 0.0980 |
| hurdle_split__timing_aware_to_hurdle | 0.0472 | 5 | 0.0555 |

Steps sum to **0.2845** against the winner's total lift **0.2845** (exact by construction). the LEVEL channel dominates by an order of magnitude — the hardcoded caps are simply too high; TIMING is a small positive increment and the HURDLE SPLIT (the certified NF-W2 transfer) is roughly twice the timing channel.

## 6. Anchors (a missing anchor is a FAILED check, never a pass — NF1.7 (a))

| arm | arm CRPS | own-form oracle | respects | evaluable |
|---|---|---|---|---|
| incumbent | 2.3933 | 2.0659 | True | True |
| fitted_status | 2.1756 | 2.0659 | True | True |
| timing_aware | 2.1561 | 1.8806 | True | True |
| hurdle_transfer | 2.1089 | 1.9194 | True | True |
| sus_regime | 2.1810 | 2.0659 | True | True |
| all_zero |  |  |  | False |
| no_cap |  |  |  | False |
| timing_aware_minus_timing | 2.1812 | 1.9282 | True | True |

**Matched-n control** — {"evaluable": true, "matched_n_crps": 2.1896, "oracle_beats_matched_n": true, "why": "the peeking oracle is a FLOOR only at matched family AND matched resolution (NF1.7 (b) / NF1.9 (f)) \u2014 the winner's own form on ONE prior season"}

## 7. What the winner would serve on today's board

Arm `hurdle_transfer` on the **22** flagged veterans of the live board: mean expected games **5.292 → 2.682**; 22 move DOWN, 0 move UP.

| player_name | position | status | eg | onset_carryover | weeks_since_last_game | incumbent_games | arm_games | delta |
|---|---|---|---|---|---|---|---|---|
| ALEC PIERCE | WR | PUP | 15.1630 | 0.0000 | 4 | 7.3490 | 3.6610 | -3.6880 |
| GEORGE KITTLE | TE | PUP | 15.0500 | 0.0000 | 3 | 7.3150 | 3.3310 | -3.9840 |
| ZACH CHARBONNET | RB | PUP | 13.6800 | 0.0000 | 2 | 6.9040 | 3.7100 | -3.1940 |
| JAYDEN HIGGINS | WR | RES | 12.8630 | 0.0000 | 2 | 6.6590 | 4.0940 | -2.5650 |
| LUKE MUSGRAVE | TE | PUP | 12.3040 | 0.0000 | 3 | 6.4910 | 3.1960 | -3.2950 |
| TYRELL SHAVERS | WR | PUP | 9.7140 | 0.0000 | 3 | 5.7140 | 3.1590 | -2.5550 |
| RICKY PEARSALL | WR | RES | 9.4990 | 1.0000 | 2 | 5.6500 | 4.0050 | -1.6450 |
| MASON TIPTON | WR | PUP | 8.7190 | 1.0000 | 6 | 5.4160 | 3.4110 | -2.0050 |
| ROBBIE OUZTS | FB | RES | 8.6990 | 0.0000 | 2 | 5.4100 | 1.4100 | -4.0000 |
| JULIAN HILL | TE | RES | 8.6790 | 0.0000 | 4 | 5.4040 | 3.0280 | -2.3760 |
| JEROME FORD | RB | RES | 8.6720 | 1.0000 | 8 | 5.4020 | 4.2180 | -1.1840 |
| ISAAC GUERENDO | RB | PUP | 7.9700 | 1.0000 | 7 | 5.1910 | 2.0460 | -3.1450 |
| GUNNER OLSZEWSKI | WR | RES | 7.9580 | 0.0000 | 4 | 5.1880 | 3.2540 | -1.9340 |
| TIP REIMAN | TE | PUP | 7.3460 | 1.0000 | 17 | 5.0040 | 2.6210 | -2.3830 |
| JAMARI THRASH | WR | RES | 6.8120 | 1.0000 | 12 | 4.8440 | 3.7040 | -1.1400 |

⚠️ Reported for the record whether or not the arm ships. A shipping arm is **level-adjacent** (MVP-1's point is `rate × games`) and additionally requires the whole-board placement read (`run_nf_tr2b_placement_read`) and `run_interval_revalidation` (NF-D16 / NF-D21) — and NF-TR2b's caveat that the VOR shield is additive-only and does NOT hold under the two superflex configs.

## 8. Era fidelity — why 2016+ (a DESIGN quantity, not an outcome)

| season | n_res | med_games | zero_rate | status_change_share |
|---|---|---|---|---|
| 2002 | 52 | 7.0000 | 0.0770 | 0.0350 |
| 2003 | 61 | 6.0000 | 0.0660 | 0.0190 |
| 2004 | 66 | 4.0000 | 0.0610 | 0.0400 |
| 2005 | 61 | 6.0000 | 0.0820 | 0.0310 |
| 2006 | 61 | 5.0000 | 0.1150 | 0.0410 |
| 2007 | 70 | 5.0000 | 0.1290 | 0.0580 |
| 2008 | 69 | 5.0000 | 0.0580 | 0.0680 |
| 2009 | 60 | 6.0000 | 0.1330 | 0.0660 |
| 2010 | 71 | 6.0000 | 0.0140 | 0.0730 |
| 2011 | 71 | 5.0000 | 0.0560 | 0.0640 |
| 2012 | 78 | 8.0000 | 0.0770 | 0.0650 |
| 2013 | 75 | 6.0000 | 0.0800 | 0.0990 |
| 2014 | 60 | 6.0000 | 0.0330 | 0.0730 |
| 2015 | 86 | 8.0000 | 0.0350 | 0.0990 |
| 2016 | 83 | 0.0000 | 0.8310 | 0.1300 |
| 2017 | 74 | 0.0000 | 0.9190 | 0.3340 |
| 2018 | 61 | 0.0000 | 0.8360 | 0.3710 |
| 2019 | 79 | 0.0000 | 0.8480 | 0.5360 |
| 2020 | 43 | 0.0000 | 0.6980 | 0.6230 |
| 2021 | 90 | 0.0000 | 0.6330 | 0.6900 |
| 2022 | 87 | 0.0000 | 0.7360 | 0.5900 |
| 2023 | 83 | 0.0000 | 0.7230 | 0.5780 |
| 2024 | 61 | 0.0000 | 0.6230 | 0.5610 |
| 2025 | 67 | 0.0000 | 0.7610 | 0.5980 |
| 2026 | 12 | 0.0000 | 1.0000 | 0.0000 |

A player recorded on IR in **week 1** who then plays a median of six games is a season-END label backfilled onto every week — i.e. OUTCOME-CONTAMINATED. ⭐ The incumbent's own docstring fits its constants on **2015–2024**, one contaminated season inside the window.

## 9. Null classification

```json
{
  "state": "POWER_LIMITED",
  "reason": "`nf_inj3_crps_hurdle_transfer`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 28 folds against 7 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
  "retest_trigger": "+21 folds for the DSR gate \u2014 field size is NOT a lever here \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)",
  "folds_have": 7,
  "folds_needed": 28,
  "extra_seasons": 21,
  "max_field_size": 0,
  "detail": {
    "n_folds": 7,
    "n_arms": 7,
    "observed_sr": 0.7338,
    "sr0": 0.3731,
    "var_trials_sr": 0.0724,
    "degenerates_excluded_from_v": true,
    "var_trials_sr_with_degenerates": 2.2023,
    "v_inflation_factor_from_degenerates": 30.4185,
    "declared_field_size": 7,
    "declared_field_size_source": "stated",
    "field_remedy_admissible": null
  },
  "field_remedy_admissible": null
}
```

⚠️ Read the machine flag `field_remedy_admissible`, **never the prose** (MH2.7).

⚠️⚠️ **TWO HAND-CORRECTIONS TO THAT REMEDY TEXT — it is arithmetically right about the
channel it varied and MISLEADING as a prescription.**

1. **"field size is NOT a lever … the only lever left is a lower-variance design"** varies
   the trial COUNT `N` while holding `V` FIXED. But `SR0 = √V · z(N)` is taxed through TWO
   channels and MH2 says the DISPERSION channel usually dominates — which it does here:
   `V` **0.0724 → 0.0151** (a 4.8× collapse) moves DSR
   **0.8913 → 0.973**, i.e. past the bar. So the binding
   quantity is `V`'s COMPOSITION, not the design's variance and not the field's SIZE.
   ⛔ That does NOT license acting on it — see the reading below.

2. **The `+21`-fold trigger is arithmetically correct and not
   actionable.** `folds_needed = 28` means 28
   NFL seasons at this design, and the era floor (2016) is a DATA-FIDELITY fact, not a
   choice — the feed yields ONE new season a year. Publishing it as a re-test trigger is the
   NF-D18 misleading direction.

⭐ What IS true and worth carrying: `SR` **0.7338** > `SR0` **0.3731**, so the gap is POSITIVE
and this is **not** `DSR_UNREACHABLE` — and NF-W8-0d's lockstep invariant (a shared-variance
lever is deterministically void) does **not** bite here, because that invariant applies when
`SR ≤ SR0`. Both levers are live in principle; neither is available in practice at 7 folds.


---

## 10. Reading the result (hand-written; the JSON above is the machine record)

**The caps are wrong, the direction is unambiguous, and the study still does NOT ship —
because the null rests on a SPECIFICATION my own pre-registration left open, not on the
evidence. Both halves of that sentence are load-bearing.**

### 1. The substantive finding, which holds regardless of the verdict

**Every real arm beats the incumbent ON THE MEAN, and the incumbent's expected games are roughly DOUBLE what any fitted form says.** Pooled mean expected games: incumbent **5.403** against 2.387–2.607 for the fitted arms. On the live board all **22 of 22** flagged veterans move DOWN (mean **5.292 → 2.682** games), none up.

⚠️ **Read the fold counts, not just the means — they are the honest measure of how strong this is.** The winner beats the incumbent on **6/7** folds; `fitted_status`, `timing_aware` and `sus_regime` on **4/7** each. So the LEVEL channel is a LARGE mean effect with HIGH fold-to-fold variance (p = 0.1265), not a metronomic one — which is exactly why the design's 7 folds cannot certify it. ⛔ The `0` in the incumbent's own "folds won" cell above is a SELF-COMPARISON ARTIFACT (its lift over itself is 0, not > 0) and must NOT be read as "the incumbent never wins a fold".

⭐ **The PM-facing reading: after the cap, the board still materially UNDER-discounts injured players.** NF-INJ1 found the ordering step handing back +36.4% of the availability discount; this finds the discount was too SMALL to begin with. They compound in the same direction, and this half is the larger of the two.

### 2. Where the lift lives — and the answer to "what transfers?"

* **LEVEL (the caps themselves): +0.2178 CRPS — 77% of the total.** Simply FITTING the same functional form in-fold is almost the whole story. The constants, not the shape, are the defect.
* **FORM (cap-blend → GLM): -0.0057 — a wash.** The incumbent's functional form is fine.
* **TIMING (the declared onset proxy): +0.0252, p = 0.098** — positive, small, and not significant. ⇒ **the story's headline hypothesis is the SMALLEST of the three live channels.**
* **HURDLE SPLIT (the NF-W2 transfer): +0.0472, p = 0.0555** — roughly TWICE the timing channel, on identical covariates. The winner is the transfer arm.

⭐ **The story said "start by asking what transfers, don't rebuild cold," and that paid.** NF-W2's FEATURES cannot transfer at all (its source has no preseason rows and no 2026 rows), but its measured FINDING — the lift lives in the zero/availability leg — transfers cleanly to a SEASON target and is the single best-performing mechanism in the field.

### 3. Why it does not ship, stated precisely

Seven of nine gates pass, including every anchor: PBO **0.0**, fold consistency **6/7**, both degenerates lose, every arm respects its own-form peeking oracle with the matched-n control, the permutation anchor is beaten, and the matched foil separates a positive timing channel. Two fail:

* **DSR 0.8913 < 0.95** under the registered `V` convention.
* **BH-FDR** — under the STRICT across-arms reading (cutoff 0.025, winner p 0.0501).

⭐⭐ **AND HERE IS THE PART THAT MATTERS MOST, because it is the kind of thing a record can quietly omit: BOTH failures trace to a specification the pre-registration left OPEN, and under the most defensible reading of each, the arm clears everything.**

* **DSR.** MH2.1 (a) says a REFERENCE arm's identically-ZERO skill series inflates a small-family `V` exactly as a diagnostic anchor does, so `V` should be measured over NON-reference arms. My pre-registration declared DSR-CONV (degenerates ∉ `V`) and **did not invoke MH2.1 (a)** — so the incumbent's structural 0.0 sat inside `V`. Measured: `V` 0.0724 → 0.0151, DSR **0.8913 → 0.973**. The dropped arm is the incumbent, **not** the winner, so the diagnostic is admissible to REPORT (NF-W7h).
* **BH-FDR.** The pre-registration says "at the family's q" and never names the family. Across arms it corrects a SECOND time for the very search DSR already deflates; there is one mechanism, one population, and no registered position axis, so BH is arguably INAPPLICABLE here rather than failed (the MH2.7 `n_arms=1 ⇒ PBO INAPPLICABLE` shape). Single-hypothesis reading: p 0.0501 < 0.1 ⇒ would survive.

⛔ **Neither is acted on, and that is the whole point.** Adopting a convention AFTER seeing the registered gate fail is the E2.1-r inversion in its most literal form, and re-cutting `V` post-hoc is the MH2.2 laundering DSR exists to prevent. The registered figures BIND, the study returns a null, and the diagnostics are recorded so a reader can see exactly what separates it from a ship.

### 4. Classification — the null rests on a REGISTRATION CHOICE, not a threshold

`classify_null` returns **POWER_LIMITED** with a +21-season trigger. Corrected above: the binding quantity is `V`'s COMPOSITION, not power and not field size. Following NF-D20's rule — *when a null rests on a REGISTRATION CHOICE rather than a gate LEVEL, say so plainly* — the honest statement is:

> **The V-composition convention, not any threshold and not the evidence, separates this null from a ship.** Had the pre-registration invoked MH2.1 (a) (a convention this program already owns and already applies elsewhere), the registered DSR would read **0.973** and the arm would have cleared it.

⇒ the remedy is a **FRESH pre-registration** — one that names the `V` convention and the BH family up front — **never a re-read of this one**, and never "more seasons."

### 5. Reusable lessons

* ⭐ **A pre-registration must name the DEFLATION CONVENTIONS, not just the arms and the gates.** This one declared the field, the metric, the folds, the anchors and nine gate thresholds — and still lost on two unstated specification details. `V`'s membership and the BH family are as load-bearing as any threshold, and they are exactly the details that only become interesting after a result, i.e. the ones you can no longer set.
* ⭐ **A REFERENCE arm's trial Sharpe is 0 BY CONSTRUCTION, and a small field feels it.** With five non-degenerate arms, one structural zero drove `V` up 4.8× and cost ~0.082 of DSR. DSR-CONV handles DEGENERATES; the reference arm is a separate and equally mechanical inflation.
* **"What transfers" is a real question with a real answer, and it beat the story's own headline hypothesis.** The certified weekly family's FEATURES were unusable; its FINDING was the best mechanism in the field.
* **A registered covariate can simply not exist, and that is a finding to MEASURE before declaring the field.** There is no designation date anywhere in this stack — the roster feed has no preseason weeks, the Sleeper ingest overwrites its own history, the injury report has no 2026 rows. Discovering that inside the run would have produced a proxy chosen after the fact instead of before it.
* **The era boundary was the single highest-leverage measurement in the study.** Pre-2016 the "week-1" status is a season-END label backfilled onto every week (a week-1 IR player plays a median SIX games), and the incumbent's own constants were fitted on a window that includes it. Training on it would have made the incumbent look right.
