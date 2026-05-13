# Memory Index

- [Use dbtf not dbt](feedback_dbtf.md) — Always use `dbtf` instead of `dbt` for all commands; project runs dbt-fusion
- [Use Snowflake MCP for queries](feedback_snowflake_mcp.md) — Use `mcp__snowflake__run_snowflake_query` for all Snowflake lookups, never Python scripts
- [Use AST checks for import guards](feedback_ast_import_checks.md) — Plan spec ACs that verify forbidden imports must use `ast.walk`, not string-in-source search
- [Model retraining deferred to pre-7M](project_model_retraining_deferral.md) — All 3 model retrains deferred until before card 7M; NGBoost >1hr each; LogNormal excluded from run_diff
- [Snowflake VARIANT insert pattern](feedback_snowflake_variant_insert.md) — PARSE_JSON/TRY_PARSE_JSON forbidden in any VALUES clause; use INSERT INTO ... SELECT instead
- [No UUID_STRING() as column DEFAULT](feedback_uuid_string.md) — UUID_STRING() in DDL column defaults causes MCP errors; generate UUIDs in Python and pass as bind params
- [DDL conventions — no IF NOT EXISTS on ADD COLUMN](feedback_ddl_no_use_statements.md) — ADD COLUMN IF NOT EXISTS unsupported on this account; also never USE DATABASE/SCHEMA, always fully qualify
