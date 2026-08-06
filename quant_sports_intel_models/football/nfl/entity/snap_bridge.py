"""snap_bridge.py — NF-W0b: `snap_counts` → canonical player-week, WITHOUT the silent zero.

⭐ THIS IS THE NF-W1-CRITICAL LEG and the reason NF-W0b runs before NF-W1.

THE DEFECT (NF-W0c, re-measured live here). `snap_counts` keys on `pfr_player_id`; the only
bridge to our `gsis_id` is `weekly_rosters.pfr_id`, which is **25–53% NULL across 2022–2025**.
The two consumers each mishandle the miss, in opposite and equally invisible ways:

  • dbt `fct_player_week` / `sat_snap_counts_weekly` LEFT-join and then
    `coalesce(offense_pct, 0.0)` → an unresolved identity becomes a **0.0 snap share**. A snap
    share is a rate in [0, 1] where 0.0 is a legal observation ("dressed, played no offensive
    snaps"), so the fabricated zero is INDISTINGUISHABLE from a real one. Live 2024:
    **Michael Woods II played 100% of CLE's week-15 snaps and the fact serves 0.00.**

  • `run_nf_w0_audit.load_sources` INNER-joins snaps to the roster bridge → an unresolved snap row
    is **dropped entirely**. Measured 19–46% of snap rows per season. Same root cause, and the
    §12A monitor for it is `silent_drop_count`, which must be 0.

THE CURE, in three parts, none of which is optional:

  1. RESOLVE PROPERLY — run the ladder, and key the vendor map on the id ALONE rather than on
     (season, id) as both consumers do today. Measured over 2022–2025: `unmatched_rate` falls to
     **0.68%–1.24%** of snap rows, `silent_drop_count` is **0**, and
     `high_value_unmatched_count` is **0** in every season — including Woods, who comes back at
     tier 1 off another season's roster row.
  2. FALL BACK AND FLAG — the residual gets `canonical_player_id = NULL`, `snap_source_tier =
     'unresolved'`, `source_degraded = True`, and **NULL snap values**, never 0.0. A model then
     sees a missing feature (which it can handle honestly) instead of a false observation.
  3. KEEP THE REAL ZEROS — a player who IS resolved and genuinely took 0 snaps keeps his 0.0, and
     `snap_source_tier = 'observed'`. Distinguishing these two zeros is the entire deliverable;
     `assert_no_silent_zero` is the guard that they stay distinguished.

⚠️ DIRECTION MATTERS AND THE TWO DIRECTIONS ANSWER DIFFERENT QUESTIONS. `resolve_snap_counts`
resolves the snap FEED (its miss = a snap observation we cannot attribute = the `silent_drop`
surface). `attach_snaps_to_player_week` attaches onto the player-week SPINE (its miss = a player
whose snap share we do not know = the `silent zero` surface). A build needs both numbers; a
single "match rate" collapses them and reads healthy while one side is broken.
"""
from __future__ import annotations

import logging

import pandas as pd

from .monitors import MonitorReport, ResolutionThresholds, DEFAULT_THRESHOLDS, evaluate
from .resolver import ResolutionSpec, resolve

log = logging.getLogger("nfl.entity.snap_bridge")

__all__ = [
    "SNAP_SPEC",
    "SNAP_VALUE_COLUMNS",
    "attach_snaps_to_player_week",
    "resolve_snap_counts",
    "skill_starter_mask",
]

# The snap columns whose value is meaningless without a resolved identity. Every one of these must
# be NULL on a degraded row — that is what `assert_no_silent_zero` checks.
SNAP_VALUE_COLUMNS = ["offense_snaps", "offense_pct", "special_teams_snaps", "special_teams_pct"]

# The snap feed's ladder spec. Blocked on (season, week, team): a fuzzy candidate must be a player
# on the SAME team in the SAME week, which is what makes the nickname rung safe enough to run.
SNAP_SPEC = ResolutionSpec(
    source_name="nflverse.snap_counts",
    vendor_id_column="pfr_player_id",
    vendor_source_name="pfr",
    name_column="player",
    team_column="team",
    position_column="position",
    block_columns=("season", "week", "team"),
)

# Positions whose snap share actually moves a fantasy projection. The §12A high-value population
# is the intersection of this and a real workload — see `skill_starter_mask`.
SKILL_POSITIONS = ("QB", "RB", "FB", "WR", "TE")


def skill_starter_mask(snaps: pd.DataFrame, *, min_offense_pct: float = 0.5) -> pd.Series:
    """The §12A `high_value_unmatched_count` population for snaps: a skill-position player who
    played at least `min_offense_pct` of his team's offensive snaps.

    ⭐ WHY A WORKLOAD FILTER AND NOT JUST A POSITION FILTER. An unmatched 3%-snap WR is a rounding
    error; an unmatched 100%-snap WR is a corrupted starter. Counting only positions would put
    both in the same number and the count would then track roster churn rather than damage. The
    live 2024 residual contains a 1.00-offense_pct WR, which is exactly the row this mask exists
    to surface.
    """
    if snaps is None or snaps.empty:
        return pd.Series(dtype=bool)
    if "position" in snaps.columns:
        is_skill = snaps["position"].astype("string").str.upper().isin(SKILL_POSITIONS)
        is_skill = is_skill.fillna(False).astype(bool)
    else:
        # No position column ⇒ we cannot tell a starter from a long-snapper. Returning all-False
        # would score the high-value monitor 0 on a frame it never actually examined (the NF1.7 (a)
        # vacuous-anchor shape), so treat every row as in-population instead: the count then
        # over-reports rather than silently reading healthy.
        is_skill = pd.Series(True, index=snaps.index)
    if "offense_pct" not in snaps.columns:
        return is_skill
    pct = pd.to_numeric(snaps["offense_pct"], errors="coerce").fillna(0.0)
    return (is_skill & (pct >= min_offense_pct)).astype(bool)


def resolve_snap_counts(
    snaps: pd.DataFrame,
    *,
    targets: pd.DataFrame,
    crosswalk: pd.DataFrame | None = None,
    reviewed: pd.DataFrame | None = None,
    thresholds: ResolutionThresholds = DEFAULT_THRESHOLDS,
    min_offense_pct: float = 0.5,
) -> tuple[pd.DataFrame, MonitorReport]:
    """Attach `canonical_player_id` to every snap row via the ladder, dropping NOTHING.

    `targets` is the identity universe — `weekly_rosters`-shaped, carrying `canonical_player_id`
    (gsis_id), `player_name`, `team`, `position`, `season`, `week`.

    Returns (resolved snap frame, monitor report). The report's `silent_drop_count` is computed
    against the INPUT row count, so the §12A "must equal 0" is a measured fact.
    """
    n_in = int(len(snaps)) if snaps is not None else 0
    resolved = resolve(
        snaps if snaps is not None else pd.DataFrame(),
        spec=SNAP_SPEC,
        crosswalk=crosswalk,
        reviewed=reviewed,
        targets=targets,
        target_name_column="player_name",
        target_team_column="team",
        target_position_column="position",
    )
    report = evaluate(
        resolved,
        source_name=SNAP_SPEC.source_name,
        n_input_rows=n_in,
        thresholds=thresholds,
        high_value_mask=skill_starter_mask(resolved, min_offense_pct=min_offense_pct),
    )
    return resolved, report


def attach_snaps_to_player_week(
    player_week: pd.DataFrame,
    resolved_snaps: pd.DataFrame,
    *,
    keys: tuple[str, ...] = ("season", "week", "canonical_player_id"),
) -> pd.DataFrame:
    """LEFT-join resolved snaps onto the player-week spine and label WHY a value is absent.

    Adds `snap_source_tier` — the column that makes the two kinds of zero tellable apart:

      • `observed`   — a resolved snap row exists. Its value stands, INCLUDING a genuine 0.0.
      • `no_snap_row`— identity resolved, but the feed carries no snap row for this player-week
                       (a bye, an inactive, a feed lag). Values NULL.
      • `unresolved` — the snap feed has rows we could not attribute to this player, or this
                       player has no resolvable identity. Values NULL, `source_degraded=True`.

    ⛔ NO `fillna(0)` ANYWHERE. That is the point of the module. A consumer that wants a zero must
    ask for one explicitly, at which point the choice is visible in ITS code and reviewable.
    """
    out = player_week.copy()
    if "canonical_player_id" not in out.columns:
        raise ValueError("player_week must carry canonical_player_id to attach resolved snaps")

    value_cols = [c for c in SNAP_VALUE_COLUMNS if c in (resolved_snaps.columns if resolved_snaps is not None else [])]
    if resolved_snaps is None or resolved_snaps.empty or not value_cols:
        for c in SNAP_VALUE_COLUMNS:
            out[c] = pd.NA
        out["snap_source_tier"] = "unresolved"
        out["source_degraded"] = True
        return out

    right = resolved_snaps[resolved_snaps["canonical_player_id"].notna()].copy()
    join_keys = [k for k in keys if k in out.columns and k in right.columns]
    if not join_keys:
        raise ValueError(f"no shared join keys between player_week and snaps (wanted {keys})")

    # Collapse duplicate snap rows per player-week (a mid-week team change can produce two) by
    # summing snaps and taking the max share — never fanning the spine out.
    agg = {c: ("max" if c.endswith("_pct") else "sum") for c in value_cols}
    right = right.groupby(join_keys, dropna=False, as_index=False).agg(agg)
    right["_matched"] = True

    n_before = len(out)
    out = out.merge(right, on=join_keys, how="left")
    if len(out) != n_before:
        raise AssertionError(
            f"attaching snaps fanned the player-week spine out ({n_before} → {len(out)}); "
            "the snap side must be unique per join key"
        )

    has_snap = out.pop("_matched").astype("boolean").fillna(False).astype(bool)
    unresolved = out["canonical_player_id"].isna()
    if "source_degraded" in player_week.columns:
        prior = player_week["source_degraded"].astype("boolean").fillna(False).astype(bool)
        unresolved = unresolved | prior.values

    tier = pd.Series("no_snap_row", index=out.index, dtype="object")
    tier[has_snap] = "observed"
    tier[unresolved] = "unresolved"
    out["snap_source_tier"] = tier
    out["source_degraded"] = ~has_snap

    # A row with no observed snap row carries NULL, never 0.0 — including the unresolved cohort.
    for c in SNAP_VALUE_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA
        else:
            out.loc[~has_snap, c] = pd.NA
    return out
