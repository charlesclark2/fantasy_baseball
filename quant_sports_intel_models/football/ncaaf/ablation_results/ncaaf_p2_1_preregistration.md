# NCAAF-P2.1 — PRE-REGISTRATION of the game-model structural hypothesis battery

**Status: PRE-REGISTERED. Written and committed BEFORE any hypothesis was scored.**
_This document is the E1.11 / E13.16 anti-mirage artifact: the full hypothesis set, the metric, the
gates, the anchors and the deflation convention are all fixed HERE, in advance. Anything added after
the first eval run is laundering and is forbidden (E2.1-r). If the battery is later amended, the
amendment is a dated entry at the bottom, never an edit to the body._

---

## 0. What P1.4 actually is — the structural verification (done FIRST, per the story's instruction)

The story spec describes the model as `margin = hfa + (θ_home − θ_away)`, `θ = μ_conf + Zβ + u`, with
an offense/defense split. **That formula is NCAAF-P1.2 (`team_strength.py`) — it is NOT the P1.4 game
model.** P1.4 (`bakeoff_ncaaf_game.py`) fits a LEARNER on a feature matrix to predict
(μ_margin, μ_total), and the P1.2 strength ratings enter only as FEATURES. So every hypothesis was
re-verified against the shipped P1.4 configuration rather than against the spec's formula. Three of
the spec's premises changed materially on contact with the code.

**The shipped reference** (`models/artifacts/ncaaf_game_distribution_v1.json`, P1.4 `REFERENCE_STANDS`):

```
learner  = ridge (alpha=10)            contract = strength_only            form = strength_posterior
σ_margin = 16.087   σ_total = 16.747   ρ = 0.056
σ₀_margin = 15.608  k_margin = 0.573   σ₀_total = 16.435  k_total = 0.499
```

`strength_only` resolves (via `_is_strength`) to the 25 columns prefixed `home_strength*`,
`away_strength*`, plus `strength_margin_diff`. **That is the entire feature set of the shipped
model.**

### Verified findings that CHANGE the registered hypotheses

| # | Spec premise | Verified against the code/data | Consequence |
|---|---|---|---|
| **V1** | "replace the single constant `hfa`" | ⭐ **There is no `hfa` term at all.** `is_neutral_site` is NOT in `strength_only`, and `strength_margin_diff` is a rating difference that carries no home-field component (P1.2 estimates `home_field` as a separate fixed coefficient which never reaches the P1.4 matrix). The ridge INTERCEPT absorbs one constant home bump, blended over a training mix that is **7.93 % neutral-site (660 games)**. | H1 is a **stronger** hypothesis than registered: the shipped model gives a neutral-site bowl game the same home bump as a true road trip. H1a is the first-order fix; H1b is the per-team refinement. |
| **V2** | "the spread runs on NET `strength_margin`, so two same-net teams with opposite profiles get an identical spread" | ⛔ **FALSE as stated.** `home_strength_offense`, `home_strength_defense`, `away_strength_offense`, `away_strength_defense` **are all in `strength_only`** as linear terms, so opposite profiles already get different spreads. | The real gap is the **INTERACTION**: ridge is additive and structurally cannot express off-vs-def matchup. H2 is re-scoped to the interaction, and this correction is recorded rather than quietly fixed. |
| **V3** | H6 bowl regime | `is_postseason` is in `_ID_COLS` → **excluded from EVERY P1.4 contract.** No arm in the 125-config P1.4 search ever saw a bowl flag. 441 postseason games (5.30 %). | H6 registered as a genuine structural absence, not a refinement. |
| **V4** | H12 "is win-prob-gated garbage-time exclusion applied? (P1.1's NFL flag was WP∉[0.05,0.95])" | **Answered: exclusion IS applied, but it is SCORE-MARGIN-gated, not win-probability-gated** — `fact_ncaaf_play.is_garbage_time` = margin > 43/37/27/22 by quarter. The `*_clean_*` features are the excluded variants and are **not** in `strength_only`. | H12 becomes a matched clean-vs-raw pair plus the recorded answer that the gate is margin-based. |
| **V5** | H10 weather ("confirm venue weather is available before registering") | ⛔ **No weather anywhere in the NCAAF lake.** CFBD `/games` `raw_json` carries no weather keys; no weather source exists in `ingest/sources.py`; no weather column exists in the matrix. | **H10 is NOT REGISTERED.** Recorded as a DATA-UNAVAILABLE scope finding, never scored — a hypothesis that cannot be measured must not enter the deflation field. |
| **V6** | doc §6.2 compact matchup set | Of the 9 named interactions, only **4** are constructible from the P1.3 matrix (rush-off vs rush-def, explosiveness gen-vs-allowed, pace, run/pass stylistic conflict). Pass-off vs pass-def, standard/passing-down, havoc, finishing-drives vs red-zone-D and pressure susceptibility-vs-generation have **no defensive counterpart column**. | The missing 5 ARE constructible from the `plays` Delta (2.20 M plays, 2014–2025 — carries `playType`, `down`, `distance`, `yardsGained`, `ppa`, scores). P2.1 builds a leakage-safe as-of-date rollup so H2b tests the **full** doc §6.2 set rather than a silently truncated half of it. |

### Exposure counts — measured BEFORE registration (design quantities only, no outcome association)

Per NF-D20: an arm registered over a population its mechanism cannot move produces a vacuous pass.
Counts are over the 8,325 completed games from 2015 (the P1.2 strength floor):

| mechanism | exposed rows | share |
|---|---|---|
| neutral-site (H1a) | 660 | 7.93 % |
| postseason/bowl (H6) | 441 | 5.30 % |
| venue elevation > 1200 m (H1a) | 542 | 6.51 % |
| dome venue (H1a) | 189 | 2.27 % |
| away travel > 1500 km (H1a) | 1,255 | 15.08 % |
| \|rest differential\| ≥ 6 d (H3) | 1,370 | 16.46 % |
| either team off a bye ≥ 10 d (H3) | 2,170 | 26.07 % |
| QB starter changed recently (H7) | 1,853 | 22.26 % |
| home teams with ≥ 30 home games (H1b pool) | 130 of 137 | median 58 home g/team |

⚠️ **Dome (2.27 %, 189 rows) is too thin to carry its own arm** and is registered only as one column
inside H1a's pooled venue block. No arm is registered on a population below ~5 %.

---

## 1. Reference, metric and gates — fixed in advance

### 1.1 The incumbent
`ridge / strength_only / strength_posterior`, exactly as shipped, on the exact P1.4 fold structure:
`PurgedWalkForwardSplit(min_train_seasons=3, year_col='game_year', date_col='game_date')` →
**8 season-forward, date-purged folds (2018 … 2025)**. Ordering is by calendar date, so it is monotone
with `season_order_week` and immune to the postseason `week`=1 collision.

### 1.2 Matched-pair construction (NF-D10)
Every hypothesis arm is `reference features ∪ {that hypothesis's block}` with **everything else
byte-identical** — same learner, same alpha, same form, same folds, same draw count, same seed. The
read is the PAIRED delta versus the reference, never a leaderboard rank: a rank cannot distinguish
"my structure is inert" from "my structure is in a tie."

### 1.3 Primary selection metric — CRPS (§0.5: CRPS-primary, ⛔ never MAE)

```
primary = mean CRPS(margin) + mean CRPS(total)        (lower is better)
```

computed by `crps_ensemble` on the drawn predictive. CRPS is proper and grades the point AND the
spread jointly, which is what a STRUCTURAL hypothesis moves. P1.4's own metric
(`PIT_max_decile_dev(margin) + PIT_max_decile_dev(total)`) is **reported as a secondary** — it was the
right selector for P1.4's question ("which distributional FORM"), but it is close to blind to a better
MEAN, which is what this battery is testing.

⚠️ MAE is forbidden here for the NF-D11/NF-D14 reason, and the degenerate ceiling below is what
PROVES the metric is not inverted rather than an assertion that it isn't.

### 1.4 The calibration GATE — a hard CONSTRAINT, never a target (NF1.8)

An arm is **ELIGIBLE** only if:

1. `calib_80 ≥ 0.78` on **both** margin and total (P1.4's 0.80 floor with its documented
   `_CALIB_FLOOR_TOL = 0.02` sampling tolerance), **and**
2. margin PIT is flat (`pit_is_flat`).

⭐ **Total PIT-flatness is deliberately NOT a constraint, and the reason is pre-registered:** the
shipped reference itself FAILS it (total PITdev 0.0218 vs the ~0.02 bar). Gating on a clause the
incumbent fails is the MH2.1(b) inversion — an incumbent-relative gate inverts exactly when the
incumbent is the defective one. Total shape is **NCAAF-P2.5's** scope. It is measured and reported for
every arm; it decides nothing here.

⛔ The floor is never tightened "for safety" and no tie is ever broken on headroom above it — both
are monotone in widening and the `max_width` degenerate wins them outright.

### 1.5 Statistical clauses

| clause | value at n=8 folds | source |
|---|---|---|
| fold-consistency | `cv_power.fold_consistency_clause(8)` — calibrated, false-fire ≤ 0.20, UNDEFINED rather than passed if unattainable | MH2 H8 |
| paired significance | one-sided paired test on the 8 per-fold CRPS deltas | — |
| multiplicity | **Benjamini–Hochberg FDR at α = 0.05 across the registered real arms** | §0.5 |
| PBO | `pbo_cscv` over the **ELIGIBLE real-arm set** (the search the selection actually ran) — anchors excluded, they are not promotion candidates | NF1.8 |
| DSR | `deflated_sharpe` on the per-bucket improvement series, gate **≥ 0.95** | §0.5 |

### 1.6 DSR-CONV — declared FORWARD (⛔ not adoptable after a failed gate)

`n_trials` = the **full declared field** (every real arm + every anchor). `V` (cross-trial Sharpe
dispersion) is measured over the **NON-degenerate, NON-diagnostic arms only**. Rationale, both halves
pre-committed:

* MH2.1(a): a DIAGNOSTIC anchor is never a trial for `V` — the `oracle_peek` arm sees the outcome, so
  its Sharpe would set the gate's own bar for a purely arithmetic reason.
* DSR-CONV: a pre-registered lose-by-construction DEGENERATE inflates `V` exactly as a huge winner
  would, making a real winner's whole-field DSR unclearable.

⭐ Exclusion is **non-monotone** and therefore is not a lever: it only lowers the bar for a genuinely
far-out designed loser. An arm qualifies as a degenerate **by design, declared here**, never by later
declaration. Both the with- and without-degenerate figures are reported; the **degenerate-excluded one
binds**, and `classify_null` is called with `degenerates_excluded_from_v=True` so its remedy prose
carries the correct provenance.

### 1.7 Anchors — declared forward, all four scored every run

| anchor | role | pre-registered expectation |
|---|---|---|
| `oracle_peek` | ORACLE FLOOR — the reference arm with the realized margin/total appended as features. Same family (ridge), same sample (NF1.7(b)/NF1.9(f)). | **Nothing may beat it.** An arm that does ⇒ the metric is inverted. |
| `permute` | PERMUTATION anchor — the reference arm fit on SHUFFLED outcomes. Well-posed at any n, which is why it and not a thin fitted oracle is the unit anchor (NF1.7(b)). | must LOSE decisively |
| `zero_width` | DEGENERATE CEILING (sharp) — σ collapsed to the `_MIN_SIGMA` floor. | must LOSE CRPS **and** FAIL the calibration floor |
| `max_width` | DEGENERATE CEILING (wide) — σ inflated ×3. | must **SATISFY** the coverage floor (proving the floor is a constraint a degenerate satisfies, not a criterion it wins — NF1.8) **and** LOSE CRPS decisively |
| `hfa_global` | MATCHED LEVEL-ONLY FOIL for H1b (NF-D15 g′) — the identical construction with per-team shrinkage taken to ∞, i.e. every team receives the same global HFA. | If H1b does not beat THIS, the effect is a global level, not per-team content — and the win is attributed to H1a, not H1b. |

⚠️ Per NF1.7(a): an anchor that fails to fit RAISES. It is never treated as a pass.

### 1.8 Nested-form tie guard (MLB Batter Props Ph2)

Every hypothesis arm strictly NESTS the reference (`ref ⊂ arm`), and a ridge at α=10 shrinks an
uninformative block toward zero, collapsing the arm onto its own foil. A `|ΔCRPS| < 1e-3` points
margin is therefore declared a **TIE**, refused as a win, and reported as `tie_with_foil`. A
numerical-precision "lead" is not a result.

### 1.9 Null classification

Every non-surviving hypothesis is classified with `cv_power.classify_null(...,
declared_field_size=<the count of registered REAL arms>, degenerates_excluded_from_v=True)` and the
report reads the **machine flag `field_remedy_admissible`**, not the prose (MH2.7). The eighth state
`CONSTRAINT_REFUSED` (NF-D18) is used where a null comes from the calibration constraint rather than
from the metric — such a null gets **no "more seasons" re-test trigger**, because no sampling error
accumulates against a hard constraint.

### 1.10 Edge claims

A calibration win is **not** an edge claim. Any arm claiming edge must additionally clear the
deflated vs-close CLV gate on the 2020–2025 closes: model-side ATS/OU hit rate **> 0.5238 breakeven
AND > the placebo**, under the same PBO/DSR deflation. P1.4's reference measured ATS 0.496
(placebo 0.497) and O/U 0.523 — a clean null. Absent that bar, every result here is
`best_alpha = 0` product value.

---

## 2. THE REGISTERED HYPOTHESIS SET (16 real arms)

Each arm is `reference ∪ block`. `Z(·)` is an in-fold z-score fit on TRAIN rows only.
`MatchupGap_k = Z(Off_k) − Z(DefAllowed_k)` per the doc §6.2 shape; the game-level term is
`home_gap_k − away_gap_k`.

### Tier 1 — structural gaps the model provably lacks

| id | arm | block | prior |
|---|---|---|---|
| **H1a** | `hfa_venue` | `is_neutral_site`, `game_venue_elevation_m`, `game_venue_is_dome`, `game_venue_is_grass`, `away_travel_km`, `away_altitude_change_m` | ⭐ highest — V1 shows the model has NO home-field term at all |
| **H1b** | `hfa_team_eb` | ONE column: an empirical-Bayes shrunk per-home-team HFA, estimated IN-FOLD on train rows only (team home-margin residual vs the global mean, shrunk by `n/(n+k)`) | medium — needs to beat `hfa_global` |
| **H1c** | `hfa_full` | H1a ∪ H1b | medium |
| **H2** | `matchup_interaction` | off-vs-def interaction on the strength split: `Z(home_str_off)·Z(away_str_def)`, `Z(away_str_off)·Z(home_str_def)`, and their difference | ⭐ high — V2: the levels are present, the interaction is structurally absent |
| **H2b** | `matchup_unit` | the **full doc §6.2 compact set** as MatchupGap diffs: rush (line-yards, stuff-rate), **pass** (plays-derived), **standard/passing-down** (plays-derived), explosiveness gen-vs-allowed, **havoc** (plays-derived), **finishing-drives vs red-zone-D** (plays-derived), pace, run/pass stylistic conflict, **pressure susceptibility vs generation** (plays-derived) | ⭐ high |

### Tier 2 — CFB situational spots

| id | arm | block |
|---|---|---|
| **H3** | `rest` | `home_rest_days`, `away_rest_days`, `rest_days_diff`, off-bye indicators (≥10 d) both sides |
| **H4** | `lookahead_letdown` | next-opponent and previous-opponent strength (schedule known pre-game; opponent strength taken AS-OF-NOW, never a future rating), and the "big game next week" / "big win last week" gaps |
| **H5** | `rivalry` | ⚠️ **PROXY, declared as such**: no rivalry list exists in the lake. Proxy = the pair met in ≥4 of the prior 6 seasons, × late-season week. A proxy null is a null about the PROXY, and the report says so. |
| **H6** | `bowl` | `is_postseason`, and `is_postseason × strength_margin_diff` (does regular-season strength transfer to bowls?) |

### Tier 3 — dynamic / non-stationarity

| id | arm | block |
|---|---|---|
| **H7** | `qb_regime` | `qb_starter_changed_recent`, `qb_starts_prior`, `qb_distinct_starters_prior`, `qb_trailing_qbr`, `qb_trailing_ypa` (diffs). ⚠️ LIGHT flag only — the availability LAYER is NCAAF-P2.7. |
| **H8** | `recency` | trailing-3-game realized margin minus season-to-date margin (a trend residual), computed from strictly PRIOR completed games |

### Tier 4 — environment / style

| id | arm | block |
|---|---|---|
| **H9** | `pace` | `seconds_per_play`, `off_plays_per_game`, `possession_seconds_per_game` — as both a diff (margin) and a SUM (the total axis, where pace should act) |
| ~~H10~~ | ~~`weather`~~ | ⛔ **NOT REGISTERED — data unavailable (V5).** Scored by nothing, counted in no field. |

### Tier 5 — noise / regression

| id | arm | block |
|---|---|---|
| **H11** | `turnover_luck` | season-to-date turnover differential, entered shrunk toward zero (the regression-to-mean hypothesis) |
| **H12** | `garbage_clean` | matched clean-vs-raw pair: `off/def_clean_ppa`, `off/def_clean_success_rate` diffs **and** their raw counterparts, so the PAIR is what is read (V4) |
| **H13** | `special_teams` | plays-derived, leakage-safe: FG% and attempt rate with mean FG distance, punt net average, ST touchdowns for/against, blocked kicks |
| **H16** | `preseason_weight` | `strength_margin_diff × 1/(1+games_played)` and the games-played shrink terms — the LIGHT preseason-prior weight foil (the deep cold-start state-space init is NCAAF-P2.6) |

**Declared field size = 16 real arms + 1 reference + 5 anchors = 22 configs.** Every one counts toward
`n_trials`. `V` is measured over the 16 real arms + reference (17), excluding the 5 anchors.

### Combined-survivor arm — declared forward

If ≥2 real arms clear BH-FDR, **exactly one** additional arm is scored: the union of the surviving
blocks. It is added to `n_trials` (making 23) and is subject to the identical gates. No second
combination, no iteration — that would be the search this document exists to bound.

### Cross-sport carry (story AC)

Any survivor among **H1 (venue/team HFA)** and **H2/H2b (matchup)** is sport-agnostic structure and is
flagged in the dossier for **NFL-N1.1** and **NCAAB**. A null for these two is equally informative for
those verticals and is recorded with the same emphasis.

---

## 3. Data + cost hygiene

ONE assembly pass → ONE parquet (`betting_ml/data/cache/ncaaf_p2_1_battery.parquet`), read by every
arm × fold. Sources: the P1.3 `feature_pregame_matrix` Delta, the `plays` Delta (for the H2b/H13
rollup), the `games` Delta (dates), and the P1.4 CLV close staging. **Snowflake-free** — DuckDB over
S3 throughout, off the MLB serving lane.

The plays rollup is aggregated per game, joined to the game DATE, and accumulated **strictly by prior
date within a team-season** — so it inherits the same date-monotone, postseason-collision-immune
ordering the P1.4 CV uses, and a team's week-`w` feature can never see week-`w` plays.

---

## 4. What a clean null means here

Most of this battery is expected to be null (P1.4 + the MLB efficiency prior), and a null is a valid
deliverable. But it is only trustworthy if it is CLASSIFIED — this report will name, per hypothesis,
which of the eight MH2 states applies and will state the margin in the unit that grows
(folds / seasons / rows), never in p-value decimals. A `GENUINE_ABSENCE` gets no re-test trigger; a
`POWER_LIMITED` gets one only if it is reachable; a `CONSTRAINT_REFUSED` gets none at all.

---

_Pre-registered 2026-08-15, before the first hypothesis was scored. Amendments (if any) appear below
this line, dated, and never as edits to the body._
