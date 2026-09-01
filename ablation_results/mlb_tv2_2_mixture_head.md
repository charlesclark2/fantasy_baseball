# MLB-TV2-2 — a mixture-density head for the served `total_runs` SHAPE

> **VERDICT: `DEFLATION_REFUSED`**

`best_alpha = 0` · `bet_paused` stays `true` · **market-blind** · **nothing serves** · **DEPLOY-HELD**

**This is a calibration/honesty study.** No edge, win-rate, ROI or CLV claim is made and no gate reads a market price. Pre-registration: [`mlb_tv2_2_prereg.md`](mlb_tv2_2_prereg.md) (amendment 1 = its §12).

NOTHING SHIPS. The pre-registered FIELD-LEVEL deflation gate refused the study: PBO 0.7710 vs the 0.2 bar, and ALL THREE registered readings fail (declared 0.221, eligible 0.771, two_arm 0.250), so the refusal does not hinge on which reading binds. The per-arm clause table is reported UNCHANGED beside it — a field-level statistic must never be converted into a per-arm veto (PM convention 2026-08-28) — but it also does not license a ship.

---

## 1. Population

| | |
|---|---|
| champion | `v6` / `pre_lineup_v6`, fit 2026-06-23 |
| served window | 2026-06-23 → 2026-08-30 |
| PRIMARY tier | `post_lineup` — n = **851** |
| ⭐ median insertion lag | **0.0 d** — served-ness is the LAG, not the `is_backfill` flag (prereg §2.1) |
| blocks | 8 contiguous DATE blocks, cross-fit |

## 2. ⭐ The REPLICATION leg (prereg §3) — the STOP gate

| read | n | window | stated | realized | gap | null 95% band | outside? | power vs TV2-0's gap | BINDS |
|---|---:|---|---:|---:|---:|---|---|---:|---|
| `FULL_ERA` | 851 | 2026-06-23 → 2026-08-30 | 0.5000 | 0.4266 | **0.0734** | [0.0006, 0.0382] | ✅ | 0.989 | ⭐ **yes** |
| `TV2_0_WINDOW` | 758 | 2026-06-23 → 2026-08-23 | 0.5000 | 0.4274 | **0.0726** | [0.0000, 0.0409] | ✅ | 0.979 | no |
| `FRESH` | 93 | 2026-08-24 → 2026-08-30 | 0.5000 | 0.4194 | **0.0806** | [0.0054, 0.1129] | ⛔ | 0.288 | no |

**Replicated: ✅** — on the BINDING `FULL_ERA` read.

⚠️ UNDERPOWERED BY DESIGN: registered in prereg §3.3 before it was run. A non-significant FRESH read is the EXPECTED outcome under a true effect and is NOT a refutation.

⚠️ The champion era is bounded below by its fit date and above by today, so the widest served window that EXISTS is +93 rows / +12.3% over TV2-0's. FULL_ERA shares 89% of its rows with TV2-0's read: it is a LARGER read, not an INDEPENDENT one (prereg §3.2).

Secondary tier (`morning`, reported, never swaps the primary — E2.1-r): replicated = ✅, gap 0.0723

---

## 3. ⭐ The controls — run BEFORE any real-data verdict was read

A harness that cannot separate a PLANTED cause cannot separate a real one, and a harness that cannot FAIL is worse than none (MH2.6's vacuity floor).

| leg | what it plants | rate | bar | ✓ |
|---|---|---:|---:|---|
| §6.3 the fitter FINDS a planted skew | skew-normal α = 4.0 | **1.00** | ≥ 0.8 | ✅ |
| §7.5 NEGATIVE control (mirrors the SHIP RULE's margin) | *nothing — a correct model* | **0.00** | ≤ 0.05 | ✅ |
| §7.6 detection on a planted GROSS defect (METRIC gates) | skew-normal α = 4.0 | **1.00** | ≥ 0.8 | ✅ |

FULL ship rate beside each leg (§16): clean **0.00**, planted gross **0.45**. The gross leg is read on the METRIC gates because a family whose metric gates fire while its DEFLATION half blocks is `DEFLATION_BLOCKED`, not a vacuous harness.


Per-clause detection on the planted GROSS defect — a failure NAMES the clause that is power-limited instead of condemning the whole harness:

| clause | `C0_replication` | `C1_not_collapsed` | `C2_asymmetry` | `C3_score_not_degraded` | `C4_fidelity` | `C5_coverage_floor` | `C6_fold_consistency` | `C7_deflation` | `C8_multiplicity` | `C9_mechanism_attribution` | `C10_own_form_oracle_floor` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| detection rate | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.45 | 1.00 | 1.00 | 1.00 |

Collapsed block fits under the positive control: **0 of 160** — the staggered initialization (§6.1) keeping the fit off the flat ridge MH2.8 died on.

⛔ ⛔ NOT 'which arm is closest' (MH2.8's second defect): this is the fraction of clean-data replicates in which the FULL ship rule of §8 produces a SHIPPABLE margin.

⚠️ The control block was REUSED from the prior run's artifact (the controls depend only on the served `(μ, σ)` and the registered seed, both unchanged). The decisive battery below was RE-RUN and reproduces the recorded numbers at 1e-9.

**PLAT-CVP1 injected-effect positive control (EXECUTED, not narrated): `DEFLATION_BLOCKED`.** Field-level statistic: **ACTIVE** (PBO under null / injected: 0.9080, 0.7880).

⚠️ NF-INJ2b: a uniform injection cannot re-order treated arms among themselves, so a rank-based FIELD-LEVEL statistic can be invariant BY CONSTRUCTION. An unmoved statistic is reported INERT, never as a passed leg.

---

## 4. The battery (PRIMARY tier, n = 851)

⛔ = an ORACLE or a CONTROL — never a shippable arm. Every arm holds `μ` EXACTLY at the served value.

| arm | `p_over_gap_abs` | `crps` | `pit_ks` | `p_over_stated` | `cov80` | `var_z_pooled` | `z_skew` |
|---|---:|---:|---:|---:|---:|---:|---:|
| `incumbent` | 0.0734 | 2.5278 | 0.0880 | 0.5000 | 0.7991 | 1.0645 | 0.7360 |
| `foil_k1` | 0.0691 | 2.5294 | 0.0819 | 0.4956 | 0.8167 | 1.0645 | 0.7360 |
| `mix2_loc` | 0.0165 | 2.5127 | 0.0332 | 0.4431 | 0.8120 | 1.0645 | 0.7360 |
| `mix2_full` | 0.0018 | 2.5110 | 0.0276 | 0.4283 | 0.8096 | 1.0645 | 0.7360 |
| `mix3_full` | 0.0001 | 2.5103 | 0.0265 | 0.4267 | 0.7885 | 1.0645 | 0.7360 |
| `mixK_bic` | 0.0015 | 2.5112 | 0.0276 | 0.4280 | 0.8085 | 1.0645 | 0.7360 |
| `degen_sharp` ⛔ | 0.0560 | 3.0828 | 0.3267 | 0.4825 | 0.2432 | 1.0645 | 0.7360 |
| `degen_wide` ⛔ | 0.0720 | 3.7437 | 0.2795 | 0.4985 | 0.9976 | 1.0645 | 0.7360 |
| `ctrl_permuted` ⛔ | 0.0018 | 2.5110 | 0.0276 | 0.4283 | 0.8096 | 1.0645 | 0.7360 |
| `ctrl_symmetrized` ⛔ | 0.0689 | 2.5304 | 0.0840 | 0.4954 | 0.7991 | 1.0645 | 0.7360 |
| `oracle_mix2_loc` ⛔ | 0.0195 | 2.4915 | 0.0318 | 0.4461 | 0.8073 | 1.0645 | 0.7360 |
| `oracle_mix2_full` ⛔ | 0.0054 | 2.4880 | 0.0222 | 0.4320 | 0.8085 | 1.0645 | 0.7360 |
| `oracle_mix3_full` ⛔ | 0.0038 | 2.4861 | 0.0205 | 0.4304 | 0.7991 | 1.0645 | 0.7360 |
| `oracle_mixK_bic` ⛔ | 0.0404 | 2.4988 | 0.0503 | 0.4670 | 0.8073 | 1.0645 | 0.7360 |
| `oracle_empirical` ⛔ | 0.0002 | 2.5100 | 0.0085 | 0.4263 | 0.7979 | 1.0645 | 0.7360 |

### The fitted mixtures — and the TIE-WITH-FOIL guard (§6.2)

| arm | K by block | fitted skew by block | sup-norm vs the K=1 foil | COLLAPSED blocks |
|---|---|---|---|---:|
| `mix2_loc` | [2, 2, 2, 2, 2, 2, 2, 2] | [0.4731, 0.473, 0.458, 0.5264, 0.4231, 0.4896, 0.4659, 0.4523] | [0.05442, 0.05583, 0.05293, 0.05119, 0.048, 0.05509, 0.05252, 0.05208] | **0** |
| `mix2_full` | [2, 2, 2, 2, 2, 2, 2, 2] | [0.6074, 0.5952, 0.5792, 0.6311, 0.5435, 0.6263, 0.5881, 0.5923] | [0.07327, 0.07135, 0.07155, 0.07246, 0.06471, 0.07698, 0.07031, 0.07285] | **0** |
| `mix3_full` | [3, 3, 3, 3, 3, 3, 3, 3] | [0.7313, 0.6919, 0.7156, 0.7854, 0.6773, 0.7622, 0.7208, 0.738] | [0.07614, 0.07382, 0.07282, 0.07412, 0.06687, 0.07937, 0.07172, 0.07524] | **0** |
| `mixK_bic` | [2, 2, 2, 2, 2, 2, 2, 3] | [0.6074, 0.5952, 0.5792, 0.6311, 0.5435, 0.6263, 0.5881, 0.738] | [0.07327, 0.07135, 0.07155, 0.07246, 0.06471, 0.07698, 0.07031, 0.07524] | **0** |

⭐ A COLLAPSED arm's margin is a **TIE that refuses to count** — never a shape finding. TV2-0's skew-normal collapsed on 5 of 5 blocks on this same population at a realized `z` skew of 0.749; that is the failure this guard exists to make visible.

---

## 5. The shape channel — every claim measured over `foil_k1`

`foil_k1` is a location+scale recalibration with NO shape channel: it keeps the machinery, the cross-fit and the scale correction and removes only what this story claims. Scoring against the incumbent instead would let the mixture bank a plain recalibrator's work (§5.2).

| arm | Δ`p_over_gap_abs` (95% CI) | material | Δ`crps` | Δ`pit_ks` | share of the incumbent's gap |
|---|---:|---|---:|---:|---:|
| `mix2_loc` | 0.0526 [0.0128, 0.0527] | ✅ | 0.0167 | 0.0486 | 0.7157 |
| `mix2_full` | 0.0673 [-0.0018, 0.0675] | ⛔ | 0.0184 | 0.0542 | 0.9160 |
| `mix3_full` | 0.0689 [-0.0035, 0.0691] | ⛔ | 0.0191 | 0.0553 | 0.9388 |
| `mixK_bic` | 0.0676 [-0.0021, 0.0678] | ⛔ | 0.0183 | 0.0542 | 0.9203 |
| `ctrl_permuted` | 0.0673 [-0.0018, 0.0675] | ⛔ | 0.0184 | 0.0542 | 0.9160 |
| `ctrl_symmetrized` | 0.0002 [0.0002, 0.0002] | ✅ | -0.0010 | -0.0021 | 0.0025 |

⛔ `ctrl_permuted` was **registered as an EXPECTED EXACT TIE** (§5.4): a row permutation cannot move a MARGINAL law. Measured lift **0.067275** — reported as a proven tie and a machinery check (no row-level leakage), never as a passed test (NF1.9).

⛔ `ctrl_symmetrized` is the matched foil for the STATED MECHANISM (§5.4): same form, ASYMMETRY destroyed. Measured lift **0.0002**. If the win survives symmetrization it is NOT about skew (NF-D15 (g′)).

---

## 6. THE SHIP RULE (§8) — winner `mix3_full`

| clause | `mix2_loc` | `mix2_full` | `mix3_full` | `mixK_bic` |
|---|---|---|---|---|
| `C0_replication` | — | — | ✅ | — |
| `C1_not_collapsed` | ✅ | ✅ | ✅ | ✅ |
| `C2_asymmetry` | ✅ | ✅ | ✅ | ✅ |
| `C3_score_not_degraded` | ✅ | ✅ | ✅ | ✅ |
| `C4_fidelity` | ✅ | ✅ | ✅ | ✅ |
| `C5_coverage_floor` | ✅ | ✅ | ✅ | ✅ |
| `C6_fold_consistency` | ✅ | ✅ | ✅ | ✅ |
| `C7_deflation` | ✅ | ✅ | ✅ | ✅ |
| `C8_multiplicity` | ✅ | ✅ | ✅ | ✅ |
| `C9_mechanism_attribution` | ✅ | ✅ | ✅ | ✅ |
| `C10_own_form_oracle_floor` | ✅ | ✅ | ✅ | ⛔ |
| **SHIPS** | ✅ | ✅ | ✅ | ⛔ |

### Deflation (§12 amendment 1 — PBO and DSR read SEPARATE series)

| | |
|---|---|
| DSR series | per-block improvement in the per-ROW BRIER score of the printed probability, over foil_k1 (n_obs = N_BLOCKS) — §13 amendment 2 |
| PBO series | per-date-bucket -p_over_gap_abs over 16 contiguous buckets |
| `V` membership | `mix2_loc`, `mix2_full`, `mix3_full`, `mixK_bic` — reference, foil and degenerates ∉ `V` (MH2.1 (a) / DSR-CONV) |
| `n_trials` | 8 — the FULL field; multiplicity paid in full |
| `var_trials_sr` | 0.0058 (with degenerates: 0.1753) |
| observed SR / `SR0` | 0.7848 / 0.1114 |
| **DSR** | **0.9789** vs 0.95 → ✅ |
| **PBO** (binding: `eligible`) | **0.7710** vs 0.2 → ⛔ |
| `pbo_application` | `field` — a FIELD-LEVEL statistic, ⛔ never carried per-arm (PM convention 2026-08-28) |
| BH family | primary-statistic tests across the 4 declared TRIAL arms; cutoff 0.0500 |
| fold clause | ≥ 6 of 8 (false-fire 0.145) |
| coverage floor | 0.7767 — POWER-DERIVED from n at a false-reject target of 0.05 (NF-D22), ⛔ never a flat nominal point-floor |

PBO under all three registered readings:

| reading | n configs | PBO | < 0.20? |
|---|---:|---:|---|
| `declared` | 8 | 0.2210 | ⛔ |
| `eligible` ⭐ **binds** | 4 | 0.7710 | ⛔ |
| `two_arm` | 2 | 0.2500 | ⛔ |

⚠️ **ALL THREE readings fail the 0.2 bar**, so the refusal does not hinge on which one binds.

### NF1.8's discriminators, reported beside the refusal

⛔ Diagnostics. They gate nothing and cannot change a verdict. A rank statistic cannot tell an UNSTABLE pick from a TIE, which is the whole question here.

| arm | pooled `p_over_gap_abs` | buckets won (of 16) |
|---|---:|---:|
| `mix2_loc` | 0.05637 | 7 |
| `mix2_full` | 0.05509 | 2 |
| `mix3_full` | 0.05540 | 7 |
| `mixK_bic` | 0.05509 | 0 |

**Contender spread 0.00128 — 2.33% of the best arm.** Flip mass sits on two arms that differ by a fraction of a percent, which is NF1.8's signature of a **TIE**, not of an unstable search: the coin flip is over WHICH of four near-identical parameterizations of one marginal shape wins in-sample, not over WHETHER to correct. Median OOS rank of the in-sample best: declared 5.00, eligible 1.00, two_arm 2.00.


---

## 7. Classification, sensitivity and scope

**`classify_null` state: `DEFLATION_REFUSED`** (`declared_field_size = 4`; read from the MACHINE FLAGS, never the prose — MH2.7).

**Lockstep check (NF-W8-0d)** — is a shared-variance lever even capable of clearing `dsr_ok`? `{'closed': False, 'sr': 0.7848116787835305, 'sr0': 0.11135539013396645, 'gap': 0.6734562886495641, 'sign_invariant': True, 'dsr_falls_as_design_sharpens': False, 'ladder': [{'dispersion_factor': 1.0, 'winner_sharpe': 0.7848116787835305, 'sr0': 0.11135539013396645, 'sr_minus_sr0': 0.6734562886495641, 'dsr': 0.9403803867708854}, {'dispersion_factor': 0.5, 'winner_sharpe': 1.569623357567061, 'sr0': 0.2227107802679329, 'sr_minus_sr0': 1.3469125772991282, 'dsr': 0.9914689380805418}, {'dispersion_factor': 0.25, 'winner_sharpe': 3.139246715134122, 'sr0': 0.4454215605358658, 'sr_minus_sr0': 2.6938251545982563, 'dsr': 0.9982910647183577}, {'dispersion_factor': 0.1, 'winner_sharpe': 7.848116787835305, 'sr0': 1.1135539013396645, 'sr_minus_sr0': 6.73456288649564, 'dsr': 0.9992107977852258}, {'dispersion_factor': 0.01, 'winner_sharpe': 78.48116787835305, 'sr0': 11.135539013396645, 'sr_minus_sr0': 67.34562886495641, 'dsr': 0.9993368785904488}]}`. ⛔ Computed, never felt: a design change that scales every arm's dispersion by a common factor scales `SR` and `SR0` in lockstep, so its SIGN is invariant and 'get a lower-variance design' is deterministically void.


### Sensitivity (§7.4)

⭐ The spec's leave-one-COVID-season-out is **INAPPLICABLE-BY-CONSTRUCTION — the served era contains no season boundary; running it would be a vacuous anchor (NF1.7 (a))**. The applicable analogue — `leave-one-DATE-BLOCK-out` — asks the identical question and is what is run.

| held-out block | n | winner's lift over the foil | material |
|---:|---:|---:|---|
| 0 | 740 | 0.0701 | ✅ |
| 1 | 748 | 0.0679 | ✅ |
| 2 | 746 | 0.0588 | ⛔ |
| 3 | 745 | 0.0706 | ✅ |
| 4 | 750 | 0.0623 | ⛔ |
| 5 | 743 | 0.0742 | ✅ |
| 6 | 742 | 0.0653 | ✅ |
| 7 | 743 | 0.0688 | ✅ |

Sign stable across all 8 leave-one-out fits: **✅** (range 0.0588 … 0.0742).

### ⭐ SCOPE — DISCRIMINATION is untouched (prereg §10)

| reading | value | bar | |
|---|---:|---:|---|
| `std_pred_meanspread` = `STDDEV(pred_total_runs)` — `betting_ml/scripts/validate_v2_gates.py:34` | **0.535** | ≥ 2.0 | ⛔ FAILS |
| `std_pred_predictive_sd` = `mean(σ)` — `betting_ml/scripts/train_totals.py:121` | 4.371 | — | |
| realized `SD(y)` | 4.547 | — | |
| `Var(μ)/Var(y)` | **0.0139** | — | |

**Read by any gate here: ⛔ — no.** Every arm holds mu EXACTLY at the served value, so no arm can move either statistic. Registering a gate against a statistic no arm can move would ship decor (NF-MARGIN2). INACTIVE gets NO fold/season re-test trigger (NF-D18).

Null state: **`INACTIVE (structural)`**; re-test trigger: **none** — ⛔ no number of served games can move a statistic no arm can move.

**This study fixes the probability the product PRINTS. It does not make the model better at telling a high-scoring game from a low-scoring one.** Whether 2.0 is even attainable for a totals model is not something this market-blind study can measure, and it stays a named OPEN question on the epic.

---

## 8. What this study cannot say

- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; `bet_paused` stays `true`; no gate reads a market price.
- Nothing about a **different champion** — the population is `v6`/`pre_lineup_v6` (fit 2026-06-23); MH2.6's boundary is respected, not stretched.
- Nothing about **DISCRIMINATION** (§7 above).
- MH2.8's `INCUMBENT_STANDS`, TV2-0's INACTIVE feature lever and MH2.10's anti-informative σ-partition all **STAND AS RECORDED**. This study registered a NEW coherent family forward; it did not re-cut, re-read or relax any recorded gate.
- The `FULL_ERA` read shares 89% of its rows with TV2-0's. It is a LARGER read, not an INDEPENDENT one (§2).
- **DEPLOY-HELD.** Per MH2.1 a model-registry merge to `main` IS the deploy and no promotion gate exists — nothing merged, no registry entry changed, `deploy.sh` not run.
