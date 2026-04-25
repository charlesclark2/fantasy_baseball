-- ============================================================
-- snowflake_task_dag.sql
-- Snowflake Task DAG for automated daily ingestion
-- Cards 6.A.1 – 6.A.5
-- ============================================================
--
-- PREREQUISITES (run manually before executing this file):
--
--   1. EXECUTE TASK + EXECUTE MANAGED TASK privileges (ACCOUNTADMIN required):
--      GRANT EXECUTE TASK ON ACCOUNT TO ROLE task_executor_role;
--      GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE task_executor_role;
--      (EXECUTE MANAGED TASK is required for serverless tasks that use
--       USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE without specifying a warehouse.)
--
--   2. NETWORK RULE + EXTERNAL ACCESS INTEGRATION creation
--      requires ACCOUNTADMIN — see Card 6.A.2 (already complete).
--
--   3. GitHub PAT stored as baseball_data.config.github_pat secret
--      (already complete per Card 6.A.0).
--
--   4. ODDS_API_KEY stored as baseball_data.config.odds_api_key secret
--      (already complete per Card 6.A.3).
--
-- MISSING GRANTS (6.A.1 covered statsapi + config only; run as ACCOUNTADMIN):
--   GRANT USAGE ON SCHEMA baseball_data.savant TO ROLE task_executor_role;
--   GRANT USAGE ON SCHEMA baseball_data.oddsapi TO ROLE task_executor_role;
--   GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA baseball_data.savant TO ROLE task_executor_role;
--   GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA baseball_data.oddsapi TO ROLE task_executor_role;
--   GRANT INSERT, SELECT ON FUTURE TABLES IN SCHEMA baseball_data.savant TO ROLE task_executor_role;
--   GRANT INSERT, SELECT ON FUTURE TABLES IN SCHEMA baseball_data.oddsapi TO ROLE task_executor_role;
--
-- ============================================================


-- ============================================================
-- SECTION 0: pipeline_run_log audit table
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball_data.config.pipeline_run_log (
    task_name     VARCHAR,
    run_ts        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    status        VARCHAR,
    rows_affected INTEGER,
    error_message VARCHAR(1000)
);


-- ============================================================
-- SECTION 4: Stored Procedures
-- Run as SYSADMIN (or any role with CREATE PROCEDURE on config schema)
-- ============================================================

-- ------------------------------------------------------------
-- 4a. proc_savant_ingestion
--     Fetches prior-day Statcast CSV from Baseball Savant.
--     Writes to baseball_data.savant.batter_pitches.
--     Auto-detects last loaded date; ingests incrementally to yesterday.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE baseball_data.config.proc_savant_ingestion()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests', 'pandas')
  EXTERNAL_ACCESS_INTEGRATIONS = (daily_ingestion_access_integration)
  HANDLER = 'handler'
  EXECUTE AS OWNER
AS $$
import requests
import pandas as pd
import io
import time
from datetime import date, timedelta

def handler(session):
    TASK = 'proc_savant_ingestion'

    try:
        last_row = session.sql(
            "SELECT MAX(game_date::date)::varchar FROM baseball_data.savant.batter_pitches"
        ).collect()[0][0]

        yesterday = date.today() - timedelta(days=1)
        start = (date.fromisoformat(last_row) + timedelta(days=1)) if last_row else yesterday
        end = yesterday

        if start > end:
            session.sql(
                f"INSERT INTO baseball_data.config.pipeline_run_log "
                f"(task_name, run_ts, status, rows_affected) "
                f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', 0)"
            ).collect()
            return 'SUCCESS:0'

        table_cols = {
            r[0].upper() for r in session.sql(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema = 'SAVANT' AND table_name = 'BATTER_PITCHES'"
            ).collect()
        }

        http = requests.Session()
        http.headers['User-Agent'] = 'baseball-ingest/1.0'
        total = 0
        current = start

        while current <= end:
            day = current.isoformat()
            params = {
                'all': 'true', 'hfGT': 'R|', 'player_type': 'pitcher',
                'type': 'details', 'min_pitches': '0', 'min_results': '0',
                'min_pas': '0', 'sort_col': 'pitches', 'sort_order': 'desc',
                'hfSea': f'{current.year}|',
                'game_date_gt': day, 'game_date_lt': day,
            }
            resp = http.get(
                'https://baseballsavant.mlb.com/statcast_search/csv',
                params=params, timeout=90
            )
            resp.raise_for_status()
            text = resp.text.strip()

            if text and text.lower() != 'null':
                df = pd.read_csv(
                    io.StringIO(text), dtype=str,
                    encoding_errors='replace', encoding='utf-8-sig'
                )
                df = df.loc[:, ~df.columns.str.match(r'^Unnamed')]
                df.columns = [c.upper() for c in df.columns]
                df = df[[c for c in df.columns if c in table_cols]]

                session.sql(
                    f"DELETE FROM baseball_data.savant.batter_pitches "
                    f"WHERE game_date::date = '{day}'::date"
                ).collect()
                session.write_pandas(
                    df, 'BATTER_PITCHES',
                    database='BASEBALL_DATA', schema='SAVANT',
                    quote_identifiers=False
                )
                total += len(df)

            current += timedelta(days=1)
            time.sleep(2.0)

        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', {total})"
        ).collect()
        return f'SUCCESS:{total}'

    except Exception as e:
        err = str(e)[:400].replace("'", '')
        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected, error_message) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'FAILED', 0, '{err}')"
        ).collect()
        raise
$$;


-- ------------------------------------------------------------
-- 4b. proc_statsapi_schedule
--     Fetches current-month schedule + lineups from Stats API.
--     MERGEs into baseball_data.statsapi.monthly_schedule.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE baseball_data.config.proc_statsapi_schedule()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (daily_ingestion_access_integration)
  HANDLER = 'handler'
  EXECUTE AS OWNER
AS $$
import requests
import json
import calendar
from datetime import date

def handler(session):
    TASK = 'proc_statsapi_schedule'

    try:
        pred = session.sql("SELECT SYSTEM$GET_PREDECESSOR_RETURN_VALUE()").collect()[0][0]
        if pred is not None and not str(pred).startswith('SUCCESS'):
            session.sql(
                f"INSERT INTO baseball_data.config.pipeline_run_log "
                f"(task_name, run_ts, status, rows_affected, error_message) "
                f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SKIPPED', 0, 'predecessor failed')"
            ).collect()
            return 'SKIPPED'
    except Exception:
        pass

    try:
        today = date.today()
        month_start = today.replace(day=1).isoformat()
        last_day = calendar.monthrange(today.year, today.month)[1]
        month_end = today.replace(day=last_day).isoformat()

        resp = requests.get(
            'https://statsapi.mlb.com/api/v1/schedule',
            params={
                'sportId': 1, 'gameType': 'R',
                'hydrate': 'lineups,probablePitcher',
                'startDate': month_start, 'endDate': month_end,
            },
            timeout=30
        )
        resp.raise_for_status()
        payload = resp.json()
        games_cnt = int(payload.get('totalGames', 0))

        json_str = json.dumps(payload).replace("'", "''")
        session.sql(f"""
            MERGE INTO baseball_data.statsapi.monthly_schedule AS tgt
            USING (
                SELECT
                    '{month_start}'::date    AS month_start_date,
                    '{month_end}'::date      AS month_end_date,
                    {games_cnt}::int         AS games_cnt,
                    PARSE_JSON('{json_str}') AS json_field
            ) AS src
            ON tgt.month_start_date = src.month_start_date
            WHEN MATCHED THEN UPDATE SET
                month_end_date = src.month_end_date,
                games_cnt      = src.games_cnt,
                json_field     = src.json_field
            WHEN NOT MATCHED THEN INSERT (month_start_date, month_end_date, games_cnt, json_field)
                VALUES (src.month_start_date, src.month_end_date, src.games_cnt, src.json_field)
        """).collect()

        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', {games_cnt})"
        ).collect()
        return f'SUCCESS:{games_cnt}'

    except Exception as e:
        err = str(e)[:400].replace("'", '')
        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected, error_message) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'FAILED', 0, '{err}')"
        ).collect()
        raise
$$;


-- ------------------------------------------------------------
-- 4c. proc_oddsapi_events
--     Fetches upcoming MLB events from The Odds API (7-day window).
--     Appends one row to baseball_data.oddsapi.mlb_events_raw.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE baseball_data.config.proc_oddsapi_events()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (daily_ingestion_access_integration)
  SECRETS = ('odds_api_key' = baseball_data.config.odds_api_key)
  HANDLER = 'handler'
  EXECUTE AS OWNER
AS $$
import _snowflake
import requests
import json
import uuid
from datetime import datetime, timedelta, timezone

def handler(session):
    TASK = 'proc_oddsapi_events'

    try:
        pred = session.sql("SELECT SYSTEM$GET_PREDECESSOR_RETURN_VALUE()").collect()[0][0]
        if pred is not None and not str(pred).startswith('SUCCESS'):
            session.sql(
                f"INSERT INTO baseball_data.config.pipeline_run_log "
                f"(task_name, run_ts, status, rows_affected, error_message) "
                f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SKIPPED', 0, 'predecessor failed')"
            ).collect()
            return 'SKIPPED'
    except Exception:
        pass

    try:
        api_key = _snowflake.get_generic_secret_string('odds_api_key')
        load_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        window_from = now.strftime('%Y-%m-%dT%H:%M:%SZ')
        window_to   = (now + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        endpoint    = '/sports/baseball_mlb/events'

        resp = requests.get(
            f'https://api.the-odds-api.com/v4{endpoint}',
            params={
                'apiKey':           api_key,
                'commenceTimeFrom': window_from,
                'commenceTimeTo':   window_to,
            },
            timeout=30
        )
        resp.raise_for_status()
        payload = resp.json()
        event_count = len(payload) if isinstance(payload, list) else 0

        req_params = json.dumps({'commenceTimeFrom': window_from, 'commenceTimeTo': window_to})

        def esc(v):
            return str(v).replace("'", "''")

        v_ts        = esc(now.isoformat())
        v_load_id   = esc(load_id)
        v_endpoint  = esc(endpoint)
        v_url       = esc(resp.url)
        v_params    = esc(req_params)
        v_status    = resp.status_code
        v_used      = esc(resp.headers.get('x-requests-used', ''))
        v_remaining = esc(resp.headers.get('x-requests-remaining', ''))
        v_json      = esc(json.dumps(payload))

        session.sql(f"""
            INSERT INTO baseball_data.oddsapi.mlb_events_raw (
                ingestion_ts, load_id, source_system, process_name,
                source_endpoint, request_url, request_params,
                http_status_code, x_requests_used, x_requests_remaining,
                raw_json, event_id, sport_key, sport_title,
                commence_time, home_team, away_team
            )
            SELECT
                '{v_ts}'::timestamp_ntz,
                '{v_load_id}',
                'the_odds_api',
                'proc_oddsapi_events',
                '{v_endpoint}',
                '{v_url}',
                PARSE_JSON('{v_params}'),
                {v_status}::int,
                TRY_CAST('{v_used}' AS INT),
                TRY_CAST('{v_remaining}' AS INT),
                PARSE_JSON('{v_json}'),
                NULL, NULL, NULL, NULL, NULL, NULL
        """).collect()

        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', {event_count})"
        ).collect()
        return f'SUCCESS:{event_count}'

    except Exception as e:
        err = str(e)[:400].replace("'", '')
        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected, error_message) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'FAILED', 0, '{err}')"
        ).collect()
        raise
$$;


-- ------------------------------------------------------------
-- 4d. proc_oddsapi_odds
--     Fetches MLB odds (h2h + totals, us + us2) from The Odds API.
--     Appends one row per event per market/region to mlb_odds_raw.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE baseball_data.config.proc_oddsapi_odds()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (daily_ingestion_access_integration)
  SECRETS = ('odds_api_key' = baseball_data.config.odds_api_key)
  HANDLER = 'handler'
  EXECUTE AS OWNER
AS $$
import _snowflake
import requests
import json
import uuid
import time
from datetime import datetime, timezone

def handler(session):
    TASK = 'proc_oddsapi_odds'

    try:
        pred = session.sql("SELECT SYSTEM$GET_PREDECESSOR_RETURN_VALUE()").collect()[0][0]
        if pred is not None and not str(pred).startswith('SUCCESS'):
            session.sql(
                f"INSERT INTO baseball_data.config.pipeline_run_log "
                f"(task_name, run_ts, status, rows_affected, error_message) "
                f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SKIPPED', 0, 'predecessor failed')"
            ).collect()
            return 'SKIPPED'
    except Exception:
        pass

    try:
        api_key   = _snowflake.get_generic_secret_string('odds_api_key')
        load_id   = str(uuid.uuid4())
        now       = datetime.now(timezone.utc)
        endpoint  = '/sports/baseball_mlb/odds'
        markets   = ['h2h', 'totals']
        regions   = ['us', 'us2']
        total_inserted = 0

        def esc(v):
            return str(v).replace("'", "''")

        for market in markets:
            for region in regions:
                params = {
                    'apiKey':     api_key,
                    'markets':    market,
                    'regions':    region,
                    'oddsFormat': 'american',
                    'dateFormat': 'iso',
                }
                resp = requests.get(
                    f'https://api.the-odds-api.com/v4{endpoint}',
                    params=params, timeout=30
                )
                resp.raise_for_status()
                events = resp.json() if isinstance(resp.json(), list) else []
                req_params_str = json.dumps({'markets': market, 'regions': region})

                v_ts        = esc(now.isoformat())
                v_load_id   = esc(load_id)
                v_endpoint  = esc(endpoint)
                v_url       = esc(resp.url)
                v_params    = esc(req_params_str)
                v_status    = resp.status_code
                v_used      = esc(resp.headers.get('x-requests-used', ''))
                v_remaining = esc(resp.headers.get('x-requests-remaining', ''))

                for event in events:
                    bookmakers      = event.get('bookmakers')
                    v_json          = esc(json.dumps(event))
                    v_event_id      = esc(event.get('id') or '')
                    v_sport_key     = esc(event.get('sport_key') or '')
                    v_sport_title   = esc(event.get('sport_title') or '')
                    v_commence_time = esc(event.get('commence_time') or '')
                    v_home_team     = esc(event.get('home_team') or '')
                    v_away_team     = esc(event.get('away_team') or '')
                    v_bk_count      = str(len(bookmakers)) if isinstance(bookmakers, list) else ''
                    session.sql(f"""
                        INSERT INTO baseball_data.oddsapi.mlb_odds_raw (
                            ingestion_ts, load_id, source_system, process_name,
                            source_endpoint, request_url, request_params,
                            http_status_code, x_requests_used, x_requests_remaining,
                            raw_json, event_id, sport_key, sport_title,
                            commence_time, home_team, away_team, bookmakers_count
                        )
                        SELECT
                            '{v_ts}'::timestamp_ntz,
                            '{v_load_id}', 'the_odds_api', 'proc_oddsapi_odds',
                            '{v_endpoint}', '{v_url}',
                            PARSE_JSON('{v_params}'),
                            {v_status}::int,
                            TRY_CAST('{v_used}' AS INT),
                            TRY_CAST('{v_remaining}' AS INT),
                            PARSE_JSON('{v_json}'),
                            NULLIF('{v_event_id}', ''),
                            NULLIF('{v_sport_key}', ''),
                            NULLIF('{v_sport_title}', ''),
                            NULLIF('{v_commence_time}', '')::timestamp_ntz,
                            NULLIF('{v_home_team}', ''),
                            NULLIF('{v_away_team}', ''),
                            TRY_CAST(NULLIF('{v_bk_count}', '') AS INT)
                    """).collect()
                    total_inserted += 1

                time.sleep(0.5)

        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', {total_inserted})"
        ).collect()
        return f'SUCCESS:{total_inserted}'

    except Exception as e:
        err = str(e)[:400].replace("'", '')
        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected, error_message) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'FAILED', 0, '{err}')"
        ).collect()
        raise
$$;


-- ------------------------------------------------------------
-- 4e. proc_github_actions_trigger
--     Dispatches dbt_daily_build.yml via GitHub REST API.
--     Returns SUCCESS:1 on HTTP 204, raises on any other status.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE baseball_data.config.proc_github_actions_trigger()
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

REPO_OWNER    = 'charlesclark2'
REPO_NAME     = 'fantasy_baseball'
WORKFLOW_FILE = 'dbt_daily_build.yml'
REF           = 'main'

def handler(session):
    TASK = 'proc_github_actions_trigger'

    try:
        pred = session.sql("SELECT SYSTEM$GET_PREDECESSOR_RETURN_VALUE()").collect()[0][0]
        if pred is not None and not str(pred).startswith('SUCCESS'):
            session.sql(
                f"INSERT INTO baseball_data.config.pipeline_run_log "
                f"(task_name, run_ts, status, rows_affected, error_message) "
                f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SKIPPED', 0, 'predecessor failed')"
            ).collect()
            return 'SKIPPED'
    except Exception:
        pass

    try:
        pat = _snowflake.get_generic_secret_string('github_pat')
        url = (
            f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}'
            f'/actions/workflows/{WORKFLOW_FILE}/dispatches'
        )
        resp = requests.post(
            url,
            json={'ref': REF, 'inputs': {'triggered_by': 'snowflake_task_dag'}},
            headers={
                'Authorization': f'token {pat}',
                'Accept': 'application/vnd.github.v3+json',
            },
            timeout=30
        )

        if resp.status_code != 204:
            raise RuntimeError(
                f'GitHub dispatch returned HTTP {resp.status_code}: {resp.text[:200]}'
            )

        session.sql(
            f"INSERT INTO baseball_data.config.pipeline_run_log "
            f"(task_name, run_ts, status, rows_affected) "
            f"VALUES ('{TASK}', CURRENT_TIMESTAMP(), 'SUCCESS', 1)"
        ).collect()
        return 'SUCCESS:1'

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
-- SECTION 5: Task DAG (all tasks serverless)
-- USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE sets the serverless
-- compute hint — no named warehouse is bound; Snowflake bills
-- by compute-second, not by warehouse-minute.
-- Run after all procedures in Section 4 are created.
-- ============================================================

CREATE OR REPLACE TASK baseball_data.config.task_savant_ingestion
  SCHEDULE = 'USING CRON 0 8 * * * America/New_York'
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
AS CALL baseball_data.config.proc_savant_ingestion();

CREATE OR REPLACE TASK baseball_data.config.task_statsapi_schedule
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_savant_ingestion
AS CALL baseball_data.config.proc_statsapi_schedule();

CREATE OR REPLACE TASK baseball_data.config.task_oddsapi_events
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_statsapi_schedule
AS CALL baseball_data.config.proc_oddsapi_events();

CREATE OR REPLACE TASK baseball_data.config.task_oddsapi_odds
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_oddsapi_events
AS CALL baseball_data.config.proc_oddsapi_odds();

CREATE OR REPLACE TASK baseball_data.config.task_github_actions_trigger
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_oddsapi_odds
AS CALL baseball_data.config.proc_github_actions_trigger();

-- Snowflake Tasks are created SUSPENDED by default.
-- Child tasks must be resumed before the root task (they do not cascade from root).
ALTER TASK baseball_data.config.task_statsapi_schedule RESUME;
ALTER TASK baseball_data.config.task_oddsapi_events RESUME;
ALTER TASK baseball_data.config.task_oddsapi_odds RESUME;
ALTER TASK baseball_data.config.task_github_actions_trigger RESUME;
ALTER TASK baseball_data.config.task_savant_ingestion RESUME;


-- ============================================================
-- TEARDOWN (reverse dependency order)
-- ============================================================

-- ALTER TASK baseball_data.config.task_savant_ingestion SUSPEND;
-- DROP TASK IF EXISTS baseball_data.config.task_github_actions_trigger;
-- DROP TASK IF EXISTS baseball_data.config.task_oddsapi_odds;
-- DROP TASK IF EXISTS baseball_data.config.task_oddsapi_events;
-- DROP TASK IF EXISTS baseball_data.config.task_statsapi_schedule;
-- DROP TASK IF EXISTS baseball_data.config.task_savant_ingestion;
-- DROP PROCEDURE IF EXISTS baseball_data.config.proc_github_actions_trigger();
-- DROP PROCEDURE IF EXISTS baseball_data.config.proc_oddsapi_odds();
-- DROP PROCEDURE IF EXISTS baseball_data.config.proc_oddsapi_events();
-- DROP PROCEDURE IF EXISTS baseball_data.config.proc_statsapi_schedule();
-- DROP PROCEDURE IF EXISTS baseball_data.config.proc_savant_ingestion();
-- DROP TABLE IF EXISTS baseball_data.config.pipeline_run_log;
-- DROP INTEGRATION IF EXISTS daily_ingestion_access_integration;
-- DROP NETWORK RULE IF EXISTS baseball_data.config.daily_ingestion_network_rule;
-- DROP SECRET IF EXISTS baseball_data.config.odds_api_key;
-- DROP SECRET IF EXISTS baseball_data.config.github_pat;
-- DROP ROLE IF EXISTS task_executor_role;
