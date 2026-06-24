# E13.2b — Feature-augmented PA-model re-test (zone-matchup PROFILES + miss_distance)

**Model-A · the "test everything we built" closure · harness-first, sim only on lift · 2026-06-24**

## Why this story exists

E13.2 (PA-outcome vs log5) and E13.10 (zone-matchup) both came back **null** — but E13.10's null was
only on a **collapsed overlap SCALAR** (`Σ batter_value·pitcher_freq`, summed across pitch groups and
the value channel alone). The full per-cell PROFILE machinery (E13.10) and the new `miss_distance`
bat-tracking axis (INC-13) were **built but never tested in-model**. Operator principle: *a null we
reasoned to, not tested, isn't trustworthy.* This is the trustworthy-null closure — test the BUILT
features against the actual baselines, then call it.

## GATE — verified 2026-06-24 (this session, before building)

🔒 Story gates on "INC-13 verifies + captures `miss_distance`." **CLEARED:**
- INC-13 shipped (commit `3659b12`); `miss_distance` cast in `stg_batter_pitches.sql:389`
  (`::float`, populated only on swinging strikes), S3 map in `ingest_statcast_to_s3.py:215`.
- **Data presence confirmed (not just plumbing):**
  - Snowflake `baseball_data.savant.batter_pitches` 2026: **36,600** non-null `miss_distance`
    over **1,164 / 1,184** games; avg 3.16, range 0.1–54.2 (all on whiffs ≈ 10.5% of pitches).
  - S3 lakehouse `stg_batter_pitches` year=2026: column present (with `bat_speed_mph`,
    `swing_length_ft`, `swing_path_tilt_degrees`), full season **Mar 25 → Jun 23**, consistent
    ~10.5% non-null by month. The harness/lakehouse path reads S3, so this is the binding check.
- ⚠️ **2026-ONLY** — Savant did NOT backfill prior seasons → `miss_distance` cannot be multi-season
  purged-CV'd. Its half of this re-test is **EXPLORATORY / underpowered** (single partial season, no
  historical fold). The zone PROFILES (2015–2025 history) are the **conclusive** half.

## What was built (code-complete; heavy runs handed to operator)

### Half 1 — zone-matchup PROFILE features (CONCLUSIVE) — the richer form the scalar collapsed
`betting_ml/scripts/zone_matchup/overlap.py` — new `compute_profile_overlap()` +
`game_side_profile_features()`. Same lineup↔opposing-starter pairing as the scalar, but emits a
**7-channel decomposition** per (game_pk, side) instead of one mean — recovering the three axes the
scalar threw away:

| Channel | Definition | Axis the scalar collapsed |
|---|---|---|
| `zone_value` | `Σ value·freq` | (= the already-null overlap scalar — kept as anchor) |
| `zone_fb` / `zone_br` / `zone_os` | per-pitch-group partial sums of `value·freq` | **pitch-group STRUCTURE** (FB-exploited ≠ BR-exploited once summed) |
| `zone_whiff` | `Σ whiff_rate·freq` | the **whiff channel** (K-exposure → run suppression) |
| `zone_xwoba` | `Σ xwoba_con·freq` | the **damage-on-contact channel** |
| `zone_peak` | `max_cell(value·freq)` | **peakiness** (one concentrated exploitable cell vs diffuse) |

Platoon structure is already baked in (the overlap joins on each pair's actual `b_hand`/`p_hand`).
Emitted `home_/away_`-wide → the E13.4 harness ingests via `--feature-parquet`.
CLI: `build_zone_matchup.py feature --rich` (new `--rich` flag).

### Half 2 — `miss_distance` whiff-severity (EXPLORATORY, 2026-only)
`betting_ml/scripts/build_miss_distance_feature.py` — new standalone builder. Two game-grain
features per side, EB-shrunk (k=30 pseudo-whiffs) toward the **as-of** league mean, strictly
leak-clean (`< game_date`, expanding within 2026 via `merge_asof(allow_exact_matches=False)`):
- `<side>_starter_miss_induced` — the side's starter's prior mean induced miss_distance
  (swing-and-miss-severity / deception proxy).
- `<side>_lineup_miss` — the side's first-3-innings lineup's prior mean own-whiff miss_distance.

### Tests + smoke (this session)
- 3 new pure-logic unit tests in `betting_ml/tests/test_zone_matchup.py`
  (channel decomposition re-sums to the total; whiff/xwoba freq-weighting; miss_distance as-of
  leak-safety — a same-day whiff never leaks). **Full suite: 540 passed, 1 skipped.**
- End-to-end smoke on REAL data (no heavy rebuild): profile channels 100% coverage, non-degenerate,
  mutually distinct (`zone_value`↔`zone_whiff` corr −0.002, ↔`zone_xwoba` 0.124; ~9 hitters/side).
  miss_distance builder ~10s, 100% coverage, starter std 0.51 / lineup std 0.25 (non-degenerate).

## OPERATOR RUN-ORDER (the heavy lift; CLAUDE.md >1-min rule)

CI first: `dbtf build --select state:modified+` is **N/A** (no dbt changes — pure lakehouse/Python).
`uv run pytest` = green (540/1). Then:

```bash
# ── Half 1: zone PROFILES (conclusive; full leak-clean per-season prior windows) ──
uv run python betting_ml/scripts/build_zone_matchup.py feature --rich \
    --seasons 2021,2022,2023,2024,2025,2026 --window-seasons 3 \
    --out artifacts/zone_profile_feature.parquet

# validate the harness on the loaded frame FIRST (noise + dup sanity), then the real candidates:
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --sanity
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \
    --feature-parquet artifacts/zone_profile_feature.parquet \
    --add-features off_zone_fb,off_zone_br,off_zone_os,off_zone_whiff,off_zone_xwoba,off_zone_peak \
    --run-name e13_2b_zone_profile
uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \
    --feature-parquet artifacts/zone_profile_feature.parquet \
    --add-features home_zone_fb,away_zone_fb,home_zone_br,away_zone_br,home_zone_os,away_zone_os,home_zone_whiff,away_zone_whiff,home_zone_xwoba,away_zone_xwoba,home_zone_peak,away_zone_peak \
    --run-name e13_2b_zone_profile

# ── Half 2: miss_distance (EXPLORATORY — NOTE --min-year 2026; 2026-only feature) ──
uv run python betting_ml/scripts/build_miss_distance_feature.py \
    --season 2026 --out artifacts/miss_distance_feature.parquet
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --min-year 2026 \
    --feature-parquet artifacts/miss_distance_feature.parquet \
    --add-features opp_starter_miss_induced,off_lineup_miss --run-name e13_2b_miss_distance
uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win --min-year 2026 \
    --feature-parquet artifacts/miss_distance_feature.parquet \
    --add-features home_starter_miss_induced,away_starter_miss_induced,home_lineup_miss,away_lineup_miss \
    --run-name e13_2b_miss_distance
```

Read the **`non_cold_start`** stratum. **SHIP gate** (per candidate): lift>0 (pooled AND non-cold)
AND PBO<0.2 AND DSR≥0.95 AND not degenerate. The miss_distance pass is single-season — even a
"pass" is SUGGESTIVE, not conclusive (flag wide CI / no historical fold).

## Surface coverage (honest scoping)
The story names three surfaces: PA-outcome (vs log5), per-side run-means, home_win. Under the
**harness-first cost gate** ("the heavy sim runs only on a lift"), this pass delivers the cheap
conclusive test on **per-side run-means** (the E2.2 priority integration target) **+ home_win** via
the E13.4 harness — for BOTH feature sets. The **PA-outcome-vs-log5** re-test with these features
is a PA-grain integration (per-PA `compute_profile_overlap` join, leak-clean as-of, into
`features_pa_outcome.py` + a 1.96M-PA retrain) — i.e. *reopening E13.2 Phase 1*. Per the escalation
rule it is **deferred unless the harness shows lift** (expected null; matchup ≈ identity already
confirmed at PA grain by E13.2 v2 — log5 near-optimal, context/splits add a sub-floor sliver). If a
zone channel clears the harness gate, the PA-grain wiring is the first escalation step.

## DECISION RULE (pre-registered)
- **Any** zone-PROFILE channel clears the gate (leak-tight, above the noise floor) → **ESCALATE**:
  reopen the heavy E13.2 Phase-2 MC sim with the winning channel(s) / feed E5.2 K props.
- **Both halves null** → the **6th independent no-edge confirmation** this cycle; the closure is now
  airtight (built machinery tested IN-MODEL, not just as a scalar) → archive, done. Honest framing:
  matchup ≈ identity; `best_alpha = 0`; value = product-quality projections + fantasy, not edge.

## RESULT

### Half 1 — zone PROFILES (operator run 2026-06-24) → **NULL both targets**
| Candidate set | target | lift (non-cold) | PBO | DSR | verdict |
|---|---|---|---|---|---|
| zone PROFILE 6ch (`off_zone_fb/br/os/whiff/xwoba/peak`) | perside_runs | +0.0008 (pooled +0.0011) | 0.427 ✗ | 0.837 ✗ | **NO-SHIP** |
| zone PROFILE 12ch (`home_/away_ ×6`) | home_win | −0.0015 (pooled −0.0015) | 0.142 ✓ | 0.073 ✗ | **NO-SHIP** |

- **perside_runs:** positive but tiny lift (+0.0008 non-cold) — BELOW the ~0.0019 noise-control floor
  the E13.4 harness sets — and fails BOTH PBO (0.427) and DSR (0.837). n_eval=11,428, coverage 90.4%,
  eval std 5.4e-4 (not degenerate).
- **home_win:** lift is NEGATIVE (−0.0015, mildly hurts) on all/non-cold/cold strata; PBO clears
  (0.142) but DSR collapses (0.073). n_eval=4,927, coverage 89.6%.
- **Orthogonal-but-inert** (the strongest form of null): the decomposition is genuinely NEW
  information, not redundant — max|corr| vs the contract is 0.28–0.38 (whiff 0.36–0.38, peak ~0.28,
  pitch-group ~0.23–0.29), all well clear of the 0.7 redundancy cut — yet it lifts nothing. The
  whiff / xwoba-on-contact / pitch-group-structure channels the E13.10 scalar collapsed carry **no
  incremental signal** over the v6 contract. The conclusive half (2015–2025 history) is **airtight
  null**. Artifacts: `e13_2b_zone_profile_{perside_runs,home_win}_lift.json`.

### Half 2 — miss_distance (2026-only, EXPLORATORY) → **UNTESTABLE-IN-HARNESS (deferred), not a null**
| Candidate set | target | result |
|---|---|---|
| miss_distance (2026-only) | perside_runs | `n_eval=0` → 🛑 guard fired (INVALID, not a signal null) |
| miss_distance (2026-only) | home_win | `n_eval=0` → 🛑 guard fired (INVALID, not a signal null) |

**Root cause = the pre-registered data constraint, made concrete.** The feature BUILD is sound —
the parquet merged at **100% coverage** with real variance (smoke: starter std 0.51, lineup std
0.25, non-degenerate). But `incremental_lift_eval`'s purged CV is **season-walk-forward** (Half 1
used eval folds 2024/2025/2026, each trained on all prior seasons). `miss_distance` exists **only in
2026**, so `--min-year 2026` leaves a single season → no walk-forward fold can form → **n_eval=0** →
the candidate slice is empty → `std=0` → the degeneracy guard correctly refuses to emit a verdict.
This is the guard doing its job, NOT a build bug and NOT a signal null.
- `--min-year 2025` does **not** rescue it: the feature is null on every 2025 train row → imputed to a
  constant in training → the model can't learn from it → still degenerate. A single-season feature is
  simply not evaluable in a season-walk-forward purged-CV harness.
- **Verdict: DEFERRED — revisit once a full prior season of `miss_distance` accrues (≈2027), when a
  leak-clean historical train fold exists.** Exactly the story's pre-registered caveat ("2026-only →
  cannot be multi-season purged-CV'd; SUGGESTIVE not conclusive; revisit as seasons accrue"). A
  bespoke within-2026 temporal split could give a weak directional peek, but the story pre-registers
  "don't draw a firm verdict from the thin sample," so it is not run here.
- Artifacts (record of the guard firing): `e13_2b_miss_distance_{perside_runs,home_win}_lift.json`.

## FINAL DECISION (2026-06-24) → **NULL / no escalation; 6th no-edge confirmation**
- **Conclusive half (zone PROFILES, 2015–2025 history) = airtight null** both targets — the richer
  per-cell decomposition (whiff / xwoba-on-contact / pitch-group structure / peakiness) the E13.10
  scalar collapsed is **orthogonal-but-inert** (genuinely new info, max|corr| 0.28–0.38; lifts
  nothing). The built zone machinery is now tested IN-MODEL, not just as a scalar → the closure is
  airtight.
- **Exploratory half (miss_distance) = parked** (untestable in-harness until 2027; build preserved
  and ready to re-run when the historical fold exists).
- **No escalation** (no leak-tight lift above the floor) → no heavy E13.2 MC-sim reopen.
- This is the **6th independent no-edge confirmation** this cycle (H2H, main totals, E13.4 coverage,
  E13.2 PA-vs-log5, E13.10 scalar, E13.2b profiles). `best_alpha = 0`; model-track value = product
  projections + fantasy, not a betting edge. `pa_outcome_v2` retains the profiles as a future-sim
  consumer only.
