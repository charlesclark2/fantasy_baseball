# INC-43 — `daily_ingestion_job` HALT: a DuckDB error destroyed its own diagnostic

**Date:** 2026-08-13 · **Severity:** P1 while it held (HALT-tier `lakehouse_w3_marts_op`; the
whole daily slate blocked behind it) · **Branch:** `inc-8-13`

**Status:** the *undiagnosable message* is FIXED and guarded. The *underlying* DuckDB failure is
**transient and its identity is unrecoverable** — precisely because the diagnostic was destroyed.
The same statement binds cleanly today (measured, § 4). 🟥 Runtime gate: **not closed until a real
`--w3-only` box run is green.**

---

## TL;DR

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xfc in position 15639
  at run_w1_lakehouse.py:2503 → conn.execute(f"CREATE OR REPLACE VIEW stg_batter_pitches AS {stg_sql}")
```

⚠️ **The card's traced premise — "a non-UTF-8 byte in the model SQL source" — is REFUTED by
measurement.** There is no bad byte, in that file or in any model file.

What actually happens: the DuckDB Python client converts the C++ exception string to `str`. When
that string carries raw bytes (an httpfs response body, a parquet fragment), **the conversion
itself raises `UnicodeDecodeError` and the real DuckDB error is thrown away.** The traceback then
points at the statement that failed while saying nothing about *why*.

**INC-37 (2026-08-01) diagnosed this exact mechanism and carded the fix.** A fix landed — at
**one** call site (`_build_marts`'s COPY). INC-43 is the same class arriving at a **different,
unwrapped** site. There are **67** `conn.execute` sites in `run_w1_lakehouse.py`; a per-site guard
was always going to lose this race.

---

## 1. The premise is refuted — measured, not argued

| Check | Result |
|---|---|
| Does `dbt/models/staging/stg_batter_pitches.sql` decode as UTF-8? | **Yes.** 45 non-ASCII bytes, **every one a valid multi-byte sequence** (`—` `\xe2\x80\x94`, `→` `\xe2\x86\x92`, `²` `\xc2\xb2`, `–` `\xe2\x80\x93`) |
| Is there a `0xfc` byte anywhere in it? | **No** — nor any invalid byte |
| Is the file identical to `origin/main`? | **Yes** — `git diff origin/main HEAD -- <file>` empty |
| Last commit touching it | `d26fa185` *"Retiring batter pitches"*, **2026-07-03** |
| **Did E11.24 introduce it?** | **No.** E11.24 never touched this model, and the last change to `run_w1_lakehouse.py` is `f04cc208` (INC-41) |
| Size of the **extracted duckdb branch** | **305 bytes, pure ASCII** |
| Size of the **whole assembled statement** | **350 bytes** |

⭐ **The decisive one:** the reported offset is **15639**. The entire statement is **350 bytes** —
45× smaller. The bad byte **cannot** have come from the file, the extracted SQL, or the statement.
It came from a **>15 KB message DuckDB produced while executing it**.

The traceback frame is also the tell the card missed: it names **line 2503 (`conn.execute`)**, not
line 2502 (`read_text()`). Had `read_text()` been the raiser, the frame would have been 2502 and
deeper, inside `pathlib`.

## 2. What the statement actually does

```sql
CREATE OR REPLACE VIEW stg_batter_pitches AS
select * from read_parquet(
  's3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_batter_pitches/**/*.parquet',
  union_by_name=true)
```

A read-through view over an S3 glob. Creating it forces DuckDB to **resolve the glob (S3 LIST) and
read parquet footers** to bind the schema — so this is the W3 mart build's first heavyweight S3
round-trip, and a natural place for an httpfs failure to land. A `>15 KB` error carrying raw bytes
is consistent with an embedded HTTP response body or parquet fragment.

**Same family as INC-42** (`--w3pre-only`, 2026-08-11): a transient S3 rejection surfacing through
whichever build step touches S3 first. INC-42's message survived and named
`RequestTimeTooSkewed`; INC-43's did not survive, which is the entire difference between a
30-minute diagnosis and this one.

## 3. Why the identity is unrecoverable

`UnicodeDecodeError.object` carries the full undecodable byte string — but only on the *live*
exception. Once the op died and the Dagster log kept just the repr, the bytes were gone. **Nothing
in the recorded evidence can now name the underlying DuckDB error.** That is the cost being paid
here, and it is exactly what the fix prevents next time.

## 4. It is transient — the same statement binds fine today

Laptop, 2026-08-13, prod S3, the exact extracted SQL:

```
CREATE VIEW bound OK in 86.9s — 120 columns
first cols: ['pitch_sk', 'game_pk', 'game_date', 'game_year', 'game_type']
```

⇒ no static SQL defect, no schema drift, no corrupt object on the served prefix. (Note the
**86.9 s** bind: resolving that `**/*.parquet` glob is slow, which widens the window for a
transient httpfs failure.)

---

## 5. The fix

### 5a. Root cause — install the salvage on the CONNECTION, once

`scripts/run_w1_lakehouse.py`:

* `NonUtf8DuckDBError(RuntimeError)` — the salvaged error type.
* `_salvage_non_utf8_duckdb_error(exc, sql, op)` — recovers `exc.object`, decodes with
  `errors="replace"`, and reports it **in full** alongside **the statement** and **which call**
  (`execute` / `fetchone` / …). Not head-truncated — INC-42's lesson.
* `_DiagnosticDuckDBConn` — a transparent proxy. `execute` returns `self`, so a **lazy** error
  surfacing at fetch time (where an S3 scan actually fails) is salvaged too. Only
  `execute`/`close`/`register`/`unregister` are used against the connection in this module;
  everything else passes through via `__getattr__`.
* Installed at the single construction site: `conn = _DiagnosticDuckDBConn(duckdb.connect())`.

⛔ **This is not `errors="ignore"`.** Nothing that *feeds* anything is decoded leniently. The
lenient decode applies only to an error message already on its way out.

An empty byte string reports *"nothing to salvage"* rather than an empty-looking success —
NF1.7(a): a check that recovered nothing must not read as one that recovered something.

`_build_marts`'s INC-37 handler is kept and widened to
`except (UnicodeDecodeError, NonUtf8DuckDBError)`. It adds what the connection proxy cannot know —
**the model and the S3 destination** — and without the widening it would have become dead code the
moment the proxy started salvaging first (the wired-but-never-invoked class).

### 5b. Hardening — pin the read encoding

The three `read_text()` calls (`extract_duckdb_sql`, `_raw_source_for`, the macro read) now pass
`encoding="utf-8"` explicitly rather than inheriting the box locale. **This did not cause INC-43**
(the codec in the message was already `utf-8`); it removes a latent locale dependency on HALT-tier
code. ⛔ never with `errors=` — a mangled byte would silently corrupt SQL that then gets executed
(NF-W2c: archived bytes are bytes).

---

## 6. Guards — `betting_ml/tests/test_inc43_duckdb_error_salvage.py` (fast gate, `core` shard)

All six RED-proven against deliberately-broken source, in-process, **asserting the mutation landed
first** (a RED-proof that can silently no-op reports a false "the guard caught it"):

| Break | Guard that fires |
|---|---|
| unwrap `duckdb.connect()` | `TestConnectionIsWrapped` |
| revert the `execute` salvage | `TestSalvage` |
| drop the fetch-path salvage | `test_a_lazy_error_surfacing_at_fetch_is_salvaged_too` |
| un-pin the read encoding | `TestExtractorReadsUtf8Explicitly` |
| narrow `_build_marts` back to `UnicodeDecodeError` only | `TestBuildMartsSiteStillFires` |
| put a real `0xfc` byte in the incident model | `TestModelSqlEncoding` |

⚠️ **Honest scope — read this before citing the encoding lint.**
`TestModelSqlEncoding` (every model `.sql` decodes as UTF-8) is the file-encoding lint the story
asked for, and it defends a **real, separate** failure: a genuinely non-UTF-8 byte in a model file
*would* crash `extract_duckdb_sql`'s `read_text()` and down a HALT-tier build. **It would NOT have
caught INC-43** — the file was clean. The guards that defend what actually broke are
`TestSalvage` / `TestConnectionIsWrapped`.

`TestModelSqlEncoding` enforces **valid UTF-8**, not ASCII-only: `—`/`²` in a SQL comment are
harmless and this very file has 45 of them. It additionally pins the measured facts that refute the
bad-byte hypothesis (the branch is ASCII; the statement is <5 KB), so a future reader can see the
reasoning is still sound rather than having to re-derive it.

The existing INC-37 guard
(`test_schedule_build_ordering_guard.py::test_build_marts_does_not_destroy_a_non_utf8_error`) was
**re-anchored, not weakened** — it now matches either `except` form and was re-RED-proven.

---

## 7. Follow-ups

* **INC-37's remaining open hypothesis still stands** and is now better supported: memory pressure
  in the shared container stack was the last surviving explanation for the `mart_derivative_closes`
  `UnicodeDecodeError`. INC-43 does not settle it — but the next occurrence of *either* will now
  arrive with the DuckDB text attached, which is what decides it.
* **The 86.9 s glob bind is worth a look on its own.** `**/*.parquet` over the full pitch history
  is a large S3 LIST on every W3 build. Not chased here.
* **`_delete_s3_uri` / boto3 paths are not proxied** — the connection proxy covers DuckDB only.
  `_build_marts` still catches a raw `UnicodeDecodeError` for that reason.
