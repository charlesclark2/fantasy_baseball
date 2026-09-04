#!/usr/bin/env python3
"""NCAAF-P3.3 RED PROOF — break the source one defect at a time, require the NAMED clause to fail.

    uv run python betting_ml/tests/ncaaf_p3_3_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_ncaaf_p3_3_team_page.py` is refactored.

WHY IT EXISTS. That suite's clauses are mostly of the form "these two empty states stay
DISTINGUISHABLE" — which is exactly the shape that reads as coverage while proving nothing, because
a suite can assert an absence and still pass when every absence collapses into one. This repo has
shipped that repeatedly: a guard a COMMENT could satisfy (INC-38), an `and`-composed clause whose
fixture was already refused by a different clause (NF-D17), a `"name" in src` clause satisfied by
the import line (NF-C0e). None was found by reading the test.

THE THREE CONTROLS, all of which this repo paid for:

  1. **BASELINE-PASS** — every named clause is proven GREEN on unbroken source first. A clause that
     is already failing would be reported RED by every break.
  2. **NOT-SELECTED** — a mistyped or stale test id makes pytest select nothing and exit NON-ZERO,
     which a naive `returncode != 0` reads as "the clause went red": the harness reporting its
     strongest result for a clause it never ran. A false RED is the dangerous direction — it is
     indistinguishable from a working guard.
  3. **UNIQUE ANCHOR** — a `replace(old, new, 1)` against a non-unique anchor lands wherever the
     first match happens to be, leaving the clause untouched and the harness reporting a FALSE
     "GREEN — VACUOUS" (NF-INJ2b). An anchor seen more than once is AMBIGUOUS-ANCHOR, never applied.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`,
which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

BUILDER = REPO / "quant_sports_intel_models/football/ncaaf/serving/team_payloads.py"
CONTRACT = REPO / "app/backend/models/ncaaf.py"
WRITER = REPO / "scripts/write_ncaaf_serving_store.py"
ROUTER = REPO / "app/backend/routers/ncaaf.py"

SUITE = "betting_ml/tests/test_ncaaf_p3_3_team_page.py"

#: (label, file, find, replace, test id)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── standings: a rank is publishable only WITH its range ─────────────────────────────────
    ("a rank is published without the range that makes it honest",
     BUILDER,
     '        "rank_lo": rank_lo,\n        "rank_hi": rank_hi,',
     '        "rank_lo": None,\n        "rank_hi": None,',
     "test_a_rank_is_never_attached_without_its_range"),

    ("the rank range is drawn UNSEEDED, so every daily write jiggles it",
     BUILDER,
     "np.random.default_rng(STANDING_SEED)",
     "np.random.default_rng()",
     "test_the_standings_are_deterministic_across_writes"),

    ("a team with no usable posterior is counted in the denominator anyway",
     BUILDER,
     "        if not (math.isfinite(mu) and math.isfinite(sd)) or sd <= 0:\n            continue",
     "        if False:\n            continue",
     "test_a_team_without_a_usable_posterior_is_left_unranked_and_out_of_the_denominator"),

    ("a one-team conference is published as a standing",
     BUILDER,
     "        if len(cols) < 2:\n            continue",
     "        if False:\n            continue",
     "test_a_population_too_small_to_rank_gets_no_standing"),

    ("the standings are computed but never attached to any payload",
     BUILDER,
     "    return attach_standings(payloads)",
     "    return payloads",
     "test_the_writer_attaches_standings_rather_than_leaving_them_to_a_caller"),

    # ── realignment: the AC this story is graded on ──────────────────────────────────────────
    ("the conference is read off the MODEL row instead of the SCD-2 dim",
     BUILDER,
     "        conference, source = dim_conf, CONFERENCE_SOURCE_DIM",
     "        conference, source = model_conf or dim_conf, CONFERENCE_SOURCE_DIM",
     "test_a_conference_disagreement_is_recorded_rather_than_silently_resolved"),

    ("a dim/model conference disagreement stops being recorded",
     BUILDER,
     "    matches = None if (dim_conf is None or model_conf is None) else (dim_conf == model_conf)",
     "    matches = None",
     "test_a_conference_disagreement_is_recorded_rather_than_silently_resolved"),

    ("a team we never looked up is REPORTED as an established program",
     BUILDER,
     '        "is_new_to_fbs": None if dim_row is None else (prior_season_dim_row is None),',
     '        "is_new_to_fbs": prior_season_dim_row is None,',
     "test_a_first_year_fbs_program_is_named_rather_than_looking_like_missing_data"),

    # ── the band ─────────────────────────────────────────────────────────────────────────────
    ("the strength band is dropped, leaving a bare rating",
     BUILDER,
     '        "strength_margin_sd": _f(row.get("strength_margin_sd")),',
     '        "strength_margin_sd": None,',
     "test_the_strength_block_carries_the_posterior_band_at_week_one"),

    # ⭐ THE MOST LIKELY REAL DEFECT HERE: `build_efficiency` correctly refuses a zero-game row (a
    # rollup of nothing is unknown), and copying that filter across to the POSTERIOR is exactly
    # backwards — a zero-game strength row IS the prior, and refusing it empties every page in
    # week 1. Two breaks, because the block has two halves and only one is the availability gate.
    ("a week-1 zero-game posterior is refused as if it were a gap (the gate)",
     BUILDER,
     "    latest_raw = _latest_by_week(rows)",
     "    latest_raw = _latest_by_week([r for r in rows if (_i(r.get(\"games_in_window\")) or 0) > 0])",
     "test_the_strength_block_carries_the_posterior_band_at_week_one"),

    ("a week-1 zero-game posterior is dropped from the week SERIES",
     BUILDER,
     "    weeks = [_strength_week(r) for r in rows if _i(r.get(\"as_of_week\")) is not None]",
     "    weeks = [_strength_week(r) for r in rows if (_i(r.get(\"games_in_window\")) or 0) > 0]",
     "test_the_strength_block_carries_the_posterior_band_at_week_one"),

    ("the current week is taken by ROW ORDER rather than by the largest as_of_week",
     BUILDER,
     "        if best_week is None or week > best_week:",
     "        if True:",
     "test_the_current_week_is_the_LARGEST_as_of_week_not_the_last_row"),

    # ── the three absences ───────────────────────────────────────────────────────────────────
    ("every empty P1.1 block collapses onto one reason",
     BUILDER,
     "    if not marts_available:\n        return \"unavailable\", REASON_NOT_BUILT\n    return \"unavailable\", (REASON_NO_GAMES if has_any_row else REASON_NO_ROW)",
     "    return \"unavailable\", REASON_NO_ROW",
     "test_the_three_causes_of_an_empty_block_are_distinguishable[build_efficiency]"),

    ("the two rollup absences are mapped the wrong way round",
     BUILDER,
     "    return \"unavailable\", (REASON_NO_GAMES if has_any_row else REASON_NO_ROW)",
     "    return \"unavailable\", (REASON_NO_ROW if has_any_row else REASON_NO_GAMES)",
     "test_the_three_causes_of_an_empty_block_are_distinguishable[build_efficiency]"),

    ("an unreadable strength lake reads as a team the fit did not model",
     BUILDER,
     '            "reason": REASON_NO_ROW if strength_available else REASON_NOT_BUILT,',
     '            "reason": REASON_NO_ROW,',
     "test_the_strength_block_distinguishes_an_unreadable_lake_from_an_absent_team"),

    # ⚠️ ANCHORED ON THE SPLITS BUILDER, not efficiency: the two share a byte-identical three-line
    # head, so an efficiency-shaped anchor is AMBIGUOUS (NF-INJ2b). The trailing `"drives"` line is
    # unique to splits, which makes the anchor land on exactly one function.
    ("a zero-game rollup row is served as an available block of nulls",
     BUILDER,
     '    played = [r for r in rows if (_i(r.get("games_played")) or 0) > 0]\n    row = _latest_by_week(played)\n    if row is None:\n        status, reason = _rollup_absence(marts_available=marts_available, has_any_row=bool(rows))\n        return {"status": status, "reason": reason, "as_of_week": None, "games_played": None,\n                "drives": None,',
     '    row = _latest_by_week(rows)\n    if row is None:\n        status, reason = _rollup_absence(marts_available=marts_available, has_any_row=bool(rows))\n        return {"status": status, "reason": reason, "as_of_week": None, "games_played": None,\n                "drives": None,',
     "test_a_zero_game_rollup_row_is_never_served_as_available[build_splits]"),

    # ── schedule / results ───────────────────────────────────────────────────────────────────
    ("an upcoming game is given a 0-0 score instead of nulls",
     BUILDER,
     "    if not completed or team_pts is None or opp_pts is None:\n        team_pts = opp_pts = margin = result = None",
     "    if False:\n        team_pts = opp_pts = margin = result = None\n    elif not completed or team_pts is None or opp_pts is None:\n        team_pts, opp_pts, margin, result = 0, 0, 0, \"T\"",
     "test_an_upcoming_game_carries_no_score_and_no_result"),

    ("the away team's page reads the HOME score column",
     BUILDER,
     '    side, opp = ("home", "away") if is_home else ("away", "home")',
     '    side, opp = ("home", "away")',
     "test_a_completed_game_is_oriented_to_the_team_being_served"),

    ("the record counts scheduled games rather than played ones",
     BUILDER,
     '    played = [g for g in games if g["result"] is not None]',
     "    played = list(games)",
     "test_the_record_counts_only_games_that_were_PLAYED"),

    # ⭐ THE INC-22 BREAK, and it is the one that would ship most easily: the mart HAS a
    # `game_date` column, so serving it looks like the obvious thing to do.
    ("the served kickoff day becomes the mart's UTC date",
     BUILDER,
     '        "game_day": game_day_for(row.get("start_date")),',
     '        "game_day": _s(row.get("game_date")),',
     "test_the_kickoff_day_is_the_LA_day_not_the_marts_utc_date"),

    ("a week label from the mart is served under the banned alias name",
     BUILDER,
     '        "game_id": int(row["game_id"]),\n',
     '        "game_id": int(row["game_id"]),\n        "season_order_week": _i(row.get("season_order_week")),\n',
     "test_no_week_label_reaches_the_served_schedule"),

    ("the team pages are quietly switched off by default",
     WRITER,
     "                        with_teams: bool = True,",
     "                        with_teams: bool = False,",
     "test_the_team_pages_are_published_by_DEFAULT"),

    ("an empty schedule claims nobody has played yet",
     BUILDER,
     "        reason = REASON_NOT_BUILT if not marts_available else REASON_NO_ROW",
     "        status, reason = _block_absence(marts_available=marts_available, has_any_row=False)",
     "test_an_empty_schedule_never_claims_that_nobody_has_played_yet"),

    # ── the universe + the tier ──────────────────────────────────────────────────────────────
    ("the team universe becomes the INTERSECTION of the fit and the dim",
     BUILDER,
     "    universe = sorted(set(by_team_strength) | set(dim_by_team))",
     "    universe = sorted(set(by_team_strength) & set(dim_by_team))",
     "test_the_team_universe_is_the_union_of_the_strength_fit_and_the_season_dim"),

    ("a team-page failure is allowed to fail the serving-critical write",
     WRITER,
     "        try:\n            team_blobs, team_report = build_team_blobs(season, now=now)\n        except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (the bonus surface)",
     "        try:\n            team_blobs, team_report = build_team_blobs(season, now=now)\n        except ZeroDivisionError as exc:  # noqa: BLE001",
     "test_the_team_pages_cannot_fail_the_serving_critical_write"),

    ("the run report pools block availability into one number",
     WRITER,
     '        "efficiency_blocks": _block_counts("efficiency"),',
     '        "efficiency_blocks": {},',
     "test_the_writer_reports_block_availability_per_block_never_pooled"),

    # ── the contract + the route ─────────────────────────────────────────────────────────────
    ("the team page grows a field that reads as a pick",
     CONTRACT,
     "    is_new_to_fbs: bool | None = None",
     "    is_new_to_fbs: bool | None = None\n    best_pick_side: str | None = None",
     "test_the_team_page_declares_no_pick_or_edge_field"),

    ("a contract model escapes the walked registry",
     CONTRACT,
     "    NcaafTeamEfficiency, NcaafTeamSplits, NcaafTeamGame, NcaafTeamSchedule, NcaafTeamPage,",
     "    NcaafTeamEfficiency, NcaafTeamSplits, NcaafTeamGame, NcaafTeamSchedule,",
     "test_every_team_page_model_is_in_the_walked_registry"),

    ("an unpublished team answers 200 with an empty body instead of 404",
     ROUTER,
     '    blob = ncaaf_serving.read_team(team_id)\n    if blob is None:\n        raise HTTPException(status_code=404, detail=f"{_NO_TEAM} (team_id={team_id})")',
     '    blob = ncaaf_serving.read_team(team_id) or {"season": 0, "generated_at": "", "team": {"team_id": team_id, "season": 0}}',
     "test_a_team_with_no_published_page_is_a_404_not_an_empty_body"),
]


def run_one(test_id: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED"."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_id}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    if "no tests ran" in out or "ERROR: not found" in out or "not found:" in out:
        return "NOT-SELECTED"
    return "PASSED" if r.returncode == 0 else "FAILED"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}

    print("baseline (every named clause, unbroken source) …")
    baseline = {t: run_one(t) for *_, t in CASES}
    bad = {t: v for t, v in baseline.items() if v != "PASSED"}
    if bad:
        for t, v in bad.items():
            print(f"🚨 baseline: {t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1
    print(f"  all {len(baseline)} green ✅\n")

    results = []
    try:
        for label, path, find, replace, test_id in CASES:
            original = backups[path]
            n = original.count(find)
            if n == 0:
                results.append((label, test_id, "ANCHOR-MISSING"))
                continue
            if n > 1:
                results.append((label, test_id, f"AMBIGUOUS-ANCHOR (x{n})"))
                continue
            patched = original.replace(find, replace, 1)
            assert patched != original, label
            path.write_text(patched)
            try:
                outcome = run_one(test_id)
            finally:
                path.write_text(original)
            results.append((label, test_id, {
                "PASSED": "GREEN — VACUOUS",
                "FAILED": "RED",
                "NOT-SELECTED": "NOT-SELECTED (the named clause does not exist)",
            }[outcome]))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = sum(1 for *_, s in results if s == "RED")
    for label, test_id, status in results:
        print(f"{'✅' if status == 'RED' else '🚨'} {label.ljust(width)}  →  {status}")
    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
