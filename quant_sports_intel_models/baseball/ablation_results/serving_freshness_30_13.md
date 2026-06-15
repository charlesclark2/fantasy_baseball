# Story 30.13 — Serving-path freshness map (Task 1)

Upcoming games audited: today=10, +1=15, +2=14. A block is judged vs the source it ACTUALLY depends on intraday: `probable_pitchers` (starter blocks) / `lineups` (lineup blocks) / `(overnight)` (bullpen/team/pythag/elo — refreshed once/day, NOT vs intraday polls). `staleness_lag_min` >0 ⇒ built before the latest intraday ingestion. Worst intraday lag: **-1 min**.

**Classes** (who owns the fix):
- **stale_now** (0) — block ABSENT at serve for TODAY's slate. Severe; 30.13's acute target.
- **stale_overnight** (0) — OVERNIGHT-sourced block NOT rebuilt today (morning job / statcast-catchup didn't run or failed). 30.13 build-ordering target.
- **unguaranteed** (0) — intraday block present now BUT built before the latest intraday ingestion (positive lag). Build-ordering EXPOSURE: a starter/lineup change between build and serve ships stale. The every-10-min lineup_monitor self-heals within a cycle; the serve-time gate (Task 4) removes the residual.
- **point_in_time** (3) — LINEUP-dependent block null for future games BY DESIGN (lineups post ~game day). NOT a 30.13 defect; the gate must ABSTAIN on pre-lineup serves → Story 30.8 pre/post contract.
- **fresh** (6).

## 🔴 stale_now (acute — absent at serve today)

_(none)_

## 🟠 stale_overnight (overnight compute didn't refresh today)

_(none)_

## 🟡 unguaranteed (intraday build-ordering exposure)

_(none)_

## point_in_time (by design → Story 30.8; reported, not a defect)

| block | class | build (LAST_ALTERED) | intraday source | latest ingestion | lag(min) | null today/+1/+2 |
|---|---|---|---|---|---|---|
| `batter_sequential` | point_in_time | 2026-06-15 16:15 | lineups | 2026-06-15 16:08 | -6.6 | 0.0/100.0/100.0 |
| `lineup_archetype` | point_in_time | 2026-06-15 16:15 | lineups | 2026-06-15 16:08 | -6.6 | 40.0/100.0/100.0 |
| `lineup_statcast` | point_in_time | 2026-06-15 16:15 | lineups | 2026-06-15 16:08 | -6.6 | 0.0/100.0/100.0 |

## 🟢 fresh

| block | class | build (LAST_ALTERED) | intraday source | latest ingestion | lag(min) | null today/+1/+2 |
|---|---|---|---|---|---|---|
| `starter_eb` | fresh | 2026-06-15 16:09 | probable_pitchers | 2026-06-15 16:08 | -0.7 | 0.0/6.7/14.3 |
| `starter_sequential` | fresh | 2026-06-15 16:09 | probable_pitchers | 2026-06-15 16:08 | -0.7 | 0.0/0.0/7.1 |
| `bullpen_eb` | fresh | 2026-06-15 09:35 | (overnight) | (overnight) | nan | 0.0/0.0/0.0 |
| `team_sequential` | fresh | 2026-06-15 16:15 | (overnight) | (overnight) | nan | 0.0/0.0/0.0 |
| `pythagorean` | fresh | 2026-06-15 16:15 | (overnight) | (overnight) | nan | 0.0/0.0/0.0 |
| `elo` | fresh | 2026-06-15 16:15 | (overnight) | (overnight) | nan | 0.0/0.0/0.0 |

**Note:** EB posterior tables (`eb_starter_posteriors`, `eb_bullpen_posteriors`) carry NO build-timestamp column — freshness is inferred from `LAST_ALTERED` only. Adding a `computed_at` to the EB computes would let the serve-time gate assert per-row freshness directly (recommend in the 30.13 Task-4 gate).
