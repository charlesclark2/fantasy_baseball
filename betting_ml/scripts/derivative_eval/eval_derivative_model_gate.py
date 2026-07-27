#!/usr/bin/env python3
"""eval_derivative_model_gate.py — Edge Program Story E2.6 (angle 3): the model-vs-market gate.

E13.13 (angles 1+2) asked whether the derivative market is efficient vs its OWN de-vigged price →
CLEAN NULL. **E2.6 (this script) is angle 3:** does our market-blind model — the E2.5 per-side
NegBin `totals_generative_v1` convolved into the honest game-total distribution (E2.2/E2.3, ρ=0) —
BEAT the derivative's CLOSING line? We price team-total / alt-total / full-total from the convolved
distribution, de-vig each close, bet the model's disagreement, and settle the realized PnL AT THE
CLOSE net of the derivative's own vig — GAME-level, deflated (PBO<0.2 + DSR≥0.95 + BH-FDR).

Beating the CLOSE is the strictest cashability test (the close is the sharpest number the book
posts). History carries only closes (E2.0) → the historical gate is realized ROI net of vig at the
close; true bet-time-vs-close CLV runs on the E2.0b forward stream with this SAME harness.

HONEST FRAME (§0.5): `best_alpha=0`. With MLB main-market efficiency (E13.8), E5.4's prop null and
E13.13's derivative-efficiency null, a CLEAN NULL (no derivative beats its own close after
deflation) is the LIKELY and fully-valid outcome. Report the deflated number; never manufacture a
survivor.

DATA (§0.5 — cached S3, NO fresh Snowflake beyond the one build_cache read → parquet):
  * derivative CLOSES        ← mart_derivative_closes (E2.0 pipeline; team_totals + alternate_totals)
  * model per-side μ         ← the E2.5 served signal store `totals_generative_signals` (`where is_oos`)
  * per-side dispersion r     ← totals_distribution_v1.json (E2.3 held-out r; home 4.06 / away 3.40)
  * realized final runs       ← mart_game_results (home_final_score / away_final_score)
  * (optional) champion total μ/σ ← --champ-preds parquet, for the distributional-accuracy gate

⛔ MARKET-BLIND: the model took ZERO market features; odds enter ONLY here (eval/CLV layer).

RUN ORDER:
  uv run python betting_ml/scripts/derivative_eval/eval_derivative_model_gate.py --smoke
  uv run python betting_ml/scripts/derivative_eval/eval_derivative_model_gate.py --build-cache   # operator, >1-min S3
  uv run python betting_ml/scripts/derivative_eval/eval_derivative_model_gate.py                 # eval cache → dossier
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils import derivative_model_gate as dg
from betting_ml.utils.overfitting import DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE
from betting_ml.utils.promotion_gate import (
    PredictiveOutput, crps_ensemble, crps_normal, evaluate_promotion,
)
from betting_ml.utils.totals_distribution import TotalsDistributionParams

# ── Paths ─────────────────────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[3]
CACHE = _REPO / "betting_ml" / "data" / "cache" / "e2_6_model_gate_frame.parquet"
DOSSIER_DIR = _REPO / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
_DIST_JSON = _REPO / "betting_ml" / "models" / "sub_models" / "totals_perside_v1" / "totals_distribution_v1.json"
_S3_BUCKET = "s3://baseball-betting-ml-artifacts"


def _out_paths(suffix: str = ""):
    return (DOSSIER_DIR / f"e2_6_derivative_gates{suffix}.json",
            DOSSIER_DIR / f"e2_6_derivative_gates{suffix}.md",
            DOSSIER_DIR / f"e2_6_model_gate_grid{suffix}.csv")


def _load_dispersion() -> tuple[float, float]:
    """E2.3 held-out per-side r (home 4.06 / away 3.40) — NEVER the artifact train-fit r (7.449;
    the under-dispersion E2.3 fixed). Committed-local read (the operator promotes the same json to
    S3 for the box)."""
    try:
        d = json.loads(_DIST_JSON.read_text())
        p = TotalsDistributionParams.from_dict(d)
        return float(p.r_home), float(p.r_away)
    except Exception as exc:  # pragma: no cover - smoke supplies r directly
        print(f"[warn] dispersion json unreadable ({exc}); falling back to pooled 3.7311")
        return 3.7311, 3.7311


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Heavy S3 read → cached parquet (operator-run; §0.5 one-read-then-cache)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_cache(seasons: list[int]) -> pd.DataFrame:
    """Read derivative closes + served model μ + realized runs from S3 → one per-quote frame.

    Derivative closes come from `mart_derivative_closes` (the E2.0 pipeline — team_totals carries the
    team in `outcome_description`; alternate_totals distinguishes quotes by `outcome_point`). Model μ
    comes from the E2.5 signal store mirror `{LAKEHOUSE}/totals_generative_signals/data.parquet`
    (SELECT*-cased → normalised to lower here), pivoted side → mu_home/mu_away, carrying `is_oos`."""
    import duckdb
    from scripts.utils.lakehouse_read import LAKEHOUSE, duck_connect

    con = duck_connect()
    season_list = ",".join(str(s) for s in seasons)

    # 1) team_totals + alternate_totals closes (skip a market whose parquet is absent, not fatal).
    parts: list[pd.DataFrame] = []
    for m in (dg.TEAM_TOTALS, dg.ALT_TOTALS):
        sql = f"""
        SELECT game_pk, home_team, away_team, bookmaker_key,
               '{m}'                                        AS market,
               lower(outcome_name)                          AS ou,
               outcome_description                          AS outcome_desc,
               outcome_point                                AS line,
               outcome_price_american                       AS price,
               year(commence_time::timestamp)               AS season,
               commence_time::date                          AS game_date
        FROM read_parquet('{LAKEHOUSE}/mart_derivative_closes/**/*.parquet', union_by_name=true)
        WHERE market_key = '{m}' AND outcome_price_american IS NOT NULL
        """
        try:
            dfm = con.execute(sql).fetchdf()
            parts.append(dfm)
            print(f"[cache] {m}: {len(dfm):,} closing quotes")
        except duckdb.IOException as exc:
            if "No files found" in str(exc) or "HTTP" in str(exc):
                print(f"[cache] {m}: no S3 files — skipped (partial/deferred)")
            else:
                raise
    if not parts:
        raise SystemExit("[error] no team/alt derivative closes under mart_derivative_closes — "
                         "check the E2.0 backfill / capture.")
    closes = pd.concat(parts, ignore_index=True)
    closes = closes[closes["season"].isin(seasons)]

    # Reshape the Over/Under pair → one row per (game, market, book, team, line) via a self-MERGE,
    # NOT pivot_table — pivot_table over ~2M rows with a 9-col index effectively hangs. fillna the
    # keys first (a NaN key drops the row); alternate_totals has a null outcome_description.
    closes["outcome_desc"] = closes["outcome_desc"].fillna("__none__")
    keys = ["game_pk", "market", "bookmaker_key", "outcome_desc", "line",
            "home_team", "away_team", "season", "game_date"]
    over = (closes[closes["ou"] == "over"].drop_duplicates(subset=keys)[keys + ["price"]]
            .rename(columns={"price": "over_price"}))
    under = (closes[closes["ou"] == "under"].drop_duplicates(subset=keys)[keys + ["price"]]
             .rename(columns={"price": "under_price"}))
    wide = over.merge(under, on=keys, how="outer")
    for c in ("over_price", "under_price"):
        if c not in wide:
            wide[c] = np.nan
    # team_side: team_totals → home/away by outcome_description; alt/main → None (game total)
    wide["team_side"] = np.where(
        wide["market"] == dg.TEAM_TOTALS,
        np.where(wide["outcome_desc"].astype(str) == wide["home_team"].astype(str), "home",
                 np.where(wide["outcome_desc"].astype(str) == wide["away_team"].astype(str),
                          "away", None)),
        None)
    wide = wide[~((wide["market"] == dg.TEAM_TOTALS) & wide["team_side"].isna())]

    # 2) served model μ (E2.5 signal store) — pivot side → mu_home / mu_away + is_oos.
    sig = con.execute(
        f"SELECT * FROM read_parquet('{LAKEHOUSE}/totals_generative_signals/data.parquet', "
        "union_by_name=true)").fetchdf()
    sig.columns = [c.lower() for c in sig.columns]
    mu_col = next((c for c in ("totals_perside_mu", "totals_perside_raw", "mu") if c in sig.columns), None)
    if mu_col is None:
        raise SystemExit(f"[error] no μ column in signal store (cols={list(sig.columns)})")
    sig = sig[["game_pk", "side", mu_col, "is_oos"]].rename(columns={mu_col: "mu"})
    # SELECT*-cased store: game_pk may deserialize as object/string and side as HOME/AWAY — normalise
    # both, else the game_pk merge dtype-clashes and the pivot yields mu_HOME/mu_AWAY (silently NULL).
    sig["game_pk"] = pd.to_numeric(sig["game_pk"], errors="coerce").astype("Int64")
    sig = sig[sig["game_pk"].notna()]
    sig["game_pk"] = sig["game_pk"].astype("int64")
    sig["side"] = sig["side"].astype(str).str.lower()
    mu_wide = sig.pivot_table(index="game_pk", columns="side", values="mu", aggfunc="first")
    mu_wide.columns = [f"mu_{c}" for c in mu_wide.columns]
    oos = sig.groupby("game_pk")["is_oos"].min().rename("is_oos")   # both sides OOS ⇒ game OOS
    mu_wide = mu_wide.join(oos).reset_index()

    # 3) realized final runs.
    res = con.execute(
        f"SELECT game_pk, home_final_score AS final_home, away_final_score AS final_away "
        f"FROM read_parquet('{LAKEHOUSE}/mart_game_results/**/*.parquet', union_by_name=true) "
        f"WHERE game_year IN ({season_list}) AND home_final_score IS NOT NULL").fetchdf()
    con.close()

    # align game_pk dtype across all three frames before the joins (closes/res may be int64/object)
    for _df in (wide, res):
        _df["game_pk"] = pd.to_numeric(_df["game_pk"], errors="coerce").astype("int64")
    frame = (wide.merge(mu_wide, on="game_pk", how="inner")
             .merge(res, on="game_pk", how="inner"))
    for c in ("mu_home", "mu_away"):
        if c not in frame:
            frame[c] = np.nan
    frame["line"] = frame["line"].astype(float)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(CACHE, index=False)
    print(f"[cache] wrote {len(frame):,} rows → {CACHE}  "
          f"({frame['game_pk'].nunique():,} games, {frame['bookmaker_key'].nunique()} books, "
          f"markets={sorted(frame['market'].unique())}, is_oos={int(frame['is_oos'].sum()):,})")
    return frame


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Price the served model + attach the market columns the gate consumes
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _prepare(frame: pd.DataFrame, r_home: float, r_away: float, *, n_draws: int,
             seed: int = 11, placebo: bool = False) -> tuple[pd.DataFrame, dict]:
    """Filter to is_oos rows, price each game's convolved distribution, and attach per-quote
    model_p_over / fair_over / devig_valid / actual_total / kind.

    `placebo=True` = the NEGATIVE CONTROL: each game is priced with ANOTHER game's μ (a fixed roll
    of the μ columns), breaking the model↔outcome link while keeping the market/close/outcome fixed.
    A contaminated gate would still fire on this; a sound one must return a clean null (the E13.16
    durable lesson — a CLV gate needs a working placebo)."""
    df = frame[frame["is_oos"].astype(bool)].copy()
    df = df[np.isfinite(df["mu_home"].to_numpy(float)) & np.isfinite(df["mu_away"].to_numpy(float))]
    if df.empty:
        return df, {"n_games": 0, "note": "no is_oos rows with μ"}

    games = (df[["game_pk", "mu_home", "mu_away", "final_home", "final_away"]]
             .drop_duplicates("game_pk").reset_index(drop=True))
    if placebo and len(games) > 1:                            # roll μ so each game gets another's
        games["mu_home"] = np.roll(games["mu_home"].to_numpy(), len(games) // 2)
        games["mu_away"] = np.roll(games["mu_away"].to_numpy(), len(games) // 2)
    gidx = {int(g): i for i, g in enumerate(games["game_pk"])}
    rng = np.random.default_rng(seed)
    samples = dg.price_game_samples(games["mu_home"].to_numpy(float),
                                    games["mu_away"].to_numpy(float), r_home, r_away, rng,
                                    n_draws=n_draws)

    df["game_index"] = df["game_pk"].map(gidx).to_numpy()
    df["kind"] = np.where(df["market"].to_numpy() == dg.TEAM_TOTALS,
                          np.where(df["team_side"].to_numpy() == "home", "home_total", "away_total"),
                          "total")
    df["model_p_over"] = dg.prob_over_at_lines(
        samples, df["game_index"].to_numpy(), df["kind"].to_numpy(object), df["line"].to_numpy(float))

    # Vectorised additive de-vig (matches derivative_eval.devig_pair / implied_no_vig_pair) — a
    # row-wise .apply over ~1M quotes hangs; this is the same math in numpy.
    op = pd.to_numeric(df["over_price"], errors="coerce").to_numpy(float)
    up = pd.to_numeric(df["under_price"], errors="coerce").to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):     # np.where evals both branches; the
        # unused +ve branch divides by zero at an even-money −100 price → discarded, result correct
        io = np.where(op > 0, 100.0 / (op + 100.0), np.abs(op) / (np.abs(op) + 100.0))
        iu = np.where(up > 0, 100.0 / (up + 100.0), np.abs(up) / (np.abs(up) + 100.0))
    tot = io + iu
    valid = np.isfinite(op) & np.isfinite(up) & np.isfinite(io) & np.isfinite(iu) & (tot > 0)
    df["fair_over"] = np.where(valid, io / np.where(tot > 0, tot, np.nan), np.nan)
    df["hold"] = np.where(valid, tot - 1.0, np.nan)
    df["devig_valid"] = valid

    fh = games.set_index("game_pk")["final_home"]
    fa = games.set_index("game_pk")["final_away"]
    total = df["game_pk"].map(fh).to_numpy(float) + df["game_pk"].map(fa).to_numpy(float)
    df["actual_total"] = np.where(
        df["kind"].to_numpy() == "home_total", df["game_pk"].map(fh).to_numpy(float),
        np.where(df["kind"].to_numpy() == "away_total", df["game_pk"].map(fa).to_numpy(float), total))
    meta = {"n_games": int(games.shape[0]), "n_quotes": int(len(df)),
            "r_home": r_home, "r_away": r_away, "n_draws": n_draws}
    return df, meta


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Distributional-accuracy gate (convolved total crps_ensemble vs champion crps_normal)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def distributional_gate(frame: pd.DataFrame, r_home: float, r_away: float, *,
                        n_draws: int, seed: int = 3) -> dict:
    """E2.6 leg 1: convolved-total `crps_ensemble` beats the `total_runs` champion `crps_normal`
    (via `evaluate_promotion`, a SamplesSpec adapter — the E2.3 distribution scored as predictive
    SAMPLES). Runs only when the frame carries champion `champ_total_mu`/`champ_total_sd`; else it
    reports SKIPPED with the reason (operator supplies champion preds via --champ-preds)."""
    need = {"champ_total_mu", "champ_total_sd"}
    g = frame[frame["is_oos"].astype(bool)].drop_duplicates("game_pk").copy()
    g = g[np.isfinite(g["mu_home"].to_numpy(float)) & np.isfinite(g["mu_away"].to_numpy(float))]
    if not need.issubset(frame.columns) or g.empty or g[list(need)].isna().all().any():
        return {"ran": False, "note": "champion total μ/σ not supplied (--champ-preds) — "
                "distributional gate skipped; derivative gate is E2.6's core."}
    y = (g["final_home"].to_numpy(float) + g["final_away"].to_numpy(float))
    season = g["season"].to_numpy(int) if "season" in g else np.full(len(g), 0)
    rng = np.random.default_rng(seed)
    dist = dg.price_game_samples(g["mu_home"].to_numpy(float), g["mu_away"].to_numpy(float),
                                 r_home, r_away, rng, n_draws=n_draws)
    conv = PredictiveOutput.from_samples(dist["total"])
    chal = crps_ensemble(y, conv.samples)
    champ = crps_normal(y, g["champ_total_mu"].to_numpy(float), g["champ_total_sd"].to_numpy(float))
    verdict = evaluate_promotion(season, champ, chal, metric="crps")
    return {"ran": True, "n": int(len(g)), "champion_crps": float(np.mean(champ)),
            "convolved_crps": float(np.mean(chal)),
            "promote": verdict.decision == "PROMOTE",
            "overall_delta": float(verdict.overall_delta),
            "verdict": "; ".join(verdict.reasons) if verdict.reasons else verdict.decision}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Full eval → dossier
# ════════════════════════════════════════════════════════════════════════════════════════════════
def run_eval(frame: pd.DataFrame, *, suffix: str = "", synthetic: bool = False,
             n_draws: int = dg.DEFAULT_N_DRAWS) -> dict:
    r_home, r_away = (frame.attrs.get("r_home"), frame.attrs.get("r_away"))
    if r_home is None:
        r_home, r_away = _load_dispersion()
    df, prep_meta = _prepare(frame, r_home, r_away, n_draws=n_draws)
    books = sorted(df["bookmaker_key"].dropna().unique().tolist()) if not df.empty else []
    markets = {}
    for m in dg.FULLGAME_MARKETS:
        dm = df[df["market"] == m] if not df.empty else df
        markets[m] = dg.evaluate_market(dm, m, books)
    # Negative control (E13.16 durable lesson): re-run the grid with each game priced by ANOTHER
    # game's μ — a sound gate must NOT fire on it. Reported beside the real verdict.
    df_pl, _ = _prepare(frame, r_home, r_away, n_draws=n_draws, placebo=True)
    placebo = {}
    for m in dg.FULLGAME_MARKETS:
        dmp = df_pl[df_pl["market"] == m] if not df_pl.empty else df_pl
        pr = dg.evaluate_market(dmp, m, books)
        placebo[m] = {"n_candidates": len(pr["candidates"]), "fdr_survive": pr["fdr"]["n_survive"],
                      "pbo": pr["pbo"].get("pbo")}
    dist_gate = distributional_gate(frame, r_home, r_away, n_draws=min(n_draws, 4000))
    meta = {"synthetic": synthetic, **prep_meta,
            "seasons": sorted(frame["season"].dropna().unique().tolist()) if "season" in frame else [],
            "n_books": len(books), "markets_present": sorted(
                [m for m, r in markets.items() if r["present"]])}
    result = {"meta": meta, "markets": markets, "distributional_gate": dist_gate,
              "placebo_control": placebo}
    write_dossier(result, suffix=suffix, synthetic=synthetic)
    return result


def _fmt(x, nd=4):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def write_dossier(result: dict, *, suffix: str = "", synthetic: bool = False) -> None:
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    json_out, md_out, csv_out = _out_paths(suffix)
    clean = {"meta": result["meta"], "distributional_gate": result["distributional_gate"],
             "placebo_control": result.get("placebo_control", {}),
             "markets": {m: {k: v for k, v in r.items() if k != "configs"}
                         for m, r in result["markets"].items()}}
    json_out.write_text(json.dumps(clean, indent=2, default=str))

    rows = []
    for m, r in result["markets"].items():
        for c in r.get("configs", []):
            rows.append({"market": m, "name": c["name"], "book_group": c["book_group"],
                         "line_bucket": c["line_bucket"], "tau": c["tau"], "n": c["n"],
                         "roi": c["roi"], "sharpe": c["sharpe"], "roi_p": c["roi_p"],
                         "mean_edge": c["mean_edge"], "roi_fdr_survive": c.get("roi_fdr_survive"),
                         "season_sign_consistent": c["season_sign_consistent"]})
    pd.DataFrame(rows).to_csv(csv_out, index=False)
    md_out.write_text(_render_md(result, synthetic=synthetic))
    n_cand = sum(len(r["candidates"]) for r in result["markets"].values())
    print(f"[dossier] {md_out.name} · {json_out.name} · {csv_out.name} → {DOSSIER_DIR}")
    print(f"[verdict] {n_cand} candidate(s) across {result['meta']['markets_present']}")
    for m, r in result["markets"].items():
        if r["present"]:
            print(f"  [{m}] PBO={_fmt(r['pbo'].get('pbo'), 3)} DSR={_fmt(r['dsr'].get('dsr'), 3)} "
                  f"FDR-survive={r['fdr']['n_survive']}/{r['fdr']['n_tested']} → {r['verdict']}")


def _render_md(result: dict, *, synthetic: bool = False) -> str:
    meta, markets, dgate = result["meta"], result["markets"], result["distributional_gate"]
    n_cand = sum(len(r["candidates"]) for r in markets.values())
    overall = ("CLEAN NULL — no derivative beats its own close after deflation" if n_cand == 0
               else f"{n_cand} candidate(s) — see per-market rows")
    banner = (["> ⚠️ **SYNTHETIC SMOKE OUTPUT** — `--smoke` on fabricated data proving the pipeline "
               "end-to-end. NOT the real evaluation.", ""] if synthetic else [])
    L = banner + [
        "# E2.6 — Derivative pricing + validation gates (angle 3: model-vs-market)", "",
        f"**Overall: {overall}.**", "",
        "Our market-blind model (E2.5 `totals_generative_v1` per-side NegBin → E2.2/E2.3 convolved, "
        "ρ=0) prices each derivative; we bet its disagreement with the de-vigged CLOSE and settle "
        "realized PnL AT THE CLOSE net of the derivative's own vig, **GAME-level** (correlated "
        "book-quotes collapsed per game — the E13.13 anti-clustering rule), **deflated** "
        f"(PBO<{PBO_SHADOW_TO_LIVE} + DSR≥{DSR_CONFIDENCE} + BH-FDR q={dg.FDR_Q}). "
        "`best_alpha=0`: beating the close is the strictest cashability test; a clean null is the "
        "likely, fully-valid result (E13.8 main-market efficiency + E5.4 + E13.13 nulls).", "",
        "## Coverage", "",
        f"- {meta.get('n_quotes', 0):,} `is_oos` closing quotes · {meta.get('n_games', 0):,} games · "
        f"{meta.get('n_books', 0)} books · seasons {meta.get('seasons')}",
        f"- markets priced: {meta.get('markets_present')}  ·  per-side r "
        f"home {_fmt(meta.get('r_home'), 3)} / away {_fmt(meta.get('r_away'), 3)}  ·  "
        f"{meta.get('n_draws', '—')} draws/game", "",
        "## Leg 1 — distributional accuracy (convolved total vs `total_runs` champion)", ""]
    if dgate.get("ran"):
        L += [f"- convolved-total CRPS **{_fmt(dgate['convolved_crps'])}** vs champion crps_normal "
              f"**{_fmt(dgate['champion_crps'])}** over {dgate['n']:,} games → "
              f"`evaluate_promotion` PROMOTE={dgate['promote']}", f"  - {dgate['verdict']}"]
    else:
        L += [f"- _skipped_: {dgate.get('note')}"]
    L += ["", "## Leg 2 — derivative edge (per market, gated vs its OWN close)", "",
          "| market | present | quotes-selectable | PBO | DSR | FDR survive | candidates | verdict |",
          "|---|:--:|--:|--:|--:|:--:|--:|---|"]
    for m, r in markets.items():
        L.append(f"| {m} | {'✓' if r['present'] else '·'} | {r.get('n_selectable', 0)} | "
                 f"{_fmt(r['pbo'].get('pbo'), 3)} | {_fmt(r['dsr'].get('dsr'), 3)} | "
                 f"{r['fdr']['n_survive']}/{r['fdr']['n_tested']} | {len(r['candidates'])} | "
                 f"{r['verdict']} |")
    # top configs per market (the no-cherry-pick ledger; full CSV is beside this file)
    L += ["", "### Strongest configs per market (game-level ROI net of vig; deflation above)", ""]
    for m, r in markets.items():
        if not r["present"] or not r.get("configs"):
            continue
        sel = sorted([c for c in r["configs"] if c["n"] >= dg.MIN_GAMES],
                     key=lambda c: -c["roi"])[:5]
        if not sel:
            L.append(f"- **{m}**: no config reached {dg.MIN_GAMES} games.")
            continue
        L.append(f"- **{m}** (top by ROI):")
        for c in sel:
            L.append(f"    - `{c['name']}` — {c['n']} games, ROI {_fmt(c['roi'])}, "
                     f"edge {_fmt(c['mean_edge'], 3)}, roi_p {_fmt(c['roi_p'], 3)}, "
                     f"season-consistent {'✓' if c['season_sign_consistent'] else '·'}, "
                     f"FDR {'✓' if c.get('roi_fdr_survive') else '·'}")
    pl = result.get("placebo_control", {})
    if pl:
        L += ["", "## Negative control (placebo — each game priced by ANOTHER game's μ)", "",
              "The E13.16 durable lesson: a CLV gate needs a working placebo. Breaking the "
              "model↔outcome link must yield **0 candidates** — a placebo that fires means the gate "
              "itself manufactures edge. (Real-vs-placebo candidate counts:)", "",
              "| market | placebo candidates | placebo FDR-survive | placebo PBO |",
              "|---|--:|--:|--:|"]
        for m, p in pl.items():
            L.append(f"| {m} | {p['n_candidates']} | {p['fdr_survive']} | {_fmt(p.get('pbo'), 3)} |")
    L += ["", "## Candidate shortlist", ""]
    any_cand = False
    for m, r in markets.items():
        for c in r["candidates"]:
            any_cand = True
            tag = " ⚠️ FRAGILE" if c.get("fragile") else ""
            L.append(f"- **{c['name']}**{tag} ({c['n']} games) — ROI {_fmt(c['roi_net_vig'])} net "
                     f"of vig, mean edge {_fmt(c['mean_edge'], 3)}, books {c['book_groups']}, "
                     f"PBO<0.2 {c['grid_pbo_lt_0p2']}, DSR≥0.95 {c['grid_dsr_ge_0p95']}")
    if not any_cand:
        L.append("**None.** No derivative cleared the deflated, GAME-level, FDR-corrected "
                 "beat-the-close bar → with E5.4 + E13.13 this closes the derivative-edge hope on "
                 "the historical closes. Value = product-quality calibration + transparency, not a "
                 "cashable derivative edge. Forward CLV on the E2.0b live stream can still re-open "
                 "this via the same harness if a prospective signal appears.")
    L += ["", "_Generated by `eval_derivative_model_gate.py` (E2.6). Every config is logged in "
          f"`{_out_paths(suffix='')[2].name}` (no cherry-pick). Market data used at the eval/CLV "
          "layer ONLY (market-blind model)._"]
    return "\n".join(L)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Smoke (synthetic; proves the pipeline end-to-end with NO S3)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def make_smoke_frame(n_games: int = 900, seed: int = 7, *, edge_strength: float = 0.0) -> pd.DataFrame:
    """Synthetic per-quote frame. `edge_strength=0` → the book prices the TRUE convolved probability
    (efficient → expected CLEAN NULL). `edge_strength>0` → the book's line is shaded so the model's
    (true) probability systematically beats the close → the gate should FIRE a candidate. Realized
    runs are drawn from the SAME per-side NegBin the model prices, so the model is correct by
    construction and the ONLY thing that moves the verdict is the book's (mis)pricing."""
    from scipy.stats import nbinom

    from betting_ml.utils.totals_distribution import draw_independent_samples
    r_home, r_away = 4.0645, 3.3977
    rng = np.random.default_rng(seed)
    books = ["pinnacle", "draftkings", "fanduel", "betmgm", "bovada"]

    # Draw every game's per-side μ + realized runs vectorised, then the convolved total ONCE/game
    # (so the true alt-line probability is computed from a single shared draw, not per book).
    seasons = rng.choice([2023, 2024, 2025, 2026], size=n_games)
    months = rng.integers(4, 10, size=n_games)
    days = rng.integers(1, 28, size=n_games)
    mu_home = rng.uniform(3.6, 5.6, size=n_games)
    mu_away = rng.uniform(3.4, 5.2, size=n_games)
    fh = nbinom.rvs(r_home, r_home / (r_home + mu_home), random_state=rng)
    fa = nbinom.rvs(r_away, r_away / (r_away + mu_away), random_state=rng)
    yh, ya = draw_independent_samples(mu_home, mu_away, r_home, rng, r_away=r_away, n_draws=8000)
    total_samples = yh + ya                                   # (n_games, 8000)

    def _american(p, vig):
        io = float(np.clip(p + vig / 2, 1e-3, 1 - 1e-3))
        return int(round(-100 * io / (1 - io))) if io >= 0.5 else int(round(100 * (1 - io) / io))

    rows = []
    for gp in range(n_games):
        gd = f"{int(seasons[gp])}-{int(months[gp]):02d}-{int(days[gp]):02d}"
        base = dict(game_pk=gp, season=int(seasons[gp]), game_date=gd,
                    mu_home=float(mu_home[gp]), mu_away=float(mu_away[gp]), is_oos=True,
                    final_home=int(fh[gp]), final_away=int(fa[gp]),
                    home_team=f"H{gp % 30}", away_team=f"A{(gp + 7) % 30}")
        gmu = mu_home[gp] + mu_away[gp]
        low_line, high_line = float(np.floor(gmu) - 0.5), float(np.floor(gmu) + 1.5)
        alt_true = {ln: float((total_samples[gp] > ln).mean()) for ln in (low_line, high_line)}
        team_specs = (("home", float(mu_home[gp]), r_home), ("away", float(mu_away[gp]), r_away))
        for bk in books:
            vig = 0.04 if bk == "pinnacle" else float(rng.uniform(0.05, 0.09))
            for ln in (low_line, high_line):
                # Concentrate the mispricing in ONE corner (the HIGH alt line) so a distinct config
                # wins in- AND out-of-sample (low PBO) — a uniform shade ties the whole field
                # (the high-PBO-over-a-tie effect). Every other cell stays efficient.
                shade = edge_strength if ln == high_line else 0.0
                pb = float(np.clip(alt_true[ln] - shade, 1e-3, 1 - 1e-3))
                rows.append({**base, "market": dg.ALT_TOTALS, "bookmaker_key": bk, "line": ln,
                             "team_side": None, "outcome_desc": None,
                             "over_price": _american(pb, vig), "under_price": _american(1 - pb, vig)})
            for side, mu, r in team_specs:                    # team totals stay efficient
                ln = float(np.floor(mu) + 0.5)
                p_true = float(nbinom.sf(int(np.floor(ln)), r, r / (r + mu)))
                rows.append({**base, "market": dg.TEAM_TOTALS, "bookmaker_key": bk, "line": ln,
                             "team_side": side, "outcome_desc": base[f"{side}_team"],
                             "over_price": _american(p_true, vig),
                             "under_price": _american(1 - p_true, vig)})
    df = pd.DataFrame(rows)
    df.attrs["r_home"], df.attrs["r_away"] = r_home, r_away
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E2.6 derivative model-vs-market gate (angle 3)")
    ap.add_argument("--smoke", action="store_true", help="synthetic end-to-end run (no S3)")
    ap.add_argument("--smoke-mispriced", action="store_true",
                    help="synthetic run with a shaded book → the gate should FIRE a candidate")
    ap.add_argument("--build-cache", action="store_true", help="read S3 → cache parquet (operator)")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--seasons", default="2023,2024,2025,2026")
    ap.add_argument("--n-draws", type=int, default=dg.DEFAULT_N_DRAWS)
    args = ap.parse_args(argv)

    if args.smoke or args.smoke_mispriced:
        strength = 0.10 if args.smoke_mispriced else 0.0
        tag = "_smoke_mispriced" if args.smoke_mispriced else "_smoke"
        print(f"[smoke] synthetic frame (edge_strength={strength}) — "
              f"expected {'CANDIDATE fires' if strength else 'CLEAN NULL'}")
        run_eval(make_smoke_frame(edge_strength=strength), suffix=tag, synthetic=True,
                 n_draws=min(args.n_draws, 4000))
        return 0

    seasons = [int(s) for s in args.seasons.split(",")]
    if args.build_cache or args.rebuild_cache or not CACHE.exists():
        if not (args.build_cache or args.rebuild_cache) and not CACHE.exists():
            print(f"[error] no cache at {CACHE}; run --build-cache (operator, >1-min S3).",
                  file=sys.stderr)
            return 2
        frame = build_cache(seasons)
    else:
        frame = pd.read_parquet(CACHE)
        print(f"[cache] loaded {len(frame):,} rows from {CACHE}")
    run_eval(frame, n_draws=args.n_draws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
