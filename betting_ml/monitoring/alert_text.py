"""INC-42 — how to put an exception into a PAGE without discarding the diagnosis.

⚠️ ROOT CAUSE OF A 17-HOUR MISDIAGNOSIS (2026-08-11). `intraday_ops._schedule_lakehouse_intraday`
recorded each failed leg as `str(exc)[:300]` and paged with it. But that exception is raised by
`_run_script` as:

    Exception(f"{script} failed (exit {rc})\\n{result.stderr}")

i.e. it carries the child process's **entire traceback**, and a Python traceback puts its
diagnostic payload — the exception type and message — at the very **END**. So a HEAD truncation
keeps `Traceback (most recent call last):` plus the first stack frames and throws away the only
part that says what went wrong.

Measured on the INC-42 page: 300 chars bought the traceback header and the frame at
`_string_timestamp_wrap` L583, and **zero** characters of the DuckDB error. Worse, the
`_string_timestamp_wrap` RuntimeError leads with a 420-char boilerplate preamble whose
`Underlying DuckDB binder error:` marker sits at index 388 — so even truncating the RuntimeError
alone (not the traceback) yields 0 chars of real error and ends mid-sentence inside the generic
"Most common cause: a date function or interval arithmetic applied to a column…" hint. The page
therefore read as if a use-site cast WAS the diagnosis (the INC-40 "an alert's own suggested-cause
banner is diagnostic anchoring" lesson, in its most literal form), and every distinct failure
cause — a transient S3 404, a throttle, a genuine binder error — produced a **byte-identical**
page.

⭐ THE INVARIANT: a page must DISCRIMINATE between causes. A truncation that yields the same text
for every failure is the same defect class as the `curl -f`/301 healthcheck (an output that cannot
distinguish success from failure) — it is not a shorter diagnosis, it is no diagnosis.

CURE: keep the HEAD (which names the script and exit code) *and* the TAIL (which carries the
exception), and say so where the middle was dropped.
"""

from __future__ import annotations

# Enough tail to carry a DuckDB/Snowflake error plus the frame it was raised from, while staying
# well inside an email/SNS body. The head only needs to survive "<script> failed (exit N)".
DEFAULT_LIMIT = 900
DEFAULT_HEAD = 160
_ELISION = "\n  …[{n} chars elided — middle of the traceback]…\n"


def exc_digest(exc: object, *, limit: int = DEFAULT_LIMIT, head: int = DEFAULT_HEAD) -> str:
    """Summarise an exception for an alert body WITHOUT discarding its tail.

    Returns at most ~``limit`` characters: the first ``head`` (the script/exit-code line) and the
    last ``limit - head`` (the exception type + message), with an explicit marker naming how much
    was dropped. Short messages are returned verbatim.

    ⛔ Never replace this with ``str(exc)[:n]``. For any exception whose text is a traceback — which
    is every exception `_run_script` raises — a head slice is the least informative slice there is.
    """
    text = str(exc)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    # Reserve room for the elision marker so the result honours `limit`.
    marker_budget = len(_ELISION.format(n=len(text)))
    usable = max(limit - marker_budget, 1)
    head_n = max(min(head, usable // 2), 0)
    tail_n = max(usable - head_n, 1)
    elided = len(text) - head_n - tail_n
    if elided <= 0:
        return text
    return text[:head_n] + _ELISION.format(n=elided) + text[-tail_n:]
