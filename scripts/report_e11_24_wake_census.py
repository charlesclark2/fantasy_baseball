#!/usr/bin/env python3
"""
scripts/report_e11_24_wake_census.py   (E11.24 — the per-BAND wake instrument)

The measurement E11.24 runs before and after every lever flip. Read-only against
`snowflake.account_usage`, on **MONITOR_WH** so the audit is never a line in its own
results (the self-inflicted-wake cure, target 3).

Run on the LAPTOP (that is where the Snowflake key lives):

    uv run python scripts/report_e11_24_wake_census.py
    uv run python scripts/report_e11_24_wake_census.py --days 12

⭐ WHY PER BAND, NOT PER DAY (docs/e11_24_literal_zero_snowflake.md "ATTRIBUTION CORRECTION"):
lever **1b** (the statcast catch-up no-op gate, flipped 2026-07-31 ~19:45 UTC) and lever
**6a** (the per-slate umpire idempotency gate) both reduce umpire-chain waits, but in
DISJOINT UTC hour bands — 1b owns 08-13 (the catch-up re-fire window), 6a owns 14-23 (the
10-min lineup-monitor tick). Crediting a whole-day delta to either double-counts the other.
So every table here is cut by band.

📐 THREE INSTRUMENTS, and the reason each is here (E11.20-COST + the 7/31 re-census):
  1. RESUMES        — `warehouse_events_history`. The bursty-lever signal. 6a is bursty ⇒
                      expect it HERE.
  2. ACTIVE MINUTES — distinct minutes containing ≥1 **warehouse-occupying** query. The
                      24/7-POLLER signal: a lever that deletes an evenly-spread poller
                      (weather) deletes awake-TIME while resumes stay flat. Report both or
                      you under-credit exactly the levers this story is built on.
     ⭐ `warehouse_size IS NOT NULL` IS REQUIRED (#679, applied 2026-08-10). A statement
     billed to CLOUD SERVICES can neither RESUME the warehouse nor KEEP it awake — `SHOW`,
     `ALTER SESSION`, `ALTER EXTERNAL TABLE … REFRESH`, `CALL SYSTEM$…`, and **every
     `CREATE OR REPLACE VIEW`** — yet unfiltered they were 40–138% of the figure, once
     ranking a Snowsight browser poll as the account's largest awake-time consumer (a
     phantom that would send a fix session at nothing). This matters MORE after #675/#662:
     those flips replace MERGE/CTAS statements with `create or replace view`, so an
     uncorrected reading would keep counting the very minutes the flip stopped billing for.
     ⚠️ Do NOT apply it to the WAIT tables — a provisioning wait implies a real occupation,
     so waits are immune (and filtering them would drop true wakers).
  3. PROVISIONING WAITS — `query_history.queued_provisioning_time > 0`. The ATTRIBUTION
                      instrument: a query only queues on provisioning if it waited for the
                      warehouse to start, so it names the waker directly (3.7% unclassified
                      vs 53% for the "first query at/after the resume" heuristic the earlier
                      censuses used).
  ⛔ NOT sum-of-elapsed-seconds — it moved the WRONG way across a real 16% awake-time cut.

⚠️ A SHAPE GOING TO ZERO IS ALSO WHAT A DEAD JOB LOOKS LIKE. Every per-shape table below
reports TOTAL EXECUTIONS beside the waits, so "the lever fired" is separable from "the
caller stopped".

⚠️ BASELINE HYGIENE: 2026-07-29 and 2026-07-31 are CONTAMINATED (the census's own audit
queries + two `--reset` backfills, run as `DBT_RW` so they cannot be filtered by user).
Use 7/28 and 7/30 as pre-flip references. `account_usage` lags ~45 min (query_history) to
~2-3 h (events), so today's last band is always partial — the footer prints the lag.
"""
from __future__ import annotations

import argparse
import math

# UTC hour bands. 1b (statcast catch-up re-fire) and 6a (lineup-monitor tick) are separable
# because they live in disjoint bands; see the attribution correction in the E11.24 doc.
BAND_CASE = """
      case when hour(start_time) between 8 and 13 then '08-13 (1b catchup)'
           when hour(start_time) between 14 and 23 then '14-23 (6a tick)'
           else '00-07 (overnight)' end
"""

# Classify a waker by the table it READS, never by the job it belongs to (the 7/29 lesson:
# compute_elo's waker is its READ of mart_game_results, and the weather slate query never
# contains the string "weather" — it joins ref_venues).
#
# ⚠️ CLASSIFY OVER THE SAME 400-CHAR WINDOW EVERYWHERE. Every caller must apply this CASE to
# `left(regexp_replace(query_text,'\s+',' '), 400)`. Truncating shorter before classifying
# silently dumps statements into 'other': an ad-hoc 110-char attribution on 2026-08-03 put all
# 30 weather-slate waits into 'other' because `ref_venues` sits past char 110 — i.e. the
# instrument invented a phantom 'other' waker and hid a real family. (Caught by cross-checking
# the two totals; they must agree.)
#
# 2026-08-03 — three families added after a statement-level attribution of the 'other' mass:
#   · 'CI on the prod WH'  — FIRST on purpose. `ci_betting*` builds are CI hitting the PROD
#     warehouse (4 overnight waits on `ci_betting_features.feature_pregame_injury_status`).
#     Matched first so a CI build of a prod-named model is never counted as a prod waker —
#     conflating them would send a fix session at the wrong caller.
#   · '8 model-health/pred_log' — compute_model_health.py + backfill_prediction_log.py.
#     ⚠️ POST-E11.24-P1 THIS FAMILY SHOULD READ ~0 — prediction_log left Snowflake, so its
#     DELETE/UPDATE/SELECT statements no longer exist. A zero here is the EXPECTED cutover
#     state, NOT a dead job — and read it PER-DAY, never off an aggregate straddling the
#     flip date (that measures residue). The one statement that SURVIVES the migration is
#     the `model_health_log` INSERT, which does not mention prediction_log and therefore
#     lands in a different bucket.
#   · '4b scd2 signal writers' now also matches `tmp_%incoming%`: scd2_writer's default temp
#     table is `tmp_scd2_incoming`, but the signal generators pass CUSTOM names
#     (`tmp_starter_ip_signals_incoming`), so the old literal pattern missed per-row INSERTs
#     that were waking the warehouse OVERNIGHT.
# These shift Table 4/4b family totals vs earlier runs — deliberately, they are corrections.
#
# 2026-08-06 — READING 'lineup_monitor audit INSERT' AFTER E11.24. The audit sink moved to
# DynamoDB, so post-flip this family should read 0 executions / 0 waits.
# MEASURED PRE-MERGE BASELINE (--days 12, run 2026-08-06 14:41 UTC): ALL 86 waits sit in the
# 14-23 band — ZERO in 00-07, ZERO in 08-13. And a live SHOW TASKS IN ACCOUNT (2026-08-06)
# showed the legacy Snowflake task DAG is a single chain rooted at TASK_SAVANT_INGESTION,
# USER_SUSPENDED since 2026-04-30 (its four downstream tasks read 'started' but are
# predecessor-driven with no schedule, so they cannot fire) ⇒ those procs are NOT writing
# pipeline_run_log either. The family is 100% the lineup monitor. ⇒ the expected post-flip
# reading is a HARD zero, and ANY non-zero is a finding, not proc residue.
#
# ⚠️ SELF-MATCH: this script's own FAMILY_CASE contains the literal '%pipeline_run_log%', so
# every census run is itself a query whose TEXT matches that pattern. A grep of query_history
# for 'pipeline_run_log' therefore returns THIS INSTRUMENT (and report_sf_cost_flips_after.py)
# as apparent readers. To find a genuine reader, match `from ...pipeline_run_log`, never a bare
# mention of the string.
# ⚠️ AND THE STANDING WARNING BINDS UNUSUALLY HARD HERE: silence is the INTENDED outcome, so
# in this instrument "the lever landed" and "the monitor died" are indistinguishable BY
# CONSTRUCTION — there is no executions-hold/waits-fall signature to read, because executions
# go to zero too. Confirm the monitor is ALIVE from the DynamoDB audit log instead (the
# runbook query in scripts/daily_run.md), never from this family's silence.
#
# ⛔ Do NOT add explanatory comments INSIDE the FAMILY_CASE string below — it is SQL sent to
# Snowflake, where `#` is not a comment (this was caught in review 2026-08-06). Comment here.
FAMILY_CASE = """
      case
        when q ilike '%ci_betting%'                          then 'CI on the prod WH'
        when q ilike '%prediction_log%'                       then '8 model-health/pred_log'
        when q ilike '%tmp_%incoming%'                        then '4b scd2 signal writers'
        when q ilike '%umpire%'                              then '6a umpire chain'
        when q ilike '%int_bullpen_ali%'                     then '1b int_bullpen_ali'
        when q ilike '%mart_game_results%'                   then '1b/1 compute_elo read'
        when q ilike '%feature_pregame_lineup_features%'
          or q ilike '%feature_pregame_starter_features%'    then '6 lineup/starter CTAS'
        when q ilike '%stg_statsapi_lineups_wide%'
          or q ilike '%stg_statsapi_probable_pitchers%'      then '6 tick CTAS (dead 7/25)'
        when q ilike '%player_sequential_posteriors%'        then '4 player posteriors'
        when q ilike '%team_sequential_posteriors%'          then '4 team posteriors'
        when q ilike '%matchup_cell_sequential_posteriors%'  then '4 matchup posteriors'
        when q ilike '%mart_sub_model_signals%'
          or q ilike '%tmp_scd2_incoming%'                   then '4b scd2 signal writers'
        when q ilike '%feature_pregame_sub_model_signals%'   then '4b signals consumer'
        when q ilike '%pipeline_run_log%'                    then 'lineup_monitor audit INSERT'
        when q ilike '%ref_venues%'                          then '2 weather slate'
        when q ilike '%metering%' or q ilike '%account_usage%' then '3 metering/audit'
        else 'other'
      end
"""


# ── GATE-0 v2: build-day-aware structural normality (re-derived 2026-08-12) ──────────────
# WHY v2. Gate-0 v1 was a fixed band on TOTAL executions ("a normal day sits in 1,536–3,480").
# On the 08-12 soak read it FAILED (1,434) on a day whose every per-family count was normal, and
# it is confounded TWICE:
#   1. BUILD-DAY BIMODALITY. `other` runs ~1,043–1,182 on non-build days and ~2,615–2,889 on
#      build days, so one band is really two populations and the low one straddles the floor.
#   2. ⭐ THE LEVERS THEMSELVES LOWER IT. Every E11.24 lever DELETES statements, so total
#      executions fall as the story succeeds — a floor derived pre-flip gets harder to clear the
#      better the work goes. A gate that fires because the fix worked is not a gate.
#
# v2 therefore splits the two jobs a gate-0 was doing:
#   · CLASSIFY the day (build vs non-build) from a DERIVED indicator, not the calendar;
#   · PASS/FAIL on a HEARTBEAT — families that fire once per daily run and that no pending lever
#     targets — which is immune to both confounds. Volume is reported as CONTEXT, never as the
#     verdict.
#
# THE INDICATOR IS DERIVED, AND SELF-VALIDATING. `2 weather slate` is absent entirely on
# non-build days; `4b signals consumer` independently reads ~33 on build days vs 2 otherwise.
# Over 2026-08-03..12 the two agreed on exactly the same four days (08-05, 08-08, 08-09, 08-11).
# That agreement IS the evidence the partition is real — so when they DISAGREE the day is
# UNKNOWN and the verdict is UNVERIFIED, never a pass (NF1.7(a): a check that could not be
# evaluated is not a check that passed).
BUILD_INDICATOR = "2 weather slate"          # absent on non-build days
BUILD_CROSSCHECK = "4b signals consumer"     # ~33 on build days, 2 otherwise
BUILD_CROSSCHECK_MIN = 10

# Fire once per daily run; NOT targeted by any pending lever, so a change here is a real
# pipeline anomaly rather than a lever landing. ⛔ Do NOT add a family a lever touches — the
# whole point is that a working lever must not trip the normality gate.
HEARTBEAT_FAMILIES = ("4 matchup posteriors", "4 player posteriors")

# "at least half the expected daily invocations". A DESIGN quantity (an outage suppresses runs
# wholesale; it does not shave one off), NOT a level tuned until the days we like pass.
HEARTBEAT_FLOOR_FRAC = 0.5

# Days excluded from the reference: their own incidents perturbed the pipeline.
CONTAMINATED_DAYS = ("2026-07-29", "2026-07-31", "2026-08-11")  # 08-11 = the INC-42 freeze


def classify_gate0(rows, *, contaminated=CONTAMINATED_DAYS):
    """PURE. [(day, family, execs)] → per-day {class, executions, heartbeat, verdict}.

    verdict is one of PASS / FAIL / UNVERIFIED. UNVERIFIED whenever the day cannot be
    classified or a heartbeat family is ABSENT — an absent heartbeat is the signature of the
    outage this gate exists to catch, so it must never read as healthy.
    """
    days = sorted({r[0] for r in rows})
    by_day = {d: {r[1]: r[2] for r in rows if r[0] == d} for d in days}
    total = {d: sum(by_day[d].values()) for d in days}

    def day_class(d):
        fams = by_day[d]
        ind = fams.get(BUILD_INDICATOR, 0) > 0
        cross = fams.get(BUILD_CROSSCHECK, 0) >= BUILD_CROSSCHECK_MIN
        if ind != cross:
            return "UNKNOWN"
        return "BUILD" if ind else "NON-BUILD"

    classes = {d: day_class(d) for d in days}

    # ⭐ LEAVE-ONE-OUT. The reference for judging day D is built from every OTHER uncontaminated
    # day of D's class — never from D itself. The first cut included D, which made the check
    # partly self-satisfying: a day whose heartbeat had collapsed to 3 simply became the new
    # minimum and passed. (Caught by its own unit test, not by inspection. Same family as "a
    # guard both sides filter into satisfaction".)
    ref_days = [d for d in days if str(d) not in contaminated and classes[d] != "UNKNOWN"]

    def reference(cls, exclude):
        cds = [d for d in ref_days if classes[d] == cls and d != exclude]
        if not cds:
            return None, {}
        vol = (min(total[d] for d in cds), max(total[d] for d in cds))
        rng = {}
        for fam in HEARTBEAT_FAMILIES:
            vals = sorted(by_day[d][fam] for d in cds if fam in by_day[d])
            if vals:
                rng[fam] = vals[len(vals) // 2]      # peer MEDIAN
        return vol, rng

    out = []
    for d in days:
        cls, hb, notes = classes[d], {}, []
        verdict = "PASS"
        if cls == "UNKNOWN":
            verdict = "UNVERIFIED"
            notes.append(f"{BUILD_INDICATOR} and {BUILD_CROSSCHECK} disagree — cannot classify")
        vol, ranges = reference(cls, d)
        for fam in HEARTBEAT_FAMILIES:
            got = by_day[d].get(fam)
            hb[fam] = got
            if got is None:
                verdict = "UNVERIFIED"          # absent ≠ healthy
                notes.append(f"{fam} ABSENT")
                continue
            med = ranges.get(fam)
            if med is None:
                verdict = "UNVERIFIED"          # no peers to compare against ≠ healthy
                notes.append(f"{fam}: no uncontaminated {cls} peer day to compare against")
                continue
            # ⭐ ONE-SIDED FLOOR, not a two-sided range. The gate's job is "did the daily
            # pipeline RUN", and an outage suppresses invocations — it does not add them, so a
            # count ABOVE the peers is a catch-up, never an outage. A two-sided min/max over
            # 2-5 peers also has no tolerance at all: the first cut FAILED 08-04 on a single
            # extra invocation (player 10 vs a (11,11) range), which is the alert-fatigue mode
            # that gets a monitor ignored. HEARTBEAT_FLOOR_FRAC is a DESIGN quantity — "at
            # least half the expected daily invocations" — not a threshold tuned until the
            # days we like pass.
            floor = math.ceil(HEARTBEAT_FLOOR_FRAC * med)
            if got < floor:
                if verdict != "UNVERIFIED":
                    verdict = "FAIL"
                notes.append(f"{fam}={got} below floor {floor} (peer median {med})")
        out.append({
            "day": d, "class": cls, "executions": total[d], "heartbeat": hb,
            "volume_band": vol, "verdict": verdict,
            "contaminated": str(d) in contaminated, "notes": notes,
        })
    return out


def render_gate0(rows):
    print(f"\n{'=' * 100}\n0. GATE-0 v2 — structural normality (build-day aware)\n{'=' * 100}")
    print("  ⭐ The VERDICT is the HEARTBEAT, not the volume. Executions fall as levers land, so a\n"
          "     fixed volume floor fires because the work SUCCEEDED — it is reported as context only.\n"
          "  ⛔ UNVERIFIED is not a pass: an absent heartbeat family is the outage signature itself.\n")
    hdr = f"{'UTC_DAY':12}{'CLASS':11}{'EXECS':>7}  {'VOL BAND (context)':>20}  "
    hdr += "".join(f"{f.split()[-1][:9]:>10}" for f in HEARTBEAT_FAMILIES) + "  VERDICT"
    print(hdr)
    for r in rows:
        band = f"{r['volume_band'][0]}-{r['volume_band'][1]}" if r["volume_band"] else "n/a"
        line = f"{str(r['day']):12}{r['class']:11}{r['executions']:>7}  {band:>20}  "
        line += "".join(f"{('-' if r['heartbeat'][f] is None else r['heartbeat'][f]):>10}"
                        for f in HEARTBEAT_FAMILIES)
        line += f"  {r['verdict']}"
        if r["contaminated"]:
            line += "  (contaminated — excluded from the reference)"
        if r["notes"]:
            line += "  ⚠️ " + "; ".join(r["notes"])
        print(line)
    return rows


def pivot_family_by_day(rows):
    """PURE. [(family, utc_day, execs, waits)] → (families, days, {(fam, day): 'execs/waits'}).

    Split out from the renderer so the shaping is unit-testable without a warehouse.
    """
    families = sorted({r[0] for r in rows})
    days = sorted({r[1] for r in rows})
    cells = {(r[0], r[1]): f"{r[2]}/{r[3]}" for r in rows}
    return families, days, cells


def run_pivot(cur, title, sql, note=None, label_width=30):
    """Render a (family, utc_day, execs, waits) result as a family × day MATRIX.

    A matrix rather than the generic long format because the whole point of this cut is reading
    a TREND across days per family — precisely what the aggregate structurally cannot show.
    """
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    if note:
        print(f"  {note}\n")
    cur.execute(sql)
    rows = cur.fetchall()
    if not rows:
        print("(no rows)")
        return rows
    families, days, cells = pivot_family_by_day(rows)
    colw = max(11, max(len(str(d)) for d in days) - 4)
    print("family".ljust(label_width) + "".join(str(d)[5:].rjust(colw) for d in days))
    for fam in families:
        print(fam[:label_width - 1].ljust(label_width)
              + "".join(cells.get((fam, d), "·").rjust(colw) for d in days))
    return rows


def run(cur, title, sql, note=None):
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    if note:
        print(f"  {note}\n")
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    widths = [
        max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
        for i, c in enumerate(cols)
    ]
    print("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    if not rows:
        print("(no rows)")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=10, help="lookback window (default 10)")
    ap.add_argument("--warehouse", default="COMPUTE_WH", help="warehouse under measurement")
    args = ap.parse_args()
    d, wh = args.days, args.warehouse

    from betting_ml.utils.data_loader import get_monitoring_connection

    conn = get_monitoring_connection()
    cur = conn.cursor()
    # Everything below is reported in UTC. ⚠️ `warehouse_events_history.timestamp` is
    # TIMESTAMP_LTZ: a `>= 'YYYY-MM-DD'` string boundary would prune in the SESSION tz and
    # cut ~7h off the first day (the LTZ boundary-day landmine). Two defences: the session is
    # pinned to UTC, and every filter is a `dateadd` on a timestamp, never a date string.
    cur.execute("alter session set timezone='UTC'")
    # INC-32 — a finite bound on every statement. This is read-only reporting, but an unbounded
    # census query holds a MONITOR_WH session open indefinitely if account_usage is slow, and the
    # per-day cut below scans query_history UNFILTERED by wait (it needs the executions
    # denominator), which is the heaviest read here. Fail loudly rather than hang.
    cur.execute("alter session set STATEMENT_TIMEOUT_IN_SECONDS=600")

    # GATE-0 v2 runs FIRST: every table below is uninterpretable on a structurally abnormal day
    # (the 1b lesson — an outage collapses every volume metric and fakes a lever's success).
    cur.execute(f"""
        select to_char(convert_timezone('UTC', start_time)::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               {FAMILY_CASE} as family,
               count(*) as execs
        from (
          select start_time, left(regexp_replace(query_text, '\\\\s+', ' '), 400) as q
          from snowflake.account_usage.query_history
          where warehouse_name = '{wh}'
            and start_time >= dateadd(day, -{d}, current_timestamp())
        )
        group by 1, 2""")
    render_gate0(classify_gate0(cur.fetchall()))

    run(cur, f"1. RESUMES/day — {wh} (the BURSTY-lever signal; 6a should land here)", f"""
        select to_char(timestamp::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               count(*) as resumes
        from snowflake.account_usage.warehouse_events_history
        where event_name = 'RESUME_WAREHOUSE' and event_state = 'STARTED'
          and warehouse_name = '{wh}'
          and timestamp >= dateadd(day, -{d}, current_timestamp())
        group by 1 order by 1""",
        note="event_state='STARTED' is REQUIRED — RESUME_WAREHOUSE and RESUME_CLUSTER are "
             "separate rows and an unfiltered count roughly doubles.")

    run(cur, f"2. ACTIVE MINUTES/day — {wh} (the 24/7-POLLER signal; ref 7/28=167, 7/30=141)", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               count(distinct iff(warehouse_size is not null,
                                  date_trunc('minute', start_time), null)) as active_min,
               count(distinct date_trunc('minute', start_time)) as active_min_raw,
               count(*) as executions
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
        group by 1 order by 1""",
        note="`executions` is the DEAD-JOB cross-check: active-min falling while executions "
             "hold = a lever; both collapsing = the caller stopped. "
             "⭐ ACTIVE_MIN is the BILLABLE cut (warehouse_size IS NOT NULL); ACTIVE_MIN_RAW is "
             "the legacy polluted figure, kept only so pre-2026-08-10 readings stay comparable — "
             "quote ACTIVE_MIN.")

    run(cur, f"3. PROVISIONING WAITS by day × BAND — {wh}  ⬅ THE HEADLINE", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               {BAND_CASE} as band,
               count(*) as waits,
               round(avg(queued_provisioning_time)/1000, 1) as avg_wait_s
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}' and queued_provisioning_time > 0
          and start_time >= dateadd(day, -{d}, current_timestamp())
        group by 1, 2 order by 1, 2""",
        note="1b owns 08-13, 6a owns 14-23. A whole-day delta double-counts; read the band.")

    run(cur, f"4. PROVISIONING WAITS by BAND × FAMILY — {wh} (who is left, and where)", f"""
        with h as (
          select {BAND_CASE} as band,
                 left(regexp_replace(query_text, '\\\\s+', ' '), 400) as q
          from snowflake.account_usage.query_history
          where warehouse_name = '{wh}' and queued_provisioning_time > 0
            and start_time >= dateadd(day, -{d}, current_timestamp())
        )
        select band, {FAMILY_CASE} as family, count(*) as waits
        from h group by 1, 2 having count(*) > 0 order by 1, 3 desc""",
        note="Classified by the table READ, not the owning job.")

    run_pivot(cur, f"4b. PER-DAY × FAMILY — {wh}  ⬅ THE LEVER-VERDICT CUT (execs/waits)", f"""
        with h as (
          select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
                 iff(queued_provisioning_time > 0, 1, 0) as is_wait,
                 left(regexp_replace(query_text, '\\\\s+', ' '), 400) as q
          from snowflake.account_usage.query_history
          where warehouse_name = '{wh}'
            and start_time >= dateadd(day, -{d}, current_timestamp())
        ),
        f as (select utc_day, {FAMILY_CASE} as family, is_wait from h)
        select family, utc_day, count(*) as execs, sum(is_wait) as waits
        from f group by 1, 2 order by 1, 2""",
        note=("Each cell is EXECUTIONS/WAITS for that family on that UTC day.\n"
              "  ⭐ HOW TO READ A LEVER (this is the cut Table 4 structurally cannot give you):\n"
              "     · executions HOLD while waits → 0 after a date  = THE GATE FIRED. The lever is\n"
              "       already dead; any waits still in Table 4's total are PRE-FLIP RESIDUE, not work.\n"
              "     · executions AND waits BOTH collapse              = the CALLER STOPPED (a dead job\n"
              "       or an outage), NOT a lever — do not take credit for it (the 1b lesson).\n"
              "     · executions hold AND waits hold                  = STILL FIRING. A real waker.\n"
              "  ⚠️ Table 4 sums a family over the WHOLE window, so a lever flipped mid-window still\n"
              "  shows a big total. That is exactly how the tick CTAS was mislabelled 'dead 7/25'\n"
              "  while being the top waking statement in the account — read THIS table, not that one."),
        label_width=30)

    run(cur, "5. LEVER 1b VERIFICATION — the two 08-13 shapes, waits AND executions", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               case when regexp_replace(query_text,'\\\\s+',' ') ilike '%int_bullpen_ali%'
                      then 'int_bullpen_ali'
                    when regexp_replace(query_text,'\\\\s+',' ') ilike '%mart_game_results%'
                      then 'compute_elo read'
                    else 'umpire (catchup chain)' end as shape,
               count(*) as executions,
               sum(iff(queued_provisioning_time > 0, 1, 0)) as waits
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
          and hour(start_time) between 8 and 13
          and (regexp_replace(query_text,'\\\\s+',' ') ilike '%int_bullpen_ali%'
            or regexp_replace(query_text,'\\\\s+',' ') ilike '%mart_game_results%'
            or regexp_replace(query_text,'\\\\s+',' ') ilike '%umpire%')
        group by 1, 2 order by 1, 2""",
        note="Pre-flip 1b: int_bullpen_ali ran ~10x/hr through 08-13. EXECUTIONS going to ~0 "
             "with the daily job still running = the gate fired; the waits column is the credit.")

    run(cur, "6. LEVER 6a PRE-FLIP REFERENCE — umpire chain by day × band, waits AND executions", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               {BAND_CASE} as band,
               count(*) as executions,
               sum(iff(queued_provisioning_time > 0, 1, 0)) as waits
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
          and regexp_replace(query_text, '\\\\s+', ' ') ilike '%umpire%'
        group by 1, 2 order by 1, 2""",
        note="6a gates ONLY the 14-23 band (the intraday tick). The 08-13 slice belongs to 1b "
             "and the once-daily UNGATED rebuild — it must NOT go to zero.")

    rows = run(cur, "7. account_usage LATENCY (how partial is today?)", f"""
        select 'query_history' as view,
               to_char(max(start_time)::timestamp_ntz, 'YYYY-MM-DD HH24:MI') as latest_utc,
               datediff('minute', max(start_time), current_timestamp()) as lag_min
        from snowflake.account_usage.query_history
        where start_time >= dateadd(day, -2, current_timestamp())
        union all
        select 'warehouse_events_history',
               to_char(max(timestamp)::timestamp_ntz, 'YYYY-MM-DD HH24:MI'),
               datediff('minute', max(timestamp), current_timestamp())
        from snowflake.account_usage.warehouse_events_history
        where timestamp >= dateadd(day, -2, current_timestamp())""")

    print(f"\n{'=' * 100}\nREAD IT LIKE THIS\n{'=' * 100}")
    print("  · Compare BANDS across days, never whole days (1b and 6a both cut umpire waits).")
    print("  · 7/29 and 7/31 are CONTAMINATED baselines (own audit queries + --reset backfills).")
    print("  · A shape at zero is only a lever if EXECUTIONS held up elsewhere; else it's a dead job.")
    print("  · Wake↓ does NOT imply credit↓ — the credit line only moves once the warehouse")
    print("    actually stays suspended for long stretches (the E11.20-COST lesson).")
    print(f"  · Today's trailing band is partial by the lag printed above ({rows and 'see table 7'}).")
    conn.close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
