"""props_identity.py — NF-W0b: the name-only Odds-API prop identity leg (§12A).

CONSUMER NOTE: this leg serves the MARKET/props vertical (`stg_nfl_props_historical` →
`mart_nfl_clv_props`), NOT NF-W1 — the weekly model excludes markets as features. It pairs with
the props-capture enablement, and today `mart_nfl_clv_props` carries a bare `player_name` with the
comment "a later props-CLV story can xref on name+team". This is that xref, done under the §12A
rules rather than as a convenient fuzzy join.

⛔ THE RULE THAT SHAPES EVERYTHING HERE: "Name-only props cannot be joined on fuzzy name alone."

An Odds-API prop outcome carries a player NAME and nothing else — no vendor id, no team, no
position. `outcomes[].description` is the player; `outcomes[].name` is the side (Over/Under).
So a naive implementation is a global fuzzy name join, which is precisely the failure §12A names:
two "Josh Allen"s (a QB and an edge rusher), a "Michael Carter" on two rosters, a rookie whose
name has not landed in our roster yet — each silently mis-prices a prop with no error anywhere.

WHERE THE CONSTRAINT COMES FROM. A prop is not actually name-only in context: it belongs to an
EVENT, and an event has exactly two teams. `resolve_prop_players` derives the block from the
event's `home_team`/`away_team` — so a candidate must be a player on one of the two teams playing
that game, in that season. That is a genuine constraint (a ~106-player universe instead of ~2,000),
and it is what upgrades the fuzzy rung from forbidden to permitted.

⛔ AND IT IS ENFORCED, NOT DOCUMENTED. A prop row whose event teams cannot be resolved gets
`allow_name_tiers = False` via an EMPTY block — the ladder then refuses tiers 3–4 outright and the
row lands unresolved. There is no code path in which a name is matched without a team constraint,
which is the difference between a rule and a comment (this repo's INC-38 lesson: a guard that
prose can satisfy is not a guard).

A MARKET CONSTRAINT, DELIBERATELY NOT USED AS A FILTER. `player_pass_yds` implies a QB, so it is
tempting to require position agreement. It is used only as a TIE-BREAK, never a filter: a
gadget-play pass attempt by a WR is a real prop, and filtering on the implied position would drop
it silently — trading a wrong match for a silent drop, which §12A forbids more strongly.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from .monitors import DEFAULT_THRESHOLDS, MonitorReport, ResolutionThresholds, evaluate
from .names import normalize_for_matching, normalize_team
from .resolver import ResolutionSpec, resolve

log = logging.getLogger("nfl.entity.props")

__all__ = [
    "NON_PLAYER_OUTCOME_RE",
    "PROPS_SPEC",
    "PROPS_SPEC_UNCONSTRAINED",
    "PROPS_THRESHOLDS",
    "MARKET_POSITION_HINT",
    "duplicate_name_floor",
    "is_non_player_outcome",
    "resolve_prop_players",
]

# The block is the EVENT — the two teams playing. `_event_team` is derived below.
PROPS_SPEC = ResolutionSpec(
    source_name="oddsapi.player_props",
    vendor_id_column=None,            # name-only by construction — there is no vendor id to try
    name_column="player_name",
    team_column=None,                 # a prop names no team; the EVENT supplies the constraint
    position_column=None,
    block_columns=("season", "_event_team"),
    # Books write the same player several ways ("Gabe"/"Gabriel Davis", "Chig"/"Chigoziem
    # Okonkwo") — 2,827 measured unresolved rows that ARE real players. Aliasing is enabled HERE
    # and nowhere else; the snap leg is validated and must not move (PM Q1).
    name_aliasing=True,
)

# ⭐ THE PROPS LEG'S PRE-REGISTERED THRESHOLDS (PM decisions Q2/Q3/Q4).
#
# tier='alert'  — props are on no serving path, so a breach pages and PROCEEDS (Q4).
# max_unmatched_rate=None — DEFERRED, and that is NOT "no limit" and NOT "healthy". The 0.02 bar
#   was pre-registered off the SNAP leg's baseline (0.68–1.24%); props genuinely sit above it, and
#   refitting a bar because it caught something is the E2.1-r inversion. The real bar is a PRODUCT
#   quantity — what share of prop lines the CLV vertical can afford to lose — FLOORED by the
#   irreducible duplicate-name-abstention rate `duplicate_name_floor` computes from the payload.
#   It is set when that vertical is built; `deferred_thresholds` keeps it visibly unset until then.
# max_high_value_unmatched=None — report + alert, no hard gate (Q3); its threshold is likewise set
#   with the vertical as a trend/spike rather than a fitted absolute.
PROPS_THRESHOLDS = ResolutionThresholds(
    tier="alert",
    max_unmatched_rate=None,
    max_low_confidence_rate=None,
    max_high_value_unmatched=None,
    require_evaluated=True,
)

# ⛔ NON-PLAYER MARKET OUTCOMES — not identity failures, because they are not players (PM Q1).
# Measured on the live 2023–24 payload, 2,988 of the 5,815 "no roster" rows are these:
#   • TEAM DEFENSES  — 2,493 rows / 131 name variants: "Miami Dolphins D/ST", "Buffalo Defense",
#     "Kansas City Defense". A defensive/special-teams TD is a real market outcome scored by a
#     TEAM, and no player crosswalk can or should resolve it.
#   • MARKET LEGS    — 495 rows: "No Touchdown" (the No side of anytime-TD).
# These leave the monitor DENOMINATOR but NOT the frame — the rows survive, flagged
# `is_non_player_outcome`, so nothing is silently dropped (§12A silent_drop_count = 0).
# ⚠️ Deliberately CONSERVATIVE: it matches an explicit defense/market token, never a shape
# heuristic. A heuristic that guessed "this looks like a team" would eventually eat a real player,
# and a wrongly-excluded player is an identity failure hidden from the very monitor built to see it.
NON_PLAYER_OUTCOME_RE = re.compile(
    r"(?:\bd/?st\b|\bdefense\b|\bdefence\b|\bspecial\s+teams\b|\bno\s+touchdown\b|\bno\s+scorer\b"
    r"|\bany\s+other\b|\bfield\s+goal\b)",  # non-capturing: a capture group makes pandas warn
    re.I,
)


def is_non_player_outcome(names: pd.Series) -> pd.Series:
    """True where an outcome's description names a TEAM or a market leg rather than a player."""
    if names is None or len(names) == 0:
        return pd.Series(dtype=bool)
    s = names.astype("string").fillna("")
    return s.str.contains(NON_PLAYER_OUTCOME_RE, regex=True).fillna(False).astype(bool)

# The same source with NO constraint — the shape a prop takes when its event cannot be resolved.
# Kept as a named constant so the "name-only is refused" behaviour is directly testable and cannot
# be reached by accident.
PROPS_SPEC_UNCONSTRAINED = ResolutionSpec(
    source_name="oddsapi.player_props",
    name_column="player_name",
    block_columns=(),
)

# Market → the position it usually implies. A TIE-BREAK ONLY (see the module docstring).
MARKET_POSITION_HINT: dict[str, str] = {
    "player_pass_yds": "QB",
    "player_pass_tds": "QB",
    "player_pass_completions": "QB",
    "player_pass_attempts": "QB",
    "player_pass_interceptions": "QB",
    "player_rush_yds": "RB",
    "player_rush_attempts": "RB",
    "player_rush_tds": "RB",
    "player_reception_yds": "WR",
    "player_receptions": "WR",
    "player_reception_tds": "WR",
}


def _explode_to_event_teams(props: pd.DataFrame) -> pd.DataFrame:
    """One candidate row per (prop, event team) — the constraint the ladder blocks on.

    A prop names no team, so it is eligible against BOTH teams in its event. Exploding to two rows
    and requiring a UNIQUE winner across them is what keeps this honest: if the same normalized
    name matches a player on each side, the prop resolves to nothing rather than to a coin flip.
    """
    rows = []
    for side in ("home_team", "away_team"):
        if side not in props.columns:
            continue
        sub = props[["_row_id"]].copy()
        sub["_event_team"] = props[side].map(normalize_team)
        rows.append(sub)
    if not rows:
        return pd.DataFrame(columns=["_row_id", "_event_team"])
    out = pd.concat(rows, ignore_index=True)
    return out[out["_event_team"].astype("string").fillna("") != ""]


def resolve_prop_players(
    props: pd.DataFrame,
    *,
    targets: pd.DataFrame,
    thresholds: ResolutionThresholds = PROPS_THRESHOLDS,
    crosswalk: pd.DataFrame | None = None,
    reviewed: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, MonitorReport]:
    """Resolve name-only prop players to `canonical_player_id`, constrained by the event's teams.

    `props` is `stg_nfl_props_historical`-shaped: `player_name`, `season`, `home_team`,
    `away_team`, `market`, … `targets` is a season-grain identity universe carrying
    `canonical_player_id`, `player_name`, `team`, `position`, `season`.

    Returns (props + resolution columns, monitor report). Row-preserving: an unresolved prop is
    flagged `source_degraded`, never dropped — a dropped prop silently shrinks a CLV denominator
    and reads as better coverage than the data supports.
    """
    n_in = int(len(props)) if props is not None else 0
    if props is None or props.empty:
        return resolve(pd.DataFrame(), spec=PROPS_SPEC_UNCONSTRAINED), evaluate(
            pd.DataFrame(columns=["canonical_player_id", "match_method", "match_confidence"]),
            source_name=PROPS_SPEC.source_name, n_input_rows=n_in, thresholds=thresholds,
        )

    work = props.copy().reset_index(drop=True)

    # ⭐ RESOLVE DISTINCT IDENTITIES, NOT ROWS. A prop feed repeats the same player across every
    # market, book and side, but identity depends ONLY on (season, event teams, name) — so
    # resolving per-row does the same work tens of times over. Measured on the real 2023–24 lake
    # payload: 601,933 outcome rows collapse to 28,158 distinct identity tuples (21×), and the
    # per-row version did not finish in 10 minutes because the fuzzy rung is O(rows × candidates).
    # Dedupe → resolve → broadcast back is exact, not an approximation: two rows with the same key
    # are the same identity question, so they must get the same answer.
    key = [c for c in ("season", "home_team", "away_team", "player_name") if c in work.columns]
    ident = work[key].drop_duplicates().reset_index(drop=True) if key else work
    ident["_row_id"] = range(len(ident))

    # A prop whose event teams are unusable gets NO name rung at all (the §12A hard rule).
    pairs = _explode_to_event_teams(ident)
    resolvable = set(pairs["_row_id"].tolist()) if not pairs.empty else set()
    if not resolvable:
        out = resolve(work, spec=PROPS_SPEC_UNCONSTRAINED, crosswalk=crosswalk, reviewed=reviewed)
        log.warning(
            "ALERT [nfl/entity/props] no event team resolved for ANY of %d prop rows — name tiers "
            "REFUSED (name-only props are never fuzzy-joined alone, v3 §12A).", len(work),
        )
        return _finalize(out, work, thresholds, n_in)

    # Candidate frame: each distinct identity paired with each of its event's teams.
    cand = pairs.merge(ident, on="_row_id", how="left")
    # The identity universe must carry the SAME block column the props side blocks on, or
    # `resolve` refuses the name tiers (a partial block is not a constraint). `_event_team` is the
    # target's own team, normalized — the join is "is this player on one of the two teams playing".
    tg = targets.copy() if targets is not None else pd.DataFrame()
    if not tg.empty and "team" in tg.columns:
        tg["_event_team"] = tg["team"].map(normalize_team)
    resolved_cand = resolve(
        cand,
        spec=PROPS_SPEC,
        crosswalk=crosswalk,
        reviewed=reviewed,
        targets=tg,
        target_name_column="player_name",
        target_team_column="team",
        target_position_column="position",
    )

    # Collapse the two sides back to one row per prop. A name that matched a DIFFERENT canonical
    # player on each side is an ambiguity → unresolved (never "pick the higher score").
    # ⚠️ CURRENTLY UNREACHABLE, AND SAID OUT LOUD SO NOBODY MISTAKES IT FOR A TESTED GUARD: for
    # the two sides to disagree, one normalized name must map to two canonical players, which IS
    # the resolver's season-scope ambiguity condition — so the resolver abstains first and this
    # branch never decides a row (proven while trying to RED-prove it; see
    # `test_the_two_sided_collapse_is_subsumed_by_the_season_scope_rule`). Kept as a backstop in
    # case a future spec narrows `ambiguity_scope_columns`, not because it has been exercised.
    hits = resolved_cand[resolved_cand["canonical_player_id"].notna()]
    if hits.empty:
        best = pd.DataFrame(columns=["_row_id", "canonical_player_id", "match_method",
                                     "match_confidence", "match_score"])
    else:
        agg = hits.groupby("_row_id").agg(
            n_ids=("canonical_player_id", "nunique"),
            canonical_player_id=("canonical_player_id", "first"),
            match_method=("match_method", "first"),
            match_confidence=("match_confidence", "max"),
            match_score=("match_score", "max"),
        ).reset_index()
        ambiguous = int((agg["n_ids"] > 1).sum())
        if ambiguous:
            log.warning(
                "ALERT [nfl/entity/props] %d prop rows matched a DIFFERENT player on each side of "
                "the event — left UNRESOLVED rather than arbitrated.", ambiguous,
            )
        best = agg[agg["n_ids"] == 1].drop(columns=["n_ids"])

    # Broadcast the per-identity answer back onto EVERY prop row that asked the same question.
    # The merge is on the identity KEY (not `_row_id`, which now indexes identities, not rows), and
    # the row count is asserted below — a many-to-one broadcast that fanned out would silently
    # multiply a CLV denominator.
    n_before = len(work)
    resolved_ident = ident.merge(best, on="_row_id", how="left").drop(columns=["_row_id"])
    out = work.merge(resolved_ident, on=key, how="left") if key else work.assign(**{
        c: best[c] for c in ("canonical_player_id", "match_method", "match_confidence", "match_score")
    })
    if len(out) != n_before:
        raise AssertionError(
            f"prop identity broadcast changed the row count ({n_before} → {len(out)}); the "
            "identity key must be unique per distinct question (v3 §12A silent_drop_count = 0)"
        )
    out["match_method"] = out["match_method"].fillna("manual_review")
    out["match_confidence"] = pd.to_numeric(out["match_confidence"], errors="coerce").fillna(0.0)
    out["canonical_player_id"] = out["canonical_player_id"].astype("string")
    out["source_degraded"] = out["canonical_player_id"].isna()
    return _finalize(out, work, thresholds, n_in)


def _finalize(
    out: pd.DataFrame, work: pd.DataFrame, thresholds: ResolutionThresholds, n_in: int
) -> tuple[pd.DataFrame, MonitorReport]:
    out = out.drop(columns=[c for c in ("_row_id", "_event_team") if c in out.columns])
    if "match_score" not in out.columns:
        out["match_score"] = float("nan")
    # Mark, never drop: a non-player leg stays in the frame and leaves only the DENOMINATOR.
    non_player = (
        is_non_player_outcome(out["player_name"]) if "player_name" in out.columns
        else pd.Series(False, index=out.index)
    )
    out["is_non_player_outcome"] = non_player.reindex(out.index).fillna(False).astype(bool)
    report = evaluate(
        out,
        source_name=PROPS_SPEC.source_name,
        n_input_rows=n_in,
        thresholds=thresholds,
        high_value_mask=_target_book_mask(out),
        identity_mask=~out["is_non_player_outcome"],
    )
    return out, report


def duplicate_name_floor(
    props: pd.DataFrame, targets: pd.DataFrame, *, name_column: str = "player_name"
) -> dict:
    """⭐ THE IRREDUCIBLE ABSTENTION FLOOR (PM decision Q2) — a DESIGN quantity, not a fitted one.

    Some share of prop rows can NEVER resolve, no matter how good the ladder gets: their name maps
    to more than one canonical player in that season (two Josh Allens, two Lamar Jacksons), and the
    season-scope ambiguity rule correctly refuses to guess. That share is a property of the NFL's
    name collisions and the book's naming, computable from the payload BEFORE any threshold is
    chosen — which is exactly what makes it a legitimate floor to pre-register against, rather than
    a number reverse-engineered from a run we wanted to pass.

    Any future `max_unmatched_rate` for props must sit ABOVE this floor; a bar below it would be
    unsatisfiable by construction (the E7.14 "BH unattainable at 5 folds" shape — a gate no effect
    of any size could pass).

    Returns the floor plus the collision inventory behind it, so the derivation travels with it.
    """
    if props is None or props.empty or targets is None or targets.empty:
        return {"floor_rate": None, "n_rows": 0, "n_colliding_rows": 0, "n_colliding_names": 0,
                "colliding_names": [], "note": "unevaluable — empty payload or identity universe"}

    t = targets.copy()
    t["_nn"] = t["player_name"].astype("string").fillna("").map(
        lambda v: normalize_for_matching(v, aliasing=PROPS_SPEC.name_aliasing)
    )
    collisions = t.groupby(["season", "_nn"])["canonical_player_id"].nunique()
    colliding = {k for k, v in collisions.items() if v > 1}

    p = props.copy()
    p["_nn"] = p[name_column].astype("string").fillna("").map(
        lambda v: normalize_for_matching(v, aliasing=PROPS_SPEC.name_aliasing)
    )
    identity_rows = p[~is_non_player_outcome(p[name_column])]
    hit = [(s, n) in colliding for s, n in zip(identity_rows["season"], identity_rows["_nn"])]
    n_rows = int(len(identity_rows))
    n_hit = int(sum(hit))
    names = sorted(identity_rows.loc[hit, name_column].dropna().unique().tolist())
    return {
        "floor_rate": round(n_hit / n_rows, 6) if n_rows else None,
        "n_rows": n_rows,
        "n_colliding_rows": n_hit,
        "n_colliding_names": len(names),
        "colliding_names": names[:40],
        "note": (
            "Irreducible: these rows name a player whose season-normalized name maps to >1 "
            "canonical player, so the ladder abstains BY DESIGN. Any props max_unmatched_rate "
            "must be pre-registered ABOVE this floor."
        ),
    }


def _target_book_mask(props: pd.DataFrame) -> pd.Series | None:
    """The §12A high-value population for props: the TARGET BOOK's lines.

    An unresolved prop at a book we do not grade against is inventory; an unresolved prop at the
    target book (`reference_target_bookmaker` = Bovada) is a hole in the CLV series the props
    vertical is actually measured on. Same argument as the snap side's starter filter — a flat
    rate over every book would average the two into a number that moves with book coverage rather
    than with damage.
    """
    if "bookmaker" not in props.columns or props.empty:
        return None
    return props["bookmaker"].astype("string").str.lower().eq("bovada").astype("boolean").fillna(False).astype(bool)
