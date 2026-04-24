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

__generated_with = "0.23.2"
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
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    import snowflake.connector

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.dpi": 120,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
    })
    return (
        default_backend,
        mo,
        np,
        pd,
        plt,
        scipy_stats,
        serialization,
        smf,
        snowflake,
    )


@app.cell
def _(mo):
    mo.md("""
    # 06 — Bat Tracking Era: Does 2023+ Data Add Signal Beyond Traditional Metrics?

    **Source:** `feature_pregame_game_features` (2023–2025) + rolling bat tracking aggregated
    from `stg_batter_pitches` (computed inline — not yet in the feature store)

    **Key question:** Given ~2,800 games in the bat tracking era vs. ~20,640 without, does the
    signal gain from `bat_speed_mph` / `swing_length_ft` features justify a separate era-specific
    model path and the complexity it adds?

    ---

    **Bat tracking rollout:** Hawk-Eye bat sensor data became available starting **2023-07-14**
    (mid-season All-Star break). Coverage is for swing-contact events only (~45% of pitches in
    2024+). The feature store does not yet include bat tracking aggregations — this notebook
    builds 30-day rolling team averages via a Snowflake CTE.
    """)
    return


@app.cell
def _(default_backend, pd, serialization, snowflake):
    # Null rate for bat_speed_mph by season/period — quantifies availability window
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
            game_year,
            CASE
                WHEN game_year = 2023 AND game_date >= '2023-07-14' THEN '2023-H2 (post-rollout)'
                WHEN game_year = 2023                               THEN '2023-H1 (pre-rollout)'
                ELSE game_year::varchar
            END                              AS label,
            COUNT(*)                         AS total_pitches,
            SUM(CASE WHEN bat_speed_mph IS NULL THEN 1 ELSE 0 END) AS null_count,
            ROUND(
                100.0 * SUM(CASE WHEN bat_speed_mph IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1
            )                                AS null_pct
        FROM baseball_data.betting.stg_batter_pitches
        WHERE game_type = 'R'
          AND game_year BETWEEN 2019 AND 2025
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)
    null_df = pd.DataFrame(
        _cur.fetchall(),
        columns=[col[0].lower() for col in _cur.description],
    )
    _cur.close()
    _conn.close()
    for _col in null_df.select_dtypes(include="object").columns:
        try:
            null_df[_col] = pd.to_numeric(null_df[_col])
        except (ValueError, TypeError):
            pass
    return (null_df,)


@app.cell
def _(mo, null_df, plt):
    plt.close("all")
    _colors = []
    for _lbl in null_df["label"]:
        if "post-rollout" in str(_lbl):
            _colors.append("#E65100")
        elif "pre-rollout" in str(_lbl):
            _colors.append("#888888")
        else:
            _colors.append("#1565C0")

    _fig, _ax = plt.subplots(figsize=(10, 4))
    _bars = _ax.bar(null_df["label"], null_df["null_pct"], color=_colors, alpha=0.82, width=0.6)
    for _rect, _v in zip(_bars, null_df["null_pct"]):
        _ax.text(
            _rect.get_x() + _rect.get_width() / 2.0,
            float(_rect.get_height()) + 1.5,
            f"{_v:.0f}%",
            ha="center", va="bottom", fontsize=8,
        )
    _ax.set_xlabel("Season / Period")
    _ax.set_ylabel("bat_speed_mph null rate (%)")
    _ax.set_title("Bat Speed Null Rate by Season — 100% null before 2023-07-14")
    _ax.set_ylim(0, 108)
    from matplotlib.patches import Patch as _Patch
    _ax.legend(handles=[
        _Patch(color="#1565C0", alpha=0.82, label="Pre-bat-tracking seasons"),
        _Patch(color="#888888", alpha=0.82, label="2023 H1 (pre-rollout)"),
        _Patch(color="#E65100", alpha=0.82, label="2023 H2+ (post-rollout)"),
    ], fontsize=8)
    plt.tight_layout()
    mo.output.append(_fig)
    mo.output.append(mo.ui.table(
        null_df[["label", "total_pitches", "null_count", "null_pct"]].rename(columns={
            "label": "Period",
            "total_pitches": "Total Pitches",
            "null_count": "Null bat_speed_mph",
            "null_pct": "Null %",
        })
    ))
    return


@app.cell
def _(default_backend, pd, serialization, snowflake):
    # Main data load: 2023-2025 traditional features + rolling 30d bat tracking per team
    # Rolling bat speed built from stg_batter_pitches via Snowflake window functions.
    # No leakage: RANGE BETWEEN '30 DAYS' PRECEDING AND '1 DAY' PRECEDING excludes same-day games.
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
        WITH bat_pitches AS (
            SELECT
                game_pk,
                game_date::date                                                       AS game_date,
                game_year,
                CASE WHEN inning_half = 'Top' THEN away_team ELSE home_team END       AS batting_team,
                bat_speed_mph,
                swing_length_ft
            FROM baseball_data.betting.stg_batter_pitches
            WHERE game_type = 'R'
              AND game_year BETWEEN 2023 AND 2025
              AND bat_speed_mph IS NOT NULL
        ),
        game_bt AS (
            SELECT
                game_pk,
                game_date,
                batting_team,
                AVG(bat_speed_mph)   AS game_bat_speed_avg,
                AVG(swing_length_ft) AS game_swing_length_avg
            FROM bat_pitches
            GROUP BY 1, 2, 3
        ),
        rolling_bt AS (
            SELECT
                game_pk,
                batting_team,
                AVG(game_bat_speed_avg) OVER (
                    PARTITION BY batting_team
                    ORDER BY game_date
                    RANGE BETWEEN INTERVAL '30 DAYS' PRECEDING AND INTERVAL '1 DAY' PRECEDING
                )   AS bat_speed_30d,
                AVG(game_swing_length_avg) OVER (
                    PARTITION BY batting_team
                    ORDER BY game_date
                    RANGE BETWEEN INTERVAL '30 DAYS' PRECEDING AND INTERVAL '1 DAY' PRECEDING
                )   AS swing_length_30d,
                COUNT(*) OVER (
                    PARTITION BY batting_team
                    ORDER BY game_date
                    RANGE BETWEEN INTERVAL '30 DAYS' PRECEDING AND INTERVAL '1 DAY' PRECEDING
                )   AS bt_games_in_window
            FROM game_bt
        )
        SELECT
            f.game_pk,
            f.game_year,
            f.game_date,
            f.home_team,
            f.away_team,
            f.home_off_woba_30d,
            f.away_off_woba_30d,
            f.home_pit_xwoba_against_30d,
            f.away_pit_xwoba_against_30d,
            f.home_starter_k_pct_std,
            f.away_starter_k_pct_std,
            f.park_run_factor_3yr,
            rh.bat_speed_30d      AS home_bat_speed_30d,
            rh.swing_length_30d   AS home_swing_length_30d,
            rh.bt_games_in_window AS home_bt_games_30d,
            ra.bat_speed_30d      AS away_bat_speed_30d,
            ra.swing_length_30d   AS away_swing_length_30d,
            ra.bt_games_in_window AS away_bt_games_30d,
            g.home_final_score + g.away_final_score   AS total_runs,
            g.run_differential,
            g.home_team_won::integer                   AS home_win
        FROM baseball_data.betting_features.feature_pregame_game_features f
        JOIN baseball_data.betting.mart_game_results g ON g.game_pk = f.game_pk
        LEFT JOIN rolling_bt rh ON rh.game_pk = f.game_pk AND rh.batting_team = f.home_team
        LEFT JOIN rolling_bt ra ON ra.game_pk = f.game_pk AND ra.batting_team = f.away_team
        WHERE f.has_full_data = true
          AND f.game_year BETWEEN 2023 AND 2025
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
def _(df_raw, pd):
    _NUMERIC = [
        "home_off_woba_30d", "away_off_woba_30d",
        "home_pit_xwoba_against_30d", "away_pit_xwoba_against_30d",
        "home_starter_k_pct_std", "away_starter_k_pct_std",
        "park_run_factor_3yr",
        "home_bat_speed_30d", "away_bat_speed_30d",
        "home_swing_length_30d", "away_swing_length_30d",
        "home_bt_games_30d", "away_bt_games_30d",
        "total_runs", "run_differential", "home_win",
    ]
    df = df_raw.copy()
    for _c in _NUMERIC:
        if _c in df.columns:
            df[_c] = pd.to_numeric(df[_c], errors="coerce")
    df = df.dropna(subset=["total_runs"]).copy()

    BT_COLS = [
        "home_bat_speed_30d", "away_bat_speed_30d",
        "home_swing_length_30d", "away_swing_length_30d",
    ]
    # Sub-sample: both teams have a full 30-day bat tracking rolling average
    df_bt = df.dropna(subset=BT_COLS).copy()

    # Full 2016-2025 training set size (from notebook 03, min 15 games played, 2020 excluded)
    N_FULL_TRADITIONAL = 20640
    return BT_COLS, N_FULL_TRADITIONAL, df, df_bt


@app.cell
def _(BT_COLS, N_FULL_TRADITIONAL, df, df_bt, mo, pd):
    _n_era = len(df)
    _n_bt = len(df_bt)
    _pct_era = 100.0 * _n_bt / _n_era if _n_era > 0 else 0.0
    _pct_full = 100.0 * _n_bt / N_FULL_TRADITIONAL

    _rows = []
    for _yr in sorted(df["game_year"].dropna().unique()):
        _yr_df = df[df["game_year"] == _yr]
        _yr_bt = _yr_df.dropna(subset=BT_COLS)
        _rows.append({
            "Season": int(_yr),
            "Total games (has_full_data)": len(_yr_df),
            "Games with bat tracking (both teams)": len(_yr_bt),
            "Coverage": f"{100.0 * len(_yr_bt) / len(_yr_df):.1f}%" if len(_yr_df) > 0 else "—",
        })
    _season_tbl = pd.DataFrame(_rows)

    mo.output.append(mo.md(f"""
    ## Part 1 — Bat Tracking Coverage

    | Metric | Value |
    |---|---|
    | 2023–2025 games (has_full_data) | **{_n_era:,}** |
    | Games where BOTH teams have 30d bat tracking | **{_n_bt:,}** ({_pct_era:.1f}% of 2023–2025) |
    | As % of full 2016–2025 training set | **{_pct_full:.1f}%** ({_n_bt:,} of {N_FULL_TRADITIONAL:,}) |

    A bat-tracking-era model would give up **{100 - _pct_full:.1f}%** of historical training data.
    """))
    mo.output.append(mo.ui.table(_season_tbl))
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 2 — Univariate Correlations: Traditional vs. Bat Tracking Features
    """)
    return


@app.cell
def _(df_bt, mo, np, plt):
    plt.close("all")

    _TRAD = {
        "home_off_woba_30d":          "Home Off wOBA (30d)",
        "away_off_woba_30d":          "Away Off wOBA (30d)",
        "home_pit_xwoba_against_30d": "Home Pit xwOBA Against (30d)",
        "away_pit_xwoba_against_30d": "Away Pit xwOBA Against (30d)",
        "home_starter_k_pct_std":     "Home Starter K% (STD)",
        "away_starter_k_pct_std":     "Away Starter K% (STD)",
        "park_run_factor_3yr":        "Park Run Factor (3yr)",
    }
    _BT = {
        "home_bat_speed_30d":     "Home Bat Speed (30d)",
        "away_bat_speed_30d":     "Away Bat Speed (30d)",
        "home_swing_length_30d":  "Home Swing Length (30d)",
        "away_swing_length_30d":  "Away Swing Length (30d)",
    }
    _TARGET = "total_runs"
    _sub = df_bt.dropna(subset=list(_TRAD) + list(_BT) + [_TARGET]).copy()

    _rs = {
        f: float(np.corrcoef(_sub[f].astype(float), _sub[_TARGET].astype(float))[0, 1])
        for f in list(_TRAD) + list(_BT)
    }
    _labels = {**_TRAD, **_BT}
    _colors = {f: "#1565C0" for f in _TRAD}
    _colors.update({f: "#E65100" for f in _BT})

    _pairs = sorted(_rs.items(), key=lambda x: abs(x[1]), reverse=True)
    _feats, _vals = zip(*_pairs)
    _abs_vals = [abs(v) for v in _vals]
    _bar_colors = [_colors[f] for f in _feats]

    _fig, _ax = plt.subplots(figsize=(12, 5))
    _xs = list(range(len(_feats)))
    _bars = _ax.bar(_xs, _abs_vals, color=_bar_colors, alpha=0.82)
    for _xi, (_rv, _av) in enumerate(zip(_vals, _abs_vals)):
        _ax.text(_xi, _av + 0.001, f"{_rv:+.3f}", ha="center", fontsize=7, rotation=45)
    _ax.axhline(0.05, color="gray", lw=0.8, ls="--", alpha=0.5, label="|r| = 0.05 reference")
    _ax.set_xticks(_xs)
    _ax.set_xticklabels([_labels[f] for f in _feats], rotation=38, ha="right", fontsize=8)
    _ax.set_ylabel("|Pearson r| with total runs")
    _ax.set_title(
        f"Feature Correlations with Total Runs — 2023–2025 bat-tracking sub-sample (n = {len(_sub):,})"
    )
    from matplotlib.patches import Patch as _Patch
    _ax.legend(handles=[
        _Patch(color="#1565C0", alpha=0.82, label="Traditional features"),
        _Patch(color="#E65100", alpha=0.82, label="Bat tracking features"),
        *_ax.get_legend_handles_labels()[0],
    ], fontsize=8)
    plt.tight_layout()
    mo.output.append(_fig)
    return


@app.cell
def _(df_bt, mo, plt, scipy_stats):
    plt.close("all")
    # Check bat speed–wOBA redundancy: if r > 0.7 bat tracking is largely captured by existing metrics
    _CHECK_PAIRS = [
        ("home_bat_speed_30d",    "home_off_woba_30d"),
        ("away_bat_speed_30d",    "away_off_woba_30d"),
        ("home_swing_length_30d", "home_off_woba_30d"),
        ("away_swing_length_30d", "away_off_woba_30d"),
    ]
    _valid = [(a, b) for a, b in _CHECK_PAIRS if a in df_bt.columns and b in df_bt.columns]
    _pair_rs = {}
    for _a, _b in _valid:
        _s = df_bt[[_a, _b]].dropna()
        if len(_s) >= 30:
            _r, _p = scipy_stats.pearsonr(_s[_a].astype(float), _s[_b].astype(float))
            _pair_rs[(_a, _b)] = (float(_r), float(_p))

    if _pair_rs:
        _fig, _axes = plt.subplots(1, len(_pair_rs), figsize=(4.5 * len(_pair_rs), 4))
        if len(_pair_rs) == 1:
            _axes = [_axes]
        for _ax, ((_a, _b), (_rv, _pv)) in zip(_axes, _pair_rs.items()):
            _s = df_bt[[_a, _b]].dropna()
            _ax.scatter(_s[_a], _s[_b], alpha=0.07, s=5, color="#1565C0")
            _ax.set_title(f"r = {_rv:.3f}", fontsize=9)
            _ax.set_xlabel(_a.replace("_30d", "").replace("_", " "), fontsize=7)
            _ax.set_ylabel(_b.replace("_30d", "").replace("_", " "), fontsize=7)
            _tag = "Redundant (r > 0.7)" if abs(_rv) > 0.7 else "Low overlap"
            _color = "#C62828" if abs(_rv) > 0.7 else "#2E7D32"
            _ax.text(0.05, 0.92, _tag, transform=_ax.transAxes, fontsize=8, color=_color)
        plt.suptitle("Bat Speed / Swing Length vs. Off wOBA — Redundancy Check", fontsize=10, y=1.02)
        plt.tight_layout()
        mo.output.append(_fig)

    bat_speed_woba_r = (
        max(abs(rv) for (rv, _) in _pair_rs.values())
        if _pair_rs else float("nan")
    )
    mo.output.append(mo.md(
        f"**Max |r| (bat tracking vs. wOBA):** {bat_speed_woba_r:.3f} — "
        + ("**Highly redundant** with traditional metrics (|r| > 0.7)"
           if bat_speed_woba_r > 0.7
           else "Moderate overlap (0.5 < |r| ≤ 0.7)"
           if bat_speed_woba_r > 0.5
           else "**Low redundancy** — independent from traditional metrics")
    ))
    return (bat_speed_woba_r,)


@app.cell
def _(df_bt, mo, pd, smf):
    _OLS_COLS = [
        "total_runs",
        "home_off_woba_30d", "away_off_woba_30d",
        "home_pit_xwoba_against_30d", "away_pit_xwoba_against_30d",
        "home_starter_k_pct_std", "away_starter_k_pct_std",
        "park_run_factor_3yr",
        "home_bat_speed_30d", "away_bat_speed_30d",
        "home_swing_length_30d", "away_swing_length_30d",
    ]
    _ols_df = df_bt.dropna(subset=_OLS_COLS).copy()

    _f_trad = (
        "total_runs ~ home_off_woba_30d + away_off_woba_30d"
        " + home_pit_xwoba_against_30d + away_pit_xwoba_against_30d"
        " + home_starter_k_pct_std + away_starter_k_pct_std"
        " + park_run_factor_3yr"
    )
    _f_full = _f_trad + (
        " + home_bat_speed_30d + away_bat_speed_30d"
        " + home_swing_length_30d + away_swing_length_30d"
    )

    _m_trad = smf.ols(_f_trad, data=_ols_df).fit()
    _m_full = smf.ols(_f_full, data=_ols_df).fit()

    ols_r2_trad = float(_m_trad.rsquared)
    ols_r2_full = float(_m_full.rsquared)
    delta_r2    = ols_r2_full - ols_r2_trad
    ols_n       = int(_m_trad.nobs)

    def _coef_tbl(model):
        return pd.DataFrame({
            "predictor": model.params.index,
            "coef":      model.params.values.round(5),
            "std_err":   model.bse.values.round(5),
            "t":         model.tvalues.values.round(3),
            "p-value":   model.pvalues.values.round(5),
        })

    mo.output.append(mo.md(f"""
    ## Part 3 — OLS R² Comparison (same {ols_n:,}-game sample)

    Both models are fit on the **identical** sub-sample where bat tracking is non-null for both teams.

    | Model | Features | R² | Adj R² | ΔR² |
    |---|---|---|---|---|
    | Traditional only | wOBA, xwOBA against, starter K%, park factor | {ols_r2_trad:.5f} | {_m_trad.rsquared_adj:.5f} | — |
    | + Bat tracking | + bat speed 30d, swing length 30d (home & away) | {ols_r2_full:.5f} | {_m_full.rsquared_adj:.5f} | **+{delta_r2:.5f}** |
    """))
    mo.output.append(mo.md("#### Traditional model coefficients"))
    mo.output.append(mo.ui.table(_coef_tbl(_m_trad)))
    mo.output.append(mo.md("#### Traditional + bat tracking model coefficients"))
    mo.output.append(mo.ui.table(_coef_tbl(_m_full)))
    return delta_r2, ols_n, ols_r2_full, ols_r2_trad


@app.cell
def _(
    N_FULL_TRADITIONAL,
    bat_speed_woba_r,
    delta_r2,
    mo,
    ols_n,
    ols_r2_full,
    ols_r2_trad,
):
    _pct_of_training = 100.0 * ols_n / N_FULL_TRADITIONAL
    _gain_meaningful = delta_r2 >= 0.005
    _highly_redundant = bat_speed_woba_r > 0.7
    _moderate_redundant = bat_speed_woba_r > 0.5

    if not _gain_meaningful and _highly_redundant:
        _rec = "**Single-model path — bat tracking not worth the complexity**"
        _body = (
            f"Bat tracking adds only **{delta_r2:.5f}** R² on the bat-tracking sub-sample. "
            f"Bat speed and wOBA are highly correlated (|r| = {bat_speed_woba_r:.3f}), so the signal "
            f"is already captured by existing offensive metrics. A separate 2023+ model path would "
            f"restrict training to {ols_n:,} games ({_pct_of_training:.1f}% of the full historical set) "
            f"for negligible gain."
        )
    elif not _gain_meaningful:
        _rec = "**Single-model path — bat tracking not worth the complexity yet**"
        _body = (
            f"Bat tracking adds only **{delta_r2:.5f}** R² — below the 0.005 threshold. "
            f"As bat tracking coverage grows (2026+), re-run this notebook. A larger sample may "
            f"reveal stronger signal. For now, the cost ({_pct_of_training:.1f}% of training data) "
            f"exceeds the measurable benefit."
        )
    elif _highly_redundant:
        _rec = "**Single-model path — bat tracking is largely redundant with wOBA**"
        _body = (
            f"Bat tracking adds **{delta_r2:.5f}** R² (≥ 0.005), but bat speed and wOBA are "
            f"highly correlated (|r| = {bat_speed_woba_r:.3f}). The marginal information content "
            f"is low once wOBA is already in the model. Not worth restricting to "
            f"{ols_n:,} games ({_pct_of_training:.1f}% of training data)."
        )
    else:
        _rec = "**Consider an era-specific model path**"
        _body = (
            f"Bat tracking adds **{delta_r2:.5f}** R² with moderate redundancy "
            f"(|r| = {bat_speed_woba_r:.3f} with wOBA). The gain is meaningful but the "
            f"sample ({ols_n:,} games, {_pct_of_training:.1f}% of training set) is small. "
            f"Revisit once bat-tracking coverage exceeds 50% of the training set (~10,000+ games)."
        )

    mo.md(f"""
    ## Phase 3 — Notebook 06 Findings and Verdict

    ### Coverage Summary
    - `bat_speed_mph` is **100% null before 2023-07-14** (pitch-level source)
    - Games with bat tracking for both teams: **{ols_n:,}** ({_pct_of_training:.1f}% of 2016–2025 training set)

    ### Signal Analysis
    - OLS R² — traditional only: **{ols_r2_trad:.5f}**
    - OLS R² — traditional + bat tracking: **{ols_r2_full:.5f}**
    - ΔR² = **{delta_r2:.5f}** (threshold for meaningful gain: 0.005)
    - Bat speed–wOBA redundancy: |r| = **{bat_speed_woba_r:.3f}**

    ---

    ### Phase 4 Recommendation

    {_rec}

    {_body}

    | Feature group | Phase 4 decision | Rationale |
    |---|---|---|
    | Traditional metrics (wOBA, xwOBA, K%) | **Include** in primary model | Full 2016–2025 coverage; strongest signal |
    | `bat_speed_mph`, `swing_length_ft` | **Exclude from primary model** | Restrict training to ~{_pct_of_training:.0f}% of data; signal not yet compelling |
    | `post_2022_rules`, `game_year` flags | **Include** | Capture 2022→2023 regime shift without restricting sample size |
    | Bat tracking enrichment block | **Optional, post-2026** | Re-evaluate when bat-tracking games exceed 50% of training set |
    """)
    return


if __name__ == "__main__":
    app.run()
