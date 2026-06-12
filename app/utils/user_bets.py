"""Owner-scoped bet access for the Streamlit tool.

Bets are canonical in DynamoDB (credence-prod-dynamo-user-bets); see
infrastructure/aws_resources.md. The Streamlit pages are the owner's internal
tool and have no per-user auth, so they read/write under a single owner sub
(OWNER_USER_ID). The public web app writes per-user via POST /bets.

Outcomes are settled by the daily Dagster `settle_user_bets_op`, so reads here
use the stored `outcome`/`profit_loss` directly — no score join needed.

NOTE: the Streamlit environment's IAM principal needs DynamoDB read/write on the
table (currently the tightly-scoped baseball-access-user lacks it) — see the
aws_resources.md IAM section.
"""

from __future__ import annotations

import os

import pandas as pd

from app.backend.services.dynamo import list_bets, put_bet

OWNER_USER_ID = os.getenv("OWNER_USER_ID", "14187448-c091-705c-1199-63858b12c986")

_COLUMNS = [
    "bet_id", "score_date", "game_pk", "matchup", "market", "bookmaker",
    "american_odds", "stake", "total_line", "model_prob", "market_prob",
    "ev", "kelly_capped", "outcome", "profit_loss", "notes", "placed_at",
]
_NUMERIC = [
    "game_pk", "american_odds", "stake", "total_line", "model_prob",
    "market_prob", "ev", "kelly_capped", "profit_loss",
]


def load_owner_bets_df(user_id: str | None = None) -> pd.DataFrame:
    """Return the owner's bets as a DataFrame with placed_bets-compatible columns.

    `outcome`/`profit_loss` are the stored, already-settled values (NaN/None while
    a bet is pending). `score_date` is a python date for easy day filtering.
    """
    bets = list_bets(user_id or OWNER_USER_ID)
    if not bets:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.DataFrame(bets)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["score_date"] = pd.to_datetime(df["score_date"], errors="coerce").dt.date
    for col in _NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def write_owner_bet(bet: dict, user_id: str | None = None) -> dict:
    """Write a bet under the owner sub (mirrors POST /bets). Stamps bet_id/placed_at
    and marks it pending so the settle job picks it up."""
    return put_bet(user_id or OWNER_USER_ID, bet)
