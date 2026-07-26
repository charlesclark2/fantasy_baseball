# NF-D3 file benchmarks (operator drop-in) — Fantasy Footballers / PFF / 4for4 / …

## Which systems are AUTO-fetched vs need a file

| system | how | leakage basis | seasons |
|--------|-----|---------------|---------|
| **ADP** (Fantasy Football Calculator) | auto (`run_adp_ingest.py`) | dated week-before-Week-1 | 2018–2024, 2026 |
| **ECR** (FantasyPros) | auto (`run_ecr_ingest.py`) | dated early-Sept snapshot | 2019–2026 |
| **Sleeper** (Rotowire projections) | auto (`run_projection_benchmark_ingest.py`) | verified frozen-preseason (gp=17 test) | 2019–2026 |
| **ESPN** (PPR draft rank) | auto (`run_projection_benchmark_ingest.py`) | preseason draft artifact (as-of date unstamped → lower-verified); unofficial API | **2023+** only |
| **Yahoo** | ❌ not available | needs 3-legged OAuth + does not expose season projections | — (NF-C0 territory) |
| **Fantasy Footballers / PFF / 4for4 / Football Outsiders** | **FILE drop-in (below)** | operator's responsibility | whatever you supply |

Auto-fetched systems need no file. Paid / no-public-API systems are supplied as files here and scored
**identically** by the standing scorecard.

## How to add a system

Drop a CSV named **`<system>_<season>.csv`** in this folder:

- `<system>` — short slug (underscores ok): `fantasy_footballers`, `pff`, `espn`, `4for4`
- `<season>` — the 4-digit projection season the file is FOR, e.g. `2025`

The loader matches headers **case/space-insensitively** and needs:

| need | accepted header names |
|------|-----------------------|
| name | `player_name` \| `player` \| `name` |
| position | `position` \| `pos` |
| **one** ordering column (either) | RANK: `rank` \| `overall_rank` \| `ecr` \| `consensus_rank` (lower=better) — OR — POINTS: `proj_fp_ppr` \| `points` \| `projection` \| `fpts` (higher=better) |

Extra columns are ignored. K/DST rows are dropped (we project offensive skill only). If both a rank and
a points column exist, POINTS is used.

## ⚠️ Leakage rule (the honesty bar)

The file **must be that system's PRESEASON ranking/projection** for `<season>` — frozen before Week 1.
A file scored against a season it was published DURING/AFTER is hindsight and disqualifies the claim.
The scorecard **cannot verify** this, so it is on you to supply preseason files only. (ADP/ECR are
verifiable — each historical year's snapshot is dated to early September of that year.)

## Scoring

- A **completed** season (realized outcomes exist) → the file is graded vs realized, apples-to-apples
  with ADP/ECR/our model: within-position Spearman ρ + rank-MAE + the fade panel. This is the
  "we beat X" proof.
- An **in-progress** season (e.g. 2026) → `run_benchmark_scorecard.py --forward-season 2026` emits an
  **agreement view** (how aligned our board is + our most contrarian picks). NO accuracy claim until
  the season completes.

## What's here now

- `fantasy_footballers_2026.csv` — FF Ultimate Draft Kit Top-200 (cross-position overall rank, 2026).
  Forward-only (no 2025→2026 realized yet). **To get a scoreable FF proof point, add
  `fantasy_footballers_2025.csv`** (their PRESEASON 2025 rankings, all positions) — it will be graded
  vs realized 2025 head-to-head with ECR + our model on the next scorecard run.

> Files in this folder are **git-ignored** (`*.csv` under `artifacts/`) — licensed competitor data is
> never committed. Only this README is tracked.
