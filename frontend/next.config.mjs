import { withSentryConfig } from "@sentry/nextjs";
/** @type {import('next').NextConfig} */
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // Next.js requires unsafe-inline for its inline scripts/styles
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      // ⚠️ EVERY HOST WE RENDER AN IMAGE FROM MUST BE LISTED, AND THE LIST IS NOT DERIVABLE FROM
      // THE SOURCE. Image URLs arrive in the DATA (nflverse's identity table supplies the NFL
      // headshot host; the team-logo helper builds the ESPN one), so a host can appear in a
      // published payload without ever appearing in this repo's code — and a missing entry fails
      // SILENTLY in the browser with no server-side error anywhere.
      //
      // 🩹 `static.www.nfl.com` was missing until 2026-08-08 and the block was invisible for as
      // long as it existed: `player-page.tsx` renders headshots with an `onError` → initials
      // fallback, so a CSP refusal looked exactly like "this player has no photo". It only surfaced
      // when the home page's fantasy card rendered one WITHOUT a fallback. Pinned against the
      // published fixtures by `test_e9_46_image_hosts_are_allowlisted.py`.
      "img-src 'self' data: blob: https://a.espncdn.com https://img.mlbstatic.com https://static.www.nfl.com",
      "font-src 'self'",
      // Cognito + our own API + PostHog + Sentry
      [
        "connect-src 'self'",
        "https://api.credencesports.com",
        "https://cognito-idp.us-east-1.amazonaws.com",
        // Cognito Hosted-UI (Google OAuth token exchange, E9.7)
        "https://us-east-1gg9zmbwqt.auth.us-east-1.amazoncognito.com",
        "https://us.i.posthog.com",
        "https://us-assets.i.posthog.com",
        "https://app.posthog.com",
        "https://*.sentry.io",
      ].join(" "),
      "frame-ancestors 'none'",
    ].join("; "),
  },
]

const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ]
  },
  // E9.56c — `/pricing` is the URL E9.56's locked CTAs shipped with and the one the deployed API
  // still returns as `upgrade.ctaHref` until the next `deploy.sh`. The page itself lives at
  // `/subscribe`. Every in-repo link now points there directly, so this is a BACKSTOP, not the
  // fix — it covers the API deploy-skew window and any link already handed out. Permanent, because
  // `/pricing` is also just the URL people will type.
  async redirects() {
    return [{ source: "/pricing", destination: "/subscribe", permanent: true }]
  },
  async rewrites() {
    return [
      {
        source: "/ingest/static/:path*",
        destination: "https://us-assets.i.posthog.com/static/:path*",
      },
      {
        source: "/ingest/array/:path*",
        destination: "https://us-assets.i.posthog.com/array/:path*",
      },
      {
        source: "/ingest/:path*",
        destination: "https://us.i.posthog.com/:path*",
      },
    ]
  },
  skipTrailingSlashRedirect: true,
}

export default withSentryConfig(nextConfig, {
  // For all available options, see:
  // https://www.npmjs.com/package/@sentry/webpack-plugin#options

  org: "credence-sports",

  project: "javascript-nextjs",

  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,

  // For all available options, see:
  // https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/

  // Upload a larger set of source maps for prettier stack traces (increases build time)
  widenClientFileUpload: true,

  // Uncomment to route browser requests to Sentry through a Next.js rewrite to circumvent ad-blockers.
  // This can increase your server load as well as your hosting bill.
  // Note: Check that the configured route will not match with your Next.js middleware, otherwise reporting of client-
  // side errors will fail.
  // tunnelRoute: "/monitoring",

  webpack: {
    // Enables automatic instrumentation of Vercel Cron Monitors. (Does not yet work with App Router route handlers.)
    // See the following for more information:
    // https://docs.sentry.io/product/crons/
    // https://vercel.com/docs/cron-jobs
    automaticVercelMonitors: true,

    // Tree-shaking options for reducing bundle size
    treeshake: {
      // Automatically tree-shake Sentry logger statements to reduce bundle size
      removeDebugLogging: true,
    },
  },
});
