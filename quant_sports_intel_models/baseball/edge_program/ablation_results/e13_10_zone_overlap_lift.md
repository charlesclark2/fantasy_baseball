# E13.10 Track B — zone-overlap incremental-lift dossier

**Status:** SCAFFOLD — feature code-complete 2026-06-24; **operator runs the lift harness** and
fills §3/§4 below. Expectation: **NULL** (the 5th "no edge" confirmation). Track A (the viz) ships
regardless; a clean null here is a fine outcome.

## 1. Hypothesis & why a null is expected
Candidate: the **zone-overlap scalar** `home_zone_overlap` / `away_zone_overlap` (= batter per-cell
run value, weighted by the opposing starter's actual pitch-location/arsenal frequency, averaged
over the lineup). Tests whether a *spatial* matchup read buys incremental signal over the existing
identity/aggregate matchup features (Stuff+ / archetype / platoon / TTO).

Prior evidence it will be null:
- **E13.2** (`e13_2_pa_outcome_v2_cv.md`): "matchup ≈ identity" — a 65-feature PA-outcome model
  beats log5 by only +0.0043 nats; **platoon/TTO ≈ 0 conditional**, 86% of signal is batter×pitcher
  identity priors. A zone read is another conditioning of the same identity.
- **E13.4** (`project_edge_program_e13_4_status`): all candidates (TTO, fatigue, FanGraphs windows)
  → NULL. The "no edge" coverage conclusion is already earned.

## 2. Pre-registered gate (from the E13.4 harness — do NOT move the bar after seeing results)
SHIP only if **ALL** hold (else record null):
- incremental lift > 0 on **both** pooled AND the **non-cold-start** subset, AND
- **PBO < 0.2**, AND
- **DSR ≥ 0.95** (deflated by #candidate configs), AND
- **not degenerate** (eval std > 1e-9, coverage > 50%, not byte-identical to base).
Run `--sanity` first to validate the harness on this load before trusting the verdict.

## 3. Run log  *(operator: paste commands + console)*
```
# build the leak-clean per-game feature (prior-season windows):
uv run python betting_ml/scripts/build_zone_matchup.py feature \
    --seasons 2021,2022,2023,2024,2025,2026 --window-seasons 3 \
    --out artifacts/zone_overlap_feature.parquet

# per-side FIRST (the priority integration target per E13.4 §6):
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --sanity
uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \
    --feature-parquet artifacts/zone_overlap_feature.parquet \
    --add-features opp_zone_overlap --run-name e13_10_zone
# then home_win:
uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \
    --feature-parquet artifacts/zone_overlap_feature.parquet \
    --add-features home_zone_overlap,away_zone_overlap --run-name e13_10_zone
```
_(JSON written to `ablation_results/e13_10_zone_<target>_lift.json`.)_

## 4. Results  *(operator fills from the JSON)*

| target | metric | n_eval | lift (all) | lift (non-cold) | PBO | DSR | degenerate? | verdict |
|---|---|---|---|---|---|---|---|---|
| perside_runs | crps | 11428 | −0.0006 | −0.0008 | 0.588 | 0.298 | **No** (cov 90.4%, std 1.8e-3) | **NO-SHIP — trustworthy null** |
| home_win | nll | 4927 | −0.0003 | −0.0010 | 0.837 | 0.397 | **No** (cov 89.6%, std 1.8e-3) | **NO-SHIP — trustworthy null** |

**perside_runs read (2026-06-24):** clean null on the priority integration target. The candidate is
**genuinely orthogonal** (max|corr| = 0.158 vs `opp_pit_k_pct_std`) — i.e. NOT redundant, it carries
*new* information — but **inert**: lift ≤ 0 on both pooled and the non-cold-start subset, PBO 0.588
(the candidate doesn't persist as best — coin-flip selection), DSR 0.298. Coverage 90.4% + non-zero
eval std ⇒ **NOT degenerate** → this is a real "no signal," not a data artifact.

**home_win read (2026-06-24):** same verdict. lift ≤ 0 on pooled (−0.0003) AND non-cold (−0.0010),
PBO 0.837, DSR 0.397; coverage 89.6%, std fine ⇒ trustworthy, not degenerate. Orthogonality is
moderate here (0.327 / 0.344 vs `home/away_lineup_avg_xwoba_vs_cluster`) — expected, since the
game-level overlap aggregates over the lineup and so partly tracks the existing lineup-archetype
xwOBA features; even the orthogonal residual is inert.

**Both targets null** ⇒ confirms the E13.2 "matchup ≈ identity" mechanism: the per-cell spatial
read adds nothing on top of the existing identity/aggregate matchup features. Exactly the predicted
outcome — the **5th independent "no edge" confirmation** this cycle (H2H, main totals, E13.4
coverage, E13.2 PA-vs-log5, now E13.10 zone-overlap). The VIZ (Track A) is the win.

**Coverage check (read FIRST):** `[feature-parquet] merged … (coverage X%)` must be high and the
JSON's `candidate_eval_coverage` > 50% — else the verdict is INVALID (under-built feature), not a
null. The feature is non-null only for games whose lineup+starter resolved (~95% in smoke).

## 5. Decision
- [x] **NULL** (gate not cleared on BOTH perside_runs and home_win) → recorded as the 5th no-edge
  confirmation; the zone-overlap scalar is NOT wired to any model; the VIZ (Track A) ships. **DONE
  2026-06-24.**
- [ ] ~~LIFT (gate cleared, leak-tight)~~ — did not occur.

**Status: CLOSED — trustworthy null, both targets.** `pa_outcome_v2` remains the future consumer if
the product/sim track reopens, but the zone-overlap feature earned no place in a betting model.
