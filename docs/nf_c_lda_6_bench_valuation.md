# NF-C-LDA-6 — what a bench pick should be measured against

**Status: MEASURED, nothing shipped.** The study changes no ranking. This is the decision memo.

## The question a live draft asked

A 2026 ESPN mock, drafting from slot 6, reported: *"WRs seemed to really not even pop up. Even when
I got to the middle rounds, they weren't being suggested, but backup TEs and QBs definitely were."*

NF-C-LDA-1 had just fixed a flex-capacity miscount that inflated backup tight ends, and the symptom
survived it. So the first job was to find out whether anything was still broken, or whether the
engine was doing exactly what it says and the thing it says is wrong.

## It is doing exactly what it says

Measured on the real 2026 board in a real 12-team league:

| ~pick 115, best available | VOR | still above replacement |
|---|---:|---:|
| QB Fernando Mendoza | +3.0 | 2 |
| TE Kenyon Sadiq | **+23.7** | 3 |
| RB Blake Corum | −37.2 | **0** |
| WR Jalen Coker | −27.0 | **0** |

Replacement level is the **starter** cutoff. 35 WRs and 25 RBs clear it, and a 12-team room consumes
every one of them by round 8 because each team starts two or three. Only 12 TEs and 12 QBs clear it,
and each team needs exactly one. ⇒ **positive VOR survives only at the two positions where a bench
player is least useful to you** — you can start one of him, and only if your starter is out.

So "best value on the board (VOR)" is *structurally guaranteed* to return a backup TE or QB in the
back half of every draft. That is not a bug in the code's own terms. VOR is a **starter-scarcity
currency**, and a bench seat is not a starter slot.

## The field

Four rules, pre-registered, each a **matched foil**: identical `recommend()` machinery — needs,
tiers, flex re-basing, bye penalties, the reserve constraint, K/DST deferral — differing *only* in
how a level-0 (bench) candidate is scored.

⭐ **The arms never differ on *whether* to take a bench player, only on *which*.** Each arm first
asks the shipped engine what it would take; if that is a need-filler, every arm takes it. A
difference is therefore attributable to the bench comparator and to nothing else (NF-D10/D15).

| arm | bench value |
|---|---|
| `incumbent` | VOR × (1 − surplus) — the shipped rule, the null to beat |
| `own_worst_starter` | his rate − my weakest startable player at a seat he could fill |
| `seats_covered` | incumbent, scaled by how many startable seats the position has for me |
| `insurance` | P(I actually need him) × what he adds over the next man up |
| `raw_points` | highest projection, position-blind — reference, not a candidate |
| ⚓ `oracle` | the marginal gain he makes to the **realized** season — peeking, same family, same sample |
| ⚓ `nihilist` | prefers the **worst** available — must lose |

## The metric

Expected **starting-lineup** points over an 18-week season with byes and absence.

⭐ Scoring "your best nine" instead would make bench depth worthless *by construction* and every arm
would tie — the whole question lives in the weeks somebody has to be started in a starter's place.
`test_the_season_rewards_a_bench_that_covers_absence` pins that the metric can see depth at all.

Availability is **read from the board, not invented**: `g` is expected games of 17, so a player
misses `17 − g` non-bye weeks and his per-game rate is `pts / g` — consistent by construction, since
`g × rate` returns his projected season.

Common random numbers throughout: every arm drafts against the same room and plays the same season,
so the paired delta cancels almost all simulation noise before it reaches the metric (NF-W7k).

## Result — 120 drafts per arm (10 seasons × 12 slots)

| arm | vs incumbent | 95% CI | won | note |
|---|---:|---:|---:|---|
| ⚓ `oracle` | **+93.1** | ±7.7 | 118/120 | the peeking floor — unbeaten ✅ |
| **`insurance`** | **+77.3** | ±7.9 | 118/120 | **83% of the oracle's headroom** |
| `own_worst_starter` | +57.7 | ±7.9 | 107/120 | |
| `incumbent` | — | — | — | shipped |
| `seats_covered` | **−26.6** | ±5.4 | 15/120 | the cheap option **loses** |
| `raw_points` | −38.0 | ±5.9 | 7/120 | reference |
| ⚓ `nihilist` | −102.2 | ±7.4 | 0/120 | last ✅ |

`insurance` beats `own_worst_starter` on the **paired** delta (+19.5 ±6.5), so they are separable —
the difference between their two column entries above would not have established that (NF1.8).

### What each rule actually puts on the bench

| arm | QB | RB | WR | TE |
|---|---:|---:|---:|---:|
| ⚓ `oracle` | 35% | 10% | **32%** | 23% |
| `insurance` | 21% | 17% | **38%** | 24% |
| `incumbent` | 47% | **0%** | **0%** | 53% |
| ⚓ `nihilist` | 0% | 0% | 2% | 98% |

The shipped rule's bench is **47% backup QB and 53% backup TE, with zero RBs and zero WRs** — the
live report, quantified over 120 drafts. ⭐ And its tight-end share sits closer to the **nihilist's**
than to the oracle's.

## Robustness

* **Absence model.** The primary draws each missed week independently, which fragments an injury a
  real season would keep contiguous — and that *understates* depth, i.e. it is conservative toward
  the incumbent. Re-run with contiguous blocks: identical ordering, `insurance` +70.7,
  `own_worst_starter` +43.3, anchors still hold, head-to-head still separable (+27.4 ±6.8).
  ⚠️ I did not pre-register which model binds; both are reported because they **agree**, so nothing
  turns on the choice (the NF-D14 shape).
* **Draft slot.** Every arm's sign holds at all 12 slots, including slot 6 where the live draft ran.
* **Anchors.** Held in both runs — the peeking oracle is never beaten, the nihilist is always last.
  ⇒ the leaderboard is readable (E2.1-r / NF-D11).

## Recommendation

**Adopt `insurance`.** It captures 83% of everything a rule with perfect foresight could get, wins
118 of 120 paired drafts, is separably better than the runner-up, and is robust to the absence model
and the draft slot. `seats_covered` — the cheap fix — is measurably **worse than doing nothing**.

## ⚠️ What this study does not establish

* **The room is not adaptive.** The other eleven teams draft ADP-with-noise; they do not react to
  scarcity we create. A rule that hoards a position would not be punished here as it would be in a
  real room.
* **Independent absence is not injury.** Even the contiguous variant places one block uniformly at
  random; it models neither injury-proneness correlation nor in-season news.
* **One board, one season, one scoring format.** Every draft is the 2026 board in a 12-team PPR
  league with this roster shape. The mechanism argument generalises; these magnitudes do not.
* **This is a simulation, not a backtest.** It measures which rule builds a better team *under our
  own projections*. A projection error common to all arms is invisible to it.
* ⛔ **No claim about winning a league.** `best_alpha = 0`; this is a ranking study, and the honest
  framing is unchanged.

## Two harness defects worth remembering

Both produced a confident, wrong leaderboard, and both were caught by the anchors rather than by eye.

1. **An inactive anchor looked like a result.** The first oracle was `insurance` with realized
   availability substituted — but the substitution only entered through a branch that rarely fires,
   so it scored **byte-identically** to the honest arm (1838.1 vs 1838.1) and was then "beaten" by a
   third rule. Reading that as a metric inversion would have been the wrong finding; an anchor that
   cannot act is uninformative, never a pass and never a fail (NF-W6d / NF-D20).
2. **A unit mismatch let an arm change the wrong decision.** Re-scoring level-0 rows inside the
   engine's own sort mixed season points with VOR, letting a bench pick jump a need-filler on units
   alone. It pushed the peeking oracle *below* the incumbent — which again reads as an inverted
   metric and was really a harness bug. The fix is the matched-foil shape described above.

And a third, in the diagnostic rather than the metric: the bench-mix table first classified "the
last six picks" as the bench, which counted the forced K and D/ST in every arm and diluted every
real share by a third. It now reads the actual slot assignment.
