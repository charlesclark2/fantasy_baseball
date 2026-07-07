"""E9.9 / A0.6 — unit tests for the push-notification-sender Lambda.

Covers: honest-framing copy (no profit/bet-rec language + affirmative disclaimer),
per-channel fan-out routing, 410/404 endpoint pruning, per-recipient isolation, and
the "no qualified plays → send nothing" guard. boto3 / pywebpush are mocked.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_HANDLER_PATH = (
    Path(__file__).resolve().parents[2]
    / "services" / "notifications" / "push_sender" / "handler.py"
)

# Same banned-language set the E5.5 honest-framing guard uses.
_BANNED = [
    r"\+ev\b", r"\bev\b", r"value play", r"value bet", r"bet this", r"\bedge\b",
    r"win[\s\-]?rate", r"\bprofit\b", r"profitable", r"\bcash(able)?\b", r"\block\b",
    r"smash", r"hammer", r"guaranteed", r"sure thing", r"lay the", r"take the over",
]
_BANNED_RE = re.compile("|".join(_BANNED), re.IGNORECASE)


def _load():
    spec = importlib.util.spec_from_file_location("push_sender_handler", _HANDLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MSG = {
    "date": "2026-07-06",
    "n_qualified": 2,
    "plays": [
        {"matchup": "NYY @ BOS", "pick": "Over 8.5"},
        {"matchup": "LAD @ SF", "pick": "LAD ML"},
    ],
}


# ── Honest framing ──────────────────────────────────────────────────────────

def test_copy_has_no_bet_rec_language():
    mod = _load()
    subject, html, text = mod.build_email(_MSG)
    push = mod.build_push_payload(_MSG)
    sms = mod.build_sms(_MSG)
    blob = " ".join([subject, html, text, push["title"], push["body"], sms])
    hit = _BANNED_RE.search(blob)
    assert hit is None, f"banned profitability language in notification copy: {hit!r}"


def test_copy_is_model_relative_and_disclaims():
    mod = _load()
    _, _, text = mod.build_email(_MSG)
    assert "qualified" in text.lower()
    assert "not betting advice" in text.lower()
    assert "2 qualified plays" in text


def test_singular_plural():
    mod = _load()
    one = {"date": "2026-07-06", "n_qualified": 1, "plays": [{"matchup": "A @ B", "pick": "x"}]}
    assert "1 qualified play" in mod.build_sms(one)
    assert "qualified plays" in mod.build_sms(_MSG)


# ── Fan-out routing ─────────────────────────────────────────────────────────

def _table_scanning(items):
    table = MagicMock()
    table.scan.return_value = {"Items": items}
    return table


def test_fan_out_routes_by_channel(monkeypatch):
    mod = _load()
    sent = {"push": [], "email": [], "sms": []}
    monkeypatch.setattr(mod, "_send_web_push", lambda sub, p: sent["push"].append(sub["endpoint"]))
    monkeypatch.setattr(mod, "_send_email", lambda ses, to, s, h, t: sent["email"].append(to))
    monkeypatch.setattr(mod, "_send_sms", lambda sns, ph, t: sent["sms"].append(ph))

    items = [
        {  # push + email
            "user_id": "u1", "enabled": True, "push_enabled": True, "email_enabled": True,
            "email": "a@x.com", "push_subscription": {"endpoint": "https://push/1", "keys": {}},
        },
        {  # email only
            "user_id": "u2", "enabled": True, "email_enabled": True, "email": "b@x.com",
        },
        {  # sms only
            "user_id": "u3", "enabled": True, "sms_enabled": True, "phone_number": "+14155550123",
        },
    ]
    stats = mod.fan_out(_MSG, _table_scanning(items), MagicMock(), MagicMock())

    assert sent["push"] == ["https://push/1"]
    assert sorted(sent["email"]) == ["a@x.com", "b@x.com"]
    assert sent["sms"] == ["+14155550123"]
    assert stats["push"] == 1 and stats["email"] == 2 and stats["sms"] == 1


def test_410_endpoint_is_pruned(monkeypatch):
    mod = _load()

    def _gone(sub, p):
        raise mod.PushEndpointGone("410")

    monkeypatch.setattr(mod, "_send_web_push", _gone)
    monkeypatch.setattr(mod, "_send_email", lambda *a, **k: None)

    table = _table_scanning([
        {"user_id": "u1", "enabled": True, "push_enabled": True, "email": "a@x.com",
         "email_enabled": True, "push_subscription": {"endpoint": "https://push/dead", "keys": {}}},
    ])
    stats = mod.fan_out(_MSG, table, MagicMock(), MagicMock())

    assert stats["pruned"] == 1 and stats["push"] == 0
    table.update_item.assert_called_once()
    # email still delivered despite the dead push endpoint (per-recipient isolation)
    assert stats["email"] == 1


def test_one_bad_endpoint_does_not_block_batch(monkeypatch):
    mod = _load()
    calls = []

    def _email(ses, to, s, h, t):
        calls.append(to)
        if to == "boom@x.com":
            raise RuntimeError("SES throttled")

    monkeypatch.setattr(mod, "_send_email", _email)
    table = _table_scanning([
        {"user_id": "u1", "enabled": True, "email_enabled": True, "email": "boom@x.com"},
        {"user_id": "u2", "enabled": True, "email_enabled": True, "email": "ok@x.com"},
    ])
    stats = mod.fan_out(_MSG, table, MagicMock(), MagicMock())
    assert calls == ["boom@x.com", "ok@x.com"]  # continued past the failure
    assert stats["email"] == 1 and stats["errors"] == 1


def test_no_qualified_plays_sends_nothing(monkeypatch):
    mod = _load()
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock())
    monkeypatch.setattr("boto3.client", lambda *a, **k: MagicMock())
    out = mod.lambda_handler({"date": "2026-07-06", "n_qualified": 0, "plays": []}, None)
    assert out["sent"] == {}
