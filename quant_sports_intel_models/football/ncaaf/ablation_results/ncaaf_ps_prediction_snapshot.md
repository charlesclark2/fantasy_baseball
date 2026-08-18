# NCAAF-PS — pre-kickoff game-prediction snapshots

_Last run: 2026-08-18T06:28:11.000Z (UTC)_

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
| min lead to kickoff | 16412 min |
| P(home win) range | 0.117 – 0.992 |
| median 80% margin interval | 42.8 pts |
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

## ⏭️ The operator prerequisite — the P1.2 re-fit (✅ done 2026-08-18)

A snapshot is immutable by design, so the season's P1.2 re-fit had to land BEFORE the first one. It has. Recorded here because two things about it are easy to get wrong.

**1. It is not one command.** P1.2 reads its covariates from the sports DuckDB MARTS (`ncaaf_team_roster_continuity`, `ncaaf_team_coaching_change`), not from the lake. So `run_team_strength` run against stale marts silently reproduces the cold start and looks successful — which is exactly what happened on 2026-08-17 (the Delta log shows the per-season writes; the output still had every covariate component at 0). The marts must be rebuilt from the fresh lake FIRST — the INC-25 build-ordering class:

```bash
cd quant_sports_intel_models/sports_dbt
AWS_DEFAULT_REGION=us-east-2 uv run python -m dbt.cli.main run \
  --select ncaaf.staging --threads 1 --project-dir . --profiles-dir .   # ~70s
AWS_DEFAULT_REGION=us-east-2 uv run python -m dbt.cli.main run \
  --select ncaaf.marts --project-dir . --profiles-dir .                 # ~20s
cd - && uv run python -m quant_sports_intel_models.football.ncaaf.models.run_team_strength --s3
```

**2. Verify it TOOK, not merely that it ran** — the check that separates the two is whether the covariate components are non-zero:

```sql
select as_of_week,
  sum(case when covariate_component_roster_flux <> 0 then 1 else 0 end) roster_flux,
  sum(case when covariate_component_coaching     <> 0 then 1 else 0 end) coaching,
  count(*) teams
from delta_scan('.../ncaaf/derived/team_strength_week') where season = <season> group by 1
```

0 / 0 / 138 is the cold start; 136 / 136 / 138 is a real re-fit.

**What the re-fit actually fixed** (worth stating, because the P0.7 note described the symptom differently): the cold start does not mis-ORDER the board so much as COMPRESS it toward the mean. Ohio State went from +19.7 to **+40.4** over Ball State and the slate's P(home win) span from 0.356-0.883 to **0.117-0.992**; the futures board sharpened from a flat 7.4%/4.9% at the top to 12.4%/11.9%. Indiana still leads the strength board after the re-fit, so "Indiana leads" was never the cold-start tell — compression was.

**No train/serve mismatch:** the re-fit rewrote only 2026. Seasons 2024 and 2025 are byte-identical across vintages (max |Δ| 0.0 over 2,144 / 2,176 rows), so the served P1.4 ridge and σ — fitted on 2015-2025 — still describe their training data exactly. The re-fit moved 2026 ONTO that manifold (covariates present, as in every training season), not off it.

