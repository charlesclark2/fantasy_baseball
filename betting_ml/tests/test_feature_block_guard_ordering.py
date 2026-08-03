"""Guard — the served-feature-block coverage check must run DOWNSTREAM of its own producer.

WHAT HAPPENED (2026-08-03, recurring near-daily false CRITICAL):

    `check_feature_block_coverage_op` sat at s5f in daily_ingestion_job, immediately after
    check_odds_coverage_op and ~13 ops BEFORE `dbt_umpire_feature_rebuild`. But that op is
    exactly what BUILDS two of the blocks the guard asserts on — its dbt selector rebuilds

        mart_bullpen_effectiveness → feature_pregame_team_features
                                   → feature_pregame_game_features{,_raw}

    which is what populates {home,away}_bp_eb_xwoba (the `bullpen_eb` block) and
    ump_accuracy_zscore (the `umpire` block).

    So the guard measured a store that was one FOLD behind and reported, as a "WHOLE-SLATE
    OUTAGE", a date that the very same run healed a few ops later:

        the 2026-08-01 run flagged 2026-07-30 at 0%
        the 2026-08-03 run flagged 2026-08-01 at 0%

    Both dates read 100% in the served store (Snowflake AND the S3 parquet, which agreed
    exactly) once the run finished. Snowflake/S3 agreement is also what ruled out the
    INC-31 ext-table VALUE:-case class the alert banner guesses at: a case bug shows the S3
    parquet healthy and Snowflake NULL, not both dead.

WHY THE FIX IS "MOVE THE GUARD", NOT "WIDEN THE EXEMPTION":
    Bumping _DATE_OUTAGE_SKIP_NEWEST from 1 to 2 would have silenced the page while ALSO
    blinding the guard for an extra day, and it would have quietly redefined an exemption
    whose documented meaning is "today's games have not been played yet". Measuring after
    the producer keeps the exemption honest and restores a full-strength detector.

    The guard stays UPSTREAM of predict_today_morning, so FEATURE_COVERAGE_STRICT=1 keeps
    its power to stop a genuinely amputated slate from being scored.

⚠️ THESE ASSERT THE DEPENDENCY, NOT THE SOURCE-LINE ORDER. daily_ingestion_job runs under
`in_process_executor`, which executes in TOPOLOGICAL order — so an op written lower in the
file but wired `start=<something early>` would still run early. A line-number test would be
vacuous. Each test below pins one edge of the graph and is RED-proven independently.

⚠️ Comment lines are stripped before matching: the fix's own explanatory comment names both
`check_feature_block_coverage_op` and `s5f`, so a prose-only match would pass on source with
the wiring deleted (the INC-38 prose-satisfiable-guard lesson).

SOURCE-INSPECTION, not an import: `pipeline/__init__.py` reads the dbt manifest, absent in the
fast gate, so importing `pipeline` here would crash at COLLECTION rather than skip (E11.23).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JOB = REPO_ROOT / "pipeline" / "jobs" / "daily_ingestion_job.py"
DAILY_OPS = REPO_ROOT / "pipeline" / "ops" / "daily_ingestion_ops.py"


def _code_only(path: Path) -> str:
    """Source with whole-line comments removed, so prose can never satisfy a guard."""
    return "\n".join(
        line for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


def _assigned_from(code: str, callee: str) -> str:
    """The variable a single `<var> = <callee>(...)` call binds to."""
    hits = re.findall(rf"^\s*(\w+)\s*=\s*{callee}\(", code, re.MULTILINE)
    assert len(hits) == 1, (
        f"expected exactly one `<var> = {callee}(...)` in {JOB.name}, found {hits}"
    )
    return hits[0]


def _start_arg(code: str, callee: str) -> str:
    """The variable passed as `start=` to a single call of `callee`."""
    hits = re.findall(rf"{callee}\(\s*start\s*=\s*(\w+)\s*\)", code)
    assert len(hits) == 1, (
        f"expected exactly one `{callee}(start=<var>)` in {JOB.name}, found {hits}"
    )
    return hits[0]


def test_coverage_guard_runs_downstream_of_its_own_producer():
    """The guard must take its `start` from dbt_umpire_feature_rebuild.

    This is THE regression: at s5f the guard ran before the op that folds bullpen_eb /
    umpire into feature_pregame_game_features, so it flagged a date the same run healed.
    """
    code = _code_only(JOB)
    producer_out = _assigned_from(code, "dbt_umpire_feature_rebuild")
    guard_start = _start_arg(code, "check_feature_block_coverage_op")
    assert guard_start == producer_out, (
        f"check_feature_block_coverage_op is wired start={guard_start!r} but must be wired "
        f"start={producer_out!r} (the dbt_umpire_feature_rebuild output). It asserts on blocks "
        f"that op BUILDS — running it earlier makes it flag a date the same run heals "
        f"(2026-08-03: flagged 08-01 at 0%, which finished the run at 100%)."
    )


def test_coverage_guard_still_gates_predict():
    """Moving the guard later must not drop it off the pre-predict path.

    FEATURE_COVERAGE_STRICT=1 promotes the guard to HALT; that is only meaningful while it
    is upstream of predict_today_morning. Isolating fixture for the second clause of the
    invariant — the producer edge above can hold while this one is broken.
    """
    code = _code_only(JOB)
    guard_out = _assigned_from(code, "check_feature_block_coverage_op")
    predict_start = _start_arg(code, "predict_today_morning")
    assert predict_start == guard_out, (
        f"predict_today_morning is wired start={predict_start!r}; it must chain off the "
        f"coverage guard's output {guard_out!r} so FEATURE_COVERAGE_STRICT=1 can still stop a "
        f"genuinely amputated slate from being scored."
    )


def test_coverage_guard_is_not_back_in_the_early_ingest_chain():
    """The old s5f slot fed ingest_weather — pin that it no longer does.

    Catches a revert that re-hoists the guard while leaving the later wiring cosmetically
    present (which would otherwise create two calls and trip the count assertions above in a
    less legible way).
    """
    code = _code_only(JOB)
    guard_out = _assigned_from(code, "check_feature_block_coverage_op")
    weather_start = _start_arg(code, "ingest_weather")
    assert weather_start != guard_out, (
        "ingest_weather chains off the coverage guard — the guard has been hoisted back into "
        "the early ingest chain (the s5f position), upstream of the op that builds the blocks "
        "it checks. See the 2026-08-03 false-CRITICAL note in daily_ingestion_job."
    )


def test_the_producer_still_builds_the_blocks_the_guard_asserts_on():
    """The ordering only helps while dbt_umpire_feature_rebuild really builds these models.

    If a future change strips mart_bullpen_effectiveness / feature_pregame_game_features out
    of that op's selector, the guard would again be reading a store nothing upstream of it
    populated — the same defect wearing different clothes. Pin the selector, not just the edge.
    """
    ops = _code_only(DAILY_OPS)
    start = ops.find("def dbt_umpire_feature_rebuild")
    assert start != -1, "dbt_umpire_feature_rebuild not found in daily_ingestion_ops.py"
    body = ops[start:start + 4000]
    for model in (
        "mart_bullpen_effectiveness",       # → bp_eb_xwoba (the `bullpen_eb` block)
        "feature_pregame_team_features",    # carries bp_eb_xwoba into the aggregator
        "feature_pregame_umpire_features",  # → ump_accuracy_zscore (the `umpire` block)
        "feature_pregame_game_features",    # the served table the guard reads
    ):
        assert f'"{model}"' in body, (
            f"dbt_umpire_feature_rebuild no longer selects {model!r}. The coverage guard is "
            f"wired downstream of this op precisely because it builds that model; dropping it "
            f"re-opens the 2026-08-03 false-CRITICAL (guard asserts on an unbuilt block)."
        )
