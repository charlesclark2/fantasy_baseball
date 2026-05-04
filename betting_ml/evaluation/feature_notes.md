# Feature Notes — Card 7.Q: Bullpen Fatigue IP Features

**Date added:** 2026-05-03  
**Card:** 7.Q — Bullpen Fatigue & Availability Features

## New columns added

Three net-new columns added to `mart_bullpen_workload` and surfaced as six home/away columns in `feature_pregame_game_features`:

| Column (game features) | Source | Description |
|---|---|---|
| `home_bullpen_ip_prev_1d` | `bw.bullpen_ip_prev_1d` | Home bullpen innings pitched (outs/3) in 1 preceding calendar day |
| `home_bullpen_ip_prev_2d` | `bw.bullpen_ip_prev_2d` | Home bullpen innings pitched (outs/3) over 2 preceding calendar days |
| `home_pitchers_used_prev_2d` | `bw.pitchers_used_prev_2d` | Home relievers used (slot count) over 2 preceding calendar days |
| `away_bullpen_ip_prev_1d` | `bw.bullpen_ip_prev_1d` | Away equivalent of above |
| `away_bullpen_ip_prev_2d` | `bw.bullpen_ip_prev_2d` | Away equivalent of above |
| `away_pitchers_used_prev_2d` | `bw.pitchers_used_prev_2d` | Away equivalent of above |

`outs_recorded` was added to `mart_bullpen_workload` using the same out-event list as `mart_bullpen_effectiveness` (consistent definition). IP = outs_recorded / 3.0, rounded to 1 decimal.

## Hypothesis

IP-normalized workload may carry stronger signal than pitch-count equivalents because it accounts for pitcher efficiency — 10 pitches over 1/3 inning vs 10 pitches over 2 innings represents very different bullpen stress. The strongest expected effect is on the totals model (depleted pen → more late-inning offense).

## Baseline: pitch-count analogues from feature_selection.md

The pitch-count equivalents had the following max |r| values across all three targets (home_win, total_runs, run_differential):

| Column | Max |r| | Retained? |
|---|---|---|
| `away_bullpen_pitches_prev_7d` | 0.0423 | Yes (r ≥ 0.02) |
| `away_bullpen_pitches_prev_3d` | 0.0167 | No (r < 0.02) |
| `away_bullpen_pitches_prev_1d` | 0.0148 | No (r < 0.02) |
| `home_bullpen_pitches_prev_3d` | 0.0145 | No (r < 0.02) |
| `home_bullpen_pitches_prev_7d` | 0.0130 | No (r < 0.02) |
| `home_bullpen_pitches_prev_1d` | 0.0182 | No (r < 0.02) |
| `away_closer_used_prev_2d` | 0.0256 | Yes (r ≥ 0.02) |
| `away_closer_used_prev_1d` | 0.0253 | Yes (r ≥ 0.02) |
| `home_closer_used_prev_2d` | 0.0252 | Yes (r ≥ 0.02) |
| `home_closer_used_prev_1d` | 0.0133 | No (r < 0.02) |

Key thresholds for IP columns to beat: `home_bullpen_pitches_prev_1d` (r=0.0182), `away_bullpen_pitches_prev_1d` (r=0.0148).

## Spot-check validation (2024-07-15 to 2024-07-20)

- `bullpen_ip_prev_1d` is non-zero for all rows where `bullpen_pitches_prev_1d > 30` ✓
- Max observed `bullpen_ip_prev_1d` = 5.0 (PIT, 2024-07-20) — well under 9.0 cap ✓
- `pitchers_used_prev_2d` ≤ `pitchers_used_prev_3d` confirmed ✓
- Equal 1d/2d values on 2024-07-20 expected: All-Star break meant no games on 2024-07-18 ✓

## Null rates (2024–2026 regular season, feature_pregame_game_features)

| Column | Null count | Null rate |
|---|---|---|
| `home_bullpen_ip_prev_1d` | 29 / 5,356 | 0.54% |
| `home_pitchers_used_prev_2d` | 142 / 5,356 | 2.65% |

Both under the 5% threshold. Nulls are expected for the first game(s) of a season where no prior-day bullpen data exists.

## Correlation analysis and CV impact

**Deferred to Card 7.MA (pre-7M batch retrain checkpoint).**

Per project cadence, model retrains are batched before Card 7.MA rather than per-card. Actual correlation values (`bullpen_ip_prev_1d`, `bullpen_ip_prev_2d`, `pitchers_used_prev_2d` max |r| against all three targets), retain/dropped status, Brier score delta, and mean h2h edge delta will be documented here after the 7.MA retrain.

Expected outcomes (hypothesis to verify at retrain):
- `home_bullpen_ip_prev_1d` should exceed r=0.0182 (its pitch-count analogue) if IP normalization improves signal
- `away_bullpen_ip_prev_1d` should exceed r=0.0148
- If no IP column clears r ≥ 0.02: workload signal is adequately captured by the already-retained `away_bullpen_pitches_prev_7d`; no further action needed on this card

---

# Feature Notes — Card 7.R: Pythagorean Win Expectation Features

**Date added:** 2026-05-03
**Card:** 7.R — Pythagorean Win Expectation Features

## New columns added

Three net-new columns added to `feature_pregame_game_features` via the `mart_team_season_record` → `feature_pregame_team_features` pipeline:

| Column (game features) | Source | Description |
|---|---|---|
| `home_pythagorean_win_exp` | `h_tm.pythagorean_win_exp` | Home team Pythagorean win expectation pre-game (RS^1.83 / (RS^1.83 + RA^1.83)) |
| `away_pythagorean_win_exp` | `a_tm.pythagorean_win_exp` | Away team Pythagorean win expectation pre-game |
| `pythagorean_win_exp_diff` | derived | Home minus away (positive favors home) |

Formula: `pow(runs_scored_ytd::float, 1.83) / (pow(runs_scored_ytd::float, 1.83) + pow(runs_allowed_ytd::float, 1.83))`, exponent 1.83 (empirically validated for MLB).

NULL guard: `pythagorean_win_exp` is NULL when `games_played < 10` (early season). Imputed to 0.5 (no information) in ML preprocessing; `pythagorean_win_exp_diff` imputed to 0.0.

## Leakage note

`mart_team_season_record` is an SCD2 model joined at `record_date = game_date - 1` in `feature_pregame_team_features`. This join ensures that only pre-game YTD run totals are used — no leakage from the game being predicted.

## Hypothesis

Pythagorean win expectation regresses to true team quality faster than win-loss record because it is based on run differential, which has lower variance than binary W/L outcomes. Expected to carry incremental signal over `win_pct` early in the season, and to be informative as a market sanity-check signal year-round.

## Multicollinearity check (win_pct vs pythagorean_win_exp)

Expected Pearson r between `home_pythagorean_win_exp` and `home_win_pct`: ~0.7–0.85. Retain both columns if |r(pythagorean, win_pct)| < 0.85 (multicollinearity threshold). If |r| ≥ 0.85, prefer `pythagorean_win_exp` as it regresses to quality faster.

## Correlation analysis and CV impact

**Deferred to Card 7.MA (pre-7M batch retrain checkpoint).**

Per project cadence, model retrains are batched before Card 7.MA. Actual max |r| values for `home_pythagorean_win_exp`, `away_pythagorean_win_exp`, `pythagorean_win_exp_diff` against all three targets (`home_win`, `total_runs`, `run_differential`), retain/dropped status, Brier score delta, and mean h2h edge delta will be documented here after the 7.MA retrain.

Expected outcomes (hypothesis to verify at retrain):
- `pythagorean_win_exp_diff` should carry stronger signal vs `home_win` target than `home_win_pct - away_win_pct`, especially in the first 30 games of the season
- |r(pythagorean_win_exp_diff, home_win)| expected in range 0.08–0.15
- Both `home_pythagorean_win_exp` and `away_pythagorean_win_exp` should pass the r ≥ 0.02 correlation filter

---

# Feature Notes — Card 7.S: Starter Velocity Trend (Start-Count Window)

**Date added:** 2026-05-03  
**Card:** 7.S — Starter Velocity Trend Features

## New columns added

Two net-new columns surfaced in `feature_pregame_game_features` via `feature_pregame_starter_features`:

| Column (game features) | Source | Description |
|---|---|---|
| `home_starter_velo_delta_3start` | `h_st.velo_delta_3start` | Home starter: avg fastball velo last ≤3 starts minus season-avg fastball velo |
| `away_starter_velo_delta_3start` | `a_st.velo_delta_3start` | Away starter equivalent |

Intermediate column `avg_fastball_velo_3start` is computed in `feature_pregame_starter_features` but not exposed in the game-level feature store.

**Formula:**
```
avg_fastball_velo_3start = avg(avg_fastball_velo) over last ≤3 prior starts
                           where avg_fastball_velo is not null
velo_delta_3start = round(avg_fastball_velo_3start - avg_fastball_velo_std, 1)
```

`avg_fastball_velo` from `mart_starting_pitcher_game_log` is the per-start mean across FF/SI/FC pitch types (not max), so a single outlier pitch or Statcast pitch-tagging error cannot inflate the result. Averaging across ≤3 starts further smooths any remaining noise.

NULL guard: NULL when pitcher has no prior starts with valid fastball velo data. Imputed → 0.0 in ML preprocessing (no trend signal).

Expected range: −3.0 to +3.0 mph for ≥99% of rows.

## Why not a duplicate of fastball_velo_trend

`fastball_velo_trend` (7-day calendar window minus 30-day calendar window) and `velo_delta_3start` (start-count window) capture different signal:

- A 7-day window can span only 1 start or a 6-day rest; a 30-day window can include 4–6 starts depending on schedule density.
- `velo_delta_3start` uses exactly the 3 most recent outings regardless of days elapsed — more robust to IL returns, skipped starts, and 6-man rotations.

If |r(velo_delta_3start, fastball_velo_trend)| < 0.85, both columns can coexist in the model (complementary signal). If |r| ≥ 0.85, prefer the column with higher |r| against the target.

## Multicollinearity check (velo_delta_3start vs fastball_velo_trend)

Expected Pearson r between `home_starter_velo_delta_3start` and `home_starter_fastball_velo_trend`: ~0.5–0.75. The two windows overlap substantially when a pitcher throws on a regular schedule, but diverge meaningfully after IL stints or irregular rest. Retain both if |r| < 0.85; drop the weaker one if ≥ 0.85.

## Correlation analysis and CV impact

**Deferred to Card 7.MA (pre-7M batch retrain checkpoint).**

Per project cadence, model retrains are batched before Card 7.MA. Actual max |r| values for `home_starter_velo_delta_3start` and `away_starter_velo_delta_3start` against all three targets (`home_win`, `total_runs`, `run_differential`), retain/dropped status, measured |r(velo_delta_3start, fastball_velo_trend)| (multicollinear check), Brier score delta, and mean h2h edge delta will be documented here after the 7.MA retrain.

Expected outcomes (hypothesis to verify at retrain):
- Both columns should pass the r ≥ 0.02 correlation filter if they capture a real fatigue/injury signal
- |r(velo_delta_3start, fastball_velo_trend)| expected < 0.85 (confirming the start-count window adds incremental signal over the calendar window)
- Strongest signal expected against `total_runs` target (velocity drop correlates with elevated run scoring)

---

# Line Movement Features (Card 7.P3)

**Date added:** 2026-05-03
**Card:** 7.P3 — Line Movement Feature Engineering

## Source

`mart_odds_line_movement` via LEFT JOIN in `feature_pregame_game_features`.

**Bookmaker:** Bovada (hardcoded). The Card 7.P2 historical backfill used Bovada; the same
bookmaker is used for live 2026+ data to ensure consistent implied-probability scale across eras.
Future enhancement: make the bookmaker configurable via a dbt variable.

**Coverage:** 2021–2025 from `odds_snapshots_historical` (Card 7.P2 backfill); 2026+ from
`mart_odds_outcomes` filtered to `ingestion_ts < commence_time`.

## Columns

| Column in feature_pregame_game_features | Source in mart_odds_line_movement | Description | Null handling |
|---|---|---|---|
| `home_h2h_line_movement` | `h2h_line_movement` | pregame_home_win_prob − open_home_win_prob; positive = line moved toward home | Imputed 0.0 (no movement = no detectable sharp action) |
| `home_open_win_prob` | `open_home_win_prob` | Implied home win probability at market open | NULL left as-is (imputing 0.0 for a probability is meaningless) |
| `total_line_movement` | `total_line_movement` | pregame_total − open_total O/U; positive = total moved up | Imputed 0.0 |
| `open_total_line` | `open_total_line` | Opening O/U total | NULL left as-is |

## Expected null rates (post 7.P2 backfill)

- **2024–2025:** ~20% null for line movement (games with only 1 snapshot); ~35–40% null for
  totals columns (Bovada often omits totals from historical snapshots).
- **2021–2023:** null rate may be higher — API data retention is shallower for older seasons.
  Accept up to 50% null for pre-2022 data.
- **2026+:** null rate ~0% for h2h movement (live intraday snapshots); ~10–15% for totals
  (some games have no totals market).

## Assumption: imputing 0.0 for no movement

When only one snapshot is available (market open = market close), `h2h_line_movement` and
`total_line_movement` are NULL in `mart_odds_line_movement` and imputed to 0.0 in
`feature_pregame_game_features`. The rationale: zero movement conveys "no detectable sharp
action" — a meaningful signal. Imputing the mean or median would introduce leakage from other
games in the training set. This assumption should be revisited if these features contribute
negatively to model performance at Card 7.MA retrain.
