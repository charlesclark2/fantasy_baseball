# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo>=0.10.0",
#   "pandas>=2.0",
#   "numpy>=1.26",
#   "matplotlib>=3.8",
#   "scipy>=1.11",
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

    return (mo,)


@app.cell
def _():
    import pandas as pd
    import numpy as np
    import matplotlib
    import matplotlib.pyplot as plt
    from scipy import stats as scipy_stats

    matplotlib.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.dpi": 130,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
    })
    return np, pd, plt, scipy_stats


@app.cell
def _(mo):
    mo.md("""
    # 01 — Target Variable Analysis
    """)
    return


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
            f.game_date,
            f.game_year,
            f.has_full_data,
            r.home_final_score,
            r.away_final_score,
            r.run_differential,
            r.home_team_won,
            r.is_extra_innings
        FROM baseball_data.betting_features.feature_pregame_game_features f
        JOIN baseball_data.betting.mart_game_results r ON r.game_pk = f.game_pk
        WHERE r.game_type = 'R'
          AND f.game_year BETWEEN 2016 AND 2025
        ORDER BY f.game_date
    """)
    df_raw = pd.DataFrame(_cur.fetchall(), columns=[col[0].lower() for col in _cur.description])
    _cur.close()
    _conn.close()
    for _col in df_raw.select_dtypes(include="object").columns:
        try:
            df_raw[_col] = pd.to_numeric(df_raw[_col])
        except (ValueError, TypeError):
            pass
    df_raw["total_runs"] = df_raw["home_final_score"] + df_raw["away_final_score"]
    df_raw["home_win"] = df_raw["home_team_won"].astype(float)
    df_raw["era"] = df_raw["game_year"].map({
        2016: "2016–2019", 2017: "2016–2019", 2018: "2016–2019", 2019: "2016–2019",
        2020: "2020 (COVID)",
        2021: "2021–2022", 2022: "2021–2022",
        2023: "2023–2025", 2024: "2023–2025", 2025: "2023–2025",
    })
    df_clean = df_raw[df_raw["has_full_data"].isin([True, 1, 1.0])].copy()
    return df_clean, df_raw


@app.cell
def _(df_clean, df_raw, np, pd):
    def _agg(df):
        g = df.groupby("game_year")
        return pd.DataFrame({
            "n_games":        g["total_runs"].count(),
            "avg_total_runs": g["total_runs"].mean().round(2),
            "std_total_runs": g["total_runs"].std().round(2),
            "avg_run_diff":   g["run_differential"].mean().round(2),
            "std_run_diff":   g["run_differential"].std().round(2),
            "home_win_rate":  g["home_win"].mean().round(4),
        }).reset_index().sort_values("game_year")

    season_stats     = _agg(df_clean)
    season_stats_all = _agg(df_raw)

    overall_mean_runs  = df_clean["total_runs"].mean()
    overall_mae_naive  = (df_clean["total_runs"] - overall_mean_runs).abs().mean()
    overall_rmse_naive = np.sqrt(((df_clean["total_runs"] - overall_mean_runs) ** 2).mean())
    return (
        overall_mae_naive,
        overall_mean_runs,
        overall_rmse_naive,
        season_stats,
        season_stats_all,
    )


@app.cell
def _(mo):
    mo.md("""
    ## 1 — Total Runs Distribution
    """)
    return


@app.cell
def _(df_clean, mo, np, plt, scipy_stats):
    plt.close("all")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))

    ax = axes[0]
    ax.hist(
        df_clean["total_runs"], bins=np.arange(0.5, 39.5, 1), density=True,
        color="#4C72B0", alpha=0.72, edgecolor="white", linewidth=0.3,
        label="Observed (has_full_data)",
    )
    mu, sigma = df_clean["total_runs"].mean(), df_clean["total_runs"].std()
    x = np.linspace(0, 38, 400)
    ax.plot(x, scipy_stats.norm.pdf(x, mu, sigma), "r-", lw=1.8,
            label=f"Normal(μ={mu:.2f}, σ={sigma:.2f})")
    ax.axvline(mu, color="red", lw=1.0, ls="--", alpha=0.5)
    ax.set_xlabel("Total Runs Scored")
    ax.set_ylabel("Density")
    ax.set_title("Total Runs — 2016–2025 (has_full_data)")
    ax.legend()
    ax.set_xlim(0, 33)
    ax.text(0.97, 0.93, f"n = {len(df_clean):,}", transform=ax.transAxes,
            ha="right", va="top", fontsize=8, color="gray")

    ax2 = axes[1]
    era_order  = ["2016–2019", "2020 (COVID)", "2021–2022", "2023–2025"]
    era_colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]
    era_data   = [df_clean.loc[df_clean["era"] == e, "total_runs"].values for e in era_order]
    bp = ax2.boxplot(
        era_data, tick_labels=era_order, patch_artist=True,
        medianprops=dict(color="white", lw=2),
        flierprops=dict(marker=".", markersize=2, alpha=0.25),
        whiskerprops=dict(lw=1.2),
        capprops=dict(lw=1.2),
    )
    for patch, color in zip(bp["boxes"], era_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.72)
    ax2.set_ylabel("Total Runs Scored")
    ax2.set_title("Total Runs by Era")
    ax2.tick_params(axis="x", rotation=12)

    plt.tight_layout()
    mo.output.append(fig)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2 — Season-by-Season Trends
    """)
    return


@app.cell
def _(mo, plt, season_stats, season_stats_all):
    plt.close("all")
    fig2, ax3 = plt.subplots(figsize=(11, 4.8))

    years     = season_stats["game_year"].values
    means     = season_stats["avg_total_runs"].values
    stds      = season_stats["std_total_runs"].values
    means_all = season_stats_all["avg_total_runs"].values

    ax3.bar(years, means, color="#4C72B0", alpha=0.72, width=0.4,
            label="has_full_data", zorder=3)
    ax3.errorbar(years, means, yerr=stds, fmt="none",
                 color="#4C72B0", capsize=5, lw=1.5, zorder=4)
    ax3.plot(years, means_all, "o--", color="#DD8452", lw=1.3, ms=5,
             label="All games", zorder=5)

    for yr, m, s in zip(years, means, stds):
        ax3.text(yr, m + s + 0.15, f"{m:.2f}", ha="center", va="bottom", fontsize=7.5)

    period_mean = means.mean()
    ax3.axhline(period_mean, color="gray", lw=1.0, ls=":",
                label=f"Period mean ({period_mean:.2f})")
    ax3.set_xticks(years)
    ax3.set_xticklabels(years, rotation=30)
    ax3.set_xlabel("Season")
    ax3.set_ylabel("Avg Total Runs per Game")
    ax3.set_title("Total Runs per Game by Season — Mean ± 1 SD")
    ax3.set_ylim(0, 16)
    ax3.legend()

    ax3.annotate("Juiced ball", xy=(2019, 9.65), xytext=(2019, 13.8),
                 arrowprops=dict(arrowstyle="->", color="gray", lw=1), fontsize=8, ha="center")
    ax3.annotate("Dead ball", xy=(2022, 8.57), xytext=(2021.2, 6.3),
                 arrowprops=dict(arrowstyle="->", color="gray", lw=1), fontsize=8, ha="center")
    ax3.annotate("Pitch clock\n+ shift ban", xy=(2023, 9.21), xytext=(2024.2, 13.2),
                 arrowprops=dict(arrowstyle="->", color="gray", lw=1), fontsize=8, ha="center")

    plt.tight_layout()
    mo.output.append(fig2)
    return


@app.cell
def _():
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3 — Run Differential
    """)
    return


@app.cell
def _(df_clean, mo, np, plt, scipy_stats):
    plt.close("all")
    fig3, axes3 = plt.subplots(1, 2, figsize=(13, 4.8))

    ax4 = axes3[0]
    ax4.hist(
        df_clean["run_differential"], bins=np.arange(-25.5, 26.5, 1),
        density=True, color="#55A868", alpha=0.72, edgecolor="white", linewidth=0.3,
        label="Observed",
    )
    mu2, sigma2 = df_clean["run_differential"].mean(), df_clean["run_differential"].std()
    x2 = np.linspace(-27, 27, 500)
    ax4.plot(x2, scipy_stats.norm.pdf(x2, mu2, sigma2), "r-", lw=1.8,
             label=f"Normal(μ={mu2:.2f}, σ={sigma2:.2f})")
    ax4.axvline(0, color="black", lw=1.0, ls="--", alpha=0.5, label="0 (break-even)")
    ax4.set_xlabel("Run Differential (Home − Away)")
    ax4.set_ylabel("Density")
    ax4.set_title("Run Differential Distribution — 2016–2025")
    ax4.legend()

    skew = scipy_stats.skew(df_clean["run_differential"].dropna())
    kurt = scipy_stats.kurtosis(df_clean["run_differential"].dropna())
    ax4.text(
        0.03, 0.93,
        f"Skew: {skew:.3f}\nExcess kurtosis: {kurt:.3f}",
        transform=ax4.transAxes, va="top", fontsize=8,
        bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
    )

    ax5 = axes3[1]
    ss = (
        df_clean.groupby("game_year")["run_differential"]
        .agg(["mean", "std"])
        .reset_index()
    )
    ax5.bar(ss["game_year"], ss["mean"], color="#55A868", alpha=0.72, width=0.5, zorder=3)
    ax5.errorbar(ss["game_year"], ss["mean"], yerr=ss["std"],
                 fmt="none", color="#55A868", capsize=5, lw=1.5, zorder=4)
    ax5.axhline(0, color="black", lw=1.0, ls="--", alpha=0.5, label="0")
    ax5.set_xlabel("Season")
    ax5.set_ylabel("Avg Run Differential (Home − Away)")
    ax5.set_title("Avg Run Differential by Season — Mean ± 1 SD")
    ax5.set_xticks(ss["game_year"])
    ax5.set_xticklabels(ss["game_year"], rotation=30)
    ax5.legend()

    plt.tight_layout()
    mo.output.append(fig3)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4 — Home Win Rate
    """)
    return


@app.cell
def _(mo, plt, season_stats, season_stats_all):
    plt.close("all")
    fig4, ax6 = plt.subplots(figsize=(10, 4.5))

    years2  = season_stats["game_year"].values
    hw      = season_stats["home_win_rate"].values
    hw_all  = season_stats_all["home_win_rate"].values

    ax6.bar(years2, hw, color="#C44E52", alpha=0.72, width=0.4,
            label="has_full_data", zorder=3)
    ax6.plot(years2, hw_all, "o--", color="#DD8452", lw=1.3, ms=5,
             label="All games", zorder=5)
    ax6.axhline(0.500, color="black", lw=1.0, ls=":", alpha=0.5, label="50% (coin flip)")
    ax6.axhline(hw.mean(), color="gray", lw=1.0, ls="--",
                label=f"Period mean ({hw.mean():.3f})")

    for yr2, rate in zip(years2, hw):
        ax6.text(yr2, rate + 0.003, f"{rate:.3f}", ha="center", va="bottom", fontsize=8)

    ax6.set_ylim(0.48, 0.58)
    ax6.set_xticks(years2)
    ax6.set_xticklabels(years2, rotation=30)
    ax6.set_xlabel("Season")
    ax6.set_ylabel("Home Win Rate")
    ax6.set_title("Home Win Rate by Season")
    ax6.legend()

    plt.tight_layout()
    mo.output.append(fig4)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5 — Naive Baseline Error
    """)
    return


@app.cell
def _(
    df_clean,
    mo,
    np,
    overall_mae_naive,
    overall_mean_runs,
    overall_rmse_naive,
    pd,
    plt,
    season_stats,
):
    plt.close("all")
    fig5, axes5 = plt.subplots(1, 2, figsize=(13, 4.8))

    ax7 = axes5[0]
    errors = df_clean["total_runs"] - overall_mean_runs
    ax7.hist(
        errors, bins=np.arange(-25, 30, 1), density=True,
        color="#8172B3", alpha=0.72, edgecolor="white", linewidth=0.3,
        label="Actual − Global Mean",
    )
    ax7.axvline(0, color="red", lw=1.2, ls="--")
    ax7.set_xlabel("Prediction Error (runs)")
    ax7.set_ylabel("Density")
    ax7.set_title(f"Naive Global-Mean Baseline Error\n(predict {overall_mean_runs:.2f} runs for every game)")
    ax7.text(
        0.97, 0.93,
        f"MAE:  {overall_mae_naive:.2f} runs\nRMSE: {overall_rmse_naive:.2f} runs",
        transform=ax7.transAxes, ha="right", va="top", fontsize=9,
        bbox=dict(facecolor="white", alpha=0.8, edgecolor="lightgray"),
    )
    ax7.legend()

    year_mean = season_stats.set_index("game_year")["avg_total_runs"].to_dict()
    years3 = sorted(year_mean.keys())[1:]

    maes_prior  = []
    maes_global = []
    for yr3 in years3:
        subset = df_clean[df_clean["game_year"] == yr3]["total_runs"]
        prior  = year_mean.get(yr3 - 1, overall_mean_runs)
        maes_prior.append((subset - prior).abs().mean())
        maes_global.append((subset - overall_mean_runs).abs().mean())

    season_baseline_maes = pd.DataFrame({
        "game_year":        years3,
        "mae_prior_season": np.round(maes_prior, 3),
        "mae_global_mean":  np.round(maes_global, 3),
    })

    ax8 = axes5[1]
    xp, wp = np.arange(len(years3)), 0.35
    ax8.bar(xp - wp / 2, maes_prior, width=wp, color="#8172B3", alpha=0.72,
            label="Prior-season mean")
    ax8.bar(xp + wp / 2, maes_global, width=wp, color="#64B5CD", alpha=0.72,
            label="Global mean (2016–2025)")
    ax8.set_xticks(xp)
    ax8.set_xticklabels(years3, rotation=30)
    ax8.set_ylabel("MAE (runs)")
    ax8.set_title("Per-Season Naive Baseline MAE\n(any useful model must beat these numbers)")
    ax8.legend()
    ax8.axhline(overall_mae_naive, color="gray", lw=1.0, ls=":", alpha=0.8)

    plt.tight_layout()
    mo.output.append(fig5)
    return (season_baseline_maes,)


@app.cell
def _(mo, season_baseline_maes, season_stats):
    min_runs  = season_stats["avg_total_runs"].min()
    max_runs  = season_stats["avg_total_runs"].max()
    min_yr    = int(season_stats.loc[season_stats["avg_total_runs"].idxmin(), "game_year"])
    max_yr    = int(season_stats.loc[season_stats["avg_total_runs"].idxmax(), "game_year"])
    hw_mean   = season_stats["home_win_rate"].mean()
    hw_min    = season_stats["home_win_rate"].min()
    hw_max    = season_stats["home_win_rate"].max()
    mae_prior = season_baseline_maes["mae_prior_season"].mean()
    mo.md(f"""
    ## Key Findings

    - **Total runs** range from {min_runs:.2f} (in {min_yr}) to {max_runs:.2f} (in {max_yr}) — a {max_runs - min_runs:.2f}-run spread across seasons.
    - **Home win rate** averages {hw_mean:.3f} (range {hw_min:.3f}–{hw_max:.3f}) — declining in recent seasons.
    - **Naive MAE** (prior-season mean): {mae_prior:.2f} runs — any useful model must beat this.
    """)
    return


if __name__ == "__main__":
    app.run()
