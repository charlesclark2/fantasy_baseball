'use client'

import * as React from 'react'
import * as PopoverPrimitive from '@radix-ui/react-popover'

import { cn } from '@/lib/utils'

// 🐛 MOBILE TAP FIX (NF3.7, 2026-08-02): this used to be a thin wrapper around
// `@radix-ui/react-tooltip`. Radix's Tooltip is intentionally HOVER-ONLY — it closes on
// `pointerdown`, so a tap on a touch device can never open it (Radix's own docs point to Popover
// for a touch-reachable pattern). Every one of this app's ~30+ `<Tooltip>` call sites — the picks
// page, EV tracker, dashboard, picks table — was silently unreachable on a phone. This is the exact
// bug NF3.4 found and fixed for the fantasy `InfoTip` component, just never ported here. Rebuilt on
// Popover instead, with the SAME external API (`Tooltip`/`TooltipTrigger`/`TooltipContent`/
// `TooltipProvider`, incl. `asChild` and `delayDuration`), so no consumer needed to change: click/tap
// opens it directly via Popover's own toggle, and pointerType-gated hover handlers (mouse only) add
// the desktop hover-with-delay feel back on top — gating is required because a touch tap fires a
// real `click` immediately followed by a browser-synthesized `mouseleave`, which would otherwise
// close it again in the same frame.

const TooltipDelayContext = React.createContext(0)

function TooltipProvider({
  delayDuration = 0,
  children,
}: {
  delayDuration?: number
  children?: React.ReactNode
}) {
  return <TooltipDelayContext.Provider value={delayDuration}>{children}</TooltipDelayContext.Provider>
}

const TooltipOpenContext = React.createContext<{ setOpen: (open: boolean) => void } | null>(null)

function Tooltip({
  open: openProp,
  defaultOpen,
  onOpenChange,
  children,
}: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  const [openState, setOpenState] = React.useState(defaultOpen ?? false)
  const isControlled = openProp !== undefined
  const open = isControlled ? openProp : openState

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (!isControlled) setOpenState(next)
      onOpenChange?.(next)
    },
    [isControlled, onOpenChange],
  )

  const ctx = React.useMemo(() => ({ setOpen }), [setOpen])

  return (
    <PopoverPrimitive.Root data-slot="tooltip" open={open} onOpenChange={setOpen}>
      {/* The original `@radix-ui/react-tooltip` wrapper always nested its own zero-delay
          `TooltipProvider` directly around its `Root`, so an ANCESTOR `TooltipProvider`'s
          `delayDuration` was already shadowed/inert everywhere (a pre-existing, unrelated bug —
          out of scope here). Preserved as-is so this fix changes tap-reachability only, not the
          existing (already-zero) hover-open timing. */}
      <TooltipDelayContext.Provider value={0}>
        <TooltipOpenContext.Provider value={ctx}>{children}</TooltipOpenContext.Provider>
      </TooltipDelayContext.Provider>
    </PopoverPrimitive.Root>
  )
}

function TooltipTrigger({
  onPointerEnter,
  onPointerLeave,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  const ctx = React.useContext(TooltipOpenContext)
  const delayDuration = React.useContext(TooltipDelayContext)
  const openTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  React.useEffect(() => {
    return () => {
      if (openTimeoutRef.current) clearTimeout(openTimeoutRef.current)
    }
  }, [])

  return (
    <PopoverPrimitive.Trigger
      data-slot="tooltip-trigger"
      onPointerEnter={(e) => {
        onPointerEnter?.(e)
        if (e.pointerType !== 'mouse' || !ctx) return
        if (delayDuration > 0) {
          openTimeoutRef.current = setTimeout(() => ctx.setOpen(true), delayDuration)
        } else {
          ctx.setOpen(true)
        }
      }}
      onPointerLeave={(e) => {
        onPointerLeave?.(e)
        if (e.pointerType !== 'mouse' || !ctx) return
        if (openTimeoutRef.current) clearTimeout(openTimeoutRef.current)
        ctx.setOpen(false)
      }}
      {...props}
    />
  )
}

function TooltipContent({
  className,
  sideOffset = 4,
  children,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        // don't steal focus on hover-open, or the pointer leaving would fight the focus ring
        onOpenAutoFocus={(e) => e.preventDefault()}
        className={cn(
          'bg-foreground text-background animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-50 w-fit origin-(--radix-popover-content-transform-origin) rounded-md px-3 py-1.5 text-xs text-balance',
          className,
        )}
        {...props}
      >
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  )
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
