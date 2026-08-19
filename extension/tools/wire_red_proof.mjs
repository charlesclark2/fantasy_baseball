// NF-C-LDA-1 — THE WIRE'S BEHAVIOURAL PROOF, and the deliberate-break run that shows it can fail.
//
// ══ WHY THIS IS BEHAVIOURAL AND NOT A grep ════════════════════════════════════════════════════
// The NF-C-LDA-0 suite proves things about the extension's SOURCE, which is right for "this file
// contains no call to `fetch`". It is the wrong instrument for "no credential can leave", because
// the question is what a function DOES with a hostile input, and this repo has already paid for
// exactly that gap: `test_an_off_allowlist_body_is_recorded_as_REFUSED_not_as_unreadable` asserted
// the string `bodyNotRead` appears in the source and passed for weeks over code that threw a
// TypeError before it could ever run (the write referenced `entry` above its own `var`). The source
// said the right thing; the behaviour was absent. NF-C4's rule, verbatim: assert RENDERED output,
// not source.
//
// So this loads `extension/src/wire.js` for real and drives it with a draft state polluted with
// every credential-shaped thing a capture has ACTUALLY carried:
//
//   * `espn_s2` and a SWID          — registerdisney's response body (spike §12)
//   * a `TOKEN 1:…:<draftSecurity>` — the socket's line-protocol handshake (spike §14.4), a SHORT
//                                     SIGNED INTEGER under every length threshold
//   * raw response bodies, request headers, a Cookie header
//   * PII (email, dateOfBirth, firstName/lastName), captured verbatim once already
//
// …and asserts none of it appears anywhere in the serialized request body.
//
// Run:  node extension/tools/wire_red_proof.mjs          (exit 0 = the wire holds and can fail)
//
// It is invoked by `betting_ml/tests/test_nf_c_lda_1_extension_wire.py`, which FAILS rather than
// SKIPS when node is unavailable — a check that could not run is not a check that passed
// (NF1.7(a)).
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WIRE = path.join(ROOT, "src/wire.js");

/** Load `wire.js` in a sandbox that supplies the `self` a service worker would. */
function loadWire(source) {
  const sandbox = { self: {} };
  vm.createContext(sandbox);
  new vm.Script(source, { filename: "wire.js" }).runInContext(sandbox);
  if (!sandbox.self.CredenceWire) throw new Error("wire.js did not export CredenceWire");
  return sandbox.self.CredenceWire;
}

// ── The hostile state ───────────────────────────────────────────────────────────────────────────
const SECRETS = [
  "AEBmarPuDdT1x9K7session",              // an espn_s2-shaped value
  "{3F2504E0-4F89-11D3-9A0C-0305E82C3301}", // a SWID
  "-1049606073",                           // the draftSecurity join token (a short signed int)
  "eyJraWQiOiJhYmMi.eyJzdWIiOiIxIn0.sig",  // a bearer JWT
  "someone@example.com",
  "1991-04-02",
];

function hostileState() {
  return {
    // Legitimate content, which MUST survive.
    espn_settings: {
      name: "Sunday Money",
      size: 12,
      rosterSettings: { lineupSlotCounts: { 0: 1, 2: 2, 4: 2, 6: 1, 23: 1, 16: 1, 17: 1, 20: 6 } },
      scoringSettings: { scoringItems: [{ statId: 42, points: 0.04 }, { statId: 43, points: 4 }] },
      // …and things that must not.
      draftSettings: { token: SECRETS[2] },
      members: [{ id: SECRETS[1], email: SECRETS[4], dateOfBirth: SECRETS[5] }],
    },
    pool: [
      {
        id: 4685415, fullName: "Travis Hunter", proTeamId: 30, defaultPositionId: 3,
        eligibleSlots: [3, 4, 5, 23, 7, 20, 21, 12, 14, 15],
        // Fields ESPN really ships on a pool row, none of which we send.
        ownership: { percentOwned: 99.1 }, stats: [{ appliedTotal: 210 }],
        swid: SECRETS[1], espn_s2: SECRETS[0],
      },
      { id: 3116385, fullName: "Joe Mixon", proTeamId: 34, defaultPositionId: 2, eligibleSlots: [2, 3, 23, 7] },
    ],
    picks: [
      { team: "14", player: "4685415", slot: "4", mine: true, swid: SECRETS[1] },
      { team: "3", player: "3116385", slot: "2", mine: false },
    ],
    my_team: "14",
    on_the_clock_team: "3",
    overall_pick: 31,
    top_n: 8,
    // Things a careless refactor might attach to the state object.
    rawFrames: ["TOKEN 1:642070:14:" + SECRETS[1] + ":" + SECRETS[2], "SELECTED 14 4685415 4"],
    responseBodies: [{ url: "https://registerdisney.go.com/guest", body: { s2: SECRETS[0] } }],
    requestHeaders: { Cookie: "espn_s2=" + SECRETS[0], Authorization: "Bearer " + SECRETS[3] },
    cookie: "espn_s2=" + SECRETS[0],
  };
}

const checks = [];
function check(name, fn) {
  try {
    fn();
    checks.push([name, true, ""]);
  } catch (e) {
    checks.push([name, false, String((e && e.message) || e)]);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const source = fs.readFileSync(WIRE, "utf8");
const wire = loadWire(source);
const body = wire.buildPayload(hostileState(), 2026);
const serialized = JSON.stringify(body);

check("a payload is produced at all (else every leak clause is vacuous)", () => {
  assert(body && typeof body === "object", "buildPayload returned nothing");
  assert(serialized.length > 200, `payload is only ${serialized.length} bytes`);
});

check("no secret or PII value survives serialization", () => {
  for (const secret of SECRETS) {
    assert(!serialized.includes(secret), `the wire leaked ${JSON.stringify(secret)}`);
  }
});

check("no credential-shaped KEY survives", () => {
  for (const key of ["swid", "espn_s2", "cookie", "Cookie", "Authorization", "authorization",
                     "token", "members", "email", "dateOfBirth", "requestHeaders",
                     "responseBodies", "rawFrames"]) {
    assert(!serialized.includes(`"${key}"`), `the wire leaked the key "${key}"`);
  }
});

check("a raw socket frame never travels", () => {
  assert(!serialized.includes("TOKEN"), "a raw TOKEN frame reached the wire");
  assert(!serialized.includes("SELECTED"), "a raw socket frame reached the wire");
});

check("the pool carries exactly the five identity fields", () => {
  assert(body.pool.length === 2, `expected 2 pool rows, got ${body.pool.length}`);
  for (const row of body.pool) {
    const keys = Object.keys(row).sort();
    assert(
      keys.join(",") === [...wire.POOL_FIELDS].sort().join(","),
      `pool row carries ${keys.join(",")}`,
    );
  }
});

check("a pick carries only the two ids — never the slot or the ownership marker", () => {
  for (const p of body.picks) {
    assert(Object.keys(p).sort().join(",") === "player,team", `pick carries ${Object.keys(p)}`);
  }
});

check("the legitimate content DOES survive (a wire that sends nothing is not a wire)", () => {
  assert(body.espn_settings, "settings were dropped");
  assert(body.espn_settings.rosterSettings, "rosterSettings were dropped");
  assert(body.espn_settings.scoringSettings, "scoringSettings were dropped");
  assert(body.my_team === "14", "my_team was dropped");
  assert(body.overall_pick === 31, "overall_pick was dropped");
  assert(serialized.includes("Travis Hunter"), "a player name was dropped");
});

check("a state with no settings produces NO request rather than a guessed league", () => {
  const s = hostileState();
  s.espn_settings = null;
  assert(wire.buildPayload(s, 2026) === null, "a settings-less state still produced a payload");
});

check("a state with no pool produces NO request", () => {
  const s = hostileState();
  s.pool = [];
  assert(wire.buildPayload(s, 2026) === null, "an empty-pool state still produced a payload");
});

// ── THE RED PROOF: break the allowlist and confirm the leak clause FIRES ───────────────────────
// ⚠️ THE MUTATION IS ASSERTED TO HAVE LANDED, AND THE TOKEN IS ASSERTED GONE. A break that silently
// no-ops reports "the guard caught it" when nothing was ever broken (#682), and one that lands
// without changing the asserted predicate is the same false green a level finer (#815).
check("RED PROOF — a rebuild replaced by a passthrough leaks, and this suite says so", () => {
  const anchor = "    return {\n      id: id,";
  assert(source.split(anchor).length === 2, "the red-proof anchor is not unique in wire.js");
  const broken = source.replace(anchor, "    return {\n      ...row,\n      id: id,");
  assert(broken !== source, "the mutation did not change the source");
  assert(broken.includes("...row,"), "the mutation did not land");

  const brokenWire = loadWire(broken);
  const leaked = JSON.stringify(brokenWire.buildPayload(hostileState(), 2026));
  const caught = SECRETS.some((s) => leaked.includes(s)) || leaked.includes('"swid"');
  assert(caught, "the allowlist was replaced by a passthrough and NOTHING leaked — this suite " +
                 "cannot detect the defect it exists to detect");
});

let failed = 0;
for (const [name, ok, why] of checks) {
  if (!ok) failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : `\n        ${why}`}`);
}
console.log(`\n${checks.length - failed}/${checks.length} wire clauses passed`);
process.exit(failed ? 1 : 0);
