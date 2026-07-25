"""fantasy_engine — the SPORT-AGNOSTIC league-config + scoring + VOR engine (NF-C1 / MLB F-C1).

Built ONCE, instantiated per sport (the `hierarchical.py`-style reuse the roadmap calls for). Nothing
in this package knows what football is: it knows how to turn a RAW projected stat line + a declarative
league config into league-specific fantasy points, value-over-replacement, positional scarcity, and a
cross-position ranked board. A sport plugs in via a `SportProfile` (which raw columns map to which
canonical scoring stats, and which fantasy positions exist) plus its own presets; the NFL instantiation
lives in `football/nfl/fantasy/league_presets.py`, MLB reuses the same engine with baseball stats.

Layers:
  * `league_config`  — the declarative settings object (scoring rules + roster/starter slots + league
                       size + PPR variant) + JSON (de)serialization. This is the SHARED CONTRACT both
                       manual entry (MVP-2) and a platform import (NF-C0) produce.
  * `scoring`        — pure: apply a config's scoring rules to a raw stat line → league points, with an
                       honest uncertainty passthrough.
  * `vor`            — pure: positional scarcity / replacement level (flex + superflex allocation) →
                       value-over-replacement → a cross-position ranked board.

Edge-independent (a projection product): the gate is scoring correctness + a transparent
replacement-level definition + face-valid preset deltas, NOT `best_alpha`/PBO/DSR.
"""
from __future__ import annotations

from quant_sports_intel_models.fantasy_engine.league_config import (  # noqa: F401
    FLEX_ALIASES,
    LeagueConfig,
    RosterSlot,
    ScoringRules,
    SportProfile,
)
from quant_sports_intel_models.fantasy_engine.scoring import score_players  # noqa: F401
from quant_sports_intel_models.fantasy_engine.vor import (  # noqa: F401
    build_board,
    compute_replacement_levels,
)

__all__ = [
    "LeagueConfig",
    "RosterSlot",
    "ScoringRules",
    "SportProfile",
    "FLEX_ALIASES",
    "score_players",
    "compute_replacement_levels",
    "build_board",
]
