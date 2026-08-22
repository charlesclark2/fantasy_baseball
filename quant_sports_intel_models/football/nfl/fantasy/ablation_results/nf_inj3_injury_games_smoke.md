# NF-INJ3 — a designation-timing-aware injury-games model (replacing the hardcoded caps)

**VERDICT: UNDEFINED** — winner `hurdle_transfer`. `best_alpha = 0`. Generated 2026-08-22T06:16:08.785255+00:00 in 0.7s.

> Pre-registration: `ablation_results/nf_inj3_preregistration.md` — committed BEFORE any arm was scored. ⛔ Not edited by this run (E2.1-r).

> 🔒 DEPLOY-HELD: `run_nf_inj3_injury_games.SERVED_ARM` is still `"incumbent"`. Nothing here serves until the PM records a disposition.

## 0. ⚠️ The registered covariate does not exist — read this before the leaderboard

The story asks for games as a function of status and **when the designation landed relative to kickoff**. Measured before the field was declared: **there is no designation DATE in this stack**. The weekly roster feed has no preseason weeks (a week-1 `RES` row is a STATE, not an EVENT); the Sleeper ingest OVERWRITES its Delta partition every capture so exactly ONE snapshot exists; the nflverse injury report has no `PRE` rows and no 2026 rows; there is no transactions feed. So the hypothesis is tested through the declared ONSET proxy (`onset_carryover, weeks_since_last_game`) and **every result below is scoped to that proxy** — it is NOT evidence about a designation date.

## 1. Reproduction pin — the incumbent IS the served board

**22** flagged veterans on the live 2026 board ({'RES': 14, 'PUP': 8}); **0** exceed the incumbent's ceiling; max round-trip error **0.00e+00**. 0 above the ceiling and a round-trip error at machine precision ⇒ the served board is on the incumbent cap path (blend 0.7, caps 4/4/4/7)

⭐ **Structural finding, out of scope, recorded for carding:** the cap never reaches a ROOKIE — `injury_availability_games` runs inside `project_veterans` while `project_rookies` is concatenated afterwards. Measured over the historical builds: **50 of 60** flagged rookies project ABOVE the incumbent's own ceiling, against **0 of 496** veterans.

## 2. The field, as declared

Folds **2023–2025** (3), expanding window, fit on 2016…Y−1. Declared field **7** arms + the matched foil `timing_aware_minus_timing`; pre-registered degenerates `all_zero`, `no_cap`. Excluded by registration: **60** rookies, **78** returners.

| arm | role | CRPS | MAE | mean games | lift vs incumbent | folds won |
|---|---|---|---|---|---|---|
| hurdle_transfer |  | 2.3720 | 3.8327 | 2.9610 | 0.0918 | 3 |
| fitted_status |  | 2.4280 | 3.8965 | 2.8510 | 0.0357 | 2 |
| sus_regime |  | 2.4280 | 3.8965 | 2.8510 | 0.0357 | 2 |
| timing_aware |  | 2.4370 | 3.7245 | 2.4870 | 0.0267 | 2 |
| incumbent | incumbent | 2.4637 | 4.4722 | 5.3170 | 0.0000 | 0 |
| timing_aware_minus_timing | matched foil | 2.4803 | 3.6930 | 2.2660 | -0.0166 | 2 |
| all_zero | DEGENERATE | 3.4549 | 3.4559 | 0.0000 | -0.9912 | 0 |
| no_cap | DEGENERATE | 3.7901 | 5.8595 | 8.4610 | -1.3264 | 0 |

⛔ **CRPS selects. MAE never does — and that is MEASURED here, not assumed.**
On this cohort (n=418, median realized games **0**, zero share 0.608) the all-zero nihilist scores MAE **2.7536** against the pooled mean's **3.5228** ⇒ MAE inverted = **True**. MAE is minimised at the conditional median, which sits AT the floor here ⇒ MAE pays for pessimism and CANNOT select. CRPS is primary (NF-D11/NF-D14).

## 3. Mechanism activity (NF-D20 — count before crediting)

| fold | n_eval | RES | PUP | NFI | SUS | timing_varies |
|---|---|---|---|---|---|---|
| 2023 | 45 | 45 | 0 | 0 | 0 | True |
| 2024 | 32 | 32 | 0 | 0 | 0 | True |
| 2025 | 41 | 41 | 0 | 0 | 0 | True |

Totals by status: `{'RES': 361, 'PUP': 26, 'NFI': 0, 'SUS': 31}`. **Inactive: `['NFI']`.** NFI has ZERO rows historically AND zero in the 2026 serving cohort — its cap is unfittable and INACTIVE; no arm may claim credit there (NF-D20).

## 4. Gates

| gate | value | bar | verdict |
|---|---|---|---|
| beats incumbent | 0.0918 | > 0 | True |
| fold consistency | 3 | ≥ 3 of 3 | True |
| PBO (declared field) |  | < 0.2 |  |
| DSR (DSR-CONV) | 0.8386 | ≥ 0.95 | False |
| BH-FDR | 0.0760 | q = 0.1 | False |
| degenerates lose | {"all_zero": 3.4549, "no_cap": 3.7901} | both lose | True |
| own-form oracle respected | per-form (NF-D16 g‴) | no arm beats its own form's peek | True |
| beats permutation | 0.1237 | > 0 | True |
| timing attributable (matched foil) | 0.0433 | > 0 | True |

Whole-field DSR **0.0** beside the binding DSR-CONV figure **0.8386** (V excl. degenerates 0.239 vs whole-field 8.3562). Contender spread 2.36% vs whole-field 59.79% — a spread computed over a field containing its OWN nulls measures the nulls (NF1.8).

Trial Sharpes: `{'hurdle_transfer': 1.3069, 'fitted_status': 0.4012, 'sus_regime': 0.4012, 'timing_aware': 0.3087, 'incumbent': 0.0, 'all_zero': -5.1463, 'no_cap': -5.6086}`

⚠️ The exclusion is NON-MONOTONE and is therefore not a lever: dropping a near-mean arm WIDENS the sample variance and RAISES the bar. It applies to the two arms named degenerate before any score, and to nothing else (DSR-CONV).

## 5. The matched foil — is the win TIMING, or the covariates it shares?

`timing_aware` CRPS **2.437** vs `timing_aware_minus_timing` **2.4803** ⇒ paired delta **0.0433** (2/3 folds positive, p = 0.2032). timing_aware − timing_aware_minus_timing = the TIMING attribution. A primary win this does not separate is a win for the covariates the two SHARE, never for timing (NF-D10 / NF-D15).

Permutation anchor (`onset_carryover, weeks_since_last_game` shuffled within status × season): permuted CRPS **2.5607** vs primary **2.437** ⇒ lift **0.1237** (p = 0.1604).

## 6. Anchors (a missing anchor is a FAILED check, never a pass — NF1.7 (a))

| arm | arm CRPS | own-form oracle | respects | evaluable |
|---|---|---|---|---|
| incumbent | 2.4637 | 2.3570 | True | True |
| fitted_status | 2.4280 | 2.3570 | True | True |
| timing_aware | 2.4370 | 2.0781 | True | True |
| hurdle_transfer | 2.3720 | 2.1198 | True | True |
| sus_regime | 2.4280 | 2.3570 | True | True |
| all_zero |  |  |  | False |
| no_cap |  |  |  | False |
| timing_aware_minus_timing | 2.4803 | 2.1231 | True | True |

**Matched-n control** — {"evaluable": true, "matched_n_crps": 2.5035, "oracle_beats_matched_n": true, "why": "the peeking oracle is a FLOOR only at matched family AND matched resolution (NF1.7 (b) / NF1.9 (f)) \u2014 the winner's own form on ONE prior season"}

## 7. What the winner would serve on today's board

Arm `hurdle_transfer` on the **22** flagged veterans of the live board: mean expected games **5.292 → 2.698**; 22 move DOWN, 0 move UP.

| player_name | position | status | eg | onset_carryover | weeks_since_last_game | incumbent_games | arm_games | delta |
|---|---|---|---|---|---|---|---|---|
| ALEC PIERCE | WR | PUP | 15.1630 | 0.0000 | 4 | 7.3490 | 3.6300 | -3.7190 |
| GEORGE KITTLE | TE | PUP | 15.0500 | 0.0000 | 3 | 7.3150 | 3.2840 | -4.0310 |
| ZACH CHARBONNET | RB | PUP | 13.6800 | 0.0000 | 2 | 6.9040 | 3.6890 | -3.2150 |
| JAYDEN HIGGINS | WR | RES | 12.8630 | 0.0000 | 2 | 6.6590 | 4.0840 | -2.5750 |
| LUKE MUSGRAVE | TE | PUP | 12.3040 | 0.0000 | 3 | 6.4910 | 3.2230 | -3.2680 |
| TYRELL SHAVERS | WR | PUP | 9.7140 | 0.0000 | 3 | 5.7140 | 3.1880 | -2.5260 |
| RICKY PEARSALL | WR | RES | 9.4990 | 1.0000 | 2 | 5.6500 | 3.9490 | -1.7010 |
| MASON TIPTON | WR | PUP | 8.7190 | 1.0000 | 6 | 5.4160 | 3.4530 | -1.9630 |
| ROBBIE OUZTS | FB | RES | 8.6990 | 0.0000 | 2 | 5.4100 | 1.4780 | -3.9320 |
| JULIAN HILL | TE | RES | 8.6790 | 0.0000 | 4 | 5.4040 | 3.0350 | -2.3690 |
| JEROME FORD | RB | RES | 8.6720 | 1.0000 | 8 | 5.4020 | 4.2210 | -1.1810 |
| ISAAC GUERENDO | RB | PUP | 7.9700 | 1.0000 | 7 | 5.1910 | 2.1590 | -3.0320 |
| GUNNER OLSZEWSKI | WR | RES | 7.9580 | 0.0000 | 4 | 5.1880 | 3.2700 | -1.9180 |
| TIP REIMAN | TE | PUP | 7.3460 | 1.0000 | 17 | 5.0040 | 2.6520 | -2.3520 |
| JAMARI THRASH | WR | RES | 6.8120 | 1.0000 | 12 | 4.8440 | 3.7100 | -1.1340 |

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
  "state": "UNDEFINED",
  "reason": "`nf_inj3_crps_hurdle_transfer`: 3 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
  "retest_trigger": "1 more fold(s) \u2014 i.e. a window of 7 seasons",
  "folds_have": 3,
  "folds_needed": 4,
  "extra_seasons": 1,
  "max_field_size": null,
  "detail": {
    "n_folds": 3,
    "n_arms": 7
  },
  "field_remedy_admissible": null
}
```

⚠️ Read the machine flag `field_remedy_admissible`, **never the prose** (MH2.7).
