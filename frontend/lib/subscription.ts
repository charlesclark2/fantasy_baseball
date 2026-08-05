// Subscription / billing API helpers (E9.8). Thin wrappers over the backend Stripe
// endpoints; the frontend never talks to Stripe directly — checkout runs through a
// backend-created Checkout Session URL (server decides the founding vs standard price).

import { apiFetch } from "@/lib/api"

export type SubscriptionStatus = {
  tier: "admin" | "subscriber" | "beta_tester" | "churned" | "free"
  has_access: boolean
  is_beta: boolean
  has_billing: boolean
  // Stripe's Customer Portal cancel action schedules the cancellation rather than
  // revoking immediately — the account stays `subscriber` (access continues) until
  // `current_period_end`. (E9.57 finding: Settings must say so, not look unchanged.)
  cancel_at_period_end: boolean
  current_period_end: number | null // unix seconds
}

export type SubscriptionPricing = {
  tier: "founding" | "standard"
  unit_amount: number // cents
  currency: string
  founding_slots_used: number
  founding_cap: number
  founding_available: boolean
}

export function getSubscriptionStatus(token: string | null): Promise<SubscriptionStatus> {
  return apiFetch("/subscription/status", {}, token)
}

export function getSubscriptionPricing(token: string | null): Promise<SubscriptionPricing> {
  return apiFetch("/subscription/pricing", {}, token)
}

export async function startCheckout(token: string | null): Promise<void> {
  const res: { url: string } = await apiFetch(
    "/stripe/create-checkout-session",
    { method: "POST" },
    token,
  )
  window.location.href = res.url
}

export async function openBillingPortal(token: string | null): Promise<void> {
  const res: { url: string } = await apiFetch(
    "/stripe/create-portal-session",
    { method: "POST" },
    token,
  )
  window.location.href = res.url
}
