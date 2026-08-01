# NF-D10 — OC / head-coach change source (the H-SYSTEM regime variable)

**Generated:** 2026-08-01T02:22:59.455031+00:00. Edge-independent, `best_alpha=0` — CANDIDATE projection features for NF1.2/NF1.5, not an edge claim. Whether H-COACH ships is decided by NF1.5's deflated market+blind re-bake-off.

## 1. Sources + ToS disposition (probed live, not read off docs)

| role | source | license / access | disposition |
|------|--------|------------------|-------------|
| **HC** | nflverse `schedules/games.parquet` (`home_coach`/`away_coach`) | the release feed this repo already reads | ✅ used — PER-GAME grain, so an HC stint carries an EXACT effective date |
| **OC** | Wikipedia team-season `==Staff==` via `api.wikimedia.org` core REST | CC BY-SA 4.0, Wikimedia's own programmatic endpoint, identifying UA, one cached fetch per page | ✅ used — the story's sanctioned last resort, after the structured options below failed |
| — | nflverse coaching release | — | ❌ **does not exist** (all 25 release tags enumerated live; `contracts`/`depth_charts`/`officials` exist, a coaches table does not) |
| — | Pro-Football-Reference coaching pages | Cloudflare JS challenge on `robots.txt` itself | ❌ **not scraped** — same disposition NF-D8 reached for Spotrac/OverTheCap |
| — | `spatto12/NFLCoaches` (PFR-derived) | MIT | ❌ HEAD-COACH ONLY and stops at 2023 — adds nothing over the nflverse coach columns |

Wikipedia's `robots.txt` was fetched and honoured: `/wiki/<Article>` is allowed for `User-agent: *` (only `Special:`, `/w/` and `/api/` are disallowed); reads go through the dedicated `api.wikimedia.org` host with a contact UA per Wikimedia's UA policy.

## 2. Coverage (the honest floor)

`oc_coverage` = share of the 32 teams with a parsed WEEK-1 offensive coordinator. `new_oc_computable` = teams where BOTH this season's opener and last season's finisher parsed, so the flag is real rather than NaN.

| season | teams | OC cov | HC cov | new_oc computable | new_oc rate | new_hc rate |
|--------|-------|--------|--------|-------------------|-------------|-------------|
| 2006 | 32 | 0.906 | 1.0 | 25 | 0.48 | 0.312 |
| 2007 | 32 | 0.812 | 1.0 | 24 | 0.417 | 0.219 |
| 2008 | 32 | 0.844 | 1.0 | 23 | 0.217 | 0.125 |
| 2009 | 32 | 0.781 | 1.0 | 21 | 0.286 | 0.281 |
| 2010 | 32 | 0.906 | 1.0 | 24 | 0.208 | 0.094 |
| 2011 | 32 | 0.938 | 1.0 | 28 | 0.393 | 0.188 |
| 2012 | 32 | 0.969 | 1.0 | 29 | 0.448 | 0.219 |
| 2013 | 32 | 1.0 | 1.0 | 32 | 0.406 | 0.281 |
| 2014 | 32 | 0.906 | 1.0 | 29 | 0.379 | 0.219 |
| 2015 | 32 | 0.969 | 1.0 | 28 | 0.536 | 0.219 |
| 2016 | 32 | 0.938 | 1.0 | 30 | 0.333 | 0.219 |
| 2017 | 32 | 0.906 | 1.0 | 28 | 0.25 | 0.156 |
| 2018 | 32 | 0.844 | 1.0 | 26 | 0.577 | 0.219 |
| 2019 | 32 | 0.875 | 1.0 | 27 | 0.481 | 0.25 |
| 2020 | 32 | 0.875 | 1.0 | 27 | 0.333 | 0.156 |
| 2021 | 32 | 0.938 | 1.0 | 28 | 0.357 | 0.219 |
| 2022 | 32 | 0.875 | 1.0 | 28 | 0.464 | 0.312 |
| 2023 | 32 | 0.969 | 1.0 | 29 | 0.586 | 0.156 |
| 2024 | 32 | 0.969 | 1.0 | 31 | 0.484 | 0.219 |
| 2025 | 32 | 0.969 | 1.0 | 30 | 0.433 | 0.219 |
| 2026 | 32 | 1.0 | 1.0 | 32 | 0.656 | 0.219 |

**Coverage floor:** OC parses for **78%–100%** of teams per season (overall 91.4%); HC is **100%** every season. The weak years are 2007–2009, where a handful of team-season articles carry no staff list at all (prose only). A team with no parsed OC gets **NaN**, never a fabricated value — the learners median-impute and the MVP-1 null ignores it.

## 3. Leakage-safe as-of (the correctness crux)

Every stint carries an `effective_date`; a projection for season *Y* may only read stints with `effective_date <= March 15 of Y` (after the new league year opens and after the Jan–Feb coaching carousel, months before Week 1). So an OFFSEASON hire is in *Y*'s feature and a MID-SEASON firing inside *Y* is not — it becomes visible only from *Y+1*.

- mid-season changes in the stint table: **78**
- of those, reaching their OWN season's pre-season feature: **0** (must be 0)
- visible to the FOLLOWING season: **78** (must equal the total — the rule must be safe by DATING, not by discarding)
- **leakage-safe: True**

## 4. Honest gaps

- **The OC parse is season-granular.** Wikipedia records WHO held the job, not the DATE he was hired; a season-opening coordinator is therefore stamped with the March 15 anchor rather than his actual announcement date. That is conservative in the direction that matters (it never makes a change known EARLIER than the offseason) but it means the source cannot answer 'was this hire known on February 1'.
- **A mid-season replacement's date is approximate** — derived from a week annotation when the article carries one, else the season's week-9 midpoint. Only its SIDE of the as-of boundary is load-bearing, and that is exact by construction (any within-season date is after the March anchor).
- **Co-coordinators** are recorded as separate stints; the first listed is treated as the week-1 holder, so a genuine co-OC pair reads as a single regime.
- **`oc_prior_pass_rate_delta` inherits the team-rate floor, and DEGENERATES below it.** `rollup_nfl_team_season` carries `off_pass_rate` for 2020–2025 only, so for projection seasons ≤2020 the column collapses to '0.0 iff the OC was retained, NaN otherwise' — the same information `new_oc` already carries, NOT a measured scheme shock. It is a genuinely distinct signal only from projection season 2021 onward (measured non-null rate on the rebuilt pools: ~0.51–0.58, of which the pre-2021 part is entirely retained-OC zeros). ⚠️ Read a family lift accordingly: if H-COACH clears only on pre-2021 targets, it is `new_oc` clearing, not the scheme-shock hypothesis. The other four columns cover the full range.
- **A parse gap in season *Y−1* makes season *Y*'s `new_oc` NaN**, not 0 — an unknown predecessor can never be silently read as 'no change'.

## Disposition

- **Ship (data):** `coaching_source.load_coach_features(season)` → per-team `new_oc` / `oc_tenure_years` / `new_hc` / `coach_continuity` (+ the names and the previous OC's last job, which `nf1_2_model.attach_coach` turns into `oc_prior_pass_rate_delta`). Landed to `nfl/fantasy/coaching/team_coach_features` + the effective-dated audit table `nfl/fantasy/coaching/coach_stints` (season-partitioned Delta).
- **Feature — ⛔ RECORDED NULL (NF1.5 blind re-bake-off, 2026-07-31).** H-COACH is registered in `nf1_2_model.REFINEMENT_FAMILIES` and in NF1.5's `base_system_coach` / `env_coach` / `kitchen_sink` bundles, and it **did not clear**: no coach bundle won at any position over 16 scored targets (2010–2025, 631–811 configs/position, placebo clean, oracle sane). The MATCHED-FOIL attribution the bundles exist for — each coach bundle against the identical bundle minus `coach` — is **NEGATIVE in 7 of 10 computable comparisons**, and no position has both of its comparisons positive. Full result: `ablation_results/nf1_5_feature_combination_bakeoff.{md,json}` (stage 2). The DATA still ships (it is the effective-dated substrate for the future weekly model); the FEATURE does not, and the incumbent bundles stand.

