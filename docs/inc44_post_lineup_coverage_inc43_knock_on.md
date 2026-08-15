# INC-44 — the 08-13 `post_lineup` coverage regression is the INC-43 knock-on (2026-08-14)

**Diagnosis only. Read-only, SF-free (DuckDB over the S3 lakehouse); no flip, no deploy, no box
run, no code change.** `best_alpha=0`.

**VERDICT: TRANSIENT — a knock-on of INC-43, self-healed, with the 08-13 rows permanently frozen
by the INC-32 one-and-done rule. Not an INC-17-class block regression. No new code fix; INC-43's
own fix is the fix.** One caveat is stated honestly in *Not verified* below.

---

## The alert, reproduced exactly

Read from the SERVED artifact (`daily_model_predictions` S3 parquet — what
`write_serving_store --s3` / `write_api_cache` actually serve), never from a mart:

| score_date | games | avg cov | min cov | `feature_store` | `intraday_assembly` |
|---|---|---|---|---|---|
| 08-06 | 8 | 1.0000 | 1.000 | 8 | 0 |
| 08-07 | 15 | 0.9666 | 0.833 | 15 | 0 |
| 08-08 | 15 | 0.9889 | 0.833 | 15 | 0 |
| 08-09 | 15 | 0.9666 | 0.833 | 15 | 0 |
| 08-10 | 10 | 1.0000 | 1.000 | 10 | 0 |
| 08-11 | 15 | 0.9777 | 0.833 | 15 | 0 |
| 08-12 | 15 | 0.9889 | 0.833 | 15 | 0 |
| **08-13** | **9** | **0.8519** | **0.667** | **5** | **4** |
| 08-14 | — | — | — | — | — (had not run at read time — see below) |

`0.8519` matches the alert's `0.852`; the 08-06→08-12 mean is `0.984` against the alert's quoted
0.977 trailing-14d baseline. **08-11 and 08-12 are healthy, so the event is isolated to 08-13.**

⭐ Note `data_source` is **`intraday_assembly`**, not `intraday_fallback` — the distinction the
E11.27 monitor's design note calls out. A monitor keyed only on `intraday_fallback` would not see
this; the coverage monitor did.

---

## Mechanism — the within-day control settles it

INC-43 HALTed `daily_ingestion_job` at `lakehouse_w3_marts_op` at **12:00 UTC** on 08-13 and did
not recover until **22:03**. `post_lineup` fires per game as its lineup completes, so 08-13's slate
was scored *across* that window — which hands us a controlled comparison inside a single day:

| window | games | avg cov | `feature_store` |
|---|---|---|---|
| scored **BEFORE** 22:03 recovery | 7 | **0.8096** | 3 / 7 |
| scored **AFTER** 22:03 recovery | 2 | **1.0000** | 2 / 2 |

Same day, same slate, same code, same model. The only variable is which side of the INC-43
recovery the game was scored on. Per game:

| game_pk | inserted_at (UTC) | cov | data_source | imputed |
|---|---|---|---|---|
| 824238 | 14:50:56 | 0.667 | `intraday_assembly` | elo_diff, home_bp_eb_{coverage_pct,uncertainty,xwoba}, park_run_factor_3yr |
| 823829 | 14:50:56 | 1.000 | `intraday_assembly` | elo_diff |
| 824561 | 15:21:03 | 1.000 | `intraday_assembly` | elo_diff |
| 823508 | 16:21:13 | 0.667 | `intraday_assembly` | away_bp_eb_{coverage_pct,uncertainty}, elo_diff |
| 822776 | 16:50:38 | 0.833 | `feature_store` | — |
| 822696 | 19:11:35 | 0.833 | `feature_store` | — |
| 823669 | 20:21:16 | 0.667 | `feature_store` | park_run_factor_3yr |
| 823915 | 23:42:56 | **1.000** | `feature_store` | — |
| 823995 | 23:42:56 | **1.000** | `feature_store` | — |

The four games scored 14:50–16:21 fell through to `intraday_assembly` because the feature store had
no 08-13 rows yet (the build was HALTed). The `feature_store` games at 16:50–20:21 read a stale /
partially-built store. Both games scored after the recovery are clean at 1.000.

### The blocks are broad AND entirely new — not one block breaking

Every imputed block on 08-13, counted against the six prior `post_lineup` days:

| block | on 08-13 | on 08-07→08-12 | prior days seen |
|---|---|---|---|
| `elo_diff` | 4 | **0** | 0 |
| `park_run_factor_3yr` | 2 | **0** | 0 |
| `away_bp_eb_coverage_pct` / `_uncertainty` | 1 each | **0** | 0 |
| `home_bp_eb_coverage_pct` / `_uncertainty` / `_xwoba` | 1 each | **0** | 0 |

`post_lineup` had **zero imputation on every one of the six preceding days**, then on 08-13
imputed across **three unrelated feature families at once** (team ELO, park factors, bullpen EB).
A single broken block cannot produce that shape; broad upstream staleness can. This is the INC-43
fingerprint, and it is what distinguishes it from the INC-17 class the alert is named for.

### Why the 08-13 rows will never improve

`post_lineup` is **one-and-done** (INC-32): step 2b only re-fires games *missing* a `post_lineup`
row, so the first degraded write is frozen permanently. The three 0.667 games were served at 0.667
to users and will stay that way. ⇒ **nothing to re-run; the rows are historical.**

---

## Both "untracked" candidates — explicitly RULED OUT

Checked because a stale EB build makes `avg_eb_woba` serve NULL with **no imputation token**, so
that outage would be invisible in `imputed_features`.

1. **`eb_batter_posteriors_raw` / `avg_eb_woba`** — ❌ not the cause. The EB build reaches the
   slate (`max(game_date) = 2026-08-13`, 486,324 rows), and `feature_pregame_lineup_features`
   `avg_eb_woba` is **100.0% covered on 08-13** (18 rows, 0 NULL) — as on 08-10/11/12.
2. **`mart_game_spine`** — ❌ not the cause. It holds **9** games for 08-13, and
   `stg_statsapi_games` shows exactly **9 Final** games that day. 08-13 was simply a 9-game slate
   (cf. 15 on 08-11/08-12). No game was dropped.

⭐ **A third "untracked" reading dissolves on the baseline:** two games sit at `0.833` with an
**empty** `imputed_features`, which looks like a block failing without a token. It is not — `0.833`
is the **routine minimum on every healthy day** (08-07/08/09/11/12 all have `min_cov = 0.833`). The
anomaly on 08-13 is the three games at **0.667**, not the two at 0.833.

The SF-vs-S3 agreement check (the one-query eliminator for the ext-table read-bug family) was
**not needed**: that class shows S3 healthy + SF NULL, and here the served S3 artifact itself
records `intraday_assembly` at scoring time, which is a timing fact, not a read bug.

---

## Self-heal evidence

- The two post-recovery 08-13 games scored **1.000** (above).
- **08-14 `morning` is 28/28 `feature_store`** across 14 games — the feature store is building
  normally today. (Contrast 08-13 morning: 9 of 18 rows `feature_store`.)
- INC-43's 08-14 12:00 daily ran clean.

⚠️ **08-14 `post_lineup` had not run at read time, and that silence is CORRECT, not a second
incident** — the INC-40 amendment (normalise against first pitch, never wall-clock): 13 of the 14
games on 08-14 first-pitch at **22:10 UTC or later** (one at 18:20), and `post_lineup` fires ~5h
out gated on complete 9-slot orders both sides. At the ~17:00 UTC read there was nothing eligible.

---

## ⏭️ The open question for the operator/PM — should the monitor suppress on a HALT day?

**Recommendation: annotate, do not suppress.** Reasons, in order:

1. **A HALT day is when serving is *most* likely genuinely degraded**, not least. Muting the
   coverage monitor on exactly those days blinds the real INC-17 detector at its highest-yield
   moment — the E11.30 balance tipped the wrong way.
2. **Suppression needs the monitor to read the job's state**, which is a new coupling that can
   itself fail (and fails silently in the direction of *not paging* — the class E11.30 exists to
   correct).
3. **The alert was not wrong and was not noise — it produced real information**: three games were
   served at 0.667 and are frozen there forever. That is a user-facing fact somebody should know.
4. The actual complaint is that it paged *without saying it was a known knock-on*. That is an
   **annotation** problem: have the alert state whether the slate's `daily_ingestion_job` completed,
   so a reader triages in one glance. Ambiguous ERROR → self-explaining ERROR, detector intact.

⛔ Not implemented here — it is a PM/operator call, and it is a monitor change, not an incident fix.

---

## NOT VERIFIED — do not inherit these as settled

- **08-14 `post_lineup` is still unread** (it had not fired at diagnosis time). The self-heal rests
  on the two post-recovery 08-13 games + a healthy 08-14 morning tier, which is strong but is not
  the direct next-day reading. ⏭️ **LAPTOP, after tonight's slate:**
  `uv run python -c "import duckdb,os; os.environ.setdefault('AWS_DEFAULT_REGION','us-east-2'); from betting_ml.utils.delta_lakehouse import register_lakehouse_views as r; c=duckdb.connect(); r(c,('daily_model_predictions',)); print(c.execute(\"select score_date,count(*) games,round(avg(feature_coverage_score),4) avg_cov,min(feature_coverage_score) min_cov from daily_model_predictions where prediction_type='post_lineup' and score_date>='2026-08-13' group by 1 order by 1\").fetchdf())"`
  Expect 08-14 ≈ 0.97–1.00. If it is also ~0.85, this diagnosis is wrong and the block regression
  is persistent → reopen and diagnose the specific block.
- **The INC-43 timeline (12:00 HALT → 22:03 recovery) is taken from the INC-43 record**, not
  re-derived here; the store's state at 14:50 cannot be reconstructed from the current parquet. The
  served `data_source` column is the contemporaneous evidence, and it is sufficient — but the
  timestamps themselves are inherited.
- **No box run.** Nothing here required one (diagnosis is read-only over the served artifact), but
  note INC-43's own 🟥 runtime gate remains open per its record.
