"use client"

import { useRouter } from "next/navigation"
import { useRef, useState, useEffect } from "react"
import Link from "next/link"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Nav } from "@/components/nav"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Bell, Check, ChevronDown, ChevronUp, Pencil, Plus, ShieldCheck, Trash2, X } from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { useLocalStorage } from "@/hooks/use-local-storage"
import { apiFetch } from "@/lib/api"

// ---------------------------------------------------------------------------
// Curated sportsbooks — same set as Book Comparison
// ---------------------------------------------------------------------------

const BOOK_CHOICES = [
  "BetMGM", "Caesars", "FanDuel", "DraftKings",
  "Fanatics", "Bovada", "Pinnacle", "Unspecified",
]

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BookAccount {
  book: string
  current_balance: number
}

interface BankrollEvent {
  event_id: string
  book: string
  type: "deposit" | "withdrawal"
  amount: number
  date: string
}

interface BookGrowth {
  total_deposited: number
  total_withdrawn: number
  net_deposits: number
  current_balance: number
  betting_pnl: number
  growth_pct: number | null
}

interface BankrollData {
  book_accounts: BookAccount[]
  bankroll_events: BankrollEvent[]
  overall_growth: BookGrowth
  per_book_growth: Record<string, BookGrowth>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tierLabel(groups: string[]): string {
  if (groups.includes("admin")) return "Admin"
  if (groups.includes("subscriber")) return "Subscriber"
  if (groups.includes("beta_tester")) return "Beta Tester"
  if (groups.includes("churned")) return "Churned"
  return "Free"
}

function tierStyle(groups: string[]): string {
  if (groups.includes("admin")) return "border border-purple-500/30 bg-purple-500/10 text-purple-400 hover:bg-purple-500/10"
  if (groups.includes("subscriber")) return "border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/10"
  if (groups.includes("churned")) return "border border-gray-500/30 bg-gray-500/10 text-gray-400 hover:bg-gray-500/10"
  return "border border-blue-500/30 bg-blue-500/10 text-blue-400 hover:bg-blue-500/10"
}

function fmtPnl(v: number) {
  const abs = Math.abs(v).toFixed(2)
  return v >= 0 ? `+$${abs}` : `-$${abs}`
}

function fmtGrowth(v: number | null) {
  if (v == null) return null
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}

function pnlColor(v: number | null | undefined) {
  return (v ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
}

// Today's date as YYYY-MM-DD
function todayIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

// ---------------------------------------------------------------------------
// AddBookPanel — select + add a new sportsbook
// ---------------------------------------------------------------------------

function AddBookPanel({
  existing,
  onAdd,
  isPending,
}: {
  existing: string[]
  onAdd: (book: string, balance: number) => void
  isPending: boolean
}) {
  const [open, setOpen] = useState(false)
  const [book, setBook] = useState("")
  const [balance, setBalance] = useState("")

  const available = BOOK_CHOICES.filter((b) => !existing.includes(b))

  function handleAdd() {
    if (!book) return
    const bal = parseFloat(balance)
    onAdd(book, isNaN(bal) ? 0 : Math.max(0, bal))
    setOpen(false)
    setBook("")
    setBalance("")
  }

  if (!open) {
    return (
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setOpen(true)}
        disabled={available.length === 0}
        className="mt-2 border border-dashed border-[#262626] text-gray-500 hover:text-gray-300 hover:border-gray-500 w-full justify-center gap-2"
      >
        <Plus className="h-3.5 w-3.5" />
        Add a sportsbook
      </Button>
    )
  }

  return (
    <div className="mt-2 rounded-lg border border-[#262626] bg-[#0a0a0a] p-4 space-y-3">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Add sportsbook</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">Book</Label>
          <select
            value={book}
            onChange={(e) => setBook(e.target.value)}
            className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-sm text-white focus:outline-none focus:border-[#10b981]"
          >
            <option value="">Select…</option>
            {available.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="new-balance" className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
            Current balance
          </Label>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">$</span>
            <Input
              id="new-balance"
              type="number"
              min={0}
              step={10}
              placeholder="0"
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              className="pl-6 bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981]"
            />
          </div>
        </div>
      </div>
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={handleAdd}
          disabled={!book || isPending}
          className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-50"
        >
          {isPending ? "Adding…" : "Add"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => { setOpen(false); setBook(""); setBalance("") }}
          className="text-gray-500 hover:text-gray-300"
        >
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CashFlowForm — inline deposit / withdrawal recorder
// ---------------------------------------------------------------------------

function CashFlowForm({
  book,
  onSubmit,
  isPending,
  onCancel,
  defaultAmount,
}: {
  book: string
  onSubmit: (type: "deposit" | "withdrawal", amount: number, date: string) => void
  isPending: boolean
  onCancel: () => void
  defaultAmount?: number
}) {
  const [type, setType] = useState<"deposit" | "withdrawal">("deposit")
  const [amount, setAmount] = useState(defaultAmount != null && defaultAmount > 0 ? String(defaultAmount) : "")
  const [date, setDate] = useState(todayIso())

  function handleSubmit() {
    const amt = parseFloat(amount)
    if (isNaN(amt) || amt <= 0) return
    onSubmit(type, amt, date)
  }

  return (
    <div className="mt-3 rounded-md border border-[#262626] bg-[#0a0a0a] p-3 space-y-3">
      <div className="flex gap-1.5">
        {(["deposit", "withdrawal"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={`rounded px-3 py-1 text-xs font-medium transition-colors capitalize ${
              type === t
                ? t === "deposit"
                  ? "bg-[#10b981] text-[#0a0a0a]"
                  : "bg-[#ef4444] text-white"
                : "border border-[#262626] text-gray-500 hover:text-gray-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-[11px] text-gray-500">Amount</Label>
          <div className="relative">
            <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-gray-500">$</span>
            <Input
              type="number"
              min={0.01}
              step={10}
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="pl-5 h-8 text-sm bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981]"
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label className="text-[11px] text-gray-500">Date</Label>
          <Input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="h-8 text-sm bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981]"
          />
        </div>
      </div>
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={isPending || !amount || parseFloat(amount) <= 0}
          className="h-7 px-3 text-xs bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-50"
        >
          {isPending ? "Saving…" : "Record"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onCancel}
          className="h-7 px-3 text-xs text-gray-500 hover:text-gray-300"
        >
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// BookCard — one sportsbook row
// ---------------------------------------------------------------------------

function BookCard({
  account,
  growth,
  events,
  existingBooks,
  onBalanceChange,
  onAddEvent,
  onRemove,
  onReassign,
  onDeleteEvent,
  onResetBaseline,
  isUpdating,
  isAddingEvent,
  isReassigning,
  isDeletingEvent,
  isResettingBaseline,
}: {
  account: BookAccount
  growth: BookGrowth | undefined
  events: BankrollEvent[]
  existingBooks: string[]
  onBalanceChange: (book: string, balance: number) => void
  onAddEvent: (book: string, type: "deposit" | "withdrawal", amount: number, date: string) => void
  onRemove: (book: string) => void
  onReassign: (fromBook: string, toBook: string) => void
  onDeleteEvent: (eventId: string) => void
  onResetBaseline: (book: string) => void
  isUpdating: boolean
  isAddingEvent: boolean
  isReassigning: boolean
  isDeletingEvent: boolean
  isResettingBaseline: boolean
}) {
  const [balInput, setBalInput] = useState(String(account.current_balance))
  const [balSaved, setBalSaved] = useState(false)
  const balTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [showCashFlow, setShowCashFlow] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [showReassign, setShowReassign] = useState(false)
  const [reassignTo, setReassignTo] = useState("")
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => {
    setBalInput(String(account.current_balance))
  }, [account.current_balance])

  function handleBalanceSave() {
    const parsed = parseFloat(balInput)
    if (isNaN(parsed) || parsed < 0) return
    onBalanceChange(account.book, Math.max(0, parsed))
    if (balTimer.current) clearTimeout(balTimer.current)
    setBalSaved(true)
    balTimer.current = setTimeout(() => setBalSaved(false), 2000)
  }

  function handleReassign() {
    if (!reassignTo) return
    onReassign(account.book, reassignTo)
    setShowReassign(false)
    setReassignTo("")
  }

  const availableBooks = BOOK_CHOICES.filter(
    (b) => b !== account.book && !existingBooks.includes(b)
  )
  const bookEvents = events.filter((e) => e.book === account.book)
  const growthStr = growth ? fmtGrowth(growth.growth_pct) : null

  return (
    <div className="rounded-lg border border-[#262626] bg-[#0a0a0a] p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {showReassign ? (
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <select
                value={reassignTo}
                onChange={(e) => setReassignTo(e.target.value)}
                className="flex-1 rounded border border-[#262626] bg-[#141414] px-2 py-1 text-sm text-white focus:outline-none focus:border-[#10b981]"
              >
                <option value="">Rename to…</option>
                {availableBooks.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
              <Button
                size="sm"
                onClick={handleReassign}
                disabled={!reassignTo || isReassigning}
                className="h-7 px-2.5 text-xs bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-50"
              >
                {isReassigning ? "…" : "Save"}
              </Button>
              <button
                onClick={() => { setShowReassign(false); setReassignTo("") }}
                className="text-gray-600 hover:text-gray-400"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <>
              <span className="text-sm font-semibold text-white truncate">{account.book}</span>
              {availableBooks.length > 0 && (
                <button
                  onClick={() => setShowReassign(true)}
                  className="text-gray-600 hover:text-gray-400 transition-colors"
                  title="Rename book"
                >
                  <Pencil className="h-3 w-3" />
                </button>
              )}
              {growthStr && (
                <span className={`text-xs font-mono font-semibold ${pnlColor(growth?.growth_pct)}`}>
                  {growthStr}
                </span>
              )}
            </>
          )}
        </div>
        {!showReassign && (
          <button
            onClick={() => onRemove(account.book)}
            className="flex-shrink-0 text-gray-600 hover:text-[#ef4444] transition-colors"
            title="Remove book"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Current balance input */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">$</span>
          <Input
            type="number"
            min={0}
            step={10}
            value={balInput}
            onChange={(e) => setBalInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleBalanceSave() }}
            className="pl-6 h-8 text-sm bg-[#141414] border-[#262626] text-white focus:border-[#10b981]"
            placeholder="Current balance"
          />
        </div>
        <Button
          size="sm"
          onClick={handleBalanceSave}
          disabled={isUpdating}
          className="h-8 shrink-0 bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-50 text-xs"
        >
          {isUpdating ? "Saving…" : "Save"}
        </Button>
        {balSaved && (
          <span className="flex items-center gap-1 text-xs text-[#10b981] shrink-0">
            <Check className="h-3 w-3" />
          </span>
        )}
      </div>

      {/* P&L summary */}
      {growth && growth.total_deposited > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 font-mono">
          <span>Net P&amp;L: <span className={pnlColor(growth.betting_pnl)}>{fmtPnl(growth.betting_pnl)}</span></span>
          <span>Net deposits: <span className="text-gray-400">${growth.net_deposits.toFixed(2)}</span></span>
          {confirmReset ? (
            <span className="flex items-center gap-1.5 ml-auto font-sans">
              <span className="text-gray-400 text-[11px]">
                Reset to ${growth.current_balance.toFixed(2)}? Growth restarts at 0%.
              </span>
              <button
                onClick={() => { onResetBaseline(account.book); setConfirmReset(false) }}
                disabled={isResettingBaseline}
                className="text-[#f59e0b] hover:text-amber-300 text-[11px] font-semibold disabled:opacity-50"
              >
                {isResettingBaseline ? "…" : "Confirm"}
              </button>
              <button
                onClick={() => setConfirmReset(false)}
                className="text-gray-600 hover:text-gray-400"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmReset(true)}
              className="ml-auto font-sans text-[11px] text-gray-600 hover:text-[#f59e0b] transition-colors"
              title="Re-base this book's cost basis to its current balance — events are kept"
            >
              Reset baseline
            </button>
          )}
        </div>
      )}

      {/* Actions row */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => { setShowCashFlow((v) => !v); if (showHistory) setShowHistory(false) }}
          className={`flex items-center gap-1 text-xs transition-colors ${
            showCashFlow ? "text-[#10b981]" : "text-gray-500 hover:text-gray-300"
          }`}
        >
          <Plus className="h-3 w-3" />
          {showCashFlow ? "Cancel" : "Add deposit / withdrawal"}
        </button>

        {bookEvents.length > 0 && (
          <button
            onClick={() => { setShowHistory((v) => !v) }}
            className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-400 ml-auto"
          >
            {showHistory ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {bookEvents.length} event{bookEvents.length !== 1 ? "s" : ""}
          </button>
        )}
      </div>

      {/* Cash flow form */}
      {showCashFlow && (
        <CashFlowForm
          book={account.book}
          onSubmit={(type, amount, date) => {
            onAddEvent(account.book, type, amount, date)
            setShowCashFlow(false)
          }}
          isPending={isAddingEvent}
          onCancel={() => setShowCashFlow(false)}
          defaultAmount={account.current_balance > 0 ? account.current_balance : undefined}
        />
      )}

      {/* Event history */}
      {showHistory && bookEvents.length > 0 && (
        <div className="space-y-1 border-t border-[#262626] pt-2">
          {bookEvents.map((evt) => (
            <div key={evt.event_id} className="flex items-center gap-2 text-xs">
              <span className={`capitalize font-medium w-20 shrink-0 ${evt.type === "deposit" ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                {evt.type}
              </span>
              <span className="text-gray-500 font-mono flex-1">{evt.date}</span>
              <span className="text-gray-300 font-mono">${evt.amount.toFixed(2)}</span>
              {confirmDeleteId === evt.event_id ? (
                <div className="flex items-center gap-1.5 ml-1">
                  <span className="text-gray-500 text-[10px]">Delete?</span>
                  <button
                    onClick={() => { onDeleteEvent(evt.event_id); setConfirmDeleteId(null) }}
                    disabled={isDeletingEvent}
                    className="text-[#ef4444] hover:text-red-300 text-[10px] font-semibold disabled:opacity-50"
                  >
                    Yes
                  </button>
                  <button
                    onClick={() => setConfirmDeleteId(null)}
                    className="text-gray-600 hover:text-gray-400"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDeleteId(evt.event_id)}
                  className="ml-1 text-gray-700 hover:text-[#ef4444] transition-colors"
                  title="Delete this event"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SportsbooksSection — the full bankroll management card
// ---------------------------------------------------------------------------

function SportsbooksSection({ accessToken }: { accessToken: string | null }) {
  const queryClient = useQueryClient()

  const { data: bankroll, isLoading } = useQuery<BankrollData>({
    queryKey: ["bankroll"],
    queryFn: () => apiFetch("/users/bankroll", {}, accessToken),
    enabled: !!accessToken,
  })

  const balanceMutation = useMutation({
    mutationFn: ({ book, balance }: { book: string; balance: number }) =>
      apiFetch(
        `/users/bankroll/books/${encodeURIComponent(book)}`,
        { method: "PUT", body: JSON.stringify({ current_balance: balance }) },
        accessToken
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bankroll"] }),
  })

  const eventMutation = useMutation({
    mutationFn: (body: { book: string; type: string; amount: number; date: string }) =>
      apiFetch(
        "/users/bankroll/events",
        { method: "POST", body: JSON.stringify(body) },
        accessToken
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bankroll"] }),
  })

  const removeMutation = useMutation({
    mutationFn: (book: string) =>
      apiFetch(
        `/users/bankroll/books/${encodeURIComponent(book)}`,
        { method: "DELETE" },
        accessToken
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bankroll"] }),
  })

  const reassignMutation = useMutation({
    mutationFn: ({ fromBook, toBook }: { fromBook: string; toBook: string }) =>
      apiFetch(
        `/users/bankroll/books/${encodeURIComponent(fromBook)}/reassign`,
        { method: "PATCH", body: JSON.stringify({ to_book: toBook }) },
        accessToken
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bankroll"] }),
  })

  const deleteEventMutation = useMutation({
    mutationFn: (eventId: string) =>
      apiFetch(
        `/users/bankroll/events/${encodeURIComponent(eventId)}`,
        { method: "DELETE" },
        accessToken
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bankroll"] }),
  })

  const resetBaselineMutation = useMutation({
    mutationFn: (book: string) =>
      apiFetch(
        `/users/bankroll/books/${encodeURIComponent(book)}/reset-baseline`,
        { method: "POST" },
        accessToken
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bankroll"] }),
  })

  const accounts = bankroll?.book_accounts ?? []
  const events = bankroll?.bankroll_events ?? []
  const overall = bankroll?.overall_growth
  const perBook = bankroll?.per_book_growth ?? {}
  const existingBooks = accounts.map((a) => a.book)

  return (
    <section className="rounded-lg border border-[#262626] bg-[#141414]">
      <div className="px-6 pt-6 pb-4">
        <h2 className="text-base font-semibold text-white">Sportsbooks</h2>
        <p className="mt-1 text-xs text-gray-500">
          Track your bankroll across books. Set each book&apos;s current balance and record
          deposits / withdrawals so growth % reflects betting results — not cash movement.
        </p>
      </div>

      {/* Overall summary — visible once deposits are set */}
      {overall && overall.total_deposited > 0 && (
        <>
          <div className="grid grid-cols-3 gap-3 px-6 pb-4">
            <div className="rounded-md bg-[#0a0a0a] border border-[#262626] px-3 py-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Growth</p>
              <p className={`mt-1 text-lg font-bold font-mono ${pnlColor(overall.growth_pct)}`}>
                {fmtGrowth(overall.growth_pct) ?? "—"}
              </p>
              <p className="text-[10px] text-gray-600">on deposited funds</p>
            </div>
            <div className="rounded-md bg-[#0a0a0a] border border-[#262626] px-3 py-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Net P&amp;L</p>
              <p className={`mt-1 text-lg font-bold font-mono ${pnlColor(overall.betting_pnl)}`}>
                {fmtPnl(overall.betting_pnl)}
              </p>
              <p className="text-[10px] text-gray-600">excl. deposits &amp; withdrawals</p>
            </div>
            <div className="rounded-md bg-[#0a0a0a] border border-[#262626] px-3 py-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Total Deposited</p>
              <p className="mt-1 text-lg font-bold font-mono text-gray-300">
                ${overall.total_deposited.toFixed(2)}
              </p>
              <p className="text-[10px] text-gray-600">cost basis</p>
            </div>
          </div>
          <p className="px-6 pb-4 text-[11px] text-gray-600">
            Growth % = betting P&amp;L ÷ total deposited. Deposits and withdrawals are netted
            out — they don&apos;t inflate or deflate the figure.
            <span className="ml-1 text-gray-700">Distinct from ROI (return on stake).</span>
          </p>
          <Separator className="bg-[#262626]" />
        </>
      )}

      {/* Book list */}
      <div className="px-6 pb-6 space-y-3 pt-4">
        {isLoading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : accounts.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-sm font-medium text-white">No sportsbooks added yet</p>
            <p className="max-w-xs text-xs text-gray-500 leading-relaxed">
              Add a sportsbook and set its current balance. Record deposits and withdrawals
              so bankroll growth tracks betting results, not cash movement.
            </p>
          </div>
        ) : (
          accounts.map((acct) => (
            <BookCard
              key={acct.book}
              account={acct}
              growth={perBook[acct.book]}
              events={events}
              existingBooks={existingBooks}
              onBalanceChange={(book, balance) => balanceMutation.mutate({ book, balance })}
              onAddEvent={(book, type, amount, date) =>
                eventMutation.mutate({ book, type, amount, date })
              }
              onRemove={(book) => removeMutation.mutate(book)}
              onReassign={(fromBook, toBook) => reassignMutation.mutate({ fromBook, toBook })}
              onDeleteEvent={(eventId) => deleteEventMutation.mutate(eventId)}
              onResetBaseline={(book) => resetBaselineMutation.mutate(book)}
              isUpdating={balanceMutation.isPending}
              isAddingEvent={eventMutation.isPending}
              isReassigning={reassignMutation.isPending}
              isDeletingEvent={deleteEventMutation.isPending}
              isResettingBaseline={resetBaselineMutation.isPending}
            />
          ))
        )}

        <AddBookPanel
          existing={existingBooks}
          onAdd={(book, balance) => {
            // Set balance; if it's a deposit amount, also record the event
            balanceMutation.mutate({ book, balance })
            if (balance > 0) {
              eventMutation.mutate({ book, type: "deposit", amount: balance, date: todayIso() })
            }
          }}
          isPending={balanceMutation.isPending || eventMutation.isPending}
        />
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const { email, groups, signOut, accessToken } = useAuth()
  const router = useRouter()
  const [bankroll, setBankroll] = useLocalStorage<number>("ev_bankroll", 1000)
  const [kellyCap, setKellyCap] = useLocalStorage<number>("ev_kelly_cap", 5)
  const [savedVisible, setSavedVisible] = useState(false)
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function markSaved() {
    if (savedTimer.current) clearTimeout(savedTimer.current)
    setSavedVisible(true)
    savedTimer.current = setTimeout(() => setSavedVisible(false), 2000)
  }

  function handleSignOut() {
    signOut()
    router.push("/login")
  }

  return (
    <>
      <Nav authenticated activeLink="settings" userEmail={email} />

      <main className="mx-auto max-w-2xl space-y-6 px-4 py-8">
        <h1 className="text-2xl font-bold text-white">Settings</h1>

        {/* ---------------------------------------------------------------- */}
        {/* Notifications — coming soon                                       */}
        {/* ---------------------------------------------------------------- */}
        <section className="rounded-lg border border-[#262626] bg-[#141414]">
          <div className="px-6 pt-6 pb-4">
            <h2 className="text-base font-semibold text-white">Notifications</h2>
          </div>
          <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#262626]">
              <Bell className="h-5 w-5 text-gray-500" />
            </div>
            <p className="text-sm font-medium text-white">Coming soon</p>
            <p className="max-w-sm text-xs text-gray-500 leading-relaxed">
              Email alerts and browser push notifications are under development.
              We&apos;ll let you know when they&apos;re available.
            </p>
          </div>
        </section>

        {/* ---------------------------------------------------------------- */}
        {/* Account card                                                      */}
        {/* ---------------------------------------------------------------- */}
        <section className="rounded-lg border border-[#262626] bg-[#141414]">
          <div className="px-6 pt-6 pb-4">
            <h2 className="text-base font-semibold text-white">Account</h2>
          </div>

          {/* Email address */}
          <div className="flex items-center justify-between gap-4 px-6 py-4">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Email address
              </p>
              <div className="flex items-center gap-2">
                <span className="text-sm text-white">{email ?? "—"}</span>
                {email && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-[#262626] px-2 py-0.5 text-[11px] font-medium text-gray-400">
                    <ShieldCheck className="h-3 w-3 text-[#10b981]" />
                    Verified
                  </span>
                )}
              </div>
            </div>
          </div>

          <Separator className="bg-[#262626]" />

          {/* Subscription tier */}
          <div className="flex items-start justify-between gap-4 px-6 py-4">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Subscription tier
              </p>
              <div className="flex items-center gap-2">
                <Badge className={tierStyle(groups)}>
                  {tierLabel(groups)}
                </Badge>
              </div>
              <p className="text-xs text-gray-500">
                {groups.includes("subscriber")
                  ? "Active subscription."
                  : groups.includes("churned")
                  ? "Subscription ended."
                  : "Full access during beta period. No billing required."}
              </p>
            </div>
          </div>

          <Separator className="bg-[#262626]" />

          {/* Billing */}
          <div className="flex items-center justify-between gap-4 px-6 py-4">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Billing
              </p>
              <p className="text-sm text-gray-500">
                No active subscription — beta access
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled
              className="text-gray-600 hover:text-gray-600 disabled:opacity-40"
              asChild
            >
              <Link href="/billing">Manage billing</Link>
            </Button>
          </div>
        </section>

        {/* ---------------------------------------------------------------- */}
        {/* Betting defaults card                                             */}
        {/* ---------------------------------------------------------------- */}
        <section className="rounded-lg border border-[#262626] bg-[#141414]">
          <div className="px-6 pt-6 pb-4">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold text-white">Betting Defaults</h2>
              {savedVisible && (
                <span className="flex items-center gap-1 text-xs text-[#10b981] transition-opacity">
                  <Check className="h-3 w-3" />
                  Saved
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Used in the EV Tracker to calculate stake sizes. Changes save automatically.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-6 px-6 pb-6">
            <div className="space-y-2">
              <Label htmlFor="bankroll" className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Bankroll
              </Label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">$</span>
                <Input
                  id="bankroll"
                  type="number"
                  min={0}
                  step={100}
                  value={bankroll}
                  onChange={(e) => { setBankroll(Math.max(0, Number(e.target.value))); markSaved() }}
                  className="pl-6 bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981] focus:ring-[#10b981]/20"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="kelly-cap" className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Kelly Cap
              </Label>
              <div className="relative">
                <Input
                  id="kelly-cap"
                  type="number"
                  min={1}
                  max={25}
                  step={1}
                  value={kellyCap}
                  onChange={(e) => { setKellyCap(Math.min(25, Math.max(1, Number(e.target.value)))); markSaved() }}
                  className="pr-8 bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981] focus:ring-[#10b981]/20"
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">%</span>
              </div>
              <p className="text-[11px] text-gray-600">Max stake per bet as % of bankroll (1–25)</p>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- */}
        {/* Sportsbooks / Bankroll bookkeeping (E9.17)                        */}
        {/* ---------------------------------------------------------------- */}
        <SportsbooksSection accessToken={accessToken} />

        {/* ---------------------------------------------------------------- */}
        {/* Danger zone card                                                  */}
        {/* ---------------------------------------------------------------- */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] border-l-2 border-l-[#ef4444]">
          <div className="px-6 pt-6 pb-4">
            <h2 className="text-base font-semibold text-[#ef4444]">Danger Zone</h2>
          </div>
          <div className="flex items-center justify-between gap-4 px-6 pb-5">
            <div className="space-y-1">
              <p className="text-sm font-medium text-white">Sign out of all devices</p>
              <p className="text-xs text-gray-500">
                Signs you out of all active sessions across all devices
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="shrink-0 border-[#ef4444]/50 text-[#ef4444] hover:bg-[#ef4444]/10 hover:text-[#ef4444] hover:border-[#ef4444]"
              onClick={handleSignOut}
            >
              Sign out everywhere
            </Button>
          </div>
        </section>
      </main>

    </>
  )
}
