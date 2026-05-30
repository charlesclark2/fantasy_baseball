# Epics 7 and 7A: Player Archetypes and the Matchup Intelligence Layer

## What These Epics Were About

Before Epics 7 and 7A, the prediction models had no concept of *what kind of player* was in a lineup. They knew statistics — on-base percentage, strikeout rate, hard-hit percentage — but they couldn't recognize that two players with similar statistics might belong to fundamentally different player types, and that those types interact with opposing pitcher types in predictable, recurring ways.

Epic 7 built a **player classification system**: ten stable archetypes (five for batters, five for pitchers) that describe recurring player profiles across all of modern baseball history. Epic 7A built a **real-time uncertainty layer** on top of those archetypes: rather than forcing every player into a single hard label, it computes a probability distribution over all archetype classes at every point in the season — especially important for rookies, early-season data-thin players, and players whose approach has visibly changed.

Together, these two epics form the foundation that Epic 8 (the matchup model) will build on.

---

## Epic 7 — Archetype Clustering

### The Problem Being Solved

Individual player matchup history is too thin to be useful at the individual level. Even across a full season, a specific batter might face a specific pitcher only eight to twelve times. You cannot build a reliable statistical signal from eight plate appearances.

But *types* of players face *types* of pitchers thousands of times per season. If you group 50 similar power-pull hitters together and 60 similar strikeout specialists together, you suddenly have tens of thousands of plate appearances to learn from — a signal stable enough to actually trust.

Epic 7 built that grouping system.

### How Archetypes Were Assigned

For each player in each season, we computed a statistical profile: batters on six dimensions (strikeout rate, walk rate, isolated power, pull percentage, hard-hit rate, groundball rate), pitchers on similar dimensions (strikeout rate, walk rate, velocity, groundball rate, pitch mix). We then ran a machine learning clustering algorithm (K-Means) across all qualified seasons simultaneously — not season by season, but pooled — so the clusters have a consistent meaning across years. A contact hitter in 2018 belongs to the same archetype as a contact hitter in 2024.

This was a deliberate design choice. Season-by-season clustering produces cluster labels that drift and flip between years — what was "cluster 2" in 2021 might become "cluster 4" in 2022, breaking the historical comparisons the matchup model depends on. Cross-season pooling fixes the labels across time.

### The Ten Archetypes

**Five batter archetypes:**

| Archetype | What It Means |
|---|---|
| Power Pull | High power, pull-heavy swing, elevated strikeout rate — the prototypical slugger |
| Patient OBP | High walk rate, low strikeout rate, gets on base by working counts |
| Contact Spray | Low strikeout rate, hits to all fields, consistent contact hitter |
| High Whiff | Elevated strikeout rate without the power to justify it — free-swinger |
| Groundball Speed | Produces groundballs, relies on speed — contact-over-power profile |

**Five pitcher archetypes:**

| Archetype | What It Means |
|---|---|
| Power Swing-and-Miss | High velocity, high strikeout rate — the classic power arm |
| Multi-Pitch Mix | Diverse arsenal, attacks batters from multiple angles |
| Changeup Deceptive | Offspeed-heavy, exploits speed differential and tunneling |
| Contact Sinker-Ball | High groundball rate, sinker-dependent, induces weak contact |
| Soft Command | Low velocity, command-dependent, finesse over power |

### Historical Coverage

After the clustering was complete, we back-filled archetype labels for every qualified player for every season from 2015 through the current 2026 season. That gives eleven years of archetype history — enough for each of the 25 batter-archetype × pitcher-archetype combinations to accumulate a meaningful sample of historical plate appearances.

### The 25-Cell Matchup Table

With archetypes defined, we built a **population-level matchup table**: for each of the 25 pairings, what does historical performance look like? How does the typical Power Pull hitter do against the typical Power Swing-and-Miss pitcher, on a rolling 180-day window? This table — `mart_batter_archetype_vs_pitcher_cluster` — is the core lookup that the matchup model (Epic 8) will draw from.

The table includes a shrinkage step: thin cells (combinations with limited historical data) have their estimates pulled toward the league average rather than trusted at face value. Pairings with more data are trusted more; pairings with less data default toward neutral.

### Pre-Game Feature Integration

Archetype labels are now available as pre-game features. For every game on the schedule, the system knows:

- **Lineup composition by archetype:** How many Power Pull hitters does each side have? How many High Whiff hitters? How many Contact Spray players? This gives the model an immediate read on a lineup's overall character — is it a power-heavy lineup or a contact-heavy one?
- **Opposing starter archetype:** Is the home team's ace a Power Swing-and-Miss pitcher or a Soft Command finesse arm? That determines which part of the matchup table is relevant.

This information is now flowing into `feature_pregame_game_features`, the consolidated pre-game feature table that all prediction models draw from.

---

## Epic 7A — Dirichlet Cold-Start

### The Problem Being Solved

The archetype system described above assigns a single, stable label per player per season — but that label is computed using the full season's data. During the season itself, especially early in the year, we often have limited evidence. A player who is 15 games into his rookie season technically has no archetype yet. A veteran coming off an injury might not have enough at-bats for the clustering algorithm to assign him confidently.

Forcing a hard label in these situations is dishonest. We're pretending to know something we don't. And downstream, the matchup model would inherit that false confidence — treating a small-sample archetype assignment the same as a 600-PA veteran's well-established profile.

Epic 7A built a proper uncertainty model.

### How It Works: Probability Distributions Over Archetypes

Instead of hard labels, Epic 7A computes a **probability vector** over all five archetypes for every active player on every game date. A veteran power hitter at his peak might look like:

```
power_pull:      0.87
patient_obp:     0.06
contact_spray:   0.04
high_whiff:      0.02
groundball_speed: 0.01
```

That player's identity is essentially certain. Contrast with a 22-year-old rookie in April:

```
power_pull:      0.38
contact_spray:   0.29
patient_obp:     0.18
high_whiff:      0.10
groundball_speed: 0.05
```

Genuinely uncertain. The model knows it's uncertain. The downstream matchup calculations can reflect that uncertainty rather than hiding it.

### The Bayesian Foundation

The uncertainty model uses a **Dirichlet prior** — the standard probability tool for multi-class membership uncertainty. The prior encodes what we know before we've seen any current-season data for a player:

- **Young players (under 24):** Wide prior, high uncertainty. They haven't established a stable profile yet.
- **Mid-career players (24–27):** Moderate prior. Most players in this range have a recognizable profile, but there's still meaningful variation.
- **Veterans (28+):** Strong prior anchored to their confirmed prior-season archetype. A player who was a contact hitter last year, with 400+ plate appearances to prove it, is very likely still a contact hitter this year.

As a player accumulates plate appearances in the current season, the prior updates. Early in April, the prior dominates. By September for an established player, their actual current-year performance dominates. For a rookie late in September who only has 80 PA, the prior still plays a meaningful role.

### What Gets Stored

For every active player on every game date, the system stores:

- **The full probability vector** over all five archetypes (the JSON object above)
- **The most likely archetype** (the argmax, equivalent to a soft "best guess" label)
- **Assignment confidence** — the maximum probability in the vector. 0.87 is high confidence; 0.38 is low.
- **Cluster entropy** — a single number measuring overall uncertainty. Zero means complete certainty; high entropy means the probabilities are spread across multiple archetypes.
- **Data source tag** — whether the assignment came from the prior alone (no current-season data yet), partial current-season data, or a full empirical update.

### Verification Against Hard Labels

As a sanity check, we compared the soft assignment's "best guess" (argmax) to the hard end-of-season labels from Epic 7 for all qualified players with 200+ plate appearances. Agreement rate: **82.8%**.

The 17% disagreement is intentional and correct. Some of those players changed their profile mid-season — a veteran who started pulling the ball less, or a pitcher who added a new pitch type. The Bayesian model picks up on the current-season evidence and starts shifting away from the prior-year label; the hard end-of-season label gets there eventually. The soft model is just earlier.

### The Scale of the Backfill

To populate the historical matchup table with soft-weighted data (described below), we ran the posterior computation for every active player on every game date from 2021 through the current 2026 season. That produced **approximately 420,000 player-date records**, each with a full probability vector. This backfill is complete.

| Season | Batter Records | Pitcher Records | Total |
|---|---|---|---|
| 2021 | 50,590 | 21,530 | 72,120 |
| 2022 | 47,308 | 20,861 | 68,169 |
| 2023 | 48,237 | 20,621 | 68,858 |
| 2024 | 48,334 | 20,683 | 69,017 |
| 2025 | 48,401 | 20,862 | 69,263 |
| 2026 (partial) | 522 | 646 | 1,168 |

### Soft-Weighted Matchup History

The final piece of Epic 7A was rewriting the 25-cell matchup table to use soft weights rather than hard labels.

Under the old system, when a plate appearance occurred, it was added to exactly one of the 25 cells — whichever batter archetype and pitcher archetype the two players had been assigned. The assignment was binary: all or nothing.

Under the new system, each plate appearance contributes fractionally to all 25 cells, weighted by the product of the batter's probability of being each archetype and the pitcher's probability of being each archetype. A plate appearance between a player who is 87% likely to be a Power Pull hitter and a pitcher who is 92% likely to be a Power Swing-and-Miss specialist will put most of its weight in the Power Pull vs. Power Swing-and-Miss cell — but a small fraction goes into each of the other 24 cells as well, proportional to the residual uncertainty.

This means the matchup table now carries uncertainty about player classification all the way through into the historical estimates. Thin cells get thinner (their weights are diluted by uncertainty); well-established matchup types get firmer estimates.

---

## What Epics 7 and 7A Mean Going Forward

Before these epics, the prediction models saw lineup construction as a list of individual players with individual statistics. After these epics, the models can see a lineup as a *composition* — and recognize patterns like "this lineup is unusually heavy on High Whiff hitters facing a Power Swing-and-Miss starter, which historically has been a tough matchup" — without needing to have seen this specific starting pitcher face these specific batters.

The matchup intelligence flows forward in two directions:

1. **Into the pre-game feature tables** (available immediately): archetype distribution per lineup side, opposing starter archetype, and the population-level expected wOBA for each batter slot's archetype matchup. These are now live features in the prediction pipeline.

2. **Into Epic 8 (the matchup model, next)**: The 25-cell interaction matrix — how well does archetype X historically do against archetype Y, after shrinkage for thin cells? — is the training signal for the dedicated matchup model. Epic 8 will estimate hierarchical interaction effects and generate a pre-game matchup quality score.

The uncertainty layer from Epic 7A is specifically designed to flow through Epic 8 without getting dropped. A rookie's uncertain archetype assignment doesn't disappear — it becomes a measurable matchup uncertainty score that the model can treat differently from a matchup between two well-established veterans.

---

*Epic 7 completed 2026-05-30. Epic 7A completed 2026-05-30. Both are prerequisites for Epic 8 (Matchup Model).*
