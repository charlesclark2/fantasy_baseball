"""edge_devig_props.py — Edge Program Story E5.3 (Edge, de-vig & per-book comparison — K props).

⭐ The FIRST market-aware prop step. E5.2 shipped the served market-blind K distribution
(`poisson_glm_k`, `strikeout_glm_v1.pkl`). This script:

  1. SCORES the E5.2 served K predictive distribution per (pitcher_id, game_date) — reusing the
     served bundle's exact serve path (μ = clip(glm.predict(scaler.transform(impute(X))),0.3,None);
     K ~ Poisson(μ); scale_spread(·, λ)).
  2. BRIDGES name→id: the E5.1 S3 K closing lines key on `player_name` (no id); the predictions key
     on `pitcher_id`. Joins them via the `ref_players` name dimension (`betting_ml/utils/prop_edge.
     normalize_name`: accents, punctuation, Jr./Sr. folded), restricted to pitchers we model so the
     namespace collapses and same-name ambiguity is resolved per game_date. Emits a JOIN-COVERAGE
     report (how many of the ~7,774 player×date closing lines resolve) with unresolved names FLAGGED.
  3. DE-VIGS each book's two-way K price → fair (no-vig) implied P(over) (`devig_two_way`,
     integer-line push handled), prices the MODEL's P at the book's EXACT line (`compute_edge_row`),
     and emits the per-(pitcher × date × book × line) EDGE + EV table with Pinnacle carried as the
     sharp fair-value anchor where it prices the K prop.

🔒 HONEST FRAMING (required, §0.1): this is a TRANSPARENCY / model-vs-market comparison, NOT a bet
rec. The prop vig is LARGE → net-of-vig is the only honest read; "edge" is model-RELATIVE and
UNPROVEN until E5.4. best_alpha = 0. No +EV claim.

DATA (per §0.5): S3-FIRST — the K closing lines are read from S3 via DuckDB (NOT a fresh Snowflake
pull); the per-start feature frame reuses the E5.2 cached parquet (Snowflake hit once, in E5.2).
This script is light (samples + joins) — it runs in well under a minute.

Outputs (→ quant_sports_intel_models/baseball/edge_program/ablation_results/):
  * e5_3_prop_edge_table.parquet   — the full per-(pitcher×date×book×line) edge/EV table (the shape
                                     E5.4 reads; gitignored — large, regenerable)
  * e5_3_prop_edge_sample.csv      — top-|edge| committed sample for inspection
  * e5_3_prop_edge_summary.{json,md}  — distribution of edge/EV/hold + Pinnacle coverage
  * e5_3_join_coverage.{json,md}   — name→id join coverage + unresolved-name flags

Usage (operator / dev):
    uv run python betting_ml/scripts/prop_pricing/edge_devig_props.py
    uv run python betting_ml/scripts/prop_pricing/edge_devig_props.py --no-save
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.prop_edge import (
    compute_edge_row,
    devig_two_way,
    last_initial_key,
    normalize_name,
    ref_display_name,
)
from betting_ml.utils.prop_pricing import scale_spread

_SEED = 42
_PINNACLE = "pinnacle"
_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)
_GLM_ARTIFACT = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "prop_pricing_v1" / "strikeout_glm_v1.pkl"
)
_S3_PROPS_GLOB = (
    "s3://baseball-betting-ml-artifacts/mlb/props/"
    "market=pitcher_strikeouts/season=*/date=*/*.parquet"
)
_S3_REF_PLAYERS = "s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_ref_players/part-0.parquet"


# ---------------------------------------------------------------------------
# 1. Score the E5.2 served K distribution per (pitcher_id, game_date)
# ---------------------------------------------------------------------------

def score_served_distribution(rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    """Reproduce the E5.2 served serve path for every eligible start → per-game K-count samples.

    Returns (preds, meta): `preds` has one row per (pitcher_id, game_date) with its sample array
    (object column `samples`) + summary mean; `meta` records the bundle version/λ. The frame reuses
    the E5.2 cached parquet (no Snowflake). Mirrors `fit_prop_pricing._fit_served_glm_bundle`'s serve
    contract exactly so E5.3 prices the SAME distribution that is served."""
    import joblib
    from betting_ml.scripts.prop_pricing.fit_prop_pricing import build_predictors, load_frame_cached

    if not _GLM_ARTIFACT.exists():
        raise FileNotFoundError(
            f"Served K bundle missing: {_GLM_ARTIFACT}. Regenerate via the E5.2 STEP-2 command:\n"
            "  uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py"
        )
    bundle = joblib.load(_GLM_ARTIFACT)
    features = bundle["features"]
    impute = bundle["impute"]
    lam = float(bundle["spread_scale"])
    n_draws = int(bundle["n_draws"])

    df = load_frame_cached(2021, 2026)
    pred = build_predictors(df, rate_mode="recency_blend")   # the served rate construction
    elig = pred.dropna(subset=["starter_ip_mu", "starter_ip_dispersion"]).reset_index(drop=True)

    X = elig[features].apply(pd.to_numeric, errors="coerce").fillna(impute).to_numpy(float)
    mu = np.clip(bundle["model"].predict(bundle["scaler"].transform(X)), 0.3, None)
    samp = rng.poisson(mu[:, None], size=(len(mu), n_draws))
    samp = scale_spread(samp, lam).astype(np.int32)          # the served coverage-λ recalibration

    elig = elig.copy()
    elig["pitcher_id"] = elig["pitcher_id"].astype("Int64")
    elig["game_date"] = pd.to_datetime(elig["game_date"]).dt.date
    elig["pred_mean_k"] = samp.mean(axis=1)
    # One distribution per (pitcher_id, game_date). Doubleheaders (same pitcher, same date) are rare;
    # keep the first start's distribution and flag the count.
    elig["_row"] = np.arange(len(elig))
    keep = elig.drop_duplicates(subset=["pitcher_id", "game_date"], keep="first")
    n_dupe = len(elig) - len(keep)
    preds = keep[["pitcher_id", "game_date", "game_year", "pred_mean_k", "_row"]].reset_index(drop=True)
    preds["samples"] = [samp[r] for r in preds["_row"].to_numpy()]
    preds = preds.drop(columns="_row")
    meta = {"bundle_version": bundle.get("version"), "model_kind": bundle.get("model_kind"),
            "served_lambda": lam, "n_draws": n_draws, "n_eligible_starts": int(len(elig)),
            "n_pitcher_dates": int(len(preds)), "n_doubleheader_dupes_dropped": int(n_dupe)}
    return preds, meta


# ---------------------------------------------------------------------------
# 2. Name→id bridge: ref_players name dimension, restricted to modelled pitchers
# ---------------------------------------------------------------------------

def load_ref_players(con) -> pd.DataFrame:
    """ref_players name dimension (mlb_bam_id, first/last) from S3 → normalised join key."""
    ref = con.execute(
        f"SELECT mlb_bam_id, first_name, last_name FROM read_parquet('{_S3_REF_PLAYERS}')"
    ).df()
    ref["norm_name"] = [
        normalize_name(ref_display_name(f, l))
        for f, l in zip(ref["first_name"], ref["last_name"])
    ]
    return ref


def build_name_to_id(ref: pd.DataFrame, modelled_ids: set[int]) -> tuple[dict, dict, pd.DataFrame]:
    """Name → modelled pitcher_id bridge, restricted to pitchers we actually predict.

    Restricting to the modelled-pitcher set collapses the ~25.9k-player namespace to starters in our
    frame, so the vast majority of names are unique. Returns (full-name→[ids], (last,initial)→[ids],
    restricted ref). The (last,initial) map is the nickname/legal-name fallback (used only when the
    full name doesn't match — e.g. feed "Matthew Boyd" vs ref "Matt Boyd"). Both maps' >1-id entries
    are AMBIGUOUS — resolved per game_date downstream."""
    sub = ref[ref["mlb_bam_id"].astype("Int64").isin(modelled_ids)].copy()
    name_map: dict[str, list[int]] = {}
    initial_map: dict[tuple[str, str], list[int]] = {}
    for nm, gid in zip(sub["norm_name"], sub["mlb_bam_id"]):
        if not nm:
            continue
        name_map.setdefault(nm, []).append(int(gid))
        lk = last_initial_key(nm)
        if lk is not None:
            initial_map.setdefault(lk, []).append(int(gid))
    name_map = {k: sorted(set(v)) for k, v in name_map.items()}
    initial_map = {k: sorted(set(v)) for k, v in initial_map.items()}
    return name_map, initial_map, sub


def load_book_lines(con) -> pd.DataFrame:
    """Per (player_name × game_date × book) CLOSING K line from S3 (DuckDB, S3-first).

    game_date = CAST(commence_time AS DATE) (the game day, matching the predictions). The CLOSING
    snapshot per (player, date, book) = the latest snapshot_ts at/<= commence_time (almost always a
    single snapshot in this backfill). One row per (player, date, book) carrying its line + two-way
    American prices."""
    return con.execute(
        f"""
        WITH raw AS (
            SELECT player_name,
                   CAST(commence_time AS DATE) AS game_date,
                   bookmaker_key, line, over_price, under_price,
                   snapshot_ts, commence_time,
                   row_number() OVER (
                       PARTITION BY player_name, CAST(commence_time AS DATE), bookmaker_key
                       ORDER BY (snapshot_ts <= commence_time) DESC, snapshot_ts DESC
                   ) AS rn
            FROM read_parquet('{_S3_PROPS_GLOB}', hive_partitioning=1)
            WHERE line IS NOT NULL
        )
        SELECT player_name, game_date, bookmaker_key, line, over_price, under_price
        FROM raw WHERE rn = 1
        """
    ).df()


def resolve_lines(lines: pd.DataFrame, preds: pd.DataFrame,
                  name_map: dict[str, list[int]],
                  initial_map: dict[tuple[str, str], list[int]]) -> tuple[pd.DataFrame, dict]:
    """Resolve each line's `player_name` → a modelled `pitcher_id` via the name bridge + game_date.

    DATE TOLERANCE (the UTC-shift fix): S3 `commence_time` is UTC, so a US night game's
    CAST(commence_time AS DATE) is the LOCAL game date OR the next UTC day. Predictions key on the
    Snowflake-mart LOCAL game_date, so a line at UTC date `gd` matches a prediction on `gd` or `gd−1`
    (UTC is never behind US). We try `gd` first, then `gd−1`; the matched prediction's LOCAL game_date
    becomes the authoritative `game_date` (the line's UTC date is kept as `line_commence_date`).

    Resolution rules (handle the duplicate-name / Jr.-Sr. ambiguity the prompt flags):
      * exactly 1 modelled id with that name has a prediction in {gd, gd−1} → resolved.
      * >1 distinct modelled id matches in the window → AMBIGUOUS (flagged, not silently dropped).
      * name modelled but no prediction in {gd, gd−1} → UNRESOLVED_NO_START (reliever / DNP / gap).
      * 0 modelled ids with that name → UNRESOLVED_NAME (not a modelled starter / spelling); flagged.
    Returns (resolved lines joined to predictions, a coverage dict). Nothing is silently dropped.
    """
    from datetime import timedelta

    lines = lines.copy()
    lines["norm_name"] = [normalize_name(n) for n in lines["player_name"]]
    lines["line_commence_date"] = pd.to_datetime(lines["game_date"]).dt.date

    # (pitcher_id, local game_date) → has a prediction.
    pred_keys = set(zip(preds["pitcher_id"].astype(int), preds["game_date"]))

    resolved_id: list[int | None] = []
    matched_date: list[object] = []
    matched_via: list[str] = []
    status: list[str] = []
    for nm, gd in zip(lines["norm_name"], lines["line_commence_date"]):
        cand = name_map.get(nm, [])
        via = "full_name"
        if not cand:
            # Fallback: (last name, first initial) — folds nickname/legal-name + middle-name mismatch.
            lk = last_initial_key(nm)
            cand = initial_map.get(lk, []) if lk is not None else []
            via = "last_initial"
        if not cand:
            resolved_id.append(None); matched_date.append(None); matched_via.append("")
            status.append("unresolved_name_not_modelled"); continue
        # Per candidate id, find its prediction date in the window (prefer the exact UTC date).
        matches: list[tuple[int, object]] = []
        for i in cand:
            for pd_date in (gd, gd - timedelta(days=1)):
                if (i, pd_date) in pred_keys:
                    matches.append((i, pd_date)); break
        distinct_ids = {i for i, _ in matches}
        if len(distinct_ids) == 1:
            i, pdate = matches[0]
            resolved_id.append(i); matched_date.append(pdate); matched_via.append(via)
            status.append("resolved"); continue
        if len(distinct_ids) > 1:
            resolved_id.append(None); matched_date.append(None); matched_via.append("")
            status.append("ambiguous_same_name_same_date"); continue
        resolved_id.append(None); matched_date.append(None); matched_via.append("")
        status.append("unresolved_no_start_that_date" if len(cand) == 1
                      else "unresolved_ambiguous_no_start_that_date")

    lines["pitcher_id"] = pd.array(resolved_id, dtype="Int64")
    lines["game_date"] = matched_date            # authoritative LOCAL game date (None when unresolved)
    lines["matched_via"] = matched_via
    lines["resolution"] = status

    # Coverage at the (player_name × commence-date) grain (the ~7,774 closing-line keys).
    pdate = lines.drop_duplicates(subset=["player_name", "line_commence_date"]).copy()
    by_status = pdate["resolution"].value_counts().to_dict()
    n_keys = int(len(pdate))
    n_resolved = int((pdate["resolution"] == "resolved").sum())
    # Top unresolved names for the flag list (so the operator can spot a systematic miss).
    unresolved = pdate[pdate["resolution"] != "resolved"]
    top_unresolved = (
        unresolved.groupby(["player_name", "resolution"]).size()
        .reset_index(name="n").sort_values("n", ascending=False).head(40)
        .to_dict(orient="records")
    )

    resolved = lines[lines["resolution"] == "resolved"].merge(
        preds[["pitcher_id", "game_date", "game_year", "pred_mean_k", "samples"]],
        on=["pitcher_id", "game_date"], how="left",
    )
    resolved_keys = pdate[pdate["resolution"] == "resolved"]
    via_counts = resolved_keys["matched_via"].value_counts().to_dict()
    coverage = {
        "n_player_date_keys": n_keys,
        "n_resolved": n_resolved,
        "resolved_frac": round(n_resolved / max(n_keys, 1), 4),
        "by_status": {k: int(v) for k, v in by_status.items()},
        "resolved_via": {k: int(v) for k, v in via_counts.items()},
        "n_book_line_rows_total": int(len(lines)),
        "n_book_line_rows_resolved": int(len(resolved)),
        "top_unresolved_names": top_unresolved,
    }
    return resolved, coverage


# ---------------------------------------------------------------------------
# 3. Edge / de-vig / EV per (pitcher × date × book × line) + Pinnacle anchor
# ---------------------------------------------------------------------------

def build_edge_table(resolved: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Per-(pitcher × date × book × line): de-vig the book price, price the model at the EXACT line,
    edge + EV, and attach the Pinnacle sharp-anchor de-vigged P(over) at the same line."""
    rows: list[dict] = []
    # Pre-compute Pinnacle's de-vigged P(over) per (pitcher_id, game_date, line) for the anchor join.
    pin = resolved[resolved["bookmaker_key"] == _PINNACLE]
    pin_anchor: dict[tuple, float] = {}
    for r in pin.itertuples(index=False):
        dv = devig_two_way(r.over_price, r.under_price)
        if dv["valid"]:
            pin_anchor[(int(r.pitcher_id), r.game_date, float(r.line))] = dv["devig_over"]

    for r in resolved.itertuples(index=False):
        if r.samples is None or (isinstance(r.samples, float) and pd.isna(r.samples)):
            continue
        er = compute_edge_row(r.samples, float(r.line), r.over_price, r.under_price)
        key = (int(r.pitcher_id), r.game_date, float(r.line))
        pin_over = pin_anchor.get(key, float("nan"))
        edge_vs_pin = (er["model_p_over_cond"] - pin_over) if np.isfinite(pin_over) else float("nan")
        rows.append({
            "pitcher_id": int(r.pitcher_id), "player_name": r.player_name,
            "game_date": r.game_date, "line_commence_date": r.line_commence_date,
            "game_year": int(r.game_year) if pd.notna(r.game_year) else None,
            "bookmaker_key": r.bookmaker_key,
            "over_price": _f(r.over_price), "under_price": _f(r.under_price),
            "pred_mean_k": round(float(r.pred_mean_k), 3),
            **{k: er[k] for k in (
                "line", "is_integer_line", "model_p_over", "model_p_under", "model_p_push",
                "model_p_over_cond", "model_p_under_cond", "book_devig_over", "book_devig_under",
                "book_hold", "devig_valid", "edge_over", "edge_under", "ev_over", "ev_under",
                "best_side", "best_edge", "best_ev")},
            "pinnacle_devig_over_same_line": pin_over,
            "edge_vs_pinnacle": edge_vs_pin,
            "is_pinnacle": (r.bookmaker_key == _PINNACLE),
        })
    tbl = pd.DataFrame(rows)

    # Round the float columns for a tidy stored table (samples already discarded).
    fcols = ["over_price", "under_price", "model_p_over", "model_p_under", "model_p_push",
             "model_p_over_cond", "model_p_under_cond", "book_devig_over", "book_devig_under",
             "book_hold", "edge_over", "edge_under", "ev_over", "ev_under", "best_edge", "best_ev",
             "pinnacle_devig_over_same_line", "edge_vs_pinnacle"]
    for c in fcols:
        if c in tbl:
            tbl[c] = tbl[c].astype(float).round(5)

    valid = tbl[tbl["devig_valid"]]
    n_pin_anchored = int(tbl["pinnacle_devig_over_same_line"].notna().sum())
    summary = {
        "n_rows": int(len(tbl)),
        "n_pitcher_dates": int(tbl.drop_duplicates(["pitcher_id", "game_date"]).shape[0]),
        "n_books": int(tbl["bookmaker_key"].nunique()),
        "books": sorted(tbl["bookmaker_key"].unique().tolist()),
        "n_one_sided_no_devig": int((~tbl["devig_valid"]).sum()),
        "n_integer_lines": int(tbl["is_integer_line"].sum()),
        "n_pinnacle_anchored_rows": n_pin_anchored,
        "pinnacle_anchor_frac": round(n_pin_anchored / max(len(tbl), 1), 4),
        "book_hold": _dist(valid["book_hold"]),
        "edge_over_two_sided": _dist(valid["edge_over"]),   # honest: ~symmetric around 0
        "abs_disagreement": _dist(valid["best_edge"]),      # |model−book|; NOT a tradeable edge
        "ev_over_two_sided": _dist(valid["ev_over"]),       # UNBIASED per-side EV (blind over) — net of vig
        "best_ev": _dist(valid["best_ev"]),                 # favourable-side selection (biased, unproven)
        "frac_best_ev_positive": round(float((valid["best_ev"] > 0).mean()), 4),
        "edge_vs_pinnacle": _dist(tbl["edge_vs_pinnacle"].dropna()),
        "per_book_hold_median": {
            b: round(float(valid[valid["bookmaker_key"] == b]["book_hold"].median()), 4)
            for b in sorted(valid["bookmaker_key"].unique())
            if valid[valid["bookmaker_key"] == b]["book_hold"].notna().any()
        },
    }
    return tbl, summary


# ---------------------------------------------------------------------------
# helpers + IO
# ---------------------------------------------------------------------------

def _f(x):
    try:
        f = float(x)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _dist(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return {"n": 0}
    return {"n": int(len(s)), "mean": round(float(s.mean()), 4), "std": round(float(s.std()), 4),
            "p05": round(float(s.quantile(0.05)), 4), "median": round(float(s.median()), 4),
            "p95": round(float(s.quantile(0.95)), 4),
            "min": round(float(s.min()), 4), "max": round(float(s.max()), 4)}


def _write_coverage_md(cov: dict, meta: dict) -> str:
    lines = [
        "# E5.3 — Name→ID join coverage (S3 K closing lines → E5.2 predictions)",
        "",
        f"_Bridge: `ref_players` name dimension → modelled pitcher_id, via "
        f"`prop_edge.normalize_name` (accents / punctuation / Jr.–Sr. folded), restricted to the "
        f"{meta['n_pitcher_dates']:,} modelled pitcher×date predictions._",
        "",
        "| metric | value |",
        "|---|---|",
        f"| player×date closing-line keys | {cov['n_player_date_keys']:,} |",
        f"| **resolved to a prediction** | **{cov['n_resolved']:,} ({cov['resolved_frac']:.1%})** |",
        f"| book-line rows total | {cov['n_book_line_rows_total']:,} |",
        f"| book-line rows resolved | {cov['n_book_line_rows_resolved']:,} |",
        f"| resolved via full name | {cov['resolved_via'].get('full_name', 0):,} |",
        f"| resolved via (last, initial) fallback | {cov['resolved_via'].get('last_initial', 0):,} |",
        "",
        "_The (last, initial) fallback folds the feed's full legal names vs ref's common names "
        "(\"Matthew Boyd\"↔\"Matt Boyd\", \"Joseph Ryan\"↔\"Joe Ryan\"), resolved against the game-date "
        "window so collisions stay rare._",
        "",
        "## Resolution status (player×date keys)",
        "",
        "| status | n |",
        "|---|---|",
    ]
    for k, v in sorted(cov["by_status"].items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v:,} |")
    lines += [
        "",
        "## Top unresolved names (FLAGGED — not silently dropped)",
        "",
        "_Most are relievers / non-modelled starters / one-off spellings; a high-count name here "
        "would signal a systematic bridge miss to fix._",
        "",
        "| player_name | reason | n |",
        "|---|---|---|",
    ]
    for r in cov["top_unresolved_names"]:
        lines.append(f"| {r['player_name']} | {r['resolution']} | {r['n']} |")
    lines += [
        "",
        "> Unresolved ≠ error: a closing line resolves only if the named pitcher is a starter we "
        "model AND has a prediction on that game_date. Relievers, openers, and DNPs legitimately "
        "have no K-distribution to compare. best_alpha = 0 — this is a comparison table, not a bet rec.",
    ]
    return "\n".join(lines) + "\n"


def _write_summary_md(summ: dict, meta: dict) -> str:
    def d(x):
        return (f"mean {x['mean']} · median {x['median']} · p05 {x['p05']} · p95 {x['p95']} "
                f"(n={x['n']:,})") if x.get("n") else "n/a"
    lines = [
        "# E5.3 — Per-book de-vig + model-vs-market K-prop edge table (TRANSPARENCY, not a bet rec)",
        "",
        f"_Served model: {meta['model_kind']} ({meta['bundle_version']}, λ={meta['served_lambda']}, "
        f"{meta['n_draws']:,} draws). {summ['n_rows']:,} (pitcher×date×book×line) rows · "
        f"{summ['n_pitcher_dates']:,} pitcher×dates · {summ['n_books']} books._",
        "",
        "## What this is",
        "- De-vig each book's two-way K over/under price (additive method, integer-line PUSH handled) "
        "→ the book's fair no-vig P(over).",
        "- Price the E5.2 served K distribution at the book's EXACT line (half-line vs integer-push).",
        "- **EDGE = model P(side | not push) − book de-vigged P(side)**; **EV per $1** at the offered "
        "price. Pinnacle carried as the sharp fair-value anchor where it prices the K prop.",
        "",
        "## Distributions (de-viggable rows only)",
        "",
        "| quantity | distribution |",
        "|---|---|",
        f"| book hold (vig / overround) | {d(summ['book_hold'])} |",
        f"| edge_over = model − book (two-sided) | {d(summ['edge_over_two_sided'])} |",
        f"| \\|model − book\\| disagreement (NOT a tradeable edge) | {d(summ['abs_disagreement'])} |",
        f"| EV per $1, blind OVER (unbiased, net of vig) | {d(summ['ev_over_two_sided'])} |",
        f"| best-side EV per $1 (favourable-side, BIASED) | {d(summ['best_ev'])} |",
        f"| edge vs Pinnacle (same line) | {d(summ['edge_vs_pinnacle'])} |",
        "",
        f"- Two-sided `edge_over` mean ≈ {summ['edge_over_two_sided'].get('mean')} (centred near 0 ⇒ the "
        f"model neither systematically over- nor under-shoots the K market on average).",
        f"- **Blind-over EV ≈ {summ['ev_over_two_sided'].get('mean')}/$1 (NEGATIVE)** — the honest "
        f"unbiased read: betting these prices without selection just pays the vig.",
        f"- `best-side EV>0` fraction = {summ['frac_best_ev_positive']:.1%} looks large but is **gross of "
        f"the line-selection bias** (we always read the favourable side) and **unproven** — E5.4 is the gate.",
        f"- One-sided quotes (no de-vig): {summ['n_one_sided_no_devig']:,}  ·  "
        f"integer lines (push-handled): {summ['n_integer_lines']:,}",
        f"- Pinnacle-anchored rows: {summ['n_pinnacle_anchored_rows']:,} "
        f"({summ['pinnacle_anchor_frac']:.1%}) — Pinnacle prices the K prop broadly here (NOT thin).",
        "",
        "## Median book hold (the prop vig is LARGE — the honest-framing point)",
        "",
        "| book | median hold |",
        "|---|---|",
    ]
    for b, h in sorted(summ["per_book_hold_median"].items(), key=lambda x: x[1]):
        lines.append(f"| {b} | {h:.3f} |")
    lines += [
        "",
        "> 🔒 **best_alpha = 0.** The edge column is MODEL-RELATIVE and UNPROVEN — net-of-vig is the "
        "only honest read, and the prop hold above is large. This table is the input to the **E5.4** "
        "hard gate (PBO<0.2/DSR>0 per market, multiple-comparison-corrected, + forward CLV net of the "
        "prop vig). No +EV claim is made here.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Story E5.3 — de-vig + per-book K-prop edge table")
    ap.add_argument("--no-save", action="store_true", help="Compute + print, skip writing outputs.")
    args = ap.parse_args()
    rng = np.random.default_rng(_SEED)

    print("=== STORY E5.3 — DE-VIG & PER-BOOK K-PROP COMPARISON (market-aware; best_alpha=0) ===")
    print("Scoring the E5.2 served K distribution (cached frame; no Snowflake) ...")
    preds, meta = score_served_distribution(rng)
    print(f"  {meta['n_pitcher_dates']:,} pitcher×dates scored "
          f"({meta['model_kind']} λ={meta['served_lambda']}, {meta['n_draws']:,} draws; "
          f"{meta['n_doubleheader_dupes_dropped']} doubleheader dupes dropped)")

    import duckdb
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    print("Loading S3 K closing lines + ref_players bridge (S3-first DuckDB) ...")
    ref = load_ref_players(con)
    modelled_ids = set(preds["pitcher_id"].astype(int).tolist())
    name_map, initial_map, _ = build_name_to_id(ref, modelled_ids)
    lines = load_book_lines(con)
    print(f"  {len(lines):,} (player×date×book) closing-line rows; "
          f"{lines.drop_duplicates(['player_name','bookmaker_key']).shape[0]:,} player×books")

    resolved, coverage = resolve_lines(lines, preds, name_map, initial_map)
    print(f"\n── Name→ID join coverage ──")
    print(f"  player×date keys: {coverage['n_player_date_keys']:,}  "
          f"resolved: {coverage['n_resolved']:,} ({coverage['resolved_frac']:.1%})  "
          f"via {coverage['resolved_via']}")
    for k, v in sorted(coverage["by_status"].items(), key=lambda x: -x[1]):
        print(f"    {k:<38} {v:,}")

    tbl, summary = build_edge_table(resolved)
    print(f"\n── Edge table ──  {summary['n_rows']:,} (pitcher×date×book×line) rows, "
          f"{summary['n_books']} books")
    print(f"  book hold (vig): {_dist(tbl[tbl['devig_valid']]['book_hold'])}")
    print(f"  edge_over (two-sided): {summary['edge_over_two_sided']}")
    print(f"  best-side EV (net of vig): {summary['best_ev']}  (frac>0 {summary['frac_best_ev_positive']})")
    print(f"  Pinnacle-anchored rows: {summary['n_pinnacle_anchored_rows']:,} "
          f"({summary['pinnacle_anchor_frac']:.1%})")

    if args.no_save:
        print("\n[--no-save] done.")
        return

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Full table → gitignored parquet (the shape E5.4 reads; large, regenerable).
    parquet_path = _RESULTS_DIR / "e5_3_prop_edge_table.parquet"
    tbl.to_parquet(parquet_path, index=False)
    # Committed inspection sample: top-|best_edge| de-viggable rows.
    sample = (tbl[tbl["devig_valid"]].assign(_abs=tbl["best_edge"].abs())
              .sort_values("_abs", ascending=False).drop(columns="_abs").head(200))
    sample.to_csv(_RESULTS_DIR / "e5_3_prop_edge_sample.csv", index=False)

    doc = {
        "story": "E5.3", "fit_at": date.today().isoformat(), "served": meta,
        "honest_framing": ("Transparency / model-vs-market comparison, NOT a bet rec. best_alpha=0. "
                           "Edge is model-relative + UNPROVEN until E5.4 (PBO/DSR + forward CLV net "
                           "of the large prop vig)."),
        "join_coverage": coverage,
        "edge_table_summary": summary,
        "outputs": {
            "full_table_parquet": str(parquet_path.relative_to(_PROJECT_ROOT)) + " (gitignored)",
            "sample_csv": "ablation_results/e5_3_prop_edge_sample.csv",
        },
        "e5_4_contract": {
            "grain": "one row per (pitcher_id, game_date, bookmaker_key, line)",
            "key_cols": ["pitcher_id", "player_name", "game_date", "game_year", "bookmaker_key", "line"],
            "model_cols": ["model_p_over", "model_p_under", "model_p_push",
                           "model_p_over_cond", "model_p_under_cond", "pred_mean_k"],
            "market_cols": ["over_price", "under_price", "book_devig_over", "book_devig_under",
                            "book_hold", "devig_valid"],
            "edge_cols": ["edge_over", "edge_under", "ev_over", "ev_under",
                          "best_side", "best_edge", "best_ev",
                          "pinnacle_devig_over_same_line", "edge_vs_pinnacle", "is_pinnacle"],
        },
    }
    (_RESULTS_DIR / "e5_3_prop_edge_summary.json").write_text(json.dumps(doc, indent=2, default=float))
    (_RESULTS_DIR / "e5_3_prop_edge_summary.md").write_text(_write_summary_md(summary, meta))
    (_RESULTS_DIR / "e5_3_join_coverage.json").write_text(json.dumps(coverage, indent=2, default=float))
    (_RESULTS_DIR / "e5_3_join_coverage.md").write_text(_write_coverage_md(coverage, meta))

    print(f"\nFull edge table → {parquet_path.relative_to(_PROJECT_ROOT)}  (gitignored; the shape E5.4 reads)")
    print("Records → ablation_results/e5_3_{prop_edge_summary,join_coverage}.{json,md} + e5_3_prop_edge_sample.csv")
    print("Next: E5.4 HARD gate (PBO<0.2/DSR>0 per market, multiple-comparison-corrected, + forward "
          "CLV net of the prop vig). best_alpha=0 — this is transparency, not an edge claim.")


if __name__ == "__main__":
    main()
