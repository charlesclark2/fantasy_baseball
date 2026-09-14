"""nf_inc_0914_followups_red_proof.py — prove the NF-INC-0914 follow-up guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). These two fixes are
both one-liners, which is exactly the shape that ships unguarded — and the defect they repair was
itself a one-character difference (`=` where `+=` belonged) that survived every green suite and
disabled the only automated per-row check the designation discount has.

⭐ THE HARNESS IS IMPORTED, NOT RE-IMPLEMENTED — `nf_inj4b_red_proof` encodes the four ways a red
proof lies (the mutation never LANDS #682; it lands but does not MOVE the asserted predicate #815;
it lands on the WRONG symbol E11.24; an unresolvable node id scores a perfect RED forever), plus the
stale-backup sweep that exists because this harness's worst case is being killed mid-edit.

⚠️ TWO-SIDED BY CONSTRUCTION. Cases 1-2 restore the OUTAGE (the overwrite verbatim; the rate cap
turned back into a ceiling). Cases 3-5 break the fix toward the OPPOSITE failure — a seasonal gate
that suppresses too much: silencing the year-round model input, dropping the measurement along with
the page, or inventing a second seasonal boundary instead of delegating to the cadence owner. A
suppression that can only ever go quieter is the muted monitor it was written to prevent.

RUN (LAPTOP, ~20 s):
    uv run python betting_ml/tests/nf_inc_0914_followups_red_proof.py
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

_SERVING = _REPO / "quant_sports_intel_models/football/nfl/fantasy/designation_discount_serving.py"
_CAP = _REPO / "quant_sports_intel_models/football/nfl/fantasy/nf_inj4_designation_duration.py"
_MON = _REPO / "betting_ml/monitoring/nfl_board_freshness.py"
_GUARD = _REPO / "betting_ml/tests/test_nf_inc_0914_followups.py"

_ACC = f"{_GUARD}::test_the_designated_count_accumulates_across_legs_like_the_moved_count"
_RATE = (f"{_GUARD}::"
         "test_a_priceable_designated_row_always_moves_so_designated_minus_moved_is_an_honest_miss")
_TWO_SIDED = f"{_GUARD}::test_the_same_board_pages_in_season_and_goes_quiet_after_it_while_still_measuring"
_OWNER = f"{_GUARD}::test_the_seasonal_gate_reuses_the_cadence_owner_rather_than_a_second_boundary"
_WHY = f"{_GUARD}::test_the_ecr_reason_names_the_ordering_feature_not_a_display_column"

#: must stay GREEN under every mutation below — in ANOTHER file, over the served constants, so it
#: cannot share the fate of a break in the monitor or the serving module.
NOT_SELECTED = (f"{_REPO}/betting_ml/tests/test_nf_inj4b_ship_wiring.py"
                "::test_the_served_arm_is_the_one_the_decisive_run_certified")

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── toward the OUTAGE ─────────────────────────────────────────────────────────────────────
    ("THE OVERWRITE, VERBATIM — the designated count stops accumulating (2026-09-14, 86 beside 0)",
     _SERVING,
     '            row_log["designated_rows_on_frame"] = (\n'
     '                int(row_log.get("designated_rows_on_frame", 0)) + designated)',
     '            row_log["designated_rows_on_frame"] = designated',
     _ACC),

    ("the rate cap becomes a CEILING — `designated - moved` silently stops being a miss count",
     _CAP,
     "    target = (float(season_games) - float(expected_missed)) / float(season_games)\n"
     "    return float(min(float(current_games), float(current_games) * target))",
     "    return float(min(float(current_games), float(season_games) - float(expected_missed)))",
     _RATE),

    # ── toward the OPPOSITE failure: a gate that suppresses too much ──────────────────────────
    ("the seasonal gate silences the YEAR-ROUND model input too (depth chart goes quiet)",
     _MON,
     '        max_lag_hours=72.0,\n'
     '        why=("the most-decayed model INPUT on the board',
     '        max_lag_hours=72.0, draft_season_only=True,\n'
     '        why=("the most-decayed model INPUT on the board',
     _TWO_SIDED),

    ("withholding the PAGE becomes withholding the MEASUREMENT — the lag stops being recorded",
     _MON,
     "        lag = round((now - parsed).total_seconds() / 3600.0, 2)\n        stamps[stamp.name] = lag",
     "        lag = round((now - parsed).total_seconds() / 3600.0, 2)\n        stamps[stamp.name] = None",
     _TWO_SIDED),

    ("the seasonal boundary is re-spelled by hand instead of delegating to the cadence owner",
     _MON,
     "    return any(is_draft_season(today - timedelta(days=d))\n"
     "               for d in range(CADENCE_BOUNDARY_LOOKBACK_DAYS + 1))",
     "    return today.month == 8 or (today.month == 9 and today.day <= 17)",
     _OWNER),

    ("the ECR reason reverts to calling an ordering feature a display column",
     _MON,
     'why=("ECR-PRIMARY in the model\'s `market_rank` ordering feature (`nf1_3_model`, consumed "\n'
     '             "by `nf1_5_model`) — a stale ECR shifts within-position ORDERING, it is not merely a "\n'
     '             "reference column beside the projection"),',
     'why="the expert-consensus reference column shown beside every projection",',
     _WHY),
]


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: the guard must be GREEN on unbroken source")
    if not _run(str(_GUARD)) or not _run(NOT_SELECTED):
        print("⛔ BASELINE FAILED — fix the suite before reading any RED below")
        return 1
    missing = sorted({c[4] for c in CASES if not _collects(c[4])})
    if missing:
        print(f"⛔ BASELINE FAILED — these node ids collect NOTHING: {missing}")
        return 1
    print(f"   ✅ baseline green, all {len({c[4] for c in CASES})} named guards resolve\n")

    red = 0
    for label, path, old, new, nodeid in CASES:
        src = path.read_text()
        n = src.count(old)                       # ⛔ #815 + E11.24: the anchor must be UNIQUE
        if n != 1:
            print(f"⛔ {label}: anchor occurs {n}× in {path.name} — NOT UNIQUE, refusing to mutate")
            continue
        bak = path.with_suffix(path.suffix + ".redproof.bak")
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            after = path.read_text()
            additive = old in new
            assert after != src, f"{label}: mutation did not land"       # ⛔ #682
            if additive:
                assert new not in src, f"{label}: the additive break was ALREADY present"
                assert new in after, f"{label}: the additive break is not in the file"
            else:
                assert old not in after, f"{label}: the old token survives"   # ⛔ #815

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
    ok = _run(str(_GUARD)) and _run(NOT_SELECTED)
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
