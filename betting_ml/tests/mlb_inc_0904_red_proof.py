"""RED proof for the MLB-INC-0904 guards — `uv run python betting_ml/tests/mlb_inc_0904_red_proof.py`.

Both halves of this incident are guarded by assertions that look like they could be satisfied by
accident: an ORDER (a list whose elements are all still present) and a THRESHOLD (a function that
returns a string). Neither has a visible failure signature in source, so each claim is proved by
re-introducing the real regression and requiring the named test to go RED.

The four ways a RED proof lies, all guarded here:
  * the mutation never LANDS (E11.24 #682)            → the source is re-read and diffed.
  * the anchor is NOT UNIQUE (E11.24 prediction_log)  → each anchor must occur exactly once.
  * the mutation lands but does not MOVE the asserted predicate (E11.24 #815) → where the
    assertion is "token X is present", the post-mutation source is checked for X's ABSENCE.
  * the harness reports RED for the wrong reason      → a BASELINE run must be GREEN first, and
    NOT-SELECTED controls prove each break is TARGETED rather than a blanket failure.

⭐ The freshness break below is the one that matters most. The spec's hard line is that this
incident must not weaken the INC-41 content-timestamp semantics to make an alert quiet, so
"a frozen artifact still fires" is proved falsifiable rather than asserted.

Restores every file in a `finally`, and restores stale backups at START-UP, so an interrupted run
can neither leave a break on disk nor be one `git add` from committing it.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_mlb_inc_0904_w3pre_priority.py"

RUN_W1 = "scripts/run_w1_lakehouse.py"
BUDGET = "betting_ml/monitoring/intraday_tick_budget.py"
FRESH = "betting_ml/monitoring/artifact_freshness.py"

_ORDER_GAMES_FIRST = (
    '    "stg_statsapi_games",    # ← lakehouse_raw/monthly_schedule   (⚠ SERVING: 90-min SLA — FIRST)\n'
    '    "stg_oddsapi_odds",      # ← lakehouse_raw/mlb_odds_raw       (daily cadence; no intraday reader)\n'
)
_ORDER_GAMES_SECOND = (
    '    "stg_oddsapi_odds",      # ← lakehouse_raw/mlb_odds_raw       (daily cadence; no intraday reader)\n'
    '    "stg_statsapi_games",    # ← lakehouse_raw/monthly_schedule   (⚠ SERVING: 90-min SLA — FIRST)\n'
)

# (label, file, old, new, "<test file>::<test name>", gone_token_or_None)
BREAKS = [
    # ── half 1: the ORDER that decides which table a timeout kills ──────────────────────────
    ("the serving-critical table is demoted below the odds staging again (the incident)",
     RUN_W1, _ORDER_GAMES_FIRST, _ORDER_GAMES_SECOND,
     f"{TEST}::test_serving_critical_table_is_built_first", None),
    ("the tier is 'sped up' by dropping a model instead of reordering it",
     RUN_W1,
     '    "stg_derivative_odds",   # ← lakehouse_raw/derivative_odds_raw (eval/CLV only — daily)\n',
     "",
     f"{TEST}::test_the_reorder_did_not_quietly_drop_a_model",
     '"stg_derivative_odds",   # ←'),

    # ── half 2: the THRESHOLD that makes growth surface before it kills a tick ──────────────
    ("an over-budget tier stops grading OVER (the build exceeding its budget goes silent)",
     BUDGET, "    if fraction >= 1.0:", "    if False:",
     f"{TEST}::test_an_over_budget_tier_surfaces_and_names_its_worst_model",
     "if fraction >= 1.0:"),
    ("a tier that measured NOTHING is scored healthy (NF1.7 (a))",
     BUDGET,
     '            "UNEVALUATED", 0.0, 0.0, None, 0.0,',
     '            "OK", 0.0, 0.0, None, 0.0,',
     f"{TEST}::test_an_unmeasured_tier_is_not_scored_healthy",
     '"UNEVALUATED", 0.0, 0.0, None, 0.0,'),
    ("the warn threshold is moved up until it only fires on the way past the cap",
     BUDGET, "W3PRE_TIER_WARN_FRACTION = 0.60", "W3PRE_TIER_WARN_FRACTION = 0.98",
     f"{TEST}::test_the_warn_threshold_leaves_real_headroom", None),

    # ── the budget check is WIRED *and* INVOKED (NF-C0e) ────────────────────────────────────
    ("run_w1_lakehouse imports the budget policy but stops CALLING it",
     RUN_W1,
     "    _v = w3pre_tier_verdict(timings)",
     '    from betting_ml.monitoring.intraday_tick_budget import W3preTierVerdict\n'
     '    _v = W3preTierVerdict("OK", 0.0, 0.0, None, 0.0, "stubbed")',
     f"{TEST}::test_build_w3pre_actually_invokes_the_verdict",
     "w3pre_tier_verdict(timings)"),
    ("_build_w3pre stops recording per-model timings (the verdict goes vacuously UNEVALUATED)",
     RUN_W1, "        timings[model] = _elapsed\n", "",
     f"{TEST}::test_build_w3pre_records_a_timing_for_every_model_it_builds",
     "timings[model] = _elapsed"),

    # ── ⭐ THE HARD LINE: the INC-41 freshness semantics must still fire ─────────────────────
    ("the freshness check stops firing on a frozen artifact (the alert is silenced)",
     FRESH, "    if lag > contract.max_lag_minutes:", "    if False:",
     f"{TEST}::test_a_frozen_artifact_still_fires",
     "if lag > contract.max_lag_minutes:"),
]

# (label, file, old, new, test, ) — mutations that must leave the named test GREEN. These prove
# each break above is TARGETED: a harness where every mutation reddens every test is measuring
# nothing but its own blast radius.
CONTROLS = [
    ("demoting the serving table does not disturb the freshness semantics",
     RUN_W1, _ORDER_GAMES_FIRST, _ORDER_GAMES_SECOND,
     f"{TEST}::test_a_frozen_artifact_still_fires"),
    ("demoting the serving table does not change the tier's MEMBERSHIP",
     RUN_W1, _ORDER_GAMES_FIRST, _ORDER_GAMES_SECOND,
     f"{TEST}::test_the_reorder_did_not_quietly_drop_a_model"),
    ("weakening the freshness check does not disturb the build-order guard",
     FRESH, "    if lag > contract.max_lag_minutes:", "    if False:",
     f"{TEST}::test_serving_critical_table_is_built_first"),
]

_BAK = ".mlb_inc_0904_red_proof.bak"


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
    """True == the selector passed."""
    proc = subprocess.run(
        ["uv", "run", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
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

    # BASELINE: the suite must be GREEN before any mutation, or every "RED" below is meaningless.
    print("── baseline ─────────────────────────────────────────────────────────────")
    if not _pytest(TEST):
        print("BASELINE ❌  the guard suite is RED on unmodified source — fix that first")
        return 1
    print("BASELINE ✅  the guard suite is green on unmodified source\n")

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
