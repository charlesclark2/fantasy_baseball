# Epic 16: The "Momentum" Experiment — Does Recent Form Help Us Predict Games?

## What Epic 16 Was About

Most of our models look at a team's stats **as a single season-long average**. A team's offense is "good" or "bad" based on everything they've done all year. But baseball isn't static — teams get hot and cold, bullpens get worn down over a stretch, lineups change. A season average treats a team that's been red-hot for two weeks the same as one that's been slumping, as long as their year-to-date numbers match.

Epic 16 asked a simple question: **if we give the models a sense of each team's recent, in-season form — and update that sense after every single game — do they predict better?**

The technical name is "sequential Bayesian updating," but the intuition is just **momentum awareness**: a belief about each team that starts at a sensible baseline and then nudges up or down after every game they play, so the model always reflects where a team is *right now*, not just where they've been on average.

---

## How We Tested It (Fairly)

We built **10 new "form" inputs** — covering team offense, bullpen quality, win pace, lineup strength, and starting-pitcher quality — each one updated game-by-game through the season.

Then we ran a clean, head-to-head experiment for each of our three models:

- **Version A ("no-momentum"):** the model exactly as documented, *without* the new form inputs.
- **Version B ("momentum"):** the identical model *with* the 10 new form inputs added.

Everything else — the data, the training process, the evaluation — was kept identical, so the **only** difference between the two versions is the momentum inputs. We then judged them on a strict, four-part rubric:

1. **Is it informative?** (Does it beat a dumb baseline that just guesses the league average?)
2. **Is it trustworthy?** (When it says "70% chance," does that happen about 70% of the time? This is "calibration.")
3. **Does it beat the market?** (Can it out-predict the sportsbook's own price?)
4. **Does it find profitable spots?** (On the specific games where it would trigger a bet, does it make money?)

A model has to clear the meaningful bars — especially **beating the market** — to be worth betting.

---

## What We Found

### Run differential (the run-margin model): a small, genuine win ✅
The momentum version predicted game margins a touch better than the no-momentum version, and both were well-behaved. This is the model that feeds our who-wins estimate, so a cleaner version here ripples through. **We adopted it.** It's the one clear success of the experiment.

### Home win (the who-wins model): a wash, dressed up as a win ⚠️
This is the most instructive result. The momentum version did **not** get better at actually picking winners — the no-momentum version was slightly sharper. What the momentum version *did* do was become **better-calibrated**: its probability estimates are more trustworthy (when it says 60%, it's closer to truly meaning 60%).

So it's a genuine trade-off, not an upgrade: slightly worse at discrimination, better at honesty. Because well-calibrated probabilities matter for how this model will eventually be used, **we adopted the momentum version** — but this changes **nothing** about our betting. The home-win model is still in evaluation, not placing automated bets, and **neither version beats the market.**

(There's an important footnote to this result — see "The Plot Twist" below. Our first analysis got this one *wrong*, and we caught it.)

### Total runs (the over/under model): no help at all ❌
The momentum version was, if anything, slightly *worse*. This is now the **third independent time** we've confirmed that our totals model doesn't beat the market — first in earlier testing, then in a dedicated betting backtest, and now here. The 10 momentum inputs added nothing. **Totals stays paused.**

---

## The Bottom Line on Momentum

The momentum idea delivered a **modest real improvement to model quality** on one model, a **calibration-only trade-off** on another, and **nothing** on the third — and across all three, it **manufactured no edge over the betting market.**

That's a legitimate, useful result. Beating a modern sports-betting market is genuinely hard; the sportsbooks are sharp. Knowing that "recent form awareness" — a sensible, intuitive idea — doesn't crack it saves us from chasing it further and points us elsewhere.

---

## The Plot Twist: Why We Almost Got It Wrong

Here's the part worth dwelling on, because it's about trustworthiness, not models.

When we **first** ran this evaluation, the home-win momentum version looked like a **clear, across-the-board winner** — better on every measure. We were ready to call it a model upgrade.

Then we discovered that one of our data sources — bullpen-quality data — had **silently broken** a week earlier (see the companion data-reliability report). The "no-momentum" comparison version had been evaluated using that broken data, which **artificially weakened it** and made the momentum version look better than it really was.

So we did the disciplined thing: we **fixed the data, retrained both versions from scratch on clean data, and re-ran the entire evaluation.** On clean data, the result **flipped** — the no-momentum version was actually sharper, and the momentum version's only real advantage was calibration. The "clear upgrade" story evaporated.

**A less careful process would have promoted a model based on contaminated evidence and written down a conclusion that wasn't true.** Instead, every production decision from this work rests on clean, re-verified data. That's the real headline of Epic 16: not the momentum features, but the fact that our evaluation caught itself.

---

## Where Epic 16 Leaves Us

- **Run differential:** momentum version is live.
- **Home win:** momentum version adopted for its better calibration; still evaluation-only, no betting change.
- **Total runs:** unchanged and still paused.
- **The strategic read:** in-season momentum awareness improves our models slightly but is **not** a path to beating the market. The search for genuine betting edge continues elsewhere — and we now have a cleaner, better-monitored data foundation to conduct that search on.
