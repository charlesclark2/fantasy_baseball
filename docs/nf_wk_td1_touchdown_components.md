# NF-WK-TD1 — touchdown components in the weekly payload

Story record. Node 1 is the diagnosis and the fork verdict; node 3 carries the
before/after coherence table the PM takes to the operator for the lens-hold decision.

---

## Node 1 — the diagnosis

### The premise, re-measured on the running system (not paraphrased)

The first weekly publish landed **2026-09-15 10:33 CT** at
`s3://credence-prod-s3-api-cache/fantasy/nfl/weekly/2026/2/` — after NF-WK-MT1's
runtime gate recorded a 404 on 09-14. Measured directly on that published blob
(500 players, all `status="projected"`):

| field | non-null | null | non-zero | mean (non-null) |
|---|---:|---:|---:|---:|
| `passAtt`  | 500 | 0 | 215 | 0.7727 |
| `passYds`  | 500 | 0 | 330 | 5.9960 |
| **`passTd`**   | **0** | **500** | 0 | — |
| **`passInt`**  | **0** | **500** | 0 | — |
| `rushAtt`  | 500 | 0 | 486 | 0.9108 |
| `rushYds`  | 500 | 0 | 441 | 3.6981 |
| **`rushTd`**   | **0** | **500** | 0 | — |
| `tgt`      | 500 | 0 | 443 | 0.9648 |
| `rec`      | 500 | 0 | 454 | 0.6295 |
| `recYds`   | 500 | 0 | 447 | 7.2292 |
| **`recTd`**    | **0** | **500** | 0 | — |

MT1's premise is CONFIRMED and this is the same artifact its gate read — the
payload's top rows are Trey McBride (11.165), Christian McCaffrey (10.455),
Bijan Robinson (10.117), Jahmyr Gibbs (9.341), Jaxon Smith-Njigba (8.767), which
are the players the spec names.

### Where the four nulls come from — the mechanism, end to end

The emission loop in `weekly_serving.build_players` iterates
`C.WEEKLY_COMPONENT_FIELD`, which carries **all eleven** components (it is derived
from `WEEKLY_COMPONENT_STAT_KEY`, and `resolve_component_fields` RAISES on an
unmapped one). So all eleven keys are written on every row; four of them take the
`else` branch and land as `None`:

```python
elif len(comp_idx) and gid in comp_idx.index and col in comp_idx.columns:
    row[field] = round(float(comp_idx.loc[gid, col]), 4)
else:
    row[field] = None                      # ← the four TD/INT keys, every row
```

`col in comp_idx.columns` is false because `weekly_projection.fit_component_head`
silently skips them:

```python
for comp in components:                    # components = WP.COMPONENTS, all 11
    if comp not in train.columns:          # ← the four TD/INT labels are not on the matrix
        continue
```

And the labels are not on the matrix because exactly two selection lists drop
them, one per source:

* `weekly_frame.attach_labels` keeps four optional stat columns —
  `("carries", "targets", "attempts", "receptions")` — the VOLUME line.
* `weekly_projection.engineer_features` merges three —
  `comp_cols = ["passing_yards", "rushing_yards", "receiving_yards"]` — the YARDAGE line.

4 + 3 = the seven populated fields, exactly. Confirmed on the cached matrices:

| matrix | component label columns present | missing |
|---|---|---|
| `nf_w1_weekly_matrix` (the serving shape) | **7** — attempts, passing_yards, carries, rushing_yards, targets, receptions, receiving_yards | **4** — passing_tds, passing_interceptions, rushing_tds, receiving_tds |
| `nf_w6_stat_matrix` (research, after `EM.attach_td_labels`) | 10 | passing_interceptions |
| `nf_w6d_stat_matrix` (research, after `SDD.attach_extra_labels`) | **11** | — |

⭐ **The four labels are already READ FROM THE LAKE on every serving build and
dropped two functions later.** `weekly_serving._load_sources` delegates to
`run_nf_w1_weekly_bakeoff.load_sources_w1`, whose stats query selects
`passing_tds, passing_interceptions, rushing_tds, receiving_tds` by name. No new
lake read, no new query, no new source is implied by emitting them.

### What the contract's null keys were reserved for

`3298b31b` (NF-C6-PH2, 2026-09-05, "the weekly served contract, declared before any
build code") declared all eleven keys in one go, because "the paid set is DERIVED
from `projection_fields.STAT_FIELD` via a SEMANTIC component map". The keys were
reserved for precisely what they name — the champion's own eleven raw component
lines. The declaration was complete; the production was not. This is the
`NF-C0e` "declaration outruns its production" class, verbatim.

### VERDICT: fork (A) — an EMISSION story

The decisive evidence is a two-sided smoke that calls
`weekly_projection.fit_component_head` **unchanged, with zero edits to any model
code**, on the NF-W6d matrix (train 2016–2023 = 67,288 rows; score 2024 wk 2 = 506):

* **ARM 1** — the four TD labels dropped from the frame, i.e. today's serving
  matrix. Emits exactly `[attempts, carries, passing_yards, receiving_yards,
  receptions, rushing_yards, targets]`. **Reproduces the published payload's seven.**
* **ARM 2** — the labels present, same function. Emits **all eleven**.
* **max |ARM 1 − ARM 2| over the seven already-served components = `0.000e+00`.**
  Carrying the TD labels cannot perturb what is already served; the change is
  additive in the strict sense, not merely in the declared one.

The TD means ARM 2 produces are sensible on each position's real channels
(head mean vs realized on the same 506 rows):

| pos | stat | head mean | realized | ratio |
|---|---|---:|---:|---:|
| QB | passing_tds | 0.6085 | 0.4359 | 1.40 |
| QB | passing_interceptions | 0.3438 | 0.3333 | 1.03 |
| RB | rushing_tds | 0.1501 | 0.1463 | 1.03 |
| RB | receiving_tds | 0.0390 | 0.0407 | 0.96 |
| WR | receiving_tds | 0.1550 | 0.1302 | 1.19 |
| TE | receiving_tds | 0.0905 | 0.0265 | 3.41 |

Off-channel cells (QB `receiving_tds`, RB/WR/TE `passing_tds`) come back at
1e-3 or below against a realized 0.0 — the head correctly says "essentially
never". (Their ratio column is meaningless by construction and is omitted rather
than printed as a large number against a zero denominator.)

**So the quantity exists, is extractable today, and needs no new model.** There
is no new learner, no new feature set, no new hyperparameter, no selection, and
no new form: `fit_component_head` is ONE head with a per-component loop, and
`WP.COMPONENTS` has named all eleven since `14fb21a9` (NF-W1). What is missing is
four label columns on the serving matrix, read from a feed that already carries
them, by the identical merge that already carries the three yardage columns.

Two further pieces of the research record confirm the quantity is a real,
already-exercised one rather than a novel output:

* `efficiency_marginals.fit_head_mean` is documented as "byte-identical
  construction to `WP.fit_component_head`" and is what NF-W6 fitted **per TD stat**
  to obtain the incumbent baseline its ceiling gate measured against. NF-W6's four
  TD-NO cells were closed because a distribution beat that baseline by only
  0.07–0.38% — a measurement that only exists because the champion head's TD mean
  was computed.
* `EM.attach_td_labels` and `stat_distributions_d.attach_extra_labels` are
  certified, guard-hardened merges of exactly these four labels onto exactly this
  matrix, whose own docstring says they are "exactly the existing yards/receptions
  attach in `WP.engineer_features`".

### What fork (A) does NOT license — stated so it is not read as more than it is

* The component head is stamped `component_head_status = "advisory_ungated"` and
  **that is unchanged**. The four new components inherit exactly the certification
  the seven served ones have, which is none. This story adds four ungated numbers
  beside seven ungated numbers; it does not promote any of them.
* The certified per-stat DISTRIBUTIONS (NF-W6c/W6d, a different registry target)
  stay staged challengers with no consumer. Nothing here serves them.
* **An observation, recorded not fixed:** `fit_component_head` ends in
  `np.clip(m.predict(...), 0.0, None)`. On a zero-heavy target the clip truncates
  negative predictions to zero, so `E[clip(pred)] ≥ E[pred]` — a structural upward
  bias. QB `passing_tds` at 1.40× and TE `receiving_tds` at 3.41× on this one
  test week are consistent with it (n=78 and n=113 against realized means of 0.44
  and 0.03, so the single-week ratios are noisy and are not by themselves a bias
  measurement). This belongs to the head, not to this story's plumbing, and is
  carried to the closeout rather than corrected here.

---

## Node 3 — the coherence measurement

### The artifact, captured before it could rotate

The weekly publish runs daily and re-projects, so the before side is a **committed
capture**, not a live read: `ablation_results/nf_wk_td1_before_week2_players.json`,
season 2026 week 2, `generated_at 2026-09-15T15:32:59+00:00`, 500 players, sha256
`6782c40f…`. A before/after measured across two publishes is not a controlled
comparison — it is the NF-INJ2c market-vintage failure in a new costume.

Method is NF-WK-MT1's, verbatim, and deviating from it would break comparability:
component sum `= passYds*0.04 + rec*1.00 + recYds*0.10 + rushYds*0.10` (plus the four
TD/INT terms once they exist), `None` counts as 0.0, `gap = head − components`, full-PPR
weights because the head is full-PPR-native. Instrument:
`run_nf_wk_td1_coherence.py`. It reproduces MT1's top-24 table to the digit.

### BEFORE (measured)

| POS | tier | n | mean head | mean gap | med \|gap\| | p95 \|gap\| | max \|gap\| |
|---|---|---:|---:|---:|---:|---:|---:|
| QB | top24 | 24 | 3.158 | **−0.576** | 0.884 | 2.201 | 2.430 |
| QB | all | 88 | 1.345 | −0.343 | 0.285 | 1.663 | 2.430 |
| RB | top24 | 24 | 6.894 | **+1.140** | 1.472 | 2.727 | 3.083 |
| RB | all | 113 | 2.585 | +0.235 | 0.227 | 1.904 | 3.083 |
| WR | top24 | 24 | 6.108 | **−0.359** | 0.727 | 2.291 | 4.136 |
| WR | all | 179 | 2.057 | −0.177 | 0.277 | 1.210 | 4.136 |
| TE | top24 | 24 | 4.359 | **+0.452** | 0.742 | 1.538 | 4.126 |
| TE | all | 120 | 1.433 | +0.040 | 0.173 | 1.174 | 4.126 |
| **ALL** | pooled | 500 | | **−0.061** | 0.233 | | 4.136 |

⚠️ **The pooled figure is the single most misleading way to report this.** The
per-position gaps carry opposite signs and cancel to −0.061, which reads as "nothing to
see". Report the signed per-position table.

⚠️ **The −0.77 in the spec's premise is a DIFFERENT artifact.** NF-C6-PH2's recorded
`mean_signed_diff = −0.7709` (n=503) was measured on a locally-staged payload during
that story, under the opposite sign convention (`components − head`). On the published
artifact the same function returns `+0.0609`. Nothing is wrong with either number; they
are different builds, and the story's before side is the published one.

### The registered hypothesis is REFUTED — with the mechanism

> HYPOTHESIS (registered forward): the missing TD expectation explains most of the
> incoherence.

It does not, and the reason is arithmetic rather than a matter of degree.

**If both heads were coherent, the seven served terms should sit BELOW the head by
exactly the TD share.** Touchdown terms are 22.1% of realized PPR (QB 33.3%, RB 22.8%,
WR 17.2%, TE 18.8%; the eleven-term reconstruction matches realized total PPR with a
mean residual of +0.0242, so the decomposition is essentially exact). What the payload
actually does:

| POS | tier | TD share | mean head | gap EXPECTED if coherent | gap MEASURED | **7-term excess** |
|---|---|---:|---:|---:|---:|---:|
| QB | top24 | 32.8% | 3.158 | +1.035 | −0.576 | **+1.611** |
| QB | all | 32.8% | 1.345 | +0.441 | −0.343 | +0.784 |
| RB | top24 | 22.6% | 6.894 | +1.559 | +1.140 | +0.419 |
| RB | all | 22.6% | 2.585 | +0.585 | +0.235 | +0.350 |
| WR | top24 | 17.2% | 6.108 | +1.052 | −0.359 | **+1.411** |
| WR | all | 17.2% | 2.057 | +0.354 | −0.177 | +0.531 |
| TE | top24 | 18.7% | 4.359 | +0.817 | +0.452 | +0.365 |
| TE | all | 18.7% | 1.433 | +0.269 | +0.040 | +0.228 |

⭐ **The excess is positive in all eight cells. The served component line is not SHORT of
the points head by the touchdown value — it is running HOT by roughly that amount.** The
payload's near-zero pooled coherence was a coincidence of two offsetting errors, not
evidence of a healthy substrate. Emission removes one of them and leaves the other
exposed, so the measured gap will get WORSE.

⚠️ **Which head is wrong is NOT determined by this measurement.** A gap is symmetric: the
component head may over-project its seven terms, or the points head may under-project
the total. Attributing it needs realized outcomes for the week, which do not exist until
it is played. Stated as a disagreement, not an indictment.

### Forward, per position — sign first, then magnitude

MT1's sign-certainty argument, carried and extended. `gap = head − components`, and the
component head clips at 0, so every emitted TD term is ≥ 0:

* **WR — sign-certain, no measurement needed.** Only `recTd` applies and it is
  positive-weighted, so emission can only push components further above a head they
  already exceed. WR coherence gets worse, at any magnitude.
* **RB, TE — direction certain (down), magnitude decides.** Their gaps are positive, so
  emission moves them toward zero; whether they land on it or overshoot is a magnitude
  question.
* **QB — genuinely ambiguous a priori**, because `passInt` is negative-weighted. MT1
  explicitly declined to claim a sign here and asked for it to be measured separately.
  **Measured: the interception penalty does NOT dominate.** Per passing yard the realized
  net is `4×0.00622 − 2×0.00321 = +0.0185`, strongly positive. QB's gap gets worse, not
  better, and the missing INT penalty does not explain it.

**Magnitude — a labelled ESTIMATE, not the measurement.** Applying realized per-position
TD-per-yard ratios to the payload's own projected yardage (a lower bound in |Δ|, because
the head's clip-at-zero biases low-projected rows up):

| POS | tier | gap now | est ΔTD PPR | est gap after | verdict |
|---|---|---:|---:|---:|---|
| QB | top24 | −0.576 | +1.913 | −2.489 | WORSENS |
| QB | all | −0.343 | +0.861 | −1.203 | WORSENS |
| RB | top24 | +1.140 | +1.914 | −0.773 | improves (overshoots past zero) |
| RB | all | +0.235 | +0.754 | −0.519 | WORSENS |
| WR | top24 | −0.359 | +1.338 | −1.697 | WORSENS |
| WR | all | −0.177 | +0.480 | −0.656 | WORSENS |
| TE | top24 | +0.452 | +0.919 | −0.467 | WORSENS (overshoots) |
| TE | all | +0.040 | +0.330 | −0.290 | WORSENS |

Seven of eight cells worsen; the one that improves overshoots past zero — exactly the
shape MT1 predicted for the positive-gap positions.

⛔ **NOTHING IS RESCALED, AND NOTHING SHOULD BE (MH2.2).** The residual stays material and
changes sign by position. That is a finding about two independent heads, to be reported
— not a defect in this story's plumbing to absorb. Forcing the component sum toward the
head would fabricate agreement between two models that genuinely disagree.

### The decisive measurement is an OPERATOR step

The magnitudes above are an estimate. The controlled measurement needs one staging
rebuild (~9 minutes, >2 min ⇒ operator). ⭐ **Both sides come from that ONE build**, which
dissolves the vintage problem entirely: the after side is the payload with TD terms, and
the controlled before side is the SAME payload with the TD terms dropped from the sum —
valid because the ARM1/ARM2 smoke measured the seven served components **bit-identical**
with and without the TD labels (max \|diff\| `0.000e+00`). The committed 2026-09-15
capture then serves as an independent vintage-drift diagnostic rather than as the before
side of the arithmetic. `run_nf_wk_td1_coherence.py --after …` computes all of it.

---

## ⚠️ A LARGER DEFECT FOUND WHILE MEASURING — reported, not fixed, and NOT this story's

The coherence numbers above are measured on a payload whose **absolute level is wrong by
roughly 3×**.

⚠️ **CORRECTED FROM MY OWN FIRST CUT.** I first compared the served projection against the
*realized top-24 by realized points*, which gave 0.17–0.37 — that comparison has a
**selection confound** and overstates the effect: the realized top-24 selects the 24 who
actually boomed, which no unbiased projection can or should match. The clean comparison
is **population-matched** — both sides are game-day-rostered QB/RB/WR/TE player-weeks
(~470–500 per week), and an unbiased projection's MEAN over a population must equal that
population's realized mean:

| POS | n served | mean PROJECTION | n realized | mean REALIZED | ratio |
|---|---:|---:|---:|---:|---:|
| QB | 88 | 1.345 | 13,462 | 6.549 | **0.205** |
| RB | 113 | 2.585 | 21,895 | 5.555 | 0.465 |
| WR | 179 | 2.057 | 31,110 | 5.743 | 0.358 |
| TE | 120 | 1.433 | 18,086 | 3.565 | 0.402 |
| **ALL** | **500** | **1.901** | **84,553** | **5.357** | **0.355** |

⭐ **AND THE BAND NAMES THE MECHANISM PRECISELY.** Every one of the top ten projections
carries **`fpP10 = 0.00`** against a plausible `fpP90` (McCaffrey 0.00 / 10.45 / 27.17;
McBride 0.00 / 11.16 / 24.61). An elite running back's 10th percentile is not zero points.
The p90 ceilings are roughly right, so the conditional-on-playing half of the champion's
hurdle is broadly intact — **what is broken is the ZERO ATOM**, which is exactly what a
whole training week of fabricated zeros would inflate. The level collapse is that atom
dragging every mean toward zero, not a uniform scale error.

**The mechanism is provable from the manifest alone.** It records
`stats_as_of: "2025-W18"` (the newest week in the stats feed) beside
`train_through: 2026 wk 1` (the newest week in the training matrix). Both are computed
correctly. Together they say: the 2026 week-1 training rows have **no stat rows**, so
`weekly_frame.attach_labels` fills `fantasy_points = 0.0` for every one of them under the
retained-zero convention. The model therefore trains on a whole week of fabricated zeros,
and every player's `prior_week_box__ppr_l1` — last week's points — is 0.0 on the week-2
slate.

**Root cause, measured:**

```
ROLL_FORWARD_SOURCES = ['rosters', 'weekly_rosters', 'schedules', 'depth_charts',
                        'injuries', 'nflverse_draft_picks', 'nflverse_combine']

stats_player_week: in roll-forward = False   tier='nflverse' on_demand=False ⇒ ELIGIBLE
snap_counts:       in roll-forward = False   tier='nflverse' on_demand=False ⇒ ELIGIBLE
```

Neither feed is referenced anywhere in `pipeline/`. **The two feeds the weekly model
actually trains on have no scheduled ingest at all**, while the feeds it does roll
forward (rosters, schedules) are current — which is exactly why `rosters_as_of` reads
`2026-W2` and `stats_as_of` reads `2025-W18`. Both are free, non-`on_demand` nflverse
sources, so they are eligible for the existing weekly roll-forward.

This is the `stg_ref_players` "a table with NO SCHEDULED WRITER is a silent-staleness
bomb" class, applied to the weekly model's training substrate, and it will hold for
**every week of the 2026 season** until the sources are added.

Consequences for reading this record: the SHAPE findings above (the sign of every Δ, the
positive 7-term excess, the refuted hypothesis) are ratios and are robust to a roughly
uniform level error. The ABSOLUTE magnitudes are not, and should be re-read after the
level defect is fixed. ⛔ Not fixed here — it is a different story, and the same
discipline that forbids rescaling the coherence residual forbids reaching outside this
story's scope to fix a model-input defect.

---

## ⏭️ Operator handoff

⛔ **Nothing in this story publishes.** No `--publish`, no `deploy.sh`. The weekly artifact
is written by the box job, and the API Lambda is untouched (`app/backend` changes are
none — the contract already declared the keys).

### Step 1 — merge PR #1137 (branch `nf-wk-td1` → `dev`), CI green.

### Step 2 — the node-3 measurement. **LAPTOP**, ~9 minutes, stages locally, publishes nothing.

⭐ `--season 2026 --week 2` is load-bearing: it pins the same target week as the committed
capture. Both sides of the controlled comparison come from THIS one build.

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
git checkout dev && git pull
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving \
  --season 2026 --week 2 \
  --out quant_sports_intel_models/football/nfl/fantasy/artifacts/weekly_serving
```

**Success looks like:** it exits 0 and logs
`component line: 11 field(s) non-null on all N projected rows` plus
`[METRIC] weekly_component_fields_complete=11`. It writes
`artifacts/weekly_serving/2026/2/players.json`. ⛔ If it raises
`… component value(s) are NULL on projected players`, the emission did not take —
that refusal is the point and should stop the run.

### Step 3 — the before/after table. **LAPTOP**, seconds.

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_td1_coherence \
  --before quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_wk_td1_before_week2_players.json \
  --after  quant_sports_intel_models/football/nfl/fantasy/artifacts/weekly_serving/2026/2/players.json \
  --out    quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_wk_td1_coherence.json
```

**Success looks like:** `AFTER TD non-null counts` shows all four fields at the full row
count (the before side reads 0/0/0/0), and it prints the controlled pair
(`after_without_td` vs `after`) plus a per-position Δ table. **That Δ table is what the PM
takes to the operator for the lens-hold decision.** Expect most cells to move the gap
further negative — the refutation in node 3 predicts it, and it is a finding rather than
a failure.

### Step 4 — publish, only if the PM wants the TD line live.

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python -m quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving \
  --s3-bucket credence-prod-s3-api-cache --publish
```

⚠️ This is the **BOX**, it reaches the LIVE prod api-cache, and it re-resolves the target
week (it will build whatever week is current, not week 2). The scheduled
`sports_nfl_weekly_serving_job` runs exactly this daily, so **merging alone will put the
TD line on the wire at the next scheduled fire** — that is the decision to make
deliberately, not the command.

### Not in this story, and worth its own spec

Follow-up (1) in the spec closeout: `stats_player_week` and `snap_counts` have no
scheduled ingest, which is holding every served weekly projection ~3–6× low. That is a
larger defect than the one this story fixes, and it bounds how this story's absolute
magnitudes should be read.
