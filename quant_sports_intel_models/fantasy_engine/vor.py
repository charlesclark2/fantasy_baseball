"""vor.py — pure, sport-agnostic positional scarcity → value-over-replacement → ranked board.

The layer that makes a cross-position ranking meaningful: 300 rushing points is not worth the same as
300 QB points, because a league starts far more QBs-worth of QB scoring per team. VOR normalizes every
player against the "last startable player at his position" — the freely-available replacement — so a
QB and a WR become comparable on a single overall board.

THE SUBTLE PART — FLEX / SUPERFLEX allocation. Replacement level is driven by league DEMAND per
position = dedicated starter spots PLUS that position's share of the flex/superflex pool. Flex is filled
by the best remaining players ACROSS eligible positions league-wide, so we must allocate the flex pool
before we know where each position's replacement sits. The allocation is a greedy draft over the flex
spots, most-restrictive slot first (a strict RB/WR/TE FLEX is filled before a QB-eligible SUPERFLEX),
each spot taking the best still-unstarted eligible player. Under superflex the QB-eligible spots pull
the best remaining QBs into starting lineups → many more QBs started → QB replacement drops deep → QB
VOR jumps. That QB lift is the face-validity proof the scarcity math is right.

Everything here is pure (DataFrame in, DataFrame/dict out) and sport-neutral: positions and eligibility
come only from the `LeagueConfig`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig, SportProfile


def compute_replacement_levels(
    scored: pd.DataFrame,
    config: LeagueConfig,
    profile: SportProfile,
    *,
    points_col: str = "league_points",
) -> tuple[dict[str, float], dict[str, int]]:
    """Return `(replacement_points_by_position, started_count_by_position)`.

    `started[pos]` = league-wide starting spots that end up filled by `pos` (dedicated + allocated
    flex). `replacement[pos]` = the points of the FIRST non-startable player at that position (the best
    player you could add for free) — the classic value-over-replacement baseline. If a position has
    fewer players than starters, replacement falls to its weakest available player (never negative).
    """
    pos_series = scored[profile.position_column].map(profile.normalize_position)
    pts = pd.to_numeric(scored[points_col], errors="coerce").fillna(0.0)

    # per-position points, sorted descending (the league-wide draft order at each position)
    ranked: dict[str, np.ndarray] = {}
    for pos in pos_series.dropna().unique():
        vals = pts[(pos_series == pos).to_numpy()].to_numpy()
        ranked[pos] = np.sort(vals)[::-1]

    # dedicated demand consumes the top-N at each position up front
    started: dict[str, int] = {pos: 0 for pos in ranked}
    for pos, n in config.dedicated_demand().items():
        started[pos] = started.get(pos, 0) + n

    # allocate the flex/superflex pool: expand every flex slot to individual spots, fill the
    # most-restrictive (smallest eligibility set) first so a QB-eligible SUPERFLEX never poaches a
    # player a strict FLEX still needed — then each spot takes the best still-unstarted eligible player.
    spots: list[frozenset[str]] = []
    for eligible, n_spots in config.flex_slot_specs():
        spots.extend([eligible] * n_spots)
    spots.sort(key=len)
    for eligible in spots:
        best_pos, best_pts = None, -np.inf
        for pos in eligible:
            arr = ranked.get(pos)
            idx = started.get(pos, 0)
            if arr is not None and idx < len(arr) and arr[idx] > best_pts:
                best_pts, best_pos = arr[idx], pos
        if best_pos is not None:
            started[best_pos] += 1

    replacement: dict[str, float] = {}
    for pos, arr in ranked.items():
        idx = started.get(pos, 0)
        if len(arr) == 0:
            replacement[pos] = 0.0
        elif idx < len(arr):
            replacement[pos] = float(arr[idx])          # first non-starter = the free replacement
        else:
            replacement[pos] = float(arr[-1])           # thinner than demand ⇒ weakest rostered
        replacement[pos] = max(0.0, replacement[pos])
    return replacement, {p: int(c) for p, c in started.items()}


def build_board(
    scored: pd.DataFrame,
    config: LeagueConfig,
    profile: SportProfile,
    *,
    points_col: str = "league_points",
) -> pd.DataFrame:
    """From a scored frame → a cross-position ranked board with VOR + ranks + carried interval.

    Adds: `replacement_points`, `vor` (points − replacement), `positional_rank` (by points within
    position), `overall_rank` (by VOR across all positions), and `vor_p10/_p90` when the scorer carried
    a `<points_col>_p10/_p90` interval (the interval just shifts by the fixed replacement level). Sorted
    by `overall_rank`.
    """
    board = scored.copy()
    replacement, started = compute_replacement_levels(board, config, profile, points_col=points_col)

    norm_pos = board[profile.position_column].map(profile.normalize_position)
    board["replacement_points"] = norm_pos.map(replacement).astype(float).fillna(0.0)
    board["vor"] = pd.to_numeric(board[points_col], errors="coerce").fillna(0.0) - board["replacement_points"]

    # shift the carried interval by the (fixed) replacement level → an honest interval on VOR
    for q in ("p10", "p90"):
        src = f"{points_col}_{q}"
        if src in board.columns:
            board[f"vor_{q}"] = pd.to_numeric(board[src], errors="coerce") - board["replacement_points"]

    board["positional_rank"] = (
        board.groupby(norm_pos)[points_col].rank(method="first", ascending=False).astype(int)
    )
    board = board.sort_values("vor", ascending=False, kind="mergesort").reset_index(drop=True)
    board["overall_rank"] = np.arange(1, len(board) + 1)
    return board


def replacement_summary(
    config: LeagueConfig, profile: SportProfile, replacement: dict[str, float], started: dict[str, int]
) -> pd.DataFrame:
    """A transparent per-position table: dedicated demand, flex allocation, total started, and the
    resulting replacement level — the auditable definition of scarcity the story's gate asks for."""
    dedicated = config.dedicated_demand()
    rows = []
    for pos in sorted(started):
        ded = int(dedicated.get(pos, 0))
        tot = int(started.get(pos, 0))
        rows.append({
            "position": pos,
            "dedicated_starters": ded,
            "flex_allocated": tot - ded,
            "total_started": tot,
            "replacement_points": round(float(replacement.get(pos, 0.0)), 1),
        })
    return pd.DataFrame(rows)
