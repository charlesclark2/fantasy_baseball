"""Card 3.11 — Bookmaker Calibration and Market Efficiency Analysis.

Analyzes bookmaker accuracy for moneyline and totals markets using 2021-2025
historical odds. Evaluates H1-H7, computes market consensus Brier as the Phase 4
model benchmark. Data source: mart_odds_outcomes (pre-parsed, per-bookmaker) joined
through mart_game_odds_bridge to game_pk universe.
"""

import json
import os
import sys
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import snowflake.connector

_KEY_PATH = os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

SHARP_BOOKS = ["lowvig", "betonlineag", "bovada"]
SOFT_BOOKS = ["draftkings", "fanduel", "betmgm", "williamhill_us", "betrivers"]
PRIMARY_BOOKS = SHARP_BOOKS + SOFT_BOOKS
_BOOKS_SQL = "', '".join(PRIMARY_BOOKS)

MIN_ML_EVENTS = 500
MIN_TOTALS_EVENTS = 100
MIN_CONSENSUS_BOOKS = 3


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super().default(obj)


def _connect() -> snowflake.connector.SnowflakeConnection:
    with open(_KEY_PATH, "rb") as fh:
        p_key = serialization.load_pem_private_key(
            fh.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account="IHUPICS-DP59975",
        user="dbt_rw",
        private_key=pkb,
        role="ACCOUNTADMIN",
        warehouse="COMPUTE_WH",
        database="baseball_data",
    )


def _fetch_df(conn: snowflake.connector.SnowflakeConnection, query: str) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(query)
    cols = [d[0].lower() for d in cur.description]
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= df[col].notna().sum():
                df[col] = converted
    return df


def _american_to_raw_prob(odds: np.ndarray) -> np.ndarray:
    """Vectorized American odds → raw (vig-inclusive) probability."""
    odds = np.asarray(odds, dtype=float)
    return np.where(
        odds > 0,
        100.0 / (odds + 100.0),
        np.abs(odds) / (np.abs(odds) + 100.0),
    )


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load game universe, outcomes, per-bookmaker h2h and totals odds.

    Returns (df_outcomes, df_h2h, df_totals). df_h2h and df_totals are
    already joined with outcomes and have vig-adjusted probabilities computed.
    """
    conn = _connect()
    try:
        print("Loading game universe (gate check)...")
        df_universe = _fetch_df(conn, """
            SELECT g.game_pk, b.event_id, g.game_year
            FROM baseball_data.betting_features.feature_pregame_game_features g
            JOIN baseball_data.betting.mart_game_odds_bridge b ON b.game_pk = g.game_pk
            WHERE g.has_odds = true
              AND g.game_year BETWEEN 2021 AND 2025
        """)
        n_games = len(df_universe)
        print(f"  Gate check: {n_games:,} matched games")
        assert n_games >= 5_000, f"Gate requires >=5,000 matched games, got {n_games}"

        print("Loading actual outcomes...")
        df_outcomes = _fetch_df(conn, """
            SELECT r.game_pk,
                   CASE WHEN r.home_final_score > r.away_final_score THEN 1 ELSE 0 END AS home_win,
                   r.home_final_score + r.away_final_score AS total_runs
            FROM baseball_data.betting.mart_game_results r
            JOIN baseball_data.betting.mart_game_odds_bridge b ON b.game_pk = r.game_pk
            JOIN baseball_data.betting_features.feature_pregame_game_features g ON g.game_pk = r.game_pk
            WHERE g.has_odds = true
              AND g.game_year BETWEEN 2021 AND 2025
        """)
        print(f"  Outcomes: {len(df_outcomes):,} games")

        print("Loading h2h odds per bookmaker...")
        df_h2h_raw = _fetch_df(conn, f"""
            SELECT b.game_pk, g.game_year, o.bookmaker_key,
                   MAX(CASE WHEN o.is_home_outcome THEN o.outcome_price_american END) AS home_price,
                   MAX(CASE WHEN o.is_away_outcome  THEN o.outcome_price_american END) AS away_price
            FROM baseball_data.betting.mart_odds_outcomes o
            JOIN baseball_data.betting.mart_game_odds_bridge b ON b.event_id = o.event_id
            JOIN baseball_data.betting_features.feature_pregame_game_features g ON g.game_pk = b.game_pk
            WHERE g.has_odds = true
              AND g.game_year BETWEEN 2021 AND 2025
              AND o.market_key = 'h2h'
              AND o.bookmaker_key IN ('{_BOOKS_SQL}')
            GROUP BY b.game_pk, g.game_year, o.bookmaker_key
        """)
        print(f"  H2H odds: {len(df_h2h_raw):,} game-book rows")

        print("Loading totals odds per bookmaker...")
        df_totals_raw = _fetch_df(conn, f"""
            SELECT b.game_pk, g.game_year, o.bookmaker_key,
                   MAX(o.outcome_point) AS total_line,
                   MAX(CASE WHEN o.outcome_name = 'Over'  THEN o.outcome_price_american END) AS over_price,
                   MAX(CASE WHEN o.outcome_name = 'Under' THEN o.outcome_price_american END) AS under_price
            FROM baseball_data.betting.mart_odds_outcomes o
            JOIN baseball_data.betting.mart_game_odds_bridge b ON b.event_id = o.event_id
            JOIN baseball_data.betting_features.feature_pregame_game_features g ON g.game_pk = b.game_pk
            WHERE g.has_odds = true
              AND g.game_year BETWEEN 2021 AND 2025
              AND o.market_key = 'totals'
              AND o.bookmaker_key IN ('{_BOOKS_SQL}')
            GROUP BY b.game_pk, g.game_year, o.bookmaker_key
        """)
        print(f"  Totals odds: {len(df_totals_raw):,} game-book rows")

    finally:
        conn.close()

    # Vig-adjust h2h probabilities
    mask_h2h = df_h2h_raw["home_price"].notna() & df_h2h_raw["away_price"].notna()
    df_h2h = df_h2h_raw[mask_h2h].copy()
    raw_home = _american_to_raw_prob(df_h2h["home_price"].values)
    raw_away = _american_to_raw_prob(df_h2h["away_price"].values)
    overround = raw_home + raw_away
    df_h2h["h2h_over"] = overround
    df_h2h["home_imp"] = raw_home / overround

    # Vig-adjust totals probabilities
    mask_tot = (
        df_totals_raw["total_line"].notna()
        & df_totals_raw["over_price"].notna()
        & df_totals_raw["under_price"].notna()
    )
    df_totals = df_totals_raw[mask_tot].copy()
    raw_over = _american_to_raw_prob(df_totals["over_price"].values)
    raw_under = _american_to_raw_prob(df_totals["under_price"].values)
    tot_overround = raw_over + raw_under
    df_totals["tot_over"] = tot_overround
    df_totals["over_imp"] = raw_over / tot_overround

    # Join with outcomes
    df_h2h = df_h2h.merge(df_outcomes, on="game_pk", how="inner")
    df_totals = df_totals.merge(df_outcomes, on="game_pk", how="inner")

    print(f"  H2H analysis set: {len(df_h2h):,} game-book rows ({df_h2h['game_pk'].nunique():,} unique games)")
    print(f"  Totals analysis set: {len(df_totals):,} game-book rows ({df_totals['game_pk'].nunique():,} unique games)")

    return df_outcomes, df_h2h, df_totals


def step1_vig_overround(df_h2h: pd.DataFrame, df_totals: pd.DataFrame) -> dict:
    """Step 1 — Vig/Overround Rankings."""
    print("\nSTEP 1 — Vig/Overround Rankings")

    h2h_stats = (
        df_h2h.groupby("bookmaker_key")
        .agg(median_overround=("h2h_over", "median"), n_events=("game_pk", "nunique"))
        .reset_index()
    )
    h2h_stats = h2h_stats[h2h_stats["n_events"] >= 100].sort_values("median_overround").reset_index(drop=True)
    h2h_stats["h2h_rank"] = range(1, len(h2h_stats) + 1)

    lowvig_rows = h2h_stats[h2h_stats["bookmaker_key"] == "lowvig"]
    lowvig_h2h_rank = int(lowvig_rows["h2h_rank"].iloc[0]) if len(lowvig_rows) > 0 else -1

    totals_stats = (
        df_totals.groupby("bookmaker_key")
        .agg(median_overround=("tot_over", "median"), n_events=("game_pk", "nunique"))
        .reset_index()
    )
    totals_stats = totals_stats[totals_stats["n_events"] >= 100].sort_values("median_overround").reset_index(drop=True)

    tot_dict = totals_stats.set_index("bookmaker_key")["median_overround"].to_dict()

    print(f"  {'Book':<20} {'Rank':>5} {'H2H Med OR':>12} {'Tot Med OR':>12} {'N H2H':>8}")
    print("  " + "-" * 62)
    for _, row in h2h_stats.iterrows():
        bk = row["bookmaker_key"]
        tot_or = tot_dict.get(bk, float("nan"))
        print(
            f"  {bk:<20} {int(row['h2h_rank']):>5} {row['median_overround']:>12.5f}"
            f" {tot_or:>12.5f} {int(row['n_events']):>8}"
        )
    print(f"  lowvig h2h rank: {lowvig_h2h_rank}")

    h2h_result = [
        {
            "bookmaker": r["bookmaker_key"],
            "median_overround": float(r["median_overround"]),
            "n_events": int(r["n_events"]),
            "h2h_rank": int(r["h2h_rank"]),
        }
        for _, r in h2h_stats.iterrows()
    ]
    totals_result = [
        {
            "bookmaker": r["bookmaker_key"],
            "median_overround": float(r["median_overround"]),
            "n_events": int(r["n_events"]),
        }
        for _, r in totals_stats.iterrows()
    ]

    return {"h2h": h2h_result, "totals": totals_result, "lowvig_h2h_rank": lowvig_h2h_rank}


def step2_moneyline_calibration(df_h2h: pd.DataFrame) -> dict:
    """Step 2 — Moneyline Calibration."""
    print("\nSTEP 2 — Moneyline Calibration (book x season, >=500 events)")

    by_book_season = []
    for (book, season), grp in df_h2h.groupby(["bookmaker_key", "game_year"]):
        if len(grp) < MIN_ML_EVENTS:
            continue
        home_imp = grp["home_imp"].values
        hw = grp["home_win"].values.astype(float)
        brier = float(np.mean((home_imp - hw) ** 2))
        clipped = np.clip(home_imp, 1e-6, 1 - 1e-6)
        ll = float(-np.mean(hw * np.log(clipped) + (1 - hw) * np.log(1 - clipped)))
        by_book_season.append(
            {"bookmaker": book, "season": int(season), "n_events": len(grp), "brier_score": brier, "log_loss": ll}
        )

    print(f"  {'Book':<20} {'Season':>7} {'N':>6} {'Brier':>9} {'LogLoss':>10}")
    print("  " + "-" * 57)
    for r in sorted(by_book_season, key=lambda x: (x["bookmaker"], x["season"])):
        print(
            f"  {r['bookmaker']:<20} {r['season']:>7} {r['n_events']:>6}"
            f" {r['brier_score']:>9.5f} {r['log_loss']:>10.5f}"
        )

    # Top 5 books by total event count → calibration curves (10 decile buckets)
    book_totals = df_h2h.groupby("bookmaker_key")["game_pk"].nunique().sort_values(ascending=False)
    top5 = book_totals.head(5).index.tolist()

    calibration_curves: dict[str, list] = {}
    for book in top5:
        grp = df_h2h[df_h2h["bookmaker_key"] == book].copy()
        try:
            grp["decile"] = pd.qcut(grp["home_imp"], q=10, labels=False, duplicates="drop")
        except ValueError:
            continue
        deciles = []
        for d in range(10):
            bucket = grp[grp["decile"] == d]
            if len(bucket) == 0:
                continue
            deciles.append(
                {
                    "decile": d + 1,
                    "mean_predicted": float(bucket["home_imp"].mean()),
                    "mean_actual": float(bucket["home_win"].mean()),
                    "n_events": len(bucket),
                }
            )
        if len(deciles) == 10:
            calibration_curves[book] = deciles

    # Home-team bias per book x season
    home_team_bias = []
    for (book, season), grp in df_h2h.groupby(["bookmaker_key", "game_year"]):
        if len(grp) < MIN_ML_EVENTS:
            continue
        mean_imp = float(grp["home_imp"].mean())
        actual_wr = float(grp["home_win"].mean())
        home_team_bias.append(
            {
                "bookmaker": book,
                "season": int(season),
                "n_events": len(grp),
                "mean_implied_home_prob": mean_imp,
                "actual_home_win_rate": actual_wr,
                "bias": round(mean_imp - actual_wr, 6),
            }
        )

    print("\n  Home-team bias (mean across seasons per book):")
    print(f"  {'Book':<20} {'Mean Bias':>10}")
    print("  " + "-" * 32)
    bias_df = pd.DataFrame(home_team_bias)
    if not bias_df.empty:
        per_book = bias_df.groupby("bookmaker")["bias"].mean().sort_values()
        for book, mb in per_book.items():
            print(f"  {book:<20} {mb:>10.5f}")

    return {
        "by_bookmaker_season": by_book_season,
        "calibration_curves": calibration_curves,
        "home_team_bias": home_team_bias,
    }


def step3_totals_accuracy(df_totals: pd.DataFrame) -> dict:
    """Step 3 — Totals Accuracy."""
    print("\nSTEP 3 — Totals Accuracy (book x season, >=100 events)")

    by_book_season = []
    for (book, season), grp in df_totals.groupby(["bookmaker_key", "game_year"]):
        if len(grp) < MIN_TOTALS_EVENTS:
            continue
        line = grp["total_line"].values.astype(float)
        actual = grp["total_runs"].values.astype(float)
        mae = float(np.mean(np.abs(line - actual)))
        bias = float(np.mean(line - actual))
        over_rate = float(np.mean(actual > line))
        by_book_season.append(
            {
                "bookmaker": book,
                "season": int(season),
                "n_events": len(grp),
                "mae": mae,
                "bias": bias,
                "over_rate": over_rate,
            }
        )

    print(f"  {'Book':<20} {'Season':>7} {'N':>6} {'MAE':>8} {'Bias':>8} {'OverRate':>10}")
    print("  " + "-" * 65)
    for r in sorted(by_book_season, key=lambda x: (x["bookmaker"], x["season"])):
        print(
            f"  {r['bookmaker']:<20} {r['season']:>7} {r['n_events']:>6}"
            f" {r['mae']:>8.4f} {r['bias']:>8.4f} {r['over_rate']:>10.4f}"
        )

    # Mean line by season (one line per game, averaged across books)
    line_by_event = df_totals.groupby(["game_pk", "game_year"])["total_line"].mean().reset_index()
    line_by_season = []
    for season, grp in line_by_event.groupby("game_year"):
        line_by_season.append(
            {
                "season": int(season),
                "mean_line": float(grp["total_line"].mean()),
                "median_line": float(grp["total_line"].median()),
                "std_line": float(grp["total_line"].std()),
            }
        )
    line_by_season.sort(key=lambda x: x["season"])

    print("\n  Mean totals line by season:")
    print(f"  {'Season':>7} {'Mean Line':>10} {'Median':>8} {'Std':>8}")
    print("  " + "-" * 38)
    for r in line_by_season:
        print(f"  {r['season']:>7} {r['mean_line']:>10.4f} {r['median_line']:>8.4f} {r['std_line']:>8.4f}")

    return {"by_bookmaker_season": by_book_season, "line_distribution_by_season": line_by_season}


def step4_consensus_disagreement(
    df_h2h: pd.DataFrame, df_totals: pd.DataFrame
) -> tuple[dict, pd.DataFrame]:
    """Step 4 — Cross-Bookmaker Consensus and Disagreement."""
    print("\nSTEP 4 — Consensus / Disagreement")

    # Per-event h2h consensus (all books)
    ev_all = (
        df_h2h.groupby("game_pk")
        .agg(
            home_win=("home_win", "first"),
            game_year=("game_year", "first"),
            home_win_prob_consensus=("home_imp", "mean"),
            ml_consensus_std=("home_imp", "std"),
            market_bookmaker_count=("bookmaker_key", "nunique"),
        )
        .reset_index()
    )

    # Sharp books consensus
    sharp_agg = (
        df_h2h[df_h2h["bookmaker_key"].isin(SHARP_BOOKS)]
        .groupby("game_pk")["home_imp"]
        .agg(home_win_prob_sharp="mean", n_sharp_books="count")
        .reset_index()
    )
    # Soft books consensus
    soft_agg = (
        df_h2h[df_h2h["bookmaker_key"].isin(SOFT_BOOKS)]
        .groupby("game_pk")["home_imp"]
        .agg(home_win_prob_soft="mean", n_soft_books="count")
        .reset_index()
    )

    ev = ev_all.merge(sharp_agg, on="game_pk", how="left")
    ev = ev.merge(soft_agg, on="game_pk", how="left")

    # Totals consensus (line and over probability)
    tot_agg = (
        df_totals.groupby("game_pk")
        .agg(
            total_line_consensus=("total_line", "mean"),
            total_line_std=("total_line", "std"),
            over_prob_consensus=("over_imp", "mean"),
        )
        .reset_index()
    )
    ev = ev.merge(tot_agg, on="game_pk", how="left")

    # Filter to events with >= MIN_CONSENSUS_BOOKS
    ev_consensus = ev[ev["market_bookmaker_count"] >= MIN_CONSENSUS_BOOKS].copy()
    ev_consensus["sharp_soft_ml_delta"] = (
        ev_consensus["home_win_prob_sharp"] - ev_consensus["home_win_prob_soft"]
    )
    ev_consensus["hw"] = ev_consensus["home_win"].astype(float)

    # Sharp vs soft Brier (events where both groups present)
    both_mask = ev_consensus["home_win_prob_sharp"].notna() & ev_consensus["home_win_prob_soft"].notna()
    ev_both = ev_consensus[both_mask]
    sharp_brier = float(np.mean((ev_both["home_win_prob_sharp"] - ev_both["hw"]) ** 2))
    soft_brier = float(np.mean((ev_both["home_win_prob_soft"] - ev_both["hw"]) ** 2))
    n_sharp_games = int(len(ev_both))
    n_soft_games = int(len(ev_both))

    # Sharp-soft delta Pearson r
    delta_mask = ev_consensus["sharp_soft_ml_delta"].notna()
    ev_delta = ev_consensus[delta_mask]
    r_val, p_val = stats.pearsonr(ev_delta["sharp_soft_ml_delta"], ev_delta["hw"])

    # Disagreement quartile signal
    std_mask = ev_consensus["ml_consensus_std"].notna()
    ev_q = ev_consensus[std_mask].copy()
    ev_q["quartile"] = pd.qcut(ev_q["ml_consensus_std"], q=4, labels=[1, 2, 3, 4])

    quartile_signal = []
    for q in [1, 2, 3, 4]:
        grp = ev_q[ev_q["quartile"] == q]
        quartile_signal.append(
            {
                "quartile": int(q),
                "std_min": float(grp["ml_consensus_std"].min()),
                "std_max": float(grp["ml_consensus_std"].max()),
                "n_games": int(len(grp)),
                "outcome_variance": float(grp["hw"].var()),
                "home_win_rate": float(grp["hw"].mean()),
            }
        )

    print(f"  Sharp books Brier: {sharp_brier:.4f}  (n={n_sharp_games:,})")
    print(f"  Soft books Brier:  {soft_brier:.4f}  (n={n_soft_games:,})")
    print(f"  Sharp-soft delta Pearson r with home_win: r={r_val:.3f}  p={p_val:.4f}")
    print(f"\n  Disagreement quartile signal:")
    print(f"  {'Q':>2} {'Std Range':>22} {'N':>6} {'OutcVar':>10} {'HWRate':>8}")
    print("  " + "-" * 54)
    for r in quartile_signal:
        print(
            f"  {r['quartile']:>2} [{r['std_min']:.4f}, {r['std_max']:.4f}]"
            f" {r['n_games']:>6} {r['outcome_variance']:>10.5f} {r['home_win_rate']:>8.4f}"
        )

    consensus_result = {
        "sharp_books": SHARP_BOOKS,
        "soft_books": SOFT_BOOKS,
        "sharp_brier": sharp_brier,
        "soft_brier": soft_brier,
        "n_sharp_games": n_sharp_games,
        "n_soft_games": n_soft_games,
        "sharp_soft_delta_r": float(r_val),
        "sharp_soft_delta_pval": float(p_val),
        "disagreement_quartile_signal": quartile_signal,
    }

    return consensus_result, ev_consensus


def step5_hypotheses_and_efficiency(
    step1_res: dict,
    step2_res: dict,
    step3_res: dict,
    step4_res: dict,
    ev_consensus: pd.DataFrame,
) -> tuple[dict, dict]:
    """Step 5 — Hypotheses H1-H7 and Market Efficiency Metrics."""
    print("\nSTEP 5 — Hypotheses")

    sharp_brier = step4_res["sharp_brier"]
    soft_brier = step4_res["soft_brier"]
    brier_diff = soft_brier - sharp_brier

    # H1: sharp_brier < soft_brier AND diff > 0.002
    if sharp_brier < soft_brier and brier_diff > 0.002:
        h1_verdict = "supported"
    elif sharp_brier >= soft_brier:
        h1_verdict = "not supported"
    else:
        h1_verdict = "inconclusive"

    # H2: lowvig_h2h_rank <= 2
    lowvig_rank = step1_res["lowvig_h2h_rank"]
    h2h_books = {r["bookmaker"]: r for r in step1_res["h2h"]}
    if lowvig_rank <= 2:
        if lowvig_rank == 2 and "lowvig" in h2h_books:
            rank1 = min(step1_res["h2h"], key=lambda x: x["h2h_rank"])
            margin = h2h_books["lowvig"]["median_overround"] - rank1["median_overround"]
            h2_verdict = "inconclusive" if margin < 0.001 else "supported"
        else:
            h2_verdict = "supported"
    else:
        h2_verdict = "not supported"

    # H3: mean home-team bias across all book-season entries
    bias_df = pd.DataFrame(step2_res["home_team_bias"])
    mean_bias = float(bias_df["bias"].mean()) if not bias_df.empty else 0.0
    if 0.010 <= mean_bias <= 0.030:
        h3_verdict = "supported"
    elif mean_bias < 0.005 or mean_bias > 0.040:
        h3_verdict = "not supported"
    else:
        h3_verdict = "inconclusive"

    # H4: Q4 outcome_variance > Q1 * 1.10
    q_signal = step4_res["disagreement_quartile_signal"]
    q1_var = next(q["outcome_variance"] for q in q_signal if q["quartile"] == 1)
    q4_var = next(q["outcome_variance"] for q in q_signal if q["quartile"] == 4)
    q4_q1_ratio = q4_var / q1_var if q1_var > 0 else 1.0
    if q4_var > q1_var * 1.10:
        h4_verdict = "supported"
    elif q4_var <= q1_var:
        h4_verdict = "not supported"
    else:
        h4_verdict = "inconclusive"

    # H5: abs(r) > 0.030 and p < 0.05
    r_val = step4_res["sharp_soft_delta_r"]
    p_val = step4_res["sharp_soft_delta_pval"]
    if abs(r_val) > 0.030 and p_val < 0.05:
        h5_verdict = "supported"
    elif abs(r_val) <= 0.010:
        h5_verdict = "not supported"
    else:
        h5_verdict = "inconclusive"

    # H6: line_delta = mean_line_2023-2025 vs 2021-2022
    line_by_season = {r["season"]: r["mean_line"] for r in step3_res["line_distribution_by_season"]}
    pre_vals = [line_by_season[s] for s in [2021, 2022] if s in line_by_season]
    post_vals = [line_by_season[s] for s in [2023, 2024, 2025] if s in line_by_season]
    pre_mean = float(np.mean(pre_vals)) if pre_vals else None
    post_mean = float(np.mean(post_vals)) if post_vals else None
    if pre_mean is not None and post_mean is not None:
        line_delta = post_mean - pre_mean
        if 0.20 <= line_delta <= 0.70:
            h6_verdict = "supported"
        elif line_delta < 0.10 or line_delta > 0.90:
            h6_verdict = "not supported"
        else:
            h6_verdict = "inconclusive"
    else:
        line_delta = float("nan")
        h6_verdict = "inconclusive"

    # H7: consensus_brier_overall
    ev = ev_consensus.copy()
    ev["hw"] = ev["home_win"].astype(float)
    consensus_brier = float(np.mean((ev["home_win_prob_consensus"] - ev["hw"]) ** 2))
    if consensus_brier < 0.240:
        h7_verdict = "supported"
    elif consensus_brier >= 0.250:
        h7_verdict = "not supported"
    else:
        h7_verdict = "inconclusive"

    # Market efficiency metrics
    fav_mask = ev["home_win_prob_consensus"] > 0.500
    dog_mask = ev["home_win_prob_consensus"] <= 0.500
    fav_brier = float(np.mean((ev.loc[fav_mask, "home_win_prob_consensus"] - ev.loc[fav_mask, "hw"]) ** 2)) if fav_mask.sum() > 0 else float("nan")
    dog_brier = float(np.mean((ev.loc[dog_mask, "home_win_prob_consensus"] - ev.loc[dog_mask, "hw"]) ** 2)) if dog_mask.sum() > 0 else float("nan")

    brier_by_season = []
    for season, grp in ev.groupby("game_year"):
        brier_by_season.append(
            {
                "season": int(season),
                "brier_score": float(np.mean((grp["home_win_prob_consensus"] - grp["hw"]) ** 2)),
                "n_games": int(len(grp)),
            }
        )
    brier_by_season.sort(key=lambda x: x["season"])

    # Print summary
    line_delta_str = f"{line_delta:.2f}" if not np.isnan(line_delta) else "N/A"
    pre_str = f"{pre_mean:.3f}" if pre_mean is not None else "N/A"
    post_str = f"{post_mean:.3f}" if post_mean is not None else "N/A"

    print(f"  H1 (sharp < soft Brier):            [{h1_verdict}]  delta={brier_diff:.4f}")
    print(f"  H2 (lowvig lowest overround):        [{h2_verdict}]  rank={lowvig_rank}")
    print(f"  H3 (home-team bias +1-3%):           [{h3_verdict}]  mean_bias={mean_bias:.3f}")
    print(f"  H4 (disagreement -> variance):        [{h4_verdict}]  Q4/Q1={q4_q1_ratio:.2f}")
    print(f"  H5 (sharp-soft delta signal):         [{h5_verdict}]  r={r_val:.3f}")
    print(f"  H6 (post-2023 line rise 0.3-0.5r):   [{h6_verdict}]  delta={line_delta_str}")
    print(f"  H7 (market beats naive baseline):     [{h7_verdict}]  brier={consensus_brier:.4f}")
    print(f"  Market baseline Brier (consensus):    {consensus_brier:.4f}")

    hypotheses = {
        "H1": {
            "verdict": h1_verdict,
            "evidence": (
                f"sharp_brier={sharp_brier:.5f}, soft_brier={soft_brier:.5f}, diff={brier_diff:.5f}. "
                f"Supported if sharp < soft AND diff > 0.002; not supported if sharp >= soft; "
                f"inconclusive if sharp < soft AND diff <= 0.002."
            ),
        },
        "H2": {
            "verdict": h2_verdict,
            "evidence": (
                f"lowvig_h2h_rank={lowvig_rank} (sorted by median h2h overround ascending). "
                f"Supported if rank <= 2; not supported if rank > 2."
            ),
        },
        "H3": {
            "verdict": h3_verdict,
            "evidence": (
                f"mean home-team bias={mean_bias:.5f} across all book-season pairs with >=500 events. "
                f"Supported if 0.010 <= mean_bias <= 0.030; not supported if < 0.005 or > 0.040."
            ),
        },
        "H4": {
            "verdict": h4_verdict,
            "evidence": (
                f"Q4 outcome_variance={q4_var:.5f}, Q1={q1_var:.5f}, ratio={q4_q1_ratio:.4f}. "
                f"Supported if Q4 > Q1 * 1.10; not supported if Q4 <= Q1."
            ),
        },
        "H5": {
            "verdict": h5_verdict,
            "evidence": (
                f"Pearson r(sharp_soft_delta, home_win)={r_val:.5f}, p={p_val:.5f}. "
                f"Supported if |r| > 0.030 and p < 0.05; not supported if |r| <= 0.010."
            ),
        },
        "H6": {
            "verdict": h6_verdict,
            "evidence": (
                f"Mean totals line: 2021-2022={pre_str}, 2023-2025={post_str}, delta={line_delta_str}. "
                f"Supported if 0.20 <= delta <= 0.70; not supported if delta < 0.10 or > 0.90."
            ),
        },
        "H7": {
            "verdict": h7_verdict,
            "evidence": (
                f"consensus_brier_overall={consensus_brier:.5f} (naive baseline ~0.250). "
                f"Supported if < 0.240; not supported if >= 0.250; inconclusive if [0.240, 0.250)."
            ),
        },
    }

    market_efficiency = {
        "consensus_brier_overall": consensus_brier,
        "favorite_brier": fav_brier,
        "underdog_brier": dog_brier,
        "brier_by_season": brier_by_season,
    }

    return hypotheses, market_efficiency


def build_design_recommendation(hypotheses: dict, market_efficiency: dict) -> dict:
    h1_supported = hypotheses["H1"]["verdict"] == "supported"
    h7_supported = hypotheses["H7"]["verdict"] == "supported"
    consensus_brier = market_efficiency["consensus_brier_overall"]

    include_consensus = bool(h7_supported)
    include_sharp_soft = bool(h1_supported)
    queue_mart = bool(include_consensus or include_sharp_soft)

    verdict_summary = "; ".join(
        f"{h}={v['verdict']}" for h, v in sorted(hypotheses.items())
    )
    rationale = (
        f"consensus_brier_overall={consensus_brier:.5f}. "
        f"H7 ({'supported' if h7_supported else hypotheses['H7']['verdict']}) → "
        f"include_consensus_features={include_consensus}. "
        f"H1 ({'supported' if h1_supported else hypotheses['H1']['verdict']}) → "
        f"include_sharp_soft_features={include_sharp_soft}. "
        f"queue_mart_odds_consensus_card={queue_mart}. "
        f"All verdicts: {verdict_summary}."
    )

    return {
        "include_consensus_features": include_consensus,
        "include_sharp_soft_features": include_sharp_soft,
        "queue_mart_odds_consensus_card": queue_mart,
        "market_baseline_brier": consensus_brier,
        "rationale": rationale,
    }


def main() -> None:
    print("=== Card 3.11 — Bookmaker Calibration and Market Efficiency ===")

    df_outcomes, df_h2h, df_totals = load_data()

    step1_res = step1_vig_overround(df_h2h, df_totals)
    step2_res = step2_moneyline_calibration(df_h2h)
    step3_res = step3_totals_accuracy(df_totals)
    step4_res, ev_consensus = step4_consensus_disagreement(df_h2h, df_totals)
    hypotheses, market_efficiency = step5_hypotheses_and_efficiency(
        step1_res, step2_res, step3_res, step4_res, ev_consensus
    )
    design_rec = build_design_recommendation(hypotheses, market_efficiency)

    results = {
        "vig_overround": step1_res,
        "moneyline_calibration": step2_res,
        "totals_accuracy": step3_res,
        "consensus_analysis": step4_res,
        "market_efficiency": market_efficiency,
        "hypotheses": hypotheses,
        "design_recommendation": design_rec,
    }

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluation")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "bookmaker_calibration_results.json")

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)

    print(f"\nResults written to {out_path}")
    print(f"\nDesign Recommendation:")
    print(f"  include_consensus_features:   {design_rec['include_consensus_features']}")
    print(f"  include_sharp_soft_features:  {design_rec['include_sharp_soft_features']}")
    print(f"  queue_mart_odds_consensus_card: {design_rec['queue_mart_odds_consensus_card']}")
    print(f"  market_baseline_brier:        {design_rec['market_baseline_brier']:.5f}")


if __name__ == "__main__":
    main()
