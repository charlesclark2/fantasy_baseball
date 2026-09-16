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

#: Re-exported from the module that OWNS it (`ncaab_season`), which imports nothing from
#: `sports_delta_freshness` and so cannot participate in the cycle described below. Existing
#: callers keep importing `SEASON_MONTHS` / `season_month_containment_holds` from here.
from betting_ml.monitoring.ncaab_season import (  # noqa: E402
    SEASON_MONTHS,
    season_month_containment_holds,
)

#: ⭐ ARMED 2026-09-15 AND THEREFORE NO LONGER HERE: `ncaab_schedules` and `ncaab_team_box`
#: now live in `sports_delta_freshness.REGISTRY`, because their writer is confirmed running —
#: the schedule's first AUTONOMOUS fire succeeded at 2026-09-15 14:00Z (every earlier run was
#: invoked by hand, which proves the JOB works and says nothing about the SCHEDULE).
#:
#: They are DEFINED there rather than imported from here, and that is forced rather than
#: stylistic: this module imports `SportsDeltaContract` FROM `sports_delta_freshness`, so a
#: module-level import back is a cycle — measured, it raises
#: `cannot import name ... from partially initialized module` whenever THIS module is imported
#: first, which is exactly what a fast-gate test does. `ARMED_IN_REGISTRY` below is names only
#: (plain strings, no import), so the two modules can still be cross-checked by a guard.
#:
#: What remains below is what is still UNARMED: the two paid odds tables, whose writer is the
#: operator's spend decision.
#:
#: Sized against the PROPOSED cadence in docs/ncaab_p0_credit_arithmetic.md §3. Each SLA is one
#: cadence plus a grace window that tolerates a late run and one deploy, but NOT a skipped cycle
#: — the distinction `classify` then splits into WARN (a missed cycle) and CRITICAL (dead feed).
DECLARED: tuple[SportsDeltaContract, ...] = (
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


# ── a CONSIDERED ABSENCE, recorded so nobody "fixes" it ──────────────────────────────────
#
# ⛔ `ncaab_team_crosswalk` HAS NO CONTRACT HERE, AND THAT IS A DECISION, NOT AN OMISSION.
#
# The obvious reading of NCAAB-P0's runtime gate is: "the crosswalk no longer escalates on a
# 404, so move the watching to a freshness SLA." That would be wrong, and INC-45 already paid
# for the lesson — do NOT put an INC-41 freshness SLA on a DELIBERATELY-STATIC artifact,
# because an SLA on something that should not advance pages daily on a healthy file, and a
# monitor that pages on a healthy state is one that gets muted.
#
# MEASURED 2026-09-14: hoopR publishes the crosswalk for exactly ONE season at a time (only
# `2026` existed; 2024, 2025 and 2027 were all 404). Between rolls NOTHING writes this table —
# legitimately, for weeks or months, on hoopR's schedule and not ours. Any lag threshold wide
# enough not to false-page across a roll is too wide to detect anything worth detecting.
#
# ⭐ WHAT WATCHES IT INSTEAD, and it is a better instrument for this failure: the question that
# actually matters is not "was the file fetched recently" but "can we resolve conference names
# for the season we are serving". `dim_ncaab_conference` answers that directly and per-row via
# `name_unresolved`, and a defunct conference keeps its history rather than disappearing. That
# is a CONTENT check at the point of use, which is strictly stronger than a fetch-time check —
# the same shape as the 7-day Byparr outage, where every liveness probe was green and only a
# staleness check on the LANDED DATA saw it.
#: The NCAAB contracts that ARE live, by name. Strings, deliberately — importing the objects
#: from `sports_delta_freshness` would re-create the cycle described above. A guard cross-checks
#: these against the real REGISTRY, so the two cannot drift apart silently.
ARMED_IN_REGISTRY: tuple[str, ...] = ("ncaab_schedules", "ncaab_team_box")


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
