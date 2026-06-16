# Parlay API — Support Request (drafted 2026-06-16, firm tone)

**Account / key:** Business plan (1,000,000 credits/mo). Key prefix `598f3d…b04c` (full key on request).
**Support form limit:** 10–5000 characters. The message body below is **form-ready and within limit** (~2,950 chars).
**Subject (if a subject field exists):** Business key silently throttled to a 500/mo quota for ~2 weeks — unrecoverable data loss

---

## FORM-READY MESSAGE (paste this)

We run a production MLB odds product on your Business plan (1M credits/mo; key prefix 598f3d…b04c) and we log your x-requests-used / x-requests-remaining headers on every call. We've found a metering failure on our account that silently cost us ~2 weeks of data, and we need specific answers — this has us questioning whether we can rely on Parlay.

THE PROBLEM. Our Business key's reported window quota (x-requests-used + x-requests-remaining) was not 1,000,000:
- on/before 2026-05-26: 100,000 (Pro-tier level)
- 2026-05-27 to ~06-04: 500 (free-tier level) — an exact step-down on 05-27
- 2026-06-16 (today): 1,000,000 (correct)

We've held Business since before we cut over to Parlay, so this key should never have reported 100k, let alone 500. During the 500 window our captured odds collapsed to roughly one quarter of normal — snapshots per game ~13 to ~7, daily stored rows ~30k to ~8k — consistent with your API throttling or truncating responses while still billing (we understand empty responses bill). No alert, no notice.

This data is unrecoverable on our side: your historical archive runs ~6 weeks behind (/v1/historical/coverage shows latest_played_date 2026-05-07) and contains no Bovada, our reference book.

WE NEED ANSWERS TO:
1. Why did our Business key meter at 100,000 and then 500 per month in late May / early June? What changed on 2026-05-27?
2. Did that low quota throttle or truncate our /v1/sports/baseball_mlb/odds responses (partial book/event coverage), or was only the header wrong and the data complete?
3. It reads 1,000,000 again today — what did you fix, and how do we prevent recurrence and get alerted if a paid key is ever downgraded again?

LIVE REPRODUCTION (today): GET /v1/sports/baseball_mlb/odds?regions=us&markets=h2h returns 200 with x-requests-used 41183, x-requests-remaining 958817 (quota 1,000,000).

SECONDARY — historical endpoints bill for empty data. In-range recent dates return 200 with an empty body but still charge credits:
- /v1/historical/sports/baseball_mlb/odds?date=2026-05-15 returns [] and bills 20 credits
- /v1/historical/sports/baseball_mlb/matches?date=2026-05-20 returns [] and bills 2; date=2026-04-15 returns 98 rows
4. What is the expected publish lag, why are in-range dates empty-but-billed, and is historical Bovada available anywhere? Your MLB historical sources are all Action-Network (suffix _an) with no Bovada.

A silent multi-week quota downgrade on a paid production account, with no alert and permanent data loss, is a serious reliability problem for us. We'd appreciate a prompt and specific response. We're happy to share our stored header logs or the full key over a secure channel.

Charlie, Credence Sports — charlie@credencesports.com

---

## Evidence appendix (our records — NOT part of the 5000-char form message)

Quota header by day (from `mart_odds_outcomes.x_requests_*`):
| Date (UTC) | used + remaining (window quota) |
|---|---|
| 2026-05-24..26 | 100,000 |
| 2026-05-27 | 500 (step change) |
| 2026-06-02..04 | 500 |
| after 2026-06-04 | header not captured (our logging gap) |
| 2026-06-16 (live) | 1,000,000 (remaining 958,817 / used 41,183) |

Capture density (Bovada h2h/totals): May ~13.2 snaps/game → June ~7.7. 5-book avg: 17.5 → 11.5.

Probes run 2026-06-16 (all 200):
- /v1/historical/sports/baseball_mlb/matches?date= → 2026-06-14:0, 05-20:0, 04-15:98, 03-20:60, 2025-09-15:31 (publish lag ~6wk)
- /v1/historical/sports/baseball_mlb/coverage → all MLB sources last_date 2026-05-09; no Bovada
- /v1/historical/coverage → summary.latest_played_date 2026-05-07
