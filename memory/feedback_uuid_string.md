---
name: feedback-uuid-string
description: UUID_STRING() Snowflake function causes MCP errors — do not use as a column DEFAULT in DDL
metadata:
  type: feedback
---

Never use `UUID_STRING()` as a column DEFAULT value in Snowflake DDL run via any tooling.

**Why:** Causes "Cannot set properties of undefined (setting 'TOKEN')" errors when executed. Consistent failure across attempts.

**How to apply:** In ALTER TABLE / CREATE TABLE statements, leave UUID/load_id columns with no DEFAULT or use `DEFAULT NULL`. Python-side code should generate UUIDs via `uuid.uuid4()` and pass them as explicit bind parameters on every INSERT.
