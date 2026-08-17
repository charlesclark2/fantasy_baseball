"""p2_1_s1b_composite.py — NCAAF-P2.1 S1b: is the composite's margin over the block EARNED?

WHAT THIS IS
------------
S1 shipped `pace` and S1-serve wired the 2-column composite `pace_axis` = {`pace_sum`, `pace_diff`}
into the served contract `strength_pace` on a MECHANISTIC argument (the `seconds_per_play` ratio
identity ⇒ the 8-column block spans a lower-dimensional space than 8, so the six per-side levels add
ridge penalty without adding span). S1-serve's own record then stated the debt:

    "If a later story wants to *claim* the +0.018, it needs its own fresh registration and run."

S1b is that run. It registers the **matched pair** — `crps(pace block) − crps(pace_axis)` per fold —
as the PRIMARY contrast. S1 measured every arm against the 25-column `reference` and recorded this
delta as an ATTRIBUTION READ its own harness labels "declared; reported, **never gated**". S1b gates
it: fold-consistency, BH-FDR, PBO, DSR, anchors.

⭐ READ THE PRE-REGISTRATION FIRST — `ablation_results/ncaaf_p2_1_s1b_preregistration.md`, committed
BEFORE the first S1b score. ⛔ Nothing here may be changed to chase a result (E2.1-r).

WHAT S1b CANNOT DO, stated in the code so no reader has to infer it
-------------------------------------------------------------------
* There is **no held-out season** — S1's folds are eval-years 2018…2025, every played FBS season;
  2026 is unplayed. S1b shares S1's measurement substrate in full.
* The harness is **deterministic** (same cache, folds, learner, α, form, seed 42, 4,000 draws), so
  S1b's CRPS is byte-identical to S1's. Re-running the battery is a REPRODUCTION check (gate R), not
  a new measurement. S1b's freshness is entirely in the GATE DESIGN.

USAGE
-----
    # 0) the P2.1 cache (identical parquet; re-assemble if absent — 24 s, Snowflake-free)
    AWS_DEFAULT_REGION=us-east-2 uv run python -m \\
        quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --assemble
    # 1) score the S1b field (foil + 2 composites + 4 anchors + the no-pace degenerate)  (~1 min)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.p2_1_s1b_composite --stage battery
    # 2) gate the matched pair on the DECLARED series, classify, render
    uv run python -m quant_sports_intel_models.football.ncaaf.models.p2_1_s1b_composite --stage decide
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_p2_1 as p21  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models.p2_1_s1_pace import S1_BLOCKS  # noqa: E402

_STORY = "NCAAF-P2.1-S1b"
_RESULTS_DIR = Path(__file__).resolve().parent.parent / "ablation_results"
_SCORES_JSON = _RESULTS_DIR / "ncaaf_p2_1_s1b_composite_scores.json"
_DECISION_JSON = _RESULTS_DIR / "ncaaf_p2_1_s1b_composite.json"
_DECISION_MD = _RESULTS_DIR / "ncaaf_p2_1_s1b_composite.md"

#: ⛔ S1b MUST NOT write S1's or S1-serve's output paths. A story run that overwrites a DECIDED
#: story's audit trail destroys evidence (NCAAF-P2.1 S1-serve defect 3). Named here so the guard can
#: assert it mechanically.
_DECIDED_STORY_PATHS_NEVER_WRITTEN: tuple[str, ...] = (
    "ncaaf_p2_1_s1_pace.json", "ncaaf_p2_1_s1_pace.md", "ncaaf_p2_1_s1_pace_scores.json",
    "ncaaf_p2_1_s1_preregistration.md", "ncaaf_p2_1_s1_readout.md",
    "ncaaf_p2_1_s1b_registration.md", "ncaaf_p2_1_s1_serve_readout.md",
)

#: S1's recorded scores — the REPRODUCTION target (gate R).
_S1_SCORES = _RESULTS_DIR / "ncaaf_p2_1_s1_pace_scores.json"

# ── pre-registered constants — every one inherited from P2.1/S1 (⛔ never edited here) ──────────
_PBO_GATE, _DSR_GATE, _FDR_ALPHA = p21._PBO_GATE, p21._DSR_GATE, p21._FDR_ALPHA
_TIE_BAND, _BREAKEVEN = p21._TIE_BAND, p21._BREAKEVEN
_REPRO_TOL = 1e-4                 # gate R: |S1b fold CRPS − S1 recorded| must be < this
_S1_FIELD_N_TRIALS = 8            # S1's declared field (lineage disclosure)
_P21_FIELD_N_TRIALS = 22          # the P2.1 field in which `pace` was FOUND (lineage disclosure)

#: ⭐ THE MATCHED FOIL — the 8-column P2.1 H9 block, the arm S1 actually PROMOTED. Every S1b contrast
#: is measured against THIS, not against the 25-column reference.
FOIL = "pace"

#: ⭐ THE PRIMARY — the 2-column composite that already serves. The only arm whose margin can be
#: claimed. Fixed here, before the run.
PRIMARY = "pace_axis"

#: The declared real-arm field: the pace representation set, re-parameterised around the block as the
#: foil. Closed and mechanistic — the block has exactly three parameterisations, one is the foil, so
#: two remain. ⛔ `pace_total_axis` is RETAINED even though it is expected to tie, precisely so the
#: field is not trimmed (MH2.2: you may pre-register a family, never discover one).
REAL_ARMS: tuple[str, ...] = ("pace_axis", "pace_total_axis")
DECLARED_FIELD_SIZE_S1B: int = len(REAL_ARMS)          # 2

#: the four generic anchors (run-validity), scored every run
GENERIC_ANCHORS: tuple[str, ...] = ("oracle_peek", "permute", "zero_width", "max_width")

#: ⭐ the S1b-specific degenerate: the 25-col NO-PACE contract. It must LOSE to the foil — a
#: two-sided orientation check on the matched pair (if a contract carrying no pace at all beat the
#: block, the contrast's sign convention is inverted and the run is not interpretable).
NO_PACE_DEGENERATE = "reference"


def scored_arms() -> list[str]:
    """Everything the battery scores: the foil, the 2 real arms, the no-pace degenerate, 4 anchors."""
    return [FOIL, *REAL_ARMS, NO_PACE_DEGENERATE, *GENERIC_ANCHORS]


def n_trials_declared() -> int:
    """foil + 2 real arms + 4 generic anchors — the DSR multiplicity count (MH2).

    ⚠️ The no-pace degenerate is NOT counted: it is an orientation ANCHOR, never a promotion
    candidate, and a diagnostic anchor must never join the trial field (MH2.1 (a) — the anchor that
    polices the metric must not set the gate's own bar)."""
    return 1 + len(REAL_ARMS) + len(GENERIC_ANCHORS)


# ===========================================================================
# The two return series — MATCHED PAIR against the foil, declared SEPARATELY
# ===========================================================================

def fold_series(foil_arm: dict, arm: dict) -> np.ndarray:
    """The DSR series: per-FOLD matched-pair `crps(foil) − crps(arm)` (>0 ⇔ the arm beats the block).

    One observation per season-forward fold — the independent unit of this design. ⭐ This is the
    statistic S1 recorded as an attribution read and never gated."""
    f = np.asarray(foil_arm["fold_crps"], float)
    a = np.asarray(arm["fold_crps"], float)
    n = min(len(f), len(a))
    return f[:n] - a[:n]


def bucket_series(foil_arm: dict, arm: dict) -> np.ndarray:
    """The per-BUCKET matched-pair series (fold quarters). Reported; the PBO GATE itself runs CSCV
    over the raw per-bucket performance matrix of the candidate set (see `stage_decide`)."""
    f = np.asarray(foil_arm["buckets"], float)
    a = np.asarray(arm["buckets"], float)
    n = min(len(f), len(a))
    return f[:n] - a[:n]


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    s = x.std(ddof=1) if len(x) > 1 else 0.0
    return float(x.mean() / s) if s > 0 else 0.0


def series_moments(x: np.ndarray) -> tuple[float, float]:
    """(skew, kurtosis) of a return series, in the convention `deflated_sharpe` uses.

    ⭐ LOAD-BEARING, and it is the MH2 "same gate NAME computed two ways" landmine live in this
    harness. `deflated_sharpe` estimates the higher moments FROM the series; `cv_power`'s
    reachability arithmetic (`folds_to_clear_dsr`, `dsr_max_field_size`) DEFAULTS to Gaussian
    (skew 0, kurt 3). On this series (skew +0.51, kurt 1.99 — platykurtic) the two disagree by
    THREE folds, so leaving the default in place publishes a "+1 more season" re-test trigger for a
    gate that has ALREADY PASSED — precisely the actively-misleading trigger MH2/NF-D18 forbid.
    The moments are therefore passed explicitly wherever the instrument accepts them."""
    from scipy import stats
    x = np.asarray(x, float)
    if len(x) < 3:
        return 0.0, 3.0
    return float(stats.skew(x, bias=False)), float(stats.kurtosis(x, fisher=False, bias=False))


# ===========================================================================
# Stage 1 — battery: the P2.1 scoring function, S1's registry, S1b's arm list
# ===========================================================================

def contrast_active_share(df, folds) -> dict[str, Any]:
    """S1b-V5 / NF-D20 — count the rows on which the CONTRAST can act at all.

    The block and the composite differ ONLY in the six per-side level columns. Where pace is NULL
    both arms impute to the train mean ⇒ identical μ ⇒ the fold delta gets EXACTLY 0 from that row.
    An inactive row is uninformative, never a pass — so the share is measured and reported rather
    than assumed, and the pooled delta is known to be diluted by it."""
    probe = "home_seconds_per_play"
    if probe not in df.columns:
        raise SystemExit(f"[{_STORY}] cannot measure contrast activity: {probe!r} absent from cache")
    per_fold = []
    for f in folds:
        ev = f.ev
        active = int(ev[probe].notna().sum())
        per_fold.append({"eval_year": int(f.eval_year), "n_eval": int(len(ev)),
                         "n_active": active,
                         "active_share": round(active / len(ev), 4) if len(ev) else 0.0})
    tot_n = sum(r["n_eval"] for r in per_fold)
    tot_a = sum(r["n_active"] for r in per_fold)
    return {"probe_column": probe, "per_fold": per_fold, "n_eval_rows": tot_n,
            "n_active_rows": tot_a,
            "active_share": round(tot_a / tot_n, 4) if tot_n else 0.0,
            "note": "rows where pace is NULL contribute EXACTLY 0 to the matched-pair delta "
                    "(both arms impute to the train mean) — the pooled delta is diluted by them"}


def stage_battery(args) -> None:
    df, _meta = p21.load_cache()
    ref_cols = p21.reference_columns(df)
    folds = p21.build_folds(df, max_folds=args.max_folds)
    arms = scored_arms()
    if args.arm:
        arms = [a for a in args.arm.split(",")]
    print(f"=== {_STORY} stage 1 — BATTERY ({len(arms)} arms × {len(folds)} folds, {len(df):,} games, "
          f"reference contract = {len(ref_cols)} cols) ===")
    print(f"  folds: {[f.eval_year for f in folds]}")
    print(f"  foil = `{FOIL}` (8-col block)   primary = `{PRIMARY}` (2-col composite)")

    activity = contrast_active_share(df, folds)
    print(f"  contrast active on {activity['n_active_rows']:,}/{activity['n_eval_rows']:,} eval rows "
          f"({activity['active_share']:.1%}) — NULL-pace rows contribute exactly 0 to the delta")

    out: dict[str, Any] = {"story": _STORY, "run_at": date.today().isoformat(),
                           "n_folds": len(folds), "n_games": int(len(df)),
                           "reference_n_cols": len(ref_cols), "foil": FOIL, "primary": PRIMARY,
                           "contrast_activity": activity, "arms": {}}
    for arm in arms:
        t0 = time.time()
        rng = np.random.default_rng(p21._SEED)     # identical stream per arm ⇒ paired
        rows = [p21.score_arm_fold(arm, f, ref_cols, rng, n_draws=args.n_draws, blocks=S1_BLOCKS)
                for f in folds]
        clv = p21._clv_leg(rows, np.random.default_rng(p21._SEED)) if not args.no_clv else {}
        slim = [{k: v for k, v in r.items() if not isinstance(v, np.ndarray)} for r in rows]
        pooled = float(np.mean(np.concatenate([r["per_game_crps"] for r in rows])))
        out["arms"][arm] = {
            "arm": arm, "folds": slim, "clv": clv,
            "pooled_crps": round(pooled, 5),
            "mean_crps": round(float(np.mean([r["crps"] for r in rows])), 5),
            "fold_crps": [r["crps"] for r in rows],
            "fold_years": [r["eval_year"] for r in rows],
            "buckets": [b for r in rows for b in r["buckets"]],
            "mean_pit_sum": round(float(np.mean([r["pit_sum"] for r in rows])), 5),
            "pooled_margin_calib": round(float(np.mean([r["margin_calib_80"] for r in rows])), 4),
            "pooled_total_calib": round(float(np.mean([r["total_calib_80"] for r in rows])), 4),
            "margin_pit_flat_folds": int(sum(r["margin_pit_flat"] for r in rows)),
            "total_pit_flat_folds": int(sum(r["total_pit_flat"] for r in rows)),
            "mean_h2h_brier": round(float(np.mean([r["h2h_brier"] for r in rows])), 4),
            "n_features": rows[0]["n_features"],
        }
        a = out["arms"][arm]
        print(f"  {arm:<18} CRPS {a['pooled_crps']:.4f}  calib80(m/t) {a['pooled_margin_calib']:.3f}/"
              f"{a['pooled_total_calib']:.3f}  mPITflat {a['margin_pit_flat_folds']}/{len(folds)}  "
              f"feat {a['n_features']:>3}  ({time.time() - t0:.0f}s)")
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _SCORES_JSON.write_text(json.dumps(out, indent=2, default=float))
    print(f"\n  scores → {_SCORES_JSON.relative_to(_PROJECT_ROOT)}\n  Next: `--stage decide`")


# ===========================================================================
# Stage 2 — decide on the DECLARED series
# ===========================================================================

def reproduction_check(arms: dict, tol: float = _REPRO_TOL) -> dict[str, Any]:
    """Gate R — S1b must REPRODUCE S1's recorded per-fold CRPS for the foil, both real arms and the
    no-pace degenerate. The harness is byte-identical, so a mismatch means the design DRIFTED and
    this is not S1b. ⭐ This is what converts "S1b shares S1's substrate" from an admission into a
    VERIFIED statement."""
    if not _S1_SCORES.exists():
        return {"holds": False, "reason": f"S1 scores missing at {_S1_SCORES.name}",
                "max_abs_dev": None}
    s1doc = json.loads(_S1_SCORES.read_text())["arms"]
    devs: dict[str, float] = {}
    for a in (FOIL, *REAL_ARMS, NO_PACE_DEGENERATE):
        if a not in arms or a not in s1doc:
            return {"holds": False, "reason": f"arm {a!r} missing", "max_abs_dev": None}
        x = np.asarray(arms[a]["fold_crps"], float)
        y = np.asarray(s1doc[a]["fold_crps"], float)
        if len(x) != len(y):
            return {"holds": False, "max_abs_dev": None,
                    "reason": f"fold count differs for {a!r} ({len(x)} vs {len(y)})"}
        devs[a] = float(np.max(np.abs(x - y)))
    mx = max(devs.values())
    return {"holds": bool(mx < tol), "max_abs_dev": mx, "per_arm": devs, "tolerance": tol,
            "reason": "" if mx < tol else f"max |Δ| {mx:.2e} ≥ {tol:g} — the harness drifted"}


def _dsr(series: np.ndarray, N: int, V: float | None) -> dict:
    """A per-FOLD series needs ≥3 observations to carry a DSR at all — below that the statistic is
    UNDEFINED (MH2: "not computable" is a state, never a pass and never a crash-into-silence)."""
    if len(series) < 3:
        return {"dsr": None, "sr": round(sharpe(series), 4), "sr0": None, "n_trials": int(N),
                "n_obs": int(len(series)), "undefined": "fewer than 3 observations"}
    r = deflated_sharpe(series, n_trials=N, var_trials_sr=V)
    return {"dsr": round(float(r.dsr), 4), "sr": round(float(r.observed_sr), 4),
            "sr0": round(float(r.sr0), 4), "n_trials": int(r.n_trials), "n_obs": int(r.n_obs)}


def _bh_shortfall(p: float, rows: dict, alpha: float) -> dict[str, Any]:
    """State the BH-FDR shortfall in the unit that BINDS, not in folds (NF-D15 (g″)).

    With `m` registered arms, the arm ranked i-th by p-value must satisfy `p ≤ α·i/m`. This reports
    the step this arm faced and how far its p-value sat from it — an interpretable shortfall, unlike
    a fold count that no additional season can obviously deliver."""
    ps = sorted(r["p_one_sided"] for r in rows.values())
    m = len(ps)
    i = ps.index(p) + 1 if p in ps else 1
    step = alpha * i / m
    return {"m_registered_arms": m, "rank_by_p": i, "bh_step_required": round(step, 6),
            "p_observed": round(float(p), 6),
            "shortfall": round(float(p - step), 6),
            "note": (f"ranked {i} of {m} by p-value, so the BH step is α·{i}/{m} = {step:g}; the "
                     f"observed p is {p:g}. The gap is what would have to close — a smaller p, i.e. "
                     "a larger or less noisy effect, NOT a larger field (a bigger m RAISES the bar "
                     "for rank 1)."),
            }


def _moment_sensitivity(series: np.ndarray, n_trials: int, V: float | None) -> dict[str, Any]:
    """How much of the binding DSR rests on 8-point higher-moment estimates? (NF-D14 two-figure
    convention, applied to the moments rather than to the field.)

    `deflated_sharpe` uses the series' own skew/kurtosis; at n = 8 those are noisy, and here they
    are FAVOURABLE (platykurtic ⇒ a smaller denominator ⇒ a higher DSR). Reporting the
    Gaussian-moment figure beside the binding one shows whether the pass depends on them. ⛔ Neither
    figure re-decides anything — the binding gate was fixed before the run (E2.1-r)."""
    sk, ku = series_moments(series)
    r_est = deflated_sharpe(series, n_trials=n_trials, var_trials_sr=V)
    # ⚠️ `deflated_sharpe` has NO skew/kurt parameters — it ALWAYS estimates them from the series, so
    # a "Gaussian-moment DSR" cannot be obtained from it and must not be fabricated. The sensitivity
    # is therefore expressed on the instrument that DOES accept the moments: how many folds the DSR
    # gate needs under each assumption. That is also exactly the quantity whose disagreement exposed
    # the two-ways-computed defect, so it is the right thing to publish.
    sr = sharpe(series)
    need_measured = cv_power.folds_to_clear_dsr(
        observed_sr=sr, n_trials=n_trials, var_trials_sr=V, skew=sk, kurt=ku)
    need_gaussian = cv_power.folds_to_clear_dsr(
        observed_sr=sr, n_trials=n_trials, var_trials_sr=V)      # instrument default: skew 0, kurt 3
    return {
        "series_skew": round(sk, 4), "series_kurtosis": round(ku, 4),
        "n_obs": int(len(series)), "observed_sr": round(sr, 4),
        "dsr_estimated_moments_BINDING": round(float(r_est.dsr), 4),
        "folds_needed_for_dsr_measured_moments": need_measured,
        "folds_needed_for_dsr_gaussian_moments": need_gaussian,
        "note": ("the binding DSR uses the series' own moments (AFML §14, the program's standard "
                 "instrument). At n=8 those estimates are noisy and here FAVOURABLE (kurt < 3 ⇒ "
                 "thinner tails ⇒ a smaller denominator ⇒ a higher DSR). `cv_power`'s reachability "
                 "arithmetic DEFAULTS to Gaussian, and the two fold requirements above show how far "
                 "apart that puts them — which is why this harness passes the measured moments to "
                 "`classify_null` explicitly (see `series_moments`)."),
    }


def _pbo_companions(arms: dict, candidates: list[str], pbo_res, foil_crps: float) -> dict[str, Any]:
    """NF1.8 — the three things the program requires REPORTED beside PBO, because a rank statistic
    on its own cannot tell "my pick is UNSTABLE" from "the candidates are TIED".

    ⛔ POST-VERDICT DISCLOSURE. The PBO gate was fixed in the pre-registration and binds on its own
    value; nothing here re-decides it. These exist so a reader can tell WHICH reading a failed PBO
    supports — and, given the composite already serves, that distinction is what the PM needs.
    """
    if not candidates:
        return {"available": False}
    pooled = {a: arms[a]["pooled_crps"] for a in candidates}
    lo, hi = min(pooled.values()), max(pooled.values())
    # per-FOLD flip distribution: which candidate is best on each fold. Read off the SAME fold CRPS
    # the gate uses — deliberately NOT a second CSCV implementation (one policy, one implementation).
    n_folds = min(len(arms[a]["fold_crps"]) for a in candidates)
    flips: dict[str, int] = {a: 0 for a in candidates}
    for i in range(n_folds):
        flips[min(candidates, key=lambda a: arms[a]["fold_crps"][i])] += 1
    return {
        "available": True,
        "n_candidates": len(candidates),
        "contender_spread_crps": round(float(hi - lo), 5),
        "contender_spread_pct_of_foil": round(float((hi - lo) / foil_crps * 100), 4),
        "pooled_crps_by_candidate": {a: round(float(v), 5) for a, v in pooled.items()},
        "fold_flip_distribution": flips,
        "n_folds_in_flip": int(n_folds),
        "median_oos_rank_of_is_best": (
            round(float(pbo_res.median_oos_rank_of_is_best), 4) if pbo_res is not None else None),
        "n_cscv_combos": int(pbo_res.n_combos) if pbo_res is not None else None,
        "reading": (
            "E2.1-r: a HIGH PBO over a field whose candidates genuinely TIE is the NULL — 'which "
            "tied candidate wins is noise' — not evidence of overfitting; a high PBO with a WIDE "
            "spread IS overfitting. The SPREAD is the discriminator, so it is reported here beside "
            "the flip distribution rather than left for the reader to assume."),
    }


def stage_decide(args) -> None:
    if not _SCORES_JSON.exists():
        raise SystemExit(f"[{_STORY}] no scores — run `--stage battery` first.")
    doc = json.loads(_SCORES_JSON.read_text())
    arms = doc["arms"]
    if FOIL not in arms:
        raise SystemExit(f"[{_STORY}] the foil {FOIL!r} was not scored — the matched pair is undefined.")
    foil = arms[FOIL]
    n_folds = doc["n_folds"]
    real = [a for a in REAL_ARMS if a in arms]
    anchors = [a for a in GENERIC_ANCHORS if a in arms]
    foil_crps = foil["pooled_crps"]

    # ── A: anchors first (a misbehaving anchor invalidates the run) ────────────────────────────
    anchor_report: dict[str, Any] = {}
    best_real = min(arms[a]["pooled_crps"] for a in real) if real else foil_crps
    if "oracle_peek" in arms:
        o = arms["oracle_peek"]["pooled_crps"]
        anchor_report["oracle_floor"] = {"oracle_crps": o, "best_real_crps": best_real,
                                         "holds": bool(o <= best_real + 1e-9)}
    for name, expect in (("permute", "must LOSE"), ("zero_width", "must LOSE + FAIL the floor"),
                         ("max_width", "must SATISFY the floor + LOSE")):
        if name in arms:
            a = arms[name]
            cov_ok, _ = p21._coverage_floor_ok(a)   # the COVERAGE FLOOR alone (never bundled — NF1.8)
            anchor_report[name] = {"crps": a["pooled_crps"],
                                   "loses_to_foil": bool(a["pooled_crps"] > foil_crps),
                                   "satisfies_coverage_floor": cov_ok,
                                   "margin_calib": a["pooled_margin_calib"],
                                   "total_calib": a["pooled_total_calib"], "expectation": expect}
    # ⭐ the S1b-specific orientation anchor
    if NO_PACE_DEGENERATE in arms:
        d = arms[NO_PACE_DEGENERATE]
        anchor_report["no_pace_degenerate"] = {
            "crps": d["pooled_crps"], "foil_crps": foil_crps,
            "loses_to_foil": bool(d["pooled_crps"] > foil_crps),
            "expectation": "the NO-PACE contract must LOSE to the block — orients the matched pair"}

    def _anchor(name, key, default):
        return bool(anchor_report.get(name, {}).get(key, default))

    anchor_checks = {
        "oracle_floor_holds": _anchor("oracle_floor", "holds", True),
        "permute_loses": _anchor("permute", "loses_to_foil", True),
        "zero_width_loses": _anchor("zero_width", "loses_to_foil", True),
        "max_width_loses": _anchor("max_width", "loses_to_foil", True),
        "zero_width_fails_floor": not _anchor("zero_width", "satisfies_coverage_floor", True),
        "max_width_satisfies_floor": _anchor("max_width", "satisfies_coverage_floor", False),
        "no_pace_degenerate_loses_to_foil": _anchor("no_pace_degenerate", "loses_to_foil", False),
    }
    anchors_ok = all(anchor_checks.values())

    # ── R: reproduction of S1 ──────────────────────────────────────────────────────────────────
    repro = reproduction_check(arms)

    # ── per-arm read on the MATCHED PAIR, both series ──────────────────────────────────────────
    clause = cv_power.fold_consistency_clause(n_folds)
    rows: dict[str, Any] = {}
    pvals: dict[str, float] = {}
    for arm in real:
        a = arms[arm]
        d_fold = fold_series(foil, a)
        d_bucket = bucket_series(foil, a)
        gain = foil_crps - a["pooled_crps"]          # >0 ⇔ the arm beats the BLOCK
        elig, why = p21._eligible(a)
        p = p21._paired_p(d_fold)
        wins = int((d_fold > 0).sum())
        rows[arm] = {
            "arm": arm, "gain_vs_foil_crps": round(float(gain), 5), "pooled_crps": a["pooled_crps"],
            "fold_deltas": [round(float(x), 5) for x in d_fold], "fold_years": a.get("fold_years"),
            "fold_wins": wins, "n_folds": n_folds, "all_folds_positive": bool(wins == n_folds),
            "fold_clause_required": clause.wins_required, "fold_clause_attainable": clause.attainable,
            "fold_clause_passes": bool(clause.passes(wins)),
            "eligible": elig, "ineligible_reason": why,
            "tie_with_foil": bool(abs(gain) < _TIE_BAND),
            "sign_flipped_vs_foil": bool(gain < -_TIE_BAND),
            "p_one_sided": round(p, 6),
            "sharpe_per_fold": round(sharpe(d_fold), 4),        # the DSR series (binding)
            "sharpe_per_bucket": round(sharpe(d_bucket), 4),    # reported
            "n_obs_fold": int(len(d_fold)), "n_obs_bucket": int(len(d_bucket)),
            "margin_calib": a["pooled_margin_calib"], "total_calib": a["pooled_total_calib"],
            "margin_pit_flat_folds": a["margin_pit_flat_folds"],
            "margin_pit_required": max(1, int(0.5 * n_folds)),
            "total_pit_flat_folds": a["total_pit_flat_folds"],
            "n_features": a["n_features"], "clv": a.get("clv", {}),
        }
        pvals[arm] = p
    bh_pass, bh_cutoff = p21._bh(pvals, alpha=_FDR_ALPHA)
    for arm in real:
        rows[arm]["bh_pass"] = bool(bh_pass[arm])

    # ── PBO — CSCV over the raw per-bucket performance of the CANDIDATE SET (eligible real + foil).
    #    The selection PBO asks about is "which pace representation serves", so the foil is IN the
    #    matrix: it is a candidate, not a baseline.
    elig_arms = [a for a in real if rows[a]["eligible"]] + ([FOIL] if p21._eligible(foil)[0] else [])
    nb = min(len(arms[a]["buckets"]) for a in elig_arms) if elig_arms else 0
    pbo = float("nan")
    pbo_res = None
    if len(elig_arms) >= 2 and nb >= 4:
        perf = np.array([arms[a]["buckets"][:nb] for a in elig_arms], float).T
        pbo_res = pbo_cscv(perf, higher_is_better=False,
                           n_splits=max(2, min(16, nb - nb % 2)))
        pbo = float(pbo_res.pbo)
    pbo_companions = _pbo_companions(arms, elig_arms, pbo_res, foil_crps)

    # ── DSR on the per-FOLD matched-pair series; V over the REAL arms only (DSR-CONV) ──────────
    sr_fold_real = [sharpe(fold_series(foil, arms[a])) for a in real]
    sr_fold_all = sr_fold_real + [sharpe(fold_series(foil, arms[a])) for a in anchors]
    V_clean = float(np.var(sr_fold_real, ddof=1)) if len(sr_fold_real) > 1 else None
    V_all = float(np.var(sr_fold_all, ddof=1)) if len(sr_fold_all) > 1 else None
    sr_bucket_real = [sharpe(bucket_series(foil, arms[a])) for a in real]
    V_bucket_clean = float(np.var(sr_bucket_real, ddof=1)) if len(sr_bucket_real) > 1 else None
    n_trials = n_trials_declared()

    prim = rows.get(PRIMARY)
    dsr: dict[str, Any] = {}
    moment_sensitivity: dict[str, Any] = {}
    if prim and prim["gain_vs_foil_crps"] > 0:
        f_series = fold_series(foil, arms[PRIMARY])
        b_series = bucket_series(foil, arms[PRIMARY])
        dsr = {
            "binding": "per_fold_declared_field_degenerate_excluded",
            "per_fold_declared_field_degenerate_excluded": _dsr(f_series, n_trials, V_clean),
            "per_fold_whole_field": _dsr(f_series, n_trials, V_all),
            "per_fold_lineage_inclusive": _dsr(
                f_series, n_trials + _S1_FIELD_N_TRIALS + _P21_FIELD_N_TRIALS, V_clean),
            "per_bucket_REPORTED_ONLY": _dsr(b_series, n_trials, V_bucket_clean),
        }
        moment_sensitivity = _moment_sensitivity(f_series, n_trials, V_clean)
    dsr_binding = dsr.get("per_fold_declared_field_degenerate_excluded", {}).get("dsr", float("nan"))
    dsr_binding = float(dsr_binding) if dsr_binding is not None else float("nan")

    # ── verdict ────────────────────────────────────────────────────────────────────────────────
    arm_gates = bool(prim and prim["eligible"] and not prim["tie_with_foil"]
                     and prim["gain_vs_foil_crps"] > 0 and prim["bh_pass"]
                     and prim["fold_clause_passes"])
    pbo_ok = bool(np.isfinite(pbo) and pbo < _PBO_GATE)
    dsr_ok = bool(np.isfinite(dsr_binding) and dsr_binding >= _DSR_GATE)
    interpretable = bool(anchors_ok and repro["holds"])

    if not interpretable:
        verdict = "NOT_INTERPRETABLE"
    elif prim and prim["sign_flipped_vs_foil"]:
        # the pre-registered revert trigger — the block beats the composite by more than the tie band
        verdict = "REVERT_TO_BLOCK"
    elif arm_gates and pbo_ok and dsr_ok:
        verdict = "MARGIN_EARNED"
    else:
        verdict = "MARGIN_NOT_EARNED"

    # ── null classification — every arm that did not earn its margin ───────────────────────────
    nulls: dict[str, Any] = {}
    for arm in real:
        if arm == PRIMARY and verdict == "MARGIN_EARNED":
            continue
        r = rows[arm]
        override = None
        if not r["eligible"]:
            override = ("CONSTRAINT_REFUSED",
                        f"refused by the calibration constraint ({r['ineligible_reason']}), not by "
                        "the metric — remedy is a different mechanism or a PM decision, never more "
                        "seasons (NF-D18).")
        elif r["tie_with_foil"]:
            override = ("TIE_WITH_FOIL",
                        f"|Δ| {abs(r['gain_vs_foil_crps']):.5f} < tie band {_TIE_BAND:g} — the "
                        "composite is a strict SUBSET of the block's columns, so a near-zero margin "
                        "is the two arms collapsing onto each other. A tie is refused as a win and "
                        "is NOT a null the metric can resolve (nested-form guard).")
        # ⭐ the measured higher moments are passed EXPLICITLY. `classify_null` otherwise defaults to
        # Gaussian (skew 0, kurt 3), which on this platykurtic series disagrees with the BINDING
        # `deflated_sharpe` figure by three folds and would publish a "+1 more season" trigger for a
        # gate that already passed — the actively-misleading trigger MH2/NF-D18 forbid.
        arm_skew, arm_kurt = series_moments(fold_series(foil, arms[arm]))
        v = cv_power.classify_null(
            metric="CRPS(margin)+CRPS(total), matched pair vs the 8-col block",
            n_folds=n_folds, n_arms=len(real),
            beats_foil=bool(r["gain_vs_foil_crps"] > 0),
            observed_sr=r["sharpe_per_fold"], var_trials_sr=V_clean, fold_wins=r["fold_wins"],
            p_one_sided=r["p_one_sided"], bh_cutoff=bh_cutoff,
            skew=arm_skew, kurt=arm_kurt,
            degenerates_excluded_from_v=True, var_trials_sr_with_degenerates=V_all,
            declared_field_size=DECLARED_FIELD_SIZE_S1B)
        # ⭐ TRIGGER SANITY — the instrument can emit a NON-POSITIVE fold delta.
        # When BH rejects EVERY arm the cutoff is 0.0, and `folds_for_sign_certifiability(0.0)`
        # degenerates: `classify_null` then renders "+-8 folds (⇒ 0 total)". A negative fold
        # requirement is not a re-test instruction, it is a mis-render of a state (the MH2.7
        # `n_arms=1`-renders-as-a-fold-shortage family, Nth instance). It is NOT silently dropped:
        # the raw instrument output is recorded verbatim beside the corrected reading.
        raw_trigger = None if override else v.retest_trigger
        degenerate_trigger = bool(
            not override and v.folds_needed is not None
            and (v.extra_seasons is None or v.extra_seasons <= 0))
        corrected = None
        if degenerate_trigger:
            corrected = (
                "UNDEFINED — the instrument returned a non-positive fold requirement "
                f"(folds_needed={v.folds_needed}, extra_seasons={v.extra_seasons}) because BH "
                f"rejected every arm, leaving a degenerate cutoff of {bh_cutoff:g}. The binding "
                "shortfall is NOT a fold count: it is the BH-FDR step itself — see "
                "`bh_shortfall` below.")
        nulls[arm] = {
            "is_primary": arm == PRIMARY,
            "arm_level_gates_cleared": bool(
                r["eligible"] and not r["tie_with_foil"] and r["gain_vs_foil_crps"] > 0
                and r["bh_pass"] and r["fold_clause_passes"]),
            "state": override[0] if override else v.state,
            "reason": override[1] if override else v.reason,
            "retest_trigger": corrected if degenerate_trigger else raw_trigger,
            "retest_trigger_raw_from_instrument": raw_trigger,
            "retest_trigger_corrected": bool(degenerate_trigger),
            # the honest shortfall, in the unit that actually binds (NF-D15 (g″)): the BH step the
            # arm must clear, and how far its p-value is from it.
            "bh_shortfall": _bh_shortfall(r["p_one_sided"], rows, _FDR_ALPHA),
            "folds_have": v.folds_have, "folds_needed": v.folds_needed,
            "extra_seasons": v.extra_seasons, "max_field_size": v.max_field_size,
            "field_remedy_admissible": v.field_remedy_admissible,
            "reclassified_from": v.state if override else None,
            "series_skew": round(arm_skew, 4), "series_kurtosis": round(arm_kurt, 4),
            # ⭐ the fold count is CALENDAR-bound, not a window choice (S1b-V3): 2018-2025 is every
            # played season. A folds/seasons trigger is therefore a FUTURE note, never a live re-test.
            "retest_reachable_now": False,
            "retest_reachability_note": (
                "the fold count is calendar-bound — 2018…2025 is every completed FBS season in the "
                "cache; a new fold requires the 2026 season to be PLAYED (opener 2026-08-29). No "
                "window widening or field change can add one now."),
        }

    out = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "preregistration": "ablation_results/ncaaf_p2_1_s1b_preregistration.md",
        "verdict": verdict, "primary": PRIMARY, "foil": FOIL,
        "contrast": "matched pair — crps(pace 8-col block) − crps(arm); >0 ⇔ the arm beats the block",
        "interpretable": interpretable, "anchors_ok": anchors_ok, "anchor_checks": anchor_checks,
        "anchors": anchor_report, "reproduction": repro,
        "n_folds": n_folds, "n_games": doc["n_games"],
        "contrast_activity": doc.get("contrast_activity", {}),
        "declared_field_size": DECLARED_FIELD_SIZE_S1B, "n_trials": n_trials,
        "series": {"pbo": "CSCV over the raw per-BUCKET performance of the candidate set "
                          "(eligible real arms + the foil), 8 folds × 4 quarters",
                   "dsr": "per-FOLD matched-pair delta (8 season-forward folds) — DECLARED "
                          "FORWARD, BINDING"},
        "foil_readout": {"pooled_crps": foil_crps, "margin_calib": foil["pooled_margin_calib"],
                         "total_calib": foil["pooled_total_calib"],
                         "margin_pit_flat_folds": foil["margin_pit_flat_folds"],
                         "h2h_brier": foil["mean_h2h_brier"], "clv": foil.get("clv", {})},
        "arms": rows,
        "fold_consistency": {"n_folds": n_folds, "wins_required": clause.wins_required,
                             "attainable": clause.attainable,
                             "false_fire": clause.attained_false_fire},
        "bh_cutoff": round(bh_cutoff, 6), "fdr_alpha": _FDR_ALPHA,
        "pbo": round(pbo, 4) if np.isfinite(pbo) else None, "pbo_gate": _PBO_GATE,
        "pbo_over": f"eligible real arms + the foil, raw per-bucket CSCV ({nb} buckets)",
        "pbo_companions": pbo_companions,
        "dsr": dsr, "dsr_gate": _DSR_GATE, "moment_sensitivity": moment_sensitivity,
        "dsr_binding_value": round(dsr_binding, 4) if np.isfinite(dsr_binding) else None,
        "V_per_fold_degenerate_excluded": V_clean, "V_per_fold_whole_field": V_all,
        "V_per_bucket_degenerate_excluded": V_bucket_clean,
        "gates": {"anchors_ok": anchors_ok, "reproduction_ok": repro["holds"],
                  "primary_arm_gates": arm_gates, "pbo_ok": pbo_ok, "dsr_ok": dsr_ok},
        "nulls": nulls, "best_alpha": 0,
        "served_effect": _served_effect(verdict),
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _DECISION_JSON.write_text(json.dumps(out, indent=2, default=float))
    _DECISION_MD.write_text(render_dossier(out))
    _print_decision(out)
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}\n  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")
    _ = args


def _served_effect(verdict: str) -> dict[str, str]:
    """What each verdict does to the SERVED artifact — fixed in the pre-registration §5, restated
    here so the closeout cannot drift from it."""
    return {
        "MARGIN_EARNED": (
            "NO CHANGE to `SERVED_PACE_COLS` / `ncaaf_game_mean_v2.json` — the composite already "
            "serves. What changes is that the margin becomes independently quotable and "
            "`ncaaf_p2_1_s1b_registration.md` §6's debt is discharged."),
        "MARGIN_NOT_EARNED": (
            "NO CHANGE. The served representation continues to stand on S1-serve §2's MECHANISTIC "
            "argument, which is independent of this margin. The record states the margin is NOT "
            "independently claimable — the status quo of §6, now measured rather than asserted."),
        "REVERT_TO_BLOCK": (
            "REVERT `SERVED_PACE_COLS` to the 8-column block (the arm S1 PROMOTED) and refit "
            "`ncaaf_game_mean_v2.json`. Pre-registered so the study can fail against the served state."),
        "NOT_INTERPRETABLE": "NO verdict and NO change; find out why the anchors or reproduction failed.",
    }.get(verdict, {})  # type: ignore[return-value]


def _print_decision(d: dict) -> None:
    print("=" * 92)
    print(f"{_STORY} DECISION — matched pair vs `{d['foil']}` · {d['n_trials']} trials · "
          f"{d['n_folds']} folds · declared field {d['declared_field_size']} · primary `{d['primary']}`")
    print("=" * 92)
    print(f"  anchors valid: {'YES ✅' if d['anchors_ok'] else 'NO ❌'}   reproduction of S1: "
          f"{'YES ✅' if d['reproduction']['holds'] else 'NO ❌'} "
          f"(max |Δ| {d['reproduction'].get('max_abs_dev')})")
    for k, v in d["anchor_checks"].items():
        print(f"    {'✅' if v else '❌'} {k}")
    act = d.get("contrast_activity", {})
    if act:
        print(f"\n  contrast active on {act.get('active_share', 0):.1%} of eval rows "
              f"({act.get('n_active_rows'):,}/{act.get('n_eval_rows'):,})")
    print(f"  foil `{d['foil']}` CRPS {d['foil_readout']['pooled_crps']:.4f}")
    print(f"  {'arm':<18}{'Δ vs foil':>11}{'folds':>7}{'p':>10}{'BH':>5}{'elig':>6}{'tie':>5}"
          f"{'SR/fold':>9}{'SR/bkt':>8}")
    for r in sorted(d["arms"].values(), key=lambda r: -r["gain_vs_foil_crps"]):
        print(f"  {r['arm']:<18}{r['gain_vs_foil_crps']:>+11.4f}{r['fold_wins']:>4}/{r['n_folds']:<2}"
              f"{r['p_one_sided']:>10.4f}{'✓' if r['bh_pass'] else '·':>5}"
              f"{'✓' if r['eligible'] else '✗':>6}{'≈' if r['tie_with_foil'] else '·':>5}"
              f"{r['sharpe_per_fold']:>9.3f}{r['sharpe_per_bucket']:>8.3f}")
    print(f"\n  fold clause: {d['fold_consistency']['wins_required']} of {d['n_folds']} wins required")
    print(f"  PBO {d['pbo']} (gate < {d['pbo_gate']})")
    for k, v in d.get("dsr", {}).items():
        if isinstance(v, dict):
            print(f"  DSR[{k}] {v['dsr']}  (SR {v['sr']} vs SR0 {v['sr0']}, N={v['n_trials']}, "
                  f"n={v['n_obs']}{'  UNDEFINED: ' + v['undefined'] if v.get('undefined') else ''})")
    print(f"  gates: {d['gates']}")
    print(f"\n  VERDICT: {d['verdict']}")
    print(f"  served effect: {d['served_effect']}")


def render_dossier(d: dict) -> str:
    g = d["gates"]
    act = d.get("contrast_activity", {})
    L = [f"# {_STORY} — is the composite's margin over the 8-column block EARNED?", "",
         f"_Decided {d['decided_at']} · matched pair vs `{d['foil']}` · {d['n_trials']} trials · "
         f"{d['n_folds']} purged folds · {d['n_games']:,} games · declared real-arm field "
         f"{d['declared_field_size']} · primary `{d['primary']}`_", "",
         "**Pre-registration:** "
         "[`ncaaf_p2_1_s1b_preregistration.md`](./ncaaf_p2_1_s1b_preregistration.md) — written and "
         "committed BEFORE the first S1b score.", "",
         "## What this run can and cannot establish (read before the verdict)", "",
         "* ⚠️ **No held-out season exists.** S1's folds are eval-years 2018…2025 — every completed "
         "FBS season in the cache; 2026 is unplayed (opener 2026-08-29). S1b shares S1's measurement "
         "substrate **in full** and cannot replicate the effect on data S1 did not see.",
         "* ⚠️ **The harness is deterministic, so S1b's CRPS is byte-identical to S1's** (gate R "
         "verifies exactly this). Re-running the battery is a REPRODUCTION, not a new measurement.",
         "* ✅ **What IS new:** S1 measured every arm against the 25-column `reference` and recorded "
         "the block-vs-composite delta as an attribution read its own harness labels *\"declared; "
         "reported, **never gated**\"*. S1b registers that delta as the PRIMARY contrast and gates "
         "it — fold-consistency, BH-FDR, PBO, DSR and an anchor set have never been applied to this "
         "statistic before.", "",
         "## Verdict", "", f"**{d['verdict']}**", "",
         f"> {d['served_effect']}", "",
         "| gate | value | bar | |", "|---|---|---|---|",
         f"| anchors valid (incl. the no-pace degenerate) | {d['anchors_ok']} | all seven checks | "
         f"{'✅' if d['anchors_ok'] else '❌'} |",
         f"| **R** — reproduction of S1's per-fold CRPS (foil + both arms + degenerate) | max abs dev "
         f"{d['reproduction'].get('max_abs_dev')} | < {d['reproduction'].get('tolerance', _REPRO_TOL)} | "
         f"{'✅' if d['reproduction']['holds'] else '❌'} |",
         f"| primary arm-level gates (eligible · not a tie · Δ>0 · BH-FDR · fold clause) | "
         f"{g['primary_arm_gates']} | all | {'✅' if g['primary_arm_gates'] else '❌'} |",
         f"| PBO (CSCV, candidate set = eligible real arms + the foil) | {d['pbo']} | "
         f"< {d['pbo_gate']} | {'✅' if g['pbo_ok'] else '❌'} |",
         f"| **DSR (per-FOLD matched pair, declared field, degenerate-excluded — BINDING)** | "
         f"**{d['dsr_binding_value']}** | ≥ {d['dsr_gate']} | {'✅' if g['dsr_ok'] else '❌'} |",
         f"| BH-FDR cutoff | {d['bh_cutoff']} | α = {d['fdr_alpha']} | — |",
         f"| fold-consistency (calibrated) | {d['fold_consistency']['wins_required']} of "
         f"{d['n_folds']} wins | false-fire ≤ 0.20 | — |", ""]
    if act:
        L += [f"**Where the contrast can act (S1b-V5 / NF-D20).** The block and the composite differ "
              f"ONLY in the six per-side level columns; on NULL-pace rows both impute to the train "
              f"mean, so those rows contribute **exactly 0** to the delta. Active on "
              f"**{act.get('active_share', 0):.1%}** of eval rows "
              f"({act.get('n_active_rows'):,}/{act.get('n_eval_rows'):,}) — the pooled delta is "
              f"diluted by the remainder. Reported, never used to rescale the metric.", ""]
    L += ["## Anchors — the two-sided proof the metric is not inverted", "",
          "| anchor | reading | expectation | holds |", "|---|---|---|---|"]
    a = d["anchors"]
    if "oracle_floor" in a:
        o = a["oracle_floor"]
        L.append(f"| `oracle_peek` (ORACLE FLOOR) | CRPS {o['oracle_crps']:.4f} vs best real "
                 f"{o['best_real_crps']:.4f} | nothing may beat it | "
                 f"{'✅' if o['holds'] else '❌ METRIC INVERTED'} |")
    for n in ("permute", "zero_width", "max_width"):
        if n in a:
            v = a[n]
            want = {"zero_width": False, "max_width": True}.get(n)
            ok = want is None or bool(v["satisfies_coverage_floor"]) is want
            L.append(f"| `{n}` | CRPS {v['crps']:.4f}, calib80 {v['margin_calib']:.3f}/"
                     f"{v['total_calib']:.3f}, coverage floor "
                     f"{'satisfied' if v['satisfies_coverage_floor'] else 'FAILED'} | "
                     f"{v['expectation']} | {'✅' if (v['loses_to_foil'] and ok) else '❌'} |")
    if "no_pace_degenerate" in a:
        v = a["no_pace_degenerate"]
        L.append(f"| `reference` ⭐ (NO-PACE degenerate, S1b-specific) | CRPS {v['crps']:.4f} vs foil "
                 f"{v['foil_crps']:.4f} | {v['expectation']} | "
                 f"{'✅' if v['loses_to_foil'] else '❌ CONTRAST INVERTED'} |")
    L += ["", "## The field — the matched pair, both series side by side", "",
          "`Δ vs foil` > 0 ⇔ the arm beats the **8-column block**. `SR/fold` is the DECLARED DSR "
          "series (8 obs); `SR/bucket` is the 32-obs series, reported so the series choice is "
          "auditable.", "",
          "| arm | Δ vs foil | fold wins | p (1-sided) | BH | eligible | margin-PIT flat | tie | "
          "SR per FOLD | SR per BUCKET | state |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(d["arms"].values(), key=lambda x: -x["gain_vs_foil_crps"]):
        st = d["nulls"].get(r["arm"], {}).get("state", "**MARGIN EARNED**")
        L.append(f"| `{r['arm']}`{' ⭐' if r['arm'] == d['primary'] else ''} | "
                 f"{r['gain_vs_foil_crps']:+.4f} | {r['fold_wins']}/{r['n_folds']} | "
                 f"{r['p_one_sided']:.4f} | {'✅' if r['bh_pass'] else '—'} | "
                 f"{'✅' if r['eligible'] else '❌'} | "
                 f"{r['margin_pit_flat_folds']}/{r['n_folds']} (need ≥{r['margin_pit_required']}) | "
                 f"{'≈' if r['tie_with_foil'] else '—'} | {r['sharpe_per_fold']:.3f} | "
                 f"{r['sharpe_per_bucket']:.3f} | {st} |")
    fo = d["foil_readout"]
    L.append(f"| `{d['foil']}` (FOIL, 8-col block) | — | — | — | — | — | "
             f"{fo['margin_pit_flat_folds']}/{d['n_folds']} | — | — | — | matched incumbent |")
    prim = d["arms"].get(d["primary"], {})
    if prim:
        L += ["", f"`{d['primary']}` per-fold Δ vs the block by eval season: " +
              ", ".join(f"{y} {x:+.4f}" for y, x in
                        zip(prim.get("fold_years") or [], prim["fold_deltas"])) + ".", ""]
        L += [f"⚠️ **Calibration-constraint status of the primary.** `{d['primary']}` is margin-PIT "
              f"flat in **{prim['margin_pit_flat_folds']}/{d['n_folds']}** folds against a threshold "
              f"of ≥{prim['margin_pit_required']} — it passes **exactly at the boundary**, and is "
              f"{fo['margin_pit_flat_folds'] - prim['margin_pit_flat_folds']} fold(s) worse than the "
              f"block ({fo['margin_pit_flat_folds']}/{d['n_folds']}). ⛔ The constraint is inherited "
              "verbatim and is NOT tightened (NF1.8: a floor is never a target, and tightening it "
              "after seeing a result is the E2.1-r inversion). Recorded as a caveat on the "
              "representation, not remedied by moving the bar.", ""]
    pc = d.get("pbo_companions") or {}
    if pc.get("available"):
        L += ["## Beside PBO — is this a TIE or an UNSTABLE pick? (NF1.8, post-verdict disclosure)", "",
              "A rank statistic alone cannot tell *\"my pick is unstable\"* from *\"the candidates "
              "are tied\"*, and the two readings imply opposite things for a representation that "
              "**already serves**. ⛔ The PBO gate binds on its own value; nothing here re-decides "
              "it.", "",
              f"* **Contender spread** — {pc['contender_spread_crps']:+.5f} CRPS across "
              f"{{{', '.join(f'`{k}` {v:.4f}' for k, v in pc['pooled_crps_by_candidate'].items())}}}, "
              f"i.e. **{pc['contender_spread_pct_of_foil']:.3f}% of the foil's CRPS**. The three "
              "representations are separated by a tenth of a percent.",
              f"* **Per-fold flip distribution** — which candidate is best on each of the "
              f"{pc['n_folds_in_flip']} folds: "
              f"{', '.join(f'`{k}` {v}' for k, v in pc['fold_flip_distribution'].items())}. "
              "(Read off the same fold CRPS the gate uses — deliberately not a second CSCV "
              "implementation.)",
              f"* **Median OOS rank of the in-sample best** — "
              f"**{pc['median_oos_rank_of_is_best']} of {pc['n_candidates']}** over "
              f"{pc['n_cscv_combos']} CSCV combinations. ⚠️ In this instrument the rank runs 1…N "
              "with **HIGHER = better out-of-sample** (`ω = rank/(N+1)`), so the in-sample winner "
              "typically lands *first* out-of-sample — the opposite of an unstable selection.", "",
              f"⚠️ **PBO is a COARSE statistic on a 3-config field.** With N = 3, ω can only take "
              "the values 0.25 / 0.50 / 0.75, and a *middle* finish (ω = 0.50) already counts as an "
              "overfit event. Among three representations separated by a tenth of a percent, "
              "finishing second is close to a coin flip, so a PBO above the 0.2 gate is near-"
              "structural here rather than diagnostic of a fragile pick.", "",
              f"> {pc['reading']}", ""]
    L += ["## DSR — the declared series binds; the others are disclosure", "",
          "| figure | DSR | SR | SR0 | N trials | n obs | status |", "|---|---|---|---|---|---|---|"]
    for k, v in d.get("dsr", {}).items():
        if isinstance(v, dict):
            tag = ("⭐ **BINDING**" if k == d["dsr"].get("binding") else
                   ("reported only" if "REPORTED" in k else "reported"))
            L.append(f"| `{k}` | {v['dsr']} | {v['sr']} | {v['sr0']} | {v['n_trials']} | "
                     f"{v['n_obs']} | {tag} |")
    if not d.get("dsr"):
        L.append("| — | — | — | — | — | — | not computed (the primary does not beat the foil) |")

    ms = d.get("moment_sensitivity") or {}
    if ms:
        L += ["", "**Moment sensitivity of the binding DSR (post-verdict disclosure, decides "
              "nothing).** `deflated_sharpe` estimates the series' higher moments from its "
              f"{ms['n_obs']} observations; here they are **skew {ms['series_skew']}, kurtosis "
              f"{ms['series_kurtosis']}** — platykurtic, i.e. FAVOURABLE (thinner tails ⇒ a smaller "
              f"denominator ⇒ a higher DSR). The binding DSR is "
              f"**{ms['dsr_estimated_moments_BINDING']}** at SR {ms['observed_sr']}.", "",
              "⚠️ `deflated_sharpe` has **no** skew/kurt parameters — it always estimates them from "
              "the series — so a \"Gaussian-moment DSR\" cannot be obtained from it and is NOT "
              "fabricated here. The sensitivity is expressed on the instrument that *does* accept "
              "the moments: the DSR gate needs "
              f"**{ms['folds_needed_for_dsr_measured_moments']} folds** under the measured moments "
              f"but **{ms['folds_needed_for_dsr_gaussian_moments']}** under Gaussian ones — against "
              f"{d['n_folds']} available. At n = 8 the moment estimates are themselves noisy, so "
              "the DSR pass should be read as resting partly on them.", "",
              "⚠️ This is also where the **same gate name is computed two ways** (MH2): `cv_power`'s "
              "reachability arithmetic defaults to Gaussian moments, and on this series that "
              "disagrees with the binding figure by three folds. This harness therefore passes the "
              "measured moments to `classify_null` explicitly — without that, the record would "
              "publish a *\"+1 more season\"* re-test trigger for a gate that has already PASSED.", ""]

    def _v(x):
        return "—" if x is None else f"{float(x):.4f}"
    L += ["", f"`V` (cross-trial per-fold Sharpe dispersion): degenerate-excluded "
          f"{_v(d['V_per_fold_degenerate_excluded'])} · whole field "
          f"{_v(d['V_per_fold_whole_field'])} · per-bucket degenerate-excluded "
          f"{_v(d['V_per_bucket_degenerate_excluded'])}.", "",
          "⚠️ **On the 2-arm field, stated because a small field lowers `SR0` and that deserves a "
          "direct answer.** The pace representation set has exactly three mechanistically distinct "
          "parameterisations (all 8 columns / the two composites / the total axis alone). S1b makes "
          "one the foil, leaving two. **No arm was removed because it lost** — `pace_total_axis` is "
          "retained even though it is expected to tie. The lineage-inclusive figure above "
          f"(N = {n_trials_declared() + _S1_FIELD_N_TRIALS + _P21_FIELD_N_TRIALS}) shows whether the "
          "verdict depends on the narrow count.", "",
          "## Null classification", "",
          f"Classified with `cv_power.classify_null(n_arms={d['declared_field_size']}, "
          f"declared_field_size={d['declared_field_size']}, degenerates_excluded_from_v=True)` on the "
          "DECLARED per-fold matched-pair series; the MACHINE flag `field_remedy_admissible` is read, "
          "never the prose (MH2.7).", "",
          "| arm | primary | arm-gates | state | field remedy admissible | re-test trigger | "
          "reachable now |", "|---|---|---|---|---|---|---|"]
    for arm, v in d["nulls"].items():
        L.append(f"| `{arm}` | {'⭐' if v['is_primary'] else '—'} | "
                 f"{'✅' if v['arm_level_gates_cleared'] else '—'} | {v['state']} | "
                 f"{v['field_remedy_admissible']} | {v['retest_trigger'] or '—'} | "
                 f"{'yes' if v.get('retest_reachable_now') else '**no — calendar-bound**'} |")
    for arm, v in d["nulls"].items():
        if v.get("retest_trigger_corrected"):
            L += ["", f"⚠️ **The instrument's raw trigger for `{arm}` was mis-rendered and is "
                  f"corrected above.** It returned `{v['retest_trigger_raw_from_instrument']}` — a "
                  "NON-POSITIVE fold requirement, which is not a re-test instruction but a "
                  "mis-render of a state: BH rejected every arm, so the cutoff was the degenerate "
                  f"{d['bh_cutoff']:g} and the certifiability arithmetic ran on it. The raw string is "
                  "recorded verbatim in the JSON (`retest_trigger_raw_from_instrument`), never "
                  "silently dropped. This is the MH2.7 `n_arms=1`-renders-as-a-fold-shortage family "
                  "recurring on a second code path — ⭐ a defect hand-corrected downstream N times is "
                  "a defect in the INSTRUMENT, and fixing `cv_power` is carded rather than done here "
                  "(a shared instrument is pinned by cross-vertical guards — MH2.7)."]
        sf = v.get("bh_shortfall")
        if sf:
            L += ["", f"**The binding shortfall for `{arm}`, in the unit that actually binds.** "
                  f"{sf['note']} Observed p **{sf['p_observed']}** vs the required "
                  f"**{sf['bh_step_required']}** — a gap of **{sf['shortfall']:+.4f}**."]
    if d["primary"] not in d["nulls"]:
        L.append(f"| `{d['primary']}` | ⭐ | ✅ | **MARGIN EARNED** | — | — | — |")
    L += ["", "⛔ **A re-test trigger stated in folds/seasons is a FUTURE note, not a live re-test.** "
          "The fold count is calendar-bound (2018…2025 is every completed FBS season); a new fold "
          "requires the 2026 season to be played. And a `DSR_UNREACHABLE` state carries **no** "
          "re-test trigger at all — `n` enters only through `√(n−1)`, so it scales a positive gap "
          "and cannot create one (MH2 / NF-D18).", "",
          "## Honest framing", "",
          f"`best_alpha = {d['best_alpha']}`. S1b changes no bet, no edge claim and no framing — it "
          "concerns which of two already-certified column sets carries a calibration term in a "
          f"market-blind mean model. The edge bar (model-side ATS/OU > {_BREAKEVEN} AND > placebo) is "
          "unchanged and unclaimed.", "",
          f"- foil `{d['foil']}` vs-close: `{json.dumps(fo.get('clv', {}))}`"]
    if prim:
        L.append(f"- `{d['primary']}` vs-close: `{json.dumps(prim.get('clv', {}))}`")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=f"Story {_STORY} — is the composite's margin over the block earned?")
    ap.add_argument("--stage", choices=["battery", "decide"], required=True)
    ap.add_argument("--no-clv", action="store_true")
    ap.add_argument("--arm", type=str, default=None, help="comma-separated subset (smoke only)")
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--n-draws", type=int, default=p21._N_DRAWS)
    args = ap.parse_args()
    if args.stage == "battery":
        stage_battery(args)
    else:
        stage_decide(args)


if __name__ == "__main__":
    main()
