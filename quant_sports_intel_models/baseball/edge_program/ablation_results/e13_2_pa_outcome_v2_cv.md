# E13.2 Phase 1 — PA-outcome multiclass CV — feature set v2 (2026-06-24)

- Substrate: 1,960,682 R-season PAs, 65 features (5 categorical + 8 entering-state + 52 point-in-time).
- No-skill marginal-prior floor (Phase 0): 1.5074 nats. nll noise floor: 0.01.

## CV mean multiclass log-loss (lower = better)
- **model**:    1.4838
- log5 prior:   1.4881  (Δ model +0.0043)
- marginal:     1.5094  (Δ model +0.0256)

**GATE FAIL — model beats log5 by only +0.0043 nats (< 0.01 noise floor): the proven split signal does NOT lift PA-outcome prediction over log5 on our data → log5 is near-optimal here. Next decision is B (sim for product/distribution value only) vs C (pause).**
(beats log5 all folds: True; beats marginal all folds: True)

## Per-class calibration (ECE, pooled held-out — lower = better)
- mean ECE: 0.0026
  1B 0.0033 · 2B 0.0004 · 3B 0.0007 · HR 0.0008 · BB 0.0033 · IBB 0.0001 · HBP 0.0003 · K 0.0069 · out 0.0094 · other 0.0012

## Pre-registered regime split @ 2023 (2023 rule changes)
Δ vs log5 (game-clustered block bootstrap, 95% CI). Decision rule fixed before the result: a real regime-specific edge requires the 2023+ lift to clear the noise floor with a CI excluding both 0 and the pre-2023 estimate.
- pre-2023 : +0.0029  [+0.0024, +0.0035]  (768,868 PA, 10,203 games)
- 2023+    : +0.0066  [+0.0060, +0.0071]  (548,586 PA, 7,289 games)
- **Regime verdict:** NULL — 2023+ lift does not clear the floor with a clean CI → log5 near-optimal; no rule-change edge → proceed to C (pause, preserve the calibrated PA asset)**

## Phase 1 decision dossier — DECISION C (pause, preserve asset)

**Finding (airtight null).** A leak-safe, EB-shrunk, split-aware LightGBM multiclass PA-outcome
model has **real, calibrated skill over the no-skill marginal** (−0.0256 nats, well above the 0.01
floor; per-class ECE 0.0026) but does **not beat the log5 matchup baseline** above the noise floor
— **+0.0043 nats full-history, +0.0066 post-2023, both below 0.01.** The pre-registered regime
split at the 2023 rule-change boundary was the last principled test: the 2023+ lift is real (CI
[+0.0060, +0.0071] excludes 0 and is growing by season) but **fails the floor** — it is too small
to be cashable in a derivative/soft market after vig. log5 (Bill-James `p_c ∝ bat_c·pit_c/league_c`)
is **near-optimal** for combining batter and pitcher identity at the PA grain on our data; the GBM's
context/split features add only a noise-floor sliver on top of the batter×pitcher EB priors
(feature importance: PIT priors 86%, context 14%, platoon/TTO ≈0 conditional). This is consistent
with the program's broader read ([[project_e13_8_market_benchmark]], [[project_edge_program_e13_4_status]]):
the edge is not in a better point model; value is product-quality calibration + transparency.

**Decision: C.** No further feature-chasing (splits were the principled shot, per the pre-registered
"do not keep adding features" rule). Specifically:
- **PAUSE** the heavy Phase 2 Monte-Carlo game sim. It is cost-gated and the product/app track is
  parked; do not build it on product-only grounds now. Reopen only when the product track reopens
  or a genuinely new signal axis lands (E13.10 zone-matchup is the natural candidate).
- **PRESERVE** `pa_outcome_v2.pkl` (ECE 0.0026, on `s3://baseball-betting-ml-artifacts/sub_models/`)
  as a **logged research asset** — NOT promoted to the serving registry. It is the calibrated
  foundation a future product-sim would chain through base-out-score transitions, and the natural
  consumer of E13.10 zone-matchup output.

**Honest framing reminder:** this asset is sim-trustworthy (calibration) but carries **no market
edge** (`best_alpha = 0`); any future product use must not be framed as a win-rate/edge claim.

## Per-fold
| eval | n_train | n_eval | model | log5 | marginal | Δ vs log5 |
|---|---|---|---|---|---|---|
| 2018 | 521,977 | 153,223 | 1.4811 | 1.4831 | 1.5057 | +0.0020 |
| 2019 | 676,965 | 186,025 | 1.4982 | 1.4997 | 1.5258 | +0.0015 |
| 2020 | 861,326 | 66,400 | 1.5062 | 1.5093 | 1.5305 | +0.0031 |
| 2021 | 927,274 | 181,348 | 1.4841 | 1.4882 | 1.5123 | +0.0041 |
| 2022 | 1,109,691 | 181,872 | 1.4691 | 1.4730 | 1.4931 | +0.0040 |
| 2023 | 1,291,471 | 183,773 | 1.4902 | 1.4949 | 1.5151 | +0.0047 |
| 2024 | 1,475,142 | 182,175 | 1.4712 | 1.4784 | 1.4965 | +0.0072 |
| 2025 | 1,659,366 | 182,638 | 1.4702 | 1.4780 | 1.4963 | +0.0078 |