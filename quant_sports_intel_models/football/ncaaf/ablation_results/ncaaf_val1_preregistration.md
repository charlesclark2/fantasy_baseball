# NCAAF-VAL1 — PRE-REGISTRATION (early-season CLV stratification)

**Written 2026-08-20, BEFORE any bucket-level hit rate was computed.** Everything below — buckets,
config, family, statistic, pass criterion, anchors, and the null-reading rule — is fixed here and
is not revisable after the run. This is the §0.5 / E2.1-r contract: *a subset that clears is a
FORWARD hypothesis, never a post-hoc edge.*

---

## 0. What was known before this document (and what was not)

**Known (prior record, quoted in the story brief):**

- P1.4's pooled vs-close CLV for the **v1** config (`ridge / strength_only / strength_posterior`):
  ATS **0.496** (n=4110, placebo 0.497), O/U **0.523** (n=4129); breakeven **0.5238**.
- S1-serve's pooled vs-close CLV for the **SERVED v2** config (`ridge / strength_pace /
  strength_posterior`): ATS **0.509** (n=4114, placebo 0.501), O/U **0.513** (n=4135).
- Both pooled reads are BELOW breakeven ⇒ the recorded game-line null, `best_alpha = 0`.
- Design quantities read from the assembled cache **before** writing this document (row counts and
  push counts only — properties of the schedule, the close and the realised score, carrying **zero**
  information about whether the model's side wins): see §3.

**NOT known (never computed before this document was committed):** any bucket-level hit rate,
placebo rate, per-season series, or any statistic that depends on the model's predicted side.

---

## 1. Buckets — fixed, on `season_order_week`

| bucket | `season_order_week` | rationale |
|---|---|---|
| `wk1-3` | 1–3 | the cold-start regime: in-season efficiency features are NULL, the strength posterior is ~3.4× wider than week 8+, and this is the slice the program's "the college book is softest early" thesis names |
| `wk4-6` | 4–6 | the transition regime — a monotonicity check between the two ends |
| `wk7+`  | ≥ 7 | the efficient/late regime |

⛔ **`season_order_week`, NEVER raw `week`** — raw `week` restarts at 1 in the postseason (the P1.1
collision), which would drop January playoff games into the "cold start" bucket. Pinned by a guard
test in this story's suite.

Buckets are a **PARTITION**, declared in advance, exhaustive and disjoint over every OOS game that
carries a leakage-safe close. No bucket is selected, tuned, or re-cut after the run.

---

## 2. Model configuration — fixed

- **PRIMARY (binding): the SERVED config** — `learner=ridge`, `contract=strength_pace`,
  `form=strength_posterior` (`ncaaf_game_distribution_v2`), run at the **recorded defaults**
  `--n-draws 4000 --seed 42`, all folds. This is the model a forward shadow season would actually
  run, so it is the decision-relevant one.
- **SECONDARY (robustness only): the P1.4 v1 config** — `ridge / strength_only /
  strength_posterior`, same defaults. This exists solely so the stratification is comparable to the
  0.496 / 0.523 headline the story brief quotes, and as a stability check (do the two configs agree
  on the bucket ordering?).
  ⛔ **The secondary CANNOT constitute a pass under any circumstance.** It is not a member of any
  declared family and no clause below may be evaluated on it. Registering this forward is what
  stops "run two configs, report the one that clears."
- **Reuse, do not rebuild:** the CLV close join is P1.4's `build_clv_staging` verbatim (leakage-safe
  `_snapshot_ts < commence_time`, latest eligible snapshot, cross-book median). The OOS collection
  is P1.4's `_collect_oos` + `draw_joint` + `derive_markets` verbatim.

### 2a. Reproduction pin (a HALT gate, checked before any bucket is read)

Under the PRIMARY config the **pooled** figures must reproduce the S1-serve record:

- ATS n = **4114**, O/U n = **4135** (exact — these are join properties, already verified at
  assemble time: 4187 closes − 73 ATS pushes − 52 O/U pushes).
- ATS hit ≈ **0.509**, O/U hit ≈ **0.513**, ATS placebo ≈ **0.501**, each within **±0.010**
  (a Monte-Carlo tolerance; the side pick flips for games whose `p_cover` sits within ~2 MC standard
  errors of 0.5).

If the pin fails, the run **HALTS** and is diagnosed before any bucket number is looked at. A
stratification of a read that does not reproduce its own pooled parent is not evidence.

---

## 3. Design quantities (read before this document; no outcome information)

Non-push rows with a leakage-safe close, OOS seasons 2020–2025:

| bucket | rows w/ close | ATS non-push | O/U non-push |
|---|---|---|---|
| `wk1-3` | 715 | **701** | **705** |
| `wk4-6` | 853 | **832** | **843** |
| `wk7+`  | 2619 | **2581** | **2587** |
| pooled | 4187 | 4114 | 4135 |

Per-season `wk1-3` counts: 2020 **31**, 2021 138, 2022 139, 2023 141, 2024 130, 2025 136.
⚠️ 2020 is the COVID season — its early weeks were largely cancelled/postponed, so the `wk1-3`
bucket is 6 seasons but effectively ~5.2. Registered forward: a **leave-2020-out sensitivity** is
reported for every `wk1-3` figure. It is a SENSITIVITY and never the primary (MH2.8's
leave-one-anomalous-season discipline).

---

## 4. The statistic

Per bucket × market, on non-push rows only:

- `hit_rate` = fraction of games where the model's side (ATS: `P(home covers close) ≥ 0.5`;
  O/U: `P(total > close total) ≥ 0.5`) was correct against the closing number. This is P1.4's
  `_clv_eval` rule verbatim.
- `p_one_sided` = **exact binomial** one-sided p, H0: p = **0.5238**, H1: p > 0.5238.
- A per-season series `edge_s = hit_rate_s − 0.5238` over the 6 eval seasons, giving
  `fold_wins` (seasons with `hit_rate_s > 0.5238`) and `observed_sr = mean(edge)/sd(edge)`.

### 4a. Two different questions, kept apart

- **PRIMARY (binding): vs the breakeven 0.5238** — "is there a *profitable* edge at −110?"
- **SECONDARY (diagnostic, non-binding): vs 0.5000** — "is there *any* demonstrable signal against
  the close, before vig?"

⛔ The vs-0.5000 read may inform the narrative of a forward hypothesis. It may **never** be
substituted for the pass criterion, and no clause below may be re-read against it. (E2.1-r: the bar
is chosen before the result, not after it fails.)

---

## 5. Declared families and the multiplicity correction

Two coherent, mechanism-separated families, exactly as the story brief declares
("a BH-FDR correction across the 3 buckets"):

- **ATS family** = {`wk1-3`, `wk4-6`, `wk7+`} — 3 tests.
- **O/U family** = {`wk1-3`, `wk4-6`, `wk7+`} — 3 tests.

BH-FDR at **α = 0.05** *within* each family (cutoffs 0.01667 / 0.03333 / 0.05000 at ranks 1/2/3).
Splitting by market is the coherent declaration (MH2(a)): spread and total are different mechanisms
and bundling them would over-tax a real finding in either.

**Reported as a conservative SENSITIVITY:** the pooled 6-test BH (all buckets × both markets;
cutoffs 0.00833 … 0.05000). Combining is the *safe* direction, so a result that clears the 6-test
correction clears the 3-test one a fortiori. ⛔ The reverse substitution is forbidden: if the 3-test
correction is passed and the 6-test is not, the verdict is the **3-test** one (the declared family),
stated together with the 6-test failure — not a re-cut.

**PBO / CSCV is INAPPLICABLE by design**, not unmet: the buckets are a pre-registered partition, not
competing candidates for one slot, and no arm is selected. Multiplicity is handled entirely by
BH-FDR. `n_arms = 3` and `declared_field_size = 3` are nevertheless passed to `classify_null` so the
DSR benchmark is taxed for the declared 3-way family (⛔ never re-cut below 3 — MH2.2/MH2.7).

---

## 6. Pass criterion — a bucket "CLEARS" iff ALL of

1. **Material point estimate:** `hit_rate ≥ 0.5238` (the −110 breakeven).
2. **Deflated significance:** the exact one-sided binomial p vs 0.5238 survives **BH-FDR at α=0.05
   within its declared 3-test family**.
3. **Placebo separation:** `hit_rate > placebo_hit_rate` on the *same* rows (P1.4's matched
   random-side control, computed per bucket).
4. **Beats every pre-registered degenerate** on the same rows (§7) — a bucket that clears only
   because it agrees with a side bias in the closes is a MARKET finding, not a model finding.
5. **Non-degenerate n:** ≥ 200 non-push rows in the bucket (all three buckets already satisfy this
   by §3 — recorded so the clause is auditable, not so it can bind).
6. **Active:** the model actually takes both sides in the bucket — `min(side_home_frac,
   1 − side_home_frac) ≥ 0.10`. A bucket where the model always picks the same side cannot be
   scored as skill (NF-D20: count whether the mechanism could act before crediting a pass).

**A bucket that CLEARS is recorded as a FORWARD SHADOW-SEASON HYPOTHESIS for P2.2/P2.3 — and
nothing else.** `best_alpha = 0` stands regardless. No product claim, no serving change, no bet.
Confirmation can only come from a forward in-season CLV window (P0.6b-fed).

**All buckets null ⇒ the founding "early season is softest" premise is measured-null-at-the-close**,
qualified by the per-bucket power state in §8.

---

## 7. Pre-registered anchors (two-sided, per bucket × market)

| anchor | expected | why |
|---|---|---|
| `placebo` (random side, P1.4's control) | ≈ 0.500, must LOSE | the degenerate ceiling — a criterion a coin flip wins is fatal (NF1.8) |
| `always_home` (ATS) / `always_over` (O/U) | must LOSE | a side-bias degenerate — separates *model skill* from *a bias in the closing line*; if this WINS a bucket, the finding is about the market, not the model |
| `always_away` (ATS) / `always_under` (O/U) | must LOSE | the mirror, so the bias check is two-sided and cannot be satisfied by direction alone |

A degenerate that BEATS the model in a bucket does not merely fail clause 4 — it is reported as a
finding in its own right (an exploitable-looking closing-line bias is a different, and separately
non-shippable, claim).

---

## 8. Null classification — `cv_power.classify_null`, and the call-site band correction

Per bucket × market, `classify_null` is called with:
`metric=<market>_<bucket>`, `n_folds=6` (eval seasons 2020–2025), `n_arms=3`,
`declared_field_size=3`, `beats_foil = (hit_rate > 0.5238)` (the **decision** foil),
`observed_sr`, `var_trials_sr` (variance of the 3 same-family per-season Sharpes),
`fold_wins`, `p_one_sided`, `bh_cutoff`, empirical `skew`/`kurt` of the per-season edge series,
`mde_sd_units` = MDE in hit-rate percentage points, `meaningful_sd_units` = **2.38 pp**.

**Pre-registered practically-meaningful effect = one full vig-width above breakeven, i.e.
`hit_rate ≥ 0.5476` (+2.38 pp).** Derived from a DESIGN quantity known before any result — the −110
price — on the reasoning that a real edge should be at least as large as the friction it must
overcome. (≈ +4.5 % ROI at −110.)

**Exact-binomial MDE at 80 % power, one-sided α = 0.05, vs 0.5238** (computed from n alone, §3):

| bucket | ATS MDE | O/U MDE |
|---|---|---|
| `wk1-3` | 0.5714 (+4.76 pp) | 0.5710 (+4.72 pp) |
| `wk4-6` | 0.5667 (+4.29 pp) | 0.5666 (+4.28 pp) |
| `wk7+`  | 0.5485 (+2.47 pp) | 0.5484 (+2.46 pp) |
| pooled  | 0.5434 (+1.96 pp) | 0.5433 (+1.95 pp) |

⇒ **Registered in advance:** `wk1-3` (MDE +4.8 pp ≫ meaningful +2.38 pp) is **expected to be
POWER-LIMITED, not deflated** — a null there must NOT be reported as "the premise is dead".
**2,759** non-push games are needed to detect a one-vig-width effect at 80 % power; `wk1-3` has 701,
i.e. a deficit of ~2,058 games ≈ **~18 more NCAAF seasons** at ~117 non-push early games/season.
The pooled read (MDE +1.96 pp < +2.38 pp) is the only slice powered for a decision-changing effect.

### 8a. Call-site band correction (registered FORWARD)

`classify_null` returns `GENUINE_ABSENCE` on any `beats_foil = False`, short-circuiting before its
MDE branch. Against a *band* bar that reading over-claims at small n (a true +2 pp edge routinely
shows as −1 pp at n=701) — the mirror of the NF-W7i finding already carded against this instrument
("a band decision is not POWER_LIMITED when the interval excludes the band"). So the **RAW**
`classify_null` state is reported verbatim, and beside it a call-site-corrected state:

Let `U` = the one-sided upper confidence bound on the bucket hit rate at
**Bonferroni-adjusted α = 0.05/3 = 0.01667** (the conservative bound, because ruling an effect OUT
is a simultaneous claim across the family):

- `hit_rate ≥ 0.5238` → the corrected state **is** `classify_null`'s (it proceeds past `beats_foil`).
- `hit_rate < 0.5238` **and** `U < 0.5476` → **`MEASURED_IMMATERIAL`** — the entire plausible range
  lies below a decision-changing edge. Decisive; **no re-test trigger** is published.
- `hit_rate < 0.5238` **and** `U ≥ 0.5476` → **`POWER_LIMITED`** — the design cannot separate the
  null from a meaningful edge. Re-test trigger stated in **games and seasons**, never in p-decimals.

The MDE reading (pre-data: "what would I have caught?") and the interval reading (post-data: "what
is still consistent with what I saw?") answer different questions and can disagree; **the interval
reading binds** for a decisive claim, and any disagreement is reported explicitly rather than
resolved silently.

---

## 9. Monte-Carlo stability control

The side pick is a threshold on `p_cover` estimated from 4,000 draws, so games near `p_cover = 0.5`
can flip with the seed. The primary run's seed (42) is fixed above. Additionally the whole
stratification is re-scored at **2 extra seeds** and at **20,000 draws** and the across-run spread of
each bucket hit rate is reported as an MC error bar. ⛔ This **cannot change any verdict** — the
primary seed and draw count are pre-declared — it exists only to bound how much of a between-bucket
difference is draw noise rather than data (the NF-W7k discipline: measure the MC contribution, do
not assume it).

---

## 10. Scope

Query-only. No serving change, no model refit, no registry edit, no bet. `best_alpha = 0` before and
after, whatever the buckets say.
