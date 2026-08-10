"""RED-proof for `test_e9_61_name_casing.py` — break the source, prove the NAMED guard goes red.

A green suite proves nothing about a guard that cannot fail (E9.60 found three passing on nothing;
E9.61's own first cut shipped a vacuous column-position assertion). Each case below reverts one
specific behaviour to its pre-fix form — several of them literally restore the code that produced
"MacK Hollins" — and asserts a NAMED test detects it.

⭐ THE MUTATION IS APPLIED IN-PROCESS AND ITS LANDING IS ASSERTED (`old` must actually be present),
because a red-proof whose edit silently no-ops reports "the guard caught it" when nothing happened —
the failure mode recorded at E11.24 #682.

    uv run python betting_ml/tests/e9_61_name_casing_red_proof.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FANTASY = "quant_sports_intel_models/football/nfl/fantasy"
NAMING = f"{FANTASY}/player_naming.py"
BOARD = f"{FANTASY}/export_draft_board_json.py"
TRACK = f"{FANTASY}/export_track_record_json.py"
SUITE = "betting_ml/tests/test_e9_61_name_casing.py"

# (label, file, old, new, the test that MUST go red)
CASES: list[tuple[str, str, str, str, str]] = [
    (
        "restore the Mac rule that produced 'MacK Hollins'",
        NAMING,
        '    out = re.sub(r"\\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), out)',
        '    for _pre in ("Mc", "Mac"):\n'
        '        _i = 0\n'
        '        while (_i := out.find(_pre, _i)) != -1:\n'
        '            _j = _i + len(_pre)\n'
        '            if _j < len(out) and out[_j].isalpha():\n'
        '                out = out[:_j] + out[_j].upper() + out[_j + 1:]\n'
        '            _i = _j',
        "test_the_mac_rule_no_longer_invents_an_internal_capital",
    ),
    (
        "drop the Mc rule as well (over-correcting the Mac fix)",
        NAMING,
        '    out = re.sub(r"\\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), out)',
        "    pass",
        "test_the_mc_rule_survives_because_it_is_the_one_that_earns_its_keep",
    ),
    (
        "de-shout EVERY input again (the bug that served 'Kc Concepcion')",
        NAMING,
        "    name = de_shout(raw_name) if raw_name.isupper() else raw_name",
        "    name = de_shout(raw_name)",
        "test_a_name_that_is_not_shouting_is_left_alone",
    ),
    (
        "remove the casefold gate — adopt the roster name unconditionally",
        NAMING,
        "    return authority if ours.casefold() == str(authority).casefold() else ours",
        "    return authority",
        "test_a_roster_disagreement_that_is_more_than_case_is_refused",
    ),
    (
        "invert the casefold gate",
        NAMING,
        "    return authority if ours.casefold() == str(authority).casefold() else ours",
        "    return authority if ours.casefold() != str(authority).casefold() else ours",
        "test_the_output_always_casefolds_equal_to_the_input",
    ),
    (
        "ignore the authority entirely (a module that is wired but inert)",
        NAMING,
        "    if authority and str(authority).casefold() == name.casefold():\n"
        "        return str(authority)",
        "    if False:\n        pass",
        "test_every_live_case_defect_is_repaired_when_the_authority_knows",
    ),
    (
        "delete the frozen fallback (the S3-outage regression)",
        NAMING,
        '    "DEVONTA SMITH": "DeVonta Smith",',
        "",
        "test_the_frozen_fallback_keeps_the_pre_authority_answer_when_the_roster_is_unreachable",
    ),
    (
        "let the frozen map override a live authority (the precedence bug this proof caught)",
        NAMING,
        "    if authority and str(authority).casefold() == name.casefold():\n"
        "        return str(authority)\n"
        "    if raw_name.isupper():",
        "    if raw_name.isupper():",
        "test_the_authority_wins_over_the_frozen_fallback",
    ),
    (
        "drop the non-case repair for De'Von Achane",
        NAMING,
        '    "devon achane": "De\'Von Achane",  # the source drops the apostrophe entirely',
        "",
        "test_a_repair_that_changes_characters_is_not_a_casing_repair",
    ),
    (
        "treat a D/ST unit label as a person's name",
        NAMING,
        "    if raw_name.upper().endswith(_UNIT_SUFFIXES):  # \"DEN D/ST\" — a unit label, not a person\n"
        "        return raw_name",
        "    if False:\n        pass",
        "test_a_unit_name_is_not_a_person",
    ),
    (
        "silence the unreachable-authority warning",
        NAMING,
        "        log.warning(\n"
        '            "name-casing authority unavailable (roster read failed: %s: %s) — names will be served "',
        "        log.info(\n"
        '            "name-casing authority unavailable (roster read failed: %s: %s) — names will be served "',
        "test_an_unreachable_authority_is_reported_rather_than_silently_empty",
    ),
    (
        # ⚠️ The first attempt at this case re-keyed only the SELECT and came back GREEN — the stub
        # connection returns a fixed frame regardless of the query text, so a SQL-only edit is
        # invisible to a behavioural test. The realistic regression (and the one that actually
        # changes the returned mapping) is re-keying the comprehension.
        "key the authority on the name instead of the id",
        NAMING,
        "    out = {str(r.gsis_id): str(r.full_name) for r in df.itertuples()}",
        "    out = {str(r.full_name).upper(): str(r.full_name) for r in df.itertuples()}",
        "test_the_authority_is_keyed_on_the_id_not_the_name",
    ),
    (
        "stop passing the authority to board_records (Rankings + league boards)",
        BOARD,
        "        skill = board_records(grp, rookie_teams, byes, casing)",
        "        skill = board_records(grp, rookie_teams, byes)",
        "test_the_board_export_passes_the_authority_to_both_record_builders[board_records]",
    ),
    (
        "stop passing the authority to projection_records (Projections + Player Search)",
        BOARD,
        "        projections = projection_records(pdf, rookie_teams, byes, bio, contrib_map, casing)",
        "        projections = projection_records(pdf, rookie_teams, byes, bio, contrib_map)",
        "test_the_board_export_passes_the_authority_to_both_record_builders[projection_records]",
    ),
    (
        "drop the repaired-count alert (an S3 failure reads as a clean export)",
        BOARD,
        "        if casing and not repaired:",
        "        if False:",
        "test_the_board_export_reports_what_the_authority_did",
    ),
    (
        "stop passing the authority to season_records (Track Record)",
        TRACK,
        "            recs = season_records(df, casing)",
        "            recs = season_records(df)",
        "test_the_track_record_export_resolves_the_authority_too",
    ),
    (
        "re-grow an independent rule pass in the board exporter",
        BOARD,
        "def _titlecase(name: str, authority: str | None = None) -> str:",
        "def _titlecase(name: str, authority: str | None = None) -> str:\n"
        "    if name.isupper():\n"
        "        return name.title()",
        "test_the_board_exporter_no_longer_carries_its_own_rule_pass",
    ),
    (
        "re-grow the hand map in the track-record exporter",
        TRACK,
        "def display_name(raw, authority: str | None = None) -> str:",
        '_KNOWN_CASINGS = {"CEEDEE LAMB": "CeeDee Lamb"}\n\n\n'
        "def display_name(raw, authority: str | None = None) -> str:",
        "test_the_track_record_exporter_no_longer_carries_its_own_rule_pass",
    ),
    (
        "quietly extend the frozen fallback map",
        NAMING,
        '    "DK METCALF": "DK Metcalf",',
        '    "DK METCALF": "DK Metcalf",\n    "SOME NEWGUY": "Some NewGuy",',
        "test_the_frozen_fallback_map_is_not_quietly_growing",
    ),
]


def run_case(label: str, rel: str, old: str, new: str, test: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(
            ROOT, work, symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git", "node_modules", ".next", ".venv", "__pycache__", "*.parquet", "*.pkl",
                ".pytest_cache", "dbt_packages", "target", "artifacts",
            ),
        )
        path = work / rel
        src = path.read_text()
        # ⭐ the mutation must LAND — a no-op edit reports a false "the guard caught it"
        if src.count(old) != 1:
            return "ANCHOR", f"anchor found {src.count(old)}x in {rel} (need exactly 1)"
        path.write_text(src.replace(old, new, 1))
        if path.read_text() == src:
            return "NOOP", "the mutation did not change the file"

        r = subprocess.run(
            [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True,
        )
        if r.returncode != 0:
            return "RED", ""
        return "GREEN", (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else ""


def main() -> int:
    print(f"RED-proof: {len(CASES)} deliberate breaks\n")
    bad = 0
    for label, rel, old, new, test in CASES:
        verdict, detail = run_case(label, rel, old, new, test)
        if verdict == "RED":
            print(f"  RED   ✅  {label}\n            └ {test}")
        else:
            bad += 1
            print(f"  {verdict:5} ❌  {label}\n            └ {test}\n            └ {detail}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} RED")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
