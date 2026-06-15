// This file configures the initialization of Sentry on the client.
// The added config here will be used whenever a users loads a page in their browser.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";
import posthog from "posthog-js";

Sentry.init({
  dsn: "https://ad10d0ff82b864b2573906e05ee97918@o4511566981890048.ingest.us.sentry.io/4511566983004160",

  // Add optional integrations for additional features
  integrations: [Sentry.replayIntegration()],

  tracesSampleRate: 0.2,
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;

posthog.init(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN!, {
  api_host: "/ingest",
  ui_host: "https://us.posthog.com",
  defaults: "2026-01-30",
  capture_exceptions: true,
  debug: process.env.NODE_ENV === "development",
});
