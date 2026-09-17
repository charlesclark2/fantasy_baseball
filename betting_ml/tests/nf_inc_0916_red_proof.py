"""nf_inc_0916_red_proof.py — prove NF-INC-0916's promotion gate can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE GATE THIS PROVES IS THE ONE THE OPERATOR IS BEING ASKED TO TRUST INSTEAD OF REMEMBERING.
The weekly page is withholding numbers it has measured wrong while a changelog entry announcing an
improvement to those same numbers waits in `changelog-held.json`. Promoting `dev` → `main` is one
click and publishes both. So "the gate is armed" is not a claim that may rest on the guard being
green — a guard can be green because it is correct or because it is vacuous, and those look
identical from a run page.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here — machinery borrowed verbatim from
`nf_wk_td1_red_proof` rather than re-invented:
  1. **the mutation never LANDS** (#682) — every mutation asserts the file CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — a replacing mutation asserts the
     OLD token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied;
  4. **the node id COLLECTS NOTHING** — pytest exits non-zero on an unresolvable node id, so a
     renamed guard reports a perfect RED for a test that no longer exists. Every node id is
     resolved during the BASELINE phase, before any source is touched.
⭐ Plus a BASELINE-PASS leg and a NOT-SELECTED leg (a mutation must not turn some OTHER test red and
be credited to this one).

⚠️ THE MUTATED FILES HERE ARE `.ts`, `.json` AND `.yml`, NOT `.py`. The borrowed sweep asserted a
`.py` target before restoring a backup; that assertion is a safety rail on the RESTORE path, so it
is widened to the extensions this harness actually touches rather than removed.

⛔ Restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's own
worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson).

⚠️ NOT SAFE TO RUN CONCURRENTLY WITH ITSELF. One at a time.

RUN (LAPTOP, ~40 s):
    uv run python betting_ml/tests/nf_inc_0916_red_proof.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TESTS = _REPO / "betting_ml/tests"

_CHANGELOG = _REPO / "frontend/data/changelog.json"
_HELD = _REPO / "frontend/data/changelog-held.json"
_FLAG_TS = _REPO / "frontend/lib/weekly-suppression.ts"
_PAGE_TSX = _REPO / "frontend/components/fantasy/weekly-page.tsx"
_CI_YML = _REPO / ".github/workflows/ci.yml"
_INGEST = _REPO / "quant_sports_intel_models/football/nfl/ingest/in_season_stats.py"
_JOB = _REPO / "pipeline/jobs/sports_nfl_weekly_serving_job.py"
_SFRESH = _REPO / "betting_ml/monitoring/nfl_weekly_stats_freshness.py"
_WS = _REPO / "quant_sports_intel_models/football/nfl/fantasy/weekly_serving.py"
_RUNNER = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_weekly_serving.py"

_GUARD = _TESTS / "test_nf_inc_0916_promotion_gate.py"
_FEED = _TESTS / "test_nf_inc_0916_training_feed.py"
_REFUSE = _TESTS / "test_nf_inc_0916_training_refusal.py"
_PH2 = _TESTS / "test_nf_c6_ph2_weekly_serving.py"
_GUARD_FILES = (_GUARD, _FEED, _REFUSE, _PH2)

#: An unrelated clause that must stay GREEN through every mutation — otherwise a RED is not
#: attributable to the guard it is credited to. Deliberately one that ALSO reads `ci.yml`, so a
#: mutation that broke the workflow wholesale (rather than the one property under test) shows up
#: here instead of being credited to this story.
NOT_SELECTED = (
    f"{_TESTS / 'test_ncaaf_p3_9_nav.py'}"
    "::test_the_changelog_filter_selects_the_changelog_and_nothing_else"
)

_BAK_SUFFIX = ".redproof.bak"
_RESTORABLE = {".ts", ".tsx", ".json", ".yml", ".py"}

def _held_item_json() -> str:
    """The deferred item, serialised exactly as `changelog.json` carries an item.

    ⭐ READ FROM THE REGISTRY rather than typed here. The mutation has to be the REAL restoration or
    it proves nothing about the real gate — and a copy typed into this file would drift from the
    registry on the first reword, at which point the mutation would stop expressing the defect
    while the harness went on reporting a perfect RED.
    """
    entry = json.loads(_HELD.read_text())["held"][0]
    body = json.dumps(entry["item"], indent=2, ensure_ascii=False)
    return "\n".join("      " + ln for ln in body.splitlines())


#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── the gate itself: a held announcement must not ship while its subject is withheld ────────
    ("the deferred announcement is put back into the changelog while the numbers are withheld",
     _CHANGELOG,
     '    "week": "2026-09-14",\n    "items": [\n',
     '    "week": "2026-09-14",\n    "items": [\n' + _held_item_json() + ",\n",
     f"{_GUARD}::test_a_held_announcement_does_not_ship_while_its_subject_is_withheld"),

    ("…and it is caught even when it was lightly reworded on the way back in",
     _CHANGELOG,
     '    "week": "2026-09-14",\n    "items": [\n',
     '    "week": "2026-09-14",\n    "items": [\n'
     + _held_item_json().replace(' of the game."', ' of the game, roughly speaking."')
     + ",\n",
     f"{_GUARD}::test_a_held_announcement_does_not_ship_while_its_subject_is_withheld"),

    ("the held registry is emptied instead of the item being restored — the announcement vanishes",
     _HELD,
     '  "held": [',
     '  "held_disabled": [',
     f"{_GUARD}::test_every_file_this_gate_reads_exists_and_parses"),

    # ── the flag is readable, and is the only lever ──────────────────────────────────────────────
    ("the withholding flag becomes a computed value, so nothing can read its state",
     _FLAG_TS,
     "export const WEEKLY_NUMBERS_WITHHELD = true",
     'export const WEEKLY_NUMBERS_WITHHELD = process.env.NEXT_PUBLIC_WEEKLY_WITHHELD !== "0"',
     f"{_GUARD}::test_every_file_this_gate_reads_exists_and_parses"),

    ("the flag moves to an environment variable, which a Vercel redeploy silently ignores",
     _FLAG_TS,
     "export const WEEKLY_WITHHELD_SINCE = ",
     'const _ENV_OVERRIDE = process.env.NEXT_PUBLIC_WEEKLY_WITHHELD\nexport const WEEKLY_WITHHELD_SINCE = ',
     f"{_GUARD}::test_the_flag_is_not_an_environment_variable"),

    ("the page stops rendering through the shared row plan and decides for itself again",
     _PAGE_TSX,
     "view={weeklyRowView(p, WEEKLY_NUMBERS_WITHHELD)}",
     "view={{ point: { kind: 'withheld' } } as WeeklyRowView}",
     f"{_GUARD}::test_the_weekly_page_reads_the_flag_and_never_decides_for_itself"),

    # ── the CI wiring: the gate must RUN on the PR class that lifts it ───────────────────────────
    ("the release-gate filter is deleted, so the reversal PR runs no Python job at all",
     _CI_YML,
     "            release_gate:\n              - 'frontend/{data/changelog.json,data/changelog-held.json,lib/weekly-suppression.ts}'\n",
     "",
     f"{_GUARD}::test_a_release_gate_filter_selects_every_file_this_invariant_spans"),

    ("the filter is split into three patterns, which under `every` selects nothing at all",
     _CI_YML,
     "              - 'frontend/{data/changelog.json,data/changelog-held.json,lib/weekly-suppression.ts}'",
     "              - 'frontend/data/changelog.json'\n"
     "              - 'frontend/data/changelog-held.json'\n"
     "              - 'frontend/lib/weekly-suppression.ts'",
     f"{_GUARD}::test_a_release_gate_filter_selects_every_file_this_invariant_spans"),

    ("the release-gate job is widened to `backend ||`, destroying the evidence its trigger works",
     _CI_YML,
     "    if: needs.changes.outputs.release_gate == 'true'",
     "    if: needs.changes.outputs.backend == 'true' || needs.changes.outputs.release_gate == 'true'",
     f"{_GUARD}::test_the_release_gate_job_runs_this_file_and_is_gated_on_its_own_filter"),

    ("the release-gate job stops running the gate, so it is wired to a filter and tests nothing",
     _CI_YML,
     "        run: uv run pytest betting_ml/tests/test_nf_inc_0916_promotion_gate.py -v --tb=short",
     "        run: echo 'release gate ok'",
     f"{_GUARD}::test_the_release_gate_job_runs_this_file_and_is_gated_on_its_own_filter"),

    ("the frontend is added to the `backend` filter — the edit that DISARMS the whole Python gate",
     _CI_YML,
     "            backend:\n              - '**'\n",
     "            backend:\n              - '**'\n              - 'frontend/lib/weekly-suppression.ts'\n",
     f"{_GUARD}::test_the_backend_filter_was_not_widened_to_reach_the_frontend"),

    # ══ NODE 1 — the training feeds have an owner, an order and an SLA ════════════════════════
    ("the training-feed set is silently emptied, so the ingest pulls nothing and reports success",
     _INGEST,
     'WEEKLY_STAT_SOURCES: list[str] = ["stats_player_week", "snap_counts", "stats_team_week"]',
     "WEEKLY_STAT_SOURCES: list[str] = []",
     f"{_FEED}::test_the_two_training_feeds_are_registered_free_nflverse_sources"),

    ("the freshness leg is unwired, so nothing judges whether the feed actually advanced",
     _JOB,
     # ⚠️ RE-ANCHORED 2026-09-16 (NF-WK-RC1 ①) — the graph body gained a second branch off the same
     # ingest, so the single-line form this break used to target no longer exists. Re-anchored onto
     # the new implementation rather than weakened: the break still UNWIRES the freshness leg and
     # must still turn the same clause red. (MH2.7: a shared change re-anchors the guards that pin
     # its output; it does not delete them.)
     "    nfl_weekly_serving_op(start=nfl_weekly_stats_freshness_op(start=landed))",
     "    nfl_weekly_serving_op(start=landed)",
     f"{_FEED}::test_the_freshness_leg_is_downstream_of_the_ingest_it_judges"),

    ("the ingest subprocess loses its finite timeout (INC-32)",
     _JOB,
     "        proc = run_bounded(cmd, cwd=str(_APP_DIR), env=env,\n"
     "                           timeout=NFL_WEEKLY_STATS_INGEST_TIMEOUT_SECONDS)",
     "        proc = subprocess.run(cmd, cwd=str(_APP_DIR), env=env,\n"
     "                              capture_output=True, text=True)",
     f"{_FEED}::test_the_ingest_subprocess_carries_a_finite_timeout"),

    ("the grace window is tightened below the vendor's measured publication lag",
     _SFRESH,
     "SETTLE_HOURS = 24.0",
     "SETTLE_HOURS = 4.0",
     f"{_FEED}::test_the_settle_window_is_longer_than_the_measured_publication_lag"),

    ("the PENDING hole is reopened: a season with NO rows reads healthy inside the window",
     _SFRESH,
     "    explicable = gap == 1 or (reading.last_week is None and last_completed_week == 1)",
     "    explicable = True",
     f"{_FEED}::test_the_feed_is_judged_against_the_week_that_was_actually_played"),

    ("an unreadable feed is scored healthy instead of warned about (NF1.7(a))",
     _SFRESH,
     '"verdict": "UNREADABLE", "severity": "WARN", "source": reading.source,',
     '"verdict": "UNREADABLE", "severity": None, "source": reading.source,',
     f"{_FEED}::test_a_feed_that_cannot_be_read_is_warned_about_and_never_scored_healthy"),

    ("one stale feed is silenced by a healthy sibling (silent-by-aggregation)",
     _SFRESH,
     "    return max(sev, key=lambda s: order.get(s, 0)) if sev else None",
     "    return max(sev, key=lambda s: order.get(s, 0)) if len(sev) == len(verdicts) else None",
     f"{_FEED}::test_one_stale_feed_pages_even_when_its_sibling_is_healthy"),

    # ══ NODE 2 — the refusals at the instrument ═══════════════════════════════════════════════
    ("the coverage floor is raised to a level real historical weeks fall below",
     _WS,
     "TRAIN_STAT_COVERAGE_FLOOR = 0.30",
     "TRAIN_STAT_COVERAGE_FLOOR = 0.50",
     f"{_REFUSE}::test_the_floor_sits_below_every_week_in_the_measured_history"),

    ("the floor is dropped to zero, which the defect itself satisfies",
     _WS,
     "TRAIN_STAT_COVERAGE_FLOOR = 0.30",
     "TRAIN_STAT_COVERAGE_FLOOR = 0.0",
     f"{_REFUSE}::test_the_floor_sits_below_every_week_in_the_measured_history"),

    ("the gate keys on ZEROS instead of coverage — it would refuse a real low-scoring week",
     _WS,
     '             .agg(n=("_has_stat_row", "size"), coverage=("_has_stat_row", "mean"))',
     '             .agg(n=("_has_stat_row", "size"), coverage=("fantasy_points", lambda v: float((v > 0).mean())))',
     f"{_REFUSE}::test_the_retained_zero_convention_is_not_repealed"),

    ("byes are counted against coverage, so the verdict depends on how many teams were off",
     _WS,
     '    played = frame[frame["_has_game"].astype(bool)]',
     "    played = frame",
     f"{_REFUSE}::test_byes_are_excluded_from_coverage"),

    ("the TARGET week is judged, which would refuse every build there has ever been",
     _WS,
     "    hist = played[key < target.season * 100 + target.week]",
     "    hist = played[key <= target.season * 100 + target.week]",
     f"{_REFUSE}::test_the_target_week_is_not_judged"),

    ("an empty examination is scored as a pass (NF1.7(a))",
     _WS,
     '    if cov.empty:\n        raise WeeklyServingError(',
     '    if False:\n        raise WeeklyServingError(',
     f"{_REFUSE}::test_it_refuses_an_empty_examination"),

    ("the manifest's two-field proof stops refusing the pair the incident published",
     _WS,
     "    if sa < (int(tt_s), int(tt_w)):",
     "    if False:",
     f"{_REFUSE}::test_the_manifest_gate_fires_on_the_exact_state_the_incident_published"),

    ("the build defines the coverage refusal and never calls it (wired != invoked)",
     _RUNNER,
     "    stat_cov = WS.assert_training_stat_coverage(frame, target=target, vintage=vintage)",
     '    stat_cov = {"min_coverage": 1.0, "n_weeks_checked": 0, "min_week": "n/a", "floor": 0.0}',
     f"{_REFUSE}::test_the_build_invokes_both_refusals"),

    ("the build stops calling the manifest refusal",
     _RUNNER,
     "    sv = WS.assert_stat_vintage_reaches_training(vintage)",
     '    sv = {"evaluable": False}',
     f"{_REFUSE}::test_the_build_invokes_both_refusals"),

    ("a top-level `pipeline` import returns to the job module, killing the fast gate at collection",
     _JOB,
     "import json\nimport os",
     "import json\nimport os\nfrom pipeline.utils.alerting import send_alert  # noqa: F401",
     f"{_FEED}::test_the_job_module_can_be_read_without_importing_the_pipeline_package"),

    # ⚠️ RE-ANCHORING AN EXISTING GUARD CAN WEAKEN IT. Node 1's second op gave this module a second
    # `.classify(` call, so NF-C6-PH2's module-wide scan failed on code unrelated to its property
    # and had to be scoped to the op it always meant. This case proves the scoping did not cost it
    # its teeth: the defect it exists to catch must still turn it RED.
    ("the re-anchored NF-C6-PH2 kickoff guard: the escalation input is dropped again",
     _JOB,
     "    verdict = WF.classify(reading, expected_week=expected_week,\n"
     "                          served_slate_ends=served_slate_ends,\n"
     "                          expected_kickoff=expected_kickoff)",
     "    verdict = WF.classify(reading, expected_week=expected_week,\n"
     "                          served_slate_ends=served_slate_ends)",
     f"{_PH2}::test_the_freshness_op_actually_supplies_the_expected_kickoff"),
]


def _run(nodeid: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header", "-p",
                        "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    return r.returncode == 0


def _collects(nodeid: str) -> bool:
    """Does this node id resolve to at least one test? ⚠️ Asked ONLY on UNBROKEN source."""
    probe = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header",
                            "--collect-only", "-p", "no:cacheprovider"],
                           cwd=_REPO, capture_output=True, text=True)
    return probe.returncode == 0 and "no tests ran" not in (probe.stdout + probe.stderr)


def _sweep_stale_backups() -> list[str]:
    """⛔ FIRST, before any mutation: a stale backup means real source is still broken.

    ⚠️ The WHOLE known suffix is stripped, never `with_suffix("")` — `Path` treats only the last
    dotted segment as a suffix, so that idiom writes the original to a junk filename, leaves the
    real file mutated and reports success.
    """
    restored = []
    for root in (_REPO / "quant_sports_intel_models/football/nfl/fantasy",
                 _REPO / "frontend/data", _REPO / "frontend/lib",
                 _REPO / "frontend/components", _REPO / ".github/workflows",
                 _REPO / "quant_sports_intel_models/football/nfl/ingest",
                 _REPO / "pipeline/jobs", _REPO / "betting_ml/monitoring"):
        for bak in root.rglob(f"*{_BAK_SUFFIX}"):
            target = Path(str(bak)[: -len(_BAK_SUFFIX)])
            assert target.suffix in _RESTORABLE, (
                f"refusing to restore {bak} onto {target} — that is not a file this harness mutates")
            target.write_text(bak.read_text())
            bak.unlink()
            restored.append(str(target.relative_to(_REPO)))
    return restored


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: every guard must be GREEN on unbroken source "
          "(a 'red' means nothing otherwise)")
    if not all(_run(str(f)) for f in _GUARD_FILES) or not _run(NOT_SELECTED):
        print("⛔ BASELINE FAILED — fix the suite before reading any RED below")
        return 1
    missing = sorted({c[4] for c in CASES if not _collects(c[4])})
    if missing:
        print(f"⛔ BASELINE FAILED — these node ids collect NOTHING (renamed/moved/deleted), so "
              f"every RED credited to them would be meaningless: {missing}")
        return 1
    print(f"   ✅ baseline green, all {len({c[4] for c in CASES})} named guards resolve\n")

    red = 0
    for label, path, old, new, nodeid in CASES:
        src = path.read_text()
        n = src.count(old)
        if n != 1:
            print(f"⛔ {label}: anchor occurs {n}× in {path.name} — NOT UNIQUE, refusing to mutate")
            continue
        bak = path.with_suffix(path.suffix + _BAK_SUFFIX)
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            after = path.read_text()
            additive = bool(new) and old in new
            assert after != src, f"{label}: mutation did not land"
            if additive:
                assert new not in src, f"{label}: the additive break was ALREADY present"
                assert new in after, f"{label}: the additive break is not in the file"
            else:
                assert old not in after, (
                    f"{label}: the old token survives — the predicate did not move")

            failed = not _run(nodeid)
            other_ok = _run(NOT_SELECTED)
            mark = "✅ RED" if failed else "⛔ STILL GREEN (VACUOUS GUARD)"
            sel = "" if other_ok else "  ⚠️ NOT-SELECTED control also broke — not attributable"
            print(f"{mark:34s} {label}{sel}")
            red += bool(failed and other_ok)
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    print(f"\n{red}/{len(CASES)} mutations turned their named guard RED (attributably).")
    print("── restoring: verifying the tree is green again")
    ok = all(_run(str(f)) for f in _GUARD_FILES)
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
