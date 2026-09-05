"""nf_c6_ph2_red_proof.py — prove NF-C6-PH2's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here:
  1. **the mutation never LANDS** (#682) — every mutation asserts the file actually CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — a replacement asserts the OLD
     token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied;
  4. **the node id COLLECTS NOTHING** — pytest exits non-zero on an unresolvable node id, so a
     renamed guard reports a perfect RED for a test that no longer exists. Every case's node id is
     resolved during the BASELINE phase, before any source is touched.
⭐ Plus a BASELINE-PASS leg (the guard must be GREEN on unbroken source, or "red" means nothing) and
a NOT-SELECTED leg (a mutation must not turn some OTHER test red and be credited to this one). The
NOT-SELECTED control deliberately lives in an UNRELATED suite that imports none of the modules a
mutation can break at import time — several breaks here trip `nfl_weekly`'s own import-time schema
assertions, which fails every test in a file that imports it and would make the control read
"not attributable" for a perfectly attributable red.

⛔ It restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's
own worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson,
learned when a RED proof SIGKILLed itself).

RUN (LAPTOP, ~90 s):
    uv run python betting_ml/tests/nf_c6_ph2_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"
_TESTS = _REPO / "betting_ml/tests"

_CONTRACT = _REPO / "app/backend/models/nfl_weekly.py"
_ROUTER = _REPO / "app/backend/routers/fantasy.py"
_GUARDRAILS = _REPO / "app/backend/services/cost_guardrails.py"
_CDN = _REPO / "frontend/app/api/public/[...path]/route.ts"
_SERVING = _FAN / "weekly_serving.py"
_FRESH = _REPO / "betting_ml/monitoring/nfl_weekly_freshness.py"

_G_CONTRACT = _TESTS / "test_nf_c6_ph2_weekly_contract.py"
_G_SERVING = _TESTS / "test_nf_c6_ph2_weekly_serving.py"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    ("the matchup-claim guard stops refusing the claim NF-W1 measured as false",
     _CONTRACT,
     "    if offending:\n        raise ValueError(\n            f\"{where} claims {offending}, but NF-W1 measured the matchup foil LOSING at all four \"",
     "    if False:\n        raise ValueError(\n            f\"{where} claims {offending}, but NF-W1 measured the matchup foil LOSING at all four \"",
     f"{_G_CONTRACT}::test_the_matchup_guard_actually_refuses_the_claim"),

    ("the paid set becomes a hand-written literal instead of being derived from STAT_FIELD",
     _CONTRACT,
     "PAID_WEEKLY_PLAYER_FIELDS: frozenset[str] = (\n    frozenset(WEEKLY_COMPONENT_FIELD.values()) | {QUANTILE_VECTOR_FIELD}\n)",
     "PAID_WEEKLY_PLAYER_FIELDS: frozenset[str] = frozenset({\"passYds\", \"rushYds\", \"recYds\"})",
     f"{_G_CONTRACT}::test_the_paid_set_is_derived_from_the_scorers_own_stat_field_map"),

    ("an unmapped component resolves silently instead of refusing",
     _CONTRACT,
     "    if unmapped:\n        raise ValueError(",
     "    if False:\n        raise ValueError(",
     f"{_G_CONTRACT}::test_a_component_with_no_stat_field_entry_is_refused"),

    ("the free reduction stops stripping paid fields",
     _CONTRACT,
     "    return {k: v for k, v in row.items() if k not in PAID_WEEKLY_PLAYER_FIELDS}",
     "    return dict(row)",
     f"{_G_CONTRACT}::test_the_free_row_carries_no_paid_field_and_keeps_every_free_one"),

    ("the FREE weekly projection serves the full payload (the component line leaks)",
     _ROUTER,
     "    return entitlement.open_projections_payload(nfl_weekly.public_weekly_payload(data))",
     "    return entitlement.open_projections_payload(data)",
     f"{_G_CONTRACT}::test_the_free_weekly_projection_carries_no_paid_component"),

    ("the PAID weekly route moves onto the ungated board router",
     _ROUTER,
     "@router.get(\"/nfl/weekly/projections-full\")",
     "@board_router.get(\"/nfl/weekly/projections-full\")",
     f"{_G_CONTRACT}::test_the_paid_weekly_route_refuses_an_anonymous_caller"),

    ("the CDN allowlist gains the PAID weekly route",
     _CDN,
     "  \"weekly-projections\": {\n    upstream: \"/fantasy/nfl/weekly/projections\",",
     "  \"weekly-projections\": {\n    upstream: \"/fantasy/nfl/weekly/projections-full\",",
     f"{_G_CONTRACT}::test_the_cdn_route_proxies_the_free_weekly_reads_and_never_the_paid_one"),

    ("the cache rules use the /weekly PREFIX, which sweeps the paid route in with it",
     _GUARDRAILS,
     "    (\"/fantasy/nfl/weekly/manifest\", 900, 3600),\n    (\"/fantasy/nfl/weekly/projections\", 900, 3600),",
     "    (\"/fantasy/nfl/weekly\", 900, 3600),",
     f"{_G_CONTRACT}::test_the_free_weekly_paths_are_shared_cacheable_and_the_paid_one_never_is"),

    ("the target week is chosen by the LAST kickoff, so a started slate stays current",
     _SERVING,
     "    firsts = s.groupby([\"season\", \"week\"], as_index=False)[\"gameday\"].min()",
     "    firsts = s.groupby([\"season\", \"week\"], as_index=False)[\"gameday\"].max()",
     f"{_G_SERVING}::test_a_slate_that_has_already_started_is_not_the_target"),

    ("the opponent-grid stub emits nothing, so the block is absent at serve again",
     _SERVING,
     "    stub = pd.DataFrame(rows)\n    for c in stats.columns:",
     "    stub = pd.DataFrame(rows).iloc[0:0]\n    for c in stats.columns:",
     f"{_G_SERVING}::test_the_stub_reproduces_the_training_block_to_1e_9"),

    ("the frozen-form check stops refusing a recomputed lag",
     _SERVING,
     "    if moved:\n        raise WeeklyServingError(\n            f\"horizon rows are NOT frozen form:",
     "    if False:\n        raise WeeklyServingError(\n            f\"horizon rows are NOT frozen form:",
     f"{_G_SERVING}::test_the_frozen_form_check_CATCHES_a_recomputed_lag"),

    ("the outcome-independence tolerance is widened until a real leak fits inside it",
     _SERVING,
     "INDEPENDENCE_RTOL = 1e-9\nINDEPENDENCE_ATOL = 1e-9",
     "INDEPENDENCE_RTOL = 1e9\nINDEPENDENCE_ATOL = 1e9",
     f"{_G_SERVING}::test_the_proof_CATCHES_a_lost_lag"),

    ("the point-in-time vacuity check accepts a gate that examined zero records",
     _SERVING,
     "    if weeks <= 0 or records <= 0:",
     "    if weeks <= 0 and records <= 0:",
     f"{_G_SERVING}::test_the_pit_gate_must_have_examined_something"),

    ("the ROS band is read at the nearest GRID levels instead of 0.16/0.84",
     _CONTRACT,
     "ROS_SIGMA_LO_LEVEL: float = 0.16\nROS_SIGMA_HI_LEVEL: float = 0.84",
     "ROS_SIGMA_LO_LEVEL: float = 0.15\nROS_SIGMA_HI_LEVEL: float = 0.85",
     f"{_G_SERVING}::test_the_ros_band_is_read_at_the_levels_that_make_sigma_sigma"),

    ("a bye stops counting as a remaining week, so rosWeeks means two things",
     _SERVING,
     "        parts.append(pd.DataFrame({\n            \"gsis_id\": horizon[\"gsis_id\"].astype(str).to_numpy(),",
     "        horizon, hq = horizon[~is_bye], hq[~is_bye]\n        mean, q16, q84 = mean[~is_bye], q16[~is_bye], q84[~is_bye]\n        parts.append(pd.DataFrame({\n            \"gsis_id\": horizon[\"gsis_id\"].astype(str).to_numpy(),",
     f"{_G_SERVING}::test_ros_counts_a_bye_as_a_remaining_week_worth_zero"),

    ("coverage is compared against POOLED training instead of the same week number",
     _SERVING,
     "    same_week = train[train[\"week\"] == target.week]",
     "    same_week = train",
     f"{_G_SERVING}::test_the_coverage_report_separates_a_serve_only_null_from_a_structural_one"),

    ("the freshness monitor stops distinguishing a WRONG WEEK from a healthy one",
     _FRESH,
     "    if reading.week != expected_week:",
     "    if False:",
     f"{_G_SERVING}::test_a_build_running_fine_on_LAST_weeks_slate_is_CRITICAL"),

    ("an unreadable manifest is scored healthy instead of UNKNOWN/WARN",
     _FRESH,
     "    if not reading.readable:",
     "    if False:",
     f"{_G_SERVING}::test_an_unreadable_manifest_is_WARN_never_healthy"),

    ("the off-season deactivation is removed, so the SLA pages for seven months",
     _FRESH,
     "    return expected_week is not None",
     "    return True",
     f"{_G_SERVING}::test_the_off_season_deactivates_the_sla_rather_than_paging_for_seven_months"),
]

#: The NOT-SELECTED control: a test that must stay GREEN under every mutation above, so a red
#: reading is never credited to a mutation that simply broke a module for everyone.
#: ⚠️ Deliberately in an UNRELATED suite that imports none of the modules a mutation can break at
#: IMPORT time — several breaks here trip `nfl_weekly`'s own import-time schema assertions, which
#: fails EVERY test in a file that imports it.
NOT_SELECTED = f"{_TESTS / 'test_freemium_tier.py'}::test_every_capability_is_placed_on_exactly_one_side"

_GUARD_FILES = (_G_CONTRACT, _G_SERVING)


def _run(nodeid: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header", "-p",
                        "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    return r.returncode == 0


def _collects(nodeid: str) -> bool:
    """Does this node id resolve to at least one test? ⚠️ Asked ONLY on UNBROKEN source: a mutation
    that trips a module-level assertion legitimately breaks COLLECTION, and refusing there would
    turn a working RED case into a hard error."""
    probe = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header",
                            "--collect-only", "-p", "no:cacheprovider"],
                           cwd=_REPO, capture_output=True, text=True)
    return probe.returncode == 0 and "no tests ran" not in (probe.stdout + probe.stderr)


def _sweep_stale_backups() -> list[str]:
    """⛔ FIRST, before any mutation: a stale `.redproof.bak` means real source is still broken."""
    restored = []
    for root in (_FAN, _TESTS, _REPO / "app/backend", _REPO / "betting_ml/monitoring",
                 _REPO / "frontend/app/api"):
        for bak in root.rglob("*.redproof.bak"):
            target = bak.with_suffix("")
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
    ok = all(_run(str(f)) for f in _GUARD_FILES)
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
