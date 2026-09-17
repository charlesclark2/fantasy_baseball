"""waiver_facts.py  (NF-WVR1 — REALIZED 2026 production-to-date, as FACT columns on the FA pool)
====================================================================================================

What an available player HAS DONE this season, scored in the caller's own league scoring, attached
to the free-agent pool as the honest interim ordering (PM rulings 1 + 2 + Q4, 2026-09-16/17).

⛔ FACTS, NOT A FORECAST, AND NOT A VALUE COLUMN. Nothing here projects anything. A rest-of-season
value column was NF-ROS1's to supply and NF-ROS1 closed as a certified NO, so there is none; the
season board's `fpPpr` is a preseason FULL-SEASON projection with no in-season production channel,
and it is never substituted for these numbers (the PM's Mendoza row: 268.3 projected, zero snaps).

⛔ NOT A FOURTH SCORER. Every point comes out of `league_scoring.score_row` unchanged, read under
`realized_stat_fields.REALIZED_STAT_FIELD` — the exact seam RC1's weekly recap uses.

───────────────────────────────────────────────────────────────────────────────────────────────────
THE SOURCE: ONE GET, AND ITS LINEAGE IS CHECKED HERE, NOT TRUSTED (PM ruling ⑯ = b)
───────────────────────────────────────────────────────────────────────────────────────────────────

`fantasy/nfl/realized/<season>/season/{players,manifest}.json` is RC1's cumulative artifact: one row
per player-GAME (not per-player totals), columnar-v1, covering weeks `1..through_week` and nothing
else, with every later served week listed in `excluded` and NOT summed in.

`verify_season` recomputes the artifact's own lineage from the bytes it serves — the rows'
`content_sha256`, the `source_fingerprint` over `[week, content_sha256]`, and the concatenation
identities (row count = Σ source rows; row week-set = `weeks`; `weeks` a contiguous run from 1).
⚠️ The hash definitions are a TWIN of `realized_week.build_season`'s, because the API Lambda bundles
neither pandas nor that module (`nfl_recap`'s header). A twin is a drift surface, so
`test_nf_wvr1_fact_columns.py` builds a real artifact with the builder and requires this verifier to
accept it and to reject each single-cell mutation of it.

⭐ WHY NOT ALSO RE-CHECK EACH WEEK AGAINST ITS SERVED WEEKLY MANIFEST: that is one GET per week —
exactly the fan-out ruling ⑯ removed — and RC1's publisher already refuses to include a week whose
rows do not match its served hash. The link was measured holding at the start of this story
(2026-09-17T05:14:25Z, week 1).

───────────────────────────────────────────────────────────────────────────────────────────────────
THE THREE ABSENCES A FACT CELL CAN CARRY, AND WHY NONE OF THEM IS A ZERO
───────────────────────────────────────────────────────────────────────────────────────────────────

  team_grain_not_covered — a team defence. The artifact is PLAYER-grained and carries no points- or
      yards-allowed column (RC1 documents it at source; ruling ⑮). "No facts for this defence" must
      never read as "this defence did nothing" (NF-C6b / NF-K1). Unlocks when card fXIYuvMN
      validates our own team-defence construction — not here.
  no_realized_line — no stat line in the covered weeks matched this player. We cannot tell "did not
      play" from "we could not match his name", so it is stated as exactly what we know.
  (league level) realized_not_published / realized_lineage_unverified — the whole column is
      withheld and the pool falls back to the stated non-ranked listing.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.backend.services import league_scoring, realized_stat_fields

#: RC1's encoding marker. A different encoding is refused rather than guessed at.
SEASON_ENCODING = "columnar-v1"

#: Positions the realized artifact can carry facts for. DST is deliberately absent — see the header.
FACT_POSITIONS: frozenset[str] = frozenset({"QB", "RB", "WR", "TE", "K"})

#: Why the WHOLE fact column is withheld for a request. The pool still renders, unranked, and says so.
FACTS_ABSENCE_REASONS: tuple[str, ...] = (
    "realized_not_published",       # no season artifact is serving yet
    "realized_lineage_unverified",  # it is serving, but its own hashes/identities do not hold
)

#: Why ONE player's fact cell is empty.
PLAYER_FACT_ABSENCE_REASONS: tuple[str, ...] = (
    "team_grain_not_covered",
    "no_realized_line",
)

#: Columns this module reads by name. The artifact declares its columns; a missing one is a
#: verification failure, never a silent `None` on every row.
_REQUIRED_COLUMNS: tuple[str, ...] = (
    "player_id", "player_display_name", "position", "team", "week",
)

#: nflverse gsis ids — the one id vocabulary the board and the realized line share. Board rows with
#: SYNTHETIC ids (rookies, team defences) do not match this and fall through to the name join.
_GSIS_ID = re.compile(r"^00-\d{7}$")


def _sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, default=str).encode()).hexdigest()


def verify_season(manifest: dict, body: dict) -> list[str]:
    """Every way the served season artifact fails its own declared lineage. Empty ⇒ verified.

    ⚠️ The two hash expressions below must stay byte-identical to `realized_week.build_season`'s
    (`json.dumps(rows, default=str)` and `json.dumps([[week, sha], …])`); the builder-parity guard
    pins them.
    """
    v: list[str] = []
    if not isinstance(manifest, dict) or not isinstance(body, dict):
        return ["the manifest or the rows file is not a JSON object"]
    if manifest.get("encoding") != SEASON_ENCODING or body.get("encoding") != SEASON_ENCODING:
        v.append(f"encoding is {manifest.get('encoding')!r}/{body.get('encoding')!r}, "
                 f"expected {SEASON_ENCODING!r}")
    cols = body.get("columns")
    rows = body.get("rows")
    if not isinstance(cols, list) or not isinstance(rows, list):
        return v + ["the rows file carries no `columns`/`rows` arrays"]
    if cols != manifest.get("columns"):
        v.append("the rows' columns do not match the manifest's")
    missing = [c for c in _REQUIRED_COLUMNS if c not in cols]
    if missing:
        v.append(f"columns this reader needs are absent: {missing}")
    bad_width = sum(1 for r in rows if not isinstance(r, list) or len(r) != len(cols))
    if bad_width:
        v.append(f"{bad_width} rows do not have {len(cols)} values")
    if manifest.get("n_rows") != len(rows):
        v.append(f"manifest n_rows={manifest.get('n_rows')!r} but {len(rows)} rows are present")
    if _sha256(rows) != manifest.get("content_sha256"):
        v.append("the rows do not match the manifest's content_sha256")

    sources = manifest.get("sources")
    weeks = manifest.get("weeks")
    if not isinstance(sources, list) or not isinstance(weeks, list):
        return v + ["the manifest carries no `sources`/`weeks` lists"]
    fingerprint = hashlib.sha256(
        json.dumps([[s.get("week"), s.get("content_sha256")] for s in sources]).encode()
    ).hexdigest()
    if fingerprint != manifest.get("source_fingerprint"):
        v.append("the manifest's source_fingerprint does not match its sources")
    if [s.get("week") for s in sources] != weeks:
        v.append(f"sources cover weeks {[s.get('week') for s in sources]} but the manifest says {weeks}")
    if weeks != list(range(1, len(weeks) + 1)):
        v.append(f"weeks {weeks} are not a contiguous run from week 1")
    if manifest.get("through_week") != (weeks[-1] if weeks else None):
        v.append(f"through_week={manifest.get('through_week')!r} does not match weeks {weeks}")
    if sum(int(s.get("n_players") or 0) for s in sources) != len(rows):
        v.append("the row count is not the sum of the source weeks' rows")
    if not missing and not bad_width:
        wk = cols.index("week")
        carried = sorted({r[wk] for r in rows if r[wk] is not None})
        if carried != weeks:
            v.append(f"the rows carry weeks {carried} but the manifest says {weeks}")
    return v


def season_facts(manifest: dict, body: dict, cfg: dict) -> dict:
    """PURE — per-player season-to-date facts in THIS league's scoring, over `manifest["weeks"]` only.

    Call only on an artifact `verify_season` accepted.

    ⭐ SCORED PER PLAYER-GAME, THEN SUMMED — not summed-then-scored. Today's scorer is linear, so the
    two agree; per-game is the one that stays right if a per-game threshold term is ever taught to
    the scorer, which is exactly why RC1 publishes per-game rows (`realized_week` section header).

    Returns `{"by_id", "by_key", "coverage"}` where each entry is
    `{"points", "games", "weeks", "name", "pos", "team"}`.
    """
    cols = body["columns"]
    covered = set(manifest.get("weeks") or [])
    games: list[tuple[str, dict]] = []
    for raw in body["rows"]:
        row = dict(zip(cols, raw))
        if row.get("week") not in covered:
            continue
        pos = league_scoring.normalize_position(row.get("position"))
        if pos not in FACT_POSITIONS or not row.get("player_id"):
            continue
        games.append((pos, row))

    flat = [realized_stat_fields.flatten_realized_row(r) for _, r in games]
    field_map = realized_stat_fields.REALIZED_STAT_FIELD
    resolved, coverage = league_scoring.resolve_scoring(
        cfg.get("scoring") or {},
        stat_field=field_map,
        # The fields actually PRESENT, so a league weight on a term this artifact does not carry
        # resolves CAPTURED instead of scoring zero behind an "applied" label (the recap's rule).
        fields=league_scoring.available_fields(flat),
        captured_rules=list((cfg.get("captured_rules") or {}).keys()),
    )

    by_id: dict[str, dict] = {}
    for (pos, row), f in zip(games, flat):
        pid = str(row["player_id"])
        pts = league_scoring.score_row(f, pos, resolved, field_map)["pts"]
        agg = by_id.get(pid)
        week = int(row["week"])
        if agg is None:
            agg = by_id[pid] = {"points": 0.0, "games": 0, "weeks": [], "latest": -1}
        agg["points"] += pts
        agg["games"] += 1
        agg["weeks"].append(week)
        # Identity comes from the player's MOST RECENT game: a mid-season trade changes the team.
        if week > agg["latest"]:
            agg.update(latest=week, name=str(row.get("player_display_name") or ""),
                       pos=pos, team=str(row.get("team") or ""))

    by_key: dict[str, dict] = {}
    ambiguous: set[str] = set()
    for pid, agg in by_id.items():
        agg["weeks"] = sorted(agg["weeks"])
        agg.pop("latest", None)
        agg["player_id"] = pid
        if not agg["name"]:
            continue
        key = league_scoring._join_key(agg["name"], agg["pos"], agg["team"])
        if key in by_key:
            ambiguous.add(key)
        by_key[key] = agg
    # ⛔ Two realized players on one name+position key is a join we cannot resolve; attaching
    # either one's facts could credit the wrong player. Measured 0 on week 1 (392 keys).
    for key in ambiguous:
        by_key.pop(key, None)

    return {"by_id": by_id, "by_key": by_key, "coverage": coverage}


def fact_for(player: dict, facts: dict) -> dict:
    """The fact cell for ONE pool row: id first (real gsis ids only), then the name join.

    ⭐ WHY AN ID RUNG HERE WHEN THE POOL SUBTRACTION FORBIDS ONE (ruling ⑥): the subtraction must
    never DROP a player, and an id join drops every synthetic-id rookie. Attaching a fact is the
    other direction — a miss leaves a STATED absence rather than removing anyone — and the id rung
    recovers name aliases the name join cannot (measured: board `Joshua Palmer` vs realized
    `Josh Palmer`, same gsis id, 10.4 PPR in week 1). Synthetic ids fail the gsis pattern and fall
    through to the name join, so no rookie loses the rung it already had.
    """
    pos = league_scoring.normalize_position(player.get("pos"))
    if pos == "DST":
        return {"points": None, "games": None, "absence": "team_grain_not_covered"}
    hit = None
    pid = str(player.get("id") or "")
    if _GSIS_ID.match(pid):
        hit = facts["by_id"].get(pid)
        if hit is not None and hit["pos"] != pos:
            hit = None  # same id, different position group: do not guess
    if hit is None:
        hit = facts["by_key"].get(
            league_scoring._join_key(str(player.get("name") or ""), pos, player.get("team"))
        )
    if hit is None:
        return {"points": None, "games": 0, "absence": "no_realized_line"}
    return {"points": hit["points"], "games": hit["games"], "absence": None}


def order_group(players: list[dict]) -> list[dict]:
    """Within ONE position: players WITH facts by realized league points (high first), then the
    rest in the board's own order. Stable, so equal points keep board order.

    ⛔ Never across positions (PM ruling 2) — the caller applies this per group.
    """
    with_facts = [p for p in players if (p.get("realized") or {}).get("points") is not None]
    without = [p for p in players if (p.get("realized") or {}).get("points") is None]
    with_facts.sort(key=lambda p: -float(p["realized"]["points"]))
    return with_facts + without


def captured_terms(coverage: dict) -> list[str]:
    """League scoring terms these totals do NOT include (no realized source), for the adjacent note."""
    return sorted(
        t["key"] for t in (coverage.get("terms") or [])
        if t.get("verdict") == "captured" and abs(float(t.get("weight") or 0.0)) > 0
    )
