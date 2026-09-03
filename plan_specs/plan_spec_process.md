# Plan-spec discipline v2 — intake process (2026-08-22)

## The rule
No card enters **To Do** or the **Sprint** without a spec in `plan_specs/`
(full or mini per the template tiering). **Backlog** may hold spec-less
one-liners; promotion out of Backlog is what triggers spec-writing.

## Why the overlap gate is the point
The card explosion happened because worker-session findings became cards
without anyone checking To Do/Backlog or the tried ledgers. The OverlapCheck
block makes that check a precondition of acceptance, with evidence required
(queries actually run). A spec that re-approaches a recorded null must cite
it and state what is new, or it is rejected — same E2.1-r posture as the
model program.

## Routing (who may create what)
- **Worker sessions**: append findings to their spec's `closeout.followUps`.
  Never create cards.
- **PM**: triages follow-ups weekly into checklist-item / merge / new spec.
  Only the PM creates cards, and only from ACCEPTED specs.
- **Operator (Charlie)**: anything, anytime — PM backfills the spec.

## Organization
New specs go under `plan_specs/<vertical>/` (mlb, nfl_fantasy, ncaaf,
platform). The phase_N folders stay as history; don't reorganize them.
Spec filename = card slug. Card description = one paragraph + the spec path
(the spec is the source of truth; the card is a pointer + status).

## Closeout
A spec CLOSES with a verdict (SHIPPED / NULL(class) / REFUSED / PARKED),
mirroring the ablation-record discipline. Closing a spec archives its card.
An IN_PROGRESS spec whose card is archived is a process error — flag it.

## Backfill policy
Do not backfill specs for the existing ~150 Backlog cards. Backfill happens
lazily: when a card is pulled toward To Do, it gets its spec then — including
the overlap check, which is exactly when stale duplicates will surface and
get merged or archived.

## Runtime handoff rule (operator ruling 2026-08-23)
In any modeling story, a command expected to run **longer than ~2 minutes is
not run by the worker session** — it is handed to the operator (Charlie) as a
paste-ready command, with the expected runtime, what artifact it writes, and
what "success" looks like stated alongside it. The session picks back up from
the artifact the operator's run produced. Quick smokes and sub-2-minute
harnesses stay in-session. Kickoff prompts carry this rule in their
DISCIPLINES block; a spec whose plan contains a known long-running node names
it as an OPERATOR-RUN step up front.

## Backend-before-frontend sequencing (operator ruling 2026-08-25)
When a backend/serving story and a frontend story touch the same surface or
contract in the same window, the backend story **completes first** — the
frontend consumes a landed contract, never a moving one, and absorbs any
client-side change the backend story flagged. Kickoff prompts for the
frontend half state the dependency explicitly. Genuinely disjoint stories
(different surfaces, no shared contract) may still run in parallel.

## Spec-premise verification (PM ruling 2026-09-01, from NF-RATE1 follow-up 1)
A spec's factual premises about the codebase (which files own a surface, whether
a deploy path exists, where a column is computed) must be either QUOTED VERBATIM
from the parent record (which carries file:line evidence) or verified against
the running system before the spec is written — never paraphrased from memory.
NF-RATE1's spec asserted a box-image "exporter half" that does not exist; the
parent follow-up had already named rankings-board.tsx:296 as the CSV's owner.
The defect entered at spec-writing time (a PM paraphrase), and the same shape
would send a future session hunting a Python artifact that isn't there. Same
family as the repo's "pre-flight a card's premise against the running system"
rule — applied one step earlier, to the spec itself.

## Pre-registration provenance guards (PM ruling 2026-09-01, from the NF-CSV1/NF-INJ2c cross-story event)
A provenance guard keyed on "the later artifact does not exist yet" is
SELF-EXPIRING: the moment the artifact legitimately lands, the guard fires on
correct work (NF-INJ2c's blind-to-node-3b guard fired against the dev→main gate
21s after an unrelated merge). Key provenance guards on the SUBSTANCE of the
claim instead — e.g. "the prereg quotes no number from the later measurement"
(commit 6547d75c) — which stays true forever if the claim is true. Applies to
every §0.5 pre-registration's blindness/ordering clauses.

## Two §0.5 registration conventions (PM rulings 2026-09-01, from MLB-TV2-2 findings ③ + ⑧)
1. POOLED-CALIBRATION STATISTICS get per-ROW fold series, never per-fold. A
   statistic that is constant within a fold (calibration-in-the-large, a stated
   probability, any pooled quantity) carries ~1 effective observation per fold —
   a per-fold series over it is a sign test wearing a t-test's clothes.
   Generalises to every vertical (NCAAF/prospect totals included).
2. RENDERERS ARE EXERCISED AGAINST REAL PRODUCER OUTPUT before the decisive
   run. TV2-2's 9-minute run completed everything then died in write_report:
   the rehearsal ran with controls=False, so the one section an amendment had
   changed never rendered. A report path rehearsed only on a config that skips
   the changed section is untested where it changed.
