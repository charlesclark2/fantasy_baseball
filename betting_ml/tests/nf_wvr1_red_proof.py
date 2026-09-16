"""NF-WVR1 RED proof — deliberately break the source and require the guards to FAIL.

A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / INC-39). This harness applies one
break at a time to the real source files, re-runs the suite, and requires the NAMED test to go red.

⚠️ THE HARNESS'S OWN FAILURE MODES, all three of which this repo has paid for and all three of which
are asserted against here before any pytest run:
  * #682 — a mutation that does not LAND reports a false "the guard is vacuous". We diff the file.
  * #815 — a mutation that lands but does not move the ASSERTED predicate is a false green. Where a
           break removes a token, we assert the token is GONE afterwards. ⚠️ THAT TOKEN MUST BE
           SCOPED TO THE MUTATED CALL SITE, not to the file: the first cut checked for
           `_join_key(name,`, which `free_agent_pool` also legitimately calls, so the check fired
           against a break that had landed perfectly. The harness refusing to report a pass it
           could not substantiate is the behaviour working — but the token is the thing to fix.
  * E11.24 prediction_log — an anchor that appears MORE THAN ONCE mutates the wrong symbol and
           reports a false vacuity, which is the dangerous direction because it invites weakening a
           correct guard. Every anchor is asserted UNIQUE in its file first.
Backups are restored at START-UP as well as in `finally`, because this harness's own worst case is
being killed mid-mutation (the E11.26 lesson: a signal skips `finally`).

Run: `uv run python betting_ml/tests/nf_wvr1_red_proof.py`
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "app/backend/services/waiver_pool.py"
SLEEPER = ROOT / "app/backend/services/platform_import/sleeper.py"
ROUTER = ROOT / "app/backend/routers/fantasy.py"
SUITE = "betting_ml/tests/test_nf_wvr1_waiver_pool.py"

#: (label, file, old, new, test that MUST go red, token that must be GONE after the break)
BREAKS = [
    (
        "the flex is summed into every position it accepts (the original defect)",
        POOL,
        "        if len(eligible) == 1:\n            pos = eligible[0]\n            dedicated[pos] = dedicated.get(pos, 0) + count\n        else:\n            flex_slots += count\n            flex_eligible.update(eligible)",
        "        if len(eligible) == 1:\n            pos = eligible[0]\n            dedicated[pos] = dedicated.get(pos, 0) + count\n        else:\n            flex_slots += count\n            flex_eligible.update(eligible)\n            for _p in eligible:\n                dedicated[_p] = dedicated.get(_p, 0) + count",
        "test_a_flex_slot_is_counted_once_not_added_to_every_position_it_accepts",
        None,
    ),
    (
        "the pool subtraction joins on ID instead of name",
        POOL,
        '            keys.add(league_scoring._join_key(name, p.get("position"), p.get("team")))',
        '            keys.add(str(p.get("player_key") or ""))',
        "test_the_subtraction_joins_on_name_not_id_so_a_synthetic_id_row_still_subtracts",
        "keys.add(league_scoring._join_key(",
    ),
    (
        "an un-refreshable platform WITHHOLDS the pool instead of caveating it",
        POOL,
        '    return [] if platform_can_refresh else ["platform_cannot_refresh"]',
        "    return []",
        "test_an_unrefreshable_platform_is_a_CAVEAT_and_never_a_refusal",
        None,
    ),
    (
        "the pool is returned FLAT, permitting a cross-position ranking",
        POOL,
        '    return [{"pos": pos, "players": players} for pos, players in by_pos.items()]',
        '    return [{"pos": pos, "players": players, "rank": i}\n            for i, (pos, players) in enumerate(by_pos.items())]',
        "test_the_pool_is_grouped_by_position_so_it_cannot_express_a_cross_position_ranking",
        None,
    ),
    (
        "the roster refresh stops raising on an empty fetch (returns a partial set)",
        SLEEPER,
        '    teams, note = _fetch_teams(str(league_id))\n    if not teams:',
        '    teams, note = _fetch_teams(str(league_id))\n    if False:',
        "test_the_roster_refresh_raises_rather_than_returning_a_partial_set",
        None,
    ),
    (
        "the roster refresh carries player_key through (inviting the id join back)",
        SLEEPER,
        '                {"name": p.name, "position": p.position, "team": p.team} for p in t.players',
        '                {"name": p.name, "position": p.position, "team": p.team,\n                 "player_key": p.player_key} for p in t.players',
        "test_the_roster_refresh_returns_the_stored_record_shape_and_drops_player_key",
        None,
    ),
    (
        "the refresh OR-s the stored truncation flag (a league ever truncated is refused forever)",
        ROUTER,
        '                "league_rosters_truncated": bool(truncated),',
        '                "league_rosters_truncated": bool(record.get("league_rosters_truncated") or truncated),',
        "test_a_successful_refresh_clears_a_stale_truncation_flag_rather_than_carrying_it_forever",
        None,
    ),
]


def run_suite(test: str | None = None) -> tuple[bool, str]:
    target = f"{SUITE}::{test}" if test else SUITE
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-500:]


def main() -> int:
    originals = {p: p.read_text() for p in (POOL, SLEEPER, ROUTER)}
    # Restore at START-UP too: this harness's worst case is being killed mid-mutation.
    for p, text in originals.items():
        if p.read_text() != text:
            p.write_text(text)

    ok, out = run_suite()
    if not ok:
        print("BASELINE IS RED — fix the suite before trusting any RED proof.\n" + out)
        return 1
    print(f"baseline: GREEN ({len(BREAKS)} breaks to apply)\n")

    failures = []
    try:
        for label, path, old, new, test, gone in BREAKS:
            src = originals[path]
            count = src.count(old)
            if count != 1:
                failures.append(f"ANCHOR NOT UNIQUE ({count}x) for: {label}")
                print(f"  ✗ {label}\n      anchor appears {count}x — would mutate the wrong symbol")
                continue
            path.write_text(src.replace(old, new, 1))
            after = path.read_text()
            if after == src:                                   # #682
                failures.append(f"MUTATION DID NOT LAND: {label}")
                print(f"  ✗ {label}\n      the break did not land on disk")
                path.write_text(src)
                continue
            if gone is not None and gone in after:             # #815
                failures.append(f"MUTATION LANDED BUT TOKEN SURVIVES: {label}")
                print(f"  ✗ {label}\n      {gone!r} still present after the break")
                path.write_text(src)
                continue
            passed, out = run_suite(test)
            path.write_text(src)
            if passed:
                failures.append(f"GUARD IS VACUOUS: {label}  ({test})")
                print(f"  ✗ {label}\n      {test} PASSED on broken source")
            else:
                print(f"  ✓ {label}\n      {test} went RED")
    finally:
        for p, text in originals.items():
            p.write_text(text)

    ok, _ = run_suite()
    print(f"\nrestored source: {'GREEN' if ok else 'RED — SOURCE NOT RESTORED'}")
    if failures or not ok:
        print("\nFAILURES:\n  " + "\n  ".join(failures or ["source not restored"]))
        return 1
    print(f"\nALL {len(BREAKS)} BREAKS WENT RED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
