# E2.0c — MLB F5 Derivative-Odds Source Survey

**Date:** 2026-06-18  
**Context:** Odds API probe (E2.0b, 2026-06-18) confirmed F5 (h2h_h1 / totals_h1) is **NOT offered by any tracked bookmaker** on The Odds API. This survey evaluates whether an alternative or supplemental source can fill the gap.  
**Verdict:** [see Recommendation below](#recommendation)

---

## Comparison Table

| Provider | F5 Coverage | History Depth | Cost/mo | Integration Fit | Status |
|---|---|---|---|---|---|
| **The Odds API** (current) | ❌ Not offered (probe confirmed) | "Additional markets" from 2023-05-03 | ~$150–200 (5M credits) | ✅ Native | In use; F5 gap confirmed |
| **SportsGameOdds** | ⚠️ `1ix5` deprecated → `1h` (baseball first-half = F5) | Historical on Pro tier only | $99 Rookie (no history) / $299 Pro | ⚠️ Inverted JSON format | Best candidate; over budget |
| **OddsJam** | ❓ "Alternate markets" in docs, no explicit F5 named | Advertises closing lines + history; no year count disclosed | Contact-only (unknown) | ❓ Unknown format | Black box; needs sales call |
| **OpticOdds** | ❓ "Several years" of price history; no F5 named in docs | "Several years" for major leagues | ~$5,000+/mo per sport (enterprise) | ✅ REST API (`/fixtures/odds/historical`) | Far out of budget |
| **Sportradar / Genius Sports** | ❓ Likely yes (official MLB data rights) | Deep, multi-year | ~$2,500–5,000+/mo | Complex licensing | Enterprise only |
| **ActionNetwork** | ❌ No public API or data export found | N/A | N/A | N/A | Not viable |
| **OddsPortal / BetResearch** | ❌ Game-level only; no F5 documented | Available but game-level | Free / cheap scraping | Scraping only; ToS risk | Not viable at production grade |
| **SportsBookReview (SBR)** | ⚠️ Displays F5 publicly in UI | Unknown; forward only likely | N/A (scraping only) | Scraping; no licensed API found | ToS review required; not production-grade |

---

## Detailed Findings

### SportsGameOdds (strongest candidate)

**F5 coverage:**  
SportsGameOdds is the **only provider** that explicitly documented a `1ix5` periodID for MLB first-5-innings markets in API documentation. However, they are **actively deprecating `1ix5` in favor of `1h` (first half)**:

> *"The `1ix5` periodID (1st 5 Innings) is being deprecated in favor of `1h` (1st Half) for Baseball. Please migrate any usage of `1ix5` to `1h`."*

In baseball betting, "first half" = "first 5 innings" — they are the same market. So `1h` almost certainly preserves F5 coverage, but the deprecation introduces uncertainty and the `1h` label is less precisely F5-specific.

**Historical depth:**  
Unknown. Historical data requires the Pro plan; no year count is disclosed in public docs.

**Pricing:**  
- Rookie: $99/mo — 77 books, 100k objects/mo, 3-min refresh, **no historical data**
- Pro: $299/mo — 82 books, unlimited objects, sub-minute refresh, historical data included

$299/mo is ~double the $150-200/mo target.

**Integration fit:**  
Structurally inverted vs The Odds API. The Odds API is bookmaker-first (array of bookmakers, each with markets). SportsGameOdds is market-first (compound oddID key `{statID}-{statEntityID}-{periodID}-{betTypeID}-{sideID}` with bookmakers nested inside). Mapping to `derivative_odds_raw → stg_derivative_odds → mart_derivative_closes` would require a non-trivial ETL transform (new ingest script, different JSON path structure).

**ToS:** Commercial use is explicitly the product model. No restrictions found.

---

### OddsJam

**F5 coverage:**  
Advertises "mainlines, spreads, totals, player props, live odds, and alternate markets" for MLB across 100+ sportsbooks. **No explicit mention of h2h_h1, totals_h1, or "first 5 innings" in any public documentation or marketing copy.** May be included under "alternate markets" but unconfirmed.

**Historical depth:**  
Advertises "Full Historical Odds Database" with "closing lines, opening odds, and live line changes" — but discloses **no specific year count or date range**.

**Pricing:**  
Contact-only. No public pricing. Could be in budget or far out of it.

**Integration fit:**  
Unknown — no public API schema documentation found. Would require trial access or sales engagement to evaluate.

---

### OpticOdds

**F5 coverage:**  
Has a `/fixtures/odds/historical` endpoint with per-price-change timestamps and settlement data. Developer docs list only "moneyline, run line, and total runs" as main baseball markets — **no F5 market code documented**.

**Historical depth:**  
"Several years of complete price history" for major leagues — no specific year named.

**Cost:**  
Enterprise-tier: estimated $5,000+/month per sport. Completely out of budget for this use case.

---

### Sportradar / Genius Sports

Not directly evaluated. Sportradar holds exclusive official MLB data rights (announced partnership). Both are enterprise-only vendors with pricing in the $2,500–5,000+/mo range. Effectively out of scope.

---

### SportsBookReview (SBR) — scraping signal

SBR publicly displays "1st 5 Innings" moneyline data in its UI. No licensed API or commercial data product built on SBR was found. Scraping is technically feasible but:
- ToS review required
- Not production-grade for a live ingest pipeline
- No historical depth guaranteed

---

## Recommendation

**Formally PAUSE (not kill) the F5 thesis. Two sales inquiries before any final kill decision.**

The research conclusively found no source within the $150-200/mo budget that offers confirmed F5 market data with verifiable historical depth. However, the absence of *documentation* does not prove absence of *data* — OddsJam and SportsGameOdds both have the plausible infrastructure to carry F5.

### Action plan

**Priority 1 — SportsGameOdds sales inquiry:**  
Ask specifically:
1. Does `1h` (first half) in MLB return the same market as the deprecated `1ix5` (first 5 innings)?
2. What is the historical depth for MLB `1h` markets on the Pro plan? Is 2021+ data available?
3. Is there a trial period or month-to-month Pro plan?
4. Can they do a budget negotiation below $299/mo for a single-sport use case?

If yes to 1 & 2 with depth ≥ 2021: **SportsGameOdds Pro at $299/mo is the recommended integration path.** ROI: enables E2.4 + E2.6 F5 efficiency evaluation, which could be the highest-alpha derivative market. A separate ETL shim would be needed (new ingest script; not a drop-in replacement for `derivative_odds_backfill.py`'s current Odds API format).

**Priority 2 — OddsJam sales inquiry:**  
Ask specifically:
1. Do you carry MLB h2h_h1 (first-half moneyline) and totals_h1 (first-half total) market codes?
2. What is your historical depth for those markets?
3. What is the pricing for API access (historical + live)?

If F5 coverage confirmed at a competitive price: OddsJam's 100+ book coverage could be a better deal than SportsGameOdds.

### Kill criterion

If **both** SportsGameOdds and OddsJam come back as:
- No F5 coverage, OR
- F5 coverage but history < 2021, OR  
- Pricing > $400/mo

→ **Formally KILL the F5 thesis.** Update E2.4 and E2.6 to remove F5 efficiency evaluation. Redirect derivative-odds evaluation to team-totals and alternate-totals (already captured live via E2.0b). Document kill in the implementation guide.

---

## Integration plan (if SportsGameOdds chosen)

A new ingestion script (`scripts/sgo_derivative_capture.py`) would be needed — the JSON format inversion means `derivative_odds_backfill.py` cannot be extended directly without significant refactoring. The transform maps:

```
SGO format:
  oddID: "{statID}-{statEntityID}-{periodID}-{betTypeID}-{sideID}"
  byBookmaker: { draftkings: { odds: '-112', available: true }, ... }

→ derivative_odds_raw target (Odds API bookmakers-array shape):
  { id, commence_time, home_team, away_team,
    bookmakers: [
      { key: 'draftkings', markets: [
          { key: 'totals_h1', outcomes: [{ name: 'Over', price: -112 }] }
      ]}
    ]
  }
```

The Snowflake staging and dbt layers (`stg_derivative_odds`, `mart_derivative_closes`) would not need changes — only the ingest script changes.

---

## CI gate

No code changes in this story. Gate/AC:
- [x] Source comparison doc produced (this file)
- [x] F5 verdict: **PAUSE** (not kill) — pending sales inquiries
- [ ] Sales inquiries sent (operator action)
- [ ] Final kill/proceed decision after sales inquiry responses
