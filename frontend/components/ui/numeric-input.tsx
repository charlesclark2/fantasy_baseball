"use client"

import { useState } from "react"

/**
 * A controlled numeric field that is actually typeable.
 *
 * Lifted out of the NF-C0b league editor (2026-08-01) because the same defect was live on the
 * bankroll and Kelly-cap fields on Settings and EV Tracker. The obvious spelling —
 * `value={n} onChange={e => set(Number(e.target.value))}` — is broken in four ways, all of which
 * this fixes by holding the raw STRING while the field has focus and committing only values that
 * are actually complete:
 *
 *  1. `Number("") === 0`. Clearing the field to retype it snaps the value to 0, so the box shows
 *     "0" and the next keystroke lands AFTER it, giving "01".
 *  2. `Number("-") === NaN`. Typing a minus to enter -2 writes NaN into state. `JSON.stringify`
 *     turns NaN into `null`, so a NaN can be POSTed to an API — the same for a lone ".".
 *  3. A committed 0 re-renders as "0", which cannot be deleted-and-retyped without hitting (1).
 *  4. ⭐ Clamping per-KEYSTROKE lands the user on a silently WRONG value rather than a malformed
 *     one. `Math.max(1, Number(""))` is 1, so clearing a min-1 field snaps it to "1" and the next
 *     keystroke reads "15" — a plausible number nobody typed. That is why `min`/`max` here REJECT
 *     an out-of-range draft (leaving the last good value committed) instead of clamping into it:
 *     the value on screen is always either what the user typed or what they last committed, never
 *     a third number the component invented. Blur then snaps the display back to the committed
 *     value, so an abandoned partial edit ("", "-") can never persist.
 *
 * `type="text"` + `inputMode` is deliberate, NOT an oversight: `type="number"` additionally fights
 * the user with spinners, silent locale parsing, and its own leading-zero normalisation. `inputMode`
 * still raises the numeric keypad on mobile, which is the only thing `type="number"` was buying.
 *
 * `text-base` on mobile is also deliberate — iOS Safari auto-zooms any form control under 16px.
 */
export function NumericInput({
  value,
  onCommit,
  min,
  max,
  allowDecimal = false,
  allowNegative = false,
  className,
  ariaLabel,
  disabled,
  id,
  placeholder,
}: {
  value: number
  onCommit: (n: number) => void
  min?: number
  max?: number
  allowDecimal?: boolean
  allowNegative?: boolean
  className?: string
  ariaLabel?: string
  disabled?: boolean
  /** Keep this in sync with any `<Label htmlFor>` partner — clicking the label must focus the field. */
  id?: string
  placeholder?: string
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const shown = draft ?? String(value)

  const pattern = allowDecimal
    ? allowNegative ? /^-?\d*\.?\d*$/ : /^\d*\.?\d*$/
    : allowNegative ? /^-?\d*$/ : /^\d*$/

  return (
    <input
      type="text"
      inputMode={allowDecimal ? "decimal" : "numeric"}
      aria-label={ariaLabel}
      disabled={disabled}
      id={id}
      placeholder={placeholder}
      className={className}
      value={shown}
      onChange={(e) => {
        const raw = e.target.value
        if (!pattern.test(raw)) return // reject a keystroke that can't lead anywhere valid
        setDraft(raw)
        if (raw === "" || raw === "-" || raw === "." || raw === "-.") return // mid-edit, not a value
        const n = Number(raw)
        if (!Number.isFinite(n)) return
        if (min != null && n < min) return
        if (max != null && n > max) return
        onCommit(n)
      }}
      onBlur={() => setDraft(null)}
    />
  )
}
