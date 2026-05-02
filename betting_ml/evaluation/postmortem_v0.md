# v0 Model System Post-Mortem

## Overview

The v0 system spans Phases 1–6 through Card 6.G: data ingestion from the MLB
Stats API and The Odds API, a feature engineering pipeline in dbt/Snowflake,
NGBoost and XGBoost models for total runs and home win probability, a Bayesian
probability layer, and a daily prediction CLI (`predict_today.py`) backed by a
Streamlit app. The evidence base is 1,098 scored game rows across 36 dates
(2026-03-27 through 2026-05-01), of which 941 have non-null
`h2h_market_implied_prob` (has_odds rows). The central finding: the model is not
beating the market. Mean h2h edge is approximately −0.017 after the
consensus_win_prob fix applied in Card 6.H (−0.036 on NGBoost alone), with ~35%
of predictions showing positive edge. The purpose of this document is to identify
the highest-impact architectural and feature improvements before Phase 7
investment begins. Periodic retraining of the current model is explicitly not on
the roadmap — model quality must improve first.

---

## Known Gaps — Analysis

### Gap 1 — Model does not improve on market calibration (best_alpha = 0.0)

**What:** Card 4.13 found best_alpha = 0.0 — the Bayesian mixing weight that
minimizes log-loss on held-out CV folds. Log-loss rises monotonically from
α = 0.0 (0.683) to α = 1.0 (0.731). The model adds no calibration value over
simply trusting the market line.

**Evidence:** As of 2026-05-01, `alpha_tuning_results` has only 1 row
(alpha=0.0, log_loss=NULL) — the Card 6.F full 11-row α grid re-run is
pending. `best_alpha` cannot be validated against corrected odds data. The
historical 11-row grid was recorded in `probability_layer_results.md` from a
terminal run but is not reproducible from Snowflake. Additionally, the original
alpha tuning was performed on an odds dataset affected by two pipeline bugs
(UTC/ET timezone mismatch and `commenceTimeTo` cutoff), which excluded all late
West Coast games from `has_odds = true`. The tuning may have been performed on
a systematically biased sample.

**Root cause (confirmed/revised):**
- Feature set does not carry information unavailable to the market: **confirmed** —
  market Brier = 0.2395 vs. model Brier = 0.2423; model is meaningfully worse.
- Training window era misalignment: **likely** — post_2022_rules flag may not
  fully capture 2026 run environment drift.
- Missing features (weather, umpires, injury status): **confirmed as contributing** —
  these are real-time market inputs absent from v0.
- Odds data incompleteness biased alpha tuning: **confirmed** — UTC/ET bug and
  commenceTimeTo cutoff excluded late West Coast games from training sample.

**Phase 7 priority:** P1

**Recommended action:** Re-run `run_probability_layer.py` after the Card 6.F
fix completes (full 11-row α grid with corrected odds data). If best_alpha
shifts away from 0.0, update `alpha_tuning_results` and `best_alpha.json`. Even
if best_alpha stays 0.0, the model needs better probability calibration (ECE
improvement) via feature additions before the Bayesian layer adds value.

---

### Gap 2 — Systematic home-team underestimation in h2h edge

**What:** The model systematically under-predicts home team win probability
relative to the market, producing negative mean h2h edge across the full 2026
season.

**Evidence:** Using 941 has_odds rows (2026-03-27 through 2026-05-01) from
`daily_model_predictions`:
- NGBoost alone: mean h2h edge = −0.0361, 22.95% positive
- consensus_win_prob (0.5 × NGBoost + 0.5 × XGBoost isotonic): mean h2h
  edge = −0.0166, 35.39% positive

The consensus_win_prob fix (Card 6.H) halved the negative bias, confirming that
NGBoost run_differential-derived win probabilities are systematically lower than
the XGBoost isotonic classifier on this target. Even after the fix, edge is
still clearly negative — ~65% of predictions are below market.

**Root cause (confirmed/revised):**
- NGBoost run_differential-to-win-probability derivation introduces systematic
  downward bias: **confirmed** — the 12.8-point gap between NGBoost-alone (22.95%)
  and consensus (35.39%) positive rates shows the issue is specific to the
  NGBoost path.
- consensus_win_prob not formalized as official model_prob: **confirmed and fixed
  in Card 6.H**.
- Residual bias after consensus fix: **inconclusive** — 35.39% positive is still
  well below 50%; deeper calibration investigation needed.

**Phase 7 priority:** P1

**Recommended action:** Investigate whether residual bias is concentrated in
specific contexts (road favorites, high-run-environment parks, afternoon games)
using the 2026 backfill. Consider a logistic recalibration layer trained on 2026
edge residuals once ≥100 game results are available.

---

### Gap 3 — Total runs MAE barely improves over the naive baseline

**What:** The v0 totals model achieves CV MAE = 3.5718 (NGBoost Normal,
n_estimators=200), a ~0.7% improvement over the naive global mean baseline
(approximately 3.59 runs). The tuned XGBoost achieves 3.5655 but is inviable
for production (no pred_dist).

**Evidence:** From `model_registry.yaml`: `total_runs` cv_mae = 3.5718. The
naive NB01 baseline is approximately 3.5–3.6 runs (global mean). The strongest
individual feature correlations are park_run_factor (r = 0.122) and elevation
(r = 0.111); no feature exceeds r = 0.13. Away pitching asymmetry: Card 3.9
found `away_pit_xwoba_against_30d` r = 0.008 vs. home pitching r = 0.075 for
total_runs — the model heavily underweights away pitching. Weather is entirely
absent.

**Root cause (confirmed/revised):**
- Low signal ceiling in current feature set: **confirmed** — max r = 0.122 from
  any single feature.
- Weather excluded (wind at Wrigley ~2-run swing): **confirmed as gap** —
  highest-expected-lift missing feature.
- Away pitching asymmetry underweighted: **confirmed** — Card 3.9 found era-specific
  asymmetry (18.2× in modern era vs. 5.8× pre-juiced ball).
- Umpire zone tendency absent: **confirmed as gap** — affects K%/BB%, no data
  source secured.

**Phase 7 priority:** P1 (weather features), P2 (umpires, away pitching investigation)

**Recommended action:** Implement weather features first (temperature, wind
speed/direction relative to park orientation, humidity for outdoor parks) — GPS
coordinates already available in `stg_statsapi_venues`. Expected lift: 0.2–0.3
runs MAE.

---

### Gap 4 — alpha_tuning_results table incomplete (1 row vs. 11 needed)

**What:** The production Card 4.13 run used `--use-alpha 0.0` as a bypass. The
Snowflake `alpha_tuning_results` table has 1 row (alpha=0.0, log_loss=NULL)
instead of the required 11 (one per α candidate 0.0, 0.1, ..., 1.0). The
per-α log-loss values from the original terminal run are recorded in
`probability_layer_results.md` but are not reproducible from Snowflake.

**Evidence:** As of 2026-05-01, querying `alpha_tuning_results` returns 1 row
(alpha=0.0, log_loss=NULL). The Card 6.F fix to re-run the full grid is not yet
complete. Card 6.E's Performance Tracker will have no α grid to visualize.

**Root cause (confirmed/revised):**
- Implementation shortcut at Card 4.13 delivery: **confirmed** — `--use-alpha`
  bypass flag added to accelerate delivery.

**Phase 7 priority:** P1 (blocking calibration validation)

**Recommended action:** Re-run `run_probability_layer.py` without the
`--use-alpha` bypass flag once corrected odds backfill is complete. All 11 α
rows will persist correctly. One-command fix.

---

### Gap 5 — best_alpha.json local fallback not written

**What:** `predict_today.py` loads `best_alpha` from `alpha_tuning_results` with
a fallback to `betting_ml/models/best_alpha.json`. That file was never written.
On Snowflake failure, the script silently defaults to alpha = 0.5 — a
significant miscalibration relative to the tuned value of 0.0.

**Evidence:** Tied to Gap 4 / Card 6.F status. As of 2026-05-01, `best_alpha.json`
does not exist in `betting_ml/models/`. The silent fallback to 0.5 would shift
h2h_posterior_prob materially toward the market line, degrading calibration.

**Root cause (confirmed/revised):**
- Noted as a known gap at Card 4.13 delivery: **confirmed** — explicit TODO in
  Card 4.13 known gaps list.

**Phase 7 priority:** P1 (links to Gap 4; resolve together)

**Recommended action:** After the Gap 4 fix (full α grid re-run), add
`json.dump({"best_alpha": best_alpha, ...})` to `run_probability_layer.py` and
update `predict_today.py` to read it as the fallback before defaulting to 0.5.
Thirty-minute fix once Gap 4 is resolved.

---

### Gap 6 — Intraday feature assembly fallback not fully reliable

**What:** `predict_today.py` queries `feature_pregame_game_features` in Snowflake.
Any run before the nightly dbt pipeline completes (~08:30–09:00 ET) returns an
empty DataFrame and exits with "No games found." The Card 5.2
`load_todays_features_via_statsapi()` fallback was never implemented.

**Evidence:** The window during which `predict_today.py` returns "No games found"
spans from midnight ET until approximately 08:30–09:00 ET (when `daily_ingestion.yml`
→ `dbt_daily_build.yml` chain completes via `workflow_call`). With GHA now
triggering dbt immediately after ingestion, the window has narrowed but has not
been eliminated. Morning lineup-lock prediction runs before ~09:00 ET are
unreliable.

**Root cause (confirmed/revised):**
- Deferred at Card 5.2 delivery due to complexity: **confirmed** — assembling
  rolling stats inline without dbt requires non-trivial engineering.

**Phase 7 priority:** P2

**Recommended action:** Implement `load_todays_features_via_statsapi(target_date)`
in `data_loader.py` using cached rolling stat snapshots from the prior day's dbt
build. Medium complexity; high usability value once the Streamlit app is the
primary consumer.

---

### Gap 7 — Feature set excludes highest-signal missing inputs

**What:** Three categories of pre-game information are incorporated by the market
but absent from the v0 feature set: weather, umpire zone tendency, and
player injury/lineup status. FanGraphs data (Stuff+, pre-season projections,
hitter/pitcher matchup splits) represents a separate and high-value gap addressed
in Gap 8.

**Evidence:** From Card 3.9 / Card 4.12 EDA:

| Missing feature | Correlation / signal | Priority |
|---|---|---|
| Weather (temp, wind, humidity) | Park factor r=0.122, elevation r=0.111; wind ~2-run swing at Wrigley | P1 |
| Umpire zone tendency (k%/bb%) | Affects total runs via K/BB rates; intraday availability | P2 |
| Injury/lineup status | Market-facing; not in rolling stats (1-day lag) | P2 |
| Per-batter bat tracking | Team avg too noisy (NB06 ΔR² < 0.001) | P3 |

Expected totals MAE improvement: weather ~0.2–0.3 runs; umpires ~0.1 runs;
injury status hard to quantify but market-facing. GPS coordinates for weather
already available in `stg_statsapi_venues`.

**Root cause (confirmed/revised):**
- Weather excluded from v0 by design (backlogged to Card 4.B1): **confirmed**.
- Umpire data source not yet secured: **confirmed**.
- Injury status requires external API commitment: **confirmed** — no ingestion
  path exists.

**Phase 7 priority:** P1 (weather), P2 (umpires, injury status)

**Recommended action:** Implement weather features first (Card 4.B1) — highest
expected lift, data source exists, GPS coordinates in hand. Umpire tendency
(Card 4.B2) second once a data source is identified.

---

### Gap 8 — No FanGraphs data pipeline: advanced pitcher metrics, pre-season projections, and matchup splits absent

**What:** FanGraphs publishes several high-signal data sets that are entirely
absent from the v0 feature set: Stuff+ (pitch-level arsenal quality), pre-season
Steamer/ZiPS/PECOTA projections (the market's primary calibration anchor in
April/early May before sufficient in-season rolling stats accumulate), and
season-level hitter vs. pitcher handedness and pitch-mix splits. The v0 model
relies exclusively on rolling stats with Bayesian shrinkage for early-season
games — exactly when the market most relies on projection systems the model
cannot replicate.

**Evidence:**
- Early-season prediction quality is unquantified but structurally suspect: with
  fewer than 15 games in a rolling stat window, `home_pit_era_30d`,
  `away_pit_xwoba_against_30d`, and similar features carry minimal signal.
  Pre-season projections (e.g., Steamer600 wRC+ and FIP) provide a stable
  anchor that does not degrade with small samples.
- Stuff+ (scale: 100 = league average, 110 = one SD above) measures per-pitch
  movement and velocity quality independent of outcomes — a leading indicator
  of pitcher performance that the market incorporates, especially for starters
  in their first 30–40 IP.
- Hitter vs. pitcher matchup coverage in the current feature set is team-level
  (team wRC+, team ERA). Per-lineup matchup splits (e.g., LHH vs. RHP K%,
  slider-heavy pitcher vs. lineup contact rate) are absent and represent the
  next granularity level of pre-game information the market uses.
- No FanGraphs ingestion script, dbt model, or Snowflake table exists in the
  current codebase.

**Root cause (confirmed/revised):**
- FanGraphs data requires a separate ingestion pipeline (CSV exports or
  third-party wrapper like `pybaseball`): **confirmed** — not in scope for
  Phases 1–6.
- Early-season model quality never benchmarked against mid-season quality:
  **inconclusive** — April-specific MAE/Brier not yet segmented.

**Phase 7 priority:** P1 (pre-season projections for early-season calibration),
P2 (Stuff+ and pitch-mix metrics), P2 (hitter/pitcher matchup splits and pitcher
clustering)

**Recommended action:** Stand up a FanGraphs ingestion layer using `pybaseball`
or direct CSV exports as the initial data source. Ingest Steamer projections once
pre-season and refresh mid-season with in-season projections. Add Stuff+ for
all rostered starters. Build hitter/pitcher matchup split features once the
ingestion layer is stable. Pitcher clustering is a downstream Phase 7B card
that depends on per-pitch arsenal data being available.

---

## Phase 7 Roadmap

Initiatives are ordered by expected lift / implementation cost ratio. The
roadmap is focused entirely on closing the model-vs-market gap — improving edge
distribution and calibration — not on operational cadence.

---

### P1 — Re-run probability layer (full α grid) with corrected odds data

**Why P1:** `alpha_tuning_results` has 1 row with a NULL log_loss (Gap 4). This
blocks: (a) auditable validation that best_alpha = 0.0 is correct on the full
corrected odds dataset; (b) the Card 6.E Performance Tracker α-grid
visualization; (c) writing `best_alpha.json` to eliminate the silent
alpha=0.5 fallback (Gap 5). The original α tuning was performed on a
biased odds sample that excluded all late West Coast games due to two pipeline
bugs now fixed. best_alpha may shift away from 0.0 once the full corrected grid
is run — this is the fastest possible check on whether the Bayesian layer can
add calibration value. Implementation: one command (`uv run python
betting_ml/scripts/run_probability_layer.py`), under 15 minutes.

- Re-run `run_probability_layer.py` without `--use-alpha` bypass (Gaps 1, 4, 5)
- Write `best_alpha.json` after α grid completes
- Verify whether best_alpha shifts from 0.0 on corrected odds data

---

### P1 — Weather features for outdoor parks (Card 4.B1)

**Why P1:** Weather is the highest-signal missing feature for the totals model
by a wide margin. Wind at outdoor parks (Wrigley Field, Fenway, Coors) produces
documented ~2-run swings. Park factor (r=0.122) and elevation (r=0.111) are the
strongest features in the current set — weather variables sit in the same signal
range and are not correlated with anything already in the model. GPS coordinates
are already available in `stg_statsapi_venues`. Expected MAE improvement: 0.2–0.3
runs, which would close roughly half the gap to the naive baseline. Implementation
is medium-high effort (weather API integration + dbt feature table) but the
highest expected-lift single investment in Phase 7.

- Add temperature, wind speed/direction (relative to park orientation), humidity
  to the feature set for outdoor parks
- Source from a weather API using GPS coordinates from `stg_statsapi_venues`
- Add as features to `feature_pregame_game_features` via new dbt model

---

### P1 — Home-team probability calibration

**Why P1:** After the consensus_win_prob fix (Card 6.H), 35.39% of has_odds
predictions show positive h2h edge — still well below 50%. The model
systematically underpredicts home win probability relative to the market even
with the consensus blend. This is not a data pipeline issue; it is a calibration
deficiency in the classifier. As 2026 game results accumulate, a calibration
curve analysis (reliability diagram, ECE) on home win predictions should identify
whether the bias is uniform or context-specific. Platt re-scaling or isotonic
recalibration trained on 2026 in-season data is the targeted fix. Implementation:
low effort once 100+ 2026 results are available.

- Compute calibration curve (reliability diagram) for home win predictions
  using 2026 actuals once ≥100 results are available
- Apply Platt scaling or isotonic recalibration if systematic bias confirmed
- Re-measure mean h2h edge and % positive after recalibration

---

### P1 — FanGraphs ingestion pipeline + pre-season projections (Gap 8)

**Why P1:** The model has no stable early-season anchor. In April and early May,
rolling stats (ERA_30d, xwOBA_30d) are based on 5–15 starts and carry
near-zero predictive signal — yet the market uses Steamer/ZiPS projections as
its primary calibration input for the first 4–6 weeks of the season. This is a
structural hole: the model is most blind exactly when the season starts and
stakes are highest for early bettors. Pre-season projections are stable,
publicly available (FanGraphs Steamer CSV exports or `pybaseball`), and slot
directly into the existing feature assembly path as additional columns on
`feature_pregame_game_features`.

- Stand up a FanGraphs ingestion script using `pybaseball` or direct CSV export
  (Steamer/ZiPS wRC+, FIP, xFIP, K%, BB% at the player level)
- Ingest once pre-season; refresh at the All-Star break with in-season
  projections
- Add projection features to `feature_pregame_game_features` dbt model,
  blended with rolling stats using a sample-size-adaptive weight
  (projection weight → 0 as `games_played_30d` grows past ~40)
- Benchmark April-specific MAE and Brier separately from full-season to
  quantify early-season lift

---

### P2 — FanGraphs Stuff+ and pitch-arsenal quality metrics (Gap 8)

- Ingest per-pitcher Stuff+ and pitch-mix data (velocity, movement, usage %)
  for all rostered starting pitchers via FanGraphs or Baseball Savant
- Add starter Stuff+ as a feature for both the totals model (K rate proxy)
  and the home win classifier
- Expected signal: Stuff+ is a leading indicator in the first 30–40 IP before
  outcomes stabilize, and it captures true stuff changes (e.g., velocity drop,
  new pitch added) that rolling ERA does not
- Prerequisite: FanGraphs ingestion pipeline from the P1 card above

---

### P2 — Intraday feature fallback (load_todays_features_via_statsapi)

- Implement `load_todays_features_via_statsapi(target_date)` in `data_loader.py`
  using cached rolling stat snapshots from the prior day's dbt build
- Eliminates the pre-09:00 ET "No games found" window (Gap 6)

---

### P2 — Umpire tendency features (Card 4.B2)

- Add per-umpire k%/bb% adjustment features once a data source is secured
  (Baseball Reference, Retrosheet, or Statcast umpire data)
- Expected totals MAE improvement: ~0.1 runs

---

### P2 — Injury and lineup status features

- Source real-time injury and confirmed lineup data from MLB Stats API or an
  external feed (ESPN, FanGraphs)
- Market-facing feature; hard to quantify expected lift but addresses a known
  market information gap

---

### P2 — Individual hitter vs. pitcher matchup metrics (Gap 8)

- Aggregate per-batter historical plate discipline splits (K%, BB%, ISO)
  against right-handed vs. left-handed starters and against pitch-mix archetypes
  (e.g., slider-heavy, fastball-dominant)
- Roll up to lineup-level weighted averages using confirmed lineup data
  (already available from `stg_statsapi_lineups_wide`)
- Adds the next granularity level beyond team wRC+ / team ERA: the specific
  offensive matchup against the scheduled starter's pitch mix and handedness
- Source: FanGraphs splits CSV exports or Baseball Savant query API;
  prerequisites: confirmed lineup ingestion (already in place) and FanGraphs
  ingestion pipeline

---

### P2 — Pitcher clustering model + hitter performance by cluster (Gap 8)

- Cluster all MLB starters into archetype groups using arsenal-level features:
  primary pitch type, velocity band, horizontal/vertical break, usage mix,
  and Stuff+ by pitch
- Suggested initial archetypes (6–8 clusters): power fastball/swing-and-miss,
  pitch-to-contact sinker-ball, elite breaking ball (slider/curve-dominant),
  changeup-heavy deceptive, soft-tossing command, multi-pitch mix
- For each cluster group, compute how each lineup (or hitter) performs
  historically — team wRC+ vs. cluster, team K% vs. cluster, lineup ISO vs.
  cluster — as additional features
- Expected benefit: captures the "style matchup" signal the market prices
  (e.g., strikeout-heavy lineup vs. swing-and-miss starter) that raw ERA/FIP
  does not reflect
- Implementation: unsupervised clustering (k-means or HDBSCAN) on
  per-pitcher arsenal vectors; cluster assignments updated seasonally;
  new dbt feature table `feature_pitcher_cluster_matchups`
- Prerequisite: Stuff+ and pitch-arsenal ingestion from P2 card above

---

### P2 — Phase 7 prediction backfill: re-score 2026 season with improved model

- After any P1 model change (calibration fix, weather features, FanGraphs
  projections) is merged, re-run `predict_today.py` (or a batch equivalent)
  over all 36+ scored 2026 dates to regenerate `daily_model_predictions` with
  the updated feature set and probability outputs
- Compare the new mean h2h edge and % positive edge against the v0 baseline
  (−0.0166, 35.39%) to measure the actual lift from each P1 improvement
- This backfill is the primary validation signal for Phase 7: if edge
  distribution does not improve materially after adding weather features and
  FanGraphs projections, the root cause is deeper (calibration or architecture)
  and the Phase 7 roadmap ordering should be revisited
- Backfill script should accept `--start-date` / `--end-date` flags and write
  to `daily_model_predictions` with a `model_version` tag so v0 and Phase 7
  predictions coexist in the table for direct comparison
- Prerequisite: at least one P1 model improvement merged and validated

---

### P3 — Production web app (replace Streamlit MVP)

- Phase 7 app card: replace the Streamlit MVP with a production-grade web
  application once the underlying model quality warrants the investment

---

### P3 — Model retraining on 2026 data

- Execute mid-season refit (Card 6.F) once ≥50 2026 regular season games
  complete and edge distribution shows meaningful improvement from P1 work
- Retraining the current architecture on more data without fixing the
  feature/calibration gaps is not expected to produce market-beating predictions;
  this is explicitly a P3 item, not P1

---

**Summary:** The two highest-impact Phase 7 investments are (1) weather features
for outdoor parks (Card 4.B1) — highest single-feature signal with an existing
data path and expected 0.2–0.3 run MAE lift — and (2) a FanGraphs ingestion
pipeline with pre-season projections, which is the only way to close the
structural early-season prediction gap the market exploits through Steamer/ZiPS
calibration that the v0 model cannot replicate.
