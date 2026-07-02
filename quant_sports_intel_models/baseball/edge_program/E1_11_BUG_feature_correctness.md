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
| **Status** | **UPDATED 2026-07-02.** Defect 1 (stale form): **fix shipped in code, CI-green** — pending a box data-rebuild. Defect 2 (umpire + odds-metadata empty): **✅ RESOLVED** — stale external-table definition (wrong key-casing); fixed by regenerating the definitions. Defect 3 (odds blackout, 07-01+): **root cause CONFIRMED (bridge froze off a frozen spine); pipeline fix + durable DQ guard shipped in code, CI-green** — pending the immediate box remediation + a box run of the fixed daily op. |
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
- **Fix status:** a corrected, gap-immune **start-indexed** form metric + honest staleness flags are
  **built and validated** in the feature code, but **not yet wired into the served feature set** (that
  step is a data-platform rebuild, deferred).

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
