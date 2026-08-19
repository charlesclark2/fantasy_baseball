# NCAAF-P2.5 — total / joint-distribution SHAPE repair

_Decided 2026-08-19 · 8 season-forward purged folds (2018–2025) · declared field 10 · `best_alpha = 0` · market-blind · deploy-held_

## Verdict — **REFERENCE_STANDS**

No candidate cleared every pre-registered clause under deflation ⇒ **the served P1.4/S1 shape stands.** A null here is a valid, recorded outcome, not a failed story.

## The premise, re-measured

The story card cites the incumbent's total PITdev as **0.0218** — that is `ncaaf_p1_4_calibration.json` (contract `strength_only`), a **superseded** contract. The config that actually SERVES (`ncaaf_s1_serve_calibration.json`, contract `strength_pace`) is at **0.0173 and PIT-flat**; P1.4's failure was `pit_mean_dev` 0.0263, a LOCATION defect the S1 pace term largely repaired. The foil here is therefore the SERVED config, not the card's — measuring against 0.0218 would hand every candidate a 0.0045 head start it did not earn.

Reproduction gate R: **PASS** — refit σ {'sigma_margin': 16.0848, 'sigma_total': 16.6424, 'rho': 0.054} vs served {'sigma_margin': 16.0848, 'sigma_total': 16.6424, 'rho': 0.054} (δ {'sigma_margin': 0.0, 'sigma_total': 0.0}, tol 0.25 pts).

## Data prerequisite — weather

**ABSENT.** no weather feed exists in the NCAAF lakehouse (0 of 207 matrix columns match weather|temp|wind|precip|humid; absent from both inventories) ⇒ the card's weather-driven variance terms are DROPPED, not fabricated. `game_venue_is_dome` / `game_venue_elevation_m` are registered as PARTIAL environment proxies and labelled as such.

## Leaderboard (primary = pooled total-CRPS, lower better)

| arm | doc §4.1 item | crps_total | gain vs foil | folds won | DSR | p | total PITdev | clauses |
|---|---|---|---|---|---|---|---|---|
| **`incumbent` (FOIL)** | the served form | 9.40526 | — | — | — | — | 0.0170 | — |
| `key_number` | discrete-score simulation (mass at 3/7/10/14) | 9.37661 | +0.02865 | 7/8 | 0.311 | 0.0049 | 0.0124 | ❌ C8 |
| `skew_normal` | skew-normal | 9.39268 | +0.01258 | 6/8 | 0.002 | 0.0547 | 0.0065 | ❌ C5 |
| `skew_t` | skew-t | 9.39313 | +0.01213 | 6/8 | 0.004 | 0.0532 | 0.0071 | ❌ C5 |
| `copula` | copula w/ independent (non-parametric) marginals | 9.39622 | +0.00904 | 6/8 | 0.001 | 0.0837 | 0.0092 | ❌ C5 |
| `student_t` | bivariate Student-t | 9.40623 | -0.00097 *(TIE)* | 4/8 | 0.000 | 0.6646 | 0.0189 | ❌ C2, C6 |
| `mixture` | Gaussian / regime mixture | 9.40697 | -0.00171 | 2/8 | 0.000 | 0.7907 | 0.0116 | ❌ C5 |
| `quantile_boost` | quantile / distributional-boosting foil | 9.43566 | -0.03040 | 2/8 | 0.000 | 0.9809 | 0.0139 | ❌ C5 |
| `cond_het` | bivariate Gaussian w/ conditional heteroskedasticity | 9.44038 | -0.03512 | 0/8 | 0.000 | 0.9951 | 0.0148 | ❌ C5, C6 |
| `home_away` | separate home/away score distributions → transform | 9.46567 | -0.06041 | 1/8 | 0.000 | 0.9979 | 0.0382 | ❌ C1, C2, C3, C5, C6 |

## Deflation

- **PBO 0.000** (PASS < 0.2) over 32 buckets / 1000 CSCV combos.
- **DSR** on the per-FOLD matched-pair series, `n_trials = 10` (the declared field), `V = 0.903946` measured over the REAL arms only — ⛔ anchors are excluded from both, because an anchor that polices the metric must not set the gate's own bar (MH2.1 a).
- **BH-FDR** α=0.05 across the 9 candidate contrasts; cutoff 0.005556.
- Contender spread **0.947%** of the foil's CRPS; per-fold flip distribution `{'incumbent': 0, 'cond_het': 0, 'student_t': 1, 'skew_normal': 1, 'skew_t': 0, 'mixture': 0, 'copula': 0, 'home_away': 0, 'key_number': 6, 'quantile_boost': 0}`.

  E2.1-r: a HIGH PBO over a field whose candidates genuinely TIE is the NULL — 'which tied candidate wins is noise' — not evidence of overfitting; a high PBO with a WIDE spread IS overfitting. The SPREAD is the discriminator, so it is reported beside the flip distribution.

## Run-validity anchors (⛔ diagnostic, never trials)

| anchor | pre-registered expectation | observed |
|---|---|---|
| `permute` | must LOSE to cond_het (it destroys the conditional structure while preserving the marginal); it lands at/near the incumbent, and beating cond_het would mean the conditional-variance channel is not real | `{"permute_crps": 9.43463, "cond_het_crps": 9.44038, "permute_minus_cond_het": -0.00575, "loses_to_cond_het": false, "tie": false}` |
| `zero_width` | must LOSE the metric AND FAIL the coverage floor (maximally sharp) | `{"pooled_crps_total": 11.83017, "total_calib_80": 0.1819, "margin_calib_80": 0.1972, "satisfies_coverage_floor": false, "loses_the_metric": true}` |
| `max_width` | must SATISFY the coverage floor and LOSE the metric — the NF1.8 proof that the floor is a CONSTRAINT a degenerate satisfies, not a criterion it wins | `{"pooled_crps_total": 14.01781, "total_calib_80": 0.999, "margin_calib_80": 0.9998, "satisfies_coverage_floor": true, "loses_the_metric": true}` |
| `coverage_target` | must SATISFY the coverage constraint and LOSE the metric — the E2.1-r proof that calib_80 is a FLOOR and never a target | `{"pooled_crps_total": 9.404, "total_calib_80": 0.8013, "margin_calib_80": 0.7981, "satisfies_coverage_floor": true, "loses_the_metric": false, "clauses": {"C1_total_pit_flat": {"ok": true, "pit_dev": 0.0178, "pit_mean_dev": 0.0149}, "C2_total_pit_repaired": {"ok": false, "foil": 0.017, "arm": 0.0178, "improvement": -0.0008, "required": 0.001}, "C3_margin_pit_flat": {"ok": true, "pit_dev": 0.0072}, "C4_coverage_floor": {"ok": true, "total": 0.8013, "margin": 0.7981, "floor": 0.78}, "C5_tail_crps": {"ok": true, "arm": 5.49366, "foil": 5.49348}, "C6_joint_calibration": {"ok": true, "arm": 0.0127, "foil": 0.013}, "C7_mean_preserved": {"ok": true, "max_abs_shift": 0.0273, "tol": 0.15}, "all_ok": false}, "ships_under_the_full_rule": false}` |

**Conditional-variance channel** (the `permute` read — REPORTED, never a validity gate): the shuffled-driver fit came in `-0.00575` against the real one ⇒ the channel is **NOT REAL**. REPORTED, never a validity gate. `permute` is `cond_het` with the driver rows SHUFFLED against the residuals: it destroys the conditional structure and leaves the marginal untouched. If the shuffled fit BEATS the real one, the registered variance drivers carry no information beyond the marginal and the real fit is paying an overfitting cost for them — a clean NEGATIVE result about the drivers, not a broken measurement.

**Per-form oracle floor** (NF-D16 g‴ — one ceiling per form, because the families NEST and a single field-wide ceiling would falsely veto a legitimately better nested form; a TIE is INACTIVE, never a refusal — NF-W6d):

| arm | pooled CRPS | own-form PEEKING oracle | gap | state | self-consistency (diagnostic) |
|---|---|---|---|---|---|
| `quantile_boost` | 9.43566 | 9.21659 | +0.21907 | OK | 9.83632 |
| `cond_het` | 9.44038 | 9.36747 | +0.07291 | OK | 9.70178 |
| `skew_normal` | 9.39268 | 9.38050 | +0.01218 | OK | 9.55535 |
| `skew_t` | 9.39313 | 9.38070 | +0.01243 | OK | 9.52432 |
| `key_number` | 9.37661 | 9.38077 | -0.00416 | BEATEN | 9.31785 |
| `copula` | 9.39622 | 9.38134 | +0.01488 | OK | 9.58377 |
| `mixture` | 9.40697 | 9.38732 | +0.01965 | OK | 9.58575 |
| `coverage_target` | 9.40400 | 9.39868 | +0.00532 | OK | 9.46337 |
| `incumbent` | 9.40526 | 9.39892 | +0.00634 | OK | 9.56473 |
| `student_t` | 9.40623 | 9.39989 | +0.00634 | OK | 9.52287 |
| `permute` | 9.43463 | 9.42929 | +0.00534 | OK | 9.48436 |
| `home_away` | 9.46567 | 9.45500 | +0.01067 | OK | 11.01667 |
| `zero_width` | 11.83017 | 11.82974 | +0.00043 | INACTIVE_TIE | 1.69184 |
| `max_width` | 14.01781 | 13.86013 | +0.15768 | OK | 28.69419 |

## Null classification

- best arm `key_number` → recorded state **CONSTRAINT_REFUSED** (binding half: **constraint**).
- `cv_power.classify_null` state `DSR_UNREACHABLE` — passed the series' OWN measured skew/kurtosis and `declared_field_size=10` (⛔ never the Gaussian default: that disagreement publishes a misleading 'come back with more seasons' trigger — NCAAF-P2.1-S1b defect 1).
- ship clauses that BOUND: `C8_own_form_floor`.
- the refusal is caused by a pre-registered SHIP CLAUSE, not by the statistic — no fold count moves a clause, so a `POWER_LIMITED`-style 'more seasons' trigger would be actively misleading (NF-D18). The instrument's own state is preserved above.
- instrument reason: `crps_total`: the winner's per-fold Sharpe 1.243 sits at or BELOW the 9-arm field's deflated benchmark SR0 1.446, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- instrument re-test trigger: field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)

## Honest framing

best_alpha = 0 — this story can only improve the SHAPE/honesty of a probability, never claim an edge. Market-blind. NCAAF is not served, so a survivor is a research-artifact re-point, never a deploy.
