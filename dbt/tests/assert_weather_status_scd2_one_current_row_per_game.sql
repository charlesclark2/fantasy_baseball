select game_pk, count(*) as current_row_count
from {{ ref('feature_pregame_weather_status') }}
where is_current = true
group by game_pk
having count(*) > 1
