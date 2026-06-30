# S3 odds/prop market inventory — ground-truth audit (2026-06-30)

**Read-only S3 audit** (no writes, no Snowflake, no feature/serving/dbt changes; parallel-safe).
Source of truth = the `baseball-betting-ml-artifacts` bucket (`us-east-2`, instance-role
`credential_chain`), **not** the 2026-06-24 recorded inventory. Globbed the actual prefixes;
nothing assumed.

## 🧭 Headline
**23 of ~46 canonical Odds-API MLB market keys are present in S3 — but only ~12 are current to 2026; 11 are stalled at the 2025-08-11 cutoff; 23 were never backfilled (almost all player props + every `1st_1/3/7`-inning spread & alternate-period market).**

All **7 full-game markets are present in some form** — including `team_totals` and full-game
`alternate_totals`, which the clean `mlb/props/` prefix does *not* carry but the **derivative
store (`stg_derivative_odds` / `mart_derivative_closes`) does, current to 2026-06-28.** A
props-only audit would have wrongly flagged those two as MISSING — they are HAVE.

## Where odds actually live — 3 distinct stores, 3 different freshness tiers
| Store (S3 path under bucket root) | Grain | Markets it holds | Coverage | Freshness |
|---|---|---|---|---|
| `baseball/lakehouse/mart_odds_outcomes/{_current,_history}` | de-vigged outcome | **h2h**, **totals** (+`h2h_lay`) | 2020-07-23 → **2026-06-30** | ✅ freshest (today) |
| `baseball/lakehouse/stg_derivative_odds/` (snapshot) + `mart_derivative_closes/` (closing) | snapshot / close | **team_totals**, **alternate_totals** (+ recent F5 `h2h/totals_1st_1/5`, legacy `*_h1`) | 2023-05 → **2026-06-28** | ✅ ~2-day lag |
| `mlb/props/market=*/season=*/date=*/data.parquet` | one row / (game,book,line) | 19 keys (props + period derivatives + spreads) | 2023-05-03 → 2026-06-23 **or** 2025-08-11 | 🟡 split: 8 reach 6/22-23 (≈1wk stale), 11 stalled 2025-08-11 |

⚠️ The clean per-date `mlb/props/` partitions are the **most stale even for the "live" keys**
(last date 2026-06-22/23 vs today 06-30) — a ~1-week capture/backfill stall (consistent with
the INC-22 box outage + the prop capture lagging the main-line capture). `mart_odds_outcomes`
is fresh to 06-30; the derivative store to 06-28.

## Classified inventory vs the canonical Odds-API MLB key list

Legend: ✅ HAVE (current to 2026) · 🟡 PARTIAL (present but stalled 2025-08-11 / season gap) · ❌ MISSING (no S3 data)

### A. Full-game markets — **7/7 present**
| Canonical key | Status | Location | Coverage (min → last) | Rows | Books |
|---|---|---|---|---|---|
| `h2h` | ✅ | mart_odds_outcomes | 2020-07-23 → 2026-06-30 | 1,251,765 | 55 |
| `totals` | ✅ | mart_odds_outcomes | 2020-07-23 → 2026-06-30 | 1,067,300 | 44 |
| `team_totals` | ✅ | stg_derivative_odds / closes | 2023-08-14 → 2026-06-28 | 454,706 / 92,487 | — |
| `alternate_totals` | ✅ | stg_derivative_odds / closes | 2023-05-03 → 2026-06-28 | 1,751,152 / 130,508 | — |
| `spreads` | 🟡 | mlb/props/spreads | 2023-05-03 → **2025-08-11** | 115,578 | 23 |
| `alternate_spreads` | 🟡 | mlb/props/alternate_spreads | 2023-05-03 → **2025-08-11** | 49,764 | 7 |
| `alternate_team_totals` | 🟡 | mlb/props/alternate_team_totals | 2024-04-01 → **2025-08-11** (no 2023) | 12,680 | 4 |

### B. Inning-period markets — 11 present (5 current, 6 stalled), 9 missing
| Canonical key | Status | Location | Coverage (min → last) | Rows | Books |
|---|---|---|---|---|---|
| `h2h_1st_5_innings` | ✅ | mlb/props (+deriv snaps) | 2023-05-03 → 2026-06-23 | 212,828 | 9 |
| `totals_1st_1_innings` | ✅ | mlb/props | 2023-05-03 → 2026-06-23 | 56,200 | 5 |
| `totals_1st_5_innings` | ✅ | mlb/props | 2023-05-03 → 2026-06-23 | 167,006 | 7 |
| `h2h_1st_1_innings` | 🟡 | mlb/props | 2023-05-03 → **2025-08-11** | 8,744 | 1 |
| `h2h_1st_3_innings` | 🟡 | mlb/props | 2023-05-03 → **2025-08-11** | 25,468 | 4 |
| `h2h_1st_7_innings` | 🟡 | mlb/props | 2023-05-03 → **2025-08-11** | 11,672 | 3 |
| `totals_1st_3_innings` | 🟡 | mlb/props | 2023-05-03 → **2025-08-11** | 21,076 | 1 |
| `totals_1st_7_innings` | 🟡 | mlb/props | 2023-05-03 → **2025-08-11** | 6,886 | 1 |
| `spreads_1st_5_innings` | 🟡 | mlb/props | 2023-05-03 → **2025-08-11** | 54,230 | 8 |
| `alternate_totals_1st_5_innings` | 🟡 | mlb/props | 2023-05-07 → **2025-08-11** | 33,052 | 7 |
| `alternate_spreads_1st_5_innings` | 🟡 | mlb/props | 2023-05-07 → **2025-08-11** | 30,666 | 7 |
| `spreads_1st_1_innings` / `_1st_3` / `_1st_7` | ❌ | — | — (only the `_1st_5` exists) | — | — |
| `alternate_totals_1st_1_innings` / `_1st_3` / `_1st_7` | ❌ | — | — (only the `_1st_5` exists) | — | — |
| `alternate_spreads_1st_1_innings` / `_1st_3` / `_1st_7` | ❌ | — | — (only the `_1st_5` exists) | — | — |

### C. Batter player props — 3 present (all current), 10+ missing
| Canonical key | Status | Location | Coverage (min → last) | Rows | Books |
|---|---|---|---|---|---|
| `batter_total_bases` | ✅ | mlb/props | 2023-05-03 → 2026-06-22 | 578,735 | 8 |
| `batter_hits` | ✅ | mlb/props | 2023-05-03 → 2026-06-22 | 500,411 | 5 |
| `batter_home_runs` | ✅ | mlb/props | 2023-05-03 → 2026-06-22 | 475,195 | 3 |
| `batter_rbis` | ❌ | — | — | — | — |
| `batter_runs_scored` | ❌ | — | — | — | — |
| `batter_hits_runs_rbis` | ❌ | — | — | — | — |
| `batter_first_home_run`, `batter_singles`, `batter_doubles`, `batter_triples`, `batter_walks`, `batter_strikeouts`, `batter_stolen_bases` | ❌ | — | — | — | — |
| all `batter_*_alternate` variants | ❌ | — | — | — | — |

### D. Pitcher player props — 2 present (both current), 4+ missing
| Canonical key | Status | Location | Coverage (min → last) | Rows | Books |
|---|---|---|---|---|---|
| `pitcher_strikeouts` | ✅ | mlb/props | 2023-05-03 → 2026-06-22 | 66,128 | 8 |
| `pitcher_outs` | ✅ | mlb/props | 2023-05-03 → 2026-06-22 | 39,679 | 9 |
| `pitcher_record_a_win`, `pitcher_hits_allowed`, `pitcher_walks`, `pitcher_earned_runs` | ❌ | — | — | — | — |
| all `pitcher_*_alternate` variants | ❌ | — | — | — | — |

**`mlb/props/` totals:** 19 keys · 10,884 files · 2,465,998 rows. (`h2h_h1`/`totals_h1` in the
derivative store are tiny 2023-only legacy snapshots — not canonical keys; ignore.)

## 🎯 Priority grab for the cross-market RV probe (E13.14) — credit budget BEFORE the rate drop
Revised against ground truth (the original target list assumed `team_totals` was missing — **it isn't**):

1. **`batter_runs_scored` + `batter_rbis`** — ❌ MISSING, and both are core to a cross-market run-value reconciliation (runs/RBIs tie batter props to team totals). **Top spend.** Add `batter_hits_runs_rbis` (the combo) if cheap.
2. **Full-game `spreads`** — 🟡 stalled at 2025-08-11. Needs a **2026 catch-up + ongoing capture** (run-line is the spread leg of the RV probe). High value, partial cost (only the 2025-08-11→present gap).
3. **`team_totals` — DO NOT re-buy.** Already current in the derivative store (→2026-06-28). If E13.14 needs it in the clean per-date `mlb/props/` grain, that's a **re-shape from existing S3**, not an Odds-API spend.
4. **Un-stall the F5 alternate/period set** (`spreads_1st_5_innings`, `alternate_totals_1st_5_innings`, `alternate_spreads_1st_5_innings`, plus `h2h/totals_1st_1/3/7`) — all 🟡 frozen at 2025-08-11. These are E13.13's derivative-efficiency inputs; the 2023-2025 history is fine for offline eval, but forward-CLV (E2.6) needs the 2026 gap filled.
5. **Lower priority:** the remaining batter/pitcher props (`pitcher_earned_runs`, `pitcher_walks`, `batter_walks`, etc.) — only if a specific prop-pricing story calls for them.

**Net budgeting read:** the expensive gaps are *player props* (most never captured) and the *2026 catch-up on the 11 stalled keys*. The full-game and the main derivative markets (h2h/totals/team_totals/alternate_totals) are already covered and current — no spend needed there beyond keeping live capture healthy.

## Method (reproducible)
- DuckDB `read_parquet` / `glob` over S3 with `PROVIDER credential_chain, REGION 'us-east-2'` (no explicit boto3 keys).
- Coverage (season/min/max/last) parsed from hive partition paths via one `glob()` (zero data reads); row counts via footer-only `count(*)`; book counts via `count(distinct bookmaker_key)` on each market's latest partition; full-game + derivative markets from `mart_odds_outcomes` / `stg_derivative_odds` / `mart_derivative_closes` `market_key` aggregates.
- No writes, no ingest, no credits consumed.

---

## ⏭️ Operator handoff
- **Headline:** S3 holds **23 of ~46** canonical Odds-API MLB keys — **~12 current to 2026, 11 stalled at 2025-08-11, 23 never backfilled**. All 7 full-game markets present (h2h/totals fresh to 06-30; team_totals/alternate_totals current to 06-28 in the derivative store; spreads/alt_spreads/alt_team_totals stalled). The biggest gaps = player props.
- **Action items (no credits spent here — inventory only):** before the Odds-API rate drop, budget for (1) `batter_runs_scored` + `batter_rbis` (+`batter_hits_runs_rbis`), (2) the 2026 catch-up on full-game `spreads` + the stalled F5/period set, and (3) re-shape (not re-buy) `team_totals` into `mlb/props/` if E13.14 wants per-date grain.
- **Also flag:** the `mlb/props/` clean partitions are ~1 week stale (last 2026-06-22/23) vs `mart_odds_outcomes` (06-30) — confirm the prop/derivative capture resumed after the INC-22 box recovery.
- **git add:**
  ```bash
  git add quant_sports_intel_models/baseball/edge_program/ablation_results/odds_market_inventory_2026-06-30.md
  ```
- No code/data/dbt changes; nothing else to commit.
