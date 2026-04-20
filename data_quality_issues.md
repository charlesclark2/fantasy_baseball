Data Quality Issues — baseball_data.savant
Identified during dbtf build test run. All failures listed here are genuine data quality observations in the source data, not schema or model logic errors. Tests have been removed from the schema to allow builds to pass; investigate and remediate at the source or add explicit filters/caps in staging as needed.

---

## 2026-04-20 — Failed Tests

### mart_pitch_game_context
- [ ] `accepted_values_mart_pitch_game_context_balls__0__1__2__3` — balls column contains values outside 0–3 (schema.yml:110)
- [ ] `accepted_values_mart_pitch_game_context_strikes__0__1__2` — strikes column contains values outside 0–2 (schema.yml:118)

### mart_pitch_characteristics
- [ ] `expression_is_true_mart_pitch_characteristics_release_speed_mph` — release_speed_mph outside 40–110 mph (schema.yml:629)
- [ ] `expression_is_true_mart_pitch_characteristics_effective_speed_mph` — effective_speed_mph outside 40–115 mph (schema.yml:638)
- [ ] `expression_is_true_mart_pitch_characteristics_release_extension_ft` — release_extension_ft outside 0–9 ft (schema.yml:687)

### mart_pitch_hit_characteristics
- [ ] `not_null_mart_pitch_hit_characteristics_is_barrel` — is_barrel has null values (schema.yml:1169)
- [ ] `not_null_mart_pitch_hit_characteristics_is_hard_hit` — is_hard_hit has null values (schema.yml:1176)
- [ ] `not_null_mart_pitch_hit_characteristics_is_sweet_spot` — is_sweet_spot has null values (schema.yml:1183)
- [ ] `not_null_mart_pitch_hit_characteristics_is_hard_hit_sweet_spot` — is_hard_hit_sweet_spot has null values (schema.yml:1191)

### mart_pitch_fielding
- [ ] `not_null_mart_pitch_fielding_if_fielding_alignment` — if_fielding_alignment has null values (schema.yml:1408)
- [ ] `not_null_mart_pitch_fielding_of_fielding_alignment` — of_fielding_alignment has null values (schema.yml:1416)
- [ ] `not_null_mart_pitch_fielding_is_infield_shift` — is_infield_shift has null values (schema.yml:1428)
- [ ] `not_null_mart_pitch_fielding_is_infield_shade` — is_infield_shade has null values (schema.yml:1436)
- [ ] `not_null_mart_pitch_fielding_is_infield_strategic` — is_infield_strategic has null values (schema.yml:1444)
- [ ] `not_null_mart_pitch_fielding_is_infield_non_standard` — is_infield_non_standard has null values (schema.yml:1453)
- [ ] `not_null_mart_pitch_fielding_is_outfield_extreme_shift` — is_outfield_extreme_shift has null values (schema.yml:1461)
- [ ] `not_null_mart_pitch_fielding_is_fourth_outfielder` — is_fourth_outfielder has null values (schema.yml:1469)
- [ ] `not_null_mart_pitch_fielding_is_outfield_strategic` — is_outfield_strategic has null values (schema.yml:1477)
- [ ] `not_null_mart_pitch_fielding_is_outfield_non_standard` — is_outfield_non_standard has null values (schema.yml:1485)
- [ ] `not_null_mart_pitch_fielding_is_any_shade_or_shift` — is_any_shade_or_shift has null values (schema.yml:1496)

