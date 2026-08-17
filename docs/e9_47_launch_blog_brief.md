# E9.47-prep — Launch-blog findings discovery + ChatGPT brief

**Date:** 2026-08-16 · **Branch:** `e9-47-blog-brief` (worktree off `dev`) · **Status:** research/content, no code changed.
`best_alpha = 0` — this document produces the *prompt* for ChatGPT, not the published post. Every
number in it is honest-analytics-screened (see §5), but the eventual blog draft still needs a human
honesty pass before it goes into `frontend/app/admin/blog/`.

Context: real fantasy subscriptions went live 2026-08-16 (today) — `sk_live_` Stripe, live Prices,
verified end-to-end with a real charge (see `docs/e9_8_p2_stripe_golive.md`). This is the launch this
blog post announces.

---

## 1. The candidate findings, ranked

Ranked by (interesting × defensible × on-brand-honest). Each entry names its exact numbers, its
reproduce path, and its honest caveat, per the story's instructions.

### 🥇 #1 — THE SELF-CORRECTION STORY (recommended primary hook)

**The finding:** The day before launch, we audited our own board against thirteen seasons of actual
outcomes (2013–2025) and found it was running systematically low — not by a little, and not evenly
across positions. We found the *mechanism* (it was the per-game rate, not games-missed), fixed it,
re-ran the validation, and republished the board and the public track record in the open, the same
week we're launching.

**The exact numbers** (from `quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_tr2_level_recalibration_b.{md,json}`, harness `run_nf_tr2_level.py --window 5`):
- On the top-156-per-season tier, our pooled bias moved from **−12.85** points/player to **+1.41**
  (near-zero) — validated out-of-fold across 13 seasons (2013–2025), not just in-sample.
- Decomposition (the finding within the finding): the miss was **the per-game rate, not
  availability** — the games-missed part of the error was actually +3.7 (we were slightly
  *over*-crediting playing time); the rate part was −16.6. Per-position rate ratios: RB 0.864, WR
  0.848, TE 0.837, QB 0.985 — i.e., before the fix, a rostered running back's *per-game* production
  was priced at roughly 86% of what he actually produced, once he was on the field.
- Validation: CRPS improved 49.92 → 49.34 pooled; pre-registered against two matched foils (a
  per-position affine fit and a no-op); DSR 0.9995 on the declared 3-arm field; p = 0.0002; the
  within-position rank order did not move (Spearman 1.0 every fold) — this was a **level** fix, not
  a re-ranking.
- Consequence on the 2026 board: RB mean points +24.8%, WR +10.0%, TE +11.2%, QB −7.1% — running
  backs move up the board relative to quarterbacks as a direct, disclosed result.
- Deployed 2026-08-15 (one day before launch): board rebuilt, published, public track record
  re-exported, `run_interval_revalidation` re-run green.

**Why it's the strongest hook:** it is the single cleanest demonstration of the actual
differentiator (transparency + calibration, not "we're right") and nobody else can tell this story —
it's a real, dated, receipts-backed narrative arc: build → audit → find a real defect in our own
model → explain the mechanism → fix it → republish. It required zero market comparison and carries
zero win/edge language by construction.

**Caveat for the writer:** this is a **level** correction (how big the number is), not a ranking
change claim — do not conflate "our numbers were 15% low at RB" with "our rankings were wrong." The
order was validated unchanged (see the rank-identity numbers above).

---

### 🥈 #2 — THE DISAGREEMENT HOOK (best pure "click" hook; forward-looking, zero accuracy claim)

**The finding:** Where the 2026 board disagrees most with the consensus, right now, before a single
game has been played. Framed exactly the way `DISAGREEMENT_HOOK` in the codebase already frames it:
"see the players we rank furthest from where the crowd is drafting them — and what is driving the
gap." This is explicitly **not** an accuracy claim (2026 has no realized outcomes yet) — it's
content: real players, real gaps, "here's what we see."

**The exact numbers** (from `ablation_results/nf_d3_benchmark_scorecard.md` §4 "Forward view — 2026"; z-score gap = our standardized value minus the benchmark's):
- We're notably **higher** than the market on: Christian McCaffrey (vs ADP +1.37, vs ECR +1.70, vs
  ESPN +2.42, vs Sleeper +1.33 — consistently higher across every benchmark), Zach Ertz (+1.79 ECR,
  +1.62 Sleeper, +2.98 ESPN), Ja'Marr Chase (+1.64 ECR, +2.30 ESPN), Alvin Kamara (+1.37 ADP).
- We're notably **lower** than the market on: Travis Hunter (−1.67 ECR, −1.15 Sleeper, −2.13 ESPN,
  −1.18 ESPN-proj — consistently lower across every benchmark), Joe Burrow (−2.35 ADP), Luther
  Burden III (−1.59 ADP, −1.27 ECR, −1.22 Sleeper), Bhayshul Tuten (−1.42 ADP, −1.17 Sleeper, −1.14
  ESPN-proj).

**Caveat for the writer, and it's load-bearing:** the source file's own text is explicit — "this
section makes NO 'we beat X' claim — it only shows how aligned our board is with each system, and
our most contrarian picks." Frame every one of these as "here's what our model sees, and the season
will tell us if it's right" — never as "we're right about McCaffrey." Also: our own architecture note
matters here — a second model blends the market's own consensus into our ORDER at most positions, so
even our disagreement is not a fully independent read on the market (see the `ARCHITECTURE_CAVEAT`
constant, quoted verbatim in §4 of the FACTS block below). That nuance should appear if this angle is
used as more than a two-line teaser.

---

### 🥉 #3 — AN ORIGINAL, FRESH-COMPUTED nflverse FINDING: RB and WR are equally volatile

**The finding:** the industry-standard fantasy-football trope is "running backs are radioactive,
wide receivers are safe" — draft a top-tier RB and you're gambling on his role surviving; draft a
top-tier WR and the role is stickier. **This is measurably not true at the top of the position.**

**Computed fresh for this brief**, directly from nflverse's own public data (not from any Credence
model or internal artifact) — reproducible by anyone with the query below:

- Source: `player_stats_season_<year>.parquet`, seasons 2015–2024 (10 seasons, 9 year-over-year
  transitions), from `https://github.com/nflverse/nflverse-data/releases/download/player_stats/`.
  Regular season only (`season_type = 'REG'`), ≥8 games played.
- Question: if a player finished **top-24 at his position** in PPR fantasy points in season N, what's
  the chance he's *also* top-24 at his position in season N+1?
- **Result (n = 216 top-24 player-seasons per position, matched threshold across positions):**

  | Position | Repeat top-24 rate (year N → N+1) |
  |---|---|
  | QB | **71.3%** |
  | TE | **60.2%** |
  | RB | **53.7%** |
  | WR | **52.8%** |

- **RB and WR are statistically indistinguishable** (53.7% vs 52.8%, on n=216 each — well inside
  noise). QBs are meaningfully stickier (71.3%), which matches conventional wisdom; TEs sit in
  between. The RB/WR gap the industry talks about isn't showing up here at the top-24 level.
- Reproduce query (DuckDB, no auth/credentials needed — pure public HTTPS parquet):

  ```sql
  -- pull player_stats_season_2015.parquet .. player_stats_season_2024.parquet, REG season only
  -- rank each position by fantasy_points_ppr within season, keep top-24, join player_id to
  -- (season+1), and compute the retention rate of a top-24 finish. Full query in this repo's
  -- session log; ~15 lines of SQL, single source table, no joins beyond the year-over-year
  -- self-join on player_id.
  ```

**Why it's useful, and where it's weaker than #1/#2:** it's genuinely interesting, entirely
independent of our own model (so zero denylist risk), and it sets up our own "we ship a range, not a
fake-precise number" pitch perfectly — a ~53% repeat rate at the top of RB/WR is exactly why a single
point projection is dishonest and a range is the right answer. It's weaker as a *launch* hook
specifically because it isn't about Credence at all until the pivot sentence — it's a "give the
reader something useful first" opener, which works well as a cold-open paragraph but shouldn't be the
whole post.

**Caveat for the writer:** this is a fact about **fantasy football**, not about Credence's own
model — do not let it drift into implying our projections "solve" this (they don't eliminate the
volatility; they price it into the range, which is a different and honest claim).

---

### #4 — THE CURRENT HONEST CLAIM ITSELF, as a hook ("the self-verifying moat")

This is really Task 2's deliverable (full detail in §2 below), but it doubles as a fourth candidate
hook: *"Every season since 2019, we grade our own board against what actually happened — in the
open, wins and losses both, and you can go look right now."* This is the "publish the methodology"
differentiator. It's the most abstract of the four (no single startling number) but it's the one
that's hardest for a competitor to copy credibly, because doing it requires actually being willing to
publish a loss.

---

### Recommendation

**Primary hook: #1 (the self-correction story).** It's the most defensible, the most on-brand, and
the most ownable narrative for a *launch* post specifically (a launch post is about why to trust a
brand-new product, and nothing demonstrates that better than "we audit ourselves and show our work").
**Backups, in order: #2 (disagreement/forward board), #4 (the track-record moat as the closing CTA —
it should appear regardless of which hook leads, as the "how we hold ourselves accountable"
section), #3 (the nflverse fact as a cold-open scene-setter if a punchier opening paragraph is
wanted).**

---

## 2. The current honest claim (Task 2) — read from the LIVE artifacts, not the stale card copy

⚠️ **Correction to the story's own framing:** the story prompt said "we beat MFL, trail
Sleeper/ECR/ESPN on ADP correlation; it's mixed" — that's directionally right but the FFC number (the
one that's actually the **shipped public headline**) is more careful than "beat" implies, and the MFL
number needs a depth caveat or it overstates. Below is the precise, current reading.

**Source artifacts (both regenerated 2026-08-16, i.e. reflect the NF-TR2b-recalibrated board that
shipped 2026-08-15 — confirmed via the A4 reproduction check inside the NF-D17 memo, which re-derives
the shipped scorecard's own numbers and checks they match):**
- `quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_d3_benchmark_scorecard_nf1_5.md`
  (the scorecard behind the served NF1.5 board)
- `quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_d17_track_record_population.md`
  (the pre-registered population-sensitivity check on the headline number)
- Generator: `export_track_record_json.py::build_claim` (reads both of the above and raises rather
  than publishing if they don't reconcile)

**The headline (FFC — Fantasy Football Calculator real-draft ADP, the shipped public comparison):**
- 7 seasons (2019–2025), ~167 ranked players/season (range 140–193)
- Our ρ 0.512 vs FFC's 0.493 → **Δρ +0.018**
- 90% paired bootstrap CI: **[−0.007, +0.044] — includes zero.** This is a wash we cannot claim as a
  real edge. The pre-registered decision rule (NF-D17) confirms this is the correct number to publish
  and explicitly does **not** license raising it.
- By position (verdict band ±0.005): QB +0.030 (ahead), WR +0.027 (ahead), TE +0.026 (ahead), RB
  −0.010 (behind, though small in absolute terms).

**Other benchmarks, same population/method, all CONTEXT not part of the shipped headline:**
- **MFL** (a second, deeper real-draft ADP crowd): Δρ **+0.169**, CI [+0.133, +0.200] — excludes
  zero, a real gap on MFL's own ~264-player pool. **But this is a depth effect, not a "we're smarter
  than MFL's crowd" effect** — restricted to FFC's shallower ~167-player population, MFL's own edge
  collapses to +0.016, CI [−0.013, +0.049] (also includes zero). The honest statement is: a
  shallower draft crowd (FFC) holds up about as well as we do; a deeper one (MFL, ranking ~100 more
  players/season) degrades faster than we do deeper into the pool. That is NOT the same claim as
  "we beat MFL."
- **ECR** (FantasyPros expert consensus): Δρ **−0.013**, CI [−0.021, −0.005] — excludes zero, we
  trail, real but small.
- **Sleeper** (staff rankings): Δρ **−0.113**, CI [−0.129, −0.098] — excludes zero, we trail,
  meaningfully.
- **ESPN**: Δρ **−0.040**, CI [−0.063, −0.018] — excludes zero, we trail.

**The one-sentence honest summary:** *against the real-money draft crowd we compare ourselves to
publicly, our order is statistically indistinguishable from the market's — a wash, not a win — and
we trail the two big staff-ranking products (Sleeper, ESPN) and FantasyPros' expert consensus by a
real but modest amount. Where we do show a clean, statistically real gap (MFL) it's explained by a
population-depth difference the data itself makes visible, not a "we're smarter" story.*

**Why this belongs in the blog at all, framed as the moat, not the claim:** per the codebase's own
established split (`fantasy-claim-copy.ts`, NF-TR1), the marketing surfaces do **not** lead with this
number — they link to it. The blog post should do the same: it can *describe* the existence of a
public, honest, includes-our-losses track record page as the differentiator, without reciting the
Δρ figures as the pitch. If the writer wants to quote a number anyway (blog posts can carry more
nuance than a banner), it must carry the full caveat above, every time.

---

## 3. The rollout (Task 3) — accurate, from shipped work

**Shipped and live as of 2026-08-16:**
- **Honest season-long point projections with an 80% range**, for every rostered-relevant NFL
  player — a range that widens or narrows depending on how much the model actually knows, not a
  fake-precise single number.
- **Projections re-scored for your league's actual settings** (half-PPR, full-PPR, superflex, custom
  bonuses, league size) — not converted from one generic scoring format, recomputed against yours.
  This is the `NF-C1` config layer; it's the engine underneath everything else.
- **A live-draft-aware draft optimizer** — VOR + positional-need + tier-break aware, usable pick by
  pick during a real draft, dogfooded on a real 2026 league. (Paid capability.)
- **One free personalized league, included with every free account** — import from Sleeper (live and
  verified end-to-end on a real 12-team league) or ESPN (compliant paste-based import), or enter a
  league by hand; see your own board re-scored for your real settings, with what changed and why.
- **Several leagues at once, plus a post-draft roster report** — value-over-replacement roster
  grading against your league's actual starter demand, a real free-agent pool once every roster in
  the league is imported, bye-week coverage, and injury-concentration — all against our own
  replacement levels, never a claim about what the other managers in the league will do. (Paid.)
- **A public, transparent track record** at `/fantasy/track-record` — every season since 2019,
  graded against what actually happened, one row per player, free, no account required, wins and
  losses both shown (see §2).
- **Pricing:** live now — the first 100 members lock in $10/month permanently; $20/month standard
  after that.

**Roadmap — ⚠️ needs a decision from the team before it goes in the post, see the flag below:**
- The story brief said "NCAAF 8/29, NFL ~9/9." That's **partly stale.** What's actually true, as of
  the current roadmap docs:
  - NCAAF's underlying **data pipeline** is ready for the season's ~8/29 kickoff (closing-line
    capture, pre-season roll-forward, the season-simulation model — all shipped and
    operator-enabled).
  - But **the NCAAF product/app surfaces are explicitly NOT committed to 8/29** — an operator
    decision on 2026-07-26 deliberately deferred the NCAAF app launch to "mid-season, after a
    model-refinement pass," on the stated principle that a better model matters more than hitting the
    date. Promising an NCAAF app for 8/29 in the blog would overstate what's actually planned.
  - NFL's own separate betting-market surfaces (game lines/props, distinct from the fantasy product
    this launch is about) target "ready by 9/9" (the NFL season opener) — that one does appear to be
    on track, but it's a different product than what this post announces.
  - **Recommendation:** don't hard-commit a specific NCAAF app date in the post. Safe framing: "more
    sports are coming this season" or, if a date is wanted, cite the season's kickoff (a fact) rather
    than implying our product ships that day (not yet a fact). Flag this for Charlie to confirm with
    the team before publishing either way.
- **Do NOT promise the weekly (in-season, week-to-week) product.** It's explicitly deploy-held —
  the codebase's own copy calls it "still in the lab." The current product is a season-long
  projection; don't imply a week-by-week start/sit tool exists yet.

---

## 4. Denylist screening notes (Task 4 prep)

Full denylist (union of `export_track_record_json._CLAIM_DENYLIST` and
`betting_ml/governance/gates._DEFAULT_CLAIM_DENYLIST`): *we beat, beat the market, beat consensus,
every position, all four, our edge, guaranteed, more accurate, beats the market, outperforms the
market, market-beating, profitable, edge over the market, beats adp, beat adp, beats ecr, beat ecr,
win your league, wins your league, sure thing, can't miss, risk-free, always right, never wrong.*

Both this memo and the ChatGPT brief in §5 were written to avoid every one of these phrases and their
close paraphrases (e.g. "we're smarter than," "we're right," "our numbers are better"). The brief
itself instructs ChatGPT with the same list verbatim, since ChatGPT has no access to the codebase's
guard tests.

---

## 5. THE CHATGPT BRIEF (the deliverable — copy everything between the lines into ChatGPT)

--- COPY BELOW THIS LINE ---

You are writing a launch blog post for **Credence**, a fantasy football analytics product that just
went live with paid subscriptions today. Read this entire brief before writing. It contains
everything you need — do not invent, estimate, or embellish any number. If you want to say something
you can't support from the FACTS block below, cut it instead.

## Who this is for

Fantasy football players — from casual redraft league managers to serious dynasty/keeper players —
who are currently in draft season (late Aug 2026) and have seen a hundred "our projections are the
best" posts before. This is also a soft, friends-and-family-adjacent launch: some readers will be
people who know the team personally. Write like you respect that they've heard hype before and are
tired of it.

## Voice

Honest, confident but humble, plainly written, data-driven without being dry. Not hype. No
exclamation-point energy. Think: a smart friend who built something and is telling you honestly what
it does and doesn't do yet — not a press release. Short sentences are fine. It's okay to say "we
don't know" or "this could just be noise" out loud; that's the brand, not a weakness to hide.

## The hook (lead with this)

**Primary: the self-correction story.** The day before today's launch, we ran a systematic audit of
our own season projections against thirteen years of actual outcomes — and found our numbers were
running low, in a specific, findable way. We tracked it down (it was how we priced a player's
per-game rate, not how often we expected him to play — a subtler bug than it sounds), fixed it,
re-validated it against thirteen years of held-out seasons, and republished the board and our public
track record in the open, in the same week we're launching. That's the story: not "our model is
right," but "here's what it means for us to catch ourselves being wrong, and show our work."

Tell it as a real narrative with a beginning, middle and end (build → audit → find the actual root
cause → fix → re-validate → publish), not as a bullet list of stats. Use the exact numbers from the
FACTS block below, but you don't need to use all of them — pick the ones that make the story clearest
to a non-technical reader (the "running backs were priced ~14% light on what they actually produced
per game" framing is probably the most vivid single number).

## Backup hooks (use if the primary doesn't fit, or as supporting color)

1. **The disagreement hook.** Show a handful of real 2026 players where our board and the market
   (ADP, expert rankings) disagree the most right now — before a single game has been played. Frame
   it explicitly as "here's what we see; we don't know if we're right yet, and the season will tell
   us." Never imply we ARE right. Use the FACTS block's disagreement examples.
2. **The accountability/track-record hook.** Every season since 2019, we've published our board
   against what actually happened — including the seasons and positions where we did *not* keep up
   with the market. That page (`/fantasy/track-record`) is public, free, and requires no account.
   Frame this as "you don't have to trust us — you can go check."
3. **A fantasy-football fact, as a cold open.** Everyone "knows" running backs are a riskier draft
   pick than wide receivers — but a fresh look at ten seasons of nflverse data (nine year-over-year
   comparisons) shows a top-24 RB and a top-24 WR repeat their tier the following year at almost
   exactly the same rate (see FACTS block). That's a good scene-setter for why a single-number
   projection is dishonest and a range is the more useful thing to ship — which is what we did.

## What we built (the rollout — state these plainly, no superlatives)

- Full-season point projections for every rostered-relevant player, each shipped with an 80%
  range — not a fake-precise single number.
- Projections re-scored for the reader's actual league (scoring format, roster shape, league size) —
  not a generic number relabeled.
- A live-draft-aware draft optimizer usable pick-by-pick during a real draft.
- One personalized league free with every account — import from Sleeper or ESPN, or enter one by
  hand.
- Several leagues at once, plus a post-draft roster report (how your draft grades against your
  league's own replacement level — not a claim about beating the other managers, since we don't hold
  their rosters).
- A public track record, graded every season since 2019, wins and losses shown, no account needed.
- Pricing: live today. First 100 members lock in $10/month permanently; $20/month after.

**Roadmap:** keep this vague and safe — "we're building out more sports this season" is fine.
**Do NOT** state a specific launch date for an NCAAF (college football) app — that has been
deliberately deferred internally and is not confirmed. **Do NOT** promise a week-to-week / in-season
start-sit tool — that does not exist yet.

## How we hold ourselves accountable (this section is required — it's the differentiator)

State plainly, using the exact FACTS block numbers: against the real-draft crowd we publicly compare
ourselves to, our order is *not distinguishable from the market's* over the last 7 seasons — a wash,
not a win. We trail two staff-ranking products and an expert-consensus product by a real, modest
amount. We do show one clean, real (not-noise) statistical gap in our favor, against a different
(deeper) draft-market pool, and we explain honestly why that shows up (it's about how deep into the
player pool a draft crowd holds up, not about "outsmarting" anyone) rather than just quoting the
bigger number. This is meant to read as credible BECAUSE it's not all good news — don't soften it
into vague positivity.

## STRICT GUARDRAILS — read every sentence you write against this list before finishing

**Never write, in any form or paraphrase:**
- "beat the market," "beats the market," "beat consensus," "beats ADP," "beat ADP," "beats ECR,"
  "outperforms the market," "market-beating," "our edge," "edge over the market"
- Any win-rate, "you'll win your league," "wins your league" framing
- "Guaranteed," "sure thing," "can't miss," "risk-free," "always right," "never wrong," "profitable"
- "More accurate" (as a standalone claim about our numbers vs anyone else's)
- A claim that spans "every position" or "all four" [benchmarks] — every comparison in this brief is
  mixed (we're ahead on some, behind on others); say so, don't round it up
- Any promise about a specific dollar outcome, ROI, or "make you money"
- Any implied prediction about how a specific 2026 player's season will go, stated as fact rather
  than as "what our model currently projects"
- A specific launch date for a product/sport that isn't live yet (see Roadmap note above)
- Do not drop any confidence-interval caveat that appears in the FACTS block below when quoting a
  number from it. If a stat's CI includes zero, the word "could" or an equivalent hedge must appear
  within the same sentence or the sentence immediately after it.

**Always:**
- Keep every hedge attached to the number it belongs to. Don't state a number in one paragraph and
  its caveat three paragraphs later.
- If in doubt whether a sentence overclaims, cut it or soften it — a duller true sentence beats a
  punchier false one for this brand.

## Structure

1. Hook (the self-correction story, or your chosen alternative) — 150–200 words
2. What we built (the rollout) — 150–200 words
3. How we hold ourselves accountable (required) — 150–200 words
4. What's next (light, roadmap-vague) — 50–100 words
5. CTA — 30–50 words, pointing at signing up / the free board / the track record page

## Length

600–900 words total for the post itself.

## Candidate headlines (give me 4–5, in this style — plain, a little wry, no hype)

Style examples to calibrate tone (do not reuse verbatim, write fresh ones in this register):
- "We Found Our Own Numbers Were Wrong. Here's What We Did About It."
- "Before You Draft: How We Grade Ourselves, Every Season, in Public"
- "Fantasy Football, Minus the Fake Precision"
- "We Just Fixed a Bug in Our Own Model. We're Telling You About It Anyway."
- "Draft Season Is Here. So Is the Part Where We Show Our Work."

---

## FACTS — do not embellish. Use only these numbers, and only with the caveats attached.

**1. The self-correction (primary hook material):**
- We audit our own season projections against 13 years (2013–2025) of actual outcomes.
- On the players who matter most for fantasy rosters, our pooled bias moved from −12.85 points/player
  (systematically low) to +1.41 (essentially zero), after a fix validated out-of-sample.
- The root cause was the *rate*, not availability: before the fix, a running back's priced per-game
  production sat at roughly 86% of what he actually produced (receiver and tight end were similarly
  affected: ~85% and ~84%). We were not underestimating how often players would be hurt or benched —
  we were slightly underpricing what they did on the field when they played.
- This was validated with a pre-registered statistical test against two alternative fixes and a
  do-nothing baseline, passing every check (statistical significance p = 0.0002; the fix cleared a
  formal overfitting check at >99.9% confidence).
- The fix does not change player rankings — verified, the order within each position was identical
  before and after (this was a correction to the size of the numbers, not who's ranked where).
- As a visible result on the board: running back point totals moved up about 25% on average, wide
  receiver and tight end up about 10–11%, quarterback down about 7% — running backs move up the
  overall board relative to quarterbacks as a direct, disclosed consequence.
- This shipped the day before today's launch (2026-08-15).

**2. The track record (accountability section — use exactly, with hedges intact):**
- Every season since 2019 (7 seasons), we grade our board against the actual draft-day market and
  against what really happened that year.
- Against the real-money draft crowd we publish ourselves against: our order and the market's are
  *statistically indistinguishable* over that span — the gap is small enough that it could be noise,
  and we say so on the page itself. This is a wash, not a win.
- We trail two staff fantasy-ranking products and one expert-consensus product by a real (not noise)
  but modest amount, over the same 7 seasons.
- Against one other real-draft-market comparison (a second, larger platform's ADP), there IS a real,
  statistically clean gap in our favor — but it's explained by that platform ranking substantially
  more players per season than the one we lead with; restricted to an apples-to-apples depth, that
  gap also becomes noise-sized. State this nuance if you use this number at all — do not quote just
  the bigger, flattering figure.
- Position-by-position, on the comparison we lead with: we're modestly ahead at quarterback, wide
  receiver and tight end, and modestly behind at running back — small gaps at every position, not a
  sweep in either direction.

**3. The disagreement examples (2026, forward-looking, NO accuracy claim — season hasn't happened):**
- We're notably higher than the market's consensus on Christian McCaffrey, Zach Ertz, Ja'Marr Chase,
  and Alvin Kamara.
- We're notably lower than the market's consensus on Travis Hunter, Joe Burrow, Luther Burden III,
  and Bhayshul Tuten.
- Frame every single one of these as "here's what our model currently sees" — never as a prediction
  stated as fact, and never implying the market is wrong.

**4. The nflverse fact (independent of our own model, freely reusable as a cold open):**
- Looking at NFL players who finished in the top 24 at their position in PPR fantasy scoring in a
  given season (from 2015–2024, 9 year-to-year comparisons, ~216 player-seasons per position): a
  top-24 quarterback repeats top-24 the next year about 71% of the time; a top-24 tight end about
  60%; a top-24 running back about 54%; a top-24 wide receiver about 53%.
- Running backs and wide receivers are essentially tied — the popular idea that receivers are the
  "safe" pick and running backs are inherently the volatile one doesn't show up at the top of either
  position, in this data.

**5. What the board actually is (use if explaining our architecture):**
"Our projected points come from a model that never looks at the draft market. A second model sets the
order players are ranked in, and at most positions that order blends the market's own consensus with
ours — so our ranking is not an independent read on the market." (This is our own internal
architecture note, quoted — use it if you need to explain why "our ranking differs from the market"
isn't a pure, independent signal.)

**6. Product/pricing facts:**
- Full-season projections with an 80% uncertainty range, for every rostered-relevant player.
- Projections re-scored for the reader's real league settings (scoring format, roster size, league
  size) — not a generic number.
- A live-draft-aware draft optimizer, usable pick-by-pick during a real draft (paid feature).
- One personalized league free with every account (import or manual entry); several leagues plus a
  post-draft roster report for paid accounts.
- A public track record page, free, no account required.
- Pricing live today: first 100 members lock in $10/month permanently; $20/month standard after.

--- COPY ABOVE THIS LINE ---

---

## 6. Follow-up (not this session's job)

This brief still needs: (a) a human to run it through ChatGPT and read the draft against the same
denylist + the honesty culture in `CLAUDE.md`; (b) placement into `frontend/app/admin/blog/` (the
live blog system); (c) confirmation with the team on the NCAAF-roadmap phrasing flagged in §3 before
anything with a date goes out; (d) a `frontend/data/changelog.json` entry is **not** needed for this
doc-only prep session, but the eventual blog *publish* PR is a user-facing change and should get one
per the repo convention.
