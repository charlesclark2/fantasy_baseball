# NCAAF-P3.1b — serving the T-1 market snapshot (readout)

**Verdict: SHIPPED (code) / NO USER-VISIBLE LINE YET (production).** The serving change is
complete, guarded and RED-proven, and it is measured to work end-to-end on real captured data.
It produces **nothing on the 2026 board today**, because the lake holds **zero 2026 odds rows of
either kind** — see §3, which is the finding this story most needs a reader to carry.

Measured on 2026-08-25 from the production lake (`ncaaf/raw/odds_ncaaf_historical` via DuckDB).
`best_alpha = 0` throughout: nothing here computes or asserts a vs-market performance reading, and
VAL1's CLV null is untouched.

---

## 1. What changed

`payloads._market()` read only the `close_*` columns and hardcoded `MARKET_SOURCE_CLOSE`. It now:

* **prefers the T-1 (~24h-prior) snapshot** and falls back to the close, because this surface
  serves a PRE-KICKOFF projection and the honest comparator beside it is the market's own
  pre-kickoff line;
* **stamps `source` and `as_of`** so a reader can recover WHICH line they are seeing and from when
  (`as_of` is an ADDITIVE field, NF-C0; declared on `NcaafMarketLine`, E9.41);
* **refuses any line it cannot prove is strictly pre-kickoff** — fail-closed, logged loudly,
  attaching nothing, with the refusal distinguishable from "nobody priced this kickoff".

`build_clv_staging` grew an opt-in `with_t1=` that asks the SAME join for the T-1 kind (E9.61 —
one rule set, parameterised, not a second copy). It is **default-OFF**: a numeric `t1_home_spread`
in the default frame would be picked up by `feature_columns` as a MODEL FEATURE and
`assert_market_blind` would HALT the bake-off, so no recorded P1.4/P2.1 result can move because of
this story. `scripts/write_ncaaf_serving_store.read_market_lines` is the one caller that opts in.

## 2. It also fixes a mislabel that predates the story

`build_clv_staging`'s kind-blind leg takes the LATEST pre-commence snapshot per event. For a
kickoff whose T-1 has been captured and whose close has NOT — the pre-kickoff case this whole story
exists for — that leg picks the T-1 row up and files it under `close_*`. Before this change the
number would have been right and the word beside it wrong, which is the harder defect to notice.

## 3. ⚠️ THE 2026 BOARD CARRIES NO LINE TODAY, AND THE SERVING CHANGE CANNOT MAKE ONE APPEAR

Per-kind row counts in the lake, measured:

| season | close rows / events | T-1 rows / events |
|--------|--------------------:|------------------:|
| 2020 | 954 / 538 | 975 / 550 |
| 2021 | 1698 / 1078 | 1749 / 851 |
| 2022 | 1991 / 1154 | 1680 / 858 |
| 2023 | 1785 / 892 | 1592 / 801 |
| 2024 | 1940 / 926 | 1872 / 900 |
| 2025 | 2027 / 944 | 1977 / 920 |
| **2026** | **0** | **0** |

The 2020–2025 T-1 backfill is real and substantial. **2026 has no partition at all**, because the
capture is the paid `/historical` CATCH-UP (P0.6b decision (A), not a live scheduler): it only
fetches a kickoff once that kickoff is past its snapshot instant, and
`sports_ncaaf_odds_capture_schedule` fires **Mondays** (`0 8 * 8-12,1 1`). For the Sat 2026-08-29
opener the T-1 instant (K−24h) falls on **Fri 8/28**, and the next scheduled fire is **Mon 8/31** —
after the games.

⇒ **The opener cards will still read "No market line" unless an operator runs the capture on Friday
8/28.** That run is the one that turns this story into a user-visible line; the serving change is
necessary and not sufficient. (The PM premise "every opener card says unavailable when a real
Friday line exists" is correct in mechanism and one capture-run short in fact.) The command is in
the handoff. Nothing about this is a defect — it is the retrospective-by-design capture meeting a
Saturday opener — but it must not be discovered on Saturday morning.

## 4. The leakage guard, measured on real data — it fires, and it costs almost nothing

Run over the whole 2025 staging mart (876 games with a close, 865 with a T-1), comparing each
snapshot instant against the **CFBD** kickoff:

| leg | rows | refused | ≤90 min late | >1 day late |
|-----|-----:|--------:|-------------:|------------:|
| T-1 | 865 | 7 (0.8%) | 0 | **7** |
| close | 876 | 79 (9.0%) | 64 | **8** |

Two genuinely different populations, and the split is the whole story:

* **≤90 minutes late (close only, 64 rows).** A **CFBD-vs-Odds-API kickoff-clock disagreement**,
  not a leak: the K−5min close is taken against the BOOK's `commence_time`, and CFBD's `startDate`
  for those games sits 5–55 minutes earlier. The T-1 leg is structurally immune (a ~24h lead
  cannot be flipped by a sub-hour disagreement), which is a second, independent reason to prefer
  it. Refusing these is the fail-closed call: at that distance a "close" price may already be an
  IN-PLAY price by CFBD's clock, and serving one as a pre-game line is the one thing this surface
  must never do.
* **>1 day late (both legs, 8 games).** ⭐ A **genuine mis-join in P1.4's staging mart**, and a
  finding that outlives this story. The odds→game join matches Odds-API team names to CFBD names
  by PREFIX with no kickoff-proximity bound, so a rematch attaches the wrong game's line: Texas
  Tech–BYU's 11/08 game carries a 12/06 snapshot (the Big 12 championship rematch); Colorado–
  Arizona's 11/01 game carries an 11/23 one. Left UNFIXED here on purpose — it is a mart P1.4 owns
  and it touches the vs-market/CLV evals, not just serving. Carded in the closeout.

**What it costs the served board:** over the whole 2025 season the block would serve **858 T-1 +
13 close and refuse 5** (0.57%) — the five where BOTH candidates are out of bounds, i.e. exactly
the mis-joins. The strict guard is nearly free and catches real defects.

## 5. Proof on a real game

`game_id=401752665`, kickoff `2025-08-30T19:30:00Z`:

* **served**: `source=odds_api_historical_t_minus_1`, `as_of=2025-08-29T19:55:39Z`,
  home spread `14.0`, total `49.0`
* the close it did **not** serve: spread `13.5`, total `47.5`, at `2025-08-30T19:20:38Z`

The two lines differ on **70.2%** of the 865 games that carry both — the T-1 line is a materially
different number from the close, which is why the label had to travel with it.

## 6. No client change (spec AC3), proven mechanically rather than by eye

The P3.2 panel reads `market.status`, the four numbers and `market.reason`; it reads **no
`source` and no `as_of`**, and it renders an unknown `reason` through `MARKET_REASON_FALLBACK`.
Both halves are asserted: the panel is scanned (comment-stripped) for a `source`/`as_of` read, and
two payloads differing ONLY in source are asserted byte-identical in every field the panel reads.
The two new `reason` values deliberately get no bespoke copy — the fallback sentence is correct for
both, and a refusal is not a state a reader can act on.

## 7. Guards

`betting_ml/tests/test_ncaaf_p3_1b_market_source.py` (32 tests) —
**`betting_ml/tests/ncaaf_p3_1b_red_proof.py`: 24/24 deliberate breaks RED**, covering all three
directions the spec names (a post-kickoff snapshot refused, a valid T-1 attached, absent stays
absent). Three guards were VACUOUS on first cut and were found by the RED proof, not by a green
suite:

1. "an out-of-bounds close does not veto a valid T-1" is **true by the preference order alone** —
   with T-1 first the bad close is never examined. The observable property is the other direction
   (a refused T-1 must not blank a valid close), and the test now runs that.
2. the run-log counter test called `_count_by` directly, so breaking the CALL SITE left it green
   (the NF-C0e wired-≠-invoked class); it now runs a real `write_serving_store`.
3. the panel's fallback assertion grepped for `MARKET_REASON_FALLBACK`, which is satisfied by the
   **import line** with every use deleted; it now matches the `||` fallback operator.

`test_ncaaf_p3_2_surface.py`'s captured-fixture round-trip was RE-ANCHORED (not weakened): a field
declared after the bytes were captured is tolerated only when it validates to `null`, and the test
NAMES what it tolerated, so the stale capture stays visible. Closing it properly is a re-capture
after the Lambda deploy — the fixture cannot lead the wire.
