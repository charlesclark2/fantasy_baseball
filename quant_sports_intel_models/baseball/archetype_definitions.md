# Archetype Definitions

**Source tables:** `baseball_data.statsapi.batter_clusters`, `baseball_data.statsapi.pitcher_clusters`  
**Generated:** 2026-05-19 (Story 2.9)  
**Downstream consumer:** `matchup_v1` training target — `mart_batter_archetype_vs_pitcher_cluster`

---

## Important notes on cluster stability

- Cluster `cluster_id` values are **not stable across seasons** — the same integer can map to different archetypes in different years. Always join on `cluster_label`, not `cluster_id`.
- Season coverage begins 2020. Some archetypes appear only in select seasons (see stability tables below) — this is an artifact of k-means convergence, not a data gap.
- Clusters with < 50 members in a season produce noisy population-level matchup estimates. Flag these in training by filtering to seasons where the cluster has ≥ 50 members.
- **Epic 7 (archetype revalidation)** is required before `matchup_v1` training. These definitions describe the current cluster assignments and are expected to change after revalidation.

---

## Batter archetypes

Five batter archetypes derived from Statcast swing and batted-ball profile features.

### `power_pull`

**Feature drivers:** High pull rate, above-average exit velocity, high hard-hit%, elevated HR rate, elevated K% (accepted tradeoff for raw power).

**Offensive profile:** Pull-side power threat. Generates extra-base hits and home runs at high rates. Vulnerable to inside fastballs and breaking balls away, which limit contact to weaker pull-side outcomes. High leverage against pitchers with limited arm-side movement.

**Example players (2024):** Gunnar Henderson, Alex Bregman, Taylor Ward, Oneil Cruz

**Matchup signal:** Elevated wOBA against `changeup_deceptive` and `soft_command` pitchers; suppressed against `power_swing_and_miss` who can bust hands with velocity.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 82      |
| 2021   | 95      |
| 2022   | 70      |
| 2023   | 92      |
| 2024   | 70      |
| 2025   | 75      |

All seasons ≥ 50. Stable archetype.

---

### `patient_obp`

**Feature drivers:** Above-average walk rate, below-average K%, high contact rate, tendency to work counts, below-average pull rate.

**Offensive profile:** On-base specialist. Generates value through walks and line-drive singles rather than power. Difficult to strike out, especially effective against pitchers who fall behind in counts. Less dangerous against elite strikeout pitchers who don't need the zone.

**Example players (2024):** LaMonte Wade Jr., Manuel Margot, Tyler Nevin, Juan Yepez

**Matchup signal:** Elevated wOBA against `soft_command` (control pitchers who must throw strikes); suppressed against `power_swing_and_miss` (high K-rate overpowers contact approach).

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 55      |
| 2021   | 112     |
| 2022   | 51      |
| 2023   | 112     |
| 2024   | 143     |
| 2025   | 71      |

All seasons ≥ 50. Stable archetype, though 2020 and 2022 are at the floor.

---

### `high_whiff`

**Feature drivers:** High K%, high swinging-strike rate, aggressive zone coverage, below-average contact rate, often elevated pull rate.

**Offensive profile:** Boom-or-bust hitter. When making contact, can generate hard-hit balls, but frequency is low. Highly exploitable by pitchers with swing-and-miss stuff; less impacted by control-first pitchers. Common in lower lineup slots.

**Example players (2024):** Paul DeJong, Jake Cave, Elehuris Montero, Jacob Stallings

**Matchup signal:** Suppressed wOBA against `power_swing_and_miss` and `elite_breaking_ball`; elevated against `contact_sinker_ball` and `soft_command` who rely on weak contact rather than strikeouts.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 79      |
| 2021   | 139     |
| 2022   | 122     |
| 2023   | 126     |
| 2024   | 142     |
| 2025   | 105     |

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
| 2020   | 93      |
| 2021   | 117     |
| 2022   | 97      |
| 2023   | 131     |
| 2024   | 100     |
| 2025   | 107     |

All seasons ≥ 50. Stable archetype.

---

### `contact_spray`

**Feature drivers:** Low K%, balanced pull/center/oppo spray rate, above-average contact rate, line-drive tendency, moderate exit velocity.

**Offensive profile:** High-contact, all-fields hitter. Hits for average with moderate power. Difficult to exploit via pitch location since they use the whole field. Effective against both left- and right-handed pitching. Lower ceiling than `power_pull` but higher floor.

**Example players (2025):** J.T. Realmuto, Paul Goldschmidt, Maikel Garcia, Trevor Story

**Matchup signal:** Moderate, positive wOBA contribution across most pitcher archetypes. Least suppressed by `power_swing_and_miss` due to contact discipline.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2022   | 129     |
| 2025   | 103     |

⚠️ **STABILITY FLAG:** `contact_spray` only appears in 2022 and 2025. Missing from 2020, 2021, 2023, and 2024 — likely absorbed into `patient_obp` or `groundball_speed` in those seasons. Do not use 2022 or 2025 `contact_spray` matchup signals for cross-season comparisons without verifying cluster consistency. Epic 7 revalidation must address this.

---

## Pitcher archetypes

Six pitcher archetypes derived from Statcast pitch-mix, velocity, movement, and command profile features.

### `power_swing_and_miss`

**Feature drivers:** High fastball velocity (95+ mph), elevated whiff rate, high K%, above-average chase rate, fastball-heavy arsenal with hard secondary offerings.

**Pitching profile:** High-strikeout power pitcher. Generates swing-and-miss across all pitch types. Favorable against high-K% batter archetypes (`high_whiff`, `power_pull`). Most valuable in strikeout-predictive contexts (K prop markets, first-5-innings totals).

**Example pitchers (2024):** Dylan Cease, George Kirby, Logan Gilbert, Freddy Peralta

**Matchup signal:** Strongly suppresses `high_whiff`; modest suppression of `power_pull`; least effective vs `patient_obp` who works counts and avoids chase.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 147     |
| 2021   | 177     |
| 2022   | 148     |
| 2023   | 187     |
| 2024   | 141     |
| 2025   | 359     |

All seasons ≥ 50. Stable archetype. 2025 spike likely reflects broader cluster reassignment — verify in Epic 7.

---

### `elite_breaking_ball`

**Feature drivers:** High slider/curveball usage and movement grade, above-average whiff rate on breaking balls, can mix velocity effectively, above-average K%.

**Pitching profile:** Breaking-ball-first pitcher. Generates whiffs with put-away breakers. Effective against aggressive, pull-heavy hitters who expand on breaking balls. Less dominant against patient hitters who lay off the zone.

**Example pitchers (2024):** Seth Lugo, Logan Webb, Aaron Nola, Brady Singer

**Matchup signal:** Suppresses `high_whiff` and `power_pull`; moderate suppression of `groundball_speed` (limited strikeout contact); least effective vs `patient_obp`.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 66      |
| 2021   | 24      |
| 2022   | 28      |
| 2023   | 112     |
| 2024   | 119     |
| 2025   | 261     |

⚠️ **STABILITY FLAG:** Only 24 and 28 members in 2021 and 2022 (below 50-member threshold). Training data for this archetype should down-weight or exclude those two seasons. Cluster grew substantially from 2023 onward — likely the feature space defining this archetype was refined between the 2022 and 2023 clustering runs. Epic 7 must resolve.

---

### `changeup_deceptive`

**Feature drivers:** High changeup usage and plus movement grade, velocity differential (fastball-changeup separation ≥ 8 mph), tunnel effectiveness, below-average strikeout rate relative to whiff rate (generates weak contact more than pure strikeouts).

**Pitching profile:** Deception-based pitcher. Creates weak contact via fastball-changeup tunneling. Effective against right-handed power hitters who struggle with arm-side fade. Performance more dependent on sequencing than raw stuff.

**Example pitchers (2024):** Pablo López, José Berríos, Miles Mikolas, Chris Flexen

**Matchup signal:** Suppresses `power_pull` (pull-side bat path misses the fade); moderate suppression of `high_whiff`; `patient_obp` hitters with good eye make harder contact on changeups left in zone.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 115     |
| 2021   | 197     |
| 2022   | 184     |
| 2023   | 185     |
| 2024   | 141     |
| 2025   | 349     |

All seasons ≥ 50. Stable archetype. 2025 spike warrants Epic 7 review.

---

### `contact_sinker_ball`

**Feature drivers:** High sinker/two-seam usage, above-average groundball rate allowed, below-average K%, above-average command (low walk rate), pitch to contact philosophy.

**Pitching profile:** Groundball/contact pitcher. Keeps the ball on the ground, limiting hard-hit rates and extra-base hits. Effective when fielding is strong and ballpark has fast infield turf. Vulnerable to `groundball_speed` hitters who beat out grounders; less affected by K-dependent archetypes.

**Example pitchers (2023):** Julio Urías, Cole Ragans, Ty Blach, Caleb Ferguson

**Matchup signal:** Suppresses fly-ball power (`power_pull`); elevated BABIP allowed against `groundball_speed`; predictable performance — low variance.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 23      |
| 2021   | 83      |
| 2022   | 79      |
| 2023   | 157     |
| 2024   | 6       |
| 2025   | 311     |

⚠️ **STABILITY FLAG:** Only 23 members in 2020 and catastrophically only 6 in 2024 (well below the 50-member threshold). These seasons must be excluded from `matchup_v1` training for this archetype. The 2024 collapse suggests most sinkerball pitchers were reclassified into adjacent clusters — Epic 7 revalidation must reconcile. Use 2021–2023 data only for this archetype.

---

### `multi_pitch_mix`

**Feature drivers:** High pitch-type diversity (4+ pitch types used ≥ 10% each), no single dominant offering, balanced usage across quadrants. Often above-average command.

**Pitching profile:** Versatile/deceptive-through-variety pitcher. Limits batter preparation by offering no predictable pitch sequence. Effective against most archetypes at average levels. Hardest to scout and model — performance is more pitcher-specific than archetype-level.

**Example pitchers (2024):** Yusei Kikuchi, Garrett Crochet, Carlos Rodón, Jake Irvin

**Matchup signal:** Weakest archetype-level matchup signal — high within-cluster variance. Model should apply lower confidence weight to `multi_pitch_mix` matchup estimates.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 62      |
| 2022   | 84      |
| 2024   | 129     |

⚠️ **STABILITY FLAG:** `multi_pitch_mix` is **absent from 2021, 2023, and 2025** entirely. This archetype appears only in alternate years — strongly suggests clustering instability or a k-means local minimum artifact. Do not include 2021, 2023, or 2025 seasons when training on this archetype. Epic 7 must investigate root cause.

---

### `soft_command`

**Feature drivers:** Below-average velocity (88–91 mph fastball), above-average command (low walk rate), relies on pitch location and sequencing rather than raw stuff, moderate K rate.

**Pitching profile:** Command-and-location pitcher. Survives via precision — misses are punished hard. Effective in pitcher-friendly parks (low run factor, cool weather) and against aggressive hitters who expand early. Highly vulnerable to patient lineups that work counts and force mistakes on the edge.

**Example pitchers (2024):** Sean Manaea, JP Sears, Cole Ragans, Patrick Corbin

**Matchup signal:** Strongly permissive against `patient_obp` (patient hitters draw walks and foul off until they get a mistake); moderate wOBA elevation against `power_pull`; best outcomes against `high_whiff` who expand on borderline pitches.

**Stability (members per season):**
| Season | Members |
|--------|---------|
| 2020   | 51      |
| 2021   | 170     |
| 2022   | 107     |
| 2024   | 89      |

⚠️ **STABILITY FLAG:** `soft_command` is **absent from 2023 and 2025**. Combined with 2020 being at the 50-member floor, only 2021–2022 and 2024 seasons have reliable population estimates. Exclude 2023 and 2025 from `matchup_v1` training for this archetype. Epic 7 must address.

---

## Cluster stability summary

### Batter archetypes — all seasons ≥ 50 except:
| Archetype       | Problem season(s)              |
|-----------------|-------------------------------|
| `contact_spray` | Absent 2020, 2021, 2023, 2024 |

### Pitcher archetypes — seasons with < 50 members or absent:
| Archetype             | Problem season(s)              |
|-----------------------|-------------------------------|
| `elite_breaking_ball` | 2021 (24), 2022 (28)          |
| `contact_sinker_ball` | 2020 (23), 2024 (6)           |
| `multi_pitch_mix`     | Absent 2021, 2023, 2025       |
| `soft_command`        | Absent 2023, 2025; 2020 (51)  |

**Training recommendation:** For `matchup_v1`, restrict training to `(cluster_label, season)` pairs where `member_count >= 50`. The `mart_batter_archetype_vs_pitcher_cluster` table already aggregates at the population level — apply this filter when constructing the training dataset.

---

## Epic 7 revalidation requirements

These definitions are based on current cluster assignments (as of 2026-05-19). Epic 7 must:

1. Rerun k-means with a stable seed and explicit k-selection criteria (silhouette + gap statistic) across the full 2020–2025 history simultaneously, rather than per-season.
2. Ensure cluster_label assignments are semantically stable year-over-year (i.e., the `power_swing_and_miss` cluster in 2025 contains players who were `power_swing_and_miss` in 2024, not a relabeled cluster).
3. Document the feature space used for each clustering run — the current silhouette scores (uniformly 0.141 for batter clusters) suggest the feature space may not be well-separated.
4. Reconcile the alternate-year dropout of `multi_pitch_mix` and `soft_command` pitcher archetypes.
5. Resolve the `contact_spray` batter archetype absence from 4 of 6 seasons.
6. After revalidation, update this document and re-register `matchup_v1` target in `sub_model_registry.yaml`.
