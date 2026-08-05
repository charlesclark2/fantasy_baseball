# NF-W0c — nflverse data-health retrospective audit (2026-08-05)

**Story:** NF-W0c (`nfl_fantasy_story_prompts.md`). **Scope:** every nflverse (+ dependent-source)
column the lake depends on, across three consumer sets — (a) the NF-W weekly
`allowed_feature_contract`, (b) the LIVE served NF1/MVP-1 season board, (c) the betting-side /
N1.2 consumers. **Method:** computed, not eyeballed — one aggregate DuckDB scan per lake table
(`s3://credence-sports-lakehouse/nfl/raw/<source>`, 30 tables, **1,566 columns**) producing
per-column × per-season non-null shares, classified mechanically
(`ablation_results/nf_w0c_column_verdicts.csv` is the full computed table; classifier thresholds
in §7). Anchor season = 2025 (the last completed season); 2026 pre-season partitions judged
separately. Every NEW death was re-verified against the **upstream nflverse release parquet** to
attribute upstream-removal vs ingest defect. `best_alpha` N/A — READ-only audit, no modeling or
serving change; all fixes are spun off.

---

## 1. ⭐ TOP — LIVE SERVED BOARD (set b) verdict

**No silently-dead column exists on the served board's NUMERIC path.** Every lake column that
feeds a served projection number was verified healthy through 2025 week 22, and the forward
(2026) partitions the board reads are fresh:

| Served signal (NF-D2 set) | Lake column(s) | Health (computed) |
|---|---|---|
| snap share | `snap_counts.offense_pct` → `fct_player_week` | ✅ 100% 2025 w1–w22 |
| target/carry/air-yards share, WOPR | `stats_player_week.target_share/air_yards_share/wopr` (+ derived carry_share) | ✅ 100% 2025 w1–w22 |
| vacated opportunity / team change | `depth_charts` NEW format (`dt/team/player_name/pos_abb/pos_rank`) via `stg_nfl_depth_charts_current` | ✅ 2025+ format 100%; 2026 fresh (max `dt` 2026-08-03) |
| week-1 Vegas env (QB tilt + K/DST) | `schedules.total_line/spread_line` | ✅ 100% ≤2025; **2026 weeks 1–3 = 16/16 games priced** |
| availability cap | `weekly_rosters.status` (2026: 2,930 rows) ⊕ Sleeper `proj_status` | ✅ present |
| xFP (NF1.5 champion) | `pbp.yardline_100/rush_touchdown/pass_touchdown/air_yards/cp/xyac_mean_yardage` | ✅ healthy through 2025 |
| K/DST overlay | `stats_player_week` kicker block; `stats_team_week` def/special columns | ✅ healthy |
| rookie leg (one hop) | `nflverse_draft_picks` (pick/round/ids), `nflverse_combine` | ✅ keys healthy (see §4 car_av + combine caveats) |
| bio panel | `nflverse_players` | ✅ healthy |

**Two served-SURFACE (display) degradations — the only set-b defects, both on the published
`projections.json → history` overlay, neither touches a projection number:**

1. 🚩 **`injuries.date_modified` is 100% NULL for 2025+** (nflverse deleted the column upstream —
   verified absent in the upstream `injuries_2025.parquet`; our `schema_mode='merge'` backfills it
   as all-NULL). `injury_log_source.py` still selects it → every published 2025+
   `history.injuryLog.dateModified` is `null`. Onset: season 2025 files (NF-W0's find, now
   confirmed on the served surface).
2. 🚩 **`injuries.report_status` is a SEMANTIC-NULL trap on the served surface** — 45.9% non-null
   in 2025 (stable 45–49% since 2022); NULL = "on the report, no designation yet", NOT healthy.
   The published `reportStatus: null` invites the wrong reading downstream/in UI.

**Set-b structural fragilities (not data deaths — recorded so they aren't rediscovered):**
- Vegas **win totals are a hard-coded Python dict** (`win_total_source.WIN_TOTALS`, current
  through 2026) on the served path — no data-health surface can see it rot; a season roll needs a
  manual edit.
- The availability-cap reads (Sleeper staging + projection-season rosters) are try/except
  WARN-tier: a missing partition silently no-ops the cap (the E11.30 "detected, nobody notified"
  class).
- `fct_player_week`'s snap join key is `weekly_rosters.pfr_id` alone, and a miss lands as
  `coalesce(offense_pct, 0.0)` — a silent 0 snap share, not a NULL.
- `stg_nfl_depth_charts*` are `select *` over the lake: a third upstream depth-chart schema change
  breaks the forward role signal wholesale.
- `xfp_source`/`defense_source`/`kdst_source` cache per-season parquets under `artifacts/` — a
  lake correction does NOT propagate until the caches are refreshed (the NF-C0e stale-cache
  class; kdst's cache is query-fingerprinted, the xfp/defense ones are not).

---

## 2. Consumer-impact-ranked FIX LIST (fixes spun off, not done here)

| # | Impact tier | Finding | Fix (spin-off) |
|---|---|---|---|
| 1 | 🔴 PROD (repo integrity) | **NF-W0's deliverables are DELETED from `dev`** — commit `1f2e7b98` ("Pushing up changes", 2026-08-04, 6 min after the PR #602 merge) removed `weekly_frame.py`, `run_nf_w0_audit.py`, `nf_w_v0_data_audit.md`, `test_nf_w0_weekly_frame.py` (19 RED-proven guards), and the 3 `nf_w0_*` ablation artifacts (1,813 lines) — almost certainly a stale-working-tree sweep, the exact shared-tree class CLAUDE.md 🌿 warns about. The certified V0 gate + allowed contract now exist only in git history (this audit recovered them from `99e075c9`). | Operator: restore the 7 files (`git checkout 99e075c9 -- <paths>` on a branch → PR). Nothing else in `1f2e7b98` conflicts. |
| 2 | 🟠 Served surface (display) | `injuries.date_modified` NULL for 2025+ rows in the published history overlay (§1.1). | In `injury_log_source.py`/exporter: stop publishing `dateModified` for 2025+ (or substitute our own capture timestamp once NF-W0a's per-ingest snapshots exist — the same cure NF-W0 already prescribed for the weekly frame). |
| 3 | 🟠 Served surface (semantics) | `report_status` NULL ≠ healthy on the published overlay (§1.2). | Exporter/UI: render NULL as "on report — no designation", never blank/healthy; add the NF-W0 semantic note to the response contract. |
| 4 | 🟡 Weekly contract (NF-W1 scope) | **`pbp_participation` provider/semantics REPLACED at 2023** (§3): `route` flipped from NULL-when-uncharted to **blank-string-filled** (26,795 `''` rows in 2024) with a changed vocabulary (HITCH/FLAT/OUT → QUICK OUT/HITCH-CURL/SCREEN), `was_pressure` became false-filled (true-share 0.29 → 0.15), `ngs_air_yards` died outright (0% from 2023), `defense_coverage_type` moved 0.39 → 0.49 non-blank with new semantics. The `opponent_matchup` family (pressure / man-zone / coverage-shell legs) is **cross-era incomparable without normalization**. | NF-W1: treat 2016–2022 vs 2023+ as two eras for the participation-derived defense legs — era indicator or 2023+ restriction; never pool `was_pressure`/coverage rates across the boundary; `'' ≠ charted` guard on `route`. |
| 5 | 🟡 Feeder (NCAAF track) | **`nflverse_draft_picks.car_av` is born-null** — 0 of 12,927 rows upstream (PFR stopped populating Career AV); NCAAF feeder's `target_car_av` (xref.py:187 → `ncaaf_draft_college_production_pairs` → `run_college_nfl_translation --target target_car_av`) is an **all-NULL target**. Default `target_w_av` is healthy (86–97% per class). Verified identical in NCAAF's own copy. | NCAAF track: remove/guard the `target_car_av` option (refuse an all-NULL target at fit time — the NF1.7 (a) vacuous-anchor rule). |
| 6 | 🟡 Future-consumer landmine | **PFR SEASON rollups lost columns at 2024, upstream**: `pfr_advstats_season_rush.td`, `season_rec.td` (100% → 0% at 2024), `season_pass.pa_pass_att`/`pa_pass_yards` (dead 2024+; also empty 2018 = pre-floor). Zero consumers today — but any future consumer inherits silently-NULL TDs/play-action. Week-level PFR + `stats_player_week` TDs remain healthy. | Record in `nfl_data_inventory.md`; if a consumer ever wants season-grain PFR TDs, derive from week files. |
| 7 | 🟢 Betting-side hygiene | The **entire betting tail is orphaned**: `dim_nfl_betting`, `mart_nfl_clv_game_lines/props`, `fct_nfl_team_game`, all three `rollup_nfl_team_*` build every run with zero downstream readers; `stg_nfl_odds` rebuilds off the intraday `odds_nfl` feed with zero readers; `odds_nfl_scores`/`odds_nfl_props` are ingested and never read. Not a data death — a cost + drift surface. | Betting track: either wire a consumer or gate the orphan builds. |
| 8 | 🟢 Pipeline (spin-off) | **All three NFL Dagster schedules ship `default_status=STOPPED`** (the E11.23 "silently never runs" class — deliberate or not, undocumented), and the **DuckDB path mismatch** means the NFL build writes `/tmp/sports_ncaaf.duckdb` while the game-day gate reads `/tmp/sports_nfl.duckdb` (gate permanently fail-open) and the Sleeper job writes a third path. | Pipeline story: unify `SPORTS_DUCKDB_PATH`, decide the schedules' intended state, document in BOX_OPERATIONS §10. |
| 9 | 🟢 Cost note | `pbp_participation` + `ftn_charting` — the two wall-clock-dominant backfills — have **zero consumers** (NF-W0's contract names participation as the route-proxy source for NF-W1, so keep; ftn_charting is speculative inventory). | None now; revisit at NF-W1. |
| 10 | ⚪ Watch | `nflverse_combine.bench/cone/shuttle` degraded (0.20–0.26 in 2025 vs 0.6–0.9 prior; `forty` 0.61 vs 0.99) — real-world drill-skipping, not a feed break. Rookie-feeder features get sparser. | None — record; imputation already handled in feeder. |

---

## 3. Per-column health table (all non-healthy columns; full 1,566-column table in `ablation_results/nf_w0c_column_verdicts.csv`)

Verdicts: **silently-dead** (alive before, 100% NULL at anchor — the merge-backfill deletion
tell) · **schema-replaced** (paired old-dead/new-alive sets) · **degraded** (real coverage drop) ·
**born-null** (never carried data in our lake) · **semantic-null** (NULL means something other
than absent). Upstream attribution: ✔ = re-verified dead in the upstream nflverse release file.

| Table | Column(s) | Verdict | Onset | Consumers hit | Notes |
|---|---|---|---|---|---|
| `depth_charts` | `club_code, week, game_type, depth_team, last_name, first_name, football_name, formation, jersey_number, position, elias_id, depth_position, full_name` (13) | **schema-replaced** (old half dead) | 2025 | `stg_nfl_depth_charts` OLD branch (translated — already era-split) | The NF-W0 find, computed. ~554k daily ESPN `dt` snapshots replace ~37k weekly rows. |
| `depth_charts` | `dt, team, player_name, espn_id, pos_grp_id, pos_grp, pos_id, pos_name, pos_abb, pos_slot, pos_rank` (11) | schema-replaced (new half) | 2025 | served (`stg_nfl_depth_charts_current`) | New format healthy + fresh; cross-era RANK comparability still open (NF-W0b spin-off). |
| `injuries` | `date_modified` | **silently-dead** ✔ | 2025 | `injury_log_source` → published history overlay (fix #2) | Upstream column DELETED; merge-backfill keeps it visible. |
| `injuries` | `report_status` | **semantic-null** | always (46–49% non-null, stable) | published overlay; NF-W weekly contract | NULL = "on report, no designation". `practice_status` is the dense sibling (99%). |
| `injuries` | `season_type` | new-in-2025 | 2025 | none | Additive upstream column — benign. |
| `pbp_participation` | `ngs_air_yards` | **silently-dead** | 2023 | none today; NF-W contract family | Died in the 2023 provider switch. |
| `pbp_participation` | `route, was_pressure, offense_personnel, defense_*_type` | **semantic-replaced** | 2023 | NF-W `opponent_matchup`/`participation_proxies` families | Blank-string fill + vocabulary + false-fill shift — see fix #4. `offense_players`/`defense_players` (the certified dropback-participation proxy) are 100% non-null every season 2016–2025 ✅. |
| `pfr_advstats_season_pass` | `pa_pass_att, pa_pass_yards` | **silently-dead** ✔ (family) | 2024 | none | Play-action block dropped upstream (also 0% in 2018 = pre-floor). |
| `pfr_advstats_season_rush` | `td` | **silently-dead** ✔ | 2024 | none | Season-rollup TDs gone upstream. |
| `pfr_advstats_season_rec` | `td` | **silently-dead** ✔ | 2024 | none | Same. |
| `pfr_advstats_week_pass` | `receiving_drop, receiving_drop_pct, def_times_blitzed, def_times_hurried, def_times_hitqb` | born-null (structural) | — | `stg_nfl_passing_pfr` selects all 5 (research marts) | nflverse ships a unioned column set per position file; the cross-family columns are never populated in this file. The real data lives in `_week_rec` / `_week_def` (healthy). Repoint if ever consumed. |
| `pfr_advstats_week_rush` | `receiving_broken_tackles` | born-null (structural) | — | `stg_nfl_rushing_pfr` | Same class (lives in `_week_rec`). |
| `pfr_advstats_week_rec` | `rushing_broken_tackles, passing_drops, passing_drop_pct` | born-null (structural) | — | `stg_nfl_receiving_pfr` | Same class. |
| `nflverse_draft_picks` | `car_av` | **born-null** ✔ | — (0/12,927 upstream) | NCAAF feeder `target_car_av` (fix #5) | PFR stopped computing Career AV. `w_av`/`dr_av` healthy. |
| `nflverse_draft_picks` | `def_ints` / `def_sacks, def_solo_tackles` | degraded | recent classes | none | Career-accumulation cohort artifact (recent classes have short careers), not a feed break. |
| `nflverse_combine` | `bench, cone, shuttle` (+ soft: `forty, broad_jump`) | **degraded** | ~2025 class | NCAAF feeder measurables | Real-world drill-skipping trend (fix #10). |
| `schedules` | `nfl_detail_id` | silently-dead | 2022 | none (`stg_nfl_schedules` doesn't select it) | Cosmetic id. |
| `schedules` | `temp, wind` | **semantic trap (leak)** | always | scanned + carried to `dim_nfl_game`/`fct_nfl_team_game`; consumed by nothing served | REALIZED game-book conditions, not forecasts (0/177 unplayed 2026 games vs 67% played 2025) — the NF-W0 leak finding, re-confirmed. Any future consumer must use the NF-W0a forecast capture instead. |
| `pbp` | `end_yard_line` | silently-dead | 2003 | none | Ancient legacy column. |
| `pbp` | `lateral_sack_player_id/_name` | born-null | — | none | Never populated. |
| `pbp` | `tackle_with_assist_1_*` | degraded | 2025 | none | Defense-detail tail-off; not on any path. |
| `stats_player_week` | `dakota` | absent-from-lake | — | `stg_nfl_weekly_data` NULL-casts it explicitly | Already handled at staging — the correct pattern. |
| `injuries` | `report_secondary_injury` | soft-degraded (0.043 vs 0.061) | 2025 | none | Within noise. |

**Freshness / completeness (computed):** every weekly table is complete through 2025 week 22
(Super Bowl); no mid-season death in 2025 for any consumed column. Roll-forward 2026 partitions
live: `depth_charts` max `dt` = 2026-08-03, `rosters`/`weekly_rosters` 2026 = 2,930 rows,
`schedules` 2026 = 272 games (weeks 1–3 fully priced; scores/referee legitimately absent
pre-season). `injuries` has no 2026 partition — correct (publication starts in-season).

## 4. Set (a) reconcile — the 10 allowed-contract families CONFIRMED

Contract recovered from git (`99e075c9`, `nf_w0_feature_contract.csv` — see fix #1). All 10
allowed families remain healthy at the column level; the audit's value was outside them:

| Family | Verdict | Note |
|---|---|---|
| game_context (schedules) | ✅ healthy | temp/wind correctly EXCLUDED by the contract (leak). |
| prior_week_box (stats_player_week) | ✅ healthy | incl. native target_share/air_yards_share/wopr, 100% 2025. |
| snap_share (snap_counts) | ✅ healthy | offense_pct 100% every 2025 week. |
| participation_proxies (pbp_participation.offense_players) | ✅ healthy | 100% non-null 2016–2025 — the certified proxy survives the 2023 provider switch. |
| team_environment (pbp) | ✅ healthy | no consumed column flagged. |
| opponent_matchup (pbp + participation) | ⚠️ healthy WITH A NEW CAVEAT | the 2023 semantics shift (fix #4) — era-normalize `was_pressure`/man-zone/coverage legs. |
| pfr_advanced (pfr_advstats_week_*) | ✅ healthy | the born-null placeholders are cross-file structural, not the family's columns (each family's columns live in its own file, healthy). |
| ngs_qualifying (ngs_*) | ✅ healthy | sparse-by-design as certified; present through 2025. |
| injury_report (injuries) | ⚠️ as certified | split fidelity (date_modified dead 2025+, report_status semantic-null) — already encoded in the contract. |
| prior_season_priors (rosters/draft_picks/combine/players) | ✅ healthy | contract features (age/experience/draft capital/measurables) fine; car_av (fix #5) and combine-drill degradation (fix #10) sit beside, not in, the family. |

**NF-W1 is NOT re-scoped** — no allowed-contract feature is dead. The one contract-adjacent
addition: carry the 2023 participation-era caveat into the opponent_matchup feature build.

## 5. Set (c) betting-side / N1.2

The N1.2 shared player-week core (`stg_nfl_weekly_data` → `fct_player_week` spine +
`weekly_rosters`/`depth_charts`/`snap_counts`/`schedules` dims) consumes **only healthy columns**
(§1 table). `schedules` betting columns (`spread_line/total_line/moneylines/odds`) are 100%
populated ≤2025 and forward-priced for 2026 weeks 1–3. The CLV marts read the Odds-API tables,
not nflverse. Remaining set-c findings are the orphan/pipeline items — fixes #7 and #8 — plus
`car_av` (#5) on the NCAAF feeder track. The odds estate note from the sweep: the nflverse lake
and the `baseball-betting-ml-artifacts` NFL odds/scores estate have **no join key wired between
them** (`schedules.game_id` ↔ odds `event_id` unreconciled) — a latent cost for any future NFL
CLV story, recorded here so it's priced in.

## 6. Semantic-NULL trap registry (NULL ≠ absent)

| Column | NULL actually means | Guard |
|---|---|---|
| `injuries.report_status` | on the report, no designation yet | never impute "healthy"; use `practice_status` (99%) as the dense signal |
| `pbp_participation.route` (2016–2022) | not the targeted receiver on this play (~59% of plays) | it is NOT per-player routes (NF-W0) |
| `pbp_participation.route` (2023+) | **`''` blank**, not NULL — vocabulary changed | `'' ≠ charted`; never count non-null as coverage |
| `pbp_participation.was_pressure` (2023+) | false-filled — False may mean "not charted" | era-normalize; never pool across 2022/2023 |
| `schedules.temp/wind` | game not yet PLAYED (realized data) | a feature-read is a leak, not a gap |
| `ngs_*` weekly rows | player didn't qualify (~40% of targeted WR/TE weeks) | flag present/absent; never impute 0 (NF-W0) |
| `snap_counts` join miss in `fct_player_week` | lands as **0.0**, not NULL (`coalesce`) | a pfr_id gap reads as a zero snap share |

## 7. Method appendix

- Sweep: for each of 30 lake tables, one `SELECT season, count(*), count(col)…GROUP BY season`
  over `delta_scan` (all-column counts in a single pass; ~2–17s/table). Classifier: anchor =
  latest season ≤2025; **silently-dead** = prior peak share ≥0.05 and anchor share 0;
  **degraded** = anchor < 0.5× prior-alive median (soft watchlist at <0.8×); **born-null** = 0
  everywhere; **new-in-anchor** = first life at anchor. 2026 shares reported, never classified.
- Upstream attribution: dead columns re-read from
  `github.com/nflverse/nflverse-data/releases/download/...` directly (season files + single
  files); every ✔ above reproduced upstream ⇒ consumer-side fixes, no ingest repair possible.
- Consumer sets: (a) recovered `nf_w0_feature_contract.csv` @ `99e075c9`; (b) traced from
  `export_draft_board_json.py` (`DEFAULT_PROJECTION_SOURCE = "nf1_5"`) back through
  `run_nf1_5 → run_nf1_2/1_1/1_3 → run_season_projection` + the K/DST + history exporters, incl.
  every raw `delta_scan` bypassing dbt; (c) all `nfl_delta()` scans in
  `sports_dbt/models/nfl/**` + `betting_ml` + `scripts` (the only non-fantasy consumers are the
  dbt betting tail and the game-day gate, which reads the local DuckDB only).
