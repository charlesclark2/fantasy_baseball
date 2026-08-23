# NF-INJ3b-M — the served-POINT impact, MEASURED (closes NF-INJ3b §5(d))

_generated 2026-08-23T06:47:07.812689+00:00_ · season 2026 · `best_alpha = 0` · **DEPLOY-HELD** (`SERVING_ENABLED` on disk = False) · **nothing published**

## What this measures, and why it could not be estimated

NF-INJ3b already published the GAMES change. The open question — the one blocking the ship decision — was the **POINT and RANK** a drafter sees. `pts` is **not** `rate × games`: NF1.5 permutes the within-position POINT MULTISET, so moving the flagged players' games changes the multiset the permutation re-assigns (NF-INJ1 measured that step handing **+36.4%** of an availability discount back). Both boards are therefore **BUILT**, through the same shipped assembly, in one process. ⛔ No proportional shortcut anywhere.

## 1. The noise floor — measured FIRST, so the effect is readable

The board build is **not** bit-deterministic run to run, so a diff that credited every non-zero delta would report the build's own noise. The baseline was built TWICE:

| quantity | rows differing | max abs | p99 abs |
|---|---|---|---|
| `proj_games` (replicate) | 21 | 3.55e-15 | 1.78e-15 |
| `proj_fp_ppr` (replicate) | 224 | 3.13e-13 | 6.49e-14 |

Replicate overall-rank order identical: **True** ⇒ a rank move in §2 cannot be build noise.

## 2. The served-POINT impact

**22 flagged** of 794 board rows.

| | flagged | unflagged |
|---|---|---|
| mean Δ `proj_games` | **-2.610** | — |
| mean Δ `pts` (PPR) | **-1.234** | — |
| median Δ `pts` (PPR) | -0.488 | — |
| points down / up | 19 / 3 | 348 changed |
| rank moves | 17 | 517 |
| mean Δ overall rank | -10.45 | — |

⭐⭐ **THE HEADLINE, AND IT IS NOT THE FLAGGED PLAYERS.** 517 UNFLAGGED players change overall rank and 348 change POINTS — and the largest single point move on the whole board, **11.46 PPR**, lands on an **UNFLAGGED** player, roughly 9× the MEAN move on a flagged one (-1.234). NF1.5 re-assigns each position's POINT MULTISET in learned-rank order, so moving the flagged players' games moves points onto UNFLAGGED players too. A proportional estimate cannot see this.

⭐ And the give-back is enormous: with NF1.5's re-order DISABLED the same cap change moves the flagged players by **−12.06** PPR; with it enabled, **-1.234**. ~90% of the raw point impact is absorbed and REDISTRIBUTED. That ratio is the single strongest argument for why §5(d) forbade a proportional estimate — and it was measured by accident, when a wrong report suffix made the re-order a no-op (§5).

### The moved rows (largest point drops first)

| player | pos | flagged? | games inc→cf | pts inc→cf | Δpts | rank inc→cf | pos-rank inc→cf |
|---|---|---|---|---|---|---|---|
| CHRIS COLLIER | RB | no | 2.25 → 0.47 | 15.7 → 4.3 | **-11.5** | 605 → 784 | 159 → 180 |
| ISAAC GUERENDO | RB | **FLAGGED** | 5.19 → 2.05 | 37.6 → 28.6 | **-9.0** | 348 → 430 | 90 → 104 |
| DANTE MILLER | RB | no | 1.33 → 0.47 | 16.0 → 7.3 | **-8.7** | 603 → 753 | 157 → 177 |
| TANNER MCLACHLAN | TE | no | 2.15 → 0.47 | 9.1 → 2.4 | **-6.7** | 743 → 788 | 150 → 170 |
| MICHAEL MAYER | TE | no | 12.09 → 12.09 | 73.8 → 67.4 | **-6.4** | 201 → 212 | 37 → 37 |
| COLE KMET | TE | no | 13.15 → 13.15 | 65.2 → 60.2 | **-5.0** | 220 → 229 | 39 → 40 |
| PAT FREIERMUTH | TE | no | 14.78 → 14.78 | 86.5 → 81.8 | **-4.7** | 170 → 181 | 29 → 29 |
| NIKOLA KALINIC | TE | **FLAGGED** | 4.24 → 1.06 | 9.4 → 5.2 | **-4.2** | 739 → 775 | 147 → 166 |
| ELIJAH MITCHELL | RB | no | 3.80 → 3.80 | 10.0 → 6.0 | **-4.0** | 728 → 766 | 178 → 178 |
| ROMAN WILSON | WR | no | 8.99 → 8.99 | 44.4 → 40.5 | **-3.9** | 303 → 318 | 124 → 130 |
| NOAH GRAY | TE | no | 12.16 → 12.16 | 55.0 → 51.2 | **-3.8** | 254 → 264 | 45 → 45 |
| TREY PALMER | WR | no | 5.07 → 5.07 | 44.9 → 41.1 | **-3.8** | 299 → 314 | 123 → 128 |
| TOMMY TREMBLE | TE | no | 13.82 → 13.82 | 49.6 → 46.1 | **-3.5** | 273 → 290 | 47 → 48 |
| ISAIAH DAVIS | RB | no | 9.47 → 9.47 | 54.8 → 51.6 | **-3.2** | 256 → 260 | 68 → 68 |
| THEO JOHNSON | TE | no | 13.56 → 13.56 | 81.8 → 78.6 | **-3.2** | 182 → 186 | 30 → 30 |
| ZACH ERTZ | TE | no | 14.97 → 14.97 | 46.0 → 43.0 | **-3.0** | 294 → 307 | 49 → 50 |
| JA'LYNN POLK | WR | no | 5.02 → 5.02 | 42.5 → 39.6 | **-2.9** | 316 → 327 | 130 → 132 |
| RAHEEM MOSTERT | RB | no | 9.86 → 9.86 | 58.7 → 55.8 | **-2.9** | 241 → 249 | 66 → 66 |
| COOPER KUPP | WR | no | 12.85 → 12.85 | 69.8 → 67.0 | **-2.8** | 211 → 213 | 81 → 81 |
| SAMAJE PERINE | RB | no | 10.78 → 10.78 | 51.6 → 48.8 | **-2.8** | 263 → 275 | 69 → 70 |

## 3. Per-config placement — all 14 published configs

| config | rank moves | max \|move\| | top-60 moved | top-60 max \|move\| | within-pos order | rookie cap |
|---|---|---|---|---|---|---|
| `standard_10` | 510/794 | 62 | 0 | 0 | False | True |
| `standard_12` | 538/794 | 119 | 0 | 0 | False | True |
| `standard_3wr_10` | 480/794 | 95 | 0 | 0 | False | True |
| `standard_3wr_12` | 515/794 | 126 | 0 | 0 | False | True |
| `half_ppr_10` | 490/794 | 123 | 0 | 0 | False | True |
| `half_ppr_12` | 539/794 | 82 | 0 | 0 | False | True |
| `half_ppr_3wr_10` | 532/794 | 105 | 0 | 0 | False | True |
| `half_ppr_3wr_12` | 521/794 | 132 | 0 | 0 | False | True |
| `full_ppr_10` | 515/794 | 113 | 0 | 0 | False | True |
| `full_ppr_12` | 525/794 | 102 | 0 | 0 | False | True |
| `full_ppr_3wr_10` | 530/794 | 91 | 0 | 0 | False | True |
| `full_ppr_3wr_12` | 517/794 | 164 | 0 | 0 | False | True |
| `superflex_10` ⭐SF | 513/794 | 120 | 0 | 0 | False | True |
| `superflex_12` ⭐SF | 547/794 | 112 | 0 | 0 | False | True |

### ⚠️ Superflex is read on its OWN rows

NF-TR2b — the VOR 'shield' (a per-group level shift cancels because a group's own replacement absorbs it) is ADDITIVE-ONLY and assumes the group is not cross-pooled. QB IS cross-pooled in superflex, so these configs must be read on their own rows, never inferred from the others.

superflex max |move|: `{'superflex_10': 120, 'superflex_12': 112}` against non-superflex `{'standard_10': 62, 'standard_12': 119, 'standard_3wr_10': 95, 'standard_3wr_12': 126, 'half_ppr_10': 123, 'half_ppr_12': 82, 'half_ppr_3wr_10': 105, 'half_ppr_3wr_12': 132, 'full_ppr_10': 113, 'full_ppr_12': 102, 'full_ppr_3wr_10': 91, 'full_ppr_3wr_12': 164}`.

## 4. What is still the OPERATOR's

This packet is the measurement §5(d) blocked on. It does **not** decide anything: `SERVING_ENABLED` is `False` on disk, the policy was forced on **in memory only**, and this runner has no `--publish` flag and writes nothing to the lake. The ship/no-ship — and the PM boundary that SUS/NFI keep the incumbent constants — remain as recorded.
