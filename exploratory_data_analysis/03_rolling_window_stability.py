# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo>=0.10.0",
#   "pandas>=2.0",
#   "numpy>=1.26",
#   "matplotlib>=3.8",
#   "seaborn>=0.13",
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

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.dpi": 120,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
    })
    return mo, np, pd, plt


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
            f.home_games_played,
            f.away_games_played,
            f.home_off_woba_7d,  f.home_off_woba_14d,  f.home_off_woba_30d,  f.home_off_woba_std,
            f.away_off_woba_7d,  f.away_off_woba_14d,  f.away_off_woba_30d,  f.away_off_woba_std,
            f.home_pit_xwoba_against_7d,  f.home_pit_xwoba_against_14d,
            f.home_pit_xwoba_against_30d, f.home_pit_xwoba_against_std,
            f.away_pit_xwoba_against_7d,  f.away_pit_xwoba_against_14d,
            f.away_pit_xwoba_against_30d, f.away_pit_xwoba_against_std,
            f.home_starter_k_pct_7d,  f.home_starter_k_pct_14d,
            f.home_starter_k_pct_30d, f.home_starter_k_pct_std,
            f.away_starter_k_pct_7d,  f.away_starter_k_pct_14d,
            f.away_starter_k_pct_30d, f.away_starter_k_pct_std,
            f.home_starter_xwoba_against_7d,  f.home_starter_xwoba_against_14d,
            f.home_starter_xwoba_against_30d, f.home_starter_xwoba_against_std,
            f.away_starter_xwoba_against_7d,  f.away_starter_xwoba_against_14d,
            f.away_starter_xwoba_against_30d, f.away_starter_xwoba_against_std,
            g.home_final_score + g.away_final_score AS total_runs,
            g.run_differential,
            g.home_team_won::integer                 AS home_win
        FROM baseball_data.betting_features.feature_pregame_game_features f
        JOIN baseball_data.betting.mart_game_results g ON g.game_pk = f.game_pk
        WHERE f.has_full_data = true
          AND f.game_year BETWEEN 2016 AND 2025
          AND f.game_year != 2020
        ORDER BY f.game_pk
    """)
    df_raw = pd.DataFrame(_cur.fetchall(), columns=[col[0].lower() for col in _cur.description])
    _cur.close()
    _conn.close()
    for _col in df_raw.select_dtypes(include="object").columns:
        try:
            df_raw[_col] = pd.to_numeric(df_raw[_col])
        except (ValueError, TypeError):
            pass
    return (df_raw,)


@app.cell
def _(df_raw):
    WINDOWS = ["7d", "14d", "30d", "std"]
    WINDOW_LABELS = {
        "7d":  "7-day",
        "14d": "14-day",
        "30d": "30-day",
        "std": "Season-to-date",
    }

    # For each family × window: (home_column, away_column)
    FEATURE_FAMILIES = {
        "Team Off wOBA": {
            w: (f"home_off_woba_{w}", f"away_off_woba_{w}") for w in WINDOWS
        },
        "Team Pit xwOBA": {
            w: (f"home_pit_xwoba_against_{w}", f"away_pit_xwoba_against_{w}") for w in WINDOWS
        },
        "Starter K%": {
            w: (f"home_starter_k_pct_{w}", f"away_starter_k_pct_{w}") for w in WINDOWS
        },
        "Starter xwOBA": {
            w: (f"home_starter_xwoba_against_{w}", f"away_starter_xwoba_against_{w}") for w in WINDOWS
        },
    }

    TARGETS = {
        "Total Runs":       "total_runs",
        "Run Differential": "run_differential",
        "Home Win":         "home_win",
    }

    df = df_raw.copy()
    df["min_games_played"] = df[["home_games_played", "away_games_played"]].min(axis=1)
    return FEATURE_FAMILIES, TARGETS, WINDOWS, WINDOW_LABELS, df


@app.cell
def _(FEATURE_FAMILIES, TARGETS, WINDOWS, df, pd):
    _rows = []
    for _family, _fam_windows in FEATURE_FAMILIES.items():
        for _w in WINDOWS:
            _hcol, _acol = _fam_windows[_w]
            _mask = df[_hcol].notna() & df[_acol].notna()
            _sub  = df[_mask]
            if len(_sub) < 200:
                continue
            # combined (symmetric): avg of home + away → predicts total runs level
            _combined  = (_sub[_hcol] + _sub[_acol]) / 2.0
            # advantage (asymmetric): home − away → predicts run differential / win
            _advantage = _sub[_hcol] - _sub[_acol]
            for _tgt_label, _tgt_col in TARGETS.items():
                _feat = _combined if _tgt_label == "Total Runs" else _advantage
                _r = _feat.corr(_sub[_tgt_col])
                _rows.append({
                    "family": _family,
                    "window": _w,
                    "target": _tgt_label,
                    "r":      _r,
                    "abs_r":  abs(_r) if pd.notna(_r) else float("nan"),
                    "n":      len(_sub),
                })
    corr_df = pd.DataFrame(_rows)
    return (corr_df,)


@app.cell
def _(FEATURE_FAMILIES, TARGETS, df, pd):
    _df2 = df.copy()
    _df2["gp_bucket"] = pd.cut(
        _df2["min_games_played"],
        bins=[0, 10, 30, 200],
        labels=["0–10 games", "10–30 games", "30+ games"],
        right=False,
    )

    _rows = []
    for _family, _fam_windows in FEATURE_FAMILIES.items():
        # Use the 30-day window: long enough to be signal, short enough to show early-season effects
        _hcol, _acol = _fam_windows["30d"]
        for _bucket, _bdf in _df2.groupby("gp_bucket", observed=True):
            _mask = _bdf[_hcol].notna() & _bdf[_acol].notna()
            _sub  = _bdf[_mask]
            if len(_sub) < 50:
                continue
            _combined  = (_sub[_hcol] + _sub[_acol]) / 2.0
            _advantage = _sub[_hcol] - _sub[_acol]
            for _tgt_label, _tgt_col in TARGETS.items():
                _feat = _combined if _tgt_label == "Total Runs" else _advantage
                _r = _feat.corr(_sub[_tgt_col])
                _rows.append({
                    "family": _family,
                    "bucket": str(_bucket),
                    "target": _tgt_label,
                    "abs_r":  abs(_r) if pd.notna(_r) else float("nan"),
                    "n":      len(_sub),
                })

    bucket_df = pd.DataFrame(_rows)
    bucket_summary = (
        bucket_df
        .groupby(["bucket", "target"])["abs_r"]
        .mean()
        .reset_index()
        .rename(columns={"abs_r": "mean_abs_r"})
    )
    return (bucket_summary,)


@app.cell
def _():
    return


@app.cell
def _(WINDOW_LABELS, corr_df, mo, plt):
    plt.close("all")

    _WINDOW_ORDER = ["7d", "14d", "30d", "std"]
    _x_labels     = [WINDOW_LABELS[w] for w in _WINDOW_ORDER]
    _x            = list(range(len(_WINDOW_ORDER)))

    _STYLES = {
        "Team Off wOBA":  {"color": "#1565C0", "marker": "o",  "ls": "-"},
        "Team Pit xwOBA": {"color": "#C62828", "marker": "s",  "ls": "--"},
        "Starter K%":     {"color": "#2E7D32", "marker": "^",  "ls": "-."},
        "Starter xwOBA":  {"color": "#E65100", "marker": "D",  "ls": ":"},
    }

    _fig, _axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    _fig.suptitle(
        "Feature–Outcome Correlation by Rolling Window Size  (|Pearson r|)",
        fontsize=12, fontweight="bold", y=1.03,
    )

    for _ax, _tgt in zip(_axes, ["Total Runs", "Run Differential", "Home Win"]):
        _sub = corr_df[corr_df["target"] == _tgt]
        for _family, _sty in _STYLES.items():
            _vals = []
            for _w in _WINDOW_ORDER:
                _row = _sub[(_sub["family"] == _family) & (_sub["window"] == _w)]
                _vals.append(float(_row["abs_r"].values[0]) if len(_row) else float("nan"))
            _ax.plot(
                _x, _vals,
                color=_sty["color"], marker=_sty["marker"],
                linestyle=_sty["ls"], linewidth=2, markersize=7,
                label=_family,
            )
        _ax.set_title(_tgt, fontsize=11, fontweight="bold")
        _ax.set_xticks(_x)
        _ax.set_xticklabels(_x_labels, rotation=20, ha="right")
        if _ax is _axes[0]:
            _ax.set_ylabel("|Pearson r|")
        _ax.set_ylim(bottom=0)
        _ax.grid(True, alpha=0.4)

    _handles, _labels = _axes[0].get_legend_handles_labels()
    _fig.legend(
        _handles, _labels, loc="lower center", ncol=4,
        bbox_to_anchor=(0.5, -0.18), frameon=True, fontsize=9,
    )
    _fig.tight_layout()
    fig_window = _fig
    mo.output.append(fig_window)
    return


@app.cell
def _(bucket_summary, mo, np, plt):
    plt.close("all")

    _BUCKET_ORDER  = ["0–10 games", "10–30 games", "30+ games"]
    _TARGET_COLORS = {
        "Total Runs":       "#1565C0",
        "Run Differential": "#C62828",
        "Home Win":         "#2E7D32",
    }
    _width = 0.25
    _x     = np.arange(len(_BUCKET_ORDER))

    _fig2, _ax2 = plt.subplots(figsize=(9, 4.5))
    for _i, (_tgt, _color) in enumerate(_TARGET_COLORS.items()):
        _sub = (
            bucket_summary[bucket_summary["target"] == _tgt]
            .set_index("bucket")
            .reindex(_BUCKET_ORDER)
        )
        _ax2.bar(
            _x + (_i - 1) * _width,
            _sub["mean_abs_r"],
            _width,
            label=_tgt,
            color=_color,
            alpha=0.85,
            edgecolor="white",
        )

    _ax2.set_title(
        "Early-Season Stability: Mean |Pearson r| by Games Played\n"
        "(30-day rolling features · mean across 4 feature families)",
        fontsize=11, fontweight="bold",
    )
    _ax2.set_xlabel("min(home_games_played, away_games_played)", fontsize=10)
    _ax2.set_ylabel("Mean |Pearson r|", fontsize=10)
    _ax2.set_xticks(_x)
    _ax2.set_xticklabels(_BUCKET_ORDER)
    _ax2.legend(frameon=True, fontsize=9)
    _ax2.set_ylim(bottom=0)
    _ax2.grid(True, alpha=0.4, axis="y")
    _fig2.tight_layout()
    fig_bucket = _fig2
    mo.output.append(fig_bucket)
    return


@app.cell
def _(mo):
    games_slider = mo.ui.slider(
        start=0, stop=50, step=5, value=15,
        label="Minimum games played by both teams",
        show_value=True,
    )
    return (games_slider,)


@app.cell
def _(FEATURE_FAMILIES, TARGETS, WINDOWS, WINDOW_LABELS, df, games_slider, pd):
    _thresh     = games_slider.value
    _df_f       = df[df["min_games_played"] >= _thresh]
    _n_total    = len(df)
    _n_filtered = len(_df_f)
    _pct        = 100.0 * _n_filtered / _n_total if _n_total else 0.0

    _rows = []
    for _family, _fam_windows in FEATURE_FAMILIES.items():
        for _w in WINDOWS:
            _hcol, _acol = _fam_windows[_w]
            _mask = _df_f[_hcol].notna() & _df_f[_acol].notna()
            _sub  = _df_f[_mask]
            if len(_sub) < 50:
                continue
            _combined  = (_sub[_hcol] + _sub[_acol]) / 2.0
            _advantage = _sub[_hcol] - _sub[_acol]
            _row = {
                "Feature Family": _family,
                "Window":         WINDOW_LABELS[_w],
                "n":              len(_sub),
            }
            for _tgt_label, _tgt_col in TARGETS.items():
                _feat = _combined if _tgt_label == "Total Runs" else _advantage
                _r    = _feat.corr(_sub[_tgt_col])
                _row[f"|r| {_tgt_label}"] = round(abs(_r), 4) if pd.notna(_r) else None
            _rows.append(_row)

    _tbl = pd.DataFrame(_rows)
    return


@app.cell
def _(bucket_summary, corr_df, df):
    _mean_by_window = corr_df.groupby("window")["abs_r"].mean()

    def _bkt(bucket, target="Total Runs"):
        _sub = bucket_summary[
            (bucket_summary["bucket"] == bucket) &
            (bucket_summary["target"] == target)
        ]
        return float(_sub["mean_abs_r"].values[0]) if len(_sub) else float("nan")

    _early_r  = _bkt("0–10 games",  "Total Runs")
    _mid_r    = _bkt("10–30 games", "Total Runs")
    _stable_r = _bkt("30+ games",   "Total Runs")
    _pct_gain = 100.0 * (_stable_r - _early_r) / max(_early_r, 1e-9)

    _n_total  = len(df)
    _n_ge15   = int((df["min_games_played"] >= 15).sum())
    _n_ge20   = int((df["min_games_played"] >= 20).sum())
    _pct_ge15 = 100.0 * _n_ge15 / _n_total
    _pct_ge20 = 100.0 * _n_ge20 / _n_total
    return


if __name__ == "__main__":
    app.run()
