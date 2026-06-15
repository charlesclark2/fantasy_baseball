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
| **30.12** | Feature-store completeness audit & backfill-degradation policy | S/M | Specced 2026-06-13 (surfaced by the v5 backfill). Quantifies which features are sparse when → **directly feeds 30.6 + 30.8 + 31.0**. Can run in parallel with Phase 0. Known lead: `pythagorean_win_exp_diff` ~6.5% persistent mid-season null floor (`[[project_pythagorean_null_floor]]`). |
| **31.0** | Data-expansion scoping spike — ingested-data utilization & orthogonality audit | S (spike) | Specced 2026-06-15. **Cheap, read-only, run now (parallel with Phase 0/30.12).** Recon finding: the orthogonal classes (weather, OAA, framing, bat-tracking, granular park) are ALREADY ingested but were **pruned from the promoted seasonnorm contracts** — totals has 0 weather/OAA/framing, home_win 0 weather/framing/park. The spike decides per class: tapped-out vs skew-pruned (false negative) vs under-wired vs new-needed. **Its action items (31.1/31.2) are gated on serving honesty; the audit itself is not.** |
| **30.6** | ⭐ Serving-skew fix (live-ceiling lift) | **L** | The keystone — CONFIRMED 2026-06-14: same model scores corr **0.61 offline-dense vs 0.016 served** (not an illusory ceiling). Mechanism = starter-EB + lineup blocks NULL at serve (stale SCD-2 starter chain), NOT value-shift → **fix serve density, not forward-capture**. Fix (A) **shipped + verified** 2026-06-14: starter_id null 80%→0; **today's serve-time starter-EB null 62.5%→0.13 (bleed stopped for today's bet)**. Residual +1/+2-day EB gap = posterior-staleness → folded into A2.11. **NEXT: Lever 2** (post_lineup re-score binding) → forward re-measure live skill (~0→~0.6) → alpha re-tune → 27.8/30.9 v6 bundle. |
| **30.13** | ⭐ Feature-store freshness guarantee (build-ordering + serve-time freshness gate) | M | **HIGH** — the durable other half of 30.6 fix (A). Guarantees serving-path feature models rebuild from the latest ingestion BEFORE predict_today + a serve-time freshness gate (abstain on staleness), so the keystone lift can't silently regress. Generalizes the SCD-2 staleness → the posterior-staleness class. Sequence right after the 30.6 re-measure. |
| **30.8** | Pre-lineup and post-lineup prediction contracts | M | Tightly coupled to 30.6 (morning projected-lineup vs confirmed-lineup confidence tiers; don't let the morning pick degrade to imputed output). |
| **A2.11** | Migrate EB posteriors from Python compute to dbt models | M | Removes the posterior-staleness fragility (`[[project_posterior_staleness_jun2026]]`) that silently corrupts serving when the Python compute scripts stall. **Now also owns the 30.6 residual:** `eb_starter_posteriors` is game_pk-keyed + written only for today's slate → starter-EB NULL for all +1/+2-day games (verified 2026-06-14). dbt as-of model keyed on `(pitcher_id, as-of)` closes it structurally — future game_pk inherits the starter's latest posterior. Bump priority toward Phase 1 (it's the durable half of the keystone, alongside 30.13). |

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
| **19.3** | ≥50 live CLV games | Backtest gate: confirm `qualified_bet` shows better CLV than unqualified before promoting it to the default view. |
| **12.4** | ≥50 | Bayesian sequential meta-model (CLV). |
| **12.5** | ≥100 + 12.4 converging | Meta-model integration into Epic 19. |
| **12.6** | ≥500 | Frequentist exploratory meta-model. |
| **12.9** | — | Wire Bayesian meta-model retraining into Dagster. |

⚠ **Gate these on Story 30.6 as well, not just the count** — a CLV meta-model trained on zero-skill live
predictions learns nothing. Don't start 12.4 until serving is fixed *and* the live count clears.

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

1. **Phase 0** (27.8 → 30.9 → v6 re-backfill) — cheap, closes the in-flight loop, consistent base-model semantics.
2. **30.12 + 31.0** (both cheap, read-only, parallelizable with Phase 0) → **Phase 1** (30.6 keystone + 30.8 + A2.11).
3. **Phase 2** (30.2 → 31.1 / 31.2 → 7.6 → 3A.3 / 5A.6 → Track B revisit).
4. Trigger the **gated 12.x / 19.3** track as live counts clear *and* 30.6 has landed.

**Alternative if maximizing live-skill-per-hour:** jump straight to **30.12 → 30.6** and return to 27.8/30.9
afterward. Phase 0's payoff is real but deferred until 30.6; 30.6 is the single highest-leverage item here.
