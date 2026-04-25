"""One-off script to seed Snowflake with the run_differential CV results that were
computed but lost when the first Snowflake write failed (schema did not exist).

Populates cv_results_run_diff from the known fold output.
RMSE and ablation values are not available from that run — those columns are left
NULL and will be overwritten with complete data on the next full re-run.

Run once:
    uv run python betting_ml/scripts/seed_run_diff_cv_results.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

# Pasted fold output — 2026 partial season excluded.
# Columns: fold, model, n_eval, mae, win_prob_brier (RMSE unknown → NULL)
_FOLD_ROWS = [
    # (fold, model,              n_eval, mae,   win_prob_brier)
    ("2019", "global_mean",      1999,   3.698, None),
    ("2019", "ridge",            1999,   3.541, None),
    ("2019", "xgboost",          1999,   3.595, None),
    ("2019", "ngboost_normal",   1999,   3.553, 0.2386),
    ("2019", "ngboost_lognormal",1999,   None,  None),
    ("2021", "global_mean",      1953,   3.552, None),
    ("2021", "ridge",            1953,   3.496, None),
    ("2021", "xgboost",          1953,   3.517, None),
    ("2021", "ngboost_normal",   1953,   3.463, 0.2445),
    ("2021", "ngboost_lognormal",1953,   None,  None),
    ("2022", "global_mean",      2007,   3.474, None),
    ("2022", "ridge",            2007,   3.336, None),
    ("2022", "xgboost",          2007,   3.378, None),
    ("2022", "ngboost_normal",   2007,   3.342, 0.2394),
    ("2022", "ngboost_lognormal",2007,   None,  None),
    ("2023", "global_mean",      2013,   3.492, None),
    ("2023", "ridge",            2013,   3.458, None),
    ("2023", "xgboost",          2013,   3.474, None),
    ("2023", "ngboost_normal",   2013,   3.424, 0.2463),
    ("2023", "ngboost_lognormal",2013,   None,  None),
    ("2024", "global_mean",      2002,   3.504, None),
    ("2024", "ridge",            2002,   3.402, None),
    ("2024", "xgboost",          2002,   3.400, None),
    ("2024", "ngboost_normal",   2002,   3.411, 0.2442),
    ("2024", "ngboost_lognormal",2002,   None,  None),
    ("2025", "global_mean",      2026,   3.576, None),
    ("2025", "ridge",            2026,   3.502, None),
    ("2025", "xgboost",          2026,   3.512, None),
    ("2025", "ngboost_normal",   2026,   3.484, 0.2445),
    ("2025", "ngboost_lognormal",2026,   None,  None),
]


def main() -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        cur.execute("CREATE SCHEMA IF NOT EXISTS baseball_data.betting_ml")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_results_run_diff (
                fold VARCHAR,
                model VARCHAR,
                n_eval INTEGER,
                mae FLOAT,
                rmse FLOAT,
                win_prob_brier FLOAT,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.cv_results_run_diff")

        for fold, model, n_eval, mae, win_prob_brier in _FOLD_ROWS:
            cur.execute(
                """
                INSERT INTO baseball_data.betting_ml.cv_results_run_diff
                    (fold, model, n_eval, mae, rmse, win_prob_brier)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (fold, model, n_eval, mae, None, win_prob_brier),
            )

        conn.commit()
        print(f"Inserted {len(_FOLD_ROWS)} rows into baseball_data.betting_ml.cv_results_run_diff.")
        print("RMSE and ablation tables (cv_era_ablation_run_diff, cv_summary_run_diff)")
        print("will be populated on the next full re-run of train_run_diff_baselines.py.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
