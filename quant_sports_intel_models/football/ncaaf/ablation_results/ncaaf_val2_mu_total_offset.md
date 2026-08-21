# NCAAF-VAL2 — μ_total − close_total, decomposed

**Verdict: `HAND_TO_VAL3_SCOPED` — the tilt is real and worth a repair, but the repairable target is
the COLD-START weeks, not a pooled level.** And a second, unplanned finding: **the vs-close CLV
evaluation this study was commissioned to extend is row-misaligned at the source**, so VAL1's
`side_tilt` table — the exact table that motivated this card — is an artifact.

`best_alpha = 0`, unchanged. Query-only: no refit of a served artifact, no serving write, no
registry edit, no bet. Market-blind in the vertical's sense (the model never sees a market feature,
re-asserted in-run) and **no edge claim is made anywhere below**.

---

## 1. Why a side split could not answer this

VAL1 recorded that the served model takes the OVER on ~58.5 % of games while the close is
median-unbiased (over hits ~49.8 %), and called it a directional totals tilt. But VAL1 only ever
computed **P(over)** — a SIDE statistic. A side says which way we lean; it cannot say by how much,
and it cannot say whose error the lean is. This study measures the level and splits it:

```
μ_total − close_total   =   (μ_total − y_total)   +   (y_total − close_total)
   ── the offset ──          ── OUR mean error ──      ── close vs realised ──
```

That identity is the whole point, and it is asserted in code (max |residual| ≤ 1e-9 or the builder
refuses). The two halves **point in opposite directions in the cold-start weeks**, so the offset
*understates* the half a μ-recalibration could actually repair — by more than a factor of two.

---

## 2. ⚠️ The finding that came first: the vs-close CLV read is misaligned

`bakeoff_ncaaf_game._clv_eval` (P1.4, and thence S1-serve) and `ncaaf_val1_clv_week_strat.score_config`
(VAL1) both do this:

```python
m = oos.merge(close, on="game_id", how="left")
m = m[m["has_close"] == True].reset_index(drop=True)   # index is now 0..n-1
idx = m.index.to_numpy()                               # ← NOT the original row positions
p_over = (dists["total"][idx] > tot_line[:, None]).mean(axis=1)
```

`dists["total"]` is `(n_games, n_draws)` over the **full** OOS frame. After the reset, `idx` is
`0..n−1`, so the read takes the **first n rows of the draw array**, not the rows that carry a close.
Measured on this cache:

| | value |
|---|---|
| rows whose as-coded index ≠ its true position | **100.0 %** (4,182 of 4,182) |
| first five true positions | 1546, 1548, 1549, 1550, 1551 |
| seasons the as-coded index actually reads | 2018–2023 |
| seasons that actually carry a close | 2020–2025 |

The served form (`strength_posterior`) is a heteroscedastic **Gaussian**, so its median *is*
`mu_total` and `P(over) ≥ 0.5` and `mu_total > close_total` are the same event up to Monte-Carlo
noise. That gives a two-sided control with an arithmetic expectation rather than a chosen tolerance:

| index used | agrees with `sign(μ − close)` |
|---|---|
| **repaired** (true positions) | **0.9802** |
| **as-coded** (`0..n−1`) | **0.6968** |

At 4,000 draws the MC standard error on P(over) is ≈0.0079, so a side can only flip inside
|offset| < **0.33 pts** — a band ~2 % of rows occupy. **0.980 is the arithmetic prediction; 0.697 is
what reading another game's distribution looks like.**

**What this does and does not overturn.** (The harness emits this comparison itself — `alignment_control.{repaired,as_coded}_read` — so it is regenerable, not a one-off script's output.) Repairing the index on this cache moves the pooled O/U hit
rate 0.5193 → **0.5127** and the `wk1-3` bucket 0.5242 → **0.4986**, and it *reverses the ordering of
the model's over-tilt across buckets* (as-coded: `wk4-6` leans over most at 0.624; repaired:
`wk7+`/`wk1-3` at 0.615/0.608). So:

- **VAL1's `ALL_BUCKETS_NULL` verdict survives** — every repaired bucket still sits below the 0.5238
  breakeven. But a misaligned eval cannot *earn* a null; it is guaranteed to produce one. The
  repaired read earns it, the recorded one did not.
- **VAL1's `side_tilt` table is an artifact** — it is the table that produced "the model's over-tilt
  is punished in wk1-3" and this card's 58.5 % premise, and it was reading the wrong games.

⛔ **Repairing it is out of scope here** (VAL2 is query-only) and it is not free: the fix changes
every recorded model-vs-close hit rate in **P1.4, S1-serve and VAL1**. It is carded for the operator
in §8, and a **tripwire guard** (`test_the_upstream_clv_misalignment_is_still_present_TRIPWIRE`) goes
RED the moment someone fixes it, with the required re-run list in its docstring.

**This study is immune to that defect by construction**, and the immunity is guarded: it joins on
`game_id` and reads each row's own `mu_total`; an AST guard fails the build if any positional read
into a draw array appears outside the alignment control.

---

## 3. The offset, pooled

n = 4,182 close-carrying OOS games (2020–2025; 53 pushes, kept — a push is a property of the
outcome, not of the line). σ_total = **16.642** (the OOS-residual fit, matching the ≈16.6 the card
cites).

| term | mean | median | sd | IQR | σ units | naive SE | season-clustered SE | clustered t (df 5) | 95 % CI |
|---|---|---|---|---|---|---|---|---|---|
| **μ − close** (offset) | **+1.144** | +1.257 | 4.89 | [−1.98, +4.41] | +0.069σ | 0.076 | 0.503 | +2.09 | [−0.24, +2.35] |
| **μ − y** (our error) | +0.670 | +1.517 | 16.48 | [−9.73, +12.22] | +0.040σ | 0.255 | 0.470 | +1.17 | [−0.66, +1.76] |
| **y − close** (close) | +0.474 | +0.000 | 15.98 | [−11.00, +10.50] | +0.029σ | 0.247 | 0.348 | +1.45 | [−0.39, +1.40] |

- μ sits above the close in **60.8 %** of games — the correct value of the statistic VAL1 recorded as
  58.5 % off the misaligned read.
- The offset moves P(over) by **+2.74 pp** at the line (`dP/dμ = φ(0)/σ`).
- **The clustered SE is 6.7× the naive one.** Games inside a season share one fitted strength
  surface, one scoring environment and one training window, so `sd/√n` is the wrong uncertainty for
  a *level* (NF1.8's per-group rule). On the naive SE the pooled offset is t ≈ 15; on the clustered
  one it is t = 2.09 against a critical 2.57. **Pooled, this is not a demonstrated level at all.**
- **41 % of the offset is not ours to repair** (see §4), leaving +0.670 pts — and that half's CI
  spans zero.

---

## 4. Is the close a MEDIAN line? — the 41 % that a μ-repair must NOT remove

| | value |
|---|---|
| P(realised > close), non-push | **0.4987** (n = 4,129; exact two-sided p vs .50 = **0.876**) |
| median(y − close) | **+0.000** |
| mean(y − close) | **+0.474** |
| realised total: mean / median / skew | 54.107 / 53.000 / **+0.368** |
| mean − median of the realised total | **+1.107 pts** |

The close is **median-unbiased to three decimals** and simultaneously sits ~0.47 pts *below* the mean
realised total. Both are true because the total is right-skewed: a shootout has no mirror image below
zero points. NCAAF-P2.5 measured exactly this (fitted skew-normal α ≈ +2.12, `REFERENCE_STANDS` —
the served predictive is still the symmetric Gaussian).

⇒ **Our μ is a conditional MEAN; the market's number behaves like a conditional MEDIAN.** A mean sits
above a median on a right-skewed target *with no model defect at all*. Shifting μ down to close that
part of the gap would move our conditional mean **away** from the realised conditional mean — a
metric-inversion of exactly the E2.1-r shape (optimising toward the wrong target because the units
were never checked). The principled instrument for that half is a **skew-aware predictive form**
(P2.5, already measured), not a level shift.

⚠️ Scope, inherited verbatim from VAL1: the strictly-market reading of `y − close` is **not** a claim
this study supports. It is reported as the second half of an arithmetic identity.

---

## 5. Where the model's own error actually lives

| bucket | n | μ − close | **μ − y** | y − close | μ−y seasons > 0 | μ−y clustered t |
|---|---|---|---|---|---|---|
| **wk1-3** | 713 | +1.369 | **+2.547** | **−1.178** | **6/6** | **+4.14** |
| wk4-6 | 853 | +0.822 | −0.626 | +1.448 | 2/6 | −1.42 |
| wk7+ | 2,616 | +1.187 | +0.581 | +0.606 | 4/6 | +0.97 |

**In the cold-start weeks the two halves fight each other**: our μ runs +2.55 pts hot while the
realised total came in 1.18 pts *under* the close. They partially cancel, so the offset there reads
+1.37 — **less than 54 % of our own error.** A VAL3 sized off the offset would under-correct by more
than half. This is the decomposition earning its keep.

By week, the effect is a sharp three-week decay and then nothing:

| wk | 1 | 2 | 3 | 4 | 5 | 6 | 7+ (range) |
|---|---|---|---|---|---|---|---|
| **μ − y** | **+4.83** | **+2.88** | +0.28 | −1.11 | +0.48 | −1.29 | −1.55 … +2.22 |

Week 1 is where the in-season efficiency features are NULL by construction (the pace composites are
NULL in week 1 — that is what makes the served pace term inert pre-season), so the mean falls back on
a prior that runs hot. ⚠️ That is a *plausible* mechanism, not a tested one — attributing it needs a
matched foil of its own (NF-D15), which is VAL3's job, not this study's.

**Note the sign of `wk4-6`: −0.63.** A pooled level correction would make that bucket *worse*.

---

## 6. Is `wk1-3` special, or is it a season-wide level in a cold-start costume?

A per-bucket read cannot tell those apart — a level bias is positive in `wk1-3` too. So the binding
statistic is the **matched contrast**, paired *within* season so any season-wide level cancels
exactly (NF-D10: read the paired delta, not the rank):

```
Δ_season = mean(μ−y | wk1-3, season) − mean(μ−y | wk4+, season)
```

| | value |
|---|---|
| early / late means | +2.547 / +0.284 |
| **Δ** | **+2.118 pts** (= +0.127σ) |
| 95 % CI (paired, 6 seasons) | **[+0.424, +3.812]** |
| t (df 5) | **+3.21** vs critical 2.571 |
| per-season Δ | +2.18, +2.31, **−0.60**, +3.65, +3.77, +1.40 |
| seasons positive | 5/6 |

The cold-start effect is **demonstrated** (the interval excludes zero) and its point estimate is
**2.1× the materiality band**. It is not a level in disguise.

---

## 7. Controls, and one place where two instruments disagree

**All three sign-stability controls discriminate** (a set that only ever says "nothing here" cannot
certify a null; one that always says "found it" cannot certify a finding):

| control | result | required |
|---|---|---|
| injection at 1.5 × MDE (+2.93 pts) | detected | must detect |
| injection at 0.4 × MDE (+0.78 pts) | not detected | must not |
| cluster-mean-centred null | not detected | must not |
| **season permutation** (2,000 shuffles) | **p = 0.700** | reported, see below |

⚠️ **The season permutation is a real result and it disarms a statistic this study might otherwise
have leaned on.** `wk1-3`'s "positive in 6/6 seasons" is reproduced by a *shuffled* season field 70 %
of the time — because the cell mean is large relative to the within-season noise, not because the
season structure carries anything. **So the sign test adds no evidence beyond the level, and it is
reported but is NOT a verdict clause** (NF1.8: a statistic a degenerate wins cannot select). A guard
proves it is not acting as a hidden clause — flipping sign stability does not move the verdict.

**Two readings, disclosed side by side.** `resolvable` (|mean| ≥ the 80 %-power clustered MDE) is a
*pre-data* question about the design; `demonstrated` (does the CI exclude zero?) is a *post-data*
question about what was found. They can disagree, and here they do — on exactly one cell:

| cell | μ−y (clustered) | 95 % CI | demonstrated | material | MDE | resolvable |
|---|---|---|---|---|---|---|
| pooled | +0.548 | [−0.66, +1.76] | ✗ | ✗ | 1.64 | ✗ |
| **wk1-3** | **+2.322** | **[+0.88, +3.76]** | **✓** | **✓** | 1.96 | ✓ |
| wk4-6 | −0.716 | [−2.02, +0.58] | ✗ | ✗ | 1.77 | ✗ |
| wk7+ | +0.507 | [−0.84, +1.85] | ✗ | ✗ | 1.83 | ✗ |
| **contrast** | **+2.118** | **[+0.42, +3.81]** | **✓** | ✓ | 2.30 | **✗** |

`demonstrated` **binds**, and the reason pre-dates this story: NF-W7i recorded that a band /
materiality decision consults the **interval**, and that reporting an effect as merely under-powered
when the interval already answers the question is the actively-misleading direction. An effect can be
significant while sitting below the 80 %-power MDE — significance and power are different bars.

⭐ **Full disclosure, because the choice changes the answer:** under the MDE rule the verdict would be
`NOT_WORTH_A_REPAIR`. The two rules disagree on the contrast alone (MDE says no, CI says yes). Both
readings are emitted in the JSON (`verdict.reading_disagreement`) so a reader can apply either without
re-running. No clause here was chosen after seeing a result: the 1.0-pt materiality band is the
card's own acceptance criterion, held as a module constant and guarded against being re-derived from
any measured value.

---

## 8. ⚠️ Provenance — this run is one cache vintage behind VAL1

The on-disk P1.4 cache is the **2026-07-22** assembly: **4,182** closes, and it predates
NCAAF-P2.1-S1-serve, so it does not carry the two served pace composites. VAL1, S1-serve and the
whole P2.1 battery scored a **2026-08-20** re-assembly with **4,187** closes, which exists in no
checkout on this machine.

Handled as follows, and visibly:
- The pace composites are derived in-session by the **same shared `derive_pace_composites`** the
  assemble path calls, from columns already in the frame — a deterministic local transform, **not a
  data pull** — and the fact that it happened is stamped in the artifact and printed at the top of
  every run.
- The vintage gap is flagged `⚠️ VINTAGE MISMATCH`, never silently absorbed.
- Consequently **VAL1's exact recorded figures do not reproduce here** — its §2a pin fails on
  `ats_n` (4110 vs 4114) and `ats_hit` (0.4976 vs 0.509).
- ⚠️ **What that does NOT establish, stated because it is the tempting inference:** whether this
  run's **μ** differs from VAL1's is *not* determined by those figures. VAL1's recorded hit rates
  come through the misaligned path of §2, whose row set is `0..n−1` — so a change in `n` alone
  shifts *which games are read*, and the recorded numbers cannot isolate a change in μ from a change
  in the population. The population difference is measured (4,182 vs 4,187 closes); a μ difference
  is **not measured either way** here.

**⛔ The 2026-08-20 vintage is not locally reproducible.** `--assemble --matrix-source parquet`
requires the P1.3 artifact `models/artifacts/feature_ncaaf_pregame_matrix.parquet`, which is
gitignored (absent in a fresh worktree) and, in the main checkout, dated **2026-07-21** — older than
the 07-22 cache, so it cannot rebuild the 08-20 assembly. `--matrix-source s3` pulls **today's**
Delta matrix, i.e. a *third* vintage, not VAL1's. VAL1's cache exists in no checkout. ⇒ the realistic
choices are to leave these levels as recorded here, or to re-quote them on the CURRENT vintage —
which is arguably the better target anyway, since VAL3 would be built against current data rather
than against VAL1's snapshot.

⚠️ **Footgun if anyone does re-assemble:** `assemble_cache` catches a failing CLV odds join, logs an
ALERT, and **still writes the cache** — with `has_close = False` on every row. A credential or
network failure there therefore replaces the only working cache on the machine with a close-less one,
and VAL2/VAL1/P1.4's vs-market legs all stop running until a successful re-assemble. Back the cache
up first (`cp betting_ml/data/cache/ncaaf_p1_4_game_matrix.{parquet,meta.json} /tmp/`).

**What that does and does not put at risk.** The misalignment finding is a property of the **source
code** and the decomposition is **arithmetic** — neither depends on the population. The offset
**level** does. The *sign* and the concentration in the cold-start weeks are structural (they track a
feature block that is NULL by construction in week 1) and are unlikely to flip, but that is a
judgement, not a measurement. ⇒ **operator step: re-run `--assemble`, then re-run this module** (16 s)
to quote §3–§6 against the recorded vintage before VAL3 sizes anything off them.

---

## 9. Verdict and what VAL3 inherits

**`HAND_TO_VAL3_SCOPED`, target cell `wk1-3`.**

- ✅ **Real** — demonstrated at the season-cluster level on both the cell (+2.32, CI [+0.88, +3.76])
  and the matched within-season contrast (+2.12, CI [+0.42, +3.81]).
- ✅ **≥ ~1 pt** — 2.1–2.5 pts, i.e. 2.3× the band, and 0.15σ.
- ⛔ **NOT a pooled level repair.** The pooled μ−y CI spans zero, `wk4-6` is *negative*, and the level
  drifts monotonically across seasons (μ−close: −0.06, −0.87, +1.31, +1.92, +1.87, +2.14). NF-TR2
  measured what happens when a full-history level constant is fitted to a non-stationary level: it
  over-corrects and is refused by its own no-inflation gate.
- ⛔ **~41 % of the pooled offset is a mean-vs-median unit mismatch and must be left alone.** The
  instrument for that half is a skew-aware form (P2.5), not a shift in μ.

**Three constraints VAL3 inherits, all measured here:**

1. **Size the repair off `μ − y`, never off the offset.** In `wk1-3` the offset is 54 % of our own
   error because the two halves partially cancel.
2. **Select the correction magnitude IN-FOLD.** This design places the cold-start effect only within
   [+0.42, +3.81] at 6 season clusters; inheriting +2.5 as a constant fitted with the answer in view
   is the NF-D18/NF-D20 inadmissible-λ shape.
3. **A level move is not free on a right-skewed target.** Check that any μ shift does not degrade the
   PIT / interval calibration P1.4 serves `strength_posterior` to protect.

**Operator / PM follow-ons**

1. ⚠️ **Card the CLV misalignment as an incident.** It is not a serving defect — nothing bets on it
   (`best_alpha = 0`) and no serving path reads `_clv_eval` — but it invalidates the recorded
   model-vs-close numbers in **P1.4, S1-serve and VAL1** and makes VAL1's `side_tilt` table an
   artifact. Repair (`idx = np.flatnonzero(mask)` taken BEFORE the reset), then re-run all three and
   re-read VAL1's verdict against the repaired figures. The tripwire guard enforces the re-run list.
2. **Recommended CLAUDE.md landmine** (a new class, for the operator to add — sessions do not edit
   that file unilaterally): *a `df[mask].reset_index(drop=True)` followed by `idx = df.index` does
   NOT recover the original row positions; indexing a parallel `(n_rows, …)` array with it silently
   reads the WRONG rows and produces a plausible ~50 % result. Take `np.flatnonzero(mask)` BEFORE the
   reset. It is invisible to CI (the shapes are right, no error is raised) and the symptom is noise,
   which is indistinguishable from an honest null.*
3. **Re-run this module after `--assemble`** to put §3–§6 on the recorded cache vintage.

## Files

- `models/ncaaf_val2_mu_total_offset.py` — the harness (query-only; join-based, never positional).
- `models/ncaaf_val2_red_proof.py` — 22 deliberate breaks, **22/22 RED**.
- `betting_ml/tests/test_ncaaf_val2_mu_total_offset.py` — 29 fast-gate guards (incl. the upstream
  tripwire).
- `ablation_results/ncaaf_val2_mu_total_offset.json` — every figure above, machine-readable.

Runtime: **16 s** end-to-end on the laptop (one OOS collection + one draw for the alignment control).
No operator run required to reproduce what is written here; the `--assemble` re-run in §8 is a
separate, optional step to re-quote the levels on VAL1's vintage.
