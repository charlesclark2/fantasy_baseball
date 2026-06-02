# Runbook — FanGraphs Ingestion via FlareSolverr (Epic FG)

Operational procedures for the FanGraphs ingests after FanGraphs moved behind a
Cloudflare managed JavaScript challenge. Companion to [Implementation Guide](../implementation_guide.md)
Epic FG and the [signal-generation conventions](../../../CONTRIBUTING.md).

**Read first — the architecture in one paragraph:** Every request to
`https://www.fangraphs.com/*` returns HTTP 403 with header `cf-mitigated:
challenge` (a Cloudflare *managed JS challenge*). `curl_cffi` matches Chrome's
TLS fingerprint but cannot execute the challenge JS, so it cannot pass on its
own. We run **FlareSolverr** (a headless-Chromium solver) as a separate Railway
service. `scripts/utils/fangraphs_client.py` POSTs the page URL to FlareSolverr,
which solves the challenge and returns a `cf_clearance` cookie + the browser's
user-agent; the client then **replays that cookie + UA on fast `curl_cffi`
requests** for the actual JSON API calls. The challenge is solved **once per
process run** and reused for every call.

---

## 1. Topology & configuration

| Component | Where | Notes |
|---|---|---|
| FlareSolverr | Railway service, image `ghcr.io/flaresolverr/flaresolverr:latest` | Same project **and environment** as the Dagster agent (private DNS + shared egress) |
| `fangraphs_client` | Inside the Dagster agent image | Reads `FLARESOLVERR_URL`; called by all FanGraphs ingest scripts |

**FlareSolverr service env vars:**

```
HOST=::            # REQUIRED — bind IPv6; Railway private networking is IPv6-only
PORT=8191          # REQUIRED — pin the port; Railway auto-injects PORT=8080 otherwise
LOG_LEVEL=info
BROWSER_TIMEOUT=60000
TZ=America/New_York
```

**Dagster agent service env var:**

```
FLARESOLVERR_URL=http://flaresolverr.railway.internal:8191/v1
```

Do **not** give FlareSolverr a public domain — it is an open challenge-solving
proxy and must stay on the private network only. Budget ~1 GB RAM (Chromium).

---

## 2. Three gotchas we hit during deploy (2026-06-02) — check these first

1. **IPv6 binding.** Railway's private network is IPv6-only. FlareSolverr binds
   `0.0.0.0` (IPv4) by default → the agent's connection to the internal IPv6
   address is refused (`curl (7) ... Could not connect`). Fix: `HOST=::`.
   Confirm in FlareSolverr's startup log: `Serving on http://:::8191`.
2. **Port override.** Railway auto-injects `PORT=8080`, and FlareSolverr honors
   `PORT` over its own 8191 default → it serves on 8080 while `FLARESOLVERR_URL`
   points at 8191 → connection refused. Fix: set `PORT=8191` explicitly.
3. **`cf_clearance` IP binding.** The cookie is bound to the egress IP of the
   host that solved it **and** the returned user-agent. The agent (which replays
   the cookie) must share FlareSolverr's egress IP. On Railway this holds when
   both services are in the same project/region (verified working 2026-06-02 —
   clearance minted by FlareSolverr was accepted on the agent with no 403). If
   it ever stops holding, see §4.

---

## 3. Health check

FlareSolverr healthy startup log:

```
INFO  Serving on http://:::8191
INFO  FlareSolverr 3.5.0
```

End-to-end check (also restores data) — re-run the daily
`ingest_fangraphs_hitting_leaderboard` op in Dagster (it is *not* day-gated).
Healthy op log:

```
INFO  Solving Cloudflare challenge via FlareSolverr (https://www.fangraphs.com/leaders/major-league)
INFO  Cloudflare clearance obtained (N cookies)
INFO  fetch_leaderboard: stats=bat type=8 season=YYYY ... → N rows
INFO  Appended N rows to baseball_data.fangraphs.fg_hitting_leaderboard_raw
```

The matching FlareSolverr log shows `Challenge detected` → `Challenge solved!`
→ `200 OK`.

---

## 4. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `curl (7) Could not connect to flaresolverr.railway.internal:8191` | FlareSolverr on IPv4 or wrong port | Check its startup log; ensure `HOST=::` and `PORT=8191`; redeploy. |
| Hostname won't resolve at all | Services in different Railway environments | Move both to the same environment; private DNS is per-environment. |
| Connects + `Challenge solved!` in FlareSolverr, but the op gets a **persistent 403 after a `re-solving Cloudflare challenge` line** | `cf_clearance` IP mismatch — agent and FlareSolverr egress from different IPs | Give both a shared static egress IP, **or** switch the client to route data calls *through* FlareSolverr (proxy mode — see Epic FG fallback). |
| FlareSolverr log: `Challenge detected` then a **captcha / Turnstile interactive** prompt it can't solve | Cloudflare *escalated* from managed challenge to interactive captcha | FlareSolverr cannot solve interactive captchas. Escalate: add a captcha-solver (`CAPTCHA_SOLVER` env) or revisit the managed-bypass-API option. This is a step-change, not a transient. |
| FlareSolverr restarting / OOM in deploy logs | Chromium memory ceiling | Bump service memory toward ~1 GB (Settings → Resources). |
| `FangraphsClientError: ... FLARESOLVERR_URL is not configured` | Env var missing on the agent | Set `FLARESOLVERR_URL` on the Dagster agent service. |

**Transient vs. step-change:** a one-off solve timeout or 5xx is transient — the
client already retries 3× and re-solves once. A *consistent* failure that shows
an interactive captcha in FlareSolverr's logs is an escalation and needs a
solver upgrade, not a retry.

---

## 5. Dependent ingests & cadence

| Ingest | Cadence | Path |
|---|---|---|
| `ingest_fangraphs_hitting_leaderboard.py` | **Daily** (in `daily_ingestion_job`, no gate) | `fetch_leaderboard` (type 8) |
| `ingest_fangraphs_stuff_plus.py` | **Weekly** (Sunday-gated op in `daily_ingestion_job`) | `fetch_leaderboard` (type 36) |
| `ingest_fangraphs_zips_pitching.py` | **Manual / preseason** (not orchestrated) | `fetch_projections` |
| `ingest_fangraphs_zips_hitting.py` | **Manual / preseason** (not orchestrated) | `fetch_projections` |

`ingest_savant_park_factors.py` and `ingest_oaa.py` hit Baseball Savant (no
Cloudflare challenge) and do **not** depend on FlareSolverr.

When running a FanGraphs ingest **locally**, set `FLARESOLVERR_URL` to a local
FlareSolverr (`docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr` →
`http://localhost:8191/v1`); without it the client raises a clear config error.

---

## 6. Monitoring

There is no FanGraphs-specific alert yet — a silent block surfaced only because
a downstream feature looked stale. Closing that gap is owned by the separate
ingestion/signal staleness-alerting story; cross-linked here so a future
FanGraphs outage is caught by freshness checks rather than by inspection.
