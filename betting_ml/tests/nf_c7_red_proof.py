"""RED proof for the NF-C7 guards — `uv run python betting_ml/tests/nf_c7_red_proof.py`.

Every claim in `test_nf_c7_pick_recommendation.py` is proved by RE-INTRODUCING the defect it exists
to catch and requiring the named test to go RED. Same harness contract as
`nf_c_lda_1_roster_red_proof.py`:

  * the mutation is applied to the SOURCE FILE and asserted to have LANDED (E11.24 #682);
  * where a guard asserts on a TOKEN, that token is asserted GONE afterwards (E11.24 #815);
  * ⭐ the anchor is asserted UNIQUE in the file before use — `draft.py` and `draft-optimizer.ts`
    are deliberate line-by-line mirrors, so a `replace(old, new, 1)` can land on the WRONG
    occurrence and report a false "the guard is vacuous" (E11.24 prediction_log);
  * pytest runs in a SUBPROCESS so `pytest.raises`' `Failed` (a `BaseException`) cannot leak past a
    narrow `except` (NF-W6c);
  * ⚠️ ONLY exit code 1 (tests FAILED) counts as RED — 2/3/4/5 is a BROKEN HARNESS (NF-INFRA1);
  * the file is restored in a `finally`.

⚠️ Every break here was written against a defect that ACTUALLY HAPPENED during NF-C7 — the seat
over-count (George Kittle at 248 points of bench cover), the missing availability discount (Bailey
Zappe at 394), the direct-integration placement regression (bench depth over an empty QB1 in 8 of 23
states), and the weighted depth bonus that was measured inert. None is hypothetical.

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~2 min — the two anchor clauses
draft twelve rosters each.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_c7_pick_recommendation.py"
_DRAFT = "quant_sports_intel_models/fantasy_engine/draft.py"

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS = [
    # ── the LOAD-BEARING guard: a preference may never produce an illegal roster ─────────────────
    ("depth target: let it reach `must_fill`, so a preference can strand a starter slot", _DRAFT,
     "        must_fill = must_fill_now and level > 0",
     "        must_fill = must_fill_now and (level > 0 or depth_short > 0)",
     # ⚠️ no `gone` token: the phrase `must_fill = must_fill_now and level > 0` is also QUOTED in a
     # comment a few lines up, so it survives the mutation legitimately (E11.24 #815 firing on a
     # badly-chosen token rather than on a bad mutation).
     "starve_the_reserve", None),
    ("depth target: let it reach the K/DST DEFERRAL, so a kicker target surfaces a kicker", _DRAFT,
     '        deferred = bool(row.get("low_pred"))',
     '        deferred = bool(row.get("low_pred")) and depth_short <= 0',
     "kicker_depth_target", '        deferred = bool(row.get("low_pred"))\n'),
    ("depth target: apply it at EVERY need level, not only on the bench", _DRAFT,
     "        if level == 0 and depth_targets:",
     "        if depth_targets:",
     "never_lifts_a_bench_pick or starve_the_reserve or never_recorded_against_an_open",
     "        if level == 0 and depth_targets:"),
    ("depth target: promote the whole bench cohort above the need-fillers", _DRAFT,
     "    recs.sort(key=lambda r: (not r.must_fill, r.deferred, -r.order_value,\n"
     "                             r.depth_short <= 0, -r.score, r.player_id))",
     "    recs.sort(key=lambda r: (not r.must_fill, r.deferred, r.depth_short <= 0,\n"
     "                             -r.order_value, -r.score, r.player_id))",
     "never_lifts_a_bench_pick", None),

    # ── the depth target must ACT (an inactive mechanism is not a passing one — NF-D20) ──────────
    ("depth target: ignore it entirely (the feature ships inert)", _DRAFT,
     "            depth_short = max(0, int(depth_targets.get(pos, 0)) - len(my_rows_by_pos.get(pos, ())))",
     "            depth_short = 0",
     "changes_which_bench_player", "int(depth_targets.get(pos, 0))"),
    ("depth target: drop the TIER from the bench re-rank (the measured-inert bonus version)", _DRAFT,
     "        ranked = sorted(cohort,\n"
     "                        key=lambda r: (r.depth_short <= 0, -r.score, -r.order_value, r.player_id))",
     "        ranked = sorted(cohort,\n"
     "                        key=lambda r: (-r.score, -r.order_value, r.player_id))",
     # ⚠️ no `gone` token: the same key chain appears in the FINAL sort's tie-break below.
     "changes_which_bench_player", None),
    ("depth target: pay it even when already MET (a gate that always fires)", _DRAFT,
     "            depth_short = max(0, int(depth_targets.get(pos, 0)) - len(my_rows_by_pos.get(pos, ())))",
     "            depth_short = 1 if int(depth_targets.get(pos, 0)) > 0 else 0",
     "met_depth_target", "- len(my_rows_by_pos.get(pos, ()))"),

    # ── the insurance formula's own two corrections ──────────────────────────────────────────────
    ("seats: go back to the roster's CAPACITY (Kittle at 248 points of bench cover)", _DRAFT,
     "            seats_for[pos] = int(open_slots.seated.get(pos, 0))",
     "            seats_for[pos] = starter_seats_for(req, pos)",
     "whole_season or bench_mix", "open_slots.seated.get(pos, 0)"),
    ("rate: go back to `pts / games` (Stick at a 40.3/game 'rate' on 1.9 projected games)", _DRAFT,
     '    return _fnum(row.get("league_points")) / SEASON_GAMES',
     '    _g = _fnum(row.get("games"))\n'
     '    return (_fnum(row.get("league_points")) / _g) if _g > 0 else 0.0',
     "almost_no_games or whole_season or bench_mix", "league_points\")) / SEASON_GAMES"),
    ("availability: stop skipping the candidate's OWN bye week", _DRAFT,
     "        if cand_bye == week:\n            continue",
     "        if False:\n            continue",
     "sharing_his_starters_bye", "if cand_bye == week:"),
    ("displacement: always take the bench branch (the rule the study scored)", _DRAFT,
     "    if seats > 0 and len(my_rates_desc) >= seats:",
     "    if False:",
     "displaces_the_weakest_seat_holder or whole_season or bench_mix",
     "if seats > 0 and len(my_rates_desc) >= seats:"),
    ("insurance: floor the PRODUCT instead of the UPGRADE (a negative bench value)", _DRAFT,
     "    upgrade = max(0.0, rate - displaced_rate(rates_desc, seats, rate))\n"
     "    if upgrade <= 0.0:\n        return 0.0",
     "    upgrade = rate - displaced_rate(rates_desc, seats, rate)\n"
     "    if False:\n        return 0.0",
     "worse_than_the_cover", None),

    # ── the PLACEMENT rule (the regression the direct integration produced) ──────────────────────
    ("placement: put the insurance value straight into the sort (the measured regression)", _DRAFT,
     "            order_value=_js_round1(\n"
     "                bench_order_value(vor) - bye_pen if level == 0 else score\n"
     "            ),",
     "            order_value=_js_round1(score),",
     "outrank_an_open_starter_slot", "bench_order_value(vor) - bye_pen"),
    ("placement: keep the damping but ALSO order the bench by it (insurance stops deciding)", _DRAFT,
     "        ranked = sorted(cohort,\n"
     "                        key=lambda r: (r.depth_short <= 0, -r.score, -r.order_value, r.player_id))",
     "        ranked = sorted(cohort,\n"
     "                        key=lambda r: (r.depth_short <= 0, -r.order_value, r.player_id))",
     "ordered_by_insurance or bench_mix", None),
    ("placement: drop the total order, so a tie falls back to board order", _DRAFT,
     "    recs.sort(key=lambda r: (not r.must_fill, r.deferred, -r.order_value,\n"
     "                             r.depth_short <= 0, -r.score, r.player_id))",
     "    recs.sort(key=lambda r: (not r.must_fill, r.deferred, -r.order_value))",
     "ordered_by_insurance", None),

    # ── the whole rule: revert to the retired comparator ─────────────────────────────────────────
    ("bench value: revert to the retired damped VOR (the rule NF-C7 replaced)", _DRAFT,
     "            return bench_value(row, p) if bench_value is not None else insurance_of(row, p)[0]",
     "            return bench_value(row, p) if bench_value is not None else bench_order_value(_fnum(row.get('vor')))",
     "bench_mix or ordered_by_insurance", "insurance_of(row, p)[0]"),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        occurrences = original.count(old)
        if occurrences == 0:
            print(f"{'BROKEN ❌ (anchor not found)':34} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        if occurrences > 1:
            print(f"{'BROKEN ❌ (anchor not unique)':34} {name} -> {occurrences}x in {rel}")
            failures.append(f"{name}: anchor appears {occurrences}x in {rel}")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name
        if gone is not None and gone in mutated:
            print(f"{'BROKEN ❌ (token survives)':34} {name} -> {gone!r} still present")
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
            print(f"{verdict:34} {name}\n{'':34} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} deliberate breaks were caught ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
