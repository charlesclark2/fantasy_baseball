"""opponent_context.py — MLB Edge-E7.15 H2: the OPPONENT / competition-quality adjustment.

⭐ **THIS SLICE EXISTS TO TEST AN ASSERTION NOBODY EVER TESTED.** `build_park_context.py`'s docstring
says of the home/road park-factor ratio:

    "Both buckets contain T's own hitters, so team offensive quality largely cancels; the residual
     difference is the park (**plus the opponent mix, which averages out over a 3-season window**)."

That parenthesis is an untested modelling assumption sitting under a shipped feature. H2 measures it
directly and then asks whether adjusting for it improves translation. **The measurement is the primary
deliverable and it is worth having whichever way the bake-off lands**: if opponent quality genuinely has
near-zero spread, the park slice's assumption is CONFIRMED (and this whole family of "adjust for who he
faced" ideas is dead for a principled reason); if the spread is large, a shipped feature rests on a
false premise regardless of whether the adjustment itself clears a §0.5 gate.

WHAT AN OPPONENT FACTOR IS
--------------------------
For each opponent team-season the player actually faced, the rate that BATTERS posted in that matchup
context, relative to the level-season pooled rate, EB-shrunk toward 1.0 in log space and clamped — then
geometrically averaged across opponents weighted by the player's REAL exposure (PA/TBF) against each.

  * BATTER focal player — his opponents are PITCHING STAFFS, so opponent quality is "how did batters hit
    against team T": high wOBA against T ⇒ T's pitching is weak ⇒ his own line is inflated ⇒ divide.
  * PITCHER focal player — his opponents are LINEUPS, so opponent quality is "how did team T's batters
    hit": high K% by T's batters ⇒ his own K% is inflated ⇒ divide.

Both are measured in the SAME batter-rate vocabulary, which is why one factor table serves both sides;
only the GROUPING KEY differs (opponents-of-T vs T-itself), and that lives in the builder.

🪤 **THE SELF-INFLATION TRAP — why leave-one-out is load-bearing here, not hygiene.** A batter's own hits
are IN his opponents' "runs allowed" bucket. A great hitter therefore makes every team he faced look
WEAKER, and dividing his rate by a weakness he personally created shrinks *him specifically* toward the
mean. Shrinkage toward the mean lowers MAE against a regressed target **whether or not opponent quality
matters at all** — so a non-LOO opponent adjustment would MANUFACTURE the very lift this slice is trying
to measure, and no deflation gate could see it because every fold would agree. This is the exact trap
E7.12 slice 1 caught with `A_park_noloo`, and it is STRONGER here: a park factor's home and road buckets
both contain the player's own team, so self-inclusion largely cancels; an opponent factor has no such
cancellation. Hence `exposure_noloo` ships beside the headline as a labelled diagnostic anchor.

The LOO is at GAME level — the focal player's entire games are removed from the opponent's bucket. That
is coarser than row-level subtraction (it removes his teammates' lines in those games too) but it is the
only form that works identically on both sides: a pitcher's influence on the opposing lineup's numbers is
real but is not a row he owns, so there is nothing to subtract. One mechanism, both sides, provably
self-free.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.park_context import (
    DEFAULT_PF_PSEUDO_PA,
    PF_CLAMP,
    _RATE_BOUNDS,
    exposure_weighted_pf,
    shrink_log_pf,
)

log = logging.getLogger("e7_15.opponent")

# The bucket vocabulary. A SUPERSET of `park_context.REDUCED_FIELDS` — the opponent bucket is always
# measured in BATTER counting stats (both sides), so it additionally needs `hr` and `go`/`ao` to serve
# the pitcher metrics `hr_rate` and `gb_pct`. Declared here rather than widening the park spec, so a
# change for H2 cannot perturb the shipped slice-1 park build.
OPP_FIELDS: tuple[str, ...] = (
    "pa", "ab", "so", "bb", "h", "tb", "hr", "go", "ao", "woba_num", "woba_den")

_DERIVED: dict[str, tuple[str, str, str]] = {
    "_tb_minus_h": ("sub", "tb", "h"),
    "_go_plus_ao": ("add", "go", "ao"),
}

# metric → (numerator field, denominator field), IN BATTER VOCABULARY, for BOTH sides.
# ⚠️ The pitcher entries are deliberately the batter-side mirror of the same physical event: a pitcher's
# `hr_rate` is HR per batter faced, and the opposing lineup's HR per plate appearance is the same
# quantity seen from the other side of the plate. `gb_pct` mirrors GO/(GO+AO) identically.
OPP_RATE_PARTS: dict[str, tuple[str, str]] = {
    "woba": ("woba_num", "woba_den"),
    "k_pct": ("so", "pa"),
    "bb_pct": ("bb", "pa"),
    "iso": ("_tb_minus_h", "ab"),
    "hr_rate": ("hr", "pa"),
    "gb_pct": ("go", "_go_plus_ao"),
}

# ⚠️ `xwoba_against` is DELIBERATELY ABSENT, exactly as in `park_context`: its minor feature IS the E7.2
# AAA-Statcast summary, which has no box-line bucket to form a ratio from. Its opponent arm is therefore
# an honest no-op the runner marks INACTIVE, never a fabricated 1.0.
OPPONENT_METRICS: dict[str, tuple[str, ...]] = {
    "batter": ("woba", "k_pct", "bb_pct", "iso"),
    "pitcher": ("k_pct", "bb_pct", "hr_rate", "gb_pct"),
}

DEFAULT_OPP_WINDOW = 1     # a team's roster turns over every year — quality is a SEASON property,
                           # unlike a park. `--window 3` is registered as a candidate formulation
                           # precisely because 3 is the window the park slice's assertion assumed.
OPPONENT_PLACEBO_SEED = 20260802
OPPONENT_MODES: tuple[str, ...] = ("off", "exposure", "exposure_noloo", "placebo")


@dataclass(frozen=True)
class OpponentSpec:
    """One pre-registered opponent-adjustment formulation. `mode='off'` is the byte-exact no-op foil."""

    mode: str = "off"
    window: int = DEFAULT_OPP_WINDOW
    # ⭐ THE NESTING ARM: keep the raw rate and hand the pooled learner the opponent DELTA as an extra
    # unpenalized fixed regressor, so the arm CONTAINS the foil at coefficient 0 and a win is
    # unambiguously "opponent quality adds information" rather than "dividing by something helps".
    as_extra: bool = False

    def __post_init__(self):
        if self.mode not in OPPONENT_MODES:
            raise ValueError(f"mode={self.mode!r} not in {OPPONENT_MODES}")
        if self.mode == "off" and self.as_extra:
            raise ValueError("mode='off' is the no-op foil — it takes no options, or it is not a foil")
        if self.window < 1:
            raise ValueError("window must be ≥ 1 season")

    @property
    def is_noop(self) -> bool:
        return self.mode == "off"

    @property
    def label(self) -> str:
        if self.is_noop:
            return "no_opponent_adj"
        bits = [self.mode, f"w{self.window}"]
        if self.as_extra:
            bits.append("extra")
        return "+".join(bits)


def _rate(df: pd.DataFrame, prefix: str, metric: str) -> np.ndarray:
    """A rate from a reduced bucket. NaN where the denominator is non-positive — a bucket with no
    denominator has no rate; it does not have rate 0."""
    def raw(name: str) -> np.ndarray:
        col = f"{prefix}_{name}"
        if col not in df.columns:
            return np.zeros(len(df), dtype=float)
        return pd.to_numeric(df[col], errors="coerce").fillna(0.0).to_numpy(float)

    def f(name: str) -> np.ndarray:
        if name in _DERIVED:
            op, left, right = _DERIVED[name]
            return raw(left) - raw(right) if op == "sub" else raw(left) + raw(right)
        return raw(name)

    num, den = OPP_RATE_PARTS[metric]
    n, d = f(num), f(den)
    return np.divide(n, d, out=np.full_like(d, np.nan), where=d > 0)


def opponent_factors_from_buckets(buckets: pd.DataFrame, metrics: tuple[str, ...],
                                  bucket_prefix: str = "o", level_prefix: str = "lv",
                                  pseudo_pa: float = DEFAULT_PF_PSEUDO_PA,
                                  clamp: tuple[float, float] = PF_CLAMP) -> pd.DataFrame:
    """Raw → EB-shrunk opponent factors: `of_m = rate_m(opponent bucket) / rate_m(level-season pooled)`.

    Normalising by the LEVEL-SEASON pooled rate rather than by a global constant is what makes this a
    STRENGTH-OF-SCHEDULE index rather than a re-encoding of the level×season run environment that E7.12
    slice 1 already ships — otherwise the arm would silently duplicate a feature that is live today and a
    win would be unattributable.

    Shrunk toward 1.0 in log space (the correct home for a multiplicative factor — shrinking 1.30 and
    0.77 by the same weight keeps them reciprocal) and clamped; the clamp count is reported by the caller.
    """
    out = buckets.copy().reset_index(drop=True)
    n_eff = pd.to_numeric(out.get(f"{bucket_prefix}_pa"), errors="coerce").fillna(0.0).to_numpy(float)
    for m in metrics:
        raw = _rate(out, bucket_prefix, m)
        base = _rate(out, level_prefix, m)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.divide(raw, base, out=np.full_like(base, np.nan), where=base > 0)
        out[f"of_{m}_raw"] = ratio
        out[f"of_{m}"] = shrink_log_pf(ratio, n_eff, pseudo_pa=pseudo_pa, clamp=clamp)
    out["of_n_eff"] = n_eff
    return out


def exposure_weighted_opponent(exposure: pd.DataFrame, metrics: tuple[str, ...],
                               weight_col: str = "pa",
                               keys: tuple[str, ...] = ("player_id", "level")) -> pd.DataFrame:
    """Collapse per-(player, opponent-season) exposure to ONE factor per (player, level).

    Reuses `park_context.exposure_weighted_pf` verbatim (geometric mean of the log factors, weighted by
    the player's REAL exposure against each opponent, with an uncovered opponent contributing weight ZERO
    rather than a fabricated 1.0). The park slice's advantage — we have per-game logs, so we know exactly
    how many PA the player took against each opponent instead of assuming a balanced schedule — is
    exactly the advantage that lets H2 be measured at all.
    """
    g = exposure_weighted_pf(exposure, metrics=metrics, pf_prefix="of_", weight_col=weight_col,
                             keys=keys)
    return g.rename(columns={"pf_n_park_seasons": "of_n_opponent_seasons"})


def opponent_spread(context: pd.DataFrame, metrics: tuple[str, ...]) -> pd.DataFrame:
    """⭐ **THE PRIMARY DELIVERABLE — a direct measurement of the park slice's untested assertion.**

    "The opponent mix averages out" is a claim about SPREAD. If the per-player exposure-weighted opponent
    factor is ~1.000 for everyone, the claim is true and the whole "adjust for who he faced" family is
    dead for a principled reason. If players differ by several percent, a shipped feature rests on a
    false premise — independently of whether correcting for it clears a §0.5 gate.

    Reported as the p5/p50/p95 of the factor and the implied p95−p5 swing in the metric's own units, so
    the answer is legible without a model.
    """
    rows = []
    for m in metrics:
        col = f"of_{m}_exposure"
        if col not in context.columns:
            continue
        v = pd.to_numeric(context[col], errors="coerce").dropna()
        if v.empty:
            continue
        p5, p50, p95 = (float(np.percentile(v, q)) for q in (5, 50, 95))
        rows.append({
            "metric": m, "n_players": int(len(v)),
            "p5": round(p5, 4), "p50": round(p50, 4), "p95": round(p95, 4),
            "p95_minus_p5_pct": round(100.0 * (p95 - p5), 2),
            "sd_pct": round(100.0 * float(v.std(ddof=0)), 3),
            "pct_players_beyond_1pct": round(100.0 * float((v.sub(1.0).abs() > 0.01).mean()), 1),
            "pct_players_beyond_3pct": round(100.0 * float((v.sub(1.0).abs() > 0.03).mean()), 1),
        })
    return pd.DataFrame(rows)


def split_half_reliability(fac: pd.DataFrame, metrics: tuple[str, ...],
                           keys: tuple[str, ...] = ("player_id", "level"),
                           weight_col: str = "pa") -> pd.DataFrame:
    """⭐ **IS THE OBSERVED SPREAD REAL STRENGTH-OF-SCHEDULE, OR IS IT SAMPLING NOISE?**

    Without this, `opponent_spread` cannot support a claim in EITHER direction. A per-player factor is an
    exposure-weighted average of noisy per-opponent estimates, so it has spread even when every player
    faced identical competition — and reporting that as "the park slice's assertion is refuted" would be
    an artifact of the estimator, not a finding about baseball. (Symmetrically, a small spread that is
    ALSO all noise would not confirm the assertion either.)

    So: split each player's OPPONENT-SEASONS into two halves (alternating by opponent, deterministic),
    build the exposure-weighted factor on each half independently, and correlate the halves across
    players in log space. Spearman-Brown steps that up to the full-length reliability
    `r_full = 2r / (1 + r)`, and `sd_true = sd_observed · sqrt(r_full)` is the noise-corrected spread —
    the number a claim about the assertion should actually be made on.

    This is the disattenuation discipline E7.12 used to refute its own "we're at the label-noise ceiling"
    reading, pointed at a feature instead of a label.

    ⚠️⚠️ **KNOWN DOWNWARD BIAS — READ BEFORE QUOTING A NUMBER FROM THIS.** A league plays a roughly
    BALANCED schedule, which imposes a fixed-sum constraint across a player's opponents: if half his
    schedule was above-average, the remaining half is mechanically pulled below average. So when there is
    no real signal the two halves are ANTI-correlated, and this estimator returns a NEGATIVE reliability
    rather than 0. That is exactly what the live league-normalised factor produces (−0.06 to −0.73), and
    the negativity is itself the fingerprint of a balanced schedule — i.e. evidence FOR "the opponent mix
    averages out", not an estimator failure.

    ⇒ **This number is a valid ONE-SIDED instrument, not a precise reliability.** It can support "there
    is no LARGE within-league component" (a real one would have to overcome the bias to read positive);
    it CANNOT be quoted as "reliability = 0.00" or inverted into a precise `sd_true`. The
    noise-corrected spread it feeds is therefore a LOWER BOUND on how much of the observed spread is
    noise, and is reported as such.

    The POSITIVE CONTROL is what keeps the reading honest: the same estimator on the same rows reads
    +0.36 to +0.48 for the LEVEL-normalised factor, whose large between-league component is shared by
    both halves and so is not subject to the fixed-sum constraint. An instrument that reports "no
    signal" is worth nothing unless it demonstrably reports signal when there is some (NF1.7 (a)).
    """
    if fac.empty:
        return pd.DataFrame()
    d = fac.copy()
    # alternate opponents within each player — deterministic, and balanced by construction so the two
    # halves have comparable exposure (a random split can hand one half all the thin opponents)
    d = d.sort_values(list(keys) + ["opp_team_id", "season"])
    d["_half"] = d.groupby(list(keys), dropna=False).cumcount() % 2
    halves = {}
    for h in (0, 1):
        halves[h] = exposure_weighted_opponent(
            d[d["_half"] == h], metrics=metrics, weight_col=weight_col, keys=keys
        ).set_index(list(keys))
    rows = []
    for m in metrics:
        col = f"of_{m}_exposure"
        a = pd.to_numeric(halves[0].get(col), errors="coerce")
        b = pd.to_numeric(halves[1].get(col), errors="coerce")
        if a is None or b is None:
            continue
        j = pd.concat([np.log(a.where(a > 0)).rename("a"), np.log(b.where(b > 0)).rename("b")],
                      axis=1).dropna()
        if len(j) < 30 or j["a"].std() == 0 or j["b"].std() == 0:
            rows.append({"metric": m, "n_players": int(len(j)), "half_corr": None,
                         "reliability_spearman_brown": None,
                         "note": "too few two-half players to estimate reliability"})
            continue
        r = float(j["a"].corr(j["b"]))
        r_full = (2.0 * r / (1.0 + r)) if r > -1 else np.nan
        rows.append({"metric": m, "n_players": int(len(j)), "half_corr": round(r, 4),
                     "reliability_spearman_brown": round(float(r_full), 4),
                     "signal_share_of_sd": (round(float(np.sqrt(max(r_full, 0.0))), 4)
                                            if np.isfinite(r_full) else None)})
    return pd.DataFrame(rows)


def _permute_within_level(values: pd.Series, levels: pd.Series,
                          seed: int = OPPONENT_PLACEBO_SEED) -> pd.Series:
    """The PLACEBO: permute factors across players WITHIN a level, deterministically. Within-level so
    the placebo keeps each level's own factor distribution — a placebo that shuffles a Triple-A factor
    onto a Single-A player would be testing level mixing, not opponents."""
    rng = np.random.default_rng(seed)
    out = values.copy()
    for _lvl, idx in values.groupby(levels, dropna=False).groups.items():
        idx = pd.Index(idx)
        if len(idx) < 2:
            continue
        out.loc[idx] = values.loc[idx].to_numpy()[rng.permutation(len(idx))]
    return out


def apply_opponent(pairs: pd.DataFrame, context: pd.DataFrame | None, spec: OpponentSpec,
                   metric: str, keys: tuple[str, ...] = ("player_id", "level")) -> pd.DataFrame:
    """Divide `minor_<metric>` by the opponent factor (or attach the delta). Returns a COPY.

    A row with NO opponent context — an unmatched player, a metric with no factor — is a documented
    NO-OP (factor 1.0), never dropped and never fabricated; `opponent_coverage` reports it.

    🪤 **THE CLIP IS APPLIED ONLY TO ROWS THE ADJUSTMENT ACTUALLY MOVED**, so a neutral factor is a byte
    no-op independently of whatever the upstream produced — the same defect H1 shipped and fixed in its
    first cut (clipping unconditionally made its identity anchor stop being an identity).
    """
    out = pairs.copy().reset_index(drop=True)
    mcol = f"minor_{metric}"
    if mcol not in out.columns:
        raise KeyError(f"pairs has no {mcol!r} column — wrong metric or a pre-E7.3 pairs artifact")
    raw = pd.to_numeric(out[mcol], errors="coerce")
    out[f"{mcol}_preopp"] = raw
    out["opp_delta"] = 0.0
    out[f"{mcol}_opp_factor"] = 1.0
    if spec.is_noop:
        return out

    # 🪤 **THE VARIANT IS CHOSEN BY THE CONTEXT PASSED IN, NOT BY THE MODE.** The first cut had
    # `exposure_noloo` look up `of_<m>_exposure_noloo` while the caller had ALREADY normalised that
    # variant onto the canonical name — so the lookup missed, the factor fell back to 1.0, and the
    # SELF-INFLATION ANCHOR became a silent no-op that then "passed". An anchor that cannot act is an
    # anchor that passes on nothing (NF1.7 (a)), and it is the single most load-bearing check in this
    # slice. One canonical column name; the mode controls only the TRANSFORMATION.
    col = f"of_{metric}_exposure"
    if context is not None and not context.empty:
        cols = [c for c in context.columns if c not in keys]
        ctx = context.drop_duplicates(subset=list(keys))[list(keys) + cols]
        out = out.merge(ctx, on=list(keys), how="left", suffixes=("", "_ctx"))
    factor = (pd.to_numeric(out[col], errors="coerce") if col in out.columns
              else pd.Series(np.nan, index=out.index, dtype=float))
    if spec.mode == "placebo":
        factor = _permute_within_level(factor, out["level"])
    factor = factor.where(factor.notna() & (factor > 0), 1.0)
    out[f"{mcol}_opp_factor"] = factor

    adj = raw / factor
    lo, hi = _RATE_BOUNDS.get(metric, (-np.inf, np.inf))
    touched = (adj - raw).abs() > 1e-12
    adj = adj.where(~touched, adj.clip(lower=lo, upper=hi)).where(raw.notna())
    out["opp_delta"] = (adj - raw).fillna(0.0)
    if not spec.as_extra:
        out[mcol] = adj
    return out


def opponent_coverage(adjusted: pd.DataFrame, metric: str) -> dict:
    """How much of the population the opponent adjustment actually MOVED.

    An adjustment whose join is dead is byte-identical to the foil and would otherwise be reported as
    "opponent quality is a clean null" having never been applied — the repo's silent-empty class. This
    is the arm-level tell; `opponent_spread` is the mechanism-level one.
    """
    delta = pd.to_numeric(adjusted.get("opp_delta"), errors="coerce").fillna(0.0)
    fac = pd.to_numeric(adjusted.get(f"minor_{metric}_opp_factor"), errors="coerce").fillna(1.0)
    n = len(adjusted)
    return {
        "n_rows": int(n),
        "pct_rows_moved": round(100.0 * float((delta.abs() > 1e-12).mean()), 2) if n else 0.0,
        "mean_abs_delta": float(delta.abs().mean()) if n else 0.0,
        "max_abs_delta": float(delta.abs().max()) if n else 0.0,
        "factor_p05": round(float(np.nanpercentile(fac, 5)), 5) if n else 1.0,
        "factor_p95": round(float(np.nanpercentile(fac, 95)), 5) if n else 1.0,
        "pct_rows_with_context": round(
            100.0 * float((fac.sub(1.0).abs() > 1e-12).mean()), 2) if n else 0.0,
    }
