#!/usr/bin/env python3
"""NF-INJ3b-SHIP RED PROOF — break the source one defect at a time, require the NAMED clause to go
RED.

    uv run python betting_ml/tests/nf_inj3b_ship_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`).

WHY IT EXISTS FOR THIS STORY. Every defect this change can have is SILENT. A board that serves the
INCUMBENT caps under the fitted arm's stamp renders identically to one that flipped correctly — the
flagged veteran is capped either way, just at a different number, and the stamp says the same thing
in both worlds. A covariate feed that drifted from the study's definition produces plausible games
from a model that is no longer the certified one. A leakage gate that admitted a training season
would score a past board with a model that read its future, and the board would look fine. None of
those raises, and the D6 guard is the ONLY thing standing between them and a publish — so a vacuous
clause here is worse than no clause at all (NF1.7 (a)).

The harness contract is carried verbatim from `nf_inj3c_red_proof.py`, including all three ways a
red proof lies: a mutation that never LANDS (E11.24 #682), one that lands on the WRONG symbol (the
non-unique anchor), and one that lands and does not MOVE the asserted predicate (#815). It restores
stale backups AT START-UP, because a `| head` closing stdout mid-mutation leaves deliberately-broken
source on disk (E11.26).

⛔ Deliberately not `git checkout --`: that destroys uncommitted work in the files it patches.
"""
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_F = REPO / "quant_sports_intel_models/football/nfl/fantasy"
GUARD = _F / "injury_games_publish_guard.py"
FEED = _F / "injury_covariate_feed.py"
POLICY = _F / "injury_games_policy.py"
SERVING = _F / "injury_games_serving.py"
SEASON = _F / "season_projection.py"
RUNNER = _F / "run_season_projection.py"
EXPORT = _F / "export_draft_board_json.py"
STUDY = _F / "nf_inj3_injury_games.py"
STUDY_RUNNER = _F / "run_nf_inj3_injury_games.py"

FLIPPED_DIFF = _F / "run_nf_inj3b_ship_flipped_diff.py"
COMBINED_READ = _F / "run_nf_inj3b_ship_combined_read.py"

FILES = (GUARD, FEED, POLICY, SERVING, SEASON, RUNNER, EXPORT, STUDY, STUDY_RUNNER,
         FLIPPED_DIFF, COMBINED_READ)

SUITE_GUARD = "betting_ml/tests/test_nf_inj3b_ship_stamp_guard.py"
SUITE_RUNNERS = "betting_ml/tests/test_nf_inj3b_ship_runners.py"
SUITE_FEED = "betting_ml/tests/test_nf_inj3b_ship_covariate_feed.py"
SUITE_STUDY = "betting_ml/tests/test_nf_inj3_injury_games.py"

#: `(label, file, anchor, replacement, gone_after, suite, the ONE test that must go red)`.
CASES = [
    # ══ D6 — THE FOUR LEGS OF THE STAMP GUARD ═══════════════════════════════════════════════════
    ("(leg 1) the guard stops looking at the ROWS, so a fed-less build passes on its stamp alone",
     GUARD,
     '    elif claims_fitted and n_fitted == 0:',
     '    elif False:',
     "elif claims_fitted and n_fitted == 0:", SUITE_GUARD,
     "TestTheFourLegs::test_the_stamp_present_but_NO_ROW_SERVED_is_REFUSED"),

    ("(leg 1b) a flip that moved NOTHING is accepted", GUARD,
     '    elif claims_fitted and n_moved == 0:',
     '    elif False:',
     "elif claims_fitted and n_moved == 0:", SUITE_GUARD,
     "TestTheFourLegs::test_the_stamp_present_but_rows_UNCHANGED_is_REFUSED"),

    ("(leg 2) the guard stops looking at the STAMP, so moved rows pass unattributed", GUARD,
     '    elif n_fitted > 0 or n_moved > 0:',
     '    elif False:',
     "elif n_fitted > 0 or n_moved > 0:", SUITE_GUARD,
     "TestTheFourLegs::test_rows_changed_with_NO_fitted_stamp_is_REFUSED"),

    ("(leg 3) a legitimate flip is refused — the guard is not two-sided", GUARD,
     '    elif claims_fitted:\n        verdict, detail = "FLIPPED_AND_MOVED"',
     '    elif claims_fitted:\n        verdict, detail = "STAMPED_BUT_UNMOVED"',
     'verdict, detail = "FLIPPED_AND_MOVED"', SUITE_GUARD,
     "TestTheFourLegs::test_a_legitimate_flip_PASSES"),

    ("(leg 4) a legitimate flag-off build is refused", GUARD,
     'PASSING = ("FLIPPED_AND_MOVED", "INCUMBENT_CLEAN", "NO_CERTIFIED_ROWS", "PRE_STORY_BOARD")',
     'PASSING = ("FLIPPED_AND_MOVED", "NO_CERTIFIED_ROWS", "PRE_STORY_BOARD")',
     '"FLIPPED_AND_MOVED", "INCUMBENT_CLEAN"', SUITE_GUARD,
     "TestTheFourLegs::test_a_legitimate_flag_off_build_PASSES_with_no_fitted_stamp"),

    # ══ THE GUARD'S OWN VACUITY FLOORS ══════════════════════════════════════════════════════════
    ("an INACTIVE board (no certified rows) is credited as a clean flip", GUARD,
     '    if n_certified == 0 and n_fitted == 0:\n        verdict, detail = "NO_CERTIFIED_ROWS", (',
     '    if n_certified == 0 and n_fitted == 0:\n        verdict, detail = "FLIPPED_AND_MOVED", (',
     'verdict, detail = "NO_CERTIFIED_ROWS", (', SUITE_GUARD,
     "TestItCannotBeSatisfiedVacuously::"
     "test_a_board_with_NO_certified_rows_passes_but_is_NOT_reported_as_a_clean_flip"),

    ("a board claiming the fitted arm with NO evidence columns is scored healthy", GUARD,
     '        verdict = "UNVERIFIABLE" if claims_fitted else "PRE_STORY_BOARD"',
     '        verdict = "PRE_STORY_BOARD"',
     '"UNVERIFIABLE" if claims_fitted', SUITE_GUARD,
     "TestItCannotBeSatisfiedVacuously::"
     "test_a_board_claiming_the_fitted_arm_with_NO_evidence_columns_is_UNVERIFIABLE"),

    ("two concatenated builds are resolved by majority vote instead of refused", GUARD,
     '    if len(vals) > 1:\n        raise ValueError(',
     '    if False:\n        raise ValueError(',
     "if len(vals) > 1:", SUITE_GUARD,
     "TestItCannotBeSatisfiedVacuously::"
     "test_two_concatenated_builds_are_a_HARD_ERROR_not_a_majority_vote"),

    ("the board comparison becomes BITWISE (the QkpAHBYa standing rule)", GUARD,
     "MATERIAL_ATOL = 1e-9",
     "MATERIAL_ATOL = 0.0",
     "MATERIAL_ATOL = 1e-9", SUITE_GUARD,
     "TestTheComparisonIsMaterialNeverBitwise::"
     "test_a_sub_tolerance_move_does_NOT_count_as_a_flip"),

    ("the guard asks the POLICY whether serving is on instead of reading the artifact", GUARD,
     "    stamp = _one(board, STAMP_COL)\n    stamp = None if stamp is None else str(stamp)\n"
     "    claims_fitted = (stamp == POLICY.MODEL_VERSION)",
     "    stamp = _one(board, STAMP_COL)\n    stamp = None if stamp is None else str(stamp)\n"
     "    claims_fitted = POLICY.serving_enabled()",
     "claims_fitted = (stamp == POLICY.MODEL_VERSION)", SUITE_GUARD,
     "TestTheGuardReadsTheARTIFACTNotThePolicy::test_the_verdict_does_not_consult_serving_enabled"),

    # ══ THE GUARD'S WIRING INTO THE PUBLISH PATH ════════════════════════════════════════════════
    # ⭐ This case is the one that found a REAL vacuity: the clause used to match the guard's
    # own `def` line and stayed GREEN with the call site deleted (NF-C0e wired-vs-invoked, inside
    # the guard written to catch it). The clause now reads `main`'s source only.
    ("the guard is unwired from the exporter (wired-but-never-invoked, NF-C0e)", EXPORT,
     "    _inj_stamp = assert_injury_games_stamp_coherent(pdf, args.season)",
     "    _inj_stamp = None",
     "_inj_stamp = assert_injury_games_stamp_coherent(", SUITE_GUARD,
     "TestItIsWiredIntoThePublishPath::test_the_exporter_calls_the_guard"),

    ("a refusal is raised as a plain Exception, which the exporter's own `except` swallows", EXPORT,
     '        raise SystemExit(_IGPG.refusal_message(result, season))',
     '        raise RuntimeError(_IGPG.refusal_message(result, season))',
     "raise SystemExit(_IGPG.refusal_message(", SUITE_GUARD,
     "TestItIsWiredIntoThePublishPath::"
     "test_a_failing_verdict_RAISES_SystemExit_so_it_survives_the_exporters_own_except"),

    ("an unreadable board is scored HEALTHY instead of UNVERIFIED", EXPORT,
     '        log.warning("[ALERT] NF-INJ3b-SHIP injury-games stamp guard DID NOT RUN — the projection "',
     '        log.info("[ALERT] NF-INJ3b-SHIP injury-games stamp OK — the projection "',
     'log.warning("[ALERT] NF-INJ3b-SHIP injury-games stamp guard DID NOT RUN', SUITE_GUARD,
     "TestItIsWiredIntoThePublishPath::"
     "test_an_unreadable_board_is_UNVERIFIED_and_never_scored_healthy"),

    # ⚠️ `gone=None`: this mutation INSERTS a policy read rather than deleting anything, so
    # there is no predicate for the #815 "did it bite?" check to watch disappear. The harness's
    # `patched != src` assertion is what stands in, and the clause under test asserts the ABSENCE
    # of a policy read — which the insertion supplies.
    ("the payload stamp is read from the POLICY MODULE instead of the built board", EXPORT,
     "    present = [c for c in _INJURY_GAMES_COLUMNS if c in pdf.columns]",
     "    from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as _P\n"
     "    return dict(_P.stamp())\n"
     "    present = [c for c in _INJURY_GAMES_COLUMNS if c in pdf.columns]",
     None, SUITE_GUARD,
     "TestItIsWiredIntoThePublishPath::test_the_payload_stamp_is_NOT_read_from_the_policy_module"),

    # ══ THE PER-ROW EVIDENCE THE GUARD DEPENDS ON ═══════════════════════════════════════════════
    ("the row log is filled only on the fitted path, blinding the guard to a fed-less build",
     SERVING,
     "    if not POLICY.serving_enabled():\n        _log_rows(None)",
     "    if not POLICY.serving_enabled():\n        pass",
     "if not POLICY.serving_enabled():\n        _log_rows(None)", SUITE_GUARD,
     "TestTheRollbackIsTheSameCodePath::"
     "test_the_row_log_is_filled_on_EVERY_path_including_the_incumbent_ones"),

    ("the incumbent column is filled only where the FITTED arm produced a value", SEASON,
     '    df["injury_games_incumbent"] = key.map(\n'
     '        dict(zip(pid[cert], np.asarray(row_log["incumbent"], dtype=float)[cert]))\n'
     '    ).astype(float).to_numpy()',
     '    _srv = df["injury_games_served"].to_numpy()\n'
     '    df["injury_games_incumbent"] = np.where(np.isfinite(_srv), key.map(\n'
     '        dict(zip(pid, np.asarray(row_log["incumbent"], dtype=float)))\n'
     '    ).astype(float).to_numpy(), np.nan)',
     'dict(zip(pid[cert], np.asarray(row_log["incumbent"], dtype=float)))', SUITE_GUARD,
     "TestTheRollbackIsTheSameCodePath::test_the_evidence_columns_distinguish_certified_from_served"),

    # ══ D7 — THE COVARIATE FEED ═════════════════════════════════════════════════════════════════
    ("the board build stops building its own covariate feed (the pre-story state)", RUNNER,
     "        injury_covariates, _inj_feed_prov = _IGF.feed_for_board(\n"
     "            con, base, projection_season, schema=schema)",
     "        injury_covariates, _inj_feed_prov = None, {}",
     "_IGF.feed_for_board(", SUITE_FEED,
     "TestTheFeedIsWiredIntoTheBoardBUILD::test_the_board_build_builds_the_feed_itself"),

    ("the auto-built feed OVERRIDES an explicitly supplied one", RUNNER,
     "    if injury_covariates is None:\n        injury_covariates, _inj_feed_prov = _IGF.feed_for_board(",
     "    if True:\n        injury_covariates, _inj_feed_prov = _IGF.feed_for_board(",
     "if injury_covariates is None:\n        injury_covariates", SUITE_FEED,
     "TestTheFeedIsWiredIntoTheBoardBUILD::test_an_explicitly_supplied_feed_still_wins"),

    ("the served feed RE-DERIVES the covariates instead of calling the study's own owner", FEED,
     "    feed = IG.derive_covariates(merged)[list(FEED_COLUMNS)]",
     '    merged["is_qb"] = (merged["position"].astype(str) == "QB").astype(float)\n'
     '    merged["onset_carryover"] = 0.0\n'
     '    merged["weeks_since_last_game"] = 0.0\n'
     '    merged["log1p_prior_fp"] = 0.0\n'
     "    feed = merged[list(FEED_COLUMNS)]",
     "IG.derive_covariates(", SUITE_FEED,
     "TestThereIsExactlyOneDefinition::test_the_served_feed_calls_the_bake_offs_own_derivation"),

    ("build_population re-derives its covariates inline again, so fitted and served can drift",
     STUDY_RUNNER,
     "        flagged = IG.derive_covariates(flagged)",
     '        flagged["log1p_prior_fp"] = 0.0\n'
     '        flagged["is_qb"] = 0.0\n'
     '        flagged["onset_carryover"] = 0.0\n'
     '        flagged["weeks_since_last_game"] = 0.0',
     "IG.derive_covariates(flagged)", SUITE_STUDY,
     "TestPopulation::test_the_covariate_derivation_has_exactly_ONE_owner"),

    ("the no-prior-game sentinel becomes fillna(0) — 'he just played' for a player who did not",
     STUDY,
     "    out[\"weeks_since_last_game\"] = (weeks - lw).fillna(weeks.max() if weeks.notna().any()\n"
     "                                                       else NO_PRIOR_SEASON_WEEKS)",
     "    out[\"weeks_since_last_game\"] = (weeks - lw).fillna(0.0)",
     ".fillna(weeks.max()", SUITE_STUDY,
     "TestPopulation::test_no_prior_game_means_the_LONGEST_absence_not_a_missing_one"),

    ("log1p stops clipping, so a negative-PPR season NaNs a real player out of the design", STUDY,
     '    out["log1p_prior_fp"] = np.log1p(out["prior_fp"].clip(lower=0.0))',
     '    out["log1p_prior_fp"] = np.log1p(out["prior_fp"])',
     'np.log1p(out["prior_fp"].clip(lower=0.0))', SUITE_FEED,
     "TestTheDefinitionsThemselves::"
     "test_log1p_prior_fp_clips_a_NEGATIVE_ppr_season_rather_than_NaN_ing_the_player"),

    ("a frame missing a covariate input emits NaN columns instead of raising", STUDY,
     "    missing = [c for c in COVARIATE_INPUT_COLUMNS if c not in df.columns]\n    if missing:",
     "    missing = []\n    if missing:",
     "missing = [c for c in COVARIATE_INPUT_COLUMNS if c not in df.columns]", SUITE_FEED,
     "TestThereIsExactlyOneDefinition::"
     "test_a_frame_missing_an_input_RAISES_rather_than_emitting_NaN_columns"),

    # ══ THE LEAKAGE GATE ════════════════════════════════════════════════════════════════════════
    ("the leakage gate admits the boundary season the artifact was TRAINED on", FEED,
     "    if int(projection_season) > bound:",
     "    if int(projection_season) >= bound:",
     "if int(projection_season) > bound:", SUITE_FEED,
     "TestTheLeakageGate::test_the_boundary_season_ITSELF_is_refused_not_admitted"),

    # ⚠️ `gone=None` for the same reason as the case above: an INSERTION deletes no predicate.
    ("the leakage bound is HARDCODED instead of read off the served artifact", FEED,
     "    ts = artifact.get(\"train_seasons\")",
     "    return 2025\n    ts = artifact.get(\"train_seasons\")",
     None, SUITE_FEED,
     "TestTheLeakageGate::test_the_bound_is_READ_OFF_THE_ARTIFACT_not_declared_here"),

    ("an artifact with no declared training window silently defaults instead of raising", FEED,
     "    if not isinstance(ts, (list, tuple)) or len(ts) != 2:\n        raise ValueError(",
     "    if False:\n        raise ValueError(",
     "if not isinstance(ts, (list, tuple)) or len(ts) != 2:", SUITE_FEED,
     "TestTheLeakageGate::test_a_missing_train_window_RAISES_rather_than_defaulting"),

    ("a refused season is silent rather than RECORDED", FEED,
     '        return None, {"supplied": False, "reason": reason,\n'
     '                      "projection_season": int(projection_season),',
     '        return None, {"supplied": False, "reason": "",\n'
     '                      "projection_season": int(projection_season),',
     '"supplied": False, "reason": reason,', SUITE_FEED,
     "TestTheLeakageGate::test_a_refusal_is_RECORDED_never_silent"),

    # ══ THE FLIP AND ITS BOUNDARIES ═════════════════════════════════════════════════════════════
    # ══ NODES 4+5 — THE RUNNERS ═════════════════════════════════════════════════════════════════
    ("the rookie-band control collapses to a SINGLE draw (the story's own false positive)",
     _F / "run_nf_inj3b_ship_flipped_diff.py",
     '            "attributable_to_the_flip": bool(\n'
     '                fl[c]["n_moved"] > max(counts) and fl[c]["max_abs"] > max(max(mags), ATOL)),',
     '            "attributable_to_the_flip": bool(\n'
     '                fl[c]["n_moved"] > counts[0] and fl[c]["max_abs"] > max(mags[0], ATOL)),',
     'fl[c]["n_moved"] > max(counts)', SUITE_RUNNERS,
     "TestTheRookieBandControlIsAnEnvelope::"
     "test_a_move_INSIDE_the_control_envelope_is_NOT_attributed"),

    ("the envelope can never fire — attribution is hardwired off",
     _F / "run_nf_inj3b_ship_flipped_diff.py",
     '            "attributable_to_the_flip": bool(\n'
     '                fl[c]["n_moved"] > max(counts) and fl[c]["max_abs"] > max(max(mags), ATOL)),',
     '            "attributable_to_the_flip": False,',
     'fl[c]["n_moved"] > max(counts)', SUITE_RUNNERS,
     "TestTheRookieBandControlIsAnEnvelope::test_a_move_OUTSIDE_the_envelope_IS_attributed"),

    ("the flagged cohort is truncated to a top-N slice", FLIPPED_DIFF,
     '    return m.sort_values("d_proj_fp_ppr")[',
     '    return m.sort_values("d_proj_fp_ppr").head(5)[',
     None, SUITE_RUNNERS,
     "TestTheOperatorPacketLegs::"
     "test_the_flagged_cohort_is_EVERY_served_row_not_a_top_N_slice"),

    ("the coherence delta stops attributing the newly-violating rows", FLIPPED_DIFF,
     '    out["newly_violating_not_flagged"] = sorted(\n'
     '        n for i, n in seen.items() if i in new_ids and i not in flagged_ids)',
     '    pass',
     'out["newly_violating_not_flagged"]', SUITE_RUNNERS,
     "TestTheOperatorPacketLegs::"
     "test_the_coherence_delta_reports_BOTH_boards_and_attributes_the_new_rows"),

    ("the flipped diff stops refusing to run with the policy OFF (a vacuous measurement)",
     _F / "run_nf_inj3b_ship_flipped_diff.py",
     "    if not POLICY.serving_enabled():\n        raise RuntimeError(",
     "    if False:\n        raise RuntimeError(",
     "if not POLICY.serving_enabled():\n        raise RuntimeError(", SUITE_RUNNERS,
     "TestNeitherRunnerPublishes::test_the_flipped_diff_REFUSES_to_run_with_the_policy_OFF"),

    ("the flipped board is built with the policy FORCED, i.e. it re-measures NF-INJ3b-M",
     _F / "run_nf_inj3b_ship_flipped_diff.py",
     "    cap: dict = {}\n    board = NF15.build_season_projection(",
     "    cap: dict = {}\n    serving_on = True\n    board = NF15.build_season_projection(",
     None, SUITE_RUNNERS,
     "TestTheFlippedBoardIsTheCommittedOne::test_it_forces_nothing_and_supplies_no_feed"),

    ("the material comparison becomes BITWISE in the runner",
     _F / "run_nf_inj3b_ship_flipped_diff.py",
     "RTOL = ATOL = 1e-9", "RTOL = ATOL = 0.0", "RTOL = ATOL = 1e-9", SUITE_RUNNERS,
     "TestTheComparisonIsMaterialAndScoped::"
     "test_material_treats_a_sub_tolerance_move_as_unchanged"),

    ("the combined read is pointed at S3 (the board already published, not the candidate)",
     _F / "run_nf_inj3b_ship_combined_read.py",
     "    return PR.run(staged, origin=None)",
     "    import tempfile, pathlib as _pl\n"
     "    return PR.run(PR._fetch(_pl.Path(tempfile.mkdtemp())), origin=PR._S3)",
     "return PR.run(staged, origin=None)", SUITE_RUNNERS,
     "TestTheCombinedReadBindsToABoard::test_it_reads_a_STAGED_directory_not_S3"),

    ("the combined read stops recording the publish state it is valid FOR",
     _F / "run_nf_inj3b_ship_combined_read.py",
     '        "reported_absence_count": manifest.get("reportedAbsenceCount"),',
     "",
     '"reported_absence_count": manifest.get("reportedAbsenceCount"),', SUITE_RUNNERS,
     "TestTheCombinedReadBindsToABoard::"
     "test_it_records_the_publish_state_the_read_is_valid_FOR"),

    ("the combined read writes to NF1.9's DECIDED interval stem", 
     _F / "run_nf_inj3b_ship_combined_read.py",
     '_INTERVAL_STEM = "nf_inj3b_ship_combined_read_interval_revalidation"',
     '_INTERVAL_STEM = IV.DECIDED_STEM',
     '_INTERVAL_STEM = "nf_inj3b_ship', SUITE_RUNNERS,
     "TestTheCombinedReadBindsToABoard::test_it_writes_under_its_OWN_stem_never_a_decided_one"),

    ("a missing staged board is reported as a clean read instead of refused",
     _F / "run_nf_inj3b_ship_combined_read.py",
     '    if not (staged / "projections.json").exists():',
     "    if False:",
     'if not (staged / "projections.json").exists():', SUITE_RUNNERS,
     "TestTheCombinedReadBindsToABoard::"
     "test_a_missing_staged_board_RAISES_rather_than_reporting_a_pass"),

    # ══ THE FLIP AND ITS BOUNDARIES ═════════════════════════════════════════════════════════════
    ("the flip is silently reverted, contradicting the recorded operator ruling", POLICY,
     "SERVING_ENABLED: bool = True",
     "SERVING_ENABLED: bool = False",
     "SERVING_ENABLED: bool = True", SUITE_GUARD,
     "TestTheFlipIsON::test_the_committed_flag_matches_the_recorded_operator_ruling"),

    ("the certified population is widened to a status the study never scored", POLICY,
     'CERTIFIED_STATUSES: tuple[str, ...] = ("RES", "PUP")\n'
     'INCUMBENT_STATUSES: tuple[str, ...] = ("SUS", "NFI")',
     'CERTIFIED_STATUSES: tuple[str, ...] = ("RES", "PUP", "SUS")\n'
     'INCUMBENT_STATUSES: tuple[str, ...] = ("NFI",)',
     'CERTIFIED_STATUSES: tuple[str, ...] = ("RES", "PUP")\n', SUITE_GUARD,
     "TestTheFlipIsON::test_an_incumbent_held_status_does_NOT_move[SUS]"),

    ("the rookie frame is 'upgraded' to the certified VETERAN hurdle (NF-INJ3c's boundary)",
     SEASON,
     '        def _rookie_formal(_frame):\n'
     '            """The INCUMBENT constants cap — see boundary (1) above. ⛔ Not the policy router."""\n'
     '            return injury_availability_games(_frame, blend=injury_override_blend)',
     '        def _rookie_formal(_frame):\n'
     '            from quant_sports_intel_models.football.nfl.fantasy import (\n'
     '                injury_games_serving as _IGS_rk,\n'
     '            )\n'
     '            return _IGS_rk.served_injury_games(_frame, blend=injury_override_blend)[0]',
     "return injury_availability_games(_frame, blend=injury_override_blend)", SUITE_GUARD,
     "TestTheFlipIsON::test_the_rookie_frame_still_never_reaches_the_certified_veteran_hurdle"),

    ("a certified row with a NON-FINITE covariate is silently zero-filled by _design", SERVING,
     "    if not missing and _cert_for_check.any():",
     "    if False:",
     "if not missing and _cert_for_check.any():", SUITE_GUARD,
     "TestTheFlipIsON::test_a_certified_row_with_a_NON_FINITE_covariate_RAISES"),

    ("a flagged RETURNER is served the arm the study never scored him with", POLICY,
     "    if CERTIFIED_EXCLUDES_RETURNERS and \"seasons_missed\" in getattr(df, \"columns\", ()):",
     "    if False:",
     'if CERTIFIED_EXCLUDES_RETURNERS and "seasons_missed" in', SUITE_GUARD,
     "TestTheFlipIsON::test_a_flagged_RETURNER_keeps_the_incumbent_cap"),

    ("the returner boundary is restated in the server instead of read from the policy", SERVING,
     "    certified = POLICY.certified_rows(df)",
     "    certified = status.isin(POLICY.CERTIFIED_STATUSES).to_numpy()",
     "certified = POLICY.certified_rows(df)", SUITE_GUARD,
     "TestTheFlipIsON::test_the_returner_boundary_lives_in_the_POLICY_not_restated_in_the_server"),

    ("the refused arm becomes the served one without a fresh registration", POLICY,
     '    if ARM in REFUSED_ARMS:\n        raise RuntimeError(',
     '    if False:\n        raise RuntimeError(',
     "if ARM in REFUSED_ARMS:", SUITE_GUARD,
     "TestTheFlipIsON::test_the_refused_arm_stays_refused_AND_unreachable"),

    ("the PM boundary stops being applied, so every flagged status takes the fitted arm", SERVING,
     "        out = np.where(certified, predict_games(a, df), incumbent)",
     "        out = predict_games(a, df)",
     "np.where(certified, predict_games(a, df), incumbent)", SUITE_GUARD,
     "TestTheFlipIsON::test_an_incumbent_held_status_does_NOT_move[NFI]"),

    ("serving OFF stops returning the incumbent, so the rollback is a SECOND code path", SERVING,
     '    if not POLICY.serving_enabled():\n        _log_rows(None)\n        return incumbent, {"path": "incumbent"',
     '    if not POLICY.serving_enabled():\n        _log_rows(None)\n        return incumbent * 0.5, {"path": "incumbent"',
     'return incumbent, {"path": "incumbent"', SUITE_GUARD,
     "TestTheRollbackIsTheSameCodePath::"
     "test_serving_OFF_returns_the_incumbent_cap_byte_for_byte[RES]"),
]

_BACKUP_DIR = REPO / ".nf_inj3b_ship_red_proof_backup"


def _slug(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("/", "__")


def _restore_stale_backups() -> None:
    """A previous run killed mid-mutation leaves deliberately broken source on disk. Restore before
    doing anything else — E11.26's own worst case."""
    if not _BACKUP_DIR.exists():
        return
    for b in _BACKUP_DIR.iterdir():
        target = REPO / b.name.replace("__", "/")
        if target.exists():
            target.write_text(b.read_text())
            print(f"restored STALE backup: {target.relative_to(REPO)}")
    shutil.rmtree(_BACKUP_DIR, ignore_errors=True)


def run(suite: str, test_name: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", f"{suite}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=REPO, capture_output=True, text=True)
    return r.returncode, r.stdout[-600:]


def main() -> int:
    _restore_stale_backups()
    backups = {p: p.read_text() for p in FILES}
    _BACKUP_DIR.mkdir(exist_ok=True)
    for path, src in backups.items():
        (_BACKUP_DIR / _slug(path)).write_text(src)
    failures: list[str] = []
    suites = sorted({c[5] for c in CASES})
    try:
        r = subprocess.run(["uv", "run", "pytest", *suites, "-q", "--no-header",
                            "-p", "no:randomly"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for label, path, old, new, gone, suite, test in CASES:
            src = backups[path]
            # ⚠️ A MISSING ANCHOR IS A FAILURE, NOT A SKIP (E11.24 #682).
            if old not in src:
                failures.append(f"{label}: PATCH ANCHOR NOT FOUND in {path.name}")
                print(f"⚠️  ANCHOR MISSING  {label}  ({path.name})")
                continue
            # ⚠️ AND IT MUST BE UNIQUE, or `replace(..., 1)` may patch a different occurrence than
            # the one under test and report a sound guard as vacuous (the dangerous direction).
            if src.count(old) != 1:
                failures.append(f"{label}: ANCHOR IS NOT UNIQUE ({src.count(old)}x) in {path.name}")
                print(f"⚠️  ANCHOR AMBIGUOUS  {label}  ({path.name})")
                continue
            patched = src.replace(old, new, 1)
            assert patched != src, f"{label}: the replacement is a no-op"
            # ⚠️ AND IT MUST MOVE THE ASSERTED PREDICATE (E11.24 #815).
            if gone is not None and gone in patched:
                failures.append(f"{label}: the mutation left {gone!r} in place")
                print(f"⚠️  MUTATION DID NOT BITE  {label}")
                continue
            path.write_text(patched)
            code, out = run(suite, test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {label}  ->  {test}")
            if code == 0:
                failures.append(f"{label} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
        print("\nrestored all files")

    if failures:
        print(f"\n❌ {len(failures)} VACUOUS OR MIS-LANDED CLAUSE(S):\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(CASES)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
