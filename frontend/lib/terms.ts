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

/** Record acceptance. Throws on failure — the caller must NOT swallow it. */
export async function acceptTerms(accessToken: string | null): Promise<void> {
  await apiFetch("/auth/accept-terms", { method: "POST" }, accessToken)
}

/** One retry, because a single Dynamo/network blip should not escalate into a blocking modal. */
export async function acceptTermsWithRetry(accessToken: string | null): Promise<void> {
  try {
    await acceptTerms(accessToken)
  } catch {
    await acceptTerms(accessToken)
  }
}
