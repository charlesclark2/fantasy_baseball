#!/usr/bin/env python3
"""NCAAF-P3.9 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/ncaaf_p3_9_nav_red_proof.py
    uv run python betting_ml/tests/ncaaf_p3_9_nav_red_proof.py redirect   # one case, by substring

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_ncaaf_p3_9_nav.py` is refactored.

WHY. `test_ncaaf_p3_9_nav.py` is a SOURCE-INSPECTION suite, which is the shape that reads as
coverage while proving nothing — this repo has shipped a guard a COMMENT could satisfy (INC-38) and
a guard whose fixture a different clause already refused, so deleting the clause it NAMED changed
nothing (NF-D17 §7). Every clause there names a string that also appears in the prose beside it, so
the comment-stripping is load-bearing and has to be demonstrated rather than asserted.

⭐ EVERY CASE IS ISOLATING (NF-D17 §7): each break leaves every OTHER clause satisfiable, so only
the named one can flip.

⚠️ THE HARNESS ASSERTS ITS OWN MUTATION LANDED, AND THAT ITS ANCHOR IS UNIQUE. A patch that silently
no-ops reports "the guard caught it" when nothing was broken (E11.24 #682), and one that lands on
the WRONG identical substring reports a FALSE VACUITY — the more dangerous direction, because it
reads as a finding and invites weakening a correct guard (E11.24 prediction_log).

Restores every file from an IN-MEMORY backup in a `finally`. ⛔ Never `git checkout --`, which
destroys uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAV = REPO / "frontend/components/nav.tsx"
COPY = REPO / "frontend/lib/positioning-copy.ts"
FOOTER = REPO / "frontend/components/site-footer.tsx"
CONFIG = REPO / "frontend/next.config.mjs"
CI = REPO / ".github/workflows/ci.yml"

SUITE = "betting_ml/tests/test_ncaaf_p3_9_nav.py"

#: (label, file, old, new, test-name-substring)
CASES = [
    # ── the two declarations of one door ──────────────────────────────────────────────────────
    ("the signed-in door drifts to a different URL", NAV,
     'const NCAAF_NAV = { label: "NCAAF", href: "/ncaaf/games", key: "ncaaf-games" } as const',
     'const NCAAF_NAV = { label: "NCAAF", href: "/ncaaf", key: "ncaaf-games" } as const',
     "test_the_two_ncaaf_nav_declarations_agree"),

    ("the signed-out entry loses its activeLink key", COPY,
     '    desktop: true,\n    key: "ncaaf-games",\n  },',
     '    desktop: true,\n  },',
     "test_the_two_ncaaf_nav_declarations_agree"),

    # ⭐ THE DEFECT THIS STORY EXISTS TO FIX, reproduced: the door added ONLY to the signed-in
    # sport menu. `/ncaaf/games` is free and unguarded, so the anonymous reader — the default one —
    # would still have no way to find it.
    ("the door is signed-in only", COPY,
     '    href: "/ncaaf/games",\n    product: "ncaaf",',
     '    href: "/fantasy/rankings",\n    product: "fantasy",',
     "test_the_two_ncaaf_nav_declarations_agree"),

    # ── one menu at a time ────────────────────────────────────────────────────────────────────
    # ⚠️ THE E9.58 SHAPE: a nav affordance present at every viewport except the one most
    # first-touch readers arrive on. Each of the four sites is broken separately, because a single
    # count assertion could be satisfied by four copies in ONE menu.
    ("the signed-out desktop bar drops the handle", NAV,
     '                data-nav-item={item.key}\n                data-nav-active=',
     '                data-nav-active=',
     "test_the_ncaaf_door_is_drawn_at_every_viewport_and_auth_state"),

    ("the signed-in phone menu drops the door", NAV,
     '              data-nav-item={NCAAF_NAV.key}\n              data-nav-active=',
     '              data-nav-active=',
     "test_the_ncaaf_door_is_drawn_at_every_viewport_and_auth_state"),

    ("a signed-in link re-types its own href", NAV,
     '            href={NCAAF_NAV.href}\n            data-nav-item={NCAAF_NAV.key}',
     '            href="/ncaaf/games"\n            data-nav-item={NCAAF_NAV.key}',
     "test_the_ncaaf_door_is_drawn_at_every_viewport_and_auth_state"),

    # ── the product key two other stories' guards read as a proxy ──────────────────────────────
    ("NCAAF is filed under the MLB betting product key", COPY,
     '    product: "ncaaf",',
     '    product: "betting",',
     "test_the_signed_out_ncaaf_door_is_not_filed_under_the_mlb_product_key"),

    # ── the route ─────────────────────────────────────────────────────────────────────────────
    ("the bare /ncaaf redirect is removed", CONFIG,
     '      { source: "/ncaaf", destination: "/ncaaf/games", permanent: false },\n',
     '',
     "test_a_bare_ncaaf_redirects_to_the_board_and_is_not_cached_forever"),

    ("the redirect is made permanently cacheable", CONFIG,
     '{ source: "/ncaaf", destination: "/ncaaf/games", permanent: false }',
     '{ source: "/ncaaf", destination: "/ncaaf/games", permanent: true }',
     "test_a_bare_ncaaf_redirects_to_the_board_and_is_not_cached_forever"),

    # ── the footer, both halves ───────────────────────────────────────────────────────────────
    ("the footer link is removed", FOOTER,
     '  { label: "NCAAF Betting Intelligence", href: "/ncaaf/games" },\n',
     '',
     "test_the_footer_links_ncaaf_instead_of_calling_it_unbuilt"),

    # ⭐ THE HALF-FIX, and the likelier one: the live link is added and the stale row is left
    # beside it, so the footer both offers the product and calls it unbuilt.
    ("the stale 'Coming this season' row is left in place", FOOTER,
     '  { label: "NFL Betting Intelligence" },\n] as const',
     '  { label: "NFL Betting Intelligence" },\n  { label: "NCAAF Betting Intelligence" },\n] as const',
     "test_the_footer_links_ncaaf_instead_of_calling_it_unbuilt"),

    # ⛔ THE OVERSHOOT: deleting the whole "Coming this season" group. NFL betting is genuinely
    # unbuilt, and the group is what keeps an unshipped product honest.
    ("the coming-soon group is emptied", FOOTER,
     '  { label: "NFL Betting Intelligence" },\n] as const',
     '] as const',
     "test_the_footer_links_ncaaf_instead_of_calling_it_unbuilt"),

    # ── the CSP host ──────────────────────────────────────────────────────────────────────────
    ("the ESPN logo host is dropped from the CSP", CONFIG,
     "blob: https://a.espncdn.com https://img.mlbstatic.com",
     "blob: https://img.mlbstatic.com",
     "test_the_espn_logo_host_is_allowlisted_by_the_csp"),

    # ── finding ⑧, the CI wiring ──────────────────────────────────────────────────────────────
    ("the changelog filter is removed", CI,
     "            changelog:\n              - 'frontend/data/changelog.json'\n",
     "",
     "test_the_changelog_filter_selects_the_changelog_and_nothing_else"),

    # ⭐⭐ THE CATASTROPHIC OBVIOUS EDIT. Under `predicate-quantifier: every` this does not extend
    # the backend filter, it DISARMS it: every backend file would now have to match the changelog
    # path too, so `backend` resolves FALSE for the whole repo and no Python job ever runs again.
    ("the changelog is added to the backend filter instead", CI,
     "              - '!docs/**'\n",
     "              - '!docs/**'\n              - 'frontend/data/changelog.json'\n",
     "test_the_changelog_filter_selects_the_changelog_and_nothing_else"),

    ("predicate-quantifier: every is dropped", CI,
     "          predicate-quantifier: 'every'\n",
     "",
     "test_the_changelog_filter_selects_the_changelog_and_nothing_else"),

    # ⭐ THE GATE THAT DESTROYS ITS OWN EVIDENCE. `backend || changelog` fires on this very PR for
    # the pre-existing reason, so "the guard ran" would prove nothing about the new trigger.
    ("the guard job is gated on backend too", CI,
     "    if: needs.changes.outputs.changelog == 'true'",
     "    if: needs.changes.outputs.backend == 'true' || needs.changes.outputs.changelog == 'true'",
     "test_the_changelog_guard_job_is_gated_on_the_changelog_alone"),

    ("the guard job runs something other than the guard", CI,
     "        run: uv run pytest betting_ml/tests/test_changelog_guard.py -v --tb=short",
     "        run: echo ok",
     "test_the_changelog_guard_job_is_gated_on_the_changelog_alone"),

    # ⭐ FINDING ⑧ MOVED ONE JOB OVER RATHER THAN FIXED: the guard runs, goes red, and the NAMED
    # required check stays green because nothing reads its result.
    ("the roll-up stops depending on the guard", CI,
     "    needs: [changes, unit-tests-shard, static-checks, changelog-guard]",
     "    needs: [changes, unit-tests-shard, static-checks]",
     "test_the_changelog_guard_is_inside_the_named_required_check"),

    ("the roll-up collects the result and discards it", CI,
     'for r in "$CHANGES" "$SHARDS" "$STATIC" "$CHANGELOG"; do',
     'for r in "$CHANGES" "$SHARDS" "$STATIC"; do',
     "test_the_changelog_guard_is_inside_the_named_required_check"),

    # ── the comment-stripping itself (INC-38) ─────────────────────────────────────────────────
    # ⭐ PROSE MUST NOT SATISFY A SOURCE GUARD. Delete the real declaration and leave a comment
    # containing the exact string the clause looks for. Without `_code`'s stripper this stays GREEN.
    ("prose is left where the declaration was", NAV,
     'const NCAAF_NAV = { label: "NCAAF", href: "/ncaaf/games", key: "ncaaf-games" } as const',
     '// const NCAAF_NAV = { label: "NCAAF", href: "/ncaaf/games", key: "ncaaf-games" } as const',
     "test_the_two_ncaaf_nav_declarations_agree"),
]


def run(test: str) -> tuple[int, str]:
    p = subprocess.run(
        ["uv", "run", "pytest", SUITE, "-k", test, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cases = [c for c in CASES if not only or only in c[0]] or CASES
    backups = {p: p.read_text() for p in {c[1] for c in cases}}
    failures: list[str] = []

    try:
        for name, path, old, new, test in cases:
            src = backups[path]
            n = src.count(old)
            if n == 0:
                # ⚠️ A STALE ANCHOR IS A FAILURE, NOT A SKIP — an UNPROVEN clause reading as a quiet
                # one, and how a red proof reports a phantom pass (E11.24 #682).
                failures.append(f"{name}: PATCH ANCHOR NOT FOUND")
                print(f"⚠️  {name}: anchor not found")
                continue
            if n > 1:
                # ⚠️ A NON-UNIQUE ANCHOR lands the break on whichever occurrence comes first, which
                # can be a DIFFERENT symbol — that reports a FALSE VACUITY and invites weakening a
                # correct guard (E11.24 prediction_log).
                failures.append(f"{name}: ANCHOR APPEARS {n}× — the break could land on the wrong one")
                print(f"⚠️  {name}: anchor is not unique ({n} occurrences)")
                continue
            patched = src.replace(old, new, 1)
            if patched == src:
                failures.append(f"{name}: PATCH WAS A NO-OP")
                print(f"⚠️  {name}: patch did not change the file")
                continue
            path.write_text(patched)
            code, out = run(test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {name}  ->  {test}")
            if code == 0:
                failures.append(f"{name} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   ")[:1200])
    finally:
        for p, src in backups.items():
            p.write_text(src)
        print("\nrestored all files")

    if failures:
        print("\n❌ VACUOUS CLAUSES:\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(cases)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
