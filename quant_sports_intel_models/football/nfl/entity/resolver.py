"""resolver.py — NF-W0b: the §12A match-order ladder.

    1. stable vendor id      (`pfr_id`, `espn_id`, … → canonical_player_id)             1.00
    2. reviewed crosswalk    (a human decision, never re-litigated by a later rung)     0.99
    3. exact normalized name + team + position-GROUP, unique candidate                  0.95
    4. constrained match     4a exact name + team, position RELAXED, unique             0.90
                             4b blocked Jaro-Winkler ≥ threshold, unique survivor  0.60–0.89
    5. manual review         UNRESOLVED — flagged source-degraded, recorded in QA       0.00

FOUR PROPERTIES THAT MAKE THIS MORE THAN A CHAIN OF MERGES:

⛔ (a) NAME-ONLY CANNOT REACH A FUZZY RUNG — MECHANICALLY. `ResolutionSpec.block_columns` names
the constraint a fuzzy candidate must be blocked inside. A spec with an EMPTY block set has its
tiers 3–4 refused outright (`allow_name_tiers` is False), so §12A's "name-only props cannot be
joined on fuzzy name alone" is a property of the code path, not a convention a caller can forget.
`props_identity` supplies the event's two teams as the block; a prop with no resolvable event
gets no name rung at all.

⛔ (b) AMBIGUITY IS AN UNRESOLVED, NOT A COIN FLIP. Every name rung requires the candidate to be
UNIQUE within its block. Two players who normalize to the same name in the same team-week do not
get the "first" one — they get no match, a QA record, and a `source_degraded` flag. A wrong merge
is far more expensive than a miss, because a miss is visible and a wrong merge is not.

⛔ (c) A RUNG NEVER OVERWRITES A HIGHER ONE. Each tier only ever fills rows still unresolved, so
adding a rung can raise the match rate but can never move a row that a stronger rung had already
decided.

⛔ (d) NOTHING IS EVER DROPPED. `resolve` returns exactly the rows it was given, in order, with
`canonical_player_id` NULL where unresolved. `silent_drop_count` is then a computable fact
(input rows minus output rows) rather than a hope — see `monitors`.

THRESHOLD CALIBRATION — MEASURED, AND IT OVERTURNED THE OBVIOUS ANSWER. The tempting way to tune
4b is to lower the threshold until `unmatched_rate` looks good. But that rate is a YIELD, and
yield is silent about whether the new matches are RIGHT: a fuzzy join that confidently merges the
wrong players scores a BETTER unmatched_rate than one that honestly abstains. So the default comes
from a blind-vendor-id control (`run_entity_resolution.py --calibrate`) that scores ACCURACY —
rows whose tier-1 answer is known independently are re-resolved with the vendor id hidden, and the
fuzzy rung's answers are compared against it. Measured over 43,013 control rows (2024–25):

    threshold  0.80  0.84  0.86  0.88  0.90  0.92  0.95
    wrong      65    64    42    34    16    16    0     (of 559/500/420/263/201/132/64 fuzzy)

Every threshold below 0.95 buys yield with wrong merges, so **0.95** is the default. The
consequence is deliberate and worth stating plainly: the nickname that motivated this story
("Michael Woods II" vs "Mike Woods") scores **0.8913** and is therefore NOT auto-matched here.
Nicknames belong in the reviewed crosswalk (tier 2) or in manual review (tier 5) — a threshold
loose enough to catch that one also makes 34 wrong merges, which the control proves.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .names import jaro_winkler, normalize_for_matching, normalize_team, position_group

log = logging.getLogger("nfl.entity.resolver")

METHOD_VENDOR_ID = "stable_vendor_id"
METHOD_REVIEWED = "reviewed_crosswalk"
METHOD_EXACT_NAME_TEAM_POS = "exact_name_team_position"
METHOD_NAME_TEAM_RELAXED = "constrained_name_team"
METHOD_FUZZY_CONSTRAINED = "constrained_fuzzy"
METHOD_UNRESOLVED = "manual_review"

# The ladder, strongest first. Order is load-bearing (property (c)).
MATCH_METHODS: tuple[str, ...] = (
    METHOD_VENDOR_ID,
    METHOD_REVIEWED,
    METHOD_EXACT_NAME_TEAM_POS,
    METHOD_NAME_TEAM_RELAXED,
    METHOD_FUZZY_CONSTRAINED,
    METHOD_UNRESOLVED,
)

MATCH_CONFIDENCE: dict[str, float] = {
    METHOD_VENDOR_ID: 1.00,
    METHOD_REVIEWED: 0.99,
    METHOD_EXACT_NAME_TEAM_POS: 0.95,
    METHOD_NAME_TEAM_RELAXED: 0.90,
    METHOD_FUZZY_CONSTRAINED: 0.0,  # scored per-row from the Jaro-Winkler similarity
    METHOD_UNRESOLVED: 0.0,
}

# A match at or below this confidence is "low confidence" for the §12A `low_confidence_rate`
# monitor. Set just under tier 4a so every fuzzy match counts and every exact one does not.
LOW_CONFIDENCE_AT_OR_BELOW = 0.89

# ⭐ CONFIDENCE IS A PROPERTY OF THE RUNG, NOT OF THE STRING SIMILARITY — and getting this wrong
# makes `low_confidence_rate` unable to fire at all. The natural-looking choice is to use the
# Jaro-Winkler score AS the fuzzy match's confidence. But the rung only accepts scores ≥ 0.95, so
# every fuzzy confidence would land ABOVE the 0.89 low-confidence bar and the monitor would read
# 0.0000 forever — a monitor that cannot fire, reported as a clean number (the NF1.7 (a) shape).
# An inexact match is inherently the least trustworthy rung REGARDLESS of how close the strings
# were, so its confidence is mapped into [0.60, 0.89]: always inside the low-confidence band,
# still ordered by similarity. The raw score stays available as `match_score`.
FUZZY_CONFIDENCE_FLOOR = 0.60
FUZZY_CONFIDENCE_CEILING = 0.89


def fuzzy_confidence(score: float, threshold: float) -> float:
    """Map a Jaro-Winkler score in [threshold, 1] onto the low-confidence band."""
    span = max(1e-9, 1.0 - threshold)
    frac = min(1.0, max(0.0, (float(score) - threshold) / span))
    return FUZZY_CONFIDENCE_FLOOR + frac * (FUZZY_CONFIDENCE_CEILING - FUZZY_CONFIDENCE_FLOOR)

# MEASURED, not assumed — see the module docstring and `--calibrate`. On a 43,013-row
# blind-vendor-id control (2024–25), the fuzzy rung's WRONG-MERGE count by threshold was:
#   0.80 → 65 wrong of 559 fuzzy   0.86 → 42 of 420   0.90 → 16 of 201
#   0.84 → 64 of 500               0.88 → 34 of 263   0.92 → 16 of 132   0.95 → 0 of 64
# 0.95 is the only value with zero measured wrong merges, so it is the default. Everything looser
# buys yield with errors, which is the trade this rung must not make.
DEFAULT_FUZZY_THRESHOLD = 0.95


@dataclass(frozen=True)
class ResolutionSpec:
    """How ONE source's records are keyed, and what a fuzzy candidate may be blocked inside.

    `vendor_id_column`/`vendor_source_name` drive tiers 1–2. `name_column` drives tiers 3–4.
    `block_columns` is the constraint set (e.g. `("season", "week", "team_id")`) — EMPTY means
    the source offers no constraint, which disables every name rung (property (a)).
    """

    source_name: str
    vendor_id_column: str | None = None
    vendor_source_name: str | None = None
    name_column: str | None = None
    team_column: str | None = None
    position_column: str | None = None
    block_columns: tuple[str, ...] = ()
    # The population a duplicate name could hide in — see the ambiguity note in `resolve`. Wider
    # than the block ON PURPOSE: a block-local uniqueness test certifies the very collision it
    # cannot see. Defaults to the season.
    ambiguity_scope_columns: tuple[str, ...] = ("season",)
    # Fold given-name diminutives (Gabe↔Gabriel, Chig↔Chigoziem) into the matching key. OPT-IN PER
    # SOURCE, never global: enabling it changes which rows a rung resolves, and the snap leg is
    # already validated against the live lake and must not move. Vendor annotation stripping
    # ("Michael (Saints) Thomas") is unconditional — a parenthetical is never part of a name.
    name_aliasing: bool = False
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD
    # Rows whose feature would materially move a projection — the §12A
    # `high_value_unmatched_count` population. A callable over the source frame → bool Series.
    high_value_mask: object = field(default=None, compare=False)

    @property
    def allow_name_tiers(self) -> bool:
        """Name rungs (3, 4a, 4b) require BOTH a name column and a real blocking constraint."""
        return bool(self.name_column) and bool(self.block_columns)


# Columns `resolve` adds to the source frame.
RESULT_COLUMNS = (
    "canonical_player_id",
    "match_method",
    "match_confidence",
    "match_score",
    "source_degraded",
)


def _norm_series(s: pd.Series, *, aliasing: bool = False) -> pd.Series:
    """The matching key. BOTH sides of every rung go through this one function with the SAME
    `aliasing` setting — an asymmetric normalization would silently make two identical names
    disagree, which is the failure the alias map exists to remove."""
    return s.astype("string").fillna("").map(
        lambda v: normalize_for_matching(v, aliasing=aliasing)
    )


def _prepare_targets(
    targets: pd.DataFrame, spec: ResolutionSpec, *, target_name_column: str,
    target_team_column: str | None, target_position_column: str | None,
) -> pd.DataFrame:
    t = targets.copy()
    t["_nn"] = _norm_series(t[target_name_column], aliasing=spec.name_aliasing)
    t["_team"] = (
        t[target_team_column].map(normalize_team) if target_team_column else ""
    )
    t["_pos"] = (
        t[target_position_column].map(position_group) if target_position_column else ""
    )
    return t


def _unique_map(frame: pd.DataFrame, keys: list[str], value: str) -> pd.DataFrame:
    """Collapse `frame` to one row per `keys` — but ONLY where the value is unambiguous.

    A key with more than one distinct canonical id is DROPPED, not arbitrated (property (b)).
    """
    g = frame.groupby(keys, dropna=False)[value].agg(["nunique", "first"]).reset_index()
    g = g[g["nunique"] == 1]
    return g.rename(columns={"first": value})[keys + [value]]


def resolve(
    source: pd.DataFrame,
    *,
    spec: ResolutionSpec,
    crosswalk: pd.DataFrame | None = None,
    reviewed: pd.DataFrame | None = None,
    targets: pd.DataFrame | None = None,
    target_id_column: str = "canonical_player_id",
    target_name_column: str = "player_name",
    target_team_column: str | None = "team",
    target_position_column: str | None = "position",
) -> pd.DataFrame:
    """Run the ladder over `source`, returning it with `RESULT_COLUMNS` attached.

    ⭐ ROW-PRESERVING BY CONTRACT: the return has exactly `len(source)` rows in the input order.
    An unmatched row survives with `canonical_player_id = <NA>`, `match_method='manual_review'`
    and `source_degraded=True`. That is the §12A fall-back-and-flag policy — the caller decides
    what to serve for a degraded row, and `monitors` refuses to let it be a silent zero.

    `targets` is the identity universe the name rungs match INTO (`weekly_rosters`-shaped:
    canonical id + name + team + position + the block columns).
    """
    out = source.copy()
    n_in = len(out)
    out["canonical_player_id"] = pd.array([pd.NA] * n_in, dtype="string")
    out["match_method"] = pd.array([METHOD_UNRESOLVED] * n_in, dtype="string")
    out["match_confidence"] = 0.0
    out["match_score"] = float("nan")
    if n_in == 0:
        out["source_degraded"] = pd.array([], dtype="boolean")
        return out

    def _fill(mask: pd.Series, ids: pd.Series, method: str, scores: pd.Series | None = None) -> None:
        """Fill ONLY still-unresolved rows (property (c))."""
        eligible = mask & out["canonical_player_id"].isna() & ids.notna()
        if not eligible.any():
            return
        out.loc[eligible, "canonical_player_id"] = ids[eligible].astype("string")
        out.loc[eligible, "match_method"] = method
        if scores is None:
            out.loc[eligible, "match_confidence"] = MATCH_CONFIDENCE[method]
            out.loc[eligible, "match_score"] = 1.0
        else:
            # `match_score` keeps the raw similarity; `match_confidence` is the RUNG's — see
            # `fuzzy_confidence` for why conflating the two silences the low-confidence monitor.
            out.loc[eligible, "match_score"] = scores[eligible].astype(float)
            out.loc[eligible, "match_confidence"] = (
                scores[eligible].astype(float).map(
                    lambda s: fuzzy_confidence(s, spec.fuzzy_threshold)
                )
            )

    # ── Tiers 1–2: vendor id, then the reviewed override ────────────────────────────────────
    # Tier 2 runs FIRST as a lookup but is applied SECOND, because a reviewed row exists precisely
    # to correct a vendor id — so it must win where the two disagree.
    vendor_col = spec.vendor_id_column
    if vendor_col and vendor_col in out.columns:
        src_ids = out[vendor_col].astype("string").str.strip()
        src_ids = src_ids.str.replace(r"\.0$", "", regex=True)
        vendor_source = spec.vendor_source_name or spec.source_name

        for book, method in ((reviewed, METHOD_REVIEWED), (crosswalk, METHOD_VENDOR_ID)):
            if book is None or book.empty:
                continue
            b = book[book["source_name"] == vendor_source]
            if b.empty:
                continue
            m = _unique_map(
                b.rename(columns={"source_player_id": "_sid"}), ["_sid"], "canonical_player_id"
            )
            joined = src_ids.rename("_sid").to_frame().merge(m, on="_sid", how="left")
            joined.index = out.index
            _fill(pd.Series(True, index=out.index), joined["canonical_player_id"], method)

    if not spec.allow_name_tiers or targets is None or targets.empty:
        out["source_degraded"] = out["canonical_player_id"].isna()
        _assert_row_preserving(out, n_in)
        return out

    # ── Tiers 3–4: name rungs, always inside the declared block ─────────────────────────────
    t = _prepare_targets(
        targets, spec,
        target_name_column=target_name_column,
        target_team_column=target_team_column,
        target_position_column=target_position_column,
    )
    if target_id_column != "canonical_player_id":
        t = t.rename(columns={target_id_column: "canonical_player_id"})
    t = t[t["canonical_player_id"].notna()]

    s_nn = _norm_series(out[spec.name_column], aliasing=spec.name_aliasing)
    s_team = out[spec.team_column].map(normalize_team) if spec.team_column else pd.Series("", index=out.index)
    s_pos = out[spec.position_column].map(position_group) if spec.position_column else pd.Series("", index=out.index)

    # ⭐ THE BLOCK MUST BE COMPLETE, NOT MERELY NON-EMPTY. A spec declaring
    # ("season", "_event_team") whose target frame supplies only "season" would run the fuzzy rung
    # blocked on the SEASON — i.e. against every player in the league, which is exactly the
    # name-only global fuzzy §12A forbids, reached by accident rather than by choice. A partial
    # block is therefore refused outright, the same as an absent one.
    block = [c for c in spec.block_columns if c in out.columns and c in t.columns]
    if len(block) != len(spec.block_columns):
        missing = [c for c in spec.block_columns if c not in block]
        log.warning(
            "ALERT [nfl/entity] source=%s declares block_columns=%s but %s are absent from the "
            "frames — name tiers REFUSED (a PARTIAL block is a weaker constraint than the one "
            "declared, and an unconstrained fuzzy match is a name-only match).",
            spec.source_name, spec.block_columns, missing,
        )
        out["source_degraded"] = out["canonical_player_id"].isna()
        _assert_row_preserving(out, n_in)
        return out

    left = out[block].copy()
    left["_nn"], left["_team"], left["_pos"] = s_nn, s_team, s_pos

    # ⭐ AMBIGUITY IS JUDGED OVER THE AMBIGUITY SCOPE (the season), NOT INSIDE THE BLOCK — AND
    # NOT ON NAME+POSITION. Both narrowings were tried and both are wrong; the blind-vendor-id
    # control is the only reason we know.
    #
    # The case: the NFL carried TWO "Jonah Williams" in 2024–25 — an offensive tackle (00-0035944)
    # and an edge rusher (00-0035629). (1) Judging uniqueness per (name, team, position-group)
    # matched the OL cell's single candidate at tier 3's 0.95 confidence and got it WRONG on all 15
    # rows: position cannot arbitrate a duplicate name, because the vendors disagree on position
    # GRAIN (the whole reason `position_group` exists), so a position that appears to separate two
    # players may only record how one vendor labelled them. (2) Judging ambiguity INSIDE the block
    # still failed, and this is the subtle part — ARI's roster that week lists only ONE Jonah
    # Williams, so within the block the name looks perfectly unique. The other one is elsewhere in
    # the league. A block-local uniqueness test cannot see a collision it does not contain, so it
    # certifies exactly the case it needs to catch.
    #
    # ⇒ the scope must be the population the TRUE player could have come from: the season. If a
    # normalized name maps to more than one canonical player anywhere in the season, every name rung
    # abstains for that name and it goes to manual review. Measured on the 43,013-row control at
    # threshold 0.95, the wider scope takes wrong merges from 15 to **0** and costs 489 extra
    # abstentions (1.1% of the control). That trade is the right way round: an abstention is
    # visible, lands in the QA queue, and is fixable by one reviewed-crosswalk row; a wrong merge
    # is invisible and silently attributes one player's snaps to another.
    scope = [
        c for c in spec.ambiguity_scope_columns if c in out.columns and c in t.columns
    ] or block[:1]
    name_keys = scope + ["_nn"]
    ambiguous = (
        t.groupby(name_keys, dropna=False)["canonical_player_id"].nunique().reset_index()
    )
    ambiguous = ambiguous[ambiguous["canonical_player_id"] > 1][name_keys]
    if not ambiguous.empty:
        ambiguous["_ambiguous"] = True
        flag = left.merge(ambiguous, on=name_keys, how="left")["_ambiguous"]
        flag.index = out.index
        name_eligible = flag.isna()
        log.info(
            "[nfl/entity] source=%s: %d rows carry a name that is ambiguous inside its block — "
            "name tiers abstain for them (duplicate names go to manual review).",
            spec.source_name, int((~name_eligible).sum()),
        )
    else:
        name_eligible = pd.Series(True, index=out.index)

    # ⭐ ONLY JOIN ON THE ATTRIBUTES THE SOURCE ACTUALLY SUPPLIES. A source may carry its team /
    # position in the BLOCK rather than in its own columns — props are exactly that: an Odds-API
    # outcome names no team, so the constraint arrives as `_event_team` in the block. Including
    # `_team`/`_pos` in the join key regardless meant comparing the source's placeholder "" against
    # the target's real value, so tiers 3 and 4a could NEVER match and every exact-name prop fell
    # through to the fuzzy rung — labelled `constrained_fuzzy` at low confidence, which drove
    # `low_confidence_rate` to 1.0 and failed the build closed on 586,850 EXACT matches.
    # (Found by running the real 2023–24 props payload; the unit fixtures all supplied a team
    # column, so none of them could expose it.)
    has_team = spec.team_column is not None
    has_pos = spec.position_column is not None
    if has_pos:
        key3 = block + ["_nn"] + (["_team"] if has_team else []) + ["_pos"]
        m3 = _unique_map(t, key3, "canonical_player_id")
        j3 = left.merge(m3, on=key3, how="left")
        j3.index = out.index
        _fill(name_eligible, j3["canonical_player_id"], METHOD_EXACT_NAME_TEAM_POS)

    # Tier 4a — exact name + team, position RELAXED (the vendors disagree on grain, not identity).
    # With no position column this is the STRONGEST honest label for an exact-name match: the team
    # constraint held (via the block or the column), the position was never checked.
    key4 = block + ["_nn"] + (["_team"] if has_team else [])
    m4 = _unique_map(t, key4, "canonical_player_id")
    j4 = left.merge(m4, on=key4, how="left")
    j4.index = out.index
    _fill(name_eligible, j4["canonical_player_id"], METHOD_NAME_TEAM_RELAXED)

    # Tier 4b — constrained fuzzy, inside one block cell, unique survivor above the threshold.
    unresolved = out["canonical_player_id"].isna() & name_eligible
    if unresolved.any():
        ids, scores = _fuzzy_within_blocks(
            left[unresolved], t, block=block, threshold=spec.fuzzy_threshold
        )
        full_ids = pd.Series(pd.array([pd.NA] * n_in, dtype="string"), index=out.index)
        full_scores = pd.Series(float("nan"), index=out.index)
        full_ids.loc[unresolved] = ids.values
        full_scores.loc[unresolved] = scores.values
        _fill(unresolved, full_ids, METHOD_FUZZY_CONSTRAINED, scores=full_scores)

    out["source_degraded"] = out["canonical_player_id"].isna()
    _assert_row_preserving(out, n_in)
    return out


def _fuzzy_within_blocks(
    left: pd.DataFrame, targets: pd.DataFrame, *, block: list[str], threshold: float
) -> tuple[pd.Series, pd.Series]:
    """Best Jaro-Winkler candidate for each unresolved row, WITHIN its own block cell.

    A candidate must (i) sit in the same block cell, (ii) agree on the normalized team when the
    source supplies one, (iii) score ≥ `threshold`, and (iv) be a STRICT winner — a tie at the top
    is an ambiguity, so it resolves to nothing (property (b)).
    """
    ids = pd.Series(pd.array([pd.NA] * len(left), dtype="string"), index=left.index)
    scores = pd.Series(float("nan"), index=left.index)
    if left.empty or targets.empty:
        return ids, scores

    tgt_by_cell: dict[tuple, list[tuple[str, str, str]]] = {}
    for row in targets[block + ["_nn", "_team", "canonical_player_id"]].itertuples(index=False):
        cell = tuple(row[: len(block)])
        tgt_by_cell.setdefault(cell, []).append(
            (row[len(block)], row[len(block) + 1], row[len(block) + 2])
        )

    for idx, row in zip(left.index, left.itertuples(index=False)):
        vals = dict(zip(left.columns, row))
        cell = tuple(vals[c] for c in block)
        cands = tgt_by_cell.get(cell)
        if not cands:
            continue
        src_nn, src_team = vals["_nn"], vals["_team"]
        if not src_nn:
            continue
        best_score, best_id, tied = -1.0, None, False
        for cand_nn, cand_team, cand_id in cands:
            if src_team and cand_team and src_team != cand_team:
                continue
            sc = jaro_winkler(src_nn, cand_nn)
            if sc > best_score:
                best_score, best_id, tied = sc, cand_id, False
            elif sc == best_score and cand_id != best_id:
                tied = True
        if best_id is None or tied or best_score < threshold:
            continue
        ids.loc[idx] = best_id
        scores.loc[idx] = best_score
    return ids, scores


def _assert_row_preserving(out: pd.DataFrame, n_in: int) -> None:
    """The row-preservation contract, asserted rather than assumed — it is what makes
    `silent_drop_count` a measurable fact instead of an article of faith."""
    if len(out) != n_in:
        raise AssertionError(
            f"entity resolution changed the row count ({n_in} → {len(out)}); a resolver must "
            "never drop or fan out a source row (v3 §12A silent_drop_count = 0)"
        )
