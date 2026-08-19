// NF-C-LDA-1 — THE WIRE. The one place anything leaves this browser, and the shape it may take.
//
// ══ THE RED LINE, RESTATED FOR THE OUTBOUND DIRECTION ═════════════════════════════════════════
// NF-C-LDA-0's rule governs what we do to ESPN: OBSERVE, NEVER ORIGINATE. This file governs the
// other direction — what reaches US. The absolute constraint is:
//
//     ⛔ ONLY NORMALIZED DATA LEAVES: draft state and player identity. NEVER a session cookie,
//        never a request header, never a raw response body, never a raw socket frame.
//
// ⭐ IT IS AN ALLOWLIST, AND IT REBUILDS RATHER THAN FILTERS. Every field on the outbound payload
// is NAMED here and copied one at a time; the input object is never forwarded, never spread, never
// `JSON.parse(JSON.stringify(...))`-cloned. That distinction is the whole guarantee: a denylist or
// a "delete the bad keys" filter is only as complete as the last thing someone remembered, and this
// codebase has now been surprised THREE separate times by a payload carrying something nobody
// expected (registerdisney's `s2` + PII, the `responseType` blind spot, and the socket's
// `TOKEN 1:…:<draftSecurity>` line-protocol secret — a SHORT SIGNED INTEGER under every length
// threshold). A rebuild cannot carry a field nobody knew about, because it copies only what it
// names.
//
// ⛔ AND IT LIVES IN THE BACKGROUND, WHICH IS THE ONLY SCRIPT THAT CAN REACH THE NETWORK. Putting
// the serializer next to `fetch` means the boundary is one function in one file, rather than an
// invariant spread over whoever assembles a request.
//
// Guarded behaviourally, not by grep: `extension/tools/wire_red_proof.mjs` feeds this a state
// polluted with `espn_s2`, a `TOKEN` frame, raw bodies and a SWID, and asserts none of it survives
// — then deliberately breaks the allowlist and asserts the check goes red.
(function () {
  "use strict";

  //: Exactly the five identity fields ESPN publishes per player. They are its PUBLIC player
  //: universe — identical in every league — which is what makes forwarding them proportionate.
  //: ⛔ Position and team are NOT among them: the server derives both, so there is one position
  //: derivation in the product rather than two (`platform_import.espn._player_position`).
  var POOL_FIELDS = ["id", "fullName", "proTeamId", "defaultPositionId", "eligibleSlots"];

  //: A pick, reduced to the two ids the ranking needs. ⛔ NOT `slot`, and above all NOT the
  //: trailing SWID that marks the user's own pick — that field is consumed as the boolean `mine`
  //: in the reader and never travels.
  var PICK_FIELDS = ["team", "player"];

  //: The three settings sub-objects the SHIPPED league translation reads
  //: (`platform_import.espn.parse_settings_payload`). ESPN's `settings` block also carries
  //: `acquisitionSettings`, `draftSettings`, `isPublic` and member-facing names; none is read, so
  //: none is sent.
  var SETTINGS_FIELDS = ["name", "size", "rosterSettings", "scoringSettings"];

  //: Bounds, so a malformed or hostile page cannot turn this into a large upload. A real ESPN
  //: draftable pool measured 1,027 rows; a 12-team league drafts 180-240 players.
  var MAX_POOL = 4000;
  var MAX_PICKS = 1500;
  var MAX_SETTINGS_BYTES = 200000;

  function str(v) {
    return v === null || v === undefined ? null : String(v).slice(0, 120);
  }

  function num(v) {
    var n = typeof v === "number" ? v : parseInt(v, 10);
    return isFinite(n) ? n : null;
  }

  function poolRow(row) {
    if (!row || typeof row !== "object") return null;
    var id = str(row[POOL_FIELDS[0]]);
    if (!id) return null;
    var slots = [];
    if (Array.isArray(row.eligibleSlots)) {
      for (var i = 0; i < row.eligibleSlots.length && i < 40; i++) {
        var s = num(row.eligibleSlots[i]);
        if (s !== null) slots.push(s);
      }
    }
    return {
      id: id,
      fullName: str(row.fullName) || "",
      proTeamId: num(row.proTeamId),
      defaultPositionId: num(row.defaultPositionId),
      eligibleSlots: slots
    };
  }

  /**
   * ⛔ A DEPTH- AND SIZE-BOUNDED PLAIN-DATA COPY, used ONLY for the two settings sub-objects whose
   * inner shape ESPN owns (`rosterSettings.lineupSlotCounts` is a map; `scoringSettings.
   * scoringItems` is an array of records). Those are the one place a field-by-field allowlist is
   * not possible without re-implementing the league translation in the browser — which is the
   * second-implementation trap this whole design exists to avoid.
   *
   * So it is constrained instead of enumerated: scalars only at the leaves, bounded depth, bounded
   * width, and any key that has EVER been observed to carry identity or credential material is
   * dropped. The server then applies `assert_no_credentials` to the same payload before parsing it
   * — two independent refusals, neither relying on the other.
   */
  var FORBIDDEN_KEY = new RegExp(
    "^(s2|espn_s2|swid|SWID|cookie|authorization|auth|token|secret|credential|session|password"
    + "|email|parentEmail|firstName|lastName|middleName|displayName|dateOfBirth|gender|username"
    + "|phone|phones|addresses|members|owners|primaryOwner)$", "i");

  function plainData(value, depth) {
    if (depth > 6) return null;
    if (value === null || value === undefined) return null;
    var t = typeof value;
    if (t === "number" || t === "boolean") return value;
    if (t === "string") return value.slice(0, 200);
    if (Array.isArray(value)) {
      var arr = [];
      for (var i = 0; i < value.length && i < 400; i++) {
        var v = plainData(value[i], depth + 1);
        if (v !== null) arr.push(v);
      }
      return arr;
    }
    if (t !== "object") return null;          // function / symbol — never data
    var out = {};
    var keys = Object.keys(value);
    for (var k = 0; k < keys.length && k < 200; k++) {
      var key = keys[k];
      if (FORBIDDEN_KEY.test(key)) continue;
      var val = plainData(value[key], depth + 1);
      if (val !== null) out[key] = val;
    }
    return out;
  }

  function settings(raw) {
    if (!raw || typeof raw !== "object") return null;
    var out = {};
    for (var i = 0; i < SETTINGS_FIELDS.length; i++) {
      var key = SETTINGS_FIELDS[i];
      if (!(key in raw)) continue;
      var value = key === "name" ? str(raw[key])
                : key === "size" ? num(raw[key])
                : plainData(raw[key], 0);
      if (value !== null) out[key] = value;
    }
    if (!out.rosterSettings) return null;      // without a lineup there is nothing to rank against
    try {
      if (JSON.stringify(out).length > MAX_SETTINGS_BYTES) return null;
    } catch (e) { return null; }
    return out;
  }

  /**
   * A draft state → the request body. Returns `null` when the state cannot support a request, so
   * a caller can never accidentally post a half-built payload.
   */
  function buildPayload(state, season) {
    if (!state || typeof state !== "object") return null;

    var pool = [];
    var rawPool = Array.isArray(state.pool) ? state.pool : [];
    for (var i = 0; i < rawPool.length && pool.length < MAX_POOL; i++) {
      var row = poolRow(rawPool[i]);
      if (row) pool.push(row);
    }
    if (!pool.length) return null;

    var picks = [];
    var rawPicks = Array.isArray(state.picks) ? state.picks : [];
    for (var j = 0; j < rawPicks.length && picks.length < MAX_PICKS; j++) {
      var p = rawPicks[j];
      if (!p || typeof p !== "object") continue;
      var team = str(p[PICK_FIELDS[0]]);
      var player = str(p[PICK_FIELDS[1]]);
      if (team && player) picks.push({ team: team, player: player });
    }

    var body = {
      season: num(season) || 2026,
      espn_settings: settings(state.espn_settings),
      pool: pool,
      picks: picks,
      my_team: str(state.my_team),
      on_the_clock_team: str(state.on_the_clock_team),
      overall_pick: num(state.overall_pick),
      top_n: Math.max(1, Math.min(num(state.top_n) || 8, 50))
    };
    // The API takes EXACTLY ONE league source and rejects both-or-neither. Without settings there
    // is nothing to rank against, and guessing a preset would silently score the user's league
    // under rules that are not theirs.
    if (!body.espn_settings) return null;
    return body;
  }

  self.CredenceWire = {
    POOL_FIELDS: POOL_FIELDS,
    PICK_FIELDS: PICK_FIELDS,
    SETTINGS_FIELDS: SETTINGS_FIELDS,
    FORBIDDEN_KEY: FORBIDDEN_KEY,
    buildPayload: buildPayload
  };
})();
