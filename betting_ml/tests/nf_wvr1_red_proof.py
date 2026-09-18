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
FACTS = ROOT / "app/backend/services/waiver_facts.py"
SUITE = "betting_ml/tests/test_nf_wvr1_waiver_pool.py"
FACT_SUITE = "betting_ml/tests/test_nf_wvr1_fact_columns.py"


def F(test: str) -> str:
    """A fact-column test, as a full node id (the harness defaults to SUITE otherwise)."""
    return f"{FACT_SUITE}::{test}"

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
        # ⚠️ RE-ANCHORED, not deleted (MH2.7): ⑰ moved the key-building into `_rostered_entries` so
        # the subtraction and its own detector cannot read the roster two different ways. The
        # PROPERTY under test is unchanged — the join is on NAME, never an id.
        "the pool subtraction joins on ID instead of name",
        POOL,
        '                "key": league_scoring._join_key(name, p.get("position"), p.get("team")),',
        '                "key": str(p.get("player_key") or ""),',
        "test_the_subtraction_joins_on_name_not_id_so_a_synthetic_id_row_still_subtracts",
        '"key": league_scoring._join_key(',
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
    # ── IR / taxi + own-roster refresh (operator 2026-09-17) ─────────────────────────────────
    (
        "Sleeper's reserve/taxi lists are ignored again (IR filed as bench)",
        SLEEPER,
        "    if pid in reserve:\n        return \"ir\"\n    if pid in taxi:\n        return \"taxi\"\n",
        "",
        "test_sleeper_files_reserve_and_taxi_ids_by_their_slot_not_as_bench",
        "if pid in reserve",
    ),
    (
        "an IR player is counted as depth",
        POOL,
        '        if imported.get("slot") in ("ir", "taxi"):',
        '        if False:',
        "test_an_ir_player_is_not_counted_as_depth",
        'imported.get("slot") in ("ir", "taxi")',
    ),
    (
        "the waiver refresh no longer rewrites the caller's own roster",
        ROUTER,
        "            if own is not None and len(own) <= MAX_IMPORTED_ROSTER_PLAYERS:",
        "            if False:",
        "test_the_waiver_refresh_rewrites_the_callers_own_roster_with_its_slots",
        "if own is not None and len(own)",
    ),
    # ── Phase B fact columns (2026-09-17) ────────────────────────────────────────────────────
    (
        "the refresh is fetched but the STALE stored rosters are still used for the pool",
        ROUTER,
        '                "league_rosters": kept,',
        '                "league_rosters": record.get("league_rosters"),',
        F("test_a_refreshed_roster_removes_a_player_the_stale_snapshot_still_listed"),
        None,
    ),
    (
        "a missing fact is filled from the preseason projection (the absolute rule)",
        FACTS,
        '        return {"points": None, "games": 0, "absence": "no_realized_line"}',
        '        return {"points": player.get("fpPpr"), "games": 0, "absence": "no_realized_line"}',
        F("test_the_projection_is_never_substituted_for_a_missing_fact"),
        None,
    ),
    (
        "a team defence reads as a zero instead of the team-grain absence",
        FACTS,
        '        return {"points": None, "games": None, "absence": "team_grain_not_covered"}',
        '        return {"points": 0.0, "games": 0, "absence": None}',
        F("test_a_team_defence_is_a_stated_team_grain_absence_never_a_zero"),
        "team_grain_not_covered\"}",
    ),
    (
        "every row present is summed, not only the covered weeks",
        FACTS,
        "        if row.get(\"week\") not in covered:\n            continue\n",
        "",
        F("test_only_the_covered_run_of_weeks_is_summed"),
        "not in covered",
    ),
    (
        "the rows-hash twin drifts from the publisher's definition",
        FACTS,
        "    return hashlib.sha256(json.dumps(obj, default=str).encode()).hexdigest()",
        "    return hashlib.sha256(json.dumps(obj, default=str, separators=(',', ':')).encode()).hexdigest()",
        F("test_the_verifier_accepts_what_the_real_builder_publishes"),
        None,
    ),
    (
        "the source_fingerprint is never checked",
        FACTS,
        '    if fingerprint != manifest.get("source_fingerprint"):',
        "    if False:",
        F("test_a_single_broken_lineage_property_is_refused"),
        'fingerprint != manifest.get("source_fingerprint")',
    ),
    (
        "the id rung is removed (name aliases lose their facts)",
        FACTS,
        "    if _GSIS_ID.match(pid):",
        "    if False:",
        F("test_the_id_rung_recovers_a_name_alias"),
        "_GSIS_ID.match(pid)",
    ),
    (
        "an id match is trusted across position groups",
        FACTS,
        "            hit = None  # same id, different position group: do not guess",
        "            pass",
        F("test_an_id_match_at_a_different_position_is_not_trusted"),
        "do not guess",
    ),
    (
        "within a position, the ordering runs low-to-high",
        FACTS,
        '    with_facts.sort(key=lambda p: -float(p["realized"]["points"]))',
        '    with_facts.sort(key=lambda p: float(p["realized"]["points"]))',
        F("test_within_a_position_facts_order_high_first_and_the_rest_keep_board_order"),
        None,
    ),
    (
        "a failed lineage check is ignored and the facts served anyway",
        ROUTER,
        "    if violations:\n        logger.warning(\"waiver facts:",
        "    if False:\n        logger.warning(\"waiver facts:",
        F("test_a_tampered_artifact_withholds_the_facts_and_is_not_cached"),
        None,
    ),
    (
        "the defence group is ranked alongside the others",
        ROUTER,
        '                group_ranked = facts is not None and g["pos"] != "DST"',
        "                group_ranked = facts is not None",
        F("test_the_defence_group_stays_unranked_with_its_specific_reason"),
        None,
    ),
    (
        "RC1's excluded weeks are dropped from the payload (a silent partial season)",
        ROUTER,
        '                    for e in (r_manifest.get("excluded") or [])',
        "                    for e in []",
        F("test_an_excluded_week_is_carried_as_a_stated_gap"),
        'r_manifest.get("excluded")',
    ),

    # ── ⑰ THE ALIAS DETECTOR (PM ruling 2026-09-18) ───────────────────────────────────────────────
    # The ruling asked for a planted alias divergence specifically. Three breaks, because the
    # detector has three separable failure modes and a single break would leave two unproven.
    (
        "the alias detector never fires (its comparison always says no)",
        POOL,
        "    return r_first.startswith(b_first) or b_first.startswith(r_first)",
        "    return False",
        "test_the_alias_detector_fires_on_the_measured_case_and_names_both_spellings",
        None,
    ),
    (
        "the alias detector refuses a rostered player who is merely OFF THE BOARD (the other cause)",
        POOL,
        '        if hits:\n            alias_suspects.append({"rostered": row, "board": hits})\n        else:\n            off_board.append(row)',
        '        alias_suspects.append({"rostered": row, "board": hits})',
        "test_a_rostered_player_genuinely_off_the_board_does_NOT_refuse",
        None,
    ),
    (
        "the alias comparison goes fuzzy and calls two different players one (planted: Kelce/Kelce)",
        POOL,
        "    if len(r_first) < 3 or len(b_first) < 3:\n        return False\n    return r_first.startswith(b_first) or b_first.startswith(r_first)",
        "    return True",
        "test_the_alias_comparison_does_not_fire_on_two_different_players",
        None,
    ),
    (
        "the endpoint computes the reconciliation and serves the pool anyway",
        ROUTER,
        "        if alias:\n            refusals = alias\n        elif total > MAX_POOL_ROWS:",
        "        if total > MAX_POOL_ROWS:",
        "test_the_endpoint_withholds_the_pool_when_the_alias_detector_fires",
        None,
    ),
]


def run_suite(test: str | None = None) -> tuple[bool, str]:
    if test is None:
        target = [SUITE, FACT_SUITE]
    else:
        target = [test if "::" in test else f"{SUITE}::{test}"]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-500:]


def main() -> int:
    originals = {p: p.read_text() for p in (POOL, SLEEPER, ROUTER, FACTS)}
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
