"""RED proof for NF-INFRA1's guards — `uv run python betting_ml/tests/nf_infra1_red_proof.py`.

The bug NF-INFRA1 fixes produced NO error and NO log line for 19 days: `sports_nfl_sleeper_injuries_job`
reported SUCCESS on 19 consecutive daily runs while its Delta table held one 19-day-old commit. A
test suite over a defect whose signature is "everything looks fine" is worth exactly its
falsifiability, so each claim below is proved by re-introducing a real defect and requiring the
named test to go RED.

Applies each break IN-PROCESS and ASSERTS THE SOURCE ACTUALLY CHANGED before running pytest — a red
proof whose mutation silently no-ops reports a triumphant, false "the guard caught it" (the E11.24
#682 lesson). Restores the file in a `finally`, so an interrupted run cannot leave a break on disk.

⭐ THIS HARNESS ALREADY EARNED ITS KEEP: on its first run, case "zero-row write downgraded to a log
line" came back GREEN. The guard had asserted `"raise Exception" in ast.unparse(op)` — satisfied by
the op's OTHER raises, so deleting the one it named changed nothing (the NF-D17 vacuity mode). It is
now asserted structurally, on the `if not n:` branch itself. Nothing but a mutation run finds that.

⚠️ NOT SCHEDULED — the same known limitation `nf_fresh2_red_proof.py` records: like the repo's other
`*_red_proof.py` harnesses this runs only when somebody types the command, and E9.64 measured what
that costs. Wiring the Python red proofs into a scheduled workflow is worth doing and is
deliberately not smuggled into this story.

Runtime ~60s. Prints one line per case; exits non-zero if ANY break stays green.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATH_TEST = "betting_ml/tests/test_nf_infra1_sports_duckdb_path.py"
SLEEP_TEST = "betting_ml/tests/test_nf_infra1_sleeper_hardening.py"

JOB = "pipeline/jobs/sports_nfl_sleeper_injuries_job.py"
RSP = "quant_sports_intel_models/football/nfl/fantasy/run_season_projection.py"
ROOKIE_TEST = "betting_ml/tests/test_nf_infra1_rookie_projection_source.py"
SRC = "quant_sports_intel_models/football/nfl/fantasy/sleeper_injuries_source.py"
FRESH = "betting_ml/monitoring/sports_delta_freshness.py"
COMPOSE = "services/dagster/aws/docker-compose.yml"

# (label, file, old, new, "<test file>::<test name>")
BREAKS = [
    # ── layer 1: the op must fail loud ──────────────────────────────────────────────────────
    ("the except handler swallows again (the literal NF-FRESH1 bug)", JOB,
     '              severity="CRITICAL", dedup_key="nfl_sleeper_injuries:fetch_failed")\n        raise\n',
     '              severity="CRITICAL", dedup_key="nfl_sleeper_injuries:fetch_failed")\n        return\n',
     f"{SLEEP_TEST}::test_every_except_handler_in_the_ingest_op_re_raises"),
    ("the missing-DuckDB precondition is removed", JOB,
     "    if not duckdb_path.exists():", "    if False:",
     f"{SLEEP_TEST}::test_a_missing_sports_duckdb_RAISES_instead_of_reporting_a_green_run"),
    ("a zero-row write is downgraded to a log line", JOB,
     '        raise Exception(f"NFL Sleeper injuries wrote 0 rows for season {season}")',
     '        context.log.warning("wrote 0 rows")',
     f"{SLEEP_TEST}::test_a_zero_row_write_is_an_error_not_a_log_line"),
    # ⭐ This case is why the harness exists. Its first form mutated "mounted at {BOX_VOLUME_DIR}"
    # and stayed GREEN — the guard's `BOX_VOLUME_DIR in remedy` clause was satisfied incidentally by
    # BOX_DUCKDB_PATH, which contains that directory as a substring. The guard now asserts the
    # VOLUME NAME, and the break removes it.
    ("the page stops naming the volume the operator has to look for",
     "betting_ml/utils/sports_duckdb.py",
     "f\"`sports_duckdb` named volume mounted at {BOX_VOLUME_DIR} and is materialized by running \"",
     "f\"place it is kept and is materialized by running \"",
     f"{SLEEP_TEST}::test_the_missing_duckdb_page_names_the_volume_and_the_job_that_creates_it"),

    # ── layer 2: a degraded land must be REFUSED, not written ───────────────────────────────
    ("the resolution floor clause is deleted (native-gsis-only lands)", SRC,
     "    if pct < float(min_pct_resolved):", "    if False:",
     f"{SLEEP_TEST}::test_a_collapsed_crosswalk_refuses_the_write"),
    ("an empty feed is written anyway", SRC,
     '        return {"verdict": "EMPTY_FEED", "should_write": False,',
     '        return {"verdict": "EMPTY_FEED", "should_write": True,',
     f"{SLEEP_TEST}::test_an_empty_feed_refuses_the_write_and_is_critical"),
    ("coverage is measured POST-drop (the flattering 100% again)", SRC,
     '        "n_fetched": n_fetched,', '        "n_fetched": n_resolved,',
     f"{SLEEP_TEST}::test_coverage_is_pre_drop_so_a_collapsed_crosswalk_is_VISIBLE"),

    # ── layer 3: the ARTIFACT is asserted, not the producer (INC-41) ────────────────────────
    ("a stale Delta log never fires", FRESH,
     "    if lag_hours > contract.max_lag_hours:", "    if lag_hours > 1e9:",
     f"{SLEEP_TEST}::test_the_19_day_freeze_this_exists_to_catch_is_critical"),
    ("an unreadable Delta log is scored HEALTHY (NF1.7(a))", FRESH,
     '        return {"name": contract.name, "verdict": "UNKNOWN", "severity": "WARN",',
     '        return {"name": contract.name, "verdict": "OK", "severity": None,',
     f"{SLEEP_TEST}::test_an_unreadable_delta_log_is_UNVERIFIED_never_healthy"),
    ("an ABSENT row metric is read as zero (pages EMPTY on every healthy commit)", FRESH,
     "    if reading.rows is not None and reading.rows <= 0:", "    if (reading.rows or 0) <= 0:",
     f"{SLEEP_TEST}::test_an_ABSENT_row_metric_is_not_read_as_zero"),
    ("the freshness check is rewired off the ingest, skipping the rebuild edge", JOB,
     "    nfl_sleeper_injuries_freshness_op(start=nfl_sleeper_injuries_rebuild_op(start=landed))",
     "    nfl_sleeper_injuries_rebuild_op(start=landed)\n"
     "    nfl_sleeper_injuries_freshness_op(start=landed)",
     f"{SLEEP_TEST}::test_the_freshness_check_runs_downstream_of_the_land_as_a_graph_edge"),

    # ── layer 4: ONE authoritative path, on a volume that survives a deploy ─────────────────
    ("an owner re-adds its own SPORTS_DUCKDB_PATH default", "pipeline/jobs/sports_dbt_job.py",
     "        **sports_duckdb_env(),",
     '        **os.environ, "SPORTS_DUCKDB_PATH": os.environ.get("SPORTS_DUCKDB_PATH", "/tmp/x.duckdb"),',
     f"{PATH_TEST}::test_only_the_resolver_names_the_env_var_in_code"),
    ("a schedule re-hardcodes a /tmp DuckDB (the fail-open NFL gate)",
     "pipeline/schedules/sports_dbt_schedules.py",
     "    return sports_duckdb_path()", '    return "/tmp/sports_nfl.duckdb"',
     f"{PATH_TEST}::test_no_pipeline_owner_hardcodes_a_deploy_ephemeral_duckdb_path"),
    ("the compose mount point drifts from BOX_VOLUME_DIR", COMPOSE,
     "      - sports_duckdb:/var/lib/credence/sports", "      - sports_duckdb:/opt/sports",
     f"{PATH_TEST}::test_compose_mounts_the_volume_on_codeloc_at_the_resolver_s_directory"),
    ("the named volume declaration is removed (back to deploy-ephemeral)", COMPOSE,
     "\n  sports_duckdb:\n", "\n  #sports_duckdb:\n",
     f"{PATH_TEST}::test_compose_declares_the_named_volume"),
    ("the deploy-time gate is removed from env.required", "services/dagster/aws/env.required",
     "\nSPORTS_DUCKDB_PATH\n", "\n#SPORTS_DUCKDB_PATH\n",
     f"{PATH_TEST}::test_env_required_gates_the_deploy_on_the_path_being_set"),

    # ── layer 5: the rookie feeder must be obtainable on the box (the SECOND instance of the
    #    gitignored-artifact class — it killed the first board build that ever ran there) ────────
    ("the lake fallback is removed (a bare FileNotFoundError on the box again)", RSP,
     "    if _ROOKIE_PARQUET.exists():", "    if True:",
     f"{ROOKIE_TEST}::test_an_absent_local_artifact_falls_back_to_the_lake"),
    ("the lake read is repointed at the wrong tier", RSP,
     'expr = delta(_ROOKIE_LAKE_SOURCE, sport="ncaaf", tier=_ROOKIE_LAKE_TIER)',
     'expr = delta(_ROOKIE_LAKE_SOURCE, sport="ncaaf", tier="raw")',
     f"{ROOKIE_TEST}::test_an_absent_local_artifact_falls_back_to_the_lake"),
    ("the lake is preferred over a present local artifact (laptop boards move silently)", RSP,
     "    if _ROOKIE_PARQUET.exists():", "    if False:",
     f"{ROOKIE_TEST}::test_a_present_local_artifact_is_used_and_the_lake_is_NOT_read"),
    ("an EMPTY lake table builds a rookie-less board instead of refusing", RSP,
     "    if df.empty:", "    if False:",
     f"{ROOKIE_TEST}::test_an_EMPTY_lake_table_refuses_rather_than_building_a_rookieless_board"),
    ("the both-absent error stops naming the box's cure", RSP,
     'f"On the BOX the lake is the only source: check SPORTS_LAKE_REGION=us-east-2 and that "',
     'f"It could not be found. "',
     f"{ROOKIE_TEST}::test_both_sources_absent_raises_a_message_that_names_BOTH_and_the_cure"),
    ("a call site bypasses the resolver and reads the parquet directly", RSP,
     "    rookies_all = load_rookie_projection_frame()",
     "    rookies_all = pd.read_parquet(_ROOKIE_PARQUET)",
     f"{ROOKIE_TEST}::test_no_call_site_reads_the_parquet_directly"),
    ("the per-build cache is removed (three reads, three possible vintages)", RSP,
     "    if _rookie_frame_cache is not None:", "    if False:",
     f"{ROOKIE_TEST}::test_the_frame_is_cached_so_one_build_reads_ONE_vintage"),
]


def main() -> int:
    failures = []
    for label, rel, old, new, test in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if old not in original:
            print(f"SETUP-ERROR  {label}\n             pattern absent from {rel} — the proof is "
                  "stale, NOT passing")
            failures.append(label)
            continue
        path.write_text(original.replace(old, new, 1))
        try:
            # ⭐ The mutation must be OBSERVABLE before the test runs, or "the guard caught it" and
            # "the break never happened" are indistinguishable.
            assert path.read_text() != original, f"mutation did not land for {label}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test, "-q", "--no-header",
                 "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True)
            red = proc.returncode != 0
        finally:
            path.write_text(original)
        print(f"{'RED  ✅' if red else 'GREEN ❌'}  {label}")
        if not red:
            failures.append(label)

    print(f"\n{len(BREAKS) - len(failures)}/{len(BREAKS)} breaks caught")
    if failures:
        print("STAYED GREEN (the guard is vacuous — fix the guard, not the proof):")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("every NF-INFRA1 guard is falsifiable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
