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
| **27.8** | Retrain home_win + run_diff on the normalized contract | M | Ready now (depends on 27.7 ✓). Bumps the pipeline to v6. **No correctness override** — must clear the gate's accuracy bars or be HELD. Watch the 2024 "normal-year tax". |
| **30.9** | Learned h2h ensemble (replace the hand-set 50/50 blend) | M | **Sequence AFTER 27.8** — learn the blend on the *retrained* base models, not the v5 ones, or the work is wasted. |
| *(op)* | Re-run the v6 prediction backfill | S | Machinery already built: `TARGET_ENV=prod predict_today --start … --is-backfill` (in-process range mode, idempotent per date+version). |

⚠ Live payoff of Phase 0 is **gated on Phase 1** — these improve the offline models, whose live skill stays
capped until point-in-time serving lands.

---

## Phase 1 — Make serving + eval honest *(the keystone — highest leverage on the list)*

| Story | What | Effort | Notes |
|---|---|---|---|
| **30.12** | Feature-store completeness audit & backfill-degradation policy | S/M | Specced 2026-06-13 (surfaced by the v5 backfill). Quantifies which features are sparse when → **directly feeds 30.6 + 30.8**. Can run in parallel with Phase 0. Known lead: `pythagorean_win_exp_diff` ~6.5% persistent mid-season null floor (`[[project_pythagorean_null_floor]]`). |
| **30.6** | ⭐ Point-in-time AS-OF feature snapshot + AS-OF retraining (the live-ceiling lift) | **L** | The keystone. Fixes the 0.42-offline-vs-0.001-live gap. Everything downstream's *live* value depends on this. |
| **30.8** | Pre-lineup and post-lineup prediction contracts | M | Tightly coupled to 30.6 (morning projected-lineup vs confirmed-lineup confidence tiers; don't let the morning pick degrade to imputed output). |
| **A2.11** | Migrate EB posteriors from Python compute to dbt models | M | Removes the posterior-staleness fragility (`[[project_posterior_staleness_jun2026]]`) that silently corrupts serving when the Python compute scripts stall. |

---

## Phase 2 — Sub-model & base-model quality *(Track B foundations)*

Do these **after** Phase 1 — sub-model gains only show up in production once serving is honest.

| Story | What | Effort | Notes |
|---|---|---|---|
| **30.2** | Wire sub-model distributional outputs into the base models (Bayesian-leverage audit) | M | The bridge into the Track B revisit. |
| **3A.3** | Park-type hierarchical prior | S | Run-environment sub-model. |
| **5A.6** | Continuous aging-curve EB prior | S | Starter sub-model (replaces age-band points with a continuous curve). |
| → | **Track B revisit** — all sub-models + the Layer 3 section | L | Strategic theme. Sequence it here: take the learnings (market-blindness, regime-normalization, serving parity) back to every sub-model and the Layer-3 blend. |

---

## Research / exploratory bucket *(opportunistic; low urgency)*

| Story | What | Effort | Notes |
|---|---|---|---|
| **27.9** | Exogenous run-environment leading indicators — ball-CoR scoping spike | S (spike) → ? | Promoted from 27.6 Task 4. The **causal** successor to 27.7's pragmatic season-norm fix: model the ball/run-environment driver directly via an exogenous *leading* signal (the one untried data class). It's a **scoping spike first** (inventory + orthogonality), cheap to start; only proceeds to modeling if a signal clears coverage + orthogonality, gated on the unchanged kill criterion. Payoff is downstream of serving honesty (30.6) and totals stays `bet_paused`, so it's genuinely low-urgency — do it when curiosity or a slow week allows, not on the critical path. |

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
2. **30.12** (parallelizable with Phase 0) → **Phase 1** (30.6 keystone + 30.8 + A2.11).
3. **Phase 2** (30.2 → 3A.3 / 5A.6 → Track B revisit).
4. Trigger the **gated 12.x / 19.3** track as live counts clear *and* 30.6 has landed.

**Alternative if maximizing live-skill-per-hour:** jump straight to **30.12 → 30.6** and return to 27.8/30.9
afterward. Phase 0's payoff is real but deferred until 30.6; 30.6 is the single highest-leverage item here.
