---
name: Snowflake VARIANT insert pattern
description: PARSE_JSON/TRY_PARSE_JSON is forbidden in any VALUES clause — use INSERT INTO ... SELECT instead
type: feedback
---

PARSE_JSON and TRY_PARSE_JSON are forbidden in any `VALUES (...)` clause in Snowflake — this applies to both `executemany` and single `cursor.execute()` calls. The error is `002014: Invalid expression [PARSE_JSON(...)] in VALUES clause`.

**Why:** Snowflake's SQL parser rejects function calls in VALUES clauses entirely.

**How to apply:** For inserts into VARIANT columns, always use `INSERT INTO table (...) SELECT ..., PARSE_JSON(%(raw_json)s)` — function calls are valid in a SELECT clause. Never use VALUES when any column requires PARSE_JSON/TRY_PARSE_JSON.
