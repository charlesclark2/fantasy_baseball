# NCAAF NFL-feeder — the college↔NFL player-ID xref (NCAAF-P0.3)

The spine of the NFL feeder: a crosswalk keying a **CFBD college athlete** to an **NFL
`gsis_id`**, so a later story (NCAAF-P1A) can attach college production + combine
measurables to an NFL career outcome — the football analog of MLB Edge **E7** (MiLB→MLB
MLEs). This is the highest-ROI Phase-0 asset: everything downstream keys on it.

## ⭐ The key is the DRAFT SLOT, not an ID

There is **no shared player ID** between CFBD and nflverse (`ncaaf_data_inventory.md` §4):

| System | Example | |
|---|---|---|
| CFBD `collegeAthleteId` | `4431611` | ESPN numeric |
| CFBD `nflAthleteId` | `108247` | ∩ nflverse `espn_id` = **0 of 257** |
| nflverse `cfb_player_id` | `caleb-williams-3` | a sports-reference **slug** |
| nflverse `gsis_id` | `00-0039918` | the NFL key |

**Any plan that assumes an ID join is wrong.** The deterministic key is the draft slot:

```
CFBD /draft/picks (year, overall)  ──deterministic slot join──▶  nflverse draft_picks (season, pick)
        │  collegeAthleteId                                              │  gsis_id / pfr_player_id / cfb_player_id
        ▼                                                               ▼
  the college universe (roster/production)              nflverse combine (cfb_id slug)  ──▶ forty / vertical / …
```

`pick` IS the overall pick. Validated at **99.7%** of 2015–25 CFBD picks → a `gsis_id`
(independently ~92–100% surname agreement — proof the key is sound, computed *outside* the
join). Combine measurables attach **nflverse-internally** on the `cfb_player_id` slug.

## What this package builds

| File | Role |
|---|---|
| `xref.py` | the builder — a DuckDB-over-Delta job (mirrors MLB `run_w1_lakehouse`) that reads the raw lake, joins on the slot key, attaches combine, resolves the UDFA residual, **asserts no cartesian**, and lands `ncaaf/marts/xref_college_nfl_players` as a versioned Delta mart. |
| `name_norm.py` | shared name normalisation (suffix / apostrophe / accent) — one definition for the surname-agreement validation + the UDFA fuzzy block, in Python **and** DuckDB SQL (parity-tested). |

The mart is also exposed as a dbt view: `sports_dbt/models/ncaaf/marts/xref_college_nfl_players.sql`
(+ `stg_ncaaf_cfbd_draft_picks`, `stg_nflverse_draft_picks` staging views).

## The mart (`xref_college_nfl_players`)

One row per matched NFL player. Key columns:

- **ids** — `gsis_id` (NFL key, unique), `pfr_player_id`, `cfb_player_id` (slug),
  `college_athlete_id` (CFBD ESPN id — the bridge to college production).
- **identity** — `player_name`, `position`, `college`, `college_conference`,
  `draft_year`, `draft_overall`, `draft_round`.
- **match provenance** (source-stamped) — `match_method` ∈ {`deterministic_slot`,
  `fuzzy_udfa`}, `match_confidence` ∈ {`high`, `medium`, `low`}, `match_score`
  (1.0 for slot; Jaro-Winkler for fuzzy), `surname_agree`, `is_udfa`.
- **measurables** — `forty, vertical, bench, broad_jump, cone, shuttle, combine_ht,
  combine_wt`, `has_combine`, `has_forty` (slot path only — attached via the slug).
- **⚠️ `target_*`** — `car_av / w_av / dr_av / games / seasons_started / probowls /
  allpro / hof`. These are the **P1A modelling TARGET** (POST-draft NFL outcomes). They are
  carried here because the target already lives in `nflverse draft_picks` (no extra source),
  but they are **NEVER features** — prefixed `target_` so a feature build can't fold them in
  (the market-blind / leakage-safe discipline).

## The three residuals (per the P0.3 spec)

- **(a) UDFAs** — undrafted players have no draft slot ⇒ a genuine **fuzzy** match of
  `name + school + position` (nflverse `players` ⇄ CFBD `roster`), blocked on
  normalised surname + school + position, ranked by Jaro-Winkler on the full name, best per
  `gsis_id` above `--udfa-min-score` (default 0.92). Lower confidence, `fuzzy_udfa`. A UDFA
  has **no `target_*`** (undrafted → no draft-pick outcome row; that outcome would come from
  a different nflverse table, out of P0.3 scope). The residual never sinks the spine — if
  `nflverse_players` lacks `college_name`/`draft_number` it yields 0 and logs an ALERT.
- **(b) transfers** — a player's CFBD production spans schools, but `collegeAthleteId` is the
  **stable** ESPN id across them; the slot path keys on the slot (school-agnostic), so
  transfers are handled automatically for drafted players. Multi-school production is stitched
  by `collegeAthleteId` downstream (P1.1/P1A) via `/player/portal` + `teamStints`.
- **(c) name normalisation** — the 2–8% surname disagreement is formatting noise (`Jr.`,
  apostrophes, accents), removed by `name_norm` so `surname_agree` reflects a real mismatch.

## Anti-cartesian discipline (the P0.1 landmine)

pandas merges **NaN-to-NaN** — coercing the slug with `to_numeric` yields all-NaN and a
cartesian explosion that fabricates a bogus ~100% match (this bit the P0.1 session). This
builder is SQL (`NULL = NULL` is NULL → null keys never match), **and** it still:
drops null join keys on both sides · dedups each side 1-row-per-key · **asserts row counts
after every join** (a join must never multiply) · raises `XrefValidationError` on any
inflation / duplicate `gsis_id` / collapsed baseline. A wrong xref can never be silently
emitted.

## Run it

**Offline (laptop, local Delta fixtures — the fast-gate parity path):**
```bash
uv run python -m quant_sports_intel_models.football.ncaaf.feeder.xref \
    --local-root /path/to/local/delta --draft-seasons 2015-2025
```

**On the box (real S3 lake — the runtime gate; DuckDB needs the region):**
```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T \
    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
    python -m quant_sports_intel_models.football.ncaaf.feeder.xref \
    --draft-seasons 2015-2025 --write
```
`--write` lands `ncaaf/marts/xref_college_nfl_players` (Delta). Omit it for a dry report
(per-draft-class slot baseline, combine attach %, surname agreement, UDFA count). The report
must reproduce the ~99.7% slot baseline with **no cartesian inflation** — the CLI prints the
per-class match %, and the builder raises if a row-count invariant fails.

## Verify on first real box run (P0.1 discipline)

The fetchers were ground-truthed in P0.1, but the flatten reads specific `nflverse_players`
fields (`college_name`, `draft_number`, `entry_year`, `display_name`). Confirm they exist on
the first real read — if absent, the UDFA path degrades gracefully to 0 (the slot spine is
unaffected). The `target_*` names (`car_av`, `w_av`, …) are nflverse `draft_picks` columns.
