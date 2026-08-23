#!/usr/bin/env python3
"""NF-DTB-1 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_dtb_1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`).

WHY IT EXISTS. `test_nf_dtb_1_quota_refusal.py` is mostly SOURCE INSPECTION and COPY SCREENING, and
Half B's contribution is a set of COPY PINS — precisely the shape that reads as coverage while
proving nothing. NF-INJ1-C's lesson is the one this story was handed: *a constant whose only guard
reads a DIFFERENT constant is unpinned and looks pinned.* The only way to know a pin is real is to
retire the string it names and watch the clause go red.

The four disciplines this harness carries, each learned from a run that lied:
  · the anchor must EXIST (a missing one is a failure, never a skip) — E11.24 #682;
  · the anchor must be UNIQUE, or `replace(..., 1)` patches the wrong occurrence and reports a sound
    guard as vacuous — the dangerous direction, because it invites weakening a guard that is fine;
  · the mutation must MOVE THE ASSERTED PREDICATE (`gone` below), or a break that lands on disk
    without changing what the clause reads comes back GREEN for the wrong reason — E11.24 #815;
  · stale backups are restored AT START-UP, because an in-memory `finally` cannot run if the process
    is killed (a `| head` delivers SIGPIPE mid-mutation) and would otherwise leave deliberately
    broken source on disk — E11.26.

⛔ Deliberately not `git checkout --`: that destroys uncommitted work in the files it patches.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = REPO / "frontend/lib/api.ts"
ENT = REPO / "frontend/lib/entitlements.ts"
EDITOR = REPO / "frontend/components/fantasy/league-settings-editor.tsx"
IMPORTER = REPO / "frontend/components/fantasy/league-import.tsx"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
ROUTER = REPO / "app/backend/routers/fantasy.py"
SUITE = "betting_ml/tests/test_nf_dtb_1_quota_refusal.py"

#: (label, file, old, new, token-that-must-be-GONE-after-the-patch, clause)
CASES = [
    # ── the shipped defect itself, at EACH of the two throw sites ────────────────────────────────
    # ⭐ TWO CASES, NOT ONE, AND THAT IS THE POINT. A clause written as "an ApiError appears
    # somewhere in api.ts" passes with either site left un-migrated — and `cdnFetch` is the one a
    # future public surface reaches for. The clause is written as "no BARE throw survives", so each
    # site has to be able to turn it red on its own.
    ("apiFetch discards res.status (THE shipped defect)", API,
     "    throw new AuthError('Unauthorized')\n"
     "  }\n"
     "  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))",
     "    throw new AuthError('Unauthorized')\n"
     "  }\n"
     "  if (!res.ok) throw new Error(await errorMessage(res))",
     None,
     "test_every_failed_response_throws_an_error_carrying_its_status"),

    ("cdnFetch discards res.status (the OTHER throw site)", API,
     "  const res = await fetch(path, { headers: { Accept: 'application/json' } })\n"
     "  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))",
     "  const res = await fetch(path, { headers: { Accept: 'application/json' } })\n"
     "  if (!res.ok) throw new Error(await errorMessage(res))",
     None,
     "test_every_failed_response_throws_an_error_carrying_its_status"),

    ("ApiError stops subclassing Error (breaks every existing caller)", API,
     "export class ApiError extends Error {",
     "export class ApiError {",
     "export class ApiError extends Error",
     "test_the_new_error_type_is_additive_so_no_existing_caller_changed_meaning"),

    ("ApiError rewrites the server's message", API,
     "    super(message)",
     "    super(`API error ${status}`)",
     "super(message)",
     "test_the_new_error_type_is_additive_so_no_existing_caller_changed_meaning"),

    ("the 409 reading drifts off the status the server sends", ENT,
     "  return apiErrorStatus(e) === 409\n",
     "  return apiErrorStatus(e) === 402\n",
     "apiErrorStatus(e) === 409",
     "test_the_status_is_interpreted_at_the_call_site_not_in_a_shared_lookup"),

    # ── the two create surfaces, one clause each ─────────────────────────────────────────────────
    ("the EDITOR stops distinguishing a limit from a fault", EDITOR,
     "  const quotaRefused = saveLeague.isError && isLeagueQuotaRefusal(saveLeague.error)",
     "  const quotaRefused = false",
     "isLeagueQuotaRefusal(saveLeague.error)",
     "test_each_create_surface_separates_a_quota_refusal_from_a_save_fault[league-settings-editor.tsx]"),

    ("the IMPORTER stops distinguishing a limit from a fault", IMPORTER,
     "      if (isLeagueQuotaRefusal(e)) setQuotaRefused(true)\n      else setError(errorText(e))",
     "      setError(errorText(e))",
     "isLeagueQuotaRefusal(e)",
     "test_each_create_surface_separates_a_quota_refusal_from_a_save_fault[league-import.tsx]"),

    ("the EDITOR reuses the PRE-EMPTIVE wording for a refusal that already happened", EDITOR,
     "              detail={quotaRefused ? LEAGUE_QUOTA_REFUSED_DETAIL : LEAGUE_QUOTA_REACHED_DETAIL}",
     "              detail={LEAGUE_QUOTA_REACHED_DETAIL}",
     "quotaRefused ? LEAGUE_QUOTA_REFUSED_DETAIL",
     "test_each_create_surface_separates_a_quota_refusal_from_a_save_fault[league-settings-editor.tsx]"),

    # ── the copy ─────────────────────────────────────────────────────────────────────────────────
    ("the refusal stops saying the save did not land", COPY,
     '  "Nothing was saved and your settings are still on screen. A free account keeps one '
     'personalized league,',
     '  "A free account keeps one personalized league,',
     "Nothing was saved and your settings are still on screen",
     "test_the_refusal_says_nothing_was_saved_and_carries_no_overclaim"),

    ("the refusal acquires an overclaim", COPY,
     '  "Nothing was saved and your settings are still on screen.',
     '  "Nothing was saved and your settings are still on screen. Members always right about this.',
     None,
     "test_the_refusal_says_nothing_was_saved_and_carries_no_overclaim"),

    # ── the backend the client now branches on ───────────────────────────────────────────────────
    # ⭐ THE COUPLING CLAUSE. The client reads 409; a router that answered 400 for the cap would
    # un-fix the whole story with no browser test going red, because the generic line is a perfectly
    # valid rendering of a 400.
    ("the router answers the cap with the GENERIC 400", ROUTER,
     '        if str(e) == "too_many_leagues":',
     '        if False:',
     'if str(e) == "too_many_leagues":',
     "test_the_backend_answers_the_cap_with_409_not_the_generic_400"),
]

#: Where the on-disk copies live while a mutation is applied — inside the repo so it is obvious and
#: greppable; removed on a clean exit.
_BACKUP_DIR = REPO / ".nf_dtb_1_red_proof_backup"


def _slug(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("/", "__")


def _restore_stale_backups() -> None:
    """⚠️ FIRST, BEFORE ANYTHING ELSE. A surviving backup dir means the previous run was killed
    mid-mutation and the file on disk is the DELIBERATELY BROKEN version."""
    if not _BACKUP_DIR.exists():
        return
    restored = []
    for saved in sorted(_BACKUP_DIR.iterdir()):
        target = REPO / saved.name.replace("__", "/")
        if target.exists() and target.read_text() != saved.read_text():
            target.write_text(saved.read_text())
            restored.append(str(target.relative_to(REPO)))
    shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
    if restored:
        print("⚠️  a previous run was killed mid-mutation; restored deliberately-broken source in:")
        for f in restored:
            print(f"     {f}")
        print()


def run(test_name: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-800:]


def main() -> int:
    _restore_stale_backups()
    cases = list(CASES)
    files = {c[1] for c in cases}
    backups = {p: p.read_text() for p in files}
    _BACKUP_DIR.mkdir(exist_ok=True)
    for path, src in backups.items():
        (_BACKUP_DIR / _slug(path)).write_text(src)

    failures: list[str] = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for label, path, old, new, gone, test in cases:
            src = backups[path]
            if old not in src:
                failures.append(f"{label}: PATCH ANCHOR NOT FOUND in {path.name}")
                print(f"⚠️  ANCHOR MISSING  {label}  ({path.name})")
                continue
            if src.count(old) != 1:
                failures.append(f"{label}: ANCHOR IS NOT UNIQUE ({src.count(old)}×) in {path.name}")
                print(f"⚠️  ANCHOR AMBIGUOUS  {label}  ({path.name})")
                continue
            patched = src.replace(old, new, 1)
            if patched == src:
                failures.append(f"{label}: the replacement is a no-op")
                print(f"⚠️  NO-OP MUTATION  {label}")
                continue
            if gone is not None and gone in patched:
                failures.append(f"{label}: the mutation left {gone!r} in place")
                print(f"⚠️  MUTATION DID NOT BITE  {label}")
                continue
            path.write_text(patched)
            code, out = run(test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {label}  ->  {test}")
            if code == 0:
                failures.append(f"{label} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
        print("\nrestored all files")

    if failures:
        print(f"\n❌ {len(failures)} VACUOUS OR MIS-LANDED CLAUSE(S):\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(cases)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
