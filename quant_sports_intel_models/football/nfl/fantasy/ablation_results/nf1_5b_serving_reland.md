# NF1.5b — re-landing the NF1.5 refined market-aware board as the SERVED board

**Status:** code-complete; **the Step-0 re-grade PASSED (2026-08-01) — see §5 for the numbers and for
the part of the headline that did NOT reproduce.** · **Operator decision (b), 2026-08-01:** serve the
refined board. · `best_alpha = 0`.

---

## 1. What this changes for a user

The served 2026 board flips from **market-BLIND** (MVP-1) to **market-AWARE** (NF1.5's refined
re-ordering). Every fantasy surface reads it: Projections, Rankings, the League Board, the Draft
Optimizer and the NF3.1 player pages.

It changes **only the order**. The projected points and the 80% bands are MVP-1's own calibrated
numbers — the refined board hands each position's players that position's *existing* point multiset
in learned-rank order. On the 2026 board **665 of 784 players sit at a different level than MVP-1
gave them**, and the per-position multiset is preserved to a mean of 0.07–0.26 PPR (max 0.78–4.69,
the raw-line rescale's own quantisation — see §3).

## 2. THE HONEST FRAME — the exact claim, and the exact non-claim

✅ **What is true and measured (re-grade, 2026-08-01, §5):** over six held-out seasons the refined
ordering beat **ADP** on pooled within-position ρ, **+0.022** (us 0.517 vs ADP 0.494) — against the
**served MVP-1 board's −0.059**. The flip therefore turns a board that loses to ADP into one that
beats it, on the metric the operator decision was made on.

⚠️ **What did NOT reproduce: "all four positions."** NF1.5's stored grade said the refined board beat
ADP at every position. On current code it is **+0.031 QB, +0.037 WR, +0.021 TE, and −0.000 at RB —
a wash**. Per season it is 4 clear wins, 1 tie (2023, +0.000) and **1 loss (2020, −0.044)** out of 6.
The claim is "beats ADP **on average**", not "at every position" and not "every season".

⚠️ **And it is ADP-specific.** We still LOSE to every expert/platform ranking set: ECR −0.013,
ESPN −0.051, Sleeper −0.125. "Beats the market" without naming ADP would be read as a claim we cannot
support.

⛔ **What must never be said:** that we *beat the market*. At the market-leaning positions the board
**incorporates** consensus (ADP/ECR) as an input — QB `market-led-adaptive`, RB `market-led`, WR
`market-led`, TE `market-blend`. A board that uses the market cannot claim an independent edge over
the market it uses.

📐 **And it is a RE-ORDERING claim, not a re-pricing one.** We re-order the same calibrated
projections; we do not re-price anyone. Anything phrased as "our projections are more accurate" is
wrong in kind, not just in degree.

⚠️ **Carry the trade-off (NF1.3/NF1.5), now with the re-grade's own numbers.** The refined board's
top-tier ρ was **not** deflation-robust (PBO 0.23–0.69, DSR below the gate at every position —
`verdict.repoint = false` for all four), and **the FADE edge is much weaker than the market-blind
board's**. On its own high-disagreement subset the refined board still out-predicts ADP (0.498 vs
0.416, a **+0.082** margin) — but MVP-1's margin on ITS subset was **+0.235** (0.478 vs 0.243).
⚠️ Those are two DIFFERENT populations (a board that leans on the market disagrees with it on a
different, less extreme set of players), so the honest read is not "the fade edge fell by 65%" but
**"the fade set itself changed, and the surviving margin on it is much narrower"** — which is the same
conclusion, arrived at without pretending the two numbers are comparable. The correct summary remains
**"tracks the market and adds signal, NOT an independent edge."** Serving it is the operator's call,
made on the PRODUCT metric (Δρ-vs-ADP) rather than on the deflation gates, and the framing must
reflect that.

🚫 **The payload note makes NO superiority claim at all** — deliberately. It carries the CAVEAT
(which positions use the market, and that this is a re-ordering not a re-pricing) and nothing else.
Three reasons: a bare "beats ADP" on a browse surface has no evidence beside it; it would contradict
the copy already on those surfaces ("ADP is a reference point, not a scoreboard"); and the result
needs two qualifications (RB is a wash; ECR/ESPN/Sleeper still beat us) that do not fit in a caption.
The claim belongs to the receipts surface that can show its working (NF3.2). What IS carried in the
payload is the part a user cannot look up: `market_lean` (per position) + `market_lean_note` in
`manifest.json` / `projections.json`, and `mktLean` on every player record, rendered by
`MarketLeanNote`. So which positions use the market travels with the model and cannot drift from the
copy.

## 3. What the re-land had to FIX before it was safe to serve

The readiness pass expected "repoint the read". It was not that. NF1.5's build **assembled a parallel
board** instead of transforming the shipped one, and had drifted from it on three axes — all of which
would have reached users on the flip:

| axis | the drift | fix |
|---|---|---|
| **UNIVERSE** | the refined board carried **716 players against the shipped 784**. It was assembled from the NF1.2 research frame, whose `load_base_season` call has no NF-D11 base-anchor rescue — so **68 returning veterans would have vanished from the draft board**. | the refined board is now `run_season_projection.build_projection` with the re-order injected as its `veteran_postprocess` hook. Same universe by construction: **784 = 784, identical player set**. |
| **INTERVAL** | it re-priced every band as `point ± 1.2816·κ·sd` — the **pre-NF1.9 normal approximation, measured coverage ~0.55 of its nominal 0.80** — and stamped it `calibrated`. Flipping the board would have silently reverted the NF1.9 per-player band on ~90% of the draft board. | the interval block was factored into `season_projection.attach_season_interval` and is **re-derived through MVP-1's own code at the re-assigned level**. The rebuilt board is **784/784 `calibrated_per_player`**, exactly as the incumbent. |
| **SURFACES** | the draft board (`board_*.json`, from `run_league_board.py`) and the Projections surface (`projections.json`) read two SEPARATE artifacts, so repointing one and not the other would rank the same player differently on two pages with no error anywhere. | `run_league_board.py` gained the same `--projection-source`, stamps `projection_source` on every board row, and the export **refuses** (`assert_board_projection_source`) on a mismatch or on a board too old to carry the column. |

**A residual, now measured and alerted rather than assumed:** `apply_learned_level` rescales each raw
line by a **clamped** scalar (0.30–3.5), so a large within-multiset promotion cannot always reach its
assigned level. On the 2026 board **20 of 703 veterans saturate the clamp**, which is the whole of why
the multiset is preserved to ~0.1–0.3 PPR rather than exactly. The build now ALERTs on saturation and
`nf1_scale` is carried on the artifact so it is auditable. This is the shipped NF1 mechanism's
documented tail guard, not something NF1.5b introduced.

**κ is gone.** It was a second, NF1.5-private interval model layered on the shipped one. There is no
knob to fit now — only a question to answer, so `calibrate_season_interval` became
`verify_season_interval`: held-out coverage **per position and pooled over ROWS**, reported as a
**FLOOR** (E2.1-r / NF1.8), never rescaled toward.

## 4. Guards

`betting_ml/tests/test_nf1_5b_served_board.py` (fast gate, 16 tests) pins: the `eligible` mask is
byte-identical to the pre-NF1.5b path when all-true; an unscored veteran passes through untouched;
the eligible subset is permuted over its OWN multiset; `attach_season_interval` is idempotent at a
fixed level and moves the band with the point when the level changes; the refined build cannot roll a
private interval (source inspection — the runtime symptom is a plausible-looking but uncalibrated
band, so only inspection catches it) and no longer accepts a `disp_kappa`; the projection-source
mismatch refuses and names the fix; and the caveat text cannot drift into a beat-the-market claim.
`test_nf1_9_veteran_intervals.py` follows the interval block to its new home and additionally pins
that `project_veterans` only ever FORWARDS the band model.
## 5. THE RE-GRADE — ✅ PASSED (2026-08-01, `--mode grade --board beats-incumbent --seasons 2019…2024`)

Re-measured on current code, over the corrected 784-player universe with NF1.9 bands. It could not be
inherited: NF1.5's stored grade predates NF1.6/1.7/1.8/1.9/NF-D11/NF-D16, its stage-1 pool (`n_pool`
6736) predates NF-D11's universe change, and NF1.5b moved the universe again by 68 players.

**Δρ pooled vs each benchmark — the refined board against the board it replaces:**

| benchmark | MVP-1 (the SERVED incumbent, NF-D3) | NF1.3 stored | **NF1.5b refined** | comparable n? |
|---|---:|---:|---:|---|
| **ADP** | **−0.059** | +0.015 | **+0.022** | ✅ both n=6 |
| ECR | −0.052 | −0.020 | −0.013 | ⚠️ MVP-1 n=7 vs 6 |
| ESPN | −0.036 | −0.100 | −0.051 | ⚠️ MVP-1 n=3 vs 2 |
| Sleeper | −0.118 | −0.163 | −0.125 | ✅ both n=6 |

⭐ **The gate result: on the two benchmarks that ARE apples-to-apples, the flip turns a −0.059 loss to
ADP into a +0.022 win, and leaves Sleeper essentially unchanged (−0.118 → −0.125).** ECR/ESPN look
improved but their season counts differ, so read them as directional only — a benchmark scored over a
different number of seasons is not a comparison, and saying so is cheaper than being wrong about it.

**Per-position and per-season (ADP) — the part of the old headline that did NOT survive:**

| | QB | RB | WR | TE | pooled |
|---|---:|---:|---:|---:|---:|
| pooled Δρ | +0.031 | **−0.000** | +0.037 | +0.021 | **+0.022** |
| seasons positive (of 6) | 5 | 4 | 4 | 3 | 4 win / 1 tie / 1 loss |

The losing season is **2020 (−0.044)**; 2023 is an exact tie (+0.000). ⇒ the claim is **"beats ADP on
average over 2019–2024"**, never "at every position" (RB is a wash) and never "every season".

**Interval verify — the FLOOR held, everywhere** (E2.1-r: reported as a floor, never rescaled toward):

* pooled `calib_80` **0.847** on n = 2688 held-out veteran-seasons;
* per position **QB 0.856 · RB 0.842 · WR 0.868 · TE 0.817 · FB 0.807** — all ≥ 0.80, pooled over
  ROWS rather than as a mean of per-season means (the NF1.8 per-group lesson);
* per season 0.832–0.870, no season below the floor;
* `uncertainty_tiers` on the graded board: **100% `calibrated_per_player`** — the NF1.9 band survives
  the re-order, which is the specific thing §3's interval fix had to earn.

**The clamp, per season:** 22–35 of ~600–750 veterans saturate the raw-line rescale each season —
stable across 2019–2024, i.e. a property of the mechanism rather than of this particular board.

⇒ **PUBLISH IS CLEARED**, with the §2 framing corrections applied: the "all four positions" and
"beat consensus ADP" phrasings were removed from the changelog, and no superiority claim ever entered
the payload.
