# FanGraphs Pipeline Validation — Season 2026

**Date:** 2026-05-02  
**Overall:** PASS

## Raw Table Row Counts

| Table | Rows | Status |
|-------|------|--------|
| fg_stuff_plus_raw | 63469 | PASS |
| fg_zips_pitching_raw | 18569 | PASS |
| fg_zips_hitting_raw | 17326 | PASS |
| fg_hitting_leaderboard_raw | 242155 | PASS |

Hitting leaderboard window types present: ['14d', '30d', '7d', 'season']

## MLBAM ID Join Rate (ZiPS Pitchers)

- Total ZiPS pitchers (season=2026): 1042
- Matched to ref_players: 1004
- Unmatched: 38
- Match rate: 96.35%  **PASS**

### Unmatched Pitchers (sample)

| Name | MLBAM ID |
|------|----------|
| Alex Hoppe | 695380 |
| Andrew Morris | 702193 |
| Andrew Painter | 691725 |
| Anthony Nunez | 689296 |
| Brian Fitzpatrick | 702153 |
| Cameron Foster | 671382 |
| Carter Baumler | 691945 |
| Coleman Crow | 689441 |
| Connor Prielipp | 687570 |
| Duncan Davitt | 701474 |
| Eduardo Rivera | 700842 |
| Elmer Rodríguez | 695684 |
| Gavin Collyer | 686560 |
| George Klassen | 691946 |
| JR Ritchie | 702275 |
| Jack Anderson | 681252 |
| Jake Bennett | 687562 |
| Jedixson Paez | 699151 |
| Jose Franco | 683742 |
| Kendry Rojas | 696070 |

## Stuff+ Null Rate (Staging)

- Total pitchers in stg_fangraphs__stuff_plus (season=2026): 549
- Null stuff_plus: 0
- Null rate: 0.0%  **PASS**

## Mart Model Duplicate Grain Checks

- fct_fangraphs_pitching_analytics: 0 duplicate grains  **PASS**
- fct_fangraphs_hitting_analytics: 0 duplicate grains  **PASS**

## Known Gaps

- **MLBAM join rate (MLB-active pitchers only)**: ZiPS projects minor league and prospect pitchers
  whose `fg_pitcher_id` has an 'sa' prefix. These players have no MLB appearances and are absent
  from `savant.ref_players`. The join rate check excludes 'sa'-prefixed IDs to measure only
  MLB-active pitchers, where ≥95% match is expected.
- ZiPS CSV projections do not include K% or BB% directly (K/9 and BB/9 are available instead).
- xFIP is not included in ZiPS CSV exports; proj_xfip will be null for CSV-sourced rows.
- Stuff+ rolling windows (14d, 30d) are stored in raw table but staging dedups to one row per pitcher×season.
