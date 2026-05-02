# Phase 6: From Predictions to a Working Betting Application

## What Phase 6 Was About

Phases 1 through 5 built the engine. Phase 6 built the dashboard.

At the end of Phase 5, the system could already predict game outcomes and compare those predictions against betting market lines — but accessing those predictions required running a command-line script and reading raw numbers in a terminal window. That's useful for development, but it's not how you actually use a tool every day before placing a bet.

Phase 6 had one central goal: **turn the prediction system into a working application that a real user can open in a browser each morning and act on.**

Along the way, Phase 6 also surfaced an important and honest finding about where the model stands — and produced a clear roadmap for what needs to improve before the system can reliably beat the market.

---

## Part 1: The Application — "Diamond Edge"

The application was built using Streamlit — a framework that lets Python data work be displayed as an interactive web interface without requiring a separate web development effort. The app was named **Diamond Edge** and consists of four functional pages, each serving a distinct purpose in the daily workflow.

### The Daily Workflow

```
Morning of a Game Day
──────────────────────────────────────────────────────────────────
Step 1  │ Open Diamond Edge in the browser
        │
Step 2  │ Check "Today's Picks" — see which games are on the board
        │ and which ones the model flags as potentially interesting
        │
Step 3  │ Dig into "Market Comparison" for any games of interest
        │ — see how the betting lines are moving and what the
        │ sharp money appears to be doing
        │
Step 4  │ Review "EV & Kelly Sizer" — find bets with positive
        │ expected value and see the suggested bet size relative
        │ to your bankroll
        │
Step 5  │ Check back after games complete — "Model Performance"
        │ tracks how the model is doing over time
──────────────────────────────────────────────────────────────────
```

---

### Page 1: Today's Picks

The first page is the morning starting point. It answers: *"What's on today, and what does the model think about it?"*

The core of the page is a picks table — one row per game, showing:
- The matchup and game time (displayed in local time, not UTC)
- The model's estimated probability for each team to win
- The market's implied probability from the betting lines
- The calculated edge (the gap between model and market)
- A flag for whether the model considers the bet actionable

Additional features on this page:
- An **odds refresh button** that pulls the latest market prices without having to reload the entire page
- A **market movement expander** that shows whether lines have shifted since they first opened — which can signal where informed betting action has come in

If starting lineups haven't been confirmed yet for a game (which is common before ~3pm ET), the page shows a lineup-pending banner so you know the prediction is based on projected rather than confirmed rosters.

---

### Page 2: Market Comparison

The second page is for going deeper on any specific game. It answers: *"What is the betting market actually saying, and are sharp bookmakers (the ones that accept large bets) priced differently from recreational bookmakers?"*

```
Market Comparison — What You Can See for a Specific Game
──────────────────────────────────────────────────────────────────────
Moneyline Movement Chart  │ How the home/away win odds have shifted
                          │ since the line first opened — rising
                          │ prices on the home team suggest buying
                          │
Totals O/U Bar Chart      │ How the over/under total has moved —
                          │ direction tells you whether oddsmakers
                          │ are expecting more or fewer runs than
                          │ initially projected
                          │
Sharp vs. Soft Panel      │ Splits between high-limits bookmakers
                          │ (sharper pricing) and recreational books
                          │ (looser pricing) — divergence can signal
                          │ where informed money is
                          │
Cross-Bookmaker Table     │ Side-by-side odds across all available
                          │ books — find the best available price
                          │ if you decide to bet
                          │
Per-Bookmaker Deep-Dive   │ Each bookmaker's full history of price
                          │ changes for this game
──────────────────────────────────────────────────────────────────────
```

The page also shows a warning after a game has already started or completed, so you don't accidentally act on stale information.

---

### Page 3: EV Tracker & Kelly Sizer

The third page is where the model's recommendations get translated into specific bet sizing guidance. It answers: *"Which bets actually have positive expected value — meaning the model believes the true probability is higher than what the market is paying — and how much of my bankroll should I put on each one?"*

**Expected Value (EV)** is the core concept: a bet has positive EV when the model believes the true win probability is meaningfully higher than what the sportsbook's odds imply. Over a large number of bets, consistently finding positive-EV situations is the only mathematically sound path to profit.

**Kelly Criterion** is the formula that converts a probability estimate and the available odds into a recommended bet size. The suggestion is expressed as a fraction of your bankroll (e.g., "bet 3.2% of your current bankroll on this game"). Kelly is theoretically optimal for maximizing long-run bankroll growth when your probability estimates are accurate.

The page includes:
- An **All Markets EV table** covering four markets per game (home win, away win, over, under)
- An **Actionable flag** highlighting only the bets with positive EV above a minimum threshold
- A **Suggested Slate** that deduplicates correlated bets (e.g., backing both "home team wins" and "under the total" in the same game may not be independent) and presents a clean set of non-overlapping recommendations
- **Interactive checkboxes** that let you toggle games in and out of the slate and see how the combined metrics change in real time
- A **bankroll input field** that converts Kelly fractions into actual dollar amounts

---

### Page 4: Model Performance

The fourth page is the accountability dashboard. It answers: *"How has the model actually done?"*

This is the page that keeps the system honest — it shows real track record data, not just real-time recommendations.

```
Model Performance — What's Tracked
──────────────────────────────────────────────────────────────────────
Brier Score Trend         │ Rolling 14-day accuracy of win
                          │ probability predictions — model vs.
                          │ market benchmark side by side
                          │
Closing Line Value (CLV)  │ Whether the model's recommended bets
  Bar Chart               │ were on the right side of line movement
                          │ — a positive CLV bar means the market
                          │ moved to agree with the model after the
                          │ fact (a sign of genuine edge)
                          │
Cumulative P&L Simulation │ Hypothetical profit/loss over time under
                          │ two bet-sizing strategies: Kelly (as
                          │ recommended by the model) and flat
                          │ betting (same dollar amount each game)
                          │
Summary Metrics Row       │ At-a-glance accuracy numbers with
  with Tooltips           │ hover explanations of each metric
──────────────────────────────────────────────────────────────────────
```

All four sections support a Combined/Moneyline/Totals tab split and a global date-range filter so you can look at any time window in isolation.

---

### Application Branding and Navigation

Late in Phase 6, the application was consolidated and given a proper identity. The app was renamed **Diamond Edge** and given a dedicated home page that explains:

- What the system does and how it was built
- A navigation guide explaining when to use each page
- A model fact sheet summarizing how the predictions are generated
- A daily workflow expander showing the full data pipeline from overnight ingestion through prediction to the app display

The technical plumbing was also cleaned up: the application was refactored to use a modern page-navigation structure that makes it easier to add new pages in future phases.

---

## Part 2: The Automation Layer

Running the application each morning requires that the database be populated with fresh predictions before the browser opens. Phase 6 completed the automated pipeline that makes this happen without manual intervention.

### The Snowflake Task DAG

A **Task DAG** (directed acyclic graph of scheduled tasks) in Snowflake is the backbone of the overnight data refresh. Think of it as a chain of dominoes — one task fires, completes, and triggers the next automatically:

```
Automated Overnight Pipeline — What Runs While You Sleep
──────────────────────────────────────────────────────────
12:00 AM  │ Statcast pitch data ingested from Baseball Savant
          │   (all pitch-by-pitch data from yesterday's games)
          ↓
          │ MLB Schedule / Lineup data refreshed
          ↓
          │ Odds data pulled from The Odds API
          ↓
          │ dbt data models rebuilt (feature tables recalculated)
          ↓
~8:30 AM  │ predict_today.py runs — scores all today's games,
          │ writes predictions to the database
          ↓
          │ Diamond Edge app reads the fresh predictions
          │ — ready when you open the browser
──────────────────────────────────────────────────────────
```

### The 2026 Prediction Backfill

Before the performance tracking page could show anything meaningful, the system needed historical predictions to display. Phase 6 ran a backfill that scored every game from the start of the 2026 season (March 27) through May 1 — 1,098 game predictions written into the database. This is what the Model Performance page draws from.

---

## Part 3: The Honest Finding — Model Postmortem

The most consequential work in Phase 6 wasn't any of the application pages. It was the **v0 Model Postmortem**: a systematic analysis of how the model is actually performing relative to the betting market.

### The Central Finding

The model is **not beating the market.**

With 1,098 scored game predictions from the 2026 season:

```
Model Performance vs. Market — v0 Summary
──────────────────────────────────────────────────────────────────
Metric                        │ Initial Build  │ After Phase 6 Fix
──────────────────────────────┼────────────────┼──────────────────
Mean edge (model vs. market)  │ −0.036         │ −0.017
% of predictions positive     │ 22.9%          │ 35.4%
──────────────────────────────────────────────────────────────────
```

What these numbers mean in plain language: the model systematically **underestimates** win probabilities relative to what the betting market prices in. On average, when the model says a team has a 48% chance to win, the market is saying roughly 50–53%. That's not a betting edge — it's a calibration deficit.

### What Was Fixed in Phase 6

One specific bug was identified and corrected during the postmortem. The original prediction script was only using the NGBoost run-differential model to estimate win probability — which, it turns out, was systematically biasing estimates downward. The fix blended two probability estimates (NGBoost and the XGBoost win classifier from Phase 4) equally. That fix cut the mean negative edge in half and raised the share of positive-edge predictions from 23% to 35%.

The fix was an improvement — but 35% positive still means the model is on the wrong side of the market 65% of the time.

### Why This Matters

This finding is not a failure. It is exactly the kind of signal a disciplined system produces before betting real money.

The postmortem identified eight specific gaps between what the model currently knows and what professional oddsmakers factor in:

| Gap | What's Missing | Expected Impact |
|---|---|---|
| Weather | Wind, temperature, humidity at outdoor parks | High — ~0.2–0.3 fewer runs of prediction error |
| Pre-season projections | FanGraphs Steamer/ZiPS player quality estimates | High — especially for early-season games |
| Pitcher arsenal quality | FanGraphs Stuff+ (a metric for "how good is this pitcher's stuff today") | Medium-high |
| Umpire tendencies | Some umpires call significantly more strikeouts than others | Medium |
| Home team calibration | The model consistently under-rates home teams | Medium |
| Hitter vs. pitcher splits | How specific matchups play out based on pitch mix | Medium |
| Injury/lineup status | Day-to-day roster news that the market prices immediately | Medium |
| Alpha tuning accuracy | A calculation setting was run on incomplete data | Low (process fix) |

The two highest-priority fixes heading into Phase 7: **weather features** (the data path already exists — ballpark GPS coordinates are already in the database) and **FanGraphs projections** (the market relies heavily on these in April and early May, when in-season rolling stats are based on only 5–15 games of history).

---

## Summary: What Phase 6 Delivered

| Component | Status | What It Does |
|---|---|---|
| Diamond Edge App (4 pages) | Complete | Full Streamlit application: Today's Picks, Market Comparison, EV & Kelly Sizer, Model Performance |
| Automated Pipeline (Task DAG) | Complete | Overnight ingestion and prediction writes happen without manual intervention |
| 2026 Prediction Backfill | Complete | 1,098 game predictions from the full 2026 season in the database |
| v0 Model Postmortem | Complete | 8-gap analysis, calibration fix applied, Phase 7 roadmap produced |
| consensus_win_prob Fix | Complete | Mean h2h edge improved from −0.036 to −0.017 |
| Model Retraining Cadence | Deferred to Phase 7 | Blocked intentionally — model quality must improve before retraining on more data adds value |

### The Honest State of the System

The application works. The automation works. The data flows from raw pitch-level tracking through feature engineering, model scoring, and a live browser interface — all without human intervention after the initial setup.

What does not yet work is the core prediction goal: the model is not finding edges the market has missed. The postmortem made that clear, identified why, and produced a concrete list of what to build next.

Phase 7 begins with that list. The goal is a model that, on average, identifies win probabilities meaningfully higher than what the market prices — the condition required for the rest of the system to have real value.

---

*This report covers Phase 6 work completed as of May 1, 2026. For context on the models the application displays, see the Phase 4 and Phase 5 non-technical reports. For the Phase 7 roadmap, see betting_ml/evaluation/postmortem_v0.md.*
