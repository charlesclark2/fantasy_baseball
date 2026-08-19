// NF-C-LDA-1 — BREAK DETECTION, proven behaviourally.
//
// ══ THE PROPERTY ══════════════════════════════════════════════════════════════════════════════
// "We can't read your draft" must NEVER render the same as "nothing has happened yet."
//
// That is the story's ⭐ requirement rather than polish, because a draft assistant fails inside a
// once-a-year two-hour window and its characteristic failure is a read that quietly stops
// advancing while the overlay keeps rendering the recommendation that was true four picks ago. A
// user cannot tell those apart by looking at advice — both are a panel with a name in it.
//
// A source-inspection guard cannot check this: the verdict is a FUNCTION OF OBSERVED STATE, and the
// question is which state produces which answer. So this drives the real `draft-state.js` through
// the states a live draft actually passes through — lobby, running, stalled, disconnected,
// unidentified team, unreadable page — and asserts each gets a DISTINGUISHABLE verdict.
//
// Run:  node extension/tools/state_red_proof.mjs
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src/draft-state.js");

function load(source) {
  const sandbox = { self: {} };
  vm.createContext(sandbox);
  new vm.Script(source, { filename: "draft-state.js" }).runInContext(sandbox);
  if (!sandbox.self.CredenceDraftState) throw new Error("draft-state.js exported nothing");
  return sandbox.self.CredenceDraftState;
}

const NOW = 1_770_000_000_000;
const iso = (msAgo) => new Date(NOW - msAgo).toISOString();

const pool = [{ id: "1", fullName: "A", proTeamId: 1, defaultPositionId: 2, eligibleSlots: [2] }];
const settings = { rosterSettings: {}, scoringSettings: {} };

const STATES = {
  // The page has not reported at all.
  no_report: null,
  // Reported, but ESPN's player list never arrived — we genuinely cannot name a player.
  unreadable: { pool: [], picks: [], socketOpen: false },
  // The pre-draft LOBBY. A real, expected state — the spike lost two captures to not knowing this.
  lobby: { pool, settings, myTeam: "14", picks: [], socketOpen: false, lastEventAt: null },
  // Running normally.
  live: { pool, settings, myTeam: "14", picks: [{ team: "3", player: "9" }], socketOpen: true,
          lastEventAt: iso(2000), onTheClockTeam: "14" },
  // Running, but the stream stopped — the failure this whole file exists for.
  stalled: { pool, settings, myTeam: "14", picks: [{ team: "3", player: "9" }], socketOpen: true,
             lastEventAt: iso(120000), onTheClockTeam: "3" },
  // The socket dropped mid-draft.
  disconnected: { pool, settings, myTeam: "14", picks: [{ team: "3", player: "9" }],
                  socketOpen: false, lastEventAt: iso(3000) },
  // Reading picks fine, but we cannot tell which team is the user's.
  no_my_team: { pool, settings, myTeam: null, picks: [{ team: "3", player: "9" }],
                socketOpen: true, lastEventAt: iso(2000) },
};

const checks = [];
const check = (name, fn) => {
  try { fn(); checks.push([name, true, ""]); }
  catch (e) { checks.push([name, false, String((e && e.message) || e)]); }
};
const assert = (c, m) => { if (!c) throw new Error(m); };

const source = fs.readFileSync(SRC, "utf8");
const S = load(source);
const verdicts = Object.fromEntries(
  Object.entries(STATES).map(([k, v]) => [k, S.verdict(v, NOW)]),
);

check("every state produces a verdict with a level and a headline", () => {
  for (const [name, v] of Object.entries(verdicts)) {
    assert(v && v.level && v.headline, `${name} produced ${JSON.stringify(v)}`);
    assert(["ok", "degraded", "blocked"].includes(v.level), `${name} level=${v.level}`);
  }
});

check("⭐ A STALLED READ IS NOT THE SAME VERDICT AS A QUIET LOBBY", () => {
  assert(verdicts.stalled.headline !== verdicts.lobby.headline,
    "a stopped stream and a pre-draft lobby produce the SAME headline — the exact ambiguity this " +
    "story exists to remove");
  assert(verdicts.stalled.gaps.includes("stale_stream"), "the stall is not named as a gap");
  assert(verdicts.lobby.gaps.includes("socket_not_open"), "the lobby is not named as a gap");
});

check("⭐ A STALLED READ IS NOT THE SAME VERDICT AS A HEALTHY ONE", () => {
  assert(verdicts.live.level === "ok", `a healthy read scored ${verdicts.live.level}`);
  assert(verdicts.stalled.level !== "ok", "a stopped stream still reads OK");
});

check("a stalled read SAYS HOW LONG and WHICH PICK it is stuck at", () => {
  const d = verdicts.stalled.detail;
  assert(/\d+s/.test(d), `the stall detail names no elapsed time: ${d}`);
  assert(/pick \d+/.test(d), `the stall detail names no pick number: ${d}`);
});

check("an unreadable page BLOCKS rather than degrading — no advice may be shown", () => {
  assert(verdicts.unreadable.level === "blocked", "an empty pool did not block");
  assert(verdicts.no_report.level === "blocked", "an absent report did not block");
});

check("a disconnected socket is distinguishable from a stalled one", () => {
  assert(verdicts.disconnected.headline !== verdicts.stalled.headline,
    "a dropped socket and a quiet one read identically");
  assert(verdicts.disconnected.gaps.includes("socket_closed"));
});

check("an unknown team is NAMED, not silently rendered as an empty roster", () => {
  assert(verdicts.no_my_team.gaps.includes("no_my_team"), "no_my_team is not reported as a gap");
  assert(verdicts.no_my_team.level === "degraded", "an unidentified team scored as fully healthy");
  assert(/team is yours/i.test(verdicts.no_my_team.detail), "the detail does not say what is wrong");
});

check("the pick echo is the pick ON THE CLOCK, one past the last completed one", () => {
  assert(S.currentOverallPick(STATES.live) === 2, "pick echo is wrong for 1 completed pick");
  assert(S.currentOverallPick(STATES.lobby) === 1, "a lobby should be reasoning about pick 1");
  assert(S.currentOverallPick(null) === null, "an absent state must not invent a pick number");
});

check("whose-turn-is-it has THREE states, not two", () => {
  assert(S.onTheClockIsMe(STATES.live) === true, "my own turn was not recognised");
  assert(S.onTheClockIsMe(STATES.stalled) === false, "another team's turn read as mine");
  assert(S.onTheClockIsMe(STATES.no_my_team) === null,
    "an UNKNOWN turn collapsed to `false` — 'not your pick' and 'we don't know' are different");
});

check("the advice key moves when the draft moves, and not otherwise", () => {
  const a = S.adviceKey(STATES.live);
  assert(a === S.adviceKey(STATES.live), "the advice key is not stable for an unchanged state");
  const moved = { ...STATES.live, picks: [...STATES.live.picks, { team: "5", player: "7" }] };
  assert(S.adviceKey(moved) !== a, "a new pick did not change the advice key");
  const turn = { ...STATES.live, onTheClockTeam: "9" };
  assert(S.adviceKey(turn) !== a, "a change of turn did not change the advice key");
});

// ── THE RED PROOF ─────────────────────────────────────────────────────────────────────────────
check("RED PROOF — remove the staleness check and this suite says so", () => {
  const anchor = "if (since !== null && since > STALE_AFTER_MS) {";
  assert(source.split(anchor).length === 2, "the red-proof anchor is not unique");
  const broken = source.replace(anchor, "if (false) {");
  assert(broken !== source && !broken.includes(anchor), "the mutation did not land");
  const brokenState = load(broken);
  const v = brokenState.verdict(STATES.stalled, NOW);
  assert(v.level === "ok",
    "the staleness check was deleted and the stalled state still did not read as healthy — the " +
    "clause above may be passing for a different reason than it claims");
});

let failed = 0;
for (const [name, ok, why] of checks) {
  if (!ok) failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : `\n        ${why}`}`);
}
console.log(`\n${checks.length - failed}/${checks.length} break-detection clauses passed`);
process.exit(failed ? 1 : 0);
