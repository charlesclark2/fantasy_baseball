# MLB Edge-E7.12 SLICE 1 — minor-league PARK factors, per-LEVEL run environment, and the small-sample hardening of the MiLB→MLB MLE

**generated:** 2026-08-01T01:02:39.779837+00:00 · **baseline:** the E7.3 incumbent (`milb_mle_v1`, `partial_pool`) · **learner held FIXED per metric**

> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.** This slice asks one question: does adjusting a prospect's minor-league rate for WHERE (park), WHEN (level×season run environment) and HOW MUCH (sample reliability) he accumulated it translate BETTER than the raw rate the E7.3 partial-pool sees today? A rung that does not clear its deflated gate is **DROPPED, not shipped** — the 8/3 draft board is a low-risk surface, which lowers the bar for shipping a CLEARED win, not the bar for what counts as one.

## 0. Pre-registration (written before the run)

| rung | kind | mechanism |
|:--|:--|:--|
| `S0_baseline` | ladder | the E7.3 incumbent, byte-exact (ContextSpec() is a no-op) |
| `S1_park_exposure` | ladder | ⭐ per-player PA-EXPOSURE-weighted leave-one-player-out park factor (our game-log advantage) |
| `S1f_park_halfweight` | ladder | the research memo's prescription verbatim: (1+PF_home)/2, the half-weight multiplier |
| `S2_level_env` | ladder | level×SEASON run environment normalised to the level's pooled baseline |
| `S3_park_env` | ladder | park + run environment together (where + when) |
| `S4_park_env_rel0.5` | ladder | + per-component reliability shrink at HALF the literature stabilisation point |
| `S4_park_env_rel1.0` | ladder | + per-component reliability shrink at the literature stabilisation point |
| `S4_park_env_rel2.0` | ladder | + per-component reliability shrink at DOUBLE the stabilisation point (harder regression) |
| `S5_full_labelweight` | ladder | + label-precision observation weights (a 150-PA rookie label is a noisier observation) |
| `I_reliability_only` | isolation | the small-sample hardening ALONE, no park, no run environment |
| `I_labelweight_only` | isolation | label-precision weights ALONE |
| `A_park_placebo` | anchor | DEGENERATE CEILING — the same park factors permuted across players within a level |
| `A_park_noloo` | anchor | DIAGNOSTIC — park factor WITHOUT the leave-one-player-out subtraction (self-shrinkage) |
| `A_rel_constant` | anchor | DEGENERATE — everyone shrunk by the population-mean r (no PA variation) |

**Per-component stabilisation points** driving the reliability shrink (`r = PA/(PA+k)`): `woba` k=470 PA · `k_pct` k=60 PA · `bb_pct` k=120 PA · `iso` k=160 PA. At 160 PA that keeps 73% of an observed K% deviation and only 50% of an ISO deviation — **ISO is regressed ~2.7× harder than K% at equal sample**, which is the measured translatability ordering (E7.3: K% 0.637 · BB% 0.491 · ISO 0.429) expressed as a prior rather than asserted.

**Gate for an ADD** (all must hold): a strict out-of-sample MAE improvement over the E7.3 incumbent, in **≥60% of held-out debut cohorts**; the arm must have MOVED >1% of rows (a dead join is not a null); the **placebo** park must lose; the **non-LOO** park must not beat the LOO park; and the deflation must be readable as a real separation rather than a tie (PBO + flip distribution + Bailey degradation + contender spread, all four reported).

## 1. Is the context join even ALIVE? (the run-level silent-empty guard)

A park arm that moves nothing has two causes that look identical at the arm level: a **dead join** (this repo's recurring silent-empty class) or a **genuinely neutral factor** for that metric — which is precisely what the falsification below predicts for K%/BB%. The distinguisher is cross-metric, so it is asked once, here, and it HALTs the run rather than producing four plausible-looking nulls.

- max % of rows moved, by metric: `{'woba': 100.0, 'k_pct': 100.0, 'bb_pct': 100.0, 'iso': 100.0}`
- ✅ the context join moves at least one metric — a per-metric no-op is a neutral factor, not a dead join.

## 2. Directional falsification — is it actually the PARK?

Parks move **balls in play**. Pre-registered before the run: a genuine park effect must be concentrated in ISO/wOBA and near-zero for K%/BB%. A lift that appears uniformly across all four metrics is generic shrinkage wearing a park costume.

- mean park lift on **iso, woba** (ball-in-play): **0.478%**
- mean park lift on **k_pct, bb_pct** (discipline): **0.126%**

> ✅ the park lift is concentrated in the ball-in-play metrics, which is what a park mechanism must look like.

## 2b. ⭐ WHICH MECHANISM ACTUALLY WON — the isolation arms

This is the headline, and it is **not what the story predicted**. The research memo ranked "minor-league park factors + per-level run environment" as ONE workstream and as the single biggest gap. Splitting that bullet into its two halves — which is exactly what the isolation arms are for — shows the two halves are **nothing like equal partners**.

| metric   |   park ALONE % |     p |   run-env ALONE % |    p  |   reliability ALONE % |   label-weight ALONE % |   placebo park % |   winner % |
|:---------|---------------:|------:|------------------:|------:|----------------------:|-----------------------:|-----------------:|-----------:|
| woba     |          0.121 | 0.283 |             0.761 | 0.094 |                -0.183 |                 -6.409 |           -0.163 |      0.761 |
| k_pct    |          0.41  | 0.031 |             3.234 | 0.026 |                 0.045 |                  1.821 |           -0.667 |      3.5   |
| bb_pct   |         -0.158 | 0.805 |             2.799 | 0.016 |                 0.482 |                 -1.924 |           -0.522 |      3.337 |
| iso      |          0.836 | 0     |             3.383 | 0.013 |                 0.435 |                 -4.407 |           -0.352 |      5.06  |

**Read it straight:**

- **The level×SEASON run environment is the mechanism.** It is the only rung that lifts all four metrics, and it is **4–17× the size of the park effect** on every one of them.
- **The park factor is real but small, and only for ISO** (+0.84%, 11/11 folds, p≈0.0001 — the cleanest single result in the run). On K% it is marginal, on wOBA it is a null, and on BB% it is **negative**. That is a coherent physical story — parks move balls in play — and it is exactly the direction the falsification pre-registered; it is simply a much SMALLER story than "the single biggest gap" implied.
- **The placebo park is NEGATIVE on all four metrics.** A wrong park factor actively hurts, which is the strongest available evidence that the small real park effect is a venue effect and not generic shrinkage.
- **Label-precision weighting is a clean pre-registered NULL** — decisively negative on three of four metrics (wOBA −6.4%, ISO −4.4%, BB% −1.9%). Dropped, as pre-registered.
- **Reliability shrinkage is a real but secondary interaction**: near-zero on its own (+0.04% to +0.48%) yet it adds ~1.5pp on top of park+run-env for ISO and BB%. It hardens the small-sample regime rather than carrying the signal itself.

⚠️ **What the run-environment rung actually is.** `rate × env_level / env_player` re-expresses a player's rate against his own level-season league baseline, so it removes league-wide offensive drift (ball, level composition, pitch clock) that the pool's per-LEVEL intercept cannot see because it has no per-SEASON term. That is an **era/context normalisation**, not a park correction — legitimate and leakage-free (every input is pre-debut MiLB, no MLB label is touched), but it should be named for what it is. The honest one-line summary of this slice is *"the MLE was missing a season-context adjustment, and secondarily a park adjustment for power"* — not *"park factors were the big miss."*

ℹ️ `env_level_<metric>` (the anchor constant) is pooled over every season in the artifact, including seasons after a given fold's training cohorts. It is a single constant per (level, metric) applied identically to train and test, and the pool carries per-level intercepts AND slopes, so it is absorbed rather than informative — a benign look-ahead, stated rather than hidden. The player-varying term, `env_<metric>`, is strictly as-of his own pre-debut seasons.

## 3. Verdict by metric

| metric   | verdict   | winner             |   best_rung_pct_lift |   fold_win_rate |   p_one_sided | BH-FDR@0.10   |   PBO(eligible) |   contender_spread_% |   Bailey_os_gap_% |
|:---------|:----------|:-------------------|---------------------:|----------------:|--------------:|:--------------|----------------:|---------------------:|------------------:|
| woba     | ADD       | S2_level_env       |                0.932 |            0.73 |     0.060269  | True          |       0.271429  |                0.173 |            0.3023 |
| k_pct    | ADD       | S4_park_env_rel0.5 |                3.5   |            0.73 |     0.0211077 | True          |       0.3       |                0.059 |            0.4261 |
| bb_pct   | ADD       | S4_park_env_rel2.0 |                3.337 |            0.82 |     0.0158411 | True          |       0.0142857 |                0.318 |            0      |
| iso      | ADD       | S4_park_env_rel2.0 |                5.06  |            0.91 |     0.0018848 | True          |       0         |                0.294 |            0.1636 |

`PBO(eligible)` is computed over the ELIGIBLE arms — the search the selection actually ran — not over every arm scored; the whole-field figure is in the JSON. A field that CONTAINS its own anchors has a huge dispersion, and a deflation statistic computed over it measures the anchors (the NF-D14 lesson).

## 4.woba — the ladder (`partial_pool@4`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `woba` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S3_park_env         | ladder    | True     |   0.02874 |          0.93191 |         0.72727 |       0.06027 |        100.00000 |               0.01194 |
| S4_park_env_rel0.5  | ladder    | True     |   0.02877 |          0.82094 |         0.36364 |       0.10247 |        100.00000 |               0.05864 |
| S2_level_env        | ladder    | True     |   0.02879 |          0.76068 |         0.72727 |       0.09387 |        100.00000 |               0.01020 |
| S4_park_env_rel1.0  | ladder    | True     |   0.02881 |          0.69287 |         0.27273 |       0.16228 |        100.00000 |               0.06332 |
| S4_park_env_rel2.0  | ladder    | True     |   0.02885 |          0.55825 |         0.36364 |       0.23240 |        100.00000 |               0.06716 |
| S1f_park_halfweight | ladder    | True     |   0.02897 |          0.15243 |         0.45455 |       0.29705 |         95.34000 |               0.00861 |
| A_park_noloo        | anchor    | True     |   0.02897 |          0.15029 |         0.63636 |       0.24404 |        100.00000 |               0.00862 |
| S1_park_exposure    | ladder    | True     |   0.02897 |          0.12126 |         0.63636 |       0.28286 |        100.00000 |               0.00863 |
| S0_baseline         | ladder    | True     |   0.02901 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00360 |
| A_rel_constant      | anchor    | True     |   0.02903 |         -0.06377 |         0.45455 |       0.88315 |        100.00000 |               0.03612 |
| A_park_placebo      | anchor    | True     |   0.02906 |         -0.16288 |         0.36364 |       0.79873 |        100.00000 |               0.00889 |
| I_reliability_only  | isolation | True     |   0.02906 |         -0.18323 |         0.45455 |       0.68467 |        100.00000 |               0.06245 |
| S5_full_labelweight | ladder    | True     |   0.03048 |         -5.05580 |         0.09091 |       0.99511 |        100.00000 |               0.06332 |
| I_labelweight_only  | isolation | True     |   0.03087 |         -6.40906 |         0.09091 |       0.99651 |          0.00000 |               0.00360 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 6/11 folds, p=0.873 (α=0.1), mean gap +8.24e-05
- non-LOO vs leave-one-player-out: **⛔ VIOLATED** — the degenerate wins 9/11 folds, p=0.035 (α=0.1), mean gap -8.42e-06
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 5/11 folds, p=0.378 (α=0.1), mean gap -3.47e-05
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.2714285714285714` · contender (top-quartile) spread: `0.173%` · full-field spread: `7.41%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.3023%` (p90 `1.8433%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| S3_park_env         |            222 |   0.481 |        0.02874 |         0     |
| S4_park_env_rel0.5  |             79 |   0.171 |        0.02877 |         0.112 |
| S4_park_env_rel2.0  |             58 |   0.126 |        0.02885 |         0.377 |
| S1f_park_halfweight |             50 |   0.108 |        0.02897 |         0.787 |
| S2_level_env        |             20 |   0.043 |        0.02879 |         0.173 |
| S4_park_env_rel1.0  |             18 |   0.039 |        0.02881 |         0.241 |

- ⛔ PARK DISQUALIFIED — the NON-LOO factor systematically beat the leave-one-player-out one (9/11 folds, p=0.035, mean gap -8.42e-06). The park arm's apparent edge here is the player shrinking HIMSELF toward the mean via his own contribution to his park's factor. Park arms are removed from selection for this metric; the non-park rungs are unaffected and still judged on their merits.
- ✅ `S2_level_env` beats the E7.3 incumbent OOS (0.02879 vs 0.02901, 0.76%) in 73% of folds.

## 4.k_pct — the ladder (`partial_pool@2`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `k_pct` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S4_park_env_rel0.5  | ladder    | True     |   0.03845 |          3.50047 |         0.72727 |       0.02111 |        100.00000 |               0.05705 |
| S3_park_env         | ladder    | True     |   0.03845 |          3.47850 |         0.72727 |       0.02156 |        100.00000 |               0.02151 |
| S4_park_env_rel1.0  | ladder    | True     |   0.03847 |          3.44388 |         0.63636 |       0.02407 |        100.00000 |               0.06281 |
| S2_level_env        | ladder    | True     |   0.03855 |          3.23425 |         0.63636 |       0.02625 |        100.00000 |               0.02096 |
| S4_park_env_rel2.0  | ladder    | True     |   0.03857 |          3.19908 |         0.72727 |       0.03686 |        100.00000 |               0.06865 |
| S5_full_labelweight | ladder    | True     |   0.03880 |          2.61634 |         0.54545 |       0.11005 |        100.00000 |               0.06281 |
| I_labelweight_only  | isolation | True     |   0.03912 |          1.82064 |         0.81818 |       0.01201 |          0.00000 |               0.00212 |
| A_park_noloo        | anchor    | True     |   0.03967 |          0.41680 |         0.72727 |       0.02736 |        100.00000 |               0.00707 |
| S1_park_exposure    | ladder    | True     |   0.03968 |          0.40991 |         0.72727 |       0.03110 |        100.00000 |               0.00708 |
| S1f_park_halfweight | ladder    | True     |   0.03973 |          0.28255 |         0.63636 |       0.17048 |         95.34000 |               0.00693 |
| I_reliability_only  | isolation | True     |   0.03982 |          0.04497 |         0.54545 |       0.44503 |        100.00000 |               0.05541 |
| S0_baseline         | ladder    | True     |   0.03984 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00212 |
| A_rel_constant      | anchor    | True     |   0.03984 |         -0.00139 |         0.36364 |       0.55515 |        100.00000 |               0.01249 |
| A_park_placebo      | anchor    | True     |   0.04011 |         -0.66667 |         0.18182 |       0.98435 |        100.00000 |               0.00716 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 2/11 folds, p=0.991 (α=0.1), mean gap +4.29e-04
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 5/11 folds, p=0.331 (α=0.1), mean gap -2.75e-06
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 5/11 folds, p=0.557 (α=0.1), mean gap +1.85e-05
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.3` · contender (top-quartile) spread: `0.059%` · full-field spread: `3.627%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.4261%` (p90 `1.9754%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| S3_park_env         |            147 |   0.318 |        0.03845 |         0.023 |
| S4_park_env_rel1.0  |             92 |   0.199 |        0.03847 |         0.059 |
| S4_park_env_rel2.0  |             74 |   0.16  |        0.03857 |         0.312 |
| S2_level_env        |             49 |   0.106 |        0.03855 |         0.276 |
| S4_park_env_rel0.5  |             44 |   0.095 |        0.03845 |         0     |
| S5_full_labelweight |             30 |   0.065 |        0.0388  |         0.916 |

- ✅ `S4_park_env_rel0.5` beats the E7.3 incumbent OOS (0.03845 vs 0.03984, 3.50%) in 73% of folds.

## 4.bb_pct — the ladder (`partial_pool@4`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `bb_pct` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S4_park_env_rel2.0  | ladder    | True     |   0.01796 |          3.33678 |         0.81818 |       0.01584 |        100.00000 |               0.03365 |
| S4_park_env_rel1.0  | ladder    | True     |   0.01798 |          3.22762 |         0.81818 |       0.01424 |        100.00000 |               0.03107 |
| S4_park_env_rel0.5  | ladder    | True     |   0.01802 |          3.02929 |         0.81818 |       0.01553 |        100.00000 |               0.02865 |
| S2_level_env        | ladder    | True     |   0.01806 |          2.79872 |         0.90909 |       0.01638 |        100.00000 |               0.01163 |
| S3_park_env         | ladder    | True     |   0.01810 |          2.59606 |         0.81818 |       0.02341 |        100.00000 |               0.01176 |
| S5_full_labelweight | ladder    | True     |   0.01823 |          1.85135 |         0.54545 |       0.13929 |        100.00000 |               0.03107 |
| I_reliability_only  | isolation | True     |   0.01849 |          0.48150 |         0.72727 |       0.05018 |        100.00000 |               0.02687 |
| S0_baseline         | ladder    | True     |   0.01858 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00083 |
| A_rel_constant      | anchor    | True     |   0.01858 |         -0.00302 |         0.36364 |       0.79931 |        100.00000 |               0.00994 |
| S1_park_exposure    | ladder    | True     |   0.01861 |         -0.15750 |         0.36364 |       0.80528 |        100.00000 |               0.00244 |
| S1f_park_halfweight | ladder    | True     |   0.01861 |         -0.16400 |         0.45455 |       0.79065 |         95.34000 |               0.00251 |
| A_park_noloo        | anchor    | True     |   0.01861 |         -0.18635 |         0.36364 |       0.81933 |        100.00000 |               0.00244 |
| A_park_placebo      | anchor    | True     |   0.01868 |         -0.52226 |         0.00000 |       0.99882 |        100.00000 |               0.00254 |
| I_labelweight_only  | isolation | True     |   0.01894 |         -1.92401 |         0.18182 |       0.99726 |          0.00000 |               0.00083 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 3/11 folds, p=0.934 (α=0.1), mean gap +6.78e-05
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 5/11 folds, p=0.875 (α=0.1), mean gap +5.36e-06
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 3/11 folds, p=0.952 (α=0.1), mean gap +9.00e-05
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.014285714285714285` · contender (top-quartile) spread: `0.318%` · full-field spread: `5.442%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.0%` (p90 `1.153%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| S4_park_env_rel2.0  |            338 |   0.732 |        0.01796 |         0     |
| S4_park_env_rel1.0  |             62 |   0.134 |        0.01798 |         0.113 |
| S2_level_env        |             38 |   0.082 |        0.01806 |         0.557 |
| I_reliability_only  |             10 |   0.022 |        0.01849 |         2.954 |
| S4_park_env_rel0.5  |             10 |   0.022 |        0.01802 |         0.318 |
| S5_full_labelweight |              3 |   0.006 |        0.01823 |         1.537 |

- ✅ `S4_park_env_rel2.0` beats the E7.3 incumbent OOS (0.01796 vs 0.01858, 3.34%) in 82% of folds.

## 4.iso — the ladder (`partial_pool@2`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `iso` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S4_park_env_rel2.0  | ladder    | True     |   0.03847 |          5.06007 |         0.90909 |       0.00188 |        100.00000 |               0.05179 |
| S4_park_env_rel1.0  | ladder    | True     |   0.03850 |          4.97324 |         1.00000 |       0.00154 |        100.00000 |               0.04659 |
| S4_park_env_rel0.5  | ladder    | True     |   0.03858 |          4.78114 |         1.00000 |       0.00184 |        100.00000 |               0.04162 |
| S3_park_env         | ladder    | True     |   0.03877 |          4.30518 |         0.90909 |       0.00321 |        100.00000 |               0.01226 |
| S2_level_env        | ladder    | True     |   0.03915 |          3.38302 |         0.90909 |       0.01269 |        100.00000 |               0.01099 |
| S5_full_labelweight | ladder    | True     |   0.03982 |          1.71366 |         0.45455 |       0.06044 |        100.00000 |               0.04659 |
| S1f_park_halfweight | ladder    | True     |   0.04016 |          0.88128 |         0.90909 |       0.00183 |         95.34000 |               0.00600 |
| S1_park_exposure    | ladder    | True     |   0.04018 |          0.83570 |         1.00000 |       0.00006 |        100.00000 |               0.00586 |
| A_park_noloo        | anchor    | True     |   0.04018 |          0.82867 |         1.00000 |       0.00005 |        100.00000 |               0.00584 |
| I_reliability_only  | isolation | True     |   0.04034 |          0.43529 |         0.72727 |       0.13533 |        100.00000 |               0.04319 |
| A_rel_constant      | anchor    | True     |   0.04051 |          0.02664 |         0.63636 |       0.19275 |        100.00000 |               0.01808 |
| S0_baseline         | ladder    | True     |   0.04052 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00035 |
| A_park_placebo      | anchor    | True     |   0.04066 |         -0.35247 |         0.36364 |       0.84400 |        100.00000 |               0.00635 |
| I_labelweight_only  | isolation | True     |   0.04230 |         -4.40685 |         0.18182 |       0.99858 |          0.00000 |               0.00035 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 2/11 folds, p=0.998 (α=0.1), mean gap +4.81e-04
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 4/11 folds, p=0.717 (α=0.1), mean gap +2.85e-06
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 3/11 folds, p=0.857 (α=0.1), mean gap +1.66e-04
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.0` · contender (top-quartile) spread: `0.294%` · full-field spread: `9.971%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.1636%` (p90 `0.7639%`)
- flip distribution (which arms win the in-sample halves):

| config             |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:-------------------|---------------:|--------:|---------------:|--------------:|
| S4_park_env_rel2.0 |            290 |   0.628 |        0.03847 |         0     |
| S4_park_env_rel1.0 |            100 |   0.216 |        0.0385  |         0.091 |
| S4_park_env_rel0.5 |             57 |   0.123 |        0.03858 |         0.294 |
| S3_park_env        |             15 |   0.032 |        0.03877 |         0.795 |

- ✅ `S4_park_env_rel2.0` beats the E7.3 incumbent OOS (0.03847 vs 0.04052, 5.06%) in 91% of folds.

## 5. What was applied

| metric   | rung               | context_spec                    |   n_rows | gates                                                                                                                                        |
|:---------|:-------------------|:--------------------------------|---------:|:---------------------------------------------------------------------------------------------------------------------------------------------|
| woba     | S2_level_env       | levelenv                        |    12423 | per-(player, level) grain unique; every emission fit on strictly-prior debut cohorts (seed not emitted); finite + plausible ([0.262, 0.406]) |
| k_pct    | S4_park_env_rel0.5 | park:exposure+levelenv+rel:0.5k |    12423 | per-(player, level) grain unique; every emission fit on strictly-prior debut cohorts (seed not emitted); finite + plausible ([0.098, 0.477]) |
| bb_pct   | S4_park_env_rel2.0 | park:exposure+levelenv+rel:2k   |    12423 | per-(player, level) grain unique; every emission fit on strictly-prior debut cohorts (seed not emitted); finite + plausible ([0.028, 0.165]) |
| iso      | S4_park_env_rel2.0 | park:exposure+levelenv+rel:2k   |    12423 | per-(player, level) grain unique; every emission fit on strictly-prior debut cohorts (seed not emitted); finite + plausible ([0.020, 0.315]) |

## 6. Limitations

- **Park factors are computed from our own free substrate**, not from Baseball America's published table. The two will not agree exactly: BA uses different denominators and a different window. Ours is reproducible, versioned and per-player-exposure-weighted; that is the trade.
- **A trailing 3-season window on a MiLB park is still thin** — an affiliate relocation or a fence move inside the window is absorbed as noise, and the EB shrink toward neutral is what keeps that from becoming a confident wrong factor.
- **A team that changes LEVEL inside the window** has its buckets pooled across levels. Rare (affiliates are stable) but not corrected.
- **The reliability stabilisation points are LITERATURE constants**, not fitted here. The 0.5×/1×/2× grid is the sensitivity, and every grid point counts toward the deflation.
- **Survivorship is untouched** — this slice does not correct the promotion selection bias (E7.12 slice 2). Every number is conditional on the graduated population E7.3 trains on.
- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

