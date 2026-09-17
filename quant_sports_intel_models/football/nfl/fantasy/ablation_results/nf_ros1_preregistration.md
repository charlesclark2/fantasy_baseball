# NF-ROS1 — pre-registration: an honest in-season REST-OF-SEASON value (prior × 2026 realized, games-remaining aware)

Registered 2026-09-17 (branch `nf-ros1`), **BEFORE any arm is fitted or scored.** Nothing in §1–§12
may be re-read after a result lands (E2.1-r). Post-run findings go in §13, appended — never edited
into the registration. A refused ship bar is closed out as a certified NO and is **not retried with a
softer bar**.

⚖️ `best_alpha = 0` · calibration/honesty product · no win-rate/edge claims · no serving-page code ·
no WVR1/trade surface change. Spec: `plan_specs/nfl_fantasy/nf-ros1.yaml`.

What has been looked at before this commit, stated so the registration's blindness is auditable:
table/parquet SCHEMAS (column names, row counts by position), Delta table HISTORY (write
timestamps), file hashes, and `cv_power` design quantities. **No realized ROS figure, no arm, no
anchor, no residual, and no match rate has been computed.** This registration quotes no number from
any measurement of an arm (the PM 2026-09-01 provenance ruling — the claim is about substance, not
about which files exist).

---

## §1 The gap (quoted from the parent record, not paraphrased)

`docs/nf_wvr1_fa_pool_diagnosis.md` §1: the season board is a FULL-SEASON projection (`max g =
17.000` with week 1 complete; 53 rows with `g > 16`); its 2026-responsive channels are *"depth chart
· roster status · injury & designation status · Vegas win totals · ADP/ECR — Role, health and
market — not production"*; *"Fernando Mendoza tops the available pool at 268.3 projected points and
did not take a snap in week 1"*. §2: the FA pool ranks *"6 QB / 3 TE / 16 K by points and 14 K /
8 DST / 2 TE / 1 QB by VOR"*. Correct for drafting; structurally wrong for "what changed since the
draft". This story builds the missing quantity and certifies it — or certifies that it cannot.

---

## §2 Substrate (spec-premise rule — verified, with the witness named)

| input | what is read | pin | verified how |
|---|---|---|---|
| **realized facts** | `s3://credence-sports-lakehouse/nfl/raw/stats_player_week`, `season_type='REG'` | Delta **version 28** for history (time-travel); the serving build reads latest | Delta history read 2026-09-17 04:1xZ |
| **schedule / byes** | `nfl/raw/schedules`, `game_type='REG'` | Delta **version 36** for history | same |
| **historical prior (QB/RB/WR/TE)** | `nf1_5_season_projections_{Y}.parquet`, Y = 2019…2025 — the SERVED lineage (`nfl_fantasy_nf1_5_v1`, base = Y−1) | sha256 prefixes below | schema read |
| **historical prior (K)** | `nfl_fantasy_kdst_projections_{Y}.parquet`, Y = 2019…2025, `position='K'` | sha256 prefixes below | schema read |
| **serving prior (2026)** | the PUBLISHED `s3://<api-cache>/fantasy/nfl/2026/projections.json`, its `generated_at` + `model_version` stamped onto the artifact | read at build time | — |
| **scorer** | `app/backend/services/league_scoring.score_row` over `realized_stat_fields.flatten_realized_row` (realized) and over the board's raw `proj_*` line (prior), with the `league_presets` standard / half-PPR / full-PPR configs. **No fourth scorer.** | — | code read |

sha256 (first 16 hex) of the gitignored historical priors, read from the MAIN checkout (the
NF-INFRA1 / NF-INJ3c rule: a fresh worktree lacks them and must not rebuild them):

```
nf1_5 2019 e7640a1026b5ac9d · 2020 c0a7aa5d3d8277ce · 2021 a6645484fd204937 · 2022 b76490e08c123f5a
      2023 abebdff5be7e9bbc · 2024 3aa7150e245a54af · 2025 3580273de0469b1d
kdst  2019 8c5955a8eb134254 · 2020 ab4513d2cafc5692 · 2021 83a11dc70dfa2527 · 2022 317bc59367da943f
      2023 f0593e8c851e70dc · 2024 5efac9750e2901a9 · 2025 509633c49b466bce
```

The harness REFUSES to run if any hash differs (a different prior vintage is a different study).

**NF-INC-0916 ingest state — verified by EXECUTION WITNESS, not row count (PM 2026-09-13 ruling).**
`stats_player_week` Delta history shows `WRITE season = 2026` at **2026-09-16T02:43:28Z** (the
recorded one-off) and again at **2026-09-16T15:30:26Z** = 08:30 PT, the `sports_nfl_weekly_serving_schedule`
cron (`30 8 * * *` America/Los_Angeles). `snap_counts` shows the same pair. The recurring writer has
fired since the one-off. The dev→main promote chain is live on `origin/main` (merges #1149, #1154,
#1158; `origin/main..origin/dev` = 5 commits at read time). 2026 carries week 1 only (week 2 unplayed).

**The weekly MODEL's outputs are NOT used.** Silence would already mean none; this line makes it
explicit. The INC-0916 lift is a fact about the INGEST (which this story reads as facts); the
weekly projection model (served at 0.355 of realized) is out of bounds and no output of it is read.

### §2.1 Declared population and handling (no NaN arithmetic)

* **Evaluated positions: QB, RB, WR, TE, K.** FB rows on historical boards are dropped (the served
  2026 board has none).
* **D/ST is NOT evaluated** — `realized_stat_fields._DST_REASON`: *"team defence scoring is a TEAM
  total … This line is one row per PLAYER, so it carries neither."* Scoring team-defence ROS would
  need a team-week substrate outside this story. The artifact carries every D/ST row with
  `rosPts = null`, `absence = "position_not_evaluated"`.
* **Population per season Y:** every evaluated-position player on the Y preseason board. A board
  player with no realized row is a **real zero** (played 0 games), never dropped
  (`include_zero_game` discipline).
* **Played** ≡ the player has a `season_type='REG'` `stats_player_week` row for that week. ONE
  definition on both the history and the serving side (E7.9 train/serve rule). Declared known limit:
  a snaps-only appearance with no box-score line (a blocking TE) is not counted as played.
* **Identity join** board → realized: gsis `player_id` first; then normalized name + position via
  `player_naming` (the WVR1 F4 ladder — 81 of the 2026 board's rows carry synthetic rookie ids).
  A name+position key that resolves to >1 realized id in a season is DROPPED from the evaluation and
  COUNTED. The match rate per season is a reported diagnostic (§10), measured in node 2.
* **Rookie with no realized history** — identical rule to any player with `n = 0`: the rate
  estimate IS the prior rate by construction (credibility weight on realized = 0). Rookies are a
  reported stratum.
* **In-season addition (no preseason prior)** — not in the evaluated population and not valued:
  artifact row absent from `players`; the manifest reports the count of realized players with no
  prior and their share of realized points to date, as a stated scope limit.
* **Player team** = the team on his most recent played week; else the board team.
* **Prior per-game rate** `r0` = the board raw stat line scored by the preset ÷ `max(proj_games,
  1.0)`. For QB/RB/WR/TE the full-PPR per-game points are capped at
  `REALIZED_MAX_SEASON_PACE[pos] / 17` (`frontend/lib/fantasy.ts:468` — QB 471.1, RB 512.3, WR
  435.2, TE 414.0; a Python mirror is added with a parity guard); when it binds the whole rate
  vector is scaled down proportionally, and the count of bound rows is reported. K is out of that
  anchor's scope (no cap).
* **Prior availability** `a0 = min(1, proj_games / G_team_season)`.

---

## §3 Target and evaluation design (registered before any fit)

* **Target** `Y_ros(k)` = realized league points in REG weeks `k+1 … last REG week`, scored by the
  preset through the scorer. Gate league = **full-PPR, 12 teams** (`league_presets.full_ppr`);
  half-PPR and standard are REPORTED.
* **Evaluation weeks** `k ∈ {1,…,12}`. WHY: an in-season waiver/trade value is consulted after
  every week; after week 12 at most 4–6 team games remain (16-game era ends week 17; 17-game era
  week 18), where a ROS total is dominated by a handful of games and the fantasy regular season is
  ending. Weeks are pooled with equal weight per (player, k) row; per-k results are reported.
* **Folds (walk-forward, expanding):** eval season Y ∈ **2020, 2021, 2022, 2023, 2024, 2025 (6
  folds)**, fitted on prior seasons 2019…Y−1. WHY this window: the served prior lineage
  (`nf1_5`) exists for 2019–2025 only; evaluating the blend on a DIFFERENT prior than the one it
  will be served on would calibrate its credibility weights to the wrong prior quality. 2019 is
  training-only because every fold needs ≥1 training season. The 16→17-game boundary (2021) is
  inside the window by design: games-remaining is computed from the schedule, never assumed.
* **Design quantities at 6 folds** (`cv_power`): `dsr_ceiling(6) = 0.9992` (does not bind at 0.95);
  `fold_consistency_clause(6)` → **5 of 6** wins (attained false-fire 0.109); MDE 1.15 SD
  (1 metric), 1.55 SD (5 metrics); `sign_test_floor(6) = 0.0156`; PBO evaluable.
* **Known biases, direction stated in advance:**
  1. the `nf1_5` learner selections were bake-off-selected over base seasons 2017–2024, and
     `run_season_projection.load_base_season` reads the LATEST `dim_player_role` record — both make
     the HISTORICAL prior look better than a true preseason prior. Effect: the incumbent is harder
     to beat (conservative for the ship bar) and the fitted prior strength `m` is biased LARGE.
  2. the SERVED 2026 prior is fresher than the historical one (daily depth/injury/designation
     updates; NF-INJ3b injury-games and NF-INJ4b designation policies are 2026-only). Effect: at
     serving, the fitted `m` under-weights a better-informed prior. Both are recorded, neither is
     corrected post hoc.

### §3.1 Primary metric

**CRPS on a 19-level quantile grid** (levels 0.05…0.95; `CRPS_q = 2·mean pinball`), full-PPR, per
(player-season, k) row. Every arm's predictive is its point plus the **same** residual-quantile
construction (§4.3), so arms differ only through their point.

* **Gate series:** per-fold (per eval season) mean CRPS lift over the incumbent, per position.
  CRPS is a per-row quantity that varies within a fold, so a per-fold series is admissible under
  the PM 2026-09-01 ruling (1) — that ruling binds the POOLED statistics in §5 (coverage, PIT),
  which are evaluated on ROWS, never as a fold series.
* **Reported beside it:** a player-block bootstrap CI (2,000 resamples, seed 20260917), MAE, RMSE,
  within-position Spearman of ROS vs realized for the top-24 by prior (QB/TE/K top-12), per-k and
  per-rookie-stratum lifts.

---

## §4 The form family (declared with mechanism)

### §4.1 Mechanism

A ROS total is `(points per game) × (games he will play)`. The preseason board supplies a prior for
both factors; each played week supplies evidence about both. The natural, minimal update is
**limited-fluctuation / Bühlmann credibility** on each factor: the prior counts as `m` games of
evidence. This family NESTS the incumbent exactly (`m = ∞` recovers the prorated prior), which is
what makes "does realized production add anything?" a well-posed test rather than a comparison
between unrelated models.

For player i at week k (team has played `t` games, has `G_rem` REG games left, bye-aware):

```
n      = games played through k            x̄   = realized points / n   (per preset)
r̂      = (m_r · r0 + n · x̄) / (m_r + n)    (n = 0 ⇒ r̂ = r0)
â      = (m_a · a0 + n)     / (m_a + t)    (clipped to [0, 1])
ROS    = r̂ · â · G_rem
```

The same `m_r` is applied to the whole per-game stat VECTOR, so the published ROS stat line scores
to exactly the ROS points under any linear preset (a measured coherence clause, §9).

### §4.2 The declared field (`declared_field_size = 3`; ⛔ never trimmed or grown — MH2.2)

| arm | rate | availability | role |
|---|---|---|---|
| `prior_prorated` | `r0` | `a0` | **INCUMBENT and binding foil** (= board points × `G_rem / G_season`) |
| `eb_rate` | credibility, `m_r` fitted | `a0` | real arm — the production channel alone |
| `eb_avail` | `r0` | credibility, `m_a` fitted | real arm — the availability channel alone |
| `eb_rate_avail` | credibility | credibility | ⭐ real arm — **the pre-registered PRIMARY** |

This is a 2×2 on the two channels with the incumbent in the (off, off) cell; the interaction is a
REPORTED quantity (`lift(both) − lift(rate) − lift(avail)`), and the two halves are never
recombined from separate measurements (NF-W7e). One winning FORM is selected on pooled full-PPR CRPS
across the five positions (§6); its parameters are fitted per position. Trials = the 3 real arms.

### §4.3 Fitting (in-fold only)

* `m_r, m_a` per position, chosen on the **grid** `{0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64,
  ∞}` (fixed here) by minimizing training-season **MSE** of full-PPR ROS points pooled over k.
  `∞` is on the grid so a collapse onto the incumbent is EXACT and FLAGGED
  (`collapsed_to_incumbent`) rather than a 1e-6 "lead" (the MLB-props nested-form lesson): a
  collapsed arm's lift is reported as a TIE, never a win.
* **Predictive:** for each preset, the 19 quantiles of the residual `y − ŷ` in training cells
  (position × k-bucket {1–3, 4–6, 7–9, 10–12} × within-position tercile of `ŷ`), added to `ŷ` and
  floored at 0, then sorted. Training residuals for training season `s` come from the arm fitted
  on the OTHER training seasons (leave-one-season-out inside the fold); fold 2020 has one training
  season, so its residuals are in-sample — declared, not hidden. A cell with < 40 residuals falls
  back to (position × k-bucket), then (position); the fallback count is reported.
* Every fit reads one assembled frame (parquet cache keyed on a SHA of the assembly code + inputs —
  the NF-C0e cache rule).

---

## §5 Anchors — SCORED every run, NEVER trials (excluded from V and from the PBO field)

| anchor | definition | registered to |
|---|---|---|
| `frozen_full` | the board's full-season points, not decremented — the literal commissioned complaint | **LOSE** |
| `naive_pace` | `x̄ · G_rem` (n = 0 ⇒ 0) | **LOSE** |
| `last3_pace` | mean points of the last ≤3 played games through k × `G_rem` (n = 0 ⇒ 0) | **LOSE** |
| `nihilist_zero` | 0 | **LOSE** (the NF-D11/D14 two-sided ceiling — its score is READ, not reasoned about) |
| `zero_width` | winner's point, interval collapsed to the point | **LOSE** (sharpness degenerate) |
| `max_width` | winner's point, interval [0, position's max training ROS] | **LOSE** (coverage-target degenerate; it must SATISFY the coverage floor and still lose — NF1.8) |
| `eb_permuted` | **MATCHED FOIL**: the primary's machinery with (x̄, n, last-3) permuted among players within (season, k, position); `m` refit on permuted training data | **LOSE to the winner** — attributes a win to PER-PLAYER content rather than to a level/league-wide shift (NF-D15) |
| `oracle_<form>` | the same form with `m` fitted on the TEST season (peeking), one per form (NF-D16 g‴) | a floor, see clause C8a |
| `matched_n_<form>` | the same form fitted on the single most recent training season only (≈ the oracle's n) | brackets the oracle at matched resolution, clause C8b (NF1.9 f) |

⚠️ **Registered forward (not presented as a pass later):** the oracle is fitted on MSE and judged on
CRPS, so a real arm can legitimately beat its own oracle on CRPS by a small amount (the NCAAF-P2.5
(b) divergence). Clause C8a therefore requires a violation to be both significant and material.

---

## §6 Ship bar (per position, declared before results)

Winner = the real arm with the lowest pooled (all five positions, all folds) full-PPR CRPS.
**Precondition (field-level, not per arm):** the pooled CSCV PBO over {incumbent + 3 arms} on
per-fold pooled CRPS is < 0.20 (`pbo_application = "field"`; if it fails, NO position ships — the
search is unstable, and that is reported as a field finding, never as an arm failure).

The winner SHIPS at position P iff every clause passes at P:

| # | clause | rule |
|---|---|---|
| C1 | `beats_incumbent` | mean per-fold CRPS lift over `prior_prorated` > 0 **and** not `collapsed_to_incumbent` |
| C2 | `fold_consistency` | `fold_consistency_clause(6)` ⇒ ≥ 5 of 6 folds won |
| C3 | `significant` | one-sided paired per-fold t p-value; **BH at q = 0.10 across the 5 positions** (the BH family = one form × five positions; no arm axis — DSR already deflates the form search) |
| C4 | `dsr_ok` | `deflated_sharpe(per-fold lifts, trial_srs)` ≥ 0.95 with `n_trials = 3`; **V's membership: the 3 real arms only** — the incumbent (identically-zero lift, MH2.1 a), the degenerates (DSR-CONV), the matched foil and every oracle/matched-n anchor are ∉ V |
| C5 | `beats_matched_foil` | mean per-fold CRPS lift over `eb_permuted` > 0 and ≥ 5 of 6 folds |
| C6 | `degenerates_lose` | every §5 LOSE anchor has pooled CRPS > the winner's at P |
| C7 | `coverage_floor` | 80% band row coverage ≥ `power_floor(n, 0.80, target 0.05)` (NF-D22 exact binomial) with **n = distinct player-seasons** at P (rows are clustered by player; the conservative effective n). A FLOOR, never a target. |
| C8a | `oracle_floor` | the winner does not beat `oracle_<winner>` by more than **1/10 of its C1 lift AND** with one-sided p < 0.05 |
| C8b | `matched_n` | `oracle_<winner>` CRPS ≤ `matched_n_<winner>` CRPS + 1e-9. If the two tie within 1e-4 the pair is **INACTIVE** — uninformative, not a fail (NF-W6d); C8a and C8b are DIFFERENT clauses and both are named (PM 2026-09-04) |
| C9 | `pit_flat` | pooled randomized-PIT (quantile-grid, seeded) max-decile deviation ≤ 0.05 at P, on rows |

* **Honest alternative, stated now:** a position where the winner fails any clause ships **no ROS
  value** — `rosPts = null`, `absence = "not_certified"` — and its consumers keep their stated
  absences. If no position ships, THAT is the finding: *realized 2026 production, as this family
  expresses it, does not improve on carrying the preseason prior forward* (or the gate cannot
  certify that it does), and the record says which.
* **Null classification:** every non-shipping position is classified with `cv_power.classify_null`
  (`n_folds = 6`, `n_arms = 3`, `declared_field_size = 3`, `degenerates_excluded_from_v = True`,
  `pbo_application = "field"`). A null bound by an ANCHOR clause (C5–C9) is `CONSTRAINT_REFUSED`
  with the binding half named and **no fold/season re-test trigger** (NF-D18). A `DSR_UNREACHABLE`
  reading publishes no "lower-variance design" or "more seasons" trigger without the lockstep check
  (NF-W8-0d).

---

## §7 The WAIVER-SPECIFIC replacement level (same registration; evaluated only if ≥ 2 positions ship)

**Mechanism (measured, WVR1 F2 + NF-C7/C5):** an FA pool is below replacement by construction, so
`value − starter replacement` is negative everywhere and low-dispersion positions float to the top.
A cross-position waiver value must reward *the chance of becoming a starter*, not *being close to a
starter while never exceeding one*.

* **League:** full-PPR, 12 teams, `league_presets.full_ppr` starters: QB 1, RB 2, WR 2, TE 1, K 1
  (FLEX ignored in the cutoff — declared). Starter cutoff counts `S = {QB 12, RB 24, WR 24, TE 12,
  K 12}`.
* **Rostered proxy (historical rosters are unknown):** K = top 12 by preseason prior points;
  QB/RB/WR/TE = top 156 by preseason draft VOR from `league_scoring.replacement_levels` on the
  preseason board (12 × 15 roster slots − 12 D/ST − 12 K). Fixed across k. **FA pool(k)** = the
  evaluated-position board players outside that set.
* **Orderings of the FA pool (declared field of 4, `declared_field_size = 4`):**

| ordering | score | role |
|---|---|---|
| `raw_ros` | ROS points | foil |
| `starter_vor_ros` | ROS − predicted starter cutoff (the S_P-th best ROS at P over all board players) | foil — the draft-VOR construction, registered to reproduce the float |
| `pool_relative` | ROS − the best FA ROS at P (the spec's candidate) | real — ⚠️ registered forward: its top scorer at EVERY position is exactly 0, so the cross-position order among the leaders is undetermined and ties are broken by `raw_ros`; the spec's reading is kept and scored, not reinterpreted |
| `expected_excess` | `E[(X − cutoff_P)⁺]` over the ROS predictive (19-level grid) | ⭐ **PRIMARY** — the option value of becoming a starter |

* **Metric:** per (season, k), take the top 10 of the FA pool by each ordering; utility = mean of
  `max(0, Y_ros − R_P)` where `R_P` is the REALIZED ROS of the S_P-th best player at P (a fact, not
  a prediction). Per-fold mean over k. Anchors: `oracle_order` (sort by realized utility — the
  ceiling), `random_order` (seed 20260917 — must lose).
* **Ship (cross-position surfaces only):** `expected_excess` ships iff it beats BOTH `raw_ros` and
  `starter_vor_ros` on mean per-fold utility, ≥ 5 of 6 folds each, one-sided per-fold t with BH at
  q = 0.10 over those 2 comparisons, and `random_order` loses. Otherwise waiver value is published
  `null` with `absence = "waiver_value_not_certified"` and cross-position ordering stays an absence;
  **within-position ordering ships on the ROS value alone** wherever §6 ships.
* **Reported diagnostic (the float, predicted in advance):** the count of K in each ordering's
  top 10 / top 25. Registered prediction: `starter_vor_ros` floats kickers; `expected_excess` does
  not. D/ST is absent from the whole comparison (§2.1) — the D/ST half of the WVR1 float cannot be
  tested here, and that is stated, not implied away.

---

## §8 Deliverable contract (born contracted — the NF-INC-0917B pattern verbatim)

`s3://<api-cache>/fantasy/nfl/ros/<season>/<through_week>/{manifest,players}.json` +
`fantasy/nfl/ros/<season>/current.json`. Pydantic contract module in `app/backend/models/`;
**validated dump** (what is written is `model_validate(...).model_dump()`, never the input dict);
**write-gate** (`missing_declared_fields` on every blob before any `put_object`, dry-run included);
**served-bytes assertion** (read back and compare `content_sha256`); **executing entrypoint smoke**
(`main()` run end-to-end with IO stubbed at the boundary). Per player: identity, `rosPts` / `rosP10`
/ `rosP90` for std/half/ppr, the ROS stat line, `gamesPlayed`, `teamGamesPlayed`,
`teamGamesRemaining`, `expGamesRemaining`, `priorRate`, `realizedRate`, `rateWeight`,
`availWeight`, `certified`, `absence`, `waiverValue`. Manifest: season, through-week, the prior's
`generated_at` + `model_version`, the facts table version, the form + per-position parameters, the
certification table verbatim from the decisive run, `best_alpha = 0`. Uncertified positions are
published as stated absences, never as numbers.

---

## §9 Measured clauses on the machinery (not gates on the model)

* `incumbent_identity` — `eb_*` at `m = ∞` reproduces `prior_prorated` at 1e-9.
* `stat_line_coherence` — the ROS stat line scored by each preset equals the ROS points at 1e-9.
* `no_future_leak` — every row's features read only weeks ≤ k (asserted on the frame by a
  week-shifted recompute).
* `reproduction` — every per-fold, per-arm, per-position CRPS of the decisive run is reproduced by
  a second invocation from the committed code at 1e-9 (the epsilon rule of PM 2026-09-04 applies to
  any quantized artifact comparison).
* `renderer_on_real_output` — the report and artifact writers are exercised on the smoke run's real
  output before the decisive run (PM 2026-09-01 ruling 2).

## §10 Reported diagnostics (never gates)

Board→realized match rate per season (id / name+position / dropped-ambiguous); pace-cap bind count;
residual-cell fallback count; fitted `m_r`, `m_a` per fold × position (and grid-edge hits);
interaction term; per-k and rookie-stratum lifts; half-PPR / standard lifts; share of realized
points held by off-board players; NF1.8 triad for the form search (flip distribution, performance
degradation, contender spread).

## §11 Out of scope

The weekly model's outputs (§2); D/ST valuation; injury/roster STATUS at week k as a covariate (the
served prior carries it, the historical one does not — §3 bias 2; a successor registers it forward);
any serving route, page or WVR1/trade surface; any change to the season board.

## §12 Runtime

The decisive run is expected to be minutes, not hours (a 2-parameter grid per position over one
cached frame). If a smoke shows > 2 minutes, the decisive run is handed to the operator as a
paste-ready command (spec standing rule).

---

## §13 Post-run findings

*(appended after the decisive run — never edited above this line)*
