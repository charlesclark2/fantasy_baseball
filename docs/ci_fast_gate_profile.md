# Fast-gate profile + shard design (2026-07-27)

Story: *tech-debt / CI hygiene — the fast gate is the merge bar every session runs, so shaving it
compounds across all tracks.* The card's own instruction was **measure first, don't assume "split
it" is the fix.** This is the measurement.

Machine: laptop, 11 cores, `uv run pytest`, pytest 9.0.3 + pytest-xdist 3.8.0 (the only plugin).

---

## 1. Baseline — what the gate actually cost

| Configuration | Wall | CPU | Notes |
|---|---|---|---|
| `-m "not slow"` **serial** | **91.0s** | 93s | 2,358 tests |
| `-m "not slow" -n auto` (11 workers) | **45.1s** | **287s** | the documented merge bar |
| `-m "not slow" -n 6` | 37.1s | — | |
| `-m "not slow" -n 4` | **35.5s** | — | *faster than `-n auto`* |
| `--collect-only` (1 process) | 7.5s | — | collection alone |
| slow gate (`-m slow -n auto`) | 133.6s | — | 38 tests |

**CLAUDE.md's "~15s with `-n auto`" was stale.** It was written at E11.13 when the suite was a
fraction of its current size; at ~2,360 tests (+~90/day) the real number was 45s.

### The decisive ratio

`-n auto` burns **287s of CPU to do 91s of work**, and adding workers past ~4 makes it *slower*.
That is the signature of a fixed per-process cost, not of slow tests.

- 194s of CPU overhead ÷ 11 workers ≈ **17.6s per worker** of pure startup.
- Collection is 7.5s/process; timing every test module's import directly gives **11.0s** of
  module-import time across 175 modules.

Every xdist worker imports **all 175 test modules** before running its ~1/11th share. Collection
is duplicated N times while the work is divided by N — so past a handful of workers you are
paying more to collect than you save by parallelising.

### Ruling out the alternatives the card listed

- **(a) slow tests leaking past the `@slow` >5s rule** — **NO.** Slowest single fast-gate test is
  **4.53s** (`test_ncaaf_team_strength`), under the threshold. Marker hygiene was already clean;
  `--strict-markers` is on in `pyproject.toml`. Nothing was reclassified, so **no coverage moved**.
- **(b) collection / import overhead** — **YES, this is it** (above).
- **(c) genuine breadth** — **YES**, for the execution half: 75.4s spread across ~440 measurable
  tests, top file only 10.2s. There is no single hog to delete.
- **(d) `-n auto` not engaging** — it engages; it **anti-scales** past ~4 workers on an 11-core box.

### Where the execution time actually sits (serial, per file)

```
10.20  test_ncaaf_team_strength.py        3.39  test_boto3_credential_lint.py
 7.79  test_copula.py                     3.37  test_totals_distribution.py
 6.68  test_ncaaf_college_nfl_translation 2.22  test_the_board_reader_guard.py
 5.96  test_perside_bakeoff.py            1.96  test_milb_player_xref.py
 5.57  test_milb_mle.py                   1.85  test_phase15_straggler_repoint.py
 5.46  test_ncaaf_game_distribution.py    1.81  test_retired_source_guard.py
 4.65  test_ncaaf_freshman_projection.py  …long tail: 6,653 tests under 5ms each
```

---

## 2. A real defect the profile surfaced

`scripts/predict_today.py` ran **`_calibrator = _load_calibrator()` at module scope** — a live
**S3 GET on import**. Eleven test modules import `predict_today`, so *every xdist worker fired a
network round-trip during collection*, in a suite whose stated invariant is that all external IO
is mocked. It also meant anything merely importing the module paid for a download.

Fixed: lazy + memoized `_calibrator()` accessor. Scoring behaviour is unchanged (still fetched
once per process), and `main()` resolves it up front so the `[calibrator] loaded from S3: …` line
still appears near the top of the run log exactly as before. Pinned by
`test_fast_gate_hygiene.py::test_predict_today_does_not_fetch_the_calibrator_at_import`.

---

## 3. The `-n auto` isolation work

The card flagged `test_retired_source_guard::test_known_unresolved_list_stays_honest` as a known
flake. **It is now inert:** commit `18c1c4a` (E11.20 phase-2b) emptied `KNOWN_UNRESOLVED` to
`set()`, so the test iterates nothing and cannot fail on content. It did not reproduce in **7
consecutive full `-n auto` runs**. Reporting that honestly rather than claiming a fix.

The underlying *class* was real and was found elsewhere. Two test modules mutated global
interpreter state **at import time** — which pytest does during collection, before any test runs,
so it leaks into every other test in that worker:

1. `test_best_price_e9_11.py` and `test_serving_timestamp_coercion.py` each installed
   `MagicMock`s into `sys.modules["snowflake.connector"]` / `sys.modules["dotenv"]` and **never
   removed them**. Worse, both were guarded by `if stub not in sys.modules`, making the behaviour
   depend on whether some *other* module imported `dotenv` first — i.e. on collection order. That
   is exactly the "passes in isolation, fails in the full run" shape.
   → replaced by the shared restore-on-exit loader `betting_ml/tests/_serving_store_loader.py`.
2. `test_e11_1_w12_sensor_fire.py` called `os.environ.setdefault(...)` at module scope.
   → moved into an autouse `monkeypatch` fixture (reverted per test).

Both were found *by* the new guard, not by hand:
`test_fast_gate_hygiene.py::test_module_does_not_mutate_global_state_at_import` AST-scans every
test file for module-level `sys.modules[...]` / `os.environ[...]` mutation and for `os.chdir` /
`os.environ.setdefault|update|pop`. This is what makes the suite safe to shard — a test whose
result depends on what else shares its worker would otherwise depend on which shard it lands in.

---

## 4. The shard design

Breadth is genuine, so the gate is sharded by **domain** (`scripts/ci_shards.py` = single source
of truth). Domain rather than round-robin so a red check localises the blame before you open the
log.

| Shard | Files | Est. work |
|---|---:|---:|
| football (NFL/NCAAF/fantasy/draft) | 27 | 32.3s |
| baseball-models (copula, per-side, totals, pricing) | 34 | 27.1s |
| guards (repo-scanning lints + contracts) | 22 | 11.6s |
| prospect-milb (MiLB/E7 translation MLEs) | 7 | 11.6s |
| serving-ops (Dagster ops, sensors, lakehouse, writers) | 74 | 5.4s |
| **core** (computed catch-all) | 13 | 1.6s |

Longest shard **32.3s vs 89.5s serial**. `prospect-milb` exists purely for balance — with MiLB
folded in, `baseball-models` was 38.7s and set the wall-clock.

### Coverage cannot escape — the property that makes this safe

Splitting a suite across jobs introduces a failure mode the single job never had: a file that
belongs to no shard just stops running, and the merge bar goes green anyway. Two defences:

1. **`core` is computed, not listed** — defined as "every collected test file not claimed by a
   named shard". A new test file joins the merge bar automatically, with zero maintenance.
2. **`test_fast_gate_hygiene.py` proves it** — exact partition (no unclaimed, no doubled), union
   equals the whole suite, no empty shard, no rotted/shadowed prefix rule, and the CI matrix
   lists every shard name.

Verified empirically: the union of the six shards' collected **node IDs** is byte-identical to the
unsharded run — 2,569 IDs, **zero missing, zero duplicated**.

### Branch protection — and a finding

The matrix runs as `unit-tests-shard`, and a roll-up job **keeps the exact name
`Unit Tests (fast gate)`** and fails if any shard did (treating `skipped` as pass, for
frontend/docs-only diffs). Renaming a required check to a matrix would leave it permanently
pending — the same skipped-but-required gotcha the `changes` job works around.

⚠️ **But verified 2026-07-28: there is no branch protection to satisfy.**
`gh api repos/:owner/:repo/branches/main/protection` → 404 *"Branch not protected"*, and
`…/rulesets` → `[]`. So "both gates are required for merge" — asserted in CLAUDE.md and the
E11.13 handoff since 2026-06-25 — is **convention, not enforcement**; nothing mechanically blocks
a red merge. This is the repo's own *documented-but-never-set* landmine class (cf. `W7B_LAKEHOUSE_S3`
documented as cut over while unset on the box), and E11.13's roadmap entry carries an unactioned
"⏭️ Operator: add the slow-tests check to BRANCH PROTECTION".

The naming discipline above is kept regardless: it costs nothing and makes enabling protection a
one-click change with zero CI rework. **Enabling it is an operator decision, not done here.**

---

## 5. Result

| | Before | After |
|---|---|---|
| Fast gate, `-n auto` | 45.1s / 2,358 tests | **38.7s / 2,575 tests** |
| Longest CI unit of work | 91s serial (one job) | **32.3s** (longest shard) |
| Network IO during collection | 1 live S3 GET per worker | none |
| Import-time global-state leaks | 3 | 0, enforced by a guard |

**Worker tuning, re-measured after the fixes.** The anti-scaling largely closed once the
import-time S3 fetch was gone — `-n auto` 38.7s vs `-n 4` 38.3s is a tie on wall-clock. But
`-n 4` gets there on **123s of CPU against 261s**, so it is the better local default on a machine
doing anything else. CI keeps `-n auto` (runners are 2–4 cores, where auto is already small).
`ci.yml` is the only workflow that runs pytest, so `-n auto` is already used everywhere.

That closure is itself the lesson: ~1s per worker of module-level network IO was a material share
of an 11-worker gate. **If the gate creeps back up, suspect a new expensive module-level import
before suspecting a slow test.**

Target was <~60s; the gate is under it on both axes, and sharding keeps it there as the suite
grows (~+90 tests/day). Nothing was deleted or reclassified — the after-run carries **more** tests
than the before-run.

---

# TD2 — the slow gate (2026-07-27)

## 6. Two premises corrected before any fix

TD1's handoff said the slow gate was "~134s dominated by a single 83s test." A serial profile
(`-m slow -p no:xdist --durations=0`, **283s total**) corrected both halves:

- **It is not one test.** The top three are *siblings in the same class* —
  `TestCalibration::test_too_tight_dispersion_fails_flatness` (63.0s),
  `::test_pit_uniform_when_correctly_specified` (55.4s), `::test_calib_80_at_or_above_floor` (55.3s)
  = **174s, 61% of the gate.** The 83s figure was a `-n auto` reading distorted by contention.
- **The cost is one systemic thing, not per-test bloat.** Every heavy test bottoms out in
  `scipy.stats.nbinom.ppf`, measured at **~0.48M inversions/s** and exactly linear in
  `n_games × n_draws`. The tests run the *production* sampler at ~400× production scale (6000
  games × 2000 draws × 2 sides = 24M inversions ≈ 55s). Same pattern in `perside_bakeoff` (23.6s),
  `derivative_model_gate` (47.8s), `line_microstructure` (16s), `prop_pricing` (13s).

## 7. "Do we even run Monte-Carlo live?" — half yes, and the half matters

The operator asked whether any of this guards live code. Checked by importer, not by memory:

- **YES for `totals_distribution`.** `write_serving_store.py:2595` → `totals_serving
  .build_totals_distribution_payload()` → `draw_independent_samples(n_draws ≤ 10_000)` **per game,
  ungated, on the HALT-tier daily serving write** — E2.7's predictive-total distribution on the
  totals pick-detail page. The 174s `TestCalibration` block guards live production math and
  **stays on the merge bar.**
- **NO for the research harnesses.** `derivative_model_gate`, `line_microstructure`,
  `bakeoff_perside`, `f5_distribution` have **zero importers** under `scripts/`, `app/`, or
  `pipeline/` — only their own bake-off scripts. ~94s (33%) of the required gate guarded code that
  nothing runs daily.

`prop_pricing` (13s) is fit-time-only by the same test, but it produces a **served** K-projection
bundle, so it was deliberately **kept on the merge bar** — 13s is not worth the risk asymmetry.

## 8. Fix: tier, then trim (both were needed)

**Tier.** A `research` marker (registered in `pyproject.toml`) moves the four harness families off
the required job (`-m "slow and not research"`) into a nightly non-blocking workflow
(`research_tests.yml`, `-m research`). `uv run pytest -m slow` still runs everything locally — the
tier only changes what blocks a merge. Same HALT/WARN shape the pipeline ops use.

⚠️ **Tiering alone bought almost nothing: 106s → 108s.** Wall-clock was pinned by a single 63s
test, so removing 94s of *parallel* work moved nothing. It saves CI minutes and clarifies the bar;
it is not the speed fix. Worth remembering — on an `-n auto` job, only the critical path matters.

**Trim.** `TestCalibration` `n_draws` 2000 → 500, `n_games` **unchanged at 6000**. The asymmetry is
the whole point: decile-frequency SE is `sqrt(0.1·0.9/n_games)` = 0.0039 at n=6000, so the 0.025
tolerance sits ~6.5 SE out — **games are the power knob**, draws only refine a per-game CDF that is
already far finer than an integer-valued total needs. **No tolerance was weakened.**

15-seed sweep at fixed n=6000 (sample columns are i.i.d., so slicing k columns of one draw is
distributionally identical to drawing k):

| n_draws | correct-spec pass | worst decile dev (tol 0.025) | too-tight DETECTED | its min dev | calib_80 range |
|---:|---:|---:|---:|---:|---|
| 500 | 15/15 | 0.0113 | 15/15 | 0.0432 | 0.8168–0.8370 |
| 400 | 15/15 | 0.0125 | 15/15 | 0.0437 | 0.8145–0.8377 |
| 300 | 15/15 | 0.0148 | 15/15 | 0.0440 | 0.8153–0.8363 |
| 200 | 15/15 | 0.0137 | 15/15 | 0.0442 | 0.8147–0.8388 |

200 would still pass; **500 is the deliberately conservative pick** on live serving math.

**Re-proven to fail** (the "a gate must be shown to fail" discipline) at the trimmed budget —
two-sided, on both assertions:

| predictive vs truth r=3.7 | is_flat | max decile dev | calib_80 | verdict |
|---|---|---:|---:|---|
| correct (r=3.7) | True | 0.0042 | 0.839 | passes |
| **too tight (r=8.5)** | **False** | 0.0485 | **0.762** | rejected |
| **too fat (r=1.5)** | **False** | 0.0653 | **0.931** | rejected |

## 9. TD2 result

| | Before | After |
|---|---|---|
| Required slow job (`-n auto`) | 106s / 38 tests | **33s / 26 tests** |
| Slow suite serial | 283s | ~60s required tier |
| `TestCalibration` (3 tests) | 174s | **44.5s** |
| Research harnesses | blocking every merge | nightly, non-blocking (52s) |
| Tolerances weakened | — | **none** |
| Tests deleted | — | **none** (38 = 26 + 12) |

Combined with TD1, the full merge bar (fast + slow, run in parallel) is now bounded by the ~38s
fast gate rather than the ~106s slow gate.

### Still open

`derivative_model_gate` (48s) and `perside_bakeoff` (24s) were **tiered, not trimmed** — they carry
the same `nbinom.ppf` cost and the same trim would likely work, but they now run nightly where the
runtime does not block anyone. Trim them only if the nightly job itself becomes a problem.

---

## TD3 (2026-08-20) — the slow gate was mostly COLLECTION, not Monte-Carlo

**Reported symptom:** the slow gate had crept to **7m19s** and was delaying merges. The obvious read
— "the Monte-Carlo tests are too slow" — is **wrong**, and the measurement says so.

### What was actually happening

`pytest -m "slow and not research"` with no path arguments collects `testpaths`. Measured:

| | |
|---|---|
| tests IMPORTED to find the 79 slow ones | **10,659** |
| collection cost | **11.04s** — and xdist pays it **once per worker** |
| serial CPU of the actual tests | 256s |
| local wall clock, `-n 4` | 106.8s |
| CI wall clock | ~440s ⇒ **CI is ~4× slower per core** |

This is the same duplicated-collection tax documented above for the fast gate, but it bites far
harder here: the fast gate at least *runs* most of what it imports, while the slow gate imported the
entire suite to run 0.7% of it.

### The fix, and what it is not

Hand pytest the **17 files that carry the marker**. `-m "slow and not research"` remains the
selector — the path list only narrows what is IMPORTED, never what RUNS — and the two were verified
to select the **identical 80 tests**.

| | collection | wall clock (`-n 4`) |
|---|---|---|
| unscoped (before) | 11.04s | 106.8s |
| **scoped (after)** | **1.30s** | **68.8s (−36%)** |

Projected CI: **~7m20s → ~4m30s**.

⛔ **Not trimmed.** The two files that are 65% of the cost (`mh2_6`, `mh2_10`) already run at
`FAST_REPS = 600`, sitting deliberately just above `min_null_reps()` — the **measured vacuity
floor**. MH2.6's own finding is that below that floor no statistic can clear the multiplicity
correction, i.e. the harness passes everything. Cutting reps here would re-create the exact defect
those tests exist to detect. TD2's "cut draws, never games" does not apply: the draws are already at
their floor.

⛔ **Not sharded, and that is measured rather than assumed.** Once scoped, this job (~4m30s) and the
E2E smoke shard (4m25s) are neck and neck, so a 3-way split would move the *whole gate* by seconds
while adding three jobs' startup and three more things to keep in sync. Shard it only if E2E gets
faster first.

### The hazard this introduces, and the guard

An explicit file list is a way for a test to **stop running with no signal**: `-m` can only select
from what is imported, so a slow test in a missed file is deselected by *absence* — green gate, no
error. Three things keep that from happening:

1. the list is **derived by AST-scanning for the marker** (`ci_shards.slow_files()`), not
   maintained by hand — all four ways of writing the marker (`@pytest.mark.slow`, `pytestmark = …`,
   `pytestmark = [ … ]`, `pytest.param(marks=…)`) parse to one attribute chain, so one check covers
   every form a regex would have to enumerate;
2. `--slow-paths` **exits non-zero on an empty list** — without that, no arguments would silently
   fall back to `testpaths` and quietly restore the whole-suite collection;
3. `test_fast_gate_hygiene.py::TestSlowGatePathScoping` pins all of it, RED-proven by
   `betting_ml/tests/ci_slow_gate_red_proof.py` (5 breaks, all caught), including
   "revert the workflow to the unscoped command", which is the wired-≠-invoked case.

### 🔴 CORRECTION (2026-08-20, same day) — the scoping did NOT move the gate

**The "~7m20s → ~4m30s" projection above is WRONG and the change should not be credited with a
speed-up.** Measured properly afterwards, across the CI job's real distribution rather than one run
either side:

| | n | mean | median | sd | range |
|---|---:|---:|---:|---:|---:|
| before scoping | 12 | 408.3s | 401s | 67.8s | 282–567 |
| after scoping | 5 | **407.8s** | 378s | 43.1s | 370–477 |

**Delta in means: −0.5s.** The job's natural run-to-run spread is **285 seconds**, so any saving
below roughly 140s cannot be seen in a before/after pair — and a before/after pair is exactly what
was reported, twice, in both directions (first "−36%" projected from one local run, then "−19%" from
one CI run).

**What is still true:** collection genuinely drops 11.04s → 1.30s, and the scoped command genuinely
selects the identical 80 tests. That is ~44s of wall clock on a 4-worker runner — real, directionally
right, and **smaller than the noise it has to beat**. The change is kept because it is free and
correct, not because it made the gate faster.

**What this means for the next attempt:** the remaining cost is the tests' own CPU (~256s serial
locally, ~4× that on CI), and the only lever that divides it is **sharding across runners** — the
thing this document argued against on the strength of the bad projection. That argument is
withdrawn. ⚠️ And it must be validated against the DISTRIBUTION: ≥5 runs each side, compared on
medians, not one run before and one after.

### The reusable lesson

**A slow pytest job is not necessarily slow tests** — `pytest <selector> --collect-only -q` prints
`N/M tests collected`, and a large `M` with a small `N` means much of the wall clock is import, paid
per worker. That diagnosis was correct here.

⭐ **But the second lesson is the one that cost something: a CI timing claim needs the job's
DISTRIBUTION, never a before/after pair.** This job ranges 282–567s run to run. Sizing a fix from one
observation — or confirming it from one — cannot distinguish a 44s improvement from nothing, and both
readings were reported as fact before the distribution was pulled. Get `n≥5` each side and compare
medians BEFORE claiming a CI speed-up, however clean the local measurement looks.
