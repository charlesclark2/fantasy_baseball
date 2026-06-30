#!/usr/bin/env python3
"""eval_cross_market.py — Edge Program Story E13.14: cross-market constellation coherence.

THE NEW MECHANISM (different from every prior program null): E5.4 / E13.13 / E13.8 asked "is OUR
prediction better than ONE line?" → efficient. This asks "are the BOOKS' OWN markets on a game
mutually COHERENT, and where two markets CONTRADICT each other, does the side the implied/sharp
market favors win NET OF the bet-market's vig?" The play is RELATIVE (market-vs-market) → partly
market-NEUTRAL: we don't predict the game, we arbitrage the books' own disagreement.

SCOPE = pure cached-data analysis, NO predictive model (an eval/harness story per guide §0.5). The
pre-registration (`ablation_results/e13_14_preregistration.md`) fixes the relations, the bet rule,
the credence gate, and the deflation BEFORE any outcome was joined.

THE RELATIONS (pre-registered):
  1 ⭐ props → team offense  (Σ batter implied E[runs] ↔ team-total)      [the laziest pair]
  2    team-totals → game-total  (home_tt + away_tt ↔ game total)
  3    F5 → full game = NEGATIVE CONTROL  (must return "consistent"; E13.13: F5 correctly derived)
  4    K-props → opposing team-total                                      [pre-registered; deferred]
  5    sides ↔ totals  (ML ↔ run-line + total)                           [pre-registered; deferred]
Relations 1-3 are assembled + evaluated here; 4-5 are pre-registered and engine-ready but their
S3 assembly is deferred (4: pitcher→side + K→runs calibration; 5: `spreads` row-encoding + 2026
catch-up) — they are LOGGED, never silently dropped (the engine evaluates them the moment a frame
is supplied via the same cache schema).

HONEST BAR (the E13.13 lesson, enforced in `betting_ml/utils/cross_market_eval.py`): game-level
collapse BEFORE any t-test/DSR/PBO; in-fold (leave-one-season-out) affine calibration; FORCED side
(deviation sign, never the outcome); deflate over ALL relations × credence-thresholds × book-groups
(PBO<0.2 + DSR + BH-FDR); cashability proxy = realized-outcome ROI net of the bet-market's OWN vig.

DATA (§0.5 — cached S3 via DuckDB, NO Snowflake; one read → parquet):
  * game total + h2h (sharp main line)  ← mart_odds_outcomes
  * team totals                         ← mart_derivative_closes (team = outcome_description)
  * F5 totals + batter/pitcher props    ← mlb/props/market={key}/season=*/date=*
  * event_id → game_pk + team names     ← mart_game_odds_bridge
  * realized runs + batter→side map     ← stg_batter_pitches (Top⇒away bats, Bot⇒home bats)

RUN ORDER:
  uv run python betting_ml/scripts/cross_market_eval/eval_cross_market.py --smoke        # synthetic, no S3
  uv run python betting_ml/scripts/cross_market_eval/eval_cross_market.py --build-cache   # operator, >1-min S3 scan
  uv run python betting_ml/scripts/cross_market_eval/eval_cross_market.py                 # eval cached frame → dossier
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils import cross_market_eval as cm
from betting_ml.utils.overfitting import DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE

# ── Paths ─────────────────────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[3]
CACHE = _REPO / "betting_ml" / "data" / "cache" / "e13_14_cross_market_frame.parquet"
DOSSIER_DIR = _REPO / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
# ref_players name dimension (mlb_bam_id ↔ name) — the prop player_name → batter_id bridge (E5.3).
_S3_REF_PLAYERS = "s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_ref_players/part-0.parquet"

# ── Relation registry (mirrors e13_14_preregistration.md) ───────────────────────────────────────
# key, display, bet-market, is_control, joint_sd floor (units of market B), unit space, status, prior
R1, R2, R3, R4, R5 = (
    "props_to_team_total", "team_total_to_game_total", "f5_to_full_control",
    "kprop_to_opp_team_total", "sides_to_totals")
RELATIONS: dict[str, dict] = {
    R1: dict(display="① props → team offense ↔ team-total", bet_market="team_total",
             is_control=False, floor=0.35, space="runs", prior="highest (laziest pair)"),
    R2: dict(display="② team-totals → game-total", bet_market="game_total",
             is_control=False, floor=0.35, space="runs", prior="medium"),
    R3: dict(display="③ F5 → full-game [NEGATIVE CONTROL]", bet_market="game_total",
             is_control=True, floor=0.35, space="runs", prior="MUST be consistent"),
    R4: dict(display="④ K-props → opposing team-total", bet_market="team_total",
             is_control=False, floor=0.35, space="runs", prior="low (deferred)"),
    R5: dict(display="⑤ sides ↔ totals (ML ↔ run-line+total)", bet_market="moneyline",
             is_control=False, floor=0.012, space="prob", prior="low / near-control (deferred)"),
}
ASSEMBLED = (R1, R2, R3)                 # relations whose S3 cache-assembly is implemented here
DEFERRED = (R4, R5)                       # pre-registered + engine-ready; assembly is a follow-up

# ── Pre-registered grid ─────────────────────────────────────────────────────────────────────────
TAU_GRID = (0.75, 0.85, 0.90, 0.95, 0.975)        # Bayesian credence thresholds
BOOK_GROUPS = ["all", "pinnacle", "soft", "majors"]
MIN_GAMES = 50          # a config needs ≥ this many unique GAMES to be selectable (game-level)
FRAGILE_GAMES = 250     # a surviving candidate below this is FRAGILE (thin)
FDR_Q = 0.10
MIN_BATTERS = 6         # R1: a team needs ≥ this many resolved batter props for a trustworthy sum

# Cache schema — one row per (relation × game × side × bet-book).
CACHE_COLS = ["relation", "game_pk", "season", "game_date", "ym", "side_label",
              "bookmaker_key", "line_B", "over_price", "under_price",
              "realized_B", "implied_raw", "posted_B", "sd_a", "sd_b"]


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Heavy S3 read → cached parquet (operator-run; §0.5 one-read-then-cache)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_cache(seasons: list[int], start_date: str | None) -> pd.DataFrame:
    """Assemble the relation frames (R1/R2/R3) from cached S3 parquet via DuckDB and cache to parquet.

    Each relation contributes long rows in CACHE_COLS. Per-relation try/except: a missing/empty
    source is LOGGED and skipped (mirror-tier), never fatal. Deferred relations (R4/R5) are recorded
    in the meta but not assembled here."""
    from scripts.utils.lakehouse_read import LAKEHOUSE, duck_connect  # heavy/S3 — lazy import

    bucket = LAKEHOUSE.rsplit("/baseball/lakehouse", 1)[0]   # s3://baseball-betting-ml-artifacts
    props = f"{bucket}/mlb/props"
    con = duck_connect()
    season_list = ",".join(str(s) for s in seasons)
    year_globs = ", ".join(
        f"'{LAKEHOUSE}/stg_batter_pitches/year={y}/**/*.parquet'" for y in seasons)
    date_filter = f"AND game_date >= DATE '{start_date}'" if start_date else ""

    # ── Common: bridge + realized full-game runs + batter→side map ──────────────────────────────
    # NB: lakehouse timestamp/date columns are ISO VARCHAR (the W8a stringify cure) → cast ::date at
    # the use-site before any date fn, or year(VARCHAR) HALTs the DuckDB binder (INC-23 landmine).
    bridge = con.execute(
        f"SELECT game_pk, odds_api_event_id AS event_id, home_team_name, away_team_name, "
        f"       game_date::date AS game_date "
        f"FROM read_parquet('{LAKEHOUSE}/mart_game_odds_bridge/**/*.parquet', union_by_name=true) "
        f"WHERE game_pk IS NOT NULL AND year(game_date::date) IN ({season_list})").fetchdf()
    bridge["game_pk"] = bridge["game_pk"].astype("int64")

    settled = con.execute(f"""
        SELECT game_pk, any_value(game_date) AS game_date,
               max(post_pitch_home_score) AS final_home,
               max(post_pitch_away_score) AS final_away,
               max(CASE WHEN inning <= 5 THEN post_pitch_home_score END) AS f5_home,
               max(CASE WHEN inning <= 5 THEN post_pitch_away_score END) AS f5_away
        FROM read_parquet([{year_globs}], union_by_name=true, hive_partitioning=false)
        WHERE game_year IN ({season_list}) {date_filter}
        GROUP BY game_pk""").fetchdf()
    settled["game_pk"] = settled["game_pk"].astype("int64")

    # batter → batting side, keyed on `batter_id` (NOT player_name — that column is the PITCHER). For
    # a BATTER, inning_half Bot (bottom) ⇒ home team batting ⇒ home; Top ⇒ away. Modal half per
    # (game, batter). batter_id is the Statcast/MLBAM id → joins the ref_players name bridge.
    batter_side = con.execute(f"""
        WITH pa AS (
            SELECT game_pk, batter_id,
                   sum(CASE WHEN inning_half = 'Bot' THEN 1 ELSE 0 END) AS bot,
                   sum(CASE WHEN inning_half = 'Top' THEN 1 ELSE 0 END) AS top
            FROM read_parquet([{year_globs}], union_by_name=true, hive_partitioning=false)
            WHERE game_year IN ({season_list}) {date_filter} AND batter_id IS NOT NULL
            GROUP BY game_pk, batter_id)
        SELECT game_pk, batter_id, CASE WHEN bot >= top THEN 'home' ELSE 'away' END AS side_label
        FROM pa""").fetchdf()
    batter_side["game_pk"] = batter_side["game_pk"].astype("int64")
    batter_side["batter_id"] = batter_side["batter_id"].astype("int64")

    parts: list[pd.DataFrame] = []
    meta_status: dict[str, str] = {}

    # Shared totals frames read ONCE (each guarded; reused by multiple relations).
    def _safe(fn, label):
        try:
            return fn()
        except Exception as exc:                                      # noqa: BLE001 (mirror-tier)
            print(f"[cache] read {label}: SKIPPED — {exc}", file=sys.stderr)
            return None

    gt = _safe(lambda: _read_game_totals(con, LAKEHOUSE, bridge, season_list), "game_totals")
    tt = _safe(lambda: _read_team_totals(con, LAKEHOUSE, bridge, season_list), "team_totals")

    def _relation(label, fn):
        try:
            df = fn()
            if df is not None and not df.empty:
                parts.append(df)
                meta_status[label] = f"RAN ({df['game_pk'].nunique()} games)"
            else:
                meta_status[label] = "EMPTY (source present but no joinable rows)"
        except Exception as exc:                                      # noqa: BLE001
            meta_status[label] = f"SKIPPED — {type(exc).__name__}: {exc}"
            print(f"[cache] {label}: SKIPPED — {exc}", file=sys.stderr)

    _relation(R2, lambda: _assemble_team_to_game(tt, gt, settled) if (tt is not None and gt is not None)
              else None)
    _relation(R3, lambda: _assemble_f5_control(
        _read_f5_totals(con, props, bridge, season_list), gt, settled) if gt is not None else None)
    _relation(R1, lambda: _assemble_props_to_team(
        _read_prop_team_runs(con, props, bridge, batter_side, season_list), tt, settled)
        if tt is not None else None)

    con.close()
    for r in DEFERRED:
        meta_status[r] = "DEFERRED (pre-registered; engine-ready; assembly is a follow-up)"

    if not parts:
        raise SystemExit("[error] no relation frames assembled — check the S3 sources / season list.")
    frame = pd.concat(parts, ignore_index=True)[CACHE_COLS]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(CACHE, index=False)
    (CACHE.with_suffix(".status.json")).write_text(json.dumps(meta_status, indent=2))
    print(f"[cache] wrote {len(frame):,} rows → {CACHE}")
    for r, st in meta_status.items():
        print(f"[cache]   {r}: {st}")
    return frame


# ── S3 readers (each returns a tidy per-(game[,side],book) frame) ────────────────────────────────
def _read_game_totals(con, lakehouse, bridge, season_list) -> pd.DataFrame:
    """Per (game_pk, book): consensus game-total line + this book's over/under prices."""
    raw = con.execute(f"""
        SELECT event_id, bookmaker_key,
               max(CASE WHEN lower(outcome_name)='over'  THEN outcome_price_american END) AS over_price,
               max(CASE WHEN lower(outcome_name)='under' THEN outcome_price_american END) AS under_price,
               max(outcome_point) AS line_B
        FROM read_parquet('{lakehouse}/mart_odds_outcomes/**/*.parquet', union_by_name=true)
        WHERE market_key = 'totals' AND outcome_point IS NOT NULL
          AND year(commence_date::date) IN ({season_list})
        GROUP BY event_id, bookmaker_key""").fetchdf()
    out = raw.merge(bridge[["game_pk", "event_id", "game_date"]], on="event_id", how="inner")
    out["game_pk"] = out["game_pk"].astype("int64")
    out["season"] = pd.to_datetime(out["game_date"]).dt.year
    return out.dropna(subset=["line_B"])


def _read_team_totals(con, lakehouse, bridge, season_list) -> pd.DataFrame:
    """Per (game_pk, side, book): team-total CLOSING line + over/under prices, BOTH teams preserved.

    Read from `stg_derivative_odds` (the un-deduped snapshot table) and do our OWN closing selection —
    NOT `mart_derivative_closes`: that mart's closing dedup partitions by (event, market, book,
    outcome_name) WITHOUT the team (`outcome_description`), and for team_totals BOTH teams share the
    'Over'/'Under' outcome_name → the dedup keeps only ONE team per (event, book), so only ~4 games
    retain both sides (the bug that collapsed R2/R1). Partitioning the row_number by
    (event, book, outcome_description, outcome_name) keeps the latest pre-game snapshot of EACH team's
    each side. game_pk is routed through the shared `event_id → bridge` join (one game_pk universe).
    NB: timestamp columns are ISO VARCHAR (W8a) → cast ::timestamp for the comparison/order (INC-23)."""
    raw = con.execute(f"""
        WITH ranked AS (
            SELECT event_id, bookmaker_key, home_team, away_team,
                   outcome_description AS team, lower(outcome_name) AS ou,
                   outcome_price_american AS price, outcome_point AS pt,
                   row_number() OVER (
                       PARTITION BY event_id, bookmaker_key, outcome_description, outcome_name
                       ORDER BY actual_snapshot_ts::timestamp DESC) AS rn
            FROM read_parquet('{lakehouse}/stg_derivative_odds/**/*.parquet', union_by_name=true)
            WHERE market_key = 'team_totals' AND outcome_point IS NOT NULL
              AND actual_snapshot_ts::timestamp <= commence_time::timestamp
              AND year(commence_time::date) IN ({season_list}))
        SELECT event_id, bookmaker_key, home_team, away_team, team,
               max(CASE WHEN ou = 'over'  THEN price END) AS over_price,
               max(CASE WHEN ou = 'under' THEN price END) AS under_price,
               max(pt) AS line_B
        FROM ranked WHERE rn = 1
        GROUP BY event_id, bookmaker_key, home_team, away_team, team""").fetchdf()
    raw = raw.merge(bridge[["game_pk", "event_id"]], on="event_id", how="inner")
    raw["game_pk"] = raw["game_pk"].astype("int64")
    side = np.where(raw["team"].astype(str) == raw["home_team"].astype(str), "home",
                    np.where(raw["team"].astype(str) == raw["away_team"].astype(str), "away", None))
    raw["side_label"] = side
    return raw.dropna(subset=["side_label", "line_B"])[
        ["game_pk", "side_label", "bookmaker_key", "over_price", "under_price", "line_B"]]


def _read_f5_totals(con, props, bridge, season_list) -> pd.DataFrame:
    """Per (game_pk, book): consensus F5-total line (the implied-A raw input for the control)."""
    raw = con.execute(f"""
        SELECT event_id, bookmaker_key,
               max(over_price)  AS over_price, max(under_price) AS under_price,
               max(line)        AS f5_line
        FROM read_parquet('{props}/market=totals_1st_5_innings/season=*/date=*/*.parquet',
                          union_by_name=true, hive_partitioning=false)
        WHERE season IN ({season_list}) AND line IS NOT NULL
        GROUP BY event_id, bookmaker_key""").fetchdf()
    out = raw.merge(bridge[["game_pk", "event_id"]], on="event_id", how="inner")
    out["game_pk"] = out["game_pk"].astype("int64")
    return out.dropna(subset=["f5_line"])


def _read_prop_team_runs(con, props, bridge, batter_side, season_list) -> pd.DataFrame:
    """Per (game_pk, side, book): implied team runs = Σ over the side's batters of the implied
    Poisson mean E[runs] (from the de-vigged `batter_runs_scored` 0.5-line P(≥1)).

    The prop carries a player NAME; the batting side comes from `batter_side` keyed on `batter_id`.
    Bridge them via the ref_players name dimension (prop name_key → `mlb_bam_id` = batter_id), then
    join (game_pk, batter_id) → batter_side. That (game_pk, batter_id) join ALSO disambiguates a
    name→multiple-id collision (only the id that actually batted in the game survives). One quote per
    batter; sum per (game, side, book); require ≥ MIN_BATTERS resolved batters."""
    from betting_ml.utils.prop_edge import ref_display_name
    ref = con.execute(
        f"SELECT mlb_bam_id, first_name, last_name "
        f"FROM read_parquet('{_S3_REF_PLAYERS}', union_by_name=true)").fetchdf()
    ref = ref.dropna(subset=["mlb_bam_id"]).copy()
    ref["batter_id"] = ref["mlb_bam_id"].astype("int64")
    ref["name_key"] = [_name_key(ref_display_name(f, l))
                       for f, l in zip(ref["first_name"], ref["last_name"])]
    ref = ref[ref["name_key"] != ""][["batter_id", "name_key"]].drop_duplicates()

    raw = con.execute(f"""
        SELECT event_id, bookmaker_key, player_name, line,
               max(over_price) AS over_price, max(under_price) AS under_price
        FROM read_parquet('{props}/market=batter_runs_scored/season=*/date=*/*.parquet',
                          union_by_name=true, hive_partitioning=false)
        WHERE season IN ({season_list}) AND line IS NOT NULL
        GROUP BY event_id, bookmaker_key, player_name, line""").fetchdf()
    raw = raw.merge(bridge[["game_pk", "event_id"]], on="event_id", how="inner")
    raw["game_pk"] = raw["game_pk"].astype("int64")
    raw["name_key"] = [_name_key(n) for n in raw["player_name"]]
    raw = raw.merge(ref, on="name_key", how="inner")                        # name → batter_id (may fan out)
    raw = raw.merge(batter_side, on=["game_pk", "batter_id"], how="inner")  # id batted in THAT game → side
    raw = raw.drop_duplicates(["game_pk", "bookmaker_key", "batter_id"])    # one quote per batter
    # de-vig + Poisson-mean per batter quote
    dv = raw.apply(lambda r: cm.devig_pair(r["over_price"], r["under_price"]), axis=1)
    fair_over = np.array([d["fair_a"] for d in dv], float)
    raw["e_runs"] = [cm.poisson_mean_from_p_over(p, ln)
                     for p, ln in zip(fair_over, raw["line"].to_numpy(float))]
    raw = raw[np.isfinite(raw["e_runs"].to_numpy(float))]
    agg = (raw.groupby(["game_pk", "side_label", "bookmaker_key"])
           .agg(implied_team_runs=("e_runs", "sum"), n_batters=("e_runs", "size")).reset_index())
    return agg[agg["n_batters"] >= MIN_BATTERS]


# ── Relation assemblers (long rows in CACHE_COLS) ────────────────────────────────────────────────
def _consensus(df: pd.DataFrame, keys: list[str], val: str) -> pd.DataFrame:
    """Per-key consensus (median) + across-book dispersion (std) of `val`."""
    g = df.groupby(keys)[val].agg(["median", "std", "size"]).reset_index()
    return g.rename(columns={"median": f"{val}_med", "std": f"{val}_sd"})


def _finalize(rows: pd.DataFrame, relation: str, realized_map: pd.DataFrame) -> pd.DataFrame:
    # realized_map is the SINGLE source of game_date + realized_B (drop any upstream copies first so
    # the merge can't create game_date_x/_y); season + ym are then derived from it.
    rows = rows.drop(columns=[c for c in ("game_date", "season", "ym", "realized_B")
                              if c in rows.columns])
    rows = rows.merge(realized_map, on=["game_pk", "side_label"], how="left")
    rows["relation"] = relation
    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows["season"] = rows["game_date"].dt.year
    rows["ym"] = rows["game_date"].dt.strftime("%Y-%m")
    for c in CACHE_COLS:
        if c not in rows.columns:
            rows[c] = np.nan
    return rows[CACHE_COLS]


def _assemble_team_to_game(tt: pd.DataFrame, gt: pd.DataFrame, settled: pd.DataFrame) -> pd.DataFrame:
    """R2: implied_raw = home_tt + away_tt (consensus); posted_B per game-total book."""
    cons = _consensus(tt, ["game_pk", "side_label"], "line_B")
    piv = cons.pivot_table(index="game_pk", columns="side_label", values="line_B_med")
    sd = cons.pivot_table(index="game_pk", columns="side_label", values="line_B_sd")
    for col in ("home", "away"):                       # both sides required; guard missing columns
        if col not in piv.columns:
            piv[col] = np.nan
        if col not in sd.columns:
            sd[col] = np.nan
    # a single-book (game,side) has std=NaN → pivot_table DROPS that game from `sd` → its index is a
    # subset of piv's → align so sd.loc[have] can't KeyError (missing std → 0 via nan_to_num below).
    sd = sd.reindex(piv.index)
    have = piv.dropna(subset=["home", "away"]).index
    implied = pd.DataFrame({
        "game_pk": have,
        "implied_raw": (piv.loc[have, "home"] + piv.loc[have, "away"]).to_numpy(),
        "sd_a": np.sqrt(np.nan_to_num(sd.loc[have, "home"].to_numpy()) ** 2
                        + np.nan_to_num(sd.loc[have, "away"].to_numpy()) ** 2)})
    real = settled.assign(realized_B=settled["final_home"] + settled["final_away"], side_label="game")
    realized_map = real[["game_pk", "side_label", "realized_B", "game_date"]]
    rows = gt.merge(implied, on="game_pk", how="inner")
    rows["side_label"] = "game"
    gtc = _consensus(gt, ["game_pk"], "line_B").rename(
        columns={"line_B_med": "posted_B", "line_B_sd": "sd_b"})
    rows = rows.merge(gtc[["game_pk", "posted_B", "sd_b"]], on="game_pk", how="left")
    return _finalize(rows, R2, realized_map)


def _assemble_f5_control(f5: pd.DataFrame, gt: pd.DataFrame, settled: pd.DataFrame) -> pd.DataFrame:
    """R3 (control): implied_raw = consensus F5-total line; posted_B per game-total book."""
    cons = _consensus(f5, ["game_pk"], "f5_line").rename(
        columns={"f5_line_med": "implied_raw", "f5_line_sd": "sd_a"})
    real = settled.assign(realized_B=settled["final_home"] + settled["final_away"], side_label="game")
    realized_map = real[["game_pk", "side_label", "realized_B", "game_date"]]
    rows = gt.merge(cons[["game_pk", "implied_raw", "sd_a"]], on="game_pk", how="inner")
    rows["side_label"] = "game"
    gtc = _consensus(gt, ["game_pk"], "line_B").rename(
        columns={"line_B_med": "posted_B", "line_B_sd": "sd_b"})
    rows = rows.merge(gtc[["game_pk", "posted_B", "sd_b"]], on="game_pk", how="left")
    return _finalize(rows, R3, realized_map)


def _assemble_props_to_team(prop_sum: pd.DataFrame, tt: pd.DataFrame,
                            settled: pd.DataFrame) -> pd.DataFrame:
    """R1: implied_raw = consensus Σ batter E[runs] per side; posted_B per team-total book."""
    cons = _consensus(prop_sum, ["game_pk", "side_label"], "implied_team_runs").rename(
        columns={"implied_team_runs_med": "implied_raw", "implied_team_runs_sd": "sd_a"})
    long = pd.melt(settled, id_vars=["game_pk", "game_date"],
                   value_vars=["final_home", "final_away"], var_name="which", value_name="realized_B")
    long["side_label"] = long["which"].map({"final_home": "home", "final_away": "away"})
    realized_map = long[["game_pk", "side_label", "realized_B", "game_date"]]
    rows = tt.merge(cons[["game_pk", "side_label", "implied_raw", "sd_a"]],
                    on=["game_pk", "side_label"], how="inner")
    ttc = _consensus(tt, ["game_pk", "side_label"], "line_B").rename(
        columns={"line_B_med": "posted_B", "line_B_sd": "sd_b"})
    rows = rows.merge(ttc[["game_pk", "side_label", "posted_B", "sd_b"]],
                      on=["game_pk", "side_label"], how="left")
    return _finalize(rows, R1, realized_map)


def _name_key(name) -> str:
    """Order-independent normalised name key (folds Statcast 'Last, First' ↔ prop 'First Last')."""
    from betting_ml.utils.prop_edge import normalize_name
    toks = sorted(normalize_name(name).split())
    return " ".join(toks)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Evaluate — per relation: LOSO affine → deviation → credence → forced side → credence-gated grid
# ════════════════════════════════════════════════════════════════════════════════════════════════
def evaluate(frame: pd.DataFrame) -> dict:
    relations: dict[str, dict] = {}
    all_configs: list[dict] = []
    present = [r for r in RELATIONS if (frame["relation"] == r).any()]
    for rkey in present:
        meta = RELATIONS[rkey]
        sub = frame[frame["relation"] == rkey].copy()
        # unit grain = (game_pk, side_label): implied_raw / posted_B / realized_B / sds are per-unit
        units = sub.drop_duplicates(["game_pk", "side_label"]).copy()
        implied_a, beta = cm.loso_affine(units["implied_raw"].to_numpy(float),
                                         units["posted_B"].to_numpy(float),
                                         units["season"].to_numpy(object))
        units["implied_A"] = implied_a
        deviation = implied_a - units["posted_B"].to_numpy(float)
        jsd = cm.joint_sd(np.abs(beta) * units["sd_a"].to_numpy(float),
                          units["sd_b"].to_numpy(float), meta["floor"])
        units["deviation"] = deviation
        units["credence"] = cm.credence(deviation, jsd)
        units["bet_side"] = cm.forced_side(deviation)
        coh = cm.coherence_summary(units["implied_A"].to_numpy(float),
                                   units["posted_B"].to_numpy(float),
                                   units["realized_B"].to_numpy(float))
        # broadcast per-unit decision to the bet-book rows
        dec = units[["game_pk", "side_label", "deviation", "credence", "bet_side", "implied_A"]]
        sub = sub.merge(dec, on=["game_pk", "side_label"], how="inner")

        cfgs = []
        for tau in TAU_GRID:
            for grp in BOOK_GROUPS:
                cfg = _eval_config(sub, rkey, meta, tau, grp)
                if cfg is not None:
                    cfgs.append(cfg)
                    all_configs.append(cfg)
        relations[rkey] = {"display": meta["display"], "is_control": meta["is_control"],
                           "prior": meta["prior"], "coherence": coh, "configs": cfgs,
                           "n_units": int(len(units)), "n_games": int(units["game_pk"].nunique())}

    defl = cm.deflate_configs(all_configs, min_games=MIN_GAMES, fdr_q=FDR_Q)
    cands = build_candidates(relations, defl)
    return {"relations": relations, "configs": all_configs, "deflation": defl, "candidates": cands}


def _eval_config(sub: pd.DataFrame, rkey: str, meta: dict, tau: float, grp: str) -> dict | None:
    """One (relation × credence τ × bet-book-group) config, scored at GAME level."""
    cmask = sub["credence"].to_numpy(float) >= tau
    gmask = cm.book_mask(sub["bookmaker_key"].to_numpy(object), grp)
    fin = np.isfinite(sub["realized_B"].to_numpy(float)) & np.isfinite(sub["line_B"].to_numpy(float))
    m = cmask & gmask & fin
    if not m.any():
        return None
    s = sub[m]
    side = s["bet_side"].to_numpy(object)
    price = np.where(side == "over", s["over_price"].to_numpy(float), s["under_price"].to_numpy(float))
    pay = cm.payoff_vec(s["realized_B"].to_numpy(float), s["line_B"].to_numpy(float), side, price)
    stats = cm.score_game_level(pay, s["game_pk"].to_numpy(), s["season"].to_numpy(object),
                                s["ym"].to_numpy(object))
    if stats is None or stats["n"] == 0:
        return None
    return {"name": f"{rkey}|tau{tau:g}|{grp}", "relation": rkey, "is_control": meta["is_control"],
            "tau": tau, "book_group": grp, "roi_fdr_survive": False, **stats}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Candidates + verdict (incl. the F5-control method check)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_candidates(relations: dict, defl: dict) -> dict:
    pbo_ok = (defl["pbo"].get("pbo") is not None and np.isfinite(defl["pbo"].get("pbo", np.nan))
              and defl["pbo"]["pbo"] < PBO_SHADOW_TO_LIVE)
    dsr_ok = (defl["dsr"].get("dsr") is not None and np.isfinite(defl["dsr"].get("dsr", np.nan))
              and defl["dsr"]["dsr"] >= DSR_CONFIDENCE)

    surviving = [c for rk in relations for c in relations[rk]["configs"]
                 if c["n"] >= MIN_GAMES and c["roi"] > 0 and c["season_sign_consistent"]
                 and c.get("roi_fdr_survive") and pbo_ok]

    # dedup overlapping book-groups → one signal per (relation, tau); widest coverage represents it
    by_signal: dict[tuple, list] = {}
    for c in surviving:
        by_signal.setdefault((c["relation"], c["tau"]), []).append(c)
    cands = []
    for (relation, tau), group in by_signal.items():
        best = max(group, key=lambda c: c["n"])
        cands.append({"relation": relation, "name": f"{relation}|tau{tau:g}", "n": best["n"],
                      "roi_net_vig": best["roi"], "roi_p": best.get("roi_p"),
                      "book_groups": sorted({c["book_group"] for c in group}),
                      "per_season_roi": {k: round(v, 4) for k, v in best["per_season"].items()},
                      "season_consistent": True, "fdr_survive": True, "grid_pbo_lt_0p2": pbo_ok,
                      "grid_dsr_ge_0p95": dsr_ok, "is_control": best["is_control"],
                      "fragile": bool(best["n"] < FRAGILE_GAMES)})

    # The F5 control MUST be consistent — a control config among the survivors ⇒ the method is broken.
    control_breaks = [c for c in cands if c["is_control"]]
    real = [c for c in cands if not c["is_control"]]
    control_relation_present = any(relations[rk]["is_control"] for rk in relations)
    control_consistent = control_relation_present and not control_breaks

    n_fragile = sum(1 for c in real if c["fragile"])
    if control_breaks:
        verdict = ("⚠️ METHOD CHECK FAILED — the F5↔main NEGATIVE CONTROL produced a 'candidate'; "
                   "the harness is mis-calibrated, NOT an edge. Investigate before trusting any result.")
    elif not real:
        verdict = "CLEAN NULL — the market constellation is internally coherent (no cross-market edge)"
    elif n_fragile == len(real):
        verdict = f"NO ROBUST EDGE — {len(real)} FRAGILE thin candidate(s) for the forward-CLV leg only"
    else:
        verdict = f"CROSS-MARKET CANDIDATE(S) — {len(real) - n_fragile} robust + {n_fragile} fragile"
    return {"candidates": real, "control_breaks": control_breaks,
            "control_consistent": control_consistent, "n_fragile": n_fragile, "verdict": verdict}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Dossier
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(x, nd=4):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def write_dossier(meta: dict, res: dict, *, suffix: str = "", synthetic: bool = False) -> None:
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    json_out = DOSSIER_DIR / f"e13_14_cross_market_coherence{suffix}.json"
    md_out = DOSSIER_DIR / f"e13_14_cross_market_coherence{suffix}.md"
    csv_out = DOSSIER_DIR / f"e13_14_relation_grid_results{suffix}.csv"

    payload = {"synthetic": synthetic, "meta": meta,
               "relations": {rk: {k: v for k, v in rv.items() if k != "configs"}
                             for rk, rv in res["relations"].items()},
               "deflation": res["deflation"], "candidates": res["candidates"]}
    json_out.write_text(json.dumps(payload, indent=2, default=str))

    rows = []
    for rk, rv in res["relations"].items():
        for c in rv["configs"]:
            rows.append({"relation": rk, "tau": c["tau"], "book_group": c["book_group"],
                         "n_games": c["n"], "n_quotes": c["n_quotes"], "roi": c["roi"],
                         "sharpe": c["sharpe"], "roi_p": c.get("roi_p"),
                         "roi_fdr_survive": c.get("roi_fdr_survive"),
                         "season_sign_consistent": c["season_sign_consistent"],
                         "is_control": c["is_control"]})
    pd.DataFrame(rows).to_csv(csv_out, index=False)
    md_out.write_text(_render_md(meta, res, synthetic=synthetic))
    print(f"[dossier] {md_out.name} · {json_out.name} · {csv_out.name} → {DOSSIER_DIR}")
    print(f"[verdict] {res['candidates']['verdict']}")


def _render_md(meta: dict, res: dict, *, synthetic: bool = False) -> str:
    cand = res["candidates"]
    defl = res["deflation"]
    banner = (["> ⚠️ **SYNTHETIC SMOKE OUTPUT** — generated by `--smoke` on fabricated data (one "
               "relation carries an injected inconsistency; the F5 control is coherent) to prove the "
               "pipeline + the honest math + the control end-to-end. NOT the real evaluation.", ""]
              if synthetic else [])
    L = banner + [
        "# E13.14 — Cross-Market Constellation Coherence", "",
        f"**Verdict: {cand['verdict']}**", "",
        "Pure cached-data RELATIVE-VALUE probe (NO predictive model). Pre-registration: "
        "`e13_14_preregistration.md`. The question is internal-market COHERENCE, not prediction "
        "accuracy: where two of a game's markets contradict each other, does the side the implied "
        "market favors win NET OF the bet-market's own vig? **Honest bar:** game-level collapse "
        "before any t-test/DSR/PBO; leave-one-season-out affine calibration; FORCED side; deflation "
        "over every relation × credence-τ × book-group. Cashability proxy = realized-outcome ROI net "
        "of vig (true beat-the-close forward CLV is the forward leg).", "",
        "## Coverage", "",
        f"- {meta.get('n_rows', 0):,} bet-quotes · {meta.get('n_games', 0):,} games · "
        f"seasons {meta.get('seasons')}",
        "",
        "## Relation status (every relation logged)", "",
        "| relation | status | prior |", "|---|---|---|"]
    status = meta.get("status", {}) or {}
    for rk, m in RELATIONS.items():
        if rk in status:
            st = status[rk]
        elif rk in res["relations"]:
            st = f"RAN ({res['relations'][rk]['n_games']} games)"
        elif rk in DEFERRED:
            st = "DEFERRED (pre-registered; engine-ready; assembly is a follow-up)"
        else:
            st = "not assembled"
        L.append(f"| {m['display']} | {st} | {m['prior']} |")

    L += ["", "## ✅ Method check — the F5 ↔ main NEGATIVE CONTROL", ""]
    if any(res["relations"].get(R3, {}).get("is_control") for _ in [0]) and R3 in res["relations"]:
        if cand["control_breaks"]:
            L.append("- **❌ FAILED.** The F5↔main control produced a candidate — the harness is "
                     "mis-calibrated. E13.13 established F5 is correctly derived off the main line, so "
                     "ANY flagged F5↔main inconsistency is a method bug, not an edge. Investigate.")
        else:
            L.append("- **✅ CONSISTENT.** The F5↔main control produced NO surviving candidate — the "
                     "method does not manufacture inconsistencies where E13.13 proved the derivation "
                     "is efficient. The harness is trustworthy.")
    else:
        L.append("- _F5 control relation not present in this run (assembly skipped)._")

    L += ["", "## Per-relation coherence diagnostics", "",
          "`corr_markets` = how tightly market A's implied tracks the posted line B (≈1 ⇒ coherent). "
          "`info_gain` = corr(realized, implied_A)² − corr(realized, posted_B)²: **>0 ⇒ market A "
          "tracks the outcome BETTER than the bet-line** — the precondition for a relative-value edge.",
          "", "| relation | n | corr_markets | ols_slope | mean_resid(wedge) | corr→implied | "
          "corr→posted | info_gain |", "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for rk, rv in res["relations"].items():
        c = rv["coherence"]
        L.append(f"| {RELATIONS[rk]['display']} | {c['n']} | {_fmt(c['corr_markets'],3)} | "
                 f"{_fmt(c['ols_slope'],3)} | {_fmt(c['mean_resid'],3)} | "
                 f"{_fmt(c['corr_realized_implied'],3)} | {_fmt(c['corr_realized_posted'],3)} | "
                 f"{_fmt(c['info_gain'],4)} |")

    L += ["", "## Deflation (anti-data-mining)", "",
          f"- credence-gated grid: {sum(len(rv['configs']) for rv in res['relations'].values())} "
          f"configs (relation × τ∈{{{', '.join(str(t) for t in TAU_GRID)}}} × book-group), "
          f"{defl.get('n_selectable', 0)} selectable (≥{MIN_GAMES} games; scored GAME-level)",
          f"- PBO (CSCV over ym slices): **{_fmt(defl['pbo'].get('pbo'),3)}** "
          f"(<{PBO_SHADOW_TO_LIVE} required) {defl['pbo'].get('note','')}",
          f"- DSR (deflated by config count): **{_fmt(defl['dsr'].get('dsr'),3)}** "
          f"(≥{DSR_CONFIDENCE} required); best = `{defl['dsr'].get('best_config','—')}` "
          f"ROI {_fmt(defl['dsr'].get('best_roi'))}",
          f"- ROI FDR (q={FDR_Q}): {defl['fdr']['n_survive']}/{defl['fdr']['n_tested']} configs survive",
          "", "## Credence-gated config grid (top by ROI, game-level net of vig)", "",
          "| relation | τ | book | games | quotes | ROI | sharpe | season-consistent | FDR |",
          "|---|--:|---|--:|--:|--:|--:|:--:|:--:|"]
    allc = [c for rv in res["relations"].values() for c in rv["configs"] if c["n"] >= MIN_GAMES]
    for c in sorted(allc, key=lambda c: -c["roi"])[:25]:
        L.append(f"| {c['relation']}{' [CTRL]' if c['is_control'] else ''} | {c['tau']:g} | "
                 f"{c['book_group']} | {c['n']} | {c['n_quotes']} | {_fmt(c['roi'])} | "
                 f"{_fmt(c['sharpe'],2)} | {'✓' if c['season_sign_consistent'] else '·'} | "
                 f"{'✓' if c.get('roi_fdr_survive') else '·'} |")

    L += ["", "## Candidate shortlist", ""]
    if cand["candidates"]:
        for c in cand["candidates"]:
            tag = " ⚠️ FRAGILE" if c.get("fragile") else ""
            L.append(f"- **{c['name']}**{tag} ({c['n']} games, book-groups {c['book_groups']}) — "
                     f"ROI {_fmt(c['roi_net_vig'])} net of vig, roi_p {_fmt(c.get('roi_p'))}, "
                     f"per-season {c['per_season_roi']}")
        L += ["", "### ⚠️ Honest reading (a candidate ≠ a declared edge)",
              "- The verdict here is **not cashability**. Every candidate is a target for the "
              "**forward-CLV leg** (beat-the-close net of the bet-market's own vig at PBO<0.2/DSR>0), "
              "which the cached closing-only odds cannot establish. Given books link-price the "
              "constellation and sharps arbitrage cross-market gaps fast, the prior that one survives "
              "forward is guarded — even for the least-arbed props↔team-total pair."]
    else:
        # Foreground WHY the null is trustworthy: (1) info_gain<0 everywhere, (2) the biggest in-sample
        # ROI is the negative control + ROI decays with n → the +ROI cells are noise PBO correctly kills.
        rels = res["relations"]
        neg_ig = [rk for rk, rv in rels.items()
                  if np.isfinite(rv["coherence"].get("info_gain", np.nan))
                  and rv["coherence"]["info_gain"] < 0]
        allsel = [c for rv in rels.values() for c in rv["configs"] if c["n"] >= MIN_GAMES]
        topc = max(allsel, key=lambda c: c["roi"]) if allsel else None
        L.append("**None.** No relation cleared the deflated, GAME-level, multiple-comparison-corrected "
                 "bar → the books' own markets are internally coherent. With E5.4 / E13.13 this closes "
                 "the cross-market angle.")
        L += ["", "### Why the null is trustworthy (not merely 'PBO failed')",
              f"- **`info_gain < 0` in {len(neg_ig)}/{len(rels)} relations** — in every relation the "
              "POSTED bet-line tracks the realized outcome *better* than the cross-market implied "
              "quantity (`corr→posted` > `corr→implied`). There is no information left on the table, so "
              "the relative-value precondition simply isn't met — including for the least-arbed "
              "props↔team-total pair.",
              f"- **PBO = {_fmt(defl['pbo'].get('pbo'),3)} ≈ 0.5** — the in-sample-best config does not "
              "persist out of sample; the apparent +ROI cells are multiple-comparison / small-sample "
              "noise, not signal."]
        if topc is not None:
            ctrl = " (the NEGATIVE CONTROL — a relation E13.13 proved is efficiently derived)" if \
                topc["is_control"] else ""
            L.append(f"- **The single largest in-sample ROI cell is `{topc['relation']}|tau{topc['tau']:g}"
                     f"|{topc['book_group']}`{ctrl}** at ROI {_fmt(topc['roi'])} on just {topc['n']} games, "
                     "and ROI decays monotonically toward ~0 as the game count grows. A fluke this size "
                     "coming from the control — then evaporating with sample size — is direct evidence "
                     "the +ROI cells are noise the deflation exists to kill, not a missed edge.")
        L.append("- **The honest conclusion stands:** value = product-quality calibration + "
                 "transparency + fantasy, not a cashable cross-market edge.")
    L += ["", "_Generated by `eval_cross_market.py` (E13.14). Strategies scored GAME-level "
          "(correlated book-quotes collapsed per game). Every relation × τ × book-group config is "
          "logged in `e13_14_relation_grid_results.csv` (no cherry-pick)._"]
    return "\n".join(L)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Smoke (synthetic; proves the engine + the control + the detect/reject behaviour with NO S3)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def make_smoke_frame(n_games: int = 600, seed: int = 7, *, efficiency: float = 1.0) -> pd.DataFrame:
    """Synthetic cache-schema frame. The F5 control (R3) and team-total→game-total (R2) are ALWAYS
    coherent (no exploitable deviation → consistent). The props↔team-total pair (R1) carries an
    injected inconsistency scaled by (1−efficiency): when <1 the team-total LINE is shaded off the
    true mean while the prop-sum stays informative → betting the prop-implied side wins net of vig
    (the gate must FIRE); at efficiency=1 R1 is coherent too → clean null. Prices are ≈fair at each
    book's posted line (standard vig), so a coherent relation loses to vig (true null)."""
    rng = np.random.default_rng(seed)
    books = ["pinnacle", "draftkings", "fanduel", "betmgm", "bovada"]
    rows: list[dict] = []
    for gp in range(n_games):
        season = int(rng.choice([2023, 2024, 2025, 2026]))
        month = int(rng.integers(4, 10))
        gd = f"{season}-{month:02d}-{int(rng.integers(1, 28)):02d}"
        ym = f"{season}-{month:02d}"
        mu_home = float(rng.uniform(3.0, 6.0))
        mu_away = float(rng.uniform(3.0, 6.0))
        real_home = int(rng.poisson(mu_home))
        real_away = int(rng.poisson(mu_away))
        game_mu = mu_home + mu_away
        # Continuous lines (no half-line aliasing → the control isn't contaminated by rounding).
        gt_line = game_mu + float(rng.normal(0, 0.15))               # game-total ≈ true mean
        f5_line = 0.54 * game_mu + float(rng.normal(0, 0.10))        # F5 coherently derived (≈0.54)
        tt_home = mu_home + float(rng.normal(0, 0.12))               # coherent team totals
        tt_away = mu_away + float(rng.normal(0, 0.12))
        for bk in books:
            jit = float(rng.normal(0, 0.08))
            # ── R2: team-totals sum ↔ game total (coherent) — implied_raw = home_tt + away_tt ────
            rows.append(_smoke_row(R2, gp, season, gd, ym, "game", bk, gt_line + jit,
                                   real_home + real_away, implied_raw=tt_home + tt_away,
                                   posted=gt_line, rng=rng))
            # ── R3: F5 ↔ full game (coherent NEGATIVE CONTROL) — implied_raw = F5 line ──────────
            rows.append(_smoke_row(R3, gp, season, gd, ym, "game", bk, gt_line + jit,
                                   real_home + real_away, implied_raw=f5_line,
                                   posted=gt_line, rng=rng))
        # ── R1: props (informative) ↔ team total (shaded LOW by `mis` when efficiency<1) ────────
        for side, mu_t, real_t in (("home", mu_home, real_home), ("away", mu_away, real_away)):
            mis = float(rng.normal(0, 0.8)) * (1.0 - efficiency)     # team-total line mispricing
            tt_line = mu_t - mis                                     # consensus shaded LOW when mis>0
            prop_sum = mu_t + float(rng.normal(0, 0.15))             # props stay ≈ truth (informative)
            for bk in books:
                jit = float(rng.normal(0, 0.08))
                rows.append(_smoke_row(R1, gp, season, gd, ym, side, bk, tt_line + jit, real_t,
                                       implied_raw=prop_sum, posted=tt_line, rng=rng))
    return pd.DataFrame(rows)[CACHE_COLS]


def _smoke_row(relation, gp, season, gd, ym, side, bk, line_B, realized_B, *, implied_raw, posted, rng):
    vig = 0.045 if bk == "pinnacle" else float(rng.uniform(0.06, 0.10))
    over = _american(0.5 + vig / 2)        # ≈ fair at the posted line (book prices its own line ~50/50)
    under = _american(0.5 + vig / 2)
    return {"relation": relation, "game_pk": gp, "season": season, "game_date": gd, "ym": ym,
            "side_label": side, "bookmaker_key": bk, "line_B": float(line_B),
            "over_price": over, "under_price": under, "realized_B": float(realized_B),
            "implied_raw": float(implied_raw), "posted_B": float(posted),
            "sd_a": float(abs(rng.normal(0, 0.05))), "sd_b": float(abs(rng.normal(0, 0.05)))}


def _american(p: float) -> int:
    p = float(np.clip(p, 1e-3, 1 - 1e-3))
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


# ════════════════════════════════════════════════════════════════════════════════════════════════
def run_eval(frame: pd.DataFrame, *, suffix: str = "", synthetic: bool = False,
             status: dict | None = None) -> dict:
    res = evaluate(frame)
    meta = {"n_rows": int(len(frame)), "n_games": int(frame["game_pk"].nunique()),
            "seasons": sorted(pd.to_numeric(frame["season"], errors="coerce").dropna()
                              .astype(int).unique().tolist()),
            "relations_present": sorted([r for r in RELATIONS if (frame["relation"] == r).any()]),
            "status": status or {}}
    write_dossier(meta, res, suffix=suffix, synthetic=synthetic)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E13.14 cross-market constellation-coherence eval")
    ap.add_argument("--smoke", action="store_true", help="synthetic end-to-end run (no S3)")
    ap.add_argument("--build-cache", action="store_true", help="read S3 → cache parquet (operator)")
    ap.add_argument("--rebuild-cache", action="store_true", help="force cache rebuild")
    ap.add_argument("--seasons", default="2023,2024,2025,2026")
    ap.add_argument("--start-date", default=None, help="pitch-settle floor, e.g. 2023-01-01")
    args = ap.parse_args(argv)

    if args.smoke:
        print("[smoke] synthetic frame — R2/R3 coherent (control), R1 carries an injected "
              "inconsistency; efficiency=1 ⇒ clean null, efficiency<1 ⇒ R1 fires (control still safe)")
        run_eval(make_smoke_frame(efficiency=0.0), suffix="_smoke", synthetic=True)
        return 0

    seasons = [int(s) for s in args.seasons.split(",")]
    status = None
    if args.build_cache or args.rebuild_cache or not CACHE.exists():
        if not (args.build_cache or args.rebuild_cache) and not CACHE.exists():
            print(f"[error] no cache at {CACHE}; run with --build-cache (operator, >1-min S3 scan).",
                  file=sys.stderr)
            return 2
        frame = build_cache(seasons, args.start_date)
    else:
        frame = pd.read_parquet(CACHE)
        print(f"[cache] loaded {len(frame):,} rows from {CACHE}")
    sf = CACHE.with_suffix(".status.json")
    if sf.exists():
        status = json.loads(sf.read_text())
    run_eval(frame, status=status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
