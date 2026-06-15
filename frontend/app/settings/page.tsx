"use client"

import { useRouter } from "next/navigation"
import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Toaster } from "@/components/ui/toaster"
import { Bell, Check, ShieldCheck } from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { useLocalStorage } from "@/hooks/use-local-storage"

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

export default function SettingsPage() {
  const { email, groups, signOut } = useAuth()
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
                  onChange={(e) => setBankroll(Math.max(0, Number(e.target.value)))}
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
                  onChange={(e) => setKellyCap(Math.min(25, Math.max(1, Number(e.target.value))))}
                  className="pr-8 bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981] focus:ring-[#10b981]/20"
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">%</span>
              </div>
              <p className="text-[11px] text-gray-600">Max stake per bet as % of bankroll (1–25)</p>
            </div>
          </div>
        </section>

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

      <Toaster />
    </>
  )
}
