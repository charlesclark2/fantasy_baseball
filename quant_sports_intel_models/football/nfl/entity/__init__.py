"""NF-W0b — the canonical cross-vendor entity-resolution service (v3 architecture §12A).

⭐ SCOPE (reconciled by NF-W0, 2026-08-05). The lake ALREADY carries espn / sportradar / pff /
pfr / yahoo / sleeper / esb / smart ids on `weekly_rosters`, so this is a RECONCILIATION of ids
that exist, NOT a canonical-id build from nothing. `canonical_player_id` IS the nflverse
`gsis_id` — the key every downstream consumer (`fct_player_week`, `season_projection`,
`export_draft_board_json`) already projects on. Minting a new surrogate would orphan all of them.

Two joins are genuinely unresolved, and they have DIFFERENT consumers:

  1. `snap_counts` → the player-week fact (`snap_bridge`). ⭐ THE NF-W1-CRITICAL ONE. snap_counts
     keys on `pfr_player_id`; the bridge is `weekly_rosters.pfr_id`, which is **25–53% NULL**
     (measured 2022–2025). Today a miss is `coalesce(offense_pct, 0.0)` — a SILENT ZERO, not a
     null. Measured on the live lake: **Michael Woods II played 100% of CLE's week-15 2024 snaps
     and the fact serves him a 0.00 snap share**, because snap_counts writes "Michael Woods II"
     while that season's roster row writes "Mike Woods" with a NULL `pfr_id`. That corrupt zero is
     a feature NF-W1 would train on.

     ⭐ WHAT ACTUALLY FIXES IT — a SEASON-AGNOSTIC vendor map, not a cleverer name match. A
     `pfr_id` is a stable property of a PLAYER; its presence in one season's roster row is not.
     Keying the crosswalk on the id alone (rather than on season+id, as both consumers do today)
     recovers Woods at **tier 1** from another season's row, and takes
     `high_value_unmatched_count` to **0** for every season 2022–2025. The name rungs handle the
     bulk residual; the cross-season id map is what rescues the high-value cohort.

  2. Odds-API player props (`props_identity`) — name-only identities, for the MARKET/props side.
     NF-W1 excludes markets as features, so this leg serves the props/CLV vertical.

WHY A NULL BEATS A ZERO HERE (the whole point of the story). A snap share is a RATE in [0, 1] and
0.0 is a perfectly legal value — "dressed, played no offensive snaps". So a join miss rendered as
0.0 is INDISTINGUISHABLE from a real observation: no error, no NULL, no coverage gate can see it,
and a model trains on it as fact. §12A's rule is therefore absolute — an unmatched high-value
feature falls back to the lower tier, is flagged source-degraded, is recorded in QA, and is
NEVER silently set to zero or silently dropped.

The match-order ladder (§12A), each rung with its own confidence:

    1. stable vendor id      (`pfr_id` → gsis_id)                            1.00
    2. reviewed crosswalk    (a human-reviewed override file)                0.99
    3. exact normalized name + team + position-GROUP, unique candidate       0.95
    4. constrained match     — exact name + team (position relaxed), then a
       blocked Jaro-Winkler ≥ 0.92 inside one (season, week, team) cell   0.60–0.90
    5. manual review         — UNRESOLVED, flagged source-degraded, in QA    0.00

⛔ Tier 4 is CONSTRAINED, never global: a fuzzy candidate must come from a single
(season, week, team) block and must be the unique survivor. `resolve()` refuses to run a fuzzy
rung at all for a source that declares no blocking constraint — which is what makes
"name-only props cannot be joined on fuzzy name alone" a mechanical property rather than a
convention (see `props_identity`).

Monitors (§12A) — `monitors.evaluate`: `unmatched_rate`, `low_confidence_rate`,
`high_value_unmatched_count`, `silent_drop_count`. **`silent_drop_count` must equal 0** and is
NOT threshold-governed: any value > 0 fails closed unconditionally.

Everything here is pure pandas so it is provable offline in the fast gate; the lake driver
(`run_entity_resolution.py`) only pulls narrow frames and hands them to these functions.
"""
from __future__ import annotations

from .crosswalk import CROSSWALK_COLUMNS, build_crosswalk, empty_crosswalk, load_reviewed_crosswalk
from .monitors import (
    DEFAULT_THRESHOLDS,
    EntityResolutionFailClosed,
    MonitorReport,
    ResolutionThresholds,
    assert_fail_closed,
    assert_no_silent_zero,
    degraded_frame,
    evaluate,
    qa_records,
)
from .names import (
    POSITION_GROUPS,
    jaro_winkler,
    normalize_name,
    normalize_team,
    position_group,
)
from .resolver import (
    MATCH_CONFIDENCE,
    MATCH_METHODS,
    METHOD_EXACT_NAME_TEAM_POS,
    METHOD_FUZZY_CONSTRAINED,
    METHOD_NAME_TEAM_RELAXED,
    METHOD_REVIEWED,
    METHOD_UNRESOLVED,
    METHOD_VENDOR_ID,
    ResolutionSpec,
    resolve,
)
from .props_identity import PROPS_SPEC, resolve_prop_players
from .snap_bridge import (
    SNAP_SPEC,
    SNAP_VALUE_COLUMNS,
    attach_snaps_to_player_week,
    resolve_snap_counts,
    skill_starter_mask,
)

__all__ = [
    "CROSSWALK_COLUMNS",
    "DEFAULT_THRESHOLDS",
    "MATCH_CONFIDENCE",
    "MATCH_METHODS",
    "METHOD_EXACT_NAME_TEAM_POS",
    "METHOD_FUZZY_CONSTRAINED",
    "METHOD_NAME_TEAM_RELAXED",
    "METHOD_REVIEWED",
    "METHOD_UNRESOLVED",
    "METHOD_VENDOR_ID",
    "POSITION_GROUPS",
    "PROPS_SPEC",
    "SNAP_SPEC",
    "SNAP_VALUE_COLUMNS",
    "EntityResolutionFailClosed",
    "MonitorReport",
    "ResolutionSpec",
    "ResolutionThresholds",
    "assert_fail_closed",
    "assert_no_silent_zero",
    "attach_snaps_to_player_week",
    "build_crosswalk",
    "degraded_frame",
    "empty_crosswalk",
    "evaluate",
    "jaro_winkler",
    "load_reviewed_crosswalk",
    "normalize_name",
    "normalize_team",
    "position_group",
    "qa_records",
    "resolve",
    "resolve_prop_players",
    "resolve_snap_counts",
    "skill_starter_mask",
]
