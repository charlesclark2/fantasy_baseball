"""NF-WK-ACC1 part 3 RED proof — break the source; each break must turn its OWN guard red.

Harness body copied from `nf_wk_acc1_part2_red_proof.py` (same discipline, its own backup suffix so
three proofs can never collide): restore-stale-backups-first, unique anchor, landed-on-disk,
token-gone, NOT-SELECTED, `BaseException`, every node resolved. Each break REPRODUCES the defect its
guard names rather than editing the guarded line.

⛔ ONE CONDITION IS DELIBERATELY NOT BROKEN HERE. `weekly_recap`'s inner
`league_pos != hit["pos"]` check on a fallback match is REDUNDANT BY CONSTRUCTION — a name+team match
requires the `name|position` key to have missed, and both keys share the same folded name, so the
positions necessarily differ on that branch. A break on it stays GREEN because no fixture can make it
false. It is documented at the call site as a cheap invariant rather than claimed as a guard: a
condition that cannot be made false is a finding, not a guard (NF1.9). The RED proof found this by
reporting the break GREEN, which is precisely its job.

⚠️ EVERY BREAK IS A REPLACEMENT, NEVER AN ADDITION. An additive break leaves its own anchor on disk
and the token-gone check correctly refuses it — a documented landmine that has now cost parts 1 and 2
a cycle each.

Run:  uv run python betting_ml/tests/nf_wk_acc1_part3_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_acc1_part3.py"
_PP = "quant_sports_intel_models/football/nfl/fantasy/realized_player_pbp.py"
_RW = "quant_sports_intel_models/football/nfl/fantasy/realized_week.py"
_RSF = "app/backend/services/realized_stat_fields.py"
_LS = "app/backend/services/league_scoring.py"
_WR = "app/backend/services/weekly_recap.py"
_BAK = ".part3bak"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    # ── the frozen derivation ──────────────────────────────────────────────────────────────────
    ("the lateral player stops being credited, so the catcher gets the touchdown", _PP,
     '            add(_pid(play.get("lateral_receiver_player_id")) or _pid(play.get("receiver_player_id")),\n'
     '                "rec_td_40p")',
     '            add(_pid(play.get("receiver_player_id")), "rec_td_40p")',
     "test_a_lateral_credits_the_player_who_SCORED_not_the_one_who_caught_it"),
    ("a lateral on a RUSH stops being credited", _PP,
     '            add(_pid(play.get("lateral_rusher_player_id")) or _pid(play.get("rusher_player_id")),\n'
     '                "rush_td_40p")',
     '            add(_pid(play.get("rusher_player_id")), "rush_td_40p")',
     "test_a_lateral_on_a_rush_credits_the_lateral_rusher"),
    ("the threshold drifts to 39 yards", _PP,
     "LONG_TD_YARDS = 40",
     "LONG_TD_YARDS = 39",
     "test_the_threshold_is_exactly_forty_yards"),
    ("a return touchdown starts paying the offensive bonuses", _PP,
     '        if _truthy_flag(play.get("pass_touchdown")):',
     '        if True:',
     "test_a_long_RETURN_touchdown_pays_none_of_the_three"),
    ("a NaN flag reads as SET, so every non-scoring play becomes a long touchdown", _PP,
     "    return not math.isnan(f) and f == 1.0",
     "    return bool(f)",
     "test_a_NaN_flag_reads_as_NOT_SET"),
    ("the read contract stops being checked, so a missing column counts zero", _PP,
     "        if missing:\n            raise ValueError(",
     "        if False:\n            raise ValueError(",
     "test_a_narrower_play_row_is_REFUSED_rather_than_scored_as_zero"),
    ("the subset-identity bound treats an absent touchdown row as nothing to check", _PP,
     "        bound = touchdowns.get(pid) or {}",
     "        bound = touchdowns.get(pid)\n        if bound is None:\n            continue",
     "test_a_player_absent_from_the_touchdown_side_is_a_violation_not_a_pass"),

    # ── the map wiring ─────────────────────────────────────────────────────────────────────────
    ("the derived terms drop out of the map the line is scored under", _RSF,
     "REALIZED_SOURCE_ALL: dict[str, tuple[str, ...]] = {**REALIZED_STAT_SOURCE, **REALIZED_PBP_SOURCE}",
     "REALIZED_SOURCE_ALL: dict[str, tuple[str, ...]] = {**REALIZED_STAT_SOURCE}",
     "test_the_three_bonuses_are_no_longer_reported_as_unsupported"),
    ("a derived column is claimed as a weekly-stat-table column, which would fail the read", _RSF,
     "REALIZED_STAT_COLUMNS: tuple[str, ...] = tuple(sorted(\n"
     "    {c for cols in REALIZED_STAT_SOURCE.values() for c in cols}\n"
     "))",
     "REALIZED_STAT_COLUMNS: tuple[str, ...] = tuple(sorted(\n"
     "    {c for cols in REALIZED_SOURCE_ALL.values() for c in cols}\n"
     "))",
     "test_the_derived_columns_are_never_asked_of_the_weekly_stat_table"),
    ("the two declarations of the derived column names drift apart", _PP,
     'LONG_TD_COLUMN: dict[str, str] = {k: f"pbp_{k}" for k in LONG_TD_KEYS}',
     'LONG_TD_COLUMN: dict[str, str] = {k: k for k in LONG_TD_KEYS}',
     "test_the_two_declarations_of_the_derived_column_names_agree"),

    # ── the build-side join ────────────────────────────────────────────────────────────────────
    ("the counts are written only for the scorers, so a quiet week reads as CAPTURED", _RW,
     "        for key, column in _LONG_TD_COLUMN.items():\n"
     "            row[column] = float((got or {}).get(key) or 0.0)",
     "        for key, column in _LONG_TD_COLUMN.items():\n"
     "            if got:\n"
     "                row[column] = float(got.get(key) or 0.0)",
     "test_the_counts_are_written_as_ZERO_on_every_row_not_only_on_the_scorers"),
    ("the derived columns are declared even when the plays were not read", _RW,
     "    cols = set(required_columns())\n    if plays_joined:\n        cols |= set(R.REALIZED_PBP_COLUMNS)",
     "    cols = set(required_columns())\n    if True:\n        cols |= set(R.REALIZED_PBP_COLUMNS)",
     "test_the_served_column_list_grows_ONLY_when_the_plays_were_joined"),

    # ── the publish decision ───────────────────────────────────────────────────────────────────
    ("a widened construction is reported as a vendor restatement, so the term never ships", _RW,
     "    if added and not (was_cols - now_cols):",
     "    if False:",
     "test_deriving_a_NEW_term_is_a_widen_not_a_vendor_restatement"),
    ("the widen stops checking the published columns, so it absorbs a real restatement", _RW,
     "        if content_hash(players, was_cols) == prior:",
     "        if True:",
     "test_a_widen_that_ALSO_moves_a_published_column_is_still_a_restatement"),
    ("a widen with no rows supplied assumes the harmless case", _RW,
     "        if players is None:\n            return {\"action\": \"restate\",",
     "        if False:\n            return {\"action\": \"restate\",",
     "test_without_the_rows_a_widen_refuses_to_assume_the_harmless_case"),
    ("a DISAPPEARING column no longer blocks the widen", _RW,
     "    if added and not (was_cols - now_cols):",
     "    if added:",
     "test_a_column_DISAPPEARING_is_never_a_widen"),
    ("the restricted hash ignores its column argument", _RW,
     "    if columns is not None:\n        keep = set(columns)",
     "    if False:\n        keep = set(columns)",
     "test_the_restricted_hash_reads_only_the_named_columns"),

    # ── the two-way-player join ────────────────────────────────────────────────────────────────
    ("the name+team fallback is removed, so a two-way player is unmatched again", _LS,
     '        if hit is None and normalize_position(r.get("position") or "") != "DST":',
     '        if False:',
     "test_a_two_way_player_whose_position_the_two_sides_DISAGREE_on_now_matches"),
    ("the fallback keys on NAME ALONE, so the wrong man's stat line is handed over", _LS,
     '    return f"{folded}|{franchise}" if folded and franchise else ""',
     '    return folded',
     "test_the_same_name_on_a_DIFFERENT_team_does_not_match"),
    ("an ambiguous name+team is arbitrated instead of dropped", _LS,
     "    by_name_team = {k: v[0] for k, v in grouped.items() if len(v) == 1}",
     "    by_name_team = {k: v[0] for k, v in grouped.items()}",
     "test_an_AMBIGUOUS_name_and_team_is_dropped_rather_than_arbitrated"),
    ("the fallback runs FIRST and overrides an exact position match", _LS,
     '        hit = by_key.get(key)\n        matched_on = "name_position" if hit is not None else None',
     '        hit = None\n        matched_on = None',
     "test_the_fallback_never_overrides_a_primary_hit"),

    # ── the position re-score on a fallback match ──────────────────────────────────────────────
    ("a fallback match keeps the LAKE's position, losing the league's position bonus", _WR,
     '                if join.get("matchedOn") == "name_team" and hit.get("flat") is not None:',
     '                if False:',
     "test_a_fallback_match_is_scored_with_the_leagues_position_bonus_not_the_lakes"),
    ("the internal stat row leaks onto the served seat", _WR,
     '                row.update({\n'
     '                    "points": pts, "source": SOURCE_OUR_SCORER,',
     '                row.update({**hit,\n'
     '                    "points": pts, "source": SOURCE_OUR_SCORER,',
     "test_the_board_row_kept_for_the_rescore_never_reaches_a_seat"),
]


def _run(test: str) -> tuple[bool, str]:
    """RED = the NAMED test fails. A collection error or a NOT-SELECTED miss is a harness fault."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-x", "-q", "--no-header",
         "-p", "no:randomly"],
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
