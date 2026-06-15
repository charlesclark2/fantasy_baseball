"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Toaster } from "@/components/ui/toaster"
import { Bell, ShieldCheck } from "lucide-react"
import { useAuth } from "@/lib/auth-context"

export default function SettingsPage() {
  const { email, signOut } = useAuth()
  const router = useRouter()

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
