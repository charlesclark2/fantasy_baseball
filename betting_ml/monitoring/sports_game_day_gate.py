"""Game-day gate for the sports (NCAAF / NFL) dbt build schedules — NCAAF-P1.1.

WHY THIS EXISTS: football is not baseball. There is no game most days — NCAAF plays mainly
Saturdays (plus scattered Thu/Fri/Tue/Wed games) and NFL mainly Sun/Mon/Thu. Running the mart
rebuild every single day would burn box compute on days when nothing changed, so the schedules
fire daily during the season and this gate decides whether the run is actually warranted.

⭐ TWO DESIGN RULES, both learned the hard way in this repo:

1. **FAIL OPEN.** A missed rebuild leaves the marts stale and nothing says so — that is exactly
   the "silently rot" failure this whole story exists to kill. A redundant rebuild costs ~2 min of
   free DuckDB compute. So the gate RUNS unless it can POSITIVELY PROVE no game was played. An
   unreadable database, a missing table, a query error — all mean RUN, loudly.

2. **NO NETWORK IO IN A SCHEDULE EVALUATION.** This is evaluated by the Dagster daemon. An
   un-timed-out S3/DuckDB-over-network read on a daemon eval thread is the INC-32 wedge class,
   which took out every sensor mid-slate. So the gate reads ONLY the LOCAL DuckDB file the job
   itself materialized — a plain file read that cannot hang on a network. That the job writes the
   very data the next evaluation reads is deliberate: it makes the gate self-correcting.

⚠️ THE DEADLOCK THIS AVOIDS: "rebuild only when a game was played" read naively from a STALE mart
means the stale mart does not know about recent games, so it never rebuilds, so it stays stale
forever. Rule 3 in `decide_build` breaks it — if the mart's own latest game predates the day we
are asking about, the mart is behind and we rebuild regardless.

Lives in `betting_ml/` (not `pipeline/`) on purpose: fast-gate tests must never import `pipeline`,
which reads the dbt manifest at import time and crashes at COLLECTION when it is absent (E11.23).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta

from betting_ml.utils.game_day import current_game_date


@dataclass(frozen=True)
class GateDecision:
    """The gate's verdict. `should_run` is what the schedule acts on; `reason` is what it logs."""

    should_run: bool
    reason: str


def target_game_date(today: "date | None" = None) -> date:
    """The game day a build launched TODAY is meant to pick up — i.e. YESTERDAY.

    Games finish late; the upstream feeds (CFBD box/PBP, nflverse) land after the fact. A build
    firing this morning is rebuilding around what was played yesterday, so that is the day whose
    game-existence we test. `today` is injectable so this is unit-testable without freezing a clock.
    """
    return (today or current_game_date()) - timedelta(days=1)


def decide_build(
    target: date,
    game_dates: "set[date] | None",
    max_known_game_date: "date | None",
) -> GateDecision:
    """Pure decision — no IO, so the policy is testable in isolation.

    Args:
        target: the game date under test (normally yesterday, per `target_game_date`).
        game_dates: every game date the local mart knows about, or None when it could not be
            read at all. None means UNKNOWN, which is NOT the same as "no games".
        max_known_game_date: the latest game date the mart knows about (None if unknown/empty).
    """
    # 1. FAIL OPEN — we could not read the mart, so we cannot prove nothing happened.
    if game_dates is None:
        return GateDecision(
            True,
            "RUN (fail-open): could not read the local mart to check for games — "
            "rebuilding rather than risk leaving stale marts unnoticed.",
        )

    # 2. A game was played on the target date → rebuild to pick it up.
    if target in game_dates:
        return GateDecision(True, f"RUN: a game was played on {target.isoformat()}.")

    # 3. DEADLOCK BREAKER — the mart's own latest game predates the day we are asking about, so
    #    the mart is behind the world and cannot be trusted to say "no game". Rebuild.
    if max_known_game_date is None:
        return GateDecision(
            True,
            "RUN (fail-open): the local mart knows of no games at all — it is empty or "
            "never built.",
        )
    if max_known_game_date < target:
        return GateDecision(
            True,
            f"RUN: the mart's latest known game is {max_known_game_date.isoformat()}, which is "
            f"before {target.isoformat()} — the mart is behind, so its 'no game' answer is not "
            "trustworthy.",
        )

    # 4. Positively proven: the mart is current AND no game was played. Skip.
    return GateDecision(
        False,
        f"SKIP: no game was played on {target.isoformat()} (mart is current through "
        f"{max_known_game_date.isoformat()}). Nothing to rebuild.",
    )


def read_game_dates(duckdb_path: str, relation: str, date_column: str):
    """Read the distinct game dates from the LOCAL DuckDB the job materialized.

    Returns `(game_dates, max_game_date)`, or `(None, None)` on ANY failure — a missing file, a
    missing relation, a schema change, a corrupt DB. Every one of those is "unknown", and the
    caller turns unknown into RUN.

    ⚠️ Deliberately local-file-only — no S3, no httpfs, no network (see the module docstring).
    ⚠️ `date_column` is cast `::date` at the use-site: NCAAF stores a real DATE but NFL's
    `game_date` is an ISO VARCHAR (the INC-23 discipline — raw stays VARCHAR, the reader casts).
    """
    if not os.path.exists(duckdb_path):
        return None, None
    try:
        import duckdb

        con = duckdb.connect(duckdb_path, read_only=True)
        try:
            rows = con.execute(
                f"select distinct try_cast({date_column} as date) as d "
                f"from {relation} where {date_column} is not null"
            ).fetchall()
        finally:
            con.close()
    except Exception:
        # Intentionally broad: EVERY failure mode here means "unknown" → the caller fails open.
        return None, None

    dates = {r[0] for r in rows if r[0] is not None}
    if not dates:
        return set(), None
    return dates, max(dates)


def evaluate_gate(
    duckdb_path: str,
    relation: str,
    date_column: str,
    today: "date | None" = None,
) -> GateDecision:
    """Read the local mart and decide. The single entry point the schedules call."""
    target = target_game_date(today)
    game_dates, max_known = read_game_dates(duckdb_path, relation, date_column)
    return decide_build(target, game_dates, max_known)
