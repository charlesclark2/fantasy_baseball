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
  * published FINAL, we now derive MORE → `widen_columns` (NF-WK-ACC1 part 3: this build carries a
                                    term the published week did not, and every column it DID carry is
                                    byte-identical. Not a restatement — nothing the vendor publishes
                                    moved — so it overwrites, like `upgrade`. ⛔ It is decided on a
                                    hash taken over the PUBLISHED week's own column set, so a vendor
                                    correction that lands in the same build still falls through to
                                    `restate`: a widen must not become a back door for one.)

⚠️ WITHOUT `widen_columns`, TEACHING THE BUILD A NEW TERM WOULD BE A NO-OP FOREVER. Any new column
changes every row's hash, so every already-published week would classify as `restate`, keep serving
the old rows, and never show the new term — while the log filled with restatement events that named
the vendor for a change we made ourselves. The distinction is the difference between a term shipping
and a term being silently withheld.

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
from typing import Iterable

from app.backend.services import league_scoring
from app.backend.services import realized_dst as D
from quant_sports_intel_models.football.nfl.fantasy import realized_dst_pbp as DP
from quant_sports_intel_models.football.nfl.fantasy import realized_player_pbp as PP
from app.backend.services import realized_stat_fields as R
from app.backend.services import weekly_recap as W

log = logging.getLogger(__name__)

#: ⭐ THE KEY SCHEME IS OWNED BY `app/backend/models/nfl_recap.py` AND IMPORTED HERE, never
#: duplicated: this module pulls pandas through the lake read, and the API Lambda bundles neither
#: pandas nor `quant_sports_intel_models`. Two copies of a key scheme is the "one logical thing,
#: many owners" shape that goes wrong the first time one side is edited.
from app.backend.models.nfl_recap import (  # noqa: E402
    realized_dst_inputs_key,
    realized_manifest_key,
    realized_players_key,
    realized_season_manifest_key,
    realized_season_players_key,
)


#: Every `stats_player_week` column the artifact must carry: the scorer's realized sources, the
#: identity columns, the source's own PPR, and whatever the explained/unexplained split needs.
#: DERIVED — adding a term to either map widens this automatically, so a column the reader silently
#: lacked (which is how the split shipped as a no-op once) cannot recur.
#:
#: ⛔ THE PLAY-DERIVED COLUMNS ARE NOT IN HERE. This is the SELECT list for the weekly line, and
#: `stats_player_week` has no column for the 40+ yard touchdown bonuses — asking it for one would
#: fail the read. They arrive from a second read (`_long_td_counts`) and are declared in the
#: manifest by `served_columns` only when that read actually succeeded.
def required_columns() -> tuple[str, ...]:
    return tuple(sorted(
        set(R.REALIZED_STAT_COLUMNS)
        | set(R.REALIZED_KEY_COLUMNS)
        | {R.REALIZED_PPR_COLUMN}
        | set(W.EXPLANATION_COLUMNS)
        # Carried for diagnosis rather than scoring, and load-bearing for the publish path — see
        # `realized_stat_fields.REALIZED_DIAGNOSTIC_COLUMNS` for why dropping them would silently
        # strand the ruling-① map change on every already-published week.
        | set(R.REALIZED_DIAGNOSTIC_COLUMNS)
    ))


def served_columns(*, plays_joined: bool) -> tuple[str, ...]:
    """What the artifact ACTUALLY carries — the weekly line, plus the play-derived terms iff joined.

    ⭐ A FUNCTION OF THE BUILD, NOT A CONSTANT, and that is the whole point. `manifest["columns"]` is
    a CLAIM a consumer trusts, and `contract_report` refuses to publish when a claimed column carries
    no value on any row. Declaring the play-derived columns unconditionally would make every week
    whose plays are not published yet fail its own contract — turning a legitimate degraded build
    into an outage — while declaring them never would leave a consumer unable to tell whether the
    bonuses are in the number it is reading.
    """
    cols = set(required_columns())
    if plays_joined:
        cols |= set(R.REALIZED_PBP_COLUMNS)
    return tuple(sorted(cols))


#: scorer key → the column the play-derived bonus is written under. ⭐ TAKEN FROM THE SCORER'S OWN
#: MAP, never re-typed here: the column this writes and the column `flatten_realized_row` reads must
#: be the same string, and the only way to guarantee that is to have one owner of it. `PP` declares
#: the identical map for the models side; a guard pins the two together, because the backend cannot
#: import `PP` (no `quant_sports_intel_models` in the Lambda) and so the duplication is unavoidable.
_LONG_TD_COLUMN: dict[str, str] = {k: cols[0] for k, cols in R.REALIZED_PBP_SOURCE.items()}

#: The canonical row order. DuckDB promises no ordering, and an ordering difference is not a
#: content difference — without this every rebuild would hash differently and every routine re-run
#: would classify as a restatement.
_ORDER_KEYS: tuple[str, ...] = ("game_id", "player_id")


def canonical_rows(players: list[dict]) -> list[dict]:
    """The week's rows in a stable order, so the same lake content always hashes the same."""
    return sorted(players, key=lambda r: tuple(str(r.get(k) or "") for k in _ORDER_KEYS))


def content_hash(players: list[dict], columns: Iterable[str] | None = None) -> str:
    """A sha256 over the ROWS ONLY — never the manifest, whose `generated_at` moves every build.

    ⭐ `columns` RESTRICTS THE HASH TO A NAMED SUBSET, which is what lets "we started deriving a new
    term" be told apart from "the vendor restated this week". Both change the full-row hash; only the
    second changes a hash taken over the columns the published week already had. Without that
    distinction a construction change would be indistinguishable from a restatement, and the
    conservative handling of a restatement (park it, serve the old week) would silently withhold
    every new term forever — see `publish_decision`.
    """
    rows = canonical_rows(players)
    if columns is not None:
        keep = set(columns)
        # ⚠️ Stripped AFTER the canonical sort, never before: the sort keys may not be in `keep`, and
        # re-sorting a stripped row set would be ordering by a different key than the full hash uses.
        # List order is preserved by the comprehension, so the restricted hash is stable.
        rows = [{k: v for k, v in r.items() if k in keep} for r in rows]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


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

    # ── the play-derived long-touchdown bonuses (NF-WK-ACC1 part 3) ──────────────────────────────
    long_td, long_td_error = _long_td_counts(season, week, q=q, delta=delta)
    if long_td is not None:
        attach_long_td_counts(players, long_td)
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
        "columns": list(served_columns(plays_joined=long_td is not None)),
        "source_table": R.REALIZED_SOURCE_TABLE,
        # ⛔ THE DEGRADED PLAYER CONSTRUCTION SAYS SO ON THE WIRE, exactly as the D/ST one does: a
        # week built without plays is missing the three 40+ yard touchdown bonuses, and "we could not
        # read the plays" must never be the same artifact as "this week had no long touchdowns"
        # (a fallback that cannot announce itself is indistinguishable from a measurement).
        "playerConstruction": "pbp_joined" if long_td is not None else "player_week_only",
        # ⭐ WHAT MAKES A RE-PUBLISH DECIDABLE. Without it, "the same week, built again" and "the
        # vendor restated this week" are the same bytes-on-the-wire question with no answer.
        "content_sha256": content_hash(players),
    }
    if long_td_error:
        manifest["playerConstructionFallbackReason"] = long_td_error
    log.info("[realized] %s wk%s: %s (%s/%s games, %s players) players=%s",
             season, week, state, realized_games, scheduled, len(players),
             manifest["playerConstruction"])
    return {"manifest": manifest, "players": players}


def attach_long_td_counts(players: list[dict], counts: dict[str, dict[str, float]]) -> int:
    """Write the play-derived bonus columns onto every player row. Returns the rows credited.

    ⭐ ZERO ON EVERY ROW, NOT ONLY ON THE SCORERS — and this is the load-bearing detail. The term is
    APPLIED or CAPTURED according to whether `league_scoring.available_fields` sees the field at all,
    so populating it only for the handful of players who scored a long touchdown would leave the
    verdict depending on whether anyone happened to score one this week. A week with no 40+ yard
    touchdown would then report the bonus as CAPTURED — i.e. "not in this number" — when in truth it
    was applied and correctly came to nothing. Present-and-zero says the second thing; absent says
    the first; they are different claims and the caller is entitled to the right one.

    ⛔ MUTATES IN PLACE, mirroring the read it belongs to: the rows are the artifact's own, and
    copying 1,100 dicts to add three keys would be a second representation of the same week.
    """
    credited = 0
    for row in players:
        if not isinstance(row, dict):
            continue
        got = counts.get(str(row.get("player_id") or ""))
        for key, column in _LONG_TD_COLUMN.items():
            row[column] = float((got or {}).get(key) or 0.0)
        if got:
            credited += 1
    return credited


def _long_td_counts(season: int, week: int, *, q, delta
                    ) -> tuple[dict[str, dict[str, float]] | None, str | None]:
    """One week's play-derived long-touchdown counts per player, or `(None, reason)`.

    ⚠️ AN EMPTY PLAY SET IS A FALLBACK, NOT A ZERO WEEK — the same distinction `_pbp_counters` makes
    for the D/ST side. Crediting nobody with a long touchdown because no plays were published reads
    exactly like a week in which nobody scored one, and the two must stay separable.
    """
    cols = ", ".join(PP.PBP_PLAYER_COLUMNS)
    try:
        plays = q(f"""
            select {cols}
            from {delta('pbp')}
            where season = {int(season)} and week = {int(week)} and season_type = 'REG'
        """).to_dict("records")
    except Exception as exc:  # noqa: BLE001 — the reason rides the manifest; see the caller
        return None, f"{type(exc).__name__}: {exc}"
    if not plays:
        return None, f"no REG plays published for {int(season)} week {int(week)} yet"
    return PP.player_long_td_counts(plays), None


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


#: Actions that WRITE to the served keys. ⚠️ THIS IS A CROSS-CHECK, NOT THE DECISION — `publish` acts
#: on `decision["servingWrite"]`, which `publish_decision` sets beside each reason, and asserts the
#: two agree. Two independent owners of "does this overwrite the served week" is how NF-WK-ACC1 part
#: 3 nearly shipped a new action that announced `servingWrite: True` and then wrote nothing: the set
#: omitted it, and the omission is silent in exactly the direction that looks like success.
_SERVING_WRITE_ACTIONS: frozenset[str] = frozenset(
    {"create", "upgrade", "backfill_hash", "widen_columns"})


def publish_decision(manifest: dict, published: dict | None,
                     players: list[dict] | None = None) -> dict:
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

    # ⭐ OUR CONSTRUCTION WIDENING IS NOT A VENDOR RESTATEMENT (NF-WK-ACC1 part 3). When this build
    # derives a term the published week did not carry, EVERY full-row hash differs — so without this
    # case a new term would classify as `restate` on every already-published week, the published week
    # would keep serving, and the term would never reach a reader. That is the shape `upgrade` already
    # rejects for partial→final: a build that is strictly MORE than what is served is not a conflict.
    #
    # ⛔ AND IT MUST NOT ABSORB A COINCIDENT RESTATEMENT. A widen and a vendor correction can land in
    # the same build, so the test is not "did columns grow" but "did anything the published week
    # ALREADY CARRIED move" — a hash over the published column set answers exactly that. If those
    # columns moved too, this is a restatement that happens to also widen, and a restatement needs a
    # human (the ruling), so it falls through.
    was_cols = set(published.get("columns") or ())
    now_cols = set(manifest.get("columns") or ())
    added = sorted(now_cols - was_cols)
    if added and not (was_cols - now_cols):
        if players is None:
            return {"action": "restate",
                    "reason": ("the published rows and this build differ and the column set has "
                               f"grown by {added}, but no rows were supplied to tell a widened "
                               "construction from a vendor restatement — refusing to assume the "
                               "harmless one"),
                    "servingWrite": False, "event": True}
        if content_hash(players, was_cols) == prior:
            return {"action": "widen_columns",
                    "reason": (f"this build derives {added}, which the published week did not "
                               "carry; every column it DID carry is byte-identical, so nothing the "
                               "vendor publishes has moved — republishing to serve the new term(s)"),
                    "servingWrite": True, "event": False, "addedColumns": added}
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
    decision = publish_decision(man, prior, built["players"])
    action = decision["action"]

    def _put(key: str, body: dict) -> str:
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{key}",
                      Body=json.dumps(body, default=str), ContentType="application/json")
        return key

    # ⛔ THE TWO OWNERS MUST AGREE, and this is where it is enforced rather than hoped. A new action
    # whose `servingWrite` flag and membership disagree is a serving write silently skipped (or, worse,
    # silently made) — so the mismatch fails here instead of showing up as a week that never updated.
    assert (action in _SERVING_WRITE_ACTIONS) == bool(decision["servingWrite"]), (
        f"publish action {action!r} says servingWrite={decision['servingWrite']!r} but "
        f"_SERVING_WRITE_ACTIONS {'contains' if action in _SERVING_WRITE_ACTIONS else 'omits'} it"
    )

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


# ── NF-WK-ACC1 ⑥ — the D/ST recorder's team-grain inputs ───────────────────────────────────────────
#
# ⭐ A SIBLING OBJECT, REWRITTEN WHEN IT CHANGES — deliberately NOT under the players artifact's
# restatement discipline. It is recorder input, never served to a reader, and it is EXPECTED to
# change after a week is final: the Monday-night result lands in `schedules` up to a week late (PM
# card yOhLHprC), and until it does the two MNF defences carry `resultPending`. Parking that update
# at a revision key would freeze the recorder on the incomplete line.
#
# ⚠️ Team counters are SUMMED FROM `stats_player_week` — RC1's construction, reproduced exactly so the
# recorder's baseline is the measured 35/48. `stats_team_week` (now ingested, ⑧) differs from the sum
# only on SAFETIES; switching to it is a measured part-2 closure, not part of the wiring.


def _num(stats: dict, col: str) -> float:
    v = stats.get(col)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def team_week_inputs(team_stats: dict[str, dict], games: list[dict],
                     pbp_counters: dict[str, dict] | None = None) -> dict[str, dict]:
    """BOX-SIDE half: `{defence: {line, opponent, gameId, resultPending}}` for one week.

    `team_stats` maps a lake team code to that team's summed `DST_TEAM_COLUMNS`; `games` are the
    week's schedule rows (`game_id`, `home_team`, `away_team`, `home_score`, `away_score`).

    ⭐ TWO CONSTRUCTIONS, AND THE CALLER'S DATA DECIDES WHICH (NF-WK-ACC1 part 2). With
    `pbp_counters` — `{lake team code: counters}` from `realized_dst_pbp.team_game_counters`, whose
    rules are FROZEN as of 2026-09-18 — every defensive term and points allowed come from the plays,
    which reproduced the league's own figures on 48 of 48 started defences in 2025 weeks 1-4. Without
    them this stays RC1's summed-player construction, which reproduced 35 of 48.
    ⛔ THE DEGRADED PATH IS NEVER SILENT: `build_dst_inputs` stamps which construction ran in the
    artifact's `source`, so a week built without plays is legible as such rather than passing for the
    frozen one (a fallback that cannot announce itself is indistinguishable from a measurement).

    A team with no stats row is OMITTED rather than zero-filled: `compare_to_platform` reports an
    omitted defence as `notConstructed`, never as agreement.
    """
    out: dict[str, dict] = {}
    for g in games:
        home, away = g.get("home_team"), g.get("away_team")
        for me, opp, opp_score in ((home, away, g.get("away_score")),
                                   (away, home, g.get("home_score"))):
            if me not in team_stats or opp not in team_stats:
                continue
            m, o = team_stats[me], team_stats[opp]
            score = None if opp_score is None or (isinstance(opp_score, float) and math.isnan(opp_score)) \
                else float(opp_score)
            mine_pbp = (pbp_counters or {}).get(me)
            theirs_pbp = (pbp_counters or {}).get(opp)
            pa_override = None
            if mine_pbp is not None and theirs_pbp is not None:
                counters = {k: float(mine_pbp.get(k) or 0.0) for k in DP.COUNTER_KEYS}
                pa_override = DP.points_allowed(score, theirs_pbp)
                non_offensive = 0.0  # unused: the frozen figure arrives as the override
            else:
                non_offensive = (_num(o, "def_tds") + _num(o, "special_teams_tds")
                                 + _num(o, "fumble_recovery_tds"))
                counters = {
                    "def_sacks": _num(m, "def_sacks"),
                    "def_int": _num(m, "def_interceptions"),
                    "def_fumble_rec": _num(m, "fumble_recovery_opp"),
                    "def_td": _num(m, "def_tds") + _num(m, "fumble_recovery_tds"),
                    "def_safety": _num(m, "def_safeties"),
                    "def_forced_fumble": _num(m, "def_fumbles_forced"),
                    "st_td": _num(m, "special_teams_tds"),
                }
            line = D.dst_row(
                opponent_score=score,
                opponent_non_offensive_tds=non_offensive,
                opponent_passing_yards=_num(o, "passing_yards"),
                opponent_rushing_yards=_num(o, "rushing_yards"),
                opponent_sack_yards_lost=_num(o, "sack_yards_lost"),
                team_defensive_stats=counters,
                points_allowed_override=pa_override,
            )
            # Keyed by the SCORER'S team vocabulary so the lake's `LA` and Sleeper's `LAR` meet.
            key = _team_key(me)
            if not key:
                continue
            out[key] = {
                "line": line,
                "opponent": _team_key(opp) or str(opp),
                "gameId": g.get("game_id"),
                "resultPending": D.result_pending(score),
            }
    return out


def _team_key(team) -> str:
    return league_scoring.normalize_team(team)



def build_dst_inputs(season: int, week: int, *, q, delta) -> dict:
    """Read one week's team-grain D/ST inputs from the lake. `q`/`delta` injected, as in `build`."""
    sums = ", ".join(f"sum({c}) as {c}" for c in D.DST_TEAM_COLUMNS)
    stats = q(f"""
        select team, {sums}
        from {delta('stats_player_week')}
        where season = {int(season)} and week = {int(week)} and season_type = 'REG'
        group by team
    """).to_dict("records")
    games = q(f"""
        select game_id, home_team, away_team, home_score, away_score
        from {delta('schedules')}
        where season = {int(season)} and week = {int(week)} and game_type = 'REG'
    """).to_dict("records")
    team_stats = {str(r["team"]): r for r in stats if r.get("team")}
    pbp_counters, pbp_error = _pbp_counters(season, week, q=q, delta=delta)
    teams = team_week_inputs(team_stats, [_clean(g) for g in games], pbp_counters)
    frozen = pbp_counters is not None
    out = {
        "season": int(season),
        "week": int(week),
        "source": ("pbp (frozen 2026-09-18 rules) + stats_player_week (yards allowed) + schedules"
                   if frozen else "stats_player_week (summed by team) + schedules"),
        "construction": "pbp_frozen" if frozen else "player_sums",
        "pointsAllowedAssumption": (D.POINTS_ALLOWED_RULE_PBP if frozen
                                    else D.POINTS_ALLOWED_ASSUMPTION),
        "teams": teams,
        "resultPendingTeams": sorted(t for t, e in teams.items() if e["resultPending"]),
    }
    # ⛔ A DEGRADED CONSTRUCTION SAYS SO ON THE WIRE. The play read is best-effort — a week whose
    # plays are not published yet must still produce a line — but "we fell back" and "this is the
    # frozen construction" must never be the same artifact (the E9.62 lesson: a fallback that cannot
    # announce itself is indistinguishable from a measurement).
    if pbp_error:
        out["constructionFallbackReason"] = pbp_error
    return out


def _pbp_counters(season: int, week: int, *, q, delta) -> tuple[dict[str, dict] | None, str | None]:
    """One week's play-derived counters per team, or `(None, reason)` if the plays cannot be read.

    ⚠️ AN EMPTY PLAY SET IS A FALLBACK, NOT AN EMPTY CONSTRUCTION. Counting zero sacks for every
    defence because no plays were published would read exactly like a quiet week.
    """
    cols = ", ".join(DP.PBP_COLUMNS)
    try:
        plays = q(f"""
            select {cols}
            from {delta('pbp')}
            where season = {int(season)} and week = {int(week)} and season_type = 'REG'
        """).to_dict("records")
    except Exception as exc:  # noqa: BLE001 — the reason rides the artifact; see the caller
        return None, f"{type(exc).__name__}: {exc}"
    if not plays:
        return None, f"no REG plays published for {int(season)} week {int(week)} yet"
    by_game: dict[str, list[dict]] = {}
    for play in plays:
        by_game.setdefault(str(play.get("game_id")), []).append(play)
    counters: dict[str, dict] = {}
    for game_plays in by_game.values():
        for team, values in DP.team_game_counters(game_plays).items():
            # One team plays once per week, so a collision would mean a duplicated game — sum rather
            # than overwrite, and the harness's agreement figures are what would catch it.
            if team in counters:
                counters[team] = {k: counters[team][k] + values[k] for k in values}
            else:
                counters[team] = dict(values)
    return counters, None


def _clean(row: dict) -> dict:
    """NaN → None, so a missing score reads as pending rather than as a float that is not a number."""
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}


def dst_inputs_hash(built: dict) -> str:
    return hashlib.sha256(json.dumps(
        {k: v for k, v in built.items() if k != "generated_at"}, sort_keys=True, default=str,
    ).encode()).hexdigest()


def publish_dst_inputs(built: dict, *, s3, bucket: str, prefix: str = "fantasy/nfl",
                       dry: bool = False) -> dict:
    """Write the week's D/ST inputs if their CONTENT changed. RAISES on a failed read or write."""
    key = f"{prefix}/{realized_dst_inputs_key(built['season'], built['week'])}"
    want = dst_inputs_hash(built)
    try:
        prior = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404"):
            raise
        prior = None
    if prior is not None and prior.get("content_sha256") == want:
        action = "unchanged"
    else:
        action = "create" if prior is None else "update"
        if not dry:
            body = {**built, "content_sha256": want,
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(body, default=str),
                          ContentType="application/json")
    return {"week": built["week"], "action": action, "teams": len(built["teams"]),
            "resultPending": built["resultPendingTeams"], "dryRun": dry}

