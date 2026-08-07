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

/**
 * E9.59 — the PUBLIC pricing read: what a logged-out stranger is shown.
 *
 * Every field except `founding_slots_remaining` comes from the Stripe Price object that
 * Checkout charges against, read server-side. ⛔ Never format a price from a constant in
 * this codebase — the whole point is that display and charge cannot drift, and a hardcoded
 * `$10` in a component silently re-creates the second source of truth E9.59 removed.
 *
 * Deliberately NO `founding_cap` / `founding_slots_used`: shipping the cap next to
 * `remaining` would leak the internal conversion count as a subtraction.
 */
export type PublicPricing = {
  unit_amount: number // cents
  currency: string
  interval: string // "month"
  interval_count: number
  product_name: string
  tier: "founding" | "standard"
  founding_slots_remaining: number
}

export function getSubscriptionPricing(token: string | null): Promise<SubscriptionPricing> {
  return apiFetch("/subscription/pricing", {}, token)
}

/**
 * No token — and it must stay that way. The route sits behind an API Gateway
 * `--authorization-type NONE` exemption, which means a Bearer token on it is not validated
 * upstream; the endpoint returns nothing caller-specific for exactly that reason.
 *
 * ⚠️ Until the operator adds that gateway route, this 401s for a logged-out visitor and
 * `apiFetch` throws `AuthError`. Callers must treat a failure as "show no price", never as
 * "hide the page" — the CTA has to keep working through the deploy-skew window.
 */
export function getPublicPricing(): Promise<PublicPricing> {
  return apiFetch("/subscription/public-pricing")
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
