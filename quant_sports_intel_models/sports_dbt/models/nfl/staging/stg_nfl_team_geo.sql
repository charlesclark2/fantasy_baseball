-- stg_nfl_team_geo — the 32-team static geography + name crosswalk (NFL-N1.0).
--
-- Two jobs, both needed by the N1.0 team-game layer and neither available from a lake source:
--   1. team-CODE → home-stadium (lat, long) — the anchor for the travel-distance feature in
--      dim_nfl_game (NFL has no stadium-coordinates feed; nflverse schedules carry stadium_id +
--      name but no lat/long). Coordinates are the team's PRIMARY home venue 2020–2024.
--   2. full team NAME → code — the Odds API historical feed keys games on full names
--      ("Kansas City Chiefs"), while schedules/pbp use codes ("KC"). stg_nfl_historical_odds and
--      stg_nfl_props_historical normalize through this map (the Washington rename is handled at
--      the odds use-site: both "Washington Commanders" and "Washington Football Team" → WAS).
--
-- ⚠️ STATIC by design (a 32-row reference, not a lake read) — the franchise set is stable and NFL
-- ships no coordinate source. Relocations already resolved to the current venue: LAR & LAC both at
-- SoFi (Inglewood), LV at Allegiant (Las Vegas). `is_dome_home` is INFORMATIONAL only — the
-- authoritative per-game dome flag comes from the game's own `roof` (dim_nfl_game), because a team
-- can play a neutral-site/international game outdoors.
select code, team_name, latitude, longitude, is_dome_home
from (values
    ('ARI', 'Arizona Cardinals',      33.5276, -112.2626, true),
    ('ATL', 'Atlanta Falcons',        33.7554,  -84.4008, true),
    ('BAL', 'Baltimore Ravens',       39.2780,  -76.6227, false),
    ('BUF', 'Buffalo Bills',          42.7738,  -78.7870, false),
    ('CAR', 'Carolina Panthers',      35.2258,  -80.8528, false),
    ('CHI', 'Chicago Bears',          41.8623,  -87.6167, false),
    ('CIN', 'Cincinnati Bengals',     39.0955,  -84.5161, false),
    ('CLE', 'Cleveland Browns',       41.5061,  -81.6995, false),
    ('DAL', 'Dallas Cowboys',         32.7473,  -97.0945, true),
    ('DEN', 'Denver Broncos',         39.7439, -105.0201, false),
    ('DET', 'Detroit Lions',          42.3400,  -83.0456, true),
    ('GB',  'Green Bay Packers',      44.5013,  -88.0622, false),
    ('HOU', 'Houston Texans',         29.6847,  -95.4107, true),
    ('IND', 'Indianapolis Colts',     39.7601,  -86.1639, true),
    ('JAX', 'Jacksonville Jaguars',   30.3239,  -81.6373, false),
    ('KC',  'Kansas City Chiefs',     39.0489,  -94.4839, false),
    ('LV',  'Las Vegas Raiders',      36.0909, -115.1833, true),
    ('LAC', 'Los Angeles Chargers',   33.9535, -118.3392, true),
    ('LAR', 'Los Angeles Rams',       33.9535, -118.3392, true),
    ('MIA', 'Miami Dolphins',         25.9580,  -80.2389, false),
    ('MIN', 'Minnesota Vikings',      44.9736,  -93.2575, true),
    ('NE',  'New England Patriots',   42.0909,  -71.2643, false),
    ('NO',  'New Orleans Saints',     29.9511,  -90.0812, true),
    ('NYG', 'New York Giants',        40.8135,  -74.0745, false),
    ('NYJ', 'New York Jets',          40.8135,  -74.0745, false),
    ('PHI', 'Philadelphia Eagles',    39.9008,  -75.1675, false),
    ('PIT', 'Pittsburgh Steelers',    40.4468,  -80.0158, false),
    ('SF',  'San Francisco 49ers',    37.4033, -121.9694, false),
    ('SEA', 'Seattle Seahawks',       47.5952, -122.3316, false),
    ('TB',  'Tampa Bay Buccaneers',   27.9759,  -82.5033, false),
    ('TEN', 'Tennessee Titans',       36.1665,  -86.7713, false),
    ('WAS', 'Washington Commanders',  38.9077,  -76.8645, false)
) as t(code, team_name, latitude, longitude, is_dome_home)
