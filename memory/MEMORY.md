# Memory Index

- [Snowflake VARIANT insert pattern](feedback_snowflake_variant_insert.md) — PARSE_JSON/TRY_PARSE_JSON forbidden in any VALUES clause; use INSERT INTO ... SELECT instead
- [No UUID_STRING() as column DEFAULT](feedback_uuid_string.md) — UUID_STRING() in DDL column defaults causes MCP errors; generate UUIDs in Python and pass as bind params
- [DDL conventions — no IF NOT EXISTS on ADD COLUMN](feedback_ddl_no_use_statements.md) — ADD COLUMN IF NOT EXISTS unsupported on this account; also never USE DATABASE/SCHEMA, always fully qualify
- [Dagster runs the pipeline; GitHub Actions runs CI/CD](feedback_no_github_actions.md) — the data pipeline EXECUTES in Dagster (not GH Actions); BUT GitHub Actions IS the live CI/CD path (orchestration_cd.yml + ci.yml + dbt_build_ci.yml + daily_ingestion.yml run tests/deploy on push to main). Do NOT call GH Actions "decommissioned".

<!-- PM prune 2026-07-27: removed 4 stale/dangling index entries whose detail files no longer existed —
     "use dbtf not dbt", "Snowflake via MCP", "AST (not string-search) for import guards" are all canonical
     in CLAUDE.md (the source of truth); the "model-retraining deferral (before card 7M)" entry referenced a
     milestone no longer in the roadmap vocabulary. NOTE: the larger ~20KB MEMORY.md flagged in the E2.6 recap
     is the MODEL SESSION's own Claude Code memory (a separate file, not this repo/memory/ index) — prune that
     one in-session (e.g. via the consolidate-memory skill); it isn't reachable from the PM session. -->
