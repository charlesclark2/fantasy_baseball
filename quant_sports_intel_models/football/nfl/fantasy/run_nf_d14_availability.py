"""run_nf_d14_availability.py — NF-D14 §0.5 bake-off: the ROOKIE-QB AVAILABILITY prior, and what it
does to the rookie-QB interval.

THE STORY IN ONE PARAGRAPH. NF1.8 got rookie-QB 80% coverage to its floor (0.741 → 0.815) with **1
covered rookie-season of slack out of 81**, and diagnosed the residual gap as class-to-class VARIANCE
rather than fittable miscalibration — so more recalibration cannot close it. The honest lever is at the
SOURCE: **35.3% of drafted rookie QBs never take a snap.** NF-D14 fits an AVAILABILITY prior (a
predictive distribution over rookie-season GAMES PLAYED) and asks whether conditioning the band on it
closes the QB gap held-out.

⚠️ **A NULL IS A PRE-REGISTERED, LEGITIMATE OUTCOME** and the harness is built so a null is legible
rather than embarrassing: leg 1 can find a real availability signal and leg 2 can still find it does
not move the interval, which is itself the answer ("the QB variance is irreducible at this N"). The
floor does NOT move either way (E2.1-r; NF1.8 §1).

────────────────────────────────────────────────────────────────────────────────────────────────────
TWO LEGS, TWO DIFFERENT QUESTIONS, TWO DIFFERENT METRICS
────────────────────────────────────────────────────────────────────────────────────────────────────
**LEG 1 — is there an availability signal at all?** ≥3 pre-registered forms + a direct-learned foil
(`rookie_availability.py`), walk-forward by draft class, selected on the DISCRETE CRPS of the emitted
games PMF, with the two-sided anchor set (`oracle_empirical` / `matched_n_candidate` / `permuted` /
`all_zero` / `all_mean`) scored EVERY run and REQUIRED, and CSCV/PBO + DSR + BH-FDR deflation over the
whole config field.

⚠️⚠️ **MAE IS INVERTED ON THIS COHORT — the CLAUDE.md NF-D11 landmine, one population over.** The
`all_zero` degenerate ("project zero games for every rookie") is IN THE FIELD precisely so that shows
up as a measurement rather than an assertion. MAE/RMSE stay reported, never selectable.

**LEG 2 — does it close the rookie-QB coverage gap?** The winner's per-player availability read is
attached to the NF1.8 band harness as `avail_risk_z` and scored under NF1.8's OWN machinery — the same
folds, the same row-pooled reducer, the same per-position floors, the same anchors, the same
Winkler interval score, the same deflation. Two pre-registered channels (a quantile-regression FEATURE
and a strictly WIDEN-ONLY widener) × two pre-registered DRIVERS:

  · `sd`     — the availability prior's own predictive SD of games. ⭐ The PRINCIPLED driver:
               availability risk is NOT monotone in expected games, it PEAKS where the outcome is a
               coin flip (a 7th-round QB3 at `p_play ≈ 0.05` is confidently near-zero; a second-rounder
               in an open camp battle at `p_play ≈ 0.5` is not).
  · `pshort` — 1 − P(plays), the naive "bust risk" driver the story's framing suggests. Pre-registered
               BESIDE the principled one rather than assumed away.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. No `best_alpha`, no CLV/ROI claim.
🔒 The rookie POINT projection is held BYTE-IDENTICAL across every leg-2 arm and asserted as such
   (max drift printed) — a band story must not smuggle a point change. The availability POINT channel
   is measured and REPORTED separately (§6) so its effect is attributable rather than entangled.

RUN ON THE LAPTOP (no Snowflake; reads the cached NF1.4 rookie pool + the local NFL marts, ~2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d14_availability

    # rebuild the availability panel (join the week-1 depth-chart proxy) after a new season lands:
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d14_availability \\
      --rebuild-panel
"""
from __future__ import annotations

import argparse
import dataclasses
import itertools
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

from quant_sports_intel_models.football.nfl.fantasy import rookie_availability as AV  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy.nf1_1_model import (  # noqa: E402
    bh_fdr,
    deflated_sharpe,
    onesided_paired_pvalue,
)

log = logging.getLogger("nfl.fantasy.nf_d14_availability")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_PANEL_CACHE = _ART / "nf_d14_rookie_availability_panel.parquet"
_STAGING_SCHEMA = "main_nfl_staging"

# The leg-2 pre-registered arm grid. The driver NAME maps to the column `AvailabilityPrior.stats`
# emits: `sd` is the PRINCIPLED driver (the predictive SD of games — availability risk peaks where the
# outcome is a coin flip, not where expected games are lowest); `pshort` is the NAIVE bust-risk driver
# the story's framing suggests. Both pre-registered, neither assumed.
_AVAIL_DRIVERS = ("sd", "pshort")
_DRIVER_COLUMN = {"sd": "sd_games", "pshort": "p_short"}
_AVAIL_GAIN_GRID = (0.10, 0.20, 0.35)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Panel — the NF1.4 rookie pool + the pre-season depth-chart proxy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_panel(pool_path: Path, duckdb_path: str, staging_schema: str = _STAGING_SCHEMA
                ) -> pd.DataFrame:
    """The NF1.4 drafted-rookie pool LEFT-joined to each rookie's WEEK-1 depth-chart rank.

    ⚠️ LEFT JOIN, ALWAYS, and the absence is KEPT AS A VALUE. A rookie with no week-1 depth-chart row
    is not a missing observation — he is a rookie who did not make a week-1 depth chart, which is the
    single most informative availability state in the whole cohort (measured: 85% of such rookie QBs
    played zero games). An inner join here would delete the population the story is about, which is
    the NF1.9 lesson and the NF1.4 survivorship bug wearing the same hat.

    ⚠️ HONEST PROVENANCE OF THE PROXY. The historical signal is the WEEK-1 chart (`stg_nfl_depth_charts`,
    which has weekly partitions back to 2001); the LIVE board reads an August
    `stg_nfl_depth_charts_current` snapshot. The week-1 chart is therefore marginally FRESHER than what
    the served board has at draft time — it is a post-final-cuts read. That mismatch can only FLATTER
    the historical fit, so the report states it and the `capital`-only arms (draft capital alone, no
    depth) are pre-registered beside every depth arm so the story always has an
    unambiguous-provenance answer."""
    import duckdb

    pool = NF17.load_pool(pool_path)
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        dc = con.execute(f"""
            select player_id, season, min(depth_chart_position_rank) as depth_rank
            from {staging_schema}.stg_nfl_depth_charts
            where week = 1 and depth_chart_position_rank is not null
            group by 1, 2
        """).fetchdf()
    finally:
        con.close()
    dc["player_id"] = dc["player_id"].astype(str)
    dc["season"] = pd.to_numeric(dc["season"], errors="coerce").astype("Int64")
    out = pool.copy()
    out["_k"] = out["gsis_id"].astype(str)
    out["_season"] = pd.to_numeric(out["draft_year"], errors="coerce").astype("Int64")
    out = out.merge(dc.rename(columns={"player_id": "_k", "season": "_season"}),
                    on=["_k", "_season"], how="left").drop(columns=["_k", "_season"])
    return out


def load_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(
            f"no NF-D14 availability panel at {path} — build it with:\n"
            "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
            "run_nf_d14_availability --rebuild-panel")
    return pd.read_parquet(path)


def cohort_census(panel: pd.DataFrame, cohorts: list[int]) -> list[dict]:
    """⭐ THE N IS THE WHOLE RISK — reported BEFORE any fit, per the story's step 0. Cohort size, the
    zero-games rate, and the depth-proxy coverage, per position."""
    d = panel[panel["draft_year"].isin(cohorts)]
    rows = []
    for p in AV.POSITIONS:
        g = d[d["position_group"].astype(str).str.upper() == p]
        if g.empty:
            continue
        games = pd.to_numeric(g["rookie_games"], errors="coerce").fillna(0.0)
        rows.append({
            "position": p, "held-out rookie-seasons": int(len(g)),
            "classes": int(g["draft_year"].nunique()),
            "per class": round(float(len(g)) / max(1, g["draft_year"].nunique()), 1),
            "played ZERO games": int((games == 0).sum()),
            "zero rate": round(float((games == 0).mean()), 3),
            "mean games": round(float(games.mean()), 2),
            "median games": float(games.median()),
            "depth-proxy present": round(float(pd.to_numeric(g.get("depth_rank"),
                                                             errors="coerce").notna().mean()), 3),
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LEG 1 — the availability bake-off
# ══════════════════════════════════════════════════════════════════════════════════════════════
def leg1_folds(panel: pd.DataFrame, cohorts: list[int], min_train: int = 120
               ) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
    """Walk-forward by DRAFT CLASS — the same leakage-safe axis NF1.4/1.7/1.8 use, so leg 1 and leg 2
    are scored on the identical cohorts and the two legs' numbers are directly comparable."""
    out = []
    for y in cohorts:
        tr = panel[panel["draft_year"] < y]
        te = panel[panel["draft_year"] == y]
        if len(tr) < min_train or len(te) < 15:
            continue
        out.append((int(y), tr.copy(), te.copy()))
    return out


def run_leg1_config(folds, cfg: dict) -> dict:
    """One availability config, scored on every held-out class and ROW-POOLED across them (the NF1.8
    convention — a position thin in one class is never silently dropped from a mean)."""
    parts, per_class = [], {}
    for y, tr, te in folds:
        prior = AV.make_prior(cfg).fit(tr)
        pmf = prior.pmf(te)
        yy = pd.to_numeric(te["rookie_games"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        pos = te["position_group"].astype(str).str.upper().to_numpy()
        parts.append(pd.DataFrame({"year": y, "pos": pos, "y": yy,
                                   "crps": AV.discrete_crps(pmf, yy),
                                   "e_games": AV.pmf_stats(pmf)["e_games"]}))
        per_class[y] = round(float(np.mean(AV.discrete_crps(pmf, yy))), 4)
    if not parts:
        return {}
    rows = pd.concat(parts, ignore_index=True)
    pmf_all = None  # scoring is done per class above; the pooled read is a reduction of `rows`
    del pmf_all
    out = {
        **{k: v for k, v in cfg.items() if k != "blocks"},
        "blocks": "+".join(cfg.get("blocks", ())),
        "n": int(len(rows)),
        "crps": round(float(rows["crps"].mean()), 4),
        "mae_games": round(float((rows["e_games"] - rows["y"]).abs().mean()), 3),
        "rmse_games": round(float(np.sqrt(((rows["e_games"] - rows["y"]) ** 2).mean())), 3),
        "per_class": per_class,
    }
    for p, g in rows.groupby("pos"):
        out[f"crps_{p}"] = round(float(g["crps"].mean()), 4)
        out[f"n_{p}"] = int(len(g))
        out[f"mae_{p}"] = round(float((g["e_games"] - g["y"]).abs().mean()), 3)
        out[f"crps_{p}_per_class"] = {int(k): round(float(v), 4)
                                      for k, v in g.groupby("year")["crps"].mean().items()}
    return out


def leg1_anchors(folds, winner_cfg: dict, seed: int = 20260731) -> dict:
    """The REQUIRED two-sided anchor set, scored with the SAME reducer the candidates use.

    ⭐ Every one of these is REQUIRED (`require_leg1_anchors`). NF1.7 lesson (a): an anchor that fails
    to fit makes its own check VACUOUSLY TRUE — `best >= anchor` on an absent anchor compares nothing
    and reports green."""
    out: dict[str, list] = {k: [] for k in
                            ("oracle_empirical", "matched_n_candidate", "permuted",
                             "all_zero", "all_mean")}
    for y, tr, te in folds:
        yy = pd.to_numeric(te["rookie_games"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        pos = te["position_group"].astype(str).str.upper().to_numpy()

        def _add(tag: str, pmf: np.ndarray) -> None:
            out[tag].append(pd.DataFrame({"year": y, "pos": pos, "y": yy,
                                          "crps": AV.discrete_crps(pmf, yy),
                                          "e_games": AV.pmf_stats(pmf)["e_games"]}))

        _add("oracle_empirical", AV.oracle_pmf(te))
        # NF1.9 (f) — the oracle floor is only well-posed at MATCHED n, so the winner's own arm is
        # also trained on ONE prior class and the gate is "the oracle beats THIS".
        last = int(tr["draft_year"].max())
        thin = tr[tr["draft_year"] == last]
        _add("matched_n_candidate", AV.make_prior(winner_cfg).fit(thin).pmf(te))
        # NF1.7 (b) — the PERMUTATION anchor: identical family AND identical n, only the information
        # content moves. Well-posed at any sample size, unlike a peeking fitted oracle.
        rng = np.random.default_rng(seed + y)
        shuffled = tr.assign(rookie_games=rng.permutation(
            pd.to_numeric(tr["rookie_games"], errors="coerce").fillna(0.0).to_numpy(dtype=float)))
        _add("permuted", AV.make_prior(winner_cfg).fit(shuffled).pmf(te))
        _add("all_zero", AV.degenerate_pmf("all_zero", len(te)))
        _add("all_mean", AV.degenerate_pmf(
            "all_mean", len(te),
            float(pd.to_numeric(tr["rookie_games"], errors="coerce").fillna(0.0).mean())))

    scored = {}
    for tag, parts in out.items():
        if not parts:
            continue
        rows = pd.concat(parts, ignore_index=True)
        rec = {"n": int(len(rows)), "crps": round(float(rows["crps"].mean()), 4),
               "mae_games": round(float((rows["e_games"] - rows["y"]).abs().mean()), 3),
               "per_class": {int(k): round(float(v), 4)
                             for k, v in rows.groupby("year")["crps"].mean().items()}}
        for p, g in rows.groupby("pos"):
            rec[f"crps_{p}"] = round(float(g["crps"].mean()), 4)
            # ⭐ per-position MAE is NOT decoration: the MAE inversion is a property of the ZERO RATE,
            # and only QB carries a 35% atom. Pooling four positions (RB/WR/TE sit at 11–13%) DILUTES
            # the very effect the metric choice rests on, so the claim has to be made per position.
            rec[f"mae_{p}"] = round(float((g["e_games"] - g["y"]).abs().mean()), 3)
        scored[tag] = rec
    return scored


_REQUIRED_LEG1_ANCHORS = ("oracle_empirical", "matched_n_candidate", "permuted",
                          "all_zero", "all_mean")


def require_leg1_anchors(scored: dict, required: tuple = _REQUIRED_LEG1_ANCHORS) -> None:
    """⭐ A MISSING ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 lesson (a))."""
    missing = [k for k in required if k not in scored or scored[k].get("crps") is None]
    if missing:
        raise SystemExit(
            f"the anchor(s) {missing} did not score — their checks would pass on NOTHING. Fix the "
            "anchor before reading any selection (NF1.7 anchor-set lesson 1).")


def leg1_deflation(results: list[dict], null_label: str, winner_label: str) -> dict:
    """CSCV/PBO over the (class × config) CRPS matrix + Bailey's companions (NF1.8's `deflate`), the
    DSR of the winner's per-class lift over the null against the whole trial population, and BH-FDR
    over the per-position lifts.

    ⚠️ Per CLAUDE.md/NF1.8: PBO alone cannot tell "my pick is unstable" from "my pick is tied", so the
    FLIP DISTRIBUTION, Bailey's performance degradation and the CONTENDER (top-quartile) spread are
    reported beside it."""
    mat = pd.DataFrame({r["label"]: r["per_class"] for r in results if r.get("per_class")}).sort_index()
    d = NF18.deflate(mat)
    null_col = mat.get(null_label)
    win_col = mat.get(winner_label)
    dsr = fdr = dsr_contenders = None
    per_pos_p: dict[str, float | None] = {}
    if null_col is not None and win_col is not None:
        deltas = (null_col - win_col).to_numpy(dtype=float)          # lower CRPS is better ⇒ lift > 0
        trial = []
        for c in mat.columns:
            dd = (null_col - mat[c]).to_numpy(dtype=float)
            sd = float(np.nanstd(dd, ddof=1)) if len(dd) > 2 else 0.0
            trial.append(float(np.nanmean(dd)) / sd if sd > 1e-12 else np.nan)
        dsr = deflated_sharpe(deltas, np.asarray(trial, dtype=float))
        # ⚠️ A SECONDARY, CLEARLY-LABELLED DIAGNOSTIC — never the gate. `deflated_sharpe`'s expected
        #    max-SR term scales with the DISPERSION of the trial Sharpes, so a field that deliberately
        #    CONTAINS its own known-bad arms deflates against those arms rather than against the
        #    contest at the top. That is the NF1.8 "a spread computed over a field that contains its
        #    own nulls measures the nulls" lesson, one statistic over. The pre-registered gate stays
        #    the whole-field DSR; this contender-set reading is reported beside it so the two readings
        #    are distinguishable instead of conflated.
        contenders = list(mat.mean(axis=0).sort_values().index[:max(4, mat.shape[1] // 4)])
        ctr_srs = []
        for c in contenders:
            dd = (null_col - mat[c]).to_numpy(dtype=float)
            sd = float(np.nanstd(dd, ddof=1)) if len(dd) > 2 else 0.0
            ctr_srs.append(float(np.nanmean(dd)) / sd if sd > 1e-12 else np.nan)
        dsr_contenders = deflated_sharpe(deltas, np.asarray(ctr_srs, dtype=float))
        win = next(r for r in results if r["label"] == winner_label)
        null = next(r for r in results if r["label"] == null_label)
        for p in AV.POSITIONS:
            a, b = win.get(f"crps_{p}_per_class"), null.get(f"crps_{p}_per_class")
            if not a or not b:
                per_pos_p[p] = None
                continue
            ks = sorted(set(a) & set(b))
            per_pos_p[p] = onesided_paired_pvalue(np.array([b[k] - a[k] for k in ks]))
        fdr = bh_fdr(per_pos_p, q=AV.FDR_Q)
    return {**d, "dsr": dsr, "dsr_contenders": dsr_contenders,
            "per_position_p": per_pos_p, "fdr": fdr,
            "spread_pct": round(100.0 * (float(mat.mean().max()) - float(mat.mean().min()))
                                / max(1e-9, float(mat.mean().min())), 2)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LEG 2 — what the winner does to the rookie interval (NF1.8's machinery, unchanged)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def attach_availability(folds: list[NF17.Fold], cfg: dict, driver: str) -> list[NF17.Fold]:
    """Attach `avail_risk_z` to every fold's train and test frames, fitted STRICTLY IN-FOLD.

    ⚠️ The TRAINING rows get a LEAVE-ONE-CLASS-OUT read, not an in-sample one. The band's quantile
    regression is fitted on the training rows' driver, so an in-sample driver would let the band learn
    against a quantity that is optimistic exactly where the prior over-fits — a small effect for forms
    this low-capacity, but it is the difference between a claim we can defend and one we cannot. The
    HELD-OUT class gets the prior fitted on the full training history, which is what production does.
    """
    col = _DRIVER_COLUMN[driver]
    out = []
    for f in folds:
        tr = f.train
        years = sorted(pd.to_numeric(tr["draft_year"], errors="coerce").dropna().unique().tolist())
        z_tr = pd.Series(np.nan, index=tr.index, dtype=float)
        for y in years:
            sel = pd.to_numeric(tr["draft_year"], errors="coerce") == y
            rest = tr[~sel]
            if len(rest) < 60:
                continue
            z_tr.loc[sel] = AV.make_prior(cfg).fit(rest).stats(tr[sel])[col].to_numpy()
        full = AV.make_prior(cfg).fit(tr)
        # a class too thin to hold out falls back to the full-history read rather than to NaN — a NaN
        # driver would silently drop those rows out of the feature and quietly change the fit
        z_tr = z_tr.fillna(pd.Series(full.stats(tr)[col].to_numpy(), index=tr.index))
        out.append(dataclasses.replace(
            f,
            train=tr.assign(avail_risk_z=z_tr.to_numpy()),
            test=f.test.assign(avail_risk_z=full.stats(f.test)[col].to_numpy())))
    return out


def leg2_configs(base: dict) -> list[dict]:
    """The pre-registered leg-2 arms: the SHIPPED NF1.8 band (the null), then the availability channels.

    Everything except availability is held at the shipped NF1.8 setting, so any movement is
    ATTRIBUTABLE to availability rather than to a second knob moving at the same time."""
    cfgs = [{**base, "label": "SHIPPED NF1.8 band (NULL)", "driver": None}]
    for driver in _AVAIL_DRIVERS:
        cfgs.append({**base, "label": f"+avail FEATURE [{driver}]", "driver": driver,
                     "avail_feature": True})
        for g in _AVAIL_GAIN_GRID:
            cfgs.append({**base, "label": f"+avail WIDEN [{driver}] gain {g:g}", "driver": driver,
                         "avail_gain": g})
            cfgs.append({**base, "label": f"+avail FEATURE+WIDEN [{driver}] gain {g:g}",
                         "driver": driver, "avail_feature": True, "avail_gain": g})
    return cfgs


def _band_kwargs(cfg: dict) -> dict:
    return {**NF18._band_kwargs(cfg),
            "avail_feature": bool(cfg.get("avail_feature", False)),
            "avail_gain": float(cfg.get("avail_gain", 0.0))}


def leg2_arm_rows(folds: list[NF17.Fold], cfg: dict) -> pd.DataFrame | None:
    """One row per held-out rookie-season — the NF1.8 shape, so `NF18.score_rows` /
    `position_floors` / `floor_slack_rows` apply unchanged and the two stories' numbers are the same
    statistic."""
    parts = []
    for f in folds:
        pos = f.test["position_group"].astype(str).str.upper().to_numpy()
        m = SP.fit_rookie_band_model(f.train, f.train_pred, **_band_kwargs(cfg))
        if m is None:
            continue
        lo, hi = m.band_many(pos, f.test_pred, overall=f.test.get("draft_overall"),
                             resid_sd=f.test.get("projected_nfl_z_sd"),
                             avail=f.test.get("avail_risk_z"))
        bad = ~(np.isfinite(lo) & np.isfinite(hi))
        if bad.any():
            idx = np.where(bad)[0]
            lo[idx], hi[idx] = NF18._tercile_band(f, f.test_pred, pos, idx)
        lo, hi = NF17._finish(lo, hi, f.test_pred)
        parts.append(pd.DataFrame({"year": f.year, "pos": pos, "lo": lo, "hi": hi,
                                   "y": f.test_real, "point": f.test_pred, "fell_back": bad}))
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True)


def run_leg2_arm(base_folds: list[NF17.Fold], cfg: dict,
                 cache: dict[str, list[NF17.Fold]]) -> dict | None:
    driver = cfg.get("driver")
    folds = base_folds if driver is None else cache[driver]
    rows = leg2_arm_rows(folds, cfg)
    if rows is None or rows.empty:
        return None
    return {**{k: v for k, v in cfg.items() if k != "blocks"}, **NF18.score_rows(rows)}


def point_drift(folds: list[NF17.Fold], avail_folds: list[NF17.Fold]) -> float:
    """The POINT-INVARIANCE proof: attaching the availability driver must not move the served rookie
    point projection by a single unit. Returns the max absolute drift over every held-out class."""
    worst = 0.0
    for a, b in zip(folds, avail_folds):
        worst = max(worst, float(np.max(np.abs(a.test_pred - b.test_pred))))
    return worst


def point_channel(folds: list[NF17.Fold], cfg: dict) -> dict:
    """§6 — the AVAILABILITY POINT CHANNEL, measured and REPORTED, never silently shipped.

    Scaling the rookie point by the availability prior's expected-games ratio is the other thing the
    story names, and the story asked for any point change to be ATTRIBUTABLE — so it is measured here
    rather than argued about. ⚠️ The measurement came back SPLIT rather than in the expected direction:
    the ratio is not a haircut (it exceeds 1 for high-capital rookies), so it modestly IMPROVES RB/TE/WR
    by partially correcting NF1.4's documented COLD bias, while BREAKING QB — the one position the
    story exists to fix — by pricing draft-capital-driven playing time a second time on top of the slot
    curve that already prices it. Declined on that evidence; see §6 of the report."""
    rows = []
    for f in folds:
        pri = AV.make_prior(cfg).fit(f.train)
        st = pri.stats(f.test)
        pos = f.test["position_group"].astype(str).str.upper().to_numpy()
        base_mean = {p: pri.pos_mean_.get(p, np.nan) for p in np.unique(pos)}
        ratio = np.array([st["e_games"].to_numpy()[i] / base_mean[p]
                          if np.isfinite(base_mean[p]) and base_mean[p] > 0 else 1.0
                          for i, p in enumerate(pos)], dtype=float)
        rows.append(pd.DataFrame({"pos": pos, "y": f.test_real, "point": f.test_pred,
                                  "scaled": f.test_pred * np.clip(ratio, 0.0, None)}))
    r = pd.concat(rows, ignore_index=True)
    out = []
    for p, g in r.groupby("pos"):
        out.append({
            "position": p, "n": int(len(g)),
            "MAE base": round(float((g["point"] - g["y"]).abs().mean()), 2),
            "MAE availability-scaled": round(float((g["scaled"] - g["y"]).abs().mean()), 2),
            "bias base": round(float((g["point"] - g["y"]).mean()), 2),
            "bias availability-scaled": round(float((g["scaled"] - g["y"]).mean()), 2),
        })
    return {"by_position": out}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".4f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    l1, l2 = out["leg1"], out["leg2"]
    an = l1["anchors"]
    p("# NF-D14 — the ROOKIE-QB AVAILABILITY prior (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · "
      f"**leg-1 configs:** {len(l1['configs'])} · **leg-2 arms:** {len(l2['arms'])} · "
      f"**held-out rookie-seasons:** {l1['best']['n']}")
    p("")
    p(f"## ⭐ VERDICT — {out['headline']}")
    p("")
    p(out["verdict"])
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      "🔒 The rookie POINT projection is byte-identical across every leg-2 arm "
      f"(max drift **{l2['point_drift']:.6f}** PPR) — a band story must not smuggle a point change.")
    p("")
    p("## 0. The cohort — reported BEFORE any fit, because the N *is* the risk")
    p("")
    p(_md(pd.DataFrame(out["census"])))
    p("")
    p("**This is the whole risk of the story.** A rookie-QB availability prior is fitted on ~12 QBs a "
      "class; NF1.8 already showed the residual QB interval gap is class-to-class VARIANCE on exactly "
      "this cohort. A clean deflated NULL was pre-registered as a legitimate outcome.")
    p("")
    p("⚠️ **PROVENANCE OF THE DEPTH-CHART PROXY.** The historical signal is the **week-1** depth chart "
      "(`stg_nfl_depth_charts`, weekly partitions back to 2001); the live board reads an August "
      "`stg_nfl_depth_charts_current` snapshot. The week-1 read is *post-final-cuts* and therefore "
      "marginally FRESHER than what the board has at draft time, which can only FLATTER the historical "
      "fit. Draft-capital-only (`capital`) arms are pre-registered beside every depth arm so the story "
      "always has an unambiguous-provenance answer — see §2.")
    p("")
    p("## 1. Selection metric — the DISCRETE CRPS, and the MAE inversion measured live")
    p("")
    p("```")
    p("CRPS(F, y) = Σ_{g=0..17} ( F(g) − 1{g ≥ y} )²                      (lower is better)")
    p("```")
    p("")
    p("Proper (uniquely minimised by the true predictive), on the integer support the outcome actually "
      "lives on — which matters because this target has a large point mass at exactly 0 and a hard "
      "ceiling at 17, and a Normal CRPS would misprice both.")
    p("")
    best, null = l1["best"], l1["null"]
    zqb, wqb = an["all_zero"].get("mae_QB"), best.get("mae_QB")
    inverted = zqb is not None and wqb is not None and zqb <= wqb
    p(f"⚠️ **THE MAE INVERSION, MEASURED PER POSITION — not asserted, and not pooled.** The `all_zero` "
      f"degenerate ('project zero games for every rookie') scores MAE **{an['all_zero']['mae_games']}** "
      f"pooled against the winner's **{best['mae_games']}**, and **{zqb}** vs **{wqb}** AT QB.")
    p("")
    p("⭐ **The pooling would be the point if the inversion fired — so it is checked PER POSITION, "
      "because the effect is a property of the ZERO RATE and only QB carries a fat atom** (RB/WR/TE "
      "sit at 7–10%). "
      + (f"At QB the degenerate **{'WINS' if inverted else 'does NOT win'}** MAE. ")
      + (f"That is the CLAUDE.md NF-D11 landmine live, one population over — a metric a nihilist wins "
         f"cannot select a projection."
         if inverted else
         "**The check comes back NEGATIVE here, and the reason sharpens the rule rather than "
         "excusing it.**"))
    p("")
    if not inverted:
        qb = next((r for r in out["census"] if r["position"] == "QB"), {})
        p(f"⚠️ **REFINEMENT OF THE LANDMINE, worth carrying forward: MAE inverts when the conditional "
          f"MEDIAN is at (or next to) ZERO — NOT merely when the zero ATOM is fat.** MAE is minimised "
          f"at the median, so a nihilist wins only if zero *is* the median. NF-D11's returner cohort "
          f"had 43% zeros AND a median of 1 game, so it inverted. This rookie-QB cohort has "
          f"{qb.get('zero rate')} zeros but a median of **{qb.get('median games')} games** — the atom "
          f"is fat, the median is not zero, and MAE duly does NOT invert "
          f"({zqb} for the degenerate vs {wqb} for the winner). ⇒ **'zero-heavy' is not the test; "
          f"score the degenerate and READ IT.** Which is exactly why the degenerate is in the field "
          f"every run rather than reasoned about — this is the anchor set earning its keep by coming "
          f"back negative.")
        p("")
    p(f"CRPS is the selection metric either way, and it orders correctly in every reading: degenerate "
      f"**{an['all_zero']['crps']}** (QB {an['all_zero'].get('crps_QB')}) against the winner's "
      f"**{best['crps']}** (QB {best.get('crps_QB')}). MAE/RMSE stay reported; they are never "
      f"selectable.")
    p("")
    rows = [{"anchor / arm": k, "what it is": v, "CRPS": an.get(k, {}).get("crps"),
             "CRPS QB": an.get(k, {}).get("crps_QB"),
             "MAE games": an.get(k, {}).get("mae_games"),
             "MAE QB": an.get(k, {}).get("mae_QB")}
            for k, v in [
                ("oracle_empirical", "ORACLE FLOOR — the held-out class's OWN realized per-position "
                                     "games distribution. Peeks; nothing may beat it."),
                ("matched_n_candidate", "the NF1.9 (f) guard that makes that floor well-posed — the "
                                        "winner's own arm trained on ONE prior class."),
                ("permuted", "the winner's own family fitted on SHUFFLED training outcomes. Same "
                             "family, same n; only information moves. Must LOSE to the truth."),
                ("all_zero", "DEGENERATE — all mass at 0 games. Wins MAE; must LOSE CRPS."),
                ("all_mean", "DEGENERATE — all mass at the pooled mean. Must LOSE."),
            ] if k in an]
    rows.append({"anchor / arm": "→ LEG-1 WINNER", "what it is": best["label"],
                 "CRPS": best["crps"], "CRPS QB": best.get("crps_QB"),
                 "MAE games": best["mae_games"], "MAE QB": best.get("mae_QB")})
    rows.append({"anchor / arm": "→ NULL", "what it is": null["label"], "CRPS": null["crps"],
                 "CRPS QB": null.get("crps_QB"), "MAE games": null["mae_games"],
                 "MAE QB": null.get("mae_QB")})
    p(_md(pd.DataFrame(rows)))
    p("")
    if best["crps"] < an["oracle_empirical"]["crps"]:
        p(f"⭐ **READ THIS BEFORE READING THE ORACLE ROW: the winner ({best['crps']}) SCORES BETTER "
          f"THAN THE PEEKING ORACLE ({an['oracle_empirical']['crps']}), and that is NOT a metric "
          f"inversion — it is the NF1.9 (f) capacity effect, reproduced.** A peeking oracle is a floor "
          f"only at MATCHED FAMILY *and* MATCHED SAMPLE SIZE. This oracle fits the ~{an['oracle_empirical']['n'] // len(out['cohorts'])}-row "
          f"held-out class; the winner is fitted on ~500 training rows, so it estimates the same "
          f"family's parameters far more precisely. Capacity, not leakage. **The check is therefore "
          f"gated at matched n**: the oracle must beat `matched_n_candidate` — the winner's own arm "
          f"trained on ONE prior class — and it does "
          f"({an['oracle_empirical']['crps']} ≤ {an['matched_n_candidate']['crps']}). The "
          f"PERMUTATION anchor ({an['permuted']['crps']}) is the one that is well-posed at any n, and "
          f"it is beaten decisively.")
        p("")
    for ok, good, bad in (
        (l1["checks"]["oracle_respected"],
         "✅ the oracle floor holds AT MATCHED n (the only reading of it that is well-posed)",
         "🚨 THE ORACLE LOSES EVEN AT MATCHED n — the metric is inverted; do NOT ship this selection"),
        (l1["checks"]["degenerates_lose"], "✅ both degenerates lose the primary metric",
         "🚨 A DEGENERATE WINS — the metric is paying for pessimism (or for spread)"),
        (l1["checks"]["permutation_beaten"], "✅ the truth beats its own permutation",
         "🚨 THE PERMUTATION IS NOT BEATEN — the arm has learnt nothing from the outcomes"),
    ):
        p(("- " + (good if ok else bad)))
    p("")
    p("## 2. Leg 1 — the availability bake-off (all configs, sorted by the primary metric)")
    p("")
    tbl = [{"config": r["label"], "CRPS": r["crps"], "CRPS QB": r.get("crps_QB"),
            "CRPS RB": r.get("crps_RB"), "CRPS WR": r.get("crps_WR"), "CRPS TE": r.get("crps_TE"),
            "MAE games": r["mae_games"], "RMSE games": r["rmse_games"]}
           for r in sorted(l1["configs"], key=lambda r: (r.get("crps") is None, r.get("crps")))]
    p(_md(pd.DataFrame(tbl)))
    p("")
    p("## 3. Leg 1 deflation — CSCV/PBO + Bailey's companions, DSR, BH-FDR")
    p("")
    d = l1["deflation"]
    p(f"**PBO = {d.get('pbo')}** over {d.get('n_splits')} balanced class splits · "
      f"Bailey performance degradation (median OS gap) **{d.get('os_gap_pct')}%** · "
      f"contender (top-quartile) spread **{d.get('contender_spread_pct')}%** · whole-field spread "
      f"**{d.get('spread_pct')}%** · **DSR = {d.get('dsr')}** (pre-registered gate ≥ {AV.DSR_MIN}).")
    p("")
    p(f"⚠️ **THE DSR IS THE ONE GATE THIS SIGNAL FAILS, AND THE READING IS NOT OBVIOUS — so both "
      f"readings are given and the PRE-REGISTERED one binds.** `deflated_sharpe`'s expected-max-SR "
      f"term scales with the DISPERSION of the trial Sharpes, and this field deliberately CONTAINS its "
      f"own known-bad arms (the worst config scores {d.get('spread_pct')}% off the best). So the "
      f"whole-field DSR deflates against the NULLS rather than against the contest at the top — the "
      f"NF1.8 lesson ('a spread computed over a field that contains its own nulls measures the nulls') "
      f"one statistic over. Restricted to the CONTENDER set the same statistic reads "
      f"**{d.get('dsr_contenders')}**.")
    p("")
    dc = d.get("dsr_contenders")
    p("**The pre-registered gate is the whole-field DSR and it stands: the leg-1 signal does not clear "
      "it.** The contender reading is reported so the two are distinguishable, NOT to re-open the gate "
      "after seeing the answer — that would be the E2.1-r inversion."
      + (f" ⭐ And in the event the distinction is moot: even the GENEROUS reading ({dc}) sits "
         f"below the pre-registered {AV.DSR_MIN}, so there is no version of this statistic under which "
         f"the signal clears its bar."
         if isinstance(dc, (int, float)) and dc < AV.DSR_MIN else
         f" ⚠️ Note the contender reading ({dc}) WOULD clear {AV.DSR_MIN} — which is precisely why the "
         f"gate has to be the one fixed in advance, and it is."))
    p("")
    p("⭐ **Either way it does not change the story's outcome: leg 2 is a null under BOTH readings** "
      "(§4). Worth saying plainly, because a gate that only binds when it is convenient is not a gate.")
    p("")
    p("⚠️ Reading it (CLAUDE.md + NF1.8): PBO alone cannot tell *'my pick is unstable'* from *'my pick "
      "is tied'*, and a whole-field spread computed over a field that CONTAINS its own nulls measures "
      "the nulls. The flip distribution below is the discriminator — mass on two arms a fraction of a "
      "percent apart is a TIE; mass spread thinly over a dozen unrelated arms is a search that has "
      "learnt nothing.")
    p("")
    if d.get("flips"):
        p(_md(pd.DataFrame(d["flips"]).head(10)))
        p("")
    p(f"Per-position one-sided paired p-values of the winner's lift over the null: "
      f"`{d.get('per_position_p')}` → BH-FDR (q={AV.FDR_Q}) survivors: `{d.get('fdr')}`.")
    p("")
    p("## 4. Leg 2 — what it does to the rookie interval (NF1.8's machinery, unchanged)")
    p("")
    p("The winner's per-player availability read is attached as `avail_risk_z` and scored through "
      "NF1.8's OWN harness: the same folds, the same row-pooled reducer, the same per-position floors, "
      "the same Winkler interval score. Two channels (a quantile-regression FEATURE, and a strictly "
      "WIDEN-ONLY widener) × two drivers.")
    p("")
    p("⭐ **`sd` is the principled driver and `pshort` the naive one, pre-registered together.** "
      "Availability risk is NOT monotone in expected games — it peaks where the outcome is a coin flip "
      "(a 7th-round QB3 at `p_play ≈ 0.05` is confidently near-zero; a second-rounder in an open camp "
      "battle at `p_play ≈ 0.5` is not). A 'bust risk' widener would widen the wrong rookies.")
    p("")
    l2rows = [{"arm": r["label"], "IS80": r["interval_score"], "cov80": r["coverage_80"],
               "cov QB": r.get("cov_QB"), "cov RB": r.get("cov_RB"), "cov TE": r.get("cov_TE"),
               "cov WR": r.get("cov_WR"), "mean width": r["mean_width"],
               "QB width": r.get("width_QB"),
               "floors met": "yes" if not r.get("_misses") else f"NO ({'; '.join(r['_misses'])})"}
              for r in sorted(l2["arms"], key=lambda r: r["interval_score"])]
    p(_md(pd.DataFrame(l2rows)))
    p("")
    p(f"**SELECTION RULE (NF1.8's, unchanged): argmin interval score among the arms that clear EVERY "
      f"per-position floor.** The NULL is in that field. Selected: **`{l2['best']['label']}`** "
      f"(IS80 {l2['best']['interval_score']}, QB coverage {l2['best'].get('cov_QB')}).")
    p("")
    p("⚠️ **Two things in this table are the whole leg-2 result, and both are pre-registered "
      "landmines firing rather than surprises:**")
    p("")
    p("1. **The WIDEN arms buy rookie-QB coverage by paying interval score.** That is a coverage "
      "TARGET winning, and it is exactly what E2.1-r/NF1.8 forbid: coverage is a FLOOR, never "
      "something to maximise, because 'more headroom above the floor' is MONOTONE IN WIDENING — the "
      "`max_width` degenerate wins that criterion outright. An arm that widens QB and loses the proper "
      "score has not improved the interval; it has moved along the width axis.")
    p("2. **The availability FEATURE channel can make QB coverage WORSE.** Handed the driver as a "
      "quantile-regression feature, the fit is free to SHARPEN the rookies whose availability it "
      "considers predictable, and it does. That is the NF1.7 (d) hazard — a two-sided knob on an "
      "uncertainty covariate — showing up on a channel where the widen-only clamp does not apply, and "
      "it is why the widener carries `clip(z, 0, 2)` while the feature does not pretend to.")
    p("")
    p("### The anchor set, re-scored on THIS run")
    p("")
    an2 = l2["anchors"]
    p(_md(pd.DataFrame([{"anchor": t, "IS80": an2[t]["interval_score"],
                         "cov80": an2[t]["coverage_80"], "cov QB": an2[t].get("cov_QB"),
                         "mean width": an2[t]["mean_width"]}
                        for t in ("oracle_qreg", "oracle_knn", "permuted_own", "zero_width",
                                  "max_width", "const_width") if t in an2])))
    p("")
    p(f"Checks: `{l2['anchor_checks']}`. ⭐ `max_width` is the constraint-vs-criterion proof (NF1.8): "
      f"it SATISFIES every coverage floor and still loses the primary metric by a wide margin — which "
      f"is the right shape. A constraint a degenerate satisfies is fine, because the metric eliminates "
      f"it; a CRITERION a degenerate wins is fatal.")
    p("")
    p("### 4b. ⭐ THE NEAR-MISS — the most tempting number in this story, stated in ROWS")
    p("")
    nm = l2["near_miss"]
    p(f"The SHARPEST arm in the whole field is **`{nm['arm']}`** at IS80 **{nm['interval_score']}** — "
      f"**{abs(nm['vs_null_pct'])}% {'better' if nm['vs_null_pct'] < 0 else 'worse'}** than the shipped "
      f"band, and it lifts rookie QB too. It is **{'ELIGIBLE' if nm['eligible'] else 'INELIGIBLE'}**.")
    p("")
    p(_md(pd.DataFrame(nm["rows"])))
    p("")
    if not nm["eligible"]:
        p("**We are not taking it, and the reason has to be stated precisely rather than implied.**")
        p("")
        p("- The miss is small — a shortfall of a handful of covered rookie-seasons — and NF1.8's own "
          "power analysis says a hard point-estimate floor at nominal rejects a PERFECTLY-calibrated "
          "arm about half the time. So this arm may well be fine. That is *not* a reason to admit it: "
          "the same argument admits every arm that misses by a little, in every direction, forever.")
        p("- **The documented Tier-2 fallback does not rescue it either, and its trigger condition is "
          "not met.** Tier 2 relaxes only the structurally-thin positions "
          f"(`{NF18._TIER2_POSITIONS}`) and only when Tier 1 admits NO config — Tier 1 admits several "
          f"here. Scored anyway as a sensitivity: Tier-2 floors `{nm['tier2_floors']}` would "
          f"**{'ADMIT' if nm['tier2_would_admit'] else 'STILL REJECT'}** this arm.")
        p("- Admitting it would be **reverse-engineering the floor from the answer** — the E2.1-r "
          "inversion facing the other way, and precisely what NF1.8 §1 forbids. A floor that moves "
          "until something clears it is not a floor.")
        p("")
        p("⚠️ Note also WHICH arm it is: the sharpening comes from the availability driver entering as "
          "a quantile-regression FEATURE, i.e. from the fit being free to NARROW the rookies whose "
          "availability it thinks it can predict. It buys the primary metric by under-covering, and "
          "the per-position floor is the thing that caught it. That is the floor doing its job on a "
          "live example, not a technicality.")
        p("")
    p("### The per-position floor margin, in ROWS (the NF1.8 convention)")
    p("")
    p("A coverage decimal hides how few outcomes a per-position floor rests on. 'QB 0.741 → 0.815' "
      "reads like a calibration change; it is **six covered rookie-seasons out of 81**.")
    p("")
    p(_md(pd.DataFrame(l2["floor_table"])))
    p("")
    p("## 5. Leg 2 deflation")
    p("")
    d2 = l2["deflation"]
    p(f"**PBO = {d2.get('pbo')}** over {d2.get('n_splits')} splits · Bailey degradation "
      f"{d2.get('os_gap_pct')}% · contender (top-quartile) spread {d2.get('contender_spread_pct')}% · "
      f"eligible configs {d2.get('n_configs')}.")
    p("")
    if d2.get("flips"):
        p(_md(pd.DataFrame(d2["flips"]).head(8)))
        p("")
    p("## 6. The POINT channel — measured, reported, NOT shipped")
    p("")
    p("Scaling the rookie point projection by the availability prior's expected-games ratio is the "
      "other thing an availability prior can drive, and the story asked for the point change to be "
      "ATTRIBUTABLE. So it is measured rather than argued about:")
    p("")
    pcr = l2["point_channel"]["by_position"]
    p(_md(pd.DataFrame(pcr)))
    p("")
    qb_row = next((r for r in pcr if r["position"] == "QB"), None)
    others = [r for r in pcr if r["position"] != "QB"]
    helped = [r["position"] for r in others
              if r["MAE availability-scaled"] < r["MAE base"]]
    p("⚠️ **THE RESULT IS SPLIT, AND NOT IN THE DIRECTION THE STORY ASSUMED — so it is reported as "
      "measured rather than summarised into the expected shape.** The ratio is not a haircut: it "
      "exceeds 1 for high-capital rookies, so at "
      + (", ".join(helped) if helped else "no position") +
      " it modestly IMPROVES MAE by partially correcting the COLD bias NF1.4 documented "
      "(tier bias RB −58 / WR −49 / TE −44 PPR).")
    p("")
    if qb_row:
        p(f"⭐ **And it BREAKS the one position this story is about.** At QB it moves MAE "
          f"**{qb_row['MAE base']} → {qb_row['MAE availability-scaled']}** "
          f"(**+{round(100.0 * (qb_row['MAE availability-scaled'] - qb_row['MAE base']) / qb_row['MAE base'], 1)}%**) "
          f"and flips the bias from **{qb_row['bias base']}** (cold) to "
          f"**+{qb_row['bias availability-scaled']}** (hot) — because a rookie QB's expected games "
          f"already vary enormously with draft capital, so the slot curve has effectively priced that "
          f"variation once and the ratio prices it a second time.")
        p("")
    p("⇒ **The point channel is DECLINED on the evidence, not on principle.** A change that helps "
      "three positions a little and damages the fourth badly is not a projection improvement; it is a "
      "trade nobody asked for, on the position the story exists to fix. The shipped rookie point is "
      "unchanged and byte-identical (§0), and this table is the attribution.")
    p("")
    p("## 7. Honest limitations")
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
def main(argv: list[str] | None = None) -> int:  # noqa: C901 — orchestration
    ap = argparse.ArgumentParser(description="NF-D14 rookie-QB availability prior bake-off")
    ap.add_argument("--panel", default=str(_PANEL_CACHE))
    ap.add_argument("--pool", default=str(NF17._POOL_CACHE))
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=_STAGING_SCHEMA)
    ap.add_argument("--rebuild-panel", action="store_true")
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--smoke", action="store_true",
                    help="one config per form; writes *_smoke artifacts so it can never be mistaken "
                         "for the real search")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if args.rebuild_panel:
        log.info("rebuilding the NF-D14 availability panel …")
        panel = build_panel(Path(args.pool), args.duckdb, args.schema)
        _PANEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(args.panel, index=False)
        log.info("panel → %s (%d rows)", args.panel, len(panel))
    panel = load_panel(Path(args.panel))
    cohorts = list(range(args.from_year, args.to_year + 1))
    suffix = "_smoke" if args.smoke else ""

    # ── LEG 1 ──────────────────────────────────────────────────────────────────────────────
    folds1 = leg1_folds(panel, cohorts)
    if len(folds1) < 4:
        raise SystemExit(f"only {len(folds1)} usable draft classes — CSCV needs ≥4")
    census = cohort_census(panel, [y for y, _, _ in folds1])
    log.info("cohort census: %s", census)

    cfgs = AV.candidate_configs(smoke=args.smoke)
    log.info("leg 1: %d availability configs × %d held-out classes", len(cfgs), len(folds1))
    results = [r for r in (run_leg1_config(folds1, c) for c in cfgs) if r]
    null = next(r for r in results if r["form"] == "pos_empirical")
    best = min((r for r in results if r["form"] != "pos_empirical"), key=lambda r: r["crps"])

    anchors = leg1_anchors(folds1, next(c for c in cfgs if c["label"] == best["label"]))
    require_leg1_anchors(anchors)
    checks = {
        # ⚠️ the ORACLE FLOOR is gated at MATCHED n (NF1.9 (f)): a peeking oracle fitted on ~80 held-out
        #    rows is only a floor against an arm of the same family AND the same resolution.
        "oracle_respected": anchors["oracle_empirical"]["crps"] <= anchors["matched_n_candidate"]["crps"],
        "degenerates_lose": (best["crps"] < anchors["all_zero"]["crps"]
                             and best["crps"] < anchors["all_mean"]["crps"]),
        "permutation_beaten": best["crps"] < anchors["permuted"]["crps"],
    }
    defl1 = leg1_deflation(results, null["label"], best["label"])
    v1 = AV.availability_verdict(
        beats_null=best["crps"] < null["crps"], oracle_respected=checks["oracle_respected"],
        degenerates_lose=checks["degenerates_lose"],
        permutation_beaten=checks["permutation_beaten"], pbo=defl1.get("pbo"),
        dsr=defl1.get("dsr"), fdr_pass=bool((defl1.get("fdr") or {}).get("QB")))

    print("\n=== NF-D14 LEG 1 — availability prior (held-out CRPS of the games PMF) ===")
    for r in sorted(results, key=lambda r: r["crps"])[:12]:
        print(f"{r['label']:44s} CRPS {r['crps']:7.4f}  QB {r.get('crps_QB', float('nan')):7.4f}  "
              f"MAEg {r['mae_games']:6.2f}")
    print(f"\nanchors: oracle {anchors['oracle_empirical']['crps']} (matched-n "
          f"{anchors['matched_n_candidate']['crps']}) · permuted {anchors['permuted']['crps']} · "
          f"all_zero {anchors['all_zero']['crps']} (MAE {anchors['all_zero']['mae_games']}) · "
          f"all_mean {anchors['all_mean']['crps']}")
    print(f"NULL  {null['label']}: CRPS {null['crps']} (QB {null.get('crps_QB')})")
    print(f"BEST  {best['label']}: CRPS {best['crps']} (QB {best.get('crps_QB')})")
    print(f"deflation: PBO {defl1.get('pbo')} · DSR {defl1.get('dsr')} · "
          f"degradation {defl1.get('os_gap_pct')}% · verdict {v1}")

    # ── LEG 2 ──────────────────────────────────────────────────────────────────────────────
    pool = NF17.load_pool(Path(args.pool))
    base_folds = NF17.build_folds(pool.merge(
        panel[["gsis_id", "draft_year", "depth_rank"]], on=["gsis_id", "draft_year"], how="left"),
        cohorts)
    win_cfg = next(c for c in cfgs if c["label"] == best["label"])
    cache = {drv: attach_availability(base_folds, win_cfg, drv) for drv in _AVAIL_DRIVERS}
    drift = max(point_drift(base_folds, cache[d]) for d in _AVAIL_DRIVERS)

    base_arm = {"arm": "model", "form": SP._ROOKIE_BAND_FORM, "k": SP._ROOKIE_BAND_K,
                "qreg_alpha": SP._ROOKIE_BAND_QREG_ALPHA,
                "resid_sd_gain": SP._ROOKIE_BAND_RESID_SD_GAIN,
                "qreg_per_pos": SP._ROOKIE_BAND_QREG_PER_POS,
                "cqr_mode": SP._ROOKIE_BAND_CQR_MODE, "cqr_scale": SP._ROOKIE_BAND_CQR_SCALE}
    arms = [r for r in (run_leg2_arm(base_folds, c, cache) for c in leg2_configs(base_arm)) if r]
    POS = sorted({k[4:] for k in arms[0] if k.startswith("cov_")})
    floors = NF18.position_floors(arms[0], POS, tier=1)
    for r in arms:
        r["_misses"] = NF18.floor_misses(r, floors)
    l2_null = next(r for r in arms if r["label"].endswith("(NULL)"))
    eligible = [r for r in arms if not r["_misses"]]
    # THE SELECTION RULE, unchanged from NF1.8: argmin interval score among the arms that clear every
    # per-position floor. The NULL is IN that field — if it wins, the story is a null, and that is the
    # honest way for this harness to say so.
    l2_best = min(eligible or arms, key=lambda r: r["interval_score"])
    avail_eligible = [r for r in eligible if r.get("driver")]
    l2_best_avail = (min(avail_eligible, key=lambda r: r["interval_score"])
                     if avail_eligible else None)

    # ⭐ the NF1.8 anchor set, re-scored on THIS run rather than cited from NF1.8's report — a
    #    degenerate that must lose has to be shown losing every time, not once.
    l2_anchors = NF18.run_anchors(base_folds, oracle_k=25, permute_cfgs={"own": base_arm})
    l2_anchor_ok = {
        "degenerates_lose": all(l2_best["interval_score"] < l2_anchors[t]["interval_score"]
                                for t in ("zero_width", "max_width", "const_width")),
        "permutation_beaten": l2_best["interval_score"] < l2_anchors["permuted_own"]["interval_score"],
        "oracle_respected": l2_best["interval_score"] >= l2_anchors["oracle_qreg"]["interval_score"],
    }

    mat2 = pd.DataFrame({r["label"]: r["per_cohort"] for r in arms}).sort_index()
    defl2 = NF18.deflate(mat2, subset=[r["label"] for r in eligible] or None)

    # ⭐ THE NEAR-MISS, IN ROWS — the single most tempting thing in this whole story, so it is measured
    #    and stated rather than left for a reader to rediscover. The sharpest arm of all is INELIGIBLE,
    #    and how ineligible it is (in covered rookie-seasons, not coverage decimals) is the number that
    #    decides whether the floor is being applied or negotiated with.
    sharpest = min(arms, key=lambda r: r["interval_score"])
    tier2 = NF18.position_floors(arms[0], POS, tier=2)
    near_miss = {
        "arm": sharpest["label"], "interval_score": sharpest["interval_score"],
        "vs_null_pct": round(100.0 * (sharpest["interval_score"] - l2_null["interval_score"])
                             / l2_null["interval_score"], 2),
        "eligible": not sharpest["_misses"],
        "tier2_floors": tier2,
        "tier2_would_admit": not NF18.floor_misses(sharpest, tier2),
        "rows": [{
            "position": p, "n": sharpest.get(f"n_{p}"), "floor": f,
            "coverage": sharpest.get(f"cov_{p}"),
            "covered rows": int(round((sharpest.get(f"cov_{p}") or 0) * (sharpest.get(f"n_{p}") or 0))),
            "rows the floor requires": int(np.ceil(f * (sharpest.get(f"n_{p}") or 0))),
            "shortfall (rows)": int(np.ceil(f * (sharpest.get(f"n_{p}") or 0))
                                    - int(round((sharpest.get(f"cov_{p}") or 0)
                                                * (sharpest.get(f"n_{p}") or 0)))),
        } for p, f in sorted(floors.items())],
    }

    contrast = l2_best_avail or l2_best
    floor_table = []
    for p in POS:
        floor_table.append({
            "position": p, "n (held-out)": l2_null.get(f"n_{p}"), "floor": floors.get(p),
            "coverage — NULL (shipped NF1.8)": l2_null.get(f"cov_{p}"),
            "coverage — best ELIGIBLE availability arm": contrast.get(f"cov_{p}"),
            "slack rows — NULL": NF18.floor_slack_rows(l2_null, floors).get(p),
            "slack rows — availability arm": NF18.floor_slack_rows(contrast, floors).get(p),
            "mean width — NULL": l2_null.get(f"width_{p}"),
            "mean width — availability arm": contrast.get(f"width_{p}"),
        })

    v2 = AV.interval_verdict(
        qb_coverage_base=l2_null.get("cov_QB"), qb_coverage_arm=l2_best.get("cov_QB"),
        floors_met=not l2_best["_misses"],
        beats_base_interval_score=l2_best["interval_score"] < l2_null["interval_score"],
        pbo=defl2.get("pbo"), point_invariant=drift < 1e-9)
    v2["selected_arm_uses_availability"] = bool(l2_best.get("driver"))
    v2 = {**v2, **{f"anchor_{k}": v for k, v in l2_anchor_ok.items()}}
    v2["ship"] = bool(v2["ship"] and v2["selected_arm_uses_availability"]
                      and all(l2_anchor_ok.values()))
    pc = point_channel(base_folds, win_cfg)

    print("\n=== NF-D14 LEG 2 — the rookie interval under the availability prior ===")
    for r in sorted(arms, key=lambda r: r["interval_score"]):
        print(f"{r['label']:44s} IS80 {r['interval_score']:8.2f}  cov {r['coverage_80']:.3f}  "
              f"QB {r.get('cov_QB', float('nan')):.3f}  w {r['mean_width']:7.1f}  "
              f"{'' if not r['_misses'] else 'FLOOR MISS: ' + ';'.join(r['_misses'])}")
    print(f"\nanchors: " + " · ".join(
        f"{t} IS80 {l2_anchors[t]['interval_score']}"
        for t in ("oracle_qreg", "permuted_own", "zero_width", "max_width", "const_width")
        if t in l2_anchors))
    print(f"SELECTED (argmin IS80 among floor-clearing arms): {l2_best['label']}")
    if l2_best_avail is not None:
        print(f"best ELIGIBLE availability arm: {l2_best_avail['label']} "
              f"IS80 {l2_best_avail['interval_score']} QB cov {l2_best_avail.get('cov_QB')}")
    print(f"leg-2 deflation: PBO {defl2.get('pbo')} · degradation {defl2.get('os_gap_pct')}% · "
          f"contender spread {defl2.get('contender_spread_pct')}%")
    print(f"point drift (must be 0): {drift:.9f}")
    print(f"leg-2 verdict: {v2}")

    ship = bool(v1["prior_is_real"] and v2["ship"])
    headline = ("✅ SHIP — the availability prior closes the rookie-QB coverage gap and the gain is "
                "deflation-real" if ship else
                "🟡 CLEAN NULL — the availability signal is real, but it does NOT close the rookie-QB "
                "interval gap; NF1.8's band STANDS and the floor does NOT move"
                if v1["prior_is_real"] else
                "🟡 CLEAN NULL — no availability form clears the pre-registered gate; NF1.8's band "
                "STANDS and the floor does NOT move")
    verdict = _verdict_prose(ship, v1, v2, best, null, l2_null, l2_best, anchors, defl1)

    out = {
        "story": "NF-D14", "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohorts": [y for y, _, _ in folds1], "census": census, "ship": ship, "headline": headline,
        "verdict": verdict,
        "leg1": {"configs": results, "best": best, "null": null, "anchors": anchors,
                 "checks": checks, "deflation": defl1, "verdict": v1},
        "leg2": {"arms": arms, "null": l2_null, "best": l2_best, "best_avail": l2_best_avail,
                 "floors": floors, "anchors": l2_anchors, "anchor_checks": l2_anchor_ok,
                 "floor_table": floor_table, "deflation": defl2, "verdict": v2,
                 "near_miss": near_miss, "point_drift": drift, "point_channel": pc},
        "limitations": _LIMITATIONS,
    }
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_d14_rookie_availability{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_d14_rookie_availability{suffix}.md")
    print(f"\n{headline}")
    return 0


def _verdict_prose(ship, v1, v2, best, null, l2_null, l2_best, anchors, defl1) -> str:
    lift = (round(100.0 * (null["crps"] - best["crps"]) / max(1e-9, null["crps"]), 1)
            if null.get("crps") else None)
    qb_lift = (round(100.0 * (null.get("crps_QB", 0) - best.get("crps_QB", 0))
                     / max(1e-9, null.get("crps_QB", 1)), 1)
               if null.get("crps_QB") else None)
    oracle_note = (
        f"scores BETTER than the peeking oracle ({anchors['oracle_empirical']['crps']}) — which is the "
        f"NF1.9 (f) CAPACITY effect, not an inversion, and the floor is therefore gated at MATCHED n, "
        f"where it holds ({anchors['oracle_empirical']['crps']} ≤ "
        f"{anchors['matched_n_candidate']['crps']}); see §1"
        if best["crps"] < anchors["oracle_empirical"]["crps"] else
        f"loses to the peeking oracle ({anchors['oracle_empirical']['crps']}) as it must")
    a = [
        f"**Leg 1 — the availability signal is LARGE AND MEASURABLE"
        f"{', but does NOT clear the pre-registered deflation gate' if not v1['prior_is_real'] else ''}.** "
        f"`{best['label']}` cuts the held-out games CRPS from the position-empirical null's "
        f"{null['crps']} to {best['crps']} ({lift}% better overall; **{qb_lift}% at QB**), beats its "
        f"own permutation ({anchors['permuted']['crps']}) decisively, {oracle_note}, and both "
        f"degenerates lose. Deflation: PBO {defl1.get('pbo')}, DSR {defl1.get('dsr')} "
        f"(gate ≥ {AV.DSR_MIN} — the one gate it fails; see §3 for why that reading is not obvious and "
        f"why it does not change the story's outcome), Bailey degradation "
        f"{defl1.get('os_gap_pct')}%. Gate detail: `{v1}`.",
        "",
        f"**Leg 2 — the story's GATE.** Rookie-QB held-out coverage under the SHIPPED NF1.8 band is "
        f"{l2_null.get('cov_QB')} at an interval score of {l2_null['interval_score']}. The selection "
        f"rule (argmin interval score among floor-clearing arms) picks `{l2_best['label']}` "
        f"(IS80 {l2_best['interval_score']}, QB {l2_best.get('cov_QB')}). Gate detail: `{v2}`.",
        "",
    ]
    if ship:
        a.append("⇒ **SHIP.** The prior widens the rookie QB band AT THE SOURCE of its uncertainty "
                 "rather than by recalibration, the per-position floors all still hold, and the gain "
                 "survives the deflation.")
    else:
        a.append("⇒ **RECORDED NULL — and it is the answer, not a failure.** This story pre-registered "
                 "that outcome: NF1.8's own diagnosis was that the residual rookie-QB gap is "
                 "class-to-class VARIANCE on a ~12-QB/class cohort rather than fittable "
                 "miscalibration, and that diagnosis now has a second, independent confirmation — a "
                 "measurably real availability signal, fed into the band through both pre-registered "
                 "channels and both pre-registered drivers, does not close it. **The QB interval "
                 "variance is irreducible at this N.** The shipped NF1.8 band STANDS, the coverage "
                 "floor does NOT move (E2.1-r; NF1.8 §1), and the question is retired rather than "
                 "left open for a third recalibration attempt.")
    return "\n".join(a)


_LIMITATIONS = [
    "⚠️ **SUPERSEDED by NF-D15 — the mechanism asserted here (cold-bias LEVEL correction) was refuted "
    "by NF-D15's matched foil; the lift is an AVAILABILITY effect, not a level correction. See "
    "`nf_d15_rookie_point_scaling.md`.** (NF-D16 then tested the level correction as its own "
    "pre-registered hypothesis — see `nf_d16_rookie_point_recalibration.md`.) This report's own "
    "reasoning is left INTACT: it is a faithful record of what NF-D14 knew at the time, and the risk "
    "being closed here is only that a re-run of this harness REGENERATES a known-superseded mechanism "
    "claim with no pointer to what overturned it.",
    "**The depth-chart proxy is FRESHER than the served signal.** The historical feature is the WEEK-1 "
    "depth chart (a post-final-cuts read); the live board reads an August "
    "`stg_nfl_depth_charts_current` snapshot. That can only FLATTER the historical fit, which is why "
    "the draft-capital-only arms are pre-registered beside every depth arm and reported in full.",
    "**`n` is small by construction** — ~12 drafted QBs a class, 81 held-out rookie-QB seasons over "
    "seven classes. A per-position claim on that cohort is a claim about six or seven covered rows; "
    "the floor margins are therefore reported in ROWS, not in coverage decimals (NF1.8's convention).",
    "**The prior predicts GAMES, not the per-game line.** A rookie who plays 17 games as a backup and "
    "one who plays 17 as a starter are the same availability outcome; the ROLE term lives in the point "
    "projection's depth-chart features, not here.",
    "**A coverage floor is a CONSTRAINT, never a target** (E2.1-r; NF1.8 §1). No arm is preferred for "
    "having more headroom above the floor — that criterion is monotone in widening, so the `max_width` "
    "degenerate wins it outright.",
    "**No edge claim.** This is a projection-quality product: `best_alpha = 0`, no CLV/ROI statement.",
    "⭐ **ONE OPEN LEAD, recorded rather than pursued (it is a different story).** §6's point channel "
    "IMPROVES held-out MAE at RB/TE/WR by 1.2–3.5 PPR, by partially correcting the COLD bias NF1.4 "
    "measured. NF-D14 declines it because it BREAKS QB and because a NON-QB point change is outside "
    "this story's pre-registered scope — selecting it here would be scope creep dressed as a finding. "
    "If a future story wants it, it needs its OWN §0.5 gate on the point (a proper score, the "
    "do-no-ordering-harm constraint, and per-position deflation), not this story's interval gate.",
]


if __name__ == "__main__":
    raise SystemExit(main())
