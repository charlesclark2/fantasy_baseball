# NF-W2d — pre-registration: re-gate the injury-availability family with 2025 in the fold set

**Committed BEFORE the run** (the NF-D20 discipline). Every constant here is code in
`weekly_projection_w2d.py` (the pure module); the runner (`run_nf_w2d_2025_regate.py`) reads it
and restates nothing. `best_alpha = 0` — a projection product, no betting/edge claim.
**Deploy-held: this story validates a training era. It promotes nothing, publishes nothing, and
retrains nothing.**

## ⛔ Fresh registration, not a re-read

NF-W2 and NF-W2b both scored 2025 as a **SHADOW** block — the injury family was structurally
unmeasurable there (nflverse deleted `injuries.date_modified` in 2025), so every arm was all-NaN
+ `observed = 0` and the registered expectation was a near-tie. **Those shadow numbers are
dark-fold artefacts of an unmeasurable era and are NOT consulted here, in any direction.** This
registration is written from the coverage measurement below and from the NF-W2b field spec —
never from a 2025 score. Shaping this registration around the prior shadow scores would be the
E2.1-r laundering failure in its most literal form.

## The ONE hypothesis (registered, not searched)

**The certified NF-W2b injury-availability family still beats its matched foil `base_rate` when
the fold set is extended to include 2025 — an era whose injury signal is composed of
as-of-that-instant third-party CAPTURE observations (NF-W2c/NF-W2c-CBS) rather than the vendor's
own `date_modified` stamp, i.e. an era with the same signal character the family will face at
serve time.**

A SHIP-shaped verdict is corroboration on a serve-adjacent era plus two folds of serve-adjacent
training signal. A NULL-shaped verdict is a real finding about serve-time signal character — the
family works on vendor-stamped history and does not survive as-of capture observations — and is
recorded as such.

## What changes vs NF-W2b: ONLY the fold set

| | NF-W2b | NF-W2d |
|---|---|---|
| GATED folds | 12 (2019H1…2024H2) | **14** (2019H1…2024H2 **+ 2025H1, 2025H2**) |
| SHADOW folds | 2 (2025H1, 2025H2) | **none** |
| arms / foil / anchors / oracles | `inj_both`,`inj_zero_leg`,`inj_override` / `base_rate` / `nihilist_zero`,`pos_marginal`,`base_noRate`,`inj_permuted`,`oracle_avail__{base,inj}` | **identical** |
| features | `WP.FEATURES` + `injury_rate` (7) + `injury_report` (7) | **identical** |
| metric, thresholds, purge, label, scoring, seed | CRPS `crps_q39`; PBO<0.20; DSR≥0.95; FDR q=0.10; coverage floor 0.80/3 SE; purge 2 wk | **identical** |

Everything except the fold set is inherited by IMPORT from `weekly_projection_w2b` /
`weekly_projection_w2` / `weekly_projection`, not re-typed — a re-typed constant is a constant
that can drift.

## What makes 2025 gate-eligible now

The 2025 injury source is the landed immutable store
`s3://credence-sports-lakehouse/nfl/pit/wayback_injuries` — **2,187 rows (629 nfl.com + 537
espn.com + 1,021 cbssports.com)**, every row a Wayback capture with a third-party-attested
instant, landed by NF-W2c + NF-W2c-CBS with 0 PIT drops.

- **The as-of instant is the CAPTURE instant.** `source_timestamp` remains a **declared
  absence** — these pages publish no per-row vendor as-of. The 2025 guard records carry
  `source_timestamp = None` plus `source_timestamp_absent_reason`; ⛔ the capture instant is
  never laundered into the vendor slot. (The ≤2024 records keep the nflverse shape,
  `source_timestamp = date_modified`.)
- **Admissibility is re-derived here, fail-closed — never trusted from the landed row.** A
  capture is consumable for a player-week iff its instant is **strictly before that row's own
  target gameday 00:00 UTC**.
- **Coverage bound `COVERAGE_MAX_AGE_DAYS = 7`, registered on sport structure, NOT tuned.** A
  capture establishes coverage for a row only if it lands within **one NFL game week** of that
  row's own gameday instant. Rationale, fixed before the numbers were read: the league's injury
  report is a WEEKLY practice-cycle document, and CBS's page mixes a *next-week preview* into
  the current week's table, so an unbounded rule would let a September capture "cover" a
  December game — an observation about a different week's practice cycle. The **3-day and
  unbounded variants are reported as pure DIAGNOSTICS**; ⛔ nothing selects on them and the gate
  never reads them.
- **`observed` becomes PER-ROW, not an era constant.** A row is observed iff ≥1 admissible,
  in-bound capture exists for its `(season, week)` strictly before its own instant. Where
  `observed = 0` the entire family is **NaN**. ⛔ **NO `fillna(0)`** — an uncovered player-week
  is *unmeasured*, never *healthy* (the NF-W0b snap discipline).
- **A covered row absent from every admissible capture reads NOT LISTED** (`listed = 0`,
  statuses 0). This is licensed by the source shape: each capture is a *league-wide* report
  snapshot, so "the report was readable before my instant and I am not in it" is a genuine
  observation of no designation — not an imputation.
- **Per-column absence is reported, never pooled (MH2.1 (c)).** ESPN carries **no practice line
  at all**; CBS carries one on 539 of 963 in-bound rows; nfl.com on 629 of 629. For a LISTED
  2025 row whose consumed capture has no practice line, the two practice columns are **NaN**,
  never 0 — "no practice information" is not "practiced fully." The 2025 practice sub-family is
  therefore materially thinner than 2016–2024's (where `practice_status` is 100% populated), and
  the report states what 2025 consequently does and does not certify.
- **The practice vocabulary is MAPPED onto the canonical nflverse contract, and the guard asserts
  the CANONICAL key** (`did not participate in practice` / `limited participation in practice`),
  never the adapter's own output — NF-C0e: a test that reads a value back under the key the code
  wrote can never catch a wrong key.

## Measured design quantities — measured BEFORE any scoring, logged, never gated

Population = the 8,688 modeled 2025 REG player-weeks in the certified frame (QB/RB/WR/TE).

| quantity | measured |
|---|---|
| coverage @ 7 d (PRIMARY) | **8,240 / 8,688 = 0.9484** |
| coverage @ 3 d / unbounded (diagnostic only) | 0.9375 / 1.0000 |
| coverage by half | 2025H1 **1.000** · 2025H2 **0.898** |
| coverage by position | QB 0.9497 · RB 0.9464 · WR 0.9492 · TE 0.9485 |
| the ONE uncovered week | **week 12 (Thanksgiving), 0.000 @ 7 d** — nearest capture 10.9 d stale |
| capture age over covered rows | median 0.606 d · p75 1.483 d · p90 1.740 d |
| in-bound landed rows joined to a modeled row | 2,083 of 2,187 |
| practice line present among those | 1,168 / 2,083 (nfl 629/629 · cbs 539/963 · **espn 0/491**) |
| practice column NaN among LISTED 2025 rows | **0.3433** (the per-column absence, never pooled) |
| store multiplicity | **1 capture per `subject_key` for all 2,187 subjects**; 664 player-weeks captured by >1 SOURCE |

**Mechanism activity (the NF-D20 count — "could the mechanism act at all?"):** listed share on
the 12 gated 2016–2024 folds runs **0.152–0.216**; the engineered 2025 listed share over covered
rows is **0.1630** (1,343 distinct covered player-weeks carry a designation — the 2,083 in-bound
store rows collapse to 1,343 player-weeks because 664 of them were captured by more than one
source, and the family consumes ONE capture per player-week). Out∪Doubtful runs **0.0337** in
2025 against 0.024–0.051 on the gated folds. **The mechanism is comparably active on the new
folds** — they are not the structurally-inactive thing the SHADOW blocks were, which is the whole
reason they may now be gated. Week 12 is the single genuinely inactive week and is reported as
such.

**An inactive clause is uninformative, never a pass (NF-D20).** Because every `subject_key`
holds exactly one capture, the guard's clause-7 REVISION check has nothing it could fire on
today; the run reports that count rather than presenting a vacuous pass. The gate is therefore
called with `store_index = {}` — the same convention as NF-W2/NF-W2b — and the reason is stated
rather than left silent: consuming the LATEST admissible capture of a player-week is a correct
as-of read, not a vendor restatement, so a populated index would false-reject legitimate
observations the moment a second capture of a subject lands.

## The field (inherited from NF-W2b verbatim)

**Foil / matched pair (non-shippable):** `base_rate` — the NF-W1 champion spec plus the
week×position `injury_rate` group-rate family, refit per fold. Each real arm is the IDENTICAL
bundle plus the player-level `injury_report` family, so the paired delta vs `base_rate` IS the
pure player-level attribution (NF-D10).

**Real arms (the declared 3-arm family — the DSR trial field):** `inj_both`, `inj_zero_leg`,
`inj_override`.

**Anchors (diagnostic — excluded from the PBO matrix and the DSR trial field, MH2.1 (a)):**

| anchor | registered expectation |
|---|---|
| `nihilist_zero` (all-zero degenerate ceiling) | **MUST lose** to every real arm — SCORED every run, never reasoned (NF-D11/NF-D14: MAE inverts at QB/TE on this frame, so the degenerate is the two-sided check that CRPS is not inverted) |
| `pos_marginal` (train climatology per position) | MUST lose |
| `base_noRate` (the NF-W1 champion EXACT spec — the production incumbent) | the winner MUST beat it (the deployment bar); `base_noRate − base_rate` prices the marginal channel directly (reported, never gated) |
| `inj_permuted` (player injury columns permuted within position × global week, rate columns untouched) | (a) the winner MUST beat it; (b) its lift over `base_rate` must be non-positive or non-significant (one-sided paired p ≥ 0.05) |
| `oracle_avail__base` / `oracle_avail__inj` | NF-D16 per-**FORM** peeking floors — each arm is floored by the peeking version of its OWN form; no arm may beat its own oracle |

## Metric

- **Selection: CRPS** (`crps_q39`), identical 39-level representation for every arm, monotone
  rearrangement uniformly applied. ⛔ **MAE is reported and NEVER selects** — its conditional
  median sits exactly at 0 for QB and TE on this frame, so it is inverted for half the board
  (NF-D11/NF-D14).
- Coverage of the central 80% interval is a **FLOOR** (0.80), never a target — reported with its
  binomial SE, blocking only beyond 3 SE (NF1.8, rows-not-decimals).

## Gates (per position; unchanged from NF-W2b except `n_folds` 12 → 14)

SHIP requires ALL of: winner (among the 3 arms, mean fold CRPS over the **14** gated folds)
beats `base_rate` · `cv_power.fold_consistency_clause(14)` paired fold wins vs `base_rate` ·
winner beats `base_noRate` (the deployment bar) · PBO < 0.20 over the eligible set
{3 arms + `base_rate`} · DSR ≥ 0.95 · BH-FDR q = 0.10 across the 4 position tests · every
MUST-lose anchor loses · the calibrated permutation pair holds · no arm beats its own-form
oracle · coverage floor not in blocking shortfall.

**Deflation convention, stated explicitly so silence cannot read as a trim.** The fantasy
vertical calls `M14.deflated_sharpe` **directly** (the DSR-CONV degenerate-exclusion change
reached only the two MLB legs, `e7_9` and `mh2_5`). NF-W2d uses that whole-field call unchanged,
over the declared 3-arm family — byte-identically the convention NF-W2 and NF-W2b used. ⛔ No
field trim, no convention switch, no post-hoc narrowing, whatever the number comes out at. (In
this harness anchors and degenerates were never in `trial_srs`, so there is no
degenerate-inflated `V` for DSR-CONV to remove; the question does not arise here and the
convention is therefore identical for the 14-fold and 12-fold reads alike.)

## Primary vs diagnostic population (registered in advance)

- **PRIMARY — what the gates read: the FULL modeled population of every fold, 2019–2025**,
  constructed identically to NF-W2b, with 2025's uncovered rows carrying `observed = 0` and a
  NaN family. This is the serve-honest reading: a partially-covered feed is exactly what the
  champion faces at serve time, and the NF-W2 record already measured that a dark feed makes the
  learned arms slightly WORSE than base.
- **DIAGNOSTIC — reported, never gated:** (i) the **covered-subset** decomposition (2025 rows
  with `observed = 1` only), so a null caused by coverage dilution is distinguishable from a null
  caused by the mechanism; (ii) the **2025-only** two-fold read; (iii) the **era delta** — the
  same run's 12-fold (2019–2024) sub-read beside the 14-fold read, so what adding 2025 did is
  visible as a quantity rather than inferred.

## Reproduction control (a run that fails it is INVALID, not a finding)

The 12 legacy folds train only on `gw ≤ start − 3` and test inside 2019–2024, so nothing they
touch can depend on the 2025 source. **The W2d harness must therefore reproduce NF-W2b's
recorded per-fold CRPS on those 12 folds to within 1e-9.** A mismatch means the inherited
harness was perturbed by the 2025 plumbing, and the run is discarded and fixed — it is not
reported as an era effect. (This is the positive control that makes "only the fold set changed"
a measured claim rather than an assertion.)

## Null handling

Any failing position is hand-classified into the **CONSTRAINT_REFUSED** family when every
STATISTICAL gate passes and the refusal rests only on anchor/registration clauses
(`W2B.hand_classify_refusal` — the NF-D18/MH2.7 `classify_null` gap, already hit twice on this
line); otherwise `cv_power.classify_null` speaks. Either way the report states the margin **in
folds / weeks / rows** and whether it is reachable now — and ⛔ never publishes a
"needs +N seasons" trigger for a refusal more data cannot move.

## ⛔ The one thing this story may not do

Change what is staged or served. The NF-W2b challenger stands exactly as staged
(`nfl_fantasy_w2b_v1`, challenger status). NF-W2d promotes nothing, publishes nothing, and
retrains nothing. A champion re-train that includes 2025 is a **POST-MERGE operator step**,
blocked on the existing chain (NF-C6 Phase 2 + NF-W0a live arming; and MH2.1's
merge-is-the-deploy hazard for any registry change) — it is listed as a note, never performed
in-session.

## Outputs

- `ablation_results/nf_w2d_2025_regate.{md,json}`; `--smoke` writes `*_smoke` artifacts that can
  never be mistaken for the real search.
- The coverage table above recomputed at run time (never hardcoded), the per-fold activity table
  including the new 2025 folds, the covered-subset and era-delta diagnostics, the reproduction
  control, and the per-position gate detail.
