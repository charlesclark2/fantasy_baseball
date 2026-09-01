// NF-CSV1 — reading an exported board CSV the way a spreadsheet reader receives it.
//
// ⭐ ONE OWNER FOR THE SPLIT, because two specs assert the SAME row-count contract from opposite
// sides — `fantasy-board-flows.spec.ts` on an untouched board (no note) and
// `full-season-rate.spec.ts` on a planted one (a note) — and a contract each spec spelled for
// itself would be two contracts that could drift apart (the E9.61 "two renderers of one field are
// two rule sets" lesson, on the assertion side).
//
// ⚠️ THE NOTE IS IDENTIFIED BY ITS OWN COPY, NOT BY A SHAPE HEURISTIC. "the last line", "a line
// whose first cell is not a number", "a line with fewer commas" would each pass on a build that
// appended something else entirely, and the first would pass on a build that appended nothing at
// all (the last data row is then "the note"). Keying on `CSV_WITHHELD_NOTE.lead` means a note that
// stops being the note is a red test rather than a quiet reclassification.
import { CSV_WITHHELD_NOTE } from "@/lib/fantasy-claim-copy"

export type ExportedCsv = {
  /** The raw bytes, exactly as downloaded. */
  raw: string
  /** Row 1, split on commas — the header, which must stay row 1. */
  header: string[]
  /** Every line after the header that is NOT the note row. */
  dataLines: string[]
  /** The note row(s). Exactly 0 or 1 in a correct file; the contract asserts which. */
  noteLines: string[]
}

/** Split a downloaded export into its header, its data rows and its note row.
 *
 *  ⛔ Trailing-newline handling is `replace(/\n+$/, "")`, NOT `String.trim()`. `trim()` would also
 *  eat LEADING whitespace, and a build that prepended a blank line before the header — the exact
 *  "header stays row 1" defect this file's contract exists to catch — would be silently repaired
 *  by the reader before any assertion saw it. */
export function readExportedCsv(raw: string): ExportedCsv {
  const lines = raw.replace(/\n+$/, "").split("\n")
  const rest = lines.slice(1)
  const isNote = (l: string) => l.includes(CSV_WITHHELD_NOTE.lead)
  return {
    raw,
    header: (lines[0] ?? "").split(","),
    dataLines: rest.filter((l) => !isNote(l)),
    noteLines: rest.filter(isNote),
  }
}

/** Pull the note row's FIRST CELL back out, unescaping the quoting `downloadCsv` applied.
 *
 *  The note contains commas, so it is written as one quoted field; reading it back is what lets a
 *  spec pin the RENDERED bytes against the copy constant rather than against a substring of them. */
export function noteCell(line: string): string {
  const m = line.match(/^"((?:[^"]|"")*)"/)
  return m ? m[1].replace(/""/g, '"') : line.split(",")[0]
}
