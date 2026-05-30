SELECT
    player_id,
    full_name,
    birth_date,
    height_inches,
    weight_lbs,
    primary_position_code,
    active,
    last_fetched_at
FROM {{ source('statsapi', 'player_profiles') }}
