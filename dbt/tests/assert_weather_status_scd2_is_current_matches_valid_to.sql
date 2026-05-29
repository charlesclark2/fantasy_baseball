select *
from {{ ref('feature_pregame_weather_status') }}
where
    (is_current = true  and valid_to is not null)
    or
    (is_current = false and valid_to is null)
