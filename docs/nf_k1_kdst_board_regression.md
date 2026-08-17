# NF-K1 — the published NFL board lost K and D/ST (2026-08-16)

**Severity:** HIGH — a live regression on the draft board, mid-draft-season, affecting every user
holding a kicker or a team defence (i.e. every carryover roster).
**Status:** code fixed + guarded; **the artifact is repaired by an operator rebuild+publish** (below).

---

## What users saw

Every rostered **K** and **D/ST** on My Teams rendered **"not matched"**, the team total was flagged
understated, and the best-possible lineup reported it could not fill 2 starting slots. The operator's
own roster: 14 of 16 matched, the two misses being `Eddy Pineiro` (K) and `Lions D/ST`.

## What was actually wrong

The **published** artifact carried 795 players — QB/RB/WR/TE only:

```
live  /fantasy/nfl/projections?season=2026
      generated_at 2026-08-16T14:22:15.886918+00:00
      795 players — WR 321, RB 197, TE 171, QB 106, K 0, DST 0
```

⛔ **It was NOT the NF-C6P3 D/ST franchise join** — the symptom the wording points at, and the second
time this cost an investigation. That join is correct and simply had nothing to match against. The
one-step discriminator: **K failed too**, and K is a plain exact-name join no D/ST logic touches.

## Onset — dated, not assumed

| when | who published | result |
|---|---|---|
| 2026-08-15 18:44 CDT | operator, by hand on the laptop | **868 players, 42 K + 32 DST** ✅ |
| 2026-08-16 07:15 PT (14:15Z) | `sports_nfl_board_publish_schedule` (`15 7 * * *`) — **first automated run** | **795 players, 0 K, 0 DST** ❌ |

The artifact's own `generated_at` (14:22:15Z) sits 7 minutes after the schedule fires. The schedule
was enabled by NF-INFRA1 on 2026-08-15 (`default_status=RUNNING`, once the `sports_duckdb` volume
prereq landed). So the regression is **the first fire of the automated publish**, not the 08-15
board republish it superficially resembles.

## Root cause

`nfl_fantasy_kdst_projections_<season>.parquet` is **the one artifact the box's publish chain READS
but never WRITES**:

```
run_nf1_5 --mode build      → writes nf1_5_season_projections_<season>.parquet   ✅
run_league_board            → writes the board CSVs                              ✅
export_draft_board_json     → reads both of the above, plus ↓
nfl_fantasy_kdst_projections_<season>.parquet   ← written by NOTHING in the chain ❌
```

`quant_sports_intel_models/football/nfl/fantasy/artifacts/.gitignore` ignores `*.parquet`, so it is
**absent from the `COPY . .` image**. `load_kdst_local` treated that as warn-and-continue (correct
in intent — a K/DST outage must not cost the operator the draft-critical offensive board), so:

* `run_league_board` folded in no K/DST → the boards fell back to unprojected placeholders;
* `export_draft_board_json` folded in no K/DST → `projections.json` carried neither position;
* every step exited 0, and `_verify_published` passed (it checks `generated_at` and `adp_as_of` —
  neither is disturbed by a missing position).

⭐ **Third instance of the NF-INFRA1 class** (after `sports.duckdb` and
`ncaaf_nfl_rookie_projections.parquet`): *a gitignored artifact a build READS is a deploy-ephemeral
time bomb.* Enumerating the chain's read-but-not-written artifacts found this is the **only**
remaining one — `nf1_player_contributions.json` and `nf_c0e_captured_term_rates_2026.json` are
tracked, and `nf1_5_projection_summary_<season>.json` is written by step 1 of the same run.

## Why every test was green

* `test_nf1_6_kdst_projection.py` guards the K/DST **code path** — unchanged and correct.
* The E2E fixture `fantasy-nfl-projections-2026-entitled.synthetic.json` still carries **42 K + 32
  DST**, so no fixture-based assertion could see it.
* Nothing looked at the **published bytes**. (The NF-C0e "verify the artifact, not the fixture"
  class in its purest form.)

## The fix

1. **`run_league_board.load_kdst`** — LOCAL-FIRST, then the **lake**. The projection is already
   landed at `nfl/fantasy/derived/kdst_projections/season=<season>/`; only the local read was
   missing. Verified: the lake returns **74 rows = 42 K + 32 DST** for 2026, matching the good
   08-15 board exactly. Both call sites repointed (a registry test pins that).
   ⛔ Deliberately **not** a `run_kdst_projection` step in the daily chain: K/DST is a *base
   preseason* projection with no need to refresh daily, and adding a heavy fit would add a failure
   mode to a cadence that does not need it.
2. **`export_draft_board_json.assert_published_position_coverage`** — a publish-time guard that
   **opens the staged JSON on disk** and REFUSES if any `PROJECTABLE` position has zero **projected**
   rows. It runs before the upload decision, on dry runs as well as `--publish`, with no env escape
   hatch (INC-39).
   ⭐ **It counts PROJECTED rows, not rows.** `kdst_records` gap-fills an unprojected placeholder per
   (pos, team), so the broken board still shipped 32 K + 32 DST rows with `pts: null` — a
   presence-only check would have passed the exact artifact it exists to catch.
3. **Three distinguishable causes on My Teams** — `/nfl/my-teams` now returns `board_positions`
   (derived from the board's own rows, additive per NF-C0), and the surface says which of *"we have
   not published that position"* / *"we could not resolve this name"* / *"we do not project this
   position"* applies, with a fourth `unknown` state for the deploy-skew window. Only the
   name-resolution case suggests a re-import.

**Two-sided proof against the real artifacts:** the guard PASSES the good 08-15 export (868 players)
and REFUSES the live 08-16 board (795 players) — not a synthetic fixture, the bytes that shipped.

---

## ⏭️ Operator: rebuild + republish (LAPTOP)

The board rebuild is a laptop task (SF-free; the box is a 2-vCPU r6g.large). ⚠️ A laptop run still
writes **PRODUCTION** S3 keys.

**1 — rebuild the boards** (reads the projections + K/DST written by the earlier steps):

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
SPORTS_LAKE_REGION=us-east-2 AWS_DEFAULT_REGION=us-east-2 \
  uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_league_board \
  --projection-season 2026
```

**2 — export and DRY-RUN first** (the coverage guard runs here; a refusal means K/DST did not load):

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
SPORTS_LAKE_REGION=us-east-2 AWS_DEFAULT_REGION=us-east-2 \
  uv run python -m quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json \
  --season 2026 --s3-bucket credence-prod-s3-api-cache
```

Expect in the log:

```
NF-K1 position coverage OK — every PROJECTABLE position (QB, RB, WR, TE, K, DST) carries a
projected row in all 15 staged board/projections file(s)
```

**3 — publish** (only after step 2 reports coverage OK):

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
SPORTS_LAKE_REGION=us-east-2 AWS_DEFAULT_REGION=us-east-2 \
  uv run python -m quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json \
  --season 2026 --s3-bucket credence-prod-s3-api-cache --publish
```

**4 — 🟥 RUNTIME CONFIRMATION (the gate CI cannot provide).** Read the LIVE artifact back:

```bash
curl -s "https://api.credencesports.com/fantasy/nfl/projections?season=2026" \
  | python3 -c "import json,sys,collections; d=json.load(sys.stdin); \
print(d['generated_at']); print(collections.Counter(p['pos'] for p in d['players']))"
```

**PASS** = a `generated_at` from this run **and** non-zero `K` and `DST` (expect ~42 K, 32 DST,
~868 players). A count of 795 with no K/DST means the old board is still being served.

**5 — the frontend half needs no deploy** (`frontend/` auto-deploys on push to `main`), **but the
API change does**: `board_positions` is a new key on `/fantasy/nfl/my-teams`, and the API Lambda has
no CI/CD:

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
./infrastructure/lambda/deploy.sh
```

The change is additive on both sides (NF-C0): an older client ignores the key, and an older API
sending no key leaves the surface on its previous single "not matched" wording rather than asserting
a cause it cannot support. So the two halves may ship in either order.
