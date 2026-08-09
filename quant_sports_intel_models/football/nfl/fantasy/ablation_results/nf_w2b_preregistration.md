# NF-W2b — pre-registration: re-register the injury family against a marginal-rate-carrying foil

**Committed BEFORE the full run** (the NF-D20 discipline). Every constant here is code in
`weekly_projection_w2b.py` (the pure module); the runner (`run_nf_w2b_injury_rate_bakeoff.py`)
reads it and restates nothing. `best_alpha = 0` — a projection product, no betting/edge claim.
Deploy-held; nothing auto-deploys.

## Where this registration comes from (the NF-W2 record, restated as the premise)

NF-W2 confirmed the injury-report availability family as real and large at every position
(+0.061–0.140 CRPS/wk, 3.4–5.5%, fold wins 11–12/12, PBO ≤ 0.036, DSR ≥ 0.9987, p ≈ 0, joint
FDR pass), SHIPPED it at TE, and recorded a **CONSTRAINT_REFUSED-family null at QB/RB/WR on
exactly one clause**: the permuted arm (player linkage destroyed, week×position marginal rates
preserved) showed a small but significant lift over the base foil (QB +0.0096 p=.033 /
RB +0.0080 p=.0089 / WR +0.0034 p=.036) ⇒ the family carries a real week×position
marginal-listing-rate channel worth 3–9% of the lift, and the registered gate demanded the
attribution be ENTIRELY player-level. That channel is **information, not leakage** (week-level
listing rates are PIT-clean); the clause polices ATTRIBUTION, not legitimacy. Player-level
content (winner − permuted) was 91–97% of the lift.

## The ONE hypothesis (registered, not searched)

**Absorb the marginal channel into the incumbent — add pre-registered week×position
LISTING-RATE features (group rates, no player linkage) to the base foil — and the injury
family's remaining lift over that stronger foil is pure player-level content: it beats the
rate-carrying foil at QB/RB/WR under full deflation, and the amended permutation clause is
satisfied by construction (the permuted arm's marginal channel is now IN the foil, so its
residual lift is inert).** This is the successor NF-W2 §7 carded: one registration, not one
discovery.

## ⛔ The one thing this story may not do

Promote an arm that has not beaten **both** (a) the rate-carrying matched foil `base_rate`
(the attribution bar) and (b) the production incumbent `base_noRate` (the NF-W1 champion spec —
the deployment bar) on purged held-out weeks under deflation. A foil win, a gate miss, or an
anchor violation is a **recorded NULL** — classified via `cv_power.classify_null` for
statistical nulls, and **hand-classified into the CONSTRAINT_REFUSED family for any
anchor/registration-driven refusal** (the NF-D18/MH2.7 instrument gap: `classify_null` has no
state for anchor refusals and mislabels them POWER_LIMITED, hit twice; a p≈0 registration
refusal never gets a sample-size re-test trigger).

## Frame (binding NF-W0/NF-W1/NF-W2 constraints — unchanged)

- Certified roster-first frame rebuilt in memory, 2016–2025 REG, zeros retained; label pinned
  `v1.nflverse.stats_player_week` / `ppr`; scoring population = QB/RB/WR/TE, `label ≠ bye`.
- All NF-W1 features unchanged (`weekly_projection.FEATURES`); the NF-W2 `injury_report`
  family unchanged (same 7 columns, same admissibility bound: `date_modified` strictly before
  the player's own target gameday 00:00 UTC, fail-closed); snap + injury families NULL-bearing
  (⛔ never `fillna(0)`); era-forbidden tokens excluded.
- Folds: the same **12 GATED** expanding-window half-season blocks (2019H1…2024H2; family
  ACTIVE + PIT-verifiable on all) + the same **2 SHADOW** blocks (2025H1/2025H2 — the whole
  injury AND rate family structurally unmeasured there: all-NaN + observed=0; scored, reported,
  never gated; registered expectation = near-tie of every arm with the foil).

## The NEW family: `injury_rate` (week×position group rates — NO player linkage)

Derived purely from the SAME admissible report rows the certified `injury_report` family
consumes (identical source, identical fail-closed admissibility); a group AGGREGATE, so its
provenance is the `injuries` contract entry's. Seven columns mirroring the player family:

| column | semantics |
|---|---|
| `injury_rate__listed` | share of this position's modeled rows this week whose consumed report is stamped strictly before THIS row's own gameday 00:00 UTC |
| `injury_rate__status_out` | same-construction share carrying each designation / practice status |
| `injury_rate__status_doubtful` | (numerator = consumed indicator ∧ stamp < this row's instant; |
| `injury_rate__status_questionable` | denominator = ALL modeled rows of (season, week, position)) |
| `injury_rate__practice_dnp` | |
| `injury_rate__practice_limited` | |
| `injury_rate__observed` | era presence flag: 1 = the family is measurable (2016–2024), else 0 with all rates NaN |

**PIT construction (strictly per-row):** a week-level rate computed over ALL of the week's
final stamps would NOT be PIT for a Thursday game (Friday/Saturday stamps land after its
instant). So the rate for a row with target-gameday instant *g* aggregates ONLY report rows
stamped strictly before *g* — computable at serving time ("as of my game's midnight, the share
of my position listed this week") and fail-closed for early-week games by construction. The
aggregation's consumed-stamp bound flows through the per-game PIT gate as one extra guard
record per row carrying the MAX consumed stamp (`_rate_max_stamp_utc`) — a `<`→`≤` bug or a
wrong-instant bug propagates into the record and the gate REJECTS (RED-proven in the guard
tests). Group-level by construction: the rate columns are CONSTANT within
(season, week, position, gameday) — asserted mechanically, so no player identity can enter.

2025+: the family is NaN with `injury_rate__observed = 0` — ⛔ never `fillna(0)`; NULL =
unmeasured, never healthy.

## The field

**Foil / matched pair (non-shippable in this field):** `base_rate` — the NF-W1 champion spec
with the `injury_rate` family added to BOTH legs, refit per fold. Each real arm is the
IDENTICAL bundle plus the player-level `injury_report` family, so the paired delta vs
`base_rate` IS the pure player-level attribution (NF-D10).

**Real arms (the declared 3-arm family — the SAME mechanism family as NF-W2, availability
incorporation, now over the rate-augmented base; this is the DSR trial field):**

| arm | form |
|---|---|
| `inj_both` | hurdle with the player injury family in BOTH legs (on top of base+rate features) |
| `inj_zero_leg` | player injury family in the P(zero) leg ONLY; conditional leg = the SHARED `base_rate` fit |
| `inj_override` | `base_rate` untouched except: test rows with admissible Out∪Doubtful get `p0 ←` the train-fold pooled empirical P(zero \| Out∪Doubtful) (raises below 200 train rows — NF1.7 (a)) |

**Anchors (diagnostic — excluded from the PBO matrix and the DSR trial field, MH2.1 (a)):**

| anchor | role | registered expectation |
|---|---|---|
| `nihilist_zero` | all-zero degenerate ceiling | MUST lose to every real arm (measured every run, never reasoned — NF-D14) |
| `pos_marginal` | train climatology per position | MUST lose |
| `base_noRate` | the NF-W1 champion EXACT spec (NF-W2's `base_hurdle`) — the production incumbent | (i) the winner MUST beat it (the deployment bar); (ii) reports the marginal channel priced directly: the paired delta `base_noRate − base_rate` (registered expectation: small positive — the 3–9% channel — REPORTED, never gated; a ~tie is also consistent, trees may not exploit weak group rates) |
| `inj_permuted` | `inj_both`'s exact form with the 7 PLAYER-level injury columns' values permuted within (position × global week) in train AND test; rate columns untouched | the NF-W2 calibrated pair, now vs `base_rate`: (a) the winner MUST beat it; (b) its lift over `base_rate` must be non-positive or non-significant (one-sided paired p ≥ 0.05). ⭐ THE registered fix: expected to PASS because the marginal channel now lives in the foil, leaving the permuted player columns inert |
| `oracle_avail__base` | PEEKING availability ceiling of the base form: `p0 = 1{y=0}` realized + `base_rate`'s conditional leg | floors `base_rate` / `inj_zero_leg` / `inj_override` (their shared conditional form) |
| `oracle_avail__inj` | same, with `inj_both`'s conditional leg | floors `inj_both` |

Per NF-D16, each arm is floored by the peeking version of **its own form**. Per MH2.5's
DSR-degenerate landmine: the DSR trial field is the declared 3-arm family ONLY — anchors and
degenerates never enter `trial_srs`, so the cross-trial dispersion V is degenerate-excluded BY
CONSTRUCTION (the DSR-CONV-compatible convention; there is no whole-field-with-degenerates DSR
in this harness to report beside it, and NF-W2 scored identically).

## Metric

- **Selection: CRPS** (`crps_q39`), identical 39-level representation for every arm, monotone
  rearrangement uniformly applied. ⛔ MAE reported, never selects (inverted at QB/TE on this
  frame — NF-D11/NF-D14).
- Coverage of the central 80% interval is a **FLOOR** (0.80): reported with binomial SE,
  blocking only beyond 3 SE (NF1.8 rows-not-decimals).

## Gates (per position; ship unit = per-position champion spec)

SHIP requires ALL of: winner (among the 3 arms, mean fold CRPS over the 12 gated folds) beats
`base_rate` · `cv_power.fold_consistency_clause(12)` = 8/12 paired fold wins vs `base_rate` ·
winner beats `base_noRate` on the mean (the deployment bar) · PBO < 0.20 over the eligible set
{3 arms + `base_rate`} (`NF18.deflate`; flips + contender spread + os-gap reported) · DSR ≥
0.95 over the declared 3-arm family (paired per-fold deltas vs `base_rate`;
`M14.deflated_sharpe`) · BH-FDR q = 0.10 across the 4 position tests · every MUST-lose anchor
loses · the calibrated permutation pair (`winner_beats_permuted` AND
`permuted_lift_not_significant`, both vs `base_rate`) holds · no arm beats its own-form
availability oracle · coverage floor not in blocking shortfall. Anything else ⇒ the position's
verdict is a recorded null (classification per the ⛔ section above), with the NF-D20
active-fold count.

**Position scope (declared in advance):**
- **QB / RB / WR — the PRIMARY ship units.** A SHIP verdict extends the injury-family champion
  to that position (spec = the winning arm over the rate-augmented bundle), staged via NF-G0
  as an operator step.
- **TE — a registered CONSISTENCY check, not a re-decision.** TE already shipped under
  NF-W2's own registration (`inj_zero_leg` vs `base_hurdle`); that ship STANDS regardless of
  this run. TE's gates are computed identically here and reported: if they pass, a UNIFIED
  rate-augmented TE spec is available (operator decision, NF-G0); if they fail, the
  discrepancy is flagged to the operator — never auto-revoked. TE stays in the BH-FDR family
  (all 4 positions test jointly, exactly as NF-W2 — declaring 3 would be the smaller-field
  trim MH2.2 warns against; with 4 the correction is weakly stricter).

## Serving dependency (inherited from NF-W2, now covering BOTH families)

The `injury_report` AND `injury_rate` features exist at serve time only with a live, stamped
injury feed — **NF-W0a forward-capture is load-bearing**. With a dark feed both families are
NaN + observed=0 and the champion must fall back to the base spec (the shadow folds price
exactly this). Every consumed injury row (player family) and every rate aggregation (max
consumed stamp) feeds NF-W0a's `assert_point_in_time`, fail-closed.

## Outputs

- `ablation_results/nf_w2b_injury_rate_bakeoff.{md,json}`; `--smoke` writes `*_smoke`
  artifacts that can never be mistaken for the real search.
- The three-way decomposition per position: `winner − base_noRate` (total lift vs production)
  = `base_rate − base_noRate` (the marginal channel priced directly) + `winner − base_rate`
  (pure player-level content, the attribution). The shadow-2025 tie check, the per-fold
  activity table, and the coverage floor report.
- Registry/serving untouched — a promotion is registered only on a SHIP verdict, and any
  staging goes through the NF-G0 governance CLI as an operator step.
