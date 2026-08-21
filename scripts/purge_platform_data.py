#!/usr/bin/env python
"""Delete every roster we hold that was copied from one import platform, across ALL accounts.

⭐ WHY THIS EXISTS. Yahoo's API Access and Use Agreement §6 (Term and Termination):

    "As soon as practicable following any termination or expiration of this Agreement (and in no
     event more than ten (10) business days thereafter), Developer agrees to uninstall and delete
     from its computer systems and servers all copies of the Yahoo Materials and Yahoo Fantasy
     Information …"

Until this script there was no way to execute that. `DELETE /fantasy/import/yahoo/connection`
deletes ONE user's copies and is reachable only by that user, so on the day the Agreement ended the
obligation was simply unmeetable — the clause named a ten-business-day deadline against a mechanism
that did not exist. It is also what §14 ("Yahoo shall have the right, at any time, to conduct
audits") would need to be answered honestly.

⚠️ DRY RUN BY DEFAULT. It reports what it would delete and writes nothing; `--apply` is required to
delete. This destroys user data across the whole account base, and the one thing worse than being
unable to run it is running it by accident.

⛔ IT DELETES ROSTERS, NOT LEAGUES. Exactly the fields `dynamo.PLATFORM_ROSTER_FIELDS` names, via
`dynamo.purge_platform_league_data` — the SAME function a user's own disconnect calls, deliberately,
so there is one deletion implementation and not two that can drift (E9.61). A league's scoring
config, roster slots and team count survive; see that module's header for the line between the
platform's data and the user's own configuration, and read `docs/nf_c0_yahoo_clause_audit.md` §2
before assuming that line is settled — under a strict reading of §1.e it is not.

⚠️ THIS DOES NOT REVOKE ANYTHING AT YAHOO, and it does not drop the stored OAuth tokens. Revocation
is the user's own account setting (we cannot do it), and token disposal on termination is a separate
step — call it out in the runbook rather than bundling a second destructive action in here.

WHERE TO RUN: the LAPTOP. It needs only DynamoDB credentials for the users table.

    uv run python scripts/purge_platform_data.py --platform yahoo             # dry run
    uv run python scripts/purge_platform_data.py --platform yahoo --apply     # delete
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("purge_platform_data")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--platform",
        required=True,
        help="the import platform whose copied rosters to delete (e.g. yahoo, espn, sleeper)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually delete. Without it the script reports and writes nothing.",
    )
    args = ap.parse_args()

    from app.backend.services import dynamo

    platform = args.platform.strip().lower()
    mode = "DELETING" if args.apply else "DRY RUN — nothing will be written"
    logger.info("[%s] scanning the users table for %s-imported rosters…", mode, platform)

    holders = list(dynamo.iter_platform_league_holders(platform))
    if not holders:
        # ⚠️ Reported as a RESULT, not silence. "No accounts hold this platform's data" and "the
        # scan never ran" look identical in an empty log, and this is a script whose whole output
        # may end up quoted to a counterparty (NF1.7 (a)).
        logger.info("no account holds any %s-imported roster — nothing to delete", platform)
        return 0

    total_leagues = sum(n for _, n in holders)
    logger.info(
        "%d account(s) hold %d %s-imported league roster(s)", len(holders), total_leagues, platform
    )
    if not args.apply:
        for user_id, n in holders:
            logger.info("  would purge %d league(s) for user=%s", n, user_id)
        logger.info("DRY RUN complete — re-run with --apply to delete")
        return 0

    purged_users, purged_leagues, failed = 0, 0, []
    for user_id, _ in holders:
        try:
            result = dynamo.purge_platform_league_data(user_id, platform)
        except Exception:  # noqa: BLE001
            # One unreachable account must not abandon the rest — a partial purge that stops at the
            # first error leaves the obligation unmet for every account after it, and silently.
            logger.exception("could not purge user=%s", user_id)
            failed.append(user_id)
            continue
        purged_users += 1
        purged_leagues += int(result.get("leagues_purged") or 0)

    logger.info(
        "[METRIC] platform_purge_users=%d platform_purge_leagues=%d platform_purge_failed=%d",
        purged_users, purged_leagues, len(failed),
    )
    if failed:
        # A NON-ZERO EXIT, because §6 is a deadline: an operator who reads "done" over a partial
        # purge has no reason to come back, and the accounts that failed stay holding the data.
        logger.error("%d account(s) FAILED and still hold %s data: %s", len(failed), platform, failed)
        return 1
    logger.info("every %s-imported roster has been deleted", platform)
    return 0


if __name__ == "__main__":
    sys.exit(main())
