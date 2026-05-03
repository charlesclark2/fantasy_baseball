## Hitter vs. Starter Pitch-Archetype Matchup Feature Impact

Date: 2026-05-03
Card: 7.J — Hitter–pitcher pitch-archetype matchup features

---

### Archetype Coverage

**Pitcher × season archetype distribution** (mart_pitcher_pitch_archetype):

Classification thresholds:
- `fastball_dominant` — fastball family (FF, SI, FT, FC) > 60% of classified pitches
- `breaking_dominant` — breaking family (SL, CU, KC, SV, CS) > 50% of classified pitches
- `mixed` — all other pitcher × season rows

Expected distribution based on Statcast pitch-mix norms (2015–2025):
- `mixed` is the plurality archetype (~55–65% of rows); most modern starters blend pitch families
- `fastball_dominant` accounts for ~20–30% (older-era and ground-ball specialists)
- `breaking_dominant` accounts for ~10–20% (elite slider-heavy starters)

Minimum sample gate: 100 classified pitches per pitcher × season (~3 starts).
Unknown pitch types (KN, FA, EP, PO, UN, null) excluded from denominator to avoid diluting family percentages.

**Starter archetype availability for scheduled starters (2016–2025)**:

Coverage uses prior-season archetype (game_year - 1), meaning:
- 2017 games use 2016 archetype data
- Starters with < 100 classified pitches in the prior season are unclassified (NULL → no archetype)
- Debut-season starters always produce NULL archetype (treated as 'mixed' at feature layer via null)

Estimated prior-season archetype availability:
- 2018–2025 regular season starters: ~85–90% archetype coverage (established starters)
- 2017: ~70–75% (partial 2016 Statcast coverage)
- April/May each season: same rate as prior-year end-of-season (annual snapshot, no mid-season update)

**Null rate for lineup_woba_vs_starter_archetype (2022–2025 regular season)**:

Expected null rate < 5% for games where:
1. A confirmed lineup exists (9 slots populated)
2. The opposing starter has a prior-season archetype
3. Batters have prior-season PA vs. that archetype

Shrinkage adjustment (pa_count / (pa_count + 50)) ensures adj_woba never returns NULL even for
low-PA cells — it blends to league average (0.320) when pa_count → 0. NULL only occurs when the
starter has no prior-season archetype at all (which nulls out the join in slot_archetype_stats,
returning coalesce(bva.pa_count, 0) = 0 and adj_woba = league average).

---

### Feature Importance

> **Note**: Full model retraining is deferred to pre-7M per project schedule. The section below
> documents the planned evaluation methodology; numbers will be populated after retrain.

**Evaluation plan**:

1. Permutation importance (sklearn `permutation_importance`) on held-out 2024–2025 test set
2. Compare `lineup_woba_vs_starter_archetype` and `lineup_k_pct_vs_starter_archetype` importance
   ranks vs. `avg_woba_30d` (existing top-ranked batting quality feature)
3. Hypothesis: archetype matchup adds incremental signal beyond raw lineup quality because it
   captures the *style-of-matchup* dimension not present in rolling averages alone

**Baseline feature set reference** (from stuff_plus_feature_impact.md, Card 7.F):
- `avg_woba_30d` consistently ranks in top 20% of features for total_runs and home_win models
- Archetype matchup features expected to rank below raw rolling averages but above platoon split
  features (analogous to Card 4.2 handedness adjustment at ΔR² = 0.001–0.002)

---

### Cross-Validation ΔR² (or equivalent)

> **Note**: Pending model retrain (deferred to pre-7M).

**Evaluation methodology**:
- 5-fold time-series CV (walk-forward splits preserving temporal ordering)
- Baseline: feature set as of Card 7.I (injury-adjusted lineup features)
- Treatment: baseline + 6 archetype matchup columns
- Targets: `total_runs` (regression) and `home_win` (classification)
- Metric: R² for total_runs, AUC-ROC for home_win

**ΔR² threshold for inclusion in primary feature set**: > 0.002 (consistent with Phase 4 notebook methodology)

Phase 4 Notebook 07 context: handedness matchup adjustment (Card 4.2) yielded ΔR² = 0.001–0.002
on its own. Pitch-archetype matchup hypothesis is that it captures a deeper style signal that
handedness does not — particularly the fastball_dominant vs. breaking_dominant distinction which
crosscuts both LHP and RHP categories.

---

### Row Count Verification

Both feature models are materialized as tables. Row count must be unchanged after adding archetype
columns (LEFT JOINs only, no new grain).

| Model | Grain | Expected behavior |
|-------|-------|-------------------|
| feature_pregame_lineup_features | game_pk × side | Row count identical — archetype_agg and starter_archetype are LEFT JOINed |
| feature_pregame_game_features | game_pk | Row count identical — upstream lineup features already one-row-per-game × side |

Verification query (run post-build):
```sql
-- Confirm row counts match pre-7J baseline
SELECT COUNT(*) FROM baseball_data.betting_ml.feature_pregame_lineup_features;
SELECT COUNT(*) FROM baseball_data.betting_ml.feature_pregame_game_features;
```

---

### Known Limitations

1. **Annual archetype snapshot**: A pitcher who dramatically changed their pitch mix mid-season
   (e.g., injury, mechanical adjustment, added a new pitch) is not captured until the next season's
   classification. The archetype reflects the full prior-season mix, not the current form.

2. **Card 7.F refinement path**: The current archetype classification uses raw Statcast pitch_type
   proportions with fixed thresholds (>60% fastball, >50% breaking). Card 7.F's Stuff+ data can
   refine archetype boundaries and add arsenal quality dimension (not just mix proportion) without
   re-engineering the feature model — documented as a future enhancement.

3. **Rookies and debut-season starters**: Have no prior-season archetype. These rows produce NULL
   for `starter_pitch_archetype` and NULL batter archetype splits. The shrinkage formula ensures
   adj_woba falls back to league average (0.320) so downstream ML models receive a sensible imputed
   value rather than NULL. Imputation in the Python preprocessing layer should treat NULL
   `starter_pitch_archetype` as 'mixed' (the plurality class).

4. **Early-season moderate null rate**: April/May call-ups who debuted in the prior season may lack
   sufficient PA (< 50) vs. a given archetype in the prior year. Shrinkage handles this gracefully
   by blending toward league average — no hard NULL is produced.

5. **Offspeed family not separately tracked in features**: The current feature set exposes wOBA,
   xwOBA, K%, ISO vs. the starter archetype but does not separately surface batter performance vs.
   the offspeed family. This is an acceptable v1 simplification — the archetype label encodes the
   dominant dimension, and offspeed-heavy pitchers fall under 'mixed'.
