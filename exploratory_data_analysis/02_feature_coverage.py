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
    return mo, pd, plt, sns


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
        SELECT *
        FROM baseball_data.betting_features.feature_pregame_game_features
        WHERE game_year BETWEEN 2015 AND 2026
        ORDER BY game_date
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
    # Exclude pure identifiers from the null analysis
    _ID_COLS = {"game_pk", "game_date", "game_year", "home_team", "away_team"}
    feature_cols = [c for c in df_raw.columns if c not in _ID_COLS]

    _null_ind = df_raw[feature_cols].isnull().astype(float)
    _null_ind["game_year"] = df_raw["game_year"].values
    null_rates = _null_ind.groupby("game_year")[feature_cols].mean() * 100
    # null_rates: index=game_year, columns=feature_col, values=% null

    all_years = sorted(df_raw["game_year"].unique().tolist())
    complete_seasons = list(range(2016, 2026))  # 2016–2025 inclusive
    return complete_seasons, feature_cols, null_rates


@app.cell
def _(df_raw, pd):
    # Expected values from schema.yml (verified 2026-04-23)
    _EXPECTED = {
        2015: 0,    2016: 2364, 2017: 2288, 2018: 1953, 2019: 2363,
        2020: 801,  2021: 2320, 2022: 2377, 2023: 2371, 2024: 2369,
        2025: 2228, 2026: 351,
    }
    _actual = (
        df_raw.groupby("game_year")["has_full_data"]
        .sum()
        .astype(int)
    )
    coverage_df = pd.DataFrame({
        "Season":              sorted(_EXPECTED.keys()),
        "Expected (schema)":   [_EXPECTED[y] for y in sorted(_EXPECTED.keys())],
        "Actual":              [int(_actual.get(y, 0)) for y in sorted(_EXPECTED.keys())],
    })
    coverage_df["Δ"] = coverage_df["Actual"] - coverage_df["Expected (schema)"]
    coverage_df["Status"] = coverage_df["Δ"].apply(
        lambda d: "✓ match" if d == 0 else f"DRIFT {d:+d}"
    )
    return


@app.cell
def _(feature_cols):
    def _match(predicates):
        result = []
        for c in feature_cols:
            for pred in predicates:
                if (callable(pred) and pred(c)) or (isinstance(pred, str) and c == pred):
                    result.append(c)
                    break
        return result

    COLUMN_GROUPS = {
        "All features (group summary)": None,
        "Home lineup": _match([
            lambda c: c.startswith("home_") and (
                "avg_" in c
                or c in ("home_has_full_lineup", "home_lhb_count", "home_rhb_count")
            ),
        ]),
        "Away lineup": _match([
            lambda c: c.startswith("away_") and (
                "avg_" in c
                or c in ("away_has_full_lineup", "away_lhb_count", "away_rhb_count")
            ),
        ]),
        "Home starter": _match([lambda c: c.startswith("home_starter_")]),
        "Away starter": _match([lambda c: c.startswith("away_starter_")]),
        "Home team": _match([
            lambda c: c.startswith("home_") and (
                c.startswith("home_off_")
                or c.startswith("home_pit_")
                or c.startswith("home_vs_")
                or c in (
                    "home_wins", "home_losses", "home_games_played",
                    "home_win_pct", "home_games_back",
                    "home_streak_direction", "home_streak_length",
                )
            ),
        ]),
        "Away team": _match([
            lambda c: c.startswith("away_") and (
                c.startswith("away_off_")
                or c.startswith("away_pit_")
                or c.startswith("away_vs_")
                or c in (
                    "away_wins", "away_losses", "away_games_played",
                    "away_win_pct", "away_games_back",
                    "away_streak_direction", "away_streak_length",
                )
            ),
        ]),
        "Home bullpen": _match([
            lambda c: c.startswith("home_") and any(
                c.startswith(p) for p in (
                    "home_bp_", "home_bullpen_", "home_pitchers_used_",
                    "home_reliever_", "home_high_leverage_", "home_closer_",
                )
            ),
        ]),
        "Away bullpen": _match([
            lambda c: c.startswith("away_") and any(
                c.startswith(p) for p in (
                    "away_bp_", "away_bullpen_", "away_pitchers_used_",
                    "away_reliever_", "away_high_leverage_", "away_closer_",
                )
            ),
        ]),
        "Home schedule": _match([lambda c: c in (
            "home_days_rest", "home_games_last_7d", "home_games_last_14d",
            "home_consecutive_home_games", "home_consecutive_away_games",
            "home_tz_changed_from_last_game",
        )]),
        "Away schedule": _match([lambda c: c in (
            "away_days_rest", "away_games_last_7d", "away_games_last_14d",
            "away_consecutive_home_games", "away_consecutive_away_games",
            "away_tz_changed_from_last_game",
        )]),
        "Park": _match([lambda c: c in (
            "venue_id", "venue_name", "elevation_ft", "turf_type", "roof_type",
            "left_line_ft", "left_ft", "left_center_ft", "center_ft",
            "right_center_ft", "right_line_ft",
            "runs_per_game_at_park", "park_run_factor_3yr",
        )]),
        "Odds": _match([
            lambda c: (
                c.startswith("odds_")
                or "moneyline" in c
                or "implied_prob" in c
                or c.endswith("_vig")
                or c in ("total_line", "over_american", "under_american")
            ),
        ]),
        "Flags": _match([lambda c: c in ("has_full_data", "has_odds")]),
    }
    return (COLUMN_GROUPS,)


@app.cell
def _(complete_seasons, feature_cols, null_rates, pd):
    _null_complete = null_rates.loc[
        null_rates.index.isin(complete_seasons), feature_cols
    ]
    _max_null = _null_complete.max(axis=0)
    flagged_cols = sorted(_max_null[_max_null > 5].index.tolist())

    flagged_df = pd.DataFrame({
        "Column":                    flagged_cols,
        "Max null % (2016–2025)":    [round(_max_null[c], 1) for c in flagged_cols],
        "Seasons above 5% thresh":   [
            int((_null_complete[c] > 5).sum()) for c in flagged_cols
        ],
    }).sort_values("Max null % (2016–2025)", ascending=False).reset_index(drop=True)
    return (flagged_cols,)


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell
def _(flagged_cols):
    _n = len(flagged_cols)
    return


@app.cell
def _(COLUMN_GROUPS, mo):
    group_selector = mo.ui.dropdown(
        options=list(COLUMN_GROUPS.keys()),
        value="All features (group summary)",
        label="Filter by feature group:",
    )
    return (group_selector,)


@app.cell
def _(COLUMN_GROUPS, group_selector, null_rates, pd):
    _selected = group_selector.value
    _cols = COLUMN_GROUPS[_selected]

    if _cols is None:
        # Summary view: one row per group, mean null rate across that group's columns
        _group_means = {}
        for _g, _gcols in COLUMN_GROUPS.items():
            if _gcols is None or len(_gcols) == 0:
                continue
            _valid = [c for c in _gcols if c in null_rates.columns]
            if _valid:
                _group_means[_g] = null_rates[_valid].mean(axis=1)
        null_rates_filtered = pd.DataFrame(_group_means, index=null_rates.index)
        selected_group = _selected
    else:
        _valid_cols = [c for c in _cols if c in null_rates.columns]
        null_rates_filtered = null_rates[_valid_cols].copy()
        selected_group = _selected
    return null_rates_filtered, selected_group


@app.cell
def _(mo, null_rates_filtered, plt, selected_group, sns):
    plt.close("all")

    _n_rows = len(null_rates_filtered.columns)
    _n_years = len(null_rates_filtered.index)
    _annotate = _n_rows <= 25
    _fig_h = max(4, min(_n_rows * 0.38 + 1.5, 32))

    fig_heatmap, _ax = plt.subplots(figsize=(max(8, _n_years * 0.75), _fig_h))

    sns.heatmap(
        null_rates_filtered.T,
        ax=_ax,
        cmap="YlOrRd",
        vmin=0,
        vmax=100,
        annot=_annotate,
        fmt=".0f",
        annot_kws={"size": 7} if _annotate else {},
        linewidths=0.4,
        linecolor="white",
        cbar_kws={"label": "% null", "shrink": 0.55},
    )
    _ax.set_title(
        f"Null rate (%) by season — {selected_group}",
        fontsize=12,
        pad=12,
    )
    _ax.set_xlabel("Season", labelpad=8)
    _ax.set_ylabel("")
    _ax.tick_params(axis="y", labelsize=8 if _n_rows > 20 else 9)
    _ax.tick_params(axis="x", labelsize=9)
    plt.tight_layout()
    mo.output.append(fig_heatmap)
    return


@app.cell
def _(complete_seasons, flagged_cols, null_rates):
    _odds_cols = [c for c in flagged_cols if "moneyline" in c or "implied_prob" in c or c.endswith("_vig") or c in ("total_line", "over_american", "under_american")]
    _starter_cols = [c for c in flagged_cols if "starter" in c and ("vs_lhb" in c or "vs_rhb" in c or "vs_lhp" in c or "vs_rhp" in c)]
    _park_cols = [c for c in flagged_cols if c in ("runs_per_game_at_park", "park_run_factor_3yr")]
    _other_cols = [c for c in flagged_cols if c not in _odds_cols + _starter_cols + _park_cols]

    _null_complete = null_rates.loc[null_rates.index.isin(complete_seasons)]

    def _max_null(col):
        return f"{_null_complete[col].max():.1f}%" if col in _null_complete.columns else "n/a"

    _starter_example = _starter_cols[0] if _starter_cols else "n/a"
    _starter_max = _max_null(_starter_example) if _starter_cols else "n/a"
    _park_max = _max_null(_park_cols[0]) if _park_cols else "n/a"
    return


if __name__ == "__main__":
    app.run()
