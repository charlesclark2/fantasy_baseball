"use client"

// NCAAF-P3.3 — the shared shell for a block that has nothing to show, and WHY.
//
// ⭐⭐ THIS COMPONENT IS THE PAGE'S CENTRAL HONESTY CLAIM, RENDERED.
//
// The payload assembles from four independently-available sources, and on a September Saturday a
// CORRECT page has a rating, a schedule, and two blocks that are structurally empty because nobody
// has played yet. Rendering that identically to "our mart build failed" is the NF-C6b / NF-K1
// defect that cost the same D/ST symptom two separate investigations — so the server carries a
// machine-readable `reason` precisely so a surface can say WHICH absence this is, and collapsing
// them at the last hop would throw that away.
//
// ⛔ AND A REASON WE HAVE NO SENTENCE FOR STILL GETS ONE. A new `reason` rendering as a BLANK is the
// exact failure the field exists to prevent, so the fallback is not optional decoration — it is
// what makes the contract's extensibility safe, and it is RED-proven.

import { BLOCK_REASON_COPY, BLOCK_REASON_FALLBACK } from "@/lib/ncaaf-copy"

export function TeamBlockAbsence({
  testId,
  label,
  reason,
}: {
  testId: string
  label: string
  reason: string | null
}) {
  return (
    <section data-testid={testId} data-block-status="unavailable" data-block-reason={reason ?? ""}>
      <h2 className="text-sm font-semibold text-white">{label}</h2>
      <p
        data-testid={`${testId}-absent-reason`}
        className="mt-2 max-w-2xl rounded-md border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500"
      >
        {(reason && BLOCK_REASON_COPY[reason]) || BLOCK_REASON_FALLBACK}
      </p>
    </section>
  )
}

/** A labelled figure inside a block. ⛔ `null` renders an em-dash, NEVER a zero: a fabricated 0.0
 *  is a wrong number wearing the costume of a measurement, which on a page of small numbers is
 *  indistinguishable from a real one. */
export function TeamStat({
  testId,
  label,
  value,
  sub,
}: {
  testId: string
  label: string
  value: string | null
  sub?: string | null
}) {
  return (
    <div
      data-testid={testId}
      data-has-value={value !== null}
      className="rounded-md border border-[#1e1e1e] px-2.5 py-2"
    >
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-0.5 text-sm tabular-nums text-gray-200">{value ?? "—"}</div>
      {sub && <div className="mt-0.5 text-[10px] tabular-nums text-gray-600">{sub}</div>}
    </div>
  )
}
