# NF-ROS1b — delta pre-registration: the ROS interval, redesigned at the mechanism NF-ROS1 named

Registered 2026-09-17 (branch `nf-ros1b`), **BEFORE any interval, hurdle probability, ratio
residual, arm score or name-join result has been computed.** Nothing in §0–§12 may be re-read after a
result lands (E2.1-r). Post-run findings go in §13, appended, never edited above it. A refused bar
closes as a certified NO. It is **not** retried with a softer bar, and **no second family is tried in
this story**.

⚖️ `best_alpha = 0` · calibration/honesty product · no win-rate/edge claims · no serving-page code ·
no WVR1/trade surface change. Spec: `plan_specs/nfl_fantasy/nf-ros1b.yaml`.

**What was looked at before this commit** (stated so the registration's blindness is auditable):
the parent's full record (`nf_ros1_preregistration.md` §1–§13, amendments 1–2,
`nf_ros1_walkforward.{json,md}`), which is already published; the parent harness source; Delta
table readability at the parent's pins (`stats_player_week` v28 and `schedules` v36 read 2026-09-17,
and both are still the latest versions); the served 2026 board's id format and row counts; and the
column lists of `rosters`, `weekly_rosters`, `injuries` and `nflverse_draft_picks`. **No quantity
defined in this document has been computed.** The family below is chosen from the parent's
qualitative mechanism statement (§13.1 item 2). No parameter is set from a parent fold number.

---

## §0 Inheritance rule

Everything in `nf_ros1_preregistration.md` §1–§12 and amendments 1–2 **binds this story verbatim**,
except the items this document names as deltas. The parent's §13.4 finding binds: the amendment-1
item 6 PIT atom rule is correct and is **not** re-repaired. The parent's figures are the before-side
of this story and are never re-claimed as fresh.

## §1 What changes, and only that

**One sentence of the parent changes:** the "Predictive" bullet of §4.3 (the location-shift residual
construction). It is replaced by §2 below for **every** predictor: the incumbent, the three real arms,
the matched foil, the four point degenerates, and every oracle and matched-n anchor. Arms therefore
still differ only through their point (parent §3.1).

Unchanged, by reference: the population and join (§2.1), the target, weeks and folds (§3), the
metric (CRPS on the 19-level grid, full-PPR 12-team gate, half-PPR and standard reported), the form
family and the m-grid MSE fitting (§4.1–§4.3 except the Predictive bullet), the declared field of 3
(§4.2, `declared_field_size = 3`), every anchor and its registered direction (§5), the `zero_width`
and `max_width` overrides, the ship bar C1–C9 at the same values (§6), the waiver section (§7),
the deliverable contract (§8), the machinery clauses (§9) and the diagnostics (§10).

**The point form is carried unchanged as the location.** `eb_rate_avail` is the pre-registered
primary. The winner is still selected on pooled full-PPR CRPS among the 3 real arms, now under the
new predictive.

---

## §2 The interval family: HURDLE (one family, fixed parameters)

### §2.1 Mechanism (from parent §13.1 item 2, quoted)

> *"A location-shift band cannot express a zero atom whose size depends on the player (injury /
> benching / release) nor a spread that scales with the projection."*

A rest-of-season total is zero when a player plays no further meaningful snaps. That event has a
player-specific probability, driven by how recently and how often he has been available. Otherwise
the total is a positive quantity whose uncertainty is **proportional** to its expected size, because
both factors of the point (rate × games) are multiplicative. The family carries exactly those two
pieces:

* a **player-specific atom** `π_i = P(Y ≤ 0)`, and
* a **conditional distribution on the ratio scale**: `Y | Y > 0 = ŷ_i · ε`, with `ε` drawn from a
  cell-level empirical distribution. The spread therefore scales with the projection by construction.

Ratio-scale residuals *without* a hurdle were the alternative the spec offered. They are **not**
registered: a cell-pooled atom in `ε` would be the same for every player in a cell, and the refusal
names a *player-specific* atom.

### §2.2 Definition

For a row with point `ŷ ≥ 0` (the predictor's own point, unchanged) and hurdle probability `π`, the
predictive quantile at each of the 19 levels `τ_j ∈ {0.05, …, 0.95}` is

```
q_j = 0                                            if τ_j ≤ π     or  ŷ = 0
q_j = ŷ · Qε_cell( (τ_j − π) / (1 − π) )           otherwise
```

then floored at 0 and sorted, exactly as the parent did.

* **Atom event:** `Y ≤ 0`. A negative realized ROS total (possible from fumbles/interceptions) is
  scored as its own value by CRPS but counts as the atom event for fitting `π`. The count of
  `y < 0` rows is reported.
* **`ŷ = 0` ⇒ a point mass at 0.** This is what a scale family at zero location says, and it is
  kept. The count of such rows, and their realized zero share, are reported (§7).
* **`Qε_cell`** is the empirical quantile function of `ε = y / ŷ`. It is stored on a fixed
  **199-level grid** (0.005 … 0.995) and evaluated by linear interpolation. Arguments below 0.005 or
  above 0.995 are clamped to the end knots.

### §2.3 Parameters, all fixed here

**Ratio table (the conditional spread).**

* Built from training rows with `ŷ > 0` **and** `y > 0`.
* Cells: position × k-bucket {1–3, 4–6, 7–9, 10–12} × tercile of `ŷ`. This is the parent's cell
  structure, unchanged.
* Tercile edges are cut per position on training rows with `ŷ > 0` and carried to test rows.
* The minimum is 40 rows per cell, with the parent's fallback order: (position × k-bucket), then
  (position). The fallback count is reported.
* Real arms use the parent's leave-one-season-out training predictions (the parent's §4.3 rule,
  including the declared in-sample exception for fold 2020). Fixed-parameter predictors use in-train
  predictions (amendment 1 item 3).

**Hurdle probability `π` (the player-specific atom).**

* Model: one logistic regression per (preset, position), fitted on the fold's training seasons with
  target `1[y_preset ≤ 0]`.
* Implementation: `sklearn.linear_model.LogisticRegression(C=1.0, solver="lbfgs",
  max_iter=2000)`. Features are standardized with training mean and SD; a zero-SD feature is dropped
  for that fit and counted.
* **Features.** Every feature is arm-independent and computed by ONE code path from the facts frame
  (§3):
  1. `a0`, the prior availability;
  2. `n / max(t, 1)`, the share of team games played through k;
  3. `1[n = 0]`;
  4. `miss_streak`, the current run of the team's games the player has not appeared in (§3.2);
  5. `log1p(g_rem)`;
  6. `log1p(max(r0_full_ppr, 0))`, the prior per-game rate (the same feature for every preset);
  7. `rookie`;
  8. k-bucket indicators (3 dummies; bucket 1–3 is the reference).
* `π` is out-of-sample for the test season by construction (fitted on training seasons only). It is
  **the same for every predictor in a fold and preset**. The one exception is the matched foil,
  whose `π` is fitted and applied on the **permuted** features (`perm_n`, `perm_miss_streak`). That
  follows from the parent's definition of the foil as "the primary's machinery with (x̄, n, last-3)
  permuted".
* A (preset, position) training set with a single class falls back to that class's training base
  rate (0 or 1). The count is reported. No other regularization, feature, interaction or calibration
  step is added, and **none may be added after a result**.

Nothing in §2 has a free parameter left.

---

## §3 The roster/injury-status covariate: **OUT**, with the asymmetry addressed

### §3.1 Decision

Status at week k (IR / out / questionable / released) is **not** a feature of `π` or of the point.

**Why.** Historical status exists in the lake, as `weekly_rosters.status` and
`injuries.report_status`: nflverse, stamped by the vendor after the fact. The SERVED 2026 prior
carries a different status channel: Sleeper, captured as-of, updated daily (parent §3 bias 2). The
repo has already measured how different those two are. CLAUDE.md, NF-W2d/W2e: *"the 2025
as-of-capture era priced the injury lift ~⅓ of the legacy vendor-stamped figure at RB (+0.042 vs
+0.135)"*.

A `π` fitted on the vendor-stamped history would therefore learn a sharper zero signal than the one
it would receive at serving. The result would be a hurdle that is **over-confident in production**:
a C9-shaped miscalibration that the backtest structurally cannot see. Addressing that asymmetry
properly needs an as-of status history (a PIT capture era). That is a registration of its own, not a
feature added here.

### §3.2 How the asymmetry is addressed instead

`π` uses only features built from `stats_player_week` + `schedules` by the one code path the parent
already uses on both the history and the serving side (parent §2.1, "ONE definition … E7.9"). The
availability signal status would have carried enters through **`miss_streak`**, the facts-table
witness of injury or benching. It is identical in training and at serving.

**`miss_streak` derivation.** It is computed from the frame's own `(n, t)` per player-season,
ordered by k, with `n(0) = t(0) = 0`:

* `team_played(k) = t(k) > t(k−1)`
* `played(k) = n(k) > n(k−1)`
* `streak(k) = 0` if `played(k)`
* `streak(k) = streak(k−1) + 1` if `team_played(k)` and not `played(k)`
* otherwise `streak(k) = streak(k−1)` (a bye week)

A missing k row carries the previous available row forward. The derivation reads only rows ≤ k, and
the parent's `no_future_leak` clause is extended to it (§6).

**Declared limit.** A mid-season team change makes the `t(k) − t(k−1)` step unreliable at the
change week. This is accepted and not corrected.

The foil's `perm_miss_streak` is the **donor's** `miss_streak`, permuted with the same per-(season,
position) draw as `n` (amendment 1 item 7).

The status channel therefore reaches serving only through the served prior's `r0`/`a0`, exactly as
in the parent. Parent §3 bias 2 is carried, not corrected.

---

## §4 The `two_pt` term-set rule, carried

Every predictor is scored on the evaluated term set: the intersection resolved in amendment 1
item 2. On the parent's inputs, `two_pt` resolves as CAPTURED on both sides (parent §13.3), so it is
outside the evaluated set.

**Binding on node 4:** the served artifact scores prior and realized rows on the SAME applied term
set the decisive run evaluated. The manifest records that term list. A term the served board carries
but the history cannot express (for example `proj_two_pt` if it ever appears) is CAPTURED in the
artifact, never applied.

---

## §5 Walk-forward, anchors, bars: unchanged, restated so the values are auditable

**Design:**

* Folds 2020–2025 (6), expanding, k = 1…12.
* CRPS on the 19-level grid; full-PPR 12-team gate.
* PIT seed `20260917 + position index`; bootstrap seed 20260917, 2,000 resamples.
* The PBO precondition is < 0.20 over {incumbent + 3 arms}, with `pbo_application = "field"`.

**Bars, per position:**

| clause | rule |
|---|---|
| C1 | mean per-fold lift over the incumbent > 0, and not collapsed |
| C2 | ≥ 5 of 6 folds |
| C3 | BH q = 0.10 over 5 positions |
| C4 | DSR ≥ 0.95, `n_trials = 3`, with V = the 3 real arms only |
| C5 | beats the matched foil on mean lift, ≥ 5 of 6 folds |
| C6 | every LOSE anchor loses |
| C7 | 80% row coverage ≥ `power_floor(n_player_seasons, 0.80, 0.05)` |
| C8a | the winner does not beat its own oracle by more than 1/10 of the C1 lift with p < 0.05 |
| C8b | oracle ≤ matched-n + 1e-9; a gap within 1e-4 is INACTIVE |
| C9 | pooled randomized-PIT max-decile deviation **≤ 0.05** |

C8a and C8b are different clauses and both are named (PM 2026-09-04).

**Honesty clause (fix-the-spec), fixed here.** The parent already measured that the point beats the
prorated prior at every position in every fold. **This story's fresh confirmatory target is the
interval: C7 and C9** (plus C8, which reads the interval-bearing CRPS). C1–C6 are re-evaluated under
the new predictive and must pass, because the bar is the bar. A pass there is **not** reported as a
new finding about the point. A C1–C6 *failure* under the hurdle **would** be new and is reported as
such.

**Null reporting (the parent's manual discipline, kept).** Every non-shipping position is run
through `cv_power.classify_null` with the parent's arguments. A null whose failed clauses include any
of C5–C9 is reported as **`CONSTRAINT_REFUSED`**, with the binding half named. The classifier's raw
state and text are **kept in the JSON and not acted on**. No fold, season or row re-test trigger is
published for it (NF-D18). A `DSR_UNREACHABLE` reading publishes no variance or data trigger
(NF-W8-0d). The platform `binding_clause` improvement is not built here.

**A reported reference, never a trial and never in V.** `winner@location_shift` is the winner's
point under the parent's construction, scored on the same rows. Its C7/C9 figures and pooled CRPS
are reported beside the hurdle's, so the construction delta is legible. It gates nothing.

---

## §6 Machinery clauses (§9 deltas): all must hold before the decisive run is read

| clause | rule |
|---|---|
| `parent_reproduction` | the harness run with `--interval location_shift` reproduces **every** figure under `result` and `diagnostics` of `nf_ros1_walkforward.json` at max abs difference **0.0** (1e-9 tolerance per the PM 2026-09-04 epsilon rule). This proves the extension changed neither the frame, nor the fits, nor the point. |
| `hurdle_positive_control` | synthetic truth drawn FROM a hurdle (logistic `π` over two covariates, lognormal `ε`), fitted by the §2.3 machinery on a training draw and applied to an independent draw of 20,000 rows. The quantile-grid randomized PIT (amendment 1 item 6, unchanged) reads max-decile deviation **≤ 0.02**. |
| `hurdle_negative_controls` | on the same synthetic truth, (i) the hurdle with `π` forced to 0, and (ii) the parent's location-shift construction, each read **> 0.05**. This shows the instrument can fail on exactly the defect this story fixes. |
| `scale_equivariance` | scaling `ŷ` by c > 0 scales every non-atom quantile by exactly c (1e-9); the atom levels are unchanged. |
| `mixture_monotone` | every applied row's 19 quantiles are non-decreasing, and every level `τ_j ≤ π` is exactly 0. |
| `no_future_leak` | extended to `miss_streak` and to every `π` feature: a week-shifted recompute leaves rows ≤ k unchanged. |
| `incumbent_identity`, `stat_line_coherence`, `renderer_on_real_output` | carried from the parent. The renderer runs on the smoke's real output, including every new §7 section, before the decisive run. |
| `decisive_reproduction` | a second invocation of the decisive run from the committed code reproduces every recorded figure at **0.0**. |

The committed artifacts are regenerated from committed code (the NF-INJ3b D3 rule). The generating
commit is the same as the artifact's commit or an ancestor of it.

---

## §7 Reported diagnostics (never gates)

Everything in parent §10, plus:

* **The mechanism check, predicted in advance.** On the top tercile of projections, report the share
  of rows whose q05 = 0 against the realized `y ≤ 0` share, and the mass in the lowest PIT decile.
  Both are reported for the winner under the hurdle and under `location_shift`.
  * *Prediction:* under the hurdle, the q05 = 0 share falls toward the realized zero share.
  * This is a reading, not a gate. If it does not move, that is a finding about the mechanism.
* `π` reliability: 10 equal-count bins of `π`, predicted vs realized `y ≤ 0` rate, per position.
* Count of `y < 0` rows, and of `ŷ = 0` rows with their realized zero share.
* Hurdle single-class fallbacks, dropped zero-SD features, and ratio-cell fallbacks.
* Per-k and rookie-stratum C9 readings. These are informative only: C9 gates pooled per position.

---

## §8 The name-join rung, tested on real data (the parent's §13.3 open item)

The parent's historical boards matched **every** row by gsis id (`by_name = 0` in every season), so
the name rung has never run on real data. The served 2026 board carries **81** non-D/ST synthetic
ids, all rookies. That count was read 2026-09-17 from `projections.json` `generated_at
2026-09-15T14:21:50Z`, `model_version nfl_fantasy_nf1_5_v1`, and those 81 rows are exactly where the
rung matters.

**What runs.** The parent's `assemble` identity-join code path, unchanged, is applied to (the served
2026 board, `stats_player_week` season 2026 REG at the latest version at read time). The board's
`generated_at`, the Delta version and the REG weeks present are all stamped.

**Authority (independent of the join).**

* **Primary:** `nflverse_draft_picks` season 2026, matched on the board's `draftPick` to the
  draft's overall pick. This key is **name-independent**. It is used only if the board's `draftPick`
  proves to be an overall-pick number that matches 1:1 on position; that is checked and recorded
  before use.
* **Fallback** (undrafted rookies, or if the pick key fails that check): `rosters` season 2026,
  latest week, matched on normalized name + position. This branch shares the normalizer with the
  rung and is **labelled normalizer-dependent**.
* An authority key that resolves to more than one gsis id is `UNVERIFIABLE`.
* Authority table versions are stamped.

**Classification of each of the 81 rows:**

| outcome | meaning |
|---|---|
| `CORRECT` | the rung's realized id equals the authority gsis id |
| `WRONG` | the rung returned an id that differs from the authority's |
| `MISSED` | the authority gsis id has a 2026 REG realized row, but the rung returned none or ambiguous |
| `CORRECT_ABSENT` | the rung returned none, and the authority id has no realized row yet (a real zero) |
| `UNVERIFIABLE` | no unique authority id; the names are listed |

**Criterion, fixed here.** Node 4 may rely on the rung only if **`WRONG = 0` and `MISSED = 0`**.

* A `WRONG` silently credits another player's production.
* A `MISSED` silently serves a rookie who has played as prior-only.

Otherwise the session **stops before node 4 and reports to the PM**. No in-story repair of the
ladder and no fourth absence type is invented here. The test runs and is recorded at node 2 whatever
the modeling verdict. It is a measurement of identity, not of any arm.

---

## §9 On certification: node 4, exactly as parent §8

This section applies only if at least one position clears C1–C9 and the §8 rung criterion holds.

**The artifact.** It is published at
`s3://<api-cache>/fantasy/nfl/ros/<season>/<through_week>/{manifest,players}.json` plus
`…/<season>/current.json`, and it is **born contracted**:

* a Pydantic contract with a validated dump;
* a `missing_declared_fields` write-gate before any `put_object`, dry-run included;
* a served-bytes `content_sha256` read-back;
* an executing `main()` entrypoint smoke with IO stubbed at the boundary.

**What it carries.**

* Certified positions only. `rosP10`/`rosP90` are taken from the hurdle grid (levels 0.10 and 0.90).
* Three distinguishable absences:
  * `not_certified`: an evaluated position that failed;
  * `position_not_evaluated`: D/ST;
  * `no_preseason_prior`: an in-season addition, counted in the manifest.
* `waiverValue` only if parent §7 is evaluated (≥ 2 positions ship) **and** ships. Otherwise it is
  `null` with `waiver_value_not_certified`.
* The ROS stat line goes through `STAT_FIELD`, which makes it paid substrate. The derived paid-set
  diff goes **to the PM before merge**.

**Cadence.** A recurring publish cadence is declared in code with its schedule
`default_status=STOPPED`. **Enablement is an operator step.** The publish itself happens post-merge
from `dev` and is also an operator step.

## §10 On a second refusal

If no position clears, this story closes as a **certified NO**, with the mechanism named from §7's
readings. Consumers keep their stated absences. The PM decides whether a third form is worth
funding. **No in-story iteration past this family** (E2.1-r): no feature, cell, grid or
regularization change after a result.

## §11 Runtime

The parent's decisive run took 2m30s, and this family adds per-(fold, preset, position) logistic fits
and a mixture evaluation. The **smoke** (2 folds) is profiled in-session **first**, by component.
Any full run expected to take more than 2 minutes goes to the operator as a paste-ready command, with
runtime, artifact and success criterion stated. That covers the decisive run, `decisive_reproduction`
and `parent_reproduction`.

⚠️ **Laptop environment note, found while verifying the §2 pins.** A bare `TOKEN` environment
variable holding a non-AWS JWT is picked up by delta-rs as the S3 session token, and every lake read
then fails with `400 InvalidToken`. Every operator command below is prefixed `env -u TOKEN`.

## §12 Out of scope (carried + deltas)

* Everything in parent §11 still applies.
* **Status at week k:** out, per §3; a successor would register it with an as-of capture history.
* The weekly model's outputs.
* D/ST valuation.
* Any serving route, page or WVR1/trade surface.
* Any change to the season board.
* The `cv_power.classify_null` `binding_clause` improvement (platform, carded separately).
* Any second interval family.

---

## §13 Post-run findings

*(appended after the decisive run — never edited above this line)*
