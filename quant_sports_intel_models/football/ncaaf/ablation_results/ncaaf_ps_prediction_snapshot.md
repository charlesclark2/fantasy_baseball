# NCAAF-PS — pre-kickoff game-prediction snapshots

_Last run: 2026-08-18T03:41:21.000Z (UTC)_

## What this is

One immutable row per `(game_id, snapshot_ts)` in `s3://…/ncaaf/derived/game_prediction_snapshots`, written BEFORE kickoff, carrying the served P1.4 model's win probability and the margin/total predictive distributions. It is the forward track record: a backtest can always be re-derived, so only a row written in advance shows what we would actually have said.

⚠️ **Market-blind projection — `best_alpha = 0`.** Probabilities and intervals only; no pick, no edge, no win-rate. P1.4's CLV leg came back a clean null (ATS 0.496 = placebo), so an edge claim would assert something the evidence does not support. `assert_no_edge_claim` makes that a schema property.

## Last run

| field | value |
|---|---|
| season | 2026 |
| status | `ok` |
| games snapshotted | 50 |
| rows written | 0 |
| strength vintage | `as_of_week = 1` |
| served model | `ncaaf_game_distribution_v2` (strength_pace) |
| min lead to kickoff | 16579 min |
| P(home win) range | 0.356 – 0.883 |
| median 80% margin interval | 42.9 pts |
| median 80% total interval | 44.3 pts |
| pace term active | False |
| futures teams snapshotted | — |

## The gates

* **Leakage (HALT, DATE-based).** `assert_pre_kickoff` refuses the whole write unless every row's `snapshot_ts` is strictly before its `commence_time`. It is deliberately date-based: a week-based assertion re-uses CFBD's postseason week ordering (which restarts at 1) and passes green on exactly the rows it should catch — the P1.1/P1.2 lesson.
* **Never lose a prior week.** The writer READ-MERGE-WRITEs the season partition (`s3io.write_season_partition` overwrites), dropping only the `(game_id, snapshot_ts)` keys the new batch re-covers. A transient lake read RAISES rather than being mistaken for an empty partition.
* **Contract coverage.** `assert_contract_covered` refuses to score if any served column is absent or wholly NULL — a missing column is mean-imputed to exactly 0.0, which would silently serve a different model than the one certified.

## Known limits of the served model (stated, not patched)

* The served `strength_pace` contract carries **no neutral-site term** — the intercept absorbs one blended home-field bump (P2.1). Neutral-site games are priced with it; `is_neutral_site` is persisted so the limitation is auditable.
* The certified **pace term is inert pre-season** (week-1 tempo is NULL by construction, and a NULL column contributes exactly 0.0). `pace_term_active` records it per row.

## The assembly is verified, not asserted

The snapshot joins `team_strength_week` onto the schedule to rebuild the served contract — a SECOND renderer of `feature_ncaaf_pregame_matrix.sql`'s strength join, and a grep of one file never clears the other (E9.61). `--verify-against-matrix 2025` compares the two on real data: **all 25 served non-pace columns reproduce the P1.3 matrix to float noise (max |Δ| 6.75e-14) across 807 games**, at each game's own as-of week.

## ⏭️ The operator prerequisite (quality, not a blocker)

**Run the close-to-kickoff P1.2 RE-FIT before the first real snapshot.** Until fall-camp covariates publish, the strength mart carries the pre-season COLD START — a 2025 carry-forward, which is why the current 2026 board has Indiana leading. A snapshot is by design immutable and cannot be retaken after kickoff, so firing before the re-fit would freeze the cold start into the permanent forward record. The schedule therefore ships `default_status=STOPPED`; enable it only after the re-fit.

