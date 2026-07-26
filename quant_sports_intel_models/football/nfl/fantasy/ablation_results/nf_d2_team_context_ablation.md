# NF-D2 slice 3 (SHIPPED) + slice 4 (blocked) — TEAM CONTEXT (movers · Vegas environment)

**Generated:** 2026-07-26T05:45:04.940730+00:00 · **seasons:** 2020–2025 · **baseline:** slice-1 (`usage_role_blend=0.4`)

> Team-context ideas ablated vs the slice-1 model. **A (mover / depth-jump) SHIPPED**; **B (Vegas environment) is blocked** on a forward-data gap; **C (system fit) deferred**. The mover arm here calls the SHIPPED `project_veterans` path, so the table measures exactly what ships.

## Arms — mean within-position ρ (+ mover subpopulation)

| arm | QB | RB | WR | TE | movers (all-pos ρ) |
|-----|----|----|----|----|--------------------|
| slice1_baseline | 0.675 | 0.739 | 0.767 | 0.754 | 0.687 |
| A_mover_opportunity | 0.675 | 0.747 | 0.773 | 0.761 | 0.717 |
| B_env_safe_QB | 0.681 | 0.739 | 0.767 | 0.754 | 0.687 |
| B_env_opt_QB_LEAKY | 0.748 | 0.739 | 0.767 | 0.754 | 0.685 |

## Reading it

- **A (mover / depth-jump opportunity) — ✅ SHIPPED (slice 3).** For a team-changer (base-season team ≠ projection-season team) at RB/WR/TE, the per-game line is rescaled toward the NEW role's volume level. Held-out lift over slice-1: **RB +0.008 · WR +0.006 · TE +0.007 · QB +0.000**, and the **mover subpopulation +~0.03**. Signal is real (diagnostic: `corr(depth-climb, next fp/g change)=+0.26`; climbers +1.3 fp/g vs non-climbers −1.5). Every skill position improves and QB is untouched ⇒ net-positive on the full-board gate. Wired into `project_veterans` (`_MOVER_OPP_BLEND`); ON by default.
- **B (Vegas team environment, QB) — ⛔ BLOCKED on a data gap.** `env_opt` (projection-season implied points) lifts QB ρ **+0.07** — a strong lever — but it LEAKS (season-Y line aggregates absorb the realized season). The leakage-safe `env_safe` (prior-season implied points) is **marginal noise (~0)** — last year's team environment is largely redundant with the player's own line. **The valuable signal is the forward preseason market view, not in the lakehouse historically ⇒ can't be leakage-safe-validated.** NOT shipped. BLOCKED on ingesting PRESEASON WIN TOTALS / forward game totals — then it's validatable, and the live 2026 board's forward lines are a legitimate non-leaky use (the best shot at the QB-ordering complaint).
- **C (system fit — archetype × scheme) — deferred.** A forward, mover-centric interaction (a run-first RB into a pass-heavy offense, etc.) that shares B's forward-data dependence and is best learned jointly in NF1; larger build, deferred.

## Strategic implication for NF-D2

Slices 1 & 3 both won through the EXPECTED-GAMES / role-VOLUME channel (snap-usage role; team-change role). Slice 2 (NGS/PFR efficiency) was a null (it re-encodes production). The pattern: the heuristic exploits ROLE/VOLUME signals but not efficiency ones; the remaining confirmed-real gains (Vegas environment, system fit) need a **forward-Vegas ingest** (preseason win totals) and are best weighted jointly in the learned **NF1** model. Recommend that ingest next, then NF1.

