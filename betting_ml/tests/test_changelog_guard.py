"""E9.18 — CI guard: every 'week' key in changelog.json must be a Monday (weekday==0)
and no two blocks may fall in the same Mon–Sun week (accidental split → render merges).

Fails the fast gate on a bad week entry so a bad write can't merge without a fix.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

_CHANGELOG = Path(__file__).resolve().parents[2] / "frontend" / "data" / "changelog.json"


def _to_monday(d: datetime.date) -> datetime.date:
    return d - datetime.timedelta(days=d.weekday())


def test_changelog_week_keys_are_mondays_and_unique():
    data = json.loads(_CHANGELOG.read_text())
    errors: list[str] = []
    seen: dict[str, str] = {}  # monday_iso → the week value that claimed it

    for entry in data:
        week_str = entry["week"]
        try:
            d = datetime.date.fromisoformat(week_str)
        except ValueError:
            errors.append(f"week={week_str!r} is not a valid ISO date (YYYY-MM-DD)")
            continue

        if d.weekday() != 0:
            errors.append(
                f"week={week_str!r} is a {d.strftime('%A')}, not a Monday"
                " — set week to the MONDAY of the ship-date's week"
            )

        monday_iso = _to_monday(d).isoformat()
        if monday_iso in seen:
            errors.append(
                f"Duplicate Mon-week {monday_iso!r}: both week={seen[monday_iso]!r}"
                f" and week={week_str!r} fall in the same week — merge into one block"
            )
        else:
            seen[monday_iso] = week_str

    assert not errors, (
        "changelog.json week-key violations:\n"
        + "\n".join(f"  • {e}" for e in errors)
    )
