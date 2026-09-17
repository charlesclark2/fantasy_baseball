"""NF-WK-ACC1 RED proof — break the source deliberately; each break must turn its OWN guard red.

The harness body is NF-WK-RC1's (`nf_wk_rc1_red_proof.py`), copied rather than imported so the two
proofs cannot share a backup suffix or a baseline: unique anchors, landed-on-disk, token-gone,
NOT-SELECTED, `BaseException`, and every node resolved. Each break REPRODUCES the defect its guard
names (not merely edits the guarded line).

Run:  uv run python betting_ml/tests/nf_wk_acc1_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_acc1_recorder.py"
FEED = "betting_ml/tests/test_nf_inc_0916_training_feed.py"
CADENCE = "betting_ml/tests/test_nf_wk_rc1_cadence.py"
SUITES = (SUITE, FEED, CADENCE)
_ROUTER = "app/backend/routers/fantasy.py"
_REC = "app/backend/services/weekly_recap.py"
_DIV = "app/backend/services/weekly_recap_divergence.py"
_DST = "app/backend/services/realized_dst.py"
_RW = "quant_sports_intel_models/football/nfl/fantasy/realized_week.py"
_RUN = "quant_sports_intel_models/football/nfl/fantasy/run_realized_week.py"
_JOB = "pipeline/jobs/sports_nfl_weekly_serving_job.py"
_ING = "quant_sports_intel_models/football/nfl/ingest/in_season_stats.py"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    ("the recap route stops asking for the record (no production caller again)", _ROUTER,
     "scored = _recap_week(record, season, week, record_divergence=True)",
     "scored = _recap_week(record, season, week)",
     "test_the_recap_route_turns_the_recorder_on"),
    ("_recap_week never invokes the recorder", _ROUTER,
     "    if record_divergence:\n        _record_recap_divergence(",
     "    if False:\n        _record_recap_divergence(",
     "test_recap_week_invokes_the_recorder_and_survives_its_failure"),
    ("a recorder failure fails the recap", _ROUTER,
     "    except Exception as exc:  # noqa: BLE001 — record-only; see the docstring\n        logger.warning(\"[recap-divergence]",
     "    except ZeroDivisionError as exc:\n        logger.warning(\"[recap-divergence]",
     "test_recap_week_invokes_the_recorder_and_survives_its_failure"),
    ("a freshly fetched week from another season is scored anyway (the 2026-09-17 defect)", _ROUTER,
     "        # Before the store: a refused week is not a capture this route should keep writing.\n"
     "        _refuse_a_different_season(fetched, season)\n",
     "        # Before the store: a refused week is not a capture this route should keep writing.\n",
     "test_an_earlier_seasons_league_is_refused_not_scored_against_this_seasons_stats"),
    ("a stored week from another season is scored anyway", _ROUTER,
     "    else:\n        _refuse_a_different_season(fetched, season)\n",
     "    else:\n        pass\n",
     "test_a_stored_week_from_another_season_is_refused_too"),
    ("a week with no season is treated as matching", _ROUTER,
     "    if got == str(int(season)):\n        return\n",
     "    if got in (str(int(season)), \"\"):\n        return\n",
     "test_a_week_whose_season_cannot_be_placed_is_refused"),
    ("score_week stops filling the seat explanations", _REC,
     "                if realized_by_seat is not None:",
     "                if False:",
     "test_score_week_fills_the_seat_explanations_and_never_serves_them"),
    ("the explanation columns are dropped from the join (the RC1 silent no-op)", _REC,
     '"explain": {c: row.get(c) for c in EXPLANATION_COLUMNS},',
     '"explain": {},',
     "test_the_explained_split_is_actually_fed_on_the_wired_path"),
    ("missing D/ST inputs are recorded as a supplied construction", _DIV,
     "        dst_points, pending = None, None",
     "        dst_points, pending = {}, set()",
     "test_missing_dst_inputs_are_recorded_as_not_supplied_never_as_agreement"),
    ("D/ST lines are scored without the league's settings", _DST,
     "        scoring or {}, stat_field=field_map,",
     "        {}, stat_field=field_map,",
     "test_published_dst_inputs_are_scored_under_the_leagues_own_settings"),
    ("the record is rewritten on every view", _DIV,
     '    if prior is not None and prior.get("contentSha256") == rec["contentSha256"]:',
     "    if False:",
     "test_the_record_is_written_once_and_rewritten_only_when_it_changes"),
    ("a read error is treated as 'nothing recorded yet'", _DIV,
     '        if code not in ("NoSuchKey", "404"):\n            raise',
     "        if False:\n            raise",
     "test_a_read_error_that_is_not_a_miss_raises"),
    ("the recorder pages", _DIV,
     "logger = logging.getLogger(__name__)",
     "logger = send_alert = logging.getLogger(__name__)",
     "test_the_recorder_never_pages"),
    ("an MNF-pending defence is not tagged", _RW,
     '"resultPending": D.result_pending(score),',
     '"resultPending": False,',
     "test_a_missing_opponent_score_is_tagged_pending_not_dropped"),
    ("a defence with no stats row is zero-filled", _RW,
     "            if me not in team_stats or opp not in team_stats:\n                continue\n"
     "            m, o = team_stats[me], team_stats[opp]",
     "            m, o = team_stats.get(me, {}), team_stats.get(opp, {})",
     "test_a_defence_with_no_stats_row_is_omitted_not_zero_filled"),
    ("the lake's team code is used unnormalised (LA never meets LAR)", _RW,
     "            key = _team_key(me)",
     "            key = str(me)",
     "test_the_lakes_LA_meets_the_platforms_LAR"),
    ("the D/ST inputs are rewritten even when unchanged", _RW,
     '    if prior is not None and prior.get("content_sha256") == want:',
     "    if False:",
     "test_dst_inputs_publish_is_content_addressed_and_dry_runs_write_nothing"),
    ("a dry run writes the D/ST inputs", _RW,
     "        if not dry:\n            body = {**built",
     "        if True:\n            body = {**built",
     "test_dst_inputs_publish_is_content_addressed_and_dry_runs_write_nothing"),
    ("a D/ST input failure escapes into the run", _RUN,
     "        except Exception as exc:  # noqa: BLE001 — record-only; see the docstring",
     "        except ZeroDivisionError as exc:",
     "test_a_dst_inputs_failure_is_kept_out_of_the_critical_error_list"),
    ("a D/ST input failure pages CRITICAL", _JOB,
     'severity="WARN", dedup_key="nfl_realized_publish:dst_inputs")',
     'severity="CRITICAL", dedup_key="nfl_realized_publish:dst_inputs")',
     "test_the_op_pages_dst_input_failures_at_warn_and_does_not_fail_the_run"),
    ("stats_team_week loses its recurring writer (⑧)", _ING,
     'WEEKLY_STAT_SOURCES: list[str] = ["stats_player_week", "snap_counts", "stats_team_week"]',
     'WEEKLY_STAT_SOURCES: list[str] = ["stats_player_week", "snap_counts"]',
     f"{FEED}::test_the_two_training_feeds_are_registered_free_nflverse_sources"),
    ("realized_dst drops out of the pinned box closure", "betting_ml/tests/test_nf_wk_rc1_cadence.py",
     '    "app/backend/services/realized_dst.py",\n',
     "",
     f"{CADENCE}::test_the_box_reached_app_backend_surface_has_not_widened"),
]


def _run(selector: str) -> bool:
    """True when pytest passes. `-p no:cacheprovider` so a break cannot poison a later run."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", selector],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    # ⭐ RESTORE ANY STALE BACKUP FIRST. This harness's own worst case is being killed mid-mutation,
    # which would leave broken source on disk looking like a real defect.
    for bak in ROOT.glob("**/*.acc1bak"):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        print(f"  restored stale backup for {target.relative_to(ROOT)}")

    for _suite in SUITES:
        if not _run(_suite):
            print(f"BASELINE FAILED ({_suite}) — a suite must be green before any break means anything")
            return 1
        print(f"baseline: {_suite} green")
    print()

    failures = []
    for label, rel, old, new, must_fail in BREAKS:
        # ⭐ A bare test name means the default suite; a `path::test` nodeid names its own. The
        # SUITE-level re-run below must use the SAME file, or a break in one suite would be
        # judged against the other's green run — a harness that cannot fail for the right reason.
        nodeid = must_fail if "::" in must_fail else f"{SUITE}::{must_fail}"
        suite = nodeid.split("::", 1)[0]
        path = ROOT / rel
        src = path.read_text()

        # (a) the anchor must be UNIQUE — otherwise the break lands on the wrong symbol
        if src.count(old) != 1:
            failures.append(f"{label}: anchor appears {src.count(old)}x in {rel} (must be exactly 1)")
            continue
        # (b) the guard must be SELECTED by the suite
        broken = src.replace(old, new, 1)
        bak = path.with_suffix(path.suffix + ".acc1bak")
        bak.write_text(src)
        path.write_text(broken)
        try:
            # (c) the mutation LANDED, and (d) the old token is GONE
            on_disk = path.read_text()
            if on_disk == src:
                failures.append(f"{label}: mutation did not land on disk")
                continue
            if old in on_disk:
                failures.append(f"{label}: the old token survives — the break may not bite")
                continue
            named_red = not _run(nodeid)
            suite_red = not _run(suite)
            if not named_red:
                failures.append(f"{label}: {nodeid} stayed GREEN on broken source (VACUOUS)")
            elif not suite_red:
                failures.append(f"{label}: the named test went red but the suite did not — "
                                "it is not selected by a plain run")
            else:
                print(f"  ✅ RED  {label}  →  {nodeid}")
        except BaseException as exc:   # noqa: BLE001 — pytest's Failed is a BaseException (NF-W6c)
            failures.append(f"{label}: harness error {type(exc).__name__}: {exc}")
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    # (e) EVERY NODE RESOLVED — a break that neither proved its guard nor recorded a failure would
    # vanish silently, which is the one outcome this harness must not permit.
    proved = len(BREAKS) - len(failures)
    assert proved + len(failures) == len(BREAKS), "a break resolved to neither RED nor a failure"
    print()
    if failures:
        print(f"❌ {len(failures)} of {len(BREAKS)} breaks did not prove their guard:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ all {len(BREAKS)} breaks turned their named guard RED; source restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
