# MH2.10 — PRE-REGISTRATION (written and committed BEFORE any statistic was computed on this population)

**Story:** MH2.10 · Morning-tier (`pre_lineup_v6`) served-calibration audit — is the morning σ
genuinely too small, by how much, and is it a **scale** defect (fixable) or a **shape** defect (the
MH2.8 class)?
**Branch:** `mh2-10-morning-audit` · **`best_alpha = 0`** · **deploy-held**.
**Harness:** `betting_ml/scripts/mh2_10_morning_audit.py` (Snowflake-free; DuckDB over the S3
lakehouse).

> Everything below is fixed in SOURCE before any statistic is scored on the MH2.10 population. A
> choice made after seeing a number is window-shopping — the defect the MH2 lineage exists to stop
> (E2.1-r).

---

## 0. ⭐ What was looked at BEFORE this document was written — stated so the ordering is auditable

A pre-registration that hides its own priors is not one. Three things were read first, and each is
either the story's premise or a design quantity:

1. **MH2.6's PUBLISHED morning figures** (`mh2_6_calibration_audit.json`, committed 2026-08-15).
   These *are* the story's premise: MH2.6 carried `morning` as a declared-secondary tier, computed
   its statistics, and never put them through its own decision rule. The premise is confirmed —
   `var_z_pooled` 1.1199 (p = 0.043) and `rms_var_z_sigma` 0.3267 (p = 0.003) sit outside their
   nulls on the FULL era where post_lineup's sit inside. ⚠️ Those are **uncorrected** α = 0.05
   marks; MH2.6's own LOCK 5b exists because an uncorrected family flags a *healthy* model ~50% of
   the time. Whether they survive the correction is this study's question, not its premise.

2. **The two tiers' served feature contracts** — a design check that **REFUTED a hypothesis before
   it entered the design.** The intended framing was information monotonicity: if the morning
   feature set were a subset of post_lineup's, then `E[Var(Y|X_morning)] ≥ E[Var(Y|X_post)]` is an
   analytic truth (law of total variance) and a narrower morning σ would be a *deterministic*
   violation needing no significance test at all. **The contracts do not nest**: morning carries 16
   served columns, post_lineup 15, and they share only 7 — each tier's contract was pruned
   independently, so morning holds nine columns post_lineup lacks. ⛔ **No information-monotonicity
   claim may be made in this study**, and the morning-vs-post comparison is demoted to a descriptive
   mechanism read (§6) with no anchoring role (MH2.1 (b): never anchor on the incumbent).

3. **A population probe — counts and dates only, no statistic.** Design quantities, exactly as
   MH2.6 derived `k` from `n`: 655 served `pre_lineup_v6` morning rows carry finals over
   2026-06-24 → 2026-08-15.

Nothing else was computed on this population before this file was committed. The ordering is visible
in the git history of this branch.

---

## 1. LOCK — POPULATION

The **SERVED** morning rows, i.e. what the app actually showed before lineups posted, read from the
S3 `daily_model_predictions` parquet, joined to realized outcomes in `mart_game_results`.

| lock | value |
|---|---|
| tier | `prediction_type = 'morning'` — **PRIMARY**, and the only tier this study judges |
| champion | `model_version = 'pre_lineup_v6'` (E13.11, morning tier, served from 2026-06-24) |
| de-dup | latest `inserted_at` per `game_pk` — the row actually served |
| backfills | `is_backfill = TRUE` EXCLUDED (not live-served) |
| outcomes | `mart_game_results`, `game_type = 'R'`, `home_final_score IS NOT NULL` |
| anchor | the newest `game_date` carrying finals |
| probed | **n = 655**, era 2026-06-24 → 2026-08-15 |

**Targets.** `total_runs`: served predictive `Normal(pred_total_runs, pred_total_runs_scale)` vs
`home_final_score + away_final_score`. `home_win`: served `calibrated_win_prob` vs `home_team_won`.

⚠️ **Declared deviation from MH2.6's population rule, with its measured cost.** MH2.6 admitted
`model_version IN ('v6', 'pre_lineup_v6')` for *both* tiers; four morning rows on 2026-08-01 carry
the post-tier stamp `v6`. MH2.10 restricts the morning population to the morning champion. The probe
shows this changes **nothing** — no such row survives de-dup with a final — and the harness asserts
the count so the deviation cannot silently grow.

⚠️ **The MH2.6 rolled-back-challenger exclusion (`totals_model_version = 'mh2_1'`) is a NO-OP on
this tier** — the MH2.1 challenger priced post_lineup rows only. The filter is nevertheless kept in
the harness and the dropped count is reported, so a future stamp cannot slip through unfiltered.

⛔ **`post_lineup` is NOT touched by this study.** It is a different model with a different feature
contract; MH2.6 already audited it. It appears here only as the descriptive contrast of §6.

---

## 2. LOCK — WINDOWS

Every served row post-dates the champion's fit (E13.11, 2026-06-23), so **the whole served era is
out of sample** — MH2.1's "split at the incumbent's fit date" rule holds by construction.

| window | definition | role |
|---|---|---|
| `FULL` | the whole `pre_lineup_v6` served era | **PRIMARY** |
| `RECENT` | the 30 days ending at the anchor | secondary |
| `EARLIER` | era start → `RECENT` start − 1 | secondary; also the σ-scale FIT window (§4d) |

⭐ **`FULL` is the primary window here, and that is a deliberate change from MH2.6.** MH2.6's
question was *drift* (had two days got worse?), so its primary window was `RECENT`. MH2.10's
question is a **standing** property — "is the morning σ too small?" — and MH2.6 already measured
that nothing on this tier moved between windows. Using the larger window for a standing question is
a power decision made from the question's shape, not from any result.

⛔ **The training-era baseline is IN-SAMPLE and is NOT a bar.** Any in-sample reference is optimistic
by construction.

---

## 3. LOCK — STATISTICS

Imported **verbatim** from `mh2_6_calibration_audit` (`totals_stats`, `h2h_stats`,
`randomized_pit`, `crps_normal`) rather than re-implemented, so there is exactly one implementation
of each. `total_runs` is an integer count, so PIT carries the E2.1-r continuity correction and
randomization; coverage is **a floor and a reference, never a target** (NF1.8).

**Strata count from `n` ALONE** (NF1.8, a design quantity known before any result):
`k = clip(n // 60, 3, 10)`. At the probed n = 655 this is **k = 10**.

### 3.1 ⭐ LOCK — THE STRATIFIER IS VALIDATED FIRST, OR NOTHING IS READ OFF IT

The exact step whose absence caused the MH2.1 rollback. Each partition publishes its
realized-SD-per-bin table (n, mean stratifier, realized SD, per-bin SE, mean |resid|) and must clear
the pre-registered bar, reusing MH2.5's implementation verbatim (`realized_dispersion_table`,
`STRATIFIER_MIN_RHO = 0.30`, `STRATIFIER_MIN_ENDPOINT_SE = 2.0`).

| stratifier | role |
|---|---|
| `incumbent_sigma` — the served morning σ | PRIMARY |
| `incumbent_mean` — the served morning μ | SECONDARY |

A partition that fails is **DISQUALIFIED**: no `Var(z)` is read off it, and `rms_var_z_sigma` leaves
the verdict family (the test count falls accordingly). A failed validation is a finding, not a
licence to read the number anyway (NF1.7 (a)).

⚠️ **Stated in advance because it is already visible in MH2.6's published record and must not be
presented as a discovery:** the morning σ-partition failed MH2.6's bar with a **negative** rank
correlation (ρ = −0.042 FULL, −0.143 RECENT). This study therefore expects `rms_var_z_sigma` — the
*strongest-looking* flag in the premise, p = 0.003 — to be **INADMISSIBLE**, and says so before
re-measuring it. If the re-measure validates the partition, the statistic re-enters the family.

### 3.2 `home_win`

Calibration-in-the-large, Brier + Murphy decomposition, ECE, log loss, reliability curve over `k`
quantile bins. ⚠️ **Stated in advance so it cannot be mistaken for a finding:** the registry records
v6 `home_win` as a confirmed **thin-signal** target (served spread ≈ 0.035), so a flat reliability
curve is the EXPECTED shape, not a defect.

---

## 4. ⭐ LOCK — THE σ-SCALE ESTIMAND, AND HOW SCALE IS SEPARATED FROM SHAPE

This is what the story asks for and what MH2.6 could not deliver on this tier.

### 4a. The estimand, in the actionable unit

`ĉ = sqrt(var_z_pooled)` — the single multiplier that would make the pooled predictive variance
correct. "The morning σ is X% too small" is `ĉ − 1`. Reported with a row-resampling bootstrap CI,
which makes **no distributional assumption** about the residual.

### 4b. PRIMARY null — the calibrated null (MH2.6's, imported verbatim)

Outcomes re-drawn from the served predictive itself (`y* ~ round(Normal(μ, σ))`), `n` and per-game
μ/σ/p̂ held fixed: *would a perfectly calibrated served model produce a window that looks this
rough?* Two-sided, Monte-Carlo p with the `(r+1)/(B+1)` plug-in.

### 4c. ⭐ CO-PRIMARY — the SHAPE-MATCHED null, and why a Normal null is the wrong yardstick for a variance statistic

**The mechanism, stated before it is measured.** MH2.6 and MH2.8 both established that realized
`total_runs` is **right-skewed and leptokurtic** against a symmetric-Normal predictive (z skew
≈ 0.74, excess kurtosis ≈ 0.59). The sampling variance of a *variance* statistic depends on the
**fourth** moment — `Var(s²) = σ⁴·(2/(n−1) + κ/n)` — so a null drawn from a **Normal** predictive is
systematically **too narrow** for `var_z_pooled` and `rms_var_z_*` whenever the truth is leptokurtic.

⇒ **A SHAPE defect mechanically manufactures apparent SCALE flags.** Since the morning and
post_lineup tiers share the same right-skewed target, this is a live alternative explanation for the
premise, and the study is worthless if it cannot rule it in or out.

**The shape-matched null** re-draws `y* = round(μ + σ·ε*)` where `ε*` is resampled with replacement
from the observed standardized residuals **re-centred to mean 0 and re-scaled to variance exactly
1**. The null hypothesis is therefore precisely *"the σ scale is correct"*, with the residual SHAPE
carried over from the data as a nuisance. A skew-normal-fitted variant is reported as a sensitivity.

⛔ **LOCK — the shape-matched null is applied ONLY to the variance statistics** (`var_z_pooled`,
`rms_var_z_sigma`, `rms_var_z_mean`). Applying it to `pit_mdd`/`pit_ks`/coverage would build the
very shape defect being tested **into the null**, making the shape untestable by construction — the
circularity is the reason for the restriction, and it is fixed here rather than decided later.

⚠️ The nuisance shape is estimated from the same rows whose variance is being tested. This is the
standard nuisance-parameter treatment, and its error direction is **conservative** (any real
heteroscedasticity inflates the pooled kurtosis and therefore widens the null), which is the safe
direction for a study whose default is NO ACTION.

### 4d. The out-of-sample read

`ĉ` fitted on `EARLIER` and applied to `RECENT`, reporting the residual `Var(z)` after the fitted
multiplier. An in-sample `ĉ` is by construction the value that zeroes its own target — it is a
CEILING, labelled as such, never a shippable estimate (the MH2.8 oracle discipline).

### 4e. ⭐ MATERIALITY — significance is not sufficiency

Imported from MH2.5 rather than invented: a `Var(z)` of `v` turns a nominal central-80% interval
into realized coverage `2Φ(1.2816/√v) − 1`, so one percentage point of coverage error corresponds to
`|v − 1| ≈ 0.045`, and MH2.5 fixed **0.05** as the smallest pricing-relevant movement. MH2.10 applies
that same bar to the pooled **level**: Phase 2 requires `|var_z_pooled − 1| ≥ 0.05` **in addition
to** statistical survival. (A stated small extension of MH2.5's constant from a *gain* to a *level*;
the derivation is identical and the bar is not re-tuned.)

---

## 5. LOCK — MULTIPLICITY. The verdict-bearing family is small, declared, and BH-corrected

Imported verbatim from MH2.6 LOCK 5b — the amendment that exists because an uncorrected family fired
on perfectly calibrated synthetic data 9 times in 20.

| | |
|---|---|
| totals verdict family | `pit_mdd`, `bias`, `var_z_pooled`, `rms_var_z_sigma` |
| h2h verdict family | `cil`, `ece` |
| correction | Benjamini–Hochberg at **q = 0.05** across the union, per window |
| conditional membership | `rms_var_z_sigma` admissible **only if** the primary stratifier validated on that window |

Every other statistic is computed and reported as descriptive context, **never as a verdict**.

⭐ **Vacuity floor (MH2.6 `min_null_reps`, imported):** a Monte-Carlo p cannot resolve below
`1/(B+1)` and BH's strictest threshold is `q/m`; if `2/(B+1) > q/m` **no** input could ever be
flagged and the verdict is a null the instrument could not have contradicted. The harness **refuses
to run** below that floor.

---

## 6. Declared DESCRIPTIVE block — the morning-vs-post_lineup contrast (verdict-inert)

Both tiers price the **same games**, so `σ_morning − σ_post` is a deterministic, outcome-free
quantity. It is reported because it names a mechanism, and it is **verdict-inert by construction**:

- ⛔ it is **not** an anchor — post_lineup is not a known-correct reference, merely a model MH2.6
  measured inside its null, and MH2.1 (b) forbids an incumbent-relative anchor. The absolute σ claim
  is anchored on the analytic truth `Var(z) = 1` and on nothing else.
- ⛔ it is **not** an information-monotonicity claim — §0.2 refuted the nesting that would license
  one.

---

## 7. ⭐ LOCK — THE INSTRUMENT MUST BE PROVEN ABLE TO FAIL, AND ABLE TO TELL SCALE FROM SHAPE

A verdict is worthless if the instrument could not have produced the other answer (NF1.7 (a)). Four
controls, all run regardless of the result:

- **Positive controls.** σ × 1.25, μ + 0.75 runs, `p̂` + 0.05 must fire — **in both nulls** for the
  variance statistics. A shape-matched null that cannot detect a real σ error is not a conservative
  null, it is a broken one.
- **⭐ NEGATIVE CONTROL — it mirrors the DECISION RULE, not a bare "did anything look odd" (MH2.8).**
  MH2.8's negative control ranked arms by "who is closest" while the ship rule required a *meaningful
  margin*, so the control answered a question the rule never asked. MH2.10's negative control draws
  clean synthetic frames at the morning population's `n`/μ/σ, runs the **whole harness**, and reads
  the **verdict LABEL that Phase 2 keys on**. Acceptance, pre-stated and two-sided:
  the non-`WITHIN_NOISE` rate ≈ 5%, and `SIGMA_SCALE_DEFECT` ≈ 0.
- **⭐ THE SCALE/SHAPE DISCRIMINATOR CONTROL — the one this study specifically needs.** Clean frames
  drawn from a **correctly-scaled but SKEWED** predictive (the real-world shape, σ exactly right).
  Acceptance: these must **not** produce `SIGMA_SCALE_DEFECT`. If they do, the discriminator is
  broken and no scale-vs-shape attribution may be reported.
- **MDE + `games_needed`.** The smallest σ-scale error, μ shift and `p̂` shift detectable at 80%
  power at the morning `n` — MH2.6 never computed power for this tier. Reported **in the unit that
  grows**: served games, and days at the observed slate rate. A trigger reachable by waiting is a
  live re-test; only a calendar-bound one is a future note (MH2).

---

## 8. LOCK — DECISION RULE (fixed before any statistic on this population)

**Default verdict: `WITHIN_NOISE` → NO ACTION. Phase 2 does not fire.**

| finding (PRIMARY window `FULL`) | verdict | action |
|---|---|---|
| nothing survives BH | **`WITHIN_NOISE`** | ⛔ NO ACTION. Report MDE + `games_needed`. |
| `var_z_pooled` survives BH in **both** nulls, `ĉ` CI excludes 1, and `\|var_z−1\| ≥ 0.05` | **`SIGMA_SCALE_DEFECT`** | ⭐ **Phase 2 FIRES** — a pre-registered σ-widening, magnitude `ĉ`. |
| `var_z_pooled` survives BH in the Normal null but **NOT** the shape-matched null | **`SHAPE_ARTIFACT`** | ⛔ Phase 2 does NOT fire. The flag is the MH2.8-class shape defect leaking into a variance statistic. |
| only PIT statistics survive | **`SHAPE_DEFECT`** | ⛔ Phase 2 does NOT fire — MH2.8 already ran that study and it did not ship. |
| survives, but `\|var_z−1\| < 0.05` | **`IMMATERIAL`** | ⛔ NO ACTION; record the magnitude. |
| the MDE cannot resolve the effect | **`POWER_LIMITED`** | say so in games AND days-to-reach; do not dress it as a clean null. |

⭐ **Firing a scoped σ branch at an unscoped shape defect is "fitting noise with extra steps"** —
MH2.6's own closing sentence, and the reason `SHAPE_ARTIFACT` is a *distinct, non-firing* verdict
rather than a caveat attached to a firing one.

### Phase 2, if and only if it fires

A pre-registered σ-widening / dynamic-range fix on the **`pre_lineup` model only**: validated
stratifier, a matched heteroscedastic foil, **flat-σ as a null-to-beat** (MH2.1's rollback demoted
flat-σ from a proven improvement to a null), scored on CRPS + the conditional instrument, split at
the incumbent's fit date (satisfied by construction, §2). ⛔ post_lineup is not touched.

⛔ **Deploy-held regardless of outcome**, and any promotion carries the MH2.1 landmines explicitly:
a one-target swap breaks bundle-assuming consumers (`daily_model_predictions.model_version` is
stamped from `home_win`; `mart_clv_labeled_games` hardcodes `v6`; the backfill idempotency key is
`(game_pk, model_version, retrain_tag)`); serve the **validated object**, never a re-derivation; and
**a registry change ships with the box image on merge to `main` — merging IS the deploy, with no
gate between merge and serve.** Any promotion is an explicit operator decision, never a session
action. `best_alpha = 0`.
