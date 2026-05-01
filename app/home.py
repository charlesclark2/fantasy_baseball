import pathlib

import streamlit as st
import yaml

st.title("💎 Diamond Edge")

# Section 1 — Project Description
st.markdown(
    "**Diamond Edge** is an MLB game prediction system that uses machine learning "
    "models trained on 10 years of historical data to surface pre-game edges against "
    "live betting market lines.\n\n"
    "Models are powered by **NGBoost** (total runs and run differential) and **XGBoost** "
    "(win probability, Platt-calibrated), integrated with real-time Odds API market "
    "prices via a Bayesian probability layer. Predictions are ranked by the gap between "
    "the model's probability estimate and the market's implied probability — the edge signal."
)

# Section 2 — Page Navigation Guide
st.subheader("What Each Page Does")
st.markdown(
    "| Page | What It Shows | Best Used When |\n"
    "|---|---|---|\n"
    "| Today's Picks | Ranked game predictions with edge scores, Kelly fractions, and lineup status for today's slate | Every morning after lineups are confirmed (~2–3 hours before first pitch) |\n"
    "| Market Comparison | Model probability vs. all bookmaker lines with intraday line movement charts | Investigating a specific game — checking if the model and sharp books agree |\n"
    "| EV Tracker | Expected value and Kelly bet sizing across all markets; bankroll simulator | Building a suggested bet slate with position sizes for the day |\n"
    "| Performance Tracker | Rolling Brier score vs. market, Closing Line Value by week, cumulative P&L | Monitoring model accuracy and bet performance over time |"
)

# Section 3 — Model Fact Sheet
st.subheader("Model Summary")

registry_path = pathlib.Path("betting_ml/models/model_registry.yaml")
last_updated = "Unknown"
if registry_path.exists():
    try:
        registry = yaml.safe_load(registry_path.read_text())
        last_updated = registry.get("home_win", {}).get("selected_at", "Unknown")
    except Exception:
        st.warning("model_registry.yaml could not be parsed — model summary may be incomplete.")
else:
    st.warning("model_registry.yaml not found — model summary may be incomplete.")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Training Games", "23,444", "2016–2025")
with col2:
    st.metric("Total Runs MAE", "3.57 runs", "NGBoost LogNormal")
with col3:
    st.metric("Win Prob Brier", "0.2393", delta="beats market 0.2395", delta_color="normal")
with col4:
    st.metric("Last Model Update", last_updated)

st.info(
    "Bayesian mixing weight α = 0.0: market implied probability is used "
    "as the probability prior. Model edge signal = model prob − market prob."
)

# Section 4 — Daily Workflow Reminder
with st.expander("How the daily pipeline works", expanded=False):
    st.markdown(
        "Five GitHub Actions workflows orchestrate the full pipeline.\n\n"
        "**08:00 ET daily — `daily_ingestion.yml`**\n"
        "Ingests four data sources in sequence: prior-day Statcast pitch data "
        "(Baseball Savant), today's game schedule and lineups (MLB Stats API), "
        "and live betting events + odds (Odds API). All data lands in Snowflake "
        "raw tables. Once ingestion finishes, it calls `dbt_daily_build.yml` as a "
        "reusable workflow: `dbt build` on odd calendar days, `dbt run` on even days, "
        "`dbt build --full-refresh` on Sundays. After dbt completes, "
        "`backfill_prediction_log.py` resolves outcomes for settled games and "
        "computes Closing Line Value.\n\n"
        "**Hourly — `lineup_monitor.yml`**\n"
        "Re-ingests the MLB Stats API schedule for the current and prior month, "
        "rebuilds `stg_statsapi_lineups` and `stg_statsapi_lineups_wide`, then "
        "runs `lineup_monitor.py` to detect newly confirmed lineups. If new "
        "confirmations are found, a targeted `dbt build --select +stg_statsapi_lineups+` "
        "refreshes the lineup-dependent feature models.\n\n"
        "**13:00 / 18:00 / 23:00 EDT — `odds_snapshot.yml`**\n"
        "Checks whether any regular-season games are scheduled today. If so, "
        "re-ingests Odds API events and odds and rebuilds the odds dbt DAG "
        "(`+stg_oddsapi_events+ +stg_oddsapi_odds+`). Skips all steps on off-days "
        "to conserve API credits.\n\n"
        "**Morning of game day (manual)**\n"
        "Open **Today's Picks** and press **Refresh** to load the latest lineups "
        "and odds. Games with confirmed lineups and an edge greater than 5% are "
        "highlighted. Wait until the Lineups column shows ✓ before acting on any signal — "
        "edge estimates are unreliable until both starting lineups are confirmed.\n\n"
        "**Lineup lock timing:** Lineups typically go official 2–3 hours before "
        "first pitch. Early games (1:00 PM ET) may lock as late as 10:30 AM ET."
    )

    st.graphviz_chart("""
        digraph pipeline {
            rankdir=TB
            graph [bgcolor=transparent, fontname="Arial", pad="0.5", nodesep="0.4", ranksep="0.6"]
            node  [fontname="Arial", fontsize="11", style="filled,rounded", shape=box, margin="0.2,0.1"]
            edge  [fontname="Arial", fontsize="10", color="#555555"]

            subgraph cluster_daily {
                label="08:00 ET daily"
                style=dashed
                color="#2088FF"
                fontcolor="#2088FF"
                fontname="Arial"
                fontsize="11"
                Statcast [label="Statcast\\n(pitch data)",           fillcolor="#D6EAF8"]
                StatsD   [label="Stats API\\n(schedule + lineups)",  fillcolor="#D6EAF8"]
                OddsD    [label="Odds API\\n(events + odds)",        fillcolor="#D6EAF8"]
                dbt      [label="dbt_daily_build\\nbuild / run / full-refresh", fillcolor="#D5F5E3"]
                Backfill [label="Backfill\\nprediction_log",         fillcolor="#FEF9E7"]
            }

            subgraph cluster_hourly {
                label="Hourly"
                style=dashed
                color="#8E44AD"
                fontcolor="#8E44AD"
                fontname="Arial"
                fontsize="11"
                LineupM  [label="lineup_monitor.yml\\n(re-ingest + detect new confirmations)", fillcolor="#F5EEF8"]
                LineupDbt[label="dbt build\\n+stg_statsapi_lineups+\\n(if new confirmations)", fillcolor="#D5F5E3"]
            }

            subgraph cluster_odds {
                label="13:00 / 18:00 / 23:00 EDT"
                style=dashed
                color="#D35400"
                fontcolor="#D35400"
                fontname="Arial"
                fontsize="11"
                OddsSnap [label="odds_snapshot.yml\\n(re-ingest if games today)", fillcolor="#FDEBD0"]
                OddsDbt  [label="dbt build\\n+stg_oddsapi_events+\\n+stg_oddsapi_odds+", fillcolor="#D5F5E3"]
            }

            Snow [label="Snowflake\\nRaw Tables",    fillcolor="#E8F8F5"]
            Feat [label="Feature Tables\\n(Snowflake)", fillcolor="#D5F5E3", penwidth=2]
            App  [label="Today's Picks\\n(manual refresh)", fillcolor="#FDEBD0", fontcolor="#7D6608", penwidth=2]

            Statcast -> Snow
            StatsD   -> Snow
            OddsD    -> Snow
            Snow     -> dbt      [label="transform"]
            dbt      -> Feat
            Feat     -> Backfill [label="settle outcomes"]

            LineupM  -> Snow     [label="re-ingest"]
            LineupM  -> LineupDbt
            LineupDbt -> Feat

            OddsSnap -> Snow     [label="re-ingest"]
            OddsSnap -> OddsDbt
            OddsDbt  -> Feat

            Feat -> App [label="predictions"]
        }
    """)
