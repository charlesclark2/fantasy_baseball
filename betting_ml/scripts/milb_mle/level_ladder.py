"""level_ladder.py — MLB Edge-E7.15 H1: the WITHIN-PLAYER minor-level translation ladder.

E7.12 closed six slices with a clean split: everything that WON was about sample composition and label
precision; everything about WHAT THE PLAYER DID (park, age, tool grades) NULLED. A disattenuation check
refuted the "we are at the label-noise ceiling" reading, so those nulls are genuine INFORMATION failures
— park/age/grades are all re-expressions of the same minor-league box score. Round 2 therefore has to add
information that is NOT already in a player's own line.

⭐ **THE H1 IDEA.** E7.3 learns `MLB_rate ~ f(minor_rate, level, league, age)` from GRADUATES only — a
player's Single-A row is one of 306 labelled Single-A observations, and every one of them is a player who
was eventually promoted. But the LEVEL-to-LEVEL part of that map does not need an MLB label at all: a
player who hit .330 wOBA at High-A and then .310 at Double-A is a direct observation of the High-A →
Double-A translation, and there are **2,102** of those against 432 labelled High-A rows. Three quarters of
them belong to players who never reached MLB — i.e. exactly the un-promoted population the draft board is
actually served on, and exactly the population a graduates-only fit cannot see.

So: estimate every rung EXCEPT the last from within-player minor→minor transitions, express each row at a
common REFERENCE level (Triple-A), and let the existing pooled learner do the final AAA→MLB step. This
multiplies n for the lower rungs, confines the promotion-selection problem (E7.12 slice 2) to the FINAL
rung, and is genuinely new information rather than a re-expression of the same line.

WHAT THIS MODULE IS AND IS NOT
------------------------------
It is the LADDER MECHANISM ONLY — pure functions over a pairs frame, no IO, no bake-off. The §0.5 harness
(candidates, anchors, folds, deflation, per-propensity-tercile read) lives in `run_e7_15_h1.py`, which
reuses E7.12 slice 1's harness rather than forking it.

🔒 **ESTIMAND PRESERVED (E7.15 readiness lock 3).** The ladder changes HOW the level translation is
learned; the model still predicts the SAME quantity — the realized MLB rate — from the same labelled
population, and `emit_projections` still writes `mle_<metric>` meaning "projected MLB rate". The E8.0
board and the E7.5b betting prior therefore stay comparable. (Contrast H4, which explicitly changes the
estimand to a regressed true-talent target and pays a board-comparability cost for it.)

🪤 **THE HAZARD THIS MECHANISM CARRIES, STATED BEFORE THE RUN.** Each rung regression is attenuated by
measurement error in its SOURCE rate. Composing three of them attenuates three times, whereas a direct
Single-A→MLB fit attenuates once. If the levels are noisy measurements of one latent talent (rather than a
true Markov chain), the composed chain therefore OVER-SHRINKS a low-level line toward the mean. That is
why `direct` mode exists (estimate the Single-A→Triple-A map from the 695 players who made that jump, in
ONE step) and why `A_ladder_meanshift` is in the field: over-shrinkage and a pure level re-centring look
identical on a leaderboard and are told apart only by a matched foil.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# The generous PHYSICAL clip the slice-1 ladder already applies (NOT the tighter emission
# `PLAUSIBLE_RANGE`). Imported rather than re-declared so the two can never drift apart.
from betting_ml.scripts.milb_mle.park_context import _RATE_BOUNDS

log = logging.getLogger("e7_15.ladder")

# Levels in ASCENDING difficulty. `milb_mle.LEVEL_ORDER` is the same set ordered nearest-to-MLB first for
# cosmetics; the ladder needs the climb direction, so it is spelled out here rather than reversed inline
# (a silently reversed ladder maps everyone DOWN and still produces plausible-looking numbers).
ASC_LEVELS: tuple[str, ...] = ("Single-A", "High-A", "Double-A", "Triple-A")
LEVEL_RANK: dict[str, int] = {lvl: i for i, lvl in enumerate(ASC_LEVELS)}

# Where every row is expressed. Triple-A is the level nearest MLB, so the final learned step (AAA→MLB) is
# the one the E7.3 pooled learner keeps doing on labelled graduates — the ladder never touches it.
REFERENCE_LEVEL = "Triple-A"

# A rung thinner than this is not fitted — it FALLS BACK to identity and says so. 60 is the pre-registered
# floor: below it a two-parameter fit on a noisy rate is a coin flip, and a wild slope compounds through
# the composition. Every fallback is counted and reported; a rung that ALWAYS falls back is a mechanism
# that cannot act (NF1.9), which is a finding, not an omission.
MIN_RUNG_N = 60

# Minimum line thickness for BOTH sides of a transition, mirroring `MleConfig.min_minor_pa`. A 20-PA
# cameo at the next level is not an observation of the translation.
MIN_TRANSITION_PA = 150

# Deterministic — a placebo that moves between runs cannot be a gate (slice 1's `PLACEBO_SEED` posture).
LADDER_PLACEBO_SEED = 20260801

LADDER_MODES = ("off", "chain", "direct", "meanshift", "identity", "shuffled")


@dataclass(frozen=True)
class LadderSpec:
    """One pre-registered ladder formulation.

    `mode="off"` is the byte-exact no-op — the E7.12-slice-1 shipped configuration with no ladder at all,
    i.e. the DIRECT-LEARNED FOIL the §0.5 rule requires. That identity is pinned by a test: without it the
    "ladder" arm would be compared against a re-implementation of the incumbent rather than the incumbent.
    """

    mode: str = "off"
    # PA-weight the rung regression by the HARMONIC MEAN of the two line lengths — a pair is only as
    # informative as its thinner side. `weighted=False` is the matched pair, so the weighting scheme's
    # contribution is attributable rather than bundled into the ladder's headline.
    weighted: bool = False
    # ⭐ THE NESTING ARM. Instead of REPLACING the minor rate, keep it and hand the pooled learner the
    # ladder DELTA (ladder rate − raw rate) as an extra unpenalized fixed regressor. This arm CONTAINS the
    # foil as the special case "delta coefficient = 0", so a win is unambiguously "the ladder adds
    # information", and the delta is far better conditioned than the near-collinear ladder rate itself.
    as_extra: bool = False
    # Registered SENSITIVITY, not the default. Slice 1's leakage posture is that a MiLB-only transform
    # touches no MLB label and can therefore be estimated over the whole substrate; this switch
    # additionally purges any transition that had not FINISHED before the held-out debut cohort, so the
    # question "does using calendar-future minor-league data change the answer?" is measured rather than
    # argued. See `fit_ladder`.
    calendar_purge: bool = False
    min_rung_n: int = MIN_RUNG_N

    def __post_init__(self):
        if self.mode not in LADDER_MODES:
            raise ValueError(f"mode={self.mode!r} not in {LADDER_MODES}")
        if self.mode == "off" and (self.weighted or self.as_extra or self.calendar_purge):
            raise ValueError("mode='off' is the no-op foil — it takes no options, or it is not a foil")

    @property
    def is_noop(self) -> bool:
        return self.mode == "off"

    @property
    def label(self) -> str:
        if self.is_noop:
            return "no_ladder"
        bits = [self.mode]
        if self.weighted:
            bits.append("paw")
        if self.as_extra:
            bits.append("extra")
        if self.calendar_purge:
            bits.append("purged")
        return "+".join(bits)


# ══════════════════════════════════════════════════════════════════════════════════════
# The transition substrate
# ══════════════════════════════════════════════════════════════════════════════════════


def build_transitions(pairs: pd.DataFrame, metric: str, *,
                      min_pa: int = MIN_TRANSITION_PA) -> pd.DataFrame:
    """Every ORDERED within-player (lower level → higher level) pair, one row per pair.

    ALL ordered pairs, not only adjacent ones: `chain` mode reads the three adjacent rungs, `direct` mode
    reads the (level → Triple-A) rungs in one step, and having both in one frame is what lets the two
    formulations be scored on the same substrate.

    🔒 **TEMPORAL ORDER IS ENFORCED, NOT ASSUMED.** The pairs table aggregates a player's whole stint at a
    level, so nothing in the row order says which came first — a rehab assignment sends a Triple-A player
    back to High-A. A pair is kept only when the destination stint STARTED no earlier than the source
    stint, so a demotion is never read as a promotion translation.

    ⚠️ There is NO MLB label anywhere in here. That is the entire point: 78% of the Single-A→High-A
    transitions belong to players who never reached MLB, and a graduates-only fit cannot see any of them.
    """
    mcol = f"minor_{metric}"
    if mcol not in pairs.columns:
        raise KeyError(f"pairs has no {mcol!r} column — wrong metric or a pre-E7.3 pairs artifact")
    need = {"player_id", "level", "minor_pa", "first_minor_season"}
    missing = need - set(pairs.columns)
    if missing:
        raise KeyError(
            f"pairs is missing {sorted(missing)} — the ladder needs the as-of MiLB window on EVERY row "
            f"including the never-promoted ones (E7.12-S2's `build_graduated_pairs` adds "
            f"first/last_minor_season). A pre-S2 artifact cannot support the calendar purge.")

    d = pairs[list(need | {"last_minor_season", "debut_cohort", mcol})].copy()
    d["rate"] = pd.to_numeric(d[mcol], errors="coerce")
    d["minor_pa"] = pd.to_numeric(d["minor_pa"], errors="coerce").fillna(0.0)
    d["rank"] = d["level"].map(LEVEL_RANK)
    d = d[d["rank"].notna() & d["rate"].notna() & (d["minor_pa"] >= min_pa)]
    d["rank"] = d["rank"].astype(int)

    keep = ["player_id", "level", "rank", "rate", "minor_pa", "first_minor_season",
            "last_minor_season", "debut_cohort"]
    m = d[keep].merge(d[keep], on="player_id", suffixes=("_src", "_dst"))
    m = m[m["rank_dst"] > m["rank_src"]]
    m = m[pd.to_numeric(m["first_minor_season_dst"], errors="coerce")
          >= pd.to_numeric(m["first_minor_season_src"], errors="coerce")]
    m["adjacent"] = (m["rank_dst"] - m["rank_src"]) == 1
    m["to_reference"] = m["level_dst"] == REFERENCE_LEVEL
    # a pair is only as informative as its thinner side — the harmonic mean, not the sum
    pa_s = m["minor_pa_src"].to_numpy(float)
    pa_d = m["minor_pa_dst"].to_numpy(float)
    m["pair_pa"] = np.where((pa_s > 0) & (pa_d > 0), 2.0 * pa_s * pa_d / (pa_s + pa_d), 0.0)
    # "known by" — the calendar season at which this transition had finished being observed
    m["known_by_season"] = pd.to_numeric(m["last_minor_season_dst"], errors="coerce").fillna(
        pd.to_numeric(m["first_minor_season_dst"], errors="coerce"))
    return m.reset_index(drop=True)


def transition_census(trans: pd.DataFrame) -> pd.DataFrame:
    """Per-rung usable transition counts — ⭐ **REPORTED BEFORE ANY SCORE** (E7.15 readiness lock 2).

    The n-multiplication is the whole premise of H1, and a rung that is thin is a PER-RUNG null rather
    than a failure of the idea. Reporting the counts first is what makes that distinction available
    before a leaderboard exists to rationalise against.
    """
    rows = []
    for (src, dst), g in trans.groupby(["level_src", "level_dst"], dropna=False):
        rows.append({
            "rung": f"{src} -> {dst}",
            "level_src": src, "level_dst": dst,
            "adjacent": bool(g["adjacent"].iloc[0]),
            "to_reference": bool(g["to_reference"].iloc[0]),
            "n_transitions": int(len(g)),
            "n_never_mlb_src": int(g["debut_cohort_src"].isna().sum()),
            "pct_never_mlb": round(100.0 * float(g["debut_cohort_src"].isna().mean()), 1),
            "median_pair_pa": round(float(g["pair_pa"].median()), 1),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["level_src", "level_dst"],
                           key=lambda s: s.map(LEVEL_RANK)).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════════
# Fitting a rung
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RungCoef:
    """One affine translation `dst ≈ a + b · src`, plus how it was obtained."""

    a: float
    b: float
    n: int
    source: str          # fitted | meanshift | identity | identity_thin | identity_degenerate

    @property
    def is_identity(self) -> bool:
        return abs(self.a) < 1e-12 and abs(self.b - 1.0) < 1e-12


_IDENTITY = RungCoef(0.0, 1.0, 0, "identity")


def _wls(x: np.ndarray, y: np.ndarray, w: np.ndarray | None) -> tuple[float, float]:
    """Weighted least squares for `y ≈ a + b·x`. Weights are relative only (normalised away)."""
    if w is None:
        w = np.ones_like(x)
    sw = float(w.sum())
    mx = float((w * x).sum() / sw)
    my = float((w * y).sum() / sw)
    sxx = float((w * (x - mx) ** 2).sum())
    sxy = float((w * (x - mx) * (y - my)).sum())
    b = sxy / sxx if sxx > 0 else 1.0
    return my - b * mx, b


def _fit_rung(sub: pd.DataFrame, spec: LadderSpec, rng: np.random.Generator) -> RungCoef:
    """Fit ONE rung under `spec`'s formulation.

    🪤 **A DEGENERATE FIT MUST NOT SILENTLY BECOME A WILD SLOPE.** With `sxx = 0` (every source rate
    identical, which happens on a thin purged rung) the OLS slope is undefined; returning identity and
    SAYING SO is the honest degradation. Returning `nan` would propagate through the composition and
    NaN the feature, which `has_target` would then quietly reinterpret as an unusable row — i.e. the arm
    would be scored on a different population than the foil.
    """
    n = int(len(sub))
    if spec.mode == "identity":
        return RungCoef(0.0, 1.0, n, "identity")
    if n < spec.min_rung_n:
        return RungCoef(0.0, 1.0, n, "identity_thin")

    x = sub["rate_src"].to_numpy(float)
    y = sub["rate_dst"].to_numpy(float)
    w = sub["pair_pa"].to_numpy(float) if spec.weighted else None
    if w is not None:
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        if w.sum() <= 0:
            w = None

    if spec.mode == "shuffled":
        # ⭐ THE LINK ANCHOR. Permute the DESTINATION rates within the rung: the two marginal
        # distributions are untouched, only the within-player pairing is destroyed. A ladder that still
        # helps after this is not reading "how this player's line changed as he climbed" — it is reading
        # a level re-centring, which the E7.3 level intercepts already own.
        y = y[rng.permutation(len(y))]

    if spec.mode == "meanshift":
        # ⭐ THE MATCHED LEVEL-ONLY FOIL (NF-D15 g′). Slope pinned to 1, so the rung can express the
        # per-level MEAN difficulty difference and NOTHING per-player. If this ties the fitted ladder,
        # the ladder's stated mechanism ("we learn how much a line COMPRESSES between levels") is
        # refuted and what actually happened is level centring.
        if w is None:
            return RungCoef(float(y.mean() - x.mean()), 1.0, n, "meanshift")
        sw = float(w.sum())
        return RungCoef(float((w * y).sum() / sw - (w * x).sum() / sw), 1.0, n, "meanshift")

    a, b = _wls(x, y, w)
    if not (np.isfinite(a) and np.isfinite(b)):
        return RungCoef(0.0, 1.0, n, "identity_degenerate")
    return RungCoef(float(a), float(b), n, "fitted")


@dataclass
class LadderFit:
    """The fitted ladder: per-rung coefficients plus the composed (source level → reference) maps."""

    spec: LadderSpec
    metric: str
    rungs: dict[tuple[str, str], RungCoef] = field(default_factory=dict)
    composed: dict[str, tuple[float, float, str]] = field(default_factory=dict)
    n_transitions_used: int = 0
    fallbacks: list[str] = field(default_factory=list)

    def to_reference(self, level: pd.Series, rate: pd.Series) -> np.ndarray:
        """Express every row's rate at `REFERENCE_LEVEL`. A row already at the reference is unchanged;
        a row at an unknown level is unchanged (documented no-op, never dropped, never fabricated)."""
        lvl = pd.Series(level).astype(object).to_numpy()
        x = pd.to_numeric(pd.Series(rate), errors="coerce").to_numpy(float)
        out = x.copy()
        for lv, (A, B, _src) in self.composed.items():
            m = lvl == lv
            if m.any():
                out[m] = A + B * x[m]
        return out

    def coefficient_table(self) -> pd.DataFrame:
        rows = [{"rung": f"{s} -> {d}", "a": c.a, "b": c.b, "n": c.n, "source": c.source}
                for (s, d), c in self.rungs.items()]
        rows += [{"rung": f"{lv} => {REFERENCE_LEVEL} (composed)", "a": A, "b": B, "n": None,
                  "source": src} for lv, (A, B, src) in self.composed.items()]
        return pd.DataFrame(rows)


def fit_ladder(trans: pd.DataFrame, spec: LadderSpec, metric: str, *,
               exclude_players: frozenset[str] | set[str] = frozenset(),
               cutoff_season: int | None = None,
               seed: int = LADDER_PLACEBO_SEED) -> LadderFit:
    """Fit every rung, then compose each source level's map to the reference level.

    🔒 **LEAKAGE POSTURE (E7.15 readiness lock 4), two guards, one always on.**

    1. **LEAVE-THE-HELD-OUT-PLAYER-OUT, ALWAYS.** `exclude_players` drops every transition belonging to a
       player in the evaluation fold, so no rung map applied to a player was fitted using that player's
       own later-level line. This is slice 1's leave-one-player-out park posture, one mechanism over, and
       it is not optional — it is the specific leakage the readiness pass named.
    2. **CALENDAR PURGE, REGISTERED AS A SENSITIVITY.** Slice 1's rule is that a MiLB-ONLY transform
       touches no MLB label and therefore cannot leak the target, which is why the park/run-environment
       context is estimated over the whole substrate and applied globally. The ladder is the same class
       of transform. Rather than assert that, `cutoff_season` additionally drops any transition that had
       not FINISHED before the held-out debut cohort — an arm scored beside the un-purged one, so the
       question is settled by measurement. ⚠️ It costs real power on the early folds (the substrate
       starts in 2015, so the 2017 fold sees only transitions completed by 2016); that is reported as a
       per-fold rung count, not hidden.
    """
    fit = LadderFit(spec=spec, metric=metric)
    if spec.is_noop:
        return fit

    t = trans
    if exclude_players:
        t = t[~t["player_id"].isin(set(exclude_players))]
    if cutoff_season is not None:
        t = t[pd.to_numeric(t["known_by_season"], errors="coerce") < cutoff_season]
    fit.n_transitions_used = int(len(t))

    rng = np.random.default_rng(seed)
    # ADJACENT rungs are always fitted: `chain` uses them directly and `direct` needs them as the
    # fallback when a (level → reference) cell is too thin.
    for i in range(len(ASC_LEVELS) - 1):
        src, dst = ASC_LEVELS[i], ASC_LEVELS[i + 1]
        sub = t[(t["level_src"] == src) & (t["level_dst"] == dst)]
        fit.rungs[(src, dst)] = _fit_rung(sub, spec, rng)
    if spec.mode == "direct":
        for src in ASC_LEVELS[:-1]:
            if src == REFERENCE_LEVEL:
                continue
            sub = t[(t["level_src"] == src) & (t["level_dst"] == REFERENCE_LEVEL)]
            fit.rungs[(src, REFERENCE_LEVEL)] = _fit_rung(sub, spec, rng)

    for lv in ASC_LEVELS:
        if lv == REFERENCE_LEVEL:
            fit.composed[lv] = (0.0, 1.0, "reference")
            continue
        if spec.mode == "direct":
            c = fit.rungs.get((lv, REFERENCE_LEVEL), _IDENTITY)
            if c.source == "fitted":
                fit.composed[lv] = (c.a, c.b, "direct")
                continue
            fit.fallbacks.append(f"{lv}->{REFERENCE_LEVEL} direct rung {c.source} (n={c.n}) → chain")
        # compose the adjacent rungs upward: y = a2 + b2·(a1 + b1·x) = (a2 + b2·a1) + (b2·b1)·x
        A, B, srcs = 0.0, 1.0, []
        for i in range(LEVEL_RANK[lv], LEVEL_RANK[REFERENCE_LEVEL]):
            c = fit.rungs[(ASC_LEVELS[i], ASC_LEVELS[i + 1])]
            A, B = c.a + c.b * A, c.b * B
            srcs.append(c.source)
            if c.source.startswith("identity_"):
                fit.fallbacks.append(f"{ASC_LEVELS[i]}->{ASC_LEVELS[i + 1]} {c.source} (n={c.n})")
        fit.composed[lv] = (A, B, "chain:" + ",".join(srcs))
    return fit


# ══════════════════════════════════════════════════════════════════════════════════════
# Applying the ladder
# ══════════════════════════════════════════════════════════════════════════════════════


def apply_ladder(pairs: pd.DataFrame, fit: LadderFit, metric: str) -> pd.DataFrame:
    """Rewrite `minor_<metric>` (or attach the delta) under a fitted ladder. Returns a COPY.

    Two shapes, chosen by `spec.as_extra`:
      * REPLACE — `minor_<metric>` becomes the reference-level-equivalent rate. Every row is then on one
        scale, so the pooled learner's per-level slope block has far less work to do.
      * EXTRA   — `minor_<metric>` is untouched and `ladder_delta` carries (ladder − raw). The learner
        reads it as an unpenalized fixed regressor, so the arm NESTS the foil at coefficient 0.

    ⭐ `ladder_delta` is **identically 0 for every reference-level row**, and its per-level MEAN is
    absorbed by the level intercepts E7.3 already fits. What is left for the coefficient to read is the
    WITHIN-level variation — i.e. genuinely per-player ladder content, not a level re-centring. That is
    what makes the EXTRA arm an attributable test rather than a restatement of `A_ladder_meanshift`.

    🔒 The clip is `park_context._RATE_BOUNDS`, the same generous physical band the slice-1 ladder uses,
    so an arm cannot change the LABELLED POPULATION (`has_target` reads `notna` + `minor_pa`, never the
    value). The runner asserts that population identity per fold anyway.
    """
    out = pairs.copy().reset_index(drop=True)
    mcol = f"minor_{metric}"
    if mcol not in out.columns:
        raise KeyError(f"pairs has no {mcol!r} column")
    raw = pd.to_numeric(out[mcol], errors="coerce")
    out[f"{mcol}_preladder"] = raw
    if fit.spec.is_noop:
        out["ladder_delta"] = 0.0
        return out

    lo, hi = _RATE_BOUNDS.get(metric, (-np.inf, np.inf))
    lad = pd.Series(fit.to_reference(out["level"], raw), index=out.index)
    # 🪤 **CLIP ONLY THE ROWS THE LADDER ACTUALLY MOVED, OR THE IDENTITY ANCHOR STOPS BEING AN IDENTITY.**
    # The first version clipped unconditionally. On the raw (pre-context) substrate a handful of very thin
    # level lines sit outside the physical band, so `A_ladder_identity` — whose composed map is exactly
    # `0 + 1·x` — still moved 0.1% of rows and was no longer the byte no-op the plumbing check depends on.
    # It happened to be invisible in the runner (`apply_context` clips to these same bounds first), which
    # is precisely the kind of accidental invariant that breaks the day an upstream stops holding it.
    touched = (lad - raw).abs() > 1e-12
    lad = lad.where(~touched, lad.clip(lower=lo, upper=hi))
    # a row whose rate was NaN stays NaN — the ladder never fabricates a line
    lad = lad.where(raw.notna())
    out["ladder_delta"] = (lad - raw).fillna(0.0)
    if not fit.spec.as_extra:
        out[mcol] = lad
    return out


def ladder_coverage(adjusted: pd.DataFrame, metric: str, fit: LadderFit) -> dict:
    """How much of the population the ladder actually MOVED, and where.

    A ladder whose maps all fell back to identity is byte-identical to the foil and would otherwise be
    reported as "the within-player ladder is a clean null" having never been applied — the repo's
    silent-empty class in a new costume. `pct_rows_moved` is the arm-level tell; the per-level breakdown
    says WHICH rung is inert.
    """
    delta = pd.to_numeric(adjusted.get("ladder_delta"), errors="coerce").fillna(0.0)
    n = len(adjusted)
    moved = (delta.abs() > 1e-12).to_numpy()
    by_level = {}
    for lv, g in adjusted.groupby("level", dropna=False):
        d = pd.to_numeric(g.get("ladder_delta"), errors="coerce").fillna(0.0)
        by_level[str(lv)] = {"n": int(len(g)), "mean_delta": float(d.mean()),
                            "mean_abs_delta": float(d.abs().mean())}
    return {
        "n_rows": int(n),
        "pct_rows_moved": round(100.0 * float(moved.mean()), 2) if n else 0.0,
        "mean_abs_delta": float(delta.abs().mean()) if n else 0.0,
        "max_abs_delta": float(delta.abs().max()) if n else 0.0,
        "n_transitions_used": int(fit.n_transitions_used),
        "n_identity_fallbacks": len(fit.fallbacks),
        "fallbacks": fit.fallbacks[:8],
        "by_level": by_level,
        "composed": {lv: {"a": round(A, 6), "b": round(B, 6), "source": s}
                     for lv, (A, B, s) in fit.composed.items()},
    }
