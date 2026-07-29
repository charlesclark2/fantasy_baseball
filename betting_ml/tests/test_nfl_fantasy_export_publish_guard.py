"""Fast-gate unit tests for the NF-D12 publish guard on the NFL fantasy draft-board exporter.

`export_draft_board_json.py` uploads to the LIVE prod api-cache (s3://credence-prod-s3-api-cache/
fantasy/nfl/<season>/) that the gated /fantasy/nfl/* endpoints serve. Before NF-D12 it uploaded
whenever a bucket resolved (--s3-bucket / $CACHE_BUCKET — always set in the operator's normal env),
so any re-export session pushed to prod with no deliberate act (NF-D11 did this unintentionally).

These tests exercise `_maybe_publish` directly (no S3/network — `_upload_to_s3` is monkeypatched to
a spy) to assert: the default path NEVER uploads even when a bucket resolves, `--publish` is the
only way to reach `_upload_to_s3`, and no bucket at all keeps the pre-existing local-only behaviour.
"""
from __future__ import annotations

import logging

import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as export_mod


@pytest.fixture
def staged_out_dir(tmp_path):
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "board_full_ppr_12.json").write_text("[]")
    return tmp_path


def _spy_upload(monkeypatch):
    calls: list[tuple] = []

    def _fake_upload(out_dir, bucket, season):
        calls.append((out_dir, bucket, season))

    monkeypatch.setattr(export_mod, "_upload_to_s3", _fake_upload)
    return calls


# ── the guard itself ──────────────────────────────────────────────────────────────────────────
def test_default_dry_run_never_uploads_even_with_a_resolved_bucket(staged_out_dir, monkeypatch):
    calls = _spy_upload(monkeypatch)
    export_mod._maybe_publish(staged_out_dir, "credence-prod-s3-api-cache", 2026, publish=False)
    assert calls == []


def test_publish_flag_reaches_the_live_upload(staged_out_dir, monkeypatch):
    calls = _spy_upload(monkeypatch)
    export_mod._maybe_publish(staged_out_dir, "credence-prod-s3-api-cache", 2026, publish=True)
    assert calls == [(staged_out_dir, "credence-prod-s3-api-cache", 2026)]


def test_no_bucket_never_uploads_regardless_of_publish(staged_out_dir, monkeypatch):
    calls = _spy_upload(monkeypatch)
    export_mod._maybe_publish(staged_out_dir, None, 2026, publish=True)
    assert calls == []


def test_dry_run_logs_what_would_upload(staged_out_dir, monkeypatch, caplog):
    _spy_upload(monkeypatch)
    with caplog.at_level(logging.INFO, logger=export_mod.log.name):
        export_mod._maybe_publish(staged_out_dir, "credence-prod-s3-api-cache", 2026, publish=False)
    msgs = " ".join(r.message for r in caplog.records)
    assert "DRY-RUN" in msgs
    assert "board_full_ppr_12.json" in msgs
    assert "manifest.json" in msgs
    assert "--publish" in msgs


def test_publish_logs_a_loud_banner(staged_out_dir, monkeypatch, caplog):
    _spy_upload(monkeypatch)
    with caplog.at_level(logging.WARNING, logger=export_mod.log.name):
        export_mod._maybe_publish(staged_out_dir, "credence-prod-s3-api-cache", 2026, publish=True)
    msgs = " ".join(r.message for r in caplog.records)
    assert "PUBLISHING TO LIVE PROD" in msgs


def test_no_bucket_warns_local_only(staged_out_dir, monkeypatch, caplog):
    _spy_upload(monkeypatch)
    with caplog.at_level(logging.WARNING, logger=export_mod.log.name):
        export_mod._maybe_publish(staged_out_dir, None, 2026, publish=False)
    msgs = " ".join(r.message for r in caplog.records)
    assert "staged locally only" in msgs


# ── the CLI flag wiring (the REAL parser main() uses, not a hand-rolled mirror) ─────────────────
def test_publish_flag_defaults_to_false_on_the_real_parser():
    ns = export_mod.build_arg_parser().parse_args(["--season", "2026"])
    assert ns.publish is False


def test_publish_flag_settable_on_the_real_parser():
    ns = export_mod.build_arg_parser().parse_args(["--season", "2026", "--publish"])
    assert ns.publish is True
