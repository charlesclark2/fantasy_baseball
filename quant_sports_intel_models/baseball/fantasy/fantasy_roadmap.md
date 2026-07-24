# MLB Fantasy / Dynasty — Roadmap (the baseball fantasy vertical)

**Status:** v0.1 — created 2026-07-22 (operator: Dynasty is a distinct PRODUCT LINE, but organize STRUCTURALLY BY SPORT). This is MLB's fantasy/dynasty vertical.
**Parents:** `../../gtm_strategy.md` (Dynasty = the named LEAD segment / "GTM dark horse") · `../edge_program/` (the MLB BETTING sibling under the same `baseball/` sport umbrella; the E7 MiLB DATA foundation lives there) · `../../multi_sport_roadmap.md` (program-level).
**Sibling docs (this folder):** `fantasy_story_prompts.md` (the runnable F-series prompts) · `fantasy_dynasty_guide.md` (methodology — the MiLB→MLB translation + dynasty valuation approach).

---

## 0. Structural principle (why this doc exists — read first)
🗂️ **ORGANIZE BY SPORT, not by product line (operator 2026-07-22).** Each sport folder holds ALL its verticals:
- **MLB** (`baseball/`): betting = `edge_program/` · **fantasy/dynasty = `fantasy/` (THIS doc)** · shared MiLB DATA = the E7 chain in `edge_program/` (it dual-serves — the betting rookie prior [E7.5] AND this vertical).
- **NFL** (`football/nfl/`): betting = N1.1/N1.2 · fantasy/dynasty = **N1.3** (already grouped under the sport — the model this vertical mirrors) · the college→NFL rookie feeder = NCAAF-**P1A** (done).
- **NCAAF** (`football/ncaaf/`): the game model + the P1A feeder (no standalone college-fantasy product).

⇒ The prior "chasm" (NFL fantasy bundled with NFL, MLB fantasy homeless) is closed by adding THIS home. Dynasty is a distinct *product* (own users, own revenue, own GTM), grouped *structurally* with its sport.

## 1. Strategic frame (from `gtm_strategy.md` — Dynasty is the GTM LEAD)
- **The genuinely underserved, defensible product.** Dynasty/keeper baseball players have high willingness-to-pay for prospect projections + rankings, and most competitors skip the hard part — the **MiLB→MLB translation moat**.
- **Edge-INDEPENDENT.** Unlike the betting product, Dynasty needs NO market edge — it's a projection product. `best_alpha=0` is irrelevant here; the value is projection QUALITY + honest uncertainty + the underserved-market positioning.
- **Year-round + content-rich.** The retention/differentiation engine that carries the MLB offseason; dynasty prospect rankings + rookie projections are high-search evergreen SEO (the acquisition play, `gtm_strategy.md §content`).
- **Honest-analytics consistent.** Same posture as the betting side: calibrated projections + honest credible intervals ("here's our read AND how sure we are"), Bayesian/partial-pooling where the sample is thin (prospects with few pro reps — the structurally-right tool, mirrors the MLB EB posteriors + NCAAF-P1.2).

## 2. The DATA foundation (already articulated — in `edge_program/`, dual-serving)
The enabling data + translation layer is the **E7 chain** (lives in the MLB betting catalog because it ALSO feeds the betting rookie prior; do NOT duplicate it here — consume it):
- **E7.1** MiLB game-log/box ingestion (→ S3 lakehouse) — 🟢 IN FLIGHT 2026-07-22.
- **E7.2** AAA Statcast (Hawk-Eye 2023+).
- **E7.3** ⭐ Minor→major translation factors (MLEs) — THE crux; the MiLB→MLB moat; the model this vertical's projections are built on.
- **E7.4** Prospect identity & ETA xref (→ the prospect dimension).
- **E7.5** Wire MiLB priors into the EB posteriors (the betting-side payoff; shares the MLE).
- **E7.6** Coverage / SLA / leakage screen.
⇒ **This vertical's F-series modeling GATES on the E7 data + the E7.3 MLE landing.** Until then, these F-stories are spec-ready but not runnable.

## 3. Phased plan — TWO BRANCHES on a shared player-projection core (F-series)
The fantasy product has two markets on ONE foundation: **REDRAFT/seasonal** (the mass market — pre-season + WEEKLY updates) and **DYNASTY** (the underserved differentiator — prospects + multi-year). The **seasonal player projection (F1) is the foundation**; Dynasty extends it (multi-year aging + prospects).

**BRANCH A — REDRAFT / SEASONAL (the mass-market foundation):**
- **F1 — ⭐ SEASONAL MLB PLAYER FANTASY PROJECTIONS (PRE-SEASON + WEEKLY REST-OF-SEASON):** a FULL fantasy stat-line projection per player (batting: the roto/points categories — AVG/HR/RBI/R/SB or points; pitching: W/K/ERA/WHIP/SV or points + role/saves), produced **PRE-SEASON** (prior seasons + aging + role/depth-chart) AND **UPDATED WEEKLY IN-SEASON** — ⭐ **Bayesian by construction: the pre-season projection is the PRIOR, weekly observed performance UPDATES it → a rest-of-season (ROS) posterior-predictive** (reuses the program's sequential-Bayes/EB machinery). ⇒ powers the in-season USE CASES **operator called out: free-agent/waiver identification, drafts (pre-season ranks), trade evaluation (ROS value compare), start/sit.** §0.5 where a model is selected; honest credible intervals. Shares the per-player distributional-projection machinery with the betting E5 props (pitcher-K) where applicable.
- (F1 IS the redraft product: the projections + the derived FA/draft/trade rankings are surfaced via F5/F6.)

**BRANCH B — DYNASTY (the differentiator; extends F1):**
- **F2 — PROSPECT DYNASTY PROJECTION MODEL:** consume the E7.3 MLE → a **multi-year** MLB-equivalent projection per prospect + **ETA** + uncertainty (partial-pooling, thin-rep shrinkage — the NCAAF-P1.2b/P1A analog). Dynasty = a MULTI-SEASON hold.
- **F3 — DYNASTY PROSPECT BOARD / RANKINGS:** rank prospects by projected multi-year value + ETA + risk, honestly. The underserved surface.
- **F4 — KEEPER / DYNASTY PLAYER VALUATIONS:** current MLB players over a multi-year horizon = **F1's projection + aging curves + years-of-control** (the multi-year extension of the seasonal projection).

**BRANCH C — THE TOOLS LAYER (league-customizable; the ENGINE is SHARED with `football/nfl/fantasy/` — build once, instantiate per sport):**
- **F-C1 — ⭐ LEAGUE CONFIGURATION + SCORING ENGINE (the KEYSTONE — build FIRST of the tools):** a league-settings schema (per-stat scoring, roster/starter slots, league size, roto-vs-points, keeper depth) + a scorer that converts F1's RAW stat-line projections → **league-specific fantasy value + VOR + positional scarcity**. Every tool reads it. ⭐ SPORT-AGNOSTIC engine (shares with NFL `NF-C1` — different stat cats, same logic).
- **F-C2 — DRAFT OPTIMIZER (⭐ LIVE-draft-aware):** given the league config + current draft state (drafted, my roster, my slot) → the VOR-maximizing pick (positional-need + tier aware), usable DURING a live draft.
- **F-C3 — TRADE CALCULATOR (redraft ROS-value + dynasty multi-year):** value a trade for MY league config — redraft=F1 ROS value; dynasty=F4 keeper/multi-year. Honest who-wins + uncertainty + roster context.
- **F-C4 — FREE-AGENT / WAIVER RANKINGS (customizable by league ROSTERS):** rank available players by league-adjusted ROS value RELATIVE to a roster's needs (not a generic list); weekly refresh off F1's ROS.

**SURFACES (all branches):**
- **F5 — FANTASY APP SURFACES** (frontend): seasonal projections + the TOOLS (F-C2 draft optimizer, F-C3 trade calc, F-C4 FA rankings, start/sit) + the dynasty board (F3) + keeper valuations (F4). `frontend/` (Next.js), app-target guard.
- **F6 — CONTENT / RANKINGS ENGINE:** seasonal rankings + dynasty prospect rankings as evergreen SEO (the GTM acquisition engine, `gtm_strategy.md §content`).

## 4. Sequencing / honesty
- **Gated on E7** (§2) — F1 can't run until the MiLB data + the E7.3 MLE land. E7.1 is in flight now; the F-series is spec-ready behind it.
- **Not deadline-bound like the football verticals** (no 8/29/9/9 gate), BUT the GTM Dynasty content push is the mid-July→late-Aug window → F5 (rankings content) + a first-pass F2 board have near-term GTM value once the data lands.
- **Edge-independent** — no PBO/DSR/forward-CLV gate applies (that's the betting posture); the gate here is PROJECTION CALIBRATION vs realized outcomes (did a prospect projected at X actually produce ~X) + honest uncertainty, validated on graduated-prospect holdouts (the E7.3 pattern).
- **Reuse, don't reinvent:** `hierarchical.py` (the sport-agnostic partial-pooling solver) + the E7.3 MLE + the feeder-MLE discipline (§0.5 bake-off, EB variance-collapse cure, parameter-vs-calibrated uncertainty, verify-joins-on-real-data) — all proven on P1.2b/P1A/E7.3.

## 5. Maintenance
Update when an F-story ships or the E7 data foundation advances. This vertical shares the `sports`/MLB lakehouse + the honest-analytics posture with `edge_program/`; it does NOT share the betting edge/CLV machinery (Dynasty is a projection product, not a bet).
