# NF-INJ2c node 3b — run 1 is **VOID**, and the cause is an UNRECOVERABLE market vintage

**Run:** 2026-09-01T05:02Z, laptop, main checkout on `dev`.
**Result:** `reproduction pin worst 84.7189 over 797 rows vs 0.05` → **exit 2, VOID, not a null**
(margin rule §5 branch 3). ⛔ No arm number from this run is interpretable, and none is quoted as a
result anywhere.

The runner behaved exactly as designed. What follows is why the pin could not have held, and why a
re-run at a different time of day would not have fixed it either.

---

## 1. The signature said "permutation", not "drift"

| | |
|---|---|
| rows past the 0.05 tolerance | **591 of 797** |
| worst \|Δ fp_ppr\| | **84.72** |
| worst \|Δ proj_games\| | 6.85 (only **21** rows past tolerance) |
| **rookies** (81 rows) | worst \|Δ\| **0.05** — reproduce to the tolerance |
| veterans, median ratio served/local | 0.98–0.999 — **no level shift** |

Points move **large and in BOTH directions with `proj_games` unchanged** — Josh Jacobs 194.9→110.2,
Davis Mills 14.4↔73.2, Mason Rudolph 51.2↔14.4. That is a **within-position multiset permutation**:
the ORDERING differs, not the level, not the availability cap. And it is confined to the leg that
gets ordered — rookies come through the independent NCAAF artifact and reproduce.

## 2. The market input, measured on both sides

| input | SERVED board (2026-08-31T14:18Z) | LOCAL rebuild (2026-09-01T05:01Z) | verdict |
|---|---|---|---|
| ADP (ffc ppr/12) | window 08-24→08-31, **8161 drafts** | window 08-24→08-31, **8161 drafts** | **IDENTICAL** |
| **ECR (fantasypros)** | `as_of 2026-08-31`, label **8/31**, 104 experts | cache `fp_ecr_PPR_2026.json`, label **8/25**, 108 experts, **mtime 2026-08-25T03:20Z** | **SIX DAYS APART** |

⭐ ADP matching is what kills the obvious "14.7h of intraday drift" story. The input that moved is
**ECR, by six days**, and `nf1_3_model` builds the ordering feature as
`market_rank = ecr.where(ecr.notna(), adp)` — **ECR-primary**, ADP only a fallback — with
`market_rank` in `POSITION_FEATURES` for **all four positions**.

**The independent confirmation, and it lands on the exact failing number:** the single largest ECR
move in the file between the two vintages is **Josh Jacobs, rank 43 → 145 (−102)** — final-cuts week
— and Josh Jacobs is the single largest point mover, at **84.72**, which *is* the pin's reported
worst difference. Largest ECR mover = largest point mover = the failure.

## 3. Why it happened — a flag NAME shared by two entrypoints with DIFFERENT SCOPE

* `run_nf1_5.py --market-refresh` → *"re-fetch **ADP/ECR** for the CURRENT season"*.
* `run_season_projection.py --market-refresh` → *"re-fetch the **ADP census**"*, and its own comment
  says *"Here it only affects the NF-D11 coverage AUDIT (MVP-1 is market-blind by design)"*.

The served board is **`projectionSource: "nf1_5"`** — the market-AWARE refined board. The operator
handoff prescribed the `run_season_projection` form, which refreshes ADP only. Measured consequence:
`ffc_ppr_12_2026.json` mtime **2026-09-01T05:01:25Z** (rewritten), `fp_ecr_PPR_2026.json` mtime
**2026-08-25T03:20:47Z** (untouched).

⛔ **And correcting the command would NOT have fixed this run**, which is the part that matters:
`apply_2026` hardcodes `market_refresh=False` at **both** call sites. That is the RIGHT choice — it
is how an archived run is reproduced byte-for-byte — but it means **the pin holds only if the
ON-DISK ECR cache is the same vintage the served board was built from**, and nothing in the pipeline
ensures that.

## 4. ⭐ The structural finding: this pin is UNACHIEVABLE against the captured board, permanently

FantasyPros serves **only the current snapshot** — there is no as-of query (verified: a live pull
today returns label `9/01`, 98 experts). The lake asset `nfl/fantasy/benchmarks/ecr_benchmark` is
**season-partitioned and overwritten**, so it holds no daily history either.

⇒ **2026-08-31's ECR no longer exists anywhere we can reach.** No command, no timing, and no re-run
recovers it. A refresh today would put the local build on `9/01` against a board built on `8/31` —
*differently* wrong, not fixed.

This is the D3 convention meeting its own limit: capture-pinning the ARTIFACT is not sufficient when
the artifact's INPUTS are unrecoverable daily vendor snapshots. **The capture must include the market
inputs, taken at the same moment as the board** — otherwise the pin is a race against a vendor's
update clock that the study loses by default.

## 5. What makes the next run able to hold

Both sides must sit on the **same ECR day**. FantasyPros rolls its label around 03–05Z; the board
publishes ≈14:18Z. So the workable window is **after that day's publish and before the next roll**,
with the ECR cache refreshed to that same day *before* the arms are built.

⚠️ Even then the pin is a race against an intra-day FP update, which is why §4's durable fix — pin
the market caches beside the board at capture time — is the thing worth building rather than a
timing prescription to re-follow.

## 6. What this does NOT say

⛔ Nothing here is evidence for or against the dominance disposition. The arms' figures from this run
are not quoted, not compared and not carried forward. The margin rule's branch 3 is what the runner
executed, and it executed correctly: **VOID is a statement about the measurement, never about the
arm.**
