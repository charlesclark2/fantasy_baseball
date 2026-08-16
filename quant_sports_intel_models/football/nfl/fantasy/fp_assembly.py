"""fp_assembly.py — NF-W7c: the ARBITRARY-LEAGUE re-scoring ASSEMBLY (pure).

THE STORY IN ONE PARAGRAPH. NF-W6d completed the per-STAT distribution substrate — 52 (position,
stat) cells, one calibrated quantile bank per cell. What the optimizer and the "what might this
player do this week" surface actually need is a per-PLAYER fantasy-POINT distribution *under a
SPECIFIC league's scoring*. That is an ASSEMBLY: draw a player's 13 scored stats JOINTLY, score
each draw with the league's own rules, read the resulting point distribution. The joint half is the
whole difficulty — carries / rushing yards / rushing TDs co-move, and NF-W7 measured what happens
when they are drawn independently: the assembled sum UNDER-DISPERSES and fails its coverage floor,
and NF-W7b then measured that fixing it is a FREE CRPS WIN (+0.0273 vs the refused independent
arm), not a coverage-for-score trade. So independence here is a MEASURED, REFUSED simplification —
never a benign default — and this story registers a matched independent foil that must LOSE.

⭐ THE ESTIMATOR IS RAW OUTCOME RANKS, NOT RESIDUAL PITs — AND IT IS EARNED, NOT INHERITED.
NF-W7b's `joint_double` (an ×2 attenuation probe registered as a REAL arm) BEAT the model-residual
PIT estimator, confirming that randomized-PIT z-scores systematically UNDER-estimate dependence on
zero-heavy discrete margins. The 13 legs here are far more zero-heavy than DST's (a WR's carries, a
QB's receptions, everyone's two_pt), so the same attenuation is expected — but it is REGISTERED as
a contest (`joint_pit` is in the field as a real arm, not assumed dead), because carrying a finding
forward as an assumption is how a measured result becomes folklore.

⛔ NO FOURTH SCORER. Option C (NF-EPIC 1) already put ONE scoring policy in three implementations
(`fantasy_engine` / the browser TS port / the Lambda), guarded by a merge-gate parity test. This
module does NOT add a fourth: it calls `ScoringRules.points_for` — the authority itself — to build a
per-position WEIGHT VECTOR, and fantasy points are then the linear form `w · x` that
`fantasy_engine.scoring.score_players` computes by construction. `test_nf_w7c_fp_assembly.py`
proves that equality exactly on real payload rows, so a scoring-rule change moves the three
implementations exactly as before and this assembly follows for free. That is why NF-W7c costs no
parity tax: it REUSES the policy rather than restating it.

⭐ LABELLING CARRIES, AND IT CARRIES ONLY WHERE IT BITES. NF-W6d's `PROMOTE_BLOCKERS` bind the
assembly directly: a Phase-C DEFAULT cell is a calibrated range, not a conditional projection, and
"the assembly consumer must read `source`/`calibration_warning`". An assembled distribution
therefore surfaces the sources of the legs it is actually BUILT from — which is exactly the legs
the league PRICES, because a leg with weight 0 contributes identically 0 to every draw and cannot
influence the answer. A default on an unpriced leg is not a caveat, it is noise; a default on a
priced leg is a caveat and is surfaced. Both directions are guarded.

⚠️ AND THE GAP THAT MUST NEVER BE SILENT. The substrate covers 13 stats. A league may price terms
outside it — a per-completion bonus, the NF-C0e long-touchdown bonuses — and scoring those as 0
would UNDER-state fantasy points with no signal anywhere (the NF-C0e "wired ≠ invoked" /
silently-dropped-field class, on the assembly side). `unpriced_scored_terms` names them and
`assemble_player_frame` REFUSES by default; the K/DST terms are partitioned off separately because
they are structurally inapplicable to a QB/RB/WR/TE, not a coverage gap.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: promotes nothing,
publishes nothing, retrains nothing. Every emitted string is a calibrated RANGE — never an edge /
ROI / win-rate claim.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w7c_fp_assembly.py`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig
from quant_sports_intel_models.football.nfl.fantasy import joint_draw as JD
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import stat_distribution_serving_d as SDSD
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W7c"
TARGET = "league_fantasy_points"
SELECTION_METRIC = "crps_q199"
EVAL_LEVELS: np.ndarray = MC.EVAL_LEVELS
N_LEVELS = int(len(EVAL_LEVELS))
#: ⭐ FRESH registration ⇒ fresh seed, deliberately ≠ every upstream story's.
_SEED = 20260818

TEST_BLOCKS = WP.TEST_BLOCKS                     # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
POSITIONS: tuple[str, ...] = tuple(SDD.POSITIONS)

#: The assembly legs, in a FIXED order — the NF-W6d substrate's own 13 scored weekly stats,
#: imported (never re-typed: a second copy is the NF-C0e wrong-key class).
LEGS: tuple[str, ...] = tuple(SDD.ALL_STATS)
N_LEGS = len(LEGS)

# ── The one mapping this story introduces: a substrate leg → the league's canonical stat key ────
#: ⚠️ This is a NAME MAP, not a scoring rule — it names which `LeagueConfig` term each modeled
#: stat IS. It is pinned three ways (`assert_stat_key_map`): exhaustive over `SDD.ALL_STATS`,
#: injective, and its image lives inside `NFL_PROFILE.stat_columns`. The guard additionally pins
#: it against the backend/frontend `STAT_FIELD` mirrors, so a canonical key renamed in one of the
#: three scoring implementations goes RED here rather than silently unpricing a leg.
STAT_KEY: dict[str, str] = {
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
    "fumbles_lost": "fumbles_lost",
    "two_pt": "two_pt",
}

#: Legs whose realized value is an INTEGER count/event — draws are rounded so the assembled sum
#: inherits the target's true lattice (a fractional reception would smear the atom the W6d
#: constructions exist to price). Yardage legs stay continuous.
INTEGER_LEGS: frozenset[str] = frozenset(LEGS) - {"passing_yards", "rushing_yards",
                                                  "receiving_yards"}

#: ⚠️ SCORED BY SOME LEAGUES, NOT IN THE SUBSTRATE — applicable to a skill position, so a league
#: pricing one of these has a REAL coverage gap the assembly must NAME (never score as 0).
SKILL_UNMODELED_KEYS: tuple[str, ...] = (
    "pass_cmp",                                   # per-completion bonus leagues
    "pass_td_40p", "rush_td_40p", "rec_td_40p",   # the NF-C0e long-touchdown bonus terms
)
#: Structurally INAPPLICABLE to QB/RB/WR/TE (a quarterback accrues no field goals and no sacks):
#: pricing them is not a gap in this substrate, it is a different position's line. Derived, so a
#: new K/DST term cannot quietly land in the "gap" bucket or vice versa.
OUT_OF_SCOPE_KEYS: tuple[str, ...] = tuple(sorted(
    set(LP.NFL_PROFILE.stat_columns) - set(STAT_KEY.values()) - set(SKILL_UNMODELED_KEYS)))

# ── The declared dependence field (⛔ never trimmed or grown after a score — MH2 (a)) ────────────
#: joint_rank   — ⭐ THE PRE-REGISTERED PRIMARY. Gaussian copula whose Σ̂ is the Spearman rank
#:                correlation of RAW per-leg outcomes, mapped to the copula scale by
#:                2·sin(π·ρs/6), estimated PER POSITION on TRAIN rows only.
#: joint_factor — the nearest ONE-FACTOR structure of that Σ̂ (one shared latent: game script /
#:                pace / opponent, which every leg loads on with a free sign).
#: joint_pit    — Σ̂ from randomized-PIT latent z-scores under the frozen W6d marginals (the
#:                model-RESIDUAL scale). Registered as a REAL ARM so the raw-rank choice is
#:                EARNED on this population rather than inherited from NF-W7b's finding.
#: joint_double — raw-rank Σ̂ off-diagonals ×2, PSD-repaired: the magnitude/attenuation probe,
#:                a REAL arm (NF-D20 — an under-correcting estimator must not be able to hide
#:                behind an anchor's ineligibility).
REAL_ARMS: tuple[str, ...] = ("joint_rank", "joint_factor", "joint_pit", "joint_double")
PRIMARY_ARM = "joint_rank"
DOUBLE_SCALE = 2.0

#: ⭐ THE MATCHED INDEPENDENT FOIL — the card's binding requirement, and the reason it is a FOIL
#: rather than an anchor: the gate's `beats_foil` clause then IS "the correlation earned its
#: place". It shares the base normals with every arm (common random numbers), so the difference
#: is dependence and nothing else. `foil_direct_points` is the second foil: a learner pointed
#: straight at league points, which asks whether assembling from per-stat parts beats modelling
#: the total — without it, "the assembly wins" would only ever be measured against itself.
FOILS: tuple[str, ...] = ("assembled_indep", "foil_direct_points")
ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *FOILS)

#: Degenerates — ALL SCORED, ALL registered to LOSE the metric (NF1.8 / NF-D14: never reasoned
#: about). `assembled_comonotone` is the over-correlated ceiling: it will trivially SATISFY the
#: coverage floor (a constraint a degenerate satisfies is fine — the metric eliminates it) and
#: must lose the score contest. Scoring it is what PROVES the floor was not promoted into a
#: selection criterion (NF-D18).
DEGENERATES: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width",
                                "assembled_comonotone")
#: ⛔ `assembled_indep` deliberately has NO oracle. Every arm here differs only in Σ, and the
#: independent draw ESTIMATES NOTHING — so a peek has nothing to improve and its "oracle" would be
#: byte-identical to the arm itself. An anchor that cannot differ from what it anchors is décor,
#: and scoring it as "respected" is a pass on nothing (NF1.7 (a) / NF1.9's "a mechanism that
#: cannot act is a finding"). `foil_direct_points` is a real learner and DOES carry one.
FOILS_WITH_ORACLE: tuple[str, ...] = ("foil_direct_points",)
ANCHORS: tuple[str, ...] = (
    *DEGENERATES, "permuted_direct",
    *(f"oracle__{a}" for a in REAL_ARMS), *(f"matched_n__{a}" for a in REAL_ARMS),
    *(f"oracle__{f}" for f in FOILS_WITH_ORACLE),
)

#: One family per position — corrected within itself AND pooled; the STRICTER binds (MH2 (a)),
#: so no verdict turns on the family choice.
FDR_FAMILIES: dict[str, tuple[str, ...]] = {"assembly": tuple(f"fp|{p}" for p in POSITIONS)}

# Inherited gate constants — ⛔ the coverage floor may not move (NF-D18 / E2.1-r / NF1.8).
COVERAGE_FLOOR = KW.COVERAGE_FLOOR
COVERAGE_BLOCK_SE = KW.COVERAGE_BLOCK_SE
PBO_MAX, DSR_MIN, FDR_Q = KW.PBO_MAX, KW.DSR_MIN, KW.FDR_Q
MIN_ESTIMATION_ROWS = JD.MIN_ESTIMATION_ROWS
#: E2.1-r: on a discrete/atom-bearing predictive the coverage figure is a FLOOR and PIT flatness
#: is the calibration TARGET. Max decile deviation from 0.10, pre-registered.
PIT_MAX_DECILE_DEV = 0.05

#: ⭐ Rows the RESIDUAL-scale estimator (`joint_pit`) computes PITs over — the most recent
#: `PIT_ESTIMATION_ROWS` train rows, not all of them.
#:
#: DERIVED FROM A DESIGN QUANTITY, NOT TUNED TO A RUNTIME OR A RESULT. Σ here is a 13×13
#: correlation; the standard error of a correlation is ≈(1−ρ²)/√(n−3), so at n = 8,000 it is
#: ≈0.011 — an order of magnitude below any dependence magnitude this story could act on, and the
#: raw-rank arms (which need no model predictions) keep using the FULL train window regardless.
#: ⛔ The marginal FIT is UNCHANGED — still the full train set, the identical predictive the real
#: arms serve; only the number of rows PITs are COMPUTED ON is capped. Pre-registered BEFORE any
#: score exists, so this is a compute decision, never a result-shaped one (E2.1-r).
PIT_ESTIMATION_ROWS = 8_000

ASSEMBLY_DRAWS = KW.ASSEMBLY_DRAWS               # 4000, NF-W7's convention
#: Rows per draw block. The base normals are seeded per BLOCK, so a run reproduces given
#: (seed, ROW_BLOCK) — pinned here and recorded in the artifact rather than left implicit.
#: Chosen so one block is ~O(100 MB): 13 legs × 4000 draws × 256 rows × 8 B ≈ 106 MB.
ROW_BLOCK = 256

STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok", "coverage_floor_ok",
    "pit_flat_ok",
)
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
    "independence_under_disperses", "dependence_moves_coverage", "beats_indep_on_coverage",
)

REFUSAL_MECHANISM = (
    ". The mechanism: the registered dependence structures UNDER-CORRECT on the skill-position "
    "legs — the joint draw moves the assembled sum's coverage toward nominal but not far enough, "
    "so residual co-movement (or a non-Gaussian dependence shape between a zero atom and a "
    "continuous yardage leg) is still unpriced.")
REFUSAL_REMEDY = (
    "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds shrink the "
    "binomial SE and make the refusal MORE certain. The remedy is a BETTER dependence "
    "estimator/shape under a FRESH registration (NF-MARGIN3 / NF-W6b-C successor pattern — e.g. "
    "a vine or an atom-aware copula that models the zero/positive mixture explicitly), or a PM "
    "decision; ⛔ never a post-hoc floor change (E2.1-r / NF1.8).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The stat-key map's contract (fail-closed)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def assert_stat_key_map() -> dict:
    """The leg→canonical-key map is EXHAUSTIVE, INJECTIVE, and lands inside the profile.

    Three independently RED-provable clauses (NF-D17: a fixture must satisfy the other clauses so
    only the named one can flip the result — see the guards)."""
    if set(STAT_KEY) != set(LEGS):
        raise ValueError(
            f"STAT_KEY does not cover the substrate legs: missing {sorted(set(LEGS) - set(STAT_KEY))}, "
            f"extra {sorted(set(STAT_KEY) - set(LEGS))} — a leg with no canonical key would be "
            f"silently unscored")
    if len(set(STAT_KEY.values())) != len(STAT_KEY):
        seen: dict[str, str] = {}
        dupes = {v: (seen.setdefault(v, k), k) for k, v in STAT_KEY.items() if v in seen}
        raise ValueError(f"STAT_KEY is not injective: {dupes} — two legs sharing one canonical "
                         f"key would double-count that league term")
    unknown = sorted(set(STAT_KEY.values()) - set(LP.NFL_PROFILE.stat_columns))
    if unknown:
        raise ValueError(f"STAT_KEY names canonical keys the NFL profile does not carry: "
                         f"{unknown} — the scorer would price them at 0")
    partition = set(STAT_KEY.values()) | set(SKILL_UNMODELED_KEYS) | set(OUT_OF_SCOPE_KEYS)
    if partition != set(LP.NFL_PROFILE.stat_columns):
        raise ValueError(
            f"the scored-key partition drifted from the profile: unclassified "
            f"{sorted(set(LP.NFL_PROFILE.stat_columns) - partition)} — a new scorable term must "
            f"land in exactly one bucket (modeled / skill-gap / out-of-scope), never nowhere")
    return {"n_legs": N_LEGS, "n_skill_unmodeled": len(SKILL_UNMODELED_KEYS),
            "n_out_of_scope": len(OUT_OF_SCOPE_KEYS)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — the EXISTING policy, read; ⛔ never restated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def leg_weights(config: LeagueConfig, position: str) -> np.ndarray:
    """(13,) points-per-unit for one position under one league, in `LEGS` order.

    ⭐ Every element comes from `ScoringRules.points_for` — the same call `fantasy_engine`,
    the browser port and the Lambda scorer all resolve to — including its per-position bonus
    (TE-premium PPR and friends). This function CHOOSES nothing; it reads."""
    return np.array([config.scoring.points_for(STAT_KEY[leg], position) for leg in LEGS],
                    dtype=float)


def priced_legs(config: LeagueConfig, position: str) -> tuple[str, ...]:
    """The legs this league actually prices. A zero-weight leg contributes identically 0 to every
    draw, so it can neither move the answer nor justify a caveat about the answer."""
    w = leg_weights(config, position)
    return tuple(leg for leg, wt in zip(LEGS, w) if wt != 0.0)


def unpriced_scored_terms(config: LeagueConfig, position: str) -> dict[str, float]:
    """Non-zero-weight league terms this assembly has NO distribution for, EXCLUDING the terms
    that are structurally another position's line (K/DST).

    ⚠️ This is the honesty valve. Silently scoring an unmodeled priced term as 0 would understate
    fantasy points with no signal anywhere — the class of defect that is invisible precisely
    because every mechanism behaves as designed."""
    out: dict[str, float] = {}
    for key in SKILL_UNMODELED_KEYS:
        w = config.scoring.points_for(key, position)
        if w != 0.0:
            out[key] = float(w)
    return out


def score_realized(stat_matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Realized league points for (n, 13) realized stat lines — the SAME linear form the
    predictive is assembled through, so target and predictive can never drift apart."""
    x = np.asarray(stat_matrix, dtype=float)
    if x.ndim != 2 or x.shape[1] != N_LEGS:
        raise ValueError(f"stat matrix is {x.shape}, expected (n, {N_LEGS}) in LEGS order")
    return x @ np.asarray(weights, dtype=float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Dependence estimation — RAW OUTCOME RANKS (⭐ the card's estimator), per position, train-only
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _embed(sub: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """A correlation matrix estimated over `keep` legs, embedded in the identity for the rest."""
    full = np.eye(N_LEGS)
    idx = np.flatnonzero(keep)
    full[np.ix_(idx, idx)] = sub
    return full


def _degenerate_legs(mat: np.ndarray) -> np.ndarray:
    """Legs with NO variation in the estimation slice (a WR's pass attempts are 0 every week).

    ⭐ Their correlation is not "assumed independent" — it is UNDEFINED and structurally so: a
    constant has no co-movement to estimate and contributes exactly 0 to a weighted sum whose
    weight it may not even carry. They are dropped from the estimate, embedded as identity, and
    RECORDED — the distinction NF1.9 draws between "a mechanism that cannot act" and an omission."""
    m = np.asarray(mat, dtype=float)
    return ~(np.nanstd(m, axis=0) > 0)


def position_sigma(raw: np.ndarray, *, min_rows: int = MIN_ESTIMATION_ROWS
                   ) -> tuple[np.ndarray, dict]:
    """⭐ THE PRIMARY ESTIMATOR: Spearman rank correlation of RAW outcomes → the Gaussian-copula
    scale (2·sin(π·ρs/6)), over one position's TRAIN rows.

    REFUSES below `min_rows` by delegating to `JD.spearman_gauss_corr` — an unevaluable estimate
    must never masquerade as independence (NF1.7 (a)); the caller is expected to let that raise,
    not to catch it into an identity."""
    m = np.asarray(raw, dtype=float)
    if m.shape[1] != N_LEGS:
        raise ValueError(f"raw outcome matrix is {m.shape}, expected (n, {N_LEGS})")
    dead = _degenerate_legs(m)
    keep = ~dead
    if int(keep.sum()) < 2:
        raise ValueError(
            f"only {int(keep.sum())} leg(s) vary in this estimation slice — there is no "
            f"dependence to estimate; refusing rather than returning a silent identity")
    sub, n_rows = JD.spearman_gauss_corr(m[:, keep], min_rows=min_rows)
    return _embed(sub, keep), {
        "estimator": "spearman_raw_ranks", "n_rows": int(n_rows),
        "degenerate_legs": [LEGS[i] for i in np.flatnonzero(dead)],
        "n_estimated_legs": int(keep.sum()),
    }


def position_sigma_pit(banks: np.ndarray, realized: np.ndarray, *, seed: int = _SEED,
                       min_rows: int = MIN_ESTIMATION_ROWS) -> tuple[np.ndarray, dict]:
    """The RESIDUAL-scale estimator (`joint_pit`): randomized PIT of each realized outcome under
    its own W6d marginal, Φ⁻¹-mapped, then Pearson. Registered as a real arm — NF-W7b measured
    this scale to be ATTENUATED on zero-heavy discrete margins, and this story re-measures it
    rather than inheriting the finding.

    `banks` is (n, 13, 199); `realized` is (n, 13)."""
    b = np.asarray(banks, dtype=float)
    y = np.asarray(realized, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    z = np.column_stack([
        JD.zscores_from_uniforms(KW.randomized_pit_from_bank(b[:, i, :], y[:, i], seed + i))
        for i in range(N_LEGS)
    ])
    dead = _degenerate_legs(z)
    keep = ~dead
    if int(keep.sum()) < 2:
        raise ValueError("fewer than 2 legs carry PIT variation — refusing a silent identity")
    sub, n_rows = JD.estimate_corr_from_z(z[:, keep], min_rows=min_rows)
    return _embed(sub, keep), {
        "estimator": "randomized_pit_z", "n_rows": int(n_rows),
        "degenerate_legs": [LEGS[i] for i in np.flatnonzero(dead)],
        "n_estimated_legs": int(keep.sum()),
    }


def sigma_for_arm(arm: str, *, raw: np.ndarray, banks: np.ndarray | None = None,
                  realized: np.ndarray | None = None, seed: int = _SEED,
                  min_rows: int = MIN_ESTIMATION_ROWS) -> tuple[np.ndarray, dict]:
    """The arm's Σ from ITS pre-registered estimator. The caller supplies the ESTIMATION context
    (train rows for a real arm; test rows for an oracle; the matched slice for a matched-n
    control) — the transform is fixed here, so no arm can quietly change scale."""
    if arm not in REAL_ARMS:
        raise KeyError(f"unknown dependence arm `{arm}` — not in the pre-registered family "
                       f"{REAL_ARMS}")
    if arm == "joint_pit":
        if banks is None or realized is None:
            raise ValueError("joint_pit needs (banks, realized) — the residual scale is defined "
                             "against the marginals, not the raw outcomes")
        return position_sigma_pit(banks, realized, seed=seed, min_rows=min_rows)
    base, note = position_sigma(raw, min_rows=min_rows)
    if arm == "joint_rank":
        return base, note
    if arm == "joint_factor":
        sig, lam = JD.one_factor_corr(base)
        return sig, {**note, "structure": "one_factor",
                     "loadings": {LEGS[i]: round(float(v), 4) for i, v in enumerate(lam)}}
    return JD.scale_offdiagonal(base, DOUBLE_SCALE), {**note, "structure": "offdiag_x2"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The assembly — marginals untouched; only the uniforms' JOINT law changes
# ══════════════════════════════════════════════════════════════════════════════════════════════
def comonotone_flip(weights: np.ndarray) -> tuple[bool, ...]:
    """Which legs take `1−u` in the comonotone degenerate — the ones whose POINTS DECREASE in
    their own outcome.

    ⚠️ THIS IS LOAD-BEARING AND LEAGUE-DEPENDENT. Two priced legs carry NEGATIVE weights (fumbles
    lost, interceptions). Co-moving every leg in the OUTCOME direction would push yards and
    interceptions up together, and their contributions would partly CANCEL in the weighted sum —
    so the "maximally dispersed" anchor would not be maximally dispersed, and the over-correlated
    ceiling registered to lose the metric (and to prove the coverage floor was not promoted into a
    selection criterion) would be neither a ceiling nor a proof. Flipping the negative legs makes
    the anchor co-move in the POINTS direction, which is the direction the gate reads. The flip is
    derived from the league's own weights, never hand-typed (NF-W7b's `COMONOTONE_FLIP`, made
    config-dependent because a league may price a term either way)."""
    return tuple(bool(w < 0) for w in np.asarray(weights, dtype=float))


def _uniforms(base_z: np.ndarray, mode: str, corr: np.ndarray | None,
              weights: np.ndarray | None = None) -> np.ndarray:
    if mode == "indep":
        return JD.independent_uniforms(base_z)
    if mode == "comonotone":
        if weights is None:
            raise ValueError("mode='comonotone' needs the league weights to orient the flip — a "
                             "degenerate co-moved in the OUTCOME direction is not the "
                             "maximal-dispersion anchor when a priced leg scores negatively")
        return JD.comonotone_uniforms(base_z, comonotone_flip(weights))
    if mode == "copula":
        if corr is None:
            raise ValueError("mode='copula' requires corr")
        return JD.gaussian_copula_uniforms(base_z, corr)
    raise ValueError(f"unknown assembly mode `{mode}`")


def draw_legs(banks_block: np.ndarray, u: np.ndarray) -> np.ndarray:
    """(b, 13, 199) banks + (b, draws, 13) uniforms → (b, draws, 13) stat draws.

    Inverse-CDF per leg, so each leg's MARGINAL law is exactly its W6d bank for ANY joint law of
    `u` whose leg marginals are U(0,1) — the mechanical statement that the copula layer adds only
    dependence. Integer legs are rounded and every leg is floored at 0 (a negative reception is
    not a quantity)."""
    b, draws, n_legs = u.shape
    if n_legs != N_LEGS or banks_block.shape[:2] != (b, N_LEGS):
        raise ValueError(f"shape mismatch: banks {banks_block.shape} vs uniforms {u.shape}")
    out = np.empty((b, draws, N_LEGS), dtype=float)
    for i, leg in enumerate(LEGS):
        vals = KW.sample_from_bank(banks_block[:, i, :], u[:, :, i])
        vals = np.clip(vals, 0.0, None)
        out[:, :, i] = np.rint(vals) if leg in INTEGER_LEGS else vals
    return out


def assemble_fp_bank(banks: np.ndarray, weights: np.ndarray, *, mode: str = "copula",
                     corr: np.ndarray | None = None, draws: int = ASSEMBLY_DRAWS,
                     seed: int = _SEED, row_block: int = ROW_BLOCK) -> np.ndarray:
    """One assembled (n, 199) league-fantasy-point bank.

    ⭐ COMMON RANDOM NUMBERS: the base normals depend only on (block index, draws, seed), so every
    arm and anchor of a fold transforms the SAME blocks — arm-vs-arm differences are dependence
    differences, never Monte-Carlo noise — and `mode="indep"` is BYTE-IDENTICAL to the copula at
    Σ = I, which is what makes "independence is a special case of the field" a fact rather than a
    claim.

    Blocked over rows so peak memory stays ~O(row_block × draws × 13); the block seeding is part
    of the reproducibility contract (see `ROW_BLOCK`)."""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    w = np.asarray(weights, dtype=float)
    if w.shape != (N_LEGS,):
        raise ValueError(f"weights are {w.shape}, expected ({N_LEGS},)")
    n = b.shape[0]
    out = np.empty((n, N_LEVELS), dtype=float)
    for start in range(0, n, row_block):
        stop = min(start + row_block, n)
        rng = np.random.default_rng(seed + start)
        base_z = rng.standard_normal((stop - start, draws, N_LEGS))
        pts = draw_legs(b[start:stop], _uniforms(base_z, mode, corr, w)) @ w
        out[start:stop] = np.quantile(pts, EVAL_LEVELS, axis=1).T
    return out


def assembled_sum_sd(banks: np.ndarray, weights: np.ndarray, corr: np.ndarray) -> np.ndarray:
    """The ANALYTIC half of arm-movability (NF-MARGIN2 / NF-D20 — a statistic the arm cannot move
    is décor, not a gate): sd(Σ wᵢXᵢ) = √((w∘σ)ᵀ Σ (w∘σ)) per row, strictly increasing in every
    off-diagonal with a positive weight product. So the dependence knob provably moves the
    assembled sum's dispersion, hence its central-interval coverage — before a single draw."""
    b = np.asarray(banks, dtype=float)
    sds = b.std(axis=2)                                   # (n, 13) grid sd of each leg's bank
    a = sds * np.asarray(weights, dtype=float)[None, :]
    return np.sqrt(np.einsum("ni,ij,nj->n", a, np.asarray(corr, dtype=float), a))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Labelling carry (NF-W6d PROMOTE_BLOCKERS, honoured at the ASSEMBLED level)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: Source values that make a leg a calibrated DEFAULT rather than a bake-off winner. IMPORTED
#: from the serving module that STAMPS them — a re-typed string here would drift silently and
#: the caveat would stop firing with nothing to notice it (the NF-C0e wrong-key class).
DEFAULT_SOURCES: frozenset[str] = frozenset({SDSD.SOURCE_W6D_DEFAULT})

ASSEMBLED_SOURCE_SHIP = "bakeoff_all_priced_legs"
ASSEMBLED_SOURCE_PARTIAL = "partial_default"
ASSEMBLED_SOURCE_DEFAULT = "default"


def assembled_labelling(served_map: dict[str, dict], config: LeagueConfig, position: str) -> dict:
    """The assembled row's provenance — ⭐ over the PRICED legs only.

    A leg the league weights at 0 contributes identically 0 to every draw, so a calibrated default
    there cannot influence the assembled distribution and must not raise a caveat about it (a
    warning that fires on something that cannot matter trains the reader to ignore warnings —
    the alert-fatigue direction of E11.30). A default on a leg the league DOES price is a real
    caveat and is surfaced, per NF-W6d's promote blocker: "the assembly consumer must read
    `source`/`calibration_warning` and never present a default as a conditional projection."""
    priced = priced_legs(config, position)
    if not priced:
        raise ValueError(f"{position}: this league prices none of the {N_LEGS} modeled legs — "
                         f"an assembled distribution would be identically zero")
    per_leg: dict[str, str] = {}
    warnings: dict[str, str] = {}
    for leg in priced:
        cell = f"{position}|{leg}"
        entry = served_map.get(cell)
        if entry is None:
            raise KeyError(f"{cell}: the served map has no cell for a PRICED leg — the substrate "
                           f"is incomplete for this league (refusing to assemble)")
        per_leg[leg] = entry["source"]
        if entry.get("calibration_warning"):
            warnings[leg] = str(entry["calibration_warning"])
    defaults = sorted(leg for leg, src in per_leg.items() if src in DEFAULT_SOURCES)
    if not defaults:
        source = ASSEMBLED_SOURCE_SHIP
    elif len(defaults) == len(priced):
        source = ASSEMBLED_SOURCE_DEFAULT
    else:
        source = ASSEMBLED_SOURCE_PARTIAL
    return {
        "source": source,
        "priced_legs": list(priced),
        "unpriced_legs": [leg for leg in LEGS if leg not in priced],
        "leg_sources": per_leg,
        "default_priced_legs": defaults,
        "calibration_warning": (
            None if not defaults else
            f"{len(defaults)} of {len(priced)} priced stats use a NF-W6d calibrated DEFAULT "
            f"({', '.join(defaults)}) — a calibrated range, not a conditional projection"),
        "leg_calibration_warnings": warnings,
    }


def default_contribution_share(banks: np.ndarray, config: LeagueConfig, position: str,
                               served_map: dict[str, dict]) -> dict:
    """How much of the assembled total actually comes from DEFAULT-sourced legs.

    ⭐ WHY THIS EXISTS, AND WHY IT IS NOT A THRESHOLD. Measured against the real NF-W6d map, EVERY
    position labels `partial_default` — because a position's MINOR CHANNELS (a wide receiver's
    passing yards) are Phase-C defaults, and a standard league prices them. Left there, the caveat
    fires on every player and stops meaning anything. The tempting fix is a materiality cutoff —
    ⛔ but choosing one now, having seen which legs it would silence, is the E2.1-r inversion in
    its most literal form. So this MEASURES and does not judge: the share of absolute expected
    point contribution (Σ|wᵢ·E[Xᵢ]| over default legs ÷ the same over all priced legs) that rests
    on a calibrated default. A consumer or a PM can then set a display rule with the number in
    hand, pre-registered forward.

    ABSOLUTE contribution, deliberately: two priced legs carry NEGATIVE weights (fumbles lost,
    interceptions), so a signed share is not a share of anything."""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    label = assembled_labelling(served_map, config, position)
    w = leg_weights(config, position)
    contrib = np.abs(b.mean(axis=2) * w[None, :])              # (n, 13) |wᵢ·E[Xᵢ]|
    total = contrib.sum(axis=1)
    idx = [LEGS.index(leg) for leg in label["default_priced_legs"]]
    share = (contrib[:, idx].sum(axis=1) / np.where(total > 0, total, 1.0)) if idx \
        else np.zeros(len(b))
    return {
        "default_priced_legs": label["default_priced_legs"],
        "mean_default_contribution_share": round(float(share.mean()), 4),
        "p90_default_contribution_share": round(float(np.quantile(share, 0.90)), 4),
        "max_default_contribution_share": round(float(share.max()), 4),
        "basis": "absolute expected point contribution per leg (two priced legs are negative)",
        "threshold_applied": None,
        "note": ("MEASURED, not thresholded — a materiality cutoff chosen after seeing which legs "
                 "it would silence is the E2.1-r inversion; any display rule is pre-registered "
                 "forward by the consumer story."),
    }


def assert_assembly_is_priceable(config: LeagueConfig, position: str, *,
                                 allow_unpriced: bool = False) -> dict:
    """Fail-closed pre-flight: every non-zero league term is either MODELED or explicitly waived.

    ⛔ The default is REFUSAL. `allow_unpriced=True` is for a caller that has decided to serve a
    partial assembly anyway — and it still returns the gap so the caller must carry it onto the
    row; it is not a way to make the gap disappear."""
    gaps = unpriced_scored_terms(config, position)
    if gaps and not allow_unpriced:
        raise ValueError(
            f"{position}: this league prices {sorted(gaps)} but the NF-W6d substrate has no "
            f"distribution for those terms — scoring them as 0 would UNDERSTATE fantasy points "
            f"with no signal anywhere. Pass allow_unpriced=True to serve a partial assembly "
            f"(the gap is then carried onto the row), or extend the substrate.")
    return {"unpriced_scored_terms": gaps, "complete": not gaps}


def representation_manifest(config: LeagueConfig, position: str,
                            served_map: dict[str, dict] | None = None) -> dict:
    """The assembled surface's declared contract — what a consumer may read off a row."""
    out = {
        "story": STORY, "target": TARGET, "n_levels": N_LEVELS, "legs": list(LEGS),
        "stat_keys": dict(STAT_KEY), "position": position,
        "weights": {leg: float(w) for leg, w in zip(LEGS, leg_weights(config, position))},
        "assembly_draws": ASSEMBLY_DRAWS, "row_block": ROW_BLOCK, "seed": _SEED,
        "uncertainty_framing": SDD.screen_copy("uncertainty_framing", (
            "an honest range for one player-week's fantasy points under THIS league's scoring: "
            "the per-stat distributions drawn together (stats co-move) and re-scored draw by "
            "draw. A calibrated RANGE — not a market comparison, and not an edge / ROI / "
            "win-rate claim of any kind.")),
        **assert_assembly_is_priceable(config, position, allow_unpriced=True),
    }
    if served_map is not None:
        out["labelling"] = assembled_labelling(served_map, config, position)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The SERVING assembly — the certified arm, READ from the record (⛔ never hand-typed)
# ══════════════════════════════════════════════════════════════════════════════════════════════
MODEL_FAMILY = SDSD.MODEL_FAMILY
REGISTRY_TARGET = "weekly_fp_distribution"
SERVED_VERSION = "nfl_fantasy_w7c_v1"
RECORD_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                  "nf_w7c_fp_assembly.json")
#: The served summaries a consumer may read off an assembled row (the boom/bust reading).
SUMMARY_COLUMNS: tuple[str, ...] = ("p10", "p50", "p90", "mean", "p_bust", "p_boom")
#: Boom/bust are defined against the row's OWN median — a fixed points threshold would mean
#: something different for a QB and a TE, and something different again in a non-PPR league.
BOOM_MULTIPLE, BUST_MULTIPLE = 1.5, 0.5


def certified_arms(record_path, *, allow_path_proof: bool = False) -> dict[str, str]:
    """{position: certified dependence arm} from the committed NF-W7c record.

    FAIL-CLOSED exactly like `SDSD._load_record`: an absent / smoke / wrong-story record, or a
    position whose gate did not SHIP, is REFUSED — a challenger may not serve itself into
    existence, and a position that did not clear its gate has no certified arm to serve."""
    import json as _json
    from pathlib import Path as _Path
    p = _Path(record_path)
    if not p.exists():
        raise FileNotFoundError(
            f"NF-W7c record missing: {p} — the serving arm is READ from the §0.5 record, never "
            f"typed; run the full (non-smoke) assembly first")
    rec = _json.loads(p.read_text())
    if rec.get("story") != STORY:
        raise ValueError(f"{p.name}: story {rec.get('story')} ≠ {STORY} — refusing")
    if rec.get("smoke"):
        raise ValueError(f"{p.name}: a --smoke path proof is not a decision record — refusing")
    verdict = rec.get("verdict") or {}
    if "ship_positions" not in verdict:
        raise ValueError(f"{p.name}: no verdict layer — refusing")
    ship = list(verdict["ship_positions"])
    if not ship:
        raise ValueError(
            f"{p.name}: the record ships NO position (story verdict "
            f"{verdict.get('story_verdict')}) — there is nothing certified to serve")
    return {p_: rec["selections"][p_]["winner"] for p_ in ship}


def serve_fp_frame(train_raw: dict[str, np.ndarray], serve_banks: dict[str, np.ndarray],
                   config: LeagueConfig, served_map: dict[str, dict], arms: dict[str, str], *,
                   train_banks: dict[str, np.ndarray] | None = None,
                   draws: int = ASSEMBLY_DRAWS, seed: int = _SEED,
                   allow_unpriced: bool = False) -> dict[str, dict]:
    """Assemble one served fantasy-point distribution per certified position.

    `train_raw[pos]` is that position's (n_train, 13) REALIZED TRAIN stat lines — Σ is always
    estimated on TRAIN, never on the slate being served, so nothing here peeks. `serve_banks[pos]`
    is the (n_serve, 13, 199) W6d bank tensor. `train_banks[pos]` (the in-sample train predictives)
    is required only by `joint_pit`, whose scale is defined against the marginals rather than the
    raw outcomes — it is REFUSED rather than silently downgraded when absent.

    ⛔ Dispatch-only over the certified constructions: the marginals arrive already built by the
    W6d serving dispatch, and this adds the dependence structure + the league's own weights.
    Nothing is fitted here."""
    out: dict[str, dict] = {}
    for position, arm in arms.items():
        gap = assert_assembly_is_priceable(config, position, allow_unpriced=allow_unpriced)
        raw = np.asarray(train_raw[position], dtype=float)
        tb = None if train_banks is None else np.asarray(train_banks[position], dtype=float)
        if arm == "joint_pit" and tb is None:
            raise ValueError(
                f"{position}: the certified arm `joint_pit` estimates Σ on the residual scale, so "
                f"it needs the IN-SAMPLE TRAIN predictives (`train_banks`) as well as the train "
                f"outcomes — refusing rather than quietly serving a different arm's Σ")
        sigma, note = sigma_for_arm(arm, raw=raw, banks=tb, realized=raw, seed=seed)
        banks = np.asarray(serve_banks[position], dtype=float)
        bank = assemble_fp_bank(banks, leg_weights(config, position), corr=sigma, draws=draws,
                                seed=seed)
        assert_served_representation(bank)
        out[position] = {
            "bank": bank, "arm": arm, "sigma_note": note,
            "summaries": encode_fp_bank(bank),
            "labelling": assembled_labelling(served_map, config, position),
            "default_contribution": default_contribution_share(banks, config, position,
                                                               served_map),
            **gap,
        }
    return out


def encode_fp_bank(bank: np.ndarray) -> dict[str, np.ndarray]:
    """The consumer-facing summaries, DERIVED from the bank by one reading rule — ⭐ nothing here
    recomputes a quantity from features, so a summary can never silently disagree with the
    distribution it describes (the NF-C0e wrong-key class)."""
    b = np.sort(np.asarray(bank, dtype=float), axis=1)
    i10 = int(np.searchsorted(EVAL_LEVELS, 0.10))
    i50 = int(np.searchsorted(EVAL_LEVELS, 0.50))
    i90 = int(np.searchsorted(EVAL_LEVELS, 0.90))
    med = b[:, i50]
    return {
        "p10": b[:, i10], "p50": med, "p90": b[:, i90], "mean": b.mean(axis=1),
        "p_bust": (b < (BUST_MULTIPLE * med)[:, None]).mean(axis=1),
        "p_boom": (b > (BOOM_MULTIPLE * med)[:, None]).mean(axis=1),
    }


def assert_served_representation(bank: np.ndarray) -> None:
    """The served contract, fail-closed: an (n, 199) FINITE, MONOTONE bank.

    ⛔ It does NOT sort-and-continue — a served bank that needs sorting is a broken construction,
    and repairing it here would hide exactly the defect this check exists to catch."""
    b = np.asarray(bank, dtype=float)
    if b.ndim != 2 or b.shape[1] != N_LEVELS:
        raise ValueError(f"assembled bank is {b.shape}, expected (n, {N_LEVELS})")
    if not np.isfinite(b).all():
        raise ValueError(f"{int((~np.isfinite(b)).sum())} non-finite values in an assembled bank "
                         f"— refusing to serve a broken predictive (NF-W3 (b))")
    if b.size and float(np.min(np.diff(b, axis=1))) < -1e-9:
        raise ValueError("assembled bank is NOT monotone — quantiles of a draw sample are "
                         "monotone by construction, so this is a real defect")


PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W7c is DEPLOY-HELD: the assembled fantasy-point distribution is an NF-G0 challenger and "
    "is served by nothing until governance promotes it",
    "an assembled row whose `source` is not `bakeoff_all_priced_legs` carries at least one "
    "NF-W6d calibrated DEFAULT among the stats this league prices — the consumer must surface "
    "`calibration_warning` and must never present it as a conditional projection",
    "a league pricing a term in SKILL_UNMODELED_KEYS has a REAL coverage gap: the assembled "
    "total omits it, and `unpriced_scored_terms` must be shown, never silently scored as 0",
    "the dependence structure is certified PER POSITION on the NF-W7c fold axis — a position or "
    "a league whose priced legs fall outside that certification is not covered by this record",
)
