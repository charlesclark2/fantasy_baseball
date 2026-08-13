// E9.58b — reading and recording ToS acceptance.
//
// Since E9.58 opened public self-serve signup, `tos_accepted_at` in credence-prod-dynamo-users
// is the only evidence that a given account agreed to the Terms. The write used to be
// fire-and-forget on both sides (`.catch(() => {})` here, `except Exception: logger.warning`
// server-side), so a failed write returned 204, reported success, and left an account in use
// with no acceptance on file — invisible everywhere.

import { apiFetch } from "@/lib/api"

export type TermsStatus =
  /** The backend told us. `accepted` is trustworthy. */
  | { known: true; accepted: boolean; acceptedAt: string | null }
  /** The backend did NOT tell us — see the deploy-skew note below. NEVER block on this. */
  | { known: false }

// ⭐ THE LOAD-BEARING DISTINCTION: a key that is ABSENT is not the same as a key that is NULL.
//
// The API Lambda ships only via a manual `deploy.sh` while the frontend auto-deploys on merge
// to `main`, so there is always a window where this code is live against a backend that has
// never heard of `tos_accepted_at`. In that window the field is ABSENT from the response.
// If absent were treated as "not accepted", the gate would block EVERY signed-in user until
// someone ran deploy.sh — a self-inflicted full outage of the product, caused by a guard.
//
// So: absent → `known: false` → fail OPEN (never block, and say so in the console).
//     present and null → `known: true, accepted: false` → block; this account really has none.
export async function getTermsStatus(accessToken: string | null): Promise<TermsStatus> {
  const profile = (await apiFetch("/users/profile", {}, accessToken)) as Record<string, unknown>
  if (!profile || !("tos_accepted_at" in profile)) {
    // Old backend. Deliberately not an error — this is the expected state during a deploy skew.
    console.warn(
      "[terms] backend does not report tos_accepted_at yet (deploy skew) — not gating. " +
        "Run infrastructure/lambda/deploy.sh to close this window.",
    )
    return { known: false }
  }
  const acceptedAt = (profile.tos_accepted_at as string | null) ?? null
  return { known: true, accepted: acceptedAt !== null, acceptedAt }
}

/**
 * G100-D0-R1 — what the acceptance write told us about whether this account is NEW.
 *
 * The same ABSENT-vs-NULL distinction `TermsStatus` draws above, for the same reason: the API
 * Lambda ships only via `deploy.sh` while this code auto-deploys, so a new client WILL run
 * against a backend whose `/auth/accept-terms` answers 204 with no body. That is `known: false`
 * — "the server did not tell us" — and it must never be collapsed into `created: false`, which
 * means "the server told us this account already existed". Collapsing them would take the
 * signup funnel's second step to a flat ZERO for the length of the skew window, and a zero on a
 * conversion chart reads as a conversion collapse rather than as a missing deploy.
 */
export type TermsAcceptance =
  /** The backend told us. `created` is authoritative. */
  | { known: true; created: boolean }
  /** The backend did NOT tell us (old Lambda, or a body we could not read). */
  | { known: false }

/**
 * Record acceptance. Throws on failure — the caller must NOT swallow it.
 *
 * ⚠️ `created` is read as a BOOLEAN ONLY when it is genuinely a boolean. Anything else — the
 * key missing (old backend, 204 ⇒ `apiFetch` returns null), a body that is not an object — is
 * reported as `known: false`, never as `created: false`, so an unknown can only ever
 * UNDER-count a signup. An analytics number that silently over-reports its own success metric
 * is much worse than one that misses some, because nothing downstream will question it.
 */
export async function acceptTerms(accessToken: string | null): Promise<TermsAcceptance> {
  const res = (await apiFetch("/auth/accept-terms", { method: "POST" }, accessToken)) as
    | Record<string, unknown>
    | null
  if (!res || typeof res.created !== "boolean") return { known: false }
  return { known: true, created: res.created }
}

/** One retry, because a single Dynamo/network blip should not escalate into a blocking modal. */
export async function acceptTermsWithRetry(accessToken: string | null): Promise<TermsAcceptance> {
  try {
    return await acceptTerms(accessToken)
  } catch {
    // ⚠️ The retry can only ever report `created: false`, because the FIRST attempt may well
    // have landed the write before its response was lost. That is the safe direction (a missed
    // signup, not an invented one) and it is why the retry is bounded at one.
    return await acceptTerms(accessToken)
  }
}
