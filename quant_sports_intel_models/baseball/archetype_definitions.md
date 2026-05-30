# Archetype Definitions

**Source tables:** `baseball_data.statsapi.batter_clusters`, `baseball_data.statsapi.pitcher_clusters`  
**Generated:** 2026-05-29 (Stories 7.1 + 7.2 revalidation — supersedes Story 2.9 prototype)  
**Downstream consumer:** `matchup_v1` training target — `mart_batter_archetype_vs_pitcher_cluster`

---

## Important notes on cluster stability

- Cluster `cluster_id` values are **not stable across seasons** — the same integer can map to different archetypes in different years. Always join on `cluster_label`, not `cluster_id`.
- Batter and pitcher season coverage begins **2015** (12 seasons through 2026, min 100 PA / 100 BF). Cross-season pooled k-means is fit once on all seasons simultaneously — per-season fitting caused local optima and label instability.
- **Silhouette score ceiling:** Baseball players form a continuum in feature space; discrete cluster separation is inherently limited. The realistic achievable silhouette is ~0.10–0.11. Batters achieved 0.1047 at k=5; pitchers achieved 0.1055 at k=5.
- **Stratum-A / stratum-B feature split:** Stratum-B features are excluded when they have era discontinuities that would dominate cluster geometry. Batters: bat speed/attack angle excluded (0 for 2020–2022, 1 for 2023+). Pitchers: `fb_arm_angle` (0% populated pre-2020) and `overall_stuff_plus` (FanGraphs Stuff+, only 2020+) excluded. Stratum-A features are consistent across all 12 seasons.
- Clusters with < 50 members in a season produce noisy population-level matchup estimates. Flag these in training by filtering to seasons where the cluster has ≥ 50 members.
- **Pitcher archetypes: 5, not 6.** `elite_breaking_ball` is retired as of Story 7.2. Without stratum-B features, elite breaking-ball pitchers are indistinguishable from `power_swing_and_miss` on outcomes (K%, whiff) and pitch mix (breaking%). They correctly merge into a single high-strikeout cluster.

---

## Batter archetypes

Five batter archetypes derived from Statcast swing and batted-ball profile features.

### `power_pull`

**Feature drivers:** High pull rate, above-average exit velocity, high hard-hit%, elevated HR rate, elevated K% (accepted tradeoff for raw power).

**Offensive profile:** Pull-side power threat. Generates extra-base hits and home runs at high rates. Vulnerable to inside fastballs and breaking balls away, which limit contact to weaker pull-side outcomes. High leverage against pitchers with limited arm-side movement.

**Example players (2024/2025):** Pete Alonso, Aaron Judge, Freddie Freeman, Paul Goldschmidt (most seasons)

**Matchup signal:** Elevated wOBA against `changeup_deceptive` and `soft_command` pitchers; suppressed against `power_swing_and_miss` who can bust hands with velocity.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 58      |
| 2016   | 76      |
| 2017   | 85      |
| 2018   | 76      |
| 2019   | 118     |
| 2020   | 93      |
| 2021   | 93      |
| 2022   | 57      |
| 2023   | 76      |
| 2024   | 56      |
| 2025   | 65      |
| 2026   | 49      |

⚠️ 2026: 49 members (partial season — expected). All complete seasons ≥ 50. Stable archetype.

---

### `patient_obp`

**Feature drivers:** Above-average walk rate, below-average K%, high contact rate, tendency to work counts, below-average pull rate.

**Offensive profile:** On-base specialist. Generates value through walks and line-drive singles rather than power. Difficult to strike out, especially effective against pitchers who fall behind in counts. Less dangerous against elite strikeout pitchers who don't need the zone.

**Example players (2024/2025):** Mookie Betts, Steven Kwan, Juan Soto (some seasons)

**Matchup signal:** Elevated wOBA against `soft_command` (control pitchers who must throw strikes); suppressed against `power_swing_and_miss` (high K-rate overpowers contact approach).

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 69      |
| 2016   | 73      |
| 2017   | 72      |
| 2018   | 72      |
| 2019   | 50      |
| 2020   | 44      |
| 2021   | 73      |
| 2022   | 63      |
| 2023   | 82      |
| 2024   | 68      |
| 2025   | 80      |
| 2026   | 79      |

⚠️ 2020: 44 members (COVID short season — expected). 2019: 50 (at threshold floor). All other seasons ≥ 50.

---

### `high_whiff`

**Feature drivers:** High K%, high swinging-strike rate, aggressive zone coverage, below-average contact rate, often elevated pull rate.

**Offensive profile:** Boom-or-bust hitter. When making contact, can generate hard-hit balls, but frequency is low. Highly exploitable by pitchers with swing-and-miss stuff; less impacted by control-first pitchers. Common in lower lineup slots.

**Example players (2024):** Paul DeJong, Jake Cave, Elehuris Montero, Jacob Stallings

**Matchup signal:** Suppressed wOBA against `power_swing_and_miss` and `elite_breaking_ball`; elevated against `contact_sinker_ball` and `soft_command` who rely on weak contact rather than strikeouts.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 71      |
| 2016   | 80      |
| 2017   | 85      |
| 2018   | 96      |
| 2019   | 105     |
| 2020   | 60      |
| 2021   | 110     |
| 2022   | 124     |
| 2023   | 117     |
| 2024   | 125     |
| 2025   | 106     |
| 2026   | 58      |

All seasons ≥ 50. Most stable archetype by count consistency.

---

### `groundball_speed`

**Feature drivers:** High groundball rate, above-average sprint speed, below-average fly-ball rate and HR rate. Contact-oriented; value derives from beating out grounders and legging out hits.

**Offensive profile:** Speed/contact hitter. Low extra-base hit rate but high BABIP due to speed. Most effective on turf and in spacious ballparks where grounders find holes. Less impacted by pitcher raw stuff; more impacted by infield alignment and park.

**Example players (2024):** Johan Rojas, Tim Anderson, Gio Urshela, Michael Siani

**Matchup signal:** Least differentiated matchup signal of all archetypes — performance driven more by ballpark/turf context than pitcher cluster. Slightly elevated against `power_swing_and_miss` (fewer strikeouts means more balls in play).

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 134     |
| 2016   | 110     |
| 2017   | 96      |
| 2018   | 79      |
| 2019   | 78      |
| 2020   | 51      |
| 2021   | 86      |
| 2022   | 106     |
| 2023   | 80      |
| 2024   | 82      |
| 2025   | 86      |
| 2026   | 52      |

All seasons ≥ 50. Stable archetype.

---

### `contact_spray`

**Feature drivers:** Low K%, balanced pull/center/oppo spray rate, above-average contact rate, line-drive tendency, moderate exit velocity.

**Offensive profile:** High-contact, all-fields hitter. Hits for average with moderate power. Difficult to exploit via pitch location since they use the whole field. Effective against both left- and right-handed pitching. Lower ceiling than `power_pull` but higher floor.

**Example players (2024/2025):** Trea Turner, Bo Bichette, Paul Goldschmidt (2024–2025)

**Matchup signal:** Moderate, positive wOBA contribution across most pitcher archetypes. Least suppressed by `power_swing_and_miss` due to contact discipline.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 113     |
| 2016   | 99      |
| 2017   | 97      |
| 2018   | 94      |
| 2019   | 101     |
| 2020   | 61      |
| 2021   | 101     |
| 2022   | 119     |
| 2023   | 106     |
| 2024   | 124     |
| 2025   | 124     |
| 2026   | 56      |

All seasons ≥ 50. **Stability flag from Story 2.9 prototype is resolved** — present in all 12 seasons (2015–2026). The prior absence was an artifact of per-season clustering and bat-tracking era discontinuity; cross-season pooled k-means on stratum-A features only resolves it.

---

## Pitcher archetypes

Five pitcher archetypes derived from Statcast pitch-mix, velocity, movement, and outcome features. Story 7.2 revalidation complete (2026-05-29) — 5618 rows, 12 seasons (2015–2026), cross-season pooled k-means (k=5, silhouette=0.1055). `elite_breaking_ball` retired; see notes above.

---

### `power_swing_and_miss`

**Feature drivers:** High breaking ball usage (+0.80 z), above-average fastball velocity (+0.75 z), very high K% (+0.98 z) and whiff rate (+0.98 z). This cluster absorbs pitchers who generate swing-and-miss via any mechanism — high velocity, elite breaking ball, or both. Without Stuff+ and arm_angle (stratum-B), velocity+outcomes dominate and the power/breaking distinction collapses correctly into one archetype.

**Pitching profile:** High-strikeout pitcher. Generates swing-and-miss across multiple pitch types. The largest single-archetype group post-2019. Most valuable in strikeout-predictive contexts (K prop markets, first-5-innings totals).

**Example pitchers (2024/2025):** Dylan Cease, Glasnow, deGrom, Ohtani (pitching seasons), Scherzer (prime), Strider, Bieber (2019–2022)

**Matchup signal:** Strongly suppresses `high_whiff`; modest suppression of `power_pull`; least effective vs `patient_obp` who works counts and avoids chase.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 59      |
| 2016   | 86      |
| 2017   | 96      |
| 2018   | 103     |
| 2019   | 126     |
| 2020   | 51      |
| 2021   | 159     |
| 2022   | 142     |
| 2023   | 152     |
| 2024   | 145     |
| 2025   | 141     |
| 2026   | 50      |

All seasons ≥ 50. ⚠️ 2026: 50 (partial season — at threshold, acceptable). Stable archetype.

---

### `changeup_deceptive`

**Feature drivers:** Very high offspeed usage (+1.48 z), above-average fastball vertical movement (+0.55 z), moderate K% (+0.15 z) and whiff (+0.39 z). Captures splitter-dominant and changeup-first pitchers where the off-speed family is the primary weapon.

**Pitching profile:** Off-speed deception pitcher. Generates weak contact and mis-timed swings via changeup/splitter tunneling. Gausman (splitter) and Alcántara (changeup-heavy prime years 2021–2023) are the prototype members. Performance more dependent on arm-side fade execution than raw velocity.

**Example pitchers (2024/2025):** Gausman (all seasons), Verlander (2024), late-career Scherzer (2023–2025), Hendricks (2024)

**Matchup signal:** Suppresses `power_pull` (pull-side bat path misses the fade); moderate suppression of `high_whiff`; `patient_obp` hitters with good eye make harder contact on changeups left in zone.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 49      |
| 2016   | 49      |
| 2017   | 67      |
| 2018   | 48      |
| 2019   | 73      |
| 2020   | 45      |
| 2021   | 85      |
| 2022   | 79      |
| 2023   | 85      |
| 2024   | 85      |
| 2025   | 95      |
| 2026   | 44      |

⚠️ 2015 (49), 2016 (49), 2018 (48): near-threshold early era — pure off-speed pitchers were less prevalent before the Statcast era drove pitch design. ⚠️ 2020 (45): COVID short season. ⚠️ 2026 (44): partial season. All complete non-COVID seasons 2021+ are ≥ 79. Training should use 2017–2019 and 2021+ for this archetype.

---

### `contact_sinker_ball`

**Feature drivers:** Low K% (−0.67 z), low whiff rate (−0.67 z), above-average groundball rate (+0.35 z), moderate breaking ball usage (+0.20 z), below-average fastball arm-side movement (−0.75 z fb_hmov). Ground-ball-inducing via movement profiles, not strikeout suppression.

**Pitching profile:** Groundball/contact pitcher. Keeps the ball on the ground, limiting hard-hit rates and extra-base hits. Logan Webb is the decade-long prototype (contact_sinker_ball every season 2019–2026). Alcántara (2018–2020, 2025+) also anchors this cluster. Effective when fielding is strong; predictable and low-variance.

**Example pitchers (2024/2025):** Logan Webb (all seasons), Alcántara (2025), early Cole (2015–2017), early Verlander (2015), Bieber (2023+)

**Matchup signal:** Suppresses fly-ball power (`power_pull`); elevated BABIP allowed against `groundball_speed`; predictable performance — low variance.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 158     |
| 2016   | 146     |
| 2017   | 130     |
| 2018   | 122     |
| 2019   | 115     |
| 2020   | 59      |
| 2021   | 95      |
| 2022   | 129     |
| 2023   | 125     |
| 2024   | 137     |
| 2025   | 139     |
| 2026   | 65      |

All seasons ≥ 50. **Prototype stability flags fully resolved** (was 6 members in 2024, absent alternate years). Cross-season pooled k-means eliminated the instability. Stable archetype.

---

### `multi_pitch_mix`

**Feature drivers:** High arm-side horizontal movement (+1.49 z fb_hmov), very negative breaking ball arm-side movement (−1.42 z brk_hmov), below-average velocity (−0.58 z), below-average K% (−0.29 z) and whiff (−0.32 z), moderate groundball rate (+0.23 z). Characterized by sinker/two-seamer heavy arm-side run profile — balanced outcomes, no dominant category.

**Pitching profile:** Sinker-heavy balanced pitcher. Max Fried is the decade-long prototype (multi_pitch_mix every season 2017–2026). Generates moderate ground balls through arm-side run rather than elite movement grades. Below-average strikeout rate; relies on weak contact management. Hardest archetype to scout at population level — high within-cluster variance.

**Example pitchers (2024/2025):** Fried (all seasons), early Glasnow (2016–2019 pre-breaking ball development)

**Matchup signal:** Weakest archetype-level matchup signal — high within-cluster variance. Model should apply lower confidence weight to `multi_pitch_mix` matchup estimates.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 118     |
| 2016   | 99      |
| 2017   | 112     |
| 2018   | 101     |
| 2019   | 111     |
| 2020   | 46      |
| 2021   | 114     |
| 2022   | 105     |
| 2023   | 106     |
| 2024   | 106     |
| 2025   | 105     |
| 2026   | 62      |

⚠️ 2020 (46): COVID short season. All other seasons ≥ 99. **Prototype stability flags fully resolved** (was absent from alternate years). Stable archetype.

---

### `soft_command`

**Feature drivers:** Very high fastball usage (+1.16 z), very low breaking ball usage (−0.76 z), below-average velocity (−0.26 z), low K% (−0.13 z) and whiff (−0.30 z). Fastball-heavy command pitchers who rely on location and sequencing rather than raw stuff.

**Pitching profile:** Command-and-location pitcher. Kyle Hendricks is the decade-long prototype (soft_command every season 2015–2025 except 2023–2024 when his increased changeup use briefly pushed him to `changeup_deceptive`). Survives via precision — misses are punished hard. Effective against aggressive hitters who expand early. Vulnerable to patient lineups.

**Example pitchers (2024/2025):** Hendricks (2025), Cole (2024 — injury year velocity drop), Glasnow (2016–2019 pre-breaking ball)

**Matchup signal:** Strongly permissive against `patient_obp` (patient hitters draw walks and foul off until they get a mistake); moderate wOBA elevation against `power_pull`; best outcomes against `high_whiff` who expand on borderline pitches.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2015   | 114     |
| 2016   | 121     |
| 2017   | 99      |
| 2018   | 103     |
| 2019   | 98      |
| 2020   | 40      |
| 2021   | 95      |
| 2022   | 67      |
| 2023   | 59      |
| 2024   | 42      |
| 2025   | 43      |
| 2026   | 18      |

⚠️ 2020 (40): COVID short season. ⚠️ 2024 (42), 2025 (43): real MLB trend — the league is moving away from command-only starters toward velocity + breaking ball. Fewer pitchers survive at below-average velocity without elite movement. This is not a clustering artifact; it reflects the actual shrinking population of this pitcher type. Use with lower weight for 2024–2025. ⚠️ 2026 (18): partial season.

---

## Cluster stability summary

### Batter archetypes (Story 7.1 revalidation — 5099 rows, 2015–2026, fit 2026-05-29)

All 5 archetypes present in all 12 seasons. `contact_spray` stability flag from Story 2.9 prototype is **resolved**.

Exceptions (expected, not actionable):
| Archetype     | Season | Members | Reason                     |
|---------------|--------|---------|----------------------------|
| `patient_obp` | 2020   | 44      | COVID short season (60 g)  |
| `power_pull`  | 2026   | 49      | Partial season at fit time |

### Pitcher archetypes (Story 7.2 revalidation — 5618 rows, 2015–2026, fit 2026-05-29)

All 5 archetypes present in all 12 seasons. All Story 2.9 prototype stability flags **resolved**.

Exceptions (expected or real-world trend, not actionable):
| Archetype            | Season(s)           | Members | Reason                                      |
|----------------------|---------------------|---------|---------------------------------------------|
| `changeup_deceptive` | 2015, 2016          | 49      | Early era — offspeed-primary pitchers rare  |
| `changeup_deceptive` | 2018                | 48      | Single-year dip; not a trend                |
| `changeup_deceptive` | 2020                | 45      | COVID short season (60 g)                   |
| `multi_pitch_mix`    | 2020                | 46      | COVID short season (60 g)                   |
| `soft_command`       | 2020                | 40      | COVID short season (60 g)                   |
| `soft_command`       | 2024, 2025          | 42, 43  | Real MLB trend — fewer command-only starters; league shifting to velocity + breaking ball |
| `changeup_deceptive` | 2026                | 44      | Partial season at fit time                  |
| `soft_command`       | 2026                | 18      | Partial season at fit time                  |

**Training recommendation:** For `matchup_v1`, restrict training to `(cluster_label, season)` pairs where `member_count >= 50`. Apply lower confidence weight to `soft_command` matchup estimates for 2024–2025 (real shrinking population, not instability).

---

## Story 7.1 revalidation — batter archetypes ✅ Complete (2026-05-29)

**Key decisions:**

1. **Cross-season pooled k-means** — single model fit on all seasons simultaneously. Per-season fitting caused local optima and the `contact_spray` stability collapse seen in the Story 2.9 prototype.
2. **Bat tracking features excluded (stratum B)** — `bat_tracking_available` is 0 for 2020–2022 and 1 for 2023+; including them created a hard era boundary that dominated cluster geometry. 11 stratum-A features used exclusively.
3. **Silhouette ceiling documented** — realistic ceiling ~0.10–0.11; achieved 0.1047 at k=5. The 0.30 AC target was aspirational and is revised.
4. **Season coverage extended to 2015** — `mart_batter_profile_summary` backfilled; 5099 rows across 12 seasons.
5. **dbt tests added to `mart_batter_profile_summary`** — `unique_combination_of_columns` on `(batter_id, game_year)`, `not_null`, `expression_is_true` range checks.

## Story 7.2 revalidation — pitcher archetypes ✅ Complete (2026-05-29)

**Key decisions:**

1. **Cross-season pooled k-means** — same strategy as 7.1; all prototype stability flags resolved.
2. **Stratum-B features excluded** — `fb_arm_angle` (0% populated pre-2020) and `overall_stuff_plus` (FanGraphs Stuff+, 2020+ only) excluded. 13 stratum-A features used exclusively.
3. **Season coverage extended to 2015** — `mart_pitcher_arsenal_summary` gate changed from 2020 to 2015; new `mart_pitcher_profile_summary` mart created.
4. **k=5 selected, `elite_breaking_ball` retired** — silhouette flat from k=5 to k=8 (0.1055 → 0.1055); without stratum-B features, breaking-ball pitchers merge correctly into `power_swing_and_miss`. 5 pitcher archetypes going forward.
5. **Label-map override required** — heuristic mis-assigned cluster 4 (soft_command) as `changeup_deceptive`; `--label-map` used at full run.
6. **dbt tests added to `mart_pitcher_profile_summary`** — `unique_combination_of_columns` on `(pitcher_id, game_year)`, `not_null`, `expression_is_true` range checks on all rate stats.

**Next step:** Re-register 5-archetype pitcher schema in `sub_model_registry.yaml`; rebuild `mart_batter_archetype_vs_pitcher_cluster` (Story 7.3).

---

## Soft Cluster Assignment — Dirichlet Posterior Methodology (Epic 7A)

**Table:** `baseball_data.betting.mart_player_archetype_posteriors`
**Script:** `betting_ml/scripts/eb_priors/compute_archetype_posteriors.py`
**Priors:** `betting_ml/models/eb_priors/archetype_priors.json`
**Coverage:** 2021–present (full-season backfills 2021–2025; daily `today` mode for 2026+)

### Bayesian posterior

```
posterior_k ∝ exp(−dist_k²) × Dirichlet_prior_k
```

`dist_k` is the squared Euclidean distance from the player's rolling cumulative feature vector to centroid k in the StandardScaler-normalized space used by the Epic 7 KMeans model. The likelihood is evaluated at each game_date using stats accumulated from game 1 of the season through that date.

### Dirichlet prior structure

Priors are fit per population × age band using empirical cluster fractions from 2015–present. The concentration parameter (`total_alpha`) controls prior strength:

| Age band | Age range | total_alpha | Intent |
|----------|-----------|-------------|--------|
| `u24`    | < 24      | 5           | Wide — high rookie uncertainty |
| `a24`    | 24–27     | 15          | Moderate |
| `a28`    | 28+       | 30          | Strong — established player profiles |

Each `α_k = total_alpha × empirical_fraction_k` for the base prior.

### Peaked prior for returning players

Players with a confirmed prior-season cluster assignment (≥ 100 PA / BF) receive a peaked Dirichlet instead of the base prior:

- Confirmed cluster: `α_k = 0.8 × total_alpha`
- All other clusters: `α_k = (0.2 × total_alpha) / (K − 1)`

This produces stable tracking for consistent players. It intentionally causes ~17% of qualified batters (≥ 200 PA) to disagree with the KMeans hard assignment — borderline players are held near their prior-year archetype even as in-season stats drift. This is by design, not a bug.

### `eb_data_source` field

| Value | Condition | Posterior basis |
|-------|-----------|-----------------|
| `prior_only` | 0 PA | Pure Dirichlet prior (no likelihood) |
| `partial_update` | 1–99 PA | Prior + limited likelihood |
| `full_eb` | ≥ 100 PA | Full Bayesian posterior update |

### `cluster_entropy` interpretation

Shannon entropy of the posterior probability vector. **Lower = more certain assignment.**

Expected population ranges (verified on 2021–2025 backfills):
- Batters: 0.25–0.27 (avg across season)
- Pitchers: 0.16–0.19 (tighter clusters → lower entropy)

**Entropy seasonality:** April entropy is *lower* than September entropy. The peaked prior suppresses early-season uncertainty for returning players; players whose profiles genuinely drift mid-season develop bimodal posteriors by late season → higher entropy. This is correct behavior.

Use `cluster_entropy` as a feature representing assignment uncertainty. High entropy signals that the model is unsure which archetype best describes the player at that point in time.

### Soft-weighted matchup table

`mart_batter_archetype_vs_pitcher_cluster` is rebuilt using soft weights (Epic 7A.3). Each historical PA event contributes fractionally to all 25 matchup cells with weight `p_batter_b × p_pitcher_p`. The column `pa_weight` (sum of joint weights over the 180-day rolling window) replaces the old `pa_count`. Gate: `pa_weight >= 50`.

`matchup_uncertainty_score = batter_cluster_entropy + pitcher_cluster_entropy` is computed at prediction time in Epic 8 by joining `mart_player_archetype_posteriors` for the specific batter and pitcher in each game. It is non-null even for `prior_only` players (the prior itself carries non-zero entropy).
