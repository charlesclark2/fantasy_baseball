# E11.5 — dbt Engine Decision Spike

**Date:** 2026-06-19  
**Status:** DECIDED  
**Spike scope:** Which engine drives the cost-opt lakehouse lane (E11.1-W1 + E11.2-T2)?

---

## Decision

**STAY ON dbt-FUSION (single engine).** No dual-engine split needed.

The dbt1060 blocker in `server.py` is a **YAML config format issue, not a feature gap.** Moving `freshness`/`loaded_at_field` from top-level to `config:` nesting unblocks E11.2-T2 immediately. dbt-fusion also runs `dbt-duckdb` models (empirically confirmed), so E11.1-W1 can proceed on the same engine. No dual-engine complexity is needed.

---

## 1. Landscape — Versions and Engine Relationship

| Component | Local version | What it is |
|---|---|---|
| `dbtf` | 2.0.0-preview.190 (Rust, 222 MB standalone binary) | dbt-fusion preview — the active project engine |
| venv `dbt` | 1.11.10 (Python script, 386 B) | dbt-core Python track — installed but NO adapters wired |
| `dbt-duckdb` | 1.10.1 (installed into venv 2026-06-19 spike) | Python adapter for dbt-core; see adapter note below |

**Operator hypothesis check — "latest dbt-core runs on the Fusion engine":**  
**FALSE for 1.11.x.** dbt-core 1.11.x is Python-based (separate codebase). dbt-fusion is a standalone Rust binary. They are distinct today. (Note: dbt Labs announced dbt Core v2.0-alpha on 2026-06-01 as a new open-source Rust-based release unified with the Fusion runtime — but that is not what either local install is. We have fusion preview on one side and the Python 1.11.x core on the other.)

**The venv `dbt` 1.11.10:** No adapters are installed in the venv (`pip list | grep dbt` → empty). It would need `dbt-snowflake` installed to handle the prod Snowflake workload — it cannot replace `dbtf` today without also installing the adapter and validating parity.

---

## 2. Empirical Evidence

All tests run 2026-06-19 against a throwaway project at `/tmp/dbt_spike_clean/` (dbt-duckdb DuckDB profile, one-row `SELECT 1` model, sources.yml with freshness config).

### 2a. dbt-duckdb adapter compatibility

| Test | Engine | Result | Error |
|---|---|---|---|
| A | dbt-core 1.11.10 + dbt-duckdb 1.10.1 `dbt run` | ✅ PASS — `1 of 1 OK created sql view model` | — |
| B2 | dbt-fusion 2.0.0-preview.190 `dbtf run` (no freshness sources) | ✅ PASS — `1 success` | — |

**Finding:** dbt-fusion CAN use the Python `dbt-duckdb` adapter. The adapter is loaded from the venv path; fusion invokes it for DuckDB targets. Both engines support the dbt-duckdb workload E11.1-W1 requires.

### 2b. Freshness config parsing

**Top-level style** (current stripped format, what was blocked):
```yaml
tables:
  - name: raw_events
    loaded_at_field: ingestion_ts        # TOP-LEVEL — blocked on fusion
    freshness:
      warn_after: {count: 24, period: hour}
```

| Test | Engine | Command | Result | Error code |
|---|---|---|---|---|
| C | dbt-core 1.11.10 | `dbt parse` | ✅ PASS (exit 0) | — |
| D | dbt-fusion | `dbtf parse` | ❌ FAIL (exit 1) | dbt1060 × 2 |
| D2 | dbt-fusion | `dbtf source freshness` | ❌ FAIL (exit 1) | dbt1060 × 2 |

**dbt1060 message:** `Ignored unexpected key "loaded_at_field"` and `Ignored unexpected key "freshness"` — parse-time hard errors that abort the command.

**`config:` nesting style** (the fix):
```yaml
tables:
  - name: raw_events
    config:                              # NESTED — accepted by fusion
      loaded_at_field: ingestion_ts
      freshness:
        warn_after: {count: 24, period: hour}
```

| Test | Engine | Command | Result | Error |
|---|---|---|---|---|
| F | dbt-fusion | `dbtf parse` | ✅ PASS (exit 0) | — |
| F2 | dbt-core | `dbt parse` | ✅ PASS (exit 0) | — |
| G | dbt-fusion | `dbtf source freshness` | ✅ Runs — fails at DB level only (dbt1308: Catalog DNE — expected, no real DuckDB source) | dbt1308 |
| G2 | dbt-core | `dbt source freshness` | ✅ Runs — fails at DB level only (same reason) | DB error |

**Finding:** The `config:` nesting style is accepted by BOTH engines. No feature gap.

### 2c. `source_status:fresher+` selector

| Test | Engine | Command | Result |
|---|---|---|---|
| H2 | dbt-fusion | `dbtf build --select source_status:fresher+` | ✅ Accepted — dbt1092 warning: "no nodes matched" (expected: no prior `sources.json` from a successful freshness run) |

**Finding:** dbt-fusion recognizes and processes the `source_status:fresher+` selector. The `dbt1092` warning is the correct no-op behavior when no prior state exists (graceful fallback to full build). The selector will match real nodes once `dbtf source freshness` has run successfully against a live Snowflake source and written `sources.json`.

---

## 3. Recommendation

**Option (i) — Stay fusion, fix the YAML format.** No engine change. No dual-engine setup.

### Why not dual-engine (Option ii)?
- dbt-fusion already handles dbt-duckdb (confirmed empirically)
- The freshness blocker is 2-line YAML not a missing feature
- Dual-engine adds: two binaries, two CI configs, two invocation conventions, divergent behavior to debug

### Why not all dbt-core (Option iii)?
- The venv dbt-core 1.11.10 has no adapters installed (would need dbt-snowflake re-wired and validated)
- `dbtf` convention is already established across the project (`CLAUDE.md`, CI, Makefile, server.py)
- No benefit: fusion already does what core does for our workload

**No CLAUDE.md / §0.1 convention change required.** `dbtf` remains the project-standard command.

---

## 4. Concrete Config Delta for W1 and T2

### 4a. `dbt/models/sources.yml` — freshness block reformat (T2 reactivation)

For every source table that needs freshness monitoring, move `loaded_at_field` and `freshness` under `config:`:

```yaml
# BEFORE (stripped / blocked):
tables:
  - name: mlb_odds_raw
    loaded_at_field: ingestion_ts
    freshness:
      warn_after: {count: 2, period: hour}
      error_after: {count: 6, period: hour}

# AFTER (fusion-compatible, both engines accept):
tables:
  - name: mlb_odds_raw
    config:
      loaded_at_field: ingestion_ts
      freshness:
        warn_after: {count: 2, period: hour}
        error_after: {count: 6, period: hour}
```

Apply to the Snowflake-backed sources that T2 will gate on. **Note (2026-06-19): Parlay API ingestion is currently off.** To avoid `dbtf source freshness` aborting the flow, all four parlayapi tables use **warn-only** (no `error_after`) — stale data emits a warning but exits 0, so the state-based build continues. When ingestion resumes, add `error_after` thresholds. Tables that receive data once daily can use `warn_after: {count: 25, period: hour}`.

### 4b. `services/dbt_runner/server.py` — un-bypass the state-aware path (T2 reactivation)

Current bypass code (lines 169–179):
```python
if use_state:
    _download_state()  # pre-warm only; selector inactive
    log.append("[dbt-runner] use_state=True but source_status selector inactive"
               " (dbt-fusion does not yet support freshness config) — running original args\n")
```

Replace with (after sources.yml is reformatted):
```python
if use_state:
    state_ready = _download_state()
    if state_ready:
        # Inject source_status:fresher+ into the select args
        target_args = _extract_target_args(args)
        cmd_source_freshness = ["dbtf", "source", "freshness",
                                "--project-dir", _DBT_PROJECT_DIR,
                                "--profiles-dir", _DBT_PROJECT_DIR] + target_args
        _run_cmd(cmd_source_freshness, env)  # non-fatal if it errors
        effective_args = ["build", "--select", "source_status:fresher+",
                          "--state", _STATE_LOCAL_DIR] + target_args
    else:
        effective_args = args  # no prior state → full build
```

### 4c. E11.1-W1 dbt-duckdb profile addition

Add a `duckdb` target to `dbt/profiles.yml` for the lakehouse lane. W1 can use `dbtf run --target duckdb` from the same Railway container. No second binary or CI job needed.

```yaml
baseball_betting_and_fantasy:
  target: dev
  outputs:
    dev:         # existing Snowflake target
      type: snowflake
      ...
    duckdb:      # new lakehouse target (W1)
      type: duckdb
      path: "{{ env_var('DUCKDB_PATH', '/data/baseball.duckdb') }}"
      extensions:
        - httpfs    # for S3 reads
```

---

## 5. T2 Reactivation Verdict

**E11.2-T2 can reactivate WITHOUT waiting** on a new fusion release. The 2-file fix (sources.yml reformat + server.py un-bypass) is sufficient. It can ride alongside the first W1 PR or be a standalone 1-day story.

**Sequencing:**
1. Reformat `sources.yml` freshness blocks (one commit)
2. Un-bypass `server.py` use_state path (one commit)
3. Confirm: `dbtf source freshness --target prod` writes `sources.json` to `target/`
4. Server uploads `sources.json` to S3 after first successful run
5. Second run: `dbtf build --select source_status:fresher+ --state /tmp/dbt-state/` skips unchanged sources → cost reduction realized

---

## 6. Compatibility Cost of Single-Engine Decision

| Concern | Impact |
|---|---|
| dbt-fusion is still "preview" | Low: it's the current production engine; no regression risk from staying |
| dbt-duckdb on fusion — future breakage? | Low: adapter worked in test; watch fusion release notes for adapter-contract changes |
| dbt Core v2.0 (alpha, Jun 2026) | Monitor: when it stabilizes, fusion preview will converge; no migration needed |
| CLAUDE.md / §0.1 `dbtf` convention | No change — convention stays valid |

---

## 7. Files Changed (T2 reactivation shipped in this spike)

The 2-file fix is **CODE-COMPLETE 2026-06-19**:

```
git add dbt/models/sources.yml          # freshness blocks added (config: style) for 4 parlayapi tables
git add services/dbt_runner/server.py   # use_state path activated (was bypassed with comment)
git add docs/e11_5_dbt_engine_decision.md
```

**CI gate result:** `dbtf parse` exit 0 (no dbt1060); `dbtf compile` exit 0 — 125 models / 1629 tests clean. Only pre-existing warnings (dbt1041 package-lock, dbt1203 cloud deferral).

**Note on Parlay API off (2026-06-19):** All four parlayapi freshness blocks use warn-only (no `error_after`), so `dbtf source freshness` exits 0 even when parlayapi is stale. The state-based build flow is unblocked. When ingestion resumes, add `error_after: {count: 8, period: hour}` to the three intraday tables and `{count: 48, period: hour}` to `mlb_canonical_events_raw`.

No version/install steps needed — dbt-fusion 2.0.0-preview.190 already supports both changes as confirmed empirically.
