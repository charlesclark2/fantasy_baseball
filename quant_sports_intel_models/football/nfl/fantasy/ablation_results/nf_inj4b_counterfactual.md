# NF-INJ4b — operator packet: what the certified designation discount would do

**Generated 2026-09-04T06:20:17+00:00 · season 2026 · as-of 2026-09-04.** `best_alpha = 0`. ⛔ **DEPLOY-HELD — this run changes nothing.** The served Questionable / Doubtful / Out discount is EXACTLY ZERO, no production caller passes the designation channel, and the publish decision is the operator's.

---

## 1. ⚠️ The scope verdict — measured, not assumed

The 2026 regular season starts **2026-09-09** (read from the schedule, not assumed) and this run is as of **2026-09-04** — **5 days before Week 1**.

The registered scope rule admits REGULAR-SEASON designations only. The live feed carries **{'questionable': 119}** — the preseason shape (the game-status report only publishes Out/Doubtful once the season starts), so the rule **refuses all 119** of them.

⚠️ OUT OF SCOPE — every live designation is a PRESEASON tag, so the registered scope rule refuses all of them and the counterfactual is EXACTLY a no-op. This is INACTIVE, therefore UNINFORMATIVE: ⛔ it is NOT evidence the discount is small, and it is NOT a passed check (NF1.7 (a) / NF-D20). The pre-registration predicted this forward; it is measured here rather than assumed.

---

## 2. The per-designation magnitude — the number the operator is deciding about

Arm `desig_x_practice`, fitted on the full frame. ⚠️ the live feed carries no practice column, so every live row resolves at practice=unknown and BACKS OFF to the designation-only parent.

| designation | E[games missed] | rate multiplier on projected games |
|---|---|---|
| `out` | 2.3145 | ×0.8639 |
| `doubtful` | 0.8052 | ×0.9526 |
| `questionable` | 0.6301 | ×0.9629 |
| `none_listed` | 0.1590 | ×0.9906 |

---

## 3. ⭐ The no-op control — why any number below can be trusted at all

With an EMPTY designation map the counterfactual must move **exactly zero** ranks on every board, and the re-derived baseline rank must agree with the PUBLISHED `overall_rank` exactly. Measured across **14 boards**: ✅ PASS — 0 max rank moves, agreement 1.0000.

⚠️ This control is not decoration. Its first run reported **1,715 of 1,716 rows moving under an empty map**, because the board's key is `(config_name, n_teams)` and not `config_name` — every config publishes a 10-team AND a 12-team board with different replacement levels. Grouping on the config alone concatenated two boards and fabricated a rank move for almost every player.

---

## 4. ⛔ OUT-OF-SCOPE REHEARSAL — NOT A RESULT

The discount applied to the PRESEASON tags the registered scope rule REFUSES. Its purpose is to prove the board arithmetic, the id join, the label crosswalk and the renderer all execute against real producer output BEFORE the operator's Week-1 run — otherwise that run would be this code's first-ever execution. ⛔ **These numbers are not a counterfactual and must never be quoted as one.**

⚠️ It earned its place: with the rehearsal reporting a plausible ZERO, the label crosswalk was found to be silently broken (the feed emits `Questionable`, the model's levels are lower-case, so every multiplier resolved to NaN and defaulted to 1.0 — 89 designated players on the board and no discount applied, with no error). An unmapped label now REFUSES instead of defaulting.

| board | designated rows | ranks moved | max abs move |
|---|---|---|---|
| `full_ppr_3wr__10team` | 89 | 467 | 36 |
| `full_ppr_3wr__12team` | 89 | 473 | 32 |
| `full_ppr__10team` | 89 | 453 | 37 |
| `full_ppr__12team` | 89 | 470 | 37 |
| `half_ppr_3wr__10team` | 89 | 462 | 28 |
| `half_ppr_3wr__12team` | 89 | 491 | 33 |
| `half_ppr__10team` | 89 | 465 | 27 |
| `half_ppr__12team` | 89 | 468 | 28 |
| `standard_3wr__10team` | 89 | 475 | 30 |
| `standard_3wr__12team` | 89 | 485 | 35 |
| `standard__10team` | 89 | 479 | 28 |
| `standard__12team` | 89 | 485 | 28 |
| `superflex__10team` | 89 | 488 | 47 |
| `superflex__12team` | 89 | 475 | 37 |

**Top 25 moves, `superflex__12team`** (a per-position level change is NOT shielded in superflex — NF-TR2b):

| player | pos | designation | rank before | rank after | move | games |
|---|---|---|---|---|---|---|
| DK METCALF | WR | `questionable` | 96 | 133 | -37 | 15.48 |
| TREVEYON HENDERSON | RB | `questionable` | 108 | 143 | -35 | 12.01 |
| ALEC PIERCE | WR | `questionable` | 122 | 154 | -32 | 15.16 |
| TUCKER KRAFT | TE | `questionable` | 111 | 140 | -29 | 12.49 |
| WAN'DALE ROBINSON | WR | `questionable` | 128 | 155 | -27 | 13.87 |
| MICHAEL PITTMAN JR. | WR | `questionable` | 132 | 159 | -27 | 14.49 |
| BHAYSHUL TUTEN | RB | `questionable` | 133 | 158 | -25 | 11.86 |
| MICHAEL PENIX JR. | QB | `questionable` | 399 | 422 | -23 | 6.5 |
| MIKE EVANS | WR | `questionable` | 87 | 106 | -19 | 12.27 |
| DANTE MILLER | RB | `questionable` | 687 | 701 | -14 | 1.33 |
| CHUBA HUBBARD | RB | `questionable` | 164 | 177 | -13 | 13.9 |
| BEN SKOWRONEK | WR | `questionable` | 662 | 675 | -13 | 8.45 |
| JACOB COWING | WR | `questionable` | 574 | 586 | -12 | 4.04 |
| JOSH DOWNS | WR | `questionable` | 169 | 180 | -11 | 12.77 |
| GABE DAVIS | WR | `questionable` | 682 | 693 | -11 | 8.38 |
| ISAIAH BOND | WR | `questionable` | 316 | 326 | -10 | 9.89 |
| OLLIE GORDON II | RB | `questionable` | 318 | 328 | -10 | 9.66 |
| BEN SINNOTT | TE | `questionable` | 389 | 399 | -10 | 9.9 |
| PATRICK TAYLOR JR. | RB | `questionable` | 506 | 516 | -10 | 4.29 |
| KEATON MITCHELL | RB | `questionable` | 275 | 284 | -9 | 8.22 |
| JUJU SMITH-SCHUSTER | WR | `questionable` | 468 | 477 | -9 | 10.59 |
| ANTONIO GIBSON | RB | `questionable` | 710 | 719 | -9 | 6.64 |
| JAKOBI MEYERS | WR | `questionable` | 175 | 183 | -8 | 14.53 |
| TYRONE TRACY JR. | RB | `questionable` | 219 | 227 | -8 | 12.12 |
| JOHN BATES | TE | `questionable` | 336 | 344 | -8 | 11.04 |

⚠️ Read the SHAPE, not the values: a ×0.9629 `questionable` cut moves mid-board players 20–37 ranks because that region is dense. A real Week-1 report carries `out` at ×0.8639 — roughly four times the cut — so the in-scope effect will be materially larger than this rehearsal.

---

## 5. What this is NOT

- ⛔ **Not a capture-pinned rebuild.** The registered ship path's step 1 rebuilds the board against a pinned baseline with matched market vintages (NF-INJ2c: a pin whose market inputs are a different day is not a pin). That is an OPERATOR step and it is what produces the publish-candidate board. This is a READ on the published board — it gives the decision-relevant magnitude beforehand.
- ⛔ **Not a publish.** Nothing here writes a served artifact.
- ⛔ **Not evidence the discount is small.** Today's zero is the SCOPE RULE refusing every row, which is uninformative — never a passed check (NF1.7 (a) / NF-D20).
