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
