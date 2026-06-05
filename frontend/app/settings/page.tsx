"use client"

import { useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { Toaster } from "@/components/ui/toaster"
import { useToast } from "@/components/ui/use-toast"
import { CheckCircle2, LogOut, ShieldCheck } from "lucide-react"

// ---------------------------------------------------------------------------
// TODO: wire to PUT /alerts/preferences and GET /auth/me
// ---------------------------------------------------------------------------
const MOCK_DATA = {
  user: {
    email: "user@example.com",
    tier: "beta_tester",
    emailVerified: true,
  },
  preferences: {
    pushNotifications: false,
    emailAlerts: true,
    alertTiming: "lineup_confirmation" as "lineup_confirmation" | "hours_before",
    hoursBeforeGame: 2,
  },
}

export default function SettingsPage() {
  const { toast } = useToast()

  // Preference state
  const [pushEnabled, setPushEnabled] = useState(MOCK_DATA.preferences.pushNotifications)
  const [emailEnabled, setEmailEnabled] = useState(MOCK_DATA.preferences.emailAlerts)
  const [alertTiming, setAlertTiming] = useState<"lineup_confirmation" | "hours_before">(
    MOCK_DATA.preferences.alertTiming
  )
  const [hoursBeforeGame, setHoursBeforeGame] = useState(MOCK_DATA.preferences.hoursBeforeGame)

  // Dirty tracking
  const isDirty =
    pushEnabled !== MOCK_DATA.preferences.pushNotifications ||
    emailEnabled !== MOCK_DATA.preferences.emailAlerts ||
    alertTiming !== MOCK_DATA.preferences.alertTiming ||
    hoursBeforeGame !== MOCK_DATA.preferences.hoursBeforeGame

  // Save success state
  const [saved, setSaved] = useState(false)

  function handleSave() {
    // TODO: call PUT /alerts/preferences
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  function handleSendTest() {
    toast({
      description: "Test notification sent",
    })
  }

  return (
    <>
      {/* ------------------------------------------------------------------ */}
      {/* Nav                                                                  */}
      {/* ------------------------------------------------------------------ */}
      <nav className="sticky top-0 z-50 border-b border-[#1a1a1a] bg-[#0a0a0a]/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <Link href="/" className="flex items-center gap-0 text-lg font-bold tracking-tight">
            <span className="text-[#10b981]">Credence</span>
            <span className="text-white"> Sports</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-gray-500 sm:block">
              {MOCK_DATA.user.email}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="text-gray-400 hover:text-white hover:bg-[#141414]"
              asChild
            >
              <Link href="/">
                <LogOut className="mr-1.5 h-3.5 w-3.5" />
                Sign Out
              </Link>
            </Button>
          </div>
        </div>
        {/* Sub-nav — Settings active */}
        <div className="mx-auto flex max-w-6xl gap-6 px-4 pb-0">
          <Link
            href="/dashboard"
            className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Dashboard
          </Link>
          <Link
            href="/performance"
            className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Performance
          </Link>
          <Link
            href="/settings"
            className="border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors"
          >
            Settings
          </Link>
        </div>
      </nav>

      {/* ------------------------------------------------------------------ */}
      {/* Page content                                                         */}
      {/* ------------------------------------------------------------------ */}
      <main className="mx-auto max-w-2xl space-y-6 px-4 py-8">
        {/* Page header */}
        <h1 className="text-2xl font-bold text-white">Settings</h1>

        {/* ---------------------------------------------------------------- */}
        {/* Notifications card                                                */}
        {/* ---------------------------------------------------------------- */}
        <section className="rounded-lg border border-[#262626] bg-[#141414]">
          <div className="px-6 pt-6 pb-4">
            <h2 className="text-base font-semibold text-white">Notifications</h2>
          </div>

          {/* Row 1 — Browser push */}
          <div className="flex items-start justify-between gap-4 px-6 py-4">
            <div className="flex-1 space-y-1">
              <p className="text-sm font-medium text-white">Browser push notifications</p>
              <p className="text-xs text-gray-500">
                Get alerted in your browser when a qualified pick fires
              </p>
              <div className="flex items-center gap-2 pt-1">
                {pushEnabled ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#10b981]/15 px-2 py-0.5 text-[11px] font-medium text-[#10b981]">
                    <CheckCircle2 className="h-3 w-3" />
                    Permission granted
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#262626] px-2 py-0.5 text-[11px] font-medium text-gray-500">
                    Permission not granted
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs text-gray-400 hover:text-white hover:bg-[#1f1f1f] disabled:opacity-40"
                  disabled={!pushEnabled}
                  onClick={handleSendTest}
                >
                  Send test
                </Button>
              </div>
            </div>
            <Switch
              checked={pushEnabled}
              onCheckedChange={(v) => { setPushEnabled(v); setSaved(false) }}
              className="mt-0.5 data-[state=checked]:bg-[#10b981]"
            />
          </div>

          <Separator className="bg-[#262626]" />

          {/* Row 2 — Email alerts */}
          <div className="flex items-start justify-between gap-4 px-6 py-4">
            <div className="flex-1 space-y-1">
              <p className="text-sm font-medium text-white">Email alerts</p>
              <p className="text-xs text-gray-500">
                Receive an email when a qualified pick is identified
              </p>
            </div>
            <Switch
              checked={emailEnabled}
              onCheckedChange={(v) => { setEmailEnabled(v); setSaved(false) }}
              className="mt-0.5 data-[state=checked]:bg-[#10b981]"
            />
          </div>

          <Separator className="bg-[#262626]" />

          {/* Alert timing */}
          <div className="px-6 py-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-gray-500">
              Alert timing
            </p>
            <RadioGroup
              value={alertTiming}
              onValueChange={(v) => {
                setAlertTiming(v as "lineup_confirmation" | "hours_before")
                setSaved(false)
              }}
              className="space-y-3"
            >
              {/* Option 1 */}
              <div className="flex items-start gap-3">
                <RadioGroupItem
                  value="lineup_confirmation"
                  id="timing-lineup"
                  className="mt-0.5 border-[#404040] text-[#10b981]"
                />
                <Label htmlFor="timing-lineup" className="cursor-pointer space-y-0.5">
                  <span className="text-sm font-medium text-white">At lineup confirmation</span>
                  <p className="text-xs text-gray-500">
                    Alerts fire when official lineups are posted (~90 min before first pitch)
                  </p>
                </Label>
              </div>

              {/* Option 2 */}
              <div className="flex items-start gap-3">
                <RadioGroupItem
                  value="hours_before"
                  id="timing-hours"
                  className="mt-0.5 border-[#404040] text-[#10b981]"
                />
                <Label htmlFor="timing-hours" className="cursor-pointer space-y-0.5">
                  <span className="text-sm font-medium text-white">X hours before game</span>
                  <p className="text-xs text-gray-500">
                    Alerts fire at a fixed time before first pitch
                  </p>
                </Label>
              </div>
            </RadioGroup>

            {/* Conditional hours input */}
            {alertTiming === "hours_before" && (
              <div className="mt-4 ml-7 flex items-center gap-3">
                <Label
                  htmlFor="hours-input"
                  className="text-xs text-gray-400 whitespace-nowrap"
                >
                  Hours before first pitch
                </Label>
                <input
                  id="hours-input"
                  type="number"
                  min={1}
                  max={6}
                  value={hoursBeforeGame}
                  onChange={(e) => {
                    const val = Math.min(6, Math.max(1, Number(e.target.value)))
                    setHoursBeforeGame(val)
                    setSaved(false)
                  }}
                  className="w-16 rounded-md border border-[#262626] bg-[#0a0a0a] px-2 py-1 text-sm text-white text-center focus:border-[#10b981] focus:outline-none"
                />
              </div>
            )}
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
                <span className="text-sm text-white">{MOCK_DATA.user.email}</span>
                {MOCK_DATA.user.emailVerified && (
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
                <Badge className="border border-blue-500/30 bg-blue-500/10 text-blue-400 hover:bg-blue-500/10">
                  Beta Tester
                </Badge>
              </div>
              <p className="text-xs text-gray-500">
                Full access during beta period. No billing required.
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
            >
              Sign out everywhere
            </Button>
          </div>
        </section>

        {/* ---------------------------------------------------------------- */}
        {/* Save button                                                       */}
        {/* ---------------------------------------------------------------- */}
        <div className="space-y-2 pb-8">
          <Button
            className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-40"
            disabled={!isDirty}
            onClick={handleSave}
          >
            Save preferences
          </Button>
          {saved && (
            <p className="flex items-center justify-center gap-1.5 text-sm text-[#10b981]">
              <CheckCircle2 className="h-4 w-4" />
              Preferences saved
            </p>
          )}
        </div>
      </main>

      <Toaster />
    </>
  )
}
