# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo>=0.10.0",
#   "pandas>=2.0",
#   "numpy>=1.26",
#   "matplotlib>=3.8",
#   "seaborn>=0.13",
#   "scipy>=1.11",
#   "statsmodels>=0.14",
#   "snowflake-connector-python>=3.6",
#   "cryptography>=41.0",
# ]
# ///

import marimo

__generated_with = "0.23.3"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns
    from scipy import stats as scipy_stats
    import statsmodels.formula.api as smf

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.dpi": 120,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
    })
    return mo, pd, scipy_stats, smf


@app.cell
def _(pd):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    import snowflake.connector

    _KEY_PATH = "/Users/charlesclark/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
    with open(_KEY_PATH, "rb") as _f:
        _p_key = serialization.load_pem_private_key(
            _f.read(), password=None, backend=default_backend()
        )
    _pkb = _p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _conn = snowflake.connector.connect(
        account="IHUPICS-DP59975",
        user="dbt_rw",
        private_key=_pkb,
        role="ACCOUNTADMIN",
        warehouse="COMPUTE_WH",
        database="baseball_data",
    )
    _cur = _conn.cursor()
    _cur.execute("""
        SELECT
            -- Park
            f.park_run_factor_3yr,
            -- Team offense (all windows for comparison)
            f.home_off_woba_7d, f.home_off_woba_30d,
            f.away_off_woba_7d, f.away_off_woba_30d,
            -- Team pitching (all windows)
            f.home_pit_xwoba_against_7d, f.home_pit_xwoba_against_30d,
            f.away_pit_xwoba_against_7d, f.away_pit_xwoba_against_30d,
            -- Starter quality (all windows)
            f.home_starter_xwoba_against_7d, f.home_starter_xwoba_against_30d, f.home_starter_xwoba_against_std,
            f.away_starter_xwoba_against_7d, f.away_starter_xwoba_against_30d, f.away_starter_xwoba_against_std,
            f.home_starter_k_pct_7d, f.home_starter_k_pct_30d, f.home_starter_k_pct_std,
            f.away_starter_k_pct_7d, f.away_starter_k_pct_30d, f.away_starter_k_pct_std,
            -- Card 4.1: delta/momentum features
            f.home_off_woba_7d_minus_30d,
            f.away_off_woba_7d_minus_30d,
            f.home_pit_xwoba_7d_minus_30d,
            f.away_pit_xwoba_7d_minus_30d,
            f.home_starter_xwoba_7d_minus_std,
            f.away_starter_xwoba_7d_minus_std,
            f.home_starter_k_pct_7d_minus_std,
            f.away_starter_k_pct_7d_minus_std,
            f.home_starter_fastball_velo_trend,
            f.away_starter_fastball_velo_trend,
            -- Card 4.2: lineup-vs-starter handedness matchup adjustments
            f.home_lineup_vs_away_starter_xwoba_adj,
            f.away_lineup_vs_home_starter_xwoba_adj,
            f.home_lineup_vs_away_starter_k_pct_adj,
            f.away_lineup_vs_home_starter_k_pct_adj,
            f.home_lineup_vs_away_starter_bb_pct_adj,
            f.away_lineup_vs_home_starter_bb_pct_adj,
            -- Targets
            g.home_final_score + g.away_final_score      AS total_runs,
            g.run_differential,
            IFF(g.home_team_won, 1, 0)::integer          AS home_win
        FROM baseball_data.betting_features.feature_pregame_game_features f
        JOIN baseball_data.betting.mart_game_results g ON g.game_pk = f.game_pk
        WHERE f.has_full_data = true
          AND f.game_year BETWEEN 2016 AND 2025
          AND f.game_year != 2020
        ORDER BY f.game_pk
    """)
    df_raw = pd.DataFrame(
        _cur.fetchall(),
        columns=[col[0].lower() for col in _cur.description],
    )
    _cur.close()
    _conn.close()
    for _col in df_raw.select_dtypes(include="object").columns:
        try:
            df_raw[_col] = pd.to_numeric(df_raw[_col])
        except (ValueError, TypeError):
            pass
    return (df_raw,)


@app.cell
def _(df_raw, mo, pd):
    TARGET_COLS   = ["total_runs", "run_differential", "home_win"]
    TARGET_LABELS = ["Total Runs", "Run Differential", "Home Win"]

    DELTA_FEATURES = [
        "home_off_woba_7d_minus_30d",
        "away_off_woba_7d_minus_30d",
        "home_pit_xwoba_7d_minus_30d",
        "away_pit_xwoba_7d_minus_30d",
        "home_starter_xwoba_7d_minus_std",
        "away_starter_xwoba_7d_minus_std",
        "home_starter_k_pct_7d_minus_std",
        "away_starter_k_pct_7d_minus_std",
        "home_starter_fastball_velo_trend",
        "away_starter_fastball_velo_trend",
    ]

    HANDEDNESS_FEATURES = [
        "home_lineup_vs_away_starter_xwoba_adj",
        "away_lineup_vs_home_starter_xwoba_adj",
        "home_lineup_vs_away_starter_k_pct_adj",
        "away_lineup_vs_home_starter_k_pct_adj",
        "home_lineup_vs_away_starter_bb_pct_adj",
        "away_lineup_vs_home_starter_bb_pct_adj",
    ]

    # Baseline A: 30d/std windows (consistent with NB04 baseline)
    BASELINE_30D = [
        "park_run_factor_3yr",
        "home_off_woba_30d", "away_off_woba_30d",
        "home_pit_xwoba_against_30d", "away_pit_xwoba_against_30d",
        "home_starter_xwoba_against_30d", "away_starter_xwoba_against_30d",
        "home_starter_xwoba_against_std", "away_starter_xwoba_against_std",
        "home_starter_k_pct_30d", "away_starter_k_pct_30d",
        "home_starter_k_pct_std", "away_starter_k_pct_std",
    ]

    # Baseline B: rich baseline already containing both 7d and 30d/std windows
    BASELINE_RICH = [
        "park_run_factor_3yr",
        "home_off_woba_7d", "home_off_woba_30d",
        "away_off_woba_7d", "away_off_woba_30d",
        "home_pit_xwoba_against_7d", "home_pit_xwoba_against_30d",
        "away_pit_xwoba_against_7d", "away_pit_xwoba_against_30d",
        "home_starter_xwoba_against_7d", "home_starter_xwoba_against_30d", "home_starter_xwoba_against_std",
        "away_starter_xwoba_against_7d", "away_starter_xwoba_against_30d", "away_starter_xwoba_against_std",
        "home_starter_k_pct_7d", "home_starter_k_pct_30d", "home_starter_k_pct_std",
        "away_starter_k_pct_7d", "away_starter_k_pct_30d", "away_starter_k_pct_std",
    ]

    df = df_raw[
        BASELINE_RICH + DELTA_FEATURES + HANDEDNESS_FEATURES + TARGET_COLS
    ].copy()
    for _c in TARGET_COLS:
        df[_c] = pd.to_numeric(df[_c], errors="coerce")

    n_full = len(df.dropna(subset=TARGET_COLS + BASELINE_30D + DELTA_FEATURES))
    n_handedness = len(df.dropna(subset=TARGET_COLS + BASELINE_30D + DELTA_FEATURES + HANDEDNESS_FEATURES))

    mo.output.append(mo.md(
        f"**Dataset:** has_full_data=true, 2016–2025 (excl. 2020)  \n"
        f"n = {len(df):,} total | {n_full:,} for baseline+delta OLS | "
        f"{n_handedness:,} for handedness OLS (non-null handedness features)"
    ))
    return (
        BASELINE_30D,
        BASELINE_RICH,
        DELTA_FEATURES,
        HANDEDNESS_FEATURES,
        TARGET_COLS,
        TARGET_LABELS,
        df,
    )


@app.cell
def _(mo):
    mo.md("""
    # 07 — Engineered Feature Incremental Lift Validation (Card 3.7)

    Tests whether Cards 4.1 (delta/momentum) and 4.2 (lineup-vs-starter handedness) provide
    incremental signal over base rolling features.

    **Two-step analysis:**
    1. Correlation fast pass — |Pearson r| for each engineered feature vs. all three targets
    2. OLS ΔR² — baseline → +delta block → +handedness block; threshold = 0.005

    **Decision rule:** ΔR² ≥ 0.005 → flag for Phase 4 inclusion; ΔR² < 0.005 → validated low-signal
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 1 — Card 4.1: Delta/Momentum Features
    """)
    return


@app.cell
def _(DELTA_FEATURES, TARGET_COLS, TARGET_LABELS, df, mo, pd, scipy_stats):
    _rows = []
    for _feat in DELTA_FEATURES:
        _row = {"feature": _feat}
        for _tgt_col, _tgt_label in zip(TARGET_COLS, TARGET_LABELS):
            _mask = df[[_feat, _tgt_col]].notna().all(axis=1)
            if _mask.sum() < 100:
                _row[_tgt_label] = None
                continue
            _r, _ = scipy_stats.pearsonr(
                df.loc[_mask, _feat].astype(float),
                df.loc[_mask, _tgt_col].astype(float),
            )
            _row[_tgt_label] = round(_r, 4)
        _rows.append(_row)

    delta_corr_df = pd.DataFrame(_rows)
    delta_corr_df["|r| max"] = delta_corr_df[TARGET_LABELS].abs().max(axis=1).round(4)
    delta_corr_df = delta_corr_df.sort_values("|r| max", ascending=False).reset_index(drop=True)

    mo.output.append(mo.md("### Correlation Fast Pass — Delta/Momentum Features"))
    mo.output.append(mo.ui.table(delta_corr_df))
    mo.output.append(mo.md(
        f"**Max |r| across all delta features × all targets: "
        f"{delta_corr_df['|r| max'].max():.4f}** "
        f"(threshold for meaningful gain: 0.005 in OLS ΔR²)"
    ))
    return


@app.cell
def _(mo):
    mo.md("""
    ### Source Window Comparison

    Delta features encode (7d window − 30d/std window). Compare their marginal correlations
    against the source windows they derive from — these should be substantially higher.
    """)
    return


@app.cell
def _(TARGET_COLS, TARGET_LABELS, df, mo, pd, scipy_stats):
    _source_features = [
        ("home_off_woba_7d",          "7d team offense wOBA (H)"),
        ("home_off_woba_30d",         "30d team offense wOBA (H)"),
        ("home_pit_xwoba_against_7d", "7d team pitching xwOBA (H)"),
        ("home_pit_xwoba_against_30d","30d team pitching xwOBA (H)"),
        ("home_starter_xwoba_against_7d",  "7d starter xwOBA (H)"),
        ("home_starter_xwoba_against_std", "std starter xwOBA (H)"),
        ("home_starter_k_pct_7d",          "7d starter K% (H)"),
        ("home_starter_k_pct_std",         "std starter K% (H)"),
    ]
    _rows = []
    for _feat, _label in _source_features:
        _row = {"feature": _feat, "label": _label}
        for _tgt_col, _tgt_label in zip(TARGET_COLS, TARGET_LABELS):
            _mask = df[[_feat, _tgt_col]].notna().all(axis=1)
            if _mask.sum() < 100:
                _row[_tgt_label] = None
                continue
            _r, _ = scipy_stats.pearsonr(
                df.loc[_mask, _feat].astype(float),
                df.loc[_mask, _tgt_col].astype(float),
            )
            _row[_tgt_label] = round(_r, 4)
        _rows.append(_row)
    source_corr_df = pd.DataFrame(_rows)
    mo.output.append(mo.md("**Source window correlations for comparison (home-side shown):**"))
    mo.output.append(mo.ui.table(source_corr_df))
    return


@app.cell
def _(
    BASELINE_30D,
    DELTA_FEATURES,
    TARGET_COLS,
    TARGET_LABELS,
    df,
    mo,
    pd,
    smf,
):
    _rows = []
    for _tgt, _lbl in zip(TARGET_COLS, TARGET_LABELS):
        _d = df[BASELINE_30D + DELTA_FEATURES + [_tgt]].dropna()
        _n = len(_d)
        _m0 = smf.ols(_tgt + " ~ " + " + ".join(BASELINE_30D), data=_d).fit()
        _m1 = smf.ols(_tgt + " ~ " + " + ".join(BASELINE_30D + DELTA_FEATURES), data=_d).fit()
        _rows.append({
            "Target": _lbl,
            "n": _n,
            "Baseline R²": round(_m0.rsquared, 5),
            "+ Delta R²": round(_m1.rsquared, 5),
            "ΔR²": round(_m1.rsquared - _m0.rsquared, 5),
            "> 0.005 threshold": "YES" if (_m1.rsquared - _m0.rsquared) >= 0.005 else "no",
        })

    delta_ols_df = pd.DataFrame(_rows)
    mo.output.append(mo.md("""
    ### OLS ΔR² — Baseline A (30d/std) → + Delta Block

    **Baseline A** = park factor + team offense/pitching 30d + starter xwOBA/K% (30d + std).
    This is consistent with the NB04 feature set.

    **Interpretation note**: delta features (7d_minus_30d) are algebraically equivalent to adding
    the 7d window alongside the 30d baseline. The ΔR² measures "does having 7d recency add signal
    beyond 30d/std windows?" — not pure momentum direction.
    """))
    mo.output.append(mo.ui.table(delta_ols_df))
    return (delta_ols_df,)


@app.cell
def _(
    BASELINE_RICH,
    DELTA_FEATURES,
    TARGET_COLS,
    TARGET_LABELS,
    df,
    mo,
    pd,
    smf,
):
    _rows = []
    for _tgt, _lbl in zip(TARGET_COLS, TARGET_LABELS):
        _d = df[BASELINE_RICH + DELTA_FEATURES + [_tgt]].dropna()
        _n = len(_d)
        _m0 = smf.ols(_tgt + " ~ " + " + ".join(BASELINE_RICH), data=_d).fit()
        _m1 = smf.ols(_tgt + " ~ " + " + ".join(BASELINE_RICH + DELTA_FEATURES), data=_d).fit()
        _rows.append({
            "Target": _lbl,
            "n": _n,
            "Baseline B R² (7d+30d+std)": round(_m0.rsquared, 5),
            "+ Delta R²": round(_m1.rsquared, 5),
            "ΔR² (redundancy check)": round(_m1.rsquared - _m0.rsquared, 5),
        })

    delta_rich_ols_df = pd.DataFrame(_rows)
    mo.output.append(mo.md("""
    ### OLS ΔR² — Baseline B (rich: 7d+30d+std) → + Delta Block

    When the baseline already includes both 7d and 30d/std source windows, delta features
    are mathematically redundant (delta = 7d − 30d, exact linear combination). Expected ΔR² ≈ 0.
    """))
    mo.output.append(mo.ui.table(delta_rich_ols_df))
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 2 — Card 4.2: Lineup-vs-Starter Handedness Matchup Adjustments
    """)
    return


@app.cell
def _(
    HANDEDNESS_FEATURES,
    TARGET_COLS,
    TARGET_LABELS,
    df,
    mo,
    pd,
    scipy_stats,
):
    _rows = []
    for _feat in HANDEDNESS_FEATURES:
        _row = {"feature": _feat}
        for _tgt_col, _tgt_label in zip(TARGET_COLS, TARGET_LABELS):
            _mask = df[[_feat, _tgt_col]].notna().all(axis=1)
            _row["n_non_null"] = int(_mask.sum())
            if _mask.sum() < 100:
                _row[_tgt_label] = None
                continue
            _r, _ = scipy_stats.pearsonr(
                df.loc[_mask, _feat].astype(float),
                df.loc[_mask, _tgt_col].astype(float),
            )
            _row[_tgt_label] = round(_r, 4)
        _rows.append(_row)

    hand_corr_df = pd.DataFrame(_rows)
    hand_corr_df["|r| max"] = hand_corr_df[TARGET_LABELS].abs().max(axis=1).round(4)
    hand_corr_df = hand_corr_df.sort_values("|r| max", ascending=False).reset_index(drop=True)

    mo.output.append(mo.md("### Correlation Fast Pass — Handedness Matchup Features"))
    mo.output.append(mo.ui.table(hand_corr_df))
    return


@app.cell
def _(
    BASELINE_30D,
    DELTA_FEATURES,
    HANDEDNESS_FEATURES,
    TARGET_COLS,
    TARGET_LABELS,
    df,
    mo,
    pd,
    scipy_stats,
    smf,
):
    # Cross-correlation: handedness vs base starter features
    _cross_pairs = [
        ("home_lineup_vs_away_starter_xwoba_adj", "away_starter_xwoba_against_std"),
        ("away_lineup_vs_home_starter_xwoba_adj", "home_starter_xwoba_against_std"),
        ("home_lineup_vs_away_starter_k_pct_adj", "away_starter_k_pct_std"),
        ("away_lineup_vs_home_starter_k_pct_adj", "home_starter_k_pct_std"),
    ]
    _cc_rows = []
    for _hf, _bf in _cross_pairs:
        _mask = df[[_hf, _bf]].notna().all(axis=1)
        _r, _ = scipy_stats.pearsonr(df.loc[_mask, _hf].astype(float), df.loc[_mask, _bf].astype(float))
        _cc_rows.append({"handedness_feature": _hf, "base_feature": _bf, "Pearson r": round(_r, 4)})
    mo.output.append(mo.md("### Cross-Correlation: Handedness vs Base Starter Features"))
    mo.output.append(mo.ui.table(pd.DataFrame(_cc_rows)))

    # OLS: handedness on top of baseline + delta
    _h_rows = []
    for _tgt, _lbl in zip(TARGET_COLS, TARGET_LABELS):
        _all_vars = BASELINE_30D + DELTA_FEATURES + HANDEDNESS_FEATURES + [_tgt]
        _d = df[_all_vars].dropna()
        _n = len(_d)
        _m0 = smf.ols(_tgt + " ~ " + " + ".join(BASELINE_30D + DELTA_FEATURES), data=_d).fit()
        _m1 = smf.ols(_tgt + " ~ " + " + ".join(BASELINE_30D + DELTA_FEATURES + HANDEDNESS_FEATURES), data=_d).fit()
        _h_rows.append({
            "Target": _lbl,
            "n": _n,
            "Baseline+Delta R²": round(_m0.rsquared, 5),
            "+ Handedness R²": round(_m1.rsquared, 5),
            "ΔR²": round(_m1.rsquared - _m0.rsquared, 5),
            "> 0.005 threshold": "YES" if (_m1.rsquared - _m0.rsquared) >= 0.005 else "no",
        })

    hand_ols_df = pd.DataFrame(_h_rows)
    mo.output.append(mo.md("""
    ### OLS ΔR² — Baseline+Delta → + Handedness Block

    Tests whether lineup-vs-starter handedness matchup features add signal beyond the
    baseline (30d/std) and delta feature set.
    """))
    mo.output.append(mo.ui.table(hand_ols_df))
    return (hand_ols_df,)


@app.cell
def _(delta_ols_df, hand_ols_df, mo):
    _thresh = 0.005
    _delta_max_dr2 = delta_ols_df["ΔR²"].max()
    _hand_max_dr2 = hand_ols_df["ΔR²"].max()

    _delta_verdict = "**PHASE 4 INCLUDE (7d window signal)**" if _delta_max_dr2 >= _thresh else "validated low-signal"
    _hand_verdict = "**PHASE 4 INCLUDE**" if _hand_max_dr2 >= _thresh else "validated low-signal"

    mo.md(f"""
    ## Summary — Card 3.7 Verdicts

    | Block | Max ΔR² | > 0.005? | Phase 4 Decision |
    |---|---|---|---|
    | Delta/momentum (Card 4.1) | {_delta_max_dr2:.4f} | {"YES" if _delta_max_dr2 >= _thresh else "no"} | {_delta_verdict} |
    | Handedness matchup (Card 4.2) | {_hand_max_dr2:.4f} | {"YES" if _hand_max_dr2 >= _thresh else "no"} | {_hand_verdict} |

    **Delta/momentum interpretation:** ΔR² > 0.005 when added to 30d/std-only baseline, but this
    reflects 7d window recency value — not pure momentum direction. Delta features are algebraically
    equivalent to adding 7d windows. When baseline already includes 7d windows, ΔR² ≈ 0 (linear
    redundancy). Phase 4 should include 7d rolling windows directly rather than delta encoding.

    **Handedness matchup interpretation:** k_pct_adj features have moderate marginal |r| (0.063–0.086
    for run_diff/home_win) but ΔR² < 0.005 after controlling for underlying starter stats. Signal
    already captured by starter xwOBA and K% in the model. Validated low-signal for linear models.
    """)
    return


if __name__ == "__main__":
    app.run()
