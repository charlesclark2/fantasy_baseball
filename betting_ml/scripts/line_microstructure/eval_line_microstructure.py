#!/usr/bin/env python3
"""eval_line_microstructure.py — Edge Program Story E13.16: line-movement microstructure.

THE NEW MECHANISM (different from every prior program null): E5.4 / E13.13 / E13.14 / E13.8 all asked
"is the PRICE right?" → efficient (PBO≈0.5). This asks "does the price's own MOVEMENT reveal
structure?" — treat each game's odds line first-posted → first-pitch as a PRICE TIME-SERIES and test
whether a trajectory signal lets us BEAT THE CLOSE (CLV, the gold-standard skill measure). CLV is a
price-vs-price quantity (no realized outcome needed) → the PRIMARY gate.

SCOPE = pure cached-data analysis, NO predictive model (an eval/harness story per guide §0.5). The
pre-registration (`ablation_results/e13_16_preregistration.md`) fixes the signals, anchors,
thresholds, segments, and deflation BEFORE any close/outcome was joined.

⚠️ HONEST DATA CONSTRAINT: fine 30-min trajectories exist only for 2026+ (`mart_odds_outcomes`
live); 2021–2025 is coarse (~3 snaps/day, thin coverage). ⇒ this is a FORWARD-ACCRUING study — the
historical run is SUGGESTIVE; the real verdict is prospective forward-CLV on the accruing captures.
The operator MAY thicken the historical leg by backfilling `/odds` snapshots scoped to `h2h`+`totals`
(the harness consumes a thicker cache transparently). Weather (H4) / public-% (H5) are forward-only
(from 2026-07-01) → pre-registered + engine-ready, DEFERRED (logged, never silently dropped).

DATA (§0.5 — cached S3 via DuckDB, NO Snowflake; one read → parquet). NOT `stg_parlayapi_*` (decommissioned):
  * odds trajectory (h2h + totals, curated US books)  ← mart_odds_outcomes (_history + _current)
  * event_id → game_pk + commence_time                ← mart_game_odds_bridge
  * realized total + winner (SECONDARY ROI only)      ← stg_batter_pitches (W1–W3 stable)

RUN ORDER:
  uv run python betting_ml/scripts/line_microstructure/eval_line_microstructure.py --smoke        # synthetic, no S3
  uv run python betting_ml/scripts/line_microstructure/eval_line_microstructure.py --build-cache   # operator, >1-min S3 scan
  uv run python betting_ml/scripts/line_microstructure/eval_line_microstructure.py                 # eval cached snapshots → dossier
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils import line_microstructure as lm
from betting_ml.utils.derivative_eval import devig_pair
from betting_ml.utils.overfitting import DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE

# ── Paths ─────────────────────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[3]
CACHE = _REPO / "betting_ml" / "data" / "cache" / "e13_16_snapshots.parquet"
DOSSIER_DIR = _REPO / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"

# curated US books (williamhill_us folded to caesars); the trajectory is read for these only.
_CACHE_BOOKS = ["pinnacle", "betmgm", "caesars", "williamhill_us", "fanduel", "draftkings",
                "fanatics", "bovada"]
SNAP_COLS = ["game_pk", "season", "game_date", "ym", "book", "market", "snapshot_ts",
             "hours_to_commence", "line", "fair_over", "fair_home", "over_price", "under_price",
             "home_price", "away_price", "realized_total", "home_won"]


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Heavy S3 read → cached parquet (operator-run; §0.5 one-read-then-cache)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_cache(seasons: list[int], start_date: str | None, *,
                with_live: bool = False, with_results: bool = False) -> pd.DataFrame:
    """Assemble the per-snapshot trajectory frame from cached S3 parquet via DuckDB → parquet.

    DEFAULT reads ONE source — `odds_snapshots_historical` (the dense multi-snapshot backfill;
    per-snapshot prices + game_pk; already covers 2021–2026). That alone gives the full CLV analysis
    (the gate). Two heavier reads are OPT-IN because laptop→S3 is slow (~2-3 min/read):
      * `--with-live`    → also union the live 30-min `mart_odds_outcomes` (freshest 2026; forward leg).
      * `--with-results` → also read game-level `mart_game_results` for the SECONDARY realized-ROI
                           cross-check (NOT the gate; game-level, no pitch scan).
    One row per (game_pk × book × market × snapshot_ts), de-vigged, leakage-guarded (snapshot < commence)."""
    import time
    from scripts.utils.lakehouse_read import LAKEHOUSE, duck_connect  # heavy/S3 — lazy import

    def _step(label):
        print(f"[cache] {label} ...", flush=True)
        return time.monotonic()

    def _done(t0):
        print(f"[cache]   done in {time.monotonic() - t0:.0f}s", flush=True)

    con = duck_connect()
    season_list = ",".join(str(s) for s in seasons)

    t0 = _step("reading historical trajectory (odds_snapshots_historical + leakage guard)")
    hist = _read_historical_snaps(con, LAKEHOUSE, season_list)
    print(f"[cache]   hist snapshots: {0 if hist is None else len(hist):,}", flush=True); _done(t0)

    if with_live:
        t0 = _step("reading live trajectory (mart_odds_outcomes) — --with-live")
        live = _read_live_snaps(con, LAKEHOUSE, season_list)
        print(f"[cache]   live snapshots: {0 if live is None else len(live):,}", flush=True); _done(t0)
    else:
        print("[cache] skipping live mart_odds_outcomes (pass --with-live to include the freshest "
              "2026 30-min captures; odds_snapshots_historical already covers 2021–2026)", flush=True)
        live = None

    if with_results:
        # SECONDARY-only realized outcomes — game-level (tiny), best-effort. Never blocks the CLV gate.
        t0 = _step("reading game results for the secondary realized-ROI cross-check (mart_game_results)")
        settled = _read_game_results(con, LAKEHOUSE, season_list)
        print(f"[cache]   games with a final score: {0 if settled is None else len(settled):,}",
              flush=True); _done(t0)
    else:
        print("[cache] skipping mart_game_results (pass --with-results for the secondary realized-ROI "
              "cross-check; the gate is CLV, which needs no outcome)", flush=True)
        settled = None
    con.close()

    parts = [p for p in (hist, live) if p is not None and not p.empty]
    if not parts:
        raise SystemExit("[error] no trajectory rows from odds_snapshots_historical or "
                         "mart_odds_outcomes — check the S3 sources / seasons / backfill.")
    t0 = _step("assembling + de-vigging the snapshot frame (local)")
    raw = pd.concat(parts, ignore_index=True)
    # de-dup: the backfill (source_rank 0) wins over the live mart (1) on an identical snapshot key.
    raw = (raw.sort_values("source_rank")
              .drop_duplicates(["game_pk", "book", "market", "snapshot_ts"], keep="first"))
    raw["book"] = raw["book"].replace({"williamhill_us": "caesars"})
    raw["season"] = pd.to_datetime(raw["game_date"]).dt.year
    raw["ym"] = pd.to_datetime(raw["game_date"]).dt.strftime("%Y-%m")

    # de-vig per snapshot → fair_home (h2h) / fair_over (totals); fall back to the stored prob.
    dv = raw.apply(lambda r: _devig_row(r), axis=1, result_type="expand")
    raw["fair_home"], raw["fair_over"] = dv[0], dv[1]

    if settled is not None and not settled.empty:
        raw = raw.merge(settled, on="game_pk", how="left")
        raw["realized_total"] = raw["final_home"] + raw["final_away"]
        raw["home_won"] = np.where(raw[["final_home", "final_away"]].notna().all(axis=1),
                                   (raw["final_home"] > raw["final_away"]).astype(float), np.nan)
    else:                                         # no results source → secondary ROI is NaN (gate is CLV)
        raw["realized_total"] = np.nan
        raw["home_won"] = np.nan
    for c in SNAP_COLS:
        if c not in raw.columns:
            raw[c] = np.nan
    frame = raw[SNAP_COLS].copy()
    _done(t0)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(CACHE, index=False)
    status = {"n_snaps": int(len(frame)), "n_games": int(frame["game_pk"].nunique()),
              "seasons": sorted(frame["season"].dropna().astype(int).unique().tolist()),
              "hist_snaps": int(0 if hist is None else len(hist)),
              "live_snaps": int(0 if live is None else len(live)),
              "fine_2026_games": int(frame[frame["season"] == 2026]["game_pk"].nunique()),
              "median_snaps_per_game_book_mkt": _median_density(frame)}
    CACHE.with_suffix(".status.json").write_text(json.dumps(status, indent=2))
    print(f"[cache] wrote {len(frame):,} snapshot rows ({status['n_games']} games) → {CACHE}")
    print(f"[cache]   seasons={status['seasons']}  hist={status['hist_snaps']:,} "
          f"live={status['live_snaps']:,}  2026-fine-games={status['fine_2026_games']}  "
          f"median snaps/(game,book,mkt)={status['median_snaps_per_game_book_mkt']}")
    return frame


def _read_historical_snaps(con, lakehouse, season_list) -> pd.DataFrame | None:
    """The operator's densified backfill store (`odds_snapshots_historical`) → long per-snapshot rows,
    one per (game_pk × book × market × snapshot_ts). It carries both markets' prices on ONE row, so we
    UNPIVOT to the (game_pk, market) grain.

    ⚠️ LEAKAGE GUARD (load-bearing): this raw store is NOT pre-filtered to pre-game — the Card 7.P2
    date-level snapshot grid captured in-game odds for early games (a 22:00 snap for a 17:00 first
    pitch). We JOIN `stg_statsapi_games` (game_pk → first-pitch `game_date::timestamptz`) and keep
    only `snapshot_ts < commence`, then derive hours_to_commence from the REAL first pitch (so the
    'close' is the last PRE-game snap and CLV is honest). Guarded: missing/empty source → skipped."""
    # restrict to the pre-registered curated book set (the `--bookmaker all` backfill also lands
    # exotic books like onexbet — keep them out of the all/soft book-groups). williamhill_us is in
    # the set (renamed → caesars downstream, matching the live reader).
    books = ",".join(f"'{b}'" for b in _CACHE_BOOKS)
    try:
        raw = con.execute(f"""
            WITH games AS (
                SELECT game_pk, game_date::timestamptz AS commence
                FROM read_parquet('{lakehouse}/stg_statsapi_games/**/*.parquet', union_by_name=true)
                WHERE game_pk IS NOT NULL
            )
            SELECT o.game_pk, o.game_date::date AS game_date, lower(o.bookmaker) AS book,
                   o.snapshot_ts::timestamptz AS snapshot_ts,
                   date_diff('second', o.snapshot_ts::timestamptz, g.commence) / 3600.0
                       AS hours_to_commence,
                   o.home_price, o.away_price, o.over_price, o.under_price,
                   o.total_line, o.home_win_prob
            FROM read_parquet('{lakehouse}/odds_snapshots_historical/**/*.parquet',
                              union_by_name=true) o
            JOIN games g ON g.game_pk = o.game_pk
            WHERE o.game_pk IS NOT NULL AND year(o.game_date::date) IN ({season_list})
              AND lower(o.bookmaker) IN ({books})
              AND o.snapshot_ts::timestamptz < g.commence""").fetchdf()   # LEAKAGE GUARD
    except Exception as exc:                                          # noqa: BLE001 (mirror-tier)
        print(f"[cache] odds_snapshots_historical: SKIPPED — {exc}", file=sys.stderr)
        return None
    if raw.empty:
        return None
    raw["game_pk"] = raw["game_pk"].astype("int64")
    h2h = raw.assign(market="h2h", line=np.nan, over_price=np.nan, under_price=np.nan)
    tot = raw.assign(market="totals", line=raw["total_line"], home_price=np.nan,
                     away_price=np.nan, home_win_prob=np.nan)
    out = pd.concat([h2h, tot], ignore_index=True)
    out["snapshot_ts"] = out["snapshot_ts"].astype(str)
    out["source_rank"] = 0
    return out[["game_pk", "game_date", "book", "market", "snapshot_ts", "hours_to_commence",
                "line", "home_price", "away_price", "over_price", "under_price",
                "home_win_prob", "source_rank"]]


def _read_game_results(con, lakehouse, season_list) -> pd.DataFrame | None:
    """Game-level final scores for the SECONDARY realized-ROI cross-check (NOT the gate). Reads
    `mart_game_results` (one row per game) — a tiny scan vs. the pitch-level table. Best-effort:
    any read failure is logged + swallowed so the CLV gate still runs (mirror-tier)."""
    try:
        df = con.execute(f"""
            SELECT game_pk, home_final_score AS final_home, away_final_score AS final_away
            FROM read_parquet('{lakehouse}/mart_game_results/**/*.parquet', union_by_name=true)
            WHERE game_pk IS NOT NULL AND year(game_date::date) IN ({season_list})""").fetchdf()
    except Exception as exc:                                          # noqa: BLE001 (mirror-tier)
        print(f"[cache] mart_game_results: SKIPPED (secondary ROI → NaN) — {exc}", file=sys.stderr)
        return None
    if df.empty:
        return None
    df["game_pk"] = df["game_pk"].astype("int64")
    return df


def _read_live_snaps(con, lakehouse, season_list) -> pd.DataFrame | None:
    """The live 30-min mart (`mart_odds_outcomes`) → long per-snapshot rows, bridged to game_pk.
    Timestamps are ISO VARCHAR on S3 (W8a) → cast ::timestamp (INC-23). Guarded (mirror-tier)."""
    books = ",".join(f"'{b}'" for b in _CACHE_BOOKS)
    try:
        bridge = con.execute(
            f"SELECT game_pk, odds_api_event_id AS event_id, game_date::date AS game_date "
            f"FROM read_parquet('{lakehouse}/mart_game_odds_bridge/**/*.parquet', union_by_name=true) "
            f"WHERE game_pk IS NOT NULL AND odds_api_event_id IS NOT NULL "
            f"AND year(game_date::date) IN ({season_list})").fetchdf()
        raw = con.execute(f"""
            SELECT event_id, bookmaker_key AS book, market_key AS market,
                   ingestion_ts::timestamp AS snapshot_ts,
                   epoch(commence_time::timestamp) - epoch(ingestion_ts::timestamp) AS secs_to_commence,
                   max(CASE WHEN market_key='h2h' AND is_home_outcome THEN outcome_price_american END) AS home_price,
                   max(CASE WHEN market_key='h2h' AND is_away_outcome THEN outcome_price_american END) AS away_price,
                   max(CASE WHEN market_key='totals' AND lower(outcome_name)='over'  THEN outcome_price_american END) AS over_price,
                   max(CASE WHEN market_key='totals' AND lower(outcome_name)='under' THEN outcome_price_american END) AS under_price,
                   max(CASE WHEN market_key='totals' THEN outcome_point END) AS line
            FROM read_parquet('{lakehouse}/mart_odds_outcomes/**/*.parquet', union_by_name=true)
            WHERE market_key IN ('h2h','totals') AND bookmaker_key IN ({books})
              AND ingestion_ts::timestamp < commence_time::timestamp
              AND year(commence_time::date) IN ({season_list})
            GROUP BY event_id, book, market, snapshot_ts, commence_time""").fetchdf()
    except Exception as exc:                                          # noqa: BLE001 (mirror-tier)
        print(f"[cache] mart_odds_outcomes: SKIPPED — {exc}", file=sys.stderr)
        return None
    if raw.empty:
        return None
    bridge["game_pk"] = bridge["game_pk"].astype("int64")
    raw = raw.merge(bridge, on="event_id", how="inner")
    raw["game_pk"] = raw["game_pk"].astype("int64")
    raw["hours_to_commence"] = raw["secs_to_commence"].astype(float) / 3600.0
    raw["snapshot_ts"] = raw["snapshot_ts"].astype(str)
    raw["source_rank"] = 1
    return raw[["game_pk", "game_date", "book", "market", "snapshot_ts", "hours_to_commence",
                "line", "home_price", "away_price", "over_price", "under_price", "source_rank"]]


def _devig_row(r) -> tuple[float, float]:
    if r["market"] == "h2h":
        d = devig_pair(r.get("home_price"), r.get("away_price"))
        fair = d["fair_a"]
        # historical backfill fallback: a stored home_win_prob when the two-sided prices are absent
        if not np.isfinite(fair) and np.isfinite(r.get("home_win_prob", np.nan)):
            fair = float(r["home_win_prob"])
        return (fair, float("nan"))
    d = devig_pair(r.get("over_price"), r.get("under_price"))
    return (float("nan"), d["fair_a"])


def _median_density(frame: pd.DataFrame) -> float:
    g = frame.groupby(["game_pk", "book", "market"]).size()
    return float(np.median(g)) if len(g) else 0.0


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Smoke (synthetic; proves the engine + the placebo control + detect/reject with NO S3)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def make_smoke_frame(n_games: int = 700, seed: int = 11) -> pd.DataFrame:
    """Synthetic per-snapshot frame. Half the TOTALS games carry a PLANTED reversion: the line
    over-moves UP early (open→t50) then reverts DOWN past the open by close → betting UNDER at t50
    (AGAINST the early up-move = the `reversion` signal) beats the close (positive CLV) consistently
    across seasons → the reversion gate MUST FIRE. The other totals games + ALL h2h games are a
    martingale (random walk) → the close is unbiased given any interior point → every signal (incl.
    the placebo control) nets ~0 CLV → MUST stay null. Proves the engine detects AND rejects."""
    rng = np.random.default_rng(seed)
    books = lm.BOOK_ORDER
    rows: list[dict] = []
    for gp in range(n_games):
        season = int(rng.choice([2024, 2025, 2026]))
        month = int(rng.integers(4, 10))
        gd = f"{season}-{month:02d}-{int(rng.integers(1, 28)):02d}"
        ym = f"{season}-{month:02d}"
        base_total = float(rng.uniform(7.0, 10.0))
        base_phome = float(rng.uniform(0.35, 0.65))
        realized_total = int(rng.poisson(base_total))
        home_won = 1.0 if rng.uniform() < base_phome else 0.0
        planted = (gp % 2 == 0)                       # half the games carry the reversion
        # 5 fine snapshots at T-6h..T-1h
        hours = [6.0, 4.5, 3.0, 1.75, 1.0]
        for book in books:
            # ── totals line path ──────────────────────────────────────────────────────────────
            if planted:
                bump = 0.6 + 0.2 * rng.uniform()      # early UP move ≥ θ=0.5
                revert = bump + 0.5 + 0.3 * rng.uniform()
                lvals = [base_total, base_total + bump, base_total + bump * 0.9,
                         base_total + bump - revert * 0.6, base_total + bump - revert]
            else:
                steps = rng.normal(0, 0.25, size=len(hours) - 1)   # martingale (efficient)
                lvals = base_total + np.concatenate([[0.0], np.cumsum(steps)])
            for h, lv in zip(hours, lvals):
                lv = float(lv) + float(rng.normal(0, 0.03))
                rows.append(_snap(gp, season, gd, ym, book, "totals", h, line=round(lv * 2) / 2,
                                  realized_total=realized_total, home_won=home_won, rng=rng))
            # ── h2h prob path (martingale → efficient) ────────────────────────────────────────
            steps = rng.normal(0, 0.012, size=len(hours) - 1)
            pvals = np.clip(base_phome + np.concatenate([[0.0], np.cumsum(steps)]), 0.05, 0.95)
            for h, pv in zip(hours, pvals):
                rows.append(_snap(gp, season, gd, ym, book, "h2h", h, phome=float(pv),
                                  realized_total=realized_total, home_won=home_won, rng=rng))
    return pd.DataFrame(rows)[SNAP_COLS]


def _snap(gp, season, gd, ym, book, market, hours, *, line=None, phome=None,
          realized_total, home_won, rng) -> dict:
    """One synthetic snapshot row. Prices are ≈fair at the posted value with standard vig (so a
    coherent/efficient bet loses to vig; only a real CLV move — the planted reversion — pays)."""
    ts = pd.Timestamp(f"{gd}T00:00:00Z") + pd.Timedelta(hours=24 - hours)  # ascending in time
    vig = 0.045 if book == "pinnacle" else float(rng.uniform(0.05, 0.09))
    row = {c: np.nan for c in SNAP_COLS}
    row.update({"game_pk": gp, "season": season, "game_date": gd, "ym": ym, "book": book,
                "market": market, "snapshot_ts": ts.isoformat(), "hours_to_commence": float(hours),
                "realized_total": float(realized_total), "home_won": float(home_won)})
    if market == "totals":
        row["line"] = float(line)
        row["fair_over"] = 0.5
        row["over_price"] = _american(0.5 + vig / 2)
        row["under_price"] = _american(0.5 + vig / 2)
    else:
        row["fair_home"] = float(phome)
        row["home_price"] = _american(phome + vig / 2)
        row["away_price"] = _american((1 - phome) + vig / 2)
    return row


def _american(p: float) -> int:
    p = float(np.clip(p, 1e-3, 1 - 1e-3))
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Dossier
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(x, nd=4):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def run_eval(frame: pd.DataFrame, *, suffix: str = "", synthetic: bool = False,
             status: dict | None = None, keep_stale: bool = False) -> dict:
    stale_stats = None
    if not keep_stale:
        n0 = len(frame)
        frame, stale_stats = lm.drop_stale_snaps(frame)
        print(f"[eval] stale-quote filter: dropped {stale_stats['n_stale_dropped']:,} / {n0:,} "
              f"snapshots ({stale_stats['pct_dropped']}%) as off-market vs cross-book consensus",
              flush=True)
    decisions = lm.build_decisions(frame)
    res = lm.evaluate(decisions)
    meta = {"n_snaps": int(len(frame)), "n_games": int(frame["game_pk"].nunique()),
            "n_decisions": int(len(decisions)),
            "seasons": sorted(pd.to_numeric(frame["season"], errors="coerce").dropna()
                              .astype(int).unique().tolist()),
            "stale_filter": ("OFF (--keep-stale)" if keep_stale else stale_stats),
            "status": status or {}}
    write_dossier(meta, res, suffix=suffix, synthetic=synthetic)
    return res


def write_dossier(meta: dict, res: dict, *, suffix: str = "", synthetic: bool = False) -> None:
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    json_out = DOSSIER_DIR / f"e13_16_line_microstructure{suffix}.json"
    md_out = DOSSIER_DIR / f"e13_16_line_microstructure{suffix}.md"
    csv_out = DOSSIER_DIR / f"e13_16_signal_grid_results{suffix}.csv"

    payload = {"synthetic": synthetic, "meta": meta,
               "markets": {mk: {"n_games": mv["n_games"], "deflation": mv["deflation"]}
                           for mk, mv in res["markets"].items()},
               "pooled_fdr": res["pooled_fdr"], "candidates": res["candidates"]}
    json_out.write_text(json.dumps(payload, indent=2, default=str))

    rows = []
    for c in res["all_configs"]:
        rows.append({"signal": c["signal"], "market": c["market"], "book_group": c["book_group"],
                     "bucket": c["bucket"], "theta": c["theta"], "anchor": c["anchor"],
                     "n_games": c["n"], "n_quotes": c["n_quotes"], "clv_mean": c["roi"],
                     "clv_sharpe": c["sharpe"], "clv_p": c.get("roi_p"),
                     "realized_roi": c.get("realized_roi"), "roi_fdr_survive": c.get("roi_fdr_survive"),
                     "season_sign_consistent": c["season_sign_consistent"], "is_control": c["is_control"]})
    pd.DataFrame(rows).to_csv(csv_out, index=False)
    md_out.write_text(_render_md(meta, res, synthetic=synthetic))
    print(f"[dossier] {md_out.name} · {json_out.name} · {csv_out.name} → {DOSSIER_DIR}")
    print(f"[verdict] {res['candidates']['verdict']}")


def _render_md(meta: dict, res: dict, *, synthetic: bool = False) -> str:
    cand = res["candidates"]
    banner = (["> ⚠️ **SYNTHETIC SMOKE OUTPUT** — generated by `--smoke` on fabricated data (half the "
               "totals games carry a PLANTED reversion that MUST fire; the rest + all h2h are a "
               "martingale that MUST stay null, incl. the placebo control) to prove the engine + the "
               "honest math + the control end-to-end. NOT the real evaluation.", ""]
              if synthetic else [])
    L = banner + [
        "# E13.16 — Line-Movement Microstructure (odds-as-a-price-series)", "",
        f"**Verdict: {cand['verdict']}**", "",
        "The FRESHEST remaining mechanism: every prior probe asked *is the price right?* (efficient); "
        "this asks *does the price's own MOVEMENT reveal structure?* — can a trajectory signal BEAT "
        "THE CLOSE (CLV, the gold-standard skill measure)? CLV needs no realized outcome → it is the "
        "PRIMARY gate. Pre-registration: `e13_16_preregistration.md`. **Honest bar:** GAME-level "
        "collapse before any t-test/DSR/PBO; FORCED side from the trajectory only; CLV net of vig; "
        "per-market deflation (PBO<0.2 + DSR≥0.95 + BH-FDR) over every signal × segment × θ × anchor; "
        "a `placebo` negative control that must NOT survive.", "",
        "## ⚠️ Honest data constraint (the verdict's own limits)", "",
        "Fine 30-min trajectories exist only for **2026+** (`mart_odds_outcomes` live, ~2.5 mo as of "
        "2026-07-04); 2021–2025 is coarse (~3 snaps/day, thin coverage). **This is a FORWARD-ACCRUING "
        "study** — the historical run is SUGGESTIVE; the real verdict is prospective forward-CLV on "
        "the accruing captures. The operator may thicken the historical leg by backfilling `/odds` "
        "snapshots scoped to `h2h`+`totals` (the harness consumes a thicker cache with no code change).",
        "", "## Coverage", "",
        f"- {meta.get('n_snaps', 0):,} snapshots · {meta.get('n_games', 0):,} games · "
        f"{meta.get('n_decisions', 0):,} forced-side decisions · seasons {meta.get('seasons')}"]
    st = meta.get("status") or {}
    if st:
        L.append(f"- fine 2026 games: {st.get('fine_2026_games', '—')} · median snaps/(game,book,mkt): "
                 f"{st.get('median_snaps_per_game_book_mkt', '—')}")
    sf = meta.get("stale_filter")
    if isinstance(sf, dict):
        L.append(f"- **Stale-quote filter (adversarial control) ON:** dropped "
                 f"{sf.get('n_stale_dropped', 0):,} / {sf.get('n_in', 0):,} snapshots "
                 f"({sf.get('pct_dropped', 0)}%) that deviated > {sf.get('totals_tol')} runs "
                 f"(totals) / {sf.get('h2h_tol')} prob (h2h) from the same-hour cross-book "
                 f"consensus (≥{sf.get('min_books')} books) — the control for the stale-quote artifact.")
    elif sf:
        L.append(f"- Stale-quote filter: **{sf}** — off-market book quotes are NOT removed.")
    L += ["", "## Signals tested (every one logged — the pre-registered grid)", "",
          "| signal | market(s) | prior | control? |", "|---|---|---|:--:|"]
    for sig, m in lm.SIGNALS.items():
        L.append(f"| `{sig}` | {m['market']} | {m['prior']} | {'✓' if m['is_control'] else ''} |")

    L += ["", "## ✅ Method check — the `placebo` NEGATIVE CONTROL", ""]
    if cand["control_breaks"]:
        L.append("- **❌ FAILED.** The placebo (side = game_pk parity, trajectory-independent) produced "
                 "a surviving candidate — the harness manufactures CLV where none exists. Investigate.")
    else:
        L.append("- **✅ CONSISTENT.** The placebo produced NO surviving candidate — the harness does "
                 "not manufacture CLV from a trajectory-independent side. The engine is trustworthy.")

    L += ["", "## Per-market deflation (anti-data-mining)", "",
          "| market | games | selectable configs | PBO (<0.2) | DSR (≥0.95) | best config | best CLV |",
          "|---|--:|--:|--:|--:|---|--:|"]
    for mk, mv in res["markets"].items():
        d = mv["deflation"]
        L.append(f"| {mk} | {mv['n_games']} | {d.get('n_selectable', 0)} | "
                 f"{_fmt(d['pbo'].get('pbo'), 3)} | {_fmt(d['dsr'].get('dsr'), 3)} | "
                 f"`{d['dsr'].get('best_config', '—')}` | {_fmt(d['dsr'].get('best_roi'))} |")
    pf = res["pooled_fdr"]
    L.append(f"\n- pooled BH-FDR (q={pf['q']}) across BOTH markets: "
             f"**{pf['n_survive']}/{pf['n_tested']}** configs survive")

    L += ["", "## Top configs by mean CLV (game-level, beat-the-close; net of vig)", "",
          "| signal | market | book | bucket | θ | anchor | games | CLV | sharpe | FDR | ctrl |",
          "|---|---|---|---|--:|---|--:|--:|--:|:--:|:--:|"]
    allc = [c for c in res["all_configs"] if c["n"] >= lm.MIN_GAMES]
    for c in sorted(allc, key=lambda c: -c["roi"])[:25]:
        L.append(f"| {c['signal']} | {c['market']} | {c['book_group']} | {c['bucket']} | {c['theta']} "
                 f"| {c['anchor']} | {c['n']} | {_fmt(c['roi'])} | {_fmt(c['sharpe'], 2)} | "
                 f"{'✓' if c.get('roi_fdr_survive') else '·'} | {'C' if c['is_control'] else ''} |")

    L += ["", "## Candidate shortlist (forward-CLV targets — NOT declared edges)", ""]
    if cand["candidates"]:
        for c in cand["candidates"]:
            tag = " ⚠️ FRAGILE" if c.get("fragile") else ""
            L.append(f"- **{c['name']}**{tag} ({c['n']} games, book-groups {c['book_groups']}) — mean "
                     f"CLV {_fmt(c['clv_mean'])}, clv_p {_fmt(c.get('clv_p'))}, realized-ROI "
                     f"{_fmt(c.get('realized_roi'))}, per-season {c['per_season_clv']}")
        L += ["", "### ⚠️ Honest reading (a candidate ≠ a declared edge)",
              "- The verdict is **not live cashability**. Each candidate is a target for the "
              "**forward-CLV leg** (E2.6): confirm beat-the-close prospectively on the accruing 30-min "
              "captures at PBO<0.2/DSR>0. The historical trajectory is granularity-limited, so a "
              "historical survivor is a hypothesis to confirm forward, never a live green light."]
    else:
        L.append("**None.** No signal cleared the deflated, GAME-level, multiple-comparison-corrected "
                 "CLV bar → **the line trajectory is efficient too**. With E5.4 / E13.13 / E13.14 this "
                 "closes the price-movement angle (pending forward accrual): the OPEN is not "
                 "systematically beatable, over-moves do not reliably revert, and steam does not "
                 "persist enough to beat the close net of vig. Value = product-quality calibration + "
                 "transparency + fantasy, not a cashable CLV-timing edge.")

    L += ["", "## H4 / H5 — deferred, engine-ready (forward-only data)", "",
          "- **H4 weather → total (lag):** `weather_intraday_series` (hourly, per game_pk; temp / wind "
          "speed+direction / humidity; outdoor parks) is S3-only from 2026-07-01 → pre-registered + "
          "aligned to the totals trajectory the moment the prefix has depth. LOGGED, never dropped.",
          "- **H5 public-% → line (reverse line movement):** `public_betting_intraday_series` (hourly; "
          "ML + totals money%/ticket%; FanDuel book 15; game_pk via the ActionNetwork crosswalk) is "
          "S3-only from 2026-07-01 → pre-registered + engine-ready, DEFERRED to forward accrual.", "",
          "## Forward-CLV accrual plan (the REAL test)", "",
          "1. The 30-min `odds_capture` already writes `mart_odds_outcomes` → the fine trajectory "
          "accrues automatically; re-run `--build-cache` + this eval weekly.",
          "2. A signal is CONFIRMED only when it clears PBO<0.2 / DSR≥0.95 / FDR on the PROSPECTIVE "
          "captures (≥ a full season of fine games), not the granularity-limited historical run.",
          "3. Enable the W11-C / W11-D hourly schedules (`W11_RAW_WRITE_MODE=s3|both`) to start "
          "accruing the H4/H5 series; assemble them once each has depth.",
          "", "_Generated by `eval_line_microstructure.py` (E13.16). Configs scored GAME-level "
          "(correlated book-quotes collapsed per game). Every signal × segment × θ × anchor config is "
          "logged in `e13_16_signal_grid_results.csv` (no cherry-pick). Gate constants: PBO<"
          f"{PBO_SHADOW_TO_LIVE}, DSR≥{DSR_CONFIDENCE}._"]
    return "\n".join(L)


# ════════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E13.16 line-movement microstructure eval")
    ap.add_argument("--smoke", action="store_true", help="synthetic end-to-end run (no S3)")
    ap.add_argument("--build-cache", action="store_true", help="read S3 → cache parquet (operator)")
    ap.add_argument("--rebuild-cache", action="store_true", help="force cache rebuild")
    ap.add_argument("--seasons", default="2024,2025,2026")
    ap.add_argument("--start-date", default=None, help="(reserved; settle is game-level now)")
    ap.add_argument("--with-live", action="store_true",
                    help="also union the live 30-min mart_odds_outcomes (slow S3 read; freshest 2026)")
    ap.add_argument("--with-results", action="store_true",
                    help="also read mart_game_results for the SECONDARY realized-ROI (slow; not the gate)")
    ap.add_argument("--keep-stale", action="store_true",
                    help="DISABLE the cross-book stale-quote filter (default ON; --keep-stale reproduces "
                         "the un-controlled run to compare)")
    args = ap.parse_args(argv)

    if args.smoke:
        print("[smoke] synthetic frame — half the totals games carry a PLANTED reversion (must FIRE); "
              "the rest + all h2h are a martingale (must stay NULL, incl. the placebo control)")
        run_eval(make_smoke_frame(), suffix="_smoke", synthetic=True, keep_stale=args.keep_stale)
        return 0

    seasons = [int(s) for s in args.seasons.split(",")]
    status = None
    if args.build_cache or args.rebuild_cache or not CACHE.exists():
        if not (args.build_cache or args.rebuild_cache) and not CACHE.exists():
            print(f"[error] no cache at {CACHE}; run with --build-cache (operator, >1-min S3 scan).",
                  file=sys.stderr)
            return 2
        frame = build_cache(seasons, args.start_date,
                            with_live=args.with_live, with_results=args.with_results)
    else:
        frame = pd.read_parquet(CACHE)
        print(f"[cache] loaded {len(frame):,} snapshot rows from {CACHE}")
    sf = CACHE.with_suffix(".status.json")
    if sf.exists():
        status = json.loads(sf.read_text())
    run_eval(frame, status=status, keep_stale=args.keep_stale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
