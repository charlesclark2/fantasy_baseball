// NF-C-LDA-0 — the MAIN-world READ PROBE. Answers spike question 1: "can we reliably read the
// live ESPN draft state?" It reports what it FINDS; it decides nothing and sends nothing.
//
// ══ THE RED LINE THIS FILE IS BUILT AROUND ════════════════════════════════════════════════════
// `docs/nf_c0_espn_access_probe.md` §3(c) refuses holding or replaying the user's `espn_s2`
// session cookie: it is not read-scoped, not individually revocable, has no consent screen and is
// long-lived — functionally a password. §3(d) permits the USER-MEDIATED PASTE, because a response
// BODY is structurally incapable of carrying the cookie (the browser attaches it to the REQUEST
// and it is never echoed back).
//
// ⭐ THIS PROBE IS THE AUTOMATED ANALOGUE OF §3(d), AND THE PROPERTY THAT KEEPS IT THERE IS:
//
//        ⛔ OBSERVE, NEVER ORIGINATE. ⛔
//
// Every network reading below is a PASSIVE wrapper over a call THE PAGE ITSELF ALREADY MADE. This
// file issues no `fetch`, no `XMLHttpRequest`, opens no `WebSocket`, and reads no cookie. It
// therefore never makes an authenticated request on the user's behalf, and never comes into
// possession of a credential — the two things §3(c) actually forbids.
//
// The distinction is load-bearing and easy to erode, so it is stated as a rule rather than left to
// judgement: an extension COULD trivially call ESPN's league API and the browser would attach the
// user's cookie for it. That is "us making an authenticated request on the user's behalf" wearing
// an extension costume, and it is the same convenience pressure that would have produced
// "paste your cookie instead". If a future story wants it, it is a DELIBERATE policy decision with
// the operator, never a quiet refactor. `test_nf_c_lda_0_extension_red_line.py` fails the build if
// this file grows an originating call or touches `document.cookie`.
//
// ══ WHAT IT CAPTURES, AND WHAT IT REFUSES TO ═════════════════════════════════════════════════
// RESPONSE bodies only. ⛔ Never request headers — that is where `Cookie:`/`Authorization:` live,
// and the whole §3(d) argument is that a body cannot carry them while a header can. Structural
// summaries (key names, shapes, small samples) rather than whole payloads, because the finding is
// "what shape is readable", not the user's league.
(function () {
  "use strict";

  var CHANNEL = "__credence_draft_probe__";
  var MAX_SAMPLE = 3;
  var MAX_STR = 200;

  // ── Draft-shaped key signatures ───────────────────────────────────────────────────────────────
  // ⭐ SHAPE-DIRECTED, NOT NAME-DIRECTED, ON PURPOSE. Hardcoding `window.__espnfitt__` (or any other
  // remembered global) would make this probe answer "is the global I guessed still there?" — and a
  // NO would be indistinguishable from "ESPN renamed it", which is the exact ambiguity the spike
  // exists to remove. Scoring by the KEYS an object carries survives a rename, and reports the new
  // path instead. (The NF-C0e "a test that reads a value back under the key the code wrote" lesson,
  // applied to discovery.)
  var DRAFT_KEYS = [
    "draftDetail", "picks", "draftPicks", "currentPick", "onTheClock", "pickOrder",
    "draftOrder", "overallPickNumber", "roundPickNumber", "playerPoolEntry", "eligibleSlots",
    "proTeamId", "lineupSlotId", "teams", "players", "rosterForCurrentScoringPeriod"
  ];

  var findings = {
    schemaVersion: 1,
    startedAt: new Date().toISOString(),
    url: location.href,
    // Tier A/B/C, in the story's stated priority order.
    globals: [],     // A — in-page JSON state
    network: [],     // B — calls the page already made
    dom: null,       // C — rendered text (last resort, flagged brittle)
    pool: null,      // identity rows for the available pool (see extractPool)
    poolSource: null,
    errors: []
  };

  function note(where, err) {
    try { findings.errors.push(where + ": " + String(err && err.message || err)); } catch (e) {}
  }

  // ── Tier A: in-page JSON state ────────────────────────────────────────────────────────────────
  function scoreShape(obj, depth, seen) {
    // How many draft-shaped keys appear anywhere in the first few levels. Bounded so a probe can
    // never become the reason the draft room janks.
    if (!obj || typeof obj !== "object" || depth > 4) return 0;
    if (seen.has(obj)) return 0;
    seen.add(obj);
    var score = 0, n = 0;
    for (var k in obj) {
      if (n++ > 200) break;
      if (DRAFT_KEYS.indexOf(k) !== -1) score += 1;
      var v;
      try { v = obj[k]; } catch (e) { continue; }        // getters can throw
      if (v && typeof v === "object") score += scoreShape(v, depth + 1, seen);
    }
    return score;
  }

  function scanGlobals() {
    var out = [];
    var keys;
    try { keys = Object.keys(window); } catch (e) { note("scanGlobals", e); return out; }
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i], v;
      try { v = window[k]; } catch (e) { continue; }
      if (!v || typeof v !== "object") continue;
      var s;
      try { s = scoreShape(v, 0, new WeakSet()); } catch (e) { continue; }
      if (s > 0) out.push({ path: "window." + k, score: s, topKeys: safeKeys(v) });
    }
    out.sort(function (a, b) { return b.score - a.score; });
    return out.slice(0, 10);
  }

  function scanJsonScriptTags() {
    var out = [];
    try {
      var tags = document.querySelectorAll('script[type="application/json"], script[type="application/ld+json"], script[id]');
      for (var i = 0; i < tags.length && i < 40; i++) {
        var t = tags[i];
        var txt = (t.textContent || "").trim();
        if (txt.length < 2 || (txt[0] !== "{" && txt[0] !== "[")) continue;
        var parsed;
        try { parsed = JSON.parse(txt); } catch (e) { continue; }
        var s = scoreShape(parsed, 0, new WeakSet());
        if (s > 0) {
          out.push({ path: "script#" + (t.id || "(anon)") + "[" + i + "]", score: s,
                     bytes: txt.length, topKeys: safeKeys(parsed) });
        }
      }
    } catch (e) { note("scanJsonScriptTags", e); }
    return out;
  }

  function safeKeys(v) {
    try { return Object.keys(v).slice(0, 25); } catch (e) { return []; }
  }

  // ── Tier B: PASSIVE observation of calls the page already made ────────────────────────────────
  // ⛔ Wrappers only. Nothing here starts a request; each one waits for the page to start one and
  // reads what came back. A wrapper that threw would break the draft room, so every body read is
  // wrapped and failure is silent-but-recorded.
  var seenUrls = Object.create(null);

  // ── REDACTION — required before ANY raw frame is kept ────────────────────────────────────────
  // ⭐ ADDED WITH THE RAW-FRAME CAPTURE, NOT AFTER IT. The first capture showed the room fetching
  // `.../teams/14/draftSecurity`, whose response is a draft-join TOKEN — so the draft socket's own
  // handshake is a plausible carrier for that token, and "capture the raw frame" would otherwise be
  // the first thing in this extension that could persist a secret. The §3(c) red line is about not
  // coming into possession of credential material; a capture file we hand around is possession.
  //
  // So: redact token-shaped runs BEFORE anything is stored, and truncate hard. A pick event is
  // small ints and short strings; anything long and high-entropy is not a pick.
  var RAW_FRAME_LIMIT = 400;

  function redact(text) {
    if (typeof text !== "string") return null;
    return text
      // GUIDs (ESPN member SWIDs are exactly this shape — NF-C0: an identifier, but "not a
      // credential is not a reason to keep one").
      .replace(/\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?/gi, "<guid>")
      // JWT-ish and long opaque runs — a token, never a pick field.
      .replace(/\b[A-Za-z0-9_-]{24,}\b/g, "<redacted>")
      // Anything self-labelled as a secret.
      .replace(/("?(?:token|auth|secret|security|credential|session)"?\s*[:=]\s*)"[^"]*"/gi,
               "$1\"<redacted>\"")
      .slice(0, RAW_FRAME_LIMIT);
  }

  // ── POOL IDENTITY EXTRACTION ─────────────────────────────────────────────────────────────────
  // ⭐ WHY THIS EXISTS: a MOCK league is DELETED the moment the draft ends (measured — the league
  // URL returns `LEAGUE_NOT_FOUND_DELETED` afterwards), so nothing can be re-queried later. The
  // probe is the only thing that ever sees this data, and a structural summary of the pool is not
  // enough to measure whether we can RESOLVE it.
  //
  // ⛔ IDENTITY FIELDS ONLY — id / name / proTeam / slots. Deliberately NOT the whole payload:
  // `ownership`, `stats`, `draftRanksByRankType` and every league-private object stay out. These
  // five fields are ESPN's public player universe (the same for every league), which is what makes
  // keeping them proportionate.
  var POOL_LIMIT = 2000;

  function extractPool(parsed) {
    try {
      var list = parsed && parsed.players;
      if (!list || !list.length) return null;
      var out = [];
      for (var i = 0; i < list.length && i < POOL_LIMIT; i++) {
        var e = list[i];
        var pl = (e && e.player) ? e.player : e;      // draft room wraps; season endpoint does not
        if (!pl || pl.id === undefined) continue;
        out.push({
          id: pl.id,
          fullName: pl.fullName,
          proTeamId: pl.proTeamId,
          defaultPositionId: pl.defaultPositionId,
          eligibleSlots: pl.eligibleSlots
        });
      }
      return out.length ? out : null;
    } catch (e) { note("extractPool", e); return null; }
  }

  function recordCall(kind, url, bodyText) {
    try {
      if (!url) return;
      var short = String(url).split("?")[0];
      var key = kind + " " + short;
      var entry = seenUrls[key];
      if (!entry) {
        entry = seenUrls[key] = { kind: kind, url: short, count: 0, shape: null, score: 0 };
        findings.network.push(entry);
      }
      entry.count += 1;
      // Shape it once — repeat polls of the same endpoint add nothing but noise.
      if (entry.shape === null && bodyText) {
        var parsed = null;
        try { parsed = JSON.parse(bodyText); } catch (e) { parsed = null; }
        if (parsed === null) {
          // ⭐ THE FIRST CAPTURE'S BLIND SPOT. 25 frames arrived on the draft socket and NONE were
          // recorded, because this branch used to `return` on anything that was not JSON — so a
          // binary or custom-text pick protocol was indistinguishable from "no messages". The
          // sibling bamgrid socket recorded `bytes=367` on the same run, which is what proved the
          // wrapper worked and the FORMAT was the problem (NF1.7(a): a check that could not read is
          // not a check that found nothing).
          if (entry.rawSample === undefined) {
            entry.rawSample = redact(bodyText);
            entry.rawBytes = bodyText.length;
            entry.rawIsString = true;
          }
          return;
        }
        entry.score = scoreShape(parsed, 0, new WeakSet());
        entry.shape = summarize(parsed, 0);
        entry.bytes = bodyText.length;
        if (findings.pool === null) {
          var pool = extractPool(parsed);
          if (pool) { findings.pool = pool; findings.poolSource = entry.url; }
        }
      } else if (entry.shape === null && bodyText === null && entry.nonTextFrames === undefined) {
        // A frame arrived that was not a string at all (ArrayBuffer/Blob). Record THAT FACT —
        // "we saw N frames we could not read" is a finding; silence is not.
        entry.nonTextFrames = 0;
      }
      if (bodyText === null && entry.nonTextFrames !== undefined) entry.nonTextFrames += 1;
    } catch (e) { note("recordCall", e); }
  }

  // A STRUCTURAL summary: key names and types, with only tiny scalar samples. The finding is the
  // shape, and a whole league payload in a capture file is somebody's private league.
  function summarize(v, depth) {
    if (v === null) return "null";
    if (Array.isArray(v)) {
      return { __array__: v.length, of: v.length && depth < 4 ? summarize(v[0], depth + 1) : "?" };
    }
    var t = typeof v;
    if (t !== "object") {
      if (t === "string") return v.length > MAX_STR ? "str(" + v.length + ")" : v;
      return v;
    }
    if (depth > 4) return "{...}";
    var out = {}, n = 0;
    for (var k in v) {
      if (n++ >= 40) { out.__truncated__ = true; break; }
      try { out[k] = summarize(v[k], depth + 1); } catch (e) { out[k] = "?"; }
    }
    return out;
  }

  function decodePrefix(buf) {
    // Bounded, lossy-tolerant decode. A binary protocol still usually carries readable field names;
    // what matters is seeing ENOUGH to identify the protocol, not reconstructing it here.
    try {
      var view = new Uint8Array(buf, 0, Math.min(buf.byteLength, RAW_FRAME_LIMIT));
      if (typeof TextDecoder !== "undefined") {
        return new TextDecoder("utf-8", { fatal: false }).decode(view);
      }
      var out = "";
      for (var i = 0; i < view.length; i++) out += String.fromCharCode(view[i]);
      return out;
    } catch (e) { note("decodePrefix", e); return null; }
  }

  function installNetworkObservers() {
    // fetch
    try {
      var origFetch = window.fetch;
      if (typeof origFetch === "function") {
        window.fetch = function () {
          var args = arguments;
          var p = origFetch.apply(this, args);
          try {
            var url = (args[0] && args[0].url) || args[0];
            p.then(function (res) {
              try {
                // ⛔ res.clone() so the page's own consumer still gets its body untouched. Reading
                // the original would consume the stream and break the draft room.
                res.clone().text().then(function (t) { recordCall("fetch", url, t); },
                                        function () { recordCall("fetch", url, null); });
              } catch (e) { recordCall("fetch", url, null); }
            }, function () {});
          } catch (e) { note("fetch-observe", e); }
          return p;
        };
      }
    } catch (e) { note("installFetch", e); }

    // XMLHttpRequest
    try {
      var openOrig = XMLHttpRequest.prototype.open;
      XMLHttpRequest.prototype.open = function (method, url) {
        try { this.__credence_url = url; } catch (e) {}
        return openOrig.apply(this, arguments);
      };
      var sendOrig = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.send = function () {
        try {
          var self = this;
          this.addEventListener("load", function () {
            try {
              var ct = "";
              try { ct = self.getResponseHeader("content-type") || ""; } catch (e) {}
              // ⚠️ `responseText` THROWS when the page set `responseType = "json"` (or arraybuffer
              // /blob): the DOM spec makes it readable only for "" and "text". The first deep
              // capture recorded exactly that as
              //   "Failed to read the 'responseText' property ... (was 'json')"
              // — so every XHR the app declared as JSON was being MISSED, which is the same defect
              // as the WebSocket blind spot in a second costume: a reader that can only handle one
              // representation reports silence for all the others.
              //
              // ⭐ It surfaced ONLY because the probe records what it could not read. That is the
              // whole argument for the `errors` array over a bare try/catch (NF1.7(a)).
              var body = null;
              var rt = "";
              try { rt = self.responseType || ""; } catch (e) {}
              if (rt === "" || rt === "text") {
                try {
                  if (typeof self.responseText === "string") body = self.responseText;
                } catch (e) { note("xhr-responseText", e); }
              } else if (rt === "json") {
                // Already parsed by the browser — re-serialize so the one shaping path downstream
                // stays the single implementation (⛔ never a second summarizer that could drift).
                try { body = JSON.stringify(self.response); } catch (e) { note("xhr-json", e); }
              }
              if (body === null && ct.indexOf("json") !== -1) {
                // Declared JSON but unreadable in every representation — RECORD THE FACT.
                recordCall("xhr", self.__credence_url, null);
                return;
              }
              recordCall("xhr", self.__credence_url, body);
            } catch (e) { note("xhr-load", e); }
          });
        } catch (e) { note("xhr-send", e); }
        return sendOrig.apply(this, arguments);
      };
    } catch (e) { note("installXhr", e); }

    // WebSocket — the likeliest carrier of live pick events.
    try {
      var OrigWS = window.WebSocket;
      if (typeof OrigWS === "function") {
        var WrappedWS = function (url, protocols) {
          var ws = protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
          try {
            recordCall("websocket-open", url, null);
            ws.addEventListener("message", function (ev) {
              try {
                var d = ev.data;
                if (typeof d === "string") { recordCall("websocket-msg", url, d); return; }
                // BINARY frame. Decode a bounded prefix so a custom/binary pick protocol is
                // legible; a Blob is async, an ArrayBuffer is not, so both are handled.
                if (d instanceof ArrayBuffer) {
                  recordCall("websocket-msg", url, decodePrefix(d));
                } else if (typeof Blob !== "undefined" && d instanceof Blob) {
                  d.arrayBuffer().then(function (buf) {
                    recordCall("websocket-msg", url, decodePrefix(buf));
                  }, function () { recordCall("websocket-msg", url, null); });
                } else {
                  recordCall("websocket-msg", url, null);
                }
              } catch (e) { note("ws-message", e); }
            });
          } catch (e) { note("ws-observe", e); }
          return ws;
        };
        WrappedWS.prototype = OrigWS.prototype;
        WrappedWS.CONNECTING = OrigWS.CONNECTING; WrappedWS.OPEN = OrigWS.OPEN;
        WrappedWS.CLOSING = OrigWS.CLOSING; WrappedWS.CLOSED = OrigWS.CLOSED;
        window.WebSocket = WrappedWS;
      }
    } catch (e) { note("installWs", e); }
  }

  // ── Tier C: rendered DOM text — LAST RESORT, and reported as brittle ──────────────────────────
  function scanDom() {
    try {
      var body = document.body ? document.body.innerText || "" : "";
      // Deliberately a WEAK, generic signal. A precise selector guessed without a real capture
      // would report a confident zero on a page whose class names simply differ — the failure mode
      // this spike is supposed to eliminate, not reproduce.
      var pickish = document.querySelectorAll('[class*="pick" i], [class*="Pick"]').length;
      return {
        available: !!document.body,
        pickLikeNodes: pickish,
        textBytes: body.length,
        brittle: true,
        note: "DOM text is a LAST-RESORT source: no version, no contract, breaks on any restyle."
      };
    } catch (e) { note("scanDom", e); return null; }
  }

  // ── Publish to the isolated world ─────────────────────────────────────────────────────────────
  function publish() {
    try {
      findings.globals = scanGlobals().concat(scanJsonScriptTags())
        .sort(function (a, b) { return b.score - a.score; }).slice(0, 12);
      findings.dom = scanDom();
      findings.observedAt = new Date().toISOString();
      window.postMessage({ __channel: CHANNEL, payload: findings }, "*");
    } catch (e) { note("publish", e); }
  }

  installNetworkObservers();          // FIRST — before the app can make its opening calls.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", publish);
  } else {
    publish();
  }
  // Re-publish as the room fills up; a draft's state arrives over time, so a single snapshot at
  // load would under-report the network tier badly.
  var ticks = 0;
  var timer = setInterval(function () {
    publish();
    if (++ticks > 120) clearInterval(timer);   // ~10 min at 5s, then stop.
  }, 5000);
})();
