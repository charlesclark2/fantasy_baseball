# NFL — Data Inventory (the master data file)

**Status:** v1.0 — produced by **NFL-N0.1** (2026-07-17). **Ground-truthed against LIVE nflverse release Parquet + The Odds API**, not docs. Supersedes the v0.1 reconstructed-from-stale-Snowflake draft.
**Parents:** `nfl_roadmap.md` §3 (the data wishlist this resolves) · `nfl_guide.md` (the brownfield port plan) · `../../sport_data_platform.md` (the lakehouse to instantiate) · `../../multi_sport_roadmap.md` §4 (the feeder).
**Consumers:** N0.2 (scaffold + backfill) + N0.3 (port the dbt IP) + N0.4 (Odds/injuries) start from the locked source set in §7.

> **How this was verified:** every ✅ below is backed by a real sample pull executed on 2026-07-17 —
> DuckDB `read_parquet('https://github.com/nflverse/nflverse-data/releases/download/<tag>/<asset>.parquet')`
> (25 assets, schema + row counts + season coverage observed), and `https://api.the-odds-api.com/v4`
> (`ODDS_API_KEY` in `.env`, live NFL odds + a historical in-season snapshot + a historical event-props snapshot).
> Row counts, field lists, and coverage windows are **observed, not documented.** The NCAAF feeder (P0.3) already
> reads three of these assets in production, so the nflverse read path is proven twice over.

---

## 0. TL;DR — the six decisions

1. **The entire NFL data stack is FREE and re-pullable via nflverse release Parquet** — every one of the 25 assets we need read live via DuckDB `read_parquet` over the public GitHub release URL (0.4–0.6s each, footer-only for schema). **No `nfl_data_py`** (abandoned — §1 landmine). The old `FOOTBALL_DATA` Snowflake stack is reference-for-logic only; we re-pull fresh, we do not migrate stale rows.
2. **⭐ NFL gets FREE exactly the advanced tracking data NCAAF gates behind PFF.** CPOE/air-yards, time-to-throw, WR separation, YAC-over-expected, RB rush-yards-over-expected + yards-after-contact, DB coverage (completion% / passer-rating allowed), pressures, and **snap counts (all positions)** are all live and free via **Next Gen Stats + PFR advanced + PBP-participation + the nflverse weekly stats** (§4). This is NFL's structural advantage over NCAAF and the reason NFL leans props/fantasy, not head-on edge.
3. **The Odds API fully covers NFL and the props surface is DEEP** (unlike NCAAF's thin, marquee-only props). `americanfootball_nfl` is active with **75 games already priced for 2026, 11 US books incl. Bovada** ⭐. A historical in-season event snapshot proved **pass/rush/reception yards + TDs + receptions + anytime-TD across up to 7 books incl. Bovada, with alternate-line depth** — even on a non-marquee game. This is a real prop-pricing surface (Phase-2 E5 analog).
4. **The current season is LIVE.** `stats_player_week`, `snap_counts`, `injuries`, `pbp` all carry **2025 through week 22** (REG 1–18 + postseason 19–22, i.e. the full 2025 season incl. Super Bowl); `rosters`/`depth_charts`/`weekly_rosters` already have a 2026 preseason placeholder. Freshness is a non-issue — nflverse updates within ~24h in-season.
5. **The NFL feeder is already SOLVED (P0.3).** `draft_picks` (12,927 rows, 1980–2026) + `combine` (8,968, 2000–2026) + `players` (25,033) read here; the college↔NFL xref keys on the **draft slot `(season, overall pick)`** at 99.7% — no ID join needed. N0.1 re-verifies the reads; the crosswalk logic lives in `../ncaaf/feeder/xref.py`.
6. **Cost = $0 new.** nflverse free; the Odds API is the existing sub (**~97.8k requests remaining this period**, observed; bulk `/odds` = 3 credits/pull). No CFBD-Patreon-style spend — NFL is cheaper than NCAAF.

---

## 1. Source register

| Source | Auth | Status | Cost | Role |
|---|---|---|---|---|
| **nflverse release Parquet** `github.com/nflverse/nflverse-data/releases` | none (public release assets) | ✅ live (25/25 assets read) | $0 | The whole player/team/PBP/advanced/roster/feeder stack |
| **The Odds API v4** | `ODDS_API_KEY` (in `.env`) | ✅ live | existing sub (~97.8k req remaining) | NFL game lines + **deep props** + scores + historical (2020+ CLV) |
| **Snowflake `FOOTBALL_DATA`** (old `jaffle_shop` dbt) | — | 🗄️ reference only | — | The existing dbt-model IP to PORT (N0.3); **not** re-homed as data |
| PFF | — | ⛔ not needed | — | NFL's advanced data is free via NGS/PFR ⇒ PFF is not a Phase-0 buy (unlike NCAAF) |

### URL pattern (all nflverse reads)
`https://github.com/nflverse/nflverse-data/releases/download/<TAG>/<ASSET>.parquet`
Season-partitioned assets are `<ASSET>_YYYY.parquet` (e.g. `stats_player/stats_player_week_2025.parquet`). **HTTP has no glob** — the ingest enumerates seasons and reads one URL per year (mirror the NCAAF `ingest/` per-season loop).

### ⚠️ Landmines found while probing (carry into N0.2)

- **🐍 `nfl_data_py` is abandoned** — it pins `pandas==1.5.3` and fails to build on py3.12 (the NCAAF-P0.1 + `sport_data_platform.md` finding). **Do NOT depend on it.** Read the release Parquet directly with DuckDB — dependency-free, lakehouse-native, already proven by the NCAAF feeder. `sport_data_platform.md §4/§10` still names `nfl_data_py`; that guidance is **stale**.
- **🔤 nflverse column names differ BETWEEN tables — ground every one live.** The `players` table uses **`rookie_season` / `draft_pick` / `draft_round`**, but `rosters` / `weekly_rosters` use **`rookie_year` / `draft_number` / `entry_year` / `draft_club`** for the same concepts. The P0.3 xref note ("`entry_year`/`draft_number` were wrong = `rookie_season`/`draft_pick`") is correct **for `players`** but the *opposite* is true for `rosters`. ⇒ never assume a column name across assets; `DESCRIBE` each on first ingest (the field lists in §2 are the observed truth).
- **💥 NaN-float → NULL cure.** nflverse numeric columns land as float64 with `NaN` for missing (combine `forty`, PFR rates, etc.). A naive `try_cast('NaN' as double)` yields a **non-null NaN**, so an `is not null` presence flag over-counts. Collapse `NaN → NULL` (`xref._num()` is the reference: `case when isnan(x) then null else x end`). This bit the feeder's `has_forty` (81.8% vs the true 65.7%).
- **📅 season vs "week 22".** nflverse `week` runs REG 1–18 then postseason 19–22 (WC 19, DIV 20, CONF 21, SB 22). `season_type` (`REG`/`POST`) disambiguates. Filter on it, don't assume `week ≤ 18`.
- **🧩 two overlapping "player stats" releases.** The legacy nflfastR `player_stats` (tag `player_stats`, 53 cols, **caps at 2024**) is superseded by the newer nflverse `stats_player` (tag `stats_player`, **145 cols, through 2025**, adds CPOE/air-yards/target-share/WOPR natively). **Use `stats_player`** (`stats_player_week_YYYY`) as the weekly player fact — it's fresher and richer. Same story for `stats_team` vs any legacy team-stats.
- **🏷️ Odds API: props + alt markets are the EVENT endpoint only.** Player props (`player_pass_yds` etc.), `alternate_spreads/totals`, `team_totals` are **not** on the bulk `/odds` endpoint (it returns `422 INVALID_MARKET`) — they come from `/events/{id}/odds`. Live props are thin **off-season** (8 weeks out we saw only `player_anytime_td` on 2 books); the honest proof of depth is the **historical** in-season event snapshot (§3).

---

## 2. nflverse assets that deliver (all read live, 2026-07-17)

**Grain legend:** 🏟️ game · 👥 team · 🧍 player · ▶️ play · 🗓️ season · wk = week

### 2.1 Core player + team performance (the fact backbone)

| # | Asset (tag/file) | Grain | Coverage | Rows (sample) | Key fields (observed) |
|---|---|---|---|---|---|
| `stats_player` `stats_player_week_YYYY` | 🧍wk | **1999–2025** (wk22) | 19,421 (2025) | player_id, gsis-joinable, season/week/season_type, team/opponent_team; **passing:** completions/attempts/passing_yards/tds/interceptions, sacks_suffered, **passing_air_yards, passing_yards_after_catch, passing_epa, `passing_cpoe`**, pacr; **rushing:** carries/rushing_yards/tds, rushing_epa, rushing_first_downs; **receiving:** receptions/targets/receiving_yards/tds, receiving_air_yards, receiving_yac, **`target_share`, `air_yards_share`, `wopr`, racr**, receiving_epa; **def block** (sacks, qb_hits, tackles, TFL, INT, pass_defended, FF); kicking/punting; **fantasy_points, fantasy_points_ppr** (145 cols) |
| `stats_player` `stats_player_reg_YYYY` / `_post` | 🧍🗓️ | 1999–2025 | 1,997 (2025 reg) | season rollup of the above |
| `stats_team` `stats_team_week_YYYY` | 👥wk | 1999–2025 | 570 (2025) | team-week mirror of the player block (133 cols) — team totals, EPA, CPOE, def block, FG/punt detail |

### 2.2 Rosters, depth, snaps, schedules (the dimensions)

| Asset (tag/file) | Grain | Coverage | Rows | Key fields |
|---|---|---|---|---|
| `rosters` `roster_YYYY` | 🧍🗓️ | **1920–2026** | 3,216 (2024) | season/team/position/depth_chart_position, full_name, gsis_id, **cross-IDs** (espn_id, sportradar_id, pff_id, pfr_id, yahoo_id, sleeper_id, esb_id, smart_id), college, years_exp, ngs_position, **entry_year, rookie_year, draft_club, draft_number** |
| `weekly_rosters` `roster_weekly_YYYY` | 🧍wk | **2002–2026** | 46,579 (2024) | same 36 cols as rosters, per week (who was actually on the roster that week — the point-in-time roster) |
| `depth_charts` `depth_charts_YYYY` | 🧍wk | **2001–2026** | 37,312 (2024) | season/week, club_code, depth_team, position, depth_position, formation, gsis_id, full_name |
| `snap_counts` `snap_counts_YYYY` | 🧍🏟️ | **2012–2025** | 26,615 (2024) | game_id, player, pfr_player_id, position, team/opponent, **offense_snaps/offense_pct, defense_snaps/defense_pct, st_snaps/st_pct** — ⭐ the all-position usage NCAAF has no free equivalent for |
| `schedules` `games` | 🏟️ | 1999–2026 | 7,548 | game_id, season/week/game_type, gameday/gametime, teams+scores, result, total, **betting: away/home_moneyline, spread_line, away/home_spread_odds, total_line, over/under_odds** (free consensus cross-check), **context: roof, surface, temp, wind, div_game, rest**, away/home_qb_id+name, coaches, referee, stadium; **cross-IDs: pfr, pff, espn, ftn, gsis, old_game_id** (the game-key rosetta) |

### 2.3 ⭐ Next Gen Stats — the tracking advanced data (FREE; NCAAF's PFF gap)

Single-file per discipline (all seasons in one asset; filter by `season`). NGS coverage begins **2016** (tracking era).

| Asset (tag `nextgen_stats`) | Grain | Rows | Key fields (observed) |
|---|---|---|---|
| `ngs_passing` | 🧍wk+season | 5,933 | **avg_time_to_throw**, avg_completed_air_yards, **avg_intended_air_yards (aDOT)**, avg_air_yards_differential, **aggressiveness**, avg_air_yards_to_sticks, **expected_completion_percentage, completion_percentage_above_expectation (CPOE)**, max_air_distance, passer_rating, player_gsis_id |
| `ngs_rushing` | 🧍wk+season | 6,059 | **efficiency**, percent_attempts_gte_eight_defenders, **avg_time_to_los**, rush_attempts/yards/tds, **expected_rush_yards, rush_yards_over_expected (RYOE), rush_yards_over_expected_per_att, rush_pct_over_expected**, player_gsis_id |
| `ngs_receiving` | 🧍wk+season | 14,731 | **avg_cushion, avg_separation**, avg_intended_air_yards, **percent_share_of_intended_air_yards**, receptions/targets/catch_percentage, **avg_yac, avg_expected_yac, avg_yac_above_expectation**, player_gsis_id |

### 2.4 PFR advanced (FREE; NCAAF's PFF gap for coverage + pressure + broken tackles)

Tag `pfr_advstats`; both `advstats_week_<disc>_YYYY` (game grain) and `advstats_season_<disc>_YYYY`. Coverage **2018–2025**. `<disc>` ∈ {pass, rec, rush, def}. Keyed `pfr_player_id` + `game_id`/`pfr_game_id`.

| Asset | Grain | Rows (2024) | Key fields |
|---|---|---|---|
| `advstats_week_pass` | 🧍🏟️ | 697 | passing_bad_throws/bad_throw_pct, **times_sacked, times_blitzed, times_hurried, times_hit, times_pressured/times_pressured_pct**, passing_drops/drop_pct |
| `advstats_week_rush` | 🧍🏟️ | 2,359 | **rushing_yards_before_contact(_avg), rushing_yards_after_contact(_avg), rushing_broken_tackles**, receiving_broken_tackles, carries |
| `advstats_week_rec` | 🧍🏟️ | 4,453 | rushing/receiving_broken_tackles, **passing_drops/drop_pct, receiving_drop/drop_pct, receiving_int, receiving_rat** |
| `advstats_week_def` | 🧍🏟️ | 7,992 | **def_targets, def_completions_allowed, def_completion_pct, def_yards_allowed(_per_cmp/_per_tgt), def_receiving_td_allowed, def_passer_rating_allowed, def_adot, def_yards_after_catch**, def_pressures, def_sacks, **def_missed_tackles/missed_tackle_pct**, def_times_blitzed/hurried/hitqb — ⭐ DB-in-coverage stats NCAAF has **only** via PFF |

### 2.5 Play-by-play + participation + charting (the raw material)

| Asset | Grain | Coverage | Rows | Key fields |
|---|---|---|---|---|
| `pbp` `play_by_play_YYYY` (nflfastR) | ▶️ | **1999–2025** | 49,492 (2024) | **372 cols** — the full nflfastR play table: epa, wpa, air_yards, yards_after_catch, cpoe, success, down/distance/yardline, play_type, personnel context, player IDs (passer/rusher/receiver), win-prob, xpass, etc. The base for any per-play derived feature |
| `pbp_participation` `pbp_participation_YYYY` | ▶️ | **2016–2025** | 45,919 (2024) | **offense_formation, offense_personnel, defenders_in_box, defense_personnel, number_of_pass_rushers, players_on_play, ngs_air_yards, time_to_throw, was_pressure, route, defense_man_zone_type, defense_coverage_type** — ⭐ per-play personnel + coverage + route (NCAAF has none of this free) |
| `ftn_charting` `ftn_charting_YYYY` | ▶️ | **2022–2025** | 48,031 (2024) | is_no_huddle, is_motion, **is_play_action, is_screen_pass, is_rpo**, is_qb_out_of_pocket, is_interception_worthy, is_throw_away, read_thrown, **is_catchable_ball, is_contested_ball, is_created_reception, is_drop**, is_qb_sneak, n_blitzers, n_pass_rushers, is_qb_fault_sack |

### 2.6 QBR, feeder, injuries, reference

| Asset (tag) | Grain | Coverage | Rows | Key fields |
|---|---|---|---|---|
| `espn_data` `qbr_week_level` | 🧍wk | 2006+ | 10,709 | qbr_total, qbr_raw, epa_total, pts_added, qb_plays, pass/run/sack/penalty splits, rank, player_id, opp |
| `espn_data` `qbr_season_level` | 🧍🗓️ | 2006+ | 1,523 | season QBR rollup |
| `injuries` `injuries_YYYY` | 🧍wk | **2009–2025** | 6,215 (2024) | gsis_id, team, week, position, **report_primary/secondary_injury, report_status** (Out/Doubtful/Questionable), **practice_primary/secondary_injury, practice_status**, date_modified — ⭐ the net-new high-leverage NFL status feed (CLV moves on this) |
| `draft_picks` `draft_picks` | 🧍 | **1980–2026** | 12,927 | season/round/pick(overall), gsis_id, pfr_player_id, **cfb_player_id** (feeder bridge), college, position + **career outcomes** (car_av, w_av, dr_av, games, seasons_started, probowls, allpro, hof, career pass/rush/rec lines) = the feeder TARGET |
| `combine` `combine` | 🧍 | **2000–2026** | 8,968 | forty/vertical/bench/broad_jump/cone/shuttle, ht/wt, **cfb_id** (feeder slug), pfr_id, pos, school, draft_ovr (incl. invited-but-undrafted) |
| `players` `players` | 🧍 | all-time | 25,033 | the ID universe: gsis_id, esb_id, nfl_id, pfr_id, **pff_id**, otc_id, espn_id, smart_id; position(_group), ngs_position, college, **rookie_season, draft_year/round/pick**, status, years_of_experience |
| `officials` `officials` | 🏟️🧍 | — | (single) | game officiating crew (referee tendency features) |
| `contracts` `historical_contracts` · `players_components` `otc_players` | 🧍 | — | — | OverTheCap salary/contract (bonus — value/roster-construction context) |

---

## 3. The Odds API — NFL ✅ (existing sub; no new cost)

| Item | Verified (2026-07-17) |
|---|---|
| Sport keys | `americanfootball_nfl` (active), `americanfootball_nfl_preseason` (active), `americanfootball_nfl_super_bowl_winner` (outrights) |
| Live coverage | **75 games priced for the 2026 season** (opener 2026-09-10), **11 US books** |
| Books | fanduel, draftkings, **bovada** ⭐, betmgm, **williamhill_us** (= Caesars-US), fanatics, betrivers, betus, mybookieag, betonlineag, lowvig |
| Core markets | `h2h`, `spreads`, `totals` — bulk `/odds` endpoint (3 credits/pull) |
| Alt/derivative | `alternate_spreads`, `alternate_totals`, `team_totals` — ⚠️ **event endpoint only** (bulk `/odds` = `422 INVALID_MARKET`) |
| **Player props** | ✅ **DEEP** (unlike NCAAF). Historical in-season event snapshot (2024-11-03, Saints @ Panthers — a *non*-marquee game) posted: `player_anytime_td` (7 books incl. Bovada, 18–26 outcomes), `player_reception_yds` (7 books incl. Bovada; betrivers 114 = alt lines), `player_receptions` (7 incl. Bovada), `player_rush_yds` (7 incl. Bovada), `player_pass_yds` + `player_pass_tds` (6 books). Also available: `player_pass_completions/attempts/interceptions`, `player_rush_attempts`, `player_reception_tds`, `player_1st_td`/`last_td`. **This is a real prop surface** — the E5 analog is viable for NFL. |
| Scores (settlement) | ✅ `/scores` (`daysFrom` ≤ 3) — 75 rows |
| **Historical depth** | ✅ **2020 → present** (2020-11-01 ✅ 25 ev, 2021-11-01 ✅ 13 ev; 2020 is the Odds API v4 floor across sports, per NCAAF-P0.1). ⇒ **CLV/backtest window = 2020–2025 (6 seasons).** nflverse `schedules` carries a free consensus line back to 1999 as a thinner cross-check. |
| Credit cost | bulk `/odds` = 3 credits; historical `/odds` = 10/market; historical **event** props ≈ 10–40/market. Observed remaining: **~97,769 requests** this period — ample. |

**Why it matters:** NFL props are deep across many books (the opposite of NCAAF's thin, marquee-only props) → a genuine props/CLV surface for Phase-2. Bovada (our target book) posts props on the yards/receptions/anytime-TD markets. The off-season caveat: live props are sparse in July (no book prices 8 weeks out); the historical snapshot is the honest proof they exist in-season.

---

## 4. ⭐ The by-position advanced coverage map — NFL's structural edge over NCAAF

The headline finding: **the tracking/charting data NCAAF gates behind PFF ($$/UI-only) is FREE for NFL** via NGS + PFR + PBP-participation + the nflverse weekly stats. Legend: ✅ = free/live-verified · 🟡 = derivable by us from PBP · 💰 = PFF-only (a genuine remaining gap) · ⛔ = no source.

### QB
| Wishlist item | NFL verdict | Source | NCAAF was… |
|---|---|---|---|
| Box: cmp/att/yds/TD/INT/sacks | ✅ | `stats_player_week` passing block | ✅ |
| QBR, EPA/play, success | ✅ | `qbr_week_level`; `stats_player_week.passing_epa`; `pbp` | ✅ |
| **CPOE** | ✅ **FREE** | `stats_player_week.passing_cpoe`; NGS `completion_percentage_above_expectation`; `pbp.cpoe` | 🟡→💰 (PFF) |
| **Air yards / aDOT** | ✅ **FREE** | `stats_player_week.passing_air_yards`; NGS `avg_intended_air_yards`, `avg_air_yards_to_sticks` | 💰 (PFF) |
| **Time-to-throw** | ✅ **FREE** | NGS `avg_time_to_throw`; `pbp_participation.time_to_throw` | 💰 (PFF) |
| Aggressiveness, bad-throw%, under pressure | ✅ | NGS `aggressiveness`; PFR `passing_bad_throw_pct`, `times_pressured/hurried/hit/blitzed` | 💰 (PFF) |
| Big-time-throw / turnover-worthy (subjective grade) | 💰 | PFF only | 💰 |

### RB
| Wishlist item | NFL verdict | Source | NCAAF was… |
|---|---|---|---|
| Box: rush/rec lines, fumbles | ✅ | `stats_player_week` rushing/receiving | ✅ |
| EPA/rush, usage/snap share | ✅ | `stats_player_week.rushing_epa`; **`snap_counts`** (all-position); `pbp` | ✅ / ⛔ snaps |
| **Rush yards over expected (RYOE)** | ✅ **FREE** | NGS rushing `rush_yards_over_expected(_per_att)`, `efficiency`, `avg_time_to_los`, box-count faced | 💰 |
| **Yards-after-contact, yards-before-contact** | ✅ **FREE** | PFR `rushing_yards_after_contact(_avg)`, `_before_contact` | 💰 (PFF) |
| **Forced/broken missed tackles** | ✅ **FREE** | PFR `rushing_broken_tackles`, `receiving_broken_tackles` | 💰 (PFF) |
| YPRR (routes run) | 🟡→💰 | routes appear in `pbp_participation.route` (2016+) → derivable; a true PFF YPRR grade is 💰 | 💰 |

### WR / TE
| Wishlist item | NFL verdict | Source | NCAAF was… |
|---|---|---|---|
| Box: rec/yds/TD, **targets ⇒ target share** | ✅ | `stats_player_week` receiving + **`target_share`, `air_yards_share`, `wopr`, racr** (native!) | ✅ (targets via PBP only) |
| EPA/target, usage share | ✅ | `stats_player_week.receiving_epa`; `snap_counts` | ✅ |
| **aDOT (intended air yards)** | ✅ **FREE** | NGS `avg_intended_air_yards`, `percent_share_of_intended_air_yards` | 💰 (P0.1 corrected NCAAF's aDOT to 💰) |
| **Separation, cushion** | ✅ **FREE** | NGS `avg_separation`, `avg_cushion` | 💰 (PFF) |
| **YAC-over-expected** | ✅ **FREE** | NGS `avg_yac_above_expectation`, `avg_expected_yac` | 💰 (PFF) |
| **Contested-catch / created reception / drop** | ✅ **FREE** | FTN `is_contested_ball`, `is_created_reception`, `is_drop`; PFR `receiving_drop_pct` | 💰 (NCAAF: drop only a proxy) |
| YPRR | 🟡→💰 | routes in `pbp_participation`; PFF YPRR grade is 💰 | 💰 |

### OL — the one shared gap (individual grade only)
| Wishlist item | NFL verdict | Source | NCAAF was… |
|---|---|---|---|
| **OL snap counts / who was on the field** | ✅ **FREE** | **`snap_counts`** (offense_snaps by lineman), `pbp_participation.offense_personnel/formation` | ⛔ (no college snaps) |
| Unit-level pass-pro / run-block proxies | ✅ | PFR `times_sacked/pressured/hurried` (QB/team), `pbp` line-yards analogs, `stats_team_week` | ✅ (unit only) |
| **Individual OL pass-block/run-block GRADE + pressures-allowed-per-lineman** | 💰 | **PFF only** — nflverse has no per-lineman grade (an OL surfaces individually only when penalised or on `snap_counts`) | 💰 |
⇒ Even for NFL, **individual OL grades remain the one PFF-gated reach** — but NFL is far better off than NCAAF (it at least has per-lineman snap counts + personnel-package context free).

### Defense
| Wishlist item | NFL verdict | Source | NCAAF was… |
|---|---|---|---|
| Team: havoc/pressure/EPA-allowed | ✅ | `stats_team_week` def block; `pbp`; PFR def | ✅ |
| Individual box: tackles, TFL, sacks, QB hits, INT, PBU, FF | ✅ | `stats_player_week` def block (`def_sacks`, `def_qb_hits`, `def_tackles_*`, `def_interceptions`, `def_pass_defended`) | ✅ |
| **Pressure rate / pass-rush win** | ✅ **FREE** | PFR `def_pressures`, `def_times_blitzed/hurried/hitqb`; snap_counts denom | 🟡→💰 |
| **Coverage: completion% / passer-rating / yards allowed in coverage, def aDOT** | ✅ **FREE** | PFR def `def_completion_pct`, `def_passer_rating_allowed`, `def_yards_allowed_per_tgt`, `def_adot`, `def_receiving_td_allowed` | 💰 (NCAAF: **no defender-in-coverage attribution** free) |
| **Missed-tackle rate** | ✅ **FREE** | PFR `def_missed_tackles`, `def_missed_tackle_pct` | 💰 (PFF) |
| **Man/zone + coverage type per play** | ✅ **FREE** | `pbp_participation.defense_man_zone_type`, `defense_coverage_type`, `was_pressure` | 💰 |
| **Snap counts (all positions)** | ✅ **FREE** | `snap_counts.defense_pct` | ⛔ (NCAAF: no free college snaps) |

**Bottom line:** the coverage table that is a wall of 💰 for NCAAF is a wall of ✅ for NFL. The *only* remaining NFL PFF gap is **individual OL grading** and PFF's proprietary subjective 0–100 grades (which we don't need). NFL's data richness is exactly why the roadmap points NFL at props/CLV/fantasy rather than head-on edge — the market prices this same free advanced data efficiently.

---

## 5. The NFL feeder (draft/combine/players) — already solved by P0.3

The three feeder assets read live here (`draft_picks` 12,927, `combine` 8,968, `players` 25,033). The college↔NFL crosswalk is **NOT an ID join** — it keys on the deterministic draft slot `(season, overall pick)` between CFBD `/draft/picks` and nflverse `draft_picks`, resolving 99.7% of 2015–25 picks to a `gsis_id`; combine measurables attach nflverse-internally on the `cfb_player_id` slug. The full recipe + the anti-cartesian guards live in `../ncaaf/feeder/xref.py` (P0.3, box-verified 2026-07-17). N0.1's job was only to re-confirm the NFL-side reads — done. The feeder TARGET (career AV / games / pro-bowls) is already carried in `draft_picks`.

---

## 6. Existing dbt marts to PORT (N0.3) — the brownfield IP map

The old `FOOTBALL_DATA` `refined` layer (from `~/Documents/machine_learning/football/jaffle_shop/`) is the model IP to re-home onto `sports_dbt` over the fresh lake. Map (source asset → old mart → port target):

| Old `refined` mart | Grain | Rebuilds from (new lake asset) | Port note |
|---|---|---|---|
| `dim_player` | player | `players` + `rosters` | dimension; keep gsis_id PK |
| `dim_player_role` (SCD-2) | player × window | `weekly_rosters` + `depth_charts` | SCD-2 via dbt incremental (feedback: SCD-2 use dbt) |
| `team_week_calendar`, `week_clock_bounds` | team×wk / wk | `schedules` | calendar spine |
| `fct_player_week` | player × wk | **`stats_player_week`** | the core fact — richer now (145 cols vs old) |
| `sat_passing/rushing/receiving_ngs_weekly` | player × wk | `ngs_passing/rushing/receiving` | join on gsis_id + season/week |
| `sat_snap_counts_weekly` | player × wk | `snap_counts` | join on pfr_player_id |
| `mart_opportunity_player_week` | player × wk | `stats_player_week` (target_share/wopr) + snaps | usage/volume driver |
| `mart_efficiency_player_week` | player × wk | `stats_player_week` (epa) + PFR advstats | efficiency |
| `mart_player_season` | player × season | `stats_player_reg` + season NGS/PFR | rollup |
| `mart_projections_preseason` | player | above + `schedules` pace | **fantasy head-start** (Phase-1) |
| `dim_nfl_betting` | game | `schedules` (free lines) + **Odds API** (per-book) | **betting head-start**; add Odds API for Bovada/CLV |

⇒ N0.3 ports the SQL (the IP); only the source/target adapter changes (Snowflake `raw` → DuckDB `read_parquet` over S3/Delta). Net-new marts (Odds/props/injuries) are N0.4.

---

## 7. 🔒 Locked Phase-0 source set (what N0.2 + N0.3 + N0.4 build against)

**Backfill window: 2016–2025** for the full advanced stack (NGS + pbp_participation floor = 2016; PFR = 2018, FTN = 2022 — thinner at the edges but present). Team/box/PBP/roster/schedule features extend to **1999**; draft/combine/players are all-time. **Current season 2025 is live through wk22.**
**Lake layout** (per `sport_data_platform.md §3`; reuse the `credence-sports-lakehouse` bucket, `nfl/` prefix): `s3://<bucket>/nfl/raw/<source>/season=YYYY/…` (Delta-native, mirror the NCAAF `ingest/s3io.py`).

| # | Lake table | nflverse asset (or Odds API) | Grain | Partition | Cadence |
|---|---|---|---|---|---|
| 1 | `stats_player_week` | `stats_player/stats_player_week_YYYY` | 🧍wk | season | weekly |
| 2 | `stats_player_season` | `stats_player/stats_player_reg_YYYY` (+`_post`) | 🧍🗓️ | season | weekly |
| 3 | `stats_team_week` | `stats_team/stats_team_week_YYYY` | 👥wk | season | weekly |
| 4 | `rosters` | `rosters/roster_YYYY` | 🧍🗓️ | season | weekly |
| 5 | `weekly_rosters` | `weekly_rosters/roster_weekly_YYYY` | 🧍wk | season | weekly |
| 6 | `depth_charts` | `depth_charts/depth_charts_YYYY` | 🧍wk | season | weekly |
| 7 | `snap_counts` | `snap_counts/snap_counts_YYYY` | 🧍🏟️ | season | weekly |
| 8 | `schedules` | `schedules/games` | 🏟️ | single (rewrite) | weekly |
| 9 | `ngs_passing` / `ngs_rushing` / `ngs_receiving` | `nextgen_stats/ngs_*` | 🧍wk | single (filter season) | weekly |
| 10 | `pfr_advstats_week_{pass,rec,rush,def}` | `pfr_advstats/advstats_week_*_YYYY` | 🧍🏟️ | season | weekly |
| 11 | `pfr_advstats_season_{…}` | `pfr_advstats/advstats_season_*_YYYY` | 🧍🗓️ | season | weekly |
| 12 | `pbp` | `pbp/play_by_play_YYYY` | ▶️ | season | weekly |
| 13 | `pbp_participation` | `pbp_participation/pbp_participation_YYYY` | ▶️ | season | weekly |
| 14 | `ftn_charting` | `ftn_charting/ftn_charting_YYYY` | ▶️ | season | weekly |
| 15 | `qbr_week` / `qbr_season` | `espn_data/qbr_{week,season}_level` | 🧍 | single | weekly |
| 16 | `injuries` | `injuries/injuries_YYYY` | 🧍wk | season | **weekly in-season (N0.4)** |
| 17 | `nflverse_draft_picks` | `draft_picks/draft_picks` | 🧍 | single | seasonal (feeder) |
| 18 | `nflverse_combine` | `combine/combine` | 🧍 | single | seasonal (feeder) |
| 19 | `nflverse_players` | `players/players` | 🧍 | single | seasonal (feeder/ID) |
| 20 | `officials` | `officials/officials` | 🏟️🧍 | single | seasonal (optional) |
| 21 | `odds_nfl` | Odds API `/odds` (h2h, spreads, totals) | 🏟️ | season/week | **intraday in-season (N0.4)** |
| 22 | `odds_nfl_props` | Odds API event endpoint (pass/rush/rec yds+tds, receptions, anytime_td) | 🏟️🧍 | season/week | in-season (N0.4) |
| 23 | `odds_nfl_scores` | Odds API `/scores` | 🏟️ | season/week | daily in-season (N0.4) |
| 24 | `odds_nfl_historical` | Odds API `/historical/*` (**2020+**) | 🏟️ | season | one-time backfill (N0.4) |

**Cost line:** nflverse **$0** · Odds API **$0 incremental** (existing sub, ~97.8k req remaining) · compute = DuckDB-over-S3 on the existing Dagster EC2 (pennies). **⇒ Total new Phase-0 spend: $0.**

---

## 8. Open gaps (carry into N0.2/N0.3/N0.4 and Phase 1)

1. **⛔/💰 Individual OL grades + pressures-allowed-per-lineman** — the one remaining PFF-gated reach even for NFL. Model OL at the unit level (snap counts + PFR team/QB pressure + line-yards analogs). Not a Phase-0 buy.
2. **⚠️ Advanced-data floors differ by asset** — NGS + pbp_participation start **2016**, PFR **2018**, FTN **2022**. A 2016–2025 backfill has every advanced feature; team/box/PBP/roster extend to 1999. Decide per-model whether to use the 2016+ or the deeper 1999+ window.
3. **⚠️ Odds history starts 2020** — CLV/backtest window is 6 seasons (nflverse `schedules` free consensus line reaches 1999 as a thinner cross-check, like CFBD `/lines` for NCAAF).
4. **🏷️ Prop-join key** — the props feed identifies players by name/team (Odds API) while the stats feed uses gsis_id. N0.4 needs a name→gsis_id resolver for props (the `players` table's name variants + team are the bridge; expect the same normalisation work as the feeder).
5. **🐍 No `nfl_data_py`** — the ingest must read release Parquet directly (per-season URL enumeration; no HTTP glob). Reuse the NCAAF `ingest/` per-season loop.
6. **🔤 Column-name drift across nflverse assets** — `players` vs `rosters` disagree on draft/rookie column names (§1). `DESCRIBE` every asset on first ingest; §2 field lists are the observed truth as of 2026-07-17.

---

_Ground-truthed 2026-07-17 against nflverse release Parquet (25 assets, live DuckDB `read_parquet`) and The Odds API v4 (live NFL odds + a historical in-season game + event-props snapshot). Row counts and field lists are observed, not documented. Re-verify before any schema-dependent ingest._
