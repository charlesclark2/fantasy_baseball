import os
import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import snowflake.connector

_KEY_PATH = os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

_QUERY = """
SELECT
    f.*,
    r.home_final_score + r.away_final_score                        AS total_runs,
    r.home_final_score - r.away_final_score                        AS run_differential,
    CASE WHEN r.home_final_score > r.away_final_score THEN 1 ELSE 0 END AS home_win
FROM baseball_data.betting_features.feature_pregame_game_features f
JOIN baseball_data.betting.mart_game_results r USING (game_pk)
WHERE f.has_full_data = TRUE
  AND LEAST(f.home_games_played, f.away_games_played) >= {min_games_played}
  AND f.game_year != 2020
"""


def _connect() -> snowflake.connector.SnowflakeConnection:
    with open(_KEY_PATH, "rb") as fh:
        p_key = serialization.load_pem_private_key(
            fh.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account="IHUPICS-DP59975",
        user="dbt_rw",
        private_key=pkb,
        role="ACCOUNTADMIN",
        warehouse="COMPUTE_WH",
        database="baseball_data",
    )


def load_features(min_games_played: int = 15) -> pd.DataFrame:
    conn = _connect()
    try:
        query = _QUERY.format(min_games_played=int(min_games_played))
        cur = conn.cursor()
        cur.execute(query)
        columns = [desc[0].lower() for desc in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=columns)
        # Snowflake returns NUMERIC/DECIMAL columns as decimal.Decimal objects.
        # Convert object-dtype columns that contain numeric values to float64 so
        # downstream arithmetic (Bayesian shrinkage, pandas ops) works correctly.
        for col in df.columns:
            if df[col].dtype == object:
                converted = pd.to_numeric(df[col], errors="coerce")
                # Only adopt the conversion if no non-null values became NaN
                # (i.e., the column genuinely contained numeric data).
                if converted.notna().sum() >= df[col].notna().sum():
                    df[col] = converted
        return df
    finally:
        conn.close()
