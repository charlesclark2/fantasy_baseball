# Multi-Sport Program Roadmap

**Status:** v1.1 — strategy + scaffold; **NCAAF Phase-0 COMPLETE + P1.1 (marts + box job) shipped 2026-07-20; NFL Phase-0 complete**
**Last updated:** 2026-07-20 _(refresh on any material change)_
**Date:** 2026-06-17

> ⏰ **CROSS-SPORT OPS WATCH (PM, from the NCAAF-P1.1 handoff 2026-07-20) — two time-sensitive items that span BOTH football verticals:**
> 1. **Turn the NCAAF + NFL Dagit schedules ON before their openers (NCAAF ~Aug 2026, NFL ~Sep 2026).** Both `sports_*_dbt_build_job` schedules shipped **STOPPED on purpose** (game-day-gated: cron fires daily in-season, the gate skips when no game was played → ~2–3 runs/wk, fails-open, no network IO). ⚠️ **While STOPPED the marts only rebuild on a MANUAL launch — the exact silent-rot this work set out to end** → flip them ON in Dagit before kickoff (recorded in `BOX_OPERATIONS.md §10d`). This is the football analog of the MLB "sensors boot STOPPED = silently never run" class (E11.23).
> 2. **NFL was exposed to a CD-trigger gap (now fixed).** CD didn't fire on `sports_dbt/**` (missing since **N0.3**) → a model-only change would run STALE on the box behind a green run. Fixed, but **any NFL model-only change merged since N0.3 may have silently not deployed** — worth a re-run/verify on the next NFL session. New dbt dirs must be added to the CD path filter; a dbt selector matching nothing exits 0 (CI now asserts non-empty). (Full cross-sport leakage + CI landmines: `sport_data_platform.md`.)

> 🏈 **NCAAF ACTIVE (post-ASB dedicated Opus session; own docs at `football/ncaaf/`).** ✅ **NCAAF-P0.1 DONE 2026-07-13** — `football/ncaaf/ncaaf_data_inventory.md` is the ground-truthed master data file. Headlines: **buy CFBD Patreon Tier-3 ($10/mo — the ONE Phase-0 cost)**; backfill window **2014–2025** (player-advanced is zero pre-2014); ⭐ **the NFL-feeder spine is SOLVED and is NOT an ID join** — CFBD⇄nflverse share no player ID, but the **draft slot `(season, overall pick)` matches 99.7%** to `gsis_id` (so §4's "player-ID xref" is really draft-slot join + UDFA fuzzy-match); **PFF is a licensing project, not a $120 buy** → Tier-A-first is locked. ⚠️ **CROSS-SPORT: the `nfl_data_py` recommendation (this doc §? / `sport_data_platform.md §4/§10`) is STALE — it's abandoned + won't build on py3.12 → use nflverse release Parquet via DuckDB `read_parquet`; also "Railway PG" serving is decommissioned → DynamoDB→S3.** Both corrected in `sport_data_platform.md`'s top banner (affects NFL + NCAAB too). NCAAF status: P0.1/P0.2/P0.3 DONE (data + scaffold + feeder xref); the P1B modeling chain (P1.1 marts → P1.2/P1.2b → P1.3 → P1.4) + P1A feeder + the P0.4/P0.5/P0.6 data adds remain.
> 🏈 **NFL ACTIVATED 2026-07-17 (own docs `football/nfl/nfl_roadmap.md` + `nfl_story_prompts.md`; deadline 9/9).** ⭐ **STRATEGIC (operator): NCAAF > NFL for EDGE** — NFL is the most efficient US market (like MLB; ~17 games/team = tiny samples) → **NFL = product/fantasy/feeder value (props/CLV/fantasy + the NCAAF-fed rookie projections), NOT a head-on edge hunt; keep the EDGE weight on NCAAF's softer college markets.** NFL is a FASTER build (brownfield: the `jaffle_shop/` dbt IP re-homes onto the NCAAF-proven `sports_dbt`/`credence-sports-lakehouse`/Dagster-EC2 stack; nflverse is FREE incl. NGS advanced = $0 new). 🏁 **NFL PHASE 0 COMPLETE 2026-07 (N0.1 data eval → N0.2 scaffold+backfill → N0.3 port the dbt IP → N0.4 Odds/injuries)** — the NFL data foundation is fully built (lake 1999–2025, 14 ported marts incl. the fantasy/betting head-starts, closing lines 2020+ / props 2023+ leakage-safe, injuries). ⏭️ **NEXT = NFL PHASE 1 (honest surfaces by 9/9 — NOT YET SPEC'D):** parlay calculator (E10.1 analog), per-book/CLV transparency (E3), NFL fantasy projections (from `mart_projections_preseason` + the NCAAF-P1A rookie feeder). ⚠️ prop CLV window = 2023–24 only (vendor floor). (Story IDs `N<phase>.<story>` — NFL uses **N**, NCAAF **P**, MLB **E**, so numbers don't collide across sports.)
> ⭐ **OPERATOR DIRECTIVES 2026-07 (apply across the football tracks):** (1) **PRIORITY: finish NCAAF's P0 data ingestion (P0.4 NIL/transfer · P0.5 coaching · P0.6 historical odds) FIRST**, then NCAAF P1.1 marts → the game-model chain; NCAAF (8/29, edge play) is not to be starved by NFL work. (2) **DON'T assume NFL alpha=0** — the MLB "efficient" finding is an informative PRIOR, not a verdict; run the same deflation gate + forward-CLV and let the data decide (a gate-clearing survivor is a REAL edge to ship; look where NFL is SOFTER — thin props, backup-QB games, news-driven line moves). (3) 🎲 **BAYESIAN INFERENCE is a core selling point → every model epic pre-registers a Bayesian/hierarchical candidate (partial pooling, priors, POSTERIOR-predictive distributions + credible intervals)** — consistent with MLB's sequential-Bayes/EB posteriors + NCAAF-P1.2's mixed-effects; the honest-uncertainty product framing holds regardless of which model wins the metric. (4) ⏰ **NICE-TO-HAVE: 2026 fantasy SEASON projections by 8/22 (operator draft) via the FAST-PATH** — the N0.3-ported `mart_projections_preseason` (dynamic, vets) + NCAAF-P1A rookies (P1A serves BOTH the NCAAF value AND the rookie leg → does NOT delay NCAAF). ⚠️ CORRECTED the guide's stale `nfl_data_py`→nflverse-parquet + Lambda→Dagster-EC2. **Deadline risk: NFL from ~zero to ready by 9/9 → start the P0 port NOW, parallel to NCAAF.**
**Purpose:** how we extend the platform beyond MLB to **NFL, NCAA Basketball (NCAAB), and NCAA Football (NCAAF)** for the fall-2026 seasons — without rebuilding the methodology each time.

---

## 1. The model: one playbook, many sports
The MLB work produced two reusable, **sport-agnostic** asset classes:
- **The Edge methodology** (`baseball/edge_program/`): overfitting-audited CV (E1: purged CV, PBO, deflated Sharpe), per-side distributional modeling (E2), closing-line/CLV (E3), cross-book sharp-anchor (E4), player props (E5), parlay (E10), plus the shared conventions (market-blind, app-session handoff, cost playbook).
- **The Fantasy/Dynasty vertical** (`baseball/fantasy/` — ✅ STOOD UP 2026-07-22: `fantasy_roadmap.md` + `fantasy_story_prompts.md` [F1–F5]): distributional player projections + aging/keeper + the Dynasty prospect board, built on the E7 MiLB→MLB translation (the moat). A distinct PRODUCT LINE (own users/revenue/GTM — the named GTM LEAD), organized STRUCTURALLY BY SPORT under `baseball/`, sibling to `edge_program/` (betting). **🗂️ ORGANIZING PRINCIPLE (operator 2026-07-22): group by SPORT, not by product line** — each sport folder holds ALL its verticals (MLB betting=`edge_program/` + fantasy=`fantasy/`; NFL betting=N1.1/N1.2 + fantasy=N1.3, both under `football/nfl/`; the E7 MiLB data dual-serves betting + fantasy so it stays in `edge_program/`). Closes the prior chasm (NFL fantasy was bundled with its sport; MLB fantasy was homeless).

**New sports instantiate these patterns; they do not reinvent them.** Each new sport's guide *cites the MLB guides as the reference implementation*. The per-sport lift is **(a) data ingestion + a sport-specific base distributional model**; the market/CLV/sharp-anchor/parlay/fantasy layers largely transfer (The Odds API covers NFL/NCAAF/NCAAB odds, props, and scores).

## 2. Repo structure (per-sport folders)
```
quant_sports_intel_models/
  baseball/        ← MLB (reference implementation): edge_program/, fantasy/, baseball_data_mart_inventory.md
  football/
    nfl/           ← nfl_guide.md, nfl_data_inventory.md, nfl_story_prompts.md (betting: N-series) + ✅ nfl/fantasy/ (NF-series — split out 2026-07-22)
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

> ⏰⏰ **AUG-1 OVERRIDE — THE PAID-FUNNEL SPRINT IS #1, AHEAD OF ALL MLB WORK (operator 2026-07-24):** GTM execution starts Aug 1 → the **E9.7 (self-serve signup) → E9.19 (MFA) → E9.8 (Stripe, live-mode, $10 founding / $20 after)** sprint jumps AHEAD OF ANY MLB work (E2.5/E2.6/E7 all wait behind it). App-track, independent of the model sessions → runs in parallel; each a fresh app session (E9.7 ∥ E9.19 → E9.8). **NCAAF + NFL tracks KEEP PUSHING** (they're not app-track — no conflict). So: paid funnel #1 → NCAAF (P0.7 data readiness, 8/29) + NFL fantasy (MVP-2→MVP-3, NF-D) continue in their own sessions → MLB resumes AFTER the funnel ships. See `gtm_strategy.md` EXECUTION PIVOT.
> 🎯🎯 **CURRENT STRATEGIC SEQUENCING (operator 2026-07-22 — this is the source-of-truth priority; supersedes the earlier all-three framing below where they conflict):**
> - **MLB — CONTINUE the E2 epic to close (E2.5 register → E2.6 F5-close eval + the totals-serving/E13.6b resolution), THEN SHIFT MLB focus to FANTASY BASEBALL** (the `baseball/fantasy/` F-series — redraft-first per the mass-market; the Dynasty branch gates on E7 MiLB data, E7.1 in flight).
> - **NCAAF — STRICTLY A BETTING surface; keep pushing it as a vertical** (P1.4 game-model → P1.5 futures → Phase-2; 8/29 deadline). No NCAAF fantasy product. (It still doubles as the NFL rookie feeder — P1A, done.)
> - **NFL — ensure a PROJECTIONS BASIS that serves BOTH props (betting) AND fantasy, but PRIORITIZE FANTASY over the betting surfaces** (the fantasy market is about to get HOT — draft season Aug–early-Sept). ⇒ build the shared per-player-week projection as a FOUNDATION that FANTASY (NF1) drives + platform integration (NF-C0) + config (NF-C1) + draft optimizer (NF-C2) for the draft-season GTM; N1.1 game-line + N1.2 props-pricing come AFTER. The projection basis is shared, so betting isn't abandoned — just sequenced behind fantasy.
> ⇒ **Cross-vertical order of effort:** NCAAF betting (8/29, in flight) + MLB E2-close run in parallel with their own sessions; NFL fantasy MVP is the hot near-term GTM push; MLB fantasy + NFL betting + NCAAB follow.

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
