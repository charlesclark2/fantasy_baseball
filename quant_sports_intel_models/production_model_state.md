# Production model state — INDEX + cross-model reconciliation (PROD-STATE-1 umbrella)

_Written 2026-08-04 · docs-only stitch over the 7 shipped per-model sections (PROD-STATE-1a–1g, PRs #591 · #588 · #592 · #585 · #586 · #589 · #590) and the umbrella lessons (1)–(21) in `baseball/edge_program/story_prompts.md`. No serving, model, or dbt change. **`best_alpha = 0` is confirmed in every one of the 7 sections** — no edge, win-rate, or beat-the-market claim rides on any production model anywhere (Totals additionally carries `bet_paused = true`; NCAAF's α=0 is *measured*, not just declared: ATS 0.4961 ≈ placebo 0.4968, both under the 0.5238 breakeven)._

> **How to read this index:** each row states the model's **version authority** (lesson 2: name it first — it is never safe to assume the registry) and its **reconciliation verdict** from the six-verdict taxonomy below. "Docs say X, prod serves X" is only one of six honest outcomes; a flat match/mismatch dichotomy would misreport five of these seven models.

---

## 1. The reconciliation taxonomy — six verdicts, not "match/mismatch"

The seven audits produced **six distinct reconciliation verdicts**. Anyone extending this inventory (a new model, a re-audit) must classify into this taxonomy — the categories exist because a naive auditor would have misreported 1c as a mismatch, 1e as drift, and 1g as an outage.

| # | Verdict | Meaning | Models |
|---|---|---|---|
| 1 | ✅ **MATCH, live-verified** | Registry version == the served version stamp, read from live served rows (never quoted from the registry alone — lesson 1) | **1a Totals** (`v6`/`pre_lineup_v6` in BOTH `model_version` and `totals_model_version`, both tiers, 08-04) · **1b H2H** (`home_win` v6 `glm_elasticnet_deleaked`, both tiers) |
| 2 | **RECONCILED-BY-IDENTITY, version stamp ABSENT** | The served rows carry NO version column for this target, so direct reconciliation is impossible; reconciled by proxy instead — a **gap, not a mismatch** (lesson 20) | **1c Run Diff**: no `run_diff_model_version` column exists (`model_version` is home_win-only per lesson 9; `totals_model_version` is MH2.1's). Proxy proof: the consensus identity reproduces exactly on live rows (stored `layer4_h2h_conviction_disagree` == recomputed `\|calibrated_win_prob − Φ(loc/scale)\|` to 4 dp, 8/8 games 08-04) AND the S3 champion artifact mtimes (2026-06-23 20:07/20:11Z) match the registry's `promoted_at: 2026-06-23` |
| 3 | **DIFFERENCE-BY-DECISION** (not drift) | A registry-vs-served difference that is correct by a standing decision — confirm it and cite the decision; do NOT headline it as a mismatch (lesson 7) | **1e MiLB**: raw `mle_projections*` Delta tables stamp `v2_parkctx` while the served priors are v1-derived — v2 was adopted only where a head-to-head gate cleared, by ⛔ standing decision. (Same class, smaller: 1b's calibrator T 1.6441 deployed-refit vs 1.6953 hold-out-selection, lesson 11; 1g's shipped `strength_posterior` form vs the decided `gaussian` reference, swapped at finalize on a pre-registered early-season coverage floor, lesson 17) |
| 4 | **SERVED-ARTIFACT-STAMP only** | No registry entry AND no `daily_model_predictions` row — the version-of-record is the code constant + the stamp inside the served artifact itself, reconciled by reading the live payload (lessons 2, 12) | **1d K-props** (`strikeout_glm_v1` — code `MODEL_VERSION` + the S3 bundle path; no `sub_model_registry.yaml` entry) · **1f NFL fantasy** (`model_version="nfl_fantasy_nf1_5_v1"` in the live S3 api-cache payload + the bake-off JSONs read at build time) |
| 5 | **N/A — NOT-YET-SERVING** (not a mismatch) | There is no serving store / API / frontend / predictions row / registry entry, so there is nothing to disagree with; stating "N/A" is the honest verdict (lesson 15) | **1g NCAAF**: the ingest→mart→model pipeline would keep producing calibrated output into the S3 *research* lakehouse at season start untouched (P0.6c odds capture is ALREADY LIVE in prod since 2026-08-01), but **no user-facing surface exists or would appear** — P3.1 serving plumbing is the unbuilt keystone. **Model FROZEN ≠ product EXISTS.** |
| 6 | **RATIFIED-BUT-HELD / READY-unstarted** | A model win that cleared its gates but is deliberately not serving (a hold is a decision, not drift), plus its unblocking story | **NF-D16** (1f): rookie level recalibration, ratified but serving flip OFF (whole-board placement-clause veto — the ⚠️ brief correction of lesson 13: HELD is NF-D16 ONLY, not "D14/15/16"; NF-D14 = clean null, NF-D15 = underpowered-not-absent with scheduled re-runs TE 2028 / RB 2029). **NF-D21** is 🟢 READY/unstarted — the PM-judgment story that would flip it ON at a board-blind λ=0.5 shrink (live payload corroborates recal OFF: top rookie is a QB). |

---

## 2. One row per model

| Model | Section | Serving surface | Version authority (lesson 2) | Served version (live-read 08-04) | Reconciliation verdict | α |
|---|---|---|---|---|---|---|
| **1a MLB Totals** (PR #591) | [`production_model_state/mlb_totals.md`](production_model_state/mlb_totals.md) | `daily_model_predictions` → picks/EV surfaces; `P(over)` = raw `norm.sf` (NO serve-time calibrator, ECE ≈ 0.06) | `model_registry.yaml['total_runs']` — ⛔ NOT `sub_model_registry.yaml` (its `totals_generative_v1` is a DIFFERENT same-target model; naming the wrong registry names the wrong ARCHITECTURE, lesson 21) | v6 `ngboost_normal_deleaked` (`pre_lineup_v6` morning / `v6` post, in both version columns) | ✅ **MATCH live-verified** | 0 **+ `bet_paused=true`** |
| **1b MLB H2H** (PR #588) | [`production_model_state/mlb_h2h.md`](production_model_state/mlb_h2h.md) | `daily_model_predictions.calibrated_win_prob` — a 50/50 consensus (GLM leg + run-diff NGBoost leg) through T=1.6441 | `model_registry.yaml['home_win']` — `daily_model_predictions.model_version` is stamped from this key ONLY (lesson 9) | v6 `glm_elasticnet_deleaked` — the champion is the **GLM, not NGBoost** (lesson 10 brief correction) | ✅ **MATCH live-verified** — the closest-to-FINISHED game model (lesson 11: 3 model-side follow-ups; feature space EXHAUSTED) | 0 |
| **1c MLB Run Diff** (PR #592) | [`production_model_state/mlb_run_diff.md`](production_model_state/mlb_run_diff.md) | Non-user-facing: `Φ(μ/σ)` is 50% of the served H2H prob + CI bands + 28.6b monitor; no run-line market exists (never ingested, live-verified) | `model_registry.yaml['run_differential']` + S3 artifact — but **NO served stamp to reconcile against** | v6 `ngboost_normal_deleaked` — provable only by proxy (consensus identity 8/8 to 4 dp; artifact mtimes == `promoted_at`) | **RECONCILED-BY-IDENTITY, stamp ABSENT** (gap, not mismatch) | 0 |
| **1d K-props** (PR #585) | [`production_model_state/mlb_pitcher_k_props.md`](production_model_state/mlb_pitcher_k_props.md) | `/props` transparency surface (S3 + DynamoDB); `is_bet_recommendation: False` baked into every payload, guard-tested | Code `MODEL_VERSION` + the S3 bundle (carries its own `features` contract) — **NO registry entry** | `strikeout_glm_v1` (calib_80 0.8104), reconciled from the live payload | **SERVED-ARTIFACT-STAMP only** | 0 (E5.4 edge thesis = clean null) |
| **1e MiLB / prospect** (PR #586) | [`production_model_state/milb_prospect.md`](production_model_state/milb_prospect.md) | Priors serve inside `eb_batter_posteriors_raw`/`eb_starter_posteriors`; board = ADMIN-ONLY S3 JSON (public 2027) | **FOUR authorities** (one per sub-model; registry alone misstated 3 of 4, lesson 8) — `sub_model_registry.yaml` + code constants + Delta stamps + board `generated_at` | All four reconciled live (S3 reads 08-04); raw tables `v2_parkctx` vs served v1-derived priors | **DIFFERENCE-BY-DECISION** (not drift) | 0 (stamped in registry entries, board build, and served manifest framing) |
| **1f NFL fantasy** (PR #589) | [`production_model_state/nfl_season_fantasy.md`](production_model_state/nfl_season_fantasy.md) | Build-time static JSON → `s3://credence-prod-s3-api-cache/fantasy/nfl/2026/` (never request-time lakehouse); TWO stacked models — NF1.5 market-aware ORDERING over MVP-1 calibrated LEVELS (lesson 12) | The served artifact stamp + bake-off JSONs — **NO registry, NO `daily_model_predictions`** | `nfl_fantasy_nf1_5_v1` (`projection_source="nf1_5"`), reconciled via live payload | **SERVED-ARTIFACT-STAMP only**; + the program's only **RATIFIED-BUT-HELD** (NF-D16) and **READY-unstarted** (NF-D21) entries | 0 (projection product, not a market) |
| **1g NCAAF** (PR #590) | [`production_model_state/ncaaf.md`](production_model_state/ncaaf.md) | ⛔ **NONE** — no store / API / frontend / predictions row; pipeline outputs land in the S3 *research* lakehouse; odds capture IS live in prod (P0.6c) | **FIVE authorities, none the registry** (lesson 16): 4 committed artifact JSONs + the ablation memos; ⚠️ the P1.5 futures board has **NO version string at all** (provenance = a sidecar meta JSON only) | Frozen artifacts (`ncaaf_game_distribution_v1` et al.); σ calibration frozen 2026-07-23 | **N/A — NOT-YET-SERVING** (not a mismatch; "would serve untouched" = keeps producing into S3, NOT a product appearing) | 0 **measured** (ATS ≈ placebo, under breakeven; `assert_market_blind`-enforced) |

---

## 3. Two cross-model GOVERNANCE CLASSES (classes, not per-model bugs)

These recur across ≥3 models each and should be handled as classes. **Both pair with the open operator decision (2026-08-02) on adding a champion-promotion gate** — currently a registry merge to `main` IS the deploy with no gate between merge and serve (the MH2.1 landmine), which is exactly why absent stamps and absent monitors are load-bearing rather than cosmetic.

### Class A — VERSION-STAMP ABSENCE (a swap could be invisible in served data)

| Instance | Section | Shape |
|---|---|---|
| `run_diff_model_version` column **missing** | 1c | The only MLB game target with no served version column; a run-diff champion swap would move the served H2H prob + CI bands + reset the 28.6b window while being **invisible in served data**. The cheapest high-value fix in the whole inventory (MH2.1 already built the pattern for totals). |
| NCAAF P1.5 futures board — **no version string**; σ frozen with **no registry entry** | 1g | A published product artifact whose provenance is only a sidecar meta JSON (lesson 16). |
| K-props — **no registry entry** | 1d | Version-of-record is a code constant + bundle path; correct today, but nothing external to the code records what serves. |
| NFL fantasy — **artifact stamp only** | 1f | Same shape as 1d at family scale; the stamp + bake-off JSONs are the only record. |

### Class B — NO DRIFT / CALIBRATION MONITOR on a served (or would-serve) number

| Instance | Section | Shape |
|---|---|---|
| Served totals `P(over)` — ECE ≈ 0.06 (0.102 recent), systematic OVER lean, **no calibrator and no automated ECE monitor** | 1a | E13.6b Part B is the highest-value open totals item — and its frozen isotonic candidate is STALE (the 7/21 refresh flipped the method pick to temperature T≈1.53), so Part B must RE-SELECT at wire time. |
| K-props — the KP-V2.0 governance item (no calibration-drift monitor on the served distribution) | 1d | The class's namesake. |
| NCAAF — **μ refreshes but σ does NOT**: P1.4's `(σ₀,k,ρ,dof)` frozen 2026-07-23, no cadence / drift monitor / refit-rollback trigger | 1g | Lesson 18: a prerequisite before any P3 surface publishes these numbers. |
| (Sibling, cadence rather than calibration) no scheduled champion retrain: H2H **E1.10** (carded, open) and its **uncarded totals sibling** (42d since fit at audit) | 1b · 1a | See spin-out §4.3. |

---

## 4. SPIN-OUT CANDIDATES (named + owning surface; deliberately NOT scoped here)

1. **E2.7 `totals_distribution` / `totals_perside_mu_v1` null — owner: the PROD-STATE-1a totals serving surface.** Confirmed independently by **1a AND 1c** (three-cornered per lesson 21a): the served game-detail blob's `totals_distribution` block (which also carries run-diff Producer B's margin density + `p_home` panel) is `null` in every sampled blob across 5 dates. The **current-slate half is explained** (the per-side consumer parquet is rebuilt one build cycle BEFORE the predict that reads it — 1a measured 12:54Z vs 13:00Z, 0/15 coverage vs 100% every prior slate) — the **historical nulls are NOT explained** (an intermittent per-side μ collapse to ~1.5 runs/side is correctly suppressed by the plausibility guard, plus an unidentified WARN-tier degrade on healthy-μ slates). **Operator-verifiable in the box `write_serving_store` step log** (`_PERSIDE_MU_BATCH` / `_load_totals_dist_params` WARN lines). Cosmetic today (WARN-tier, α=0, served pick unaffected) but it blanks a shipped transparency panel.
2. **`MIN_SPREAD_RUNDIFF = 0.50` flat-output floor recalibration — owner: `check_served_prediction_integrity_op` / serving guards (1c).** The floor is v5-calibrated (374-feature dense model); the 13/124-feature v6 models are structurally narrower — morning-tier `stddev(pred_run_diff_loc)` < 0.50 on 8/33 slates since promotion (min 0.157) ⇒ chronic false-positive risk on a guard that **E11.30 pages CRITICAL on**. Precedent: INC-17-P3 (**recalibrate the FLOOR, don't touch the model**). ⚠️ reconstructed from served rows — verify against the op's step log first.
3. **Totals retrain cadence — owner: model ops (1a), sibling of H2H's carded E1.10.** The totals champion has no scheduled retrain (42d since fit at audit) and no card; E1.10 exists for H2H only.
4. **Cross-model version-stamp governance story — owner: serving schema + registry (Class A above).** One story that closes the class: add `run_diff_model_version` (the MH2.1 pattern), give the NCAAF P1.5 board a version string, and decide the registry-entry question for K-props/NFL — as a companion to the open no-promotion-gate decision rather than four one-off patches.

---

## 5. Operator one-liner

`betting_ml/models/model_registry.yaml` → `total_runs` → `served_live_rows: "VERIFY"` can be updated to **15** — the MH2.1 live rollback window is exactly 15 live-served rows (2026-08-02 post_lineup, written 19:42:47→19:48:30Z); the other 1,362 `mh2_1` rows are `prediction_type='backfill'` re-scorings, and `totals_model_version` is NULL before 08-02 (pre-08-02 totals reconciliation must use the registry). Measured in [`mlb_totals.md`](production_model_state/mlb_totals.md) §field-7.

---

## Sections (all 7, shipped 2026-08-04)

- [MLB Totals — PROD-STATE-1a](production_model_state/mlb_totals.md) (PR #591)
- [MLB H2H — PROD-STATE-1b](production_model_state/mlb_h2h.md) (PR #588)
- [MLB Run Diff — PROD-STATE-1c](production_model_state/mlb_run_diff.md) (PR #592)
- [MLB Pitcher K-Props — PROD-STATE-1d](production_model_state/mlb_pitcher_k_props.md) (PR #585)
- [MiLB / Prospect family — PROD-STATE-1e](production_model_state/milb_prospect.md) (PR #586)
- [NFL Season Fantasy — PROD-STATE-1f](production_model_state/nfl_season_fantasy.md) (PR #589)
- [NCAAF game + futures — PROD-STATE-1g](production_model_state/ncaaf.md) (PR #590)

_Reconciliation ground truth: umbrella lessons (1)–(21) in `quant_sports_intel_models/baseball/edge_program/story_prompts.md` (PROD-STATE-1 block). Per-task memory notes exist for 1a–1g; this index stitches, it does not re-derive — ⛔ do not re-open a per-model dig from here; open a spin-out story instead._
