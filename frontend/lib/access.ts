// E9.56c — the ONE way a visitor with no account can get one.
//
// There is no self-serve sign-up: the Cognito pool is not wired for public registration, and every
// "get an account" affordance in the product is this mailto (the nav's Request Access button and
// both home-page CTAs already use exactly this address and subject). The login page instead linked
// to `/request-access`, a route that has never existed in `frontend/app/` — so the single link a
// brand-new visitor was most likely to click, on the page they were most likely to be stranded on,
// was a 404. Verified live.
//
// Centralised here so the next person to change the address changes it once. `nav.tsx` and the home
// page still carry the literal; they are owned by the in-flight home-page redesign, so they are
// deliberately left alone rather than edited from under it — they should adopt this constant when
// that story lands.
//
// ⚠️ This is a STOPGAP, not a funnel. A visitor who arrives on a locked 2026 projection, decides to
// buy, and is told to send an email will mostly not send the email. Self-serve sign-up is the real
// fix and is a product decision (it needs the Cognito pool opened for registration plus an email
// verification flow) — see the E9.56c handoff.
export const REQUEST_ACCESS_MAILTO =
  "mailto:charlie@credencesports.com?subject=Beta%20Access%20Request"
