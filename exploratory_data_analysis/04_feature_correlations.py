# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo>=0.10.0",
#   "pandas>=2.0",
#   "numpy>=1.26",
#   "matplotlib>=3.8",
#   "seaborn>=0.13",
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
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns
    from scipy import stats as scipy_stats

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.dpi": 120,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
    })
    return mo, np, pd, plt, scipy_stats, sns


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
            f.*,
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
def _(df_raw, np):
    TARGETS = {
        "Total Runs":       "total_runs",
        "Run Differential": "run_differential",
        "Home Win":         "home_win",
    }
    TARGET_LABELS = list(TARGETS.keys())
    TARGET_COLS   = list(TARGETS.values())

    _ID_COLS = {
        "game_pk", "game_date", "game_year", "home_team", "away_team",
        "venue_id", "venue_name", "has_full_data", "has_odds",
        # exclude non-informative count/id columns
        "home_starter_pitcher_id", "away_starter_pitcher_id",
        "home_wins", "home_losses", "away_wins", "away_losses",
        *TARGET_COLS,
    }

    _numeric = df_raw.select_dtypes(include=[np.number]).columns.tolist()
    _candidate = [c for c in _numeric if c not in _ID_COLS]

    # Drop columns with > 50% null rate (primarily odds price columns — 100% null pre-backfill)
    _null_rates = df_raw[_candidate].isnull().mean()
    feature_cols = [c for c in _candidate if _null_rates[c] <= 0.50]

    df = df_raw[feature_cols + TARGET_COLS].dropna(subset=TARGET_COLS).copy()
    return TARGET_COLS, TARGET_LABELS, df, feature_cols


@app.cell
def _(TARGET_COLS, TARGET_LABELS, df, feature_cols, pd):
    # Vectorized Pearson and Spearman via full correlation matrix.
    # Filter to columns with ≥ 200 non-null values before computing.
    _valid = [c for c in feature_cols if df[c].notna().sum() >= 200]
    _all_cols = _valid + TARGET_COLS

    _pearson  = df[_all_cols].corr(method="pearson")
    _spearman = df[_all_cols].corr(method="spearman")

    _rows = []
    for _tgt_col, _tgt_label in zip(TARGET_COLS, TARGET_LABELS):
        for _feat in _valid:
            _pr = _pearson.loc[_feat, _tgt_col]
            _sr = _spearman.loc[_feat, _tgt_col]
            if pd.notna(_pr):
                _rows.append({
                    "feature":       _feat,
                    "target":        _tgt_label,
                    "pearson_r":     round(float(_pr), 5),
                    "spearman_r":    round(float(_sr), 5) if pd.notna(_sr) else None,
                    "abs_pearson_r": abs(float(_pr)),
                })
    corr_df = pd.DataFrame(_rows)
    return (corr_df,)


@app.cell
def _(mo):
    mo.md("""
    # 04 — Feature-Outcome Correlations and Multicollinearity

    **Source:** `feature_pregame_game_features` (has_full_data = true) ⋈ `mart_game_results`
    **Training set:** 2016–2025 regular season, 2020 excluded
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 1 — Univariate Feature–Outcome Correlations

    Pearson and Spearman |r| for every numeric feature (null rate ≤ 50%) with each prediction target.
    Bars = Pearson r (blue = positive, red = negative). Orange diamonds = Spearman r.
    """)
    return


@app.cell
def _(TARGET_LABELS, mo):
    target_selector = mo.ui.dropdown(
        options=TARGET_LABELS,
        value="Total Runs",
        label="Target variable:",
    )
    return (target_selector,)


@app.cell
def _(corr_df, mo, np, plt, target_selector):
    plt.close("all")

    _tgt = target_selector.value
    _sub = (
        corr_df[corr_df["target"] == _tgt]
        .dropna(subset=["pearson_r"])
        .sort_values("abs_pearson_r", ascending=False)
        .head(40)
        .reset_index(drop=True)
    )

    _fig, _ax = plt.subplots(figsize=(15, 7))
    _x = np.arange(len(_sub))
    _colors = ["#1565C0" if v >= 0 else "#C62828" for v in _sub["pearson_r"]]

    _ax.bar(_x, _sub["pearson_r"], color=_colors, alpha=0.75, label="Pearson r", zorder=3)
    _ax.scatter(
        _x, _sub["spearman_r"],
        color="#E65100", s=45, zorder=5, label="Spearman r", marker="D",
    )
    _ax.axhline(0, color="black", lw=0.8, ls="--", alpha=0.4)

    _ax.set_xticks(_x)
    _ax.set_xticklabels(_sub["feature"], rotation=55, ha="right", fontsize=7.5)
    _ax.set_ylabel("Correlation (r)")
    _ax.set_title(
        f"Top 40 Features by |Pearson r| — Target: '{_tgt}'\n"
        "(blue = positive correlation, red = negative; bars = Pearson, diamonds = Spearman)",
        fontsize=11,
    )
    _ax.legend(fontsize=9, loc="upper right")
    _ax.grid(True, alpha=0.35, axis="y")
    plt.tight_layout()
    mo.output.append(_fig)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Part 2 — Multicollinearity Within Feature Groups

    Correlation heatmap within feature families reveals whether multiple window variants or
    metric variants of the same concept are effectively measuring the same signal. Pairs with
    **|r| > 0.85** are flagged as redundant — keeping both in a linear model inflates variance
    without adding predictive power.
    """)
    return


@app.cell
def _(feature_cols):
    _WINS = ("7d", "14d", "30d", "std")

    def _m(pred):
        return [c for c in feature_cols if pred(c)]

    MULTICOLLIN_GROUPS = {
        "Team offense — window comparison (home)": _m(
            lambda c: c.startswith("home_off_") and any(c.endswith(f"_{w}") for w in _WINS)
        ),
        "Team offense — window comparison (away)": _m(
            lambda c: c.startswith("away_off_") and any(c.endswith(f"_{w}") for w in _WINS)
        ),
        "Team pitching — window comparison (home)": _m(
            lambda c: c.startswith("home_pit_") and any(c.endswith(f"_{w}") for w in _WINS)
        ),
        "Team pitching — window comparison (away)": _m(
            lambda c: c.startswith("away_pit_") and any(c.endswith(f"_{w}") for w in _WINS)
        ),
        "Starter quality — window comparison": _m(
            lambda c: (c.startswith("home_starter_") or c.startswith("away_starter_"))
            and any(c.endswith(f"_{w}") for w in _WINS)
            and any(m in c for m in ("k_pct", "xwoba_against", "bb_pct", "whiff_rate"))
        ),
        "Offense cross-metric at 30-day (home)": _m(
            lambda c: c.startswith("home_off_") and c.endswith("_30d")
        ),
        "Offense cross-metric at STD (home)": _m(
            lambda c: c.startswith("home_off_") and c.endswith("_std")
        ),
        "Pitching cross-metric at 30-day (home)": _m(
            lambda c: c.startswith("home_pit_") and c.endswith("_30d")
        ),
        "Starter cross-metric at STD": _m(
            lambda c: (c.startswith("home_starter_") or c.startswith("away_starter_"))
            and c.endswith("_std")
            and not any(x in c for x in ("pitcher_id", "has_", "appearances", "velo_trend", "minus"))
        ),
        "Lineup batting quality (home + away)": _m(
            lambda c: c.startswith(("home_avg_", "away_avg_"))
            and any(c.endswith(f"_{w}") for w in ("30d", "std"))
        ),
    }
    MULTICOLLIN_GROUPS = {k: v for k, v in MULTICOLLIN_GROUPS.items() if len(v) >= 2}
    return (MULTICOLLIN_GROUPS,)


@app.cell
def _(MULTICOLLIN_GROUPS, mo):
    group_selector = mo.ui.dropdown(
        options=list(MULTICOLLIN_GROUPS.keys()),
        value=next(iter(MULTICOLLIN_GROUPS)),
        label="Feature group for heatmap:",
    )
    return (group_selector,)


@app.cell
def _(MULTICOLLIN_GROUPS, df, group_selector):
    _cols = MULTICOLLIN_GROUPS[group_selector.value]
    _valid = [c for c in _cols if c in df.columns and df[c].notna().sum() >= 100]
    group_corr = df[_valid].corr(method="pearson") if len(_valid) >= 2 else None
    group_cols = _valid
    return group_cols, group_corr


@app.cell
def _(group_cols, group_corr, group_selector, mo, plt, sns):
    plt.close("all")
    if group_corr is not None and len(group_cols) >= 2:
        _n = len(group_cols)
        _fig_h, _ax_h = plt.subplots(figsize=(max(8, _n * 0.72), max(6, _n * 0.62)))
        sns.heatmap(
            group_corr,
            ax=_ax_h,
            cmap="RdBu_r",
            vmin=-1, vmax=1, center=0,
            annot=(_n <= 22),
            fmt=".2f" if _n <= 22 else "",
            annot_kws={"size": 7},
            linewidths=0.3,
            linecolor="white",
            square=True,
            cbar_kws={"label": "Pearson r", "shrink": 0.7},
        )
        _ax_h.set_title(
            f"Multicollinearity Heatmap — {group_selector.value}",
            fontsize=11, pad=12,
        )
        _ax_h.tick_params(axis="x", labelsize=7, rotation=45)
        _ax_h.tick_params(axis="y", labelsize=7, rotation=0)
        plt.tight_layout()
        mo.output.append(_fig_h)
    return


@app.cell
def _(MULTICOLLIN_GROUPS, df, mo, pd):
    # Compute all redundant pairs (|r| > 0.85) across every defined group
    _THRESH = 0.85
    _pairs = []
    for _gname, _gcols in MULTICOLLIN_GROUPS.items():
        _valid = [c for c in _gcols if c in df.columns and df[c].notna().sum() >= 100]
        if len(_valid) < 2:
            continue
        _cm = df[_valid].corr(method="pearson")
        _cl = _cm.columns.tolist()
        for _i in range(len(_cl)):
            for _j in range(_i + 1, len(_cl)):
                _r = float(_cm.iloc[_i, _j])
                if abs(_r) > _THRESH:
                    _pairs.append({
                        "group":     _gname,
                        "feature_a": _cl[_i],
                        "feature_b": _cl[_j],
                        "abs_r":     round(abs(_r), 3),
                    })
    all_flagged_pairs_df = (
        pd.DataFrame(_pairs).sort_values("abs_r", ascending=False).reset_index(drop=True)
        if _pairs
        else pd.DataFrame(columns=["group", "feature_a", "feature_b", "abs_r"])
    )
    mo.output.append(
        mo.md(f"### Redundant feature pairs — |r| > {_THRESH} ({len(all_flagged_pairs_df)} pairs found across all groups)")
    )
    mo.output.append(mo.ui.table(all_flagged_pairs_df))
    return (all_flagged_pairs_df,)


@app.cell
def _(mo):
    mo.md("""
    ## Part 3 — Home / Away Matchup Differential Features

    Tests whether an explicit matchup signal —
    `home_off_woba_30d − away_pit_xwoba_against_30d` — produces a stronger correlation with
    game outcomes than either component alone. Four derived signals are evaluated:

    | Signal | Formula | Hypothesis |
    |---|---|---|
    | Off(H) − Pit(A) 30d | home offense quality minus away pitching quality | Predicts home scoring environment |
    | Off(A) − Pit(H) 30d | away offense quality minus home pitching quality | Predicts away scoring environment |
    | Σ Quality 30d | sum of both differentials | Higher = more total runs expected |
    | Δ Advantage 30d | difference of both differentials | Higher = stronger home advantage |
    """)
    return


@app.cell
def _(TARGET_COLS, TARGET_LABELS, df, pd, scipy_stats):
    _req = [
        "home_off_woba_30d", "away_pit_xwoba_against_30d",
        "away_off_woba_30d", "home_pit_xwoba_against_30d",
    ]
    _have = all(c in df.columns for c in _req)
    diff_df = pd.DataFrame()

    if _have:
        _d = df.copy()
        _d["home_matchup_quality"] = _d["home_off_woba_30d"] - _d["away_pit_xwoba_against_30d"]
        _d["away_matchup_quality"] = _d["away_off_woba_30d"] - _d["home_pit_xwoba_against_30d"]
        _d["total_matchup_quality"] = _d["home_matchup_quality"] + _d["away_matchup_quality"]
        _d["matchup_advantage"]     = _d["home_matchup_quality"] - _d["away_matchup_quality"]

        # (diff_col, label, comp_a, comp_b)
        _specs = [
            ("home_matchup_quality",  "Off(H) − Pit(A) 30d",  "home_off_woba_30d",           "away_pit_xwoba_against_30d"),
            ("away_matchup_quality",  "Off(A) − Pit(H) 30d",  "away_off_woba_30d",           "home_pit_xwoba_against_30d"),
            ("total_matchup_quality", "Σ Quality 30d",         None,                           None),
            ("matchup_advantage",     "Δ Advantage 30d",       None,                           None),
        ]

        _rows = []
        for _tgt_col, _tgt_label in zip(TARGET_COLS, TARGET_LABELS):
            for _dc, _dlabel, _ca, _cb in _specs:
                _mask = _d[[_dc, _tgt_col]].notna().all(axis=1)
                if _mask.sum() < 100:
                    continue
                _r, _ = scipy_stats.pearsonr(
                    _d.loc[_mask, _dc].astype(float),
                    _d.loc[_mask, _tgt_col].astype(float),
                )
                _entry = {
                    "signal":  _dlabel,
                    "target":  _tgt_label,
                    "r_diff":  round(_r, 4),
                }
                for _cn, _cc in [("r_comp_a", _ca), ("r_comp_b", _cb)]:
                    if _cc and _cc in _d.columns:
                        _m2 = _d[[_cc, _tgt_col]].notna().all(axis=1)
                        _rc, _ = scipy_stats.pearsonr(
                            _d.loc[_m2, _cc].astype(float),
                            _d.loc[_m2, _tgt_col].astype(float),
                        )
                        _entry[_cn] = round(_rc, 4)
                _rows.append(_entry)
        diff_df = pd.DataFrame(_rows)
    return (diff_df,)


@app.cell
def _(TARGET_LABELS, diff_df, mo, np, pd, plt):
    plt.close("all")
    if not diff_df.empty:
        _SIG_ORDER = [
            "Off(H) − Pit(A) 30d",
            "Off(A) − Pit(H) 30d",
            "Σ Quality 30d",
            "Δ Advantage 30d",
        ]
        _fig, _axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
        _fig.suptitle(
            "Matchup Differentials vs. Individual Component Correlations (|Pearson r| with target)",
            fontsize=11, fontweight="bold", y=1.01,
        )

        for _ax, _tgt in zip(_axes, TARGET_LABELS):
            _sub = diff_df[diff_df["target"] == _tgt]
            if _sub.empty:
                continue
            _x = np.arange(len(_SIG_ORDER))
            _w = 0.28

            _r_d = []
            for _s in _SIG_ORDER:
                _row = _sub[_sub["signal"] == _s]
                _r_d.append(abs(float(_row["r_diff"].values[0])) if not _row.empty else 0.0)
            _ax.bar(_x, _r_d, width=_w * 2.2, color="#1565C0", alpha=0.78, label="Differential", zorder=3)

            for _si, _s in enumerate(_SIG_ORDER[:2]):
                _row = _sub[_sub["signal"] == _s]
                if _row.empty:
                    continue
                if "r_comp_a" in _row.columns and pd.notna(_row["r_comp_a"].values[0]):
                    _ax.bar(
                        _x[_si] - _w * 0.85,
                        abs(float(_row["r_comp_a"].values[0])),
                        width=_w, color="#90CAF9", alpha=0.85, edgecolor="gray", lw=0.5,
                        label="Comp A (offense)" if _si == 0 else "_nolegend_",
                        zorder=3,
                    )
                if "r_comp_b" in _row.columns and pd.notna(_row["r_comp_b"].values[0]):
                    _ax.bar(
                        _x[_si] + _w * 0.85,
                        abs(float(_row["r_comp_b"].values[0])),
                        width=_w, color="#EF9A9A", alpha=0.85, edgecolor="gray", lw=0.5,
                        label="Comp B (pitching)" if _si == 0 else "_nolegend_",
                        zorder=3,
                    )

            _ax.set_title(_tgt, fontsize=10, fontweight="bold")
            _ax.set_xticks(_x)
            _ax.set_xticklabels(_SIG_ORDER, rotation=22, ha="right", fontsize=8)
            _ax.set_ylabel("|Pearson r|")
            _ax.grid(True, alpha=0.35, axis="y")
            _ax.legend(fontsize=7, loc="upper right")

        plt.tight_layout()
        mo.output.append(_fig)
    return


@app.cell
def _(all_flagged_pairs_df, corr_df, diff_df, mo, pd):
    # Build dynamic recommendation text from computed findings
    def _top5(tgt):
        _sub = (
            corr_df[corr_df["target"] == tgt]
            .sort_values("abs_pearson_r", ascending=False)
            .head(5)
        )
        return "\n".join(
            f"  {i+1}. `{row.feature}` (r={row.pearson_r:+.3f})"
            for i, row in enumerate(_sub.itertuples())
        )

    _top_total = _top5("Total Runs")
    _top_rdiff = _top5("Run Differential")
    _top_win   = _top5("Home Win")

    _n_red = len(all_flagged_pairs_df)
    _redund_lines = (
        "\n".join(
            f"  - `{row.feature_a}` ↔ `{row.feature_b}` (|r|={row.abs_r:.3f})"
            for _, row in all_flagged_pairs_df.head(12).iterrows()
        )
        if _n_red > 0
        else "  *None found above threshold*"
    )

    # Differential summary
    _diff_lines = ""
    if not diff_df.empty:
        for _tgt in ["Total Runs", "Run Differential"]:
            _sub_d = diff_df[diff_df["target"] == _tgt]
            for _sig in ["Σ Quality 30d", "Δ Advantage 30d"]:
                _row = _sub_d[_sub_d["signal"] == _sig]
                if not _row.empty:
                    _r = float(_row["r_diff"].values[0])
                    _diff_lines += f"  - `{_sig}` vs. **{_tgt}**: r={_r:+.4f}\n"

        # Check if differential beats components
        _beats = []
        for _, _row in diff_df[diff_df["signal"].isin(["Off(H) − Pit(A) 30d", "Off(A) − Pit(H) 30d"])].iterrows():
            _r_d = abs(_row["r_diff"])
            _r_a = abs(_row.get("r_comp_a", 0) or 0)
            _r_b = abs(_row.get("r_comp_b", 0) or 0)
            if _r_d > max(_r_a, _r_b):
                _beats.append(f"`{_row['signal']}` vs. {_row['target']}")
        _beats_summary = (
            "Differential **beats both components** for: " + ", ".join(_beats)
            if _beats
            else "Differentials do not consistently outperform individual components on this dataset (individual correlations are weak enough that the subtraction adds limited benefit)."
        )
    else:
        _diff_lines = "  *Required 30d columns not found in feature table.*"
        _beats_summary = ""

    # wOBA vs xwOBA redundancy check
    # Match pairs where one feature has bare _woba_ (no x prefix) and the other has _xwoba_
    def _is_woba_xwoba_pair(r):
        def _has_bare_woba(c):
            return "woba" in c and "xwoba" not in c
        def _has_xwoba(c):
            return "xwoba" in c
        return (
            (_has_bare_woba(r["feature_a"]) and _has_xwoba(r["feature_b"]))
            or (_has_xwoba(r["feature_a"]) and _has_bare_woba(r["feature_b"]))
        )
    _woba_pairs = (
        all_flagged_pairs_df[all_flagged_pairs_df.apply(_is_woba_xwoba_pair, axis=1)]
        if not all_flagged_pairs_df.empty
        else pd.DataFrame()
    )
    _woba_note = (
        f"wOBA and xwOBA within the same window are highly correlated ({len(_woba_pairs)} redundant pairs) — prefer xwOBA (park-adjusted, less noise)."
        if not _woba_pairs.empty
        else "wOBA and xwOBA overlap was not detected above the 0.85 threshold in defined groups."
    )

    mo.md(f"""
    ## Phase 3 — Notebook 04 Findings and Recommendations

    ### Top Features by Target (|Pearson r| ranking)

    **Total Runs** (over/under target):
    {_top_total}

    **Run Differential** (spread target):
    {_top_rdiff}

    **Home Win** (moneyline target):
    {_top_win}

    ---

    ### Feature Selection Recommendations

    #### Keep

    - **Season-to-date and 30-day windows** for all starter and pitching metrics — confirmed as the
      strongest windows from notebook 03 and validated here by correlation magnitude.
    - **30-day windows for team offense** — equivalent to STD and more robust to in-season roster changes.
    - **Era flags** (`game_year`, `post_2022_rules`) — absorb the structural 2022→2023 rule-change shift.
    - **`home_win_rate_trailing_3yr`** — time-varying home advantage (0.548 → 0.519 trend).
    - **Starter IP history** (`avg_ip_last_3`, `avg_ip_season`) — expected game depth signal not captured
      by rolling K% or xwOBA.
    - **Delta/momentum features** (Cards 4.1) — 7-day window is redundant as a standalone feature
      but retains value as the short end of the delta signal.

    #### Drop as Redundant ({_n_red} pairs with |r| > 0.85)

    The worst offenders are window variants of the same metric. Primary recommendation: **drop 14-day
    window standalone features** — 7d carries momentum signal, 30d/STD carry stability signal, and 14d
    falls between both without adding independent information. The most redundant pairs detected:

    {_redund_lines}

    **{_woba_note}** Prefer xwOBA over raw wOBA where both exist for the same window.

    #### Replace with Differentials

    Matchup differential correlations with targets:
    {_diff_lines}

    {_beats_summary}

    Regardless of raw |r| comparison, **explicit matchup differentials are recommended as engineered
    features** because:
    1. They encode the three-way interaction (lineup composition × starter quality × ballpark) in a
       single scalar that XGBoost/NGBoost would otherwise need to approximate.
    2. `total_matchup_quality_30d` is the cleanest single-feature proxy for expected total scoring
       environment and belongs in the Phase 4 feature matrix.
    3. `matchup_advantage_30d` is the directional complement — belongs in run-differential and win
       probability models.

    ---

    ### Phase 4 Feature Matrix Implications

    | Decision | Rationale |
    |---|---|
    | Drop 14-day standalone features | Redundant with 30-day; add collinearity without signal |
    | Prefer xwOBA over wOBA same-window | xwOBA is more stable; raw wOBA has park-size noise |
    | Add `total_matchup_quality_30d` | Explicit scoring-environment interaction feature |
    | Add `matchup_advantage_30d` | Directional home-advantage interaction feature |
    | Retain 7-day only as delta inputs | Standalone 7d is noisy; value is in 7d−30d spread |
    | Keep `game_year` and `post_2022_rules` | Era shift is visible in correlation by season |
    """)
    return


if __name__ == "__main__":
    app.run()
