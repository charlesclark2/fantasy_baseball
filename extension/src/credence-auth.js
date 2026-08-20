// NF-C-LDA-1 — the ENTITLEMENT handoff. Runs ONLY on credencesports.com.
//
// ══ HOW THE EXTENSION KNOWS WHO YOU ARE ═══════════════════════════════════════════════════════
// The overlay is paid, and the gate that matters is SERVER-side: `/fantasy/nfl/draft-assistant`
// sits behind `require_fantasy_access`, so an unentitled caller gets a 403 no matter what this
// extension believes (E9.45 — a client-side gate on a paid feature is not a gate). This file only
// answers the practical question of how a bearer token reaches the background worker.
//
// It reads the user's OWN Credence session from OUR OWN origin's `localStorage`, where
// `amazon-cognito-identity-js` already keeps it for the web app, and hands it to the background.
//
// ⛔ THE DISTINCTION FROM THE ESPN RED LINE IS NOT A LOOPHOLE, IT IS THE WHOLE POINT. NF-C0 §3(c)
// refuses to hold a user's ESPN `espn_s2` because it is a THIRD PARTY's long-lived, unscoped,
// non-revocable session credential with no consent screen. This is OUR OWN session, on OUR OWN
// origin, granted to a user who installed our extension, revocable by signing out, and it is used
// for exactly one thing: authenticating them to us. The two are not the same act, and conflating
// them would argue that no extension may ever authenticate its own user.
//
// ⛔ AND IT IS ONE-WAY. This file never sends the token to ESPN, never reads an ESPN page (the
// manifest grants it no ESPN host match), and never persists the token itself — the background
// keeps it in `chrome.storage.session`, which is in-memory and cleared when the browser closes.
(function () {
  "use strict";

  //: The `amazon-cognito-identity-js` cache layout the web app writes:
  //:   CognitoIdentityServiceProvider.<clientId>.<username>.accessToken
  //: Matched structurally rather than by a hardcoded client id — the id is deployment config, and
  //: a hardcoded one silently stops matching the day it rotates, which would present as "the
  //: extension says I am signed out while the site says I am signed in".
  var ACCESS_TOKEN_RE = /^CognitoIdentityServiceProvider\..+\.accessToken$/;

  function readAccessToken() {
    try {
      var newest = null;
      for (var i = 0; i < window.localStorage.length; i++) {
        var key = window.localStorage.key(i);
        if (!key || !ACCESS_TOKEN_RE.test(key)) continue;
        var value = window.localStorage.getItem(key);
        // A JWT and nothing else. Anything that is not three dot-separated base64url segments is
        // not a token we should be forwarding anywhere.
        if (typeof value === "string" && /^[\w-]+\.[\w-]+\.[\w-]+$/.test(value)) newest = value;
      }
      return newest;
    } catch (e) {
      return null;     // private mode / storage disabled — the overlay then says "signed out"
    }
  }

  var last = null;
  function push() {
    var token = readAccessToken();
    if (token === last) return;          // nothing changed; do not chatter at the worker
    last = token;
    try {
      chrome.runtime.sendMessage({ type: "CREDENCE_TOKEN", token: token }, function () {
        // Swallowing `lastError` deliberately: the worker may be asleep, and a console error on
        // our own marketing pages would be a support ticket about nothing.
        void chrome.runtime.lastError;
      });
    } catch (e) { /* extension context torn down (an update/reload) — the next tick retries */ }
  }

  push();
  // A sign-in, a sign-out and a silent refresh all rewrite the same keys, and none of them
  // navigates. Re-read on a slow tick so the extension follows the site's session rather than
  // whatever it happened to see on first paint.
  setInterval(push, 15000);
  window.addEventListener("storage", push);
  window.addEventListener("focus", push);
})();
