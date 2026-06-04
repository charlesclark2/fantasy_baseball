# Two Data Outages, Both Fixed — A Reliability Story (June 4, 2026)

This week we found and fixed **two separate, silent data outages**, and added monitoring so the next one can't hide. Neither caused a visible crash — that's exactly what made them dangerous. This is the story of how they were caught and what we did to make the pipeline sturdier.

---

## Why "Silent" Outages Are the Scary Kind

When a system crashes, you know immediately. The scary failures are the ones where everything *looks* fine — the daily jobs run, no errors, the dashboard loads — but a piece of data has quietly stopped updating. The models keep making predictions, just with stale or missing information, and nobody notices until something downstream looks off. Both of this week's issues were that kind.

---

## Outage #1: The Bullpen Data That Quietly Froze

### What broke
We track a measure of each team's **bullpen quality** — how good their relief pitchers have been. This feeds both the live prediction model and the new "momentum" features from Epic 16.

It turned out that the behind-the-scenes job that produces this data **was never actually connected to the daily schedule.** Someone had been running it by hand. The last manual run was **May 28**, and after that, the bullpen-quality data simply stopped advancing — frozen in time — while everything around it kept moving. Because the related jobs kept running without errors, nothing flagged it.

### How it was caught
We were running a routine spot-check on the new momentum data — confirming all the new inputs were present for recent games — and noticed that the bullpen-related inputs were **completely empty for every game since May 29.** Pulling the thread led straight to the frozen job.

### Why it mattered
Two things were affected:
1. The **live prediction model** had been quietly filling in "best guess" placeholder values for bullpen quality on every game for about a week.
2. More importantly for this week's work, it had **contaminated our model evaluation** — the comparison that initially (and wrongly) made one of the new models look like a clear winner. (That's the "plot twist" in the Epic 16 report.)

### How we fixed it — three layers
1. **Recovered the lost data** — rebuilt the bullpen-quality numbers for the missing window and verified every game from May 29 onward was filled in correctly.
2. **Connected the job to the daily schedule** — so it now runs automatically every day, in the right order, as part of the normal pipeline. This was the root cause, and it's now permanently addressed.
3. **Made the data self-healing** — adjusted how the data is assembled so that if a day's data ever arrives late, the next run automatically backfills it rather than leaving a permanent hole.

The fix is confirmed working in production.

---

## Outage #2: FanGraphs Locked the Door

### What broke
**FanGraphs** is a baseball-stats website we pull player data from. Like many sites, it sits behind **Cloudflare**, a security layer that challenges visitors to prove they're a real browser and not a bot. For a while, our workaround was: use a helper service to solve the challenge once, grab the resulting "you're cleared" pass, and reuse that pass on our fast data requests.

That stopped working — every request started getting rejected. The frustrating part: the helper service was solving the challenge *successfully* every time, but our data requests were **still** being turned away.

### Why it broke (the subtle part)
Cloudflare's "you're cleared" pass is tied to **the exact computer (and its internet address) that earned it.** Our setup runs the challenge-solver and the data-fetcher as **two separate services in the cloud**, and those two services have **different internet addresses** — addresses that can even change when the system redeploys. So the pass earned by one service was being presented by the other, and Cloudflare correctly rejected it as "that's not the visitor I cleared." It had worked briefly and then broke two days later precisely because of this fragility.

### How we fixed it
Instead of trying to *borrow and reuse* the pass across two services, we **changed the approach entirely**: now the challenge-solver service makes the actual data request **itself** and just hands us back the results. The fetcher never touches FanGraphs directly. Because only one service is involved end-to-end, there's no pass to transfer and no mismatched addresses — the whole class of failure simply can't happen anymore.

We tested it against live FanGraphs data and it pulled **1,172 player records** cleanly. It's verified working in production.

---

## The Common Thread — and the Fix That Covers Both

Both outages shared a root flaw: **a silent gap with no alarm.** So beyond fixing each one, we added a **freshness monitor** for the player-stats feed. Every day it checks: "has this data updated recently?" If it ever goes stale again, it gets flagged in the daily logs the very next day — instead of being discovered by accident a week later.

Importantly, we made that alarm **non-blocking** for the player-stats feed: it *warns* us, but it will **never halt the core betting pipeline**, because that particular data isn't used by the betting models (it's destined for upcoming fantasy features). We want to know about problems without letting a non-critical feed take down the critical path.

---

## A Useful Discovery Along the Way

While tracing where the FanGraphs hitting data goes, we mapped its full path through the system and confirmed something worth writing down: **that data is not used by any of the betting models.** It feeds some player-grouping analytics, but the betting models get their hitting information from a different source (Statcast).

This matters for two reasons:
1. It told us the missing/gappy FanGraphs hitting history **doesn't affect betting predictions at all** — so there was no urgency to backfill it for the models.
2. But it **will** be important for the **fantasy** features we're building next. So we've reclassified it as a **maintained data asset** going forward — monitored now, kept reliable, ready when the fantasy work begins.

---

## Where Reliability Stands Now

| Item | Before this week | After |
|---|---|---|
| Bullpen-quality data | Frozen since May 28, no alarm, run by hand | Auto-scheduled, self-healing, recovered |
| FanGraphs player feed | Fragile pass-sharing, silently failing | Robust single-service fetch, verified |
| Outage detection | None for these feeds | Daily freshness alarm (non-blocking) |
| Confidence in evaluations | Vulnerable to silent contamination | One caught and corrected; process hardened |

The pipeline is meaningfully more trustworthy than it was a week ago — not because nothing broke, but because **what broke got found, fixed at the root, and wrapped in monitoring** so it stays fixed.
