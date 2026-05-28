import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from betting_ml.utils.calibrated_classifier import PlattCalibratedXGBClassifier  # noqa: F401 — joblib needs this in __main__

st.set_page_config(
    page_title="Diamond Edge",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.markdown("# 💎 Diamond Edge")
st.sidebar.markdown("_MLB game predictions powered by NGBoost + XGBoost_")
st.sidebar.divider()
st.sidebar.caption(f"Today: {datetime.date.today().strftime('%B %d, %Y')}")

pg = st.navigation([
    st.Page("home.py",                      title="Home",                icon="🏠"),
    st.Page("pages/1_Today_Picks.py",       title="Today's Picks",       icon="⚾"),
    st.Page("pages/2_Market_Comparison.py", title="Market Comparison",   icon="📊"),
    st.Page("pages/3_EV_Kelly.py",          title="EV Tracker",          icon="💰"),
    st.Page("pages/5_Game_Insights.py",     title="Game Insights",       icon="🔍"),
    st.Page("pages/4_Model_Performance.py", title="Performance Tracker", icon="📈"),
])
pg.run()
