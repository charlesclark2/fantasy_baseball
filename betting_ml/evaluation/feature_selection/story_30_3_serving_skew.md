# Story 30.3 — Production Serving-Skew Verification

**Status:** ROOT CAUSE IDENTIFIED — serving gap confirmed (not a contract/architecture bug).
**Date:** 2026-06-11. **Owner:** Charles Clark.
**Binding directive (Epic 30 header):** judge on prediction accuracy to the true outcome first; market-edge is secondary. This story is a *serving* audit — accuracy can't recover until the live matrix matches what the model was trained on.

---

## TL;DR

30.1 left a paradox: the **same** home_win contract + model scores **corr 0.42 / Brier 0.206 OFFLINE**
but **~0.001 / 0.252 LIVE**. 30.1 proved the model has skill, so the live zero-skill is a **serving**
problem. 30.3 localizes it.

**Root cause — point-in-time serving-completeness skew (not a column-order / contract bug):**
the live serve feeds the production models a matrix in which **~30% of features are NULL → imputed to
a single training-median constant for every game**, because the feature store rows for *not-yet-played*
games are sparse pre-game. The offline 0.42 benchmark reads the **same game_pks after they are played**,
when the feature store has been backfilled to dense — so it imputes ≈0 features. Same model, same games,
opposite null profile. On a model whose signal is extremely diffuse (top-10 features = 9% of |SHAP|),
flattening 30% of the matrix to constants collapses the thin edge to noise.

The structural guards 30.1 added (CONTRACT-GUARD count parity, FEATURE-ALIGN absent-column refusal) are
**passing** — the matrix is the right shape with the right columns in the right order. The failure is
**value-level**: right columns, null/constant values, at prediction time.

---

## 1. Live skill is genuinely ~zero (confirmed)

`daily_model_predictions.p_home_win_classifier` vs the actual winner (`mart_game_results`), settled 2026
games. Live corr is ≈0 / negative across every serving path (small samples; the headline matches the
audit's 0.001):

| data_source | n (settled) | corr | Brier | acc | avg disc-coverage |
|---|---|---|---|---|---|
| (unstamped, pre-06-09) | 94 | −0.055 | 0.267 | 0.40 | n/a |
| feature_store | 15 | −0.105 | 0.299 | 0.53 | 0.993 |
| intraday_assembly | 15 | +0.184 | 0.246 | 0.53 | n/a |

The contract's **offline** number on the 2026 has_full_data surface is **corr 0.42 / Brier 0.206** (30.1).
The gap is the whole story.

---

## 2. The serving gap, quantified — ~30% of the live matrix is imputed-to-constant

`daily_model_predictions` imputation footprint, recent stamped slates (376-feature contracts):

| date | prediction_type | data_source | n | imputed features / game | imputed *discriminative* / game | feat-coverage |
|---|---|---|---|---|---|---|
| 2026-06-10 | **morning** | feature_store | 45 | **37.5** | **9.2** | 0.87 |
| 2026-06-10 | post_lineup | feature_store | 15 | 22.5 | **0.2** | 0.98 |
| 2026-06-11 | **morning** | intraday_assembly | 16 | **137.5** | 1.0 | 0.65 |
| 2026-06-11 | **morning** | feature_store | 8 | **111.5** | 0.0 | 0.81 |
| 2026-06-11 | post_lineup | feature_store | 8 | 21.6 | 0.0 | 0.98 |

- The **morning** run (the SLA-binding prediction, made ≥30 min before first pitch) imputes **110–140 of
  376 features (~30%)** to constants. By **post_lineup** (after lineups/starters drop) the same slate is
  near-complete (imputed ≈ 0, coverage 0.98). The model is materially degraded *at the time the bet is made*.
- `intraday_assembly` (the fallback when the feature store is too sparse to clear the coverage gate) imputes
  the most (137/game) — it carries forward each team's last-game row + overlays lineups, leaving whole
  derived families null.

## 3. Why offline ≠ live — the feature store is not point-in-time-snapshotted

`feature_pregame_game_features` null rate by game_date (read **now**), strong-tier columns:

| game_date | status | eb_woba_seq | eb_woba | xwoba_vs_cluster | archetype_xwoba | stuff+ | elo |
|---|---|---|---|---|---|---|---|
| 2026-06-07…06-11 | **settled (backfilled)** | 0.00 | 0.00 | 0.21–0.33 | 0.21–0.33 | 0.00–0.13 | 0.00 |
| 2026-06-12, 06-13 | **scheduled (pre-game)** | **1.00** | **1.00** | **1.00** | **1.00** | 0.47–0.60 | 0.00 |

The **same table** returns 100% null on the strong-tier blocks for not-yet-played games and ~0% null once
they're played and backfilled. The live serve reads the top row of this table; the offline 0.42 reads the
bottom row of these same game_pks after the fact. This is exactly the AS-OF gap the architecture proposal
flags (§"Point-in-Time Feature Engineering": *"never consume features whose timestamps occur after
prediction time, lineup lock, or game start"*). Practical consequence: **the offline 0.42 is optimistic**
— it is not a point-in-time-honest number. The achievable live skill is bounded by what is genuinely known
pre-game, which the **post_lineup** run (disc-coverage 0.99) approximates far better than the morning run.

## 4. Per-feature parity (training surface vs live-served surface)

`feature_pregame_game_features`, 2026, by `has_full_data` (the live serve applies **no** `has_full_data` /
`min_games_played` filter — `_TODAY_QUERY` in `data_loader.py` — so it scores games the training surface
`_QUERY` excludes):

| feature (strong-tier) | null @ has_full_data=TRUE (n=968) | null @ has_full_data=FALSE (n=86) |
|---|---|---|
| home_starter_stuff_plus | 0.00 | 0.21 |
| away_starter_stuff_plus | 0.00 | 0.14 |
| home_lineup_avg_xwoba_vs_cluster | 0.13 | **0.58** |
| home_avg_eb_woba | 0.01 | 0.35 |
| home_avg_xwoba_vs_lhp | 0.00 | 0.35 |
| home_batter_cluster_mode | 0.00 | 0.35 |
| home_lineup_archetype_avg_xwoba | 0.13 | **0.58** |
| home_elo / elo_diff | 0.00 | 0.00 |

`has_full_data=FALSE` is ~8% of 2026 games but carries 2–4× the strong-tier null rate; the live serve
scores them anyway → another constant-imputed slice. (ELO is robust on both surfaces — not the culprit.)

---

## Acceptance criteria

- [x] **Served-vs-trained parity report** — per-feature live null/impute rate (§2–§4), count/order check
  (§5 below), and the informative-but-unserved list (the strong-tier blocks in §3/§4: EB-sequential,
  lineup-vs-cluster, lineup-archetype, plus the `has_full_data=FALSE` slice). Reusable harness:
  `betting_ml/scripts/serving_parity_report.py` (run for **today** to capture the live-sparse profile).
- [x] **Count + ORDER parity (§5).** Count parity is enforced at load by the 30.1 CONTRACT-GUARD
  (`len(contract)==model.n_features`, 376/376/369). Order parity is structurally guaranteed: predict_today
  slices with `reindex(columns=feature_cols)`, which emits the contract order whenever every column is
  present, and FEATURE-ALIGN refuses to score if any is absent. The served matrix tracks the post-30.1
  376-dim contract (verified against the registry `feature_columns_path`, not a stale 379/374). **No
  structural/order gap exists** — the failure is value-level.
- [x] **Serving gap found + re-attributed.** The gap is real and is **point-in-time completeness**, not
  architecture (30.1 already showed the contract scores 0.42 offline). See recommended fix below; live-skill
  re-measurement is gated on accumulating settled slates under the dense **post_lineup feature_store** path
  (disc-coverage 0.99) — the morning/intraday paths cannot be the skill benchmark.

### §5 — count/order parity result
All three targets: served matrix = contract length (376 / 376 / 369), every contract column structurally
present, order preserved by `reindex`. Guards pass. **The matrix is correctly shaped; its values are
degraded at serve time.**

---

## Fix SHIPPED — per-game serving-health edge guard (`predict_today.py`)

The parity harness run for 2026-06-11 (post-lineup, `data_source=feature_store`, coverage 0.98) confirmed the
**dense** serve is clean: **376/376 served, strong-tier degraded 0, only 5 all-null→constant (1%)** for all
three targets. The 5 persistent nulls decompose as: 2 ump z-scores (point-in-time / upstream 2026 ump-data gap —
~1% null ≤2025 but 35% null in settled 2026; deferred as a separate upstream ticket) and 3 market cols
(`over_american`/`under_american`/`under_implied_prob`, already ~48% null in training, removed by 30.4). So the
**post-lineup matrix needs no structural fix** — the live degradation is the *morning pre-lineup* state, which is
mostly **expected** lineup-/pitcher-gated absence (a TIMING question owned by Epic A1), not a serving defect.

The genuinely-fixable production gap: `is_degraded` was **computed and stored but never gated anything** — a
genuinely-collapsed matrix (the 2026-05-29 / 06-10 carry-forward incidents) or an out-of-training game still
surfaced a full actionable edge + Kelly. Shipped a per-game **SERVING-GUARD** (`_serving_degraded()` +
wiring in `_write_predictions_to_snowflake`): the actionable `h2h_edge`/`h2h_kelly`/`totals_edge`/`totals_kelly`
are **abstained (set NULL)** when the served matrix is value-degraded —
  1. `is_degraded` (unconditional-core collapse: ELO / bullpen-EB / team-sequential / RISP / park), or
  2. `has_full_data=FALSE` (the game is outside the training admission criteria; `_TODAY_QUERY` has no filter).
Model probabilities, raw diagnostic edges (`layer4_h2h_edge`), and CLV monitoring are **preserved**; only the
actionable bet is suppressed — the same stance as the global `best_alpha==0` EDGE-GUARD, applied per game. By
design it does **not** fire on a normal morning pre-lineup pick. A `[SERVING-GUARD]` warning logs the abstained
count. Covered by 6 unit tests in `betting_ml/tests/test_predict_today_write.py` (`TestServingDegradedGate`).

## Recommended fix (priority order)

1. **Bind the actionable prediction to the dense path, not the morning sparse one. ✅ SHIPPED (2026-06-11).**
   `predict_today.py` now gates the actionable h2h/totals edge + Kelly on per-game lineup confirmation
   (`_lineups_confirmed`): a PRE-LINEUP game (lineups not both confirmed) **defers its edge to the dense
   post_lineup re-score** instead of surfacing one off the ~30%-imputed morning matrix; degraded games still
   abstain; confirmed games bet normally. Fails OPEN if the lineup flags aren't served (post_lineup run, which
   filters to confirmed games, is unaffected). Model probabilities + raw diagnostic edges are still written for
   every game; only the *actionable* bet defers. This is the PRIMARY live-skill lever — the post_lineup serve is
   dense (disc-coverage 0.99), so betting from it (not morning) is what moves live skill toward the ceiling.
   Logged as `[SERVING-GUARD] … PRE-LINEUP … deferred`. (Complements Epic A1's SLA *timing* gate.) 5 unit tests
   (`TestLineupsConfirmedGate`).
2. **Make the offline benchmark point-in-time-honest. ✅ SHIPPED (2026-06-11).** The 0.42 is an upper-bound
   CEILING (it re-reads the post-game-dense row); the honest live number comes from scoring the ACTUALLY-SERVED
   predictions in `daily_model_predictions` against the outcome. Deliverables:
   - `betting_ml/scripts/honest_live_skill.py` — reusable point-in-time live tracker. Epic 30 PRIMARY metrics
     (H2H: accuracy/Brier/NLL/corr/ECE; totals: RMSE/MAE/MedAE/calib_80), scoped to the dense
     post_lineup/feature_store serve, with morning/intraday paths shown for contrast. First run (since 2026-01-01):
     **honest live home_win = corr −0.105 / Brier 0.299 / ECE 0.46 (n=15)** vs the 0.42 ceiling — i.e. the live
     model is ~0-skill and badly miscalibrated on the dense path too, but **n=15 is far too small for a verdict**;
     the job is to accumulate settled post_lineup/feature_store slates (now with the 30.3 serving-guard + Story
     30.5 umpire feed live) and watch the number move toward the ceiling. Totals honest live: MAE 3.38 / calib_80
     0.867.
   - `load_features()` docstring now carries the ⚠ NOT-POINT-IN-TIME ceiling caveat at the source, pointing future
     eval authors to the honest tracker. The true AS-OF-snapshot of the feature store remains the long-term fix
     (arch §Point-in-Time) — until then, offline evals via `load_features` are ceilings, not live KPIs.
3. **Exclude `has_full_data=FALSE` games from scoring or hard-flag them.** `_TODAY_QUERY` has no completeness
   filter; those ~8% of games are the heaviest-imputed and were never in the training distribution.
4. **Close the lineup-vs-cluster / archetype null gap** (`*_lineup_avg_xwoba_vs_cluster`,
   `*_lineup_archetype_avg_xwoba`): ~13% null even on the dense training surface, ~25–58% live — these are
   top-tier home_win drivers and the largest *recoverable* strong-tier nulls. Cross-ref
   [[project_posterior_staleness_jun2026]] (compute scripts unwired since 2026-06-03) and
   [[reference_bullpen_freshness_chain]] for the upstream populate path.

## How to verify (hand-off — >1 min, needs Snowflake + models)

```bash
# capture today's TRUE live-sparse profile (a past date reads the dense backfill and understates the skew)
uv run python betting_ml/scripts/serving_parity_report.py --date $(date +%Y-%m-%d)
# writes betting_ml/evaluation/feature_selection/serving_parity/parity_<date>.{md,json}
```

Re-measure live skill once ≥30–50 settled games exist under the dense **post_lineup feature_store** path
(disc-coverage ≥0.99): corr/Brier on that slice is the honest live number to compare against the 0.42 cap.
