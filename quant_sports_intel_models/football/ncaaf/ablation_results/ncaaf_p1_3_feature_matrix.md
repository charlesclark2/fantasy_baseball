# NCAAF-P1.3 — the pregame feature matrix (`feature_ncaaf_pregame_matrix`)

**Generated:** 2026-07-22T04:47:58.319054+00:00
**Shape:** 9,086 FBS-vs-FBS games (2014–2025) × 200 columns — 174 home_/away_ feature columns across 14 families, 6 POST-KICKOFF `label_*` targets.

> ⚠️ **This is a leakage-safe FEATURE matrix, not an edge claim.** Every `home_*`/`away_*` column is snapshot AS OF that game's own kickoff (as_of_week = its `season_order_week`); `label_*` is the POST-KICKOFF target P1.4 predicts and must NEVER be fed as a feature. `best_alpha = 0` holds — whether any of this beats a closing line is P1.4's question under full §0.5 deflation. NULL = unknown and is kept NULL; P1.4's learners handle missingness.

## 1. Gates (all HALT-tier)

- ✅ grain is 1-row-per-game — no join fanned out (9,086 games, unique)
- ✅ no games dropped — matrix == dim_ncaaf_game FBS universe (9,086)
- ✅ 6 label_* target columns present + prefixed (never a feature)
- ✅ DATE-based leakage gate PASSES on the real build (18,172 sides, 0 violations)
- ✅ leakage gate PROVEN to fail on a tampered/back-dated row (2 violations raised)

## 2. Per-family coverage (% non-null, pooled over both sides, per season) — banner A

A family reading ~0% where it should be present is a silently-dead join (the F2/INC-31 class) and must be caught HERE, not in P1.4. A LEGITIMATELY-empty cell is expected and labelled below — read the table, do not just scan for green:

- **strength (P1.2)** is NULL for **2014** (P1.2 emits 2015+) and thin at each season's week 1 only in `_sd` terms — the point estimate is a preseason posterior, never NULL.
- **portal_flux (P0.4)** is a real 0 (not NULL) from **2021** on; pre-2021 the portal feed does not exist (`portal_data_covered = false`) — do not read pre-2021 portal as 'no churn'.
- **efficiency / opp_adj / drive / pace / qb** are NULL at each team's **week 1** and for teams with no play coverage — the honest 'no games yet' unknown.
- **travel/altitude** is NULL on **neutral sites** by design (venue geography is not attributed to a neutral game — §7 gap 2) and wherever a venue lat/long is missing.

| family                    |   2014 |   2015 |   2016 |   2017 |   2018 |   2019 |   2020 |   2021 |   2022 |   2023 |   2024 |   2025 |
|:--------------------------|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|
| coaching (P0.5)           |     98 |     99 |    100 |     98 |     99 |    100 |    100 |     99 |     99 |     98 |     99 |     98 |
| drive_quality             |     91 |     92 |     91 |     91 |     91 |     92 |     88 |     91 |     91 |     91 |     91 |     91 |
| efficiency_opp_adj (P1.1) |     91 |     92 |     91 |     91 |     91 |     92 |     88 |     91 |     91 |     91 |     91 |     91 |
| efficiency_raw (P1.1)     |     91 |     92 |     91 |     91 |     91 |     92 |     88 |     91 |     91 |     91 |     91 |     91 |
| freshman_prior (P1.2b)    |      0 |     99 |     99 |     99 |     99 |     99 |    100 |     98 |    100 |     99 |     99 |     96 |
| line_trench               |     91 |     92 |     91 |     91 |     91 |     92 |     88 |     91 |     91 |     91 |     91 |     91 |
| pace_style                |     91 |     92 |     91 |     91 |     91 |     92 |     88 |     91 |     91 |     91 |     91 |     91 |
| portal_flux (P0.4)        |     98 |     99 |    100 |     98 |     99 |    100 |    100 |     99 |     99 |     98 |     99 |     98 |
| qb_continuity             |     91 |     91 |     91 |     91 |     91 |     92 |     88 |     91 |     91 |     91 |     91 |     91 |
| rest                      |     95 |     95 |     95 |     94 |     94 |     94 |     89 |     94 |     94 |     94 |     95 |     94 |
| roster_continuity (P0.4)  |     98 |     99 |    100 |     98 |     99 |    100 |    100 |     99 |     99 |     98 |     99 |     98 |
| strength (P1.2)           |      0 |    100 |    100 |    100 |    100 |    100 |     96 |    100 |    100 |    100 |    100 |    100 |
| talent (P0.4)             |      0 |     99 |    100 |     98 |     99 |    100 |    100 |     99 |     99 |     98 |     99 |     97 |
| travel/altitude           |     86 |     87 |     86 |     87 |     86 |     87 |     88 |     87 |     87 |     87 |     86 |     87 |

## 3. The families + their sources / grain / as-of semantics

| Family | Representative cols | Source mart | Join grain | As-of |
|---|---|---|---|---|
| Team strength | `{home,away}_strength_margin`, `_offense`, `_defense`, `_sd` | `ncaaf_team_strength_week` (P1.2) | (season, team_id, as_of_week) **1:1** | kickoff week |
| Efficiency (raw) | `{home,away}_off_ppa`, `_success_rate`, `_explosiveness`, `_clean_*` | `rollup_ncaaf_team_week_asof` (P1.1) | (season, team_id, as_of_week) **1:1** | kickoff week |
| Efficiency (opp-adj) | `{home,away}_adj_net_ppa`, `_adj_off/def_*`, `_sos_opponent_net_ppa` | `rollup_ncaaf_team_week_opponent_adjusted` (P1.1) | (season, team_id, as_of_week) **1:1** | kickoff week |
| Pace / style | `{home,away}_off_plays_per_game`, `_seconds_per_play`, `_possession_seconds_per_game` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Line / trench (UNIT proxies) | `{home,away}_off/def_line_yards`, `_off/def_stuff_rate` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Drive quality | `{home,away}_points_per_drive`, `_scoring_opportunity_rate`, `_three_and_out_rate` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Roster continuity / portal / talent | `{home,away}_returning_ppa_pct`, `_roster_continuity_pct`, `_portal_net_count`, `_team_talent` | `ncaaf_team_roster_continuity` (P0.4) | (season, team) **BROADCAST** | pre-season |
| Freshman prior | `{home,away}_freshman_proj_production`, `_top_proj_production`, `_avg_rating`, `_blue_chip_count` | `ncaaf_team_freshman_prior` (P1.2b) | (season, team) **BROADCAST** | pre-season |
| Coaching (HC-only) | `{home,away}_hc_tenure_years`, `_hc_change_from_prev`, `_hc_prior_sp_*` | `ncaaf_team_coaching_change` (P0.5) | (season, team) **BROADCAST** | pre-season |
| QB continuity | `{home,away}_qb_starts_prior`, `_qb_distinct_starters_prior`, `_qb_starter_changed_recent`, `_qb_trailing_ypa/qbr` | `fact_ncaaf_player_game` (derived) | per matchup side, prior starts only | strictly prior games |
| Situational | `is_neutral_site`, `is_conference_game`, `{home,away}_rest_days`, `season_order_week` | `dim_ncaaf_game` + schedule | game-level | kickoff |
| Environment (travel/altitude) | `away_travel_km`, `away_altitude_change_m`, `game_venue_elevation_m`, `game_venue_is_dome/grass` | `dim_ncaaf_team` venue geo | game-level, non-neutral | kickoff |

## 4. Honest scope notes (what is NOT in the matrix, and why)

- **QB has no injury flag** — college football has no mandated injury report and P0.1 established no injury source, so the QB block is the DERIVABLE half only: starter continuity + a trailing efficiency proxy from strictly-prior starts. Not an availability signal.
- **Coaching is HEAD-COACH-only** — OC/DC coordinators have no free CFBD endpoint (P0.5 deferred them, gated like NIL-$). No `is_rivalry` — no confirmed CFBD field / maintained pair list was available, so it is dropped rather than guessed (banner (3b)).
- **Line/trench is UNIT-level** — individual-OL production is the confirmed PFF-only gap; sack-rate-allowed / DL-havoc are not in the rollup (a §7 refinement if a P1.4 ablation wants them).
- **Travel DISTANCE is included (non-neutral) — a deliberate, verified departure from the P1.1-update banner's 'drop travel/altitude'.** That banner predates confirming `venue_latitude`/`venue_longitude` are in fact staged on `stg_ncaaf_teams` → travel/altitude ARE buildable for the ~non-neutral majority, so they ship coverage-flagged for P1.4 to ablate. Neutral-site venue geography stays NULL (§7 gap 2 — not attributed).
- **Uncertainty columns (`_strength_margin_sd`) are PARAMETER uncertainty** — relative confidence only, ~1.5× too tight to price directly. P1.4 recalibrates (the E13.6 pattern).
- **NULL is kept NULL, never imputed to 0** — week-1, no-coverage, first-time HC, pre-2021 portal, 2014 strength. The imputation choice belongs to P1.4's learners, not the matrix.

