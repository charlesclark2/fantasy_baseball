{% macro scd2_merge(target, source, natural_key_cols, payload_cols) %}
{#
    SCD-2 merge operation for dbt-managed tables (Stories 2.6, 2.9+).

    Executes two statements:
      1. Close out current rows in `target` whose payload hash differs from `source`.
      2. Insert new current rows for natural keys with no surviving current row.

    Parameters
    ----------
    target           : Fully-qualified target table name (string)
    source           : Fully-qualified source table or CTE name (string)
    natural_key_cols : List of column names forming the natural key
    payload_cols     : List of payload columns used in record_hash computation

    record_hash formula: MD5(CONCAT_WS('|', COALESCE(col::VARCHAR, '') ...))
    This matches the Python scd2_writer._record_hash() function exactly.

    Usage (run-operation):
        dbtf run-operation scd2_merge --args '{
            "target": "baseball_data.betting.my_mart",
            "source": "baseball_data.betting_features.my_staging",
            "natural_key_cols": ["game_pk", "side"],
            "payload_cols": ["col_a", "col_b"]
        }'

    See scd2_convention.md for the full convention and AS-OF query pattern.
#}

{%- set hash_parts = [] -%}
{%- for col in payload_cols -%}
    {%- do hash_parts.append("COALESCE(s." ~ col ~ "::VARCHAR, '')") -%}
{%- endfor -%}

{%- set key_join_parts = [] -%}
{%- for col in natural_key_cols -%}
    {%- do key_join_parts.append("t." ~ col ~ " = s." ~ col) -%}
{%- endfor -%}

{%- set hash_expr = "MD5(CONCAT_WS('|', " ~ hash_parts | join(', ') ~ "))" -%}
{%- set key_join = key_join_parts | join(' AND ') -%}

-- Step 1: close out current rows whose payload has changed
UPDATE {{ target }} t
SET
    valid_to   = CURRENT_TIMESTAMP()::TIMESTAMP_NTZ,
    is_current = FALSE
FROM {{ source }} s
WHERE {{ key_join }}
  AND t.is_current  = TRUE
  AND t.record_hash != {{ hash_expr }};

-- Step 2: insert new current rows (new natural key or just closed out above)
INSERT INTO {{ target }} (
    {{ natural_key_cols | join(', ') }},
    {{ payload_cols | join(', ') }},
    computed_at, valid_from, valid_to, is_current, record_hash
)
SELECT
    s.{{ natural_key_cols | join(', s.') }},
    s.{{ payload_cols | join(', s.') }},
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ,
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ,
    NULL,
    TRUE,
    {{ hash_expr }}
FROM {{ source }} s
LEFT JOIN {{ target }} t
    ON {{ key_join }}
    AND t.is_current = TRUE
WHERE t.{{ natural_key_cols[0] }} IS NULL;

{% endmacro %}
