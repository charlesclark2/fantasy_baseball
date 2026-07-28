"""e7_9_train_serve_consistency.py — MLB Edge-E7.9: close the E7.5 / E7.5p train-serve gap and
decide whether the MiLB-MLE-corrected feature block (+ the newly-joined `eb_gb_pct`) earns a
retrained champion.

WHY THIS EXISTS
---------------
E7.5 wired the BATTER MiLB→MLB MLE into `eb_batter_posteriors_raw` and E7.5p wired the PITCHER MLE
into `eb_starter_posteriors`. Both changed the SERVED feature distribution while the served
champions were still fitted on the OLD generic-prior values — a train/serve mismatch. E7.5p also
landed `eb_gb_pct` (E7.3p's strongest translation, −23% cold-start MAE) as a served column with NO
consumer; E7.9's dbt change joins it through `feature_pregame_starter_features` →
`home_/away_starter_eb_gb_pct`, and THIS script is what decides whether a model should use it.

TWO MODES
---------
`--audit` (fast, S3-native, no fitting)
    Answers "how big is the skew, and which SERVED contracts does it actually touch?" BEFORE
    spending a retrain on it. Reads the served v6 sidecars and intersects them with the columns
    E7.5 / E7.5p can move. ⚠️ Run this FIRST: the answer re-scopes the bake-off.

`--bakeoff --target ... --tier ...` (the §0.5 retrain, minutes → OPERATOR)
    A pre-registered arm grid of CONTRACT VARIANT × LEARNER CLASS under E1.1 purged/embargoed CV,
    scored on the target's honest distributional metric (CRPS), with ONE shared PBO surface over
    the whole grid and a DSR deflated by the grid size.

      contract variants
        incumbent   — the served v6 contract, verbatim. The bar.
        plus_gb     — incumbent + home_/away_starter_eb_gb_pct (the E7.9 join; the question the
                      story exists to answer).
        plus_eb     — incumbent + the E7.5/E7.5p-corrected EB columns the contract does NOT already
                      carry. Pre-registered so "the corrected block does not help" is a MEASURED
                      null rather than an assumption.
        plus_both   — plus_gb ∪ plus_eb.
      learner classes: the model_bakeoff slate (ngboost_normal = the incumbent class, xgboost,
      lightgbm, catboost, glm_elasticnet) — ≥3 classes with a direct-learned foil, per §0.5.

DECISION RULE (pre-registered; the default is INCUMBENT_STANDS)
--------------------------------------------------------------
SHIP a challenger only if ALL hold:
  1. it beats the INCUMBENT arm (incumbent contract × incumbent class) on CRPS by MORE than the
     NOISE_FLOOR for the metric — a within-floor win is a tie, and a tie ships nothing;
  2. PBO < 0.2 over the whole arm grid;
  3. DSR > 0 at 95% on the per-bucket improvement series, deflated by n_arms;
  4. calibration (PIT-KS) does not degrade vs the incumbent arm.
Otherwise: INCUMBENT_STANDS, and the null IS the deliverable.
⚠️ E2.1-r SELECTION-METRIC HYGIENE: an ORACLE arm (sees the realized target) is scored alongside
the candidates and MUST come first. A candidate beating the oracle is mathematically impossible and
means the metric is inverted — the run HALTs rather than reporting a winner.
⚠️ `best_alpha = 0`. This is a calibration / train-serve-consistency exercise, not an edge claim.
Nothing here licenses a win-rate or ROI statement.

LEAKAGE POSTURE (audited, not assumed)
--------------------------------------
The MLE prior itself is leakage-safe by CONSTRUCTION: `milb_mle.emit_projections` refits the
translation map per MLB debut cohort on STRICTLY-PRIOR cohorts, and the minor-league line entering
it is strictly pre-debut (`build_graduated_pairs`). So a 2023 game reads a prior fit on ≤2022
graduates — no as-of rebuild is required for the historical backfill. The one residual full-sample
quantity is the recalibrated κ (ONE scalar per metric, from `mle_prior.recalibrate`); it carries no
player-specific information and is reported in the audit rather than silently ignored.

RUNTIME: the bake-off retrains (arms × folds) — NGBoost/CatBoost dominate. Minutes → HAND TO THE
OPERATOR (>2-min rule). `--smoke` caps rows/estimators/arms for a fast end-to-end harness check.

Usage:
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py --audit
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py \
        --bakeoff --target run_diff --tier pre_lineup --s3 --refresh-cache
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py --bakeoff --target total_runs --smoke

⚠️ `--s3 --refresh-cache` is the real-run combination. Without `--refresh-cache` the harness reads a
stale cached matrix; without `--s3` it reads Snowflake, which does not carry `eb_gb_pct` until the
operator recreates the external table — so the `plus_gb` arm would be silently DROPPED and the
story's headline question would go unanswered. The harness reports every dropped variant for
exactly this reason: read that line before trusting a verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_ABL = PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
_JSON_DIR = PROJECT_ROOT / "betting_ml/evaluation/feature_selection/bakeoff"

STORY = "E7.9"
BEST_ALPHA = 0

# ── the columns E7.5 / E7.5p can move, at the GAME grain ──────────────────────────────────────
# E7.5  (batter MLE → eb_batter_posteriors_raw): K% / BB% / ISO, aggregated to avg_eb_* per side.
# E7.5p (pitcher MLE → eb_starter_posteriors):   K% / BB% for a COLD-START starter, plus the NEW
#        eb_gb_pct column. eb_xwoba_against (+ _sequential, _uncertainty) is NOT wired to the MLE —
#        it keeps its experience-band prior verbatim — so it is deliberately absent here.
E75_BATTER_COLS = tuple(
    f"{side}_avg_eb_{m}" for side in ("home", "away") for m in ("k_pct", "bb_pct", "iso")
)
E75P_STARTER_COLS = tuple(
    f"{side}_starter_eb_{m}" for side in ("home", "away") for m in ("k_pct", "bb_pct")
)
# The E7.9 join itself — a NEW column, in no incumbent contract by construction.
E79_GB_COLS = ("home_starter_eb_gb_pct", "away_starter_eb_gb_pct")

MLE_AFFECTED_COLS = E75_BATTER_COLS + E75P_STARTER_COLS

# served v6 sidecars (registry `feature_columns_path` / `pre_lineup_feature_columns_path`)
SERVED_CONTRACTS = {
    ("total_runs", "post_lineup"): "betting_ml/models/total_runs/feature_columns_v6_total_runs_post_lineup_served.json",
    ("total_runs", "pre_lineup"):  "betting_ml/models/total_runs/feature_columns_v6_total_runs_pre_lineup_served.json",
    ("run_diff", "post_lineup"):   "betting_ml/models/run_differential/feature_columns_v6_run_diff_post_lineup_served.json",
    ("run_diff", "pre_lineup"):    "betting_ml/models/run_differential/feature_columns_v6_run_diff_pre_lineup_served.json",
    ("home_win", "post_lineup"):   "betting_ml/models/home_win/feature_columns_v6_home_win_post_lineup_served.json",
    ("home_win", "pre_lineup"):    "betting_ml/models/home_win/feature_columns_v6_home_win_pre_lineup_served.json",
}

# build_imputation_pipeline() ALWAYS appends these; they are in the served sidecar but are not
# real contract features, so they must be stripped before a contract is re-derived.
IMPUTER_ADDED = ("has_starter_platoon_data", "is_new_venue")

# The incumbent learner class per regression target (E1.9 v6 → E13.11 deploy).
INCUMBENT_CLASS = {"total_runs": "ngboost_normal", "run_diff": "ngboost_normal"}

PBO_MAX = 0.2
DSR_MIN_CONF = 0.95


def _read_contract(path: str) -> list[str]:
    raw = json.loads((PROJECT_ROOT / path).read_text())
    cols = raw["feature_cols"] if isinstance(raw, dict) else raw
    return [c for c in cols if c not in IMPUTER_ADDED]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MODE 1 — the exposure audit (no fitting; run this BEFORE spending a retrain)
# ══════════════════════════════════════════════════════════════════════════════════════════════


def audit_served_contracts() -> dict:
    """Which SERVED contracts actually carry a column E7.5 / E7.5p can move?

    The story's premise is a train/serve mismatch on 'the served totals + run-diff models'. That
    premise is only true where an affected column is IN a served contract — and the v6 post_lineup
    contracts are 13-feature slim sets. Measuring this first is what keeps the retrain honest (and
    scoped): an unaffected contract needs no retrain, only the new-feature question.
    """
    out = {}
    for (target, tier), path in SERVED_CONTRACTS.items():
        p = PROJECT_ROOT / path
        if not p.exists():
            out[f"{target}/{tier}"] = {"error": f"missing sidecar {path}"}
            continue
        cols = _read_contract(path)
        affected = [c for c in cols if c in MLE_AFFECTED_COLS]
        out[f"{target}/{tier}"] = {
            "contract": path,
            "n_features": len(cols),
            "mle_affected_in_contract": affected,
            "n_mle_affected": len(affected),
            "has_gb_already": [c for c in cols if c in E79_GB_COLS],
            "train_serve_skew": bool(affected),
        }
    return out


def audit_prior_exposure(min_season: int = 2021) -> dict:
    """How much of the served starter population does the pitcher MLE actually move, and by how
    much? SF-free — reads the S3 lakehouse parquet directly.

    Reference for the magnitude is the GENERIC experience-band prior mean (`ref_eb_starter_priors`,
    age_band 'u25'). That is EXACT for `prior_only` rows (where the generic posterior IS the band
    mean) and an UPPER BOUND for `full_eb` rows (where the generic path would already have shrunk
    toward the pitcher's own observed line). Reported split by branch so the bound is visible
    rather than buried in a pooled average.
    """
    import duckdb

    conn = duckdb.connect()
    conn.execute("install httpfs; load httpfs; set s3_region='us-east-2';")
    try:
        conn.execute("create secret (type s3, provider credential_chain)")
    except Exception:
        pass  # a secret may already exist in this process
    b = "s3://baseball-betting-ml-artifacts/baseball/lakehouse"
    s = f"read_parquet('{b}/eb_starter_posteriors/**/*.parquet')"
    p = f"read_parquet('{b}/milb_mle_pitcher_prior/data.parquet')"
    r = f"read_parquet('{b}/ref_eb_starter_priors/**/*.parquet')"

    exposure = conn.execute(f"""
        with s as (select * from {s} where season >= {int(min_season)}),
             p as (select try_cast(pitcher_id as bigint) pid from {p})
        select count(*)                                                              as starter_rows,
               sum(case when s.age_band = 'u25' then 1 else 0 end)                   as cold_start_rows,
               sum(case when s.age_band = 'u25' and p.pid is not null then 1 else 0 end) as mle_moved_rows
        from s left join p on p.pid = try_cast(s.pitcher_id as bigint)
    """).fetchone()

    magnitude = conn.execute(f"""
        with s as (select * from {s} where season >= {int(min_season)} and age_band = 'u25'),
             p as (select try_cast(pitcher_id as bigint) pid from {p}),
             ref as (select SEASON season, lower(METRIC) metric, MU mu from {r} where AGE_BAND = 'u25')
        select s.eb_data_source,
               count(*)                                              as n,
               avg(abs(s.eb_k_pct  - rk.mu))                         as mean_abs_k_shift,
               quantile_cont(abs(s.eb_k_pct - rk.mu), 0.9)           as p90_abs_k_shift,
               avg(abs(s.eb_bb_pct - rb.mu))                         as mean_abs_bb_shift
        from s
        join p on p.pid = try_cast(s.pitcher_id as bigint)
        left join ref rk on rk.season = s.season and rk.metric = 'k_pct'
        left join ref rb on rb.season = s.season and rb.metric = 'bb_pct'
        group by 1 order by 2 desc
    """).fetchdf()

    gb = conn.execute(
        f"select count(*) n, count(eb_gb_pct) nonnull, min(eb_gb_pct) lo, max(eb_gb_pct) hi from {s}"
    ).fetchone()
    conn.close()

    rows, cold, moved = exposure
    return {
        "min_season": min_season,
        "starter_rows": int(rows),
        "cold_start_rows": int(cold),
        "mle_moved_rows": int(moved),
        "share_of_starter_rows_moved": round(moved / rows, 4) if rows else None,
        # a game has two starters; P(at least one moved) under independence — a scoping figure,
        # NOT a claim about the joint distribution of the two rotations.
        "approx_share_of_games_touched": round(1 - (1 - moved / rows) ** 2, 4) if rows else None,
        "magnitude_vs_generic_band_prior_mean": magnitude.to_dict(orient="records"),
        "eb_gb_pct": {"rows": int(gb[0]), "non_null": int(gb[1]),
                      "min": float(gb[2]), "max": float(gb[3])},
    }


def run_audit(min_season: int) -> dict:
    contracts = audit_served_contracts()
    exposure = audit_prior_exposure(min_season)
    skewed = [k for k, v in contracts.items() if v.get("train_serve_skew")]
    result = {
        "story": STORY, "mode": "audit", "best_alpha": BEST_ALPHA,
        "served_contracts": contracts,
        "contracts_with_train_serve_skew": skewed,
        "prior_exposure": exposure,
        "leakage_posture": {
            "mle_map": "leakage-safe by construction — emit_projections refits per debut cohort on "
                       "STRICTLY-PRIOR cohorts; the minor line is strictly pre-debut. No as-of "
                       "rebuild is needed for the historical backfill.",
            "residual_full_sample_quantity": "the recalibrated kappa (one scalar per metric, from "
                                             "mle_prior.recalibrate) is fit on all graduates; it "
                                             "carries no player-specific information.",
        },
    }
    _write_audit_report(result)
    return result


def _write_audit_report(result: dict) -> None:
    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    (_JSON_DIR / "e7_9_audit.json").write_text(json.dumps(result, indent=2, default=float))

    ex = result["prior_exposure"]
    skewed = result["contracts_with_train_serve_skew"]
    lines: list[str] = []
    a = lines.append
    a(f"# MLB Edge-{STORY} — train/serve exposure audit (BATTER + STARTER MiLB-MLE priors)")
    a("")
    a("> ⚠️ **Not an edge result.** This scopes a retrain; `best_alpha = 0`.")
    a("")
    a("## Which SERVED contracts does the MLE actually touch?")
    a("")
    a("| model / tier | features | E7.5/E7.5p columns in contract | train-serve skew |")
    a("|---|---:|---|---|")
    for k, v in result["served_contracts"].items():
        if "error" in v:
            a(f"| {k} | — | `{v['error']}` | ? |")
            continue
        cols = ", ".join(f"`{c}`" for c in v["mle_affected_in_contract"]) or "—"
        a(f"| {k} | {v['n_features']} | {cols} | {'**YES**' if v['train_serve_skew'] else 'no'} |")
    a("")
    if skewed:
        a(f"**Skewed contracts: {', '.join(skewed)}.** Every other served contract is UNAFFECTED — "
          "the MLE-moved columns are simply not in it, so for those models E7.9 is a "
          "new-feature question (`eb_gb_pct`) and not a skew repair.")
    else:
        a("**No served contract carries an MLE-moved column** — the flagged train/serve skew does "
          "not reach any served prediction. E7.9 reduces to the `eb_gb_pct` question.")
    a("")
    a("## How much does the pitcher MLE move the served starter population?")
    a("")
    a(f"- Starter rows (season ≥ {ex['min_season']}): **{ex['starter_rows']:,}**")
    a(f"- Cold-start (`age_band='u25'`): **{ex['cold_start_rows']:,}**")
    a(f"- Cold-start WITH an MLE prior (the rows whose `eb_k_pct`/`eb_bb_pct` actually change): "
      f"**{ex['mle_moved_rows']:,}** = {ex['share_of_starter_rows_moved']:.1%} of starter rows "
      f"(≈{ex['approx_share_of_games_touched']:.1%} of games touch ≥1 moved starter)")
    a("")
    a("Magnitude vs the generic experience-band prior mean — EXACT for `prior_only`, an UPPER "
      "BOUND for `full_eb` (the generic path would already have shrunk toward the observed line):")
    a("")
    a("| eb_data_source | n | mean abs K% shift | p90 | mean abs BB% shift |")
    a("|---|---:|---:|---:|---:|")
    for row in ex["magnitude_vs_generic_band_prior_mean"]:
        a(f"| {row['eb_data_source']} | {int(row['n']):,} | {row['mean_abs_k_shift']:.4f} | "
          f"{row['p90_abs_k_shift']:.4f} | {row['mean_abs_bb_shift']:.4f} |")
    a("")
    g = ex["eb_gb_pct"]
    a(f"`eb_gb_pct` (the E7.5p column E7.9 joins through): {g['non_null']:,}/{g['rows']:,} non-null, "
      f"range {g['min']:.3f}–{g['max']:.3f}.")
    a("")
    a("## Leakage posture")
    a("")
    for k, v in result["leakage_posture"].items():
        a(f"- **{k}** — {v}")
    a("")
    (_ABL / "e7_9_train_serve_audit.md").write_text("\n".join(lines) + "\n")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MODE 2 — the pre-registered retrain bake-off
# ══════════════════════════════════════════════════════════════════════════════════════════════


def build_arm_contracts(target: str, tier: str, df_cols) -> dict[str, list[str]]:
    """The PRE-REGISTERED contract variants. Registered before any result is seen; a variant whose
    added columns are entirely absent from the matrix is DROPPED (and reported), never silently
    collapsed onto the incumbent — two identically-columned arms would double-count in the PBO
    surface and understate the multiple-testing burden."""
    base = [c for c in _read_contract(SERVED_CONTRACTS[(target, tier)]) if c in df_cols]
    gb = [c for c in E79_GB_COLS if c in df_cols and c not in base]
    eb = [c for c in MLE_AFFECTED_COLS if c in df_cols and c not in base]

    variants = {"incumbent": base}
    if gb:
        variants["plus_gb"] = base + gb
    if eb:
        variants["plus_eb"] = base + eb
    if gb and eb:
        variants["plus_both"] = base + gb + eb
    return variants


class _OracleSpec:
    """E2.1-r selection-metric sanity: a predictive centred on the REALIZED target with a tiny
    spread. It cannot be beaten on a proper score. If any candidate outscores it, the metric is
    inverted and the run must HALT rather than crown a winner."""

    name = "oracle_floor"

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None):
        from betting_ml.utils.promotion_gate import PredictiveOutput
        y = np.asarray(yev, float)
        return PredictiveOutput.normal(y, np.full(len(y), 1e-3))


def run_retrain_bakeoff(target: str, tier: str, *, seed: int, smoke: bool,
                        refresh_cache: bool, embargo_days: int, s3: bool = False) -> dict:
    from betting_ml.scripts.model_bakeoff import (
        _TARGETS, _assert_market_blind, _candidates, load_clean_matrix,
    )
    from betting_ml.scripts.promotion_gate_eval import _impute, make_gate_splitter
    from betting_ml.utils.feature_hygiene import is_identifier_name
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv
    from betting_ml.utils.promotion_gate import NOISE_FLOOR, calibration_report

    cfg = _TARGETS[target]
    kind, metric, tcol = cfg["kind"], cfg["metric"], cfg["col"]
    if kind != "reg":
        raise SystemExit(f"{STORY} covers the regression champions only; got kind={kind}")

    # SF-FREE READ (repo doctrine): with --s3 the matrix comes from the S3 lakehouse via DuckDB
    # instead of Snowflake. This is not just hygiene — the DuckDB `--w8b` build carries the E7.9
    # `*_starter_eb_gb_pct` join from its FIRST rebuild, whereas the Snowflake table does not until
    # the operator recreates the external table and re-materializes. Reading S3 is what lets the
    # retrain run WITHOUT waiting on that, and it is the same surface the served `--s3` path uses.
    if s3:
        from betting_ml.utils.data_loader import set_s3_mode
        set_s3_mode(True)
        print(f"[{STORY}] reading the training matrix from the S3 lakehouse (Snowflake-free)")
    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=smoke)
    variants = build_arm_contracts(target, tier, set(df.columns))
    dropped = [v for v in ("plus_gb", "plus_eb", "plus_both") if v not in variants]
    for cols in variants.values():
        _assert_market_blind(cols)
        bad = [c for c in cols if is_identifier_name(c)]
        if bad:
            raise SystemExit(f"❌ identifier column(s) in a contract variant: {bad}")

    # learner slate: reuse the E1.9 bake-off classes so the comparison is apples-to-apples with the
    # selection that produced the incumbent. Floors are dropped here — E7.9's bar is the INCUMBENT
    # arm, not no-skill; the market floor would also break the market-blind posture of the grid.
    classes = [c for c in _candidates(kind, target, df, seed=seed, smoke=smoke)
               if not c.name.startswith("floor_")]
    arms = [(v, c) for v in variants for c in classes]
    arm_names = [f"{v}::{c.name}" for v, c in arms]
    incumbent_arm = f"incumbent::{INCUMBENT_CLASS[target]}"
    if incumbent_arm not in arm_names:
        raise SystemExit(f"❌ the incumbent arm {incumbent_arm} is not in the grid {arm_names}")

    # one splitter over the UNION of every variant's columns, so every arm sees IDENTICAL folds
    # (a per-variant purge band would give the wider contract different eval rows and make the
    # arms incomparable).
    union_cols = sorted({c for cols in variants.values() for c in cols})
    splitter, _ = make_gate_splitter(True, feature_cols=union_cols, embargo_days=embargo_days)
    folds = list(splitter(df))
    print(f"[{STORY}] {target}/{tier}: {len(variants)} contract variants × {len(classes)} classes "
          f"= {len(arms)} arms × {len(folds)} purged folds  (metric={metric})")
    for v, cols in variants.items():
        print(f"   {v:10s} {len(cols):4d} features"
              + (f"  (+{sorted(set(cols) - set(variants['incumbent']))})" if v != "incumbent" else ""))
    if dropped:
        print(f"   [dropped variants — added columns absent from the matrix] {dropped}")

    per_arm: dict[str, list] = {n: [] for n in arm_names}
    oracle = _OracleSpec()
    per_arm[oracle.name] = []
    for tr, ev in folds:
        ytr, yev = df.loc[tr, tcol].values, df.loc[ev, tcol].values
        cache: dict[str, tuple] = {}
        for (v, c), name in zip(arms, arm_names):
            if v not in cache:
                cache[v] = _impute(df.loc[tr, variants[v]], df.loc[ev, variants[v]])
            Xtr, Xev = cache[v]
            per_arm[name].append((ev, c.fit_predict(Xtr, ytr, Xev, yev), yev))
        Xtr, Xev = cache["incumbent"]
        per_arm[oracle.name].append((ev, oracle.fit_predict(Xtr, ytr, Xev, yev), yev))

    # pool per-arm scores + a (bucket × arm) matrix for PBO
    rows, bucket_perf = [], {}
    for name in arm_names + [oracle.name]:
        primary, buckets, pit = [], [], []
        for ev, out, yev in per_arm[name]:
            primary.append(out.score_to_truth(yev, metric))
            ym = (df.loc[ev, "game_year"].astype(int).astype(str) + "-"
                  + df.loc[ev, "game_date"].astype("datetime64[ns]").dt.month.astype(str).str.zfill(2))
            buckets.append(ym.values)
            if out.kind in ("normal", "lognormal", "samples"):
                pit.append(calibration_report(yev, out)["pit_ks"])
        primary = np.concatenate(primary)
        bvec = np.concatenate(buckets)
        bucket_perf[name] = pd.Series(primary).groupby(pd.Series(bvec)).mean().to_dict()
        variant, _, cls = name.partition("::")
        rows.append({
            "arm": name, "variant": variant, "learner": cls or "-",
            f"{metric}_mean": float(np.nanmean(primary)),
            "pit_ks": float(np.nanmean(pit)) if pit else float("nan"),
            "n": int(len(primary)),
        })
    table = pd.DataFrame(rows).sort_values(f"{metric}_mean").reset_index(drop=True)

    # ── E2.1-r ORACLE-FLOOR SANITY — must fire BEFORE any winner is declared ──
    oracle_score = float(table.loc[table["arm"] == oracle.name, f"{metric}_mean"].iloc[0])
    cand = table[table["arm"] != oracle.name]
    beats_oracle = list(cand.loc[cand[f"{metric}_mean"] < oracle_score - 1e-12, "arm"])
    if beats_oracle:
        raise SystemExit(
            f"❌ ORACLE-FLOOR VIOLATION: {beats_oracle} scored better than an oracle that SEES the "
            f"target ({metric} {oracle_score:.6f}). The selection metric is inverted — fix the "
            f"metric before reading any result (E2.1-r)."
        )

    inc = cand.loc[cand["arm"] == incumbent_arm].iloc[0]
    best = cand.iloc[0]
    nf = NOISE_FLOOR.get(metric, 0.0)
    margin = float(inc[f"{metric}_mean"]) - float(best[f"{metric}_mean"])  # >0 ⇒ challenger better

    # PBO over the WHOLE grid (every variant × class counts toward the multiple-testing surface)
    all_b = sorted(set().union(*[set(bucket_perf[n]) for n in arm_names]))
    perf = np.array([[bucket_perf[n].get(b, np.nan) for n in arm_names] for b in all_b])
    keep = ~np.isnan(perf).any(axis=1)
    pbo_val = float("nan")
    if keep.sum() >= 4 and len(arm_names) >= 2:
        pbo_val = float(pbo_cscv(perf[keep], higher_is_better=False,
                                 n_splits=min(16, keep.sum() - (keep.sum() % 2))).pbo)

    # DSR on the per-bucket improvement of the leader over the incumbent, deflated by grid size
    imp = np.array([bucket_perf[incumbent_arm].get(b, np.nan) - bucket_perf[best["arm"]].get(b, np.nan)
                    for b in all_b], float)
    imp = imp[np.isfinite(imp)]
    dsr = (deflated_sharpe(imp, n_trials=len(arm_names))
           if len(imp) >= 3 and np.std(imp) > 0 else None)
    dsr_p = float(getattr(dsr, "dsr", float("nan"))) if dsr is not None else float("nan")

    calib_ok = bool(np.isnan(best["pit_ks"]) or np.isnan(inc["pit_ks"])
                    or best["pit_ks"] <= inc["pit_ks"] + 1e-9)
    gates = {
        "beats_incumbent_by_more_than_noise_floor": bool(best["arm"] != incumbent_arm and margin > nf),
        "pbo_lt_0_2": bool(np.isfinite(pbo_val) and pbo_val < PBO_MAX),
        "dsr_gt_0_at_95": bool(np.isfinite(dsr_p) and dsr_p >= DSR_MIN_CONF),
        "calibration_not_degraded": calib_ok,
    }
    ship = all(gates.values())
    verdict = "SHIP_CHALLENGER" if ship else "INCUMBENT_STANDS"

    result = {
        "story": STORY, "mode": "bakeoff", "best_alpha": BEST_ALPHA,
        "target": target, "tier": tier, "metric": metric, "smoke": smoke, "seed": seed,
        "n_arms": len(arm_names), "n_folds": len(folds), "n_rows": int(len(df)),
        "variants": {k: {"n_features": len(v),
                         "added_vs_incumbent": sorted(set(v) - set(variants["incumbent"]))}
                     for k, v in variants.items()},
        "dropped_variants": dropped,
        "incumbent_arm": incumbent_arm,
        "incumbent_metric": float(inc[f"{metric}_mean"]),
        "leader_arm": str(best["arm"]),
        "leader_metric": float(best[f"{metric}_mean"]),
        "margin_vs_incumbent": round(margin, 6),
        "noise_floor": nf,
        "pbo": pbo_val, "dsr": dsr_p,
        "oracle_metric": oracle_score, "oracle_floor_ok": True,
        "gates": gates, "verdict": verdict,
        "table": table.to_dict(orient="records"),
    }
    _write_bakeoff_report(result, table)
    print(f"\n[{STORY}] VERDICT: {verdict}  (leader={result['leader_arm']}, "
          f"margin={margin:+.4f} vs floor {nf}, PBO={pbo_val:.3f}, DSR={dsr_p:.3f})")
    return result


def _write_bakeoff_report(result: dict, table: pd.DataFrame) -> None:
    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"e7_9_retrain_{result['target']}_{result['tier']}" + ("_smoke" if result["smoke"] else "")
    (_JSON_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, default=float))

    m = result["metric"]
    lines: list[str] = []
    a = lines.append
    a(f"# MLB Edge-{STORY} — retrain bake-off: {result['target']} ({result['tier']})")
    a("")
    if result["smoke"]:
        a("> ⚠️ **SMOKE RUN** — rows/estimators/arms capped. A harness check, NOT a result.")
        a("")
    a(f"> ⚠️ **Not an edge claim.** `best_alpha = {BEST_ALPHA}`. This decides whether the "
      "MiLB-MLE-corrected feature block and the newly-joined `eb_gb_pct` earn a retrained champion; "
      "it says nothing about win rate or ROI.")
    a("")
    a(f"**VERDICT: `{result['verdict']}`**")
    a("")
    a(f"- Honest metric **{m}** (lower = better) · {result['n_arms']} arms × "
      f"{result['n_folds']} purged/embargoed folds · {result['n_rows']:,} rows · seed {result['seed']}")
    a(f"- Incumbent arm `{result['incumbent_arm']}` = {result['incumbent_metric']:.4f}")
    a(f"- Leader `{result['leader_arm']}` = {result['leader_metric']:.4f} "
      f"(margin {result['margin_vs_incumbent']:+.4f}; noise floor {result['noise_floor']})")
    a(f"- PBO {result['pbo']:.3f} (gate < {PBO_MAX}) · DSR {result['dsr']:.3f} "
      f"(gate ≥ {DSR_MIN_CONF})")
    a(f"- Oracle-floor sanity (E2.1-r): oracle {m} = {result['oracle_metric']:.6f}; no candidate "
      "beat it ✅")
    a("")
    a("## Pre-registered gates")
    a("")
    a("| gate | result |")
    a("|---|---|")
    for k, v in result["gates"].items():
        a(f"| `{k}` | {'✅ pass' if v else '❌ fail'} |")
    a("")
    if result["verdict"] == "INCUMBENT_STANDS":
        a("**Reading the null honestly.** No arm clears every gate, so the served champion is "
          "unchanged and there is NO prediction backfill to run (E7.9 step 7 is conditional on a "
          "promotion). Per the E2.1-r note: if the top arms are TIED within the noise floor, a high "
          "PBO is the NULL — 'which tied arm wins is noise' — not evidence of overfitting. Check the "
          "spread in the table below before reading PBO as a failure.")
    else:
        a("**A challenger cleared every gate.** Promote per the model-promotion runbook, then run "
          "E7.9 step 7 (the historical prediction backfill) — labelled a BACKTEST, never a "
          "real-time record.")
    a("")
    a("## Contract variants")
    a("")
    a("| variant | features | added vs incumbent |")
    a("|---|---:|---|")
    for k, v in result["variants"].items():
        added = ", ".join(f"`{c}`" for c in v["added_vs_incumbent"]) or "— (the bar)"
        a(f"| `{k}` | {v['n_features']} | {added} |")
    if result["dropped_variants"]:
        a("")
        a(f"Dropped (added columns absent from the matrix): {result['dropped_variants']}. A dropped "
          "variant is NOT silently folded onto the incumbent — that would double-count an arm and "
          "understate the multiple-testing burden.")
    a("")
    a("## Full arm table")
    a("")
    a(f"| arm | variant | learner | {m} | PIT-KS | n |")
    a("|---|---|---|---:|---:|---:|")
    for r in table.to_dict("records"):
        a(f"| `{r['arm']}` | {r['variant']} | {r['learner']} | {r[f'{m}_mean']:.4f} | "
          f"{r['pit_ks']:.4f} | {r['n']:,} |")
    a("")
    (_ABL / f"{stem}.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{STORY} train/serve consistency: audit + retrain bake-off")
    ap.add_argument("--audit", action="store_true", help="Exposure audit only (fast, no fitting).")
    ap.add_argument("--bakeoff", action="store_true", help="Run the pre-registered retrain bake-off.")
    ap.add_argument("--target", choices=["total_runs", "run_diff"], default="total_runs")
    ap.add_argument("--tier", choices=["post_lineup", "pre_lineup"], default="post_lineup")
    ap.add_argument("--min-season", type=int, default=2021, help="Audit: earliest season to scope.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Re-pull the training matrix (REQUIRED after the E7.9 dbt join lands, or "
                         "the cached parquet has no eb_gb_pct columns).")
    ap.add_argument("--s3", action="store_true",
                    help="Read the training matrix from the S3 lakehouse via DuckDB instead of "
                         "Snowflake (repo doctrine; also the only source carrying eb_gb_pct before "
                         "the Snowflake external table is recreated). Pair with --refresh-cache.")
    ap.add_argument("--smoke", action="store_true", help="Cap rows/estimators for a harness check.")
    args = ap.parse_args()

    if not (args.audit or args.bakeoff):
        ap.error("pass --audit and/or --bakeoff")
    if args.audit:
        res = run_audit(args.min_season)
        skew = res["contracts_with_train_serve_skew"]
        print(f"\n[{STORY}] served contracts WITH train/serve skew: {skew or 'NONE'}")
        print(f"[{STORY}] report → {_ABL / 'e7_9_train_serve_audit.md'}")
    if args.bakeoff:
        run_retrain_bakeoff(args.target, args.tier, seed=args.seed, smoke=args.smoke,
                            refresh_cache=args.refresh_cache, embargo_days=args.embargo_days,
                            s3=args.s3)


if __name__ == "__main__":
    main()
