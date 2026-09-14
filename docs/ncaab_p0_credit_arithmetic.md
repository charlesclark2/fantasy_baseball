# NCAAB-P0 — Odds API credit arithmetic, cadence proposal, and the fan-out ceiling

**For the operator. This is a spend decision; nothing here has been enabled.**
Measured 2026-09-14 against live `x-requests-remaining` / `x-requests-last` headers.
Witness: `quant_sports_intel_models/basketball/ncaab/ablation_results/ncaab_p0_credit_probe.json`.
Constants: `basketball/ncaab/ingest/budget.py`. Reproduce: `python -m …ingest.credit_probe`.

## 0. How these numbers were made honest

Every paid call was measured **twice, independently**:

1. `x-requests-last` — the API's own statement of what the call cost.
2. A **bracket** — a free `/sports` read before and after the run. `/sports` bills 0 (measured,
   not assumed), so the drop in `x-requests-remaining` is a total that does not depend on
   trusting the per-call header.

**The two agreed exactly on every leg** (`state: AGREE`, 392 = 392 on the authoritative run).
That agreement is the evidence. This discipline exists because NF-CAP1 recorded figures that
were **10× too high** by reasoning from the vendor's documented multiplier instead of measuring.

**Total spent establishing all of this: 775 credits — 0.016% of the balance.**
Balance at probe open: **4,812,933** remaining (187,067 used).

## 1. Measured unit prices

| Call | Credits | How established |
|---|---:|---|
| `/sports` | **0** | measured — the bracket instrument |
| live `/sports/{key}/events` | **0** | measured — board enumeration is free |
| live `/odds`, per market × region | **1** | measured on the futures board |
| live `/odds`, 3 markets × `us` (a game-line snapshot) | **3** | *derived* — see note |
| live `/odds` on an **empty** board | **0** | measured ⭐ |
| historical `/odds`, per market × region | **10** | measured 3×, one market at a time |
| historical `/odds`, 3 markets × `us` | **30** | measured |
| historical `/events` | **1** | measured (**not** free, unlike the live one) |
| historical **per-event** `/odds`, 3 markets | **30** | measured — the fan-out unit price |
| historical `/odds` before the archive begins | **0** | measured ⭐ |
| NCAAB **player props** | **n/a** | measured: HTTP 200, **0 books, 0 markets, 0 credits** |

> **The one derived number.** `basketball_ncaab` was out of season on the measurement date, so
> its live board was empty — and an empty board bills 0, so the live game-line price could not
> be read directly. The derivation is tight: the *historical* per-market price is measured at
> 10, and the multiplier is measured at exactly 10× (the identical single-market futures call
> billed **1 live and 10 historical**, same key, same region, same day). So live per-market is
> 1 and three markets cost 3. **Verify it directly on the first in-season day** — it is a
> one-call check.

⭐ **Two free behaviours that change the cadence decision.** An empty board costs nothing, and a
pre-archive historical probe costs nothing. A polling schedule enabled today therefore bills
**zero** until games actually post lines. Enablement does not have to wait for the season.

## 2. Archive depth and granularity — measured, and the vendor named the floor

Three pre-archive probes each returned `next_timestamp: 2020-11-16T09:15:00Z`, so no binary
search was needed — the API states its own first snapshot.

| | Game lines (`basketball_ncaab`) | Title futures |
|---|---|---|
| First snapshot | **2020-11-16T09:15:00Z** | **2023-10-24T05:45:43Z** |
| Seasons recoverable | **6** (2020-21 … 2025-26) | 3 |
| Granularity | **5 min** from 2022-23; 10 min for 2020-21 & 2021-22 | 5 min |
| Markets retained | h2h, spreads, totals — all three, all seasons probed | outrights |
| Books | 10–11 US books | 3–4 |

**A T-1 snapshot and a true closing line are both fully reconstructible** at 5-minute
resolution for the last four seasons.

### ⚠️ This corrects the brief's "now-or-never" framing

The spec treats early futures as now-or-never. **Measured: they are not.** Title futures are
recoverable from `/historical` back to 2023-10-24 at 10 credits a snapshot. The urgency is real
but it is a **10× cost premium**, not permanent loss. Forward capture remains the right call —
it is 10× cheaper and it is the only way to capture *this* week — but "we lose it forever"
should not be an input to the decision for anything after October 2023.

## 3. Forward capture — the proposal

One `/odds` call returns the **entire** upcoming board no matter how large (measured up to 105
events). **Cadence, not slate size, is the only lever on cost.**

| Option | Credits/season (154 days) | % of balance |
|---|---:|---:|
| Futures, weekly | 22 | 0.000% |
| **Futures, daily** | **154** | **0.003%** |
| Game lines, 2×/day (T-1 + evening) | 924 | 0.019% |
| Game lines, hourly × 16h | 7,392 | 0.154% |
| **Game lines, every 30 min × 16h** | **14,784** | **0.307%** |
| Game lines, every 5 min × 16h | 88,704 | 1.843% |

### Recommendation

**Futures daily (154) + game lines every 30 minutes across the 16-hour US window (14,784) —
≈ 14,938 credits for the whole season, 0.31% of the balance.**

Rationale: 30-minute resolution puts a snapshot within half an hour of every tip, which is
enough for an honest closing-line read, while costing a rounding error. The 5-minute option
matches the vendor's own archive granularity and is still under 2% — so if P2's calibration
work later wants exact closes, **the upgrade is affordable and reversible**; it does not need
to be decided now.

⚠️ The live endpoint returns **in-play** games with in-play prices. The capture must bound on
`commence_time` and re-check after the fetch — an in-play price reaching a store that a
pre-game line is served from is the one thing this vertical must never do (the NCAAF
`odds_live_capture` discipline, inherited).

## 4. Historical backfill — priced, as a decision

30 credits per whole-board 3-market snapshot; 6 archived seasons.

| Resolution | Per season | **6 seasons** | % of balance |
|---|---:|---:|---:|
| T-1 only (1/day) | 4,620 | **27,720** | 0.58% |
| T-1 + late evening (2/day) | 9,240 | **55,440** | 1.15% |
| Every 4h evening (4/day) | 18,480 | **110,880** | 2.30% |
| Hourly evening (8/day) | 36,960 | **221,760** | 4.61% |
| Per distinct tip slot (~21/day) | 97,020 | **582,120** | 12.09% |

**Recommendation: T-1 + late evening, 6 seasons — 55,440 credits (1.15%).** That buys a
market-relative training window and a CLV benchmark for every archived season at close to a
rounding error. The per-tip-slot option is the only one that costs real money, and it buys
exact per-game closes, which nothing in P1 or P2 currently needs.

> **This is the binding constraint on market-relative work, and it is worth stating plainly:**
> game data goes back **24 seasons** (free, hoopR); market data goes back **6**. Any model that
> needs the market in its training window is capped at 6 seasons **regardless of spend** —
> that is an archive limit, not a budget one.

## 5. The fan-out ceiling — built in, refusing, not truncating

**Measured: a per-event historical call costs 30 credits and returns ONE event. The bulk call
costs 30 credits and returns 105.** Identical data, **105× the price**.

NCAAF could afford a per-kickoff loop because its ~60 kickoffs sit on one day a week. NCAAB
runs 50+ games a night for five months and the board does **not** cluster (measured: 105 events
across 45 distinct tip slots), so the shape that is merely wasteful in football is
budget-destroying here.

| | Per-event | Bulk |
|---|---:|---:|
| One peak Saturday board | **3,150** | **30** |
| A season of daily closes (~60 games/day) | **277,200** | **4,620** |

`budget.guard_fan_out()` **raises** above a default ceiling of 8 events, naming the cost, the
cheaper bulk alternative, and how to raise the ceiling deliberately. It does **not** truncate:
a silently-truncated fan-out captures a partial board and reports success, so the gap is
invisible in the artifact and the operator pays for a capture they cannot trust. Refusing is
recoverable; a silent partial is not.

## 6. Two findings that change scope

- **There is no conference-futures sport key.** The live `/sports` list carries exactly two
  NCAAB keys: `basketball_ncaab` and `basketball_ncaab_championship_winner`. The spec's
  "futures (title/conference)" can be delivered as **title only**. Conference futures are not
  available at this vendor at any price.
- **NCAAB player props are not offered.** A per-event props request returns HTTP 200 with **0
  books and 0 markets** and bills 0. The roadmap's E5-style props track is **blocked at the
  source**, not a budget question — worth knowing before it is planned around.

## 7. Operator steps — paste-ready

Nothing below has been run. All are laptop commands; none exceeds ~2 minutes.

```bash
# 0. Re-verify the balance and the measured prices at any time (spends 392 credits).
cd <repo> && set -a && source .env && set +a
uv run python -m quant_sports_intel_models.basketball.ncaab.ingest.credit_probe \
  --dates "2018-02-01T18:00:00Z,2020-11-16T09:15:00Z,2026-02-01T18:00:00Z" \
  --shape-dates "2026-02-07T23:00:00Z" \
  --markets-date "2026-02-07T23:00:00Z" \
  --out quant_sports_intel_models/basketball/ncaab/ablation_results/ncaab_p0_credit_probe.json

# 1. Confirm the ONE derived price on the first in-season day (~1 call, 3 credits expected).
uv run python -m quant_sports_intel_models.basketball.ncaab.ingest.credit_probe --no-live \
  --dates "" --shape-dates "" 2>/dev/null; \
uv run python -c "
import os,requests
k=os.environ['ODDS_API_KEY']
r=requests.get('https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds',
  params={'apiKey':k,'regions':'us','markets':'h2h,spreads,totals','oddsFormat':'american'})
print('events:',len(r.json()),'cost:',r.headers['x-requests-last'],'(expect 3)')"
```

Schedule enablement, cadence choice, and any backfill remain **operator decisions**. The
ingest side is built and tested; what it does **not** yet have is a Dagster schedule, because
turning one on is the spend decision this document exists to inform.
