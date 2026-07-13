"""test_serving_timestamp_coercion.py — the INC-23-class serving-blob timestamp bug.

THE BUG (observed live on 2026-07-04 and 2026-07-12): in `--s3` (DuckDB/lakehouse) read mode a
TIMESTAMP column comes back as a VARCHAR like '2026-07-12 17:35:00+00' (space separator, 2-digit
'+00' offset). `write_serving_store._ts()` passed that through verbatim (`str(val)`), so the
serving blob carried a NON-ISO timestamp. Pydantic's strict datetime parser REJECTS that form →
`EVPicksResponse(**blob)` raised → the /picks/ev router's try/except silently fell through to an
(empty) last-resort read → **the EV Tracker rendered completely blank for that whole date.**

A silent, whole-page data outage from one loose offset string. Both halves are guarded here:

  1. WRITER  — `_ts()` must parse-and-re-emit CANONICAL ISO for any loose string form, so newly
     written blobs are always strictly parseable.
  2. API     — the picks models must TOLERATE the loose form (`LooseDatetime`), so blobs ALREADY
     written with it still serve (no backfill required) and a future format drift can never
     silently blank a page again.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from app.backend.models.picks import (
    DataQuality,
    EVPicksResponse,
    Pick,
    TodayPicksResponse,
)

_REPO = Path(__file__).parents[2]

# The exact loose form the lakehouse emitted (and which pydantic used to reject).
LOOSE = "2026-07-12 17:35:00+00"
CANONICAL = "2026-07-12T17:35:00+00:00"


def _load_writer() -> ModuleType:
    """Import scripts/write_serving_store.py by path, ONCE (it is not an installed package).

    Heavy optional imports are stubbed so the load stays cheap in the fast gate — mirrors the
    existing loader in test_best_price_e9_11.py."""
    import unittest.mock as _mock

    for stub in ("snowflake.connector", "dotenv"):
        if stub not in sys.modules:
            sys.modules[stub] = _mock.MagicMock()
            if stub == "dotenv":
                sys.modules[stub].load_dotenv = lambda *a, **kw: None
    src = _REPO / "scripts" / "write_serving_store.py"
    spec = importlib.util.spec_from_file_location("write_serving_store_ts", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_TS = _load_writer()._ts  # module-level: pay the import once for the whole file


# ── 1. WRITER: _ts() emits canonical ISO ─────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (LOOSE, CANONICAL),                                     # the actual bug input
        ("2026-07-12 17:35:00", "2026-07-12T17:35:00"),         # space separator, no offset
        ("2026-07-12T17:35:00+00:00", CANONICAL),               # already canonical → unchanged
        (datetime(2026, 7, 12, 17, 35), "2026-07-12T17:35:00"),  # a real datetime still works
        (None, None),
    ],
)
def test_writer_ts_emits_canonical_iso(raw, expected):
    assert _TS(raw) == expected


def test_writer_ts_output_is_pydantic_parseable():
    """The whole point: whatever _ts emits MUST survive the model that reads the blob back."""
    blob = {
        "picks": [{"game_pk": 1, "market_type": "h2h", "game_start_utc": _TS(LOOSE)}],
        "total": 1,
    }
    resp = EVPicksResponse(**blob)  # must not raise
    assert resp.picks[0].game_start_utc == datetime.fromisoformat(CANONICAL)


def test_writer_ts_unparseable_value_degrades_not_raises():
    """A surprise format must not crash the write path — it falls back to the old passthrough."""
    assert _TS("not-a-timestamp") == "not-a-timestamp"


# ── 2. API: the models tolerate the loose form (heals already-written blobs) ──

def test_ev_response_accepts_loose_timestamp():
    """The regression: this blob shape used to raise and blank the EV Tracker for the date."""
    blob = {
        "picks": [
            {"game_pk": 822708, "market_type": "h2h", "game_start_utc": LOOSE,
             "game_date": "2026-07-12", "model_prob": 0.48},
        ],
        "total": 1,
    }
    resp = EVPicksResponse(**blob)
    assert len(resp.picks) == 1
    assert resp.picks[0].game_start_utc == datetime.fromisoformat(CANONICAL)


def test_today_response_accepts_loose_timestamps():
    blob = {
        "picks": [{"game_pk": 1, "market_type": "totals", "game_start_utc": LOOSE,
                   "predicted_at": LOOSE}],
        "data_quality": {"last_updated_at": LOOSE, "pipeline_status": "ok"},
    }
    resp = TodayPicksResponse(**blob)
    assert resp.picks[0].game_start_utc == datetime.fromisoformat(CANONICAL)
    assert resp.picks[0].predicted_at == datetime.fromisoformat(CANONICAL)
    assert resp.data_quality.last_updated_at == datetime.fromisoformat(CANONICAL)


def test_canonical_and_none_still_work():
    p = Pick(game_pk=1, market_type="h2h", game_start_utc=CANONICAL)
    assert p.game_start_utc == datetime.fromisoformat(CANONICAL)
    assert Pick(game_pk=1, market_type="h2h").game_start_utc is None
    assert DataQuality().last_updated_at is None


def test_genuinely_bad_timestamp_still_rejected():
    """Tolerance is for loose ISO forms only — real garbage must still fail loudly."""
    with pytest.raises(Exception):
        Pick(game_pk=1, market_type="h2h", game_start_utc="definitely-not-a-date")
