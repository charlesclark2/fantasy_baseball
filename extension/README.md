# `extension/` — the Credence live-draft assistant (NF-C-LDA-1)

A Manifest V3 Chrome extension that overlays our pick recommendation on a live **ESPN** draft board.
It is **not** part of the Next.js app: it does not go through Vercel or
`infrastructure/lambda/deploy.sh`, and it is loaded unpacked by hand.

It began as NF-C-LDA-0's read PROBE — a feasibility spike that shipped no advice. That spike is
closed: the read is decoded, the resolution is measured, and this is the product built on it.

---

## The two red lines

### 1. Toward ESPN: **observe, never originate**

`docs/nf_c0_espn_access_probe.md` §3(c) refuses holding or replaying a user's `espn_s2` cookie — it
is not read-scoped, not individually revocable, has no consent screen and is long-lived, i.e.
functionally a password. Every reading here is a **passive wrapper over a call the page already
made**: response **bodies only**, never request headers (the one place `Cookie:`/`Authorization:`
appear), from a **fail-closed host allowlist** of two ESPN draft hosts.

⚠️ The overlay needs one thing the spike did not: it has to ask **our** API for a recommendation. So
the rule is kept where it actually bites — by **separating the contexts** rather than by relaxing it:

| script | runs where | may reach the network? |
|---|---|---|
| `src/main-world-probe.js` | ESPN's page context | **no** |
| `src/content.js`, `src/draft-state.js`, `src/overlay.js` | ESPN tab, isolated world | **no** |
| `src/background.js` | no page context, no ESPN host permission | `api.credencesports.com` only |
| `src/credence-auth.js` | our own origin only | **no** |

A request to ESPN is therefore not forbidden by convention: **the code that can see an ESPN page
cannot make one, and the code that can make one cannot see an ESPN page.**

### 2. Away from the browser: **only normalized data leaves**

`src/wire.js` is the single choke point, and it **rebuilds** the outbound body from an allowlist —
it never forwards, spreads or clones the state it was handed. That distinction is the guarantee: a
denylist is only as complete as the last thing someone remembered, and this codebase has been
surprised **three** separate times by a payload carrying something nobody expected (registerdisney's
`s2` + PII, the `responseType` blind spot, and the socket's `TOKEN 1:…:<draftSecurity>` handshake —
a *short signed integer*, under every length threshold). A rebuild cannot carry a field nobody knew
about.

What leaves: player identity (`id`, `fullName`, `proTeamId`, `defaultPositionId`, `eligibleSlots`),
the picks (`team`, `player`), the league's roster + scoring settings, and which team is yours.
**Never** a cookie, a header, a raw body, or a raw socket frame.

---

## How it reads a draft — measured, not chosen

```
SEED   the league payload once  →  pool + teams + settings + the 180-slot draft order
APPLY  wss://fantasydraft.espn.com deltas  →  SELECTED / SELECTING / AUTOSUGGEST / CLOCK
```

⛔ **Do not poll `draftDetail.picks[]`.** NF-C-LDA-0 proved the league endpoint is fetched **once**
at load and never re-polled, so `picks[]` never populates — it stays 180 empty slots all draft. A
design that polled it would read a permanently pre-draft snapshot: no error, no empty screen, just
confident advice about a draft that stopped four rounds ago.

## Everything that decides anything runs on the server

The extension ships **no board, no matcher and no ranker**. Position derivation, the board join and
the optimizer all live behind `POST /fantasy/nfl/draft-assistant`, each the *shipped*
implementation:

* position ← `platform_import.espn._player_position` (incl. the two-way-player fix)
* the join ← `league_scoring._join_key` (DST franchise resolution included) — **98.8%** on the
  committed real-league fixture, join-failure rate **0.0%**
* the ranking ← `fantasy_engine.draft.recommend`, pinned byte-for-byte to
  `frontend/lib/draft-optimizer.ts` by `betting_ml/tests/test_nf_c_lda_1_optimizer_parity.py`

A second copy of any of those in the browser would be free to drift, and a draft assistant that
recommends a different player from the website is the worst version of that — both answers look
right (E9.61).

## Break detection is a feature, not polish

A draft assistant fails inside a once-a-year two-hour window, and its characteristic failure is a
read that quietly stops advancing while the overlay keeps rendering advice that was true four picks
ago. **"We can't read your draft" and "nothing has happened yet" are otherwise pixel-identical.**

So the panel always states **which pick it is reasoning about** (compare it with ESPN's own counter
and a freeze is visible in one glance), the verdict is `OK` / `DEGRADED` / `BLOCKED` derived from
what was actually observed, each degraded state names itself (lobby ≠ stalled ≠ disconnected ≠
"we can't tell which team is yours"), and a **BLOCKED read shows no recommendations at all** — a
stale "best available" is wrong in exactly the way the user cannot check.

---

## Load it (operator)

1. Sign in at `credencesports.com` in any tab — that is where the extension picks up your session.
   The paid gate is enforced **server-side**; the extension only carries the token.
2. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** → this directory.
3. Open an ESPN draft room (`https://fantasy.espn.com/football/draft?...`).
4. The panel appears bottom-right. Before a capture is worth anything, check it reads **OK** and
   names a pick number.

⚠️ **A mock league is DELETED the moment the draft ends** (`LEAGUE_NOT_FOUND_DELETED`) — nothing can
be re-queried, so the overlay has to be debuggable from a **single live pass**. That is why every
failure carries a named reason on screen rather than in a console nobody will still have open.

⚠️ **`inProgress=true` and a `fantasydraft.espn.com` socket are the two preconditions** for anything
live to appear. An ESPN mock puts you in a LOBBY first; the socket opens only when the countdown
ends. The panel says "Waiting for your draft to start" for exactly that state, on purpose.

## Verify it (no browser needed)

```bash
node extension/tools/wire_red_proof.mjs      # nothing credential-shaped can leave  (+ its RED proof)
node extension/tools/state_red_proof.mjs     # broken never looks like quiet         (+ its RED proof)
uv run python extension/tools/red_proof.py   # all 35 guard clauses go red on a deliberate break
uv run python extension/tools/measure_resolution.py   # reproduce the 98.8% resolution figure
```

The first two drive the **real** JavaScript rather than inspecting its source, and that is
deliberate: this extension has already shipped a guard that asserted a string was present in the
source and passed for weeks over code that threw before it could run (NF-C4 — assert rendered
output, not source).
