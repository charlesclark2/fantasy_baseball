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

import re

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

# ── NF-C7b: per-position DEPTH TARGETS ───────────────────────────────────────────────────────────
# How many of a position the user WANTS to end the draft holding. A position short of its target is
# a soft need, ranked below a real open starter slot and above generic bench depth (NF-C7).
#
# ⭐ WHY THIS LIVES ON THE LEAGUE RECORD AND NOT IN THE BROWSER. NF-C7 shipped it in localStorage
# keyed by season + scoring-format NAME, which meant two different leagues on the same format
# silently shared one setting, nothing synced across devices, and — the real gap — the Chrome
# extension could not read it at all. The extension already resolves the caller's saved league by
# id (`_draft_league_config`), so putting the targets on that record means the extension inherits
# them with NO new request field and NO client change: it dodges the E8.6 deploy-skew hazard
# (a newly-added request field that an un-deployed backend accepts, ignores and drops with a 200)
# entirely, because nothing new is ever sent.
#
# ⚠️ DECLARED ON `_LeagueFields` OR SILENTLY DROPPED — these models set no `extra="forbid"`.
#
# Item-budget note (NF-C6P3): a six-key int map is ~60 bytes per league, ~1.5 KB across a
# subscriber's 25 — three orders of magnitude inside the shared 400 KB ceiling. Measured, not
# assumed, because that ceiling is shared with the league rosters above.
DEPTH_TARGET_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
MAX_DEPTH_TARGET = 20


def sanitize_depth_targets(raw: object) -> dict[str, int]:
    """Normalise a depth-target map. Pure and total — never raises.

    Unknown positions are dropped, non-numeric values are dropped, and counts are clamped into
    `[0, MAX_DEPTH_TARGET]`. A zero is dropped rather than stored: "no target" and "a target of
    zero" are the same instruction to the optimizer, and keeping both spellings would let two
    records that behave identically compare unequal.

    ⚠️ DROPS rather than clamps an out-of-range or junk value on the WRITE path's behalf being a
    deliberate asymmetry with the UI's `NumericInput` (which rejects a bad keystroke outright): by
    the time a value reaches storage the user has no way to see a correction, so the safe move is
    to store nothing rather than a number they never chose.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for pos in DEPTH_TARGET_POSITIONS:
        value = raw.get(pos)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        count = int(value)
        if count <= 0 or count > MAX_DEPTH_TARGET:
            continue
        out[pos] = count
    return out


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

    # ── NF-C7b: per-position depth targets (see the module constants) ─────────────────────────
    # `None` means "this league has never been given targets" and is DISTINCT from `{}` ("the user
    # deliberately cleared them"): the first inherits the account default, the second does not.
    # Collapsing the two would make clearing a league's targets impossible — it would silently
    # re-inherit — which is the shape of a preference the user cannot turn off.
    depth_targets: dict[str, int] | None = None


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


class FantasyPreferences(BaseModel):
    """NF-C7b — ACCOUNT-level fantasy defaults (`GET/PUT /fantasy/preferences`).

    Deliberately its own model rather than a field on the league: these apply to every league the
    user has NOT given its own value, so they are not a property of any one league.

    ⚠️ NO VALIDATOR HERE. The router sanitises on the way in and again on the way out, and the
    normalisation is `sanitize_depth_targets` — the SAME function the league save uses, so an
    account default and a per-league value can never disagree about what a legal target is. Two
    normalisers for one field would be the E9.61 two-renderers shape.
    """

    depth_targets: dict[str, int] = Field(default_factory=dict)


class LeagueSave(_LeagueFields):
    """Inbound payload for POST/PUT. Every validator here applies to SAVES only."""

    @field_validator("depth_targets")
    @classmethod
    def _depth_targets_bounded(cls, v: dict | None) -> dict | None:
        """Normalise on the way IN only.

        ⚠️ ON `LeagueSave`, NOT ON `_LeagueFields` — E9.49. A validator on the shared base runs when
        a STORED record is serialized back out, so tightening an input rule would retroactively
        reject history: one league saved before the rule existed would raise on READ and, because
        the list endpoint builds its response in one comprehension, blank the caller's entire league
        list with a 500. Write rules live on the write model.
        """
        return None if v is None else sanitize_depth_targets(v)

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

    # ── NF-C0-Yahoo-ENABLE (Half A): why a deleted roster has to SAY it was deleted ────────────
    # True once a disconnect, or the retention window closing, removed roster data this league HAD
    # held (`dynamo.purge_platform_league_data` / the read-side expiry).
    #
    # ⭐ WITHOUT IT THE DELETION IS INDISTINGUISHABLE FROM A LEAGUE THAT NEVER DRAFTED. My Teams
    # branches on `source_team_key && !roster.length` and explains that state as "the platform
    # reported no rostered players — the usual reason is your league hasn't drafted yet." After a
    # purge that sentence is a confident, wrong explanation for something WE did, and it invites the
    # user to re-import to fix a non-problem. This is the NF-C6b ambiguous-empty-state class: an
    # absence must be reported, never imputed.
    #
    # ⚠️ ON `League`, NOT ON `_LeagueFields` — E9.49, and the same reasoning as the validators
    # above facing the other way. This is storage metadata about what we did to a record, not
    # something a client may assert about itself; putting it on the shared base would let a SAVE
    # set it. A hand edit that rewrites the league legitimately clears it, because the record being
    # written is the user's own and holds no purged platform data to describe.
    roster_retention_purged: bool = False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-C4 — the CUSTOM BIG BOARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# A user's own ranking of one published (config, size) board: an explicit ORDER PREFIX, the tier
# breaks they drew, and a target/avoid tag per player. See `frontend/lib/big-board.ts` for why the
# order is a prefix rather than a full copy, and for the identity that makes the prefix exact.
#
# ⭐ IT STORES NO MODEL OUTPUT. Not one projection, VOR, ADP or rank is persisted — only player ids
# and the user's own annotations. Three consequences worth stating, because they are what make this
# feature cheap and safe at once:
#   · a saved board can never serve a STALE number, because it holds none: it is re-joined to
#     whatever board is published at read time;
#   · the stored document is worth nothing to anyone who does not already have the (paid) board it
#     references, so a big board is not a second copy of the paywalled data;
#   · it is small, which is the constraint that actually binds (see `dynamo.MAX_FANTASY_BYTES`).
#
# ⚠️ BOUNDS, NOT TASTE. As with the league bounds above, these exist to keep a payload sane and to
# stop one board from being able to consume the shared item on its own. They are set ABOVE the size
# of any board we publish (858 rows on the 2026 export), so no real user can reach them by ranking
# players — a payload that does is not a big board.
MAX_BIG_BOARD_ORDER = 1000
MAX_BIG_BOARD_TIER_BREAKS = 200
MAX_BIG_BOARD_TAGS = 1000
#: How many rows on one board may carry a note, and how long a note may be.
#:
#: ⭐ THE NOTE CAP IS THE ONE FIELD ON THIS MODEL THAT CAN GROW WITHOUT BOUND FROM TYPING ALONE — an
#: id is ~10 bytes and fixed, a note is whatever a person writes. 300 x 200 chars is ~60 KB worst
#: case, which one board could not spend even if it wanted to: `put_fantasy_big_board` weighs the
#: WHOLE record against the shared 400 KB item budget (NF-C6P3) and refuses it outright. These caps
#: are what stop a single board from being the thing that fills the item, so the refusal stays rare
#: and lands on a board that is genuinely enormous rather than on a normal one.
#:
#: ⚠️ `MAX_BIG_BOARD_NOTE_LEN` is MIRRORED by `MAX_NOTE_LEN` in `frontend/lib/big-board.ts` so the
#: textarea stops the user where the server would truncate. The two are pinned equal by a guard.
MAX_BIG_BOARD_NOTES = 300
MAX_BIG_BOARD_NOTE_LEN = 200
MAX_PLAYER_ID_LEN = 40
#: ⚠️ HOW MANY BOARDS an account may keep is NOT here — it is a STORAGE ceiling and it lives beside
#: its sibling `MAX_LEAGUES_PER_USER` in `services/dynamo.py`. One number, one owner: this repo's
#: recurring defect is one logical thing with two owners (INC-30, INC-36, INC-38).

BIG_BOARD_TAGS = ("target", "avoid")


class _BigBoardFields(BaseModel):
    """The shared field set — carries NO validators (the E9.49 rule stated in the module docstring:
    a rule tightened for SAVES must never make an already-stored board unreadable)."""

    config: str
    size: int
    order: list[str] = Field(default_factory=list)
    tier_breaks: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)
    #: `{player id -> the user's own note}`. ADDITIVE (NF-C0): a client that predates this field
    #: sends nothing and gets `{}` back, and a stored board written before it reads the same way.
    notes: dict[str, str] = Field(default_factory=dict)


def _clean_ids(ids: list[str], limit: int) -> list[str]:
    """De-duplicated, non-empty, length-bounded player ids, in order, capped at `limit`.

    ⚠️ A DUPLICATE ID IS DROPPED RATHER THAN REJECTED, and that is the safe direction: `applyDoc`
    would otherwise render one player twice — two rows for the same man, colliding on their React
    key, one of which the user cannot act on. Silently correcting a shape no legitimate client
    produces beats failing a save the user experiences as losing their work.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        pid = str(raw or "").strip()
        if not pid or len(pid) > MAX_PLAYER_ID_LEN or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        if len(out) >= limit:
            break
    return out


class BigBoardSave(_BigBoardFields):
    """Inbound payload for `PUT /fantasy/nfl/custom-boards`. Every validator here applies to SAVES."""

    @field_validator("config")
    @classmethod
    def _config_shape(cls, v: str) -> str:
        v = str(v or "").strip()
        # A preset name (`half_ppr`) or a saved-league selection (`custom:<uuid>`). Bounded and
        # charset-restricted because it is half of a DynamoDB map key.
        if not v or len(v) > 60 or not re.fullmatch(r"[A-Za-z0-9_:-]+", v):
            raise ValueError("config is not a recognised board selection")
        return v

    @field_validator("size")
    @classmethod
    def _size_in_range(cls, v: int) -> int:
        if not 2 <= int(v) <= 32:
            raise ValueError("size must be between 2 and 32")
        return int(v)

    @field_validator("order")
    @classmethod
    def _bound_order(cls, v: list[str]) -> list[str]:
        return _clean_ids(v, MAX_BIG_BOARD_ORDER)

    @field_validator("tier_breaks")
    @classmethod
    def _bound_breaks(cls, v: list[str]) -> list[str]:
        return _clean_ids(v, MAX_BIG_BOARD_TIER_BREAKS)

    @field_validator("tags")
    @classmethod
    def _bound_tags(cls, v: dict[str, str]) -> dict[str, str]:
        """Keep only recognised tags, capped.

        ⚠️ AN UNRECOGNISED TAG IS DROPPED, NOT STORED. `extra="forbid"` is deliberately not set on
        these models (see `_LeagueFields`), so an unknown VALUE would otherwise be persisted and
        every consumer would have to defend against it forever. Two states is the contract.
        """
        out: dict[str, str] = {}
        for raw_id, raw_tag in (v or {}).items():
            pid = str(raw_id or "").strip()
            tag = str(raw_tag or "").strip()
            if not pid or len(pid) > MAX_PLAYER_ID_LEN or tag not in BIG_BOARD_TAGS:
                continue
            out[pid] = tag
            if len(out) >= MAX_BIG_BOARD_TAGS:
                break
        return out


    @field_validator("notes")
    @classmethod
    def _bound_notes(cls, v: dict[str, str]) -> dict[str, str]:
        """Trim, truncate and cap the user's notes.

        ⚠️ TRUNCATED, NOT REJECTED — and the client is what makes that honest. A save refused
        because one note ran three characters long would cost a user a whole curated board; the
        textarea already stops them at the same limit, so a note reaching here over-length is a
        client that is out of date rather than a person mid-sentence.

        A whitespace-only note is DROPPED rather than stored as `""`: an empty string is bytes in
        the shared item that carry no meaning, and every reader would have to treat it as absent
        anyway.
        """
        out: dict[str, str] = {}
        for raw_id, raw_note in (v or {}).items():
            pid = str(raw_id or "").strip()
            note = str(raw_note or "").strip()[:MAX_BIG_BOARD_NOTE_LEN]
            if not pid or len(pid) > MAX_PLAYER_ID_LEN or not note:
                continue
            out[pid] = note
            if len(out) >= MAX_BIG_BOARD_NOTES:
                break
        return out


class BigBoard(_BigBoardFields):
    """Outbound representation of a stored board. NO validators, on purpose — see `League`."""

    board_key: str
    created_at: str | None = None
    updated_at: str | None = None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-C-LDA-1 — the LIVE DRAFT ASSISTANT request
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# What the Chrome extension sends us from an ESPN draft room. Two properties are load-bearing and
# both are enforced here rather than trusted:
#
#   1. ⛔ IT IS NORMALIZED DATA ONLY — the identity fields ESPN publishes for each player, plus who
#      took whom. NO session cookie, NO request headers, NO raw response bodies. The extension's own
#      wire serializer builds this shape from an allowlist (`extension/src/wire.js`), and these
#      models are the second, server-side statement of the same contract: an unknown field is
#      REJECTED, not stored (`extra="forbid"`, deliberately unlike the league models — a draft
#      request is transient, so there is no deploy-skew reason to accept unknown keys, and refusing
#      them is what makes "we only ever receive these fields" checkable).
#
#   2. ⭐ POSITION AND TEAM ARE NOT ACCEPTED FROM THE CLIENT. The pool rows carry ESPN's raw
#      `defaultPositionId`/`eligibleSlots`/`proTeamId` and the SERVER derives from them, using the
#      same `platform_import.espn._player_position` the paste import uses. Deriving in the browser
#      would be a second position derivation, and the two-way-player fix (`Travis Hunter`) would
#      have landed on the server while the overlay kept the old answer.

#: A real ESPN draftable pool measured 1,027 rows; the whole player universe is ~11,600. Generous
#: enough for either, and a bound on what reaches the join.
MAX_DRAFT_POOL = 4000
#: A 12-team league drafts 180-240 players; 32 teams x 40 slots is 1,280.
MAX_DRAFT_PICKS = 1500


class DraftPoolEntry(BaseModel):
    """One player ESPN published in the draft room's pool — identity fields only."""

    model_config = {"extra": "forbid"}

    id: str
    fullName: str = ""
    proTeamId: int | None = None
    defaultPositionId: int | None = None
    eligibleSlots: list[int] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v):
        # ESPN player ids are integers in the payload and strings everywhere in our join.
        return "" if v is None else str(v)

    @field_validator("eligibleSlots")
    @classmethod
    def _bound_slots(cls, v: list[int]) -> list[int]:
        return v[:40]


class DraftPick(BaseModel):
    """One `SELECTED <teamId> <playerId>` frame from the live draft socket, in pick order."""

    model_config = {"extra": "forbid"}

    team: str
    player: str

    @field_validator("team", "player", mode="before")
    @classmethod
    def _coerce(cls, v):
        return "" if v is None else str(v)


class DraftAssistantRequest(BaseModel):
    """A live draft state → a recommendation.

    ⚠️ `league_id` XOR `espn_settings`: the caller either names one of their own SAVED leagues, or
    hands us the draft room's own settings block, which we translate with the SHIPPED ESPN adapter
    (`parse_settings_payload`, `assert_no_credentials` included). A mock draft has no saved league,
    and mock is the only surface a draft tool can be developed against — a real league drafts once a
    year — so the settings path is not a convenience, it is what makes this debuggable at all.
    """

    model_config = {"extra": "forbid"}

    season: int = Field(default=2026, ge=2000, le=2100)
    league_id: str | None = None
    espn_settings: dict | None = None

    pool: list[DraftPoolEntry] = Field(default_factory=list)
    picks: list[DraftPick] = Field(default_factory=list)
    #: ESPN's team id for the CALLER's own team, read from the draft-room URL (`teamId=`). Without
    #: it we can rank the board but cannot fill a roster, so the response says so rather than
    #: silently recommending as though the roster were empty.
    my_team: str | None = None
    #: Whose pick it is now (`SELECTING <teamId>`), and which overall pick that is. ⭐ ECHOED BACK
    #: in the response so the overlay can SHOW which pick the advice is about — a frozen read then
    #: looks frozen instead of looking like a quiet draft (see the router's docstring).
    on_the_clock_team: str | None = None
    overall_pick: int | None = Field(default=None, ge=0, le=10000)
    top_n: int = Field(default=8, ge=1, le=50)

    @field_validator("pool")
    @classmethod
    def _bound_pool(cls, v: list[DraftPoolEntry]) -> list[DraftPoolEntry]:
        if len(v) > MAX_DRAFT_POOL:
            raise ValueError(f"pool is larger than {MAX_DRAFT_POOL} rows")
        return v

    @field_validator("picks")
    @classmethod
    def _bound_picks(cls, v: list[DraftPick]) -> list[DraftPick]:
        if len(v) > MAX_DRAFT_PICKS:
            raise ValueError(f"more than {MAX_DRAFT_PICKS} picks")
        return v

    @field_validator("my_team", "on_the_clock_team", "league_id", mode="before")
    @classmethod
    def _coerce_optional(cls, v):
        return None if v is None else str(v)

    @model_validator(mode="after")
    def _needs_exactly_one_league_source(self):
        if bool(self.league_id) == bool(self.espn_settings):
            raise ValueError("provide exactly one of league_id or espn_settings")
        return self
