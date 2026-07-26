# NF-D2 slices 3 & 4 (both SHIPPED) — TEAM CONTEXT (movers · Vegas environment)

**Generated:** 2026-07-26T06:19:46.144060+00:00 · **seasons:** 2020–2025 · **baseline:** slice-1 (`usage_role_blend=0.4`)

> Team-context ideas ablated vs the slice-1 model. **A (mover / depth-jump) SHIPPED**; **B (Vegas environment, QB) SHIPPED via leakage-safe Week-1 lines**; **C (system fit) deferred**. Every arm calls the SHIPPED `project_veterans` path, so the table measures exactly what ships.

## Arms — mean within-position ρ (+ mover subpopulation)

| arm | QB | RB | WR | TE | movers (all-pos ρ) |
|-----|----|----|----|----|--------------------|
| slice1_baseline | 0.675 | 0.739 | 0.767 | 0.754 | 0.687 |
| A_mover_opportunity | 0.675 | 0.747 | 0.773 | 0.761 | 0.717 |
| B_env_wk1_QB_SAFE | 0.687 | 0.739 | 0.767 | 0.754 | 0.688 |
| B_env_opt_QB_LEAKY | 0.718 | 0.739 | 0.767 | 0.754 | 0.686 |
| D_injury_availability | 0.680 | 0.740 | 0.771 | 0.754 | 0.687 |

## Reading it

- **A (mover / depth-jump opportunity) — ✅ SHIPPED (slice 3).** For a team-changer (base-season team ≠ projection-season team) at RB/WR/TE, the per-game line is rescaled toward the NEW role's volume level. Held-out lift over slice-1: **RB +0.008 · WR +0.006 · TE +0.007 · QB +0.000**, and the **mover subpopulation +~0.03**. Signal is real (diagnostic: `corr(depth-climb, next fp/g change)=+0.26`; climbers +1.3 fp/g vs non-climbers −1.5). Every skill position improves and QB is untouched ⇒ net-positive on the full-board gate. Wired into `project_veterans` (`_MOVER_OPP_BLEND`); ON by default.
- **B (Vegas team environment, QB) — ✅ SHIPPED (slice 4), leakage-safe, no new ingest.** A QB tilt on the projection-season team's **Week-1 implied points** (`env_wk1`) lifts QB ρ **+~0.015**. A Week-1 line is set BEFORE any of the season's games ⇒ leakage-safe, and it's a decent forward proxy for the season environment (corr ≈0.65). The season-long `env_opt` (QB **+~0.06**) is the LEAKY ceiling — Week-1 captures ~1/5, so a richer FORWARD signal (preseason win totals / a captured preseason line snapshot) would recover more. QB-scoped: RB/WR/TE already carry team context through their own usage line; a QB has no such volume anchor. Wired into `project_veterans` (`_ENV_TILT_BLEND`); reads `dim_nfl_game` Week-1 lines (full 2020–2025; 2026 Week-1 already posted).
- **D (injury / availability) — ✅ SHIPPED (slice 5), leakage-safe, no new ingest.** A forward roster-status flag of unavailability (RES/IR, PUP, NFI, SUS) set preseason caps expected games toward the empirical status level (RES→3.7 g, PUP→2.4 vs ACT→13.2). The measured QB/skill ρ lift is only +~0.002 — but that BADLY under-states it: the ρ eval keeps only players with ≥6 realized games, which EXCLUDES the shelved players this fixes. It's a **correctness fix** — don't rank a season-ending-IR or PUP star as a startable option. QB especially benefits (+0.005). Wired into `project_veterans` (`_INJURY_STATUS_GAMES_CAP`); reads the projection-season Week-1 roster status. ⚠️ The nflverse injury REPORT is in-season only (no offseason) and 2026 is unpublished — the roster PUP/IR flag is the available forward source; it populates through camp. A live injury-news feed (Sleeper API `injury_status`) would surface offseason-surgery cases EARLIER — recommended follow-on ingest.
- **C (system fit — archetype × scheme) — deferred.** A forward, mover-centric interaction (a run-first RB into a pass-heavy offense, etc.) best learned jointly in NF1; larger build.

## Strategic implication for NF-D2

Slices 1, 3 & 4 all shipped from data ALREADY in the lakehouse. The winning channels are ROLE/VOLUME (slice 1 snap-usage; slice 3 team-change) and cross-team ENVIRONMENT (slice 4 QB Week-1 lines); slice 2 (NGS/PFR efficiency) was the null (re-encodes production). Remaining headroom: a RICHER forward-Vegas signal (preseason win totals) would grow slice 4 toward its +0.06 ceiling, and weak/interacting signals are best weighted jointly in the learned **NF1** model.

