# NF-C3-REREAD — NF-RECAL1's C3 and NF-D21's interval-floor gate, re-read under the CORRECT served band

_generated 2026-08-08_ · `best_alpha = 0` · a GATE re-read, not a bake-off — no new model, no new arm, no moved floor · data: `nf_c3_reread.json` · harness: `run_nf_c3_reread.py` (15.8s laptop, no Snowflake)

## Verdict

| story | recorded null state | does the recorded null STAND? | corrected state | ships? |
|---|---|---|---|---|
| **NF-RECAL1** (veteran level) | CONSTRAINT_REFUSED | **NO — the refusal was a gate artifact for the two constant-lift arms** | **POWER_LIMITED** (statistical — the surviving refusal is the pre-registered DEFLATION gate, not a constraint) | **NO** — DSR 0.642 < 0.95 (ε-read: 0.796, PBO 0.286 > 0.2); nothing serves |
| **NF-D21** (rookie λ=0.5) | CONSTRAINT_REFUSED | **YES — unchanged; the `served_*` trap never reached this gate** | CONSTRAINT_REFUSED | NO (unchanged; stays CLOSED) |

**One sentence each.** NF-RECAL1: with `coverage_incumbent` measured on the band actually on the wire (0.845-class, not the panel columns' 0.50), the two constant multiplicative lifts clear the corrected — STRICTER — C3 out-of-sample on every fold, the pre-registered machinery replayed end-to-end produces an eligible winner with the genuine level-fix signature, and the only thing still refusing a ship is the deflation gate — a statistical refusal, so the null re-classifies CONSTRAINT_REFUSED → POWER_LIMITED and the level hypothesis is **alive, not constraint-dead**. NF-D21: its gate reads the ROOKIE band refit through the rookie model path — never a `served_*` panel column — the recorded sweep reproduces row-for-row, the corrected C3 structure reduces to the bare 0.80 floor it was already refused under (λ=0 RB coverage 0.8041 ≥ 0.80), and λ=0.5 RB is still 0.7905 = 2 covered rows short: **truly closed**.

## 0. STEP 0 — proof of WHICH band is being gated on (the whole point)

The incumbent band here is refit per walk-forward fold through the served code path
(`season_projection.fit_veteran_band_model`, `knn_norm k300`) and must reproduce the recorded
figures before any gate is read. All three reproduce; the run RAISES otherwise.

| reproduction | this run | recorded | Δ |
|---|---|---|---|
| NF1.9 universe IS80 (2013–2025, 8398 rows) | **160.888** | 160.888 | **0.0000%** |
| NF1.9-R served-band tier coverage 2019–2025 | **0.8452** | 0.8452 | 0 |
| panel `served_p10/p90` tier coverage 2019–2025 (the pre-NF1.9 normal band — the trap) | **0.5046** | 0.5046 | 0 |

Incumbent fallback fraction 0.0000 — no row silently reverted to the panel band. The as-recorded
NF-RECAL1 harness was then reproduced exactly (11 arms; incumbent CRPS 53.0400; the recorded
out-of-sample constraint table matched arm-for-arm, fold-for-fold) before anything was corrected —
so the corrected read is a re-read of THAT record, not of a re-derivation.

⭐ **Why a STRICTER bar passes MORE arms** (pre-empting the obvious objection): the mis-specification
was in BOTH terms of `coverage_λ ≥ min(floor, coverage_incumbent)`. The recorded run measured the
arm's shifted band AND the incumbent on the panel's pre-NF1.9 normal band (~0.50-class), so arms were
refused for degrading a 0.50 that was never on the wire. Corrected, the bar RISES to the full 0.80
floor at most position-folds — and the arm's shifted SERVED band covers 0.83–0.97 there, clearing it
with real row slack (per-fold slack table in the JSON; typically +1 to +10 rows, not ε-passes).

## 1. READ 1 — the RECORDED arms, re-gated on the corrected C3

Recorded λ paths reproduced from the as-recorded harness, applied to the band on the wire; C1/C2
unchanged (band-independent). CRPS below is the CORRECTED metric (split-normal on the served band).

| arm | recorded λ path | corrected C3 every fold | holds out (C1∧C2∧C3) | failing folds → cause | CRPS (served band) |
|---|---|---|---|---|---|
| incumbent (NULL) | — | ✓ | ✓ | — | 48.8081 |
| **global_const · unconstrained** | 0,1,1,1,1,1,1 | **✓** | **✓ CLEARS** | — (was refused on 6/7 folds) | 48.9544 (loses to NULL) |
| **pos_const · unconstrained** | 0,1,1,1,1,1,1 | **✓** | **✓ CLEARS** | — (was refused on 6/7 folds) | **48.6223 (beats NULL)** |
| pos_offset · unconstrained | 0,1,1,1,1,1,1 | ✗ | ✗ | 2020/22/23/25 → genuine under-coverage of the shifted band | 48.2652 (best CRPS, C3-refused) |
| pos_affine · unconstrained | 0,1,1,1,1,1,1 | ✓ | ✗ | 2021 → **C1 ordering** (negative fitted slope — NF-D16 (2)'s conditional monotonicity, live and band-independent) | 48.9830 |
| avail_cond · unconstrained | 0,1,1,0.75,0.75,1,0.75 | ✗ | ✗ | 6 folds → under-coverage | 49.0723 |
| all 5 `· infold` arms | 0 everywhere | (ε-artifact, §3) | — | identical to the incumbent | 48.8081 |

ε-sensitivity: the same two arms clear (`arms_..._eps` in the JSON). So READ 1's headline does not
rest on the rounding artifact.

**The recorded verdict's central clause — "every recalibrating arm BEAT the incumbent and was removed
by a DETERMINISTIC constraint" — does not survive the corrected band on either half:** the two
constant lifts were not legitimately removed (gate artifact), and on the corrected metric the λ=1
lifts are OVER-corrections (`global_const` at λ=1 actually loses to the incumbent; the in-fold
optimum sits near λ≈0.5, §2).

## 2. READ 2 — the pre-registered machinery replayed end-to-end on the corrected band (disclosure; the B3 escalation input)

λ rules re-derived from corrected in-fold scores and corrected admissibility; selection + deflation
under the corrected metric. ⛔ Nothing here ships anything — the pre-registered deflation gate binds.

- **Eligible set:** {NULL, `global_const · infold`, `global_const · unconstrained`} — non-degenerate
  for the first time (the recorded run's eligible set was the NULL alone).
- **Winner:** `global_const · infold` — the CONSTRAINED, shippable-by-design arm — λ path
  0, 0.75, 0.5, 0.5, 0.5, 0.5, 0.5 · CRPS **48.7002 vs 48.8081** (fold wins 3/7, per-fold deltas
  0.00/−0.02/−0.07/+0.14/+0.34/+0.37/−0.00) · pooled bias **−12.59 → −5.44** · universe bias +3.70.
- **Attribution signature (NF-D15 (g′)): `level_fix`** — accuracy improved AND pooled bias moved
  toward zero. The recorded run's `no_lift` verdict was itself a product of the collapsed field.
- **The pre-registered pooled gate:** every constraint clause PASSES (ordering ✓, placement ✓,
  coverage floors ✓), PBO(eligible) 0.1429 ✓, p 0.0822 ≤ 0.10 ✓ — **DSR 0.6423 < 0.95 ✗ ⇒ SHIP =
  FALSE.** (ε-read: winner `pos_const · infold` λ≈0.5, CRPS 48.529, p 0.039 ✓, PBO 0.2857 ✗,
  DSR 0.7962 ✗ ⇒ SHIP = FALSE.) The DSR ceiling at 7 folds is 0.9997, so the gate is reachable at
  this fold count in principle — the refusal is evidence-strength, not design impossibility.
- **Classification (`cv_power.classify_null`): POWER_LIMITED.** A deterministic-refusal state may
  never be re-labelled statistical by fiat — but here the constraint no longer refuses anything; the
  surviving refusal IS the deflation gate, which is exactly the statistical case the taxonomy
  classifies. ⛔ The one thing this may NOT become is a "+N seasons" auto-trigger: the reachable-NOW
  re-test is the one NF-RECAL1 §5 already named — the metric window is 13 folds today, and C2 needs
  the operator board rebuild (`run_season_projection --backtest-from 2013`) to make 13 folds
  constraint-evaluable. That rebuild is B3's natural first step.

## 3. Scrutiny — the mandated extra checks on a surprising pass

- **Oracle floor + degenerates (corrected band):** `oracle_perplayer` 0.0026 (nothing beats it ✓);
  `zero_project` 162.80 and `pos_median` 82.82 lose to every real arm ✓; `wide_band` 63.02 SATISFIES
  every C3 floor and LOSES the metric ✓ — the constraint-not-criterion proof is intact. No metric
  inversion.
- **⭐ The recorded refuted-magnitude finding REVERSES:** the recorded run had `over_scale` (λ=2)
  WINNING CRPS (50.25 vs best real 50.68) — "the fit under-corrects; the optimum lies outside the
  registered interval." On the served band `over_scale` = **51.54, losing to every real arm**, and
  the in-fold argmin lands at λ≈0.5 inside the grid. The magnitude anomaly was a panel-band
  artifact too; the registered λ interval contains the optimum.
- **A lost tooth, disclosed:** on the corrected band `over_scale` and `wide_band` no longer BREACH
  C3 anywhere (recorded: `over_scale` breached it) — a proportional over-widening keeps coverage, so
  the corrected C3 cannot refuse a magnitude error from above; only the metric can (and does).
  `zero_project` still breaches C2∧C3 — the gate can still fail something (NF1.7 (a) satisfied).
- **⚠️ Harness finding — the round-then-ceil ε-artifact (both runs, recorded and corrected):**
  `coverage_floor_check` computes `need = ceil(round(inc, 6)·n)`, so when the 6-dp rounding rounds
  the incumbent's own coverage UP, an arm whose coverage EQUALS the incumbent's — including λ=0,
  which IS the incumbent — fails by exactly one row (e.g. RB 0.7568 < "0.757"). The recorded run's
  λ=0 arms "failing C3 on 6/7 folds" is this artifact, cosmetic there and here (the infold arms
  score identically to the NULL either way), but it biases infold admissible sets conservative. The
  ε-tolerant sensitivity (`need = ceil(bind·n − 1e-9)`, unrounded incumbent) is reported beside
  every read; no headline changes under it. ⛔ The recorded clause was NOT edited — a re-read does
  not rewrite its subject's pre-registration; the fix belongs to B3's harness.

## 4. NF-D21 — the trap never reached this gate; the refusal stands

- **Band source, measured not assumed:** the `interval_floors` gate reads the ROOKIE band refit
  through the rookie model path (`shipped_rookie_cfg()` off `season_projection` constants via
  `NF17.build_folds` + `NF18.run_arm`) — no `served_*` panel column anywhere on that path. Proven by
  reproducing the recorded λ-sweep row-for-row (every position, every λ, ≤ 5e-5).
- **The corrected C3 STRUCTURE changes nothing:** incumbent (λ=0) RB coverage 0.8041 ≥ 0.80 ⇒
  `min(floor, coverage_incumbent)` = 0.80 — the clause reduces to the bare floor NF-D21 was refused
  under. λ=0.5 RB = 0.7905, **2 covered rows short of 119 at n=148**, exactly as recorded.
- Per-draft-class RB coverage (JSON `rb_per_class_coverage`): the shortfall is carried by the 2021
  (0.60) and 2025 (0.72–0.76) classes at n≈20–25 — the structural thinness NF-D22 exists to gate
  honestly. **State: CONSTRAINT_REFUSED, unchanged. Remedy unchanged: NF-D22 (post-launch,
  independently derived) or a PM decision — never more data, never a moved floor, λ untouched.**

## 5. What this decides, and what it hands off

1. **NF-D21 is TRULY closed.** The PM's close stands on a correctly-measured gate; this record is
   the answer to "was that refusal computed against the wrong band?" — it was not.
2. **NF-RECAL1's record is corrected, not erased:** its C3 refusals of the two constant lifts were
   gate artifacts; its "no_lift" attribution and its over_scale magnitude anomaly were panel-band
   artifacts; its premise finding (−12.85 tier bias, not −37.7) and its C1/C2 findings stand. The
   corrected null state is **POWER_LIMITED at the deflation gate** — the veteran level correction is
   a live hypothesis with an eligible, constraint-clearing, level-fix-signatured winner that does
   not yet carry ship-grade evidence.
3. **What would ship if the evidence strengthened** (named for the escalation, serving nothing
   today): a λ≈0.5 constant multiplicative veteran lift (`global_const`/`pos_const · infold`),
   selected in-fold under the corrected C3.
4. **B3 (joint level+band selection under the corrected C3) inherits:** (a) `coverage_incumbent`
   MUST be the model-path refit band — ⛔ never a `served_*` panel column (the NF1.9-R rule, now
   enforced by this harness's step-0 RAISE); (b) the ε-fix to `coverage_floor_check`'s equality
   boundary; (c) the operator board rebuild to 2013 as the power remedy; (d) the C3-magnitude lost
   tooth — the metric, not the floor, polices over-correction.
