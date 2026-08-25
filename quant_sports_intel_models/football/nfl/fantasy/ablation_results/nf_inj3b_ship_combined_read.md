# NF-INJ3b-SHIP node 5 — the D10 COMBINED READ

_generated 2026-08-25T03:21:53.847277+00:00_ · `best_alpha = 0` · **DEPLOY-HELD, nothing published**

## Verdict: **PASS**

a per-story read cannot attribute a board that moved for two reasons. The board that publishes carries this flip PLUS whatever else is live, so there is ONE read on the ONE board — and it binds to that board, not to a date.

## 1. The board this read is valid FOR

⭐ THE BOARD, NOT THE DATE. If `reported_absence_count` changes (NF-INJ-NEWS-1 overrides adopted or withdrawn), or `n_rookie_rows` changes (the roster cutdown), or `injury_games_policy` changes, the board that would publish is no longer the board this read covers and the combined read must be RE-RUN before it ships.

| component | value |
|---|---|
| season | 2026 |
| projection lineage | `nf1_5` |
| board rows | 868 (81 rookie) |
| injury-games cap | `fitted_hurdle` / `nfl_fantasy_nf_inj3b_injury_games_v1` |
| adopted reported-absence overrides | **0** |
| rookie policy | `None` |
| veteran level | `recalibrated` |

## 2. Placement — whole-board, cross-position, on the PUBLISH CANDIDATE

**SANE** · gates `{'band_integrity': 'PASS', 'within_position_order': 'PASS', 'rookie_placement_cap': 'PASS', 'position_survival': 'PASS'}`

Read from `local-dir:/tmp/nf_inj3b_ship_stage/2026` (local-dir); configs read: 14, absent: none.

⚠️ This is NOT the S3 baseline the NF-INJ3b ship path ran. That one reads the board as currently PUBLISHED and structurally cannot see a change that has not shipped; this one reads the board that WOULD ship.

## 3. Interval re-validation

**✅ ALL FLOORS MET** (exit 0). a floor breach is a RE-SELECTION trigger for that population, never a reason to move the floor (E2.1-r / NF1.8 §1)

| population | form | n | pooled coverage |
|---|---|---|---|
| rookies | qreg_sqrt | 553 | 0.83 |
| veterans | knn_norm | 8398 | 0.8897 |
| kdst | empirical_ratio_band | 795 | 0.8566 |

Written to `nf_inj3b_ship_combined_read_interval_revalidation.json` via this story's own `--out` stem. Decided artifacts verified byte-identical across BOTH legs: `{'nf_tr2b_placement_read.json': True, 'nf1_9_interval_revalidation.json': True}`.

## 4. What is still the OPERATOR's

The ship/hold call. This read gates the first publish; it does not take it. Nothing here wrote to S3 and this runner has no `--publish` flag.
