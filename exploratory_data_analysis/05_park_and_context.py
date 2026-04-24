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

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.dpi": 120,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
    })
    return mo, np, pd, plt, scipy_stats, smf, sns


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
            f.game_pk,
            f.game_year,
            f.venue_name,
            f.park_run_factor_3yr,
            f.runs_per_game_at_park,
            f.home_days_rest,
            f.away_days_rest,
            f.home_tz_changed_from_last_game,
            f.away_tz_changed_from_last_game,
            f.home_games_last_7d,
            f.away_games_last_7d,
            f.elevation_ft,
            g.home_final_score + g.away_final_score AS total_runs,
            g.run_differential,
            g.home_team_won::integer               AS home_win
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
def _(df_raw, pd):
    df = df_raw.copy()

    for _c in [
        "total_runs", "run_differential", "home_win",
        "park_run_factor_3yr", "runs_per_game_at_park",
        "home_days_rest", "away_days_rest",
        "home_tz_changed_from_last_game", "away_tz_changed_from_last_game",
        "home_games_last_7d", "away_games_last_7d",
        "elevation_ft",
    ]:
        if _c in df.columns:
            df[_c] = pd.to_numeric(df[_c], errors="coerce")

    REST_ORDER = ["0", "1", "2", "3", "4+"]

    def _bucket(x):
        if pd.isna(x):
            return None
        return "4+" if int(x) >= 4 else str(int(x))

    df["home_rest_bucket"] = df["home_days_rest"].apply(_bucket)
    df["away_rest_bucket"] = df["away_days_rest"].apply(_bucket)
    df = df.dropna(subset=["total_runs"]).copy()
    return REST_ORDER, df


@app.cell
def _(mo):
    mo.md("""
    # 05 — Park Run Factor and Schedule Fatigue Effects

    **Source:** `feature_pregame_game_features` (has_full_data = true) ⋈ `mart_game_results`
    **Training set:** 2016–2025 regular season, 2020 excluded

    Three questions:
    1. Does `park_run_factor_3yr` accurately predict relative total runs across venues?
    2. Do `days_rest` and `tz_changed_from_last_game` meaningfully shift game outcomes?
    3. How much variance do park + schedule features explain together (OLS R²)?
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 1 — Park Run Factor vs. Actual Total Runs
    """)
    return


@app.cell
def _(df, mo, pd, scipy_stats):
    _park_df = df.dropna(subset=["park_run_factor_3yr", "total_runs"]).copy()

    _r, _p = scipy_stats.pearsonr(
        _park_df["park_run_factor_3yr"].astype(float),
        _park_df["total_runs"].astype(float),
    )

    _park_df["prf_quartile"] = pd.qcut(
        _park_df["park_run_factor_3yr"],
        q=4,
        labels=["Q1 (pitcher-friendly)", "Q2", "Q3", "Q4 (hitter-friendly)"],
    )
    _qs = (
        _park_df.groupby("prf_quartile", observed=True)["total_runs"]
        .agg(n="count", mean="mean", std="std", median="median")
        .reset_index()
    )
    _qs.columns = ["Quartile", "N", "Mean Runs", "SD", "Median"]
    _qs = _qs.round({"Mean Runs": 3, "SD": 3, "Median": 2})

    _means = _qs.set_index("Quartile")["Mean Runs"]
    park_rank_preserved = bool(
        _means.get("Q1 (pitcher-friendly)", 0) < _means.get("Q2", 0)
        and _means.get("Q2", 0) < _means.get("Q3", 0)
        and _means.get("Q3", 0) < _means.get("Q4 (hitter-friendly)", 0)
    )
    quartile_spread = float(
        _means.get("Q4 (hitter-friendly)", float("nan"))
        - _means.get("Q1 (pitcher-friendly)", float("nan"))
    )

    mo.output.append(mo.md(
        f"**Pearson r (park_run_factor_3yr → total_runs):** {_r:.4f} "
        f"(p = {_p:.4g}, n = {len(_park_df):,})  \n"
        f"Quartile rank preserved (Q1 < Q2 < Q3 < Q4): **{park_rank_preserved}** | "
        f"Q4 − Q1 mean spread: **{quartile_spread:.2f} runs**"
    ))
    mo.output.append(mo.ui.table(_qs))

    park_r = float(_r)
    park_p = float(_p)
    return park_p, park_r, park_rank_preserved, quartile_spread


@app.cell
def _(df, mo, np, pd, plt, sns):
    plt.close("all")
    _park_df = df.dropna(subset=["park_run_factor_3yr", "total_runs"]).copy()
    _park_df["prf_quartile"] = pd.qcut(
        _park_df["park_run_factor_3yr"],
        q=4,
        labels=["Q1\n(pitcher-friendly)", "Q2", "Q3", "Q4\n(hitter-friendly)"],
    )
    _order = ["Q1\n(pitcher-friendly)", "Q2", "Q3", "Q4\n(hitter-friendly)"]

    _fig, (_ax1, _ax2) = plt.subplots(1, 2, figsize=(13, 5))

    sns.boxplot(
        data=_park_df, x="prf_quartile", y="total_runs",
        order=_order, palette="RdYlGn", showfliers=False, ax=_ax1,
    )
    _means_p = _park_df.groupby("prf_quartile", observed=True)["total_runs"].mean().reindex(_order)
    for _xi, _mv in enumerate(_means_p):
        if not np.isnan(_mv):
            _ax1.plot(_xi, _mv, marker="D", color="black", ms=6, zorder=5)
    _ax1.set_xlabel("Park Run Factor Quartile")
    _ax1.set_ylabel("Total Runs")
    _ax1.set_title("Total Runs by Park Quartile (diamonds = mean)")

    _ax2.scatter(
        _park_df["park_run_factor_3yr"],
        _park_df["total_runs"],
        alpha=0.04, s=8, color="#1565C0",
    )
    _mc, _bc = np.polyfit(
        _park_df["park_run_factor_3yr"].astype(float),
        _park_df["total_runs"].astype(float),
        1,
    )
    _xr = np.linspace(
        _park_df["park_run_factor_3yr"].min(),
        _park_df["park_run_factor_3yr"].max(),
        100,
    )
    _ax2.plot(_xr, _mc * _xr + _bc, color="#C62828", lw=1.8, label=f"OLS fit (slope={_mc:.2f})")
    _ax2.set_xlabel("park_run_factor_3yr")
    _ax2.set_ylabel("Total Runs")
    _ax2.set_title("Scatter: Park Factor vs. Total Runs")
    _ax2.legend(fontsize=8)

    plt.tight_layout()
    mo.output.append(_fig)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 2 — Schedule Fatigue Effects

    Testing whether `home_days_rest`, `away_days_rest`, and timezone travel
    (`home_tz_changed_from_last_game`, `away_tz_changed_from_last_game`) move
    total runs or home win rate. The hypothesis: fatigued or jet-lagged teams
    have degraded pitching depth and plate discipline.
    """)
    return


@app.cell
def _(REST_ORDER, df, mo, np, plt):
    plt.close("all")
    _fig, _axes = plt.subplots(2, 2, figsize=(14, 9))
    _fig.suptitle("Days Rest vs. Total Runs and Home Win Rate", fontsize=11, fontweight="bold")

    for _idx, (_bucket_col, _label) in enumerate([
        ("home_rest_bucket", "Home Team"),
        ("away_rest_bucket", "Away Team"),
    ]):
        _grp = (
            df.dropna(subset=[_bucket_col, "total_runs", "home_win"])
            .groupby(_bucket_col)
            .agg(
                mean_runs=("total_runs", "mean"),
                se_runs=("total_runs", lambda x: x.std() / np.sqrt(len(x))),
                win_rate=("home_win", "mean"),
                n=("total_runs", "count"),
            )
            .reindex(REST_ORDER)
            .dropna(subset=["mean_runs"])
        )
        _valid = _grp.index.tolist()
        _x = list(range(len(_valid)))

        _ax_r = _axes[_idx][0]
        _ax_r.bar(
            _x, _grp.loc[_valid, "mean_runs"],
            yerr=_grp.loc[_valid, "se_runs"] * 1.96,
            capsize=4, color="#1565C0", alpha=0.75, ecolor="gray", error_kw={"lw": 1.2},
        )
        _ax_r.axhline(
            float(_grp["mean_runs"].mean()),
            color="red", lw=1, ls="--", alpha=0.6, label="Group mean",
        )
        _ax_r.set_xticks(_x)
        _ax_r.set_xticklabels(_valid)
        _ax_r.set_title(f"{_label} Days Rest → Mean Total Runs (±95% CI)")
        _ax_r.set_xlabel("Days Rest")
        _ax_r.set_ylabel("Mean Total Runs")
        _ax_r.legend(fontsize=8)
        for _i, _bkt in enumerate(_valid):
            _n = int(_grp.loc[_bkt, "n"])
            _v = float(_grp.loc[_bkt, "mean_runs"])
            _e = float(_grp.loc[_bkt, "se_runs"]) * 2.2
            _ax_r.text(_i, _v + _e, f"n={_n}", ha="center", fontsize=7)

        _ax_w = _axes[_idx][1]
        _ax_w.bar(_x, _grp.loc[_valid, "win_rate"], color="#2E7D32", alpha=0.75)
        _ax_w.axhline(0.529, color="red", lw=1, ls="--", alpha=0.6, label="Season avg (0.529)")
        _ax_w.set_xticks(_x)
        _ax_w.set_xticklabels(_valid)
        _ax_w.set_title(f"{_label} Days Rest → Home Win Rate")
        _ax_w.set_xlabel("Days Rest")
        _ax_w.set_ylabel("Home Win Rate")
        _ax_w.set_ylim(0.46, 0.60)
        _ax_w.legend(fontsize=8)

    plt.tight_layout()
    mo.output.append(_fig)
    return


@app.cell
def _(df, mo, np, plt):
    plt.close("all")
    _fig, _axes = plt.subplots(2, 2, figsize=(12, 8))
    _fig.suptitle("Timezone Travel vs. Total Runs and Home Win Rate", fontsize=11, fontweight="bold")
    _xlabels = {0: "No TZ change", 1: "TZ changed"}

    for _row_idx, (_tz_col, _label) in enumerate([
        ("home_tz_changed_from_last_game", "Home Team"),
        ("away_tz_changed_from_last_game", "Away Team"),
    ]):
        _tz_df = df.dropna(subset=[_tz_col, "total_runs", "home_win"]).copy()
        _tz_df[_tz_col] = _tz_df[_tz_col].astype(int)

        _grp = (
            _tz_df.groupby(_tz_col)
            .agg(
                mean_runs=("total_runs", "mean"),
                se_runs=("total_runs", lambda x: x.std() / np.sqrt(len(x))),
                win_rate=("home_win", "mean"),
                n=("total_runs", "count"),
            )
        )
        _vals = _grp.index.tolist()
        _x = list(range(len(_vals)))

        _ax_r = _axes[_row_idx][0]
        _ax_r.bar(
            _x, _grp["mean_runs"].values,
            yerr=_grp["se_runs"].values * 1.96,
            capsize=4, color="#1565C0", alpha=0.75, ecolor="gray", error_kw={"lw": 1.2},
        )
        _ax_r.axhline(float(_grp["mean_runs"].mean()), color="red", lw=1, ls="--", alpha=0.5)
        _ax_r.set_xticks(_x)
        _ax_r.set_xticklabels([_xlabels.get(v, str(v)) for v in _vals])
        _ax_r.set_title(f"{_label} TZ Travel → Mean Total Runs")
        _ax_r.set_ylabel("Mean Total Runs")
        for _i, _v in enumerate(_vals):
            _n = int(_grp.loc[_v, "n"])
            _top = float(_grp.loc[_v, "mean_runs"]) + float(_grp.loc[_v, "se_runs"]) * 2.2
            _ax_r.text(_i, _top, f"n={_n}", ha="center", fontsize=7)

        _ax_w = _axes[_row_idx][1]
        _ax_w.bar(_x, _grp["win_rate"].values, color="#2E7D32", alpha=0.75)
        _ax_w.axhline(0.529, color="red", lw=1, ls="--", alpha=0.6, label="Avg (0.529)")
        _ax_w.set_xticks(_x)
        _ax_w.set_xticklabels([_xlabels.get(v, str(v)) for v in _vals])
        _ax_w.set_title(f"{_label} TZ Travel → Home Win Rate")
        _ax_w.set_ylabel("Home Win Rate")
        _ax_w.set_ylim(0.46, 0.60)
        _ax_w.legend(fontsize=8)

    plt.tight_layout()
    mo.output.append(_fig)
    return


@app.cell
def _(df, mo, scipy_stats):
    # ANOVA: total_runs ~ home_rest_bucket
    _rest_grps = [
        g["total_runs"].dropna().values
        for _, g in df.dropna(subset=["home_rest_bucket", "total_runs"]).groupby("home_rest_bucket")
        if len(g) >= 30
    ]
    if len(_rest_grps) >= 2:
        _f_stat, _p_anova = scipy_stats.f_oneway(*_rest_grps)
    else:
        _f_stat, _p_anova = float("nan"), float("nan")

    # t-test: total_runs ~ home TZ change
    _tz_h = df.dropna(subset=["home_tz_changed_from_last_game", "total_runs"])
    _tz_h0 = _tz_h[_tz_h["home_tz_changed_from_last_game"] == 0]["total_runs"].values
    _tz_h1 = _tz_h[_tz_h["home_tz_changed_from_last_game"] == 1]["total_runs"].values
    if len(_tz_h0) >= 10 and len(_tz_h1) >= 10:
        _t_htz, _p_htz = scipy_stats.ttest_ind(_tz_h0, _tz_h1)
    else:
        _t_htz, _p_htz = float("nan"), float("nan")

    # t-test: home_win ~ away TZ change (does away team travel benefit home?)
    _tz_a = df.dropna(subset=["away_tz_changed_from_last_game", "home_win"])
    _tz_a0 = _tz_a[_tz_a["away_tz_changed_from_last_game"] == 0]["home_win"].values
    _tz_a1 = _tz_a[_tz_a["away_tz_changed_from_last_game"] == 1]["home_win"].values
    if len(_tz_a0) >= 10 and len(_tz_a1) >= 10:
        _t_atz, _p_atz = scipy_stats.ttest_ind(_tz_a0, _tz_a1)
    else:
        _t_atz, _p_atz = float("nan"), float("nan")

    mo.output.append(mo.md(f"""
    ### Statistical Significance Tests

    | Test | Statistic | p-value | Result |
    |---|---|---|---|
    | ANOVA: total_runs ~ home days rest (5 buckets) | F = {_f_stat:.3f} | {_p_anova:.4g} | {'**Significant** (p < 0.05)' if _p_anova < 0.05 else 'Not significant'} |
    | t-test: total_runs ~ home TZ change | t = {_t_htz:.3f} | {_p_htz:.4g} | {'**Significant** (p < 0.05)' if _p_htz < 0.05 else 'Not significant'} |
    | t-test: home_win ~ away TZ change | t = {_t_atz:.3f} | {_p_atz:.4g} | {'**Significant** (p < 0.05)' if _p_atz < 0.05 else 'Not significant'} |
    """))

    anova_p   = float(_p_anova)
    home_tz_p = float(_p_htz)
    away_tz_p = float(_p_atz)
    return anova_p, away_tz_p, home_tz_p


@app.cell
def _(mo):
    mo.md("""
    ## Part 3 — OLS Regression: Park + Schedule Context
    """)
    return


@app.cell
def _(df, mo, pd, smf):
    _ols_df = df.dropna(subset=[
        "total_runs", "park_run_factor_3yr",
        "home_days_rest", "away_days_rest",
        "home_tz_changed_from_last_game", "away_tz_changed_from_last_game",
    ]).copy()
    _ols_df["home_tz"] = _ols_df["home_tz_changed_from_last_game"].astype(float)
    _ols_df["away_tz"] = _ols_df["away_tz_changed_from_last_game"].astype(float)

    _m1 = smf.ols("total_runs ~ park_run_factor_3yr", data=_ols_df).fit()
    _m2 = smf.ols(
        "total_runs ~ park_run_factor_3yr + home_days_rest + away_days_rest + home_tz + away_tz",
        data=_ols_df,
    ).fit()

    ols_r2_park = float(_m1.rsquared)
    ols_r2_full = float(_m2.rsquared)
    ols_n = int(_m1.nobs)

    def _coef_tbl(model):
        return pd.DataFrame({
            "predictor": model.params.index,
            "coef":      model.params.values.round(5),
            "std_err":   model.bse.values.round(5),
            "t":         model.tvalues.values.round(3),
            "p-value":   model.pvalues.values.round(5),
        })

    mo.output.append(mo.md(f"""
    ### OLS Results (n = {ols_n:,} games)

    | Model | Predictors | R² | Adj R² | ΔR² |
    |---|---|---|---|---|
    | Park only | `park_run_factor_3yr` | {ols_r2_park:.5f} | {_m1.rsquared_adj:.5f} | — |
    | Park + Schedule | + rest & TZ | {ols_r2_full:.5f} | {_m2.rsquared_adj:.5f} | **+{ols_r2_full - ols_r2_park:.5f}** |
    """))
    mo.output.append(mo.md("#### Park-only model coefficients"))
    mo.output.append(mo.ui.table(_coef_tbl(_m1)))
    mo.output.append(mo.md("#### Park + Schedule model coefficients"))
    mo.output.append(mo.ui.table(_coef_tbl(_m2)))
    return ols_r2_full, ols_r2_park


@app.cell
def _(mo):
    mo.md("""
    ## Part 4 — Stadium Run Factor Trend (Interactive)

    Select a stadium to compare its `park_run_factor_3yr` (the pre-game feature value)
    against the actual mean total runs scored at that park per season.
    """)
    return


@app.cell
def _(df, mo):
    _vc = df["venue_name"].value_counts()
    _vs = df.groupby("venue_name")["game_year"].nunique()
    _valid_venues = sorted(
        [v for v in _vc.index if _vs.get(v, 0) >= 2],
        key=lambda v: _vc.get(v, 0),
        reverse=True,
    )
    stadium_selector = mo.ui.dropdown(
        options=_valid_venues,
        value=_valid_venues[0] if _valid_venues else None,
        label="Select stadium:",
    )
    return (stadium_selector,)


@app.cell
def _(df, mo, np, plt, stadium_selector):
    plt.close("all")
    _venue = stadium_selector.value
    _vdf = df[df["venue_name"] == _venue].dropna(subset=["game_year", "total_runs"]).copy()

    if len(_vdf) >= 5:
        _by_yr = _vdf.groupby("game_year").agg(
            mean_runs=("total_runs", "mean"),
            se_runs=("total_runs", lambda x: x.std() / np.sqrt(len(x))),
            mean_prf=("park_run_factor_3yr", "mean"),
            n=("total_runs", "count"),
        ).reset_index()

        _fig, _ax1 = plt.subplots(figsize=(10, 5))
        _ax2 = _ax1.twinx()

        _ax1.errorbar(
            _by_yr["game_year"],
            _by_yr["mean_runs"],
            yerr=_by_yr["se_runs"] * 1.96,
            fmt="-o", color="#1565C0", lw=2, ms=6, capsize=4,
            label="Mean total runs (±95% CI)",
        )
        _ax2.plot(
            _by_yr["game_year"],
            _by_yr["mean_prf"],
            "--s", color="#C62828", lw=1.5, ms=5,
            label="park_run_factor_3yr",
        )
        _ax1.set_xlabel("Season")
        _ax1.set_ylabel("Mean Total Runs", color="#1565C0")
        _ax2.set_ylabel("Park Run Factor (3yr)", color="#C62828")
        _ax1.set_title(f"{_venue}: Park Run Factor vs. Actual Total Runs by Season")
        _ax1.tick_params(axis="y", labelcolor="#1565C0")
        _ax2.tick_params(axis="y", labelcolor="#C62828")
        _h1, _l1 = _ax1.get_legend_handles_labels()
        _h2, _l2 = _ax2.get_legend_handles_labels()
        _ax1.legend(_h1 + _h2, _l1 + _l2, fontsize=8, loc="upper right")
        for _, _row in _by_yr.iterrows():
            _ax1.text(
                _row["game_year"],
                float(_row["mean_runs"]) + float(_row["se_runs"]) * 2.5,
                f"n={int(_row['n'])}",
                ha="center", fontsize=7, color="#1565C0",
            )
        plt.tight_layout()
        mo.output.append(_fig)
    return


@app.cell
def _(
    anova_p,
    away_tz_p,
    home_tz_p,
    mo,
    ols_r2_full,
    ols_r2_park,
    park_p,
    park_r,
    park_rank_preserved,
    quartile_spread,
):
    _park_verdict = (
        "**Strong signal** — park factor is a statistically significant predictor with consistent "
        "rank ordering across environments."
        if abs(park_r) >= 0.10 and park_p < 0.05 and park_rank_preserved
        else "**Moderate/weak signal** — statistically significant but small effect size; "
        "rank ordering not fully preserved." if park_p < 0.05
        else "**Inconclusive** — park factor correlation not statistically significant."
    )

    _sig_schedule = [
        label for label, p in [
            ("days rest (ANOVA)", anova_p),
            ("home TZ travel (t-test)", home_tz_p),
            ("away TZ travel (t-test)", away_tz_p),
        ]
        if p < 0.05
    ]
    _schedule_verdict = (
        f"**Significant effects detected for:** {', '.join(_sig_schedule)}."
        if _sig_schedule
        else "**No statistically significant schedule effects** at p < 0.05."
    )

    _r2_delta = ols_r2_full - ols_r2_park
    _ols_verdict = (
        f"Schedule variables add **{_r2_delta:.5f}** R² over park alone "
        f"({ols_r2_park:.5f} → {ols_r2_full:.5f}). "
        + ("This is a meaningful improvement." if _r2_delta > 0.005
           else "This increment is negligible.")
    )

    _include_park     = park_p < 0.05
    _include_schedule = bool(_sig_schedule) or _r2_delta > 0.003
    _overall = (
        "Include **both** park and schedule features in the Phase 4 baseline."
        if _include_park and _include_schedule
        else "Include **park factor only** in the Phase 4 baseline; schedule features are noise at this sample size."
        if _include_park
        else "**Neither** park nor schedule features show clear signal — validate in Phase 4 ablation before including."
    )

    mo.md(f"""
    ## Phase 3 — Notebook 05 Findings and Verdict

    ### Park Run Factor
    - Pearson r with total runs: **{park_r:.4f}** (p = {park_p:.4g})
    - Q1 → Q4 mean spread: **{quartile_spread:.2f} runs** | Rank preserved: **{park_rank_preserved}**
    - {_park_verdict}

    ### Schedule Fatigue
    - {_schedule_verdict}

    ### OLS Regression
    - {_ols_verdict}

    ---

    ### Phase 4 Recommendation

    | Feature | Include in Phase 4? | Rationale |
    |---|---|---|
    | `park_run_factor_3yr` | **{"Yes" if _include_park else "Ablation only"}** | {"Significant predictor with consistent quartile ordering" if _include_park else "Not significant; verify in ablation"} |
    | `home_days_rest`, `away_days_rest` | **{"Yes" if "days rest (ANOVA)" in _sig_schedule else "Low-cost flag"}** | {"Significant ANOVA effect on total runs" if "days rest (ANOVA)" in _sig_schedule else "No significant effect; cheap to include as continuous feature"} |
    | `home_tz_changed_from_last_game` | **{"Yes" if "home TZ travel (t-test)" in _sig_schedule else "Low-cost flag"}** | {"Significant at p < 0.05" if "home TZ travel (t-test)" in _sig_schedule else "Not significant; binary flag with near-zero cost to include"} |
    | `away_tz_changed_from_last_game` | **{"Yes" if "away TZ travel (t-test)" in _sig_schedule else "Low-cost flag"}** | {"Significant at p < 0.05" if "away TZ travel (t-test)" in _sig_schedule else "Not significant; binary flag with near-zero cost to include"} |

    **Overall verdict:** {_overall}
    """)
    return


if __name__ == "__main__":
    app.run()
