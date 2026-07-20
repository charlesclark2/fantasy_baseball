# NCAAF-P1.2 — conference/team-strength mixed-effects model

**Model:** `ncaaf_team_strength_v1` · **generated:** 2026-07-20T22:20:30.572807+00:00
**Seasons emitted:** 2015–2025 (22,992 team-week rows) · **seed (not emitted):** 2014

> ⚠️ **This is a strength PRIOR, not an edge claim.** Every number below is measured against realized margins, never against a market price. No bet, no win rate, no ROI is implied or claimed; `best_alpha = 0` still holds. Whether this feature is worth anything against a closing line is P1.4's question, and P1.4 answers it under the §0.5 bake-off discipline (≥3 model classes, purged/embargoed CV, PBO/DSR).

## 1. Leakage gates

- ✅ season_order_week is monotone in game_date (date-based, not week-based)
- ✅ seed season 2014 not emitted (its hyperparameters are in-sample)
- ✅ every emitted row's hyperparameters were fit on strictly prior seasons
- ✅ the first as-of week of each season is a pure preseason prior (0 games)
- ✅ grain (season, team_id, as_of_week) is unique
- ✅ strength_margin / _sd are finite and the sd is strictly positive
- ✅ strength_margin_sd is physically plausible (max 13.8 pts, ceiling 50.0)

## 2. What the model learned (stage-A hyperparameters, fit on strictly prior seasons)

|   season | model   | seasons_used        |   n_obs |   sigma |   home_field |   tau_team |   tau_conference | converged   |
|---------:|:--------|:--------------------|--------:|--------:|-------------:|-----------:|-----------------:|:------------|
|     2020 | margin  | 2016,2017,2018,2019 |    3081 |   8.404 |        2.546 |      7.334 |            1.253 | True        |
|     2021 | margin  | 2017,2018,2019,2020 |    2837 |   8.186 |        2.095 |      7.495 |            2.423 | True        |
|     2022 | margin  | 2018,2019,2020,2021 |    2831 |   8.351 |        1.866 |      7.603 |            1.934 | True        |
|     2023 | margin  | 2019,2020,2021,2022 |    2835 |   8.442 |        1.817 |      7.271 |            1.654 | True        |
|     2024 | margin  | 2020,2021,2022,2023 |    2853 |   8.679 |        1.991 |      6.668 |            1.252 | True        |
|     2025 | margin  | 2021,2022,2023,2024 |    3135 |   8.202 |        2.561 |      6.934 |            1.055 | True        |

`home_field` is the fitted home-field advantage in points; `tau_team` is how far teams spread around their conference mean; `tau_conference` is how far conferences spread around the league. The ratio of the two IS the partial-pooling story — a team with few games is pulled toward its conference by roughly `sigma^2 / (sigma^2 + n * tau_team^2)` of the distance.

### 2.1 Pre-season covariate coefficients (points of strength per 1 sd of covariate)

| covariate                    | group       |   beta (pts / sd) |
|:-----------------------------|:------------|------------------:|
| def__hc_change_from_prev     | other       |           nan     |
| def__hc_recent_sp_overall    | other       |           nan     |
| def__is_first_year_at_school | other       |           nan     |
| def__portal_net_stars        | other       |           nan     |
| def__prior_strength          | other       |           nan     |
| def__returning_ppa_pct       | other       |           nan     |
| def__roster_continuity_pct   | other       |           nan     |
| def__team_talent             | other       |           nan     |
| hc_change_from_prev          | coaching    |            -0.475 |
| hc_recent_sp_overall         | coaching    |             3.468 |
| is_first_year_at_school      | coaching    |            -0.475 |
| off__hc_change_from_prev     | other       |           nan     |
| off__hc_recent_sp_overall    | other       |           nan     |
| off__is_first_year_at_school | other       |           nan     |
| off__portal_net_stars        | other       |           nan     |
| off__prior_strength          | other       |           nan     |
| off__returning_ppa_pct       | other       |           nan     |
| off__roster_continuity_pct   | other       |           nan     |
| off__team_talent             | other       |           nan     |
| portal_net_stars             | roster_flux |             0.119 |
| prior_strength               | carryover   |             4.543 |
| returning_ppa_pct            | roster_flux |             1.225 |
| roster_continuity_pct        | roster_flux |            -0.054 |
| team_talent                  | talent      |             2.958 |

## 3. ⭐ Does the roster/NIL-flux covariate actually move teams? (the P1.2 sanity check)

`covariate_component_roster_flux` is, per team, the points of pre-season strength attributable to returning production + roster continuity + net portal stars — i.e. exactly what would vanish if those covariates were removed from the prior mean. Measured at each season's week-1 row, where the covariates are the ONLY in-season-free signal there is.

| component   |   sd across teams (pts) |   max |contribution| (pts) |
|:------------|------------------------:|---------------------------:|
| carryover   |                   5.937 |                     21.011 |
| talent      |                   3.452 |                     14.461 |
| roster_flux |                   2.167 |                     27.363 |
| coaching    |                   2.053 |                      8.910 |
| unknown     |                   1.715 |                     28.564 |

**Largest roster/portal-driven pre-season adjustments (all seasons):**

|   season | team                  | conference        |   covariate_component_roster_flux |   strength_margin |   strength_margin_sd |
|---------:|:----------------------|:------------------|----------------------------------:|------------------:|---------------------:|
|     2021 | Massachusetts         | FBS Independents  |                            -27.36 |            -56.92 |                 8.85 |
|     2020 | Akron                 | Mid-American      |                             11.09 |            -14.84 |                 7.72 |
|     2021 | New Mexico State      | FBS Independents  |                              7.80 |             -1.73 |                 8.37 |
|     2019 | UConn                 | American Athletic |                             -7.64 |            -30.04 |                 7.60 |
|     2020 | Massachusetts         | FBS Independents  |                             -7.57 |            -37.13 |                 7.67 |
|     2018 | Ball State            | Mid-American      |                              6.90 |            -15.16 |                 8.83 |
|     2021 | Florida International | Conference USA    |                              6.85 |             -4.79 |                 7.97 |
|     2019 | Rutgers               | Big Ten           |                             -6.29 |            -16.00 |                 7.53 |
|     2018 | Charlotte             | Conference USA    |                              6.19 |            -14.16 |                 8.79 |
|     2019 | Central Michigan      | Mid-American      |                             -6.11 |            -18.46 |                 7.62 |
|     2020 | Michigan              | Big Ten           |                             -5.98 |             11.49 |                 7.53 |
|     2018 | UTSA                  | Conference USA    |                             -5.91 |            -14.41 |                 8.75 |

Read this list, do not just count it: if the biggest movers are not teams whose rosters plausibly churned, the covariate is picking up something else and the finding is not real.

## 4. Face validity — end-of-season top 10

**2024**

| team       | conference       |   strength_margin |   strength_margin_sd |   strength_offense |   strength_defense |
|:-----------|:-----------------|------------------:|---------------------:|-------------------:|-------------------:|
| Notre Dame | FBS Independents |             26.96 |                 3.17 |              15.69 |              10.93 |
| Texas      | SEC              |             25.70 |                 3.20 |               9.23 |              16.00 |
| Ohio State | Big Ten          |             25.35 |                 3.45 |               9.28 |              15.54 |
| Georgia    | SEC              |             23.61 |                 3.35 |              13.15 |              10.51 |
| Alabama    | SEC              |             23.49 |                 3.63 |              10.92 |              12.18 |
| Oregon     | Big Ten          |             23.41 |                 3.29 |              13.58 |               9.73 |
| Ole Miss   | SEC              |             22.67 |                 3.42 |               9.43 |              12.78 |
| Penn State | Big Ten          |             20.94 |                 3.20 |              10.01 |              10.83 |
| Tennessee  | SEC              |             20.83 |                 3.26 |               8.41 |              12.00 |
| Indiana    | Big Ten          |             19.83 |                 3.44 |              12.01 |               6.98 |

**2025**

| team       | conference       |   strength_margin |   strength_margin_sd |   strength_offense |   strength_defense |
|:-----------|:-----------------|------------------:|---------------------:|-------------------:|-------------------:|
| Indiana    | Big Ten          |             32.02 |                 3.15 |              14.86 |              15.35 |
| Ohio State | Big Ten          |             30.72 |                 3.21 |              10.33 |              19.18 |
| Notre Dame | FBS Independents |             28.33 |                 3.12 |              15.70 |              12.09 |
| Texas Tech | Big 12           |             28.08 |                 3.08 |              12.68 |              13.85 |
| Oregon     | Big Ten          |             27.23 |                 3.33 |              12.80 |              13.20 |
| Miami      | ACC              |             22.41 |                 3.25 |               8.36 |              13.30 |
| Georgia    | SEC              |             22.06 |                 3.13 |               8.27 |              13.62 |
| Utah       | Big 12           |             19.91 |                 3.26 |              12.82 |               5.84 |
| Alabama    | SEC              |             19.10 |                 3.22 |               8.37 |              10.54 |
| Ole Miss   | SEC              |             19.00 |                 3.39 |              12.36 |               6.54 |

**Cross-check:** the margin model and the offense/defense model are INDEPENDENT fits. `strength_offense + strength_defense` correlates with `strength_margin` at **0.999**. (Sum, not difference — defense is signed as points PREVENTED.) A low value here means the two fits disagree about who is good and neither should be trusted.

## 5. Walk-forward accuracy (out-of-sample, vs realized margin — NOT vs a market)

| predictor        |   n_games |    mae |   rmse |   winner_accuracy |
|:-----------------|----------:|-------:|-------:|------------------:|
| strength model   |      8303 | 13.001 | 16.429 |             0.723 |
| home-field only  |      8303 | 16.436 | 20.986 |             0.578 |
| zero (coin flip) |      8303 | 16.743 | 21.292 |             0.420 |

**Mean absolute error by season:**

|   season |   n_games |   mae |
|---------:|----------:|------:|
|  2015.00 |    765.00 | 13.93 |
|  2016.00 |    759.00 | 13.68 |
|  2017.00 |    776.00 | 12.65 |
|  2018.00 |    772.00 | 13.18 |
|  2019.00 |    774.00 | 12.52 |
|  2020.00 |    515.00 | 13.46 |
|  2021.00 |    770.00 | 13.31 |
|  2022.00 |    776.00 | 12.76 |
|  2023.00 |    792.00 | 12.73 |
|  2024.00 |    797.00 | 12.69 |
|  2025.00 |    807.00 | 12.35 |

## 6. Is the emitted uncertainty honest?

- standardized-residual sd: **1.469** (1.00 = perfectly calibrated; >1 = overconfident, <1 = timid)
- standardized-residual mean: 0.024 (0 = unbiased)
- realized 80% interval coverage: 0.629 (target 0.80)
- realized 95% interval coverage: 0.823 (target 0.95)
- n = 8,303 games


**What this does and does NOT say.** `strength_margin_sd` is the posterior uncertainty in the STRENGTH PARAMETER, and on that job it behaves correctly — it decays monotonically as games accumulate and it is wider for thin-sample teams. The numbers above test something stricter: whether a GAME-LEVEL predictive interval built as `sqrt(residual_sigma^2 + sd_home^2 + sd_away^2)` is honest. It is not, by about the factor above (1.47x).

**The identified cause, stated rather than hand-waved.** `residual_sigma` comes from a RECENCY-WEIGHTED fit in which a game's variance is modelled as `sigma^2 / w`. The fitted `sigma` is therefore the variance a maximally-weighted (most recent) observation would have, not the average game's. Using it directly as a predictive residual understates the spread, and the shortfall is roughly `E[1/w]`. Two smaller contributors: the variance components are plugged in empirical-Bayes style rather than integrated over, and the offense/defense model treats a game's two team-rows as independent when they share weather, pace and officiating.

**Consequence for P1.4 — do not consume this as a calibrated predictive sd.** Use `strength_margin` as a point feature and `strength_margin_sd` as a RELATIVE confidence signal (it ranks teams' certainty correctly). If P1.4 needs a calibrated game-level interval it must recalibrate on held-out data, exactly as MLB's E13.6 did for served totals probabilities — recalibration is its own story, and pretending a structural sd is a predictive one is how a model ends up quietly overconfident in production.

## 7. Limitations

- **`strength_margin_sd` is PARAMETER uncertainty, not a calibrated predictive sd.** It is correct and well-behaved as a measure of how well the strength is pinned down, and it is ~1.5x too tight if used to build a game-level interval. §6 gives the measured factor and the identified cause (a recency-weighted `sigma`). P1.4 must recalibrate rather than consume it directly.
- **Empirical-Bayes plug-in.** `sigma`, `tau_team`, `tau_conference` and the covariate coefficients are point estimates from the prior-season fit, not integrated out.
- **Offense/defense residual correlation.** The points model's two rows per game share weather, pace and officiating; treating them as independent makes `strength_offense_sd` / `strength_defense_sd` mildly optimistic. Prefer `strength_margin_sd` when one honest uncertainty is needed.
- **The conference level is a POOLING level, not a claim.** `mu_conf` is where thin samples get shrunk to; it is not evidence that conference membership causes strength.
- **The first emitted season (2015) is thinly calibrated.** Its hyperparameters come from a single prior season (759 games) rather than the full lookback, so its shrinkage is less well tuned. This is disclosed per row via `hyper_n_prior_seasons` / `hyper_n_games` — P1.3/P1.4 can down-weight or drop it rather than discovering it downstream.
- **🚨 `strength_offense - strength_defense` is a trap.** Both are signed higher-is-better (defense = points PREVENTED), so a team's net strength is their SUM. Subtracting them returns ~0 for everyone. Use `strength_margin`.
- **Pre-2021 portal data does not exist** (`portal_data_covered = false`). Those seasons carry a `portal_net_stars_missing` indicator rather than a fabricated zero.
- **This model does not read `rollup_ncaaf_team_week_opponent_adjusted`.** P1.1's 2-pass schedule adjustment and this estimator are INDEPENDENT routes to opponent-adjusted strength; §5 lets them be compared rather than making one depend on the other. Fusing them is a P1.3/P1.4 question, not a P1.2 assumption.

## 8. Run notes

- season 2014: no prior season available; hyperparameters fit in-sample (seed season, NOT emitted)
- season 2018 [points]: variance-component optimizer did not converge: Maximum number of function evaluations has been exceeded.
- season 2019 [points]: variance-component optimizer did not converge: Maximum number of function evaluations has been exceeded.
- season 2020 [points]: variance-component optimizer did not converge: Maximum number of function evaluations has been exceeded.
- season 2021 [points]: variance-component optimizer did not converge: Maximum number of function evaluations has been exceeded.
- season 2023 [points]: variance-component optimizer did not converge: Maximum number of function evaluations has been exceeded.
- season 2025 [points]: variance component 'conf_def' hit a bound at 0.001 (unidentified)

