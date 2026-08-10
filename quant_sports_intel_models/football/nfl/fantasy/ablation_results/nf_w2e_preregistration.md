# NF-W2e — pre-registration: is NF-W2d's 2025 attenuation caused by CAPTURE FRESHNESS?

**Committed BEFORE any lift is scored** (the NF-D20 discipline). Constants live in
`weekly_projection_w2e.py`; the runner reads them and restates nothing. `best_alpha = 0`,
**deploy-held**.

## ⛔ This story CANNOT certify anything, and that is registered up front

The mechanism under test can only act on rows whose injury family comes from a capture store —
i.e. **2025 only, 2 folds.** That is not a data-scarcity accident, it is the design, so the power
ceiling is a DESIGN quantity and is computed rather than asserted (`betting_ml/utils/cv_power.py`):

| at n_folds = 2 | value | consequence |
|---|---|---|
| `fold_consistency_clause(2).attainable` | **False** | the fold clause cannot be satisfied by any result |
| `pbo_evaluable(2)` | **False** (needs 4) | PBO is UNDEFINED, not failed |
| `sign_test_floor(2)` | **0.2500** | above every BH cutoff ⇒ no effect of any size can pass |
| `dsr_ceiling(2)` | **0.9214** | below the 0.95 gate ⇒ DSR is mathematically unreachable |

⇒ **NF-W2e is a MECHANISM-ATTRIBUTION study, not a §0.5 selection.** It registers no ship unit,
promotes nothing, and its per-position verdict field is fixed to `NO_CERTIFICATION_POSSIBLE` by
construction. Reporting a "SHIP" here would be meaningless, and reporting a "NULL" as though the
gates had been *evaluated* would be the MH2 `UNDEFINED`-vs-`GENUINE-ABSENCE` conflation. What the
study CAN do is measure a direction and a magnitude at ROW level, and prove a mechanical control.

**Re-test trigger (calendar-bound, and stated as such):** the capture era gains ~2 folds per
season of NF-W0a forward capture. PBO becomes evaluable at **4 capture-era folds (end of 2026)**;
`folds_for_sign_certifiability(0.10) = 4`. This is a genuine future re-test, NOT a "needs more
data" shrug — the folds arrive on a known schedule.

## The ONE hypothesis (registered, not searched)

**NF-W2d measured that the injury family's lift is ~3× smaller at RB on the 2025 as-of-capture
era, arm-invariantly, and eliminated coverage dilution, season scale and practice-line absence.
The surviving candidate is the capture SIGNAL CHARACTER itself. NF-W2e tests its sharpest form:
that the attenuation is caused by consuming designations that a FRESHER available capture has
already superseded — and therefore that restricting consumption to fresher captures RECOVERS
lift.**

The competing outcome is registered as equally informative: **freshness costs volume.**
Restricting to fresh captures discards 65–79% of the 2025 designations (measured below), so
`inj_latest` winning would mean a stale-but-present designation is worth more than no designation
— which would REFUTE the carry-over mechanism and leave the era-character question open. Both
directions are pre-registered as findings; neither is the "hoped-for" result.

## Design quantities — measured BEFORE any lift was scored

### (1) The lag distributions: it is a DISPERSION difference, not a location shift

Consumed-stamp lag (days before the row's own gameday 00:00 UTC), over listed rows:

| era | n | median | sd | share > 2 d | share < 0.5 d |
|---|---|---|---|---|---|
| legacy (nflverse `date_modified`) | 14,058 | 1.435 | 0.439 | **3.9%** | 5.1% |
| 2025 (wayback capture) | 1,343 | **1.483** | **1.375** | **27.0%** | **29.8%** |

⭐ The MEDIANS are nearly identical. The 2025 regime is not systematically *older*, it is
**far more DISPERSED** — a fresher head and a much staler tail. This is why the registered
mechanism is *freshness dispersion / carry-over*, and why a constant-lag "degrade the legacy
stamp" simulation was considered and **rejected**: it would model a location shift the data says
does not exist, and (worse) applying a larger lag to nflverse — which holds one report per
player-week — converts "a stale designation" into "no designation", which is a different
degradation entirely.

### (2) The stratifier VALIDATES — but only after a confound was removed (MH2.1)

Before reading any lift by capture age, the partition must be shown to separate the realized
quantity the hypothesis needs. Using the 627 player-weeks with ≥2 admissible in-bound captures,
does the gap between consecutive captures separate whether the DESIGNATION changed?

**First cut — WRONG, and recorded because the error is the lesson:** rank corr = **−0.003,
p = 0.947**, i.e. "the stratifier is inert, the hypothesis is INACTIVE." That reading was an
artifact: nfl.com publishes practice-only rows carrying a NULL `report_status`, so 286 of the 386
"changes" were a row crossing between a source that publishes designations and one that publishes
a practice line — a **source-format** difference, not a designation change.

**Confound removed (both captures carry a real designation, n = 341):**

| gap between captures | n | designation-change rate | SE |
|---|---|---|---|
| < 0.5 d | 52 | **0.038** | 0.027 |
| 0.5–1 d | 66 | 0.258 | 0.054 |
| 1–2 d | 84 | 0.333 | 0.051 |
| 2–3 d | 10 | 0.200 | 0.126 |
| > 3 d | 129 | **0.395** | 0.043 |

rank corr = **+0.289, p < 0.0001**. Two-bin cut: **≤1 d → 0.161 · >1 d → 0.363**.

⇒ The partition separates designation staleness by ~2.3×. **The 1-day threshold in the ladder
below is taken from THIS table** — a design quantity measured before any lift was read — not
tuned on an outcome.

### (3) Carry-over is large and structurally impossible in the legacy era

**36.3% of listed 2025 rows (487 / 1,343) are consumed from a capture that a FRESHER capture of
the same week has superseded** — the newer report exists and does not list them. Median carry-over
gap 1.65 d, p90 4.08 d, max 6.14 d. In the legacy era nflverse holds one report per player-week,
so this cannot occur at all.

### (4) Mechanism activity (NF-D20): the ladder's cost in designations

| arm | consumption rule | listed 2025 rows | share of incumbent |
|---|---|---|---|
| `inj_latest` | latest admissible capture ≤ 7 d (**the NF-W2d incumbent**) | 1,343 | 100% |
| `inj_fresh1d` | latest admissible capture ≤ **1 d** | 475 | 35.4% |
| `inj_freshest` | only the row's OWN freshest admissible capture instant | **856** | **63.7%** |

By position (`inj_latest` → `inj_fresh1d`): QB 159→51 · RB 279→104 · TE 298→108 · WR 607→212.
The ladder is a real freshness-versus-volume trade-off, which is what makes it a test rather than
a foregone conclusion.

> ⚠️ **CORRECTION (recorded rather than quietly amended).** The `inj_freshest` row first read
> **281 / 20.9%** here. That figure came from a scratch probe that took the week's freshest
> capture as a single **week-level minimum age**, which is wrong twice over: rows inside a week
> have different gamedays (Thu / Sun / Mon), so (a) the reference instant is a PER-ROW quantity,
> and (b) a week-level minimum can be a capture landing AFTER an earlier row's gameday — i.e. the
> probe's rule would have been a PIT violation had it been implemented. The harness uses the
> per-row `_inj_capture_age_days` that `attach_coverage` already computes under the strict
> pre-gameday bound, giving 856. The corrected number is self-consistent with the carry-over
> census above (1,343 − 856 = 487 superseded rows = the measured 36.3%), which is what confirms
> it. Nothing about the registered arms, metric, gates or expectations changes — the ladder is
> simply less brutal at its top rung than the erroneous probe suggested.

## The field

**Foil:** `base_rate` — unchanged from NF-W2b/NF-W2d (NF-W1 champion + the week×position
`injury_rate` family), refit per fold. Every arm is the identical bundle plus the player-level
`injury_report` family, so each paired delta is the pure player-level attribution (NF-D10).

**The declared family — a monotone FRESHNESS LADDER (one coherent mechanism, MH2's
"run a COHERENT, DECLARED family"):** `inj_latest` (≤7 d) → `inj_fresh1d` (≤1 d) →
`inj_freshest` (freshest instant only). A ladder, so the three arms answer one question.

**Arm FORM: `inj_both` for every rung.** Justified by a measured quantity, not convenience —
NF-W2d found the era ratio ARM-INVARIANT (max |`inj_both` − `inj_zero_leg`| = 0.062 across all
four positions), so the freshness question does not depend on the leg structure and holding the
form fixed removes a nuisance dimension.

**Anchors (diagnostic; never trials):** `nihilist_zero` and `pos_marginal` must lose (SCORED
every run, never reasoned — NF-D11/NF-D14); `oracle_avail__inj` is the NF-D16 per-form peeking
floor for the `inj_both` form and no arm may beat it.

## ⭐ The COVERAGE bound and the CONSUMPTION bound are separated — this is load-bearing

`COVERAGE_MAX_AGE_DAYS = 7` (NF-W2d's registered one-game-week bound) continues to decide which
rows are **observed**, for EVERY rung. Only the **consumption** bound varies down the ladder.
Collapsing the two would shrink the observed POPULATION as the ladder tightens, and the arms
would then differ in both their features and the rows they are scored on — a confound that would
make the whole comparison uninterpretable. The population is identical across all three rungs by
construction, and a guard asserts it.

## The mechanical control: the ladder is INERT before 2025, exactly

The consumption rule can only touch capture-era rows, so **the three arms' feature matrices must
be byte-identical on every pre-2025 row**. This is asserted exactly (all 14 family columns,
75,865 rows) and is a PROOF, not an estimate: it means the 12 legacy folds cannot differ. It is
backed by a MEASURED tie — all three rungs are additionally fitted on two registered legacy folds
(**2024H1, 2024H2**) and their per-fold CRPS must agree to 1e-9. A difference on either control
means the consumption rule leaked into the legacy era ⇒ **the run is INVALID, not a finding.**

(Fitting all three rungs on all twelve legacy folds would buy nothing beyond this, since the
matrices are provably identical there; the two measured folds exist so the proof is not the only
evidence.)

## Metric + the primary read

- **CRPS** (`crps_q39`), identical 39-level representation. ⛔ MAE reported, never selects
  (inverted at QB/TE on this frame — NF-D11/NF-D14).
- **PRIMARY: the row-level paired delta on the capture era**, `inj_fresh1d − inj_latest` and
  `inj_freshest − inj_latest`, per position, over the 2025 rows — with a **week-CLUSTERED SE**
  (18 clusters). Rows inside a week share a capture schedule and are NOT independent draws; a
  naive per-row SE would overstate precision by roughly the square root of the cluster size
  (the NF1.8 rows-not-decimals lesson, one level over). Both the naive and the clustered SE are
  reported so the difference is visible.
- **SECONDARY: the pre-registered stratified read** — the incumbent's per-row lift over
  `base_rate` split at the validated **≤1 d / >1 d** consumed-age boundary, per position. If
  staleness attenuates the lift, the fresh stratum carries more of it.
- **Fold-level** deltas on the 2 capture-era folds are reported for completeness and are
  explicitly NOT gated (see the power ceiling above).

## Registered expectations (two-sided, so neither direction is the "hoped-for" one)

1. **Carry-over hypothesis TRUE** ⇒ `inj_fresh1d` and/or `inj_freshest` beat `inj_latest` on 2025
   despite holding 35%/21% of the designations, and the ≤1 d stratum carries more lift.
2. **Carry-over hypothesis FALSE / volume dominates** ⇒ `inj_latest` wins; a stale-but-present
   designation beats no designation. The carry-over is then BENIGN, and the NF-W2d attenuation
   must be attributed elsewhere (a genuine era difference, or something not yet named).
3. **Instrument blind** ⇒ the clustered CI spans both directions at every position. Then the
   honest state is `UNDEFINED` at this fold count with the calendar-bound trigger above —
   ⛔ never reported as "no effect."

## ⛔ What this story may not do

Change the incumbent, the staged challenger, the served board, or the NF-W2d construction. If the
carry-over rule turns out to look better, that is a **carded proposal for a future story with
enough capture-era folds to certify it** — adopting a construction change off a 2-fold read would
be exactly the E2.1-r failure this program keeps cataloguing. `best_alpha = 0`; deploy-held.

## Outputs

`ablation_results/nf_w2e_capture_freshness.{md,json}`; `--smoke` writes `*_smoke`. The
stratifier-validation table (both the confounded and the corrected version), the carry-over
census, the ladder's activity counts, the mechanical + measured controls, and the clustered
row-level reads are all recomputed at run time, never hardcoded from this document.
