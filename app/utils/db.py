"""Shared Snowflake connection factory and query helpers for the Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))


@st.cache_resource
def get_snowflake_session():
    """Return a cached Snowflake connection (created once per Streamlit process).

    Delegates to the existing RSA key connector in betting_ml/utils/data_loader.py.
    Disables Snowflake's server-side result cache so every query hits current data.
    """
    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection()
    conn.cursor().execute("ALTER SESSION SET USE_CACHED_RESULT = FALSE")
    return conn


def run_query(sql: str, conn=None) -> pd.DataFrame:
    """Execute SQL and return a pandas DataFrame.

    Uses the cached session if conn is not provided.
    """
    if conn is None:
        conn = get_snowflake_session()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetch_pandas_all()
    except Exception as exc:
        preview = sql[:200].replace("\n", " ")
        raise RuntimeError(
            f"Snowflake query failed: {exc}\nSQL preview: {preview}"
        ) from exc


@st.cache_data(ttl=3600)
def load_best_alpha() -> float:
    """Return best_alpha from alpha_tuning_results (cached 1 hour).

    Raises RuntimeError if the table is empty — run run_probability_layer.py first.
    """
    df = run_query(
        "SELECT alpha FROM baseball_data.betting_ml.alpha_tuning_results "
        "ORDER BY loaded_at DESC LIMIT 1"
    )
    if df.empty:
        raise RuntimeError(
            "alpha_tuning_results table is empty. "
            "Run run_probability_layer.py to populate it before using this app."
        )
    col = df.columns[0]
    return float(df.iloc[0][col])
