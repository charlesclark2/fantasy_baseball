# `extension/` — Credence draft-read probe (NF-C-LDA-0 spike)

**This is a feasibility spike, not a product.** It answers two questions and ships nothing to a user:

1. Can we reliably READ the live ESPN draft state?
2. Can we RESOLVE the players it shows to OUR player ids?

It is a **new artifact type**: a Manifest V3 Chrome extension. It is **not** part of the Next.js app
and does **not** go through Vercel or `infrastructure/lambda/deploy.sh`. It is loaded unpacked, for
testing, by hand.

⛔ **Out of scope, deliberately:** the recommendation overlay, any call to our optimizer,
entitlement/auth, Sleeper, and Chrome Web Store packaging. Per the epic, recommendations will come
from **our API running the same optimizer** (one ranker) — never a copy bundled in the extension —
so nothing here ranks or advises.

## The red line

`docs/nf_c0_espn_access_probe.md` §3(c) refuses holding or replaying a user's `espn_s2` cookie.
This extension is the automated analogue of §3(d) (the user-mediated paste), and the property that
keeps it there is:

> **Observe, never originate.**

Every reading is a passive wrapper over a call the page already made. The extension issues no
`fetch`, constructs no `WebSocket`/`XMLHttpRequest`, reads no cookie, requests **zero** permissions,
and is host-scoped to the draft path alone. It reads **response bodies only** — never request
headers, which is the one place `Cookie:`/`Authorization:` appear.

`betting_ml/tests/test_nf_c_lda_0_extension_red_line.py` fails the build if that decays.
`extension/tools/red_proof.py` proves each clause goes red on its own deliberate break.

## Load it (operator)

1. Chrome → `chrome://extensions` → enable **Developer mode**.
2. **Load unpacked** → select this `extension/` directory.
3. Open an ESPN **mock draft** room (`https://fantasy.espn.com/football/draft?...`).
4. A small readout appears bottom-right: `OK` / `DEGRADED` / `BLOCKED`, plus counts.
5. Let several picks happen, then click **Copy capture JSON** and save it to
   `extension/captures/` (git-ignored — it describes a real league).

The capture is a **structural summary** (key names, shapes, small scalar samples) rather than the
league payload, so it can be reasoned about without carrying somebody's private league around.

## ⚠️ A mock league is DELETED when the draft ends

Measured 2026-08-18: the league URL returns `LEAGUE_NOT_FOUND_DELETED` afterwards. **Nothing can be
re-queried**, so the capture must be complete while the draft is live — that is why the probe
extracts pool identity rows rather than only a structural summary. Take the capture **30+ picks in**,
not at load: the first capture was 35 s old and its 180 pick slots were still empty.

The player POOL, by contrast, is league-independent and survives:

```bash
uv run python -c "from quant_sports_intel_models.football.nfl.fantasy import espn_source as E; E.fetch_espn_draftranks(2026)"
```

## What a capture settles

The capture names which of three sources exists, in the story's priority order:

| tier | source | verdict if it is what we get |
|---|---|---|
| A | in-page JSON state object | **go** — structured |
| B | draft-state network calls the room already makes | **go** — structured, and versioned by URL |
| C | rendered DOM text | **yellow flag** — brittle, no contract |

## Reproduce the resolution numbers

```bash
uv run python extension/tools/measure_resolution.py                    # name rung, no AWS needed
AWS_DEFAULT_REGION=us-east-2 uv run python extension/tools/measure_resolution.py --with-crosswalk
AWS_DEFAULT_REGION=us-east-2 uv run python extension/tools/measure_resolution.py --pool --with-crosswalk
uv run python extension/tools/red_proof.py                             # prove the guard can fail
```

⚠️ `--pool` reads `artifacts/espn_cache/espn_2026.json`, which is **gitignored** — so it is absent
from a fresh `git worktree` even when the main checkout has it (NF-INFRA1; this spike walked into it).
Pass an explicit path when running from a worktree.
