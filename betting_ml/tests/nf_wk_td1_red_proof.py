"""nf_wk_td1_red_proof.py — prove NF-WK-TD1's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here — the machinery is `nf_wk_mt1_red_proof`'s,
reused verbatim rather than re-invented:
  1. **the mutation never LANDS** (#682) — every mutation asserts the file CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — a replacing mutation asserts the
     OLD token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied;
  4. **the node id COLLECTS NOTHING** — pytest exits non-zero on an unresolvable node id, so a
     renamed guard reports a perfect RED for a test that no longer exists. Every node id is
     resolved during the BASELINE phase, before any source is touched.
⭐ Plus a BASELINE-PASS leg and a NOT-SELECTED leg (a mutation must not turn some OTHER test red and
be credited to this one).

⛔ Restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's own
worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson).

⚠️ NOT SAFE TO RUN CONCURRENTLY WITH ITSELF. One at a time.

RUN (LAPTOP, ~60 s):
    uv run python betting_ml/tests/nf_wk_td1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TESTS = _REPO / "betting_ml/tests"
_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"

_SERVING = _FAN / "weekly_serving.py"
_RUNNER = _FAN / "run_weekly_serving.py"
_SCORING = _REPO / "app/backend/services/league_scoring.py"

_GUARD = _TESTS / "test_nf_wk_td1_touchdown_components.py"
_GUARD_FILES = (_GUARD,)

#: An unrelated clause that must stay GREEN through every mutation — otherwise a RED is not
#: attributable to the guard it is credited to.
NOT_SELECTED = f"{_TESTS / 'test_nf_c6_ph2_weekly_contract.py'}::test_the_paid_set_is_derived_from_the_scorers_own_stat_field_map"

_BAK_SUFFIX = ".redproof.bak"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── the attach: derived, and off the right feed ─────────────────────────────────────────────
    ("the missing set is a HAND LIST of the four, so a twelfth component lands null again",
     _SERVING,
     "    missing = tuple(c for c in components if c not in modeled.columns)",
     '    missing = tuple(c for c in ("passing_tds", "passing_interceptions", "rushing_tds",\n'
     '                                "receiving_tds") if c not in modeled.columns)',
     f"{_GUARD}::test_the_missing_set_is_derived_so_a_twelfth_component_cannot_land_null"),

    ("the attach reads the STUB-BEARING feed, so a fabricated zero can become a label",
     _SERVING,
     '    modeled, label_audit = attach_component_labels(modeled, src["stats"])',
     "    modeled, label_audit = attach_component_labels(modeled, feat_stats)",
     f"{_GUARD}::test_build_serving_matrix_calls_the_attach_on_the_real_feed_not_the_stub"),

    ("nothing attaches the labels at all — the defect, restored",
     _SERVING,
     '    modeled, label_audit = attach_component_labels(modeled, src["stats"])\n'
     '    audit = {**audit, "component_labels": label_audit}\n',
     "",
     f"{_GUARD}::test_build_serving_matrix_calls_the_attach_on_the_real_feed_not_the_stub"),

    ("a feed missing a declared column DEGRADES to null instead of refusing",
     _SERVING,
     "    absent_from_feed = [c for c in missing if c not in stats.columns]",
     "    missing = tuple(c for c in missing if c in stats.columns)\n"
     "    absent_from_feed = []",
     f"{_GUARD}::test_the_attach_refuses_rather_than_degrades_when_the_feed_lacks_a_declared_column"),

    ("the duplicate-grain refusal is dropped, so one player becomes two half-truths",
     _SERVING,
     '    dup = int(s.duplicated(keys).sum())\n    if dup:',
     '    dup = int(s.duplicated(keys).sum())\n    s = s.drop_duplicates(keys)\n    if False:',
     f"{_GUARD}::test_the_attach_refuses_a_duplicate_grain"),

    # ── the refusal: VALUES, never keys ─────────────────────────────────────────────────────────
    ("the completeness refusal checks KEY PRESENCE instead of a non-null VALUE",
     _SERVING,
     "                if r.get(f) is None:",
     "                if f not in r:",
     f"{_GUARD}::test_the_refusal_fires_on_the_published_pre_td_artifact_shape"),

    ("the fabrication branch is dropped — a number for a player we did not project can ship",
     _SERVING,
     "        elif status != \"bye\":",
     "        elif False:",
     f"{_GUARD}::test_the_refusal_fires_on_a_fabricated_row_for_a_player_the_model_did_not_project"),

    ("the refusal scores a payload with ZERO projected rows as healthy",
     _SERVING,
     "    if not n_projected:",
     "    if False:",
     f"{_GUARD}::test_the_refusal_refuses_to_pass_on_nothing"),

    ("a bye is treated as a fabrication, so the deterministic identity zero cannot ship",
     _SERVING,
     '        if status == "projected":',
     '        if status in ("projected", "bye"):',
     f"{_GUARD}::test_a_bye_is_the_documented_exception_and_does_not_trip_either_direction"),

    # ── the runner invokes it (wired ≠ invoked) ─────────────────────────────────────────────────
    ("the refusal is defined but the runner never calls it",
     _RUNNER,
     "    comp_line = WS.assert_component_line_complete(players)",
     "    comp_line = {\"n_projected\": len(players), \"n_component_fields\": 11}",
     f"{_GUARD}::test_the_runner_refuses_a_payload_whose_component_line_is_incomplete"),

    ("training is no longer strictly before the target week, so a retained zero becomes a label",
     _RUNNER,
     '    train = modeled.loc[modeled["gw"] < int(target_rows["gw"].iloc[0])].reset_index(drop=True)',
     '    train = modeled.loc[modeled["gw"] <= int(target_rows["gw"].iloc[0])].reset_index(drop=True)',
     f"{_GUARD}::test_a_target_week_label_can_never_reach_training"),

    # ── the consumer-visible point: CAPTURED → APPLIED ──────────────────────────────────────────
    ("the coverage classifier counts a KEY rather than a value, so a null term reads as applied",
     _SCORING,
     "            if isinstance(v, bool) or v is None:\n                continue",
     "            if isinstance(v, bool):\n                continue\n"
     "            if v is None:\n                out.add(k)\n                continue",
     f"{_GUARD}::test_emission_flips_the_touchdown_terms_from_captured_to_applied"),
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
    for root in (_REPO / "app/backend", _TESTS, _FAN):
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
            additive = bool(new) and old in new
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
