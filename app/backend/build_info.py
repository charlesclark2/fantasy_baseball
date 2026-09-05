"""Which BUILD of this Lambda is answering — stamped at package time by `deploy.sh`.

⭐ WHY THIS EXISTS, AND IT IS A MEASURED COST RATHER THAN A NICETY. The API Lambda has NO CD: it
ships only via a manual `infrastructure/lambda/deploy.sh`, which packages the CURRENT WORKING TREE
(`cp -r app/backend …`) with no branch check and no ref pin. So "is the deployed build the one I
think it is?" has, until now, been answerable only by curling a FEATURE and inferring backwards —
and on 2026-09-05 that inference was wrong: a single read of a `/ncaaf/*` route (CDN-cached at
`s-maxage=900, stale-while-revalidate=3600`) showed a field missing, which read as "the deploy did
not take" when the deploy was fine and the cache had simply not turned over. Isolating it took a
direct S3 read of the served blob to prove the writer had produced the field. One request against
this marker answers it instead.

G100-C0-MFA recorded the same lesson once already ("a `guard_version` claim marker beats 'the PR
merged' for an API-Lambda change — no CD there, so a merged PR is NOT a deployed build"). This is
its second instance, which is why it is now a permanent affordance rather than a per-story one.

══ HOW IT IS SET, AND THE LANDMINE IT DELIBERATELY AVOIDS ══════════════════════════════════════

⛔ NOT AN ENVIRONMENT VARIABLE. Setting one would require `aws lambda update-function-configuration
--environment`, which REPLACES the whole Variables map — and `deploy.sh` only ever calls
`update-function-code`, so it would not restore what it wiped. E9.8-P2 measured that failure on the
day money started moving (a single forgotten read wipes every var: the Stripe keys, the Cognito
ids, the store names). A build marker is not worth a class of outage that severe.

⇒ INSTEAD, `deploy.sh` REWRITES THIS FILE INSIDE THE PACKAGE DIRECTORY ONLY, never in the working
tree. The committed value below is therefore the honest answer for any process that was not built
by `deploy.sh` — a local `uvicorn`, a test run, a developer's laptop — and a guard asserts the
working-tree copy still holds the sentinel, so a stray real SHA cannot be committed by accident.

⚡ ZERO COLD-START COST: a module-level string literal, no file read, no import of anything. The
PERF story measured this Lambda's init as I/O-bound on unpacking a 57 MB package, so a marker that
opened a file at import would be paying into exactly the wrong budget.
"""

#: The commit `deploy.sh` packaged, or `SENTINEL` when this process was not packaged by it.
#: ⛔ Must stay the sentinel in the repository — `deploy.sh` overwrites the PACKAGED copy.
SENTINEL = "unpackaged"

BUILD_SHA: str = SENTINEL
#: UTC ISO-8601 instant the package was built, or None when unpackaged.
BUILT_AT: str | None = None


def build_marker() -> dict[str, str | None]:
    """What `/health` reports. `packaged` is the question an operator is actually asking.

    ⚠️ IT NEVER GUESSES. An unpackaged process reports the sentinel and `packaged: false` rather
    than reaching for `git rev-parse` — a marker that could report a SHA the running code was not
    built from would be worse than no marker, because it reads as authoritative (NF1.7(a)).
    """
    return {"sha": BUILD_SHA, "built_at": BUILT_AT, "packaged": BUILD_SHA != SENTINEL}
