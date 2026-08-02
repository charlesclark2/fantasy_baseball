"""run_nf1_feature_importance.py — NF3.4: export the NF1 GBM's own feature importances.

NF3.4 asks for a transparency panel on the player page: "this projection leans most on snap share,
age, prior-year efficiency…". The one model in this package that is actually fitted with a genuine
`.feature_importances_` is NF1's bake-off winner (PooledGBM/LightGBM — see
`ablation_results/nf1_season_bakeoff.json`, winner="gbm"); MVP-1 (the SERVED projection,
`season_projection.py`) is a fixed heuristic pipeline with no fitted model to introspect. NF1
consumes the SAME orthogonal NF-D signal set MVP-1's heuristic is built from (see nf1_model.py's
module docstring), so its importances are a true description of what the underlying signals are
worth — but they are NOT necessarily the literal mechanism behind any one player's SERVED number.
`M.feature_importance_report`'s docstring carries the full honest-labelling note; `main()` here just
assembles the pool + writes the artifact the exporter reads.

SF-free / offline: the walk-forward training pool NF1's bake-off already validated is cached locally
under `artifacts/nf1_feature_cache/pool_base<season>.parquet` (one file per base season) — this
script reads ONLY those cache files (no DuckDB / S3 / Snowflake connection), so it runs in seconds
on a laptop with no lake credentials. If a required base-season cache is missing, it fails loudly
(the exporter's `load_feature_importance` treats a missing artifact as best-effort, but this script
producing a wrong/partial one silently would be worse than not producing one at all).

Usage:
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf1_feature_importance
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf1 import build_training_pool  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf1_feature_importance")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_BAKEOFF_JSON = _REPORT_DIR / "nf1_season_bakeoff.json"
_OUT_JSON = _ART / "nf1_feature_importance.json"
_OUT_MD = _REPORT_DIR / "nf1_feature_importance.md"


def _load_winner_hp() -> tuple[list[int], dict]:
    """The bake-off's own base seasons + tuned hyperparameters for the winning learner ("gbm") — reuse
    what was already validated rather than re-guessing a config here."""
    d = json.loads(_BAKEOFF_JSON.read_text())
    if d.get("winner") != "gbm":
        raise SystemExit(
            f"nf1_season_bakeoff.json winner is {d.get('winner')!r}, not 'gbm' — "
            f"feature_importance_report is written for PooledGBM only. Re-check before re-running."
        )
    return d["base_seasons"], d["winner_hp"]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    base_seasons, hp = _load_winner_hp()
    log.info("winner hp from %s: base_seasons=%s hp=%s", _BAKEOFF_JSON.name, base_seasons, hp)

    pool = build_training_pool(None, base_seasons, use_cache=True)
    if pool.empty:
        raise SystemExit(
            f"empty training pool for base_seasons={base_seasons} — one of the "
            f"nf1_feature_cache/pool_base<season>.parquet files is missing. This script is offline-only "
            f"(reads the cache the validated bake-off already wrote); run run_nf1.py's bakeoff mode "
            f"first (needs the lake) if a cache file is genuinely absent."
        )
    log.info("pool: %d rows", len(pool))

    report = M.feature_importance_report(pool, hp)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["base_seasons"] = base_seasons

    _ART.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(json.dumps(report, indent=2))
    log.info("wrote %s", _OUT_JSON)

    _write_report_md(report)
    log.info("wrote %s", _OUT_MD)
    return 0


def _write_report_md(report: dict) -> None:
    lines = [
        "# NF3.4 — NF1 feature-importance transparency",
        "",
        f"Generated: {report['generated_at']}  ·  model: `{report['model_version']}`  ·  "
        f"pool: {report['n_pool']} rows over base seasons {report['base_seasons']}",
        "",
        "🚨 MODEL-LEVEL, NOT PER-PLAYER — see `nf1_model.feature_importance_report`'s docstring. This "
        "describes NF1 (the validated, market-blind research model over the same signal set MVP-1's "
        "served heuristic pipeline is built from), not a per-player attribution of the SERVED "
        "MVP-1 projection. `mvp1_fp` (NF1's own incumbent-prior feature) is excluded from the tables "
        "below as circular — its true share is disclosed as `baseline_pct` instead.",
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
    _OUT_MD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
