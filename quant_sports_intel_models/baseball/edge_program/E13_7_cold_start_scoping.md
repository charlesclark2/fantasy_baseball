# E13.7 — Unknown-pitcher cold-start fallback: scoping note (Phase 0)

**Status:** Phase 0 scoping (greenlit by operator 2026-06-22). **Date:** 2026-06-23.
**Frame:** product / fantasy + model-coverage / data-quality. **Explicitly NOT a betting-edge play.**
**Why this exists:** INC-8 found the starter-archetype model input is ~15–27% NULL and *rises through the
season* — rookies/call-ups have no prior-season profile, so the feature is blank exactly in the recent games
the E13.4 edge lift-tests judge edge on. A null edge result computed on degraded recent-window data is
untrustworthy (operator's bar). E13.7 replaces the blank with a sensible population **prior + an
`is_cold_start` flag** so the eval runs on trustworthy data. This is also the **first concrete building block
toward MiLB (Epic 7) and the Dynasty product (Epic 8)** — the proper fix is a MiLB-equivalent prior.

---

## (a) Cold-start NULL inventory

Three prior-season starter blocks in `feature_pregame_starter_features` go blank for pitchers with no
prior-season MLB profile. All three share the same root cause: each joins on a **prior-season** key
(`season = year(game_date) - 1`, archetype falls back to `-2`) as a leakage guard, so a pitcher with no
qualifying prior season gets NULL.

| Block | Feature columns | Source | Join key |
|---|---|---|---|
| **Archetype** | `starter_pitcher_archetype` (categorical cluster label) | `statsapi.pitcher_clusters` | season −1, fallback −2 |
| **Stuff+ / arsenal** | `starter_stuff_plus`, `starter_fastball/slider/curveball/changeup_stuff_plus`, `starter_fastball/breaking/offspeed_pct`, `starter_avg_fastball_velo`, `starter_primary_pitch_type` | `fct_fangraphs_pitcher_arsenal_wide` | season −1 (E1.8 leak fix) |
| **Platoon** | `k_pct/bb_pct/xwoba/whiff_rate _vs_lhb` and `_vs_rhb` | `mart_pitcher_vs_handedness_splits` | season −1 |

### % NULL by month (feature store, % of starter rows)

**2026 (current season, through 2026-06):**

| Month | Starters | Archetype | Stuff+ | Platoon (L/R) |
|---|---|---|---|---|
| 2026-03 | 152 | 6.6% | 5.3% | 5.3% |
| 2026-04 | 784 | 7.4% | 6.1% | 6.1% |
| 2026-05 | 837 | 12.8% | 10.5% | 10.5% |
| 2026-06 | 634 | **15.1%** | **12.6%** | **12.6%** |

**Prior full seasons — confirms the "rises through the season" curve, peaking in exactly the late-season
recent window E13.4 evaluates:**

| Month | 2024 archetype | 2024 Stuff+ | 2025 archetype | 2025 Stuff+ |
|---|---|---|---|---|
| Apr | 12.3% | 9.1% | 12.0% | 8.2% |
| Jun | 18.6% | 16.7% | 15.6% | 14.8% |
| Aug | 22.4% | 20.6% | 18.5% | 19.4% |
| **Sep** | **27.1%** | **25.6%** | **23.6%** | **20.5%** |

→ The "~20–25% and rising" characterization is correct: archetype NULL peaks at **23–27% in September**.
The signal degrades monotonically into the recent eval window — the worst possible timing for E13.4.

### Concentration in rookies/call-ups

Of the **53 distinct pitchers** with a NULL archetype in 2026, **46 (87%)** have **no prior-season cluster
assignment in any season** — true rookies / first-MLB-exposure call-ups. The remaining 7 have a cluster only
≥3 seasons back (injury / long absence gaps the −1/−2 lookback misses). The NULL is overwhelmingly a
**genuine cold-start** condition, not a data-pipeline gap (that class was the separate INC-8 freshness fix,
E11.8, which is closed).

### Why blanks are worse than a prior (current downstream handling)

- `starter_pitcher_archetype` (categorical): preprocessing maps NULL → `"__NA__"` then one-hot encodes — an
  uninformative "unknown" bucket. Rookies (whose true profile is unknown but *not* arbitrary) and genuine
  missing-data rows collapse into the same bucket, and the eval can't tell them apart.
- Stuff+ / platoon (continuous): preprocessing imputes NULL → **training-set column mean** (not a leak-clean,
  point-in-time value). At ~15–25% NULL, a large share of recent rows regress to a single global mean,
  washing out cross-pitcher variance precisely where the lift-test needs it.

---

## (b) Fallback-prior options (ranked)

| Tier | Approach | Cost | Ships |
|---|---|---|---|
| **Near-term (THIS story, Phase 1)** | League / role baseline + EB-shrinkage-to-prior. Categorical archetype → explicit `'league_baseline'` category; continuous Stuff+/platoon → **leak-clean prior-season league-average for starters** (= the EB posterior at n=0, full shrinkage to the population prior, since a true rookie has no MLB sample). Plus an `is_cold_start` flag so models/eval can condition on / stratify by cold-start status. | Cheap; pure-dbt, no new source. | **Now** |
| **Proper (follow-on, Epic 7)** | **MiLB-equivalent prior**: translate a pitcher's minor-league arsenal / Stuff+ / platoon line into an MLB-equivalent (MLE) and use it as the prior instead of the generic league baseline. EB-shrink the (sparse) early-MLB sample toward the *MiLB-translated* prior rather than the league mean. This is the real fix and the E7/Dynasty bridge. | Higher — needs MiLB ingestion + a translation model. | Epic 7 |

The near-term tier is deliberately a **product/coverage** improvement, not an edge claim: a generic
league-baseline prior carries no pitcher-specific information for a true rookie. Its value is (1) making the
recent-window data clean enough that E13.4's null is trustworthy, and (2) giving every consumer an explicit
`is_cold_start` signal. The pitcher-specific information only arrives with the MiLB prior (E7).

### Why `'league_baseline'` (not the modal cluster) for the categorical archetype

Assigning every rookie the population-modal cluster (`contact_sinker_ball`, the most common label) would be a
strong and usually-wrong claim about an individual pitcher. An explicit `'league_baseline'` category is
honest ("generic starter, profile unknown") and, paired with `is_cold_start`, lets a retrained model learn a
rookie-specific offset rather than mislabel the pitcher's pitch profile.

---

## (c) MiLB sourcing — FREE-FIRST (validate cheap before any paid source)

The proper prior (E7) needs minor-league arsenal/performance. Validate free sources before paying:

1. **MLB StatsAPI (free, already in our stack):** carries MiLB games, boxscores, and probable pitchers under
   the minor-league `sportId`s (AAA=11, AA=12, A+=13, A=14). We already ingest MLB StatsAPI; extending the
   `sportId` is the cheapest probe. **Validate:** pitch-level / Statcast-grade detail is the open question —
   AAA has had ball-tracking (Hawk-Eye/Statcast in AAA parks) but lower levels are sparse; confirm what
   arsenal granularity is actually returned before committing.
2. **FanGraphs (free leaderboards via the existing FlareSolverr path):** publishes MiLB stats and prospect
   boards; **Stuff+ for MiLB is the item to validate** — confirm whether FG exposes minor-league Stuff+/arsenal
   or only surface stats. (Reuse `fangraphs_client` through FlareSolverr — see the FG.7 split-egress note.)
3. **Baseball Savant / Statcast:** MLB-only for the pitch-tracking we use; AAA ball-tracking exists but is not
   in the public Savant export at MLB parity. Treat as MLB-side only.
4. **Paid (last resort, only if 1–3 fail):** prospect/scouting data providers. Do not pursue until the free
   probes are exhausted and documented.

**MiLB→MLB translation (the noisy, moat-y part):** raw MiLB lines overstate MLB performance; the standard
approach is **Minor League Equivalencies (MLEs)** — league/level run-environment factors + age/level
regression to project an MLB-equivalent line, which then seeds the EB prior. This is the hard, defensible
modeling work and is intentionally scoped to E7, not this story.

---

## (d) How it plugs in

- **Archetype / Stuff+ / platoon NULLs:** Phase 1 fills all three blocks at the feature-store layer
  (`feature_pregame_starter_features`), so the NULL rate in the recent window drops to ~0 and the E13.4
  lift-tests run on clean data. `is_cold_start` propagates to the public surface
  (`feature_pregame_game_features` via the `_raw` passthrough) as `home_starter_is_cold_start` /
  `away_starter_is_cold_start`.
- **Dynasty / fantasy product (E8):** the same cold-start machinery is what a dynasty/prospect product needs —
  a defensible projection for a player with little/no MLB track record. The near-term baseline is the
  placeholder; the MiLB-equivalent prior (E7) is the actual dynasty feature. E13.7 is the seam they share.
- **Model retrain note:** filling the *existing* columns changes what the model sees for cold-start rows.
  The offline E13.4 lift-tests benefit immediately. The deployed champion will see the new
  `'league_baseline'` archetype category (maps to all-zero one-hot until retrained) — flagged for the
  operator; go-live of the convention is gated by the normal model-promotion runbook + the next retrain
  (E1.9 / E13.4 track), not by this data-quality change.

---

## Phase 1 acceptance criteria (this story)

- [x] Scoping note committed (this doc).
- [x] Near-term fallback shipped: cold-start NULL rate → 0 by construction for archetype + Stuff+ +
      platoon (coalesce to a non-null prior-season league baseline / `'league_baseline'` literal);
      `is_cold_start` flag exposed on the public feature surface (`home_/away_starter_is_cold_start`).
- [x] Leak-clean: baselines computed only from strictly-prior seasons (year-1 join, all-seasons pooled
      fallback for the earliest data year); no `<game_date` violation.
- [x] CI green: `dbtf compile` 1766/1766; selected compile 43/43; `uv run pytest` 451 passed, 1 skipped.
      (Warehouse `dbtf build --select state:modified+` — which materializes the tables and runs the new
      not_null tests on real rows — is >1 min and handed to the operator; recent-window null→0 is then
      observable, full-history backfill of the incremental game-feature tables needs `--full-refresh`.)

**Follow-on:** the proper MiLB-equivalent prior = Epic 7, scoped by this note.
