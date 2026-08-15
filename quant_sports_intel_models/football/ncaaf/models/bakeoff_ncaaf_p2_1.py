"""bakeoff_ncaaf_p2_1.py — NCAAF-P2.1: the pre-registered STRUCTURAL hypothesis battery.

WHAT THIS IS
------------
P1.4 returned `REFERENCE_STANDS` — a trustworthy null WITHIN the conventional search
(learner × feature-subset × parametric form). It never tried richer model STRUCTURE. This harness
tests the 16 structural hypotheses pre-registered in
`ablation_results/ncaaf_p2_1_preregistration.md`, under the full §0.5 deflation, against the
SHIPPED P1.4 reference.

⭐ READ THE PRE-REGISTRATION FIRST. It is the contract: the arms, the metric, the constraint, the
anchors and the deflation convention were all fixed BEFORE the first score. Nothing here may be
changed to chase a result (E2.1-r).

THE DESIGN IN ONE PARAGRAPH
---------------------------
Every arm is `reference ∪ one block`, everything else byte-identical (ridge α=10, form
`strength_posterior`, the same 8 season-forward date-purged folds, the same seed, the same draw
count) — so the read is the PAIRED delta versus the reference, never a leaderboard rank (NF-D10: a
rank cannot tell "my structure is inert" from "my structure is tied"). The selection metric is CRPS
(proper; grades point AND spread — §0.5, ⛔ never MAE). Calibration is a hard CONSTRAINT, never a
target (NF1.8). Five anchors run every time: an oracle floor nothing may beat, a permutation that
must lose, two degenerates that must lose the metric from opposite directions, and a matched
level-only foil that decides whether H1b's per-TEAM content earned its win or a global level did.

USAGE (operator — stages 0 and 1 are the >2-minute jobs)
--------------------------------------------------------
    # 0) ONE pull → ONE parquet (matrix + plays rollup + derived blocks + CLV closes)
    AWS_DEFAULT_REGION=us-east-2 uv run python -m \\
        quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --assemble

    # 1) score the full battery (reference + 16 arms + 5 anchors) on all 8 folds
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 \\
        --stage battery

    # 2) deflate + classify + render the dossier
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 \\
        --stage decide
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils import cv_power  # noqa: E402
from betting_ml.utils.cv import PurgedWalkForwardSplit  # noqa: E402
from betting_ml.utils.market_blind import assert_market_blind  # noqa: E402
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv  # noqa: E402
from betting_ml.utils.promotion_gate import crps_ensemble  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (  # noqa: E402
    SCORED_DISTS,
    JointDispersion,
    derive_markets,
    downstream_score,
    draw_joint,
    fit_gaussian_dispersion,
    fit_strength_posterior_scale,
    score_calibration,
    strength_posterior_sigma,
)
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import (  # noqa: E402
    BLOCKS,
    DECLARED_FIELD_SIZE,
    block_columns,
    eb_team_hfa_infold,
)

_STORY = "NCAAF-P2.1"
_MODELS_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _MODELS_DIR.parent / "ablation_results"
_CACHE_DIR = _PROJECT_ROOT / "betting_ml" / "data" / "cache"
_CACHE_PATH = _CACHE_DIR / "ncaaf_p2_1_battery.parquet"
_META_PATH = _CACHE_DIR / "ncaaf_p2_1_battery.meta.json"
_SCORES_JSON = _RESULTS_DIR / "ncaaf_p2_1_battery_scores.json"
_DECISION_JSON = _RESULTS_DIR / "ncaaf_p2_1_structural_battery.json"
_DECISION_MD = _RESULTS_DIR / "ncaaf_p2_1_structural_battery.md"

_MARGIN, _TOTAL, _YEAR, _DATE = "label_home_margin", "label_total_points", "season", "game_date"
_STRENGTH_PREFIXES = ("home_strength", "away_strength", "strength_margin_diff")
_CLOSE_COLS = ("close_home_spread", "close_total", "close_home_ml_american", "close_home_ml_prob",
               "close_snapshot_ts", "has_close")

# ── the pre-registered constants (⛔ changing one after the first score is laundering) ──────────
_SEED = 42
_RIDGE_ALPHA = 10.0            # the shipped P1.4 reference
_FORM = "strength_posterior"   # the shipped P1.4 form
_N_DRAWS = 4_000
_N_SLICES = 4                  # PBO buckets per fold
_CALIB_TARGET, _CALIB_TOL = 0.80, 0.02
_PBO_GATE, _DSR_GATE, _FDR_ALPHA = 0.2, 0.95, 0.05
_TIE_BAND = 1e-3               # |ΔCRPS| below this ⇒ TIE, refused as a win (nested-form guard)
_BREAKEVEN = 0.5238            # -110 vig

#: anchors are DIAGNOSTIC/DEGENERATE — in `n_trials` for multiplicity, out of `V` (DSR-CONV +
#: MH2.1(a)). Declared FORWARD in the pre-registration; ⛔ not adoptable after a failed gate.
ANCHORS: tuple[str, ...] = ("oracle_peek", "permute", "zero_width", "max_width", "hfa_global")

_T0 = time.time()


def _log(msg: str, indent: int = 0) -> None:
    print(f"[{datetime.now():%H:%M:%S} +{time.time() - _T0:6.0f}s] {'  ' * indent}{msg}",
          file=sys.stderr, flush=True)


# ===========================================================================
# Stage 0 — assemble ONE parquet (§0.5 cost hygiene: every arm × fold reads this)
# ===========================================================================

def _long_team_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team) with that team's own strength, its opponent, and its realised
    margin — the substrate for the schedule-derived blocks (H4 lookahead, H8 recency)."""
    out = []
    for side, opp in (("home", "away"), ("away", "home")):
        sign = 1.0 if side == "home" else -1.0
        out.append(pd.DataFrame({
            "season": df["season"].to_numpy(),
            "game_id": df["game_id"].to_numpy(),
            "game_date": df[_DATE].to_numpy(),
            "team": df[f"{side}_team"].to_numpy(),
            "opp": df[f"{opp}_team"].to_numpy(),
            "own_strength": pd.to_numeric(df[f"{side}_strength_margin"], errors="coerce").to_numpy(),
            "opp_strength_now": pd.to_numeric(df[f"{opp}_strength_margin"], errors="coerce").to_numpy(),
            "own_margin": sign * pd.to_numeric(df[_MARGIN], errors="coerce").to_numpy(),
        }))
    return pd.concat(out, ignore_index=True).sort_values(["season", "team", "game_date", "game_id"])


def _schedule_blocks(df: pd.DataFrame) -> pd.DataFrame:
    """H4 (lookahead/letdown) + H8 (recency) — both strictly leakage-safe.

    ⭐ The leakage subtlety in H4: WHO you play next week is a pre-game FACT (the schedule), but
    that opponent's STRENGTH must be taken as-of TODAY, never from their future game row. So the
    next opponent's rating is resolved with a backward `merge_asof` onto their most recent game on
    or before the current date. Using the rating attached to the future game would import a future
    measurement — a silent leak that would flatter H4.
    """
    lg = _long_team_frame(df)
    g = lg.groupby(["season", "team"], sort=False)

    lg["next_opp"] = g["opp"].shift(-1)
    lg["prev_opp"] = g["opp"].shift(1)
    lg["prev_opp_strength_asof"] = g["opp_strength_now"].shift(1)

    # each team's own strength AS OF each date (the as-of source for a future opponent)
    asof_src = (lg[["season", "team", "game_date", "own_strength"]]
                .dropna(subset=["game_date"]).sort_values("game_date"))
    left = lg[["season", "team", "game_date", "next_opp"]].copy().sort_values("game_date")
    left = left.dropna(subset=["game_date"])
    merged = pd.merge_asof(
        left, asof_src.rename(columns={"team": "next_opp", "own_strength": "next_opp_strength"}),
        on="game_date", by=["season", "next_opp"], direction="backward", allow_exact_matches=True)
    lg = lg.merge(merged[["season", "team", "game_date", "next_opp_strength"]],
                  on=["season", "team", "game_date"], how="left")

    # H8 recency: trailing-3 realised margin minus season-to-date, both over STRICTLY PRIOR games
    g = lg.groupby(["season", "team"], sort=False)
    prior = g["own_margin"].shift(1)
    roll3 = prior.groupby([lg["season"], lg["team"]], sort=False).rolling(3, min_periods=2).mean() \
                 .reset_index(level=[0, 1], drop=True)
    expand = prior.groupby([lg["season"], lg["team"]], sort=False).expanding(min_periods=3).mean() \
                  .reset_index(level=[0, 1], drop=True)
    lg["recent_form"] = roll3 - expand

    keep = ["game_id", "team", "next_opp_strength", "prev_opp_strength_asof", "recent_form",
            "opp_strength_now"]
    lg = lg[keep].drop_duplicates(subset=["game_id", "team"], keep="first")
    out = df
    for side in ("home", "away"):
        r = lg.rename(columns={"team": f"{side}_team",
                               "next_opp_strength": f"{side}_next_opp_strength",
                               "prev_opp_strength_asof": f"{side}_prev_opp_strength",
                               "recent_form": f"{side}_recent_form",
                               "opp_strength_now": f"{side}_cur_opp_strength"})
        out = out.merge(r, on=["game_id", f"{side}_team"], how="left")
    for side in ("home", "away"):
        cur = pd.to_numeric(out[f"{side}_cur_opp_strength"], errors="coerce")
        out[f"{side}_lookahead_gap"] = pd.to_numeric(out[f"{side}_next_opp_strength"], errors="coerce") - cur
        out[f"{side}_letdown_gap"] = pd.to_numeric(out[f"{side}_prev_opp_strength"], errors="coerce") - cur
    out["lookahead_gap_diff"] = out["home_lookahead_gap"] - out["away_lookahead_gap"]
    out["letdown_gap_diff"] = out["home_letdown_gap"] - out["away_letdown_gap"]
    out["recent_form_diff"] = (pd.to_numeric(out["home_recent_form"], errors="coerce")
                               - pd.to_numeric(out["away_recent_form"], errors="coerce"))
    return out.drop(columns=[c for c in out.columns if c.endswith("_cur_opp_strength")])


def _rivalry_blocks(df: pd.DataFrame, lookback: int = 6, min_meetings: int = 4) -> pd.DataFrame:
    """H5 — ⚠️ a declared PROXY. No rivalry list exists in the NCAAF lake, so 'rivalry' is
    approximated by an annually-recurring matchup: the unordered pair met in ≥`min_meetings` of the
    prior `lookback` seasons (STRICTLY prior — leakage-safe). A null here is a null about THE
    PROXY, and the dossier says so rather than claiming rivalry itself was refuted."""
    pair = pd.DataFrame({
        "season": df["season"].to_numpy(),
        "a": np.minimum(df["home_team"].astype(str), df["away_team"].astype(str)),
        "b": np.maximum(df["home_team"].astype(str), df["away_team"].astype(str)),
    })
    met = pair.drop_duplicates().assign(one=1)
    counts = []
    for s in sorted(pair["season"].unique()):
        w = met[(met["season"] >= s - lookback) & (met["season"] < s)]
        c = w.groupby(["a", "b"], as_index=False)["one"].sum().rename(columns={"one": "n_prior"})
        c["season"] = s
        counts.append(c)
    hist = pd.concat(counts, ignore_index=True)
    out = df.copy()
    out["_a"], out["_b"] = pair["a"].to_numpy(), pair["b"].to_numpy()
    out = out.merge(hist, left_on=["season", "_a", "_b"], right_on=["season", "a", "b"], how="left")
    out["rivalry_prior_meetings"] = out["n_prior"].fillna(0.0)
    out["is_rivalry_proxy"] = (out["rivalry_prior_meetings"] >= min_meetings).astype(float)
    out["rivalry_late_season"] = out["is_rivalry_proxy"] * (
        pd.to_numeric(out["season_order_week"], errors="coerce").fillna(0) >= 10).astype(float)
    return out.drop(columns=[c for c in ("_a", "_b", "a", "b", "n_prior") if c in out.columns])


def _simple_blocks(df: pd.DataFrame) -> pd.DataFrame:
    """H3 off-bye flags, H6 bowl terms, H9 pace aggregates — pure row-level derivations."""
    out = df.copy()
    for side in ("home", "away"):
        rest = pd.to_numeric(out[f"{side}_rest_days"], errors="coerce")
        out[f"{side}_off_bye"] = (rest >= 10).astype(float)
    out["off_bye_diff"] = out["home_off_bye"] - out["away_off_bye"]

    post = out["is_postseason"].fillna(False).astype(bool).astype(float)
    smd = pd.to_numeric(out["strength_margin_diff"], errors="coerce").fillna(0.0)
    out["is_postseason_flag"] = post
    out["postseason_x_strength"] = post * smd
    out["postseason_x_abs_strength"] = post * smd.abs()

    spp = [pd.to_numeric(out[f"{s}_seconds_per_play"], errors="coerce") for s in ("home", "away")]
    out["pace_sum"] = spp[0] + spp[1]      # the TOTAL axis: slow+slow ⇒ fewer possessions
    out["pace_diff"] = spp[0] - spp[1]
    return out


def assemble(args) -> Path:
    from quant_sports_intel_models.football.ncaaf.ingest.query_lake import q, delta
    from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game import build_clv_staging
    from quant_sports_intel_models.football.ncaaf.models.p2_1_plays_rollup import (
        attach_home_away, plays_game_team_sql, season_to_date,
    )

    print(f"=== {_STORY} stage 0 — assembling the battery cache ===")
    t0 = time.time()
    df = q(f"select * from {delta('feature_pregame_matrix', tier='derived')}")
    df[_DATE] = pd.to_datetime(df[_DATE], errors="coerce")
    df = df[df["label_is_completed"] == True].reset_index(drop=True)  # noqa: E712
    df = df[df[_YEAR] >= args.min_year].reset_index(drop=True)
    df["game_year"] = df[_YEAR].astype(int)
    print(f"  matrix: {len(df):,} completed games {int(df[_YEAR].min())}–{int(df[_YEAR].max())} "
          f"({time.time() - t0:.0f}s)")

    t1 = time.time()
    gt = q(plays_game_team_sql(delta("plays"), delta("games"), min_season=args.min_year))
    roll = season_to_date(gt)
    df = attach_home_away(df, roll)
    print(f"  plays rollup: {len(gt):,} game-team rows → season-to-date (strictly prior dates) "
          f"({time.time() - t1:.0f}s)")

    t2 = time.time()
    df = _schedule_blocks(df)
    df = _rivalry_blocks(df)
    df = _simple_blocks(df)
    print(f"  derived blocks: schedule (H4/H8) + rivalry proxy (H5) + simple (H3/H6/H9) "
          f"({time.time() - t2:.0f}s)")

    for c in _CLOSE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df["has_close"] = False
    if not args.no_odds:
        try:
            t3 = time.time()
            clv = build_clv_staging(min_year=2020)
            df = df.drop(columns=[c for c in _CLOSE_COLS if c in df.columns])
            df = df.merge(clv, on="game_id", how="left")
            df["has_close"] = df["close_home_spread"].notna() | df["close_total"].notna()
            print(f"  CLV closes: joined {int(df['has_close'].sum()):,} games ({time.time() - t3:.0f}s)")
        except Exception as e:  # noqa: BLE001 — degrade LOUDLY, never silently
            _log(f"[ALERT] CLV close join skipped ({type(e).__name__}: {e}) — the edge leg cannot "
                 "run without it; re-run --assemble with AWS creds.")

    # every block's declared columns must EXIST now (a missing column must raise here, not score a
    # quietly smaller feature set later)
    for b in BLOCKS:
        missing = [c for c in b.raw if c not in df.columns]
        if missing:
            raise SystemExit(f"[{_STORY}] block {b.arm!r} declares missing columns: {missing}")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_CACHE_PATH, index=False)
    _META_PATH.write_text(json.dumps({
        "story": _STORY, "assembled_at": date.today().isoformat(), "n_games": int(len(df)),
        "seasons": sorted(int(y) for y in df[_YEAR].unique()),
        "n_with_close": int(df["has_close"].sum()),
        "reference_cols": sorted(reference_columns(df)),
        "blocks": [b.arm for b in BLOCKS],
    }, indent=2))
    print(f"  cache → {_CACHE_PATH.relative_to(_PROJECT_ROOT)} "
          f"({_CACHE_PATH.stat().st_size / 1e6:.1f} MB)  [{time.time() - t0:.0f}s total]")
    return _CACHE_PATH


def load_cache() -> tuple[pd.DataFrame, dict]:
    if not _CACHE_PATH.exists():
        raise SystemExit(f"[{_STORY}] no cache at {_CACHE_PATH}. Run `--assemble` first.")
    return pd.read_parquet(_CACHE_PATH), json.loads(_META_PATH.read_text())


# ===========================================================================
# Folds — the EXACT P1.4 structure (season-forward, date-purged)
# ===========================================================================

def reference_columns(df: pd.DataFrame) -> list[str]:
    """The shipped P1.4 `strength_only` contract, resolved on this frame."""
    return [c for c in df.columns
            if any(c.startswith(p) for p in _STRENGTH_PREFIXES)
            and str(df[c].dtype) not in ("object", "category")]


@dataclass
class Fold:
    eval_year: int
    tr: pd.DataFrame
    ev: pd.DataFrame
    inner_tr: pd.DataFrame
    inner_ho: pd.DataFrame


def build_folds(df: pd.DataFrame, max_folds: int | None = None) -> list[Fold]:
    df = df.sort_values([_YEAR, "season_order_week", _DATE]).reset_index(drop=True)
    splitter = PurgedWalkForwardSplit(min_train_seasons=3, year_col="game_year", date_col=_DATE)
    folds = []
    for tr_idx, ev_idx in splitter.split(df, feature_cols=None):
        tr, ev = df.loc[tr_idx].reset_index(drop=True), df.loc[ev_idx].reset_index(drop=True)
        yr = int(ev["game_year"].mode().iloc[0])
        inner_year = int(tr["game_year"].max())
        mask = (tr["game_year"] == inner_year).to_numpy()
        if mask.sum() < 150 or (~mask).sum() < 300:
            mask = np.zeros(len(tr), bool); mask[int(len(tr) * 0.85):] = True
        folds.append(Fold(yr, tr, ev, tr[~mask].reset_index(drop=True), tr[mask].reset_index(drop=True)))
        if max_folds and len(folds) >= max_folds:
            break
    return folds


def _matrices(tr: pd.DataFrame, ev: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """bool→0/1, everything→float64, TRAIN-mean impute (fit on train only)."""
    def num(f: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({c: pd.to_numeric(f[c], errors="coerce").astype("float64") for c in cols},
                            index=f.index)
    A, B = num(tr), num(ev)
    m = A.mean(numeric_only=True)
    return A.fillna(m).fillna(0.0).to_numpy(float), B.fillna(m).fillna(0.0).to_numpy(float)


def _strength_var(frame: pd.DataFrame, impute: float | None = None) -> np.ndarray:
    sv = np.zeros(len(frame))
    for c in ("home_strength_margin_sd", "away_strength_margin_sd"):
        s = pd.to_numeric(frame[c], errors="coerce") if c in frame.columns else pd.Series(np.nan, index=frame.index)
        if impute is not None:
            s = s.fillna(np.sqrt(max(impute, 0.0) / 2.0))
        sv = sv + np.nan_to_num(s.to_numpy(float)) ** 2
    return sv


def _ridge_fit_predict(X_tr, y_m, y_t, X_ev, alpha: float = _RIDGE_ALPHA):
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler()
    A, B = sc.fit_transform(X_tr), sc.transform(X_ev)
    return (Ridge(alpha=alpha).fit(A, y_m).predict(B),
            Ridge(alpha=alpha).fit(A, y_t).predict(B))


# ===========================================================================
# Scoring one arm on one fold
# ===========================================================================

def _arm_columns(arm: str, fold: Fold, ref_cols: list[str]):
    """Materialise (train, eval, inner-train, inner-holdout) matrices for `arm`.

    An anchor that reuses the reference features returns them unchanged; `hfa_global` is the matched
    LEVEL-ONLY foil for H1b (identical construction, shrinkage → ∞)."""
    tr, ev, itr, iho = fold.tr, fold.ev, fold.inner_tr, fold.inner_ho

    def build(a: pd.DataFrame, b: pd.DataFrame):
        if arm in ("reference", "oracle_peek", "permute", "zero_width", "max_width"):
            return a[ref_cols], b[ref_cols], list(ref_cols)
        if arm == "hfa_global":
            x, y = eb_team_hfa_infold(a, b, shrink_to_global=True)
            return (pd.concat([a[ref_cols], a[["is_neutral_site"]], x], axis=1),
                    pd.concat([b[ref_cols], b[["is_neutral_site"]], y], axis=1),
                    list(ref_cols) + ["is_neutral_site"] + list(x.columns))
        blk = next(bb for bb in BLOCKS if bb.arm == arm)
        x, y, names = block_columns(blk, a, b)
        return (pd.concat([a[ref_cols], x], axis=1), pd.concat([b[ref_cols], y], axis=1),
                list(dict.fromkeys(list(ref_cols) + names)))

    tr_f, ev_f, cols = build(tr, ev)
    itr_f, iho_f, _ = build(itr, iho)
    cols = list(dict.fromkeys(cols))
    tr_f, ev_f = tr_f.loc[:, ~tr_f.columns.duplicated()], ev_f.loc[:, ~ev_f.columns.duplicated()]
    itr_f, iho_f = itr_f.loc[:, ~itr_f.columns.duplicated()], iho_f.loc[:, ~iho_f.columns.duplicated()]
    return tr_f, ev_f, itr_f, iho_f, cols


def score_arm_fold(arm: str, fold: Fold, ref_cols: list[str], rng: np.random.Generator,
                   *, n_draws: int = _N_DRAWS) -> dict[str, Any]:
    tr_f, ev_f, itr_f, iho_f, cols = _arm_columns(arm, fold, ref_cols)
    assert_market_blind(cols, context=f"{_STORY} {arm} fold {fold.eval_year}")

    y_m_tr = fold.tr[_MARGIN].to_numpy(float)
    y_t_tr = fold.tr[_TOTAL].to_numpy(float)
    y_m_ev = fold.ev[_MARGIN].to_numpy(float)
    y_t_ev = fold.ev[_TOTAL].to_numpy(float)

    if arm == "permute":
        # PERMUTATION anchor (NF1.7 b): fit on SHUFFLED outcomes. Well-posed at any n, which is why
        # it — not a thin fitted oracle — is the unit anchor. It must LOSE.
        p = rng.permutation(len(y_m_tr))
        y_m_tr, y_t_tr = y_m_tr[p], y_t_tr[p]

    X_tr, X_ev = _matrices(tr_f, ev_f, cols)
    if arm == "oracle_peek":
        # ORACLE FLOOR: the realised outcome appended as a feature. Same family (ridge), same
        # sample. NOTHING may beat it — an arm that does means the metric is inverted.
        X_tr = np.hstack([X_tr, y_m_tr[:, None], y_t_tr[:, None]])
        X_ev = np.hstack([X_ev, y_m_ev[:, None], y_t_ev[:, None]])

    mu_m, mu_t = _ridge_fit_predict(X_tr, y_m_tr, y_t_tr, X_ev)

    # dispersion: fit on the INNER HOLDOUT (inside train ⇒ leakage-safe), exactly as P1.4 does
    Xi_tr, Xi_ho = _matrices(itr_f, iho_f, cols)
    yi_m_tr, yi_t_tr = fold.inner_tr[_MARGIN].to_numpy(float), fold.inner_tr[_TOTAL].to_numpy(float)
    yi_m_ho, yi_t_ho = fold.inner_ho[_MARGIN].to_numpy(float), fold.inner_ho[_TOTAL].to_numpy(float)
    if arm == "oracle_peek":
        Xi_tr = np.hstack([Xi_tr, yi_m_tr[:, None], yi_t_tr[:, None]])
        Xi_ho = np.hstack([Xi_ho, yi_m_ho[:, None], yi_t_ho[:, None]])
    mu_m_ho, mu_t_ho = _ridge_fit_predict(Xi_tr, yi_m_tr, yi_t_tr, Xi_ho)
    rm, rt = yi_m_ho - mu_m_ho, yi_t_ho - mu_t_ho

    g = fit_gaussian_dispersion(rm, rt)
    disp = JointDispersion(sigma_margin=g.sigma_margin, sigma_total=g.sigma_total, rho=g.rho)
    sv_imp = float(np.nanmedian(_strength_var(fold.tr)))
    sv_ho = _strength_var(fold.inner_ho, impute=sv_imp)
    sv_ev = _strength_var(fold.ev, impute=sv_imp)
    disp.sigma0_margin, disp.k_margin = fit_strength_posterior_scale(rm, sv_ho)
    disp.sigma0_total, disp.k_total = fit_strength_posterior_scale(rt, sv_ho)
    sig_m = strength_posterior_sigma(disp.sigma0_margin, disp.k_margin, sv_ev)
    sig_t = strength_posterior_sigma(disp.sigma0_total, disp.k_total, sv_ev)

    if arm == "zero_width":
        # DEGENERATE (sharp): σ at the floor. Must LOSE CRPS *and* FAIL the calibration floor.
        sig_m = np.full_like(sig_m, 3.0); sig_t = np.full_like(sig_t, 3.0)
    elif arm == "max_width":
        # DEGENERATE (wide): σ ×3. Must SATISFY the coverage floor (proving the floor is a
        # constraint a degenerate satisfies, not a criterion it wins — NF1.8) and LOSE CRPS.
        sig_m, sig_t = sig_m * 3.0, sig_t * 3.0

    m_s, t_s = draw_joint(_FORM, mu_m, mu_t, disp, rng, n_draws=n_draws,
                          sigma_margin_native=sig_m, sigma_total_native=sig_t)
    dists = derive_markets(m_s, t_s)
    obs = {"margin": y_m_ev, "total": y_t_ev, "home_win": (y_m_ev > 0).astype(float)}
    metrics = score_calibration(dists, obs, rng)

    crps_m = crps_ensemble(y_m_ev, m_s)
    crps_t = crps_ensemble(y_t_ev, t_s)
    per_game = crps_m + crps_t

    buckets = []
    for sl in np.array_split(np.arange(len(y_m_ev)), _N_SLICES):
        if len(sl) >= 40:
            buckets.append(float(per_game[sl].mean()))

    # vs-close inputs, reduced to per-game PROBABILITIES here rather than carrying the raw
    # (n_games × n_draws) sample arrays out of the fold — at 8 folds those would be ~0.5 GB per arm
    # for a leg that only ever needs P(cover) and P(over).
    sp = pd.to_numeric(fold.ev.get("close_home_spread"), errors="coerce").to_numpy(float)
    tl = pd.to_numeric(fold.ev.get("close_total"), errors="coerce").to_numpy(float)
    has_close = np.isfinite(sp) | np.isfinite(tl)
    p_cover = np.where(np.isfinite(sp), (m_s > np.nan_to_num(-sp)[:, None]).mean(axis=1), np.nan)
    p_over = np.where(np.isfinite(tl), (t_s > np.nan_to_num(tl)[:, None]).mean(axis=1), np.nan)

    return {
        "arm": arm, "eval_year": fold.eval_year, "n_games": int(len(y_m_ev)), "n_features": len(cols),
        "crps": round(float(per_game.mean()), 5),
        "crps_margin": round(float(crps_m.mean()), 5), "crps_total": round(float(crps_t.mean()), 5),
        "pit_sum": round(downstream_score(metrics), 5),
        "margin_calib_80": metrics["margin"]["calib_80"], "total_calib_80": metrics["total"]["calib_80"],
        "margin_pit_flat": bool(metrics["margin"]["pit_is_flat"]),
        "total_pit_flat": bool(metrics["total"]["pit_is_flat"]),
        "margin_pit_dev": metrics["margin"]["pit_max_decile_dev"],
        "total_pit_dev": metrics["total"]["pit_max_decile_dev"],
        "h2h_brier": metrics["home_win"]["brier"],
        "sigma_margin": round(disp.sigma_margin, 3), "sigma_total": round(disp.sigma_total, 3),
        "k_margin": round(disp.k_margin, 3),
        "buckets": [round(b, 5) for b in buckets],
        "per_game_crps": per_game, "game_id": fold.ev["game_id"].to_numpy(),
        "p_cover": p_cover, "p_over": p_over, "has_close": has_close,
        "close_home_spread": sp, "close_total": tl,
        "y_margin": y_m_ev, "y_total": y_t_ev,
    }


# ===========================================================================
# Stage 1 — the battery
# ===========================================================================

def _clv_leg(rows: list[dict], rng: np.random.Generator) -> dict:
    """Deflated vs-close leg. An EDGE claim requires model-side ATS/OU > breakeven AND > placebo;
    a calibration win alone is NOT an edge claim (pre-registration §1.10).

    ⭐ Pushes are EXCLUDED from both the numerator and the denominator (a push returns the stake),
    and the placebo picks a random side on the SAME games — so it answers "does the model's SIDE
    beat a coin flip", not "does this game land over".
    """
    ym = np.concatenate([r["y_margin"] for r in rows])
    yt = np.concatenate([r["y_total"] for r in rows])
    sp = np.concatenate([r["close_home_spread"] for r in rows])
    tl = np.concatenate([r["close_total"] for r in rows])
    p_cov = np.concatenate([r["p_cover"] for r in rows])
    p_over = np.concatenate([r["p_over"] for r in rows])

    out: dict[str, Any] = {}
    ats_ok = np.isfinite(sp) & np.isfinite(p_cov)
    if ats_ok.sum() >= 100:
        s, y, p = sp[ats_ok], ym[ats_ok], p_cov[ats_ok]
        push = y == -s
        win = np.where(p >= 0.5, y > -s, y < -s)
        plac = np.where(rng.random(len(y)) >= 0.5, y > -s, y < -s)
        out.update({"ats_hit_rate": round(float(win[~push].mean()), 4),
                    "ats_n": int((~push).sum()),
                    "ats_placebo": round(float(plac[~push].mean()), 4)})
    ou_ok = np.isfinite(tl) & np.isfinite(p_over)
    if ou_ok.sum() >= 100:
        t, y, p = tl[ou_ok], yt[ou_ok], p_over[ou_ok]
        push = y == t
        win = np.where(p >= 0.5, y > t, y < t)
        out.update({"ou_hit_rate": round(float(win[~push].mean()), 4), "ou_n": int((~push).sum())})
    if not out:
        return {"n_with_close": int(ats_ok.sum()),
                "note": "too few closes for a stable vs-market read"}
    out["n_with_close"] = int(ats_ok.sum())
    out["breakeven"] = _BREAKEVEN
    out["clears_edge_bar"] = bool(
        out.get("ats_hit_rate", 0) > _BREAKEVEN
        and out.get("ats_hit_rate", 0) > out.get("ats_placebo", 1.0))
    return out


def stage_battery(args) -> None:
    df, meta = load_cache()
    ref_cols = reference_columns(df)
    folds = build_folds(df, max_folds=args.max_folds)
    arms = ["reference"] + [b.arm for b in BLOCKS] + list(ANCHORS)
    if args.arm:
        arms = ["reference"] + [a for a in args.arm.split(",") if a != "reference"]
    print(f"=== {_STORY} stage 1 — BATTERY ({len(arms)} arms × {len(folds)} folds, "
          f"{len(df):,} games, reference contract = {len(ref_cols)} cols) ===")
    print(f"  folds: {[f.eval_year for f in folds]}")

    out: dict[str, Any] = {"story": _STORY, "run_at": date.today().isoformat(),
                           "n_folds": len(folds), "n_games": int(len(df)),
                           "reference_n_cols": len(ref_cols), "arms": {}}
    for arm in arms:
        t0 = time.time()
        rng = np.random.default_rng(_SEED)   # identical stream per arm ⇒ a paired comparison
        rows = [score_arm_fold(arm, f, ref_cols, rng, n_draws=args.n_draws) for f in folds]
        clv = _clv_leg(rows, np.random.default_rng(_SEED)) if not args.no_clv else {}
        slim = [{k: v for k, v in r.items() if not isinstance(v, np.ndarray)} for r in rows]
        pooled_crps = float(np.mean(np.concatenate([r["per_game_crps"] for r in rows])))
        out["arms"][arm] = {
            "arm": arm, "folds": slim, "clv": clv,
            "pooled_crps": round(pooled_crps, 5),
            "mean_crps": round(float(np.mean([r["crps"] for r in rows])), 5),
            "fold_crps": [r["crps"] for r in rows],
            "buckets": [b for r in rows for b in r["buckets"]],
            "mean_pit_sum": round(float(np.mean([r["pit_sum"] for r in rows])), 5),
            "min_margin_calib": round(float(np.min([r["margin_calib_80"] for r in rows])), 4),
            "min_total_calib": round(float(np.min([r["total_calib_80"] for r in rows])), 4),
            "pooled_margin_calib": round(float(np.mean([r["margin_calib_80"] for r in rows])), 4),
            "pooled_total_calib": round(float(np.mean([r["total_calib_80"] for r in rows])), 4),
            "margin_pit_flat_folds": int(sum(r["margin_pit_flat"] for r in rows)),
            "total_pit_flat_folds": int(sum(r["total_pit_flat"] for r in rows)),
            "mean_h2h_brier": round(float(np.mean([r["h2h_brier"] for r in rows])), 4),
            "n_features": rows[0]["n_features"],
        }
        a = out["arms"][arm]
        print(f"  {arm:<22} CRPS {a['pooled_crps']:.4f}  calib80(m/t) {a['pooled_margin_calib']:.3f}/"
              f"{a['pooled_total_calib']:.3f}  PITsum {a['mean_pit_sum']:.4f}  "
              f"feat {a['n_features']:>3}  ({time.time() - t0:.0f}s)")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _SCORES_JSON.write_text(json.dumps(out, indent=2, default=float))
    print(f"\n  scores → {_SCORES_JSON.relative_to(_PROJECT_ROOT)}")
    print("  Next: `--stage decide`")
    _ = meta


# ===========================================================================
# Stage 2 — deflate, classify, render
# ===========================================================================

def _coverage_floor_ok(a: dict) -> tuple[bool, str]:
    """Clause 1 of the constraint — the 80% COVERAGE FLOOR alone, on both scored distributions.

    ⚠️ Kept SEPARATE from the PIT clause on purpose. NF1.8's `max_width` proof is specifically that
    a maximally-wide degenerate **satisfies the coverage floor** and is then eliminated by the
    METRIC — that is what shows the floor is a CONSTRAINT rather than a criterion a degenerate can
    win. Reading that anchor through a predicate that also bundles PIT-flatness reports
    `satisfies_floor = False` at calib 1.000 and silently destroys the proof (a bundled gate flag
    mixing two distinct clauses is a liability — the reader cannot tell which half failed).
    """
    floor = _CALIB_TARGET - _CALIB_TOL
    if a["pooled_margin_calib"] < floor:
        return False, f"margin calib {a['pooled_margin_calib']:.3f} < {floor:.2f}"
    if a["pooled_total_calib"] < floor:
        return False, f"total calib {a['pooled_total_calib']:.3f} < {floor:.2f}"
    return True, ""


def _margin_pit_ok(a: dict) -> tuple[bool, str]:
    """Clause 2 — the margin PIT must be flat in a majority of folds.

    ⭐ Total PIT-flatness is deliberately NOT a clause: the shipped reference itself FAILS it (P1.4
    total PITdev 0.0218), and gating on a clause the incumbent fails is the MH2.1(b) inversion —
    an incumbent-relative gate inverts exactly when the incumbent is the defective one. Total shape
    is NCAAF-P2.5's scope; it is measured and reported here, and decides nothing."""
    need = max(1, int(0.5 * len(a["fold_crps"])))
    if a["margin_pit_flat_folds"] < need:
        return False, (f"margin PIT flat in only {a['margin_pit_flat_folds']}/"
                       f"{len(a['fold_crps'])} folds (need ≥ {need})")
    return True, ""


def _eligible(a: dict) -> tuple[bool, str]:
    """The full pre-registered calibration CONSTRAINT = coverage floor AND margin-PIT flatness.
    Never a target; never tightened above nominal (both are monotone in widening — NF1.8)."""
    for clause in (_coverage_floor_ok, _margin_pit_ok):
        ok, why = clause(a)
        if not ok:
            return False, why
    return True, ""


def _paired_p(delta: np.ndarray) -> float:
    """One-sided paired p-value that the mean improvement > 0 (t on the per-fold deltas)."""
    d = np.asarray(delta, float)
    n = len(d)
    if n < 2 or d.std(ddof=1) == 0:
        return 1.0 if d.mean() <= 0 else 0.0
    from scipy import stats
    t = d.mean() / (d.std(ddof=1) / math.sqrt(n))
    return float(stats.t.sf(t, df=n - 1))


def _bh(pvals: dict[str, float], alpha: float = _FDR_ALPHA) -> tuple[dict[str, bool], float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    passed, cutoff = {k: False for k in pvals}, 0.0
    kmax = 0
    for i, (_k, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            kmax, cutoff = i, alpha * i / m
    for i, (k, _p) in enumerate(items, start=1):
        passed[k] = i <= kmax
    return passed, cutoff


def stage_decide(args) -> None:
    if not _SCORES_JSON.exists():
        raise SystemExit(f"[{_STORY}] no scores — run `--stage battery` first.")
    doc = json.loads(_SCORES_JSON.read_text())
    arms = doc["arms"]
    if "reference" not in arms:
        raise SystemExit(f"[{_STORY}] the reference arm is missing from the scores.")
    ref = arms["reference"]
    n_folds = doc["n_folds"]
    real = [b.arm for b in BLOCKS if b.arm in arms]
    anchors = [a for a in ANCHORS if a in arms]

    # ── anchor verification FIRST: an anchor that misbehaves invalidates the whole run ─────────
    anchor_report: dict[str, Any] = {}
    ref_crps = ref["pooled_crps"]
    all_real = {a: arms[a]["pooled_crps"] for a in real}
    best_real = min(all_real.values()) if all_real else ref_crps
    if "oracle_peek" in arms:
        o = arms["oracle_peek"]["pooled_crps"]
        anchor_report["oracle_floor"] = {
            "oracle_crps": o, "best_real_crps": best_real,
            "holds": bool(o <= best_real + 1e-9),
            "note": "nothing may beat a peeking same-family, same-sample oracle; a breach ⇒ the "
                    "metric is inverted (E2.1-r)."}
    for name, expect in (("permute", "must LOSE"), ("zero_width", "must LOSE + FAIL the floor"),
                         ("max_width", "must SATISFY the floor + LOSE")):
        if name in arms:
            a = arms[name]
            # ⚠️ the COVERAGE FLOOR alone, never the bundled eligibility predicate — see
            # `_coverage_floor_ok`. Reading `max_width` through the bundled version reports
            # "floor failed" at calib 1.000 and destroys the NF1.8 proof this anchor exists for.
            cov_ok, _ = _coverage_floor_ok(a)
            anchor_report[name] = {
                "crps": a["pooled_crps"], "loses_to_reference": bool(a["pooled_crps"] > ref_crps),
                "satisfies_coverage_floor": cov_ok, "margin_calib": a["pooled_margin_calib"],
                "total_calib": a["pooled_total_calib"], "expectation": expect}

    def _anchor(name: str, key: str, default: bool) -> bool:
        return bool(anchor_report.get(name, {}).get(key, default))

    anchor_checks = {
        "oracle_floor_holds": _anchor("oracle_floor", "holds", True),
        "permute_loses": _anchor("permute", "loses_to_reference", True),
        "zero_width_loses": _anchor("zero_width", "loses_to_reference", True),
        "max_width_loses": _anchor("max_width", "loses_to_reference", True),
        # the two-sided degenerate proof: the SHARP one must FAIL the coverage floor, the WIDE one
        # must SATISFY it (and still lose the metric) — NF1.8's "a constraint a degenerate
        # satisfies is fine; a criterion a degenerate wins is fatal".
        "zero_width_fails_floor": not _anchor("zero_width", "satisfies_coverage_floor", True),
        "max_width_satisfies_floor": _anchor("max_width", "satisfies_coverage_floor", False),
    }
    anchors_ok = all(anchor_checks.values())

    # ── per-arm paired read ────────────────────────────────────────────────────────────────────
    ref_folds = np.array(ref["fold_crps"], float)
    ref_buckets = np.array(ref["buckets"], float)
    clause = cv_power.fold_consistency_clause(n_folds)
    rows: dict[str, Any] = {}
    pvals: dict[str, float] = {}
    for arm in real:
        a = arms[arm]
        d = ref_folds - np.array(a["fold_crps"], float)     # >0 ⇔ arm better (lower CRPS)
        gain = ref_crps - a["pooled_crps"]
        elig, why = _eligible(a)
        tie = abs(gain) < _TIE_BAND
        p = _paired_p(d)
        rows[arm] = {
            "arm": arm, "gain_crps": round(float(gain), 5), "pooled_crps": a["pooled_crps"],
            "fold_wins": int((d > 0).sum()), "n_folds": n_folds,
            "fold_clause_required": clause.wins_required, "fold_clause_attainable": clause.attainable,
            "fold_clause_passes": bool(clause.passes(int((d > 0).sum()))),
            "eligible": elig, "ineligible_reason": why,
            "tie_with_foil": bool(tie),
            "p_one_sided": round(p, 6),
            "margin_calib": a["pooled_margin_calib"], "total_calib": a["pooled_total_calib"],
            "total_pit_flat_folds": a["total_pit_flat_folds"],
            "pit_sum": a["mean_pit_sum"], "n_features": a["n_features"],
            "clv": a.get("clv", {}),
        }
        pvals[arm] = p
    bh_pass, bh_cutoff = _bh(pvals)
    for arm in real:
        rows[arm]["bh_pass"] = bool(bh_pass[arm])

    # ── deflation: PBO over the ELIGIBLE REAL set; DSR with the DSR-CONV convention ────────────
    elig_arms = [a for a in real if rows[a]["eligible"]] + (["reference"] if _eligible(ref)[0] else [])
    nb = min(len(arms[a]["buckets"]) for a in elig_arms) if elig_arms else 0
    pbo = float("nan")
    if len(elig_arms) >= 2 and nb >= 4:
        perf = np.array([arms[a]["buckets"][:nb] for a in elig_arms], float).T
        pbo = float(pbo_cscv(perf, higher_is_better=False,
                             n_splits=max(2, min(16, nb - nb % 2))).pbo)

    # trial Sharpes for V: NON-anchor arms only (DSR-CONV, declared forward)
    def bucket_improvement(arm: str) -> np.ndarray:
        n = min(len(ref_buckets), len(arms[arm]["buckets"]))
        return ref_buckets[:n] - np.array(arms[arm]["buckets"][:n], float)

    def sharpe(x: np.ndarray) -> float:
        s = x.std(ddof=1)
        return float(x.mean() / s) if s > 0 else 0.0

    sr_real = [sharpe(bucket_improvement(a)) for a in real]
    sr_all = sr_real + [sharpe(bucket_improvement(a)) for a in anchors]
    n_trials = 1 + len(real) + len(anchors)     # reference + real arms + anchors
    V_clean = float(np.var(sr_real, ddof=1)) if len(sr_real) > 1 else None
    V_all = float(np.var(sr_all, ddof=1)) if len(sr_all) > 1 else None

    # ── survivors ──────────────────────────────────────────────────────────────────────────────
    survivors = [a for a in real
                 if rows[a]["eligible"] and not rows[a]["tie_with_foil"]
                 and rows[a]["gain_crps"] > 0 and rows[a]["bh_pass"]
                 and rows[a]["fold_clause_passes"]]

    # ⭐ DEFLATE THE ARM THAT WOULD ACTUALLY BE PROMOTED, not merely the best-CRPS one. If a
    # candidate leads on raw CRPS but is INELIGIBLE (or a tie, or fails BH), deflating IT would
    # decide the promotion gate on an arm that cannot be promoted — the gate must bind on the
    # thing it is gating. Falls back to the best arm only when there is no survivor, purely so a
    # null still reports a DSR figure.
    dsr_arm = (min(survivors, key=lambda a: arms[a]["pooled_crps"]) if survivors
               else (min(real, key=lambda a: arms[a]["pooled_crps"]) if real else None))
    dsr_clean = dsr_all = float("nan")
    if dsr_arm and rows[dsr_arm]["gain_crps"] > 0:
        imp = bucket_improvement(dsr_arm)
        dsr_clean = float(deflated_sharpe(imp, n_trials=n_trials, var_trials_sr=V_clean).dsr)
        dsr_all = float(deflated_sharpe(imp, n_trials=n_trials, var_trials_sr=V_all).dsr)
    deflation_clean = bool(np.isfinite(pbo) and pbo < _PBO_GATE and dsr_clean >= _DSR_GATE)

    # H1b attribution vs its matched level-only foil (NF-D15 g′)
    attribution = {}
    if "hfa_team_eb" in rows and "hfa_global" in arms:
        eb, gl = arms["hfa_team_eb"]["pooled_crps"], arms["hfa_global"]["pooled_crps"]
        attribution["hfa_team_eb_vs_global"] = {
            "eb_crps": eb, "global_foil_crps": gl, "delta": round(float(gl - eb), 5),
            "per_team_content_earns_it": bool(gl - eb > _TIE_BAND),
            "note": "if the EB per-team arm does not beat the identical construction with "
                    "shrinkage→∞, the effect is a GLOBAL LEVEL (H1a's territory), not per-team "
                    "content — the mechanism claim is refuted, not assumed (NF-D15 g′)."}

    # ── null classification ────────────────────────────────────────────────────────────────────
    # ⭐ A SURVIVOR IS CLASSIFIED TOO WHENEVER THE RUN DOES NOT PROMOTE IT. An arm can clear every
    # ARM-LEVEL gate (eligible, not a tie, BH-FDR, fold-consistency) and still not ship because a
    # RUN-LEVEL gate (PBO / DSR) failed — and then its state is the single most important line in
    # the report, because it says whether the shortfall is reachable. Skipping survivors left
    # exactly that line missing on the first real run: `pace` cleared 8/8 folds at p=0.0020 and was
    # reported with NO state at all, so a reader could not tell POWER_LIMITED (buy more seasons)
    # from DSR_UNREACHABLE (no `n` and no field size ever clears). Classify every non-promoted arm.
    promoted = set(survivors) if (survivors and deflation_clean and anchors_ok) else set()
    nulls = {}
    for arm in real:
        if arm in promoted:
            continue
        r = rows[arm]
        state_override = None
        if not r["eligible"]:
            # a null caused by a HARD CONSTRAINT, not by the metric — no amount of data moves it
            state_override = ("CONSTRAINT_REFUSED",
                              f"refused by the calibration constraint ({r['ineligible_reason']}), "
                              "not by the metric — the remedy is a different mechanism or a PM "
                              "decision, NEVER more seasons (NF-D18).")
        v = cv_power.classify_null(
            metric="CRPS(margin)+CRPS(total)", n_folds=n_folds, n_arms=len(real),
            beats_foil=bool(r["gain_crps"] > 0),
            observed_sr=sharpe(bucket_improvement(arm)),
            var_trials_sr=V_clean, fold_wins=r["fold_wins"],
            p_one_sided=r["p_one_sided"], bh_cutoff=bh_cutoff,
            degenerates_excluded_from_v=True,
            var_trials_sr_with_degenerates=V_all,
            declared_field_size=DECLARED_FIELD_SIZE)
        nulls[arm] = {
            "arm_level_gates_cleared": bool(arm in survivors),
            "state": state_override[0] if state_override else v.state,
            "reason": state_override[1] if state_override else v.reason,
            "retest_trigger": None if state_override else v.retest_trigger,
            "folds_have": v.folds_have, "folds_needed": v.folds_needed,
            "extra_seasons": v.extra_seasons, "max_field_size": v.max_field_size,
            "field_remedy_admissible": v.field_remedy_admissible,
            "reclassified_from": v.state if state_override else None,
        }

    verdict = ("PROMOTE" if (survivors and deflation_clean and anchors_ok)
               else "REFERENCE_STANDS")

    out = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "preregistration": "ablation_results/ncaaf_p2_1_preregistration.md",
        "verdict": verdict, "anchors_ok": anchors_ok, "anchor_checks": anchor_checks,
        "anchors": anchor_report,
        "n_folds": n_folds, "n_games": doc["n_games"],
        "declared_field_size": DECLARED_FIELD_SIZE, "n_trials": n_trials,
        "reference": {"pooled_crps": ref_crps, "margin_calib": ref["pooled_margin_calib"],
                      "total_calib": ref["pooled_total_calib"], "pit_sum": ref["mean_pit_sum"],
                      "h2h_brier": ref["mean_h2h_brier"], "clv": ref.get("clv", {})},
        "arms": rows, "survivors": survivors,
        "fold_consistency": {"n_folds": n_folds, "wins_required": clause.wins_required,
                             "attainable": clause.attainable,
                             "false_fire": clause.attained_false_fire,
                             "legacy_wins_required": clause.legacy_wins_required},
        "bh_cutoff": round(bh_cutoff, 6), "fdr_alpha": _FDR_ALPHA,
        "pbo": round(pbo, 4) if np.isfinite(pbo) else None, "pbo_gate": _PBO_GATE,
        "pbo_over": "the ELIGIBLE REAL-arm set (anchors excluded — they are not promotion candidates)",
        "dsr_degenerate_excluded": round(dsr_clean, 4) if np.isfinite(dsr_clean) else None,
        "dsr_whole_field": round(dsr_all, 4) if np.isfinite(dsr_all) else None,
        "dsr_gate": _DSR_GATE, "dsr_binding": "degenerate-excluded (DSR-CONV, declared forward)",
        "dsr_arm": dsr_arm, "dsr_arm_is_survivor": bool(dsr_arm in survivors),
        "V_degenerate_excluded": V_clean, "V_whole_field": V_all,
        "deflation_clean": deflation_clean,
        "attribution": attribution, "nulls": nulls,
        "best_alpha": 0,
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _DECISION_JSON.write_text(json.dumps(out, indent=2, default=float))
    _DECISION_MD.write_text(render_dossier(out))
    _print_decision(out)
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}\n  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")
    _ = args


def _print_decision(d: dict) -> None:
    print("=" * 88)
    print(f"{_STORY} DECISION — {d['n_trials']} configs, {d['n_folds']} folds, "
          f"declared field {d['declared_field_size']}")
    print("=" * 88)
    print(f"  anchors valid: {'YES ✅' if d['anchors_ok'] else 'NO ❌ — the run is not interpretable'}")
    for k, v in d.get("anchor_checks", {}).items():
        print(f"    {'✅' if v else '❌'} {k}")
    for k, v in d["anchors"].items():
        print(f"    {k:<14} {json.dumps({kk: vv for kk, vv in v.items() if kk != 'note'})}")
    print(f"\n  reference CRPS {d['reference']['pooled_crps']:.4f}")
    ordered = sorted(d["arms"].values(), key=lambda r: -r["gain_crps"])
    print(f"  {'arm':<22}{'ΔCRPS':>9}{'folds':>7}{'p':>10}{'BH':>5}{'elig':>6}{'tie':>5}")
    for r in ordered:
        print(f"  {r['arm']:<22}{r['gain_crps']:>+9.4f}{r['fold_wins']:>4}/{r['n_folds']:<2}"
              f"{r['p_one_sided']:>10.4f}{'✓' if r['bh_pass'] else '·':>5}"
              f"{'✓' if r['eligible'] else '✗':>6}{'≈' if r['tie_with_foil'] else '·':>5}")
    print(f"\n  PBO {d['pbo']} (gate < {d['pbo_gate']})   DSR(degenerate-excluded) "
          f"{d['dsr_degenerate_excluded']} (gate ≥ {d['dsr_gate']})   "
          f"DSR(whole-field) {d['dsr_whole_field']}")
    print(f"  survivors: {d['survivors'] or 'NONE'}")
    print(f"\n  VERDICT: {d['verdict']}")


def render_dossier(d: dict) -> str:
    L = [f"# {_STORY} — game-model structural refinement: the pre-registered hypothesis battery", "",
         f"_Decided {d['decided_at']} · {d['n_trials']} configs · {d['n_folds']} purged folds · "
         f"{d['n_games']:,} games · declared real-arm field {d['declared_field_size']}_", "",
         f"**Pre-registration:** [`{d['preregistration'].split('/')[-1]}`]"
         f"(./{d['preregistration'].split('/')[-1]}) — written and committed BEFORE the first score.",
         "", "## Verdict", "", f"**{d['verdict']}**", ""]
    if d["verdict"] == "REFERENCE_STANDS":
        L += ["No pre-registered structural hypothesis survived the full deflation. The shipped P1.4 "
              "reference (`ridge / strength_only / strength_posterior`) carries.", ""]
    L += ["| gate | value | bar | |", "|---|---|---|---|",
          f"| anchors valid | {d['anchors_ok']} | all five must behave | "
          f"{'✅' if d['anchors_ok'] else '❌'} |",
          f"| PBO (eligible real set) | {d['pbo']} | < {d['pbo_gate']} | "
          f"{'✅' if d['pbo'] is not None and d['pbo'] < d['pbo_gate'] else '❌'} |",
          f"| DSR (degenerate-excluded — **binding**) | {d['dsr_degenerate_excluded']} | ≥ {d['dsr_gate']} | "
          f"{'✅' if (d['dsr_degenerate_excluded'] or 0) >= d['dsr_gate'] else '❌'} |",
          f"| DSR (whole field, reported) | {d['dsr_whole_field']} | — | — |",
          f"| BH-FDR cutoff | {d['bh_cutoff']} | α = {d['fdr_alpha']} | — |",
          f"| fold-consistency (calibrated) | {d['fold_consistency']['wins_required']} of "
          f"{d['n_folds']} wins | false-fire ≤ 0.20 | — |", "",
          "## Anchors — the two-sided proof the metric is not inverted", "",
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
            want_floor = {"zero_width": False, "max_width": True}.get(n)
            floor_ok = (want_floor is None
                        or bool(v["satisfies_coverage_floor"]) is want_floor)
            L.append(f"| `{n}` | CRPS {v['crps']:.4f}, calib80 {v['margin_calib']:.3f}/"
                     f"{v['total_calib']:.3f}, coverage floor "
                     f"{'satisfied' if v['satisfies_coverage_floor'] else 'FAILED'} | "
                     f"{v['expectation']} | "
                     f"{'✅' if (v['loses_to_reference'] and floor_ok) else '❌'} |")
    L += ["", "## Per-hypothesis result", "",
          "ΔCRPS > 0 means the arm BEATS the reference (CRPS is lower-is-better; the column is "
          "`reference − arm`). `elig` is the pre-registered calibration CONSTRAINT; `tie` is the "
          "nested-form guard (every arm nests the reference, so a sub-`1e-3` \"lead\" is a TIE, "
          "refused as a win).", "",
          "| arm | ΔCRPS | fold wins | p (1-sided) | BH | eligible | tie | null state |",
          "|---|---|---|---|---|---|---|---|"]
    for r in sorted(d["arms"].values(), key=lambda x: -x["gain_crps"]):
        st = d["nulls"].get(r["arm"], {}).get("state", "**SURVIVOR**")
        L.append(f"| `{r['arm']}` | {r['gain_crps']:+.4f} | {r['fold_wins']}/{r['n_folds']} | "
                 f"{r['p_one_sided']:.4f} | {'✅' if r['bh_pass'] else '—'} | "
                 f"{'✅' if r['eligible'] else '❌'} | {'≈' if r['tie_with_foil'] else '—'} | {st} |")
    if d.get("attribution"):
        L += ["", "## Mechanism attribution (matched foils)", ""]
        for k, v in d["attribution"].items():
            L += [f"- **{k}** — {json.dumps({kk: vv for kk, vv in v.items() if kk != 'note'})}",
                  f"  <br>{v.get('note', '')}"]
    L += ["", "## Null classification", "",
          "Each non-survivor is classified with `cv_power.classify_null(declared_field_size="
          f"{d['declared_field_size']}, degenerates_excluded_from_v=True)`. The report reads the "
          "MACHINE flag `field_remedy_admissible`, not the prose (MH2.7). A `CONSTRAINT_REFUSED` "
          "gets **no** re-test trigger — no sampling error accumulates against a hard constraint "
          "(NF-D18).", "",
          "⭐ An arm marked **arm-gates ✅** cleared every ARM-level gate (eligible · not a tie · "
          "BH-FDR · fold-consistency) and was still not promoted because a RUN-level gate "
          "(PBO / DSR) failed. Its state is the line that says whether that shortfall is "
          "REACHABLE.", "",
          "| arm | arm-gates | state | field remedy admissible | re-test trigger |",
          "|---|---|---|---|---|"]
    for arm, v in d["nulls"].items():
        L.append(f"| `{arm}` | {'✅' if v.get('arm_level_gates_cleared') else '—'} | {v['state']} | "
                 f"{v['field_remedy_admissible']} | {v['retest_trigger'] or '—'} |")
    L += ["", "## Honest framing", "",
          f"`best_alpha = {d['best_alpha']}`. A calibration result is **product value** (honest "
          "3-market probabilities), never an edge claim. An edge claim additionally requires the "
          f"deflated vs-close leg (model-side ATS/OU > {_BREAKEVEN} breakeven AND > placebo); the "
          "reference's own vs-close reading is recorded below.", "",
          f"- reference vs-close: `{json.dumps(d['reference'].get('clv', {}))}`", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"Story {_STORY} — NCAAF structural hypothesis battery")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--stage", choices=["battery", "decide"])
    ap.add_argument("--min-year", type=int, default=2015)
    ap.add_argument("--no-odds", action="store_true")
    ap.add_argument("--no-clv", action="store_true")
    ap.add_argument("--arm", type=str, default=None, help="comma-separated subset (smoke only)")
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--n-draws", type=int, default=_N_DRAWS)
    args = ap.parse_args()
    _log(f"{_STORY} start · stage={args.stage or 'assemble'} · pid={os.getpid()}")
    if args.assemble:
        assemble(args)
    elif args.stage == "battery":
        stage_battery(args)
    elif args.stage == "decide":
        stage_decide(args)
    else:
        ap.error("pass --assemble or --stage {battery,decide}")


if __name__ == "__main__":
    main()
