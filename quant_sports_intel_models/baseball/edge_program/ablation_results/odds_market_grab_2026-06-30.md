# Pre-reset MLB odds DATA-GRAB — probe + validation + handoff (2026-06-30)

**Probe-first, value-ranked, idempotent.** Land in S3 `mlb/props/market={key}/season=/date=/data.parquet`
(NOT Snowflake), single region `us`, via `backfill_multisport_props_to_s3.py` (instance-role
`credential_chain` / boto3 default chain; bucket `baseball-betting-ml-artifacts`, `us-east-2`).
Pairs with the 2026-06-30 inventory (`odds_market_inventory_2026-06-30.md`).

## 🧭 Headline
- **Live balance (verified, free `/v4/sports`): 544,402 credits**, EXPIRING at the 7/1 reset → refreshes to ~5M (good to ~7/17, then 100k/mo).
- **PROBE ANSWER: every targeted market is AVAILABLE** — archived historically (2024-06-12) **and** current (2026-06-22). The gating question ("are these props even offered?") is YES for all 13 probed keys.
- **Pipeline VALIDATED end-to-end** — a bounded 2-date smoke grab of `batter_runs_scored`+`batter_rbis` landed clean parquet in S3 (sane O/U 0.5 lines, 7 books, ~350 players/day). The new batter markets need no code change — `--markets` override + standard Over/Under extraction handles them identically to `batter_total_bases`.
- **Session spend: 841 credits** (probe 257 + smoke 582 + coverage audit 2). **Remaining: 543,561.**
- The hours-long full grab is **handed to the operator** (per the >1-min rule) with a value-ranked, budget-bounded, resume-on-5M queue below.

## Probe — availability + book depth (region=us, main key)
`PRESENT` = the market returned bookmaker data for the probed game.

| Market | 2024-06-12 | 2026-06-22 | Verdict |
|---|---|---|---|
| `batter_runs_scored` ⭐ | 5 books | 1 book | ✅ available both eras |
| `batter_rbis` ⭐ | 5 books | 4 books | ✅ available both eras |
| `batter_hits_runs_rbis` | 3 books | 6 books | ✅ available both eras |
| `spreads` (full-game) | 12 books | 11 books | ✅ (catch-up 2025-08-12+) |
| `spreads_1st_5_innings` | 9 | 7 | ✅ catch-up |
| `alternate_totals_1st_5_innings` | 5 | 5 | ✅ catch-up |
| `alternate_spreads_1st_5_innings` | 4 | 5 | ✅ catch-up |
| `h2h_1st_1_innings` | 2 | 1 | ✅ catch-up (thin) |
| `h2h_1st_3_innings` | 3 | 5 | ✅ catch-up |
| `h2h_1st_7_innings` | 1 | 2 | ✅ catch-up (thin) |
| `totals_1st_1_innings` | 3 | 4 | ✅ catch-up |
| `totals_1st_3_innings` | 3 | 1 | ✅ catch-up (thin) |
| `totals_1st_7_innings` | 1 | absent (this game) | ✅ catch-up (very thin) |

Book depth varies by game/era but every key is sourced. The single-game `absent` for
`totals_1st_7_innings` on 06-22 is per-game thinness, not a missing market (it was PRESENT on 2024-06-12).

Events/day sample (for projection): 2023-06-14=16, 2024-06-12=15, 2025-06-11=15, 2026-06-18=9, 2026-06-22=13 → **~14–15/day**.

## Per-market FULL-HISTORY cost projections (2023-05-03 → 2026-06-29, us, 2 snapshots)
Formula: `Σ_date [ 1 (events fetch) + n_events × eff × 10×N_markets ]`. `eff` = effective odds-calls/event:
**CONSERVATIVE 1.5×** (the script's `2 snapshots × 0.75`) vs **REALISTIC ~1.15×** (the 23:30Z snapshot
leakage-skips most night games, so snapshot 1 captures nearly everything). Smoke-measured ~200 cr/date for a
2-market combo, consistent with the realistic end.

| Grab | Conservative | Realistic | Fits expiring 544k? |
|---|---|---|---|
| `batter_runs_scored` (1 market) | ~164k | ~126k | ✅ |
| **`batter_runs_scored`+`batter_rbis`** ⭐ | **~328k** | **~252k** | ✅ comfortable buffer |
| +`batter_hits_runs_rbis` (all 3) | ~492k | ~377k | ⚠️ fits but ~52k buffer (conservative) — leave for 5M |
| `spreads` catch-up (2025-08-12+) | ~40k | ~30k | ✅ trivial |
| F5/period set ×9 catch-up (2025-08-12+) | ~356k | ~273k | ✅ on the 5M |

## What was grabbed THIS session (validation only)
`batter_runs_scored` + `batter_rbis`, 2 dates (2023-05-03, 2023-05-04), idempotent.

| Market | rows | events | books | players | avg line | avg over |
|---|---|---|---|---|---|---|
| `batter_runs_scored` | 2,946 | 25 | 7 | 349 | 0.5 | +86 |
| `batter_rbis` | 2,951 | 25 | 7 | 350 | 0.5 | +188 |

Coverage audit (`audit_prop_coverage.py`, events-probe vs S3 diff): 2023-05-03 api=16/s3=15 (1 leakage-skipped
early game), 2023-05-04 api=10/s3=10 ✓ → **gap 1/26 = 3.8%**, the expected leakage-filter behavior (games started
by the 17:00Z snapshot), not a capture defect.

## ⏭️ OPERATOR HANDOFF — the grab queue (run in order; stop when value bar / budget says so)
All commands: single-region `us`, idempotent (existing partitions auto-skip), land in S3. **Hours-long → run on the box.**
The job runs ACROSS the 7/1 reset by design: spend the expiring 544k on #1, then #2–#4 continue on the fresh 5M.

```bash
# ── #1 TONIGHT (uses the expiring ~544k; top value, ~252–328k) ──────────────
uv run scripts/backfill_multisport_props_to_s3.py --mode backfill \
    --sport baseball_mlb --markets batter_runs_scored,batter_rbis
#  (2023-05-03/04 already landed; idempotency skips them. Combining the two
#   shares the 1cr/date events fetch — cheaper than two separate runs.)

# ── RESUME on the fresh 5M (post-7/1) ───────────────────────────────────────
# #2  the H+R+RBI combo (~150k)
uv run scripts/backfill_multisport_props_to_s3.py --mode backfill \
    --sport baseball_mlb --markets batter_hits_runs_rbis

# #3  full-game spreads — 2026 catch-up only (history to 2025-08-11 auto-skips; ~30–40k)
uv run scripts/backfill_multisport_props_to_s3.py --mode backfill \
    --sport baseball_mlb --markets spreads

# #4  the stalled F5 / period set — 2026 catch-up only (~273–356k)
uv run scripts/backfill_multisport_props_to_s3.py --mode backfill \
    --sport baseball_mlb --markets spreads_1st_5_innings,alternate_totals_1st_5_innings,\
alternate_spreads_1st_5_innings,h2h_1st_1_innings,h2h_1st_3_innings,h2h_1st_7_innings,\
totals_1st_1_innings,totals_1st_3_innings,totals_1st_7_innings

# ── After EACH market: coverage audit (events-probe vs S3 diff; 1cr/sampled date) ──
uv run scripts/audit_prop_coverage.py --market batter_runs_scored --sample 12
uv run scripts/audit_prop_coverage.py --market batter_rbis --sample 12
```

**DO NOT grab** `team_totals` / `alternate_totals` — already in the derivative store
(`stg_derivative_odds`/`mart_derivative_closes`, current to 2026-06-28). If E13.14 needs the per-date
`mlb/props/` grain, **reshape from existing S3** (zero API spend), don't re-buy.

**Resume-queue math** (so the post-reset continuation stays bounded; realistic est.):
#1 ~252k (tonight) · #2 ~126k · #3 ~30k · #4 ~273k → **full constellation ~681k total**, trivially inside
the 5M. Everything except #1 has zero urgency (the 5M lasts to 7/17).

**Verify live balance before each run:** `GET https://api.the-odds-api.com/v4/sports?apiKey=$ODDS_API_KEY`
(free; reads `x-requests-remaining`). Confirm the 5M refresh actually landed after 7/1 before kicking off #2–#4.

## Method (reproducible)
- Balance + spend: free `/v4/sports` (`x-requests-remaining`), 0 credits.
- Availability: two-step historical endpoint (`/events` 1cr → `/events/{id}/odds` 10×N cr), all 13 candidate markets in ONE odds call per probed date, region `us`, 2 dates (2024-06-12, 2026-06-22).
- Projection: game-day counts × sampled events/day × eff × 10×N; conservative (1.5×) + realistic (1.15×) bands.
- Smoke + validation: `backfill_multisport_props_to_s3.py --limit 2`; DuckDB footer read over S3 (`credential_chain`, `us-east-2`).
- Coverage audit: `audit_prop_coverage.py` (new) — events-probe vs S3 event-id diff.
- No Snowflake, no eu region, no double-write.

## git add
```bash
git add scripts/audit_prop_coverage.py \
        scripts/backfill_multisport_props_to_s3.py \
        quant_sports_intel_models/baseball/edge_program/ablation_results/odds_market_grab_2026-06-30.md
```
Excluded (gitignored / data, not committed): the S3 parquet partitions written by the smoke grab.
No dbt/feature/serving changes; CI surface = none touched beyond the standalone scripts.
