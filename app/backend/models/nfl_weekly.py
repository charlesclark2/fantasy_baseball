"""nfl_weekly.py — NF-C6-PH2: the SERVED payload contract for the NFL WEEKLY projection.

THIS MODULE IS THE CONTRACT, AND IT HAS EXACTLY ONE OWNER
---------------------------------------------------------
Every field the weekly surfaces ever see is declared here, once. Both ends of the pipe read this
module and nothing else — the same shape `app/backend/models/ncaaf.py` established:

  * the BOX BUILDER (`quant_sports_intel_models/football/nfl/fantasy/weekly_serving.py`) builds its
    blobs against these models and REFUSES to write a payload that does not validate, so a field the
    app expects can never be silently absent from the store;
  * the API ROUTER (`app/backend/routers/fantasy.py`) reduces and returns against these models, so a
    field the store carries can never be silently DROPPED on serialize (E9.41: `FeaturedYesterday`
    never declared `status`, Pydantic stripped it, and the Won/Lost colour was broken for every
    settled pick with the data correct in the store the whole time).

⛔ WHY THIS FILE IMPORTS NOTHING FROM `quant_sports_intel_models`
----------------------------------------------------------------
The API Lambda ships a hand-curated copy list (`infrastructure/lambda/deploy.sh` §3b-3d) and
`test_nf_c_lda_1_lambda_import_weight.py` FAILS the build if the backend imports a
`quant_sports_intel_models` module that list does not carry. A contract shared with a box writer
must therefore live on the backend side and be imported *by* the box, never the reverse. The box
image is a `COPY . .` of the repo, so `app.backend.models.nfl_weekly` is present there; this module
is pydantic + stdlib only, so importing it costs the box nothing.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ THE ENTITLEMENT SIDE OF EVERY ROUTE, DECIDED HERE — BEFORE ANY OF THEM WAS WRITTEN
═══════════════════════════════════════════════════════════════════════════════════════════════════
The PM ruling for this story is MIRROR THE SEASON FREEMIUM EXACTLY, and the mirror is literal: the
weekly split is the season split with `projections`/`projections-full` re-keyed on a week.

  ROUTE                                     SIDE   CAPABILITY          BYTE-IDENTITY
  /fantasy/nfl/weekly/manifest              FREE   GENERIC_BOARD       YES — no `Request` param
  /fantasy/nfl/weekly/projections           FREE   GENERIC_BOARD       YES — no `Request` param
  /fantasy/nfl/weekly/projections-full      PAID   DECISION_SUPPORT    n/a (gated, `Authorization`)

⭐ NO NEW CAPABILITY IS INTRODUCED, and that is deliberate. `Capability.DECISION_SUPPORT` already
names "the draft optimizer, and the weekly surfaces as they land" in its own docstring, so the paid
weekly half lands on a capability the pricing page already sells and
`test_every_capability_is_placed_on_exactly_one_side` does not move. A new capability would have
been a pricing change wearing a refactor's clothes.

⭐⭐ THE BYTE-IDENTITY INVARIANT THREE OTHER SYSTEMS REST ON. The two FREE routes take no `Request`
and read no entitlement: a handler that cannot see its caller cannot branch on them. That is what
makes (a) the CDN entry legal (one edge copy for everybody), (b) `cache_control_for`'s "same URL,
two bodies" hazard not arise, and (c) the frontend's `entitled`-keyed query cache unable to strand a
new subscriber on a stale view. ⛔ The PAID route must never join the CDN allowlist
(`frontend/app/api/public/[...path]/route.ts`) or `cost_guardrails._PUBLIC_CACHE_RULES`.

⚠️ GATEWAY. A route is only reachable anonymously once its API Gateway authorizer is set to NONE —
per-route console config, outside this repo's IaC (NF3.2) — so a route that is public in code still
401s before Lambda until the operator flips it. The paid route keeps whatever the gateway default
is; its gate is `require_fantasy_access` INSIDE the Lambda, exactly like `/nfl/projections-full`.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE PAID SET IS DERIVED FROM THE SCORER'S OWN `STAT_FIELD` MAP — NEVER LISTED BY HAND
───────────────────────────────────────────────────────────────────────────────────────────────────
`PAID_WEEKLY_PLAYER_FIELDS` is derived from `projection_fields.STAT_FIELD` for the same reason the
season's is (NF-EPIC 1): a hand-written list is a DENYLIST, so the next component the champion's
head emits would be PUBLIC BY DEFAULT and leak on the next publish with no code change, no error and
no failing test. Deriving it means a new SCORABLE stat is paid the moment someone teaches the scorer
about it. `WEEKLY_COMPONENT_STAT_KEY` maps each champion component onto its `STAT_FIELD` key and
RAISES AT IMPORT if one has no entry — so a component can never be served under a name the paywall
does not know about.

⚠️ ARITHMETIC LEAK CHECK (the freemium `half = full − 0.5·rec` lesson). The free set is
identity + `fpPpr` + the 80% band + the ROS triple. `fpHalf`/`fpStd` are NOT served weekly at all,
and `rec` is paid, so neither is recoverable. The 39-level vector `q` is paid and the free band is
2 of its 39 levels — strictly less, never a reconstruction. `paid_weekly_fields_present()` is the
audit instrument that answers "is any paid value recoverable from this payload" mechanically.

───────────────────────────────────────────────────────────────────────────────────────────────────
📣 THE CLAIMS CONSTRAINT IS A SCHEMA PROPERTY (NF-W1's record, enforced not narrated)
───────────────────────────────────────────────────────────────────────────────────────────────────
NF-W1 measured the weekly edge as USAGE / SNAP conditioning: `foil_matchup` — the "season ÷ games,
spread by a matchup adjustment" degenerate — LOST at ALL FOUR positions (QB 3.7820 vs the champion's
2.5882; RB 3.0974 vs 2.5046; WR 3.1806 vs 2.6726; TE 2.2299 vs 1.8197), and it lost to the FLAT foil
too. So "matchup-based" is a claim the evidence contradicts, and `assert_no_matchup_claim` REFUSES
it in any served field name or description. `assert_no_edge_claim_in_schema` refuses the pick/edge
family beside it (`best_alpha = 0` — this is a projection product and no stake rides on it).

⚠️ THE SCAN IS SCOPED TO SERVED NAMES AND DESCRIPTIONS, never to source files, and that scoping is
load-bearing rather than lazy: the champion legitimately CONSUMES an `opponent_matchup__*` feature
family, so a source-wide grep would fire on the model's own internals — the NF-W7 `'temp' ⊂
'attempt'` over-eager-guard shape. Consuming an opponent feature is not claiming the edge comes from
it. `assert_no_matchup_claim` is exported for the weekly FRONTEND story to point at its copy.

───────────────────────────────────────────────────────────────────────────────────────────────────
⚖️ ABSENT vs NULL vs ZERO — THREE DIFFERENT FACTS, DELIBERATELY DISTINGUISHABLE
───────────────────────────────────────────────────────────────────────────────────────────────────
An empty state that means three things costs an investigation every time it recurs (NF-C6b/NF-K1:
the D/ST "not matched" symptom was investigated twice because a join bug and an absent position
rendered identically). So:

  * ABSENT → the player has no row in `players` at all, and `manifest.absences` carries a COUNT per
    machine-readable `reason`. Nothing is fabricated. K and D/ST are absent BY DESIGN: NF-W1's
    champion covers QB/RB/WR/TE only and was never fitted on them.
  * ZERO   → `status = "bye"`, `fpPpr = fpP10 = fpP90 = 0.0`. This is NOT a missing projection: a
    bye is a DETERMINISTIC zero knowable at schedule release, and NF-W1's pre-registration says
    serving emits it as the identity 0 exactly (which is also why byes are excluded from its
    scoring — identical free zeros discriminate nothing).
  * NULL   → the field is DECLARED, PRESENT in the JSON and `null`, with a reason beside it. `ros*`
    is null in the season's final week: there is no remaining horizon to sum, which is a different
    fact from a ROS of zero.

Consequently NOTHING here is serialised with `exclude_none` — a declared field is always on the wire.

───────────────────────────────────────────────────────────────────────────────────────────────────
🔑 THE KEY SCHEME
───────────────────────────────────────────────────────────────────────────────────────────────────
    fantasy/nfl/weekly/<season>/<week>/manifest.json     one week's provenance + counts + absences
    fantasy/nfl/weekly/<season>/<week>/players.json      one week's payload (paid superset)
    fantasy/nfl/weekly/<season>/current.json             a POINTER to the newest built week

Same bucket and prefix family as the season board, so the existing `CACHE_BUCKET` grant already
covers it — no new IAM grant, so no E8.5-class silently-denied first write.

⭐ `current.json` IS A FULL OVERWRITE, NEVER A READ-MODIFY-WRITE. A build that had to read an index,
append itself and write it back would be a lost-update race the moment two builds overlap, and it
would fail OPEN (an unreadable index silently becomes a one-entry index). Overwriting a pointer that
describes exactly one week cannot lose anything it did not itself write.

⚠️ (season, week) IS A SAFE KEY FOR THE NFL, unlike NCAAF. CFBD restarts `week` at 1 for the
postseason, so NCAAF-P3.1 had to key on a kickoff DATE; the NFL feed continues the numbering
(2025 REG ran weeks 1–18 and POST 19–22 in the same column), so a REG week number cannot collide.
`SEASON_TYPE` pins the REG scope the champion was fitted on, and the builder filters on it.
"""

from __future__ import annotations

from typing import Literal, get_args, get_origin

from pydantic import BaseModel, Field

from app.backend.services.projection_fields import STAT_FIELD

# ── what the champion is, restated as constants the payload stamps ───────────────────────────────

#: NF-W1's scoring system. The weekly point is PPR-NATIVE — it is the model's own output, not a
#: re-scoring of a stat line — which is why no `config`/`size` parameter exists on these routes.
#: Serving one would imply other presets sit behind the paywall; in fact they do not exist at all
#: yet, because re-scoring an arbitrary league needs the per-stat line and a scorer, which is the
#: DEFERRED gate-3 story. A parameter that does nothing today is declaration outrunning production.
SCORING_SYSTEM_ID = "ppr"

#: The season phase the champion was fitted on (`weekly_projection.load_sources_w1` filters REG).
SEASON_TYPE = "REG"

#: The positions the champion covers. Everything else is an honest ABSENCE, never a fabricated row.
PROJECTED_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

#: The certified 80% band's levels (`weekly_projection.INTERVAL_LO/HI`). SERVED rather than assumed:
#: a later ladder change is then additive on the client instead of silently relabelling a range it
#: did not recompute (the NCAAF-P3.3 lesson).
INTERVAL_LO_LEVEL: float = 0.10
INTERVAL_HI_LEVEL: float = 0.90

#: The two levels the ROS σ is read at. `weekly_projection.ros_projection` computes
#: σ = (q84 − q16)/2, which is exactly σ for a Normal — so the builder must supply the band at
#: 0.16/0.84 and NOT the nearest 39-level grid points (0.15/0.85 would give 1.036σ, a 3.6%
#: over-estimate baked into every ROS interval). The builder interpolates the quantile function at
#: these exact levels, which is the sanctioned operation on a quantile vector.
ROS_SIGMA_LO_LEVEL: float = 0.16
ROS_SIGMA_HI_LEVEL: float = 0.84

#: Verbatim from `weekly_projection.ros_projection`'s own docstring. Carried on the wire so a
#: consumer cannot present the ROS band as anything more than it is.
ROS_INTERVAL_NOTE = (
    "Rest-of-season interval is a DECLARED independence approximation "
    "(sigma_ros = sqrt(sum of weekly sigma^2)), honest for ranking-scale use; week-to-week "
    "dependence such as injury persistence makes the true tails wider."
)

#: How the remaining-week rows behind `ros*` are built, named on the wire so it is never inferred.
#:
#: ⭐ "frozen_form" is a real constraint, not a shortcut. Every champion feature is LAGGED, so a
#: week-5 feature row needs week-4's realized outcome — which does not exist for any week after the
#: target. Re-running the feature engineering across the horizon would read the target week's
#: PLACEHOLDER zero as a realized outcome and compound it forward, collapsing every remaining week
#: toward the nihilist. So the builder COPIES the target week's feature row per player and overrides
#: only the schedule-derived game context (opponent, home, rest, week index, bye), which is provably
#: free of that compounding and is what `weekly_serving.assert_frozen_form` pins.
ROS_BASIS = "frozen_form"

#: The champion's component head, mapped onto the SCORER's own stat keys.
#:
#: ⚠️ THE MAP IS SEMANTIC AND MUST BE READ, NOT PATTERN-MATCHED: the champion calls a pass attempt
#: `attempts` and a rush attempt `carries`, while the scorer calls them `pass_att` / `rush_att`. A
#: name-similarity join would silently mis-map both — the NF-C0e wrong-key class, whose whole harm
#: is that unrecognized keys pass through as "captured" with no error.
WEEKLY_COMPONENT_STAT_KEY: dict[str, str] = {
    "attempts": "pass_att",
    "passing_yards": "pass_yds",
    "passing_tds": "pass_td",
    "passing_interceptions": "pass_int",
    "carries": "rush_att",
    "rushing_yards": "rush_yds",
    "rushing_tds": "rush_td",
    "targets": "targets",
    "receptions": "rec",
    "receiving_yards": "rec_yds",
    "receiving_tds": "rec_td",
}

def resolve_component_fields(stat_field: dict[str, str],
                             component_stat_key: dict[str, str] | None = None) -> dict[str, str]:
    """component name → the payload field it is served under, RESOLVED THROUGH `STAT_FIELD`.

    RAISES on a component whose stat key the scorer does not know about. A pure function rather
    than inline module code so the refusal itself is directly testable: a guard that can only be
    exercised by reloading a module is a guard nobody drives, and it would leave the one branch
    that keeps the paid set safe untested (the NF1.7(a) family).
    """
    keys = component_stat_key if component_stat_key is not None else WEEKLY_COMPONENT_STAT_KEY
    unmapped = sorted(k for k in keys.values() if k not in stat_field)
    if unmapped:
        raise ValueError(
            f"weekly components map onto stat key(s) {unmapped} that are absent from "
            "projection_fields.STAT_FIELD. The paid set is DERIVED from that map — an unmapped "
            "component would be served PUBLIC by default (the NF-EPIC 1 denylist hazard). Add the "
            "key to STAT_FIELD (and its two mirrors) or drop the component."
        )
    return {comp: stat_field[key] for comp, key in keys.items()}


#: Resolved at IMPORT, because both the router and the builder import this module: a component the
#: paywall does not know about must not be servable on a day CI was skipped.
WEEKLY_COMPONENT_FIELD: dict[str, str] = resolve_component_fields(STAT_FIELD)

#: The 39-level predictive vector. Paid: the free band is 2 of its levels, so it is strictly more.
QUANTILE_VECTOR_FIELD = "q"

#: ⭐ THE PAID SET, DERIVED. Never edit this literal — edit `WEEKLY_COMPONENT_STAT_KEY`.
PAID_WEEKLY_PLAYER_FIELDS: frozenset[str] = (
    frozenset(WEEKLY_COMPONENT_FIELD.values()) | {QUANTILE_VECTOR_FIELD}
)

#: Machine-readable absence reasons. A reader must be able to tell "we do not project this position"
#: from "we could not resolve this player" from "the point-in-time gate refused this week's row"
#: without an investigation (NF-C6b).
ABSENCE_REASONS: tuple[str, ...] = (
    "position_not_projected",     # K / DST / OL / DEF — NF-W1 covers QB/RB/WR/TE only
    "no_gameday_roster_row",      # not on a game-day roster for this week
    "pit_gate_dropped",           # the week's row failed `assert_point_in_time` fail-closed
)

#: Token families refused in any served field name or description.
FORBIDDEN_PAYLOAD_TOKENS: tuple[str, ...] = (
    "edge", "pick", "bet", "wager", "win_rate", "roi", "clv", "recommend", "kelly", "alpha",
    "value_side", "best_side",
)
FORBIDDEN_TOKEN_EXEMPT_FIELDS: frozenset[str] = frozenset({"best_alpha"})

#: The claim NF-W1's own field measured as FALSE. Two spellings because a hyphen and a space are the
#: two ways the phrase is actually written; `matchup` alone is NOT banned, because the model does
#: legitimately consume an opponent feature and banning the bare word would refuse an honest
#: description of an input while permitting the claim itself in any other phrasing.
FORBIDDEN_CLAIM_PHRASES: tuple[str, ...] = (
    "matchup-based", "matchup based", "matchup-driven", "matchup driven",
    "based on matchup", "beats the matchup",
)


# ── the key scheme ───────────────────────────────────────────────────────────────────────────────

def weekly_prefix(season: int) -> str:
    return f"weekly/{int(season)}"


def weekly_manifest_key(season: int, week: int) -> str:
    """Relative key (under `fantasy/nfl/`) of one week's manifest."""
    return f"{weekly_prefix(season)}/{int(week)}/manifest.json"


def weekly_players_key(season: int, week: int) -> str:
    """Relative key (under `fantasy/nfl/`) of one week's player payload."""
    return f"{weekly_prefix(season)}/{int(week)}/players.json"


def weekly_current_key(season: int) -> str:
    """Relative key of the pointer naming the newest built week for a season."""
    return f"{weekly_prefix(season)}/current.json"


# ── the models ───────────────────────────────────────────────────────────────────────────────────

class NflWeeklyPlayer(BaseModel):
    """One player-week. The PAID fields are declared here too — this model describes the stored
    superset; `public_weekly_player_row` is what a free caller receives."""

    # identity — public facts about the player
    id: str = Field(description="nflverse gsis_id")
    name: str
    pos: Literal["QB", "RB", "WR", "TE"]
    team: str
    opp: str | None = Field(default=None, description="opponent team code; null on a bye")
    home: bool | None = Field(default=None, description="null on a bye")

    #: "projected" (a real predictive) or "bye" (the deterministic identity zero). NEVER a third
    #: value meaning "missing" — a missing player is ABSENT from `players` and counted in the
    #: manifest instead.
    status: Literal["projected", "bye"]

    # the free wedge — our number and its honest 80% band
    fpPpr: float
    fpP10: float
    fpP90: float

    # rest-of-season, summed over the remaining weeks on the frozen-form basis
    rosPpr: float | None = Field(default=None, description="null in the season's final week")
    rosP10: float | None = None
    rosP90: float | None = None
    rosWeeks: int = Field(description="remaining weeks summed, byes included as identity zeros")

    #: How many prior modeled weeks stand behind this row's lagged features. Served because a
    #: week-1 rookie is projected from position and rookie-flag alone, and a reader deserves to see
    #: the evidence base rather than infer it. Not a model value; free.
    histWeeks: int

    # ── PAID ──
    q: list[float] | None = Field(
        default=None,
        description="the 39-level predictive quantile vector; absent for a non-entitled caller",
    )
    passAtt: float | None = None
    passYds: float | None = None
    passTd: float | None = None
    passInt: float | None = None
    rushAtt: float | None = None
    rushYds: float | None = None
    rushTd: float | None = None
    tgt: float | None = None
    rec: float | None = None
    recYds: float | None = None
    recTd: float | None = None


class NflWeeklyAbsence(BaseModel):
    """A COUNT of players not projected, by machine-readable reason. Counts rather than rosters:
    the reason is the actionable fact, and a per-player list of everyone we do not project would be
    a second, unmaintained roster."""

    reason: str
    n: int
    detail: str


class NflWeeklyInputVintage(BaseModel):
    """When each input was READ — provenance, never a value. Free on both sides for the same reason
    the season's is: one build date rendered over inputs of several vintages hides staleness
    (NF-FRESH2), and withholding the vintage from a free caller would leave that defect in place for
    half the audience."""

    rosters_as_of: str | None = None
    schedule_as_of: str | None = None
    stats_as_of: str | None = None
    snaps_as_of: str | None = None
    #: Newest (season, week) whose realized outcomes entered TRAINING. Must be strictly before the
    #: target week — `weekly_serving` refuses to write otherwise, which is the no-current-week-
    #: outcome invariant stated as a number rather than as a promise.
    train_through_season: int | None = None
    train_through_week: int | None = None


class NflWeeklyLineage(BaseModel):
    """The composite lineage this payload was produced by, stamped so the NF-G0
    `model_stamp_consistency` gate has something to reconcile the registry against. The registry is
    the AUTHORITY; a disagreement is a GATE FAILURE, never an adoption of the artifact's value."""

    model_family: str = "nfl_fantasy"
    target: str = "weekly_projection"
    served_version: str
    base_model_version: str
    point_model_version: str
    interval_model_version: str
    #: The component head is the champion's own advisory raw line, and it is NOT independently
    #: gated (`weekly_projection.fit_component_head`: "advisory raw lines beside the gated points
    #: distribution, never themselves gated in this slice"). Stamped so the claim cannot drift into
    #: "certified" by omission. The certified per-stat DISTRIBUTIONS (NF-W6c/W6d) remain staged
    #: CHALLENGERS with no consumer and are NOT served here.
    component_head_status: Literal["advisory_ungated"] = "advisory_ungated"
    scoring_contract_version: str | None = None


class NflWeeklyHonestFraming(BaseModel):
    """The posture, on the wire. `best_alpha` NAMES the absence of a claim — it is the one exemption
    from the forbidden-token scan."""

    best_alpha: float = 0.0
    interval_note: str = (
        "The 80% range is a measured COVERAGE FLOOR, not a promise: held-out coverage was "
        "0.817 (QB) / 0.849 (RB) / 0.852 (WR) / 0.883 (TE) against a 0.80 floor."
    )
    ros_interval_note: str = ROS_INTERVAL_NOTE


class NflWeeklyManifest(BaseModel):
    """One week's provenance, counts and absences. Free — nothing here is a per-player value."""

    season: int
    week: int
    season_type: Literal["REG"] = SEASON_TYPE
    scoring_system_id: Literal["ppr"] = SCORING_SYSTEM_ID
    generated_at: str
    #: The kickoff instant the projection is AS OF — the target week's first game.
    projection_day: str
    interval_lo_level: float = INTERVAL_LO_LEVEL
    interval_hi_level: float = INTERVAL_HI_LEVEL
    ros_basis: Literal["frozen_form"] = ROS_BASIS
    ros_sigma_lo_level: float = ROS_SIGMA_LO_LEVEL
    ros_sigma_hi_level: float = ROS_SIGMA_HI_LEVEL
    positions: list[str] = Field(default_factory=lambda: list(PROJECTED_POSITIONS))
    n_players: int
    n_by_position: dict[str, int]
    n_bye: int
    #: How many served players are ROOKIES (no prior NFL season in the frame). Stamped because
    #: `gates.rookie_coverage` cannot see its subject without it — and a gate left UNEVALUABLE by an
    #: omission is not "legitimately unresolvable", it is a check nobody ran (NF1.7(a)).
    n_rookies: int
    absences: list[NflWeeklyAbsence]
    #: `assert_point_in_time` counts from the SERVING frame. `weeks_checked > 0` is what makes the
    #: gate non-vacuous — a guard that examined nothing has not passed (NF1.7(a)).
    pit_weeks_checked: int
    pit_records_checked: int
    pit_rows_dropped: int
    input_vintage: NflWeeklyInputVintage
    lineage: NflWeeklyLineage
    framing: NflWeeklyHonestFraming = NflWeeklyHonestFraming()


class NflWeeklyManifestResponse(NflWeeklyManifest):
    """What `/nfl/weekly/manifest` actually puts on the wire: the manifest PLUS the entitlement
    envelope `entitlement.open_manifest_payload` adds.

    ⛔⛔ WHY THIS EXISTS INSTEAD OF `response_model=NflWeeklyManifest` (NF-INC-0917B).

    The obvious fix for a pass-through route is to hang the contract model on it. On THIS route
    that would have been a REGRESSION, and the measurement is one line: validating the LIVE
    response against a bare `NflWeeklyManifest` drops

        ['entitled', 'freeBoard', 'locked', 'lockedSeason']

    because `open_manifest_payload` adds four keys the contract does not declare and pydantic
    silently discards what it has no field for. That is E9.41 exactly — `FeaturedYesterday` never
    declared `status`, the serializer stripped it, and Won/Lost colouring was broken for every
    settled pick with the store correct the whole time. Fixing a missing-field defect by
    introducing a dropped-field defect is not a fix; it is the same bug facing the other way.

    ⭐ SO THE ENVELOPE IS DECLARED RATHER THAN TOLERATED. The response is then additive in both
    directions — the nine defaulted contract fields arrive, the four envelope keys survive — and
    the shape is enforced at serving regardless of what a future builder writes, which is the half
    of this fix the box deploy cannot provide.

    ⚠️ THE RESIDUAL, NAMED: a key `entitlement_envelope` gains LATER would be dropped here, since
    this model declares the four it emits today. That is not left to memory —
    `test_the_manifest_response_declares_every_key_the_envelope_actually_adds` DERIVES the key set
    by calling `open_manifest_payload` on a real manifest and comparing, so growing the envelope
    without growing this model is a red build rather than a silent strip.

    ⛔ NOT a second contract. Everything a projection means is inherited from `NflWeeklyManifest`;
    what is added here is transport metadata about the CALLER's tier, which is why it lives on a
    response wrapper and not on the artifact the builder writes.
    """

    #: `False` unconditionally on this route — both free weekly handlers take no `Request` and read
    #: no entitlement, which is what makes the bytes identical for every caller (and the CDN entry
    #: legal). Served explicitly rather than implied by absence, for the E9.41 reason
    #: `entitlement_envelope` states: a client must never infer entitlement from a missing key.
    locked: bool = False
    entitled: bool = True
    lockedSeason: int
    #: Which season-board preset is free. Weekly has no presets, so this is the SEASON board's
    #: boundary travelling on a shared envelope — meaningless here, already deployed, and therefore
    #: preserved rather than tidied away (NF-C0: never remove a key a deployed client may read).
    freeBoard: dict[str, object]


class NflWeeklyPayload(BaseModel):
    """`players.json` — the stored superset. The free route serves `public_weekly_payload` of it."""

    season: int
    week: int
    generated_at: str
    scoring_system_id: Literal["ppr"] = SCORING_SYSTEM_ID
    players: list[NflWeeklyPlayer]


class NflWeeklyCurrent(BaseModel):
    """`current.json` — the pointer naming the newest built week. A full overwrite every build."""

    season: int
    week: int
    generated_at: str
    manifest_key: str
    players_key: str


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ NF-WK-MT1 — THE LEAGUE-SCORED WEEKLY LINE (the paid my-teams lens's contract)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The paid question the weekly stack exists to answer — "what does MY roster do this week, in MY
# league's scoring" — served by running the league's stored settings over the weekly COMPONENT line
# through `services/league_scoring`, the ONE server scorer NF-EPIC 1 already owns.
#
# ⛔ NO FOURTH SCORING IMPLEMENTATION, AND NOTHING ABOUT THE EXISTING THREE MOVES. The weekly
# component line is served under the SAME field names `projection_fields.STAT_FIELD` already maps to
# (`WEEKLY_COMPONENT_FIELD` is derived from it), so `league_scoring.score_row` reads a weekly row
# verbatim — the adapter in `services/weekly_league_board.py` contains no scoring arithmetic of its
# own, and `test_nf_wk_mt1_weekly_league_board.py` proves that by SUBSTITUTION rather than by grep.
#
# ───────────────────────────────────────────────────────────────────────────────────────────────
# ⭐⭐ THE POINT IS EXACT; THE RANGE AND THE REST-OF-SEASON TOTALS ARE NOT, AND THEY SAY SO
# ───────────────────────────────────────────────────────────────────────────────────────────────
# League scoring is LINEAR in the component line, so `leaguePts` is the league's settings applied to
# the projected stats — exact, not an approximation of anything.
#
# A RANGE is a different object. Re-expressing an 80% interval under arbitrary scoring needs the
# per-stat DISTRIBUTIONS (NF-W6c/W6d — staged challengers with no consumer), not the per-stat means.
# `score_row` does carry an interval by rescaling the payload's own bounds by the ratio the point
# moved; that is a defensible first-order move for a SEASON board and it is deliberately DISCARDED
# here, because a rescaled range labelled as this league's would be a pseudo-band asserting a
# precision the substrate does not have. So the range on the wire is the model's own PPR range,
# carried through UNCHANGED and labelled. Rest-of-season is the same story one step further out:
# there is no ROS component line at all, so it could only ever be scaled, and it is not.
#
# ⚠️ THIS IS WHY `pprPts` IS SERVED BESIDE `leaguePts` AND IS NOT OPTIONAL. The range brackets the
# PPR number, not the league number. A range rendered beside a league-scored point with no PPR point
# in sight reads as that point's range, which is false — so the number the range actually belongs to
# travels with it. Any consumer that renders the band MUST render `pprPts`.
#
# ⚠️ AND THE TWO NUMBERS WILL NOT AGREE, BY CONSTRUCTION RATHER THAN BY DEFECT. NF-C6-PH2 measured
# it: scoring the served component line as full-PPR against the served points head gives mean SIGNED
# −0.7709, median |d| 0.6016, p95 3.7101, max 7.9200 over n=503 staged rows (2026-09-05) — the
# component line scores BELOW the points head on average. They are INDEPENDENT heads of one model,
# not a value and its own derivation, so neither corrects the other. ⛔ A disclosure phrased as "the
# components may exceed the total" is BACKWARDS (the PM adopted that warning verbatim on 2026-09-14,
# NF-WK-FE1's disposition). `SCORING_BASIS_NOTE` states the mechanism in words and quotes no figure:
# a typed magnitude drifts silently on the next re-score, and the honest route to a rendered number
# is a coherence block written by the box beside the figures `component_coherence` already computes —
# a PM-declined option, deliberately NOT taken here.
#
# ───────────────────────────────────────────────────────────────────────────────────────────────
# ⭐ A LEAGUE SCORES FEWER TERMS WEEKLY THAN IT DOES SEASONALLY, AND THAT IS REPORTED, NOT HIDDEN
# ───────────────────────────────────────────────────────────────────────────────────────────────
# The champion's component head emits ELEVEN stats (`WEEKLY_COMPONENT_STAT_KEY`). The season payload
# carries far more — `fumbles_lost`, `two_pt`, `pass_cmp`, every K and D/ST term. Those terms are in
# the DEFAULT preset scoring, so a perfectly ordinary full-PPR league has real weights on stats this
# week's line cannot express.
#
# `league_scoring.resolve_scoring` already answers this correctly when it is handed the fields that
# are ACTUALLY PRESENT: such a term resolves as CAPTURED — kept for fidelity, scored as zero, and
# named in the report — rather than silently zeroed behind an "applied" label. So `coverage` on this
# envelope is not decoration: it is the difference between "your fumble scoring contributed nothing"
# and "your fumble scoring is not in this number", which are different facts.
#
# ⛔ WHICH MAKES THE FIELD SET A CORRECTNESS INPUT, NOT AN OPTIMISATION. Run against the PUBLIC
# weekly payload every component would be absent, every term would resolve CAPTURED, and every
# player would score exactly 0.0 — a total, silent failure that looks like a calm empty state.
# `weekly_league_board.score_weekly_roster` REFUSES a payload carrying no component field at all.

#: Why a rostered player carries no weekly line. FIVE causes, and they are separated because an
#: empty state meaning several things costs an investigation every time it recurs (NF-C6b; NF-K1,
#: where a board that published ZERO K and D/ST rows sent two investigations at a join that was
#: fine and simply had nothing to match against).
#:
#: ⭐ `position_not_projected` IS REUSED VERBATIM from `ABSENCE_REASONS` because it means exactly
#: what it means there. The other four are NEW, and deliberately do NOT reuse that tuple's
#: `no_gameday_roster_row` / `pit_gate_dropped`: those are MANIFEST-level attributions counted over
#: the whole slate, and this route cannot tell which of them applies to one player. Emitting either
#: per-row would be a confident wrong explanation — worse than none (NF1.7 (a)). The manifest's own
#: counts travel on `absences` so a reader can see the slate-level split without us imputing it.
ROSTER_ABSENCE_REASONS: tuple[str, ...] = (
    "position_not_projected",     # K / D/ST / IDP — the champion covers QB/RB/WR/TE only
    "position_absent_this_week",  # projectable by contract, yet ZERO rows served this week (our gap)
    "not_in_weekly_payload",      # projectable AND served; this player has no row (see `absences`)
    "roster_position_unknown",    # the stored roster row carries no usable position
    "roster_row_unnamed",         # the stored roster row carries no name to join on
)

#: Plain-words scope for the two figures that are NOT in the caller's scoring. No imperative, no
#: opponent language, and no magnitude (see the header for why a typed figure is refused).
SCORING_BASIS_NOTE = (
    "The points column is your league's scoring applied to this week's projected stat line. The "
    "range and the rest-of-season totals beside it are the model's own PPR figures, carried through "
    "unchanged — re-expressing a range in your scoring needs a per-stat distribution, which this "
    "projection does not publish. The PPR number the range belongs to is shown with it. The two "
    "numbers come from two separate outputs of the model rather than one being derived from the "
    "other, so they will not match exactly."
)


class NflWeeklyRosterAbsence(BaseModel):
    """Why one rostered player has no weekly line. `reason` is machine-readable and drawn from
    `ROSTER_ABSENCE_REASONS`; `detail` is the sentence a surface may render as-is."""

    reason: str
    detail: str


class NflWeeklyLeagueRow(BaseModel):
    """One rostered player under the caller's league scoring.

    The roster side is echoed even when nothing matched, so an absent player still renders as
    himself rather than as a blank row — the whole point of separating the absence causes."""

    # ── the stored roster row, echoed ───────────────────────────────────────────────────────────
    rosterName: str
    rosterPos: str | None = None
    rosterTeam: str | None = None
    starter: bool | None = Field(
        default=None, description="whether the platform had this player in a starting slot at import"
    )

    # ── the matched weekly row's identity (null when absent) ────────────────────────────────────
    id: str | None = None
    name: str | None = None
    pos: str | None = None
    team: str | None = None
    opp: str | None = Field(default=None, description="opponent team code; null on a bye")
    home: bool | None = None
    status: str | None = Field(default=None, description='"projected" or "bye"')

    #: ⭐ THE NUMBER THIS ROUTE EXISTS TO PRODUCE — the league's settings applied to the projected
    #: component line. Exact (scoring is linear in the line), not a rescale of anything.
    leaguePts: float | None = None

    #: The model's own PPR number. Served because the range below is ITS range (header).
    pprPts: float | None = None

    # ── the served PPR range and rest-of-season totals, carried through UNCHANGED ───────────────
    bandP10: float | None = None
    bandP90: float | None = None
    rosPpr: float | None = None
    rosP10: float | None = None
    rosP90: float | None = None
    rosWeeks: int | None = None
    histWeeks: int | None = None

    absence: NflWeeklyRosterAbsence | None = None


class NflWeeklyLeagueBoard(BaseModel):
    """One saved league's roster, scored for one week. The response of the paid my-teams lens.

    ⛔ CARRIES NO COMPONENT LINE. The caller is entitled to it (this route sits behind the same
    `require_fantasy_access` as `/nfl/weekly/projections-full`) and can fetch it there; shipping it
    again here would multiply the response by a roster for no question this surface asks."""

    season: int
    week: int
    league_id: str
    league_name: str | None = None

    #: What `leaguePts` is in: the league's own settings, named rather than assumed.
    scoring_source: Literal["league_settings"] = "league_settings"
    #: What `pprPts`, the range and the rest-of-season totals are in.
    band_scoring_system_id: Literal["ppr"] = SCORING_SYSTEM_ID
    scoring_basis_note: str = SCORING_BASIS_NOTE

    #: `league_scoring.resolve_scoring`'s report — every league term classified applied / derived /
    #: captured against the fields this week's line ACTUALLY carries. See the header: this is what
    #: separates "contributed nothing" from "is not in this number".
    coverage: dict

    #: Which projectable positions this week's payload ACTUALLY carries, read off the served rows
    #: rather than restated from `PROJECTED_POSITIONS` — the NF-K1 direction. A constant would have
    #: reported a position as published right through an outage in which it was not.
    weekly_positions: list[str]

    rows: list[NflWeeklyLeagueRow]

    #: The manifest's own slate-level absence counts, carried so a per-row `not_in_weekly_payload`
    #: can be understood without this route imputing a reason it cannot know.
    #:
    #: ⚠️ `null`, NOT `[]`, when the manifest could not be read. An empty list is a REAL answer
    #: ("this week left nobody out"), and conflating it with "we do not know" would make every
    #: absent player on a degraded read look unexplained when the explanation merely failed to
    #: load — the same distinction `/nfl/my-teams` draws with `board_positions` (NF1.7 (a)).
    absences: list[NflWeeklyAbsence] | None = None

    generated_at: str
    projection_day: str | None = None


#: Every model this contract declares — the walk targets for the schema guards, and the registry
#: `test_nf_c6_ph2_weekly_contract.py` asserts is EXHAUSTIVE (a model added to this file but not to
#: this tuple would escape every guard, which is the vacuity this list exists to prevent).
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    NflWeeklyPlayer, NflWeeklyAbsence, NflWeeklyInputVintage, NflWeeklyLineage,
    NflWeeklyHonestFraming, NflWeeklyManifest, NflWeeklyManifestResponse, NflWeeklyPayload,
    NflWeeklyCurrent,
    # NF-WK-MT1 — the league-scored weekly lens. In the registry so the import-time claim guards
    # walk these too: a surface that renders a roster is exactly where a start/sit imperative or an
    # opponent claim would first appear.
    NflWeeklyRosterAbsence, NflWeeklyLeagueRow, NflWeeklyLeagueBoard,
)


# ── the free/paid reduction (mirrors `projection_fields`, which is the LIVE season path) ─────────

def public_weekly_player_row(row: dict) -> dict:
    """One player-week reduced to what a non-paying caller may hold.

    Takes no caller — see the byte-identity note in the header. A non-dict row is returned untouched
    rather than dropped: a malformed row must cost only itself, never blank the collection (E9.49).
    """
    if not isinstance(row, dict):
        return row
    return {k: v for k, v in row.items() if k not in PAID_WEEKLY_PLAYER_FIELDS}


def public_weekly_payload(data: dict) -> dict:
    """`players.json` with every paid field removed from every row."""
    players = data.get("players")
    if not isinstance(players, list):
        return dict(data)
    return {**data, "players": [public_weekly_player_row(r) for r in players]}


def paid_weekly_fields_present(data: dict) -> set[str]:
    """Which PAID fields a payload still carries — the audit instrument.

    Returns names rather than a bool so a failure says exactly what leaked. A field present but
    `None` does NOT count as a leak: the contract declares every field, and a declared null carries
    no value (this is the same reason nothing here is serialised with `exclude_none`).
    """
    out: set[str] = set()
    for row in data.get("players") or []:
        if not isinstance(row, dict):
            continue
        out |= {k for k in PAID_WEEKLY_PLAYER_FIELDS if row.get(k) is not None}
    return out


# ── the schema guards ────────────────────────────────────────────────────────────────────────────

def declared_field_names(model: type[BaseModel]) -> tuple[str, ...]:
    """The field names `model` declares, in declaration order."""
    return tuple(model.model_fields.keys())


def _nested_model(annotation) -> type[BaseModel] | None:
    """`X` if `annotation` is `X` or `X | None` and `X` is one of our models, else None.

    ⚠️ A `list[X]` IS NOT A NESTED OBJECT, and skipping it here is load-bearing rather than tidy:
    `get_args(list[NflWeeklyAbsence])` is `(NflWeeklyAbsence,)`, identical to what a union yields,
    so without the guard `absences` recursed as though the LIST were one absence — reported as
    "absences is list, not an object" on a perfectly valid manifest. Caught by running this against
    the real published blob rather than by reading it.
    """
    if get_origin(annotation) is list:
        return None
    for cand in (annotation, *get_args(annotation)):
        if get_origin(cand) is list:
            continue
        if isinstance(cand, type) and issubclass(cand, BaseModel):
            return cand
    return None


def _item_model(annotation) -> type[BaseModel] | None:
    """`X` if `annotation` is `list[X]` (or `list[X] | None`) and `X` is one of our models."""
    for cand in (annotation, *get_args(annotation)):
        if get_origin(cand) is list:
            inner = get_args(cand)
            if inner and isinstance(inner[0], type) and issubclass(inner[0], BaseModel):
                return inner[0]
    return None


def missing_declared_fields(blob, model: type[BaseModel], *, where: str = "") -> list[str]:
    """Every field `model` (and its nested models) declares that `blob` does NOT carry, as paths.

    ⛔⛔ THIS ASKS THE QUESTION `model_validate` CANNOT (NF-INC-0917B). A field declared REQUIRED
    WITH A DEFAULT can never fail validation by being absent — the default lands on the validated
    object, and if the caller then writes the INPUT dict the field reaches nobody. That is exactly
    how a manifest missing `framing` passed its own guard and took `/fantasy/weekly` down for 758
    minutes. `model_validate` answers "could this become a valid object"; this answers "is the
    contract ON THE WIRE", and only the second question is the one a published artifact has to pass.

    ⭐ DERIVED FROM THE MODELS, NEVER A HAND LIST, and it RECURSES: a nested contract added later
    (or a field added to `NflWeeklyLineage`) is covered the moment it is declared, with nothing to
    remember. A hand-written key list is the denylist hazard `PAID_WEEKLY_PLAYER_FIELDS` is
    derived to avoid, one contract over.

    Returns PATHS (`manifest.lineage.model_family`) rather than bare names so a caller's refusal
    says where to look. An explicit `null` COUNTS AS PRESENT — the contract declares nullable
    fields on purpose and a declared null carries no value (the same reason nothing here is
    serialised with `exclude_none`).
    """
    pre = f"{where}." if where else ""
    if not isinstance(blob, dict):
        return [f"{where or '<root>'} is {type(blob).__name__}, not an object"]
    out = [f"{pre}{f}" for f in model.model_fields if f not in blob]
    for name, field in model.model_fields.items():
        if name not in blob or blob[name] is None:
            continue
        sub = _nested_model(field.annotation)
        if sub is not None:
            out += missing_declared_fields(blob[name], sub, where=f"{pre}{name}")
            continue
        item = _item_model(field.annotation)
        if item is not None and isinstance(blob[name], list):
            for i, row in enumerate(blob[name]):
                out += missing_declared_fields(row, item, where=f"{pre}{name}[{i}]")
    return out


def _served_texts(models=CONTRACT_MODELS) -> list[tuple[str, str]]:
    """(where, text) for every served field NAME and DESCRIPTION — the scan surface.

    ⛔ Deliberately NOT source files. The champion consumes an `opponent_matchup__*` feature family,
    so a source-wide scan would fire on the model's own internals (the NF-W7 `'temp' ⊂ 'attempt'`
    over-eager-guard shape). What is banned is a CLAIM about where the edge comes from, and a claim
    only reaches a reader through a name or a description.
    """
    out: list[tuple[str, str]] = []
    for model in models:
        for name, field in model.model_fields.items():
            out.append((f"{model.__name__}.{name}", name))
            if field.description:
                out.append((f"{model.__name__}.{name}.description", field.description))
            default = field.default
            if isinstance(default, str):
                out.append((f"{model.__name__}.{name}.default", default))
    return out


def assert_no_edge_claim_in_schema(models=CONTRACT_MODELS) -> None:
    """REFUSE a field name that reads as a pick / edge / stake / win-rate claim."""
    offending = [
        where for where, text in _served_texts(models)
        if where.count(".") == 1
        and text not in FORBIDDEN_TOKEN_EXEMPT_FIELDS
        and any(tok in text.lower() for tok in FORBIDDEN_PAYLOAD_TOKENS)
    ]
    if offending:
        raise ValueError(
            f"the NFL weekly served contract declares {offending}, which reads as an edge/pick "
            "claim. This is an edge-independent projection product (best_alpha = 0) — "
            "distributions and intervals only."
        )


def assert_no_matchup_claim(texts, *, where: str = "the NFL weekly served contract") -> None:
    """REFUSE copy, a field name or a description claiming the weekly edge is matchup-based.

    NF-W1 MEASURED the opposite: `foil_matchup` (season ÷ games spread by a matchup adjustment) lost
    to the champion at all four positions AND lost to the flat foil. The edge is usage/snap
    conditioning. Exported so the weekly FRONTEND story can point this at its copy constants rather
    than re-inventing the token list — one owner, two consumers.
    """
    offending = [
        (label, phrase)
        for label, text in texts
        for phrase in FORBIDDEN_CLAIM_PHRASES
        if phrase in str(text).lower()
    ]
    if offending:
        raise ValueError(
            f"{where} claims {offending}, but NF-W1 measured the matchup foil LOSING at all four "
            "positions (QB 3.7820 / RB 3.0974 / WR 3.1806 / TE 2.2299 mean CRPS vs the champion's "
            "2.5882 / 2.5046 / 2.6726 / 1.8197) — it lost to the FLAT foil too. The weekly edge is "
            "usage/snap conditioning. Record: ablation_results/nf_w1_weekly_bakeoff.md."
        )


def assert_best_alpha_is_zero(payload: dict) -> None:
    """Every `best_alpha` anywhere in a payload tree must be exactly 0.0.

    Walked rather than trusted to the model default: a builder that CONSTRUCTS the framing block
    could carry a non-zero through, and the stamp's whole point is that it is a fact about the
    program rather than a value in a row.
    """
    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "best_alpha":
                    if v is None or float(v) != 0.0:
                        raise ValueError(
                            f"{path}.{k} = {v!r}; best_alpha must be exactly 0.0 — no stake rides "
                            "on an NFL weekly projection."
                        )
                else:
                    walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(payload)


# Fail at IMPORT if the contract ever declares a claim field: the router and the builder both import
# this module, so neither can start against a schema that violates the posture. A guard that only
# runs under pytest would let a bad deploy ship on a day CI was skipped.
assert_no_edge_claim_in_schema()
assert_no_matchup_claim(_served_texts())
