# NF-D8 — Contract / financial feature source (salary as a team-investment proxy)

**Generated:** 2026-07-27T07:14:04.160996+00:00. Data source: nflverse's `historical_contracts.parquet` release (CC-BY-4.0), NOT a direct OverTheCap/Spotrac scrape — see the disposition note below. Edge-independent, `best_alpha=0` — a projection FEATURE for NF1.2/NF1.5, not an edge claim.

## 1. Dataset probe

- 51734 contracts, `gsis_id` coverage (all-time) 0.919
- positions: ['C', 'CB', 'ED', 'FB', 'IDL', 'K', 'LB', 'LG', 'LS', 'LT', 'P', 'QB', 'RB', 'RG', 'RT', 'S', 'TE', 'WR']
- unmapped team nicknames: []

## 2. Per-season coverage + face-validity

Join match-rate = our skill-position (QB/RB/WR/TE) `fct_player_week` universe matched to a contract row for that season (the `sport_data_platform.md` crosswalk check).

| season | contract rows | skill players (ours) | matched | % matched | QB | RB | WR | TE |
|--------|---------------|-----------------------|---------|-----------|----|----|----|----|
| 2022 | 2505 | 617 | 601 | 97.4 | 0.988 | 0.948 | 0.972 | 1.0 |
| 2023 | 2533 | 600 | 589 | 98.2 | 1.0 | 0.967 | 0.983 | 0.985 |
| 2024 | 2583 | 602 | 597 | 99.2 | 1.0 | 1.0 | 0.984 | 0.992 |
| 2025 | 2630 | 628 | 621 | 98.9 | 1.0 | 0.993 | 0.976 | 1.0 |
| 2026 | 2223 | 0 | 0 | None | — | — | — | — |

### Face-validity (2026) — top O-line cap investment

| team | O-line cap ($M) | % of team cap |
|------|-----------------|---------------|
| CAR | 95.1 | 0.32 |
| DEN | 75.12 | 0.26 |
| KC | 74.05 | 0.26 |
| LAR | 71.64 | 0.24 |
| ATL | 71.28 | 0.29 |

### Face-validity (2026) — most cap-CONCENTRATED skill-position rooms (HHI)

| team | skill-cap HHI | skill cap total ($M) |
|------|---------------|------------------------|
| LAC | 0.33 | 82.604 |
| CLE | 0.327 | 74.767 |
| BAL | 0.255 | 72.965 |
| TB | 0.247 | 107.278 |
| KC | 0.235 | 75.982 |

## 3. Honest gaps

- A rookie drafted for a projection season may not yet appear in the nflverse contracts release if it hasn't been refreshed since the draft — a preseason board built too early in the cycle will show that player with no contract row (NaN features, not a fabricated 0). Re-run `--refresh` closer to Week 1.
- `gsis_id` is null for ~8% of all-time contract rows (mostly non-skill positions / very old / retired players outside our skill-position universe) — the join-match-rate table above is the number that actually matters (QB/RB/WR/TE, current era).
- Mid-season restructures are not captured intra-season — this is a snapshot read at ingest time, not a point-in-time-versioned history; a restructure changes a future year's cap number, which the next `--refresh` will pick up.
- `team_total_cap` / `team_*_cap_*` are computed by SUMMING this dataset's own listed contracts per team-season — a proxy for the team's real accounted cap (practice-squad / minimum-tender players not carrying a filed contract row are undercounted), not the league's official cap-compliance number.

## Disposition

- **Ship:** `contract_source.load_contract_features(season)` — per-player cap hit / base salary / guaranteed $ / `guaranteed_ratio` / `log_investment` WITH the team's O-line-cap and skill-cap-concentration aggregates merged in; `load_team_cap_aggregates(season)` for the team table alone. Landed to `nfl/fantasy/contracts/player_contract_features` + `nfl/fantasy/contracts/team_cap_aggregates` (season-partitioned Delta).
- **Source:** nflverse's `historical_contracts.parquet` release (CC-BY-4.0), not a direct OverTheCap/Spotrac scrape — overthecap.com's `robots.txt` explicitly disallows the Anthropic-AI crawler and Spotrac hard-blocks automated fetches (both probed live 2026-07-27), so this session did not build a scraper against either site. nflverse already fetches + redistributes the same OTC contract data under an open license, and is the SAME upstream vendor this repo already reads pbp/rosters/snap_counts from — a trusted, terms-compliant substitute with a strictly better join key (`gsis_id`, not a fuzzy name crosswalk).
- Leakage-safe: only contracts signed on/before the projection season are used (free-agent/rookie deals are public well before Week 1). `best_alpha=0` — delivered as CANDIDATE features; the lift is proven in NF1.2/NF1.5's ablation under deflation, not here.

