"""NF-INC-0914 — the NFL board publish entrypoint must be EXECUTED by something, not just read.

🔴 THE INCIDENT, DATED. `sports_nfl_board_publish_job` run dd44e28e died in
`export_draft_board_json.main()` at the line that stamps the designation discount onto the
manifest::

    manifest["designationDiscountStamp"] = designation_discount_stamp(
        pdf, designations, season=season)      # NameError: name 'season' is not defined

Every other reference in `main()` is `args.season`; `season` is bound nowhere — not a local, not a
parameter, not a module global. The line sits at `main()`'s top level inside no `if`, `try` or
`with`, so **`main()` crashed unconditionally, on every flag combination, on every path**, from the
moment the break merged. Nothing published; the previously published board kept serving.

⭐ WHY THREE GREEN VERIFICATIONS MISSED IT — the whole design brief for this file.

  1. **CI.** Thirty-one test files import this module. **None of them executed `main()`.** The only
     two guards that touched it read it as TEXT — `assert call in src` and
     `inspect.getsource(EX.main)`. A source-text guard can see that a name is MENTIONED; it can
     never see whether that name RESOLVES. That is the difference between the two, and it is the
     entire incident.
  2. **The ship battery** imports this module for helpers (`weekly_designation_map`,
     `_norm_player_id`) and never calls `main()`. Its `--verify-published` arm reads the PUBLISHED
     artifact, so it is downstream of the very step that crashed and cannot run until it succeeds.
  3. **The operator's 2026-09-13 manual publish** ran code that PREDATES the break (introduced
     2026-09-14 00:14, merged 00:27). There was no fork of entrypoint, flags or branch — the
     divergence was purely temporal. The 07:15 PT scheduled fire was simply **the first execution
     of `main()` by anything, anywhere, after the break landed**.

⭐⭐ AND THE PART WORTH REMEMBERING. The immediately preceding commit (#1100, "make the manifest
stamp a function something actually invokes") had ALREADY diagnosed this exact hazard — "the stamp
block sat inside `main()`, where every symbol it uses resolves statically and NOTHING in the suite
executes it" — and fixed it by extracting the body into a function the tests could call directly.
That remedy was right about the danger and shrank the un-executed surface from the whole block down
to **the single call line that hands the function its arguments**. The next commit changed exactly
that line. The fix relocated the blind spot instead of closing it, and the very next edit found it.

⇒ the only guard that closes the class is one that RUNS the entrypoint. This file does, with the IO
stubbed **at the boundary rather than at the entrypoint**: `main()` does its own real argument
parsing and every line of its own body executes, while the lake/disk/market reads and the S3 upload
are replaced. Everything between those boundaries — including the call site that crashed — is real.

⛔ NON-VACUITY IS LOAD-BEARING HERE. A smoke that merely reaches `return 0` would stay green if a
later change routed around the designation call site, which is the failure it exists to prevent. So
the smoke asserts the branch was genuinely TAKEN: the stamp must be on the staged manifest and must
report a non-zero ELIGIBLE population, neither of which is reachable without executing line 2137.
"""
from __future__ import annotations

import ast
import builtins
import json
import warnings
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX

_MOD = "quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json"
_SRC = Path(EX.__file__)
_SEASON = 2026
# Two designated players, so the discount's ELIGIBLE population is provably non-zero. If this map
# were empty the smoke could reach `return 0` without the designation branch ever mattering.
_DESIGNATED = {"00-0000": "Questionable", "00-0001": "Out"}


def _frame() -> pd.DataFrame:
    """A production-SHAPED board frame: one shipped preset, every PROJECTABLE position present.

    Every PROJECTABLE position is required, not decorative — `assert_published_position_coverage`
    (NF-K1) refuses a staged board missing one, and that guard runs three lines above the crash
    site. A frame that cannot clear it is a frame that never reaches the line under test."""
    rows = []
    for i, pos in enumerate(["QB", "RB", "WR", "TE", "K", "DST"] * 3):
        rows.append(dict(
            config_name="full_ppr", n_teams=12, projection_source="nf1_5",
            player_id=f"00-000{i}", player_name=f"Player {i}", position=pos, team_id="DET",
            is_rookie=False, overall_rank=i + 1, positional_rank=1, proj_games=16.0,
            league_points=200.0 - i, league_points_p10=150.0, league_points_p90=250.0,
            replacement_points=80.0, vor=100.0, vor_p10=60.0, vor_p90=140.0,
        ))
    return pd.DataFrame(rows)


def _projections() -> pd.DataFrame:
    pdf = _frame().copy()
    pdf["season"] = _SEASON
    pdf["proj_fp_ppr"] = pdf["league_points"]
    pdf["proj_fp_std"] = pdf["league_points"] - 20.0
    pdf["proj_fp_half"] = pdf["league_points"] - 10.0
    pdf["fp_ppr_sd"] = 20.0
    pdf["fp_ppr_p10"] = pdf["league_points"] - 40.0
    pdf["fp_ppr_p90"] = pdf["league_points"] + 40.0
    pdf["confidence"] = "medium"
    pdf["draft_overall"] = pdf["overall_rank"]
    return pdf


def _run_main(out_dir: Path, argv: list[str] | None = None) -> int:
    """Execute the real `main()` with IO replaced AT THE BOUNDARY.

    ⭐ THE BOUNDARY IS THE POINT. Each name below is a read of the lake, the local artifacts, the
    market cache or S3 — the edges of the process. Nothing BETWEEN them is stubbed, so
    `board_records`, `projection_records`, `kdst_records`, the publish guards, the coherence report
    and the designation stamp's own call site all execute exactly as they do on the box."""
    argv = argv if argv is not None else ["--season", str(_SEASON), "--out", str(out_dir)]
    with patch(f"{_MOD}.load_boards_local", return_value=_frame()), \
         patch(f"{_MOD}.load_boards_lake", return_value=_frame()), \
         patch(f"{_MOD}.load_projections_local", return_value=_projections()), \
         patch(f"{_MOD}.load_projections_lake", return_value=_projections()), \
         patch(f"{_MOD}.rookie_team_map", return_value={}), \
         patch(f"{_MOD}.player_bio_map", return_value={"00-0000": {}}), \
         patch(f"{_MOD}.bye_week_map", return_value={}), \
         patch(f"{_MOD}.kicker_map", return_value={}), \
         patch(f"{_MOD}.draft_board_names", return_value={}), \
         patch(f"{_MOD}.adp_cache_for", return_value={}), \
         patch(f"{_MOD}.load_player_contributions", return_value=None), \
         patch(f"{_MOD}.PN.roster_casing_authority", return_value={}), \
         patch("quant_sports_intel_models.football.nfl.fantasy.run_league_board.load_kdst",
               return_value=None), \
         patch(f"{_MOD}.weekly_designation_map", return_value=dict(_DESIGNATED)), \
         patch(f"{_MOD}._maybe_publish"):
        return EX.main(argv)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The entrypoint is EXECUTED — the clause that would have caught run dd44e28e
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_publish_entrypoint_runs_end_to_end_with_the_designation_branch_taken(tmp_path):
    """`main()` runs to completion and the designation stamp reaches the staged manifest.

    ⭐ This is the clause that fails on the historical break. A NameError at the stamp's call site
    propagates straight out of `main()`, so no assertion about the manifest is even reached — which
    is precisely the signal, and precisely what no source-reading guard can produce."""
    rc = _run_main(tmp_path)
    assert rc == 0, "export main() must exit 0 on a complete, publishable board"

    manifest = json.loads((tmp_path / "manifest.json").read_text())

    # ⛔ NON-VACUITY. Presence alone is not enough: a stamp could be present with the designation
    #    branch inert. The ELIGIBLE count is only non-zero if the map reached the projection rows,
    #    so this asserts the call site RAN with real arguments rather than merely existing.
    stamp = manifest.get("designationDiscountStamp")
    assert stamp is not None, (
        "the manifest must carry `designationDiscountStamp` — its absence means the call site at "
        "the end of main() never executed, which is the shape of run dd44e28e")
    # ⛔ THE FLOOR IS SEPARATE FROM THE EQUALITY AND BOTH ARE REQUIRED. `== len(_DESIGNATED)`
    #    alone is satisfied by 0 == 0, so emptying the fixture would make this clause pass on
    #    nothing — the vacuity it exists to prevent, reachable by editing the fixture rather than
    #    the code. The floor is what makes the equality mean something.
    assert stamp.get("eligible_rows_on_projections", 0) >= 1, (
        "the discount must see at least one designated row — an empty fixture would satisfy the "
        "equality below by 0 == 0 and this smoke would assert nothing")
    assert stamp.get("eligible_rows_on_projections") == len(_DESIGNATED), (
        "the designation branch must be genuinely TAKEN — a smoke that reaches return 0 without "
        f"the discount seeing its {len(_DESIGNATED)} designated rows would stay green through the "
        "very regression this file exists to catch")


def test_the_season_the_stamp_reads_is_the_season_the_run_was_asked_for(tmp_path):
    """The repaired argument is the RUN'S season, not a guess.

    ⭐ WHY A SEPARATE CLAUSE. The crash is one failure mode of a wrong `season`; a *silently wrong*
    one is the other, and it is worse. `_designation_apply_record` refuses to guess a year
    precisely because a guessed year reads a DIFFERENT build's count and reports it as this one's —
    so binding the caller to `args.season` is a correctness property, not just a scope repair. This
    pins the argument the call site actually passes, so a future edit cannot quietly re-point it at
    a clock-derived or defaulted year while clause 1 stays green."""
    seen: dict = {}
    real = EX.designation_discount_stamp

    def _spy(pdf, designations, season=None):
        seen["season"] = season
        return real(pdf, designations, season=season)

    with patch(f"{_MOD}.designation_discount_stamp", side_effect=_spy):
        rc = _run_main(tmp_path, ["--season", str(_SEASON), "--out", str(tmp_path)])

    assert rc == 0
    assert seen.get("season") == _SEASON, (
        f"the stamp must be handed the run's own --season ({_SEASON}), got {seen.get('season')!r}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The residual the smoke cannot cover: a name on a path this run does not take
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_no_name_in_the_exporter_resolves_nowhere(tmp_path):
    """Every loaded name in every function resolves to a local, a module global or a builtin.

    ⭐ COMPLEMENTARY, NOT REDUNDANT. The smoke above covers the path it executes; this covers the
    branches it does not. The incident's break happened to sit at `main()`'s top level, so the
    smoke catches it — but the same class hiding inside an `if` that the smoke's fixture never
    enters would sail past it, and would then fail on the box exactly as this one did. A static
    scope check costs milliseconds and has no such blind spot."""
    tree = ast.parse(_SRC.read_text())

    def _bound(node, *, into: set) -> set:
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                into.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                into.add(n.name)
            elif isinstance(n, ast.alias):
                into.add((n.asname or n.name).split(".")[0])
            elif isinstance(n, ast.ExceptHandler) and n.name:
                into.add(n.name)
            elif isinstance(n, ast.arg):
                into.add(n.arg)
        return into

    module_scope = _bound(tree, into=set())
    functions = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert functions, "scope check found no functions to check — it would pass on nothing"

    unresolved: list[str] = []
    for fn in functions:
        known = _bound(fn, into=set()) | module_scope | set(dir(builtins))
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in known:
                unresolved.append(f"{fn.name}() line {n.lineno}: {n.id!r}")

    assert not unresolved, (
        "name(s) in the publish path resolve nowhere — this is the NF-INC-0914 class, and on the "
        "box it is a NameError that publishes nothing:\n  " + "\n  ".join(sorted(set(unresolved))))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The lesson itself, pinned — so the next reader does not re-derive it from an outage
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_entrypoint_has_an_executing_caller_and_not_only_a_source_reader():
    """At least one test must CALL `EX.main`, not merely read its source.

    ⭐ THE CLASS, PINNED AT ITS OWN LEVEL. Before this file the suite's only contact with `main()`
    was `inspect.getsource(EX.main)` and `assert call in src`. Both stayed green through a break
    that stopped every publish, because reading a function's text says nothing about whether its
    names resolve. If a future refactor deletes the executing caller and leaves the text-readers,
    the suite silently returns to the state that produced run dd44e28e — so the existence of an
    executing caller is asserted here rather than assumed."""
    tests = Path(__file__).parent
    callers: list[str] = []
    for path in sorted(tests.glob("test_*.py")):
        try:
            # Siblings' docstrings contain regex fragments that raise SyntaxWarning when parsed
            # out of context. That is their file's business, not this clause's — suppress the
            # noise rather than edit another story's guard to quieten our own.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(path.read_text())
        except SyntaxError:                       # pragma: no cover — a broken sibling is not ours
            continue
        for n in ast.walk(tree):
            # An EXECUTING caller: `<alias>.main(...)`. `inspect.getsource(EX.main)` is an
            # ast.Attribute inside another call and is deliberately NOT matched.
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "main" and isinstance(n.func.value, ast.Name)
                    and n.func.value.id in {"EX", "ex", "EXPORT", "export_draft_board_json"}):
                callers.append(f"{path.name}:{n.lineno}")

    assert callers, (
        "no test executes export_draft_board_json.main(). An entrypoint no test executes is an "
        "entrypoint CI cannot see — restore an executing smoke before relying on this suite to "
        "guard the publish path.")
