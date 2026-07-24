# MLB Fantasy / Dynasty — Story Prompts (per-vertical catalog)

**Story-ID scheme: `F<n>` (F = MLB Fantasy/Dynasty — distinct from Edge `E…`, NCAAF `P…`, NFL `N…`).**
**Parent roadmap:** `fantasy_roadmap.md` · **Guide:** `fantasy_dynasty_guide.md` · **DATA foundation (dual-served, in the betting catalog):** `../edge_program/story_prompts.md` (the E7 chain) · **Reference impl:** MLB Edge `../edge_program/` + NCAAF-P1.2b/P1A (the proven feeder-MLE siblings) + NFL-N1.3 (the fantasy sibling under its sport).
**Conventions:** `uv run python`; DuckDB/S3-native (SF-free); do NOT `git commit`/`push` (operator does git — provide `git add`); honest-analytics framing (this is a PROJECTION product — NO betting-edge claim; `best_alpha` is N/A here). §0.5 bake-off discipline applies to any predictive model.
🔒 **GATES:** Branch B (Dynasty: F2–F4-prospect) depends on the E7 DATA foundation + E7.3 MLE (E7.1 in flight 2026-07-22). **Branch A (Redraft/Seasonal: F1) does NOT need E7** — it's current-MLB-player projections off the existing MLB data + the served projection machinery, so it's the more NEAR-TERM-runnable branch.

---
```
▶ F1 — ⭐ SEASONAL MLB PLAYER FANTASY PROJECTIONS (PRE-SEASON + WEEKLY REST-OF-SEASON) — the redraft foundation   [Model · 🧭 OPUS · 🔬 §0.5 · the mass-market core; the Dynasty branch extends it]   (operator 2026-07-22 — the in-season projection need)
🎯 WHY: the bread-and-butter fantasy product + the FOUNDATION Dynasty (F4 keeper) builds on. Operator's requirement: **not just pre-season — WEEKLY-UPDATING projections that power free-agent/waiver identification, drafts, trade evaluation, and start/sit.**
DO: a FULL fantasy stat-line projection per MLB player — **batting** (the roto cats AVG/HR/RBI/R/SB or points-league equiv) + **pitching** (W/K/ERA/WHIP/SV or points + role/save-share) + **playing-time / role** (the hard part — PA/IP projection from depth-chart/usage). Produce it in TWO modes: **(a) PRE-SEASON** (from prior seasons + AGING curves + role/depth-chart — the draft-day projection) and **(b) WEEKLY IN-SEASON REST-OF-SEASON (ROS)** — ⭐ **Bayesian by construction: the pre-season projection is the PRIOR, weekly-observed performance UPDATES it → the ROS posterior-predictive for the remaining schedule** (reuse the program's sequential-Bayes / EB-posterior machinery + `hierarchical.py`; a hot/cold streak shrinks toward the prior by sample size — the structurally-right tool). §0.5 bake-off where a component model is selected; honest credible intervals (not false-precise points). Share the per-player distributional-projection machinery with the betting E5 props (pitcher-K) where it overlaps. Leakage-safe (as-of each week — never fold post-week into the ROS-as-of row). ⚠️ this is a SERVING product on a WEEKLY cadence → the update job design matters (like the MLB daily pipeline, but weekly for fantasy).
🎯 THE USE CASES IT MUST SERVE (state each is answerable): FREE AGENTS (ROS value of an available player vs the roster), DRAFTS (pre-season ranks + tiers), TRADES (ROS value compare across players), START/SIT (weekly matchup-adjusted). These are the derived rankings F5 surfaces.
GATE/AC: pre-season + weekly-ROS player projections (full stat line + playing time + honest uncertainty), calibration-validated on a holdout season (does a player projected at X produce ~X ROS); the 4 use-case rankings derivable; the weekly-update job specified; feeds F4 (keeper = F1 + aging) + F5/F6. Operator handoff + `git add`.
```
```
▶ F2 — PROSPECT DYNASTY PROJECTION MODEL (Dynasty branch — consumes the E7.3 MLE)   [Model · 🧭 OPUS · 🔬 §0.5 · gated on E7.3]
🎯 WHY: the Dynasty moat = a MULTI-YEAR MLB-equivalent projection + ETA for a prospect the market prices on priors only. Built on the E7.3 minor→major translation (the MLE).
DO: from the E7.3 per-player MLB-equivalent line + the E7.4 prospect dimension (age/level/ETA), project a prospect's MULTI-SEASON MLB production trajectory (not single-season) + honest uncertainty. §0.5 bake-off ≥3 candidates + a foil — ⭐ REUSE `hierarchical.py` (partial-pool prospect within level/age/position, thin-rep shrinkage — the P1.2b/P1A pattern) + a stratified-regression foil + a GBM + a naive-MLE-carry null. Select on a GRADUATED-PROSPECT holdout (pre-MLB projection vs realized MLB outcome), calibration-gated. Inherit the feeder-MLE lessons: EB variance-collapse cure (boundary-avoiding Gamma prior + multi-start + pin test); state UNCERTAINTY type (parameter vs calibrated — F3/F4 recalibrate if ranking off intervals); verify every join on the real lake (the P1.2b dead-bridge check); expect ROBUST-BUT-MODEST + that's valid (the market is priors-only). HONEST: a projection + credible interval, NOT an edge claim.
GATE/AC: a validated multi-year prospect projection (mean + ETA + uncertainty), calibration-checked on a graduated-prospect holdout; position/level-aware; feeds F3/F4. Operator handoff + `git add`.
```
```
▶ F3 — DYNASTY PROSPECT BOARD / RANKINGS (the differentiator surface)   [Model/product · 🧭 OPUS · gated on F2]
🎯 WHY: the underserved product — rank prospects by projected MULTI-YEAR value + ETA + risk, honestly. Most competitors don't do the MiLB→MLB translation; this is the moat made visible.
DO: rank prospects from F2's projections in a DYNASTY context (multi-season hold) — value × ETA × risk; surface the honest uncertainty per prospect. Position-tiered; dynasty-league-format-aware where feasible.
GATE/AC: an honest dynasty prospect board (ranked, with uncertainty + ETA), face-validity-checked; feeds F5/F6. Operator handoff + `git add`.
```
```
▶ F4 — KEEPER / DYNASTY PLAYER VALUATIONS (current MLB players, multi-year = F1 + aging)   [Model/product · 🧭 OPUS · gated on F1]
🎯 WHY: dynasty/keeper decisions value a player over MULTIPLE seasons — age curves, years of control, not just current-season points. The multi-year EXTENSION of the F1 seasonal projection (+ the F3 prospects = the full keeper roster).
DO: extend the F1 seasonal projection into a MULTI-YEAR valuation via AGE CURVES + control window. Honest uncertainty (widening with the horizon).
GATE/AC: multi-year keeper valuations for current MLB players (age-adjusted, uncertainty-aware, horizon-widening); feeds F5/F6. Operator handoff + `git add`.
```
```
▶ F5 — FANTASY APP SURFACES (redraft tools + dynasty board)   [App · 🧭 frontend · gated on F1–F4]
🎯 WHY: surface F1 (seasonal projections + FA/draft/trade/start-sit tools) + F3 (dynasty board) + F4 (keeper valuations) to users. The paid-tier depth (`gtm_strategy.md`).
🚨 APP-TARGET GUARD: UI = `frontend/` (Next.js) ONLY (`cat frontend/package.json` first); backend = `app/backend/`; ⛔ never legacy Streamlit. Honest-uncertainty display (credible intervals, not false-precise points). Changelog.
GATE/AC: seasonal projections + FA/draft/trade tools + the dynasty board + keeper valuations in `frontend/`, honest-uncertainty framed; changelog; CI green. Operator handoff + `git add`.
```
```
▶ F6 — CONTENT / RANKINGS ENGINE (the GTM acquisition play)   [Product/content · 🧭 GTM]
🎯 WHY: seasonal rankings + prospect/dynasty rankings are high-search evergreen SEO — the acquisition engine `gtm_strategy.md` leans on. Ad-policy-safe, honest-brand-consistent.
DO: turn F1 (seasonal ranks) + F3 (dynasty board) into publishable rankings content (evergreen, updated on the data cadence — the weekly ROS refresh feeds in-season content too). Honest, methodology-transparent. Coordinate with `gtm_strategy.md §content`.
GATE/AC: a repeatable rankings content surface fed by F1/F3; honest + methodology-linked. Operator handoff.
```
```
═══════ F TOOLS LAYER (league-customizable; the ENGINE is SHARED with `football/nfl/fantasy/` NF-C*) ═══════
⭐ **SHARED-ENGINE PRINCIPLE (operator 2026-07-22): the tool LOGIC (config schema, draft-optimizer math, trade-value math) is SPORT-AGNOSTIC → build the ENGINE ONCE, instantiate per sport.** Projection INPUTS differ (MLB roto/points cats vs NFL); the optimizer/trade/config logic does NOT (`hierarchical.py`-style reuse). Whoever builds one sport's tool ships the shared engine + the sport instantiation; the other sport reuses.
```
```
▶ F-C0 — ⭐ PLATFORM INTEGRATION / LEAGUE IMPORT (the HARD prerequisite — ingest the user's real league)   [App/backend + infra · 🧭 OPUS]
🎯 WHY: "customizable by league" is impossible without INGESTING the user's league (rosters + scoring/roster settings + draft state). Feeds F-C1 (config) → all tools. ⭐ **SHARES the canonical league-model + adapter framework with NFL `NF-C0` — build once, add sport-specific platforms.**
DO: per-platform adapters importing a user's baseball league. ⚠️ **CORRECTED/COMPLETED PLATFORM LIST (operator listed ESPN/Yahoo/CBS — these were MISSING and matter, esp. for the DYNASTY differentiator): Yahoo · ESPN · CBS Sports (the big-3 redraft) + ⭐ Fantrax (THE dynasty/deep-league leader — critical since dynasty is our differentiator) + NFBC (high-stakes redraft/roto) + Ottoneu (salary-cap dynasty/keeper — dedicated serious users) + Fleaflicker (free/deep).** ⭐ **BUILD ORDER by API-ease × reach (verify current API status live): Yahoo (official OAuth) + Fantrax (has an API; owns dynasty) first → ESPN (unofficial/cookie/fragile) → CBS → NFBC/Ottoneu (harder/limited APIs).** Normalize into ONE canonical league-model F-C1 scores. Credentials = operator-provisioned.
GATE/AC: import a real baseball league (rosters + settings) from ≥Yahoo+ESPN+Fantrax into the canonical model F-C1 consumes; per-platform adapter pattern; honest auth. Operator handoff + `git add`.
```
```
▶ F-C1 — ⭐ LEAGUE CONFIGURATION + SCORING ENGINE (the KEYSTONE — build FIRST of the tools)   [App/backend + model glue · 🧭 OPUS · needs F-C0]
🎯 WHY: every tool must be CUSTOMIZABLE BY LEAGUE. F1 emits RAW stat-line projections; this converts them to league-specific value.
DO: a league-settings SCHEMA (per-stat scoring, roster/starter slots, league size, roto-vs-points, keeper depth) + a SCORER mapping F1 raw projections → **league fantasy value + VOR + positional scarcity**. Persist per-user/per-league configs. ⭐ build sport-agnostic (NFL `NF-C1` reuses it — MLB roto/points cats vs NFL, same engine).
GATE/AC: a league-config schema + scorer turning raw projections into league-specific value/VOR for arbitrary settings; every downstream tool reads it; sport-agnostic engine. Operator handoff + `git add`.
```
```
▶ F-C2 — DRAFT OPTIMIZER (⭐ LIVE-draft-aware)   [App/backend + model · 🧭 OPUS · needs F-C1]
🎯 WHY: value-maximizing pick given league config + live draft state (the flagship draft tool).
DO: given F-C1 league value + current DRAFT STATE (drafted, my roster, my slot, needs) → recommended pick(s): VOR-maximizing, positional-need + tier-break aware, honest uncertainty. ⭐ LIVE mode (real-time state during a draft, fast recompute) + a pre-draft cheat-sheet/tiers.
GATE/AC: a draft optimizer recommending picks from league config + live draft state, live-draft-fast; validated on a replayed draft. Operator handoff + `git add`.
```
```
▶ F-C3 — TRADE CALCULATOR (redraft ROS-value + dynasty multi-year)   [App/backend + model · 🧭 OPUS · needs F-C1]
🎯 WHY: evaluate a trade in MY league's terms.
DO: value each side under F-C1 — **redraft = F1 ROS value; dynasty = F4 keeper/multi-year**. Output who-wins + margin + uncertainty + roster fit before/after. Two modes.
GATE/AC: a trade calculator (redraft + dynasty) valuing both sides for a league config with honest uncertainty + roster context. Operator handoff + `git add`.
```
```
▶ F-C4 — FREE-AGENT / WAIVER RANKINGS (customizable by league ROSTERS)   [App/backend + model · 🧭 OPUS · needs F-C1]
🎯 WHY: the weekly in-season churn tool — who to add/drop FOR a given roster.
DO: rank AVAILABLE players (given league rosters — rostered vs free) by league-adjusted ROS value RELATIVE to a target roster's needs (positional scarcity, IL/injury gaps). Weekly refresh off F1's ROS.
GATE/AC: roster-aware FA/waiver rankings (league-config + roster-need adjusted), refreshed weekly off F1's ROS. Operator handoff + `git add`.
```
