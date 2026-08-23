# NF-INJ3b — pre-registration: a FRESH forward registration of the injury-games caps

**Committed BEFORE any arm was scored under this registration.** ⛔ Not edited after a result
(E2.1-r). Anything the decisive run overturns is left in place verbatim under a `SUPERSEDED`
marker (NF-W7f).

`best_alpha = 0`. **DEPLOY-HELD**: nothing here serves until the gated ship path passes AND the
operator records a disposition.

Spec: `plan_specs/nfl_fantasy/nf-inj3b.yaml`. Parent: NF-INJ3
(`ablation_results/nf_inj3_injury_games.md`, PR #1003, `POWER_LIMITED`, PM-closed 2026-08-22).
This story is that null's **sanctioned successor** under the PM's recorded ruling **D2 = A**.

---

## 0. Why this study exists — and what it is NOT

NF-INJ3 measured the served caps `{RES: 4.0, PUP: 4.0, NFI: 4.0, SUS: 7.0}` at blend 0.7 to be
roughly **twice** what any fitted form says: every real arm beat the incumbent on the mean,
pooled expected games 5.403 (incumbent) vs 2.387–2.607 (fitted arms), and **22 of 22** flagged
draftable veterans on the live 2026 board move DOWN.

It nevertheless returned a null, and the null did **not** rest on the evidence or on any
threshold. It rested on two things the pre-registration **left unstated**:

* **`V`'s membership.** NF-INJ3 declared DSR-CONV (degenerates ∉ `V`) and never invoked
  MH2.1 (a) — so the `incumbent` REFERENCE arm's identically-zero trial Sharpe sat inside `V`
  and inflated it.
* **The BH family.** NF-INJ3 said "survives BH-FDR at the family's q" and never named the family.

⭐ **A pre-registration must name its DEFLATION CONVENTIONS, not just its arms, folds, metric and
thresholds.** Those two items are as load-bearing as any threshold, and they are exactly the
details that only become interesting AFTER a result — i.e. the ones you can no longer set. This
registration names them, up front, in §3 and §6.

### ⚠️ HONESTY CLAUSE — binding registration item (6), stated before anything is scored

**This story buys a PROPERLY-REGISTERED RECORD and an HONEST BH ANSWER. It does not buy new
evidence, and it must never be written up as though it does.**

The *direction and magnitude* of the effect are already public in NF-INJ3's record; re-running
the same harness on the same data cannot confirm them a second time. Seven of nine NF-INJ3 gates
passed and will pass again; a pass here is a **reproduction**, not a corroboration. If the study
clears, the report says so in those words. ⛔ **A foregone gate outcome is never presented as
fresh confirmation.**

### ⚠️⚠️ AND THE HALF OF THAT CLAUSE THAT CUTS THE OTHER WAY: **DSR IS *NOT* FOREGONE HERE**

NF-INJ3's report carries a diagnostic figure of **0.973** — DSR recomputed with the reference arm
removed from `V`. It is tempting (and the parent's PM note flags exactly this temptation) to treat
NF-INJ3b as "the story where DSR already reads 0.973". **It is not, and registering it that way
would be wrong twice over:**

1. **`V` is a SAMPLE VARIANCE over the field's trial Sharpes, so it moves NON-MONOTONICALLY with
   the field's MEMBERSHIP.** DSR-CONV already documents that dropping a NEAR-MEAN arm *widens*
   `V` and *raises* the bar. NF-INJ3b's field is not NF-INJ3's field (§2), so **0.973 is not
   inherited and is not this study's expected value.** NF-INJ3b's DSR is genuinely unknown until
   it is computed under this registration, and it may be **worse** than the parent's registered
   0.8913.
2. **A diagnostic DSR does not transfer to a narrower field, and computing a MENU of per-candidate
   -family DSRs to choose the family is the MH2.2 laundering wearing a successor's badge.**
   NF-INJ3 deliberately computed none, and said so. **Neither does this registration**: the field
   in §2 is declared on MECHANISM, and no DSR of any kind is computed until this document is
   committed.

⇒ the registered expectation is: **the substantive gates reproduce; DSR is an open question; BH
gets its first honest answer.**

---

## 1. What is unchanged from NF-INJ3, and why

Everything about the DATA and the SCORING is inherited **byte-identically**, and that is
deliberate: the only thing NF-INJ3b changes is the REGISTRATION. The harness modules
`nf_inj3_injury_games.py` and `run_nf_inj3_injury_games.py` are **imported read-only and not
edited** — a post-decision story writes to its OWN output paths and never mutates a decided
story's code or artifacts.

Inherited verbatim (see NF-INJ3 §2–§4 for the full derivations, which stand):

* **Population** — one row per (target season Y, player) on that season's MVP-1 veteran board with
  a Y week-1 roster status in {RES, PUP, NFI, SUS}; rookies and returners (`seasons_missed ≥ 1`)
  excluded for the reasons NF-INJ3 §3 records.
* **Outcome** — realized games from the warehouse (`fct_player_week`), never from a projection
  panel; the model's own `proj_games` from the single-vintage 2016–2025 build (NF-D10).
* **Metric** — EXACT discrete CRPS over {0..n_Y}. ⛔ **MAE is disclosed and NEVER selects**, and
  that is MEASURED, not assumed: on this cohort the all-zero nihilist WINS MAE, so MAE is
  demonstrably inverted here (NF-D11 / NF-D14).
* **Shared predictive family** — one `Beta-Binomial(n_Y, μ, φ)` with a single φ fitted in-fold
  **under the INCUMBENT's mean** and held byte-identical across arms, so the arms differ ONLY in
  μ and the nuisance is generous to the thing being challenged.
* **Folds** — expanding window, eval Y ∈ 2019…2025 (**7 folds**), fit on 2016…Y−1.
* **The two structural INACTIVITIES, re-declared forward (NF-D20):** `NFI` has ZERO rows
  historically and ZERO on the 2026 serving cohort — its cap is unfittable and **INACTIVE**; and
  the cap never reaches a ROOKIE (`injury_availability_games` runs inside `project_veterans`).
  No arm may claim credit on either.
* **The scope limit on "timing"** — there is no designation DATE anywhere in this stack; the
  onset PROXY (`onset_carryover`, `weeks_since_last_game`) is what is measurable, and no result
  here is evidence about a designation date.

### Binding registration item (5) — the ERA FLOOR is a DATA-FIDELITY quantity

**Training and evaluation start at season 2016.** Pre-2016 the weekly roster feed is not a weekly
snapshot: it is a season-**END** status backfilled onto every week, so a "week-1" label is
**outcome-contaminated**. NF-INJ3 §8 measures it — a week-1 `RES` player pre-2016 plays a MEDIAN
of six games and is *never* seen `ACT` later (share 0.000 in every pre-2016 season), against a
median of 0 and a 0.62–0.92 zero rate from 2016 on.

⭐ The floor is therefore derived from a property of the FEED, not from any outcome or any result,
and it is re-declared here rather than inherited silently because it **bears directly on the
incumbent**: `_INJURY_STATUS_GAMES_CAP`'s own docstring fits its constants on **2015–2024**, i.e.
with **one contaminated season inside the window**. Training on that season would make the
incumbent look right.

⛔ The floor is NOT a tuning knob and is not revisited by this study under any outcome.

---

## 2. Binding registration item (4) — THE FIELD, DECLARED ON MECHANISM, BEFORE ANY DSR

**The mechanism under test:** *the served per-status injury-games LEVEL is mis-set for flagged
veterans, and an in-fold fitted availability model corrects it.*

The coherent family is therefore **every form that fits that availability level in-fold on the
same population through the same shared predictive**, plus the reference it must beat and the two
degenerates that must lose. Membership is decided by that sentence and by nothing else.

### Arms — `DECLARED_FIELD_SIZE = 6`

| arm | role | what it is |
|---|---|---|
| `incumbent` | **REFERENCE** | the shipped `{RES:4, PUP:4, NFI:4, SUS:7}` at blend 0.7 — the thing to beat |
| `fitted_status` | arm | the SAME functional form, per-status level + blend fitted in-fold — the minimal expression of the mechanism |
| `timing_aware` | arm **+ MATCHED FOIL** | one Beta-Binomial GLM for the conditional mean on status + the onset proxy + base covariates — i.e. the primary with the availability SPLIT removed and nothing else changed |
| **`hurdle_transfer`** | **PRIMARY** | the NF-W2/W2b/W2d transfer: an explicit availability hurdle, `P(plays ≥ 1) × E[games \| plays ≥ 1]`, on **identical covariates** to `timing_aware` |
| `all_zero` | **DEGENERATE** | μ = 0 for every flagged player (NF-D11's nihilist). MUST lose |
| `no_cap` | **DEGENERATE** | the uncapped stale durability estimate — the mechanism removed. MUST lose |

### Excluded from the family ON MECHANISM: `sus_regime`

`sus_regime` is not another way to fit the availability level — it is a **per-status REGIME
carve-out** for `SUS`, and `SUS` is **structurally inactive on the population this study is
registered to serve**. Measured in NF-INJ3 §3 and re-declared here forward (NF-D20 — count the
rows the mechanism can act on BEFORE crediting anything):

* **0** `SUS` rows on the 2026 serving cohort (22 flagged veterans: 14 `RES`, 8 `PUP`);
* **11** `SUS` rows across all seven eval folds, **all of them in 2019–2020** — so the arm cannot
  act on **5 of the 7** folds, and cannot act on a single served row.

Registering it would make the whole field pay multiplicity for an arm that is inert exactly where
the claim lands. ⛔ It is excluded because of that structure, **not** because of any score.

> ⚠️ **AND THE NARROWING IS DECLARED TO BE ADVERSE, WHICH IS THE POINT.** NF-INJ3's trial Sharpes
> are already public: `sus_regime` 0.475 sits essentially ON TOP of `fitted_status` 0.4779, i.e.
> it is a NEAR-MEAN arm — and DSR-CONV documents that dropping a near-mean arm **WIDENS** `V` and
> **RAISES** the bar. So this exclusion, qualitatively, works **against** the study's own
> interest. That is stated here, before scoring, precisely so the narrowing cannot be read as
> chosen for its effect on the gate. ⛔ **No DSR was computed for this or any other candidate
> field before this document was committed.**

### Anchors — scored, never shippable. A missing or unfittable anchor RAISES (NF1.7 (a))

* **Per-FORM peeking oracle** (NF-D16 g‴) — each arm floored by the peeking version of its OWN
  form. The forms NEST, so a single field-wide ceiling would falsely veto a legitimately better
  nested form.
* **Matched-n control** (NF1.7 (b) / NF1.9 (f)) — the primary's own form trained on ONE prior
  season, so the oracle floor is enforced at equal family AND equal resolution.
* **`permuted_timing`** — the onset covariates shuffled within (status × season); player linkage
  destroyed, marginals preserved. The primary carries those covariates, so this anchor binds on
  the primary and must be beaten.
* **`pooled_mean`** — one in-fold pooled mean for every flagged player, status ignored.

### Binding registration item (3) — the PRIMARY is `hurdle_transfer`, and it is REGISTERED, not selected

Per the PM's recorded ruling D2 = A ("the **hurdle** form as primary"). Mechanistically: NF-W2's
certified weekly FEATURES cannot transfer at all (its source has no preseason rows and no 2026
rows), but its measured FINDING — *the lift lives in the zero/availability leg* — is a portable
hypothesis about WHERE the signal lives, and an explicit hurdle is its season-target expression.

⭐ **Every gate below is computed on the PRIMARY, not on the field's argmin.** If some other
eligible arm posts a lower pooled CRPS, that is recorded as a leaderboard fact and the study does
**not** switch to it — a shipping arm chosen after the scores is a search this registration did
not declare. (This is strictly stronger than NF-INJ3, which selected the argmin.)

---

## 3. Binding registration item (1) — `V`'s MEMBERSHIP, named up front

`SR0 = √V · z(N)`. The two channels are set independently and each is declared here:

* **`N` = `n_trials` = `DECLARED_FIELD_SIZE` = 6.** Every declared arm pays FULL multiplicity,
  including both degenerates and the reference. Nothing is trimmed from `N` under any outcome.
* **`V` is measured over `{fitted_status, timing_aware, hurdle_transfer}` — the three
  non-degenerate, non-reference arms.** Two exclusions, each on a convention this program already
  owns, both declared BEFORE any score:
  * **DSR-CONV** — the two pre-registered lose-by-construction DEGENERATES are excluded from `V`
    (they remain in `N`). They are named degenerate in §2 above, before any score; declaring one
    after it loses is laundering.
  * **MH2.1 (a)** — the `incumbent` REFERENCE arm is excluded from `V`. Its skill series is
    identically zero **by construction** (it is the baseline every lift is measured against), so
    its trial Sharpe is a structural 0.0 that inflates a small family's `V` exactly as a
    diagnostic anchor does. This is the convention NF-INJ3's registration omitted, and it is the
    single specification change that separates this study's registration from its parent's.

⛔ **`V`'s membership is fixed by this section and is not re-cut under any outcome** (MH2.2). The
2×2 diagnostics the harness computes stay diagnostics: they name a lever, they never license a
re-read (E2.1-r). In particular, a DSR reached by deleting the arm under test is INADMISSIBLE and
is refused rather than reported (NF-W7h).

---

## 4. The primary metric and the direction

Primary = **mean per-fold CRPS lift of `hurdle_transfer` over `incumbent`**, positive = better.
Reported beside it: per-fold lifts, folds won, the one-sided paired p-value, the NF1.8 triad (flip
distribution, Bailey degradation, contender spread) beside PBO, and the whole-field DSR beside the
binding figure.

---

## 5. Gates — ALL must pass to SHIP

| # | gate | bar |
|---|---|---|
| 1 | `beats_incumbent` | primary's mean per-fold CRPS lift > 0 |
| 2 | `fold_consistency` | `cv_power.fold_consistency_clause(7)` ⇒ **≥ 6 of 7** folds won by the primary |
| 3 | `pbo_ok` | PBO < 0.20 over the ELIGIBLE (declared, 6-arm) field, on **negated** CRPS |
| 4 | `dsr_ok` | DSR ≥ 0.95 under the §3 `V` convention at `N = 6` |
| 5 | `bh_ok` | the primary survives BH-FDR at the §6 family's q |
| 6 | `degenerates_lose` | BOTH `all_zero` and `no_cap` lose to the primary. A criterion a degenerate WINS is fatal (NF1.8) |
| 7 | `oracle_respected` | no arm in the declared field beats its own-form peeking oracle, and the matched-n control is evaluable |
| 8 | `beats_permutation` | the primary beats `permuted_timing` |
| 9 | `hurdle_attributable` | the matched-foil paired delta `timing_aware − hurdle_transfer` > 0 |

**Reporting rule for gate 9, declared forward.** Gate 9 is what makes the win attributable to the
**availability SPLIT** rather than to the covariates `hurdle_transfer` and `timing_aware` SHARE
(they are identical in every other respect — NF-D10 / NF-D15). A primary win that gate 9 does not
separate is reported as *a win for the shared in-fold fitted LEVEL*, never as a win for the
hurdle. It is a hard SHIP gate regardless; this rule governs what may be CLAIMED, not what may
ship.

**Level-adjacency (the gated ship path).** A shipping arm changes `proj_games`, hence the served
point (`point = rate × games`), so a pass does **not** deploy. It additionally requires, all still
deploy-held: (a) the whole-board cross-position **placement read**
(`run_nf_tr2b_placement_read`) against the PUBLISHED artifact; (b) **`run_interval_revalidation`**
(NF-D16 / NF-D21 machinery); (c) NF-TR2b's caveat carried — the VOR "shield" is **ADDITIVE-only**
and does **not** hold under the two superflex configs; (d) the served-**POINT** impact
**MEASURED, never assumed proportional** — NF1.5's ordering step hands part of the availability
discount back (NF-INJ1 / NF-INJ2 territory), so the point-level consequence of a games change is
unknown until it is measured. Ship/no-ship is then the operator's decision.

---

## 6. Binding registration item (2) — the BH FAMILY, named up front

**The family is a SINGLE hypothesis, at `q = 0.10`, and the tested statistic is the primary's
one-sided paired p-value.**

The justification, stated before any p-value is computed:

* **one MECHANISM** — the injury-games level for a flagged veteran. There is no second mechanism
  in this registration;
* **one POPULATION** — flagged, non-returner veterans on the MVP-1 board, 2019–2025 eval folds.
  There is no second population;
* **no POSITION axis and no per-status axis is registered.** Per-status results are DISCLOSED
  (and `NFI`/`SUS` are declared inactive in §1/§2), but no per-status hypothesis is tested, so
  none enters the family;
* **the primary is REGISTERED, not selected** (§2). There is exactly one hypothesis test in this
  study: *does `hurdle_transfer` beat `incumbent`?*

⭐ **Why the field's other arms do NOT enter the family.** The field exists so that the SEARCH is
deflated — and the instrument that deflates a search is DSR (§3), which taxes `N = 6` in full.
Applying BH across the arms as well would deflate the same search a **second** time with a second
instrument. That is not conservatism, it is double-counting, and it is the MH2.7
`n_arms = 1 ⇒ PBO INAPPLICABLE` shape one instrument over.

**DISCLOSED BESIDE IT, and NOT binding:** the strict across-arms reading (the eligible arms as
parallel hypotheses, rank-1 cutoff `q / n_eligible`) is reported as a SENSITIVITY, exactly as
NF-INJ3 reported both. It is a disclosure, not the gate. ⛔ The registered family is the
single-hypothesis one and it binds **whichever way the result falls** — including if the strict
reading would have been kinder.

---

## 7. Power, and the outcomes this design admits

At 7 folds the design's MDE is **1.20 SD units** of the per-fold lift (80% power, one metric);
`dsr_ceiling(7) = 0.9997`, so the DSR ceiling does not bind. ~283 rows sit in eval folds. Two
channels are thin by construction and this study is **pre-labelled EXPLORATORY on every per-status
channel other than `RES`** — a `RES` result is the one the design can carry.

Any null is classified with **`cv_power.classify_null(declared_field_size=6, …)`** and the machine
flag **`field_remedy_admissible` is read, never the prose** (MH2.7).

### ⛔ PROHIBITIONS, binding on this study's write-up

* **No re-read of NF-INJ3's gate off the 0.973 diagnostic** (E2.1-r). NF-INJ3's null STANDS as
  recorded; this is a fresh registration, not a re-scoring of that one.
* **No post-hoc field trim** (MH2.2). §2's membership and §3's `V` are fixed by this document.
* **No "more seasons" re-test trigger.** 28 folds is 28 NFL seasons, the era floor is a
  data-fidelity fact, and the feed yields one season a year. NF-INJ3 measured the binding quantity
  to be `V`'s COMPOSITION, not power — publishing a fold-count trigger here would be the NF-D18
  actively-misleading direction. If this study nulls, its trigger is whatever is **genuinely
  reachable**, and if nothing is, it says so and closes.
* **No new arm invented mid-run**, and no gate re-cut after a score.

### Valid outcomes

**CLEARS** (all nine gates pass ⇒ the gated ship path in §5, still deploy-held) — or a
**classified null**, its state named per `cv_power`. A null closes cleanly.

---

## 8. Reproduction pin — at 1e-9, declared before the run

Two pins, both hard failures:

1. **Scoring identity.** Every per-fold, per-arm CRPS produced under this registration must equal
   NF-INJ3's recorded value to **< 1e-9** (never `round(..., 6)`). This is what makes "only the
   REGISTRATION changed" a measured claim rather than an assertion: the data, the folds, the
   shared φ and the arm fits are byte-identical, and the delta between the two studies is exactly
   the specification in §2/§3/§6.
2. **Served-board identity.** The incumbent must reproduce the CURRENT served board — every
   flagged row on the live 2026 MVP-1 board inverts through `g = 0.3·eg + 0.7·min(eg, cap)` with a
   round-trip error at machine precision and 0 rows above the incumbent's ceiling.

New guards ship with a RED proof asserting each deliberate break **lands on disk**, **removes the
asserted token**, and **anchors uniquely** (#682 / #815 / E11.24), and a guard that cannot go red
is not a guard (NF1.7 (a)).
