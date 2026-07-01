# E1.11 — Feature Correctness + Config Audit (Phase 1 dossier)

**Story:** E1.11 (🧭 OPUS) — the clean-foundation precursor to the pre-All-Star-break edge RE-TEST.
**Date:** 2026-07-01 · **Scope:** `feature_pregame_game_features(_raw)` + `feature_pregame_starter_features` correctness.
**Thesis (operator, correct):** *a null on buggy/misconfigured features is not a trustworthy null.* The model-discrimination
edge nulls were computed on features we now have direct evidence are stale/miscalculated and (in production) partly dead.
This dossier = the bug inventory (null + miscalc) + fixes + reconfigured features + a **what-we-now-trust** statement, so Phase 2
(granular features) and Phase 3 (the E13.4-harness, deflation-honest lift re-test) run on a substrate we can defend.

> **Discipline honored:** Phase 1 is CORRECTNESS, not lift-chasing. No new predictive axis is claimed here; the one *reconfigured*
> feature (start-indexed form) is a fix for a proven miscalc, not an edge play. The §0.5 PBO<0.2/DSR>0 deflation gate on the
> eventual re-test is untouched and remains the thing that stops the sprint manufacturing a mirage.

**Data source:** production reads from the **S3 lakehouse via `BASEBALL_DATA.LAKEHOUSE_EXT.*`** (post-W8b cutover). All audit
queries below ran against `LAKEHOUSE_EXT` (the served truth), cross-checked against the frozen Snowflake copy
`BASEBALL_DATA.BETTING_FEATURES.*` to separate *migration read-regressions* from *genuine* nulls. `n = 26,474` game rows /
`52,060` starter-rows (both sides, `has_starter_data = true`).

---

## 0. TL;DR — the four correctness findings

| # | Class | Finding | Severity | Status |
|---|-------|---------|----------|--------|
| **F1** | **MISCALC** | Calendar `*_7d/_14d/_30d` starter form is a **stale carry-forward with no max-staleness bound** — 100% of the 9.43% of starter-rows with `days_rest>15` show a *populated* "7-day" window (impossible). `days_rest` itself is **correct**. | **HIGH** (feeds every game) | **Fixed** (start-indexed form + staleness flags built; calendar-guard specced) |
| **F2** | **DEAD IN PROD** | The lakehouse cutover **silently dropped whole blocks** from the served table: the **entire umpire block** + odds-metadata are **100% null in `LAKEHOUSE_EXT`** but populated in the frozen Snowflake copy. In-flight migration gap (W11b/odds not box-cut-over). | **HIGH** (feature set is provably incomplete) | **Diagnosed** → gate the re-test on restoration |
| **F3** | **CONTEXT MISATTRIB** | Traded / new-team pitchers carry cross-team-blended season-to-date + a stale calendar window on the new-team debut; **no `is_recently_acquired`/team-change flag exists**. 104 in-season new-team starts since 2021 (deadline-concentrated). | **MED** | **Diagnosed** (+ `starter_long_layoff` flag lands the debut case) |
| **F4** | **NULL STRUCTURE** | Full per-column null audit complete (see §4). Most high-null columns are *honest* coverage limits (odds/public-betting ~70%, bat-tracking ~73% pre-2023, weather ~51% pre-2021), not bugs — but they define the **trustable training window**. | INFO | **Catalogued** |

---

## 1. F1 — the flagship miscalc: stale calendar rolling ("Teheran 189")

### 1.1 The contradiction, resolved
Operator's proof row: `feature_pregame_game_features` game_pk **634573** — Julio Teheran (id 527054), **2021-04-03 DET vs CLE**:

```
home_starter_days_rest        = 189
home_starter_k_pct_7d         = 0.188      home_starter_k_pct_30d = 0.134   home_starter_k_pct_std = 0.134
home_starter_avg_fastball_velo_7d = 90.1   home_starter_appearances_30d = 5  home_starter_appearances_std = 10
```

**Resolution — the two numbers do NOT both get to be right, and we now know which is which:**
- `days_rest = 189` is **CORRECT.** 2021-04-03 was Teheran's first start of the season; his prior start was **2020-09-26**
  (as LAA). `datediff` = 189 days. `days_rest` is sourced from `mart_starting_pitcher_game_log` (starts only), so it is already
  *start-indexed* and IL/offseason-aware. ✅ Trust it.
- The `*_7d/_30d/appearances_*` form is **WRONG (stale carry-forward).** It comes from a *different* source
  (`mart_pitcher_rolling_stats`) via an as-of join that takes the most-recent row (`rn = 1`) with **no upper bound on
  staleness**. On a season debut the "most recent row" is the pitcher's *last game of the prior season*, so its 7-/30-day window
  (computed relative to **Sept 2020**) is stamped onto an **April 2021** start. The tell: `k_pct_30d == k_pct_std == 0.134`
  (the 30-day and season windows coincide because it's a late-season row), and `appearances_30d = 5` is 5 appearances in the
  30 days *ending Sept 2020*.

### 1.2 Root cause (code)
`feature_pregame_starter_features.sql`:
- `days_rest` (correct): `datediff('day', ps.last_start_date, pp.game_date)` where `ps.last_start_date = max(gl.game_date)` from
  the **game log**, `gl.game_date < pp.game_date`.
- calendar rolling (buggy): CTE `rolling_ranked` joins `mart_pitcher_rolling_stats` with only a lower guard
  (`rs.game_date::date < pp.game_date`) and picks `row_number() … order by rs.game_date desc = 1`. **There is no
  `AND rs.game_date >= pp.game_date - N` bound**, so an arbitrarily old row wins when the pitcher has a gap.

### 1.3 Systemic rate (quantified, `LAKEHOUSE_EXT`, `has_starter_data=true`, n=52,060 starter-rows)

| metric | rows | % |
|---|---|---|
| `days_rest > 15` | 4,907 | **9.43%** |
| `days_rest > 30` | 3,840 | 7.38% |
| `days_rest > 15` **AND** `k_pct_7d` populated (stale) | 4,907 | **9.43%** |
| `days_rest > 30` **AND** `k_pct_7d` populated (stale) | 3,840 | 7.38% |

**Every** long-gap row carries a populated calendar window → the "7-day form" is a stale prior-window in 100% of gap cases.
Concentrated at **each season's opening turn** and **post-IL returns** — precisely the low-N, high-variance regime the E13.4
lift-tests weight. This is the "unknown systemic rate" the story flagged, now bounded: **~9.4% of starter-rows carry
misleading calendar form**, and it is silent (populated, not null → not caught by any null test).

### 1.4 Fix — START-INDEXED form + staleness diagnostics (BUILT)
Reconfigured `feature_pregame_starter_features.sql` (DuckDB branch, additive; ground-truth-validated on Teheran):

| new column | definition | Teheran 634573 |
|---|---|---|
| `sp_k_pct_l3` | BF-weighted K% over last ≤3 **starts** (strict `<` guard) | **0.115** (vs stale `k_pct_7d=0.188`) |
| `sp_bb_pct_l3` | BF-weighted BB% last ≤3 starts | 0.192 |
| `sp_xwoba_against_l3` | BF-weighted xwOBA-against last ≤3 starts | 0.6846 |
| `sp_form_start_count` | # prior starts backing it (0–3) | 3 |
| `starter_form_source_age_days` | age (days) of the **calendar** rolling source row (`stats_game_date`) vs the game | 189 |
| `starter_form_stale` | `source_age_days > 30` — the `*_7d/_14d/_30d` block is NOT recent form for this start | **true** |
| `starter_long_layoff` | `days_rest > 30` — offseason debut / IL return; makes a correct large `days_rest` legible | **true** |

Start-indexed rates are **gap-immune** ("the last 3 real starts, whenever they were") and BF-weighted (a 1-batter opener cameo
can't distort them). The staleness columns let a model (Phase 3) **down-weight or gate** the calendar block instead of trusting a
phantom window. Validated: an independent SQL replay of the exact aggregate over `mart_starting_pitcher_game_log` reproduces the
table above row-for-row.

**Follow-on (specced, NOT yet applied — deliberately, to keep blast radius contained for Phase 1):** a *calendar-guard* that
`NULL`s `*_7d/_14d/_30d` (→ impute-as-unknown) when `starter_form_stale`. Held for Phase 3 so the guarded-vs-raw calendar block
can be A/B'd under the deflation gate rather than silently changing the served matrix mid-audit.

---

## 2. F2 — DEAD-IN-PROD blocks (lakehouse read-regression)

Cross-check of `LAKEHOUSE_EXT` (served) vs `BETTING_FEATURES` (frozen Snowflake), non-null counts, n=26,474:

| column | `LAKEHOUSE_EXT` (served) | `BETTING_FEATURES` (frozen) | verdict |
|---|---|---|---|
| `ump_accuracy_zscore` | **0** | 26,115 (98.6%) | **regression** |
| `umpire_name`, `ump_*_zscore`, `ump_games_sample` | **0** | 26,115 | **regression** |
| `odds_hours_before_game` | **0** | 7,757 | **regression** |
| `market_bookmaker_count` | **0** | 9,746 | **regression** |
| `odds_ingestion_ts`, `odds_bookmaker_key` | **0** | (metadata) | **regression** |
| `temp_f` | 12,896 | 12,896 | ✅ identical (mechanism sound) |
| `home_starter_days_rest` | 25,707 | 25,708 | ✅ identical |

Because parity columns (`temp_f`, `days_rest`) match **exactly**, the external-table read mechanism itself is fine — this is
**block-specific**: the umpire block and odds-metadata are genuinely absent from the S3 parquet. This is consistent with memory
`[project_e11_1_w11b_umpire]` (umpire→S3 "CODE-COMPLETE + CI-green, **box cutover remains**") and the odds-metadata W-series
tail. i.e. the S3 feature build currently emits these blocks all-null because their upstream S3 mirrors aren't being written on
the box yet.

**Consequence for the edge push:** the served feature set is **provably incomplete** today — the entire umpire signal and the
odds-timing/So-book-count metadata are zeroed out. Memory records umpire z-scores were repaired to ~1.1% null in Snowflake
(Story 30.5); that repair is **not reaching production**. **The Phase-3 re-test MUST NOT run until F2 is closed** (either the
W11b/odds box cutover lands, or the audit explicitly excludes these columns and says so). Coordinate with E11.22 / INC-24.

**Genuinely-null (both stores) — NOT regressions, documented:** `home/away_starter_proj_xfip` (FanGraphs ZiPS omits xFIP);
`home_consecutive_away_games` / `away_consecutive_home_games` (never populated in either store — a dead column to either wire or
drop; flagged for Phase 2 triage).

---

## 3. F3 — traded / new-team context misattribution

- **Mechanism:** rolling & season-to-date starter features are pitcher-keyed, so a mid-season-acquired pitcher's `*_std`
  season-to-date blends both teams (mostly benign for a pitcher — *skill travels*), but his **new-team debut** row also inherits
  (a) a **stale calendar window** from his old team (F1), and (b) **team-context** features (defense-behind / bullpen / park
  handedness) attributed to the new club with zero games of evidence. **No `is_recently_acquired` / team-change flag exists.**
- **Scope (2021+, `mart_starting_pitcher_game_log`):** **104** in-season new-team starts across **83** pitchers — small but
  **trade-deadline-concentrated**, landing right inside the current 2-week window.
- **Phase-1 mitigation:** `starter_long_layoff` catches the offseason/IL debut; the traded-*within-season* debut (days_rest small,
  new context) is **not** yet flagged and is the cleaner motivation for the Phase-2 `is_recently_acquired` feature (an
  information-timing signal: both the market and our own rolling features are slow to re-rate a player in a new context).
- **Batter/lineup side (larger cohort) — Phase-2 deepening:** the same blend hits traded *hitters* far more numerously; that is
  the higher-value traded-player validation and is explicitly deferred to Phase 2 (lineup decomposition touches the same code).

---

## 4. F4 — full null audit (structure of the served matrix)

Per-column null-rate computed over `LAKEHOUSE_EXT.feature_pregame_game_features_raw` (all ~700 cols; method:
`object_construct_keep_null(*)` + `lateral flatten`, so no column enumeration). Buckets:

- **100% null (15 cols):** F2 regressions (umpire, odds-metadata) + genuine-dead (`*_proj_xfip`, `*_consecutive_*_games`). See §2.
- **~62–79% null — odds / market / public-betting** (`total_line*`, `*_moneyline_*`, `*_implied_prob`, `over/under_*`, sharp
  signals, ActionNetwork pcts): **honest historical coverage** (odds backfill is partial; `has_odds` flag exists). Defines the
  odds-complete sub-window; not a bug.
- **~73% — bat-tracking** (`*_bat_speed*`, `*_attack_angle`, `*_swing_length`): Statcast bat-tracking only exists 2023+.
- **~46–53% — weather (51%), EB-sequential & team-sequential posteriors (~49–53%), ZiPS proj_fip (~47%):** pre-2021 coverage
  gaps + posterior warm-up. Honest.
- **~9–30% — cluster/archetype matchups, pythagorean, team-OAA-prior, base-state splits, EB-starter (~9.5%):** rookies / early
  season / prior-season-absent. Mostly leak-clean cold-start (E13.7) by design.
- **~1.6–2.9% — the starter rolling block & `days_rest`** (`~459` / `~784` rows): debut pitchers + season openers. This is the
  **null** face of F1 (debuts null out; long-gap rows populate-but-stale — the more dangerous case).

**Implication:** the **trustable dense-training window** is roughly **2021+ with `has_odds` and non-cold-start**, and even there the
served rows currently lack the umpire block (F2). Phase 3 should stratify/condition on `has_full_data`, `has_odds`,
`is_cold_start`, and the new `starter_form_stale` / `starter_long_layoff` flags.

---

## 5. ✅ WHAT WE NOW TRUST (the clean-substrate statement)

**Trust (validated this audit):**
- `days_rest` (both sides) — start-indexed, correct even at 189-day extremes.
- `temp_f` and other parity-checked columns — identical across stores; the ext-table read mechanism is sound.
- The new **`sp_*_l3` start-indexed form** + **`starter_form_stale` / `starter_long_layoff` / `starter_form_source_age_days`**
  diagnostics — ground-truth-validated on the lead case; gap-immune by construction.
- The null *structure* (§4) — coverage limits are understood and mostly honest; the dense window is characterized.

**Do NOT trust until fixed/gated:**
- Calendar `*_7d/_14d/_30d` starter form on any row where `starter_form_stale = true` (~9.4% of starter-rows) — use `sp_*_l3`
  or gate. **(F1)**
- **The entire umpire block and odds-timing metadata in production** — 100% null in the served table. **The Phase-3 lift re-test
  is BLOCKED on F2** (restore via W11b/odds box cutover, or exclude-and-declare). **(F2)**
- New-team-debut rows' team-context features (small cohort; add `is_recently_acquired` in Phase 2). **(F3)**

**Gate posture for Phase 3:** run the E13.4 harness (purged/embargoed CV + PBO<0.2/DSR>0 + shrinkage) **only** after F2 is
closed, on the 2021+ dense window, with `starter_form_stale`/`is_cold_start` as stratifiers and the calendar-block-guard A/B'd
as a pre-registered config (counted toward PBO). A trustworthy null (or a real edge) is only earned on that substrate.

---

## 6. Phase 2 / Phase 3 hand-forward (unchanged scope, now substrate-ready)
- **Phase 2 (granularity, un-tested):** lineup decomposition (top/middle/bottom × 7/30/season), bullpen role-structure
  (7th/8th/9th arms), team-decision modeling, **`is_recently_acquired`** (acquired-N-days + new-context-adjusted form), and a
  clean-data batter-vs-pitcher re-check. Lineup decomposition + the batter-side traded validation (F3) share code → do together.
- **Phase 3 (the honest re-test):** E13.4 harness on the corrected + decomposed features → trustworthy null OR the real edge.

---

## Appendix — audit reproduction (all read-only, `LAKEHOUSE_EXT`)
1. **Staleness rate:** two-sided `union all` of starter-rows, `count_if(days_rest>15 and k_pct_7d is not null)` etc. (§1.3).
2. **Full null audit:** `object_construct_keep_null(*)` + `lateral flatten` → per-key null count (§4). (Note: `t.*` inside the
   function trips the SELECT-only MCP classifier; use unqualified `*`.)
3. **Read-regression:** non-null `count()` of the same columns in `LAKEHOUSE_EXT` vs `BETTING_FEATURES` (§2).
4. **Start-indexed validation & traded scope:** `mart_starting_pitcher_game_log` for pitcher 527054 < 2021-04-03 (§1.4);
   `lag(pitching_team)` same-season change count (§3).
</content>
</invoke>
