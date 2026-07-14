# NCAAF — Roadmap (per-sport, its own doc)

**Status:** v0.1 — activated 2026-07-08 (operator: each sport gets its OWN roadmap + prompts). Kickoff at the MLB All-Star break; NCAAF season opens ~late-Aug 2026.
**Parents:** `../../multi_sport_roadmap.md` (program-level) · `../../sport_data_platform.md` (the shared lean lakehouse — INSTANTIATE it, don't reinvent) · MLB `../../baseball/edge_program/` (the reference implementation).
**Sibling docs (this folder):** `ncaaf_guide.md` (the methodology stub) · `ncaaf_story_prompts.md` (the runnable prompts) · `ncaaf_data_inventory.md` (**to be created by Phase 0** — the master data file).

> **Session model (operator 2026-07-08):** post-ASB the two concurrent Opus sessions split — **1 baseball (continuation) + 1 DEDICATED NCAAF.** This doc + `ncaaf_story_prompts.md` drive the NCAAF session.

---

## 0. The two value cases (why NCAAF is in scope — read first)
1. **NCAAF's own betting/analytics product — a STRETCH** on the fall timeline (huge talent disparity, scheme/pace variance, but *soft markets on smaller programs* = where a real edge is most plausible). Phase it; don't over-invest before it earns.
2. **The NFL FEEDER — the real near-term value.** College production + combine/draft data → **college→NFL translation factors** → NFL rookie projections (fantasy-dynasty + rookie props where the market is otherwise priors-only). This is the football analog of MLB's MiLB→MLB MLEs (Edge **E7**). ⇒ **NCAAF *data* + the translation model are worth building even if NCAAF *betting* slips.** Data-first is the right posture either way.

## 1. Platform (instantiate, don't reinvent)
Follow `../../sport_data_platform.md`: free APIs → **Lambda + EventBridge cron → S3 Parquet lake** (`s3://<bucket>/ncaaf/raw/<source>/season=YYYY/…`) → **`dbt-duckdb` over S3** (staging→marts) → serving.
- ⚠️ **STALENESS FIX (the platform doc predates INC-16):** it says "serve on Railway PG" — **Railway is DECOMMISSIONED.** NCAAF serves on the CURRENT stack: **DynamoDB (primary) → S3 (fallback)**, same as MLB post-decommission. Do NOT stand up Railway.
- ⭐ **NCAAF inherits E11.20's platform choices** (Delta-on-path + Polars + the decomposed/incremental build + retention discipline) — this is the "get it right ONCE before the ×3 scale-out" payoff. Weekly-batch cadence ⇒ naturally cheap.

## 2. 🎯 DATA — exactly what we're looking for (the crux; drives Phase 0)
**Minimum bar = full box scores (team + per-player game logs). Reach = position-level ADVANCED metrics.** The honest availability map (grounds the Phase-0 source decision):

**Tier A — FREE / near-free via CFBD (CollegeFootballData; free tier 1,000 calls/mo, or Patreon Tier-3 ~$10/mo for 75k calls + GraphQL + live):** box scores (team + player), **play-by-play** (→ derive EPA/play, success rate, explosiveness, usage/share ourselves), advanced **TEAM** metrics (SP+, havoc rate, line-yards, stuff rate, sack rate, finishing/field-position), rosters, **recruiting/talent ratings**, results/schedule. **The Odds API** covers NCAAF game lines + props + scores. ⇒ this alone gets us box scores + team-advanced + PBP-derived player-advanced.

**Tier B — PAID charting (PFF College, or Sports Info Solutions):** the individual GRADES + tracking we can't derive from PBP — OL pass-block/run-block grades & pressures allowed, DB coverage grades & completion/passer-rating-allowed, WR separation & yards-per-route-run & contested-catch, RB yards-after-contact & forced missed tackles, QB CPOE/air-yards/time-to-throw. **This is the "incredibly useful if available" tier.** Decision (Phase 0): is the PFF College cost justified pre-profit, or do we ship on Tier-A + PBP-derived proxies first and add PFF only if the model earns it? (Default lean: Tier-A first; PFF is a later, edge-gated buy.)

**By position — the wishlist (✅ Tier-A derivable · 💰 Tier-B/PFF · ⛔ genuine gap):**
- **QB:** box (cmp/att/yds/TD/INT/sacks/rush) ✅ · EPA/play, success rate, pressure→sack (team-derived) ✅ · CPOE, air yards/ADOT, time-to-throw, big-time-throw/TWP grades 💰
- **RB:** box (rush/rec lines, fumbles) ✅ · EPA/rush, success rate, explosive-run rate, stuff rate, snap/usage share ✅ · yards-after-contact, forced missed tackles, YPRR 💰
- **WR/TE:** box (rec/yds/TD) ✅ · **targets ⇒ target share** ✅ (⚠️ *not* in the box score — only via CFBD `/plays/stats` `statType='Target'`, 2013+) · EPA/target ✅ · **aDOT 💰** (⚠️ **corrected by P0.1**: air yards are NOT charted free anywhere — this was listed ✅-from-PBP and is actually PFF-only) · separation, YAC over expected, contested-catch %, yards-per-route-run, drop rate 💰
- **OL (linemen):** ⛔ **the hardest gap — NO free individual-OL production exists anywhere.** TEAM proxies ✅ (line yards, stuff rate, sack rate allowed, havoc allowed, adjusted-line-yards) · individual pass-block win rate / pressures-allowed / run-block grades 💰 (PFF only). ⇒ model OL at the UNIT level from Tier-A; individual OL is a PFF-gated reach.
- **Defense:** team (havoc, stuff rate, PPA/EPA & success allowed, explosiveness allowed) ✅ · individual box (tackles/TFL/sacks/QB-hurries/INT/PBU/FF) ✅ · individual pressure rate, pass-rush win rate, coverage grade / completion & passer-rating allowed in coverage, missed-tackle rate 💰

**⇒ Phase-0 conclusion to reach (not assume):** Tier-A (CFBD + Odds API) delivers box scores + team-advanced + PBP-derived player metrics for QB/RB/WR/TE/DEF at $0–$10/mo; **OL-individual + all position grades are PFF-paid** — decide the buy after the Tier-A model exists. Ground every "available/derivable" claim against the live CFBD v2 endpoints (the free tier's 1,000-call cap likely forces the $10 Patreon tier for a multi-season backfill — a Phase-0 cost call).

> ### ✅ RESOLVED by **NCAAF-P0.1** (2026-07-13) — see **`ncaaf_data_inventory.md`** (the master data file; every claim ground-truthed on live endpoints)
> The conclusion above **held**, with four corrections that change downstream work:
> 1. **BUY CFBD Patreon Tier 3 — $10/mo, 75k calls.** The free tier's 1,000/mo cap is **confirmed live** (the `X-Calllimit-Remaining` response header). The backfill needs **~15,800 calls**; Tier 3 clears it in one month with ~5× headroom. **The only Phase-0 cost.**
> 2. **⚠️ Player-advanced data starts 2014, not 2004** (`/ppa/players/games` and `/plays/stats` return **zero** before 2013/14). Team/box/PBP reach back to 2004. **⇒ backfill window = 2014–2025.**
> 3. **⚠️ aDOT / air yards / CPOE are NOT free** (corrected above). **Snap counts have no college equivalent** (proxy = `/player/usage`). The **OL-individual gap is CONFIRMED** — `/games/players` has no OL category at all.
> 4. **⭐ The NFL-feeder spine is solved and is NOT an ID join** — CFBD and nflverse share **no player ID**. The **draft slot `(season, overall pick)`** is deterministic: **99.7% of CFBD draft picks (2015–25) resolve to an NFL `gsis_id`**. P0.3 is now a much smaller job (fuzzy matching only for UDFAs).
>
> Odds API covers NCAAF fully (11 books incl. **Bovada**; h2h/spreads/totals; **historical floor 2020**; props exist but are **thin** — marquee games/top players only). **PFF is not even a clean buy:** its $119.99/yr product is a **website subscription, not an API/bulk licence** — so it's an edge-gated *licensing* project, never a Phase-0 line item.

## 3. Phased plan
- **Phase 0 — DATA (start here):** evaluate + lock the sources (CFBD tier decision, Odds API NCAAF, draft/combine) → build `ncaaf_data_inventory.md` (every source → endpoint → fields → the by-position coverage map above, marking ✅/💰/⛔) + the **college↔NFL player-ID xref** (the spine of the feeder) + the lean-lakehouse scaffold (`ingest/` per `sport_data_platform.md §2`). *(prompts: P0.1 sources+inventory, P0.2 scaffold, P0.3 xref)*
- **Phase 1 — honest surfaces:** ⭐ the **college→NFL feeder** (E7 analog: college production + combine → NFL rookie projections; highest ROI, feeds the NFL vertical) FIRST; then (optional/stretch) an NCAAF honest-analytics surface — the E10.1 parlay CALCULATOR + CLV transparency (these transfer directly from MLB, no new modeling).
- **Phase 2 — gated edge (post-kickoff, optional):** NCAAF sharp-anchor / totals / props under the SAME deflation gate as MLB (**PBO<0.2, DSR≥0.95, FDR**; game-level correlated-quote collapse). ⭐ this is where MLB's now-hardened instruments earn out.

## 4. ⭐ Why NCAAF is where the closed-MLB tools get their real test
MLB returned **9 mechanism nulls** (H2H, totals, props, derivatives, cross-market, microstructure, 6 model classes) *because MLB main markets are efficient*. **College markets are thinner + softer-lined** → the weaker-efficiency prior where an edge is actually plausible. Re-point the hardened, deflation-honest MLB instruments here:
- **E13.16 microstructure/CLV harness** (leakage guard + stale-quote control + working negative control + realized-ROI) → NCAAF line movement, esp. smaller programs.
- **E1.12 regime-conditioning** → talent-mismatch regimes (huge in CFB) are a natural specialization axis.
- **E13.14 cross-market** → sides↔totals↔props constellation on softer lines.
All under the same PBO/DSR/FDR deflation — the clock must NOT manufacture a mirage (the MLB discipline transfers wholesale).

## 5. Cost posture (pre-profit)
CFBD $0 (free tier) → ~$10/mo (Patreon Tier-3, likely needed for the backfill) · Odds API (existing sub) · PFF College = a LATER edge-gated buy, not a Phase-0 cost · compute = Lambda + DuckDB-over-S3 (pennies) + the existing AWS box/S3. No new Snowflake. Weekly in-season cadence keeps it cheap.

## 6. Timeline
- **Now → ASB:** Phase 0 prompts ready (this doc + `ncaaf_story_prompts.md`); the dedicated NCAAF session starts at the ASB.
- **ASB → late-Aug:** Phase 0 data + scaffold + the feeder xref land; Phase 1 feeder projections.
- **Season (late-Aug on):** honest surfaces live; Phase 2 edge gated + optional.

---
_Data-source facts current as of 2026-07-08. Phase 0 re-verifies against live CFBD v2 endpoints before committing._
