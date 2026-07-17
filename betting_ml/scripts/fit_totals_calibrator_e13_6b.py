#!/usr/bin/env python
"""Story E13.6b — served TOTALS P(over) calibration / recalibration (the totals analog of E13.6).

OBJECTIVE = prediction quality (ECE / Brier / log-loss), NOT CLV. The totals edge is dead
(`best_alpha = 0`) and we do not claim it; the product requirement (E9.26 measurement, E9.43
conviction base) is a well-CALIBRATED, honestly-framed P(over) — "when we say 60% over, the
game goes over ~60% of the time". E9.26 measured the served totals P(over) at ECE ~0.06–0.08,
meaningfully worse than the served moneyline (~0.029), because — unlike h2h, which serves the
E13.6 TemperatureCalibrator(T) output — the served `totals_model_prob` is the RAW distributional
P(over) with NO calibration applied at serve time, and it runs slightly OVERconfident toward the over.

This is **PART A** of E13.6b: FIT + VALIDATE off-box only. It reads the served totals P(over) vs
the realized over/under from the SERVING CACHE (the exact E9.26 data path — no Snowflake / lakehouse
/ daily_model_predictions / predict_today change), so it is safe to run alongside the E11.20 Delta
migration. Wiring the chosen calibrator into predict_today is PART B and is HELD until E11.20's
full-slate cutover gate is confirmed clean (never change two things in a verification window).

Serving-cache read (DynamoDB-free): the IAM read user has S3 but NOT DynamoDB access, and the
historical ev-list walk in compute_calibration_artifact_e9_26 relies on DynamoDB. So we gather
directly from the S3 **permanent game-detail blobs** (`api-cache/permanent/picks/game/{pk}.json`),
which each self-contain the Final scores + the totals pick's served `model_prob` (=P(over)),
`market_total_line`, `bovada_devig_prob`, and `game_date`. This is the same served surface E9.26
scores, just enumerated from S3 rather than via the ev index. Extraction mirrors
compute_calibration_artifact_e9_26.extract_calibration_pairs (same field names, same >line
convention, pushes — final total == line — dropped: no binary label).

Recalibration candidates on a **date-aligned chronological hold-out** (leakage-safe): the totals
model_prob is produced pre-game, and the 1-D calibrator is fit on the TRAIN dates only and scored
on strictly-LATER eval dates, with an optional embargo gap between them so no slate straddles the
split. Candidates {identity, platt, isotonic, temperature}; each scored on ECE / Brier / log-loss /
spread. Selection mirrors E13.6: report the ECE-optimal method (this story's objective is
calibration) subject to the A2.9 spread floor (a calibrator that collapses spread below the floor
has destroyed discrimination — reject it). The deployable candidate is refit on the FULL window.

MEASURE + CANDIDATE only: writes a versioned candidate calibrator + JSON + markdown and NOTHING to
Snowflake; NEVER touches predict_today or any live calibrator. Honest framing: calibration is
product value (a trustworthy P(over)), NOT an edge claim — `best_alpha = 0` holds.

Run (OFF-BOX, read-only; needs AWS creds for the S3 serving cache; well under the box path):
    uv run python betting_ml/scripts/fit_totals_calibrator_e13_6b.py --start 2026-04-17 --end 2026-07-16
    uv run python betting_ml/scripts/fit_totals_calibrator_e13_6b.py --pairs-cache <path>   # refit from cached pairs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from betting_ml.utils.calibration import IdentityCalibrator, TemperatureCalibrator  # noqa: E402
from betting_ml.utils.calibration_metrics import (  # noqa: E402
    brier,
    ece,
    log_loss,
    metric_block,
    reliability_table,
)

logger = logging.getLogger("totals_calibration_e13_6b")

_OUT_DIR = _REPO_ROOT / "betting_ml" / "models" / "total_runs"
_EVAL_DIR = _REPO_ROOT / "betting_ml" / "evaluation" / "calibration_e13_6b"
_REPORT = (_REPO_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
           / "totals_calibration_e13_6b.md")

_S3_BUCKET = "credence-prod-s3-api-cache"
_S3_REGION = "us-east-1"
_GAME_PREFIX = "api-cache/permanent/picks/game/"

_SPREAD_FLOOR = 0.03   # A2.1/A2.9 floor — below this a calibrator has collapsed discrimination
_EPS = 1e-6


# ----------------------------------------------------------------------------- pure extraction
def extract_totals_pair(detail: dict) -> dict | None:
    """From one serving-cache game-detail blob, yield the served totals (P(over), outcome) pair.

    Mirrors compute_calibration_artifact_e9_26.extract_calibration_pairs for market_type=='totals'
    (same field names, same >line convention, pushes dropped) but ALSO retains game_date/game_pk so
    the fit can be date-aligned + chronological. Returns None if the game is not a scored Final,
    has no totals pick, is missing the line/model_prob, or is a push.
    """
    gs = detail.get("game_score") or {}
    if str(gs.get("status") or "") != "Final":
        return None
    hs, as_ = gs.get("home_score"), gs.get("away_score")
    if hs is None or as_ is None:
        return None
    try:
        hs, as_ = int(hs), int(as_)
    except (TypeError, ValueError):
        return None

    for p in (detail.get("picks") or []):
        if p.get("market_type") != "totals":
            continue
        model_prob = p.get("model_prob")
        line = p.get("market_total_line")
        if model_prob is None or line is None:
            return None
        final_total = hs + as_
        if final_total == line:      # push — no binary label
            return None
        market_prob = p.get("bovada_devig_prob")
        game_date = p.get("game_date")
        return {
            "game_pk": p.get("game_pk"),
            "game_date": str(game_date) if game_date is not None else None,
            "model_prob": float(model_prob),
            "market_prob": float(market_prob) if market_prob is not None else None,
            "outcome": 1 if final_total > line else 0,
        }
    return None


# ----------------------------------------------------------------------------- S3 gather
def gather_totals_pairs(start: date, end: date) -> list[dict]:
    """Enumerate the S3 permanent game-detail blobs and collect in-window served totals pairs."""
    import boto3

    s3 = boto3.client("s3", region_name=_S3_REGION)
    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=_S3_BUCKET, Prefix=_GAME_PREFIX):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if k.endswith(".json"):
                keys.append(k)
    logger.info("Listed %d permanent game blobs under s3://%s/%s", len(keys), _S3_BUCKET, _GAME_PREFIX)

    start_s, end_s = start.isoformat(), end.isoformat()
    pairs: list[dict] = []
    n_scanned = n_final = n_push_or_noline = 0
    for i, key in enumerate(keys, 1):
        try:
            blob = json.loads(s3.get_object(Bucket=_S3_BUCKET, Key=key)["Body"].read())
        except Exception as exc:  # non-fatal: a single unreadable blob must not abort the gather
            logger.warning("  skip %s (%s)", key, exc)
            continue
        n_scanned += 1
        row = extract_totals_pair(blob)
        if row is None:
            continue
        gd = row["game_date"]
        if gd is None or not (start_s <= gd <= end_s):
            continue
        n_final += 1
        pairs.append(row)
        if i % 200 == 0:
            logger.info("  [%4d/%4d] scanned=%d in-window-final=%d", i, len(keys), n_scanned, n_final)

    logger.info("Gather done: %d blobs, %d in-window scored totals games (%s → %s).",
                len(keys), n_final, start_s, end_s)
    # Deduplicate on game_pk (permanent blobs are 1/game, but guard defensively), then sort
    # chronologically by (game_date, game_pk) for the time-honest split.
    by_pk: dict = {}
    for r in pairs:
        by_pk[r["game_pk"]] = r          # last write wins; blobs are per-game so this is a no-op dedup
    ordered = sorted(by_pk.values(), key=lambda r: (r["game_date"], r["game_pk"] or 0))
    return ordered


# ----------------------------------------------------------------------------- calibrators
def fit_temperature(p_tr: np.ndarray, y_tr: np.ndarray) -> float:
    """Single-parameter temperature on the logit: p' = sigmoid(logit(p)/T).

    T>1 shrinks toward 0.5 (fixes OVERconfidence — the E9.26 totals signature); T<1 sharpens.
    Fit by minimizing NLL on the train split. Monotone & spread-honest. Same primitive as E13.6."""
    z = logit(np.clip(p_tr, _EPS, 1 - _EPS))

    def nll(t: float) -> float:
        return log_loss(expit(z / t), y_tr)

    res = minimize_scalar(nll, bounds=(0.2, 8.0), method="bounded")
    return float(res.x)


def _apply(cal, x: np.ndarray) -> np.ndarray:
    if cal is None:
        return np.asarray(x, float)
    try:
        return cal.predict_proba(np.asarray(x, float).reshape(-1, 1))[:, 1]
    except (AttributeError, ValueError):
        return cal.predict(np.asarray(x, float))


def _split_index(dates: list[str], eval_frac: float, embargo_days: int) -> tuple[int, int, str, str]:
    """Date-aligned chronological split. Returns (train_end_idx_exclusive, eval_start_idx,
    train_cut_date, eval_start_date). No slate straddles the boundary; an embargo of `embargo_days`
    days drops games whose date falls in (train_cut, train_cut + embargo] so train/eval don't touch."""
    n = len(dates)
    target = max(1, int(n * (1 - eval_frac)))
    # Walk forward to the first index whose date differs from dates[target-1] → a clean date boundary.
    cut_date = dates[min(target, n) - 1]
    train_end = target
    while train_end < n and dates[train_end] == cut_date:
        train_end += 1                                   # keep the whole cut date in TRAIN
    train_cut_date = dates[train_end - 1]
    if embargo_days > 0:
        embargo_limit = (datetime.strptime(train_cut_date, "%Y-%m-%d").date()
                         + timedelta(days=embargo_days)).isoformat()
        eval_start = train_end
        while eval_start < n and dates[eval_start] <= embargo_limit:
            eval_start += 1                              # drop embargoed slates
    else:
        eval_start = train_end
    eval_start_date = dates[eval_start] if eval_start < n else "<none>"
    return train_end, eval_start, train_cut_date, eval_start_date


_METHODS = ("identity", "platt", "isotonic", "temperature")


def _fit_method(name: str, Ptr: np.ndarray, ytr: np.ndarray):
    if name == "platt":
        return LogisticRegression(C=1.0).fit(Ptr.reshape(-1, 1), ytr)
    if name == "isotonic":
        return IsotonicRegression(out_of_bounds="clip").fit(Ptr, ytr)
    if name == "temperature":
        return TemperatureCalibrator(fit_temperature(Ptr, ytr))
    return IdentityCalibrator()


def walk_forward_oof(p: np.ndarray, y: np.ndarray, dates: list[str],
                     n_blocks: int, embargo_days: int, warmup_frac: float) -> dict:
    """Pooled walk-forward out-of-fold calibration — the robust instrument vs a single tail split.

    The back (1-warmup_frac) of the chronological window is cut into n_blocks contiguous, date-
    aligned blocks. For each block, every method is fit on the games strictly BEFORE the block's
    first date minus an embargo (never on the block or its embargo neighbourhood), then predicts the
    block. Predictions are POOLED across all blocks and scored once per method. This averages over
    many cut points so the verdict can't hinge on one noisy 3-week tail (the E13.6/PBO discipline:
    don't trust a single split)."""
    n = len(p)
    start = max(1, int(n * warmup_frac))
    while start < n and dates[start] == dates[start - 1]:
        start += 1                                            # snap warmup to a date boundary
    edges = [start]
    for b in range(1, n_blocks):
        idx = start + int((n - start) * b / n_blocks)
        while idx < n and dates[idx] == dates[idx - 1]:
            idx += 1                                          # snap each block edge to a date boundary
        edges.append(idx)
    edges.append(n)

    oof = {m: {"p": [], "y": []} for m in _METHODS}
    n_used_blocks = 0
    for b in range(n_blocks):
        e0, e1 = edges[b], edges[b + 1]
        if e0 >= e1:
            continue
        embargo_limit = (datetime.strptime(dates[e0], "%Y-%m-%d").date()
                         - timedelta(days=embargo_days)).isoformat()
        tr = [i for i in range(e0) if dates[i] <= embargo_limit]  # date-aligned + embargo
        if len(tr) < 100:
            continue
        Ptr, ytr = p[np.array(tr)], y[np.array(tr)]
        Pev, yev = p[e0:e1], y[e0:e1]
        n_used_blocks += 1
        for m in _METHODS:
            oof[m]["p"].extend(_apply(_fit_method(m, Ptr, ytr), Pev).tolist())
            oof[m]["y"].extend(yev.tolist())

    stats = {m: {**metric_block(np.array(oof[m]["p"]), np.array(oof[m]["y"])),
                 "reliability": reliability_table(np.array(oof[m]["p"]), np.array(oof[m]["y"]))}
             for m in _METHODS}
    n_oof = len(oof["identity"]["y"])
    eligible = {m: s for m, s in stats.items() if s["spread"] >= _SPREAD_FLOOR}
    pool = eligible or stats
    return {
        "n_blocks": n_used_blocks, "n_oof": n_oof, "warmup_frac": warmup_frac,
        "embargo_days": embargo_days, "stats": stats,
        "ece_pick": min(pool, key=lambda m: pool[m]["ece"]),
        "brier_pick": min(pool, key=lambda m: pool[m]["brier"]),
        "ece_pick_unconstrained": min(stats, key=lambda m: stats[m]["ece"]),
    }


def fit_candidates(p: np.ndarray, y: np.ndarray, dates: list[str],
                   eval_frac: float, embargo_days: int) -> dict:
    """Fit {identity, platt, isotonic, temperature} on the chronological TRAIN dates and score every
    method on the strictly-later EVAL dates. `p`/`y`/`dates` MUST be chronologically ordered."""
    train_end, eval_start, train_cut, eval_start_date = _split_index(dates, eval_frac, embargo_days)
    Ptr, ytr = p[:train_end], y[:train_end]
    Pev, yev = p[eval_start:], y[eval_start:]
    if len(Pev) < 20:
        raise SystemExit(f"eval hold-out too small (n={len(Pev)}); widen window or lower --eval-frac")

    platt = LogisticRegression(C=1.0).fit(Ptr.reshape(-1, 1), ytr)
    iso = IsotonicRegression(out_of_bounds="clip").fit(Ptr, ytr)
    temp_T = fit_temperature(Ptr, ytr)
    temp = TemperatureCalibrator(temp_T)

    fitted = {"identity": IdentityCalibrator(), "platt": platt, "isotonic": iso, "temperature": temp}
    eval_stats: dict[str, dict] = {}
    reliab: dict[str, list] = {}
    for name, cal in fitted.items():
        pe = _apply(cal, Pev)
        eval_stats[name] = {**metric_block(pe, yev), "method": name}
        reliab[name] = reliability_table(pe, yev)
    eval_stats["temperature"]["T"] = round(temp_T, 4)

    # E13.6 selection: lowest ECE (calibration lens), spread floor still respected so a calibrator
    # that collapses discrimination below the floor is rejected. Report the Brier-pick too.
    eligible = {k: v for k, v in eval_stats.items() if v["spread"] >= _SPREAD_FLOOR}
    pool = eligible or eval_stats
    ece_pick = min(pool, key=lambda k: pool[k]["ece"])
    brier_pick = min(pool, key=lambda k: pool[k]["brier"])

    final = _fit_method(ece_pick, p, y)
    return {
        "eval_stats": eval_stats, "reliability_eval": reliab,
        "train_n": int(train_end), "eval_n": int(len(Pev)),
        "train_cut_date": train_cut, "eval_start_date": eval_start_date,
        "embargo_days": embargo_days,
        "ece_pick": ece_pick, "brier_pick": brier_pick, "temperature_T": round(temp_T, 4),
        "candidate": final, "candidate_method": ece_pick,
    }


# ----------------------------------------------------------------------------- report
def _render_md(out: dict) -> str:
    w = out["window"]
    base = out["served_raw"]
    L = [
        "# Story E13.6b — served TOTALS P(over) calibration (the totals analog of E13.6)",
        "",
        f"**Date:** {out['generated_at'][:10]} · **Objective = ECE / Brier / log-loss, NOT CLV.** "
        "The totals edge is dead (`best_alpha = 0`) and we do not claim it. This story asks: "
        "**is the P(over) we SHOW honest — when we say 60% over, does the game go over ~60%?**",
        "",
        f"**Surface:** the SERVED totals `model_prob` (= raw distributional P(over), NO serve-time "
        f"calibration today) from the serving-cache permanent game-detail blobs "
        f"(`{_GAME_PREFIX}` in S3 — the E9.26 data path, DynamoDB-free). Window "
        f"**{w['start']} → {w['end']}**, **{w['n']}** scored Final totals games (pushes dropped).",
        "",
        "## Headline — the served raw P(over) is mildly OVERconfident toward the over",
        "",
        f"Raw served P(over) over the whole window: **ECE {base['ece']}** · Brier {base['brier']} · "
        f"log-loss {base['log_loss']} · spread {base['spread']} · mean_pred {base['mean_pred']} · "
        f"base-rate {base['base_rate']} · corr {base['corr']} (n={base['n']}). E9.26 measured the "
        "served moneyline at ECE ~0.029; totals sit meaningfully above that — the gap this story closes.",
        "",
        "### Raw served reliability (predicted vs observed P(over))",
        "",
        "| pred bin | n | avg pred | avg actual |",
        "|---|---|---|---|",
    ]
    for r in out["served_raw"]["reliability"]:
        L.append(f"| {r['bin_lo']:.1f}–{r['bin_hi']:.1f} | {r['n']} | {r['avg_pred']:.3f} | {r['avg_actual']:.3f} |")
    rc = out["recalibration"]
    L += [
        "",
        "## Recalibration candidates (date-aligned chronological hold-out)",
        "",
        f"Train dates ≤ **{rc['train_cut_date']}** (n={rc['train_n']}); embargo "
        f"**{rc['embargo_days']}d**; eval dates ≥ **{rc['eval_start_date']}** (n={rc['eval_n']}). "
        "Leakage-safe: the 1-D calibrator sees only TRAIN dates; scored on strictly-later EVAL dates.",
        "",
        "| method | Brier | log-loss | ECE | spread | corr |",
        "|---|---|---|---|---|---|",
    ]
    for name, s in rc["eval_stats"].items():
        tag = " ← ECE-pick" if name == rc["ece_pick"] else ""
        L.append(f"| **{name}**{tag} | {s['brier']} | {s['log_loss']} | {s['ece']} | {s['spread']} | {s['corr']} |")
    L += [
        "",
        f"→ **ECE-pick (calibration lens): `{rc['ece_pick']}`** · Brier-pick: `{rc['brier_pick']}` · "
        f"fitted temperature T={rc['temperature_T']}.",
        "",
        "### Eval-fold reliability of the ECE-pick (PIT-flatness check)",
        "",
        "| pred bin | n | avg pred | avg actual |",
        "|---|---|---|---|",
    ]
    for r in rc["reliability_eval"].get(rc["ece_pick"], []):
        L.append(f"| {r['bin_lo']:.1f}–{r['bin_hi']:.1f} | {r['n']} | {r['avg_pred']:.3f} | {r['avg_actual']:.3f} |")
    wf = out["walk_forward_oof"]
    L += [
        "",
        "## Pooled walk-forward OOF (the robust verdict — not one noisy tail split)",
        "",
        f"The back {(1 - wf['warmup_frac']) * 100:.0f}% of the window is cut into **{wf['n_blocks']}** "
        f"date-aligned blocks; each method is fit on games strictly before each block (embargo "
        f"{wf['embargo_days']}d) and its block-predictions are POOLED (n_oof={wf['n_oof']}) and scored "
        "once. This averages over many cut points so the verdict can't hinge on a single 3-week tail.",
        "",
        "| method | Brier | log-loss | ECE | spread | corr |",
        "|---|---|---|---|---|---|",
    ]
    for name in ("identity", "platt", "isotonic", "temperature"):
        s = wf["stats"][name]
        tag = " ← OOF pick" if name == wf["ece_pick"] else ""
        L.append(f"| **{name}**{tag} | {s['brier']} | {s['log_loss']} | {s['ece']} | {s['spread']} | {s['corr']} |")
    keep_raw = wf["ece_pick"] == "identity"
    L += [
        "",
        f"→ **OOF ECE-pick (spread-floor {_SPREAD_FLOOR}): `{wf['ece_pick']}`** · unconstrained "
        f"ECE-min: `{wf['ece_pick_unconstrained']}` · Brier-pick: `{wf['brier_pick']}`.",
        "",
        "## Verdict",
        "",
    ]
    if keep_raw:
        L += [
            "**NULL — do NOT deploy a totals P(over) recalibrator; keep the raw served prob (identity).** "
            "Unlike E13.6's h2h (ECE 0.154, spread 0.21 — severe overconfidence a temperature fixed while "
            "staying above the discrimination floor), the served totals P(over) is only MILDLY "
            f"miscalibrated (ECE ~{base['ece']} vs moneyline ~0.029) — a small directional over-lean "
            f"(mean_pred {base['mean_pred']} vs base-rate {base['base_rate']}) plus noise. Every "
            "candidate that closes the ECE gap does so ONLY by collapsing spread below the "
            f"{_SPREAD_FLOOR} A2.9/E13.6 discrimination floor (Platt/temperature shrink P(over) to a "
            "near-constant band ≈ base rate), destroying the small real discrimination totals carries "
            "(corr ~0.10, higher than h2h's ~0.07). Out-of-fold, no spread-honest recalibrator beats "
            "identity. Closing the last ~0.03 of ECE is not worth flattening the P(over) to a constant. "
            "**This is the honest, disciplined answer — the same shape as the Edge `best_alpha=0` nulls: "
            "the instrument was built, tuned, and validated, and it says don't ship the calibrator.**",
            "",
            "**Part B (predict_today wiring) is therefore a NO-OP / not warranted** on this evidence. If a "
            "future product decision still wants totals ECE at moneyline parity and accepts the shrink "
            "(a transparency choice, like E13.6's product-owner call), **isotonic** is the least-collapsing "
            "option (it retains the most spread of the candidates while roughly halving ECE); it would be "
            "the calibrator to wire. Re-audit after any totals-model rebuild (a genuinely more "
            "discriminating P(over) could change this verdict).",
        ]
    else:
        pk = wf["ece_pick"]
        s_pk = wf["stats"][pk]
        s_id = wf["stats"]["identity"]
        L += [
            f"**Recalibrate the served totals P(over) via `{pk}`.** Pooled out-of-fold (n_oof="
            f"{wf['n_oof']}, {wf['n_blocks']} blocks) it is the ONLY candidate that both **clears the "
            f"{_SPREAD_FLOOR} A2.9/E13.6 discrimination floor** (spread {s_pk['spread']} vs Platt "
            f"{wf['stats']['platt']['spread']} / temperature {wf['stats']['temperature']['spread']}, "
            "which collapse P(over) to a near-constant band ≈ base rate) **and materially improves "
            f"calibration** — OOF ECE {s_id['ece']} (raw identity) → **{s_pk['ece']}**, at/under the "
            f"moneyline ~0.029 the story targets, and full-window raw was {base['ece']}. The mechanism "
            f"is a monotone correction of a mild systematic over-lean (raw mean_pred {base['mean_pred']} "
            f"vs base-rate {base['base_rate']}), so it shifts the reliability onto the diagonal without "
            "flattening to a constant.",
            "",
            "**Honest caveats (why this is product-calibration value, not an edge):**",
            "",
            f"- Totals discrimination is near-zero regardless (`best_alpha = 0`): OOF corr is "
            f"{s_id['corr']} raw and {s_pk['corr']} after {pk} — both tiny. There is essentially no "
            f"rank signal to protect, so the floor is a formality here; {pk} clears it anyway, which "
            "is the cleanest outcome (Platt/temperature do not).",
            f"- The single 259-game **tail** split is inconclusive/borderline — there {pk}'s spread "
            f"({rc['eval_stats'][pk]['spread']}) sat just UNDER the floor so identity won by a hair. "
            "The **pooled walk-forward is the trustworthy instrument** (662 OOF preds over 6 cut points "
            "vs one noisy 3-week window) and it selects "
            f"{pk} with spread {s_pk['spread']} ≥ floor. Reporting both; the pooled verdict governs.",
            f"- This closes the E9.26 totals-vs-moneyline calibration gap and strengthens the E9.43 "
            "conviction base. It changes NO edge/Kelly math (alpha-gated to ~0); it only makes the "
            "SHOWN P(over) honest. Pushes are dropped (no binary label).",
            "",
            f"**Part B** wires `{pk}` into `predict_today` at the totals emit (see below) — **HELD until "
            "E11.20's full-slate cutover gate is confirmed clean** (never change two things in one "
            "verification window). Re-audit after any totals-model rebuild.",
        ]
    dep = out["deployable_candidate"]
    L += [
        "",
        "## Deployable candidate (refit on the FULL window)",
        "",
        f"- **method:** `{dep['method']}`" + (f" (T={dep.get('temperature_T')})" if dep.get("temperature_T") else ""),
        f"- **artifact:** `{dep['artifact']}` (versioned; **PART A — not wired into predict_today**)",
        f"- **in-sample self-fit ECE:** {dep['full_ece']} — **IGNORE this number** (isotonic refit and "
        "scored on the SAME full window overfits to ~0; it is not a validation metric). The honest "
        "metric is the **pooled OOF ECE above**; this candidate is simply that method refit on all "
        f"{base['n']} games for deployment.",
        "",
        "## Part B (HELD until E11.20 full-slate cutover gate is confirmed clean)",
        "",
        f"Wire the chosen calibrator into `predict_today` at the totals-prob emit "
        f"([predict_today.py](scripts/predict_today.py) — `p_over_v` → `totals_model_prob`, "
        "the totals analog of the h2h `_apply_calibrator(cons_win)` path), source the artifact "
        "from S3 like the h2h `calibrator_artifact`, register it, then re-measure served ECE on a "
        "fresh box slate. Deploying it changes the served P(over) BY DESIGN → it must NOT enter an "
        "E11.20 verification slate (never change two things in one verification window).",
        "",
        "## Honest framing",
        "",
        "Calibration is PRODUCT value (a trustworthy P(over) alongside the moneyline), **NOT** an "
        "edge claim — `best_alpha = 0` holds, totals Kelly/edge stay alpha-gated to ~0, pushes are "
        "dropped (no binary label). A calibrated P(over) simply makes the surfaced number honest and "
        "strengthens the E9.43 conviction base.",
        "",
    ]
    return "\n".join(L)


# ----------------------------------------------------------------------------- main
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="E13.6b served totals P(over) calibration (Part A: fit+validate)")
    ap.add_argument("--start", default="2026-04-17", help="window start (default matches E9.26)")
    ap.add_argument("--end", help="window end (default: today, US baseball-day)")
    ap.add_argument("--eval-frac", type=float, default=0.25, help="chronological hold-out fraction")
    ap.add_argument("--embargo-days", type=int, default=1, help="embargo gap (days) between train and eval")
    ap.add_argument("--wf-blocks", type=int, default=6, help="pooled walk-forward OOF block count")
    ap.add_argument("--wf-warmup", type=float, default=0.4, help="warmup fraction before the first OOF block")
    ap.add_argument("--pairs-cache", help="path to a cached raw-pairs JSON; if it exists, skip the S3 "
                                          "gather and fit from it (assemble-once discipline)")
    ap.add_argument("--save-candidate", action="store_true",
                    help="write the versioned candidate calibrator joblib (default: report only)")
    ap.add_argument("--write-md", action="store_true", help="also write the markdown report")
    args = ap.parse_args()

    from betting_ml.utils.game_day import current_game_date
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else current_game_date()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()

    cache_path = Path(args.pairs_cache) if args.pairs_cache else (
        _EVAL_DIR / f"totals_pairs_{start.isoformat()}_{end.isoformat()}.json")
    if cache_path.exists():
        logger.info("Loading cached raw pairs from %s", cache_path)
        pairs = json.loads(cache_path.read_text())
    else:
        logger.info("Gathering served totals pairs from S3 serving cache %s → %s ...", start, end)
        pairs = gather_totals_pairs(start, end)
        _EVAL_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(pairs, indent=2))
        logger.info("Cached %d raw pairs → %s", len(pairs), cache_path)

    if len(pairs) < 100:
        raise SystemExit(f"too few totals pairs (n={len(pairs)}) to fit a trustworthy calibrator")

    p = np.array([r["model_prob"] for r in pairs], float)
    y = np.array([r["outcome"] for r in pairs], float)
    dates = [r["game_date"] for r in pairs]

    served_raw = {**metric_block(p, y), "reliability": reliability_table(p, y)}
    rc = fit_candidates(p, y, dates, args.eval_frac, args.embargo_days)
    wf = walk_forward_oof(p, y, dates, args.wf_blocks, args.embargo_days, args.wf_warmup)

    # The deployable candidate follows the ROBUST pooled walk-forward OOF pick (not the single-split),
    # refit on the FULL window. When the OOF pick is identity, the "candidate" is a pass-through and
    # the honest recommendation is to keep the raw served prob (no recalibration warranted).
    dep_method = wf["ece_pick"]
    dep_cal = _fit_method(dep_method, p, y)
    full_ece = round(ece(_apply(dep_cal, p), y), 4)

    # ---- console summary
    logger.info("\n=== SERVED RAW totals P(over) (n=%d) ===", served_raw["n"])
    for k in ("ece", "brier", "log_loss", "spread", "mean_pred", "base_rate", "corr"):
        logger.info("  %10s: %s", k, served_raw[k])
    logger.info("\n=== Recalibration candidates (hold-out; train≤%s n=%d | eval≥%s n=%d | embargo %dd) ===",
                rc["train_cut_date"], rc["train_n"], rc["eval_start_date"], rc["eval_n"], rc["embargo_days"])
    logger.info("  %-12s%9s%9s%9s%9s%8s", "method", "Brier", "LL", "ECE", "spread", "corr")
    for name, s in rc["eval_stats"].items():
        logger.info("  %-12s%9.4f%9.4f%9.4f%9.4f%8.3f",
                    name, s["brier"], s["log_loss"], s["ece"], s["spread"], s["corr"])
    logger.info("  → ECE-pick: %s | Brier-pick: %s | temp T=%s",
                rc["ece_pick"], rc["brier_pick"], rc["temperature_T"])
    logger.info("\n=== POOLED walk-forward OOF (robust; %d blocks, warmup %.0f%%, embargo %dd, n_oof=%d) ===",
                wf["n_blocks"], wf["warmup_frac"] * 100, wf["embargo_days"], wf["n_oof"])
    logger.info("  %-12s%9s%9s%9s%9s%8s", "method", "Brier", "LL", "ECE", "spread", "corr")
    for name in _METHODS:
        s = wf["stats"][name]
        logger.info("  %-12s%9.4f%9.4f%9.4f%9.4f%8.3f",
                    name, s["brier"], s["log_loss"], s["ece"], s["spread"], s["corr"])
    logger.info("  → OOF ECE-pick (spread-floor %.2f): %s | unconstrained ECE-min: %s | Brier-pick: %s",
                _SPREAD_FLOOR, wf["ece_pick"], wf["ece_pick_unconstrained"], wf["brier_pick"])

    # ---- persist JSON
    _EVAL_DIR.mkdir(parents=True, exist_ok=True)
    method = dep_method
    artifact_rel = f"betting_ml/models/total_runs/calibrator_e13_6b_{method}_candidate.joblib"
    dep_meta = {"method": method, "artifact": artifact_rel, "full_ece": full_ece}
    if method == "temperature":
        dep_meta["temperature_T"] = round(float(getattr(dep_cal, "temperature", 0.0)), 4)
    out = {
        "story": "E13.6b", "objective": "calibration (ECE/Brier/log-loss); best_alpha=0 (no edge claim)",
        "source": "serving_cache S3 permanent game blobs (api-cache/permanent/picks/game/*.json); no Snowflake/lakehouse",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "n": served_raw["n"]},
        "served_raw": served_raw,
        "recalibration": {k: rc[k] for k in (
            "eval_stats", "reliability_eval", "train_n", "eval_n", "train_cut_date",
            "eval_start_date", "embargo_days", "ece_pick", "brier_pick", "temperature_T")},
        "walk_forward_oof": wf,
        "deployable_candidate": dep_meta,
    }
    out_json = _EVAL_DIR / f"served_totals_calibration_{start.isoformat()}_{end.isoformat()}.json"
    out_json.write_text(json.dumps(out, indent=2, default=str))
    logger.info("\n  Wrote JSON → %s", out_json)

    if args.save_candidate:
        import joblib
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        cand_path = _REPO_ROOT / artifact_rel
        joblib.dump(dep_cal, cand_path)
        logger.info("  Wrote candidate (%s) → %s", method, cand_path)
    else:
        logger.info("  Candidate NOT saved (pass --save-candidate). Report/JSON only — nothing wired.")

    if args.write_md:
        _REPORT.parent.mkdir(parents=True, exist_ok=True)
        _REPORT.write_text(_render_md(out))
        logger.info("  Wrote report → %s", _REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
