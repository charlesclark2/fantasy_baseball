"""NF-WK-RC1 RED proof — break the source deliberately; each break must turn its OWN guard red.

⛔ A guard trusted because it passed once is not a guard. This harness encodes every way this repo
has watched a RED proof lie:

  • #682 — the mutation must be proven to LAND ON DISK, or "the break no-opped" and "the guard
    caught it" are indistinguishable, and the FALSE-VACUITY reading is the dangerous one.
  • #815 — the token must be proven GONE afterwards; a mutation that writes without moving the
    asserted predicate comes back green.
  • the 3rd way — the anchor must be UNIQUE in the file, or `replace(old, new, 1)` lands on the
    WRONG symbol and reports a false vacuity against a guard that is fine.
  • NF-W6c — `pytest.raises` failures are `BaseException`, so a bare `except Exception` lets a
    deliberate break sail straight through.
  • NOT-SELECTED — a break must turn red the guard it NAMES, not merely "something".

Run:  uv run python betting_ml/tests/nf_wk_rc1_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_rc1_weekly_recap.py"
#: NF-WK-RC1 ① — the cadence clauses live in their own file. A break names a test in EITHER
#: suite: the last field is a bare test name (⇒ `SUITE`) or a full `path::test` nodeid.
CADENCE = "betting_ml/tests/test_nf_wk_rc1_cadence.py"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    ("dst seat serves our scorer instead of the league's figure",
     "app/backend/services/weekly_recap.py",
     '''                pts = seat.get("platformPts")''',
     '''                pts = (hit or {}).get("leaguePts")''',
     "test_the_dst_seat_carries_the_leagues_own_figure_not_ours"),

    ("matchup decided on OUR itemisation",
     "app/backend/services/weekly_recap.py",
     '''        a_t = side[0]["standingsTotal"] if side else None
        b_t = side[1]["standingsTotal"] if len(side) == 2 else None''',
     '''        a_t = side[0]["itemisedTotal"] if side else None
        b_t = side[1]["itemisedTotal"] if len(side) == 2 else None''',
     "test_the_matchup_result_is_decided_on_the_leagues_total_never_our_sum"),

    ("the gap note goes generic",
     "app/backend/services/weekly_recap.py",
     '''    return (f"This league also scores {subject}, which the breakdown below doesn't itemize yet — "
            "so the slot points don't add up to the total above.")''',
     '''    return "Totals may differ."''',
     "test_the_gap_note_names_the_leagues_own_captured_terms_and_is_not_generic"),

    # ⚠️ THE BREAK MUST REMOVE THE CONSTRUCTION OVERRIDE, not the None-guard. A first cut broke
    # `if dst_constructed is None: continue` -> `if False: continue`, which changes NOTHING when a
    # construction IS supplied — so it reported the guard vacuous when the guard was fine and the
    # BREAK was inert. That is the "it landed but did not move the asserted predicate" shape (#815)
    # arriving in the harness rather than the suite.
    ("the dst comparison reverts to the SERVED value (the vacuity this guard exists for)",
     "app/backend/services/weekly_recap.py",
     '''                rec["ours"] = float(dst_constructed[key])
                rec["delta"] = rec["ours"] - float(theirs)''',
     '''                pass''',
     "test_the_dst_comparison_is_not_vacuous_against_the_served_value"),

    ("a seat is allowed to alert",
     "app/backend/services/weekly_recap.py",
     '''            "mayAlert": False,
            "explainedBy": sorted(EXPLAINABLE_CAPTURED_TERMS),''',
     '''            "mayAlert": True,
            "explainedBy": sorted(EXPLAINABLE_CAPTURED_TERMS),''',
     "test_no_seat_may_alert"),

    ("completeness becomes 'any game played' (a clock-rule stand-in)",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '''    return "final" if realized_games >= scheduled_games else "partial"''',
     '''    return "final"''',
     "test_a_postponed_game_keeps_a_week_partial"),

    ("points allowed reverts to the opponent's score",
     "app/backend/services/realized_dst.py",
     '''    return max(0.0, float(opponent_score) - NON_OFFENSIVE_TD_POINTS * tds)''',
     '''    return max(0.0, float(opponent_score))''',
     "test_points_allowed_excludes_the_opponents_non_offensive_touchdowns"),

    ("the disclosure stops requiring a MEASURED gap (the live-gate defect)",
     "app/backend/services/weekly_recap.py",
     '''    if max_gap is not None and abs(max_gap) <= GAP_EPSILON:
        return None''',
     '''    if False:
        return None''',
     "test_no_disclosure_when_the_itemisation_actually_matches"),

    ("float noise is no longer snapped out of the served gap",
     "app/backend/services/weekly_recap.py",
     '''    return 0.0 if abs(value) <= GAP_EPSILON else value''',
     '''    return value''',
     "test_float_noise_is_snapped_out_of_the_served_gap"),

    ("the artifact stops carrying the explanation columns",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '''        | set(W.EXPLANATION_COLUMNS)''',
     '''        | set()''',
     "test_the_explanation_columns_are_actually_carried_by_the_published_artifact"),

    # ══ NF-WK-RC1 ① — the recurring writer, and its refusals ═══════════════════════════════════
    ("the realized publish is unwired from the job, so nothing publishes a week ever again",
     "pipeline/jobs/sports_nfl_weekly_serving_job.py",
     "    nfl_realized_week_publish_op(start=landed)",
     "    pass  # unwired",
     f"{CADENCE}::test_the_realized_publish_runs_downstream_of_the_stats_ingest_it_reads"),

    # ⚠️ THE FIRST CUT OF THIS BREAK WAS ITSELF VACUOUS, and it is kept in the record because the
    # failure mode is the interesting part: it wrote
    # `nfl_realized_week_publish_op(start=nfl_weekly_serving_op(start=landed))`, which invokes the
    # build op a SECOND time — Dagster then ALIASES it to `nfl_weekly_serving_op_2`, so the
    # reachability clause looked for a node name that no longer existed and passed on broken source.
    # A break must reproduce the DEFECT, not merely edit the line the defect would live on.
    ("the realized publish is chained BEHIND the projection build, so a refused build withholds it",
     "pipeline/jobs/sports_nfl_weekly_serving_job.py",
     "    landed = nfl_weekly_stats_ingest_op()\n    nfl_weekly_serving_op(start=nfl_weekly_stats_freshness_op(start=landed))\n    # NF-WK-RC1 ① — an INDEPENDENT branch off the same ingest: it must not be withheld by a\n    # refused projection build, and must not withhold one. See the op's own docstring.\n    nfl_realized_week_publish_op(start=landed)",
     "    landed = nfl_weekly_stats_ingest_op()\n    built = nfl_weekly_serving_op(start=nfl_weekly_stats_freshness_op(start=landed))\n    # NF-WK-RC1 ① — an INDEPENDENT branch off the same ingest: it must not be withheld by a\n    # refused projection build, and must not withhold one. See the op's own docstring.\n    nfl_realized_week_publish_op(start=built)",
     f"{CADENCE}::test_the_realized_publish_is_not_downstream_of_the_projection_build"),

    ("the publish subprocess loses its finite timeout (INC-32)",
     "pipeline/jobs/sports_nfl_weekly_serving_job.py",
     "        proc = run_bounded(cmd, cwd=str(_APP_DIR), env=env,\n"
     "                           timeout=NFL_REALIZED_PUBLISH_TIMEOUT_SECONDS)",
     "        proc = subprocess.run(cmd, cwd=str(_APP_DIR), env=env,\n"
     "                              capture_output=True, text=True)",
     f"{CADENCE}::test_the_realized_publish_subprocess_is_bounded"),

    ("the backstop moves INSIDE the job it judges, so it can never see that job stop",
     "pipeline/jobs/sports_nfl_sleeper_injuries_job.py",
     "    nfl_realized_freshness_op()",
     "    pass  # moved",
     f"{CADENCE}::test_the_realized_freshness_backstop_runs_on_a_different_job_than_its_subject"),

    ("the cadence starts publishing PARTIAL weeks (the pre-MNF fire the PM gate refuses)",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '    final_weeks = sorted(w for w, s in states.items() if s == "final")',
     '    final_weeks = sorted(w for w, s in states.items() if s != "not_started")',
     f"{CADENCE}::test_a_partial_week_is_never_planned_by_the_cadence"),

    ("a restatement silently OVERWRITES the week a reader is already looking at",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '    return {"action": "restate",',
     '    return {"action": "create",',
     f"{CADENCE}::test_a_restatement_keeps_the_published_week_serving"),

    ("a FINAL week can be clobbered by a later PARTIAL build",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '    if was == "final" and state != "final":',
     "    if False:",
     f"{CADENCE}::test_a_final_week_is_never_replaced_by_a_partial_one"),

    ("an uncomparable published week is reported as 'unchanged' (the NF1.7(a) vacuous pass)",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '    prior = published.get("content_sha256")\n    if not prior:',
     '    prior = published.get("content_sha256")\n    if False:',
     f"{CADENCE}::test_an_uncomparable_published_week_is_not_reported_as_unchanged"),

    ("the content hash stops being order-invariant, so every rebuild reads as a restatement",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     "        json.dumps(canonical_rows(players), sort_keys=True, default=str).encode()",
     "        json.dumps(players, sort_keys=True, default=str).encode()",
     f"{CADENCE}::test_the_content_hash_ignores_row_order_but_not_row_content"),

    ("the backstop pages out of season, on an artifact that is correctly static (INC-45)",
     "betting_ml/monitoring/nfl_realized_freshness.py",
     '        return {"verdict": "INACTIVE", "severity": None, "missing": [],',
     '        return {"verdict": "INACTIVE", "severity": "WARN", "missing": [],',
     f"{CADENCE}::test_no_final_week_is_inactive_and_never_pages"),

    ("an unevaluable backstop reading is scored HEALTHY instead of WARN (NF1.7(a))",
     "betting_ml/monitoring/nfl_realized_freshness.py",
     '        return {"verdict": "UNEVALUABLE", "severity": "WARN", "missing": [],',
     '        return {"verdict": "UNEVALUABLE", "severity": None, "missing": [],',
     f"{CADENCE}::test_an_unevaluable_reading_is_warn_and_never_healthy"),

    ("the grace window is tightened below the vendor's own measured publication lag",
     "betting_ml/monitoring/nfl_realized_freshness.py",
     "GRACE_HOURS = VENDOR_LAG_HOURS + CADENCE_HOURS + SLACK_HOURS",
     "GRACE_HOURS = 6",
     f"{CADENCE}::test_the_grace_window_exceeds_the_measured_vendor_lag"),

    ("a parked revision counts as a published week, hiding a real gap behind it",
     "quant_sports_intel_models/football/nfl/fantasy/run_realized_week.py",
     '            if parts[-1] == "manifest.json" and len(parts) >= 2 and parts[-2].isdigit():',
     '            if parts[-1].startswith("manifest") and len(parts) >= 2 and parts[-2].isdigit():',
     f"{CADENCE}::test_a_parked_revision_does_not_read_as_a_published_week"),

    ("the MNF-pending D/ST rows are DROPPED rather than tagged, so 'could not compute' reads as "
     "'agreed' (PM item 4 / card yOhLHprC)",
     "app/backend/services/weekly_recap.py",
     '                if abs(rec["delta"]) > tolerance:\n'
     "                    dst_div.append(rec)\n"
     '                    if rec["scheduleResultPending"]:\n'
     "                        dst_pending.append(rec)",
     '                if abs(rec["delta"]) > tolerance and not rec["scheduleResultPending"]:\n'
     "                    dst_div.append(rec)",
     f"{CADENCE}::test_a_defence_whose_game_result_has_not_published_is_tagged_not_dropped"),
]



def _run(selector: str) -> bool:
    """True when pytest passes. `-p no:cacheprovider` so a break cannot poison a later run."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", selector],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    # ⭐ RESTORE ANY STALE BACKUP FIRST. This harness's own worst case is being killed mid-mutation,
    # which would leave broken source on disk looking like a real defect.
    for bak in ROOT.glob("**/*.rc1bak"):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        print(f"  restored stale backup for {target.relative_to(ROOT)}")

    for _suite in (SUITE, CADENCE):
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
        bak = path.with_suffix(path.suffix + ".rc1bak")
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
