# NF-INJ4b — operator packet: what the certified designation discount would do

**Generated 2026-09-13T21:29:44+00:00 · season 2026 · as-of 2026-09-13.** `best_alpha = 0`. ⛔ **DEPLOY-HELD — this run changes nothing.** The served Questionable / Doubtful / Out discount is EXACTLY ZERO, no production caller passes the designation channel, and the publish decision is the operator's.

---

## 1. ⚠️ The scope verdict — measured, not assumed

The 2026 regular season starts **2026-09-09** (read from the schedule, not assumed) and this run is as of **2026-09-13** — **-4 days before Week 1**.

The registered scope rule admits REGULAR-SEASON designations only. The live feed carries **{'doubtful': 2, 'out': 20, 'questionable': 76}** — the preseason shape (the game-status report only publishes Out/Doubtful once the season starts), so the rule **refuses all 0** of them.

IN SCOPE — the counterfactual below is a real read.

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

## 4. The in-scope counterfactual

| board | designated rows | ranks moved | max abs move |
|---|---|---|---|
| `full_ppr_3wr__10team` | 59 | 640 | 278 |
| `full_ppr_3wr__12team` | 59 | 606 | 201 |
| `full_ppr__10team` | 59 | 627 | 279 |
| `full_ppr__12team` | 59 | 620 | 291 |
| `half_ppr_3wr__10team` | 59 | 551 | 179 |
| `half_ppr_3wr__12team` | 59 | 551 | 262 |
| `half_ppr__10team` | 59 | 590 | 152 |
| `half_ppr__12team` | 59 | 576 | 175 |
| `standard_3wr__10team` | 59 | 609 | 390 |
| `standard_3wr__12team` | 59 | 574 | 398 |
| `standard__10team` | 59 | 564 | 288 |
| `standard__12team` | 59 | 589 | 346 |
| `superflex__10team` | 59 | 600 | 85 |
| `superflex__12team` | 59 | 549 | 133 |

---

## 5. What this is NOT

- ⛔ **Not a capture-pinned rebuild.** The registered ship path's step 1 rebuilds the board against a pinned baseline with matched market vintages (NF-INJ2c: a pin whose market inputs are a different day is not a pin). That is an OPERATOR step and it is what produces the publish-candidate board. This is a READ on the published board — it gives the decision-relevant magnitude beforehand.
- ⛔ **Not a publish.** Nothing here writes a served artifact.
- ⛔ **Not evidence the discount is small.** Today's zero is the SCOPE RULE refusing every row, which is uninformative — never a passed check (NF1.7 (a) / NF-D20).
