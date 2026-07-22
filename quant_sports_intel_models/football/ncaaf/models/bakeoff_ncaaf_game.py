"""bakeoff_ncaaf_game.py — NCAAF-P1.4 (the game-model BAKE-OFF: H2H · spread · total).

WHAT P1.4 IS
------------
The NCAAF game model, built with the MLB §0.5 bake-off discipline — NOT a single architecture.
Per the story it is built LEAN (`ncaaf_game_distribution.py`): model the JOINT (margin, total)
scoring distribution ONCE and DERIVE all three markets, mirroring MLB E2 (per-side → convolve →
read off every market). The three markets are pure reads off the joint draw:

    H2H     P(home wins)   = P(margin > 0)
    spread  P(home covers) = P(margin > line)
    total   P(over)        = P(total > line)

THE PRE-REGISTERED SEARCH  (learner × contract × form) — every axis counts toward deflation
------------------------------------------------------------------------------------------
LEARNERS (predict the two means μ_margin, μ_total per game):
  ridge · lgbm · xgb · catboost · ngboost_normal (native per-game σ)

DISTRIBUTIONAL FORMS (`ncaaf_game_distribution.FORMS`, the §0.5 ≥3-form axis):
  gaussian (bivariate Normal — the textbook football form + the E13.6 σ recalibration) ·
  student_t (heavy tails for CFB blowouts / back-door covers) ·
  native (NGBoost per-game σ — heteroscedastic) · count (home/away NegBin point counts convolved)

FEATURE CONTRACTS (pre-registered, hypothesis-driven, selected IN-FOLD):
  full · strength_only (the P1.2 strength prior alone — the FOIL the full matrix must beat;
  a candidate that doesn't beat strength-only isn't earning its complexity) · clustered
  (|ρ|≥0.95 redundancy prune) · top_k (in-fold gain top-K)

THE REFERENCE/FOIL = `ridge__strength_only__gaussian` — the P1.2 strength margin/total prior with a
held-out-calibrated Gaussian spread. The bake-off question is exactly "does the full 180-feature
matrix, under a real learner + form, robustly BEAT the strength prior on downstream calibration?"

SELECTION METRIC (carried from MLB E2.1-r, with its landmine fix):
    downstream_score = PIT_max_decile_dev(margin) + PIT_max_decile_dev(total)   (lower better)
`calib_80 ≥ 0.80` enforced as a FLOOR, never a target (inclusive-integer coverage is inflated —
an oracle covers > 0.80). Guard: `test_oracle_is_the_scoring_floor`. PBO<0.2 / DSR≥0 count EVERY
(learner × contract × form × Optuna trial) config.

CV — the single most important P1.1 carry-over: the time axis is the SEASON ORDER, never raw
`week`. We use a season-forward PURGED walk-forward split (train on all prior seasons, eval one
held-out season), purging the prior-season TAIL by CALENDAR DATE (`game_date`). Because the purge
and fold ordering are by date — monotone with `season_order_week` and IMMUNE to the postseason
`week`=1 collision — the embargo can never leak January playoff games into September. The eval
season is wholly out of sample, so there is no within-season train/eval overlap at all.

DATA (§0.5 cost hygiene) — ONE PULL → PARQUET, off the MLB serving lane:
  `--assemble` reads the P1.3 `feature_ncaaf_pregame_matrix` (cached parquet or S3 Delta,
  Snowflake-FREE) ONCE, builds the CLV staging join (`odds_ncaaf_historical` closing lines ⋈
  matrix on the CFBD game id, `snapshot_ts < commence`), and writes one cache. Every learner ×
  contract × form × Optuna trial × CV fold reads that cache.

MARKET-BLIND: `assert_market_blind` runs on every contract's column list before any fit. The
closing lines live ONLY in the vs-market/CLV eval leg, never as training features.

HONEST FRAME: a market-BLIND joint distribution is PRODUCT value (calibrated 3-market
probabilities), NOT an edge claim. `best_alpha = 0` until the gate clears AND a positive
vs-close window (pre-season NCAAF: the offline deflated historical-CLV eval, 2020–2025).

USAGE (operator — stages 1/2/4 are the >1-min jobs; NCAAF is ~9k games so lighter than MLB)
------------------------------------------------------------------------------------------
    # 0) one pull → parquet cache (LAPTOP, has AWS read creds; needs AWS_DEFAULT_REGION=us-east-2)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --assemble

    # 1) the bake-off: 5 learners × 4 contracts × their default form, purged CV
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage bakeoff

    # 2) Optuna, ONE learner per invocation (retrain-per-target convention)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game \
        --stage optuna --model-class lgbm --n-trials 40

    # 3) collect every stage-1/2 config → PBO/DSR + winner-vs-reference verdict
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage decide

    # 4) fit the winner on all seasons → served joint distribution + PIT gate + vs-close CLV eval
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage finalize
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

_THREAD_CAP = os.environ.get("NCAAF_P1_4_THREADS", "").strip()
if _THREAD_CAP:
    for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[_v] = _THREAD_CAP

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv import PurgedWalkForwardSplit  # noqa: E402
from betting_ml.utils.market_blind import assert_market_blind  # noqa: E402
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (  # noqa: E402
    FORMS,
    SCORED_DISTS,
    JointDispersion,
    NcaafGameDistributionParams,
    derive_markets,
    downstream_score,
    draw_joint,
    fit_gaussian_dispersion,
    fit_negbin_r,
    fit_strength_posterior_scale,
    fit_student_t_dof,
    interval_coverage,
    passes_calibration_floor,
    pit_flatness,
    randomized_pit,
    score_calibration,
    strength_posterior_sigma,
)

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

_STORY = "NCAAF-P1.4"
_REFERENCE = ("ridge", "strength_only", "gaussian")   # the P1.2 strength prior + Gaussian spread
_REF_LEARNER, _REF_CONTRACT, _REF_FORM = _REFERENCE

_MODELS_DIR = Path(__file__).resolve().parent
_ARTIFACT_DIR = _MODELS_DIR / "artifacts"
_DEFAULT_MATRIX_PARQUET = _ARTIFACT_DIR / "feature_ncaaf_pregame_matrix.parquet"

_CACHE_DIR = _PROJECT_ROOT / "betting_ml" / "data" / "cache"
_CACHE_PATH = _CACHE_DIR / "ncaaf_p1_4_game_matrix.parquet"
_META_PATH = _CACHE_DIR / "ncaaf_p1_4_game_matrix.meta.json"

_RESULTS_DIR = _MODELS_DIR.parent / "ablation_results"
_TRIALS_DIR = _RESULTS_DIR / "ncaaf_p1_4_configs"
_DECISION_JSON = _RESULTS_DIR / "ncaaf_p1_4_game_bakeoff.json"
_DECISION_MD = _RESULTS_DIR / "ncaaf_p1_4_game_bakeoff.md"
_CALIB_JSON = _RESULTS_DIR / "ncaaf_p1_4_calibration.json"
_CALIB_MD = _RESULTS_DIR / "ncaaf_p1_4_calibration.md"
_SERVED_JSON = _ARTIFACT_DIR / "ncaaf_game_distribution_v1.json"

_MARGIN = "label_home_margin"
_TOTAL = "label_total_points"
_YEAR = "season"
_DATE = "game_date"

# Non-feature columns: identifiers, the CV axes, the labels, and the high-cardinality team /
# conference NAMES (identifiers — team quality is already encoded by the strength ratings; OHE-ing
# team names would only invite memorisation and explode the matrix). Booleans ARE features
# (0/1/NaN). The vs-market close columns (built in the CLV staging join) are excluded from every
# training contract by `assert_market_blind` + this list.
_ID_COLS = frozenset({
    "sport", "game_id", "season", "game_year", "week", "season_order_week", "season_type",
    "is_postseason", "game_date", "start_date", "game_venue_timezone",
    "home_team", "away_team", "home_conference", "away_conference",
})
_LABEL_PREFIX = "label_"
# The CLV staging columns the assemble step appends (kept OUT of features).
_CLOSE_COLS = ("close_home_spread", "close_total", "close_home_ml_american", "close_home_ml_prob",
               "close_snapshot_ts", "has_close")

_STRENGTH_PREFIXES = ("home_strength", "away_strength", "strength_margin_diff")
_DEFAULT_TOP_K = 60
_DEFAULT_DRAWS = 4_000
_CORR_THRESHOLD = 0.95
_PBO_GATE = 0.2
_CALIB_TARGET = 0.80
# The small-N slice (the PM posterior-predictive nudge): games this early in the season order carry
# the widest strength posterior; the served distribution's calib floor is re-checked here so an
# early-season under-coverage can't hide behind the late-season-dominated aggregate.
_EARLY_SEASON_WEEKS = 3
# The strictest cold-start slice: week ≤ this = BOTH teams have ~0 in-season games (the strength
# model is purely on its pre-season prior — the P1.2 "sd ~6.7 in wk1" regime). Its interval MUST be
# honestly wide (that width is the correct answer, not a weakness).
_COLD_START_WEEK = 1
# An in-season efficiency feature that is NULL when a team has played no games yet — used to
# CONFIRM the cold-start CV never peeks at current-season data on a week-1 eval game.
_INSEASON_FEATURE = "home_off_ppa"
_SEED = 42

_T0 = time.time()


def _log(msg: str, *, indent: int = 0) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp} +{time.time() - _T0:6.0f}s] {'  ' * indent}{msg}", file=sys.stderr, flush=True)


class _Step:
    def __init__(self, msg: str, *, indent: int = 0):
        self.msg, self.indent = msg, indent

    def __enter__(self):
        self.t0 = time.time()
        _log(f"{self.msg} …", indent=self.indent)
        return self

    def __exit__(self, exc_type, exc, tb):
        tag = "✓" if exc_type is None else "✗ FAILED"
        _log(f"{self.msg} {tag} ({time.time() - self.t0:.1f}s)", indent=self.indent)
        return False


# ---------------------------------------------------------------------------
# Feature column resolution
# ---------------------------------------------------------------------------

def feature_columns(df: pd.DataFrame) -> list[str]:
    """Every model-eligible column: not an id / CV-axis / label / close column, and numeric or
    boolean (booleans are cast to 0/1 in `_prepare_matrix`)."""
    out = []
    for c in df.columns:
        if c in _ID_COLS or c.startswith(_LABEL_PREFIX) or c in _CLOSE_COLS:
            continue
        dt = str(df[c].dtype)
        if df[c].dtype == object or dt.startswith("category"):
            continue  # residual string identifiers (none expected after _ID_COLS)
        out.append(c)
    return out


def _is_strength(col: str) -> bool:
    return any(col.startswith(p) for p in _STRENGTH_PREFIXES)


# ---------------------------------------------------------------------------
# Stage 0 — one pull → cache (matrix + CLV odds staging join)
# ---------------------------------------------------------------------------

def load_matrix(source: str) -> pd.DataFrame:
    """Read the P1.3 pregame matrix ONCE. `parquet` = the cached artifact (default, offline);
    `s3` = the Delta at `ncaaf/derived/feature_pregame_matrix` via DuckDB."""
    if source == "s3":
        from quant_sports_intel_models.football.ncaaf.ingest.query_lake import q, delta
        df = q(f"select * from {delta('feature_pregame_matrix', tier='derived')}")
    else:
        if not _DEFAULT_MATRIX_PARQUET.exists():
            raise SystemExit(f"[{_STORY}] no cached matrix at {_DEFAULT_MATRIX_PARQUET}; run P1.3 "
                             "run_feature_matrix first, or pass --matrix-source s3.")
        df = pd.read_parquet(_DEFAULT_MATRIX_PARQUET)
    df[_DATE] = pd.to_datetime(df[_DATE], errors="coerce")
    return df


def build_clv_staging(min_year: int = 2020) -> pd.DataFrame:
    """The vs-market/CLV staging mart P1.4 OWNS: the leakage-safe CLOSING consensus line per game,
    keyed to the matrix `game_id`.

    Path (a CROSS-SOURCE join — verified by row-count, the P1.2b dead-bridge lesson):
      odds_ncaaf_historical (Odds-API team names, commence_time)
        ⋈  games   (season + CFBD team-name PREFIX match + kickoff proximity)  →  CFBD game id
      →  the CFBD id IS the matrix `game_id` (int).
    Only snapshots with `_snapshot_ts < commence_time` are eligible (leakage-safe close); per game
    we keep the LATEST such snapshot and take the cross-book MEDIAN home spread / total / home ML.
    """
    from quant_sports_intel_models.football.ncaaf.ingest.query_lake import q, delta
    O, G = delta("odds_ncaaf_historical"), delta("games")
    sql = f"""
    with snaps as (
        select json_extract_string(raw_json,'$.id')            as event_id,
               season,
               json_extract_string(raw_json,'$.home_team')     as odds_home,
               json_extract_string(raw_json,'$.away_team')     as odds_away,
               json_extract_string(raw_json,'$.commence_time') as commence,
               json_extract_string(raw_json,'$._snapshot_ts')  as snap_ts,
               raw_json
        from {O}
        where json_extract_string(raw_json,'$._snapshot_ts')
            < json_extract_string(raw_json,'$.commence_time')          -- leakage-safe close
          and season >= {int(min_year)}
    ),
    latest as (   -- the single latest pre-commence snapshot per event
        select *, row_number() over (partition by event_id order by snap_ts desc) rn from snaps
    ),
    close_snap as (select * from latest where rn = 1),
    -- unnest bookmakers → markets → outcomes and pull the home spread / over total / home ML
    quotes as (
        select cs.event_id, cs.season, cs.odds_home, cs.odds_away, cs.commence, cs.snap_ts,
               json_extract_string(mk,'$.key')                    as market,
               json_extract_string(oc,'$.name')                   as outcome_name,
               try_cast(json_extract_string(oc,'$.point') as double) as point,
               try_cast(json_extract_string(oc,'$.price') as double) as price
        from close_snap cs,
             unnest(cast(json_extract(cs.raw_json,'$.bookmakers') as json[])) as b(bm),
             unnest(cast(json_extract(bm,'$.markets')            as json[])) as m(mk),
             unnest(cast(json_extract(mk,'$.outcomes')           as json[])) as o(oc)
    ),
    consensus as (
        select event_id, any_value(season) season, any_value(odds_home) odds_home,
               any_value(odds_away) odds_away, any_value(commence) commence,
               any_value(snap_ts) snap_ts,
               median(point) filter (where market='spreads' and outcome_name = odds_home) as close_home_spread,
               median(point) filter (where market='totals'  and outcome_name = 'Over')    as close_total,
               median(price) filter (where market='h2h'     and outcome_name = odds_home) as close_home_ml_american
        from quotes group by event_id
    ),
    games as (
        select json_extract_string(raw_json,'$.id')::bigint season_game_id,
               json_extract_string(raw_json,'$.season')::int season,
               json_extract_string(raw_json,'$.homeTeam')   g_home,
               json_extract_string(raw_json,'$.awayTeam')   g_away
        from {G}
    )
    select g.season_game_id as game_id, c.close_home_spread, c.close_total,
           c.close_home_ml_american, c.snap_ts as close_snapshot_ts
    from consensus c
    join games g
      on g.season = c.season
     and c.odds_home like g.g_home || '%'
     and c.odds_away like g.g_away || '%'
    """
    clv = q(sql)
    # dedupe (a rare double-prefix match) — keep one row per game_id.
    clv = clv.dropna(subset=["game_id"]).drop_duplicates(subset=["game_id"], keep="first")
    clv["game_id"] = clv["game_id"].astype("int64")
    # American home ML → implied prob (vig-inclusive; the de-vig is a follow-on refinement).
    ml = clv["close_home_ml_american"]
    clv["close_home_ml_prob"] = np.where(
        ml < 0, (-ml) / ((-ml) + 100.0), np.where(ml > 0, 100.0 / (ml + 100.0), np.nan)
    )
    return clv


def assemble_cache(args) -> Path:
    print(f"=== {_STORY} stage 0 — assembling the game matrix (matrix + CLV close join) ===")
    t0 = time.time()
    df = load_matrix(args.matrix_source)
    df = df[df["label_is_completed"] == True].reset_index(drop=True)  # noqa: E712 — train on played
    df = df[df[_YEAR] >= args.min_year_train].reset_index(drop=True)
    df["game_year"] = df[_YEAR].astype(int)   # the splitter's year_col alias
    feat = feature_columns(df)
    assert_market_blind(feat, context=f"{_STORY} game matrix")
    print(f"  matrix: {len(df):,} completed games {int(df[_YEAR].min())}–{int(df[_YEAR].max())}  "
          f"| {len(feat)} features | market-blind ✅  ({time.time() - t0:.0f}s)")

    for c in _CLOSE_COLS:
        df[c] = np.nan
    df["has_close"] = False
    if not args.no_odds:
        try:
            t1 = time.time()
            clv = build_clv_staging(min_year=args.min_year_odds)
            n_match = int(df["game_id"].isin(clv["game_id"]).sum())
            df = df.drop(columns=[c for c in _CLOSE_COLS if c in df.columns])
            df = df.merge(clv, on="game_id", how="left")
            df["has_close"] = df["close_home_spread"].notna() | df["close_total"].notna()
            n_odds_2020 = int((df[_YEAR] >= args.min_year_odds).sum())
            print(f"  CLV staging: {len(clv):,} closes 2020+ | joined {n_match:,} of {n_odds_2020:,} "
                  f"games in the 2020+ window ({100.0*n_match/max(n_odds_2020,1):.1f}%)  "
                  f"({time.time() - t1:.0f}s)")
            print(f"    (expect < 100%: the 2 known P0.6 no-close FBS orphans + any non-matched drop)")
        except Exception as e:  # noqa: BLE001 — assemble is a laptop convenience; degrade loudly
            _log(f"[ALERT] CLV odds join skipped ({type(e).__name__}: {e}); outcome-only cache "
                 "written — re-run --assemble with AWS creds for the vs-market leg.")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_CACHE_PATH, index=False)
    _META_PATH.write_text(json.dumps({
        "story": _STORY, "assembled_at": date.today().isoformat(),
        "matrix_source": args.matrix_source, "n_games": int(len(df)),
        "seasons": sorted(int(y) for y in df[_YEAR].unique()),
        "n_features": len(feat), "feature_cols": feat,
        "n_with_close": int(df["has_close"].sum()),
        "margin_mean": round(float(df[_MARGIN].mean()), 3),
        "margin_std": round(float(df[_MARGIN].std()), 3),
        "total_mean": round(float(df[_TOTAL].mean()), 3),
        "total_std": round(float(df[_TOTAL].std()), 3),
    }, indent=2))
    print(f"  cache → {_CACHE_PATH.relative_to(_PROJECT_ROOT)}  "
          f"({_CACHE_PATH.stat().st_size / 1e6:.1f} MB, {int(df['has_close'].sum()):,} with close)")
    return _CACHE_PATH


def load_cache() -> tuple[pd.DataFrame, list[str], dict]:
    if not _CACHE_PATH.exists():
        raise SystemExit(f"[{_STORY}] no cache at {_CACHE_PATH}. Run `--assemble` first.")
    meta = json.loads(_META_PATH.read_text())
    return pd.read_parquet(_CACHE_PATH), list(meta["feature_cols"]), meta


# ---------------------------------------------------------------------------
# Candidate learners — each predicts (μ_margin, μ_total[, σ_margin, σ_total])
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    name: str
    fit_predict: Callable[..., tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]]
    native: bool = False
    params: dict[str, Any] = field(default_factory=dict)


def _ridge(params: dict | None = None) -> Candidate:
    p = {"alpha": 10.0}
    p.update(params or {})

    def fp(X_tr, y_m, y_t, X_ev):
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        sc = StandardScaler()
        Xtr, Xev = sc.fit_transform(X_tr), sc.transform(X_ev)
        mm = Ridge(**p).fit(Xtr, y_m)
        mt = Ridge(**p).fit(Xtr, y_t)
        return mm.predict(Xev), mt.predict(Xev), None, None

    return Candidate("ridge", fp, params=p)


def _lgbm(params: dict | None = None) -> Candidate:
    p = {"objective": "regression", "num_leaves": 31, "learning_rate": 0.03, "n_estimators": 400,
         "min_child_samples": 40, "subsample": 0.85, "subsample_freq": 1, "colsample_bytree": 0.85,
         "random_state": _SEED, "verbose": -1}
    p.update(params or {})

    def fp(X_tr, y_m, y_t, X_ev):
        import lightgbm as lgb
        mm = lgb.LGBMRegressor(**p).fit(X_tr, y_m)
        mt = lgb.LGBMRegressor(**p).fit(X_tr, y_t)
        return mm.predict(X_ev), mt.predict(X_ev), None, None

    return Candidate("lgbm", fp, params=p)


def _xgb(params: dict | None = None) -> Candidate:
    p = {"objective": "reg:squarederror", "max_depth": 5, "learning_rate": 0.03, "n_estimators": 400,
         "subsample": 0.85, "colsample_bytree": 0.85, "min_child_weight": 5.0, "reg_lambda": 1.0,
         "random_state": _SEED, "tree_method": "hist", "verbosity": 0}
    p.update(params or {})

    def fp(X_tr, y_m, y_t, X_ev):
        import xgboost as xgb
        mm = xgb.XGBRegressor(**p).fit(X_tr, y_m)
        mt = xgb.XGBRegressor(**p).fit(X_tr, y_t)
        return mm.predict(X_ev), mt.predict(X_ev), None, None

    return Candidate("xgb", fp, params=p)


def _catboost(params: dict | None = None) -> Candidate:
    p = {"loss_function": "RMSE", "depth": 6, "learning_rate": 0.03, "iterations": 600,
         "l2_leaf_reg": 3.0, "random_seed": _SEED, "verbose": False, "allow_writing_files": False}
    p.update(params or {})

    def fp(X_tr, y_m, y_t, X_ev):
        from catboost import CatBoostRegressor
        mm = CatBoostRegressor(**p).fit(X_tr, y_m)
        mt = CatBoostRegressor(**p).fit(X_tr, y_t)
        return mm.predict(X_ev), mt.predict(X_ev), None, None

    return Candidate("catboost", fp, params=p)


def _ngboost(params: dict | None = None) -> Candidate:
    """NATIVE per-game σ: NGBoost Normal emits (μ, σ) per game for BOTH margin and total — the
    heteroscedastic foil that could replace the held-out scalar σ with a learned per-game one."""
    p = {"n_estimators": 300, "learning_rate": 0.03, "minibatch_frac": 0.5, "random_state": _SEED}
    p.update(params or {})

    def fp(X_tr, y_m, y_t, X_ev):
        from ngboost import NGBRegressor
        from ngboost.distns import Normal
        out = []
        for y in (y_m, y_t):
            m = NGBRegressor(Dist=Normal, verbose=False, **p).fit(X_tr, y)
            d = m.pred_dist(X_ev)
            out.append((np.asarray(d.params["loc"], float), np.clip(np.asarray(d.params["scale"], float), 1e-6, None)))
        (mu_m, sd_m), (mu_t, sd_t) = out
        return mu_m, mu_t, sd_m, sd_t

    return Candidate("ngboost_normal", fp, native=True, params=p)


_BUILDERS: dict[str, Callable[[dict | None], Candidate]] = {
    "ridge": _ridge, "lgbm": _lgbm, "xgb": _xgb, "catboost": _catboost, "ngboost_normal": _ngboost,
}
MODEL_CLASSES: tuple[str, ...] = tuple(_BUILDERS)
CONTRACTS: tuple[str, ...] = ("full", "strength_only", "clustered", "top_k")

_N_JOBS: int | None = None
_THREAD_PARAM = {"lgbm": "n_jobs", "xgb": "n_jobs", "catboost": "thread_count"}


def set_n_jobs(n: int | None) -> None:
    global _N_JOBS
    _N_JOBS = n


def build_candidate(model_class: str, params: dict | None = None) -> Candidate:
    if model_class not in _BUILDERS:
        raise KeyError(f"unknown model class {model_class!r}; known: {sorted(_BUILDERS)}")
    merged = dict(params or {})
    if _N_JOBS is not None and model_class in _THREAD_PARAM:
        merged.setdefault(_THREAD_PARAM[model_class], _N_JOBS)
    return _BUILDERS[model_class](merged)


def default_form(model_class: str) -> str:
    return "native" if build_candidate(model_class).native else "gaussian"


# ---------------------------------------------------------------------------
# Matrix prep + feature contracts (in-fold, train rows only)
# ---------------------------------------------------------------------------

def _prepare_matrix(
    tr: pd.DataFrame, ev: pd.DataFrame, feat_cols: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bool→0/1, TRAIN-mean impute (fit on train only). Returns (X_tr, X_ev, train_means)."""
    def num(frame: pd.DataFrame) -> pd.DataFrame:
        # Everything to plain float64 (bool→0/1, nullable Int32/Int64→float with NaN) so the
        # TRAIN-mean impute below never hits a nullable dtype that rejects a float fill value.
        out = frame[feat_cols].copy()
        for c in feat_cols:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
        return out
    Xtr, Xev = num(tr), num(ev)
    means = Xtr.mean(numeric_only=True)
    Xtr = Xtr.fillna(means)
    Xev = Xev.fillna(means)
    return Xtr.to_numpy(float), Xev.to_numpy(float), means.to_numpy(float)


def infold_importance(X_tr: np.ndarray, y: np.ndarray, feat_cols: list[str]) -> list[str]:
    """Gain-importance ranking from ONE cheap LightGBM fit on TRAIN rows only (shared across
    contracts; never sees eval)."""
    import lightgbm as lgb
    m = lgb.LGBMRegressor(objective="regression", num_leaves=31, learning_rate=0.05,
                          n_estimators=200, min_child_samples=40, random_state=_SEED, verbose=-1)
    m.fit(X_tr, y)
    gains = np.asarray(m.booster_.feature_importance(importance_type="gain"), float)
    return [feat_cols[i] for i in np.argsort(-gains)]


def clustered_contract(X_tr: np.ndarray, feat_cols: list[str], ranking: list[str]) -> list[str]:
    idx = {c: i for i, c in enumerate(feat_cols)}
    Z = np.asarray(X_tr, float)
    std = Z.std(axis=0)
    kept, kept_idx = [], []
    for col in ranking:
        j = idx[col]
        if std[j] == 0:
            continue
        if kept_idx:
            a, block = Z[:, j], Z[:, kept_idx]
            with np.errstate(invalid="ignore", divide="ignore"):
                num = ((block - block.mean(0)) * (a - a.mean())[:, None]).mean(0)
                rho = num / (block.std(0) * a.std() + 1e-12)
            if np.nanmax(np.abs(rho)) >= _CORR_THRESHOLD:
                continue
        kept.append(col)
        kept_idx.append(j)
    return kept


def resolve_contract(contract: str, X_tr, feat_cols, ranking, *, top_k=_DEFAULT_TOP_K) -> list[str]:
    if contract == "full":
        return list(feat_cols)
    if contract == "strength_only":
        cols = [c for c in feat_cols if _is_strength(c)]
        return cols or list(feat_cols)   # never empty
    if contract == "top_k":
        return ranking[: min(top_k, len(ranking))]
    if contract == "clustered":
        return clustered_contract(X_tr, feat_cols, ranking)
    raise KeyError(f"unknown contract {contract!r}; known: {CONTRACTS}")


# ---------------------------------------------------------------------------
# Purged folds (season-forward; date-purged — season_order, never raw week)
# ---------------------------------------------------------------------------

# The P1.2 strength posterior sd columns → the per-game strength posterior VARIANCE the
# `strength_posterior` form propagates (home + away posteriors are independent, so their
# variances add). Used ONLY to set the predictive WIDTH — never as a mean feature.
_STRENGTH_SD_COLS = ("home_strength_margin_sd", "away_strength_margin_sd")


def strength_variance(frame: pd.DataFrame, impute: float | None = None) -> np.ndarray:
    """Per-game summed home/away strength posterior variance (σ²_home + σ²_away). NaN → `impute`
    (the TRAIN median, passed in) so the eval/holdout use a train-only fill (leakage-safe)."""
    sv = np.zeros(len(frame), dtype=float)
    for c in _STRENGTH_SD_COLS:
        s = pd.to_numeric(frame[c], errors="coerce") if c in frame.columns else pd.Series(np.nan, index=frame.index)
        if impute is not None:
            s = s.fillna(np.sqrt(max(impute, 0.0) / 2.0))
        sv = sv + np.nan_to_num(s.to_numpy(float)) ** 2
    return sv


@dataclass
class FoldMatrices:
    eval_year: int
    feat_cols: list[str]
    ranking: list[str]
    X_tr: np.ndarray
    y_m_tr: np.ndarray
    y_t_tr: np.ndarray
    X_ev: np.ndarray
    y_m_ev: np.ndarray
    y_t_ev: np.ndarray
    ev_meta: pd.DataFrame
    X_inner_tr: np.ndarray
    y_m_inner_tr: np.ndarray
    y_t_inner_tr: np.ndarray
    X_inner_ho: np.ndarray
    y_m_inner_ho: np.ndarray
    y_t_inner_ho: np.ndarray
    strength_var_ev: np.ndarray      # per eval game (strength_posterior form)
    strength_var_inner_ho: np.ndarray  # per inner-holdout game (fits σ0/k leakage-safe)


def build_folds(df: pd.DataFrame, feat_cols: list[str], *, max_folds: int | None = None) -> list[FoldMatrices]:
    """Season-forward purged walk-forward. The purge band is by CALENDAR DATE, so the ordering is
    monotone with `season_order_week` and the postseason `week`=1 collision can never leak."""
    df = df.sort_values([_YEAR, "season_order_week", _DATE]).reset_index(drop=True)
    with _Step("fold prologue: purged walk-forward split (season-forward, date-purged)"):
        splitter = PurgedWalkForwardSplit(min_train_seasons=3, year_col="game_year", date_col=_DATE)
        folds_idx = list(splitter.split(df, feature_cols=None))
    out: list[FoldMatrices] = []
    for train_idx, eval_idx in folds_idx:
        tr, ev = df.loc[train_idx], df.loc[eval_idx]
        eval_year = int(ev["game_year"].mode().iloc[0])
        _log(f"fold {eval_year}: {len(tr):,} train / {len(ev):,} eval", indent=1)
        with _Step(f"fold {eval_year}: impute matrix", indent=2):
            X_tr, X_ev, _ = _prepare_matrix(tr, ev, feat_cols)
        inner_year = int(tr["game_year"].max())
        inner_mask = (tr["game_year"] == inner_year).to_numpy()
        if inner_mask.sum() < 150 or (~inner_mask).sum() < 300:
            inner_mask = np.zeros(len(tr), dtype=bool)
            inner_mask[int(len(tr) * 0.85):] = True
        with _Step(f"fold {eval_year}: in-fold importance (LightGBM on margin)", indent=2):
            ranking = infold_importance(X_tr, tr[_MARGIN].to_numpy(float), feat_cols)
        sv_impute = float(np.nanmedian(strength_variance(tr)))   # TRAIN-median fill (leakage-safe)
        sv_ev = strength_variance(ev, impute=sv_impute)
        sv_tr = strength_variance(tr, impute=sv_impute)
        ev_meta = ev[["game_id", _DATE, "game_year", "season_order_week"]].reset_index(drop=True)
        ev_meta["strength_var"] = sv_ev
        out.append(FoldMatrices(
            eval_year=eval_year, feat_cols=feat_cols, ranking=ranking,
            X_tr=X_tr, y_m_tr=tr[_MARGIN].to_numpy(float), y_t_tr=tr[_TOTAL].to_numpy(float),
            X_ev=X_ev, y_m_ev=ev[_MARGIN].to_numpy(float), y_t_ev=ev[_TOTAL].to_numpy(float),
            ev_meta=ev_meta,
            X_inner_tr=X_tr[~inner_mask], y_m_inner_tr=tr[_MARGIN].to_numpy(float)[~inner_mask],
            y_t_inner_tr=tr[_TOTAL].to_numpy(float)[~inner_mask],
            X_inner_ho=X_tr[inner_mask], y_m_inner_ho=tr[_MARGIN].to_numpy(float)[inner_mask],
            y_t_inner_ho=tr[_TOTAL].to_numpy(float)[inner_mask],
            strength_var_ev=sv_ev, strength_var_inner_ho=sv_tr[inner_mask],
        ))
        if max_folds and len(out) >= max_folds:
            break
    return out


# ---------------------------------------------------------------------------
# Held-out dispersion under a form (inner holdout = last train season)
# ---------------------------------------------------------------------------

def _fit_dispersion(
    cand: Candidate, fold: FoldMatrices, cols_idx: np.ndarray, form: str,
    sigma_m_ev: np.ndarray | None, sigma_t_ev: np.ndarray | None,
) -> tuple[JointDispersion, dict[str, Any], np.ndarray | None, np.ndarray | None]:
    """σ/ρ/dof/r/k from INNER-HOLDOUT residuals (leakage-safe — inner holdout is inside train).
    Returns (disp, info, draw_sig_m, draw_sig_t): the per-game σ arrays the sampler consumes —
    `native` from the learner, `strength_posterior` from the propagated posterior, else None."""
    mu_m_ho, mu_t_ho, _, _ = cand.fit_predict(
        fold.X_inner_tr[:, cols_idx], fold.y_m_inner_tr, fold.y_t_inner_tr, fold.X_inner_ho[:, cols_idx]
    )
    rm = fold.y_m_inner_ho - mu_m_ho
    rt = fold.y_t_inner_ho - mu_t_ho
    g = fit_gaussian_dispersion(rm, rt)
    disp = JointDispersion(sigma_margin=g.sigma_margin, sigma_total=g.sigma_total, rho=g.rho)
    info: dict[str, Any] = {"sigma_margin": round(g.sigma_margin, 3),
                            "sigma_total": round(g.sigma_total, 3), "rho": round(g.rho, 3)}
    draw_sig_m = draw_sig_t = None
    if form == "student_t":
        disp.dof = fit_student_t_dof(rm, g.sigma_margin)
        info["dof"] = round(disp.dof, 2)
    elif form == "count":
        y_home = (fold.y_t_inner_ho + fold.y_m_inner_ho) / 2.0
        y_away = (fold.y_t_inner_ho - fold.y_m_inner_ho) / 2.0
        mu_home = np.clip((mu_t_ho + mu_m_ho) / 2.0, 0.5, None)
        mu_away = np.clip((mu_t_ho - mu_m_ho) / 2.0, 0.5, None)
        disp.r_home = fit_negbin_r(np.clip(y_home, 0, None), mu_home)
        disp.r_away = fit_negbin_r(np.clip(y_away, 0, None), mu_away)
        info["r_home"], info["r_away"] = round(disp.r_home, 1), round(disp.r_away, 1)
    elif form == "native":
        info["sigma_source"] = "per_game_native"
        draw_sig_m, draw_sig_t = sigma_m_ev, sigma_t_ev
    elif form == "strength_posterior":
        # E13.6-recalibrate the per-game strength-posterior propagation on inner-holdout residuals.
        sv_ho = fold.strength_var_inner_ho
        disp.sigma0_margin, disp.k_margin = fit_strength_posterior_scale(rm, sv_ho)
        disp.sigma0_total, disp.k_total = fit_strength_posterior_scale(rt, sv_ho)
        draw_sig_m = strength_posterior_sigma(disp.sigma0_margin, disp.k_margin, fold.strength_var_ev)
        draw_sig_t = strength_posterior_sigma(disp.sigma0_total, disp.k_total, fold.strength_var_ev)
        info.update({"sigma0_margin": round(disp.sigma0_margin, 3), "k_margin": round(disp.k_margin, 3),
                     "sigma0_total": round(disp.sigma0_total, 3), "k_total": round(disp.k_total, 3),
                     "sigma_margin_med": round(float(np.median(draw_sig_m)), 3)})
    return disp, info, draw_sig_m, draw_sig_t


def _draw(form, mu_m, mu_t, disp, rng, n_draws, sig_m=None, sig_t=None):
    m, t = draw_joint(form, mu_m, mu_t, disp, rng, n_draws=n_draws,
                      sigma_margin_native=sig_m, sigma_total_native=sig_t)
    return derive_markets(m, t), None


# ---------------------------------------------------------------------------
# Score ONE config across every fold
# ---------------------------------------------------------------------------

def evaluate_config(
    folds: list[FoldMatrices], model_class: str, contract: str, *,
    form: str | None = None, params: dict | None = None, top_k: int = _DEFAULT_TOP_K,
    n_draws: int = _DEFAULT_DRAWS, n_slices: int = 4, seed: int = _SEED,
) -> dict[str, Any]:
    cand = build_candidate(model_class, params)
    fm = form or default_form(model_class)
    if fm == "native" and not cand.native:
        fm = "gaussian"   # non-native learners have no per-game σ → gaussian is the scalar analog
    rng = np.random.default_rng(seed)
    cfg_id = f"{model_class}__{contract}__{fm}"

    fold_rows, bucket_scores, bucket_metrics = [], [], []
    pooled_margin, pooled_total, obs_margin, obs_total = [], [], [], []
    _log(f"CONFIG {cfg_id}  ({len(folds)} folds, {n_draws:,} draws)")
    for i, fold in enumerate(folds, start=1):
        t_fold = time.time()
        _log(f"[{i}/{len(folds)}] fold {fold.eval_year}", indent=1)
        cols = resolve_contract(contract, fold.X_tr, fold.feat_cols, fold.ranking, top_k=top_k)
        assert_market_blind(cols, context=f"{_STORY} {cfg_id} fold {fold.eval_year}")
        cols_idx = np.array([fold.feat_cols.index(c) for c in cols])

        with _Step(f"mean fit {model_class} on {len(fold.y_m_tr):,}×{len(cols)}", indent=2):
            mu_m, mu_t, sig_m, sig_t = cand.fit_predict(
                fold.X_tr[:, cols_idx], fold.y_m_tr, fold.y_t_tr, fold.X_ev[:, cols_idx])
        with _Step(f"dispersion '{fm}'", indent=2):
            disp, info, draw_sig_m, draw_sig_t = _fit_dispersion(cand, fold, cols_idx, fm, sig_m, sig_t)
            _log(f"disp → {info}", indent=3)

        dists, _ = _draw(fm, mu_m, mu_t, disp, rng, n_draws, draw_sig_m, draw_sig_t)
        obs = {"margin": fold.y_m_ev, "total": fold.y_t_ev, "home_win": (fold.y_m_ev > 0).astype(float)}
        metrics = score_calibration(dists, obs, rng)
        score = downstream_score(metrics)

        for sl in np.array_split(np.arange(len(fold.y_m_ev)), n_slices):
            if len(sl) < 40:
                continue
            bm = score_calibration(dists, obs, rng, rows=sl)
            bucket_scores.append(downstream_score(bm))
            bucket_metrics.append({j: dict(bm[j]) for j in SCORED_DISTS})

        pooled_margin.append(dists["margin"]); pooled_total.append(dists["total"])
        obs_margin.append(fold.y_m_ev); obs_total.append(fold.y_t_ev)
        _log(f"fold {fold.eval_year}: score {score:.5f}  calib80(margin) "
             f"{metrics['margin']['calib_80']:.3f} calib80(total) {metrics['total']['calib_80']:.3f}  "
             f"brier(h2h) {metrics['home_win']['brier']:.4f}  ({time.time() - t_fold:.0f}s)", indent=2)
        fold_rows.append({
            "eval_year": fold.eval_year, "n_games": int(len(fold.y_m_ev)),
            "downstream_score": round(score, 5),
            "margin_calib_80": metrics["margin"]["calib_80"], "total_calib_80": metrics["total"]["calib_80"],
            "margin_pit_maxdev": metrics["margin"]["pit_max_decile_dev"],
            "total_pit_maxdev": metrics["total"]["pit_max_decile_dev"],
            "h2h_brier": metrics["home_win"]["brier"], "n_features": len(cols), **info,
        })

    # pooled scoring over all folds (ragged draw arrays → score each dist on the stacked obs)
    pm = np.concatenate(pooled_margin); pt = np.concatenate(pooled_total)
    om = np.concatenate(obs_margin); ot = np.concatenate(obs_total)
    pooled_dists = {"margin": pm, "total": pt, "home_win": (pm > 0).astype(float)}
    pooled_obs = {"margin": om, "total": ot, "home_win": (om > 0).astype(float)}
    pooled_metrics = score_calibration(pooled_dists, pooled_obs, rng)

    return {
        "story": _STORY, "config_id": cfg_id, "model_class": model_class, "contract": contract,
        "form": fm, "params": cand.params, "top_k": top_k if contract == "top_k" else None,
        "is_reference": (model_class == _REF_LEARNER and contract == _REF_CONTRACT and fm == _REF_FORM),
        "folds": fold_rows,
        "mean_downstream_score": round(float(np.mean([f["downstream_score"] for f in fold_rows])), 5),
        "pooled_downstream_score": round(downstream_score(pooled_metrics), 5),
        "pooled_metrics": pooled_metrics,
        "mean_h2h_brier": round(float(np.mean([f["h2h_brier"] for f in fold_rows])), 4),
        "bucket_scores": [round(float(b), 5) for b in bucket_scores],
        "bucket_metrics": bucket_metrics, "n_buckets": len(bucket_scores),
        "passes_calibration_floor": passes_calibration_floor(pooled_metrics),
    }


def save_config_result(res: dict, tag: str = "") -> Path:
    _TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{res['config_id']}{('__' + tag) if tag else ''}.json".replace("/", "_")
    (_TRIALS_DIR / name).write_text(json.dumps(res, indent=2, default=float))
    return _TRIALS_DIR / name


def load_config_results() -> list[dict]:
    if not _TRIALS_DIR.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(_TRIALS_DIR.glob("*.json"))]


# ---------------------------------------------------------------------------
# Stage 1 — the bake-off
# ---------------------------------------------------------------------------

def stage_bakeoff(args) -> None:
    df, feat, meta = load_cache()
    print(f"=== {_STORY} stage 1 — BAKE-OFF ({len(df):,} games, {len(feat)} features) ===")
    folds = build_folds(df, feat, max_folds=args.max_folds)
    print(f"  purged folds: {[f.eval_year for f in folds]}")
    classes = [args.model_class] if args.model_class else list(MODEL_CLASSES)
    contracts = [args.contract] if args.contract else list(CONTRACTS)

    plan: list[tuple[str, str, str]] = [_REFERENCE]
    for mc in classes:
        for ct in contracts:
            # honour an explicit --form when the operator scopes a single config; else the
            # learner's default form (gaussian / native).
            e = (mc, ct, args.form or default_form(mc))
            if e not in plan:
                plan.append(e)
    # the distributional-form question: student_t / count on the strongest gradient learner, and
    # the POSTERIOR-PREDICTIVE `strength_posterior` form on BOTH the strength prior (the textbook
    # posterior-predictive) and the full-matrix learner (does propagating the per-game strength
    # posterior widen the thin-sample games enough to beat the homoscedastic gaussian on PIT?).
    if not args.model_class and not args.contract:
        for e in [("lgbm", "full", "student_t"), ("lgbm", "full", "count"),
                  ("ridge", "strength_only", "strength_posterior"),
                  ("lgbm", "full", "strength_posterior")]:
            if e not in plan:
                plan.append(e)

    print(f"  {len(plan)} configs to evaluate\n")
    for mc, ct, fm in plan:
        t0 = time.time()
        res = evaluate_config(folds, mc, ct, form=fm, top_k=args.top_k, n_draws=args.n_draws,
                              n_slices=args.n_slices, seed=args.seed)
        save_config_result(res, tag="bakeoff")
        flag = "  ← REFERENCE (strength prior)" if res["is_reference"] else ""
        print(f"  {res['config_id']:<40} score {res['pooled_downstream_score']:.4f}  "
              f"calib80(m/t) {res['pooled_metrics']['margin']['calib_80']:.3f}/"
              f"{res['pooled_metrics']['total']['calib_80']:.3f}  brier {res['mean_h2h_brier']:.4f}  "
              f"({time.time() - t0:.0f}s){flag}")
    _ = meta
    print(f"\n  configs → {_TRIALS_DIR.relative_to(_PROJECT_ROOT)}")
    print("  Next: `--stage optuna --model-class <class>` per class, then `--stage decide`.")


# ---------------------------------------------------------------------------
# Stage 2 — Optuna (one learner per invocation)
# ---------------------------------------------------------------------------

def _space(model_class: str, trial) -> dict:
    if model_class == "ridge":
        return {"alpha": trial.suggest_float("alpha", 0.1, 300.0, log=True)}
    if model_class == "lgbm":
        return {"num_leaves": trial.suggest_int("num_leaves", 15, 127),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 200, 1200, step=100),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 200, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 50.0, log=True),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 20.0, log=True)}
    if model_class == "xgb":
        return {"max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 200, 1200, step=100),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
                "min_child_weight": trial.suggest_float("min_child_weight", 0.5, 50.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 50.0, log=True)}
    if model_class == "catboost":
        return {"depth": trial.suggest_int("depth", 4, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "iterations": trial.suggest_int("iterations", 300, 1500, step=100),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 0.5, 30.0, log=True),
                "random_strength": trial.suggest_float("random_strength", 0.1, 10.0, log=True)}
    if model_class == "ngboost_normal":
        return {"n_estimators": trial.suggest_int("n_estimators", 150, 700, step=50),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.08, log=True),
                "minibatch_frac": trial.suggest_float("minibatch_frac", 0.3, 1.0)}
    raise KeyError(model_class)


def stage_optuna(args) -> None:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    mc = args.model_class
    if not mc:
        raise SystemExit("--stage optuna requires --model-class (one class per invocation)")
    df, feat, _ = load_cache()
    print(f"=== {_STORY} stage 2 — OPTUNA ({mc}, {args.n_trials} trials) ===")
    folds = build_folds(df, feat, max_folds=args.max_folds)
    contract = args.contract or "full"
    fm = args.form or default_form(mc)

    def objective(trial):
        res = evaluate_config(folds, mc, contract, form=fm, params=_space(mc, trial),
                              top_k=args.top_k, n_draws=args.n_draws, n_slices=args.n_slices, seed=args.seed)
        save_config_result(res, tag=f"optuna_t{trial.number:03d}")
        return res["pooled_downstream_score"]

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=args.n_trials, show_progress_bar=False)
    print(f"\n  best pooled downstream score: {study.best_value:.5f}")
    print(f"  best params: {json.dumps(study.best_params)}")
    print("  every trial persisted → it counts toward PBO/DSR at `--stage decide`.")


# ---------------------------------------------------------------------------
# Stage 3 — decide (deflated verdict; reuses pbo_cscv / deflated_sharpe)
# ---------------------------------------------------------------------------

def decide_verdict(results: list[dict], *, pbo_gate: float = _PBO_GATE) -> dict[str, Any]:
    reference = next((r for r in results if r.get("is_reference")), None)
    if reference is None:
        raise ValueError("no reference config present")

    def floor_ok(r):
        return bool(r.get("passes_calibration_floor", passes_calibration_floor(r["pooled_metrics"])))

    n_buckets = min(len(r["bucket_scores"]) for r in results)
    perf = np.array([r["bucket_scores"][:n_buckets] for r in results], float).T
    n_cfg = perf.shape[1]
    n_splits = min(16, n_buckets - (n_buckets % 2))
    full_pbo = float(pbo_cscv(perf, higher_is_better=False, n_splits=max(2, n_splits)).pbo)

    eligible = [r for r in results if floor_ok(r)]
    rejected = [r for r in results if not floor_ok(r)]
    ref_ok = floor_ok(reference)
    ref_buckets = np.array(reference["bucket_scores"][:n_buckets], float)

    best = min(eligible, key=lambda r: r["pooled_downstream_score"]) if eligible else None
    best_dsr, full_clean = 0.0, False
    if best is not None and best["config_id"] != reference["config_id"]:
        ch = np.array(best["bucket_scores"][:n_buckets], float)
        improvement = ref_buckets - ch                         # >0 ⇔ challenger better (lower)
        best_dsr = float(deflated_sharpe(improvement, n_trials=max(1, n_cfg), benchmark_sr=0.0).dsr)
        best_gain = reference["pooled_downstream_score"] - best["pooled_downstream_score"]
        full_clean = best_gain > 0 and full_pbo < pbo_gate and best_dsr > 0.0

    if full_clean:
        verdict, winner = "PROMOTE", best
    elif not ref_ok and best is not None and best["config_id"] != reference["config_id"]:
        verdict, winner = "FIX_REQUIRED", None
    else:
        verdict, winner = "REFERENCE_STANDS", None

    return {"verdict": verdict, "winner": winner, "reference": reference,
            "reference_passes_floor": ref_ok, "best": best, "full_pbo": round(full_pbo, 4),
            "best_dsr": round(best_dsr, 4), "n_configs": n_cfg, "n_buckets": n_buckets,
            "eligible": eligible, "rejected": rejected}


def stage_decide(args) -> None:
    results = load_config_results()
    if not results:
        raise SystemExit(f"[{_STORY}] no config results — run --stage bakeoff first.")
    if not any(r.get("is_reference") for r in results):
        raise SystemExit(f"[{_STORY}] the reference {'/'.join(_REFERENCE)} is missing — re-run bakeoff.")
    d = decide_verdict(results, pbo_gate=_PBO_GATE)
    ref, best, winner, verdict = d["reference"], d["best"], d["winner"], d["verdict"]
    gain = (ref["pooled_downstream_score"] - winner["pooled_downstream_score"]) if winner else 0.0

    print("=" * 80)
    print(f"{_STORY} DECISION — {d['n_configs']} configs, {d['n_buckets']} buckets")
    print("=" * 80)
    for r in sorted(d["eligible"], key=lambda r: r["pooled_downstream_score"])[:15]:
        marks = ("  ← REFERENCE" if r.get("is_reference") else "") + \
                ("  ★ WINNER" if winner and r["config_id"] == winner["config_id"] else "")
        print(f"  {r['pooled_downstream_score']:.5f}  {r['config_id']:<40} "
              f"calib80(m/t) {r['pooled_metrics']['margin']['calib_80']:.3f}/"
              f"{r['pooled_metrics']['total']['calib_80']:.3f}  brier {r.get('mean_h2h_brier', 0):.4f}{marks}")
    print(f"\n  reference : {ref['config_id']}  score {ref['pooled_downstream_score']:.5f}  "
          f"[calib floor {'PASS' if d['reference_passes_floor'] else 'FAIL'}]")
    if winner:
        print(f"  winner    : {winner['config_id']}  score {winner['pooled_downstream_score']:.5f}  (gain {gain:+.5f})")
    print(f"  full-search PBO : {d['full_pbo']:.3f} ({'PASS' if d['full_pbo'] < _PBO_GATE else 'FAIL'} < {_PBO_GATE})"
          " — high with a TIED field ⇒ a null; high with a WIDE spread ⇒ overfitting")
    print(f"  best DSR        : {d['best_dsr']:.3f} ({'PASS' if d['best_dsr'] > 0 else 'FAIL'} > 0)")
    print(f"\n  VERDICT   : {verdict}")
    _print_action(verdict, ref, winner)
    print("\n  Honest framing: a market-BLIND joint distribution is PRODUCT value, not an edge "
          "claim (best_alpha = 0). The vs-close CLV leg (--stage finalize) is the edge question.")

    def _slim(r):
        return None if r is None else {k: r.get(k) for k in
            ("config_id", "form", "params", "pooled_downstream_score", "pooled_metrics", "mean_h2h_brier")}

    doc = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "n_configs": d["n_configs"], "n_buckets": d["n_buckets"],
        "selection_metric": ("sum over {margin, total} of PIT max-decile-dev (lower better); "
                             "calib_80 ≥ 0.80 a FLOOR not a target (inclusive-integer coverage "
                             "is inflated — an oracle covers > 0.80); h2h Brier secondary"),
        "reference_config": "/".join(_REFERENCE), "verdict": verdict,
        "reference_passes_calibration_floor": d["reference_passes_floor"],
        "reference": _slim(ref), "best": _slim(best), "winner": _slim(winner),
        "gain_vs_reference": round(gain, 5), "full_search_pbo": d["full_pbo"], "best_dsr": d["best_dsr"],
        "gates": {"full_search_deflated": bool(d["full_pbo"] < _PBO_GATE and d["best_dsr"] > 0.0),
                  "market_blind": True},
        "leaderboard": [{"config_id": r["config_id"], "form": r.get("form"),
                         "score": r["pooled_downstream_score"],
                         "calib_80_margin": r["pooled_metrics"]["margin"]["calib_80"],
                         "calib_80_total": r["pooled_metrics"]["total"]["calib_80"],
                         "h2h_brier": r.get("mean_h2h_brier"),
                         "passes_floor": r.get("passes_calibration_floor",
                             passes_calibration_floor(r["pooled_metrics"]))}
                        for r in sorted(results, key=lambda x: x["pooled_downstream_score"])],
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _DECISION_JSON.write_text(json.dumps(doc, indent=2, default=float))
    _DECISION_MD.write_text(_render_md(doc))
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}\n  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")
    _ = args


def _print_action(verdict, ref, winner) -> None:
    if verdict == "PROMOTE" and winner:
        print(f"  → the full matrix BEATS the strength prior: the search cleanly identifies "
              f"`{winner['config_id']}`\n    (form={winner.get('form')}). Run `--stage finalize "
              "--model-class <winner> --contract <winner>\n    --form <winner>` → served joint "
              "distribution + PIT gate + the vs-close CLV eval.")
    elif verdict == "FIX_REQUIRED":
        print("  → the strength-prior REFERENCE fails the calib floor and no deflation-clean full-\n"
              "    matrix challenger was found — widen the form/Optuna search before finalizing.")
    else:  # REFERENCE_STANDS
        print("  → nothing robustly beats the strength prior under deflation ⇒ the full 180-feature\n"
              "    matrix does NOT earn its complexity here (a TRUSTWORTHY null). Finalize on the\n"
              "    reference — the calibrated strength-prior joint distribution is the honest ship.")


def _render_md(doc: dict) -> str:
    lines = [f"# {_STORY} — NCAAF game-model bake-off (H2H · spread · total from the joint distribution)",
             "", f"_Decided {doc['decided_at']} · {doc['n_configs']} configs · {doc['n_buckets']} CV buckets_",
             "", "## Verdict", "",
             f"**{doc['verdict']}**" + (
                 f" — winner `{doc['winner']['config_id']}` (form `{doc['winner']['form']}`) vs reference "
                 f"`{doc['reference']['config_id']}`, gain `{doc['gain_vs_reference']:+.5f}`."
                 if doc.get("winner") else
                 f" — the strength-prior reference `{doc['reference']['config_id']}` carries; the full "
                 "matrix does not robustly beat it."),
             "",
             f"- reference passes calib_80 floor: **{'YES' if doc['reference_passes_calibration_floor'] else 'NO'}**",
             f"- full-search PBO `{doc['full_search_pbo']:.3f}` "
             f"({'PASS' if doc['gates']['full_search_deflated'] else 'FAIL'} < 0.2)",
             f"- best DSR `{doc['best_dsr']:.3f}`",
             "", "## Selection metric", "", doc["selection_metric"], "",
             "## Leaderboard", "",
             "| config | form | score | calib_80 (margin) | calib_80 (total) | h2h Brier | floor |",
             "|---|---|---|---|---|---|---|"]
    for r in doc["leaderboard"][:30]:
        lines.append(f"| `{r['config_id']}` | {r['form']} | {r['score']:.5f} | {r['calib_80_margin']:.3f} | "
                     f"{r['calib_80_total']:.3f} | {r.get('h2h_brier', 0):.4f} | "
                     f"{'✅' if r.get('passes_floor', True) else '❌'} |")
    lines += ["", "## Honest framing", "",
              "A market-BLIND joint (margin, total) distribution is **product value** — calibrated "
              "H2H / spread / total probabilities — NOT an edge claim (`best_alpha = 0`). Whether it "
              "beats a closing line is the vs-close CLV leg (`--stage finalize`), 2020–2025, under "
              "PBO/DSR deflation. Market-blind CONTRACT-GUARD held on every contract.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 4 — finalize: served distribution + PIT gate + vs-close CLV eval
# ---------------------------------------------------------------------------

def _collect_oos(folds, mc, contract, fm, *, top_k, seed) -> pd.DataFrame:
    """Walk-forward OOS per-game (μ_margin, μ_total, realised, [σ]) for the chosen config."""
    cand = build_candidate(mc)
    rows = []
    for fold in folds:
        cols = resolve_contract(contract, fold.X_tr, fold.feat_cols, fold.ranking, top_k=top_k)
        assert_market_blind(cols, context=f"{_STORY} finalize {mc}/{contract}")
        cols_idx = np.array([fold.feat_cols.index(c) for c in cols])
        mu_m, mu_t, sig_m, sig_t = cand.fit_predict(
            fold.X_tr[:, cols_idx], fold.y_m_tr, fold.y_t_tr, fold.X_ev[:, cols_idx])
        d = fold.ev_meta.copy()
        d["mu_margin"], d["mu_total"] = mu_m, mu_t
        d["y_margin"], d["y_total"] = fold.y_m_ev, fold.y_t_ev
        d["season"] = fold.eval_year
        if sig_m is not None:
            d["sig_margin"], d["sig_total"] = sig_m, sig_t
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def _clv_eval(oos: pd.DataFrame, df: pd.DataFrame, dists: dict, rng) -> dict:
    """Historical vs-close eval (2020–2025 — the pre-season SHIP bar; forward-CLV accrues in-season).

    For every OOS game with a leakage-safe close, the model's derived P(cover)/P(over) picks a
    side; we measure the realised ATS / O/U hit-rate of the model's side vs the closing number, and
    a PLACEBO (a random side) to show the signal is not a mirage. Honest, deflation-aware — a hit
    rate near 50% is the expected null (best_alpha = 0)."""
    close = df[["game_id", "close_home_spread", "close_total", "has_close"]].drop_duplicates("game_id")
    m = oos.merge(close, on="game_id", how="left")
    m = m[m["has_close"] == True].reset_index(drop=True)  # noqa: E712
    out: dict[str, Any] = {"n_with_close": int(len(m))}
    if len(m) < 100:
        out["note"] = "too few closes for a stable vs-market read"
        return out
    idx = m.index.to_numpy()
    p_cover = (dists["margin"][idx] > (-m["close_home_spread"].to_numpy())[:, None]).mean(axis=1)
    ats_win = np.where(p_cover >= 0.5,
                       m["y_margin"].to_numpy() > -m["close_home_spread"].to_numpy(),
                       m["y_margin"].to_numpy() < -m["close_home_spread"].to_numpy())
    ats_push = m["y_margin"].to_numpy() == -m["close_home_spread"].to_numpy()
    p_over = (dists["total"][idx] > m["close_total"].to_numpy()[:, None]).mean(axis=1)
    ou_win = np.where(p_over >= 0.5, m["y_total"].to_numpy() > m["close_total"].to_numpy(),
                      m["y_total"].to_numpy() < m["close_total"].to_numpy())
    ou_push = m["y_total"].to_numpy() == m["close_total"].to_numpy()
    rand = rng.random(len(m)) >= 0.5
    ats_placebo = np.where(rand, m["y_margin"].to_numpy() > -m["close_home_spread"].to_numpy(),
                           m["y_margin"].to_numpy() < -m["close_home_spread"].to_numpy())
    out.update({
        "ats_hit_rate": round(float(ats_win[~ats_push].mean()), 4),
        "ats_n": int((~ats_push).sum()),
        "ats_placebo_hit_rate": round(float(ats_placebo[~ats_push].mean()), 4),
        "ou_hit_rate": round(float(ou_win[~ou_push].mean()), 4),
        "ou_n": int((~ou_push).sum()),
        "breakeven": 0.5238,  # -110 vig
        "note": ("historical vs-close hit rates; > 0.5238 clears the -110 vig. best_alpha=0 until "
                 "this beats breakeven AND the placebo under deflation, confirmed by a forward "
                 "in-season CLV window (post-kickoff, P0.6b-fed)."),
    })
    return out


def _interval_width(samples: np.ndarray) -> float:
    """Median per-game 80% predictive interval width (Q90 − Q10)."""
    return float(np.median(np.quantile(samples, 0.9, axis=1) - np.quantile(samples, 0.1, axis=1)))


def _early_season_validation(oos: pd.DataFrame, df: pd.DataFrame, dists: dict, obs: dict, rng) -> dict:
    """Validate the served distribution in the Week-1–3 cold-start regime SEPARATELY (the PM
    nudge): calib + PIT on early rows only, a week-1 wide-interval confirmation, and a cold-start
    no-peeking check (week-1 eval games must have NULL in-season efficiency features — the strength
    model is on its pre-season prior alone). Season-forward CV means a week-1 eval game is predicted
    from PRIOR-SEASON + PRE-SEASON data only, so this is the E13.7 cold-start analog by construction;
    this confirms it holds on the real build."""
    wk = oos["season_order_week"].to_numpy()
    early = wk <= _EARLY_SEASON_WEEKS
    out: dict[str, Any] = {"weeks": _EARLY_SEASON_WEEKS, "n": int(early.sum())}
    if early.sum() < 100:
        return out
    em = score_calibration({k: v[early] for k, v in dists.items()},
                           {k: v[early] for k, v in obs.items()}, rng)
    out["calib_80"] = {j: em[j]["calib_80"] for j in SCORED_DISTS}
    out["pit_max_decile_dev"] = {j: em[j]["pit_max_decile_dev"] for j in SCORED_DISTS}
    out["pit_is_flat"] = {j: bool(em[j]["pit_is_flat"]) for j in SCORED_DISTS}
    out["floor_ok"] = all(out["calib_80"][j] >= _CALIB_TARGET - 0.02 for j in SCORED_DISTS)

    w1, late = wk <= _COLD_START_WEEK, wk >= 8
    mw1, mlate = _interval_width(dists["margin"][w1]), _interval_width(dists["margin"][late])
    out["wk1_interval"] = {"margin_wk1": mw1, "margin_late": mlate,
                           "margin_ratio": round(mw1 / mlate, 3) if mlate else None,
                           "n_wk1": int(w1.sum())}
    # cold-start no-peeking confirmation: week-1 eval games should have NULL in-season efficiency.
    if _INSEASON_FEATURE in df.columns:
        w1_ids = set(oos.loc[w1, "game_id"])
        sub = df[df["game_id"].isin(w1_ids)]
        null_frac = float(pd.to_numeric(sub[_INSEASON_FEATURE], errors="coerce").isna().mean()) if len(sub) else 0.0
        out["cold_start_null_frac"] = round(null_frac, 3)
        out["cold_start_ok"] = null_frac >= 0.90
    else:
        out["cold_start_null_frac"], out["cold_start_ok"] = None, True
    return out


def stage_finalize(args) -> None:
    df, feat, meta = load_cache()
    mc = args.model_class or _REF_LEARNER
    contract = args.contract or _REF_CONTRACT
    fm = args.form or _REF_FORM
    print(f"=== {_STORY} stage 4 — FINALIZE ({mc} / {contract} / form={fm}) ===")
    folds = build_folds(df, feat, max_folds=args.max_folds)
    oos = _collect_oos(folds, mc, contract, fm, top_k=args.top_k, seed=args.seed)
    print(f"  OOS: {len(oos):,} games, seasons {sorted(int(s) for s in oos['season'].unique())}")

    rm = (oos["y_margin"] - oos["mu_margin"]).to_numpy()
    rt = (oos["y_total"] - oos["mu_total"]).to_numpy()
    g = fit_gaussian_dispersion(rm, rt)
    disp = JointDispersion(sigma_margin=g.sigma_margin, sigma_total=g.sigma_total, rho=g.rho)
    draw_sig_m = draw_sig_t = None
    if fm == "student_t":
        disp.dof = fit_student_t_dof(rm, g.sigma_margin)
    elif fm == "count":
        y_home = ((oos["y_total"] + oos["y_margin"]) / 2.0).to_numpy()
        y_away = ((oos["y_total"] - oos["y_margin"]) / 2.0).to_numpy()
        mu_home = np.clip(((oos["mu_total"] + oos["mu_margin"]) / 2.0).to_numpy(), 0.5, None)
        mu_away = np.clip(((oos["mu_total"] - oos["mu_margin"]) / 2.0).to_numpy(), 0.5, None)
        disp.r_home = fit_negbin_r(np.clip(y_home, 0, None), mu_home)
        disp.r_away = fit_negbin_r(np.clip(y_away, 0, None), mu_away)
    elif fm == "native":
        draw_sig_m = oos["sig_margin"].to_numpy() if "sig_margin" in oos else None
        draw_sig_t = oos["sig_total"].to_numpy() if "sig_total" in oos else None
    elif fm == "strength_posterior":
        sv = oos["strength_var"].to_numpy(float)
        disp.sigma0_margin, disp.k_margin = fit_strength_posterior_scale(rm, sv)
        disp.sigma0_total, disp.k_total = fit_strength_posterior_scale(rt, sv)
        draw_sig_m = strength_posterior_sigma(disp.sigma0_margin, disp.k_margin, sv)
        draw_sig_t = strength_posterior_sigma(disp.sigma0_total, disp.k_total, sv)
        print(f"  strength-posterior propagation: margin σ0={disp.sigma0_margin:.2f} k={disp.k_margin:.3f}"
              f" | total σ0={disp.sigma0_total:.2f} k={disp.k_total:.3f}  "
              f"(per-game σ_margin {np.percentile(draw_sig_m, 10):.1f}→{np.percentile(draw_sig_m, 90):.1f})")
    print(f"  served dispersion: σ_margin={disp.sigma_margin:.2f} σ_total={disp.sigma_total:.2f} "
          f"ρ={disp.rho:.3f} dof={disp.dof:.1f} r=({disp.r_home:.0f},{disp.r_away:.0f})  (form {fm})")

    rng = np.random.default_rng(args.seed)
    m_s, t_s = draw_joint(fm, oos["mu_margin"].to_numpy(), oos["mu_total"].to_numpy(), disp, rng,
                          n_draws=args.n_draws, sigma_margin_native=draw_sig_m,
                          sigma_total_native=draw_sig_t)
    dists = derive_markets(m_s, t_s)
    obs = {"margin": oos["y_margin"].to_numpy(float), "total": oos["y_total"].to_numpy(float),
           "home_win": (oos["y_margin"].to_numpy() > 0).astype(float)}
    metrics = score_calibration(dists, obs, rng)
    floor_ok = passes_calibration_floor(metrics)
    pit_ok = all(metrics[j]["pit_is_flat"] for j in SCORED_DISTS)
    print("\n  ── joint-distribution gate (pooled OOS) ──")
    for j in SCORED_DISTS:
        print(f"    {j:<7} calib_80 {metrics[j]['calib_80']:.3f}  PITdev {metrics[j]['pit_max_decile_dev']:.4f}"
              f"  flat {metrics[j]['pit_is_flat']}")
    print(f"    home_win Brier {metrics['home_win']['brier']:.4f}  (pred {metrics['home_win']['pred_rate']:.3f}"
          f" vs obs {metrics['home_win']['obs_rate']:.3f})")
    print(f"  calib floor (≥{_CALIB_TARGET}): {'PASS ✅' if floor_ok else 'FAIL ❌'}  |  "
          f"PIT-flat: {'PASS ✅' if pit_ok else 'FAIL ❌'}")

    # ⭐ EARLY-SEASON / COLD-START VALIDATION (the PM Week-1 nudge): Week 1–3 is a DIFFERENT
    # feature regime (priors-heavy, in-season efficiency NULL) and a season-averaged calibration
    # HIDES its quality (the aggregate is dominated by the many late-season games). So the served
    # distribution is validated SEPARATELY on the early-season slice — PIT + calib as a FLOOR — and
    # the week-1 interval is confirmed honestly WIDE (that width is the correct cold-start answer).
    early_val = _early_season_validation(oos, df, dists, obs, rng)
    if early_val.get("n"):
        c = early_val["calib_80"]
        print(f"\n  ── early-season / cold-start validation (season_order_week ≤ {_EARLY_SEASON_WEEKS}, "
              f"n={early_val['n']}) ──")
        print(f"    calib_80 margin {c['margin']:.3f} / total {c['total']:.3f}  "
              f"PIT-flat margin {early_val['pit_is_flat']['margin']} / total {early_val['pit_is_flat']['total']}  "
              f"→ early floor {'PASS ✅' if early_val['floor_ok'] else 'FAIL ❌ (understates thin-sample uncertainty)'}")
        w = early_val["wk1_interval"]
        print(f"    week-{_COLD_START_WEEK} 80% interval width — margin {w['margin_wk1']:.1f} vs "
              f"late-season {w['margin_late']:.1f} (×{w['margin_ratio']:.2f})  |  cold-start rows with "
              f"in-season features NULL: {early_val['cold_start_null_frac']:.0%} "
              f"({'✅ no current-season peeking' if early_val['cold_start_ok'] else '⚠ check leakage'})")

    clv = _clv_eval(oos, df, dists, rng)
    print("\n  ── vs-close CLV eval (2020–2025 historical; best_alpha=0 until it clears) ──")
    if clv.get("ats_n"):
        print(f"    ATS: model-side hit {clv['ats_hit_rate']:.3f} (n={clv['ats_n']}, placebo "
              f"{clv['ats_placebo_hit_rate']:.3f}, breakeven {clv['breakeven']})")
        print(f"    O/U: model-side hit {clv['ou_hit_rate']:.3f} (n={clv['ou_n']})")
    else:
        print(f"    {clv.get('note', 'no closes joined — re-run --assemble with AWS creds')}")

    params = NcaafGameDistributionParams(
        form=fm, sigma_margin=disp.sigma_margin, sigma_total=disp.sigma_total, rho=disp.rho,
        dof=disp.dof, r_home=disp.r_home, r_away=disp.r_away,
        sigma0_margin=disp.sigma0_margin, k_margin=disp.k_margin,
        sigma0_total=disp.sigma0_total, k_total=disp.k_total, learner=mc, contract=contract,
        n_draws=10_000,
        notes=(f"NCAAF P1.4 joint (margin,total) distribution. learner={mc} contract={contract}. "
               "Held-out σ/ρ/dof/k calibrated on pooled OOS residuals (E13.6). For form="
               "strength_posterior the per-game σ propagates the P1.2 strength posterior "
               "(σ_g²=σ0²+k²·[home_sd²+away_sd²]); μ from the mean artifact at score time. "
               "Market-blind; best_alpha=0."))
    calib_doc = {"story": _STORY, "fit_at": date.today().isoformat(), "model_class": mc,
                 "contract": contract, "form": fm, "n_oos_games": int(len(oos)),
                 "served_params": params.to_dict(), "gate": metrics,
                 "early_season_validation": early_val, "early_season_weeks": _EARLY_SEASON_WEEKS,
                 "gate_pass": {"calib_floor": floor_ok, "pit_flat": pit_ok,
                               "early_season_floor": early_val.get("floor_ok"),
                               "cold_start_no_peek": early_val.get("cold_start_ok")},
                 "clv_eval": clv, "market_blind": True}
    if args.no_save:
        print("\n[--no-save] skipping artifact + calibration write.")
        return
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _SERVED_JSON.write_text(json.dumps(params.to_dict(), indent=2))
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _CALIB_JSON.write_text(json.dumps(calib_doc, indent=2, default=float))
    _CALIB_MD.write_text(_render_calib_md(calib_doc))
    print(f"\n  served params → {_SERVED_JSON.relative_to(_PROJECT_ROOT)}")
    print(f"  calibration   → {_CALIB_JSON.relative_to(_PROJECT_ROOT)}")
    _ = meta


def _render_calib_md(doc: dict) -> str:
    g, clv = doc["gate"], doc.get("clv_eval", {})
    lines = [f"# {_STORY} — served NCAAF joint game distribution (calibration)", "",
             f"_Fit {doc['fit_at']} · learner `{doc['model_class']}` · contract `{doc['contract']}` · "
             f"form `{doc['form']}` · {doc['n_oos_games']:,} OOS games_", "", "## Served contract", "",
             f"- form **{doc['form']}** · σ_margin `{doc['served_params']['sigma_margin']}` · "
             f"σ_total `{doc['served_params']['sigma_total']}` · ρ `{doc['served_params']['rho']}` · "
             f"dof `{doc['served_params']['dof']}`", "", "## Distribution gate (pooled OOS)", "",
             "| dist | calib_80 | PIT max-decile-dev | PIT-flat |", "|---|---|---|---|"]
    for j in SCORED_DISTS:
        lines.append(f"| {j} | {g[j]['calib_80']:.3f} | {g[j]['pit_max_decile_dev']:.4f} | "
                     f"{'✅' if g[j]['pit_is_flat'] else '❌'} |")
    lines += ["", f"**calib floor:** {'PASS ✅' if doc['gate_pass']['calib_floor'] else 'FAIL ❌'} · "
              f"**PIT-flat:** {'PASS ✅' if doc['gate_pass']['pit_flat'] else 'FAIL ❌'} · "
              f"**H2H Brier** {g['home_win']['brier']:.4f}", ""]

    ev = doc.get("early_season_validation", {})
    if ev.get("n"):
        c, w = ev["calib_80"], ev.get("wk1_interval", {})
        lines += [f"## Early-season / cold-start validation (season_order_week ≤ {ev['weeks']}, n={ev['n']})", "",
                  "Week 1–3 is a priors-heavy regime (in-season efficiency NULL) whose quality the "
                  "season-averaged aggregate HIDES; validated separately as a FLOOR. Season-forward CV "
                  "predicts a week-1 game from PRIOR-SEASON + PRE-SEASON data only (the E13.7 cold-start "
                  "analog), confirmed below.", "",
                  f"- calib_80 — margin **{c['margin']:.3f}** / total **{c['total']:.3f}** · early floor "
                  f"**{'PASS ✅' if ev['floor_ok'] else 'FAIL ❌'}** · PIT-flat margin "
                  f"{ev['pit_is_flat']['margin']}",
                  f"- week-1 80% interval width — margin "
                  f"**{w.get('margin_wk1', 0):.1f}** vs late-season {w.get('margin_late', 0):.1f} "
                  f"(×{w.get('margin_ratio')}) — honestly WIDER when both teams have 0 in-season games",
                  f"- cold-start no-peek: {ev.get('cold_start_null_frac', 0):.0%} of week-1 eval games "
                  f"carry NULL in-season features "
                  f"**{'✅ no current-season leakage' if ev.get('cold_start_ok') else '⚠'}**", ""]

    lines += ["## Downstream season-simulation interface (P1.5 futures — do NOT collapse the output)", "",
              "`ncaaf_game_predictor.sample_matchup(...)` exposes the joint predictive for P1.5's "
              "NC/conference-title Monte-Carlo. ⭐ The width DECOMPOSES: `σ_g² = σ₀² + k²·(home_sd² + "
              "away_sd²)` — irreducible game noise + the strength posterior. A season sim draws each "
              "team's strength ONCE per simulated season (from the P1.2 `ncaaf_team_strength_week` "
              "posterior) and reuses it across the schedule, so it must call `sample_matchup(..., "
              "fixed_strength=True)` (σ₀ only) to avoid DOUBLE-COUNTING the strength uncertainty. The "
              "served params carry σ₀ and k separately for exactly this.", "",
              "## vs-close CLV (2020–2025 historical)", ""]
    if clv.get("ats_n"):
        lines += [f"- ATS model-side hit **{clv['ats_hit_rate']:.3f}** (n={clv['ats_n']}, placebo "
                  f"{clv['ats_placebo_hit_rate']:.3f}, breakeven {clv['breakeven']})",
                  f"- O/U model-side hit **{clv['ou_hit_rate']:.3f}** (n={clv['ou_n']})", "", clv["note"], ""]
    else:
        lines += [f"- {clv.get('note', 'no closes joined')}", ""]
    lines += ["## Honest framing", "",
              "Market-BLIND joint distribution = product value (calibrated 3-market probabilities), "
              "NOT an edge claim (`best_alpha = 0`). A hit rate near 50% is the expected null; a real "
              "edge needs > breakeven AND > placebo under deflation, confirmed in-season by forward "
              "CLV (which cannot exist pre-season).", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=f"Story {_STORY} — NCAAF game-model bake-off")
    ap.add_argument("--assemble", action="store_true", help="Stage 0: one pull → cache (matrix + CLV join).")
    ap.add_argument("--stage", choices=["bakeoff", "optuna", "decide", "finalize"])
    ap.add_argument("--matrix-source", choices=["parquet", "s3"], default="parquet")
    ap.add_argument("--no-odds", action="store_true", help="assemble: skip the CLV odds join (offline).")
    ap.add_argument("--min-year-train", type=int, default=2015, help="feature floor (P1.2 emits 2015+).")
    ap.add_argument("--min-year-odds", type=int, default=2020, help="odds floor (P0.6).")
    ap.add_argument("--model-class", choices=list(MODEL_CLASSES))
    ap.add_argument("--contract", choices=list(CONTRACTS))
    ap.add_argument("--form", choices=list(FORMS))
    ap.add_argument("--top-k", type=int, default=_DEFAULT_TOP_K)
    ap.add_argument("--n-trials", type=int, default=30)
    ap.add_argument("--n-draws", type=int, default=_DEFAULT_DRAWS)
    ap.add_argument("--n-slices", type=int, default=4)
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--n-jobs", type=int, default=None)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--seed", type=int, default=_SEED)
    args = ap.parse_args()

    set_n_jobs(args.n_jobs)
    _log(f"{_STORY} start · stage={args.stage or 'assemble'} · pid={os.getpid()} · BLAS cap={_THREAD_CAP or 'default'}")
    if args.assemble:
        assemble_cache(args)
    elif args.stage == "bakeoff":
        stage_bakeoff(args)
    elif args.stage == "optuna":
        stage_optuna(args)
    elif args.stage == "decide":
        stage_decide(args)
    elif args.stage == "finalize":
        stage_finalize(args)
    else:
        ap.error("pass --assemble or --stage {bakeoff,optuna,decide,finalize}")


if __name__ == "__main__":
    main()
