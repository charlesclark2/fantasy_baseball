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


#: NCAAF-P3.3 — one FBS team's stats page, addressed by CFBD team id. LATEST-WINS, exactly like
#: the futures board: the payload declares the `season` it describes, so nothing has to guess a
#: season from a key. ⛔ NOT keyed on a week — the page carries the whole week SERIES and names its
#: own `as_of_week`, and a week in a key would inherit the `season_order_week` alias landmine.
def team_cache_key(team_id: int | str) -> str:
    return f"{NAMESPACE}/team/{team_id}"


def slate_s3_key(game_day: str) -> str:
    return f"{S3_PREFIX}/slate/{game_day}.json"


def game_s3_key(game_id: int | str) -> str:
    return f"{S3_PREFIX}/game/{game_id}.json"


def team_s3_key(team_id: int | str) -> str:
    return f"{S3_PREFIX}/team/{team_id}.json"


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
    #: WHICH observation this line is — `odds_api_live` (the ahead-of-kickoff board,
    #: NCAAF-ODDS-LIVE), `odds_api_historical_t_minus_1` (the ~24h-prior snapshot, P0.6c) or
    #: `odds_api_historical_close` (K−5min). All three can coexist per kickoff, and they are
    #: materially different numbers — a live line days out and a close are a week of movement
    #: apart — so a served number that did not SAY which one it is would be a number whose
    #: meaning a reader cannot recover. The served line is the FRESHEST of them that is provably
    #: pre-kickoff; `as_of` says when.
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


# ── NCAAF-P3.3: the team stats page ──────────────────────────────────────────────────────────
#
# ⚖️ EVERY BLOCK CARRIES ITS OWN `status` + `reason`, and that is not ceremony.
#
# A team page assembles from FOUR independent sources with genuinely different availability: the
# P1.2 strength posterior comes from the LAKE and exists from week 1 (a zero-game row is a real
# PRE-SEASON posterior, not a gap); the P1.1 efficiency / trench / pace blocks come from the dbt
# marts and DO NOT EXIST until games have been played; the schedule exists as soon as the season
# rolls forward. So on the Saturday of week 1 a correct page has a strength rating, a schedule, and
# three blocks that are honestly, structurally empty — and rendering that identically to "the mart
# build failed" would cost an investigation every time week 1 comes round (NF-C6b / NF-K1).
#
# ⛔ NULLS STAY NULL. Nothing here is defaulted to 0.0 to make a column render: a fabricated zero is
# a wrong number that looks like a measurement.


#: `status`/`reason` values a team-page block can carry. Machine-readable so a surface BRANCHES
#: rather than pattern-matching a sentence.
TEAM_BLOCK_REASON_NO_GAMES = "no_games_played_yet"
TEAM_BLOCK_REASON_NOT_BUILT = "source_marts_unavailable"
TEAM_BLOCK_REASON_NO_ROW = "no_row_for_this_team_and_season"


class NcaafTeamBlockStatus(BaseModel):
    """Why a block of the team page is empty, when it is.

    ⭐ THE THREE CAUSES ARE KEPT APART BECAUSE THEY POINT AT DIFFERENT THINGS: `no_games_played_yet`
    is the correct state of week 1 and needs no action; `source_marts_unavailable` means OUR build
    did not run and is a defect; `no_row_for_this_team_and_season` means the team exists but this
    particular rollup has nothing for it. A single blank renders all three the same.
    """

    status: Literal["available", "unavailable"] = "unavailable"
    reason: str | None = None


class NcaafTeamIdentity(BaseModel):
    """Who the team is, AS OF THE SEASON BEING DESCRIBED.

    ⭐ REALIGNMENT IS THE POINT. `conference` is resolved through `dim_ncaaf_team`'s SCD-2 versions
    at the payload's own season, never off a "current" row — a type-1 read would report 2026's
    Pac-12 Boise State as Mountain West for every prior season, or (worse, and the direction that
    actually bites a live page) report a 2026 mover under its 2025 conference. Eleven FBS programs
    changed conference for 2026 and two of them are brand new to FBS, which is why this is a
    declared field with a stated source rather than a value copied along from whatever row was
    handy.

    `conference_source` says WHICH resolution produced it, so a reader (and a guard) can tell a
    dim-resolved conference from a fallback. `conference_matches_model_input` records whether the
    P1.2 strength row agreed: they are independently derived, and a disagreement is a real finding
    about the model's inputs rather than something to silently paper over.
    """

    team_id: int
    team: str | None = None
    season: int
    conference: str | None = None
    conference_division: str | None = None
    classification: str | None = None
    #: "scd2_dim" when resolved point-in-time through `dim_ncaaf_team`; "model_input" when only the
    #: strength row carried one; None when neither did.
    conference_source: str | None = None
    #: None when either side had no conference to compare.
    conference_matches_model_input: bool | None = None
    abbreviation: str | None = None
    mascot: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    venue_state: str | None = None
    #: True only when the team has NO prior-season FBS row — a first-year FBS program, whose
    #: pre-season covariates are absent by construction rather than missing by accident.
    is_new_to_fbs: bool | None = None


class NcaafTeamStrengthWeek(BaseModel):
    """One (team, as_of_week) row of the P1.2 posterior — the rating AND its band.

    ⚠️ `strength_margin_sd` IS NOT OPTIONAL DECORATION. At as_of_week 1 no game has been played and
    the posterior is the prior: the rating is real and the band is WIDE (~7 points of sd on the
    2026 opener). A surface that showed the number without the band would be publishing a precision
    the model does not claim, which on this vertical is the whole difference between context and a
    pick.

    🚨 SIGN CONVENTION: `strength_offense` and `strength_defense` are BOTH higher-is-better
    (defense = points PREVENTED). Net strength is their SUM. `offense - defense` returns ~0 for
    every team; `strength_margin` is the number to read.
    """

    as_of_week: int
    games_in_window: int | None = None
    has_sufficient_sample: bool | None = None
    strength_margin: float | None = None
    strength_margin_sd: float | None = None
    #: the three additive pieces of `strength_margin` — they sum to it exactly, which is what makes
    #: the rating auditable instead of a black box.
    strength_conference_component: float | None = None
    strength_covariate_component: float | None = None
    strength_team_component: float | None = None
    strength_offense: float | None = None
    strength_offense_sd: float | None = None
    strength_defense: float | None = None
    strength_defense_sd: float | None = None


class NcaafTeamStanding(BaseModel):
    """Where a team's rating places it in a population — WITH how uncertain that placement is.

    ⭐⭐ THE RANGE IS THE WHOLE REASON THIS MODEL EXISTS, and it is not the same argument as the
    band on the rating. A rank is the most compressed, most quotable, most screenshot-able number
    a page like this can publish, and it reads as exact in a way a point estimate with a `±` does
    not. Measured on the live 2026 week-1 board (138 teams, every sd ≈ 7.3): the MEDIAN team's 80%
    rank range spans **77 of 138 places**, and 130 of 138 span more than 40. Boise State's point
    rank is 42nd and its 80% range is 18th to 97th. A bare "42nd" would therefore be the single
    most over-precise thing on the page — worse than a bare rating, which at least carries its own
    spread.

    ⏳ AND THE NOISE EXPIRES, WHICH IS WHY THE FIX IS A RANGE RATHER THAN A REFUSAL. The width is a
    function of the posterior sd, which shrinks as games are played, so the same fields get sharper
    on their own through the season and a November rank is genuinely informative. Refusing to rank
    at all would have been correct in week 1 and wrong by week 10; publishing a bare rank is wrong
    in week 1 and fine by week 10. Publishing rank-with-range is right in both.

    ⛔ NOT A RATING OF ANYTHING NEW. Every field here is a descriptive re-expression of the P1.2
    posterior that is already served on this same block — an ordering of numbers a reader can
    already see. No selection is performed, no new predictive claim is made, and nothing here is a
    recommendation about a game (`best_alpha = 0`).
    """

    #: `"fbs"` or `"conference"` — which population the rank is within.
    scope: str
    #: What to call that population to a reader: `"FBS"`, or the conference's own name.
    scope_label: str | None = None
    #: 1 = the highest-rated team in the population, by the served `strength_margin`.
    rank: int | None = None
    #: The rank interval, at the SAME levels as the rating's own band so the two cannot be read
    #: against different confidences. `rank_lo` is the BETTER (numerically smaller) rank.
    rank_lo: int | None = None
    rank_hi: int | None = None
    #: How many teams were ranked. ⚠️ Not the size of the conference — the size of the population
    #: that HAD a usable posterior, which is the only set a rank can honestly be taken within.
    n_ranked: int | None = None
    #: Restated from the interval that produced the range, never a constant on the client.
    interval_lo_level: float | None = None
    interval_hi_level: float | None = None


class NcaafTeamStrength(BaseModel):
    """The strength block: the CURRENT week's posterior plus the season's week-by-week series."""

    status: Literal["available", "unavailable"] = "unavailable"
    reason: str | None = None
    #: the newest `as_of_week` in `weeks`, restated so a client need not scan for it.
    as_of_week: int | None = None
    current: NcaafTeamStrengthWeek | None = None
    weeks: list[NcaafTeamStrengthWeek] = []
    #: fit-level context, identical for every team in a season — carried so a rating can be read
    #: against the league it is measured in rather than in the abstract.
    league_base_points: float | None = None
    home_field_advantage: float | None = None
    residual_sigma: float | None = None
    model_version: str | None = None
    #: how many prior seasons the shrinkage was calibrated on. The first emitted season has only
    #: one and is measurably weaker; disclosed rather than buried.
    hyper_n_prior_seasons: int | None = None
    #: Where this rating places the team, in FBS and in its own conference. See `NcaafTeamStanding`
    #: for why each carries a RANGE. Null when the population was too small to rank within (a
    #: one-team conference is not a standing) or when this team has no posterior to place.
    standing_fbs: NcaafTeamStanding | None = None
    standing_conference: NcaafTeamStanding | None = None
    # ── NCAAF-P3.3b — WHEN this rating last took in games, and when it next will ──────────────
    #
    # ⭐ THE RATING'S DATE IS PART OF THE RATING, for the same reason the band is. P3.3 measured
    # the gap: the posterior moves only when P1.2 is re-fit, so between fits a team can win by 26
    # while its rating, band and both ranks sit unchanged beside that win in its own schedule.
    # Every number above is then correct and the PAGE is still misleading, because a reader reads
    # a rating printed today as a rating computed today. `generated_at` cannot answer it — that is
    # when the SERVING WRITE ran (hourly), which is precisely the number that makes a five-week-old
    # rating look fresh.
    #
    # ⚠️ BOTH ARE ISO-8601 UTC INSTANTS OR NULL, AND NULL IS A STATED ABSENCE THE SURFACE RENDERS
    # — never a date the client invents, and never a silently-dropped field (E9.41: an undeclared
    # field is stripped on serialize, which is how a store that had the value right the whole time
    # serves a page that never shows it).
    #
    #: When `ncaaf/derived/team_strength_week` was last WRITTEN — read from inside its Delta
    #: transaction log, never an S3 `LastModified` (INC-41). `run_team_strength` is its only
    #: writer, so a newer value here means a re-fit actually landed.
    ratings_as_of: str | None = None
    #: The next scheduled REWRITE of that artifact.
    #:
    #: ⛔ NULL TODAY, AND THAT IS A MEASUREMENT RATHER THAN AN OMISSION (2026-09-04): no Dagster
    #: schedule re-fits P1.2 — it is an operator laptop step, stated in the roll-forward job, the
    #: snapshot job and `BOX_OPERATIONS.md §10`, and confirmed on the lake (the ratings table last
    #: committed 2026-08-18 while the roll-forward's own tables committed 2026-08-31 13:00Z, i.e.
    #: it fired and moved nothing here). Deriving this from `NCAAF_ROLL_FORWARD_CRON` — which
    #: P3.3b was specified to do, on a premise recorded in #1081's commit message — would promise a
    #: refresh that job cannot deliver. `betting_ml/monitoring/ncaaf_ratings_vintage.py` owns the
    #: registry this comes from and refuses that entry by name.
    ratings_next_update: str | None = None


class NcaafTeamEfficiency(BaseModel):
    """Opponent-adjusted efficiency (P1.1), at the newest as-of week with games behind it.

    ⭐ ADJUSTED AND RAW ARE BOTH SERVED. Raw efficiency is close to meaningless in this sport —
    136 teams, ~12 games, almost no schedule overlap — so the adjusted number is the one to read;
    serving the raw beside it is what lets a reader see how much of a team's profile is schedule.
    ⛔ There is deliberately no ranking field: an ordering over 136 teams computed here would be a
    claim this page does not make.
    """

    status: Literal["available", "unavailable"] = "unavailable"
    reason: str | None = None
    as_of_week: int | None = None
    games_played: int | None = None
    adj_off_ppa: float | None = None
    adj_def_ppa: float | None = None
    adj_net_ppa: float | None = None
    adj_off_success_rate: float | None = None
    adj_def_success_rate: float | None = None
    adj_points_for_per_game: float | None = None
    adj_points_against_per_game: float | None = None
    raw_off_ppa: float | None = None
    raw_def_ppa: float | None = None
    raw_off_success_rate: float | None = None
    raw_def_success_rate: float | None = None
    raw_points_for_per_game: float | None = None
    raw_points_against_per_game: float | None = None
    #: strength of schedule, as the adjustment itself measures it.
    sos_opponent_net_ppa: float | None = None
    opponents_counted: int | None = None
    #: False when no opponent rating existed and the adjusted value FELL BACK to the raw one — the
    #: number is then honest but unadjusted, and a surface that did not say so would be presenting
    #: a raw figure under an adjusted label.
    adjustment_applied: bool | None = None
    #: False in the first weeks, when opponents have 0-1 games and the adjustment is mostly noise.
    has_reliable_adjustment: bool | None = None


class NcaafTeamSplits(BaseModel):
    """Trench and pace splits (P1.1), at the same as-of week as the efficiency block.

    TRENCH = line yards + stuff rate, both sides. PACE = plays, drives, possession time, points per
    drive. They are one model because they come from one rollup row and share one availability.
    """

    status: Literal["available", "unavailable"] = "unavailable"
    reason: str | None = None
    as_of_week: int | None = None
    games_played: int | None = None
    # ── trenches ──
    off_line_yards: float | None = None
    def_line_yards: float | None = None
    off_stuff_rate: float | None = None
    def_stuff_rate: float | None = None
    # ── pace / drive economy ──
    off_plays_per_game: float | None = None
    possession_seconds_per_game: float | None = None
    drives: int | None = None
    points_per_drive: float | None = None
    scoring_opportunity_rate: float | None = None
    three_and_out_rate: float | None = None
    explosive_drive_rate: float | None = None
    avg_start_yards_to_goal: float | None = None
    off_explosiveness: float | None = None
    def_explosiveness: float | None = None


class NcaafTeamGame(BaseModel):
    """One game on the team's season schedule — played or upcoming.

    ⭐ `is_completed` IS THE ONLY THING THAT SEPARATES A RESULT FROM A FIXTURE, and every scoring
    field is null on an upcoming game rather than zero. A 0-0 on next week's opponent would read as
    a played scoreless game; the honest render of "not yet" is nothing at all.

    ⛔ NO PROJECTION HERE. This block is the schedule and what happened; the model's view of an
    upcoming game lives on `/ncaaf/games/{game_id}`, which is what `game_id` is for.
    """

    game_id: int
    # ⛔ NO WEEK LABEL, DELIBERATELY, AND THE REASON IS A NAME COLLISION RATHER THAN A LIMITATION.
    #
    # TWO different columns in this repo are called `season_order_week`. `dim_ncaaf_game`'s is a
    # genuinely derived, postseason-safe ordering (monotone in the kickoff date). But
    # `game_prediction_snapshot.py`'s is a VERBATIM ALIAS of CFBD's raw `week`, which restarts at 1
    # in the postseason — the recorded alias landmine, and the reason
    # `test_ncaaf_p3_1_serving.py::test_nothing_in_the_serving_layer_keys_on_season_order_week`
    # bans the token from this layer outright. Serving the safe one under the unsafe one's name is
    # how the next reader conflates them.
    #
    # Nothing is lost: the schedule is ordered by `game_day`, each row carries `is_postseason`, and
    # `game_id` links to the game board. A properly-named week label is a deliberate follow-up, not
    # an omission — recorded in the story's closeout rather than smuggled in under a banned name.
    #: ⭐ THE AMERICA/LOS_ANGELES KICKOFF DAY, derived from the kickoff INSTANT — the SAME field
    #: name, semantics and format as `NcaafGamePrediction.game_day`, so the two payloads agree and
    #: a client can cross-link without a conversion.
    #:
    #: ⚠️ IT IS NOT `dim_ncaaf_game.game_date`, AND THE DIFFERENCE IS THE INC-22 BUG. That mart
    #: column is `start_date::date` — the UTC date — so a 03:30-UTC kickoff (a Saturday NIGHT game
    #: everywhere in the US, i.e. the marquee window on a college slate) files under SUNDAY. A team
    #: page that dated a night game a day late would disagree with the game board about the same
    #: game, which is the two-renderers class on a value a reader checks first.
    game_day: str | None = None
    #: the kickoff instant, UTC ISO-8601 — the same instant `NcaafGamePrediction.commence_time`
    #: carries, under the same name (one word, one instant — the P3.1b `snapshot_ts` lesson).
    commence_time: str | None = None
    season_type: str | None = None
    is_postseason: bool | None = None
    is_home: bool | None = None
    is_neutral_site: bool | None = None
    is_conference_game: bool | None = None
    #: False when the opponent is not FBS — a real and common case in September, and one a reader
    #: needs in order to read a result correctly.
    is_fbs_matchup: bool | None = None
    opponent_team_id: int | None = None
    opponent: str | None = None
    opponent_conference: str | None = None
    venue_name: str | None = None
    is_completed: bool | None = None
    team_points: int | None = None
    opponent_points: int | None = None
    #: this team's margin (team points − opponent points), null until the game is played.
    margin: int | None = None
    #: "W" / "L" / "T", null until the game is played.
    result: str | None = None


class NcaafTeamSchedule(BaseModel):
    """The season's games, in date order, with the played/upcoming split stated as counts."""

    status: Literal["available", "unavailable"] = "unavailable"
    reason: str | None = None
    n_games: int = 0
    n_completed: int = 0
    n_upcoming: int = 0
    wins: int | None = None
    losses: int | None = None
    ties: int | None = None
    games: list[NcaafTeamGame] = []


class NcaafTeamPage(BaseModel):
    """One FBS team's stats page, as served.

    Assembled from four independently-available sources; see `NcaafTeamBlockStatus` for why each
    block states its own availability rather than sharing one.
    """

    sport: Literal["ncaaf"] = "ncaaf"
    season: int
    generated_at: str
    team: NcaafTeamIdentity
    strength: NcaafTeamStrength = NcaafTeamStrength()
    efficiency: NcaafTeamEfficiency = NcaafTeamEfficiency()
    splits: NcaafTeamSplits = NcaafTeamSplits()
    schedule: NcaafTeamSchedule = NcaafTeamSchedule()
    provenance: NcaafModelProvenance = NcaafModelProvenance()
    framing: NcaafHonestFraming = NcaafHonestFraming()


#: Every model this contract declares — the walk targets for the schema guards below, and the
#: registry `test_ncaaf_serving_contract.py` asserts is EXHAUSTIVE (a model added to this file but
#: not to this tuple would escape every guard, which is the vacuity this list exists to prevent).
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    NcaafHonestFraming, NcaafModelProvenance, NcaafTeamSide, NcaafWinProbability,
    NcaafDistribution, NcaafMarketLine, NcaafGamePrediction, NcaafSlate, NcaafGameDayRef,
    NcaafManifest, NcaafFuturesTeam, NcaafFuturesBoard,
    # NCAAF-P3.3 — the team stats page
    NcaafTeamBlockStatus, NcaafTeamIdentity, NcaafTeamStrengthWeek, NcaafTeamStanding,
    NcaafTeamStrength,
    NcaafTeamEfficiency, NcaafTeamSplits, NcaafTeamGame, NcaafTeamSchedule, NcaafTeamPage,
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


#: The levels the strength band and the rank range are BOTH taken at.
#:
#: ⭐ ONE OWNER, because the two are read together: "42nd of 138, plausibly 18th–97th" beside
#: "+3.1, plausibly −6.2 to +12.4" invites a reader to treat them as the same statement, and they
#: only ARE the same statement if they are taken at the same confidence. Serving the levels rather
#: than assuming them also means a later ladder change is additive on the client instead of
#: silently relabelling a range it did not recompute.
TEAM_STANDING_INTERVAL_LO_LEVEL: float = 0.10
TEAM_STANDING_INTERVAL_HI_LEVEL: float = 0.90
