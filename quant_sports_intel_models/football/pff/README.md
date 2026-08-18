# PFF probe (NF-W9-0) — operator runbook

Research only. `best_alpha = 0`. No serving path, nothing published.

## What the operator must supply

PFF is a paid subscription behind login. **This client never attempts to bypass auth** — it
replays a credential you capture from your own logged-in session.

Capture it once, from a browser logged into PFF:

1. Open PFF, DevTools → **Network**, filter `api/v1`.
2. Click anything that loads data (a game page). Pick a `/api/v1/…` request.
3. From **Request Headers** copy **either**:
   * `authorization: Bearer …` → the value after `Bearer ` is `PFF_AUTH_TOKEN`, **or**
   * `cookie: …` → the whole line's value is `PFF_COOKIE`.

Both is best: the `direct` transport prefers the token; `flaresolverr` can only replay a cookie
(its headless browser cannot send an `Authorization` header).

> Tokens expire. If a run reports `PFFAuthError`, re-capture — that error means *the credential
> was rejected*, and it is deliberately distinct from `PFFChallengeError` (Cloudflare) so you
> know which one to act on.

## Run the probe — **LAPTOP** (not the box; needs no box-only state, and reads the S3 lake)

```bash
cd /path/to/your/worktree

export PFF_AUTH_TOKEN='<paste the bearer token>'
export PFF_COOKIE='<paste the whole cookie header>'      # optional but recommended
export AWS_DEFAULT_REGION=us-east-2                      # DuckDB-S3 lake reads

uv run python -m quant_sports_intel_models.football.pff.probe \
    --league nfl,ncaa \
    --season 2024 \
    --weeks 1,2 \
    --out ablation_results/nf_w9_0
```

Runtime: a few minutes (2 leagues × 2 weeks × ~4 facets per game). It writes
`ablation_results/nf_w9_0/nf_w9_0_probe_report.json` plus one small parquet per league.

**If Cloudflare challenges the direct call** (`PFFChallengeError`), rerun through the existing
FanGraphs solver — this needs the cookie, not the token:

```bash
export PFF_TRANSPORT=flaresolverr
export FLARESOLVERR_URL='http://localhost:8191/v1'   # or the box's flaresolverr
export PFF_COOKIE='<paste the whole cookie header>'
uv run python -m quant_sports_intel_models.football.pff.probe \
    --league nfl,ncaa --season 2024 --weeks 1,2 --out ablation_results/nf_w9_0
```

### Alternative: hand over captured JSON instead of a credential

If you would rather not share a token, capture two responses (DevTools → the request → **Copy
response**) and save them with these exact names:

```
api_v1_games__league-nfl__season-2024__week-1.json
api_v1_facet_rushing_summary__game_id-<the game id>.json
```

```bash
export PFF_TRANSPORT=sample PFF_SAMPLE_DIR=/path/to/those/files
uv run python -m quant_sports_intel_models.football.pff.probe \
    --league nfl --season 2024 --weeks 1 --out ablation_results/nf_w9_0
```

`sample` is a first-class transport, not a mock: the same parsing, the same raw-stats guard and
the same resolution code run. (`client.sample_filename(path, params)` prints any filename.)

## Reading the report — the three numbers that decide the go/no-go

| Field | What it answers |
|---|---|
| `id_space_agreement.verdict` | **Read this first.** `SAME_ID_SPACE` → the deterministic NFL join holds. `DISJOINT_ID_SPACE` → nflverse's `pff_id` is *not* PFF's `player_id`; NFL falls back to name matching. `PARTIAL` → investigate before trusting tier 1. |
| `player_match.opportunity_matched_rate` | The honest NFL match rate. The row rate is **not** the number to quote — see §2 of the feasibility write-up. |
| `facet_catalog` | Which facets actually exist, with the failures listed beside them. |

Also worth a look: `model_output_columns_stripped` (PFF grade columns the guard dropped — an
empty list means PFF sent none, *not* that the guard was off) and, on the NCAAF leg,
`unknown_school` rows, which are alias-map entries waiting to be added to `schools.py`.

**A zero-row pull exits non-zero.** That is intentional: a probe asking "can we join this?" must
never answer "yes, 0 rows". Use `--no-strict` only to diagnose *why* a leg is empty.

## Guards

```bash
uv run pytest betting_ml/tests/test_nfl_pff_probe.py -q          # 65 tests, ~0.2s
uv run python quant_sports_intel_models/football/pff/red_proof.py # 12/12 proven RED
```
