# NCAAF-P1.5 — season-simulation futures (National Championship + conference titles)

_Generated 2026-07-24T07:20:51.945141+00:00_

> ⚠️ **Product value, not an edge claim.** These are calibrated season-long title probabilities from a posterior-predictive Monte-Carlo on the P1.4 game model. Futures carry a HIGH hold (20–40%) and are brand/public-shaped; `best_alpha = 0` holds — an edge is only claimed if a de-vigged-vs-market number survives the deflation gate over teams×markets×seasons, which needs a historical futures capture that does not exist yet.

## Method (posterior-predictive season sim)

1. **Draw each team's true season strength ONCE per simulated season** from its P1.2 week-1 posterior (`ncaaf_team_strength_week`), reused across that team's whole schedule — the correlation structure that makes a futures number honest (a genuinely-good draw wins more of its schedule that sim). 2. **Simulate every game** with the P1.4 model in `fixed_strength=True` mode (σ₀ ONLY — the strength uncertainty is already in the drawn μ; adding the per-game k² term would double-count it). 3. **Bookkeeping**: conference standings → a simulated neutral conference-championship game between the top two → the 2026 12-team CFP (5 champion auto-qualifiers, straight seeding, top-4 byes, 5v12…8v9) simulated to a champion. 4. **Count frequencies** over N sims.

**Encoded ruleset (explicit + swappable — the committee is fuzzy):** 12-team CFP, STRAIGHT SEEDING (the 2025-26 rule change, confirmed for 2026 — NOT the 2024 champions-seeded-1–4 rule); auto-qualifiers = the 4 Power-conference champions + the single highest-ranked Group-of-5 champion; committee ranking proxy = `drawn net strength − loss_penalty·losses`; conference-title tiebreak = (conf win-pct, overall win-pct, drawn strength) — a documented proxy for the real multi-way NCAA tiebreakers, infeasible to replay exactly across thousands of sims.

## Board — 2026 (as-of week 1, 20,000 sims)

| team | conf | strength | E[W] | P(conf) | P(CFP) | P(bye) | P(final) | P(natty) |
|---|---|---|---|---|---|---|---|---|
| Indiana | Big Ten | 9.0 | 7.7 | 0.193 | 0.415 | 0.229 | 0.126 | 0.075 |
| Ohio State | Big Ten | 6.8 | 7.8 | 0.139 | 0.278 | 0.126 | 0.077 | 0.044 |
| Notre Dame | FBS Independents | 6.4 | 8.3 | 0.000 | 0.313 | 0.158 | 0.082 | 0.043 |
| Oregon | Big Ten | 5.8 | 7.0 | 0.113 | 0.274 | 0.124 | 0.070 | 0.040 |
| Texas Tech | Big 12 | 4.8 | 7.5 | 0.194 | 0.346 | 0.153 | 0.070 | 0.038 |
| Miami | ACC | 5.4 | 7.2 | 0.190 | 0.317 | 0.134 | 0.068 | 0.037 |
| Georgia | SEC | 4.1 | 5.8 | 0.085 | 0.224 | 0.090 | 0.048 | 0.025 |
| Ole Miss | SEC | 3.9 | 6.5 | 0.113 | 0.210 | 0.080 | 0.048 | 0.025 |
| Utah | Big 12 | 3.3 | 6.8 | 0.133 | 0.233 | 0.089 | 0.044 | 0.024 |
| Iowa | Big Ten | 3.2 | 6.5 | 0.070 | 0.185 | 0.072 | 0.038 | 0.021 |
| Penn State | Big Ten | 3.0 | 7.5 | 0.097 | 0.206 | 0.080 | 0.041 | 0.020 |
| Texas A&M | SEC | 3.0 | 6.3 | 0.092 | 0.178 | 0.063 | 0.034 | 0.019 |
| Alabama | SEC | 2.8 | 6.2 | 0.087 | 0.169 | 0.061 | 0.033 | 0.018 |
| Vanderbilt | SEC | 2.5 | 6.2 | 0.084 | 0.169 | 0.061 | 0.032 | 0.017 |
| Texas | SEC | 2.6 | 6.2 | 0.072 | 0.163 | 0.058 | 0.031 | 0.016 |
| Washington | Big Ten | 2.1 | 6.0 | 0.051 | 0.134 | 0.048 | 0.028 | 0.016 |
| SMU | ACC | 1.8 | 6.5 | 0.114 | 0.195 | 0.063 | 0.032 | 0.016 |
| USC | Big Ten | 2.4 | 6.8 | 0.065 | 0.139 | 0.050 | 0.029 | 0.014 |
| Oklahoma | SEC | 1.9 | 6.1 | 0.065 | 0.148 | 0.052 | 0.030 | 0.014 |
| James Madison | Sun Belt | 0.9 | 7.0 | 0.212 | 0.197 | 0.078 | 0.031 | 0.014 |
| BYU | Big 12 | 1.3 | 6.1 | 0.087 | 0.155 | 0.049 | 0.027 | 0.013 |
| South Florida | American Athletic | 0.3 | 6.8 | 0.146 | 0.171 | 0.067 | 0.028 | 0.013 |
| Clemson | ACC | 0.6 | 6.2 | 0.071 | 0.150 | 0.050 | 0.025 | 0.012 |
| Tennessee | SEC | 0.8 | 5.8 | 0.063 | 0.122 | 0.037 | 0.021 | 0.011 |
| Louisville | ACC | 0.4 | 6.0 | 0.082 | 0.142 | 0.043 | 0.023 | 0.010 |

## Honest limitations

- **No live 2026 board yet** — the 2026 schedule + 2026 week-1 strengths do not exist until the season nears; re-run `--season 2026` when they land (nothing else changes).
- **The committee seeding is a transparent heuristic, not the committee** — stated + swappable (`CfpFormat`). NCAA multi-way tiebreakers (head-to-head, division/common-opponent records) are approximated by the strength ordering.
- **Divisions are not modelled** — the top-2-by-conference-record championship-game structure is applied uniformly (the pre-2024 division brackets changed yearly; a documented simplification).
- **`strength_margin_sd` is P1.2 PARAMETER uncertainty** — the once-per-season draw uses it at `strength_sd_scale` (default 1.0). If the held-out title-odds are over/under-confident, recalibrate that ONE scalar (the E13.6 pattern) rather than the whole model.
- **vs-market is a scaffold** — historical futures odds were never captured; the de-vig comparison lands when a futures feed exists (`--futures-csv`). `best_alpha = 0`.

