import * as React from 'react'

import { cn } from '@/lib/utils'

/** The shadcn `Input` look, exported so a NON-`Input` control (e.g. `NumericInput`, which must
 *  render a raw `<input>`) can sit beside real `Input`s without the styling drifting apart. */
export const INPUT_BASE =
  'file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm ' +
  'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] ' +
  'aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        INPUT_BASE,
        className,
        // ⭐ AFTER `className`, deliberately. iOS Safari auto-zooms any focused form control whose
        // font-size is under 16px, and the zoom re-lays-out the viewport under the user. The base
        // classes above already say `text-base md:text-sm`, but `cn()` is tailwind-merge: a call
        // site passing `text-sm` (25 of them did — the bet-log and prop-logging forms, i.e. exactly
        // where a phone user types) REPLACES that safe base. This trailing `max-sm:` utility is a
        // different merge group, so it survives any call-site size, and Tailwind emits variant
        // utilities after unprefixed ones — so below 640px it wins the cascade and we stay at 16px.
        // Desktop is untouched: the media query simply does not apply.
        'max-sm:text-base',
      )}
      {...props}
    />
  )
}

export { Input }
