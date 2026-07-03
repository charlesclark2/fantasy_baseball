# 🐞 BUG REPORT — production model features are not correct (E1.11 audit)

**Reported:** 2026-07-01 · **From:** E1.11 feature-correctness audit · **To:** PM
**Full technical detail:** [E1_11_feature_correctness_dossier.md](./E1_11_feature_correctness_dossier.md)
**One-line:** The features our MLB models are served on are, in two concrete ways, **wrong** — a silent
stale-data miscalculation and whole feature blocks that are **empty in production** — so any recent
"no-edge" conclusion was measured on an untrustworthy input and can't be trusted as-is.

---

## Severity & status
| | |
|---|---|
| **Severity** | **HIGH** — affects the live prediction inputs, silently (no error, no null-alert). |
| **Customer-facing?** | Indirect. Predictions still render; they're just computed on partly-wrong/partly-missing inputs. No incorrect *claims* are shown to users. |
| **Status** | **UPDATED 2026-07-03 (pre-Phase-3 revalidation).** Defect 1 (stale form): **✅ RESOLVED** — start-indexed form + staleness flags verified (Teheran `sp_k_pct_l3=0.1154`). Defect 2 (umpire empty): **⚠️ REGRESSED 2026-07-03** — the 7/2 ext-DDL regen did NOT hold (patched a fragile mirror source); umpire is empty AGAIN in the external tables (native historical still intact → Phase-3 substrate unaffected). Durable fix = the deferred **W11b umpire box cutover**; a durable **feature-block coverage guard shipped** this session so it can't fire silently a 3rd time. Defect 3 (odds blackout): **✅ RESOLVED** — bridge-freeze fix + odds DQ guard shipped; store now fresh (reaches 07-05, native==ext). **Phase-3 revalidation verdict: the 2021–2025 native substrate is CLEAN; the only open item is the live umpire cutover.** |
| **Blocks** | The planned pre-All-Star-break edge re-test. Re-testing on these inputs would produce a false result either way. |

---

## Defect 1 — starter "recent form" is silently stale (miscalculation)
- **What's wrong:** a starting pitcher's "last 7 / 30 day" form numbers are carried forward with **no
  staleness limit**. On a pitcher's first start of a season (or after an injury layoff), the model is
  shown *last season's* numbers labeled as "current form."
- **Proof:** Julio Teheran, 2021-04-03 — the row shows **189 days of rest** (correct: it's his season
  debut) **alongside a populated "7-day form"** (impossible; those are his Sept-2020 numbers, 189 days
  old). The two facts can't coexist — one of them is a bug.
- **How widespread:** **~9.4% of all starter rows** (every row with a >15-day gap carries a
  populated "7-day" window). Concentrated at each season's opening turn and post-injury returns —
  exactly the situations where "recent form" matters most.
- **Also implicated (same root):** traded / newly-acquired pitchers get form + team-context attributed
  to the wrong team on their debut with a new club (104 such starts since 2021, trade-deadline-heavy).
- **Fix status: ✅ RESOLVED 2026-07-02 — surfaced + verified in the served store.** The corrected,
  gap-immune **start-indexed** form metric (`*_sp_k_pct_l3` / `_sp_bb_pct_l3` / `_sp_xwoba_against_l3` /
  `_sp_form_start_count`) + honest staleness flags (`_form_source_age_days` / `_form_stale` /
  `_long_layoff`, 7 per side / 14 total) are now live in `feature_pregame_game_features(_raw)` after the
  box `--w8b` rebuild + external-table regen/refresh. Verified against the served external table: columns
  ~97–99% populated across 2021 and on the current slate; the Teheran proof row (game_pk 634573) now reads
  `sp_k_pct_l3 = 0.1154` (the true last-3-starts value, NOT the stale 0.188), with
  `form_source_age_days = 189`, `form_stale = true`, `long_layoff = true` — the honest flags now EXPOSE
  the 189-day gap instead of silently showing a populated "7-day form" beside it.

## Defect 2 — umpire + odds-metadata read back empty → ✅ RESOLVED 2026-07-02
- **What it was:** the umpire block and the odds-timing metadata read back **100% empty** in the served
  store, even though the data was physically present.
- **True root cause (verified against live data):** a **stale external-table definition**, NOT missing
  data and NOT the "circular mirror / native-build" theory in an earlier draft of this report (that was
  wrong). The served store exposes each column by pulling a named key out of the underlying file; the
  definition had those keys in the **wrong letter-case** (e.g. it looked for `ump_accuracy_zscore` while
  the file stored `UMP_ACCURACY_ZSCORE`), so the read silently returned empty. The values were in the
  file the whole time.
- **Fix (done):** **regenerating + applying the external-table definitions** (the migration's
  `generate_w8b_external_tables.py`, which reads the file's real column names and emits matching keys).
  After the regen: umpire z-scores populate **98–99% across every season 2015→2026**, and the
  odds-metadata columns populate on every date that has odds. Confirmed on both the raw and public served
  tables. **No data was re-derived; no model change.**
- **Lesson for the migration track:** whenever a lakehouse file's writer changes column casing, the
  external-table definition must be **regenerated against the actual file** — a case drift reads as
  "100% empty" silently (this is the documented `VALUE:`-case landmine).

### ⚠️ Defect 2 REGRESSED 2026-07-03 (F2-recurrence — the 7/2 regen did NOT hold)
- **Found during the pre-Phase-3 data revalidation.** The **umpire block is empty AGAIN** in the served
  external tables: `lakehouse_ext.feature_pregame_umpire_features` = **0.000** umpire coverage across
  every season (data present — 26,223 rows — read as null), and the W8b aggregator's external table has
  the umpire columns **entirely absent** (a 2025 parquet row has 740 keys, *zero* containing `ump`/`zscore`).
  The native `betting_features` tables are still populated **historically** (standalone umpire model =
  26,223 rows @ **1.000**; aggregator 2021–2025 @ 0.97–1.0), but the native incremental MERGEs the null
  umpire into the **current slate** — recent-2-week aggregator umpire coverage has collapsed to **0.502**
  (last-7-days **0.077**) and is falling.
- **Why it came back:** the 7/2 "fix" regenerated the external-table DDL against the **SF export-mirror
  parquet** (uppercase, written by `export_features_to_s3.py`) — a fragile source. The **durable** source
  is the native duckdb build of `feature_pregame_umpire_features` (`--w11b`), whose **box cutover was never
  done** (`W11B_UMPIRE_NIGHTLY` unset — see [[project_e11_1_w11b_umpire]]). So the aggregator still reads
  the mirror parquet and the block nulls out. Root cause is the **deferred W11b umpire cutover**, not a new
  code regression (git history clean).
- **Impact on Phase 3:** NONE on the trustable window — Phase 3 reads native `betting_features` 2021–2025,
  where umpire is intact. The break is a **live-serving** correctness bug (current slate + external tables).
- **Durable fix = complete the W11b umpire cutover on the box** (operator, RUNTIME-GATE): `W11B_UMPIRE_NIGHTLY=1`
  → `run_w1_lakehouse.py --w11b-only` (native lowercase umpire parquet overwrites the mirror's `data.parquet`,
  last-writer-wins) → `refresh_w1_external_tables.py --w11b` → `--w8b-only` rebuild (aggregator precursor view
  now picks up the native parquet) → regen + refresh the w8b ext DDL → dbt run `feature_pregame_game_features_raw`
  + `feature_pregame_game_features` → **per-ROW** fetch through `lakehouse_ext.feature_pregame_umpire_features`
  (non-null) + `check_feature_block_coverage.py --env prod` green → then trim umpire from
  `export_features_to_s3.FEATURE_TABLES`. Full runbook in [[project_e11_1_w11b_umpire]] steps 4–9.
- **Durable GUARD (shipped this session, CI-green):** `scripts/check_feature_block_coverage.py` +
  `check_feature_block_coverage_op` (wired into the daily job after `refresh_w1_external_tables_op`, beside
  the odds guard). Self-calibrating: compares each served feature BLOCK's coverage on recently-played slates
  to its own older baseline → fires **DEGRADED** when a normally-full block silently collapses (umpire:
  baseline 1.000 → recent 0.077 on live data), **SKIPs** coverage-gapped blocks (odds), never false-fires on
  posting-timing. ALERT-continue by default; `FEATURE_COVERAGE_STRICT=1` → HALT after the cutover restores it.
  12 unit tests (`test_feature_block_coverage_guard.py`). This closes the "F2 fired twice, silently" gap.

---

## 🚨 Defect 3 (LIVE — found by the odds DQ check) — odds blackout for the current slate → CONFIRMED root cause + fix
- **What's wrong:** the served store shows **`has_odds = false` for the entire current slate** — no
  moneyline, no total — so today's (and the next days') predictions run with **no market data at all.**
  Began **07-01, the day after the 06-30 cutover.**
- **CONFIRMED root cause (traced end-to-end in Snowflake 2026-07-02):** NOT missing odds. The join table
  `mart_game_odds_bridge` **froze at 06-30** while *both* of its inputs are fresh — `mart_game_spine`
  reaches 07-04 and `mart_odds_outcomes` reaches 07-02. For 07-01 and 07-02 there are **9–14 scheduled
  games AND 9–14 matching odds events**, so odds *would* attach on a rebuild — the bridge parquet simply
  had not been rebuilt since 06-30. WHY: in the daily `run_w1_lakehouse_op`, the `--w6` step that builds
  the bridge runs **before** the spine rebuild (`--w5-group-a`) in the same op, so the bridge is always
  built off the *previous* run's spine. When that prior spine was frozen (the sibling spine-freeze
  incident), the bridge froze with it. This is silent — no error, no null-alert.
- **Fixes shipped in code this session (CI-green; box run pending — RUNTIME GATE):**
  1. **Pipeline fix** — `run_w1_lakehouse_op` now rebuilds the odds-serving hot set
     (`mart_odds_outcomes` `_current` + `mart_game_odds_bridge`, via `--w6-odds-current`) **after** the
     same-run spine rebuild, off the FRESH spine, and refreshes those two external tables. The bridge can
     no longer lag the spine within a run.
  2. **Durable DQ guard** — new `scripts/check_odds_coverage.py` + `check_odds_coverage_op`, wired into
     `daily_ingestion_job` right after the odds marts refresh and before the prediction path. It fires a
     loud **FREEZE** alert when the current slate has games AND odds events but **zero** attached in the
     bridge (the exact incident signature). It keys off `odds_events > 0`, so it can **never** false-fire
     when books simply have not posted yet (that path is the benign `NO_ODDS_YET`). Default tier is
     **ALERT-loud-but-continue** (never blocks serving during rollout); set `ODDS_COVERAGE_STRICT=1` to
     promote a current-slate freeze to a **HALT** once validated on the box. Unit-tested
     (`betting_ml/tests/test_odds_coverage_guard.py`, 11 cases).
- **Immediate remediation (operator, box) to restore TODAY's odds now** — the spine is already fresh, so a
  single targeted rebuild fixes it: `run_w1_lakehouse.py --w6-odds-current` then
  `refresh_w1_external_tables.py --w6-odds`, then re-verify (query below). Going forward the pipeline fix +
  the daily spine rebuild keep the bridge current; the guard catches any regression loudly.

## Data-quality note (the requested check) — the migration window is otherwise clean
Full odds-coverage sweep of the migration window (2026-06-18 → 07-02) against the served store:
**every date 06-18 → 06-30 is fully covered** — bridge `has_odds` = scheduled games, and both moneyline
and totals events are present for every game. **The only blackout is the 07-01+ bridge freeze (Defect 3).**
(An earlier draft flagged a 06-18→06-20 price gap; at the aggregate market level those dates are fully
covered, so any residual gap was book-specific, not a slate-wide blackout.) The new
`check_odds_coverage.py` guard runs this same coverage logic daily going forward.

---

## Business impact / why it matters now
1. **Our recent "the model has no edge" findings are not trustworthy.** They were computed on inputs that
   are ~9% stale-in-a-known-way and missing two whole feature groups. That's not evidence of "no edge" —
   it's evidence we haven't measured on a clean input yet.
2. **It's silent.** Nothing errors or alerts; the numbers are just wrong/absent, so it would keep shipping
   indefinitely without this audit.
3. **The pre-ASB edge push is gated on it.** Re-running the edge test before this is fixed wastes the
   window and risks a false green or false red.

## Recommendation (PM decision needed)
- **Prioritize the two fixes as a prerequisite** to the edge re-test (both are understood; neither is
  research — they're a data-platform rebuild + a migration switch-on).
- **Then** run the edge re-test on the clean inputs. Only that result (positive or negative) is
  trustworthy.
- Until then, treat any model-vs-market "edge / no-edge" conclusion as **provisional**.

*(Engineering detail, exact queries, quantification tables, and the built fix live in the dossier linked
above. No user-facing claims are affected; this is an internal input-correctness defect.)*
