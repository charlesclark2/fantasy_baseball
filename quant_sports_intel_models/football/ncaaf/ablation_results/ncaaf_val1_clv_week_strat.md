# NCAAF-VAL1 — early-season CLV stratification

**Status (2026-08-20): ✅ COMPLETE — verdict `ALL_BUCKETS_NULL`, and the founding premise is
directionally CONTRADICTED, not merely unsupported.** Query-only; no serving change, no refit, no
bet. `best_alpha = 0` before and after.

Pre-registration: [`ncaaf_val1_preregistration.md`](./ncaaf_val1_preregistration.md), committed at
`df8373cc` **before** a single bucket hit rate was computed. Machine record:
`ncaaf_val1_clv_week_strat.json`. Harness: `models/ncaaf_val1_clv_week_strat.py`.

---

## The question

The vertical repeatedly asserts that *"early season is where the college book is softest"* — the
sentence that motivated the P1.4 `strength_posterior` form swap. But the vs-close CLV eval is
**pooled over 2020–2025**, so a genuine week-1–3 edge could in principle be hiding under ~2,600
efficient late-season games. This is the cheapest possible test of that premise: stratify the
EXISTING CLV read by a pre-registered `season_order_week` bucket, once, and classify what comes out.

## The headline

**There is no early-season edge, and week 1–3 is the WORST of the three buckets in BOTH markets.**
The premise is not merely unproven — the point estimates run the opposite way.

| market | pooled | **wk1-3** | wk4-6 | wk7+ | breakeven |
|---|---|---|---|---|---|
| ATS | 0.5083 | **0.4936** | 0.5228 | 0.5076 | 0.5238 |
| O/U | 0.5137 | **0.4950** | 0.5291 | 0.5137 | 0.5238 |

**0 of 6 tests clear.** Not one bucket × market cell passes the pre-registered criterion, in either
declared 3-test BH family or in the conservative 6-test sensitivity.

And the ordering is **non-monotone** — worst early, best in the middle, mid late. A real regime
effect ("the book gets sharper as the season progresses") predicts a monotone decline. A
non-monotone ordering across three buckets is the signature of noise, which is exactly what the
null classification below says it is.

## Per-bucket result (PRIMARY: the served `ridge / strength_pace / strength_posterior`)

| market | bucket | n | hit | edge (pp) | ROI@−110 | placebo | best degenerate | p(>0.5238) | BH cut | MDE | upper bound | null state |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ATS | pooled | 4114 | 0.5083 | −1.55 | −3.10 % | 0.4995 | 0.5005 | 0.9778 | — | 0.5434 | 0.5212 | *(MEASURED_IMMATERIAL)* |
| ATS | **wk1-3** | 701 | **0.4936** | −3.02 | −5.77 % | 0.4879 | **0.5121** | 0.9494 | 0.0333 | 0.5714 | 0.5344 | **MEASURED_IMMATERIAL** |
| ATS | wk4-6 | 832 | 0.5228 | −0.10 | −0.19 % | 0.5096 | 0.5072 | 0.5362 | 0.0167 | 0.5667 | 0.5601 | **POWER_LIMITED** |
| ATS | wk7+ | 2581 | 0.5076 | −1.62 | −3.10 % | 0.4994 | 0.5017 | 0.9527 | 0.0500 | 0.5485 | 0.5287 | **MEASURED_IMMATERIAL** |
| O/U | pooled | 4135 | 0.5137 | −1.01 | −1.93 % | 0.4958 | 0.5018 | 0.9067 | — | 0.5433 | 0.5266 | *(MEASURED_IMMATERIAL)* |
| O/U | **wk1-3** | 705 | **0.4950** | −2.88 | −5.49 % | 0.4752 | **0.5362** | 0.9414 | 0.0500 | 0.5710 | 0.5358 | **MEASURED_IMMATERIAL** |
| O/U | wk4-6 | 843 | 0.5291 | +0.53 | +1.00 % | 0.5089 | 0.5172 | 0.3932 | 0.0167 | 0.5666 | 0.5661 | **DSR_UNREACHABLE** |
| O/U | wk7+ | 2587 | 0.5137 | −1.01 | −1.93 % | 0.4971 | 0.5014 | 0.8522 | 0.0333 | 0.5484 | 0.5348 | **MEASURED_IMMATERIAL** |

*"upper bound" = the one-sided Clopper–Pearson bound at the family-adjusted α = 0.05/3, the
conservative bound for a simultaneous ruling-out claim. The pooled rows are a **descriptive**
extension of the same deterministic rule — they belong to no declared family, carry no BH cutoff
and no pass verdict.*

### Pass criterion (§6) — which clauses actually fired

| cell | CLEARS | clauses that refused |
|---|---|---|
| ats/wk1-3 | ❌ | 1 material point · 2 BH · **4 beats degenerates** |
| ou/wk1-3 | ❌ | 1 material point · 2 BH · **4 beats degenerates** |
| ats/wk4-6 | ❌ | 1 material point · 2 BH |
| ou/wk4-6 | ❌ | 2 BH *(clause 1 PASSED — 0.5291 ≥ 0.5238)* |
| ats/wk7+ | ❌ | 1 material point · 2 BH |
| ou/wk7+ | ❌ | 1 material point · 2 BH |

⭐ **The side-bias degenerates earned their registration; the random-side placebo did not.** The
placebo (clause 3) passed in all six cells and discriminated nothing. The pre-registered *side-bias*
anchors (clause 4) fired in both `wk1-3` cells: `always_home` beat the model ATS (0.5121 vs 0.4936)
and `always_under` beat it on O/U (0.5362 vs 0.4950). **Reusable lesson: a random-side placebo is a
weak degenerate — it only tests that the metric is not a coin flip. The degenerate with teeth is the
one that encodes a plausible *bias* (always-home, always-under), because that is what a spurious
"edge" actually looks like.** Recommend carrying both into every future vs-close leg.

⚠️ **The winning degenerates are NOT themselves findings.** `always_under` at 0.5362 on n=705 is
p ≈ 0.24 against breakeven — nowhere near significant, and it is a *market* claim (an early-season
closing-total bias), not a model claim. It is reported because clause 4 fired, not because it stands.

## The wk1-3 verdict is DECISIVE, not underpowered — with a stated limit

The pre-registration predicted `wk1-3` would come back POWER_LIMITED (its MDE, +4.8 pp, is roughly
double the pre-registered meaningful effect of +2.38 pp). The **interval** reading, registered
forward in §8a and binding for a decisive claim, says something stronger:

- ATS wk1-3 family-adjusted upper bound **0.5344**; O/U wk1-3 **0.5358**.
- Both lie **below** the pre-registered meaningful effect **0.5476** (one full vig-width above
  breakeven, derived from the −110 price before any result).

⇒ **The wk1-3 slice does not merely fail to show a decision-changing early-season edge — it is
inconsistent with one.** Same conclusion for wk7+ and for the pooled read.

🚧 **The precise limit of that claim, stated because it is easy to over-read:** both upper bounds sit
*above* the 0.5238 breakeven. So what is excluded is a **decision-changing** edge (≥ +2.38 pp,
≈ +4.5 % ROI). A *marginal* edge — one that barely clears the vig — is **not** excluded by this
data, and could not be: distinguishing 0.5238 from 0.5300 needs ~40,000 non-push games — an order of magnitude beyond even the 18-season figure below.

### The MDE and the interval disagree, and that is expected

The MDE (+4.8 pp) and the interval (excludes +2.38 pp) answer different questions — *"what would I
have caught?"* (pre-data) versus *"what is still consistent with what I saw?"* (post-data). The
interval is sharper here **because the observed rate landed low**: had `wk1-3` come in at 0.53, the
same n would have produced an upper bound well above 0.5476 and the honest verdict would have been
POWER_LIMITED. Both readings were registered in advance precisely so this could not be chosen after
the fact.

### The one bucket that is genuinely undecidable

`wk4-6` is the only slice whose interval still admits a meaningful edge (upper bounds 0.5601 /
0.5661), and O/U wk4-6 is the only cell whose point estimate clears breakeven (0.5291, +1.0 % ROI,
4 of 6 seasons above breakeven). It is nowhere near significant — **p = 0.3932 against a BH cutoff
of 0.0167, off by a factor of 24** — so the binding constraint is significance, not deflation.

`classify_null` additionally returns **DSR_UNREACHABLE** for it (per-season Sharpe 0.322 vs the
declared 3-arm field's SR0 0.405) and — correctly — reports that **field size is not the lever**:
even a 2-arm field does not clear at this fold count and dispersion. Per MH2.2/MH2.7 the field is
the declared 3 buckets and may not be re-cut below it (`declared_field_size=3`). Following NF-W7f,
this is *reported*, not converted into a re-registration recommendation: the binding gate is BH by a
wide margin, so "the field did it" is not the diagnosis here.

⛔ **`wk4-6` is NOT recorded as a forward shadow-season hypothesis.** It failed the pre-registered
criterion. Elevating "the bucket that looked least bad" would be exactly the E2.1-r inversion this
story was designed to avoid. It is recorded as *undecidable at this n*, with the re-test trigger
below.

## Re-test trigger — stated in games and seasons, never in p-decimals

Detecting a one-vig-width edge at 80 % power needs **≈ 2,785 non-push games** (the exact-binomial
requirement is a sawtooth in n: power first reaches 0.80 at n≈2,729 and holds from n≈2,785; the
pre-registration's 2,759 landed inside that sawtooth — the conservative 2,785 is used here).

| bucket | has | needs | deficit | ≈ seasons at this bucket's rate |
|---|---|---|---|---|
| `wk1-3` | 701 | 2,785 | 2,084 | **~18 more seasons** |
| `wk4-6` | 832 | 2,785 | 1,953 | **~14 more seasons** |

⇒ **The early-season hypothesis is not testable to a decision-grade standard from historical CLV.**
This is a design fact, not a data-collection to-do: a full extra decade and a half of college
football would be needed, and the sport's own regime would not hold still across it. If the question
matters, the answer has to come from a **higher-frequency design** (more markets per game — props,
alternate lines, first-half — or a sharper statistic than a binary hit rate), not from waiting.

For `wk1-3` the trigger is published only for `wk4-6`; **`wk1-3` publishes NO re-test trigger**,
because its interval already excludes the effect the trigger would be sized on (NF-D18: a decisive
result must not carry a "come back with more seasons" note).

## Controls

**Reproduction pin (§2a — a HALT gate, checked before any bucket was read).** The pooled read
reproduces the recorded S1-serve CLV exactly:

| | got | recorded | |
|---|---|---|---|
| ATS n | 4114 | 4114 | ✅ exact |
| O/U n | 4135 | 4135 | ✅ exact |
| ATS hit | 0.5083 | 0.509 | ✅ |
| O/U hit | 0.5137 | 0.513 | ✅ |
| ATS placebo | 0.4995 | 0.501 | ✅ |

The n figures are *exact* (4,187 closes − 73 ATS pushes − 52 O/U pushes), which proves the close
join was reused rather than rebuilt. The placebo reproduces because the harness consumes the RNG
stream in P1.4's exact order — reordering those calls would have silently broken this pin.

**MC stability (§9).** Re-scoring at 2 extra seeds and at 20,000 draws moves each bucket hit rate by
at most **0.59 pp** (max−min). The wk1-3-vs-wk4-6 gap is 2.9 pp (ATS) / 3.4 pp (O/U) — ~5× the draw
noise. **The bucket ordering is data, not Monte Carlo.**

**Config robustness (§2, cannot pass).** The P1.4 v1 `strength_only` config reproduces the same
ordering in both markets — ATS 0.4922 / 0.5228 / 0.5076, O/U 0.5050 / 0.5255 / 0.5164. `wk1-3` is
the worst bucket under both configs; `wk4-6` the best under both.

**Leave-2020-out (§3, COVID).** 2020 contributed only 31 `wk1-3` games. Dropping it moves ATS
wk1-3 to 0.5000 (n=670) and O/U wk1-3 to 0.4926 (n=674) — **still below breakeven, still the worst
bucket.** The `wk1-3` null is not a COVID artifact.

**Multiplicity sensitivity (§5).** Nothing clears under the declared 3-test families; nothing clears
under the conservative pooled 6-test correction either. The verdict does not turn on the choice.

## Where wk1-3 actually loses — descriptive attribution (⛔ no inferential claim)

| bucket | model takes home (ATS) | home actually covered | model takes over (O/U) | over actually hit |
|---|---|---|---|---|
| wk1-3 | 0.417 | 0.512 | 0.574 | **0.464** |
| wk4-6 | 0.508 | 0.493 | 0.618 | 0.517 |
| wk7+ | 0.513 | 0.498 | 0.577 | 0.501 |

The model carries a **persistent over-tilt** (57–62 % of O/U picks are OVER in every bucket). That
tilt is roughly free in wk4-6/wk7+ (over hits ≈ 0.50–0.52) and is **punished in wk1-3, where over
hit only 0.464**. Symmetrically on ATS, wk1-3 is the one bucket where the model leans *away* from
home (0.417) while home covered slightly more often (0.512).

⇒ **The most actionable lead this story produces is about our own model, not the market: the served
total mean looks systematically HIGH relative to the close in weeks 1–3** — the cold-start regime
where in-season efficiency features are NULL and the strength posterior is at its widest. That is a
mean-calibration question for a P2.x successor, and it is *market-blind* (a comparison of our μ to
the close, not an edge claim).

⚠️ Scope: this table is a post-hoc description of an already-decided null, not a test. The market
half of it is not established — over hitting 0.464 on n=705 is ~1.9 SE from 0.50 (two-sided
p ≈ 0.055), so *"early-season closing totals are too high"* is **not** a claim this story supports.
What *is* solid is our model's tilt, because that is a property of the model, not a sample statistic.

## Instrument finding — a 5th call-site correction of `cv_power.classify_null`

`classify_null` returned **`GENUINE_ABSENCE` for 5 of the 6 buckets**, because any below-foil point
estimate short-circuits before its MDE branch. Two problems, both registered forward in §8a and
both material:

1. At n = 701 a true +2 pp edge routinely presents as −1 pp, so `GENUINE_ABSENCE` ("no sample size
   rescues a negative point estimate — do NOT re-test") **over-claims**.
2. It is *actively misleading in the wrong direction* for `ats/wk4-6`, whose interval still admits a
   meaningful edge: the raw instrument would have published "do not re-test" for the one ATS bucket
   that is genuinely undecidable.

The raw state is preserved verbatim beside a call-site-corrected state (the NCAAF-P2.1-S1b pattern:
fix at the call site, never mutate the shared instrument's output). This is the **mirror** of the
carded NF-W7i finding ("a band decision is not POWER_LIMITED when the interval excludes the band"),
and it is the 5th downstream hand-correction of this instrument — which per MH2.7's own lesson makes
it a defect in the instrument, not in its callers. **Recommended for the carded `classify_null`
fix:** when `meaningful_sd_units` is supplied, a below-foil point estimate should consult the
interval before returning `GENUINE_ABSENCE`.

A second, unrelated defect was found and fixed in this story's own harness before the binding run:
`observed_sr` lives under `per_season`, so reading it at the top level yielded an empty list,
collapsed `var_trials_sr` to zero, and made `classify_null` **skip its DSR branch entirely** — every
verdict still plausible, the deflation leg never run (the NF-C0e wired-but-never-invoked class). It
is now an explicit `SystemExit` rather than a silent skip, and guarded.

## Verdict

**`ALL_BUCKETS_NULL` — the founding "early season is softest" premise is measured-null at the close,
and directionally contradicted at the point estimate.**

- **No forward shadow-season hypothesis is produced.** Nothing cleared; promoting the least-bad
  bucket would be the E2.1-r inversion.
- **`best_alpha = 0` stands**, unchanged, on the same basis as before.
- **What the premise may still legitimately claim:** P1.4's early-season finding was about
  *calibration* — the homoscedastic form under-covers weeks 1–2 (0.785) and the posterior-predictive
  fixes it (0.804). That result is untouched and remains the correct reason to serve
  `strength_posterior`. ⛔ What must stop is the *slide* from "our uncertainty is honestly wider
  early" to "the book is softer early, so there is edge there." **The first is measured and true;
  the second is measured and false.** Any card, prompt or doc that motivates work with the second
  sentence should be corrected to the first.

## Follow-ons (registered as leads, not conclusions)

1. **The early-season total-mean tilt** (side-tilt table above) — a market-blind μ-calibration
   question for P2.x, the one place this story found something to fix.
2. **The `classify_null` band correction** — feed the §8a rule into the carded instrument fix.
3. ⛔ **Do not card "re-test the early-season CLV edge with more seasons."** It needs ~18, the
   interval already excludes the effect that would matter, and the honest lever is a
   higher-frequency design.

## Files

- `models/ncaaf_val1_clv_week_strat.py` — the harness (query-only; reuses P1.4's close join, OOS
  collection, dispersion fit and joint draws verbatim).
- `models/ncaaf_val1_red_proof.py` — 16 deliberate breaks, **16/16 RED**.
- `betting_ml/tests/test_ncaaf_val1_clv_week_strat.py` — 26 fast-gate guards.
- `ablation_results/ncaaf_val1_preregistration.md` · `ncaaf_val1_clv_week_strat.json`.

Runtime: assemble ≈ 10 s, the full stratification (2 configs + 3 MC replicates) ≈ 35 s — both well
inside the laptop budget; no operator run required.
