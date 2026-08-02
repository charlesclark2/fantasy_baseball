# INC-39 — a CRITICAL W11-tail page on a healthy slate (2026-08-02)

**Severity:** P2. No serving impact. `check_w11_tail_coverage_op` is ALERT-tier and never HALTs;
predict fanned out and the slate served normally.

**Verdict: FALSE POSITIVE.** `feature_pregame_public_betting_features` held **15/15** slate games
for 2026-08-02. There was no build gap.

---

## The page

```
W11 SERVING TAIL (INC-37): BUILD GAP: public_betting BUILD_GAP 0/15 slate games
on SMOKE-TEST. ... A BUILD GAP means the raw feed HAS the slate and the built table
does not ... on the 1st of a month, suspect the INC-37 month-boundary schedule hole ...
```

This was the first CRITICAL from the op since INC-37 wired it.

## Ground truth (gathered OUTSIDE the op, before touching any code)

`scripts/check_w11_tail_coverage.py`, run on the laptop against the live lakehouse
(SF-free DuckDB/S3, `AWS_DEFAULT_REGION=us-east-2`):

| slate | umpire | weather | public_betting |
|---|---|---|---|
| 2026-08-02 | 0/15 BUILD_GAP | 0/15 BUILD_GAP | **15/15 OK** |
| 2026-08-01 | 15/15 OK | 14/14 OK | 15/15 OK |

umpire/weather gapping on the *current* slate is the designed one-build-cycle lag (their feeds
land after `lakehouse_w11_nightly_op`), which is exactly why the policy judges them on the prior
slate. Feeding both real outputs through the real `classify`:

```
SEVERITY: None
MSG: W11 serving tail OK — every block covers the newest slate its build could have reached
```

**The daily op's real path over the real data does not page.** The CRITICAL did not come from it.

## What actually went wrong

The string `SMOKE-TEST` exists nowhere in the repo — no branch, no history — and `main` is
identical to `dev` on every file in this chain, so there is no deploy skew. It occupies the slot
`classify(..., today_date=...)` fills from `_today()`, which returns an ISO date. The page was
therefore produced by an out-of-band invocation (the shape of the E11.30-mandated live-box smoke
that INC-37 left open), calling `send_alert` with the **production severity, subject and
`dedup_key`**.

Two defects made that indistinguishable from a real incident, and one of them is worse than the
false page:

1. **A smoke page looked exactly like a real page.** Same `[Credence PROD]` subject, same
   `CRITICAL`, same body. The only tell was a non-date buried mid-sentence.
2. **A smoke consumed the production dedup slot.** `send_alert` rate-limits per `dedup_key` for
   **1 hour**, so a smoke on `w11_tail_coverage` *suppresses the genuine page for the next hour* —
   smoke-testing a monitor could blind it precisely while someone is poking at the box. This
   affects all 66 `send_alert` call sites, not just this one.
3. **Nothing downstream could tell which slate the numbers described.** The per-block `[METRIC]`
   lines carried no date, so replayed / stale / synthetic output parsed byte-identically to a live
   read of the requested slate.

## Fixes

- **`scripts/check_w11_tail_coverage.py`** — emits `[METRIC] w11_tail_date=<ISO>` on *every* exit
  path (including the read-failure path, so the cross-check below can never be vacuously satisfied
  by an absent line — NF1.7 (a)).
- **`betting_ml/monitoring/w11_tail_coverage.py`** — `parse_date()`; `classify` demotes a leg whose
  reported slate disagrees with the requested one to **UNVERIFIED (WARN)** — never CRITICAL, never
  healthy. Inert when the caller passes a prose label rather than a date, and inert when the line is
  absent, so it can only ever *add* a refusal on positive evidence of a wrong slate.
- **`pipeline/utils/alerting.py`** — `send_alert(..., smoke=True)`: `[SMOKE TEST]` leads the
  subject, a banner leads the body, and the dedup key is namespaced `smoke:` so a self-test can
  never occupy a real alert's slot. Deliberately a **keyword argument with no env-var backdoor**: a
  left-set `ALERT_SMOKE_TEST=1` would label every real page a smoke, which is the mirror-image
  failure and strictly worse (this repo's documented-but-never-set flag class, cf.
  `W7B_LAKEHOUSE_S3`). Pinned by a test.

The two-runs-one-per-slate cadence (public_betting → TODAY, umpire/weather → PRIOR) is unchanged.

## The guard gap this exposed

The op was covered from both ends and still shipped an unexercised middle. `test_w11_tail_coverage.py`
tested the script's classifier; `test_w11_tail_coverage_alerting.py` tested the paging policy;
`test_check_ops_alerting_execution.py` executed the op — **with `_run_script` monkeypatched away**.
Every assertion ran against a stdout string a *test author* wrote, so the suite would have stayed
green if the script's print format and the monitor's regex had drifted apart.

`betting_ml/tests/test_inc39_w11_tail_daily_invocation.py` exercises the real chain: the real
script's `main()` (only its lakehouse read stubbed) → its real stdout → the real parsers → the real
`classify` → the real `_run_script` subprocess → the real op in a Dagster job. Only S3/DuckDB and
SNS are stubbed, so the fast gate stays hermetic.

Per INC-38, every guard was proven able to **FAIL** before being trusted:

| deliberate break | result |
|---|---|
| script stops stamping the slate | 3 RED |
| `classify` stops refusing a wrong-slate leg | 2 RED |
| smoke reuses the production dedup key | 2 RED |
| op drops its INC-32 subprocess timeout | 1 RED |

Two of these tests initially passed **for the wrong reason**: `_run_script` runs with `cwd=/app`
(the box layout), so off-box every subprocess died before exec and the op reported UNVERIFIED/WARN
— which is what one test was asserting. The silent-slate test now also asserts both legs really ran
and parsed (`parse_date`, `parse_evaluated`), so "the op stayed quiet" can never be satisfied by
"the subprocess never started".

## Generalisable lesson

> **A smoke test of an ALERT-tier monitor must be structurally distinguishable from a real page and
> must never occupy the real page's dedup slot.** E11.30 mandates a live-box smoke for every such
> monitor, and `send_alert` rate-limits per `dedup_key` for an hour — so an unlabelled smoke both
> costs an incident response and *silently suppresses the genuine page* for the next hour. Related:
> a monitor that parses a subprocess's metrics must be able to verify **which slate those metrics
> describe** — replayed, stale or synthetic output parses identically to a live read, and numbers
> that are individually real can still be about the wrong day.
