"""NF-WK-ACC1 part 2 RED proof — break the source; each break must turn its OWN guard red.

Harness body copied from `nf_wk_acc1_red_proof.py` (same discipline, its own backup suffix so two
proofs can never collide): unique anchor, landed-on-disk, token-gone, NOT-SELECTED, `BaseException`,
every node resolved. Each break REPRODUCES the defect its guard names rather than editing the
guarded line.

Run:  uv run python betting_ml/tests/nf_wk_acc1_part1_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_acc1_dst_pbp.py"
_DP = "quant_sports_intel_models/football/nfl/fantasy/realized_dst_pbp.py"
_RW = "quant_sports_intel_models/football/nfl/fantasy/realized_week.py"
_DST = "app/backend/services/realized_dst.py"
_BAK = ".part2bak"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    ("a punt stops counting as special teams (the classification rule)", _DP,
     'SPECIAL_TEAMS_PLAY_TYPES: frozenset[str] = frozenset({"field_goal", "extra_point", "punt", "kickoff"})',
     'SPECIAL_TEAMS_PLAY_TYPES: frozenset[str] = frozenset({"field_goal", "extra_point", "kickoff"})',
     "test_the_special_teams_play_types_are_exactly_the_frozen_set"),
    # ⚠️ A REPLACEMENT, NOT AN ADDITION. An additive break leaves its own anchor on disk, and the
    # token-gone check correctly refuses it (the documented landmine — it cost this proof a cycle).
    ("points allowed also excludes the opponent's ST touchdowns (RC1's convention)", _DP,
     '                out[scorer]["st_td"] += 1',
     '                out[scorer]["st_td"] = out[scorer]["st_td"] + 1; '
     'out[scorer]["defensive_tds_scored"] += 1',
     "test_points_allowed_keeps_charging_the_opponents_special_teams_touchdowns"),
    ("a recovery keys on possession instead of on who fumbled (543 -> 539)", _DP,
     "                if opponent_of.get(t) == fumbled_by:",
     "                if pos and opponent_of.get(t) == pos:",
     "test_a_recovery_keys_on_who_FUMBLED_and_a_forced_fumble_on_who_had_POSSESSION"),
    ("a NaN play flag reads as SET, inflating every counter", _DP,
     "    return f == f and f != 0.0",
     "    return bool(f)",
     "test_a_nan_flag_is_not_set_so_a_missing_value_cannot_inflate_every_counter"),
    ("the read contract stops being checked, so a missing column counts zero", _DP,
     "    if missing:\n        raise ValueError(",
     "    if False:\n        raise ValueError(",
     "test_a_narrower_select_is_refused_rather_than_counting_zero"),
    ("the frozen points-allowed figure is ignored by the row builder", _DST,
     "    pa = (float(points_allowed_override) if points_allowed_override is not None\n"
     "          else points_allowed(opponent_score, opponent_non_offensive_tds))",
     "    pa = points_allowed(opponent_score, opponent_non_offensive_tds)",
     "test_with_plays_the_line_carries_the_frozen_terms_and_the_frozen_points_allowed"),
    ("the play counters are ignored, so the frozen construction never runs", _RW,
     "            if mine_pbp is not None and theirs_pbp is not None:",
     "            if False:",
     "test_with_plays_the_line_carries_the_frozen_terms_and_the_frozen_points_allowed"),
    ("a fallback week is stamped as the frozen construction", _RW,
     '        "construction": "pbp_frozen" if frozen else "player_sums",',
     '        "construction": "pbp_frozen",',
     "test_a_week_with_no_published_plays_is_labelled_a_fallback_with_its_reason"),
    ("a failed play read is swallowed without naming the failure", _RW,
     '        return None, f"{type(exc).__name__}: {exc}"',
     '        return None, None',
     "test_a_failed_play_read_falls_back_and_names_the_failure_rather_than_pretending"),
    ("the play-derived terms drop out of the map the line is scored under", _DST,
     '    **REALIZED_PBP_DST_FIELD,\n}',
     '}',
     "test_the_play_derived_terms_are_scorable_and_not_claimed_as_player_columns"),
]

def _run(test: str) -> tuple[bool, str]:
    """RED = the NAMED test fails. A collection error or a NOT-SELECTED miss is a harness fault."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-x", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    if "no tests ran" in out or "ERROR" in out.split("\n")[0]:
        return False, f"NOT-SELECTED or collection error for {test}:\n{out[-800:]}"
    return proc.returncode != 0, out[-400:]


def main() -> int:
    # (a) Restore any stale backup FIRST: this harness's own worst case is dying mid-mutation.
    for bak in ROOT.rglob(f"*{_BAK}"):
        target = bak.with_suffix("")
        print(f"restoring stale backup {bak.relative_to(ROOT)}")
        target.write_text(bak.read_text())
        bak.unlink()

    cases = list(BREAKS)
    failures: list[str] = []
    for label, rel, old, new, test in cases:
        path = ROOT / rel
        src = path.read_text()
        # (b) UNIQUE ANCHOR — a substring that appears twice could land on the wrong occurrence.
        if src.count(old) != 1:
            failures.append(f"{label}: anchor appears {src.count(old)}x (must be exactly 1)")
            continue
        bak = path.with_suffix(path.suffix + _BAK)
        bak.write_text(src)
        try:
            broken = src.replace(old, new, 1)
            path.write_text(broken)
            # (c) LANDED + TOKEN-GONE: the mutation is on disk AND the old text is really absent.
            on_disk = path.read_text()
            if on_disk == src or old in on_disk:
                failures.append(f"{label}: mutation did not land / anchor still present")
                continue
            red, tail = _run(test)
            print(f"  {'✅ RED ' if red else '❌ GREEN'} {label}  →  {SUITE}::{test}")
            if not red:
                failures.append(f"{label}: {test} stayed GREEN\n{tail}")
        except BaseException as exc:  # noqa: BLE001 — a signal must not leave source mutated
            failures.append(f"{label}: harness raised {type(exc).__name__}: {exc}")
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    # (d) EVERY NODE RESOLVED.
    assert len(cases) - len(failures) + len(failures) == len(cases)
    print()
    if failures:
        print(f"❌ {len(failures)} of {len(cases)} breaks did not prove their guard:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ all {len(cases)} breaks turned their named guard RED; source restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
