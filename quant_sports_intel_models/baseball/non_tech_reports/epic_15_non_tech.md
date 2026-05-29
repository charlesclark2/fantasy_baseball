# Epic 15: Building a Time Machine for the Feature Store

## What Epic 15 Was About

Every day, the system makes predictions about baseball games. Those predictions depend on dozens of inputs: weather forecasts, projected lineups, the starting pitcher, betting market percentages, park dimensions, and more. Each of those inputs has a value *at prediction time* — and that value may change before first pitch, or may have been different yesterday than it is today.

Epic T (the immediately preceding work) stopped the permanent erasure of historical state by converting all ingestion scripts to append-only. What Epic 15 did was take that preserved raw history and restructure the database so that any downstream feature table can answer the question: *"What did this value look like at any point in the past?"*

This property is called **SCD-2** (Slowly Changing Dimension, Type 2) — a database pattern where instead of overwriting a record when it changes, you close the old version with an end timestamp and insert a new version with a start timestamp. The result is a complete audit trail of every value, every time it changed, and exactly when.

---

## The Problem Epic 15 Was Solving

Before this work, the feature tables used by the model were **current-state only**. When a lineup changed, the old lineup was gone. When a weather forecast updated, the old forecast was overwritten. When a public betting percentage shifted intraday, the earlier value was lost.

This creates two problems:

**1. We can't audit past predictions.** If the model made a bad prediction on a specific game, there's no way to replay exactly what inputs it saw. The data that existed at 10 AM when the prediction ran may look completely different by 3 PM.

**2. We can't backtest properly.** Any attempt to train or evaluate a model on historical data is silently contaminated. If a game's predicted lineup at 10 AM showed Player A starting but he was scratched at noon, and the training data only shows the post-scratch lineup, every historical training example has been quietly inflated with information that wasn't available at the time the prediction would have been made.

Epic 15 fixed the structure of the database so that both of these problems go away — for historical data where it's recoverable, and for all future data going forward.

---

## What Was Actually Built: Eight Marts Converted

### 15.1 — Betting Lines and Odds

**What changed:** The odds table was restructured to record every line movement, not just the final odds. Each time a sportsbook changed the spread, total, or moneyline, a new timestamped row was added and the prior row was closed.

**Why it matters:** A model trained on "the line at game time" is fundamentally different from one trained on "the line at prediction time." Line movement is itself a signal — a total dropping from 9.5 to 8.5 means sharp money came in on the under. That information can only be captured if every movement is preserved.

**Coverage:** Full historical replay was possible because the underlying raw data was already append-only. 136,457 historical rows populated across 9,670 games going back to 2020.

---

### 15.2 — Lineup State

**What changed:** Lineup data now records every version of a team's announced lineup for a given game. A lineup posted at 10 AM and then updated at noon (scratched player) now produces two timestamped records, not one.

**Why it matters:** Lineup state is one of the highest-signal inputs to any game prediction. A late scratch of a key batter can shift the expected run total meaningfully. If the model doesn't see that scratch — or sees it too late — the prediction is made on stale data.

**Coverage:** Forward-only from 2026-05-12 (Epic T conversion date). Pre-conversion history is unrecoverable — the MERGE pattern overwrote it. 1,544 rows loaded; 10 pre-game scratches captured in first few weeks.

---

### 15.3 — Player Injury Status

**What changed:** The injury table was promoted to the full SCD-2 pattern, with proper temporal bounds on every player's injury period. The lineup feature table now uses point-in-time joins against this table rather than a simpler static lookup.

**Why it matters:** A player may be on the injured list for one segment of the season and return later. The lineup model needs to know whether a given player was injured on a given game date, not just whether they're injured today.

**Coverage:** Full historical replay from 2021 — the underlying transaction data was always append-only. Oldest source of complete historical coverage in the feature store.

---

### 15.4 — Projected Starters

**What changed:** The projected starting pitcher table was rebuilt to capture each time the projected starter changed. A game might post Pitcher A as the probable at 72 hours out, then switch to Pitcher B at 24 hours due to injury. Both states are now preserved.

**Why it matters:** The starting pitcher is the single most important feature in total runs prediction. Training on a pitcher who didn't actually start produces a corrupted data point. Prediction made on a starter who was later scratched without knowing about the scratch is systematically wrong.

**Coverage:** Forward-only from 2026-05-12. Pre-conversion history uses a sentinel date to indicate "original posting, change tracking not yet active."

---

### 15.5 — Weather Forecasts

**What changed:** Weather was restructured so that every forecast update for a game is preserved. An afternoon game might have a forecast from the night before, another from 6 hours before first pitch, and a final update 1 hour out. All three are now independently queryable.

**Why it matters:** Weather has a meaningful effect on scoring in outdoor parks. A 20 mph wind blowing out is worth roughly 0.5 additional runs compared to a calm night. If the model saw a calm forecast at prediction time but actual conditions were windy, that's a real gap — but it's also auditable now.

**Coverage:** Forward-only from 2026-05-01 (Epic T.2 conversion). Historical weather forecasts as they existed at prediction time are not recoverable for prior seasons.

---

### 15.6 — Public Betting Percentages

**What changed:** The Action Network betting percentage data (what fraction of money and tickets are on each side of a bet) was restructured to preserve every intraday shift. When 60% of bettors favor the over at 9 AM and 72% favor it by noon, both states are now captured.

**Why it matters:** Public betting percentages are useful both as a model feature and as an edge-detection signal. Sharp money movement — when the line moves despite heavy public betting on one side — is a known indicator of informed action. That signal only exists if the data is captured at multiple points during the day.

**Coverage:** Forward-only from 2026-05-07. There is also a permanent gap: Action Network's API does not serve historical betting percentages before 2024-02-22. Pre-2024 betting percentage data does not exist anywhere and cannot be recovered.

---

### 15.7 — Umpire Assignments

**What changed:** Home plate umpire data was restructured with point-in-time tracking so that late substitutions (when the originally assigned umpire can't work the game) can be captured.

**Why it matters:** Umpires have measurable and persistent tendencies — some call a wider strike zone, some are tighter. The total runs model benefits from knowing who is actually behind the plate. A substitution that happens 2 hours before first pitch changes the relevant umpire features for that game.

**Coverage:** Forward-only from ~2026-05-02. No intraday umpire substitutions have been captured yet — all 25,731 games currently have a single umpire row. The system is in place and will capture substitutions as they occur.

---

### 15.8 — Park Factors

**What changed:** Park factors (how much each ballpark inflates or suppresses scoring relative to a neutral environment) were given a proper temporal structure organized by venue and season. Retired stadiums (ones no longer in use) were correctly closed out so they don't appear as "current."

**Why it matters:** Park factors shift gradually over time — rule changes, humidor installation, wall modifications, altitude adjustments. Having one factor per park per season (rather than one global value) gives the model more accurate historical context.

**Coverage:** Full historical from 2015–2026 across 36 venues (362 rows). This was the most tractable conversion because park factors are annual and stable — minimal complexity, high historical completeness.

---

### 15.9 — Validation: Does It Actually Work?

The final story was a systematic audit of the entire Epic 15 effort: pick three real historical games, run AS-OF queries against all the rebuilt SCD-2 tables, and verify that the feature values at prediction time match what was actually stored in the prediction snapshot.

**Part 1 — Feature reconstruction:** For games 823384, 824280, and 824360 (all predicted on 2026-05-15 at 14:06 UTC), the AS-OF queries against weather, public betting, and park factor tables returned the exact same values that were stored in the prediction record at the time of prediction. 18 out of 18 field comparisons matched exactly. **This confirms that the SCD-2 infrastructure works as designed.**

**Part 2 — Model reconstruction:** The original goal was also to verify that loading the stored model and running it on the stored feature snapshot reproduces the original prediction within ±0.001. This was initially deferred because the prediction pipeline was storing raw feature values rather than post-imputation values, creating gaps of 0.8–1.9 units that made exact reconstruction impossible.

Story 15.10 fixed this: the prediction pipeline was updated to store the post-imputation feature vector (the exact input the model saw) rather than the raw pre-imputation values. After that fix shipped, Part 2 was re-run against 3 live snapshots from 2026-05-29:

- game_pk=822732: stored=10.071926, reconstructed=10.071926, Δ=0.000000 ✓
- game_pk=822894: stored=8.044533, reconstructed=8.044533, Δ=0.000000 ✓
- game_pk=822978: stored=8.955847, reconstructed=8.955847, Δ=0.000000 ✓

**All three passed with zero delta.** The validation script now auto-discovers the most recent live snapshots on every run, so this check will continue to verify future predictions without needing to update hardcoded game identifiers.

---

## What Epic 15 Enables

**Honest backtesting.** The most important consequence. When a model is trained on past games, it can now be constrained to only use information that was available at the time a prediction would have been made. A lineup scratch that happened at 1 PM should not be visible to a model that's being evaluated on a 10 AM prediction window. With SCD-2 tables, this constraint can be enforced.

**Full auditability of past predictions.** For any prediction the system has ever made, it's now possible to reconstruct (or closely approximate) the exact feature values it saw. This is the foundation of any rigorous post-hoc analysis: "the model was wrong about this game — what did it believe, and was the belief reasonable given the information available?"

**Closed-loop value tracking (CLV).** Closing Line Value measures how accurate your predictions were relative to where the betting market settled just before game time. Computing this accurately requires knowing what the line was at prediction time, not at game time. Epic 15 is what makes that computation trustworthy.

---

## What It Doesn't Fix (Yet)

Several data sources have permanent historical gaps where data was lost before Epic T converted the ingestion scripts:

- **Lineup state before 2026-05-12**: Gone. The MERGE pattern overwrote all prior states.
- **Weather forecasts before 2026-05-01**: Gone for the same reason.
- **Public betting % before 2026-05-07**: Gone for the raw-capture gap; also permanently gone before 2024-02-22 from the Action Network API itself.
These aren't failures of Epic 15 — they're documented and understood. Epic T stopped the bleeding; Epic 15 built the structure. Future data is fully captured.

---

*Epic 15 completed 2026-05-29. All 10 stories shipped. AS-OF validation passed 18/18 field comparisons across 3 games. Prediction reconstruction passed 3/3 with Δ=0.000000 after 15.10 post-imputation vector storage fix.*
