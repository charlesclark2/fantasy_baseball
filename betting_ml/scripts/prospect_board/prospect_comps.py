"""prospect_comps.py — MLB Edge-E7.13: the PECOTA-style prospect → historical-MLB COMP engine.

Pure numpy / pandas, no IO, no `pipeline` import — so the fast gate exercises every rule below
directly (the repo convention for model-quality code, since CI mocks all IO). The runner
(`build_prospect_comps.py`) does the parquet/CSV reads and the export; everything that decides
*which players are comparable and what their outcomes mean* lives here.

WHAT THIS PRODUCES
------------------
For each prospect on the current board, the `k` most similar HISTORICAL prospects — players who
stood at a comparable point of a comparable career, graded by the same scouts, whose outcome we
now know — plus the empirical DISTRIBUTION of what those players actually did:

    "Similar to: Jordan Groshans, Nolan Jones, Brayan Rocchio.
     Of 15 comps: 9 never reached MLB, 3 fringe, 2 regular, 1 impact.
     3-yr dynasty points p10–p90: 0 – 291 (median 12)."

That sentence is the product. It is honest in the one way a prospect projection usually is not:
**most of the comps are failures, and the display says so.**

🔒 HONEST FRAME (`best_alpha = 0`). A comp is a similarity estimate, not a forecast. Nothing here
claims to beat FanGraphs, and the comp distribution is NOT blended into any projection unless the
E7.13 Phase-2 validation clears its deflated gates (see `run_e7_13_comp_validation.py`). Until then
these columns are DISPLAY, labelled as such on the board.

═══════════════════════════════════════════════════════════════════════════════════════════════
🚨 THE THREE WAYS A COMP ENGINE SHIPS BROKEN, AND WHAT THIS MODULE DOES ABOUT EACH
═══════════════════════════════════════════════════════════════════════════════════════════════

**(1) SURVIVORSHIP — the comp pool must contain the busts.**
The tempting pool is "historical players and their MLB careers", which silently means *players who
had an MLB career*. Comp against that and every prospect reads like a future regular, because the
61% who never arrived were filtered out before the median was taken. **The zeros are the point.**
This module's pool is E7.8's `fv_translation_cohort` — one row per (board season, prospect) drawn
from the board itself, so a player who never played an MLB inning is IN IT, carrying a realized
outcome of ZERO. `validate_pool` HARD-FAILS if the supplied pool's non-debut share falls below
`MIN_POOL_BUST_SHARE`, because a pool that has quietly lost its failures is the single most likely
way this ships wrong and it is invisible in any output you would think to eyeball.

**(2) HINDSIGHT IN THE COMP'S OWN PROFILE — measured, not hypothesised.**
A comp must be keyed to what a player looked like THEN, not to what he is now. FanGraphs serves the
*retained* past board rather than a point-in-time snapshot, and the retained board's **`level`
column is updated to the player's CURRENT level**. Measured on the live 2018–2022 cohort:

        level = 'MLB'            → 2,035 debuts, 1,258 non-debuts
        level ∈ {A, A+, AA, AAA} → 1,908 rows, of which ONE debuted

i.e. a minor-league `level` on a retained board is a **near-perfect one-sided tell that the player
busted**. A comp engine that used it would score beautifully in validation and be worthless in
production, where no such column exists. It is therefore in `LEAKED_COLUMNS` and
`assert_no_leaked_features` raises if it reaches the feature set. The leakage-safe substitute is
`top_level_pre_board`, derived from game logs strictly before the board date.

⚠️ The same retained-board caveat applies in principle to `fv` — E7.8 states it and this module
inherits it. It does NOT show the leak signature (`fv` separates debut/non-debut at AUC 0.701,
which is what an honest scouting grade looks like; the contaminated `level` sits at 0.800 with the
one-sided structure above). `fv` is kept, the caveat is carried in the report, and the Phase-2 arm
field includes a **matched `no_fv` foil** so the question is measured rather than asserted.

**(3) MATURITY — a comp whose outcome has not finished is not a comp.**
Distinct from (2), and easy to conflate with it. A 2024 board prospect has no realized 3-season
outcome yet; including him would mix "hasn't happened" into a distribution read as "didn't happen".
`matured_pool` keeps only comps whose entire outcome window closed strictly before the query's
as-of season.

📌 **A NOTE ON THE STORY'S "comps drawn ONLY from players who DEBUTED BEFORE the projection date".**
Read literally that is a *debuted-only* filter — which is precisely the survivorship filter (1)
forbids, and the two bullets of the prompt are in tension. The resolution implemented here, and
flagged to the operator: the binding rule is **the comp's OUTCOME WINDOW closed before the query
date**, which is the leakage intent (no comp may be keyed to information from the query's future)
while keeping every bust in the pool. Survivorship wins the tie; it has to.

═══════════════════════════════════════════════════════════════════════════════════════════════
📐 THE SIMILARITY METRIC
═══════════════════════════════════════════════════════════════════════════════════════════════

* **Robustly standardized, not raw.** Each numeric feature is centred on the pool median and scaled
  by the pool IQR (÷1.349, the normal-consistent estimator), then winsorized to ±3. Raw Euclidean
  on unstandardized features would let ISO (range ~0.30) and age (range ~14) trade at 45:1 by
  accident of units.
* **Gower, not Euclidean.** 15–18% of pool rows have no MiLB component line at all (drafted or
  signed too recently to have one), and 11% of the current board has no FanGraphs FV. Gower scores
  a pair over the features they SHARE and renormalizes by that weight, so a missing feature costs
  coverage rather than fabricating a neutral value. `MIN_PAIR_COVERAGE` stops the degenerate case
  where two players are declared identical because they happen to share one observed feature.
* **Position is a HARD FILTER**, not a weight. A shortstop is comped to middle infielders and a
  starter to starters. Pitcher role is the subtle case: the 2018–2020 boards list unresolved arms
  as `RHP`/`LHP` while the 2026 board uses `SP`/`SIRP`/`MIRP`, so a literal position filter would
  fail to match ACROSS ERAS. Role is therefore resolved from `minor_start_share` — a leakage-safe
  as-of quantity from pre-board game logs — whenever the position token does not carry it.
* **Every weight is traceable to a measured number**, in the same spirit as `board_assembly`'s:
  the component-metric shares are E7.3/E7.3p's out-of-sample translation correlations (so a metric
  that translates poorly cannot dominate the distance, and the two E7.3 NO-SIGNAL metrics —
  batter wOBA, pitcher HR-rate/xwOBA — are absent entirely rather than laundered in at low weight);
  the scouting-vs-us split is E7.8's `FV_WEIGHT_BY_TYPE` verdict. See `FEATURE_WEIGHTS`.
* **k is reported, and so is every distance.** `comp_detail_frame` emits one row per (prospect,
  comp) with its distance and outcome, so any comp on the board can be audited back to why.

📉 **COVERAGE HONESTY.** `comp_quality` is calibrated against the pool's OWN leave-one-out distance
distribution rather than an invented threshold: 'strong' = mean comp distance at or below the pool
median, 'fair' = below the pool p90, 'thin' = worse than 90% of the pool, too few eligible comps,
or too little of the query's own profile observed. A THIN row shows a WIDER band (p05–p90 rather
than p10–p90) and says so in `comp_note`. Never a false-precise comp off two neighbours.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "COMP_LEVEL_RANK",
    "CompsError",
    "DEFAULT_K",
    "FEATURE_WEIGHTS",
    "LEAKED_COLUMNS",
    "MIN_PAIR_COVERAGE",
    "OUTCOME_TIERS",
    "PoolStats",
    "assert_no_leaked_features",
    "attach_comp_ranking",
    "attach_comps",
    "build_pool",
    "comp_detail_frame",
    "comp_distribution",
    "comp_note",
    "distance_matrix",
    "fit_pool_stats",
    "format_comp_names",
    "level_from_token",
    "matured_pool",
    "outcome_tier",
    "tricube_weights",
    "pitcher_role",
    "position_group",
    "weighted_quantile",
]


class CompsError(RuntimeError):
    """A comp-engine invariant failed.

    HARD stop rather than a degraded column: every failure this raises on — a leaked feature, a
    de-busted pool, an un-matured comp — produces output that looks *better* than honest output,
    so a quiet fallback would ship the wrong answer wearing the right column names.
    """


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Leakage guards
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: Columns that MUST NEVER enter the similarity feature set. See the module docstring §(2).
#:
#: `level` — the retained board's CURRENT level (near-perfect one-sided bust tell).
#: `debuted` / `mlb_*` / `fantasy_points` / `exposure` / `outcome_tier` — the label itself.
#: `in_majors` — the current board's mirror of `level == 'MLB'`.
LEAKED_COLUMNS: frozenset[str] = frozenset({
    "level", "in_majors",
    "debuted", "fantasy_points", "exposure", "outcome_tier", "outcome_rank",
    "mlb_pa", "mlb_hits", "mlb_home_runs", "mlb_walks", "mlb_strikeouts",
    "mlb_batters_faced", "mlb_hits_allowed", "mlb_walks_allowed",
    "mlb_strikeouts_pitched", "mlb_home_runs_allowed",
    "mlb_woba", "mlb_k_pct", "mlb_bb_pct", "mlb_iso", "mlb_gb_pct", "mlb_hr_rate",
    "mlb_xwoba_against", "has_mlb_label", "is_prospect", "debut_cohort",
})

#: A pool whose non-debut share is below this is not a prospect pool, it is a graduate pool — the
#: survivorship failure the module exists to prevent. The live 2018–2022 cohort sits at ~0.61.
MIN_POOL_BUST_SHARE = 0.35


def assert_no_leaked_features(features: Iterable[str]) -> None:
    """Raise if any similarity feature is a label, or a retained-board field updated post-hoc.

    This is a *mechanical* guard on purpose. The `level` leak was not caught by reasoning about it;
    it was caught by crosstabbing the column against the outcome and finding 1,908 rows on one side
    of which exactly one debuted. A future feature add gets the check for free.
    """
    bad = sorted(set(features) & LEAKED_COLUMNS)
    if bad:
        raise CompsError(
            f"leaked feature(s) in the comp similarity set: {bad}. "
            "See prospect_comps §(2) — the retained board's `level` is the player's CURRENT level "
            "and is a near-perfect one-sided tell that he never debuted; outcome columns are the "
            "label. Use `top_level_pre_board` (derived pre-board-date) for level context."
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Level + position taxonomy
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: Ordinal level, shared by both sides of the join. The pool's `top_level_pre_board` uses the
#: E7.1 long names; the current board uses FanGraphs' short tokens. `level_from_token` normalizes.
#: Rookie-complex / DSL and "no full-season record yet" collapse to the SAME rank on purpose:
#: E7.1's MiLB substrate carries only the four full-season levels, so a CPX/DSL prospect and a
#: just-drafted prospect are, to every feature this engine can see, the same kind of unknown.
COMP_LEVEL_RANK: dict[str, int] = {
    "complex": 0, "single-a": 1, "high-a": 2, "double-a": 3, "triple-a": 4,
}

_LEVEL_TOKENS: dict[str, str] = {
    "single-a": "single-a", "a": "single-a", "lo-a": "single-a", "low-a": "single-a",
    "a-": "single-a", "sal": "single-a", "cal": "single-a", "flo": "single-a",
    "high-a": "high-a", "a+": "high-a", "hi-a": "high-a",
    "double-a": "double-a", "aa": "double-a",
    "triple-a": "triple-a", "aaa": "triple-a",
    "cpx": "complex", "dsl": "complex", "r": "complex", "rk": "complex",
    "rookie": "complex", "acl": "complex", "fcl": "complex",
}


def level_from_token(value: Any) -> str | None:
    """Normalize either taxonomy's level token to the shared `COMP_LEVEL_RANK` key.

    Returns None for a missing/unrecognized token AND for `MLB` — a player already in the majors
    has no *minor-league* level, and silently ranking him above Triple-A would smuggle the very
    outcome information `LEAKED_COLUMNS` bans. The caller supplies his highest MiLB level instead.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    tok = str(value).strip().lower()
    if not tok or tok in {"nan", "none", "(unknown)", "mlb", "maj", "majors"}:
        return None
    return _LEVEL_TOKENS.get(tok)


def level_rank(value: Any) -> float:
    """`COMP_LEVEL_RANK` of a token, or NaN when unknown (Gower drops it for that pair)."""
    key = level_from_token(value)
    return float(COMP_LEVEL_RANK[key]) if key is not None else float("nan")


_POSITION_GROUPS: dict[str, str] = {
    "C": "C",
    "SS": "IF_MID", "2B": "IF_MID", "MIF": "IF_MID", "INF": "IF_MID",
    "1B": "IF_CORNER", "3B": "IF_CORNER", "DH": "IF_CORNER",
    "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF",
}

#: A pitcher listed as bare `RHP`/`LHP` has an UNRESOLVED role — the 2018–2020 boards used
#: handedness where the 2026 board uses SP/SIRP/MIRP. Resolving that from the position token alone
#: would make the pool and the query un-matchable across eras (measured: pool is 1,371 RHP/LHP vs
#: 567 SP; the 2026 board is 329 SP vs 67 RHP/LHP). Role comes from `minor_start_share` instead.
_UNRESOLVED_ARM = {"RHP", "LHP", "P", "TWP"}
_STARTER_TOKENS = {"SP", "SIRP"}          # SIRP = swing/multi-inning → started, see below
_RELIEVER_TOKENS = {"RP", "MIRP", "CL"}

#: `minor_start_share` at or above this is a starter. 0.5 = "started at least half his appearances".
STARTER_SHARE_THRESHOLD = 0.5


def _first_token(position: Any) -> str | None:
    if position is None or (isinstance(position, float) and np.isnan(position)):
        return None
    tok = re.split(r"[/,|]", str(position).strip())[0].strip().upper()
    return tok or None


def pitcher_role(position: Any, minor_start_share: Any = None) -> str:
    """'SP' or 'RP' — resolved from the position token, falling back to measured start share.

    ⚠️ `SIRP` (swing / multi-inning reliever) is grouped with STARTERS, not relievers: FanGraphs
    uses it for arms who start in the minors and profile to the bullpen, and their MiLB workload —
    the thing every component feature here is measured over — is a starter's. `MIRP` (middle
    reliever) is a true reliever. Getting this backwards would comp starters' innings to one-inning
    arms' rate stats.
    """
    tok = _first_token(position)
    if tok in _STARTER_TOKENS:
        return "SP"
    if tok in _RELIEVER_TOKENS:
        return "RP"
    share = pd.to_numeric(pd.Series([minor_start_share]), errors="coerce").iloc[0]
    if pd.notna(share):
        return "SP" if float(share) >= STARTER_SHARE_THRESHOLD else "RP"
    return "SP"      # an unresolved arm with no workload record: the modal prospect arm is a starter


def position_group(position: Any, player_type: Any, minor_start_share: Any = None) -> str:
    """The HARD comp filter: 'C' | 'IF_MID' | 'IF_CORNER' | 'OF' | 'SP' | 'RP'.

    `player_type` wins over an ambiguous token — a two-way player's board position ('TWP', '1B/LHP')
    cannot be parsed reliably, and the board already resolved his type.
    """
    ptype = str(player_type).strip().lower() if player_type is not None else ""
    tok = _first_token(position)
    if ptype == "pitcher" or (tok in _UNRESOLVED_ARM | _STARTER_TOKENS | _RELIEVER_TOKENS
                              and ptype != "batter"):
        return pitcher_role(position, minor_start_share)
    if tok in _POSITION_GROUPS:
        return _POSITION_GROUPS[tok]
    # An unparsed batter token ("4C", "UTIL", a blank): the least-wrong group is the one that makes
    # the fewest positional assumptions. Corner IF is the default defensive bucket on any board.
    return "IF_CORNER" if ptype == "batter" else "SP"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The feature set + its weights
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐ EVERY WEIGHT BELOW IS A MEASURED NUMBER, NOT A TASTE CALL — the `board_assembly` convention.
#
#   * The SCOUTS-vs-US split is E7.8's verdict, re-used verbatim from `FV_WEIGHT_BY_TYPE`:
#       pitchers 0.70 (FV COMPLEMENTS our line — it added +0.031 on top of our +0.014, gates cleared)
#       batters  0.35 (FV SUBSTITUTES for it — +0.015 on top of our +0.047, no stage cleared)
#   * Inside OUR block, the component metrics take 0.75 and the structural "null" terms 0.25 —
#     `board_assembly.AGE_WEIGHT_IN_MODEL_SCORE`, unchanged.
#   * The component metrics split their share PROPORTIONAL to that metric's measured out-of-sample
#     translation correlation (E7.3 / E7.3p), so a metric that translates poorly cannot quietly
#     dominate the distance. The two NO-SIGNAL metrics are ABSENT, not down-weighted:
#       batter  wOBA 0.220 ❌   ·  pitcher HR-rate 0.094 ❌ / xwOBA-against 0.147 ❌
#     Including a null metric at a small weight would launder it into a similarity claim.
#   * The structural block is E7.8's NULL arm — age-relative-to-level, level, pedigree — split
#     EQUALLY, because E7.8 scored that arm as a block and never decomposed it. An unequal split
#     would be a number this program has not measured.
#
# 🔬 These are the PRE-REGISTERED defaults. The Phase-2 validation carries `no_fv` and `equal_block`
#    as matched foils so the split is TESTED rather than asserted (E7.13 arm field).

_BAT_COMPONENT_CORR = {"minor_k_pct": 0.637, "minor_bb_pct": 0.491, "minor_iso": 0.429}
_PIT_COMPONENT_CORR = {"minor_gb_pct": 0.551, "minor_bb_pct": 0.367, "minor_k_pct": 0.366}

_STRUCTURAL = ("age_vs_level", "level_rank", "pro_experience_years")
_FV_WEIGHT_BY_TYPE = {"batter": 0.35, "pitcher": 0.70}
_COMPONENT_SHARE_OF_MODEL_BLOCK = 0.75          # = 1 − board_assembly.AGE_WEIGHT_IN_MODEL_SCORE


def _build_weights(player_type: str) -> dict[str, float]:
    corr = _BAT_COMPONENT_CORR if player_type == "batter" else _PIT_COMPONENT_CORR
    fv_w = _FV_WEIGHT_BY_TYPE[player_type]
    model_w = 1.0 - fv_w
    comp_block = model_w * _COMPONENT_SHARE_OF_MODEL_BLOCK
    struct_block = model_w - comp_block
    total_corr = sum(corr.values())
    weights = {m: comp_block * c / total_corr for m, c in corr.items()}
    weights.update({s: struct_block / len(_STRUCTURAL) for s in _STRUCTURAL})
    weights["fv"] = fv_w
    return weights


#: feature → weight, per player type. Sums to 1.0 by construction.
FEATURE_WEIGHTS: dict[str, dict[str, float]] = {
    "batter": _build_weights("batter"),
    "pitcher": _build_weights("pitcher"),
}
for _t, _w in FEATURE_WEIGHTS.items():
    assert_no_leaked_features(_w)

#: The PERFORMANCE block — the features that make a comp a comp rather than a grade lookup.
COMPONENT_FEATURES: dict[str, tuple[str, ...]] = {
    "batter": tuple(_BAT_COMPONENT_CORR),
    "pitcher": tuple(_PIT_COMPONENT_CORR),
}

#: k = 25 is the MEASURED pick, not a round number: it won the E7.13 Phase-2 CRPS on BOTH player
#: types and took 5 of 6 CSCV in-sample halves on each (batters 64.81 vs 65.27 at k=15; pitchers
#: 97.90 vs 99.88). Raising k here is free on the display side — `comp_names` shows the three
#: CLOSEST comps, and the three closest of the 25 nearest are the same three as of the 15 nearest —
#: so a wider neighbourhood buys a better-resolved band and changes no name on the board.
DEFAULT_K = 25
#: Fewer eligible comps than this and the row is THIN regardless of how close they are — a
#: distribution read off 5 neighbours has a p10 that is one player's career.
MIN_COMPS = 8
#: A (query, comp) pair sharing less than this fraction of the total feature weight is not a
#: comparison, it is a coincidence. Excluded from the neighbour set entirely.
MIN_PAIR_COVERAGE = 0.50
#: …AND the pair must share this fraction of the COMPONENT-block weight specifically.
#:
#: 🚨 THIS SECOND FLOOR IS NOT BELT-AND-BRACES, IT IS LOad-BEARING — measured on the live pool.
#: FV alone carries 0.70 of the pitcher weight, so a *total*-weight floor of 0.50 is satisfied by
#: FV on its own: two arms sharing nothing but a grade pass the check, and because both their
#: remaining features are missing the Gower renormalization then scores them at distance EXACTLY
#: 0.000 — a perfect comp. 4,432 such pairs appeared in the first 50 query rows of the 2,648-row
#: pitcher pool, and they sort to the TOP of the comp list, e.g. Robert Stock (26, Triple-A, 9 years
#: pro) declared identical to Brailyn Marquez (19, no full-season record) on a shared 40 FV.
#: A comp is a claim about a PERFORMANCE profile. Without the performance block it is an FV bucket
#: wearing a player's name — the exact "false-precise comp off two neighbours" failure the coverage
#: floor exists to prevent, and it is INVISIBLE in any summary you would think to check.
MIN_COMPONENT_COVERAGE = 0.50

#: The fallback space for a prospect with NO full-season minor-league record at all (a just-drafted
#: or complex-league player: 13% of the 2026 board). He cannot be comped on performance, so he is
#: comped against pool rows in the SAME situation, on the only two things either board knows — how
#: old he is and what the scouts graded him. Split EQUALLY: no study in this program has measured
#: their relative weight for a player with no record, and inventing one would be a taste call.
#: Always labelled `comp_basis='scouting_only'` and forced to `comp_quality='thin'`.
SCOUTING_ONLY_FEATURES: tuple[str, ...] = ("age", "fv")
SCOUTING_ONLY_WEIGHTS: dict[str, float] = {"age": 0.5, "fv": 0.5}
#: A QUERY observing less than this fraction of its own feature weight is THIN — its comps are
#: real neighbours in the subspace it has, and the flag says the subspace is small.
MIN_QUERY_COVERAGE = 0.55
#: Winsorization bound on the robust z-scores, and hence the Gower per-feature denominator.
Z_CLIP = 3.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Outcome tiers — calibrated to the pool, not invented
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# Four exhaustive tiers. `never_reached` is its OWN tier rather than "the bottom of the scale",
# because the distinction a dynasty owner cares about is categorical: a player who never arrived is
# not a bad player, he is an absent one. The remaining three split the DEBUTED subpopulation at its
# own median and 85th percentile, so each tier's share of the pool is a fact about the pool.

OUTCOME_TIERS: tuple[str, ...] = ("never_reached", "fringe", "regular", "impact")
_TIER_LABELS: dict[str, str] = {
    "never_reached": "never reached MLB",
    "fringe": "fringe",
    "regular": "regular",
    "impact": "impact",
}
_DEBUTED_TIER_QUANTILES = (0.50, 0.85)


def outcome_tier(fantasy_points: Any, debuted: Any, cuts: Sequence[float]) -> str:
    """Map a realized outcome to its tier. `cuts` = the debuted-subpopulation (p50, p85)."""
    if not bool(debuted):
        return "never_reached"
    fp = pd.to_numeric(pd.Series([fantasy_points]), errors="coerce").iloc[0]
    if pd.isna(fp):
        return "never_reached"
    if fp < cuts[0]:
        return "fringe"
    if fp < cuts[1]:
        return "regular"
    return "impact"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Pool construction + validation
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PoolStats:
    """Everything fitted on the POOL that the query side must reuse verbatim.

    Fitting these on the pool alone is not a nicety — the query side is a single board with a
    different level mix, and standardizing it on its own moments would silently redefine what
    "one unit of ISO away" means between the two sides of the same distance.
    """
    player_type: str
    features: tuple[str, ...]
    weights: dict[str, float]
    center: dict[str, float]
    scale: dict[str, float]
    level_age_median: dict[int, float]
    tier_cuts: tuple[float, float]
    #: Pool-internal leave-one-out mean comp distances → the `comp_quality` calibration.
    quality_cuts: tuple[float, float] = (float("nan"), float("nan"))
    n_pool: int = 0

    def weight_total(self) -> float:
        return float(sum(self.weights[f] for f in self.features))


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df.get(col), errors="coerce")


def build_pool(cohort: pd.DataFrame, *, player_type: str,
               horizon_seasons: int | None = None) -> pd.DataFrame:
    """Turn E7.8's `fv_translation_cohort` into a comp pool for one player type.

    Derives ONLY leakage-safe fields: the level context comes from `top_level_pre_board` (the
    player's level at his last game strictly before the board date), never the retained `level`.
    """
    ptype = str(player_type)
    if ptype not in FEATURE_WEIGHTS:
        raise CompsError(f"unknown player_type {player_type!r}")
    df = cohort.loc[cohort["player_type"].astype(str) == ptype].copy()
    if df.empty:
        raise CompsError(f"empty comp pool for player_type={ptype!r}")

    df["comp_level"] = df["top_level_pre_board"].map(level_from_token)
    df["level_rank"] = df["comp_level"].map(lambda k: float(COMP_LEVEL_RANK[k]) if k else np.nan)
    df["fv"] = _numeric(df, "fv")
    df["age"] = _numeric(df, "age")
    df["pro_experience_years"] = _numeric(df, "pro_experience_years")
    for m in ("minor_k_pct", "minor_bb_pct", "minor_iso", "minor_gb_pct", "minor_start_share"):
        if m in df.columns:
            df[m] = _numeric(df, m)
    df["position_group"] = [
        position_group(p, ptype, s)
        for p, s in zip(df.get("position", pd.Series(index=df.index, dtype=object)),
                        df.get("minor_start_share", pd.Series(index=df.index, dtype=float)))
    ]
    df["fantasy_points"] = _numeric(df, "fantasy_points").fillna(0.0)
    df["debuted"] = df["debuted"].astype(bool)
    df["horizon_seasons"] = (int(horizon_seasons) if horizon_seasons is not None
                             else _numeric(df, "horizon_seasons").fillna(3).astype(int))
    df["board_season"] = _numeric(df, "board_season").astype("Int64")
    df["comp_key"] = df.get("player_key", df.get("mlbam_id")).astype(str)
    return df.reset_index(drop=True)


def validate_pool(pool: pd.DataFrame, *, min_bust_share: float = MIN_POOL_BUST_SHARE) -> dict:
    """HARD-fail a pool that has lost its busts, or that leaks. See the module docstring §(1).

    A survivorship-filtered pool produces output that is *more* attractive than the honest version —
    higher medians, tighter bands, rosier comps — so nothing downstream would flag it. This is the
    only place that can.
    """
    n = int(len(pool))
    if n == 0:
        raise CompsError("empty comp pool")
    bust_share = float((~pool["debuted"].astype(bool)).mean())
    if bust_share < min_bust_share:
        raise CompsError(
            f"comp pool non-debut share {bust_share:.3f} < {min_bust_share:.2f} — the busts have "
            "been filtered out. A comp distribution taken over survivors is survivorship-inflated "
            "and every comp reads rosy; the zeros ARE the downside (prospect_comps §1)."
        )
    zero_share = float((pool["fantasy_points"] <= 0).mean())
    return {"n_pool": n, "bust_share": round(bust_share, 4),
            "zero_outcome_share": round(zero_share, 4),
            "board_seasons": sorted(int(s) for s in pool["board_season"].dropna().unique()),
            "position_groups": pool["position_group"].value_counts().to_dict()}


def matured_pool(pool: pd.DataFrame, *, as_of_season: int) -> pd.DataFrame:
    """Comps whose ENTIRE outcome window closed strictly before `as_of_season`.

    Module docstring §(3). This is a *maturity* filter, not the point-in-time filter — a comp whose
    3-season window is still open contributes "hasn't happened yet" to a distribution the board
    reads as "didn't happen", which biases the bust rate UP and the upside DOWN.
    """
    last_outcome_season = pool["board_season"].astype("Int64") + pool["horizon_seasons"].astype(int)
    keep = last_outcome_season < int(as_of_season)
    out = pool.loc[keep.fillna(False)].reset_index(drop=True)
    if out.empty:
        raise CompsError(
            f"no matured comps for as_of_season={as_of_season} — every pool row's outcome window "
            "is still open. Comping against unfinished careers is what §3 forbids."
        )
    return out


def fit_pool_stats(pool: pd.DataFrame, *, player_type: str,
                   features: Sequence[str] | None = None,
                   weights: dict[str, float] | None = None) -> PoolStats:
    """Fit the standardization, the per-level age medians and the tier cuts on the POOL alone."""
    w = dict(weights) if weights is not None else dict(FEATURE_WEIGHTS[player_type])
    feats = tuple(features) if features is not None else tuple(w)
    assert_no_leaked_features(feats)
    missing = [f for f in feats if f not in w]
    if missing:
        raise CompsError(f"features without a weight: {missing}")

    # age-relative-to-level: the level's median age, TRAIN-SIDE ONLY (the E7.12-slice5 convention).
    lvl_med: dict[int, float] = {}
    lr = pool["level_rank"]
    for rank in sorted(set(COMP_LEVEL_RANK.values())):
        sub = pool.loc[lr == rank, "age"].dropna()
        if len(sub) >= 20:
            lvl_med[int(rank)] = float(sub.median())
    if not lvl_med:                        # degenerate pool — fall back to one global median
        lvl_med = {int(r): float(pool["age"].median()) for r in set(COMP_LEVEL_RANK.values())}

    frame = _feature_frame(pool, feats, lvl_med)
    center, scale = {}, {}
    for f in feats:
        col = frame[f].dropna().astype(float)
        center[f] = float(col.median()) if len(col) else 0.0
        iqr = float(col.quantile(0.75) - col.quantile(0.25)) if len(col) > 3 else 0.0
        # ÷1.349 makes the IQR a normal-consistent σ estimate; the floor stops a near-constant
        # feature (e.g. FV on a pool where everyone is a 45) from exploding into the whole distance.
        scale[f] = max(iqr / 1.349, 1e-6) if iqr > 0 else max(float(col.std(ddof=0) or 0.0), 1e-6)

    deb = pool.loc[pool["debuted"].astype(bool), "fantasy_points"].astype(float)
    cuts = ((float(deb.quantile(_DEBUTED_TIER_QUANTILES[0])),
             float(deb.quantile(_DEBUTED_TIER_QUANTILES[1]))) if len(deb) >= 10 else (0.0, 0.0))

    return PoolStats(player_type=player_type, features=feats, weights=w, center=center,
                     scale=scale, level_age_median=lvl_med, tier_cuts=cuts, n_pool=int(len(pool)))


def _feature_frame(df: pd.DataFrame, features: Sequence[str],
                   level_age_median: dict[int, float]) -> pd.DataFrame:
    """The raw (pre-standardization) feature matrix, with `age_vs_level` derived here.

    ⭐ `age_vs_level` and not raw age: age is a property of the LEVEL, not the player — 22 is old
    for Single-A and young for Triple-A — which is `board_assembly`'s own framing. A row whose
    level is unknown gets NaN rather than a global-median fallback: fabricating a neutral value is
    exactly the "forbidden fabricated neutral" the E7.12-S6 landmine names.
    """
    out = pd.DataFrame(index=df.index)
    for f in features:
        if f == "age_vs_level":
            lvl_med = df["level_rank"].map(lambda r: level_age_median.get(int(r))
                                           if pd.notna(r) else None)
            out[f] = pd.to_numeric(df["age"], errors="coerce") - pd.to_numeric(lvl_med,
                                                                               errors="coerce")
        else:
            out[f] = pd.to_numeric(df.get(f), errors="coerce")
    return out


def standardize(df: pd.DataFrame, stats: PoolStats) -> np.ndarray:
    """Robust-z + winsorize, using the POOL's centre/scale. NaN survives as NaN (Gower needs it)."""
    frame = _feature_frame(df, stats.features, stats.level_age_median)
    z = np.empty((len(frame), len(stats.features)), dtype=float)
    for j, f in enumerate(stats.features):
        col = (frame[f].astype(float).to_numpy() - stats.center[f]) / stats.scale[f]
        z[:, j] = np.clip(col, -Z_CLIP, Z_CLIP)
    return z


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Distance
# ══════════════════════════════════════════════════════════════════════════════════════════════


def distance_matrix(query_z: np.ndarray, pool_z: np.ndarray, weights: np.ndarray,
                    *, metric: str = "gower",
                    inv_cov: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(distance, pair_coverage) for every (query, pool) pair.

    **Gower** (default) — per feature, `|z_q − z_p| / (2·Z_CLIP)` ∈ [0,1]; the pair's distance is
    the weighted mean over features BOTH rows observe, and `pair_coverage` is the share of total
    weight those features carry. A feature missing on either side costs coverage rather than
    contributing a fabricated zero — which is the difference between "we could not compare these
    two on power" and "these two have identical power".

    **Mahalanobis** — the alternative the story pre-registers, on the standardized numerics with
    the pool covariance. It de-correlates (K% and wOBA carry overlapping information, and Gower
    double-counts that) but it cannot handle missingness, so rows are mean-imputed to the pool
    centre (z = 0) and `pair_coverage` still reports what was actually observed. Carried as a
    Phase-2 arm, not the default, precisely because that imputation is a fabricated neutral.
    """
    nq, nf = query_z.shape
    npool = pool_z.shape[0]
    if pool_z.shape[1] != nf or weights.shape[0] != nf:
        raise CompsError("feature-count mismatch between query, pool and weights")

    q_obs = ~np.isnan(query_z)
    p_obs = ~np.isnan(pool_z)
    wt_total = float(weights.sum())

    # shared-weight per pair: (nq, npool)
    shared_w = (q_obs.astype(float) * weights) @ p_obs.astype(float).T
    coverage = shared_w / wt_total if wt_total > 0 else np.zeros_like(shared_w)

    if metric == "mahalanobis":
        if inv_cov is None:
            raise CompsError("mahalanobis metric requires inv_cov")
        qz = np.nan_to_num(query_z, nan=0.0)
        pz = np.nan_to_num(pool_z, nan=0.0)
        sw = np.sqrt(weights)
        qz, pz = qz * sw, pz * sw
        diff = qz[:, None, :] - pz[None, :, :]
        d = np.sqrt(np.maximum(np.einsum("qpi,ij,qpj->qp", diff, inv_cov, diff), 0.0))
        # scale into a comparable [0,1]-ish band so `quality_cuts` mean the same thing across arms
        return d / (2.0 * Z_CLIP * np.sqrt(max(nf, 1))), coverage

    if metric != "gower":
        raise CompsError(f"unknown metric {metric!r}")

    num = np.zeros((nq, npool), dtype=float)
    for j in range(nf):
        qj, pj = query_z[:, j][:, None], pool_z[:, j][None, :]
        both = q_obs[:, j][:, None] & p_obs[:, j][None, :]
        contrib = np.abs(qj - pj) / (2.0 * Z_CLIP)
        num += weights[j] * np.where(both, np.nan_to_num(contrib, nan=0.0), 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.where(shared_w > 0, num / np.where(shared_w > 0, shared_w, 1.0), np.nan)
    return d, coverage


def tricube_weights(d: np.ndarray) -> np.ndarray:
    """Similarity weights: `(1 − u³)³` on the within-neighbourhood distance rank.

    PECOTA's lineage weights a comp by how similar it is rather than counting it equally. Tricube
    is the standard local-regression kernel — smooth, compactly supported, and it does not let the
    kth (worst) neighbour carry the same vote as the 1st. `u` is normalized by the neighbourhood's
    OWN worst distance, so the weighting is scale-free and a uniformly-close neighbourhood is
    weighted near-uniformly (which is the correct behaviour: they really are all comparable).
    """
    if d.size == 0:
        return d
    dmax = float(np.nanmax(d))
    if not np.isfinite(dmax) or dmax <= 0:
        return np.ones_like(d)
    u = np.clip(d / dmax, 0.0, 1.0)
    w = (1.0 - u ** 3) ** 3
    # the worst neighbour gets weight 0 under a raw tricube; give it the floor a k-NN implies
    return np.maximum(w, 1.0 / (4.0 * len(d)))


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float | Sequence[float]):
    """Weighted quantile(s) by the standard interpolated-CDF definition (`np.quantile`-compatible
    when the weights are equal)."""
    qs = np.atleast_1d(np.asarray(q, dtype=float))
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if v.size == 0:
        return np.full(qs.shape, np.nan) if qs.size > 1 else float("nan")
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w)
    # midpoint (a.k.a. "Type 5") plotting positions — unbiased for a weighted empirical CDF
    pos = (cw - 0.5 * w) / cw[-1]
    out = np.interp(qs, pos, v)
    return out if qs.size > 1 else float(out[0])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The comp distribution
# ══════════════════════════════════════════════════════════════════════════════════════════════

_QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


def comp_distribution(comp_fp: np.ndarray, comp_debuted: np.ndarray, comp_tier: Sequence[str],
                      comp_dist: np.ndarray, *, thin: bool,
                      similarity_weighted: bool = False) -> dict[str, Any]:
    """The realized-outcome distribution of a neighbourhood.

    Reports the median under BOTH weightings so the kernel's contribution stays visible rather than
    baked in (Phase 2 measured that the similarity kernel over-sharpens — see
    `CompConfig.similarity_weighted`), and the band WIDENS on a thin neighbourhood (p05–p90 instead
    of p10–p90) rather than pretending to the same resolution off fewer players.
    """
    k = int(len(comp_fp))
    if k == 0:
        return {"comp_k": 0, "comp_p_debut": np.nan, "comp_bust_rate": np.nan}
    d = np.asarray(comp_dist, dtype=float)
    w = tricube_weights(d) if similarity_weighted else np.ones(k, dtype=float)
    qv = weighted_quantile(comp_fp, w, _QUANTILES)
    tiers = pd.Series(list(comp_tier))
    counts = {t: int((tiers == t).sum()) for t in OUTCOME_TIERS}
    p_debut = float(np.average(np.asarray(comp_debuted, dtype=float), weights=w))
    lo_q, hi_q = (0.05, 0.90) if thin else (0.10, 0.90)
    out = {
        "comp_k": k,
        "comp_p_debut": round(p_debut, 4),
        "comp_bust_rate": round(1.0 - p_debut, 4),
        "comp_fp_median": round(float(qv[3]), 1),
        "comp_fp_median_simweighted": round(
            float(weighted_quantile(comp_fp, tricube_weights(d), 0.5)), 1),
        "comp_fp_p10": round(float(qv[1]), 1),
        "comp_fp_p25": round(float(qv[2]), 1),
        "comp_fp_p75": round(float(qv[4]), 1),
        "comp_fp_p90": round(float(qv[5]), 1),
        "comp_band_lo": round(float(qv[_QUANTILES.index(lo_q)]), 1),
        "comp_band_hi": round(float(qv[_QUANTILES.index(hi_q)]), 1),
        "comp_band_quantiles": f"p{int(lo_q * 100):02d}-p{int(hi_q * 100):02d}",
        "comp_mean_distance": round(float(np.mean(comp_dist)), 4),
        "comp_min_distance": round(float(np.min(comp_dist)), 4),
    }
    out.update({f"comp_n_{t}": counts[t] for t in OUTCOME_TIERS})
    return out


def format_comp_names(names: Sequence[str], distances: Sequence[float], n: int = 3) -> str:
    """`"Name (0.08), Name (0.11), Name (0.12)"` — the distance travels with the name on purpose.

    A comp without its distance invites the reader to treat the 12th-closest neighbour as the same
    kind of statement as the 1st. Every comp on the board is auditable back to its number.
    """
    pairs = list(zip(list(names)[:n], list(distances)[:n]))
    return ", ".join(f"{nm} ({d:.2f})" for nm, d in pairs)


def comp_note(dist: dict[str, Any], quality: str, *, basis: str = "full") -> str:
    """The one-line honest summary. Leads with the bust count, because that is the finding."""
    k = int(dist.get("comp_k", 0) or 0)
    if k == 0:
        return ("No comparable historical prospects — no full-season minor-league record to "
                "match on.")
    parts = []
    if basis == "scouting_only":
        parts.append("GRADE-AND-AGE match only (no minor-league record yet)")
    n_never = int(dist.get("comp_n_never_reached", 0))
    parts.append(f"{n_never} of {k} comps never reached MLB")
    tail = [f"{int(dist.get(f'comp_n_{t}', 0))} {_TIER_LABELS[t]}"
            for t in ("fringe", "regular", "impact") if int(dist.get(f"comp_n_{t}", 0)) > 0]
    if tail:
        parts.append("; ".join(tail))
    band = dist.get("comp_band_quantiles", "p10-p90")
    parts.append(f"3-yr dynasty pts {band} {dist.get('comp_band_lo')}–{dist.get('comp_band_hi')} "
                 f"(median {dist.get('comp_fp_median')})")
    if quality == "thin":
        parts.append("THIN comp set — band widened, read as a range not a projection")
    return ". ".join(parts) + "."


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The engine
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class CompConfig:
    """A pre-registered arm of the comp engine. The defaults ARE the shipped configuration."""
    k: int = DEFAULT_K
    metric: str = "gower"
    weights: dict[str, float] | None = None      # None → FEATURE_WEIGHTS[player_type]
    features: tuple[str, ...] | None = None
    hard_position_filter: bool = True
    #: ⚠️ EQUAL-WEIGHT IS THE SHIPPED DEFAULT, AND THAT IS A PHASE-2 FINDING, NOT AN OVERSIGHT.
    #: The tricube similarity kernel is the intuitive PECOTA-flavoured choice (weight a comp by how
    #: similar it is) and it is genuinely better at a POINT estimate — but it OVER-SHARPENS the
    #: predictive, and the band is the honest half of this display. Measured on the E7.13 Phase-2
    #: backtest, batters, k=15: similarity-weighted CRPS 69.03 vs equal-weight **65.27**, randomized
    #: -PIT max-decile-deviation 0.0767 (FAILS the pre-registered 0.05 flatness constraint) vs
    #: **0.0426**, and p10–p90 coverage 0.764 vs **0.831** against a nominal 0.80 FLOOR. The
    #: pitcher side agrees (106.98 → 99.88; 0.0653 → 0.0409; 0.763 → 0.834).
    #: Ordering of the NAMED comps is by distance either way, so this changes the band and the
    #: median, not who the comps are. `tricube_weights` stays available and is still reported.
    similarity_weighted: bool = False
    min_pair_coverage: float = MIN_PAIR_COVERAGE
    min_component_coverage: float = MIN_COMPONENT_COVERAGE
    #: features counted toward `min_component_coverage`; None → COMPONENT_FEATURES[player_type]
    component_features: tuple[str, ...] | None = None
    #: label carried onto every row this config produces
    basis: str = "full"
    #: 'nearest' (the engine), 'random' (the matched placebo — same machinery, similarity
    #: destroyed), 'oracle' (the peeking floor — neighbours by realized-outcome proximity).
    neighbour_rule: str = "nearest"
    name: str = "comp_gower_k15"
    seed: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


def _quality(mean_distance: float, query_coverage: float, k_used: int,
             cuts: tuple[float, float]) -> str:
    if k_used < MIN_COMPS or query_coverage < MIN_QUERY_COVERAGE:
        return "thin"
    if not np.isfinite(cuts[0]):
        return "fair"
    if mean_distance <= cuts[0]:
        return "strong"
    if mean_distance <= cuts[1]:
        return "fair"
    return "thin"


def _neighbour_order(d_row: np.ndarray, eligible: np.ndarray, cfg: CompConfig,
                     pool: pd.DataFrame, rng: np.random.Generator,
                     query_outcome: float | None) -> np.ndarray:
    idx = np.flatnonzero(eligible)
    if idx.size == 0:
        return idx
    if cfg.neighbour_rule == "random":
        return rng.permutation(idx)
    if cfg.neighbour_rule == "oracle":
        # ⚠️ THE PEEKING FLOOR — same family, same k, same eligible set (NF1.7(b)/NF1.9(f): an
        # oracle is a floor only at MATCHED capacity). It chooses neighbours by proximity in the
        # REALIZED outcome, which no production arm can do. Nothing may beat it; a real arm that
        # does means the scoring metric is inverted, not that the arm is good.
        if query_outcome is None:
            return idx[np.argsort(d_row[idx], kind="stable")]
        y = pool["fantasy_points"].to_numpy(float)[idx]
        return idx[np.argsort(np.abs(y - float(query_outcome)), kind="stable")]
    return idx[np.argsort(d_row[idx], kind="stable")]


def _dedupe_by_person(order: np.ndarray, pool_keys: np.ndarray | None, k: int) -> np.ndarray:
    """Take the k nearest DISTINCT PEOPLE, not the k nearest pool ROWS.

    🚨 A CORRECTNESS FIX, NOT A COSMETIC ONE. The pool is one row per (board season, prospect), so a
    player who sat on the board for five years contributes five rows — and they are near-identical,
    so if one is a neighbour they usually all are. Measured on the live 2026 board before this fix:
    a prospect's 15-comp set repeated the same PERSON 1.7 times on average and up to **7 times**,
    which means one man's single career was carrying 47% of that prospect's outcome distribution
    and 47% of the bust rate. The display symptom ("Bo Bichette (0.04), Gleyber Torres (0.05), Bo
    Bichette (0.05)") is the visible tip of a distribution that had silently stopped being an
    average over 15 careers.

    Keeps each person's CLOSEST board season, which is also the right answer for the display: the
    comp is "the season of his career that most resembles this prospect", not an arbitrary one.
    """
    if pool_keys is None or order.size == 0:
        return order[:k]
    seen: set[str] = set()
    keep: list[int] = []
    for j in order:
        key = pool_keys[j]
        if key in seen:
            continue
        seen.add(key)
        keep.append(int(j))
        if len(keep) >= k:
            break
    return np.asarray(keep, dtype=int)


def find_comps(query: pd.DataFrame, pool: pd.DataFrame, stats: PoolStats,
               cfg: CompConfig | None = None, *,
               exclude_key_col: str | None = "comp_key",
               query_outcome_col: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score every query row against the pool. Returns (summary, detail).

    `summary` — one row per query row: the comp names, the outcome distribution, the coverage flags.
    `detail`  — one row per (query row, comp): name, distance, realized outcome, tier. This is the
                audit trail; a comp that looks wrong on the board is traceable to its features here.

    `exclude_key_col` purges a player from his OWN comp set — the same person appears in several
    board seasons of the pool, and a prospect comping to his own past self is a tautology that
    would also be his single closest neighbour.
    """
    cfg = cfg or CompConfig()
    rng = np.random.default_rng(cfg.seed)
    feats = cfg.features or stats.features
    weights = np.array([(cfg.weights or stats.weights)[f] for f in feats], dtype=float)
    st = PoolStats(player_type=stats.player_type, features=tuple(feats),
                   weights=(cfg.weights or stats.weights), center=stats.center, scale=stats.scale,
                   level_age_median=stats.level_age_median, tier_cuts=stats.tier_cuts,
                   quality_cuts=stats.quality_cuts, n_pool=stats.n_pool)

    pool_z = standardize(pool, st)
    query_z = standardize(query, st)
    inv_cov = None
    if cfg.metric == "mahalanobis":
        cov = np.cov(np.nan_to_num(pool_z, nan=0.0), rowvar=False)
        cov = np.atleast_2d(cov) + np.eye(len(feats)) * 1e-6
        inv_cov = np.linalg.pinv(cov)
    dist, cov_frac = distance_matrix(query_z, pool_z, weights, metric=cfg.metric, inv_cov=inv_cov)

    # COMPONENT-block coverage per pair — the load-bearing second floor. See MIN_COMPONENT_COVERAGE.
    comp_feats = (cfg.component_features if cfg.component_features is not None
                  else COMPONENT_FEATURES.get(stats.player_type, ()))
    comp_idx = [j for j, f in enumerate(feats) if f in set(comp_feats)]
    if comp_idx and cfg.min_component_coverage > 0:
        cw = weights[comp_idx]
        comp_cov = ((~np.isnan(query_z[:, comp_idx])).astype(float) * cw) @ \
            (~np.isnan(pool_z[:, comp_idx])).astype(float).T
        comp_cov = comp_cov / max(float(cw.sum()), 1e-12)
    else:
        comp_cov = np.ones_like(dist)

    pool_tier = [outcome_tier(fp, db, st.tier_cuts)
                 for fp, db in zip(pool["fantasy_points"], pool["debuted"])]
    pool_fp = pool["fantasy_points"].to_numpy(float)
    pool_deb = pool["debuted"].to_numpy(bool)
    pool_names = pool.get("player_name", pd.Series(pool.index.astype(str))).astype(str).to_numpy()
    pool_season = pool["board_season"].astype("Int64").to_numpy()
    pool_group = pool["position_group"].astype(str).to_numpy()
    pool_keys = (pool[exclude_key_col].astype(str).to_numpy()
                 if exclude_key_col and exclude_key_col in pool.columns else None)

    q_keys = (query[exclude_key_col].astype(str).to_numpy()
              if exclude_key_col and exclude_key_col in query.columns else None)
    q_group = query["position_group"].astype(str).to_numpy()
    q_outcome = (query[query_outcome_col].to_numpy(float)
                 if query_outcome_col and query_outcome_col in query.columns else None)

    # how much of its OWN profile each query row observes
    q_obs = ~np.isnan(query_z)
    q_coverage = (q_obs.astype(float) @ weights) / max(float(weights.sum()), 1e-12)

    summaries, details = [], []
    for i in range(len(query)):
        base = (np.isfinite(dist[i]) & (cov_frac[i] >= cfg.min_pair_coverage)
                & (comp_cov[i] >= cfg.min_component_coverage))
        eligible = base.copy()
        if cfg.hard_position_filter:
            eligible &= (pool_group == q_group[i])
            if eligible.sum() < MIN_COMPS:
                # relax to the whole player type rather than emit a false-precise 3-comp read;
                # the fallback is recorded so the board can say the filter was widened.
                eligible = base.copy()
                relaxed = True
            else:
                relaxed = False
        else:
            relaxed = False
        if pool_keys is not None and q_keys is not None:
            eligible &= (pool_keys != q_keys[i])

        order = _neighbour_order(dist[i], eligible, cfg, pool, rng,
                                 None if q_outcome is None else float(q_outcome[i]))
        sel = _dedupe_by_person(order, pool_keys, cfg.k)
        if sel.size == 0:
            summaries.append({"comp_k": 0, "comp_quality": "none", "comp_basis": cfg.basis,
                              "comp_relaxed_position": relaxed,
                              "comp_query_coverage": round(float(q_coverage[i]), 3),
                              "comp_names": "", "comp_note": comp_note({"comp_k": 0}, "none")})
            continue

        d_sel = dist[i][sel]
        mean_d = float(np.mean(d_sel))
        thin_pre = (sel.size < MIN_COMPS) or (q_coverage[i] < MIN_QUERY_COVERAGE)
        quality = _quality(mean_d, float(q_coverage[i]), int(sel.size), stats.quality_cuts)
        if cfg.basis != "full":
            # a grade-and-age match is never 'strong', however close the two numbers are
            quality = "thin"
        dist_summary = comp_distribution(pool_fp[sel], pool_deb[sel],
                                         [pool_tier[j] for j in sel], d_sel,
                                         thin=(quality == "thin" or thin_pre),
                                         similarity_weighted=cfg.similarity_weighted)
        row = dict(dist_summary)
        row["comp_quality"] = quality
        row["comp_basis"] = cfg.basis
        row["comp_relaxed_position"] = bool(relaxed)
        row["comp_query_coverage"] = round(float(q_coverage[i]), 3)
        row["comp_names"] = format_comp_names(pool_names[sel], d_sel, n=3)
        row["comp_names_5"] = format_comp_names(pool_names[sel], d_sel, n=5)
        row["comp_note"] = comp_note(row, quality, basis=cfg.basis)
        summaries.append(row)

        for rank, j in enumerate(sel, start=1):
            details.append({
                "query_index": int(i),
                "comp_rank": rank,
                "comp_name": pool_names[j],
                "comp_board_season": (int(pool_season[j]) if pool_season[j] is not pd.NA
                                      and pd.notna(pool_season[j]) else None),
                "comp_position_group": pool_group[j],
                "distance": round(float(dist[i][j]), 4),
                "pair_coverage": round(float(cov_frac[i][j]), 3),
                "comp_debuted": bool(pool_deb[j]),
                "comp_fantasy_points": round(float(pool_fp[j]), 1),
                "comp_outcome_tier": pool_tier[j],
            })

    summary = pd.DataFrame(summaries, index=query.index)
    detail = pd.DataFrame(details)
    return summary, detail


def calibrate_quality_cuts(pool: pd.DataFrame, stats: PoolStats,
                           cfg: CompConfig | None = None,
                           *, sample: int = 400, seed: int = 0) -> tuple[float, float]:
    """The `comp_quality` thresholds, read off the POOL's own leave-one-out distances.

    A hand-picked "0.15 is a close comp" would be a taste call about a unit nobody has intuition
    for. Instead: comp a sample of the pool AGAINST the pool, and let the resulting mean-distance
    distribution define 'strong' (≤ p50) and 'fair' (≤ p90). A query is then graded against how
    well players in this feature space typically match, which is the only reference that exists.
    """
    cfg = cfg or CompConfig()
    rng = np.random.default_rng(seed)
    n = len(pool)
    idx = np.arange(n) if n <= sample else rng.choice(n, size=sample, replace=False)
    probe = pool.iloc[np.sort(idx)]
    summary, _ = find_comps(probe, pool, stats, cfg)
    md = pd.to_numeric(summary.get("comp_mean_distance"), errors="coerce").dropna()
    if len(md) < 20:
        return (float("nan"), float("nan"))
    return (float(md.quantile(0.50)), float(md.quantile(0.90)))


def _scouting_only_pass(board: pd.DataFrame, pool: pd.DataFrame, stats: PoolStats,
                        cfg: CompConfig, need: np.ndarray,
                        exclude_key_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Second pass for board rows the performance-based engine could not comp at all.

    Restricted to pool rows that ALSO lack a component line, so the comparison is symmetric — both
    sides are known only by grade and age. Comping a record-less prospect against players who DO
    have a record would compute the distance over the handful of fields the record-less pool rows
    happen to share, which is how the FV-bucket-at-distance-zero defect arose in the first place.
    """
    comp_feats = COMPONENT_FEATURES.get(stats.player_type, ())
    lineless = pool[list(comp_feats)].isna().all(axis=1) if comp_feats else pd.Series(True,
                                                                                      index=pool.index)
    sub_pool = pool.loc[lineless].reset_index(drop=True)
    empty = (pd.DataFrame(index=board.index[need]), pd.DataFrame())
    if len(sub_pool) < MIN_COMPS:
        return empty
    fb_cfg = CompConfig(k=cfg.k, metric="gower", weights=dict(SCOUTING_ONLY_WEIGHTS),
                        features=SCOUTING_ONLY_FEATURES, hard_position_filter=True,
                        similarity_weighted=cfg.similarity_weighted, min_pair_coverage=0.99,
                        min_component_coverage=0.0, component_features=(),
                        basis="scouting_only", name=f"{cfg.name}_scouting_only", seed=cfg.seed)
    fb_stats = fit_pool_stats(sub_pool, player_type=stats.player_type,
                              features=SCOUTING_ONLY_FEATURES, weights=SCOUTING_ONLY_WEIGHTS)
    fb_stats = PoolStats(**{**fb_stats.__dict__, "tier_cuts": stats.tier_cuts,
                            "quality_cuts": stats.quality_cuts})
    return find_comps(board.loc[need], sub_pool, fb_stats, fb_cfg,
                      exclude_key_col=exclude_key_col)


def attach_comps(board: pd.DataFrame, pool: pd.DataFrame, *, player_type: str,
                 as_of_season: int, cfg: CompConfig | None = None,
                 exclude_key_col: str = "comp_key",
                 scouting_only_fallback: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """End-to-end for one player type: mature the pool, fit, calibrate, comp.

    Returns (board-with-comp-columns, detail frame, report dict).
    """
    cfg = cfg or CompConfig()
    mp = matured_pool(pool, as_of_season=as_of_season)
    report = validate_pool(mp)
    report.update({"player_type": player_type, "as_of_season": int(as_of_season),
                   "config": cfg.name, "k": cfg.k, "metric": cfg.metric})
    stats = fit_pool_stats(mp, player_type=player_type,
                           features=cfg.features, weights=cfg.weights)
    cuts = calibrate_quality_cuts(mp, stats, cfg)
    stats = PoolStats(player_type=stats.player_type, features=stats.features,
                      weights=stats.weights, center=stats.center, scale=stats.scale,
                      level_age_median=stats.level_age_median, tier_cuts=stats.tier_cuts,
                      quality_cuts=cuts, n_pool=stats.n_pool)
    report["quality_cuts"] = [None if not np.isfinite(c) else round(c, 4) for c in cuts]
    report["tier_cuts_debuted_p50_p85"] = [round(c, 1) for c in stats.tier_cuts]
    report["feature_weights"] = {f: round(stats.weights[f], 4) for f in stats.features}

    summary, detail = find_comps(board, mp, stats, cfg, exclude_key_col=exclude_key_col)
    details = [_label_detail(detail, board, np.arange(len(board)))]

    need = (summary["comp_k"].fillna(0).astype(int) == 0).to_numpy()
    report["scouting_only_rows"] = int(need.sum())
    if scouting_only_fallback and need.any():
        fb_summary, fb_detail = _scouting_only_pass(board, mp, stats, cfg, need, exclude_key_col)
        if not fb_summary.empty:
            for col in fb_summary.columns:
                if col not in summary.columns:
                    summary[col] = pd.NA
            summary.loc[fb_summary.index, fb_summary.columns] = fb_summary.values
            details.append(_label_detail(fb_detail, board, np.flatnonzero(need)))
        report["scouting_only_comped"] = int((fb_summary.get("comp_k", pd.Series(dtype=float))
                                              .fillna(0) > 0).sum()) if not fb_summary.empty else 0

    out = pd.concat([board, summary], axis=1)
    report["comp_quality"] = summary.get("comp_quality", pd.Series(dtype=object)) \
        .value_counts().to_dict()
    report["comp_basis"] = summary.get("comp_basis", pd.Series(dtype=object)) \
        .value_counts().to_dict()
    report["rows_scored"] = int(len(board))
    detail_all = pd.concat([d for d in details if not d.empty], ignore_index=True) \
        if any(not d.empty for d in details) else pd.DataFrame()
    return out, detail_all, report


def _label_detail(detail: pd.DataFrame, board: pd.DataFrame,
                  row_positions: np.ndarray) -> pd.DataFrame:
    """Map a detail frame's positional `query_index` back onto the board's identity columns."""
    if detail is None or detail.empty:
        return pd.DataFrame()
    d = detail.copy()
    pos = row_positions[d["query_index"].to_numpy()]
    for col in ("player_name", "mlbam_id", "org", "position"):
        if col in board.columns:
            d[f"query_{col}"] = board[col].to_numpy()[pos]
    return d


def comp_detail_frame(details: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Stack the per-type detail frames into the board's `Comps` tab."""
    frames = [d for d in details if d is not None and not d.empty]
    if not frames:
        return pd.DataFrame(columns=["query_player_name", "comp_rank", "comp_name", "distance"])
    out = pd.concat(frames, ignore_index=True)
    front = [c for c in ("query_player_name", "query_mlbam_id", "comp_rank", "comp_name",
                         "comp_board_season", "distance", "pair_coverage", "comp_position_group",
                         "comp_debuted", "comp_outcome_tier", "comp_fantasy_points")
             if c in out.columns]
    return out[front + [c for c in out.columns if c not in front]]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The QUERY side — building a current-board prospect's profile in the POOL's own units
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# 🚨 THE APPLES-TO-ORANGES TRAP THIS EXISTS TO CLOSE. The pool's `minor_k_pct` is the player's
# CAREER-TO-DATE line across EVERY level, summed over all his MiLB games strictly before the board
# date (E7.8's construction). The E7.3 pairs table's `minor_k_pct` is a career-AT-ONE-LEVEL line.
# They are different aggregations of the same games, and a distance computed with one on each side
# is a systematic bias dressed as a similarity — a Triple-A-only line and an all-levels line differ
# by exactly the lower-level performance the pool row includes and the query row does not.
#
# So the query profile is rebuilt from the pairs table's RAW BOX COUNTS, summed across levels, and
# run through the SAME `compute_rate_metrics_from_counts` the pool used. One formula home, one
# aggregation, on both sides.

_BAT_SUM_COLS = (
    "bat_plate_appearances", "bat_at_bats", "bat_hits", "bat_doubles", "bat_triples",
    "bat_home_runs", "bat_walks", "bat_intentional_walks", "bat_hit_by_pitch", "bat_sac_flies",
    "bat_strike_outs", "bat_total_bases",
)
_PIT_SUM_COLS = (
    "pit_batters_faced", "pit_strike_outs", "pit_walks", "pit_home_runs",
    "pit_ground_outs", "pit_air_outs", "pit_games_played", "pit_games_started",
)


def collapse_pairs_to_career_line(pairs: pd.DataFrame, *, player_type: str,
                                  key: str = "player_id") -> pd.DataFrame:
    """One career-to-date MiLB line per player, in the POOL's units.

    Also derives the two structural fields the pool builds from game logs:
      * `comp_level` — the level of the player's MOST RECENT MiLB season (matching the pool's
        `top_level_pre_board`, which is the level at his last pre-board game), ties broken by the
        higher level;
      * `first_minor_season` — the pedigree anchor for `pro_experience_years`.
    """
    from betting_ml.scripts.milb_mle.milb_mle import (       # one formula home (pure module)
        compute_pitcher_rate_metrics_from_counts, compute_rate_metrics_from_counts,
    )
    if pairs.empty:
        return pd.DataFrame(columns=[key])
    cols = _BAT_SUM_COLS if player_type == "batter" else _PIT_SUM_COLS
    df = pairs.copy()
    df[key] = df[key].astype(str)
    for c in cols:
        df[c] = pd.to_numeric(df.get(c), errors="coerce").fillna(0.0)
    agg = df.groupby(key, as_index=False)[list(cols)].sum()

    lvl = df.copy()
    lvl["_lr"] = lvl["level"].map(level_rank)
    lvl["_last"] = pd.to_numeric(lvl.get("last_minor_season"), errors="coerce")
    lvl = lvl.sort_values([key, "_last", "_lr"], na_position="first")
    top = lvl.groupby(key, as_index=False).tail(1)[[key, "level"]].rename(
        columns={"level": "_top_level"})
    first = df.groupby(key, as_index=False).agg(
        first_minor_season=("first_minor_season", "min"),
        last_minor_season=("last_minor_season", "max"))

    out = agg.merge(top, on=key, how="left").merge(first, on=key, how="left")
    out = (compute_rate_metrics_from_counts(out) if player_type == "batter"
           else compute_pitcher_rate_metrics_from_counts(out))
    out["comp_level"] = out["_top_level"].map(level_from_token)
    return out.drop(columns=["_top_level"])


def build_query_profile(board: pd.DataFrame, career: pd.DataFrame, *, player_type: str,
                        as_of_season: int, id_col: str = "mlbam_id",
                        career_key: str = "player_id") -> pd.DataFrame:
    """Attach the pool-comparable feature columns to a slice of the current board.

    `comp_level` prefers the game-log-derived level (identical construction to the pool's) and falls
    back to the board's own level token — which, for a CURRENT prospect, genuinely is as-of and
    carries no hindsight. A board row whose level reads `MLB` yields None from `level_from_token`
    and keeps the game-log level, so an already-graduated player is compared on his last MINOR
    level rather than being ranked above Triple-A on the strength of having arrived.
    """
    df = board.copy()
    df["_id"] = pd.to_numeric(df.get(id_col), errors="coerce").astype("Int64").astype(str)
    car = career.copy()
    car[career_key] = car[career_key].astype(str)
    keep = [career_key, "comp_level", "minor_pa", "first_minor_season"] + [
        c for c in ("minor_k_pct", "minor_bb_pct", "minor_iso", "minor_woba",
                    "minor_gb_pct", "minor_hr_rate", "minor_start_share") if c in car.columns]
    df = df.merge(car[keep], left_on="_id", right_on=career_key, how="left")

    df["comp_level"] = df["comp_level"].fillna(df.get("level", pd.Series(index=df.index))
                                               .map(level_from_token))
    df["level_rank"] = df["comp_level"].map(lambda k: float(COMP_LEVEL_RANK[k]) if k else np.nan)
    df["age"] = pd.to_numeric(df.get("age"), errors="coerce")
    df["fv"] = pd.to_numeric(df.get("fv"), errors="coerce")
    df["pro_experience_years"] = (int(as_of_season)
                                  - pd.to_numeric(df.get("first_minor_season"), errors="coerce"))
    df["position_group"] = [
        position_group(p, player_type, s)
        for p, s in zip(df.get("position", pd.Series(index=df.index, dtype=object)),
                        df.get("minor_start_share", pd.Series(index=df.index, dtype=float)))
    ]
    df["comp_key"] = df["_id"]
    return df.drop(columns=["_id", career_key], errors="ignore")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. FEEDING THE RANKING — the comp term inside `model_score`, and the re-sort
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐ THIS IS THE ONE PLACE A COMP NUMBER TOUCHES THE ORDER YOU DRAFT IN, so the weight and the shape
# are both measured, and the shape is the more important of the two.
#
# 🚨 `board_rank` IS NOT SORTED BY `blend_score`. It is a LEXICOGRAPHIC sort — `fv` first,
# `model_score` as the tiebreak, `blend_score` third (`board_assembly.assemble_board`). Since FV is
# reported on a coarse 5-point grid, almost the whole board is a tie on the first key and the
# TIEBREAK does the real ordering work. Two consequences that decided this implementation:
#
#   1. Adding a comp term to `blend_score` alone would barely move the board — it is the third key.
#      The comp term therefore enters **`model_score`**, which is the key that actually sorts.
#   2. Re-sorting the board by `blend_score + comp` instead (abandoning FV-first) tested BETTER on
#      batters (+0.042 IC on the clean fold) but was UNSTABLE on pitchers (−0.036 on one fold), and
#      plain `blend_score` is measurably WORSE than the FV-first sort almost everywhere — E8.0's
#      lexicographic design is doing real work. So the FV-first shape is KEPT and only the tiebreak
#      changes. Conservative, and it is the variant that never loses.
#
# 📊 MEASURED (E7.13 Phase-2 ordering study, Spearman rank-IC vs realized 3-yr dynasty value;
#    `run_e7_13_comp_validation.py` → `ordering`). ΔIC of `lex(fv, model+comp)` vs the incumbent
#    `lex(fv, model, blend)`:
#
#      batters   matured zero-overlap fold +0.0101 · relaxed 2019–22 +0.0014 / +0.0115 / +0.0169 / +0.0192
#      pitchers  matured zero-overlap fold +0.0192 · relaxed 2019–22 +0.0328 / +0.0055 / +0.0235 / +0.0192
#
#    **Positive in 10 of 10 fold×type combinations, never negative**, including the single
#    STRICTLY-MATURED fold whose comp pool has ZERO outcome-window overlap with the query — so the
#    effect is not the era artifact the relaxed folds are exposed to. That matured fold is the load-
#    bearing evidence here, because unlike the CRPS study the ordering incumbent does NOT read the
#    comp pool at all, so the "every arm shares the hindsight" argument does NOT apply and the
#    overlap had to be ruled out directly.
#
# ⚠️ WHAT THE SAME STUDY REFUTED: on the relaxed folds `comp_only` ordered BETTER than everything
#    (batter IC 0.566 vs 0.473) and would have said "replace the board's formula with comps". On the
#    zero-overlap fold that advantage COLLAPSED — batters 0.5205, now below the blends; pitchers
#    0.2377, below the incumbent outright. **The replacement was an era artifact; the blend is not.**
COMP_RANK_WEIGHT = 0.30


def attach_comp_ranking(board: pd.DataFrame, *,
                        weight: float = COMP_RANK_WEIGHT) -> pd.DataFrame:
    """Mix the comp read into `model_score`, then re-sort the board on the E8.0 lexicographic keys.

    ⭐ THIN DELEGATE (E8.1, 2026-08-02). The implementation moved to
    `board_assembly.apply_comp_term` — scoring belongs to the scoring module, and E7.13's ordering
    had been reachable ONLY through this module's separate re-export script, so a plain
    `build_prospect_board.py` rebuild silently produced the PRE-comp order. `build_prospect_board.py`
    now applies the same term natively.

    This stays as the public E7.13 name (its callers and its measured evidence above are unchanged)
    and delegates rather than reimplementing, so the native path and this one cannot drift apart —
    "byte-for-byte identical" is then a structural property, not a claim a test has to keep re-proving
    against two copies of the arithmetic.
    """
    from betting_ml.scripts.prospect_board.board_assembly import apply_comp_term

    return apply_comp_term(board, weight=weight)


#: The board columns this module contributes, in display order.
COMP_COLUMNS: tuple[str, ...] = (
    "comp_rank_delta", "comp_score", "comp_names", "comp_note", "comp_quality", "comp_basis", "comp_k",
    "comp_bust_rate", "comp_fp_median", "comp_band_lo", "comp_band_hi", "comp_band_quantiles",
    "comp_n_never_reached", "comp_n_fringe", "comp_n_regular", "comp_n_impact",
    "comp_mean_distance", "comp_min_distance", "comp_query_coverage", "comp_relaxed_position",
    "comp_names_5", "comp_p_debut", "comp_fp_p10", "comp_fp_p25", "comp_fp_p75", "comp_fp_p90",
    "comp_fp_median_simweighted",
)
