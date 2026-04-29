-- ============================================================
-- lineup_monitor_task.sql
-- Snowflake Task + Stored Procedure for hourly lineup monitoring
-- Phase 5 / Card 3 — Lineup Notification Hourly Batch
-- ============================================================
--
-- PREREQUISITES (run manually before executing this file):
--
--   1. EXECUTE TASK + EXECUTE MANAGED TASK privileges (ACCOUNTADMIN required,
--      already granted to task_executor_role by snowflake_task_dag.sql):
--      GRANT EXECUTE TASK ON ACCOUNT TO ROLE task_executor_role;
--      GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE task_executor_role;
--      (EXECUTE MANAGED TASK is required because this task uses
--       USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE — serverless compute.)
--
--   2. NETWORK RULE + EXTERNAL ACCESS INTEGRATION:
--      daily_ingestion_access_integration already exists (Card 6.A.2).
--
--   3. GitHub PAT secret: baseball_data.config.github_pat already exists (Card 6.A.0).
--
--   4. Schema-level grants for task_executor_role (run as ACCOUNTADMIN if not
--      already granted — betting/betting_features were not covered by Card 6.A.1):
--      stg + mart models build into baseball_data.betting:
--      GRANT USAGE ON SCHEMA baseball_data.betting TO ROLE task_executor_role;
--      GRANT SELECT ON ALL TABLES IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
--      GRANT SELECT ON FUTURE TABLES IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
--      GRANT SELECT ON ALL VIEWS IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
--      GRANT SELECT ON FUTURE VIEWS IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
--      feature models build into baseball_data.betting_features:
--      GRANT USAGE ON SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
--      GRANT SELECT ON ALL TABLES IN SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
--      GRANT SELECT ON FUTURE TABLES IN SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
--      GRANT SELECT ON ALL VIEWS IN SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
--      GRANT SELECT ON FUTURE VIEWS IN SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
--      -- config schema grants (pipeline_run_log + lineup_monitor_state):
--      GRANT USAGE ON SCHEMA baseball_data.config TO ROLE task_executor_role;
--      GRANT INSERT, SELECT, UPDATE ON ALL TABLES IN SCHEMA baseball_data.config TO ROLE task_executor_role;
--      GRANT INSERT, SELECT, UPDATE ON FUTURE TABLES IN SCHEMA baseball_data.config TO ROLE task_executor_role;
--
-- EXECUTE ORDER:
--   1. Run Section 0 (state table + pipeline_run_log IF NOT EXISTS)
--   2. Run Section 1 (lineup_monitor_proc stored procedure)
--   3. Run Section 2 (CREATE TASK + RESUME)
-- ============================================================


-- ============================================================
-- SECTION 0: State table and audit log
-- ============================================================

-- Deduplication guard: UNIQUE (run_date, game_pk) prevents re-triggering
-- the same game on repeat hourly fires.
CREATE TABLE IF NOT EXISTS baseball_data.config.lineup_monitor_state (
    run_date           DATE          NOT NULL,
    game_pk            INT           NOT NULL,
    triggered_at       TIMESTAMP_NTZ NOT NULL,
    gh_workflow_run_id STRING,
    UNIQUE (run_date, game_pk)
);

-- pipeline_run_log already exists from Card 6.A (snowflake_task_dag.sql, Section 0).
-- Existing schema: task_name, run_ts, status, rows_affected, error_message.
-- CREATE TABLE IF NOT EXISTS is a no-op when the table already exists.
CREATE TABLE IF NOT EXISTS baseball_data.config.pipeline_run_log (
    task_name     VARCHAR,
    run_ts        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    status        VARCHAR,
    rows_affected INTEGER,
    error_message VARCHAR(1000)
);


-- ============================================================
-- SECTION 1: lineup_monitor_proc stored procedure
-- ============================================================

CREATE OR REPLACE PROCEDURE baseball_data.config.lineup_monitor_proc()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (daily_ingestion_access_integration)
  SECRETS = ('github_pat' = baseball_data.config.github_pat)
  HANDLER = 'handler'
  EXECUTE AS OWNER
AS $$
import _snowflake
import requests
import json
from datetime import date

REPO_OWNER    = 'charlesclark2'
REPO_NAME     = 'fantasy_baseball'
WORKFLOW_FILE = 'dbt_staging_build.yml'
REF           = 'main'
TASK          = 'lineup_monitor_proc'

def handler(session):
    try:
        today = date.today().isoformat()

        # Step A — Lineup detection: query stg_statsapi_lineups_wide for today.
        # A lineup is confirmed when both home_lineup_slot_1 and away_lineup_slot_1
        # are populated. This view reflects the most recent dbtf build output.
        # stg_statsapi_lineups_wide has one row per (game_pk, home_away) and
        # already excludes rows where slot_1_player_id is null (i.e. no lineup yet).
        # Both lineups are confirmed when both 'home' and 'away' rows exist for a game.
        confirmed_rows = session.sql(f"""
            SELECT game_pk
            FROM baseball_data.betting.stg_statsapi_lineups_wide
            WHERE official_date = '{today}'::date
            GROUP BY game_pk
            HAVING COUNT(DISTINCT home_away) = 2
        """).collect()

        confirmed_game_pks = [row[0] for row in confirmed_rows]

        # Step B — Deduplication and dispatch.
        # Only process games not already in lineup_monitor_state for today.
        already_triggered_rows = session.sql(f"""
            SELECT game_pk
            FROM baseball_data.config.lineup_monitor_state
            WHERE run_date = '{today}'::date
        """).collect()
        already_triggered = {row[0] for row in already_triggered_rows}

        new_game_pks = [pk for pk in confirmed_game_pks if pk not in already_triggered]
        dispatched = 0

        if new_game_pks:
            pat = _snowflake.get_generic_secret_string('github_pat')
            url = (
                f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}'
                f'/actions/workflows/{WORKFLOW_FILE}/dispatches'
            )

            for game_pk in new_game_pks:
                # Insert with NOT EXISTS guard to prevent duplicate inserts on
                # concurrent executions (belt-and-suspenders alongside the UNIQUE constraint).
                session.sql(f"""
                    INSERT INTO baseball_data.config.lineup_monitor_state
                        (run_date, game_pk, triggered_at)
                    SELECT
                        '{today}'::date,
                        {game_pk}::int,
                        CURRENT_TIMESTAMP()
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM baseball_data.config.lineup_monitor_state
                        WHERE run_date = '{today}'::date
                          AND game_pk  = {game_pk}::int
                    )
                """).collect()

                # Dispatch dbt_staging_build.yml for this game_pk.
                resp = requests.post(
                    url,
                    headers={
                        'Authorization': f'token {pat}',
                        'Accept': 'application/vnd.github+json',
                    },
                    json={
                        'ref': REF,
                        'inputs': {
                            'game_pk': str(game_pk),
                            'triggered_by': 'lineup_monitor',
                        },
                    },
                    timeout=30,
                )

                # On success (HTTP 204), update gh_workflow_run_id placeholder.
                # The actual run ID is populated by the workflow callback on completion.
                if resp.status_code == 204:
                    session.sql(f"""
                        UPDATE baseball_data.config.lineup_monitor_state
                        SET gh_workflow_run_id = 'dispatched'
                        WHERE run_date = '{today}'::date
                          AND game_pk  = {game_pk}::int
                    """).collect()
                    dispatched += 1
                else:
                    err_msg = f'dispatch HTTP {resp.status_code} for game_pk {game_pk}: {resp.text[:200]}'.replace("'", '')
                    session.sql(
                        f"INSERT INTO baseball_data.config.pipeline_run_log "
                        f"(task_name, run_ts, status, rows_affected, error_message) "
                        f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'DISPATCH_ERROR', 0, '{err_msg}')"
                    ).collect()

        # Step C — Audit log: one row per hourly fire regardless of dispatch count.
        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', {dispatched})"
        ).collect()
        return f'SUCCESS:{dispatched}'

    except Exception as e:
        err = str(e)[:400].replace("'", '')
        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected, error_message) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'FAILED', 0, '{err}')"
        ).collect()
        raise
$$;


-- ============================================================
-- SECTION 2: Snowflake Task definition
-- ============================================================

-- Fires at the top of every hour (ET) to check for newly confirmed lineups.
CREATE OR REPLACE TASK baseball_data.config.task_lineup_monitor
  SCHEDULE = 'USING CRON 0 * * * * America/New_York'
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  COMMENT = 'Hourly lineup monitor: detects confirmed lineups, dispatches dbt_staging_build.yml'
AS
  CALL baseball_data.config.lineup_monitor_proc();

-- Snowflake Tasks are created SUSPENDED by default — explicit RESUME is required.
ALTER TASK baseball_data.config.task_lineup_monitor RESUME;


-- ============================================================
-- TEARDOWN (run to decommission the lineup monitor pipeline)
-- ============================================================

-- ALTER TASK baseball_data.config.task_lineup_monitor SUSPEND;
-- DROP TASK IF EXISTS baseball_data.config.task_lineup_monitor;
-- DROP PROCEDURE IF EXISTS baseball_data.config.lineup_monitor_proc();
-- DROP TABLE IF EXISTS baseball_data.config.lineup_monitor_state;
