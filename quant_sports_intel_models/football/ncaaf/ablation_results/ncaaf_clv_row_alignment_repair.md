# NCAAF-CLV-repair — the vs-close eval reads the rows that carry a close

**Verdict: `REPAIRED_AND_RE-RUN`.** Both call sites fixed, P1.4 / S1-serve / VAL1 re-run on the
repaired path, and VAL1's verdict re-read. Model/eval correctness only: **no serving change, no
refit of a served artifact, no registry edit, no bet.** `best_alpha = 0` before and after.

Discovered by NCAAF-VAL2 §2, which measured the defect and left a deliberate tripwire guard
(`..._is_still_present_TRIPWIRE`) carrying the re-run list. This story discharges it.

---

## 1. The defect

Both `bakeoff_ncaaf_game._clv_eval` (P1.4 → S1-serve) and `ncaaf_val1_clv_week_strat.score_config`
(VAL1) did this:

```python
m = oos.merge(close, on="game_id", how="left")
m = m[m["has_close"] == True].reset_index(drop=True)   # index is now 0..n-1
idx = m.index.to_numpy()                               # ← NOT the original row positions
p_over = (dists["total"][idx] > tot_line[:, None]).mean(axis=1)
```

`dists["total"]` is `(n_games, n_draws)` over the **full** OOS frame, so row *i* of the draw array is
row *i* of `oos`. After `reset_index(drop=True)` the original positions are gone and `idx` is
`0..n−1` — the **first n rows of the draw array**, not the rows carrying a close. Every read took
some *other* game's predictive distribution and compared it to *this* game's closing number.

**100.0 % of 4,182 rows misindexed.** The as-coded index reads seasons 2018–2023; the rows that
carry a close are 2020–2025.

## 2. The repair

`np.flatnonzero(mask)` taken **before** any reset, at both sites:

```python
merged = oos.merge(close, on="game_id", how="left")
if len(merged) != len(oos):                  # ← new: the positional read needs this invariant
    raise SystemExit(...)                    #   a duplicated close key would silently re-index
mask = (merged["has_close"] == True).to_numpy()
idx = np.flatnonzero(mask)                   # TRUE positions into the (n_games, n_draws) arrays
m = merged[mask].reset_index(drop=True)
```

The row-count HALT is new and load-bearing: the whole read is positional, so `merged` row *i* must
BE `dists[...][i]`, and a duplicated close key would break that silently. `build_offset_frame`
(VAL2) already asserted it; the two eval paths did not.

**The two-sided control.** The served form is a heteroscedastic Gaussian, so its median *is* `mu` and
"the model takes the over" and `mu_total > close_total` are the same event up to Monte-Carlo noise.
That gives an arithmetic expectation rather than a chosen tolerance:

| index used | agrees with `sign(μ − close)` — total | — margin |
|---|---|---|
| **repaired** | **0.9802** | **0.9790** |
| as-coded | 0.6968 | 0.5478 |

(`total` on the served `strength_pace` config from `ncaaf_val2_mu_total_offset.json`
`alignment_control`; `margin` on `strength_only`. At 4,000 draws the MC standard error on P(over) is
≈0.0079, so a side can only flip inside |offset| < 0.33 pts — ~2 % of rows.)

⭐ The two as-coded figures differ for a reason worth keeping: **totals are homogeneous across games
and spreads are not.** A random other game's *total* distribution still tends to sit above this
game's total line, so the misaligned O/U read scores 0.697; a random other game's *margin*
distribution has no such luck against a spread ranging ±40, so the misaligned ATS read is a coin
flip at 0.548. The defect was hardest to see on the leg where the market is most homogeneous.

## 3. ⚠️ The headline hit rate could not have detected this — measured twice

**The ATS leg lands on exactly 2,039 / 4,110 under BOTH reads — while 45.8 % of the underlying sides
flip.** Identical to the integer, on a statistic built from 4,110 decisions of which 1,883 differ.

It is not a coincidence so much as a consequence: the ATS side carries no edge, so flipping a
near-random side on a near-50 % market returns you to the same place. A before/after diff of the
headline would have concluded "the repair changed nothing for ATS", which is exactly wrong.

The same trap fired a second time, differently: S1-serve's **recorded** O/U hit rate (0.5127, on the
2026-08-20 vintage, misaligned) is **numerically identical** to its **repaired** value (0.5127, on
the 2026-07-22 vintage). Diffing the two recorded numbers again says "nothing changed"; a
like-for-like read on one vintage says 0.5193 → 0.5127.

⇒ **the discriminating statistic is the side-agreement control of §2, not the hit rate.** This is
the vertical's own recurring class (a metric a correct pipeline and a broken one both produce cannot
certify the pipeline) and it is why the guard suite's load-bearing test is numerical, not textual.

## 4. What the re-runs produced

All three on one cache vintage (**2026-07-22, 4,182 closes**) so the repair is the only thing that
differs. Runtime 18–34 s each; no operator run required.

### 4a. P1.4 (`ridge` / `strength_only`) — exactly reproducible, its record is this vintage

| | recorded (misaligned) | repaired | Δ |
|---|---|---|---|
| ATS hit (n=4,110) | 0.4961 | 0.4961 | **+0.0000** (45.8 % of sides flipped) |
| ATS placebo | 0.4968 | 0.4968 | +0.0000 |
| **O/U hit** (n=4,129) | **0.5229** | **0.5059** | **−0.0170** |

**Blast radius, measured not assumed:** of 88 fields in `ncaaf_p1_4_calibration.json`, the only
metric that moved is `clv_eval.ou_hit_rate`. σ, ρ, k, `calib_80`, PIT, Brier and the whole
early-season validation reproduce **byte-identically** — the repair touches the eval and nothing
else, which is what makes it safe to leave the served artifacts untouched.

### 4b. S1-serve (`ridge` / `strength_pace`, the SERVED config)

Its record is the 2026-08-20 vintage (4,187 closes), which exists in no checkout, so this is not
like-for-like. On the local vintage, repaired: **ATS 0.4993 (n=4,110), O/U 0.5127 (n=4,129)**.

⭐ **Cross-check.** VAL2's `alignment_control.repaired_read` computes the served config's repaired
O/U hit rate by an independent path, and it agrees to four decimals: **0.5127, n=4,129**. VAL1's own
primary read reproduces the same figure a third time. Three modules, three code paths, one number.

### 4c. VAL1 — see §5.

### 4d. VAL2 re-ran and reproduced EXACTLY — two things that buys

Re-running `ncaaf_val2_mu_total_offset` on the repaired tree reproduces its JSON **field for field**
(1,168 fields; the only difference is `run_at`). That is a control, not a formality:

1. it confirms VAL2's claim to be **immune by construction** — it joins on `game_id` and reads each
   row's own `mu_total`, taking no positional index into a draw array, so repairing the two eval
   paths cannot move it. A study that claimed immunity and then moved would have been the finding;
2. it confirms the **`ensure_pace_composites` move is behaviour-preserving**. That helper shipped in
   VAL2 and VAL1's repair needed the same behaviour, so rather than keep two copies of "derive it if
   absent" around one shared rule (the one-logical-thing-many-owners class, INC-30/36/38) it now
   lives beside `assemble_cache` — which owns the assemble-time derivation — and VAL2 delegates. It
   is a no-op on any post-S1-serve cache, so a re-assembled cache behaves identically.

## 5. VAL1's verdict, re-read against the repaired figures

| cell | recorded | repaired | Δ | < breakeven 0.5238? |
|---|---|---|---|---|
| ATS pooled | 0.5083 | 0.4993 | −0.0090 | ✅ |
| **ATS wk1-3** | 0.4936 | **0.5193** | **+0.0257** | ✅ |
| ATS wk4-6 | 0.5228 | 0.4928 | −0.0300 | ✅ |
| ATS wk7+ | 0.5076 | 0.4959 | −0.0116 | ✅ |
| O/U pooled | 0.5137 | 0.5127 | −0.0009 | ✅ |
| O/U wk1-3 | 0.4950 | 0.4986 | +0.0035 | ✅ |
| O/U wk4-6 | 0.5291 | 0.5219 | −0.0071 | ✅ |
| O/U wk7+ | 0.5137 | 0.5135 | −0.0002 | ✅ |

**✅ `ALL_BUCKETS_NULL` SURVIVES — and is now EARNED.** 0 of 6 cells clear the pre-registered
criterion; every cell sits below breakeven. The point that matters: *a misaligned eval cannot earn a
null, it is guaranteed to produce one.* The recorded null was guaranteed; this one is measured.

**⛔ But two secondary claims in VAL1's record DO NOT survive, and one of them is its headline
sentence.**

1. **"week 1–3 is the WORST of the three buckets in BOTH markets" is REFUTED.** Repaired, wk1-3 is
   the **best** ATS bucket (0.5193, vs 0.4928 / 0.4959) and the worst O/U bucket (0.4986).
2. **"the founding premise is directionally CONTRADICTED" downgrades to UNSUPPORTED.** No cell
   clears and none comes close to significance (ATS wk1-3 p = 0.609 against a BH cutoff of 0.0167),
   so there is still **no early-season edge**. But the ATS point estimate now runs *with* the
   "early season is softest" premise rather than against it, so the stronger claim — that the
   estimates run the opposite way — is no longer supportable.

**What survives besides the null:** the non-monotone-ordering argument. Both markets are still
non-monotone across the three buckets (ATS wk1-3 > wk7+ > wk4-6; O/U wk4-6 > wk7+ > wk1-3), which is
the noise signature VAL1 read it as.

**The `side_tilt` table — the one VAL2 called an artifact — reverses**, as predicted:

| bucket | model→over recorded | repaired | model→home recorded | repaired |
|---|---|---|---|---|
| wk1-3 | 0.5745 | **0.6083** | 0.4165 | 0.4349 |
| wk4-6 | **0.6180** | 0.5765 | 0.5084 | 0.4892 |
| wk7+ | 0.5771 | **0.6146** | 0.5126 | 0.4630 |

Over-tilt ordering: recorded `wk4-6 > wk7+ > wk1-3` → repaired **`wk7+ > wk1-3 > wk4-6`**. Pooled
over-tilt **0.5850 → 0.6057** — and VAL2 independently measured `μ > close` on **0.608** of games,
which the misaligned 58.5 % had understated. `over_actually_hit` barely moves (0.4638 → 0.4630 at
wk1-3), exactly as it should: the repair moves OUR side, never the realised outcome.

**⛔ A third claim flips, and it is the one VAL1's roadmap entry stars: "the `wk1-3` null is
DECISIVE, not underpowered".** That rested on the family-adjusted one-sided upper bounds lying
BELOW the pre-registered meaningful effect (`BREAKEVEN + VIG_WIDTH` = 0.5476), i.e. a
decision-changing early-season edge being inconsistent with the data. Repaired:

| cell | upper bound recorded | repaired | < 0.5476 ⇒ decisive? |
|---|---|---|---|
| **ATS wk1-3** | 0.5344 | **0.5601** | ✅ → **⛔ NO — no longer excluded** |
| O/U wk1-3 | 0.5358 | 0.5394 | ✅ → ✅ still decisive |

So the null is decisive on **O/U only**. On ATS `wk1-3` the interval no longer excludes an edge that
would matter — which is exactly what the null-state flip to `POWER_LIMITED` says independently. The
roadmap's companion advice ("⛔ Do NOT card 're-test with more seasons'") was derived from the
decisive reading and is therefore half-invalidated: it still holds for O/U, not for ATS.

⭐ **The one thing that gets STRONGER:** VAL1's "one actionable lead" — the served total mean running
high in the cold-start weeks — survives and sharpens. The model takes the over on **60.8 %** of
`wk1-3` picks (recorded: 57.4 %) in the one bucket where over hit only 0.463, and VAL2 independently
measured `μ > close` on 60.8 % of games. That lead is the input VAL3 actually needs, and the repair
did not weaken it.

**3 of 6 null-state classifications change** (ATS wk1-3 `MEASURED_IMMATERIAL`→`POWER_LIMITED`;
ATS wk4-6 `POWER_LIMITED`→`MEASURED_IMMATERIAL`; O/U wk4-6 `DSR_UNREACHABLE`→`POWER_LIMITED`).

### VAL1's §2a reproduction pin, re-anchored

The pin's targets (`ats_n` 4114, `ou_hit` 0.513 …) were the numbers **the defect made**. Pinning a
repaired child to a defective parent is not a reproduction check, so they now come from S1-serve's
repaired re-run, and the pin records which parent run and which cache vintage they came from. **The
clause is unchanged** — strict equality on the population, `tol = 0.010` on every rate — and it is
⛔ never derived from VAL1's own output, which would make the pin restate the thing it checks.

⚠️ The targets are vintage-bound and are *supposed* to be: after a re-assemble this pin HALTs,
correctly. The remedy is to re-run the parent (S1-serve) and re-anchor from **its** output. That
sequencing is in the handoff.

## 6. Guards

`betting_ml/tests/test_ncaaf_clv_row_alignment.py` — 9 tests, **RED-proven 6/6** by
`models/ncaaf_clv_repair_red_proof.py` (which asserts each mutation is unique and actually lands
before trusting a verdict).

- the **numerical** guard drives the REAL `_clv_eval` over draws whose value names their row, where
  repaired and broken give 1.0 and 0.0 — no tolerance, no near-50 % ambiguity to hide in — plus a
  two-sided companion proving the fixture can fail;
- `np.flatnonzero` must precede the reset (order *is* the defect);
- the row-count invariant must be the condition of a **reachable** HALT — read off the AST, because
  the first cut asserted the substring and `if False and len(merged) != len(oos)` passed it. The RED
  proof caught that; it is the "a break that lands but does not move the asserted predicate" class;
- all source guards read `ast.unparse` output, **comments stripped** — the repair's own comments
  quote the defect verbatim, so a text scan would match the prose explaining the fix.

VAL2's tripwire is discharged and replaced by a weak anti-regression check in its own suite, so
VAL2's record stays coherent about its §2. The substantive guards live in the file above.

Also fixed in passing: VAL1's pin test hardcoded the pre-repair rates and **still passed** after the
re-anchor — by 0.0003 of the tolerance. It now derives its fixture from `PIN`, so it tests the
function rather than restating a constant that silently rots.

## 7. Scope

- **Not a serving or betting defect.** Nothing bets on it (`best_alpha = 0`) and no serving path
  reads `_clv_eval`; `game_prediction_snapshot` and the served artifacts never call it. The served
  dispersion + mean artifacts were **not** rewritten — `--calib-out` was added so an eval-only
  re-run cannot touch them (the hazard this file already warned about).
- **The levels here are the 2026-07-22 vintage.** The repair is a property of the source code and
  reproduces on any vintage; the *levels* do not. §8 of `ncaaf_val2_mu_total_offset.md` documents why
  VAL1's 2026-08-20 cache is not locally reproducible.
- **NCAAF-VAL3 is unblocked** — it touches this eval path, and would have inherited the defect.

## Files

- `models/bakeoff_ncaaf_game.py` — `_clv_eval` repaired; `ensure_pace_composites` now owned here
  (VAL2 delegates); `--calib-out` added.
- `models/ncaaf_val1_clv_week_strat.py` — `score_config` repaired; `PIN` re-anchored.
- `models/ncaaf_clv_repair_red_proof.py` — 6 deliberate breaks, **6/6 RED**.
- `betting_ml/tests/test_ncaaf_clv_row_alignment.py` — 9 guards.
- `ablation_results/ncaaf_val1_clv_week_strat.json` — regenerated on the repaired path.
