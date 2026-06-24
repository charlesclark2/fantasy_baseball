# E13.10 — Zone-Matchup heatmap (design + methodology)

**Status:** code-complete 2026-06-24. Track A (marketable viz) = shippable; Track B (signal test)
= operator runs the lift harness (honest-null expected — the 5th "no edge" confirmation if it
lands null, consistent with [[project_edge_program_e13_4_status]] and the E13.2 "matchup ≈
identity" finding).

**Reframe (operator 2026-06-24):** the edge search is exhausted, so E13.10's PRIMARY deliverable
is the **marketable batter-hot-zone × pitcher-tendency overlay** — "show your work" transparency
content that ships regardless of edge. The zone-overlap *signal* is a gated bonus.

All compute is **lakehouse (S3 + duckdb), never Snowflake** (E13.10 cost-aware rule). A
3-month profile read is ~8s; a 1-season window ~10s (year-restricted globs + column pruning).

---

## 1. Where the code lives

| Piece | Path |
|---|---|
| Pure grid / pitch-group binning | `betting_ml/scripts/zone_matchup/grid.py` |
| Empirical-Bayes shrinkage | `betting_ml/scripts/zone_matchup/shrink.py` |
| duckdb lakehouse reads (S3) | `betting_ml/scripts/zone_matchup/lakehouse.py` |
| Profile assembly (EB + cold-start) | `betting_ml/scripts/zone_matchup/profiles.py` |
| Overlap scalar + per-game aggregation | `betting_ml/scripts/zone_matchup/overlap.py` |
| Track A viz (structured overlay JSON + PNG proof) | `betting_ml/scripts/zone_matchup/viz.py` |
| Operator CLI | `betting_ml/scripts/build_zone_matchup.py` |
| Harness bridge (`--feature-parquet`) | `betting_ml/scripts/incremental_lift_eval.py` |
| Unit tests (pure logic + bridge + overlay JSON) | `betting_ml/tests/test_zone_matchup.py` |
| JSON contract example (committed) | `e13_10_sample_overlay.json` |
| Served JSON (product) | `s3://…/baseball/serving/zone_matchup/overlay/as_of=<date>/<bid>_vs_<pid>.json` |
| PNG research proof (S3, NOT git) | `s3://…/baseball/artifacts/zone_matchup_proofs/as_of=<date>/<bid>_vs_<pid>.png` |
| App-render spec | `e13_10_app_handoff_spec.md` |
| Lift null-dossier (operator fills) | `ablation_results/e13_10_zone_overlap_lift.md` |

## 2. The grid

A `GRID_NX × GRID_NZ` (default **5×5**) grid over **(plate_x_ft, z_norm)** where
`z_norm = (plate_z_ft − sz_bot)/(sz_top − sz_bot)` height-normalizes the rulebook zone per batter
(so a 6'5" and a 5'9" hitter share coordinates). The grid covers the zone **plus a shadow band**
(x ∈ [−1.4, 1.4] ft, z_norm ∈ [−0.25, 1.25]) so chase/edge cells exist. Bins are **uniform** so
the Python binning (`grid.bin_x/bin_z`) and the duckdb SQL (`grid.sql_ix/sql_iz`) are the same
closed form — pinned by `test_python_and_sql_binning_agree`.

Pitch types collapse to 3 **arsenal groups** (`FB` fastballs, `BR` breaking, `OS` offspeed) to
keep per-cell counts from going too sparse. Both the Python `group_of()` and the SQL `CASE` are
kept in lock-step (`test_group_of_and_sql_case_agree`).

## 3. The two profiles (built ONCE, serve both tracks)

**Batter value profile** — per `(batter, b_hand, vs_p_hand, group, cell)`, three EB-shrunk reads:
- `value` = mean **`delta_run_exp`** (run value per pitch, batter POV; +1.45 on a HR, −0.22 on a
  K — verified on the lakehouse) — the overlap input. Captures takes, whiffs, and contact in one.
- `whiff_rate` = swings-and-misses / swings.
- `xwoba_con` = mean xwOBA on balls in play.

Split by **both** handednesses (`b_hand` = the batter's stance — varies with the pitcher hand for
switch hitters; `vs_p_hand` = the pitcher faced). Expanded to the **full grid** per key, so cells
the batter rarely sees resolve to the EB prior rather than being dropped (which would bias the
freq-weighted overlap).

**Pitcher usage profile** — per `(pitcher, p_hand, vs_b_hand, group, cell)`, the normalized pitch
**frequency** (Σ = 1 within a pitcher × faced-batter-hand) — *where + what they throw, platoon-
split*.

**Heavy EB shrinkage** (E13.10 "cells sparse"): `value' = (n·raw + k·prior)/(n+k)` toward a
**tiered league prior** (cell → group → global fallback), with heavy pseudo-counts (K_VALUE=120,
K_RATE=150, K_XWOBA=60). Pinned by `test_eb_*`.

**Cold-start (E13.7 pattern):** a batter/pitcher with `< 200` window pitches is flagged
`is_cold_start`; pitchers additionally fall back to the **league usage distribution** for their
handedness. The flag rides through to the lift harness's cold-start stratification.

## 4. Leak discipline

Every profile read takes a half-open window `[start, end)` and filters `game_date >= start AND
game_date < end` — strictly `< end` (the as-of leak boundary). For **Track B** each season `Y` is
profiled from the **prior `window_seasons` seasons only** (`[Y−W, Y)`), so the feature for a game
in season `Y` never sees in-season-or-later pitch — strictly leak-clean (mirrors the repo's
prior-season archetype/Stuff+ joins). The lineup proxy uses only **who batted in innings ≤ 3**
(the 9-man card, first time through) — *who*, never outcomes.

## 5. The overlap scalar (Track B)

The E5.6 game-theory-corrected overlap (the §"weight by pitcher's actual location frequency"):

```
overlap(b, p) = Σ_{cell, group}  batter_value(b, vs p.hand, cell, group)
                                  · pitcher_freq(p, vs b.hand, cell, group)
```

`pitcher_freq` sums to 1, so the overlap is the batter's per-cell run value **averaged by where /
what the pitcher actually throws** — a hot zone counts only to the extent the pitcher lives there.
Per game/side: averaged over the side's lineup vs the opposing starter →
`home_zone_overlap` / `away_zone_overlap` (the columns the harness ingests). Pinned by
`test_compute_overlap_*` and `test_game_side_overlap_pivots_to_home_away`.

## 6. Operator run commands

```bash
# Track A — full profiles as-of today + the overlay product (JSON→serving S3, PNG proof→artifact S3):
uv run python betting_ml/scripts/build_zone_matchup.py profiles \
    --start 2023-01-01 --end 2026-06-24 --out-dir artifacts/zm_2026 --s3        # ~tens of sec
uv run python betting_ml/scripts/build_zone_matchup.py viz \
    --profiles-dir artifacts/zm_2026 --top 8                                     # JSON+proof → S3
# (add --no-s3 --local-dir <dir> for a local dev render; JSON is the product, PNG is proof-only)

# Track B — per-game feature (prior-season windows ⇒ leak-clean) → lift harness:
uv run python betting_ml/scripts/build_zone_matchup.py feature \
    --seasons 2021,2022,2023,2024,2025,2026 --window-seasons 3 \
    --out artifacts/zone_overlap_feature.parquet                                 # minutes
# sanity-validate the harness, then the candidate (per-side FIRST, then home_win):
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --sanity
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \
    --feature-parquet artifacts/zone_overlap_feature.parquet \
    --add-features opp_zone_overlap --run-name e13_10_zone
uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \
    --feature-parquet artifacts/zone_overlap_feature.parquet \
    --add-features home_zone_overlap,away_zone_overlap --run-name e13_10_zone
```

**GATE (Track B, pre-registered):** SHIP only if lift > 0 on BOTH pooled AND non-cold-start AND
PBO < 0.2 AND DSR ≥ 0.95 AND not-degenerate. Expectation = **null** (4 prior confirmations +
matchup≈identity). A clean null is a fine outcome — the viz is the win. If it DOES lift leak-
tight → feed E5.2 K-props / the preserved `pa_outcome_v2` asset.
