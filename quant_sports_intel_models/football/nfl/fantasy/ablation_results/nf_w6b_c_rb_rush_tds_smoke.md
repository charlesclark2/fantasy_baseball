# NF-W6b-C — RB rushing_tds fresh-family successor (§0.5 bake-off; PM Decision C)

**Generated:** 2026-08-15T07:01:33+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cell:** RB|rushing_tds (one)

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). ⭐ FRESH registration (MH2.2/E2.1-r): a NEW field, seed 20260816 — ⛔ not a re-score and not a trim of NF-W6b's field; the W6b record stands. The declared family is coherent and atom-aware ONLY (⛔ no linear-residual arm — the W6b field-inflating class is excluded up front on mechanistic grounds). Coverage is a one-sided FLOOR (NF1.9 (e)); the two-sidedness lives in the sharpness degenerates. Verdict words are three-way and derived, failing closed to TIES (NF-W2e).

> 🟥 **Runtime gate: N/A, stated** — no serving path is touched (no `--publish`, no `deploy.sh`, no Dagster op, no S3/registry/dbt write); local artifacts read by governance only. **Serving:** RB|rushing_tds stays guard-pinned OUT of NF-W6c's dispatch (`WITHHELD_NULL_CELLS`) regardless of this verdict; a SHIP licenses a future wiring story under NF-G0, it does not execute one.

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped.

## Verdict: **RB-RUSHTD-FRESH UNDEFINED**

- `knn_quantile` TIES `inc_climatology` by +0.0181 CRPS (interval unevaluable)
- lift 11.474% of foil CRPS · fold wins 2/2 (required None) · p None · PBO None · **DSR None** · cov80 0.9473 (floor 0.8, one-sided)

## The DSR mechanism, W6b → W6b-C (the reason this field exists)

- NF-W6b (the retired field): winner `knn_quantile` Δ 0.0194 (12.966%), per-fold Sharpe 6.474, **DSR 0.2131** — refused because `enet_residual` (trial Sharpe -9.199) inflated the field's dispersion to sr0 ≈ 7.32.
- THIS field (fresh, coherent, atom-aware): trial Sharpes [4.136, 8.543, 2.142] → **sr0 2.7936** vs the winner's observed Sharpe 8.543 → **DSR None**. ⛔ This is NOT a trim of the W6b field (MH2.2) — it is a fresh registration whose family excludes the incoherent class on mechanistic grounds, declared before scoring.

## Leaderboard (mean CRPS over folds; anchors indented — never trials)

| label            |   mean_crps |
|:-----------------|------------:|
| knn_quantile     |     0.13955 |
| count_negbin     |     0.14190 |
| lgbm_hurdle_tail |     0.14222 |
| oracle_knn       |     0.14419 |
| matched_knn      |     0.14521 |
| oracle_negbin    |     0.14842 |
| matched_negbin   |     0.14919 |
| oracle_marginal  |     0.15746 |
| inc_climatology  |     0.15764 |
| matched_marginal |     0.15786 |
| permuted_knn     |     0.15860 |
| matched_hurdle   |     0.16694 |
| oracle_hurdle    |     0.16763 |
| nihilist_zero    |     0.17809 |
| zero_width       |     0.17809 |
| max_width        |     0.18683 |

- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs (NF-D16 (g‴) — winner's own form `knn_quantile` gates; others reported): {"marginal": {"oracle_crps": 0.15746, "matched_crps": 0.15786, "oracle_beats_matched": true}, "knn_quantile": {"oracle_crps": 0.14419, "matched_crps": 0.14521, "oracle_beats_matched": true}, "lgbm_hurdle_tail": {"oracle_crps": 0.16763, "matched_crps": 0.16694, "oracle_beats_matched": false}, "count_negbin": {"oracle_crps": 0.14842, "matched_crps": 0.14919, "oracle_beats_matched": true}}
- coverage: {"winner_coverage_80": 0.9473, "binding_foil_coverage_80": 0.9688, "structural_expectation": 0.9857, "n_rows": 2144, "binomial_se": 0.0086, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.8573, "winner_pred_p0": 0.8693, "binding_foil_pred_p0": 0.8693, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.01809 vs legacy Δ None
- PBO companions (NF1.8): os_gap None% · contender spread None% · flips []
- fdr (single-cell family, m=1 ⇒ cutoff = q): {"family": ["RB|rushing_tds"], "m": 1, "binding_cutoff": 0.1, "pass": false}
- points-units note: {"points_units": 0.1085, "note": "REPORT-ONLY \u2014 winner-vs-foil CRPS lift \u00d7 the 6.0 PPR rushing-TD weight; a MARGINAL contribution in points units, NOT an assembled-points claim."}

## Null state (recorded)

```json
{
  "state": "UNDEFINED",
  "reason": "`crps_q199|RB|rushing_tds`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
  "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons",
  "folds_have": 2,
  "folds_needed": 4,
  "extra_seasons": 2,
  "max_field_size": null,
  "detail": {
    "n_folds": 2,
    "n_arms": 3
  },
  "field_remedy_admissible": null,
  "failing_checks": [
    "fold_consistency",
    "pbo_ok",
    "dsr_ok",
    "fdr_ok"
  ],
  "classifier": "cv_power.classify_null (declared_field_size stated \u2014 MH2.7; read field_remedy_admissible, never the prose)"
}
```

- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

## Pre-registration

- cell: ['RB|rushing_tds'] (⛔ closed TD-NO cells stay closed: ['QB|rushing_tds', 'RB|receiving_tds', 'WR|receiving_tds', 'TE|receiving_tds']); arms: ['lgbm_hurdle_tail', 'knn_quantile', 'count_negbin'] (declared_field_size=3); banned classes: ['enet_residual', 'inc_head_bank']; foil: ['inc_climatology']; anchors: ['nihilist_zero', 'zero_width', 'max_width', 'permuted_knn', 'oracle_marginal', 'matched_marginal', 'oracle_knn', 'matched_knn', 'oracle_hurdle', 'matched_hurdle', 'oracle_negbin', 'matched_negbin'].
- gates: paired lift vs foil ∧ `fold_consistency_clause(2)` ∧ PBO<0.2 over the eligible field ∧ DSR≥0.95 ∧ single-cell BH (p ≤ 0.1) ∧ coverage floor (one-sided) ∧ degenerates lose ∧ permutation behaves ∧ not_a_foil_tie (eps 0.0001) ∧ winner_own_form_floor. Fails closed.
- null classification: CONSTRAINT_REFUSED by hand (the cv_power gap); statistical nulls via `cv_power.classify_null(declared_field_size=3, degenerates_excluded_from_v=True)`; the record reads `field_remedy_admissible`, never the prose (MH2.7; guide §0.5.4 rules 5/5b).

_Runtime: 147.9s · seed 20260816 · matrix cache key 57c4cf96bb3c3570_