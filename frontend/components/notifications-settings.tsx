"use client"

// Notifications settings (E9.9 / A0.6) — the live opt-in that replaces E9.10's
// "Coming soon" placeholder. Users choose channels for the "qualified plays today"
// alert: email (always available), browser push (needs permission), and SMS (needs
// a phone number, since Cognito doesn't capture one). Honest framing: this alerts
// when the model posts QUALIFIED plays — it is model output, not a bet recommendation.

import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Bell, Check, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { useToast } from "@/hooks/use-toast"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"
import {
  pushSupported,
  subscribeToPush,
  unsubscribeFromPush,
  PushPermissionDenied,
} from "@/lib/push"

interface Prefs {
  user_id: string
  enabled: boolean
  email_enabled: boolean
  push_enabled: boolean
  sms_enabled: boolean
  email: string | null
  phone_number: string | null
  push_subscription: unknown | null
}

const E164_RE = /^\+[1-9]\d{7,14}$/

function Row({
  title,
  desc,
  children,
}: {
  title: string
  desc: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-6 py-4">
      <div className="space-y-1">
        <p className="text-sm font-medium text-white">{title}</p>
        <p className="max-w-sm text-xs text-gray-500 leading-relaxed">{desc}</p>
      </div>
      <div className="shrink-0 pt-1">{children}</div>
    </div>
  )
}

export function NotificationsSettings({ accessToken }: { accessToken: string | null }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { email } = useAuth()

  const { data: prefs, isLoading } = useQuery<Prefs>({
    queryKey: ["alert-preferences"],
    queryFn: () => apiFetch("/alerts/preferences", {}, accessToken),
    enabled: !!accessToken,
  })

  const [phone, setPhone] = useState("")
  const [phoneErr, setPhoneErr] = useState<string | null>(null)
  useEffect(() => {
    if (prefs?.phone_number) setPhone(prefs.phone_number)
  }, [prefs?.phone_number])

  const putPrefs = useMutation({
    mutationFn: (body: Partial<Prefs>) =>
      apiFetch("/alerts/preferences", { method: "PUT", body: JSON.stringify(body) }, accessToken),
    onSuccess: (data) => queryClient.setQueryData(["alert-preferences"], data),
    onError: () => toast({ title: "Couldn't save notification settings", variant: "destructive" }),
  })

  const [pushBusy, setPushBusy] = useState(false)

  async function togglePush(on: boolean) {
    setPushBusy(true)
    try {
      if (on) {
        const subscription = await subscribeToPush()
        const data = await apiFetch(
          "/alerts/subscribe",
          { method: "POST", body: JSON.stringify({ subscription, email }) },
          accessToken
        )
        queryClient.setQueryData(["alert-preferences"], data)
        toast({ title: "Browser push enabled" })
      } else {
        await apiFetch("/alerts/subscribe", { method: "DELETE" }, accessToken)
        await unsubscribeFromPush()
        queryClient.invalidateQueries({ queryKey: ["alert-preferences"] })
        toast({ title: "Browser push disabled" })
      }
    } catch (e) {
      if (e instanceof PushPermissionDenied) {
        toast({
          title: "Notifications blocked",
          description: "Allow notifications for this site in your browser settings, then try again.",
          variant: "destructive",
        })
      } else {
        toast({ title: "Couldn't update browser push", variant: "destructive" })
      }
    } finally {
      setPushBusy(false)
    }
  }

  function saveSms(enabled: boolean) {
    const trimmed = phone.trim()
    if (enabled && !E164_RE.test(trimmed)) {
      setPhoneErr("Enter a phone number in +1XXXXXXXXXX format")
      return
    }
    setPhoneErr(null)
    putPrefs.mutate({
      sms_enabled: enabled,
      phone_number: trimmed || null,
      enabled: enabled ? true : prefs?.enabled,
    })
  }

  const enabled = prefs?.enabled ?? false
  const supported = typeof window !== "undefined" && pushSupported()

  return (
    <section className="rounded-lg border border-[#262626] bg-[#141414]">
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-[#10b981]" />
          <h2 className="text-base font-semibold text-white">Notifications</h2>
        </div>
        <p className="mt-1 text-xs text-gray-500 leading-relaxed">
          Get alerted when the model posts qualified plays for the day&apos;s slate. Most days
          nothing fires — you&apos;re only notified when there are qualified plays. This is model
          output, not betting advice.
        </p>
      </div>

      {isLoading ? (
        <p className="px-6 pb-6 text-sm text-gray-500">Loading…</p>
      ) : (
        <>
          <Separator className="bg-[#262626]" />

          {/* Master toggle */}
          <Row
            title="Enable alerts"
            desc="Turn all notifications on or off. Individual channels below."
          >
            <Switch
              checked={enabled}
              onCheckedChange={(v) => putPrefs.mutate({ enabled: v, email: email ?? undefined })}
            />
          </Row>

          <Separator className="bg-[#262626]" />

          {/* Email */}
          <Row
            title="Email"
            desc={email ? `Sent to ${email}` : "Sent to your account email"}
          >
            <Switch
              checked={(prefs?.email_enabled ?? true) && enabled}
              disabled={!enabled}
              onCheckedChange={(v) => putPrefs.mutate({ email_enabled: v, email: email ?? undefined })}
            />
          </Row>

          <Separator className="bg-[#262626]" />

          {/* Browser push */}
          <Row
            title="Browser push"
            desc={
              supported
                ? "Desktop / mobile push notifications from this browser."
                : "Not supported in this browser."
            }
          >
            {pushBusy ? (
              <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
            ) : (
              <Switch
                checked={(prefs?.push_enabled ?? false) && enabled}
                disabled={!enabled || !supported}
                onCheckedChange={togglePush}
              />
            )}
          </Row>

          <Separator className="bg-[#262626]" />

          {/* SMS */}
          <div className="px-6 py-4 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <p className="text-sm font-medium text-white">SMS / text</p>
                <p className="max-w-sm text-xs text-gray-500 leading-relaxed">
                  Text alerts to your phone. We store your number here — it isn&apos;t taken from
                  your login. Standard message rates may apply.
                </p>
              </div>
              <div className="shrink-0 pt-1">
                <Switch
                  checked={(prefs?.sms_enabled ?? false) && enabled}
                  disabled={!enabled}
                  onCheckedChange={(v) => saveSms(v)}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 space-y-1">
                <Label htmlFor="sms-phone" className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                  Phone number
                </Label>
                <Input
                  id="sms-phone"
                  type="tel"
                  inputMode="tel"
                  placeholder="+14155550123"
                  value={phone}
                  disabled={!enabled}
                  onChange={(e) => { setPhone(e.target.value); setPhoneErr(null) }}
                  className="bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981]"
                />
                {phoneErr && <p className="text-[11px] text-[#ef4444]">{phoneErr}</p>}
              </div>
              <Button
                size="sm"
                onClick={() => saveSms(prefs?.sms_enabled ?? false)}
                disabled={!enabled || putPrefs.isPending}
                className="mt-5 h-9 shrink-0 bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-50 text-xs"
              >
                {putPrefs.isPending ? "Saving…" : <span className="flex items-center gap-1"><Check className="h-3 w-3" /> Save</span>}
              </Button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
