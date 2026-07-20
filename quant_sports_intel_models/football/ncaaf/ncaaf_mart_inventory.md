# NCAAF — Analytic Mart Inventory (the conformed dimensional model)

**Status:** v1.0 — produced by **NCAAF-P1.1** (2026-07-20). Every row count below is **observed on a
real build over the S3 Delta lake**, not estimated.
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

**Coverage honesty:** 18,032 of 18,124 team-games have a CFBD advanced row (99.5%);
`has_advanced_stats` flags the rest rather than letting NULL read as zero. `/plays` coverage has
genuine per-game holes (2014 Washington week 1 has **0** plays), so a team can have `games_played > 0`
and still have a NULL efficiency rating.

### 2.1 Definitions fixed ONCE (so no two consumers disagree)

| Definition | Where | Rule |
|---|---|---|
| **Success rate** | `stg_ncaaf_plays` | 1st down ≥ 50% of distance · 2nd ≥ 70% · 3rd/4th ≥ 100%. Observed on clean scrimmage plays: **43.5%** (matches the CFB norm). |
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
| `rollup_ncaaf_team_week_asof` | (season, team_id, as_of_week) | **24,000** | ✅ **YES — this is the surface** |
| `rollup_ncaaf_team_week_opponent_adjusted` | (season, team_id, as_of_week) | 24,000 | ✅ YES |

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

**Observed behaviour** (2024, `as_of_week = 10`): correlation with raw is 0.95 and the mean absolute
shift is 0.027 PPA against a raw SD of 0.107 — it moves ~25% of a standard deviation, meaningful but
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

## 6. Open gaps carried into P1.2 / P1.3

1. **Special teams is thin.** Kicking/punting live in the long player-stat table but are not pivoted
   into `fact_ncaaf_player_game`. Add if a P1.3 ablation wants them.
2. **No venue for neutral-site games** — deliberately NULL rather than wrongly attributing the home
   team's stadium to a bowl. If travel/altitude features need them, a neutral-venue table is a
   precursor.
3. **`box_advanced` (lake table #8) is not staged** — it overlaps `game_advanced`, which is already
   the modelling grain. Stage it only if a specific field is missing.
4. **Opponent adjustment is 2-pass, unweighted per opponent.** A full iterative solve or a
   play-count-weighted opponent average is a possible P1.2 refinement; the residual movement after
   pass 2 is small relative to ≤12-game noise.
5. **2014 is the floor** for everything player-advanced (`ncaaf_data_inventory.md` §2.7), so
   season-over-season priors do not exist for 2014.
