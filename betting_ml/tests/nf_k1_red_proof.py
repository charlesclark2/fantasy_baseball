"""RED proof for NF-K1's guards — `uv run python betting_ml/tests/nf_k1_red_proof.py`.

Each claim in `test_nf_k1_kdst_board_coverage.py` is proved by re-introducing the defect it guards
against and requiring the named test to go RED. Same harness contract as `nf_tr2_red_proof.py`:

  * the mutation is applied to the SOURCE FILE and asserted to have LANDED — a red proof whose
    mutation silently no-ops reports a false "the guard caught it" (E11.24 #682);
  * ⭐ and where the guard asserts on a TOKEN, the token is asserted GONE after the mutation. A break
    that lands but leaves the asserted substring intact comes back GREEN for the wrong reason
    (E11.24 #815) — `assert_published_position_coverage_XX` still contains
    `assert_published_position_coverage`, so a rename-style break must be checked, not assumed;
  * pytest runs in a SUBPROCESS, so `pytest.raises`' `Failed` (a BaseException) cannot leak past a
    too-narrow `except` and be read as a pass (NF-W6c);
  * ⚠️ ONLY exit code 1 (tests FAILED) counts as RED. 2/3/4/5 is a BROKEN HARNESS, never a caught
    break — otherwise a missing module reads as "the guard caught it" (NF-INFRA1);
  * the file is restored in a `finally`.

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~15s.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_k1_kdst_board_coverage.py"
_EX = "quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py"
_RLB = "quant_sports_intel_models/football/nfl/fantasy/run_league_board.py"
_LS = "app/backend/services/league_scoring.py"
_TSLS = "frontend/lib/league-scoring.ts"
_TSQ = "frontend/lib/fantasy-queries.ts"
_TSC = "frontend/lib/fantasy-claim-copy.ts"
_TSMT = "frontend/components/fantasy/my-teams.tsx"
_API = "app/backend/routers/fantasy.py"

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS = [
    # ── the publish guard ───────────────────────────────────────────────────────────────────────
    ("guard: count ROWS instead of PROJECTED rows (the vacuous version placeholders satisfy)",
     _EX,
     '        projected = r.get("pts") if "pts" in r else r.get("fpPpr")\n'
     '        if pos and projected is not None:',
     '        if pos:',
     "placeholder_rows_do_not_satisfy", None),
    ("guard: report a missing position instead of refusing", _EX,
     '    if problems:\n        raise SystemExit(',
     '    if problems:\n        log.warning(\n            ',
     "missing_any_projectable_position or payload_that_actually_shipped", None),
    ("guard: an empty staging dir passes (a check that found nothing to check)", _EX,
     "    if not checked:\n        # NF1.7 (a)",
     "    if False:\n        # NF1.7 (a)",
     "empty_staging_dir", None),
    ("guard: an unreadable staged file is skipped rather than failed", _EX,
     '            problems.append(f"{path.name}: UNREADABLE',
     '            continue\n        if False:\n            problems.append(f"{path.name}: UNREADABLE',
     "unreadable_staged_file", None),
    ("guard: check only K/DST rather than every PROJECTABLE position", _EX,
     "        missing = [p for p in PROJECTABLE if cov.get(p, 0) == 0]",
     '        missing = [p for p in ("K", "DST") if cov.get(p, 0) == 0]',
     "missing_any_projectable_position", None),
    ("wiring: the guard is never called (wired ≠ invoked)", _EX,
     "    assert_published_position_coverage(out_dir, args.season)",
     "    pass",
     "runs_before_the_publish_decision", "assert_published_position_coverage(out_dir, args.season)"),
    ("wiring: the guard runs AFTER the upload decision", _EX,
     "    assert_published_position_coverage(out_dir, args.season)\n\n    # Upload to S3",
     "    # Upload to S3",
     "runs_before_the_publish_decision", None),
    ("guard: an env-var escape hatch", _EX,
     "    staged = sorted(out_dir.glob(\"*.json\"))",
     "    if os.environ.get(\"NF_K1_SKIP\"):\n        return\n    staged = sorted(out_dir.glob(\"*.json\"))",
     "no_env_var_escape_hatch", None),

    # ── the cause: local-first, then the lake ───────────────────────────────────────────────────
    ("load_kdst: no lake fallback (the pre-NF-K1 local-only read)", _RLB,
     "    kdf = load_kdst_lake(season)\n    if len(kdf):",
     "    kdf = pd.DataFrame()\n    if len(kdf):",
     "falls_back_to_the_lake", None),
    ("load_kdst: always read the lake (a laptop build stops being byte-identical)", _RLB,
     "    if from_lake:\n        return load_kdst_lake(season)",
     "    if True:\n        return load_kdst_lake(season)",
     "prefers_the_local_artifact", None),
    ("call site: the exporter goes back to the local-only read", _EX,
     "        kdf = load_kdst(_ARTIFACTS, args.season, from_lake=args.from_lake)",
     "        from quant_sports_intel_models.football.nfl.fantasy.run_league_board import (\n"
     "            load_kdst_local,\n        )\n"
     "        kdf = load_kdst_local(_ARTIFACTS, args.season)",
     "every_kdst_call_site", "load_kdst(_ARTIFACTS"),
    ("call site: run_league_board goes back to the local-only read", _RLB,
     "        kdst = load_kdst(out_dir, season, from_lake=args.from_lake)",
     "        kdst = load_kdst_local(out_dir, season)",
     "every_kdst_call_site", None),

    # ── the three causes ────────────────────────────────────────────────────────────────────────
    ("published_positions: declare the intent instead of reading the board", _LS,
     "    seen = {normalize_position(p.get(\"pos\")) for p in board_players if isinstance(p, dict)}\n"
     "    return [p for p in PROJECTABLE_POSITIONS if p in seen]",
     "    return list(PROJECTABLE_POSITIONS)",
     "read_off_the_board_not_declared", None),
    ("published_positions: stop folding aliases", _LS,
     "    seen = {normalize_position(p.get(\"pos\")) for p in board_players if isinstance(p, dict)}",
     "    seen = {p.get(\"pos\") for p in board_players if isinstance(p, dict)}",
     "folds_aliases", None),
    ("PROJECTABLE drifts between the API and the exporter", _LS,
     'PROJECTABLE_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "K", "DST")',
     'PROJECTABLE_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")',
     "three_projectable_declarations_agree", None),
    ("server: an unreadable projections blob reports [] instead of None", _API,
     "        logger.warning(\"could not load projections for %s; board positions unknown\", season)\n"
     "        return None",
     "        logger.warning(\"could not load projections for %s; board positions unknown\", season)\n"
     "        return []",
     "server_reports_unknown_positions_as_null", None),
    ("classifier: an unknown board set claims 'not published' (the deploy-skew failure)", _TSLS,
     '  if (!published) return "unknown"',
     "  if (!published) return \"not-published\"",
     "unknown_board_position_set", 'if (!published) return "unknown"'),
    ("hook: `?? []` papers over an absent board_positions", _TSQ,
     "  const boardPositions = query.data?.board_positions ?? null",
     "  const boardPositions = query.data?.board_positions ?? []",
     "unknown_board_position_set", "board_positions ?? null"),
    ("copy: the not-published cell blames the roster", _TSC,
     '  "not-published":\n    "We have not published a projection for this position on the current board, so there was nothing for this player to match against. This is a gap on our side, not a problem with your roster — re-importing will not change it.",',
     '  "not-published":\n    "We could not match this player to our board.",',
     "not_published_copy_owns_the_gap", "not a problem with your roster"),
    ("copy: the not-published cell sends the user round a re-import loop", _TSC,
     "re-importing will not change it.",
     "re-importing usually fixes it.",
     "only_the_unresolved_cause_suggests_a_reimport", None),
    ("component: the cell goes back to one word for all three causes", _TSMT,
     "                      {UNMATCHED_LABEL[classifyUnmatched(r.roster.position, boardPositions)]}",
     "                      not matched",
     "table_cell_and_the_footnote_share_one_classifier", None),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if old not in original:
            print(f"{'BROKEN ❌ (anchor not found)':30} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        mutated = original.replace(old, new, 1)
        # #682 — the mutation must actually land, or a no-op reads as "the guard caught it".
        assert mutated != original, name
        # #815 — where the guard asserts on a token, that token must be GONE, or the break can land
        # and still leave the assertion satisfied (a false GREEN reported as a real finding).
        if gone is not None and gone in mutated:
            print(f"{'BROKEN ❌ (token survives)':30} {name} -> {gone!r} still present")
            failures.append(f"{name}: asserted token survived the mutation")
            continue
        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:30} {name}\n{'':30} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every NF-K1 guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
