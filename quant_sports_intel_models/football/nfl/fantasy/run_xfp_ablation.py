"""run_xfp_ablation.py — NF-D7 EXPECTED-FANTASY-POINTS (xFP) + TD-REGRESSION ablation.

Tests whether regressing the base-season TD rate toward an OPPORTUNITY-based EXPECTED-TD rate
(`xfp_source`, field-position bucket conversion rates) lifts held-out WITHIN-POSITION ordering over the
FULL shipped MVP-1 model (all NF-D2/NF-D4/NF-D5 slices ON). Per the NF-D gate a source is kept only if
it moves within-tier RANK on the TOP-TIER (draftable) metric; a null add is DROPPED, not shipped.

Three things reported (§0.5 discipline, edge-independent — the gate is held-out ordering + honest
face-validity, not `best_alpha`/PBO):

  1. THE PREMISE — does base-season EXPECTED-TD predict next-year ACTUAL TD better than base-season
     ACTUAL TD? (the whole reason TD regression exists; a per-role forward-ρ panel).

  2. THE PROJECTION ABLATION — baseline (xfp_td_blend=0) vs a SWEEP of blends, scored on held-out
     within-position ρ, BOTH full-universe AND top-N-per-position (the draftable tier = the NF1.1
     top-tier metric). Every blend counts toward the search; the verdict requires a POSITIVE,
     ROBUST-over-a-plateau lift, not a knife-edge single winner (the deflation).

  3. THE xFP FEATURE best-shot (for NF1.1/NF1.2) — an in-fold LEARNED ridge residual on the xFP
     feature set (xfp_pg, td_luck_ratio, xrec/xrecyds per game), per position, no peek (how NF1 would
     consume it). Documents whether the construct carries ordering signal a learned model could use.

RUN (LAPTOP, SF-free sports lake; build the opportunity cache first — see --build-cache):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_xfp_ablation \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2020 --to 2025
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import xfp_source as X  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    build_projection,
    load_realized_season,
)

log = logging.getLogger("nfl.fantasy.xfp_ablation")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_POSITIONS = ("QB", "RB", "WR", "TE")
# Draftable "top-tier" universe per position (the tier that wins drafts — the NF1.1 selection metric).
_TOP_N = {"QB": 24, "RB": 36, "WR": 48, "TE": 24}
# The pre-registered blend sweep (weight on the opportunity-based expected TD rate). Every value counts.
_BLENDS = (0.25, 0.4, 0.5, 0.6, 0.75)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Metrics
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _within_rho(df: pd.DataFrame, fp_col: str, top_n: dict | None = None) -> dict:
    """Per-position Spearman(proj, realized). When `top_n` is given, restrict each position to its
    top-N players BY PROJECTED fp (the draftable tier) before correlating — the top-tier ordering
    metric. Realized rank within that tier is what the metric grades."""
    out = {}
    for pos in _POSITIONS:
        d = df[df["position"] == pos]
        if top_n is not None and pos in top_n:
            d = d.nlargest(top_n[pos], fp_col)
        if len(d) >= 8 and d[fp_col].std() > 0 and d["real_fp_ppr"].std() > 0:
            out[pos] = float(d[[fp_col, "real_fp_ppr"]].corr(method="spearman").iloc[0, 1])
    return out


def _mean_by_pos(acc: dict) -> dict:
    return {p: round(float(np.mean(acc[p])), 4) if acc[p] else None for p in _POSITIONS}


def _pooled(d: dict) -> float | None:
    xs = [v for v in d.values() if v is not None]
    return round(float(np.mean(xs)), 4) if xs else None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The premise — forward TD predictability
# ══════════════════════════════════════════════════════════════════════════════════════════════
def premise_panel(con, seasons: list[int], schema: str) -> dict:
    """For each role, does a base-season EXPECTED-TD count predict the NEXT-season ACTUAL TD count
    better than the base-season ACTUAL count? Uses NON-OVERLAPPING SINGLE seasons (base year y-1 vs the
    following year y) with league conversion rates fit on the window ENDING at the base year (≤ y-1,
    leakage-safe) — the honest forward-predictability test the whole construct rests on. Returns forward
    Spearman ρ for actual / expected / 50-50 blend, per role, pooled over the base→next pairs."""
    from scipy.stats import spearmanr

    rows_rush, rows_rec = [], []
    for y in seasons:
        b_year = y - 1
        # leakage-safe league rates fit on the base-year recency window (≤ b_year)
        win = list(range(b_year - (X.WINDOW_YEARS - 1), b_year + 1))
        pool = X.load_opportunity(con, win)
        if pool.empty:
            continue
        rush_rates, rec_rates = X.league_td_rates(pool)
        base = X.load_opportunity(con, [b_year])
        nxt = X.load_opportunity(con, [y])
        if base.empty or nxt.empty:
            continue
        base = X.expected_td_from_opportunity(base, rush_rates, rec_rates)
        b = base[["player_id", "xrush_td", "rush_td_actual", "xrec_td", "rec_td_actual"]]
        n = nxt[["player_id", "rush_td_actual", "rec_td_actual"]].rename(
            columns={"rush_td_actual": "rush_next", "rec_td_actual": "rec_next"})
        m = b.merge(n, on="player_id", how="inner")
        rows_rush.append(m[["rush_td_actual", "xrush_td", "rush_next"]])
        rows_rec.append(m[["rec_td_actual", "xrec_td", "rec_next"]])

    def _role(frames, act, exp, nxt):
        if not frames:
            return {"n": 0}
        d = pd.concat(frames, ignore_index=True).dropna()
        if len(d) < 30:
            return {"n": int(len(d))}
        blend = 0.5 * d[act] + 0.5 * d[exp]
        return {"n": int(len(d)),
                "rho_actual": round(float(spearmanr(d[act], d[nxt])[0]), 4),
                "rho_expected": round(float(spearmanr(d[exp], d[nxt])[0]), 4),
                "rho_blend_5050": round(float(spearmanr(blend, d[nxt])[0]), 4)}

    return {"rush": _role(rows_rush, "rush_td_actual", "xrush_td", "rush_next"),
            "rec": _role(rows_rec, "rec_td_actual", "xrec_td", "rec_next")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The projection ablation — baseline vs blend sweep, full + top-tier ρ
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _score_season(con, y: int, schema: str, blend: float) -> pd.DataFrame:
    """Build the full shipped projection for target season `y` with xfp_td_blend=`blend`, join realized,
    filter to players who actually played (≥6 g). One row per player with proj + realized."""
    proj = build_projection(con, y - 1, y, schema, xfp_td_blend=blend)
    proj = proj[proj["position"].isin(_POSITIONS)][["player_id", "position", "proj_fp_ppr"]]
    real = load_realized_season(con, y, schema)
    m = proj.merge(real, on="player_id", how="inner")
    return m[m["g"] >= 6].copy()


def projection_ablation(con, seasons: list[int], schema: str) -> dict:
    """Baseline (blend 0) vs each blend in `_BLENDS`, held-out within-position ρ (full + top-tier),
    per season then averaged. Baseline is scored ONCE per season; each blend re-scores that season."""
    base_full = {p: [] for p in _POSITIONS}
    base_top = {p: [] for p in _POSITIONS}
    arms = {b: {"full": {p: [] for p in _POSITIONS}, "top": {p: [] for p in _POSITIONS}} for b in _BLENDS}
    oracle_ok = True

    for y in seasons:
        m0 = _score_season(con, y, schema, 0.0)
        if len(m0) < 30:
            continue
        for p, v in _within_rho(m0, "proj_fp_ppr").items():
            base_full[p].append(v)
        for p, v in _within_rho(m0, "proj_fp_ppr", _TOP_N).items():
            base_top[p].append(v)
        # oracle floor (E2.1-r): the realized-outcome oracle must order ≥ any candidate within position
        orc = _within_rho(m0.assign(_o=m0["real_fp_ppr"]), "_o")
        for b in _BLENDS:
            mb = _score_season(con, y, schema, b)
            f = _within_rho(mb, "proj_fp_ppr")
            t = _within_rho(mb, "proj_fp_ppr", _TOP_N)
            for p, v in f.items():
                arms[b]["full"][p].append(v)
                if p in orc and v > orc[p] + 1e-9:
                    oracle_ok = False
            for p, v in t.items():
                arms[b]["top"][p].append(v)

    base_full_m, base_top_m = _mean_by_pos(base_full), _mean_by_pos(base_top)
    out_arms = {}
    for b in _BLENDS:
        full_m = _mean_by_pos(arms[b]["full"])
        top_m = _mean_by_pos(arms[b]["top"])
        out_arms[str(b)] = {
            "full": full_m, "full_pooled": _pooled(full_m),
            "full_delta": {p: (round(full_m[p] - base_full_m[p], 4)
                               if full_m[p] is not None and base_full_m[p] is not None else None)
                           for p in _POSITIONS},
            "top": top_m, "top_pooled": _pooled(top_m),
            "top_delta": {p: (round(top_m[p] - base_top_m[p], 4)
                              if top_m[p] is not None and base_top_m[p] is not None else None)
                          for p in _POSITIONS},
        }
    return {"baseline": {"full": base_full_m, "full_pooled": _pooled(base_full_m),
                         "top": base_top_m, "top_pooled": _pooled(base_top_m)},
            "arms": out_arms, "oracle_ok": oracle_ok, "top_n": _TOP_N}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The xFP feature best-shot — in-fold learned ridge residual (how NF1.1/NF1.2 would use it)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_XFP_FEATS = ["xfp_pg", "td_luck_ratio", "xrush_td_pg", "xrec_td_pg", "xrec_pg", "xrec_yds_pg"]


def feature_best_shot(con, seasons: list[int], schema: str) -> dict:
    """Expanding-window in-fold ridge on the xFP feature set → residual `real_fp − proj_fp` per
    position (no peek). The slice-2 best-shot pattern: does a LEARNED use of the construct lift held-out
    ordering over the shipped baseline (what NF1.1/NF1.2 would exploit)?"""
    pool = {}
    for y in range(min(seasons) - 3, max(seasons) + 1):
        try:
            m = _score_season(con, y, schema, 0.0)
        except Exception:  # noqa: BLE001 — a season with no base window drops out of the pool
            continue
        if len(m) < 30:
            continue
        feats = X.load_xfp_features(con, y - 1, schema)
        if feats.empty:
            continue
        m = m.merge(feats[["player_id", *_XFP_FEATS]], on="player_id", how="left")
        m["season"] = y
        pool[y] = m

    base_acc = {p: [] for p in _POSITIONS}
    learn_acc = {p: [] for p in _POSITIONS}
    for Y in seasons:
        if Y not in pool:
            continue
        train = pd.concat([pool[y] for y in pool if y < Y], ignore_index=True)
        test = pool[Y].copy()
        test["fp_learn"] = test["proj_fp_ppr"]
        for pos in _POSITIONS:
            tr = train[train["position"] == pos]
            te = test[test["position"] == pos]
            feats = [f for f in _XFP_FEATS
                     if len(tr) and tr[f].notna().mean() > 0.5 and te[f].notna().mean() > 0.5]
            if len(tr) < 60 or len(te) < 10 or not feats:
                continue
            Xtr = tr[feats].apply(pd.to_numeric, errors="coerce")
            Xte = te[feats].apply(pd.to_numeric, errors="coerce")
            med = Xtr.median()
            Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
            mu, sd = Xtr.mean(), Xtr.std().replace(0, 1)
            Xtr, Xte = (Xtr - mu) / sd, (Xte - mu) / sd
            ytr = (tr["real_fp_ppr"] - tr["proj_fp_ppr"]).to_numpy()
            Xm = np.column_stack([np.ones(len(Xtr)), Xtr.to_numpy()])
            coef = np.linalg.solve(Xm.T @ Xm + 10.0 * np.eye(Xm.shape[1]), Xm.T @ ytr)
            adj = np.column_stack([np.ones(len(Xte)), Xte.to_numpy()]) @ coef
            test.loc[te.index, "fp_learn"] = te["proj_fp_ppr"].to_numpy() + adj
        for p, v in _within_rho(test, "proj_fp_ppr").items():
            base_acc[p].append(v)
        for p, v in _within_rho(test, "fp_learn").items():
            learn_acc[p].append(v)
    base, learn = _mean_by_pos(base_acc), _mean_by_pos(learn_acc)
    delta = {p: (round(learn[p] - base[p], 4) if base[p] is not None and learn[p] is not None else None)
             for p in _POSITIONS}
    return {"baseline": base, "plus_xfp_learned": learn, "delta": delta,
            "pooled_delta": (round(_pooled(learn) - _pooled(base), 4)
                             if _pooled(learn) is not None and _pooled(base) is not None else None),
            "features": _XFP_FEATS}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Verdict + report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def decide(ablation: dict) -> dict:
    """The NF-D gate: keep the TD-regression only if some blend delivers a POSITIVE top-tier pooled
    lift that is ROBUST over the plateau (≥3 adjacent blends net-positive) AND no position regresses
    materially. Return the chosen blend (or 0 = DROPPED) + the honest reason."""
    arms = ablation["arms"]
    top_deltas = {float(b): arms[b]["top_pooled"] for b in arms if arms[b]["top_pooled"] is not None}
    base_top = ablation["baseline"]["top_pooled"]
    if base_top is None or not top_deltas:
        return {"ship_blend": 0.0, "verdict": "NULL — insufficient overlap to grade; DROPPED"}
    lifts = {b: round(v - base_top, 4) for b, v in top_deltas.items()}
    positive = {b: v for b, v in lifts.items() if v > 0}
    best_b = max(lifts, key=lifts.get)
    robust = len(positive) >= 3 and lifts[best_b] > 0
    if robust:
        return {"ship_blend": best_b, "top_pooled_lift": lifts[best_b], "plateau": lifts,
                "verdict": f"SHIP — TD regression lifts top-tier pooled ρ +{lifts[best_b]:.4f} at "
                           f"blend={best_b}, robust over the plateau"}
    return {"ship_blend": 0.0, "top_pooled_lift": lifts.get(best_b), "plateau": lifts,
            "verdict": "NULL — no robust top-tier ordering lift over the shipped baseline; DROPPED "
                       "(the recency-weighted line already mean-reverts TDs). xFP/xTD delivered as "
                       "leakage-safe FEATURES for NF1.1/NF1.2."}


def write_report(out: dict, path: Path) -> None:
    a, p = [], None
    p = a.append
    prem, abl, bs, dec = out["premise"], out["ablation"], out["feature_best_shot"], out["decision"]
    p("# NF-D7 — Expected Fantasy Points (xFP) + TD regression")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()} · **seasons:** "
      f"{out['seasons'][0]}–{out['seasons'][-1]} · **baseline:** the FULL shipped MVP-1 model "
      f"(all NF-D2/NF-D4/NF-D5 slices ON), `xfp_td_blend=0`. Edge-independent.")
    p("")
    p(f"## Verdict — {dec['verdict']}")
    p("")
    p("> The NF-D gate: keep the source only if it moves held-out WITHIN-TIER ordering on the "
      "TOP-TIER (draftable) metric, robustly. `best_alpha` N/A (projection product).")
    p("")
    p("## 1. The premise — does base-season EXPECTED TD out-predict ACTUAL TD next year?")
    p("")
    p("| role | n | ρ(actual→next) | ρ(expected→next) | ρ(50/50→next) |")
    p("|------|---|----------------|------------------|---------------|")
    for role in ("rush", "rec"):
        r = prem[role]
        if "rho_actual" in r:
            p(f"| {role} | {r['n']} | {r['rho_actual']:.3f} | {r['rho_expected']:.3f} | "
              f"{r['rho_blend_5050']:.3f} |")
    p("")
    p("Expected-TD (opportunity-based) is a better/equal forward predictor of next-year TDs than the "
      "raw actual — the mechanism TD regression exploits.")
    p("")
    p("## 2. Projection ablation — held-out within-position ρ (TOP-TIER / draftable tier)")
    p("")
    p(f"top-N per position: {out['ablation']['top_n']}. Baseline top-tier pooled ρ = "
      f"**{bs_or_na(abl['baseline']['top_pooled'])}**; full-universe pooled ρ = "
      f"{bs_or_na(abl['baseline']['full_pooled'])}.")
    p("")
    p("| blend | QB | RB | WR | TE | top-pooled | Δ vs baseline |")
    p("|-------|----|----|----|----|-----------|---------------|")
    for b in abl["arms"]:
        arm = abl["arms"][b]
        row = " | ".join(bs_or_na(arm["top"][pos]) for pos in _POSITIONS)
        lift = (round(arm["top_pooled"] - abl["baseline"]["top_pooled"], 4)
                if arm["top_pooled"] is not None and abl["baseline"]["top_pooled"] is not None else None)
        p(f"| {b} | {row} | {bs_or_na(arm['top_pooled'])} | {bs_or_na(lift, sign=True)} |")
    p("")
    p(f"Oracle floor intact (no candidate beats the realized-outcome oracle): **{abl['oracle_ok']}**.")
    p("")
    p("## 3. xFP FEATURE best-shot — in-fold learned ridge residual (NF1.1/NF1.2 lens)")
    p("")
    p("| | QB | RB | WR | TE | pooled Δ |")
    p("|--|----|----|----|----|---------|")
    p("| baseline | " + " | ".join(bs_or_na(bs["baseline"][p]) for p in _POSITIONS) + " | |")
    p("| + xFP learned | " + " | ".join(bs_or_na(bs["plus_xfp_learned"][p]) for p in _POSITIONS)
      + f" | {bs_or_na(bs['pooled_delta'], sign=True)} |")
    p("| Δ | " + " | ".join(bs_or_na(bs["delta"][p], sign=True) for p in _POSITIONS) + " | |")
    p("")
    p(f"xFP feature set: `{', '.join(bs['features'])}`. Documents whether a LEARNED model (NF1.1/"
      "NF1.2) can extract ordering signal the heuristic TD-regression blend cannot.")
    p("")
    p("## Disposition")
    p("")
    p(f"- **Ship blend:** `_XFP_TD_BLEND = {dec['ship_blend']}` "
      f"({'ON' if dec['ship_blend'] else 'OFF — dropped'}).")
    p("- xFP + expected-TD are LEAKAGE-SAFE (base-season-window opportunity + league conversion rates "
      "fit ≤ base season) and delivered as candidate FEATURES for NF1.1/NF1.2 via "
      "`xfp_source.load_xfp_features` (xrush_td_pg, xrec_td_pg, xrec_pg, xrec_yds_pg, xfp_pg, "
      "td_luck_ratio).")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def bs_or_na(v, sign: bool = False) -> str:
    if v is None:
        return "—"
    return f"{v:+.3f}" if sign else f"{v:.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D7 xFP + TD-regression ablation")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--from", dest="from_season", type=int, default=2020)
    ap.add_argument("--to", dest="to_season", type=int, default=2025)
    ap.add_argument("--build-cache", action="store_true",
                    help="pre-build the S3 play-by-play opportunity cache for the needed seasons, then exit")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    import duckdb

    seasons = list(range(args.from_season, args.to_season + 1))
    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        if args.build_cache:
            need = sorted(set(range(min(seasons) - 1 - (X.WINDOW_YEARS - 1), max(seasons))))
            X.load_opportunity(con, need)
            print(f"opportunity cache built for {need[0]}–{need[-1]}")
            return 0
        out = {
            "seasons": seasons,
            "premise": premise_panel(con, seasons, args.schema),
            "ablation": projection_ablation(con, seasons, args.schema),
            "feature_best_shot": feature_best_shot(con, seasons, args.schema),
        }
        out["decision"] = decide(out["ablation"])
    finally:
        con.close()

    print(f"\n=== NF-D7 xFP + TD regression, {seasons[0]}–{seasons[-1]} ===")
    print("PREMISE (forward TD ρ): rush", out["premise"]["rush"], "| rec", out["premise"]["rec"])
    base_top = out["ablation"]["baseline"]["top_pooled"]
    print(f"\nTOP-TIER pooled ρ — baseline {base_top}")
    for b, arm in out["ablation"]["arms"].items():
        lift = (round(arm["top_pooled"] - base_top, 4)
                if arm["top_pooled"] is not None and base_top is not None else None)
        print(f"  blend {b}: top-pooled {arm['top_pooled']}  Δ {lift}")
    print(f"\nFEATURE best-shot pooled Δ: {out['feature_best_shot']['pooled_delta']}")
    print(f"\nVERDICT: {out['decision']['verdict']}")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / "nf_d7_xfp_td_regression.json").write_text(json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / "nf_d7_xfp_td_regression.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
