# Fantasy & Dynasty Projections — Implementation Guide (MLB)

**Status:** v1.0 — engineering-ready
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Scope:** A standalone B2C vertical: fantasy-baseball advice (focus on the underdeveloped **Dynasty** market) powered by a **full distributional player-projections suite** (rest-of-season + multi-year + prospects). Spun out of the Edge Program (was Epic E8) because it's a distinct product with its own data context, users, validation bar, and roadmap — and because it's the seed for **multi-sport fantasy** (NFL fantasy is the larger market; see §7).
**Companion docs:**
- **Master data file →** `quant_sports_intel_models/baseball/baseball_data_mart_inventory.md` — the canonical catalog of every Snowflake table / dbt mart we have. **Every story below names the marts it consumes from there; treat the inventory as the single source of truth for "what data exists."**
- `edge_program/edge_program_implementation_guide.md` — shared conventions (§0), the cost playbook (§6), the app-session handoff pattern (§0.3), and the modeling machinery this reuses (E2 distributional, E7 MiLB MLEs).
- `edge_program/edge_program_technical_spec.md` — **Workstream H** is the design rationale for this suite.
- `edge_program/edge_program_executive_summary.md` — why this vertical is plausibly the program's highest-value, most-defensible B2C bet (it doesn't need a market edge).

---

## 0. How to use this guide

This guide is self-contained for the fantasy vertical. It **inherits the Edge Program's conventions** rather than restating them — read `edge_program_implementation_guide.md` §0 once.

### 0.1 Inherited conventions (from the Edge guide §0.1)
`dbtf` not `dbt` (always `--select`-scoped); Snowflake = OLAP only (MCP, fully-qualified, no `USE`; never a live Snowflake query on a request path); `uv run python`; hand >1-min scripts to the operator; **do not `git commit`/`push`**; Dagster ops import packaged code only; **cost-first** (Dagster coordinates, Railway/EC2-batch/DuckDB/S3-Parquet executes — §6 of the Edge guide).

**Honest-framing rule, fantasy variant:** the bar here is **"match or beat the public projection systems (ZiPS / Steamer / industry)" on transparent accuracy metrics** — *not* a betting win-rate, and not "we're the best." Every projection ships with its uncertainty (P10/P50/P90) and is presented as a calibrated estimate, never a guarantee. (The market-blind rule from the Edge guide does **not** apply here — there's no line to leak; the relevant discipline is leakage-safe, point-in-time data + honest backtest vs the industry baselines.)

### 0.2 Master data file — the data-context contract (the important one)
Before building any projection story, consult the **master data inventory** (`baseball_data_mart_inventory.md`) for the exact marts/columns available. The projection suite draws primarily on:

| Need | Where (per the inventory) |
|------|---------------------------|
| Per-player rate skill (hitters) | `mart_batter_rolling_stats`, `mart_batter_profile_summary`, `eb_batter_posteriors` (EB-shrunk wOBA/K%/BB%/ISO) |
| Per-player rate skill (pitchers) | `mart_pitcher_rolling_stats`, `mart_pitcher_profile_summary`, `eb_starter_posteriors`, `eb_bullpen_posteriors` |
| Industry projections to blend/baseline | `stg_fangraphs__zips_hitting`, `stg_fangraphs__zips_pitching` (ZiPS / Steamer / rZIPS) |
| Playing time / role | `mart_player_start_probability` (Story 33.1), `mart_player_game_starts`, depth-chart inputs |
| Prospects / minor-league | **Edge Program E7** (MiLB ingestion + MLEs) — not yet in the inventory; F4 depends on it |
| Park / environment context | `mart_eb_park_factors`, `feature_league_contact_baseline` |
| Identity / xref | `mart_player_profile_identity`, `dim_fangraphs_player_xref` |

> **Convention:** when a story needs data not in the inventory, that's a data-ingestion task first (route it to the owning ingestion epic — e.g. prospects → Edge E7), and the inventory must be updated when the mart lands. Keep the inventory current; it is the contract.

### 0.3 App/UI work = separate session (Edge guide §0.3)
Same handoff pattern: the fantasy UI (F7) is a **separate app-repo session**, and its `▶ App-session prompt` is **emitted by the upstream model session as its final step**, filled with the real served contract (PG table/columns). Do not hand-author it.

---

## 1. Why this is its own vertical
Per the Edge Program market SWOT (`edge_program_implementation_guide.md` §7A): fantasy — especially **Dynasty** — is an underdeveloped market with weaker incumbents at the prospect/multi-year end. Crucially it **monetizes by subscription and is not gated on beating an efficient market** ("match or beat ZiPS/Steamer" is an achievable, defensible bar), so it de-risks the whole business: even if every betting-edge track washes out, this can still be a real product. It reuses the same modeling spine (distributional projections, EB posteriors, playing-time, MiLB MLEs), so the marginal build cost is low and the moat (prospect projections via minor-league translation) is real.

## 2. End-user explanation (customer-facing)
*"Fantasy baseball — especially Dynasty leagues, where you keep players for years — lives and dies on projections, and most tools give you a single number with no sense of risk or upside. Credence projects every player as a **range** (floor / midpoint / ceiling) across the rest of the season and into future years, and does the same for **prospects** in the minors by translating their minor-league performance into what it's likely to become in the majors. So when you're deciding whether to trade for a 21-year-old in Triple-A, you see a real, risk-aware projection, not a gut call."*

---

## 3. Epics & stories

> Naming: these are the **F-series** (formerly Edge E8.1–E8.8). They reuse the Edge Program's E2 distributional machinery, the EB posteriors, ZiPS/Steamer, the Story-33.1 playing-time model, and (for prospects) Edge E7's MiLB MLEs. **Phase it:** MLB rest-of-season projections first, then multi-year/Dynasty + prospects.

### F1 — Projection target spec (rest-of-season, distributional)  ⬜
**Tasks:**
- [ ] Per-player ROS projections per fantasy category — hitters (AVG/OBP/SLG, HR, R, RBI, SB, wOBA/wRC+), pitchers (ERA, WHIP, K, W, SV, IP, FIP).
- [ ] Emit **distributions (P10/P50/P90)**, not points; reuse the Edge E2 per-player distributional machinery + EB posteriors + a ZiPS/Steamer blend (weight by sample size).
- [ ] Source per the §0.2 data contract (EB posteriors, rolling marts, ZiPS staging).
**AC:** ROS distributional projections for all active players; calibrated vs realized (F8); leakage-safe (point-in-time).

### F2 — Playing-time projection  ⬜  **[biggest single driver]**
**Tasks:**
- [ ] Integrate the Story-33.1 `mart_player_start_probability` (P(start)/role) + depth charts → projected PA (hitters) and IP/starts + role (pitchers).
**AC:** projected PA/IP per player feeding F1's counting-stat projections (volume drives counting stats more than rate skill).

### F3 — Aging curves & multi-year (Dynasty)  ⬜
**Tasks:**
- [ ] Per-player multi-season trajectories with position-specific aging curves; Dynasty value = risk-discounted multi-year projection.
**AC:** N-year projections per player with uncertainty **widening** over the horizon.

### F4 — Prospect projections  ⬜  **[depends on Edge E7 — MiLB ingestion + MLEs]**
**Tasks:**
- [ ] Translate the Edge-E7 minor-league MLE lines + ETA into MLB-equivalent projections + prospect Dynasty rankings.
- [ ] Block on E7.3 (MLEs) / E7.5; until then, F1–F3 ship for established players without prospects.
**AC:** prospects carry risk-aware projections + ETA; ranked alongside MLB players in Dynasty value. **This is the differentiating moat.**

### F5 — League-context value conversion  ⬜
**Tasks:**
- [ ] Convert raw projections to fantasy value (z-scores / SGP / auction $), parameterized by league settings (categories vs points, roto vs H2H, redraft vs Dynasty, roster size).
**AC:** value outputs respond correctly to league-setting inputs.

### F6 — Advice surfaces  ⬜
**Tasks:**
- [ ] Rankings, start/sit, waiver/streamer, trade-value, Dynasty prospect boards — all derived from F1–F5 (not bespoke logic).
**AC:** each advice view derives from the projections; advisory framing; honest accuracy claims only.

### F7 — App / serving  🧩  **[separate app session — prompt emitted by the F-model session; see §0.3]**
**Scope:** a fantasy section in Credence (or a sibling surface); projections precomputed to Railway PG; the A0.4.16 player pages show the player's projection distribution. **AC:** projections render per player; precomputed (no request-time compute); changelog entry.
```
▶ App-session prompt — Story F7 (fantasy projection surfaces)  [app repo]
⏳ TO BE GENERATED by the F-model session as its final task (§0.3), after F1+ produce the projection payload.
   Must specify the ACTUAL PG table + columns (per-player P10/P50/P90 per category, projected PA/IP,
   Dynasty/prospect value) and serving path — then a fresh app session renders the fantasy section + player-page
   projection distributions per the Edge §0.2 architecture + honest framing + changelog. Do not hand-author.
```

### F8 — Validation  ⬜
**Tasks:**
- [ ] Backtest projections vs realized seasons (rank correlation + distribution calibration / PIT) with **ZiPS/Steamer/industry as the baselines to match-or-beat.**
**AC:** projection-accuracy report vs baselines; P10/P50/P90 calibration; honest "match-or-beat" framing.

```
▶ New-session prompt — Fantasy projections suite (copy into a fresh model-repo session)

You are building the MLB Fantasy/Dynasty projection suite. Start with F1 (ROS distributional projections) +
F2 (playing time) — Dynasty/prospects (F3/F4) come after; F4 needs Edge Epic E7 (MiLB MLEs).

Read first:
  1. quant_sports_intel_models/baseball/fantasy/fantasy_dynasty_guide.md (this guide) — §0.2 data contract is your map
  2. baseball_data_mart_inventory.md — the master data file: confirm the exact marts/columns before coding
  3. edge_program_technical_spec.md Workstream H (design) + Workstream B (the distributional machinery you reuse)
  4. master implementation_guide.md — Story 33.1 (playing-time), Epic 18 (fantasy, gated behind Epic 16 ✅),
     EB-posterior models (eb_batter/starter), ZiPS/Steamer staging (stg_fangraphs__zips_*)

Build F1 ROS projections as DISTRIBUTIONS (P10/P50/P90) per fantasy category, blending EB posteriors +
ZiPS/Steamer, conditioned on F2 projected PA/IP. Validate vs ZiPS/Steamer baselines (F8). Bar = match-or-beat
industry; honest accuracy framing (not a betting metric, not "we're best"). FINAL STEP (§0.3): emit the F7
app-session prompt into §F7 of this guide with the real PG table/columns — the fantasy UI is a SEPARATE app session.

COMPUTE: projections are a batch job → S3-Parquet/DuckDB or daily Dagster op; precompute to Railway PG for the
app; never request-time compute. Conventions: dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run
python; hand >1min scripts to the operator; do not git commit/push.
```

---

## 4. Sequencing
1. **F1 + F2** (ROS projections + playing time) — the core; ships for established players, validates vs ZiPS/Steamer immediately (F8).
2. **F5 + F6 + F7** — value conversion + advice surfaces + app (F7 is a separate app session).
3. **F3 (multi-year/Dynasty)** then **F4 (prospects)** — F4 gated on Edge E7 (MiLB MLEs). Dynasty + prospects are the differentiator, so prioritize E7 upstream.

Go/no-go: F8 accuracy vs ZiPS/Steamer is the gate for promoting this from "internal projection" to a shipped product surface.

---

## 5. Multi-sport note
This guide is **MLB fantasy**. The projection pattern (distributional per-player projection + playing-time + aging + a college/minor→pro translation for prospects) is **sport-agnostic**, and NFL fantasy is the larger market. When the program adds football (`quant_sports_intel_models/football/`), expect a sibling `football/fantasy/` guide that instantiates the same F-series against an NFL data inventory — and note the strong **NCAA-Football → NFL draft-continuity** parallel to MLB's MiLB→MLB MLEs (college production translates to pro rookie projections). See the program-level multi-sport roadmap for sequencing.
