# NF-INJ4b-SHIP — OPERATOR PACKET: ship the weekly-designation discount?

**Prepared 2026-09-13T22:19:11+00:00 · season 2026 · `best_alpha = 0`.** Nothing in this session published anything. The decision is yours.

---

## ⚠️⚠️ Read this first: **merging the PR IS the deploy**

The season board is not like the API Lambda. It is published by `sports_nfl_board_publish_schedule` — a Dagster schedule that ships `default_status=RUNNING` and runs `export_draft_board_json --publish` **daily at 07:15 America/Los_Angeles** from the box image, which is built from `main` on merge.

⇒ **There is no separate publish step to approve later.** Merging this PR to `dev` and on to `main` means the next scheduled build serves the discount and NF-C9's new copy becomes true. That is the MH2.1 (c) promotion-mechanics landmine on the fantasy board, and it is why the copy change and the changelog line are IN this PR rather than a follow-up: a declaration must not outrun its production, and here they arrive together or not at all.

**If the answer is no:** the PR does not merge. It is not a case of pulling the copy and keeping the wiring — the wiring IS the serve.

---

## 1. What you are approving

When a club lists a player Out / Doubtful / Questionable on the game-status report our injury feed carries, his projected games are discounted by a measured average of what past listings like it have cost. NF-INJ4b certified the model (9 of 9 registered gates under a matched-resolution anchor); those gates are settled and this packet does not re-open them.

| designation | E[games missed] | multiplier on projected games | players on the live feed |
|---|---|---|---|
| **Out** | 2.3145 | x0.8639 | 20 |
| **Doubtful** | 0.8052 | x0.9526 | 2 |
| **Questionable** | 0.6301 | x0.9629 | 76 |

It touches **60 of 870 rows** on each board. 16 further player(s) carry a feed value we cannot interpret: they are shown as 'unknown' and **priced at nothing** — never guessed at, never silently dropped.

⛔ The no-designation baseline hazard (x0.9906) is **not** served. Applying it would discount ~2,400 undesignated players — a board-wide level shift, which is a different change from the one that was certified.

---

## 2. The combined read on the publish candidate

| check | result |
|---|---|
| no-op control (empty map ⇒ zero movement) | ✅ PASS, worst `0.0e+00` at eps `1e-09` |
| baseline rank reproduces the published `ovrRank` | 1.0000 (min over 14 boards) |
| whole-board placement gates newly failing | ✅ none |
| NF-INJ1 coherence (violating players) | UNCHANGED — 8 → 8 |
| NF-RATE1 full-season-rate suppression | 0 → 0 (Δ +0) |
| columns the discount must not touch | ✅ unchanged |
| interval revalidation | ⛔ STRUCTURALLY_INACTIVE — reported as such, **not** as a pass |

⭐ The suppression and coherence rows are **structurally** unchanged, not luckily so: the full-season rate is `pts x 17 / games` and the discount scales `pts` and `games` by the same multiplier, so it cancels (worst rate move on any capped row across all boards: `2.8e-14`).

---

## 3. What moves, per config

| config | designated | ranks moved | max abs move |
|---|---|---|---|
| `full_ppr_10` | 60 | 520 | 124 |
| `full_ppr_12` | 60 | 559 | 142 |
| `full_ppr_3wr_10` | 60 | 560 | 161 |
| `full_ppr_3wr_12` | 60 | 545 | 218 |
| `half_ppr_10` | 60 | 616 | 202 |
| `half_ppr_12` | 60 | 585 | 280 |
| `half_ppr_3wr_10` | 60 | 611 | 241 |
| `half_ppr_3wr_12` | 60 | 531 | 197 |
| `standard_10` | 60 | 584 | 206 |
| `standard_12` | 60 | 511 | 201 |
| `standard_3wr_10` | 60 | 598 | 257 |
| `standard_3wr_12` | 60 | 551 | 284 |
| `superflex_10` ⭐ | 60 | 508 | 127 |
| `superflex_12` ⭐ | 60 | 572 | 95 |

⭐ **Read the two superflex configs on their own rows.** NF-W8-0's VOR 'shield' — a per-group level shift cancelling because the group's own replacement absorbs it — is ADDITIVE-ONLY and assumes the group is not cross-pooled. This discount is MULTIPLICATIVE and QB **is** cross-pooled in superflex, so the shield does not hold there (NF-TR2b).

### Top 25 moves — `superflex_10`

| player | pos | designation | rank | → | move | games |
|---|---|---|---|---|---|
| Michael Penix Jr. | QB | Out | 430 | 557 | -127 | 6.5 → 5.62 |
| TreVeyon Henderson | RB | Out | 110 | 173 | -63 | 12.0 → 10.37 |
| Tutu Atwell | WR | Out | 472 | 533 | -61 | 7.9 → 6.82 |
| Jordan James | RB | Out | 400 | 446 | -46 | 5.6 → 4.84 |
| Tory Horton | WR | Out | 314 | 347 | -33 | 7.5 → 6.48 |
| Sam Darnold | QB | Out | 163 | 192 | -29 | 16.5 → 14.25 |
| Tua Tagovailoa | QB | Out | 234 | 261 | -27 | 15.0 → 12.96 |
| Ty Johnson | RB | Questionable | 383 | 401 | -18 | 10.0 → 9.63 |
| Brock Bowers | TE | Out | 30 | 46 | -16 | 15.1 → 13.04 |
| LeQuint Allen Jr. | RB | Questionable | 397 | 413 | -16 | 9.7 → 9.34 |
| Dante Miller | RB | Questionable | 653 | 666 | -13 | 1.3 → 1.25 |
| Devin Neal | RB | Questionable | 451 | 463 | -12 | 4.1 → 3.95 |
| Devontez Walker | WR | Questionable | 542 | 554 | -12 | 7.4 → 7.13 |
| Jermar Jefferson | RB | Questionable | 640 | 652 | -12 | 3.5 → 3.37 |
| JuJu Smith-Schuster | WR | Questionable | 540 | 551 | -11 | 10.6 → 10.21 |
| Rome Odunze | WR | Questionable | 156 | 166 | -10 | 14.8 → 14.25 |
| Kene Nwangwu | RB | Out | 766 | 776 | -10 | 6.8 → 5.87 |
| Sean Tucker | RB | Doubtful | 297 | 306 | -9 | 9.3 → 8.86 |
| Patrick Taylor Jr. | RB | Questionable | 560 | 569 | -9 | 4.3 → 4.14 |
| Raheem Mostert | RB | Questionable | 579 | 588 | -9 | 9.9 → 9.53 |
| Xavier Weaver | WR | Questionable | 693 | 702 | -9 | 8.0 → 7.7 |
| Anthony Firkser | TE | Questionable | 385 | 393 | -8 | 6.4 → 6.16 |
| Jerome Ford | RB | Questionable | 544 | 552 | -8 | 8.7 → 8.38 |
| Raheem Blackshear | RB | Questionable | 597 | 605 | -8 | 4.1 → 3.95 |
| Gabe Davis | WR | Questionable | 683 | 691 | -8 | 8.4 → 8.09 |

### Top 25 moves — `superflex_12`

| player | pos | designation | rank | → | move | games |
|---|---|---|---|---|---|
| Sam Darnold | QB | Out | 74 | 169 | -95 | 16.5 → 14.25 |
| TreVeyon Henderson | RB | Out | 86 | 176 | -90 | 12.0 → 10.37 |
| Michael Penix Jr. | QB | Out | 319 | 368 | -49 | 6.5 → 5.62 |
| Tutu Atwell | WR | Out | 423 | 470 | -47 | 7.9 → 6.82 |
| Tua Tagovailoa | QB | Out | 196 | 231 | -35 | 15.0 → 12.96 |
| Jordan James | RB | Out | 390 | 424 | -34 | 5.6 → 4.84 |
| Tory Horton | WR | Out | 298 | 329 | -31 | 7.5 → 6.48 |
| Rome Odunze | WR | Questionable | 101 | 131 | -30 | 14.8 → 14.25 |
| Brock Bowers | TE | Out | 36 | 63 | -27 | 15.1 → 13.04 |
| Raheem Mostert | RB | Questionable | 590 | 607 | -17 | 9.9 → 9.53 |
| Jerome Ford | RB | Questionable | 512 | 526 | -14 | 8.7 → 8.38 |
| Patrick Taylor Jr. | RB | Questionable | 541 | 555 | -14 | 4.3 → 4.14 |
| JuJu Smith-Schuster | WR | Questionable | 481 | 494 | -13 | 10.6 → 10.21 |
| Devontez Walker | WR | Questionable | 483 | 496 | -13 | 7.4 → 7.13 |
| Ainias Smith | WR | Questionable | 510 | 523 | -13 | 2.7 → 2.6 |
| Jermar Jefferson | RB | Questionable | 677 | 690 | -13 | 3.5 → 3.37 |
| Devin Neal | RB | Questionable | 429 | 441 | -12 | 4.1 → 3.95 |
| LeQuint Allen Jr. | RB | Questionable | 389 | 400 | -11 | 9.7 → 9.34 |
| Nick Kallerup | TE | Out | 576 | 587 | -11 | 7.1 → 6.13 |
| Alvin Kamara | RB | Questionable | 264 | 274 | -10 | 11.5 → 11.07 |
| Raheem Blackshear | RB | Questionable | 621 | 631 | -10 | 4.1 → 3.95 |
| Gabe Davis | WR | Questionable | 673 | 683 | -10 | 8.4 → 8.09 |
| Dalevon Campbell | WR | Questionable | 697 | 707 | -10 | 3.7 → 3.56 |
| Xavier Weaver | WR | Questionable | 686 | 695 | -9 | 8.0 → 7.7 |
| Jamari Thrash | WR | Questionable | 624 | 632 | -8 | 6.8 → 6.55 |

### Top 25 moves — `half_ppr_12`

| player | pos | designation | rank | → | move | games |
|---|---|---|---|---|---|
| Tua Tagovailoa | QB | Out | 494 | 774 | -280 | 15.0 → 12.96 |
| Sam Darnold | QB | Out | 242 | 329 | -87 | 16.5 → 14.25 |
| Tutu Atwell | WR | Out | 450 | 511 | -61 | 7.9 → 6.82 |
| Jordan James | RB | Out | 346 | 382 | -36 | 5.6 → 4.84 |
| TreVeyon Henderson | RB | Out | 50 | 85 | -35 | 12.0 → 10.37 |
| Rome Odunze | WR | Questionable | 100 | 132 | -32 | 14.8 → 14.25 |
| Tory Horton | WR | Out | 298 | 327 | -29 | 7.5 → 6.48 |
| Brock Bowers | TE | Out | 28 | 55 | -27 | 15.1 → 13.04 |
| Raheem Mostert | RB | Questionable | 520 | 536 | -16 | 9.9 → 9.53 |
| JuJu Smith-Schuster | WR | Questionable | 548 | 563 | -15 | 10.6 → 10.21 |
| Kene Nwangwu | RB | Out | 695 | 710 | -15 | 6.8 → 5.87 |
| LeQuint Allen Jr. | RB | Questionable | 359 | 371 | -12 | 9.7 → 9.34 |
| Ty Johnson | RB | Questionable | 339 | 350 | -11 | 10.0 → 9.63 |
| Devontez Walker | WR | Questionable | 505 | 516 | -11 | 7.4 → 7.13 |
| Ainias Smith | WR | Questionable | 573 | 584 | -11 | 2.7 → 2.6 |
| Antonio Gibson | RB | Questionable | 637 | 648 | -11 | 6.6 → 6.36 |
| Malik Nabers | WR | Questionable | 43 | 53 | -10 | 11.9 → 11.46 |
| Jerome Ford | RB | Questionable | 460 | 470 | -10 | 8.7 → 8.38 |
| Sean Tucker | RB | Doubtful | 258 | 267 | -9 | 9.3 → 8.86 |
| Patrick Taylor Jr. | RB | Questionable | 468 | 477 | -9 | 4.3 → 4.14 |
| Anthony Firkser | TE | Questionable | 423 | 431 | -8 | 6.4 → 6.16 |
| DJ Turner | WR | Questionable | 753 | 761 | -8 | 4.5 → 4.33 |
| Alvin Kamara | RB | Questionable | 244 | 251 | -7 | 11.5 → 11.07 |
| John FitzPatrick | TE | Questionable | 340 | 346 | -6 | 10.7 → 10.3 |
| Devin Neal | RB | Questionable | 393 | 399 | -6 | 4.1 → 3.95 |

---

## 4. ⛔ What this packet does NOT establish

- **It is not a capture-pinned rebuild.** The registered ship path's step 1 rebuilds the board against a pinned baseline with matched market vintages. It is **not reachable from this checkout**: the precondition was RUN and it **REFUSED**. The served board carries `ecr_as_of 2026-09-10` and FantasyPros serves only the CURRENT snapshot, so that vintage is **unrecoverable** (NF-INJ2c) — ⛔ do not chase it.
- **So every figure above is FIRST-ORDER**: replacement levels are the published board's, and NF1.5's ordering permutation has not re-run. NF-INJ1 measured that step handing **+36.4%** of an availability discount BACK, so a rebuild's rank moves will differ — most plausibly they will be **smaller** than the table above.
- **The interval revalidation is inactive, not passed** — the channel is season-gated and NF1.9 scores historical panels, so it cannot reach a row the discount moved.

---

## 5. If you approve — the sequence

**Step 1 — merge the PR (`nf-inj4b-ship` → `dev`), then `dev` → `main`.** This is the deploy; nothing else is required for the discount to serve.

**Step 2 — the next scheduled publish does the rest**, at 07:15 America/Los_Angeles. To watch it rather than wait: Dagster → `sports_nfl_board_publish_job`. Expected in the step log: `NF-INJ4b: designation discount applied to N of M rows`.

**Step 3 — verify the SERVED board actually moved (LAPTOP, ~30 s).** ⭐ This is the check that matters, and it is the reason the manifest stamp alone is not enough: a stamp records what a build was CONFIGURED to do, never what it DID (NF-C0e / NF-INJ3b-SHIP D6). This joins the PUBLISHED board back to the 60 designated players by normalised id and reports whether each one's games actually moved off the pre-ship figure.

```bash
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_ship_battery --verify-published
```

Expected on a board that HAS shipped: `✅ all N scoreable designated player(s) moved off their pre-ship games` (exit 0). ⭐ **The check is proven two-sided**: run against today's pre-ship board it reports `moved 0 · UNMOVED 58 · below the board's rounding 2` and exits 1 — so a green is informative rather than the only thing it can say (G100-D1: a check whose failure state is indistinguishable from its healthy state has not been verified).

⚠️ Two players' whole discount is smaller than the board's own one-decimal rounding, so they are individually UNSCOREABLE and are reported as their own state rather than as passes.

**Step 4 — if you want it OFF again (LAPTOP, one line + the copy).**

```bash
# in quant_sports_intel_models/football/nfl/fantasy/designation_discount_policy.py
#   SERVING_ENABLED: bool = False
```

⚠️ The rollback is **two** edits, and the guard enforces it: `WEEKLY_DESIGNATION_HOW_MODELLED` must revert to denying the adjustment in the SAME change, or `test_nf_inj4b_ship_wiring.py` goes red. A one-line flag flip feels complete and would leave the board advertising a discount of exactly zero.

---

## 6. The decision

**Ship the weekly-designation discount — yes or no?**

A yes moves 60 players per board by the multipliers in §1, moves 508–616 ranks per board, breaks no placement gate the published board passes, and changes neither the coherence nor the suppression population. A no leaves the board exactly as it is today and the PR unmerged.
