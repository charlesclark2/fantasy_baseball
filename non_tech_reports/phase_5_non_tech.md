# Phase 5: Putting It All Together — From Models to a Working Prediction System

## What Phase 5 Was About

Phase 4 built and evaluated three machine learning models — one each for total runs, run differential, and win probability. Phase 5 had one clear goal: **turn those models into a working prediction system you can actually run before a game is played.**

This meant solving three distinct problems:

1. **Which model do we actually use?** Phase 4 explored multiple model types per target. Someone had to look at all the results and make a final, committed selection — then package those models in a way the rest of the system could reliably load.

2. **How do we go from model files to an actual prediction?** A trained model sitting in a folder does nothing. We needed a script that could take today's date, pull all the relevant data, run it through the models, apply the probability math developed in Phase 4, and produce a ranked list of games with actionable information.

3. **What happens when starting lineups are announced?** In baseball, confirmed lineups dramatically change the picture — a team's offensive stats mean more when you know exactly who's playing. The system needed a way to automatically detect when lineups went official and trigger a data refresh.

All three components were built and validated during Phase 5. The result is a system that, for any given game day, can produce predictions and rankings without manual intervention beyond having credentials to connect to the database.

---

## Part 1: Choosing the Final Models

### The Problem with "Best During Testing"

Throughout Phase 4, every model was evaluated using a technique called cross-validation — essentially running the same model on many different time slices of historical data and averaging the results. That process identified winners for each prediction target. But there's a difference between "best model on average during testing" and "the specific model files we commit to running in production."

Phase 5 made that decision concrete. For each of the three targets, we:

- Reviewed the Phase 4 evaluation results side by side
- Selected a single winning model
- Labeled it as the production version

```
Final Model Selections
─────────────────────────────────────────────────────────────────
Target              │ Winner
────────────────────┼────────────────────────────────────────────
Total Runs          │ NGBoost (LogNormal distribution)
                    │ Avg error: 3.57 runs
                    │
Run Differential    │ NGBoost (Normal distribution)
                    │ Avg error: 3.45 runs
                    │
Win Probability     │ XGBoost with Platt calibration
                    │ Brier score: 0.2393
                    │ (beats sportsbook benchmark of 0.2395)
─────────────────────────────────────────────────────────────────
```

Each selected model was saved with a `_prod` label — think of it as stamping "approved for use" on a specific version of the model, so that future changes don't accidentally overwrite or confuse which file is the official one. A rollback to a previous version is as simple as swapping a file path.

### The Model Registry

With three production models selected, the system needed a single place to look them up. We created a **model registry** — a small configuration file that lists, for each prediction target, exactly which model file to use and when it was selected.

The purpose of the registry is simple: any piece of the system that needs to load a model — whether it's the prediction script or the Streamlit app — reads from this one file. If the approved model ever changes, you update the registry once and everything else picks it up automatically. No hunting through code to find where each model is referenced.

### Extra Care for Win Probability

Win probability required one additional step that total runs and run differential did not.

The Phase 4 win probability model was calibrated during testing — meaning its raw confidence scores were adjusted to match real-world outcomes (if the model says 65% home win, it should be right about 65% of the time). But the way calibration was done during testing used data that overlapped with training, which is fine for benchmarking but not ideal for the model you'll actually deploy.

For production, we ran a stricter version:

```
Win Probability Production Calibration — Three-Step Process
───────────────────────────────────────────────────────────
Step 1 — VERIFICATION:
  Train model on:     2016–2023 seasons
  Calibrate using:    2024 season  ← never seen by the model
  Evaluate on:        2025 season  ← never seen by either step
  
  Purpose: confirm calibration generalizes before committing to production

Step 2 — PRODUCTION REFIT:
  Train model on:     2016–2024 seasons  ← more data = better
  Calibrate using:    2025 season  ← dedicated calibration hold-out
  
  Purpose: use all available history for the actual production model

Step 3 — VERIFICATION CHECK:
  Calibration error delta: +0.0028  ← well within the 0.005 threshold
  Verdict: PASS  ✓
───────────────────────────────────────────────────────────
```

The check confirmed that the production calibration held up when evaluated on data neither the model nor the calibrator had seen. The small positive delta (+0.0028) means the production calibration is only slightly less precise than the testing benchmark — well within acceptable range.

The final production model for win probability was saved with a note indicating it was calibrated using 2025 data as the dedicated hold-out, so anyone reading the registry knows exactly how it was built.

---

## Part 2: The Prediction Script

### The Goal

The prediction script — called `predict_today.py` — is the daily workhorse. Run it on any morning with a game schedule, and it:

1. Pulls the pre-game data for that day from the database
2. Loads the three production models
3. Scores every game
4. Applies the probability math from Phase 4
5. Produces a ranked list of games, sorted by how far our model's estimate diverges from the betting market

```
What predict_today.py Does, Step by Step
──────────────────────────────────────────────────────────────────
Step 1  │ Query today's games from the database
        │ Focus on games where:
        │   • Odds data is available  (has a market line to compare against)
        │   • Both lineups are confirmed  (we know who's actually playing)
        │
Step 2  │ Load the three production models from the model registry
        │
Step 3  │ Score every game:
        │   • NGBoost total runs model → P(over line) and P(under line)
        │   • NGBoost run differential model → win probability estimate
        │   • XGBoost win probability model → calibrated win probability
        │
Step 4  │ Apply the Bayesian probability layer:
        │   • Load the α mixing weight (best_alpha = 0.0)
        │   • Compute: edge = model probability − market implied probability
        │   • Compute: Kelly fraction (suggested bet size relative to bankroll)
        │
Step 5  │ Output:
        │   • Ranked table printed to screen (sorted by edge, largest first)
        │   • Parquet file: probability_outputs_{date}.parquet
        │   • CSV file: predictions_{date}.csv (all games, including non-odds)
──────────────────────────────────────────────────────────────────
```

### A Note on Best Alpha

In Phase 4, the Bayesian mixing step found that the best mixing weight (alpha) was 0.0. This means the market's implied probability is actually better calibrated than our model's probability on its own — at least for now. The practical effect: when we compute "edge," we're comparing our model's raw prediction directly against the market line without blending them together.

This isn't a failure. It's an honest finding: the sportsbook consensus is a very good calibrator, and the model's main value is in *identifying where it disagrees with the market*, not in overriding the market's probability estimate. The edge signal — how far the model's prediction strays from the market line — is the primary actionable output.

### The Fallback Problem

One known limitation was documented explicitly: the database only populates pre-game features *after* the nightly data pipeline runs, which happens in the early morning hours. If someone tries to run the prediction script in the afternoon on game day before the pipeline has refreshed, the query returns empty and the script exits with "no games found."

The ideal solution is a real-time fallback that assembles features on the fly using live data from MLB's public Stats API. The groundwork for this was laid, but the full implementation was left for a future sprint — it's a complex piece of engineering that would have delayed the rest of Phase 5 without adding value to the core functionality.

### What the Output Looks Like

When the script runs successfully, the screen output shows one row per game, sorted by how interesting each matchup is from a betting standpoint:

```
Example Output — Rankings by Edge (Largest First)
─────────────────────────────────────────────────────────────────────────────────
Signal  Matchup              Time    P(Over)  Model%  Market%  Post%  Edge  Kelly
─────────────────────────────────────────────────────────────────────────────────
🟢     NYY @ BOS            7:10p   61%      54.2%   49.1%    49.1%  +5.1%  5.1%
🟡     PHI @ ATL            7:20p   48%      47.8%   51.2%    51.2%  -3.4%  0.0%
⚪     CHC @ MIL            8:10p   52%      50.1%   50.8%    50.8%  -0.7%  0.0%
⛔     LAD @ SF             10:15p  —        —       —        —      —      —
─────────────────────────────────────────────────────────────────────────────────
🟢 = abs(edge) > 5%, lineups confirmed   ⛔ = No odds data available
```

Green rows are the ones worth taking a closer look at. The Kelly fraction tells you the suggested stake as a percentage of your bankroll, based on how large the edge is and how confident the model is.

---

## Part 3: The Lineup Monitor

### Why Lineups Matter

In baseball, the starting lineup is announced a few hours before game time. Up until that announcement, pre-game features are built on *expected* lineup configurations — typically the team's most common recent lineup. Once the lineup is confirmed, those features can be refreshed with exact information: this specific player is batting second, this one is sitting out today.

A lineup monitor that catches confirmation events and triggers a data refresh turns the system from "reasonably accurate pre-game" to "as accurate as possible at game time."

### How It Works

The lineup monitor is built around a **Snowflake Task** — an automated job that runs on a schedule without any human involvement. Here's how the full pipeline works:

```
Lineup Monitor Architecture
──────────────────────────────────────────────────────────────────

Every hour (on the hour):
┌──────────────────────────────────────────────────────────────┐
│  Snowflake Task (task_lineup_monitor)                        │
│  Runs automatically at the top of every hour, 24/7          │
│                                                              │
│  1. Look at today's games in the lineup database table       │
│  2. For each game, check if both home AND away lineup        │
│     are confirmed (i.e., actual players are listed)          │
│  3. If confirmed AND we haven't already logged this game:    │
│     → Record it in lineup_monitor_state (prevents repeats)   │
│     → Send a trigger to GitHub via the API                   │
│  4. Log this run to pipeline_run_log regardless of outcome   │
└──────────────────────────────────────────────────────────────┘
                              │
                              │ (GitHub API trigger)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  GitHub Actions Workflow (dbt_staging_build.yml)             │
│                                                              │
│  Triggered automatically when the Snowflake proc fires       │
│                                                              │
│  1. Install dbt-fusion (the data transformation tool)        │
│  2. Run: dbt build for lineup-dependent data models          │
│  3. Refreshed lineup data is now available in the database   │
└──────────────────────────────────────────────────────────────┘
```

The key design principle: no emails are sent at this stage, and no human needs to be watching. The system detects the event, refreshes the data, and the updated numbers are ready whenever the prediction script is next run.

### Deduplication

One subtle problem: if the task runs hourly and lineups go official at 10:30am, the task will detect confirmed lineups at 11:00am, trigger the refresh — and then *also* trigger it again at 12:00pm, 1:00pm, and every hour after. That would be wasteful and potentially disruptive.

The system handles this with a **deduplication table** (`lineup_monitor_state`). When a lineup refresh is triggered for a given game on a given day, a record is written to that table. Every subsequent hourly check does a "has this already been triggered?" lookup before firing — and skips games that are already recorded. Each game gets exactly one refresh trigger, no matter how many times the task runs.

### Status at Phase 5 Completion

The lineup monitor was 22 out of 23 acceptance criteria complete at the end of Phase 5. All the infrastructure is live and verified — the task is running, the GitHub workflow responds to triggers, the deduplication logic is in place. The one remaining criterion was simply waiting for a real game day with confirmed lineups to generate a real dispatch log entry. That will self-complete on the next day with an actual game schedule.

Email notifications when lineups lock were intentionally scoped out of Phase 5 and deferred to Phase 6.

---

## Summary: What Phase 5 Delivered

| Component | Status | What It Does |
|---|---|---|
| Model Registry | Complete | Single source of truth for which production model files to load per target |
| Production Model Files | Complete | `_prod` copies of all three models, clearly labeled and version-controlled |
| Win Probability Calibration | Complete | Proper three-step calibration refit; verification check passed (delta +0.0028) |
| `predict_today.py` | Complete | Runs on any game date; queries data, scores games, computes edge, outputs ranked table + files |
| Parquet/CSV Output | Complete | Structured output files consumed by Phase 6 application layer |
| Lineup Monitor Task | Substantially complete (22/23) | Hourly Snowflake task detects confirmed lineups and triggers data refresh automatically |
| GitHub Actions Workflow | Complete | Rebuilds lineup-dependent features in the database when triggered |

### What's Still Open

- **Intraday data fallback:** Running the prediction script in the afternoon before the nightly pipeline runs returns empty. A Stats API fallback to assemble features in real time is planned for a future sprint.
- **Lineup monitor live dispatch:** One acceptance criterion — seeing a real log entry from an actual lineup confirmation — will complete on the next game day automatically.
- **Email notifications:** Intentionally deferred to Phase 6. The infrastructure to trigger a rebuild is live; the "notify me when lineups are confirmed" layer comes next.

---

*This report covers Phase 5 work completed as of April 27, 2026. For context on the models themselves, see the Phase 4 non-technical report. For what comes next — the Streamlit application and betting sizing layer — see the Phase 6 non-technical report.*
