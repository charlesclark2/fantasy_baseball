"""NF-WK-RC1 RED proof — break the source deliberately; each break must turn its OWN guard red.

⛔ A guard trusted because it passed once is not a guard. This harness encodes every way this repo
has watched a RED proof lie:

  • #682 — the mutation must be proven to LAND ON DISK, or "the break no-opped" and "the guard
    caught it" are indistinguishable, and the FALSE-VACUITY reading is the dangerous one.
  • #815 — the token must be proven GONE afterwards; a mutation that writes without moving the
    asserted predicate comes back green.
  • the 3rd way — the anchor must be UNIQUE in the file, or `replace(old, new, 1)` lands on the
    WRONG symbol and reports a false vacuity against a guard that is fine.
  • NF-W6c — `pytest.raises` failures are `BaseException`, so a bare `except Exception` lets a
    deliberate break sail straight through.
  • NOT-SELECTED — a break must turn red the guard it NAMES, not merely "something".

Run:  uv run python betting_ml/tests/nf_wk_rc1_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_rc1_weekly_recap.py"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    ("dst seat serves our scorer instead of the league's figure",
     "app/backend/services/weekly_recap.py",
     '''                pts = seat.get("platformPts")''',
     '''                pts = (hit or {}).get("leaguePts")''',
     "test_the_dst_seat_carries_the_leagues_own_figure_not_ours"),

    ("matchup decided on OUR itemisation",
     "app/backend/services/weekly_recap.py",
     '''        a_t = side[0]["standingsTotal"] if side else None
        b_t = side[1]["standingsTotal"] if len(side) == 2 else None''',
     '''        a_t = side[0]["itemisedTotal"] if side else None
        b_t = side[1]["itemisedTotal"] if len(side) == 2 else None''',
     "test_the_matchup_result_is_decided_on_the_leagues_total_never_our_sum"),

    ("the gap note goes generic",
     "app/backend/services/weekly_recap.py",
     '''    return (f"This league also scores {subject}, which the breakdown below doesn't itemize yet — "
            "so the slot points don't add up to the total above.")''',
     '''    return "Totals may differ."''',
     "test_the_gap_note_names_the_leagues_own_captured_terms_and_is_not_generic"),

    # ⚠️ THE BREAK MUST REMOVE THE CONSTRUCTION OVERRIDE, not the None-guard. A first cut broke
    # `if dst_constructed is None: continue` -> `if False: continue`, which changes NOTHING when a
    # construction IS supplied — so it reported the guard vacuous when the guard was fine and the
    # BREAK was inert. That is the "it landed but did not move the asserted predicate" shape (#815)
    # arriving in the harness rather than the suite.
    ("the dst comparison reverts to the SERVED value (the vacuity this guard exists for)",
     "app/backend/services/weekly_recap.py",
     '''                rec["ours"] = float(dst_constructed[key])
                rec["delta"] = rec["ours"] - float(theirs)''',
     '''                pass''',
     "test_the_dst_comparison_is_not_vacuous_against_the_served_value"),

    ("a seat is allowed to alert",
     "app/backend/services/weekly_recap.py",
     '''            "mayAlert": False,
            "explainedBy": sorted(EXPLAINABLE_CAPTURED_TERMS),''',
     '''            "mayAlert": True,
            "explainedBy": sorted(EXPLAINABLE_CAPTURED_TERMS),''',
     "test_no_seat_may_alert"),

    ("completeness becomes 'any game played' (a clock-rule stand-in)",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '''    return "final" if realized_games >= scheduled_games else "partial"''',
     '''    return "final"''',
     "test_a_postponed_game_keeps_a_week_partial"),

    ("points allowed reverts to the opponent's score",
     "app/backend/services/realized_dst.py",
     '''    return max(0.0, float(opponent_score) - NON_OFFENSIVE_TD_POINTS * tds)''',
     '''    return max(0.0, float(opponent_score))''',
     "test_points_allowed_excludes_the_opponents_non_offensive_touchdowns"),

    ("the artifact stops carrying the explanation columns",
     "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
     '''        | set(W.EXPLANATION_COLUMNS)''',
     '''        | set()''',
     "test_the_explanation_columns_are_actually_carried_by_the_published_artifact"),
]


def _run(selector: str) -> bool:
    """True when pytest passes. `-p no:cacheprovider` so a break cannot poison a later run."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", selector],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    # ⭐ RESTORE ANY STALE BACKUP FIRST. This harness's own worst case is being killed mid-mutation,
    # which would leave broken source on disk looking like a real defect.
    for bak in ROOT.glob("**/*.rc1bak"):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        print(f"  restored stale backup for {target.relative_to(ROOT)}")

    if not _run(SUITE):
        print("BASELINE FAILED — the suite must be green before any break is meaningful")
        return 1
    print(f"baseline: {SUITE} green\n")

    failures = []
    for label, rel, old, new, must_fail in BREAKS:
        path = ROOT / rel
        src = path.read_text()

        # (a) the anchor must be UNIQUE — otherwise the break lands on the wrong symbol
        if src.count(old) != 1:
            failures.append(f"{label}: anchor appears {src.count(old)}x in {rel} (must be exactly 1)")
            continue
        # (b) the guard must be SELECTED by the suite
        broken = src.replace(old, new, 1)
        bak = path.with_suffix(path.suffix + ".rc1bak")
        bak.write_text(src)
        path.write_text(broken)
        try:
            # (c) the mutation LANDED, and (d) the old token is GONE
            on_disk = path.read_text()
            if on_disk == src:
                failures.append(f"{label}: mutation did not land on disk")
                continue
            if old in on_disk:
                failures.append(f"{label}: the old token survives — the break may not bite")
                continue
            named_red = not _run(f"{SUITE}::{must_fail}")
            suite_red = not _run(SUITE)
            if not named_red:
                failures.append(f"{label}: {must_fail} stayed GREEN on broken source (VACUOUS)")
            elif not suite_red:
                failures.append(f"{label}: the named test went red but the suite did not — "
                                "it is not selected by a plain run")
            else:
                print(f"  ✅ RED  {label}  →  {must_fail}")
        except BaseException as exc:   # noqa: BLE001 — pytest's Failed is a BaseException (NF-W6c)
            failures.append(f"{label}: harness error {type(exc).__name__}: {exc}")
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    # (e) EVERY NODE RESOLVED — a break that neither proved its guard nor recorded a failure would
    # vanish silently, which is the one outcome this harness must not permit.
    proved = len(BREAKS) - len(failures)
    assert proved + len(failures) == len(BREAKS), "a break resolved to neither RED nor a failure"
    print()
    if failures:
        print(f"❌ {len(failures)} of {len(BREAKS)} breaks did not prove their guard:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ all {len(BREAKS)} breaks turned their named guard RED; source restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
