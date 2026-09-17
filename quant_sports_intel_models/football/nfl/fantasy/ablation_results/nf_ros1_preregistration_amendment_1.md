# NF-ROS1 — pre-registration amendment 1 (implementation pins, committed BEFORE any scoring)

Amends `nf_ros1_preregistration.md` (commit 44395535). Written while building the harness and
**before any arm, anchor, residual or match rate has been computed.** Every item below resolves a
detail the registration left under-specified; none moves a gate, a threshold, a population, a fold,
a metric or an arm.

1. **Name normalizer (§2.1).** The registration said "normalized name + position via
   `player_naming`". `player_naming` has display-casing helpers only, no join normalizer. The
   join uses `app/backend/services/league_scoring.normalize_player_name` + `normalize_position` —
   the normalizer the WVR1 F4 ladder and the live `_join_key` already use (one owner of the key).

2. **Scored term set (§2).** Prior and realized rows are both scored by `league_scoring.score_row`
   with a scoring resolved by `league_scoring.resolve_scoring(..., fields=F)`, where `F` is the
   INTERSECTION of the payload fields the prior rows carry and the fields the realized rows carry.
   A term only one side can express (e.g. the 40+-yard TD bonuses, absent from the realized line by
   `REALIZED_ABSENCE_REASON`) is CAPTURED on both sides, so prior and realized points are the same
   quantity. The resolved term report is written to the record.

3. **Anchor and degenerate intervals (§5).** §3.1 says every predictive is "its point plus the
   same residual-quantile construction (§4.3)". For a predictor with FIXED parameters (every
   degenerate, the oracle, the matched-n control) the residuals are computed on the training seasons
   with those fixed parameters (no leave-one-season-out, because there is nothing to refit). Real
   arms use the §4.3 leave-one-season-out residuals. `zero_width` / `max_width` override the
   interval as §5 states.

4. **History read (§2).** Historical `stats_player_week` and `schedules` are read through
   `deltalake.DeltaTable(uri, version=V)` with the §2 version pins (DuckDB's `delta_scan` carries no
   version argument). The serving build reads the latest version and stamps it.

5. **Team code resolution.** A player's team is resolved against the season's REG schedule team
   set; a board team code absent from that set falls back to the player's realized team. The harness
   REFUSES (raises) if more than 1% of evaluated player-seasons still have no schedule team — a
   silent zero `G_rem` is the failure this prevents. The resolved count is reported.

6. **Randomized PIT on the quantile grid (C9).** With `q_1..q_19` at levels `0.05..0.95`:
   `y < q_1` ⇒ `u ~ U(0, 0.05)`; `y > q_19` ⇒ `u ~ U(0.95, 1)`; `y` equal to one or more `q_i`
   (an atom, e.g. many quantiles at 0) ⇒ `u ~ U(L_first − 0.05, L_last)`; otherwise linear
   interpolation between the bracketing knots. Seed 20260917. 80% coverage is `q_2 ≤ y ≤ q_18`
   (levels 0.10 and 0.90), inclusive.

7. **Permuted matched foil (§5).** The permutation is drawn ONCE per (season, position) over
   players and applied to every k, so a player's permuted realized history stays internally
   consistent across weeks (a per-k permutation would hand the foil a history that is not any
   player's). Seed 20260917.

8. **`power_floor` (C7)** is `betting_ml.utils.coverage_power_floor.power_floor(n, nominal=0.80,
   target=0.05)`.
