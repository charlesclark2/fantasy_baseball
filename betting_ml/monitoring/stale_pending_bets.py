"""stale_pending_bets.py — INC-38 stuck-bet page classifier.

WHY THIS EXISTS (INC-38, 2026-08-02):
    A user bet settles only when its game shows up FINAL with scores. Every settlement skip is
    written as the benign "game not final yet" case — which is correct for a game in progress and
    catastrophically wrong for a game whose Final will never arrive. On 2026-07-31 the
    month-boundary schedule hole (the INC-37 lookback sibling) froze 14 of 15 games non-final in
    stg_statsapi_games; three bets on two of them sat PENDING with no error, no ALERT, and no
    self-heal. The operator noticed, two days later, by looking at the bet log.

    This is the E9.48 permanent-wrong-state class: a "latest event wins" pipeline turns one missed
    event into a state that is wrong FOREVER, and a freshness check cannot see it because the
    SOURCE is fresh — it is the DERIVED state that is stuck.

    settle_user_bets.py now emits `[METRIC] stale_pending_bets=<n|-1>` on every pass; this module
    turns that line into a paging decision and `_run_settlement` calls send_alert on it. The
    settle op's own tier is UNCHANGED (WARN — settlement is off the prediction path); this only
    makes a real stuck bet visible instead of silent.

    Lives in betting_ml/ (not pipeline/) so the fast gate can import it: `pipeline/__init__.py`
    reads the dbt manifest, which is absent in CI, so a fast-gate test importing `pipeline` would
    crash at COLLECTION rather than skip (E11.23).

THREE-VALUED, like spine_horizon. `0` = no stuck bets. `n > 0` = that many bets whose game
first-pitched more than STALE_AFTER_HOURS ago are still unsettled (page). `-1` = the check could
not be evaluated (the DuckDB read raised) — NOT a pass: a guard whose evaluation failed must never
be scored healthy (the NF1.7 (a) lesson — an anchor that fails to fit makes its assertion
vacuously true). An ABSENT metric line is treated like `-1` but reported at WARN, because the
likeliest cause is a settle pass that died early rather than a real stuck bet.

WHY 24h AND NOT SOONER: a 9-inning game runs ~3h, extras and rain delays stretch that, and the
settle passes are periodic. A game that first-pitched a full day ago and still has no Final is not
"running long" — it is a data defect. Anything tighter would page on the ordinary evening slate.
"""

from __future__ import annotations

METRIC_PREFIX = "[METRIC] stale_pending_bets="

NONE_STALE = 0
UNKNOWN = -1

# A pending bet is only counted stale once its game first-pitched this long ago.
STALE_AFTER_HOURS = 24


def parse_stale_pending_bets(stdout: str) -> int | None:
    """Return the LAST `stale_pending_bets` value in `stdout`, or None if never emitted."""
    value: int | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith(METRIC_PREFIX):
            continue
        try:
            value = int(line[len(METRIC_PREFIX):].strip())
        except ValueError:
            continue
    return value


def classify(value: int | None) -> tuple[str | None, str]:
    """PURE. Map a parsed metric value to (severity, message). severity None = do not page."""
    if value == NONE_STALE:
        return None, "No pending bet is older than its game's final."
    if value is not None and value > 0:
        return "CRITICAL", (
            f"{value} user bet(s) are still PENDING on games that first-pitched more than "
            f"{STALE_AFTER_HOURS}h ago. A bet only settles when its game reads FINAL with scores, "
            "so this means the game's Final never arrived in our data and the bet will NEVER "
            "self-heal (INC-38). Most likely cause: the month-boundary schedule hole — a game "
            "that first-pitched after 00:00 UTC on the 1st is not covered by any capture of the "
            "NEW month, so it stays frozen non-final in stg_statsapi_games. Remediate: re-run "
            "`ingest_statsapi.py schedule --start-date <prior-month-01> --lookback-days 3 "
            "--lookahead-days 3`, rebuild the W3pre flatten, then re-run settle_user_bets.py. "
            "Check that BOTH schedule callers still pass --lookback-days (the daily one alone is "
            "clobbered by the intraday tick's overwrite of the shared dt= partition)."
        )
    if value == UNKNOWN:
        return "WARN", (
            "The stale-pending-bet check could not be evaluated (the game-date read raised). "
            "Whether any bet is stuck is UNVERIFIED for this pass — treat it as unknown, not "
            "healthy (INC-38). Check the step log for the underlying DuckDB/S3 error."
        )
    return "WARN", (
        "The settle pass emitted no stale_pending_bets metric — whether any bet is stuck is "
        "UNVERIFIED for this pass (INC-38). Expected if the pass exited before the check "
        "(scan/lakehouse failure); otherwise the script did not reach it."
    )
