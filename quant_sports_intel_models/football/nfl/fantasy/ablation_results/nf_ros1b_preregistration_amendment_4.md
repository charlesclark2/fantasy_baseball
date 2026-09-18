# NF-ROS1b — amendment 4 (PM acks, 2026-09-18): the serving decisions, recorded

⛔ **THIS AMENDMENT GATES NOTHING AND MOVES NO BAR.** It is written after §13, after the decisive
run, after node 4 was built. It changes no arm, no clause, no threshold and no verdict, and nothing
in it can be read back onto the certification — C1–C9 stand exactly as registered and exactly as
measured. It records three SERVING decisions the PM ruled on, and the reason each one is written
down rather than left to the diff: two of them differ from what an earlier instruction said, and a
future reader must be able to see that the difference was ruled on rather than quietly taken.

The scoring, the interval family, the honesty clause and the RB-rookie rule (amendments 1–3) are
untouched.

---

## 1. R3 is superseded: the publish rides the weekly serving job, not a 09:30 schedule

**What R3 ordered (PM, 2026-09-17):** a separate daily schedule at 09:30 America/Los_Angeles with
`default_status=STOPPED`.

**What was built:** an independent branch of `sports_nfl_weekly_serving_job`, hanging off that job's
stats ingest, deploy-held by a new env flag `NF_ROS_PUBLISH_ENABLED` (default off), with
`nfl_ros_freshness_op` watching the artifact from the Sleeper job.

**Ruled (PM ack, 2026-09-18): APPROVED, and recorded as a supersession rather than a silent
deviation.** The session flagged the difference against R3 before building it (followUp ⑭); the PM
ratified it afterwards on three grounds, each one a house lesson applied:

1. **Ordering by construction, not by clock (INC-25).** The publish reads the `stats_player_week`
   the same run has just refreshed. A 09:30 cron would have ordered it by the wall clock, which is
   the arrangement INC-37 broke.
2. **The deploy-held state is visible (NCAAF-P1.2W / NF-CAP1).** A `default_status=STOPPED`
   schedule cannot be heartbeat-checked — the heartbeat flags only a PERSISTED stopped row, and a
   volume reset leaves none — and E11.23's guard pins critical schedules to RUNNING. The env flag
   holds "merged never means running" instead, and `ARMED_NOT_FIRING` reports it at WARN daily, so
   the off state is a thing you can see rather than a thing nobody mentions.
3. **It fails toward not publishing.** An undeclared flag means no publish, which is the safe
   direction for a paid-substrate artifact.

⇒ R3 as written is **SUPERSEDED**, by ruling, on 2026-09-18. It was not ignored.

---

## 2. The ROS Std/Half values are PAID; the PPR triple stays free

**The question** (raised by the paid-set diff the PM was shown before merge): the artifact's stat
line is classified paid automatically, because `projection_fields.PAID_PLAYER_FIELDS` is DERIVED
from `STAT_FIELD`. But the six per-scoring values `rosPts/rosP10/rosP90` × {Std, Half} came out
**free**, because the other half of that module — `PAID_SCORING_FIELDS` — was a **hand list of two
field names** (`fpStd`, `fpHalf`). Nothing was wrong with the ROS contract; the pricing rule simply
did not reach it.

**Ruled (PM ack, 2026-09-18): ADD them to the paid set. PPR stays free, with its band.** This is
the existing freemium policy applied, not a new boundary — one free format (the PPR number and the
80% range that makes it honest), alternative scoring presets paid — and shipping it the other way
would have meant a user paying for Std/Half on the season board and getting them free one tab over.

**How it was implemented, and why that matters more than the six names.** The ruling is expressed as
a RULE, not six additions:

```
PAID_SCORING_FIELDS = { stem + SCORING_SUFFIX[preset]
                        for stem in SCORED_FIELD_STEMS        # fp, rosPts, rosP10, rosP90
                        for preset in PAID_SCORING_PRESETS }  # standard, half_ppr
```

so a new per-scoring surface prices its formats by declaring one stem, and the same value cannot be
priced differently on two surfaces. `app/backend/models/nfl_ros.py` now imports that suffix map
rather than keeping a second copy of the spelling.

**The finding, recorded for the census family** (followUp ⑯): `PAID_SCORING_FIELDS` was the last
hand list inside the module whose own header explains why hand lists leak — *"a hand-written list is
a DENYLIST; the next field the exporter adds is public by default and leaks on the next publish,
with no code change, no error and no failing test."* It failed in exactly that way on the first new
surface that published a per-scoring value, and the guard pinning it (`PAID_SCORING_FIELDS ==
{"fpStd","fpHalf"}`) held green throughout, because a membership pin cannot see a field nobody
added. The guard now asserts the mechanism first and the membership second.

---

## 3. §13 finding ⑪ rides the artifact

**Ruled (PM ack, 2026-09-18):** the upper-tail observation goes into the served manifest, not only
into the record, and WVR1 inherits it when it renders the value column.

`NflRosManifest.upper_tail_note` now carries it: 9 of 197 certified RB rows (the top backs) hold a
P90 above the largest realized per-game pace on record scaled to games remaining (widest: 664
against 482); no point estimate does; this is the registered ratio table's top cell spreading
upward, consistent with RB's measured over-coverage (0.859 against a nominal 0.80); it is
**deliberately not clamped**, because clamping would change the interval family the certification
was earned under. A consumer is told to render the upper edge as a tail, never as a ceiling.

---

## 4. Ack 1 is NOT recorded here

The RB-rookie C9 reading is governed by **amendment 3**, whose rule was fixed before the number
exists, and the PM's 2026-09-18 ack confirms that rule stands unchanged — including how a reading
above 0.05 will be judged against amendment 3's dependence range (≈0.00 false-positive under row
independence, ≈0.51 under full within-player clustering). Nothing in this amendment touches it. The
read is an operator run; its number and its disposition are appended to §13 when it exists.
