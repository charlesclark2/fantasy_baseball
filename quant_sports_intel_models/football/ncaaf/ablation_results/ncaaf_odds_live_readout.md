# NCAAF-ODDS-LIVE — the ahead-of-kickoff market feed (readout)

**Verdict: BUILT AND PROVEN END-TO-END ON REAL DATA; NOT YET DEPLOYED.** Operator-directed
2026-08-27 ("football is bet days ahead — ingest ≥3 days prior, multiple snapshots per day").
`best_alpha = 0` throughout: a market line is context beside the model, never a pick, and nothing
here computes a vs-market performance reading (VAL1's null stands).

---

## 1. The measurement that reframed the problem

The P0.6b `/historical` catch-up cannot serve an ahead-of-kickoff line **by construction** — it
only requests a kickoff once `K − buffer` has already passed. Measured 2026-08-27, the fix is not
"ask `/historical` more", it is a feed we already had and never wired:

| | one call returns | **measured cost** |
|---|---|---|
| live `/odds` (`sources._odds_ncaaf` — DECLARED since P0.1, **ingested by nothing**) | the **whole** upcoming board: 109 events, 1.6→92.6 days out, Bovada on 51 | **3 credits** |
| `/historical` (the existing weekly capture) | one ±30-min kickoff window at one past instant | **30 credits** |

⭐ **The ahead-of-kickoff feed is a TENTH the unit cost of what we already run.** The tiered
cadence is ~4,900 credits/season against a ~4.49M balance — **0.11%**. Cost was never the
constraint; the source spec had simply never been invoked (the NF-C0e "wired ≠ invoked" class, on
an ingest). *Both* figures above are measured against the live API, not read off a doc — the first
probe reported the cumulative `x-requests-used` counter, which is not the call cost, and re-taking
it properly is what produced the 3.

## 2. What was built

* **`odds_live_capture.py`** — fetch the live board → stamp `_snapshot_ts` / `_snapshot_kind` →
  READ-MERGE-WRITE per season partition of a **new `odds_ncaaf_live` Delta table**.
* **`sports_ncaaf_odds_live_job`** + **`sports_ncaaf_odds_live_schedule`** — hourly in-season cron,
  `default_status=STOPPED` (paid feed, operator-gated per the E11.23 carve-out).
* **Serving** — `build_clv_staging(with_live=True)` adds a `live_` leg; `payloads._market` now
  serves the **freshest strictly-pre-kickoff observation**.

### The three things that had to not go wrong

1. ⛔ **Live rows never touch `odds_ncaaf_historical`.** That mart's kind-blind leg takes the
   latest pre-commence snapshot per event, so a live snapshot minutes before kickoff would
   silently *become* "the close" — and P1.4's model selection and VAL1's CLV null were both
   decided on it. The separation is the TABLE, not a flag, and `with_live` is opt-in for the same
   reason `with_t1` is (a numeric `live_` column in the default frame is model-eligible and would
   HALT the bake-off on `assert_market_blind`).
2. ⛔ **`s3io.write_season_partition` is a season-grained `replaceWhere`.** A naive fetch→write on
   an hourly cadence deletes the whole season on *every fire*. The merge keys on
   `(event id, snapshot instant)` — deliberately not on the event alone, because two observations
   of one game at different instants are two rows and that history IS the line-movement asset.
   Proven live: run 1 → 109 rows, run 2 → 218.
3. 🔒 **In-play prices.** The live endpoint returns games already underway. Two independent
   defences (a `commenceTimeFrom` request bound *and* a post-fetch re-check, because a request
   parameter is one edit away from being dropped), plus the serving-side leakage guard as a third.

### The tier, and why it is one cron

Operator-chosen: **hourly inside 24h of the next kickoff, 6-hourly otherwise.** That decision is a
pure function (`should_capture`) called by the op — **not a second cron**. Two crons for one
logical job is this repo's most-repeated operational defect (INC-30's double-installed crontab,
INC-36's raced deploy, INC-38's per-caller flag). A non-capturing tick spends zero credits and
says why, because a silent skip is indistinguishable from a schedule that stopped firing
(NF-FRESH1's 19 green runs). The schedule evaluation itself does **no IO** — the tier needs
kickoff times, and a CFBD call inside a schedule eval would put network in the Dagster daemon
(the INC-32 wedge class), so the op does that read in its own process.

## 3. It supersedes a decision NCAAF-P3.1b shipped two days ago

P3.1b preferred the T-1 snapshot over the close. That was right when the only alternative was a
close captured *after* the game. With a live feed the argument no longer selects T-1: for an
upcoming game the honest comparator is what the market says **now**, and for a played game the
freshest pre-kickoff observation *is* the close — which is also correct there. So **freshest
strictly-pre-kickoff wins** is one rule that is right in both regimes where a fixed order is wrong
in one. `source` + `as_of` (both shipped by P3.1b) are what keep it honest.

Five P3.1b clauses encoded the old order and were **re-anchored, not deleted**; every other
property P3.1b defends (the label, `as_of`, the leakage guard, additivity, the no-client-change
claim) is unchanged and still asserted.

## 4. Proven end-to-end on the real opener slate

One real capture → 109 events → `odds_ncaaf_live` → `build_clv_staging(with_live=True)` →
`payloads._market`, against the actual served 8/29 board:

```
North Carolina     @ TCU                 available  src=odds_api_live  spread=-9.0   total=46.5
San José State     @ USC                 available  src=odds_api_live  spread=-6.5   total=52.5
NC State           @ Virginia            available  src=odds_api_live  spread=-4.0   total=51.5
Jacksonville State @ North Dakota State  available  src=odds_api_live  spread=-7.0   total=46.5
Sacramento State   @ Eastern Michigan    available  src=odds_api_live  spread=-9.5   total=53.5
Hawai'i            @ Stanford            available  src=odds_api_live  spread=…      total=…
New Mexico State   @ Florida State       available  src=odds_api_live  spread=-32.0  total=53.5
Memphis            @ UNLV                available  src=odds_api_live  spread=-4.5   total=56.5
```

**8 of 8 — but only after fixing a join defect the first run exposed.** The raw pass joined 6 of 8:
`San José State` and `Hawai'i` failed the odds→CFBD **prefix name join** on a diacritic and an
apostrophe. Folding accents + punctuation fixes both, and a negative control confirms the looser
join is not a wrong one (`Miami (OH)` still does not match `Miami Hurricanes`).

⚠️ **The fold is applied to the LIVE leg ONLY.** Applying it to the default leg would *add* rows
to the CLV mart — i.e. change the population P1.4's selection and VAL1's null were decided on —
so the default join is byte-identical and a false-negative sweep of the historical legs is carded.
That is the same discipline as ①: a serving convenience must not be able to move a recorded result.

## 5. Guards

`betting_ml/tests/test_ncaaf_odds_live.py` (31) — **`ncaaf_odds_live_red_proof.py`: 24/24 RED**.
`ncaaf_p3_1b_red_proof.py` re-anchored and back to **24/24**. Four vacuous guards were found by
the RED proofs rather than by a green suite, all in this session's own new code:

1. nothing asserted that `fetch_live_board` **passes** the `commenceTimeFrom` bound — the request
   accepting one proves nothing about the capture sending one (wired ≠ invoked, NF-C0e);
2. the tier-purity scan was **defeated by the op's own docstring**, which names `should_capture`
   while explaining it — INC-38 pointing the other way (prose breaking a guard rather than
   satisfying one);
3. the re-anchored "the writer opts in" clause was **satisfied by the writer's docstring** and
   shipped that way for one RED-proof cycle before being matched as a call fragment;
4. a dense-window boundary fixture built its kickoffs relative to the wrong clock, so it tested a
   39-hour window while naming a 24-hour one.
