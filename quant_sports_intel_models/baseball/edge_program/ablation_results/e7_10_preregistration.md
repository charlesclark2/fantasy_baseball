# MLB Edge-E7.10 — PRE-REGISTRATION: is FanGraphs FV an incremental cold-start RATE prior for debuting starters?

**Written BEFORE any arm was scored.** Every number below is either a DESIGN quantity (fold counts, row
counts, coverage) measured by a counts-only probe, or a threshold transplanted from a prior story's
recorded result. Nothing here is reverse-engineered from an E7.10 outcome. `best_alpha = 0`.

---

## 0. The question, and why it is NOT already answered by E7.8

E7.8 graded **FanGraphs FV → 3-year dynasty FANTASY POINTS** and found FV *complements* our own MiLB
performance read **for pitchers** (`pitcher/debut` DSR 0.998, `pitcher/unconditional` DSR 0.998). That is
a different target, a different population and a different decision.

E7.10 asks the betting question: at a starter's **MLB debut**, does the pre-debut FV grade improve the
**RATE prior** (K% / BB% / GB%) that `eb_starter_posteriors` serves — *over the E7.5p MiLB-MLE prior that
is already wired there*? A better-calibrated cold-start rate prior feeds better-calibrated run-diff /
totals for rookie-starter games. **It is a CALIBRATION claim, never an edge claim.**

A positive E7.8 verdict is **evidence to run this study, not evidence for its conclusion.** A null is a
valid and reasonably likely outcome and will be recorded as one.

---

## 1. Population (declared; both variants fixed in advance)

One row per **graduated pitcher at his HIGHEST reached MiLB level** (`mle_prior.highest_level_rows` —
the row the SERVED prior actually uses), with:

* `has_mlb_label` — the E7.3p floor `mlb_pa ≥ 150` TBF (the E7.5 thin-cameo landmine), plus
  `mlb_bip ≥ 50` for GB% (the E7.5p second-order floor). Applied verbatim, not re-derived.
* a **strictly-prior-season FV grade** (see §2).

| | definition | why |
|---|---|---|
| **PRIMARY — `starter`** | pre-debut MiLB **start share ≥ 0.50** (`pit_games_started / pit_games_played`, summed over the pre-debut MiLB record) | leakage-safe and knowable AT CALL-UP, which is when the served prior is applied. It does not condition on anything that happens after the debut. |
| **SENSITIVITY — `all_pitchers`** | every labelled graduated pitcher | more rows; reported beside the primary so a starter-specific finding is distinguishable from a pitcher-wide one |

⚠️ **Stated, not corrected (inherited from E7.3p/E7.5p):** graduated pitchers are self-selected — they
reached the TBF floor. That IS the served population, so the calibration is on the right people, but it
is not a random sample of call-ups.

## 2. The as-of / leakage rule (conservative by construction)

The FV attached to a pitcher is the grade from the **LATEST board season STRICTLY BEFORE his MLB debut
season** (`board_season < debut_cohort`).

Why strictly-prior-SEASON rather than "any snapshot before the debut date": E7.7 records that FanGraphs
serves the **RETAINED** past board rather than a true point-in-time snapshot, and stamps every pre-2026
season `<season>-07-01`. A same-season board therefore may embed a revision made *after* the player
debuted in April. Excluding the debut season removes that hazard entirely at a cost in coverage.

* The looser rule (`as_of_date < debut_date`, allowing the debut-season board) is run as a **declared
  sensitivity** and reported. It is NOT the headline.
* Board → MLBAM routes through `player_xref` (E7.4): board `fg_minor_id` → leaderboard `xMLBAMID`, with
  the numeric-`fg_player_id` graduate leg as the second hop. The board is read ONLY via
  `player_xref.register_board` — ⛔ never `delta_scan` (void-typed `mlbam_id`) and never a
  `read_parquet` glob (tombstone union). Measured resolution 99.7%.

## 3. Folds, and the design quantities that fix them (probe, 2026-08-03 — counts only)

Fold unit = **MLB debut cohort**, leave-one-cohort-out, purged (a pitcher has exactly one debut cohort,
so no pitcher straddles the boundary).

Board seasons: **2018–2026** (1 snapshot/season pre-2026). So a strictly-prior grade first exists for
**debut cohort 2019**. An eval cohort additionally needs ≥1 strictly-prior cohort that itself carries FV
rows (the in-fold FV term must be fittable) ⇒

> **Evaluable folds = debut cohorts 2020 … 2025 = 6.**
> 2026 is EXCLUDED: its 2-season label window has not closed (15 labelled pitchers vs ~80 typical) — the
> E7.8 `default_season_ceiling` discipline, a truncated label is a silently-wrong label.

Labelled graduated pitchers with a strictly-prior FV grade, per cohort (probe):

| debut cohort | labelled pitchers | starter-ish | with prior FV | **starter + prior FV** |
|---|---|---|---|---|
| 2019 | 70 | 50 | 34 | 34 |
| 2020 | 68 | 52 | 39 | 36 |
| 2021 | 91 | 56 | 60 | 44 |
| 2022 | 79 | 53 | 38 | 32 |
| 2023 | 83 | 57 | 60 | 47 |
| 2024 | 84 | 52 | 59 | 45 |
| 2025 | 66 | 47 | 42 | 33 |

⇒ ~**237 scored rows over 6 folds** on the primary population (2019 trains, never evaluates).

> 📌 **AMENDMENT, 2026-08-03 — recorded BEFORE any arm was scored** (the assembler had been written and
> run for its coverage counts; no score, leaderboard or contrast had been computed).
>
> The first cut of `build_fv_starter_cohort` applied E7.8's `default_season_ceiling` rule — drop any
> cohort whose FULL 2-season label window is still open — which yields ceiling 2024 and **5** eval
> folds, not the 6 stated above. **The rule does not transfer, and this table is the authority.**
> E7.8's target was ACCUMULATED fantasy points over a fixed horizon, where truncation labels a good
> prospect a bust — a BIASED label. E7.10's target is a **RATE**, where a partial window is NOISIER but
> not biased; and keeping the 2025 cohort is what aligns this population with **E7.5p's own ablation**,
> the incumbent E7.10 must be compared against on like-for-like rows. So the ceiling is the **last
> COMPLETE MLB season** (2025). The strict 2-season-closed variant is added as a **declared
> sensitivity** (`--strict-label-window`) and reported.
>
> Same amendment fixes the **coverage-gate denominator**: THE BOARD starts in 2018, so debut cohorts
> ≤2018 have 0% strictly-prior coverage BY CONSTRUCTION and say nothing about FanGraphs' reach. Pooling
> them drags the headline from ~74% to ~47% — a coverage number for a quietly different population than
> the one it names (NF1.8). The report leads with coverage over **gradable** cohorts (debut ≥ 2019) and
> labels the pooled figure as such. Both are emitted.

## 4. What the design CAN and CANNOT detect — computed up front (MH2)

| gate | at n_folds = 6 | reachable? |
|---|---|---|
| PBO / CSCV | needs ≥4 folds | ✅ **evaluable** (`cv_power.pbo_evaluable(6, ·)`) |
| DSR | needs ≥3 folds; ceiling `dsr_ceiling(6)` | ✅ computable — the attainable ceiling is reported in the result, and a DSR shortfall will be classified `POWER_LIMITED` vs `DSR_UNREACHABLE` by `cv_power.classify_null`, never merged |
| fold consistency | `fold_consistency_clause(6, α=0.20)` ⇒ **5 of 6 wins required** (the legacy ≥60% bar would demand only 4 and fires 34.4% of the time on a TRUE ZERO) | ✅ attainable (`2⁻⁶ = 0.0156 ≤ 0.20`) |
| BH-FDR over the 3-metric family | strictest rung `0.10/3 = 0.0333`; one-sided fold-sign floor at 6 folds `2⁻⁶ = 0.0156` | ✅ **certifiable** — the floor sits BELOW the cutoff, so an effect of some size *could* pass (the E7.14 failure mode is avoided by design, not by luck) |

**Pre-registered practically-meaningful effect** (so `TRUSTWORTHY_DEAD` is reachable, and so a null is
not a shrug): **a ≥3% relative improvement in held-out CRPS over the matched foil.** Basis — E7.5p's
recorded gain of the WHOLE MLE prior over the generic prior was CRPS −23.0% (gb_pct), −10.4% (k_pct),
−7.6% (bb_pct). An FV term worth less than roughly a third of the smallest of those cannot move a served
rate enough to change a priced total. The threshold is set from a PRIOR story's recorded result, before
this run — not from this run's spread.

The realized MDE in per-fold-SD units is computed at run time (`cv_power.mde_in_sd_units`) and compared
against this figure; the verdict is emitted by `cv_power.classify_null`, whose 8 states are reported
verbatim rather than collapsed to "trustworthy/underpowered".

## 5. The arms — a COHERENT, DECLARED family (MH2 (a): you pre-register a family, you do not discover one)

The family is **"the pre-debut SCOUTING GRADE as an addition to the served MLE rate prior"**. Every arm
below is in the DSR trial field and counts toward PBO. ⛔ No arm may be dropped after the fact.

### Candidate arms (selectable)

| arm | prediction of the debut-window rate | role |
|---|---|---|
| `L0_mle_served` | the served E7.5p `mle_<m>` **verbatim** (no in-fold fit) | **the SHIPPED foil** — what serving does today |
| `C0_mle_recal` | in-fold OLS `mlb_<m> ~ mle_<m>` | ⭐ **the MATCHED FOIL — the primary comparison** |
| `A1_mle_fv` | in-fold OLS `mlb_<m> ~ mle_<m> + fv` | the mechanism, linear FV |
| `A2_mle_fv_bucket` | in-fold OLS `mlb_<m> ~ mle_<m> + 1{FV bucket}` | FV is an ordinal grade; the E7.8 `#bucket` form |
| `A3_mle_fv_eta_risk` | in-fold OLS `mlb_<m> ~ mle_<m> + fv + eta + 1{risk}` | the grade's full published payload |

⭐ **WHY `C0_mle_recal` IS THE PRIMARY DEFENDER AND `L0_mle_served` IS NOT.** Any `A*` arm also gets a
free in-fold intercept and slope on `mle_<m>`. Scored against `L0`, an FV arm could win on **recalibration
of the MLE alone** and the win would be mis-attributed to the scouting grade. `C0` holds the recalibration
constant and varies only the FV channel — the NF-D10 (g) / NF-D15 (g′) matched-foil discipline, which is
what earns an *attributable* answer either way. **PRIMARY CONTRAST, per metric: `A1_mle_fv − C0_mle_recal`.**
`L0` is reported so "in-fold recalibration alone helps" is visible as its own finding.

### Anchors — declared with what a violation MEANS (evaluated by `h_harness.evaluate_anchors`)

| anchor | kind | must | a violation means |
|---|---|---|---|
| `Z_fv_permuted` | `refute` (defender `A1_mle_fv`) | LOSE | FV **shuffled within the eval cohort** — marginal distribution preserved EXACTLY, per-player pairing destroyed. If it beats the real arm, the "grade carries player-specific information" story is refuted. This is the PLACEBO. |
| `Z_cohort_mean` | `block` | LOSE | the generic prior-cohort mean (what the pre-E7.5p prior collapsed to). A degenerate winning the metric ⇒ the metric is INVERTED (NF-D11). |
| `Z_sigma_sharp` | `block` | LOSE | the best arm's mean with σ/10 — maximally SHARP. Must lose or CRPS is being gamed from the sharp side (NF1.7 (3)). |
| `Z_sigma_wide` | `block` | LOSE | the best arm's mean with 10σ — maximally WIDE. Must lose or the score rewards uselessness (NF1.7 (3)). |
| per-form **peeking floor** | reported gate | each arm ≥ the peeking version of **ITS OWN form** | a single shared ceiling would veto a legitimately-better nested form (NF-D16 (g‴)); `A1` nests `C0`, so `C0`'s ceiling cannot floor `A1`. |

Every anchor carries `must_move`: an anchor that RAN but moved ~0% of rows is **INERT and BLOCKS** — its
"it lost" would be a pass on nothing (NF1.7 (a)). `Z_fv_permuted` is expected to move ~100% of rows;
if it does not, the FV column is degenerate and the whole run is BLOCKED, not read.

## 6. Scoring

* **PRIMARY: held-out CRPS** of a Normal predictive, each arm carrying **its own** in-fold
  self-calibrated σ (the std of its own train-fold residuals). A proper score grades point AND spread
  jointly, so a pessimism/sharpness degenerate cannot win it (NF-D11).
  ⚠️ MAE is explicitly NOT primary. It is reported as a sensitivity, and the degenerate anchors are
  scored every run and their scores PRINTED (NF-D14: do not *reason* about whether a point score
  inverts — keep the degenerate in the field and READ it).
* Reported beside it: NLL, MAE, and interval coverage at ±σ / ±1.645σ. **Coverage is a FLOOR, never a
  target** (E2.1-r / NF1.8) — it gates nothing here and is published only so a sharp-but-miscalibrated
  arm is visible.
* Deflation: `deflation_report` (PBO over the **eligible** set + the flip distribution + Bailey's
  degradation + the CONTENDER spread — NF1.8's four numbers, not PBO alone) and `dsr_report` (DSR over
  the eligible set, with the whole-field figure reported beside it — NF-D14).

## 7. The pre-registered decision rule

Per metric ∈ (`gb_pct`, `k_pct`, `bb_pct`), **ADD the FV term iff ALL of:**

1. `A1_mle_fv` beats `C0_mle_recal` on held-out CRPS **on average**;
2. it wins **≥5 of 6 folds** (the calibrated `fold_consistency_clause`, not the legacy 60% rate);
3. one-sided paired p over the per-fold deltas survives **BH-FDR at q = 0.10** across the 3-metric family;
4. `PBO(eligible) < 0.20` **and** `DSR(eligible) ≥ 0.95`;
5. every anchor in §5 holds (no BLOCK, no refutation of `A1`);
6. the per-form peeking floor holds.

**IF a metric clears** → wire FV as an ADDITIONAL cold-start κ-term in `eb_starter_posteriors`, behind
the EXISTING E7.5p cold-start gate (`n_prior_seasons = 0`), κ-blend only (⛔ never Normal-Normal — the
E7.5 ISO lesson), leakage-safe as-of, with the MLE prior as the fallback wherever FV is absent.

**IF it nulls** → record the null with its `cv_power.classify_null` state and its re-test trigger *in the
unit that grows*; the E7.5p MLE prior stands as the sole cold-start term, unchanged. **The null is
shipped as the finding.** No metric is re-picked on a different score after the fact.

## 8. Coverage gate (reported either way — FV can only help where it exists)

The report states the fraction of debuting starters carrying a strictly-prior FV grade, by cohort and
pooled. Ungraded pitchers fall back to the E7.5p MLE prior — **never a silent drop**. If the wiring
happens, the served SQL must make the FV term NULL-safe so an ungraded pitcher's prior is byte-identical
to today's.

## 9. Known limitations, stated in advance

* **Small-N by construction** — 6 folds, ~40 rows per fold. This design can honestly rule out a LARGE
  effect; it cannot resolve a small one. That is why §4 computes the MDE rather than asserting power.
* **Cohort-out, not strictly real-time** — a model tested on cohort *Y* trains on earlier cohorts whose
  2-season label windows extend into *Y*. Same posture as E7.3p / E7.5p / E7.8 §5; stated, not hidden.
* **Pre-2026 as-of is approximate** (retained board, §2). Mitigated by the strictly-prior-SEASON rule;
  the looser rule is a reported sensitivity only.
* **The board is FanGraphs' GRADED population** — this measures "is the grade informative among the
  graded", not "is the board's coverage complete". §8 is the other half of that sentence.
* **`gb_pct` is a cross-definition map** (MiLB ground-out share → Statcast GB/BIP), inherited from E7.3p.
* **`best_alpha = 0`** — a cold-start calibration prior, never a market bet.
