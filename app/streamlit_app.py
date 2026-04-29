import datetime

import streamlit as st

st.set_page_config(
    page_title="Baseball Betting Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.header("Baseball Betting Dashboard")
    st.caption(f"Today: {datetime.date.today().strftime('%B %d, %Y')}")

st.title("Baseball Betting Dashboard")
st.write(
    "MLB game predictions powered by NGBoost + XGBoost with Bayesian market integration."
)
st.info("Use the sidebar to navigate between pages.")
