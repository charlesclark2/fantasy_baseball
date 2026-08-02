"""run_nf1_feature_importance.py — NF3.4: export the NF1 GBM's per-PLAYER feature contributions.

NF3.4 asks for a transparency panel on the player page — "what components about a player contribute
to their ranking", i.e. a genuine PER-PLAYER attribution, not a position-level description. The one
model in this package that is actually fitted (and so can be introspected at all) is NF1's bake-off
winner (PooledGBM/LightGBM — see `ablation_results/nf1_season_bakeoff.json`, winner="gbm"); MVP-1
(the SERVED projection, `season_projection.py`) is a fixed heuristic pipeline with nothing to
introspect. This script fits that same validated NF1 model, then uses LightGBM's own exact TreeSHAP
(`pred_contrib=True` — no external `shap` dependency) to get, for every currently-projected veteran,
how many fantasy points each signal is estimated to add or subtract for HIM specifically. See
`nf1_model.player_feature_contributions`'s docstring for the honest-labelling contract (still NF1's
own number, not necessarily the served MVP-1 total).

A secondary, POSITION-level report (`nf1_model.feature_importance_report` — "what does the model lean
on for QBs in general") is also written, purely as a research/documentation artifact
(`ablation_results/nf1_feature_importance.md`) — it is NOT what the player page surfaces.

Two different data sources, two different freshness stories:
  * the per-player step needs the CURRENT feature matrix (today's veteran board) — reads the local
    dbt-built `sports_dbt/sports.duckdb` (SF-free, no network; `--duckdb`/`--schema` override it).
    Rookies are NOT covered (NF1 has no base-season feature row to attribute for a rookie — see
    `build_season_projection`'s module docstring); they simply don't appear in `players`, and the
    exporter/UI must treat that as expected, not a defect.
  * the position-level step is offline-only, reading the walk-forward training pool cached under
    `artifacts/nf1_feature_cache/pool_base<season>.parquet` (no DuckDB connection at all).

Usage:
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf1_feature_importance
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf1 import (  # noqa: E402
    MARTS_SCHEMA,
    assemble_features,
    build_training_pool,
)

log = logging.getLogger("nfl.fantasy.nf1_feature_importance")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_BAKEOFF_JSON = _REPORT_DIR / "nf1_season_bakeoff.json"
_DEFAULT_DUCKDB = "quant_sports_intel_models/sports_dbt/sports.duckdb"
_OUT_POSITION_JSON = _ART / "nf1_feature_importance.json"
_OUT_POSITION_MD = _REPORT_DIR / "nf1_feature_importance.md"
_OUT_PLAYER_JSON = _ART / "nf1_player_contributions.json"


def _load_winner_hp() -> tuple[list[int], dict]:
    """The bake-off's own base seasons + tuned hyperparameters for the winning learner ("gbm") — reuse
    what was already validated rather than re-guessing a config here."""
    d = json.loads(_BAKEOFF_JSON.read_text())
    if d.get("winner") != "gbm":
        raise SystemExit(
            f"nf1_season_bakeoff.json winner is {d.get('winner')!r}, not 'gbm' — this script is "
            f"written for PooledGBM only. Re-check before re-running."
        )
    return d["base_seasons"], d["winner_hp"]


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb", default=_DEFAULT_DUCKDB,
                    help="local dbt-built DuckDB with the NFL marts (for the per-player step)")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--top-n", type=int, default=6, help="drivers shown per player")
    return ap


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_arg_parser().parse_args(argv)

    base_seasons, hp = _load_winner_hp()
    log.info("winner hp from %s: base_seasons=%s hp=%s", _BAKEOFF_JSON.name, base_seasons, hp)

    pool = build_training_pool(None, base_seasons, use_cache=True)
    if pool.empty:
        raise SystemExit(
            f"empty training pool for base_seasons={base_seasons} — one of the "
            f"nf1_feature_cache/pool_base<season>.parquet files is missing. Run run_nf1.py's bakeoff "
            f"mode first (needs the lake) if a cache file is genuinely absent."
        )
    log.info("pool: %d rows", len(pool))

    # ── position-level (research/documentation artifact only) ──────────────────────────────────
    position_report = M.feature_importance_report(pool, hp)
    position_report["generated_at"] = datetime.now(timezone.utc).isoformat()
    position_report["base_seasons"] = base_seasons
    _ART.mkdir(parents=True, exist_ok=True)
    _OUT_POSITION_JSON.write_text(json.dumps(position_report, indent=2))
    _write_position_report_md(position_report)
    log.info("wrote %s + %s (research artifact, not surfaced in the app)",
             _OUT_POSITION_JSON.name, _OUT_POSITION_MD.name)

    # ── per-player (what the app actually surfaces) ─────────────────────────────────────────────
    duckdb_path = _PROJECT_ROOT / args.duckdb
    if not duckdb_path.is_file():
        raise SystemExit(
            f"no DuckDB at {duckdb_path} — the per-player step needs the local dbt-built NFL marts "
            f"(see run_nf1.py's docstring: `python -m dbt.cli.main run --select nfl.staging nfl.marts "
            f"--threads 1` from sports_dbt/). Pass --duckdb to point at a different build."
        )
    import duckdb

    learner = M.PooledGBM(feats=M.FEATURES, **hp)
    import numpy as np
    import pandas as pd

    y = pd.to_numeric(pool["real_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    pos = np.array([str(p) for p in pool["position"]], dtype=object)
    learner.fit(pool, y, pos)

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        base_season = int(con.sql(
            f"select max(season) from {args.schema}.fct_player_week where played_flag"
        ).fetchone()[0])
        projection_season = base_season + 1
        current = assemble_features(con, base_season, projection_season, args.schema)
    finally:
        con.close()
    if current.empty:
        raise SystemExit(f"assemble_features returned no rows for base_season={base_season} — "
                          f"check the marts are built ({args.schema}).")
    log.info("current veteran feature matrix: %d players (base_season=%d -> projection_season=%d)",
             len(current), base_season, projection_season)

    cur_pos = np.array([str(p) for p in current["position"]], dtype=object)
    F = learner._frame(current, cur_pos)
    F["_pos"] = F["_pos"].astype("category")
    player_ids = current["player_id"].astype(str).tolist()

    contributions = M.player_feature_contributions(learner._model, F, player_ids, top_n=args.top_n)
    legend = {
        f: {"label": M.FEATURE_LABELS[f], "description": M.FEATURE_DESCRIPTIONS[f]}
        for f in M.FEATURES if f not in M._TAUTOLOGICAL_FEATURES
    }
    payload = {
        "model_version": M.MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_season": base_season,
        "projection_season": projection_season,
        "n_players": len(contributions),
        "legend": legend,
        "players": contributions,
    }
    _OUT_PLAYER_JSON.write_text(json.dumps(payload, separators=(",", ":")))
    log.info("wrote %s (%d players)", _OUT_PLAYER_JSON.name, len(contributions))
    return 0


def _write_position_report_md(report: dict) -> None:
    lines = [
        "# NF3.4 — NF1 position-level feature importance (research artifact, NOT the app panel)",
        "",
        "⚠️ The player page surfaces PER-PLAYER contributions (`nf1_player_contributions.json`), not "
        "this report — see `run_nf1_feature_importance.py`'s module docstring for why both exist.",
        "",
        f"Generated: {report['generated_at']}  ·  model: `{report['model_version']}`  ·  "
        f"pool: {report['n_pool']} rows over base seasons {report['base_seasons']}",
        "",
        f"## Global (pooled across positions, LightGBM gain importance) — "
        f"baseline (`mvp1_fp`) share: {report['baseline_pct']}%",
        "",
        "| Feature | Label | % |",
        "|---|---|---|",
    ]
    for row in report["global"]:
        lines.append(f"| `{row['feature']}` | {row['label']} | {row['pct']}% |")
    for pos, rows in report["positions"].items():
        base = report["positions_baseline_pct"].get(pos)
        lines += ["", f"## {pos} (permutation importance) — baseline (`mvp1_fp`) share: {base}%",
                  "", "| Feature | Label | % |", "|---|---|---|"]
        for row in rows:
            lines.append(f"| `{row['feature']}` | {row['label']} | {row['pct']}% |")
    _OUT_POSITION_MD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
