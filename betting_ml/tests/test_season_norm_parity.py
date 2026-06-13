"""Story 27.7 drift guard: the contact-quality column list must be identical on the
Python side (betting_ml/utils/season_normalization.py) and the dbt side
(contact_quality_columns() in dbt/macros/season_normalize_contact.sql).

If these diverge, training would season-normalize a different set than the dbt mart
emits `_seasonnorm` columns for → a silent train/serve skew. Keep them byte-for-byte.
"""

from __future__ import annotations

import re
from pathlib import Path

from betting_ml.utils.season_normalization import CONTACT_QUALITY_COLUMNS

_MACRO = Path(__file__).resolve().parents[2] / "dbt" / "macros" / "season_normalize_contact.sql"


def _dbt_macro_columns() -> list[str]:
    src = _MACRO.read_text()
    block = re.search(r"contact_quality_columns\(\).*?return\(\[(.*?)\]\)", src, re.S)
    assert block, "contact_quality_columns() return([...]) block not found in macro"
    return re.findall(r"'([a-z0-9_]+)'", block.group(1))


def test_python_and_dbt_contact_lists_match_exactly():
    dbt_cols = _dbt_macro_columns()
    assert CONTACT_QUALITY_COLUMNS == dbt_cols, (
        "Python/dbt contact-quality column lists diverged.\n"
        f"  only in python: {set(CONTACT_QUALITY_COLUMNS) - set(dbt_cols)}\n"
        f"  only in dbt:    {set(dbt_cols) - set(CONTACT_QUALITY_COLUMNS)}\n"
        "  (or the ORDER differs)"
    )


def test_no_duplicate_contact_columns():
    assert len(CONTACT_QUALITY_COLUMNS) == len(set(CONTACT_QUALITY_COLUMNS))
