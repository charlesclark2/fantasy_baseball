# The Totals Post-Mortem — Why We're Closing the Over/Under Model (June 11, 2026)

A plain-language account of everything we tried to make the **total runs (over/under)** model beat the
sportsbook, why each attempt failed, and the decision we've reached. No code, every term explained as we go.

---

## The 30-Second Version

Over the past several weeks we threw nine distinct, serious attempts at the over/under model — new math,
new signals, a new model family, and finally a completely different way of even *measuring* success. **Every
one reached the same conclusion: we cannot beat the market on totals.** Today we ran the cleanest test of all
and got the most decisive answer yet.

So we're making it official: **the totals model is closed for betting.** It stays in the product only as an
information display — and even there, the honest thing to show users is the *sportsbook's own number*, because
it's more accurate than ours. We're redirecting that effort to the head-to-head (who-wins) market, where the
math at least leaves the door open.

This is not a failure of execution. It's a disciplined, well-documented "no" — the kind that stops us from
pouring months into a dead end.

---

## What "Totals" Means and Why It's Hard

A **totals** (or **over/under**) bet is simply: will the two teams *combined* score more or fewer runs than
the number the sportsbook posts? If Bovada posts **8.5**, you bet whether the real total lands over or under.

Here's the crucial feature of this market: the sportsbook posts those bets at roughly **even odds** —
"-110 / -110," meaning you risk about $110 to win $100 on either side. **Even odds is the market telling you
it believes the posted number splits the outcome 50/50.** In other words, the posted line *is* the market's
best single guess at how many runs will score. To beat it, we don't just need a good guess — we need a guess
that is *systematically better than the sharpest guess in the building.*

---

## The Nine Attempts (and the Tenth Test)

We'll walk through these in plain terms. Each was a real, multi-day effort with a pre-committed pass/fail bar
set *before* we looked at results — so we couldn't move the goalposts.

### Attempt 1–2: The first Bayesian rebuild (Epics 16B & 17)

We rebuilt the totals model on a more principled statistical foundation (a "hierarchical Bayesian" model —
think of it as a model that shares information intelligently across teams and players instead of treating each
in isolation). This is where we discovered the first deep problem, which we nicknamed the **"Jensen floor."**

**The Jensen floor, explained simply:** the model was built using a piece of math (an exponential link) that,
as an unavoidable side effect, forced its predictions to always sit a little *high* — around 8.9 runs minimum —
no matter what the inputs said. It literally could not predict a low-scoring environment even when one was
happening. Imagine a thermometer that can't read below 70°F: useless on a cold day. That built-in floor sat
*above* the level we needed to hit to be competitive. **Verdict: fail (confirmations 1–7 accumulated here
across variants).**

### Attempt 3–5: A brand-new signal — sensing the season's "scoring weather" (Epic 27)

The leading theory for *why* we kept missing: the run-scoring environment **shifts during the season** (April
played cold, May warmer, etc.), and our model was too slow to notice. So we built a dedicated new signal — a
"**scoring-environment tracker**" — using the same kind of smoothing math (a Kalman filter) that engineers use
to track a moving target with noisy radar. It was specifically designed to detect these shifts faster than a
crude running average, *and it did* — it tracked the season's swings beautifully and with low noise.

Then we fed it into the model (Story 27.3, **the official re-open gate**) and... **it added essentially
nothing.** The model's prediction barely moved. The signal was real, but the model couldn't convert it into a
better bet. **Verdict: fail — the 8th independent confirmation.** This one stung, because it was the
purpose-built fix for the leading theory.

### Attempt 6: A completely different model family (Story 10.10)

Every attempt so far used that same exponential math with the built-in "Jensen floor." So we asked: what if we
remove it entirely and use a totally different kind of model (a "quantile" model with no floor)? **This worked
exactly as hoped on the narrow question** — the floor vanished, and for the first time the model could predict
a low-scoring environment and land near the real average. **We proved the floor was a genuine artifact of the
old math, not a fact about baseball.**

But proving the floor was removable just exposed the deeper truth: **even with the floor gone, the model still
couldn't beat the market or even a coin flip on which side of the line the game would land.** Removing the
obstacle revealed there was no treasure behind it. **Verdict: fail — the 9th confirmation, and the first one
using an entirely different model family.**

### The Tenth Test: changing the question itself (Epic 29)

At this point we stepped back and challenged our own yardstick. We'd always measured success as "did we pick the
right side of the line?" But since the line sits at even odds, maybe the fairer question is simpler and more
fundamental: **how close does our predicted total get to the actual runs scored — compared to the sportsbook's
number?** This is a measure we had, surprisingly, never run head-to-head.

So we ran it on this season's games. The result was the most clarifying number in the whole investigation:

| Who's predicting the total | Typical miss vs. reality |
|---|---|
| **The Bovada line** | **within ~1.5 runs** |
| Our model | within ~2.9 runs |
| A dumb "season average" baseline | within ~3.2 runs |

The sportsbook's number is **roughly twice as accurate** as our model at predicting the actual runs in a game.
Our model is barely better than just guessing the season average every time.

And here's the subtle, important part: our model's predictions are **correctly centered on average** — it's
not biased high or low overall anymore. The problem is purely that, *game to game*, it's much noisier than the
market. **The market isn't beating us because it's less biased; it's beating us because it knows something about
each individual game that our data doesn't capture.** That's an *information gap*, and it's the hardest kind of
gap to close — you can't fix it with better math or recalibration. You'd need a genuinely new source of insight
about individual games that the sharpest bettors in the world don't already have.

---

## So What Do We Actually Conclude?

**The market is simply better-informed than we are on totals, game by game, and no amount of model engineering
has changed that across ten distinct attempts.** Three things follow:

1. **No automated over/under betting.** This was already the case (the model has been paused for weeks); now it's
   a settled, documented decision rather than a "for now."
2. **In the product, show the sportsbook's number, not ours.** If we want to display a projected total to a user,
   the most accurate number available is the market line itself. Our model doesn't improve on it.
3. **Even "just wait for more data" is now doubtful.** Our last fallback plan was to revisit totals in October
   with a full season of data. But that plan was designed to fix a *level* problem (predicting too high), and
   we've now shown the real problem is *game-to-game noise* — which more data won't fix. We're not banking on it.

---

## Was This a Waste? (No — here's the value created)

Two things worth being clear about:

- **The work wasn't thrown away.** The "scoring-environment tracker" and a new defensive-quality signal we built
  along the way are wired into the **head-to-head** model, where they may still help. And the data-pipeline
  speedups and monitoring we added are permanent infrastructure wins.
- **This is exactly how good research is supposed to end.** We set hard pass/fail bars in advance, tested
  rigorously on clean data, and let the evidence make the call — ten times. The alternative (chasing totals for
  another quarter on hope) would have cost real time and money. Knowing precisely where *not* to dig is itself a
  valuable result.

---

## Totals Scorecard

| What we tried | Outcome |
|---|---|
| Bayesian rebuild (Epics 16B/17) | ❌ Discovered the built-in "Jensen floor" forcing high predictions |
| Scoring-environment tracker (Epic 27) | ❌ Great signal, but the model couldn't use it (8th confirmation) |
| New model family, no floor (Story 10.10) | ❌ Floor removed & proven artificial — but still no edge (9th) |
| Change the yardstick to accuracy (Epic 29) | ❌ Market is ~2× more accurate per game; an information gap |
| **Overall totals-for-betting verdict** | **🔴 Closed — product shows the market line, not our model** |

---

## What's Next: Redirecting to Head-to-Head

We're moving the effort to the **head-to-head (who-wins / moneyline)** market. The reason is concrete, not just
optimism: the *specific mathematical trap* that doomed totals — that "Jensen floor" — **does not exist** in the
who-wins math. We've confirmed the who-wins models converge cleanly where totals structurally couldn't.

Honesty requires a caveat: head-to-head has had its *own* string of "no edge yet" findings, so this is not a
guaranteed win — it's the market where the door is still genuinely open. The next phase focuses there, plus on a
related idea (tracking the *sharp* money's line movements) that doesn't require us to out-predict the market
outright — only to follow the smart money's signal. More on that in the head-to-head write-up to come.

**The one-line summary: totals is an honest, well-earned dead end; we're putting our energy where the math still
gives us a chance.**
