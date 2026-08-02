"""Epic 1 / Story 1.6 — Backfill daily_model_predictions with market-blind v2 rows.

Loads the 2024+ feature store in one batch, runs all three promoted market-blind
models, and writes one row per game to baseball_data.betting_ml.daily_model_predictions.
score_date and game_date are set from the actual game date in the feature store, not
from today — so the backfill covers the true starting and ending dates of each season.

Idempotent: existing (game_pk, model_version, retrain_tag) tuples are skipped.

Usage
-----
    # Dry-run — validate row format for 2026 games only
    uv run python betting_ml/scripts/backfill_predictions.py --dry-run --start-year 2026

    # Full backfill for 2024-2026
    uv run python betting_ml/scripts/backfill_predictions.py --start-year 2024
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.model_io import load_model
from betting_ml.utils.probability_layer import compute_edge, compute_posterior, compute_kelly
from betting_ml.models.total_runs_trainer import p_over_line

_MODELS = PROJECT_ROOT / "betting_ml" / "models"
_REGISTRY_PATH = _MODELS / "model_registry.yaml"
_CALIBRATOR_PATH = _MODELS / "home_win" / "calibrator.joblib"

_ML_SCHEMA = "baseball_data.betting_ml"
_RETRAIN_TAG = "market_blind_epic1"
_PREDICTION_TYPE = "backfill"
_BATCH_SIZE = 500


_ALTER_RETRAIN_TAG = f"""
ALTER TABLE {_ML_SCHEMA}.daily_model_predictions
ADD COLUMN IF NOT EXISTS retrain_tag VARCHAR(50)
"""

# Story 30.7: explicit, non-overloaded provenance flag (TRUE for backfilled rows).
# MH2.1 — per-target totals champion stamp (additive; `model_version` keeps its prior meaning).
_ALTER_TOTALS_MODEL_VERSION = f"""
ALTER TABLE {_ML_SCHEMA}.daily_model_predictions
ADD COLUMN IF NOT EXISTS totals_model_version VARCHAR(20)
"""

_ALTER_IS_BACKFILL = f"""
ALTER TABLE {_ML_SCHEMA}.daily_model_predictions
ADD COLUMN IF NOT EXISTS is_backfill BOOLEAN DEFAULT FALSE
"""

_INSERT_ROW = f"""
INSERT INTO {_ML_SCHEMA}.daily_model_predictions (
    model_version, inserted_at, score_date, prediction_type, retrain_tag, is_backfill,
    game_pk, game_date, game_datetime,
    home_team, away_team, home_team_abbrev, away_team_abbrev,
    has_odds,
    p_home_win_ngboost, p_home_win_classifier, consensus_win_prob, calibrated_win_prob, pick,
    pred_total_runs, pred_total_runs_scale,
    pred_run_diff_loc, pred_run_diff_scale,
    p_over_ngboost,
    alpha,
    h2h_market_implied_prob, h2h_posterior_prob, h2h_edge, h2h_kelly_fraction,
    total_line_consensus, over_prob_consensus,
    totals_model_prob, totals_posterior_prob, totals_edge, totals_kelly_fraction,
    totals_model_version
) VALUES (
    %(model_version)s, %(inserted_at)s, %(score_date)s, %(prediction_type)s, %(retrain_tag)s, %(is_backfill)s,
    %(game_pk)s, %(game_date)s, %(game_datetime)s,
    %(home_team)s, %(away_team)s, %(home_team_abbrev)s, %(away_team_abbrev)s,
    %(has_odds)s,
    %(p_home_win_ngboost)s, %(p_home_win_classifier)s, %(consensus_win_prob)s,
    %(calibrated_win_prob)s, %(pick)s,
    %(pred_total_runs)s, %(pred_total_runs_scale)s,
    %(pred_run_diff_loc)s, %(pred_run_diff_scale)s,
    %(p_over_ngboost)s,
    %(alpha)s,
    %(h2h_market_implied_prob)s, %(h2h_posterior_prob)s, %(h2h_edge)s, %(h2h_kelly_fraction)s,
    %(total_line_consensus)s, %(over_prob_consensus)s,
    %(totals_model_prob)s, %(totals_posterior_prob)s, %(totals_edge)s, %(totals_kelly_fraction)s,
    %(totals_model_version)s
)
"""


def _load_calibrator():
    if _CALIBRATOR_PATH.exists():
        return joblib.load(_CALIBRATOR_PATH)
    print("[WARN] calibrator.joblib not found — using raw consensus_win_prob")
    return None


def _apply_calibrator(calibrator, consensus_win_prob: float) -> float:
    if calibrator is not None:
        raw = np.array([consensus_win_prob])
        try:
            return float(calibrator.predict_proba(raw.reshape(-1, 1))[0, 1])
        except AttributeError:
            return float(calibrator.predict(raw)[0])
    return consensus_win_prob


def _load_best_alpha() -> float:
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT alpha FROM baseball_data.betting_ml.alpha_tuning_results "
                "ORDER BY loaded_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is not None:
                return float(row[0])
            print("[WARN] alpha_tuning_results is empty; trying local cache")
        finally:
            conn.close()
    except Exception as exc:
        print(f"[WARN] Could not load alpha from Snowflake ({exc}); trying local cache")

    cache = PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
    if cache.exists():
        return float(json.loads(cache.read_text())["best_alpha"])

    print("[WARN] best_alpha.json not found; using 0.5")
    return 0.5


def _infer_prev_version(artifact_path: str) -> str:
    """Best-effort version label for a previous champion, from its artifact filename.

    Only used when the registry carries no explicit `prev_model_version`. Deliberately returns a
    clearly-provisional string rather than guessing a clean 'vN': a WRONG version stamp is worse
    than an obviously-approximate one, because it would silently merge this backfill's rows with a
    real champion's in any group-by.
    """
    stem = artifact_path.rsplit("/", 1)[-1].removesuffix(".pkl")
    for token in stem.split("_"):
        if len(token) > 1 and token[0] == "v" and token[1:].isdigit():
            return token
    return f"prev:{stem[:14]}"


def _get_existing_game_pks(model_version: str, retrain_tag: str = _RETRAIN_TAG) -> set[int]:
    """Rows already written for this (model_version, retrain_tag).

    ⚠️ MH2.1 — `retrain_tag` MUST be parameterised. The idempotency key is
    (game_pk, model_version, retrain_tag), and `model_version` is the home_win-derived BUNDLE
    stamp, which a totals-only champion swap does NOT move. With the tag hardcoded, an MH2.1
    backtest would match the E13.11-era rows on BOTH key parts and be skipped as "already
    backfilled" — writing nothing, silently, and reporting success.
    """
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT DISTINCT game_pk FROM {_ML_SCHEMA}.daily_model_predictions "
                "WHERE model_version = %s AND retrain_tag = %s",
                (model_version, retrain_tag),
            )
            return {int(row[0]) for row in cur.fetchall() if row[0] is not None}
        finally:
            conn.close()
    except Exception as exc:
        print(f"[WARN] Could not query existing game_pks ({exc}); will insert all rows")
        return set()


def _sanitize(row: dict) -> dict:
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()}


def _col(df: pd.DataFrame, col: str, i: int):
    if col not in df.columns:
        return None
    v = df.iloc[i][col]
    if pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


def _to_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if hasattr(val, "date"):
        return val.date()
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


def _build_rows(
    df: pd.DataFrame,
    model_version: str,
    totals_model_version: str,
    retrain_tag: str,
    p_hw_ngb: np.ndarray,
    p_hw_clf: np.ndarray,
    loc_tot: np.ndarray,
    scale_tot: np.ndarray,
    loc_diff: np.ndarray,
    scale_diff: np.ndarray,
    p_over_tot: np.ndarray,
    total_line_vals: np.ndarray,
    best_alpha: float,
    calibrator,
    inserted_at: datetime,
) -> list[dict]:
    rows = []
    for i in range(len(df)):
        game_date_val = _to_date(_col(df, "game_date", i))
        if game_date_val is None:
            continue

        ngb_win = float(p_hw_ngb[i])
        clf_win = float(p_hw_clf[i])
        cons_win = ngb_win * 0.5 + clf_win * 0.5
        cal_win = _apply_calibrator(calibrator, cons_win)

        if cal_win >= 0.55:
            pick = f"HOME ({cal_win*100:.0f}%)"
        elif cal_win <= 0.45:
            pick = f"AWAY ({(1-cal_win)*100:.0f}%)"
        elif cal_win > 0.50:
            pick = f"TOSS-UP (lean HOME {cal_win*100:.0f}%)"
        elif cal_win < 0.50:
            pick = f"TOSS-UP (lean AWAY {(1-cal_win)*100:.0f}%)"
        else:
            pick = "EVEN"

        h2h_mkt_v = _col(df, "home_win_prob_consensus", i)
        h2h_mkt_v = float(h2h_mkt_v) if h2h_mkt_v is not None else None
        over_mkt_v = _col(df, "over_prob_consensus", i)
        over_mkt_v = float(over_mkt_v) if over_mkt_v is not None else None
        tl = total_line_vals[i]
        total_line_v = float(tl) if not np.isnan(tl) else None

        has_odds = h2h_mkt_v is not None

        if has_odds:
            h2h_edge = compute_edge(cal_win, h2h_mkt_v)
            h2h_post = compute_posterior(cal_win, h2h_mkt_v, best_alpha)
            h2h_kelly = compute_kelly(h2h_edge, h2h_mkt_v)
        else:
            h2h_edge = h2h_post = h2h_kelly = None

        p_over_v = float(p_over_tot[i])
        if has_odds and over_mkt_v is not None:
            tot_edge = compute_edge(p_over_v, over_mkt_v)
            tot_post = compute_posterior(p_over_v, over_mkt_v, best_alpha)
            tot_kelly = compute_kelly(tot_edge, over_mkt_v)
        else:
            tot_edge = tot_post = tot_kelly = None

        home_team = _col(df, "home_team", i)
        away_team = _col(df, "away_team", i)

        rows.append(_sanitize({
            "model_version":          model_version,
            "totals_model_version":   totals_model_version,   # MH2.1 — per-target totals champion
            "inserted_at":            inserted_at,
            "score_date":             game_date_val,
            "prediction_type":        _PREDICTION_TYPE,
            "retrain_tag":            retrain_tag,
            "is_backfill":            True,  # Story 30.7: explicit provenance flag
            "game_pk":                _col(df, "game_pk", i),
            "game_date":              game_date_val,
            "game_datetime":          None,
            "home_team":              home_team,
            "away_team":              away_team,
            "home_team_abbrev":       home_team,
            "away_team_abbrev":       away_team,
            "has_odds":               has_odds,
            "p_home_win_ngboost":     ngb_win,
            "p_home_win_classifier":  clf_win,
            "consensus_win_prob":     cons_win,
            "calibrated_win_prob":    cal_win,
            "pick":                   pick,
            "pred_total_runs":        float(loc_tot[i]),
            "pred_total_runs_scale":  float(scale_tot[i]),
            "pred_run_diff_loc":      float(loc_diff[i]),
            "pred_run_diff_scale":    float(scale_diff[i]),
            "p_over_ngboost":         p_over_v,
            "alpha":                  best_alpha,
            "h2h_market_implied_prob": h2h_mkt_v if has_odds else None,
            "h2h_posterior_prob":     h2h_post,
            "h2h_edge":               h2h_edge,
            "h2h_kelly_fraction":     h2h_kelly,
            "total_line_consensus":   total_line_v if has_odds else None,
            "over_prob_consensus":    over_mkt_v if has_odds else None,
            "totals_model_prob":      p_over_v if has_odds else None,
            "totals_posterior_prob":  tot_post,
            "totals_edge":            tot_edge,
            "totals_kelly_fraction":  tot_kelly,
        }))
    return rows


def _write_rows(rows: list[dict], model_version: str, retrain_tag: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(_ALTER_RETRAIN_TAG)
        except Exception as exc:
            print(f"[WARN] ALTER TABLE for retrain_tag skipped ({exc})")

        total = 0
        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start: start + _BATCH_SIZE]
            cur.executemany(_INSERT_ROW, batch)
            total += len(batch)
            print(f"  Inserted {total}/{len(rows)} rows...")
        conn.commit()
        print(f"\nWrote {len(rows)} rows to {_ML_SCHEMA}.daily_model_predictions "
              f"(model_version={model_version}, retrain_tag={retrain_tag})")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill daily_model_predictions with market-blind v2 rows for 2024+."
    )
    parser.add_argument(
        "--start-year", type=int, default=2024,
        help="First season to include (default: 2024)",
    )
    parser.add_argument(
        "--retrain-tag", default=_RETRAIN_TAG,
        help=(
            "Idempotency/label tag written to retrain_tag. Defaults to the historical "
            f"'{_RETRAIN_TAG}' so existing behaviour is unchanged. Pass a DISTINCT tag for a new "
            "champion's backtest (MH2.1 uses 'mh2_1_backtest') — otherwise the run collides with "
            "the previous champion's rows on the (model_version, retrain_tag) key and silently "
            "writes nothing. These rows are a BACKTEST, never a real-time record: they are also "
            "stamped prediction_type='backfill' and is_backfill=TRUE."
        ),
    )
    parser.add_argument(
        "--totals-artifact", choices=["prod", "prev"], default="prod",
        help=(
            "Which total_runs champion to score with. 'prod' (default) = the current champion. "
            "'prev' = the registry's `prev_artifact_path` + `prev_feature_columns_path`, i.e. the "
            "champion this one REPLACED. Exists so an old-vs-new comparison can be made "
            "apples-to-apples: every row written before 2026-08-02 carries the dropped-imputer-"
            "indicator defect (present since this script's first commit, 2026-05-12), so the "
            "pre-existing rows for a previous champion are NOT a valid baseline for a new one. "
            "Re-score the previous champion under its own --retrain-tag on fixed code instead. "
            "home_win and run_differential are always scored at 'prod' — they are unchanged by a "
            "totals-only promotion, so varying them would add a second difference to the contrast."
        ),
    )
    parser.add_argument(
        "--allow-noop", action="store_true", default=False,
        help=(
            "Permit a run where EVERY game is already present (writes nothing) to exit 0. Without "
            "this the script FAILS on a total no-op, because that is indistinguishable from the "
            "silent-failure mode of reusing a --retrain-tag after a per-target promotion."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Print row count and sample row without writing to Snowflake",
    )
    args = parser.parse_args()

    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    model_version = registry["home_win"]["model_version"]
    # MH2.1 — per-target totals stamp; `model_version` is a home_win-derived BUNDLE stamp and
    # does not move on a totals-only champion swap. Same column predict_today writes.
    totals_model_version = str(registry["total_runs"].get("model_version") or "unknown")
    tot_dist = registry["total_runs"]["dist"]
    diff_dist = registry["run_differential"]["dist"]

    print("=== Epic 1 / Story 1.6 — Historical Prediction Backfill ===")
    print(f"  model_version={model_version}  start_year={args.start_year}  "
          f"dry_run={args.dry_run}")

    print("\nLoading feature store from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= args.start_year].reset_index(drop=True)
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    if "game_date" in df.columns and "game_year" in df.columns:
        for yr in sorted(df["game_year"].unique()):
            sub = df[df["game_year"] == yr]["game_date"]
            print(f"  {yr}: {sub.min()} → {sub.max()}  ({len(sub):,} games)")
    else:
        print(f"  {len(df):,} rows loaded")

    if not args.dry_run:
        # Ensure retrain_tag + is_backfill columns exist before inserting (Story 30.7).
        try:
            conn = get_snowflake_connection()
            try:
                conn.cursor().execute(_ALTER_RETRAIN_TAG)
                conn.cursor().execute(_ALTER_IS_BACKFILL)
                conn.cursor().execute(_ALTER_TOTALS_MODEL_VERSION)   # MH2.1
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            print(f"[WARN] Could not add retrain_tag/is_backfill column ({exc})")

        print("\nChecking for existing backfill rows in Snowflake...")
        existing_pks = _get_existing_game_pks(model_version, args.retrain_tag)
        if existing_pks and "game_pk" in df.columns:
            before = len(df)
            df = df[~df["game_pk"].isin(existing_pks)].reset_index(drop=True)
            print(f"  Idempotency: skipped {before - len(df)} existing rows, "
                  f"{len(df):,} remaining")
            # ⚠️ TOTAL no-op guard. A 100%-skip is AMBIGUOUS: it is either a deliberate re-run
            # (harmless) or the silent-failure mode this script is most prone to — reusing a
            # retrain_tag after a PER-TARGET promotion. The idempotency key is
            # (game_pk, model_version, retrain_tag), and `model_version` is the home_win-derived
            # BUNDLE stamp, which a totals-only or run_diff-only promotion does NOT move. So the
            # new champion's backfill matches the OLD champion's rows on both key parts, skips
            # every game, writes nothing, and — before this guard — exited 0 with a cheerful
            # "Nothing to backfill." An operator has no way to tell that from success.
            #
            # State alone cannot separate the two cases, so the default is to FAIL and make the
            # operator say which it is. That is the right asymmetry: a needless `--allow-noop` on a
            # deliberate re-run costs one retry, whereas a silent no-op costs an entire believed-
            # complete backfill. Safe to exit non-zero — nothing automated invokes this script
            # (verified: no Dagster op, cron, or workflow references it).
            if df.empty and not args.allow_noop:
                raise SystemExit(
                    f"❌ EVERY game was skipped as already-present for "
                    f"(model_version={model_version!r}, retrain_tag={args.retrain_tag!r}) — "
                    f"NOTHING would be written.\n"
                    f"   If you are backfilling a NEW champion, this is the failure mode to check "
                    f"first: `model_version` is derived from home_win ALONE, so a per-target "
                    f"promotion does not change it, and reusing a retrain_tag makes the run a "
                    f"silent no-op. Pass a DISTINCT --retrain-tag (e.g. '<champion>_backtest').\n"
                    f"   If this re-run is deliberate and you expect zero new rows, pass "
                    f"--allow-noop."
                )
        else:
            print(f"  No existing rows found — inserting all {len(df):,} games")

    if df.empty:
        print("Nothing to backfill." + (" (--allow-noop)" if args.allow_noop else ""))
        return

    print("\nFitting imputation pipeline on numeric columns...")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    pipe = build_imputation_pipeline()
    pipe.fit(df[numeric_cols])
    _transformed = pipe.transform(df[numeric_cols])
    # ⚠️ Keep the transform's OWN columns. `build_imputation_pipeline` runs `_AddIndicators`, which
    # APPENDS has_starter_platoon_data + is_new_venue — both of which are in every served sidecar.
    # Re-wrapping a returned DataFrame as `pd.DataFrame(t, columns=numeric_cols)` does not RENAME,
    # it SELECTS: the two indicators were silently dropped, and the later
    # `reindex(columns=..., fill_value=0.0)` then filled them with 0.0 for every game — i.e. "no
    # platoon data / not a new venue" asserted for the whole backfill. That is a wrong VALUE, not a
    # crash, so it would have scored an entire history quietly. predict_today never had this bug
    # (it carries the imputer's output frame through unchanged).
    df_t = (_transformed.set_index(df.index) if isinstance(_transformed, pd.DataFrame)
            else pd.DataFrame(_transformed, columns=numeric_cols, index=df.index))
    print(f"  Transformed shape: {df_t.shape}")
    for _ind in ("has_starter_platoon_data", "is_new_venue"):
        if _ind not in df_t.columns:
            print(f"  [WARN] imputer indicator '{_ind}' absent from the transformed frame — it "
                  f"will be 0.0-filled for every game, which is a VALUE the models were not "
                  f"trained to see uniformly. Investigate before trusting this backfill.")

    # ── which total_runs champion are we scoring with? ────────────────────────────────────────
    _tot_is_prev = args.totals_artifact == "prev"
    if _tot_is_prev:
        _missing = [k for k in ("prev_artifact_path", "prev_feature_columns_path")
                    if not registry["total_runs"].get(k)]
        if _missing:
            raise SystemExit(
                f"❌ --totals-artifact prev requires {_missing} on the total_runs registry entry; "
                f"they are absent. There is no recorded previous champion to score."
            )
        # The stamp must name the model that actually scored the row, not the current champion —
        # otherwise the comparison rows are labelled as if the new model produced them.
        totals_model_version = str(
            registry["total_runs"].get("prev_model_version")
            or _infer_prev_version(registry["total_runs"]["prev_artifact_path"])
        )
        print(f"  ⚠️  totals scored with the PREVIOUS champion "
              f"({registry['total_runs']['prev_artifact_path'].split('/')[-1]}), stamped "
              f"totals_model_version={totals_model_version!r}. home_win/run_diff stay at prod.")

    def feat_cols(target: str) -> list[str]:
        """The served column list for a target.

        ⚠️ Sidecars come in TWO shapes: a bare JSON list (pre-E13.11) and
        `{"feature_cols": [...], "_provenance": {...}}` (E13.11+). Returning the parsed JSON
        unconditionally yields the DICT for the modern shape, whose `len()` is 2 and whose
        iteration order is `["feature_cols", "_provenance"]` — so `reindex(columns=...)` built a
        2-column matrix out of the KEY NAMES and every model raised a feature-count error. This
        script was left behind when the sidecars gained provenance; `predict_today._load_cols` has
        carried the unwrap since E13.11. Mirrored here.
        """
        _key = ("prev_feature_columns_path"
                if (target == "total_runs" and _tot_is_prev) else "feature_columns_path")
        path = PROJECT_ROOT / registry[target][_key]
        raw = json.loads(path.read_text())
        return raw["feature_cols"] if isinstance(raw, dict) else raw

    hw_cols = feat_cols("home_win")
    tot_cols = feat_cols("total_runs")
    diff_cols = feat_cols("run_differential")
    print(f"  Feature columns: home_win={len(hw_cols)}, "
          f"total_runs={len(tot_cols)}, run_diff={len(diff_cols)}")

    # Fail HERE, with a readable message, rather than ~20 frames deep in sklearn's
    # `_check_n_features`. The registry advertises each target's served width; a contract that
    # resolves to a different count means the sidecar was misread (the dict-vs-list bug above) or
    # the registry and the sidecar have drifted — either way the scored matrix would be wrong.
    for _tgt, _cols in (("home_win", hw_cols), ("total_runs", tot_cols),
                        ("run_differential", diff_cols)):
        _advertised = (None if (_tgt == "total_runs" and _tot_is_prev)
                       else registry[_tgt].get("features"))  # registry `features` names the CURRENT champion
        if _advertised is not None and len(_cols) != int(_advertised):
            raise SystemExit(
                f"❌ {_tgt}: sidecar resolved {len(_cols)} feature(s) but the registry advertises "
                f"{_advertised}. Resolved head: {list(_cols)[:4]}. If that looks like JSON KEYS "
                f"('feature_cols', '_provenance') the sidecar unwrap regressed; otherwise the "
                f"registry `features` and {registry[_tgt]['feature_columns_path']} have drifted."
            )

    print("\nLoading production models from registry...")
    clf_hw = load_model("home_win", "prod")
    # load_model resolves any entry-level registry key as a "variant", so `prev_artifact_path`
    # needs no change to model_io.
    ngb_tot = load_model("total_runs", "prev_artifact_path" if _tot_is_prev else "prod")
    ngb_diff = load_model("run_differential", "prod")
    print(f"  home_win:        {type(clf_hw).__name__}")
    print(f"  total_runs:      {type(ngb_tot).__name__}  dist={tot_dist}")
    print(f"  run_differential:{type(ngb_diff).__name__}  dist={diff_dist}")

    calibrator = _load_calibrator()
    best_alpha = _load_best_alpha()
    print(f"  best_alpha={best_alpha}")

    print("\nRunning inference...")
    # ⚠️ EVERY model input comes from the IMPUTED frame `df_t`, never the raw `df`.
    # This line used to read `df.reindex(..., fill_value=np.nan)` under the comment "Elasticnet uses
    # its own internal imputer" — describing an architecture that is no longer served. The E13.11
    # home_win champion is `PlattCalibratedLinearClassifier(Pipeline(StandardScaler,
    # LogisticRegression))`, which has NO imputer and rejects NaN outright ("LogisticRegression does
    # not accept missing values encoded as NaN natively"). The previous XGBoost champion consumed
    # NaN natively, so the raw-frame path was silently invalidated by that swap and nothing noticed
    # — the backfill was already unrunnable for a different reason (the sidecar unwrap).
    # `predict_today` builds ALL THREE inputs from its imputed matrix (`X_today_imp`); this now
    # matches it exactly, including fill_value and dtype.
    X_hw = df_t.reindex(columns=hw_cols, fill_value=0.0).values.astype(np.float32)
    if not np.isfinite(X_hw).all():
        _bad = [c for c in hw_cols if c in df_t.columns and not np.isfinite(df_t[c]).all()]
        raise SystemExit(
            f"❌ home_win matrix still contains NaN/inf after imputation in {len(_bad)} column(s): "
            f"{_bad[:8]}. The served classifier rejects NaN, so this would fail deep inside sklearn "
            f"with a message naming neither the column nor the target."
        )
    p_hw_clf = clf_hw.predict_proba(X_hw)[:, 1]

    # NGBoost models use the externally imputed df_t
    X_tot = df_t.reindex(columns=tot_cols, fill_value=0.0).values
    pred_dist_tot = ngb_tot.pred_dist(X_tot)
    loc_tot = pred_dist_tot.params["loc"]
    scale_tot = pred_dist_tot.params["scale"]

    X_diff = df_t.reindex(columns=diff_cols, fill_value=0.0).values
    pred_dist_diff = ngb_diff.pred_dist(X_diff)
    loc_diff = pred_dist_diff.params["loc"]
    scale_diff = pred_dist_diff.params["scale"]

    # P(run_diff > 0) is the NGBoost-derived home win probability
    p_hw_ngb = p_over_line(diff_dist, {"loc": loc_diff, "scale": scale_diff}, total_line=0)

    total_line_vals = (
        df["total_line_consensus"].values
        if "total_line_consensus" in df.columns
        else np.full(len(df), np.nan)
    )
    p_over_tot_arr = p_over_line(
        tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line_vals
    )

    inserted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = _build_rows(
        df, model_version, totals_model_version, args.retrain_tag,
        p_hw_ngb, p_hw_clf,
        loc_tot, scale_tot,
        loc_diff, scale_diff,
        p_over_tot_arr, total_line_vals,
        best_alpha, calibrator, inserted_at,
    )

    has_odds_count = sum(1 for r in rows if r.get("has_odds"))
    print(f"\n  Built {len(rows):,} rows ({has_odds_count:,} with market odds)")

    if rows:
        s = rows[0]
        print(f"  Sample [0]: game_pk={s['game_pk']}, game_date={s['game_date']}, "
              f"p_hw_clf={s['p_home_win_classifier']:.4f}, "
              f"pred_total={s['pred_total_runs']:.2f}, "
              f"pred_rdiff={s['pred_run_diff_loc']:.2f}")
        s = rows[-1]
        print(f"  Sample [-1]: game_pk={s['game_pk']}, game_date={s['game_date']}, "
              f"p_hw_clf={s['p_home_win_classifier']:.4f}, "
              f"pred_total={s['pred_total_runs']:.2f}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would insert {len(rows):,} rows — Snowflake write skipped.")
        return

    print("\nWriting to Snowflake...")
    _write_rows(rows, model_version, args.retrain_tag)


if __name__ == "__main__":
    main()
