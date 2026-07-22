# NCAAF — Analytic Mart Inventory (the conformed dimensional model)

**Status:** v1.1 — produced by **NCAAF-P1.1** (2026-07-20). Every row count below is **observed on a
real build over the S3 Delta lake**, not estimated, and was **re-measured after the
`season_order_week` fix** — see the note below.
**✅ Box-verified 2026-07-20:** `sports_ncaaf_dbt_build_job` ran green on the EC2 box in **2m59s**
(run op ~3 min), reproducing these counts exactly (`rollup_ncaaf_team_week_asof` = 25,565;
`ncaaf_team_coaching_change` = 1,555). The runtime gate is CLOSED.

> ⚠️ **Provenance note (why v1.1).** v1.0 quoted 24,000 for the two week-grained rollups. That was
> a PRE-FIX measurement carried forward by mistake: it was taken before `season_order_week` existed,
> when the postseason still collapsed onto week 1. The fix adds the real postseason weeks (16, 17)
> to the spine, which adds exactly one as-of week per team-season — 1,565 rows — giving 25,565.
> The box run surfaced the discrepancy. **Lesson: re-measure after a fix; never carry a pre-fix
> number into the docs.** Every other figure here was re-audited against the post-fix build and
> was already correct.
**Parents:** `ncaaf_data_inventory.md` §8 (the 25 raw lake tables this is built from) ·
`../../baseball/baseball_data_mart_inventory.md` (the MLB analog) ·
`../../baseball/scd2_convention.md` (the SCD-2 convention mirrored here).
**Project:** `quant_sports_intel_models/sports_dbt` (dbt-duckdb; schemas `ncaaf_staging` /
`ncaaf_marts`). **Separate from MLB's Snowflake dbt on purpose** (`sport_data_platform.md` §16.1).
**Consumers:** P1.2 (team-strength), P1.2b (freshman priors), P1.3 (feature engineering),
P1A (the NFL feeder).

---

## 0. TL;DR — the five things to know before you use these marts

1. **`rollup_ncaaf_team_week_asof` is the pregame surface.** In-season team features come from it or
   from `rollup_ncaaf_team_week_opponent_adjusted`. **Never** from `rollup_ncaaf_team_season`, which
   contains the whole season including games that had not happened yet.
2. **🚨 `season_order_week`, never `week`.** CFBD restarts `week` at 1 for the postseason, so raw
   `week` sorts January's national championship before September's week 2. This is not theoretical:
   it was live in this model during development — 2024 Ohio State had **five** games at `week <= 1`
   (its opener plus four CFP games), and every as-of row from week 2 on was absorbing them.
3. **Opponent-adjust before comparing anything.** 136 teams, ~12 games, almost no schedule overlap.
   Raw efficiency mostly measures strength of schedule.
4. **The FBS filter is structural, not optional.** The lake lands ~3,800 games/season across all
   divisions; ~800 are FBS-vs-FBS. Every fact is restricted to `is_fbs_matchup`.
5. **NULL means unknown and must stay NULL.** Week-1 as-of rows, teams with no play coverage, and
   first-time head coaches all carry honest NULLs. Coalescing them to 0 tells a model something
   false.

---

## 1. Dimensions

| Mart | Grain | Rows | SCD-2 | Notes |
|---|---|---|---|---|
| `dim_ncaaf_conference` | conference | 11 | — | Lifespan + membership-size trace. Membership itself lives on `dim_ncaaf_team` (it drifts). `is_power_conference` is a coarse slicing label, not a strength measure. |
| `dim_ncaaf_team` | (team_id, version) | **293** (137 teams) | ✅ | Payload = team name, conference, conference division, classification. |
| `dim_ncaaf_player` | (player_id, version) | **~69.9k players** | ✅ | Payload = team, position. FBS-filtered *by that season's membership*. |
| `dim_ncaaf_game` | game_id | 28,053 | — | The spine. Carries `season_order_week`, the three-way FBS classification, venue, and (post-kickoff) result. |

### 1.1 Why `dim_ncaaf_team` is SCD-2 — realignment, verified

A type-1 dimension would retroactively report a 2021 Texas game as an SEC game. Observed versions:

| Team | v1 | v2 | v3 |
|---|---|---|---|
| Texas | Big 12 2014–2023 | **SEC 2024–** | |
| Oklahoma | Big 12 2014–2023 | **SEC 2024–** | |
| UCLA | Pac-12 2014–2021 | Pac-12 2022–2023 *(division change)* | **Big Ten 2024–** |
| BYU | FBS Independents 2014–2022 | **Big 12 2023–** | |
| Cincinnati | AAC 2014 | AAC East 2015–2021 → AAC 2022 | **Big 12 2023–** |

**Point-in-time lookup (the only correct join):**
```sql
join dim_ncaaf_team d
  on d.team = f.team          -- or d.team_id = f.team_id
 and f.season between d.valid_from_season and coalesce(d.valid_to_season, 9999)
```
Because the team NAME is in the payload, `(season, team-name)` is a sound key — which matters,
because `/games/players`, `/drives` and `/plays` carry **no teamId** at all.

⚠️ **Idaho has NO `is_current` row.** It left FBS after 2017. That is correct — it is not currently
an FBS team. Do not "fix" it by forcing one.

### 1.2 Why `dim_ncaaf_player` excludes `class_year` from the payload

Class year advances every season by construction. Measured on the real lake: **20,672** of 30,433
version breaks would be class-year-only vs **9,761** genuine team/position changes — 2:1 noise
burying the signal. A version here means **a real roster change** (a transfer or a position switch).
Class year is carried descriptively as `class_year_first` / `class_year_last`.

### 1.3 Validity is SEASON-grained, not timestamp-grained

A deliberate departure from MLB's `TIMESTAMP` `valid_from`/`valid_to`. The sources (CFBD
`/teams/fbs`, `/roster`) are once-a-season snapshots — there is no intra-season "as of 3pm" truth,
and faking timestamps would imply precision the data does not have. `record_hash`, the
change-detection rule, and `is_current ⇔ valid_to IS NULL` are the convention's, unchanged.

---

## 2. Facts — all FBS-filtered (`is_fbs_matchup`) + sport-tagged

| Mart | Grain | Rows | Sources conformed |
|---|---|---|---|
| `fact_ncaaf_team_game` | (game_id, team_id) | **18,124** (9,062 games × 2) | box line + CFBD advanced box + game context |
| `fact_ncaaf_player_game` | (game_id, player_id) | **539,152** | the long player-stat vocabulary, pivoted |
| `fact_ncaaf_drive` | drive_id | **213,954** | `/drives` + derived scoring-opportunity / points |
| `fact_ncaaf_play` | play_id | **1,550,367** | `/plays` + score state + garbage time |

**⚠️ Every fact here is POST-KICKOFF.** They describe games that were played. Nothing in them may be
read into a pregame row for the *same* game.

**Play subsets** (`fact_ncaaf_play`, for anyone computing their own splits):
all rows **1,550,367** → `is_scrimmage_play` **1,222,754** → also non-garbage **1,112,244**.

**Coverage honesty:** 18,032 of 18,124 team-games have a CFBD advanced row (99.5%);
`has_advanced_stats` flags the rest rather than letting NULL read as zero. `/plays` coverage has
genuine per-game holes (2014 Washington week 1 has **0** plays), so a team can have `games_played > 0`
and still have a NULL efficiency rating.

### 2.1 Definitions fixed ONCE (so no two consumers disagree)

| Definition | Where | Rule |
|---|---|---|
| **Success rate** | `stg_ncaaf_plays` | 1st down ≥ 50% of distance · 2nd ≥ 70% · 3rd/4th ≥ 100%. Observed on clean (garbage-excluded) scrimmage plays: **43.7%** (matches the CFB norm). |
| **Passing down** | `stg_ncaaf_plays` | 2nd & ≥8, or 3rd/4th & ≥5. |
| **Garbage time** | `fact_ncaaf_play` | Margin by quarter > 43 / 37 / 27 / 22. **8.8%** of plays. |
| **Scoring opportunity** | `fact_ncaaf_drive` | Drive reached the opponent's 40. Observed rate **49.1%**; **2.04** points/drive; **26.0%** three-and-out. |

**Garbage time is correctness, not hygiene.** Blowout snaps are backups against a prevent defense;
including them inflates the loser's efficiency and deflates the winner's. Plays are **flagged, never
dropped** — the rollups exclude them, anything wanting the full game still can.

---

## 3. Rollups

| Mart | Grain | Rows | Pregame-safe? |
|---|---|---|---|
| `rollup_ncaaf_team_season` | (season, team_id) | 1,565 | ⛔ **NO — not for its own season** |
| `rollup_ncaaf_team_week_asof` | (season, team_id, as_of_week) | **25,565** | ✅ **YES — this is the surface** |
| `rollup_ncaaf_team_week_opponent_adjusted` | (season, team_id, as_of_week) | 25,565 | ✅ YES |

### 3.1 The leakage contract

> A row for `as_of_week = W` aggregates ONLY games with `season_order_week < W`. Strictly less-than.

Enforced structurally by the join; asserted by three singular tests that run in the box job:

| Test | Asserts |
|---|---|
| `assert_asof_week_has_no_future_games` | **Date-based**: every contributing game was played strictly before its own week's first kickoff. |
| `assert_opponent_adjustment_is_point_in_time` | Each opponent's rating was read at the **same** `as_of_week`, not season-final. |
| `assert_season_order_week_is_monotone_in_date` | `season_order_week` orders a season the way the calendar does. |

**⚠️ Why the first test is date-based.** The obvious test — recompute `games_played` with
`week < as_of_week` and compare — is worthless: it re-uses the ordering the model used, so if the
*ordering* is wrong the filter is still satisfied and the test passes green. That is exactly what
happened here. The test goes around the ordering entirely and uses the clock.

### 3.2 The opponent adjustment

```
adj_off = raw_off + (league_avg_def_allowed − avg_def_allowed_by_opponents_faced)
adj_def = raw_def + (league_avg_off        − avg_off_by_opponents_faced)
```
Two passes: pass 1 against opponents' raw ratings, pass 2 against their pass-1 ratings (so "who did
your opponents play" enters). Everything — this team's rating, the opponent list, and each
opponent's rating — is read at the **same** `as_of_week`.

**Observed behaviour**: correlation with raw is 0.958 and the mean absolute
shift is 0.024 PPA against a raw SD of 0.104 — it moves ~23% of a standard deviation, meaningful but
not wild. The direction is right where it should be:

- **Indiana** (SOS +0.055, a soft schedule at that point) — offense adjusted **up** 0.354 → 0.422 but
  defense marked **down**; the famous 2024 "great record, weak schedule" case.
- **Army** (SOS −0.086) — adjusted **down** on both sides.
- **Ohio State** (SOS +0.115) — adjusted **up**, and finishes the season the #1 adjusted team.

Season-end 2024 adjusted top 5: **Ohio State, Notre Dame, Texas, Oregon, Ole Miss** — which is the
actual CFP result, from a model that never sees a ranking.

**Honesty flags:** `has_reliable_adjustment` (this team AND every opponent ≥3 games) and
`adjustment_applied` (false ⇒ adjusted values *are* the raw values — never a NULL that silently
drops the row from a feature join). Early-season adjustment is noise and says so.

---

## 4. Staging (the flattening layer)

15 models, all materialized as **tables**, not views — the delta_scan-stacking cure inherited from
NFL-N0.3: DuckDB's delta extension cannot serialize a `DeltaScan` operator inside a complex plan, so
a mart joining several staging views over `delta_scan` fails outright. Physical tables read each
Delta table once.

New in P1.1: `stg_ncaaf_teams`, `stg_ncaaf_game_team_stats`, `stg_ncaaf_game_player_stats`,
`stg_ncaaf_drives`, `stg_ncaaf_plays`, `stg_ncaaf_game_advanced`.

### 4.1 `stg_ncaaf_game_player_stats` stays LONG on purpose

Four chained UNNESTs (`teams → categories → types → athletes`) produce one row per
(game, player, category, stat_type) — **5.2M rows**. The stat vocabulary differs per category and
CFBD adds types over time (`kicking.TOT` appears 33 times in 12 seasons), so a pivot here would
silently drop anything not enumerated. `fact_ncaaf_player_game` pivots the modelled subset; the rest
stays reachable.

### 4.2 🧯 Two models are memory-pinned

`stg_ncaaf_game_player_stats` and `fact_ncaaf_play` pin `threads = 1` +
`preserve_insertion_order = false` (restored afterwards — they are connection-global). Both OOM a
4 GB / 4-thread DuckDB otherwise; single-threaded they complete in ~40s and ~5s. **Do not remove
these pins when the box gets more RAM** — the amplification scales with seasons ingested.

`stg_ncaaf_game_advanced` extracts the `offense`/`defense` sub-objects once per row; reaching into
the full document ~100× with `$.offense.standardDowns.ppa`-style paths re-parses the whole JSON per
column and OOM'd 4 GB on a 25k-row table.

---

## 5. Orchestration + gates

| Surface | What |
|---|---|
| **Box job** | `sports_ncaaf_dbt_build_job` (`pipeline/jobs/sports_dbt_job.py`) — builds the **whole** NCAAF DAG, P0.4's `ncaaf_team_roster_continuity` and P0.5's `ncaaf_team_coaching_change` included. |
| **Tiers** | `dbt run` = **HALT** → the 3 leakage gates = **HALT** → the rest of `dbt test` = **WARN-continue**. Leakage is carved out of the INC-6 WARN default on purpose: a pregame rollup absorbing post-kickoff data is a correctness emergency, and a warning nobody reads is how the postseason week-1 collision reached a shipped model. |
| **Serial staging** | Built one model at a time — the P0.5 fusion-segfault landmine *and* the measured OOM above. ~85s. |
| **CI** | `.github/workflows/sports_dbt_ci.yml` — offline parse + compile, an NCAAF-specific slice, the three leakage gates, and a non-empty-selector assertion (a selector matching nothing still exits 0 in dbt). |

**Observed clean-slate build:** staging 15 models / ~85s → marts 14 models / ~14s → 166 tests / ~14s.

### ⚠️ Known accepted nulls — RATCHETED, not waived (P0.3 `xref_college_nfl_players`)

`gsis_id` is NULL for **8 of 4,211** rows: drafted players who never took an NFL snap, for whom
nflverse issues no `gsis_id` (e.g. Bud Sasser, 2015 round 6 pick 201). These are legitimate nulls,
not match failures — P0.3's original `not_null` was simply wrong about its own data.

The test is now a **ratchet**: `warn_if: ">0"`, `error_if: ">8"`. The 8 known nulls warn; **a 9th
fails the build.** The count can only drift down silently — any growth means something new is
broken (a regression in the deterministic slot match, or a fresh draft class not yet on the field)
and must surface rather than blend into an accepted background level.

**Verified in both directions** (2026-07-20): at threshold 8 → `WARN` (`Got 8 results, configured
to warn if >0`); at a simulated threshold 7 → `ERROR` (`Got 8 results, configured to fail if >7`).

⚠️ **When this legitimately changes, raise the threshold DELIBERATELY in `_ncaaf_marts.yml` and say
why.** Do not delete the test, and do not bump it reflexively to whatever today's number is.

---

---

## 6. Column reference

Generated from `information_schema` on the **box-verified build** (2026-07-20), so this is what the
tables actually contain — not what the models were intended to contain. Repetitive metric families
are shown as a pattern row rather than enumerated 24 times; the pattern expands to every
combination listed.

**Conventions used throughout:** `sport` is on every row (always `'ncaaf'`). `*_key` /
`*_surrogate_key` are the grain contract (unique, not-null, tested). ⚠️ marks a column with a
semantic trap. ⛔ marks a POST-KICKOFF column that must not reach a pregame feature row.

### 6.1 `dim_ncaaf_conference` — 11 cols · grain: conference

| Column | Type | Notes |
|---|---|---|
| `sport` | VARCHAR | always `'ncaaf'` |
| `conference` | VARCHAR | the natural key |
| `conference_key` | VARCHAR | `ncaaf-<conference>` — grain contract (unique) |
| `first_season`, `last_season`, `latest_season` | BIGINT | observed lifespan |
| `n_teams_latest_season`, `min_teams`, `max_teams` | BIGINT | membership-size trace |
| `is_defunct` | BOOLEAN | last seen before the newest ingested season (folded / left FBS) |
| `is_power_conference` | BOOLEAN | ⚠️ coarse slicing label at CURRENT alignment, deliberately not season-varying. Not a strength measure — use the opponent-adjusted rollup. |

### 6.2 `dim_ncaaf_team` — 26 cols · grain: (team_id, version) · SCD-2

| Column | Type | Notes |
|---|---|---|
| `team_surrogate_key` | VARCHAR | `ncaaf-<team_id>-v<n>` — grain contract (unique, not-null) |
| `team_id` | BIGINT | CFBD team id — stable across versions |
| `version_number` | HUGEINT | 1-based; increments on a payload change or a membership gap |
| **`team`, `conference`, `conference_division`, `classification`** | VARCHAR | **the SCD-2 PAYLOAD** — a change in any opens a new version. `team` is in the payload so `(season, team-name)` is a sound join key for the name-only CFBD sources. |
| `is_fbs` | BOOLEAN | `classification = 'fbs'` |
| `valid_from_season` | BIGINT | INCLUSIVE lower bound |
| `valid_to_season` | BIGINT | INCLUSIVE upper bound; **NULL ⇔ `is_current`** |
| `is_current` | BOOLEAN | ⚠️ a team that LEFT FBS (Idaho, after 2017) correctly has NO current row |
| `record_hash` | VARCHAR | MD5 over the payload (`scd2_convention.md` formula; NULL → `''`) |
| `seasons_in_version` | BIGINT | span length |
| `mascot`, `abbreviation` | VARCHAR | descriptive, as of the version's last season |
| `venue_name/_city/_state/_timezone` | VARCHAR | descriptive — NOT payload (a renovation must not open a version) |
| `venue_latitude`, `venue_longitude`, `venue_elevation_m` | DOUBLE | travel / altitude features |
| `venue_capacity` | INTEGER | |
| `venue_is_dome`, `venue_is_grass` | BOOLEAN | |

### 6.3 `dim_ncaaf_player` — 24 cols · grain: (player_id, version) · SCD-2

| Column | Type | Notes |
|---|---|---|
| `player_surrogate_key` | VARCHAR | `ncaaf-<player_id>-v<n>` — grain contract (unique, not-null) |
| `player_id` | VARCHAR | CFBD athlete id (string, not numeric) |
| `version_number` | HUGEINT | increments on a REAL roster change only |
| **`team`, `position`** | VARCHAR | **the SCD-2 PAYLOAD** — a transfer or position switch opens a version |
| `team_id` | BIGINT | resolved point-in-time through `dim_ncaaf_team`'s SCD-2 range |
| `conference` | VARCHAR | the conference AS OF that version's seasons |
| `class_year_first`, `class_year_last` | INTEGER | ⚠️ descriptive, **deliberately NOT payload** — class advances every season, and hashing it made 20,672 of 30,433 version breaks class-only noise vs 9,761 real changes |
| `player_name`, `first_name`, `last_name` | VARCHAR | |
| `valid_from_season`, `valid_to_season`, `is_current`, `record_hash`, `seasons_in_version` | — | SCD-2 block, same semantics as `dim_ncaaf_team` |
| `is_post_change_version` | BOOLEAN | `version_number > 1` |
| `first_fbs_season`, `last_fbs_season`, `fbs_seasons`, `n_teams` | BIGINT | career context (constant across a player's versions) |
| `is_transfer_career` | BOOLEAN | appeared for >1 FBS team |

### 6.4 `dim_ncaaf_game` — 37 cols · grain: game_id

| Column | Type | Notes |
|---|---|---|
| `game_key`, `game_id` | VARCHAR / BIGINT | grain contract (both unique, not-null) |
| `season` | INTEGER | |
| `week` | INTEGER | ⚠️ **CFBD-native. NOT a season ordering** — postseason restarts at 1. Reporting only. |
| **`season_order_week`** | INTEGER | ⭐ **the ONLY safe season ordering.** Regular weeks as-is; postseason offset past the last regular week. Monotone in `game_date`. Every window/filter uses this. |
| `season_type`, `is_postseason` | VARCHAR / BOOLEAN | `is_postseason` = `season_type <> 'regular'` |
| `start_date`, `game_date` | TIMESTAMP / DATE | kickoff; `game_date` is what the date-based leakage gate uses |
| `home_team_id`, `home_team`, `home_conference`, `home_classification` | — | participants |
| `away_team_id`, `away_team`, `away_conference`, `away_classification` | — | participants |
| **`is_fbs_matchup`** | BOOLEAN | ⭐ BOTH sides FBS — **the modelling universe every fact filters on.** NULL-safe (unknown classification ⇒ false) |
| `is_fbs_involved` | BOOLEAN | either side FBS — the right universe for a team's RECORD |
| `is_conference_game`, `is_neutral_site` | BOOLEAN | |
| `venue_*` (8 cols) | — | ⚠️ **NULL on neutral sites by design** — attributing the home team's stadium to a bowl would be plainly wrong |
| `is_completed` | BOOLEAN | ⚠️ a scheduled-but-unplayed game has NULL points — never treat as 0–0 |
| ⛔ `home_points`, `away_points`, `total_points`, `home_margin`, `winning_team_id`, `is_tie` | — | POST-KICKOFF outcome |

### 6.5 `fact_ncaaf_team_game` — 101 cols · grain: (game_id, team_id) · ⛔ POST-KICKOFF

**Identity + context (18):** `team_game_key` (grain contract), `sport`, `game_id`, `team_id`,
`season`, `week`, `season_order_week`, `season_type`, `game_date`, `team`, `conference`, `is_home`,
`is_neutral_site`, `is_conference_game`, `is_postseason`, `opponent_team_id`, `opponent_team`,
`opponent_conference`.

**⛔ Result (5):** `is_completed`, `points_for`, `points_against`, `margin`, `is_win`
(NULL on a tie).

**Box line (27):** `first_downs`, `total_yards`, `net_passing_yards`, `rushing_yards`,
`rushing_attempts`, `rushing_tds`, `passing_tds`, `completions`, `pass_attempts`, `yards_per_pass`,
`yards_per_rush_attempt`, `third_down_conversions`, `third_down_attempts`,
`fourth_down_conversions`, `fourth_down_attempts`, `turnovers`, `fumbles_lost`,
`interceptions_thrown`, `passes_intercepted`, `sacks`, `tackles_for_loss`, `qb_hurries`,
`passes_deflected`, `penalties`, `penalty_yards`, `possession_seconds`, `kicking_points`.

**Derived rates (4)** — defined once here so no two consumers disagree: `third_down_rate`,
`fourth_down_rate`, `completion_rate`, `scrimmage_plays_box`.

**CFBD advanced (47):** `has_advanced_stats` (BOOLEAN — ⚠️ **check it**; 18,032 of 18,124 rows have
one, and a NULL must not read as zero), plus the `off_` / `def_` families below.
⚠️ **`def_*` is what THIS team's DEFENSE ALLOWED**, not the opponent's offense row.

| Family | Expands to |
|---|---|
| `{off,def}_{plays,drives,ppa,total_ppa,success_rate,explosiveness,power_success,stuff_rate,line_yards,second_level_yards,open_field_yards}` | 22 cols |
| `{off,def}_{standard_downs,passing_downs,rushing_plays,passing_plays}_{ppa,success_rate,explosiveness}` | 24 cols |

### 6.6 `fact_ncaaf_player_game` — 52 cols · grain: (game_id, player_id) · ⛔ POST-KICKOFF

**Identity + context (18):** `player_game_key` (grain contract), `sport`, `game_id`, `player_id`,
`season`, `week`, `season_order_week`, `season_type`, `game_date`, `player_name`, `team`, `team_id`
(⚠️ point-in-time resolved — `/games/players` carries no teamId), `conference`, `is_home`,
`opponent_team`, `is_neutral_site`, `is_conference_game`, `is_postseason`.

| Line | Columns |
|---|---|
| Passing | `completions`, `pass_attempts` (⚠️ split from the composite `C/ATT` string), `passing_yards`, `passing_tds`, `interceptions_thrown`, `passing_yards_per_attempt`, `qbr` |
| Rushing | `rushing_attempts`, `rushing_yards`, `rushing_tds`, `rushing_yards_per_carry`, `rushing_long` |
| Receiving | `receptions`, `receiving_yards`, `receiving_tds`, `receiving_yards_per_catch`, `receiving_long` |
| Defensive | `tackles_total`, `tackles_solo`, `sacks`, `tackles_for_loss`, `qb_hurries`, `passes_defended`, `defensive_tds` |
| Turnovers | `fumbles`, `fumbles_lost`, `fumbles_recovered`, `interceptions_caught`, `interception_return_yards`, `interception_return_tds` |
| Participation | `has_passing_line`, `has_rushing_line`, `has_receiving_line`, `has_defensive_line` |

⚠️ Stat values are DOUBLE because CFBD ships them as strings and they are `try_cast` — a
non-numeric stat becomes NULL rather than 0. ⚠️ Special teams (kicking / punting / returns) is
**not pivoted here** — it stays long in `stg_ncaaf_game_player_stats` (§7 gap 1).

### 6.7 `fact_ncaaf_drive` — 37 cols · grain: drive_id · ⛔ POST-KICKOFF

**Identity + context (16):** `drive_key` (grain contract), `sport`, `drive_id`, `game_id`,
`season`, `week`, `season_order_week`, `season_type`, `game_date`, `drive_number`, `offense_team`,
`offense_team_id`, `offense_conference`, `defense_team`, `defense_team_id`, `defense_conference`,
`is_home_offense`.

| Column | Type | Notes |
|---|---|---|
| `drive_result` | VARCHAR | CFBD's label (`TD`, `PUNT`, `END OF HALF`, …) |
| `is_scoring_drive`, `plays`, `yards`, `elapsed_seconds` | — | drive shape |
| `start_period`, `end_period`, `start_yardline`, `start_yards_to_goal`, `end_yardline`, `end_yards_to_goal` | INTEGER | field position |
| **`is_scoring_opportunity`** | BOOLEAN | ⭐ reached the opponent's 40 — the points-per-opportunity DENOMINATOR. Observed 49.1%. |
| **`points_scored`** | INTEGER | ⚠️ from the OFFENSE's score delta, so a defensive / special-teams score is NOT credited to the offense. Observed 2.04/drive. |
| `is_three_and_out`, `is_explosive_drive`, `yards_per_play` | — | tails + efficiency. 26.0% three-and-out. |
| `start_offense_score`, `start_defense_score`, `end_offense_score`, `end_defense_score` | INTEGER | score state |

### 6.8 `fact_ncaaf_play` — 41 cols · grain: play_id · ⛔ POST-KICKOFF

**Identity + context (19):** `play_key` (grain contract), `sport`, `play_id`, `game_id`,
`drive_id`, `season`, `week`, `season_order_week`, `season_type`, `game_date`, `drive_number`,
`play_number`, `offense_team`, `offense_team_id`, `offense_conference`, `defense_team`,
`defense_team_id`, `defense_conference`, `is_home_offense`.

| Column | Type | Notes |
|---|---|---|
| `period`, `clock_seconds_remaining`, `down`, `distance`, `yardline`, `yards_to_goal`, `yards_gained` | INTEGER | situation |
| `offense_score`, `defense_score`, `offense_score_margin` | INTEGER | score state |
| `is_red_zone` | BOOLEAN | `yards_to_goal <= 20` |
| `play_type`, `play_text` | VARCHAR | CFBD labels |
| `is_scrimmage_play`, `is_pass_play`, `is_rush_play`, `is_passing_down` | BOOLEAN | classification — defined ONCE in `stg_ncaaf_plays` |
| **`is_successful_play`** | BOOLEAN | ⭐ the ONE success definition (50/70/100% of distance by down). 43.7% on clean scrimmage plays. |
| `ppa` | DOUBLE | CFBD's EPA-analog. ⚠️ **NULL on 23.5% of ALL rows but only 3.0% of SCRIMMAGE plays** — CFBD does not score kickoffs/punts/PATs. Averaging `ppa` over the unfiltered fact silently mixes those in; always filter `is_scrimmage_play` first (the rollups do). |
| **`is_garbage_time`** | BOOLEAN | ⭐ margin by quarter > 43/37/27/22. **8.8% of plays.** Flagged, never dropped — the rollups exclude it. |
| `wallclock` | VARCHAR | ⚠️ ISO string, NOT a timestamp (INC-23 — the reader casts at the use-site) |

### 6.9 `rollup_ncaaf_team_season` — 57 cols · grain: (season, team_id) · ⛔ NOT PREGAME-SAFE

`team_season_key` (grain contract), `sport`, `season`, `team_id`, `team`, `conference`, then:

| Group | Columns |
|---|---|
| Record | `games_played`, `wins`, `losses`, `win_pct` |
| Scoring | `points_for_per_game`, `points_against_per_game`, `margin_per_game` |
| Box per-game | `total_yards_per_game`, `rushing_yards_per_game`, `passing_yards_per_game`, `turnovers_per_game`, `third_down_rate`, `fourth_down_rate`, `completion_rate`, `possession_seconds_per_game`, `penalties_per_game`, `penalty_yards_per_game` |
| Advanced (play-weighted) | `{off,def}_{ppa,success_rate,explosiveness,line_yards,stuff_rate,power_success}`, `off_plays_per_game`, `off_plays_total`, `def_plays_total` |
| Drive quality | `drives`, `points_per_drive`, `scoring_opportunity_rate`, `three_and_out_rate`, `explosive_drive_rate`, `drive_yards_per_play`, `avg_start_yards_to_goal` |
| ⭐ Garbage-excluded | `{off,def}_clean_{plays,ppa,success_rate,passing_down_success_rate,pass_ppa,rush_ppa}` |

### 6.10 `rollup_ncaaf_team_week_asof` — 47 cols · grain: (season, team_id, as_of_week) · ✅ PREGAME

| Column | Type | Notes |
|---|---|---|
| `team_week_key` | VARCHAR | `<season>-<team_id>-w<as_of_week>` — grain contract (unique, not-null) |
| **`as_of_week`** | INTEGER | ⭐ **this is `season_order_week`, never CFBD's raw `week`.** The row is pregame FOR this week. |
| `games_played` | BIGINT | strictly-prior completed games. **0 at `as_of_week` 1** by construction |
| `has_sufficient_sample` | BOOLEAN | `games_played >= 3` — shrink toward a prior below this |
| `last_game_order_week` | INTEGER | most recent contributing game |
| Record / scoring | `wins`, `losses`, `win_pct`, `points_for_per_game`, `points_against_per_game`, `margin_per_game` |
| Box | `total_yards_per_game`, `rushing_yards_per_game`, `passing_yards_per_game`, `turnovers_per_game`, `third_down_rate`, `completion_rate`, `possession_seconds_per_game`, `penalty_yards_per_game` |
| Advanced | `{off,def}_{ppa,success_rate,explosiveness,line_yards,stuff_rate}`, `off_plays_per_game` |
| Drive | `drives`, `points_per_drive`, `scoring_opportunity_rate`, `three_and_out_rate`, `explosive_drive_rate`, `avg_start_yards_to_goal` |
| ⭐ Garbage-excluded | `{off,def}_clean_{plays,ppa,success_rate}` — the cleanest strength read, and what the opponent adjustment consumes |

⚠️ **Every metric is NULL when `games_played = 0`** (week 1, and any team before its opener). That
NULL is the honest "unknown" — **do not coalesce it to 0**, which would tell a model the team
scores zero points per game.

### 6.11 `rollup_ncaaf_team_week_opponent_adjusted` — 29 cols · grain: (season, team_id, as_of_week) · ✅ PREGAME

| Column | Type | Notes |
|---|---|---|
| `team_week_key`, `as_of_week`, `games_played`, `has_sufficient_sample` | — | same grain + sample semantics as §6.10 |
| `raw_off_ppa`, `raw_def_ppa`, `raw_off_success_rate`, `raw_def_success_rate`, `raw_points_for_per_game`, `raw_points_against_per_game` | DOUBLE | the unadjusted inputs, carried so raw and adjusted are always comparable |
| **`adj_off_ppa`, `adj_def_ppa`, `adj_off_success_rate`, `adj_def_success_rate`, `adj_points_for_per_game`, `adj_points_against_per_game`** | DOUBLE | ⭐ 2-pass schedule-adjusted. Falls back pass-2 → pass-1 → raw. |
| **`adj_net_ppa`** | DOUBLE | ⭐ `adj_off_ppa − adj_def_ppa` — the single-number team-strength read |
| `opponents_counted`, `min_opponent_games` | BIGINT | adjustment support. `min_opponent_games` is what the point-in-time leakage gate recomputes. |
| `sos_opponent_off_ppa`, `sos_opponent_def_ppa`, `sos_opponent_net_ppa` | DOUBLE | ⭐ strength of schedule as a first-class output (the adjustment's residual) |
| `adjustment_applied` | BOOLEAN | ⚠️ **false ⇒ the adjusted columns ARE the raw columns** — never a NULL that silently drops the row from a feature join |
| `has_reliable_adjustment` | BOOLEAN | this team AND every opponent had ≥3 games. Early-season rows are honestly `false`. |

### 6.12 Inherited NCAAF marts (built by this job, owned by earlier stories)

These predate P1.1 but the box job materializes them, so they belong in this inventory.

| Mart | Story | Grain | Rows | Columns |
|---|---|---|---|---|
| `ncaaf_team_roster_continuity` | P0.4 | (season, team) | 1,555 | 32 — returning production (`returning_{ppa,pass_ppa,rec_ppa,rush_ppa}_pct`, `returning_usage`), roster overlap (`roster_size`, `roster_returning_players`, `roster_continuity_pct`, `roster_retention_pct`), portal flux (`portal_{in,out,net}_count`, `*_stars_sum`, `*_rating_sum`, `*_blue_chip`, `portal_out_uncommitted`), talent (`team_talent`, `team_talent_prev`, `team_talent_yoy_delta`). ⚠️ **`portal_data_covered`** — pre-2021 portal zeros are UNKNOWN, not "no churn". |
| `ncaaf_team_coaching_change` | P0.5 | (season, team) | 1,555 | 25 — `head_coach`, `hc_tenure_years`, `is_first_year_at_school`, `hc_change_from_prev` (⚠️ NULL at the 2014 floor), `hc_midseason_change`, `n_coaches_in_season`, and the ⭐ prior track record `hc_prior_{seasons,sp_overall_avg,sp_offense_avg,sp_defense_avg,wins,losses}` + `hc_recent_sp_{overall,offense,defense}`. `is_first_time_hc` / `is_hc_history_censored` mark honest NULLs. |
| `xref_college_nfl_players` | P0.3 | gsis_id | 4,211 | 37 — the draft-slot crosswalk + combine measurables + ⛔ `target_*` POST-draft NFL outcomes (the P1A modelling target, **never features**). ⚠️ `gsis_id` NULL on 8 rows — see §5. |

### 6.13 Staging column counts (the flattening layer)

Full column lists live in `models/ncaaf/staging/_ncaaf_staging.yml`; these are the shapes.

| Model | Cols | Grain |
|---|---|---|
| `stg_ncaaf_teams` ⭐new | 19 | (season, team_id) |
| `stg_ncaaf_games` | 20 | game_id |
| `stg_ncaaf_game_team_stats` ⭐new | 49 | (game_id, team_id) — pivoted from CFBD's long string categories |
| `stg_ncaaf_game_player_stats` ⭐new | 13 | (game_id, player_id, category, stat_type) — **stays LONG**, 5.19M rows |
| `stg_ncaaf_drives` ⭐new | 26 | drive_id |
| `stg_ncaaf_plays` ⭐new | 33 | play_id |
| `stg_ncaaf_game_advanced` ⭐new | 59 | (game_id, team) |
| `stg_ncaaf_roster` | 8 | (season, player_id) |
| `stg_ncaaf_coaches` | 14 | (coach, team, season) |
| `stg_ncaaf_returning_production` | 16 | (season, team) |
| `stg_ncaaf_transfer_portal`, `stg_ncaaf_talent`, `stg_ncaaf_cfbd_draft_picks`, `stg_nflverse_draft_picks`, `stg_ncaaf_odds` | — | P0.3–P0.5 sources |


### 6.13 `ncaaf_team_strength_week` — 30 cols · grain: (season, team_id, as_of_week) · ✅ PREGAME · ⭐ P1.2

The **team-strength posterior**: how many points better than an average FBS team each team was
BEFORE `as_of_week` kicked off, with honest uncertainty. Hierarchical partial pooling, **team
nested in conference**, so a thin or lopsided sample is shrunk toward its conference mean instead
of trusted at face value. Grain matches `rollup_ncaaf_team_week_asof` exactly → join on
`team_week_key`.

⚠️ **NOT COMPUTED IN dbt.** This model is a read-only view over the parquet written by
`football/ncaaf/models/run_team_strength.py` to `ncaaf/derived/team_strength_week` in the lake.
The estimator is an iterative mixed-effects fit (~200 leakage-safe refits, each with a
variance-component optimization) and is not expressible in SQL.

🚨 **BUILD ORDER (the INC-25 lesson).** `dbt run` (P1.1 marts) → `run_team_strength.py` →
`dbt run --select ncaaf_team_strength_week`. Building it in the same pass that produces its inputs
serves the PREVIOUS run's strengths — a silent one-slate staleness. Tagged `ncaaf_p1_2` so it is
opt-in and cannot break a build before the script has ever run.

🚨 **SIGN CONVENTION — the one thing consumers get wrong.** `strength_offense` and
`strength_defense` are BOTH higher-is-better (defense = points **PREVENTED**). Net strength is
their **SUM**:  `margin = (O_home + D_home) - (O_away + D_away)`. Subtracting them returns ~0 for
every team, because a good team is good at both and the two large positive components cancel. Use
`strength_margin`.

| Group | Columns |
|---|---|
| Grain | `sport`, `season`, `team_id`, `team`, `conference`, `as_of_week`, `team_week_key` |
| Sample | `games_in_window`, `has_sufficient_sample` |
| ⭐ Feature | `strength_margin`, `strength_margin_sd` |
| Decomposition (sums to `strength_margin` exactly) | `strength_conference_component` (the pooling level), `strength_covariate_component` (what the pre-season covariates say), `strength_team_component` (what this season's games add) |
| Covariate attribution | `covariate_component_carryover`, `covariate_component_talent`, `covariate_component_roster_flux`, `covariate_component_coaching` |
| Scoring split (for P1.4's totals leg) | `strength_offense`, `strength_offense_sd`, `strength_defense`, `strength_defense_sd`, `league_base_points` |
| Fit provenance | `home_field_advantage`, `residual_sigma`, `tau_team`, `tau_conference`, `hyper_seasons`, `hyper_n_prior_seasons`, `hyper_n_games`, `model_version` |

**Leakage contract.** A row for `as_of_week = W` is fit only on games with
`season_order_week < W` — strictly, and never on raw `week`. The covariate coefficients, the
home-field advantage and the variance components come from **strictly prior seasons** and are then
held fixed. **2014 is NOT emitted**: it is the seed that bootstraps the first hyperparameter fit
and gives 2015 its prior-season covariate, so every emitted row has out-of-sample hyperparameters.
Gated by `assert_team_strength_is_point_in_time`, which checks count parity AND a DATE-based clock
condition (a week-based test would re-use the very ordering it is meant to police — the P1.1 trap).

**⚠️ NULLs differ from the rollups on purpose.** `strength_margin` is **never NULL**, including at
week 1 where `games_in_window = 0`. A rollup of nothing is unknown and must stay NULL; a posterior
with no data is the **prior** — here the conference level plus the pre-season covariates — carried
with an honestly large `strength_margin_sd`. That is the entire point of partial pooling, and it is
why this surface can price a week-1 game that `rollup_ncaaf_team_week_asof` cannot.

**⚠️ The first emitted season (2015) is thinly calibrated** — one prior season of hyperparameter
data instead of the full lookback. Disclosed per row via `hyper_n_prior_seasons` / `hyper_n_games`
so P1.3/P1.4 can down-weight or drop it.

**Observed behaviour on the real 2014–2025 build** (see
`ablation_results/ncaaf_p1_2_team_strength.md`): posterior sd decays monotonically from ~6.7 pts at
week 1 to ~2.7 by season's end; 2024's final top three (Ohio State, Notre Dame, Texas) reproduces
the actual CFP semifinal field with **no ranking input**; walk-forward MAE vs realized margin is
~13.1 pts against ~15.7 for a home-field-only baseline. ⚠️ That is accuracy against REALITY, not
against a market — no edge is claimed, and P1.4 is what tests this feature against a closing line.

---

### 6.14 P1.2b freshman-projection marts (the recruit→college MLE)

Three marts land with **NCAAF-P1.2b**. They project a TRUE FRESHMAN's first-college-season
production from their recruiting rating (a player with no snaps has no rollup features — the
recruiting rating is the only pre-arrival signal), leakage-safe, position-specific.

| Mart | Grain | What | Tag |
|---|---|---|---|
| `ncaaf_recruit_production_pairs` | (player_id, arrival_season) | dbt-native substrate: a bridged recruit + their first-FBS-season box production (the LABEL). ~8,373 pairs, 2014–2025. | (in default build) |
| `ncaaf_freshman_priors` | (player_id, arrival_season) | ⭐ the per-recruit prior: `projected_production_z` + `_sd`. View over `ncaaf/derived/freshman_priors`. | `ncaaf_p1_2b` |
| `ncaaf_team_freshman_prior` | (season, team) | ⭐ the **P1.3 join contract** — the class's projected freshman contribution, broadcast to every `as_of_week`. | `ncaaf_p1_2b` |

- **⭐ THE BRIDGE = `roster.recruit_ids ↔ recruiting_players.recruit_id`** (the recruiting RECORD
  id), NOT `athleteId` (7 matches in 12 seasons — the data inventory was wrong; corrected). 60,883
  unnested matches → 8,373 distinct bridged freshmen.
- **ARRIVAL = the player's first FBS roster season** (not the recruiting class year — they agree
  ~90% of the time; the observed first FBS season absorbs redshirt/grayshirt lag honestly).
- **The model is a §0.5 bake-off** (partial-pooling via `hierarchical.py` REUSED / stratified-OLS /
  GBM / position-mean null), leave-one-CLASS-out expanding-window CV, PBO/DSR, oracle-floor.
  Not in dbt — `models/run_freshman_projection.py`; **INC-25 build order** (P1.1 marts + pairs mart
  → script → the two views). ⚠️ **`projected_production_z_sd` is PARAMETER uncertainty** (relative
  confidence — recalibrate to price). ⚠️ **OL/ST have `box_production_available = false`** (a
  rating-only prior; a lineman logs no stat line). ⚠️ **NULL production stays NULL**, never 0.

---

## 7. Open gaps carried into P1.2 / P1.3

1. **Special teams is thin.** Kicking/punting live in the long player-stat table but are not pivoted
   into `fact_ncaaf_player_game`. Add if a P1.3 ablation wants them.
2. **No venue for neutral-site games** — deliberately NULL rather than wrongly attributing the home
   team's stadium to a bowl. If travel/altitude features need them, a neutral-venue table is a
   precursor.
3. **`box_advanced` (lake table #8) is not staged** — it overlaps `game_advanced`, which is already
   the modelling grain. Stage it only if a specific field is missing.
4. **Opponent adjustment is 2-pass, unweighted per opponent.** ✅ **Partly addressed by P1.2**,
   which is an INDEPENDENT route to opponent-adjusted strength (a full hierarchical solve rather
   than 2 passes) — §6.13. The two are deliberately NOT fused: keeping them independent lets P1.3
   compare them instead of making one depend on the other. The 2-pass rollup remains as-is.
5. **2014 is the floor** for everything player-advanced (`ncaaf_data_inventory.md` §2.7), so
   season-over-season priors do not exist for 2014. P1.2 consumes 2014 as an un-emitted seed and
   starts emitting at 2015 (§6.13).
