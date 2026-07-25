"use client"

import { useCallback, useEffect, useState } from "react"
import Image from "next/image"
import QRCode from "qrcode"
import posthog from "posthog-js"
import { Check, Copy, KeyRound, Loader2, ShieldCheck, ShieldOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp"
import { useAuth } from "@/lib/auth-context"
import {
  beginTotpEnrollment,
  confirmTotpEnrollment,
  disableTotpMfa,
  getMfaStatus,
  reauthenticatePassword,
  subscriberMfaRequired,
} from "@/lib/cognito"

type Mode = "view" | "enroll" | "disable"

export function MfaSettings() {
  const { email, groups } = useAuth()

  const [loading, setLoading] = useState(true)
  const [enabled, setEnabled] = useState(false)
  const [federated, setFederated] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [mode, setMode] = useState<Mode>("view")

  // Enrollment state
  const [secret, setSecret] = useState<string | null>(null)
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [enrollCode, setEnrollCode] = useState("")
  const [secretCopied, setSecretCopied] = useState(false)

  // Disable (re-auth) state
  const [reauthPassword, setReauthPassword] = useState("")

  const [working, setWorking] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const refreshStatus = useCallback(async () => {
    try {
      const status = await getMfaStatus()
      setEnabled(status.enabled)
      setFederated(status.federated)
      setStatusError(null)
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Could not load your security settings.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshStatus()
  }, [refreshStatus])

  function resetTransient() {
    setSecret(null)
    setQrDataUrl(null)
    setEnrollCode("")
    setReauthPassword("")
    setSecretCopied(false)
    setActionError(null)
    setWorking(false)
  }

  async function startEnroll() {
    if (!email) return
    resetTransient()
    setWorking(true)
    setMode("enroll")
    try {
      const { secretCode, otpauthUrl } = await beginTotpEnrollment(email)
      const dataUrl = await QRCode.toDataURL(otpauthUrl, { margin: 1, width: 200 })
      setSecret(secretCode)
      setQrDataUrl(dataUrl)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not start two-factor setup. Please try again.")
      setMode("view")
    } finally {
      setWorking(false)
    }
  }

  async function submitEnroll() {
    if (enrollCode.length !== 6) return
    setWorking(true)
    setActionError(null)
    try {
      await confirmTotpEnrollment(enrollCode)
      posthog.capture("mfa_enabled", { method: "totp" })
      resetTransient()
      setMode("view")
      await refreshStatus()
    } catch (err) {
      setActionError(
        err instanceof Error && /code|CodeMismatch|invalid/i.test(err.message)
          ? "That code didn't match. Check your authenticator app and try again."
          : err instanceof Error
          ? err.message
          : "Could not verify the code. Please try again.",
      )
      setWorking(false)
    }
  }

  async function submitDisable() {
    if (!email || !reauthPassword) return
    setWorking(true)
    setActionError(null)
    try {
      await reauthenticatePassword(email, reauthPassword)
      await disableTotpMfa()
      posthog.capture("mfa_disabled", { method: "totp" })
      resetTransient()
      setMode("view")
      await refreshStatus()
    } catch (err) {
      setActionError(
        err instanceof Error && /NotAuthorized|Incorrect|password/i.test(err.message)
          ? "That password is incorrect. Please try again."
          : err instanceof Error
          ? err.message
          : "Could not disable two-factor. Please try again.",
      )
      setWorking(false)
    }
  }

  function copySecret() {
    if (!secret) return
    navigator.clipboard?.writeText(secret).then(
      () => {
        setSecretCopied(true)
        setTimeout(() => setSecretCopied(false), 2000)
      },
      () => {},
    )
  }

  const required = subscriberMfaRequired(groups) && !enabled

  return (
    <section className="rounded-lg border border-[#262626] bg-[#141414]">
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-white">Two-Factor Authentication</h2>
          {!loading && !federated && (
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                enabled
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                  : "border-gray-500/30 bg-gray-500/10 text-gray-400"
              }`}
            >
              {enabled ? <ShieldCheck className="h-3 w-3" /> : <ShieldOff className="h-3 w-3" />}
              {enabled ? "Enabled" : "Disabled"}
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Protect your account with an authenticator app (TOTP). You&apos;ll enter a 6-digit code
          from the app when you sign in, in addition to your password.
        </p>
      </div>

      <div className="px-6 pb-6">
        {loading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : statusError ? (
          <Alert variant="destructive">
            <AlertDescription>{statusError}</AlertDescription>
          </Alert>
        ) : federated ? (
          // Google-session user — MFA inherited from Google; no Cognito TOTP prompt.
          <div className="flex items-start gap-3 rounded-md border border-[#262626] bg-[#0a0a0a] px-4 py-3">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#10b981]" />
            <p className="text-sm text-gray-300">
              You&apos;re signed in with Google, so two-factor authentication is managed by your
              Google account. Manage it in your Google security settings — there&apos;s nothing to
              set up here.
            </p>
          </div>
        ) : (
          <>
            {required && (
              <Alert className="mb-4 border-[#f59e0b]/40 bg-[#f59e0b]/10">
                <AlertDescription className="text-[#f59e0b]">
                  Two-factor authentication is required for your subscription. Please enable it to
                  keep access.
                </AlertDescription>
              </Alert>
            )}

            {actionError && mode !== "enroll" && mode !== "disable" && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>{actionError}</AlertDescription>
              </Alert>
            )}

            {/* ── View: enabled/disabled with the primary action ── */}
            {mode === "view" && (
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <KeyRound className="h-4 w-4 text-gray-500" />
                  <p className="text-sm text-gray-300">
                    {enabled
                      ? "Two-factor authentication is on for this account."
                      : "Two-factor authentication is off."}
                  </p>
                </div>
                {enabled ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0 border-[#ef4444]/50 text-[#ef4444] hover:bg-[#ef4444]/10 hover:text-[#ef4444] hover:border-[#ef4444]"
                    onClick={() => {
                      resetTransient()
                      setMode("disable")
                    }}
                  >
                    Disable
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    className="shrink-0 bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                    onClick={startEnroll}
                  >
                    Enable two-factor
                  </Button>
                )}
              </div>
            )}

            {/* ── Enroll: QR + secret + verify ── */}
            {mode === "enroll" && (
              <div className="space-y-4">
                <ol className="space-y-1 text-xs text-gray-400 list-decimal list-inside">
                  <li>Open your authenticator app (Google Authenticator, Authy, 1Password…).</li>
                  <li>Scan the QR code, or enter the setup key manually.</li>
                  <li>Enter the 6-digit code the app shows to finish.</li>
                </ol>

                <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
                  <div className="rounded-lg border border-[#262626] bg-white p-3">
                    {qrDataUrl ? (
                      <Image
                        src={qrDataUrl}
                        alt="Two-factor QR code"
                        width={180}
                        height={180}
                        unoptimized
                        className="h-[180px] w-[180px]"
                      />
                    ) : (
                      <div className="flex h-[180px] w-[180px] items-center justify-center">
                        <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
                      </div>
                    )}
                  </div>

                  <div className="flex-1 space-y-3">
                    <div className="space-y-1.5">
                      <Label className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                        Setup key (manual entry)
                      </Label>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 break-all rounded border border-[#262626] bg-[#0a0a0a] px-2.5 py-1.5 font-mono text-xs text-gray-300">
                          {secret ?? "…"}
                        </code>
                        <button
                          type="button"
                          onClick={copySecret}
                          disabled={!secret}
                          className="shrink-0 text-gray-500 hover:text-gray-300 disabled:opacity-40"
                          title="Copy setup key"
                        >
                          {secretCopied ? (
                            <Check className="h-4 w-4 text-[#10b981]" />
                          ) : (
                            <Copy className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                        Verification code
                      </Label>
                      <InputOTP
                        maxLength={6}
                        value={enrollCode}
                        onChange={setEnrollCode}
                        disabled={working}
                        containerClassName="justify-start"
                      >
                        <InputOTPGroup>
                          {[0, 1, 2, 3, 4, 5].map((i) => (
                            <InputOTPSlot key={i} index={i} className="text-white" />
                          ))}
                        </InputOTPGroup>
                      </InputOTP>
                    </div>
                  </div>
                </div>

                {actionError && (
                  <Alert variant="destructive">
                    <AlertDescription>{actionError}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={submitEnroll}
                    disabled={working || enrollCode.length !== 6}
                    className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-50"
                  >
                    {working ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Verifying…
                      </>
                    ) : (
                      "Verify & enable"
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      resetTransient()
                      setMode("view")
                    }}
                    disabled={working}
                    className="text-gray-500 hover:text-gray-300"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {/* ── Disable: re-auth with password ── */}
            {mode === "disable" && (
              <div className="space-y-3">
                <p className="text-sm text-gray-300">
                  Enter your password to turn off two-factor authentication.
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="reauth-password" className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                    Password
                  </Label>
                  <Input
                    id="reauth-password"
                    type="password"
                    autoComplete="current-password"
                    value={reauthPassword}
                    onChange={(e) => setReauthPassword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void submitDisable()
                    }}
                    disabled={working}
                    className="max-w-xs bg-[#0a0a0a] border-[#262626] text-white focus:border-[#10b981]"
                    autoFocus
                  />
                </div>

                {actionError && (
                  <Alert variant="destructive">
                    <AlertDescription>{actionError}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={submitDisable}
                    disabled={working || !reauthPassword}
                    className="border border-[#ef4444]/50 bg-transparent text-[#ef4444] hover:bg-[#ef4444]/10 disabled:opacity-50"
                  >
                    {working ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Disabling…
                      </>
                    ) : (
                      "Disable two-factor"
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      resetTransient()
                      setMode("view")
                    }}
                    disabled={working}
                    className="text-gray-500 hover:text-gray-300"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}
