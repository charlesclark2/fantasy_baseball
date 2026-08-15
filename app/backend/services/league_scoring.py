"""NF-EPIC 1 — score a league board SERVER-SIDE, in bare Python.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ WHY THIS EXISTS, AND WHY IT IS A THIRD IMPLEMENTATION
═══════════════════════════════════════════════════════════════════════════════════════════════════

The PM's Option C (2026-08-10): the raw stat line is PAID and must not reach a free or anonymous
caller — but G100-C1's ONE FREE PERSONALIZED LEAGUE stays. Those two only coexist if the league is
scored where the stat line already is: on the server. The browser then receives a board it could not
have computed, and never sees the substrate.

There are now three implementations of one scoring policy, and it is worth being blunt about why:

  1. `fantasy_engine/scoring.py` + `vor.py`  — pandas/numpy. Produces the SHIPPED PRESET BOARDS via
     `export_draft_board_json.py`. **This module is the authority.**
  2. `frontend/lib/league-scoring.ts`        — the browser port (NF-C0b), for instant re-score on edit.
  3. THIS MODULE                             — bare Python for the API Lambda, which bundles neither
     pandas/numpy nor `quant_sports_intel_models` (its zip already sits near the size cap).

⛔ A third implementation is a drift hazard, not a free lunch. `test_nf_epic1_parity.py` runs THIS
module and `fantasy_engine` over the SAME payload rows and asserts they agree field-for-field. That
guard is load-bearing — the PM called it out by name — because a silent drift means a free user's
league board disagrees with the preset board we sell, and nothing would surface it.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ IT MIRRORS `fantasy_engine`, NOT THE TS PORT — AND THE TWO ALREADY DISAGREE
───────────────────────────────────────────────────────────────────────────────────────────────────

Found while porting, and it decided the target: on the interval bounds the two existing engines are
NOT byte-identical.

    fantasy_engine   p10 = floor(lo × 10)/10      p90 = ceil(hi × 10)/10     (widen — conservative)
    league-scoring.ts p10 = round(lo × 10)/10     p90 = round(hi × 10)/10    (nearest)

and where the base projection is ~0 the TS port emits `null` bounds while the Python engine emits
floor/ceil of the point estimate. So a custom league scored in the browser could already differ from
a PRESET board by up to 0.05 on a bound. This module follows **fantasy_engine + the exporter's
`round(x, 1)`**, because the risk the PM named is "the free user's league disagrees with the board",
and the board is what `fantasy_engine` produced. A side effect is that custom leagues now agree with
presets where they previously did not.

⚠️ Python's `round` is round-half-EVEN and JS `Math.round` is round-half-UP. Matching the exporter's
`round` is therefore also part of matching the board; do not "fix" it to half-up.
"""

from __future__ import annotations

import math

#: 80% two-sided normal quantile — the projection's own interval convention (`scoring._Z80`).
Z80 = 1.2815515594

#: Mirror of `NFL_PROFILE.position_aliases`. The exporter already folds these; this is the same
#: defensive second pass the TS port keeps, for a stored config that predates the fold.
POSITION_ALIASES: dict[str, str] = {
    "FB": "RB",
    "DEF": "DST", "D/ST": "DST", "DEFENSE": "DST", "D": "DST",
    "PK": "K", "KICKER": "K",
}

#: The payload's own point/interval fields — the base the rescore carries through. These are the
#: PUBLIC counterparts of `NFL_PROFILE.base_*_column`, and they stay public (see
#: `projection_fields`): they describe the FREE PPR number, not the paid substrate.
BASE_POINTS_FIELD = "fpPpr"
BASE_SD_FIELD = "fpSd"
BASE_P10_FIELD = "fpP10"
BASE_P90_FIELD = "fpP90"

#: Mirror of `league_presets.FG_DERIVED_BUCKETS` / the TS `FG_DERIVED_BUCKETS`. A league's six
#: distance buckets fold onto the projection's three; the fold is EXACT whenever the fine values
#: inside a projected bucket agree, which is the common case.
FG_DERIVED_BUCKETS: tuple[tuple[str, str, float], ...] = (
    ("fg_made_0_19", "fg_made_0_39", 0.02),
    ("fg_made_20_29", "fg_made_0_39", 0.30),
    ("fg_made_30_39", "fg_made_0_39", 0.68),
    ("fg_made_50_59", "fg_made_50_plus", 0.88),
    ("fg_made_60p", "fg_made_50_plus", 0.12),
)

_EPS = 1e-12


def normalize_position(pos: str | None) -> str:
    if pos is None:
        return ""
    return POSITION_ALIASES.get(str(pos), str(pos))


def _num(row: dict, field: str | None) -> float:
    """A NaN/None-safe numeric read. An absent column contributes 0 to ITS term only.

    ⚠️ NOT a truthiness check — `0.0` is a real value and `False` is not a number. Mirrors
    `scoring._stat_series` (`to_numeric(errors="coerce").fillna(0.0)`).
    """
    if not field:
        return 0.0
    v = row.get(field)
    if isinstance(v, bool) or v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def available_fields(players: list[dict]) -> set[str]:
    """Payload fields carrying at least one real number — the input to MECHANICAL coverage.

    ⭐ THIS IS WHY THE SERVER MUST SCORE OFF THE **FULL** PAYLOAD. Run against the public (reduced)
    blob, every scorable field would be absent, every term would downgrade to `captured`, and the
    board would score all-zero while reporting itself as covered. `build_board`'s caller is
    responsible for handing in the full rows; `score_league` asserts it.
    """
    out: set[str] = set()
    for p in players:
        for k, v in p.items():
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)) and not math.isnan(float(v)):
                out.add(k)
    return out


def resolve_scoring(
    scoring: dict,
    *,
    stat_field: dict[str, str],
    fields: set[str] | None = None,
    captured_rules: list[str] | None = None,
) -> tuple[dict, dict]:
    """Fold a league's scoring onto what the projection can express; report what actually applies.

    Port of `fantasy_engine/settings.resolve_scoring` and the TS `resolveScoring`. A term with no
    projection behind it is CAPTURED (kept for fidelity, never scored) rather than silently zeroed
    behind an "applied" label.
    """
    captured_rules = list(captured_rules or [])
    per_stat: dict = dict(scoring.get("per_stat") or {})

    def is_projected(key: str) -> bool:
        field = stat_field.get(key)
        if not field:
            return False
        return field in fields if fields is not None else True

    resolved: dict[str, float] = {}
    terms: list[dict] = []
    handled_fine: set[str] = set()

    # 1. fold the fine FG buckets the user actually set
    by_projected: dict[str, list[tuple[str, str, float]]] = {}
    for bucket in FG_DERIVED_BUCKETS:
        by_projected.setdefault(bucket[1], []).append(bucket)

    for projected_key, buckets in by_projected.items():
        present = [b for b in buckets if b[0] in per_stat]
        if not present:
            continue
        if not is_projected(projected_key):
            for fine_key, _proj, _share in present:
                handled_fine.add(fine_key)
                terms.append({
                    "key": fine_key, "verdict": "captured",
                    "weight": _as_float(per_stat.get(fine_key)), "exact": True,
                    "note": "no projection backs this scoring term",
                })
            continue
        values = [_as_float(per_stat.get(b[0])) for b in present]
        exact = (max(values) - min(values)) <= 1e-9
        if exact:
            folded = values[0]
        else:
            total_share = sum(max(0.0, b[2]) for b in present)
            if total_share > 0:
                folded = sum(
                    _as_float(per_stat.get(b[0])) * max(0.0, b[2]) for b in present
                ) / total_share
            else:
                folded = sum(values) / len(values)
        resolved[projected_key] = folded
        for fine_key, _proj, _share in present:
            handled_fine.add(fine_key)
            terms.append({
                "key": fine_key, "verdict": "derived",
                "weight": _as_float(per_stat.get(fine_key)),
                "projectedKey": projected_key, "exact": exact,
                "note": "" if exact else (
                    "the projection resolves this stat more coarsely, so buckets that score "
                    "differently are combined by their attempt share"
                ),
            })

    # 2. everything else passes through, classified against the data actually present
    for key, raw in per_stat.items():
        if key in handled_fine:
            continue
        weight = _as_float(raw)
        if key in resolved:
            terms.append({
                "key": key, "verdict": "derived", "weight": weight,
                "projectedKey": key, "exact": True,
                "note": "superseded by the per-bucket values set for this stat",
            })
            continue
        resolved[key] = weight
        if abs(weight) <= _EPS:
            continue  # a zeroed term is a non-statement
        applied = is_projected(key)
        terms.append({
            "key": key, "verdict": "applied" if applied else "captured",
            "weight": weight, "exact": True,
            "note": "" if applied else "no projection backs this scoring term",
        })

    terms.sort(key=lambda t: (t["verdict"], t["key"]))
    report = {
        "terms": terms,
        "capturedRules": captured_rules,
        "hasApproximation": any(t["verdict"] == "derived" and not t["exact"] for t in terms),
    }
    return {"per_stat": resolved, "position_bonuses": scoring.get("position_bonuses") or {}}, report


def _as_float(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def score_row(row: dict, pos: str, resolved: dict, stat_field: dict[str, str]) -> dict:
    """One projection row → points and the carried 80% interval (`scoring.score_players`).

    The interval is a first-order RESCALE of the projection's own dispersion, not a re-derivation:
    we have no per-format game logs. Where the payload publishes its own bounds, EACH SIDE is
    carried by the ratio the point moved, so an ASYMMETRIC band survives — right for a rookie whose
    p10 is near zero while his p90 is a real season (NF1.7). The CV path is the fallback.
    """
    pts = 0.0
    for stat_key, weight in (resolved.get("per_stat") or {}).items():
        w = _as_float(weight)
        if w == 0.0:
            continue
        pts += w * _num(row, stat_field.get(stat_key))

    bonus = (resolved.get("position_bonuses") or {}).get(pos)
    if bonus:
        for stat_key, weight in bonus.items():
            w = _as_float(weight)
            if w == 0.0:
                continue
            pts += w * _num(row, stat_field.get(stat_key))

    base_pts = _num(row, BASE_POINTS_FIELD)
    base_sd = _num(row, BASE_SD_FIELD)

    cv = (base_sd / base_pts) if base_pts > 1e-9 else 0.0
    league_sd = abs(cv * pts)
    lo = max(0.0, pts - Z80 * league_sd)
    hi = pts + Z80 * league_sd

    b_lo = _num(row, BASE_P10_FIELD)
    b_hi = _num(row, BASE_P90_FIELD)
    usable = base_pts > 1e-9 and b_hi >= b_lo and (b_hi > 0 or b_lo > 0)
    if usable:
        k = pts / base_pts
        lo = max(0.0, b_lo * k)
        hi = b_hi * k

    # coherence: a displayed interval must contain its own point estimate (NF1.7)
    lo = max(0.0, min(lo, pts))
    hi = max(hi, pts)

    # ⚠️ floor/ceil, NOT round — this is the `fantasy_engine` convention the shipped boards carry.
    return {"pts": pts, "p10": math.floor(lo * 10.0) / 10.0, "p90": math.ceil(hi * 10.0) / 10.0}


def replacement_levels(rows: list[dict], cfg: dict) -> tuple[dict[str, float], dict[str, int]]:
    """`(replacement_by_position, started_by_position)` — `vor.compute_replacement_levels`.

    THE SUBTLE PART is the flex allocation: demand is dedicated starters PLUS that position's share
    of the flex pool, and the pool is filled by the best remaining players ACROSS eligible positions,
    most-restrictive slot first — so a QB-eligible SUPERFLEX never poaches a player a strict FLEX
    still needed. Under superflex that pulls the best remaining QBs into starting lineups, QB
    replacement drops deep and QB VOR jumps, which is the face-validity proof the scarcity math is
    right.
    """
    n_teams = int(cfg.get("n_teams") or 0)
    roster = list(cfg.get("roster") or [])

    ranked: dict[str, list[float]] = {}
    for r in rows:
        ranked.setdefault(r["pos"], []).append(r["pts"])
    for pos in ranked:
        ranked[pos].sort(reverse=True)

    started: dict[str, int] = {pos: 0 for pos in ranked}

    starters = [s for s in roster if not s.get("bench") and int(s.get("count") or 0) > 0]
    for s in starters:
        eligible = list(s.get("eligible") or [])
        if len(eligible) == 1:
            pos = eligible[0]
            started[pos] = started.get(pos, 0) + n_teams * int(s.get("count") or 0)

    spots: list[list[str]] = []
    for s in starters:
        eligible = list(s.get("eligible") or [])
        if len(eligible) > 1:
            spots.extend([eligible] * (n_teams * int(s.get("count") or 0)))
    spots.sort(key=len)  # most-restrictive first

    for eligible in spots:
        best_pos, best_pts = None, -math.inf
        for pos in eligible:
            arr = ranked.get(pos)
            idx = started.get(pos, 0)
            if arr is not None and idx < len(arr) and arr[idx] > best_pts:
                best_pts, best_pos = arr[idx], pos
        if best_pos is not None:
            started[best_pos] = started.get(best_pos, 0) + 1

    replacement: dict[str, float] = {}
    for pos, arr in ranked.items():
        idx = started.get(pos, 0)
        if not arr:
            v = 0.0
        elif idx < len(arr):
            v = arr[idx]          # first non-starter = the free replacement
        else:
            v = arr[-1]           # thinner than demand ⇒ weakest rostered
        replacement[pos] = max(0.0, v)
    return replacement, {p: int(c) for p, c in started.items()}


def build_board(players: list[dict], cfg: dict, stat_field: dict[str, str]) -> dict:
    """A FULL projection payload + a league config → the ranked board (`vor.build_board`).

    Returns rows in the SAME shape the pre-exported preset boards use, so every consumer — the
    board, VOR, the draft optimizer — reads a hand-entered league through the identical interface
    it reads a preset. That equivalence is the point; a caller must not be able to tell which.
    """
    fields = available_fields(players)
    resolved, report = resolve_scoring(
        cfg.get("scoring") or {},
        stat_field=stat_field,
        fields=fields,
        captured_rules=list((cfg.get("captured_rules") or {}).keys()),
    )

    # rank only positions the league can actually start or bench
    rosterable: set[str] = set()
    for s in cfg.get("roster") or []:
        if int(s.get("count") or 0) <= 0:
            continue
        rosterable.update(s.get("eligible") or [])

    rows: list[dict] = []
    for p in players:
        pos = normalize_position(p.get("pos"))
        if rosterable and pos not in rosterable:
            continue
        scored = score_row(p, pos, resolved, stat_field)
        rows.append({"player": p, "pos": pos, **scored})

    replacement, started = replacement_levels(rows, cfg)

    # positional rank by POINTS within position, ties broken by original order (pandas rank "first")
    by_pos: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_pos.setdefault(r["pos"], []).append(i)
    pos_rank: dict[int, int] = {}
    for _pos, idxs in by_pos.items():
        for rank, i in enumerate(sorted(idxs, key=lambda i: (-rows[i]["pts"], i)), start=1):
            pos_rank[i] = rank

    out: list[dict] = []
    for i, r in enumerate(rows):
        p = r["player"]
        repl = replacement.get(r["pos"], 0.0)
        out.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "pos": r["pos"],
            "team": p.get("team"),
            "bye": p.get("bye"),
            "rookie": bool(p.get("rookie")),
            "g": p.get("g"),
            "pts": _round1(r["pts"]),
            "repl": _round1(repl),
            "vor": _round1(r["pts"] - repl),
            "posRank": pos_rank.get(i, 0),
            "ovrRank": 0,  # assigned after the VOR sort
            "vorP10": _round1(r["p10"] - repl),
            "vorP90": _round1(r["p90"] - repl),
            "ptsP10": _round1(r["p10"]),
            "ptsP90": _round1(r["p90"]),
            "adp": p.get("adp"),
            "lowPred": p.get("lowPred"),
            "predNote": p.get("predNote"),
            "_i": i,
            # ⚠️ THE UNROUNDED VOR, KEPT ONLY TO SORT ON — see below. Stripped before returning.
            "_vor_raw": r["pts"] - repl,
        })

    # STABLE sort by VOR descending — `vor.build_board` uses mergesort, so ties keep frame order.
    #
    # ⚠️ SORTS ON THE UNROUNDED VOR, AND THAT IS NOT A DETAIL. Sorting on the ROUNDED value instead
    # collapses players whose VOR differs in the second decimal into a tie, which the index tiebreak
    # then orders by frame position rather than by value — the parity guard caught exactly this as
    # 32 adjacent `ovrRank` swaps (28↔29, 92↔93 …) while every points/VOR/interval field agreed. The
    # engine rounds only at the exporter, i.e. AFTER ordering, so ordering must see the raw float.
    out.sort(key=lambda row: (-row["_vor_raw"], row["_i"]))
    for rank, row in enumerate(out, start=1):
        row["ovrRank"] = rank
        row.pop("_i", None)
        row.pop("_vor_raw", None)

    return {
        "players": out,
        "replacement": {k: _round1(v) for k, v in replacement.items()},
        "started": started,
        "coverage": report,
    }


def _round1(v: float | None) -> float | None:
    """The exporter's `_fnum` — `round(x, 1)`, Python's round-half-EVEN.

    ⚠️ Deliberately not half-up. The shipped boards were written through Python's `round`, so
    matching the board means matching its tie behaviour too.
    """
    if v is None:
        return None
    f = _as_float(v)
    return round(f, 1)


# ── NF-C6 roster join, moved server-side with the scorer ─────────────────────────────────────────
# Port of `league-scoring.ts::normalizePlayerName` / `matchRosterToBoard`. It moves here for the
# same reason the scorer did: the join needs a SCORED BOARD, and the board can no longer be built in
# a free user's browser. A miss is a REAL, expected outcome (a spelling divergence, a DST rendered
# as a team abbreviation, a platform id NF-C0c never resolved to a name) and is surfaced, never
# hidden — matching NF-C0c's own "matched N of M" convention.

#: ⚠️ THE STEP ORDER IS LOAD-BEARING AND MIRRORS THE TS REGEX CHAIN EXACTLY.
#: Suffix words are removed from the LOWERCASED, still-punctuated string, and only then is
#: everything outside `[a-z ]` dropped. Doing it the other way round — strip punctuation first,
#: then filter suffix TOKENS — is not equivalent: "I.V. Jones" folds to "iv jones" under that order
#: and "iv" then reads as a generational suffix, deleting a real initial. Contrived, but the two
#: implementations must agree on every input or a roster that matched in the browser silently stops
#: matching on the server, which presents as "my players disappeared".
_SUFFIX_RE = r"\b(jr|sr|ii|iii|iv|v)\b\.?"
#: The same combining-marks block the TS `replace(/[̀-ͯ]/g, "")` strips. Deliberately the
#: explicit range rather than `unicodedata.combining`, which covers more blocks and would fold a
#: character the browser keeps.
_COMBINING_RE = r"[̀-ͯ]"


def normalize_player_name(name: str) -> str:
    """ASCII-fold, drop generational suffixes and punctuation, collapse whitespace.

    ⚠️ Must agree with the TS `normalizePlayerName` character-for-character or a roster that
    matched in the browser stops matching on the server. `test_nf_epic1_parity.py` pins a table of
    real awkward names (accents, suffixes, apostrophes, periods) across both.
    """
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", name or "")
    s = re.sub(_COMBINING_RE, "", s).lower()
    s = re.sub(_SUFFIX_RE, "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# NF-C6P3 — THE D/ST JOIN. A team defence is not a person, and the name join never worked on it.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# Measured on the real captured ESPN league (`espn_league_642070_2025_drafted.json`, 10 teams / 172
# players): the board publishes a team unit as **"DET D/ST"** and every platform publishes it under
# its NICKNAME — ESPN "Lions D/ST", Sleeper "Detroit Lions", Yahoo "Detroit". Fold both through
# `normalize_player_name` and you get `det dst` against `lions dst`: no match, ever, for any team,
# on any platform.
#
# ⚠️ AND THE FAILURE IS SILENT AND EXPENSIVE. The miss is a legitimate `board: None` row, so nothing
# errors — it lands in the report's "we could not resolve" list while the D/ST STARTING SLOT sits
# empty and contributes exactly ZERO to the headline team total. A number that is confidently wrong
# and renders perfectly (the E9.46 class), on the one figure this whole surface is opened to read.
#
# ⭐ THE FIX IS TO JOIN A UNIT ON ITS TEAM, NOT ON ITS NAME. A team defence is uniquely identified by
# its franchise, both sides carry that franchise, and a name is a lossy rendering of it. So for a
# DST row the key becomes `dst|<abbreviation>`, resolved in this order:
#
#     1. the row's own `team` field — the strongest signal, present on both sides and on every
#        adapter (ESPN "DET", Yahoo "Det", Sleeper "DET"); aliased so a platform's spelling of a
#        relocated franchise (OAK/LV, SD/LAC, STL/LAR, WSH/WAS, JAC/JAX, LA) lands on ours;
#     2. failing that, a NICKNAME in the name ("Lions D/ST", "Detroit Lions", "Bills");
#     3. failing that, an ABBREVIATION token in the name ("DET D/ST" — which is how OUR OWN board
#        names them, so this branch is what matches the board side when its `team` is absent).
#
# A row that resolves to nothing keeps the old name key and is reported unmatched, exactly as before:
# an absence is reported, never imputed. ⛔ There is deliberately NO fuzzy fallback — matching the
# WRONG defence would silently credit a user with points they did not draft, which is worse than the
# honest miss this replaces.
#
# ⚠️ THIS MAP MUST MIRROR THE TS PORT AND THE RESEARCH TREE'S FRANCHISE TABLE.
# `frontend/lib/league-scoring.ts` carries the same two maps (the E2E harness scores through it), and
# `coaching_source._FRANCHISE_ERAS` is the repo's existing franchise authority. Both are pinned
# mechanically by `betting_ml/tests/test_nf_c6p3_league_rosters.py` — a nickname added to one and not
# the others is a failing test, not a platform that quietly stops matching (the E9.61 "two renderers
# of one field are two rule sets" lesson, on the join side).

#: Franchise nickname → the abbreviation our board publishes. Lowercased single words, because that
#: is what survives `normalize_player_name` on every rendering a platform uses. Historical nicknames
#: are included: a league imported from an older season still names them that way, and a nickname is
#: never reused by a different franchise.
NFL_TEAM_BY_NICKNAME: dict[str, str] = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "jags": "JAX",
    "chiefs": "KC", "chargers": "LAC", "rams": "LAR", "raiders": "LV",
    "dolphins": "MIA", "vikings": "MIN", "patriots": "NE", "saints": "NO",
    "giants": "NYG", "jets": "NYJ", "eagles": "PHI", "steelers": "PIT",
    "seahawks": "SEA", "ers": "SF", "niners": "SF", "buccaneers": "TB",
    "bucs": "TB", "titans": "TEN", "commanders": "WAS", "redskins": "WAS",
    # ⚠️ THE ONLY TWO-WORD ENTRY, and it is why `dst_team` checks adjacent token PAIRS as well as
    # single tokens. Washington played as the "Football Team" for 2020–21, so a league imported from
    # those seasons names its defence that way — and the single token "team" cannot be the key,
    # because a defence rendered "Team 3 D/ST" would then resolve to Washington. Found by the guard
    # that walks `coaching_source._FRANCHISE_ERAS`, not by inspection.
    "football team": "WAS",
}
# ⚠️ "49ers" folds to "ers" under `normalize_player_name` (digits are outside `[a-z ]`), which is why
# the key above is "ers" rather than "49ers". It looks like a typo and is not — the map is keyed on
# what the NORMALIZER produces, because that is the only string the join ever sees.

#: A platform's team abbreviation → the one our board publishes. Only the DIVERGENCES are listed;
#: anything already matching passes through. Relocations dominate, because a league imported from an
#: older season carries the franchise's abbreviation at the time.
NFL_TEAM_ABBREV_ALIASES: dict[str, str] = {
    "OAK": "LV", "LVR": "LV",
    "SD": "LAC", "SDG": "LAC",
    "STL": "LAR", "LA": "LAR", "RAM": "LAR",
    "WSH": "WAS", "WFT": "WAS",
    "JAC": "JAX",
    "GNB": "GB", "KAN": "KC", "NWE": "NE", "NOR": "NO", "SFO": "SF", "TAM": "TB",
    "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
}

#: The abbreviations the board actually publishes — the set a resolution must land in. Derived from
#: the two maps' targets so it cannot drift from them.
NFL_TEAM_ABBREVIATIONS: frozenset[str] = frozenset(NFL_TEAM_BY_NICKNAME.values())


def normalize_team(team: str | None) -> str:
    """A platform's team abbreviation, as OUR board spells it. `""` when it is not resolvable.

    ⚠️ Returns `""` rather than the input for anything unrecognised. A DST key built from an
    unknown abbreviation would be a key that can only ever match itself, i.e. a silent no-match
    dressed up as a resolution; the caller falls back to the name instead and reports the miss.
    """
    t = str(team or "").strip().upper()
    if not t:
        return ""
    t = NFL_TEAM_ABBREV_ALIASES.get(t, t)
    return t if t in NFL_TEAM_ABBREVIATIONS else ""


def dst_team(name: str, team: str | None) -> str:
    """The franchise a D/ST row belongs to, or `""` when it cannot be resolved honestly.

    The three-step resolution documented above. Kept separate from `_join_key` so both the guard
    suite and the TS parity table can exercise it directly on real platform renderings.
    """
    resolved = normalize_team(team)
    if resolved:
        return resolved
    # `normalize_player_name` is what both sides of the join are folded through, so resolving off
    # its output (rather than off the raw string) is what makes "Lions D/ST", "lions d/st" and
    # "Detroit Lions" the same lookup.
    tokens = normalize_player_name(name).split()
    # Adjacent PAIRS before single tokens: the map has one two-word nickname ("football team") whose
    # second word must never be a key on its own. Pairs first so a name containing both a pair and a
    # single-token match resolves to the more specific one.
    for i in range(len(tokens) - 1):
        hit = NFL_TEAM_BY_NICKNAME.get(f"{tokens[i]} {tokens[i + 1]}")
        if hit:
            return hit
    for token in tokens:
        hit = NFL_TEAM_BY_NICKNAME.get(token)
        if hit:
            return hit
    # Our own board's rendering ("DET D/ST") — the abbreviation is a token of the RAW name, since
    # normalization lowercases it. Read off the raw string so "det" and "DET" both resolve.
    for token in str(name or "").replace("/", " ").split():
        hit = normalize_team(token)
        if hit:
            return hit
    return ""


def _join_key(name: str, pos: str | None, team: str | None) -> str:
    """The key both sides of the roster/board join are reduced to.

    Everyone but a team defence keys on `name|pos` exactly as before — this is deliberately NOT a
    rewrite of a join that works for 95% of a roster.
    """
    position = normalize_position(pos or "")
    if position == "DST":
        resolved = dst_team(name, team)
        if resolved:
            return f"DST|{resolved}"
    return f"{normalize_player_name(name)}|{position}"


def match_roster_to_board(roster: list[dict], board_players: list[dict]) -> list[dict]:
    """Join an imported roster onto an already-scored board, by normalized name + position.

    First match wins, and because the board arrives VOR-sorted that is the highest-VOR row — the
    same tiebreak the TS version documents.

    ⭐ NF-C6P3 — a D/ST row keys on its FRANCHISE instead (see the block above): the name join
    structurally never matched a team defence on any platform, which left the starting D/ST slot
    empty and silently absent from the headline total.
    """
    by_key: dict[str, dict] = {}
    for p in board_players:
        key = _join_key(str(p.get("name") or ""), p.get("pos"), p.get("team"))
        by_key.setdefault(key, p)

    out: list[dict] = []
    for r in roster:
        name = str(r.get("name") or "")
        if not name:
            out.append({"roster": r, "board": None})
            continue
        key = _join_key(name, r.get("position") or "", r.get("team"))
        out.append({"roster": r, "board": by_key.get(key)})
    return out
