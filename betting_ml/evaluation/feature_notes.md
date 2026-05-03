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
