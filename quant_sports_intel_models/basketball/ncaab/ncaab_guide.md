# NCAA Basketball (NCAAB) — Implementation Guide (stub)

**Status:** v0.1 — scaffold (Phase 0 not yet started)
**Parent:** `quant_sports_intel_models/multi_sport_roadmap.md`
**Reference implementation:** MLB `baseball/edge_program/` — NCAAB instantiates the same tracks.
**Master data file:** `basketball/ncaab/ncaab_data_inventory.md` *(to be created in Phase 0)*.

> **Cost posture (pre-profit):** start on the **lean substrate** (roadmap §6; **scaffold in `sport_data_platform.md`** — instantiate it, don't reinvent) — free data ingested by **Lambda + EventBridge cron → S3 Parquet lake**, transformed with **`dbt-duckdb`** (Athena for ad hoc), served on the existing Railway PG. No Snowflake warehouse to start. Weekly/daily batch ⇒ naturally cheap. Port-up later (if it earns traction) = Lambda→Dagster, DuckDB→Snowflake from the same S3 prefixes.

## Why NCAAB fits the methodology well
**Most runway** (season ~early Nov) and a **huge game sample** (~360 D1 teams, thousands of games) — far friendlier to the modeling than NFL's ~17 games/team. The base model is the well-established **tempo × efficiency** structure (adjusted offensive/defensive efficiency + pace, KenPom/Torvik-style) → a per-game scoring distribution. The clearest edge seam: **markets are sharp on majors but soft on mid-majors / small conferences** — a strong fit for the **cross-book sharp-anchor (E4)**.

## Applicable Edge tracks
| MLB track | NCAAB instantiation |
|---|---|
| E1 (overfitting audit / CV) | reuse directly |
| E2 (per-side distributions) | tempo×efficiency → game total, team totals, 1H totals (convolve two team-scoring distributions) |
| E3 (closing-line / CLV) | applies; lots of games/day → CLV stabilizes fast |
| E4 (cross-book sharp-anchor) | **strongest seam** — mid-major / small-conference lines lag the sharps |
| E5 (player props) | points/rebounds/assists/threes props |
| E10 (parlay) | calculator first |

## Phased plan (kickoff ~early Nov — most runway of the three)
- **Phase 0 — data:** The Odds API NCAAB (odds + props + scores) on the Railway-cron pattern; team/efficiency + pace data (compute adjusted efficiency from PBP, or ingest a Torvik/KenPom-style source); rosters + injuries; build `ncaab_data_inventory.md`.
- **Phase 1 — honest surfaces by kickoff:** tempo×efficiency base totals/team-totals distribution, parlay calculator, per-book/CLV transparency (esp. mid-major sharp-vs-soft comparison).
- **Phase 2 — gated edge (post-kickoff):** sharp-anchor (E4 — lead with mid-majors), props (E5), CLV (E3); each PBO<0.2 + DSR>0.

```
▶ New-session prompt — NCAAB Phase 0 (data inventory + base model)
Read: multi_sport_roadmap.md + this stub + baseball/edge_program §0/§6 + E2 (the convolution/distribution
pattern) + E4 (sharp-anchor). STEP 1: ingest Odds API NCAAB (odds/props/scores) + team efficiency/pace +
rosters/injuries → write basketball/ncaab/ncaab_data_inventory.md. STEP 2: build a tempo×efficiency per-team
scoring distribution → convolve to game/team totals (E2 analog). Conventions: dbtf not dbt; Snowflake via MCP
fully-qualified no USE; uv run python; hand >1min scripts to the operator; do not git commit/push.
```
