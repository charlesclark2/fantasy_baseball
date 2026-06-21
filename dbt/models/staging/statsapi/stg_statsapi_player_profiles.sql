WITH ranked AS (
    SELECT
        player_id,
        full_name,
        birth_date,
        height_inches,
        weight_lbs,
        primary_position_code,
        active,
        last_fetched_at,
        ROW_NUMBER() OVER (
            PARTITION BY player_id
            ORDER BY last_fetched_at DESC
        ) AS rn
    FROM {{ source('statsapi', 'player_profiles_raw') }}
)

SELECT
    player_id,
    full_name,
    birth_date,
    -- Coerce out-of-range StatsAPI bio values to NULL (placeholder/zero rows from new
    -- player records). accepted_range skips NULLs; downstream clustering imputes.
    -- INC-6 (2026-06-21): a zero-height row exit-1'd the Sunday dbtf build.
    CASE WHEN height_inches BETWEEN 60 AND 84 THEN height_inches END AS height_inches,
    CASE WHEN weight_lbs BETWEEN 130 AND 375 THEN weight_lbs END AS weight_lbs,
    primary_position_code,
    active,
    last_fetched_at
FROM ranked
WHERE rn = 1
