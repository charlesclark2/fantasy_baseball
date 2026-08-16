# MH2.6 — PRE-REGISTRATION (written and committed BEFORE any statistic was computed)

**Story:** MH2.6 · MLB game-model calibration audit (`total_runs` + `home_win`) — diagnose drift vs
noise, recalibrate only if warranted.
**Branch:** `mh2-6-cal-audit` · **`best_alpha = 0`** · **deploy-held**.
**Harness:** `betting_ml/scripts/mh2_6_calibration_audit.py` (Snowflake-free; DuckDB over the S3
lakehouse).

> Everything below is fixed in SOURCE before any arm, window or statistic is scored. A choice made
> after seeing a number is window-shopping — the defect the MH2 lineage exists to stop (E2.1-r).

---

## 0. The trigger, stated honestly

The operator's report is that `total_runs` / `h2h` "feel rough over two days". At `best_alpha = 0`
**no bet rides on either model**, and two days is ~24–30 games. The prior is therefore **noise**, and
the pre-registered default verdict is **NO ACTION**. This study exists because the program has never
run a calibration audit on a *fresh served window* — not because two days is evidence.

⛔ **A retrain is NOT on the table in Phase 1.** Phase 2 fires only if Phase 1 finds a defect
**outside noise**, and then only as a pre-registered §0.5 fix aimed at the *specific* defect found.

---

## 1. LOCK — POPULATION

The **SERVED** rows, i.e. what the app actually showed, read from the S3
`daily_model_predictions` parquet (the artifact `write_serving_store --s3` / `write_api_cache`
serve), joined to realized outcomes in `mart_game_results`.

| lock | value |
|---|---|
| era | the **E13.11 champion bundle**: `model_version ∈ {'v6', 'pre_lineup_v6'}` (post_lineup v6 from 2026-06-23; morning pre_lineup_v6 from 2026-06-24) |
| tiers | `post_lineup` (PRIMARY — the final served tier) and `morning` (declared secondary) |
| de-dup | latest `inserted_at` per `(game_pk, prediction_type)` — the row actually served |
| backfills | `is_backfill = TRUE` and `prediction_type = 'backfill'` EXCLUDED (not live-served) |
| outcomes | `mart_game_results`, `game_type = 'R'`, `home_final_score IS NOT NULL` |
| anchor | the newest `game_date` carrying finals for the tier |
| ⛔ totals exclusion | rows stamped `totals_model_version = 'mh2_1'` are DROPPED **from the totals leg only** — those 15 post_lineup rows on 2026-08-02 were priced by the MH2.1 challenger that was rolled back the same day. Their `home_win` side is still v6, so they are KEPT in the h2h leg. |

**Targets.** `total_runs`: served predictive `Normal(pred_total_runs, pred_total_runs_scale)` vs
`home_final_score + away_final_score`. `home_win`: served `calibrated_win_prob` vs `home_team_won`.

---

## 2. LOCK — WINDOWS

Every served row post-dates the champion's fit (E13.11, 2026-06-23), so **the whole served era is
out of sample**. This is the MH2.1 rollback's "split at the incumbent's fit date" rule already
satisfied by construction, and it is what makes the temporal contrast admissible.

| window | definition | role |
|---|---|---|
| `RECENT` | the 30 days ending at the anchor | the complaint window |
| `EARLIER` | the remainder of the E13.11 served era (era start → RECENT start − 1) | the within-champion control |
| `TRIGGER` | the last **2** dates carrying finals | the cohort that prompted the story |
| `FULL` | the whole E13.11 served era | the absolute-calibration read |

**Declared sensitivity (not a second chance at the answer):** the same contrast under a
**median-date split** of the served era. Reported whatever it says.

⛔ **The training-era baseline is IN-SAMPLE and is therefore NOT a drift bar.** The champion was fit
on its training era, so any in-sample reference is optimistic **by construction**; "recent is worse
than training-era" would be true of a perfectly healthy model. It is reported (where obtainable) as
an anchor for *what the fit targeted*, and **no drift claim may rest on it**. The drift bar is
`RECENT` vs `EARLIER` — both out of sample, same champion, same serving pipeline.

---

## 3. LOCK — STATISTICS

### 3.1 `total_runs`

`total_runs` is an **integer count** and the served predictive is continuous, so PIT is taken with a
**continuity correction and randomization** (E2.1-r: for a discrete target, gate on randomized-PIT
flatness, never on raw interval coverage):

```
u = Φ((y − 0.5 − μ)/σ) + V · [ Φ((y + 0.5 − μ)/σ) − Φ((y − 0.5 − μ)/σ) ],   V ~ U(0,1)
```

- **PRIMARY flatness:** max-decile deviation (MDD) of `u`. Secondary: KS.
- **Coverage** at 80% / 50%, read off `u`. ⛔ **A FLOOR AND A REFERENCE, NEVER A TARGET** (NF1.8):
  no arm is selected for being closer to nominal, and the naive integer-interval coverage is
  reported *beside* it purely to show the E2.1-r inflation.
- **Level:** mean residual (`y − μ`) with CI; MAE; RMSE.
- **Proper score:** CRPS (Normal closed form).
- **⭐ Conditional instrument (MH2.5):** `RMS |Var(z) − 1|` across strata, `z = (y − μ)/σ`,
  anchored on the analytic truth 1.0 — never on the incumbent (MH2.1 (b)). Reported beside its
  **noise floor** (`metric_noise_floor`), because a difference smaller than the floor is not a
  measurement.

### 3.2 ⭐ LOCK — THE STRATIFIER IS VALIDATED FIRST, OR NOTHING IS READ OFF IT

This is the exact defect that caused the MH2.1 rollback: *a conditional-calibration result is a
property of its stratifier*. Before any `Var(z)` number is read, each partition must publish its
realized-SD-per-bin table (n, mean stratifier, realized SD, **per-bin SE**, mean |resid|) and clear
the **pre-registered** bar, reusing MH2.5's implementation verbatim
(`realized_dispersion_table`, `STRATIFIER_MIN_RHO = 0.30`, `STRATIFIER_MIN_ENDPOINT_SE = 2.0`):

| stratifier | role |
|---|---|
| `incumbent_sigma` — the served v6's OWN σ | **PRIMARY** (the story's ask) |
| `incumbent_mean` — the served μ | SECONDARY (the partition MH2.5 found validated on the wide window) |

A partition that fails is **DISQUALIFIED** and **no `Var(z)` is read off it** — a failed validation
is a finding, not a licence to read the number anyway (NF1.7 (a)).

**Strata count is derived from `n` ALONE — a design quantity known before any result** (NF1.8):
`k = clip(floor(n / 60), 3, 10)`, i.e. ≥60 rows per bin so a bin's SD carries an SE ≤ ~9% of itself.
`k = 10` is reported as a declared sensitivity.

### 3.3 `home_win`

Calibration-in-the-large (mean `p̂` − realized rate); Brier + **Murphy decomposition**
(reliability / resolution / uncertainty); ECE; log loss; reliability curve over `k` quantile bins
(same `k` rule).

⚠️ **Stated in advance so it cannot be mistaken for a finding:** the registry records v6 `home_win`
as a **confirmed thin-signal target** whose calibrated served spread is ≈0.035. A reliability
*slope* is therefore barely estimable at any n available here, and a flat reliability curve is the
**expected** shape, not evidence of a defect. The served `p̂` SD is reported so this is visible.

---

## 4. ⭐ LOCK — HOW "WITHIN NOISE" IS DECIDED (two instruments, not one)

1. **Bootstrap CI** (2,000 resamples, seed 42) on every statistic and on every RECENT−EARLIER
   difference — the *sampling uncertainty of the statistic*.
2. **⭐ CALIBRATED NULL** (2,000 parametric simulations, seed 42) — outcomes re-drawn from the
   **served predictive itself** (`y* ~ discretized Normal(μ, σ)`; `y* ~ Bernoulli(p̂)`), holding
   `n` and the per-game μ/σ/p̂ fixed. This answers the question actually being asked: *would a
   perfectly calibrated served model produce a window that looks this rough?* A statistic inside its
   calibrated null is **within noise**, full stop.

A defect is declared **only** when the observed statistic sits **outside** the calibrated null
(two-sided, α = 0.05) **and** the RECENT−EARLIER difference CI excludes zero. Either alone is not a
defect: the first without the second is a *standing* property of the model, not drift; the second
without the first is a difference between two windows that are both fine.

### 4b. ⭐ AMENDMENT — the verdict-bearing family is small, declared, and BH-corrected

**Added 2026-08-15, BEFORE any real served statistic was read; the reason is a control result, not
a result.** The pre-registered negative control (§5) was run first, on synthetic frames drawn from
a *perfectly calibrated* predictive. §4 as originally written fired on them **9 times in 20**, twice
reporting `DRIFT`.

The cause is multiplicity, not a coding error: ~15 statistics were each placed in their own null at
α = 0.05 with no correction, so the family-wise error rate was **≈50%, not 5%**. An audit that flags
a healthy model half the time is the mirror image of a vacuous check, and on this study — whose
expected answer is a null — it would have produced a **wrong answer**.

The cure is the MH2 "declare a family, don't discover one" rule applied to **statistics** rather
than to arms:

| | |
|---|---|
| totals verdict family | `pit_mdd`, `bias`, `var_z_pooled`, `rms_var_z_sigma` |
| h2h verdict family | `cil`, `ece` |
| correction | Benjamini–Hochberg at **q = 0.05** across the union, per window |
| ⭐ conditional membership | `rms_var_z_sigma` is admissible **only if the primary stratifier validated on that window**. A disqualified partition is refused outright — it is not read "with a caveat" — so it leaves the family and the test count falls accordingly. |

Every other statistic is still **computed and reported**, as descriptive context, and **never as a
verdict**. Acceptance for the amendment is two-sided and pre-stated: the false-positive rate on
clean synthetic frames must fall to ≈5%, **and** the positive controls of §5 must still fire.

⚠️ Recorded rather than quietly folded in: this changed the study's decision rule after the
harness existed. It is admissible **only** because it was driven by a synthetic control and landed
before any real number was read — the ordering is visible in the git history of this branch.

## 5. ⭐ LOCK — THE INSTRUMENT MUST BE PROVEN ABLE TO FAIL AT THIS n

A "within noise" verdict is worthless if the instrument could not have detected a real defect at the
available sample size — a check that cannot fail is not a check (NF1.7 (a)). Two controls, both run
regardless of the result:

- **Positive controls:** deliberately corrupt the served predictive (σ × 1.25, μ + 0.75 runs,
  `p̂` shifted +0.05) and confirm each statistic's calibrated-null test **fires**.
- **⭐ MDE (minimum detectable effect):** by simulation, the smallest σ-scale error, μ-level shift
  and `p̂` shift detectable at **80% power** at the observed `n`. **Any null verdict must be stated
  together with its MDE, in the unit that grows (games)** — "no defect found" means "no defect
  larger than the MDE", and saying so is the difference between a measured null and a shrug
  (NF1.8 / MH2 `POWER_LIMITED`).

---

## 6. LOCK — DECISION RULE (fixed before the data were touched)

| finding | verdict | action |
|---|---|---|
| every statistic inside its calibrated null | **WITHIN_NOISE** | ⛔ **NO ACTION.** Report the MDE. Phase 2 does not fire. |
| a statistic outside its null but RECENT ≈ EARLIER | **STANDING_MISCALIBRATION** | not drift — a property of the champion. Record it; Phase 2 fires only if it is also material. |
| outside the null **and** RECENT ≠ EARLIER | **DRIFT** | Phase 2, scoped to the defect found (σ dynamic range → the MH2.5 target; level/mean → the wide-window retrain). |
| the instrument cannot resolve the MDE | **POWER_LIMITED** | say so in games; do not dress it as a clean null. |

⛔ **Phase 2, if it fires, is deploy-held regardless of outcome** and carries the MH2.1 promotion
landmines explicitly: a one-target swap breaks bundle-assuming consumers (`model_version` is stamped
from `home_win`; `mart_clv_labeled_games` hardcodes `v6`; the backfill idempotency key); serve the
**validated object**, never a re-derivation; and **a registry change ships with the box image on
merge to `main` — merging IS the deploy, with no gate**. Any promotion is an explicit operator
decision, never a session action.
