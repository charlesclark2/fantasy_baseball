"""league_config.py — the SPORT-AGNOSTIC declarative league-settings object (the shared contract).

A `LeagueConfig` fully describes ONE fantasy league: how a stat line scores, what the starting lineup
looks like (dedicated + FLEX/SUPERFLEX slots), how many teams, and which sport it belongs to. The
engine reads NOTHING else — a sport is expressed entirely through the config's stat keys + roster
eligibility + its `SportProfile` (the raw-column mapping). This is the object that BOTH the MVP-2
manual format-entry AND the NF-C0 platform import produce, so it round-trips through JSON
(`to_dict`/`from_dict`) unchanged — that is the "shared contract" invariant.

Nothing here is NFL-specific: `ScoringRules.per_stat` keys are arbitrary canonical stat identifiers,
roster `eligible` positions are arbitrary strings, and `position_bonuses` covers per-position wrinkles
(e.g. TE-premium PPR) without the engine knowing what a "TE" is.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

CONFIG_FORMAT_VERSION = "1.0"

# Slot names the engine treats as multi-position FLEX pools (purely a naming convenience for presets;
# the ACTUAL eligibility always comes from `RosterSlot.eligible`, never from the name — a league can
# call a slot anything). Kept so a preset / importer can spell a common flex by name.
FLEX_ALIASES = ("FLEX", "SUPERFLEX", "OP", "WRT", "WR/RB", "RB/WR/TE", "REC_FLEX")


@dataclass(frozen=True)
class ScoringRules:
    """Per-stat scoring: a canonical `stat_key -> points-per-unit` map, plus optional per-position
    bonuses (the general home for TE-premium PPR, position-specific TD values, etc.).

    `per_stat` keys are canonical stat identifiers the `SportProfile` maps to raw projection columns
    (e.g. NFL `"pass_yds"`, `"rec"`). A stat absent from `per_stat` simply scores 0. `position_bonuses`
    is `{position: {stat_key: extra_points_per_unit}}` — added ONLY for players of that position (so
    TE-premium is `{"TE": {"rec": 0.5}}`), keeping the engine position-agnostic.
    """

    per_stat: dict[str, float]
    position_bonuses: dict[str, dict[str, float]] = field(default_factory=dict)

    def points_for(self, stat_key: str, position: str | None = None) -> float:
        base = float(self.per_stat.get(stat_key, 0.0))
        if position is not None:
            base += float(self.position_bonuses.get(position, {}).get(stat_key, 0.0))
        return base

    def to_dict(self) -> dict:
        return {
            "per_stat": {k: float(v) for k, v in self.per_stat.items()},
            "position_bonuses": {
                pos: {k: float(v) for k, v in bonus.items()}
                for pos, bonus in self.position_bonuses.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoringRules":
        return cls(
            per_stat={k: float(v) for k, v in (d.get("per_stat") or {}).items()},
            position_bonuses={
                pos: {k: float(v) for k, v in (bonus or {}).items()}
                for pos, bonus in (d.get("position_bonuses") or {}).items()
            },
        )


@dataclass(frozen=True)
class RosterSlot:
    """One starting-lineup slot type. `count` of them per team; each fillable by any player whose
    position is in `eligible`. A dedicated slot has a single eligible position (`("QB",)`); a FLEX has
    several (`("RB","WR","TE")`); a SUPERFLEX adds the QB (`("QB","RB","WR","TE")`). `bench=True` marks
    non-scoring depth (BN/IR) that contributes NO starter demand (so it does not affect replacement)."""

    name: str
    count: int
    eligible: tuple[str, ...]
    bench: bool = False

    @property
    def is_flex(self) -> bool:
        return (not self.bench) and len(self.eligible) > 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "count": int(self.count),
            "eligible": list(self.eligible),
            "bench": bool(self.bench),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RosterSlot":
        return cls(
            name=str(d["name"]),
            count=int(d["count"]),
            eligible=tuple(d.get("eligible") or ()),
            bench=bool(d.get("bench", False)),
        )


@dataclass(frozen=True)
class SportProfile:
    """How a sport's RAW projection frame plugs into the engine — pure mapping, no scoring policy.

    * `sport`             — "nfl" | "mlb" | …
    * `stat_columns`      — canonical `stat_key -> raw projection column` (e.g. `"pass_yds" ->
                            "proj_pass_yds"`). The scorer reads a stat only through this map, so the
                            engine never hardcodes a column name.
    * `positions`         — the fantasy positions this sport ranks (drives per-position replacement).
    * `position_column`   — the projection column carrying a player's position.
    * `base_points_column`/`base_sd_column` — the projection's convenience point total + its sd, used
                            ONLY to carry an uncertainty CV through the rescore (see `scoring`). Kept
                            optional: a projection without them simply yields no interval.
    * `base_p10_column`/`base_p90_column` — the projection's OWN 80% bounds. Optional, and supplying
                            them changes the rescore materially: with them, each SIDE of the band is
                            carried through independently, so an ASYMMETRIC interval survives. Without
                            them the rescore can only rebuild a symmetric ±z·sd band, which silently
                            re-centres a skewed interval (NF1.7 — the rookie band is very skewed).
    * `position_aliases`  — fold odd raw positions into a ranked one (NFL: FB→RB, so a fullback is
                            RB/flex-eligible rather than an un-scarce island).
    """

    sport: str
    stat_columns: dict[str, str]
    positions: tuple[str, ...]
    position_column: str = "position"
    base_points_column: str | None = None
    base_sd_column: str | None = None
    base_p10_column: str | None = None
    base_p90_column: str | None = None
    position_aliases: dict[str, str] = field(default_factory=dict)

    def normalize_position(self, pos: str | None) -> str | None:
        if pos is None:
            return None
        return self.position_aliases.get(pos, pos)


@dataclass(frozen=True)
class LeagueConfig:
    """A complete league definition. `scoring` + `roster` + `n_teams` + `ppr` describe the format;
    `sport` ties it to a `SportProfile`. `ppr` is a human-readable label only (the ACTUAL per-reception
    value lives in `scoring.per_stat["rec"]`) so a config is self-describing without the engine."""

    name: str
    sport: str
    n_teams: int
    scoring: ScoringRules
    roster: tuple[RosterSlot, ...]
    ppr: str = "standard"  # "standard" | "half" | "ppr" | "custom" — a descriptive label
    superflex: bool = False
    description: str = ""
    format_version: str = CONFIG_FORMAT_VERSION

    # ── derived views the engine uses ─────────────────────────────────────────────────────────────
    def starter_slots(self) -> tuple[RosterSlot, ...]:
        return tuple(s for s in self.roster if not s.bench)

    def dedicated_demand(self) -> dict[str, int]:
        """League-wide dedicated starter spots per position = n_teams × single-eligibility slot counts."""
        out: dict[str, int] = {}
        for s in self.starter_slots():
            if len(s.eligible) == 1:
                out[s.eligible[0]] = out.get(s.eligible[0], 0) + self.n_teams * s.count
        return out

    def flex_slot_specs(self) -> list[tuple[frozenset[str], int]]:
        """The multi-eligibility (FLEX/SUPERFLEX) slots as `(eligible_set, league_wide_spots)`."""
        return [
            (frozenset(s.eligible), self.n_teams * s.count)
            for s in self.starter_slots()
            if len(s.eligible) > 1
        ]

    def validate(self) -> "LeagueConfig":
        if self.n_teams <= 0:
            raise ValueError(f"n_teams must be positive, got {self.n_teams}")
        if not self.scoring.per_stat:
            raise ValueError("scoring.per_stat is empty — a league must score at least one stat")
        for s in self.roster:
            if s.count < 0:
                raise ValueError(f"roster slot {s.name!r} has negative count {s.count}")
            if not s.bench and not s.eligible:
                raise ValueError(f"starter slot {s.name!r} has no eligible positions")
        if not any(not s.bench and s.count > 0 for s in self.roster):
            raise ValueError("config has no starting slots — nothing to rank against")
        return self

    def to_dict(self) -> dict:
        return {
            "format_version": self.format_version,
            "name": self.name,
            "sport": self.sport,
            "n_teams": int(self.n_teams),
            "ppr": self.ppr,
            "superflex": bool(self.superflex),
            "description": self.description,
            "scoring": self.scoring.to_dict(),
            "roster": [s.to_dict() for s in self.roster],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LeagueConfig":
        return cls(
            name=str(d["name"]),
            sport=str(d["sport"]),
            n_teams=int(d["n_teams"]),
            scoring=ScoringRules.from_dict(d["scoring"]),
            roster=tuple(RosterSlot.from_dict(s) for s in d.get("roster", [])),
            ppr=str(d.get("ppr", "standard")),
            superflex=bool(d.get("superflex", False)),
            description=str(d.get("description", "")),
            format_version=str(d.get("format_version", CONFIG_FORMAT_VERSION)),
        ).validate()

    def with_overrides(self, **kwargs) -> "LeagueConfig":
        """Return a copy with fields replaced (the 'custom override on a preset' path)."""
        return replace(self, **kwargs).validate()
