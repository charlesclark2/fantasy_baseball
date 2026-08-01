"""canonical.py — the ONE league model every platform adapter normalizes into (NF-C0).

🎯 THE CONTRACT. An imported league and a hand-entered (NF-C0b) league are the IDENTICAL object: the
`fantasy_engine` `LeagueConfig`, serialized by its `to_dict()`. There is deliberately NO second
settings schema — a Sleeper import, a Yahoo import and a typed-in league all land in the same
`fantasy_leagues` map, are read by the same `/fantasy/leagues` endpoints, and are scored by the same
`resolve_config`. Everything in this module exists to turn a platform's private vocabulary into that
one object.

⚠️ WHY THIS LIVES IN `app/backend/` AND NOT IN `fantasy_engine`. The API Lambda bundles neither
`quant_sports_intel_models` nor pandas/numpy (see `app/backend/models/fantasy.py`), so the backend
cannot import the engine — the shape is restated here in pure stdlib and kept honest MECHANICALLY by
`betting_ml/tests/test_nf_c0_platform_import.py`, which feeds every adapter's output through the
REAL `LeagueConfig.from_dict()` + `resolve_config()`. A drift between this module and the engine is
therefore a failing test, not a silent divergence.

🚨 THE HONESTY RULE FOR AN UNMAPPED SCORING TERM. A platform scores things our projection does not
produce (Sleeper pays for an IDP solo tackle; Yahoo for a 40+ yard TD bonus). The temptation is to
DROP those keys so the config "looks clean". That would be the exact failure NF-C0b's coverage
machinery was built to prevent: the term would vanish, the user would see a board that silently
ignored a rule their league really has, and nothing would say so. So an unmapped term is carried
through VERBATIM under its platform key. `resolve_scoring` then finds no projection column for it
and classifies it CAPTURED — stored faithfully, contributing nothing, and SAYING so. Fidelity is
preserved and the honest verdict is produced by code rather than by our judgement at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Mirrors `league_config.CONFIG_FORMAT_VERSION` — pinned by the parity test.
CONFIG_FORMAT_VERSION = "1.0"

# The canonical flex eligibilities the NFL presets use (`league_presets._FLEX_ELIG` /
# `_SUPERFLEX_ELIG`). A platform slot name maps onto one of these; the ACTUAL eligibility always
# travels in `RosterSlot.eligible`, never in the slot's name.
FLEX_ELIG = ("RB", "WR", "TE")
SUPERFLEX_ELIG = ("QB", "RB", "WR", "TE")
WR_TE_ELIG = ("WR", "TE")
RB_WR_ELIG = ("RB", "WR")
IDP_ELIG = ("DL", "LB", "DB")

# Positions our projection ranks. A slot eligible ONLY for positions outside this set (an IDP-only
# league) still imports — it simply produces no ranked players, which the coverage surface shows.
PROJECTED_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")


@dataclass(frozen=True)
class ImportedPlayer:
    """One rostered/drafted player as the PLATFORM names them.

    ⚠️ `player_key` is the platform's own id and is NOT joinable to our projection ids. Name+position
    is what a consumer matches on, so both are carried; a consumer that needs an exact join must do
    the matching itself and say what it could not match (there is no silent id coincidence to rely
    on — Sleeper's "12527" and our player key are unrelated namespaces).
    """

    player_key: str
    name: str
    position: str | None = None
    team: str | None = None
    starter: bool = False

    def to_dict(self) -> dict:
        return {
            "player_key": self.player_key,
            "name": self.name,
            "position": self.position,
            "team": self.team,
            "starter": self.starter,
        }


@dataclass(frozen=True)
class ImportedTeam:
    team_key: str
    name: str
    owner: str | None = None
    is_owner: bool = False
    players: tuple[ImportedPlayer, ...] = ()

    def to_dict(self) -> dict:
        return {
            "team_key": self.team_key,
            "name": self.name,
            "owner": self.owner,
            "is_owner": self.is_owner,
            "players": [p.to_dict() for p in self.players],
        }


@dataclass(frozen=True)
class DraftPick:
    pick_no: int
    round: int
    team_key: str | None
    player: ImportedPlayer | None

    def to_dict(self) -> dict:
        return {
            "pick_no": self.pick_no,
            "round": self.round,
            "team_key": self.team_key,
            "player": self.player.to_dict() if self.player else None,
        }


@dataclass(frozen=True)
class DraftState:
    """LIVE draft state — deliberately NEVER persisted.

    A stored snapshot of "who is already drafted" is wrong the moment the next pick lands, and a
    stale board that LOOKS live is worse than no board: the user would draft against it. So the
    settings (`LeagueConfig`) are the durable half of an import and this is fetched fresh on every
    read (`GET /fantasy/leagues/{id}/live`).
    """

    status: str | None = None
    type: str | None = None
    rounds: int | None = None
    start_time: str | None = None
    picks: tuple[DraftPick, ...] = ()
    supported: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "type": self.type,
            "rounds": self.rounds,
            "start_time": self.start_time,
            "picks": [p.to_dict() for p in self.picks],
            "pick_count": len(self.picks),
            "supported": self.supported,
            "note": self.note,
        }


@dataclass(frozen=True)
class ImportedLeague:
    """What an adapter returns: the shared config + the live, non-persisted state around it."""

    platform: str
    source_league_id: str
    season: str | None
    config: dict
    teams: tuple[ImportedTeam, ...] = ()
    draft: DraftState | None = None
    # Things the platform said that we could NOT faithfully represent, in plain language. Rendered
    # verbatim by the import UI — an import that quietly loses a rule is the failure mode this
    # whole module is shaped against.
    warnings: tuple[str, ...] = ()
    unmapped_scoring_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "source_league_id": self.source_league_id,
            "season": self.season,
            "config": self.config,
            "teams": [t.to_dict() for t in self.teams],
            "draft": self.draft.to_dict() if self.draft else None,
            "warnings": list(self.warnings),
            "unmapped_scoring_keys": list(self.unmapped_scoring_keys),
        }


# ── roster-shape normalization ────────────────────────────────────────────────────────────────────


def collapse_slots(sequence: list[tuple[str, tuple[str, ...], bool]]) -> list[dict]:
    """Collapse a platform's per-seat lineup listing into counted `RosterSlot` dicts.

    Sleeper (and Yahoo, once flattened) express a lineup as one entry PER SEAT — `["QB","RB","RB",
    "WR","WR","WR","TE","TE","FLEX","FLEX","FLEX","SUPER_FLEX","BN",…]`. The engine wants
    `{name, count, eligible, bench}`. Entries are keyed by NAME so a lineup that interleaves seats
    ("RB","WR","RB") still yields RB:2 / WR:1 rather than three fragmented slots, and FIRST-SEEN
    order is preserved so the saved roster reads in the platform's own order.
    """
    order: list[str] = []
    acc: dict[str, dict] = {}
    for name, eligible, bench in sequence:
        if name not in acc:
            order.append(name)
            acc[name] = {"name": name, "count": 0, "eligible": list(eligible), "bench": bench}
        acc[name]["count"] += 1
    return [acc[n] for n in order]


def derive_ppr_label(per_stat: dict[str, float]) -> str:
    """The human-readable format label. Descriptive ONLY — the per-reception value that actually
    scores is `per_stat["rec"]`, so a mislabel can never move a number (see `LeagueConfig.ppr`)."""
    rec = float(per_stat.get("rec", 0.0) or 0.0)
    if abs(rec) < 1e-9:
        return "standard"
    if abs(rec - 0.5) < 1e-9:
        return "half"
    if abs(rec - 1.0) < 1e-9:
        return "ppr"
    return "custom"


def detect_superflex(roster: list[dict]) -> bool:
    """True when a NON-BENCH slot can start a QB alongside other positions.

    Read off eligibility, never off the slot's NAME: leagues call it SUPERFLEX, OP, SFLEX, or just
    a second "FLEX" with QB added, and a name-based check silently misses the ones that matter.
    """
    for slot in roster:
        if slot.get("bench"):
            continue
        eligible = tuple(slot.get("eligible") or ())
        if "QB" in eligible and len(eligible) > 1:
            return True
    return False


def build_config(
    *,
    name: str,
    n_teams: int,
    per_stat: dict[str, float],
    roster: list[dict],
    position_bonuses: dict[str, dict[str, float]] | None = None,
    captured_rules: dict[str, object] | None = None,
    description: str = "",
    sport: str = "nfl",
) -> dict:
    """Assemble the `LeagueConfig.to_dict()` payload. Key order and types mirror the engine exactly
    (pinned by the parity test), so this dict round-trips through `LeagueConfig.from_dict`."""
    scoring = {
        "per_stat": {str(k): float(v) for k, v in per_stat.items()},
        "position_bonuses": {
            str(pos): {str(k): float(v) for k, v in bonus.items()}
            for pos, bonus in (position_bonuses or {}).items()
            if bonus
        },
    }
    return {
        "format_version": CONFIG_FORMAT_VERSION,
        "name": name,
        "sport": sport,
        "n_teams": int(n_teams),
        "ppr": derive_ppr_label(scoring["per_stat"]),
        "superflex": detect_superflex(roster),
        "description": description,
        "scoring": scoring,
        "roster": [
            {
                "name": str(s["name"]),
                "count": int(s["count"]),
                "eligible": [str(e) for e in (s.get("eligible") or ())],
                "bench": bool(s.get("bench", False)),
            }
            for s in roster
        ],
        "captured_rules": dict(captured_rules or {}),
    }


def config_is_rankable(config: dict) -> bool:
    """Mirror of `LeagueConfig.validate()`'s binding condition: at least one STARTING slot exists.

    Without one, value-over-replacement has nothing to rank against. Checked at IMPORT time so a
    best-ball / all-bench league fails with an explanation instead of being stored and then
    producing an empty board later.
    """
    if int(config.get("n_teams", 0)) <= 0:
        return False
    if not (config.get("scoring") or {}).get("per_stat"):
        return False
    return any(
        (not s.get("bench")) and int(s.get("count", 0)) > 0 for s in config.get("roster") or []
    )


@dataclass
class ScoringTranslation:
    """The result of mapping one platform's scoring vocabulary onto the canonical keys."""

    per_stat: dict[str, float] = field(default_factory=dict)
    position_bonuses: dict[str, dict[str, float]] = field(default_factory=dict)
    unmapped: list[str] = field(default_factory=list)


def apply_scoring_map(
    raw: dict[str, object],
    key_map: dict[str, tuple[str, ...]],
    *,
    bonus_map: dict[str, tuple[str, str]] | None = None,
    ignore: frozenset[str] = frozenset(),
) -> ScoringTranslation:
    """Translate a platform's `{platform_key: weight}` into canonical keys.

    * `key_map` — platform key → the canonical key(s) it sets. A TUPLE because a platform bucket is
      sometimes COARSER than ours: Sleeper's single `pts_allow_14_20` covers our `dst_pa_g_14_17`
      AND `dst_pa_g_18_20`. Writing the same weight to both is an EXACT restatement of the league's
      rule, not an approximation — the nine canonical buckets were chosen as the common refinement
      of the ESPN and Yahoo tables precisely so this fan-out is lossless (see `SCORING_CATALOG`'s
      `merge_group`). It is the mirror image of the FG case, where the league is FINER than the
      projection and `resolve_scoring` folds with an explicit `exact` flag.
    * `bonus_map` — platform key → `(position, canonical_stat)`, for per-position premiums that
      belong in `position_bonuses` rather than `per_stat` (Sleeper's `bonus_rec_te` is TE-premium
      PPR, and folding it into the flat `rec` weight would over-pay every RB and WR in the league).
    * `ignore` — platform keys that are genuinely NOT scoring rules and would be noise in the
      coverage report.

    Anything else is passed through under its ORIGINAL key and listed in `unmapped`, so it is stored
    faithfully and reported CAPTURED rather than silently dropped (see the module docstring).
    """
    out = ScoringTranslation()
    for key, value in sorted(raw.items()):
        key = str(key)
        if key in ignore:
            continue
        try:
            weight = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if bonus_map and key in bonus_map:
            position, stat = bonus_map[key]
            out.position_bonuses.setdefault(position, {})[stat] = weight
            continue
        targets = key_map.get(key)
        if targets:
            for canonical in targets:
                out.per_stat[canonical] = weight
            continue
        out.per_stat[key] = weight
        if abs(weight) > 1e-12:
            # Only a NON-ZERO unmapped term is worth telling the user about — a platform ships its
            # whole scoring table with the unused rules set to 0, and reporting those as "captured"
            # would bury the handful that genuinely matter under dozens of non-statements.
            out.unmapped.append(key)
    return out


__all__ = [
    "CONFIG_FORMAT_VERSION",
    "FLEX_ELIG",
    "IDP_ELIG",
    "PROJECTED_POSITIONS",
    "RB_WR_ELIG",
    "SUPERFLEX_ELIG",
    "WR_TE_ELIG",
    "DraftPick",
    "DraftState",
    "ImportedLeague",
    "ImportedPlayer",
    "ImportedTeam",
    "ScoringTranslation",
    "apply_scoring_map",
    "build_config",
    "collapse_slots",
    "config_is_rankable",
    "derive_ppr_label",
    "detect_superflex",
]
