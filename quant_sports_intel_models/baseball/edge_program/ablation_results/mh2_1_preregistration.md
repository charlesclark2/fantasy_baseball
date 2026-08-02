# MH2.1 — PRE-REGISTRATION: the wide-window re-run of E7.9's retrain bake-off

**Registered 2026-08-02, BEFORE any arm was scored.** Everything below is fixed in source
(`betting_ml/scripts/e7_9_train_serve_consistency.py`, the `MH21_*` block) and pinned by
`betting_ml/tests/test_mh2_1_wide_window_retrain.py`. Nothing here may move after a result is seen.

> ⚠️ **`best_alpha = 0`.** A CRPS improvement on `total_runs` is a **pricing / calibration**
> improvement. It is not an edge, a win rate, or an ROI, and nothing in this document licenses such
> a claim. `INCUMBENT_STANDS` remains the default and a null is a real, publishable outcome.

---

## Why this exists

E7.9 recorded `INCUMBENT_STANDS` on `total_runs/post_lineup` with the binding caveat *"3 purged
folds — this can rule out a LARGE effect, not a small one."* MH2 measured that the 3 folds were a
**WINDOW CHOICE, not a data limit**: `feature_pregame_game_features` holds 2015–2026 / 26,883 rows,
and the served 13-column contract is ≥0.827 non-null from 2016 (0.449 in 2015). So E7.9's own
pre-registered follow-up #2 — *"`plus_eb` on `total_runs` specifically, PROPERLY POWERED"* — is
reachable **today, with no calendar wait**.

The point is not to overturn E7.9. It is to make its answer **trustworthy**: to move the null from
`POWER_LIMITED` (or, as MH2 showed, `UNDEFINED`) to a state that actually says something about the
mechanism.

---

## LOCK 1 — the window, and the 2020 decision

| | |
|---|---|
| **PRIMARY** | `min_year = 2016`, **2020 KEPT** — 11 seasons ⇒ **8 folds** (eval years 2019–2026) |
| **DECLARED SENSITIVITY** | 2020 dropped from **BOTH** train and eval — 10 seasons ⇒ **7 folds** |
| E7.9, for contrast | 2021–2026 — 6 seasons ⇒ **3 folds** |

Fold count is deterministic (`n_seasons − min_train_seasons`, `min_train_seasons = 3`), so all three
numbers are checkable before any data is touched, and they are.

**Why 2020 is in the PRIMARY — decided in advance, on design grounds only:**

1. it is what MH2 §7 measured and what this story's own 8-fold arithmetic assumes; changing it after
   the fact would silently move the headline;
2. power is the entire point of the re-run, and dropping 2020 costs a fold (8 → 7);
3. 2020 is atypical but not unrepresented downstream — the extra-innings ghost runner it introduced
   is permanent from 2023, so it is not a one-season-only regime the way the 60-game schedule is.

**Why the sensitivity is mandatory anyway:** 2020 is an **898-game** season whose totals-generating
process (7-inning doubleheaders, no fans, a 60-game sprint) is structurally different. **If the
verdict FLIPS between the two arms, neither reading is trustworthy and that fact is the finding.**

---

## LOCK 1b — the field, DECLARED and not discoverable

`{incumbent, plus_eb} × {ngboost_normal, glm_elasticnet}` = **4 arms**.

- `plus_eb` is E7.9's follow-up #2 — the E7.5/E7.5p-corrected EB block the served contract does not
  already carry.
- `ngboost_normal` is the incumbent learner class; `glm_elasticnet` is the **direct-learned foil**
  (a genuinely different model class, and E7.9's own leader learner).
- **NOT** E7.9's 24–28-arm variant×learner grid. MH2 §2b: the DSR bar rises with FIELD SIZE, and
  E7.9 measured that **74% of its own headline margin was the LEARNER SWAP**, not the features.

⚠️ **You get to pre-register a family; you do not get to discover one.** No arm may be dropped after
a score is seen — trimming a field after the fact under-taxes DSR and is a second layer of the very
selection bias DSR exists to deflate. An unbuildable pre-registered arm **HALTs** the run.

---

## LOCK 3 — the DSR convention, FIXED FIRST (non-negotiable; MH2 defect 2)

E7.9 computed DSR on **~19 year-MONTH buckets** and passed **no `trial_sharpes``**. Two independent
biases, both pushing the same way:

1. **`n_obs` was buckets, not folds.** The statistic scales with `√(n_obs−1)`, and month-buckets
   inside one purged fold are not independent draws — they share a training fit. Counting 19 where
   the design yields 3 inflates the statistic by ≈ √(18/2) ≈ **3×**.
2. **`trial_sharpes` omitted** ⇒ `deflated_sharpe` fell back to the asymptotic `V = 1/n_obs` instead
   of the measured cross-trial dispersion. `SR0 = √V·z(N)`, so an understated `V` understates the
   bar.

⇒ **E7.9's recorded `DSR 0.842` is an OVERSTATEMENT** of what that design supported. A wide-window
number scored the legacy way would not have been comparable to it, and the whole point of the re-run
would have been lost.

**THE FIX** (`dsr_gate`, matching `h_harness.dsr_report`): observations are the **FOLDS**, and
`trial_sharpes` is **measured** from every candidate arm's own per-fold skill series. Both
conventions are emitted every run; **the fixed one BINDS**, the legacy one is reported beside it so
the size of the bias is on the record rather than asserted.

### Two defects the build-out's own harness check surfaced (on smoke data, before any real arm)

Both were found by the disclosure this lock required, which is the argument for the disclosure.

1. **The reference arm was inflating the dispersion.** The incumbent's skill-vs-itself series is
   identically zero by construction; feeding that forced 0 into a variance estimated from a handful
   of arms inflates `V` and hence `SR0` for a purely structural reason. `h_harness.dsr_report`
   excludes its foil for exactly this reason. `V` is now measured over the **non-reference** arms —
   while `n_trials` stays the **full** field size, because every arm including the incumbent was a
   configuration that could have won and multiplicity must not be understated.
2. **🪤 The E2.1-r `oracle_floor` was leaking into the trial field.** The oracle *sees the realized
   target*. Left in the field it posted a per-fold skill Sharpe near **30** and drove `V` to **≈220**
   / `SR0` to **≈15.6** — i.e. **the anchor that exists to POLICE the metric was silently setting the
   gate's bar**, making DSR unclearable for an arithmetic reason rather than an evidential one. With
   it excluded, `V` falls to ≈0.015. It is a diagnostic anchor, never a trial.

**And `V` from a 4-arm family is itself unstable**, so it is disclosed rather than trusted silently:
two arms differing from the incumbent by a nearly constant amount across folds have a near-zero
skill SD and hence an enormous Sharpe — a near-zero-denominator artifact. Every run therefore also
reports the **asymptotic-`V` DSR** and an explicit list of **degenerate trial arms**. The measured-`V`
figure BINDS as pre-registered; the other two exist so *a high bar can be told apart from a broken
one*.

**PBO** stays on year-month buckets (pre-registered as binding, so the wide window stays comparable
to E7.9 on that gate); the coarser fold-level PBO is reported beside it.

---

## LOCK 2 — coverage is NOT uniform across the window

2016–2020 sit at ≈0.83 contract coverage against ≈0.98 for 2024+, so the **older folds lean harder
on imputation**. Every report prints **per-fold score beside per-fold contract coverage**, measured
on the actual training matrix.

**A lift that lives only in the thin folds is an imputation artifact, not a feature effect.** This is
a *reporting* obligation, not a gate — a coverage-based exclusion decided after the fact would be
exactly the window-shopping Lock 1 forbids.

### 🚩 …AND A PER-SEASON MEAN HIDES THE THING THAT ACTUALLY MATTERS (measured 2026-08-02, pre-run)

The served 13-column contract is:

`away_bp_eb_coverage_pct`, `away_bp_eb_uncertainty`, **`away_lineup_bat_speed_vs_starter_velo`**,
`away_losses`, `away_wins`, `home_bp_eb_coverage_pct`, `home_bp_eb_uncertainty`,
`home_pit_woba_against_14d`, `home_pit_woba_against_30d`, `home_pit_woba_against_std`,
`home_starter_avg_ip_season`, `home_starter_proj_fip`, `park_run_factor_3yr`

**TWO** of those columns are structurally absent for part of the window. Measured on the REAL served
store (`s3://…/lakehouse/feature_pregame_game_features`, read 2026-08-02 — non-null share):

| season | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `away_lineup_bat_speed_vs_starter_velo` | **0.000** | **0.000** | **0.000** | **0.000** | **0.000** | **0.000** | **0.000** | 0.431 | 0.988 | 0.989 | 0.979 |
| `home_starter_proj_fip` | **0.000** | **0.000** | **0.000** | **0.000** | 0.973 | 0.963 | 0.987 | 0.985 | 0.986 | 0.987 | 0.963 |
| **mean contract coverage** | 0.828 | 0.826 | 0.834 | 0.829 | 0.886 | 0.900 | 0.906 | 0.938 | 0.982 | 0.982 | 0.976 |

`away_lineup_bat_speed_vs_starter_velo` is **Statcast BAT-TRACKING** (launched mid-2023);
`home_starter_proj_fip` is a **FanGraphs projection** that begins in 2020.

Pooled, this reads as "0.83–0.91 coverage" — i.e. *uniformly noisier data*. **The truth is that
specific contract features are entirely absent for the older part of the window**, so what each fold
actually evaluates is:

| eval fold | season | real contract features | absent |
|---:|---:|---:|---|
| 1 | 2019 | **11 of 13** | `bat_speed`, `proj_fip` |
| 2–4 | 2020–2022 | **12 of 13** | `bat_speed` |
| 5 | 2023 | 12 + a 43%-covered 13th | `bat_speed` partial |
| 6–8 | 2024–2026 | **13 of 13** | — (the served contract) |

⇒ **The early and late folds differ in WHICH contract they are testing, not merely in how noisy it
is** — and only **3 of the 8 folds** evaluate the contract that is actually served. Every report
therefore names the structurally-absent columns per fold rather than reporting a pooled mean. Three
consequences fixed in advance:

- a cross-fold difference must **not** be attributed to the `plus_eb` block without accounting for
  this;
- ⚠️ **the added power is PARTLY COSMETIC, and by more than first estimated** — five of the eight
  folds test a contract the model does not serve, and the oldest fold is missing two features.
  **That does not invalidate the re-run**: the incumbent and the challenger face the *identical*
  handicap in every fold, so the CONTRAST stays fair and the verdict is still a valid answer to "does
  `plus_eb` beat the incumbent?". But it bounds what the extra folds certify about the **served**
  model, and the verdict must say so rather than claiming 8 clean folds;
- **No column is dropped and no fold is excluded over this.** Doing so after measuring it would be
  exactly the post-hoc trim Lock 1 and Lock 1b forbid. It is disclosed, not acted on.

*(This also confirms the Lock-1 choice to start at 2016: 2015 has **seven** of the 13 absent, hence
its 0.449.)*

---

## LOCK 4 — the matrix is still NOT point-in-time

`load_features` reads each game's row **as it exists now** (post-game backfilled and dense); the live
serve only ever saw the sparse pre-game row. **Widening the window WIDENS this exposure** — the
2016–2020 rows have had the longest to be backfilled — so a wide-window score is if anything a *more*
optimistic ceiling than E7.9's.

**Every number this study produces is a CEILING, not an achievable live figure**, and the caveat is
printed unconditionally in every report.

---

## LOCK 5 — the bar, stated before the run

Required per-fold Sharpe to clear `DSR ≥ 0.95` (asymptotic `V = 1/n_obs`, the convention MH2 §7's
design table used — reproduced exactly by `design_bar`, pinned by a test):

| design | folds | arms | required per-fold Sharpe | DSR ceiling at ANY effect | PBO evaluable |
|---|---:|---:|---:|---:|---|
| E7.9, as it ran | 3 | 28 | **7.28** | 0.9772 | ❌ **no — UNDEFINED** |
| wider window, same field | 8 | 28 | 1.69 | 0.9999 | ✅ yes |
| **MH2.1 PRIMARY** | **8** | **4** | **1.18** | 0.9999 | ✅ yes |
| MH2.1 sensitivity (no 2020) | 7 | 4 | 1.31 | 0.9997 | ✅ yes |

Two things this table settles before any arm is fitted:

- **E7.9's PBO was not FAILED — it was not COMPUTABLE** (CSCV is undefined below 4 folds). Reporting
  it as a met-or-unmet deflation requirement converted a design limit into a finding about the
  mechanism.
- **At 3 observations the maximum attainable DSR is 0.977** against a 0.95 gate. E7.9's `0.842` was
  a statement about the design before it was one about the features.

### Classifying the outcome

An `INCUMBENT_STANDS` verdict is classified by `cv_power.classify_null` into one of the **seven**
states (§0.5.4) — **computed, never asserted**. MH2.1's claim is that this null moves off
`POWER_LIMITED`; that claim is worth nothing unless the classifier was free to land somewhere worse,
including `GENUINE_ABSENCE` (which carries **no** re-test trigger).

The minimum detectable effect is derived from **the gate that actually binds here** — margin + PBO +
DSR + calibration. This harness carries **no** fold-consistency clause and **no** BH family, so
`cv_power.mde_in_sd_units` (which simulates a consistency+BH composite) would describe a rule it does
not run. The pre-registered practically-meaningful lift is `NOISE_FLOOR['crps'] = 0.02` — the
program's own materiality constant, fixed long before this story, **not** reverse-engineered from the
answer.

---

## Decision rule (unchanged from E7.9)

SHIP a challenger only if **all** hold:

1. it beats the incumbent arm on CRPS by more than `NOISE_FLOOR['crps'] = 0.02`;
2. PBO < 0.2 over the whole field;
3. DSR ≥ 0.95 **under the fixed convention**;
4. calibration (PIT-KS) not degraded, at amendment-#1 tolerance.

Otherwise **`INCUMBENT_STANDS`**, and the null is the deliverable — this time a powered one. On a
promotion, E7.9 step 7's historical prediction backfill fires (labelled a BACKTEST, never a real-time
record).

---

## The runs

Both are **>2 min ⇒ OPERATOR, on the LAPTOP** (a laptop run still writes production S3 keys only if
it publishes; this one writes local artifacts only).

```bash
# PRIMARY — 2016–2026, 2020 kept, 8 folds
uv run python betting_ml/scripts/e7_9_train_serve_consistency.py \
    --bakeoff --mh2-1 --target total_runs --tier post_lineup --s3 --refresh-cache

# DECLARED SENSITIVITY — 2020 dropped from train AND eval, 7 folds
uv run python betting_ml/scripts/e7_9_train_serve_consistency.py \
    --bakeoff --mh2-1 --exclude-seasons 2020 --target total_runs --tier post_lineup --s3
```

`--refresh-cache` on the first run only: the 2016 window is a **new cache key**
(`edge_e1_training_from2016`) and must be pulled once. The second run reuses it.
