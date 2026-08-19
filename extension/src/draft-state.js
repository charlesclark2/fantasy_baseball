// NF-C-LDA-1 — the ISOLATED-world DRAFT STATE + READ VERDICT. Pure functions; no DOM, no network.
//
// ══ WHY BREAK DETECTION IS THE FIRST THING IN THIS FILE ═══════════════════════════════════════
// A draft assistant is used inside a once-a-year, two-hour window, and its characteristic failure
// is not a crash — it is a READ that quietly stops advancing while the overlay keeps rendering the
// recommendation that was true four picks ago. "We can no longer read your draft" and "nothing has
// happened yet" are otherwise PIXEL-IDENTICAL, and the wrong one of those is confidently wrong
// advice on a decision the user cannot take back.
//
// So the verdict is DERIVED FROM WHAT WAS OBSERVED, never assumed, and every degraded state names
// itself. An unreadable draft is a NAMED state, never an empty one (NF1.7(a): a check that could
// not run is not a check that passed).
//
// The three states are the spike's:
//   OK        — seeded, socket open, a frame seen recently. Advice is about the CURRENT pick.
//   DEGRADED  — we are reading something but not everything. Advice is shown WITH what is missing.
//   BLOCKED   — we cannot read this draft. NO advice is shown at all, and the reason is stated.
(function () {
  "use strict";

  //: How long a live socket may go quiet before the read is called stale. ESPN sends `CLOCK` ticks
  //: and `SELECTING` frames continuously while a draft runs, so ~25s of true silence on an open
  //: socket means the stream stopped, not that the room is calm. Deliberately generous: a false
  //: DEGRADED trains a user to ignore the badge, which is how a real one gets missed.
  var STALE_AFTER_MS = 25000;

  function ageMs(iso, now) {
    if (!iso) return null;
    var t = Date.parse(iso);
    return isNaN(t) ? null : Math.max(0, now - t);
  }

  /**
   * The read verdict, from the MAIN world's observations alone.
   *
   * ⛔ IT NEVER GUESSES UPWARD. Anything it could not establish is reported as a named gap, so a
   * verdict is only ever as good as what was actually seen.
   */
  function verdict(draft, now) {
    now = now || Date.now();
    var gaps = [];
    if (!draft) {
      return { level: "blocked", headline: "Waiting for the draft page…",
               detail: "The reader has not reported yet.", gaps: ["no_report"] };
    }

    // ── BLOCKED: without the pool we cannot name a single player, so we say nothing ────────────
    if (!draft.pool || !draft.pool.length) {
      return {
        level: "blocked",
        headline: "We can’t read this draft",
        detail: "ESPN’s player list hasn’t loaded here yet. If this stays up once your draft "
              + "board is on screen, ESPN has changed something and we are not reading it.",
        gaps: ["no_pool"]
      };
    }
    if (!draft.settings) gaps.push("no_settings");
    if (!draft.myTeam) gaps.push("no_my_team");

    // ── The stream ────────────────────────────────────────────────────────────────────────────
    var since = ageMs(draft.lastEventAt, now);
    if (!draft.socketOpen && !draft.picks.length) {
      // The pre-draft lobby: a real, expected state and NOT a break. Saying so explicitly is the
      // whole point — the spike lost two captures to "let 30 picks happen", which is not
      // actionable in a lobby where the socket has not opened yet.
      return {
        level: "degraded",
        headline: "Waiting for your draft to start",
        detail: "We can see your league and the player pool. Live picks appear here once ESPN "
              + "opens the draft room.",
        gaps: gaps.concat(["socket_not_open"])
      };
    }
    if (!draft.socketOpen) {
      return {
        level: "degraded",
        headline: "Live pick feed disconnected",
        detail: "We are showing the draft as of pick " + (draft.picks.length) + ". Anything picked "
              + "since then is missing. Reload the draft page to reconnect.",
        gaps: gaps.concat(["socket_closed"])
      };
    }
    if (since !== null && since > STALE_AFTER_MS) {
      return {
        level: "degraded",
        headline: "Pick feed has gone quiet",
        detail: "No update for " + Math.round(since / 1000) + "s. We are still showing the draft "
              + "as of pick " + draft.picks.length + " — treat it as possibly behind.",
        gaps: gaps.concat(["stale_stream"])
      };
    }
    if (gaps.length) {
      return {
        level: "degraded",
        headline: "Reading your draft",
        detail: gaps.indexOf("no_my_team") !== -1
          ? "We can’t tell which team is yours from this page, so we can’t fill your roster. "
          + "Recommendations below rank the board, not your needs."
          : "We are reading picks, but your league’s settings haven’t loaded yet.",
        gaps: gaps
      };
    }
    return {
      level: "ok",
      headline: "Reading your draft",
      detail: draft.picks.length + " picks seen",
      gaps: []
    };
  }

  /**
   * The overall pick number the advice is about — i.e. the pick ON THE CLOCK, which is one past
   * the last completed one.
   *
   * ⭐ SHOWN, NOT INFERRED. A user glancing between this number and ESPN's own pick counter can
   * see a frozen read in one second; nothing derivable from the recommendation itself can do that.
   */
  function currentOverallPick(draft) {
    if (!draft || !draft.picks) return null;
    return draft.picks.length + 1;
  }

  /** Is it MY turn? Unknown (null) is a third state, distinct from "no". */
  function onTheClockIsMe(draft) {
    if (!draft || !draft.myTeam || !draft.onTheClockTeam) return null;
    return String(draft.onTheClockTeam) === String(draft.myTeam);
  }

  /**
   * The state the background sends to our API. Built here so the shape is one object with one
   * definition; `wire.js` then re-derives the OUTBOUND payload from an allowlist, because a
   * serializer that trusts its input is not a boundary.
   */
  function requestState(draft, topN) {
    return {
      espn_settings: draft.settings || null,
      pool: draft.pool || [],
      picks: (draft.picks || []).map(function (p) { return { team: p.team, player: p.player }; }),
      my_team: draft.myTeam || null,
      on_the_clock_team: draft.onTheClockTeam || null,
      overall_pick: currentOverallPick(draft),
      top_n: topN || 8
    };
  }

  /**
   * Has anything changed that would change the ADVICE? Used to decide whether to re-ask the API.
   *
   * ⛔ NOT A TIMER. Polling a paid endpoint every second through a two-hour draft would be both
   * wasteful and, on the cost side, exactly the abuse profile G100-D1's guardrails were sized for.
   * The advice is a function of (picks made, whose turn it is, my roster) — so it is re-asked when
   * one of those moves, and not otherwise.
   */
  function adviceKey(draft) {
    if (!draft) return "none";
    return [
      (draft.picks || []).length,
      draft.onTheClockTeam || "-",
      draft.myTeam || "-",
      (draft.pool || []).length,
      draft.settings ? "s" : "-"
    ].join("|");
  }

  self.CredenceDraftState = {
    STALE_AFTER_MS: STALE_AFTER_MS,
    verdict: verdict,
    currentOverallPick: currentOverallPick,
    onTheClockIsMe: onTheClockIsMe,
    requestState: requestState,
    adviceKey: adviceKey
  };
})();
