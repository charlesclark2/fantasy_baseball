# MLB-HV2-1 — Node 1: odds data audit

**Story:** MLB-HV2-1 (Bovada H2H market-bias backtest; model-independent).
**Date:** 2026-08-24. **Spec:** `plan_specs/mlb/mlb-hv2-1.yaml`.
**Status of this document:** written and committed BEFORE the pre-registration
(node 2) and before any scoring, per the Plan graph's node order. Every number
below is a COVERAGE / VINTAGE fact. No outcome, no ROI, no price-vs-result
statistic has been computed at the time of writing.

---

## 1. Source tables (exact), and their vintage

The study reads the S3 lakehouse via DuckDB (`scripts/utils/lakehouse_read.duck_connect`),
region `us-east-2`, bucket `s3://baseball-betting-ml-artifacts`.

| Table | S3 key | Role | Object mtime (read 2026-08-24) |
|---|---|---|---|
| `mart_odds_outcomes` | `baseball/lakehouse/mart_odds_outcomes/{_history,_current}/data.parquet` | the Bovada H2H prices | `_history` 238.1 MiB @ 2026-08-24 07:21Z · `_current` 944.8 KiB @ 2026-08-24 20:40Z |
| `mart_game_odds_bridge` | `baseball/lakehouse/mart_game_odds_bridge/**` | `event_id` → `game_pk` (canonical team-id resolution, doubleheader `game_slot`) | daily build |
| `mart_game_results` | `baseball/lakehouse/mart_game_results/**` | `home_team_won`, `game_type`, final scores | 439.6 KiB @ 2026-08-24 07:41Z |
| `stg_statsapi_games` | `baseball/lakehouse/stg_statsapi_games/**` | scheduled first-pitch timestamp (population definition only) | intraday |

Lineage of the odds: `lakehouse_raw/mlb_odds_raw/` (raw Odds API JSON, S3-native
since 2026-07-05) → `stg_oddsapi_odds` (three lateral flattens) → `mart_odds_outcomes`.
**No new paid data is pulled.** No Snowflake.

`mart_game_results` is Statcast/StatsAPI-derived and carries no model output;
`mart_game_odds_bridge` is a name→team_id join. Nothing in this chain is a
Credence model artifact (see the model-independence guard, node 2).

## 2. Bovada H2H raw extent

`bookmaker_key='bovada' AND market_key='h2h' AND sport_key='baseball_mlb'`:
**124,660 outcome rows / 9,494 distinct events, 2020-07-23 → 2026-08-25.**
Bovada is the 5th-best-covered book in the store (draftkings 10,610 events,
betrivers 9,555, betonlineag 9,528, fanduel 9,513, **bovada 9,494**), so the
book named by the spec is also a well-covered one.

## 3. ⚠️ `ingestion_ts` is NOT the capture time before 2026 — use `bookmaker_last_update`

Rows per event, by season, and the sign of `commence_time − ingestion_ts`:

| season | events | rows | rows/event | rows with `ingestion_ts < commence_time` | distinct `load_id` |
|---|---|---|---|---|---|
| 2020 | 590 | 1,180 | 2.00 | **0** | 1 |
| 2021 | 1,690 | 3,380 | 2.00 | **0** | 1 |
| 2022 | 1,666 | 3,332 | 2.00 | **0** | 1 |
| 2023 | 127 | 254 | 2.00 | **0** | 2 |
| 2024 | 1,801 | 3,602 | 2.00 | **0** | 4 |
| 2025 | 1,859 | 3,718 | 2.00 | **0** | 3 |
| 2026 | 1,761 | 109,194 | 62.01 | 97,696 | 3,941 |

2020–2025 is a **one-shot historical backfill**: exactly 2 rows per event (one
per side), a handful of `load_id`s per season, and an `ingestion_ts` stamped at
the 2026-04-23 export run — i.e. *years after* first pitch. A naive
`ingestion_ts < commence_time` pre-game guard therefore rejects **100 %** of the
historical era and silently leaves a 2026-only study. (It did, on the first pass
here: 1,452 events, all 2026.)

The true quote time survives in **`bookmaker_last_update`** — the Odds API's own
"when this book last moved this market" stamp. It is non-null on every row and
strictly pre-first-pitch on **every historical row**:

| season | n | `bookmaker_last_update < commence_time` | median lead (min) | p05 | p95 |
|---|---|---|---|---|---|
| 2020 | 1,180 | 1,180 (100 %) | 221 | 66 | 430 |
| 2021 | 3,380 | 3,380 (100 %) | 224 | 67 | 456 |
| 2022 | 3,332 | 3,332 (100 %) | 248 | 67 | 467 |
| 2023 | 254 | 254 (100 %) | 156 | 65 | 1,880 |
| 2024 | 3,602 | 3,602 (100 %) | 219 | 66 | 460 |
| 2025 | 3,718 | 3,718 (100 %) | 191 | 66 | 462 |
| 2026 | 109,194 | 98,370 (90.1 %) | 554 | −78 | 1,422 |

So the historical price is a **single pre-game quote, typically 1–8 h before
first pitch**. 2026's live capture includes in-play snapshots (negative leads),
which the same bound removes.

**Leakage argument, stated explicitly.** `bookmaker_last_update < commence_time`
bounds *when the price was posted*, not when the snapshot was requested. A
snapshot requested after first pitch that returned a price last moved before it
is still a **pre-game price** — it contains no post-first-pitch information,
which is the only thing that would constitute leakage. The bound is therefore
sufficient for this study, and it is the only column in the store that is a
capture-time proxy across both eras.

## 4. ⚠️⚠️ The store has a systematic WEST-COAST-NIGHT hole (INC-22 UTC-date class)

Coverage of the **completed regular-season slate** (`mart_game_results`,
`game_type='R'`, final score present), split by scheduled first-pitch UTC hour:

| first pitch (UTC hour) | slate games | covered | coverage |
|---|---|---|---|
| 15–23 (US morning → evening ET/CT) | 8,300 | 7,825 | **0.93 – 0.96** |
| 00, 01, 02 (after midnight UTC = West-Coast night) | 3,275 | 351 | **0.098 – 0.119** |

By season and stratum (`early` = first pitch before 00:00 UTC):

| season | early covered / slate | early frac | late covered / slate | late frac | all frac |
|---|---|---|---|---|---|
| 2020 | 575 / 641 | 0.897 | 0 / 257 | **0.000** | 0.640 |
| 2021 | 1,652 / 1,732 | 0.954 | 1 / 697 | **0.001** | 0.681 |
| 2022 | 1,637 / 1,784 | 0.918 | 0 / 646 | **0.000** | 0.674 |
| 2023 | 126 / 1,800 | **0.070** | 0 / 630 | 0.000 | **0.052** |
| 2024 | 1,777 / 1,807 | 0.983 | 0 / 622 | **0.000** | 0.732 |
| 2025 | 1,839 / 1,841 | 0.999 | 0 / 589 | **0.000** | 0.757 |
| 2026 | 1,348 / 1,500 | 0.899 | 350 / 464 | 0.754 | 0.865 |

**The historical backfill captured literally ZERO late-stratum games in five of
six seasons.** The mechanism is the repo's own documented INC-22 class: a
per-UTC-day fetch covers that UTC day's slate, and a game commencing after
00:00 UTC belongs to the *next* UTC day, so it was never requested. Only 2026's
live 30-minute capture reaches those games (0.754).

Its fingerprint in the pooled data is a **team** skew, not an obvious time skew —
home games per team over the whole observed sample ran from LAD 132 and LAA 136
up to CIN 413 and NYY 411. Every under-covered club is Pacific/Mountain.
A study that read the pooled sample as "a 70 % sample of MLB" would have been
reading a near-census of Eastern/Central starts plus a 10 % sample of West-Coast
nights, with the marquee-team segment (LAD) the worst-hit cell.

## 5. Data-quality checks (all pass)

- **E9.52 mixed-snapshot smell** — an impossible both-positive American pair:
  **0 of 9,305**. (1,461 both-*negative* pairs exist; those are ordinary
  near-pick'em prices, not the smell.) The read is snapshot-aligned: both sides
  are taken from the *same* `bookmaker_last_update`, never max()'d across snapshots.
- **Overround** (two-way, proportional): min 1.0229, median 1.0442, max 1.0698 —
  every game vigged, no arbitrage, no sentinel prices surviving.
- **Grain** — `game_pk` is unique in the joined frame: **0 duplicates** (the
  bridge's doubleheader `game_slot` routing holds).
- **Sanity** — pooled home win rate in the joined frame **0.5262**, per season
  0.452 (2023, n=126) to 0.543; MLB's true home-field rate is ~0.52–0.54. The
  join is not scrambled.
- **Game type** — every joined row is `game_type='R'`. The odds backfill carries
  no postseason rows that survive the bridge, so "regular season only" is a
  property of the data, not a filter this study chose.
- **INC-23** — `commence_time`, `ingestion_ts`, `bookmaker_last_update` and
  `stg_statsapi_games.game_date` are VARCHAR in parquet; every comparison in the
  study casts at the use-site (`::timestamp`). The first audit pass raised
  `Cannot compare TIMESTAMP and VARCHAR`, i.e. the loud arm of that landmine.

## 6. Verdict of the audit → what node 2 may register

**The stored odds DO support a market-bias backtest, but NOT over "all stored
MLB games".** Two facts bind:

1. The late (post-00:00 UTC) stratum is ~0 % covered before 2026. Including it
   makes the sample a mixture of a near-census and a 10 % sample, with the
   selection correlated with team, time zone, and therefore with the marquee and
   home/away segments the study wants to test.
2. **2023 is 7.0 % covered** in the early stratum (126 games over 20 distinct
   dates) — a clustered, near-absent season.

Per the spec's own instruction ("re-register the smaller window explicitly
instead"), node 2 registers the **smaller population explicitly**:

- **Population:** completed MLB **regular-season** games with scheduled first
  pitch in UTC hours **03–23** (i.e. before 00:00 UTC), carrying a two-sided
  Bovada H2H quote with `bookmaker_last_update < commence_time`.
- **Seasons:** those whose *early-stratum* coverage is **≥ 0.50** →
  **2020, 2021, 2022, 2024, 2025, 2026** (six season folds). 2023 (0.070) is
  excluded and reported as an unfolded diagnostic.
  The 0.50 threshold is **not load-bearing**: the partition is identical for any
  threshold in **[0.08, 0.89]**, so no choice inside that range changes the design.
- **Resulting n = 8,828 games**, at 0.897 – 0.999 coverage of each season's
  early-stratum slate — a near-census of a cleanly named population rather than
  an unknown-selection sample.
- Every team is present (138 – 737 games). West-Coast clubs appear
  disproportionately as **road** teams (LAD 97 home / 234 away vs NYY 404/322);
  this is a stated limitation, and it is why node 2 registers **no** marquee ×
  home/away interaction arm.

The full observed sample (9,305 games incl. 2023 and the late stratum) is
retained as a **declared, non-gating sensitivity** so nothing is hidden.

## 7. Runtime

The whole extraction — full-history `mart_odds_outcomes` scan filtered to Bovada
H2H, snapshot alignment, both joins — runs in **~7 s** on the laptop against S3.
It is far under the 2-minute operator-handoff threshold; no handoff is required
for this study.

## 8. Reproduce

```
uv run python -m betting_ml.scripts.mlb_hv2_1_market_bias --audit
```
