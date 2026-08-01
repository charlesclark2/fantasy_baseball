"use client"

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

/**
 * A dropdown with a native-`<select>`-shaped API, rendered with Radix underneath.
 *
 * WHY THIS EXISTS (2026-08-01, third report of the same bug). On iOS the native `<select>` popup
 * was opening detached from the control — anchored near the top-left of the page rather than to
 * the field the user tapped. Two contributing causes were found and fixed first (a sub-16px font
 * triggering focus auto-zoom, and a `<select>` nested inside its own `<label>`), and neither was
 * sufficient: the popup was still misplaced with both corrected, a 16px font, a correct
 * `width=device-width` viewport, and no transform/scroll-container ancestor to blame.
 *
 * What settled it was that the defect tracked the IMPLEMENTATION, not the page. Every surface
 * using a raw `<select>` (the fantasy pages, Players, Settings) reproduced it; every surface
 * already using Radix (Bet Log, Parlay, the prop-logging dialogs) did not — same device, same
 * session. Radix renders a `<button>` trigger plus a portalled, JS-positioned menu, so it never
 * relies on WebKit anchoring a native popup at all.
 *
 * Two deliberate consequences worth knowing:
 *  - The trigger is a `<button>`, so it is immune to the iOS focus auto-zoom that affects
 *    `input`/`select`/`textarea`. The 16px-on-mobile rule still applies to real text fields.
 *  - Radix forbids an empty-string item value (it reserves "" for "nothing selected"). A native
 *    `<option value="">Select…</option>` therefore becomes `placeholder` here, which is what that
 *    option always meant anyway.
 */

export interface PickerOption {
  value: string
  label: string
  disabled?: boolean
}

export interface PickerGroup {
  label: string
  options: PickerOption[]
}

export function Picker({
  value,
  onValueChange,
  options,
  groups,
  placeholder,
  id,
  ariaLabel,
  className,
  contentClassName,
  disabled,
}: {
  /** Pass "" (or undefined) for "nothing selected" — the placeholder shows instead. */
  value: string | null | undefined
  onValueChange: (v: string) => void
  /** Flat list, or use `groups` for the `<optgroup>` equivalent. Exactly one of the two. */
  options?: PickerOption[]
  groups?: PickerGroup[]
  placeholder?: string
  id?: string
  ariaLabel?: string
  /** Classes for the trigger — the closest analogue to a native select's className. */
  className?: string
  contentClassName?: string
  disabled?: boolean
}) {
  const renderOption = (o: PickerOption) => (
    <SelectItem key={o.value} value={o.value} disabled={o.disabled}>
      {o.label}
    </SelectItem>
  )

  return (
    <Select
      // Radix treats "" as "no value"; a null/undefined value must map to that, not to a crash.
      value={value ? value : undefined}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <SelectTrigger id={id} aria-label={ariaLabel} className={cn(className)}>
        <SelectValue placeholder={placeholder ?? "Select…"} />
      </SelectTrigger>
      <SelectContent className={contentClassName}>
        {groups
          ? groups
              .filter((g) => g.options.length > 0)
              .map((g) => (
                <SelectGroup key={g.label}>
                  <SelectLabel>{g.label}</SelectLabel>
                  {g.options.map(renderOption)}
                </SelectGroup>
              ))
          : (options ?? []).map(renderOption)}
      </SelectContent>
    </Select>
  )
}
