# PFF probe (NF-W9-0) — operator runbook

Research only. `best_alpha = 0`. No serving path, nothing published.

> ⚠️ **The current subscription tier withholds every field NF-W9-1/2/3 need** (`routes`,
> `avg_depth_of_target`, `yards_after_contact`, …). See the feasibility write-up. The probe
> below still runs end to end and is the instrument to **re-run against an upgraded
> credential** — `opportunity_field_availability` flips on its own if the fields unlock.

## What the operator must supply

PFF is a paid subscription behind login. **This client never attempts to bypass auth** — it
replays a credential you capture from your own logged-in session.

**There is no bearer token to find.** PFF uses **Clerk**: the `__session` cookie *is* the JWT.
So the credential is the **cookie**, and `PFF_AUTH_TOKEN` is optional (PFF does not appear to
issue one to the browser).

1. Open PFF, DevTools → **Network**, filter `api/v1`.
2. Click anything that loads data (a game page). Pick a `/api/v1/…` request.
3. From **Request Headers** copy the whole `cookie:` value → `PFF_COOKIE`.

> ⭐ **The `__session` JWT lives 60 SECONDS — and that is fine.** You do *not* need to paste it
> within a minute. An expired session makes the API 307 to Clerk's handshake, which mints a
> fresh one from the long-lived `__refresh_*` cookie in the same jar; the client follows that
> redirect with a persistent session, exactly as the browser does. What you must NOT do is
> hand the cookie to something that sends it as a one-shot header — that loops the redirect
> until curl aborts with "maximum redirects followed".
>
> If a run reports `PFFAuthError`, the whole jar has gone stale (you logged out, or the refresh
> token expired) — re-capture. That is deliberately distinct from `PFFChallengeError`
> (DataDome/Cloudflare) so you know which one to act on.

## Run the probe — **LAPTOP** (not the box; needs no box-only state, and reads the S3 lake)

```bash
cd /path/to/your/worktree

# ⚠️ quote it — the jar contains `$`, `;` and `=`
export PFF_COOKIE='<paste the whole cookie header value>'
export AWS_DEFAULT_REGION=us-east-2                      # DuckDB-S3 lake reads

# NFL and NCAAF have different season/week calendars, so run them separately.
uv run python -m quant_sports_intel_models.football.pff.probe \
    --league nfl  --season 2024 --weeks 1,2 --out ablation_results/nf_w9_0

uv run python -m quant_sports_intel_models.football.pff.probe \
    --league ncaa --season 2025 --weeks 11  --no-discover --out ablation_results/nf_w9_0_ncaa
```

Runtime: ~2 min for NFL wk1–2; ~10 min for an NCAAF week (116 games × 4 facets). Each writes a
`nf_w9_0_probe_report.json` plus one small parquet.

⛔ **Do not commit the parquet or the cookie.** The parquet is PFF's licensed data and the
cookie is a live credential — keep both out of the repo (the probe writes wherever `--out`
points; point it at a scratch dir if in doubt).

**Last measured (2026-08-18):** NFL 100% player / 100% game match; NCAAF 97.1% / 100%;
`id_space_agreement = SAME_ID_SPACE`; `opportunity_field_availability = NO_OPPORTUNITY_FIELDS`.

**If DataDome/Cloudflare challenges the direct call** (`PFFChallengeError`), rerun through the
existing FanGraphs solver:

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
| `opportunity_field_availability.verdict` | **The go/no-go.** `NO_OPPORTUNITY_FIELDS` means the tier withholds everything the downstream stories consume — rows arrive, but carrying nothing we don't already have. `FULL` means the upgrade worked. |
| `restricted_fields_by_facet` | Exactly which fields PFF says this subscription withholds. |
| `facet_catalog` | Which facets exist (`not_published_404`) vs which we failed to fetch (`fetch_failed`) — different facts. |

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
