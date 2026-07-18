# NFL — Implementation Guide (stub)

> ⭐ **NFL NOW HAS ITS OWN ROADMAP + P0 PROMPTS (operator 2026-07-17, deadline 9/9):** `nfl_roadmap.md` + `nfl_story_prompts.md` (story IDs `N<phase>.<story>`: N0.1 data eval → N0.2 scaffold+backfill → N0.3 port the dbt IP → N0.4 Odds/injuries). ⚠️ **TWO CORRECTIONS to this guide's port plan below:** (1) NO `nfl_data_py` (abandoned) → nflverse release Parquet via DuckDB `read_parquet`; (2) orchestrate on the existing **Dagster EC2**, not Lambda+EventBridge. ♻️ Reuse the PROVEN NCAAF stack (`credence-sports-lakehouse`/`nfl/` prefix, `sports_dbt`, the `ncaaf/ingest/` pattern). 🎯 **NFL = product/fantasy/feeder (efficient market → props/CLV/fantasy, NOT head-on edge); NCAAF is the edge play.** This guide = methodology + the detailed port plan; the roadmap/prompts drive the work.

**Status:** v0.2 — roadmap + P0 prompts written 2026-07-17 (deadline-driven); Phase 0 = the brownfield port
**Parent:** `quant_sports_intel_models/multi_sport_roadmap.md`
**Reference implementation:** the MLB `baseball/edge_program/` guides + `baseball/fantasy/` — NFL **instantiates** those patterns; cite them rather than re-deriving.
**Master data file:** `football/nfl/nfl_data_inventory.md` — **v1.0 (N0.1, 2026-07-17)**: ground-truthed live against nflverse release Parquet (25 assets) + The Odds API; source set + lake-table plan LOCKED.

> **Brownfield migration (not greenfield, not preserve-in-place).** `FOOTBALL_DATA` (Snowflake) already holds a working **`raw → staging → refined` dbt stack** (from `~/Documents/machine_learning/football/jaffle_shop/`), sourced from **nflverse + PFR + Next Gen Stats + Combine**: ~16 raw tables, `stg_*` views, and `refined` marts including a **player-week fact** (`fct_player_week`), NGS satellites, season rollups, a **preseason projections mart** (`mart_projections_preseason`), and a **betting dimension** (`dim_nfl_betting`). **But the data is stale (untouched a while), and `nfl_data_py` is free + re-pullable — so we re-home onto the pre-profit stack (S3 lake + Lambda + dbt-duckdb; roadmap §6), re-pull fresh rather than migrate stale rows, and port the dbt models (the real IP).** Snowflake `FOOTBALL_DATA` is kept only as a **reference for the existing model logic**, not the runtime target. NFL is the **first brownfield migration onto the new stack — it proves the porting story** for the other sports. (Prior code is exploratory, not production-ready.)

## Why NFL leans props / CLV / fantasy (not head-on game prediction)
~17 games/team/season ⇒ tiny samples ⇒ out-predicting the full-game line is even harder than MLB. The value seams: **player props** (the biggest), **closing-line/CLV** (NFL lines move sharply on injury/inactive news), **cross-book sharp-anchor** (Pinnacle/Circa vs soft books), **parlay** (huge in NFL, esp. SGP), and **fantasy** (the largest fantasy market — its own `nfl/fantasy/` guide later).

## Applicable Edge tracks (instantiate per NFL)
| MLB track | NFL instantiation |
|---|---|
| E1 (overfitting audit / CV utils) | reuse directly — sport-agnostic |
| E2 (per-side distributions) | per-team scoring distributions → game total, team totals, 1H/quarter totals |
| E3 (closing-line / CLV) | strong fit — NFL lines move a lot on news; CLV is the right scoreboard |
| E4 (cross-book sharp-anchor) | strong — anchor soft books to Pinnacle/Circa |
| E5 (player props) | **the priority** — passing/rushing/receiving yards, TDs, receptions, etc. |
| E10 (parlay) | calculator first; SGP correlation matters more in NFL |
| Fantasy F-series | NFL fantasy (incl. Dynasty + rookies fed by NCAAF — see roadmap §4) |

## Existing ingestion (from the prior notebooks) → port plan
**What the prior code does** (`~/Documents/machine_learning/football/Untitled.ipynb`, 46 cells — exploratory but functional):
- `import nfl_data_py as nfl` → pulls each source for **full history 2015–2025**: `import_seasonal_rosters` → `ROSTERS`, `import_weekly_rosters` → `WEEKLY_ROSTERS`, `import_weekly_data` (2015–2024) → `WEEKLY_DATA`, `import_seasonal_data(…, 'REG')`, `import_draft_picks`, `import_schedules` → `SCHEDULES`, `import_combine_data` → `COMBINE_DATA`, `import_ngs_data('passing'|'rushing'|'receiving')` → `*_NEXT_GEN_STATS`, `import_depth_charts` → `DEPTH_CHARTS`, `import_qbr(level='nfl', frequency='season')` → `QB_RATINGS`, `import_weekly_pfr('pass'|'rec'|'rush', 2018–2024)` → `*_PRO_FOOTBALL_REF`. Light pandas cleanup (e.g. `to_numeric` on jersey/draft numbers).
- **Write path:** `snowflake.connector.connect(account='IHUPICS-DP59975', role='ACCOUNTADMIN', warehouse='COMPUTE_WH', database='FOOTBALL_DATA', schema='RAW', authenticator='snowflake_jwt')` + `write_pandas(df, table_name=…, database='FOOTBALL_DATA', schema='RAW')` — one table per source, **bulk full-history load, manual / notebook-run, not incremental, not scheduled**. (`Untitled1.ipynb` is just EDA — 2025 schedule + NGS for one game.)
- **Good bones:** JWT key-pair auth, `nfl_data_py`→`write_pandas` is exactly the right primitive; the source list already matches the inventory. **Not production:** `ACCOUNTADMIN` + `COMPUTE_WH`, full-reload every run, secrets/keys in the notebook, no schedule, no incrementality.

**Port to the pre-profit stack (Lambda · S3 lake · dbt-duckdb — scaffold in `sport_data_platform.md`; NFL is its first instance):**
1. **Wrap each `nfl.import_* → Parquet-to-S3` as a parameterized ingest fn** (`source`, `seasons`) — swap the old `write_pandas`(Snowflake) for a Parquet write to `s3://<bucket>/nfl/<source>/season=YYYY/…`. **Re-pull fresh** (the data is stale): one backfill (2015–present) as a one-off container/EC2 job, then **incremental weekly** (current season; rewrite the season partition).
2. **Orchestrate with Lambda + EventBridge cron** (weekly in-season) — not Railway cron, not Dagster+ run-minutes. The chunky `nfl_data_py`+pandas+pyarrow dep ships as a **Lambda layer / container image**; the one-time backfill runs off-Lambda (15-min cap).
3. **Transform with dbt-duckdb over S3:** port the existing `jaffle_shop/` models (staging + `refined` marts — `fct_player_week`, NGS satellites, `mart_player_season`, `mart_projections_preseason`, `dim_nfl_betting`) to **`dbt-duckdb`** reading the S3 Parquet. The model SQL is the IP; only the source/target adapter changes.
4. **Secrets / least-privilege:** an **IAM role for S3** + secrets in Lambda env — **no** `ACCOUNTADMIN`, `COMPUTE_WH`, or keys-in-code.
5. **The Odds API** (NFL odds/props/scores) ingests on the **same Lambda→S3 pattern** → its own lake prefixes → joins to the betting/props marts. This is the net-new betting data (player data just gets re-pulled).
6. **Port-up path (when profitable):** the **S3 lake stays**; swap **Lambda→Dagster** and **DuckDB→Snowflake** (external tables / `COPY INTO` from the *same* prefixes) with minimal model change (roadmap §6). Pre-profit work isn't throwaway — it's the lower tier of the eventual stack.

## Phased plan (per roadmap §3; NFL kickoff ~early Sept)
- **Phase 0 — data (brownfield migration):** stand up the **S3 lake + Lambda ingest** (port plan above); **re-pull fresh** nflverse data → S3; port the dbt models to **dbt-duckdb**; refresh `nfl_data_inventory.md` against the lake. Then add the **missing** market + status data: **The Odds API** (odds/props/scores) + **injuries/inactives** (`nfl_data_py` injuries + game-day inactives). Existing Snowflake `FOOTBALL_DATA` = reference only.
- **Phase 1 — honest surfaces by kickoff:** parlay calculator (E10.1 analog), per-book/CLV transparency (A0.4.32 + E3), NFL fantasy projections (F-series). No validated edge required.
- **Phase 2 — gated edge (post-kickoff):** props (E5) + sharp-anchor (E4) + CLV (E3), each PBO<0.2 + DSR>0.

```
▶ New-session prompt — NFL Phase 0 (brownfield migration to the S3-lake stack)
Read: multi_sport_roadmap.md (§6 lean stack + migration path) + this guide (esp. the port plan) +
football/nfl/nfl_data_inventory.md (the existing Snowflake stack you're re-homing) + baseball/edge_program §0/§6.

CONTEXT: NFL data exists in Snowflake FOOTBALL_DATA but is STALE; nfl_data_py is free + re-pullable → RE-HOME,
don't preserve. TARGET STACK = S3 Parquet lake + Lambda/EventBridge orchestration + dbt-duckdb (roadmap §6).

STEP 1 — ingest: build the Lambda ingest (wrap nfl_data_py import_* → Parquet to
s3://<bucket>/nfl/<source>/season=YYYY/). Backfill 2015–present once OFF-Lambda (container/EC2; 15-min cap),
then weekly incremental on an EventBridge cron. Ship deps as a Lambda layer/container.
STEP 2 — transform: port the prior jaffle_shop dbt models (staging + refined marts: fct_player_week, NGS
satellites, mart_player_season, mart_projections_preseason, dim_nfl_betting) to dbt-duckdb over the S3 lake;
refresh nfl_data_inventory.md against the lake.
STEP 3 — net-new betting/status data: Odds API (odds/props/scores) + injuries/inactives, same Lambda→S3 pattern.

Conventions: uv run python; IAM role for S3 + secrets in Lambda env (NO ACCOUNTADMIN / keys-in-code); keep it
weekly batch + incremental; do not git commit/push. Port-up path (later): Lambda→Dagster, DuckDB→Snowflake from the same S3.
```
