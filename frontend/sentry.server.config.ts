// This file configures the initialization of Sentry on the server.
// The config you add here will be used whenever the server handles a request.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: "https://ad10d0ff82b864b2573906e05ee97918@o4511566981890048.ingest.us.sentry.io/4511566983004160",

  tracesSampleRate: 0.2,
});
