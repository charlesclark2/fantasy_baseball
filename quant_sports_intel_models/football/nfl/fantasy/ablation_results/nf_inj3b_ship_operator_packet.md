# NF-INJ3b-SHIP — OPERATOR PACKET

_The D5=A flip, built and measured. **DEPLOY-HELD — nothing published from this session, and this runner set has no `--publish` flag.** `best_alpha = 0`._

## 0. The call that is yours

Everything the ruling asked for has run and passed. What is left is **publish or hold**, and there are two facts below that a reasonable person could decide either way on — §5 (five players' games nearly halve while their points do not move) and §6 (that adds three rows to the NF-INJ1 incoherence count). Neither is a gate failure; both are consequences the flip makes visible, and both are owned by NF-INJ2b. They are stated up front rather than buried because they are the parts of this you might not want to ship today.

| gate | result |
|---|---|
| D6 publish-time stamp guard | **FLIPPED_AND_MOVED** — 22 certified rows, 22 served, 22 materially moved, largest 4.00 games |
| D10 combined read (placement) | **SANE** — all four gates PASS across 14 configs |
| D10 combined read (interval) | **ALL FLOORS MET** |
| Sanity anchor vs NF-INJ3b-M | **REPRODUCES** — mean Δgames -2.6104 vs -2.6104 (deviation +0.0000) |
| Rookie-band motion attributable to the flip | **False** (5-draw control envelope) |
| Decided artifacts intact | {'nf_tr2b_placement_read.json': True, 'nf1_9_interval_revalidation.json': True} |

## 1. What the flip does

**22 of 794** board rows are served by the certified hurdle — every flagged RES/PUP veteran who is not a returner.

| | flagged | unflagged |
|---|---|---|
| mean Δ `proj_games` | **-2.610** | — |
| mean Δ `pts` (PPR) | **-1.351** | — |
| median Δ `pts` (PPR) | -0.711 | — |
| points down / up | 19 / 3 | 340 changed |
| rank moves | 19 | 519 |
| largest single point move | — | 6.40 PPR |

⭐ **The games effect is deterministic; the point effect is not.** Mean Δgames reproduced NF-INJ3b-M's figure to four decimals and was identical across every run this session. Mean Δpts measured **−1.44** and **−1.35** on two runs of the same commit whose only difference was a refreshed ADP cache — because the point lands through NF1.5's re-order, which reads the market vintage. Read Δpts as a magnitude, not a constant.

## 2. The flagged cohort — all 22, named

| player | pos | games inc→flip | Δgames | pts inc→flip | Δpts | rank inc→flip |
|---|---|---|---|---|---|---|
| ISAAC GUERENDO | RB | 5.19 → 2.05 | **-3.14** | 37.6 → 28.6 | **-9.0** | 348 → 430 |
| NIKOLA KALINIC | TE | 4.24 → 1.06 | **-3.18** | 9.7 → 5.2 | **-4.5** | 736 → 782 |
| RICKY PEARSALL | WR | 5.65 → 4.01 | **-1.64** | 45.0 → 42.5 | **-2.6** | 298 → 311 |
| TIP REIMAN | TE | 5.00 → 2.62 | **-2.38** | 18.0 → 15.8 | **-2.2** | 547 → 600 |
| JAYDEN HIGGINS | WR | 6.66 → 4.09 | **-2.56** | 101.1 → 99.1 | **-1.9** | 154 → 155 |
| PRINCETON FANT | TE | 3.90 → 1.27 | **-2.63** | 11.0 → 9.4 | **-1.7** | 703 → 734 |
| TREY SERMON | RB | 4.14 → 1.37 | **-2.78** | 17.9 → 16.4 | **-1.5** | 551 → 589 |
| JULIAN HILL | TE | 5.40 → 3.03 | **-2.38** | 20.9 → 19.5 | **-1.4** | 499 → 519 |
| JUSTIN SHORTER | WR | 4.22 → 1.61 | **-2.61** | 8.5 → 7.3 | **-1.1** | 758 → 763 |
| JAMARI THRASH | WR | 4.84 → 3.70 | **-1.14** | 6.7 → 5.7 | **-1.0** | 776 → 777 |
| BRENDEN BATES | TE | 4.80 → 2.13 | **-2.67** | 10.9 → 10.0 | **-0.9** | 707 → 723 |
| QUENTIN SKINNER | WR | 4.16 → 1.46 | **-2.70** | 13.7 → 13.1 | **-0.6** | 653 → 655 |
| ROBBIE OUZTS | FB | 5.41 → 1.41 | **-4.00** | 0.5 → 0.1 | **-0.4** | 794 → 794 |
| GUNNER OLSZEWSKI | WR | 5.19 → 3.25 | **-1.93** | 11.1 → 10.8 | **-0.4** | 699 → 702 |
| DAN CHISENA | WR | 3.02 → 1.24 | **-1.78** | 11.0 → 10.7 | **-0.3** | 704 → 705 |
| MASON TIPTON | WR | 5.42 → 3.41 | **-2.00** | 15.2 → 15.0 | **-0.2** | 616 → 614 |
| TYRELL SHAVERS | WR | 5.71 → 3.16 | **-2.56** | 19.1 → 19.0 | **-0.1** | 529 → 527 |
| JEROME FORD | RB | 5.40 → 4.22 | **-1.18** | 37.1 → 37.1 | **-0.0** | 350 → 346 |
| GEORGE KITTLE | TE | 7.32 → 3.33 | **-3.98** | 112.3 → 112.3 | **-0.0** | 141 → 141 |
| ALEC PIERCE | WR | 7.35 → 3.66 | **-3.69** | 118.3 → 118.3 | **+0.0** | 131 → 131 |
| ZACH CHARBONNET | RB | 6.90 → 3.71 | **-3.19** | 83.1 → 83.1 | **+0.0** | 180 → 179 |
| LUKE MUSGRAVE | TE | 6.49 → 3.20 | **-3.30** | 27.7 → 27.7 | **+0.0** | 437 → 436 |

## 3. Per-config placement — all 14 published configs, superflex included

| config | rank moves | max \|move\| | top-60 moved | rookie cap |
|---|---|---|---|---|
| `standard_10` | 484/794 | 57 | 0 | True |
| `standard_12` | 507/794 | 106 | 0 | True |
| `standard_3wr_10` | 460/794 | 99 | 0 | True |
| `standard_3wr_12` | 508/794 | 118 | 0 | True |
| `half_ppr_10` | 480/794 | 48 | 0 | True |
| `half_ppr_12` | 515/794 | 72 | 0 | True |
| `half_ppr_3wr_10` | 499/794 | 95 | 0 | True |
| `half_ppr_3wr_12` | 518/794 | 86 | 0 | True |
| `full_ppr_10` | 488/794 | 60 | 0 | True |
| `full_ppr_12` | 481/794 | 103 | 0 | True |
| `full_ppr_3wr_10` | 497/794 | 94 | 0 | True |
| `full_ppr_3wr_12` | 521/794 | 78 | 0 | True |
| `superflex_10` ⭐SF | 491/794 | 62 | 0 | True |
| `superflex_12` ⭐SF | 508/794 | 105 | 0 | True |

⭐ **Zero top-60 moves on every config.** The change lands entirely outside the draftable range a reader spends their first six rounds in.

⚠️ **Superflex read on its own rows** (NF-TR2b: the VOR shield is additive-only and assumes the group is not cross-pooled; QB IS cross-pooled there). `superflex_10` 491 moves / max 62; `superflex_12` 508 / max 105 — in line with the non-superflex configs, not an outlier.

## 4. Top-25 rank moves by config

<details><summary><code>standard_10</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 420 | -57 |
| NIKOLA KALINIC | TE | 344 | -37 |
| ISAIAH DAVIS | RB | 319 | -37 |
| NAJEE HARRIS | RB | 306 | -29 |
| TREY SERMON | RB | 610 | -26 |
| GEORGE HOLANI | RB | 246 | -15 |
| TREY PALMER | WR | 400 | -13 |
| PRINCETON FANT | TE | 330 | -13 |
| DAMEON PIERCE | RB | 652 | -13 |
| RAY DAVIS | RB | 185 | -13 |
| TIP REIMAN | TE | 290 | -12 |
| DJ GIDDENS | RB | 360 | -11 |
| TREYLON BURKS | WR | 404 | -11 |
| KYLE WILLIAMS | WR | 260 | -11 |
| JUSTICE HILL | RB | 274 | -11 |
| PATRICK TAYLOR JR. | RB | 476 | -10 |
| EMANUEL WILSON | RB | 210 | -10 |
| JAHDAE WALKER | WR | 536 | -10 |
| JACK BECH | WR | 307 | -10 |
| JAYLIN LANE | WR | 436 | -9 |
| JALEN REAGOR | WR | 596 | -9 |
| ULYSSES BENTLEY IV | RB | 622 | +9 |
| TRAYVEON WILLIAMS | RB | 620 | +9 |
| Zachariah Branch | WR | 407 | +8 |
| ROSCHON JOHNSON | RB | 637 | +8 |

</details>

<details><summary><code>standard_12</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 334 | -106 |
| TREY PALMER | WR | 371 | -45 |
| TREYLON BURKS | WR | 382 | -42 |
| NIKOLA KALINIC | TE | 393 | -39 |
| ELIJAH MITCHELL | RB | 649 | -30 |
| RICKY PEARSALL | WR | 370 | -27 |
| SAVION WILLIAMS | WR | 401 | -27 |
| TREY SERMON | RB | 533 | -25 |
| CHRIS BROOKS | RB | 289 | -18 |
| BRITISH BROOKS | RB | 688 | -16 |
| KENDRICK BOURNE | WR | 374 | -15 |
| ROMAN WILSON | WR | 388 | -15 |
| PATRICK TAYLOR JR. | RB | 442 | -14 |
| TY CHANDLER | RB | 590 | -13 |
| JACOB SAYLORS | RB | 622 | -13 |
| KHALIL HERBERT | RB | 595 | -13 |
| GEORGE HOLANI | RB | 207 | -13 |
| MOLIKI MATAVAO | TE | 403 | +12 |
| XAVIER HUTCHINSON | WR | 316 | -12 |
| MO ALIE-COX | TE | 405 | +12 |
| TIP REIMAN | TE | 325 | -12 |
| RAY DAVIS | RB | 166 | -11 |
| JA'LYNN POLK | WR | 419 | -11 |
| RONNIE RIVERS | RB | 609 | -11 |
| PRINCETON FANT | TE | 376 | -11 |

</details>

<details><summary><code>standard_3wr_10</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 523 | -99 |
| ISAIAH DAVIS | RB | 379 | -50 |
| NAJEE HARRIS | RB | 365 | -41 |
| NIKOLA KALINIC | TE | 415 | -37 |
| RAY DAVIS | RB | 209 | -19 |
| GEORGE HOLANI | RB | 294 | -18 |
| TREYLON BURKS | WR | 285 | -18 |
| TREY PALMER | WR | 280 | -18 |
| DEVIN SINGLETARY | RB | 470 | -17 |
| JAYLIN LANE | WR | 335 | -17 |
| PRINCETON FANT | TE | 398 | -16 |
| CHRIS BROOKS | RB | 477 | -16 |
| KALIF RAYMOND | WR | 314 | -16 |
| JUSTICE HILL | RB | 329 | -14 |
| SAVION WILLIAMS | WR | 293 | -14 |
| DJ GIDDENS | RB | 431 | -13 |
| JORDAN WHITTINGTON | WR | 392 | -13 |
| EMANUEL WILSON | RB | 244 | -12 |
| TIP REIMAN | TE | 347 | -12 |
| KEVIN AUSTIN JR. | WR | 393 | -11 |
| TUTU ATWELL | WR | 338 | -11 |
| TREY SERMON | RB | 665 | -11 |
| JA'LYNN POLK | WR | 299 | -10 |
| JOHN METCHIE III | WR | 355 | -10 |
| AINIAS SMITH | WR | 378 | -10 |

</details>

<details><summary><code>standard_3wr_12</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 351 | -118 |
| NIKOLA KALINIC | TE | 455 | -53 |
| PATRICK TAYLOR JR. | RB | 468 | -39 |
| JOHN METCHIE III | WR | 349 | -18 |
| TIP REIMAN | TE | 388 | -17 |
| JAYLIN LANE | WR | 330 | -17 |
| TREY PALMER | WR | 284 | -17 |
| TREYLON BURKS | WR | 289 | -17 |
| NAJEE HARRIS | RB | 250 | -16 |
| ISAIAH DAVIS | RB | 256 | -16 |
| BRAYDEN WILLIS | TE | 497 | -15 |
| MICHAEL MAYER | TE | 183 | -15 |
| TREY SERMON | RB | 656 | -14 |
| AMEER ABDULLAH | RB | 505 | -14 |
| PRINCETON FANT | TE | 442 | -12 |
| RICKY PEARSALL | WR | 282 | -11 |
| AINIAS SMITH | WR | 377 | -11 |
| SAVION WILLIAMS | WR | 298 | -11 |
| KALIF RAYMOND | WR | 317 | -10 |
| GEORGE HOLANI | RB | 221 | -10 |
| TUTU ATWELL | WR | 335 | -10 |
| JAHDAE WALKER | WR | 520 | -9 |
| RAY DAVIS | RB | 174 | -9 |
| NOAH FANT | TE | 231 | -9 |
| DEVIN CULP | TE | 413 | -9 |

</details>

<details><summary><code>half_ppr_10</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 417 | -48 |
| NIKOLA KALINIC | TE | 379 | -37 |
| TREY PALMER | WR | 386 | -29 |
| TREYLON BURKS | WR | 394 | -26 |
| RICKY PEARSALL | WR | 383 | -26 |
| ELIJAH MITCHELL | RB | 663 | -23 |
| PRINCETON FANT | TE | 358 | -20 |
| TREY SERMON | RB | 553 | -18 |
| ISAIAH DAVIS | RB | 268 | -17 |
| DEVIN SINGLETARY | RB | 350 | -17 |
| KENDRICK BOURNE | WR | 377 | -16 |
| NAJEE HARRIS | RB | 275 | -15 |
| TY CHANDLER | RB | 607 | -14 |
| EMANUEL WILSON | RB | 212 | -14 |
| KHALIL HERBERT | RB | 614 | -13 |
| CHRIS BROOKS | RB | 326 | -13 |
| SAVION WILLIAMS | WR | 412 | -13 |
| PATRICK TAYLOR JR. | RB | 461 | -13 |
| TIP REIMAN | TE | 304 | -12 |
| BRITISH BROOKS | RB | 698 | -11 |
| DYLAN LAUBE | RB | 625 | -10 |
| GEORGE HOLANI | RB | 244 | -10 |
| BRENDEN BATES | TE | 364 | -10 |
| RAY DAVIS | RB | 190 | -9 |
| DAMEON PIERCE | RB | 593 | -9 |

</details>

<details><summary><code>half_ppr_12</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 312 | -72 |
| NIKOLA KALINIC | TE | 439 | -49 |
| BRITISH BROOKS | RB | 643 | -30 |
| TREYLON BURKS | WR | 337 | -30 |
| JOHN METCHIE III | WR | 402 | -27 |
| TREY PALMER | WR | 332 | -26 |
| JAYLIN LANE | WR | 390 | -25 |
| PRINCETON FANT | TE | 412 | -25 |
| TUTU ATWELL | WR | 414 | -22 |
| PATRICK TAYLOR JR. | RB | 383 | -20 |
| ELIJAH MITCHELL | RB | 611 | -20 |
| RICKY PEARSALL | WR | 331 | -20 |
| KALIF RAYMOND | WR | 381 | -19 |
| BRAYDEN WILLIS | TE | 480 | -19 |
| SAVION WILLIAMS | WR | 354 | -18 |
| AMEER ABDULLAH | RB | 379 | -14 |
| TY CHANDLER | RB | 565 | -13 |
| TREY SERMON | RB | 527 | -13 |
| NAJEE HARRIS | RB | 236 | -12 |
| BRENDEN BATES | TE | 419 | -12 |
| KHALIL HERBERT | RB | 573 | -11 |
| CJ DIPPRE | TE | 456 | -11 |
| KYLE WILLIAMS | WR | 259 | -10 |
| KENDRICK BOURNE | WR | 325 | -10 |
| PAT FREIERMUTH | TE | 139 | -10 |

</details>

<details><summary><code>half_ppr_3wr_10</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 444 | -95 |
| NIKOLA KALINIC | TE | 447 | -46 |
| PATRICK TAYLOR JR. | RB | 537 | -27 |
| PRINCETON FANT | TE | 424 | -22 |
| TIP REIMAN | TE | 363 | -18 |
| BRAYDEN WILLIS | TE | 485 | -17 |
| JOHN METCHIE III | WR | 322 | -17 |
| CHRIS BROOKS | RB | 357 | -17 |
| JAYLIN LANE | WR | 317 | -16 |
| AMEER ABDULLAH | RB | 533 | -16 |
| DEVIN SINGLETARY | RB | 382 | -15 |
| TREYLON BURKS | WR | 288 | -15 |
| GEORGE HOLANI | RB | 267 | -14 |
| ISAIAH DAVIS | RB | 299 | -12 |
| EMANUEL WILSON | RB | 229 | -12 |
| TREY PALMER | WR | 286 | -12 |
| AUDRIC ESTIME | RB | 490 | -11 |
| BRENDEN BATES | TE | 431 | -11 |
| TREY SERMON | RB | 666 | -10 |
| DJ GIDDENS | RB | 341 | -10 |
| MICHAEL MAYER | TE | 166 | -10 |
| TUTU ATWELL | WR | 335 | -10 |
| NAJEE HARRIS | RB | 304 | -10 |
| JAKE TONGES | TE | 174 | -10 |
| RICKY PEARSALL | WR | 285 | -10 |

</details>

<details><summary><code>half_ppr_3wr_12</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| NIKOLA KALINIC | TE | 544 | -86 |
| ISAAC GUERENDO | RB | 312 | -61 |
| TREY SERMON | RB | 518 | -35 |
| PRINCETON FANT | TE | 510 | -34 |
| BRAYDEN WILLIS | TE | 609 | -26 |
| PATRICK TAYLOR JR. | RB | 369 | -20 |
| DEVIN CULP | TE | 477 | -20 |
| ELIJAH MITCHELL | RB | 672 | -20 |
| TREYLON BURKS | WR | 295 | -19 |
| TIP REIMAN | TE | 429 | -18 |
| ERICK ALL JR. | TE | 259 | -17 |
| TREY PALMER | WR | 292 | -17 |
| JERMAR JEFFERSON | RB | 545 | -16 |
| BRENDEN BATES | TE | 517 | -16 |
| JAYLIN LANE | WR | 331 | -15 |
| JAHDAE WALKER | WR | 565 | -15 |
| DRAKE DABNEY | TE | 413 | -14 |
| JOHN METCHIE III | WR | 337 | -13 |
| KHALIL HERBERT | RB | 619 | -13 |
| ZACH ERTZ | TE | 257 | -13 |
| CJ DIPPRE | TE | 577 | -12 |
| ELIJAH MOORE | WR | 508 | -12 |
| PAT FREIERMUTH | TE | 146 | -12 |
| RICKY PEARSALL | WR | 291 | -12 |
| AMEER ABDULLAH | RB | 366 | -12 |

</details>

<details><summary><code>full_ppr_10</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 422 | -60 |
| NIKOLA KALINIC | TE | 394 | -39 |
| TREYLON BURKS | WR | 352 | -36 |
| TREY PALMER | WR | 345 | -33 |
| SAVION WILLIAMS | WR | 370 | -30 |
| RICKY PEARSALL | WR | 343 | -22 |
| TREY SERMON | RB | 559 | -22 |
| PRINCETON FANT | TE | 373 | -20 |
| JA'LYNN POLK | WR | 384 | -19 |
| TIP REIMAN | TE | 312 | -19 |
| ROMAN WILSON | WR | 393 | -19 |
| ELIJAH MITCHELL | RB | 674 | -19 |
| DAMEON PIERCE | RB | 604 | -17 |
| RAY DAVIS | RB | 204 | -14 |
| JOHN METCHIE III | WR | 420 | -14 |
| NAJEE HARRIS | RB | 289 | -13 |
| SIONE VAKI | RB | 603 | -12 |
| ISAIAH DAVIS | RB | 275 | -11 |
| GEORGE HOLANI | RB | 258 | -11 |
| NOAH GRAY | TE | 177 | -11 |
| PATRICK TAYLOR JR. | RB | 475 | -11 |
| KENDRICK BOURNE | WR | 336 | -11 |
| KALIF RAYMOND | WR | 419 | -10 |
| PAT FREIERMUTH | TE | 131 | -9 |
| BRITISH BROOKS | RB | 702 | -9 |

</details>

<details><summary><code>full_ppr_12</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 362 | -103 |
| NIKOLA KALINIC | TE | 462 | -42 |
| PATRICK TAYLOR JR. | RB | 453 | -25 |
| TREY SERMON | RB | 577 | -23 |
| PRINCETON FANT | TE | 441 | -22 |
| TIP REIMAN | TE | 363 | -20 |
| AMEER ABDULLAH | RB | 422 | -19 |
| TREYLON BURKS | WR | 305 | -18 |
| TREY PALMER | WR | 303 | -16 |
| JAYLIN LANE | WR | 344 | -16 |
| JOHN METCHIE III | WR | 341 | -15 |
| BRAYDEN WILLIS | TE | 495 | -13 |
| KALIF RAYMOND | WR | 339 | -13 |
| RICKY PEARSALL | WR | 302 | -11 |
| AUDRIC ESTIME | RB | 397 | -11 |
| SAVION WILLIAMS | WR | 317 | -11 |
| BUB MEANS | WR | 356 | -11 |
| ISAIAH DAVIS | RB | 261 | -10 |
| NAJEE HARRIS | RB | 273 | -10 |
| KEVIN AUSTIN JR. | WR | 417 | -9 |
| DARIUS COOPER | WR | 433 | -9 |
| JA'LYNN POLK | WR | 323 | -9 |
| DAMEON PIERCE | RB | 632 | -9 |
| BRENDEN BATES | TE | 444 | -9 |
| ROMAN WILSON | WR | 327 | -8 |

</details>

<details><summary><code>full_ppr_3wr_10</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 376 | -94 |
| NIKOLA KALINIC | TE | 466 | -51 |
| PATRICK TAYLOR JR. | RB | 459 | -26 |
| TIP REIMAN | TE | 372 | -24 |
| BRAYDEN WILLIS | TE | 503 | -22 |
| TREYLON BURKS | WR | 293 | -21 |
| PRINCETON FANT | TE | 446 | -19 |
| TREY SERMON | RB | 604 | -19 |
| TREY PALMER | WR | 290 | -18 |
| RICKY PEARSALL | WR | 289 | -17 |
| AMEER ABDULLAH | RB | 435 | -15 |
| AUDRIC ESTIME | RB | 407 | -15 |
| DAMEON PIERCE | RB | 657 | -13 |
| DARIUS COOPER | WR | 412 | -12 |
| SIONE VAKI | RB | 654 | -11 |
| MICHAEL MAYER | TE | 162 | -11 |
| TUTU ATWELL | WR | 351 | -11 |
| JAYLIN LANE | WR | 333 | -10 |
| KALIF RAYMOND | WR | 329 | -10 |
| JA'LYNN POLK | WR | 312 | -10 |
| SAVION WILLIAMS | WR | 310 | -9 |
| ISAIAH DAVIS | RB | 268 | -9 |
| JOHN METCHIE III | WR | 332 | -9 |
| NAJEE HARRIS | RB | 279 | -9 |
| BRENDEN BATES | TE | 449 | -9 |

</details>

<details><summary><code>full_ppr_3wr_12</code></summary>

| player | pos | rank inc | move |
|---|---|---|---|
| NIKOLA KALINIC | TE | 589 | -78 |
| ISAAC GUERENDO | RB | 319 | -61 |
| PRINCETON FANT | TE | 558 | -32 |
| TREY SERMON | RB | 495 | -29 |
| ELIJAH MITCHELL | RB | 657 | -26 |
| TIP REIMAN | TE | 438 | -25 |
| BRAYDEN WILLIS | TE | 655 | -21 |
| DAMEON PIERCE | RB | 556 | -20 |
| DEVIN CULP | TE | 532 | -20 |
| TREYLON BURKS | WR | 290 | -18 |
| AMEER ABDULLAH | RB | 355 | -17 |
| SIONE VAKI | RB | 551 | -17 |
| PATRICK TAYLOR JR. | RB | 376 | -16 |
| TREY PALMER | WR | 289 | -15 |
| TY CHANDLER | RB | 583 | -14 |
| SAVION WILLIAMS | WR | 300 | -14 |
| DYLAN LAUBE | RB | 604 | -14 |
| KHALIL HERBERT | RB | 591 | -14 |
| RONNIE RIVERS | RB | 612 | -13 |
| BLAKE WHITEHEART | TE | 480 | -11 |
| ERICK ALL JR. | TE | 252 | -11 |
| BRENDEN BATES | TE | 563 | -11 |
| MO ALIE-COX | TE | 627 | +11 |
| BRITISH BROOKS | RB | 694 | -10 |
| MILES SANDERS | RB | 636 | +10 |

</details>

<details><summary><code>superflex_10</code> ⭐SUPERFLEX</summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 427 | -62 |
| NIKOLA KALINIC | TE | 399 | -40 |
| TREYLON BURKS | WR | 355 | -38 |
| TREY PALMER | WR | 348 | -35 |
| SAVION WILLIAMS | WR | 374 | -31 |
| TREY SERMON | RB | 567 | -23 |
| RICKY PEARSALL | WR | 346 | -23 |
| PRINCETON FANT | TE | 377 | -21 |
| ELIJAH MITCHELL | RB | 684 | -20 |
| JA'LYNN POLK | WR | 389 | -19 |
| TIP REIMAN | TE | 315 | -19 |
| ROMAN WILSON | WR | 398 | -19 |
| DAMEON PIERCE | RB | 613 | -18 |
| JOHN METCHIE III | WR | 425 | -15 |
| RAY DAVIS | RB | 207 | -14 |
| PATRICK TAYLOR JR. | RB | 481 | -13 |
| SIONE VAKI | RB | 612 | -13 |
| NAJEE HARRIS | RB | 292 | -13 |
| BRITISH BROOKS | RB | 714 | -11 |
| KALIF RAYMOND | WR | 424 | -11 |
| KENDRICK BOURNE | WR | 339 | -11 |
| ISAIAH DAVIS | RB | 278 | -11 |
| GEORGE HOLANI | RB | 261 | -11 |
| JAYLIN LANE | WR | 431 | -10 |
| TYLER BADIE | RB | 668 | -10 |

</details>

<details><summary><code>superflex_12</code> ⭐SUPERFLEX</summary>

| player | pos | rank inc | move |
|---|---|---|---|
| ISAAC GUERENDO | RB | 371 | -105 |
| NIKOLA KALINIC | TE | 473 | -43 |
| PATRICK TAYLOR JR. | RB | 463 | -26 |
| PRINCETON FANT | TE | 451 | -23 |
| TREY SERMON | RB | 596 | -23 |
| TIP REIMAN | TE | 372 | -20 |
| TREYLON BURKS | WR | 312 | -20 |
| AMEER ABDULLAH | RB | 432 | -19 |
| TREY PALMER | WR | 310 | -17 |
| JAYLIN LANE | WR | 352 | -17 |
| JOHN METCHIE III | WR | 350 | -15 |
| BRAYDEN WILLIS | TE | 507 | -14 |
| KALIF RAYMOND | WR | 348 | -13 |
| SAVION WILLIAMS | WR | 325 | -12 |
| RICKY PEARSALL | WR | 309 | -12 |
| JACOB SAYLORS | RB | 698 | -11 |
| AUDRIC ESTIME | RB | 406 | -11 |
| TYLER BADIE | RB | 707 | -11 |
| BUB MEANS | WR | 365 | -11 |
| NAJEE HARRIS | RB | 280 | -10 |
| DAMEON PIERCE | RB | 651 | -10 |
| BRITISH BROOKS | RB | 737 | -10 |
| ISAIAH DAVIS | RB | 268 | -10 |
| JA'LYNN POLK | WR | 331 | -10 |
| DJ GIDDENS | RB | 313 | -9 |

</details>

## 5. ⚠️ The give-back, stated plainly

Five of the 22 have their projected games nearly halved and their projected points move by **less than 0.05 PPR**:

| player | pos | games | pts |
|---|---|---|---|
| JEROME FORD | RB | 5.40 → 4.22 | 37.1 → 37.1 |
| GEORGE KITTLE | TE | 7.32 → 3.33 | 112.3 → 112.3 |
| ALEC PIERCE | WR | 7.35 → 3.66 | 118.3 → 118.3 |
| ZACH CHARBONNET | RB | 6.90 → 3.71 | 83.1 → 83.1 |
| LUKE MUSGRAVE | TE | 6.49 → 3.20 | 27.7 → 27.7 |

A drafter looking at George Kittle sees **3.3 games** beside **112.3 points**. That is not a defect this change introduced — it is NF1.5 re-assigning each position's point multiset while the availability chain moves games, which NF-INJ1 measured and NF-INJ2b owns — but the flip makes it **visible on exactly the rows it touches**, and a reader will see the pair.

## 6. ⚠️ NF-INJ1 coherence — the flip adds three rows, all attributable

| board | violating players | violations | by position |
|---|---|---|---|
| incumbent | 9 | 16 | {'QB': 9} |
| flipped | 12 | 23 | {'QB': 9, 'TE': 1, 'WR': 2} |

**Δ = +3**, and every newly-violating row is one the flip moved: ALEC PIERCE, GEORGE KITTLE, JAYDEN HIGGINS. Newly violating and NOT flagged: **none** — so the count is fully attributable and the change did not disturb any row it does not touch.

This is **ALERT-tier by PM decision, never a HALT** (`report_publish_coherence`), so it will not block the export. It is your call whether +3 is acceptable to ship today.

## 7. What the read is valid FOR — and when it stops being

| component | at the read |
|---|---|
| board rows | 868 (81 rookie) |
| injury-games cap | `fitted_hurdle` |
| adopted NF-INJ-NEWS-1 overrides | **0** |
| projection lineage | `nf1_5` |

⭐⭐ **The combined read binds to a BOARD, not a date.** It covers the flip and nothing else, because nothing else is live: there are **zero adopted overrides** and the rows are **pre-cutdown**. If either changes, the board that would publish is no longer the board this read covers and **the combined read must re-run before it ships** (ruling D10).

## 8. Rollback

`injury_games_policy.SERVING_ENABLED = False`. One line, the same code path — pinned by test to return the incumbent cap byte-for-byte at every blend and every status. A merge does not serve anything; a board reaches users only through `export_draft_board_json --publish`.
