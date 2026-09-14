"""nf_wk_fe1_red_proof.py — prove NF-WK-FE1's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here (the shape `nf_c6_ph2_red_proof.py`
established, reused deliberately rather than re-invented):
  1. **the mutation never LANDS** (#682) — every mutation asserts the file actually CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — a replacing mutation asserts the
     OLD token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied;
  4. **the node id COLLECTS NOTHING** — pytest exits non-zero on an unresolvable node id, so a
     renamed guard reports a perfect RED for a test that no longer exists. Every case's node id is
     resolved during the BASELINE phase, before any source is touched.
⭐ Plus a BASELINE-PASS leg (the guard must be GREEN on unbroken source, or "red" means nothing) and
a NOT-SELECTED leg (a mutation must not turn some OTHER test red and be credited to this one).

⛔ Restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's own
worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson).

⚠️ NOT SAFE TO RUN CONCURRENTLY WITH ITSELF — the start-up sweep would treat another instance's
in-flight backup as stale. One at a time.

RUN (LAPTOP, ~40 s):
    uv run python betting_ml/tests/nf_wk_fe1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TESTS = _REPO / "betting_ml/tests"
_FE = _REPO / "frontend"

_COPY = _FE / "lib/fantasy-claim-copy.ts"
_READ = _FE / "lib/nfl-weekly.ts"
_PAGE = _FE / "components/fantasy/weekly-page.tsx"
_NAV = _FE / "lib/nav-model.ts"
_FREE_FIX = _FE / "e2e/fixtures/api/fantasy-nfl-weekly-players-free.synthetic.json"

_GUARD = _TESTS / "test_nf_wk_fe1_weekly_page.py"
_GUARD_FILES = (_GUARD,)

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── AC 1(f): the claims discipline ──────────────────────────────────────────────────────────
    ("the page copy claims the weekly edge is matchup-based (NF-W1 measured that FALSE)",
     _COPY,
     "These are conditioned on how players are actually being used",
     "These are matchup-based and conditioned on how players are actually being used",
     f"{_GUARD}::test_the_weekly_copy_makes_no_matchup_claim"),

    ("a component's inline copy reintroduces the matchup claim the module screen cannot see",
     _PAGE,
     '<h2 className="text-[13px] font-semibold text-gray-300">{WEEKLY_PPR_NATIVE_TITLE}</h2>',
     '<h2 className="text-[13px] font-semibold text-gray-300">Matchup-driven weekly points</h2>',
     f"{_GUARD}::test_the_weekly_page_source_carries_no_matchup_claim_either"),

    # ── AC 1(a): the points head is the projection ──────────────────────────────────────────────
    ("the page totals the component line into a second, irreconcilable points figure",
     _PAGE,
     "  const shown = WEEKLY_STAT_FIELDS.filter(",
     "  const derivedTotal = (paid!.passYds ?? 0) + (paid!.rushYds ?? 0)\n"
     "  void derivedTotal\n"
     "  const shown = WEEKLY_STAT_FIELDS.filter(",
     f"{_GUARD}::test_the_weekly_tree_never_derives_a_total_from_the_component_line"),

    ("the stat-line note drops the independence statement that is its entire point",
     _COPY,
     "the two are produced independently and they will not agree exactly",
     "the two are close enough for most purposes",
     f"{_GUARD}::test_the_stat_line_note_states_the_independence_rather_than_a_measured_figure"),

    # ── AC 1(c): the three absence causes stay three ────────────────────────────────────────────
    ("a served absence reason loses its label and would render under its raw machine key",
     _COPY,
     '  pit_gate_dropped: "Held back by our point-in-time check",\n',
     "",
     f"{_GUARD}::test_every_served_absence_reason_has_a_frontend_label"),

    ("the page labels an absence reason nothing serves (dead copy reading as coverage)",
     _COPY,
     '  pit_gate_dropped: "Held back by our point-in-time check",\n',
     '  pit_gate_dropped: "Held back by our point-in-time check",\n'
     '  invented_reason_nothing_serves: "Something else",\n',
     f"{_GUARD}::test_the_frontend_labels_no_reason_the_contract_does_not_declare"),

    # ── AC 2: the paid set and the entitlement seam ─────────────────────────────────────────────
    ("a paid component drops out of the display registry and is silently never drawn",
     _READ,
     '  { key: "recTd", label: "Rec TD" },\n',
     "",
     f"{_GUARD}::test_the_display_stat_registry_covers_every_paid_component"),

    ("a per-position stat list names a field that does not exist, rendering nothing silently",
     _READ,
     '  TE: ["tgt", "rec", "recYds", "recTd"],',
     '  TE: ["tgt", "rec", "recYds", "recTd", "recFumblesNotAField"],',
     f"{_GUARD}::test_every_position_stat_list_names_only_real_component_fields"),

    ("the PAID read is routed through the CDN arm, which strips Authorization by design",
     _READ,
     "  return apiFetch(`/fantasy/nfl/weekly/projections-full?${weeklyQuery(season, week)}`, {}, token)",
     "  return cdnFetch(`/api/public/weekly-projections-full?${weeklyQuery(season, week)}`)",
     f"{_GUARD}::test_the_paid_read_is_never_routed_through_the_cdn_arm"),

    ("the weekly tree imports a scorer — the fourth implementation of one scoring policy",
     _PAGE,
     'import { useMemo, useState } from "react"',
     'import { useMemo, useState } from "react"\nimport { buildBoard } from "@/lib/league-scoring"',
     f"{_GUARD}::test_the_weekly_tree_imports_no_scorer"),

    # ── AC 1(e): the pricing framing ────────────────────────────────────────────────────────────
    ("the PPR framing reads as a paywall — 'one free format' implies twelve locked ones",
     _COPY,
     "Other scoring formats are not being withheld; they do not exist for the weekly projection yet.",
     "This is the one free format; unlock the rest with a membership.",
     f"{_GUARD}::test_the_ppr_framing_says_the_other_formats_do_not_exist_rather_than_that_they_are_withheld"),

    ("the read layer starts sending a scoring-format parameter the routes do not accept",
     _READ,
     '  const qs = new URLSearchParams({ season: String(season) })',
     '  const qs = new URLSearchParams({ season: String(season), config: "full_ppr" })',
     f"{_GUARD}::test_the_weekly_routes_take_no_scoring_format_parameter"),

    # ── the nav door ────────────────────────────────────────────────────────────────────────────
    ("the weekly nav entry loses `public`, hiding a free surface from the visitors it is for",
     _NAV,
     '                href: "/fantasy/weekly",\n                key: "fantasy-weekly",\n                public: true,',
     '                href: "/fantasy/weekly",\n                key: "fantasy-weekly",',
     f"{_GUARD}::test_the_weekly_nav_entry_exists_and_is_public_beside_the_season_projections"),

    ("the nav label is typed into the data module where no copy screening ever sees it",
     _NAV,
     "                label: WEEKLY_NAV_LABEL,",
     '                label: "This Week",',
     f"{_GUARD}::test_the_nav_label_comes_from_the_canonical_copy_module"),

    # ── the fixtures ────────────────────────────────────────────────────────────────────────────
    ("the free fixture is hand-edited, so every entitlement clause tests an invented paywall",
     _FREE_FIX,
     '      "histWeeks": 21',
     '      "histWeeks": 21,\n      "passYds": 239.4',
     f"{_GUARD}::test_the_free_fixture_is_the_shipping_reducer_applied_to_the_entitled_one"),

    ("the fixture loses its bye row, so the bye clauses would assert on nothing",
     _FREE_FIX,
     '      "status": "bye",',
     '      "status": "projected",',
     f"{_GUARD}::test_the_fixture_reaches_every_state_the_page_distinguishes[bye]"),
]

#: The NOT-SELECTED control: a test that must stay GREEN under every mutation above, so a red
#: reading is never credited to a mutation that simply broke a module for everyone.
#: ⚠️ Deliberately in an UNRELATED suite that imports none of the modules a mutation can break at
#: IMPORT time.
NOT_SELECTED = f"{_TESTS / 'test_freemium_tier.py'}::test_every_capability_is_placed_on_exactly_one_side"

_BAK_SUFFIX = ".redproof.bak"


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
    real file mutated and reports success (the defect `nf_c6_ph2_red_proof.py` records).
    """
    restored = []
    for root in (_FE / "lib", _FE / "components", _FE / "e2e", _TESTS):
        for bak in root.rglob(f"*{_BAK_SUFFIX}"):
            target = Path(str(bak)[: -len(_BAK_SUFFIX)])
            assert target.suffix in (".py", ".ts", ".tsx", ".json"), (
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
