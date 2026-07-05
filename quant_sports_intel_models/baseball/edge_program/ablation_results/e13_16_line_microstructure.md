# E13.16 — Line-Movement Microstructure (odds-as-a-price-series)

**Verdict: ⚠️ METHOD CHECK FAILED — the `placebo` NEGATIVE CONTROL produced a 'candidate'; the harness manufactures CLV where none exists. Investigate before trusting any result.**

The FRESHEST remaining mechanism: every prior probe asked *is the price right?* (efficient); this asks *does the price's own MOVEMENT reveal structure?* — can a trajectory signal BEAT THE CLOSE (CLV, the gold-standard skill measure)? CLV needs no realized outcome → it is the PRIMARY gate. Pre-registration: `e13_16_preregistration.md`. **Honest bar:** GAME-level collapse before any t-test/DSR/PBO; FORCED side from the trajectory only; CLV net of vig; per-market deflation (PBO<0.2 + DSR≥0.95 + BH-FDR) over every signal × segment × θ × anchor; a `placebo` negative control that must NOT survive.

## ⚠️ Honest data constraint (the verdict's own limits)

Fine 30-min trajectories exist only for **2026+** (`mart_odds_outcomes` live, ~2.5 mo as of 2026-07-04); 2021–2025 is coarse (~3 snaps/day, thin coverage). **This is a FORWARD-ACCRUING study** — the historical run is SUGGESTIVE; the real verdict is prospective forward-CLV on the accruing captures. The operator may thicken the historical leg by backfilling `/odds` snapshots scoped to `h2h`+`totals` (the harness consumes a thicker cache with no code change).

## Coverage

- 695,100 snapshots · 7,278 games · 554,615 forced-side decisions · seasons [2023, 2024, 2025, 2026]
- fine 2026 games: 980 · median snaps/(game,book,mkt): 8.0
- **Stale-quote filter (adversarial control) ON:** dropped 1,674 / 696,774 snapshots (0.24%) that deviated > 0.75 runs (totals) / 0.06 prob (h2h) from the same-hour cross-book consensus (≥3 books) — the control for the stale-quote artifact.

## Signals tested (every one logged — the pre-registered grid)

| signal | market(s) | prior | control? |
|---|---|---|:--:|
| `static_over` | totals | retail/open-staleness probe |  |
| `static_under` | totals | retail/open-staleness probe |  |
| `static_home` | h2h | retail/open-staleness probe |  |
| `static_away` | h2h | retail/open-staleness probe |  |
| `reversion` | both | over-reaction → mean-reversion |  |
| `continuation` | both | steam persists (opposite of reversion) |  |
| `sharp_convergence` | both | LOW (12.10′ ~tapped) |  |
| `placebo` | both | NEGATIVE CONTROL — must NOT survive | ✓ |

## ✅ Method check — the `placebo` NEGATIVE CONTROL

- **❌ FAILED.** The placebo (side = game_pk parity, trajectory-independent) produced a surviving candidate — the harness manufactures CLV where none exists. Investigate.

## Per-market deflation (anti-data-mining)

| market | games | selectable configs | PBO (<0.2) | DSR (≥0.95) | best config | best CLV |
|---|--:|--:|--:|--:|---|--:|
| totals | 7262 | 260 | 0.000 | 0.051 | `sharp_convergence|totals|bovada|all|θ1|t50` | 1.2000 |
| h2h | 7262 | 69 | 0.000 | 0.935 | `sharp_convergence|h2h|bovada|all|θ0.04|t50` | 0.0722 |

- pooled BH-FDR (q=0.1) across BOTH markets: **159/329** configs survive

## Top configs by mean CLV (game-level, beat-the-close; net of vig)

| signal | market | book | bucket | θ | anchor | games | CLV | sharpe | FDR | ctrl |
|---|---|---|---|--:|---|--:|--:|--:|:--:|:--:|
| sharp_convergence | totals | bovada | all | 1 | t50 | 55 | 1.2000 | 0.77 | ✓ |  |
| sharp_convergence | totals | majors | all | 1 | t50 | 88 | 0.9801 | 0.85 | ✓ |  |
| sharp_convergence | totals | all | all | 1 | t50 | 128 | 0.9510 | 0.81 | ✓ |  |
| sharp_convergence | totals | soft | all | 1 | t50 | 128 | 0.9510 | 0.81 | ✓ |  |
| sharp_convergence | totals | all | all | 1 | t75 | 56 | 0.7424 | 1.11 | ✓ |  |
| sharp_convergence | totals | soft | all | 1 | t75 | 56 | 0.7424 | 1.11 | ✓ |  |
| sharp_convergence | totals | all | mid | 1 | t50 | 67 | 0.6129 | 1.09 | ✓ |  |
| sharp_convergence | totals | soft | mid | 1 | t50 | 67 | 0.6129 | 1.09 | ✓ |  |
| reversion | totals | bovada | low | 1 | t50 | 98 | 0.6071 | 0.51 | ✓ |  |
| reversion | totals | majors | low | 1 | t50 | 130 | 0.5551 | 0.50 | ✓ |  |
| reversion | totals | pinnacle | low | 1 | t50 | 85 | 0.5235 | 0.47 | ✓ |  |
| reversion | totals | soft | low | 1 | t50 | 152 | 0.5219 | 0.50 | ✓ |  |
| reversion | totals | all | low | 1 | t50 | 159 | 0.5088 | 0.49 | ✓ |  |
| sharp_convergence | totals | bovada | high | 0.5 | t50 | 133 | 0.4323 | 0.37 | ✓ |  |
| reversion | totals | bovada | high | 1 | t50 | 114 | 0.4298 | 0.29 | ✓ |  |
| sharp_convergence | totals | all | high | 0.5 | t50 | 536 | 0.3668 | 0.49 | ✓ |  |
| sharp_convergence | totals | soft | high | 0.5 | t50 | 536 | 0.3668 | 0.49 | ✓ |  |
| reversion | totals | all | high | 1 | t50 | 194 | 0.3652 | 0.28 | ✓ |  |
| reversion | totals | soft | high | 1 | t50 | 186 | 0.3446 | 0.26 | ✓ |  |
| sharp_convergence | totals | majors | high | 0.5 | t50 | 457 | 0.3435 | 0.48 | ✓ |  |
| reversion | totals | pinnacle | high | 1 | t50 | 100 | 0.3400 | 0.28 | ✓ |  |
| reversion | totals | bovada | all | 1 | t50 | 403 | 0.3127 | 0.30 | ✓ |  |
| reversion | totals | majors | high | 1 | t50 | 160 | 0.3078 | 0.24 | ✓ |  |
| sharp_convergence | totals | majors | low | 0.5 | t50 | 481 | 0.2976 | 0.48 | ✓ |  |
| sharp_convergence | totals | majors | all | 0.5 | t50 | 2685 | 0.2969 | 0.62 | ✓ |  |

## Candidate shortlist (forward-CLV targets — NOT declared edges)

- **static_over|totals|all|low|θna|open** (1757 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.1707, clv_p 0.0000, realized-ROI -0.0255, per-season {'2023': 0.3081, '2024': 0.1607, '2025': 0.1369, '2026': 0.0965}
- **static_under|totals|all|high|θna|open** (1323 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.1817, clv_p 0.0000, realized-ROI -0.0104, per-season {'2023': 0.1632, '2024': 0.2081, '2025': 0.199, '2026': 0.158}
- **reversion|totals|all|all|θ0.5|t50** (4375 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.1191, clv_p 0.0000, realized-ROI -0.0649, per-season {'2023': 0.1374, '2024': 0.1231, '2025': 0.1142, '2026': 0.0819}
- **reversion|totals|all|all|θ0.5|t75** (4805 games, book-groups ['all', 'bovada', 'pinnacle', 'soft']) — mean CLV 0.0665, clv_p 0.0000, realized-ROI -0.0659, per-season {'2023': 0.0685, '2024': 0.0717, '2025': 0.0791, '2026': 0.0227}
- **reversion|totals|all|all|θ1|t50** (662 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2828, clv_p 0.0000, realized-ROI -0.0084, per-season {'2023': 0.3555, '2024': 0.3356, '2025': 0.1829, '2026': 0.1514}
- **reversion|totals|all|low|θ0.5|t50** (951 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.1654, clv_p 0.0000, realized-ROI -0.0413, per-season {'2023': 0.2444, '2024': 0.1677, '2025': 0.1528, '2026': 0.0966}
- **reversion|totals|all|low|θ1|t50** ⚠️ FRAGILE (159 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.5088, clv_p 0.0000, realized-ROI 0.0254, per-season {'2023': 0.7692, '2024': 0.5429, '2025': 0.3069, '2026': 0.4124}
- **reversion|totals|all|mid|θ0.5|t50** (2918 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.0894, clv_p 0.0000, realized-ROI -0.0815, per-season {'2023': 0.0884, '2024': 0.0834, '2025': 0.1027, '2026': 0.0746}
- **reversion|totals|all|mid|θ0.5|t75** (3157 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.0614, clv_p 0.0000, realized-ROI -0.0733, per-season {'2023': 0.0601, '2024': 0.0622, '2025': 0.0696, '2026': 0.0409}
- **reversion|totals|all|mid|θ1|t50** (340 games, book-groups ['all', 'majors', 'soft']) — mean CLV 0.1175, clv_p 0.0000, realized-ROI -0.0705, per-season {'2023': 0.0707, '2024': 0.1594, '2025': 0.1258, '2026': 0.0901}
- **reversion|totals|all|mid|θ1|t75** (434 games, book-groups ['all', 'majors', 'pinnacle', 'soft']) — mean CLV 0.0877, clv_p 0.0000, realized-ROI -0.1083, per-season {'2023': 0.0691, '2024': 0.1201, '2025': 0.0652, '2026': 0.0719}
- **reversion|totals|all|high|θ0.5|t50** (860 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.1842, clv_p 0.0000, realized-ROI -0.0357, per-season {'2023': 0.1924, '2024': 0.2567, '2025': 0.145, '2026': 0.1297}
- **reversion|totals|all|high|θ1|t50** ⚠️ FRAGILE (194 games, book-groups ['all']) — mean CLV 0.3652, clv_p 0.0001, realized-ROI 0.0695, per-season {'2023': 0.4807, '2024': 0.6349, '2025': 0.1511, '2026': 0.0901}
- **reversion|totals|bovada|low|θ0.5|t75** (656 games, book-groups ['bovada']) — mean CLV 0.0648, clv_p 0.0000, realized-ROI -0.0364, per-season {'2023': 0.0625, '2024': 0.0703, '2025': 0.0928, '2026': 0.0046}
- **sharp_convergence|totals|all|all|θ0.5|t50** (3122 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2957, clv_p 0.0000, realized-ROI -0.0069, per-season {'2023': 0.2852, '2024': 0.282, '2025': 0.3148, '2026': 0.3131}
- **sharp_convergence|totals|all|all|θ0.5|t75** (2679 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2404, clv_p 0.0000, realized-ROI -0.0026, per-season {'2023': 0.2366, '2024': 0.2151, '2025': 0.2598, '2026': 0.2684}
- **sharp_convergence|totals|all|all|θ1|t50** ⚠️ FRAGILE (128 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.9510, clv_p 0.0000, realized-ROI 0.1112, per-season {'2023': 1.0858, '2024': 1.0414, '2025': 0.7278, '2026': 0.8316}
- **sharp_convergence|totals|all|all|θ1|t75** ⚠️ FRAGILE (56 games, book-groups ['all', 'soft']) — mean CLV 0.7424, clv_p 0.0000, realized-ROI -0.0711, per-season {'2023': 0.2083, '2024': 0.7, '2025': 0.715, '2026': 1.6286}
- **sharp_convergence|totals|all|low|θ0.5|t50** (569 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2849, clv_p 0.0000, realized-ROI -0.0434, per-season {'2023': 0.2312, '2024': 0.2779, '2025': 0.3252, '2026': 0.3214}
- **sharp_convergence|totals|all|low|θ0.5|t75** (526 games, book-groups ['all', 'majors', 'soft']) — mean CLV 0.2092, clv_p 0.0000, realized-ROI -0.0464, per-season {'2023': 0.2417, '2024': 0.1972, '2025': 0.2045, '2026': 0.2057}
- **sharp_convergence|totals|all|mid|θ0.5|t50** (2061 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2836, clv_p 0.0000, realized-ROI -0.0006, per-season {'2023': 0.2612, '2024': 0.2829, '2025': 0.3093, '2026': 0.2713}
- **sharp_convergence|totals|all|mid|θ0.5|t75** (1704 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2413, clv_p 0.0000, realized-ROI 0.0112, per-season {'2023': 0.223, '2024': 0.2152, '2025': 0.2717, '2026': 0.2814}
- **sharp_convergence|totals|all|mid|θ1|t50** ⚠️ FRAGILE (67 games, book-groups ['all', 'soft']) — mean CLV 0.6129, clv_p 0.0000, realized-ROI -0.0119, per-season {'2023': 0.6406, '2024': 0.5382, '2025': 0.7267, '2026': 0.3889}
- **sharp_convergence|totals|all|high|θ0.5|t50** (536 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.3668, clv_p 0.0000, realized-ROI 0.0103, per-season {'2023': 0.3748, '2024': 0.3344, '2025': 0.3399, '2026': 0.4504}
- **sharp_convergence|totals|all|high|θ0.5|t75** (468 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.2797, clv_p 0.0000, realized-ROI -0.0063, per-season {'2023': 0.2649, '2024': 0.2581, '2025': 0.2835, '2026': 0.36}
- **static_home|h2h|all|all|θna|open** (7262 games, book-groups ['all', 'majors', 'soft']) — mean CLV 0.0016, clv_p 0.0017, realized-ROI -0.0300, per-season {'2023': 0.0001, '2024': 0.0021, '2025': 0.0009, '2026': 0.0053}
- **reversion|h2h|all|all|θ0.02|t50** (2716 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.0050, clv_p 0.0000, realized-ROI 0.0124, per-season {'2023': 0.0058, '2024': 0.0053, '2025': 0.0043, '2026': 0.0042}
- **reversion|h2h|all|all|θ0.04|t50** (913 games, book-groups ['all', 'bovada', 'majors', 'pinnacle', 'soft']) — mean CLV 0.0136, clv_p 0.0000, realized-ROI 0.0860, per-season {'2023': 0.0146, '2024': 0.0149, '2025': 0.0143, '2026': 0.0055}
- **sharp_convergence|h2h|all|all|θ0.02|t75** (637 games, book-groups ['all', 'bovada', 'majors', 'soft']) — mean CLV 0.0156, clv_p 0.0000, realized-ROI 0.0613, per-season {'2023': 0.0169, '2024': 0.0092, '2025': 0.0179, '2026': 0.0221}
- **sharp_convergence|h2h|all|all|θ0.04|t75** ⚠️ FRAGILE (69 games, book-groups ['all', 'soft']) — mean CLV 0.0371, clv_p 0.0054, realized-ROI 0.0001, per-season {'2023': 0.0374, '2024': 0.0068, '2025': 0.034, '2026': 0.0703}
- **sharp_convergence|h2h|bovada|all|θ0.02|t50** (306 games, book-groups ['bovada']) — mean CLV 0.0191, clv_p 0.0001, realized-ROI 0.0750, per-season {'2023': 0.0141, '2024': 0.0197, '2025': 0.0261, '2026': 0.0097}
- **sharp_convergence|h2h|bovada|all|θ0.04|t50** ⚠️ FRAGILE (64 games, book-groups ['bovada']) — mean CLV 0.0722, clv_p 0.0000, realized-ROI 0.4071, per-season {'2023': 0.1349, '2024': 0.0592, '2025': 0.0726, '2026': 0.047}

### ⚠️ Honest reading (a candidate ≠ a declared edge)
- The verdict is **not live cashability**. Each candidate is a target for the **forward-CLV leg** (E2.6): confirm beat-the-close prospectively on the accruing 30-min captures at PBO<0.2/DSR>0. The historical trajectory is granularity-limited, so a historical survivor is a hypothesis to confirm forward, never a live green light.

## H4 / H5 — deferred, engine-ready (forward-only data)

- **H4 weather → total (lag):** `weather_intraday_series` (hourly, per game_pk; temp / wind speed+direction / humidity; outdoor parks) is S3-only from 2026-07-01 → pre-registered + aligned to the totals trajectory the moment the prefix has depth. LOGGED, never dropped.
- **H5 public-% → line (reverse line movement):** `public_betting_intraday_series` (hourly; ML + totals money%/ticket%; FanDuel book 15; game_pk via the ActionNetwork crosswalk) is S3-only from 2026-07-01 → pre-registered + engine-ready, DEFERRED to forward accrual.

## Forward-CLV accrual plan (the REAL test)

1. The 30-min `odds_capture` already writes `mart_odds_outcomes` → the fine trajectory accrues automatically; re-run `--build-cache` + this eval weekly.
2. A signal is CONFIRMED only when it clears PBO<0.2 / DSR≥0.95 / FDR on the PROSPECTIVE captures (≥ a full season of fine games), not the granularity-limited historical run.
3. Enable the W11-C / W11-D hourly schedules (`W11_RAW_WRITE_MODE=s3|both`) to start accruing the H4/H5 series; assemble them once each has depth.

_Generated by `eval_line_microstructure.py` (E13.16). Configs scored GAME-level (correlated book-quotes collapsed per game). Every signal × segment × θ × anchor config is logged in `e13_16_signal_grid_results.csv` (no cherry-pick). Gate constants: PBO<0.2, DSR≥0.95._