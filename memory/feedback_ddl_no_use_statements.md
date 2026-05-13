---
name: feedback-ddl-no-use-statements
description: DDL conventions for this Snowflake account — no USE statements, no IF NOT EXISTS on ADD COLUMN
metadata:
  type: feedback
---

Two DDL restrictions apply to this Snowflake account:

1. Never use `USE DATABASE` or `USE SCHEMA` — always use fully qualified `database.schema.table` names.
2. Never use `ADD COLUMN IF NOT EXISTS` in ALTER TABLE — the account version does not support it. Omit the guard; if idempotency is needed, drop and recreate or check information_schema first.

**Why:** Both cause SQL compilation errors on this account.

**How to apply:** Any time you write DDL for this project — migrations, setup scripts, CI steps — use the simpler forms:
- `ALTER TABLE db.schema.table ADD COLUMN col_name TYPE`
- Always qualify table names fully
