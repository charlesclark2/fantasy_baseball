# NCAAF-P2.1 S1-serve — deploying the certified `pace` effect (with S1b folded in)

**Status (2026-08-17): ✅ CODE COMPLETE, runtime gate PASSED on the laptop.** The served artifacts
are built and committed; the board publish to the research lakehouse is the operator's post-merge
step. `best_alpha = 0` throughout — this is a calibration ship, not an edge claim.

Prior art: [`ncaaf_p2_1_s1_readout.md`](./ncaaf_p2_1_s1_readout.md) §4 (which specified this work),
[`ncaaf_p2_1_s1b_registration.md`](./ncaaf_p2_1_s1b_registration.md) (the served representation),
[`ncaaf_p1_5_season_simulation.md`](./ncaaf_p1_5_season_simulation.md) (the re-run gate).

---

## 1. What shipped

| # | S1 read-out §4 asked for | shipped |
|---|---|---|
| 1 | a `strength_pace` contract; pace composites derived at `--assemble`, kept OUT of `full` | `POST_P1_4_CONTRACTS = ("strength_pace",)`; `p2_1_blocks.derive_pace_composites` is now the SINGLE derivation both the P2.1 battery and the P1.4 serving assemble call |
| 2 | a MEAN artifact beside the dispersion (⛔ never σ alone) | `ncaaf_game_mean.py` + `artifacts/ncaaf_game_mean_v2.json` — a diffable coefficient table, written by the same `--stage finalize` that writes σ, and **refused as a pair if the two contracts disagree** |
| 3 | a pace term in the sim's mean map, NULL ⇒ inert, guard-pinned | `season_simulation.PaceAdjustment`; week-1 boards byte-identical (guarded, and measured on the real 2026 board) |
| 4 | re-run P1.5's held-out calibration gate | re-run; **PASSES, and is unchanged by the promotion** (§4) |
| 5 | finalize + publish | finalize RUN (it is a 20 s laptop job, not the multi-minute job the read-out assumed); the `--s3` board publish is the operator's post-merge step (§6) |
| ⭐ | fold in S1b — ship the 2-column composite | `SERVED_PACE_COLS = ("pace_sum", "pace_diff")`, one constant read by both the contract resolver and the mean artifact so the two cannot diverge |

## 2. The one identity everything rests on — a NULL feature is EXACTLY inert

The served learner is `StandardScaler → Ridge` over a TRAIN-MEAN-imputed matrix. Mean-imputation
preserves a column's mean, so the scaler's `mean_` *is* the NaN fill, and

    μ = intercept + Σ_k coef_k · (x_k − scaler_mean_k) / scale_k

contributes **exactly 0.0** — bit for bit, not within a tolerance — for any missing column. Every
week-1 team-week row is the rollup's honest empty row ⇒ 100 % NULL pace ⇒ a pre-season board cannot
move. That is why a mid-August deploy is safe against an 08-29 kickoff, and it is asserted three
ways: on the artifact math, end-to-end through the simulator, and on the real 2026 board.

## 3. The served pace coefficients — and what they say about the mechanism

From `ncaaf_game_mean_v2.json` (ridge α=10, 27 columns, 8,325 rows, ∂μ per second-per-play):

| target | ∂μ/∂`pace_sum` | ∂μ/∂`pace_diff` |
|---|---|---|
| **total** | **−0.5609** | +0.0216 |
| margin | −0.0326 | +0.0764 |

⭐ This independently corroborates S1 §3's attribution *from the served model rather than from the
CRPS ranking*: the effect is the **possessions channel on the TOTAL axis** (a second per play
slower on both sides ⇒ ~0.56 fewer points), and the margin axis carries almost nothing. S1 read
that off a leaderboard delta of +0.0014 inside a tie band; the coefficient table shows the same
thing structurally, at 17× the magnitude on the total.

## 4. The gates

### 4a. P1.4 finalize gate — where the improvement actually shows

Both runs: ridge / `strength_posterior`, 6,024 OOS games, 2018–2025, same folds, same seed.

| | `strength_only` (frozen v1) | `strength_pace` (v2) |
|---|---|---|
| σ_margin · σ_total | 16.09 · 16.75 | 16.08 · **16.64** |
| σ₀_margin · k_margin | 15.61 · 0.573 | 15.61 · 0.572 |
| calib_80 margin / total | 0.800 / 0.802 | 0.800 / 0.799 |
| PIT max-decile-dev, total | 0.0218 → **flat FALSE ❌** | 0.0173 → **flat TRUE ✅** |
| calib floor · PIT-flat | PASS · **FAIL** | PASS · **PASS** |
| ATS / O-U vs close | 0.508 / 0.515 | 0.509 / 0.513 |

⭐ **The headline: the served TOTAL distribution's PIT-flatness gate goes FAIL → PASS.** That is
where a total-axis mean improvement is supposed to land, and it is the strongest single statement
this deploy can make. ⚠️ Stated honestly: PIT flatness is a threshold, so "FAIL → PASS" overstates
a 0.0045 move in the underlying statistic; the direction and the mechanism agree, the *step* is
partly the bar's location. Both ATS and O/U remain under the 0.5238 breakeven — `best_alpha = 0`
is untouched.

⛔ **Reproduction check.** Re-running finalize on `strength_only` with all of this story's code in
place reproduces the frozen P1.4 v1 artifact to every printed digit (σ_margin 16.09, σ_total 16.75,
σ₀ 15.61, k 0.573, ρ 0.056). The frozen record is untouched at RUNTIME, not merely in a unit guard.

### 4b. P1.5 held-out calibration gate — re-run, and unchanged

`--calibrate --n-sims 20000`, seasons 2016–2025, three seeds each, v1 vs v2 under identical code
and data:

| leg | v1 (`strength_only`) | v2 (`strength_pace`) | Δ | seed-to-seed range |
|---|---|---|---|---|
| expected-wins MAE | 1.6393 | 1.6397 | +0.0003 | 0.0010 |
| conference-title Brier | 0.04430 | 0.04430 | 0.00000 | 0.00005 |
| conference-title Brier-skill | 0.0405 | 0.0405 | 0.00000 | 0.0011 |
| national-title Brier-skill | 0.1303 | 0.1304 | +0.00003 | 0.0010 |

**The gate passes and the promotion moves it by nothing** — every delta is an order of magnitude
inside the seed noise. That is the CORRECT result, and worth stating rather than glossing: this
gate is a **pre-season, margin-axis** read, so it is structurally blind to both channels S1-serve
touches (pace is inert at week 1; the σ improvement is on the total, which this board does not
simulate). It is re-run to prove nothing REGRESSED, not to show a gain.

### 4c. Two defects the re-run surfaced (both pre-existing on `dev`, both fixed here)

1. ⭐ **An unplayed season was scored as "nobody won a conference title".** The moment 2026 entered
   the strength mart, `run_calibration` added its 136 conference-eligible teams to the leg with
   label 0 — n 1257 → 1393, base rate 0.0485 → 0.0438, **Brier-skill 0.0513 → 0.0272**. A pure
   artefact, indistinguishable from a real regression, and it would have been read as one. The
   natty leg already had the guard; the conference leg did not. Fixed (`if ... and realized_ccg`),
   with a loud per-season ALERT and the scored-season list recorded on the result.
   ⚠️ Reproduced on **unmodified `dev`** in a control worktree before being called pre-existing.
2. **A `dev`-vs-July data-vintage difference, NOT a model change.** The committed July record shows
   conference Brier-skill 0.0513; today's marts give **0.0398 on unmodified `dev` with the frozen
   v1 artifact**, seasons 2016–2025. The marts DuckDB was rebuilt since. Recorded so the next
   reader does not attribute it to this deploy — the P1.5 record this PR updates carries the new
   number.

### 4d. 🟥 Runtime gate (laptop, real artifacts, real marts)

| check | result |
|---|---|
| pre-season 2026 board, pace ON vs `--no-pace` | **BYTE-IDENTICAL** (138 teams × 15 cols, `DataFrame.equals` True); meta records `acted: false`, 0/138 teams with a tempo |
| in-season 2024 week-8 board carries the term | **YES** — 134/134 teams with a tempo, Δμ_margin on **390/390** simulated games, mean \|Δ\| 0.231 pts, max 0.844 |
| …and it moves the board, by a little | exp-wins changed on 112/134 teams, max \|Δ\| 0.06 wins; P(natty) max \|Δ\| 0.0023 — **small, as predicted**: this board is margin-only and pace lives on the total |
| P1.4 finalize under `strength_only` reproduces v1 | every printed digit |
| P1.5 calibration gate | PASS, unchanged (§4b) |

⚠️ **Scope the byte-identity claim precisely.** It is about the **pace term**: with the served
dispersion held fixed, pace ON and pace OFF give the identical pre-season board. It is NOT a claim
that the committed 2026 board is unchanged — σ₀_margin moved 15.6083 → 15.6097 in the refit, so a
few probabilities shift in the 4th decimal (e.g. Notre Dame P(CFP) 0.313 → 0.312). μ is bit-for-bit
the pre-S1-serve mean map; σ is a new (better-calibrated) fit, and that is the intended change.

## 5. Guards

`betting_ml/tests/test_ncaaf_s1_serve_pace.py` — 36 fast-gate guards (`football` shard; imports no
`pipeline`, no IO). **11 deliberate source breaks were RED-proven**, each asserting the mutation
landed on disk AND that the replaced token was gone (#682/#815):

full-contract filter removed · importance ranking fitted over all columns · `strength_pace` silently
falling back to `strength_only` · served representation narrowed to `pace_sum` · a NULL pace no
longer zeroed in the sim · `simulate_season` dropping the term from the regular-season draw · …from
the neutral CCG/bracket draw · a NULL feature no longer contributing zero to μ · `load_served_pair`
not checking the contracts match · the shared derivation computing the wrong composite · the P2.1
battery re-implementing the derivation instead of delegating.

⭐ **The RED proof earned its keep — it found two real coverage holes in the first cut** and both
are now closed by isolating clauses (NF-D17: an AND-composed wiring needs one fixture per leg):

* "`simulate_season` ignores pace" stayed GREEN, because the board-level control was satisfied by
  the CCG/bracket legs alone — a dead regular-season draw would have passed. Now pinned by a
  standings-level clause and a `_batch_neutral`-level clause separately.
* "the shared derivation is wrong" stayed GREEN, because breaking the SHARED function moves both
  callers together and the equality guard only proves they AGREE. Now paired with a clause that
  pins the arithmetic itself.

### 4e. A third defect, found by the publish itself

The operator's first real board publish (`--season 2026 --s3`) **silently deleted the entire
held-out-calibration section from the tracked P1.5 report** — the story's own gate evidence. Cause:
a board-only run computes no calibration, `write_report` rendered only what THAT invocation
produced, and the report path is fixed. It would have recurred on every board refresh forever,
and the deletion is invisible unless someone diffs the file.

Fixed: the section is now re-rendered from the persisted `ncaaf_p1_5_calibration.json` and
**stamped** `⏳ NOT recomputed by this run — computed <ISO timestamp>`. Staleness is visible on the
page rather than inferable from an absence (NF-FRESH2), and a partial run can no longer destroy a
fuller artifact (NF-W2c-CBS). ⚠️ Note this is the SECOND instance of that class in one story — the
first was the finalize clobbering P1.4's calibration record (§ above). Both were fixed-output-path
writes in a stage a later story reused; neither raised, and neither was visible in any test run.

## 6. Operator step (post-merge)

Everything above is already built and committed. The only remaining action is the board publish:

```bash
# LAPTOP, from the repo root, after the PR merges to dev
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.run_season_simulation --season 2026 --s3
```

To rebuild the served artifacts from scratch instead of taking the committed ones (also LAPTOP,
~30 s total; needs AWS for the CLV join):

```bash
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --assemble
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage finalize \
    --model-class ridge --contract strength_pace --form strength_posterior
```

## 7. Honest framing + scope

* `best_alpha = 0`. A market-blind calibration improvement is product value, not an edge claim; the
  vs-close legs sit at 0.509 ATS / 0.513 O-U against a 0.5238 breakeven.
* **NCAAF still serves no product surface** (no store, no API, no frontend — boards land in the S3
  *research* lakehouse), so there is no changelog entry and no Lambda deploy. When the NCAAF app is
  sequenced mid-season, it inherits a μ that is an artifact rather than an assumption.
* **The season board is margin-only.** The pace term is wired into it because a σ refit under the
  pace contract must not be served against a pace-free μ (E7.9) — not because the futures board is
  where pace pays. Where it pays is the standalone game distribution's TOTAL, which is exactly what
  §4a measures.
* The +0.018 CRPS S1b margin over the S1 primary is an S1 MEASUREMENT re-used as a serving decision,
  not an independently-earned lift; see the S1b registration §1 and §6.
