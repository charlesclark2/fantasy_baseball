# NCAA Football (NCAAF) — Implementation Guide (stub)

**Status:** v0.1 — scaffold (Phase 0 not yet started)
**Parent:** `quant_sports_intel_models/multi_sport_roadmap.md`
**Reference implementation:** MLB `baseball/edge_program/` + the MiLB→MLB translation (Edge **E7**) — NCAAF's feeder model is the football analog of E7.
**Master data file:** `football/ncaaf/ncaaf_data_inventory.md` *(to be created in Phase 0)*.

> **Cost posture (pre-profit):** start on the **lean substrate** (roadmap §6; **scaffold in `sport_data_platform.md`** — instantiate it, don't reinvent) — CFBD is free; ingest via **Lambda + EventBridge cron → S3 Parquet lake**, transform with **`dbt-duckdb`** (Athena for ad hoc), serve on the existing Railway PG. No Snowflake warehouse to start. Weekly batch ⇒ naturally cheap. Port-up later = Lambda→Dagster, DuckDB→Snowflake from the same S3 prefixes.

## Dual role (read this first)
NCAAF has **two distinct value cases**, and the second is why it's in scope despite the tight timeline:
1. **Its own betting/fantasy product — a stretch** on the fall timeline (huge talent disparity, scheme/pace variance, soft markets on smaller programs). Phase it like the others; don't over-invest before NFL/NCAAB.
2. **The NFL feeder — the real near-term value.** College production + combine/draft data → **college→NFL translation factors** → NFL **rookie projections** that power NFL fantasy-dynasty + NFL props (where rookies are otherwise priors-only). This is the football analog of MLB's MiLB→MLB MLEs (Edge E7). **Prioritize NCAAF *data* + the translation model even if NCAAF *betting* slips.**

## Applicable tracks
- Feeder (priority): college→pro player-ID xref + a **college→NFL MLE/translation model** (analog of Edge E7) → feeds the NFL guide's rookie projections (fantasy + props).
- Own product (stretch): E1 (CV), E2 (scoring distributions → totals/team-totals; mismatch-aware), E3 CLV, E4 sharp-anchor (softer small-program lines), E10 parlay calculator.

## Phased plan (kickoff ~late Aug)
- **Phase 0 — data:** **CollegeFootballData (CFBD) API** (free, rich — PBP, rosters, recruiting/talent, results) + The Odds API NCAAF + draft/combine data; build `ncaaf_data_inventory.md`. Build the **college↔NFL player-ID xref** early (it's the spine of the feeder).
- **Phase 1 — honest surfaces (where feasible):** the **feeder rookie projections into NFL** (highest ROI); optionally an NCAAF parlay calculator + CLV transparency.
- **Phase 2 — gated edge (post-kickoff, optional):** NCAAF sharp-anchor / props / totals, PBO<0.2 + DSR>0.

```
▶ New-session prompt — NCAAF Phase 0 (data + the NFL-feeder spine)
Read: multi_sport_roadmap.md (esp. §4 draft-continuity) + this stub + baseball/edge_program Epic E7 (the
MiLB→MLB MLE pattern you mirror). STEP 1: ingest CFBD (PBP/rosters/recruiting/talent) + Odds API NCAAF +
draft/combine data → write football/ncaaf/ncaaf_data_inventory.md. STEP 2: build the college↔NFL player-ID
xref + a first college→NFL translation (the E7 analog) → hand its rookie projections to the NFL guide.
Conventions: dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run python; do not git commit/push.
```
