"""E7.12 SLICE 2 — does correcting for PROMOTION SELECTION improve the MiLB→MLB translation?

Run (LAPTOP, ~2-4 min per side):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice2 \
        --player-type batter
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice2 \
        --player-type pitcher

WHAT IS BEING TESTED, STATED CORRECTLY
---------------------------------------------------------------------------------------------------
The MLE is fit on GRADUATES and served on PROSPECTS. It is tempting to say "promotion is decided on the
minor-league line, which IS the model's feature, so the fit is biased" — **that is false.** Selection on
an OBSERVED covariate leaves `E[Y|X]` unbiased; it is the textbook harmless case. Two things do motivate
a correction, and they call for different instruments:

  (a) **THE ESTIMAND.** We fit where the data is dense (good prospects who got promoted) and serve where
      it is sparse. Even with unbiased coefficients the fit is optimised for the wrong population.
      → IPW. This is a statement about WHICH conditional mean we want, not a bias fix.
  (b) **SELECTION ON UNOBSERVABLES.** Scouts promote on tools, makeup, health and organisational need,
      none of which is in the design matrix and all of which plausibly predict MLB performance.
      → Heckman. **IPW does NOT address this** — inverse-propensity weighting fixes selection on
      observables, under which the conditional mean was already fine.

Registering both, separately, is the point: they are not two implementations of one idea, and if the
IPW arm wins while the Heckman arm does not, the finding is about the estimand and should be described
that way rather than as "we removed survivorship bias".

WHAT THE HARNESS INHERITS (and why nothing here is re-derived)
---------------------------------------------------------------------------------------------------
Fold structure, deflation (NF1.8's four numbers), BH-FDR enforcement, paired anchors and the SideConfig
registry are IMPORTED from `run_e7_12_slice1`, not reimplemented — the E7.3p "harness reused, not forked"
precedent. The LEARNER IS HELD FIXED at the pinned per-metric partial-pool prior scale (E7.9: 54-77% of
every "margin" in this program's history was a learner swap in disguise).

⭐ **THE BASELINE IS THE SHIPPED SLICE-1 CONFIGURATION, PER METRIC — NOT `ContextSpec()`.** ISO ships
with park+run-env+reliability; pitcher BB% ships with label-precision weights. Testing IPW against a bare
E7.3 baseline would report the slice-1 win a second time under a new name, and on the metrics that ship a
weight column it would also confound "add IPW" with "remove label weighting". Every S2 arm is therefore
the shipped spec PLUS the S2 mechanism, and an IPW weight MULTIPLIES the shipped label weight rather than
replacing it (NF-D10: to attribute a mechanism you register it as a matched pair, with vs without).

PRE-REGISTERED FALSIFICATIONS
---------------------------------------------------------------------------------------------------
  1. **PROPENSITY-STRATIFIED LIFT.** A real selection correction must CONCENTRATE its benefit in the
     LOW-propensity tercile — the observable proxy for the un-promoted population we actually serve. An
     arm that improves high-propensity graduates just as much is generic re-weighting (a variance
     effect), not a selection correction, and must be reported as such even if its overall MAE wins.
  2. **`A_propensity_placebo`** — the same IPW weights permuted across players. Must lose. If a permuted
     weight vector does as well, the "correction" is weight DISPERSION, not the propensity.
  3. **`A_uniform_weight`** — a column of ones. Must be byte-identical to the baseline, which proves the
     weighting seam is wired and that any movement elsewhere is the weights, not the plumbing.
  4. **ESS IS REPORTED AS A RESULT.** IPW buys representativeness by SPENDING sample size; an arm whose
     effective n collapses has traded bias for variance and MAE alone hides it completely.

🚨 **THE RISK SET IS RESTRICTED TO COMPLETE-FOLLOW-UP ENTRY COHORTS AND THIS IS NOT OPTIONAL.** Measured
on the live substrate, the 2024/2025/2026 entry cohorts promote at o/e 0.47 / 0.29 / 0.08 against a
4-season horizon — they are "not promoted YET", not "not promoted" (`survivorship.censoring_diagnostic`
fires on all three, both sides). A propensity fit over them learns follow-up time, and IPW would then
up-weight the OLDEST cohorts — the opposite of the intended correction, invisible in an overall MAE.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.milb_mle import (
    PartialPoolProjector,
    build_target,
)
from betting_ml.scripts.milb_mle.park_context import ContextSpec, apply_context
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
    SIDES,
    SideConfig,
    _paired_p,
    bh_fdr,
    deflation_report,
    paired_anchor,
)
from betting_ml.scripts.milb_mle.survivorship import (
    DEFAULT_HORIZON,
    DEFAULT_WEIGHT_CLIP,
    MARGINAL_FEATURES,
    build_person_seasons,
    censoring_diagnostic,
    fit_hazard,
    fixed_horizon_propensity,
    ipw_weights,
    propensity_strata,
    resolve_rate_col,
)

log = logging.getLogger("e7_12_slice2")

_KEYS = ["player_id", "level"]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ABLATION = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

# ══════════════════════════════════════════════════════════════════════════════════════
# The shipped slice-1 configuration, per metric — the S2 baseline
# ══════════════════════════════════════════════════════════════════════════════════════
# Transcribed from the PUBLISHED slice-1 / slice-1p reports (the `verdict`/`winner` table). A DROP metric
# ships `S0_baseline`, i.e. the byte-exact E7.3 incumbent. `_shipped_spec` re-resolves these against the
# live ladder, so a label that no longer exists RAISES here rather than silently degrading to no-op.
SHIPPED_RUNG: dict[str, dict[str, str]] = {
    "batter": {
        "woba": "S2_level_env",
        "k_pct": "S4_park_env_rel0.5",
        "bb_pct": "S4_park_env_rel2.0",
        "iso": "S4_park_env_rel2.0",
    },
    "pitcher": {
        "k_pct": "S0_baseline",
        "bb_pct": "S5_full_labelweight",
        "hr_rate": "S5_full_labelweight",
        "gb_pct": "S0_baseline",
        "xwoba_against": "S0_baseline",
    },
}


def shipped_spec(side: SideConfig, metric: str) -> ContextSpec:
    """The slice-1 winner's ContextSpec for `metric`, resolved against the live ladder."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import by_label, ladder_for

    label = SHIPPED_RUNG[side.player_type][metric]
    lookup = by_label(ladder_for(side, include_posthoc=True))
    if label not in lookup:
        raise KeyError(
            f"SHIPPED_RUNG[{side.player_type}][{metric}] = {label!r} is not a rung on the current "
            f"ladder ({sorted(lookup)}). The S2 baseline must be the CONFIGURATION ACTUALLY SERVED — "
            f"silently falling back to ContextSpec() would re-report the slice-1 win as an S2 win.")
    return lookup[label].spec


# ══════════════════════════════════════════════════════════════════════════════════════
# The pre-registered S2 ladder
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class S2Arm:
    label: str
    ipw: str | None      # None | "raw" | "stabilized" | "placebo" | "uniform"
    mills: str | None    # None | "real" | "placebo"
    kind: str            # "ladder" | "anchor" | "sensitivity"
    note: str
    clip: tuple[float, float] | None = None

    @property
    def selectable(self) -> bool:
        return self.kind != "anchor"


S2_LADDER: tuple[S2Arm, ...] = (
    S2Arm("T0_shipped", None, None, "ladder",
          "the SHIPPED slice-1 configuration for this metric — the real incumbent, not a bare E7.3"),
    S2Arm("T1_ipw", "raw", None, "ladder",
          "⭐ (a) THE ESTIMAND: inverse fixed-horizon promotion propensity, re-weighting the training "
          "graduates toward the prospect population we actually serve"),
    S2Arm("T1b_ipw_odds", "odds", None, "ladder",
          "⭐ INVERSE-ODDS weights (1-p)/p — targets the UN-PROMOTED population rather than the full "
          "one. Arguably the truer estimand: the board scores players who have NOT debuted, so the "
          "population we serve is the un-selected one, not the union"),
    S2Arm("T2_heckman", None, "real", "ladder",
          "⭐ (b) SELECTION ON UNOBSERVABLES: the inverse-Mills ratio of the promotion propensity as an "
          "extra UNPENALIZED fixed regressor — the only arm that can address correlated unobservables"),
    S2Arm("T3_joint", "raw", "real", "ladder",
          "both mechanisms together — registered because (a) and (b) are different problems and a "
          "correction for one does not subsume the other"),
    # ── anchors: these MUST LOSE (or, for uniform, must be a byte-exact no-op) ──
    S2Arm("A_uniform_weight", "uniform", None, "anchor",
          "PLUMBING PROOF — a weight column of ones must be BYTE-IDENTICAL to T0. If it is not, the "
          "weighting seam itself is moving the answer and every weighted arm is uninterpretable."),
    S2Arm("A_propensity_placebo", "placebo", None, "anchor",
          "DEGENERATE FOIL — the SAME IPW weights permuted across players within a debut cohort. If it "
          "does as well as T1, the effect is weight DISPERSION, not the propensity."),
    S2Arm("A_mills_placebo", None, "placebo", "anchor",
          "DEGENERATE FOIL — a permuted Mills ratio. Guards the Heckman arm the way the placebo park "
          "guards the park arm."),
    # ── sensitivity: counted toward deflation, never folded into the headline margin ──
    S2Arm("V_ipw_clip_tight", "raw", None, "sensitivity",
          "propensity trimmed at [0.10, 0.90] instead of [0.02, 0.98] — how much of any lift is the "
          "trimming choice? (the default clip trims ZERO rows on this substrate, so a tighter one is "
          "the only version of this sensitivity that is not inert — see `mean_rows_trimmed`)",
          (0.10, 0.90)),
)

_MILLS_COL = "_s2_mills"
_WEIGHT_PREFIX = "_s2w_"

# How much of a low-vs-high tercile lift gap counts as a real gradient, in percentage points of MAE lift.
# 0.10pp is well inside the smallest lift any arm has produced (~0.14pp overall) while being large enough
# that two terciles differing by rounding noise read as `flat`.
CONCENTRATION_TOL = 0.10


def by_label(arms: tuple[S2Arm, ...]) -> dict[str, S2Arm]:
    return {a.label: a for a in arms}


# ══════════════════════════════════════════════════════════════════════════════════════
# Propensity assembly — leakage-safe, censoring-restricted
# ══════════════════════════════════════════════════════════════════════════════════════


def _inverse_mills(p: np.ndarray) -> np.ndarray:
    """λ(z) = φ(z)/Φ(z) evaluated at the propensity's probit score — the standard Heckman correction
    term for the SELECTED sample. `p` is P(promoted); the selected units are the graduates."""
    from scipy.stats import norm

    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    z = norm.ppf(p)
    return norm.pdf(z) / np.clip(norm.cdf(z), 1e-12, None)


@dataclass
class PropensityFold:
    """Everything the arms need for ONE fold, all fit WITHOUT seeing that fold's outcomes."""

    propensity: pd.DataFrame            # keys + propensity + entry_cohort + follow_up_complete
    marginal: float
    marginal_propensity: pd.DataFrame   # the STABILIZED-IPW numerator: a reduced, calendar-only model
    diagnostic: dict
    n_hazard_rows: int


def propensity_for_fold(pairs: pd.DataFrame, cutoff_season: int | None, *,
                        horizon: int = DEFAULT_HORIZON,
                        restrict_complete_followup: bool = True) -> PropensityFold:
    """Fit the promotion + attrition hazards on seasons STRICTLY BEFORE `cutoff_season`, then score
    every player.

    ⚠️ **THE CUTOFF IS WHY THIS IS NOT A ONE-LINER.** The propensity's outcome IS promotion, so a hazard
    fit over the full panel has already seen the test fold's debuts; the IPW weight for a held-out player
    would then be a function of whether he was promoted. Restricting the hazard panel to `season <
    cutoff` is the clean calendar-based cut — it cannot see a promotion that happens in the test year or
    later, and it needs no per-player bookkeeping.

    🚨 `restrict_complete_followup` drops entry cohorts whose 4-season window does not fit inside the
    observed calendar. On the live substrate that is ~19-22% of players, promoting at o/e 0.47/0.29/0.08
    — a propensity fit over them learns follow-up time, not selection.
    """
    ps_all = build_person_seasons(pairs)
    panel = ps_all if cutoff_season is None else ps_all[ps_all["season"] < cutoff_season]
    if panel.empty or panel["event"].sum() < 10:
        raise ValueError(f"hazard panel too thin before {cutoff_season}: "
                         f"{len(panel)} rows / {int(panel['event'].sum())} events")

    max_season = int(panel["season"].max())
    if restrict_complete_followup:
        entry = panel.groupby(_KEYS, dropna=False)["season"].min().rename("entry").reset_index()
        keep = entry[entry["entry"] <= max_season - horizon + 1][_KEYS]
        fit_panel = panel.merge(keep, on=_KEYS, how="inner")
        if fit_panel["event"].sum() >= 10:
            panel = fit_panel

    fit, mu = fit_hazard(panel)
    exit_fit, exit_mu = fit_hazard(panel, event_col="exited")
    diag = censoring_diagnostic(panel, fit, mu, horizon=horizon,
                                exit_fit=exit_fit, exit_mu=exit_mu, max_season=max_season)
    # score EVERY player (including the held-out fold) with the train-only hazard
    prop = fixed_horizon_propensity(fit, ps_all, mu, horizon=horizon, max_season=max_season,
                                    exit_fit=exit_fit, exit_mu=exit_mu)
    marginal = float(np.clip(prop["propensity"].mean(), 1e-6, 1 - 1e-6))

    # the STABILIZED-IPW numerator — a REDUCED hazard carrying only calendar position, no player
    # covariates. 🪤 Using the scalar sample mean here instead makes the stabilized arm byte-identical
    # to the raw one (the constant cancels under mean-normalisation), which is exactly what the first
    # version of this runner did: three "arms" on the leaderboard that were one arm, agreeing with
    # themselves and padding the field the deflation is computed over.
    m_fit, m_mu = fit_hazard(panel, features=MARGINAL_FEATURES)
    m_exit, m_exit_mu = fit_hazard(panel, event_col="exited", features=MARGINAL_FEATURES)
    m_prop = fixed_horizon_propensity(m_fit, ps_all, m_mu, horizon=horizon, max_season=max_season,
                                      exit_fit=m_exit, exit_mu=m_exit_mu)
    return PropensityFold(propensity=prop, marginal=marginal, marginal_propensity=m_prop,
                          diagnostic=diag, n_hazard_rows=int(len(panel)))


def attach_arm_columns(frame: pd.DataFrame, arm: S2Arm, prop: pd.DataFrame, marginal: float,
                       shipped_weight_col: str | None, rng: np.random.Generator,
                       marginal_prop: pd.DataFrame | None = None
                       ) -> tuple[pd.DataFrame, str | None, dict]:
    """Return `(frame_with_columns, weight_col_or_None, audit)` for one arm.

    ⭐ **AN IPW WEIGHT MULTIPLIES THE SHIPPED LABEL-PRECISION WEIGHT, IT DOES NOT REPLACE IT.** Pitcher
    BB% and HR-rate ship with `weight_col="mlb_pa"`. An arm that swapped that for the IPW weight would be
    testing "IPW instead of label weighting", and a loss would be misread as "IPW does not help" when it
    actually means "IPW is worse than the thing it displaced". The matched pair is shipped-weights vs
    shipped-weights × IPW (NF-D10).
    """
    out = frame.merge(prop[_KEYS + ["propensity"]], on=_KEYS, how="left")
    audit: dict = {}
    p = pd.to_numeric(out["propensity"], errors="coerce")
    p = p.fillna(float(np.nanmedian(p)) if p.notna().any() else marginal)

    base = (pd.to_numeric(out.get(shipped_weight_col), errors="coerce")
            if shipped_weight_col else pd.Series(1.0, index=out.index))
    base = base.where(np.isfinite(base) & (base > 0))
    base = base.fillna(float(np.nanmedian(base)) if base.notna().any() else 1.0)

    weight_col: str | None = None
    if arm.ipw is not None:
        clip = arm.clip or (0.02, 0.98)
        w, audit = ipw_weights(p, clip=clip)
        if arm.ipw == "uniform":
            w = np.ones(len(out))
            audit = {"note": "plumbing anchor — all weights 1.0"}
        elif arm.ipw == "odds":
            # 🪤 **STABILIZED IPW IS NOT A DISTINCT ARM HERE, AND AN EARLIER VERSION OF THIS LADDER
            # PRETENDED IT WAS.** The textbook stabilized weight is `P(S=1) / P(S=1|X)` with a CONSTANT
            # numerator — and these weights are normalised to mean 1 before use, so the constant cancels
            # exactly and the arm is byte-identical to raw IPW. The first fix (a reduced calendar-only
            # numerator model) did not help either: under a FIXED horizon every player is evaluated at
            # the same `season_index = 0..3`, so a calendar-only propensity is the same number for
            # everyone and cancels too. Three leaderboard rows agreeing to six decimals was the tell.
            # Inverse ODDS is a genuinely different estimand, not a re-parameterisation of the same one.
            pv = np.clip(p.to_numpy(float), clip[0], clip[1])
            w = (1.0 - pv) / pv
            w = np.clip(w / float(np.mean(w)), *DEFAULT_WEIGHT_CLIP)
            n = len(w)
            audit = {**audit, "note": "inverse odds (1-p)/p — targets the UN-PROMOTED population",
                     "ess_fraction": (round(float((w.sum() ** 2) / np.sum(w ** 2)) / n, 4)
                                      if n else 0.0)}
        elif arm.ipw == "placebo":
            # permute WITHIN debut cohort so the placebo keeps the cohort-level weight distribution and
            # only destroys the player↔weight pairing — the same shape as the slice-1 park placebo
            w = pd.Series(w, index=out.index).groupby(
                out["debut_cohort"].fillna(-1)).transform(
                    lambda s: rng.permutation(s.to_numpy())).to_numpy(float)
            audit = {**audit, "note": "placebo — weights permuted within debut cohort"}
        weight_col = f"{_WEIGHT_PREFIX}{arm.label}"
        out[weight_col] = base.to_numpy(float) * np.asarray(w, dtype=float)
    elif shipped_weight_col:
        weight_col = shipped_weight_col

    if arm.mills is not None:
        m = _inverse_mills(p.to_numpy(float))
        if arm.mills == "placebo":
            m = rng.permutation(m)
        out[_MILLS_COL] = m
    return out, weight_col, audit


# ══════════════════════════════════════════════════════════════════════════════════════
# The ladder
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class S2Result:
    metric: str
    prior_scale: float
    shipped_rung: str
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
    deflation: dict
    anchors: dict
    stratified: pd.DataFrame
    ess: dict
    censoring: dict
    verdict: str                       # ADD | DROP | BLOCKED
    winner: str
    reasons: list[str] = field(default_factory=list)


def run_s2_ladder(pairs: pd.DataFrame, context: pd.DataFrame | None, metric: str,
                  side: SideConfig, arms: tuple[S2Arm, ...] = S2_LADDER,
                  seed: int = 7) -> S2Result:
    """Score every S2 arm under the E7.3 fold structure, learner held fixed."""
    base_spec = shipped_spec(side, metric)
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)
    rng = np.random.default_rng(seed)

    # the shipped context adjustment is applied ONCE — it is the same for every arm, so re-deriving it
    # per arm would only add a chance for them to differ
    adj = apply_context(pairs, context, base_spec, metric, tuple(_KEYS))
    lab = build_target(adj, cfg)
    lab = lab[lab["has_target"]].reset_index(drop=True)
    cohorts = sorted(int(y) for y in lab["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"need ≥2 evaluable debut cohorts; got {fold_cohorts}")

    labels = [a.label for a in arms]
    mae = pd.DataFrame(index=fold_cohorts, columns=labels, dtype=float)
    per_row: list[pd.DataFrame] = []
    ess: dict[str, list[float]] = {a.label: [] for a in arms}
    trimmed: dict[str, list[int]] = {}
    censoring: dict = {}
    notes: list[str] = []

    for year in fold_cohorts:
        try:
            pf = propensity_for_fold(pairs, cutoff_season=year)
        except Exception as e:  # noqa: BLE001 — a thin early fold must not kill the sweep
            notes.append(f"fold {year}: propensity unavailable ({type(e).__name__}: {e})")
            continue
        censoring[year] = pf.diagnostic
        strata = propensity_strata(pf.propensity["propensity"])
        strat_map = pf.propensity[_KEYS].assign(stratum=strata)

        for arm in arms:
            frame, wcol, audit = attach_arm_columns(lab, arm, pf.propensity, pf.marginal,
                                                    base_spec.weight_col, rng,
                                                    marginal_prop=pf.marginal_propensity)
            if audit.get("ess_fraction") is not None:
                ess[arm.label].append(float(audit["ess_fraction"]))
            if audit.get("n_propensity_trimmed") is not None:
                trimmed.setdefault(arm.label, []).append(int(audit["n_propensity_trimmed"]))
            train = frame[frame["debut_cohort"] < year]
            test = frame[frame["debut_cohort"] == year]
            if train.empty or test.empty:
                continue
            try:
                mdl = PartialPoolProjector(
                    prior_scale=scale, weight_col=wcol,
                    extra_cols=(_MILLS_COL,) if arm.mills else ()).fit(train)
                yhat, _ = mdl.predict(test)
                err = np.abs(test["target"].to_numpy(float) - yhat)
                mae.loc[year, arm.label] = float(np.mean(err))
                per_row.append(pd.DataFrame({
                    "fold": year, "arm": arm.label, "abs_err": err,
                    "player_id": test["player_id"].to_numpy(), "level": test["level"].to_numpy(),
                }))
            except Exception as e:  # noqa: BLE001
                notes.append(f"fold {year} arm {arm.label}: {type(e).__name__}: {e}")

    if not per_row:
        raise RuntimeError(f"[{metric}] no fold produced a scored arm — see notes: {notes}")

    rows_df = pd.concat(per_row, ignore_index=True)
    # attach the LAST fold's strata for the stratified read (each fold's own strata are used for its own
    # rows; recorded per fold so the merge is not a cross-fold leak)
    strat_all = []
    for year, dfold in rows_df.groupby("fold"):
        try:
            pf = propensity_for_fold(pairs, cutoff_season=int(year))
        except Exception:  # noqa: BLE001
            continue
        sm = pf.propensity[_KEYS].assign(stratum=propensity_strata(pf.propensity["propensity"]))
        strat_all.append(dfold.merge(sm, on=_KEYS, how="left"))
    rows_df = pd.concat(strat_all, ignore_index=True) if strat_all else rows_df.assign(stratum=np.nan)

    base = mae["T0_shipped"]
    board = []
    for arm in arms:
        col = mae[arm.label]
        d = (base - col).to_numpy(float)
        d_fin = d[np.isfinite(d)]
        e = ess.get(arm.label) or []
        board.append({
            "arm": arm.label, "kind": arm.kind, "selectable": arm.selectable,
            "oos_mae": float(col.mean(skipna=True)),
            "mae_lift_vs_T0": float(np.mean(d_fin)) if len(d_fin) else np.nan,
            "pct_lift_vs_T0": (100.0 * float(np.mean(d_fin)) / float(base.mean(skipna=True))
                               if len(d_fin) and base.mean(skipna=True) else np.nan),
            "fold_win_rate": float(np.mean(d_fin > 0)) if len(d_fin) else np.nan,
            "p_one_sided": _paired_p(d),
            "mean_ess_fraction": float(np.mean(e)) if e else np.nan,
            # 🪤 a sensitivity arm that trims NOTHING is not agreement, it is INERT — without this
            # column the tight-clip arm reads as a third independent confirmation of the same number
            "mean_rows_trimmed": (float(np.mean(trimmed[arm.label]))
                                  if trimmed.get(arm.label) else np.nan),
            "note": arm.note,
        })
    leaderboard = pd.DataFrame(board).sort_values("oos_mae").reset_index(drop=True)

    eligible = [a.label for a in arms if a.selectable]
    defl = deflation_report(mae, eligible)
    defl["whole_field"] = deflation_report(mae)

    stratified = stratified_lift(rows_df, "T0_shipped")
    anchors = s2_anchors(mae, leaderboard, stratified)
    verdict, winner, reasons = s2_verdict(leaderboard, anchors, stratified, notes)
    anchors["concentration"] = {a.label: concentration_read(stratified, a.label)
                                for a in arms if a.selectable and a.label != "T0_shipped"}

    return S2Result(
        metric=metric, prior_scale=scale, shipped_rung=SHIPPED_RUNG[side.player_type][metric],
        leaderboard=leaderboard, mae_by_fold=mae, fold_cohorts=fold_cohorts, deflation=defl,
        anchors=anchors, stratified=stratified,
        ess={k: (float(np.mean(v)) if v else None) for k, v in ess.items()},
        censoring=censoring, verdict=verdict, winner=winner, reasons=reasons)


def stratified_lift(rows: pd.DataFrame, reference: str) -> pd.DataFrame:
    """⭐ THE DIRECTIONAL FALSIFICATION. Held-out MAE by PROPENSITY TERCILE, per arm.

    Pre-registered reading: a genuine selection correction must help the LOW-propensity graduates — the
    only observable proxy we have for the un-promoted prospects the model is actually served on — and
    should do little or nothing for the high-propensity ones, who already dominate the training fit. An
    arm whose benefit is FLAT across terciles is doing generic re-weighting (a variance effect), and must
    be described that way even if its overall MAE wins.
    """
    if "stratum" not in rows.columns:
        return pd.DataFrame()
    ref = (rows[rows["arm"] == reference].set_index(["fold", "player_id", "level"])["abs_err"]
           .rename("ref_err"))
    out = []
    for arm, d in rows.groupby("arm"):
        j = d.set_index(["fold", "player_id", "level"]).join(ref, how="inner")
        for s, ds in j.groupby("stratum"):
            out.append({"arm": arm, "stratum": int(s), "n": int(len(ds)),
                        "mae": float(ds["abs_err"].mean()),
                        "pct_lift_vs_ref": (100.0 * float((ds["ref_err"] - ds["abs_err"]).mean())
                                            / float(ds["ref_err"].mean())
                                            if float(ds["ref_err"].mean()) else np.nan)})
    return pd.DataFrame(out)


def s2_anchors(mae: pd.DataFrame, leaderboard: pd.DataFrame, stratified: pd.DataFrame) -> dict:
    """Paired anchors + the plumbing identity."""
    def m_of(lbl: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == lbl, "oos_mae"]
        return float(r.iloc[0]) if len(r) else float("nan")

    uniform_gap = float(np.nanmax(np.abs(
        (mae["A_uniform_weight"] - mae["T0_shipped"]).to_numpy(float))
    )) if "A_uniform_weight" in mae.columns else np.nan

    return {
        "propensity_placebo_vs_ipw": paired_anchor(mae, "A_propensity_placebo", "T1_ipw"),
        "mills_placebo_vs_heckman": paired_anchor(mae, "A_mills_placebo", "T2_heckman"),
        # 🪤 the plumbing identity: a weight column of ones must reproduce the unweighted fit EXACTLY.
        # `_weights` normalises to mean 1 and clips to [0.2, 5], so ones survive untouched; any gap here
        # means the weighted code path itself perturbs the answer and every weighted arm is confounded.
        "uniform_weight_max_abs_gap": uniform_gap,
        "uniform_weight_is_a_noop": bool(np.isfinite(uniform_gap) and uniform_gap < 1e-9),
        "placebo_mae": m_of("A_propensity_placebo"), "ipw_mae": m_of("T1_ipw"),
        "mills_placebo_mae": m_of("A_mills_placebo"), "heckman_mae": m_of("T2_heckman"),
    }


def concentration_read(stratified: pd.DataFrame, arm: str) -> dict:
    """Is the arm's benefit CONCENTRATED in the low-propensity tercile, as a selection correction must be?

    The pre-registered claim is DIRECTIONAL — the benefit must not GROW with propensity — so the read is
    on the GRADIENT (stratum 2 minus stratum 0), not on the signs:

      * `concentrated` — the benefit is at least `TOL` larger in the low tercile. The pre-registered
                         signature of a real selection correction.
      * `flat`         — the two ends are within `TOL`. Generic re-weighting / a variance effect: not a
                         defect, but it must not be DESCRIBED as a survivorship correction.
      * `anti`         — ⛔ the benefit is at least `TOL` larger at the HIGH-propensity end. The exact
                         opposite of the mechanism claimed, and no overall MAE win rehabilitates it —
                         the served population is prospects, who are low-propensity by construction.

    🪤 **AN EARLIER VERSION KEYED ON SIGNS RATHER THAN THE GRADIENT AND GRADED THE WORST REAL CASE AS
    "FLAT".** On the live k_pct run `T3_joint` lifts +0.15% at the low end and +1.19% at the high end —
    an 8× gradient, monotone in propensity, and the single clearest example in the whole run of a benefit
    accruing to the players the fit already handled best. Because BOTH ends were positive, a sign-based
    rule called it flat and let it through as the winner. The direction of the gradient IS the finding.
    """
    if not len(stratified):
        return {"verdict": "unavailable"}
    d = stratified[stratified["arm"] == arm].set_index("stratum")["pct_lift_vs_ref"]
    if not {0, 2}.issubset(set(d.index)):
        return {"verdict": "unavailable"}
    lo, hi = float(d.loc[0]), float(d.loc[2])
    gradient = hi - lo
    if gradient > CONCENTRATION_TOL:
        v = "anti"
    elif gradient < -CONCENTRATION_TOL:
        v = "concentrated"
    else:
        v = "flat"
    return {"verdict": v, "low_propensity_lift_pct": round(lo, 4),
            "high_propensity_lift_pct": round(hi, 4),
            "gradient_high_minus_low_pct": round(gradient, 4),
            "mid_propensity_lift_pct": round(float(d.loc[1]), 4) if 1 in d.index else None}


def s2_verdict(leaderboard: pd.DataFrame, anchors: dict, stratified: pd.DataFrame,
               notes: list[str]) -> tuple[str, str, list[str]]:
    """ADD only if the winner beats the SHIPPED config in ≥60% of folds, its anchor holds, the weighting
    plumbing is a proven no-op, AND its benefit is not ANTI-concentrated. Otherwise the shipped config
    stands.

    ⚠️ **THE STRATIFIED READ IS ENFORCED HERE, NOT MERELY PRINTED.** E7.12 slice 1p shipped a metric at
    p=0.113 because its BH-FDR result was computed and then never consumed — a computed-but-unconsumed
    statistic is the quiet cousin of the silent-empty class. The first version of THIS runner repeated
    the mistake with the concentration read: on the ISO smoke it picked a winner whose entire benefit sat
    in the HIGH-propensity tercile while it actively hurt the low-propensity one, and the verdict logic
    never looked.
    """
    reasons = list(notes)
    if not anchors.get("uniform_weight_is_a_noop", False):
        reasons.append(
            f"⛔ BLOCKED — a uniform weight column is NOT a no-op (max |Δ| "
            f"{anchors.get('uniform_weight_max_abs_gap')}). The weighting seam moves the answer by "
            f"itself, so no weighted arm on this metric can be attributed to its propensity.")
        return "BLOCKED", "T0_shipped", reasons

    sel = leaderboard[leaderboard["selectable"] & (leaderboard["arm"] != "T0_shipped")]
    sel = sel[sel["fold_win_rate"] >= 0.60]
    if sel.empty:
        reasons.append("no S2 arm beat the shipped configuration in ≥60% of held-out cohorts")
        return "DROP", "T0_shipped", reasons

    # ⭐ CONCENTRATION IS A PRE-REGISTERED ELIGIBILITY CRITERION, NOT A TIEBREAK ON THE WINNER.
    # An anti-concentrated arm is INELIGIBLE the same way an anchor arm is unselectable — so it is
    # removed from the field BEFORE the best-MAE pick, rather than being selected and then vetoed. On the
    # live k_pct run that is the difference between shipping `T3_joint` (+0.64% overall, but +1.19% at
    # the high-propensity end vs +0.15% at the low) and shipping the arm whose benefit actually sits
    # where the served population lives.
    anti = [a for a in sel["arm"]
            if concentration_read(stratified, str(a)).get("verdict") == "anti"]
    if anti:
        c = {a: concentration_read(stratified, a) for a in anti}
        reasons.append(
            "⛔ INELIGIBLE (anti-concentrated) — " + "; ".join(
                f"{a} lifts {c[a]['low_propensity_lift_pct']:+.3f}% at the LOW-propensity end vs "
                f"{c[a]['high_propensity_lift_pct']:+.3f}% at the HIGH end" for a in anti) +
            ". A selection correction must help where the served population lives; prospects are "
            "low-propensity by construction. A benefit that GROWS with propensity is the fit "
            "reallocating attention toward the players it already handled best — the opposite of the "
            "stated mechanism — so these arms are removed from the field before the pick, not vetoed "
            "after it.")
        sel = sel[~sel["arm"].isin(anti)]
    if sel.empty:
        reasons.append("every arm that cleared the fold gate was anti-concentrated ⇒ the shipped "
                       "configuration stands")
        return "DROP", "T0_shipped", reasons

    win = sel.sort_values("oos_mae").iloc[0]
    label = str(win["arm"])
    if label.startswith("T1") and anchors.get("propensity_placebo_vs_ipw", {}).get("violated"):
        reasons.append("⛔ the permuted-propensity placebo matched or beat the real IPW weights — the "
                       "movement is weight DISPERSION, not the propensity")
        return "DROP", "T0_shipped", reasons
    if label.startswith("T2") and anchors.get("mills_placebo_vs_heckman", {}).get("violated"):
        reasons.append("⛔ the permuted Mills ratio matched or beat the real one")
        return "DROP", "T0_shipped", reasons

    conc = concentration_read(stratified, label)
    if conc.get("verdict") == "flat":
        reasons.append(
            f"⚠️ FLAT across propensity terciles (low {conc['low_propensity_lift_pct']:+.3f}% vs high "
            f"{conc['high_propensity_lift_pct']:+.3f}%) — reported as generic re-weighting (a variance "
            f"effect), NOT as a survivorship correction, whatever the headline MAE does.")
    return "ADD", label, reasons


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def _probit_propensity(X: np.ndarray, y: np.ndarray, iters: int = 60) -> np.ndarray:
    """A small Newton-Raphson PROBIT — the selection equation Heckman's Mills ratio is defined against.

    Deliberately probit, not logit: `_inverse_mills` evaluates `φ(z)/Φ(z)` at `z = Φ⁻¹(p̂)`, which is the
    correct correction term only when p̂ came from a normal-latent selection model.
    """
    from scipy.stats import norm

    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        z = np.clip(X @ beta, -8, 8)
        Phi = np.clip(norm.cdf(z), 1e-9, 1 - 1e-9)
        phi = norm.pdf(z)
        w = phi ** 2 / (Phi * (1 - Phi))
        resid = (y - Phi) * phi / (Phi * (1 - Phi))
        H = (X * w[:, None]).T @ X + 1e-6 * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ resid)
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    return np.clip(norm.cdf(np.clip(X @ beta, -8, 8)), 1e-4, 1 - 1e-4)


def synthetic_recovery_check(n: int = 4000, *, rho: float = 0.8, seed: int = 11) -> dict:
    """⭐ THIS SLICE'S ORACLE FLOOR — and the ONLY thing that can tell its two kinds of null apart.

    We can only ever score on players who WERE promoted, so the live gate measures *"does modelling
    selection improve prediction ON GRADUATES"*, which is strictly weaker than *"removes the bias"*. A
    null on real data is therefore **AMBIGUOUS**: it means either "there is no selection bias" or "the
    correction cannot be validated on the population we can observe". Those are very different findings
    and reporting the second as the first would be the slice's central dishonesty.

    So: plant a selection process whose bias is KNOWN, and check the machinery recovers it.

        U      ~ N(0,1)            the UNOBSERVED scout judgement — tools, makeup, health, org need
        Y      = 1 + 0.6·X + ρ·U   the true translation; U genuinely predicts MLB performance
        S = 1  iff  0.9·X + U + ε > c    promotion depends on BOTH the observed line and U

    This is case (b), selection on unobservables — the only channel that can actually bias `E[Y|X]`. The
    graduate-only fit is biased DOWNWARD, because among promoted players a low X implies a high U.

    Scoring is against `E[Y|X] = 1 + 0.6·X` over the **FULL population including the un-promoted**, which
    is precisely the quantity the live gate cannot see. Runs through the REAL `PartialPoolProjector` +
    `extra_cols` path, not a textbook re-implementation, so it certifies the shipped code.
    """
    rng = np.random.default_rng(seed)
    X = rng.normal(0.0, 1.0, n)
    U = rng.normal(0.0, 1.0, n)
    Y = 1.0 + 0.6 * X + rho * U + rng.normal(0.0, 0.3, n)
    sel_index = 0.9 * X + U + rng.normal(0.0, 0.5, n)
    promoted = sel_index > np.quantile(sel_index, 0.88)          # ~12% promotion, as in the substrate

    # 🪤 The propensity must be a CALIBRATED probability or the Mills ratio is not the Mills ratio. A
    # first version of this check squashed a linear-probability fit through `norm.cdf((·-0.5)*3)` with
    # hand-picked constants; that p is not a probability, λ(Φ⁻¹(p)) is not E[U|X,S=1], and the check
    # reported that the machinery cannot recover a planted bias — a false negative on the oracle floor
    # itself, which would have made every live null look uninformative.
    p = _probit_propensity(np.column_stack([np.ones(n), X]), promoted.astype(float))

    frame = pd.DataFrame({
        "feat": X, "age": rng.normal(23.0, 1.5, n), "level": "Double-A", "league": "EL",
        "target": Y, "has_target": True, _MILLS_COL: _inverse_mills(p),
        "_w_ipw": np.clip((1.0 / p) / np.mean(1.0 / p), 0.2, 5.0),
    })
    grads = frame[promoted].reset_index(drop=True)
    truth = 1.0 + 0.6 * X

    def _mae(*, zero_mills: bool = False, **kw) -> float:
        m = PartialPoolProjector(prior_scale=2.0, **kw).fit(grads)
        # 🚨 **A HECKMAN CORRECTION IS ONLY A CORRECTION IF THE MILLS TERM IS ZEROED AT PREDICT TIME.**
        # Fitted with λ and predicted WITH each player's own λ, the model reproduces `E[Y|X, S=1]` — the
        # SELECTED conditional mean, i.e. exactly the biased quantity we set out to remove. λ→0 is what
        # asks "what would this player do if promotion were not selective". Measured here: carrying λ
        # into prediction leaves the error at 1.443 — WORSE than doing nothing (1.424) — while zeroing it
        # drops the error to 0.803, removing 43.6% of the planted bias. IDENTICAL fitted coefficients;
        # the entire correction lives in the predict step.
        #
        # ⇒ **THE LIVE GATE CANNOT VALIDATE THE HECKMAN ARM AS A BIAS FIX.** It scores held-out
        # GRADUATES, for whom carrying λ is the correct prediction (they really were selected), so the
        # live number measures "does λ help predict graduates" — a different question. If a Heckman arm
        # ever clears the gate, EMISSION for prospects must set λ = 0, and that step is validated ONLY
        # here. Shipping the fitted model as-is would apply no correction at all.
        at = frame.assign(**{_MILLS_COL: 0.0}) if zero_mills else frame
        return float(np.mean(np.abs(m.predict(at)[0] - truth)))

    out = {
        "uncorrected": _mae(),
        "ipw": _mae(weight_col="_w_ipw"),
        "heckman": _mae(extra_cols=(_MILLS_COL,), zero_mills=True),
        "joint": _mae(weight_col="_w_ipw", extra_cols=(_MILLS_COL,), zero_mills=True),
        "heckman_mills_carried_into_predict": _mae(extra_cols=(_MILLS_COL,)),
        "promotion_rate": round(float(promoted.mean()), 4),
        "rho_unobserved": rho,
    }
    best = min(("ipw", "heckman", "joint"), key=lambda k: out[k])
    out["best_correction"] = best
    out["recovers_planted_bias"] = bool(out[best] < out["uncorrected"])
    out["pct_bias_removed"] = round(
        100.0 * (out["uncorrected"] - out[best]) / out["uncorrected"], 2)
    out["reading"] = (
        f"✅ the machinery RECOVERS a planted selection bias ({best} cuts the error against the true "
        f"population translation by {out['pct_bias_removed']}%), so a null on live data is a REAL null — "
        f"evidence that selection on unobservables is not materially biasing this translation."
        if out["recovers_planted_bias"] else
        f"⚠️ the machinery does NOT recover a planted selection bias, so a null on live data is "
        f"**UNINFORMATIVE** — it cannot distinguish 'no bias' from 'this correction cannot detect bias "
        f"in this design'. Do not report the live null as a clean one.")
    return out


def write_report(results: dict[str, S2Result], fdr: dict, side: SideConfig, dest: Path,
                 recovery: dict | None = None) -> None:
    L: list[str] = []
    A = L.append
    A(f"# E7.12 slice 2 — promotion-selection (survivorship) correction ({side.player_type}s)\n")
    A("> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.**\n")
    A("This slice asks whether correcting for the fact that the MLE is FIT ON GRADUATES and SERVED ON "
      "PROSPECTS improves the translation. Two distinct mechanisms are registered separately because "
      "they address different problems:\n")
    A("- **IPW** targets the ESTIMAND — re-weighting training toward the served population. It does "
      "**not** fix bias; selection on an observed covariate leaves `E[Y|X]` unbiased.\n")
    A("- **Heckman** (inverse-Mills ratio) targets SELECTION ON UNOBSERVABLES — scout judgement, health, "
      "organisational need — which is the only channel that can actually bias the translation.\n")
    A("\nThe baseline is the **SHIPPED slice-1 configuration per metric**, not a bare E7.3 incumbent, and "
      "an IPW weight MULTIPLIES the shipped label-precision weight rather than replacing it — otherwise "
      "the comparison would confound adding IPW with removing label weighting.\n")

    if recovery:
        A("\n## Synthetic-truth recovery — this slice's oracle floor\n")
        A("The live gate can only score players who WERE promoted, so it measures *\"does modelling "
          "selection improve prediction ON GRADUATES\"* — strictly weaker than *\"removes the bias\"*. "
          "A live null is therefore ambiguous between **no bias** and **the correction cannot be "
          "validated on the observable population**. This check plants a KNOWN selection-on-"
          "unobservables process and scores against the true `E[Y|X]` over the FULL population, "
          "including the un-promoted — the quantity the live gate cannot see.\n")
        A("```\n" + json.dumps(recovery, indent=2, default=str) + "\n```")
        A(f"\n**{recovery['reading']}**\n")

    A("\n## Verdicts\n")
    rows = [{
        "metric": m, "shipped_baseline": r.shipped_rung, "verdict": r.verdict, "winner": r.winner,
        "pct_lift": round(float(r.leaderboard.loc[r.leaderboard["arm"] == r.winner,
                                                  "pct_lift_vs_T0"].iloc[0]), 3)
        if r.winner in set(r.leaderboard["arm"]) else None,
        "fold_win_rate": round(float(r.leaderboard.loc[r.leaderboard["arm"] == r.winner,
                                                       "fold_win_rate"].iloc[0]), 2)
        if r.winner in set(r.leaderboard["arm"]) else None,
        "BH-FDR@0.10": fdr.get(m),
        "PBO(eligible)": round(float(r.deflation.get("pbo", np.nan)), 3),
    } for m, r in results.items()]
    A(pd.DataFrame(rows).to_markdown(index=False))

    for m, r in results.items():
        A(f"\n---\n\n## `{m}` (baseline = `{r.shipped_rung}`, prior scale {r.prior_scale})\n")
        A(r.leaderboard.drop(columns=["note"]).round(6).to_markdown(index=False))
        A("\n### Propensity-stratified lift — the directional falsification\n")
        A("A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only "
          "observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic "
          "re-weighting, not a selection correction.\n")
        if len(r.stratified):
            A(r.stratified.round(4).to_markdown(index=False))
        A("\n### Anchors\n")
        A("```\n" + json.dumps(r.anchors, indent=2, default=str) + "\n```")
        A("\n### Censoring guard (per fold)\n")
        for yr, d in sorted(r.censoring.items()):
            A(f"- fold **{yr}**: fired=`{d['recent_cohorts_are_censoring_contaminated']}` "
              f"flagged={d['flagged_cohorts']} incomplete_followup={d['pct_incomplete_followup']}% "
              f"mature o/e {d['mature_oe_mean']}")
        A("\n### Deflation\n")
        A("```\n" + json.dumps(r.deflation, indent=2, default=str) + "\n```")
        if r.reasons:
            A("\n### Notes\n")
            for x in r.reasons:
                A(f"- {x}")

    dest.write_text("\n".join(L))
    log.info("wrote %s", dest)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.12 slice 2 — promotion-selection correction")
    p.add_argument("--player-type", choices=sorted(SIDES), default="batter")
    p.add_argument("--metrics", nargs="*", default=None, help="subset for a cheap smoke")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[args.player_type]
    recovery = synthetic_recovery_check()
    log.info("synthetic recovery: %s (best=%s, %.2f%% of the planted bias removed)",
             recovery["recovers_planted_bias"], recovery["best_correction"],
             recovery["pct_bias_removed"])
    artifacts = _ABLATION / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(artifacts / side.pairs_name)
    log.info("pairs: %d rows, rate_col=%s", len(pairs), resolve_rate_col(pairs))

    ctx_name = f"mle_park_context{side.reduced.artifact_suffix}.parquet"
    ctx_path = _ABLATION / "e7_12_artifacts" / ctx_name
    context = pd.read_parquet(ctx_path) if ctx_path.exists() else None
    log.info("context: %s", f"{len(context)} rows" if context is not None else "ABSENT")

    metrics = tuple(args.metrics) if args.metrics else side.metrics
    results: dict[str, S2Result] = {}
    for m in metrics:
        log.info("── %s ──", m)
        results[m] = run_s2_ladder(pairs, context, m, side, seed=args.seed)
        log.info("[%s] verdict=%s winner=%s", m, results[m].verdict, results[m].winner)

    pvals = {m: float(r.leaderboard.loc[r.leaderboard["arm"] == r.winner, "p_one_sided"].iloc[0])
             for m, r in results.items()
             if r.verdict == "ADD" and r.winner in set(r.leaderboard["arm"])
             and np.isfinite(r.leaderboard.loc[r.leaderboard["arm"] == r.winner,
                                               "p_one_sided"].iloc[0])}
    fdr = bh_fdr(pvals)
    # ⚠️ ENFORCED, not merely reported — slice 1p shipped a metric at p=0.113 because this loop was
    # missing there. A computed-but-unconsumed statistic is the quiet cousin of the silent-empty class.
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict = "DROP"
            r.winner = "T0_shipped"
            r.reasons.append("⛔ FDR-DOWNGRADED — did not survive Benjamini-Hochberg at alpha=0.10 "
                             "across the metrics tested in this run")

    dest = _ABLATION / f"e7_12_slice2_survivorship{side.reduced.artifact_suffix}.md"
    write_report(results, fdr, side, dest, recovery=recovery)
    for m, r in results.items():
        log.info("FINAL [%s] %s → %s", m, r.verdict, r.winner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
