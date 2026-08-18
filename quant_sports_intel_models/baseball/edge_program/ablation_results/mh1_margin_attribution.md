# MH1 — margin attribution across the shared bake-off harness

> ⚠️ **Not an edge claim.** `best_alpha = 0`. MH1 changes no model, no feature, no gate and no verdict — it changes what a report is allowed to CLAIM a margin means.

## What the defect was

A `(contract variant × learner class)` bake-off reports one headline number, `margin = incumbent_arm − leader_arm`. That is the right PROMOTION question and is unchanged here. It is the wrong number to attribute to a FEATURE study, because a leader that also swapped its learner class carries both effects in one figure.

E7.9 measured this on itself (54–77% of its margins were the learner swap) and fixed it locally. MH1's finding is that the defect is GENERIC: `model_bakeoff.py` has the same arm shape and the same leader-vs-incumbent comparison — but SPREAD ACROSS A PAIR OF RUNS (a `--contract` variant run beside the tier-default run), so the comparison a reader makes was made BY EYE, across two reports, with nothing holding the learner fixed. Strictly more exposed than E7.9 was: there, at least one number was computed; here, none was.

## What shipped

- `betting_ml/utils/margin_attribution.py` — the ONE owner of the decomposition and its markdown block (pure, IO-free, fast-gate safe). E7.9 now DELEGATES to it; its local implementation is gone, verified byte-identical on all three recorded results first.
- `model_bakeoff.py` emits the block on EVERY report — including the runs where the decomposition cannot act, which carry a NAMED reason. Silence and "checked, came back clean" must not look the same (NF1.7 (a)).
- `--rewrite-reports` / `mh1_margin_attribution.py --rewrite-all` re-emit every recorded report FROM STORED ARM JSON. **⛔ Not one model was fitted.**

## Two readings the raw share cannot give you

**1 — A SIGN FLIP.** `learner_share > 1` means the CONTRACT component points the OPPOSITE way to the headline: holding the learner fixed, the "winning" contract LOST. That is not over-crediting, it is the wrong DIRECTION, and it is flagged separately.

**2 — A SUB-NOISE DENOMINATOR.** A share is a RATIO, and a ratio whose denominator sits inside the metric's own noise floor is noise amplification, not a proportion. The number is still computed (the recorded values did not move) but the report refuses to headline a percentage it cannot support. ⚠️ **This applies to E7.9's own quoted figures: two of its three margins (0.0053 and 0.0127 crps against a 0.02 floor) are sub-noise, so its "54%" and "77%" are shares of a denominator the gate itself calls noise.** The ABSOLUTE contract components (+0.0059 / +0.0012 / +0.0053) are unaffected and are what should be quoted.

## Every affected result

| result | harness | metric | total | learner swap | contract | share | reading |
|---|---|---|---:|---:|---:|---:|---|
| `bakeoff_home_win_post_lineup` | model_bakeoff | brier | — | — | — | — | _inactive — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute_ |
| `bakeoff_home_win_post_lineup_home_win_post_reprune_glm` | model_bakeoff | brier | +0.0029 | +0.0020 | +0.0009 | 68% | 🚩 majority of the margin is the LEARNER SWAP |
| `bakeoff_home_win_pre_lineup` | model_bakeoff | brier | — | — | — | — | _inactive — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute_ |
| `bakeoff_home_win_pre_lineup_pre_lineup_home_win_reprune_glm` | model_bakeoff | brier | +0.0023 | +0.0003 | +0.0021 | 11% | contract-dominated ✅ |
| `bakeoff_run_diff_post_lineup` | model_bakeoff | crps | — | — | — | — | _inactive — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute_ |
| `bakeoff_run_diff_pre_lineup` | model_bakeoff | crps | — | — | — | — | _inactive — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute_ |
| `bakeoff_total_runs_post_lineup` | model_bakeoff | crps | — | — | — | — | _inactive — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute_ |
| `bakeoff_total_runs_pre_lineup` | model_bakeoff | crps | — | — | — | — | _inactive — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute_ |
| `bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb` | model_bakeoff | crps | +0.0007 | +0.0037 | -0.0029 | (507%) sub-noise | 🚩🚩 **SIGN FLIP** — the contract is WORSE holding the learner fixed |
| `e7_9_retrain_run_diff_post_lineup` | e7_9 | crps | +0.0127 | +0.0068 | +0.0059 | (53%) sub-noise | 🚩 majority of the margin is the LEARNER SWAP |
| `e7_9_retrain_run_diff_pre_lineup` | e7_9 | crps | +0.0053 | +0.0041 | +0.0012 | (77%) sub-noise | 🚩 majority of the margin is the LEARNER SWAP |
| `e7_9_retrain_total_runs_post_lineup` | e7_9 | crps | +0.0206 | +0.0153 | +0.0053 | 74% | 🚩 majority of the margin is the LEARNER SWAP |

Active decompositions: **6 of 12**. The rest are single-contract runs with no contract axis — an inactive check is NOT a passed one (NF-D20), which is why the count is stated rather than implied.

## The finding

**`total_runs / pre_lineup` is a SIGN FLIP.** The 14-column re-pruned contract shows a `+0.0007` crps margin over the 87-column incumbent — but holding the learner fixed it is `-0.0029` WORSE, and it is worse for all four of the most competitive learners (`ngboost_normal` −0.0029, `ngboost_lognormal` −0.0009, `glm_elasticnet` −0.0184, `catboost` −0.0102); it wins only on the three weakest. The entire apparent margin, and more, is the `glm_elasticnet → ngboost_normal` swap. ⚠️ Every one of these quantities is inside the 0.02 crps noise floor, so the honest statement is **"this pair of runs is evidence for nothing"** — which is a materially different record from "the re-pruned contract won".

`home_win / post_lineup` is 68% learner swap (the contract bought +0.0009 of a +0.0029 margin, against a 0.002 brier floor). `home_win / pre_lineup` is only 11% learner — a genuine contract effect. **The instrument exonerates as well as accuses**, which is what makes it worth reading.

## Where the decomposition is structurally INACTIVE (and why that is a finding)

Checked, so a future session does not chase a non-defect:

- **NCAAF P1.4** (`bakeoff_ncaaf_game.py`) has a literal `learner × contract × form` grid and IS the same arm shape — but its verdict is `REFERENCE_STANDS` with `winner=None` and `gain_vs_reference=0.0`, so there is no promoted margin to mis-attribute. It becomes affected the moment a winner is promoted.
- **NFL fantasy** (`run_nf_w*_bakeoff.py`) arms are mechanism/form arms on a FIXED feature set — no contract axis, so no learner-vs-contract confound exists to split.
- **`h_harness.py`** (MiLB/prospect, E7.12/E7.15/MH2.x) arms are hypothesis arms against a shared foil — same reason.

All three can adopt the shared owner by calling it; none needed a report change now. The shared function takes `lower_is_better=` precisely so a higher-is-better vertical cannot adopt it and get every sign silently backwards.

## Verdict safety

Attribution is PRESENTATIONAL. A decomposition that would move a verdict is a bug, not a feature — so the proof is a fingerprint of every decision field of all 12 affected results, captured at the PRE-MH1 commit (`betting_ml/tests/fixtures/mh1_verdict_baseline.json`, read out of git blobs, never the working tree) and asserted by `test_mh1_margin_attribution.py::test_no_verdict_gate_or_selection_moved_across_the_whole_migration`. The fingerprint hashes EVERY field except the attribution block, so a field added to the harness later is covered without editing the guard.

Result: **no verdict, gate, winner, tie-break, PBO or margin moved.** 20 guards, all 14 declared breaks RED-proved (`betting_ml/tests/mh1_red_proof.py`).

## Reproduce

```bash
# LAPTOP — re-emit every affected report from stored arm JSON (no fitting, ~2s)
uv run python betting_ml/scripts/mh1_margin_attribution.py --rewrite-all --check
uv run python betting_ml/tests/mh1_red_proof.py
```
