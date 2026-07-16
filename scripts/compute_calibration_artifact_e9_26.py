"""E9.26 — per-market calibration artifact (reliability curve + ECE) from the SERVING CACHE.

Produces the "how calibrated we've been" artifact the product cites and E9.43's
conviction layer consumes as its Task-1 input. Reads settled results ONLY through
the serving cache (DynamoDB -> S3 game-detail blobs), the exact E9.40 discipline —
NO Snowflake / lakehouse / mart / daily_model_predictions read, so it is safe to
run alongside the E11.20 Delta migration.

For each Final game in the window it pairs the served per-market model probability
with the realized binary outcome:
  * h2h    — model_prob = P(home win)  vs  outcome = 1[home won]
  * totals — model_prob = P(over)      vs  outcome = 1[final total > closing line]
             (pushes — final total == line — are dropped: no binary label)
Then per market_type it computes ECE, Brier, log-loss, spread and a 10-bin
reliability table (predicted vs observed frequency). The de-vigged market prob
(bovada_devig_prob) is scored the same way as a benchmark.

Honest framing (best_alpha = 0): this is a factual calibration measurement of the
served probabilities. It makes no market-advantage or return claim.

Usage (OFF-BOX, read-only; needs AWS creds for the serving cache):
    uv run python scripts/compute_calibration_artifact_e9_26.py --start 2026-03-27 --end 2026-07-15
    uv run python scripts/compute_calibration_artifact_e9_26.py --days 60      # trailing window ending today

Outputs:
    betting_ml/evaluation/calibration_e9_26/served_calibration_<start>_<end>.json
    quant_sports_intel_models/baseball/ablation_results/calibration_e9_26.md  (--write-md)
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from betting_ml.utils.calibration_metrics import metric_block, reliability_table

logger = logging.getLogger("calibration_e9_26")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUT_DIR = _REPO_ROOT / "betting_ml" / "evaluation" / "calibration_e9_26"
_MD_PATH = (_REPO_ROOT / "quant_sports_intel_models" / "baseball"
            / "ablation_results" / "calibration_e9_26.md")


# ── pure extraction (unit-tested; no network) ────────────────────────────────

def extract_calibration_pairs(detail: dict) -> dict[str, list[dict]]:
    """From one serving-cache game-detail blob, yield per-market (prob, outcome) pairs.

    Returns {market_type: [{"model_prob", "market_prob", "outcome"}, ...]} for a
    Final game with both scores; {} otherwise. Uses the SAME field names and the
    SAME >=0.5-side convention as app/backend/services/scorecard.py.
    """
    gs = detail.get("game_score") or {}
    if str(gs.get("status") or "") != "Final":
        return {}
    hs, as_ = gs.get("home_score"), gs.get("away_score")
    if hs is None or as_ is None:
        return {}
    try:
        hs, as_ = int(hs), int(as_)
    except (TypeError, ValueError):
        return {}

    out: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for p in (detail.get("picks") or []):
        mt = p.get("market_type")
        if mt not in ("h2h", "totals") or mt in seen:
            continue
        seen.add(mt)
        model_prob = p.get("model_prob")
        market_prob = p.get("bovada_devig_prob")
        if model_prob is None:
            continue
        if mt == "h2h":
            if hs == as_:  # MLB has no ties; guard defensively
                continue
            outcome = 1 if hs > as_ else 0
        else:  # totals
            line = p.get("market_total_line")
            if line is None:
                continue
            final_total = hs + as_
            if final_total == line:  # push — no binary label
                continue
            outcome = 1 if final_total > line else 0
        out.setdefault(mt, []).append({
            "model_prob": float(model_prob),
            "market_prob": float(market_prob) if market_prob is not None else None,
            "outcome": int(outcome),
        })
    return out


def build_artifact(pairs_by_market: dict[str, list[dict]], window: dict) -> dict:
    """Aggregate per-market (prob, outcome) pairs into the calibration artifact dict."""
    markets: dict[str, dict] = {}
    for mt, rows in sorted(pairs_by_market.items(), key=lambda kv: 0 if kv[0] == "h2h" else 1):
        model_p = [r["model_prob"] for r in rows]
        model_y = [r["outcome"] for r in rows]
        mkt_rows = [r for r in rows if r["market_prob"] is not None]
        block = {
            "n": len(rows),
            "model": {
                **metric_block(model_p, model_y),
                "reliability": reliability_table(model_p, model_y),
            },
        }
        if mkt_rows:
            mkt_p = [r["market_prob"] for r in mkt_rows]
            mkt_y = [r["outcome"] for r in mkt_rows]
            block["market"] = {
                **metric_block(mkt_p, mkt_y),
                "reliability": reliability_table(mkt_p, mkt_y),
            }
        markets[mt] = block
    return {
        "story": "E9.26",
        "source": "serving_cache (DynamoDB -> S3 game-detail blobs); no Snowflake/lakehouse",
        "window": window,
        "notes": {
            "h2h": "served model_prob = calibrated_win_prob (E13.6 TemperatureCalibrator T=6.30)",
            "totals": "served model_prob = totals_model_prob (raw distributional P(over); "
                      "not temperature/isotonic-calibrated at serving — its ECE here is the "
                      "genuine served-calibration measurement)",
        },
        "markets": markets,
    }


# ── serving-cache read orchestration (needs AWS creds) ───────────────────────

def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _read_ev_game_pks(serving_cache, s3_get, date_str: str, today_str: str) -> list[int]:
    blob = serving_cache.get_cache("picks/ev", date_str)
    if blob is None:
        # S3 fallback: a per-date key, then the undated "today" blob ONLY for today
        # (otherwise it false-hits today's slate for every historical date → wrong
        # attribution + a redundant game-detail miss storm).
        blob = s3_get(f"picks/ev/{date_str}.json")
        if blob is None and date_str == today_str:
            blob = s3_get("picks/ev.json")
    pks, seen = [], set()
    for p in ((blob or {}).get("picks") or []):
        gp = p.get("game_pk")
        if gp is not None and gp not in seen:
            seen.add(gp)
            pks.append(int(gp))
    return pks


def _read_game_detail(serving_cache, s3_get, game_pk: int, date_str: str) -> dict | None:
    blob = serving_cache.get_cache(f"picks/game/{game_pk}", date_str)
    if blob is not None and blob.get("picks"):
        return blob
    s3_key = f"picks/game/{game_pk}.json"
    blob = s3_get(s3_key, permanent=True) or s3_get(s3_key)
    return blob if blob and blob.get("picks") else None


def gather_pairs(start: date, end: date) -> tuple[dict[str, list[dict]], dict]:
    """Walk the window's serving-cache blobs and collect per-market pairs."""
    from app.backend.services import serving_cache
    from app.backend.services.s3_cache import get_cache as s3_get

    today_str = end.isoformat()
    all_dates = list(_daterange(start, end))
    total = len(all_dates)
    pairs: dict[str, list[dict]] = {}
    n_final = 0
    n_dates_with_games = 0
    for i, d in enumerate(all_dates, 1):
        date_str = d.isoformat()
        gpks = _read_ev_game_pks(serving_cache, s3_get, date_str, today_str)
        day_final = 0
        for gp in gpks:
            detail = _read_game_detail(serving_cache, s3_get, gp, date_str)
            if detail is None:
                continue
            extracted = extract_calibration_pairs(detail)
            if extracted:
                n_final += 1
                day_final += 1
            for mt, rows in extracted.items():
                pairs.setdefault(mt, []).extend(rows)
        if gpks:
            n_dates_with_games += 1
        # Progress heartbeat: one line per date so a long run is observable.
        logger.info("  [%3d/%3d] %s  ev_games=%-3d final=%-3d  (running: %d final games)",
                    i, total, date_str, len(gpks), day_final, n_final)
    logger.info("Done gathering: %d/%d dates had EV blobs, %d Final games scored.",
                n_dates_with_games, total, n_final)
    window = {"start": start.isoformat(), "end": end.isoformat(), "n_final_games": n_final}
    return pairs, window


def _render_md(artifact: dict) -> str:
    w = artifact["window"]
    lines = [
        "# E9.26 — Served per-market calibration (reliability + ECE)",
        "",
        f"Window **{w['start']} → {w['end']}** · {w['n_final_games']} Final games · "
        "source: serving cache (no Snowflake/lakehouse).",
        "",
        "Factual calibration measurement of the *served* probabilities — how close "
        "each market's model probability has been to observed frequency. Not a "
        "market-advantage claim (`best_alpha = 0`).",
        "",
    ]
    for mt, block in artifact["markets"].items():
        label = "Moneyline (P home win)" if mt == "h2h" else "Total Runs (P over)"
        m = block.get("model", {})
        lines += [
            f"## {label} — n={block.get('n', 0)}",
            "",
            f"- **Model** ECE `{m.get('ece')}` · Brier `{m.get('brier')}` · "
            f"spread `{m.get('spread')}` · base-rate `{m.get('base_rate')}`",
            f"- _{artifact['notes'].get(mt, '')}_",
            "",
            "| pred bin | n | avg pred | avg actual |",
            "|---|---|---|---|",
        ]
        for r in m.get("reliability", []):
            lines.append(f"| {r['bin_lo']:.1f}–{r['bin_hi']:.1f} | {r['n']} | "
                         f"{r['avg_pred']:.3f} | {r['avg_actual']:.3f} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="E9.26 per-market calibration artifact from serving cache")
    ap.add_argument("--start", help="YYYY-MM-DD window start")
    ap.add_argument("--end", help="YYYY-MM-DD window end (default: today, US baseball-day)")
    ap.add_argument("--days", type=int, help="trailing window length ending --end (overrides --start)")
    ap.add_argument("--write-md", action="store_true", help="also write the markdown artifact")
    args = ap.parse_args()

    from betting_ml.utils.game_day import current_game_date  # local import (needs betting_ml)
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else current_game_date()
    if args.days:
        start = end - timedelta(days=args.days)
    elif args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        ap.error("provide --start or --days")

    logger.info("Gathering serving-cache blobs %s → %s ...", start, end)
    pairs, window = gather_pairs(start, end)
    artifact = build_artifact(pairs, window)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = _OUT_DIR / f"served_calibration_{start.isoformat()}_{end.isoformat()}.json"
    out_json.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    logger.info("Wrote %s", out_json)

    for mt, block in artifact["markets"].items():
        m = block.get("model", {})
        logger.info("  %-7s n=%-4d model ECE=%s Brier=%s spread=%s",
                    mt, block.get("n", 0), m.get("ece"), m.get("brier"), m.get("spread"))

    if args.write_md:
        _MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MD_PATH.write_text(_render_md(artifact), encoding="utf-8")
        logger.info("Wrote %s", _MD_PATH)


if __name__ == "__main__":
    main()
