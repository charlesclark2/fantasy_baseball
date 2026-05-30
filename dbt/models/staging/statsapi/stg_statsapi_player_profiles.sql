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
    height_inches,
    weight_lbs,
    primary_position_code,
    active,
    last_fetched_at
FROM ranked
WHERE rn = 1
