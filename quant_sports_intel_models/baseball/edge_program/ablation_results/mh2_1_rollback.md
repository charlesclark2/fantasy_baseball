# MH2.1 — ROLLBACK of the `total_runs` / `post_lineup` champion swap

> ⚠️ **Not an edge claim, and none is retracted.** `best_alpha = 0` on both sides of this.
> `bet_paused` stayed `true` throughout. No bet ever rode on either model. This is a
> pricing/calibration record only — it says nothing about win rate, edge, or ROI.

**Promoted 2026-08-02. Rolled back 2026-08-02. Live served slates under the challenger: 0.**

**VERDICT: `ROLL_BACK — THE DECIDING EVIDENCE DID NOT REPRODUCE`**

---

## 1. What was promoted, and on what basis

MH2.1 re-ran E7.9's retrain bake-off over 2016–2026 (8 purged/embargoed folds vs E7.9's 3) with a
pre-registered 4-arm family and returned `SHIP_CHALLENGER` for `plus_eb × glm_elasticnet`
(CRPS +0.0297, PBO 0.010, DSR 0.9998, lift in 8/8 folds).

The promotion was **explicitly not argued on that margin.** The story's own decision text:

> "Driven by the conditional-calibration evidence (RMS |Var(z)−1| 0.050 vs served 0.158; served
> Var(z)=1.44 in the calmest σ-decile = overconfident exactly where P(over)-at-a-line is most
> sensitive), **not the thin CRPS margin.**"

That is the claim this document retracts.

## 2. What the served-population check found

E7.9 step 7's historical backfill re-scored **both** arms over the same 1,362 games of 2026
(`daily_model_predictions`, `retrain_tag` in `mh2_1_backtest` / `v6_baseline_refit`), stratified by
the **served v6's own σ** into deciles, scoring RMS |Var(z) − 1| — the identical statistic MH2.1
reported.

| window | n | `mh2_1` challenger | `v6` served | gap |
|---|---:|---:|---:|---:|
| in-sample for v6 | 903 | 0.1829 | **0.1228** | 0.060 |
| **out-of-sample for v6** | 459 | 0.2519 | **0.2275** | 0.024 |

v6 was fit 2026-06-23, so games from 06-24 are genuinely held out **for v6** while remaining
in-sample for the challenger (fit through 08-01). **The OOS split therefore runs against the
challenger under a bias that favours it.**

Three readings, in order of confidence:

1. **v6's σ is partly overfit.** Its advantage shrinks ~60% (0.060 → 0.024) once out of sample.
   That much of the "the NGBoost σ is overfit" hypothesis is supported.
2. **But not only overfit.** It still wins on data it never saw. The challenger wins in **no**
   window measurable here.
3. **Neither model is well calibrated per-game out of sample** (0.23–0.25 for both, vs 0.12–0.18
   in-sample). That is the honest state of totals uncertainty, and it is MH2.5's real target.

Pooled point accuracy weakly agrees: MAE 3.5401 (v6) vs 3.56 (challenger).

## 3. Why the original finding did not hold — an UNVALIDATED STRATIFIER

`mh2_1_conditional_calibration.md` stratified by the predicted σ of **`plus_eb::ngboost_normal`** —
the arm that report scored *worst* (0.180) — and applied those strata to every arm.

It ran real controls and they were not sloppy: a σ coefficient-of-variation floor (0.0798 vs a 0.02
floor), a matched heteroscedastic foil, a positive control (the foil's σ deliberately flattened),
and a 400-permutation null. Each of those asks **"does σ vary, and does the instrument detect a
known defect?"**

**None of them asks the load-bearing question: do these strata actually separate realized
dispersion?** A stratifier can have healthy σ-variation, pass a permutation test, and still order
games in a way that has little to do with how volatile they truly were.

Measured against the served v6's σ, the strata **do** separate:

| σ decile | n | mean σ (v6) | realized SD | mean abs resid |
|---:|---:|---:|---:|---:|
| 1 | 137 | 4.018 | 3.671 | 3.056 |
| 2 | 137 | 4.226 | 4.334 | 3.509 |
| 3 | 136 | 4.286 | 4.038 | 3.185 |
| 4 | 136 | 4.328 | 4.723 | 3.609 |
| 5 | 136 | 4.363 | 4.259 | 3.522 |
| 6 | 136 | 4.408 | 4.747 | 3.936 |
| 7 | 136 | 4.469 | 4.185 | 3.342 |
| 8 | 136 | 4.530 | 4.280 | 3.384 |
| 9 | 136 | 4.626 | 4.754 | 3.873 |
| 10 | 136 | 4.957 | 4.973 | 3.988 |

Realized SD rises **+35%** across a σ range of only **+23%** — the heteroscedasticity is real and
*stronger* than v6's σ expresses. Spearman ρ ≈ 0.66; endpoints ~4.8 SE apart (SE of an SD estimate
at n≈136 is ≈ sd/√(2n) ≈ 0.26). It is **informative but noisy** — the signal lives at the extremes,
and deciles 3/5/7 sit out of order well within sampling error.

The constant-σ arm's spread follows arithmetically from that table, which is what makes the
mechanism confirmed rather than inferred:

| decile | realized SD | predicted Var(z) = (SD / 4.4521)² | observed |
|---:|---:|---:|---:|
| 1 | 3.671 | 0.680 | 0.733 |
| 10 | 4.973 | 1.248 | 1.33 |

### ⭐ The durable lesson

> **A conditional-calibration result is a property of its stratifier.** A stratifier that does not
> demonstrably separate realized dispersion measures nothing, and a Var(z)-by-stratum metric
> computed over it can be silently **inverted** — the E2.1-r inversion class, one level up from the
> metric to the *partition the metric is computed over*.
>
> **Validate the stratifier before reading any per-stratum calibration number:** realized SD must
> rise across its bins, reported as a table, with the rank correlation and the per-bin SE. σ-CV
> floors, matched foils and permutation nulls do **not** substitute for it — MH2.1 had all three
> and still landed on strata whose ordering did not survive.

Sibling of NF1.7 (a) (an anchor that cannot fail is not a check) and (b) (an anchor is only a floor
at matched family *and* matched sample). This adds the partition axis.

## 4. What is honestly contested vs. settled

Being fair to MH2.1, its evidence is **not simply worse** than this check:

| | MH2.1's finding | this check |
|---|---|---|
| sample | 21,006 rows, 2016–2026 | 1,362 games, 2026 only |
| fold discipline | out-of-fold, 8 purged folds | in-sample for the challenger |
| stratifier | unvalidated (a different arm's σ) | validated (table above) |
| v6-OOS split | not available | yes, and it favours v6 |

So the correct statement is **not** "MH2.1 was wrong." It is: **the calibration finding is contested,
not established** — and a promotion whose stated basis has become contested reverts to the incumbent.
That is the conservative default, and it costs nothing here (`best_alpha = 0`, no bets, one registry
edit).

**Neither test can settle it**, and no further 2026 backtest can either, because the challenger was
fit through 2026-08-01 — every 2026 row is in-sample for it. Only forward live-served evidence can.

## 5. What survives

- ✅ **The CRPS bake-off result stands** — +0.0297, out of fold, 8/8 folds, PBO 0.010, DSR 0.9998,
  sensitivity (exclude 2020) +0.0299. It is untouched by this. It was simply never the basis the
  promotion was argued on. ⚠️ And it does **not** carry a decision alone: it decomposes as
  **+0.0175 learner swap / +0.0122 `plus_eb` block, neither clearing the 0.02 noise floor**.
- ✅ **MH2's window thesis stands** — the 3-fold ceiling was a WINDOW choice, not a data limit
  (the DSR bar fell 7.28 → 1.18 as folds went 3 → 8). Reproduced exactly; unaffected.
- ✅ **The serving machinery is retained, not deleted** — `HomoscedasticNormalRegressor`,
  `finalize_mh2_1_champion.py`, the 25-col sidecar, and the fitted artifact all remain addressable
  under the registry's `mh2_1_*` keys. A re-promotion is a registry edit, not a re-fit.
- ✅ **`daily_model_predictions.totals_model_version`** — the per-target totals stamp MH2.1 added is
  **kept**. It closed a real gap (the bundle `model_version` is home_win-only, so a totals champion
  swap was invisible in the served rows) and is independent of which champion serves. It reads
  `v6` again.
- ✅ **Three pre-existing `backfill_predictions.py` breaks** found by this work stay fixed (dict
  sidecar unwrap; the transformed-frame `columns=` that *selected* rather than renamed and silently
  zero-filled the imputer indicators; `X_hw` built from the raw NaN-bearing frame), plus the no-op
  guard and `--totals-artifact prev`.

## 6. What does NOT survive — do not cite these

- ❌ **"The served NGBoost's per-game σ is actively wrong"** and **"flattening its σ improves
  calibration."** Not established. `mh2_1_conditional_calibration.md` carries a correction header.
- ❌ **The figures 0.050 / 0.158 / 0.180 / 0.107** and the "Var(z) = 1.44 in the calmest decile"
  line. Stratifier artifacts.
- ❌ **`VERDICT: INCUMBENT_VARIANCE_UNINFORMATIVE`.** Superseded.

## 7. Re-promotion bar (pre-registered here, so it is not re-litigated from the answer)

1. A **validated stratifier** — realized SD must demonstrably separate across its bins, reported.
2. The challenger ahead on conditional calibration over **forward live-served rows it never saw**.
3. **Not** another 2026 backtest — structurally incapable of settling this.

## 8. MH2.5 note

MH2.5 re-baselines σ on the **served** model, which is the v6 NGBoost again. Its target is
unchanged in substance and arguably clearer: **both** candidate variance models are poorly
calibrated per-game out of sample (0.23–0.25). That, not the choice between them, is the problem.

## Reproduction

```sql
-- both arms, same games; stratified by the SERVED v6 sigma; split at v6's fit date
with v6 as (
  select game_pk,
         case when game_date >= '2026-06-24' then 'OOS_for_v6' else 'in_sample_v6' end as window,
         ntile(10) over (
           partition by case when game_date >= '2026-06-24' then 1 else 0 end
           order by pred_total_runs_scale) as sigma_decile
  from baseball_data.betting_ml.daily_model_predictions
  where prediction_type = 'backfill' and retrain_tag = 'v6_baseline_refit'
),
p as (
  select retrain_tag, game_pk, pred_total_runs, pred_total_runs_scale
  from baseball_data.betting_ml.daily_model_predictions
  where prediction_type = 'backfill'
    and retrain_tag in ('mh2_1_backtest', 'v6_baseline_refit')
),
r as (
  select game_pk, home_final_score + away_final_score as actual_total
  from baseball_data.betting.mart_game_results
  where game_type = 'R' and home_final_score is not null
),
per_decile as (
  select v6.window, v6.sigma_decile, p.retrain_tag, count(*) as n,
         avg(power((r.actual_total - p.pred_total_runs) / p.pred_total_runs_scale, 2)) as var_z
  from p join r on p.game_pk = r.game_pk
         join v6 on v6.game_pk = p.game_pk
  group by 1, 2, 3
)
select window, retrain_tag, sum(n) as n,
       round(sqrt(avg(power(var_z - 1, 2))), 4) as rms_dev_from_1
from per_decile group by 1, 2 order by 1, 2;
```

The stratifier-validity table in §3 is the same `v6` CTE without the window split, reporting
`stddev(actual_total - pred_total_runs)` and `avg(abs(...))` per decile.
