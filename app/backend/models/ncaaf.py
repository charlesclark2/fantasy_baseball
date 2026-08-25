"""ncaaf.py — NCAAF-P3.1: the SERVED payload contract for the college-football vertical.

THIS MODULE IS THE CONTRACT, AND IT HAS EXACTLY ONE OWNER
---------------------------------------------------------
Every field the NCAAF surfaces ever see is declared here, once. Both ends of the pipe read this
module and nothing else:

  * the BOX WRITER (`scripts/write_ncaaf_serving_store.py`) builds its blobs against these models
    and REFUSES to write a payload that does not validate — so a field the app expects can never be
    silently absent from the store;
  * the API ROUTER (`app/backend/routers/ncaaf.py`) returns these models — so a field the store
    carries can never be silently DROPPED on serialize.

That second half is the E9.41 landmine, and it is why the models live here rather than being
inferred from the blob: `FeaturedYesterday` never declared `status`, FastAPI/Pydantic stripped it,
and the Won/Lost colour was broken for every settled pick since the field was introduced — with the
data correct in the store the whole time and no error anywhere. A response model is a WHITELIST.

⛔ WHY THIS FILE IMPORTS NOTHING FROM `quant_sports_intel_models`
----------------------------------------------------------------
The API Lambda ships a hand-curated copy list (`infrastructure/lambda/deploy.sh` §3b-3d) and
`test_nf_c_lda_1_lambda_import_weight.py` FAILS the build if the backend imports a
`quant_sports_intel_models` module that list does not carry. A contract shared with the box writer
must therefore live on the backend side and be imported *by* the box, never the reverse. The box
image is a `COPY . .` of the repo, so `app.backend.models.ncaaf` is present there; this module is
pydantic + stdlib only, so importing it costs the box nothing.

📣 HONEST FRAMING IS A SCHEMA PROPERTY, NOT A PROMISE
-----------------------------------------------------
P1.4's CLV leg came back a clean null (VAL1: ATS 0.496 = placebo; the pooled CLV null stands), so
`best_alpha = 0` — no stake rides on any number here. A payload field named for a pick, an edge, a
stake or a win-rate would assert something the evidence does not support, so
`assert_no_edge_claim_in_schema` walks the whole declared model tree and REFUSES such a name. There
is no pick field, and adding one means deleting a guard — a reviewable act rather than an accident.
This mirrors `game_prediction_snapshot.assert_no_edge_claim`, which enforces the same property one
layer up on the persisted lake rows; `test_ncaaf_serving_contract.py` pins the two token lists
together so the two enforcement points cannot silently fork (the E9.61 two-renderers class).

⚖️ ABSENT vs NULL — A DIFFERENT FACT, DELIBERATELY DISTINGUISHABLE
------------------------------------------------------------------
"We have no prediction for this game" and "we have a prediction and its market line is unknown" are
different facts and must not render identically (the NF-C6b/NF-K1 lesson: an empty state that means
three things costs an investigation every time it recurs).

  * ABSENT  → the game is not in the slate at all / the router 404s. Nothing is fabricated.
  * NULL    → the field is DECLARED, PRESENT in the JSON, and `null`, with a machine-readable
              `status` + `reason` beside it wherever a reader could otherwise mistake the null for
              a defect (see `NcaafMarketLine`).

Consequently NOTHING here is ever serialised with `exclude_none` — a declared field is always on
the wire. `test_ncaaf_serving_contract.py` asserts exactly that.

🔑 THE KEY SCHEME — LA GAME-DAY, AND OFF THE MLB SERVING LANE
--------------------------------------------------------------
Keys are namespaced `ncaaf/…` in the SAME DynamoDB table and the SAME S3 bucket the MLB lane uses,
under a namespace/prefix nothing else writes. That is "separate keys, not a separate lane"
deliberately: the DynamoDB partition key IS the namespace (`pk="ncaaf"`), so no MLB read can reach
an NCAAF row and no NCAAF write can touch an MLB one, while the existing IAM grants
(`credence-prod-serving-cache` table-wide; `credence-prod-s3-api-cache/*` bucket-wide) already
cover it — no new grant, so no E8.5-class silently-denied first write.

Every date in a key is the **America/Los_Angeles game-day** (`betting_ml.utils.game_day`), never
UTC: the box runs UTC, so a UTC-derived "today" rolls to tomorrow at 00:00 UTC — which is still
Saturday EVENING in the US, i.e. mid-slate for college football (INC-22).

⛔ AND NOTHING HERE IS KEYED ON A WEEK. CFBD restarts `week` at 1 for the postseason, so "week 1"
names both the season opener and a December bowl; `game_prediction_snapshot.py`'s
`season_order_week` is a verbatim alias of that raw week (the recorded alias landmine) and this
story may not key on it. A kickoff DATE cannot collide with itself, so the slate key, the manifest's
selector and every ordering here are date-grained. `cfbd_week` is carried on the payload as a
DISPLAY label only — read it, never group by it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# ── the standing posture, stamped on every payload ───────────────────────────────────────────

#: what the payload IS. Mirrors `game_prediction_snapshot.FRAMING` (pinned by a guard test).
FRAMING = "market_blind_projection"

#: ⛔ NOT a knob and NOT a result — the recorded fact that no stake rides on these numbers.
BEST_ALPHA = 0.0

#: The served disclosure string. Probability + calibration language only: no pick, no edge, no
#: win-rate, no "best bets". Pinned verbatim by `test_ncaaf_serving_contract.py` so a reword is a
#: reviewed change rather than a drift (the NF-C10 rendered-string lesson).
DISCLOSURE = (
    "These are market-blind projections: probabilities and distributional intervals from a model "
    "that never sees a betting line. Where a market line is shown it is shown for comparison only "
    "— we make no claim to an advantage over it, and we publish no picks."
)

#: Tokens a market-blind projection payload may never carry in a FIELD NAME. Byte-identical to
#: `game_prediction_snapshot.FORBIDDEN_PAYLOAD_TOKENS` — pinned equal by a guard test so the lake
#: row contract and the served contract cannot fork.
FORBIDDEN_PAYLOAD_TOKENS: tuple[str, ...] = (
    "edge", "pick", "bet", "wager", "win_rate", "roi", "clv", "recommend", "kelly", "alpha",
    "value_side", "best_side",
)

#: The single exemption, and the reason it exists: `best_alpha` NAMES the absence of a claim.
FORBIDDEN_TOKEN_EXEMPT_FIELDS: frozenset[str] = frozenset({"best_alpha"})


# ── the key scheme ───────────────────────────────────────────────────────────────────────────

#: The DynamoDB partition key for everything this vertical serves. `serving_cache` derives `pk`
#: from the cache key up to the first "/", so this prefix IS the isolation from the MLB lane.
NAMESPACE = "ncaaf"

#: The S3 fallback prefix. Deliberately NOT `api-cache/` (the MLB lane's prefix) — same bucket,
#: same grant, disjoint key space.
S3_PREFIX = "ncaaf-cache"


def slate_cache_key(game_day: str) -> str:
    """The blob holding every FBS game kicking off on `game_day` (an LA date, `YYYY-MM-DD`)."""
    return f"{NAMESPACE}/slate/{game_day}"


def game_cache_key(game_id: int | str) -> str:
    """One game's full prediction blob, addressed by its CFBD game id."""
    return f"{NAMESPACE}/game/{game_id}"


#: The P1.5 futures board — one blob, latest-wins.
FUTURES_CACHE_KEY = f"{NAMESPACE}/futures/board"

#: What days have a slate, which season, and when it was built. This is what a week selector reads
#: instead of a CFBD week (see the module docstring).
MANIFEST_CACHE_KEY = f"{NAMESPACE}/manifest"


def slate_s3_key(game_day: str) -> str:
    return f"{S3_PREFIX}/slate/{game_day}.json"


def game_s3_key(game_id: int | str) -> str:
    return f"{S3_PREFIX}/game/{game_id}.json"


FUTURES_S3_KEY = f"{S3_PREFIX}/futures/board.json"
MANIFEST_S3_KEY = f"{S3_PREFIX}/manifest.json"


# ── the models ───────────────────────────────────────────────────────────────────────────────

#: `model_*` field names collide with pydantic v2's protected namespace. They are the honest names
#: for model provenance and renaming them to dodge a library warning would make the served payload
#: describe itself less clearly, so the namespace is cleared instead.
_UNPROTECTED = ConfigDict(protected_namespaces=())


class NcaafHonestFraming(BaseModel):
    """The honest-frame flags, stamped on every blob this vertical serves.

    Machine-readable, not just copy: a surface can BRANCH on `market_blind` / `projection_only`
    rather than trusting a rendered sentence, which is what makes the VAL1 null enforceable
    downstream instead of merely documented (the spec's "flags are the enforcement" clause).
    """

    framing: Literal["market_blind_projection"] = FRAMING
    #: always 0.0 — asserted, not defaulted-and-hoped (`assert_best_alpha_is_zero`).
    best_alpha: float = BEST_ALPHA
    market_blind: bool = True
    projection_only: bool = True
    disclosure: str = DISCLOSURE


class NcaafModelProvenance(BaseModel):
    """Which artifacts produced the number, and which vintage of the inputs they read.

    Served rather than kept internal so a reader can audit *what we ran*, and so a stale board is
    visible instead of inferable (the NF-FRESH2 per-input as-of lesson).
    """

    model_config = _UNPROTECTED

    model_version: str | None = None
    model_form: str | None = None
    model_learner: str | None = None
    model_contract: str | None = None
    mean_artifact_version: str | None = None
    #: the P1.2 strength vintage the prediction read. A WEEK INDEX ON THE INPUT, never a key.
    strength_as_of_week: int | None = None
    #: whether the certified S1/S1b pace term ACTED. False pre-season is correct by construction
    #: (week-1 team-weeks are NULL and a NULL contributes exactly 0.0 to a mean-imputed ridge);
    #: recording it means "no pace" is stated rather than silent.
    pace_term_active: bool | None = None
    n_draws: int | None = None
    #: the immutable pre-kickoff instant the prediction was taken at (UTC ISO-8601).
    snapshot_ts: str | None = None
    snapshot_kind: str | None = None


class NcaafTeamSide(BaseModel):
    """One side of a matchup, with the P1.2 posterior that priced it."""

    team_id: int | None = None
    team: str | None = None
    conference: str | None = None
    strength_margin: float | None = None
    strength_margin_sd: float | None = None


class NcaafWinProbability(BaseModel):
    """Both sides, explicitly. `away` is served rather than left as `1 - home` so a client never
    has to re-derive it (two renderers of one number is how they drift — E9.61)."""

    home: float | None = None
    away: float | None = None


class NcaafDistribution(BaseModel):
    """Enough to DRAW the curve, two independent ways.

    `mu`/`sigma` parameterise the served predictive directly; the quantile ladder is the
    non-parametric read of the SAME joint draw, so a client that would rather interpolate an
    empirical curve than assume a shape can. `quantile_levels` and `quantiles` are parallel arrays
    in the same order — the levels are served rather than assumed so a later ladder change is
    additive to the client instead of a silent re-interpretation (NF-C0).
    """

    mu: float | None = None
    sigma: float | None = None
    quantile_levels: list[float] = []
    quantiles: list[float] = []
    #: the central interval quoted as "the interval" — 0.10/0.90, matching P1.4's calib_80.
    interval_lo_level: float | None = None
    interval_hi_level: float | None = None
    interval_lo: float | None = None
    interval_hi: float | None = None
    interval_width: float | None = None


class NcaafMarketLine(BaseModel):
    """The market's line, served BESIDE the model's — transparency, never a comparison verdict.

    ⭐ There is deliberately NO difference/discrepancy field. "Model −7, market −3.5" is a fact a
    reader can see; "model beats market by 3.5" is the claim VAL1's null forbids, and a signed
    difference column is one rename away from being read as exactly that.

    `status` + `reason` exist because a null market line has SEVERAL causes that must not render
    identically: no line has been captured for this kickoff yet, versus a read that failed. A
    surface can say which; a bare `null` cannot.
    """

    status: Literal["available", "unavailable"] = "unavailable"
    #: machine-readable cause when `status == "unavailable"`; None when available.
    reason: str | None = None
    #: WHICH captured snapshot this line is — `odds_api_historical_t_minus_1` (the ~24h-prior
    #: line, P0.6c) or `odds_api_historical_close` (K−5min). NCAAF-P3.1b: the two coexist per
    #: kickoff in the lake, so a served line that did not SAY which one it is would be a number
    #: whose meaning a reader cannot recover — and the T-1 line is a materially different thing
    #: from a close (a day of movement apart).
    source: str | None = None
    snapshot_ts: str | None = None
    #: NCAAF-P3.1b, ADDITIVE (NF-C0): the instant the served line was captured — the same value as
    #: `snapshot_ts`, declared under a reader-facing name because `snapshot_ts` means the MODEL's
    #: snapshot in `provenance` and the MARKET's here, and one word meaning two instants on one
    #: payload is the mislabelling class this vertical keeps paying for. A surface can quote
    #: `as_of` beside the line without having to know which block it came from.
    as_of: str | None = None
    home_spread: float | None = None
    total: float | None = None
    home_moneyline_american: float | None = None
    home_moneyline_implied_probability: float | None = None


class NcaafGamePrediction(BaseModel):
    """One pre-kickoff, market-blind projection for one FBS-vs-FBS game."""

    game_id: int
    season: int
    #: the America/Los_Angeles calendar day this game kicks off on — the serving grain (INC-22).
    game_day: str
    commence_time: str | None = None
    start_time_tbd: bool | None = None
    season_type: str | None = None
    #: ⚠️ CFBD's raw week — a DISPLAY LABEL ONLY. It restarts at 1 in the postseason, so it is not
    #: an ordering and nothing keys on it (see the module docstring).
    cfbd_week: int | None = None
    is_neutral_site: bool | None = None
    is_conference_game: bool | None = None
    home: NcaafTeamSide = NcaafTeamSide()
    away: NcaafTeamSide = NcaafTeamSide()
    win_probability: NcaafWinProbability = NcaafWinProbability()
    #: the HOME margin distribution (home points − away points).
    margin: NcaafDistribution = NcaafDistribution()
    total: NcaafDistribution = NcaafDistribution()
    market: NcaafMarketLine = NcaafMarketLine()
    provenance: NcaafModelProvenance = NcaafModelProvenance()
    framing: NcaafHonestFraming = NcaafHonestFraming()


class NcaafSlate(BaseModel):
    """Every projection for one LA game-day."""

    sport: Literal["ncaaf"] = "ncaaf"
    game_day: str
    season: int
    generated_at: str
    n_games: int
    games: list[NcaafGamePrediction] = []
    framing: NcaafHonestFraming = NcaafHonestFraming()


class NcaafGameDayRef(BaseModel):
    game_day: str
    n_games: int


class NcaafManifest(BaseModel):
    """The index a surface reads to know what exists — WITHOUT ever asking about a week."""

    sport: Literal["ncaaf"] = "ncaaf"
    season: int
    generated_at: str
    #: "today" in LA terms at write time — the default slate a surface opens on.
    current_game_day: str
    game_days: list[NcaafGameDayRef] = []
    n_games_total: int = 0
    futures_available: bool = False
    provenance: NcaafModelProvenance = NcaafModelProvenance()
    framing: NcaafHonestFraming = NcaafHonestFraming()


class NcaafFuturesTeam(BaseModel):
    """One team's P1.5 season-simulation probabilities."""

    team_id: int
    team: str | None = None
    conference: str | None = None
    strength_margin: float | None = None
    strength_margin_sd: float | None = None
    expected_wins: float | None = None
    expected_losses: float | None = None
    #: False for a conference that crowns no champion (too few members / Independents) — which is
    #: why `p_conference_title = 0.0` there is a STRUCTURAL zero, not a projection of futility.
    conference_title_available: bool | None = None
    p_conference_title: float | None = None
    p_playoff: float | None = None
    p_top_seed: float | None = None
    p_reach_final: float | None = None
    p_national_title: float | None = None


class NcaafFuturesBoard(BaseModel):
    """The P1.5 futures board as served."""

    sport: Literal["ncaaf"] = "ncaaf"
    season: int
    generated_at: str
    n_sims: int | None = None
    n_teams: int = 0
    teams: list[NcaafFuturesTeam] = []
    provenance: NcaafModelProvenance = NcaafModelProvenance()
    framing: NcaafHonestFraming = NcaafHonestFraming()


#: Every model this contract declares — the walk targets for the schema guards below, and the
#: registry `test_ncaaf_serving_contract.py` asserts is EXHAUSTIVE (a model added to this file but
#: not to this tuple would escape every guard, which is the vacuity this list exists to prevent).
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    NcaafHonestFraming, NcaafModelProvenance, NcaafTeamSide, NcaafWinProbability,
    NcaafDistribution, NcaafMarketLine, NcaafGamePrediction, NcaafSlate, NcaafGameDayRef,
    NcaafManifest, NcaafFuturesTeam, NcaafFuturesBoard,
)


# ── the schema guards ────────────────────────────────────────────────────────────────────────

def declared_field_names(model: type[BaseModel]) -> tuple[str, ...]:
    """The field names `model` declares, in declaration order."""
    return tuple(model.model_fields.keys())


def assert_no_edge_claim_in_schema(models=CONTRACT_MODELS) -> None:
    """REFUSE a field name that reads as a pick / edge / stake / win-rate claim.

    The mirror of `game_prediction_snapshot.assert_no_edge_claim`, moved up to the SERVED contract:
    that one polices the lake row, this one polices what reaches a reader. Both are needed — a
    field can be introduced at either end.
    """
    offending: list[str] = []
    for model in models:
        for name in model.model_fields:
            if name in FORBIDDEN_TOKEN_EXEMPT_FIELDS:
                continue
            if any(tok in name.lower() for tok in FORBIDDEN_PAYLOAD_TOKENS):
                offending.append(f"{model.__name__}.{name}")
    if offending:
        raise ValueError(
            f"the NCAAF served contract declares {offending}, which reads as an edge/pick claim. "
            "This vertical serves a market-blind projection (best_alpha=0; P1.4's CLV leg was a "
            "clean null, VAL1 ATS 0.496 = placebo) — probabilities and intervals only.")


def assert_best_alpha_is_zero(payload: dict) -> None:
    """Every `best_alpha` anywhere in a payload tree must be exactly 0.0.

    Walked rather than trusted to the model default: a writer that CONSTRUCTS the framing block
    from lake values (rather than letting the default apply) could carry a non-zero through, and
    the whole point of the stamp is that it is a fact about the program, not a value in a row.
    """
    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "best_alpha":
                    if v is None or float(v) != 0.0:
                        raise ValueError(
                            f"{path}.{k} = {v!r}; best_alpha must be exactly 0.0 — no stake rides "
                            "on an NCAAF projection (the recorded CLV null).")
                else:
                    walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(payload)


# Fail at IMPORT if the contract ever declares a claim field: the router and the writer both import
# this module, so neither can start against a schema that violates the posture. A guard that only
# runs under pytest would let a bad deploy ship on a day CI was skipped.
assert_no_edge_claim_in_schema()
