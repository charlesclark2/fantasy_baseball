# E1.13 — Injury-feature + seasonnorm correction → served-model revalidation (2026-08-14)

**Story:** E1.13 (renumbered from E1.12) — the E9.48 (injury latest-event-wins fix) + E9.53
(seasonnorm fabricated-0.0) + E11.24-6c (matchup-sigma inflation) downstream revalidation,
under the E7.9 train/serve-consistency discipline. `best_alpha = 0` throughout — nothing here
is an edge, win-rate, or ROI claim.

**Headline verdicts**

| Question | Verdict |
|---|---|
| A. Injury features (`injured_player_count`, `injury_adj_avg_woba_30d`) in a served champion contract? | **NO — recorded NULL, no retrain** (0 of 6 contracts) |
| A′. Matchup-sigma signal in a served champion contract / any serving read? | **NO — recorded NULL, no retrain** |
| B. Seasonnorm NULL cure | **APPLIED in both copies**; reaches exactly ONE served contract (total_runs pre_lineup) |
| B′. §0.5 retrain-vs-incumbent for that contract | **INCUMBENT_STANDS (TIES)** — bounded-by-exposure null |
| Posterior-store audit (routed here after the E11.24 target-6 descope) | **Both stores CLEAN** on the inflation identity |

---

## Part A — injury-feature × served-contract intersection (the E7.9 step-1 discipline)

E9.48 corrected 42,416 player-game appearances (5.2%, 2021–2026) wrongly `is_injured=true`
(now 29), changing the historical values of `injured_player_count` + `injury_adj_avg_woba_30d`.

**Intersection with the six served champion contracts** (registry-resolved sidecars:
home_win post 21 / pre 38; run_diff post 15 / pre 126; total_runs post 15 / pre 16; plus the
rolled-back mh2_1 sidecar 25): **neither feature — nor `injury_adj_avg_xwoba_30d` — appears
in ANY of them** (case-insensitive scan of the full 162-column union). Per the pre-registered
rule: the corruption was in features the champions do not consume → **NO retrain; null
recorded** (the expected E7.9-style outcome — the eb_gb_pct precedent reached 1 of 6; this
reaches 0 of 6).

**Indirect routes checked (not just contract names):**
- The **offense_v1/v2 sub-models** DO train on all three injury features — but their signals
  are consumed by **no serving read**: `predict_today` reads only `bullpen_mu_v2` from
  `feature_pregame_sub_model_signals` (the Epic-19 OOD gate) and `write_serving_store` reads
  only `totals_perside_mu_v1/dispersion` (E2.7). Offense signals reach export/freshness/
  research surfaces only.
- ⚠️ **Flagged secondary finding (outside E1.13's gate, for the PM):** the **E2.3 per-side
  NegBin** sub-model trains on `injured_player_count`/`injury_adj_avg_*` (LINEUP_BASES in
  `train_perside_negbin.py`) and its serve-time signal generator scores the same matrix — so
  the E2.7 totals-distribution DISPLAY surface carries an E7.9-class skew (fit pre-E9.48,
  scored post-E9.48). Not a champion, not on any bet path (`bet_paused`, `best_alpha=0`),
  app-cosmetic blast radius. The corrected features are what any future E2.x per-side refit
  will see; carding that refit is a PM decision, not an E1.13 deliverable.

## Part A′ — matchup-sigma (E11.24-6c) × served contracts

`matchup_cell_sequential_posteriors`' `posterior_sigma` shipped ~7.1% too small into
`generate_matchup_signals` historically (repaired → 1.0000, duplicates stopped 7/19). The
matchup signal columns (`matchup_advantage_mu/sigma`, `matchup_volatility_signal`,
`matchup_k_pressure_signal`, `matchup_power_signal`) appear in **no served champion contract
and no serving read** (same consumer trace as above; remaining references are
export/freshness/ablation/layer3-research only). **NULL — no retrain.**

## Posterior-store audit (routed into E1.13 after the E11.24 target-6 descope)

The audit E9.53 item (2) called for, run on both unaudited stores. The identity: per chain,
`max(n_cumulative) == sum(n_obs)` — the E9.53 double-apply replays observations onto the
existing prior, so a replay breaks it at ~2× (the team store measured 2.72× before its
repair). Neither store has a games-played identity (`player` observations are PAs per
appearance; `matchup` PAs per cell-game), so the self-consistency identity is the right
instrument.

- **`player_sequential_posteriors`** (S3 mirror, 402,468 rows, 10,565 chains 2021–2026,
  batter/starter/bullpen × season): **0 broken identities; every ratio exactly 1.0000; zero
  duplicate game_pk rows.** No double-apply anywhere.
  - Residual (noted, different class): **56 chains (0.53%) carry TWO `is_current=true` rows**
    — all batter/xwoba, seasons 2021–2025, none in 2026. Chain content is correct (the
    identity holds); this is an SCD-2 flag-hygiene blemish on historical seasons, not
    inflation, and it cannot affect live serving (2026 is clean). Left for a PM card if a
    consumer is found ordering on it.
- **`matchup_cell_sequential_posteriors`** (Snowflake, current-season-only by design: 25
  cells, season 2026): **0 broken identities; ratio 1.0000; `is_current` clean** — the
  E11.24-6c repair state confirmed holding.

⇒ E1.13 (and any future story) can train on these stores; nothing blocked the bake-off.

## Part B — the E9.53 seasonnorm NULL cure (applied)

**The cure:** `coalesce((raw−mu)/nullif(sd,0), 0)` →
`(case when raw.<c> is null then null else coalesce((raw.<c>−mu)/nullif(sd,0), 0) end)::double`
— a missing RAW feature now carries a real NULL (imputer + `discriminative_coverage` see it);
a missing/zero-variance BASELINE with a present raw still coalesces to 0 (the documented
Story 27.7 regime-neutral behaviour, kept).

**Applied in BOTH copies** (the one-sided-edit trap): the dbt model
`dbt/models/feature/feature_pregame_game_features.sql` (DuckDB branch) AND the served Python
port `scripts/run_w1_lakehouse.py::_game_features_wrapper_sql`.
`test_w8b_wrapper_seasonnorm_parity.py` re-verifies token-level parity; its three
deferred-defect pins are flipped to the cured expectations (missing raw → NULL; missing raw
now distinguishable from genuinely-average; seasonnorm nullable), and the two
baseline-coalesce tests survive unchanged. The `test_team_seq_per_metric_resolution` doc-pin
is flipped from "deferred to E1.12" to "applied by E1.13 + the cure expression must stay".
INC-19 `::double` pin preserved (type-contract guard green). `dbt compile` 1516/1516.

**`--full-refresh` requirement — satisfied structurally:** the story's instruction predates
the E11.24 #675 view-flip. Today the SERVED artifact is the S3 parquet built by
`run_w1_lakehouse` `--w8b`, and `_build_one_sql` COPYs the **full history** on every run (no
incremental window); the Snowflake branch is a **view** over the ext table. So the first
`--w8b` run with the merged code rebuilds every historical row with the cure — no dbt
`--full-refresh`/DROP is involved. (The dbt DuckDB branch's incremental config is not the
served build path.)

**Exposure (measured, two instruments):**
- Served store parquet (all rows 2021+): **290 of 14,017 rows (2.07%)** carry ≥1 fabricated
  value among the six contract seasonnorm columns; per column: `home/away_bp_eb_xwoba`
  ~27–41/season, `home_bp_hard_hit_pct_30d` identical to home_bp_eb (same missing-bullpen
  games); the `team_sequential`/`off_xwoba_30d`/`pit_hard_hit_30d` raws have **zero** NULLs
  post-E9.53.
- Training matrix (12,078 target-bearing rows): **180 rows (1.49%)**, spread 21–43/season.

**Which served contracts the cure reaches:** exactly **one of six** —
`feature_columns_v6_total_runs_pre_lineup_served.json` (6 of 14 base features are
`_seasonnorm`, incl. 3 of its 7 core discriminative). home_win post/pre, run_diff post/pre,
total_runs post, and the mh2_1 sidecar carry none.

## Part B′ — the §0.5 retrain-vs-incumbent (total_runs / pre_lineup)

Harness: `betting_ml/scripts/e1_13_seasonnorm_cure_revalidation.py` (pre-registered locks in
source; guards in `betting_ml/tests/test_e1_13_seasonnorm_cure_harness.py`, 16 tests).

Design: 2 arms (a single pre-registered contrast; default INCUMBENT_STANDS) —
`incumbent_asfit` (fit on the pre-cure matrix, scored on CURED eval rows through its own
pre-cure imputer = ship-the-cure-keep-the-pickle) vs `refit_cured` (fit on the cured matrix)
— both ngboost_normal at the champion config, global RNG seeded (the MH2.5 NGBoost seeding
rule), window 2021+ (the champion's own convention; a wider window would conflate MH2.1's
question), 3 purged/embargoed folds, CRPS, non-finite scores REFUSED. The store-null mask is
computed from the **pre-swap** cached frame — the de-leak bullpen_v3 swap FILLS raw bp_eb
cells in the clean matrix, so a post-swap mask under-counts (measured: 0 vs 180).
Controls: untouched-eval-rows byte-exactness (held, max |Δ|=0), touched-rows paired delta
(the mechanism-can-act population, NF1.9), input-shift cost (same fit, two inputs).

**Result (full run, 2026-08-14 — `ablation_results/e1_13_seasonnorm_cure_bakeoff.{json,md}`):**

| Gate | Value | Bar | Read |
|---|---|---|---|
| CRPS margin (incumbent_asfit − refit_cured) | **+0.00127** | > 0.02 | **TIE** (16× under the floor) |
| DSR (fixed convention; folds as obs; n_trials=2; asymptotic V) | 0.9595 | ≥ 0.95 | clears — but the floor binds |
| PBO | UNDEFINED (single contrast, 3 folds — `pbo_evaluable=False`) | <0.2 | not "failed" (NF-W3 rule) |
| PIT-KS refit vs incumbent | 0.0766 vs 0.0760 (tol 0.0076) | not degraded | ok |
| Touched eval rows | 71 (of 5,688) | >0 | mechanism ACTIVE, not vacuous |

**VERDICT: INCUMBENT_STANDS (contest: TIES).** A within-floor win is a tie, and a tie ships
nothing (the pre-registered E7.9 rule).

**Why this null is trustworthy and final (not power-limited):** on the 71 rows the cure
actually touches, the refit IS better — paired delta **+0.086 CRPS** — but the pooled margin
is structurally capped at exposure × touched-row effect ≈ 1.25% × 0.086 ≈ **0.0011**, which
is the measured +0.0013. No fold count or window change moves the 1.5% exposure share, so
the 0.02 floor is unreachable **by construction** — a bounded-by-exposure null, not a
POWER_LIMITED one; no re-test trigger is published (publishing "needs N more seasons" here
would be the misleading direction NF-D18/MH2 warn against).

**Cost of shipping the cure WITHOUT a retrain (measured, not assumed):** the incumbent's own
fits scored on cured vs pre-cure eval rows differ by mean |ΔCRPS| **0.00315** per row
(pooled CRPS moves ≤0.004 in any fold, direction mixed) — far below the noise floor. The
cure is a correctness fix with sub-noise serving cost; the champion pickle stays.

## Operator steps (post-merge; also in the session handoff)

1. Merge PR → `dev` → (operator) promote to `main`; the box image ships the cure via
   `orchestration_cd` on the `main` merge. The next daily run's `--w8b` rebuilds the full
   wrapper history with the cure (no dbt full-refresh needed — see above). To apply + verify
   immediately instead of waiting for the daily (BOX):
   `docker compose -f services/dagster/aws/docker-compose.yml exec -T -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc python scripts/run_w1_lakehouse.py --w8b`
2. **🟥 Runtime gate** — after the first box build with the cure, verify on the box that the
   served parquet now carries NULLs (BOX):
   `docker compose -f services/dagster/aws/docker-compose.yml exec -T -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc python -c "import duckdb; c=duckdb.connect(); c.execute(\"INSTALL httpfs; LOAD httpfs; CREATE SECRET (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')\"); print(c.execute(\"select count(*) filter (where home_bp_eb_xwoba is null and home_bp_eb_xwoba_seasonnorm is null) as cured, count(*) filter (where home_bp_eb_xwoba is null and home_bp_eb_xwoba_seasonnorm = 0) as fabricated from read_parquet('s3://baseball-betting-ml-artifacts/baseball/lakehouse/feature_pregame_game_features/data.parquet')\").fetchone())"`
   — expect `cured ≈ 94+, fabricated = 0` (pre-cure reads `0, 94+`).
3. **Re-baseline `is_degraded`** (it rises by design: genuinely-missing core seasonnorm
   features now count as imputed; `is_degraded = discriminative_coverage < 0.85`). Baseline
   expectation from the measured exposure: ~1.5–2% of games gain 1–3 newly-imputed core
   features — most were already degraded-adjacent (missing bullpen block). Over the first
   week post-deploy, compare the served rate to the trailing pre-deploy week (LAPTOP):
   `uv run python -c "import duckdb,os; c=duckdb.connect(); c.execute(\"INSTALL httpfs; LOAD httpfs; CREATE SECRET (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')\"); print(c.execute(\"select game_date, prediction_type, count(*) n, sum(case when is_degraded then 1 else 0 end) degraded from read_parquet('s3://baseball-betting-ml-artifacts/baseball/lakehouse/daily_model_predictions/**/*.parquet') where game_date >= '2026-08-07' group by 1,2 order by 1,2\").df().to_string())"`
   (export `AWS_DEFAULT_REGION=us-east-2` first). A step-change ≳5pp sustained = investigate;
   ~0–2pp = the expected re-baseline, record the new steady rate.
4. (Optional confirmation) re-run the bake-off on the post-rebuild store (LAPTOP, ~5 min):
   `uv run python betting_ml/scripts/e1_13_seasonnorm_cure_revalidation.py --s3 --refresh-cache`
   — the harness is store-vintage-robust (it reconstructs both views either way), so this is
   a confirmation, not a dependency; expect the same TIES verdict.

## What survives / what does not

- SURVIVES: the E9.48/E9.53/E11.24-6c corrections themselves (all shipped previously);
  the cure (this PR); the incumbent v6 champions, all six contracts, unchanged.
- The tiny consistent refit direction (+0.0013 pooled, 3/3 folds, DSR 0.96) is REAL but
  sub-floor; it is not bankable and does not compound with more data (exposure-capped). If a
  future story retrains total_runs pre_lineup for its own reasons, fitting on the cured
  store inherits this for free.
- No changelog entry (internal serving/model; nothing in `frontend/` reads these columns).
