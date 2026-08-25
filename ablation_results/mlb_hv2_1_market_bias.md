# MLB-HV2-1 — DECISIVE RECORD: Bovada H2H market-bias backtest

**Verdict: `GENUINE_ABSENCE`. No registered segment survives. The market-bias
direction CLOSES.**

**Story:** MLB-HV2-1. **Spec:** `plan_specs/mlb/mlb-hv2-1.yaml`.
**Pre-registration:** `mlb_hv2_1_prereg.md` (committed before any scoring).
**Data audit:** `mlb_hv2_1_data_audit.md` (committed before the pre-registration).
**Artifact:** `mlb_hv2_1_market_bias.json`. **Date:** 2026-08-24.
**`best_alpha = 0`** — nothing here is a bet, a tout, or a served change.

---

## 1. The answer, in one paragraph

Over **8,827 completed MLB regular-season games (2020–2022, 2024–2026)** priced by
Bovada, **all eight pre-registered segment rules lose money**, at ROI −0.025 to
−0.091 per unit staked. Not one clears the very first gate (`ROI > 0`) — the gate
that is de-vig-free, PBO-free, DSR-free and field-free. Every arm's ROI sits
**inside** the band a *perfectly efficient* market would produce, and every
segment's realized win rate sits within **1.6 percentage points** of the price's
own no-vig implied probability. Bovada's H2H prices behave, at the segment level,
like a **fair market plus vig**. The public-bias premise this study was built on
is not present in the data.

`cv_power.classify_null` returns **`GENUINE_ABSENCE`** with **no re-test trigger**
— its own words: *"No sample size rescues a negative point estimate and no field
size changes its sign — do NOT re-test."*

## 2. Result — the eight registered arms

| arm | n bets | **ROI** | season-block 95 % CI | hit rate | implied | **calib. gap** | folds ROI>0 | one-sided p |
|---|---|---|---|---|---|---|---|---|
| `dog_vs_heavy_fav` | 1,382 | **−0.0908** | [−0.150, −0.017] | 0.3082 | 0.3242 | −0.0160 | 2/6 | 0.993 |
| `dog_vs_mod_fav` | 3,685 | **−0.0249** | [−0.076, +0.023] | 0.4138 | 0.4072 | +0.0066 | 2/6 | 0.903 |
| `dog_vs_slight_fav` | 3,548 | **−0.0573** | [−0.093, −0.029] | 0.4634 | 0.4705 | −0.0072 | 0/6 | 1.000 |
| `road_all` | 8,827 | **−0.0475** | [−0.063, −0.032] | 0.4673 | 0.4691 | −0.0018 | 0/6 | 1.000 |
| `road_dog` | 5,567 | **−0.0526** | [−0.081, −0.032] | 0.4101 | 0.4136 | −0.0035 | 0/6 | 1.000 |
| `road_fav` | 3,048 | **−0.0385** | [−0.077, −0.010] | 0.5696 | 0.5683 | +0.0012 | 1/6 | 0.994 |
| `fade_marquee` | 3,071 | **−0.0441** | [−0.092, −0.001] | 0.4438 | 0.4434 | +0.0004 | 2/6 | 0.986 |
| `fade_marquee_fav` | 2,266 | **−0.0440** | [−0.112, +0.007] | 0.4060 | 0.4053 | +0.0007 | 2/6 | 0.962 |

Gate tallies: `roi_positive` **0/8**, `fold_consistency` (≥5 of 6) **0/8**,
BH-FDR (α=0.05 over all 8, cutoff 0.00625) **0/8**, PBO 0.273 (bar 0.20)
**fails**, DSR ≤ 0.007 everywhere (bar 0.95) **fails**. **Survivors: none.**

The one-sided p-values are near **1.0** because the alternative registered was
"the rule *wins*". Read the other way, six of the eight arms lose **significantly**.

### Per-season ROI (the fold structure)

| arm | 2020 | 2021 | 2022 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| `dog_vs_heavy_fav` | +0.078 | −0.051 | −0.100 | −0.171 | −0.201 | +0.079 |
| `dog_vs_mod_fav` | −0.012 | −0.006 | −0.126 | −0.046 | +0.054 | +0.006 |
| `dog_vs_slight_fav` | −0.108 | −0.041 | −0.115 | −0.025 | −0.018 | −0.103 |
| `road_all` | −0.043 | −0.030 | −0.072 | −0.036 | −0.067 | −0.029 |
| `road_dog` | −0.031 | −0.024 | −0.124 | −0.045 | −0.043 | −0.036 |
| `road_fav` | −0.042 | −0.031 | +0.006 | −0.022 | −0.114 | −0.014 |
| `fade_marquee` | +0.045 | −0.029 | −0.148 | −0.055 | +0.007 | −0.028 |
| `fade_marquee_fav` | +0.072 | −0.045 | −0.197 | −0.011 | +0.002 | −0.006 |
| *(games)* | 575 | 1,652 | 1,636 | 1,777 | 1,839 | 1,348 |

No arm is positive in more than 2 of 6 seasons; the sign flips look like noise
around a constant loss of roughly the vig.

## 3. ⭐ The decisive read: an efficient-market null band

Re-drawing every game's outcome from **its own no-vig Bovada price** (500
simulations; prices, segments, eligibility and vig untouched — the *only* thing
removed is a systematic implied-vs-realized gap) gives the ROI each rule would
earn against a market that is exactly right:

| arm | real ROI | efficient mean | efficient 95 % band | Δ | outside? |
|---|---|---|---|---|---|
| `dog_vs_heavy_fav` | −0.0908 | −0.0420 | [−0.108, +0.032] | −0.049 | no |
| `dog_vs_mod_fav` | −0.0249 | −0.0417 | [−0.083, −0.003] | +0.017 | no |
| `dog_vs_slight_fav` | −0.0573 | −0.0432 | [−0.076, −0.012] | −0.014 | no |
| `road_all` | −0.0475 | −0.0420 | [−0.065, −0.020] | −0.006 | no |
| `road_dog` | −0.0526 | −0.0425 | [−0.075, −0.011] | −0.010 | no |
| `road_fav` | −0.0385 | −0.0409 | [−0.069, −0.010] | +0.002 | no |
| `fade_marquee` | −0.0441 | −0.0422 | [−0.082, −0.004] | −0.002 | no |
| `fade_marquee_fav` | −0.0440 | −0.0419 | [−0.091, +0.007] | −0.002 | no |

**Arms above the band: none. Arms below the band: none.** Bovada's observed prices
are indistinguishable from a fair-but-vigged market on every registered segment.

The **de-vig choice changes nothing**: calibration gaps are −0.016…+0.007 under the
registered proportional method and −0.009…+0.011 under the declared Shin
sensitivity. The direction of the residual is if anything the *classical* one —
heavy dogs are slightly **over**-priced (`dog_vs_heavy_fav` realized 0.3082 vs
implied 0.3242), i.e. the favorite–longshot bias runs the way the literature says
and therefore **against** the rule this study registered.

## 4. Anchors — all four pass

| anchor | ROI | required | ok |
|---|---|---|---|
| `anchor_oracle_winner` (bets the winner) | **+0.9139** | beat every arm | ✅ |
| `anchor_coin_flip` (seeded random side) | −0.0590 | lose | ✅ |
| `anchor_all_home` (mirror of `road_all`) | −0.0386 | lose | ✅ |
| `anchor_all_fav` (mirror of family A) | −0.0372 | lose | ✅ |

`anchor_all_home` at −0.0386 vs `road_all` at −0.0475 is the two-sided read that
matters for family B: **neither side of the home/road axis wins.** Registering the
mirror is what makes "there is no home bias" a measurement rather than an artifact
of which side happened to be registered.

## 5. ⚠️ Harness controls — one MIS-SPECIFIED and FAILING, one FAILING, one PASSING

Both pre-registered controls failed. Per NF-D20 they are left **failing and
decomposed**, not re-labelled.

**(a) NEGATIVE control (permutation) — PRE-REGISTERED, MIS-SPECIFIED, FAILED.**
`dog_vs_heavy_fav` survives every gate on permuted outcomes at **+0.378 ROI**.
Diagnosis: permuting outcomes does not implement "no segment bias" — it severs the
price↔probability link entirely, so a +250 dog wins at the pooled ~47 % base rate
instead of ~29 %. That is a **massive artificial dog bias**, not the absence of
one. The control never tested what it named.

**(b) NEGATIVE control (efficient market) — AMENDED, PASSES.** Re-drawing each
outcome from its own no-vig price is the null the permutation was meant to be.
**Survivors: none**, and every arm lands at **−0.034 … −0.051** — i.e. exactly
minus the vig (node 1 measured overround 1.023–1.070). Both directions check out:
nothing certifies, and the control prices the vig rather than breaking even.

**(c) POSITIVE control — PRE-REGISTERED, FAILED, and this is a real instrument
finding.** With a **6-percentage-point dog bias injected**, *no arm survives*. The
**metric** gates all fire correctly (`roi_positive`, `fold_consistency`, `bh_fdr`
pass for 6 of 8 arms, ROI up to +0.156, p as low as 1.4e-8). The **deflation**
gates block every one:

- **PBO rises to 0.426.** A uniform injected edge makes six arms simultaneously
  strong *near-clones*, so "which arm is best in-sample" becomes a coin flip.
  This is NF1.8's lesson exactly — **a high PBO over a near-clone field is the
  signature of a TIE, not of overfitting** — and a field-level PBO applied as a
  per-arm gate therefore vetoes a real, large effect.
- **DSR collapses to ~0.** The same injected edge inflates cross-trial dispersion
  `V` (arms spread from −0.147 to +0.156), so `SR0` outruns every arm's Sharpe —
  the MH2.5 / NF-W6b-C mechanism.

⇒ **The deflation gates as registered cannot certify a real effect of this size
over this (deliberately correlated) family.** That bounds what a *survivor* would
have meant. It does **not** touch this study's null.

### Why the control failures do not weaken the verdict

**The null rests on G1, not on the deflation gates.** Every arm has a **negative**
ROI, and `roi_positive` is de-vig-free, PBO-free, DSR-free and field-free. No
change to any deflation gate can turn a negative point estimate positive. The
positive control's failure would matter if an arm were *positive but blocked*;
none is. This is asserted, not narrated, by
`test_the_null_rests_on_the_point_estimate_not_on_a_deflation_gate`.

## 6. Sensitivity — the full observed sample

Scoring the **entire** observed sample (9,304 games: all seasons including the
5.2 %-covered 2023, plus the ~10 %-covered post-00:00-UTC stratum) gives the same
picture — ROI −0.022 to −0.087, **survivors: none**. The population restriction
registered at node 2 is a claim about *what the sample represents*, not a lever on
the result.

## 7. Model independence — verified, not asserted

`test_the_study_imports_no_model_serving_or_learner_module` imports the study in a
**subprocess** and inspects the `sys.modules` **delta**. No learner
(`sklearn`/`lightgbm`/`xgboost`/`ngboost`/`torch`/`statsmodels`), no
`betting_ml.models`, no `pipeline`, no `predict_today`/`write_serving_store`. The
detector writes its **own** leaky module so its two-sided proof cannot expire when
some other module switches to a lazy import.

*(The measurement is the DELTA, not the final `sys.modules`: this interpreter
starts with a bare `snowflake` namespace package already present — a `.pth`
artifact imported by nobody — so a final-state match would false-fire for every
module in the repo and could only be silenced by weakening the forbidden list.)*

## 8. Reproduction

25 guards, **20 deliberate breaks all RED**
(`betting_ml/tests/mlb_hv2_1_red_proof.py`, source **and** artifact mutations).
The extracted frame is committed (`betting_ml/tests/fixtures/mlb_hv2_1_input.csv.gz`,
92 KB) and everything after `extract()` is pure, so the record re-derives offline
and is pinned at **1e-9 absolute**.

```
uv run python -m betting_ml.scripts.mlb_hv2_1_market_bias      # ~9 s, laptop
uv run pytest betting_ml/tests/test_mlb_hv2_1_market_bias.py
uv run python betting_ml/tests/mlb_hv2_1_red_proof.py
```

## 9. What this does and does not close

**CLOSES.** The pre-registered public-bias hypotheses — the public overweighting
**favorites**, **home teams**, and **marquee clubs** — are **not exploitable in
Bovada's stored H2H prices** over 2020–2026. Combined with E13.8's model-side
headroom cap (~0.002–0.005 Brier), the two obvious sources of MLB H2H edge are now
both measured and both empty. **HV2 should re-rank on that basis.**

**DOES NOT close.** Stated plainly so the null is not over-read:

1. **A ~4.4 % overround is a large hurdle.** This measures whether a bias exceeds
   the vig, not whether a bias exists. The calibration gaps (≤1.6 pp) say the
   underlying miscalibration is small too — but a 1 pp segment bias would be real
   and still unprofitable at these prices.
2. **Segment definitions are the ones registered.** Eight closed, directional
   rules. A different partition (odds deciles, division/rivalry, streak state,
   day/night) is untested — but ⛔ picking one *now* is the 28.2 subset-mining
   trap, and it would have to be its own forward pre-registration.
3. **The sample is a named sub-population.** First pitch before 00:00 UTC, at
   0.897–0.999 season coverage. **West-Coast night games are ~0 %-covered before
   2026** and this study says nothing about them.
4. **The deflation gates could not have certified a survivor anyway** (§5c). A
   successor that expects a *positive* result needs a coherent, non-clone family
   registered forward — never a post-hoc trim of this one (MH2.2).
5. **Closing-line dynamics are untested.** One pre-game quote per event
   historically; line *movement* as a bias signal is a different study (and HV2-4's
   territory).

## 10. Findings for the PM

Carried into `plan_specs/mlb/mlb-hv2-1.yaml` `closeout.followUps`.
