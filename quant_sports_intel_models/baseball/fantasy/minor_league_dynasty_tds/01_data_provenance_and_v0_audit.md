# Minor League Dynasty Projection System
## Appendix A — Feature-to-Source Provenance and V0 Audit

**Purpose:** Determine what can actually be built, legally and point-in-time, before activating a feature.

## 1. Source Tiers

- **Tier 0:** Free/public box-score and roster data.
- **Tier 1:** Publicly viewable scouting/ranking data requiring explicit usage review.
- **Tier 2:** Paid editorial/scouting subscriptions or licensed feeds.
- **Tier 3:** Licensed MiLB pitch/batted-ball/player tracking.
- **Unsupported:** No stable source at the required level/timestamp.

## 2. Hard Data Boundary

Baseball Savant states that Minor League Statcast exists only for **certain levels and ballparks** beginning in 2021. That is not equivalent to complete, point-in-time coverage across Triple-A, Double-A, A-ball, Complex, and DSL.

The production system therefore assumes:

- No comprehensive minor-league exit velocity.
- No comprehensive minor-league launch angle.
- No comprehensive bat speed.
- No comprehensive sprint speed.
- No comprehensive pitch velocity, spin, IVB, horizontal break, or release traits.
- No comprehensive chase, swing, contact, or whiff pitch-level feed.

Any of those fields requires an acquired vendor/league feed and a level-by-level coverage audit.

## 3. Feature-to-Source Table

| Feature | Named source | Cost / license | MiLB existence by level | Historical depth | Cadence / projection-time availability | Fallback / status |
|---|---|---|---|---|---|---|
| Player identity, org, affiliate, level | MLB Stats API | Free/public endpoint; terms must be reviewed | MLB and affiliated MiLB, including lower levels where endpoint coverage exists | Varies by endpoint and season | Transaction/roster refresh; capture daily | Internal crosswalk; required V1 |
| Game schedules and game IDs | MLB Stats API | Free/public | Affiliated MiLB | Multiple seasons, audit exact completeness | Known ahead; updates daily | MiLB site capture |
| Box-score PA, AB, H, 2B, 3B, HR, BB, SO | MLB Stats API | Free/public | Affiliated levels, but current V1 intentionally starts Single-A–AAA | Multiple seasons; audit per league | Postgame / stat-correction updates | None; core V1 |
| Pitcher BF, IP, H, HR, BB, SO | MLB Stats API | Free/public | Affiliated levels | Multiple seasons | Postgame | Core V1 |
| Stolen-base attempts, SB, CS | MLB Stats API box scores | Free/public | Affiliated levels where scoring is complete | Multiple seasons | Postgame | Core V1; attempt propensity validated, success rate currently null |
| K%, BB%, ISO | Derived from MLB Stats API | Internal | Single-A–AAA in current system | Same as box-score history | Recomputed after ingest | Core V1 |
| Age | MLB Stats API bio / internal player dimension | Free/public | All identified players | Career | Static/event-driven | FanGraphs/MLB Pipeline bio |
| Age relative to level | Derived from player age + league roster population | Internal | Supported levels | Same as roster history | Daily/weekly | League-season average age |
| Repeated-level indicator | Derived from historical assignments | Internal | Supported levels | Requires roster/transaction history | Daily | Season-level highest-level proxy |
| Time at level | MLB Stats API game logs / transactions | Free-derived | Supported levels | Multiple seasons | Daily | Games/PA at level |
| Draft round, pick, signing type | MLB Stats API draft endpoint; FanGraphs Board | Free/public or Tier 1 | Drafted players; international fields may be incomplete | Multi-year | Annual/event-driven | Manual draft file |
| Signing bonus | FanGraphs Board, MLB reports, Baseball America | Tier 1/paid editorial; usage review required | Variable | Historical snapshots if captured | Event-driven | Missing indicator; do not scrape without approval |
| Current level / ETA | FanGraphs Board | Publicly viewable; FV/admin use must follow approved policy | Board covers all listed prospects, including CPX/DSL | Historical lists only if retained point-in-time | Irregular editorial updates | MLB Pipeline ETA; model-derived broad ETA; no current-state backfill |
| FanGraphs FV | FanGraphs Board | Tier 1; current product is admin-gated; redistribution/public display restricted by internal policy | Prospects across levels | Historical Board snapshots only if actually retained and timestamped | Editorial updates, not daily | V0 must classify as retrospective vs prospective-shadow; current FV cannot be backfilled historically |
| FanGraphs risk / position / role | FanGraphs Board | Tier 1 | Listed prospects | Historical snapshots if retained | Editorial | Box-score usage + position; broader uncertainty |
| FanGraphs tool grades | FanGraphs reports/Board where present | Tier 1 | Selected prospects, uneven | Historical if captured | Editorial | FV only; do not infer hidden tools |
| Baseball America rank / grade | Baseball America | Paid subscription/editorial; commercial use requires license | Broad prospect universe, including lower minors | Long historical Top 100; detailed data depends product | Periodic | Exclude unless licensed |
| MLB Pipeline rank / tool grades | MLB Pipeline prospect pages | Publicly viewable; scraping/redistribution review required | Top 100 and organizational lists | Annual/periodic snapshots if captured | Periodic | FanGraphs FV only |
| Other rankings | Baseball Prospectus, Keith Law, ZiPS/OOPSY lists | Paid/editorial or public article; source-specific license | Varies | Varies | Periodic | Exclude absent contract |
| Park and league run environment | MLB Stats API game/venue + internally estimated factors | Free-derived | Supported levels | Requires multi-season game history | Refit seasonal/monthly | League-year shrinkage if park sample small |
| Opponent quality | Internal latent ratings from box-score opponents | Internal | Supported levels | Same as game history | Daily/weekly | Level average |
| Schedule strength | Internal from opponent ratings | Internal | Supported levels | Same as game history | Daily/weekly | League average |
| Defensive position appearances | MLB Stats API fielding/game logs | Free/public | Supported levels, endpoint completeness audit | Multiple seasons | Postgame | Primary listed position |
| Starter/reliever usage | MLB Stats API games started, appearances, innings | Free/public | Supported levels | Multiple seasons | Postgame | Recent usage share |
| Injury history | MLB Stats API transactions/IL; team reports | Free but incomplete | Affiliated MiLB, variable | Uneven | Event-driven | Missingness flag; do not treat absent record as healthy |
| 40-man status / options proxy | MLB Stats API roster/transactions | Free/public | Upper minors/MLB-relevant | Multiple seasons | Daily | Unknown state |
| Rule 5 timing | Derived from signing/draft date and rules | Internal; legal/rules verification needed | Eligible cohorts | Career | Annual | Broad eligibility band |
| Organizational depth | MLB Stats API rosters + internal MLB projections | Free/internal | All orgs | Current and historical snapshots | Daily/weekly | Position-count proxy |
| Organization promotion tendency | Derived historical transactions | Internal | Supported levels | Requires several years | Seasonal | League-wide prior |
| Exit velocity | MiLB Hawk-Eye / licensed vendor; partial Baseball Savant minors | Tier 3 | Certain levels/ballparks since 2021; not complete A-ball/CPX/DSL | Patchy | Postgame if feed exists | **Unavailable V1; do not impute as observed** |
| 90th-percentile/max exit velocity | Same as exit velocity | Tier 3 | Same limitations | Patchy | Postgame | **Unavailable V1** |
| Launch angle / barrel / hard-hit | MiLB Hawk-Eye / licensed vendor; partial Savant | Tier 3 | Certain parks/levels only | Patchy since 2021 | Postgame | **Unavailable V1** |
| Bat speed | Hawk-Eye bat tracking / licensed feed | Tier 3 | Not comprehensive publicly below MLB | Very limited/non-public | Vendor-dependent | **Unsupported** |
| Sprint speed | Hawk-Eye/Statcast tracking / vendor | Tier 3 | Not comprehensive publicly below MLB | Patchy | Vendor-dependent | SB attempt propensity + age; do not call it sprint speed |
| Swing rate / chase rate | Pitch-level MiLB tracking | Tier 3 | Not comprehensive public coverage | Patchy | Pitch-level/postgame | **Unavailable V1** |
| Contact / zone-contact / whiff | Pitch-level MiLB tracking | Tier 3 | Not comprehensive public coverage | Patchy | Pitch-level/postgame | K% as box-score proxy; distinct construct |
| Called-strike rate | Pitch-level MiLB tracking | Tier 3 | Not comprehensive public coverage | Patchy | Postgame | BB%/K% only |
| Pitch velocity | MiLB Hawk-Eye/vendor; occasional public reports | Tier 3 or unstructured reports | Spotty even at Triple-A; not comprehensive lower minors | Patchy | Vendor/editorial | **Unavailable systematic V1** |
| Spin rate / axis | MiLB Hawk-Eye/vendor | Tier 3 | Not public comprehensively | Patchy | Postgame | **Unsupported** |
| IVB / horizontal break | MiLB Hawk-Eye/vendor | Tier 3 | Not public comprehensively | Patchy | Postgame | **Unsupported** |
| Release height/side/extension | MiLB Hawk-Eye/vendor | Tier 3 | Not public comprehensively | Patchy | Postgame | **Unsupported** |
| Pitch mix | Pitch-level tracking/vendor | Tier 3 | Partial by tracked park/level | Patchy | Postgame | Box-score starter/reliever usage only |
| Pitch-level whiff/chase/location | Pitch-level tracking/vendor | Tier 3 | Partial | Patchy | Postgame | **Unavailable V1** |
| Ground-ball/fly-ball distributions | MLB Stats API play-level/event feed if complete; tracking vendor | Free-derived only if event detail is available; otherwise Tier 3 | Audit by level | Variable | Postgame | Omit or use aggregate damage proxy |
| Platoon splits | MLB Stats API game logs/play detail where batter/pitcher handedness is retained | Free-derived | Supported levels if event data complete | Variable | Postgame | Overall rates with wider uncertainty |
| Weather | Stadium + external weather API | Free/low-cost | All outdoor parks | Historical/forecast depends vendor | Capture pregame forecast | Park/season effect |
| Altitude / dimensions / surface | Venue dimension/manual registry | Free/manual | All known parks | Long-lived | Rare changes | League/park random effect |
| Written scouting text | FanGraphs, BA, Pipeline | Editorial copyrighted content | Selected players | Historical articles | Irregular | Do not ingest verbatim absent license; structured approved fields only |

## 4. V0 Audit Checklist

For each source and feature:

```yaml
feature_name:
source_name:
endpoint_or_delivery:
legal_owner:
license_status:
redistribution_allowed:
derived_feature_allowed:
minor_league_levels:
first_available_date:
missingness_by_level:
publication_lag:
revision_behavior:
point_in_time_snapshot_available:
fallback:
activation_status:
```

Activation states:

- `ACTIVE_V1`
- `ACTIVE_INTERNAL_ONLY`
- `GATED_LICENSE`
- `GATED_COVERAGE`
- `UNSUPPORTED`
- `DEPRECATED`
- `RETROSPECTIVELY_VALIDATED`
- `PROSPECTIVELY_SHADOW_VALIDATED`
- `NOT_VALIDATED`


## 4A. FanGraphs FV Point-in-Time Snapshot Audit

V0 must determine whether contemporaneous FanGraphs Board/FV snapshots actually exist for each historical evaluation date.

The audit must answer:

```yaml
fv_source:
snapshot_date:
capture_timestamp:
players_covered:
fields_available:
historical_version_retained:
source_revision_behavior:
usable_for_as_of_backtest:
license_status:
validation_class:
```

Allowed `validation_class` values:

- `RETROSPECTIVELY_VALIDATED`
- `PROSPECTIVELY_SHADOW_VALIDATED`
- `NOT_VALIDATED`

### 4A.1 Retrospective Use Rule

FV may be used in a historical backtest only when the exact or appropriately prior snapshot was captured before the projection timestamp.

Permitted join:

```text
fv_snapshot_timestamp <= projection_timestamp
```

Forbidden join:

```text
current_fv joined to historical player-season
```

Current FV may encode knowledge of:

- Later minor-league performance.
- Promotions.
- Injuries.
- Role changes.
- MLB performance.
- Updated scouting reports.

Using current FV in an older backtest is forward-looking editorial leakage.

### 4A.2 No Historical Snapshot Available

When historical FV snapshots are absent:

- FV's incremental value cannot be claimed from retrospective evaluation.
- The historical model must use the box-score-only feature set or historically available scouting inputs.
- FV must be evaluated prospectively through shadow snapshots.
- The production board may still use current FV if licensed and clearly timestamped, but its incremental validation status is `PROSPECTIVELY_SHADOW_VALIDATED`.
- Model cards and product documentation must distinguish box-score validation from FV-assisted prospective performance.

### 4A.3 Required Ablations

Every release reports:

1. Box-score-only.
2. FV-only where contemporaneous FV exists.
3. Box-score + FV.
4. Box-score + current FV only in prospective shadow evaluation.

This preserves the ability to ship and validate without FV.

## 5. Box-Score + FV Minimum Viable Set

The V1 board can honestly ship with:

### Hitter inputs

- Level and league.
- Age and age relative to level.
- PA.
- K%.
- BB%.
- ISO.
- HR, doubles, triples.
- SB attempts per opportunity proxy.
- SB success observations, but not translated success skill.
- Recent and career sample sizes.
- Promotion history.
- Position.
- FanGraphs FV.
- Park/league/year factors.
- Organization context.

### Pitcher inputs

- Level and age relative to level.
- BF and IP.
- K%.
- BB%.
- HR or damage proxy.
- Starts, relief appearances, innings per appearance.
- Workload trend.
- Promotion history.
- FanGraphs FV.
- Park/league/year factors.
- Organization context.

### Explicit V1 exclusions

- Exit velocity.
- Launch angle.
- Bat speed.
- Sprint speed.
- Swing/chase/contact/whiff rates.
- Pitch shape.
- Spin.
- IVB/HB.
- Release traits.
- Reliable command-location models.
- Complex/DSL statistical translations.

## 6. Reference Notes

- MLB Baseball Savant Minor League Statcast Search: tracking is available since 2021 only for certain levels and ballparks.
- FanGraphs The Board includes FV, risk, ETA, current level, position/role, age, and prospect metadata; current snapshots must be retained point-in-time.
- FanGraphs describes FV as a 20–80 future-value construct and emphasizes FV tiers over simple ordinal rank.
- Baseball America and MLB Pipeline are useful potential scouting sources but require explicit licensing/scraping review before product ingestion.
