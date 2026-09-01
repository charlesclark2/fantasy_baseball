# MLB-TV2-2 — PRE-REGISTRATION (committed BEFORE any scoring)

> A mixture-density head for the served `total_runs` predictive SHAPE.
> Spec: `plan_specs/mlb/mlb-tv2-2.yaml` · epic `pa4ii3tQ` · card https://trello.com/c/J9G2VHu8

`best_alpha = 0` · `bet_paused` stays `true` · **market-blind** · **nothing serves** · **DEPLOY-HELD**

**This is a calibration/honesty study.** It makes no claim about edge, win rate, ROI or CLV, and
none of its gates reads a market price. At `best_alpha = 0` no bet rides on this model.

**Status of this document.** Everything below is fixed before any statistic involving a realized
outcome is computed on this population. The census in §2 reads row counts, date ranges, champion
stamps and insertion lags only — design quantities, no outcome value — and is what allows §3 to
NAME its window rather than choose one after seeing a result (E2.1-r).

---

## 1. The four epic obligations, carried verbatim

The spec's AC-1 requires four obligations be carried verbatim. They are §3, §6, §9 and §10
respectively. Each is stated in full at its own section; this table is the index, not the text.

| # | obligation | section |
|---|---|---|
| 1 | LONGER-WINDOW REPLICATION — TV2-0's 2-month/1-champion read licenses FUNDING, not serving | §3 |
| 2 | TIE-WITH-FOIL guard + asymmetric initialization + the MH2.8 positive control | §6 |
| 3 | `std_pred` DISAMBIGUATION by file:line | §9 |
| 4 | SCOPE — DISCRIMINATION is untouched; no gate here reads it | §10 |

---

## 2. Census — the design quantities, measured before this document was written

Read from the served store on 2026-08-31. **No realized outcome value was read**; these are row
counts, date ranges, champion stamps and insertion lags.

### 2.1 ⭐ `is_backfill = FALSE` DOES NOT ESTABLISH "SERVED" — the insertion LAG does

| `model_version` | tier | `is_backfill` | n | window | **median insert lag** | verdict |
|---|---|---|---:|---|---:|---|
| `v0` | morning | **FALSE** | 15,263 | 2021-04-01 → 2026-05-11 | **981 d** | ⛔ BACKTEST |
| `v1` | morning | **FALSE** | 14,528 | 2021-04-01 → 2026-05-06 | **1009 d** | ⛔ BACKTEST |
| `v2` | morning | **FALSE** | 10,607 | 2021-04-18 → 2026-06-01 | **1001 d** | ⛔ BACKTEST |
| `v6` | post_lineup | TRUE | 1,236 | 2026-03-25 → 2026-06-27 | 43 d | ⛔ backfill (correctly flagged) |
| **`v6`** | **post_lineup** | **FALSE** | **887** | **2026-06-23 → 2026-08-31** | **0 d** (max 12) | ✅ **SERVED** |
| **`pre_lineup_v6`** | **morning** | **FALSE** | **2,867** | **2026-06-24 → 2026-08-31** | **0 d** (max 2) | ✅ **SERVED** |

⭐ **A ~40,000-row history carries `is_backfill = FALSE` while sitting a median of ~2.7 YEARS
after its own game date.** Those rows are a historical scoring run wearing a served table's
clothing. Under MH2.6 a backtest structurally cannot see a serving-path defect, so admitting them
would silently convert the decisive population into the one thing the discipline forbids.

**The flag is not the instrument; the lag is.** TV2-0's pull filtered on the flag and was safe
only because its `model_version` filter happened to exclude the mislabelled eras — safe by
ACCIDENT of the champion filter, not by the flag. This study establishes served-ness by
`median(inserted_at − game_date) = 0`, and reports the lag it measured. *(Carried to closeout as a
finding: the served-row filter in `mlb_tv2_0_ceiling_diagnosis.py` is under-specified for reuse.)*

### 2.2 The champion era, and how much window actually exists

The population is defined by the CHAMPION, not the calendar (MH2.10). The champion
(`v6` / `pre_lineup_v6`) was fit **2026-06-23**; today is **2026-08-31**.

| slice | post_lineup | morning |
|---|---:|---:|
| TV2-0's read (2026-06-23 → 08-23) | 758 | 765 |
| **FRESH extension (08-24 → 08-30)** | **93** | **93** |
| **FULL champion era to date** | **851** | **858** |

⚠️ **Registered forward, because it bounds what obligation 1 can prove: a materially longer
served window DOES NOT EXIST.** The era is bounded below by the fit date and above by today, so
the widest window available is **+93 rows / +12.3%** over TV2-0's. It can be widened only by
waiting (≈93 rows per game-week) or by changing champion — which MH2.6 forbids treating as the
same population. This study will not pretend otherwise, and §3 is designed around it.

Excluded: 15 post_lineup rows stamped `totals_model_version = 'mh2_1'` on 2026-08-02 — the
footprint of the MH2.1 promotion that was promoted, briefly served and rolled back the same day
(PR #514). A different predictive; not this champion's population.

### 2.3 Bars, checked for reachability before they were adopted

| quantity | value at this design | reachable? |
|---|---:|---|
| `dsr_ceiling(n_obs = 5 folds)` | **0.9977** | ✅ the 0.95 bar is attainable (unlike MH2's 3-fold 0.977 case) |
| `fold_consistency_clause(n_folds = 5)` | wins_required **4**, false-fire **0.1875** | ✅ calibrated, not the legacy 0.60 rule (false-fire 0.50) |
| `pbo_evaluable(5)` | **True** | ✅ PBO is defined, not vacuous |

---

## 3. ⭐ OBLIGATION 1 — the LONGER-WINDOW REPLICATION leg

> **Verbatim (spec AC-1):** *"a LONGER-WINDOW REPLICATION leg of the shape gap — TV2-0's
> 2-month/1-champion read licenses FUNDING, not serving; the prereg names the wider served window
> (and its champion boundaries — the population is defined by the CHAMPION, not the calendar, per
> MH2.10) on which the gap must replicate before any ship clause can fire."*

**The wider served window, NAMED:** `model_version ∈ {v6, pre_lineup_v6}` (champion fit
2026-06-23), served rows only (§2.1), deduplicated to the served row per `(game_pk, tier)` by
latest `inserted_at`, joined to a realized regular-season final, `totals_model_version` NULL or in
`{v6, pre_lineup_v6}`, game dates **2026-06-23 → 2026-08-30**. PRIMARY tier `post_lineup`
(**n = 851**); SECONDARY tier `morning` (**n = 858**), reported as replication only and never able
to swap the primary (E2.1-r).

### 3.1 The three reads, and which one BINDS

| read | population | n | role | can trigger STOP? |
|---|---|---:|---|---|
| **FULL-ERA** | 2026-06-23 → 08-30, served, post_lineup | **851** | ⭐ **BINDS** | ✅ **yes** |
| FRESH slice | 2026-08-24 → 08-30, served, disjoint from TV2-0 | 93 | independent check, reported | ⛔ **no** — see §3.3 |
| BACKTEST context | pre-champion eras (§2.1) | — | labelled BACKTEST; context only | ⛔ no |

**Replication is declared** iff, on the FULL-ERA read, the incumbent's `p_over_gap_abs` lies
OUTSIDE its calibrated-null 95% band **with the same sign as TV2-0's** (stated over-probability
EXCEEDS realized). Same instrument, same construction, same tier as TV2-0 — a like-for-like read.

**STOP rule.** If the FULL-ERA read does not replicate, the study STOPS after recording: the
funding premise fails, nothing is fitted, no ship clause can fire, and the verdict returns to the
PM. No gate downstream of §3 is evaluated.

### 3.2 The honest limit of this leg, stated before it is run

The FULL-ERA read shares **758 of its 851 rows (89%) with TV2-0's**. It is therefore a
LARGER read, not an INDEPENDENT one. It answers *"does the gap survive on every served row this
champion has produced?"* — the population a ship would serve — and it does **not** answer *"does
the gap appear on data TV2-0 never saw?"* That second question is the FRESH slice's, and §3.3 says
in advance how little it can carry.

### 3.3 ⚠️ The FRESH slice is UNDERPOWERED BY DESIGN — registered forward

At n = 93 the standard error of a `p_over` gap is **0.0518**, so TV2-0's 0.0726 gap sits at
**1.40 SE**: a two-sided 95% read detects it **28.8%** of the time, and the slice's MDE at 80%
power is **0.145** — twice the effect it is being asked about.

⭐ **Therefore, registered NOW rather than discovered later: a non-significant FRESH slice is the
EXPECTED outcome under a TRUE effect, and reading it as refutation would be a design error**
(NF1.7 (a) — a check that cannot discriminate has not discriminated; MH2's underpowered ≠ absent).
The FRESH slice is reported with its power and its MDE beside it. It cannot trigger STOP.

For contrast the FULL-ERA read has **98.9%** power against the same effect (4.24 SE, MDE@80%
0.048) — which is why it, and only it, binds.

---

## 4. The mechanism, and the single axis the field varies

The served predictive is `Normal(μ_i, σ_i)` — symmetric — against a right-skewed target
(TV2-0 measured realized `z` skew **0.749**; the finding is program-level, confirmed in two sports
by MH2.6/MH2.8 and NCAAF-P2.5). **The mechanism axis is the marginal predictive SHAPE,
parameterized as a K-component Gaussian mixture on the standardized residual**
`z_i = (y_i − μ_i) / σ_i`, with **K** and the **within-mixture parameterization** as the only
things that vary across trial arms.

Every arm holds **μ EXACTLY at the served value** (inherited from TV2-0). Every law is fitted
**OUT OF BLOCK** over **5 contiguous date blocks** (TV2-0's `date_blocks`, cross-fit, no date
straddling two blocks). Nothing in this study is fitted on the rows it is scored on except the
per-form peeking oracles, which exist to be beaten-or-not and never ship.

---

## 5. THE FIELD — declared coherent, FORWARD

The MH2.8 lesson is explicit: its real skew arm cleared 9 of 10 clauses and died on a DSR bar that
ONE heterogeneous arm inflated, and the sanctioned successor is a NARROWER coherent family — a
diagnostic ~0.79, **not a foregone pass**. This field is declared on MECHANISM before any DSR is
computed, and ⛔ **no per-candidate-family DSR menu is computed at any point** (NF-INJ3b: publishing
a menu hands a successor a family selected on its DSR — the MH2.2 laundering one hop removed).

### 5.1 Arms

| arm | role | ∈ `n_trials`? | ∈ `V`? |
|---|---|---|---|
| `incumbent` — the served `Normal(μ, σ)` | **REFERENCE** | ✅ | ⛔ **no** (MH2.1 (a)) |
| `foil_k1` — identical machinery at K=1: a Normal fitted to out-of-block `z` | **MATCHED FOIL** | ✅ | ⛔ no |
| `mix2_loc` — K=2, free weights + locations, COMMON scale | trial | ✅ | ✅ |
| `mix2_full` — K=2, free weights + locations + scales | trial | ✅ | ✅ |
| `mix3_full` — K=3, free weights + locations + scales | trial | ✅ | ✅ |
| `mixK_bic` — K ∈ {1,2,3} by out-of-block BIC, full parameterization | trial | ✅ | ✅ |
| `degen_sharp` — scale × 0.25 | **DEGENERATE** (must lose) | ✅ | ⛔ no (DSR-CONV) |
| `degen_wide` — scale × 3.0 | **DEGENERATE** (must lose) | ✅ | ⛔ no (DSR-CONV) |
| `ctrl_permuted` | control | ⛔ no | ⛔ no |
| `ctrl_symmetrized` | control | ⛔ no | ⛔ no |
| `oracle_<form>` (one PER FORM) + `oracle_empirical` | ⛔ ORACLE | ⛔ no | ⛔ no |

**`declared_field_size = 4`** — the trial arms. Passed to `classify_null` (MH2.7), whose
`field_remedy_admissible` flag is read from the MACHINE FLAG, never from the prose.

### 5.2 Why `foil_k1` is the comparator and not `incumbent`

`foil_k1` is a location+scale recalibration with NO shape channel: it keeps the fitting machinery,
the cross-fit, the out-of-block estimation and the scale correction, and removes only the thing
this story claims. Every shape claim is therefore measured as `arm − foil_k1`, exactly as TV2-0
measured its architecture lever beyond `A1` rather than beyond the incumbent. Scoring against the
incumbent instead would let the mixture bank a plain recalibrator's work.

### 5.3 `V`-membership, declared before anything is scored

**`V` (the cross-trial Sharpe dispersion) is computed over the 4 TRIAL arms only.** The reference
(`incumbent`) and the matched foil are excluded because a reference arm's near-zero or
identically-zero skill series inflates a small family's `V` for a purely arithmetic reason
(MH2.1 (a)); the two degenerates are excluded per DSR-CONV. **All 8 remain in `n_trials`** so
multiplicity is paid in full. Both the `V`-with-degenerates and `V`-without figures are reported;
**the declared (degenerate-excluded) reading BINDS.**

⛔ No arm is added to or removed from `V` after any DSR is computed. Exclusion is
NON-MONOTONE (DSR-CONV) and is therefore not available as a lever.

### 5.4 Controls

- **`ctrl_permuted` — registered as an EXPECTED EXACT TIE.** A row permutation cannot move a
  MARGINAL law, which depends only on the out-of-block multiset of `z`. The control is INERT BY
  CONSTRUCTION (NF1.9: a mechanism that cannot act is a finding, not an omission; NF-D16 sibling 1:
  register such an anchor as an expected tie IN ADVANCE and prove it). Its job is a machinery
  check — it proves the fit carries no row-level leakage — and it is reported as a proven tie,
  ⛔ never presented as a passed test.
- **`ctrl_symmetrized` — the matched foil for the STATED MECHANISM.** The same mixture form fitted
  to a SYMMETRIZED out-of-block `z` (`z ∪ −z`): scale and kurtosis machinery intact, ASYMMETRY
  destroyed. NF-D15 (g′) — a win must be attributed to the channel it claims, and "my arm won" is
  not "it won for the reason I said." If the win survives symmetrization it is NOT about skew.
- **Per-form peeking oracles, one PER FORM** (NF-D16 (g‴)): the forms NEST (`mix3 ⊃ mix2 ⊃ K=1`),
  so a single field-wide ceiling would veto a legitimately-better nested form as a false metric
  inversion. Each form is floored by the peeking version of ITS OWN form at matched n
  (NF1.7 (b) / NF1.9 (f): a peeking oracle is a floor only at matched family AND matched sample).
  `oracle_empirical` (TV2-0's `B2` law) is reported as the nonparametric marginal ceiling.

### 5.5 Multiplicity, PBO, and which reading binds

- **BH family: the primary-statistic tests across the 4 declared TRIAL arms (k = 4).** The
  single-hypothesis reading (one mechanism, one population, one primary statistic) is REPORTED
  beside it. ⭐ **The BH-across-arms reading BINDS** — the conservative one, declared now.
- **`pbo_application = "field"`.** PBO/CSCV is a FIELD-LEVEL statistic (PM convention 2026-08-28)
  and is ⛔ never carried as a per-arm pass/fail; `classify_null` refuses to convert a field-level
  refusal into a per-arm verdict, and this study reads it that way.
- **Deflation gates** are the program default `{pbo, cscv, dsr, deflated_sharpe}`;
  `bh_fdr` and `fold_consistency` are MULTIPLICITY/STABILITY gates and are NOT deflation-class.

### 5.6 PLAT-CVP1 — the injected-effect positive control

`cv_power.injected_effect_positive_control` is **EXECUTED, not narrated** (import verified at
kickoff by execution, not assumed). `DEFLATION_REFUSED` is a reachable, reportable state, and the
lockstep computation is trusted over any "get a lower-variance design" instinct
(NF-W8-0d: a shared-variance lever is deterministically void for `dsr_ok`).

⚠️ **Uniform-injection caveat (NF-INJ2b), registered forward:** a uniform additive injection cannot
re-order treated arms among themselves, so a rank-based FIELD-LEVEL statistic can be INVARIANT BY
CONSTRUCTION. The control reports the count of splits whose winner the injection actually moved,
and any field-level statistic with a zero count is reported **INERT**, never as a passed leg.

---

## 6. ⭐ OBLIGATION 2 — the TIE-WITH-FOIL guard

> **Verbatim (spec AC-1):** *"a TIE-WITH-FOIL guard: any arm that nests its foil (a K-component
> mixture nests K=1 Normal exactly as NB nests Poisson) must declare the collapse detector — a
> near-zero margin is a TIE that refuses to count, and the fit must NOT start from the symmetric
> point a flat likelihood can't leave (staggered/asymmetric initialization, with the MH2.8 positive
> control proving the fitter FINDS a planted skew)."*

This is the single most likely way this study fails silently. TV2-0 measured the trap on this exact
population: `B1_shape_skewnormal` collapsed onto its Normal foil on **5 of 5 blocks**
(α = [0.025, 0.012, −0.002, −0.004, −0.003]) while the realized `z` skew was **0.749** — a fitter
started near symmetry reporting *no skew, converged successfully* on obviously skewed data. A
K-component mixture is unidentified at the collapse point in the same way.

### 6.1 Asymmetric / staggered initialization — registered

Components are initialized at **DISTINCT out-of-block `z` quantiles** — for K components, the
`(j + 0.5)/K` empirical quantiles, `j = 0…K−1` — with **unequal starting weights**
(`w_j ∝ K − j + 1`, normalized) and per-component scales at the out-of-block SD × `(0.7, 1.0, 1.4)`
truncated to K. ⛔ **No component starts at a common point**, so the fit never begins on the flat
ridge. A second start from the mirrored initialization is run and the better out-of-block
log-likelihood is kept; both are reported.

### 6.2 The collapse detector — registered thresholds

An arm is **COLLAPSED** on a block if ANY of:

| condition | threshold |
|---|---|
| sup-norm ‖F_mix − F_k1‖ on the CRPS grid | `< 1e-3` |
| any fitted weight | `< 0.02` |
| all component locations within | `0.02` **and** all scales within a factor `1.02` |

**A COLLAPSED arm's margin is a TIE. It REFUSES TO COUNT: it cannot win, cannot ship, and is
reported as COLLAPSED — never as a null on the mechanism** (MLB Batter Props Ph2: when a candidate
NESTS its foil, a near-zero margin is a TIE, not a win). The per-block collapse count is reported
for every arm regardless of outcome.

### 6.3 The MH2.8 positive control — the fitter must FIND a planted skew

A known skew (skew-normal `α = 4.0`, TV2-0's control level) is planted into `y` on the REAL served
`(μ, σ)`. The fitter must recover it. Following TV2-0's amendment 2, this is a **DETECTION RATE
over 20 replicates, never a single draw**.

**Bar: ≥ 0.80 of replicates return a NON-collapsed mixture whose fitted asymmetry carries the
PLANTED SIGN.** A harness that cannot find a skew it was handed cannot be trusted to report its
absence — and MH2.8's false null had every gate green.

---

## 7. Statistics, nulls, and the instrumentation obligations

### 7.1 Which statistic each gate reads

| statistic | what it is | null |
|---|---|---|
| `p_over_gap_abs` | **PRIMARY.** \|stated − realized\| P(over) at the model's OWN mean — market-blind | calibrated null |
| `crps` | proper score, per-row, shared quantile grid (midpoint quadrature, 499 levels) | calibrated null |
| `pit_ks` | overall distributional fidelity, continuity-corrected randomized PIT | calibrated null |
| `cov80` | coverage — a **FLOOR, never a target** (E2.1-r) | power-derived floor, §7.3 |
| `var_z_pooled` | pooled variance of the standardized residual | ⭐ **SHAPE-MATCHED null**, §7.2 |

Every arm shares ONE uniform draw for the randomized PIT (TV2-0's pairing), and every statistic is
rebuilt from per-row components so the bootstrap is PAIRED — the decision-relevant noise is the
noise of the DIFFERENCE.

### 7.2 ⭐ Variance statistics sit in a SHAPE-MATCHED null (MH2.10)

`Var(s²)` depends on the FOURTH moment, and this target is right-skewed and leptokurtic against a
symmetric Normal — so a Normal-DRAWN null is systematically TOO NARROW for a variance statistic
and a SHAPE defect mechanically MANUFACTURES an apparent SCALE flag. **`var_z_pooled` is therefore
scored against a null built by resampling the observed standardized residuals rescaled to variance
EXACTLY 1**, so the null hypothesis is precisely "the σ scale is correct" with shape as a nuisance.
⛔ This applies to variance statistics ONLY — on a PIT statistic it would build the tested defect
into the null. PIT/coverage/CRPS/`p_over` keep the standard calibrated null.

### 7.3 Coverage is a FLOOR, and the floor is POWER-DERIVED

`cov80`'s floor is `coverage_power_floor.power_floor(n, nominal=0.80, target=0.05)` — derived from
n and a false-reject target registered long before this story, ⛔ never a flat nominal point-floor
(which false-rejects a perfectly calibrated band ~39–50% of the time at EVERY n) and ⛔ never
reverse-engineered from an observed value (NF-D22). A degenerate satisfying the floor is fine — the
proper score eliminates it — and the floor is ⛔ never tightened above nominal "for safety", nor
used to break a tie (both are monotone in widening: `degen_wide` would win them, NF1.8).

### 7.4 The anomalous-season sensitivity — registered, and its applicability measured

> Spec AC-3 requires "the leave-one-anomalous-season sensitivity (the 2.7% COVID season moved
> MH2.8's per-fold SNR ~5×) is registered and reported".

**Registered. And measured as INAPPLICABLE-BY-CONSTRUCTION on the decisive population:** the
served champion era is 2026-06-23 → 2026-08-30 and contains **no 2020 season** — indeed no season
boundary at all. Running a "leave-one-COVID-season-out" on it would be a vacuous anchor reported as
a passed test (NF1.7 (a)). The applicable analogue, which asks the identical question — *does one
anomalous chunk carry the result?* — is a **LEAVE-ONE-BLOCK-OUT sensitivity over the 5 date
blocks**, and that is what is run and reported on the served population. Where the BACKTEST context
read spans seasons the COVID season IS present, and the leave-one-COVID-season sensitivity is run
and reported there, labelled BACKTEST.

### 7.5 The negative control mirrors the SHIP RULE's margin (MH2.8's second defect)

⛔ Not a bare "which arm is closest". On CLEAN synthetic data — outcomes drawn from the incumbent's
own predictive, so there is no shape defect to find — the control reports the fraction of
replicates in which **the full ship rule of §8 produces a SHIPPABLE margin**. **Bar: ≤ 0.05.**

### 7.6 The vacuity floor (MH2.6) — the harness proves it CAN fail

Both are reported, and both must pass before any real-data verdict is read:

| leg | bar |
|---|---|
| clean-data false-positive rate (§7.5) | ≤ 0.05 |
| detection rate on a PLANTED GROSS defect (skew-normal α = 4.0), over 20 replicates | ≥ 0.80 |

A harness combining a Monte-Carlo null with a multiplicity correction has three compounding ways to
return "within noise" for every input including a catastrophically broken model. Below a certain
replicate count NO statistic can clear the correction — a machine that passes everything.

### 7.7 Reproducibility

The **GLOBAL RNG is seeded** (`SEED = 42`) for every stochastic component — `NGBRegressor(random_state=…)`
does not seed its base learner, and identical-spec fits have been measured to disagree by up to 0.30
in per-game σ (MH2.5). Reproduction pins at **1e-9**. The committed fixture is regenerated from the
committed code before it is committed (NF-INJ3b D3: an artifact whose `generated_at` precedes its
generating module's first commit is a provenance defect).

---

## 8. THE SHIP RULE — registered forward, deterministic, order fixed

An arm SHIPS only if **ALL** of C0–C10 hold. Nothing below reads a result to choose a branch.

| # | clause | bar |
|---|---|---|
| **C0** | **REPLICATION** (§3) — the FULL-ERA read replicated | else **STOP**; no clause below is evaluated |
| **C1** | **NOT COLLAPSED** (§6.2) — a genuine mixture on a majority of blocks | collapse ⇒ TIE, refuses to count |
| **C2** | **ASYMMETRY (primary)** — paired lift over `foil_k1` on `p_over_gap_abs` | 95% CI excludes 0 **AND** point ≥ 0.20 × the incumbent's own gap |
| **C3** | **PROPER SCORE NOT DEGRADED** — `crps` vs `foil_k1` | paired CI not materially adverse (MH2.8: flat calibration bought at a materially worse predictive FAILS) |
| **C4** | **FIDELITY** — `pit_ks` vs `foil_k1` | not materially worse |
| **C5** | **COVERAGE FLOOR** — `cov80` | ≥ `power_floor(n, 0.80, 0.05)` (§7.3) |
| **C6** | **FOLD CONSISTENCY** | `cv_power.fold_consistency_clause(n_folds=5)` ⇒ ≥ 4 of 5 |
| **C7** | **DEFLATION** | PBO (field-level) < 0.20 **and** DSR > 0.95, `V` as declared in §5.3 |
| **C8** | **MULTIPLICITY** | BH across the 4 trial arms on the primary (§5.5) |
| **C9** | **MECHANISM ATTRIBUTION** | `ctrl_symmetrized` must NOT reproduce the win (§5.4) |
| **C10** | **OWN-FORM ORACLE FLOOR** | the arm does not beat its OWN-form peeking oracle at matched n (§5.4) |

**Materiality** is a paired 95% bootstrap CI excluding 0 (every arm scores the same outcomes).
Demonstrable ≠ material (NF-W6): a statistically demonstrable but immaterial lift does not ship.

### 8.1 What a failure means, and what it does NOT

The verdict is classified with `cv_power.classify_null(declared_field_size=4,
degenerates_excluded_from_v=True, pbo_application="field")`, and the classification is read from
the machine flags. Registered readings:

- A refusal by a **HARD CONSTRAINT** (C1 collapse, C9, C10) classifies **`CONSTRAINT_REFUSED`** —
  the remedy is a different mechanism or a PM decision, ⛔ **NEVER more data**, and ⛔ **no
  fold/season re-test trigger is published** (NF-D18).
- A **`DSR_UNREACHABLE`** reading is NOT automatically a field-composition story. The 2×2
  (series × field) is MEASURED before any remedy is named: if `V` falls hard and DSR barely moves,
  the binding quantity is per-fold VARIANCE, not multiplicity, and prescribing a coherent
  re-registration would burn a story on the wrong lever (NF-W7f). ⛔ No post-hoc trim, ever
  (MH2.2), and ⛔ never a trim that would delete the winner (NF-W7h).
- If a statistical gate AND a hard constraint both fail, the **CONSTRAINT BINDS** and the
  statistical shortfall is reported beside it — not hidden, not used to publish a fold trigger.
- ⛔ **No gate is re-read on a different statistic, a different field, or a different population
  after seeing it fail** (E2.1-r, absolute).

---

## 9. ⭐ OBLIGATION 3 — the `std_pred` DISAMBIGUATION, by file:line

> **Verbatim (spec AC-1):** *"the `std_pred` DISAMBIGUATION: two statistics share the name
> (`validate_v2_gates.py:34` mean-spread vs `train_totals.py:121` predictive SD) — the prereg
> states which one every gate reads, by file:line."*

| name | definition | source | what it is a property of | read by any gate here? |
|---|---|---|---|---|
| `std_pred_meanspread` | `STDDEV(p.pred_total_runs)` | **`betting_ml/scripts/validate_v2_gates.py:34`** | **μ ACROSS games** — the V2 gate's `≥ 2.0` reading | ⛔ **NO** — see §10 |
| `std_pred_predictive_sd` | `mean(sqrt(mu + mu²/r))` in `_std_pred(mu, r)` | **`betting_ml/scripts/train_totals.py:121`** | the PREDICTIVE SD of one game | ⛔ **NO** — reported as context only |
| `var_z_pooled` | pooled variance of `z = (y − μ)/σ` | this study | whether the served σ SCALE is right | ✅ **yes** — and ONLY in the SHAPE-MATCHED null of §7.2 |

**Every dispersion-touching gate in this study reads `var_z_pooled`, and neither `std_pred`.** Both
line references were verified in this worktree at kickoff (`grep -n`), not copied from the spec.

---

## 10. ⭐ OBLIGATION 4 — SCOPE: DISCRIMINATION is untouched

> **Verbatim (spec AC-1):** *"the SCOPE statement: DISCRIMINATION (`Var(mu)/Var(y)=0.0142` vs the
> `>=2.0` gate) is untouched by any shape fix; its attainability stays a named OPEN question on the
> epic — this story makes no claim on it and no gate reads it."*

Every arm in this study holds **μ EXACTLY at the served value**. The location channel is therefore
**ARM-INVARIANT BY CONSTRUCTION**: no arm here can move `Var(μ)/Var(y)` (TV2-0: **0.0142**) or
`STDDEV(pred_total_runs)` (**0.544** against the V2 gate's **≥ 2.0**), and registering a gate
against a statistic no arm can move would ship décor (NF-MARGIN2).

**This story will fix the probability the product PRINTS. It will not make the model better at
telling a high-scoring game from a low-scoring one.** Whether 2.0 is even attainable for a totals
model is not something this market-blind study can measure, and it stays a named OPEN question on
the epic. No claim is made on it and no gate reads it.

Its null state is **`INACTIVE (structural)`** — the remedy is a different population or a different
mechanism, ⛔ never more served games (NF-D18 / E7.15).

---

## 11. What this study cannot say, written before it is run

- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; `bet_paused` stays `true`.
- Nothing about a **different champion**. The population is `v6`/`pre_lineup_v6` (fit 2026-06-23);
  MH2.6's boundary is respected, not stretched.
- Nothing about **DISCRIMINATION** (§10).
- MH2.8's `INCUMBENT_STANDS`, TV2-0's INACTIVE feature lever and MH2.10's anti-informative
  σ-partition all **STAND AS RECORDED**. This study registers a NEW coherent family forward. It
  does not re-cut, re-read or relax any recorded gate.
- A clearing verdict is **DEPLOY-HELD**. Per MH2.1 a model-registry merge to `main` IS the deploy
  and no promotion gate exists — so nothing merges to `main`, no registry entry changes, and
  `deploy.sh` is not run. The merge decision is the operator's.
- **A null that closes the shape question honestly is a valid outcome**, and is reported with its
  MDE and its null STATE, never as a shrug.

---

## 12. AMENDMENT 1 — the DEFLATION SERIES (filed BEFORE any scoring)

**Filed 2026-08-31, before any statistic involving a realized outcome was computed on this
population.** §8 C7 named a PBO bar and a DSR bar but did not name the SERIES each reads. That is a
specification gap of exactly the kind that only becomes interesting after a result, so it is closed
now rather than settled later (E2.1-r; NF-INJ3b: a pre-registration must name its deflation
conventions, not just its arms, folds, metric and thresholds).

### 12.1 PBO and DSR want DIFFERENT series — NCAAF-P2.1 measured the cost of sharing one

CSCV/PBO needs MANY buckets; DSR needs LOW-NOISE INDEPENDENT observations. NCAAF-P2.1 measured a
real effect whose per-BUCKET Sharpe was ~3× below its per-FOLD Sharpe — the same effect on the same
folds, the gap being the SERIES DEFINITION alone — and sharing one series silently taxed DSR.
Registered, separately:

| gate | series | n |
|---|---|---:|
| **DSR** | per-BLOCK paired lift over `foil_k1` on the PRIMARY statistic | 5 (= `N_BLOCKS`) |
| **PBO/CSCV** | per-DATE-BUCKET `−p_over_gap_abs` over 16 contiguous buckets, 16 CSCV splits | 16 |

⛔ Neither gate is re-read on the other's series after seeing it fail.

### 12.2 Three PBO readings, and which BINDS

NF1.8 requires PBO over the ELIGIBLE set — the search the selection actually ran — not over every
config scored; NCAAF-VAL3 measured that an eligible-set PBO can be WORSE than the declared-field
one, so the two-arm decision is reported as a diagnostic and never as a rescue.

| reading | configs | role |
|---|---|---|
| `declared` | all 8 in `n_trials` | reported |
| **`eligible`** | the **4 TRIAL arms** — the search the selection ran | ⭐ **BINDS** |
| `two_arm` | winner vs `foil_k1` — the decision actually taken | reported as a diagnostic |

⚠️ Registered forward: at 4 configs PBO is STRUCTURALLY COARSE (a middle finish already counts as
an overfit event), so a high eligible-set PBO over near-clone arms is read as the signature of a
TIE, not of overfitting — and the discriminator is the SPREAD, reported beside it (NF1.8; the
E2.1-r tied-field reading). ⛔ This is a reading registered in advance, never a post-hoc rescue,
and ⛔ no field is trimmed at any point (MH2.2), least of all one that would delete the winner
(NF-W7h).

### 12.3 The lockstep check is computed, not felt

`cv_power.lockstep_variance_lever` is EXECUTED on the winner's own numbers and reported. A design
change that scales every arm's per-fold dispersion by a common factor scales the winner's `SR` and
the benchmark `SR0` in LOCKSTEP, so the sign of `SR − SR0` is invariant: "get a lower-variance
design" is deterministically void as a remedy (NF-W8-0d). If `DSR_UNREACHABLE` fires, ⛔ no
fold/season/row re-test trigger is published.

### 12.4 What this amendment does NOT do

It changes no bar, no arm, no population, no primary statistic and no ship clause. It names series
that §8 left unnamed. Nothing had been scored when it was filed, and the commit order is the proof.

---

## 13. AMENDMENT 2 — the per-fold SERIES is a PROPER score (filed BEFORE any scoring)

**Filed 2026-08-31, before any statistic involving a realized outcome was computed on this
population — forced by the VACUITY CONTROL of §7.6, which is exactly what it is for.** TV2-0 filed
its own node-2 amendment for the same reason: *"the controls PROVED a single yardstick cannot
separate the levers."*

### 13.1 `|p_over_gap|` per block cannot be the per-fold series

`p_over_gap = mean(stated) − mean(over)` is additive per row, so `over_i` cancels EXACTLY between
two arms scored on the same rows. **`|·|` has a KINK at zero and destroys that cancellation** in
any block whose realized rate happens to fall between the two arms' stated values — and at ~106
rows a block's realized rate carries an SE of **0.049** against an effect of **0.073**.

Measured on the committed fixture, same arms, same data:

| reading | point | paired 95% CI | fold wins |
|---|---:|---|---:|
| `|gap|` per block | +0.0436 | **[−0.0391, +0.0524]** — spans zero | 3/5 |
| MOVEMENT of the printed probability | +0.0518 | **[+0.0512, +0.0525]** | 5/5 |

### 13.2 What replaces it — and why not the MOVEMENT series

**C2 (the PRIMARY asymmetry clause) is read exactly as TV2-0's ASYMMETRY CHANNEL** — the MOVEMENT
of the stated probability, in which the realized over-rate cancels EXACTLY, gated on the
incumbent's SIGNED gap being materially non-zero (TV2-0 §3 registered precisely this construction
and measured `[0.0724, 0.0732]` with it). C2 additionally requires the move to actually REDUCE the
pooled `|gap|` and to close ≥ `MATERIAL_SHARE` of it, so an overshoot cannot pass on magnitude.

⛔ **The MOVEMENT series is NOT the DSR/fold series: it has NO correctness content.** Measured —
every arm wins 5 of 5 folds on movement with a Sharpe of 5.5–12.7, *including arms that overshoot*,
because moving the number always "wins" regardless of direction. A gate every arm passes by
construction is décor (NF-MARGIN2).

⭐ **The DSR and fold-consistency series is the per-ROW BRIER score of the printed probability**,
`(stated_i − over_i)²`, as an improvement over `foil_k1`. It is PROPER (an arm that moves the
printed number the WRONG way is penalised), per-row, and paired on the same `over_i`. Registered
for both `dsr` and `fold_consistency`; the PBO bucket series of §12.1 is unchanged.

---

## 14. AMENDMENT 3 — `N_BLOCKS` and the FIELD-LEVEL PBO (filed BEFORE any scoring)

Also forced by the vacuity control, and both defects are ones this repo has already paid for once.

### 14.1 ⭐ At `N_BLOCKS = 5` the multiplicity clause was STRUCTURALLY UNPASSABLE (E7.14)

A signed-rank test over `n` folds has a minimum attainable one-sided p of `2^-n`. The BH threshold
for the smallest of 4 p-values at α = 0.05 is **0.0125**. At `n = 5` the floor is **0.03125** —
**above the cutoff, so NO EFFECT OF ANY SIZE could pass C8.** This is E7.14 verbatim ("the fold-SIGN
floor `2⁻ⁿ` can sit ABOVE the BH cutoff so no effect of any size could pass"), and
`cv_power.folds_for_sign_certifiability(0.0125)` returns **7**. §2.3 checked the DSR ceiling, the
fold clause and PBO evaluability for reachability and did not check this one; the control caught it.

**`N_BLOCKS = 8`, by a rule stated forward:** the SMALLEST `n` at which the sign floor is ≤ HALF the
BH cutoff (margin, so a borderline p can still clear) AND the fold clause's false-fire rate is
≤ 0.20. Measured: `n = 7` → floor 0.0078 (0.62 of the cutoff — no margin); **`n = 8` → floor 0.0039
(0.31), fold clause 6 of 8, false-fire 0.145, `dsr_ceiling` 0.9999.** Derived from `n` and the GATE
SET alone — a design quantity known before any result (NF1.8), ⛔ never chosen to make a gate pass.

**Its power, stated in the unit that grows:** at 106 rows/block the per-block realized rate has
SE 0.049, so against TV2-0's measured 0.0726 gap the per-block win probability is 0.773 and the
**fold clause's power is 0.735**. ⇒ a C6 failure at this design is ~1-in-4 under a TRUE effect of
the measured size and must be read as POWER-LIMITED, not as absence.

### 14.2 C7 carries DSR only — PBO is FIELD-LEVEL and never a per-arm veto

§5.5 registered `pbo_application = "field"` and said PBO is "⛔ never carried as a per-arm pass/fail".
The first cut of the ship rule contradicted its own registration by ANDing `pbo_pass` into C7. That
is the defect MLB-HV2-1 MEASURED: a planted 6-percentage-point effect drove PBO to 0.426 *precisely
because* it made the arms near-clones, so the per-arm reading VETOED a real, large effect —
NF1.8's lesson that a high PBO over a near-clone field is the signature of a **TIE**, not of
overfitting, and `classify_null` refuses to convert a field-level refusal into a per-arm verdict.

**C7 = `dsr_ok` alone.** PBO is computed under all three readings of §12.2, reported at the FIELD
level beside the verdict, and read as a field diagnostic. ⚠️ Registered forward: this field is FOUR
arms expressing ONE marginal shape, i.e. near-clones by construction, so a HIGH eligible-set PBO is
the EXPECTED reading and is not evidence against the mechanism.

### 14.3 What amendments 2 and 3 do NOT do

They change no bar, no arm, no population, no primary statistic, no ship clause and no threshold.
They fix a series that could not carry a signal, a fold count at which a registered gate was
unpassable, and a line of code that contradicted its own registration. Every one was found by a
CONTROL before any realized outcome on this population was read, and the commit order is the proof.

---

## 15. AMENDMENT 4 — the per-fold series, C8's statistic, and C10's anchor (BEFORE any scoring)

All three defects were found by the VACUITY CONTROL of §7.6 running on PLANTED data over the real
served `(μ, σ)` — **no realized outcome on this population had been read**, and the commit order is
the proof. Each is a defect this repo has already paid for once.

### 15.1 The per-fold series is the per-ROW CRPS improvement

§13 replaced `|gap|` with the per-row BRIER score. Measured, the Brier series is still too coarse
for a FOLD-level test: **the printed probability is a property of the BLOCK'S LAW, so it is
CONSTANT within a block** — a Brier series therefore carries ~ONE effective observation per fold.

| per-fold series | fold clause on a PLANTED GROSS defect | on CLEAN data |
|---|---:|---:|
| per-block `|gap|` | 3/5 typical | — |
| per-row BRIER | **4 of 6** | 0 of 6 |
| ⭐ per-row **CRPS** | **6 of 6** | 0 of 6 |

**Registered: the per-fold series (for `fold_consistency` and the DSR return series) is the
per-ROW CRPS improvement over `foil_k1`** — a proper score of the DENSITY the mixture actually
changes, which TV2-0 measured the shape oracle improves (2.5301 → 2.5114). It is two-sided: it
detects the planted defect 6/6 and fires on clean data 0/6. The Brier series is still REPORTED.

### 15.2 C8 corrects the statistic that carries the CLAIM

The first cut tested a per-fold signed-rank for multiplicity while C2's claim lived in a pooled
statistic with ~100× the resolution. **A multiplicity correction must be applied to the statistic
that carries the claim.** Registered: **C8 is BH across the 4 trial arms on C2's OWN paired
bootstrap p-value** (one-sided, `+1` corrected). The per-fold signed-rank p is REPORTED beside it,
never binding.

⚠️ **The N_BLOCKS = 8 choice of §14.1 was derived to make a per-fold sign test clear the BH cutoff.
This amendment retires that premise.** A re-derivation of `N_BLOCKS` would now be legitimate
*forward* — and it is **deliberately NOT done**, because it is being contemplated *after* observing
a DSR of 0.948 against a 0.95 bar, and re-tuning a design quantity at that moment is the E2.1-r
inversion whatever the premise. `N_BLOCKS` stays **8**, as registered.

### 15.3 C10's anchor needed a TIE BAND, and at this `n` it is INACTIVE

Both C10 anchors sit at the peek's `n` (~106 out-of-block rows), so the comparison is same-FAMILY
and same-SAMPLE (NF1.7 (b) / NF1.9 (f)) and the clause is a METRIC-INVERSION detector: a peek that
LOSES to an honest fit at its own `n` means the metric is inverted.

Two corrections: **(a)** the first cut required the FULL-`n` arm not to beat the peek — but the
honest arm trains on ~745 rows against the peek's ~106, so beating it is **CAPACITY, not leakage**,
and NF1.9 (f) is explicit that such a win is admissible. That cut vetoed live arms. **(b)** the tie
band was `1e-6` against a statistic whose SE at this `n` is **0.017**, so the anchor pair read
ACTIVE on pure noise. Measured: **22 of 24** peek-minus-control differences sit inside one SE.
**Registered: the tie band is ONE SE of the primary statistic at this `n`** — a design quantity
from `n` alone. NF-W6d: an anchor pair that TIES is **INACTIVE**, not a refusal; NF-D20: an
inactive anchor is UNINFORMATIVE and is reported beside the pass count, never as a pass.

---

## 16. AMENDMENT 5 — the VACUITY FLOOR reads the PLAT-CVP1 taxonomy (BEFORE any scoring)

§7.6's floor asked for a "detection rate on a planted gross defect ≥ 0.80" and §7.5 defined the
clean rate on the FULL ship rule, so by symmetry the gross rate was also read on the full rule.
Measured, that conflates two different questions — and the spec itself names the answer:
*"expect `DEFLATION_REFUSED` as a reachable state."*

The helper's own taxonomy separates them: **`VACUOUS` means an arm survives the NO-EFFECT payload**
(the family certifies noise); **`DEFLATION_BLOCKED` means every METRIC gate fires on a planted
effect while the deflation half blocks** — a reachable, reportable state, not a broken harness.

Registered:

| leg | statistic | bar |
|---|---|---|
| negative control (CLEAN payload) | the **FULL ship rule** produces a shippable margin | ≤ 0.05 |
| gross-defect detection | every **METRIC** clause (all of C0–C10 except C7) fires | ≥ 0.80 |
| the deflation half | the **PLAT-CVP1 verdict**, executed | reported, `DEFLATION_BLOCKED` reachable |

Both legs report the FULL ship rate and the PER-CLAUSE detection rate, so a failure NAMES the
clause that is power-limited instead of condemning the whole harness.

⚠️ **Registered forward, so it cannot be discovered later: at this design a planted GROSS defect
(skew-normal α = 4.0, closing ~100% of the printed gap) yields DSR ≈ 0.92–0.95 against the 0.95
bar.** The deflation half is therefore expected to be the binding clause, and a `DEFLATION_BLOCKED`
outcome on the real data would be a statement about the DESIGN's power at 8 folds, ⛔ not evidence
against the mechanism. The DSR bar is **NOT** moved: 0.95 is the program standard, and lowering a
registered threshold because it blocks is the E2.1-r inversion.

---

## 17. AMENDMENT 6 — two wiring corrections, filed AFTER the decisive run (and why that is admissible)

⚠️ Unlike §12–§16, this amendment is filed **after** the decisive run. Both changes make the
verdict **STRICTER** and both restore what was already registered; neither relaxes a bar, moves a
threshold, re-cuts a field or re-reads a gate. **The direction is the test** — refusing to make a
correction that turns a `SHIP_CANDIDATE` into a refusal would itself be the E2.1-r inversion, in
the direction that favours the result.

### 17.1 A FIELD-LEVEL deflation refusal governs the STUDY verdict

**§8 C7 as originally registered:** *"PBO (field-level) < 0.20 **and** DSR > 0.95."*

Amendment 3 removed PBO from C7, citing the PM convention that PBO/CSCV must never be carried as a
per-arm pass/fail (MLB-HV2-1 measured that a per-arm reading VETOES a real, large planted effect).
**That over-applied the convention.** "Not a PER-ARM veto" is not "not a gate": a field-level
statistic refuses the **FIELD**, and `classify_null` implements exactly that — it returned
`DEFLATION_REFUSED` with `pbo_application_admissible = True` and `pbo_refusal_admitted = True`
while the per-arm table showed arms clearing their own clauses.

**Corrected:** PBO never touches an arm's clause table (unchanged), and a field-level refusal
governs the STUDY verdict. Measured: **all three registered readings fail** — `declared` 0.221,
`eligible` 0.771, `two_arm` 0.250 — so the refusal does not hinge on which reading binds.

### 17.2 The PLAT-CVP1 helper partitions gates BY NAME, and this study's names shared none

The helper splits a study's registered gates into deflation-class and metric, and **`BLIND` and
`DEFLATION_BLOCKED` are OPPOSITE readings** — `BLIND` says a null from this family is free;
`DEFLATION_BLOCKED` says every metric gate fired and only deflation stopped it. The intersection of
its default names `{cscv, deflated_sharpe, dsr, pbo}` with this study's clause names
(`C0_replication` … `C10_own_form_oracle_floor`) is **EMPTY**, so the default call filed
`C7_deflation` as a METRIC gate and returned **`BLIND`** — for a family whose own `blocking_gates`
showed every arm clearing every metric clause.

**Corrected** by passing `deflation_gates={"C7_deflation"}` — the partition §5.5 already REGISTERED,
not one discovered afterwards. Verdict moves **`BLIND` → `DEFLATION_BLOCKED`**, with all four arms
in `metric_survivors`. This is the state the spec named in advance.

⭐ Carried to closeout as an instrument finding: the helper's verdict silently inverts for any study
whose gate names do not use its vocabulary, and nothing warns.

### 17.3 What did NOT change

The population, the arms, every bar, the primary statistic, `V`-membership, the BH family, the
per-arm clause table and every recorded number are untouched. The decisive battery was re-run and
reproduces the recorded figures at **1e-9** (`winner`, `dsr`, `observed_sr`, `pbo`,
`incumbent_gap`). The control block was REUSED from the completed run and that reuse is RECORDED in
the artifact — the controls depend only on the served `(μ, σ)` and the registered seed, both
unchanged.
