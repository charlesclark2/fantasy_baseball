# NF-INC-0916 — operator handoff

Written for: **Charlie (operator)**, to run in order.

Spec: `plan_specs/nfl_fantasy/nf-inc-0916.yaml` (`IN_PROGRESS`). Branch `nf-inc-0916`, PR **#1141 → `dev`**.

---

## What is wrong, in three lines

The weekly model's two training feeds (`stats_player_week`, `snap_counts`) had **no scheduled ingest anywhere**, so the 2026 week-1 training rows carried no stat line, `attach_labels` filled them with zeros under the retained-zero convention, and the hurdle learned a `P(zero)` from a week nobody had played. Population-matched against realized scoring the served point runs at **0.355** of reality — **QB 0.205**, RB 0.465, WR 0.358, TE 0.402. `best_alpha = 0`, so nothing was staked on it.

---

## ⭐ STEP 1 — merge #1141 to `dev`, then promote `dev` → `main`. This is the one that matters today.

Node 0 (the withholding) is frontend-only, and **Vercel production is `main`** — so the suppression reaches users only through the `dev → main` promotion you are currently holding.

**The hold is now discharged, and here is the reasoning rather than an assertion.** #1139 carries two separable things:

| | verdict |
|---|---|
| NF-WK-TD1's touchdown **emission** (box code) | **harmless under suppression.** The only surface that renders a weekly stat line is the paid panel, which node 0 now withholds from *every* caller. The box publishing TD columns nobody can see costs nothing. |
| the changelog entry **announcing** it | **not harmless.** It tells users about a stat line the same release refuses to show them. |

So the announcement has been **deferred** into `frontend/data/changelog-held.json` — verbatim, with its week, its gate and why. That is what the spec already required of it (node 4(ii): *"its changelog entry publishes only now, when it is true"*). **It is held, not lost**, and restoring it at node 4 is now *mandatory*: the gate below fails the build if the flag is lifted while the registry is non-empty.

⚠️ **This edits NF-WK-TD1's merged changelog entry.** Flagging it plainly rather than burying it — nothing else in #1139 is touched.

**After the promotion, verify by content (cache-busted), not by a green deploy:**

⚠️ **Two traps in this check, both of which return `0` on a perfectly healthy page.** (a) React escapes `'` to `&#x27;`, so a grep string containing an apostrophe never matches the rendered HTML; (b) the weekly **table is client-rendered**, so `curl` of the server HTML cannot see a single cell — a grep for the notice proves only that the banner shipped, never that the numbers are withheld. Use both commands below.

```bash
# LAPTOP. ~2 s. The notice shipped (apostrophe-free fragment, deliberately).
curl -s "https://www.credencesports.com/fantasy/weekly?cb=$(date +%s)" \
  | grep -c "projected points down"
# expect: 1   (withheld)   /   0 after node 4 (un-suppressed)
```

```bash
# LAPTOP. ~15 s. The CELLS are withheld — reads the shipped client bundle,
# which is the only place the row rendering is decided.
cd "$(mktemp -d)" && curl -s "https://www.credencesports.com/fantasy/weekly?cb=$(date +%s)" -o p.html \
  && grep -o 'src="/_next/static/chunks/[^"]*"' p.html | sed 's/src="//;s/"//' \
     | while read -r c; do curl -s "https://www.credencesports.com${c}"; echo; done > b.js \
  && grep -c 'point:g,p10:g,p90:g,ros:g,rosP10:g,rosP90:g,band:!1,statLine:!1' b.js
# expect: 1   (every model cell folded to the withheld singleton, no conditional)
# after node 4 this goes to 0 and the row view carries real values instead.
```

Verified live 2026-09-16 on `dpl_54WZndz76f3GBdEWBUrcUWzd5Db9`: both return as expected.

⚠️ And the repo's standing hazard applies: a long-open `dev → main` PR can merge an **earlier** `dev` snapshot with every signal green. Verify `main`'s actual file content afterwards, never the merge status:

```bash
# LAPTOP
git fetch origin
git show origin/main:frontend/lib/weekly-suppression.ts | grep -c 'WEEKLY_NUMBERS_WITHHELD = true'   # expect 1
git rev-list --count origin/main..origin/dev                                                          # expect 0
```

---

## STEP 2 — the retrain happens BY ITSELF, and that is the intended path

`orchestration_cd.yml` fires on a push to `main` and its path filter covers every file this story changed (verified: `pipeline/**`, `betting_ml/**`, `quant_sports_intel_models/football/nfl/{ingest,fantasy}/**`). So merging to `main` rebuilds and deploys the box image, and the **next `sports_nfl_weekly_serving_schedule` fire (daily, 08:30 PT)** runs the corrected chain:

```
nfl_weekly_stats_ingest_op  →  nfl_weekly_stats_freshness_op  →  nfl_weekly_serving_op
   (refresh the two feeds)       (is each carrying the last        (train + publish, now
                                  week that was played?)            REFUSING a fabricated week)
```

That IS node 3's "retrain + republish through the registered pipeline". **Nothing to run by hand.**

**If you want it sooner than 08:30 PT**, run it manually from a checkout of **merged `dev`** (⛔ never from the story branch — the standing `--publish`-from-merged-`dev` rule). Both commands, in this order, because a manual build does **not** run the ingest op:

```bash
# LAPTOP, repo root, on merged dev. ~20 s. Writes PRODUCTION S3 (the raw lake).
AWS_DEFAULT_REGION=us-east-2 uv run python -m quant_sports_intel_models.football.nfl.ingest.in_season_stats

# LAPTOP, repo root, on merged dev. ~9 min. Writes PRODUCTION S3 (the live api-cache).
AWS_DEFAULT_REGION=us-east-2 uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving \
  --s3-bucket credence-prod-s3-api-cache --publish
```

Success looks like: `weekly_train_stat_coverage_min` well above `0.30`, a `stat vintage vs training boundary` line whose `stats_as_of` is **not** behind `train_through`, and a published manifest for the target week.

⚠️ **The ingest may report "0 not-yet-published" and change nothing** — that is fine and expected. The lake already holds 2026 wk 1 for both feeds (1,118 / 1,492 rows), written **once** at 2026-09-16T02:43Z. The Delta history shows nothing else for these tables since the 2026-07-18 historical backfill, while `weekly_rosters` (a real roll-forward source) writes several times a day. **That contrast is the proof**: the rows were present and the *cadence* was absent — the `stg_ref_players` shape, invisible to a row count.

---

### ⭐ Did the retrain actually correct it? Read the PUBLISHED MANIFEST — one command, no box access

This is the decisive check and it needs nothing but `curl`. The manifest carries the
defect's own two-field proof, so it answers the question directly rather than by proxy.

```bash
# LAPTOP. ~2 s. Read-only. Exit 0 = corrected, exit 1 = still defective.
curl -s "https://api.credencesports.com/fantasy/nfl/weekly/manifest?cb=$(date +%s)" | python3 -c '
import json, sys
d = json.load(sys.stdin); v = d.get("input_vintage", {})
def wk(s):
    try:
        y, w = str(s).split("-W"); return (int(y), int(w))
    except Exception: return (0, 0)
st, sn = wk(v.get("stats_as_of")), wk(v.get("snaps_as_of"))
tt = (v.get("train_through_season") or 0, v.get("train_through_week") or 0)
print("generated_at :", d.get("generated_at"), " target:", d.get("season"), "wk", d.get("week"))
print("stats_as_of  :", v.get("stats_as_of"), "  snaps_as_of:", v.get("snaps_as_of"))
print("train_through:", tt[0], "wk", tt[1])
ok = st >= tt and sn >= tt
print("VERDICT      :", "OK - both feeds reach the training boundary" if ok
      else "DEFECTIVE - a feed is BEHIND train_through")
sys.exit(0 if ok else 1)
'
```

**Proven two-sided.** Run against the live served manifest on 2026-09-16 (built by the
**09-15** 08:30 PT fire, i.e. before the fix deployed) it returns:

```
generated_at : 2026-09-15T15:32:59+00:00  target: 2026 wk 2
stats_as_of  : 2025-W18   snaps_as_of: 2025-W18
train_through: 2026 wk 1
VERDICT      : DEFECTIVE - a feed is BEHIND train_through      (exit 1)
```

That is the incident, still on the wire, dated. **Read the three outcomes correctly:**

| after the next 08:30 PT fire | means |
|---|---|
| `generated_at` advances **and** VERDICT OK | **fixed** — go to the after-table below |
| `generated_at` does **not** advance | node 2's publish guard **REFUSED** to publish a payload whose stats are behind its training boundary. The guard is working; the *ingest* is not landing. Check the run, not the guard. |
| `generated_at` advances but VERDICT still DEFECTIVE | the publish guard failed to fire — that is a defect in node 2 and should be reported |

---

## STEP 3 — read the table, then rule on un-suppression

Once a corrected payload has published, produce the after-table with **the same runner that reproduced TD1's before-table** (so the two are comparable by construction):

```bash
# LAPTOP, repo root. ~40 s. Read-only.
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inc_0916_level \
  --payload quant_sports_intel_models/football/nfl/fantasy/artifacts/weekly_serving/2026/<WEEK>/players.json \
  --label AFTER \
  --out    quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inc_0916_level_after.json \
  --out-md quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inc_0916_level_after.md
```

and the coherence read (TD1's method, verbatim — full-PPR weights, `gap = head − components`, per-position and signed):

```bash
# LAPTOP, repo root. ~30 s. Read-only.
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_td1_coherence \
  --before quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_wk_td1_before_week2_players.json \
  --after  quant_sports_intel_models/football/nfl/fantasy/artifacts/weekly_serving/2026/<WEEK>/players.json \
  --out    quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_wk_td1_coherence.json
```

**The BEFORE table, committed at `ablation_results/nf_inc_0916_level_before.{json,md}`:**

| POS | n served | mean PROJECTION | n realized | mean REALIZED | ratio |
|---|---:|---:|---:|---:|---:|
| QB | 88 | 1.345 | 13,575 | 6.552 | **0.205** |
| RB | 113 | 2.585 | 22,094 | 5.547 | **0.466** |
| WR | 179 | 2.057 | 31,372 | 5.743 | **0.358** |
| TE | 120 | 1.433 | 18,230 | 3.563 | **0.402** |
| **ALL** | **500** | **1.901** | **85,271** | **5.355** | **0.355** |

…and 10 of the top 10 projections carried `fpP10 = 0.00` against plausible ceilings (McCaffrey 0.00 / 10.45 / 27.17). **That is the discriminating read**: a uniform scale error and an inflated zero atom both depress the mean, and they are different defects. If the atom is fixed, the top rows come back with a non-zero p10.

⛔ **No acceptance threshold has been invented, in the code or the tests.** The criterion in the spec is that the fabricated-zero mechanism is gone and the ratio is reported honestly. **You read the table and rule on un-suppression.**

⚠️ **Registered expectation for the coherence read, so it is not misread as a regression:** TD1's node-3 hypothesis was **refuted** — emission is expected to make coherence **worse**, in 7 of 8 cells. The served component line was running *hot* by roughly the value of the four terms it omitted, so the near-zero pooled coherence was two offsetting errors. **A widening gap is the predicted result.**

### ⏳ The zero-clip re-read is a SECOND, LATER pass — it is calendar-bound, not missing

TD1's component-head zero-clip figures (QB `passing_tds` 1.40×, TE `receiving_tds` 3.41×, n=78/113) compare the head's MEAN against REALIZED per-component outcomes, which do not exist for a week until it has been **played**. 2026 week 2 runs 09-17 → 09-21, so that read cannot be taken before 09-22, and `run_nf_wk_td1_coherence` does not compute it. The level and zero-atom reads above are available the moment a corrected payload publishes; this one follows a week later.

---

## STEP 4 — the held chain, in order

1. **Un-suppress** — flip `WEEKLY_NUMBERS_WITHHELD` to `false` in `frontend/lib/weekly-suppression.ts` **and** move the held item from `frontend/data/changelog-held.json` back into `frontend/data/changelog.json` under its stated `week`, verbatim, emptying the `held` list. ⭐ The gate makes this mechanical: lifting the flag with a non-empty registry is a **red build** that names the file and the item, so the announcement cannot be quietly dropped.
2. **NF-WK-TD1's spec** flips to DONE — its emission is now in a published, corrected payload.
3. **The MT1 weekly-lens hold** lifts per the restated criterion.

---

## What is NOT covered, stated plainly

- **Node 0 is rendering only**, per the spec. The free API and CDN routes still serve the defective numbers — `curl`ing `/api/public/weekly-projections` still returns them. That is the spec's scope (`node 0 touches only its rendering, never the serving path`); the publish-path half is node 2's manifest guard, which now refuses to publish an inconsistent payload going forward.
- **The ordering was withheld too**, which is a judgment beyond the letter of the spec. Within-position ordering *probably* survives the defect, but publishing a hedged claim in the same breath as withholding the firm one it derives from is not defensible — a ranked list with its numbers stripped still reads as a ranking. `weeklyRowOrder` is the one line if you want it kept.
