"""RED proof for the MLB-LAKE2 guards — `uv run python betting_ml/tests/mlb_lake2_red_proof.py`.

This story's two claims are both of the kind that pass by accident if nobody checks:

  ① "promote-then-delete is safe for derivative_odds_raw" rests on two readers deduping an exact
     duplicate. The MEASUREMENT of that ("the output is identical") is indistinguishable from a
     measurement that never happened, so the duplication itself is proved detectable, and each
     reader's dedup is proved load-bearing by removing it.
  ② "the tick may stop building three models" rests on a DAILY builder still building them. That
     is an assumption about a box's env, so the anti-orphan guards are proved falsifiable.

The four ways a RED proof lies, all guarded (mirrors mlb_inc_0904_red_proof.py):
  * the mutation never LANDS (E11.24 #682)             → the source is re-read and diffed.
  * the anchor is NOT UNIQUE (E11.24 prediction_log)   → each anchor must occur exactly once.
  * it lands but does not MOVE the predicate (#815)    → an expected-GONE token is checked absent.
  * RED for the wrong reason                           → a BASELINE run must be GREEN first, and
    NOT-SELECTED controls prove each break is TARGETED, not a blanket failure.

⭐ The spec's hard line is that nothing here may quiet an alert. Two breaks defend it directly:
the INC-41 "a frozen artifact still fires" semantics, and the freshness coverage that makes a
stopped daily builder page instead of silently freezing the tables the tick stopped building.

Restores every file in a `finally`, and restores stale backups at START-UP, so an interrupted run
can neither leave a break on disk nor be one `git add` from committing it.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

LAKE2 = "betting_ml/tests/test_mlb_lake2_w3pre_tier.py"
COMPACT_T = "scripts/tests/test_compact_lakehouse_raw.py"
INC0904_T = "betting_ml/tests/test_mlb_inc_0904_w3pre_priority.py"
ORDER_T = "betting_ml/tests/test_lineup_intraday_wide_rebuild.py"

EVAL = "betting_ml/scripts/cross_market_eval/eval_cross_market.py"
MART = "dbt/models/mart/mart_derivative_closes.sql"
FLATTEN = "dbt/models/staging/stg_derivative_odds.sql"
COMPACT = "scripts/compact_lakehouse_raw.py"
RUN_W1 = "scripts/run_w1_lakehouse.py"
INTRADAY = "pipeline/ops/intraday_ops.py"
DAILY = "pipeline/ops/daily_ingestion_ops.py"
FRESH = "betting_ml/monitoring/artifact_freshness.py"

_EVAL_DEDUP = "        FROM ranked WHERE rn = 1"
_MART_DEDUP = "    where snap_rank = 1"
_TICK_FLAG = '    for _flag, _what in (("--w3pre-serving-only", "game-state flatten"),'
_DAILY_CALL = '    _run_script(context, "run_w1_lakehouse.py", ["--w3pre-only"], timeout=1800)'

# (label, file, old, new, "<test file>::<test name>", gone_token_or_None)
BREAKS = [
    # ── ① the reader sign-off: each dedup is LOAD-BEARING, and the duplicate is DETECTABLE ──
    # ⭐ This break defeats TWO mechanisms at once, and that is a FINDING rather than a
    # convenience. eval_cross_market is duplicate-idempotent redundantly: `rn = 1` keeps exactly
    # one row per key however many copies exist, AND the outer max() is invariant over a doubled
    # multiset. Each was broken ALONE first and the test correctly stayed GREEN both times — the
    # output really is unchanged — so only defeating both proves the measurement can see
    # duplication. Defence in depth is why this reader's sign-off survives one of the two being
    # edited; the guard in test_compact_lakehouse_raw.py pins the row_number half regardless.
    ("eval_cross_market is made duplicate-SENSITIVE (both mechanisms defeated at once)",
     EVAL,
     "               max(pt) AS line_B\n        FROM ranked WHERE rn = 1",
     "               sum(pt) AS line_B\n        FROM ranked WHERE rn >= 1",
     f"{LAKE2}::test_eval_cross_market_closing_selection_is_unchanged_by_the_duplicate_window",
     "FROM ranked WHERE rn = 1"),
    ("eval_cross_market's dedup is removed — the ALLOWLIST's own claim about it goes stale",
     EVAL, "row_number() OVER (", "dense_rank() OVER (",
     f"{COMPACT_T}::test_each_stg_derivative_odds_reader_still_dedups"
     "[betting_ml/scripts/cross_market_eval/eval_cross_market.py]",
     None),
    ("mart_derivative_closes stops deduping — the OTHER reader of the flattened output",
     MART, _MART_DEDUP, "    where snap_rank >= 1",
     f"{LAKE2}::test_mart_derivative_closes_is_unchanged_by_the_duplicate_window",
     "where snap_rank = 1"),
    ("the harness stops duplicating — 'identical output' would then prove NOTHING (NF1.7 (a))",
     LAKE2, '        body = f"{body} UNION ALL {body}"', "        body = body",
     f"{LAKE2}::test_the_duplicate_window_actually_reaches_the_readers",
     'body = f"{body} UNION ALL {body}"'),
    ("the flatten gains a dedup — the allowlist rationale stops describing its own first hop",
     FLATTEN, "from outcomes_flattened", "from outcomes_flattened group by all",
     f"{LAKE2}::test_the_flatten_cannot_absorb_or_amplify_the_duplication", None),
    ("the fixture is cut back to one reader's columns — the other reader silently stops running",
     LAKE2, '    "outcome_price_decimal": "DOUBLE", "outcome_point": "DOUBLE",',
     '    "outcome_price_decimal": "DOUBLE", "outcome_point": "DOUBLE", "bogus_col": "VARCHAR",',
     f"{LAKE2}::test_the_fixture_is_real_and_its_closing_selection_is_load_bearing", None),
    ("a source is compacted without its own vetted rationale (the borrowed-rationale refusal)",
     COMPACT, '    "derivative_odds_raw": (', '    "venues_raw": (\n        "x",\n    ),\n    "derivative_odds_raw": (',
     f"{COMPACT_T}::test_only_allowlisted_sources_may_be_compacted", None),
    # ⭐ "a compaction that would orphan a reader must refuse": a NEW, unvetted reader of the
    #    flattened output must be DETECTED, not silently inherited.
    ("a new UNVETTED reader of stg_derivative_odds appears — compaction must refuse it",
     RUN_W1, "def _build_w3pre(",
     "def _unvetted_new_reader(conn):\n"
     "    return conn.execute('select * from stg_derivative_odds').fetchall()\n\n\n"
     "def _build_w3pre(",
     f"{COMPACT_T}::test_the_derivative_reader_lists_are_still_exhaustive", None),

    # ── ② the move: the anti-orphan and anti-silent-freeze guards ───────────────────────────
    ("the tick goes back to building the full W3pre tier inside its 480 s leg",
     INTRADAY, _TICK_FLAG,
     '    for _flag, _what in (("--w3pre-only", "game-state flatten"),',
     f"{LAKE2}::test_the_tick_asks_for_the_scoped_build_and_the_daily_asks_for_the_full_tier",
     '"--w3pre-serving-only", "game-state flatten"'),
    ("the DAILY builder narrows too — the moved models lose their last builder (ORPHANED)",
     DAILY, _DAILY_CALL,
     '    _run_script(context, "run_w1_lakehouse.py", ["--w3pre-serving-only"], timeout=1800)',
     f"{LAKE2}::test_the_daily_build_still_owns_every_model_the_tick_drops",
     '["--w3pre-only"], timeout=1800'),
    ("a moved table loses its freshness SLA — a stopped daily builder would freeze it silently",
     FRESH, '        name="stg_derivative_odds",', '        name="stg_derivative_odds_RENAMED",',
     f"{LAKE2}::test_every_moved_model_is_watched_or_has_a_stated_exemption[stg_derivative_odds]",
     'name="stg_derivative_odds",'),
    ("the daily cap and the timeout the daily op enforces drift apart (one thing, two owners)",
     DAILY, _DAILY_CALL,
     '    _run_script(context, "run_w1_lakehouse.py", ["--w3pre-only"], timeout=900)',
     f"{LAKE2}::test_the_daily_cap_matches_the_timeout_the_daily_op_actually_passes",
     '["--w3pre-only"], timeout=1800'),
    ("the tick's scope drops the serving-critical model (the MLB-INC-0904 outage, re-armed)",
     RUN_W1, 'W3PRE_INTRADAY_MODELS = [\n    "stg_statsapi_games",',
     'W3PRE_INTRADAY_MODELS = [\n    "stg_oddsapi_events",',
     f"{LAKE2}::test_the_intraday_scope_is_a_subset_that_keeps_the_serving_critical_model", None),
    ("the full tier is graded against the TICK cap again — a permanently-wrong OVER every day",
     RUN_W1, "                 leg_timeout_seconds: int = W3PRE_DAILY_TIMEOUT_SECONDS) -> None:",
     "                 leg_timeout_seconds: int = LEG_TIMEOUT_SECONDS) -> None:",
     f"{LAKE2}::test_the_full_tier_is_graded_against_the_daily_cap_unless_the_tick_asks_otherwise",
     "leg_timeout_seconds: int = W3PRE_DAILY_TIMEOUT_SECONDS"),

    # ⭐ The INC-31 ordering guard was RE-ANCHORED onto the new flag, not weakened — so prove it
    # still fails when the W3pre leg disappears from the tick altogether.
    ("the tick loses its W3pre build entirely (the re-anchored ordering guard must still fail)",
     INTRADAY, _TICK_FLAG, '    for _flag, _what in ((',
     f"{ORDER_T}::test_intraday_schedule_rebuilds_lineups_wide_after_games_and_before_refresh",
     '"--w3pre-serving-only", "game-state flatten"'),

    # ── ⭐ THE HARD LINE: INC-41 semantics are untouched and no alert is silenced ────────────
    ("the freshness check stops firing on a frozen artifact (an alert IS silenced)",
     FRESH, "    if lag > contract.max_lag_minutes:", "    if False:",
     f"{INC0904_T}::test_a_frozen_artifact_still_fires",
     "if lag > contract.max_lag_minutes:"),
]

# Mutations that must leave the named test GREEN. A harness where every mutation reddens every
# test is measuring its own blast radius, not the guards.
CONTROLS = [
    ("breaking eval's dedup does not disturb the tick-scope guard",
     EVAL, _EVAL_DEDUP, "        FROM ranked WHERE rn >= 1",
     f"{LAKE2}::test_the_tick_asks_for_the_scoped_build_and_the_daily_asks_for_the_full_tier"),
    ("reverting the tick's scope does not disturb the compaction reader measurement",
     INTRADAY, _TICK_FLAG,
     '    for _flag, _what in (("--w3pre-only", "game-state flatten"),',
     f"{LAKE2}::test_eval_cross_market_closing_selection_is_unchanged_by_the_duplicate_window"),
    ("breaking the mart's dedup does not disturb the freshness-coverage guard",
     MART, _MART_DEDUP, "    where snap_rank >= 1",
     f"{LAKE2}::test_every_moved_model_is_watched_or_has_a_stated_exemption[stg_derivative_odds]"),
    ("narrowing the DAILY builder does not disturb the INC-41 frozen-artifact semantics",
     DAILY, _DAILY_CALL,
     '    _run_script(context, "run_w1_lakehouse.py", ["--w3pre-serving-only"], timeout=1800)',
     f"{INC0904_T}::test_a_frozen_artifact_still_fires"),
]

_BAK = ".mlb_lake2_red_proof.bak"


def _invalidate_bytecode(path: Path) -> None:
    """CPython validates bytecode on (source mtime, source size), so a SAME-LENGTH mutation
    restored within the same second can leave a poisoned .pyc that reads correct in source."""
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(path.stem + ".*.pyc"):
            pyc.unlink(missing_ok=True)
    try:
        os.utime(path, None)
    except OSError:
        pass


def _restore_stale_backups() -> None:
    for rel in {b[1] for b in BREAKS} | {c[1] for c in CONTROLS}:
        bak = REPO / (rel + _BAK)
        if bak.exists():
            (REPO / rel).write_text(bak.read_text())
            bak.unlink()
            print(f"RESTORED     {rel} from a stale backup (a previous run died mid-mutation)")


def _pytest(test: str) -> bool:
    """True == the selector passed. ⚠️ run under the PROJECT interpreter: a bare `python3` with
    no pytest exits non-zero, which a naive harness reads as a (false) RED."""
    proc = subprocess.run(
        ["uv", "run", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    # NOT-SELECTED control: a selector that matches NOTHING also exits non-zero in recent pytest,
    # but an older one exits 0 — either way "no tests ran" must never read as a verdict.
    if "no tests ran" in proc.stdout or "ERROR" in proc.stdout.splitlines()[:1]:
        print(f"SETUP-ERROR  selector matched no tests: {test}")
        return False
    return proc.returncode == 0


def _apply(rel: str, old: str, new: str, label: str) -> tuple[Path, str] | None:
    path = REPO / rel
    original = path.read_text()
    occurrences = original.count(old)
    if occurrences != 1:
        print(f"SETUP-ERROR  {label}\n             anchor occurs {occurrences}x in {rel} "
              f"(need exactly 1) — the proof is stale/ambiguous, NOT passing")
        return None
    (REPO / (rel + _BAK)).write_text(original)
    path.write_text(original.replace(old, new, 1))
    return path, original


def main() -> int:
    _restore_stale_backups()
    failures: list[str] = []

    print("── baseline (every selector must be GREEN before any mutation) ──────────")
    for test in sorted({b[4] for b in BREAKS} | {c[4] for c in CONTROLS}):
        if not _pytest(test):
            print(f"BASELINE ❌  {test}")
            failures.append(f"(baseline) {test}")
    if failures:
        print("\nthe guard suite is RED on unmodified source — fix that first")
        return 1
    print("BASELINE ✅  every selector green on unmodified source\n")

    print("── breaks (each MUST go RED) ────────────────────────────────────────────")
    for label, rel, old, new, test, gone in BREAKS:
        applied = _apply(rel, old, new, label)
        if applied is None:
            failures.append(label)
            continue
        path, original = applied
        try:
            mutated = path.read_text()
            assert mutated != original, f"mutation did not land for {label}"
            if gone is not None and gone in mutated:
                print(f"SETUP-ERROR  {label}\n             {gone!r} survived the mutation — the "
                      "break does not move the asserted predicate, NOT passing")
                failures.append(label)
                continue
            red = not _pytest(test)
        finally:
            path.write_text(original)
            _invalidate_bytecode(path)
            (REPO / (rel + _BAK)).unlink(missing_ok=True)
        print(f"{'RED  ✅' if red else 'GREEN ❌'}  {label}")
        if not red:
            failures.append(label)

    print("\n── NOT-SELECTED controls (each MUST stay GREEN) ─────────────────────────")
    for label, rel, old, new, test in CONTROLS:
        applied = _apply(rel, old, new, label)
        if applied is None:
            failures.append(label)
            continue
        path, original = applied
        try:
            green = _pytest(test)
        finally:
            path.write_text(original)
            _invalidate_bytecode(path)
            (REPO / (rel + _BAK)).unlink(missing_ok=True)
        print(f"{'GREEN ✅' if green else 'RED  ❌'}  {label}")
        if not green:
            failures.append(f"(control) {label}")

    print()
    if failures:
        print(f"❌ {len(failures)} case(s) did not behave as required:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ all {len(BREAKS)} breaks went RED and all {len(CONTROLS)} controls stayed GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
