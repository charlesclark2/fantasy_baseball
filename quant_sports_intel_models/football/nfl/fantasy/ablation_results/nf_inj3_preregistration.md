# NF-INJ3 — pre-registration: a designation-timing-aware injury-games model

**Committed BEFORE any arm was scored.** ⛔ Not edited after a result (E2.1-r). Anything the
decisive run overturns is left in place verbatim under a `SUPERSEDED` marker (NF-W7f).

Story: NF-INJ1 §5d / §8.3 — the PM funded this as its own §0.5 story, explicitly **NOT** bundled
with NF-INJ2 (mixing a level change with an availability change makes neither attributable —
NF-W7e's measured non-additivity). NF-INJ2 landed **no model change** (`CONSTRAINT_REFUSED`), so
the incumbent this runs against is the shipped board.

`best_alpha = 0`. Deploy-held: nothing here serves until the PM records a disposition.

---

## 1. The defect

`season_projection._INJURY_STATUS_GAMES_CAP = {"RES": 4.0, "PUP": 4.0, "NFI": 4.0, "SUS": 7.0}`
at `_INJURY_OVERRIDE_BLEND = 0.7`, applied in `injury_availability_games` (`season_projection.py:375`,
called at `:990`). Four hardcoded constants, described in-code as "empirical" but never fitted
in-fold and never re-validated since NF-D2. They set the expected games of every flagged player on
the board, and `proj_games` is both what makes an injured player project down (MVP-1's point is
`rate × games`) and a directly served field.

Two things are wrong with them a-priori, and both are measured in §7 below:

1. **They do not match their own stated empirics.** The docstring reports RES → 3.7, PUP → 2.4,
   SUS → 6.9 games and then hardcodes 4.0 / 4.0 / 7.0.
2. **They are timing-blind.** A March PUP and a late-August PUP both collapse to 4.0 games.

---

## 2. ⚠️ SCOPE FINDING, MEASURED BEFORE REGISTRATION — the literal timing covariate DOES NOT EXIST

The story's hypothesis is "games as a function of status and **when the designation landed relative
to kickoff**". That covariate is **not obtainable from any source this program has**, forward or
historical, and that was established before the field was declared rather than discovered inside it:

| candidate source | why it cannot carry a designation date |
|---|---|
| `stg_nfl_weekly_rosters` (the historical status feed) | week 1..17/18 only — **no preseason weeks**. A week-1 `RES` row is a *state*, not an *event*; nothing records when it was entered. |
| `stg_nfl_sleeper_injuries` (the forward feed) | `run_sleeper_injuries_ingest.py` **overwrites the season's Delta partition on every capture**, so the table holds exactly **ONE snapshot** (measured: `count(distinct ingested_at) = 1`, 2026-08-20). No first-seen date exists to derive. |
| `stg_nfl_injuries` (nflverse weekly report) | starts at REG week 1 — **no `PRE` rows** — and holds **no 2026 rows at all** (latest season 2025). Cannot serve a preseason board in either direction. |
| NFL transactions | **no such feed exists** in this stack. |

⇒ The registered hypothesis is therefore tested through the **best available operationalisation of
designation ONSET**, declared here in full, and the study's conclusion is scoped to that proxy — it
is NOT evidence about a designation date, and must never be reported as such.

**The registered timing proxy** (both leakage-safe: known from season Y−1 and the Y week-1 snapshot):

* `onset_carryover` — the player's status in the FINAL week of season Y−1 is itself an
  unavailable/inactive designation (`RES`/`PUP`/`NFI`/`SUS`/`INA`). Distinguishes a long-standing
  absence carried into the new season from a fresh offseason/camp injury.
* `weeks_since_last_game` — (final week of Y−1) − (last week the player actually played in Y−1).
  Larger = the absence has been running longer.

These two columns and **only** these two are what the matched foil strips (§4).

---

## 3. Population, era, and the two structural INACTIVITIES

**Rows.** One row per (target season Y, player) where the player is (a) on that season's MVP-1
veteran board, (b) carries a Y **week-1** roster status in {RES, PUP, NFI, SUS}, and (c) is not a
returner (see below). **Outcome** = realized games in Y (`fct_player_week`, `played_flag and not
is_bye`) — taken from the warehouse, never from a projection panel, and the model's own
`proj_games` is taken from the **single-vintage** 2016–2025 build (all ten artifacts written in ONE
run, 2026-08-08 19:10). That split is the NF-D10 mixed-vintage rule applied literally.

**Era = 2016–2025, and the restriction is derived from a DESIGN quantity, not from an outcome.**
Pre-2016 the weekly roster feed is not a weekly snapshot at all — it is a season-END status
backfilled onto every week, so the "week-1" label is **outcome-contaminated**:

| fidelity statistic (all seasons) | pre-2016 | 2016+ |
|---|---|---|
| share of player-seasons whose status ever changes | 0.019 – 0.099 | 0.130 – 0.690 |
| share of week-1 `RES` players ever seen `ACT` later | **0.000 every season** | 0.148 – 0.378 |
| week-1 `RES` median realized games / zero-rate | 6 / 0.03–0.13 | **0 / 0.62–0.92** |

A player recorded as on IR in week 1 who then plays a median of six games is a season-end label.
⭐ Recorded because it bears on the incumbent: `_INJURY_STATUS_GAMES_CAP`'s docstring fits its
constants on **2015–2024**, i.e. one contaminated season inside the window.

**Returners are EXCLUDED (`seasons_missed ≥ 1`).** NF-D11's absence prior runs immediately AFTER
the injury cap and caps games again, so a returner's served `proj_games` is the composition of two
caps and the injury cap's contribution is **not separably recoverable**; an `eg` recovered from it
would misattribute the absence prior's discount to this mechanism. Excluded count and the serving
cohort's own returner share are both reported — this is a stated scope limit, not a silent filter.

**Two structural INACTIVITIES, declared forward (NF-D20 — count the rows the mechanism can act on
BEFORE crediting a pass):**

* **`NFI` has ZERO rows** in the entire historical feed and **zero** in the 2026 serving cohort. Its
  cap is **unfittable and inactive**; every arm inherits the incumbent's constant for it and no arm
  may claim credit there.
* **The cap never reaches a ROOKIE.** `injury_availability_games` runs inside `project_veterans`;
  `project_rookies` is a separate frame concatenated afterwards. Measured: of 60 historical flagged
  rookie rows, **50 project ABOVE the incumbent's own ceiling** (Derrius Guice, `RES` for all of
  2018, projected 12.5 games) while **0 of 496 flagged veterans do**. This is a real defect and it
  is **OUT OF SCOPE** here — NF-INJ3 makes the cap accurate on the population it acts on; extending
  it to a new population is a different change. Recorded for carding.

---

## 4. The declared field

**Primary metric = exact discrete CRPS** over games ∈ {0..n_Y} (n_Y = 16 for Y ≤ 2020, 17 for
Y ≥ 2021), i.e. `Σ_k (F(k) − 1{y ≤ k})²`. Not a quantile grid — a coarse grid silently ties arms on
a zero-heavy discrete target (NF-W4).

⛔ **MAE is reported and NEVER selects, and this is measured rather than assumed.** On this cohort
the all-zero nihilist scores **MAE 2.7628** against the pooled mean's **3.5283** — the conditional
median sits at the floor, so MAE is *demonstrably inverted* here (NF-D11; NF-D14's refinement that
the median, not the zero share, is the test).

**Shared predictive family (a matched nuisance).** Every arm emits a mean μ; the mean is mapped to a
distribution by `Beta-Binomial(n_Y, μ, φ)` with **one φ fitted in-fold under the INCUMBENT's mean**
and held byte-identical for every arm. So the arms differ ONLY in μ — the served quantity — and the
dispersion is calibrated to the arm being challenged, which is generous to the incumbent by
construction. Family adequacy measured before registration: fitted φ ≈ 1.0 reproduces P(0) = 0.559
against an empirical 0.606 and costs 0.013 CRPS against a fully nonparametric pooled pmf.

**Folds:** expanding window, eval season Y ∈ **2019…2025** (7 folds), fit on 2016…Y−1. Burn-in
2016–2018.

### Arms (declared field size = 7)

| arm | what it is |
|---|---|
| `incumbent` | the shipped `{RES:4, PUP:4, NFI:4, SUS:7}` at blend 0.7 — the thing to beat |
| `fitted_status` | the SAME functional form, with the per-status level and the blend fitted in-fold |
| **`timing_aware`** | **PRIMARY** — `fitted_status` plus the §2 onset covariates and the non-timing covariates, one Beta-Binomial GLM |
| `hurdle_transfer` | the W2/W2b/W2d transfer: an explicit availability hurdle, `P(plays ≥ 1) × E[games | plays]` — the certified weekly finding is that the lift lives in the **zero/availability leg** |
| `sus_regime` | `SUS` fitted as its own regime (a known-length administrative absence, not an injury), injuries on the `fitted_status` form |
| `all_zero` | **DEGENERATE** — μ = 0 for every flagged player (NF-D11's nihilist ceiling; MUST lose) |
| `no_cap` | **DEGENERATE** — the uncapped stale durability estimate, i.e. the mechanism removed (MUST lose) |

`DECLARED_FIELD_SIZE = 7`. Under **DSR-CONV** the two degenerates stay in `n_trials` (they pay full
multiplicity) and are excluded from the cross-trial dispersion `V`. They are named degenerate
**here, before any score** — declaring one after it loses is laundering.

### Matched foil (NF-D10 / NF-D15) — non-shippable

`timing_aware_minus_timing`: byte-identical machinery to `timing_aware` with `onset_carryover` and
`weeks_since_last_game` **removed and nothing else changed**. The paired per-fold delta
`timing_aware − timing_aware_minus_timing` **IS** the timing attribution. A win for `timing_aware`
that this foil does not separate is a win for the *covariates it shares with the foil*, not for
timing, and must be reported as such.

### Anchors

* **Per-FORM peeking oracle** (NF-D16 g‴): each arm is floored by the peeking version of its OWN
  form (that form refit on the eval fold's realized outcomes). The forms NEST
  (`fitted_status` ⊂ `timing_aware`), so a single field-wide ceiling would falsely veto a
  legitimately better nested form.
* **Matched-n control** (NF1.7 (b) / NF1.9 (f)): the winner's own form trained on ONE prior season,
  so the oracle floor is enforced at equal family AND equal resolution.
* **`permuted_timing`**: the two timing covariates shuffled within (status × season) — player
  linkage destroyed, marginals preserved. `timing_aware` must beat it.
* **`pooled_mean`**: one in-fold pooled mean for every flagged player, status ignored.
* ⭐ A missing or unfittable anchor **RAISES**. It is never treated as a pass (NF1.7 (a)).

---

## 5. Gates — all must pass to SHIP

1. `beats_incumbent` — mean per-fold CRPS lift over `incumbent` > 0.
2. `fold_consistency` — `cv_power.fold_consistency_clause(7)` ⇒ **≥ 6 of 7** folds won
   (attained false-fire 0.0625).
3. `pbo` < 0.20, computed over the ELIGIBLE (declared) field on **negated** CRPS, reported beside
   the NF1.8 triad (flip distribution, Bailey degradation, contender spread).
4. `dsr` ≥ 0.95 under DSR-CONV, with the whole-field figure reported beside it.
5. `bh_fdr` — survives BH-FDR at the family's q.
6. `degenerates_lose` — BOTH `all_zero` and `no_cap` lose. A criterion a degenerate WINS is fatal
   (NF1.8).
7. `oracle_respected` — no arm beats its own-form peeking oracle, with the matched-n control.
8. `beats_permutation` — `timing_aware` beats `permuted_timing`.
9. `timing_attributable` — the matched-foil paired delta > 0. **A win that fails only this is
   reported as a win for the non-timing covariates, not for timing.**

**Level-adjacent.** A shipping arm changes `proj_games`, hence the served point (`rate × games`), so
it additionally triggers the whole-board **placement read** (`run_nf_tr2b_placement_read`) and
**`run_interval_revalidation`** per NF-D16 / NF-D21 before any deploy. ⚠️ NF-TR2b's caveat applies:
the VOR "shield" is additive-only and does **not** hold under the two superflex configs.

---

## 6. Power — declared FORWARD, and this study is pre-labelled

At 7 folds the design's MDE is **1.20 SD units** of the per-fold lift (80% power, one metric);
`dsr_ceiling(7) = 0.9997`, so the DSR ceiling does not bind. The scored population is ~418 rows
with ~283 in eval folds, and two channels are thin by construction: `PUP` has **28** historical rows
(none after 2020, while it is 8 of 26 in the serving cohort) and `SUS` has **35**.

⇒ **This study is pre-labelled EXPLORATORY on the per-status channels other than `RES`.** A `RES`
result is the one the design can carry. Any null is classified with
`cv_power.classify_null(declared_field_size=7, …)` and the machine flag `field_remedy_admissible` is
read, **never the prose** (MH2.7). `CONSTRAINT_REFUSED` / `POWER_LIMITED` are valid outcomes.

---

## 7. Reproduction pin (verified before the run)

The incumbent reproduces the CURRENT served board. Every one of the **26** flagged rows on the live
2026 MVP-1 board inverts cleanly through `g = 0.3·eg + 0.7·min(eg, cap)`, and **0** exceed the
incumbent's ceiling of `0.3·17 + 0.7·4 = 7.9` — Kittle 7.315, Pierce 7.349, Higgins 6.659,
Pearsall 5.650, matching NF-INJ1 §7.1 exactly. Across the historical single-vintage builds,
**0 of 496** flagged veterans exceed their ceiling.

Serving cohort composition (2026, measured): **26 flagged veterans — 18 `RES`, 8 `PUP`, 0 `NFI`,
0 `SUS`**. So the `SUS` and `NFI` caps are **inactive on today's board**, and any per-status result
must be read against that.
