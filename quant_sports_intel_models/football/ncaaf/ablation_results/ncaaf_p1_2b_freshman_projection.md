# NCAAF-P1.2b — recruit-rating → freshman-production projection (the HS→college MLE)

**Model:** `ncaaf_freshman_projection_v1` · **generated:** 2026-07-22T01:25:32.469255+00:00
**Classes emitted:** 2015–2025 (16,541 recruit priors) · **seed (not emitted):** 2014

> ⚠️ **This is a freshman PRIOR, not an edge claim.** It projects a recruit's first-season production from their recruiting rating, measured against realized production — never a market. `best_alpha = 0` holds; P1.4 decides whether a freshman feature earns its place. The uncertainty is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a calibrated predictive interval — a pricing consumer MUST recalibrate on held-out data.

## 1. Gates

- ✅ seed class 2014 not emitted (no strictly-prior map exists)
- ✅ every emitted prior was fit on strictly-prior recruit classes (n_prior ≥ 1)
- ✅ per-recruit grain (player_id, arrival_season) is unique
- ✅ projection finite + plausible (|z|≤2.72, sd≤2.56)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the position-mean null OOS (MAE 0.7011 < 0.7164)
- ✅ PBO computed = 0.000 over 6 configs (<0.2 ✅)
- ✅ DSR computed = 0.821 (n_trials=6)

## 2. The §0.5 bake-off leaderboard (leave-one-class-out expanding-window CV)

Every candidate is fit on STRICTLY-PRIOR classes and scored on the held-out class; the metric is MAE on the standardized production target (lower = better). `position_mean` is the NULL FLOOR (ignores rating). `oos_skill_vs_null` = how much MAE the config removes vs that null (>0 ⇒ the recruiting rating carries signal).

| config           |   oos_mae |   oos_skill_vs_null |
|:-----------------|----------:|--------------------:|
| gbm@200-2-0.05   |    0.7011 |              0.0154 |
| gbm@400-3-0.03   |    0.7091 |              0.0073 |
| partial_pool@2.0 |    0.7150 |              0.0014 |
| partial_pool@4.0 |    0.7150 |              0.0014 |
| stratified_ols   |    0.7160 |              0.0004 |
| position_mean    |    0.7164 |              0.0000 |

**Winner:** `gbm@200-2-0.05`, refit on all 11 emittable classes for emission.

## 3. Overfitting deflation (PBO / DSR)

- **PBO** = 0.000 over 6 configs × 8 CSCV splits.
  - ⚠️ **Reading a high PBO correctly (E2.1-r):** if the top configs genuinely TIE, a high PBO is the NULL (which tied candidate wins is noise), not evidence of overfitting. A high PBO with a WIDE leaderboard spread IS overfitting. Read the spread above.
- **DSR** = 0.821 (observed skill-Sharpe 0.880 vs deflated floor 0.392, n_trials=6). ≥0.95 = the winner's OOS skill survives the multiple-testing deflation.

## 4. Does the projection track reality? (rating → realized freshman production)

Correlation of the emitted `projected_production_z` with the recruit's REALIZED standardized production, per position group (emitted rows that DID produce — a true out-of-sample read, since each class's prior was fit only on strictly-prior classes). A positive, position-plausible correlation is the behavioural gate that the map learned something; a flat correlation means the recruiting rating does not predict production and the honest verdict is no signal.

| group   |   proj↔realized corr |
|:--------|---------------------:|
| ALL     |                0.204 |
| ATH     |                0.024 |
| DB      |                0.152 |
| DL      |                0.283 |
| LB      |                0.143 |
| QB      |                0.183 |
| RB      |                0.201 |
| TE      |                0.299 |
| WR      |                0.268 |

## 5. Face validity — the top projected freshmen (most recent class)

**2025 class:**

| recruit_name      | arrival_team   | position_group   |   stars |   composite_rating |   projected_production_z |   projected_production_z_sd |
|:------------------|:---------------|:-----------------|--------:|-------------------:|-------------------------:|----------------------------:|
| Elijah Griffin    | Georgia        | DL               |       5 |              0.999 |                    1.728 |                       1.752 |
| Keelon Russell    | Alabama        | QB               |       5 |              1.000 |                    1.611 |                       1.759 |
| Bryce Underwood   | Michigan       | QB               |       5 |              1.000 |                    1.611 |                       1.759 |
| Tavien St. Clair  | Ohio State     | QB               |       5 |              0.997 |                    1.155 |                       1.479 |
| David Sanders Jr. | Tennessee      | OL               |       5 |              0.997 |                    1.114 |                       1.748 |
| Dakorien Moore    | Oregon         | WR               |       5 |              0.998 |                    1.114 |                       1.762 |
| Michael Fasusi    | Oklahoma       | OL               |       5 |              0.998 |                    1.114 |                       1.748 |
| Justus Terry      | Texas          | DL               |       5 |              0.994 |                    1.068 |                       1.420 |
| DJ Pickett        | LSU            | DB               |       5 |              0.994 |                    1.049 |                       1.393 |
| Harlem Berry      | LSU            | RB               |       5 |              0.992 |                    1.018 |                       1.479 |
| Andrew Babalola   | Michigan       | OL               |       5 |              0.991 |                    1.011 |                       1.433 |
| Jerome Myles      | Texas A&M      | WR               |       5 |              0.988 |                    1.009 |                       1.412 |

Read the list, do not just count it: the top projected freshmen should be blue-chip recruits at skill positions. If they are not, the map is picking up something else.

## 6. The P1.3 team aggregate (the join contract)

Grain **(season, team)** — a PRE-SEASON constant that P1.3 broadcasts to every `as_of_week` by joining on `(season = arrival_season, team = arrival_team)`. Columns: `n_incoming_freshmen`, `freshman_class_projected_production` (Σ over the class), `freshman_class_avg_projected_production`, `freshman_class_top_projected_production`, `freshman_class_avg_rating`, `blue_chip_count`. A team absent from this table has no bridged incoming class — LEFT JOIN and read the absence as zero projected contribution.

1,424 (season, team) rows. Top projected incoming classes (2025):

| team       |   n_incoming_freshmen |   freshman_class_projected_production |   freshman_class_avg_rating |   blue_chip_count |
|:-----------|----------------------:|--------------------------------------:|----------------------------:|------------------:|
| Texas      |                    22 |                                  6.53 |                        0.94 |                18 |
| Georgia    |                    20 |                                  6.10 |                        0.94 |                20 |
| Alabama    |                    18 |                                  5.38 |                        0.93 |                15 |
| Ohio State |                    18 |                                  4.23 |                        0.93 |                16 |
| LSU        |                    21 |                                  3.02 |                        0.92 |                21 |
| Oregon     |                    17 |                                  2.69 |                        0.93 |                15 |
| Michigan   |                    13 |                                  2.61 |                        0.93 |                 9 |
| Auburn     |                    20 |                                  2.50 |                        0.93 |                17 |
| Florida    |                    19 |                                  2.36 |                        0.92 |                16 |
| Texas A&M  |                    22 |                                  2.12 |                        0.92 |                19 |

## 7. Limitations

- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks confidence correctly, too tight to price. P1.3/P1.4 must recalibrate (E13.6 pattern).
- **OL and special teams have NO box production** (`box_production_available = False`): a lineman logs no stat line, so participation-via-stats reads ~0 for all of them. They get a rating-only prior from the global line and are excluded from the production VALIDATION. Their prior is a talent signal, not a validated production projection.
- **The target is WITHIN-(group, season) standardized** — it captures who produced more AMONG their positional peers that class, not an absolute yardage. That is the honestly learnable signal (rating orders within-class production); absolute cross-position production is not comparable and is not claimed.
- **The bridge is roster.recruit_ids ↔ recruiting.id** (NOT athleteId — the data-inventory doc was wrong; corrected). ~19k pairs; a recruit with no roster recruitIds link (walk-ons, some transfers) is simply absent — a coverage limit, not a bias claim.
- **JUCO/PrepSchool recruits are excluded by default** (`recruit_types`) — they arrive older and are a different translation than the clean HS→college signal.
- **Empirical-Bayes plug-in** (partial-pool winner): the variance components are point estimates, not integrated over — the same posture as P1.2 and MLB's bullpen posteriors.

