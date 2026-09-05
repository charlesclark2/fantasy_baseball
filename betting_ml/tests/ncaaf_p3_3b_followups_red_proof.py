#!/usr/bin/env python3
"""NCAAF-P3.3b FOLLOW-UPS RED PROOF — break each affordance, require its named clause to fail.

    uv run python betting_ml/tests/ncaaf_p3_3b_followups_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`).

WHY THESE IN PARTICULAR. Every clause in the suite this drives asserts that something ISN'T there —
no stale marker, no un-busted request, no env-var write, no IO at import. That is the single easiest
shape to write so it can never fail, and this repo has shipped it repeatedly without noticing by
reading the test. Two of these guards ALSO scan source, which adds the INC-38 hazard on top: prose
describing a defect can satisfy — or trip — a scan meant for code. The suite strips comments and
docstrings for exactly that reason, and these breaks are what prove the stripping did not also
strip the guard's teeth.

THE THREE CONTROLS: BASELINE-PASS (every clause green on unbroken source first, or a break proves
nothing), NOT-SELECTED (a stale test id makes pytest exit non-zero, which a naive check reads as
RED — the harness reporting its strongest result for a clause it never ran), and UNIQUE ANCHOR (a
first-occurrence replace against a repeated anchor lands elsewhere and reports a FALSE
"GREEN — VACUOUS", which reads as a finding and invites weakening a guard that was fine).

Restores every file from an in-memory backup in a `finally`. ⛔ Not `git checkout --`, which would
destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

WRITER = REPO / "scripts/write_ncaaf_serving_store.py"
LIVE = REPO / "frontend/e2e/specs/ncaaf-live-api.spec.ts"
INFO = REPO / "app/backend/build_info.py"
DEPLOY = REPO / "infrastructure/lambda/deploy.sh"
MAIN = REPO / "app/backend/main.py"
GUARDRAILS = REPO / "app/backend/services/cost_guardrails.py"

SUITE = "betting_ml/tests/test_ncaaf_p3_3b_followups.py"

#: (label, file, find, replace, test id)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── 1. the run report ────────────────────────────────────────────────────────────────────
    ("the run report goes silent on the vintage again",
     WRITER,
     '        "ratings_as_of": stamp["ratings_as_of"],',
     "",
     "test_the_run_report_carries_the_ratings_vintage"),

    ("a failed vintage read OMITS the key instead of reporting null",
     WRITER,
     '        stamp = {"ratings_as_of": None, "ratings_next_update": None}',
     "        stamp = {}",
     "test_the_report_reports_a_null_vintage_rather_than_omitting_the_key"),

    # ── 2. the @live suite ───────────────────────────────────────────────────────────────────
    # A plain read cannot tell "the server stopped sending X" from "the cache has not turned
    # over" — the two produced a byte-identical response on 2026-09-05 and cost a misdiagnosis.
    ("a @live request drops its cache-bust",
     LIVE,
     'await request.get(bust("/ncaaf/manifest"))',
     "await request.get(`${API}/ncaaf/manifest`)",
     "test_every_live_ncaaf_request_is_cache_busted"),

    ("@live stops reading the team payload at all",
     LIVE,
     'const res = await request.get(bust("/ncaaf/teams/68"))',
     'const res = await request.get(bust("/ncaaf/manifest"))',
     "test_the_live_suite_covers_the_team_payloads_stamp"),

    # ── 3. the build marker ──────────────────────────────────────────────────────────────────
    # ⛔ A real SHA in the tree is a marker that lies with authority: an unpackaged process would
    # report a commit it was not built from.
    ("a real SHA is committed into the repo copy of the marker",
     INFO,
     "BUILD_SHA: str = SENTINEL",
     'BUILD_SHA: str = "47f8b412b8ed31a2e8b4fb65ed8b4cad51e6c5ab"',
     "test_the_repo_copy_of_the_marker_holds_the_sentinel"),

    ("deploy.sh stamps the WORKING TREE instead of the package",
     DEPLOY,
     'cat > "$PACKAGE_DIR/app/backend/build_info.py"',
     "cat > app/backend/build_info.py",
     "test_deploy_stamps_the_package_and_never_the_working_tree"),

    # ⛔⛔ The E9.8-P2 landmine: `--environment` REPLACES the whole Variables map and this script
    # only calls `update-function-code`, so it cannot restore what it wiped.
    ("deploy.sh reaches for update-function-configuration",
     DEPLOY,
     'BUILD_SHA_VALUE="$(git rev-parse HEAD 2>/dev/null || echo unknown)"',
     'BUILD_SHA_VALUE="$(git rev-parse HEAD)"\n'
     'aws lambda update-function-configuration --environment "Variables={BUILD_SHA=$BUILD_SHA_VALUE}"',
     "test_the_marker_never_becomes_a_lambda_environment_variable"),

    ("the marker reads a file at import (paying into the cold-start budget)",
     INFO,
     'SENTINEL = "unpackaged"',
     'import pathlib\nSENTINEL = pathlib.Path("/tmp/sha").read_text()',
     "test_the_marker_costs_nothing_at_import"),

    ("/health stops reporting which build is answering",
     MAIN,
     'return {"status": "ok", "environment": _TARGET_ENV, "build": build_marker()}',
     'return {"status": "ok", "environment": _TARGET_ENV}',
     "test_health_serves_the_marker_additively"),

    # ⭐ THE ONE MOST LIKELY TO HAPPEN BY ACCIDENT: someone adds /health to the cost guardrails'
    # cache rules as an obvious saving, and the build marker silently starts reporting the
    # PREVIOUS build for 15 minutes — the exact confusion it was built to end.
    ("/health becomes shared-cacheable, so the marker can be served stale",
     GUARDRAILS,
     '    ("/ncaaf", 900, 3600),',
     '    ("/ncaaf", 900, 3600),\n    ("/health", 900, 3600),',
     "test_health_is_not_shared_cached_so_the_build_marker_cannot_go_stale"),
]


def run_one(test_id: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED"."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_id}", "-q", "--no-header",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=REPO, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    if "no tests ran" in out or "ERROR: not found" in out or "not found:" in out:
        return "NOT-SELECTED"
    return "PASSED" if r.returncode == 0 else "FAILED"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}

    print("baseline (every named clause, unbroken source) …")
    baseline = {t: run_one(t) for *_, t in CASES}
    bad = {t: v for t, v in baseline.items() if v != "PASSED"}
    if bad:
        for t, v in bad.items():
            print(f"🚨 baseline: {t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1
    print(f"  all {len(baseline)} green ✅\n")

    results = []
    try:
        for label, path, find, replace, test_id in CASES:
            original = backups[path]
            n = original.count(find)
            if n == 0:
                results.append((label, test_id, "ANCHOR-MISSING"))
                continue
            if n > 1:
                results.append((label, test_id, f"AMBIGUOUS-ANCHOR (x{n})"))
                continue
            patched = original.replace(find, replace, 1)
            assert patched != original, label
            path.write_text(patched)
            try:
                outcome = run_one(test_id)
            finally:
                path.write_text(original)
            results.append((label, test_id, {
                "PASSED": "GREEN — VACUOUS",
                "FAILED": "RED",
                "NOT-SELECTED": "NOT-SELECTED (the named clause does not exist)",
            }[outcome]))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = sum(1 for *_, s in results if s == "RED")
    for label, test_id, status in results:
        print(f"{'✅' if status == 'RED' else '🚨'} {label.ljust(width)}  →  {status}")
    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
