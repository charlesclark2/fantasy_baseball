"""nfl_ros.py — NF-ROS1b node 4: the served REST-OF-SEASON value contract, born contracted.

`s3://<api-cache>/fantasy/nfl/ros/<season>/<through_week>/{manifest,players}.json` plus
`fantasy/nfl/ros/<season>/current.json`. Registered in
`quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_ros1b_preregistration.md` §9
(which inherits NF-ROS1 §8) and amendment 1.

⭐ BORN CONTRACTED (the NF-INC-0917B pattern). The builder writes `model_validate(...).model_dump()`
— never the input dict — and refuses to put any blob that `missing_declared_fields` finds short of
this contract, dry-run included; the publisher then reads the bytes back and compares their sha256.
`missing_declared_fields` is IMPORTED from `nfl_weekly`, not re-implemented: one owner of the
question "is the contract on the wire".

⭐ ONLY CERTIFIED POSITIONS CARRY NUMBERS. Every other row is a stated absence, and the four
absences are distinguishable by construction (a Literal, not free text):

  * `not_certified` — an evaluated position whose ROS value did not clear the registered bar;
  * `position_not_evaluated` — D/ST (team grain; no player-level realized line exists);
  * `no_preseason_prior` — an in-season addition. It has no row (there is no prior to update);
    the manifest counts them and their share of realized points instead;
  * `join_unresolved` — a certified-position player whose identity join could not be verified to
    have found his realized line (PM amendment 1: a MISSED name-rung match is served as this,
    never as a prior-only number that silently ignores the games he played).

⛔ NO CROSS-POSITION COMPARISON FIELD (PM R4). A certified value exists for some positions only, so
a global rank or a cross-position percentile would invite exactly the comparison the artifact
cannot support. The shape cannot express it: there is no rank, tier or percentile anywhere here,
and a guard pins that. The manifest states it in words as well.

⚠️ PAID SUBSTRATE. The ROS stat line is one optional field per `STAT_FIELD` payload name, DERIVED
from `STAT_FIELD` (never a hand list), so `projection_fields.PAID_PLAYER_FIELDS` classifies it the
way it classifies the season board's stat line — adding a scorable stat makes it paid here too
(NF-EPIC1). The three per-scoring values (`rosPts`/`rosP10`/`rosP90`) follow the same policy the
season board applies: the PPR triple is FREE (the number never without its band), Std and Half are
PAID (PM ack, 2026-09-18). That ruling is expressed in `projection_fields` as a rule over presets
rather than six more names — the hand list is what let them ship free in the first place. No route
serves this artifact yet; entitlement is the consumer stories' job.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, create_model

from app.backend.models.nfl_weekly import declared_field_names, missing_declared_fields  # noqa: F401
from app.backend.services.projection_fields import SCORING_SUFFIX, STAT_FIELD

STORY = "NF-ROS1b"
ARTIFACT_VERSION = "nfl_ros_value_v1"
INTERVAL_FAMILY = "hurdle"
INTERVAL_LO_LEVEL = 0.10
INTERVAL_HI_LEVEL = 0.90

ROS_ABSENCES = ("not_certified", "position_not_evaluated", "no_preseason_prior", "join_unresolved")
RosAbsence = Literal["not_certified", "position_not_evaluated", "no_preseason_prior",
                     "join_unresolved"]
WAIVER_ABSENCE = "waiver_value_not_certified"

COMPARISON_NOTE = ("A rest-of-season value is published only for the certified positions listed "
                   "here. It is not a cross-position ranking input: an uncertified position "
                   "carries no number, so comparing values across positions would compare a value "
                   "with an absence.")
#: ⭐ THE UPPER EDGE IS A TAIL, NOT A CEILING (NF-ROS1b §13 finding ⑪; PM ack 2026-09-18 ordered it
#: carried on the artifact itself, not only in the record). Served so a display consumer cannot
#: render the number without the caveat that belongs to it.
UPPER_TAIL_NOTE = (
    "The upper edge of the 80% range can exceed any full-season pace on record. On the decisive "
    "run 9 of 197 certified RB rows carried a P90 above the largest realized per-game pace we have "
    "observed, scaled to that player's games remaining (the widest: 664 against 482); no point "
    "estimate does. That is the registered interval's top ratio cell spreading upward — RB "
    "over-covers, 0.859 against a nominal 0.80 — and it is deliberately NOT clamped, because "
    "clamping would change the interval family the certification was earned under. Render the "
    "upper edge as a tail, never as a ceiling or a target."
)
HONEST_FRAMING = ("best_alpha = 0. This is a projection with a measured 80% range, not a pick, an "
                  "edge or a promise. The range reads flat on held-out seasons (randomized-PIT "
                  "max-decile deviation within 0.05) for the certified positions only.")

#: The three scorings every value is published in, and the field suffix each one uses. ⭐ IMPORTED,
#: not restated: `projection_fields` owns the suffix spelling because it PRICES by it
#: (`SCORED_FIELD_STEMS × PAID_SCORING_PRESETS`), so a second copy here could silently name a field
#: the pricing rule does not reach — which is the hand-list defect the PM's 2026-09-18 ack closed.
PRESET_SUFFIX = SCORING_SUFFIX

#: The stat-line field names — every `STAT_FIELD` payload name, in `STAT_FIELD` order.
STAT_LINE_FIELDS: tuple[str, ...] = tuple(dict.fromkeys(STAT_FIELD.values()))


# ── the key scheme ───────────────────────────────────────────────────────────────────────────────
def ros_prefix(season: int) -> str:
    return f"ros/{int(season)}"


def ros_manifest_key(season: int, week: int) -> str:
    """Relative key (under `fantasy/nfl/`) of one through-week's manifest."""
    return f"{ros_prefix(season)}/{int(week)}/manifest.json"


def ros_players_key(season: int, week: int) -> str:
    return f"{ros_prefix(season)}/{int(week)}/players.json"


def ros_current_key(season: int) -> str:
    return f"{ros_prefix(season)}/current.json"


# ── the models ───────────────────────────────────────────────────────────────────────────────────
class _RosPlayerBase(BaseModel):
    """One board player. Numbers are present only when `certified`; otherwise `absence` says why."""

    id: str = Field(description="the served board's player id (gsis, or the board's synthetic id)")
    name: str
    pos: str
    team: Optional[str] = None
    certified: bool
    absence: Optional[RosAbsence] = None

    gamesPlayed: Optional[int] = None
    teamGamesPlayed: Optional[int] = None
    teamGamesRemaining: Optional[int] = None
    expGamesRemaining: Optional[float] = None
    priorRate: Optional[float] = Field(default=None, description="prior full-PPR points per game")
    realizedRate: Optional[float] = Field(default=None,
                                          description="realized full-PPR points per game; null "
                                                      "before his first game")
    rateWeight: Optional[float] = Field(default=None,
                                        description="share of the rate carried by realized games")
    availWeight: Optional[float] = Field(default=None,
                                         description="share of availability carried by realized "
                                                     "team games")

    rosPtsStd: Optional[float] = None
    rosP10Std: Optional[float] = None
    rosP90Std: Optional[float] = None
    rosPtsHalf: Optional[float] = None
    rosP10Half: Optional[float] = None
    rosP90Half: Optional[float] = None
    rosPtsPpr: Optional[float] = None
    rosP10Ppr: Optional[float] = None
    rosP90Ppr: Optional[float] = None

    waiverValue: Optional[float] = None
    waiverAbsence: Optional[Literal["waiver_value_not_certified"]] = None


#: Derived, never hand-listed: one optional float per STAT_FIELD payload name.
NflRosPlayer = create_model(
    "NflRosPlayer",
    __base__=_RosPlayerBase,
    **{f: (Optional[float], None) for f in STAT_LINE_FIELDS},
)


class NflRosCertification(BaseModel):
    """One position's row of the decisive run's certification table, verbatim."""

    pos: str
    certified: bool
    failed_clauses: list[str]
    mean_lift: float
    folds_won: int
    pit_max_decile_dev: float
    coverage80: float
    coverage_floor: float
    reported_state: Optional[str] = None


class NflRosPositionParams(BaseModel):
    pos: str
    m_rate: Optional[float] = Field(description="prior strength on the rate, in games (null = ∞)")
    m_avail: Optional[float] = Field(description="prior strength on availability (null = ∞)")


class NflRosAbsenceCount(BaseModel):
    reason: RosAbsence
    n: int


class NflRosManifest(BaseModel):
    season: int
    throughWeek: int
    generated_at: str
    story: str = STORY
    artifact_version: str = ARTIFACT_VERSION
    best_alpha: float = 0.0
    framing: str = HONEST_FRAMING
    comparison_note: str = COMPARISON_NOTE
    upper_tail_note: str = UPPER_TAIL_NOTE
    certified_positions: list[str]
    certified_weeks: list[int] = Field(description="[first, last] through-week the value was "
                                                   "certified over")
    certified_for_this_week: bool
    form: str = "eb_rate_avail"
    interval_family: str = INTERVAL_FAMILY
    interval_lo_level: float = INTERVAL_LO_LEVEL
    interval_hi_level: float = INTERVAL_HI_LEVEL
    params: list[NflRosPositionParams]
    certification: list[NflRosCertification]
    decisive_commit: str
    params_sha256: str
    prior_generated_at: Optional[str] = None
    prior_model_version: Optional[str] = None
    stats_player_week_version: int
    schedules_version: int
    scoring_terms: dict[str, list[str]]
    n_players: int
    absence_counts: list[NflRosAbsenceCount]
    no_preseason_prior_players: int
    no_preseason_prior_realized_share: Optional[float] = None
    join_unresolved_names: list[str]
    rookie_stratum_note: Optional[str] = None
    players_sha256: str


class NflRosPayload(BaseModel):
    season: int
    throughWeek: int
    generated_at: str
    players: list[NflRosPlayer]  # type: ignore[valid-type]


class NflRosCurrent(BaseModel):
    season: int
    throughWeek: int
    generated_at: str
    manifest_key: str
    players_key: str


CONTRACT_MODELS = (NflRosManifest, NflRosPayload, NflRosCurrent)

#: R4 — tokens a field name must never carry.
FORBIDDEN_FIELD_TOKENS = ("rank", "tier", "percentile", "pctile")


def contract_field_names() -> list[str]:
    names = []
    for m in (NflRosManifest, NflRosPayload, NflRosCurrent, NflRosPlayer, NflRosCertification,
              NflRosPositionParams, NflRosAbsenceCount):
        names += list(m.model_fields)
    return names
