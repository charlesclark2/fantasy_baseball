# NF-C7 — the bench comparator, and a control for the thing it de-emphasises

**Status: SHIPPED.** Two changes that had to go together, plus five defects the work surfaced —
four of them found by DRAFTING, one by re-running a measurement, and none by a green test suite.

**The shipped rule, measured end to end through the engine users actually run:**
**+40.7 season points, 95% CI ±8.5, winning 97 of 120 paired drafts** against the rule it replaces
(`insurance_sorted` in the artifact). Anchors held — the peeking oracle is unbeaten at +92.4, the
nihilist is last at −102.8.

Its bench comes back **19% QB / 16% RB / 22% WR / 44% TE**, against the retired rule's
**51% / 0% / 0% / 49%**: closer to the peeking oracle (35/10/32/23) and farther from the nihilist
(0/0/2/98) on both counts, with running backs and receivers going from **none of the bench to 38% of
it** — which is the live report ("WRs seemed to really not even pop up") answered.

Artifacts: `ablation_results/nf_c7_bench_integration.md` (primary) and
`…_contiguous.md` (absence-model sensitivity).
Guards: `betting_ml/tests/test_nf_c7_pick_recommendation.py`, RED-proven by
`betting_ml/tests/nf_c7_red_proof.py` (16 deliberate breaks, all caught).
`best_alpha = 0`; nothing here claims an edge or a result.

## What shipped

**1. A bench pick is priced as insurance, not as discounted VOR.** Once every starter slot is full,
the next pick is bench depth — and it was ranked by VOR, which is a STARTER-SCARCITY currency.
NF-C-LDA-6 showed that is structurally guaranteed to return a backup TE or QB late (only 12 QBs and
12 TEs clear replacement; 35 WRs and 25 RBs do and a 12-team room takes all of them by round 8), and
quantified it over 120 drafts: the retired rule's bench came back **51% backup QB / 49% backup TE,
with zero RBs and zero WRs**. A bench seat collects points only in the weeks you have to start him,
so that is what is now measured:

    bench value = P(the men ahead of him are out) × (his weekly points − the man he displaces)

**2. Per-position depth targets.** The insurance rule de-emphasises a backup QB/TE *further*, which
is right on average and wrong for a user who deliberately wants one. A target count per position
moves a short position up **within the bench cohort only** — below every open starter slot, above
generic depth. ⛔ The comparator itself is NOT exposed: `insurance` beats the runner-up by 19.5
season points on the paired delta, which is a measurement, not a preference a user can adjudicate.

Both move in all three implementations together — `frontend/lib/draft-optimizer.ts` (the shipping
engine), `quant_sports_intel_models/fantasy_engine/draft.py` (the extension's), and the mock draft's
shared primitives — pinned byte-for-byte by `test_nf_c_lda_1_optimizer_parity.py`.

## The load-bearing guarantee

**A depth target can never produce an illegal roster.** It reorders WITHIN the level-0 cohort and
touches nothing else: `need_level` is unchanged, so `must_fill` cannot see it; the K/DST deferral is
a higher sort key, so a kicker target cannot surface a kicker in round 6. The reserve constraint
outranks every depth target **by construction, not by tuning**. RED-proven three ways (let the
target reach `must_fill`; let it reach `deferred`; let it apply at every need level — each goes red).

## Five defects, and how each was found

| # | defect | found by |
|---|---|---|
| 1 | A bench candidate priced at his ENTIRE projected season — George Kittle at **248 points of cover** — because the seat count read the roster's CAPACITY at a position instead of the seats it actually OCCUPIES (TE capacity is 2 in 1TE+1FLEX, but with an RB in the flex a TE occupies ONE seat). | running the new rule against the real 2026 board |
| 2 | `pts / games` is points per game PLAYED, so it divides by a number that is tiny for exactly the players a bench comparison is about. Easton Stick (1.9 projected games, 76.6 points) came out at a **40.3/game "rate"**, nearly double any real starting QB, so the rule concluded he would walk into the starting seat ahead of Lamar Jackson and recommended him in **round 10 at "worth 35 as cover" against a published VOR of −189**. Cured by `pts / SEASON_GAMES` — a constant denominator, availability carried once in the numerator. | a live draft pass |
| 3 | With the whole bench tied at 0 (every candidate the roster has no use for), the placement tie fell through to the **player id**, and round 10 recommended Philip Rivers (VOR −246) over bench receivers the retired rule ranked 200 points higher. Cured by breaking the tie on the candidate's own placement value: where insurance is indifferent, the retired ordering stands. | a live draft pass |
| 4 | Putting the insurance value straight into the sort made bench depth outrank EVERY open-starter-slot filler in **8 of the 23** committed draft states that have both — one preferring a bench RB (55.6) to filling an **empty QB1** (12.9). The retired rule did it in 1 of 8, by 0.3 points. | a measurement over the parity states |
| 5 | The study arm claiming to measure the shipped engine re-derived the ranking with its own `max(recs, key=score)` — but `score` is not the engine's sort key. It had been measuring the direct integration (defect 4) and reporting it as the shipped rule. | a re-run coming back BYTE-IDENTICAL after a change that provably moved the engine |

Defect 5 is the one worth carrying forward. **A harness that re-derives what it claims to measure is
a second implementation, free to drift** (E9.61, inside the study this time), and the tell was not a
failing assertion — it was a number that refused to move.

## Two things the measurement decided that argument would not have

**Insurance is a good TIE-BREAKER and a bad PRIMARY.** NF-C-LDA-6 scored its arms by asking the
engine for its top 40 and re-ranking the bench candidates among THOSE. That shortlist was never
presented as part of the rule — but it is. With the identical valuation function:

* re-rank the legacy top-40's bench candidates → **+45.2** season points, ±8.0, 102/120
* re-rank EVERY bench candidate on the board → **+3.0**, ±12.2, 61/120 — a NULL

An insurance value is points added to *my* lineup, so it will happily crown a player the league has
passed on 300 times if his position is thin on my roster; VOR is what says he is not worth a pick.
`BENCH_RERANK_SHORTLIST` is therefore part of the rule, carried over verbatim at 40 — moving it is a
re-measurement, not a preference. ⭐ It admits one exception: the best candidate at any position the
USER is short of, because a bound on how far *insurance* may reach must not be a bound on what the
*user* may ask for. That union is provably inert when no target is set, which is what keeps the
measurement above valid.

**A weighted depth bonus does not work, and the reason generalises.** The obvious spelling was
`NEED_W_DEPTH * urgency` beneath `NEED_W_FLEX`. `urgency` is a VOR gap and a bench candidate's score
is an insurance value — the wrong unit for the number it is added to. Measured mid-draft with
`{QB: 2, TE: 2}` set: the bonus came to well under one point against bench running backs scoring
50+, and not one candidate at a short position reached a six-slot panel. Raising the weight would
have needed ~50× `NEED_W_FLEX`, at which point it is a number reverse-engineered from the answer
(E2.1-r). So the target ORDERS rather than scores, exactly as the K/DST deferral does and for the
same stated reason.

## ⚠️ What this does not establish

* **The shipped rule scores below the study's original arm — +40.7 against +76.5 — and the gap is
  not noise.** Two of the defects above (the seat count and the per-game rate) inflated a
  high-projection candidate toward his whole projected season, and the metric — which fills the best
  legal lineup every week — REWARDS raw quality on the bench. Removing them costs points there while
  making the number the product DISPLAYS true. Shipping "worth 248 as cover" for a player the board
  ranks 17 points below replacement was not an option; the numbers are on screen. ⚠️ Anyone reading
  the original +77.3 as this feature's expected value is reading an arm that priced Bailey Zappe,
  0.8 projected games, at 394 points of bench cover.
* **The room is not adaptive**, and it is one board, one season, one scoring format. The mechanism
  generalises; the magnitudes do not. Absence is drawn independently per week in the primary run; a
  contiguous variant (a missed week makes the next likelier — an injury, not a coin flip) is reported
  as a sensitivity and moves the shipped arm to **+46.9 ±8.2, 99 of 120**, with both anchors intact
  and the same ordering — except that `own_worst_starter` falls BELOW the shipped rule there, so the
  runner-up's identity is not stable across the absence model even though the shipped rule's standing
  is.
* **It is a simulation, not a backtest** — it measures which rule builds a better team *under our
  own projections*. A projection error common to every arm is invisible to it.
* ⛔ **No claim about winning a league.** `best_alpha = 0`.

## For the next session

* `BENCH_RERANK_SHORTLIST` is the highest-leverage number in the engine and has been measured at
  exactly one value. A successor that wants to move it must re-run the study, not reason about it.
* The `bench_value` argument on `recommend` is a RESEARCH SEAM (`None` in every shipped caller). It
  exists so the study scores the real engine instead of a copy — which is the defect that produced
  the most misleading result in this story.
* A position where you hold exactly one starter and no backup has `displaced = 0`, so its bench
  candidate is credited with his full weekly points. That is correct in the model's own terms and is
  why the shipped bench mix still leans tight end. Whether a cross-position displacement (the flex
  seat would be filled by SOMEBODY) is worth modelling is untested, and is the obvious next question.
