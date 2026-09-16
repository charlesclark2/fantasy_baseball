"""NF-WK-RC1 — publish ONE completed week's realized stat lines as a served artifact.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY AN ARTIFACT RATHER THAN A REQUEST-TIME LAKE READ
═══════════════════════════════════════════════════════════════════════════════════════════════════

The recap endpoints need realized stat lines. Reading the NFL Delta lake from the API Lambda would
be NEW capability on a request path — `services/lakehouse_read.py` points at the MLB PARQUET
lakehouse, not `credence-sports-lakehouse`, so this would mean the `delta` extension plus a new IAM
grant plus DuckDB inside a request. E5.10 is the record of what that costs: two stacked
silent-failure modes (an empty `$HOME` breaking `INSTALL httpfs`, and a bucket-level `ListBucket`
the role had never been granted) that both presented identically as `degraded: []`.

So the week is published ONCE as a blob, exactly as the weekly projection already is, and the
endpoints read JSON. One shared artifact per season-week, identical for every league.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE COMPLETENESS GATE IS A COUNT, NOT A CLOCK
───────────────────────────────────────────────────────────────────────────────────────────────────

A week is FINAL when the realized line carries as many distinct `game_id`s as the schedule says the
week has. Measured at node 1: week 1 of 2026 reached 32/32 teams and 16/16 games about 23 hours
after its Monday-night game ended, which matches the inventory's "~24h in-season".

⛔ A CLOCK RULE IS WRONG IN THE ONE CASE THAT MATTERS. "Tuesday morning" calls a 15/16 week FINAL the
moment a game is postponed or flexed, silently, and a recap that renders a half-played week as final
is the dangerous default the spec names. The count is derived from TWO INDEPENDENT SOURCES, so it
can only ever describe the data in hand (the NF-K1 direction).

⚠️ The gate does not REFUSE a partial week — it LABELS it. A user watching Sunday evening is
entitled to see what has happened so far; what they are not entitled to is a partial total presented
as a final one.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.backend.services import realized_stat_fields as R
from app.backend.services import weekly_recap as W

log = logging.getLogger(__name__)

#: ⭐ THE KEY SCHEME IS OWNED BY `app/backend/models/nfl_recap.py` AND IMPORTED HERE, never
#: duplicated: this module pulls pandas through the lake read, and the API Lambda bundles neither
#: pandas nor `quant_sports_intel_models`. Two copies of a key scheme is the "one logical thing,
#: many owners" shape that goes wrong the first time one side is edited.
from app.backend.models.nfl_recap import realized_manifest_key, realized_players_key  # noqa: E402


#: Every lake column the artifact must carry: the scorer's realized sources, the identity columns,
#: the source's own PPR, and whatever the explained/unexplained split needs. DERIVED — adding a
#: term to either map widens this automatically, so a column the reader silently lacked (which is
#: how the split shipped as a no-op once) cannot recur.
def required_columns() -> tuple[str, ...]:
    return tuple(sorted(
        set(R.REALIZED_STAT_COLUMNS)
        | set(R.REALIZED_KEY_COLUMNS)
        | {R.REALIZED_PPR_COLUMN}
        | set(W.EXPLANATION_COLUMNS)
    ))


def completeness(realized_games: int, scheduled_games: int) -> str:
    """`final` | `partial` | `not_started` — see the header for why this is a count."""
    if scheduled_games <= 0 or realized_games <= 0:
        return "not_started"
    return "final" if realized_games >= scheduled_games else "partial"


def build(season: int, week: int, *, q, delta) -> dict:
    """Read one week from the lake and return `{manifest, players}` ready to publish.

    `q` / `delta` are injected (the `query_lake` pair) so this is testable without a lake and so the
    module carries no import-time connection — the fast gate must never need credentials.
    """
    cols = ", ".join(required_columns())
    players = q(f"""
        select {cols}
        from {delta('stats_player_week')}
        where season = {int(season)} and week = {int(week)} and season_type = 'REG'
    """).to_dict("records")

    sched = q(f"""
        select count(*) as n
        from {delta('schedules')}
        where season = {int(season)} and week = {int(week)} and game_type = 'REG'
    """)
    scheduled = int(sched["n"].iloc[0]) if len(sched) else 0
    realized_games = len({str(p.get("game_id")) for p in players if p.get("game_id")})
    state = completeness(realized_games, scheduled)

    manifest = {
        "season": int(season),
        "week": int(week),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "completeness": state,
        "realized_games": realized_games,
        "scheduled_games": scheduled,
        "n_players": len(players),
        "n_teams": len({str(p.get("team")) for p in players if p.get("team")}),
        # ⭐ SERVED, not assumed: a consumer can tell whether the artifact it holds carries the
        # columns its scorer needs, rather than discovering a missing one as a silent zero.
        "columns": list(required_columns()),
        "source_table": R.REALIZED_SOURCE_TABLE,
    }
    log.info("[realized] %s wk%s: %s (%s/%s games, %s players)",
             season, week, state, realized_games, scheduled, len(players))
    return {"manifest": manifest, "players": players}


def publish(built: dict, *, s3, bucket: str, prefix: str = "fantasy/nfl") -> dict:
    """Write the artifact. RAISES on a failed write — a publish that reports success while shipping
    nothing is the NF-FRESH1 failure this repo has already paid for once."""
    season, week = built["manifest"]["season"], built["manifest"]["week"]
    for key, body in (
        (realized_players_key(season, week), {"players": built["players"],
                                              "generated_at": built["manifest"]["generated_at"]}),
        (realized_manifest_key(season, week), built["manifest"]),
    ):
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{key}",
                      Body=json.dumps(body, default=str), ContentType="application/json")
    return {"published": [realized_players_key(season, week),
                          realized_manifest_key(season, week)],
            "completeness": built["manifest"]["completeness"]}
