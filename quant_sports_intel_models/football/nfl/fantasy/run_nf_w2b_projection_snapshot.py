"""run_nf_w2b_projection_snapshot.py — pre/post-flip projection snapshot (NF-W2b flip tracking).

Operator requirement (2026-08-08): before the champion flip, capture per-player projections
from the PRE-flip spec (the NF-W1 champion — `W2B.PRE_FLIP_SPEC`) and the POST-flip spec (the
NF-W2b validated winners — `W2B.POST_FLIP_SPEC`, artifact-pinned by guard test) on the SAME
slate, so model differences are trackable row by row across the flip.

Two uses:
- TODAY (historical reference): score both spec sets on 2024 held-out half-season folds —
  training strictly precedes each fold exactly as in the bake-off, so the snapshot reproduces
  the validated comparison at per-player granularity.
- AT FLIP TIME (2026, live feed armed via NF-W0a): run on the flip week before staging the new
  spec through NF-G0 — the parquet is the before/after record.

Writes `artifacts/nf_w2b_projection_snapshot_<season>[H<half>].parquet` (per-row: both models'
q10/q50/q90, realized points, per-row CRPS for each, deltas — parquet is gitignored, local
record) + a committed summary `ablation_results/nf_w2b_projection_snapshot[_...].md`.

RUN (LAPTOP — reads the cached matrix / S3 lake read-only):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_projection_snapshot
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_projection_snapshot --season 2024 --half 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_injury_rate_bakeoff import (  # noqa: E402
    SEASONS,
    build_matrix_w2b,
)

log = logging.getLogger("nfl.fantasy.nf_w2b_snapshot")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"

_QIDX = {q: i for i, q in enumerate(np.round(WP.Q_LEVELS, 4))}
Q10, Q50, Q90 = _QIDX[0.10], _QIDX[0.50], _QIDX[0.90]


def snapshot_fold(fold: WP.Fold, feat: pd.DataFrame) -> pd.DataFrame:
    """Score BOTH spec sets on one fold's test rows; one output row per player-week."""
    train = feat.loc[fold.train_idx]
    test = feat.loc[fold.test_idx]
    t0 = time.time()
    norate = list(WP.FEATURES)
    rate = list(W2B.FEATURES_BASE_RATE)
    full = list(W2B.FEATURES_W2B)

    # pre-flip: the NF-W1 champion (base features both legs)
    p0_pre, cond_pre = W2.hurdle_parts(train, test, norate, norate)
    q_pre = W2.mix_parts(p0_pre, cond_pre)
    # post-flip parts: exactly the bake-off's arm constructions
    p0_rate, cond_rate = W2.hurdle_parts(train, test, rate, rate)
    p0_both, cond_both = W2.hurdle_parts(train, test, full, full)
    p0_zero_leg, _ = W2.hurdle_parts(train, test, full, rate)
    arm_qmats = {
        "inj_both": W2.mix_parts(p0_both, cond_both),
        "inj_zero_leg": W2.mix_parts(p0_zero_leg, cond_rate),
        "inj_override": W2.mix_parts(W2.override_p0(p0_rate, train, test)[0], cond_rate),
    }
    pos = test["position"].to_numpy()
    q_post = np.empty_like(q_pre)
    for p, arm in W2B.POST_FLIP_SPEC.items():
        sel = pos == p
        q_post[sel] = arm_qmats[arm][sel]

    y = test["fantasy_points"].to_numpy(dtype=float)
    crps_pre = WP.crps_from_quantiles(q_pre, y)
    crps_post = WP.crps_from_quantiles(q_post, y)
    s_pre, s_post = np.sort(q_pre, axis=1), np.sort(q_post, axis=1)
    out = pd.DataFrame({
        "season": test["season"].to_numpy(),
        "week": test["week"].to_numpy(),
        "gsis_id": test["gsis_id"].to_numpy(),
        "position": pos,
        "gameday": test["_target_gameday"].to_numpy(),
        "fantasy_points": y,
        "pre_spec": [W2B.PRE_FLIP_SPEC[p] for p in pos],
        "post_spec": [W2B.POST_FLIP_SPEC[p] for p in pos],
        "pre_q10": s_pre[:, Q10], "pre_q50": s_pre[:, Q50], "pre_q90": s_pre[:, Q90],
        "post_q10": s_post[:, Q10], "post_q50": s_post[:, Q50], "post_q90": s_post[:, Q90],
        "delta_q50": s_post[:, Q50] - s_pre[:, Q50],
        "crps_pre": crps_pre, "crps_post": crps_post,
        "crps_delta": crps_pre - crps_post,  # >0 = post-flip better on this row
        "injury_listed": pd.to_numeric(
            test["injury_report__listed"], errors="coerce").to_numpy(),
    })
    log.info("fold %s snapshot in %.1fs (%d rows)", fold.label, time.time() - t0, len(out))
    return out


def summarize(snap: pd.DataFrame) -> dict:
    out: dict = {}
    for p in WP.POSITIONS:
        s = snap[snap["position"] == p]
        listed = s[s["injury_listed"] == 1.0]
        out[p] = {
            "n_rows": int(len(s)),
            "mean_crps_pre": round(float(s["crps_pre"].mean()), 4),
            "mean_crps_post": round(float(s["crps_post"].mean()), 4),
            "mean_crps_delta": round(float(s["crps_delta"].mean()), 4),
            "mean_abs_delta_q50": round(float(s["delta_q50"].abs().mean()), 4),
            "share_moved_gt_1ppr": round(float((s["delta_q50"].abs() > 1.0).mean()), 4),
            "share_moved_gt_3ppr": round(float((s["delta_q50"].abs() > 3.0).mean()), 4),
            "listed_rows": int(len(listed)),
            "listed_mean_abs_delta_q50": round(float(listed["delta_q50"].abs().mean()), 4)
            if len(listed) else None,
        }
    return out


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W2b pre/post-flip projection snapshot")
    ap.add_argument("--season", type=int, default=2024,
                    help="snapshot season (default 2024 — the latest gated season)")
    ap.add_argument("--half", type=int, choices=(1, 2), default=None,
                    help="restrict to one half-season block (default: both)")
    ap.add_argument("--all-gated", action="store_true",
                    help="snapshot EVERY gated season (2019–2024, all 12 blocks) — the "
                         "full-history model-side reference (~30 min)")
    args = ap.parse_args(argv)

    feat, _ = build_matrix_w2b(SEASONS)
    if args.all_gated:
        blocks = W2B.TEST_BLOCKS_W2B
    else:
        blocks = tuple((args.season, h) for h in ((args.half,) if args.half else (1, 2)))
    folds = W2.build_folds_w2(feat, blocks)
    if not folds:
        raise SystemExit(f"no test rows for blocks {blocks}")
    log.info("snapshotting %s over %d fold(s): %s",
             args.season, len(folds), [f.label for f in folds])

    snap = pd.concat([snapshot_fold(f, feat) for f in folds], ignore_index=True)
    if args.all_gated:
        tag = f"{blocks[0][0]}_{blocks[-1][0]}"
    else:
        tag = f"{args.season}" + (f"H{args.half}" if args.half else "")
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    pq = _ARTIFACTS / f"nf_w2b_projection_snapshot_{tag}.parquet"
    snap.to_parquet(pq, index=False)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W2b flip tracking", "season": args.season, "half": args.half,
        "folds": [f.label for f in folds], "n_rows": int(len(snap)),
        "pre_flip_spec": dict(W2B.PRE_FLIP_SPEC), "post_flip_spec": dict(W2B.POST_FLIP_SPEC),
        "parquet": str(pq.relative_to(_PROJECT_ROOT)),
        "positions": summarize(snap),
    }
    md = _REPORT_DIR / f"nf_w2b_projection_snapshot_{tag}.md"
    lines = [
        "# NF-W2b — pre/post-flip projection snapshot",
        "",
        f"**Generated:** {summary['generated_at']} · **folds:** {', '.join(summary['folds'])} · "
        f"**rows:** {summary['n_rows']} · per-row record: `{summary['parquet']}` (gitignored)",
        "",
        "Pre-flip = the NF-W1 champion spec; post-flip = the NF-W2b validated winners "
        "(artifact-pinned). Positive `mean_crps_delta` = the post-flip model is better.",
        "",
        pd.DataFrame(summary["positions"]).T.to_markdown(),
        "",
        "```json",
        json.dumps(summary, indent=2, default=str),
        "```",
    ]
    md.write_text("\n".join(lines))
    log.info("snapshot → %s + %s", pq.name, md.name)
    print(json.dumps({k: v for k, v in summary["positions"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
