# E7.13 — PECOTA-style prospect → historical-MLB COMPS

**Status (2026-08-01):** Phase 1 **SHIPPED** (comps on the board). Phase 2 **RUN**. The comp term
**IS WIRED INTO THE BOARD'S RANKING** at operator direction, on the strength of a separate
ORDERING study (§6) — the CRPS study alone did not license that and is recorded as
DISPLAY-ONLY / BLEND-ELIGIBLE-NOT-WIRED for the *projection*. `best_alpha = 0`.

| | |
|---|---|
| Engine | `betting_ml/scripts/prospect_board/prospect_comps.py` (pure, fast-gate tested) |
| Board runner | `betting_ml/scripts/prospect_board/build_prospect_comps.py` |
| Validation | `comp_validation.py` + `run_e7_13_comp_validation.py` |
| Artifacts | `ablation_results/e7_13_artifacts/` |
| Tests | `test_prospect_comps.py` (66) + `test_comp_validation.py` (31) — all fast-gate |

---

## 1. What shipped (Phase 1)

For each of the **1,451** prospects on the 2026 board, the 25 most similar HISTORICAL prospects and
what they actually did:

> **#5 Trey Yesavage** (SP, 21.7, FV 60) — *Daniel Espino (0.02), Deivi García (0.02), Forrest
> Whitley (0.02)*
> 5 of 25 comps never reached MLB. 8 fringe; 7 regular; 5 impact. 3-yr dynasty pts p05–p90
> 0.0–1181.0 (median 244.0). THIN comp set — band widened, read as a range not a projection.

**The comp pool is E7.8's cohort** — one row per (past board, prospect) with the realized 3-season
dynasty-fantasy outcome attached, board seasons 2018–2022, **non-debut share 0.609 (batters) /
0.615 (pitchers)**. The busts are in the pool by construction; that is the whole design.

Coverage across the board: **504 strong / 582 fair / 280 thin / 85 no-comp**. 238 rows fall back to
a labelled grade-and-age match (no full-season minor-league record yet — DSL/complex/just-drafted),
always forced to `thin` and flagged `comp_basis = scouting_only`.

**The bust gradient is the product.** Comp-implied bust rate on the 2026 board, by FV:

| FV | n | comp bust rate | comp median 3-yr pts |
|---|---|---|---|
| <40 | 417 | **0.80** | 0.0 |
| 40–44 | 572 | 0.64 | 5.0 |
| 45–49 | 174 | 0.43 | 87.2 |
| 50–54 | 91 | 0.22 | 228.9 |
| 55–59 | 20 | 0.15 | 282.2 |
| 60+ | 12 | **0.13** | 280.3 |

A farm system is mostly 40-FV players, and the honest thing to tell a drafter is that two thirds of
them historically produced nothing. That row is what the comp column exists to say.

---

## 2. Three defects found and fixed while building it

Each produced output that looked **better** than the honest version, which is why each is now
pinned by a test rather than a comment.

### 2.1 🚨 The retained board's `level` is a near-perfect one-sided outcome leak

FanGraphs serves the *retained* past board, and its `level` column is the player's **CURRENT**
level. Measured on the live 2018–2022 cohort:

```
level = 'MLB'             → 2,035 debuts, 1,258 non-debuts
level ∈ {A, A+, AA, AAA}  → 1,908 rows, of which exactly ONE debuted
```

A minor-league `level` on a retained board **tells you with near-certainty that the player busted.**
An engine using it would validate beautifully and be worthless in production, where no such column
exists. It is now in `LEAKED_COLUMNS`; `assert_no_leaked_features` raises; the leakage-safe
substitute is `top_level_pre_board`, derived from game logs strictly before the board date.

`fv` was checked for the same signature and does **not** show it (AUC 0.701 vs the contaminated
`level`'s 0.800 with the one-sided structure above) — it is kept, the E7.8 retained-board caveat
travels with it, and Phase 2 carries a matched `no_fv` foil so the question is measured.

### 2.2 🚨 A total-weight coverage floor is satisfied by the FV grade alone → distance exactly 0.000

FV carries 0.70 of the pitcher feature weight (E7.8's verdict), so a 0.50 **total**-weight coverage
floor passes on FV by itself. Both players' remaining features being missing, Gower's renormalization
then scores them at **distance exactly 0.000** — a perfect comp — and they sort to the TOP of the
list. **4,432 such pairs in the first 50 query rows** of the 2,648-row pitcher pool, e.g.

> Robert Stock (26, Triple-A, 9 years pro) ≡ Brailyn Marquez (19, no full-season record) — shared 40 FV, distance 0.000

Cured by a second, load-bearing floor: `MIN_COMPONENT_COVERAGE` on the **performance block**
specifically. A comp is a claim about a performance profile; without it, it is an FV bucket wearing
a player's name.

### 2.3 🚨 The pool is one row per (board season, player) → one career could carry 7 of 25 votes

A prospect who sat on the board five years contributes five near-identical rows, so if one is a
neighbour they usually all are. Before the fix a 15-comp set repeated the same **person 1.7 times on
average and up to 7 times** — one man's single career carrying 47% of the outcome distribution *and*
47% of the bust rate. The visible symptom (`Bo Bichette (0.04), Gleyber Torres (0.05), Bo Bichette
(0.05)`) was the tip of a distribution that had stopped being an average over k careers.
`_dedupe_by_person` keeps each person's closest board season. Post-fix duplicate count: **0**.

---

## 3. Phase 2 — does the comp distribution earn a place in the projection?

**Target** — dynasty fantasy points over the 3 seasons after the board, **0 for a prospect who never
reached MLB (47% of the pool)**.
**Primary metric — CRPS**, not MAE: on a target with a 47% zero atom MAE is minimised by pessimism
(NF-D11), and `test_comp_validation.py::test_the_nihilist_loses_which_is_why_this_is_not_mae`
demonstrates the inversion on this cohort and proves CRPS does not share it.
**Constraint** — randomized-PIT max decile deviation ≤ 0.05. Coverage is reported as a **floor**,
never a target (E2.1-r).
**Incumbent** — `fv_bucket`: the empirical outcome distribution of same-grade, same-position
historical prospects. That is what the board already knows with no similarity engine at all.

13 pre-registered arms, 4 forward-chained folds (2019–2022), paired at the row level, clustered on
the person.

### 3.1 Results

| | batters | pitchers |
|---|---|---|
| best contender | `comp_gower_k25` | `comp_gower_k25` |
| CRPS vs incumbent | **−8.63** (p < 0.0001) | **−3.25** (p = 0.0010) |
| PBO (contender set) | 0.00 | 0.00 |
| flip distribution | k25 5/6, k15 1/6 | k25 5/6, blend 1/6 |
| DSR (contender set) | **1.000** | **0.945** ✗ (gate 0.95) |
| PIT max decile dev | 0.026 ✅ | 0.035 ✅ |
| p10–p90 coverage | 0.849 ✅ (floor 0.80) | 0.847 ✅ |
| **verdict** | **BLEND-ELIGIBLE-NOT-WIRED** | **DISPLAY-ONLY** |

**All four two-sided anchors passed on both sides**: the peeking oracle is the floor (nothing beat
it), `all_zero` and `marginal` both lost, and the matched random-neighbour placebo lost to the
engine by 17.9 / 15.3 CRPS. The metric is not inverted.

### 3.2 ⭐ The position asymmetry reproduces E7.8's verdict independently

E7.8 found that FV **substitutes** for our read on hitters and **complements** it on pitchers. This
harness, on a different target with a different estimator, lands in the same place:

* **batters** — the comp read beats the scouts' grade bucket outright (−8.6 CRPS, every gate clear);
* **pitchers** — at k=15 the comp read is a statistical **tie** with the grade bucket (−1.27,
  p = 0.28) and only the wider k=25 neighbourhood separates them (−3.25), then misses DSR at 0.945.

That two independent studies recover the same asymmetry is the strongest corroboration in this
story. It also means any future blend must respect it rather than applying one weight to both.

### 3.3 Matched-foil attribution (ΔCRPS, negative = the arm is better)

| channel | batters | pitchers |
|---|---|---|
| FV in the distance (`vs no_fv`) | −4.77 *** | −5.06 *** |
| structural block (`vs components_only`) | −8.73 *** | −10.66 *** |
| **similarity itself** (`vs random neighbours`) | **−17.89** *** | **−15.26** *** |
| equal-weight vs similarity kernel | −3.76 *** | −7.10 *** |

The similarity channel is the largest single effect on both sides: the neighbourhood is doing real
work, not just k-NN estimation. The component block **alone** is worse than random neighbours on
both sides — it narrows the distribution without informing it, which is exactly why the scouting
grade and the age/level/pedigree terms are in the distance.

### 3.4 A finding that changed what shipped

The PECOTA-intuitive choice is to weight a comp by how similar it is. Measured, the tricube
similarity kernel **over-sharpens the predictive**: batters k=15, CRPS 69.03 → **65.27** on equal
weights, randomized-PIT deviation 0.0767 (**failing** the pre-registered 0.05 constraint) →
**0.0426**, coverage 0.764 → **0.831**. Pitchers agree (106.98 → 99.88; 0.0653 → 0.0409; 0.763 →
0.834). The shipped default is now **equal weight**, and because the named comps are the three
closest either way, this changed the band and not a single name on the board. Same reasoning for
**k = 25** over k = 15: it won CRPS on both types and took 5 of 6 CSCV in-sample halves on each,
and the three closest of the 25 nearest *are* the three closest of the 15 nearest.

---

## 4. 🚨 The fold ceiling — read before quoting any absolute number

Production comps the 2026 board against 2018–2022, every outcome window closed by 2025.
`matured_pool` enforces that and a test pins it. **The shipped path is strictly leakage-clean.**

The **backtest** cannot be. With a 3-season horizon and a 5-season archive, a strictly-matured
backtest admits **exactly one fold** (query 2022 ← pool {2018}); every earlier query season has an
empty matured pool. One fold cannot compute PBO and cannot deflate. So the primary run relaxes the
pool to *any strictly earlier board season* — 4 folds — which grants historical queries hindsight
their boards did not have.

Two things bound the damage, and both are load-bearing:

1. the relaxation exists **only inside the backtest**; the production path is clean and guarded;
2. **every arm reads the identical pool**, so the hindsight accrues equally to the incumbent, the
   degenerates and the placebo — the HEAD-TO-HEAD (which is the question the story asks) stays fair
   even though the LEVELS are optimistic.

⇒ **quote the deltas, never the absolute CRPS as "the comp engine's accuracy".**

🔁 **Re-open mechanically.** Each board season whose 3-year window closes adds one strictly-matured
fold: **2 folds in 2027, 4 in 2029.** `fold_plan(..., strict=True)` is the trigger and
`test_comp_validation.py::test_strict_maturity_admits_exactly_one_fold_at_this_archive_depth`
fails the moment the archive deepens. This is the E7.12-S6 shape: a ceiling recorded is a real
deliverable, and an unpowered test reported as a null is worse than not running it.

---

## 5. Verdict

**The comp DISPLAY ships**, and every row carries its k, its distances, its coverage flag and its
bust count. **The comp term also feeds the board's RANKING** (§6) — measured on the ordinal
statistic that actually governs a board, positive in 10/10 folds including the zero-overlap one,
and reversible with `--no-comp-ranking`.

The verdicts below are about the **PROJECTION**, which is a separate consumer and is unchanged.

**The batter comp term is BLEND-ELIGIBLE but deliberately NOT WIRED.** It cleared every
pre-registered gate — but it cleared them on a backtest that cannot be made strictly leakage-clean
at this archive depth. Per the NF-D15 (g″) discipline, a real-but-not-cleanly-verifiable effect
earns a **scheduled re-validation, not a ship**. E8.1 may wire it after the 2027 re-run, and if it
does, it must respect the §3.2 position asymmetry rather than applying one weight to both sides.

**The pitcher comp term is DISPLAY-ONLY on its own merits** — DSR 0.945 against a 0.95 gate at 4
folds is *underpowered, not absent* (the k=25 arm is a real −3.25 CRPS at p = 0.0010), and it is
re-runnable on the same 2027 trigger.

---

## 6. The ORDERING study — the comp term in the board's ranking (operator-directed, 2026-08-01)

The operator asked for comps to feed the rankings. Reviewing why they weren't, the honest answer was
that **§3 measured the wrong statistic for that question**. CRPS grades a predictive DISTRIBUTION; a
draft board is purely ORDINAL. An arm can win CRPS on calibration while ordering no better, because
CRPS rewards the width of the band and a ranking cannot see the band at all. So the ordinal
statistic was measured directly: **Spearman rank-IC against realized dynasty value**, same folds.

### 6.1 The incumbent is not what §3 assumed

`board_rank` is **not** sorted by `blend_score`. `board_assembly.assemble_board` sorts
lexicographically on **`fv` → `model_score` → `blend_score`**, and because FV sits on a coarse
5-point grid, most of the board ties on the first key and **the tiebreak does the ordering work.**
Two consequences decided the implementation: a comp term added to `blend_score` alone would barely
move the board (third key), so it enters **`model_score`**; and the FV-first *shape* is kept.

### 6.2 ⚠️ The relaxed folds would have given the wrong answer, and a direct test caught it

§4's "every arm shares the hindsight, so the head-to-head is fair" argument **does not hold here** —
`board_proxy` and `fv_only` never read the comp pool at all, so only the comp arms are exposed to
the outcome-window overlap. That had to be ruled out directly, on the single **strictly-matured**
fold (query 2022 ← pool 2018; windows 2018–21 vs 2022–25, **zero overlap**):

| arm | batters relaxed | batters **matured** | pitchers relaxed | pitchers **matured** |
|---|---|---|---|---|
| `comp_only` | **0.566** (best) | 0.5205 | 0.399 | **0.2377** |
| `board_plus_comp_w30` | 0.530 | **0.5405** | 0.408 | **0.3618** |
| `board_proxy` (incumbent) | 0.473 | 0.4983 | 0.377 | 0.3340 |

**On the relaxed folds `comp_only` won outright and would have said "replace the board's formula
with comps". On the zero-overlap fold that collapsed** — below the blends on batters, and below the
incumbent outright on pitchers. **The replacement was an era artifact; the blend is not.**

### 6.3 What was wired

ΔIC of `lex(fv, model+comp)` vs the true incumbent `lex(fv, model_score, blend_score)`:

| fold | batters | pitchers |
|---|---|---|
| **matured, zero-overlap** | **+0.0101** | **+0.0192** |
| relaxed 2019 | +0.0014 | +0.0328 |
| relaxed 2020 | +0.0115 | +0.0055 |
| relaxed 2021 | +0.0169 | +0.0235 |
| relaxed 2022 | +0.0192 | +0.0192 |

**Positive in 10 of 10 fold×type combinations, never negative**, including the zero-overlap fold on
both types. Small but perfectly consistent — and the conservative variant: re-sorting on
`blend_score + comp` instead scored higher on batters (+0.042) but went **negative on a pitcher fold
(−0.036)**, and plain `blend_score` is measurably *worse* than the FV-first sort almost everywhere,
which independently validates E8.0's lexicographic design.

`prospect_comps.attach_comp_ranking` mixes the comp percentile into `model_score` at
**`COMP_RANK_WEIGHT = 0.30`** (the clean-fold winner on both types), re-sorts on E8.0's own keys,
and preserves `model_score_no_comps` / `blend_score_no_comps` / `board_rank_no_comps` plus
`comp_rank_delta`. A row without comps keeps its original score and is never penalised.

**Effect on the 2026 board:** 1,392 of 1,451 rows move, median **24 places**, max +176 / −122. The
top of the board barely moves (top 15 shift by ≤1) because FV still leads the sort — the movement
concentrates in the 40-FV mass, which is where a board has the least information and where the comp
read has the most to add. Biggest fallers carry comp bust rates of 0.72–1.00.

⚠️ **Stated deviation:** the historical cohort carries the raw MiLB component line but not E7.3's
*translated* line, so the study's `mle_score` is a labelled **proxy** built from raw components under
the same weights and directions. It preserves the ordering content of the component block but is not
byte-identical to the live board's `mle_score`, so a small residual mis-attribution between the comp
term and the MLE term is possible. Removing it needs an E7.3 back-projection of every historical
board season.

🔧 **Durable follow-up:** the wiring lives in the E7.13 augmenter (which re-exports the shipped
board) rather than in `board_assembly.attach_scores`, so a *fresh* E8.0 board build does not yet
carry it. Folding it into `board_assembly` needs the comp pool available inside that pipeline and is
the right move once E8.1 lands. `--no-comp-ranking` reverts to the untouched E8.0 order.

---

### Known limitations, stated

* Absolute accuracy is not measurable at this archive depth (§4).
* `fv` inherits E7.8's retained-board caveat; the `no_fv` foil shows it carries real signal, but a
  pre-2026 grade may embed a later revision.
* The outcome is dynasty fantasy points over 3 seasons — it under-serves a player whose value is
  speed or defence, the same known gap `board_assembly`'s `speed_flag` exists to surface.
* 85 board rows get no comps at all (no minor-league record and no gradeable pool match). They say
  so rather than showing a fabricated one.
