# NCAAF-P2.1 S1b — the SERVED pace representation, registered

**Status (2026-08-17): decided as part of S1-serve. The served contract `strength_pace` carries
`pace_axis` = {`pace_sum`, `pace_diff`} — the 2-column composite, NOT the 8-column S1 primary.**

This is a **representation** decision inside the shipping story, exactly where the S1 read-out
(§3) said it belonged: *"whichever representation serves has to be the one the mean map carries,
so it should be folded into the serving story rather than run as a separate research session."*

---

## 1. What is and is not being claimed

S1's pre-registration fixed the *ship candidate* as the P2.1 H9 block verbatim (8 columns) and said
a better sibling is a **successor hypothesis, never a promotion from that run** — "pick the best of
three" is precisely the search the registration bounds. S1 honoured that: all three arms cleared
every arm-level gate and the two siblings were recorded
`FIELD_MEMBER_CLEARED_NOT_PROMOTABLE`.

S1b is that successor, and it is a **cheap one** because the arm it promotes is not a new candidate
— it is a *declared member of S1's own field that already cleared every arm-level gate in the run*:

| arm | ΔCRPS vs reference | folds | p | S1 verdict |
|---|---|---|---|---|
| `pace` (8 cols — the S1 PRIMARY) | +0.0620 | 8/8 | 0.0020 | PROMOTED |
| `pace_axis` = {`pace_sum`, `pace_diff`} | **+0.0803** | 8/8 | 0.0005 | field member, cleared |
| `pace_total_axis` = {`pace_sum`} | +0.0789 | 8/8 | 0.0008 | field member, cleared |

⭐ **The honest caption.** The +0.018 margin of `pace_axis` over the primary is an S1 MEASUREMENT,
not a fresh independent one; no new scoring run was performed for S1b. What S1b changes is which
already-gated arm is wired into the serving path. It is a registration change, and it is recorded
here rather than absorbed silently.

## 2. Why the composite, on mechanistic grounds (declared, not fitted)

S1-V4 predicted this ordering **before** the run and the result matched:

* `seconds_per_play ≡ possession_seconds_per_game / off_plays_per_game` is an **exact ratio
  identity** (verified on the cache, max deviation 0.0), and `pace_sum` / `pace_diff` are exact
  linear combinations of the two per-side `seconds_per_play` levels.
* So the 8-column block **spans a lower-dimensional space than 8**. Under a standardized ridge the
  six redundant per-side levels do not add span — they add penalty. The composites express the same
  subspace in the coordinates the hypothesis was written in ("the SUM on the total axis, where pace
  should act" — P2.1 H9).

⇒ The composite is the representation the hypothesis *states*; the 8-column block was the P2.1
column bundle. Choosing it is a mechanistic call with a pre-registered rationale, not a leaderboard
pick — which matters, because "the best of three" is exactly what S1's registration forbade.

## 3. Why not `pace_total_axis` (`pace_sum` alone)

`pace_axis` beat it by +0.0014 — **inside the 1e-3-scale tie band**, i.e. no measurable margin-axis
content. Two arms that tie do not get separated by their point estimates (NF1.8: a rank statistic
cannot tell a tie from a win). The tie is broken on a pre-existing structural preference, not on
the tied metric: the served mean model has **two** targets, and `pace_diff` is the only channel
through which pace can reach the **margin** mean at all. Dropping it would hard-code "pace has zero
margin content" into the artifact on the strength of a tie. Keeping it costs one ridge-penalised
coefficient and lets the data say so instead — which the served coefficient table then shows
explicitly.

## 4. What ships

* `bakeoff_ncaaf_game.SERVED_PACE_COLS = ("pace_sum", "pace_diff")` — the single source of truth,
  read by the contract resolver AND by the mean artifact's `pace_columns`, so the representation
  that serves and the one the mean map carries **cannot** diverge (guard-pinned).
* contract `strength_pace` = `strength_only` ∪ `SERVED_PACE_COLS`, registered in
  `POST_P1_4_CONTRACTS` — **outside** P1.4's frozen deflation field, because pace was certified
  under its own registration (P2.1 → S1), not inside P1.4's search.
* the derivation is the SHARED `p2_1_blocks.derive_pace_composites`, the same function P2.1's
  battery assemble calls — so the serving columns are byte-identical to the certified ones.

## 5. What is NOT re-litigated here

`best_alpha = 0`. S1 is a calibration ship (+0.062 CRPS ≈ 0.3 % of the reference's 18.52), not an
edge claim; the vs-close leg is unchanged and both sides sit under the −110 breakeven. S1b does not
change that framing by a single word — it changes which of two already-gated columns sets serves.

## 6. Reading the S1b margin forward

If a later story wants to *claim* the +0.018, it needs its own fresh registration and run — this
record explicitly does not license quoting it as an independently-earned lift. What it licenses is
serving the arm, on the mechanistic argument in §2, with the measurement disclosed.

---

_**Amendment 2026-08-17 (appended; the body above is unchanged).** §6's open question — whether a
later story can *claim* the +0.018 — has been answered by a fresh §0.5 registration and run:
**it cannot.** See [`ncaaf_p2_1_s1b_preregistration.md`](./ncaaf_p2_1_s1b_preregistration.md) and
[`ncaaf_p2_1_s1b_readout.md`](./ncaaf_p2_1_s1b_readout.md) — verdict `MARGIN_NOT_EARNED` (the
matched pair clears DSR at 0.9687 but fails BH-FDR and PBO). The sign holds in 6/8 folds, so the
pre-registered revert trigger did not fire and **the served representation is unchanged**; it
continues to stand on §2's mechanistic argument exactly as this document says it does. What changed
is that the margin is now MEASURED to be non-quotable rather than merely undeclared._
