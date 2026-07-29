"""E9.48 — injury / IL status health classification (PURE logic, no IO).

WHY THIS EXISTS
    On 2026-07-29 the player pages were serving a WRONG IL status for 62 of the 187
    players flagged as currently on the Injured List — Jesús Luzardo showed "On IL
    since 2024-06-19" while starting for PHI five days earlier. A wrong status is a
    TRUST failure: worse than no status at all.

    The mechanism is structural, not a one-off. `feature_pregame_injury_status` calls
    an interval CURRENT iff no later classified event exists, so a single MISSED
    clearing event pins a player as injured FOREVER — and there were three ways to
    miss one (bare "activated" text, a return via a roster move, and a transaction
    feed with a hard Nov–Feb hole every year). See the E9.48 block in
    dbt/models/staging/statsapi/stg_statsapi_player_injury_status.sql.

    Because the failure is SILENT — no error, no empty result, just a stale boolean —
    it can only be caught by asserting on the data. That is what this module does.

WHAT IT CHECKS (two independent signals; both must hold)
    1. FEED FRESHNESS — the newest roster-transaction event vs the current baseball
       day. MLB posts roster moves essentially every in-season day, so a multi-day
       gap means the ingest stopped and every status is frozen at that date.
       ⚠️ This intentionally fires during the OFF-SEASON too: ingest_transactions.py
       runs on a 7-day lookback from the in-season daily job, so Nov–Feb is a real
       hole in the feed (that hole is what stranded Luzardo). Making it visible is
       the point; the guard is ALERT-tier so it informs without blocking.
    2. IL PLAUSIBILITY — the correctness signature itself: a player reported as
       CURRENTLY on the IL who has since APPEARED IN AN MLB GAME. Post-fix this is
       exactly 0 and it is text-independent, so it detects a regression no matter how
       the Stats API rewords its descriptions.

TIER: ALERT-loud-but-continue (E11.7). The IL badge is a profile adornment, not the
    serving path, so a stale feed must not HALT the daily job — but it must never
    pass silently either. `--strict` / INJURY_STATUS_STRICT=1 promotes to HALT.

PURE by design: stdlib only, no duckdb / boto3 / pandas and no `pipeline` import, so
    it is importable from the fast gate (CLAUDE.md fast-gate hygiene rule).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# A feed gap wider than this many days means the ingest stopped. MLB posts roster
# moves on essentially every in-season day (the observed max in-season gap in the
# 2021-2026 history is well under this), so 4 days absorbs the daily-job cadence
# plus a quiet stretch without false-firing.
MAX_FEED_LAG_DAYS = 4

# The plausibility check is a CORRECTNESS assertion, not a rate: post-E9.48 the count
# is 0 by construction (an appearance truncates the injured interval). Any non-zero
# value means the reconciliation stopped being applied.
MAX_IMPLAUSIBLE_IL = 0

OK = "OK"
STALE = "STALE"
IMPLAUSIBLE = "IMPLAUSIBLE"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Check:
    """One guard verdict. `ok` is the only thing callers gate on."""

    name: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == OK


def classify_feed_freshness(
    latest_event_date: date | None,
    asof: date,
    max_lag_days: int = MAX_FEED_LAG_DAYS,
) -> Check:
    """Is the roster-transaction feed still being written?

    `latest_event_date` is max(coalesce(effective_date, transaction_date)) over the
    transaction staging model. A missing value is UNKNOWN, never a silent OK — an
    empty read is the classic silent-failure shape (E9.26b).
    """
    if latest_event_date is None:
        return Check(
            "feed_freshness",
            UNKNOWN,
            "no roster transactions found at all — the feed read returned nothing",
        )
    lag = (asof - latest_event_date).days
    if lag > max_lag_days:
        return Check(
            "feed_freshness",
            STALE,
            f"newest roster transaction is {latest_event_date} — {lag}d old "
            f"(limit {max_lag_days}d). Every IL status is frozen at that date; "
            f"players activated since still show on the IL.",
        )
    return Check(
        "feed_freshness",
        OK,
        f"newest roster transaction {latest_event_date} ({lag}d old, limit {max_lag_days}d)",
    )


def classify_il_plausibility(
    current_il_count: int,
    played_since_il_start: int,
    max_implausible: int = MAX_IMPLAUSIBLE_IL,
) -> Check:
    """Do any CURRENTLY-flagged-IL players have an MLB appearance after il_since?

    This is the E9.48 bug signature, stated directly. It reads no description text,
    so it survives any Stats API wording change.
    """
    if current_il_count == 0:
        # Not an error in the abstract, but a whole-league zero mid-season means the
        # chain produced nothing — report it rather than calling an empty set healthy.
        return Check(
            "il_plausibility",
            UNKNOWN,
            "zero players are flagged on the IL — the injury chain produced no current rows",
        )
    if played_since_il_start > max_implausible:
        return Check(
            "il_plausibility",
            IMPLAUSIBLE,
            f"{played_since_il_start} of {current_il_count} players flagged CURRENTLY on "
            f"the IL have played an MLB game since their il_since date "
            f"(limit {max_implausible}). The E9.48 clearing/reconciliation logic in "
            f"stg_statsapi_player_injury_status is not being applied.",
        )
    return Check(
        "il_plausibility",
        OK,
        f"{current_il_count} players flagged on the IL, {played_since_il_start} of them "
        f"with a later appearance (limit {max_implausible})",
    )


def summarize(checks: list[Check]) -> tuple[bool, str]:
    """(all_ok, one-line banner). The banner names every failing check."""
    bad = [c for c in checks if not c.ok]
    if not bad:
        return True, "injury/IL status healthy: " + "; ".join(c.detail for c in checks)
    return False, "injury/IL status " + "; ".join(f"{c.name}={c.status} ({c.detail})" for c in bad)
