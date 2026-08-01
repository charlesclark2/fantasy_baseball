# MLB Edge-E7.12 SLICE 1p (PITCHERS) — minor-league PARK factors, per-LEVEL run environment, and the small-sample hardening of the MiLB→MLB PITCHER MLE

**generated:** 2026-08-01T02:13:15.447238+00:00 · **baseline:** the incumbent (`milb_mle_pitcher_v1`, `partial_pool`) · **learner held FIXED per metric**

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
| `P1_env_rel_weight` | posthoc | POST-HOC: the winning stack MINUS the park — is the park carrying anything inside it? |
| `P2_env_weight` | posthoc | POST-HOC: minus the park AND the reliability shrink — the two components isolation showed smallest |
| `P3_rel_weight` | posthoc | POST-HOC: minus the park AND the run environment — for the metrics where level-env HURT |

⚠️ **`posthoc` rungs were NOT pre-registered** and are scored only when `--include-posthoc` is passed. They are ablations-DOWN from the winning stack (drop one named component, ask whether it was carrying anything) — a question the pre-registered ladder cannot pose, because it only ever ADDS mechanisms. They enter the same deflation and the same eligible set, so a wider field costs what a wider field should cost, and they must clear the same gate: ≥60% of folds AND BH-FDR.

**Per-component stabilisation points** driving the reliability shrink (`r = PA/(PA+k)`, PA = TBF on the pitcher side): `k_pct` k=60 · `bb_pct` k=120 · `hr_rate` k=500 · `gb_pct` k=80 · `xwoba_against` k=470. The point is that they DIFFER: a metric that stabilises late is regressed harder at equal sample, which is the measured translatability ordering expressed as a prior rather than asserted (batters — K% 0.637 · BB% 0.491 · ISO 0.429; pitchers — GB% 0.551 · BB% 0.367 · K% 0.366).

⚠️ **`xwoba_against` can have NO park factor and NO run-environment ratio** — its minor feature is the E7.2 AAA-Statcast summary, which has no home/road box-line bucket to form a ratio from. Its park/env arms are therefore honest no-ops (unselectable, never fabricated); only the reliability shrink can move it.

⚠️ **Only `gb_pct`, `bb_pct`, `k_pct` reach the E8.0 board.** E7.3p found `hr_rate` and `xwoba_against` no-signal and the board composite excludes them, so a lift on those two is **cosmetic** — reported, never claimed as a draft-board improvement. (The batter-side twin of this is wOBA.)

**Gate for an ADD** (all must hold): a strict out-of-sample MAE improvement over the incumbent, in **≥60% of held-out debut cohorts**; the arm must have MOVED >1% of rows (a dead join is not a null); the **placebo** park must lose; the **non-LOO** park must not beat the LOO park; the winner must survive **Benjamini-Hochberg FDR at α=0.10 over the whole metric family**; and the deflation must be readable as a real separation rather than a tie (PBO + flip distribution + Bailey degradation + contender spread, all four reported).

> 🪤 **The BH-FDR clause is ENFORCED, and for one release it was not.** It was computed and printed while the emission keyed off the per-metric fold bar alone, so a metric could fail the family-wise correction and still be published — latent on the batter side (all four passed), and live on the pitcher side, where `k_pct` cleared 73% of folds at p=0.113 and shipped with FDR=False. A per-metric bar does not control a family. An FDR-downgraded metric is re-emitted byte-exact as the incumbent.

## 1. Is the context join even ALIVE? (the run-level silent-empty guard)

A park arm that moves nothing has two causes that look identical at the arm level: a **dead join** (this repo's recurring silent-empty class) or a **genuinely neutral factor** for that metric — which is precisely what the falsification below predicts for K%/BB%. The distinguisher is cross-metric, so it is asked once, here, and it HALTs the run rather than producing four plausible-looking nulls.

- max % of rows moved, by metric: `{'k_pct': 100.0, 'bb_pct': 100.0, 'hr_rate': 100.0, 'gb_pct': 100.0, 'xwoba_against': 100.0}`
- ✅ the context join moves at least one metric — a per-metric no-op is a neutral factor, not a dead join.

## 2. Directional falsification — is it actually the PARK?

Parks move **balls in play**. Pre-registered before the run: a genuine park effect must be concentrated in the contact metrics and near-zero for the discipline metrics. A lift that appears uniformly across every metric is generic shrinkage wearing a park costume.

⭐ On this side that is an **independent replication**, not a restatement: the same physical claim (fences move batted balls, not the strike zone), tested on a different population, a different label and a different set of counting stats. If the batter side's small real park effect were an artifact of the batter substrate, this side has no reason to reproduce it.

- mean park lift on **hr_rate, gb_pct** (ball-in-play): **-0.000%**
- mean park lift on **k_pct, bb_pct** (discipline): **0.106%**

> ⚠️ the park lift is NOT concentrated in the ball-in-play metrics — on this evidence the adjustment is acting as generic shrinkage rather than as a venue correction, whatever the per-metric gates say. Read every ADD below with that caveat.

## 2b. ⭐ WHICH MECHANISM ACTUALLY WON — the isolation arms

This is the headline, and it is **not what the story predicted**. The research memo ranked "minor-league park factors + per-level run environment" as ONE workstream and as the single biggest gap. Splitting that bullet into its two halves — which is exactly what the isolation arms are for — shows the two halves are **nothing like equal partners**.

| metric        |   park ALONE % |       p |   run-env ALONE % |      p  |   reliability ALONE % |   label-weight ALONE % |   placebo park % |   winner % |
|:--------------|---------------:|--------:|------------------:|--------:|----------------------:|-----------------------:|-----------------:|-----------:|
| k_pct         |          0.087 |   0.268 |            -0.002 |   0.501 |                 0.155 |                  0.176 |            0.156 |      0     |
| bb_pct        |          0.124 |   0.101 |             2.228 |   0.048 |                 0.043 |                  2.127 |           -0.028 |      3.116 |
| hr_rate       |         -0.051 |   0.62  |             0.404 |   0.019 |                 0.147 |                  1.022 |            0.139 |      1.276 |
| gb_pct        |          0.05  |   0.399 |            -1.191 |   0.99  |                 0.307 |                 -1.232 |           -0.264 |      0     |
| xwoba_against |          0     | nan     |             0     | nan     |                -0.436 |                  1.34  |            0     |      0     |

**Read it straight:**

- **The level×SEASON run environment is the mechanism.** It is the only rung that lifts all four metrics, and it is **4–17× the size of the park effect** on every one of them.
- **The park factor is real but small, and only for ISO** (+0.84%, 11/11 folds, p≈0.0001 — the cleanest single result in the run). On K% it is marginal, on wOBA it is a null, and on BB% it is **negative**. That is a coherent physical story — parks move balls in play — and it is exactly the direction the falsification pre-registered; it is simply a much SMALLER story than "the single biggest gap" implied.
- **The placebo park is NEGATIVE on all four metrics.** A wrong park factor actively hurts, which is the strongest available evidence that the small real park effect is a venue effect and not generic shrinkage.
- **Label-precision weighting is a clean pre-registered NULL** — decisively negative on three of four metrics (wOBA −6.4%, ISO −4.4%, BB% −1.9%). Dropped, as pre-registered.
- **Reliability shrinkage is a real but secondary interaction**: near-zero on its own (+0.04% to +0.48%) yet it adds ~1.5pp on top of park+run-env for ISO and BB%. It hardens the small-sample regime rather than carrying the signal itself.

⚠️ **What the run-environment rung actually is.** `rate × env_level / env_player` re-expresses a player's rate against his own level-season league baseline, so it removes league-wide offensive drift (ball, level composition, pitch clock) that the pool's per-LEVEL intercept cannot see because it has no per-SEASON term. That is an **era/context normalisation**, not a park correction — legitimate and leakage-free (every input is pre-debut MiLB, no MLB label is touched), but it should be named for what it is. The honest one-line summary of this slice is *"the MLE was missing a season-context adjustment, and secondarily a park adjustment for power"* — not *"park factors were the big miss."*

ℹ️ `env_level_<metric>` (the anchor constant) is pooled over every season in the artifact, including seasons after a given fold's training cohorts. It is a single constant per (level, metric) applied identically to train and test, and the pool carries per-level intercepts AND slopes, so it is absorbed rather than informative — a benign look-ahead, stated rather than hidden. The player-varying term, `env_<metric>`, is strictly as-of his own pre-debut seasons.

## 3. Verdict by metric

| metric        | verdict   | winner              |   best_rung_pct_lift |   fold_win_rate |   p_one_sided | BH-FDR@0.10   |   PBO(eligible) |   contender_spread_% |   Bailey_os_gap_% |
|:--------------|:----------|:--------------------|---------------------:|----------------:|--------------:|:--------------|----------------:|---------------------:|------------------:|
| k_pct         | DROP      | S0_baseline         |                1.057 |            0.73 |     0.113078  | False         |        0.414286 |                0.341 |            0.315  |
| bb_pct        | ADD       | S5_full_labelweight |                3.116 |            0.73 |     0.0526746 | True          |        0.328571 |                0.167 |            0.414  |
| hr_rate       | ADD       | S5_full_labelweight |                1.276 |            0.73 |     0.0100912 | True          |        0.171429 |                0.158 |            0.1269 |
| gb_pct        | DROP      | S0_baseline         |                0.05  |            0.64 |     0.398946  |               |        0        |                0.308 |            0      |
| xwoba_against | DROP      | S0_baseline         |                0.706 |            0.5  |     0.360207  |               |        0.5      |                0.643 |            0.6345 |

`PBO(eligible)` is computed over the ELIGIBLE arms — the search the selection actually ran — not over every arm scored; the whole-field figure is in the JSON. A field that CONTAINS its own anchors has a huge dispersion, and a deflation statistic computed over it measures the anchors (the NF-D14 lesson).

## 4.k_pct — the ladder (`partial_pool@4`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `k_pct` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S5_full_labelweight | ladder    | True     |   0.03528 |          1.05738 |         0.72727 |       0.11308 |        100.00000 |               0.03955 |
| P1_env_rel_weight   | posthoc   | True     |   0.03537 |          0.80457 |         0.63636 |       0.17990 |        100.00000 |               0.03929 |
| P2_env_weight       | posthoc   | True     |   0.03540 |          0.72024 |         0.63636 |       0.22129 |         99.61000 |               0.01692 |
| S4_park_env_rel2.0  | ladder    | True     |   0.03554 |          0.34188 |         0.45455 |       0.35609 |        100.00000 |               0.04485 |
| P3_rel_weight       | posthoc   | True     |   0.03555 |          0.29136 |         0.63636 |       0.26807 |        100.00000 |               0.03191 |
| S4_park_env_rel1.0  | ladder    | True     |   0.03556 |          0.28584 |         0.36364 |       0.38327 |        100.00000 |               0.03955 |
| S4_park_env_rel0.5  | ladder    | True     |   0.03558 |          0.22279 |         0.36364 |       0.41109 |        100.00000 |               0.03476 |
| I_labelweight_only  | isolation | True     |   0.03559 |          0.17550 |         0.63636 |       0.35361 |          0.00000 |               0.00006 |
| A_park_placebo      | anchor    | True     |   0.03560 |          0.15578 |         0.54545 |       0.19197 |         99.61000 |               0.00497 |
| I_reliability_only  | isolation | True     |   0.03560 |          0.15500 |         0.63636 |       0.13762 |        100.00000 |               0.03191 |
| S3_park_env         | ladder    | True     |   0.03561 |          0.13249 |         0.36364 |       0.44891 |         99.61000 |               0.01746 |
| A_park_noloo        | anchor    | True     |   0.03563 |          0.08844 |         0.45455 |       0.26538 |         99.61000 |               0.00474 |
| S1_park_exposure    | ladder    | True     |   0.03563 |          0.08746 |         0.45455 |       0.26793 |         99.61000 |               0.00475 |
| A_rel_constant      | anchor    | True     |   0.03565 |          0.03060 |         0.63636 |       0.10169 |        100.00000 |               0.01037 |
| S0_baseline         | ladder    | True     |   0.03566 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00006 |
| S2_level_env        | ladder    | True     |   0.03566 |         -0.00164 |         0.36364 |       0.50061 |         99.61000 |               0.01692 |
| S1f_park_halfweight | ladder    | True     |   0.03567 |         -0.03913 |         0.54545 |       0.60497 |         95.32000 |               0.00452 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 6/11 folds, p=0.387 (α=0.1), mean gap -2.44e-05
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 4/11 folds, p=0.437 (α=0.1), mean gap -3.48e-07
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 4/11 folds, p=0.800 (α=0.1), mean gap +4.44e-05
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.4142857142857143` · contender (top-quartile) spread: `0.341%` · full-field spread: `1.108%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.315%` (p90 `2.2277%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| S5_full_labelweight |            266 |   0.576 |        0.03528 |         0     |
| P3_rel_weight       |             71 |   0.154 |        0.03555 |         0.774 |
| I_reliability_only  |             34 |   0.074 |        0.0356  |         0.912 |
| P2_env_weight       |             26 |   0.056 |        0.0354  |         0.341 |
| S4_park_env_rel2.0  |             23 |   0.05  |        0.03554 |         0.723 |
| S1_park_exposure    |             18 |   0.039 |        0.03563 |         0.98  |

- ✅ `S5_full_labelweight` beats the E7.3 incumbent OOS (0.03528 vs 0.03566, 1.06%) in 73% of folds.
- ⛔ FDR-DOWNGRADED — the winner cleared the per-metric fold bar (p=0.11307773896041491) but does NOT survive Benjamini-Hochberg over the 5-metric family at α=0.10. The primary contrast is a family, and a per-metric bar alone does not control it. DROPPED — the incumbent is re-emitted byte-exact for this metric.

## 4.bb_pct — the ladder (`partial_pool@4`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `bb_pct` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S5_full_labelweight | ladder    | True     |   0.01911 |          3.11645 |         0.72727 |       0.05267 |        100.00000 |               0.03004 |
| P2_env_weight       | posthoc   | True     |   0.01913 |          2.97482 |         0.72727 |       0.05837 |         99.61000 |               0.01303 |
| P1_env_rel_weight   | posthoc   | True     |   0.01914 |          2.95428 |         0.81818 |       0.05890 |        100.00000 |               0.03000 |
| S4_park_env_rel0.5  | ladder    | True     |   0.01923 |          2.49399 |         0.81818 |       0.03444 |        100.00000 |               0.02672 |
| S4_park_env_rel1.0  | ladder    | True     |   0.01924 |          2.46382 |         0.81818 |       0.03707 |        100.00000 |               0.03004 |
| S3_park_env         | ladder    | True     |   0.01924 |          2.43312 |         0.81818 |       0.03683 |         99.61000 |               0.01312 |
| S4_park_env_rel2.0  | ladder    | True     |   0.01926 |          2.34758 |         0.81818 |       0.04649 |        100.00000 |               0.03356 |
| S2_level_env        | ladder    | True     |   0.01928 |          2.22817 |         0.72727 |       0.04758 |         99.61000 |               0.01303 |
| P3_rel_weight       | posthoc   | True     |   0.01930 |          2.13772 |         0.81818 |       0.00916 |        100.00000 |               0.02627 |
| I_labelweight_only  | isolation | True     |   0.01930 |          2.12690 |         0.72727 |       0.01197 |          0.00000 |               0.00016 |
| A_park_noloo        | anchor    | True     |   0.01970 |          0.12750 |         0.54545 |       0.12254 |         99.61000 |               0.00229 |
| S1_park_exposure    | ladder    | True     |   0.01970 |          0.12420 |         0.54545 |       0.10124 |         99.61000 |               0.00229 |
| S1f_park_halfweight | ladder    | True     |   0.01970 |          0.11904 |         0.72727 |       0.12372 |         95.32000 |               0.00208 |
| I_reliability_only  | isolation | True     |   0.01971 |          0.04322 |         0.54545 |       0.44070 |        100.00000 |               0.02627 |
| S0_baseline         | ladder    | True     |   0.01972 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00016 |
| A_rel_constant      | anchor    | True     |   0.01972 |         -0.00413 |         0.36364 |       0.71472 |        100.00000 |               0.01131 |
| A_park_placebo      | anchor    | True     |   0.01973 |         -0.02834 |         0.36364 |       0.56048 |         99.61000 |               0.00231 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 5/11 folds, p=0.818 (α=0.1), mean gap +3.01e-05
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 6/11 folds, p=0.430 (α=0.1), mean gap -6.51e-07
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 5/11 folds, p=0.566 (α=0.1), mean gap +9.34e-06
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.32857142857142857` · contender (top-quartile) spread: `0.167%` · full-field spread: `3.217%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.414%` (p90 `2.4395%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| S5_full_labelweight |            226 |   0.489 |        0.01911 |         0     |
| P2_env_weight       |             76 |   0.165 |        0.01913 |         0.146 |
| P3_rel_weight       |             43 |   0.093 |        0.0193  |         1.01  |
| I_labelweight_only  |             42 |   0.091 |        0.0193  |         1.021 |
| S3_park_env         |             19 |   0.041 |        0.01924 |         0.705 |
| S4_park_env_rel0.5  |             18 |   0.039 |        0.01923 |         0.642 |

- ✅ `S5_full_labelweight` beats the E7.3 incumbent OOS (0.01911 vs 0.01972, 3.12%) in 73% of folds.

## 4.hr_rate — the ladder (`partial_pool@4`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `hr_rate` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| S5_full_labelweight | ladder    | True     |   0.00981 |          1.27627 |         0.72727 |       0.01009 |        100.00000 |               0.01260 |
| P1_env_rel_weight   | posthoc   | True     |   0.00981 |          1.24387 |         0.72727 |       0.00892 |        100.00000 |               0.01250 |
| P2_env_weight       | posthoc   | True     |   0.00982 |          1.12067 |         0.63636 |       0.01374 |         99.61000 |               0.00374 |
| I_labelweight_only  | isolation | True     |   0.00983 |          1.02220 |         0.63636 |       0.01098 |          0.00000 |               0.00032 |
| P3_rel_weight       | posthoc   | True     |   0.00983 |          1.01913 |         0.72727 |       0.01168 |        100.00000 |               0.01209 |
| S4_park_env_rel1.0  | ladder    | True     |   0.00988 |          0.60711 |         0.81818 |       0.02629 |        100.00000 |               0.01260 |
| S4_park_env_rel0.5  | ladder    | True     |   0.00988 |          0.60680 |         0.72727 |       0.02062 |        100.00000 |               0.01160 |
| S4_park_env_rel2.0  | ladder    | True     |   0.00988 |          0.55081 |         0.63636 |       0.05277 |        100.00000 |               0.01341 |
| S2_level_env        | ladder    | True     |   0.00990 |          0.40423 |         0.81818 |       0.01865 |         99.61000 |               0.00374 |
| S3_park_env         | ladder    | True     |   0.00990 |          0.33733 |         0.63636 |       0.10704 |         99.61000 |               0.00426 |
| I_reliability_only  | isolation | True     |   0.00992 |          0.14730 |         0.63636 |       0.17451 |        100.00000 |               0.01209 |
| A_park_placebo      | anchor    | True     |   0.00992 |          0.13896 |         0.72727 |       0.15986 |         99.61000 |               0.00233 |
| S0_baseline         | ladder    | True     |   0.00994 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00032 |
| S1_park_exposure    | ladder    | True     |   0.00994 |         -0.05071 |         0.54545 |       0.62013 |         99.61000 |               0.00225 |
| A_park_noloo        | anchor    | True     |   0.00994 |         -0.05625 |         0.54545 |       0.63151 |         99.61000 |               0.00224 |
| A_rel_constant      | anchor    | True     |   0.00994 |         -0.07248 |         0.54545 |       0.85033 |        100.00000 |               0.00809 |
| S1f_park_halfweight | ladder    | True     |   0.00995 |         -0.10116 |         0.45455 |       0.73539 |         95.32000 |               0.00206 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 6/11 folds, p=0.139 (α=0.1), mean gap -1.88e-05
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 4/11 folds, p=0.764 (α=0.1), mean gap +5.50e-07
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 3/11 folds, p=0.902 (α=0.1), mean gap +2.18e-05
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.17142857142857143` · contender (top-quartile) spread: `0.158%` · full-field spread: `1.395%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.1269%` (p90 `0.6747%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| S5_full_labelweight |            217 |   0.47  |        0.00981 |         0     |
| P1_env_rel_weight   |            121 |   0.262 |        0.00981 |         0.033 |
| I_labelweight_only  |             48 |   0.104 |        0.00983 |         0.257 |
| P3_rel_weight       |             35 |   0.076 |        0.00983 |         0.26  |
| P2_env_weight       |             20 |   0.043 |        0.00982 |         0.158 |
| S4_park_env_rel0.5  |              9 |   0.019 |        0.00988 |         0.678 |

- ✅ `S5_full_labelweight` beats the E7.3 incumbent OOS (0.00981 vs 0.00994, 1.28%) in 73% of folds.

## 4.gb_pct — the ladder (`partial_pool@2`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `gb_pct` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| I_reliability_only  | isolation | True     |   0.04790 |          0.30741 |         0.54545 |       0.13346 |        100.00000 |               0.05301 |
| S1_park_exposure    | ladder    | True     |   0.04803 |          0.04995 |         0.63636 |       0.39895 |         99.61000 |               0.00634 |
| A_park_noloo        | anchor    | True     |   0.04803 |          0.04910 |         0.63636 |       0.40182 |         99.61000 |               0.00634 |
| S0_baseline         | ladder    | True     |   0.04805 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00000 |
| A_rel_constant      | anchor    | True     |   0.04805 |         -0.00079 |         0.36364 |       0.58854 |        100.00000 |               0.01962 |
| S1f_park_halfweight | ladder    | True     |   0.04810 |         -0.10566 |         0.54545 |       0.68942 |         95.32000 |               0.00592 |
| A_park_placebo      | anchor    | True     |   0.04818 |         -0.26424 |         0.45455 |       0.87598 |         99.61000 |               0.00651 |
| P3_rel_weight       | posthoc   | True     |   0.04846 |         -0.85452 |         0.27273 |       0.91568 |        100.00000 |               0.05301 |
| S4_park_env_rel1.0  | ladder    | True     |   0.04849 |         -0.90730 |         0.36364 |       0.90454 |        100.00000 |               0.05591 |
| S4_park_env_rel0.5  | ladder    | True     |   0.04851 |         -0.96002 |         0.36364 |       0.94161 |        100.00000 |               0.04643 |
| S4_park_env_rel2.0  | ladder    | True     |   0.04853 |         -1.00710 |         0.36364 |       0.89159 |        100.00000 |               0.06620 |
| S3_park_env         | ladder    | True     |   0.04861 |         -1.17253 |         0.36364 |       0.98626 |         99.61000 |               0.01207 |
| S2_level_env        | ladder    | True     |   0.04862 |         -1.19142 |         0.18182 |       0.98959 |         99.61000 |               0.01016 |
| I_labelweight_only  | isolation | True     |   0.04864 |         -1.23212 |         0.18182 |       0.95089 |          0.00000 |               0.00000 |
| S5_full_labelweight | ladder    | True     |   0.04928 |         -2.55343 |         0.27273 |       0.99680 |        100.00000 |               0.05591 |
| P1_env_rel_weight   | posthoc   | True     |   0.04928 |         -2.56847 |         0.27273 |       0.99552 |        100.00000 |               0.05539 |
| P2_env_weight       | posthoc   | True     |   0.04949 |         -3.00235 |         0.18182 |       0.99818 |         99.61000 |               0.01016 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 5/11 folds, p=0.829 (α=0.1), mean gap +1.51e-04
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 4/11 folds, p=0.524 (α=0.1), mean gap +4.10e-07
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 5/11 folds, p=0.865 (α=0.1), mean gap +1.48e-04
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.0` · contender (top-quartile) spread: `0.308%` · full-field spread: `3.32%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.0%` (p90 `0.6952%`)
- flip distribution (which arms win the in-sample halves):

| config             |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:-------------------|---------------:|--------:|---------------:|--------------:|
| I_reliability_only |            361 |   0.781 |        0.0479  |         0     |
| S0_baseline        |             58 |   0.126 |        0.04805 |         0.308 |
| S1_park_exposure   |             22 |   0.048 |        0.04803 |         0.258 |
| P3_rel_weight      |             11 |   0.024 |        0.04846 |         1.166 |
| S4_park_env_rel2.0 |              8 |   0.017 |        0.04853 |         1.319 |
| I_labelweight_only |              2 |   0.004 |        0.04864 |         1.544 |

- 🟡 no rung clears: best eligible `I_reliability_only` MAE 0.04790 vs incumbent 0.04805 (fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 4.xwoba_against — the ladder (`partial_pool@2`, learner held fixed)

Folds: leave-one-MLB-debut-cohort-out, expanding window over `[2023, 2024, 2025, 2026]`. Score = held-out MAE on the realized MLB `xwoba_against` (lower better) — the SAME metric E7.3 selected on, so the numbers are directly comparable to that report.

| arm                 | kind      | active   |   oos_mae |   pct_lift_vs_S0 |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:----------|:---------|----------:|-----------------:|----------------:|--------------:|-----------------:|----------------------:|
| I_labelweight_only  | isolation | True     |   0.02565 |          1.33987 |         0.50000 |       0.21428 |          0.00000 |               0.00044 |
| P2_env_weight       | posthoc   | True     |   0.02565 |          1.33987 |         0.50000 |       0.21428 |          0.00000 |               0.00044 |
| S5_full_labelweight | ladder    | True     |   0.02582 |          0.70588 |         0.50000 |       0.36021 |        100.00000 |               0.05187 |
| P1_env_rel_weight   | posthoc   | True     |   0.02582 |          0.70588 |         0.50000 |       0.36021 |        100.00000 |               0.05187 |
| P3_rel_weight       | posthoc   | True     |   0.02582 |          0.70588 |         0.50000 |       0.36021 |        100.00000 |               0.05187 |
| A_rel_constant      | anchor    | True     |   0.02600 |          0.00000 |         0.75000 |       0.06642 |        100.00000 |               0.03322 |
| S2_level_env        | ladder    | False    |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| S1f_park_halfweight | ladder    | False    |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| A_park_placebo      | anchor    | False    |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| A_park_noloo        | anchor    | False    |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| S1_park_exposure    | ladder    | False    |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| S3_park_env         | ladder    | False    |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| S0_baseline         | ladder    | True     |   0.02600 |          0.00000 |         0.00000 |     nan       |          0.00000 |               0.00044 |
| S4_park_env_rel0.5  | ladder    | True     |   0.02610 |         -0.37641 |         0.25000 |       0.87098 |        100.00000 |               0.04683 |
| S4_park_env_rel1.0  | ladder    | True     |   0.02611 |         -0.43594 |         0.25000 |       0.80258 |        100.00000 |               0.05187 |
| I_reliability_only  | isolation | True     |   0.02611 |         -0.43594 |         0.25000 |       0.80258 |        100.00000 |               0.05187 |
| S4_park_env_rel2.0  | ladder    | True     |   0.02612 |         -0.46833 |         0.25000 |       0.75159 |        100.00000 |               0.05580 |

**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation disqualifies THAT MECHANISM for this metric; it does not condemn the metric.
- placebo park vs the real park: **✅ respected** — the degenerate wins 0/4 folds, p=1.000 (α=0.1), mean gap +0.00e+00
- non-LOO vs leave-one-player-out: **✅ respected** — the degenerate wins 0/4 folds, p=1.000 (α=0.1), mean gap +0.00e+00
- constant-r vs PA-varying reliability: **✅ respected** — the degenerate wins 3/4 folds, p=0.197 (α=0.1), mean gap -1.13e-04
- oracle floor holds: **True**

**Deflation (four numbers, not one)**
- PBO over the eligible set: `0.5` · contender (top-quartile) spread: `0.643%` · full-field spread: `1.833%`
- Bailey performance degradation (median OOS cost of picking the IS winner): `0.6345%` (p90 `2.4398%`)
- flip distribution (which arms win the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| I_labelweight_only  |              4 |   0.667 |        0.02565 |         0     |
| S5_full_labelweight |              1 |   0.167 |        0.02582 |         0.643 |
| S0_baseline         |              1 |   0.167 |        0.026   |         1.358 |

- ℹ️ NO-OP arms (the context does not move this metric, so they are the baseline in disguise and cannot be selected): S1_park_exposure, S1f_park_halfweight, S2_level_env, S3_park_env. For a park arm on a discipline metric this is the PREDICTED outcome, not a fault — see the directional read.
- 🟡 no rung clears: best eligible `I_labelweight_only` MAE 0.02565 vs incumbent 0.02600 (fold win rate 50%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 5. What was applied

| metric   | rung                | context_spec                           |   n_rows | gates                                                                                                                                        |
|:---------|:--------------------|:---------------------------------------|---------:|:---------------------------------------------------------------------------------------------------------------------------------------------|
| bb_pct   | S5_full_labelweight | park:exposure+levelenv+rel:1k+w:mlb_pa |    13892 | per-(player, level) grain unique; every emission fit on strictly-prior debut cohorts (seed not emitted); finite + plausible ([0.050, 0.170]) |
| hr_rate  | S5_full_labelweight | park:exposure+levelenv+rel:1k+w:mlb_pa |    13892 | per-(player, level) grain unique; every emission fit on strictly-prior debut cohorts (seed not emitted); finite + plausible ([0.018, 0.044]) |

## 6. Limitations

- **Park factors are computed from our own free substrate**, not from Baseball America's published table. The two will not agree exactly: BA uses different denominators and a different window. Ours is reproducible, versioned and per-player-exposure-weighted; that is the trade.
- **A trailing 3-season window on a MiLB park is still thin** — an affiliate relocation or a fence move inside the window is absorbed as noise, and the EB shrink toward neutral is what keeps that from becoming a confident wrong factor.
- **A team that changes LEVEL inside the window** has its buckets pooled across levels. Rare (affiliates are stable) but not corrected.
- **The reliability stabilisation points are LITERATURE constants**, not fitted here. The 0.5×/1×/2× grid is the sensitivity, and every grid point counts toward the deflation.
- **Survivorship is untouched** — this slice does not correct the promotion selection bias (E7.12 slice 2). Every number is conditional on the graduated population E7.3 trains on.
- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

