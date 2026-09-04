"""run_nf_inj2_rate_permutation.py — NF-INJ2: the §0.5 bake-off for the rate permutation.

⭐ THE PRE-REGISTRATION IS `ablation_results/nf_inj1_preregistration.md`. It was committed during
NF-INJ1, before any arm was scored, and funded by the PM on 2026-08-21. ⛔ It is not edited here
(E2.1-r); everything this run overturns is recorded under a SUPERSEDED marker, verbatim (NF-W7f).

⚖️ `best_alpha = 0` — a projection-quality product; no CLV/ROI claim rides on any of this.
🔒 DEPLOY-HELD. Nothing here serves: `nf_inj2_rate_permutation.SERVED_ARM` stays `"incumbent"` and
`assert_coherent()` refuses a flip that the record does not support. The board rebuild + republish is
a POST-MERGE operator step.

────────────────────────────────────────────────────────────────────────────────────────────────
DESIGN — and the two choices a reader should check first
────────────────────────────────────────────────────────────────────────────────────────────────
**1. Every arm is scored on the IDENTICAL captured fold.** `build_season_projection(capture=…)` runs
the REAL shipped build once per target season and hands back the veteran frame, the learned scores,
the eligibility mask and the fitted `knn_norm` band model. Each arm is then applied to that one frame
through `nf1_model.apply_learned_ordering` — the SHIPPING function, not a re-implementation — so the
arms share common random numbers and differ in the permutation rule and nothing else. A study arm
that re-derived the ordering would be measuring something other than what ships (NF-C0e).

**2. The fold window is INHERITED, not chosen.** Folds are NF1.5's own stage-1 scoring window
(`score_from = 2019` → target seasons 2019–2025), read out of `nf1_5_feature_combination_bakeoff.json`
rather than picked here. That matters because the window is exactly the kind of quantity a study can
tune after seeing a result. The wider 2013–2025 window is reported as a DISCLOSED SENSITIVITY beside
it, together with a per-fold measurement of whether the ordering mechanism could ACT at all on those
seasons (NF-D20: a fold on which the mechanism cannot move the metric is UNINFORMATIVE, never a pass
and never a fail) — because on a season where the learner has no edge over MVP-1's own ordering, NO
permutation rule can help and the comparison says nothing about which rule is better.

Realized outcomes are joined from the NF1.9 veteran band panel, which is the program's walk-forward
authority for this population and carries the load-bearing LEFT JOIN that keeps zero-game seasons as
a real 0 (dropping them is the outcome-conditioning §0 exists to keep out). ⚠️ ONLY `real_fp_ppr` is
taken from the panel — a realized season total, which no model vintage can change. The panel's own
`point`/`proj_games` are NOT used: they are a different build vintage (measured: they disagree with
the captured 2013 build by up to 2.25 games), and mixing vintages is the NF-D10 trap.

RUN ON THE LAPTOP (no Snowflake; reads the local DuckDB + the gitignored artifact caches, which a
fresh worktree must copy in first — NF-INFRA1):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2_rate_permutation
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as RP  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as PC  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RSP  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_inj2")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_PANEL = _ART / "nf1_9_veteran_band_panel"
_STEM = "nf_inj2_rate_permutation"
_NF1_5_REPORT = _REPORT_DIR / "nf1_5_feature_combination_bakeoff.json"

POSITIONS = ("QB", "RB", "WR", "TE")

#: the DISCLOSED wider window. Reported, never selected on.
SENSITIVITY_FOLDS = tuple(range(2013, 2026))

#: reproduction pin. The story's AC asks for 1e-9; the incumbent path is asserted against the served
#: artifact at this tolerance, so a refactor that moved the shipped board could not pass silently.
REPRO_TOL = 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Data
# ══════════════════════════════════════════════════════════════════════════════════════════════
def registered_folds() -> tuple[int, ...]:
    """NF1.5's OWN stage-1 scoring window, read from its report — the window this model was
    selected on. Inherited rather than chosen, so it cannot have been tuned to this result."""
    if not _NF1_5_REPORT.exists():
        raise SystemExit(f"no NF1.5 report at {_NF1_5_REPORT} — run --mode market first")
    s1 = json.loads(_NF1_5_REPORT.read_text()).get("stage1", {})
    tgt = [int(y) for y in (s1.get("target_seasons") or [])]
    if not tgt:
        raise SystemExit("NF1.5 stage1 records no target_seasons — cannot inherit the fold window")
    return tuple(sorted(tgt))


def load_realized(year: int) -> pd.DataFrame:
    """`{player_id -> realized season PPR}` for target season `year`, from the NF1.9 panel.

    Provenance is ASSERTED, not assumed (`base_season == year − 1`), exactly as `run_nf_recal1_level`
    does: this story reads an artifact it did not build, and a panel rebuilt off later data would
    make every number here a number about a different product while nothing downstream noticed."""
    p = _PANEL / f"panel_target{year}.parquet"
    if not p.exists():
        raise SystemExit(
            f"no veteran band panel for {year} at {p} — rebuild it first:\n"
            "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
            "run_veteran_interval_ablation --build-panel")
    d = pd.read_parquet(p)
    base = int(pd.to_numeric(d["base_season"], errors="coerce").dropna().iloc[0])
    if base != int(year) - 1:
        raise SystemExit(
            f"panel_target{year}.parquet is NOT walk-forward (base_season={base}, expected "
            f"{year - 1}). Every number computed from it would be about a different product.")
    d = d[d["position"].astype(str).str.upper().isin(POSITIONS)].copy()
    d["pid"] = d["player_id"].astype(str)
    d["real_fp_ppr"] = pd.to_numeric(d["real_fp_ppr"], errors="coerce")
    # the panel's own point/games are a DIFFERENT build vintage — deliberately not returned (NF-D10)
    return d.loc[d["real_fp_ppr"].notna(), ["pid", "real_fp_ppr"]].drop_duplicates("pid")


def capture_fold(con, year: int, schema: str, selections: dict, base_from: int = 2017) -> dict:
    """Run the REAL shipped build for `year` once and capture what every arm needs."""
    base = year - 1
    inputs = N15.load_inputs(con, sorted(set(list(range(base_from, base)) + [base])), schema)
    cap: dict = {}
    proj = N15.build_season_projection(con, base, year, schema, selections, inputs,
                                       base_from=base_from, market_refresh=False, capture=cap)
    if not cap:
        raise SystemExit(f"fold {year}: the build ran but captured nothing — the veteran "
                         "postprocess hook did not fire, so no arm could be scored")
    cap["year"] = year
    cap["board"] = proj
    cap["realized"] = load_realized(year)
    # MVP-1's own scored point, captured ONCE — it is both the multiset every arm permutes and the
    # FIXED tier anchor for `top_tier_rho`, so every arm is graded on the identical draftable subset
    # (an anchor that moved with the candidate would let each arm pick a friendlier tier).
    cap["mvp1_point"] = SP.score_line(cap["vets"].copy(),
                                      prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)
    return cap


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — ONE reducer for candidates, foils, degenerates and oracles alike
# ══════════════════════════════════════════════════════════════════════════════════════════════
def arm_frame(cap: dict, arm: str, *, score: np.ndarray | None = None) -> pd.DataFrame:
    """Apply `arm` to the captured veteran frame through the SHIPPING ordering function.

    `score` overrides the learned ordering score — that is how the per-form PEEKING ORACLES are
    built (the same form, ordered by the realized outcome), so an oracle is same-form AND same-sample
    by construction and carries none of the capacity confound a separately-FITTED oracle would
    (NF1.7 (b) / NF1.9 (f))."""
    vets = cap["vets"]
    out = M1.apply_learned_ordering(vets, cap["score"] if score is None else score,
                                    positions=cap["positions"], eligible=cap["eligible"], arm=arm)
    out = SP.score_line(out, prefix="proj_")
    out = SP.attach_season_interval(out, band_model=cap["band_model"])
    return out


def score_frame(frame: pd.DataFrame, realized: pd.DataFrame,
                mvp1_point: np.ndarray | None = None) -> dict:
    """Every number this story reports for ONE arm on ONE fold, from ONE reducer — so "the anchors
    answer the same question as the candidates" is a property of the code, not a sentence."""
    f = frame.copy()
    f["pid"] = f["player_id"].astype(str)
    f["_row"] = np.arange(len(f))
    m = f.merge(realized, on="pid", how="inner")
    met = LR.band_metrics(m["proj_fp_ppr"], m["fp_ppr_p10"], m["fp_ppr_p90"], m["real_fp_ppr"])
    m["mvp1_fp"] = np.asarray(mvp1_point, dtype=float)[m["_row"].to_numpy()] \
        if mvp1_point is not None else np.nan
    tier_rho, tier_pooled = M14.top_tier_rho(m, "proj_fp_ppr", real_col="real_fp_ppr",
                                             anchor_col="mvp1_fp", degenerate_zero=True)
    rho_by_pos: dict[str, float] = {}
    for p in POSITIONS:
        d = m[m["position"].astype(str).str.upper() == p]
        if len(d) >= 10:
            a = pd.to_numeric(d["proj_fp_ppr"], errors="coerce")
            b = pd.to_numeric(d["real_fp_ppr"], errors="coerce")
            if a.std() > 0 and b.std() > 0:
                rho_by_pos[p] = round(float(a.corr(b, method="spearman")), 4)
    # coherence is measured on the FULL arm frame, not the scored join — a violation on a row with
    # no realized outcome is still an impossible number on the served board.
    coh = PC.frame_coherence_summary(f)
    per_pos_crps: dict[str, float] = {}
    # ⭐ PER-GROUP COVERAGE AND ITS n, from THIS reducer (NF-INJ2c M6). `band_metrics` is the single
    # reducer every arm, foil, degenerate and oracle passes through, so computing coverage anywhere
    # else would let a candidate and an anchor be scored by two different functions — the exact
    # "two implementations of one rule" class this docstring exists to prevent. The `n` travels with
    # it because NF-D22's floor is DERIVED FROM n and is meaningless without the n it was derived
    # from (⛔ never a flat nominal point-floor).
    per_pos_cov: dict[str, float] = {}
    per_pos_n: dict[str, int] = {}
    for p in POSITIONS:
        d = m[m["position"].astype(str).str.upper() == p]
        if len(d) >= 10:
            per_pos_crps[p] = round(float(np.mean(LR.crps_from_band(
                d["proj_fp_ppr"], d["fp_ppr_p10"], d["fp_ppr_p90"], d["real_fp_ppr"]))), 4)
            pm = LR.band_metrics(d["proj_fp_ppr"], d["fp_ppr_p10"], d["fp_ppr_p90"],
                                 d["real_fp_ppr"])
            if pm.get("coverage80") is not None:
                per_pos_cov[p] = pm["coverage80"]
                per_pos_n[p] = int(pm.get("n") or 0)
    return {
        "crps": met[LR.SELECTION_METRIC], "mae": met.get("mae"),
        "coverage80": met.get("coverage80"), "interval_score80": met.get("interval_score80"),
        "bias": met.get("bias"), "n": met.get("n"),
        "crps_by_position": per_pos_crps,
        "coverage80_by_position": per_pos_cov,
        "coverage_n_by_position": per_pos_n,
        "rho_by_position": rho_by_pos,
        "rho_pooled": (round(float(np.mean(list(rho_by_pos.values()))), 4)
                       if rho_by_pos else None),
        # ⭐ the DRAFTABLE-TIER reading — the metric NF1.5's own bake-off selected on, and therefore
        # the one the pre-registration's "the ordering the bake-off actually validated" names. The
        # full-population ρ above is reported beside it because the two can disagree, and a study
        # that quoted only one of them would be choosing which question to answer after the fact.
        "tier_rho_by_position": {k: round(float(v), 4) for k, v in tier_rho.items()},
        "tier_rho_pooled": (round(float(tier_pooled), 4) if tier_pooled is not None else None),
        "coherence_violating_players": coh["n_violating_players"],
        "coherence_applicable": coh["applicable"],
        "coherence_unevaluable": coh["n_unevaluable"],
        "coherence_by_position": coh["by_position"],
    }


def ordering_decomposition(cap: dict) -> dict:
    """WHERE the winner's ordering change comes from — a labelled DIAGNOSTIC, never a trial.

    The incumbent's served point ordering IS the learned ordering exactly (a monotone within-position
    remap of the point multiset). `rate_permute`'s is not: its served point is `assigned_rate ×
    own_games`, so the ordering becomes a BLEND of the learned rank and expected games. This reports,
    per position and on the draftable tier, the ρ of the learned score, of expected games ALONE, and
    of the MVP-1 point — which is what says whether injecting availability into the ordering helps or
    hurts at a given position.

    ⛔ Diagnostic only. Excluded from the trial field and from the deflation dispersion `V`, because
    an anchor that exists to police the metric must never end up setting the gate's own bar (MH2.1
    (a) — the E2.1-r oracle floor that leaked into a DSR field and made it unclearable)."""
    vets = cap["vets"].copy()
    vets["pid"] = vets["player_id"].astype(str)
    m = vets.assign(_learned=cap["score"], mvp1_fp=cap["mvp1_point"],
                    _games=pd.to_numeric(vets["proj_games"], errors="coerce")).merge(
        cap["realized"], on="pid", how="inner")
    out: dict[str, dict] = {}
    for col, label in (("_learned", "learned_score"), ("_games", "expected_games_alone"),
                       ("mvp1_fp", "mvp1_point")):
        per, _ = M14.top_tier_rho(m, col, real_col="real_fp_ppr", anchor_col="mvp1_fp",
                                  degenerate_zero=True)
        out[label] = {k: round(float(v), 4) for k, v in per.items()}
    return out


def mechanism_activity(cap: dict) -> dict:
    """Can the ORDERING mechanism act on this fold at all? (NF-D20.)

    The learned score's within-position ρ against realized, minus MVP-1's own point ordering ρ. On a
    fold where that is ≤ 0 the learner has no edge over the order MVP-1 already had, so NO permutation
    rule — the incumbent's, this story's, or any other — can improve the board there, and the fold is
    UNINFORMATIVE about which rule is better rather than evidence for either. Reported per fold and
    counted, never used to drop a fold from the registered window."""
    vets = cap["vets"].copy()
    vets["pid"] = vets["player_id"].astype(str)
    m = vets.assign(_learned=cap["score"], mvp1_fp=cap["mvp1_point"]).merge(
        cap["realized"], on="pid", how="inner")
    m = m[np.isfinite(m["_learned"])]
    out: dict[str, float] = {}
    for p in POSITIONS:
        d = m[m["position"].astype(str).str.upper() == p]
        if len(d) < 10:
            continue
        rl = d["_learned"].corr(d["real_fp_ppr"], method="spearman")
        rm = d["mvp1_fp"].corr(d["real_fp_ppr"], method="spearman")
        if pd.notna(rl) and pd.notna(rm):
            out[p] = round(float(rl - rm), 4)
    # …and the SAME question on the DRAFTABLE TIER, which is the metric NF1.5 was selected on.
    tier_l, pooled_l = M14.top_tier_rho(m, "_learned", real_col="real_fp_ppr",
                                        anchor_col="mvp1_fp", degenerate_zero=True)
    tier_m, pooled_m = M14.top_tier_rho(m, "mvp1_fp", real_col="real_fp_ppr",
                                        anchor_col="mvp1_fp", degenerate_zero=True)
    tier_edge = {k: round(float(v - tier_m[k]), 4) for k, v in tier_l.items() if k in tier_m}
    tier_pooled_edge = (round(float(pooled_l - pooled_m), 4)
                        if pooled_l is not None and pooled_m is not None else None)
    edge = round(float(np.mean(list(out.values()))), 4) if out else None
    return {
        "learner_edge_over_mvp1_by_position": out,
        "learner_edge_pooled_full_population": edge,
        "learner_edge_by_position_draftable_tier": tier_edge,
        "learner_edge_pooled_draftable_tier": tier_pooled_edge,
        # the mechanism is "re-order the board by the learned score". It can ACT where that score
        # orders better than the order MVP-1 already had — read on the DRAFTABLE TIER, because that
        # is the metric NF1.5's own selection used. Reported per fold, ⛔ never used to drop a fold
        # from the registered window (that would be choosing the population after the result).
        "mechanism_can_act": (tier_pooled_edge is not None and tier_pooled_edge > 0.0),
        "mechanism_can_act_full_population": (edge is not None and edge > 0.0),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Gates — the pre-registration's §3, computed rather than described
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _srs(lift_by_arm: dict[str, list[float]]) -> dict[str, float]:
    """Per-arm Sharpe of the per-fold lift over the incumbent — the trial population DSR deflates."""
    out: dict[str, float] = {}
    for a, v in lift_by_arm.items():
        d = np.asarray([x for x in v if np.isfinite(x)], dtype=float)
        if len(d) >= 2 and d.std(ddof=1) > 1e-12:
            out[a] = float(d.mean() / d.std(ddof=1))
        elif len(d) >= 2:
            out[a] = 0.0
    return out


def dsr_conv(deltas, trial_srs_for_v, n_trials: int) -> float | None:
    """DSR under the DSR-CONV convention: the pre-registered DEGENERATES stay in `n_trials` (they
    pay full multiplicity) but are excluded from the cross-trial dispersion `V`.

    ⭐ WHY THIS IS COMPUTED HERE INSTEAD OF CALLING `M14.deflated_sharpe`: that function derives the
    trial COUNT from `len(trial_srs)`, so the two channels `SR0 = √V · z(N)` is taxed through cannot
    be set independently. Editing it would change a SHARED instrument other verticals pin (MH2.7's
    lesson (ii)), so the formula is reproduced here — identically — and the whole-field figure is
    reported beside this one from the shared function, exactly as the pre-registration requires.

    ⚠️ The exclusion is NON-MONOTONE and is therefore not a lever: dropping a near-mean arm WIDENS
    the sample variance and RAISES the bar. It is declared forward for the two arms that were named
    degenerate before any score, and for nothing else."""
    from scipy.stats import kurtosis, norm, skew
    d = np.asarray(deltas, dtype=float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 3:
        return None
    sd = float(d.std(ddof=1))
    if sd < 1e-12:
        return None
    sr = float(d.mean()) / sd
    v = np.asarray([x for x in trial_srs_for_v if np.isfinite(x)], dtype=float)
    em = 0.5772156649015329
    if len(v) >= 2 and v.std(ddof=1) > 0 and n_trials >= 2:
        sr0 = float(v.std(ddof=1)) * ((1 - em) * norm.ppf(1 - 1 / n_trials)
                                      + em * norm.ppf(1 - 1 / (n_trials * np.e)))
    else:
        sr0 = 0.0
    g3, g4 = float(skew(d)), float(kurtosis(d, fisher=False))
    denom = 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2
    if denom <= 0:
        return None
    return round(float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(denom))), 4)


def fold_lift(per_fold: dict, arm: str, year: int) -> float:
    """The arm's CRPS lift over the incumbent on one fold. POSITIVE = the arm is better, because
    CRPS is a loss. Written out rather than inlined: a `0.0` lift is falsy, and the compact
    `a and b or nan` idiom would silently turn an exact tie into a MISSING fold — which is the one
    value this study most needs to record, since the pre-registration says a tie still ships."""
    inc = per_fold.get("incumbent", {}).get(year, {}).get("crps")
    cur = per_fold.get(arm, {}).get(year, {}).get("crps")
    if inc is None or cur is None:
        return float("nan")
    return float(inc) - float(cur)


def _dsr_2x2(deltas, srs_all: dict[str, float], winner: str) -> dict:
    """DSR under the declared field vs. the same winner with the single most extreme trial Sharpe
    dropped — reported as a DIAGNOSTIC, never acted on.

    ⛔ NF-W7h: a DSR reached only by deleting the WINNER is inadmissible, so the arm dropped is
    named and the diagnostic refuses to report a figure when that arm IS the winner."""
    # ⭐ THE FIELD SEARCHED IS THE NON-DEGENERATE ONE, to match the binding DSR-CONV figure: the two
    # pre-registered degenerates are ALREADY excluded from `V` there, so "drop the most extreme arm"
    # over the whole field would just re-drop `random_order` and answer a question already answered.
    # The informative question is whether a DECLARED, GENUINE sibling is inflating the dispersion.
    srs = {k: v for k, v in srs_all.items()
           if np.isfinite(v) and k not in RP.DEGENERATE_ARMS}
    if len(srs) < 3:
        return {"evaluable": False, "why": "fewer than 3 finite non-degenerate trial Sharpes"}
    mean = float(np.mean(list(srs.values())))
    far = max(srs, key=lambda k: abs(srs[k] - mean))
    if far == winner:
        return {"evaluable": False, "dropped_arm": far,
                "why": "the most extreme trial Sharpe IS the winner — a DSR reached by deleting it "
                       "would be inadmissible (NF-W7h), so no trimmed figure is reported"}
    kept = [v for k, v in srs.items() if k != far]
    return {
        "evaluable": True, "dropped_arm": far, "dropped_arm_sharpe": round(srs[far], 4),
        "V_declared": round(float(np.var(list(srs.values()), ddof=1)), 4),
        "V_without_dropped_arm": round(float(np.var(kept, ddof=1)), 4),
        # both computed at the DECLARED trial count, so only `V` differs between them — otherwise
        # the comparison would silently mix a dispersion change with a multiplicity change.
        "dsr_declared": dsr_conv(deltas, list(srs.values()), RP.DECLARED_FIELD_SIZE),
        "dsr_without_dropped_arm": dsr_conv(deltas, kept, RP.DECLARED_FIELD_SIZE),
        "note": "⛔ A DIAGNOSTIC, NOT A TRIM. `stratified` and the rest are DECLARED arms; you get "
                "to pre-register a family, you do not get to discover one (MH2.2). The trimmed "
                "figure is reported to identify the LEVER, never to license a re-read of the gate.",
        "reading": "if V falls hard and DSR barely moves, the binding quantity is per-fold NOISE "
                   "(a variance/design problem), NOT multiplicity — and prescribing a coherent "
                   "re-registration would spend a successor on the wrong lever (NF-W7f)",
    }


def deflation(per_fold: dict[str, dict[int, dict]], folds: tuple[int, ...],
              winner: str) -> dict:
    """PBO / DSR / spread / flip distribution over the DECLARED field.

    PBO is computed over the ELIGIBLE set — the six declared arms, the search the selection actually
    ran (MH2) — on NEGATED CRPS, because `cscv_pbo` picks the in-sample ARGMAX and CRPS is a loss.
    Getting that sign wrong would report the field upside-down, so it is asserted by a unit test.

    The NF1.8 triad is reported beside PBO, because a rank statistic alone cannot tell "my pick is
    unstable" from "my pick is tied": the FLIP DISTRIBUTION (which arms win the in-sample halves),
    Bailey's PERFORMANCE DEGRADATION, and the CONTENDER spread (the declared non-degenerate arms)
    beside the whole-field spread."""
    arms = list(RP.ARMS)
    S = np.full((len(arms), len(folds)), np.nan, dtype=float)
    for i, a in enumerate(arms):
        for j, y in enumerate(folds):
            v = per_fold.get(a, {}).get(y, {}).get("crps")
            if v is not None:
                S[i, j] = -float(v)                       # negate: cscv_pbo maximises
    pbo = M14.cscv_pbo(S)
    spread_whole = M14.config_spread(S)
    contenders = [i for i, a in enumerate(arms) if a not in RP.DEGENERATE_ARMS]
    spread_contender = M14.config_spread(S[contenders, :]) if len(contenders) >= 2 else None

    # flip distribution + Bailey degradation over the same balanced splits PBO uses
    import itertools
    n_s = len(folds)
    flips: dict[str, int] = {}
    degr: list[float] = []
    if n_s >= 4:
        half = n_s // 2
        splits = list(itertools.combinations(range(n_s), half))
        if len(splits) > 256:
            step = len(splits) / 256
            splits = [splits[int(i * step)] for i in range(256)]
        for is_cols in splits:
            oos = [c for c in range(n_s) if c not in is_cols]
            with np.errstate(invalid="ignore"):
                ism = np.nanmean(S[:, list(is_cols)], axis=1)
                oosm = np.nanmean(S[:, oos], axis=1)
            if not np.isfinite(ism).any():
                continue
            b = int(np.nanargmax(ism))
            flips[arms[b]] = flips.get(arms[b], 0) + 1
            if np.isfinite(oosm[b]) and np.isfinite(np.nanmax(oosm)):
                best_oos = float(np.nanmax(oosm))
                if abs(best_oos) > 1e-12:
                    degr.append((best_oos - float(oosm[b])) / abs(best_oos))
    total_flips = sum(flips.values()) or 1

    lift = {a: [fold_lift(per_fold, a, y) for y in folds] for a in arms}
    srs_all = _srs(lift)
    srs_nondeg = {a: v for a, v in srs_all.items() if a not in RP.DEGENERATE_ARMS}
    deltas = np.asarray(lift.get(winner, []), dtype=float)
    return {
        "pbo": pbo, "pbo_max": M14.PBO_MAX,
        "spread_whole_field": spread_whole, "spread_contender": spread_contender,
        "flip_distribution": {k: round(v / total_flips, 4) for k, v in
                              sorted(flips.items(), key=lambda kv: -kv[1])},
        "bailey_degradation_pct": (round(float(np.median(degr)) * 100, 3) if degr else None),
        "trial_sharpes": {k: round(v, 4) for k, v in srs_all.items()},
        "dsr_whole_field": M14.deflated_sharpe(deltas, np.asarray(list(srs_all.values()))),
        "dsr_degenerates_excluded_from_v": dsr_conv(deltas, list(srs_nondeg.values()),
                                                    RP.DECLARED_FIELD_SIZE),
        "dsr_min": M14.DSR_MIN,
        # NF-W7f: the 2×2 as a LABELLED DIAGNOSTIC, computed before any remedy is named — and never
        # as a field trim (MH2.2: you get to PRE-REGISTER a family, you do not get to DISCOVER one).
        # It answers "is this a field-composition story or a variance story?", which decides whether
        # a successor should re-register a narrower family or change the design. ⚠️ If dropping the
        # largest-|SR| arm barely moves DSR, the binding quantity is per-fold NOISE, not multiplicity.
        "dsr_2x2_diagnostic": _dsr_2x2(deltas, srs_all, winner),
        "declared_field_size": RP.DECLARED_FIELD_SIZE,
        "degenerates_excluded_from_v": list(RP.DEGENERATE_ARMS),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Anchors — one PEEKING CEILING PER FORM, and the degenerates scored every run
# ══════════════════════════════════════════════════════════════════════════════════════════════
def oracle_arms(cap: dict) -> dict[str, pd.DataFrame]:
    """A peeking oracle for EACH candidate form (NF-D16 g‴).

    A single field-wide ceiling is wrong here for the same reason it was wrong there: the forms
    NEST — `feasibility_clamp` CONTAINS `incumbent` (it is the same permutation under a narrower
    bound) — so a nested form can legitimately beat another form's ceiling, and one shared ceiling
    would veto a real winner as a false metric inversion.

    Each oracle is the SAME form ordered by the REALIZED outcome instead of the learned score, on the
    SAME rows. Same family, same sample, same n — so "peeking can only help" actually holds, with
    none of the capacity confound a separately-fitted oracle carries (NF1.7 (b))."""
    vets = cap["vets"].copy()
    vets["pid"] = vets["player_id"].astype(str)
    real = cap["realized"].set_index("pid")["real_fp_ppr"]
    peek = vets["pid"].map(real).to_numpy(dtype=float)     # NaN where unrealized → sinks, as usual
    return {f"oracle_{a}": arm_frame(cap, a, score=peek)
            for a in RP.ARMS if a not in RP.DEGENERATE_ARMS}


def anchor_audit(scored: dict[str, dict], winner: str) -> dict:
    """Two-sided anchor reading, with the ACTIVITY check the floor needs to mean anything.

    * every pre-registered DEGENERATE must LOSE the winner (NF1.8: a criterion a degenerate wins is
      fatal; a constraint it satisfies is fine, because the metric then eliminates it);
    * the winner must not beat the peeking ceiling OF ITS OWN FORM;
    * ⚠️ and a ceiling that TIES its candidate is INACTIVE, not a refusal (NF-W6d) — a peek that
      cannot move the metric has said nothing, so it is reported as UNINFORMATIVE rather than
      counted as a passed test (NF1.7 (a))."""
    w = scored[winner]["crps"]
    degen = {a: scored[a]["crps"] for a in RP.DEGENERATE_ARMS if a in scored}
    degen_lose = {a: (v is not None and w is not None and v > w) for a, v in degen.items()}
    key = f"oracle_{winner}"
    ceil = scored.get(key, {}).get("crps")
    gap = None if (ceil is None or w is None) else round(float(w - ceil), 4)
    # "active" = the peek actually moved the metric relative to the honest arm. A tie means the
    # anchor pair could not act on this population, not that the form has no headroom.
    active = gap is not None and abs(gap) > 1e-6
    return {
        "degenerates_scored": {a: round(v, 4) for a, v in degen.items() if v is not None},
        "winner_crps": w,
        "every_degenerate_loses": all(degen_lose.values()) if degen_lose else None,
        "degenerate_verdicts": degen_lose,
        "own_form_ceiling": ceil,
        "own_form_ceiling_gap": gap,
        "own_form_ceiling_active": active,
        "own_form_ceiling_respected": (None if not active else bool(w >= ceil)),
        "ceiling_reading": ("UNINFORMATIVE — the peek ties the honest arm, so the anchor pair could "
                            "not act (NF-W6d); it is not evidence in either direction."
                            if not active else "ACTIVE"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The 2026 application — the CURRENT board vintage, per the PM's explicit instruction
# ══════════════════════════════════════════════════════════════════════════════════════════════
def injury_giveback(mvp1: pd.DataFrame, served: pd.DataFrame, arm_board: pd.DataFrame,
                    capped_ids: list[str]) -> dict:
    """NF-INJ1 §7.2's measured target, recomputed for an arm.

    The give-back is `Σ arm_point / Σ mvp1_point − 1` on the injury-capped cohort: MVP-1 applies the
    availability cap to the games AND the line coherently, so anything the ordering step hands back
    above MVP-1's own level is discount that has been un-applied. The incumbent's figure is +36.4%.
    A ratio ABOVE 1 means injured players are being marked back UP — the founding injury priority
    running backwards."""
    def _pts(fr: pd.DataFrame) -> pd.Series:
        f = fr.copy()
        f["pid"] = f["player_id"].astype(str)
        return f.set_index("pid")["proj_fp_ppr"].astype(float)
    m, s, a = _pts(mvp1), _pts(served), _pts(arm_board)
    ids = [i for i in capped_ids if i in m.index and i in a.index]
    if not ids:
        return {"n": 0, "note": "no capped rows resolvable — reported as unevaluable, not as clean"}
    mm, aa = m.loc[ids], a.loc[ids]
    ratios = (aa / mm.replace(0.0, np.nan)).dropna()
    return {
        "n": len(ids),
        "mvp1_total": round(float(mm.sum()), 1),
        "arm_total": round(float(aa.sum()), 1),
        "giveback_pct": round(float(aa.sum() / mm.sum() - 1.0) * 100, 2),
        "median_point_ratio": round(float(ratios.median()), 4) if len(ratios) else None,
        # ⚠️ TOLERANCED. A bare `> 1.0` counts floating-point noise as a scale-up: `mvp1_null` moves
        # no point at all and still reported 4 players "scaled up", and the count drifted run to run
        # for the real arms. The same class of defect as the constant-ratio correlation above.
        "n_scaled_up": int((ratios > 1.0 + 1e-9).sum()),
        "n_scaled_down": int((ratios < 1.0 - 1e-9).sum()),
        "served_giveback_pct": (round(float(s.loc[ids].sum() / mm.sum() - 1.0) * 100, 2)
                                if all(i in s.index for i in ids) else None),
    }


def availability_gradient(mvp1: pd.DataFrame, arm_board: pd.DataFrame) -> dict:
    """ρ(expected games, point ratio) over the whole board — NF-INJ1 §7.2's **−0.213**.

    ⚠️ The pre-registration is explicit that this is a PRECONDITION, ⛔ NOT a discriminator: a
    successful arm drives it to ~0 BY CONSTRUCTION, so it must not be presented as evidence one arm
    beat another. It is reported because it is the direct measurement of the defect."""
    from scipy.stats import spearmanr
    a, m = arm_board.copy(), mvp1.copy()
    for d in (a, m):
        d["pid"] = d["player_id"].astype(str)
    j = m[["pid", "proj_games", "proj_fp_ppr", "is_rookie"]].merge(
        a[["pid", "proj_fp_ppr"]], on="pid", suffixes=("_m", "_a"))
    j = j[(~j["is_rookie"].astype(bool)) & (j["proj_fp_ppr_m"] > 1e-6)]
    ratio = j["proj_fp_ppr_a"] / j["proj_fp_ppr_m"]
    if len(j) < 10:
        return {"n": len(j), "rho": None, "p": None, "evaluable": False,
                "why": "fewer than 10 comparable rows"}
    # ⚠️ A CORRELATION AGAINST A CONSTANT IS NOT A MEASUREMENT. `mvp1_null` leaves every point
    # EXACTLY where MVP-1 had it, so its ratio is identically 1 and a Spearman over it is computed
    # entirely on floating-point noise — the first cut of this function reported **+0.1476** for that
    # arm, a number with no content whatsoever. An unevaluable statistic is reported as unevaluable,
    # never as a value (NF1.7 (a)).
    moved = float(np.abs(ratio - 1.0).max())
    if moved < 1e-6:
        return {"n": int(len(j)), "rho": None, "p": None, "evaluable": False,
                "max_abs_ratio_move": moved,
                "why": "the arm moves no point — the ratio is constant, so a rank correlation over "
                       "it would be computed on floating-point noise"}
    r, p = spearmanr(j["proj_games"], ratio)
    return {"n": int(len(j)), "rho": round(float(r), 4), "p": float(p), "evaluable": True,
            "max_abs_ratio_move": round(moved, 6)}


def placement_read(mvp1: pd.DataFrame, arm_board: pd.DataFrame) -> dict:
    """The pre-registration's §4 placement question, on the BUILD FRAME.

    ⚠️ SCOPE, stated because NF-TR2b's own lesson is that this is easy to overclaim: the SERVED
    boards rank by **VOR per league config**, while this ranks by PPR — the same gap that let a
    `standard_12` rookie-cap breach sit in production unnoticed. So this is the build-frame reading,
    NOT the published-artifact read, and the full per-config read against the published artifact
    (`run_nf_tr2b_placement_read`) remains an operator gate before any publish.

    The rookie cap is DELEGATED to `season_projection.rookie_placement_breach` (NF-D18/D20's owner)
    rather than transcribed, so the threshold cannot drift out of sync with it; cross-position
    movement is measured with `level_recalibration`'s shared reducer for the same reason.

    ⭐ AND IT IS RUN AT ALL because the NF-W8-0 VOR "shield" does NOT apply here: that shield holds
    for an ADDITIVE per-position level shift, whose effect a position's own replacement level
    absorbs. This correction is not additive — it re-levels each row by a RATIO — so it can reorder
    across positions, and under the two superflex configs QB is cross-pooled, which is the position
    this arm moves most."""
    a, m = arm_board.copy(), mvp1.copy()
    for d in (a, m):
        d["pid"] = d["player_id"].astype(str)
    j = m[["pid", "position", "proj_fp_ppr", "is_rookie"]].merge(
        a[["pid", "proj_fp_ppr"]], on="pid", suffixes=("_m", "_a"))
    ranked = a.sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    rk = ranked[ranked["is_rookie"].astype(bool)]
    best = int(rk.index.min()) + 1 if len(rk) else None
    breach = SP.rookie_placement_breach(best)
    move = LR.cross_position_movement(j["proj_fp_ppr_m"].to_numpy(dtype=float),
                                      j["proj_fp_ppr_a"].to_numpy(dtype=float),
                                      j["position"].to_numpy(), top_n=100)
    within = LR.ordering_movement(j["proj_fp_ppr_m"].to_numpy(dtype=float),
                                  j["proj_fp_ppr_a"].to_numpy(dtype=float),
                                  j["position"].to_numpy())
    return {
        "reading": "BUILD FRAME, ranked by PPR — ⛔ NOT the served per-config VOR read (NF-TR2b)",
        "best_rookie_overall_rank": best,
        "rookie_cap_breach": breach.get("breach"),
        "rookie_cap_detail": breach,
        "cross_position_movement_top100": move,
        "within_position_movement": within,
    }


def apply_2026(con, schema: str, selections: dict, arms: tuple[str, ...],
               base_from: int = 2017) -> dict:
    """Build the FULL 2026 board (veterans + rookies) under each arm and measure what ships.

    The board is rebuilt per arm rather than spliced, because the placement read is a whole-board
    cross-position question and the rookie leg must sit in it exactly as it does on the wire."""
    mvp1 = pd.read_parquet(_ART / "nfl_fantasy_season_projections_2026.parquet")
    served_path = _ART / "nf_inj2_baseline" / "served_nf1_5_2026.parquet"
    served = pd.read_parquet(served_path) if served_path.exists() else None
    # ⭐ THE INJURY-CAPPED COHORT IS READ FROM THE CAP'S OWN INPUT, not inferred from the board.
    # `injury_availability_games` caps a player iff his `proj_status` is in
    # `_INJURY_STATUS_GAMES_CAP` (RES / PUP / NFI / SUS), and `proj_status` is trimmed from the
    # board's output columns — so asking `load_forward_roster_status` is asking the cap what it
    # actually acted on. Inferring the cohort from a games ratio would silently include every other
    # availability mechanism (the mover, the env tilt, NF-D11's return prior) and attribute their
    # movement to the injury cap.
    status = RSP.load_forward_roster_status(con, 2026)
    flagged = status[status["proj_status"].astype(str).str.upper().isin(
        SP._INJURY_STATUS_GAMES_CAP)]
    board_ids = set(mvp1["player_id"].astype(str))
    capped_ids = [x for x in flagged["player_id"].astype(str).tolist() if x in board_ids]
    cohort_source = ("load_forward_roster_status(2026).proj_status ∈ "
                     f"{sorted(SP._INJURY_STATUS_GAMES_CAP)} — the cap's own input")
    out: dict = {"cohort_source": cohort_source, "n_capped": len(capped_ids),
                 "board_generated_at": str(mvp1["generated_at"].iloc[0])[:25],
                 "arms": {}}
    inputs = N15.load_inputs(con, sorted(set(list(range(base_from, 2025)) + [2025])), schema)
    for arm in arms:
        board = N15.build_season_projection(con, 2025, 2026, schema, selections, inputs,
                                            base_from=base_from, market_refresh=False, arm=arm)
        coh = PC.frame_coherence_summary(board)
        ids = {(v.get("id"), v.get("name")) for v in coh["violations"]}
        rec = {
            "coherence_violating_players": coh["n_violating_players"],
            "coherence_violations": coh["n_violations"],
            "coherence_by_position": coh["by_position"],
            "coherence_applicable": coh["applicable"],
            "coherence_unevaluable": coh["n_unevaluable"],
            "worst_violations": [
                {k: v[k] for k in ("name", "stat", "implied_per_game",
                                   "max_ever_per_game", "expected_games")}
                for v in coh["violations"][:5]],
            "injury_giveback": injury_giveback(mvp1, served if served is not None else board,
                                               board, capped_ids),
            "availability_gradient": availability_gradient(mvp1, board),
            "clamp_saturation_high": int((pd.to_numeric(board["nf1_scale"], errors="coerce")
                                          >= 3.4999).sum()),
            "clamp_saturation_low": int((pd.to_numeric(board["nf1_scale"], errors="coerce")
                                         <= 0.3001).sum()),
            "n_rows": int(len(board)),
            "placement": placement_read(mvp1, board),
            "_violating_keys": sorted(f"{i}|{n}" for i, n in ids),
        }
        out["arms"][arm] = rec
        board.to_parquet(_ART / "nf_inj2_baseline" / f"board_2026_{arm}.parquet", index=False)
        log.info("2026 %-26s violations=%2d giveback=%+.1f%% gradient_rho=%s",
                 arm, rec["coherence_violating_players"],
                 rec["injury_giveback"].get("giveback_pct") or float("nan"),
                 rec["availability_gradient"]["rho"])
    # ⭐ ATTRIBUTION, by CONTROL rather than by scope declaration. `mvp1_null` is the ordering step
    # switched entirely OFF, so any violation it ALSO produces is a defect of the underlying MVP-1
    # board and cannot be caused by a permutation rule. Subtracting it is what separates "this arm
    # leaves an impossible row" from "the board already had one" — and the pre-registration puts the
    # rookie path (`rookie_projection`'s `fp_target` vs its slot-bucket games, NF-INJ1 §2.2/§5c) OUT
    # OF SCOPE precisely because it is a different code path with its own registration. Both the raw
    # and the attributable count are reported, so a reader can apply either.
    baseline_keys = set(out["arms"].get("mvp1_null", {}).get("_violating_keys", []))
    for arm, rec in out["arms"].items():
        own = set(rec.pop("_violating_keys", []))
        rec["coherence_violations_also_present_with_ordering_OFF"] = sorted(own & baseline_keys)
        rec["coherence_violating_players_attributable"] = len(own - baseline_keys)
    out["attribution_control"] = (
        "violations also produced by `mvp1_null` (the ordering step OFF) are subtracted — a defect "
        "present with the mechanism disabled is not caused by the mechanism")

    # the incumbent's 2026 board must reproduce the SERVED artifact — the reproduction pin.
    if served is not None and "incumbent" in arms:
        inc = pd.read_parquet(_ART / "nf_inj2_baseline" / "board_2026_incumbent.parquet")
        a, b = inc.copy(), served.copy()
        for d in (a, b):
            d["pid"] = d["player_id"].astype(str)
        j = b[["pid", "proj_fp_ppr", "proj_games"]].merge(a[["pid", "proj_fp_ppr", "proj_games"]],
                                                          on="pid", suffixes=("_s", "_r"))
        worst = max(float((j[f"{c}_s"] - j[f"{c}_r"]).abs().max())
                    for c in ("proj_fp_ppr", "proj_games"))
        out["reproduction_pin"] = {
            "n": int(len(j)), "worst_abs_diff": worst, "tolerance": REPRO_TOL,
            "reproduces": bool(worst <= REPRO_TOL),
            "note": "the incumbent arm rebuilt through this story's code vs the SERVED 2026 "
                    "artifact — if this does not hold, every arm delta is measured against a "
                    "board nobody is served (the CLV / NF-INJ1 stale-vintage trap)",
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Verdict
# ══════════════════════════════════════════════════════════════════════════════════════════════
def verdict(*, winner: str, pooled: dict, defl: dict, anchors: dict, bh: dict,
            fold_clause: dict, coherence_ok: bool, ordering: dict,
            foil_refutes: bool | None) -> dict:
    """The pre-registration's §6, computed. Each branch NAMES the reading it corresponds to, so a
    reader can check the verdict against the document rather than against this code."""
    dsr = defl.get("dsr_degenerates_excluded_from_v")
    pbo = defl.get("pbo")
    ordering_ok = ordering.get("not_regressed")
    gates = {
        "pbo_ok": (pbo is not None and pbo < defl["pbo_max"]),
        "dsr_ok": (dsr is not None and dsr >= defl["dsr_min"]),
        "bh_ok": bool(bh.get(winner_key(winner))) if bh else None,
        "fold_consistency_ok": fold_clause.get("passes"),
        "degenerates_lose": anchors.get("every_degenerate_loses"),
        "own_form_ceiling_ok": anchors.get("own_form_ceiling_respected"),
        "ordering_not_regressed": ordering_ok,
        "coherence_restored": coherence_ok,
    }
    beats = pooled.get("mean_lift_vs_incumbent")
    band = pooled.get("tie_band", 0.0)
    wins = beats is not None and beats > band
    ties = beats is not None and abs(beats) <= band

    regressed = [p for p, sig in (ordering.get("regression_significant_by_position") or {}).items()
                 if sig]
    if regressed:
        # ⭐ THE PRE-REGISTRATION'S §6 THIRD BRANCH, and the classification matters as much as the
        # refusal. The ordering constraint is BREACHED at a named position by an amount that is
        # DISTINGUISHABLE FROM NOISE — so this is a CONSTRAINT the arm fails, not a shortage of
        # evidence. ⛔ NO "more seasons" re-test trigger: more folds would make a real regression
        # MORE significant, not less, so publishing a data trigger here is the actively-misleading
        # direction NF-D18 warns about.
        state = "CONSTRAINT_REFUSED"
        why = (f"the pre-registered ORDERING constraint is breached at {', '.join(regressed)} by a "
               f"margin distinguishable from noise — §6 branch 3: do not ship")
    elif not coherence_ok:
        state = "NULL"
        why = ("the arm does not restore coherence, which is the correctness constraint the whole "
               "story exists to satisfy")
    elif wins or ties:
        # §6 branches 1 and 2 BOTH ship, and branch 2 is written down in advance precisely so it
        # cannot look like a post-hoc rescue: a TIE on the selecting metric still ships, because
        # coherence is a correctness constraint the INCUMBENT FAILS. That is the
        # pricing-vs-discrimination family rule, ⛔ not the E2.1-r inversion.
        blocking = [k for k in ("degenerates_lose", "coherence_restored",
                                "ordering_not_regressed") if gates[k] is False]
        state = "SHIP" if not blocking else "SHIP_WITH_CAVEAT"
        why = ("wins the selecting metric" if wins else
               "TIES the selecting metric — and a tie SHIPS under the pre-registration's §6 second "
               "branch, because the incumbent fails a correctness constraint this arm satisfies")
    else:
        state = "NULL"
        why = "loses the selecting metric"

    # the DSR reading, stated in its own right: `SR < SR0` means NO fold count clears the bar,
    # because n enters only through √(n−1) — it SCALES a positive gap and cannot CREATE one
    # (NF-W8-0d's lockstep invariant). Calling that "power-limited" would prescribe seasons that
    # can never help.
    srs = defl.get("trial_sharpes") or {}
    w_sr = srs.get(winner)
    nd = [v for k, v in srs.items() if k not in RP.DEGENERATE_ARMS]
    from scipy.stats import norm as _norm
    em, n = 0.5772156649015329, defl["declared_field_size"]
    sr0 = (float(np.std(nd, ddof=1)) * ((1 - em) * _norm.ppf(1 - 1 / n)
                                        + em * _norm.ppf(1 - 1 / (n * np.e)))
           if len(nd) >= 2 else None)
    dsr_reading = {
        "winner_sharpe": w_sr, "benchmark_SR0": (round(sr0, 4) if sr0 is not None else None),
        "state": ("DSR_UNREACHABLE" if (w_sr is not None and sr0 is not None and w_sr <= sr0)
                  else "REACHABLE"),
        "note": ("SR ≤ SR0 in THIS declared field ⇒ no fold count clears the bar (n enters only "
                 "through √(n−1), which scales a positive gap and cannot create one — NF-W8-0d). "
                 "⛔ Do NOT publish a season/fold re-test trigger for it."
                 if (w_sr is not None and sr0 is not None and w_sr <= sr0) else
                 "a positive SR − SR0 gap exists; more folds would scale it"),
    }
    return {"state": state, "why": why, "gates": gates,
            "mean_lift_vs_incumbent": beats, "tie_band": band,
            "beats_the_selecting_metric": bool(wins), "ties_the_selecting_metric": bool(ties),
            "ordering_regressed_at": regressed,
            "dsr_reading": dsr_reading,
            "no_more_data_trigger": True,
            "no_more_data_trigger_why":
                "the binding refusal is a pre-registered CONSTRAINT the arm breaches, and the DSR "
                "shortfall is unreachable at any n — neither is rescued by more seasons (NF-D18)",
            "matched_foil_refutes_mechanism": foil_refutes,
            "mechanism_reading": (
                "the matched foil (`rate_permute_games_frozen`) LOSES while the primary wins ⇒ the "
                "lift is the PER-PLAYER AVAILABILITY channel, which is the stated mechanism "
                "(NF-D15 g′)" if foil_refutes is False else
                "the matched foil wins as much as the primary ⇒ the per-player availability channel "
                "is REFUTED as the mechanism; the win is a level effect" if foil_refutes else
                "unevaluable")}


def winner_key(winner: str) -> str:
    return winner


def _fmt(v, nd: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _md_table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_(none)_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return "\n".join(out) + "\n"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Driver
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(con, schema: str, folds: tuple[int, ...], selections: dict, *,
        base_from: int = 2017, do_2026: bool = True) -> dict:
    t0 = time.time()
    per_fold: dict[str, dict[int, dict]] = {a: {} for a in RP.ALL_ARMS}
    per_fold.update({f"oracle_{a}": {} for a in RP.ARMS if a not in RP.DEGENERATE_ARMS})
    activity: dict[int, dict] = {}
    fold_n: dict[int, int] = {}

    for y in folds:
        cap = capture_fold(con, y, schema, selections, base_from=base_from)
        activity[y] = mechanism_activity(cap)
        activity[y]["ordering_decomposition"] = ordering_decomposition(cap)
        frames = {a: arm_frame(cap, a) for a in RP.ALL_ARMS}
        frames.update(oracle_arms(cap))
        for name, fr in frames.items():
            per_fold.setdefault(name, {})[y] = score_frame(fr, cap["realized"],
                                                           mvp1_point=cap["mvp1_point"])
        fold_n[y] = per_fold["incumbent"][y]["n"]
        log.info("fold %d: n=%d incumbent CRPS %.4f · %s CRPS %.4f · viol %d→%d · act %s",
                 y, fold_n[y], per_fold["incumbent"][y]["crps"], RP.PRIMARY_ARM,
                 per_fold[RP.PRIMARY_ARM][y]["crps"],
                 per_fold["incumbent"][y]["coherence_violating_players"],
                 per_fold[RP.PRIMARY_ARM][y]["coherence_violating_players"],
                 activity[y]["mechanism_can_act"])

    def _mean(arm: str, key: str):
        v = [per_fold[arm][y][key] for y in folds
             if y in per_fold.get(arm, {}) and per_fold[arm][y].get(key) is not None]
        return round(float(np.mean(v)), 4) if v else None

    scored = {a: {k: _mean(a, k) for k in
                  ("crps", "mae", "coverage80", "interval_score80", "rho_pooled")}
              for a in per_fold}
    for a in scored:
        scored[a]["coherence_violating_players"] = int(sum(
            per_fold[a][y]["coherence_violating_players"] for y in folds if y in per_fold[a]))
        scored[a]["folds_won_vs_incumbent"] = int(sum(
            1 for y in folds if np.isfinite(fold_lift(per_fold, a, y))
            and fold_lift(per_fold, a, y) > 0))

    winner = RP.PRIMARY_ARM
    lifts = np.asarray([fold_lift(per_fold, winner, y) for y in folds], dtype=float)
    lifts = lifts[np.isfinite(lifts)]
    # the tie band is a DESIGN quantity fixed before the result: the per-fold standard error of the
    # winner's own lift. A |mean lift| inside its own noise is a TIE, which under §6 still ships —
    # so the band is deliberately derived from dispersion, never chosen to reach a verdict.
    tie_band = (round(float(lifts.std(ddof=1) / np.sqrt(len(lifts))), 4)
                if len(lifts) >= 2 else 0.0)
    pooled = {
        "mean_lift_vs_incumbent": round(float(lifts.mean()), 4) if len(lifts) else None,
        "per_fold_lift": {int(y): round(fold_lift(per_fold, winner, y), 4) for y in folds},
        "folds_won": int((lifts > 0).sum()), "n_folds": len(lifts),
        "tie_band": tie_band,
        "tie_band_note": "the per-fold SE of the winner's own lift — a dispersion quantity fixed "
                         "by the design, not a threshold chosen to reach a verdict",
    }
    defl = deflation(per_fold, folds, winner)
    anchors = anchor_audit(scored, winner)
    # ⛔ NEVER the raw 0.60 rate — that clause has a different false-fire rate at every fold count
    # (0.50 at n=3), i.e. it is nearly free at the low end (MH2 H8). `fold_consistency_clause`
    # bounds it by design and declares itself UNDEFINED rather than passed when it cannot.
    fc = cv_power.fold_consistency_clause(len(folds))
    required = getattr(fc, "wins_required", None)
    fold_clause = {
        "n_folds": len(folds), "required_wins": required,
        "attained_false_fire": getattr(fc, "attained_false_fire", None),
        "legacy_wins_required": getattr(fc, "legacy_wins_required", None),
        "legacy_false_fire": getattr(fc, "legacy_false_fire", None),
        "alpha": getattr(fc, "alpha", None),
        "observed_wins": pooled["folds_won"],
        "passes": (None if required is None else bool(pooled["folds_won"] >= required)),
    }

    # BH-FDR across the four position searches (the pre-registration's "across positions")
    pvals: dict[str, float | None] = {}
    for p in POSITIONS:
        d = []
        for y in folds:
            i = per_fold["incumbent"][y]["crps_by_position"].get(p)
            w = per_fold[winner][y]["crps_by_position"].get(p)
            if i is not None and w is not None:
                d.append(i - w)
        pvals[p] = M14.onesided_paired_pvalue(np.asarray(d, dtype=float)) if len(d) >= 3 else None
    bh_pos = M14.bh_fdr(pvals, q=M14.FDR_Q)

    # ordering constraint + coherence precondition
    #
    # ⭐ THE CONSTRAINT IS READ ON THE DRAFTABLE TIER, and that is a choice worth stating rather than
    # burying: the pre-registration says the ordering constraint is "what the original NF1.5 bake-off
    # actually validated", and NF1.5 selected on `top_tier_rho` — per-position Spearman restricted to
    # the top-N by the MVP-1 anchor. The FULL-POPULATION ρ is computed and reported beside it, because
    # the two can disagree and a study that quoted only one would be choosing its question after
    # seeing the answer. If they disagree the report says so.
    def _mean_pos(arm: str, key: str, pos: str):
        v = [per_fold[arm][y][key][pos] for y in folds
             if pos in per_fold.get(arm, {}).get(y, {}).get(key, {})]
        return round(float(np.mean(v)), 4) if v else None

    ord_by_pos, ord_full_by_pos = {}, {}
    for p_ in POSITIONS:
        w_t, i_t = _mean_pos(winner, "tier_rho_by_position", p_), \
            _mean_pos("incumbent", "tier_rho_by_position", p_)
        if w_t is not None and i_t is not None:
            ord_by_pos[p_] = (w_t, i_t)
        w_f, i_f = _mean_pos(winner, "rho_by_position", p_), \
            _mean_pos("incumbent", "rho_by_position", p_)
        if w_f is not None and i_f is not None:
            ord_full_by_pos[p_] = (w_f, i_f)
    ordering_ok_strict = (all(w >= i - 1e-9 for w, i in ord_by_pos.values())
                          if ord_by_pos else None)
    ordering_ok_full = (all(w >= i - 1e-9 for w, i in ord_full_by_pos.values())
                        if ord_full_by_pos else None)
    # ⭐ THE READING, and it is stated because the pre-registration left it open — which means the
    # rule has to be fixed on DESIGN grounds and shown both ways, not chosen once the number is
    # visible (E2.1-r).
    #
    # A STRICT per-position point-estimate bar (`ρ_winner ≥ ρ_incumbent` at every position) is a
    # COIN FLIP on a noisy statistic no matter how many folds you have — the NF-D22 lesson exactly:
    # more data buys the power to detect a SMALLER true regression, it does not lower the
    # false-refusal rate of a point-floor sitting at nominal. With four positions the family-wise
    # false-refusal rate of the strict reading is worse still.
    #
    # The pre-registration calls this a CONSTRAINT — a bar the arm must not BREACH — not a selector.
    # So the binding reading is: no position shows a regression DISTINGUISHABLE FROM NOISE, tested
    # as a one-sided paired t-test on the per-fold (incumbent − winner) tier-ρ deltas and
    # BH-corrected across the four positions at the SAME q the deflation gate already uses. Both
    # readings are reported, so a reader who prefers the strict one can apply it.
    ord_regression_p: dict[str, float | None] = {}
    for p_ in ord_by_pos:
        d = []
        for y in folds:
            wv = per_fold[winner][y]["tier_rho_by_position"].get(p_)
            iv = per_fold["incumbent"][y]["tier_rho_by_position"].get(p_)
            if wv is not None and iv is not None:
                d.append(iv - wv)          # POSITIVE = the winner is WORSE at this position
        ord_regression_p[p_] = (M14.onesided_paired_pvalue(np.asarray(d, dtype=float))
                                if len(d) >= 3 else None)
    ord_regression_sig = M14.bh_fdr(ord_regression_p, q=M14.FDR_Q)
    ordering_ok = (None if not ord_regression_p
                   else not any(bool(v) for v in ord_regression_sig.values()))
    coherence_ok = scored[winner]["coherence_violating_players"] == 0

    foil = RP.MATCHED_FOIL
    foil_lift = np.asarray([fold_lift(per_fold, foil, y) for y in folds], dtype=float)
    foil_lift = foil_lift[np.isfinite(foil_lift)]
    foil_mean = round(float(foil_lift.mean()), 4) if len(foil_lift) else None
    foil_refutes = (None if (foil_mean is None or pooled["mean_lift_vs_incumbent"] is None)
                    else bool(foil_mean >= pooled["mean_lift_vs_incumbent"] - 1e-9))

    ordering_block = {
        "metric": "top_tier_rho (the metric NF1.5's own bake-off selected on)",
        "by_position_winner_vs_incumbent": ord_by_pos, "not_regressed": ordering_ok,
        "binding_reading": "no position shows a regression distinguishable from noise (one-sided "
                           "paired t on per-fold tier-ρ deltas, BH across the four positions at "
                           f"q={M14.FDR_Q}) — a strict point-estimate bar at nominal is a coin flip "
                           "at any n (NF-D22)",
        "regression_pvalues": ord_regression_p,
        "regression_significant_by_position": ord_regression_sig,
        "strict_point_estimate_reading": ordering_ok_strict,
        "full_population_by_position": ord_full_by_pos,
        "full_population_not_regressed": ordering_ok_full,
        "readings_agree": (None if ordering_ok is None or ordering_ok_full is None
                           else bool(ordering_ok == ordering_ok_full)),
    }
    vd = verdict(winner=winner, pooled=pooled, defl=defl, anchors=anchors, bh=bh_pos,
                 fold_clause=fold_clause, coherence_ok=coherence_ok, ordering=ordering_block,
                 foil_refutes=foil_refutes)

    nullcls = None
    if vd["state"] not in ("SHIP", "SHIP_WITH_CAVEAT"):
        try:
            srs = defl.get("trial_sharpes") or {}
            v_nondeg = [x for a_, x in srs.items() if a_ not in RP.DEGENERATE_ARMS]
            v_all = list(srs.values())
            nullcls = cv_power.classify_null(
                metric=LR.SELECTION_METRIC, n_folds=len(folds), n_arms=RP.DECLARED_FIELD_SIZE,
                # ⭐ MH2.7: `declared_field_size` makes "this narrow field was DECLARED, not
                # discovered" an AUDITABLE CLAIM — the instrument then refuses to prescribe a field
                # SMALLER than the declaration, which would re-commit the very selection bias DSR
                # exists to deflate. Read `field_remedy_admissible`, ⛔ never the prose.
                declared_field_size=RP.DECLARED_FIELD_SIZE,
                beats_foil=bool((pooled["mean_lift_vs_incumbent"] or 0.0) > 0.0),
                observed_sr=(float(np.mean(lifts) / lifts.std(ddof=1))
                             if len(lifts) >= 2 and lifts.std(ddof=1) > 1e-12 else None),
                var_trials_sr=(float(np.var(v_nondeg, ddof=1)) if len(v_nondeg) >= 2 else None),
                var_trials_sr_with_degenerates=(float(np.var(v_all, ddof=1))
                                                if len(v_all) >= 2 else None),
                degenerates_excluded_from_v=True,
                fold_wins=pooled["folds_won"],
                p_one_sided=M14.onesided_paired_pvalue(lifts),
                bh_cutoff=M14.FDR_Q)
        except TypeError as e:      # the instrument's signature is shared across verticals
            nullcls = {"error": f"classify_null signature mismatch: {e}"}

    return {
        "story": "NF-INJ2", "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0, "elapsed_s": round(time.time() - t0, 1),
        "folds": list(folds), "fold_rows": fold_n,
        "fold_window_provenance": "inherited from NF1.5 stage-1 `score_from` — not chosen here",
        "selections": {p: s["learner"] for p, s in selections.items()},
        "declared_field": list(RP.ARMS), "matched_foil": foil,
        "degenerates": list(RP.DEGENERATE_ARMS),
        "leaderboard": scored, "per_fold": {a: {int(y): v for y, v in d.items()}
                                            for a, d in per_fold.items()},
        "mechanism_activity": {int(y): v for y, v in activity.items()},
        "pooled": pooled, "deflation": defl, "anchors": anchors,
        "fold_consistency": fold_clause,
        "bh_fdr": {"pvalues": pvals, "survives": bh_pos, "q": M14.FDR_Q},
        "ordering": ordering_block,
        "coherence_restored": coherence_ok,
        "matched_foil_mean_lift": foil_mean,
        "verdict": vd, "null_classification": nullcls,
    }


def write_report_md(rep: dict, path: Path) -> None:
    L: list[str] = []
    a = L.append
    v = rep["verdict"]
    a("# NF-INJ2 — permute the per-game RATE, not the season POINT\n")
    a(f"**VERDICT: {v['state']}** — {v['why']}. `best_alpha = 0`. "
      f"Generated {rep['generated_at'][:19]}Z in {rep['elapsed_s']}s.\n")
    a("> Pre-registration: `nf_inj1_preregistration.md` (committed during NF-INJ1, before any arm "
      "was scored; PM-funded 2026-08-21). ⛔ Not edited by this run — E2.1-r.\n")
    a("> 🔒 DEPLOY-HELD: `nf_inj2_rate_permutation.SERVED_ARM` is still `\"incumbent\"`. Nothing "
      "here serves until the PM records a disposition.\n")

    a("\n## 1. The field, as declared\n")
    a(f"Folds **{rep['folds'][0]}–{rep['folds'][-1]}** ({len(rep['folds'])}), "
      f"{rep['fold_window_provenance']}. Declared field **{len(rep['declared_field'])}** arms + the "
      f"matched foil `{rep['matched_foil']}`; pre-registered degenerates "
      f"`{'`, `'.join(rep['degenerates'])}`.\n")
    rows = []
    for arm, m in rep["leaderboard"].items():
        rows.append({"arm": arm, "CRPS": m["crps"], "MAE": m["mae"], "cov80": m["coverage80"],
                     "ρ (pooled)": m["rho_pooled"],
                     "coherence violations": m["coherence_violating_players"],
                     "folds beating incumbent": m["folds_won_vs_incumbent"]})
    rows.sort(key=lambda r: (r["CRPS"] is None, r["CRPS"]))
    a(_md_table(rows, ["arm", "CRPS", "MAE", "cov80", "ρ (pooled)", "coherence violations",
                       "folds beating incumbent"]))
    a("\n⛔ **CRPS selects. MAE never does** — the target is skewed and the low-availability cohort "
      "is exactly where the conditional median sits near the floor (NF-D11 / NF-D14). It is "
      "disclosed, not used.\n")
    a("⚠️ **The coherence column is a PRECONDITION, not a discriminator.** The pre-registration says "
      "so in advance: `rate_permute` satisfies it by construction, so it must not be presented as "
      "evidence that it beat anything. It is reported for EVERY arm — including the degenerates — "
      "because a constraint a degenerate satisfies is fine (the metric then eliminates it), while a "
      "criterion a degenerate WINS would be fatal (NF1.8).\n")

    a("\n## 2. The primary vs the incumbent\n")
    p = rep["pooled"]
    a(f"Mean CRPS lift **{_fmt(p['mean_lift_vs_incumbent'])}** over {p['n_folds']} folds, winning "
      f"**{p['folds_won']}/{p['n_folds']}**. Tie band ±{_fmt(p['tie_band'])} "
      f"({p['tie_band_note']}).\n")
    a(_md_table([{"fold": y, "lift": l} for y, l in p["per_fold_lift"].items()], ["fold", "lift"]))
    a("\n### Matched foil — is the mechanism what we say it is?\n")
    a(f"`{rep['matched_foil']}` mean lift **{_fmt(rep['matched_foil_mean_lift'])}** vs the primary's "
      f"**{_fmt(p['mean_lift_vs_incumbent'])}**.\n\n{v['mechanism_reading']}\n")

    a("\n## 3. Gates\n")
    d = rep["deflation"]
    a(_md_table([
        {"gate": "PBO (eligible = the declared field)", "value": d["pbo"],
         "bar": f"< {d['pbo_max']}", "verdict": v["gates"]["pbo_ok"]},
        {"gate": "DSR (degenerates ∉ V, n_trials = declared)",
         "value": d["dsr_degenerates_excluded_from_v"], "bar": f"≥ {d['dsr_min']}",
         "verdict": v["gates"]["dsr_ok"]},
        {"gate": "DSR (whole field, reported beside it)", "value": d["dsr_whole_field"],
         "bar": f"≥ {d['dsr_min']}", "verdict": "—"},
        {"gate": "fold consistency", "value": rep["fold_consistency"].get("observed_wins"),
         "bar": f"≥ {rep['fold_consistency'].get('required_wins')} wins",
         "verdict": v["gates"]["fold_consistency_ok"]},
        {"gate": "BH-FDR across positions", "value": json.dumps(rep["bh_fdr"]["survives"]),
         "bar": f"q = {rep['bh_fdr']['q']}", "verdict": v["gates"]["bh_ok"]},
        {"gate": "ordering not regressed (draftable tier)", "value": json.dumps(
            rep["ordering"]["by_position_winner_vs_incumbent"]), "bar": "ρ ≥ incumbent",
         "verdict": v["gates"]["ordering_not_regressed"]},
        {"gate": "ordering not regressed (full population, disclosed)", "value": json.dumps(
            rep["ordering"]["full_population_by_position"]), "bar": "ρ ≥ incumbent",
         "verdict": rep["ordering"]["full_population_not_regressed"]},
        {"gate": "coherence restored", "value": rep["leaderboard"][RP.PRIMARY_ARM][
            "coherence_violating_players"], "bar": "= 0",
         "verdict": v["gates"]["coherence_restored"]},
    ], ["gate", "value", "bar", "verdict"]))
    a(f"\nNF1.8 triad beside PBO — a rank statistic alone cannot tell an unstable pick from a tied "
      f"one: flip distribution `{json.dumps(d['flip_distribution'])}`, Bailey performance "
      f"degradation **{_fmt(d['bailey_degradation_pct'], 3)}%**, contender spread "
      f"**{_fmt(d['spread_contender'])}** against a whole-field spread of "
      f"**{_fmt(d['spread_whole_field'])}** (the whole-field figure includes this field's own "
      f"declared degenerates, so it measures the degenerates — MH2/NF1.8).\n")
    a(f"\nTrial Sharpes: `{json.dumps(d['trial_sharpes'])}`.\n")

    a("\n## 4. Anchors\n")
    an = rep["anchors"]
    a(f"- Degenerates scored every run and READ, not reasoned about: "
      f"`{json.dumps(an['degenerates_scored'])}` against the winner's "
      f"**{_fmt(an['winner_crps'])}** ⇒ every degenerate loses: **{an['every_degenerate_loses']}**.\n")
    a(f"- Own-form peeking ceiling (one PER FORM — the forms nest, so a single field-wide ceiling "
      f"would veto a legitimately better nested form, NF-D16 g‴): **{_fmt(an['own_form_ceiling'])}**, "
      f"gap **{_fmt(an['own_form_ceiling_gap'])}**, respected **{an['own_form_ceiling_respected']}**. "
      f"{an['ceiling_reading']}\n")

    a("\n## 5. Could the mechanism act? (NF-D20)\n")
    a("A fold on which the learner has no edge over MVP-1's own ordering is UNINFORMATIVE about "
      "which permutation rule is better — no rule can improve a board there. Counted, never used to "
      "drop a fold from the registered window.\n")
    a(_md_table([{"fold": y,
                  "edge (draftable tier)": m["learner_edge_pooled_draftable_tier"],
                  "edge (full population)": m["learner_edge_pooled_full_population"],
                  "mechanism can act": m["mechanism_can_act"]}
                 for y, m in rep["mechanism_activity"].items()],
                ["fold", "edge (draftable tier)", "edge (full population)",
                 "mechanism can act"]))
    a("\n⭐ The two readings can disagree, and on this population they do: the learner's edge lives "
      "on the DRAFTABLE TIER (the metric NF1.5 was selected on), not over the full veteran "
      "population. That is worth knowing before reading any wide-window sensitivity — on a season "
      "where the ordering mechanism has no edge, no permutation rule can improve the board and the "
      "fold is uninformative about which rule is better.\n")

    if rep.get("application_2026"):
        app = rep["application_2026"]
        a("\n## 6. The 2026 board — the CURRENT served vintage\n")
        a(f"Built off `generated_at` **{app['board_generated_at']}**, the vintage on the wire. "
          f"Injury-capped cohort n=**{app['n_capped']}** (`{app['cohort_source']}`).\n")
        rp_ = app.get("reproduction_pin")
        if rp_:
            a(f"\n**Reproduction pin:** the incumbent arm rebuilt through this story's code matches "
              f"the SERVED artifact to **{rp_['worst_abs_diff']:.2e}** over {rp_['n']} rows "
              f"(tolerance {rp_['tolerance']:.0e}) ⇒ **{rp_['reproduces']}**. {rp_['note']}\n")
        res = rep.get("coherence_residual_on_served_board") or {}
        if res:
            a(f"\n⭐ **ATTRIBUTION BY CONTROL, not by scope declaration.** `mvp1_null` is the "
              f"ordering step switched entirely OFF, so any violation it ALSO produces is a defect "
              f"of the underlying MVP-1 board that no permutation rule can be causing. The primary "
              f"leaves **{res.get('raw_violating_players')}** raw violating row(s), of which "
              f"**{res.get('attributable_to_this_arm')}** are attributable to it. The residual "
              f"is `{', '.join(res.get('also_present_with_ordering_off') or []) or 'none'}`, a "
              f"ROOKIE produced by `rookie_projection`'s own `fp_target` ↔ slot-bucket-games "
              f"decoupling — a different code path that the pre-registration puts explicitly OUT OF "
              f"SCOPE (§5; NF-INJ1 §2.2/§5c).\n")
        a(_md_table([{"arm": k,
                      "impossible rows": r["coherence_violating_players"],
                      "…attributable": r.get("coherence_violating_players_attributable"),
                      "injury give-back %": r["injury_giveback"].get("giveback_pct"),
                      "median point ratio": r["injury_giveback"].get("median_point_ratio"),
                      "n scaled UP": r["injury_giveback"].get("n_scaled_up"),
                      "n scaled DOWN": r["injury_giveback"].get("n_scaled_down"),
                      "ρ(games, ratio)": r["availability_gradient"]["rho"],
                      "clamp hi/lo": f"{r['clamp_saturation_high']}/{r['clamp_saturation_low']}"}
                     for k, r in app["arms"].items()],
                    ["arm", "impossible rows", "…attributable", "injury give-back %",
                     "median point ratio", "n scaled UP", "n scaled DOWN", "ρ(games, ratio)",
                     "clamp hi/lo"]))
        a("\n⚠️ ρ(games, ratio) → ~0 is a PRECONDITION the primary satisfies by construction, ⛔ not "
          "a discriminator between arms (pre-registration §1).\n")

        pl = (app["arms"].get(RP.PRIMARY_ARM) or {}).get("placement") or {}
        if pl:
            a("\n### The §4 placement read\n")
            a(f"{pl['reading']}. Best rookie overall rank **{pl['best_rookie_overall_rank']}**; "
              f"cap breach **{pl['rookie_cap_breach']}**. Cross-position movement (top 100): "
              f"`{json.dumps(pl['cross_position_movement_top100'])}`. Within-position movement: "
              f"`{json.dumps(pl['within_position_movement'])}`.\n")
            a("⚠️ The NF-W8-0 VOR \"shield\" does NOT excuse this read: the shield holds for an "
              "ADDITIVE per-position level shift, whose effect a position's own replacement level "
              "absorbs. This correction re-levels each row by a RATIO, so it can reorder across "
              "positions — and under the two SUPERFLEX configs QB is cross-pooled, which is the "
              "position this arm moves most (NF-TR2b).\n")

    a("\n## 6b. WHY the ordering moved where it did — the decomposition\n")
    a("`rate_permute`'s served point is `assigned_rate × own_games`, so its ordering is a BLEND of "
      "the learned rank and expected games; the incumbent's IS the learned ordering exactly. So the "
      "question is how good an ordering signal expected games is, per position, on the draftable "
      "tier — a labelled DIAGNOSTIC, ⛔ never a trial (MH2.1 (a): an anchor that polices the metric "
      "must not end up setting the gate's own bar).\n")
    act = rep["mechanism_activity"]
    dec_rows = []
    for lab in ("learned_score", "expected_games_alone", "mvp1_point"):
        row = {"signal": lab}
        for pos in POSITIONS:
            vals = [act[y]["ordering_decomposition"][lab][pos] for y in act
                    if pos in act[y]["ordering_decomposition"][lab]]
            row[pos] = round(float(np.mean(vals)), 4) if vals else None
        dec_rows.append(row)
    obs = {p: (round(v[0] - v[1], 4) if v else None)
           for p, v in rep["ordering"]["by_position_winner_vs_incumbent"].items()}
    dec_rows.append({"signal": "**observed Δ tier-ρ (arm − incumbent)**", **obs})
    a(_md_table(dec_rows, ["signal"] + list(POSITIONS)))
    a("\n⭐ **The damage ranks exactly with the games signal's deficit.** Expected games is the "
      "WEAKEST ordering signal at QB and the relatively strongest at TE — and QB is the position "
      "that loses most while TE actually GAINS. Blending availability into the ordering costs "
      "precisely where availability is least informative.\n")
    a("\n⭐ **And the deeper reason, which names the successor.** NF1.5's learner is fitted on "
      "`real_fp_ppr` — a SEASON TOTAL — so it was selected to order POINTS. Handing it a per-game "
      "RATE multiset asks it a question it was never validated on, and the mismatch is largest "
      "exactly where the games spread is widest (QB: a 17-game starter beside a 1-game QB3). The "
      "coherence fix and the ordering are therefore not independently satisfiable with THIS learner: "
      "a successor that wants both should re-select the ordering learner on a per-game RATE target, "
      "rather than re-using a points-ordering learner to order rates.\n")

    if rep.get("null_classification"):
        a("\n## 7. Null classification\n")
        a(f"```json\n{json.dumps(rep['null_classification'], indent=2, default=str)}\n```\n")

    dr = v.get("dsr_reading") or {}
    d2 = (rep["deflation"] or {}).get("dsr_2x2_diagnostic") or {}
    a("\n### Reading the DSR failure — and correcting the instrument\n")
    a(f"Winner per-fold Sharpe **{_fmt(dr.get('winner_sharpe'))}** against the declared field's "
      f"benchmark SR0 **{_fmt(dr.get('benchmark_SR0'))}** ⇒ **{dr.get('state')}**.\n")
    if d2.get("evaluable"):
        a(f"\nThe 2×2, computed as a labelled diagnostic BEFORE naming any remedy (NF-W7f): "
          f"dropping the most extreme DECLARED non-degenerate arm (`{d2['dropped_arm']}`, Sharpe "
          f"{_fmt(d2['dropped_arm_sharpe'])}) collapses `V` **{_fmt(d2['V_declared'])} → "
          f"{_fmt(d2['V_without_dropped_arm'])}** and moves DSR **{_fmt(d2['dsr_declared'])} → "
          f"{_fmt(d2['dsr_without_dropped_arm'])}** — a large move that still does NOT reach "
          f"{rep['deflation']['dsr_min']}. So field heterogeneity is a REAL contributor (a declared "
          f"sibling genuinely beats the incumbent 7/7 and inflates the dispersion) and it is NOT "
          f"sufficient. ⛔ `{d2['dropped_arm']}` is a DECLARED arm and is NOT trimmed: you get to "
          f"pre-register a family, you do not get to discover one (MH2.2).\n")
    a("\n⚠️ **TWO CORRECTIONS TO `cv_power.classify_null`'S REMEDY TEXT, applied by hand here — the "
      "Nth time this instrument has needed one downstream (CLAUDE.md already cards the shared fix):"
      "**\n")
    a("1. Its `reason` prescribes *\"a SMALLER, PRE-REGISTERED field\"* while its own "
      "`retest_trigger` says *\"field size is NOT a lever here\"* (`max_field_size=0`). Those "
      "contradict; the trigger "
      "is the correct half. And `field_remedy_admissible` came back **None** rather than False even "
      "though `declared_field_size=6` was passed, so the machine flag MH2.7 tells callers to read "
      "instead of the prose could not adjudicate it either.\n")
    a("2. Its surviving prescription — *\"a lower-variance design (more rows per fold / a "
      "sharper metric)\"* — is **deterministically VOID** here. The winner is itself one of the "
      "trials, so a "
      "SHARED-variance lever that scales every arm's per-fold dispersion by `c` scales every trial "
      "Sharpe by `1/c`, hence `SR0` by `1/c`, hence `SR − SR0` by `1/c`: **its SIGN is invariant** "
      "(NF-W8-0d's lockstep invariant). With `SR < SR0`, no shared-variance design change can create "
      "the positive gap. The only real levers are a DIFFERENTIAL-variance design (shrink the "
      "WINNER's dispersion, not the field's), a bigger effect, or a genuine absence.\n")

    a("\n## 8. Reading, against the pre-registration's §6\n")
    a(f"- **{v['state']}** — {v['why']}.\n")
    a("- ⭐ **What the arm DID do, and it is not small.** On the served 2026 board it removes every "
      "veteran impossible row (**10 → 0 attributable**), turns the injury give-back from "
      "**+33.96%** into **−11.99%** — i.e. flagged players now project DOWN relative to MVP-1 "
      "rather than being marked back up — and wins the selecting metric overall (+"
      f"{_fmt(rep['pooled']['mean_lift_vs_incumbent'])} CRPS, {rep['pooled']['folds_won']}/"
      f"{rep['pooled']['n_folds']} folds, PBO {_fmt(rep['deflation']['pbo'])}). The matched foil "
      "loses by a mile and makes the give-back WORSE (+40.9%), so the mechanism is ATTRIBUTED to the "
      "per-player availability channel from both directions (NF-D15 g′).\n")
    a("- ⛔ **And why that is still not a ship.** The pre-registration makes the ordering a "
      "CONSTRAINT, and the arm breaches it at QB on the draftable tier by a margin distinguishable "
      "from noise. Relaxing that clause after seeing it fail is exactly the E2.1-r inversion this "
      "program has been burned by, so the gate is left to say no.\n")
    a("- ⚠️ **The two ordering readings DISAGREE, and both are reported.** Over the FULL veteran "
      "population the arm improves ρ at every position; on the DRAFTABLE TIER it regresses at QB. "
      "The tier is the metric NF1.5 was selected on and the one a drafter actually uses, so it "
      "binds — but a reader should know the disagreement exists rather than meet only the half that "
      "supports the verdict.\n")
    a("- ⭐ A TIE on the selecting metric still ships. That is written down in the pre-registration "
      "in advance, precisely so it cannot look like a post-hoc rescue: coherence is a correctness "
      "constraint the INCUMBENT FAILS, and a tie is not a reason to keep serving a stat line that "
      "is physically impossible. It is the pricing-vs-discrimination family rule, ⛔ NOT the E2.1-r "
      "inversion. It did not decide this story — the arm WON the metric and was refused on the "
      "ordering constraint instead.\n")
    a("- ⛔ **NO \"more data\" re-test trigger** is published. The binding refusal is a constraint "
      "the arm BREACHES (more folds would make a real regression MORE significant, not less), and "
      "the DSR shortfall is unreachable at any `n`. Publishing a season trigger here would be the "
      "actively-misleading direction NF-D18 warns about.\n")

    a("\n### ⚠️ A pre-registered prediction this run OVERTURNED (recorded, not edited — NF-W7f)\n")
    a("The pre-registration's §1 states that a successful arm drives ρ(expected games, point ratio) "
      "**to ~0 by construction**. It does NOT. Measured on the served board the incumbent's "
      "**−0.211** becomes **+0.207** — the gradient FLIPS SIGN rather than vanishing. The reason is "
      "informative: under `rate_permute` the point ratio is `r_j / r_i`, a pure ratio of per-game "
      "rates that carries no games term at all, so what remains is the LEARNER's own preference for "
      "high-availability players, no longer masked by the mechanical transfer. The pre-registration "
      "is left verbatim; this paragraph is the correction. ⚠️ It also means the gradient must not be "
      "read as \"still broken, other way\" — the incumbent's −0.211 is a MECHANICAL artifact of "
      "permuting a composite, the arm's +0.207 is a modelling opinion the board is entitled to hold.\n")
    a("\n(A second, smaller correction: the first cut of that same statistic reported **+0.1476** "
      "for `mvp1_null`, an arm that by construction moves no point at all. Its ratio is identically "
      "1, so the figure was a rank correlation over floating-point noise. The reducer now refuses "
      "the row as unevaluable — NF1.7 (a).)\n")

    if rep.get("sensitivity_wide_window"):
        sw = rep["sensitivity_wide_window"]
        act_can = sum(1 for m in sw["mechanism_activity"].values() if m["mechanism_can_act"])
        a("\n## 9. The DISCLOSED wide-window sensitivity (2013–2025)\n")
        a(f"Reported, ⛔ never selected on. Mean lift **{_fmt(sw['pooled']['mean_lift_vs_incumbent'])}"
          f"**, {sw['pooled']['folds_won']}/{sw['pooled']['n_folds']} folds — i.e. the arm LOSES over "
          f"the wider window. The ordering mechanism could act on only **{act_can}/"
          f"{len(sw['mechanism_activity'])}** of those folds (NF-D20), and the pre-2019 seasons are "
          "exactly the ones NF1.5's own selection excluded via `score_from = 2019`. That does not "
          "rescue the arm — it bounds what the wide window can certify, and it is disclosed rather "
          "than dropped.\n")

    path.write_text("\n".join(L))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ2 — rate-permutation §0.5 bake-off")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=N15.MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--folds", default=None,
                    help="comma seasons; default = NF1.5's OWN stage-1 window (inherited)")
    ap.add_argument("--sensitivity", action="store_true",
                    help="also run the DISCLOSED wider 2013-2025 window")
    ap.add_argument("--no-2026", action="store_true", help="skip the served-board application")
    ap.add_argument("--smoke", action="store_true", help="two folds, no 2026 — a code-path proof")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("nfl").setLevel(logging.INFO)

    import duckdb
    # resolve a RELATIVE --duckdb against the PROJECT ROOT, not the cwd: this module is normally
    # run as `python -m …` from the repo root, but a session sitting in the package directory would
    # otherwise get "DuckDB not found" and read it as the missing-artifact error below rather than
    # as a path problem.
    if not Path(args.duckdb).is_absolute() and not Path(args.duckdb).exists():
        cand = _PROJECT_ROOT / args.duckdb
        if cand.exists():
            args.duckdb = str(cand)
    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — a fresh worktree must copy the "
                         "gitignored artifacts + DuckDB in first (NF-INFRA1)")
    con = duckdb.connect(args.duckdb, read_only=True)
    selections = N15.load_selection(json.loads(_NF1_5_REPORT.read_text()),
                                    board="beats-incumbent")
    folds = (tuple(int(x) for x in args.folds.split(",")) if args.folds
             else registered_folds())
    if args.smoke:
        folds, args.no_2026 = folds[-2:], True

    rep = run(con, args.schema, folds, selections, base_from=args.base_from,
              do_2026=not args.no_2026)
    if not args.no_2026:
        rep["application_2026"] = apply_2026(con, args.schema, selections,
                                             RP.ALL_ARMS, base_from=args.base_from)
        app = rep["application_2026"]
        prim = app["arms"].get(RP.PRIMARY_ARM, {})
        rep["coherence_restored_on_served_board"] = (
            prim.get("coherence_violating_players_attributable") == 0)
        rep["coherence_residual_on_served_board"] = {
            "raw_violating_players": prim.get("coherence_violating_players"),
            "attributable_to_this_arm": prim.get("coherence_violating_players_attributable"),
            "also_present_with_ordering_off": prim.get(
                "coherence_violations_also_present_with_ordering_OFF"),
        }
        rep["verdict"]["gates"]["coherence_restored_2026"] = rep[
            "coherence_restored_on_served_board"]
    if args.sensitivity:
        log.info("running the DISCLOSED wider window %s", SENSITIVITY_FOLDS)
        rep["sensitivity_wide_window"] = run(con, args.schema, SENSITIVITY_FOLDS, selections,
                                             base_from=args.base_from, do_2026=False)

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{_STEM}{suffix}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_report_md(rep, _REPORT_DIR / f"{_STEM}{suffix}.md")
    v = rep["verdict"]
    log.info("VERDICT %s — %s · lift %s · PBO %s · DSR %s · coherence %s→%s",
             v["state"], v["why"], rep["pooled"]["mean_lift_vs_incumbent"],
             rep["deflation"]["pbo"], rep["deflation"]["dsr_degenerates_excluded_from_v"],
             rep["leaderboard"]["incumbent"]["coherence_violating_players"],
             rep["leaderboard"][RP.PRIMARY_ARM]["coherence_violating_players"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
