# Model Work Roadmap

**Scope:** model/ML work only (Track-B sub-models, base models, serving, eval, meta-model). Application/
frontend/infra work is tracked separately. Authored 2026-06-13.

Story specs live in `quant_sports_intel_models/baseball/implementation_guide.md`; this file is the
sequencing/priority layer over them.

---

## The thesis that orders everything

Live `home_win` skill is ~0 today — **not** because the models are weak (offline `home_win` corr ≈ 0.42)
but because of **serving skew**: the morning serve imputes ~30% of the feature matrix to constants
(Story 30.3 root cause; the feature store is sparse pre-lineup, dense post-game). **Until point-in-time
serving is fixed (Story 30.6), no offline model gain converts to live edge.**

Consequence for sequencing: finish the cheap in-flight loop → make serving + eval honest → *then* invest
in sub-model quality. Sub-model and blend gains are invisible in production until serving is fixed.

---

## Phase 0 — Finish the normalized-contract loop *(in-flight, cheap, do first)*

Closes the loop opened by Story 27.7 (season-normalized contact features, totals v5 promoted 2026-06-13).

| Story | What | Effort | Notes |
|---|---|---|---|
| **27.8** | Retrain home_win + run_diff on the normalized contract | M | ✅ GATED 2026-06-14 — **split: home_win PROMOTE (Δbrier −0.0048, clean) → v6; run_diff HOLD** (Δmae −0.0185 sub-floor + 2026 regresses → stays v5 raw). No override applied. Seasonnorm run_diff contract shelved. |
| **30.9** | Learned h2h ensemble (replace the hand-set 50/50 blend) | M | 🟢 **Offline build UNBLOCKED** — both inputs now final (home_win v6 seasonnorm local artifact + run_diff v5). ⚠ **Live wiring SHELVED: `best_alpha=0.0`** (posterior = pure market) → no live payoff until the 30.6 alpha-unlock. Build+gate offline, persist artifact+eval, defer wiring. Calibrator must be refit when w changes (Platt fit on 50/50). |
| *(op)* | Re-run the v6 prediction backfill | S | **Deferrable** — at `best_alpha=0` the only value is refreshing recorded h2h columns (CLV bookkeeping); bundle with the 30.6 alpha-unlock cycle to avoid a double backfill. Machinery: `TARGET_ENV=prod predict_today --start … --is-backfill` (idempotent per date+version). |

⚠ Live payoff of Phase 0 is **gated on Phase 1** — these improve the offline models, whose live skill stays
capped until point-in-time serving lands.

---

## Phase 1 — Make serving + eval honest *(the keystone — highest leverage on the list)*

| Story | What | Effort | Notes |
|---|---|---|---|
| **30.12** | Feature-store completeness audit & backfill-degradation policy | S/M | ✅ **DONE 2026-06-14.** 317 contract feats → after triage **~15–20 genuine structural gaps** (not the 131 the pooled bar over-flagged); the big "2026 bump" is the **serving-skew signature** (whole-row sparsity on recent games) = 30.6's territory, not a dbt fix. Pythagorean floor re-classed **2024-only, not structural** (downgraded). Spillovers: `left_ft`→`left_line_ft` folds into run_diff's next retrain; pitcher-cluster coverage → 7.6. |
| **31.0** | Data-expansion scoping spike — ingested-data utilization & orthogonality audit | S (spike) | ✅ **DONE 2026-06-15.** Per-class verdicts feed 31.1/31.2/31.3 — all **gated on serving honesty (30.6)**; re-running feature selection on skewed data just re-prunes. |
| **30.6** | ⭐ Serving-skew fix (live-ceiling lift) | **L** | The keystone — CONFIRMED 2026-06-14: same model scores corr **0.61 offline-dense vs 0.016 served** (not an illusory ceiling). Mechanism = starter-EB + lineup blocks NULL at serve (stale SCD-2 starter chain), NOT value-shift → **fix serve density, not forward-capture**. Fix (A) **shipped + verified** 2026-06-14: starter_id null 80%→0; **today's serve-time starter-EB null 62.5%→0.13 (bleed stopped for today's bet)**. Residual +1/+2-day EB gap = posterior-staleness → folded into A2.11. **NEXT: Lever 2** (post_lineup re-score binding) → forward re-measure live skill (~0→~0.6) → alpha re-tune → 27.8/30.9 v6 bundle. |
| **30.13** | ⭐ Feature-store freshness guarantee (build-ordering + serve-time freshness gate) | M | **HIGH** — the durable other half of 30.6 fix (A). Guarantees serving-path feature models rebuild from the latest ingestion BEFORE predict_today + a serve-time freshness gate (abstain on staleness), so the keystone lift can't silently regress. Generalizes the SCD-2 staleness → the posterior-staleness class. Sequence right after the 30.6 re-measure. |
| **30.8** | Pre-lineup and post-lineup prediction contracts | M | Tightly coupled to 30.6 (morning projected-lineup vs confirmed-lineup confidence tiers; don't let the morning pick degrade to imputed output). |
| **A2.11** | Migrate EB posteriors from Python compute to dbt models | M | 🟢 **ACTIVATED 2026-06-14 (correctness driver, not cost); 5 dbt models on disk** (`eb_posteriors/` — batter/starter/bullpen/bullpen-team + int_bullpen_ali). **Owns the 30.6 residual:** the Python `eb_starter_posteriors` is game_pk-scoped to today's slate → starter-EB NULL for +1/+2-day games; sourcing the dbt model from `stg_statsapi_probable_pitchers` (full schedule spine) closes it by construction. Validate byte-for-byte vs the Python table on closed 2025, then cut over. The durable half of the keystone — pick up right after the 30.6 levers. |

---

## Phase 2 — Sub-model & base-model quality *(Track B foundations)*

Do these **after** Phase 1 — sub-model gains only show up in production once serving is honest.

| Story | What | Effort | Notes |
|---|---|---|---|
| **30.2** | Wire sub-model distributional outputs into the base models (Bayesian-leverage audit) | M | The bridge into the Track B revisit. **The biggest "use what we have better" lever** — sub-models already emit σ; the base models discard it. Directly attacks the totals variance-deficiency (29.1). Retrains Layer 2 only (no sub-model retrain). **Gated behind 30.6 + 30.8** — σ-features are NULL-pre-lineup, the exact serving trap. |
| **31.1** | Re-evaluate skew-pruned data classes on honest serving data | M | The action half of 31.0. Re-run feature selection per target with the (B) skew-pruned classes forced back in, AFTER serving is honest. **Gated on 30.6 + 30.12 + 31.0** — re-running on skewed data just re-prunes. |
| **31.2** | Wire catcher framing (run-prevention) into totals + h2h | S/M | The clearest under-wired class — framing in `mart_catcher_framing`, 0 promoted contracts, and totals has zero run-prevention input. Additive wiring + ablate. Soft-gated on 31.0's orthogonality finding. |
| **31.4** | Weather pipeline repair + totals retrain | S | Pipeline FIXED + DQ-validated 2026-06-15 (`[[project_weather_repair_and_team_oaa]]`): not a join bug — forecast_pregame-only filter excluded all pre-2026 history; dual-source fix (observed backfill) lifts coverage 396 → 12,708 games. NGBoost `--force-weather` retrain wired, awaiting run. Team-OAA-for-totals CLOSED (deadweight, corr −0.023). h2h does NOT use weather. |
| **31.4b** | LightGBM-monotone weather challenger (totals) | S | CONDITIONAL, gated on 31.4's NGBoost result. The only base-learner swap worth doing — monotone constraints (`temp_f`+, `wind_component_mph`+) NGBoost can't express; regularizes thin weather regimes. RUN only if weather is signal-bearing-but-noisy in NGBoost. Reuses 10.10 quantile-LGBM infra. If it still misses the market → 3rd estimator-swap confirmation the gap is architecture (30.2 → Epic 32), not the learner. |
| **3A.3** | Park-type hierarchical prior | S | Run-environment sub-model. |
| **5A.6** | Continuous aging-curve EB prior | S | Starter sub-model (replaces age-band points with a continuous curve). |
| **7.6** | Pitcher-cluster coverage (cold-start / unclustered-starter fallback) | M | Surfaced by 30.12: ~24.7% of games have the opposing starter unclustered (prior-season-lag join → rookies/low-IP/relievers) → the `*_vs_cluster` matchup family is null for a quarter of games. Leakage-safe AS-OF + arsenal cold-start fallback; ablate. Batter-archetype coverage is the same shape (fold in or sibling). **(D)-bucket source = Story 31.3 prospect/minor-league arsenal.** |
| → | **Track B revisit** — all sub-models + the Layer 3 section | L | Strategic theme. Sequence it here: take the learnings (market-blindness, regime-normalization, serving parity) back to every sub-model and the Layer-3 blend. |

---

## Research / exploratory bucket *(opportunistic; low urgency)*

| Story | What | Effort | Notes |
|---|---|---|---|
| **27.9** | Exogenous run-environment leading indicators — ball-CoR scoping spike | S (spike) → ? | Promoted from 27.6 Task 4. The **causal** successor to 27.7's pragmatic season-norm fix: model the ball/run-environment driver directly via an exogenous *leading* signal (the one untried data class). It's a **scoping spike first** (inventory + orthogonality), cheap to start; only proceeds to modeling if a signal clears coverage + orthogonality, gated on the unchanged kill criterion. Payoff is downstream of serving honesty (30.6) and totals stays `bet_paused`, so it's genuinely low-urgency — do it when curiosity or a slow week allows, not on the critical path. |
| **31.3** | Genuinely-new-class scouting (prospect arsenal · injury/roster · run-env) | S (spike) | The (D) new-needed bucket from 31.0 — the only items needing net-new ingestion. Prospect arsenal feeds 7.6 cold-start; injury/roster feed complements 30.6; folds 27.9 (ball-CoR) as the run-env member. LOW — only after the (B)/(C) re-use list is exhausted (re-using ingested data is strictly cheaper than new ingestion). |
| **A2.14** | Migrate archetype posteriors to dbt (KMeans-in-SQL) | M-L | DEFERRED follow-on of A2.11 (which migrated the 3 closed-form EB families). Archetype is a **sklearn KMeans soft-assignment** (centroids + StandardScaler + Gaussian softmax + Dirichlet prior + VARIANT JSON) — a categorically harder, higher-risk SQL port, carved out for its own design+validation. **Pull forward ONLY if** the archetype Python op becomes a measurable COMPUTE_WH line item OR a train/serve skew shows up in the `*_vs_cluster`/archetype features; else it stays here. Spec stub in the impl guide. |

---

## Parallel track — live-accumulation gated *(unlocks by calendar, not build order)*

These accumulate live CLV-labeled games as the season plays; you **trigger** them at thresholds, you don't
"build" them on demand.

| Story | Unlock | What |
|---|---|---|
| **12.4** | ≥50 | ✅ **CONVERGED + SERVING 2026-06-16** — H2H Bayesian sequential CLV meta-model; all 3 gates pass, temporal AUC 0.595 (real discrimination). Served on the morning row via `predict_today.py`. |
| **12.12** | ≥50 | ✅ **BUILT + SERVING 2026-06-17** — totals arm of the meta-model (parity with H2H for beta display). Honest result: **no OOS discrimination** (temporal AUC 0.446) → Tier-A display ships framed as near-flat/low-information; Tier-B gating on totals meta is OFF. |
| **12.13** | — | 🔴 **LEVER 1 CLOSED 2026-06-17** — Layer-4-feature discrimination lift was negative on BOTH markets (H2H 0.595→0.588, totals 0.446→0.448); `edge_mag` already captures the CLV signal. **v0 retained.** Lever 2 (post-lineup meta variant) untested, low-priority, not blocking. |
| **O.5 / 12.9** | — | ✅ **DONE** — weekly Bayesian meta-model retrain wired into Dagster (`weekly_meta_model_job`, Wed 10:00 UTC), both markets as independent failure domains, S3-upload + convergence gate; serve-side S3 pull in `predict_today.py`. (12.9 collapsed into O.5.) |
| **19.3** | ≥50 live CLV games | Backtest gate: confirm `qualified_bet` (= Layer-4 non-abstain side **AND** meta P(CLV>0) > per-market τ) shows better CLV than unqualified before promoting it to the default view. **No longer waits on 12.13** — "definition D" collapsed into "definition C (base meta IS the gate)." Forward CLV labels accrue through early/mid-July; follow-up **2026-07-01** (also the 12.5 checkpoint). |
| **12.5** | ≥100 served-then-CLV-observed games since go-live + 12.4 converging | Meta-model integration into Epic 19 (the gate τ tuning + view promotion). Forward-count definition; follow-up **2026-07-01**. |
| **12.6** | ≥500 | Frequentist exploratory meta-model. |

⚠ **Gate these on Story 30.6 as well, not just the count** — a CLV meta-model trained on zero-skill live
predictions learns nothing. 12.4/12.12 converged on the *pre-test* surface; the live-population retrains
(O.5 weekly) only become trustworthy once serving is honest *and* the live count clears.

---

## Not active — cleanup / fold elsewhere

| Item | Status |
|---|---|
| **30.10** | ✅ CLOSED 2026-06-13 — the totals v5 Normal market-blind refit (Story 27.7) *was* 30.10's deliverable. |
| **29.2 / 29.3** | ⛔ SHELVED by the 29.1 gate — totals trails the market line by ~0.53 RMSE/game; calibration can't manufacture an alt-line edge around a worse-centered estimate. Blocked until the central estimate reaches market parity. |
| **12.10** | ❌ CANCELLED (Betfair feed). |
| **12.11** | Parlay WebSocket streaming — infra/app, not model work → app session. |
| **A2.13** | Bovada totals web-app coverage audit — data-quality, app-adjacent; fold into 30.12's pass or the app session. |

---

## Recommended start order

The two cheap read-only spikes (**30.12 ✅, 31.0 ✅**) are now DONE — they confirmed the diagnosis and
de-risked the keystone. Nothing cheap is left to hide behind: the critical path is the keystone itself.

1. ⭐ **30.6 Lever 2** (post-lineup re-score binding) — **the immediate next action.** Fix (a) already stopped
   today's starter-EB bleed (62.5%→0.13% null); Lever 2 binds picks to the dense post-lineup path, then
   **forward-re-measure live skill (~0 → ~0.6 expected)** and re-tune `best_alpha` off zero.
2. **A2.11 cutover** (durable 30.6 residual fix — 5 dbt EB models built; validate byte-for-byte vs Python on
   closed 2025, then cut over) + **30.13** (serve-time freshness gate, so the lift can't silently regress).
3. **Phase 0 bundle** (27.8 home_win v6 → 30.9 learned h2h ensemble → v6 re-backfill) — now has a live payoff
   path once `best_alpha` unlocks. Includes the `left_ft`→`left_line_ft` swap (30.12 spillover) in run_diff's retrain.
4. **Phase 2** (30.2 → 31.1 / 31.2 → 7.6 → 3A.3 / 5A.6 → Track B revisit) — sub-model quality, now visible in prod.
5. Trigger the **gated 12.x / 19.3** track as live counts clear *and* 30.6 has landed (follow-up **2026-07-01**).
