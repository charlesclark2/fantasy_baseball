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

from collections.abc import Sequence
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


#: Roster slots that hold players you CANNOT SPEND A DRAFT PICK ON — injured-reserve and (Sleeper)
#: taxi spots. All three platform adapters already emit these under canonical names, so keying on the
#: name is a statement about OUR vocabulary, not about a vendor's.
#:
#: ⭐ WHY THIS EXISTS AS A SEPARATE IDEA FROM `bench`. `bench=True` means "creates no starter demand"
#: — correct for BN *and* IR, and that is all replacement-level cares about. But the draft optimizer's
#: reserve constraint asks a different question: HOW MANY PICKS DO I HAVE LEFT? An IR spot is bench
#: depth that no pick can ever reach, so counting it inflates the answer, and the constraint —
#: which binds only when `picks_remaining <= open_starter_count` — fires that many picks LATE.
#:
#: Measured on the live 2026 ESPN mock that surfaced this (9 starters + 6 bench + 2 IR): the roster
#: counted as 17 against ESPN's own limit of 15, so `must_fill` first turned true with the roster
#: ALREADY FULL — i.e. never in time. The user reached the final two picks with D/ST and K both
#: empty and was recommended a backup QB and five tight ends, which is the exact illegal-roster
#: ending the reserve constraint was written to make impossible.
#:
#: ⚠️ ERR TOWARD COUNTING A SLOT. An unrecognised slot stays draftable: over-counting only delays a
#: constraint that is inert with slack, whereas under-counting fires it EARLY and would force K/DST
#: on a user who still had picks to spare — distorting normal drafting, which the constraint
#: explicitly must not do.
RESERVE_SLOT_NAMES = frozenset({"IR", "TAXI"})


def draftable_slot_count(roster: "Sequence[RosterSlot]") -> int:
    """How many players a team actually DRAFTS — every roster slot except the reserve ones.

    ⚠️ LOCK-STEP: mirrored in `frontend/lib/draft-optimizer.ts` (`draftableSlotCount`).
    """
    return sum(s.count for s in roster if s.name.upper() not in RESERVE_SLOT_NAMES)


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
    # ── NF-C5: how the league DRAFTS ──────────────────────────────────────────────────────────────
    # "snake" (the default, and what every shipped preset is) or "auction". This changes NOTHING
    # about scoring or value-over-replacement — a player is worth the same points either way — it
    # changes only how that value is TRANSACTED, which is why it sits here beside `n_teams` rather
    # than anywhere near `scoring`. `auction_budget` is the per-team budget in the league's own
    # currency; it is meaningless (and ignored) under "snake", and defaults to $200 for an auction
    # because that is the near-universal host default.
    draft_type: str = "snake"
    auction_budget: int = 200
    # ── NF-C0b: league rules CAPTURED FOR FIDELITY THAT THE ENGINE DELIBERATELY DOES NOT APPLY ────
    # A real league carries rules that are genuinely part of its identity but have NO effect on a
    # per-player season projection or on value-over-replacement — the motivating case is Sleeper's
    # "second matchup vs the league median", which changes STANDINGS/SCHEDULE outcomes, not what any
    # player is projected to score. Storing them here (rather than dropping them on import, or worse
    # smuggling them into `scoring.per_stat` where they WOULD silently move a number) keeps a
    # round-tripped config faithful to the league while making it structurally impossible for the
    # scorer to act on them: NOTHING in `scoring`/`vor`/`draft` reads this field, by design.
    # The UI's contract is to SHOW these as "captured, not applied to the board".
    captured_rules: dict[str, object] = field(default_factory=dict)

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
        if self.draft_type not in ("snake", "auction"):
            raise ValueError(
                f"draft_type must be 'snake' or 'auction', got {self.draft_type!r}"
            )
        # ⚠️ Only enforced FOR an auction. A snake league carries the default budget as inert
        # baggage, and refusing it there would fail configs that have no auction in them at all.
        if self.draft_type == "auction" and self.auction_budget <= 0:
            raise ValueError(
                f"an auction league needs a positive auction_budget, got {self.auction_budget}"
            )
        return self

    def roster_spots(self) -> int:
        """Total spots on ONE team — starters AND bench. The auction pool's reserve is built from
        this (every spot costs at least the minimum bid), so bench depth is not free money."""
        return sum(int(s.count) for s in self.roster)

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
            "captured_rules": dict(self.captured_rules),
            # NF-C5. Always emitted (never conditional on being an auction) so a round-tripped
            # config has ONE shape — a key that appears only sometimes is the shape a reader gets
            # wrong (NF-C0's dropped-key class, on the serialize side).
            "draft_type": self.draft_type,
            "auction_budget": int(self.auction_budget),
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
            captured_rules=dict(d.get("captured_rules") or {}),
            # NF-C5 — absent on any config serialized before this shipped, and the safe default is
            # "snake": every league that exists today is one, and reading an old config as an
            # auction would invent a budget nobody set.
            draft_type=str(d.get("draft_type") or "snake"),
            auction_budget=int(d.get("auction_budget") or 200),
        ).validate()

    def with_overrides(self, **kwargs) -> "LeagueConfig":
        """Return a copy with fields replaced (the 'custom override on a preset' path)."""
        return replace(self, **kwargs).validate()
