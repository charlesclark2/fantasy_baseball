# NF-W1 — pre-registration: the lean weekly per-game distributional projection (§0.5 bake-off)

**Committed BEFORE the full run** (the NF-D20 discipline). Every constant here is code in
`weekly_projection.py`; the runner (`run_nf_w1_weekly_bakeoff.py`) reads it and restates nothing.

## ⛔ The one thing this story may not do

Serve a weekly model that has not beaten the honest degenerate weekly baseline — **season ÷ games,
spread by a matchup adjustment** — on purged held-out WEEKS under deflation. A foil win, a gate
miss, or an anchor violation is a **recorded NULL** (classified via `cv_power.classify_null`),
never a ship. `best_alpha = 0` — a projection product, no betting/edge claim.

## The frame (binding NF-W0 constraints)

- Certified roster-first frame, rebuilt in memory: 2016–2025 REG, zeros RETAINED
  (bye / inactive / dressed-no-stat kept distinct). ⛔ never `stats_player_week`-first.
- Label pinned on every result: `v1.nflverse.stats_player_week` / `ppr`.
- **Scoring population:** positions QB/RB/WR/TE, `label ≠ bye`. A bye is a deterministic
  schedule-known zero — served as the identity 0; scoring every arm on identical free zeros
  discriminates nothing (the with-bye sensitivity is analytic: it rescales every identity-emitting
  arm's mean CRPS by the same factor and cannot reorder arms). Inactive + dressed-no-stat zeros
  are RETAINED — game-day status is a banned feature, so availability risk is what the model must
  price. FB is excluded (no board presence).
- **PIT boundary:** `assemble_matrix` invokes NF-W0a's `assert_point_in_time` per target week
  (first real caller of the guard). Stamps = the window-end as-of instant; a week whose window
  cannot be proven clean (the 2020 rescheduling shape) is dropped fail-closed and counted.
- **Snap features are NULL-bearing** (NF-W0b): NULL = unmeasured, never zero snaps; the
  `snap_share__observed_l4` flag carries presence; ⛔ no `fillna(0)`. Model-internal train-fold
  median imputation (with the flag retained) is declared for learners that cannot pass NaN.
- **Era constraint honored by exclusion:** no `pbp_participation` pressure/coverage/route legs at
  all in this slice (`ERA_FORBIDDEN_TOKENS` guard). NGS / pfr_advanced / injury_report /
  participation_proxies are allowed-but-deferred (recorded in `UNUSED_ALLOWED_FAMILIES`).
- No markets, weather, depth-chart rank, or game-day inactive status as features (NF-W0 (5)).

## Metric

- **Selection: CRPS** (`crps_q39`) — the 2×mean-pinball identity over 39 levels (0.025…0.975),
  identical representation for every arm (monotone rearrangement applied uniformly).
- ⛔ MAE is INVERTED at QB/TE on this frame (conditional median exactly 0.0 — NF-W0 §2.3; the
  NF-D11/NF-D14 class). MAE is reported, never selects, never gates.
- Coverage of the central 80% interval is a **FLOOR** (0.80), never a target: reported with
  binomial SE; blocks only when the shortfall exceeds 3 SE (NF1.8 rows-not-decimals).

## Folds

8 expanding-window half-season test blocks **over weeks**: 2022H1, 2022H2, 2023H1, 2023H2,
2024H1, 2024H2, 2025H1, 2025H2 (H1 = weeks 1–9). Train = every modeled row ≥ 2 global weeks
(PURGE_WEEKS) before the block start; strictly earlier always. 2016–2021 is burn-in history.

## The field

**Real arms (the declared 4-learner-class family — the DSR trial field):**

| arm | class |
|---|---|
| `lgbm_quantile` | GBM nonparametric quantile bank (pooled, position categorical; 9 knots → 39 levels) |
| `lgbm_hurdle` | two-part mixture: P(zero) classifier × conditional-on-nonzero quantile bank |
| `enet_residual` | linear: ElasticNet mean + per-position empirical residual quantiles |
| `knn_quantile` | neighborhood: per-position standardized kNN (k=300) empirical quantiles |

**Foils (the honest null family — eligible for PBO, non-shippable):**

| foil | form |
|---|---|
| `foil_flat` | EB-shrunk unconditional PPG: (prior-season pts + season-to-date pts + κ·pos-mean) / (prior games + s2d games + κ), κ=4; distribution = per-position train residual quantiles |
| `foil_matchup` | `foil_flat` × opponent DVP index (PPR allowed to position, lagged L8, ÷ league mean, clipped [0.75, 1.25]) — **the story foil** |

Denominators are rostered team games ex-bye (unconditional — availability embedded), matching the
served NF1 weekly leg's semantics (`proj_fp_ppr / 17`).

**Anchors (diagnostic — excluded from the PBO matrix and the DSR trial field, MH2.1 (a)):**

| anchor | role | registered expectation |
|---|---|---|
| `nihilist_zero` | all-zero degenerate ceiling | MUST lose to any shipped arm (measured, never reasoned — NF-D14) |
| `pos_marginal` | train climatology per position | MUST lose (conditioning must earn its keep) |
| `permuted_within` | same estimator, labels shuffled within position×week | MUST lose (features carry player signal) |
| `zero_width` | point mass at the foil's point | MUST lose (sharpness degenerate #1) |
| `max_width` | foil residual bank ×3 | MUST lose CRPS while satisfying the coverage floor (NF1.8 — proves the floor is a constraint, not a criterion) |
| `oracle_marginal` | PEEKING per-position marginal fit on the test block | reported ceiling of marginal information; a conditional arm may legitimately beat it (capacity — NF1.9 (f)); never a veto |

## Gates (per position; ship unit = per-position champion)

SHIP requires ALL of: beats the best foil on mean fold CRPS · calibrated fold-consistency
(`cv_power.fold_consistency_clause(8)` — 6 of 8 wins) · PBO < 0.20 over the eligible field
(4 arms + 2 foils; `NF18.deflate`, flips + contender spread + os-gap reported) · DSR ≥ 0.95 over
the declared 4-arm family (`M14.deflated_sharpe`) · BH-FDR q=0.10 across the 4 position tests ·
all MUST-lose anchors lose · coverage floor not in blocking shortfall. Anything else ⇒ the
position's verdict is a `classify_null` state, recorded.

## Outputs

- Raw components beside the gated points distribution: per-component LGBM means
  (`fit_component_head`, 11 components) — advisory raw lines any league's scoring can re-score
  (MVP-1 philosophy); never themselves gated in this slice.
- Weekly-updating ROS = Σ remaining weekly projections (`ros_projection`; declared independence
  approximation for the interval).
- Artifacts: `ablation_results/nf_w1_weekly_bakeoff.{md,json}`; `--smoke` writes `*_smoke` files
  that can never be mistaken for the real search.
