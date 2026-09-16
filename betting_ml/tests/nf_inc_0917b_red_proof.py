"""nf_inc_0917b_red_proof.py — prove NF-INC-0917B's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE FIRST CASE IS THE HISTORICAL STATE ITSELF — `model_validate(manifest)` with the result
discarded, exactly the line that shipped a manifest with no `framing` and took `/fantasy/weekly`
down for 758 minutes. If that mutation does not turn a guard red, nothing in this story is guarded.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here — machinery reused verbatim from
`nf_wk_td1_red_proof` rather than re-invented:
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

⚠️ WHY THE TWO ROUTE MUTATIONS BOTH POINT AT A STRUCTURAL GUARD, stated so it is not read as a
weaker test: the response model and the explicit coercion are REDUNDANT BY DESIGN — either alone
keeps the wire complete — so deleting one cannot be seen behaviourally while the other covers for
it. The structural guard is the only place that deletion is visible, and its own RED proof is these
two cases.

⛔ Restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's own
worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson).

⚠️ NOT SAFE TO RUN CONCURRENTLY WITH ITSELF. One at a time.

RUN (LAPTOP, ~40 s):
    uv run python betting_ml/tests/nf_inc_0917b_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TESTS = _REPO / "betting_ml/tests"
_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"

_RUNNER = _FAN / "run_weekly_serving.py"
_CONTRACT = _REPO / "app/backend/models/nfl_weekly.py"
_ROUTER = _REPO / "app/backend/routers/fantasy.py"
_CONFIG = _REPO / "frontend/next.config.mjs"

_GUARD = _TESTS / "test_nf_inc_0917b_wire_shape.py"
_GUARD_FILES = (_GUARD,)

#: An unrelated clause that must stay GREEN through every mutation — otherwise a RED is not
#: attributable to the guard it is credited to.
NOT_SELECTED = (f"{_TESTS / 'test_nf_c6_ph2_weekly_contract.py'}"
                "::test_the_paid_set_is_derived_from_the_scorers_own_stat_field_map")

_BAK_SUFFIX = ".redproof.bak"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── the historical state, restored ───────────────────────────────────────────────────────────
    ("THE OUTAGE ITSELF — the builder validates the manifest and throws the result away",
     _RUNNER,
     "    manifest = C.NflWeeklyManifest.model_validate(manifest).model_dump()",
     "    C.NflWeeklyManifest.model_validate(manifest)",
     f"{_GUARD}::test_the_weekly_builder_never_validates_and_discards"),

    ("…and the same for the players payload, which is missing `scoring_system_id` on the wire today",
     _RUNNER,
     "    payload = C.NflWeeklyPayload.model_validate(payload).model_dump()",
     "    C.NflWeeklyPayload.model_validate(payload)",
     f"{_GUARD}::test_the_weekly_builder_never_validates_and_discards"),

    # ── the write-path gate ──────────────────────────────────────────────────────────────────────
    ("staging no longer refuses a blob that is short of its own contract",
     _RUNNER,
     "    shape = assert_contract_shaped(built)\n"
     "    log.info(\"[METRIC] weekly_contract_fields_checked=%d\", sum(shape.values()))\n",
     "",
     f"{_GUARD}::test_the_write_path_refuses_the_manifest_that_actually_shipped"),

    ("the dry run skips the gate, so the rehearsal stops exercising the refusal",
     _RUNNER,
     "    assert_contract_shaped(built)\n    t = built[\"target\"]\n    keys = {",
     "    t = built[\"target\"]\n    keys = {",
     f"{_GUARD}::test_the_dry_run_refuses_too_not_only_a_real_publish"),

    ("the shape check stops recursing, so a nested contract can empty out unseen",
     _CONTRACT,
     "        sub = _nested_model(field.annotation)\n"
     "        if sub is not None:\n"
     "            out += missing_declared_fields(blob[name], sub, where=f\"{pre}{name}\")\n"
     "            continue",
     "        sub = None\n        if sub is not None:\n            continue",
     f"{_GUARD}::test_the_historical_manifest_really_is_defective"),

    ("the shape check stops walking list items, so one bad player row ships",
     _CONTRACT,
     "        item = _item_model(field.annotation)\n"
     "        if item is not None and isinstance(blob[name], list):",
     "        item = None\n        if item is not None and isinstance(blob[name], list):",
     f"{_GUARD}::test_a_missing_field_on_one_player_row_is_caught_too"),

    # ── the route: two halves, each deletable without the other noticing ─────────────────────────
    ("the route loses its response_model and is a pass-through of the S3 blob again",
     _ROUTER,
     '@board_router.get("/nfl/weekly/manifest",\n'
     '                  response_model=nfl_weekly.NflWeeklyManifestResponse)',
     '@board_router.get("/nfl/weekly/manifest")',
     f"{_GUARD}::test_the_manifest_route_carries_both_halves_of_the_fix"),

    ("the route stops coercing, so a blob already in S3 reaches the wire as written",
     _ROUTER,
     "    return nfl_weekly.NflWeeklyManifestResponse.model_validate(\n"
     "        entitlement.open_manifest_payload(nfl_weekly.NflWeeklyManifest.model_validate(data).model_dump())\n"
     "    )",
     "    return entitlement.open_manifest_payload(data)",
     f"{_GUARD}::test_the_manifest_route_carries_both_halves_of_the_fix"),

    ("the response model is the BARE contract, so the entitlement envelope is stripped (E9.41)",
     _ROUTER,
     "                  response_model=nfl_weekly.NflWeeklyManifestResponse)",
     "                  response_model=nfl_weekly.NflWeeklyManifest)",
     f"{_GUARD}::test_the_route_preserves_the_entitlement_envelope"),

    # ── the CSP ─────────────────────────────────────────────────────────────────────────────────
    ("worker-src is gone, so session replay is silently off in production again",
     _CONFIG,
     '      "worker-src \'self\' blob:",\n',
     "",
     f"{_GUARD}::test_the_replay_worker_is_not_blocked_by_our_own_policy"),

    ("worker-src names only 'self', which reads as a fix and still blocks the blob: worker",
     _CONFIG,
     '"worker-src \'self\' blob:"',
     '"worker-src \'self\'"',
     f"{_GUARD}::test_the_replay_worker_is_not_blocked_by_our_own_policy"),
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
    for root in (_REPO / "app/backend", _TESTS, _FAN, _REPO / "frontend"):
        for bak in root.rglob(f"*{_BAK_SUFFIX}"):
            target = Path(str(bak)[: -len(_BAK_SUFFIX)])
            assert target.suffix in (".py", ".mjs"), (
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
