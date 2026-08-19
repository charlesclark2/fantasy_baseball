// NF-C-LDA-1 — the background service worker. THE ONLY FILE IN THIS EXTENSION THAT MAY REACH THE
// NETWORK, and it may reach exactly one host.
//
// ══ WHY THE NETWORK LIVES HERE AND NOWHERE ELSE ═══════════════════════════════════════════════
// NF-C-LDA-0's red line is OBSERVE, NEVER ORIGINATE: nothing we ship may make an authenticated
// request to ESPN on the user's behalf, because the browser would attach their `espn_s2` cookie for
// us and that is §3(c) wearing an extension costume. The spike could state that as "this extension
// issues no requests at all", which is a very easy rule to check.
//
// The overlay cannot keep that rule as written — it has to ask OUR API for a recommendation. So the
// rule is kept where it actually bites, by SEPARATING THE CONTEXTS:
//
//   * `main-world-probe.js` runs in ESPN's page context, sees the draft, and ORIGINATES NOTHING.
//   * `content.js` runs in the isolated world on the ESPN tab, renders, and ORIGINATES NOTHING.
//   * this file has NO ESPN page context at all, and talks to `api.credencesports.com` ONLY.
//
// A request to ESPN is therefore not "forbidden by convention" — the code that could see an ESPN
// page cannot make one, and the code that can make one cannot see an ESPN page. The host allowlist
// below is the second, explicit statement of the same thing, and `manifest.json` grants no ESPN
// host permission to this worker to begin with.
//
// ⛔ THE OUTBOUND BODY IS BUILT BY `wire.js`, NEVER BY THIS FILE. That serializer rebuilds the
// payload from an allowlist rather than filtering the state it was handed, so it cannot forward a
// field nobody knew about.
"use strict";

importScripts("./wire.js");

//: The ONE host this extension may talk to. A constant, not a setting: a configurable endpoint is
//: an exfiltration primitive with a nice name.
var API_ORIGIN = "https://api.credencesports.com";
var RECOMMEND_PATH = "/fantasy/nfl/draft-assistant";

//: Where the ESPN tab's content script hands us the user's Credence session, and where our own
//: site's content script deposits it. `chrome.storage.session` is in-memory and cleared when the
//: browser closes — a draft assistant has no reason to persist a bearer token to disk.
var TOKEN_KEY = "credence_access_token";

//: ⚠️ ONE IN FLIGHT AT A TIME. A draft socket can burst several frames a second; without this a
//: fast round of picks would fan out into a dozen concurrent paid requests, which is precisely the
//: traffic profile G100-D1's cost guardrails were sized against.
var inFlight = false;

function getToken() {
  return new Promise(function (resolve) {
    try {
      chrome.storage.session.get([TOKEN_KEY], function (got) {
        resolve((got && got[TOKEN_KEY]) || null);
      });
    } catch (e) { resolve(null); }
  });
}

/**
 * Ask our API for a recommendation.
 *
 * ⭐ EVERY FAILURE RETURNS A NAMED REASON, never `null` and never an empty list. An overlay that
 * receives "no recommendations" cannot tell "your subscription lapsed" from "the API is down" from
 * "we could not read the draft" — and it would render all three as an empty panel, which reads as
 * a quiet moment in the draft. That is the exact ambiguity this story exists to remove, so the
 * reason travels with the failure and the overlay prints it (E5.10: a swallowed error must be
 * SURFACEABLE, or an outage is indistinguishable from a quiet day).
 */
async function recommend(state, season) {
  var body = self.CredenceWire.buildPayload(state, season);
  if (!body) {
    return { ok: false, reason: "not_enough_state",
             message: "We can see the page but not yet your league’s settings or player pool." };
  }
  var token = await getToken();
  if (!token) {
    return { ok: false, reason: "signed_out",
             message: "Sign in at credencesports.com in another tab, then reload this page." };
  }
  var res;
  try {
    res = await fetch(API_ORIGIN + RECOMMEND_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: JSON.stringify(body)
    });
  } catch (e) {
    return { ok: false, reason: "network", message: "Couldn’t reach Credence: " + String(e && e.message || e) };
  }
  if (res.status === 401) {
    // The gateway's Cognito authorizer rejected the token before our Lambda ran, or it expired
    // mid-draft. Clear it so the next handoff from our site replaces it rather than re-failing.
    try { chrome.storage.session.remove([TOKEN_KEY]); } catch (e) {}
    return { ok: false, reason: "signed_out",
             message: "Your Credence session expired. Open credencesports.com to sign back in." };
  }
  if (res.status === 403) {
    return { ok: false, reason: "not_subscribed",
             message: "The live draft assistant is part of a Credence subscription." };
  }
  if (!res.ok) {
    var detail = "";
    try { detail = (await res.json()).detail || ""; } catch (e) {}
    return { ok: false, reason: "api_error_" + res.status,
             message: detail || ("Credence returned " + res.status + ".") };
  }
  try {
    return { ok: true, data: await res.json() };
  } catch (e) {
    return { ok: false, reason: "bad_response", message: "Credence sent something we couldn’t read." };
  }
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || typeof msg !== "object") return;

  if (msg.type === "CREDENCE_TOKEN") {
    // ⛔ ONLY FROM OUR OWN SITE. `sender.origin` is set by Chrome, not by the page, so a content
    // script injected anywhere else cannot claim to be us. Without this check any site the user
    // visits could hand us a token to attach to their requests.
    var origin = String((sender && sender.origin) || "");
    if (origin !== "https://credencesports.com" && origin !== "https://www.credencesports.com") {
      sendResponse({ ok: false, reason: "bad_origin" });
      return true;
    }
    var token = msg.token && String(msg.token);
    var write = {};
    write[TOKEN_KEY] = token || null;
    try { chrome.storage.session.set(write); } catch (e) {}
    sendResponse({ ok: true, stored: !!token });
    return true;
  }

  if (msg.type === "CREDENCE_RECOMMEND") {
    if (inFlight) {
      sendResponse({ ok: false, reason: "busy", message: "Still fetching the last recommendation." });
      return true;
    }
    inFlight = true;
    recommend(msg.state, msg.season)
      .then(function (out) { sendResponse(out); })
      .catch(function (e) {
        sendResponse({ ok: false, reason: "unexpected", message: String(e && e.message || e) });
      })
      .finally(function () { inFlight = false; });
    return true;    // keep the message channel open for the async reply
  }

  if (msg.type === "CREDENCE_AUTH_STATE") {
    getToken().then(function (t) { sendResponse({ ok: true, signedIn: !!t }); });
    return true;
  }
});
