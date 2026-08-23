# NCAAF-VAL3b — the cold-start μ_total correction as ONE pre-registered contrast

**Verdict: `SHIP_CORRECTION`.** Market-blind · `best_alpha = 0` · no serving change, no registry edit, no refit of a served artifact, no bet.

_Cache assembled 2026-08-23 · 6,024 OOS games · 8 purged folds 2018–2025 · served config `ridge`/`strength_pace`/`strength_posterior` · declared field 2 (1 selectable)_

## 1. The contrast

| arm | role | δ̄ (pts) | CRPS wk1-3 | gain vs foil | folds won | DSR | p | C1–C8 | M1/M2 |
|---|---|---|---|---|---|---|---|---|---|
| `none` (foil) | foil | 0.000 | 9.4642 | — | — | — | — | — | — |
| `bucket_shift` | candidate | 1.517 | 9.3793 | +0.0848 | 8/8 | 1.000 | 0.0047 | ✅ | ✅ |

Foil cold-start bias **+2.074 pts** (pooled +0.362); after the correction **+0.557** (pooled +0.102).

Per-fold CRPS improvement (foil − arm): 2018 +0.0085, 2019 +0.0311, 2020 +0.0899, 2021 +0.0651, 2022 +0.0274, 2023 +0.1020, 2024 +0.2113, 2025 +0.1433

## 2. Materiality — the bars VAL3 recorded as a pre-registration gap and handed FORWARD

| bar | required | observed | ok |
|---|---|---|---|
| **M1** — wk1-3 \|bias\| reduction (VAL2's inherited band) | ≥ 1.00 pts | **+1.517 pts** (+2.074 → +0.557) | ✅ |
| **M2** — relative wk1-3 CRPS gain (closed form from VAL2's 0.15 σ / 1.0 pt) | ≥ 0.7543 % | **0.8962 %** | ✅ |

_M2 re-derived at run time from VAL2's two constants: C(0.150) = 0.57053077, C(0.085) = 0.56622711 ⇒ 0.7543 % (module literal 0.7543 %). Removing the bias ENTIRELY is worth 1.1115 %, so M2 asks for 68 % of the whole available headroom. Zero free parameters._

## 3. Calibration — the AC's "without degrading aggregate PIT"

| arm | wk1-3 bias | wk1-3 PIT | wk1-3 calib80 | pooled bias | **pooled PIT** | pooled calib80 |
|---|---|---|---|---|---|---|
| `none` (foil) | +2.074 | 0.0653 | 0.8270 | +0.362 | **0.0261** | 0.8080 |
| `bucket_shift` | +0.557 | 0.0613 | 0.8302 | +0.102 | **0.0269** | 0.8086 |

C1's tolerance is **+0.002** on the pooled PIT max-decile-dev; C2/C3 floor `calib_80` at **0.78** — a FLOOR, never a target (NF1.8/E2.1-r).

## 4. Ship clauses C1–C8 — the PARENT's function, called (not a copy)

| clause | ok | detail |
|---|---|---|
| `C1_pooled_pit_not_degraded` | ✅ | arm=0.02691, foil=0.02606, tol=0.002 |
| `C2_pooled_calib_floor` | ✅ | value=0.8086, floor=0.78 |
| `C3_cold_calib_floor` | ✅ | value=0.8302, floor=0.78 |
| `C4_market_blind_estimator` | ✅ | enforced_at=assert_estimator_is_market_blind |
| `C5_week_scoped` | ✅ | max_late_crps_gap=0.0, scope=cold, tol=1e-09 |
| `C6_margin_frozen` | ✅ | enforced_at=no arm touches mu_margin (by construction) |
| `C7_sigma_frozen` | ✅ | max_gap=0.0, tol=1e-09 |
| `C8_own_form_oracle_floor` | ✅ | state=FLOORED, gap=0.032903536034151415 |

## 5. Gates

- **PBO / CSCV — `INAPPLICABLE`.** a SINGLE pre-registered contrast has NO SEARCH to overfit — CSCV/PBO asks whether the in-sample winner of a search holds up out of sample, and there is no winner to pick. `cv_power.classify_null`'s own n_arms<2 branch says exactly this and emits NO re-test trigger. ⛔ Recorded INAPPLICABLE, never 'passed'; a two-arm CSCV number is deliberately NOT computed even as a diagnostic, because reproducing the figure VAL3 already reported as a lower bound would read as 'the gate we failed now passes' — the misreading this successor shape exists to avoid (§4.1).
- **DSR** 0.9996 (gate ≥ 0.95); observed SR 1.2519 vs **SR0 0.1838**, `V` = 0.12500 (the asymptotic 1/n_obs default); ceiling at 8 folds 0.99991 ⇒ the gate is REACHABLE at this design.
  - `V` is UNDEFINED at one selectable arm (a variance needs ≥2 points), so `deflated_sharpe`'s documented fallback — the ASYMPTOTIC null variance of a Sharpe estimate, V = 1/n_obs — is what this study DECLARED FORWARD. It is a DESIGN quantity: it depends only on the fold count. ⛔ Importing VAL3's measured V (0.05878) would be a dispersion from a field this registration does not have. ⭐ The resulting bar SR0 = 0.18376 is LOWER than VAL3's 0.35374, and that is the whole arithmetic content of the successor shape: a 2-arm design carries almost no expected-max inflation. It is legitimate ONLY because the family is declared FORWARD on a mechanism argument and scored whole — never trimmed after the fact (MH2.2). The NF-W8-0d lockstep invariant does NOT apply: V is not a field variance.
  - **DSR sensitivity — did the arm clear the gate, or was the gate lowered?** ⭐ NON-BINDING, and it answers the first question a sceptical reader asks of a successor whose field is smaller than its parent's: did the arm CLEAR the gate, or was the gate LOWERED? Re-scored under VAL3's own recorded `V`/`n_trials` and under the strictest combination constructible from either study's declared quantities. ⛔ It changes no verdict — the binding reading is §4.2's, declared forward before scoring; adopting a different one after the fact would be the E2.1-r inversion.

    | reading | n_trials | `V` | SR0 | DSR | clears ≥0.95 | binds |
    |---|---|---|---|---|---|---|
    | **VAL3b, declared forward** | 2 | 0.12500 | 0.18376 | 0.999627 | ✅ | ✅ **BINDING** |
    | `val3_full_field` | 8 | 0.05878 | 0.35373 | 0.997713 | ✅ | sensitivity |
    | `val3_dsr_conv_variant` | 8 | 0.09080 | 0.43965 | 0.994832 | ✅ | sensitivity |
    | `strictest_constructible` | 8 | 0.12500 | 0.51584 | 0.989932 | ✅ | sensitivity |

- **BH** α 0.05 → cutoff 0.05000, p 0.0047 — ✅. ONE hypothesis ⇒ the Benjamini–Hochberg cutoff IS α. Stated so a reader sees the multiplicity correction became trivial as a CONSEQUENCE of the declared design, not because it was switched off.
- **Fold consistency** (`cv_power.fold_consistency_clause`): 6 of 8 required, attained 8 — ✅; false-fire 0.1445 (legacy would ask 5 at 0.3633)
- **Fold flips** (which arm wins each fold's cold cell): {'none': 0, 'bucket_shift': 8}

## 6. Anchors

- headline bucket peek CRPS **9.3464** vs its matched-n control **9.4154** ⇒ peek gain +0.0689, pair **ACTIVE**
- a peeking oracle is a floor only at MATCHED family AND MATCHED sample (NF1.7 (b) / NF1.9 (f)); it is computed PER FORM (NF-D16 g‴) and a peek that does not beat its own matched-n control could not act, so its floor is INACTIVE — uninformative, never a pass and never a fail (NF-W6d / NF-D20).

| arm | form | own-form peek | its matched-n | peek gain | pair | arm − peek | C8 state |
|---|---|---|---|---|---|---|---|
| `bucket_shift` | `bucket` | 9.3464 | 9.4154 | +0.0689 | ACTIVE | +0.0329 | FLOORED |

**Channel attribution — CITED from VAL3, not re-measured.** magnitude (`bucket_shift − week_blind`, wk1-3) +0.0704, 7/8, p 0.0051; scoping (`week_blind − pooled_level`, pooled) +0.0000, 3/8, p 0.4928. ⛔ CITED from `ncaaf_val3_cold_start_mu.md` §4b, NOT re-measured here. VAL3's matched foils are honest, in-principle-shippable estimators; calling one a 'diagnostic' to keep it out of VAL3b's multiplicity count would be exactly the laundering MH2.2 forbids, so they are OUT of this field entirely. The cost is disclosed: VAL3b does not independently re-attribute the channel.

**Instrument control** — closed-form vs ensemble CRPS on the foil: 5000 draws 0.02125  →  20000 draws 0.01234 (0.130 % of the CRPS; shrinks with draws: ✅). the closed-form Gaussian CRPS and the ensemble identity score the SAME predictive. Read the CONVERGENCE, not the single gap.

## 7. The wk1-3 over-tilt — DESCRIPTIVE

On the 715 close-carrying cold-start rows (over actually hit **0.457**). ⚠️ DESCRIPTIVE — the only market-touching number here, never a clause and never an edge claim.

⭐ **Implementation, NAMED:** ncaaf_val3_cold_start_mu.over_tilt_report — a `game_id` join that takes no positional index into any array (the `_clv_leg`-immune implementation). ⛔ NOT `_clv_eval`.

| arm | model → over | mean μ − close (pts) |
|---|---|---|
| `none` | 0.614 | +1.370 |
| `bucket_shift` | 0.502 | -0.144 |
| `oracle_bucket` | 0.448 | -1.101 |
| `matched_n_bucket` | 0.481 | -0.546 |


## 9. Reproduction pin

Anchored on the PARENT (`ncaaf_val3_s1_serve_reanchor.json (S1-serve --stage finalize, repaired _clv_eval)`) and the fold structure — ⛔ never on VAL3b's own output. Binding legs PASS ✅.

| leg | got | expected | binds | ok |
|---|---|---|---|---|
| `n_with_close` | 4187 | 4187 | ✅ | ✅ |
| `n_oos_games` | 6024 | 6024 | ✅ | ✅ |
| `fold_years` | [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | ✅ | ✅ |
| `cache_assembled_at` | 2026-08-23 | — (reported) | ❌ reported only | — |

_The `cache_assembled_at` leg is REPORTED, not pinned — declared forward in §7 of the pre-registration, because `assemble_cache` stamps `date.today()` and that leg moves with the clock whatever the population is. The three population legs HALT._

## 10. Ship gating

⛔ SHIP_CORRECTION does NOT serve anything. A pre-opener ship needs the S1-serve-class train/serve PARITY check against the SERVED artifact contract AND explicit operator approval; otherwise DEPLOY-HELD with the gap named (spec AC (a)/(b)). Nothing serves from this session.
