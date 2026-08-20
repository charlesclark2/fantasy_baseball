"""RED proof for the E11.24 P1 guards —
`uv run python betting_ml/tests/e11_24_prediction_log_red_proof.py`.

P1 re-expressed a set of semantics rather than adding a feature: the #885 overwrite rule
moved from `DELETE ... game_pk IN (...)` + INSERT to append-and-dedup over S3 parquet. A
re-anchored guard that quietly stops falsifying is indistinguishable from a deleted one,
so every claim is proved by re-introducing a real regression and requiring the named test
to go RED. Three of the clauses in this suite were VACUOUS on their first cut and were
found here, not by a green run.

Three ways a RED proof lies, all guarded below:
  * the mutation never LANDS (E11.24 #682)            → the source is re-read and diffed.
  * the anchor is NOT UNIQUE (E11.24 prediction_log)  → each anchor must occur exactly once.
  * the mutation lands but does not MOVE the asserted predicate (#815) → where the guard
    asserts "token X is present", the post-mutation source is checked for X's ABSENCE.

Restores every file in a `finally`, and restores stale backups at STARTUP — a run killed
by a signal never reaches `finally`, and a deliberate break left on disk is one `git add`
away from being committed (E11.26).

Runtime ~1-2 min (each case spawns a pytest). Exits non-zero if ANY break stays green.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

STORE_T = "betting_ml/tests/test_e11_24_prediction_log_s3.py"
WIRE_T = "betting_ml/tests/test_e11_24_prediction_log_wiring.py"
WRITE_T = "betting_ml/tests/test_predict_today_write.py"

STORE = "scripts/utils/prediction_log_store.py"
READ = "scripts/utils/lakehouse_read.py"
SCORER = "scripts/predict_today.py"
JOB = "pipeline/jobs/daily_ingestion_job.py"
HEALTH = "scripts/compute_model_health.py"
BACKFILL = "scripts/backfill_prediction_log.py"
MIGRATE = "scripts/migrate_prediction_log_to_s3.py"

# The winner-selection block, mutated wholesale in one case: resolving the winner per
# (game, MARKET) instead of per (game, BATCH) is the subtle wrong answer — it looks
# correct and silently resurrects a market a later batch dropped.
_WINNER_BLOCK = """JOIN (
    SELECT prediction_date, game_pk, loaded_at AS _lt, _part AS _pf
    FROM (
        SELECT prediction_date, game_pk, loaded_at, filename AS _part
        FROM read_parquet('{base}/**/*.parquet', union_by_name=true, filename=true)
    )
    QUALIFY row_number() OVER (
        PARTITION BY prediction_date, game_pk
        ORDER BY loaded_at DESC, _part DESC
    ) = 1
) w
  ON  r.prediction_date = w.prediction_date
  AND r.game_pk         = w.game_pk
  AND r.loaded_at       = w._lt
  AND r._part           = w._pf"""

_WINNER_BLOCK_PER_MARKET = """JOIN (
    SELECT prediction_date, game_pk, market, loaded_at AS _lt, _part AS _pf
    FROM (
        SELECT prediction_date, game_pk, market, loaded_at, filename AS _part
        FROM read_parquet('{base}/**/*.parquet', union_by_name=true, filename=true)
    )
    QUALIFY row_number() OVER (
        PARTITION BY prediction_date, game_pk, market
        ORDER BY loaded_at DESC, _part DESC
    ) = 1
) w
  ON  r.prediction_date = w.prediction_date
  AND r.game_pk         = w.game_pk
  AND r.market IS NOT DISTINCT FROM w.market
  AND r.loaded_at       = w._lt
  AND r._part           = w._pf"""

# (label, file, old, new, "<test file>::<test name>", gone_token_or_None)
BREAKS = [
    # ── the #885 overwrite semantics, re-expressed ──────────────────────────────────
    ("a scoped batch clears the whole date again (THE #885 regression)", STORE,
     "    stale_keys = [] if scoped else list_partition_keys(prediction_date, s3=s3)",
     "    stale_keys = list_partition_keys(prediction_date, s3=s3)",
     f"{STORE_T}::TestOverwriteSemantics::"
     "test_a_sequence_of_scoped_runs_preserves_the_whole_slate",
     "[] if scoped else"),
    ("a full-slate batch stops clearing the previous parts (dropped games resurrect)", STORE,
     "    if stale_keys:\n        _delete_keys(s3, stale_keys)",
     "    if False:\n        _delete_keys(s3, stale_keys)",
     f"{STORE_T}::TestOverwriteSemantics::test_a_full_slate_run_still_clears_dropped_games",
     None),
    ("the full-slate overwrite deletes BEFORE it puts (an empty-read window)", STORE,
     "    stale_keys = [] if scoped else list_partition_keys(prediction_date, s3=s3)\n"
     "    key = _put_part(s3, parquet_rows, prediction_date) if parquet_rows else None\n"
     "    if stale_keys:\n        _delete_keys(s3, stale_keys)",
     "    stale_keys = [] if scoped else list_partition_keys(prediction_date, s3=s3)\n"
     "    if stale_keys:\n        _delete_keys(s3, stale_keys)\n"
     "    key = _put_part(s3, parquet_rows, prediction_date) if parquet_rows else None",
     f"{STORE_T}::TestOverwriteSemantics::"
     "test_a_full_slate_write_lands_before_the_old_parts_are_removed",
     None),
    ("the ownership marker is dropped (an empty scoped run leaves stale rows)", STORE,
     "    for pk in _int_list(scoped_game_pks):\n"
     "        out.append({\n"
     "            **{c: None for c in COLUMNS},\n"
     "            \"prediction_date\": pdate,\n"
     "            \"game_pk\": pk,\n"
     "            \"market\": None,          # the ownership marker\n"
     "            \"loaded_at\": loaded_at,\n"
     "        })\n",
     "",
     f"{STORE_T}::TestOverwriteSemantics::"
     "test_a_scoped_run_that_produced_no_rows_clears_only_its_own_games",
     "the ownership marker"),
    ("the winner is resolved per (game, MARKET) instead of per BATCH", STORE,
     _WINNER_BLOCK, _WINNER_BLOCK_PER_MARKET,
     f"{STORE_T}::TestOverwriteSemantics::"
     "test_a_market_that_disappears_in_a_later_batch_does_not_survive",
     "PARTITION BY prediction_date, game_pk\n"),
    ("the view stops filtering out ownership markers", STORE,
     "WHERE r.market IS NOT NULL", "WHERE 1 = 1",
     f"{STORE_T}::TestOverwriteSemantics::test_ownership_markers_are_never_returned_as_rows",
     "WHERE r.market IS NOT NULL"),

    # ── the dedup's ordering key ────────────────────────────────────────────────────
    ("the stamp reverts to isoformat (variable width — a midnight stamp mis-sorts)", STORE,
     '    return dt.strftime(_STAMP_FMT)', '    return dt.isoformat(sep=" ")',
     f"{STORE_T}::TestStampOrdering::"
     "test_the_stamp_is_fixed_width_so_string_order_is_time_order",
     "dt.strftime(_STAMP_FMT)"),

    # ── the empty-prefix degradation (a monitoring read must not crash) ─────────────
    ("register_view stops degrading to an empty relation on an absent prefix", STORE,
     "    except Exception:  # noqa: BLE001 — an absent/empty prefix is the expected case here",
     "    except ZeroDivisionError:",
     f"{STORE_T}::TestEmptyPrefix::test_register_view_degrades_to_an_empty_typed_relation",
     None),

    # ── one definition of the view, not two ────────────────────────────────────────
    ("lakehouse_read grows its own bare glob for prediction_log (dedup lost)", READ,
     '    if table == "prediction_log":',
     '    if table == "prediction_log_DISABLED":',
     f"{STORE_T}::TestViewIsTheOnlyDefinition::"
     "test_lakehouse_read_serves_the_stores_dedup_body",
     '    if table == "prediction_log":'),

    # ── predict_today: the Snowflake statements must not come back ──────────────────
    ("a Snowflake DELETE against prediction_log reappears", SCORER,
     "    rows = _prediction_log_rows(output_rows, prediction_date)",
     '    _sql = "DELETE FROM baseball_data.config.prediction_log WHERE prediction_date = 1"\n'
     "    rows = _prediction_log_rows(output_rows, prediction_date)",
     f"{WRITE_T}::TestSnowflakePredictionLogIsGone::"
     "test_no_delete_against_the_snowflake_prediction_log",
     None),
    ("the intraday UPDATE sweeps come back", SCORER,
     "    rows = _prediction_log_rows(output_rows, prediction_date)",
     '    _sql = "UPDATE baseball_data.config.prediction_log SET actual_outcome = 1"\n'
     "    rows = _prediction_log_rows(output_rows, prediction_date)",
     f"{WRITE_T}::TestSnowflakePredictionLogIsGone::test_no_intraday_update_sweeps",
     None),
    ("main() stops scoping the write (every scoped run overwrites the date)", SCORER,
     "        _write_prediction_log(output_rows, target_date,\n"
     "                              scoped_game_pks=prediction_log_scope)",
     "        _write_prediction_log(output_rows, target_date)",
     f"{WRITE_T}::TestPredictionLogScopeIsWiredFromMain::"
     "test_main_passes_a_scope_to_the_writer",
     "scoped_game_pks=prediction_log_scope"),
    ("the writer stops delegating to the store (a second implementation appears)", SCORER,
     "    from scripts.utils import prediction_log_store as _pred_log",
     "    import json as _pred_log_placeholder  # noqa: F401",
     f"{WRITE_T}::TestPredictionLogScopeIsWiredFromMain::test_the_writer_delegates_to_the_store",
     # NOT the bare identifier: the migration's explanatory COMMENTS name the module too,
     # and the guard strips comment lines — so the import line is the predicate that moves.
     "from scripts.utils import prediction_log_store as _pred_log"),
    ("the EV formula drifts", SCORER,
     "            ev = model_prob * (decimal_odds - 1) - (1 - model_prob) if model_prob is not None else None",
     "            ev = model_prob * decimal_odds if model_prob is not None else None",
     f"{WRITE_T}::TestPredictionLogRowProjection::"
     "test_derives_ev_from_model_prob_and_decimal_odds",
     None),

    # ── INC-25: the reader must sit downstream of its producer ─────────────────────
    ("the daily job runs compute_model_health BEFORE its own producer again", JOB,
     "    s22 = backfill_prediction_log(start=s21)\n    compute_model_health(start=s22)",
     "    s22 = compute_model_health(start=s21)\n    backfill_prediction_log(start=s22)",
     f"{WIRE_T}::TestDailyJobOrdering::test_model_health_depends_on_the_backfill",
     None),

    # ── compute_model_health ───────────────────────────────────────────────────────
    ("the S3 reader is defined but never invoked (wired != invoked)", HEALTH,
     "    rows = _fetch_prediction_log(market, window_start, run_date, model_version)",
     "    rows = []",
     f"{WIRE_T}::TestModelHealthReadsS3::test_the_reader_is_actually_invoked",
     # the CALL, not the def — `_fetch_prediction_log(market` also matches its signature.
     "rows = _fetch_prediction_log("),
    ("the project-root sys.path insert is dropped (a runtime-only ImportError)", HEALTH,
     "if str(_PROJECT_ROOT) not in sys.path:",
     "if False:",
     f"{WIRE_T}::TestModelHealthReadsS3::test_the_project_root_is_on_sys_path",
     # No `gone` token: `sys.path.insert(...)` SURVIVES inside the dead branch, which is
     # exactly why a source scan for it was a weak guard and the clause is behavioural.
     None),

    # ── backfill: the bound that keeps it off today's partition ────────────────────
    ("the candidate bound becomes inclusive (today's partition is reachable)", BACKFILL,
     "        WHERE prediction_date < ?", "        WHERE prediction_date <= ?",
     f"{WIRE_T}::TestBackfillCannotReachTodaysPartition::"
     "test_the_candidate_query_is_strictly_before_the_bound",
     # the SQL constant's indented form — the bare string also appears inside the
     # `.replace()` that appends the lower bound.
     "        WHERE prediction_date < ?"),
    ("the default bound becomes the UTC day (INC-22)", BACKFILL,
     "    end = date.fromisoformat(args.end) if args.end else current_game_date()",
     "    end = date.fromisoformat(args.end) if args.end else date.today()",
     f"{WIRE_T}::TestBackfillCannotReachTodaysPartition::"
     "test_the_default_bound_is_the_current_baseball_day",
     "current_game_date()"),
    ("the commence_time cast is dropped (INC-23 / E9.52)", BACKFILL,
     "           moe.commence_time::timestamp AS commence_ts",
     "           moe.commence_time AS commence_ts",
     f"{WIRE_T}::TestBackfillCannotReachTodaysPartition::"
     "test_a_commence_time_comparison_casts_the_string_column",
     "commence_time::timestamp"),
    ("a Snowflake UPDATE sweep is restored in the backfill", BACKFILL,
     "def _connect():",
     '_LEGACY = "UPDATE baseball_data.config.prediction_log SET actual_outcome = 1"\n\n\n'
     "def _connect():",
     f"{WIRE_T}::TestBackfillIsSnowflakeFree::test_no_update_statements_survive",
     None),

    # ── the one-time migration ─────────────────────────────────────────────────────
    ("the repair copies daily_model_predictions' POSTERIOR kelly (silently ~0)", MIGRATE,
     "        \"kelly_fraction\":            (compute_kelly(compute_edge(model_prob, mkt), mkt)\n"
     "                                      if model_prob is not None and mkt else None),",
     "        \"kelly_fraction\":            row[\"h2h_kelly_fraction\"],",
     f"{WIRE_T}::TestMigrationReconstruction::test_kelly_is_recomputed_not_copied",
     # the projection line, not the identifier — `_project`'s docstring explains the trap
     # and names both functions (the guard strips docstrings; this check reads raw source).
     '"kelly_fraction":            (compute_kelly(compute_edge(model_prob, mkt), mkt)'),
    ("the repair overwrites surviving Snowflake rows instead of adding missing keys", MIGRATE,
     "        added = [_project(r) for r in candidates if _key(r) not in have]",
     "        added = [_project(r) for r in candidates]",
     f"{WIRE_T}::TestMigrationReconstruction::test_the_repair_only_adds_missing_keys",
     "_key(r) not in have"),

    # ── the loaded_at coercion (the defect that killed the first real migration run) ──
    ("canonical_stamp stops coercing a datetime (pyarrow: 'Expected bytes, got ...')", STORE,
     "    if isinstance(value, datetime):\n        return utc_stamp(value)\n",
     "",
     f"{STORE_T}::TestLoadedAtCoercion::"
     "test_a_datetime_loaded_at_is_coerced_to_the_canonical_string",
     # NOT the `isinstance` line — `_iso_date` and `_as_date` carry it too (3 occurrences).
     "        return utc_stamp(value)"),
    ("normalise_rows stops routing loaded_at through the coercion", STORE,
     '            "loaded_at":                 canonical_stamp(r.get("loaded_at"), loaded_at),',
     '            "loaded_at":                 r.get("loaded_at") or loaded_at,',
     f"{STORE_T}::TestLoadedAtCoercion::test_a_datetime_row_actually_serialises",
     "canonical_stamp(r.get"),
    ("rows_to_arrow_table loses the named type check (back to pyarrow's opaque error)", STORE,
     "    for col in (\"market\", \"model_version\", \"loaded_at\"):",
     "    for col in ():",
     f"{STORE_T}::TestLoadedAtCoercion::test_a_hand_built_row_with_a_datetime_fails_by_NAME",
     None),
    ("_snowflake_rows stops canonicalising at the read boundary", MIGRATE,
     '    for r in rows:\n        r["loaded_at"] = pred_log.canonical_stamp(r["loaded_at"])\n',
     "",
     f"{WIRE_T}::TestMigrationReconstruction::"
     "test_snowflake_loaded_at_is_canonicalised_at_the_read_boundary",
     'r["loaded_at"] = pred_log.canonical_stamp'),
    ("--dry-run stops serialising (it validates parity and nothing else)", MIGRATE,
     "            pred_log.rows_to_arrow_table(parquet_rows)\n",
     "",
     f"{WIRE_T}::TestMigrationReconstruction::test_the_dry_run_serialises_every_partition",
     "pred_log.rows_to_arrow_table(parquet_rows)"),

    # ── the guard's own source-stripper ────────────────────────────────────────────
    # Every "this statement is GONE" clause rests on docstrings being stripped. If the
    # stripper degenerated, those clauses would all pass on their own explanatory prose —
    # which is exactly what happened on the first cut of this suite.
    ("the source-stripper stops removing docstrings (every absence clause goes vacuous)",
     WIRE_T,
     "        if not isinstance(body, list):   # Lambda / IfExp carry a single node, not a list\n"
     "            continue\n",
     "        continue\n",
     f"{WIRE_T}::test_code_only_strips_prose_but_keeps_sql",
     None),
]

_BAK = ".e11_24_pred_log_red_proof.bak"


def _invalidate_bytecode(path: Path) -> None:
    """CPython validates bytecode on (source mtime, source SIZE), so a SAME-LENGTH mutation
    restored within the same wall-clock second leaves a poisoned .pyc that still validates."""
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(path.stem + ".*.pyc"):
            pyc.unlink(missing_ok=True)
    try:
        os.utime(path, None)
    except OSError:
        pass


def _restore_stale_backups() -> None:
    for rel in {b[1] for b in BREAKS}:
        bak = REPO / (rel + _BAK)
        if bak.exists():
            (REPO / rel).write_text(bak.read_text())
            bak.unlink()
            print(f"RESTORED     {rel} from a stale backup (a previous run died mid-mutation)")


def main() -> int:
    _restore_stale_backups()
    failures = []
    for label, rel, old, new, test, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        occurrences = original.count(old)
        if occurrences != 1:
            print(f"SETUP-ERROR  {label}\n             anchor occurs {occurrences}x in {rel} "
                  f"(need exactly 1) — the proof is stale/ambiguous, NOT passing")
            failures.append(label)
            continue
        bak = REPO / (rel + _BAK)
        bak.write_text(original)
        path.write_text(original.replace(old, new, 1))
        try:
            mutated = path.read_text()
            assert mutated != original, f"mutation did not land for {label}"
            if gone is not None and gone in mutated:
                print(f"SETUP-ERROR  {label}\n             {gone!r} survived the mutation — the "
                      "break does not move the asserted predicate, NOT passing")
                failures.append(label)
                continue
            proc = subprocess.run(
                ["uv", "run", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            red = proc.returncode != 0
        finally:
            path.write_text(original)
            _invalidate_bytecode(path)
            bak.unlink(missing_ok=True)
        print(f"{'RED  ✅' if red else 'GREEN ❌'}  {label}")
        if not red:
            failures.append(label)

    print(f"\n{len(BREAKS) - len(failures)}/{len(BREAKS)} breaks caught")
    if failures:
        print("STAYED GREEN (the guard is vacuous — fix the guard, not the proof):")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("every E11.24 P1 guard is falsifiable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
