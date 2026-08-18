// NF-C-LDA-0 — ISOLATED-world half of the read probe.
//
// Receives the MAIN world's findings and renders a small status readout with a "copy capture"
// button, so the operator's mock draft produces a FILE we can reason about afterwards.
//
// ⚠️ THIS IS A PROBE READOUT, NOT THE RECOMMENDATION OVERLAY. The overlay is explicitly out of
// this spike's scope and is designed OFF this spike's verdict; per the epic its recommendations
// come from OUR API running the SAME optimizer (one ranker), never a copy bundled here. Nothing
// in this file ranks, scores, or advises — it reports what the page exposed.
//
// It also sends nothing anywhere: no `fetch`, no host beyond the ESPN tab, no storage. The capture
// reaches us only if the operator copies it and hands it over — the same user-mediated shape as
// the §3(d) paste flow.
(function () {
  "use strict";

  var CHANNEL = "__credence_draft_probe__";
  var latest = null;

  window.addEventListener("message", function (ev) {
    if (ev.source !== window) return;
    var d = ev.data;
    if (!d || d.__channel !== CHANNEL) return;
    latest = d.payload;
    render(latest);
  });

  // ── BREAK DETECTION ───────────────────────────────────────────────────────────────────────────
  // ⭐ The spike's question 5. The requirement is that the extension can tell "ESPN changed and we
  // can no longer read it" from "we read it fine and there is nothing to say" — because those two
  // are otherwise pixel-identical to a user, and the failure mode is showing stale or empty state
  // as if it were live (the E9.46/NF-K1 "a confidently wrong number renders perfectly" class).
  //
  // So the verdict is derived from what was ACTUALLY observed, never assumed, and an unreadable
  // state is a NAMED state rather than an empty one (NF1.7(a): a check that could not run is not
  // a pass).
  function verdict(f) {
    if (!f) return { level: "unknown", label: "probe has not reported yet" };
    var bestGlobal = (f.globals && f.globals[0]) || null;
    var netHits = (f.network || []).filter(function (n) { return n.score > 0; });
    if (netHits.length) {
      return { level: "ok", label: "structured source: " + netHits.length +
               " draft-shaped response(s) observed", detail: netHits[0].url };
    }
    if (bestGlobal && bestGlobal.score >= 3) {
      return { level: "ok", label: "structured source: in-page state at " + bestGlobal.path,
               detail: "score " + bestGlobal.score };
    }
    if (f.dom && f.dom.pickLikeNodes > 0) {
      return { level: "degraded", label: "DOM-text only — brittle, no structured source found",
               detail: f.dom.pickLikeNodes + " pick-like nodes" };
    }
    return { level: "blocked", label: "cannot read this draft right now", detail: "no source found" };
  }

  var box = null;
  function ensureBox() {
    if (box) return box;
    box = document.createElement("div");
    box.id = "credence-draft-probe";
    box.setAttribute("style", [
      "position:fixed", "right:12px", "bottom:12px", "z-index:2147483647",
      "max-width:340px", "font:12px/1.45 ui-sans-serif,system-ui,sans-serif",
      "background:#111827", "color:#f9fafb", "border:1px solid #374151",
      "border-radius:10px", "padding:10px 12px", "box-shadow:0 6px 24px rgba(0,0,0,.35)"
    ].join(";"));
    document.documentElement.appendChild(box);
    return box;
  }

  function render(f) {
    var v = verdict(f);
    var el = ensureBox();
    var colour = v.level === "ok" ? "#34d399" : v.level === "degraded" ? "#fbbf24" : "#f87171";
    el.textContent = "";

    var h = document.createElement("div");
    h.setAttribute("style", "font-weight:600;margin-bottom:4px;color:" + colour);
    h.textContent = "Credence read probe — " + v.level.toUpperCase();
    el.appendChild(h);

    var p = document.createElement("div");
    p.setAttribute("style", "margin-bottom:6px;");
    p.textContent = v.label + (v.detail ? " (" + v.detail + ")" : "");
    el.appendChild(p);

    var stats = document.createElement("div");
    stats.setAttribute("style", "color:#9ca3af;margin-bottom:8px;");
    stats.textContent = "globals " + ((f.globals || []).length) +
      " · network " + ((f.network || []).length) +
      " · dom-nodes " + ((f.dom && f.dom.pickLikeNodes) || 0);
    el.appendChild(stats);

    var btn = document.createElement("button");
    btn.setAttribute("style",
      "background:#2563eb;color:#fff;border:0;border-radius:6px;padding:5px 9px;cursor:pointer;font:inherit");
    btn.textContent = "Copy capture JSON";
    btn.addEventListener("click", function () {
      var text = JSON.stringify(latest, null, 2);
      navigator.clipboard.writeText(text).then(
        function () { btn.textContent = "Copied (" + text.length + " bytes)"; },
        function () { btn.textContent = "Copy failed — see console"; console.log(text); }
      );
    });
    el.appendChild(btn);
  }

  render(null);
})();
