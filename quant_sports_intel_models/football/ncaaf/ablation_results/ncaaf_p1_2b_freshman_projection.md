# NCAAF-P1.2b — recruit-rating → freshman-production projection (the HS→college MLE)

**Status:** 🟢 **CODE-COMPLETE + synthetic-validated + CI-green + data-assembly runtime-verified
on the real lake (2026-07-20).** The numeric validation table (bake-off leaderboard, PBO/DSR,
projection↔realized correlation, face-validity lists) is produced by the operator's real
`run_freshman_projection.py` run over the 2014+ build — **this file is regenerated in full by that
run** and currently carries the design + the verified data-assembly facts. This mirrors P1.2's
"code-complete, validated on a real build by the operator" delivery.

> ⚠️ **This is a freshman PRIOR, not an edge claim.** It projects a recruit's first-college-season
> production from their recruiting rating, measured against realized production — never a market.
> `best_alpha = 0` holds; P1.4 decides whether a freshman feature earns its place. The uncertainty
> is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a calibrated predictive
> interval — a pricing consumer MUST recalibrate on held-out data.

---

## 1. What was built (the analog: MLB E7 MiLB→MLB MLE, one rung down)

A true freshman has **no college snaps**, so P1.3's snap-based roster features are blank for them.
The only pre-arrival signal is the **recruiting rating**, so it becomes the prior. P1.2b learns the
**recruit-rating → first-college-season production** map, position-specific, leakage-safe, and emits
a per-recruit prior + a team-level aggregate for P1.3.

| Layer | File | What |
|---|---|---|
| staging | `sports_dbt/.../stg_ncaaf_recruiting_players.sql` | flatten CFBD `/recruiting/players` (rating, stars, position, class, committed college) |
| staging | `sports_dbt/.../stg_ncaaf_roster.sql` (extended) | + `recruit_ids` (VARCHAR[]) — the bridge key |
| mart | `sports_dbt/.../ncaaf_recruit_production_pairs.sql` | the training/emission substrate: recruit → first-FBS-season production |
| model | `football/ncaaf/models/freshman_projection.py` | the §0.5 bake-off (4 candidate classes) + leakage-safe emission + team aggregate |
| CLI | `football/ncaaf/models/run_freshman_projection.py` | load → bake-off → gates → parquet/S3 → this report |
| view | `sports_dbt/.../ncaaf_freshman_priors.sql` | per-recruit prior (grain `player_id, arrival_season`) |
| view | `sports_dbt/.../ncaaf_team_freshman_prior.sql` | ⭐ the **P1.3 join contract** (grain `season, team`) |
| tests | `betting_ml/tests/test_ncaaf_freshman_projection.py` | 14 fast-gate behavioural + leakage guards |

## 2. 🔧 The bridge — a corrected data-inventory error (verified on the real lake)

`ncaaf_data_inventory.md` documented the recruit↔college link as **recruiting.athleteId ↔
roster.recruitIds**. On the real lake that matches **7 rows across 12 seasons** — effectively dead.
The link that actually works is **roster.recruit_ids ↔ recruiting_players.id** (the recruiting
RECORD id): **60,883 unnested matches → 8,373 distinct bridged freshmen** at their first FBS season,
2014–2025 (~760/class). Every bridged recruit carries a composite rating. The data inventory has
been corrected. This is exactly the "verify a documented key on the real data" runtime-gate class —
CI (which mocks IO) could not have caught it.

## 3. 🔬 The §0.5 bake-off (this is a MODEL, not a lookup)

Pre-registered candidate set — every config counts toward PBO/DSR (deflation makes the search safe):

- **(a) ⭐ Partial pooling** via `hierarchical.py` (the P1.2 solver, **reused unchanged**): a
  random-slopes model — a GLOBAL rating→production line plus per-position-group intercept AND
  rating-slope deviations, EB-shrunk toward the global line. This IS "position-specific + EB-shrunk
  for thin cells," and it inherits the **boundary-avoiding Gamma(2,·) tau prior + multi-start** that
  the P1.2 build proved is MANDATORY (ML genuinely collapses a variance component to 0 on thin
  cells, silently deleting a level of the hierarchy — a live bug there). A fast-gate test pins that
  the variance components stay alive.
- **(b) Position-stratified OLS** on rating — the interpretable foil (no pooling between cells).
- **(c) Learned GBM** on rating + stars + national_ranking + position one-hot + class size.
- **(d) Position-mean NULL FLOOR** — predict the group mean, ignore rating. The honest "no signal"
  baseline every candidate must beat.

**Selection:** leave-one-CLASS-out **expanding-window** CV (project class Y using ONLY strictly-prior
classes) on held-out MAE of the standardized production target; **PBO** over folds×configs; **DSR**
on the winner's per-fold skill (n_trials = config count); and an **ORACLE-FLOOR** sanity check
(a target-seeing model must beat every candidate — a candidate beating it is the E2.1-r
inverted-metric tell). *(A high PBO on a genuinely-tied field is the NULL, not overfitting — read
the leaderboard spread, per the E2.1-r discipline.)*

## 4. The target (why standardized, why leakage-free)

Production is position-incomparable (QB passing yards vs a corner's tackles), so the raw metric is
chosen per group (offense: scrimmage yards + TD bonus; defense: havoc = tackles + 2·(sacks+TFL) +
3·(PBU+INT)) and then **z-scored within (position_group, arrival_season)**. Standardization makes
the raw scale irrelevant (only within-group-season ordering matters) and absorbs league drift. It is
leakage-free: it only builds the TRAINING label on completed classes; emission predicts z from
rating and never needs the new class's production.

**OL and deep special teams record no box stat line** — participation-via-stats reads ~0 for every
lineman — so they carry **no production label** and get a **rating-only prior**, flagged
`box_production_available = false`, and are excluded from the production VALIDATION. Their prior is a
talent signal, honestly labelled, never a fabricated 0.

## 5. Output grain + the P1.3 join contract (PM addition #3)

- **`ncaaf_freshman_priors`** — grain **(player_id, arrival_season)**: `projected_production_z`
  (mean), `projected_production_z_sd` (parameter uncertainty), `box_production_available`,
  `n_prior_classes`, `n_prior_pairs`, `model_version`.
- **`ncaaf_team_freshman_prior`** — grain **(season, team)** = the P1.3 slot. Columns:
  `n_incoming_freshmen`, `freshman_class_projected_production` (Σ), `freshman_class_avg_projected_production`,
  `freshman_class_top_projected_production`, `freshman_class_avg_rating`, `blue_chip_count`.
  **P1.3 joins on `(season = arrival_season, team = arrival_team)` and broadcasts to every
  `as_of_week`** (the freshman prior is a pre-season constant). A team with no bridged class is
  ABSENT → LEFT JOIN and read absence as zero projected contribution.

## 6. Uncertainty semantics (PM addition #4)

`projected_production_z_sd` is **PARAMETER** uncertainty (posterior/quantile sd of the fitted map at
this recruit's rating), NOT a calibrated predictive interval for realized production. Like P1.2's
`strength_margin_sd` it ranks confidence correctly but is too tight to price with — **any pricing
consumer must recalibrate on held-out data** (the E13.6 pattern). P1.3 uses `projected_production_z`
as a POINT feature and the sd as a RELATIVE confidence signal only.

## 7. Behavioural gates (PM addition #5) — verified

- **Synthetic bake-off** recovers a planted rating→production signal; the winner beats the null
  floor; partial pooling demonstrably shrinks a thin position cell; the tau prior keeps the group
  level alive; PBO/DSR compute. (14 fast-gate tests, 5.9s.)
- **Leakage is CLASS-based and verified to FAIL on a tamper:** a FUTURE class's production cannot
  move an earlier class's prior (guard), AND tampering a PRIOR (training) class DOES move the
  downstream prior (the complement — so "no change on future tamper" means something). The seed
  class (2014) is never emitted; every prior has ≥1 strictly-prior class.
- **Oracle-floor** holds (no candidate beats a target-seeing oracle).
- **Real-lake runtime check:** the novel bridge SQL (`unnest(recruit_ids)`, `try_cast(... as
  varchar[])`, the dedup `row_number`, arrival = min FBS season) executes over the real Delta lake
  and yields the 8,373-freshman substrate. The dbt project **parses + compiles** clean (CI gate).

## 8. Limitations (carried into P1.3/P1.4)

- Uncertainty is parameter-only (recalibrate before pricing).
- OL/ST have no validated production projection (rating-only prior).
- The target is within-(group, class) relative production, not absolute yardage.
- JUCO/PrepSchool excluded by default (`recruit_types`) — a different, older-arrival translation.
- Empirical-Bayes plug-in variance components (the P1.2 posture).

## 9. ⏭️ Operator validation run (regenerates §3–§5 numbers)

See the story's Operator Handoff — the box command runs the bake-off over the real 2014+ build,
lands the priors in the lake (`--s3`), and rewrites this report with the leaderboard, PBO/DSR,
projection↔realized correlation, and face-validity lists. **Acceptance:** a position-specific
recruit→production prior (mean + uncertainty), validated on a holdout recruit class (the CV winner
beats the position-mean null), that feeds P1.3 as the true-freshman feature.
