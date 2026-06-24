# E13.10 — App-render spec: matchup zone-overlay heatmap

The **product is the structured JSON** (one object per batter×pitcher, per as-of date); the
frontend renders it **natively — no image pipeline**. E13.10 delivers the **JSON + this spec**
(plus an S3 PNG research proof). The shipped page is a **downstream E5.5-class app story** — open
it gated on E13.10's findings. Honest framing: **explainability / transparency content, NOT an edge
claim** — no win-rate / "we beat the book" language.

- **Committed contract example:** `e13_10_sample_overlay.json` (real data — Yordan Álvarez vs
  Freddy Peralta, as-of 2026-06-20).
- **Served JSON (writer output):**
  `s3://baseball-betting-ml-artifacts/baseball/serving/zone_matchup/overlay/as_of=<date>/<batter_id>_vs_<pitcher_id>.json`
- **Research proof PNG (NOT git, NOT user-served):**
  `s3://baseball-betting-ml-artifacts/baseball/artifacts/zone_matchup_proofs/as_of=<date>/<batter_id>_vs_<pitcher_id>.png`

---

## 1. JSON schema (`schema_version: "2.0"`)

```jsonc
{
  "schema_version": "2.0",
  "as_of_date": "2026-06-20",            // leak boundary: profiles use only pitch BEFORE this
  "matchup": {
    "batter_id": 670541, "batter_name": "Yordan Álvarez", "b_hand": "L",
    "pitcher_id": 642547, "pitcher_name": "Freddy Peralta", "p_hand": "R"
  },
  "strike_zone": { "sz_top": 3.392, "sz_bot": 1.712 },   // the batter's mean zone bounds (ft)
  "grid": {
    "nx": 5, "nz": 5,
    "x_edges":     [-1.4, -0.84, -0.28, 0.28, 0.84, 1.4],   // feet, catcher POV (len nx+1)
    "z_norm_edges":[-0.25, 0.05, 0.35, 0.65, 0.95, 1.25],   // normalized zone height (len nz+1)
    "orientation": "cells carry (ix, iz); iz=0 is BOTTOM of zone, ix=0 is catcher-POV left",
    "x_units": "feet (catcher POV)",
    "z_units": "normalized strike-zone height (0=bottom, 1=top); z_ft via strike_zone bounds",
    "called_zone": { "x_half_ft": 0.83, "z_norm": [0.0, 1.0] }  // draw the rulebook box here
  },
  "pitch_groups": ["fastball", "breaking", "offspeed", "all"],
  "overlap_scalar": 0.0104,              // expected batter run value / pitch, usage-weighted
  "overlap_units": "expected batter run value per pitch, weighted by pitcher usage (>0 favors batter)",
  "is_cold_start": { "batter": false, "pitcher": false },   // render a "limited data" badge if true
  "cells": [
    {
      "pitch_group": "all",              // one record per (cell × group); groups above
      "ix": 2, "iz": 2,                  // grid indices (ix=column/x, iz=row/z)
      "x_ft": 0.0, "z_norm": 0.5, "z_ft": 2.552,   // CELL CENTER (z_ft via strike_zone)
      "batter_run_value": -0.0037,       // run value/pitch, batter POV (diverging: red>0, blue<0)
      "batter_whiff": 0.095,             // whiff/swing (alt batter layer)
      "batter_xwoba": 0.4076,            // xwOBA on contact (alt batter layer)
      "pitcher_usage_freq": 0.05585,     // share of pitches in this cell×group (bubble SIZE)
      "pitcher_loc": { "x_ft": -0.049, "z_ft": 2.541 }  // measured mean location (bubble POSITION)
    }
    // … 25 cells × 4 groups = 100 records
  ]
}
```

Field notes for the renderer:
- `cells` is long-form; filter by `pitch_group`. `"all"` = the hero view (usage-weighted batter
  value + total location density + usage-weighted location/whiff/xwoba).
- `batter_run_value` ≈ ±0.06 at cell edges → **diverging** scale centered at 0 (red = batter hot,
  blue = cold). Robust symmetric vmax ≈ 95th pct of |value| across cells.
- `pitcher_usage_freq` drives **bubble size**; `pitcher_loc.{x_ft,z_ft}` is the **bubble position**
  (the pitcher's measured mean spot in that cell — slightly off the cell center).
- `null` = no data even after shrinkage (rare) → render neutral.
- Use `strike_zone.{sz_top,sz_bot}` + `called_zone` to draw the rulebook box in feet.

## 2. Frontend component design note (downstream story — DO NOT build here)

- **Hero = the "All pitches" view** (single most legible read); **Fastball / Breaking / Offspeed
  toggles** (segmented control) switch the `pitch_group` filter.
- **Render natively as SVG** (recharts isn't ideal for a 2-D heat grid — a small custom SVG/canvas
  is cleaner): a 5×5 diverging-color grid for `batter_run_value` + overlaid circles at
  `pitcher_loc` sized by `pitcher_usage_freq`; draw the called-zone box.
- **Per-cell hover** shows the exact numbers: run value (e.g. "+0.04 runs/pitch") + usage
  ("12% of pitches here") + optionally whiff% / xwOBA.
- **Plain-language caption:** *"Red = this batter hits well here; bubbles = where the pitcher
  actually throws; overlap = the overall matchup read (higher favors the batter)."*
- **Themed** to the app design system (reuse the chart color tokens / tooltip from
  `frontend/components/ui/chart.tsx`); **responsive** (grid scales; toggles stack on mobile).
- **Badges:** show a "limited data" chip when `is_cold_start.batter|pitcher` is true.
- Placement: player page (`frontend/app/players/[player_id]/page.tsx`) + the matchup/pick detail.
  Add a `frontend/data/changelog.json` entry when the page ships (transparency feature).

## 3. Serving path (downstream story)

1. **Writer** (WARN tier — peripheral/app-cosmetic): a daily op runs `build_zone_matchup.py
   profiles --s3` then `… viz` to materialize today's slate's overlay JSON to the serving prefix
   (above) / Railway PG per [[project_serving_store_architecture]], keyed by `(as_of_date,
   batter_id, pitcher_id)`.
2. **Backend (FastAPI):** a Pydantic `MatchupZoneOverlay` mirroring §1 + a read endpoint (e.g.
   `GET /players/{player_id}/matchup-overlay?vs={pitcher_id}`); reads the serving artifact only —
   never Snowflake / never recompute at request time.

## 4. What NOT to do
- Don't surface `overlap_scalar` as a bet signal unless Track B's lift test clears the gate
  (expected null). It's a descriptive matchup tag.
- Don't ship PNGs to git or a user path — they're S3 research proofs only.
- Don't drop the `is_cold_start` badge — a rookie's map is mostly league prior and must say so.
