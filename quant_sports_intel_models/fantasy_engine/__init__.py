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

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ LAZY RE-EXPORTS — so `fantasy_engine.draft` can be imported WITHOUT pandas/numpy
# ══════════════════════════════════════════════════════════════════════════════════════════════
# `league_config`, `draft` and `auction` are pure stdlib; `scoring` and `vor` are pandas/numpy. This
# module used to import all five EAGERLY, which meant importing ANY of them pulled in pandas — so
# `import quant_sports_intel_models.fantasy_engine.draft` (a ~500-line, dependency-free optimizer)
# could not run anywhere pandas was absent, because Python executes a package's `__init__` before its
# submodule.
#
# That mattered for exactly one reason and it is a hard constraint, not a preference: NF-C-LDA-1's
# live-draft assistant runs `draft.recommend` INSIDE THE API LAMBDA, whose deployment zip carries no
# pandas and already sits near the size cap (`app/backend/models/fantasy.py` and
# `services/league_scoring.py` both record paying that tax). `infrastructure/lambda/deploy.sh` copies
# the three stdlib-only modules the way it already copies `betting_ml/utils/game_day.py` — a
# stdlib-only module lifted out of a heavy package — and this lazy `__init__` is what makes the
# import path resolve there.
#
# ⚠️ IT IS ALSO THE PERF LESSON'S OWN CURE, one level up: a transitive module-scope import is how the
# API Lambda silently reacquired `snowflake.connector`+pandas on every cold start (−21.8% once
# lazied). An eager re-export is that hazard built into a package's front door.
#
# Every public name still resolves — `from quant_sports_intel_models.fantasy_engine import recommend`
# works unchanged, it just imports `draft` at first use instead of at package import. Pinned by
# `betting_ml/tests/test_nf_c_lda_1_lambda_import_weight.py`, which asserts the draft import stays
# pandas-free IN A SUBPROCESS (in-process would be vacuous — pytest has already loaded pandas).
import importlib
from typing import TYPE_CHECKING

#: public name → the submodule that defines it.
_LAZY: dict[str, str] = {
    "APPLIED": "settings",
    "AuctionPool": "auction",
    "AuctionValue": "auction",
    "CAPTURED": "settings",
    "CoverageReport": "settings",
    "DEFAULT_AUCTION_BUDGET": "auction",
    "DEFAULT_MIN_BID": "auction",
    "DERIVED": "settings",
    "DRAFT_TYPES": "auction",
    "DerivedBucket": "settings",
    "FLEX_ALIASES": "league_config",
    "Inflation": "auction",
    "LeagueConfig": "league_config",
    "MaxBid": "auction",
    "OpenSlots": "draft",
    "Recommendation": "draft",
    "RosterRequirements": "draft",
    "RosterSlot": "league_config",
    "ScoringRules": "league_config",
    "SportProfile": "league_config",
    "StatTerm": "settings",
    "TermCoverage": "settings",
    "assign_tiers": "draft",
    "auction_pool": "auction",
    "auction_values": "auction",
    "build_board": "vor",
    "compute_replacement_levels": "vor",
    "dollars_per_slot": "auction",
    "inflation": "auction",
    "max_bid": "auction",
    "open_starter_slots": "draft",
    "picks_until_next": "draft",
    "recommend": "draft",
    "resolve_scoring": "settings",
    "score_players": "scoring",
}

if TYPE_CHECKING:  # pragma: no cover — import-time cost is exactly what this module avoids
    from quant_sports_intel_models.fantasy_engine.auction import *  # noqa: F401,F403
    from quant_sports_intel_models.fantasy_engine.draft import *  # noqa: F401,F403
    from quant_sports_intel_models.fantasy_engine.league_config import *  # noqa: F401,F403
    from quant_sports_intel_models.fantasy_engine.scoring import *  # noqa: F401,F403
    from quant_sports_intel_models.fantasy_engine.settings import *  # noqa: F401,F403
    from quant_sports_intel_models.fantasy_engine.vor import *  # noqa: F401,F403


def __getattr__(name: str):
    """PEP 562 — resolve a re-exported name by importing its submodule on first use."""
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f"{__name__}.{module}"), name)
    globals()[name] = value          # memoize, so repeat access costs nothing
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    "LeagueConfig",
    "RosterSlot",
    "ScoringRules",
    "SportProfile",
    "FLEX_ALIASES",
    "score_players",
    "compute_replacement_levels",
    "build_board",
    "recommend",
    "Recommendation",
    "RosterRequirements",
    "OpenSlots",
    "open_starter_slots",
    "assign_tiers",
    "picks_until_next",
    # NF-C5 — auction values + the live budget/inflation math (sport-agnostic; MLB roto reuses it)
    "auction_pool",
    "auction_values",
    "inflation",
    "max_bid",
    "dollars_per_slot",
    "AuctionPool",
    "AuctionValue",
    "Inflation",
    "MaxBid",
    "DEFAULT_AUCTION_BUDGET",
    "DEFAULT_MIN_BID",
    "DRAFT_TYPES",
]
