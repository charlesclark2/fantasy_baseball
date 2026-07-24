# NCAAF-P1.5 — season-simulation futures (National Championship + conference titles)

_Generated 2026-07-24T06:13:02.486517+00:00_

> ⚠️ **Product value, not an edge claim.** These are calibrated season-long title probabilities from a posterior-predictive Monte-Carlo on the P1.4 game model. Futures carry a HIGH hold (20–40%) and are brand/public-shaped; `best_alpha = 0` holds — an edge is only claimed if a de-vigged-vs-market number survives the deflation gate over teams×markets×seasons, which needs a historical futures capture that does not exist yet.

## Method (posterior-predictive season sim)

1. **Draw each team's true season strength ONCE per simulated season** from its P1.2 week-1 posterior (`ncaaf_team_strength_week`), reused across that team's whole schedule — the correlation structure that makes a futures number honest (a genuinely-good draw wins more of its schedule that sim). 2. **Simulate every game** with the P1.4 model in `fixed_strength=True` mode (σ₀ ONLY — the strength uncertainty is already in the drawn μ; adding the per-game k² term would double-count it). 3. **Bookkeeping**: conference standings → a simulated neutral conference-championship game between the top two → the 2026 12-team CFP (5 champion auto-qualifiers, straight seeding, top-4 byes, 5v12…8v9) simulated to a champion. 4. **Count frequencies** over N sims.

**Encoded ruleset (explicit + swappable — the committee is fuzzy):** 12-team CFP, STRAIGHT SEEDING (the 2025-26 rule change, confirmed for 2026 — NOT the 2024 champions-seeded-1–4 rule); auto-qualifiers = the 4 Power-conference champions + the single highest-ranked Group-of-5 champion; committee ranking proxy = `drawn net strength − loss_penalty·losses`; conference-title tiebreak = (conf win-pct, overall win-pct, drawn strength) — a documented proxy for the real multi-way NCAA tiebreakers, infeasible to replay exactly across thousands of sims.

## Board — 2024 (as-of week 1, 20,000 sims)

| team | conf | strength | E[W] | P(conf) | P(CFP) | P(bye) | P(final) | P(natty) |
|---|---|---|---|---|---|---|---|---|
| Georgia | SEC | 29.9 | 8.2 | 0.293 | 0.807 | 0.567 | 0.374 | 0.246 |
| Oregon | Big Ten | 22.3 | 8.9 | 0.292 | 0.650 | 0.354 | 0.168 | 0.087 |
| Penn State | Big Ten | 22.6 | 9.8 | 0.311 | 0.644 | 0.348 | 0.171 | 0.087 |
| Ohio State | Big Ten | 22.2 | 8.9 | 0.198 | 0.646 | 0.330 | 0.168 | 0.084 |
| Texas | SEC | 21.7 | 8.7 | 0.145 | 0.587 | 0.285 | 0.149 | 0.077 |
| Missouri | SEC | 20.4 | 8.7 | 0.162 | 0.564 | 0.264 | 0.120 | 0.062 |
| Notre Dame | FBS Independents | 19.5 | 9.9 | 0.000 | 0.580 | 0.284 | 0.117 | 0.054 |
| Alabama | SEC | 20.4 | 7.5 | 0.101 | 0.361 | 0.147 | 0.091 | 0.048 |
| Ole Miss | SEC | 17.4 | 7.6 | 0.074 | 0.314 | 0.112 | 0.061 | 0.030 |
| Clemson | ACC | 16.3 | 7.8 | 0.240 | 0.378 | 0.108 | 0.056 | 0.025 |
| LSU | SEC | 17.1 | 7.3 | 0.077 | 0.295 | 0.106 | 0.055 | 0.024 |
| Oklahoma | SEC | 16.3 | 6.3 | 0.031 | 0.241 | 0.076 | 0.045 | 0.021 |
| Tennessee | SEC | 15.7 | 7.4 | 0.051 | 0.251 | 0.071 | 0.041 | 0.017 |
| SMU | ACC | 13.2 | 8.1 | 0.192 | 0.354 | 0.106 | 0.040 | 0.015 |
| Florida State | ACC | 13.9 | 6.1 | 0.107 | 0.231 | 0.061 | 0.031 | 0.014 |
| Kansas State | Big 12 | 12.0 | 7.4 | 0.173 | 0.272 | 0.064 | 0.024 | 0.010 |
| Florida | SEC | 12.4 | 5.2 | 0.018 | 0.110 | 0.027 | 0.017 | 0.008 |
| Kansas | Big 12 | 10.0 | 4.4 | 0.133 | 0.288 | 0.067 | 0.021 | 0.007 |
| Texas A&M | SEC | 12.3 | 5.7 | 0.019 | 0.135 | 0.035 | 0.019 | 0.007 |
| Michigan | Big Ten | 10.7 | 7.1 | 0.043 | 0.114 | 0.026 | 0.014 | 0.006 |
| Iowa State | Big 12 | 9.3 | 6.2 | 0.092 | 0.177 | 0.038 | 0.014 | 0.005 |
| Auburn | SEC | 11.0 | 6.2 | 0.013 | 0.078 | 0.016 | 0.009 | 0.005 |
| TCU | Big 12 | 9.0 | 6.0 | 0.097 | 0.171 | 0.031 | 0.013 | 0.004 |
| Miami | ACC | 10.1 | 7.0 | 0.097 | 0.177 | 0.036 | 0.015 | 0.004 |
| USC | Big Ten | 10.5 | 6.6 | 0.035 | 0.087 | 0.018 | 0.010 | 0.004 |

_Realized 2024 national champion: **Ohio State**._

## Honest limitations

- **No live 2026 board yet** — the 2026 schedule + 2026 week-1 strengths do not exist until the season nears; re-run `--season 2026` when they land (nothing else changes).
- **The committee seeding is a transparent heuristic, not the committee** — stated + swappable (`CfpFormat`). NCAA multi-way tiebreakers (head-to-head, division/common-opponent records) are approximated by the strength ordering.
- **Divisions are not modelled** — the top-2-by-conference-record championship-game structure is applied uniformly (the pre-2024 division brackets changed yearly; a documented simplification).
- **`strength_margin_sd` is P1.2 PARAMETER uncertainty** — the once-per-season draw uses it at `strength_sd_scale` (default 1.0). If the held-out title-odds are over/under-confident, recalibrate that ONE scalar (the E13.6 pattern) rather than the whole model.
- **vs-market is a scaffold** — historical futures odds were never captured; the de-vig comparison lands when a futures feed exists (`--futures-csv`). `best_alpha = 0`.

