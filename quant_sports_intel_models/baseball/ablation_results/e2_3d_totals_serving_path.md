# E2.3-d — Totals serving-path diagnostic (read-only spike)

**Date:** 2026-07-20 · **Scope:** decide E2.3-deploy vs E13.6b · **Type:** read-only trace + cheap re-measure
**Constraints honored:** READ-ONLY (no writes/deploy/fit), SF-FREE (serving-cache pairs only), OFF-BOX. `best_alpha = 0` unchanged — this is CALIBRATION, not edge.

---

## 🎯 THE ONE ANSWER

**Today the app serves totals `P(over)` from the NGBoost *Normal* total-runs model — NOT from E2.3's convolved NegBin distribution. E2.3's `totals_distribution_v1.json` is ORPHANED with respect to the totals serving path.** The two "totals miscalibration" stories are therefore *not* the same object seen from two ends: E9.26 measured the NGBoost-Normal served prob, and E2.3 is a different, never-wired model. There is **no double-calibration risk from E2.3 today** because E2.3 is not deployed.

---

## 1. The traced served path (module + artifact, exact)

The served totals probability is produced in **one place** and consumed in **one place**, both NGBoost-Normal:

**Produce — [scripts/predict_today.py](../../../../scripts/predict_today.py):**
- L82 `from betting_ml.models.total_runs_trainer import p_over_line`
- L2244–2255: `pred_dist_tot = ngb_total.pred_dist(X_tot)` → `loc_tot`, `scale_tot`; then
  `p_over_total = p_over_line(ngb_tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line_vals)`
- `p_over_line` in [betting_ml/models/total_runs_trainer.py:166](../../../../betting_ml/models/total_runs_trainer.py#L166) is literally `stats.norm.sf(total_line, loc=loc, scale=scale)` — a **Normal survival function**.
- Stored to `daily_model_predictions` as `p_over_ngboost` (L1249) and `totals_model_prob` (L1257), plus the raw Normal params `pred_total_runs` (=loc) and `pred_total_runs_scale` (=scale).
- **No calibrator is applied to totals.** Only h2h passes through `_apply_calibrator` (the E13.6 temperature calibrator). Totals is the *raw* distributional CDF.

**Re-derive per book — [scripts/write_serving_store.py](../../../../scripts/write_serving_store.py):**
- L1441 `_MODEL_DIST_BATCH` reads `pred_total_runs`, `pred_total_runs_scale` back out of `daily_model_predictions`.
- L1817: `p_over = float(_scipy_norm.sf(line, loc=pred_mu, scale=pred_scale))` — same **Normal CDF**, per book/line. Comment L1815: *"Champion totals model is NGBoost Normal — use Normal CDF."*

**E2.3 (`totals_distribution_v1.json`) appears nowhere in either file.** `grep` for `totals_distribution` / `prop_pricing` / `totals_perside` in both serving modules → **zero hits**.

## 2. Artifact status: `totals_distribution_v1.json` — ORPHANED (from totals serving)

- **Location/size/age:** `betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json`, 855 bytes, last written **2026-06-24** (commit `e56a91f` "Shipping E2.3"). Not touched since.
- **Content:** global dispersion params only — `dispersion_r_home=4.0645`, `dispersion_r_away=3.3977`, `rho=0.0`, a P05–P95 quantile grid. It is **not a per-game served distribution**; it's the calibration constants for the convolution machinery.
- **Consumers (whole-repo grep):** `betting_ml/utils/totals_distribution.py` (the convolution util), `betting_ml/utils/prop_pricing.py`, the fit/bakeoff scripts, the two unit tests, and **`scripts/write_pitcher_k_projections.py`** — i.e. the **strikeout K-props** pricing path, *not* game totals. **Neither `predict_today` nor `write_serving_store` reads it.**
- **Verdict:** deployed to git, but **orphaned relative to the totals serving path**. It is only "live" inside the K-props surface via `prop_pricing`.

## 3. Reconciliation with E9.26 — no contradiction

E9.26 (and E13.6b Part A) measured the **served `totals_model_prob`**, which is the NGBoost-Normal raw CDF — exactly the path traced above. E2.3 was never the served path, so there is nothing to reconcile: the 0.079/0.060 miscalibration is a property of the **NGBoost Normal** model, and E2.3's offline gate (calib_80 0.838, PIT-flat 0.0068, r_home 4.03 / r_away 3.57) describes a **different, better-dispersed model that was never wired in.**

Two caveats that matter for the decision:
- **E2.3's headline gate metric is the biased one.** `calib_80` is the inclusive-integer interval-coverage figure the CLAUDE.md E2.1-r landmine flags as *inflated for discrete/count predictives* — so "0.838" does **not** guarantee E2.3-served would beat an isotonic-recalibrated NGBoost on the **served ECE** metric we actually care about here. Its PIT-flatness (0.0068) is the trustworthy part, but that was measured offline on re-derived E2.1 marginals, not on the serving surface.
- E2.3's own README notes totals **discrimination is ~0** (`best_alpha=0`), same as the served model — so deploying it buys *dispersion honesty*, not edge.

## 4. Cheap re-measure via the serving cache — 0.079 still holds (and recent is worse)

Re-measured **from the cached serving-cache pairs** `betting_ml/evaluation/calibration_e13_6b/totals_pairs_2026-04-17_2026-07-17.json` (1,110 served totals games, sourced from the S3 permanent game blobs `api-cache/permanent/picks/game/*.json` — the E9.40/E9.26 read discipline; **no mart/lakehouse/SF query**). 10-bin ECE:

| Window | n | ECE | mean_pred | base_rate | note |
|---|---|---|---|---|---|
| Apr 17 – Jul 16 (full) | 1110 | **0.0595** | 0.546 | 0.498 | matches E13.6b's 0.0595 |
| since Jun 16 | 366 | 0.068 | 0.532 | 0.478 | |
| since Jun 25 | 244 | 0.067 | 0.527 | 0.492 | |
| since Jul 1 | 164 | **0.102** | 0.521 | 0.470 | recent, still over-leaning |
| since Jul 9 | 59 | 0.107 | 0.530 | 0.424 | small-n, noisy |

**Confirmed:** the served totals prob is miscalibrated ~2× worse than moneyline (~0.03), with a **consistent systematic lean toward the OVER** (mean_pred 0.52–0.55 vs base 0.42–0.50) in every window. E9.26's ~0.079 is real; the recent window is if anything *worse*. (Data is 3 days stale — window ends 2026-07-16; a fresher gather is the slow ~15–20 min S3 walk, out of scope for a read-only spike. The direction is unambiguous.)

---

## ✅ RECOMMENDATION — **(B) E13.6b as spec'd. Do NOT deploy E2.3 as the calibration fix.**

E2.3's artifact is **not** the served path, so E13.6b is not redundant with a hidden calibrated distribution. Concretely:

1. **E13.6b is the small, already-validated, correctly-targeted fix.** Part A is DONE and fit *directly on the served NGBoost output*: isotonic cuts pooled walk-forward OOF ECE **0.048 → 0.015** (at/under moneyline parity) and is the only candidate clearing the 0.03 spread floor (Platt/temperature collapse P(over) to base rate). Wire-in is a one-line analog of the h2h `_apply_calibrator` at `predict_today` `p_over_v` (~L1111) → `totals_model_prob` (~L1257), serving the `calibrator_e13_6b_isotonic_candidate.joblib` from S3.

2. **E2.3 deploy is a large ON-BOX re-wire with a weaker guarantee — not a calibration bolt-on.** `totals_distribution_v1.json` holds only global dispersion constants; serving E2.3 would require (a) serving the E2.1 per-side NegBin **mean** marginals at serve time, (b) convolving per game at serve, and (c) **reworking `write_serving_store`'s hardcoded Normal-CDF per-book recompute** (L1817) to a NegBin/quantile-grid — because `pred_total_runs_scale` would no longer be a Normal σ. And its selection metric (`calib_80`) is the biased-for-counts one, so it isn't even guaranteed to beat isotonic-recalibrated NGBoost on served ECE. That is a *fix-at-source model-swap story*, not this decision's lane.

3. **Guard against double-calibration = deploy exactly ONE totals-calibration mechanism.** The double-calibration hazard is **between E2.3 and E13.6b**, not against today's served path. E13.6b's isotonic was fit on the *current* NGBoost output; if E2.3 ever replaces that output, the isotonic calibrator must be **retired/refit**, never stacked. So: ship E13.6b now; if a future story deploys E2.3 at source, that story **removes** the E13.6b calibrator (and re-measures) rather than layering on top.

**Sequencing (important):** E13.6b **Part B wiring is an ON-BOX `predict_today` change** and must be sequenced **after** the E11.20 phase-2a / SCD-2 lane confirms clean on a live slate — per the existing Part-B hold ("never change two things in one verification window"). It must **not** run concurrently with the E11.20 box lane. The runtime gate for Part B is a fresh served-slate ECE re-measure on the box.

*Not chosen:* (A)/(C) — E2.3 is not the served path and stacking risks double-calibration; (D) — the miscalibration is real and reproduced today (0.06 full / 0.10 recent, over-leaning), not a measurement artifact.
