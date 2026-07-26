# NF-D2 slices 3 & 4 + NF-D4 — TEAM CONTEXT (movers · Vegas environment · forward win totals)

**Generated:** 2026-07-26T22:32:53.476671+00:00 · **seasons:** 2020–2025 · **baseline:** slice-1 (`usage_role_blend=0.4`)

> Team-context ideas ablated vs the slice-1 model. **A (mover / depth-jump) SHIPPED**; **B (Vegas environment, QB) SHIPPED — slice-4 Week-1 lines, NF-D4 AUGMENTS it with the forward SEASON WIN TOTAL (win-total × Week-1 z-blend)**; **C (system fit) deferred**. Every arm calls the SHIPPED `project_veterans` path, so the table measures exactly what ships.

## Arms — mean within-position ρ (+ mover subpopulation)

| arm | QB | RB | WR | TE | movers (all-pos ρ) |
|-----|----|----|----|----|--------------------|
| slice1_baseline | 0.675 | 0.739 | 0.767 | 0.754 | 0.686 |
| A_mover_opportunity | 0.675 | 0.744 | 0.772 | 0.762 | 0.711 |
| B_env_wk1_QB_SAFE | 0.682 | 0.739 | 0.767 | 0.754 | 0.687 |
| B_env_wintotal_QB | 0.677 | 0.739 | 0.767 | 0.754 | 0.685 |
| B_env_wt_wk1_QB | 0.684 | 0.739 | 0.767 | 0.754 | 0.686 |
| B_env_opt_QB_LEAKY | 0.721 | 0.739 | 0.767 | 0.754 | 0.684 |
| B_env_wintotal_ALLSKILL | 0.677 | 0.737 | 0.768 | 0.753 | 0.681 |
| D_injury_availability | 0.680 | 0.740 | 0.771 | 0.754 | 0.686 |

## Reading it

- **A (mover / depth-jump opportunity) — ✅ SHIPPED (slice 3).** For a team-changer (base-season team ≠ projection-season team) at RB/WR/TE, the per-game line is rescaled toward the NEW role's volume level. Held-out lift over slice-1: **RB +0.008 · WR +0.006 · TE +0.007 · QB +0.000**, and the **mover subpopulation +~0.03**. Signal is real (diagnostic: `corr(depth-climb, next fp/g change)=+0.26`; climbers +1.3 fp/g vs non-climbers −1.5). Every skill position improves and QB is untouched ⇒ net-positive on the full-board gate. Wired into `project_veterans` (`_MOVER_OPP_BLEND`); ON by default.
- **B (Vegas team environment, QB) — ✅ SHIPPED (slice 4 + NF-D4), leakage-safe.** A QB tilt on the projection-season team's **Week-1 implied points** (`env_wk1`) lifts QB ρ over baseline; the season-long `env_opt` is the LEAKY ceiling (QB **+~0.046** over baseline in this run) — Week-1 captures only a fraction. **NF-D4 forward-Vegas upgrade:**
  - ⚠️ *Probe:* the **Odds API exposes NO NFL win-total futures market** (only `americanfootball_nfl_super_bowl_winner` outrights) → NF-D4 source #2 UNAVAILABLE, no credits spent. The forward win total comes from a STATIC public backfill (source #3, `win_total_source.py`, covers.com Sports Odds History, 2020–2026).
  - `env_wt` (**win total ALONE**) is **WORSE than Week-1** (loses 5/6 seasons): a win total is a season-level TEAM-QUALITY read (offense + defense), but the recoverable ceiling (`env_opt`) is OFFENSE-specific → a win total dilutes the offense signal with defense. **DROPPED.**
  - `env_wt_wk1` (**win-total × Week-1 z-blend**) **BEATS Week-1** on the 6-season-mean QB ρ (**0.684 vs 0.682**, wins 4/6) by STABILISING the noisy single Week-1 game line — the win total rescues seasons where one Week-1 line is a bad proxy (e.g. 2020: base 0.706, wk1 0.685, blend 0.696). **SHIPPED** as the QB env source (AUGMENT — `blend_env_with_win_total`; graceful fallback to Week-1-only when a season's totals aren't backfilled).
  - `env_wt_ALLSKILL` (**tilt widened to RB/WR/TE**) adds **NO lift** (matches the slice-4 finding — skill players already carry team context through their own usage line). Stays **QB-scoped.** The `env_tilt_positions` knob is wired but defaults to QB.
  - **Honest headroom:** the gain over Week-1 is SMALL (+0.002) and most of the ceiling stays unrecovered because it is offense-specific. The true future lever is a going-forward preseason **OPENING-LINE / team-total** capture (serves 2026+, but CANNOT validate historically — the Odds-API `/historical` game-line endpoint returns the CLOSING snapshot, floor 2020).
- **D (injury / availability) — ✅ SHIPPED (slice 5), leakage-safe, no new ingest.** A forward roster-status flag of unavailability (RES/IR, PUP, NFI, SUS) set preseason caps expected games toward the empirical status level (RES→3.7 g, PUP→2.4 vs ACT→13.2). The measured QB/skill ρ lift is only +~0.002 — but that BADLY under-states it: the ρ eval keeps only players with ≥6 realized games, which EXCLUDES the shelved players this fixes. It's a **correctness fix** — don't rank a season-ending-IR or PUP star as a startable option. QB especially benefits (+0.005). Wired into `project_veterans` (`_INJURY_STATUS_GAMES_CAP`); reads the projection-season Week-1 roster status. ⚠️ The nflverse injury REPORT is in-season only (no offseason) and 2026 is unpublished — the roster PUP/IR flag is the available forward source; it populates through camp. A live injury-news feed (Sleeper API `injury_status`) would surface offseason-surgery cases EARLIER — recommended follow-on ingest.
- **C (system fit — archetype × scheme) — deferred.** A forward, mover-centric interaction (a run-first RB into a pass-heavy offense, etc.) best learned jointly in NF1; larger build.

## Strategic implication for NF-D2 / NF-D4

Slices 1, 3, 4 & the NF-D4 win-total augment all ship from FREE data (lakehouse + a one-time static win-total backfill). The winning channels are ROLE/VOLUME (slice 1 snap-usage; slice 3 team-change) and cross-team ENVIRONMENT (slice 4 QB Week-1 lines, NF-D4 win-total blend); slice 2 (NGS/PFR efficiency) was the null (re-encodes production). **NF-D4 verdict:** the forward SEASON win total genuinely helps but only in BLEND with the offense-specific Week-1 line, and only marginally (+0.002) — a win total measures team quality, not offense, so it can't recover the offense-specific ceiling on its own. The next real lever is a going-forward preseason OPENING-LINE / team-total capture (offense-specific AND season-forward), which serves future seasons but can't be validated on history; and weak/interacting signals are best weighted jointly in the learned **NF1** model.

