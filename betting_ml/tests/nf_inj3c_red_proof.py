#!/usr/bin/env python3
"""NF-INJ3c RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_inj3c_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`).

WHY IT EXISTS FOR THIS STORY. Every defect this routing can have is SILENT. A rookie whose formal
cap stopped firing looks exactly like a healthy rookie — that is precisely the state the story
found, and it survived for the entire life of the mechanism. A boundary that stopped holding (the
rookie frame pointed at NF-INJ3b's certified VETERAN hurdle, or handed the NF-D11 prior) would
produce a plausible number from an uncertified model on a population it never scored, and no output
would look wrong. A rescale that stopped carrying the line would show a healthy fantasy total beside
a shelved player's game count. None of those raises.

The harness contract is carried verbatim from `nf_inj_news_1_red_proof.py`, including all three ways
a red proof lies: a mutation that never LANDS (E11.24 #682), one that lands on the WRONG symbol (the
non-unique anchor), and one that lands and does not MOVE the asserted predicate (#815). It restores
stale backups AT START-UP, because a `| head` closing stdout mid-mutation leaves deliberately-broken
source on disk (E11.26).

⛔ Deliberately not `git checkout --`: that destroys uncommitted work in the files it patches.
"""
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_F = REPO / "quant_sports_intel_models/football/nfl/fantasy"
SEASON = _F / "season_projection.py"
RUNNER = _F / "run_season_projection.py"
ART = _F / "ablation_results/nf_inj3c_rookie_availability.json"
SUITE = "betting_ml/tests/test_nf_inj3c_rookie_availability.py"

FILES = (SEASON, RUNNER, ART)

#: `(label, file, anchor, replacement, gone_after, the ONE test that must go red)`.
CASES = [
    # ══ THE DEFECT ITSELF ═══════════════════════════════════════════════════════════════════════
    ("the rookie frame stops running a formal step at all (the story's own defect, restored)",
     SEASON,
     '        def _rookie_formal(_frame):\n'
     '            """The INCUMBENT constants cap — see boundary (1) above. ⛔ Not the policy router."""\n'
     '            return injury_availability_games(_frame, blend=injury_override_blend)',
     '        def _rookie_formal(_frame):\n'
     '            return _frame["proj_games"].to_numpy()',
     "return injury_availability_games(_frame, blend=injury_override_blend)",
     "test_a_flagged_rookie_is_capped_by_the_formal_status_path"),

    ("the rookie frame never gets a status, so the formal step is unreachable", SEASON,
     '    if roster_status is not None and not roster_status.empty and "proj_status" not in df.columns:',
     "    if False:",
     'if roster_status is not None and not roster_status.empty',
     "test_a_flagged_rookie_is_capped_by_the_formal_status_path"),

    ("build_projection stops handing the rookie frame its roster status", RUNNER,
     "                           roster_status=_rk_status)",
     "                           )",
     "roster_status=_rk_status)",
     "test_build_projection_hands_the_rookie_frame_its_roster_status"),

    ("the status is loaded AFTER the rookie frame, so it can only feed the detector again", RUNNER,
     "    _rk_status = load_forward_roster_status(con, projection_season)\n"
     "    rks = (project_rookies(",
     "    rks = (project_rookies(",
     None,
     "test_build_projection_hands_the_rookie_frame_its_roster_status"),

    # ══ AC-1 — THE CERTIFIED-ARM BOUNDARY ═══════════════════════════════════════════════════════
    ("the rookie frame is 'upgraded' to NF-INJ3b's certified VETERAN hurdle", SEASON,
     '            return injury_availability_games(_frame, blend=injury_override_blend)',
     '            from quant_sports_intel_models.football.nfl.fantasy import (\n'
     '                injury_games_serving as _IGS_rk,\n'
     '            )\n'
     '            return _IGS_rk.served_injury_games(_frame, blend=injury_override_blend)[0]',
     "return injury_availability_games(_frame, blend=injury_override_blend)",
     "test_the_rookie_frame_routes_the_INCUMBENT_CONSTANTS_never_the_certified_veteran_hurdle"),

    ("the boundary's reasoning is deleted, leaving a bare constants call beside a certified model",
     SEASON,
     "    #          here would be an uncertified re-derivation on a population it never scored — MH2.1's",
     "    #          here would be an uncertified re-derivation on a population it never scored — the",
     "MH2.1's",
     "test_the_boundary_is_written_where_a_future_editor_will_read_it"),

    # ══ AC-2 — NF-D11 NOT-APPLICABLE-BY-CONSTRUCTION ════════════════════════════════════════════
    ("the NF-D11 prior is forced onto the rookie frame", SEASON,
     "        absence_prior=None, absence_prior_blend=0.0,   # NF-D11: not-applicable-by-construction",
     "        absence_prior=_absence_prior_for_rookies, absence_prior_blend=1.0,",
     # ⚠️ the token must be unique to the CALL — `absence_prior=None` also appears in this
     #    module's own explanatory header comment, so a bare name never goes absent (#815).
     "absence_prior=None, absence_prior_blend=0.0",
     "test_the_rookie_frame_passes_NO_absence_prior"),

    ("the chain stops self-gating on seasons_missed, so a stray prior would act", SEASON,
     '    if absence_prior_blend > 0 and absence_prior is not None and "seasons_missed" in df.columns:',
     "    if absence_prior_blend > 0 and absence_prior is not None:",
     # ⚠️ `"seasons_missed" in df.columns` also guards `absence_return_games` and
     #    `absence_games_sd`, so the gone-token must carry the chain's own conjunction.
     'absence_prior is not None and "seasons_missed" in df.columns',
     "test_the_chain_self_gates_on_seasons_missed_so_the_ruling_holds_at_both_ends"),

    ("the ruling records the conclusion but drops the mechanism that produced it", SEASON,
     "    #          four terms are prior-NFL-career quantities. A rookie has no prior NFL season, so",
     "    #          four terms are prior-NFL-career quantities. This does not apply to rookies, so",
     "A rookie has no prior NFL season",
     "test_the_ruling_names_the_mechanism_not_just_the_conclusion"),

    # ══ ONE OWNER ═══════════════════════════════════════════════════════════════════════════════
    ("the rookie frame goes back to its own copy of the caps", SEASON,
     "    df = apply_availability_chain(\n"
     "        df,\n"
     "        formal_games=_rookie_formal,",
     "    df = _rookie_local_chain(\n"
     "        df,\n"
     "        formal_games=_rookie_formal,",
     None,
     "test_both_projection_frames_reach_the_SAME_availability_step"),

    ("the shared rescale stops being the owner of proj_games", SEASON,
     '    df["proj_games"] = new_games\n'
     '    df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])\n'
     '    df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])\n'
     '    df["proj_fumbles_lost"] = np.round(\n'
     '        (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)\n'
     "    return score_line(df, prefix=\"proj_\")",
     '    df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])\n'
     '    df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])\n'
     '    df["proj_fumbles_lost"] = np.round(\n'
     '        (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)\n'
     "    return score_line(df, prefix=\"proj_\")",
     None,
     "test_the_games_rescale_has_exactly_one_owner"),

    ("the line stops following the games discount (points stay healthy, games do not)", SEASON,
     "    for col in AVAILABILITY_LINE_COLS:\n"
     "        if col in df.columns:\n"
     "            df[col] = df[col].to_numpy() * scale",
     "    for col in AVAILABILITY_LINE_COLS:\n"
     "        if col in df.columns:\n"
     "            df[col] = df[col].to_numpy()",
     "df[col] = df[col].to_numpy() * scale",
     "test_the_scored_line_moves_with_games_and_the_fumble_rounding_is_the_only_gap"),

    # ══ THE REFACTOR'S OWN GATE ═════════════════════════════════════════════════════════════════
    ("the chain reorders NF-D11 ahead of the formal cap (a veteran row moves)", SEASON,
     "    # ── 1) the FORMAL roster-status cap ─────────────────────────────────────────────────────────\n"
     "    if formal_games is not None:",
     "    if absence_prior_blend > 0 and absence_prior is not None and \"seasons_missed\" in df.columns:\n"
     "        df = rescale_line_to_games(\n"
     "            df, absence_return_games(df, absence_prior, blend=absence_prior_blend))\n"
     "    if formal_games is not None:",
     None,
     "test_the_extraction_reproduces_the_old_three_blocks_BIT_FOR_BIT"),

    ("the reported-absence provenance is stamped from the FILE instead of the decisions", SEASON,
     "    applied = [d for d in decisions if d.get(\"applied\")]\n    if not applied:\n        return",
     "    applied = [{**d, \"applied\": True} for d in decisions]\n    if not applied:\n        return",
     'applied = [d for d in decisions if d.get("applied")]',
     "test_the_extraction_reproduces_the_old_three_blocks_BIT_FOR_BIT"),

    # ══ THE JOIN ════════════════════════════════════════════════════════════════════════════════
    ("the rookie status join stops normalising the board end (the NF-C9 padded-id defect)", SEASON,
     '        df["player_id"] = pd.Series(df["player_id"]).map(_RAO_rk.normalize_player_id).to_numpy()',
     '        df["player_id"] = pd.Series(df["player_id"]).to_numpy()',
     'df["player_id"] = pd.Series(df["player_id"]).map(_RAO_rk.normalize_player_id)',
     "test_the_rookie_status_join_normalises_BOTH_ends"),

    # ══ THE RECORDED EVIDENCE ═══════════════════════════════════════════════════════════════════
    ("the recorded reproduction pin stops reproducing NF-INJ3's 50/60", ART,
     '"reproduces": true', '"reproduces": false', '"reproduces": true',
     "test_the_measured_verification_is_committed_and_every_leg_passed"),

    ("the recorded evidence claims the LIVE 2026 class was an ACTIVE test of the routing", ART,
     '"season": 2026,\n        "rookie_rows": 81,\n        "flagged": 0,\n        "active": false,',
     '"season": 2026,\n        "rookie_rows": 81,\n        "flagged": 0,\n        "active": true,',
     '"flagged": 0,\n        "active": false,',
     "test_the_recorded_evidence_states_that_the_LIVE_class_is_INACTIVE"),
]

_BACKUP_DIR = REPO / ".nf_inj3c_red_proof_backup"


def _slug(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("/", "__")


def _restore_stale_backups() -> None:
    """A previous run killed mid-mutation leaves deliberately broken source on disk. Restore before
    doing anything else — E11.26's own worst case."""
    if not _BACKUP_DIR.exists():
        return
    for b in _BACKUP_DIR.iterdir():
        target = REPO / b.name.replace("__", "/")
        if target.exists():
            target.write_text(b.read_text())
            print(f"restored STALE backup: {target.relative_to(REPO)}")
    shutil.rmtree(_BACKUP_DIR, ignore_errors=True)


def run(test_name: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=REPO, capture_output=True, text=True)
    return r.returncode, r.stdout[-600:]


def main() -> int:
    _restore_stale_backups()
    backups = {p: p.read_text() for p in FILES}
    _BACKUP_DIR.mkdir(exist_ok=True)
    for path, src in backups.items():
        (_BACKUP_DIR / _slug(path)).write_text(src)
    failures: list[str] = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header", "-p", "no:randomly"],
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
    raise SystemExit(main())
