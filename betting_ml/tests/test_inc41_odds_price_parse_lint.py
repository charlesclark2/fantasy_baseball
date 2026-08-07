"""INC-41 (2026-08-06) — a raw-JSON odds price must be parsed as BIGINT and bounded.

WHAT HAPPENED. At 20:22:46Z MyBookie.ag posted an h2h moneyline price of ``-2147483648`` —
INT32_MIN, a vendor "no price / locked market" sentinel. ``stg_oddsapi_odds`` parsed it with
``::integer`` and took ``abs()`` of it. INT32_MIN has no positive INT32 representation, so DuckDB
raised ``OutOfRangeException: Overflow on abs(-2147483648)`` and aborted the whole
``run_w1_lakehouse.py --w3pre-only`` build.

WHY THAT COST A SLATE. ``--w3pre-only`` is the FIRST leg of the intraday chain in
``intraday_ops._schedule_lakehouse_intraday``; when it raised, ``--w7b-only`` never ran, so the
``stg_statsapi_lineups(_wide)`` parquet froze at 20:08Z. The lineup monitor reads that parquet
(via the SF ext view), so it reported "No newly confirmed lineups" for 6.5 hours and three games
never got a post_lineup prediction. The op's ``except`` is ALERT-continue, so the job reported
SUCCESS on every 30-minute tick. **One malformed vendor price, one whole evening.**

THE INVARIANT PINNED HERE. No dbt model may parse a raw-JSON odds price with a bare
``::integer``. Three distinct failure modes ride on that cast, all measured against the real
values from the 08-06 blob:

  * ``-2147483648`` → ``abs()`` **raises** (the outage)
  * ``9999999999``  → the ``::integer`` cast itself **raises** ConversionException
  * ``0``           → ``100.0/abs(0)`` yields literal **inf** as a decimal price
                      (``stg_oddsapi_odds`` had no zero-guard at all)

The cure is ``try_cast(... as bigint)`` plus a plausibility bound — American odds satisfy
|price| >= 100 by construction, so junk becomes NULL instead of a ~1.0000000005 decimal implying
~100% probability, which would poison de-vigging / CLV / best-price selection (the E9.52 lesson:
garbage that looks like data is worse than NULL).

Source-inspection only — no IO, so it belongs in the fast gate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

DBT_MODELS = Path(__file__).resolve().parents[2] / "dbt" / "models"

# A raw-JSON price extraction cast straight to INT32, in any quoting style.
_BARE_INT_PRICE = re.compile(
    r"""json_extract_string\(\s*\w+\s*,\s*['"]\$\.price['"]\s*\)\s*::\s*integer""",
    re.IGNORECASE,
)


def _sql_files() -> list[Path]:
    files = sorted(DBT_MODELS.rglob("*.sql"))
    assert files, f"no dbt models found under {DBT_MODELS}"
    return files


def _strip_sql_comments(sql: str) -> str:
    """Blank out ``--`` line comments and ``/* */`` blocks.

    Load-bearing: every fixed model now DOCUMENTS this defect, and those comments necessarily
    quote the banned ``...'$.price')::integer`` form. Without stripping, the lint would fire on
    the very code that satisfies it (the INC-38 prose-vs-argv lesson).
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def test_no_model_parses_a_raw_json_odds_price_as_int32():
    """RED-proves: restore any `json_extract_string(o, '$.price')::integer` and this fails."""
    offenders: list[str] = []
    for path in _sql_files():
        code = _strip_sql_comments(path.read_text())
        for m in _BARE_INT_PRICE.finditer(code):
            line = code[: m.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(DBT_MODELS)}:{line}")
    assert not offenders, (
        "raw-JSON odds price parsed as INT32 (INC-41). A vendor INT32_MIN sentinel makes abs() "
        "overflow and aborts the whole W3pre build; an out-of-INT32 price raises on the cast "
        "itself. Use try_cast(... as bigint) plus an |price| BETWEEN 100 AND 1000000 bound, then "
        f"cast back to ::integer to keep the stored type. Offenders: {offenders}"
    )


def test_the_comment_stripper_cannot_hide_a_real_offender():
    """Prose must not be able to SATISFY the lint (over-eager stripper) or BREAK it (under-eager).

    Without this, the lint above could be passing only because the stripper blanks real code.
    """
    real = "select json_extract_string(o, '$.price')::integer as p\n"
    commented = "-- json_extract_string(o, '$.price')::integer is banned\nselect 1\n"
    assert _BARE_INT_PRICE.search(_strip_sql_comments(real)), "stripper ate REAL code → false pass"
    assert not _BARE_INT_PRICE.search(_strip_sql_comments(commented)), "comment read as code → false fail"


@pytest.mark.parametrize(
    "price,expect_american,expect_decimal",
    [
        ("-2147483648", None, None),   # the outage value — INT32_MIN vendor sentinel
        ("9999999999", None, None),    # beyond INT32: the bare cast used to raise
        ("0", None, None),             # used to yield inf (stg_oddsapi_odds had no zero-guard)
        ("-99", None, None),           # impossible American odds (|price| >= 100)
        ("-110", -110, 1.9090909090909092),
        ("100", 100, 2.0),
        ("-6000", -6000, 1.0166666666666666),   # real value from the same 08-06 blob
        ("3600", 3600, 37.0),                    # real value from the same 08-06 blob
        ("-100000", -100000, 1.001),             # real, extreme-but-legitimate — must SURVIVE
    ],
)
def test_the_bounded_bigint_expression_behaves(price, expect_american, expect_decimal):
    """Execute the SHIPPED expression in DuckDB against the real 08-06 values.

    A source-inspection lint proves nobody wrote the bad form; it cannot prove the replacement is
    correct. This runs the actual SQL. The legitimate extremes (-6000 / 3600 / -100000, all real
    prices from the incident blob) must come through UNCHANGED — a bound that also discards good
    data would be a silent downgrade, not a fix.
    """
    duckdb = pytest.importorskip("duckdb")
    american = (
        "case when abs(try_cast(p as bigint)) between 100 and 1000000 "
        "then try_cast(p as bigint)::integer end"
    )
    decimal = (
        "case when abs(try_cast(p as bigint)) not between 100 and 1000000 then null "
        "when try_cast(p as bigint) >= 100 then (try_cast(p as bigint) / 100.0) + 1.0 "
        "else (100.0 / abs(try_cast(p as bigint))) + 1.0 end::double"
    )
    con = duckdb.connect()
    got_a, got_d = con.execute(
        f"select {american}, {decimal} from (select '{price}' as p)"
    ).fetchone()
    assert got_a == expect_american
    if expect_decimal is None:
        assert got_d is None
    else:
        assert got_d == pytest.approx(expect_decimal)


def test_the_old_expression_really_did_raise_on_the_incident_value():
    """Anchor the regression: prove the PRE-FIX form fails on the exact production value.

    Without this the suite could drift to a cure for a defect that never existed as described.
    """
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    old = (
        "case when p::integer >= 100 then (p::integer / 100.0) + 1.0 "
        "else (100.0 / abs(p::integer)) + 1.0 end"
    )
    with pytest.raises(Exception) as exc:
        con.execute(f"select {old} from (select '-2147483648' as p)").fetchone()
    assert "abs" in str(exc.value).lower() or "range" in str(exc.value).lower()


# ── the not_null contract must be upheld by a FILTER, not by hope ───────────────────
# My post-repair verification counted out-of-band prices and inf decimals, reported clean, and
# never counted NULLs against the `not_null` test on outcome_price_american — so a live
# data-quality gate was already violated while I was calling the data healthy. The dbt Build job
# caught it. This pins the structural property that check missed.
_BOUND_IN_WHERE = re.compile(
    r"where\s+abs\(\s*try_cast\(\s*json_extract_string\([^)]*'\$\.price'\s*\)\s*as\s+bigint\s*\)\s*\)"
    r"\s*between\s+100\s+and\s+1000000",
    re.IGNORECASE,
)

_NOT_NULL_PRICE_MODELS = ("stg_oddsapi_odds", "stg_derivative_odds")


def test_a_w3pre_only_build_has_a_matching_targeted_ext_table_refresh():
    """`run_w1_lakehouse.py --w3pre-only` must have a paired `refresh_w1_external_tables --w3pre`.

    Found while writing the INC-41 repair steps: every other build tier (w6-odds, w8a, w8b, w11b/c/d,
    w11tx, w9, sub-model-signals) had a targeted refresh flag; W3pre had none, so the ONLY way to
    refresh it was the full no-flag daily path. That matters specifically for W3pre because it is
    CUT OVER — the dbt else branches are `select * from lakehouse_ext.stg_*` and stg_oddsapi_odds
    feeds mart_odds_outcomes, read at request time by predict_today / write_serving_store. So an
    operator who rebuilds just this tier (exactly the INC-41 repair) has no narrow correct command,
    and the tempting fallback — rebuild the parquet and skip the refresh — leaves Snowflake serving
    the OLD file with no error at all (AUTO_REFRESH=FALSE).

    Kept deliberately narrow: most build tiers legitimately refresh only via the daily path, so a
    blanket "every --X-only needs a --X" lint would be noise reverse-engineered to this one answer.

    RED-proves: delete the `--w3pre` argument or its branch and this fails.
    """
    src = (Path(__file__).resolve().parents[2]
           / "scripts" / "refresh_w1_external_tables.py").read_text()
    assert 'add_argument("--w3pre"' in src, "refresh_w1_external_tables.py must expose --w3pre"
    # The branch must actually refresh the W3pre tier, and as REQUIRED — a best-effort skip here
    # is indistinguishable from success while serving stale prices.
    assert re.search(
        r"if\s+args\.w3pre\s*:.*?_refresh\(\s*W3PRE_TABLES\s*,\s*required\s*=\s*set\(\s*W3PRE_TABLES\s*\)\s*\)",
        src,
        re.DOTALL,
    ), "--w3pre must _refresh(W3PRE_TABLES, required=set(W3PRE_TABLES))"
    # …and the tier must still contain the model whose staleness caused the incident.
    w3pre_const = src[src.index("W3PRE_TABLES = ["):]
    assert "stg_oddsapi_odds" in w3pre_const[: w3pre_const.index("]")]


@pytest.mark.parametrize("model", _NOT_NULL_PRICE_MODELS)
def test_an_unusable_price_excludes_the_row_rather_than_nulling_it(model):
    """`outcome_price_american` carries a not_null test, so the model must FILTER, not NULL.

    Nulling in place is the tempting fix and it silently breaks the gate — 1 NULL row out of
    6.1M was enough to fail dbt Build, which is exactly the gate doing its job. The documented
    contract (mart_odds_outcomes column docs) is that a row without a usable price is excluded at
    the staging layer.

    RED-proves: delete the WHERE bound from either model and this fails.
    """
    path = next(DBT_MODELS.rglob(f"{model}.sql"), None)
    assert path is not None, f"{model}.sql not found"
    code = _strip_sql_comments(path.read_text())
    assert _BOUND_IN_WHERE.search(code), (
        f"{model} must EXCLUDE a row whose price is not a usable American odd (a WHERE bound), "
        "not carry it with a NULL price — outcome_price_american has a not_null test at this "
        "layer AND in mart_odds_outcomes, which selects it straight through."
    )
