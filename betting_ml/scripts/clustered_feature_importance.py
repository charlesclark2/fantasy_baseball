"""clustered_feature_importance.py — Epic E1.3: clustered MDA under purged CV.

WHY (AFML §8.4–8.5)
-------------------
The feature surface (`feature_pregame_game_features`, ~690 cols) is heavily collinear:
`home_*`/`away_*` mirror pairs, the same stat at 7d/14d/30d windows, EB-shrunk and raw
variants of the same quantity. Single-feature importances (and MDI in particular) are
BIASED in that setting — signal carried by a *concept* gets diluted across its six
near-duplicate columns, and high-cardinality columns absorb spurious importance. The Layer-3
stacking weights coming out "near-uniform" is the classic symptom.

The fix is **clustered MDA**: cluster the features into concepts (hierarchical on `1 − |ρ|`),
then shuffle each *cluster together* and measure the out-of-sample score degradation under
the purged walk-forward CV (E1.1). That attributes signal to a concept ("starter suppression
block", "bullpen contact-quality block") instead of to one column with five substitutes — and
clusters whose importance is statistically indistinguishable from noise (paired-bootstrap CI
crossing 0) can be dropped/consolidated, shrinking the overfitting surface for E2–E4.

WHAT IT DOES
------------
1. Load the training matrix (cached parquet → no repeated Snowflake scans, §6).
2. Take the target's active feature contract; impute; cluster on `1 − |ρ|` (hierarchical,
   `--corr-threshold` controls granularity).
3. For each PURGED fold: fit the champion recipe once (baseline OOS score), then for each
   cluster shuffle ALL its columns together in the eval matrix (`--n-repeats` permutations)
   and re-score. Importance = mean OOS score degradation (loss goes UP when a real concept
   is destroyed).
4. Pool per-game (shuffled − baseline) deltas across folds; season-stratified paired
   bootstrap CI per cluster. CI entirely > 0 ⇒ the concept carries signal; CI crossing 0 ⇒
   noise (drop candidate).
5. Write `ablation_results/clustered_feature_importance.md` + a JSON sidecar.

COST (§6): NGBoost/XGB is refit once per fold (the heavy part); MDA only RE-PREDICTS per
cluster/permutation (cheap). Still a multi-minute job — HAND OFF to run with Snowflake creds.
Periodic, not daily. One `--target` per invocation (parallelizable; see
`[[feedback_retrain_per_target]]`).

Usage:
    uv run python betting_ml/scripts/clustered_feature_importance.py --target total_runs
    uv run python betting_ml/scripts/clustered_feature_importance.py --target home_win --corr-threshold 0.7
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.promotion_gate_eval import (
    _TARGETS, _build_specs, _contract_cols, _reconstruct_champion_cols,
)
from betting_ml.utils.cv import PurgedWalkForwardSplit
from betting_ml.utils.data_loader import get_snowflake_connection, load_features
from betting_ml.utils.training_cache import get_cached_df

_REPORT_DIR = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_JSON_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "clustered_importance"


# ── Story E2.1b: bullpen_v3 swap-in for the honest MDA re-check ────────────────
# Replaces the STATIC home/away `bp_eb_xwoba` (+ uncertainty) columns in the training
# matrix with the expected-leverage×availability-weighted `bullpen_v3` values, so we can
# re-run this exact clustered-MDA and report whether bullpen-EB importance DROPS once the
# leaky outs-weighting is gone (the required E2.1b honesty check). Default `static` leaves
# the matrix untouched.

def _swap_bullpen_v3(df: pd.DataFrame, shrinkage_k: float) -> pd.DataFrame:
    from betting_ml.scripts.eb_priors.compute_bullpen_v3 import aggregate_team_v3, _cache_path

    seasons = sorted({int(y) for y in pd.to_numeric(df["game_year"]).dropna().unique()})
    frames = []
    for s in seasons:
        p = _cache_path(s)
        if p.exists():
            frames.append(pd.read_parquet(p))
        else:
            print(f"  [warn] no bullpen_v3 cache for season {s} ({p.name}); "
                  f"run compute_bullpen_v3.py --backfill-season {s} first.")
    if not frames:
        raise FileNotFoundError("No bullpen_v3 per-reliever caches found — cannot run the v3 MDA re-check.")
    team = aggregate_team_v3(pd.concat(frames, ignore_index=True), shrinkage_k=shrinkage_k)
    team["game_pk"] = team["game_pk"].astype(str)
    tv = team.set_index(["game_pk", "team"])

    out = df.copy()
    out["game_pk"] = out["game_pk"].astype(str)
    # The training frame already carries team abbreviations; only fall back to a
    # mart_game_results join if a future schema drops them.
    if "home_team" not in out.columns or "away_team" not in out.columns:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "select game_pk::varchar game_pk, home_team, away_team "
                "from baseball_data.betting.mart_game_results where game_type = 'R' "
                f"and game_year >= {seasons[0]}"
            )
            sides = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
        finally:
            conn.close()
        out = out.merge(sides, on="game_pk", how="left")
    n_swapped = 0
    for side in ("home", "away"):
        idx = list(zip(out["game_pk"], out[f"{side}_team"].astype(str)))
        for src_col, dst_col in (("team_eb_bullpen_xwoba_v3", f"{side}_bp_eb_xwoba"),
                                 ("team_eb_bullpen_uncertainty_v3", f"{side}_bp_eb_uncertainty")):
            if dst_col in out.columns:
                new = pd.Series(tv[src_col].reindex(idx).to_numpy(), index=out.index)
                # keep the static value where v3 is missing (no pool / pre-2021 sparsity)
                out[dst_col] = new.where(new.notna(), out[dst_col])
                if src_col == "team_eb_bullpen_xwoba_v3":
                    n_swapped += int(new.notna().sum())
    print(f"  bullpen_v3 swap-in (k={shrinkage_k}): {n_swapped} home/away cells replaced "
          f"across {len(out)} games")
    return out.drop(columns=["home_team", "away_team"], errors="ignore")


# ── Story E1.8: leakage-safe (prior-season) Stuff+/arsenal swap-in ─────────────
# E1.8's leakage sweep found the FanGraphs Stuff+/arsenal block is LEAKY-season-to-date:
# `feature_pregame_starter_features` joins `fct_fangraphs_pitcher_arsenal_wide` on
# `season = year(game_date)` with NO `< game_date` guard, and the source is grain
# pitcher×season at the LATEST ingestion — so each historical game gets the full-season
# (end-of-state) value, embedding game-G-and-later pitches. The leakage-safe reconstruction
# is the SAME starter's PRIOR-SEASON arsenal (`season = game_year - 1`), mirroring how the
# platoon splits (mart_pitcher_vs_handedness_splits, game_year-1) and team OAA already key
# season-grain FanGraphs data. `deleaked` swaps it in so this exact clustered-MDA reports
# whether the Stuff+ block's importance survives the de-leak (the E2.1b template, applied to
# the E1.8 finding). Default `leaky` leaves the matrix untouched.

# arsenal-wide source column → starter feature suffix (matrix col = f"{side}_{suffix}")
_STUFF_ARSENAL_MAP = {
    "overall_stuff_plus":    "starter_stuff_plus",
    "fastball_stuff_plus":   "starter_fastball_stuff_plus",
    "slider_stuff_plus":     "starter_slider_stuff_plus",
    "curveball_stuff_plus":  "starter_curveball_stuff_plus",
    "changeup_stuff_plus":   "starter_changeup_stuff_plus",
    "avg_fastball_velo_mph": "starter_avg_fastball_velo",
    "fastball_pct":          "starter_fastball_pct",
    "breaking_pct":          "starter_breaking_pct",
    "offspeed_pct":          "starter_offspeed_pct",
}


def _swap_stuff_plus_deleaked(df: pd.DataFrame) -> pd.DataFrame:
    """Replace the leaky current-season Stuff+/arsenal columns with the starter's
    PRIOR-SEASON arsenal (the leakage-safe reconstruction).

    Keeps the leaky value where the prior season is missing (rookies / first MLB season) —
    a minimal-change A/B, the same fallback convention as `_swap_bullpen_v3`; the fallback
    count is printed so the operator can read how much of the block was actually de-leaked.
    NOTE: only the non-windowed season-arsenal columns are swapped — the rolling
    `*_avg_fastball_velo_{7d,14d,30d,std}` columns are AS-OF-safe (E1.8) and untouched.
    """
    min_year = int(pd.to_numeric(df["game_year"]).min())
    src_cols = ", ".join(f"a.{c}" for c in _STUFF_ARSENAL_MAP)
    q = (
        "select s.game_pk::varchar as game_pk, lower(s.side) as side, " + src_cols + " "
        "from baseball_data.betting_features.feature_pregame_starter_features s "
        "left join baseball_data.betting.fct_fangraphs_pitcher_arsenal_wide a "
        "  on a.mlbam_pitcher_id = s.pitcher_id and a.season = s.game_year - 1 "
        f"where s.game_year >= {min_year}"
    )
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(q)
        pri = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
    finally:
        conn.close()
    if pri.empty:
        raise RuntimeError("prior-season arsenal query returned no rows — cannot run the Stuff+ de-leak A/B.")
    pri["game_pk"] = pri["game_pk"].astype(str)

    out = df.copy()
    out["game_pk"] = out["game_pk"].astype(str)
    keys = out["game_pk"].to_numpy()
    n_total = n_fallback = 0
    for side in ("home", "away"):
        ps = pri[pri["side"] == side].drop_duplicates("game_pk").set_index("game_pk")
        for src_col, suffix in _STUFF_ARSENAL_MAP.items():
            dst = f"{side}_{suffix}"
            if dst not in out.columns or src_col not in ps.columns:
                continue
            new = pd.Series(
                pd.to_numeric(ps[src_col].reindex(keys), errors="coerce").to_numpy(),
                index=out.index,
            )
            present = new.notna()
            n_total += int(present.sum())
            n_fallback += int((~present & out[dst].notna()).sum())
            out[dst] = new.where(present, out[dst])      # keep leaky where prior-season missing
    print(f"  Stuff+ de-leak swap-in: {n_total} cells repointed to prior-season "
          f"({n_fallback} kept leaky as rookie/no-prior fallback) across {len(out)} games")
    return out


def _cluster_features(X: pd.DataFrame, corr_threshold: float) -> dict[int, list[str]]:
    """Hierarchical clustering of columns on distance `1 − |ρ|`.

    Average-linkage; cut at `1 − corr_threshold` so columns with |ρ| ≥ corr_threshold to the
    cluster land together. Returns {cluster_id: [col, ...]}. Falls back to one-column-per-
    cluster if SciPy is unavailable.
    """
    cols = list(X.columns)
    if len(cols) < 2:
        return {0: cols}
    corr = np.corrcoef(np.nan_to_num(X.values, nan=0.0), rowvar=False)
    corr = np.clip(np.nan_to_num(corr, nan=0.0), -1.0, 1.0)
    dist = 1.0 - np.abs(corr)
    np.fill_diagonal(dist, 0.0)
    try:
        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import squareform
        condensed = squareform(dist, checks=False)
        Z = linkage(condensed, method="average")
        labels = fcluster(Z, t=1.0 - corr_threshold, criterion="distance")
    except Exception as exc:  # pragma: no cover
        print(f"  [warn] SciPy clustering unavailable ({exc}); one cluster per column.")
        labels = np.arange(1, len(cols) + 1)
    clusters: dict[int, list[str]] = {}
    for col, lab in zip(cols, labels):
        clusters.setdefault(int(lab), []).append(col)
    # Re-key by descending size for stable, readable cluster ids.
    ordered = sorted(clusters.values(), key=len, reverse=True)
    return {i: members for i, members in enumerate(ordered)}


def _score_per_game(out, y, metric: str) -> np.ndarray:
    return out.score_to_truth(np.asarray(y, float), metric)


def _champion_cols(name: str, cfg: dict, df: pd.DataFrame) -> list[str]:
    if cfg["champion_kind"] == "reconstruct":
        return _reconstruct_champion_cols(df)
    return _contract_cols(cfg["champion_contract"], df)


def run(target: str, *, corr_threshold: float, n_repeats: int, seed: int,
        refresh_cache: bool, use_champion: bool, embargo_days: int,
        bullpen_version: str = "static", shrinkage_k: float = 1.0,
        stuff_plus_version: str = "leaky") -> dict:
    cfg = _TARGETS[target]
    metric = cfg["metric"]
    df = get_cached_df("edge_e1_training", load_features, refresh=refresh_cache).reset_index(drop=True)
    print(f"Loaded {len(df)} rows; seasons {sorted(df['game_year'].dropna().unique().tolist())}")

    if bullpen_version == "v3":
        print(f"E2.1b re-check: swapping STATIC bullpen EB → bullpen_v3 (k={shrinkage_k}) ...")
        df = _swap_bullpen_v3(df, shrinkage_k).reset_index(drop=True)

    if stuff_plus_version == "deleaked":
        print("E1.8 re-check: swapping LEAKY season-to-date Stuff+/arsenal → prior-season (leakage-safe) ...")
        df = _swap_stuff_plus_deleaked(df).reset_index(drop=True)

    # The feature set we audit: the champion-of-record contract (use_champion) or the active
    # tuned challenger contract (default — that is the set E2–E4 would inherit).
    if use_champion:
        feat_cols = _champion_cols(target, cfg, df)
        spec, _ = _build_specs(target, cfg, seed=seed)
    else:
        feat_cols = _contract_cols(cfg["challenger_contract"], df)
        _, spec = _build_specs(target, cfg, seed=seed)
    print(f"Auditing {len(feat_cols)} features with recipe {spec.name}")

    # Cluster on the imputed FULL matrix (cluster structure is a property of the features,
    # not a fold) so cluster ids are stable across folds.
    X_full, _ = _impute(df[feat_cols], df[feat_cols])
    clusters = _cluster_features(X_full, corr_threshold)
    print(f"Formed {len(clusters)} clusters at |ρ|≥{corr_threshold} "
          f"(largest={max(len(c) for c in clusters.values())} cols)")

    splitter = PurgedWalkForwardSplit(embargo_days=embargo_days)
    rng = np.random.default_rng(seed)

    # Accumulate per-game (shuffled − baseline) deltas per cluster across folds, tagged by
    # season for the stratified paired bootstrap.
    deltas: dict[int, list[np.ndarray]] = {cid: [] for cid in clusters}
    seasons: list[np.ndarray] = []
    base_scores: list[np.ndarray] = []
    for train_idx, eval_idx in splitter.split(df, feature_cols=feat_cols):
        yr = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        ytr = df.loc[train_idx, cfg["target_col"]].values
        yev = df.loc[eval_idx, cfg["target_col"]].values
        Xtr, Xev = _impute(df.loc[train_idx, feat_cols], df.loc[eval_idx, feat_cols])
        # Fit ONCE per fold (calibrate on the unpermuted eval); MDA holds this model fixed
        # and only re-PREDICTS on permuted eval matrices — fast and sound.
        predictor = spec.fit(Xtr, ytr, Xev, yev)
        base = _score_per_game(predictor.output(Xev), yev, metric)
        seasons.append(np.full(len(yev), yr))
        base_scores.append(base)
        print(f"  fold {yr}: baseline {metric}={base.mean():.4f} (n={len(yev)}), "
              f"train={len(Xtr)} after purge")
        cols_set = set(Xev.columns)
        for cid, members in clusters.items():
            present = [c for c in members if c in cols_set]
            if not present:
                deltas[cid].append(np.zeros(len(yev)))
                continue
            rep = np.zeros(len(yev))
            for _ in range(n_repeats):
                Xp = Xev.copy()
                perm = rng.permutation(len(Xp))
                Xp[present] = Xp[present].values[perm]            # shuffle cluster JOINTLY
                rep += _score_per_game(predictor.output(Xp), yev, metric)
            deltas[cid].append(rep / n_repeats - base)

    season = np.concatenate(seasons)
    rows = _aggregate(clusters, deltas, season, seed=seed)
    payload = {
        "target": target, "metric": metric, "recipe": spec.name,
        "n_features": len(feat_cols), "n_clusters": len(clusters),
        "corr_threshold": corr_threshold, "n_repeats": n_repeats,
        "pooled_baseline": float(np.concatenate(base_scores).mean()),
        "bullpen_version": bullpen_version,
        "stuff_plus_version": stuff_plus_version,
        "clusters": rows,
    }
    suffix_parts = []
    if bullpen_version != "static":
        suffix_parts.append(f"bullpen_{bullpen_version}")
    if stuff_plus_version != "leaky":
        suffix_parts.append(f"stuffplus_{stuff_plus_version}")
    _write_report(payload, suffix=("_" + "_".join(suffix_parts)) if suffix_parts else "")
    return payload


def _aggregate(clusters, deltas, season, *, seed: int, n_boot: int = 2000) -> list[dict]:
    """Per-cluster pooled importance + season-stratified paired-bootstrap CI on the delta.

    Importance = mean OOS score degradation when the cluster is shuffled (loss metric → a
    POSITIVE delta means destroying the concept hurt accuracy ⇒ the concept carried signal).
    CI entirely above 0 ⇒ real; CI crossing 0 ⇒ noise (drop candidate).
    """
    rng = np.random.default_rng(seed + 7)
    seasons_u = sorted({int(s) for s in np.unique(season)})
    idx_by_season = {s: np.where(season == s)[0] for s in seasons_u}
    rows = []
    for cid, members in clusters.items():
        d = np.concatenate(deltas[cid])
        boots = np.empty(n_boot)
        for b in range(n_boot):
            parts = [d[rng.choice(idx_by_season[s], size=len(idx_by_season[s]), replace=True)]
                     for s in seasons_u]
            boots[b] = np.concatenate(parts).mean()
        lo, hi = float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))
        importance = float(d.mean())
        rows.append({
            "cluster_id": cid, "n_features": len(members), "importance": importance,
            "ci_low": lo, "ci_high": hi, "is_noise": bool(lo <= 0.0 <= hi),
            "members": members,
        })
    rows.sort(key=lambda r: r["importance"], reverse=True)
    return rows


def _write_report(payload: dict, suffix: str = "") -> None:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    target = payload["target"]
    jpath = _JSON_DIR / f"clustered_importance_{target}{suffix}.json"
    jpath.write_text(json.dumps(payload, indent=2, default=float))

    rows = payload["clusters"]
    n_noise = sum(r["is_noise"] for r in rows)
    noise_feats = sum(r["n_features"] for r in rows if r["is_noise"])
    total_feats = payload["n_features"]
    lines = [
        f"# Clustered Feature Importance — {target} (Epic E1.3)",
        "",
        f"- Recipe: `{payload['recipe']}` · metric **{payload['metric']}** (lower = better) · "
        f"pooled baseline {payload['pooled_baseline']:.4f}",
        f"- Features: **{total_feats}** in **{payload['n_clusters']}** clusters "
        f"(`|ρ| ≥ {payload['corr_threshold']}`), {payload['n_repeats']} MDA permutations/fold, purged CV (E1.1)",
        f"- **Noise clusters (CI crosses 0): {n_noise}/{payload['n_clusters']}** "
        f"covering **{noise_feats}/{total_feats}** features → drop/consolidate candidates "
        f"(≈{noise_feats/total_feats:.0%} dimensionality cut with no expected accuracy loss)",
        "",
        "Importance = mean OOS **score degradation** when the whole cluster is shuffled "
        "together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). "
        "Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing "
        "concept, a CI crossing 0 is indistinguishable from noise.",
        "",
        "| rank | cluster | #feat | importance (Δ" + payload["metric"] + ") | 95% CI | verdict | top members |",
        "|---|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(rows, 1):
        members = ", ".join(r["members"][:4]) + (" …" if r["n_features"] > 4 else "")
        verdict = "🟡 noise → drop" if r["is_noise"] else "✅ signal"
        lines.append(f"| {rank} | C{r['cluster_id']} | {r['n_features']} | {r['importance']:+.5f} | "
                     f"[{r['ci_low']:+.5f}, {r['ci_high']:+.5f}] | {verdict} | `{members}` |")
    lines += ["",
              "## Payoff (E1.3 AC)",
              f"Dropping the {n_noise} noise clusters ({noise_feats} features) is the "
              "dimensionality cut to verify value-preserving: re-run the promotion gate "
              "(`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no "
              "accuracy regression beyond the noise floor before promoting the smaller set.",
              "",
              f"_JSON: `{jpath.relative_to(PROJECT_ROOT)}`_"]
    rpath = _REPORT_DIR / f"clustered_feature_importance_{target}{suffix}.md"
    rpath.write_text("\n".join(lines))
    print(f"\nWrote {rpath}")
    print(f"Wrote {jpath}")
    print(f"\n→ {n_noise}/{payload['n_clusters']} clusters are noise "
          f"({noise_feats}/{total_feats} features droppable)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs"], required=True,
                    help="One target per invocation (parallelizable; see feedback_retrain_per_target).")
    ap.add_argument("--corr-threshold", type=float, default=0.75,
                    help="|ρ| at/above which columns cluster together (higher = finer clusters).")
    ap.add_argument("--n-repeats", type=int, default=3, help="MDA shuffle permutations per cluster/fold.")
    ap.add_argument("--embargo-days", type=int, default=3, help="Purged-CV embargo (E1.1).")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--refresh-cache", action="store_true", help="Re-pull the training matrix from Snowflake.")
    ap.add_argument("--use-champion", action="store_true",
                    help="Audit the champion-of-record contract instead of the active tuned challenger set.")
    ap.add_argument("--bullpen-version", choices=["static", "v3"], default="static",
                    help="E2.1b honesty check: 'v3' swaps the static bullpen EB for bullpen_v3 "
                         "(needs compute_bullpen_v3 caches) and writes *_bullpen_v3 outputs to "
                         "compare whether bullpen-EB importance drops once the leaky weighting is gone.")
    ap.add_argument("--shrinkage-k", type=float, default=1.0,
                    help="bullpen_v3 prior-precision multiplier (use the k the CV gate picked).")
    ap.add_argument("--stuff-plus-version", choices=["leaky", "deleaked"], default="leaky",
                    help="E1.8 honesty check: 'deleaked' repoints the LEAKY season-to-date "
                         "Stuff+/arsenal block to the starter's PRIOR-SEASON arsenal (leakage-safe) "
                         "and writes *_stuffplus_deleaked outputs, to compare whether the Stuff+ "
                         "block's importance survives the de-leak.")
    args = ap.parse_args()
    run(args.target, corr_threshold=args.corr_threshold, n_repeats=args.n_repeats,
        seed=args.seed, refresh_cache=args.refresh_cache, use_champion=args.use_champion,
        embargo_days=args.embargo_days, bullpen_version=args.bullpen_version,
        shrinkage_k=args.shrinkage_k, stuff_plus_version=args.stuff_plus_version)


if __name__ == "__main__":
    main()
