# NCAAF-P1.5 — season-simulation futures (National Championship + conference titles)

_Generated 2026-08-17T18:57:35.367909+00:00_

> ⚠️ **Product value, not an edge claim.** These are calibrated season-long title probabilities from a posterior-predictive Monte-Carlo on the P1.4 game model. Futures carry a HIGH hold (20–40%) and are brand/public-shaped; `best_alpha = 0` holds — an edge is only claimed if a de-vigged-vs-market number survives the deflation gate over teams×markets×seasons, which needs a historical futures capture that does not exist yet.

## Method (posterior-predictive season sim)

1. **Draw each team's true season strength ONCE per simulated season** from its P1.2 week-1 posterior (`ncaaf_team_strength_week`), reused across that team's whole schedule — the correlation structure that makes a futures number honest (a genuinely-good draw wins more of its schedule that sim). 2. **Simulate every game** with the P1.4 model in `fixed_strength=True` mode (σ₀ ONLY — the strength uncertainty is already in the drawn μ; adding the per-game k² term would double-count it). 3. **Bookkeeping**: conference standings → a simulated neutral conference-championship game between the top two → the 2026 12-team CFP (5 champion auto-qualifiers, straight seeding, top-4 byes, 5v12…8v9) simulated to a champion. 4. **Count frequencies** over N sims.

**Encoded ruleset (explicit + swappable — the committee is fuzzy):** 12-team CFP, STRAIGHT SEEDING (the 2025-26 rule change, confirmed for 2026 — NOT the 2024 champions-seeded-1–4 rule); auto-qualifiers = the 4 Power-conference champions + the single highest-ranked Group-of-5 champion; committee ranking proxy = `drawn net strength − loss_penalty·losses`; conference-title tiebreak = (conf win-pct, overall win-pct, drawn strength) — a documented proxy for the real multi-way NCAA tiebreakers, infeasible to replay exactly across thousands of sims.

## Held-out calibration (2016–2026 pre-season, vs realized outcomes)

_11 seasons (2016–2026), 20,000 sims each, strength_sd_scale 1.0. The P1.2 thin-seed season (2015, whose pre-season prior is fit on one prior season → near-flat noise) is dropped by default._

> ⏳ **This section was NOT recomputed by this run** — it is re-rendered from `ncaaf_p1_5_calibration.json`, computed 2026-08-17T18:57:32+00:00. A board-only publish does not re-run the gate; pass `--calibrate` to refresh it.

_Served model: `ridge` / `strength_pace` / form `strength_posterior` (σ₀_margin 15.6097); mean artifact `strength_pace`, 27 cols, pace ['pace_sum', 'pace_diff']. ⭐ This gate is a PRE-SEASON read, so the pace term is inert on every season by construction (measured: pace acted on NO season) — any movement vs the pre-S1-serve gate is the σ REFIT under the pace contract, not the pace term._

**Expected wins** (the cleanest dense check of the game layer): MAE **1.64** wins · bias 0.012 · corr 0.662 (n=1309 team-seasons). A ~1.6-win MAE with ~zero bias means the game-simulation layer is honestly calibrated season-long.

**Conference title** (dense — ~6 champions/season): base rate 0.0485, Brier **0.04433**, Brier-skill vs climatology **0.0398** (>0 ⇒ skillful), n=1257.

| predicted-prob bin | n | mean predicted | observed freq |
|---|---|---|---|
| [0.0,0.1) | 928 | 0.0336 | 0.0237 |
| [0.1,0.2) | 193 | 0.1396 | 0.057 |
| [0.2,0.3) | 92 | 0.2446 | 0.1413 |
| [0.3,0.4) | 26 | 0.3413 | 0.3077 |
| [0.4,0.5) | 16 | 0.4411 | 0.375 |
| [0.6,0.7) | 1 | 0.6714 | 0.0 |
| [0.7,0.8) | 1 | 0.7992 | 1.0 |

⚠️ **Mild over-confidence in the mid bins** (predicted > observed around 0.1–0.3): the once-per-season draw is slightly too tight, the residual of P1.2's known ~1.5×-too-tight sd. A `--strength-sd-scale ≈1.3` widens the draw and marginally improves the conf-title Brier; the national-title directional signal is best at 1.0, so **1.0 ships as the honest default** (draw straight from the posterior, the prescribed method) with the scale exposed as the one E13.6-style recalibration knob.

**National title** (THIN — ~11 outcomes, directional): base rate 0.0076, Brier 0.0066, Brier-skill 0.13, n=1309.

**Where the eventual champion sat on the pre-season board: 9/10 were pre-season TOP-4** (the market-blind board, no ranking input). The lone outlier is the historic shock — see the table.

| season | champion | pre-season natty rank | pre-season P(natty) |
|---|---|---|---|
| 2016 | Clemson | 2 | 0.08925 |
| 2017 | Alabama | 1 | 0.23565 |
| 2018 | Clemson | 4 | 0.0981 |
| 2019 | LSU | 4 | 0.0525 |
| 2020 | Alabama | 3 | 0.1224 |
| 2021 | Georgia | 3 | 0.13005 |
| 2022 | Georgia | 1 | 0.2772 |
| 2023 | Michigan | 4 | 0.1038 |
| 2024 | Ohio State | 4 | 0.07935 |
| 2025 | Indiana | 18 | 0.00945 |
| 2026 | None | None | None |

## Board — 2026 (as-of week 1, 20,000 sims)

_The certified pace term is **INERT on this board by construction** — no team carries an as-of-week tempo yet (every week-1 team-week row is the rollup's honest empty row), so μ is bit-for-bit the pre-S1-serve mean map. Pace acts in-season (`--as-of-week` ≥ 2)._

| team | conf | strength | E[W] | P(conf) | P(CFP) | P(bye) | P(final) | P(natty) |
|---|---|---|---|---|---|---|---|---|
| Indiana | Big Ten | 9.0 | 7.7 | 0.193 | 0.415 | 0.229 | 0.126 | 0.075 |
| Ohio State | Big Ten | 6.8 | 7.8 | 0.139 | 0.278 | 0.126 | 0.078 | 0.044 |
| Notre Dame | FBS Independents | 6.4 | 8.3 | 0.000 | 0.312 | 0.157 | 0.082 | 0.043 |
| Oregon | Big Ten | 5.8 | 7.0 | 0.113 | 0.274 | 0.124 | 0.070 | 0.040 |
| Texas Tech | Big 12 | 4.8 | 7.5 | 0.194 | 0.346 | 0.153 | 0.070 | 0.038 |
| Miami | ACC | 5.4 | 7.2 | 0.190 | 0.317 | 0.134 | 0.068 | 0.037 |
| Georgia | SEC | 4.1 | 5.8 | 0.085 | 0.224 | 0.090 | 0.048 | 0.025 |
| Ole Miss | SEC | 3.9 | 6.5 | 0.113 | 0.210 | 0.080 | 0.048 | 0.025 |
| Utah | Big 12 | 3.3 | 6.8 | 0.133 | 0.234 | 0.089 | 0.044 | 0.024 |
| Iowa | Big Ten | 3.2 | 6.5 | 0.070 | 0.185 | 0.072 | 0.038 | 0.021 |
| Penn State | Big Ten | 3.0 | 7.5 | 0.097 | 0.206 | 0.080 | 0.042 | 0.020 |
| Texas A&M | SEC | 3.0 | 6.3 | 0.092 | 0.179 | 0.063 | 0.034 | 0.019 |
| Alabama | SEC | 2.8 | 6.2 | 0.087 | 0.169 | 0.061 | 0.033 | 0.018 |
| Vanderbilt | SEC | 2.5 | 6.2 | 0.084 | 0.169 | 0.061 | 0.032 | 0.017 |
| Texas | SEC | 2.6 | 6.2 | 0.072 | 0.163 | 0.058 | 0.031 | 0.016 |
| Washington | Big Ten | 2.1 | 6.0 | 0.051 | 0.134 | 0.048 | 0.028 | 0.016 |
| SMU | ACC | 1.8 | 6.5 | 0.114 | 0.195 | 0.063 | 0.032 | 0.016 |
| USC | Big Ten | 2.4 | 6.8 | 0.065 | 0.139 | 0.050 | 0.029 | 0.014 |
| Oklahoma | SEC | 1.9 | 6.1 | 0.065 | 0.148 | 0.052 | 0.030 | 0.014 |
| James Madison | Sun Belt | 0.9 | 7.0 | 0.212 | 0.197 | 0.078 | 0.031 | 0.014 |
| South Florida | American Athletic | 0.3 | 6.8 | 0.146 | 0.171 | 0.067 | 0.028 | 0.013 |
| BYU | Big 12 | 1.3 | 6.1 | 0.087 | 0.155 | 0.049 | 0.027 | 0.013 |
| Clemson | ACC | 0.6 | 6.2 | 0.071 | 0.150 | 0.050 | 0.025 | 0.012 |
| Tennessee | SEC | 0.8 | 5.8 | 0.063 | 0.122 | 0.037 | 0.021 | 0.011 |
| Louisville | ACC | 0.4 | 6.0 | 0.082 | 0.142 | 0.043 | 0.023 | 0.010 |

## Honest limitations

- **No live 2026 board yet** — the 2026 schedule + 2026 week-1 strengths do not exist until the season nears; re-run `--season 2026` when they land (nothing else changes).
- **The committee seeding is a transparent heuristic, not the committee** — stated + swappable (`CfpFormat`). NCAA multi-way tiebreakers (head-to-head, division/common-opponent records) are approximated by the strength ordering.
- **Divisions are not modelled** — the top-2-by-conference-record championship-game structure is applied uniformly (the pre-2024 division brackets changed yearly; a documented simplification).
- **`strength_margin_sd` is P1.2 PARAMETER uncertainty** — the once-per-season draw uses it at `strength_sd_scale` (default 1.0). If the held-out title-odds are over/under-confident, recalibrate that ONE scalar (the E13.6 pattern) rather than the whole model.
- **vs-market is a scaffold** — historical futures odds were never captured; the de-vig comparison lands when a futures feed exists (`--futures-csv`). `best_alpha = 0`.

