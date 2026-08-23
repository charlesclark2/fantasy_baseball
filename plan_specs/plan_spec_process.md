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
