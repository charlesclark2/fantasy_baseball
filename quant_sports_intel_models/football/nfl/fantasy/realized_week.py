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

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ PUBLISHING THE SAME WEEK TWICE IS A DECISION, NOT A RETRY (NF-WK-RC1 ①, 2026-09-16)
───────────────────────────────────────────────────────────────────────────────────────────────────

The moment this runs on a recurring cadence rather than by hand, the same week gets built again the
next day — so "what does a DIFFERENCE mean?" stops being hypothetical. nflverse restates played
weeks (a stat correction lands days later), and the answer is already ruled: `weekly_recap_store`
holds the identical question for the matchup capture and its ruling is that **the stored record
keeps serving and the restatement is a NAMED EVENT, never a silent overwrite** — "never a number
that changes underneath a reader with no explanation".

So this module classifies rather than PUTs, and the classification is a PURE function
(`publish_decision`) so it is testable without S3:

  * nothing published            → `create`
  * identical content            → `unchanged`   (no write at all — a routine re-run is silent)
  * published PARTIAL, now FINAL → `upgrade`     (an upgrade is not a restatement; overwrite)
  * published FINAL, now PARTIAL → `refuse_downgrade` (a mid-week hand-run cannot clobber a final)
  * published FINAL, content moved → `restate`   (⛔ the served keys are UNTOUCHED; the new build is
                                    parked at a revision key and the caller is handed an event)
  * published FINAL, no hash recorded → `backfill_hash` (the one-time transition for a week
                                    published before this machinery existed — overwritten ONCE and
                                    logged under its own name, because "we could not compare" must
                                    never be silently reported as "unchanged" (NF1.7(a)))

⭐ THE HASH COVERS THE PLAYER ROWS ONLY. `generated_at` moves on every build, so hashing the whole
blob would classify every routine re-run as a restatement — an event stream that fires on nothing is
ignored inside a week (the muted-monitor pattern, and the same reason `_VOLATILE_FIELDS` exists in
the store). Rows are sorted to a canonical order first, because DuckDB does not promise one and an
ordering difference is not a content difference.
"""

from __future__ import annotations

import hashlib
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


#: The canonical row order. DuckDB promises no ordering, and an ordering difference is not a
#: content difference — without this every rebuild would hash differently and every routine re-run
#: would classify as a restatement.
_ORDER_KEYS: tuple[str, ...] = ("game_id", "player_id")


def canonical_rows(players: list[dict]) -> list[dict]:
    """The week's rows in a stable order, so the same lake content always hashes the same."""
    return sorted(players, key=lambda r: tuple(str(r.get(k) or "") for k in _ORDER_KEYS))


def content_hash(players: list[dict]) -> str:
    """A sha256 over the ROWS ONLY — never the manifest, whose `generated_at` moves every build."""
    return hashlib.sha256(
        json.dumps(canonical_rows(players), sort_keys=True, default=str).encode()
    ).hexdigest()


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
    players = canonical_rows(players)

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
        # ⭐ WHAT MAKES A RE-PUBLISH DECIDABLE. Without it, "the same week, built again" and "the
        # vendor restated this week" are the same bytes-on-the-wire question with no answer.
        "content_sha256": content_hash(players),
    }
    log.info("[realized] %s wk%s: %s (%s/%s games, %s players)",
             season, week, state, realized_games, scheduled, len(players))
    return {"manifest": manifest, "players": players}


#: How far back a routine cadence re-examines already-published weeks. A vendor stat correction
#: lands within DAYS of the week it restates, so re-building all 18 weeks every day would spend the
#: whole season's lake reads to watch a window that closed months earlier. ⚠️ THIS IS A DELIBERATE
#: SCOPE LIMIT, NOT AN OVERSIGHT: a restatement older than this is not detected by the cadence, and
#: the operator command in the module header re-examines any single week on demand.
RESTATEMENT_WINDOW_WEEKS = 3


def week_completeness_map(realized_by_week: dict[int, int],
                          scheduled_by_week: dict[int, int]) -> dict[int, str]:
    """PURE — `{week: 'final'|'partial'|'not_started'}` from two independent counts.

    ⭐ ONE OWNER OF THE COUNT RULE. This delegates to `completeness` rather than restating the
    comparison, so the cadence and the single-week path cannot drift apart on what FINAL means.
    """
    return {
        int(w): completeness(int(realized_by_week.get(w, 0)), int(n))
        for w, n in scheduled_by_week.items()
    }


def plan_auto(states: dict[int, str], published_weeks: set[int],
              *, window: int = RESTATEMENT_WINDOW_WEEKS) -> list[dict]:
    """PURE — which weeks a cadence fire should BUILD, and why. Ascending.

    Two reasons a week is examined, and they are reported separately because they answer different
    questions: `missing` is the self-healing leg (a week the cadence never landed — a run that was
    down, a season backfilled late), and `restatement_window` is the watching leg.

    ⛔ A `partial` WEEK IS NEVER PLANNED. The PM gate (2026-09-16) is that a scheduled fire publishes
    a FINAL week or nothing: a pre-MNF fire that shipped 15/16 games would leave that week's
    Monday-night players rendering as absences indistinguishable from "did not play", and if the
    next fire failed it would sit there. A human can still publish a partial deliberately through
    the single-week CLI, which is where that judgement belongs.
    """
    final_weeks = sorted(w for w, s in states.items() if s == "final")
    watch = set(final_weeks[-int(window):]) if window > 0 else set()
    plan = []
    for w in final_weeks:
        if w not in published_weeks:
            plan.append({"week": w, "reason": "missing"})
        elif w in watch:
            plan.append({"week": w, "reason": "restatement_window"})
    return plan


def revision_players_key(season: int, week: int, stamp: str) -> str:
    """Where a RESTATED build is parked. Never served; kept so nothing is discarded."""
    safe = stamp.replace(":", "").replace("-", "")
    return f"realized/{int(season)}/{int(week)}/players.revision-{safe}.json"


def revision_manifest_key(season: int, week: int, stamp: str) -> str:
    safe = stamp.replace(":", "").replace("-", "")
    return f"realized/{int(season)}/{int(week)}/manifest.revision-{safe}.json"


#: Actions that WRITE to the served keys. Derived and used by `publish`, so adding an action cannot
#: silently become a serving write by omission.
_SERVING_WRITE_ACTIONS: frozenset[str] = frozenset({"create", "upgrade", "backfill_hash"})


def publish_decision(manifest: dict, published: dict | None) -> dict:
    """PURE — what a re-publish of this week MEANS. See the header for the full table.

    Returns `{action, reason, servingWrite, event}`. `event` is True for the cases a caller must
    surface to a human (a restatement, a refused downgrade); routine cases are silent by design.

    ⛔ `unchanged` IS ONLY REACHABLE FROM A RECORDED HASH. A published week with no
    `content_sha256` cannot be compared, and answering "we could not tell" with "unchanged" is the
    NF1.7(a) vacuous pass — it gets its own action so the transition is visible in the log exactly
    once per week rather than dissolving into the quiet path.
    """
    state = manifest.get("completeness")
    if published is None:
        return {"action": "create", "reason": "nothing is published for this week yet",
                "servingWrite": True, "event": False}

    was = published.get("completeness")
    if was == "partial" and state == "final":
        return {"action": "upgrade",
                "reason": f"the published week is {was}; this build is {state}",
                "servingWrite": True, "event": False}
    if was == "final" and state != "final":
        return {"action": "refuse_downgrade",
                "reason": (f"the published week is FINAL and this build is {state!r} — refusing to "
                           "replace a complete week with an incomplete one"),
                "servingWrite": False, "event": True}

    prior = published.get("content_sha256")
    if not prior:
        return {"action": "backfill_hash",
                "reason": ("the published week carries no content hash (it predates the "
                           "restatement machinery), so this build cannot be compared against it; "
                           "republishing ONCE to install the hash"),
                "servingWrite": True, "event": False}
    if prior == manifest.get("content_sha256"):
        return {"action": "unchanged", "reason": "byte-identical player rows",
                "servingWrite": False, "event": False}
    return {"action": "restate",
            "reason": ("the vendor has RESTATED this week — the published rows and this build "
                       "differ. The published week keeps serving; this build is parked at a "
                       "revision key."),
            "servingWrite": False, "event": True}


def published_manifest(season: int, week: int, *, s3, bucket: str,
                       prefix: str = "fantasy/nfl") -> dict | None:
    """The manifest currently SERVING for this week, or None if nothing is published.

    ⛔ A READ ERROR IS NOT A MISS. A missing key genuinely means nothing is published; anything else
    RAISES, because answering "we could not tell" with "nothing is there" would classify the next
    build as a `create` and overwrite a served week (the `weekly_recap_store.load` reasoning, and
    the same failure it guards).
    """
    import botocore.exceptions

    try:
        body = s3.get_object(Bucket=bucket,
                             Key=f"{prefix}/{realized_manifest_key(season, week)}")["Body"].read()
    except botocore.exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    return json.loads(body)


def publish(built: dict, *, s3, bucket: str, prefix: str = "fantasy/nfl") -> dict:
    """Write the artifact according to `publish_decision`. RAISES on a failed write — a publish that
    reports success while shipping nothing is the NF-FRESH1 failure this repo has already paid for.

    ⭐ IT READS BEFORE IT WRITES. The prior behaviour was an unconditional PUT, which is correct for
    a hand-run one-shot and wrong the moment a cadence re-builds the same week: it would overwrite a
    served week with no record that anything had moved.
    """
    man = built["manifest"]
    season, week = man["season"], man["week"]
    prior = published_manifest(season, week, s3=s3, bucket=bucket, prefix=prefix)
    decision = publish_decision(man, prior)
    action = decision["action"]

    def _put(key: str, body: dict) -> str:
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{key}",
                      Body=json.dumps(body, default=str), ContentType="application/json")
        return key

    written: list[str] = []
    if action in _SERVING_WRITE_ACTIONS:
        written.append(_put(realized_players_key(season, week),
                            {"players": built["players"], "generated_at": man["generated_at"]}))
        written.append(_put(realized_manifest_key(season, week), man))
    elif action == "restate":
        stamp = man["generated_at"]
        written.append(_put(revision_players_key(season, week, stamp),
                            {"players": built["players"], "generated_at": man["generated_at"]}))
        written.append(_put(revision_manifest_key(season, week, stamp), man))

    log.info("[realized] %s wk%s: %s — %s", season, week, action, decision["reason"])
    return {
        "action": action,
        "reason": decision["reason"],
        "event": decision["event"],
        "published": written if decision["servingWrite"] else [],
        "revision": written if action == "restate" else [],
        "completeness": man["completeness"],
        "priorCompleteness": (prior or {}).get("completeness"),
    }
