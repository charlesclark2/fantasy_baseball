# NF-W6b-C — RB rushing_tds fresh-family successor (§0.5 bake-off; PM Decision C)

**Generated:** 2026-08-15T07:18:18+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cell:** RB|rushing_tds (one)

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). ⭐ FRESH registration (MH2.2/E2.1-r): a NEW field, seed 20260816 — ⛔ not a re-score and not a trim of NF-W6b's field; the W6b record stands. The declared family is coherent and atom-aware ONLY (⛔ no linear-residual arm — the W6b field-inflating class is excluded up front on mechanistic grounds). Coverage is a one-sided FLOOR (NF1.9 (e)); the two-sidedness lives in the sharpness degenerates. Verdict words are three-way and derived, failing closed to TIES (NF-W2e).

> 🟥 **Runtime gate: N/A, stated** — no serving path is touched (no `--publish`, no `deploy.sh`, no Dagster op, no S3/registry/dbt write); local artifacts read by governance only. **Serving:** RB|rushing_tds stays guard-pinned OUT of NF-W6c's dispatch (`WITHHELD_NULL_CELLS`) regardless of this verdict; a SHIP licenses a future wiring story under NF-G0, it does not execute one.

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped.

## Verdict: **RB-RUSHTD-FRESH SHIP**

- `knn_quantile` BEATS `inc_climatology` by +0.0194 CRPS (CI95 [+0.0169, +0.0219] excludes zero)
- lift 12.966% of foil CRPS · fold wins 8/8 (required 6) · p 0.0 · PBO 0.0 · **DSR 1.0** · cov80 0.9537 (floor 0.8, one-sided)

## The DSR mechanism, W6b → W6b-C (the reason this field exists)

- NF-W6b (the retired field): winner `knn_quantile` Δ 0.0194 (12.966%), per-fold Sharpe 6.474, **DSR 0.2131** — refused because `enet_residual` (trial Sharpe -9.199) inflated the field's dispersion to sr0 ≈ 7.32.
- THIS field (fresh, coherent, atom-aware): trial Sharpes [3.758, 6.474, 3.795] → **sr0 1.3281** vs the winner's observed Sharpe 6.474 → **DSR 1.0**. ⛔ This is NOT a trim of the W6b field (MH2.2) — it is a fresh registration whose family excludes the incoherent class on mechanistic grounds, declared before scoring.

## Leaderboard (mean CRPS over folds; anchors indented — never trials)

| label            |   mean_crps |
|:-----------------|------------:|
| knn_quantile     |     0.13023 |
| count_negbin     |     0.13312 |
| lgbm_hurdle_tail |     0.13340 |
| oracle_knn       |     0.13608 |
| matched_knn      |     0.13701 |
| matched_negbin   |     0.13941 |
| oracle_negbin    |     0.13943 |
| oracle_marginal  |     0.14949 |
| inc_climatology  |     0.14964 |
| permuted_knn     |     0.14965 |
| matched_marginal |     0.14969 |
| matched_hurdle   |     0.15583 |
| oracle_hurdle    |     0.15630 |
| nihilist_zero    |     0.16898 |
| zero_width       |     0.16898 |
| max_width        |     0.18005 |

- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs (NF-D16 (g‴) — winner's own form `knn_quantile` gates; others reported): {"marginal": {"oracle_crps": 0.14949, "matched_crps": 0.14969, "oracle_beats_matched": true}, "knn_quantile": {"oracle_crps": 0.13608, "matched_crps": 0.13701, "oracle_beats_matched": true}, "lgbm_hurdle_tail": {"oracle_crps": 0.1563, "matched_crps": 0.15583, "oracle_beats_matched": false}, "count_negbin": {"oracle_crps": 0.13943, "matched_crps": 0.13941, "oracle_beats_matched": false}}
- coverage: {"winner_coverage_80": 0.9537, "binding_foil_coverage_80": 0.9738, "structural_expectation": 0.9861, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.8607, "winner_pred_p0": 0.8719, "binding_foil_pred_p0": 0.8693, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.01809 vs legacy Δ 0.01984
- PBO companions (NF1.8): os_gap 0.0% · contender spread 14.9% · flips [{"config": "knn_quantile", "IS-half wins": 70, "share": 1.0, "full-sample IS80": 0.13, "\u0394 vs best %": 0.0}]
- fdr (single-cell family, m=1 ⇒ cutoff = q): {"family": ["RB|rushing_tds"], "m": 1, "binding_cutoff": 0.1, "pass": true}
- points-units note: {"points_units": 0.1164, "note": "REPORT-ONLY \u2014 winner-vs-foil CRPS lift \u00d7 the 6.0 PPR rushing-TD weight; a MARGINAL contribution in points units, NOT an assembled-points claim."}

## Pre-registration

- cell: ['RB|rushing_tds'] (⛔ closed TD-NO cells stay closed: ['QB|rushing_tds', 'RB|receiving_tds', 'WR|receiving_tds', 'TE|receiving_tds']); arms: ['lgbm_hurdle_tail', 'knn_quantile', 'count_negbin'] (declared_field_size=3); banned classes: ['enet_residual', 'inc_head_bank']; foil: ['inc_climatology']; anchors: ['nihilist_zero', 'zero_width', 'max_width', 'permuted_knn', 'oracle_marginal', 'matched_marginal', 'oracle_knn', 'matched_knn', 'oracle_hurdle', 'matched_hurdle', 'oracle_negbin', 'matched_negbin'].
- gates: paired lift vs foil ∧ `fold_consistency_clause(8)` ∧ PBO<0.2 over the eligible field ∧ DSR≥0.95 ∧ single-cell BH (p ≤ 0.1) ∧ coverage floor (one-sided) ∧ degenerates lose ∧ permutation behaves ∧ not_a_foil_tie (eps 0.0001) ∧ winner_own_form_floor. Fails closed.
- null classification: CONSTRAINT_REFUSED by hand (the cv_power gap); statistical nulls via `cv_power.classify_null(declared_field_size=3, degenerates_excluded_from_v=True)`; the record reads `field_remedy_admissible`, never the prose (MH2.7; guide §0.5.4 rules 5/5b).

_Runtime: 545.7s · seed 20260816 · matrix cache key 57c4cf96bb3c3570_
## Post-run reading (hand note, 2026-08-15 — the derived record above is the authority)

- **The mechanism was the field, not the effect.** The winner is byte-identical to NF-W6b's (same pinned `SD.arm_knn_quantile` code path: Δ +0.0194, per-fold Sharpe 6.474 both reproduce exactly). What changed is the deflation bar: trial Sharpes [3.76, 6.47, 3.80] in a coherent atom-aware family give sr0 1.33 (W6b's field: ≈7.32 with `enet_residual` at −9.2 in it) ⇒ DSR 0.2131 → 1.0. This is the MH2/DSR-CONV "a deflation statistic over a field containing a designed loser measures the loser" lesson, resolved the admissible way (a fresh mechanistic registration), not by trimming.
- **Selection is unambiguous:** flip mass 70/70 on `knn_quantile` (PBO 0.0, os-gap 0.0%); the two other atom-aware arms tie each other (`count_negbin` 0.13312 vs `lgbm_hurdle_tail` 0.13340) ~2% behind. NB2 dispersion α at RB sits 0.12–0.50 across folds — genuinely over-dispersed, never at the Poisson floor.
- **Per-form pairs (NF-D16 g‴):** the kNN pair (the winner's own) and the marginal pair pass; the winner beats its own block peek (0.13023 < 0.13608) — legitimate capacity at unmatched n, admissible because the matched control sits above the peek. The hurdle and NB2 pairs do NOT pass (block-size fits are capacity-saturated: 0.1563 vs 0.15583, 0.13943 vs 0.13941) — REPORTED; neither is the winner's form, so neither gates.
- **Atom priced:** real P(0) 0.8607, winner pred 0.8719 (foil 0.8693). Coverage 0.9537 vs structural expectation 0.9861 (one-sided floor 0.80). Era: capture Δ +0.0181 vs legacy +0.0198 (quote the capture era forward). Points-units: ≈0.116 pts/wk (REPORT-ONLY).
- **What this licenses:** RB|rushing_tds `knn_quantile` is now a certified construction that MAY join NF-W6c's dispatch-only serving wiring as a follow-on story under NF-G0. ⛔ It does not move today: `stat_distribution_serving.WITHHELD_NULL_CELLS` still holds the cell (guard-pinned), and moving it is a separate wiring PR (add the cell to `SERVED_CELLS` → `SD.arm_knn_quantile`, remove it from `WITHHELD_NULL_CELLS`, re-run the W6c stage/serve path). Deploy-held; `best_alpha` N/A.
