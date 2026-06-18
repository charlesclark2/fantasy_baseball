# Edge Program — Executive Summary

**Date:** 2026-06-17
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Audience:** internal leadership / strategic stakeholders
**Companion docs:** `edge_program_technical_spec.md` (design), `edge_program_implementation_guide.md` (build plan)
**Tone note:** this is a candid internal assessment, not a sales document. Likelihoods are informed judgment with explicit reasoning, given as ranges to avoid false precision.

---

## 1. The situation in one paragraph

We have built a genuinely strong MLB quantitative platform — comprehensive data, leakage-safe temporal modeling, distributional sub-models, a disciplined promotion gate, and a live advisory product (Credence). The honest finding from our own work is that our models, however well-engineered, **do not beat the full-game moneyline or total head-on.** We have confirmed this 13 independent times across H2H and totals. That is not a failure of execution; it is what an efficient market looks like. The full-game line is the single most-scrutinized number in baseball, and ~10,000 noisy game outcomes cannot out-predict it. The Edge Program accepts this result and redirects the same machinery at the places where edge can still plausibly exist.

---

## 2. What we are doing

We are pivoting from *"predict the game better than the market"* to five betting-edge tracks, each attacking a different, more exploitable seam:

| Track | What it does | Why it can work where head-on prediction can't |
|-------|--------------|------------------------------------------------|
| **E1 — Overfitting audit** | Stress-tests every claimed edge for statistical reality (PBO, Deflated Sharpe, purged cross-validation). | We've run many experiments; each raises the odds the *next* promising result is luck. This makes "is it real?" a measured number, and gates everything else. |
| **E2 — Per-side distributions** | Models each team's runs as a full probability distribution, combines them, and prices the markets books set lazily (first-5-innings, team totals, alternate lines). | The full-game total is priced carefully; its *derivatives* often aren't. A real distribution also powers the transparent "why this pick" view customers want. |
| **E3 — Closing-line / CLV** | Predicts how the line will *move* from open to close, rather than predicting the game. | The market's own move is far more predictable than the game outcome, and "beating the closing line" is the leading indicator of a good price that pros actually optimize. |
| **E4 — Cross-book sharp-anchor** | Flags when a user's book (Bovada, Caesars, FanDuel) lags the sharp book (Pinnacle) on the side sharp money favors. | Requires no out-prediction of anyone — only that soft books update slower than Pinnacle, which is a well-documented, real phenomenon. |
| **E5 — Player props** | Projects individual-player outcomes (strikeouts, total bases, hits, outs) and prices them against the book's prop line, on the player pages. | Props are the softest, most numerous markets — and we already model players in depth, with a prop feature mart and player pages already built. The missing piece (market-line ingestion) is now affordable. |

The product stays strictly **advisory and B2C** (users place their own bets), and every output is framed as transparency/confidence — never a promised win-rate.

**Beyond the betting tracks — data, product, and a second vertical (E6–E10).** The same machinery and brand extend past game betting:
- **E6 — Feature-engineering audit:** a one-time sweep of our ~690 features for overlooked signal and dead weight; cheap, improves every model.
- **E7 — Minor-league data + MLEs:** ingest AAA/AA performance and translate it to MLB-equivalents — closing the rookie-prior gap for the betting models *and* enabling prospect projections.
- **E8 — Fantasy / Dynasty projections suite:** a **second B2C product** — distributional, multi-year, prospect-aware player projections (esp. the underdeveloped Dynasty market). Per the market SWOT (guide §7A) this is plausibly the **highest-value, most-defensible** B2C bet: it monetizes by subscription and isn't gated on beating an efficient market — "match or beat ZiPS/Steamer" is an achievable bar.
- **E9 — Beta-request backlog:** the living product-feedback loop (incl. the migrated auth/billing/push/onboarding stories and the paid-tier revenue path).
- **E10 — Parlay tool:** an honest parlay calculator now (differentiation without edge), a recommender gated behind a real edge source.

---

## 3. Why we are doing it (the strategic logic)

Three facts drive the whole pivot:

1. **Efficient markets can't be beaten on their most-traded number.** Our 13 no-edge confirmations are evidence the system works, not that it's broken. Continuing to tune the point model is the one path we've already proven is a dead end.
2. **Edge migrates to where attention is thin.** Less-traded markets (F5, team totals, alt-lines) and slower books (soft vs. sharp) get less pricing scrutiny. That's where a good model earns its keep.
3. **The right scoreboard is the price, not the result.** Closing-line value (CLV) stabilizes far faster than win/loss and measures skill with much less data — letting us know within weeks, not seasons, whether something is real.

In short: we stop competing where the market is strongest and start competing where it is weakest, and we measure ourselves honestly enough to tell the difference between signal and luck.

---

## 4. What "success" means (defined in tiers)

"Likelihood of success" is only meaningful once success is defined. We see three distinct tiers:

- **Tier 1 — Product success:** a demonstrably better, more transparent, more differentiated platform — full-game and derivative *distributions*, a CLV-confidence read, and book-aware market comparison, all surfaced honestly. This is a defensible consumer product whether or not it beats the market.
- **Tier 2 — Edge success:** a *statistically validated, exploitable* betting edge in at least one market (most plausibly E4 sharp-anchor and/or E3 CLV), surviving our own overfitting gates and showing positive forward closing-line value over ≥100 live games.
- **Tier 3 — Business success:** Tier 2 at enough coverage and durability to drive subscriber retention and growth — i.e. the edge appears often enough, and persists long enough, to matter to a paying user.

> **A second, parallel path to Tier-3 that doesn't require a betting edge:** the **fantasy/Dynasty projections vertical (E8)** is judged on "match or beat industry projections + subscription retention," not on beating a market. Per the market SWOT (guide §7A) it's plausibly the program's most *durable* B2C value, and it de-risks the business case — even if every betting-edge track washes out at the gates, E8 can still be a real product.

---

## 5. Expected likelihood of success (honest assessment)

These are subjective, reasoned estimates, not guarantees. Ranges reflect genuine uncertainty.

| Outcome | Likelihood | Reasoning |
|---------|-----------|-----------|
| **Tier 1 — better, honest product** | **High (~85–90%)** | This depends on sound modeling on data we already have, not on finding market inefficiency. The per-side distribution, CLV bar, and book comparison are buildable and differentiated. Main risk is execution time, not feasibility. |
| **Tier 2 — validated edge in ≥1 market** | **Moderate (~45–60%)** | Two co-front-runners: **E4 (sharp-anchor)**, which needs only that soft books lag Pinnacle (real), and **E5 (player props)**, the softest markets where our deep player models have the most to exploit. **E3 (CLV)** is next. The added breadth of E5 lifts the "at least one market" odds modestly, but all are coverage-dependent and our overfitting gates are deliberately strict, so some apparent edges will wash out. |
| **Tier 3 — edge big/durable enough to drive the business** | **Lower–moderate (~25–35%)** | Even a real edge may be thin in coverage (few exploitable games/day) or limited by soft-book betting caps on winners. This is the hardest tier and the one most outside our modeling control. |
| **Beating full-game main lines head-on** | **Low (<15%) — and not the goal** | Included only to be explicit: we are not betting the program on this, and we'd treat it as a pleasant surprise, not a plan. |

**Per-track read:**
- **E1 (audit):** ~95% it ships and adds value — it's methodology. Its "risk" is that it tells us the other tracks have less signal than hoped, which is it doing its job.
- **E2 (distributions):** ~80% it delivers the distribution + UX (Tier 1); ~30–40% the derivative markets yield a validated edge (Tier 2). High product value, uncertain edge value.
- **E3 (CLV):** ~45–55% the model shows real skill at predicting line movement; monetizing it then depends on our ingestion/timing being fast enough. The most academically-supported path to "real edge," but execution-sensitive.
- **E4 (sharp-anchor):** ~50–60% the signal is real and exploitable — borrows the sharps' accuracy rather than competing with it. Biggest unknown is *coverage* (how often a fresh, exploitable gap exists), not whether the effect is real.
- **E5 (player props):** ~45–55% a validated edge in at least one prop type — the softest markets, and we already model players in depth (a credit-limit increase to 5M/mo makes ingestion + full historical backfill affordable, so the binding constraint is overfitting discipline, not cost). Higher *edge* ceiling than the full-game derivatives; lower *business* ceiling because props carry heavy vig and low limits, and books cap winners fast.
- **E8 (fantasy/Dynasty projections):** ~70–80% it ships as a credible product that matches/beats ZiPS/Steamer on its own validation — and it's **not gated on a market edge**, so it's the highest-probability *durable B2C revenue* of anything here (guide §7A). The real constraint is build scope (it depends on E7 minor-league data + E2's machinery), not feasibility.
- **E6 (feature audit) / E7 (MiLB):** enablers, ~90%+ they deliver — they sharpen models and unlock E8; their "risk" is telling us a track has less signal than hoped (which is them working).
- **E10 (parlay):** the honest **calculator** ~90% ships (pure tooling, zero edge required); the **recommender** is gated behind a live edge source, so its odds track E4/E5.

**The honest headline:** we are very likely to build something genuinely better and more trustworthy than what's on the market (Tier 1), and we have a realistic — slightly better than even — shot at a validated betting edge in at least one market (Tier 2), with **E4 (sharp-anchor) and E5 (props)** the front-runners. We're unlikely to "beat the market" head-on and have stopped trying. The quietly strongest business card may be **E8 (fantasy/Dynasty projections)** — a second B2C vertical that doesn't need a market edge at all.

---

## 6. What would move these odds (leading indicators to watch)

We will know early, not after a full season:
- **E1 PBO/Deflated-Sharpe on the first strategy** — if early candidates clear the overfitting bar, the Tier-2 odds rise; if they consistently wash out, we recalibrate expectations fast and cheaply.
- **E4 coverage report** — how many games per day actually present a fresh Bovada/Caesars/FanDuel gap vs. Pinnacle above threshold. This single number largely determines Tier 3.
- **E3 forward CLV over the first ~100 live games** — positive mean CLV is the leading signal that real edge exists, available in weeks.
- **E2 calibration (`calib_80`) and derivative CLV** — tells us whether the distribution is honest enough to price the soft markets.
- **E5 per-prop PBO + prop calibration** — whether any prop type's edge survives the overfitting gate after the multiple-comparison penalty across markets tried. The honest test of whether prop softness translates into real, repeatable edge.
- **E8 projection accuracy vs ZiPS/Steamer** — does our distributional projection match or beat the industry baselines on rank-correlation + calibration? This (not a betting metric) is the go/no-go for the second vertical, and it's measurable on historical seasons immediately.

Each of these is a cheap, early, go/no-go checkpoint. The program is structured so we spend little before we know whether the expensive parts are worth it.

---

## 7. Cost posture

The program is deliberately cost-disciplined given existing infrastructure spend (Dagster+, Railway, AWS, Snowflake, The Odds API). Dagster only coordinates; heavy compute runs on cheaper surfaces (Railway cron, EC2 batch, DuckDB, S3-Parquet) rather than billed Snowflake or Dagster+ run-minutes. New recurring jobs must show a favorable break-even before they ship. The recent increase of The Odds API limit to **5M credits/month** makes player-prop ingestion *and* a full historical prop backfill affordable, so E5's constraint is modeling discipline, not data cost. This keeps the downside of the uncertain tracks bounded.

---

## 8. Bottom line

We have proven we can't out-predict the market's headline numbers, and we've stopped wasting effort trying. The Edge Program redirects a strong platform at better-targeted opportunities — softer markets, the line's own movement, sharp-book anchoring, and player props — measures each with unusual statistical honesty, and fails fast where the signal isn't there. The most probable outcome is a clearly superior, transparent consumer product; the upside case — a validated, exploitable betting edge, most likely from sharp-book anchoring or props — is a realistic coin-flip rather than a long shot, and we'll know within weeks, not seasons. And independent of all of that, the **fantasy/Dynasty projections vertical (E8)** is a second B2C product whose success doesn't require a market edge at all — the program's most durable business hedge.
