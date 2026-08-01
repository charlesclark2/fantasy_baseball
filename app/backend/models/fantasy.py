"""Fantasy league-settings models (NF-C0b) — the persisted shared config contract.

These mirror `quant_sports_intel_models.fantasy_engine.league_config.LeagueConfig.to_dict()` exactly,
so a league SAVED by the manual editor and a league POPULATED by a platform import (NF-C0) are the
same object, and either round-trips through this API unchanged. The backend deliberately does NOT
import `fantasy_engine` — the Lambda bundle carries neither pandas/numpy nor
`quant_sports_intel_models`, and its zip already sits near the size cap — so the validation rules are
restated here and kept honest by `betting_ml/tests/test_nf_c0b_league_settings.py`, which asserts
this schema and `LeagueConfig.validate()` accept and reject the same configs.

🚨 E9.49 DISCIPLINE — A WRITE-TIME RULE MUST NEVER RUN ON THE READ PATH. The shared field set lives
in a validator-FREE base; `LeagueSave` (inbound) owns every rule, and `League` (outbound) owns NONE.
A response model that subclasses a request model makes every future tightening RETROACTIVE over
stored rows: when E9.49 made `total_line` required for over/under, one legacy bet started raising on
READ and blanked the entire bet log. League configs are long-lived user data that we fully expect to
extend, so that separation matters more here, not less.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# Bounds are deliberately generous — this is a floor for leagues we cannot import, so the goal is to
# admit any real league, not to police format taste. They exist only to keep a payload sane.
MAX_ROSTER_SLOTS = 40
MAX_SLOT_COUNT = 40
MAX_STAT_TERMS = 200
MAX_NAME_LEN = 80


class RosterSlotModel(BaseModel):
    """One starting-lineup or bench slot. A BENCH slot (BN/IR) may declare an EMPTY eligibility
    list — it never starts, so it contributes no starter demand and cannot move replacement level."""

    name: str
    count: int
    eligible: list[str] = Field(default_factory=list)
    bench: bool = False


class ScoringRulesModel(BaseModel):
    per_stat: dict[str, float] = Field(default_factory=dict)
    position_bonuses: dict[str, dict[str, float]] = Field(default_factory=dict)


class _LeagueFields(BaseModel):
    """The shared field set — DELIBERATELY carries NO validators (see the module docstring)."""

    name: str
    sport: str = "nfl"
    n_teams: int
    ppr: str = "custom"
    superflex: bool = False
    description: str = ""
    format_version: str = "1.0"
    scoring: ScoringRulesModel
    roster: list[RosterSlotModel] = Field(default_factory=list)
    # League rules captured for fidelity that the engine deliberately does NOT apply (median
    # scoring, etc.). Stored verbatim; never read by any scorer.
    captured_rules: dict[str, object] = Field(default_factory=dict)

    # ── NF-C0 import provenance ───────────────────────────────────────────────────────────────
    # Where a league CAME FROM. Storage metadata in the same class as `created_at` — deliberately
    # NOT part of `LeagueConfig.to_dict()`, so the shared config contract is unchanged and an
    # imported league remains byte-identical to a hand-entered one once you drop the envelope.
    # A hand-entered league simply leaves these None, which is what keeps "an imported league and a
    # typed-in league are the IDENTICAL object" literally true rather than nearly true.
    #
    # They earn their place by enabling ONE thing the config cannot express: re-reading LIVE draft
    # state for a saved league (`GET /fantasy/leagues/{id}/live`). Draft state is never persisted —
    # a stored snapshot of "who is already drafted" is wrong the moment the next pick lands — so the
    # league has to remember which platform league to go back and ask.
    source_platform: str | None = None
    source_league_id: str | None = None
    imported_at: str | None = None


class LeagueSave(_LeagueFields):
    """Inbound payload for POST/PUT. Every validator here applies to SAVES only."""

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("league name is required")
        if len(v) > MAX_NAME_LEN:
            raise ValueError(f"league name must be at most {MAX_NAME_LEN} characters")
        return v

    @field_validator("n_teams")
    @classmethod
    def _teams_in_range(cls, v: int) -> int:
        if not 2 <= v <= 32:
            raise ValueError("n_teams must be between 2 and 32")
        return v

    @field_validator("scoring")
    @classmethod
    def _scoring_nonempty(cls, v: ScoringRulesModel) -> ScoringRulesModel:
        if not v.per_stat:
            raise ValueError("scoring.per_stat is empty — a league must score at least one stat")
        if len(v.per_stat) > MAX_STAT_TERMS:
            raise ValueError(f"scoring.per_stat has more than {MAX_STAT_TERMS} terms")
        for key, weight in v.per_stat.items():
            if not isinstance(key, str) or not key:
                raise ValueError("every scoring key must be a non-empty string")
            if abs(float(weight)) > 1000:
                raise ValueError(f"scoring weight for {key!r} is out of range")
        return v

    @model_validator(mode="after")
    def _roster_is_rankable(self) -> "LeagueSave":
        """Mirror of `LeagueConfig.validate()`: a config with no STARTING slot has nothing to rank
        against, so value-over-replacement is undefined — reject it at write time rather than
        storing a league that can never produce a board."""
        if len(self.roster) > MAX_ROSTER_SLOTS:
            raise ValueError(f"roster has more than {MAX_ROSTER_SLOTS} slots")
        for s in self.roster:
            if not s.name.strip():
                raise ValueError("every roster slot needs a name")
            if s.count < 0 or s.count > MAX_SLOT_COUNT:
                raise ValueError(f"roster slot {s.name!r} has an invalid count")
            if not s.bench and not s.eligible:
                raise ValueError(f"starting slot {s.name!r} has no eligible positions")
        if not any((not s.bench) and s.count > 0 for s in self.roster):
            raise ValueError("config has no starting slots — nothing to rank against")
        return self


class League(_LeagueFields):
    """Outbound representation of a stored league. Carries NO validators on purpose: a rule
    tightened for saves must never make an already-stored league unreadable."""

    league_id: str
    user_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
