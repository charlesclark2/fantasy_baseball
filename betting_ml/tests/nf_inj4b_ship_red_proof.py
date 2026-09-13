"""nf_inj4b_ship_red_proof.py — prove NF-INJ4b-SHIP's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17), and this story is
exactly where that matters: the whole 52-clause NF-C9 suite passed GREEN over a wired discount that
made its copy false, because its boundary clause was keyed on token spellings in a file the wiring
does not touch. Every clause below is therefore broken deliberately and required to go RED.

⭐ **THE HARNESS IS IMPORTED, NOT RE-IMPLEMENTED.** `nf_inj4b_red_proof` already encodes the four
ways a red proof lies — the mutation never LANDS (#682), it lands but does not MOVE the asserted
predicate (#815), it lands on the WRONG symbol (E11.24), and an unresolvable node id scores a
perfect RED forever (NF-INJ4b §3d) — plus the stale-backup sweep that exists because this kind of
harness's worst case is being killed mid-mutation. A second copy would be a second thing to drift
(the one-logical-thing-many-owners shape this repo keeps paying for).

⭐ Two cases replay defects this programme ACTUALLY SHIPPED, rather than hypotheticals:
  · the certified-winner transcription slip (`out ×0.8682` for `×0.8639`), NF-INJ4b §3b(3);
  · the rollback that moves the flag and leaves the copy claiming a discount of exactly zero.

RUN (LAPTOP, ~60 s):
    uv run python betting_ml/tests/nf_inj4b_ship_red_proof.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from betting_ml.tests.nf_inj4b_red_proof import (  # noqa: E402
    _collects,
    _run,
    _sweep_stale_backups,
)

_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"
_POLICY = _FAN / "designation_discount_policy.py"
_SERVING = _FAN / "designation_discount_serving.py"
_CALLER = _FAN / "run_season_projection.py"
_ARTIFACT = _FAN / "served_artifacts/nfl_fantasy_designation_duration_v1.json"
_BATTERY = _FAN / "run_nf_inj4b_ship_battery.py"
_COPY = _REPO / "frontend/lib/fantasy-claim-copy.ts"

_SHIP = _REPO / "betting_ml/tests/test_nf_inj4b_ship_wiring.py"
_INJ4 = _REPO / "betting_ml/tests/test_nf_inj4_designation_duration.py"
_C9 = _REPO / "betting_ml/tests/test_nf_c9_designation_disclosure.py"

#: a guard that must stay GREEN under every mutation — otherwise a RED is not attributable.
NOT_SELECTED = f"{_INJ4}::test_the_two_channels_compose_as_one_cap_and_never_stack"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    ("the production caller is UNPLUGGED (the deploy hold returns, silently)",
     _CALLER,
     "        _DDS.designation_games_callable(int(projection_season), row_log=_desig_log)",
     "        None",
     f"{_INJ4}::test_the_designation_channel_is_wired_AND_REACHED_by_a_production_caller"),

    ("⭐ THE ROLLBACK IS HALF-DONE — the flag goes off, the copy still claims the discount",
     _POLICY,
     "SERVING_ENABLED: bool = True",
     "SERVING_ENABLED: bool = False",
     f"{_SHIP}::test_the_user_facing_copy_and_the_served_policy_cannot_disagree"),

    ("the RETIRED NF-C9 disclaimer comes back (we deny work we have done)",
     _COPY,
     '"Our projected-games figure takes this into account.',
     '"Our projected-games figure does not take this into account.',
     f"{_C9}::test_the_definition_says_out_loud_that_the_projection_DOES_price_it_in"),

    ("⭐ THE CERTIFIED-WINNER TRANSCRIPTION SLIP — the registered arm's ×0.8682 is served",
     _ARTIFACT,
     '"rate_multiplier": 0.8639',
     '"rate_multiplier": 0.8682',
     f"{_SHIP}::test_the_served_constants_are_the_ones_in_the_operator_packet"),

    ("a designation is dropped from the served set (priced at nothing, silently)",
     _ARTIFACT,
     '"served_designations": [\n  "out",',
     '"served_designations": [\n  "doubtful",',
     f"{_C9}::test_the_projection_path_REACHES_the_designation_channel_through_the_certified_model"),

    ("an UNPRICEABLE label stops raising and silently applies no discount",
     _SERVING,
     "    if unpriceable:",
     "    if False and unpriceable:",
     f"{_SHIP}::test_an_unpriceable_label_raises_rather_than_silently_applying_nothing"),

    ("an UNREADABLE feed reports itself as readable (an outage looks like a normal build)",
     _SERVING,
     '        row_log["feed_readable"] = False',
     '        row_log["feed_readable"] = True',
     f"{_SHIP}::test_an_unreadable_feed_degrades_loudly_to_the_pre_ship_board"),

    ("the BASELINE HAZARD is served too (a board-wide level shift on ~2,400 rows)",
     _POLICY,
     '    out = {d: payload["designations"][d] for d in served}',
     '    out = dict(payload["designations"])',
     f"{_SHIP}::test_only_the_three_disclosed_designations_are_priced"),

    ("the season gate goes, so a 2019 backtest is regraded against today's designations",
     _CALLER,
     "        if int(projection_season) == _current_season() else None)",
     "        if True else None)",
     f"{_INJ4}::test_the_designation_discount_is_never_served_for_a_historical_season"),

    ("the serving path reaches for the GITIGNORED fitting frame (NF-INFRA1)",
     _SERVING,
     "    consts = POLICY.load_constants()\n    out = {}",
     "    consts = POLICY.load_constants()\n    _ = DD.fit_predict\n    out = {}",
     f"{_SHIP}::test_the_serving_path_never_refits_the_model"),

    ("the battery RE-DERIVES vor instead of applying the delta (1,113 phantom rank moves)",
     _BATTERY,
     "            g[vor_col] = board[vor_col].astype(float).to_numpy() + delta",
     "            g[vor_col] = g[pts_col].astype(float) - g[\"repl\"].astype(float)",
     f"{_SHIP}::test_an_empty_designation_map_moves_nothing_on_a_board_whose_vor_is_ROUNDED"),
]


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: every guard GREEN on unbroken source (a 'red' means nothing otherwise)")
    for g in (_SHIP, _INJ4, _C9):
        if not _run(str(g)):
            print(f"⛔ BASELINE FAILED in {g.name} — fix the suite before reading any RED below")
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
        bak = path.with_suffix(path.suffix + ".redproof.bak")
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
    ok = all(_run(str(g)) for g in (_SHIP, _INJ4, _C9))
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
