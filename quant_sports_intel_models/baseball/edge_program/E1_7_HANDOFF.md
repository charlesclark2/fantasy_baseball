# Story E1.7 — De-leak the production bullpen EB feature — Operator runbook

**Date:** 2026-06-18 · **Status:** ✅ DATA LAYER DONE + VALIDATED (de-leak + full-history rebuild + parity PASS); ⏳ MDA / slim re-derive / retrains remain (operator, retrains batch after E1.8) · **Track:** Edge Program · Tier-0 correctness · touches the live champions

> **✅ Verified 2026-06-18:** §3.A full-history rebuild done (`feature_pregame_game_features` bullpen coverage 96.9–98.9% for 2016–2026; scheduled slate 37/37). §3.B parity **PASS** on 2026-06-10/13/16 (n=88): Jaccard **1.0**, n_relievers **88/88**, corr **0.962**, mean|Δ| **0.0024** vs `aggregate_team_v3(equal)`. §3.C MDA-collapse **DONE on all 3 targets** (xwOBA #1/#2 → 0% everywhere; coverage_pct rises to #1/#2). §3.D slim contracts **RE-DERIVED** (de-leaked: total_runs 14→21, home_win 31→21, run_diff 19→15; written as `*_deleaked_2026.json`, INTERIM pending E1.8). Remaining = §3.E retrains (batch after E1.8, on the post-E1.8-re-derived contracts).

---

## 1. TL;DR

E2.1b proved the #1/#2 champion feature `bp_eb_xwoba` was a **within-game leak**. E1.7 fixes it **in the production dbt path (Path A — pure dbt, no new Python op)**:

`dbt/models/eb_posteriors/eb_bullpen_team_posteriors.sql` is rewritten from an **outs-in-game-weighted average over the arms that actually pitched the eval game** → an **equal-weight mean over the team's leakage-safe trailing-30d pre-game relief pool**, **spined on `mart_game_spine`** so the feature now also **populates for tonight's scheduled slate** (the old appeared-in-game roster only ever produced rows for completed games → null at serve = part of the offline→live collapse).

Output columns are unchanged → **zero downstream rename**; `mart_bullpen_effectiveness` and the feature marts are untouched in shape.

⚠️ **Offline NLL/Brier/importance WILL DROP — that is correct (a peek was removed), NOT a regression.** Gate ONLY on live/forward + serving-parity.

---

## 2. What shipped this session (code-complete, no Snowflake run)

- **`dbt/models/eb_posteriors/eb_bullpen_team_posteriors.sql`** — de-leaked (spine + trailing-30d equal-weight pool). `dbtf compile` clean (9/9).
- **`dbt/models/eb_posteriors/schema.yml`** — model + column descriptions updated to the de-leaked construction.
- **`betting_ml/scripts/eb_priors/parity_check_bullpen_deleak.py`** — SQL↔Python parity guardrail (the dbt table vs `aggregate_team_v3(weight_mode='equal')`): asserts pool-membership Jaccard ≈ 1.0 + xwoba corr ≥ 0.95, mean|Δ| ≤ 0.015 (the residual Δ is the leakage-safe EB-freshness gap — last-appearance EB vs fresh as-of-tonight). Read-only; operator-run.

---

## 3. Operator run-order

### A. Rebuild the de-leaked feature path (Snowflake; >1 min)

⚠️⚠️ **MUST full-refresh the UPSTREAM per-reliever source too — `eb_bullpen_posteriors` only holds ~12 recent days** (verified 2026-06-18: min 2026-06-06, max 06-17). Both `eb_bullpen_posteriors` and `eb_bullpen_team_posteriors` are rolling-window incrementals that do NOT accumulate full history; the de-leaked team table can only build where its source has rows. A first attempt that selected `eb_bullpen_team_posteriors+` (downstream only) populated the de-leaked feature for the recent/scheduled window **but left it NULL across all of 2015–2026-pre-June** in `feature_pregame_game_features` (0% historical coverage). The retrain matrix needs the de-leaked bullpen across ALL seasons, so the per-reliever source must be rebuilt full-history FIRST (its base `stg_batter_pitches` has all 12 seasons / 7.6M pitches → it can).

Also (dbt-fusion quirk, [[feedback_dbtf_incremental_fullrefresh]]): `--full-refresh` does a MERGE, not DROP+CREATE, for incrementals → **DROP each incremental first** so it truly rebuilds full history.

```bash
# 1. DROP the three incrementals so full-refresh rebuilds ALL history (not a bounded MERGE):
#    Snowflake (MCP, fully-qualified, no USE):
#      DROP TABLE IF EXISTS baseball_data.betting.eb_bullpen_posteriors;
#      DROP TABLE IF EXISTS baseball_data.betting.eb_bullpen_team_posteriors;
#      DROP TABLE IF EXISTS baseball_data.betting.mart_bullpen_effectiveness;
# 2. Rebuild upstream→downstream in one full-refresh selection (run from dbt/):
dbtf build --full-refresh -s eb_bullpen_posteriors+
#   eb_bullpen_posteriors (per-reliever, ALL seasons from pitches — the heavy step)
#     → eb_bullpen_team_posteriors (de-leaked, ALL seasons)
#     → mart_bullpen_effectiveness → feature_pregame_team_features
#     → feature_pregame_game_features  (champion matrices, de-leaked across history)
```
**Verify (both):**
- Scheduled slate: `eb_bullpen_team_posteriors` has rows for today's scheduled game_pks; `home/away_bp_eb_xwoba` non-null for them. *(Already confirmed 37/37 on the first partial rebuild.)*
- **Historical coverage (the gap to close):** `home_bp_eb_xwoba` non-null % per `game_year` in `feature_pregame_game_features` should be high for 2021–2026 (was 0% after the downstream-only rebuild).

### B. Parity guardrail (Snowflake; read-only)
Use dates that exist in BOTH the dbt table and the per-reliever source. BEFORE the step-A full-history rebuild that means the recent window only (e.g. 2026-06-10/13/16); AFTER it, any in-season date works.
```bash
uv run python betting_ml/scripts/eb_priors/parity_check_bullpen_deleak.py \
    --dates 2026-06-10 2026-06-13 2026-06-16
# Expect (AFTER the §3.A full-history backfill): ✅ PARITY (Jaccard ≈ 1.0, corr ≥ 0.97).
# "✗ no overlapping rows" ⇒ dates not built in the dbt table (source/table spans a recent window — see §3.A).
```
**⚠️ Pre-backfill, parity DIVERGES on roster but AGREES on value — and that is expected, not a bug.** First run (2026-06-18, dates 06-10/13/16, n=88): pool Jaccard **0.67**, n_relievers exact 0/88, but xwoba mean|Δ| **0.0062** (within gate) / corr 0.85. Root cause confirmed: the dbt pool is sourced from the thin `eb_bullpen_posteriors` (~12 days) so each "trailing-30d" pool is truncated to the available days (06-13 games: dbt pool avg **9.17** vs true 30-d pool **13.70** → 9.17/13.70 = 0.669 ≈ the observed Jaccard) — the dbt pool is a clean SUBSET of the true pool, which is why the EBs it does carry match. The equal-weight aggregation math is therefore validated; **the membership gate only becomes meaningful after §3.A rebuilds the per-reliever source over full history.**

### C. Finish the MDA-collapse documentation — home_win + run_diff (the v3 caches from E2.1b must exist)
Run against the **still-leaky matrix cache** (do **NOT** `--refresh-cache` after step A) so the `static` arm is the leaky incumbent and the `v3` arm is the de-leaked feature — that contrast IS the collapse. Each pair is parallelizable.
```bash
# leaky baseline (static) + de-leaked (v3) — one pair per target
uv run python betting_ml/scripts/clustered_feature_importance.py --target home_win
uv run python betting_ml/scripts/clustered_feature_importance.py --target home_win --bullpen-version v3
uv run python betting_ml/scripts/clustered_feature_importance.py --target run_diff
uv run python betting_ml/scripts/clustered_feature_importance.py --target run_diff --bullpen-version v3
# total_runs: already done in E2.1b (clustered_importance_total_runs_bullpen_v3.json)
```
Expected (mirrors total_runs): `home/away_bp_eb_xwoba` collapses #1/#2 → noise (0% retained); `coverage_pct`/`uncertainty` rise.

> **Note:** the leaky-static baselines for home_win + run_diff ALREADY EXIST from E1.3 (`clustered_importance_home_win.json` / `_run_diff.json`, 2026-06-17), so only the `--bullpen-version v3` arm needs running; compare each new `*_bullpen_v3` report to its Jun-17 static counterpart. Run WITHOUT `--refresh-cache` (swap only the bullpen channel on the same matrix).

**✅ COLLAPSE CONFIRMED — all three targets.**

`home_win` (static 178 → v3 174 clusters, 2026-06-18; 158/174 v3 clusters are noise):

| feature | static (leaky) rank / imp | v3 (de-leaked) rank / imp | retained |
|---|---|---|---|
| `home_bp_eb_xwoba` | **#1** / +0.0352 | #10 / +0.0002 | **1%** |
| `away_bp_eb_xwoba` | **#2** / +0.0265 | #155 / −0.0001 (NOISE) | **~0%** |
| `home_bp_eb_uncertainty` | #3 / +0.0092 | #172 / −0.0001 (NOISE) | ~0% |
| `away_bp_eb_uncertainty` | #4 / +0.0084 | #172 / −0.0001 (NOISE) | ~0% |
| `home_bp_eb_coverage_pct` | #6 / +0.0017 | **#1** / +0.0080 | rises to top |
| `away_bp_eb_coverage_pct` | #10 / +0.0003 | **#2** / +0.0037 | rises |

`run_diff` (static 147 → v3 144 clusters, 2026-06-18; 132/144 v3 clusters are noise):

| feature | static (leaky) rank / imp | v3 (de-leaked) rank / imp | retained |
|---|---|---|---|
| `home_bp_eb_xwoba` | **#1** / +0.2139 | #24 / +0.0009 | **0%** |
| `away_bp_eb_xwoba` | **#2** / +0.1671 | #31 / +0.0008 (NOISE) | **0%** |
| `home_bp_eb_coverage_pct` | #3 / +0.0659 | **#1** / +0.1094 | rises to top |
| `away_bp_eb_coverage_pct` | #6 / +0.0271 | **#2** / +0.0789 | rises |
| `home_bp_eb_uncertainty` | #4 / +0.0649 | #6 / +0.0028 | 4% |
| `away_bp_eb_uncertainty` | #5 / +0.0618 | #6 / +0.0028 | 5% |

**✅ STEP C COMPLETE — collapse confirmed on ALL THREE targets.** Consistent pattern everywhere: **the `bp_eb_xwoba` VALUE was ~100% leak (→ 0% retained on every target), and `coverage_pct` (data depth) rises to #1/#2.** `uncertainty` is modest/variable (run_diff 4–5%, total_runs ~28%, home_win ~0%). So E1.3's "bullpen EB dominates every target" headline was the leak on all three; the real (modest) pre-game bullpen signal is data depth, not the EB estimate. → For the slim re-derivation (step D): **keep `bp_eb_coverage_pct`; drop `bp_eb_xwoba` (all 3 targets) and `bp_eb_uncertainty` (home_win/run_diff; total_runs may keep it).**

### D. Re-derive the slim 14/31/19 contracts on the de-leaked matrix (feeds E6.7) — ✅ DONE 2026-06-18 (INTERIM, re-derive once more after E1.8)
Re-selected the signal-bearing clusters (paired-bootstrap CI > 0) from the three de-leaked `*_bullpen_v3` reports — the same E1.3 prune procedure, now on the leakage-safe bullpen matrix. **Written as NEW files (old contaminated ones preserved for provenance/diff):**
- `betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_deleaked_2026.json` — **14 → 21**
- `betting_ml/models/home_win/feature_columns_xgb_classifier_pruned_clustered_deleaked_2026.json` — **31 → 21**
- `betting_ml/models/run_differential/feature_columns_ngboost_pruned_clustered_deleaked_2026.json` — **19 → 15**

**Diff highlights (old contaminated → de-leaked):**
- `total_runs` GREW (14→21): both `*_bp_eb_xwoba` dropped; +11 pitching/starter signals (`home_pit_woba_against_*`, `home_starter_whiff_rate_14d`, `away_starter_avg_fastball_velo`, …) surfaced once the leak stopped dominating.
- `home_win` near-total turnover (31→21; 26 dropped / 16 added): the whole leaky EB block shrank (`*_bp_eb_uncertainty`, `*_starter_eb_*`, `away_avg_eb_*` out); `elo_diff` + `pythagorean_win_exp_diff` + lineup-vs-cluster + `coverage_pct` in.
- `run_diff` (19→15): `away_bp_eb_xwoba` + `away_team_sequential_bullpen_xwoba` out; `elo_diff` + `pythagorean_win_exp_diff` in.
- **Cross-target:** `elo_diff` & `pythagorean_win_exp_diff` enter BOTH H2H targets — fundamental team-strength features the leaky bullpen rank had been masking. `bp_eb_coverage_pct` retained on all three.
- **bp_eb_xwoba nuance:** dropped on total_runs + the away side everywhere; RETAINED only on home_win/run_diff *home* side, and only as a correlated **passenger** of `home_team_sequential_bullpen_xwoba` (the cluster's real, non-leaky signal; CI low +0.00000 / +0.00006). E6.7 may legitimately drop it and keep just the sequential posterior.

⚠️ **INTERIM** (flagged in each file's `_provenance`): these were re-derived post-de-leak but PRE-E1.8. E1.8 (full leakage sweep) may de-leak more features and shift the prune → **re-derive ONCE MORE after E1.8 before the §3.E retrains consume a contract.** Also: gate any new contract via `promotion_gate_eval.py --purged-cv` before promotion (E1.3/E1.4 AC), since home_win especially is a near-total turnover.

### E. ⏸️ STAGED — champion retrains (DO NOT RUN YET)
**Decision (PM 2026-06-18): do NOT anchor to the legacy pre-7M batch.** Run all 3 NGBoost retrains **once, after E1.8 (the full leakage sweep)**, on the fully de-leaked + leak-swept matrix — E1.8 will likely surface more leaks needing the same retrains, so retraining now and again post-E1.8 is a wasteful double ~3 hr batch. **Guardrail:** if E1.8 slips materially, retrain after E1.7 rather than leave the leaked champions live indefinitely.

Ready-to-run (each >1 hr NGBoost/XGB; run after the de-leaked matrix exists — step A — with a cache refresh):
```bash
uv run python betting_ml/scripts/run_xgb_home_win_search.py          # home_win
uv run python betting_ml/scripts/run_ngboost_run_diff_search.py      # run_differential (Normal only; LogNormal excluded)
uv run python betting_ml/scripts/run_ngboost_total_runs_search.py    # total_runs
# then: rebaseline_purged_cv.py --target all  + promotion_gate eval, and update model_registry.yaml
```

---

## 4. Validation gate (per the AC — critical)
- **Offline NLL/Brier/importance WILL DROP. That is the de-leak working, not a regression. Do NOT gate on it.**
- **Honest gate = live/forward + serving-parity:** (1) `bp_eb_xwoba` is non-null for scheduled games at serve time (was null); (2) `serving_parity_report.py` shows the bullpen channel no longer degraded pre-lineup; (3) once retrained (step E), live `model_health_metrics.py` skill rises toward the now-honest (lower) offline number rather than collapsing.

## 5. `git add` (operator commits — session does not)
```
git add dbt/models/eb_posteriors/eb_bullpen_team_posteriors.sql
git add dbt/models/eb_posteriors/schema.yml
git add betting_ml/scripts/eb_priors/parity_check_bullpen_deleak.py
git add quant_sports_intel_models/baseball/edge_program/E1_7_HANDOFF.md
git add quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md
git add quant_sports_intel_models/baseball/edge_program/story_prompts.md
# de-leaked slim contracts (step D — NEW files; old contaminated ones left in place):
git add betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_deleaked_2026.json
git add betting_ml/models/home_win/feature_columns_xgb_classifier_pruned_clustered_deleaked_2026.json
git add betting_ml/models/run_differential/feature_columns_ngboost_pruned_clustered_deleaked_2026.json
# de-leaked MDA reports (step C — commit alongside the existing total_runs_bullpen_v3 if that's the convention):
git add betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_home_win_bullpen_v3.json
git add betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_run_diff_bullpen_v3.json
git add quant_sports_intel_models/baseball/ablation_results/clustered_feature_importance_home_win_bullpen_v3.md
git add quant_sports_intel_models/baseball/ablation_results/clustered_feature_importance_run_diff_bullpen_v3.md
```
**Excluded (gitignored — go to S3/registry, not git):** per-reliever caches `betting_ml/models/sub_models/bullpen_v3/*.parquet`; any retrained `*.pkl`/model binaries.

## 6. Not user-facing
Model/correctness change only — **no `frontend/data/changelog.json` entry** (no app surface change).
