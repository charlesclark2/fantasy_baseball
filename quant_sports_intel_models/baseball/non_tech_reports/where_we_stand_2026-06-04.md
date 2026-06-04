# Where We Stand — System Snapshot (June 4, 2026)

A plain-language summary of what the baseball prediction system is doing right now, what changed this week, and what's next. No code, and every term is explained as we go. Two companion write-ups go deeper: **"The Momentum Experiment"** (`epic_16_non_tech.md`) and **"Two Data Outages, Both Fixed"** (`data_reliability_2026-06-04.md`).

---

## The 30-Second Version

This week we did three things:

1. **Tested a new idea** — giving the models a sense of each team's *recent in-season form* (think "momentum"), instead of treating the whole season as one flat average.
2. **Fixed two separate data outages** — one in our bullpen-quality data, one in our player-stats feed from FanGraphs — and added alarms so they can't silently break again.
3. **Re-ran our model evaluation honestly** after discovering the first outage had quietly contaminated the original results.

The headline finding: the new "momentum" idea **modestly improved one model and produced no way to beat the betting market.** The market remains hard to beat. The most valuable outcome wasn't a model improvement — it was **catching a data problem that would have led us to the wrong decision**, and redoing the analysis on clean data.

---

## What the System Actually Does

Every day, the system pulls in live game data — rosters, pitching matchups, weather, ballpark, betting odds — and runs three prediction models for each MLB game:

| Model | What it predicts | How it's used |
|---|---|---|
| **Run differential** | The likely margin (home runs minus away runs) | Feeds our moneyline (who-wins) estimate |
| **Home win** | The probability the home team wins | A who-wins probability, currently in evaluation |
| **Total runs** | Whether the game goes over/under the posted total | Over/under bets — **currently paused** |

It then compares each model's view to the sportsbook's price to decide whether there's a worthwhile bet.

---

## Are We Actually Betting These? (Honest answer: not automatically, yet)

The system is in an **evaluation-first posture**. It is *not* firing automated bets on these markets right now:

- **Total runs (over/under) is paused.** We've confirmed three separate ways that our totals model does not beat the market. Until that changes, the system places **no automated over/under bets**.
- **Home win / moneyline is in evaluation.** The model runs and logs its picks, but it is not authorized for automated betting.
- The genuinely profitable activity today is **human selection** — an experienced handicapper picking spots. The models support that process with information; they don't yet replace it.

**The health metric we watch is "CLV" (Closing Line Value)** — whether our picks land on the side the market *moves toward* before game time. Beating the closing line is the single best early sign that a model has real edge. On this front, our production picks are **positive** (they're beating the close), which is encouraging — but it's an early indicator over a modest number of games, not yet proven profit.

> If you looked at the dashboard's "Combined" P&L and it seemed alarming: that view mixes in the **paused** totals model and is hypothetical shadow accounting over small samples. The number that matters (CLV) is positive. See the dashboard's "Moneyline" tab for the cleaner picture.

---

## What Changed This Week

### 1. The "momentum" experiment (Epic 16)
We added 10 new inputs that track each team's and player's *recent form within the current season* and updates them game-by-game, rather than relying on a flat season-long average. We then retrained all three models with these inputs and rigorously compared them to the versions without.

**Result:**
- **Run differential** got a small but genuine improvement → **adopted**.
- **Home win** didn't get sharper at picking winners, but it became **better-calibrated** (its stated probabilities are more trustworthy) → we adopted it on those grounds, but **it changes nothing about our betting** (still evaluation-only).
- **Total runs** got no benefit (slightly worse) → **stays paused**.
- Across the board, the new inputs **did not create any edge over the market.**

Full story in `epic_16_non_tech.md`.

### 2. Two data outages — found and fixed
- A behind-the-scenes **bullpen-quality data job was never connected to the daily schedule**, so that data silently froze on May 28 — degrading both the live model and the new momentum features. We found it, recovered the data, connected the job properly, and made the data self-healing.
- Our **FanGraphs player-stats feed broke** when FanGraphs tightened its bot protection. We redesigned how we fetch it; it's verified working again.
- We added **freshness alarms** so a silent outage like these gets flagged the next day instead of going unnoticed.

Full story in `data_reliability_2026-06-04.md`.

### 3. Fantasy groundwork
We confirmed that our FanGraphs hitting-stats data is **not** used by the betting models — but it **will** matter for the upcoming **fantasy** features. So we've started treating it as a maintained, monitored data asset now, before the fantasy work begins, so the data is reliable when we need it.

---

## The Honest Takeaway

The "momentum" idea was a reasonable bet that didn't pay off in the way we hoped: it improved model quality at the margins but **did not find a way to beat the sportsbooks.** That's a normal and useful outcome — it tells us where *not* to keep digging.

The more important story is about **discipline**. Our first pass at evaluating the new models was quietly corrupted by the bullpen data outage, and it made one model look like a clear winner. We caught it, fixed the data, and re-ran the whole evaluation — which **reversed that conclusion**. A less careful process would have promoted a model based on contaminated evidence. Instead, the production decisions rest on clean data.

---

## Where Things Stand — Scorecard

| Area | Status |
|---|---|
| Run differential model | ✅ Upgraded (momentum version live) |
| Home win model | ⏳ Improved calibration; evaluation-only, no betting change |
| Total runs model | ⏸️ Paused — no market edge (confirmed 3×) |
| Automated betting | Evaluation-first; manual selection is the profitable process |
| Bullpen data pipeline | ✅ Recovered + permanently fixed + monitored |
| FanGraphs data feed | ✅ Redesigned + verified + monitored |
| Fantasy data readiness | 🟡 Groundwork started; full scope pending |

---

## What's Next (deliberately parked, not forgotten)

- **Fantasy data scope** — decide how much history/detail the fantasy features need, then backfill accordingly. The data is recoverable on demand, so there's no rush.
- **Moneyline activation** — revisit the home-win model for real betting only once we wire up live, game-by-game market prices and a non-trivial blend.
- **Totals** — stays paused until a model clears the bar of beating both a naive baseline *and* the market on recent live games.

The short version: **models are stable and honestly evaluated, the data pipeline is more reliable than it was a week ago, and the fantasy foundation is being laid.**
