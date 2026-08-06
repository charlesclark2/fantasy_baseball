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

import pandas as pd

from .monitors import DEFAULT_THRESHOLDS, MonitorReport, ResolutionThresholds, evaluate
from .names import normalize_team
from .resolver import ResolutionSpec, resolve

log = logging.getLogger("nfl.entity.props")

__all__ = [
    "PROPS_SPEC",
    "PROPS_SPEC_UNCONSTRAINED",
    "MARKET_POSITION_HINT",
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
)

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
    thresholds: ResolutionThresholds = DEFAULT_THRESHOLDS,
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
    report = evaluate(
        out,
        source_name=PROPS_SPEC.source_name,
        n_input_rows=n_in,
        thresholds=thresholds,
        high_value_mask=_target_book_mask(out),
    )
    return out, report


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
