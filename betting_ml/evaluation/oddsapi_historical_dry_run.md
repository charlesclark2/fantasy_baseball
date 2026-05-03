# OddsAPI Historical Snapshot Dry-Run

## Recommendation: **PROCEED**

≥50% of qualifying games (67.3%) showed ≥1 pp of intraday home-win-probability movement; historical resolution is sufficient for the line-movement feature track.

---

## Methodology

- **Bookmaker:** draftkings
- **Dates sampled (12):** 2024-04-15, 2024-05-10, 2024-06-20, 2024-07-25, 2024-08-30, 2024-09-20, 2025-04-12, 2025-05-06, 2025-06-25, 2025-07-20, 2025-08-28, 2025-09-15
- **Timestamps queried (UTC):** 12:00, 17:00, 23:00
- **Movement metric:** `abs(home_win_prob_latest − home_win_prob_earliest)`
- **Threshold for ≥1pp:** `abs_movement ≥ 0.01`
- **Proceed gate:** `pct_above_1pp ≥ 0.50`
- **Implied-prob formula:** `|odds| / (|odds| + 100)` for negative odds; `100 / (odds + 100)` for positive

---

## Per-Game Results

| Date | Home | Away | Earliest Prob | Latest Prob | Abs Movement | ≥1pp |
|------|------|------|:-------------:|:-----------:|:------------:|:----:|
| 2024-04-15 | Baltimore Orioles | Minnesota Twins | 0.608 | 0.775 | 0.167 | yes |
| 2024-04-15 | Boston Red Sox | Cleveland Guardians | 0.574 | 0.574 | 0.000 | no |
| 2024-04-15 | Chicago White Sox | Kansas City Royals | 0.385 | 0.413 | 0.029 | yes |
| 2024-04-15 | Detroit Tigers | Texas Rangers | 0.495 | 0.535 | 0.040 | yes |
| 2024-04-15 | Miami Marlins | San Francisco Giants | 0.495 | 0.556 | 0.061 | yes |
| 2024-04-15 | Milwaukee Brewers | San Diego Padres | 0.495 | 0.541 | 0.046 | yes |
| 2024-04-15 | New York Mets | Pittsburgh Pirates | 0.556 | 0.556 | 0.000 | no |
| 2024-04-15 | Philadelphia Phillies | Colorado Rockies | 0.726 | 0.737 | 0.011 | yes |
| 2024-04-15 | Tampa Bay Rays | Los Angeles Angels | 0.630 | 0.683 | 0.053 | yes |
| 2024-04-15 | Toronto Blue Jays | New York Yankees | 0.535 | 0.535 | 0.000 | no |
| 2024-05-10 | Baltimore Orioles | Arizona Diamondbacks | 0.574 | 0.574 | 0.000 | no |
| 2024-05-10 | Boston Red Sox | Washington Nationals | 0.672 | 0.692 | 0.020 | yes |
| 2024-05-10 | Chicago White Sox | Cleveland Guardians | 0.519 | 0.541 | 0.022 | yes |
| 2024-05-10 | Detroit Tigers | Houston Astros | 0.467 | 0.524 | 0.057 | yes |
| 2024-05-10 | Miami Marlins | Philadelphia Phillies | 0.370 | 0.379 | 0.008 | no |
| 2024-05-10 | New York Mets | Atlanta Braves | 0.435 | 0.446 | 0.012 | yes |
| 2024-05-10 | Pittsburgh Pirates | Chicago Cubs | 0.587 | 0.565 | 0.022 | yes |
| 2024-05-10 | Tampa Bay Rays | New York Yankees | 0.467 | 0.488 | 0.021 | yes |
| 2024-05-10 | Toronto Blue Jays | Minnesota Twins | 0.545 | 0.535 | 0.011 | yes |
| 2024-06-20 | Chicago White Sox | Houston Astros | 0.413 | 0.400 | 0.013 | yes |
| 2024-06-20 | Cleveland Guardians | Seattle Mariners | 0.524 | 0.565 | 0.041 | yes |
| 2024-06-20 | Colorado Rockies | Los Angeles Dodgers | 0.357 | 0.357 | 0.000 | no |
| 2024-06-20 | Minnesota Twins | Tampa Bay Rays | 0.565 | 0.587 | 0.022 | yes |
| 2024-06-20 | New York Yankees | Baltimore Orioles | 0.597 | 0.597 | 0.000 | no |
| 2024-06-20 | Oakland Athletics | Kansas City Royals | 0.435 | 0.435 | 0.000 | no |
| 2024-06-20 | St. Louis Cardinals | San Francisco Giants | 0.545 | 0.505 | 0.041 | yes |
| 2024-06-20 | Washington Nationals | Arizona Diamondbacks | 0.587 | 0.587 | 0.000 | no |
| 2024-07-25 | Cleveland Guardians | Detroit Tigers | 0.643 | 0.597 | 0.046 | yes |
| 2024-07-25 | Los Angeles Dodgers | San Francisco Giants | 0.574 | 0.556 | 0.019 | yes |
| 2024-07-25 | Miami Marlins | Baltimore Orioles | 0.317 | 0.062 | 0.255 | yes |
| 2024-07-25 | New York Mets | Atlanta Braves | 0.476 | 0.524 | 0.048 | yes |
| 2024-07-25 | Texas Rangers | Chicago White Sox | 0.721 | 0.714 | 0.006 | no |
| 2024-07-25 | Toronto Blue Jays | Tampa Bay Rays | 0.519 | 0.528 | 0.009 | no |
| 2024-07-25 | Washington Nationals | San Diego Padres | 0.394 | n/a | n/a | n/a |
| 2024-08-30 | Cincinnati Reds | Milwaukee Brewers | 0.574 | 0.545 | 0.029 | yes |
| 2024-08-30 | Cleveland Guardians | Pittsburgh Pirates | 0.630 | 0.608 | 0.022 | yes |
| 2024-08-30 | Detroit Tigers | Boston Red Sox | 0.476 | 0.394 | 0.082 | yes |
| 2024-08-30 | New York Yankees | St. Louis Cardinals | 0.630 | 0.658 | 0.028 | yes |
| 2024-08-30 | Philadelphia Phillies | Atlanta Braves | 0.574 | 0.583 | 0.009 | no |
| 2024-08-30 | Tampa Bay Rays | San Diego Padres | 0.556 | 0.565 | 0.010 | no |
| 2024-08-30 | Washington Nationals | Chicago Cubs | 0.424 | 0.476 | 0.052 | yes |
| 2024-09-20 | Baltimore Orioles | Detroit Tigers | 0.664 | 0.618 | 0.046 | yes |
| 2024-09-20 | Boston Red Sox | Minnesota Twins | 0.519 | 0.495 | 0.024 | yes |
| 2024-09-20 | Chicago Cubs | Washington Nationals | 0.630 | 0.630 | 0.000 | no |
| 2024-09-20 | Cincinnati Reds | Pittsburgh Pirates | 0.556 | 0.667 | 0.111 | yes |
| 2024-09-20 | Miami Marlins | Atlanta Braves | 0.370 | 0.357 | 0.013 | yes |
| 2024-09-20 | New York Mets | Philadelphia Phillies | 0.524 | 0.505 | 0.019 | yes |
| 2024-09-20 | Tampa Bay Rays | Toronto Blue Jays | 0.535 | 0.545 | 0.011 | yes |
| 2025-04-12 | Baltimore Orioles | Toronto Blue Jays | 0.565 | 0.890 | 0.325 | yes |
| 2025-04-12 | Chicago White Sox | Boston Red Sox | 0.424 | 0.556 | 0.132 | yes |
| 2025-04-12 | Cincinnati Reds | Pittsburgh Pirates | 0.565 | 0.574 | 0.009 | no |
| 2025-04-12 | Cleveland Guardians | Kansas City Royals | 0.574 | 0.574 | 0.000 | no |
| 2025-04-12 | Houston Astros | Los Angeles Angels | 0.597 | 0.618 | 0.022 | yes |
| 2025-04-12 | Miami Marlins | Washington Nationals | 0.597 | 0.980 | 0.383 | yes |
| 2025-04-12 | Minnesota Twins | Detroit Tigers | 0.541 | 0.597 | 0.055 | yes |
| 2025-04-12 | New York Yankees | San Francisco Giants | 0.574 | 0.574 | 0.000 | no |
| 2025-04-12 | Oakland Athletics | New York Mets | 0.467 | 0.455 | 0.013 | yes |
| 2025-04-12 | St. Louis Cardinals | Philadelphia Phillies | 0.424 | 0.408 | 0.016 | yes |
| 2025-04-12 | Tampa Bay Rays | Atlanta Braves | 0.597 | 0.345 | 0.252 | yes |
| 2025-05-06 | Atlanta Braves | Cincinnati Reds | 0.686 | 0.692 | 0.007 | no |
| 2025-05-06 | Boston Red Sox | Texas Rangers | 0.495 | 0.512 | 0.017 | yes |
| 2025-05-06 | Chicago Cubs | San Francisco Giants | 0.597 | 0.608 | 0.011 | yes |
| 2025-05-06 | Kansas City Royals | Chicago White Sox | 0.697 | 0.721 | 0.024 | yes |
| 2025-05-06 | Miami Marlins | Los Angeles Dodgers | 0.308 | 0.278 | 0.030 | yes |
| 2025-05-06 | Milwaukee Brewers | Houston Astros | 0.535 | 0.556 | 0.021 | yes |
| 2025-05-06 | Minnesota Twins | Baltimore Orioles | 0.618 | 0.636 | 0.018 | yes |
| 2025-05-06 | New York Yankees | San Diego Padres | 0.524 | 0.565 | 0.041 | yes |
| 2025-05-06 | St. Louis Cardinals | Pittsburgh Pirates | 0.476 | 0.500 | 0.024 | yes |
| 2025-05-06 | Tampa Bay Rays | Philadelphia Phillies | 0.495 | 0.476 | 0.019 | yes |
| 2025-05-06 | Washington Nationals | Cleveland Guardians | 0.495 | 0.512 | 0.017 | yes |
| 2025-06-25 | Baltimore Orioles | Texas Rangers | 0.448 | 0.465 | 0.017 | yes |
| 2025-06-25 | Chicago White Sox | Arizona Diamondbacks | 0.459 | 0.437 | 0.022 | yes |
| 2025-06-25 | Cincinnati Reds | New York Yankees | 0.364 | 0.368 | 0.004 | no |
| 2025-06-25 | Cleveland Guardians | Toronto Blue Jays | 0.524 | 0.692 | 0.168 | yes |
| 2025-06-25 | Detroit Tigers | Oakland Athletics | 0.625 | 0.623 | 0.003 | no |
| 2025-06-25 | Kansas City Royals | Tampa Bay Rays | 0.490 | 0.481 | 0.009 | no |
| 2025-06-25 | Los Angeles Angels | Boston Red Sox | 0.559 | 0.569 | 0.009 | no |
| 2025-06-25 | Milwaukee Brewers | Pittsburgh Pirates | 0.531 | 0.524 | 0.007 | no |
| 2025-06-25 | Minnesota Twins | Seattle Mariners | 0.567 | 0.548 | 0.020 | yes |
| 2025-06-25 | New York Mets | Atlanta Braves | 0.609 | 0.590 | 0.019 | yes |
| 2025-06-25 | San Diego Padres | Washington Nationals | 0.609 | 0.600 | 0.009 | no |
| 2025-06-25 | St. Louis Cardinals | Chicago Cubs | 0.469 | 0.439 | 0.031 | yes |
| 2025-07-20 | Arizona Diamondbacks | St. Louis Cardinals | 0.597 | 0.609 | 0.013 | yes |
| 2025-07-20 | Atlanta Braves | New York Yankees | 0.569 | 0.569 | 0.000 | no |
| 2025-07-20 | Chicago Cubs | Boston Red Sox | 0.459 | 0.467 | 0.009 | no |
| 2025-07-20 | Cleveland Guardians | Oakland Athletics | 0.567 | 0.515 | 0.053 | yes |
| 2025-07-20 | Colorado Rockies | Minnesota Twins | 0.338 | 0.337 | 0.001 | no |
| 2025-07-20 | Los Angeles Dodgers | Milwaukee Brewers | 0.611 | 0.621 | 0.010 | yes |
| 2025-07-20 | Miami Marlins | Kansas City Royals | 0.490 | 0.507 | 0.017 | yes |
| 2025-07-20 | New York Mets | Cincinnati Reds | 0.602 | 0.587 | 0.015 | yes |
| 2025-07-20 | Philadelphia Phillies | Los Angeles Angels | 0.649 | 0.640 | 0.009 | no |
| 2025-07-20 | Pittsburgh Pirates | Chicago White Sox | 0.587 | 0.597 | 0.010 | no |
| 2025-07-20 | Seattle Mariners | Houston Astros | 0.556 | 0.588 | 0.033 | yes |
| 2025-07-20 | Tampa Bay Rays | Baltimore Orioles | 0.559 | 0.175 | 0.384 | yes |
| 2025-07-20 | Texas Rangers | Detroit Tigers | 0.365 | 0.408 | 0.043 | yes |
| 2025-07-20 | Toronto Blue Jays | San Francisco Giants | 0.524 | 0.597 | 0.073 | yes |
| 2025-07-20 | Washington Nationals | San Diego Padres | 0.490 | 0.490 | 0.000 | no |
| 2025-08-28 | Baltimore Orioles | Boston Red Sox | 0.391 | 0.375 | 0.016 | yes |
| 2025-08-28 | Chicago White Sox | New York Yankees | 0.382 | 0.394 | 0.012 | yes |
| 2025-08-28 | Houston Astros | Colorado Rockies | 0.705 | 0.716 | 0.011 | yes |
| 2025-08-28 | Milwaukee Brewers | Arizona Diamondbacks | 0.625 | 0.621 | 0.004 | no |
| 2025-08-28 | New York Mets | Miami Marlins | 0.722 | 0.731 | 0.009 | no |
| 2025-08-28 | Philadelphia Phillies | Atlanta Braves | 0.659 | 0.602 | 0.057 | yes |
| 2025-08-28 | San Francisco Giants | Chicago Cubs | 0.526 | 0.522 | 0.005 | no |
| 2025-08-28 | St. Louis Cardinals | Pittsburgh Pirates | 0.552 | 0.559 | 0.008 | no |
| 2025-09-15 | Chicago White Sox | Baltimore Orioles | 0.439 | 0.459 | 0.020 | yes |
| 2025-09-15 | Minnesota Twins | New York Yankees | 0.389 | 0.382 | 0.007 | no |
| 2025-09-15 | Pittsburgh Pirates | Chicago Cubs | 0.469 | 0.507 | 0.038 | yes |
| 2025-09-15 | St. Louis Cardinals | Cincinnati Reds | 0.558 | 0.531 | 0.027 | yes |
| 2025-09-15 | Tampa Bay Rays | Toronto Blue Jays | 0.481 | 0.481 | 0.000 | no |
| 2025-09-15 | Washington Nationals | Atlanta Braves | 0.439 | 0.483 | 0.044 | yes |

---

## Aggregate Summary

| Metric | Value |
|--------|-------|
| n_games_sampled | 110 |
| mean_abs_movement | 0.0383 |
| pct_above_1pp | 67.3% |
| recommendation | PROCEED |
