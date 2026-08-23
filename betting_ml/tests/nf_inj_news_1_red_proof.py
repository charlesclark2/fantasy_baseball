#!/usr/bin/env python3
"""NF-INJ-NEWS-1 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_inj_news_1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`).

WHY IT EXISTS FOR THIS STORY IN PARTICULAR. Every defect this mechanism can have is SILENT. A
disjointness rule that stopped firing would double-discount a player and the board would still look
plausible. A `min` that became a `max` would RAISE an injured player's availability — the founding
priority running backwards, exactly the NF-INJ1 shape. A join that stopped normalising would match
nothing, and a matched-nothing override renders identically to a genuine absence (NF-C9, which cost
Josh Jacobs and DK Metcalf a live board). An expiry that stopped expiring would suppress a healthy
player for the rest of the season. None of those raises, none shows up in a diff you skim, and the
suite is green for all of them unless the clauses actually bite.

The harness contract is carried verbatim from `nf_c9_red_proof.py`, including all three ways a red
proof lies: a mutation that never LANDS (E11.24 #682), one that lands on the WRONG symbol (the
non-unique anchor), and one that lands and does not MOVE the asserted predicate (#815). It restores
stale backups AT START-UP, because a `| head` closing stdout mid-mutation leaves deliberately-broken
source on disk (E11.26).

⛔ Deliberately not `git checkout --`: that destroys uncommitted work in the files it patches.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_F = REPO / "quant_sports_intel_models/football/nfl/fantasy"
LOADER = _F / "reported_absence_overrides.py"
SEASON = _F / "season_projection.py"
RUNNER = _F / "run_season_projection.py"
EXPORTER = _F / "export_draft_board_json.py"
YAML = _F / "data/reported_absence_overrides.yaml"
FIELDS = REPO / "app/backend/services/projection_fields.py"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
OPTIMIZER = REPO / "frontend/lib/draft-optimizer.ts"
SUITE = "betting_ml/tests/test_nf_inj_news_1_reported_absence.py"

FILES = (LOADER, SEASON, RUNNER, EXPORTER, YAML, FIELDS, COPY, SHARED, RANKINGS,
         OPTIMIZER)

#: `(label, file, anchor, replacement, gone_after, the ONE test that must go red)`.
#: `gone_after` is the token the named clause asserts on; after the mutation it must NOT be in the
#: file, or the break landed without moving the assertion and GREEN would mean "the mutation
#: missed" rather than "the guard is vacuous". `None` where the clause asserts on an ABSENCE.
CASES = [
    # ══ RULE 1 — DISJOINTNESS ════════════════════════════════════════════════════════════════════
    ("disjointness deleted: apply the override to a formally-tagged player too", SEASON,
     "        if formal[i]:",
     "        if False:",
     "if formal[i]:",
     "test_a_formally_tagged_player_is_never_touched_by_an_override[RES]"),

    ("disjointness reads a hand-copied literal set instead of the formal map", SEASON,
     'formal = df["proj_status"].astype("string").map(_INJURY_STATUS_GAMES_CAP).notna().to_numpy()',
     'formal = df["proj_status"].isin(["RES", "PUP", "NFI", "SUS"]).to_numpy()',
     # ⚠️ the `gone` token must be unique to THIS function: a bare
     # `map(_INJURY_STATUS_GAMES_CAP)` also appears in `injury_availability_games`, so the
     # mutation would read as "did not bite" while having landed perfectly.
     'formal = df["proj_status"].astype("string").map(',
     "test_the_disjointness_rule_reads_the_formal_map_itself_not_a_copy_of_its_keys"),

    # ══ RULE 2 — CAP-ONLY / MONOTONE ═════════════════════════════════════════════════════════════
    ("the cap can RAISE availability (min -> max): the injury priority backwards", SEASON,
     "        eg[i] = min(before, cap) if np.isfinite(before) else cap",
     "        eg[i] = max(before, cap) if np.isfinite(before) else cap",
     "eg[i] = min(before, cap)",
     "test_an_override_can_never_raise_expected_games"),

    ("the hard cap becomes a 0.7 blend, silently overruling the operator's number", SEASON,
     "        cap = float(season_games - row.expected_games_missed)",
     "        cap = float(0.3 * 13.6 + 0.7 * (season_games - row.expected_games_missed))",
     "cap = float(season_games - row.expected_games_missed)",
     "test_the_cap_is_a_hard_min_not_a_blend"),

    ("an inert cap is reported as a working discount", SEASON,
     '"inert": bool(np.isfinite(before) and eg[i] >= before - 1e-9),',
     '"inert": False,',
     '"inert": bool(',
     "test_an_override_can_never_raise_expected_games"),

    # ══ RULE 3 — NORMALISED JOIN, VERIFIED BY NAME ═══════════════════════════════════════════════
    ("the board end of the join stops normalising (the NF-C9 padded-id defect)", SEASON,
     'board_ids = pd.Series(df["player_id"]).map(_RAO.normalize_player_id).to_numpy()',
     'board_ids = pd.Series(df["player_id"]).astype(str).to_numpy()',
     "map(_RAO.normalize_player_id)",
     "test_a_whitespace_padded_board_id_still_receives_its_override"),

    ("an unmatched override is silently skipped instead of reported", SEASON,
     '''            decisions.append({
                "player_id": row.player_id, "player_name": row.player_name,
                "applied": False, "reason": _RAO.REASON_UNMATCHED,
                "detail": "no board row carries this player_id — verify the id BY NAME",
            })
            continue''',
     "            continue",
     "REASON_UNMATCHED",
     "test_an_override_matching_no_board_row_is_REPORTED_not_silently_dropped"),

    # ══ RULE 4 — review_by EXPIRY ════════════════════════════════════════════════════════════════
    ("expiry deleted: a stale judgment suppresses a healthy player forever", LOADER,
     "        if row.review_by < as_of:",
     "        if False:",
     "if row.review_by < as_of:",
     "test_a_row_past_its_review_by_stops_applying_and_says_so"),

    # ══ THE LOAD CONTRACT ════════════════════════════════════════════════════════════════════════
    ("source_url stops being required: a cap with no citation", LOADER,
     '_REQUIRED_FIELDS = ("player_id", "player_name", "expected_games_missed",\n'
     '                    "source_url", "entered_by", "entered_at", "review_by")',
     '_REQUIRED_FIELDS = ("player_id", "player_name", "expected_games_missed",\n'
     '                    "entered_by", "entered_at", "review_by")',
     None,
     "test_a_row_with_no_source_url_is_rejected"),

    ("a duplicate silently picks the first row instead of rejecting the group", LOADER,
     "        if len(group) > 1:",
     "        if False:",
     "if len(group) > 1:",
     "test_two_rows_for_one_player_reject_the_WHOLE_GROUP"),

    ("an unreadable file reports as an empty one", LOADER,
     "        result.readable = False",
     "        result.readable = True",
     "result.readable = False",
     "test_an_unreadable_file_is_a_DIFFERENT_state_from_an_empty_one"),

    # ══ THE LEAKAGE GATE ═════════════════════════════════════════════════════════════════════════
    ("the season gate is removed: a 2026 judgment reaches a 2019 backtest fold", LOADER,
     "    if season is not None and file_season is not None and int(season) != file_season:",
     "    if False:",
     "int(season) != file_season",
     "test_the_season_gate_yields_nothing_for_a_different_season"),

    ("the historical band panel starts receiving operator judgments", RUNNER,
     "    vets = build_veteran_projection(con, base_season, int(target_season), schema, band_model=None)",
     "    vets = build_veteran_projection(con, base_season, int(target_season), schema,\n"
     "                                    band_model=None, reported_absence_rows=[])",
     None,
     "test_the_historical_panel_path_never_passes_overrides"),

    # ══ THE PAYLOAD STAMP ════════════════════════════════════════════════════════════════════════
    ("the stamp is sprayed onto every row as null instead of omitted", EXPORTER,
     '''        _ra = _reported_absence(r)
        if _ra:
            recs[-1]["reportedAbsence"] = _ra''',
     '        recs[-1]["reportedAbsence"] = _reported_absence(r)',
     None,
     "test_an_un_overridden_row_carries_NO_reportedAbsence_KEY_AT_ALL"),

    ("the export stamp re-reads the overrides FILE instead of the built board", EXPORTER,
     '    url = r.get("reported_absence_source_url")',
     "    from quant_sports_intel_models.football.nfl.fantasy import reported_absence_overrides\n"
     "    _ = reported_absence_overrides.load_overrides\n"
     '    url = r.get("reported_absence_source_url")',
     None,
     "test_the_stamp_is_written_from_what_was_APPLIED_not_from_the_override_file"),

    ("a provenance column is dropped from the emitted schema", SEASON,
     '''REPORTED_ABSENCE_COLS = [
    "reported_absence_source_url", "reported_absence_entered_at", "reported_absence_games_missed",
]''',
     '''REPORTED_ABSENCE_COLS = [
    "reported_absence_entered_at", "reported_absence_games_missed",
]''',
     '"reported_absence_source_url", "reported_absence_entered_at"',
     "test_the_provenance_columns_survive_the_emitted_schema"),

    ("the citation is withheld from the free board while the capped number is shown", FIELDS,
     'PAID_SCORING_FIELDS: frozenset[str] = frozenset({"fpStd", "fpHalf"})',
     'PAID_SCORING_FIELDS: frozenset[str] = frozenset({"fpStd", "fpHalf", "reportedAbsence"})',
     None,
     "test_the_provenance_fields_are_public_because_nothing_here_is_scorable"),

    # ══ HONESTY ══════════════════════════════════════════════════════════════════════════════════
    ("the curated file claims the overrides improve the projection", YAML,
     "# ⚖️ WHAT A ROW IN THIS FILE IS:",
     "# These overrides make the projection more accurate for injured players.\n"
     "# ⚖️ WHAT A ROW IN THIS FILE IS:",
     None,
     "test_no_module_or_data_file_in_this_story_claims_accuracy_or_forecasts_a_return"),

    ("the curated file forecasts a return date", YAML,
     "schema_version: 1",
     "# Each capped player will return in the week after his review_by date.\nschema_version: 1",
     None,
     "test_no_module_or_data_file_in_this_story_claims_accuracy_or_forecasts_a_return"),

    # ══ THE FRONTEND — where a reader actually meets the claim ═══════════════════════════════════
    ("the copy drops the 'this is manual, not a model output' sentence", COPY,
     '  "This is a manual judgment, not a model output. It has not been tested against outcomes."',
     '  "We adjusted this player\'s games projection."',
     "not a model output. It has not been tested",
     "test_the_copy_says_out_loud_that_this_is_manual_and_untested"),

    ("the copy forecasts a return date", COPY,
     '  "It is not a medical opinion and not a return date — our projection carries no view on when he plays again."',
     '  "He will return once the reported absence ends."',
     "not a return date",
     "test_the_copy_never_forecasts_a_return_or_claims_an_improvement"),

    ("the copy claims the override makes the projection better", COPY,
     'export const REPORTED_ABSENCE_SUMMARY =',
     'export const REPORTED_ABSENCE_SUMMARY_UNUSED = "x"\nexport const REPORTED_ABSENCE_SUMMARY =\n  "A more accurate games figure for this player." ||',
     None,
     "test_the_copy_never_forecasts_a_return_or_claims_an_improvement"),

    ("the chip is nested inside AvailabilityFlag, hiding it from the motivating case", SHARED,
     "      {asOf && <p className=\"mt-2 text-gray-500\">{asOf}</p>}\n    </InfoTip>\n  )\n}\n\n// \u2550\u2550 NF-C9",
     "      {asOf && <p className=\"mt-2 text-gray-500\">{asOf}</p>}\n      <ReportedAbsence reported={null} />\n    </InfoTip>\n  )\n}\n\n// \u2550\u2550 NF-C9",
     None,
     "test_the_chip_is_a_DISTINCT_component_from_the_availability_flag_and_the_designation"),

    ("a surface that renders `g` stops rendering the stamp", RANKINGS,
     "                            <ReportedAbsence reported={p.reportedAbsence} />",
     "                            {null}",
     "<ReportedAbsence ",
     "test_the_chip_is_bound_on_every_surface_that_renders_the_games_number"),

    ("the optimizer starts READING the stamp, pricing the judgment twice", OPTIMIZER,
     "  reportedAbsence?: { sourceUrl?: string | null; enteredAt?: string | null } | null",
     "  reportedAbsence?: { sourceUrl?: string | null; enteredAt?: string | null } | null\n"
     "  scoreHack = (p: any) => (p.reportedAbsence ? 0 : 1)",
     None,
     "test_the_stamp_never_reaches_ordering_or_the_optimizer"),

    # ══ BOTH POPULATIONS — the defect the measurement found ══════════════════════════════════════
    ("the rookie path stops applying the cap (the Tyson class becomes unreachable)", SEASON,
     "        _new_games, _ra_dec = reported_absence_games(df, reported_absence_rows)",
     "        _new_games, _ra_dec = (df[\"proj_games\"].to_numpy(), [])",
     "_ra_dec = reported_absence_games(",
     "test_the_cap_reaches_the_ROOKIE_path_not_only_the_veteran_one"),

    ("build_projection stops passing the overrides to the rookie half", RUNNER,
     "                           reported_absence_rows=_ra.rows, reported_absence_log=_ra_log)\n"
     "           if not incoming.empty else pd.DataFrame())",
     "                           )\n           if not incoming.empty else pd.DataFrame())",
     None,
     "test_the_cap_reaches_the_ROOKIE_path_not_only_the_veteran_one"),

    ("the two halves' decisions stop being reconciled (an alert on every healthy row)", RUNNER,
     "    decisions = list(best.values())",
     "    decisions = list(decisions)",
     "decisions = list(best.values())",
     "test_a_rookie_override_is_not_reported_as_unmatched_by_the_veteran_half"),

    ("reconciliation loses the actionable reason and reports UNMATCHED instead", RUNNER,
     "        elif not prev.get(\"applied\") and prev.get(\"reason\") == REASON_UNMATCHED:",
     "        elif False:",
     'prev.get("reason") == REASON_UNMATCHED',
     "test_a_real_refusal_outranks_not_in_this_half"),
]

_BACKUP_DIR = REPO / ".nf_inj_news_1_red_proof_backup"


def _slug(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("/", "__")


def _restore_stale_backups() -> None:
    """A previous run killed mid-mutation (a `| head` closing stdout, a Ctrl-C) leaves deliberately
    broken source on disk. Restore before doing anything else — E11.26's own worst case."""
    if not _BACKUP_DIR.exists():
        return
    for b in _BACKUP_DIR.iterdir():
        target = REPO / b.name.replace("__", "/")
        if target.exists():
            target.write_text(b.read_text())
            print(f"restored STALE backup: {target.relative_to(REPO)}")
    shutil.rmtree(_BACKUP_DIR, ignore_errors=True)


def _write_backups(backups: dict) -> None:
    _BACKUP_DIR.mkdir(exist_ok=True)
    for path, src in backups.items():
        (_BACKUP_DIR / _slug(path)).write_text(src)


def run(test_name: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-600:]


def main() -> int:
    _restore_stale_backups()
    backups = {p: p.read_text() for p in FILES}
    _write_backups(backups)
    failures: list[str] = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for label, path, old, new, gone, test in CASES:
            src = backups[path]
            # ⚠️ A MISSING ANCHOR IS A FAILURE, NOT A SKIP (E11.24 #682).
            if old not in src:
                failures.append(f"{label}: PATCH ANCHOR NOT FOUND in {path.name}")
                print(f"⚠️  ANCHOR MISSING  {label}  ({path.name})")
                continue
            # ⚠️ AND IT MUST BE UNIQUE, or `replace(..., 1)` may patch a different occurrence than
            # the one under test and report a sound guard as vacuous (the dangerous direction).
            if src.count(old) != 1:
                failures.append(f"{label}: ANCHOR IS NOT UNIQUE ({src.count(old)}x) in {path.name}")
                print(f"⚠️  ANCHOR AMBIGUOUS  {label}  ({path.name})")
                continue
            patched = src.replace(old, new, 1)
            assert patched != src, f"{label}: the replacement is a no-op"
            # ⚠️ AND IT MUST MOVE THE ASSERTED PREDICATE (E11.24 #815).
            if gone is not None and gone in patched:
                failures.append(f"{label}: the mutation left {gone!r} in place")
                print(f"⚠️  MUTATION DID NOT BITE  {label}")
                continue
            path.write_text(patched)
            code, out = run(test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {label}  ->  {test}")
            if code == 0:
                failures.append(f"{label} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
        print("\nrestored all files")

    if failures:
        print(f"\n❌ {len(failures)} VACUOUS OR MIS-LANDED CLAUSE(S):\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(CASES)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
