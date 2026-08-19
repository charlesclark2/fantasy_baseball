"""resolve.py — PFF ↔ our ids (NF-W9-0). THE CRUX OF THE SPIKE.

A feed we cannot join is a feed we do not have. This module resolves both entities, per league,
and REPORTS ITS OWN MATCH RATE with the unmatched enumerated — because the failure mode here is
not an error, it is a confident 0% join that reads as "PFF has no data for these players"
(the D/ST-nickname and NF-W3 franchise-code class, twice over).

NFL PLAYERS — deterministic, and the measurement that makes this story a GO:
  nflverse `weekly_rosters` already carries a `pff_id` vendor column, so NFL resolution is a
  TIER-1 stable-vendor-id join with no fuzzy matching at all. Measured on the live lake:

    season                        2021    2022    2023    2024    2025
    same-season pff_id coverage   99.66%  87.10%  68.60%  56.16%  99.97%   (opportunity-weighted)
    PLAYER-LEVEL (cross-season)   99.94%  99.59%  99.66%  99.89%  99.97%

  ⭐ THE SECOND ROW IS THE DESIGN. `pff_id` is a PLAYER-level id, but nflverse populates it
  per roster-row, and the historical rows are patchy — so a naive same-season join loses 44% of
  2024 opportunity while the id is sitting right there in another season's row for the same
  player. `build_pff_crosswalk` therefore collapses across ALL seasons.

  ⚠️ AND THE NAIVE COLLAPSE IS A WRONG MERGE. `max(pff_id)` is the obvious way to write it and
  it is wrong: pff_id 47327 is attached to BOTH Ryan Izzo and Tyler Conklin in the live lake, and
  Conklin also carries 47124 — so `max()` hands Conklin an id that is not uniquely his. We drop
  ambiguous ids instead of arbitrating (resolver property (b): a miss is visible, a wrong merge
  is not). This is delegated to `resolver._unique_map`, which already enforces exactly that.

  ⚠️ THE UNVERIFIED ASSUMPTION, STATED PLAINLY: all of the above measures the coverage of
  *nflverse's* `pff_id` COLUMN. It does NOT establish that nflverse's `pff_id` is the same id
  space as the PFF API's own `player_id`. Nothing in our lake can settle that — only a live PFF
  pull can, and `id_space_agreement` is the check that does it. Until it runs, the NFL match
  rate is a CEILING, not a result. Assuming two same-named id columns are the same key is
  precisely the NF-C0e wrong-key class.

NCAAF PLAYERS — genuinely harder, and honest about it:
  There is NO shared id between CFBD and anyone (NCAAF-P0.3 measured `CFBD nflAthleteId ∩
  nflverse espn_id = 0 of 257`), so a PFF college player must be matched on name + school +
  position. That is a fuzzy rung, so it runs INSIDE a block (the school) and demands a unique
  survivor, and we expect a materially lower rate than NFL. Reporting NCAAF's rate next to NFL's
  without that caveat would imply the two were measured the same way; they are not.

GAMES — both leagues, deterministic:
  No shared game id either, but `(season, week, home, away)` is a clean key once team names are
  normalized. Team normalization is the known landmine (NF-W7: `schedules` carries ERA franchise
  codes while pbp carries CURRENT), so an unmatched GAME is reported rather than dropped: a
  silently-dropped game takes all of its players' rows with it and depresses the PLAYER match
  rate for a reason that has nothing to do with players.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ..nfl.entity.crosswalk import CROSSWALK_COLUMNS
from ..nfl.entity.names import normalize_for_matching, normalize_team, position_group
from ..nfl.entity.resolver import ResolutionSpec, resolve
from .schools import school_key

log = logging.getLogger("pff.resolve")

PFF_SOURCE_NAME = "pff"


# ── NFL: the vendor-id crosswalk ────────────────────────────────────────────────────────────
def build_pff_crosswalk(weekly_rosters: pd.DataFrame) -> pd.DataFrame:
    """PLAYER-level `pff_id → gsis_id` rows in the §12A crosswalk shape.

    Collapsed across ALL seasons on purpose (see the module docstring): the id is player-level,
    nflverse's population of it is not, and the cross-season carry is worth ~44 points of 2024
    opportunity coverage. Ambiguous ids are NOT arbitrated here — `resolver._unique_map` drops
    any `source_player_id` that resolves to more than one player when the ladder runs.
    """
    need = {"gsis_id", "pff_id"}
    missing = need - set(weekly_rosters.columns)
    if missing:
        raise ValueError(f"weekly_rosters is missing {sorted(missing)} — cannot build the map")

    df = weekly_rosters.loc[
        weekly_rosters["pff_id"].notna() & weekly_rosters["gsis_id"].notna(),
        [c for c in ("gsis_id", "pff_id", "full_name", "team", "position") if c in weekly_rosters.columns],
    ].copy()
    if df.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in CROSSWALK_COLUMNS})

    df["source_player_id"] = (
        df["pff_id"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df = df.drop_duplicates(subset=["gsis_id", "source_player_id"])

    out = pd.DataFrame({
        "canonical_player_id": df["gsis_id"].astype("string"),
        "source_name": PFF_SOURCE_NAME,
        "source_player_id": df["source_player_id"],
        "source_player_name": df.get("full_name", pd.Series("", index=df.index)),
        "normalized_name": df.get("full_name", pd.Series("", index=df.index)).map(
            lambda v: normalize_for_matching(v)
        ),
        "team_id": df.get("team", pd.Series("", index=df.index)),
        "position": df.get("position", pd.Series("", index=df.index)),
        "match_method": "stable_vendor_id",
        "match_confidence": 1.0,
        "review_status": "auto",
    })
    for c in CROSSWALK_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA
    return out[list(CROSSWALK_COLUMNS)].reset_index(drop=True)


# The PFF→gsis spec. `block_columns` is populated so the name rungs are legal for the residual
# tail; an empty block would disable them outright (resolver property (a)).
NFL_PFF_SPEC = ResolutionSpec(
    source_name="pff.facet",
    vendor_id_column="pff_player_id",
    vendor_source_name=PFF_SOURCE_NAME,
    name_column="pff_player_name",
    team_column="pff_team",
    position_column="pff_position",
    block_columns=("season", "week", "pff_team"),
)


def resolve_nfl_players(
    pff_rows: pd.DataFrame, crosswalk: pd.DataFrame, targets: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Run the calibrated NF-W0b ladder over PFF rows. Row-preserving by that module's contract.

    Reusing the ladder rather than writing a merge buys the properties that make a join
    trustworthy and are easy to omit by hand: ambiguity becomes an UNRESOLVED instead of a coin
    flip, a fuzzy rung cannot fire outside its block, and the 0.95 threshold is one someone
    already calibrated against a blind vendor-id control instead of tuned until the yield
    looked good.
    """
    spec = NFL_PFF_SPEC if targets is not None and not targets.empty else ResolutionSpec(
        source_name=NFL_PFF_SPEC.source_name,
        vendor_id_column=NFL_PFF_SPEC.vendor_id_column,
        vendor_source_name=NFL_PFF_SPEC.vendor_source_name,
    )
    return resolve(
        pff_rows,
        spec=spec,
        crosswalk=crosswalk,
        targets=targets,
        target_id_column="gsis_id",
        target_name_column="full_name",
        target_team_column="team",
        target_position_column="position",
    )


# ── NCAAF: name + school + position, no id to lean on ───────────────────────────────────────
def resolve_ncaaf_players(
    pff_rows: pd.DataFrame,
    cfbd_roster: pd.DataFrame,
    *,
    name_col: str = "pff_player_name",
    team_col: str = "pff_team",
    pos_col: str = "pff_position",
) -> pd.DataFrame:
    """Match PFF college players to CFBD athlete ids on (normalized name, school, position).

    EXACT ONLY, and unique-within-school required. No fuzzy rung: with no id to fall back on and
    ~130 FBS rosters of ~120 players each, a loose threshold would buy yield in exactly the way
    the NF-W0b calibration proved costs wrong merges — and a wrong college player is
    indistinguishable from a right one downstream. An ambiguous or missing match is reported as
    unmatched WITH ITS REASON, so the residual is actionable rather than a number.
    """
    out = pff_rows.copy()
    n_in = len(out)
    out["cfbd_athlete_id"] = pd.array([pd.NA] * n_in, dtype="string")
    out["match_method"] = pd.array(["manual_review"] * n_in, dtype="string")
    if n_in == 0 or cfbd_roster.empty:
        out["source_degraded"] = out["cfbd_athlete_id"].isna()
        return out

    r = cfbd_roster.copy()
    r["_nn"] = (
        r["firstName"].fillna("").astype(str) + " " + r["lastName"].fillna("").astype(str)
    ).map(normalize_for_matching)
    # ⛔ school_key, NOT normalize_team: the latter is an NFL code folder that would leave
    # `Ole Miss` ≠ `Mississippi` and mangle accents — see schools.py.
    r["_team"] = r["team"].map(school_key)
    r["_pos"] = r["position"].map(position_group)

    s_nn = out[name_col].map(normalize_for_matching)
    s_team = out[team_col].map(school_key)
    s_pos = out[pos_col].map(position_group) if pos_col in out.columns else pd.Series("", index=out.index)

    for keys, src_keys, method in (
        (["_nn", "_team", "_pos"], [s_nn, s_team, s_pos], "exact_name_team_position"),
        (["_nn", "_team"], [s_nn, s_team], "constrained_name_team"),
    ):
        g = r.groupby(keys, dropna=False)["id"].agg(["nunique", "first"]).reset_index()
        g = g[g["nunique"] == 1].rename(columns={"first": "_cid"})[keys + ["_cid"]]
        probe = pd.concat(src_keys, axis=1)
        probe.columns = keys
        j = probe.merge(g, on=keys, how="left")
        j.index = out.index
        fill = out["cfbd_athlete_id"].isna() & j["_cid"].notna()
        out.loc[fill, "cfbd_athlete_id"] = j.loc[fill, "_cid"].astype("string")
        out.loc[fill, "match_method"] = method

    out["source_degraded"] = out["cfbd_athlete_id"].isna()
    # A school whose key matches NOTHING in the CFBD roster is almost never "PFF has extra
    # players" — it is a NAME we failed to reconcile, and it takes that school's whole roster
    # down with it. Naming those schools turns a depressed match rate into an alias-map entry.
    known = set(r["_team"].unique())
    out["unknown_school"] = ~s_team.isin(known)
    return out


# ── Games, both leagues ─────────────────────────────────────────────────────────────────────
def resolve_games(
    pff_games: pd.DataFrame,
    our_games: pd.DataFrame,
    *,
    pff_home: str = "home_team",
    pff_away: str = "away_team",
    our_home: str = "home_team",
    our_away: str = "away_team",
    our_id: str = "game_id",
    team_key=normalize_team,
) -> pd.DataFrame:
    """Join PFF games to ours on (season, week, normalized home, normalized away).

    Tries the orientation as given, then SWAPPED — a feed that labels home/away the other way
    round would otherwise produce a clean, total, and completely mysterious 0% match.

    ⚠️ `team_key` IS A REQUIRED DECISION, NOT A DETAIL. It defaults to the NFL code folder; the
    NCAAF caller MUST pass `school_key`. This was a live bug in the first cut of this module:
    the player path was moved onto `school_key` and this one was left on `normalize_team`, so
    `Ohio St` vs `Ohio State` scored a clean 0% game match while the PLAYER join was 100% — two
    renderers of one field quietly running two rule sets (the E9.61 class). It was caught by
    RUNNING the probe, not by a unit test, which is why `probe.run_league` now picks the key
    from the league and a test pins that it does.
    """
    out = pff_games.copy()
    out["our_game_id"] = pd.array([pd.NA] * len(out), dtype="string")
    out["game_match_method"] = pd.array(["unmatched"] * len(out), dtype="string")
    if out.empty or our_games.empty:
        return out

    o = our_games.copy()
    o["_h"] = o[our_home].map(team_key)
    o["_a"] = o[our_away].map(team_key)
    keys = ["season", "week", "_h", "_a"]
    g = o.groupby(keys, dropna=False)[our_id].agg(["nunique", "first"]).reset_index()
    g = g[g["nunique"] == 1].rename(columns={"first": "_gid"})[keys + ["_gid"]]

    for h_col, a_col, method in ((pff_home, pff_away, "exact"), (pff_away, pff_home, "swapped")):
        probe = pd.DataFrame({
            "season": out["season"], "week": out["week"],
            "_h": out[h_col].map(team_key), "_a": out[a_col].map(team_key),
        })
        j = probe.merge(g, on=keys, how="left")
        j.index = out.index
        fill = out["our_game_id"].isna() & j["_gid"].notna()
        out.loc[fill, "our_game_id"] = j.loc[fill, "_gid"].astype("string")
        out.loc[fill, "game_match_method"] = method
    return out


# ── Reporting ───────────────────────────────────────────────────────────────────────────────
def match_report(
    resolved: pd.DataFrame,
    *,
    id_column: str,
    label: str,
    opportunity_column: str | None = None,
    name_column: str | None = None,
    max_unmatched: int = 50,
) -> dict[str, Any]:
    """Match rate + the ENUMERATED unmatched. Never just a percentage.

    Reports the OPPORTUNITY-WEIGHTED rate beside the row rate when an opportunity column is
    given, because they answer different questions and the row rate is the misleading one: NFL
    2024 is 56% of roster rows and >99% of actual targets-and-carries, and a story that needs
    the targets is entitled to the number about targets (the NF1.8 "state the margin in the unit
    that matters" rule).
    """
    n = len(resolved)
    matched = resolved[id_column].notna() if n else pd.Series(dtype=bool)
    rep: dict[str, Any] = {
        "label": label,
        "rows": n,
        "matched": int(matched.sum()) if n else 0,
        "match_rate": round(float(matched.mean()), 4) if n else None,
        "by_method": (
            resolved.loc[:, "match_method"].value_counts().to_dict()
            if "match_method" in resolved.columns else {}
        ),
    }
    if opportunity_column and opportunity_column in resolved.columns and n:
        opp = pd.to_numeric(resolved[opportunity_column], errors="coerce").fillna(0.0)
        total = float(opp.sum())
        rep["opportunity_total"] = total
        rep["opportunity_matched_rate"] = (
            round(float(opp[matched].sum() / total), 4) if total > 0 else None
        )
        rep["opportunity_unmatched"] = float(opp[~matched].sum())
    if n:
        cols = [c for c in (name_column, "pff_team", "pff_position", "pff_player_id") if c and c in resolved.columns]
        un = resolved.loc[~matched, cols] if cols else resolved.loc[~matched]
        rep["unmatched_count"] = int((~matched).sum())
        rep["unmatched_sample"] = un.head(max_unmatched).to_dict("records")
    return rep


def id_space_agreement(
    pff_rows: pd.DataFrame, crosswalk: pd.DataFrame, *, pff_id_col: str = "pff_player_id"
) -> dict[str, Any]:
    """⭐ THE ASSUMPTION TEST: is PFF's own `player_id` the same id space as nflverse's `pff_id`?

    The whole NFL go/no-go rests on this and NOTHING in our lake can answer it. Two failure
    shapes are possible and they look nothing alike:
      • overlap ≈ 0  → different id spaces. The vendor column is useless and NFL resolution
                       falls all the way back to name matching. This is the NF-C0e wrong-key
                       class and it would be a materially worse (though still workable) answer.
      • overlap high → the same space, and NFL resolution is the deterministic join measured
                       above.
    A partial overlap is the interesting middle and is reported as-is rather than rounded to a
    verdict.
    """
    ids = (
        pff_rows[pff_id_col].dropna().astype("string").str.strip()
        .str.replace(r"\.0$", "", regex=True).unique()
        if pff_id_col in pff_rows.columns else []
    )
    known = set(
        crosswalk.loc[crosswalk["source_name"] == PFF_SOURCE_NAME, "source_player_id"]
        .dropna().astype("string")
    )
    ids = list(ids)
    overlap = [i for i in ids if i in known]
    rate = round(len(overlap) / len(ids), 4) if ids else None
    return {
        "pff_ids_seen": len(ids),
        "nflverse_pff_ids_known": len(known),
        "overlap": len(overlap),
        "overlap_rate": rate,
        "verdict": (
            "UNTESTED (no PFF ids in probe)" if not ids
            else "SAME_ID_SPACE" if (rate or 0) >= 0.80
            else "DISJOINT_ID_SPACE — nflverse pff_id is NOT PFF's player_id; fall back to names"
            if (rate or 0) <= 0.05 else "PARTIAL — investigate before relying on tier 1"
        ),
    }
