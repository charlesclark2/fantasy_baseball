# NCAAF-VAL3 — cold-start μ_total correction (weeks 1–3, in-fold selected)

**Verdict: `INCUMBENT_STANDS`.** Market-blind · `best_alpha = 0` · no serving change, no registry edit, no refit of a served artifact, no bet.

_Cache 2026-08-22 · 6,024 OOS games · 8 purged folds 2018–2025 · served config `ridge`/`strength_pace`/`strength_posterior` · declared field 8_

## 1. The field and what each arm did

| arm | role | δ̄ (pts) | CRPS wk1-3 | gain vs foil | folds won | DSR | p | clauses |
|---|---|---|---|---|---|---|---|---|
| `none` (foil) | foil | 0.000 | 9.4642 | — | — | — | — | — |
| `bucket_shift` | candidate | 1.517 | 9.3793 | +0.0848 | 8/8 | 0.998 | 0.0047 | ✅ |
| `per_week_shift` | candidate | 1.555 | 9.3908 | +0.0734 | 6/8 | 0.703 | 0.0712 | ✅ |
| `linear_decay` | candidate | 1.526 | 9.3822 | +0.0820 | 7/8 | 0.953 | 0.0194 | ✅ |
| `shrunk_bucket` | candidate | 0.997 | 9.3918 | +0.0723 | 8/8 | 0.999 | 0.0065 | ✅ |
| `pooled_level` | lose | 0.239 | 9.4497 | +0.0145 | 6/8 | 0.949 | 0.0118 | ✅ |
| `week_blind` | lose | 0.239 | 9.4497 | +0.0145 | 6/8 | 0.949 | 0.0118 | ✅ |
| `over_scale` | lose | 3.034 | 9.3723 | +0.0918 | 6/8 | 0.826 | 0.0463 | ❌ C8 |

Foil cold-start bias **+2.074 pts** (pooled +0.362) — the quantity VAL2 measured and this study tries to remove.

## 1b. Calibration — the AC's "without degrading aggregate PIT"

| arm | wk1-3 bias | wk1-3 PIT | wk1-3 calib80 | pooled bias | **pooled PIT** | pooled calib80 |
|---|---|---|---|---|---|---|
| `none` (foil) | +2.074 | 0.0653 | 0.8270 | +0.362 | **0.0261** | 0.8080 |
| `bucket_shift` | +0.557 | 0.0613 | 0.8302 | +0.102 | **0.0269** | 0.8086 |
| `per_week_shift` | +0.520 | 0.0581 | 0.8299 | +0.102 | **0.0253** | 0.8080 |
| `linear_decay` | +0.549 | 0.0628 | 0.8311 | +0.102 | **0.0267** | 0.8087 |
| `shrunk_bucket` | +1.078 | 0.0656 | 0.8269 | +0.190 | **0.0262** | 0.8080 |
| `pooled_level` | +1.867 | 0.0670 | 0.8296 | +0.155 | **0.0273** | 0.8080 |
| `week_blind` | +1.867 | 0.0670 | 0.8296 | +0.327 | **0.0256** | 0.8084 |
| `over_scale` | -0.960 | 0.0544 | 0.8277 | -0.158 | **0.0264** | 0.8081 |

C1's tolerance is **+0.002** on the pooled PIT max-decile-dev, and C2/C3 floor `calib_80` at **0.78** — a FLOOR, never a target (NF1.8/E2.1-r).

## 2. The AC's headline — the wk1-3 over-tilt

On the 715 close-carrying cold-start rows (over actually hit **0.456**). ⚠️ DESCRIPTIVE — the only market-touching number here, never a clause and never an edge claim.

| arm | model → over | mean μ − close (pts) |
|---|---|---|
| `none` | 0.613 | +1.357 |
| `bucket_shift` | 0.502 | -0.157 |
| `per_week_shift` | 0.509 | -0.160 |
| `linear_decay` | 0.497 | -0.162 |
| `shrunk_bucket` | 0.519 | +0.147 |
| `pooled_level` | 0.608 | +1.244 |
| `week_blind` | 0.608 | +1.244 |
| `over_scale` | 0.410 | -1.672 |
| `oracle_bucket` | 0.448 | -1.114 |
| `matched_n_bucket` | 0.481 | -0.560 |

## 3. Gates

- **PBO** 0.5300 (gate < 0.2) over 15 buckets, 1,000 CSCV combos — ❌
- **DSR** gate ≥ 0.95; `V` **binding (full field)** 0.05878, DSR-CONV variant 0.09080 (reported, NOT binding)
- **BH** α 0.05 → cutoff 0.03571
- **Fold consistency** (`cv_power.fold_consistency_clause`): 6 of 8 wins required, attainable True, false-fire 0.1445 (legacy would ask 5 at 0.3633)
- **PBO companions** — CANDIDATE spread 0.0125 CRPS (0.13 % of the foil); whole-field spread 0.0774 (NF1.8: a spread over a field containing its own pre-registered nulls measures the NULLS); flip distribution {'none': 0, 'bucket_shift': 1, 'per_week_shift': 3, 'linear_decay': 1, 'shrunk_bucket': 0, 'pooled_level': 0, 'week_blind': 0, 'over_scale': 3}

**PBO sensitivity** — the pre-registered population BINDS; the rest are labelled diagnostics proving the null does not rest on the gate choice (NF-D15 g″). ⛔ None of them may be adopted after the fact (MH2.2 / E2.1-r).

| population | arms | PBO | binds |
|---|---|---|---|
| `binding_preregistered` — §5's declared population: the foil + all 7 scored arms. | 8 | **0.5300** | ✅ BINDING |
| `eligible_set_only` — the search the SELECTION actually ran — the foil + the 4 SELECTABLE candidates. Reported because CLAUDE.md's own PBO note says the eligible set is the right population; ⛔ but it was NOT what this study pre-registered, so it cannot be adopted here (MH2.2). | 5 | **0.7010** | diagnostic |
| `two_arm_decision` — the question a PM actually faces — correct vs do nothing. A 2-arm CSCV has almost no search to overfit, so this is a lower bound, not a gate. | 2 | **0.0000** | diagnostic |

## 4. Anchors

- headline bucket peek CRPS **9.3464** vs its matched-n control **9.4154** ⇒ peek gain +0.0689, pair **ACTIVE**
- a peeking oracle is a floor only at MATCHED family AND MATCHED sample (NF1.7 (b) / NF1.9 (f)); it is computed PER FORM (NF-D16 g‴) and a peek that does not beat its own matched-n control could not act, so its floor is INACTIVE — uninformative, never a pass and never a fail (NF-W6d / NF-D20).

| arm | form | own-form peek | its matched-n | peek gain | pair | arm − peek | C8 state |
|---|---|---|---|---|---|---|---|
| `bucket_shift` | `bucket` | 9.3464 | 9.4154 | +0.0689 | ACTIVE | +0.0329 | FLOORED |
| `per_week_shift` | `per_week` | 9.2117 | 9.4692 | +0.2575 | ACTIVE | +0.1790 | FLOORED |
| `linear_decay` | `linear` | 9.2845 | 9.4361 | +0.1516 | ACTIVE | +0.0977 | FLOORED |
| `shrunk_bucket` | `shrunk` | 9.3762 | 9.4218 | +0.0456 | ACTIVE | +0.0156 | FLOORED |
| `pooled_level` | `pooled_all` | 9.4449 | 9.4154 | -0.0295 | INACTIVE | +0.0048 | INACTIVE |
| `week_blind` | `pooled_cold` | 9.4449 | 9.4154 | -0.0295 | INACTIVE | +0.0048 | INACTIVE |
| `over_scale` | `over2` | 9.4177 | 9.5265 | +0.1088 | ACTIVE | -0.0454 | BEATEN |

## 4b. Channel attribution — paired, never a rank (NF-D10 / NF-D15 g′)

| channel | pair | cell | mean gain | folds + | p |
|---|---|---|---|---|---|
| magnitude | `bucket_shift − week_blind` | wk1-3 | +0.0704 | 7/8 | 0.0051 |
| scoping | `week_blind − pooled_level` | pooled (all rows) | +0.0000 | 3/8 | 0.4928 |

_the primary metric is the wk1-3 cell (the only rows the mechanism can move — NCAAF-P2.1 (f)); the scoping channel is invisible there BY CONSTRUCTION and is therefore read on the pooled cell. Stated as an arithmetic property of the design, not discovered from a score._

**Instrument control** — closed-form vs ensemble CRPS on the foil: 5000 draws 0.02125  →  20000 draws 0.01234 (0.130 % of the CRPS; shrinks with draws: ✅). the closed-form Gaussian CRPS and the ensemble identity score the SAME predictive; a disagreement would mean one of them is not scoring what this study claims to score, and it would be invisible in every headline. Read the CONVERGENCE, not the single gap: a fixed residual gap would be a real disagreement, a gap that shrinks ~1/√n is the sampler's own error.

## 5. The null, classified

- best candidate **`bucket_shift`**
- `cv_power.classify_null` state **`POWER_LIMITED`** — `crps_total_wk1_3`: insufficient recorded statistics to certify the null as powered. Absent a detectability figure the honest default is POWER-LIMITED — a null is trustworthy only when something was computed to make it so.
- **recorded state `DEFLATION_REFUSED_PBO`** (binding half: deflation)
- the refusal is caused by a pre-registered DEFLATION gate that WAS evaluated and FAILED. ⚠️ `cv_power.classify_null` takes no PBO argument at all — it can express PBO-UNDEFINED (too few folds/arms) but NOT PBO-EVALUATED-AND-FAILED — so its own state structurally cannot see the gate that bound here. That is an INSTRUMENT GAP, recorded rather than worked around; the instrument's state is preserved above and is not the verdict. ⛔ No fold/season re-test trigger is published: the admissible remedy for a PBO refusal is a FORWARD-registered narrower coherent family (or a forward-registered PBO population), never more seasons and NEVER a post-hoc re-cut of a field already scored (MH2.2).
- re-test trigger: `None`
- `field_remedy_admissible` = `True` (declared field 8; MH2.7 — read the FLAG, not the prose)
- **deflation gates failed: pbo**
- ⚠️ This study pre-registered a materiality band in POINTS (inherited from VAL2) but NOT a practically-meaningful CRPS effect in SD units, so `classify_null` correctly falls through to its honest default rather than certifying the null as powered. ⛔ Supplying one now would be re-deriving a bar from the answer (E2.1-r); it is a pre-registration gap, recorded as such, and a successor registers it forward.

## 6. Reproduction pin

Anchored on the PARENT (`ncaaf_val3_s1_serve_reanchor.json (S1-serve --stage finalize, repaired _clv_eval)`) and the cache meta — ⛔ never on VAL3's own output. All legs PASS ✅.

| leg | got | expected | ok |
|---|---|---|---|
| `cache_assembled_at` | 2026-08-22 | 2026-08-22 | ✅ |
| `n_with_close` | 4187 | 4187 | ✅ |
| `n_oos_games` | 6024 | 6024 | ✅ |
| `fold_years` | [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | ✅ |

_Vintage-bound on purpose: a re-assemble moves the population and this pin HALTs. The remedy is to re-run the parent and re-anchor from ITS output._
