"""E11.20 phase 1.5 — the W1 straggler repoint stays wired (source inspection; no
pipeline import — the fast gate has no dbt manifest).

WHY: the SF `betting.mart_pitch_*` views drop in the phase-1.5 decommission. Every
raw-SQL consumer found by the INC-27 grep must carry an --s3 lakehouse path, and the two
SCHEDULED consumers must actually receive the flag from their Dagster ops — a repoint
that exists in the script but is never passed by the op is exactly how INC-31's
"gated-off native build" class ships. If a test here fails, either the flag wiring
regressed or a NEW raw-SQL mart_pitch consumer appeared (add its repoint + list it here).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

OPS = (REPO / "pipeline" / "ops" / "daily_ingestion_ops.py").read_text()

# Every Python consumer of betting.mart_pitch_* (the INC-27 grep set) → its flag.
REPOINTED_SCRIPTS = {
    "betting_ml/scripts/sequential_bayes/update_player_posteriors.py": "--s3",
    "betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py": "--s3",
    "betting_ml/scripts/eb_priors/generate_matchup_signals.py": "--s3",
    "betting_ml/scripts/eb_priors/build_matchup_training_data.py": "--s3",
    "betting_ml/scripts/eb_priors/compute_bullpen_posteriors.py": "--s3",
    "betting_ml/scripts/eb_priors/compute_bullpen_v3.py": "--s3",
    "betting_ml/scripts/eb_priors/fit_bullpen_priors.py": "--s3",
    "betting_ml/scripts/pitcher_clustering/cluster_stability_analysis.py": "--s3",
    "scripts/ingest_player_profiles.py": "--s3",
}


def test_every_mart_pitch_consumer_has_an_s3_flag():
    for rel, flag in REPOINTED_SCRIPTS.items():
        src = (REPO / rel).read_text()
        assert "mart_pitch" in src, f"{rel}: no longer reads mart_pitch — remove from this list"
        assert f'"{flag}"' in src, (
            f"{rel}: reads betting.mart_pitch_* but has no {flag} lakehouse path — "
            f"it breaks the moment the SF views drop (phase 1.5)."
        )


def test_scheduled_consumer_ops_pass_the_w7a_flag():
    """The two consumers with Dagster schedules must RECEIVE the flag from their op —
    daily update_player_posteriors_op and weekly ingest_player_profiles_update."""
    for op_name in ("update_player_posteriors_op", "ingest_player_profiles_update"):
        m = re.search(rf"def {op_name}\(context\):(.*?)(?=\n@op|\n# ─|\Z)", OPS, re.S)
        assert m, f"op {op_name} not found in daily_ingestion_ops.py"
        assert "_w7a_s3_args()" in m.group(1), (
            f"{op_name} no longer passes _w7a_s3_args() — under W7A_LAKEHOUSE_S3=1 the "
            f"script would silently keep reading the (soon-dropped) SF mart_pitch views."
        )


def test_no_new_unrepointed_mart_pitch_consumer():
    """The INC-27 sweep, mechanized: any NEW .py file embedding
    `betting.mart_pitch_` as a raw SQL string must be added to REPOINTED_SCRIPTS
    (with an --s3 path) — the dbt DAG cannot see these consumers."""
    known = {str(REPO / rel) for rel in REPOINTED_SCRIPTS}
    # Scripts that WRITE/DDL/refresh the family or are the builder itself — not readers.
    exempt_parts = ("scripts/ddl/", "run_w1_lakehouse.py", "refresh_w1_external_tables.py",
                    "parity_check_delta_w1.py", "/tests/",
                    "train_matchup_v1.py",    # registry-metadata prose, not a read
                    "_lakehouse_duck.py")     # the rewrite map (the cure, not a consumer)
    offenders = []
    for py in list(REPO.glob("scripts/**/*.py")) + list(REPO.glob("betting_ml/**/*.py")) \
            + list(REPO.glob("pipeline/**/*.py")) + list(REPO.glob("app/backend/**/*.py")):
        p = str(py)
        if p in known or any(x in p for x in exempt_parts):
            continue
        try:
            text = py.read_text()
        except UnicodeDecodeError:
            continue
        if "betting.mart_pitch_" in text or "BETTING.MART_PITCH_" in text:
            offenders.append(p)
    assert not offenders, (
        f"NEW raw-SQL betting.mart_pitch_* consumer(s) with no registered repoint: "
        f"{offenders} — add an --s3 lakehouse path + list in REPOINTED_SCRIPTS "
        f"(the SF views drop in E11.20 phase 1.5)."
    )
