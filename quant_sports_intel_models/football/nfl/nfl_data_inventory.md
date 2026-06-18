# NFL Data Inventory — `FOOTBALL_DATA` (Snowflake)

**Status:** v0.1 — **reconstructed from prior code, NOT a live Snowflake scan.**
**Date:** 2026-06-17
**Database (current/stale source):** `FOOTBALL_DATA` (Snowflake) · schemas `raw` → `staging` → `refined`.
**Migration target:** the pre-profit **S3 data lake** (Lambda + `dbt-duckdb`; roadmap §6). This Snowflake stack is the **source to re-home + a reference for the model logic** — *not* the runtime target. The data is stale; `nfl_data_py` is free + re-pullable, so we re-pull fresh into S3 rather than migrate stale rows (see `nfl_guide.md`).

> **How this was derived & its limits.** No Snowflake MCP is connected in the current session, so this inventory was reconstructed from the existing dbt project at `~/Documents/machine_learning/football/jaffle_shop/` (dbt profile `football`, target `FOOTBALL_DATA`; staging = views, marts = tables in `refined`). It is faithful to the **structure** (tables, schemas, grain, lineage) but **does not yet have live row counts, exact column lists, season coverage, or freshness.** §5 gives the SQL to confirm those against the live warehouse (run via the Snowflake MCP in a Claude Code session, or by the operator). Treat this as the Phase-0 first draft to be validated, per `nfl_guide.md`.
>
> The prior code is **exploratory / not-necessarily-production** (per the operator); folder is named `jaffle_shop` for legacy reasons (it's the real football dbt project, not the tutorial).

---

## 1. Provenance
Data is **nflverse** (`nfl_data_py`) plus derived sources: Pro-Football-Reference (PFR), Next Gen Stats (NGS), FTN charting, the NFL Combine, and an imported fantasy-rankings CSV ("footballers"). All landed in `FOOTBALL_DATA.raw` and modeled with dbt up through a `refined` mart layer that already includes **a betting dimension and a preseason projections mart** — i.e. both the betting and fantasy verticals have a real head-start here.

## 2. `raw` schema — source tables (16)
Defined as dbt sources (`models/staging/__sources.yml`). One ingestion table each:

| Table | Source | Description |
|---|---|---|
| `weekly_data` | nflverse weekly | Weekly player stats (the core fact source) |
| `weekly_rosters` | nflverse | Weekly rosters per player (feeds `dim_player`) |
| `rosters` | nflverse | Full roster data per player |
| `depth_charts` | nflverse | Weekly depth-chart positions |
| `snap_counts` | nflverse / PFR | Player snap counts per week |
| `schedules` | nflverse | Game schedule per week (feeds `dim_nfl_betting`) |
| `qb_ratings` | derived | QB ratings per player |
| `passing_pro_football_ref` | PFR | Advanced passing (PFR) |
| `rushing_pro_football_ref` | PFR | Advanced rushing (PFR) |
| `receiving_pro_football_ref` | PFR | Advanced receiving (PFR) |
| `passing_next_gen_stats` | NGS | NGS passing (weekly + season) |
| `rushing_next_gen_stats` | NGS | NGS rushing (weekly + season) |
| `receiving_next_gen_stats` | NGS | NGS receiving (weekly + season) |
| `ftn_chart_data` | FTN | Play-level charting data (keyed `ftn_game_id`) |
| `combine_data` | nflverse Combine | NFL Combine results (keyed `pfr_id`) — **the rookie/draft feeder seed (NCAAF→NFL, roadmap §4)** |
| `footballers_rankings_raw` | imported CSV | Fantasy "footballers" positional rankings (QB/RB/WR/TE) — a fantasy benchmark |

## 3. `staging` schema — `stg_*` views (cleaned/renamed, 1:1 over raw)
`stg_weekly_data` (PK `player_id`), `stg_weekly_rosters`, `stg_depth_charts`, `stg_snap_counts`, `stg_schedules` (PK `game_id`), `stg_qb_ratings`, `stg_combine_data` (PK `pfr_id`), `stg_ftn_chart_data` (PK `ftn_game_id`), `stg_passing_pfr` / `stg_rushing_pfr` / `stg_receiving_pfr`, and the NGS pair per discipline: `stg_passing_ngs_weekly` + `stg_passing_ngs_season` (and the same for rushing + receiving). Materialized as **views**. (Exact columns: verify live — §5.)

## 4. `refined` schema — marts (materialized tables)
| Mart | Grain | Lineage / purpose |
|---|---|---|
| `dim_player` | one row per `player_id` | Player dimension (from `stg_weekly_rosters`) |
| `dim_player_role` | player × validity window | **Type-2 SCD** of player role/position over time (rosters + depth charts + `team_week_calendar`) |
| `team_week_calendar` | team × week | Game schedule + week bounds per team |
| `week_clock_bounds` | week | Week time ranges (time-based joins) |
| `fct_player_week` | **player × week** | Core weekly performance fact (`dim_player_role` × calendar × `stg_weekly_data`) |
| `sat_passing_ngs_weekly` | player × week | `fct_player_week` ⋈ passing NGS |
| `sat_rushing_ngs_weekly` | player × week | `fct_player_week` ⋈ rushing NGS |
| `sat_receiving_ngs_weekly` | player × week | `fct_player_week` ⋈ receiving NGS |
| `sat_snap_counts_weekly` | player × week | `fct_player_week` ⋈ snap counts |
| `mart_opportunity_player_week` | player × week | Opportunity/usage metrics (volume — the projection driver) |
| `mart_efficiency_player_week` | player × week | Efficiency metrics (PFR + fact) |
| `mart_player_season` | player × season | Season rollup (opportunity + efficiency + fact) |
| `mart_projections_preseason` | player (preseason) | **Preseason projections** (team pace/volume × player-season) — a fantasy-projection head-start |
| `dim_nfl_betting` | game | **Betting dimension** off `stg_schedules` (game/score/spread/total context) — a betting head-start |

## 5. Live-verification SQL (run via the Snowflake MCP / a Snowflake-connected session)
Confirm structure, coverage, and freshness — this turns v0.1 into a verified inventory:
```sql
-- 5.1 All tables/views + row counts + columns
select table_schema, table_name, table_type, row_count, bytes
from FOOTBALL_DATA.information_schema.tables
where table_schema in ('RAW','STAGING','REFINED')
order by table_schema, table_name;

select table_schema, table_name, column_name, data_type, ordinal_position
from FOOTBALL_DATA.information_schema.columns
where table_schema in ('RAW','STAGING','REFINED')
order by table_schema, table_name, ordinal_position;

-- 5.2 Season/week coverage + freshness on the core fact (adjust col names to actual)
select min(season) season_min, max(season) season_max,
       count(distinct season) n_seasons, max(week) max_week, count(*) rows
from FOOTBALL_DATA.refined.fct_player_week;

-- 5.3 Schedule coverage (betting dim source)
select min(season) season_min, max(season) season_max, count(*) games
from FOOTBALL_DATA.staging.stg_schedules;
```

## 6. Gaps vs the Phase-1 needs (`nfl_guide.md`)
Strong on **player performance / usage / projections**; the betting layer needs market + status data we don't appear to have yet:
- [ ] **Odds / props / scores** — no Odds API ingestion here. Add NFL odds + player props + scores (Railway-cron pattern, A2.18) → the market layer (E3/E4/E5/E10 analogs).
- [ ] **Injuries / inactives** — high-leverage for NFL; not present in the source list. Add (nflverse injuries + game-day inactives).
- [ ] **Player-ID xref to the Odds API** (props join key) — needed before any prop pricing.
- [ ] **Freshness / current-season** — confirm whether `raw.*` is loaded for the current season and how it's refreshed (the prior code is from ~2025; verify via §5.2).
- [ ] **Combine → NFL rookie translation** — `combine_data` exists; the NCAAF→NFL feeder (roadmap §4) builds on it.

## 7. Bottom line — brownfield migration onto the S3 lake
NFL is **brownfield, not greenfield**: a working `raw → staging → refined` dbt stack exists (player-week facts, NGS/PFR satellites, season rollups, a **preseason projections mart**, a **betting dimension**) sourced from nflverse + PFR + NGS + Combine — **but the data is stale.** Per `nfl_guide.md` + roadmap §6, the plan is **not** to preserve it in Snowflake: **re-home onto the pre-profit S3-lake + Lambda + dbt-duckdb stack** — re-pull fresh nflverse data to S3, port the dbt models (the IP) to `dbt-duckdb`, and add the missing **market data (odds/props/scores) + injuries**. This Snowflake inventory is the **catalog of what to re-home + a model-logic reference**, not the runtime target. (§5 SQL is now **optional** — useful only to confirm the stale source's columns/coverage while porting the models.)
