# ⏭️ Operator run-order — Trade-deadline prospect board regen (2026-08-03 draft)

**Why:** we're mid MLB trade deadline. Trades change a prospect's **org/team**, which changes the
board's **org**, its **AL/NL (`mlb_league`)** scoping, and the E8.2 available/rostered overlay — but
**not** their talent. So the E7.3/E7.3p MLE translations and the E7.4 identity xref do **NOT** need
re-running. Refresh only the two sources that carry the CURRENT org — **FanGraphs "The Board" (E7.7)**
and **MLB Pipeline rankings (E7.11)** — then rebuild the board, which re-derives `mlb_league` from the
refreshed org via the static 30-team org→league map.

**Run everything on the LAPTOP** (per INC-37: data rebuilds default to the laptop; none of these
needs box-only state). All are SF-free (DuckDB over S3). `AWS_DEFAULT_REGION=us-east-2` is required on
every command that touches the S3 lakehouse. `best_alpha=0` — this is a projection product, no edge claim.

Run from the repo root: `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy`

---

## The checklist (run in order)

### ☐ Step 1 — Re-ingest FanGraphs "The Board" (E7.7 → `baseball/milb/the_board`)
Carries FanGraphs FV/rank + the org each prospect's grade is attached to.

**LAPTOP:**
```bash
AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_fangraphs_prospects_to_s3.py --season 2026
```
- ~1 min; idempotent partition overwrite (re-run same day = safe, stamps a fresh `as_of_date`).
- Optional pre-check (fetches, writes nothing): append `--probe`.

### ☐ Step 2 — Re-ingest MLB Pipeline rankings (E7.11 → `baseball/milb/mlb_pipeline_rankings`)
Top 100 + all 30 org Top 30s (~900 players, MLBAM-keyed). The board build (Step 3) **hard-fails** if
this snapshot is empty, so it must run before the build.

**LAPTOP:**
```bash
AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026
```
- ~1 min (31 polite page fetches, 1.5 s apart); idempotent per (season, as_of_date).
- Optional pre-check (one list, robots verdict + parsed shape, writes nothing): append `--probe`.
- Re-reads `mlb.com/robots.txt` and refuses if `/prospects/` becomes disallowed — that's expected safety, not an error.

### ☐ Step 3 — Rebuild the board (E8.0/E8.0b/E8.1 → `e8_0_prospect_board.xlsx`)
Joins FanGraphs ∪ MLB-Pipeline + our MLE line + consensus, re-derives `mlb_league` (AL/NL) from the
refreshed org, applies E8.2 availability + E7.13 comp ordering natively. `--prospect-savant` folds in
Prospect Savant expected stats (the optional 3rd source — 8 cached HTTP calls to an unofficial hobbyist
endpoint; no separate ingest step).

**LAPTOP:**
```bash
AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
    betting_ml.scripts.prospect_board.build_prospect_board --prospect-savant
```
- ~1–3 min (S3 I/O over ~40k xref + 26k MLE + ~14k Pipeline rows).
- **Draft file:** `quant_sports_intel_models/baseball/edge_program/ablation_results/e8_0_artifacts/e8_0_prospect_board.xlsx`
  (tabs: All / AL / NL / Hitters / Pitchers / Minors only / By blend / Disagreements / Pipeline-only / How to read this).
  Also writes `e8_0_prospect_board.csv` + `_AL.csv` / `_NL.csv` and `e8_0_join_report.json`.

---

## Caveats to carry into tonight's draft

- ⚠️ **The board is only as fresh as the VENDOR boards.** A very-recent trade that FanGraphs / MLB
  Pipeline have **not yet posted** will still show the OLD org (and old AL/NL). A prospect's org can
  come from **either** source — check `on_fangraphs_board` / the source columns in the join report if a
  known-traded player looks stale. When the two sources disagree on org, that's the tell.
- ✅ **E7.13 comp-order footgun is closed (E8.1):** a plain `build_prospect_board.py` run now produces
  the comp-ordered board natively — no separate augmenter re-run needed. The fresh `e8_0_prospect_board.xlsx`
  IS the draft file.
- **If Step 3 hard-stops on missing E7.13 comp inputs** (the e7_8 cohort / e7_3 / e7_3p artifacts not on
  this machine): those are talent artifacts unaffected by trades and should already be present from prior
  builds. Only if genuinely absent, ship the pre-comp board with `--skip-comps` appended.
- **Fantasy serving is BUILD-TIME.** For **tonight's draft**, the xlsx/CSV export above is what you draft
  off — nothing else required. If you also want the in-app E8.1 board to reflect the refresh, re-publish
  the board JSON as a **post-step** (`quant_sports_intel_models/baseball/fantasy/export_prospect_board_json.py`)
  — not needed for the draft.
- 🔒 `best_alpha = 0` — FanGraphs + MLB Pipeline consensus + our MLE + where they disagree. A description, not a claim to beat any source.
