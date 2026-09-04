# NF-INJ4 — data census (node 1), run BEFORE the pre-registration

Generated 2026-09-03T06:01:46+00:00. Season 2025. Regenerate with `uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4_census`.

> Every number below is a DESIGN quantity — depth, cell sizes, coverage, censoring, provenance. No arm is fitted, ranked or chosen here. The one exception is §5, a FRAME-INTEGRITY check, recorded rather than hidden: a frame in which `out` players play is broken, and registering a study on it would be the most expensive kind of silent null.

## 0. What the census concluded (and what it cost)

- **The substrate is ONE season, 1309 player-weeks, 398 players, 18/18 weeks.** Season-transfer is structurally unmeasurable at `n_seasons = 1`; 2026 is the named, genuinely reachable re-test.
- **The NF-W0a forward capture contributes ZERO usable rows.** It holds 12136 rows, ALL `season=2025`, ALL captured on ['2026-08-05'] — i.e. one post-season backfill of the finished season, whose capture instant is months AFTER every 2025 gameday and therefore point-in-time inadmissible for it. 2026 rows: 0 (Week 1 is 2026-09-09). The spec's "plus the NF-W0a forward capture (2026)" premise does not hold today.
- **ESPN's 537 rows are inadmissible** — its designations are attributed ONE WEEK LATE (§3a), which leaves them with no point-in-time-valid week in either reading. Cost: 97 distinct player-weeks the other two sources do not already cover.
- **A NULL `report_status` is MISSING, not a level** (§3b) — nfl.com fills its game-status column only on the final report.
- **The pre-registered resolution SENSITIVITY is INACTIVE** (§3c): all 18 conflicting player-weeks resolve identically under both rules, so its agreement carries no information.
- **The `doubtful` cell holds 29 rows and its thinnest position cell holds 1**, so a designation x position family cannot be certified at this depth — which is exactly why the registration declares the coarser conditioning shapes FORWARD, with a min-cell backoff, rather than choosing after a fit.

## 1. Substrate depth, measured

```json
{
  "substrate_wayback": {
    "rows_landed_all_sources": 2187,
    "rows_by_source": {
      "cbs": 1021,
      "nfl": 629,
      "espn": 537
    },
    "distinct_player_weeks_all_sources": 1406,
    "admissible_sources": [
      "nfl",
      "cbs"
    ],
    "excluded_sources": [
      "espn"
    ],
    "distinct_player_weeks_admissible": 1309,
    "player_weeks_lost_to_exclusion": 97,
    "store_subjects_with_more_than_one_capture": 0,
    "revision_clause_activity": "INACTIVE \u2014 no store subject holds more than one capture, so the \u00a713 revised-vendor-record clause had nothing to act on. Reported so 'it did not fire' is never read as 'it passed' (NF-D20)."
  },
  "substrate_forward_capture": {
    "rows": 12136,
    "seasons": {
      "2025": {
        "n": 12136,
        "min_week": 1,
        "max_week": 22
      }
    },
    "distinct_capture_dates": [
      "2026-08-05"
    ],
    "usable_2026_rows": 0
  },
  "resolution": {
    "rule": "the LATEST admissible capture CARRYING a designation wins; a player-week designated in no admissible capture resolves to `none_listed` (a NULL report_status is MISSING within a capture, never a resolved absence)",
    "sensitivity_rule": "most SEVERE designation wins, recency breaks ties (pre-registered sensitivity; see `sensitivity_activity` before reading its agreement)",
    "player_weeks_where_the_two_rules_disagree": 0,
    "sensitivity_activity": {
      "player_weeks_with_more_than_one_distinct_designation": 18,
      "of_those_latest_equals_strongest": 18,
      "resolution_pairs": {
        "latest=out|strongest=out": 18
      },
      "sensitivity_is_active": false,
      "reading": "INACTIVE \u2014 every conflicting player-week resolves identically under both rules, because in this population a designation only ever ESCALATES through the week (questionable \u2192 out) and never de-escalates. The pre-registered sensitivity is therefore guaranteed byte-identical to the primary, and its agreement carries NO information (NF-D20: an inactive clause is uninformative, never a pass)."
    },
    "null_designation_is_missing_not_a_level": {
      "capture_lead_days_by_source_and_designation_presence": {
        "cbs|has_designation=True": {
          "n": 1021,
          "median": 1.617,
          "q25": 0.606,
          "q75": 3.432
        },
        "nfl|has_designation=False": {
          "n": 499,
          "median": 1.525,
          "q25": 1.01,
          "q75": 1.74
        },
        "nfl|has_designation=True": {
          "n": 130,
          "median": 0.339,
          "q25": 0.233,
          "q75": 1.01
        }
      },
      "captures_by_source_dow_and_designation_presence": {
        "cbs|Friday|has_designation=True": 203,
        "cbs|Monday|has_designation=True": 15,
        "cbs|Saturday|has_designation=True": 259,
        "cbs|Sunday|has_designation=True": 113,
        "cbs|Thursday|has_designation=True": 216,
        "cbs|Tuesday|has_designation=True": 99,
        "cbs|Wednesday|has_designation=True": 116,
        "nfl|Friday|has_designation=False": 352,
        "nfl|Friday|has_designation=True": 45,
        "nfl|Saturday|has_designation=False": 85,
        "nfl|Saturday|has_designation=True": 69,
        "nfl|Sunday|has_designation=False": 7,
        "nfl|Sunday|has_designation=True": 6,
        "nfl|Thursday|has_designation=False": 50,
        "nfl|Wednesday|has_designation=False": 5,
        "nfl|Wednesday|has_designation=True": 10
      }
    }
  },
  "pit_gate": {
    "invoked": true,
    "records_checked": 1309,
    "rows_dropped": 0,
    "rows_kept": 1309,
    "findings_by_reason": {},
    "rows_without_a_resolvable_gameday": 0
  }
}
```

## 2. The modelled frame

1309 rows / 398 distinct players / 18 weeks.

### Cell sizes — designation x position

|              |   QB |   RB |   TE |   WR |
|:-------------|-----:|-----:|-----:|-----:|
| out          |   27 |   32 |   42 |   98 |
| doubtful     |    1 |   11 |    6 |   11 |
| questionable |   93 |  174 |  189 |  386 |
| none_listed  |   35 |   46 |   55 |  103 |

### Cell sizes — designation x practice participation

|              |   dnp |   full |   limited |   unknown |
|:-------------|------:|-------:|----------:|----------:|
| doubtful     |    20 |      0 |         4 |         5 |
| none_listed  |    27 |    152 |        60 |         0 |
| out          |    33 |      0 |         7 |       159 |
| questionable |   152 |     44 |       354 |       292 |

## 3a. Source week-attribution probe (the SOURCE-admissibility decision)

A source whose designation describes week `w` should peak at lag 0. One peaks at lag -1.

| source   | designation   |   n@lag0 |   miss@lag-1 |   miss@lag0 |   miss@lag+1 |
|:---------|:--------------|---------:|-------------:|------------:|-------------:|
| cbs      | doubtful      |       28 |       0.4074 |      1      |       0.6087 |
| cbs      | out           |      165 |       0.5223 |      1      |       0.6439 |
| cbs      | questionable  |      828 |       0.3459 |      0.2681 |       0.2313 |
| espn     | doubtful      |       10 |       0.5714 |      1      |       0.7778 |
| espn     | out           |      159 |       0.9858 |      0.4843 |       0.3399 |
| espn     | questionable  |      368 |       0.4007 |      0.4103 |       0.3027 |
| nfl      | doubtful      |        2 |       0.5    |      1      |       0.5    |
| nfl      | none_listed   |      499 |       0.2678 |      0.2144 |       0.2058 |
| nfl      | out           |       58 |       0.4138 |      0.931  |       0.5357 |
| nfl      | questionable  |       70 |       0.2899 |      0.3286 |       0.1714 |

## 3b. Capture timing (the NULL-designation decision)

`report_status` NULL is treated as MISSING within a capture rather than as a level, because nfl.com fills its game-status column only on the final report:

|                           |    n |   median |   q25 |   q75 |
|:--------------------------|-----:|---------:|------:|------:|
| cbs|has_designation=True  | 1021 |    1.617 | 0.606 | 3.432 |
| nfl|has_designation=False |  499 |    1.525 | 1.01  | 1.74  |
| nfl|has_designation=True  |  130 |    0.339 | 0.233 | 1.01  |

## 3c. Is the pre-registered resolution SENSITIVITY able to act?

```json
{
  "player_weeks_with_more_than_one_distinct_designation": 18,
  "of_those_latest_equals_strongest": 18,
  "resolution_pairs": {
    "latest=out|strongest=out": 18
  },
  "sensitivity_is_active": false,
  "reading": "INACTIVE \u2014 every conflicting player-week resolves identically under both rules, because in this population a designation only ever ESCALATES through the week (questionable \u2192 out) and never de-escalates. The pre-registered sensitivity is therefore guaranteed byte-identical to the primary, and its agreement carries NO information (NF-D20: an inactive clause is uninformative, never a pass)."
}
```

## 4. The target

```json
{
  "definition": "consecutive team games missed from the designation week onward, terminated by the next appearance; right-censored at the season end",
  "mean": 0.8052,
  "sd": 1.7359,
  "zero_share": 0.6555,
  "max": 14,
  "distribution": {
    "0": 858,
    "1": 222,
    "2": 104,
    "3": 55,
    "4": 26,
    "5": 12,
    "6": 7,
    "7": 4,
    "8": 4,
    "9": 3,
    "10": 3,
    "11": 3,
    "12": 3,
    "13": 3,
    "14": 2
  },
  "censored_rows": 77,
  "censored_share": 0.0588,
  "games_remaining": {
    "count": 1309.0,
    "mean": 9.08,
    "std": 5.09,
    "min": 1.0,
    "25%": 4.0,
    "50%": 9.0,
    "75%": 13.0,
    "max": 17.0
  }
}
```

## 5. Frame integrity

does an `out` designation overwhelmingly produce a miss? A frame in which it does not is BROKEN, and registering on it would be a silent null. Recorded rather than hidden; no arm is fitted, ranked or chosen on it.

|              |   n |   zero_share |
|:-------------|----:|-------------:|
| doubtful     |  29 |       0      |
| none_listed  | 239 |       0.954  |
| out          | 199 |       0.0201 |
| questionable | 842 |       0.7435 |

## 6. Power arithmetic (PLAT-CVP2 `validate_sign_certifiability` + operating characteristics)

|   n_folds | single_hypothesis                                                                                                               | arm_corrected                                                                                                                        | fold_consistency                                                                                   | pbo_evaluable   |   dsr_ceiling |   mde_sd_units |
|----------:|:--------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------|:----------------|--------------:|---------------:|
|         7 | {'bh_cutoff': 0.05, 'sign_floor': 0.00781, 'certifiable': True, 'headroom': 0.1562, 'folds_needed': 5, 'margin_rule_met': True} | {'bh_cutoff': 0.00714, 'sign_floor': 0.00781, 'certifiable': False, 'headroom': 1.0938, 'folds_needed': 8, 'margin_rule_met': False} | {'wins_required': 6, 'attainable': True, 'attained_false_fire': 0.0625, 'legacy_wins_required': 5} | True            |        0.9997 |           1.2  |
|         8 | {'bh_cutoff': 0.05, 'sign_floor': 0.00391, 'certifiable': True, 'headroom': 0.0781, 'folds_needed': 5, 'margin_rule_met': True} | {'bh_cutoff': 0.00714, 'sign_floor': 0.00391, 'certifiable': True, 'headroom': 0.5469, 'folds_needed': 8, 'margin_rule_met': False}  | {'wins_required': 6, 'attainable': True, 'attained_false_fire': 0.1445, 'legacy_wins_required': 5} | True            |        0.9999 |           0.95 |
|        10 | {'bh_cutoff': 0.05, 'sign_floor': 0.00098, 'certifiable': True, 'headroom': 0.0195, 'folds_needed': 5, 'margin_rule_met': True} | {'bh_cutoff': 0.00714, 'sign_floor': 0.00098, 'certifiable': True, 'headroom': 0.1367, 'folds_needed': 8, 'margin_rule_met': True}   | {'wins_required': 7, 'attainable': True, 'attained_false_fire': 0.1719, 'legacy_wins_required': 6} | True            |        1      |           0.8  |
|        12 | {'bh_cutoff': 0.05, 'sign_floor': 0.00024, 'certifiable': True, 'headroom': 0.0049, 'folds_needed': 5, 'margin_rule_met': True} | {'bh_cutoff': 0.00714, 'sign_floor': 0.00024, 'certifiable': True, 'headroom': 0.0342, 'folds_needed': 8, 'margin_rule_met': True}   | {'wins_required': 8, 'attainable': True, 'attained_false_fire': 0.1938, 'legacy_wins_required': 8} | True            |        1      |           0.75 |

```json
{
  "n_arms_planned": 7,
  "by_fold_count": [
    {
      "n_folds": 7,
      "single_hypothesis": {
        "bh_cutoff": 0.05,
        "sign_floor": 0.00781,
        "certifiable": true,
        "headroom": 0.1562,
        "folds_needed": 5,
        "margin_rule_met": true
      },
      "arm_corrected": {
        "bh_cutoff": 0.00714,
        "sign_floor": 0.00781,
        "certifiable": false,
        "headroom": 1.0938,
        "folds_needed": 8,
        "margin_rule_met": false
      },
      "fold_consistency": {
        "wins_required": 6,
        "attainable": true,
        "attained_false_fire": 0.0625,
        "legacy_wins_required": 5
      },
      "pbo_evaluable": true,
      "dsr_ceiling": 0.9997,
      "mde_sd_units": 1.2
    },
    {
      "n_folds": 8,
      "single_hypothesis": {
        "bh_cutoff": 0.05,
        "sign_floor": 0.00391,
        "certifiable": true,
        "headroom": 0.0781,
        "folds_needed": 5,
        "margin_rule_met": true
      },
      "arm_corrected": {
        "bh_cutoff": 0.00714,
        "sign_floor": 0.00391,
        "certifiable": true,
        "headroom": 0.5469,
        "folds_needed": 8,
        "margin_rule_met": false
      },
      "fold_consistency": {
        "wins_required": 6,
        "attainable": true,
        "attained_false_fire": 0.1445,
        "legacy_wins_required": 5
      },
      "pbo_evaluable": true,
      "dsr_ceiling": 0.9999,
      "mde_sd_units": 0.95
    },
    {
      "n_folds": 10,
      "single_hypothesis": {
        "bh_cutoff": 0.05,
        "sign_floor": 0.00098,
        "certifiable": true,
        "headroom": 0.0195,
        "folds_needed": 5,
        "margin_rule_met": true
      },
      "arm_corrected": {
        "bh_cutoff": 0.00714,
        "sign_floor": 0.00098,
        "certifiable": true,
        "headroom": 0.1367,
        "folds_needed": 8,
        "margin_rule_met": true
      },
      "fold_consistency": {
        "wins_required": 7,
        "attainable": true,
        "attained_false_fire": 0.1719,
        "legacy_wins_required": 6
      },
      "pbo_evaluable": true,
      "dsr_ceiling": 1.0,
      "mde_sd_units": 0.8
    },
    {
      "n_folds": 12,
      "single_hypothesis": {
        "bh_cutoff": 0.05,
        "sign_floor": 0.00024,
        "certifiable": true,
        "headroom": 0.0049,
        "folds_needed": 5,
        "margin_rule_met": true
      },
      "arm_corrected": {
        "bh_cutoff": 0.00714,
        "sign_floor": 0.00024,
        "certifiable": true,
        "headroom": 0.0342,
        "folds_needed": 8,
        "margin_rule_met": true
      },
      "fold_consistency": {
        "wins_required": 8,
        "attainable": true,
        "attained_false_fire": 0.1938,
        "legacy_wins_required": 8
      },
      "pbo_evaluable": true,
      "dsr_ceiling": 1.0,
      "mde_sd_units": 0.75
    }
  ]
}
```
