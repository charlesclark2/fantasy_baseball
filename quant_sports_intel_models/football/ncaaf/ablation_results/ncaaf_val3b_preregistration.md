# NCAAF-VAL3b — pre-registration (written BEFORE any arm was scored)

**Story.** The NCAAF cold-start μ_total correction as **ONE forward-registered contrast**:
`bucket_shift` **vs** the served incumbent. Model / §0.5 / market-blind / `best_alpha = 0`.
Query + eval only: **no serving write, no registry edit, no refit of a served artifact, no bet.**

Spec: `plan_specs/ncaaf/ncaaf-val3b.yaml` (PM-authored, FULL tier). Parent record:
`ncaaf_val3_cold_start_mu.md` (`INCUMBENT_STANDS`, recorded state `DEFLATION_REFUSED_PBO`).

⛔ **Everything in §1–§8 below is fixed before a single arm is scored, and none of it may be
revisited after seeing a score (E2.1-r).** §0 is disclosure, not result.

---

## 0. Disclosure — what this session already knew when it wrote this document

This is a **successor** to a study whose scores are on disk and were read in full before this
document was written. Pretending otherwise would be worse than saying it, so:

- VAL3's `bucket_shift` scored **CRPS wk1-3 9.3793 vs the foil's 9.4642 (+0.0848), 8/8 folds,
  DSR 0.998, p 0.0047, all clauses ✅**, and was refused by **PBO 0.5300** over a declared field of 8.
- VAL3 also MEASURED that the refusal is a **field-composition artifact**: the 2-arm decision PBO is
  **0.0000** and the eligible-set (5-arm) PBO is **0.7010 — WORSE**, so trimming to the eligible set
  is not the remedy and the four near-identical correction forms are.

⇒ **Every choice below is therefore constrained to have ZERO free parameters that a knowing author
could turn.** Concretely: the field is the spec's ("ONE arm, one foil"); the metric, folds,
population, estimator, clauses C1–C8 and the fold-consistency clause are **imported verbatim from
VAL3, not re-derived**; `V` is `deflated_sharpe`'s own documented no-field default; and the two
materiality bars (§5) are a closed-form arithmetic function of constants **VAL2** recorded, with no
knob. Where a choice could plausibly have gone two ways, both readings are computed and the binding
one is declared **here** (§4, §6).

⛔ **What this does NOT license.** VAL3's field is not re-cut and its scores are not re-read
(MH2.2). VAL3b re-runs the contrast from scratch on a freshly assembled cache and stands on its own
numbers. VAL3's verdict is unchanged and is not rewritten (NF-W7f).

---

## 1. Why a single contrast is the admissible successor, and what it costs

**The licence.** MH2.2 / NF-W6b-C / NCAAF-P2.1-S1: the admissible remedy for a deflation refusal
over a heterogeneous field is **a fresh registration of a COHERENT family declared FORWARD on
mechanistic grounds** — never a post-hoc trim of a field already scored. VAL3's PM ruling carded
exactly this shape. NCAAF-VAL3 also measured the diagnostic that separates "the field did it" from
"the effect is noisy" (CLAUDE.md's NF-W7f caution): here the **two-arm** PBO is 0.000 while the
**eligible-set** PBO is *worse* than the full field, which is the signature of near-clones, not of
an unstable winner.

**The mechanism argument, stated forward.** VAL2 measured the cold-start error decaying
**+4.77 / +2.88 / +0.28** across weeks 1/2/3 against a `wk4-6` cell that is *negative*. Over the
three-week cell that shape is well described by **one constant**; a per-week or ramp
parameterisation spends 2–3 parameters to express the same 3-week mean. The correction the product
needs is a single number applied to a single declared cell. `bucket_shift` **is** that estimator.

**What it costs, stated so it is visibly a choice.**

- VAL3b **does not re-attribute the channel**. VAL3's matched foils (`week_blind`, `pooled_level`)
  are OUT of this field. They are honest, in-principle-shippable estimators, and calling one a
  "diagnostic" to keep it out of the multiplicity count would be precisely the laundering MH2.2
  forbids. The attribution is therefore **CITED from VAL3's record, not re-measured here**:
  magnitude channel (`bucket_shift − week_blind`, wk1-3) **+0.0704, 7/8 folds, p = 0.0051**; scoping
  channel (`week_blind − pooled_level`, pooled) **+0.0000, 3/8, p = 0.4928**. A reader who does not
  accept a citation should read VAL3's §4b, not this document.
- VAL3b **cannot discover a better form**. That is the point, not an oversight: there is nothing to
  search, which is exactly what makes PBO inapplicable.
- ⛔ **NO δ-scaling.** `over_scale` (δ = 2·d̂) topped VAL3's raw leaderboard, but its **paired** read
  against `bucket_shift` is a **TIE** (+0.0070 CRPS, 5/8 folds, p = 0.779) and it was **BEATEN** by
  its own-form peek (C8 ❌). A rank cannot tell a tie from a win (NF1.8), and a magnitude adopted
  after seeing it rank is the inadmissible-λ shape (NF-D18 / NF-D20). No scaled variant is
  registered, scored, or reported as a candidate here.

---

## 2. Population, folds and the frozen model — imported, not restated

Identical to VAL3 §2, by import rather than by a second literal (a restated constant can drift away
from the one the parent scored — the E9.61 two-renderers hazard):

- Cache: the P1.4 assembly re-run at session start (§7).
- Config: the **SERVED** one — `ridge` / `strength_pace` / `strength_posterior`, read from
  `ncaaf_val1_clv_week_strat.PRIMARY`.
- Folds: `bakeoff_ncaaf_game.build_folds` verbatim — **8 purged season-forward folds, eval 2018–2025**.
- Scored population: the **full OOS frame** (VAL3: 6,024 games) — *not* the close-carrying subset.
  The target `μ − y` needs no market number, so the study is market-blind **by construction**.
- Cell: `season_order_week ≤ 3` (⛔ never raw `week` — the P1.1 postseason restart).
- **FROZEN-σ / FROZEN-margin invariant.** The arm moves **μ_total only**; per-game σ and μ_margin are
  byte-identical to the foil's. A REFUSAL condition (C6/C7), not a diagnostic.
- **The in-fold estimator.** For outer eval season `Y`, a nested purged walk-forward over rows with
  `season < Y` (`min_train_seasons = 2`, a design quantity fixed by the fold structure) yields honest
  in-train OOS predictions; δ is the mean of **those** rows' `mu_total − y_total` over the cold cell.
  ⛔ No constant is inherited from VAL2 or VAL3.

---

## 3. The field — ⛔ CLOSED, and it has two members

| arm | role | δ on a `wk1-3` row | eligible to ship |
|---|---|---|---|
| `none` | **foil** — the served model, untouched; the do-nothing degenerate and the incumbent, one and the same | 0 | — |
| `bucket_shift` | **the single candidate** | `d̂_bucket(f)` = the in-fold mean of `mu_total − y_total` over the fold's nested-inner-OOS cold-start rows | ✅ |

**Diagnostic anchors — NOT trials; excluded from `n_trials` AND from `V` (MH2.1 (a)).** These are
*peeking* constructions: they read the eval fold's own residuals, so they were never candidates for
selection and counting them as trials would be a category error, not a concession.

| anchor | what it is |
|---|---|
| `oracle_bucket` | δ = the mean `mu_total − y_total` of the **eval fold's own** cold-start rows. Same FORM as `bucket_shift` (NF-D16 g‴: one ceiling per form). |
| `matched_n_bucket` | the same estimator on a random **in-fold** slice sized to the eval fold's own cold-start n — what makes the peek readable at matched family **AND** matched sample (NF1.7 (b) / NF1.9 (f)). |

**`DECLARED_FIELD_SIZE = 2`** = the foil + the one candidate. Declared here, forward. Selectable
arms: **1**.

---

## 4. The gates — each declared with the value it takes at this design, computed BEFORE scoring

### 4.1 PBO / CSCV — **INAPPLICABLE, and no number is computed**

A single pre-registered contrast has **no search to overfit**: CSCV asks "does the in-sample winner
of a search hold up out of sample?" and there is no winner to pick. `cv_power.classify_null`'s own
`n_arms < 2` branch (the MH2.7 co-fix) says this in exactly those words and emits **no re-test
trigger**.

⛔ **`pbo` is recorded as `INAPPLICABLE` / `null`. It is NOT recorded as passed, and a two-arm CSCV
number is deliberately NOT computed even as a diagnostic.** VAL3 already reported that figure
(0.0000) as a labelled lower bound; reproducing it inside the successor's own gate block would read
as "the gate we failed now passes", which is the misreading this whole shape exists to avoid. The
deflation requirement here is satisfied by the **DESIGN**, and the remaining gates carry the weight.

### 4.2 DSR — gate ≥ 0.95, `n_trials = 2`, `V` = the asymptotic no-field default

- `n_trials = DECLARED_FIELD_SIZE = 2` (VAL3's convention: the foil counts).
- **`V` (cross-trial Sharpe dispersion) is UNDEFINED at one selectable arm** — a variance needs ≥2
  points. `deflated_sharpe`'s documented fallback is then the **asymptotic null variance of a Sharpe
  estimate, `V = 1/n_obs = 1/8 = 0.125`**. That is a *design* quantity (it depends only on the fold
  count), and it is what this study declares. ⛔ **Importing VAL3's measured `V` (0.05878) is
  INADMISSIBLE in either direction** — it is a dispersion measured over a field this registration
  does not have.
- ⇒ **`SR0 = √V · z(N=2) = 0.35355 × 0.51925 = 0.18376`. Declared here, before scoring.**
- **The bar is LOWER than VAL3's (`SR0` 0.18376 vs 0.35374), and this document says so plainly.**
  That is the entire arithmetic content of the successor shape: a 2-arm design carries almost no
  expected-max inflation. It is legitimate **only** because the family is DECLARED FORWARD on the §1
  mechanism argument and the whole field is scored — not trimmed after the fact.
- The **lockstep invariant** (NF-W8-0d — a shared-variance lever cannot clear DSR because the winner
  is one of the trials setting `V`) **does not apply here**: `V` is not a field variance at all.
- `cv_power.dsr_ceiling(8) = 0.99991`, so the 0.95 gate is **reachable** at this fold count (MH2: at
  3 observations the ceiling is 0.977 and the gate is structurally unreachable). Recorded so a
  failure cannot be a design artifact nobody checked.
- Empirical skew/kurtosis of the per-fold series are threaded through (never the Gaussian default).

### 4.3 BH-FDR — α = 0.05

One hypothesis ⇒ the Benjamini–Hochberg cutoff **is** α = **0.05**. Stated because a reader should
see that the multiplicity correction has become trivial *as a consequence of the declared design*,
not because it was switched off.

### 4.4 Fold consistency — `cv_power.fold_consistency_clause(n_folds = 8)`

**6 of 8 wins required**, attainable `True`, calibrated false-fire **0.1445** (the legacy 60 % clause
would ask 5 at 0.3633).

### 4.5 Ship clauses C1–C8 — imported verbatim from VAL3 §5

| id | clause |
|---|---|
| **C1** | pooled total PIT max-decile-dev ≤ foil's **+ 0.0020** |
| **C2** | pooled total `calib_80` ≥ **0.78** (the P1.4 floor) — a FLOOR, never a target (NF1.8) |
| **C3** | `wk1-3` total `calib_80` ≥ **0.78** |
| **C4** | **market-blind estimator** — sized off `mu_total − y_total` only; asserted at the estimator frame |
| **C5** | `wk4+` CRPS unchanged to 1e-9 (week-scoping, asserted not assumed) |
| **C6** | margin CRPS byte-identical to the foil's |
| **C7** | per-game σ byte-identical to the foil's |
| **C8** | own-form peeking-oracle floor: the arm does not BEAT `oracle_bucket`. A peek that does not beat its own matched-n control is **INACTIVE** — uninformative, never a pass and never a fail (NF-W6d / NF-D20) |

---

## 5. Materiality and detectability — **the gap VAL3 recorded and handed forward**

VAL3 recorded: *"This study pre-registered a materiality band in POINTS but NOT a practically-
meaningful CRPS effect in SD units, so `classify_null` correctly falls through to its honest default.
⛔ Supplying one now would be re-deriving a bar from the answer; it is a pre-registration gap, and a
successor registers it forward."* This is that successor. Both bars below have **zero free
parameters** — each is a closed-form function of a constant **VAL2** recorded before VAL3 existed.

**M1 — materiality in the native unit (inherited, not re-derived).** The correction must reduce the
`wk1-3` **|bias| by ≥ 1.00 pt**. This is VAL2's own acceptance band, held there as a module constant
and guarded against being re-derived from any measured value.

**M2 — the practically-meaningful CRPS effect, derived analytically.** VAL2 recorded the cold-start
bias as **+2.3 pts ≈ 0.15 σ**, i.e. its 1.0-pt band is **0.065 σ**. For a calibrated Gaussian
predictive the expected CRPS is `σ·E[g(Z)]`, `Z ~ N(−β, 1)`, `g(z) = z(2Φ(z)−1) + 2φ(z) − 1/√π`, so
the **relative** gain from removing a bias is **σ-free**:

```
C(0.150) = 0.57053077      # the foil, at VAL2's recorded cold-start bias
C(0.085) = 0.56622711      # after removing VAL2's 1.0-pt band (0.065 σ)
M2  =  (C(0.150) − C(0.085)) / C(0.150)  =  0.7543 %   of the foil's wk1-3 CRPS
```
(for reference, removing the bias *entirely* is worth 1.1115 % — so M2 asks for ~68 % of the whole
available headroom.)

**M1 and M2 BIND**: a ship requires both, on top of C1–C8 and the gates. They are *stricter* than
VAL3's clause set — a new refusal condition, registered forward, not a loosened one. The anchoring
at VAL2's 0.15 σ is the **conservative** direction: if the true starting bias is smaller, the
achievable gain is smaller and M2 is harder, not easier.

**Detectability (a pure design quantity, no data).** `cv_power.mde_in_sd_units(n_folds = 8) = 0.95`
fold-delta SDs at 80 % power. Used to read a NULL: an observed lift **below** the MDE ⇒ the design
could not have seen it (POWER-LIMITED); **above** it ⇒ the design could, and the binding gate is the
finding.

---

## 6. Verdict rules — declared forward

**SHIP_CORRECTION** iff **all** of: C1–C8 ✅ · M1 ✅ · M2 ✅ · gain > 0 and not a numerical tie
(`|gain| > 1e-6`) · DSR ≥ 0.95 · BH pass at cutoff 0.05 · fold consistency ≥ 6/8 · PBO recorded
INAPPLICABLE (never "passed"). Otherwise **INCUMBENT_STANDS**.

**A null is a valid outcome and closes cleanly.** It is classified with
`cv_power.classify_null(n_arms = 1, declared_field_size = 2, degenerates_excluded_from_v = None)` —
whose n_arms<2 branch returns `UNDEFINED` with the PBO-INAPPLICABLE reason and **no trigger** — and
the instrument's state is **preserved beside**, never replaced by, the recorded state. The recorded
state names the **binding half**: a ship-CLAUSE refusal ⇒ `CONSTRAINT_REFUSED` with ⛔ **no
fold/season re-test trigger** (no fold count moves a clause — NF-D18); a materiality refusal (M1/M2)
⇒ `IMMATERIAL` (the effect is real but below the band — likewise no season trigger); a deflation
refusal ⇒ `DEFLATION_REFUSED_<gate>`; otherwise the instrument's own state stands.

⛔ **`SHIP_CORRECTION` does not serve anything.** See §8.

---

## 7. Reproduction pin (§6a) — anchored on the PARENT, with the date leg named for what it is

Sourced from `ncaaf_val3_s1_serve_reanchor.json` (the S1-serve eval-only re-run: `n_oos_games` 6024,
`clv_eval.n_with_close` 4187, `fit_at` 2026-08-22) and the fold structure. ⛔ **Never from VAL3b's
own output.**

| leg | expected | binds |
|---|---|---|
| `n_with_close` | **4187** | ✅ HALT |
| `n_oos_games` | **6024** | ✅ HALT |
| `fold_years` | **2018–2025** | ✅ HALT |
| `cache_assembled_at` | — | ❌ **REPORTED, not pinned** |

⭐ **Why the date leg is reported rather than pinned, declared here so it cannot look like a
loosening after a failure.** `assemble_cache` stamps `assembled_at = date.today()`. VAL3 ran and
assembled on the same day, so pinning the literal `"2026-08-22"` cost it nothing. VAL3b must
re-assemble (the main checkout holds the 07-22 vintage, 4,182 closes) and will therefore stamp
**today's** date **whatever the population is** — so that leg would fail for a reason that carries no
information about the population, while the three legs that *do* define the population would be
buried under it. The date is recorded as provenance. **The population legs HALT.**

---

## 8. Ship gating — two steps, and nothing serves from this session

Per the spec's acceptance criterion (a), even a cleared contrast is **DEPLOY-HELD by default**:

- **(a)** A pre-opener ship is permitted **only if** the S1-serve-class **train/serve parity** holds
  against the **SERVED artifact contract**, checked directly rather than assumed, **AND** the
  operator explicitly approves.
- **(b)** Otherwise **DEPLOY-HELD with the gap NAMED**, shipping post-opener via the P1.4 serve path.

The parity question is registered forward as three legs, each answered against the artifacts on
disk, not from memory: **(i)** can the served mean contract *express* a week-conditional shift?
**(ii)** is the quantity that would serve the *same* quantity this study validated? **(iii)** does
the serving path carry the *right* week column (`season_order_week`, not CFBD's postseason-restarted
`week`)? Any leg failing ⇒ **(b)**.

**Either way this session writes no served artifact, edits no registry, and places no bet.**
`best_alpha = 0` before and after. Any vs-close figure reported is **DESCRIPTIVE**, produced by the
`_clv_leg`-immune `over_tilt_report` implementation (a `game_id` join that takes no positional index
into any array — ⛔ never the row-misaligned `_clv_eval`, a recorded INC), and the implementation is
NAMED wherever such a figure appears.

## 9. Scope guard

⛔ The **+0.557 pt residual** VAL3 measured after the correction (the estimator cannot track a rising
level) belongs to a **separate future lead** (a drift-aware estimator). It is **not** bundled here,
and no arm in §3 attempts it.
