Data Quality Issues — Open (baseball_betting_and_fantasy)
All issues below are unresolved. Resolved issues are in `resolved_data_quality_issues_april_2026.md`.

---

## mart_pitch_fielding — Source alignment columns (intentional warns, irresolvable at model layer)

- [ ] `not_null_mart_pitch_fielding_if_fielding_alignment` — if_fielding_alignment has null values (schema.yml:1708)
  - **Findings:** 70,778 of 7,396,560 pitches (0.96%) have null `if_fielding_alignment` in the Statcast source. All are `game_type = 'R'` (regular season). Nulls are a Statcast sensor gap — the alignment tracking system simply did not record data for these pitches. Concentration is highest in early seasons (2015: 4.71%, 2016: 1.89%) and has declined to ~0.1–0.5% in recent years. Cannot be backfilled or corrected — no alignment data exists in the source. Fielder IDs are populated on the same rows, confirming this is an alignment-sensor-specific gap, not a broader tracking failure.
  - **Resolution:** Test intentionally kept at `warn` severity. Cannot be resolved at the model layer — the nulls originate in Baseball Savant's raw data. The nine derived boolean flags (`is_infield_shift`, etc.) now use `coalesce(..., false)` so they are never null; only the raw source strings remain nullable. No further action possible without a source correction from MLB/Statcast.
  - **Resolution Date:** N/A — acknowledged limitation

- [ ] `not_null_mart_pitch_fielding_of_fielding_alignment` — of_fielding_alignment has null values (schema.yml:1718)
  - **Findings:** Same 70,778 rows as `if_fielding_alignment`. Both alignment columns are always null together — there are no pitches where one is null and the other populated. Same root cause and same irresolvable nature.
  - **Resolution:** Test intentionally kept at `warn` severity. Same reasoning as `if_fielding_alignment` above.
  - **Resolution Date:** N/A — acknowledged limitation

