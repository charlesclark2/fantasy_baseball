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
MAX_IMPORTED_ROSTER_PLAYERS = 60

# ── NF-C6P3: the WHOLE league's rosters ──────────────────────────────────────────────────────────
# `MAX_IMPORTED_ROSTER_PLAYERS` bounds ONE team. A whole league is a different order of magnitude and
# needs its own limit, because these all land in the SAME DynamoDB item: `fantasy_leagues` is a map
# on the user row, so a subscriber's 25 leagues share one 400 KB ceiling with their portfolio, their
# platform tokens and their MLB leagues. Measured on the real captured ESPN league (10 teams / 172
# players) the slim form below is ~11 KB; a 14-team league is ~16 KB. Twenty-five of those would be
# 400 KB on their own — i.e. a per-league cap ALONE cannot keep the item safe, which is why
# `dynamo.put_fantasy_league` carries a second, TOTAL budget. These two bounds do different jobs and
# both are needed.
MAX_LEAGUE_ROSTER_TEAMS = 32  # the `n_teams` ceiling — a league cannot have more rosters than teams
MAX_LEAGUE_ROSTER_PLAYERS = 500  # total across every team: 32 × 15 starters + deep benches

#: The per-player fields kept for OTHER teams. Deliberately NOT `ImportedPlayer.to_dict()`:
#: `player_key` is a platform id that is not joinable to anything of ours (`canonical.ImportedPlayer`
#: says so in its own docstring) and `starter` is THEIR lineup decision, which the comparison
#: explicitly does not use — it fills every roster with OUR optimizer, and says so. Dropping the two
#: is a 40% size saving on the field that is up against the item ceiling.
LEAGUE_ROSTER_PLAYER_FIELDS = ("name", "position", "team")


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

    # ── NF-C5 — how the league DRAFTS ─────────────────────────────────────────────────────────
    # ⚠️ DECLARED HERE OR SILENTLY DROPPED. These models set no `extra="forbid"`, so a key the
    # model does not declare is accepted, ignored and lost with a 200 and no error anywhere — the
    # E8.6 silent-save class. `canonical.build_config` now emits both, so without these two lines
    # every imported league would round-trip through the store having quietly lost its draft type.
    #
    # Neither affects scoring or value-over-replacement — a player is worth the same points either
    # way — so they sit here beside `n_teams` and nothing in the scorer reads them. `auction_budget`
    # is meaningless under "snake" and is carried as inert baggage rather than made conditional: a
    # key that appears only sometimes is the shape a reader gets wrong.
    draft_type: str = "snake"
    auction_budget: int = 200

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

    # ── NF-C6: WHICH imported team is the user's own, and its roster snapshot ────────────────
    # A platform's roster payload is never joinable to our own player ids (`canonical.ImportedPlayer`
    # docstring), and ESPN's response never identifies the requesting account at all (its adapter
    # sets `is_owner=False` unconditionally, by design — "nobody is marked rather than guessing").
    # Sleeper CAN in principle, but the common import path (paste a league ID) never resolves a
    # Sleeper user id either. So there is no reliable AUTO-detection across platforms today: the
    # import UI asks the user which of the previewed teams is theirs (pre-filled from `is_owner`
    # when a platform did supply it, e.g. Yahoo's OAuth identity) and that choice — plus the chosen
    # team's roster AT THAT MOMENT — is what gets saved here.
    #
    # ⚠️ A SNAPSHOT, NOT A LIVE READ, and deliberately so: unlike draft state (which the live/{id}
    # endpoint re-fetches because a stale "who's drafted" is actively misleading), a roster snapshot
    # persisted at (re-)import time is a bounded, cheap, uniform choice that works identically across
    # all three platforms — including ESPN, which structurally CANNOT be re-fetched at all (the paste
    # flow never lets this server call ESPN). `roster_synced_at` is shown so the age is never hidden;
    # re-importing the league (the existing "update rather than duplicate" path) refreshes it.
    source_team_key: str | None = None
    source_team_name: str | None = None
    # Each entry mirrors `canonical.ImportedPlayer.to_dict()`: player_key/name/position/team/starter.
    imported_roster: list[dict] | None = None
    roster_synced_at: str | None = None

    # ── NF-C6P3: EVERY team's roster, not just the user's own ─────────────────────────────────
    # ⭐ THE FINDING THAT MADE THIS CHEAP: we already FETCH all of them. `ImportedLeague.teams[]`
    # carries `players` for every adapter — it is how the "which of these is your team?" screen
    # works — and then we threw all but one away. So the surface that said "we do not hold your
    # league's other rosters, so these are not waiver claims" was describing a limit we had
    # imposed on ourselves, and the fix was to KEEP them rather than to reword the caveat.
    #
    # Two things it makes possible, neither of which was expressible before: a TRUE free-agent pool
    # (a player on nobody's roster, instead of "outside the pool a league your size drafts"), and a
    # comparison of your roster against the other teams in your own league.
    #
    # ⚠️ A SNAPSHOT AT IMPORT TIME, exactly like `imported_roster`, and the surfaces must keep
    # saying so: we never re-fetch, so a waiver claim made after the import is invisible to us.
    # `league_rosters_synced_at` is what keeps the age honest.
    #
    # ⚠️ BOUNDED, AND TRUNCATION IS BY WHOLE TEAMS. `LeagueSave` slims and caps this; the writer
    # applies a second total-item budget. Both drop ENTIRE teams — never players within a team —
    # because a half-stored roster would produce a team total that is quietly too low and looks
    # exactly like a real one, whereas a missing team is simply absent and can be counted and named
    # ("we hold 8 of your 12 rosters"). `league_rosters_truncated` records that it happened.
    league_rosters: list[dict] | None = None
    league_rosters_synced_at: str | None = None
    league_rosters_truncated: bool = False


def bound_league_rosters(
    rosters: list[dict] | None,
) -> tuple[list[dict] | None, bool]:
    """Slim and cap a whole league's rosters. Returns `(kept, truncated)`.

    ⭐ TRUNCATION IS BY WHOLE TEAMS, IN ORDER, AND THAT IS THE LOAD-BEARING CHOICE. Dropping players
    from inside a team would leave a roster that still LOOKS complete and whose optimal-lineup total
    is quietly too low — a plausible wrong number, which is the class this repo keeps paying for
    (E9.46's rank, the empty D/ST slot this same story fixes). A dropped TEAM is simply absent: it
    can be counted, named and rendered as "we hold 8 of your 12 rosters".

    Slimming to `LEAGUE_ROSTER_PLAYER_FIELDS` is not cosmetic either — it is what keeps the field
    inside the shared item budget (see the constants above).

    Pure and total: a malformed entry is skipped rather than raised on, because this runs on a WRITE
    that the user experiences as "save my league" and a single junk row must not cost them the save.
    A skipped entry counts as truncation, so it is never silent.
    """
    if rosters is None:
        return None, False

    kept: list[dict] = []
    players_kept = 0
    truncated = False
    for entry in rosters:
        if not isinstance(entry, dict):
            truncated = True
            continue
        raw_players = entry.get("players")
        if not isinstance(raw_players, list):
            raw_players = []
        players = [
            {f: (p.get(f) if p.get(f) is not None else None) for f in LEAGUE_ROSTER_PLAYER_FIELDS}
            for p in raw_players
            if isinstance(p, dict)
        ]
        if len(kept) >= MAX_LEAGUE_ROSTER_TEAMS:
            truncated = True
            continue
        if players_kept + len(players) > MAX_LEAGUE_ROSTER_PLAYERS:
            # This team does not fit WHOLE, so it does not go in at all. Continuing rather than
            # breaking lets a later, smaller team still land — the cap is on total players, not on
            # position in the list.
            truncated = True
            continue
        kept.append(
            {
                "team_key": str(entry.get("team_key") or ""),
                "team_name": str(entry.get("team_name") or entry.get("name") or ""),
                "players": players,
            }
        )
        players_kept += len(players)

    return kept, truncated


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

    @field_validator("imported_roster")
    @classmethod
    def _roster_size_sane(cls, v: list[dict] | None) -> list[dict] | None:
        if v is not None and len(v) > MAX_IMPORTED_ROSTER_PLAYERS:
            raise ValueError(f"imported_roster has more than {MAX_IMPORTED_ROSTER_PLAYERS} players")
        return v

    @model_validator(mode="after")
    def _bound_league_rosters(self) -> "LeagueSave":
        """NF-C6P3 — SLIM AND CAP, never reject.

        ⚠️ DELIBERATELY NOT A `raise` like `_roster_size_sane` above, and the difference matters.
        `imported_roster` over 60 players is a malformed payload — no real team has one. A league's
        combined rosters legitimately RUN LARGE (a 32-team dynasty), and refusing the save would
        fail the user's whole import over an enhancement they never asked for. So the oversized
        part is dropped, the drop is RECORDED on `league_rosters_truncated`, and the surfaces
        render "we hold N of your M rosters" — an absence reported, never imputed.

        ⚠️ IT LIVES ON `LeagueSave`, NOT ON `_LeagueFields`. E9.49: a write-time rule that ran on
        the READ path would re-slim every stored league on every read, and the day the shape changes
        it would silently rewrite history under the user.
        """
        if self.league_rosters is None:
            return self
        kept, truncated = bound_league_rosters(self.league_rosters)
        self.league_rosters = kept
        # ⭐ OR, never assignment: a client that already truncated (the importer slims before it
        # sends) has told us something true, and overwriting its flag with our own `False` would
        # erase it. Truncation is a claim that can only ever be added to.
        self.league_rosters_truncated = bool(self.league_rosters_truncated or truncated)
        return self

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
