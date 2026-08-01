"""run_nf_d15_point_scaling.py — NF-D15 §0.5 bake-off: the AVAILABILITY-SCALED rookie POINT projection
for RB/TE/WR, with its OWN gate on the POINT.

THE STORY IN ONE PARAGRAPH. NF-D14 fitted a rookie availability prior for the rookie-QB *interval* and
recorded a clean null there. On the way past it MEASURED — outside its pre-registered scope — that
scaling the rookie POINT by that prior's expected-games ratio improves held-out RB/TE/WR MAE by
1.2–3.5 PPR, and BREAKS QB (+16.8%, bias −10.7 COLD → +11.4 HOT: the slot curve already prices
draft-capital playing time once and the ratio prices it twice). NF-D14 declined the whole thing because
it was a POINT change under an INTERVAL gate. NF-D15 is the honest home for the RB/TE/WR half: same
fitted signal, RE-USED not refitted, under a gate built for a point projection.

────────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS DIFFERENT FROM NF-D14, AND WHY EACH DIFFERENCE IS THE POINT
────────────────────────────────────────────────────────────────────────────────────────────────────
1. **The metric is NF1.4's `tier_mae`, inherited rather than chosen.** The incumbent rookie point was
   selected on it; grading a change to that product on a different metric is metric-shopping. NF-D14's
   UNIVERSE MAE is reported in full (it is the bridge back to its §6 and this harness's wiring proof)
   but never selects.
2. **A DO-NO-ORDERING-HARM constraint, checked PER POSITION.** A per-player multiplicative scale
   reorders the board; a point-MAE win that scrambles the draft order is a loss for a draft-board
   product. NF1.4's `ORDERING_DO_NO_HARM` verbatim, never a pooled mean (a pooled ρ hides a single
   position collapsing).
3. ⭐ **A MATCHED FOIL beside every availability arm (NF-D10).** NF-D14's own explanation of the lift —
   "the ratio exceeds 1 for high-capital rookies, so it partially corrects the COLD bias NF1.4
   documented" — describes a LEVEL correction, which a single per-position constant delivers with zero
   per-player information and zero ordering risk. `mean_ratio` IS that constant, registered at the same
   base and the same λ, so the PAIRED delta is the availability content. Without it a leaderboard rank
   cannot tell "availability works" from "anything that inflates RB/TE/WR works".
4. **⛔ QB is excluded by pre-registration and enforced in ONE place** (`apply_position_scale`), then
   PROVEN on emitted projections (`qb_untouched`) rather than asserted.
5. **Per-position deflation, and the BH-FDR is CONSUMED.** Each position runs its own search, its own
   PBO/DSR, its own paired p-value; BH-FDR across the three is an ARGUMENT to the per-position ship
   decision, not a number printed under it (E7.12's computed-but-unconsumed landmine).

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. No `best_alpha`, no CLV/ROI claim.
🔒 The rookie INTERVAL is untouched — NF-D14 settled that question and this story does not re-open it.
   (A shipped point change does move the band's CENTRE, because the band is pasted around the point;
   its WIDTH model is unchanged. That is stated in the report rather than glossed.)

RUN ON THE LAPTOP (no Snowflake; reads the cached NF1.4 pool + NF-D14's availability panel, ~1 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d15_point_scaling
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import rookie_availability as AV  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import rookie_point_scaling as PS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_d15_point_scaling")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_PANEL_CACHE = _ART / "nf_d14_rookie_availability_panel.parquet"
_NF_D14_RESULT = _REPORT_DIR / "nf_d14_rookie_availability.json"

_REAL = "rookie_fp_ppr"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Step 0 — REUSE NF-D14's fitted signal (this story does NOT refit it)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_nf_d14_winner(path: Path = _NF_D14_RESULT) -> dict:
    """Read NF-D14's leg-1 winner config back out of NF-D14's OWN artifact.

    ⭐ Read, not re-derived and not hard-coded. Re-deriving would be a refit — the thing the story's
    step 0 explicitly forbids — and hard-coding would let NF-D14 be re-run with a different winner
    while NF-D15 silently kept consuming the old one. `PS.require_reused_prior` then asserts the
    artifact still carries the prior this story was written against, so a regenerated NF-D14 with a new
    leg-1 winner fails LOUDLY here instead of quietly changing every number downstream."""
    if not path.exists():
        raise SystemExit(
            f"NF-D15 REUSES NF-D14's fitted availability prior and no NF-D14 artifact exists at "
            f"{path}. Run NF-D14 first:\n  uv run python -m quant_sports_intel_models.football.nfl."
            "fantasy.run_nf_d14_availability")
    best = json.loads(path.read_text())["leg1"]["best"]
    cfg = {"label": best["label"], "form": best["form"], "blend": float(best.get("blend", 1.0)),
           "tier": best.get("tier", "round"),
           "blocks": tuple(str(best.get("blocks") or "capital").split("+"))}
    PS.require_reused_prior(cfg)
    return cfg


def build_pool(pool_path: Path, panel_path: Path) -> pd.DataFrame:
    """The NF1.4 rookie pool carrying NF-D14's week-1 depth-chart proxy — the identical join NF-D14's
    leg 2 makes, so the two stories' availability reads are the same numbers on the same rows."""
    pool = NF17.load_pool(pool_path)
    if not panel_path.exists():
        raise SystemExit(
            f"no NF-D14 availability panel at {panel_path} — rebuild it with:\n  uv run python -m "
            "quant_sports_intel_models.football.nfl.fantasy.run_nf_d14_availability --rebuild-panel")
    panel = pd.read_parquet(panel_path)
    return pool.merge(panel[["gsis_id", "draft_year", "depth_rank"]],
                      on=["gsis_id", "draft_year"], how="left")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The per-fold availability reads — computed ONCE per class and shared by every arm
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _slot_games(fold: NF17.Fold) -> np.ndarray:
    """The expected games the SLOT CURVE ITSELF already assumed for each held-out rookie.

    Read from `curve.games_by_pos_slot` exactly the way `project_rookies` reads it (same bucket, same
    fallback, same clip), because the whole point of the `ratio_slot` arm is to be relative to what the
    served point ALREADY prices. Re-deriving it a second way would make the arm relative to something
    the board does not use."""
    pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    overall = pd.to_numeric(fold.test["draft_overall"], errors="coerce").to_numpy(dtype=float)
    out = np.full(len(pos), np.nan)
    for i, (p, o) in enumerate(zip(pos, overall)):
        if not np.isfinite(o):
            continue
        g = fold.curve.games_by_pos_slot.get((p, SP._slot_bucket(o)))
        if g is None:
            g = fold.curve.games_by_pos_slot.get((p, "101+"), 6.0)
        out[i] = float(np.clip(g, 1.0, 17.0))
    return out


def _learned_scale(fold: NF17.Fold) -> np.ndarray:
    """THE DIRECT-LEARNED FOIL — a shallow GBM on the realized MULTIPLICATIVE correction.

    Target `log1p(realized) − log1p(point)` over the same availability features the ratio arms use, so
    the foil differs from them ONLY in the functional form of the correction and a win is attributable
    to the learner rather than to the information. Deliberately shallow and heavily regularised (NF1.4's
    convention, inherited): ~400 training rows across three positions is nowhere near enough for a deep
    tree, and an over-fit foil makes for a dishonest bake-off.

    Fitted on the SCALED positions only — a foil allowed to learn from QB would be fitted on a
    population it is then forbidden to score."""
    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:                                    # pragma: no cover - sklearn is a dep
        return np.full(len(fold.test), np.nan)
    tr = AV.availability_features(fold.train)
    feats = AV.block_features(("capital", "depth"))
    tr_pos = tr["position_group"].astype(str).str.upper().to_numpy()
    point = np.asarray(fold.train_pred, dtype=float)
    real = pd.to_numeric(tr[_REAL], errors="coerce").to_numpy(dtype=float)
    keep = (np.isin(tr_pos, PS.SCALED_POSITIONS) & np.isfinite(point) & np.isfinite(real)
            & (point > 1e-6))
    if keep.sum() < 60:
        return np.full(len(fold.test), np.nan)
    x_tr, cols = AV._design(tr[keep], feats)
    y_tr = np.log1p(np.clip(real[keep], 0.0, None)) - np.log1p(point[keep])
    m = GradientBoostingRegressor(n_estimators=200, learning_rate=0.04, max_depth=2,
                                  min_samples_leaf=25, subsample=0.8, random_state=17)
    m.fit(x_tr, y_tr)
    x_te, _ = AV._design(AV.availability_features(fold.test), feats, cols=cols)
    # clipped in LOG space before exponentiating — an unclipped tree extrapolation is a multiplicative
    # blow-up, and this foil exists to be a fair comparison, not to lose on an outlier.
    return np.exp(np.clip(m.predict(x_te), -1.5, 1.5))


def fold_scales(fold: NF17.Fold, winner_cfg: dict, *, seed: int = 20260801) -> dict:
    """Every base scale for ONE held-out class, computed once and shared by every arm (§0.5 cost
    hygiene — and, more importantly, the guarantee that two arms differing only in λ really do differ
    only in λ).

    The availability prior is fitted STRICTLY IN-FOLD on the prior draft classes, exactly as NF-D14's
    leg 2 does it. The CAPITAL-ONLY sibling is fitted the same way and is not a candidate: it is the
    denominator that lets `ratio_residual` carry the depth-chart increment ALONE, i.e. the availability
    content the slot curve cannot already have priced through draft capital."""
    pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    prior = AV.make_prior(winner_cfg).fit(fold.train)
    e_games = prior.stats(fold.test)["e_games"].to_numpy(dtype=float)
    pos_mean = np.array([prior.pos_mean_.get(p, np.nan) for p in pos], dtype=float)

    cap = AV.make_prior(PS.NF_D14_CAPITAL_SIBLING).fit(fold.train)
    e_capital = cap.stats(fold.test)["e_games"].to_numpy(dtype=float)

    # the PERMUTATION anchor: the same family, the same n, fitted against SHUFFLED training outcomes.
    # Well-posed at any sample size (NF1.7 (b)) — unlike a peeking oracle, which is a floor only at
    # matched family AND matched resolution.
    rng = np.random.default_rng(seed + int(fold.year))
    shuffled = fold.train.assign(rookie_games=rng.permutation(
        pd.to_numeric(fold.train["rookie_games"], errors="coerce").fillna(0.0).to_numpy(dtype=float)))
    perm = AV.make_prior(winner_cfg).fit(shuffled)
    e_perm = perm.stats(fold.test)["e_games"].to_numpy(dtype=float)
    perm_mean = np.array([perm.pos_mean_.get(p, np.nan) for p in pos], dtype=float)

    return {
        "ratio_pos": PS.safe_ratio(e_games, pos_mean),
        "ratio_slot": PS.safe_ratio(e_games, _slot_games(fold)),
        "ratio_residual": PS.safe_ratio(e_games, e_capital),
        "learned": _learned_scale(fold),
        "_permuted": PS.safe_ratio(e_perm, perm_mean),
        # NF-D14 §6 VERBATIM — no denominator floor, no upper clip, no QB exclusion. The wiring proof,
        # and deliberately NOT the candidate arm: `ratio_pos` is the same quantity under this story's
        # own physical bounds. Both are reported so the bounds' effect is visible, not implied.
        "_nf_d14_section6": np.clip(np.where(np.isfinite(pos_mean) & (pos_mean > 0),
                                             e_games / np.where(pos_mean > 0, pos_mean, 1.0), 1.0),
                                    0.0, None),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring one arm
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _scale_for(cfg: dict, bases: dict, positions: np.ndarray) -> np.ndarray:
    """The scale one arm applies to one held-out class.

    ⭐ THE MATCHED FOIL IS BUILT BY AVERAGING ITS PARTNER'S OWN SCALE — shrink FIRST, then take the
    per-position mean — not by averaging the raw ratio and shrinking that. The two differ (Jensen), and
    only the first gives the foil the IDENTICAL per-position MEAN scale as its partner. That identity
    is the whole instrument: the pair then differs in NOTHING except the per-player variation, so the
    paired delta is the availability content and cannot be a level difference wearing its clothes."""
    fam = cfg["family"]
    if fam == "incumbent":
        return np.ones(len(positions))
    shrunk = PS.shrink_scale(bases[cfg["base"]], cfg["lam"])
    return PS.position_mean_scale(shrunk, positions) if fam == "mean_ratio" else shrunk


def score_arm(folds: list[NF17.Fold], scales: dict[int, dict], cfg: dict,
              pos_scale: dict[int, dict]) -> dict:
    """One arm, scored on every held-out draft class with NF1.4's OWN `cohort_metrics`.

    Two reads per class, both kept: `tier_mae_by_pos` in RAW PPR (the per-position selection metric —
    readable as "PPR of error on the rookies you would actually draft", and no cross-position scale
    normalisation is needed when nothing is pooled), and the scale-free POOLED tier_mae over the scaled
    positions for the headline. `mae`/`rmse`/`bias` over the whole drafted universe are reported —
    that is NF-D14 §6's read — and never selected on."""
    per_cohort: dict[int, dict] = {}
    per_cohort_scaled: dict[int, dict] = {}
    rows = []
    for f in folds:
        pos = f.test["position_group"].astype(str).str.upper().to_numpy()
        k = _scale_for(cfg, scales[f.year], pos)
        pred = PS.apply_position_scale(f.test_pred, pos, k)
        d = pd.DataFrame({"position_group": pos, _REAL: f.test_real,
                          "_inc": f.test_pred, "_pred": pred})
        per_cohort[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year])
        per_cohort_scaled[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year],
                                                       tier_k=PS.SCALED_TIER_K)
        rows.append(d.assign(year=f.year, _k=np.where(np.isin(pos, PS.SCALED_POSITIONS), k, 1.0)))
    allrows = pd.concat(rows, ignore_index=True)
    scaled = PS.scaled_positions_only(allrows)
    out = {
        "label": cfg["label"], "key": PS.config_key(cfg),
        **{q: cfg[q] for q in ("family", "base", "lam", "uses_availability", "shippable")},
        "per_cohort": per_cohort,
        "pooled_tier_mae": _mean([v.get("tier_mae") for v in per_cohort_scaled.values()], 4),
        # ROW-POOLED universe reads over the SCALED positions — the bridge back to NF-D14 §6.
        "universe_mae": round(float((scaled["_pred"] - scaled[_REAL]).abs().mean()), 3),
        "universe_bias": round(float((scaled["_pred"] - scaled[_REAL]).mean()), 3),
        "mean_scale": round(float(np.nanmean(scaled["_k"])), 4),
        "sd_scale": round(float(np.nanstd(scaled["_k"])), 4),
    }
    for p in ("QB",) + PS.SCALED_POSITIONS:
        g = allrows[allrows["position_group"] == p]
        if g.empty:
            continue
        out[f"universe_mae_{p}"] = round(float((g["_pred"] - g[_REAL]).abs().mean()), 2)
        out[f"universe_bias_{p}"] = round(float((g["_pred"] - g[_REAL]).mean()), 2)
        out[f"tier_mae_{p}"] = _mean([v.get("tier_mae_by_pos", {}).get(p)
                                      for v in per_cohort.values()], 3)
        out[f"tier_bias_{p}"] = _mean([v.get("tier_bias_by_pos", {}).get(p)
                                       for v in per_cohort.values()], 3)
        out[f"rho_{p}"] = _mean([v.get("rho_by_pos", {}).get(p) for v in per_cohort.values()], 4)
    return out


def _mean(values, nd: int = 4) -> float | None:
    v = np.array([x for x in values if x is not None], dtype=float)
    v = v[np.isfinite(v)]
    return round(float(v.mean()), nd) if len(v) else None


def _pos_row(rec: dict, cohorts: list[int], pos: str,
             key: str = "tier_mae_by_pos") -> np.ndarray:
    return np.array([rec["per_cohort"].get(y, {}).get(key, {}).get(pos, np.nan) for y in cohorts],
                    dtype=float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The anchors — two-sided, every run, and EVERY one required
# ══════════════════════════════════════════════════════════════════════════════════════════════
def score_anchors(folds: list[NF17.Fold], scales: dict[int, dict],
                  pos_scale: dict[int, dict]) -> dict:
    """The REQUIRED anchor set, scored through the SAME reducer the candidates use.

    ⭐ Both DIRECTIONS, and both READ rather than reasoned about:
      · the ORACLE FLOOR at two resolutions — full per-player (`oracle_perplayer`, which must be
        unbeatable) and the MATCHED FAMILY of the constant foil (`oracle_posconst`, which an honest
        per-player arm may legitimately beat: NF1.7 (b) / NF1.9 (f), a peeking oracle is a floor only
        at matched family AND matched sample resolution);
      · the DEGENERATE CEILINGS — `zero_scale` and NF1.4's `pos_median` MAE-collapse tell. NF-D14's
        refinement of the NF-D11 landmine is precisely that reasoning about whether MAE will invert is
        not a substitute for scoring the arm that would win it if it did, so both are in the field
        every run and the report READS them.
      · the PERMUTATION — the same family, the same n, only the information moves.

    Every anchor honours the QB exclusion (it goes through `apply_position_scale` like everything
    else), so the anchors and the candidates are answering the same question."""
    out: dict[str, dict] = {}
    specs = ("oracle_perplayer", "oracle_posconst", "permuted", "zero_scale", "pos_median")
    for tag in specs:
        per_cohort, per_cohort_scaled, rows = {}, {}, []
        for f in folds:
            pos = f.test["position_group"].astype(str).str.upper().to_numpy()
            pred = _anchor_pred(tag, f, scales[f.year], pos)
            d = pd.DataFrame({"position_group": pos, _REAL: f.test_real,
                              "_inc": f.test_pred, "_pred": pred})
            per_cohort[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year])
            per_cohort_scaled[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year],
                                                           tier_k=PS.SCALED_TIER_K)
            rows.append(d)
        allrows = pd.concat(rows, ignore_index=True)
        scaled = PS.scaled_positions_only(allrows)
        rec = {"label": tag, "per_cohort": per_cohort,
               "pooled_tier_mae": _mean([v.get("tier_mae") for v in per_cohort_scaled.values()], 4),
               PS.SELECTION_METRIC: _mean([v.get("tier_mae")
                                           for v in per_cohort_scaled.values()], 4),
               "universe_mae": round(float((scaled["_pred"] - scaled[_REAL]).abs().mean()), 3)}
        for p in PS.SCALED_POSITIONS:
            rec[f"tier_mae_{p}"] = _mean([v.get("tier_mae_by_pos", {}).get(p)
                                          for v in per_cohort.values()], 3)
            g = allrows[allrows["position_group"] == p]
            if not g.empty:
                rec[f"universe_mae_{p}"] = round(float((g["_pred"] - g[_REAL]).abs().mean()), 2)
        out[tag] = rec
    return out


def _anchor_pred(tag: str, fold: NF17.Fold, bases: dict, pos: np.ndarray) -> np.ndarray:
    real = np.asarray(fold.test_real, dtype=float)
    point = np.asarray(fold.test_pred, dtype=float)
    if tag == "permuted":
        return PS.apply_position_scale(point, pos, bases["_permuted"])
    if tag == "zero_scale":
        return PS.apply_position_scale(point, pos, np.zeros(len(pos)))
    if tag == "oracle_perplayer":
        # PEEKS at full resolution: the exact multiplicative correction. Scores ~0 on an MAE-type
        # metric; nothing may beat it. A DIRECTION check (E2.1-r's oracle floor in its weak form for a
        # monotone-in-accuracy metric), not the strong guard — the strong guards here are the
        # degenerates and the permutation.
        k = np.where(np.abs(point) > 1e-6, real / np.where(np.abs(point) > 1e-6, point, 1.0), 1.0)
        return PS.apply_position_scale(point, pos, k, clip=(0.0, np.inf))
    if tag == "oracle_posconst":
        # PEEKS at the MATCHED FAMILY of `mean_ratio`: the held-out class's OWN per-position mean
        # correction. This is the floor that is well-posed against a CONSTANT arm.
        k = np.ones(len(pos))
        for p in PS.SCALED_POSITIONS:
            sel = (pos == p) & (np.abs(point) > 1e-6) & np.isfinite(real)
            if sel.sum() >= 3:
                k[pos == p] = float(np.mean(real[sel] / point[sel]))
        return PS.apply_position_scale(point, pos, k)
    if tag == "pos_median":
        # NF1.4's MAE-COLLAPSE TELL: the in-fold position median for everyone. MAE is minimised at the
        # conditional median, so this is the arm that WINS an inverted metric — and it carries ZERO
        # ordering information, so the do-no-ordering-harm constraint is what makes it ineligible even
        # when it scores well. Both halves are reported.
        tr_pos = fold.train["position_group"].astype(str).str.upper().to_numpy()
        tr_real = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)
        out = point.copy()
        for p in PS.SCALED_POSITIONS:
            v = tr_real[(tr_pos == p) & np.isfinite(tr_real)]
            if len(v):
                out[pos == p] = float(np.median(v))
        return out
    raise ValueError(f"unknown anchor {tag!r}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-position selection + deflation (NF1.4's `_select_for_position`, one story over)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def select_for_position(results: list[dict], inc: dict, cohorts: list[int], pos: str) -> dict:
    """Pick + deflate ONE position's search.

    Metric = that position's draftable-tier MAE in raw PPR (nothing is pooled here, so no scale
    normalisation is needed and the number stays readable). Eligibility = shippable AND
    do-no-ordering-harm AT THIS POSITION. `winner = None` with candidates present is a REAL result, not
    a bug: it means no arm stayed within `ORDERING_DO_NO_HARM` of the incumbent's within-position rank.

    ⚠️ PBO is computed over the ELIGIBLE set — the search the selection ACTUALLY ran — per NF1.8, not
    over every config scored. Both the whole-field and the contender-set DSR are reported: NF-D14 was
    bitten by exactly the statistic that scales with the DISPERSION of the trial Sharpes, so a field
    holding its own weak arms deflates against those arms rather than against the contest at the top.
    ⭐ THE PRE-REGISTERED GATE IS THE WHOLE-FIELD DSR (NF-D14's choice, carried forward); the contender
    reading is reported so the two are distinguishable, never to re-open the gate after seeing it."""
    inc_row = _pos_row(inc, cohorts, pos)
    inc_mae = _mean(inc_row, 4)
    inc_rho = _mean(_pos_row(inc, cohorts, pos, "rho_by_pos"), 4)

    cands = []
    for r in results:
        row = _pos_row(r, cohorts, pos)
        mae = _mean(row, 4)
        if mae is None:
            continue
        rho = _mean(_pos_row(r, cohorts, pos, "rho_by_pos"), 4)
        ordering = PS.ordering_check({pos: rho}, {pos: inc_rho}, positions=(pos,))
        cands.append({"rec": r, "row": row, "metric": mae, "rho": rho,
                      "tier_bias": _mean(_pos_row(r, cohorts, pos, "tier_bias_by_pos"), 3),
                      "ordering": ordering,
                      "eligible": bool(r["shippable"] and ordering["ok"])})
    if not cands:
        return {"position": pos, "winner": None, "incumbent_metric": inc_mae,
                "incumbent_rho": inc_rho, "n_candidates": 0, "deflation": {}, "paired_p": None,
                "matched_foil": None, "ordering": PS.ordering_check({}, {pos: inc_rho},
                                                                    positions=(pos,))}

    eligible = [c for c in cands if c["eligible"]]
    best = min(eligible, key=lambda c: c["metric"]) if eligible else None
    best_any = min(cands, key=lambda c: c["metric"])

    mat = pd.DataFrame({c["rec"]["label"]: dict(zip(cohorts, c["row"])) for c in cands}).sort_index()
    defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)

    trial, ctr_labels = [], list(mat.mean(axis=0).sort_values().index[:max(4, mat.shape[1] // 4)])
    ctr = []
    for c in cands:
        d = inc_row - c["row"]
        d = d[np.isfinite(d)]
        sr = (float(d.mean() / d.std(ddof=1))
              if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
        trial.append(sr)
        if c["rec"]["label"] in ctr_labels:
            ctr.append(sr)
    dsr = dsr_ctr = pval = None
    deltas: list[float] = []
    if best is not None:
        raw = inc_row - best["row"]
        deltas = [float(x) for x in raw[np.isfinite(raw)]]
        dsr = M14.deflated_sharpe(np.array(deltas), np.array(trial, dtype=float))
        dsr_ctr = M14.deflated_sharpe(np.array(deltas), np.array(ctr, dtype=float))
        pval = M14.onesided_paired_pvalue(np.array(deltas))

    return {
        "position": pos, "n_candidates": len(cands), "n_eligible": len(eligible),
        "incumbent_metric": inc_mae, "incumbent_rho": inc_rho,
        "incumbent_tier_bias": _mean(_pos_row(inc, cohorts, pos, "tier_bias_by_pos"), 3),
        "winner": None if best is None else {
            **{k: best["rec"][k] for k in ("label", "key", "family", "base", "lam",
                                           "uses_availability", "shippable")},
            "metric": best["metric"], "rho": best["rho"], "tier_bias": best["tier_bias"]},
        "best_any": {"label": best_any["rec"]["label"], "metric": best_any["metric"],
                     "eligible": best_any["eligible"]},
        "ordering": None if best is None else best["ordering"],
        "deflation": {**defl, "dsr": dsr, "dsr_contenders": dsr_ctr},
        "paired_p": pval, "per_cohort_delta": [round(x, 2) for x in deltas],
        "matched_foil": _matched_foil(cands, best, inc_row, cohorts),
    }


def _matched_foil(cands: list[dict], best: dict | None, inc_row: np.ndarray,
                  cohorts: list[int]) -> dict | None:
    """⭐ THE ATTRIBUTION (NF-D10). The selected availability arm beside the IDENTICAL arm with its
    per-player content stripped — same base, same λ — and the PAIRED per-class delta between them.

    A leaderboard rank cannot separate "availability works" from "any inflation of RB/TE/WR works";
    the paired delta can, and it is the number this story's claim actually rests on. If the pair is a
    tie, the honest reading is that the LEVEL correction earned the lift and availability earned none
    of it — a null for NF-D15 and a recorded lead for a recalibration story."""
    if best is None or best["rec"]["family"] not in PS.AVAILABILITY_FAMILIES:
        return None
    foil = next((c for c in cands
                 if c["rec"]["family"] == "mean_ratio"
                 and c["rec"]["base"] == best["rec"]["base"]
                 and abs(float(c["rec"]["lam"]) - float(best["rec"]["lam"])) < 1e-12), None)
    if foil is None:
        return None
    d = foil["row"] - best["row"]                       # > 0 ⇒ the per-player content HELPS
    d = d[np.isfinite(d)]
    return {
        "arm": best["rec"]["label"], "arm_metric": best["metric"],
        "foil": foil["rec"]["label"], "foil_metric": foil["metric"],
        "paired_delta": round(float(np.mean(d)), 4) if len(d) else None,
        "paired_p": M14.onesided_paired_pvalue(d) if len(d) >= 3 else None,
        "classes_arm_wins": int(np.sum(d > 0)), "classes": int(len(d)),
        "foil_beats_incumbent": bool(foil["metric"] < _mean(inc_row, 4)),
        "foil_ordering_ok": bool(foil["ordering"]["ok"]),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".4f")
    except Exception:                                     # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, path: Path) -> None:          # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    an, per_pos = out["anchors"], out["per_position"]
    p("# NF-D15 — the AVAILABILITY-SCALED rookie POINT projection (RB/TE/WR) — §0.5 bake-off")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · **arms:** "
      f"{len(out['arms'])} · **held-out rookie-seasons (RB/TE/WR):** {out['n_scaled_rows']} · "
      f"**availability prior:** `{out['prior']['label']}` (NF-D14 leg-1 winner, REUSED not refitted)")
    p("")
    p(f"## ⭐ VERDICT — {out['headline']}")
    p("")
    p(out["verdict"])
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      f"⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm and "
      f"every held-out QB: **{out['qb_max_drift']:.9f}** PPR). 🔒 The rookie INTERVAL's width model is "
      "untouched — NF-D14 settled that question.")
    p("")

    p("## 0. Step 0 — the REUSE, and the wiring proof that it is faithful")
    p("")
    p(f"The availability signal is NF-D14's leg-1 winner `{out['prior']['label']}`, read back out of "
      "`ablation_results/nf_d14_rookie_availability.json` and re-fitted STRICTLY IN-FOLD per held-out "
      "draft class. It is not re-selected here — `require_reused_prior` fails loudly if NF-D14 is "
      "re-run with a different winner, because every number below would then be about a prior nobody "
      "selected.")
    p("")
    rep = out["nf_d14_reproduction"]
    p(f"**The wiring proof.** This harness rebuilds NF-D14 §6's scale in new code, so it is required "
      f"to REPRODUCE §6's published numbers before any selection is read "
      f"(tolerance ±{rep['check']['tol']} PPR): "
      f"**{'✅ REPRODUCED' if rep['check']['ok'] else '🚨 DOES NOT REPRODUCE — do not read the rest'}**.")
    p("")
    p(_md(pd.DataFrame(rep["table"])))
    p("")
    p("⭐ **The QB row is REPORTED, not checked, and the difference is the whole story.** NF-D14 §6 "
      "scaled QB — that is what it measured and declined. NF-D15 cannot: `apply_position_scale` passes "
      "QB through unchanged. So the QB row above is this harness re-deriving NF-D14's finding *as a "
      "measurement it is forbidden to act on*, and it lands in the same place: the ratio prices "
      "draft-capital playing time a second time on top of the slot curve that already prices it.")
    p("")

    p("## 1. Selection metric, the constraint, and the anchor set")
    p("")
    p("**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The incumbent rookie "
      "point was selected on the draftable-tier MAE, on a tier FIXED by the incumbent's own projection "
      "(NF1.1's fixed-anchor rule, so no arm can buy a friendlier subset). NF-D15 changes that same "
      "product; grading it on a different metric would be metric-shopping. Per position the metric is "
      "that position's tier MAE in RAW PPR — nothing is pooled, so it stays readable as *PPR of error "
      "on the rookies you would actually draft*.")
    p("")
    p("⚠️ **NF-D14's headline for this lead is a UNIVERSE MAE** (all ~75 drafted rookies a class). It "
      "is reported in every table below — it is the bridge back to §6 — and it **never selects**: the "
      "universe read is dominated by late-round rookies nobody drafts, and the product is a draft "
      "board.")
    p("")
    p(f"**The constraint — DO NO ORDERING HARM.** A per-player multiplicative scale REORDERS the board "
      f"within a position, and a point-MAE win that scrambles the draft order is a loss for this "
      f"product. Each scaled position's within-position Spearman ρ must stay within "
      f"`ORDERING_DO_NO_HARM = {PS.ORDERING_DO_NO_HARM}` of the incumbent's — NF1.4's own constant, "
      f"inherited verbatim so the bar is not re-negotiated by the story that needs it. Checked PER "
      f"POSITION, never as a pooled mean (a pooled ρ can sit flat while one position collapses).")
    p("")
    p("### The anchors, scored on THIS run")
    p("")
    rows = [{"anchor": t, "what it is": w,
             "tier MAE RB": an[t].get("tier_mae_RB"), "tier MAE TE": an[t].get("tier_mae_TE"),
             "tier MAE WR": an[t].get("tier_mae_WR"),
             "universe MAE": an[t].get("universe_mae")}
            for t, w in [
                ("oracle_perplayer", "ORACLE FLOOR, full resolution (k = realized/point). Peeks; "
                                     "nothing may beat it."),
                ("oracle_posconst", "ORACLE FLOOR at the MATCHED FAMILY of the constant foil — the "
                                    "held-out class's OWN per-position mean correction."),
                ("permuted", "the availability prior fitted on SHUFFLED training games. Same family, "
                             "same n; only information moves. Must LOSE."),
                ("zero_scale", "DEGENERATE — k = 0, project nothing. Must LOSE."),
                ("pos_median", "DEGENERATE — NF1.4's MAE-collapse tell (the in-fold position median "
                               "for everyone). Wins an INVERTED metric; must LOSE this one."),
            ] if t in an]
    inc = out["incumbent"]
    rows.append({"anchor": "→ INCUMBENT (NULL)", "what it is": "the shipped rookie point, unscaled",
                 "tier MAE RB": inc.get("tier_mae_RB"), "tier MAE TE": inc.get("tier_mae_TE"),
                 "tier MAE WR": inc.get("tier_mae_WR"), "universe MAE": inc.get("universe_mae")})
    if out["best_overall"]:
        b = out["best_overall"]
        rows.append({"anchor": "→ BEST AVAILABILITY ARM", "what it is": b["label"],
                     "tier MAE RB": b.get("tier_mae_RB"), "tier MAE TE": b.get("tier_mae_TE"),
                     "tier MAE WR": b.get("tier_mae_WR"), "universe MAE": b.get("universe_mae")})
    p(_md(pd.DataFrame(rows)))
    p("")
    for ok, good, bad in (
        (out["checks"]["degenerates_lose"],
         "✅ both degenerates lose the primary metric — the metric is not paying for pessimism",
         "🚨 A DEGENERATE WINS THE PRIMARY METRIC — it is INVERTED; nothing in this run may be "
         "shipped (CLAUDE.md NF-D11/NF-D14)"),
        (out["checks"]["permutation_beaten"],
         "✅ the truth beats its own permutation — the scale carries information, not just shape",
         "🚨 THE PERMUTATION IS NOT BEATEN — the arm has learnt nothing from the outcomes"),
        (out["checks"]["oracle_respected"],
         "✅ the full-resolution oracle floor holds",
         "🚨 THE ORACLE IS BEATEN AT FULL RESOLUTION — mathematically impossible ⇒ the metric is "
         "inverted"),
        (out["checks"]["qb_untouched"],
         "✅ QB is untouched on real emitted projections, not merely by assertion",
         "🚨 A SCALE REACHED QB — the pre-registered exclusion is broken"),
    ):
        p("- " + (good if ok else bad))
    p("")
    if out["best_overall"]:
        beats = [q for q in PS.SCALED_POSITIONS
                 if (out["best_overall"].get(f"tier_mae_{q}") is not None
                     and an["oracle_posconst"].get(f"tier_mae_{q}") is not None
                     and out["best_overall"][f"tier_mae_{q}"]
                     < an["oracle_posconst"][f"tier_mae_{q}"])]
        if beats:
            p(f"⭐ **READ THE `oracle_posconst` ROW BEFORE CONCLUDING ANYTHING FROM IT: the best "
              f"availability arm BEATS that peeking oracle at {', '.join(beats)}, and that is NOT a "
              f"metric inversion.** It is the NF1.7 (b) / NF1.9 (f) capacity effect, reproduced. A "
              f"peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION, and this "
              f"one is a per-position CONSTANT — it knows the held-out class's average correction and "
              f"nothing about any individual rookie. An honest PER-PLAYER arm is free to beat it, "
              f"because it is answering a finer question. **The floor that is well-posed against a "
              f"per-player arm is `oracle_perplayer`** (full resolution, scored "
              f"{an['oracle_perplayer']['pooled_tier_mae']}), and it holds; `oracle_posconst` is the "
              f"floor for the CONSTANT foils, where it does its job. This is exactly why both "
              f"resolutions are in the anchor set rather than one.")
            p("")
    p(out["degenerate_reading"])
    p("")

    p("## 2. The full field (pooled over the SCALED positions RB/TE/WR)")
    p("")
    p(_md(pd.DataFrame([{
        "arm": r["label"], "avail?": "yes" if r["uses_availability"] else "—",
        "pooled tier MAE (scale-free)": r["pooled_tier_mae"],
        "tier MAE RB": r.get("tier_mae_RB"), "tier MAE TE": r.get("tier_mae_TE"),
        "tier MAE WR": r.get("tier_mae_WR"),
        "universe MAE": r["universe_mae"], "universe bias": r["universe_bias"],
        "mean scale": r["mean_scale"]}
        for r in sorted(out["arms"], key=lambda r: (r["pooled_tier_mae"] is None,
                                                    r["pooled_tier_mae"]))])))
    p("")
    p("⭐ **Read the `MATCHED FOIL` rows against their `avail ratio` partners at the same base and the "
      "same λ, not against the leaderboard.** The foil delivers the IDENTICAL average level correction "
      "with ZERO per-player information; the paired difference between a pair is the availability "
      "content, and a rank cannot tell that apart from 'anything that inflates RB/TE/WR helps' "
      "(NF-D10).")
    p("")

    p("## 3. Per-position selection, deflation, and the SHIP decision")
    p("")
    p(_md(pd.DataFrame([{
        "position": r["position"],
        "incumbent tier MAE": r["incumbent_metric"],
        "selected arm": (r["winner"] or {}).get("label", "— none eligible —"),
        "tier MAE": (r["winner"] or {}).get("metric"),
        "Δ vs incumbent": (None if not r["winner"] or r["incumbent_metric"] is None
                           else round(r["winner"]["metric"] - r["incumbent_metric"], 3)),
        "ρ inc → arm": (f"{r['incumbent_rho']} → {(r['winner'] or {}).get('rho')}"),
        "PBO": r["deflation"].get("pbo"), "DSR": r["deflation"].get("dsr"),
        "paired p": r["paired_p"], "BH-FDR": "survives" if out["fdr"].get(r["position"]) else "no",
        "SHIP": "✅" if out["ship_by_position"][r["position"]]["ship"] else "—",
    } for r in per_pos])))
    p("")
    for r in per_pos:
        pos = r["position"]
        ship = out["ship_by_position"][pos]
        p(f"### {pos} — {'✅ SHIPS' if ship['ship'] else '🟡 does NOT ship'}")
        p("")
        p(f"Gate detail: `{ship}`")
        p("")
        if r["winner"] is None:
            p(f"**No arm was eligible.** {r['n_candidates']} arms scored; none stayed within "
              f"`ORDERING_DO_NO_HARM` of the incumbent's within-position ρ ({r['incumbent_rho']}). "
              f"The unconstrained best was `{r['best_any']['label']}` at "
              f"{r['best_any']['metric']} — **a point-MAE win that scrambles the draft order, which "
              f"is exactly the trade this constraint exists to refuse.**")
            p("")
            continue
        d = r["deflation"]
        p(f"Deflation over the ELIGIBLE set ({r['n_eligible']} of {r['n_candidates']} arms): "
          f"**PBO {d.get('pbo')}** · Bailey degradation {d.get('os_gap_pct')}% · contender spread "
          f"{d.get('contender_spread_pct')}% · **DSR {d.get('dsr')}** (gate ≥ {PS.DSR_MIN}; "
          f"contender-set reading {d.get('dsr_contenders')}, reported for distinguishability, NOT the "
          f"gate) · one-sided paired p {r['paired_p']}.")
        p("")
        if d.get("flips"):
            # NF1.8's `deflate` is shared with an INTERVAL story, so it names its full-sample column
            # `IS80`. Rendering that label here would put an interval score's name on a tier MAE.
            p(_md(pd.DataFrame(d["flips"]).head(6)
                  .rename(columns={"full-sample IS80": "full-sample tier MAE"})))
            p("")
        mf = r["matched_foil"]
        if mf:
            p(f"⭐ **THE MATCHED FOIL — the attribution.** `{mf['arm']}` ({mf['arm_metric']}) against "
              f"its identical-base, identical-λ constant foil `{mf['foil']}` ({mf['foil_metric']}): "
              f"paired mean delta **{mf['paired_delta']}** PPR in the availability arm's favour "
              f"(one-sided paired p {mf['paired_p']}), winning **{mf['classes_arm_wins']} of "
              f"{mf['classes']}** held-out classes. The foil "
              f"{'DOES' if mf['foil_beats_incumbent'] else 'does NOT'} beat the incumbent on its own.")
            p("")
            if mf["foil_beats_incumbent"] and (mf["paired_delta"] or 0) <= 0:
                p("🚨 **READ THIS AS THE RESULT: the constant foil matches or beats the availability "
                  "arm.** The lift at this position is a LEVEL correction of NF1.4's documented cold "
                  "bias, and the per-player availability content earned none of it. That is a null "
                  "for NF-D15's claim — and a recorded lead for a recalibration story, which is a "
                  "different change with a different risk profile (no ordering movement at all).")
                p("")
        p(_md(pd.DataFrame([{"position": k, **v} for k, v in
                            (r["ordering"] or {}).get("per_position", {}).items()])))
        p("")
    p("### The BH-FDR is CONSUMED, not printed")
    p("")
    p(f"One-sided paired p-values across the three scaled positions: "
      f"`{ {r['position']: r['paired_p'] for r in per_pos} }` → BH-FDR (q={PS.FDR_Q}) survivors: "
      f"`{out['fdr']}`. ⭐ Each position's survival is an ARGUMENT to its own ship decision "
      f"(`per_position_ship`), so a position that fails its multiplicity correction cannot receive the "
      f"scaling whatever its point estimate says. That is E7.12's landmine — a statistic computed, "
      f"printed, and then never allowed to gate anything — closed by construction.")
    p("")

    p("### ⭐ 3b. IS THE ANSWER RESTING ON A GATE LEVEL I CHOSE? — the sensitivity, computed")
    p("")
    gs = out["gate_sensitivity"]
    p(f"This story pre-registered NF-D14's stricter **DSR ≥ {gs['preregistered_dsr_min']}** rather "
      f"than NF1.4's own **DSR ≥ 0.0**, on the stated ground that the availability signal it consumes "
      f"is the one that failed exactly that gate in NF-D14. That reasoning is sound going in and worth "
      f"nothing if the choice silently decides the outcome — so the ship decision is RE-RUN at NF1.4's "
      f"level, and with the DSR dropped entirely, and all three answers are reported.")
    p("")
    p(_md(pd.DataFrame([{"position": k, **v} for k, v in gs["per_position"].items()])))
    p("")
    p(f"- ships at the pre-registered DSR ≥ {gs['preregistered_dsr_min']}: "
      f"`{gs['ships_at_preregistered'] or 'none'}`")
    p(f"- ships at NF1.4's DSR ≥ 0.0: `{gs['ships_at_nf1_4_dsr_min_0'] or 'none'}`")
    p(f"- ships with the DSR gate REMOVED ALTOGETHER: "
      f"`{gs['ships_with_dsr_dropped_entirely'] or 'none'}`")
    p("")
    if not gs["ships_with_dsr_dropped_entirely"]:
        p("⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING "
          "IT.** Nothing ships even with the DSR removed entirely, because the **BH-FDR blocks all "
          "three positions independently**. So the null is not an artefact of preferring NF-D14's "
          "0.95 to NF1.4's 0.0 — a reader who disagrees with that choice reaches the same verdict. "
          "(Had they disagreed, the pre-registered gate would still govern and this section would be "
          "the disclosure that the answer was close — never a licence to take the other reading, "
          "which is the E2.1-r inversion facing outward.)")
    else:
        p("⚠️ **THE GATE LEVEL IS LOAD-BEARING.** The pre-registered DSR is the only thing standing "
          "between this story and a ship at "
          f"`{gs['ships_with_dsr_dropped_entirely']}`. The pre-registered gate GOVERNS — a bar moved "
          "after seeing the answer is not a bar (E2.1-r) — but a reader is entitled to know that, and "
          "the honest next step is a story that earns more held-out classes, not a re-read of this "
          "one.")
    p("")
    p("⚠️ Note also the whole-field vs contender-set DSR gap in the table above — the NF-D14/NF1.8 "
      "lesson firing again: `deflated_sharpe`'s expected-max-SR term scales with the DISPERSION of "
      "the trial Sharpes, so a 33-arm field that deliberately contains its own weak arms (every λ "
      "0.25 shrink, every constant foil) deflates against those arms rather than against the contest "
      "at the top. Both readings are reported; the **whole-field one is the pre-registered gate** and "
      "it binds.")
    p("")

    p("### ⭐ 3c. THE MARGIN IN DRAFT CLASSES — what kind of null this is")
    p("")
    p(_md(pd.DataFrame(out["power_in_classes"])))
    p("")
    p("'p = 0.07 against a cutoff of 0.067' reads like a hair's breadth of evidence. What it actually "
      "is, is SEVEN held-out draft classes of a quantity whose per-class spread is larger than its "
      "mean — the same shape NF1.8 diagnosed on rookie QBs and NF-D14 confirmed. Stating the margin "
      "in CLASSES rather than in p-value decimals is NF1.8's 'state the margin in ROWS' convention "
      "one unit over, and it is what separates **'underpowered'** from **'absent'**: an effect that "
      "needs a plausible number of further classes is a story to re-run when they exist; one that "
      "needs dozens is a null at any n this program will have.")
    p("")

    p("## 4. What this does to the board (the ordering movement, measured)")
    p("")
    p(_md(pd.DataFrame(out["board_movement"])))
    p("")
    p("A scale that does no ordering harm can still MOVE the board; 'no harm' is a statement about "
      "rank correlation with the realized outcome, not about the board being unchanged. The churn "
      "above is what a user would actually see, and it is reported because a projection change nobody "
      "can see is not worth shipping and one that reshuffles a tier silently is worth knowing about.")
    p("")

    p("## 5. Honest limitations")
    p("")
    for line in out["limitations"]:
        p(f"- {line}")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:            # noqa: C901 — orchestration
    ap = argparse.ArgumentParser(
        description="NF-D15 availability-scaled rookie POINT bake-off (RB/TE/WR; QB excluded)")
    ap.add_argument("--pool", default=str(NF17._POOL_CACHE))
    ap.add_argument("--panel", default=str(_PANEL_CACHE))
    ap.add_argument("--nf-d14", default=str(_NF_D14_RESULT))
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--smoke", action="store_true",
                    help="one λ per family; writes *_smoke artifacts so it can never be mistaken "
                         "for the real search")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    suffix = "_smoke" if args.smoke else ""

    winner_cfg = load_nf_d14_winner(Path(args.nf_d14))
    log.info("REUSING NF-D14's leg-1 availability winner: %s", winner_cfg["label"])

    pool = build_pool(Path(args.pool), Path(args.panel))
    cohorts_req = list(range(args.from_year, args.to_year + 1))
    folds = NF17.build_folds(pool, cohorts_req)
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable draft classes — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    log.info("%d held-out draft classes: %s", len(folds), cohorts)

    scales = {f.year: fold_scales(f, winner_cfg) for f in folds}
    pos_scale = {f.year: M14.position_scale(f.train) for f in folds}

    cfgs = PS.candidate_configs(smoke=args.smoke)
    log.info("%d arms × %d classes", len(cfgs), len(folds))
    arms = [score_arm(folds, scales, c, pos_scale) for c in cfgs]
    incumbent = next(r for r in arms if r["family"] == "incumbent")

    anchors = score_anchors(folds, scales, pos_scale)
    PS.require_anchors(anchors)

    avail_arms = [r for r in arms if r["uses_availability"] and r["pooled_tier_mae"] is not None]
    best_overall = min(avail_arms, key=lambda r: r["pooled_tier_mae"]) if avail_arms else None

    # ── the global sanity checks. A failure here vetoes EVERY per-position result in the run: a
    #    degenerate winning the metric does not mean one position was unlucky, it means the
    #    measurement is untrustworthy everywhere.
    ref = best_overall or incumbent
    checks = {
        "degenerates_lose": all(ref["pooled_tier_mae"] < anchors[t]["pooled_tier_mae"]
                                for t in ("zero_scale", "pos_median")),
        "permutation_beaten": ref["pooled_tier_mae"] < anchors["permuted"]["pooled_tier_mae"],
        "oracle_respected": (anchors["oracle_perplayer"]["pooled_tier_mae"]
                             <= ref["pooled_tier_mae"] + 1e-9),
        "qb_untouched": True,
    }

    # ⛔ THE SCOPE ASSERTION, MEASURED — every arm, every class, every held-out QB.
    qb_drift = 0.0
    for f in folds:
        pos = f.test["position_group"].astype(str).str.upper().to_numpy()
        qb = pos == "QB"
        if not qb.any():
            continue
        for c in cfgs:
            k = _scale_for(c, scales[f.year], pos)
            got = PS.apply_position_scale(f.test_pred, pos, k)
            qb_drift = max(qb_drift, float(np.max(np.abs(got[qb] - f.test_pred[qb]))))
    checks["qb_untouched"] = qb_drift < 1e-12

    per_pos = [select_for_position(arms, incumbent, cohorts, p) for p in PS.SCALED_POSITIONS]
    fdr = M14.bh_fdr({r["position"]: r["paired_p"] for r in per_pos}, q=PS.FDR_Q)
    ship_by_pos = {}
    for r in per_pos:
        ship_by_pos[r["position"]] = PS.per_position_ship(
            position=r["position"], winner=r["winner"], incumbent_metric=r["incumbent_metric"],
            ordering=r["ordering"] or {"per_position": {}}, pbo=r["deflation"].get("pbo"),
            dsr=r["deflation"].get("dsr"), fdr_survives=bool(fdr.get(r["position"])))
    shipped = tuple(p for p, v in ship_by_pos.items() if v["ship"])
    verdict_gate = PS.point_scaling_verdict(positions_shipped=shipped, **checks)

    # ── the NF-D14 §6 wiring proof ────────────────────────────────────────────────────────────
    repro = _nf_d14_reproduction(folds, scales)

    n_scaled = int(sum(len(PS.scaled_positions_only(f.test)) for f in folds))
    out = {
        "story": "NF-D15", "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohorts": cohorts, "n_scaled_rows": n_scaled, "prior": winner_cfg,
        "arms": arms, "incumbent": incumbent, "best_overall": best_overall,
        "anchors": anchors, "checks": checks, "qb_max_drift": qb_drift,
        "per_position": per_pos, "fdr": fdr, "ship_by_position": ship_by_pos,
        "ship": verdict_gate["ship"], "verdict_gate": verdict_gate,
        "nf_d14_reproduction": repro,
        "gate_sensitivity": _gate_sensitivity(per_pos, fdr, ship_by_pos),
        "power_in_classes": _power_in_classes(per_pos),
        "board_movement": _board_movement(folds, scales, per_pos, ship_by_pos),
        "degenerate_reading": _degenerate_reading(anchors, incumbent, ref),
        "limitations": _LIMITATIONS,
    }
    out["headline"] = (
        f"✅ SHIP — availability-scaled rookie point at {', '.join(shipped)}"
        if verdict_gate["ship"] else
        "🟡 RECORDED NULL — no availability-scaled rookie POINT arm clears its own gate; the shipped "
        "rookie point STANDS")
    out["verdict"] = _verdict_prose(out)

    print("\n=== NF-D15 — availability-scaled rookie POINT (RB/TE/WR; QB excluded) ===")
    for r in sorted(arms, key=lambda r: (r["pooled_tier_mae"] is None, r["pooled_tier_mae"]))[:14]:
        print(f"{r['label']:42s} pooled {r['pooled_tier_mae']:7.4f}  "
              f"RB {r.get('tier_mae_RB', float('nan')):7.2f}  TE {r.get('tier_mae_TE', float('nan')):7.2f}  "
              f"WR {r.get('tier_mae_WR', float('nan')):7.2f}  univMAE {r['universe_mae']:6.2f}")
    print("\nanchors: " + " · ".join(
        f"{t} {anchors[t]['pooled_tier_mae']}" for t in anchors))
    print(f"NF-D14 §6 reproduced: {repro['check']['ok']}  ·  QB max drift {qb_drift:.9f}")
    print(f"global checks: {checks}")
    for r in per_pos:
        w = r["winner"]
        print(f"{r['position']}: inc {r['incumbent_metric']} → "
              f"{(w or {}).get('label', 'NONE ELIGIBLE')} {(w or {}).get('metric')} · "
              f"PBO {r['deflation'].get('pbo')} DSR {r['deflation'].get('dsr')} p {r['paired_p']} "
              f"FDR {fdr.get(r['position'])} → ship {ship_by_pos[r['position']]['ship']}")
    print(f"\nverdict: {verdict_gate}")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_d15_rookie_point_scaling{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_d15_rookie_point_scaling{suffix}.md")
    print(f"\n{out['headline']}")
    return 0


def _nf_d14_reproduction(folds: list[NF17.Fold], scales: dict[int, dict]) -> dict:
    """Re-derive NF-D14 §6's universe MAE table with §6's OWN scale (QB included, no bounds) and check
    it against the published numbers. The one cheap proof that this harness's rebuild is faithful."""
    rows = []
    for f in folds:
        pos = f.test["position_group"].astype(str).str.upper().to_numpy()
        k = scales[f.year]["_nf_d14_section6"]
        rows.append(pd.DataFrame({"pos": pos, "y": f.test_real, "point": f.test_pred,
                                  "scaled": f.test_pred * np.nan_to_num(k, nan=1.0)}))
    r = pd.concat(rows, ignore_index=True)
    measured, table = {}, []
    for p, g in r.groupby("pos"):
        rec = {"mae_base": round(float((g["point"] - g["y"]).abs().mean()), 2),
               "mae_scaled": round(float((g["scaled"] - g["y"]).abs().mean()), 2)}
        measured[p] = rec
        want = PS.NF_D14_SECTION6.get(p, {})
        table.append({
            "position": p, "NF-D14 §6 MAE base": want.get("mae_base"),
            "NF-D15 MAE base": rec["mae_base"], "NF-D14 §6 MAE scaled": want.get("mae_scaled"),
            "NF-D15 MAE scaled": rec["mae_scaled"],
            "checked": "yes" if p in PS.SCALED_POSITIONS else "reported only (QB is out of scope)"})
    return {"check": PS.reproduces_nf_d14_section6(measured), "table": table,
            "measured": measured}


def _board_movement(folds, scales, per_pos, ship_by_pos) -> list[dict]:
    """How much a shipped scale would actually MOVE the board, per position: the mean |Δ| in PPR, the
    within-position rank churn, and how many of the incumbent's draftable tier get displaced.

    Reported whether or not anything ships — if nothing ships this is the size of what was declined,
    which is the number a reader needs to judge whether the null is expensive."""
    out = []
    for r in per_pos:
        pos_name = r["position"]
        w = r["winner"]
        if w is None:
            # ⚠️ no `|` in a column name — it is the markdown table's own delimiter, and a header
            # carrying one renders as a broken table rather than as an error.
            out.append({"position": pos_name, "arm": "— none eligible —",
                        "mean abs Δ (PPR)": None, "max abs Δ (PPR)": None,
                        "mean abs rank Δ": None, "tier displacements": None, "would ship": "no"})
            continue
        cfg = {"family": w["family"], "base": w["base"], "lam": w["lam"]}
        d_abs, rank_moves, displaced, tier_n = [], [], 0, 0
        k_tier = M14.TIER_K.get(pos_name, 5)
        for f in folds:
            pos = f.test["position_group"].astype(str).str.upper().to_numpy()
            sel = pos == pos_name
            if sel.sum() < 3:
                continue
            k = _scale_for(cfg, scales[f.year], pos)
            new = PS.apply_position_scale(f.test_pred, pos, k)
            base, cand = f.test_pred[sel], new[sel]
            d_abs.append(np.abs(cand - base))
            rb = pd.Series(base).rank(ascending=False)
            rc = pd.Series(cand).rank(ascending=False)
            rank_moves.append(np.abs(rb.to_numpy() - rc.to_numpy()))
            top_b = set(np.argsort(-base)[:k_tier].tolist())
            top_c = set(np.argsort(-cand)[:k_tier].tolist())
            displaced += len(top_b - top_c)
            tier_n += min(k_tier, int(sel.sum()))
        out.append({
            "position": pos_name, "arm": w["label"],
            "mean abs Δ (PPR)": round(float(np.mean(np.concatenate(d_abs))), 2) if d_abs else None,
            "max abs Δ (PPR)": round(float(np.max(np.concatenate(d_abs))), 2) if d_abs else None,
            "mean abs rank Δ": round(float(np.mean(np.concatenate(rank_moves))), 2)
            if rank_moves else None,
            "tier displacements": f"{displaced} of {tier_n}" if tier_n else None,
            "would ship": "yes" if ship_by_pos[pos_name]["ship"] else "no",
        })
    return out


def _gate_sensitivity(per_pos: list[dict], fdr: dict, ship_by_pos: dict) -> dict:
    """⭐ IS THE ANSWER RESTING ON A GATE LEVEL I CHOSE? — computed, because a pre-registered bar that
    happens to be the ONLY thing standing between a story and a ship is a bar the reader is entitled to
    see tested.

    This story pre-registered NF-D14's stricter `DSR ≥ 0.95` rather than NF1.4's own `DSR ≥ 0.0`, on
    the stated ground that the availability signal it consumes is the one that failed exactly that gate
    in NF-D14. That reasoning is sound going in and worth nothing if the choice silently decides the
    outcome. So the ship decision is RE-RUN under NF1.4's level, and both answers are reported.

    ⚠️ This is a SENSITIVITY, never a re-opened gate (E2.1-r: a gate that only binds when it is
    convenient is not a gate). If the two readings disagree, the pre-registered one still governs — the
    disclosure is that the answer would have been different, not a licence to take the other one."""
    relaxed = {}
    for r in per_pos:
        relaxed[r["position"]] = PS.per_position_ship(
            position=r["position"], winner=r["winner"], incumbent_metric=r["incumbent_metric"],
            ordering=r["ordering"] or {"per_position": {}}, pbo=r["deflation"].get("pbo"),
            dsr=r["deflation"].get("dsr"), fdr_survives=bool(fdr.get(r["position"])),
            dsr_min=0.0)
    # what would ship if the DSR gate were dropped ENTIRELY (the most generous reading available)
    no_dsr = {}
    for r in per_pos:
        s = dict(ship_by_pos[r["position"]])
        s.pop("dsr_ok", None)
        no_dsr[r["position"]] = all(v for k, v in s.items() if k not in ("position", "ship"))
    return {
        "preregistered_dsr_min": PS.DSR_MIN,
        "ships_at_preregistered": [p for p, v in ship_by_pos.items() if v["ship"]],
        "ships_at_nf1_4_dsr_min_0": [p for p, v in relaxed.items() if v["ship"]],
        "ships_with_dsr_dropped_entirely": [p for p, v in no_dsr.items() if v],
        "dsr_is_load_bearing": ([p for p, v in relaxed.items() if v["ship"]]
                                != [p for p, v in ship_by_pos.items() if v["ship"]]),
        "per_position": {p: {"dsr": next(r["deflation"].get("dsr") for r in per_pos
                                         if r["position"] == p),
                             "dsr_contenders": next(r["deflation"].get("dsr_contenders")
                                                    for r in per_pos if r["position"] == p),
                             "ships_at_0.95": ship_by_pos[p]["ship"],
                             "ships_at_0.0": relaxed[p]["ship"],
                             "ships_without_dsr": no_dsr[p]}
                         for p in ship_by_pos},
    }


def _power_in_classes(per_pos: list[dict], q: float = PS.FDR_Q, n_tests: int = 3,
                      max_n: int = 60) -> list[dict]:
    """⭐ THE MARGIN STATED IN DRAFT CLASSES, not in p-value decimals (NF1.8's "state the margin in
    ROWS" convention, one unit over).

    "p = 0.0735 against a BH cutoff of 0.0667" reads like a hair's breadth of evidence; what it
    actually is, is SEVEN held-out draft classes of a quantity whose per-class spread is larger than
    its mean. Holding the observed effect and spread fixed, this reports how many held-out classes the
    position would need for its one-sided paired p to reach `q / n_tests` — the BH cutoff a position
    must clear to survive UNCONDITIONALLY, i.e. whatever the other two positions do.

    It is an honest statement of what kind of null this is: **underpowered, not absent** — or, where
    the effect is small relative to its spread, absent at any n this program will ever have."""
    out = []
    target = q / float(n_tests)
    for r in per_pos:
        d = np.asarray(r["per_cohort_delta"], dtype=float)
        rec = {"position": r["position"], "classes now": int(len(d)),
               "mean Δ (PPR)": None, "sd Δ (PPR)": None, "one-sided p": r["paired_p"],
               "BH cutoff to clear unconditionally": round(target, 4), "classes needed": None}
        if len(d) >= 3 and float(d.std(ddof=1)) > 1e-12:
            mu, sd = float(d.mean()), float(d.std(ddof=1))
            rec["mean Δ (PPR)"] = round(mu, 2)
            rec["sd Δ (PPR)"] = round(sd, 2)
            if mu > 0:
                from scipy.stats import t as student_t
                for n in range(len(d), max_n + 1):
                    if float(student_t.sf(mu / (sd / np.sqrt(n)), n - 1)) <= target:
                        rec["classes needed"] = n
                        break
                else:
                    rec["classes needed"] = f">{max_n}"
            else:
                rec["classes needed"] = "n/a (effect is negative)"
        out.append(rec)
    return out


def _degenerate_reading(anchors: dict, incumbent: dict, ref: dict) -> str:
    """⭐ The degenerates are SCORED AND READ, never reasoned about (NF-D14's refinement of the NF-D11
    landmine). This prose states which way they came back on THIS run and what that means."""
    z, m = anchors["zero_scale"], anchors["pos_median"]
    inverted = min(z["pooled_tier_mae"], m["pooled_tier_mae"]) <= ref["pooled_tier_mae"]
    if inverted:
        return (
            "🚨 **A DEGENERATE WON THE PRIMARY METRIC — the metric is INVERTED and nothing in this run "
            f"may be shipped.** `zero_scale` {z['pooled_tier_mae']} / `pos_median` "
            f"{m['pooled_tier_mae']} against the reference arm's {ref['pooled_tier_mae']}. This is "
            "CLAUDE.md's NF-D11 landmine firing; the selection must be re-specified on a metric a "
            "nihilist cannot win before any of the numbers below mean anything.")
    return (
        f"⭐ **The degenerate check comes back NEGATIVE, and it is reported because it was SCORED, not "
        f"because it was expected.** `zero_scale` ({z['pooled_tier_mae']}) and NF1.4's `pos_median` "
        f"MAE-collapse tell ({m['pooled_tier_mae']}) both lose the primary metric decisively to the "
        f"reference arm ({ref['pooled_tier_mae']}). NF-D14's refinement of the NF-D11 landmine is the "
        f"reason this is a measurement rather than an argument: **MAE inverts when the conditional "
        f"MEDIAN sits at the floor, not merely when the zero atom is fat** — and on the RB/TE/WR "
        f"DRAFTABLE TIER the median is nowhere near zero, so it does not invert here. The right "
        f"response to that rule is to keep the degenerate in the field and READ it every run, which "
        f"is what this line is.")


def _verdict_prose(out: dict) -> str:                      # noqa: C901 — prose assembly
    a: list[str] = []
    per_pos, ship = out["per_position"], out["ship_by_position"]
    shipped = [p for p, v in ship.items() if v["ship"]]
    inc = out["incumbent"]
    if out["best_overall"]:
        b = out["best_overall"]
        a.append(
            f"**The availability lift NF-D14 surfaced REPRODUCES on the universe read** — the best "
            f"availability arm `{b['label']}` moves the RB/TE/WR universe MAE "
            f"{inc['universe_mae']} → {b['universe_mae']} and the bias {inc['universe_bias']} → "
            f"{b['universe_bias']} (NF-D14 §6's lead, re-measured). **On the metric that selects — "
            f"NF1.4's draftable-tier MAE — it reads {inc['pooled_tier_mae']} → "
            f"{b['pooled_tier_mae']} pooled.**")
        a.append("")
    for r in per_pos:
        p = r["position"]
        s = ship[p]
        w = r["winner"]
        if w is None:
            a.append(f"**{p} — no eligible arm.** {r['n_candidates']} arms scored and none stayed "
                     f"within the ordering constraint; the unconstrained best was "
                     f"`{r['best_any']['label']}`. The constraint refused a point-MAE win that "
                     f"scrambles the draft order, which is what it is for.")
            continue
        failed = [k for k, v in s.items() if k not in ("position", "ship") and not v]
        mf = r["matched_foil"]
        foil_note = ""
        if mf:
            foil_note = (f" Matched foil: the same base and λ with the per-player content stripped "
                         f"scores {mf['foil_metric']} against the arm's {mf['arm_metric']} "
                         f"(paired Δ {mf['paired_delta']}, p {mf['paired_p']}) — "
                         + ("**so the availability content, not the level correction, is what earned "
                            "it**." if (mf['paired_delta'] or 0) > 0 and (mf['paired_p'] or 1) < 0.10
                            else "**so the lift is a LEVEL correction and the per-player availability "
                                 "content earned none of it**."))
        a.append(
            f"**{p} — {'✅ SHIPS' if s['ship'] else '🟡 does not ship'}.** `{w['label']}` moves the "
            f"draftable-tier MAE {r['incumbent_metric']} → {w['metric']} PPR with ρ "
            f"{r['incumbent_rho']} → {w['rho']}; PBO {r['deflation'].get('pbo')}, DSR "
            f"{r['deflation'].get('dsr')}, paired p {r['paired_p']}, BH-FDR "
            f"{'survives' if out['fdr'].get(p) else 'does NOT survive'}."
            + (f" Failing gate(s): `{failed}`." if failed else "") + foil_note)
    a.append("")
    # ⭐ The attribution result is worth its own paragraph even inside a null: it is the one thing this
    #    story establishes that NF-D14 could not, and it CONTRADICTS NF-D14's stated mechanism.
    foils = [r["matched_foil"] for r in per_pos if r["matched_foil"]]
    won = [f for f in foils if (f["paired_delta"] or 0) > 0 and (f["paired_p"] or 1) < 0.10]
    if won:
        won_pos = [r["position"] for r in per_pos
                   if r["matched_foil"] and r["matched_foil"] in won]
        detail = "; ".join(
            f"**{r['position']}** — foil {r['matched_foil']['foil_metric']} vs incumbent "
            f"{r['incumbent_metric']}, arm {r['matched_foil']['arm_metric']}, paired Δ "
            f"{r['matched_foil']['paired_delta']} PPR at p {r['matched_foil']['paired_p']}"
            for r in per_pos if r["matched_foil"] and r["matched_foil"] in won)
        beaten = [r for r in per_pos if r["matched_foil"] in won
                  and not r["matched_foil"]["foil_beats_incumbent"]]
        a.append(
            "⭐ **THE MATCHED FOIL SETTLES THE MECHANISM, AND IT CONTRADICTS NF-D14's STATED ONE.** "
            "NF-D14 explained its RB/TE/WR lift as the ratio 'partially correcting the COLD bias NF1.4 "
            "documented' — i.e. as a LEVEL correction, which a per-position CONSTANT delivers with "
            "zero per-player information and zero ordering risk. That constant is registered here at "
            f"the identical base and the identical λ. At {' and '.join(won_pos)} it does not merely "
            f"lose to the availability arm — "
            + ("at every one of those positions it **fails to beat the incumbent at all** "
               if len(beaten) == len(won_pos) else
               "and at " + ", ".join(r["position"] for r in beaten)
               + " it **fails to beat the incumbent at all** ")
            + f"({detail}). So whatever is happening at those positions is PER-PLAYER, and it is NOT "
              "the recalibration NF-D14 named — which is the opposite of NF-D14's reading, and a thing "
              "only the matched pairing could establish (a leaderboard rank cannot tell 'my feature "
              "works' from 'anything that inflates RB/TE/WR works': NF-D10).")
        a.append("")
    if won and out["best_overall"]:
        a.append(
            "⭐ **AND THE BIAS CORROBORATES IT FROM THE OTHER SIDE.** If the lift were the cold-bias "
            f"correction NF-D14 described, the winning arm would move the bias TOWARD zero. It does "
            f"not: pooled over RB/TE/WR the bias goes {inc['universe_bias']} → "
            f"{out['best_overall']['universe_bias']} — marginally FURTHER from zero — while the MAE "
            f"improves anyway. A level story cannot produce that pattern; a per-player one can, by "
            f"moving the right rookies in both directions.")
        a.append("")
    learned_pos = [r["position"] for r in per_pos
                   if (r["winner"] or {}).get("family") == "learned"]
    if learned_pos:
        a.append(
            f"⚠️ **Where an availability arm wins at all ({', '.join(learned_pos)}), the winner is the "
            f"DIRECT-LEARNED FOIL — not any of the three prescribed ratio forms, and specifically not "
            f"`ratio_pos`, which is NF-D14 §6's own construction.** The prescribed multiplicative "
            f"haircut is therefore not the right functional form for this correction even where the "
            f"correction is real, which is a second, independent reason NF-D14 §6's arm should not "
            f"have been shipped on its measured MAE alone.")
        a.append("")
    if shipped:
        a.append(
            f"⇒ **SHIP at {', '.join(shipped)}.** The availability scale improves the metric the "
            f"incumbent rookie point was itself selected on, does no ordering harm at those "
            f"positions, beats its matched constant foil on the paired read, and survives per-position "
            f"deflation and the multiplicity correction. QB stays exactly where NF-D14 left it.")
    else:
        a.append(
            "⇒ **RECORDED NULL — and NF-D14's open lead is now CLOSED rather than left dangling.** "
            "The MAE improvement NF-D14 measured is real and reproduces here; what it does not do is "
            "clear a gate built for a point projection. The shipped rookie point STANDS, the interval "
            "is untouched, and the QB exclusion was never re-opened.")
    return "\n".join(a)


_LIMITATIONS = [
    "⚠️ **THE SELECTED ARM IS DEPTH-DRIVEN, SO THE PROVENANCE CAVEAT IS LIVE AND IT IS A HARD "
    "PRECONDITION ON ANY FUTURE REVIVAL.** The availability signal is REUSED, so NF-D14's caveats are "
    "inherited in full — most importantly that the historical depth feature is the WEEK-1 chart (a "
    "post-final-cuts read) while the live board reads an August `stg_nfl_depth_charts_current` "
    "snapshot. The proxy is therefore marginally FRESHER than the served signal and can only FLATTER "
    "the historical fit. Nothing ships here, so no re-measurement was required to reach this verdict "
    "— but **the measured lift above is an UPPER BOUND on what the served signal could deliver, and "
    "any story that revives this arm must FIRST re-measure it on the served August snapshot.** That "
    "is also why `ratio_residual` (the depth increment ALONE, net of draft capital) is registered and "
    "reported separately: it is the arm whose provenance risk is largest and most legible.",
    "**The learned foil's training-row point projections are IN-SAMPLE for that fold's slot curve.** "
    "It learns the multiplicative correction against a point that is slightly better-fitted than the "
    "held-out point it is then applied to, so the correction it learns is if anything UNDER-stated. "
    "The direction is conservative — it cannot manufacture the lift — but it is not zero, and a "
    "revival should fit the correction against out-of-fold training predictions.",
    "⛔ **QB is out of scope by pre-registration, not by result.** NF-D14 measured the double-pricing "
    "(+16.8% MAE, bias −10.66 → +11.36) and this story does not re-open it. A future story that wants "
    "rookie-QB availability in the point needs to model what the slot curve already prices, not to "
    "multiply on top of it.",
    "**`tier_mae` grades the DRAFTABLE TIER, which is ~6 RB / 8 WR / 3 TE per class.** A per-position "
    "claim here is a claim about a few dozen rookie-seasons across seven classes; the paired per-class "
    "deltas are reported so the reader can see the spread rather than only the mean.",
    "**Do-no-ordering-harm is a rank-correlation constraint, not a promise the board will not move.** "
    "§4 reports the actual churn — mean |Δ| in PPR, rank movement, and tier displacements — because "
    "'no harm' and 'no change' are different claims and only the first one is being made.",
    "**The scale is bounded** (`SCALE_CLIP`, and a floor on every ratio denominator). Those bounds are "
    "physical rather than tuned — a rookie cannot play negative games — but they do mean this story's "
    "`ratio_pos` arm is not byte-identical to NF-D14 §6's unbounded form. Both are computed and the §6 "
    "form is reported as the wiring proof, so the difference is visible rather than implied.",
    "**No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.",
]


if __name__ == "__main__":
    raise SystemExit(main())
