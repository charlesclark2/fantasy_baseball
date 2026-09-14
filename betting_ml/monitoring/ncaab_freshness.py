"""NCAAB-P0 — the DECLARED freshness contracts for the NCAAB lake, and why they are not yet live.

⛔ THESE ARE DELIBERATELY **NOT** IN `sports_delta_freshness.REGISTRY` YET, AND THAT IS THE POINT.

That registry's own rule is that an entry is a CLAIM about a table's real commit behaviour, and
an unmeasured claim produces a permanent false page — it is exactly why INC-41 REJECTED
`feature_pregame_game_features_raw` from its own registry after measuring its only temporal
column at 40 hours stale on a healthy store. NCAAB has **no Dagster schedule**, because enabling
one is the operator's spend decision (see `docs/ncaab_p0_credit_arithmetic.md`). A table that
nothing writes cannot be stale; registering these today would page CRITICAL on every table,
every day, from the first deploy — and a monitor that is red before it is meaningful is a
monitor that gets muted before the season it exists to watch.

So the contracts are DECLARED here, sized against the cadence they will have, and REGISTERED in
the same change that turns their writer on. `registration_snippet()` prints exactly what to
paste, so enabling the schedule and arming its monitor are one action rather than two — the
second of which is the one everybody forgets (the `W7B_LAKEHOUSE_S3` documented-but-never-set
class, which this vertical inherits the lesson from rather than the bug).

⭐ ACTIVE-SEASON SEMANTICS. NCAAB runs November to early April, so a wall-clock SLA would page
all summer on a table that is correctly idle. These contracts carry `active_months`, which
counts lag only inside the season window — so an April final commit stays legitimately fresh
through October and starts ageing again on November 1. Idle by DECLARATION, never by a
suppressed check (the NCAAF-P1.2W mechanic, inherited).

TIER: this module DECIDES. It never pages, never raises, and imports no `pipeline` (E11.23), so
it is safe in the fast gate.
"""

from __future__ import annotations

from dataclasses import replace

from betting_ml.monitoring.sports_delta_freshness import SportsDeltaContract

#: The D-I season window, MONTH-granular. November through April; April is in because the title
#: game falls in its first week.
#:
#: ⚠️ THE RELATIONSHIP WITH `sources.in_season()` IS CONTAINMENT, NOT EQUALITY, and writing it
#: down is the point. The ingest layer's `in_season()` is DAY-granular (April 1-10, because the
#: season really does end mid-month); `active_months` cannot express a mid-month boundary at
#: all. That is the same shape as INC-41's hour-granularity windows being unable to express a
#: 30-minute grace — the coarser instrument must be the WIDER one, or it suppresses a check on
#: a day the finer one considers live.
#:
#: So the invariant is: every month in which `in_season()` is EVER true must appear here. The
#: converse is deliberately false — this window stays open for the back half of April, when
#: `in_season()` has already closed, which costs at most a few days of a contract ageing
#: against a season that has just ended. That direction is safe; the other direction would
#: silently blind the monitor during live play. `season_month_containment_holds()` asserts it,
#: and a guard test drives it, because two owners of one boundary is this repo's documented
#: seasonal-hole class (E9.48(c) / INC-37 / NCAAF-RF1).
SEASON_MONTHS: tuple[int, ...] = (11, 12, 1, 2, 3, 4)


def season_month_containment_holds() -> tuple[bool, tuple[int, ...]]:
    """Does `SEASON_MONTHS` cover every month the ingest layer ever calls in-season?

    Returns (ok, months_missing_from_SEASON_MONTHS). Imported lazily so this module stays
    import-cheap and free of a cycle.
    """
    from datetime import date

    from quant_sports_intel_models.basketball.ncaab.ingest.sources import in_season

    # 2027 is a non-leap year; every month is probed on days 1, 15 and 28 so a mid-month
    # boundary (April 10) cannot hide between probes.
    live = {m for m in range(1, 13)
            for d in (1, 15, 28) if in_season(date(2027, m, d))}
    missing = tuple(sorted(live - set(SEASON_MONTHS)))
    return (not missing), missing


#: Sized against the PROPOSED cadence in docs/ncaab_p0_credit_arithmetic.md §3. Each SLA is one
#: cadence plus a grace window that tolerates a late run and one deploy, but NOT a skipped cycle
#: — the distinction `classify` then splits into WARN (a missed cycle) and CRITICAL (dead feed).
DECLARED: tuple[SportsDeltaContract, ...] = (
    SportsDeltaContract(
        name="ncaab_schedules",
        sport="ncaab",
        source="schedules",
        tier="raw",
        # Daily writer. 36h tolerates a late run and one deploy window, not a skipped day.
        max_lag_hours=36.0,
        cadence="daily (proposed: sports_ncaab_ingest_schedule)",
        active_months=SEASON_MONTHS,
        why=("the game spine every NCAAB surface and model reads. Frozen, the slate silently "
             "stops advancing while every job still reports success — hoopR overwrites the "
             "current season's file in place, so a frozen mirror is indistinguishable from a "
             "quiet day in every signal except this one"),
        remediate=("run the ingest for the current season and READ THE RECEIPT: "
                   "`uv run python -m quant_sports_intel_models.basketball.ncaab.ingest.handler "
                   "--sources schedules`. It exits non-zero on an escalation rather than "
                   "swallowing, and refuses to overwrite a good partition with an empty one"),
    ),
    SportsDeltaContract(
        name="ncaab_team_box",
        sport="ncaab",
        source="team_box",
        tier="raw",
        max_lag_hours=36.0,
        cadence="daily (proposed: sports_ncaab_ingest_schedule)",
        active_months=SEASON_MONTHS,
        why=("the box lines the possession estimate — and therefore every tempo and efficiency "
             "figure — is computed from. Frozen, ratings keep serving off last week's games "
             "with no error anywhere"),
        remediate=("as ncaab_schedules, with `--sources team_box`. ⚠️ Before the season's first "
                   "tip the upstream file legitimately 404s and the ingest reports "
                   "`not published yet` — that is the expected pre-season state, which is why "
                   "this contract is active_months-gated and not wall-clock"),
    ),
    SportsDeltaContract(
        name="ncaab_odds_game_lines",
        sport="ncaab",
        source="odds_game_lines",
        tier="raw",
        # At the proposed 30-minute in-season cadence, 6h is ~12 missed cycles — deliberately
        # loose, because a single missed poll is not a defect and the capture is cheap to refire.
        max_lag_hours=6.0,
        cadence="every 30 min across the 16h US window, in season (PROPOSED — not yet enabled)",
        active_months=SEASON_MONTHS,
        why=("the market side of every model-vs-market surface. A forward capture is the only "
             "way to hold THIS week's line: recovering it later costs 10x through /historical "
             "and only works inside the vendor's retained window"),
        remediate=("check the Odds-API balance first (`x-requests-remaining` is stamped on every "
                   "captured row, so the lake itself answers it), then re-fire the capture"),
    ),
    SportsDeltaContract(
        name="ncaab_odds_futures",
        sport="ncaab",
        source="odds_futures",
        tier="raw",
        max_lag_hours=36.0,
        cadence="daily (PROPOSED — not yet enabled)",
        active_months=SEASON_MONTHS,
        why=("the title-futures board. 1 credit a call, so a whole season costs less than one "
             "historical Saturday — there is no budget reason for this to ever be stale"),
        remediate="re-fire the capture; confirm ODDS_API_KEY is set in the executing container",
    ),
)


def registration_snippet() -> str:
    """Exactly what to paste into `sports_delta_freshness.REGISTRY` at enablement.

    A copy-pasteable line rather than prose, because "also register the monitor" is the step
    that gets dropped, and a dropped monitor is invisible by construction.
    """
    names = ", ".join(c.name for c in DECLARED)
    return (
        "# In betting_ml/monitoring/sports_delta_freshness.py, extend REGISTRY with:\n"
        "#     from betting_ml.monitoring.ncaab_freshness import DECLARED as _NCAAB\n"
        "#     REGISTRY = (... existing ..., *_NCAAB)\n"
        f"# Arms: {names}.\n"
        "# ⚠️ Register ONLY the contracts whose writer you just enabled — a contract for a table\n"
        "#    nothing writes is a permanent false page, which is the whole reason these are not\n"
        "#    registered already."
    )


def for_enabled(*names: str) -> tuple[SportsDeltaContract, ...]:
    """The subset of DECLARED whose writers are actually on. Registering a table nothing writes
    is the failure mode this module exists to prevent, so the subset is explicit."""
    known = {c.name: c for c in DECLARED}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise KeyError(f"unknown NCAAB freshness contract(s) {unknown}; known: {sorted(known)}")
    return tuple(known[n] for n in names)


def proposed_but_unenabled() -> tuple[str, ...]:
    """The contracts still waiting on an operator enablement decision — i.e. all of them today.

    Exposed so the closeout and any future audit can ASK the code rather than trusting a doc
    sentence that will rot the moment the first schedule is turned on.
    """
    return tuple(c.name for c in DECLARED)
