# INC-45 — the box's K/DST lake read returned 0 rows, and the board froze mid-draft-season

**Status:** code fixed + guarded. 🟥 The runtime gate (the automated publish succeeding on the box)
is an operator step — CI and the laptop structurally cannot provide it, for the same reason NF-K1's
fallback shipped unproven.

**Sequence.** NF-K1 fixed a published board that carried ZERO K and ZERO D/ST by (1) making the
K/DST read LOCAL-FIRST-THEN-LAKE and (2) adding a publish-time coverage guard that refuses to ship a
board missing a projectable position. Part 2 worked exactly as designed: the product never served a
broken board again. Part 1 did not work **on the box** — the lake fallback loaded 0 rows there, so
the guard refused every morning and the published board stopped advancing. NF-K1's own recap flagged
this risk: the repair ran on the laptop, where the local parquet exists, so the lake path never
fired even once before it shipped.

## The cause: the credentials were handed to a channel the reader does not read

DuckDB's `delta` extension resolves S3 credentials through the **Secret Manager** only.
`SET s3_access_key_id / s3_secret_access_key / s3_region` is an **httpfs** channel, and `delta_scan`
**ignores it**.

`run_league_board._kdst_lake_connection` resolved credentials correctly — through
`s3io.storage_options()`, the botocore chain (env → profile → IMDS instance role) that every S3
writer on the box already depends on, and the one that correctly skips an empty-string AKID — and
then handed them to DuckDB through those legacy settings. They never reached the reader. What
actually authenticated the read was **delta-kernel-rs's own ambient resolution**, done inside the
extension, with no reference to anything the code had computed.

That is why the behaviour splits exactly along laptop-vs-box, and why no amount of static review of
the credential path could see it: on a laptop the ambient chain finds `~/.aws` and the read returns
74 rows; the box's ambient environment is not the laptop's.

**Measured, both directions**, with the ambient chain stripped (empty-string `AWS_ACCESS_KEY_ID`, no
`~/.aws`) and real credentials supplied ONLY through what `storage_options()` returns — i.e. the box's
shape:

| | rows |
|---|---|
| before — credentials via the legacy `s3_*` settings | **0** — `delta_scan` ignored them and went off to IMDS by itself (`DeltaKernel ObjectStoreError … PUT http://169.254.169.254/latest/api/token`) |
| after — credentials via a `CREATE SECRET` | **74** (42 K + 32 D/ST) |

⚠️ **What is proven here and what is not.** The dead channel is proven, and it is sufficient to
produce exactly the observed symptom. Which ambient sub-cause bites on the box specifically —
an empty-string AKID, an unreachable IMDS from the container, a region default — is **not** proven
from a laptop, and this session had no box access (`ssm:SendCommand` / `ec2:DescribeInstances` are
denied for `baseball-access-user`, as INC-40 records). The operator diagnostic below captures the
raw pre-fix error so the record names the sub-cause instead of inferring it. The fix does not depend
on which one it was: it stops relying on ambient resolution altogether.

## The fix

`s3io.configure_duckdb_lake_auth` / `s3io.duckdb_lake_connection` — **one owner** for "how a lake
read authenticates", placed next to `storage_options()`, which already owned the same contract for
the delta-rs **write** side. Credentials go into a `CREATE OR REPLACE SECRET (TYPE S3, …)` whenever
botocore resolves them, and fall back to `PROVIDER credential_chain` when it cannot; the region
rides the secret too, because `SET s3_region` is part of the same ignored channel.

This is not a new pattern — it is the pattern every lake reader in this repo that is **proven on the
box** already used, and the fix brings the six that had forked away back onto it:

* `sports_dbt/profiles.yml` — `provider: credential_chain`, and it `delta_scan`s *this exact bucket
  on this exact box* in `sports_nfl_dbt_build_job`
* `ingest/query_lake`, `run_nf_c0e_captured_terms`, `kdst_source`, `xfp_source`

Six call sites carried their own copy of the broken setup: `run_league_board` (×2, including the
K/DST read and the `--from-lake` projection read), `export_draft_board_json`, `defense_source`,
`contract_source`, `coaching_source`. ⚠️ The last three **swallow the failure and recompute**, so a
broken channel there has no symptom at all — they may have been silently recomputing off-laptop for
months. That is why the fix is one owner rather than one call site.

## The decision NOT to add a scheduled K/DST rebuild

NF-K1 deliberately kept `run_kdst_projection` out of the daily chain. **That decision stands**, and
this incident is evidence for it rather than against it:

* The lake partition was **never missing**. It has held 74 rows since 2026-08-03, and the 2019–2026
  partitions are all present. Nothing needed rebuilding — the read was broken.
* K/DST is a **BASE preseason fit**. A daily rebuild would put a heavy fit, and a new failure mode,
  on the draft-critical publish path to refresh a number that does not change day to day.
* An **INC-41 freshness SLA is the wrong instrument here** for the same reason: INC-41 exists for
  artifacts that should be *advancing*, and this one deliberately should not. An SLA on it would
  page every day after its window on a perfectly healthy artifact — the alert-fatigue mode that gets
  a monitor muted.
* The right detector already exists and already worked: **NF-K1's publish-time coverage guard**
  checks *consumability at the moment it matters* and refuses the publish. That is strictly stronger
  than a freshness check on a static file, and it is what turned this from a silent regression into
  a red job with a page. The board froze **because the guard did its job**.

## 🟥 Operator steps

**1 — capture the pre-fix error (BOX).** Do this *before* deploying, so the record names the
sub-cause rather than inferring it. Prints the raw exception the swallowed read hit:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python -c "
import logging; logging.basicConfig(level=logging.INFO)
from quant_sports_intel_models.football.nfl.fantasy.run_league_board import load_kdst_lake
print('ROWS:', len(load_kdst_lake(2026)))
"
```

**2 — deploy (BOX).** ⚠️ Merge #892 (the CD path filter) first, or the change may not reach the box:

```bash
docker compose -f services/dagster/aws/docker-compose.yml up -d --build
```

**3 — confirm the read is fixed (BOX).** Same command as step 1. **PASS = `ROWS: 74`** plus a
`NF-K1: K/DST recovered from the lake — 74 row(s)` line.

**4 — un-freeze the board immediately (BOX), without waiting for tomorrow's 14:15Z schedule.**
Runs the same three steps the scheduled job runs, in the same order:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python -m quant_sports_intel_models.football.nfl.fantasy.run_nf1_5 \
    --mode build --market-refresh --duckdb /var/lib/credence/sports/sports.duckdb

docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python -m quant_sports_intel_models.football.nfl.fantasy.run_league_board \
    --projection-season 2026

docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python -m quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json \
    --season 2026 --market-refresh --s3-bucket credence-prod-s3-api-cache --publish
```

**5 — 🟥 THE RUNTIME GATE (the real proof): the AUTOMATED job succeeds.** Step 4 proves the read;
only the scheduled run proves the *job*. Let `sports_nfl_board_publish_job` fire on its own schedule
(`15 7 * * *` America/Los_Angeles = ~14:15Z) — or launch it from Dagit — and read the live artifact:

```bash
curl -s "https://api.credencesports.com/fantasy/nfl/projections?season=2026" \
  | python3 -c "import json,sys,collections; d=json.load(sys.stdin); \
print(d['generated_at']); print(collections.Counter(p['pos'] for p in d['players']))"
```

**PASS** = `K: 42`, `DST: 32`, ~868 players, and `generated_at` at the **schedule** time (~14:2x UTC)
rather than the hand-run time from step 4. A 795-player board with no K/DST means the old artifact
is still being served.
