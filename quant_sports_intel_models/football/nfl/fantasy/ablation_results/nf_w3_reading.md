# NF-W3 — reading: what the game-environment component actually found

Companion to `nf_w3_game_environment.md` (the scored artifact) and `nf_w3_preregistration.md`
(what was decided in advance). Every number here is read off the committed JSON; nothing is
re-derived by hand. `best_alpha = 0`; **deploy-held** — this story serves nothing.

---

## 1. The verdict, in one paragraph

**The game-environment channel is REAL and MEASURABLE at the player level — and almost entirely
UNFORECASTABLE from the allowed contract.** A peeking oracle that is handed the *realized* team
play count and pass share for the target week improves the NF-W1 champion's player-week CRPS at
**all four positions, on 8 of 8 folds, with an interval that excludes zero** (+0.0664 QB / +0.0781
RB / +0.0528 WR / +0.0394 TE — 2.0–3.1% of champion CRPS). The **modeled** environment captures
**2–4% of that ceiling** and moves the player projection **not at all**: `champion_env` TIES the
champion at QB/RB/WR and is negative at TE. NF-W3 is therefore a **recorded null, not a served
model** — the captured-stays-captured discipline, applied to the first V1 component.

| | QB | RB | WR | TE |
|---|---|---|---|---|
| `champion_env` − `champion` (CRPS/wk) | +0.0014 | +0.0027 | +0.0019 | −0.0017 |
| CI95 | [−0.0107, +0.0135] | [−0.0053, +0.0107] | [−0.0057, +0.0094] | [−0.0078, +0.0043] |
| fold wins (of 8, clause needs 6) | 5 | 5 | 5 | 2 |
| **⭐ realized-env ORACLE** | **+0.0664** | **+0.0781** | **+0.0528** | **+0.0394** |
| oracle CI95 | [+0.0393,+0.0935] | [+0.0574,+0.0989] | [+0.0391,+0.0665] | [+0.0233,+0.0555] |
| oracle fold wins | **8/8** | **8/8** | **8/8** | **8/8** |
| model as % of ceiling | 2.1% | 3.5% | 3.6% | −4.3% |
| oracle as % of champion CRPS | 2.57% | 3.12% | 1.98% | 2.17% |

**States:** QB/RB/WR `POWER_LIMITED` (calendar-bound and far out of reach — ~147 / 18 / 33 seasons
of half-season folds for the DSR gate at the observed per-fold Sharpe); **TE `GENUINE_ABSENCE`**
(a negative point estimate — ⛔ no re-test trigger is published, per MH2).

## 2. Why Layer B is null — Layer A already says it

The two component targets are not equally learnable, and the difference is the whole mechanism:

| target | climatology | team-EB foil | winner | own-form peeking oracle | headroom captured |
|---|---|---|---|---|---|
| `off_plays` | 4.8681 | 4.8552 | 4.8185 (`negbin_glm`) | 4.4466 | **12%** of a 8.7%-of-scale headroom |
| `pass_share` | 0.0614 | 0.0589 | 0.0575 (`betabinom`) | 0.0533 | **48%** of a 13.2%-of-scale headroom |

- **Team play volume is nearly pure league-level noise.** Knowing *which team* is playing buys
  0.013 CRPS over league climatology (0.3% of scale); the best of four learner classes buys 0.05
  (1.0%), and even a same-form model that PEEKS at the test block only reaches 4.45. The verdict
  is `DSR_UNREACHABLE`: the winner's per-fold Sharpe (0.588) sits below the 4-arm field's deflated
  benchmark (0.837), so **no fold count clears it** — and the interval spans zero, so the
  three-way verdict word is `TIES`, not `BEATS`, despite a positive point estimate.
- **Pass share IS partly learnable** — `betabinom` beats the team-EB foil by +0.0014 on **8/8
  folds**, PBO 0.0, p = 0.0018, clearing BH in **both** declared families. It fails only DSR
  (0.881 vs 0.95), i.e. `POWER_LIMITED`. It is a genuine, reproducible, and very small effect.

⇒ The environment layer transmits nothing downstream because the half of it that matters most for
volume of opportunity (plays) is barely forecastable, and the half that is forecastable (share)
moves player outcomes too little to survive.

### Three corroborating anchors say the same thing three different ways

1. **The matched foil-env anchor.** Building the env block from the *foil* instead of the learned
   winner produces the same tie (−0.0037 / −0.0018 / −0.0002 / +0.0034). So the null is not "our
   learner is bad" — **team environment in ANY form is inert at the player level once the
   champion's own usage/snap features are present.**
2. **The shuffle control.** At WR and TE the real env block does not even beat env columns
   permuted across teams within week — the strongest available statement that the block carries
   no information there.
3. **The opponent adjustment is worse than nothing, again.** `foil_team_eb_matchup` LOSES to the
   flat `foil_team_eb` on **both** targets (5.2213 vs 4.8552; 0.0607 vs 0.0589). That is now the
   third independent replication in this vertical of "a scalar opponent tilt is a null" (NF1's
   DVP leg, NF-W1's `foil_matchup`, and now team-grain volume/share).

## 3. ⭐ What outlives the null: the ceiling is measured, small, and REAL

The single most decision-relevant number NF-W3 produces is not its own verdict — it is the
**oracle ceiling**, because it prices the entire remaining chain:

> Perfect, cheat-level knowledge of a team's play count and pass rate is worth **2.0–3.1% of
> player-week CRPS**, two-sided and on every fold.

That bounds NF-W5 → NF-W8 from above along this channel. It is **not zero** — an environment layer
is worth building if (and only if) it can be made materially more accurate than what lagged
league/team aggregates already deliver. It is also **not large**: even a perfect environment model
would move the product by ~2–3%, so the chain cannot be justified on this channel alone.

## 4. What this means for NF-W5 (the next component)

- ⛔ **Do not card NF-W5 as "opportunity allocation given a projected environment."** On these
  numbers the environment input contributes nothing the champion does not already have, and
  conditioning NF-W5 on a projected volume/share would inherit a component measured to be inert.
- ⭐ **Card NF-W5 against the ORACLE decomposition instead.** The right question is the one this
  story can now pose precisely: of the 2–3% ceiling, how much survives when the environment is
  *shared* across a game rather than used per player — i.e. is the value in the LEVEL (which this
  story shows is unforecastable) or in the CORRELATION structure (which NF-W8's simulator needs
  and which a point-projection gate like Layer B structurally cannot see)? **Layer B tested the
  level channel and only the level channel.** A shared game state can matter for the JOINT
  distribution (stacks, lineups) while being worth ~0 for a marginal per-player CRPS — and the
  v3 doc's own justification for the simulator (§9) is the joint, not the marginal.
- That is the honest successor: NF-W3's null narrows NF-W5's scope rather than blocking it, and it
  names the metric the successor must be judged on (a joint/correlation gate, doc §9.1/§10.1A),
  not the one that just failed.

## 5. Limitations, stated because the same tables show them

- **The env block is a POINT + spread, not a sample.** Layer B injects projected volume/share as
  features into a marginal player model; it does not simulate from a shared game state. A
  correlation benefit is structurally invisible to this design (see §4).
- **Train-row env values carry residual in-sample optimism.** They come from an expanding window
  inside the training span (season *s* predicted from seasons < *s*, two-season minimum), which
  removes most but not all of it. The residual biases the gate **against** NF-W3 — declared in the
  pre-registration, in that direction, before the run.
- **`pbo_ok` was mis-registered as a Layer-B gate.** CSCV resamples a *field*; Layer B fields one
  pre-registered contrast, so PBO there is **UNDEFINED, not failed**. The gate was left in place
  (⛔ a gate is not dropped after seeing it fail) and reported as undefined — and the null is
  measured not to rest on it: waiving `pbo_ok` still leaves `fold_consistency`, `dsr_ok` and
  `fdr_ok` refusing at every position, plus `beats_champion` at TE.
- **The matched-n control matches sample SIZE, not ERA.** `matched_n__<arm>` is the most recent
  block-sized slice of train while the oracle is the test block itself, so it bounds capacity and
  recency together.
- **`negbin_glm` and `betabinom` were selected in-fold, then reused as the Layer-B env forms.**
  Layer B therefore evaluates the *selected* component; its optimism is bounded by Layer A's own
  deflation, and the oracle anchor bounds the whole thing regardless of which arm won.

## 6. Defects found while building (all four are transferable)

**Data (found by guards, would have shipped silently):**

1. **`pbp.posteam` is normalised to CURRENT franchise codes while `schedules` keeps the ERA code**
   — pbp `LAC`/`LV` in 2016 vs schedule `SD`/`OAK`, `LV` through 2019. The team-grain join NaN'd
   exactly the relocated franchises, and **because pandas matches NaN against NaN those rows then
   CROSS-JOINED into duplicates** (34 rows in a 32-team week). The NF-W0a PIT guard refused all
   **65 affected weeks / 1,994 rows** fail-closed, which is the only reason it surfaced. NF-W1
   never saw it because `weekly_rosters` agrees with `schedules` — pbp is the odd source out.
2. **`scipy.stats.binom`/`betabinom` return NaN for a NON-INTEGER `n`**, and a 4-game rolling
   trial count is non-integer almost always ⇒ both T2 GLM arms emitted NaN on most rows and
   **`np.nanmean` silently scored them on a smaller population than the rest of the field**
   (`betabinom` 0.0626 → 0.0574 after the fix — from losing to the foil to beating it). A
   leaderboard whose arms are scored on different populations is not a comparison; the reducer now
   refuses a non-finite predictive.

**Reporting (found by reading the first artifact, and the reason this file exists):**

3. **`cv_power.classify_null` published a nonsensical, actively misleading trigger for Layer B.**
   Called with the honest `n_arms=1`, `pbo_evaluable` is false — but the instrument renders that
   as a FOLD shortage, printing "8 fold(s) < 4" at **eight** folds and prescribing **"−4 more
   fold(s)"**. That record tells a future reader to buy seasons for a null no season count can
   move. Hand-corrected (the third such correction in this vertical: NF-W2 → CONSTRAINT_REFUSED,
   NF-D18 → the 8th state, now the field-size axis), with the instrument's own verdict recorded
   beside the correction rather than discarded.
4. ⭐ **A verdict must be DERIVED, not stored — one level up from NF-W2e's sentence rule.** Fixing
   (3) would have cost a 26-minute re-run if the *states* had only ever been written at scoring
   time; `--rewrite-report` now re-derives gates, both BH families, null states and verdicts from
   the stored per-fold selections, prints what moved, and stamps `verdict_corrected_from` in the
   artifact. The correction took seconds and is visible in the record.

Also caught: `classify_null`'s "the remedy is a SMALLER field" text is flagged **SUSPECT — NOT
ADVICE** on both Layer-A targets, because this story's 4-arm family is the pre-registered §0.5
minimum and shrinking below it would be the retired post-hoc field (MH2.2).

## 7. Anchors and gates behaved (the run is trustworthy)

PIT: 175 weeks / 5,278 team-game records checked, **0 rows dropped** after the franchise-code fix.
All four degenerates lose on both targets (`nihilist_zero` 61.70 / 0.574; `zero_width` and
`max_width` both lose — a constraint a degenerate satisfies is fine, a criterion one wins is
fatal). The permuted arm loses with its lift over the foil negative and p ≥ 0.96. Per-form oracle
floors hold at matched n on both targets; the one strict failure (`knn_quantile` on `pass_share`,
0.0585 vs its 0.0593 oracle) is the documented NF1.9 (f) capacity case — that oracle is fit on a
274-row test block and is itself beaten by the same form at matched n — and **both readings are
reported**. Coverage clears its floor everywhere. At 8 folds no gate is structurally unattainable
(clause 6/8 attainable, PBO evaluable for Layer A, sign floor 0.0039 < 0.10, `dsr_ceiling` 0.9999
vs a 0.95 gate) ⇒ **these nulls are findings, not design artifacts.**
