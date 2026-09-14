"""nf_wk_mt1_red_proof.py — prove NF-WK-MT1's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here (the shape `nf_wk_fe1_red_proof.py`
established, reused deliberately rather than re-invented):
  1. **the mutation never LANDS** (#682) — every mutation asserts the file actually CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — a replacing mutation asserts the
     OLD token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied;
  4. **the node id COLLECTS NOTHING** — pytest exits non-zero on an unresolvable node id, so a
     renamed guard reports a perfect RED for a test that no longer exists. Every case's node id is
     resolved during the BASELINE phase, before any source is touched.
⭐ Plus a BASELINE-PASS leg (the guard must be GREEN on unbroken source, or "red" means nothing) and
a NOT-SELECTED leg (a mutation must not turn some OTHER test red and be credited to this one).

🩹 WHAT THIS HARNESS ALREADY CAUGHT, before it proved anything else: the three cache clauses looked
up the route by a PATH CONSTANT declared in the test file, so renaming the real route to a CHILD of
the free reads — the exact breach they exist to refuse — left them reading the old string and
passing. They now resolve the route by its ENDPOINT FUNCTION and ask the cache rules about the path
it ACTUALLY serves. That defect was invisible to review and to a green suite.

⚠️ TWO MUTATIONS LAND OUTSIDE `app/backend` ON PURPOSE, and neither is a scorer:
`league_presets.py` (a preset CONFIG — the spec's literal "deliberate scoring-weight mutation") and
`projection_fields.STAT_FIELD` (the wrong-key class the parity clause exists to catch). Both are
restored in a `finally`, and the start-up sweep restores them even if this process is killed.

⛔ Restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's own
worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson).

⚠️ NOT SAFE TO RUN CONCURRENTLY WITH ITSELF — the start-up sweep would treat another instance's
in-flight backup as stale. One at a time.

RUN (LAPTOP, ~90 s):
    uv run python betting_ml/tests/nf_wk_mt1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TESTS = _REPO / "betting_ml/tests"

_ADAPTER = _REPO / "app/backend/services/weekly_league_board.py"
_CONTRACT = _REPO / "app/backend/models/nfl_weekly.py"
_ROUTER = _REPO / "app/backend/routers/fantasy.py"
_FIELDS = _REPO / "app/backend/services/projection_fields.py"
_PRESETS = _REPO / "quant_sports_intel_models/football/nfl/fantasy/league_presets.py"

_GUARD = _TESTS / "test_nf_wk_mt1_weekly_league_board.py"
_GUARD_FILES = (_GUARD,)

#: An unrelated clause that must stay GREEN through every mutation — otherwise a RED is not
#: attributable to the guard it is credited to.
NOT_SELECTED = f"{_TESTS / 'test_freemium_tier.py'}::test_every_capability_is_placed_on_exactly_one_side"

#: The route's decorator AND its function-level dependency, as ONE anchor.
#:
#: ⭐ IT HAS TO BE ONE ANCHOR, and the RED proof is what established that: the ROUTER-LEVEL
#: `Depends(require_fantasy_access)` is what actually 403s an unentitled caller, so swapping only
#: the function-level dependency ADDS a gate without removing one and the guard stays green — an
#: insufficient mutation reading exactly like a vacuous guard. Moving the route to another router
#: object is the only break that really removes the gate, and that means moving the decorator and
#: the signature together.
_ROUTE_SIGNATURE = """\
@router.get("/nfl/weekly/league-board")
def nfl_weekly_league_board(
    request: Request,
    league_id: str = Query(..., description="a saved league id belonging to the caller"),
    season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100),
    week: int | None = Query(default=None, ge=1, le=22),
    user_id: str = Depends(require_fantasy_access),"""


def _resigned(router_name: str, dep: str) -> str:
    """The same signature re-homed onto another router object with another gate."""
    return (
        _ROUTE_SIGNATURE
        .replace("@router.get", f"@{router_name}.get", 1)
        .replace("user_id: str = Depends(require_fantasy_access),", dep, 1)
    )


_BAK_SUFFIX = ".redproof.bak"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── boundary (a): no fourth scorer ──────────────────────────────────────────────────────────
    ("the adapter scores points itself instead of calling the one server scorer",
     _ADAPTER,
     '        points = league_scoring.score_row(player, pos, resolved, stat_field)["pts"]',
     '        points = sum(\n'
     '            float(w) * float(player.get(stat_field.get(k)) or 0)\n'
     '            for k, w in (resolved.get("per_stat") or {}).items()\n'
     '        )',
     f"{_GUARD}::test_every_weekly_point_comes_out_of_the_one_server_scorer"),

    ("the adapter carries a scoring weight of its own",
     _ADAPTER,
     "_CARRIED_FIELDS: tuple[str, ...] = (",
     "_LEGACY_RECEPTION_WEIGHT = 1.0\n\n_CARRIED_FIELDS: tuple[str, ...] = (",
     f"{_GUARD}::test_the_adapter_holds_no_numeric_literal_and_so_cannot_hold_a_scoring_weight"),

    ("the adapter walks the league's scoring table — the shape of a scorer",
     _ADAPTER,
     "    scored: list[dict] = []\n",
     "    scored: list[dict] = []\n"
     "    for _k, _w in (resolved.get('per_stat') or {}).items():\n"
     "        pass\n",
     f"{_GUARD}::test_the_adapter_never_iterates_a_scoring_rule_table"),

    # ── boundary (b): the band is carried, never re-expressed ───────────────────────────────────
    ("the band is rescaled on its way to the wire",
     _ADAPTER,
     '        row["bandP10"] = player.get(league_scoring.BASE_P10_FIELD)',
     '        row["bandP10"] = (player.get(league_scoring.BASE_P10_FIELD) or 0) * 2',
     f"{_GUARD}::test_the_served_band_is_the_payloads_own_band_byte_identical"),

    ("score_row's own rescaled interval is carried onto the wire as this league's band",
     _ADAPTER,
     '        row["bandP10"] = player.get(league_scoring.BASE_P10_FIELD)\n'
     '        row["bandP90"] = player.get(league_scoring.BASE_P90_FIELD)',
     '        _rescaled = league_scoring.score_row(player, pos, resolved, stat_field)\n'
     '        row["bandP10"] = _rescaled["p10"]\n'
     '        row["bandP90"] = _rescaled["p90"]',
     f"{_GUARD}::test_the_rescaled_interval_score_row_returns_is_discarded"),

    ("the PPR point the band belongs to is dropped from the contract",
     _CONTRACT,
     "    pprPts: float | None = None\n",
     "",
     f"{_GUARD}::test_the_contract_serves_the_ppr_point_the_band_belongs_to"),

    # ── the parity clause (the spec's literal ask: a deliberate scoring-weight mutation) ─────────
    ("a SCORING WEIGHT moves, so our full-PPR no longer reproduces full-PPR",
     _PRESETS,
     '"rec_yds": 0.1, "rec_td": 6.0,',
     '"rec_yds": 0.1, "rec_td": 5.0,',
     f"{_GUARD}::test_the_server_scorer_reproduces_full_ppr_over_the_weekly_line"),

    ("a component is mapped to the WRONG stat key (the NF-C0e class the clause exists to catch)",
     _FIELDS,
     '"targets": "tgt", "rec": "rec", "rec_yds": "recYds", "rec_td": "recTd",',
     '"targets": "tgt", "rec": "tgt", "rec_yds": "recYds", "rec_td": "recTd",',
     f"{_GUARD}::test_the_server_scorer_reproduces_full_ppr_over_the_weekly_line"),

    # ── the substrate refusal ───────────────────────────────────────────────────────────────────
    ("the public payload is scored to a roster of honest-looking zeroes instead of refused",
     _ADAPTER,
     "    if not present:\n",
     "    if present is None:\n",
     f"{_GUARD}::test_the_public_payload_is_refused_rather_than_scored_to_zero"),

    ("both refusals report the same cause, so two different fixes look identical",
     _ADAPTER,
     '"this week\'s projection carries no players at all, so there is nothing to score"',
     '"this week\'s projection cannot be scored"',
     f"{_GUARD}::test_an_empty_week_is_refused_with_a_different_cause_than_a_reduced_one"),

    # ── coverage honesty ────────────────────────────────────────────────────────────────────────
    ("every league term is reported APPLIED, including ones the weekly line cannot express",
     _ADAPTER,
     "        fields=league_scoring.available_fields(weekly_players),",
     "        fields=None,",
     f"{_GUARD}::test_a_league_term_the_weekly_line_cannot_express_is_reported_captured"),

    # ── absences ────────────────────────────────────────────────────────────────────────────────
    ("two different absence causes collapse onto one reason",
     _ADAPTER,
     '            reason = "position_absent_this_week"',
     '            reason = "not_in_weekly_payload"',
     f"{_GUARD}::test_each_absence_cause_is_reachable_and_distinct"),

    ("a per-player row is given a manifest-level reason this route cannot know",
     _ADAPTER,
     '    "roster_row_unnamed": (',
     '    "pit_gate_dropped": "Held back by our point-in-time check.",\n'
     '    "roster_row_unnamed": (',
     f"{_GUARD}::test_no_row_is_ever_given_a_manifest_level_reason_it_cannot_know"),

    ("the served positions are restated from the constant instead of read off the rows",
     _ADAPTER,
     "    return [p for p in nfl_weekly.PROJECTED_POSITIONS if p in seen]",
     "    return list(nfl_weekly.PROJECTED_POSITIONS)",
     f"{_GUARD}::test_weekly_positions_is_read_off_the_rows_not_restated_from_the_constant"),

    # ── the route: entitlement and the cache side ───────────────────────────────────────────────
    ("the paid weekly line is placed on the FREE personalized-league quota gate",
     _ROUTER,
     "    week: int | None = Query(default=None, ge=1, le=22),\n"
     "    user_id: str = Depends(require_fantasy_access),",
     "    week: int | None = Query(default=None, ge=1, le=22),\n"
     "    user_id: str = Depends(require_personalized_league_access),",
     f"{_GUARD}::test_the_route_is_gated_on_fantasy_access_and_not_on_the_free_league_quota"),

    ("the route is renamed to a CHILD of the free weekly reads, inheriting their public cache rule",
     _ROUTER,
     '@router.get("/nfl/weekly/league-board")',
     '@router.get("/nfl/weekly/projections/league-board")',
     f"{_GUARD}::test_the_route_path_is_a_sibling_of_the_free_reads_and_not_a_child"),

    # ── copy ────────────────────────────────────────────────────────────────────────────────────
    ("the scope note issues a start/sit instruction",
     _CONTRACT,
     "The points column is your league's scoring applied to this week's projected stat line.",
     "You should start the players with the highest points column.",
     f"{_GUARD}::test_the_served_contract_makes_no_start_sit_or_opponent_claim"),

    ("the scope note types a measured figure that will drift on the next re-score",
     _CONTRACT,
     "so they will not match exactly.",
     "so they will not match exactly, typically differing by 0.7709 points.",
     f"{_GUARD}::test_the_scope_note_quotes_no_measured_figure"),

    # ── the route, actually invoked ─────────────────────────────────────────────────────────────
    ("the paid weekly line is mounted on the FREE board router with no gate at all",
     _ROUTER,
     _ROUTE_SIGNATURE,
     _resigned("board_router", 'user_id: str = "anon",'),
     f"{_GUARD}::test_an_anonymous_read_is_refused"),

    ("the free personalized-league tier reaches the paid weekly lens (a pricing change)",
     _ROUTER,
     _ROUTE_SIGNATURE,
     _resigned("personal_router", "user_id: str = Depends(require_personalized_league_access),"),
     f"{_GUARD}::test_a_signed_in_account_without_a_membership_is_refused"),

    ("the slate's own absence counts are dropped on the way to the wire",
     _ROUTER,
     "        absences=absences,",
     "        absences=None,",
     f"{_GUARD}::test_a_subscriber_gets_a_scored_roster_with_every_absence_cause_distinguishable"),

    ("the lens contract declares a per-player component field, so the stat line reaches the wire",
     _CONTRACT,
     "    leaguePts: float | None = None\n",
     "    leaguePts: float | None = None\n    rec: float | None = None\n",
     f"{_GUARD}::test_the_response_carries_no_component_line"),

    ("an unpublished week returns an EMPTY roster instead of an honest 404",
     _ROUTER,
     '    payload = _load_json(nfl_weekly.weekly_players_key(season, week))\n'
     '    if payload is None:\n'
     '        raise HTTPException(status_code=404, detail="Weekly projection not found")',
     '    payload = _load_json(nfl_weekly.weekly_players_key(season, week)) or {"players": []}',
     f"{_GUARD}::test_an_unpublished_week_is_a_404_and_not_an_empty_roster"),

    ("a missing week POINTER is guessed at instead of reported",
     _ROUTER,
     '        cur = _load_json(nfl_weekly.weekly_current_key(season))\n'
     '        if cur is None:\n'
     '            raise HTTPException(status_code=404, detail="Weekly projection not found")\n'
     '        week = int(cur["week"])\n\n'
     '    payload = _load_json(nfl_weekly.weekly_players_key(season, week))',
     '        cur = _load_json(nfl_weekly.weekly_current_key(season)) or {"week": 1}\n'
     '        week = int(cur["week"])\n\n'
     '    payload = _load_json(nfl_weekly.weekly_players_key(season, week)) or {"players": []}',
     f"{_GUARD}::test_a_missing_week_pointer_is_a_404_too"),
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
    roots = (_REPO / "app/backend", _TESTS,
             _REPO / "quant_sports_intel_models/football/nfl/fantasy")
    for root in roots:
        for bak in root.rglob(f"*{_BAK_SUFFIX}"):
            target = Path(str(bak)[: -len(_BAK_SUFFIX)])
            assert target.suffix == ".py", (
                f"refusing to restore {bak} onto {target} — that is not a source file")
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
            additive = old in new
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
