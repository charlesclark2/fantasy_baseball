"""Epic E12 (← master Story 30.3) — production serving-parity harness.

Answers the question 30.1 raised: the SAME home_win contract+model scores
corr 0.42 OFFLINE (feature-store surface) but ~0.001 LIVE. 30.1 proved the model
has skill, so the live zero-skill is a SERVING problem. This harness localizes it
by building, for one date, the EXACT matrix `predict_today.py` feeds each model and
comparing it — column-for-column — against the SERVED contract AND the training
distribution.

⭐ TIER-AWARE (E12, 2026-06-19). The morning slate no longer serves the champion:
Story 33.0 routes the live pre-lineup run to a DISTINCT pre-lineup model whose
contract drops the lineup-gated families that are legitimately NULL before lineups
post (home_win 211→156 cols, lineup-gated families 32→5). So diffing the sparse
morning matrix against the *champion* contract — what this harness used to do —
OVERSTATES the skew: it flags ~30% imputed for a model the morning tier never
serves. The harness now resolves the SAME serve variant `predict_today` would
(`--tier auto` → pre_lineup for a live/today run, champion for `--tier champion`
or a backfill), and reports parity against the contract that is ACTUALLY served.
`--champion-shadow` additionally shows what the champion WOULD impute on the same
matrix — i.e. WHY the morning run is routed to the pre-lineup model.

It reproduces predict_today's matrix construction faithfully:
    df_hist  = load_features(min_games_played=15)          # training/offline surface
    df_today = load_todays_features(date)                  # the LIVE serve path
    pipeline = build_imputation_pipeline().fit(X_hist)     # imputer fit on TRAIN
    X_today  = pipeline.transform(reindex(df_today))       # served, imputed matrix
and then, per served target contract, reports:
  - COUNT + ORDER parity of the served matrix vs the registry feature_columns_*.json
  - per-feature live state: structurally-absent | served-but-ALL-NULL (→ constant
    impute) | served-real, with the training-surface null rate alongside
  - the STRONG-TIER subset (the diffuse top drivers) called out separately, since
    a handful of those served null collapses the thin edge
  - a per-target **parity_ok** verdict (no structural-absent + no strong-tier
    null/absent within the served contract) and a process exit code, so the
    harness can GATE a serve, not just diagnose it.

⭐ The offline-vs-live paradox, made concrete: the feature store is NOT
point-in-time-snapshotted. Re-reading it for a *settled* date returns the
POST-game-backfilled (dense) row; the live serve only ever saw the PRE-game
(sparse) row. So run this for TODAY (date defaults to today) to capture the real
live-sparse profile — running it for a past date reads the dense backfill and will
*understate* the skew (that re-read is exactly why the 0.42 benchmark is optimistic).

Runtime: loads ~30k historical rows from Snowflake + fits the imputation pipeline —
minutes. Hand off to run with real credentials:

    uv run python betting_ml/scripts/serving_parity_report.py --date 2026-06-19
    uv run python betting_ml/scripts/serving_parity_report.py                 # today, pre_lineup tier
    uv run python betting_ml/scripts/serving_parity_report.py --tier champion # post-lineup / champion
    uv run python betting_ml/scripts/serving_parity_report.py --champion-shadow

`compute_target_parity` is a PURE function (no I/O) so the standing serving-parity
assertion (`betting_ml/tests/test_serving_parity_guard.py`) exercises the verdict
logic in CI without Snowflake.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, load_todays_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "serving_parity"
_REGISTRY_PATH = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
_TARGETS = ("total_runs", "run_differential", "home_win")

# Strong-tier home_win drivers (INFLUENCE_REPORT.md families: starter Stuff+,
# lineup xwoba-vs-cluster, EB posteriors, bullpen, platoon). These are the diffuse
# signal carriers — if they arrive null/constant live, the thin edge evaporates.
# Only the members that survive INTO the served contract are graded (a feature the
# served model doesn't use can't degrade its prediction), so this list is a superset
# spanning both tiers; `compute_target_parity` intersects it with each contract.
_STRONG_TIER = [
    "away_starter_stuff_plus", "home_starter_stuff_plus",
    "away_starter_changeup_stuff_plus", "home_starter_fastball_stuff_plus",
    "away_lineup_avg_xwoba_vs_cluster", "home_lineup_avg_xwoba_vs_cluster",
    "away_lineup_archetype_avg_xwoba", "home_lineup_archetype_avg_xwoba",
    "home_avg_eb_woba", "away_avg_eb_woba",
    "home_avg_eb_woba_sequential", "away_avg_eb_woba_sequential",
    "home_starter_eb_xwoba_against", "away_starter_eb_xwoba_against",
    "home_starter_eb_xwoba_against_sequential", "away_starter_eb_xwoba_against_sequential",
    "home_avg_xwoba_vs_lhp", "home_avg_xwoba_vs_rhp",
    "home_bp_eb_xwoba", "away_bp_eb_xwoba",
    "home_elo", "away_elo", "elo_diff",
    "away_win_pct", "home_win_pct",
]


def _load_contract(path: str) -> list[str]:
    raw = json.loads((PROJECT_ROOT / path).read_text())
    return raw["feature_cols"] if isinstance(raw, dict) else raw


def resolve_serve_variant(registry: dict, target: str, use_pre_lineup: bool) -> tuple[str, str]:
    """(variant_label, feature_columns_path) for `target` at this serve tier.

    Mirrors `scripts/predict_today.py::_resolve_serve_variant` EXACTLY so the
    harness grades the same contract the live serve would: when the live run is
    pre-lineup (Story 33.0: not lineup-confirmed and not a backfill) and a
    `pre_lineup` variant is wired, the morning tier serves it; otherwise the
    champion. FAIL-SAFE to champion so this is inert until all pre-lineup
    artifacts exist.
    """
    entry = registry[target]
    if (use_pre_lineup and entry.get("pre_lineup")
            and entry.get("pre_lineup_feature_columns_path")):
        return "pre_lineup", entry["pre_lineup_feature_columns_path"]
    return "prod", entry["feature_columns_path"]


def compute_target_parity(
    contract: list[str],
    served_cols: set[str],
    all_null_cols: set[str],
    strong_tier: list[str],
) -> dict:
    """PURE serving-parity verdict for one target (no I/O — unit-tested in CI).

    Args:
      contract:      the SERVED model's feature columns, in order.
      served_cols:   columns structurally present in the assembled+imputed matrix.
      all_null_cols: columns that are ENTIRELY NULL across the slate (→ each is
                     imputed to a single training constant for every game, i.e.
                     zero discrimination — the live-skill killer).
      strong_tier:   the diffuse top-driver superset; intersected with `contract`.

    Verdict (`parity_ok`) is True iff the served matrix is point-in-time COMPLETE
    for this contract's signal: NO structural-absent column (those get a silent
    0.0-fill the model never saw) AND NO strong-tier column flattened to a
    constant or absent. A non-strong feature served-all-null is reported but does
    NOT by itself fail parity (those are the odds/ump columns that are genuinely
    absent for some games and were null a comparable fraction of the time in
    training).
    """
    absent = [c for c in contract if c not in served_cols]
    served_but_all_null = [c for c in contract if c in all_null_cols]
    strong_in = [c for c in strong_tier if c in contract]
    strong_degraded = sorted(
        {c for c in strong_in if c in all_null_cols or c not in served_cols}
    )
    parity_ok = (len(absent) == 0) and (len(strong_degraded) == 0)
    return {
        "contract_len": len(contract),
        "served": len(contract) - len(absent),
        "absent": absent,
        "served_but_all_null": served_but_all_null,
        "imputed_to_constant_frac": round(len(served_but_all_null) / len(contract), 3) if contract else 0.0,
        "order_ok": len(absent) == 0,
        "strong_tier_total": len(strong_in),
        "strong_tier_degraded": strong_degraded,
        "parity_ok": parity_ok,
    }


def _build_served_matrix(df_hist: pd.DataFrame, df_today: pd.DataFrame,
                         serve_contracts: dict[str, list[str]]) -> set[str]:
    """Reproduce predict_today's served-matrix column set for the resolved tier.

    predict_today fits the imputation pipeline on `retained + total_runs +
    run_differential` SERVED contracts, then reindexes today's frame to the
    training columns and transforms. We mirror that to learn which columns the
    served+imputed matrix actually carries.
    """
    retained = load_retained_features()
    all_feat = list(dict.fromkeys(
        retained + serve_contracts["total_runs"] + serve_contracts["run_differential"]
    ))
    cols_hist = [c for c in all_feat if c in df_hist.columns]
    cols_today = [c for c in all_feat if c in df_today.columns]
    X_hist = df_hist[cols_hist]
    X_today_raw = df_today[cols_today].reindex(columns=X_hist.columns, fill_value=np.nan)
    pipeline = build_imputation_pipeline()
    X_hist_imp = pipeline.fit_transform(X_hist).select_dtypes(include=[np.number])
    X_today_imp = pipeline.transform(X_today_raw).reindex(columns=X_hist_imp.columns, fill_value=0.0)
    return set(X_today_imp.columns)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=_date.today().isoformat(),
                    help="slate to inspect (default: today — the only date with a true live-sparse profile)")
    ap.add_argument("--tier", choices=("auto", "pre_lineup", "champion"), default="auto",
                    help="which serve variant to grade. 'auto' (default) = pre_lineup for a "
                         "live/today run, mirroring predict_today's morning routing.")
    ap.add_argument("--champion-shadow", action="store_true",
                    help="also report what the CHAMPION contract would impute on the same "
                         "matrix (shows why the morning run is routed to the pre-lineup model).")
    ap.add_argument("--no-fail", action="store_true",
                    help="always exit 0 (diagnostic mode); default exits 1 if any served target fails parity.")
    args = ap.parse_args()
    target_date = args.date
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    # Mirror predict_today: pre-lineup tier is the LIVE (not lineup-confirmed, not
    # backfill) run. The harness has no lineup-confirmed/backfill switches, so:
    #   auto/pre_lineup → use_pre_lineup=True ; champion → False.
    use_pre_lineup = args.tier in ("auto", "pre_lineup")
    serve_variant = {t: resolve_serve_variant(registry, t, use_pre_lineup) for t in _TARGETS}
    serve_contracts = {t: _load_contract(p) for t, (_, p) in serve_variant.items()}
    champion_contracts = {t: _load_contract(registry[t]["feature_columns_path"]) for t in _TARGETS}
    tier_label = serve_variant["home_win"][0]
    print(f"[parity] tier={tier_label} | "
          + ", ".join(f"{t}={serve_variant[t][0]}({len(serve_contracts[t])})" for t in _TARGETS))

    print(f"[parity] loading LIVE serve path for {target_date} ...")
    df_today = load_todays_features(target_date)
    if df_today.empty:
        print(f"No games for {target_date}; nothing to compare.")
        return 0
    data_source = df_today["data_source"].iloc[0] if "data_source" in df_today.columns else "unknown"
    n_today = len(df_today)
    print(f"[parity] {n_today} game(s); live data_source={data_source}")

    print("[parity] loading training/offline surface (load_features) ...")
    df_hist = load_features(min_games_played=15)
    print(f"[parity] {len(df_hist):,} historical rows")

    served_cols = _build_served_matrix(df_hist, df_today, serve_contracts)
    # Columns entirely NULL across the slate → constant-imputed for every game.
    all_null_cols = {c for c in df_today.columns if df_today[c].isna().all()}
    train_null = {c: float(df_hist[c].isna().mean()) for c in df_hist.columns}

    report: dict = {
        "date": target_date, "data_source": data_source, "n_games": n_today,
        "tier": tier_label, "targets": {},
    }
    md = [f"# E12 Serving-Parity Report ({target_date}) — tier `{tier_label}`", "",
          f"- Live `data_source`: **{data_source}**, {n_today} game(s)",
          f"- Served tier: **{tier_label}** "
          + "(" + ", ".join(f"`{t}`={len(serve_contracts[t])}" for t in _TARGETS) + ")",
          "",
          "Per SERVED target: how the LIVE served matrix compares to the contract the",
          "morning tier actually serves and to the training distribution.",
          "`served-but-ALL-NULL` columns are imputed to a single training-median constant",
          "for every game → zero discrimination. `parity_ok` fails only on a structural-absent",
          "column or a STRONG-TIER column flattened/absent (the live-skill killers).",
          ""]

    any_fail = False
    for tgt in _TARGETS:
        cols = serve_contracts[tgt]
        r = compute_target_parity(cols, served_cols, all_null_cols, _STRONG_TIER)
        r["variant"] = serve_variant[tgt][0]
        report["targets"][tgt] = r
        any_fail = any_fail or (not r["parity_ok"])
        verdict = "✅ PASS" if r["parity_ok"] else "❌ FAIL"
        md += [f"## {tgt} — {r['variant']} (contract {r['contract_len']})  {verdict}", "",
               f"- structurally served: **{r['served']}/{r['contract_len']}**  "
               f"(absent→0.0-fill: {len(r['absent'])})",
               f"- served-but-ALL-NULL→constant-impute: **{len(r['served_but_all_null'])}**  "
               f"(**{r['imputed_to_constant_frac']:.0%}** of the matrix flattened to a constant live)",
               f"- column ORDER parity: {'OK (all present, reindex preserves contract order)' if r['order_ok'] else 'BROKEN — absent cols below'}",
               f"- STRONG-TIER served null/absent: **{len(r['strong_tier_degraded'])}/{r['strong_tier_total']}**"
               f"{' → ' + ', '.join(r['strong_tier_degraded']) if r['strong_tier_degraded'] else ''}",
               ""]
        if r["served_but_all_null"]:
            md += ["<details><summary>served-but-all-null columns (live null / train null)</summary>", ""]
            for c in sorted(r["served_but_all_null"]):
                md.append(f"  - `{c}` — train null {train_null.get(c, float('nan')):.2%}")
            md += ["", "</details>", ""]
        if r["absent"]:
            md += ["**ABSENT (silently 0.0-filled — structural gap):** "
                   + ", ".join(f"`{c}`" for c in r["absent"]), ""]

    # --- Champion-shadow: what the champion contract WOULD impute on this matrix --
    if args.champion_shadow and tier_label != "prod":
        md += ["---", "", "## Champion-shadow (why morning routes to pre-lineup)", "",
               "What the **champion** contract would have imputed on the SAME morning matrix —",
               "the gap the Story 33.0 tier-split sidesteps by serving the pre-lineup model.", ""]
        report["champion_shadow"] = {}
        for tgt in _TARGETS:
            r = compute_target_parity(champion_contracts[tgt], served_cols, all_null_cols, _STRONG_TIER)
            report["champion_shadow"][tgt] = r
            md += [f"- **{tgt}** champion ({r['contract_len']}): "
                   f"{len(r['served_but_all_null'])} all-null→const "
                   f"({r['imputed_to_constant_frac']:.0%}), "
                   f"strong-tier degraded {len(r['strong_tier_degraded'])}/{r['strong_tier_total']}"]
        md += [""]

    suffix = f"_{tier_label}"
    out_json = _OUT_DIR / f"parity_{target_date}{suffix}.json"
    out_md = _OUT_DIR / f"parity_{target_date}{suffix}.md"
    out_json.write_text(json.dumps(report, indent=2, default=float))
    out_md.write_text("\n".join(md))
    print(f"[parity] wrote {out_md}")
    print(f"[parity] wrote {out_json}")

    for tgt, r in report["targets"].items():
        print(f"  {tgt} ({r['variant']}): {r['served']}/{r['contract_len']} served | "
              f"{len(r['served_but_all_null'])} all-null→const ({r['imputed_to_constant_frac']:.0%}) | "
              f"strong-tier degraded {len(r['strong_tier_degraded'])}/{r['strong_tier_total']} | "
              f"{'PASS' if r['parity_ok'] else 'FAIL'}")

    if any_fail and not args.no_fail:
        print("[parity] ❌ at least one served target FAILED parity — see report above.")
        return 1
    print("[parity] ✅ all served targets pass point-in-time parity.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
