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
import math
from datetime import datetime, timezone

from app.backend.services import realized_stat_fields as R
from app.backend.services import weekly_recap as W

log = logging.getLogger(__name__)

#: ⭐ THE KEY SCHEME IS OWNED BY `app/backend/models/nfl_recap.py` AND IMPORTED HERE, never
#: duplicated: this module pulls pandas through the lake read, and the API Lambda bundles neither
#: pandas nor `quant_sports_intel_models`. Two copies of a key scheme is the "one logical thing,
#: many owners" shape that goes wrong the first time one side is edited.
from app.backend.models.nfl_recap import (  # noqa: E402
    realized_manifest_key,
    realized_players_key,
    realized_season_manifest_key,
    realized_season_players_key,
)


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


# ── the publish-time contract (NF-WK-RC1 addendum, PM 2026-09-17; scope = NF-WVR1 ⑭) ─────────────
#
# ⭐ WHAT WAS MISSING WAS NARROW. The column contract was already DERIVED (`required_columns`), NAMED
# in the SELECT (a vanished lake column fails the read loudly), and SERVED (`manifest["columns"]`).
# What nothing did was check the EMITTED ROWS against it: a lake column that exists but is
# unpopulated would be advertised in `columns` and then scored downstream as silent zeros — the
# NF-C0e "reads the value back under the key the code wrote" shape, one level out.
#
# ⛔ NOT A BLANKET SCHEMA VALIDATOR (the PM's explicit exclusion). Three checks, each tied to a
# measured failure shape, and nothing about value ranges or types.
#
# ⚠️ THE FIVE ALL-ZERO COLUMNS ON WEEK 1 ARE TRUE ZEROS (`def_safeties`, `fg_made_0_19`,
# `fg_made_60_`, `rushing_2pt_conversions`, `special_teams_tds` — rare events across 16 games). The
# check counts rows CARRYING A VALUE (non-null), never non-zero rows, so they pass, correctly. A
# future reader must not "fix" them.

#: ⭐ AN IDENTITY, NOT A TUNED FLOOR: every game has exactly two teams. Measured 2026-09-16 on all
#: 142 REG weeks in the lake (2018–2026 wk1): `count(distinct team) == 2 × count(distinct game_id)`
#: on every one, bye weeks included. So a shortfall is never noise — it is a game with a side missing.
TEAMS_PER_GAME = 2

#: Rows per realized game, floored. ⭐ ANCHORED ON A MEASURED POPULATION, not on week 1 alone: the
#: same 142 weeks run 63.25–69.88 players per game (2026 wk1 = 69.88, the high end — a floor set
#: from week 1 would have false-fired on 2023 wk17's 63.25). 50 is 0.8 × the lowest week observed,
#: rounded down.
#: ⚠️ SCOPE, stated so nobody over-reads a pass: this catches a GROSS row loss (≥ ~21% on the
#: thinnest week ever seen — a whole unit or most of a game's box score). It does NOT catch a single
#: missing position (QBs are ~2.3 rows per game). Column loss is the non-null check's job.
MIN_PLAYERS_PER_GAME = 50


def carries_value(v) -> bool:
    """True when a cell holds a value. ⛔ `NaN` IS NOT A VALUE: the lake read goes through pandas,
    so an unpopulated NUMERIC column arrives as `NaN`, never `None` — an `is not None` test would
    count every such cell as populated and make this check vacuous on exactly the numeric columns it
    exists for."""
    return v is not None and not (isinstance(v, float) and math.isnan(v))


class RealizedContractError(RuntimeError):
    """A built artifact does not carry what its manifest says it carries. Nothing is written."""


def contract_report(manifest: dict, players: list[dict]) -> dict:
    """PURE — does this week's artifact carry what it declares? Returns `{ok, violations, ...}`.

    Three checks (the PM's list, and only those):
      1. every column in `manifest["columns"]` carries a non-null value on at least one row;
      2. `n_teams` / `n_players` clear their floors for the number of games actually realized;
      3. the manifest's counts describe THESE rows (recounted, never trusted) — a floor read off a
         manifest that disagrees with its rows would check the wrong thing.

    ⭐ A MISSING KEY COUNTS AS NULL. `r.get(c)` is None whether the column is null or absent, so a
    column dropped from the row dicts entirely fails exactly like an unpopulated one.
    """
    cols = list(manifest.get("columns") or [])
    violations: list[str] = []
    if not cols:
        violations.append("the manifest lists no columns, so nothing it serves can be checked")

    carrying = {c: sum(1 for r in players if carries_value(r.get(c))) for c in cols}
    empty = sorted(c for c, n in carrying.items() if n == 0)
    for c in empty:
        violations.append(f"column {c!r} is listed but carries no value on any of "
                          f"{len(players)} rows")

    rows_games = len({str(r.get("game_id")) for r in players if carries_value(r.get("game_id"))})
    rows_teams = len({str(r.get("team")) for r in players if carries_value(r.get("team"))})
    for field, recount in (("n_players", len(players)), ("n_teams", rows_teams),
                           ("realized_games", rows_games)):
        if int(manifest.get(field) or 0) != recount:
            violations.append(f"manifest {field}={manifest.get(field)!r} but the rows carry "
                              f"{recount}")

    if rows_games <= 0:
        violations.append("the rows carry no realized games")
    else:
        if rows_teams < TEAMS_PER_GAME * rows_games:
            violations.append(f"{rows_teams} teams across {rows_games} games — below the "
                              f"{TEAMS_PER_GAME}-per-game identity, so a game is missing a side")
        if len(players) < MIN_PLAYERS_PER_GAME * rows_games:
            violations.append(f"{len(players)} rows across {rows_games} games — below the floor "
                              f"of {MIN_PLAYERS_PER_GAME} per game")

    return {
        "ok": not violations,
        "violations": violations,
        "emptyColumns": empty,
        # Reported, not gated: every REG week in the lake carries exactly ONE all-zero row with no
        # player attached (measured on all 142 weeks) — a vendor artifact, harmless to scoring.
        "rowsWithoutPlayerId": sum(1 for r in players if not carries_value(r.get("player_id"))),
        "fewestCarryingRows": min(carrying.values()) if carrying else 0,
    }


def assert_contract(manifest: dict, players: list[dict], *, label: str) -> dict:
    rep = contract_report(manifest, players)
    if not rep["ok"]:
        raise RealizedContractError(f"{label}: REFUSING to publish — "
                                    + "; ".join(rep["violations"]))
    return rep


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
    # ⛔ BEFORE ANY READ OR WRITE, on every path — a serving write and a parked revision alike. A
    # build that does not carry what it declares is refused whole rather than half-published.
    assert_contract(man, built["players"], label=f"{season} wk{week}")
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


# ── the cumulative season-to-date artifact (PM ruling, NF-WVR1 ⑯ = option b, 2026-09-17) ─────────
#
# ⭐ WHY IT EXISTS. A season-to-date consumer (WVR1's fact columns) otherwise reads one weekly file
# per completed week — 1 GET today, ~18 by the last week — and the dangerous failure of that fan-out
# is a SILENT TRUNCATION: a total summed over a subset of weeks looks exactly like a quiet player.
# One artifact, built while this job already has every week in hand, removes the fan-out rather than
# bounding it.
#
# ⭐ IT IS BUILT FROM THE *SERVED* WEEKLY ARTIFACTS, NEVER FROM A SECOND LAKE READ. So it can never
# disagree with what the weekly files serve, and the restatement discipline is inherited for free: a
# restated build is parked at a revision key, is not served, and therefore never enters this either.
# Each week's rows are verified against that week's served `content_sha256` before they are used.
#
# ⭐ ONE ROW PER PLAYER-GAME, NOT PER-PLAYER SEASON TOTALS. The league scorer is linear today, so
# totals WOULD score identically — but that is a property of today's scorer, not of the artifact.
# Keeping the per-game rows makes this a checkable CONCATENATION of the served weeks (row counts and
# week sets are identities) and leaves every per-game fact (a D/ST result, a future threshold term)
# intact. It is encoded COLUMNAR (`columns` + `rows` of arrays), measured on week 1 at 179 KB vs
# 1.10 MB as row objects — ~3.2 MB for a full 18-week season, uncompressed, so the consumer needs no
# gzip handling.
#
# ⛔ A GAP ENDS IT, AND THE GAP IS NAMED. The artifact covers the longest run of weeks 1..K that are
# all served, FINAL and verifiable. Any served week past a gap is listed in `excluded` with its
# reason and is NOT summed in — a season total that silently skipped week 3 is the exact shape this
# artifact exists to prevent. A consumer reads `through_week` and `excluded`, never infers them.

SEASON_ENCODING = "columnar-v1"

#: Why a served week is not in the cumulative artifact. `not_final` is routine (a deliberately
#: hand-published partial week); every other reason is a defect the cadence pages on.
_ROUTINE_EXCLUSIONS: frozenset[str] = frozenset({"not_final"})


def load_served_week(season: int, week: int, *, s3, bucket: str,
                     prefix: str = "fantasy/nfl") -> tuple[dict, list[dict]] | None:
    """`(manifest, players)` currently SERVING for this week, or None if no manifest is served.

    ⛔ A served manifest whose players file cannot be read RAISES — including a 404. A manifest
    advertising rows that are not there is a broken week, not an absent one.
    """
    man = published_manifest(season, week, s3=s3, bucket=bucket, prefix=prefix)
    if man is None:
        return None
    body = s3.get_object(Bucket=bucket,
                         Key=f"{prefix}/{realized_players_key(season, week)}")["Body"].read()
    return man, json.loads(body)["players"]


def build_season(season: int, served: dict[int, tuple[dict, list[dict]]]) -> dict:
    """PURE — the season-to-date artifact from the served weekly artifacts. See the section header.

    `served` maps week → `(manifest, players)` for every week that has a served manifest.
    """
    cols = list(required_columns())
    included: list[int] = []
    excluded: list[dict] = []
    blocked_by: int | None = None
    expected = 1
    for week in sorted(served):
        man, players = served[week]
        reason = detail = None
        if blocked_by is not None:
            reason, detail = "after_gap", f"week {blocked_by} is not in the artifact"
        elif week != expected:
            reason, detail = "after_gap", f"week {expected} has no served artifact"
        elif man.get("completeness") != "final":
            reason, detail = "not_final", f"served as {man.get('completeness')!r}"
        elif not man.get("content_sha256"):
            reason, detail = "unverifiable", "the served manifest carries no content hash"
        elif content_hash(players) != man["content_sha256"]:
            reason, detail = "hash_mismatch", "the served rows do not match their manifest's hash"
        elif not set(cols) <= set(man.get("columns") or []):
            missing = sorted(set(cols) - set(man.get("columns") or []))
            reason, detail = "columns_behind", f"published before these columns existed: {missing}"
        else:
            rep = contract_report(man, players)
            if not rep["ok"]:
                reason, detail = "contract", "; ".join(rep["violations"])
        if reason:
            excluded.append({"week": int(week), "reason": reason, "detail": detail})
            if blocked_by is None:
                blocked_by = expected if reason == "after_gap" and week != expected else week
            continue
        included.append(int(week))
        expected += 1

    rows: list[list] = []
    sources: list[dict] = []
    for week in included:
        man, players = served[week]
        rows.extend([r.get(c) for c in cols] for r in canonical_rows(players))
        sources.append({"week": week, "content_sha256": man["content_sha256"],
                        "n_players": len(players)})

    pid = cols.index("player_id")
    manifest = {
        "season": int(season),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "encoding": SEASON_ENCODING,
        # ⭐ The one field a consumer must read before summing: the artifact covers weeks
        # 1..through_week and nothing else. None means no week qualifies.
        "through_week": included[-1] if included else None,
        "weeks": included,
        "excluded": excluded,
        "columns": cols,
        "n_rows": len(rows),
        "n_players": len({r[pid] for r in rows if carries_value(r[pid])}),
        "sources": sources,
        # ⭐ What makes a re-publish decidable without re-hashing 20k rows: the artifact is a pure
        # function of which served weeks it concatenates, and each of those is already hashed.
        "source_fingerprint": hashlib.sha256(
            json.dumps([[s["week"], s["content_sha256"]] for s in sources]).encode()
        ).hexdigest(),
        "content_sha256": hashlib.sha256(
            json.dumps(rows, default=str).encode()).hexdigest(),
    }
    return {"manifest": manifest, "columns": cols, "rows": rows}


def season_contract_report(built: dict) -> dict:
    """PURE — does the season artifact carry what it declares? The same discipline as a week's,
    plus the identities a concatenation must satisfy."""
    man, cols, rows = built["manifest"], built["columns"], built["rows"]
    violations: list[str] = []
    weeks = list(man.get("weeks") or [])

    if cols != list(man.get("columns") or []):
        violations.append("the rows' column order does not match the manifest's `columns`")
    if weeks != list(range(1, len(weeks) + 1)):
        violations.append(f"weeks {weeks} are not a contiguous run from week 1")
    if man.get("through_week") != (weeks[-1] if weeks else None):
        violations.append(f"through_week={man.get('through_week')!r} does not match weeks {weeks}")
    bad_width = sum(1 for r in rows if len(r) != len(cols))
    if bad_width:
        violations.append(f"{bad_width} rows do not have {len(cols)} values")
    if man.get("n_rows") != len(rows):
        violations.append(f"manifest n_rows={man.get('n_rows')!r} but {len(rows)} rows are present")
    if len(rows) != sum(s["n_players"] for s in man.get("sources") or []):
        violations.append("the row count is not the sum of the source weeks' rows")

    if weeks and not bad_width:
        wk = cols.index("week")
        carried = sorted({int(r[wk]) for r in rows if carries_value(r[wk])})
        if carried != weeks:
            violations.append(f"the rows carry weeks {carried} but the manifest says {weeks}")
        for i, c in enumerate(cols):
            if not any(carries_value(r[i]) for r in rows):
                violations.append(f"column {c!r} carries no value on any of {len(rows)} rows")

    return {"ok": not violations, "violations": violations}


def season_publish_decision(manifest: dict, published: dict | None) -> dict:
    """PURE — what writing this season artifact MEANS.

    ⛔ IT NEVER SHRINKS. A build covering fewer weeks than the one serving is refused: a season
    total that silently lost a week is worse than one that has not advanced yet.
    ⛔ AND IT NEVER PUBLISHES EMPTY. With no qualifying week there is nothing to write, and a
    consumer's missing file stays an honest absence rather than an artifact of zero rows.
    """
    through = manifest.get("through_week")
    if through is None:
        return {"action": "skip_empty", "reason": "no served week qualifies yet",
                "servingWrite": False, "event": False}
    if published is None:
        return {"action": "create", "reason": f"nothing is published; covering weeks 1-{through}",
                "servingWrite": True, "event": False}
    was = published.get("through_week") or 0
    if through < was:
        return {"action": "refuse_regress",
                "reason": (f"the published artifact covers weeks 1-{was}; this build covers only "
                           f"1-{through} — refusing to shrink a season total"),
                "servingWrite": False, "event": True}
    if published.get("source_fingerprint") == manifest.get("source_fingerprint"):
        return {"action": "unchanged", "reason": f"same source weeks 1-{through}",
                "servingWrite": False, "event": False}
    if through > was:
        return {"action": "advance", "reason": f"weeks 1-{was} → 1-{through}",
                "servingWrite": True, "event": False}
    return {"action": "refresh",
            "reason": (f"weeks 1-{through} unchanged in range, but a served source week was "
                       "rewritten (an upgrade or a hash backfill)"),
            "servingWrite": True, "event": False}


def published_season_manifest(season: int, *, s3, bucket: str,
                              prefix: str = "fantasy/nfl") -> dict | None:
    """The season manifest currently serving, or None. A read error that is not a miss RAISES."""
    import botocore.exceptions

    try:
        body = s3.get_object(Bucket=bucket,
                             Key=f"{prefix}/{realized_season_manifest_key(season)}")["Body"].read()
    except botocore.exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    return json.loads(body)


def publish_season(built: dict, *, s3, bucket: str, prefix: str = "fantasy/nfl") -> dict:
    """Write the season artifact according to `season_publish_decision`. RAISES on a contract
    violation (before any write) or a failed write. Rows first, manifest last, so a reader never
    sees a manifest describing rows that have not landed."""
    man = built["manifest"]
    season = man["season"]
    if man.get("through_week") is not None:
        rep = season_contract_report(built)
        if not rep["ok"]:
            raise RealizedContractError(f"{season} season: REFUSING to publish — "
                                        + "; ".join(rep["violations"]))
    prior = published_season_manifest(season, s3=s3, bucket=bucket, prefix=prefix)
    decision = season_publish_decision(man, prior)

    written: list[str] = []
    if decision["servingWrite"]:
        for key, body in (
            (realized_season_players_key(season),
             {"encoding": SEASON_ENCODING, "columns": built["columns"], "rows": built["rows"],
              "generated_at": man["generated_at"]}),
            (realized_season_manifest_key(season), man),
        ):
            s3.put_object(Bucket=bucket, Key=f"{prefix}/{key}",
                          Body=json.dumps(body, default=str, separators=(",", ":")),
                          ContentType="application/json")
            written.append(key)

    log.info("[realized] %s season: %s — %s", season, decision["action"], decision["reason"])
    return {**decision, "published": written, "through_week": man.get("through_week"),
            "priorThroughWeek": (prior or {}).get("through_week")}


def season_defects(built: dict) -> list[dict]:
    """The exclusions a cadence must PAGE on — every one except a deliberately partial week."""
    return [e for e in built["manifest"]["excluded"] if e["reason"] not in _ROUTINE_EXCLUSIONS]
