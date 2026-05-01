import datetime

import streamlit as st

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
    st.Page("pages/4_Model_Performance.py", title="Performance Tracker", icon="📈"),
])
pg.run()
