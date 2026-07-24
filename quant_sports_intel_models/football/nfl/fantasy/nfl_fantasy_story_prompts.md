# NFL Fantasy / Dynasty — Story Prompts (per-vertical catalog)

**Story-ID scheme: `NF<n>` (NFL-Fantasy — parallel to MLB's `F`; distinct from NFL-betting `N…`).** Moved out of the NFL betting catalog (was `N1.3`) 2026-07-22.
**Parent roadmap:** `nfl_fantasy_roadmap.md` · **Betting sibling (builds the SHARED player-week core):** `../nfl_story_prompts.md` (N1.2) · **Rookie feeder:** NCAAF-`P1A` (done) · **Reference:** MLB `../../../baseball/fantasy/` (F-series) + the NFL N-series conventions.
**Conventions:** `uv run python`; DuckDB/S3-native (SF-free); do NOT `git commit`/`push`; honest-analytics framing — this is a PROJECTION product, NO betting-edge claim (`best_alpha` N/A). §0.5 where a predictive model is selected.
🔗 **THE SHARED CORE:** the per-player-week posterior-predictive projection is built in **N1.2 (props)** and consumed here — build once, don't duplicate. NF1 refines it into fantasy points; if NF1 runs before N1.2, IT builds the shared core (coordinate).

---
```
▶ NF1 — WEEKLY + SEASON FANTASY-POINT PROJECTIONS (the core fantasy model)   [Model · 🧭 OPUS · §0.5 · consumes the N1.2 shared player-week core]   (was N1.3; operator-scoped 2026-07)
🟢🟢 **READY-TO-RUN (cleared 2026-07-22) — but see NF-FASTPATH for the NEAR-TERM 8/22 deliverable (that ships first; NF1 is the full refine).**
🎯 WHY: NFL fantasy is the LARGEST fantasy market — season + weekly points projections. Calibrated projections are pure PRODUCT value (edge-independent; the betting efficient-market caveat does NOT apply).
DO: from the SHARED N1.2 per-player-week posterior-predictive projection → fantasy points (weekly + season; **standard + PPR** — the validated N0.3 PPR calc) via opportunity × efficiency × role (`dim_player_role`). §0.5 where a model is selected; posterior-predictive (honest credible intervals, not point estimates). ⚠️ **fantasy points are built off DISCRETE-count props (receptions/TDs) → carry the E2.1-r metric hygiene (PIT flatness, calib_80 as a floor, oracle-check).** State the uncertainty type (parameter vs calibrated). NULL = unknown kept NULL.
GATE/AC: weekly + season fantasy projections (std + PPR) with honest uncertainty; validated vs a HOLDOUT SEASON (behavioral face-validity — do top projected players match actual finishers?); feeds NF2/NF3. Operator handoff + `git add`.
```
```
▶ NF2 — DYNASTY / ROOKIE BOARD (multi-year hold; the differentiator)   [Model/product · 🧭 OPUS · rookie leg needs P1A ✅]   (was N1.3's Dynasty leg)
🎯 WHY: the Dynasty rookie market is priors-only → an honest model-based board is the underserved differentiator (the GTM Dynasty play). Multi-year hold, not single-season.
DO: rank players/prospects for a multi-season hold. ⭐ **THE ROOKIE LEG CONSUMES NCAAF-P1A AS A RESIDUAL ON THE DRAFT SLOT, NOT standalone:** P1A's verdict = college production is real (PBO 0.000/DSR 0.994) but the DRAFT SLOT beats it (0.64 vs 0.79 MAE) → **rank on draft position + the P1A residual (where `projected_nfl_z` [view `ncaaf_nfl_rookie_projections`, keyed `gsis_id`] disagrees with the draft board), NEVER P1A alone** (worse than the draft board). ⭐ trust at SKILL positions (RB/TE/QB/WR); ≈0 for DL/LB/DB; the `sd` is PARAMETER uncertainty → recalibrate before ranking/pricing off it. Veterans (from NF1) + rookies (P1A residual) combine into the board.
GATE/AC: an honest dynasty board (multi-year, uncertainty-aware); rookie leg = draft-slot + P1A-residual (skill positions); face-validity-checked; feeds NF3. Operator handoff + `git add`.
```
```
▶ NF3 — FANTASY APP SURFACES (projections + rankings + dynasty board)   [App · 🧭 frontend · gated on NF1/NF2]
🎯 WHY: surface NF1 projections + the NF2 dynasty board to fantasy users (the paid-tier depth + the content engine).
🚨 APP-TARGET GUARD: UI = `frontend/` (Next.js) ONLY (`cat frontend/package.json` first); backend = `app/backend/`; ⛔ never legacy Streamlit. Honest-uncertainty display (credible intervals). Changelog.
GATE/AC: fantasy projections + rankings + dynasty board in `frontend/`, honest-uncertainty framed; changelog; CI green. Operator handoff + `git add`.
```
```
▶ NF-FASTPATH = ⚡ DRAFT-SEASON MVP-1 — 2026 SEASON PROJECTIONS (the draft-tool content foundation + the operator's 8/22 deliverable)   [Model/product · 🧭 OPUS · ⏰ draft-season · off-box/SF-free/parallel-safe]
✅ **DONE 2026-07-24 (MVP complete)** — `football/nfl/fantasy/{season_projection.py,run_season_projection.py}` + view `mart_nfl_fantasy_season_projection` (tag `nfl_fantasy`) + S3 Delta `nfl/fantasy/derived/season_projections/season=YYYY/` for **8 seasons 2019–2026** (each projected off its own season−1). Veteran = a **3-yr recency+games-weighted** per-game line (0.6^age×games — regresses career/injured years toward the player's own baseline; fixes single-season recency bias that ranked Trevor Lawrence QB2 off a fluke 9-rush-TD 2025 → now QB5) shrunk by sample × an EXPECTED-GAMES role estimate (fixes `mart_projections_preseason`'s backup-QB-at-#1 — Malik Willis was its #1); rookies = draft-slot fp-curve × P1A residual (composite-first, bounded). **🐛 FIXED A SEASON-DATA CORRUPTION first** (see landmine): `dim_player` name-variant dupes fanned `fct_player_week` ×N (Achane 36-game/2× seasons) + the depth-chart-anchored spine dropped the entire 2025 rookie class (Jeanty/Egbuka absent) — cured (dim_player unique on player_id; fct anchored on the box score; guards `assert_nfl_fct_player_week_unique_grain`/`assert_nfl_fct_covers_stat_lines`). Gate MET on CLEAN data: 8-season backtest vs realized `spearman_all` 0.727–0.796 with within-position ρ 0.6–0.8 (QB/RB/WR/TE); face-valid (Josh Allen/CMC/Bijan top; Jeanty now a 2026 vet). vs **The Fantasy Footballers 2025** (top-40/pos, realized): FF still edges within-tier ordering (RB 0.61 vs 0.45, WR 0.29 vs 0.10) — the gap is offseason depth/target info we don't ingest; we win TE + slightly lower MAE. Report: `ablation_results/nf_fastpath_season_projection.md`. **🧬 2025 DEPTH-CHART FEED RESHAPE FIXED (2026-07-24):** the "lake lacks 2025" gap was nflverse RESHAPING the `depth_charts` feed (≤2024 weekly game_type/formation rows → 2025+ daily ESPN `pos_abb`/`pos_rank` snapshots); the old `stg_nfl_depth_charts` silently dropped the whole new schema. Cured — the staging model UNIONs both branches, ASOF-mapping each daily snapshot to its NFL week (self-contained from `stg_nfl_schedules`); ingested `depth_charts` 2025 (856 skill players, was 0; 99.99% of 2025 fct rows now carry a real rank; the **2026 board now uses real current depth** for expected-games). Guard: `assert_nfl_depth_charts_season_coverage.sql`. (`depth_charts_2026.parquet` maps to 0 until the 2026 schedule lands → re-ingest then.) **⏭️ MVP-2/NF-C1 OUTPUT-SCHEMA CONTRACT** (season totals, gsis_id grain): `proj_games`; passing `proj_pass_{att,cmp,yds,td,int}`; rushing `proj_rush_{att,yds,td}`; receiving `proj_{targets,rec,rec_yds,rec_td}`; `proj_fumbles_lost`, `proj_two_pt`(NULL); convenience `proj_fp_{std,half,ppr}` (NF-C1 RESCORES the raw line — do NOT consume these as the league score); uncertainty `fp_ppr_{sd,p10,p90}`, `uncertainty_type`(empirical=vet / parameter=rookie); meta `sport,projection_season,base_season,player_id,player_name,position,team_id,source,is_rookie,draft_overall,confidence,model_version,generated_at`.
🟢🟢 **READY-TO-RUN — this is MVP STEP 1 (see roadmap §2b); the content MVP-2 (config) + MVP-3 (draft optimizer) rank. NOT the full NF1 — a servable first-pass. Fantasy is the prioritized NFL vertical (operator 2026-07-22).**
🎯 GOAL: a first-pass 2026 FULL-SEASON fantasy projection for every draft-relevant NFL player — a **RAW stat-line projection** (passing/rushing/receiving volume + TDs + the components fantasy scoring needs) per player, so MVP-2/NF-C1 can convert it to ANY league's scoring. Ship it ranked + validated.
DO:
 1. Read `nfl_mart_inventory.md` + **`mart_projections_preseason`** (N0.3 ported it + made it DYNAMIC on 2026 data — confirm it populates for 2026 on the real lake). dbt-duckdb over S3, **SF-free** (`-e AWS_DEFAULT_REGION=us-east-2`), OFF the box.
 2. Produce a 2026 season projection per player = the **RAW stat components** (do NOT bake in one league's scoring — emit the raw line so NF-C1 scores it per league). Include **playing-time / games-played expectation** (the hard part — from role/depth-chart) + honest uncertainty where available.
 3. **ROOKIES: attach from NCAAF-P1A** (✅ done — view `ncaaf_nfl_rookie_projections`, keyed `gsis_id`). ⚠️ P1A is a **RESIDUAL ON DRAFT SLOT, not standalone** — rank rookies on draft position + the P1A residual (skill positions RB/TE/QB/WR; ≈0 for DL/LB/DB); recalibrate its parameter `sd`.
 4. **VALIDATE on the real data** (the N0.3 Mahomes-pattern face-validity + a holdout-season sanity check where feasible — do the top projected players look right?) + a **coverage report** (players with projections vs gaps).
 5. Land the projections to S3 (a `fantasy/derived` prefix) + a readable ranked output.
🔒 HONEST FRAME: a PROJECTION product — **edge-independent (NO `best_alpha`/PBO/DSR gate — that's the betting posture)**; the gate here is face-validity + coverage; the full NF1 model refines it later. NULL = unknown kept NULL.
🖥️ CONSTRAINTS: `uv run python`; SF-free/off-box (parallel-safe with E2.5, E7.1, P1.4 — all currently running); do NOT `git commit`/`push` (hand back `git add <paths>`); laptop-vs-box on any command.
GATE/AC: a 2026 raw-stat-line projection per draft-relevant player (+ playing-time + uncertainty), rookies attached via the P1A-residual, validated (face-valid + coverage report), landed to S3 + a ranked output; **ready for MVP-2/NF-C1 to score per league.** Operator handoff + `git add`. ⏭️ its OUTPUT SCHEMA is the input contract for MVP-2 → PM writes MVP-2 (config/scoring) against the actual schema this lands.
```
```
═══════ NF TOOLS LAYER (the Fantasy-Footballers-competitive suite; league-customizable) ═══════
⭐ **SHARED-ENGINE PRINCIPLE (operator 2026-07-22): the tool LOGIC (config schema, draft-optimizer math, trade-value math) is SPORT-AGNOSTIC → build the ENGINE ONCE, instantiate per sport (NFL here + MLB `F-C*`).** The projection INPUTS differ; the optimizer/trade/config logic does NOT — the `hierarchical.py`-style reuse. Competitor bar = The Fantasy Footballers (a full tools suite, not just rankings).
```
```
▶ NF-C0 — ⭐ PLATFORM INTEGRATION / LEAGUE IMPORT (the HARD prerequisite — ingest the user's real league)   [App/backend + infra · 🧭 OPUS · ⏰ draft-season GTM]
🎯 WHY: "customizable by league" is impossible without INGESTING the user's league (rosters + scoring/roster settings + LIVE draft state). Feeds NF-C1 (config) → all tools.
DO: per-platform adapters that import a user's league — **rosters, league settings (scoring + roster slots + size), and live draft state**. **Platforms by 2025 MAU: ESPN 48% · Sleeper 33% · Yahoo 18%** (~99% redraft) + **CBS · MyFantasyLeague (MFL) · Fantrax** (dynasty long-tail) + NFL.com. ⭐ **BUILD ORDER by API-ease × reach (verify current API status live per platform): (1) Sleeper (public read-only API — easiest, #2 reach) + (2) Yahoo (official OAuth API) → (3) ESPN (must-have but UNOFFICIAL/cookie-based/fragile — budget for breakage) → (4) CBS / MFL / Fantrax.** Normalize every platform's league into ONE canonical league-model that NF-C1 scores. ⚠️ credentials/OAuth = operator provisions; honest handling. ⏰ **draft-season MVP: Sleeper+Yahoo+ESPN import is the GTM-timely subset.**
GATE/AC: import a real league (rosters + settings + live draft state) from ≥Sleeper+Yahoo+ESPN into ONE canonical model that NF-C1 consumes; per-platform adapter pattern (add CBS/MFL/Fantrax later); honest auth. Operator handoff + `git add`.
```
```
▶ NF-C1 — ⭐ LEAGUE CONFIGURATION + SCORING ENGINE (the KEYSTONE — build FIRST of the tools)   [App/backend + model glue · 🧭 OPUS · needs NF-C0]
🎯 WHY: every tool must be CUSTOMIZABLE BY LEAGUE. NF1 emits RAW stat-line projections; this converts them to league-specific value.
DO: a league-settings SCHEMA (per-stat scoring, roster/starter slots, league size, PPR variant, superflex, etc.) + a SCORER that maps NF1 raw projections → **league fantasy points + VOR (value-over-replacement) + positional scarcity** for a given config. Persist per-user/per-league configs. ⭐ build the schema + scorer SPORT-AGNOSTIC (MLB `F-C1` reuses it — different stat cats, same engine).
GATE/AC: a league-config schema + scorer that turns raw projections into league-specific points/VOR for arbitrary settings; every downstream tool reads it; sport-agnostic engine. Operator handoff + `git add`.
```
```
▶ NF-C2 — DRAFT OPTIMIZER (⭐ LIVE-draft-aware)   [App/backend + model · 🧭 OPUS · needs NF-C1]
🎯 WHY: the flagship draft tool — the value-maximizing pick given league config + live draft state.
DO: given the NF-C1 league value + the current DRAFT STATE (drafted players, my roster, my slot, roster needs) → the recommended pick(s): VOR-maximizing, positional-need + tier-break aware, with the honest uncertainty. ⭐ **LIVE mode: accept real-time draft-state updates during an actual draft** (fast recompute). Support pre-draft cheat-sheet/tiers too.
GATE/AC: a draft optimizer that recommends picks from league config + live draft state (VOR + need + tiers), fast enough for a live draft; validated on a mock/replayed draft. Operator handoff + `git add`.
```
```
▶ NF-C3 — TRADE CALCULATOR (redraft ROS-value + dynasty multi-year)   [App/backend + model · 🧭 OPUS · needs NF-C1]
🎯 WHY: evaluate a proposed trade in MY league's terms — the Fantasy-Footballers trade-tool analog.
DO: value each side of a trade under the NF-C1 config — **redraft = ROS value (NF1); dynasty = multi-year (NF2/keeper)**. Output "who wins + margin + uncertainty" + roster-context (positional fit before/after). Two modes (redraft/dynasty).
GATE/AC: a trade calculator (redraft + dynasty modes) valuing both sides for a league config with honest uncertainty + roster context. Operator handoff + `git add`.
```
```
▶ NF-C4 — FREE-AGENT / WAIVER RANKINGS (customizable by league ROSTERS)   [App/backend + model · 🧭 OPUS · needs NF-C1]
🎯 WHY: the weekly in-season churn tool — who to add/drop, ranked FOR a given roster (not a generic list).
DO: rank AVAILABLE players (given league rosters — who's rostered vs free) by league-adjusted ROS value RELATIVE to a target roster's needs (positional scarcity, bye/injury gaps). Weekly refresh off the NF1 ROS update.
GATE/AC: roster-aware FA/waiver rankings (league-config + roster-need adjusted), refreshed weekly off NF1's ROS. Operator handoff + `git add`.
```
