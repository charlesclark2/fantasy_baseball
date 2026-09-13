# NF-INJ4b-SHIP — the measurement battery on the publish candidate

**Generated 2026-09-13T22:19:11+00:00 · season 2026.** `best_alpha = 0`. ⛔ **This run publishes nothing.** It measures what the wired discount does to the board the operator is deciding about.

---

## 1. What board these numbers describe

| field | value |
|---|---|
| board generated at | `2026-09-13T14:19:12.836904+00:00` |
| projections sha256 (16) | `0d02b827098658ea` |
| ADP as-of | `2026-09-13` |
| ECR as-of | `2026-09-10` |
| sleeper status as-of | `2026-09-13T13:30:17.090380+00:00` |
| designation feed rows | 114 |
| designation census | `{'Questionable': 76, 'Out': 20, 'Doubtful': 2, 'UNINTERPRETABLE': 16}` |

### ⛔ The capture-pinned REBUILD precondition: **REFUSED**

Measured against **this capture** (the shared helper is pinned to NF-INJ2c's own baseline directory, so its figures describe a different board):

| market input | this capture served | local cache | match |
|---|---|---|---|
| ADP | `2026-09-13` | `None` | ⛔ |
| ECR | `2026-09-10` | `None` | ⛔ |

⚠️ a local cache reading None means this WORKTREE has none at all — the market caches are gitignored (NF-INFRA1), so they are absent from a fresh worktree and live only in the main checkout.

The registered ship path's step 1 — a full rebuild against a pinned baseline with matched market vintages — is **not reachable from this checkout**, and the precondition was RUN rather than assumed:

```
⛔ MARKET VINTAGE MISMATCH — refusing before the arms are built.

  · ADP: served 2026-08-31, LOCAL CACHE UNREADABLE OR ABSENT. Refresh it, then re-capture:
      uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_adp_ingest --from 2026 --to 2026 --refresh
  · ECR: served 2026-09-01, LOCAL CACHE UNREADABLE OR ABSENT. Refresh it, then re-capture:
      uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_ecr_ingest --from 2026 --to 2026 --refresh

WHY: `apply_2026` builds every arm with `market_refresh=False`, so the ordering reads the ON-DISK caches. `market_rank` is ECR-primary and is a feature at all four positions, so a cache from a different day than the served board produces a different within-position ordering and the pin cannot hold. On NF-INJ2c run 1 that cost a full VOID run at a worst difference of 84.72.
⚠️ A vendor snapshot is NOT recoverable once its day rolls — FantasyPros serves only the current one and the lake's ecr_benchmark asset is season-partitioned and overwritten. If the served board's vintage has already passed, ⛔ do NOT chase it: wait for the next publish, refresh the caches promptly after it, and capture then.
```

⚠️ **The ECR vintage is UNRECOVERABLE, not merely stale.** FantasyPros serves only the CURRENT snapshot, so the board's own `ecr_as_of` cannot be re-fetched once its day has rolled (NF-INJ2c). ⛔ Do not chase it. The rebuild belongs to the operator, in an environment whose caches match — which is where NF-INJ4b's closeout already put it. **Every leg below therefore runs on the PUBLISHED board with the SERVED constants applied, FIRST-ORDER.**

---

## 2. ⭐ The no-op control — why anything below can be trusted

With an EMPTY designation map the candidate must reproduce the baseline. Measured across **14 boards** at an explicit epsilon of `1e-09`: ✅ PASS — worst absolute difference `0.000e+00`, 0 ranks moved.

⛔ Representation-tolerant, never bitwise: two rebuilds of this board at the SAME commit differ in the rookie band at 0–21 material cells, so a bitwise pin reports motion this repo cannot attribute (card QkpAHBYa).

---

## 3. The per-designation magnitude actually being served

| designation | E[games missed] | rate multiplier | players on the live feed |
|---|---|---|---|
| `out` | 2.3145 | ×0.8639 | 20 |
| `doubtful` | 0.8052 | ×0.9526 | 2 |
| `questionable` | 0.6301 | ×0.9629 | 76 |

⚠️ 16 further player(s) carry a value the feed publishes but we cannot interpret. They are DISCLOSED as unknown and **priced at nothing** — never silently dropped, and never guessed at.

---

## 4. The material diff, population-scoped

At an epsilon of `1e-09`.

| population | rows (summed over boards) | material cells moved | worst move |
|---|---|---|---|
| designated | 840 | 3444 | 49.5404 (standard_10.ptsP90) |
| undesignated | 11340 | 0 | 0.0000 |
| rookies | 1134 | 0 | 0.0000 |
| veterans | 11046 | 3444 | 49.5404 (standard_10.ptsP90) |

✅ Every column the discount must NOT touch (`adp`, `repl`, `bye`, `pos`, `team`, `rookie`) is unchanged on every board.

---

## 5. NF-INJ1's envelope and NF-RATE1's suppression

Suppressed rows, summed over the 14 boards: baseline **0**, candidate **0** (Δ +0).

⭐ **The full-season rate is INVARIANT under this discount, and that is measured rather than argued.** The rate is `pts × 17 ÷ games` and the discount scales `pts` and `games` by the SAME multiplier, so it cancels. Worst rate move on any capped row across all boards: `2.842e-14`. ⇒ the suppression population cannot move, so NF-RATE1's guard stays green here for a STRUCTURAL reason, not a lucky one.

---

## 5b. NF-INJ1's COHERENCE on the served projections

| | in scope | unevaluable | violating players |
|---|---|---|---|
| baseline | 796 | 0 | **8** |
| candidate | 796 | 0 | **8** |

**UNCHANGED** (Δ +0). The 8 violations on the published board are a PRE-EXISTING property of it, not something this discount did; what matters for the decision is that it neither creates nor clears any — which follows from the same invariance as §5: scaling the line and the games together leaves the implied per-game rate untouched.

---

## 6. The whole-board placement read

Verdict — baseline **SANE** (0 failing), candidate **SANE** (0 failing).

⭐ **The decision-relevant question is not whether the candidate PASSES — it is whether it fails anything the baseline does not.** A gate the published board already breaches is a pre-existing property of the board, and reading it as damage this discount did would attribute someone else's finding to this ship.

| gate | baseline | candidate | introduced by the discount? |
|---|---|---|---|
| `band_integrity` | True | True | no |
| `position_survival` | True | True | no |
| `rookie_placement_cap` | True | True | no |
| `within_position_order` | True | True | no |

✅ **No placement gate that passes on the published board fails under the discount.**


⚠️ Read the SUPERFLEX rows on their own: NF-W8-0's VOR shield is ADDITIVE-only and assumes the group is not cross-pooled. This discount is MULTIPLICATIVE and QB IS cross-pooled in superflex, so the shield does not hold there (NF-TR2b).

---

## 7. The interval revalidation — ⛔ **STRUCTURALLY INACTIVE, not passed**

the designation channel is gated on the current season, and the NF1.9 revalidation scores historical rookie/veteran panels — it cannot reach a row the discount moved.

- season-gated: `True` · availability runs before the band attach: `True`
- a capped player's 80% band is attached to his CAPPED point — the identical treatment the formal availability cap has always received; the band's calibration lives in the panel, which this change cannot touch.

⛔ It is NOT reported as a passed interval check. An inactive read presented as a pass is the error NF-INJ4b §6 avoided for the preseason placement read, and the reason that refusal was correct then is the reason this one is correct now (NF1.7 (a) / NF-D20).

---

## 8. Top rank moves per config

- `full_ppr_10` — 60 designated, 520 ranks moved, max |move| 124, baseline rank agrees with published 1.0000
- `full_ppr_12` — 60 designated, 559 ranks moved, max |move| 142, baseline rank agrees with published 1.0000
- `full_ppr_3wr_10` — 60 designated, 560 ranks moved, max |move| 161, baseline rank agrees with published 1.0000
- `full_ppr_3wr_12` — 60 designated, 545 ranks moved, max |move| 218, baseline rank agrees with published 1.0000
- `half_ppr_10` — 60 designated, 616 ranks moved, max |move| 202, baseline rank agrees with published 1.0000
- `half_ppr_12` — 60 designated, 585 ranks moved, max |move| 280, baseline rank agrees with published 1.0000
- `half_ppr_3wr_10` — 60 designated, 611 ranks moved, max |move| 241, baseline rank agrees with published 1.0000
- `half_ppr_3wr_12` — 60 designated, 531 ranks moved, max |move| 197, baseline rank agrees with published 1.0000
- `standard_10` — 60 designated, 584 ranks moved, max |move| 206, baseline rank agrees with published 1.0000
- `standard_12` — 60 designated, 511 ranks moved, max |move| 201, baseline rank agrees with published 1.0000
- `standard_3wr_10` — 60 designated, 598 ranks moved, max |move| 257, baseline rank agrees with published 1.0000
- `standard_3wr_12` — 60 designated, 551 ranks moved, max |move| 284, baseline rank agrees with published 1.0000
- `superflex_10` — 60 designated, 508 ranks moved, max |move| 127, baseline rank agrees with published 1.0000
- `superflex_12` — 60 designated, 572 ranks moved, max |move| 95, baseline rank agrees with published 1.0000

**Top moves, `superflex_12`** (the config the VOR shield does NOT protect):

| player | pos | designation | rank before | rank after | move | games before → after |
|---|---|---|---|---|---|---|
| Sam Darnold | QB | `Out` | 74 | 169 | -95 | 16.5 → 14.25 |
| TreVeyon Henderson | RB | `Out` | 86 | 176 | -90 | 12.0 → 10.37 |
| Michael Penix Jr. | QB | `Out` | 319 | 368 | -49 | 6.5 → 5.62 |
| Tutu Atwell | WR | `Out` | 423 | 470 | -47 | 7.9 → 6.82 |
| Tua Tagovailoa | QB | `Out` | 196 | 231 | -35 | 15.0 → 12.96 |
| Jordan James | RB | `Out` | 390 | 424 | -34 | 5.6 → 4.84 |
| Tory Horton | WR | `Out` | 298 | 329 | -31 | 7.5 → 6.48 |
| Rome Odunze | WR | `Questionable` | 101 | 131 | -30 | 14.8 → 14.25 |
| Brock Bowers | TE | `Out` | 36 | 63 | -27 | 15.1 → 13.04 |
| Raheem Mostert | RB | `Questionable` | 590 | 607 | -17 | 9.9 → 9.53 |
| Jerome Ford | RB | `Questionable` | 512 | 526 | -14 | 8.7 → 8.38 |
| Patrick Taylor Jr. | RB | `Questionable` | 541 | 555 | -14 | 4.3 → 4.14 |
| JuJu Smith-Schuster | WR | `Questionable` | 481 | 494 | -13 | 10.6 → 10.21 |
| Devontez Walker | WR | `Questionable` | 483 | 496 | -13 | 7.4 → 7.13 |
| Ainias Smith | WR | `Questionable` | 510 | 523 | -13 | 2.7 → 2.6 |
| Jermar Jefferson | RB | `Questionable` | 677 | 690 | -13 | 3.5 → 3.37 |
| Devin Neal | RB | `Questionable` | 429 | 441 | -12 | 4.1 → 3.95 |
| LeQuint Allen Jr. | RB | `Questionable` | 389 | 400 | -11 | 9.7 → 9.34 |
| Nick Kallerup | TE | `Out` | 576 | 587 | -11 | 7.1 → 6.13 |
| Alvin Kamara | RB | `Questionable` | 264 | 274 | -10 | 11.5 → 11.07 |
| Raheem Blackshear | RB | `Questionable` | 621 | 631 | -10 | 4.1 → 3.95 |
| Gabe Davis | WR | `Questionable` | 673 | 683 | -10 | 8.4 → 8.09 |
| Dalevon Campbell | WR | `Questionable` | 697 | 707 | -10 | 3.7 → 3.56 |
| Xavier Weaver | WR | `Questionable` | 686 | 695 | -9 | 8.0 → 7.7 |
| Jamari Thrash | WR | `Questionable` | 624 | 632 | -8 | 6.8 → 6.55 |

---

## 9. ⛔ What this battery does NOT establish

- **Not a rebuild.** Replacement levels are the published board's, and NF1.5's ordering permutation has not re-run. NF-INJ1 measured that step handing **+36.4%** of an availability discount BACK, so a rebuild's rank moves will differ — most plausibly they will be SMALLER. That is the operator's step and it is the one that produces the real publish candidate.
- **Not a publish.** Nothing here writes a served artifact.
- **Not a re-reading of NF-INJ4b's gates.** They are settled (E2.1-r); this measures the SHIP, not the model.
