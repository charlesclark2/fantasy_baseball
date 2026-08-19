// NF-C-LDA-1 — the ISOLATED-world ORCHESTRATOR: take the reader's draft state, keep the verdict
// current, ask the background for advice when (and only when) the advice could have changed, and
// render.
//
// ⛔ IT ORIGINATES NOTHING. No `fetch`, no `WebSocket`, no `XMLHttpRequest` — it talks to the
// background worker over `chrome.runtime` and to the page's MAIN world over `postMessage`. The
// background is the only script with network access and it can only reach `api.credencesports.com`
// (see `background.js` for why the contexts are split rather than the rule being a convention).
//
// ⭐ THE VERDICT IS RE-RENDERED ON A CLOCK, NOT ONLY ON AN EVENT. That is the difference between
// an overlay that can report a break and one that cannot: a stream that STOPS produces no event by
// definition, so anything that only redraws on arrival goes quiet exactly when it most needs to
// speak (NF1.7(a), on a UI).
(function () {
  "use strict";

  var DRAFT_CHANNEL = "__credence_draft_state__";
  var SEASON = 2026;

  var draft = null;
  var lastAdviceKey = null;
  var view = {
    verdict: { level: "blocked", headline: "Waiting for the draft page…", detail: "", gaps: [] },
    pickNumber: null,
    onTheClockIsMe: null,
    data: null,
    message: null
  };

  function refreshVerdict() {
    view.verdict = self.CredenceDraftState.verdict(draft, Date.now());
    view.pickNumber = self.CredenceDraftState.currentOverallPick(draft);
    view.onTheClockIsMe = self.CredenceDraftState.onTheClockIsMe(draft);
    self.CredenceOverlay.render(view);
  }

  function askForAdvice() {
    if (!draft) return;
    // ⛔ NEVER WHILE BLOCKED. Asking for a recommendation we could not attach to a pick would spend
    // a paid request to produce advice the overlay is not going to show.
    if (view.verdict.level === "blocked") return;

    var key = self.CredenceDraftState.adviceKey(draft);
    if (key === lastAdviceKey) return;      // nothing that could change the advice has moved
    lastAdviceKey = key;

    var state = self.CredenceDraftState.requestState(draft, 8);
    try {
      chrome.runtime.sendMessage(
        { type: "CREDENCE_RECOMMEND", state: state, season: SEASON },
        function (res) {
          if (chrome.runtime.lastError) {
            view.message = "Extension was reloaded — refresh this page.";
            refreshVerdict();
            return;
          }
          if (!res || !res.ok) {
            // ⭐ A FAILED FETCH MUST NOT LEAVE STALE ADVICE ON SCREEN LOOKING CURRENT. Keeping the
            // last successful recommendation while the pick number moves on is precisely the
            // "confidently stale" shape this story is against — so the data is cleared and the
            // named reason is shown in its place.
            if (res && res.reason === "busy") { lastAdviceKey = null; return; }
            view.data = null;
            view.message = (res && res.message) || "Couldn’t reach Credence.";
            lastAdviceKey = null;           // let the next tick retry
            refreshVerdict();
            return;
          }
          view.data = res.data;
          view.message = null;
          refreshVerdict();
        }
      );
    } catch (e) {
      view.message = "Extension context is gone — refresh this page.";
      refreshVerdict();
    }
  }

  window.addEventListener("message", function (ev) {
    if (ev.source !== window) return;
    var d = ev.data;
    if (!d || d.__channel !== DRAFT_CHANNEL) return;
    draft = d.payload;
    refreshVerdict();
    askForAdvice();
  });

  // The heartbeat. Cheap (a verdict is arithmetic over an object we already hold) and the only
  // thing that can notice a stream which stopped.
  setInterval(function () {
    refreshVerdict();
    askForAdvice();
  }, 3000);

  refreshVerdict();
})();
