# Multi-Sport Program Roadmap

**Status:** v1.0 — strategy + scaffold
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Date:** 2026-06-17
**Purpose:** how we extend the platform beyond MLB to **NFL, NCAA Basketball (NCAAB), and NCAA Football (NCAAF)** for the fall-2026 seasons — without rebuilding the methodology each time.

---

## 1. The model: one playbook, many sports
The MLB work produced two reusable, **sport-agnostic** asset classes:
- **The Edge methodology** (`baseball/edge_program/`): overfitting-audited CV (E1: purged CV, PBO, deflated Sharpe), per-side distributional modeling (E2), closing-line/CLV (E3), cross-book sharp-anchor (E4), player props (E5), parlay (E10), plus the shared conventions (market-blind, app-session handoff, cost playbook).
- **The Fantasy projection suite** (`baseball/fantasy/`): distributional player projections + playing-time + aging/Dynasty + prospect (minor→pro) translation.

**New sports instantiate these patterns; they do not reinvent them.** Each new sport's guide *cites the MLB guides as the reference implementation*. The per-sport lift is **(a) data ingestion + a sport-specific base distributional model**; the market/CLV/sharp-anchor/parlay/fantasy layers largely transfer (The Odds API covers NFL/NCAAF/NCAAB odds, props, and scores).

## 2. Repo structure (per-sport folders)
```
quant_sports_intel_models/
  baseball/        ← MLB (reference implementation): edge_program/, fantasy/, baseball_data_mart_inventory.md
  football/
    nfl/           ← nfl_guide.md (+ later nfl/fantasy/), nfl_data_inventory.md
    ncaaf/         ← ncaaf_guide.md, ncaaf_data_inventory.md  (also the NFL feeder — §4)
  basketball/
    ncaab/         ← ncaab_guide.md, ncaab_data_inventory.md
  multi_sport_roadmap.md   ← this file
```
**Every sport gets its own master data file** — a `*_data_inventory.md` modeled on `baseball_data_mart_inventory.md` — the single source of truth for "what data exists" for that sport. Per-sport guides reference it the same way the Fantasy guide references the baseball inventory.

## 3. Sequencing & timeline (fall 2026)
Today is **2026-06-17**. Approximate season starts: **NCAAF ~late Aug · NFL ~early Sept · NCAAB ~early Nov.** That's ~10–12 weeks for football, ~20 for basketball. **You cannot build a *validated-edge* stack for a new sport in that window.** So each sport is **phased**, and "ready by kickoff" means *data + honest product*, not *proven edge*:

- **Phase 0 — Data + odds ingestion** (the long pole; gates everything). Build the sport's `*_data_inventory.md`.
- **Phase 1 — Honest, edge-free surfaces by kickoff** (ship value without a validated edge): the **parlay calculator** (E10.1 analog), **per-book / CLV transparency** (A0.4.32 + E3 surfaces), and **fantasy projections** (F-series analog). None of these require beating the market.
- **Phase 2 — Validated-edge models, gated, after kickoff**: sharp-anchor (E4), props (E5), closing-line (E3) — each gated by the same **PBO < 0.2 + DSR > 0** discipline as MLB. We do **not** promise edge by kickoff.

**Priority** (all three targeted; NCAAF doubles as the NFL feeder):
1. **NFL** — biggest betting + fantasy market. Caveat: ~17 games/team ⇒ tiny samples ⇒ head-on game prediction is even weaker than MLB; lean into **props, CLV, and fantasy**. **Data head-start: some NFL data already exists in Snowflake** — Phase 0 begins by inventorying it (§NFL stub).
2. **NCAAB** — most runway (Nov) + huge game sample (suits the modeling); markets sharp on majors, **soft on mid-majors** (the sharp-anchor seam).
3. **NCAAF** — its own betting/fantasy product is a stretch on the timeline, but its data is high-value as the **NFL feeder** (§4). Prioritize NCAAF *data* even if NCAAF *betting models* slip.

## 4. The NCAAF → NFL draft-continuity pipeline (the cross-sport MLE analog)
This is the same idea as MLB's MiLB→MLB translation (Edge E7): **college production translates to pro rookie expectations.** NCAAF (+ combine/draft data) → **college→NFL translation factors** → NFL **rookie projections** that power NFL fantasy-dynasty and NFL player props (where rookies are otherwise priors-only). So NCAAF ingestion has dual ROI: a (stretch) NCAAF product *and* a real lift to the higher-priority NFL vertical. Build the college→pro player-ID xref + translation model as the football analog of Edge E7.

## 5. Per-sport guides (scaffolded)
- `football/nfl/nfl_guide.md` — NFL (props/CLV/fantasy lean; existing Snowflake data head-start).
- `football/ncaaf/ncaaf_guide.md` — NCAAF (own product = stretch; **NFL feeder = the real value**).
- `basketball/ncaab/ncaab_guide.md` — NCAAB (tempo×efficiency base model; mid-major soft-market seam).

## 6. Shared infrastructure & cost — **lean stack for pre-profit sports**
New sports won't be profitable at launch, so they start on the **cheapest stack that still produces honest product**, and only earn heavier infra once they show traction. Principle: **adding a sport should cost ~$0–5/mo at the margin, not a new stack.**

**Cost reality of the inputs:** the sports *data* is essentially free — `nfl_data_py` (nflverse GitHub releases), CollegeFootballData (CFBD, free), and free/cheap basketball efficiency sources. The only metered feed is **The Odds API**, and it's already paid (5M credits/mo, shared) — multi-sport odds/props/scores fit inside that budget.

### The lean substrate — an AWS **S3 data lake** orchestrated by **Lambda** (the pre-profit stack)
> **Reusable scaffold → `sport_data_platform.md`** has the copy-paste implementation every sport instantiates (ingest Lambda handler, S3 partition writer, per-sport source registry, `dbt-duckdb` profile/sources/models, EventBridge schedule, Dockerfile, migration path). The text below is the *why*; that guide is the *how*.

We already have AWS + S3, so the cheapest *and* cleanest-to-migrate option is a **serverless lakehouse**, entirely inside the AWS footprint we already pay for:
- **Land (S3 data lake):** raw pulls written as **Parquet to S3**, partitioned `s3://<bucket>/<sport>/<source>/season=YYYY/…`. **This S3 lake is the durable substrate** — everything above it is swappable.
- **Orchestrate (Lambda + EventBridge):** each `nfl_data_py` / CFBD / Odds-API pull is a **Lambda** on an **EventBridge cron** (weekly in-season). Pay-per-invocation ≈ ~$0 for weekly jobs; schedules are free; no always-on service, no Dagster+ run-minutes. **Simplest possible orchestration** — and the easiest to port later.
- **Transform / query (DuckDB or Athena over S3):** `dbt-duckdb` reads the S3 Parquet directly for the staging→refined models (free, in-process); **Athena** is the serverless pay-per-query option for ad hoc. No Snowflake warehouse required for a pre-profit sport.
- **Serve:** reuse the existing **Railway PG + Credence app shell** — add per-sport tables/sections; never a request-time warehouse/Athena query on a hot path (precompute, same rule as MLB).

### Migration path to post-profit infra (why pre-profit choices aren't throwaway)
The **S3 Parquet lake stays put**; you swap only the layers above it:
- **Orchestration Lambda → Dagster** — point Dagster ops at the same ingest code / S3 prefixes.
- **Engine DuckDB → Snowflake** — Snowflake external tables or `COPY INTO` from the *same* S3 prefixes; dbt re-targets with minimal model change (the SQL is shared). So the pre-profit stack is just the **lower tier of the eventual stack**, not a rewrite.

### Lambda caveats (size the jobs right)
Lambda is 15-min max + limited memory/ephemeral disk, and `nfl_data_py`+pandas+pyarrow is a chunky dependency → ship it as a **Lambda layer or container image**. **Weekly incremental** pulls fit Lambda easily; run any **one-time full-history backfill** as a one-off container/EC2/local job (not Lambda).

### Per-sport application
- **NFL = brownfield migration onto this stack (first mover, proves the porting story).** The existing `FOOTBALL_DATA` Snowflake data is **stale (untouched a while)**, and `nfl_data_py` is free + re-pullable — so we **re-home, not preserve**: re-point the prior ingestion (notebook `nfl_data_py`→`write_pandas`) to Lambda→S3-Parquet, **re-pull fresh** rather than migrate stale rows, and port the existing dbt models (the real IP — `fct_player_week`, the marts, `mart_projections_preseason`, `dim_nfl_betting`) to **dbt-duckdb over S3**. Snowflake `FOOTBALL_DATA` is kept only as a **reference for the existing model logic**, not the runtime target.
- **NCAAB / NCAAF = greenfield on the same substrate** from day one.
- All three: **weekly batch + incremental** — sidesteps the intraday-frequency / full-rebuild costs that hurt MLB (A2.15/16); keep them batch.

**Guardrail:** carry forward the MLB cost lessons from day one — batch (no intraday), incremental (no full reloads), runaway guards on any new job, and a break-even note before any standing service. Defer scaled/metered infra per sport until it shows traction.

## 7. What "ready by kickoff" honestly means
By each season's start we aim to have: **(1)** the sport's data flowing + a master data inventory, **(2)** honest edge-free surfaces live (parlay calculator, CLV/per-book transparency, fantasy projections), and **(3)** baseline distributional models in shadow. **Validated betting edge is a post-kickoff, gated outcome** — not a launch promise. This keeps the multi-sport expansion fast where it's safe (data + transparency + projections) and disciplined where it's risky (claimed edge).

## 8. Orchestration timing — do NOT wire up recurring schedules until pre-season

The one-time history backfill scripts (`backfill_multisport_odds_to_s3.py`, and future scores/stats ingest scripts) are **run manually once** to populate S3. **No recurring orchestration (Lambda + EventBridge, Dagster) should be set up until ~2–4 weeks before each sport's season starts:**

| Sport | Season start | Wire up orchestration by |
|---|---|---|
| NCAAF | ~late Aug 2026 | ~early Aug 2026 |
| NFL | ~early Sept 2026 | ~mid Aug 2026 |
| NCAAB | ~early Nov 2026 | ~mid Oct 2026 |

**Why:** Standing schedules on pre-season sports cost credits/compute for zero value — there are no games to ingest. The incremental-only ingest scripts are cheap to re-run from scratch at season start given S3 already has the history; a full-history re-pull is never needed again. Set a calendar reminder per sport; do not pre-build cron infrastructure months in advance.
