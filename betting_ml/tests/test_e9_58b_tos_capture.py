"""E9.58b — ToS acceptance must be CAPTURED, not hoped for.

WHY THIS FILE EXISTS. `POST /auth/accept-terms` was written for the first-login set-password
path, where every account had been created by hand by the operator and a lost write was a
blemish. It was fire-and-forget on BOTH sides: the client did `.catch(() => {})` and the router
did `except Exception: logger.warning(...)` and returned 204 regardless. So a failed write
reported SUCCESS to the caller.

E9.58 made Google self-serve signup public. That turned this record from telemetry into
EVIDENCE — the only thing that says a given account agreed to anything — while leaving the
delivery mechanism unchanged. An account could be created and used with no acceptance on file,
and no log line, alarm, or screen anywhere would say so.

The guarantee is now three parts, and each is pinned below because removing any one silently
restores the old behaviour:
  1. the server RAISES on a failed write (no more 204-on-failure)
  2. the client can READ the record back, so a missing one is detectable at all
  3. TermsGate BLOCKS a signed-in account that has none, and only clears on a successful write

⚠️ And the fourth property, which is the one most likely to be "simplified" away by a future
reader who thinks it is redundant: the gate FAILS OPEN when the backend does not report the
field. The API Lambda ships only via a manual deploy.sh while the frontend auto-deploys, so
there is always a window where this code runs against a backend that has never heard of
`tos_accepted_at`. Treating absent as "not accepted" would block every signed-in user until
someone ran deploy.sh — a full product outage caused by the guard itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path("frontend")
_BACKEND = Path("app/backend")

pytestmark = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")


def _code(path: Path) -> str:
    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


def _py(path: Path) -> str:
    """Python source with comments and docstrings stripped, so prose cannot satisfy a guard."""
    import ast

    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    return ast.unparse(tree)


# ── 1. the server must not report success for a write that failed ────────────────────────────────


def test_accept_terms_raises_instead_of_swallowing():
    src = _py(_BACKEND / "routers/auth.py")
    body = src.split("def accept_terms(")[1].split("\ndef ")[0]
    assert "raise HTTPException" in body, (
        "accept_terms swallows its exception again — a failed write returns 204 and the client "
        "reports success, which is exactly how an account ends up in use with no acceptance"
    )
    assert "record_tos_acceptance" in body


def test_the_write_never_overwrites_the_original_timestamp():
    """The FIRST acceptance is the legally interesting one; re-accepting must not move it."""
    src = _py(_BACKEND / "services/dynamo.py")
    body = src.split("def record_tos_acceptance(")[1].split("\ndef ")[0]
    assert "if_not_exists" in body


# ── 2. the record must be readable, or a missing one is undetectable ─────────────────────────────


def test_the_profile_endpoint_declares_the_acceptance_fields():
    """A field absent from the Pydantic response model is SILENTLY DROPPED on serialize.

    That is the E9.41 defect verbatim: DynamoDB holds the value, the API omits it, and the
    client concludes the account has no record — here that would mean blocking a user who HAS
    accepted, which is the false-positive direction of the same bug.
    """
    src = _py(_BACKEND / "routers/users.py")
    model = src.split("class UserProfile(")[1].split("class ")[0]
    assert "tos_accepted_at" in model and "tos_version" in model


def test_the_store_read_returns_the_acceptance_fields():
    src = _py(_BACKEND / "services/dynamo.py")
    body = src.split("def get_user_profile(")[1].split("\ndef ")[0]
    assert "tos_accepted_at" in body


def test_the_response_change_is_additive():
    """NF-C0: the API Lambda ships only via deploy.sh, so an OLDER client will read this
    response. Adding keys is safe; removing or renaming `initial_deposit` is not."""
    src = _py(_BACKEND / "routers/users.py")
    assert "initial_deposit" in src.split("class UserProfile(")[1].split("class ")[0]


# ── 3. the gate blocks, and only a successful write clears it ────────────────────────────────────


def test_every_authed_surface_is_behind_the_gate():
    """⚠️ Asserts the RENDERED element, not the bare name.

    The first version of this test checked `"TermsGate" in guard`, which the `import` line
    satisfies on its own — deleting the actual usage left the test GREEN. Caught only by
    running the deliberate break. Same family as a test that reads a value back under the key
    the code wrote: it restated that the symbol was mentioned, not that it was used.
    """
    guard = _code(_FRONTEND / "components/auth-guard.tsx")
    body = guard.split("export function AuthGuard")[1].split("export function ")[0]
    assert "<TermsGate>" in body and "</TermsGate>" in body, (
        "AuthGuard no longer RENDERS the terms gate around its children"
    )


def test_the_modal_cannot_be_dismissed_without_accepting():
    gate = _code(_FRONTEND / "components/terms-gate.tsx")
    for forbidden in ("onClose", "onOpenChange", "Escape"):
        assert forbidden not in gate, (
            f"{forbidden} suggests the blocking modal became dismissible — a gate the user can "
            "close is a prompt, and a prompt is what we already had"
        )
    assert "acceptTerms(" in gate


def test_the_gate_clears_on_the_backends_word_not_our_own():
    """Re-read after the write. Otherwise a 204 from a future half-broken endpoint clears it."""
    gate = _code(_FRONTEND / "components/terms-gate.tsx")
    accept = gate.split("async function handleAccept()")[1].split("\n  }")[0]
    assert "getTermsStatus(" in accept, "the gate clears without confirming the record landed"


def test_a_profile_read_error_does_not_lock_everyone_out():
    """An unreadable profile is not evidence of non-acceptance. If a Dynamo blip could satisfy
    the block condition, one 503 would lock every signed-in user out of the product."""
    gate = _code(_FRONTEND / "components/terms-gate.tsx")
    cond = gate.split("const mustAccept =")[1].split("\n\n")[0]
    assert "status.isSuccess" in cond, "the gate must require a SUCCESSFUL read before blocking"
    assert "isError" not in cond, "an errored read must never satisfy the block condition"


# ── 4. …but it must fail OPEN across a deploy skew ───────────────────────────────────────────────


def test_absent_is_not_the_same_as_null():
    """THE property most likely to be 'simplified' away, and the one that would hurt most.

    `tos_accepted_at` ABSENT means an old backend (deploy skew — frontend auto-deploys, the
    Lambda does not). `tos_accepted_at: null` means this account genuinely has no record.
    Collapsing the two blocks EVERY signed-in user until someone runs deploy.sh.
    """
    lib = _code(_FRONTEND / "lib/terms.ts")
    assert '"tos_accepted_at" in profile' in lib, (
        "lib/terms.ts no longer distinguishes an ABSENT field from a NULL one — a deploy skew "
        "would now lock every user out behind the terms gate"
    )
    assert "known: false" in lib


def test_the_gate_only_blocks_when_the_status_is_known():
    gate = _code(_FRONTEND / "components/terms-gate.tsx")
    cond = gate.split("const mustAccept =")[1].split("\n\n")[0]
    assert "status.data.known" in cond, "the gate blocks without knowing the backend reported it"


def test_signup_still_attempts_the_write_up_front():
    """The gate is the guarantee; the callback write is what makes it almost never fire."""
    callback = _code(_FRONTEND / "app/callback/page.tsx")
    assert "acceptTermsWithRetry" in callback


def test_the_guard_can_actually_fail():
    """Anti-vacuity: the source readers must actually be reading source."""
    assert "def accept_terms" in _py(_BACKEND / "routers/auth.py")
    assert len(_code(_FRONTEND / "components/terms-gate.tsx")) > 500
    # `_py` must really strip docstrings, or every assertion above could be satisfied by prose.
    assert "WHY THIS EXISTS" not in _py(_BACKEND / "routers/auth.py")


# ── the audit answers "who is already missing one" ───────────────────────────────────────────────


def test_the_audit_script_exists_and_is_nonzero_on_a_gap():
    src = Path("scripts/audit_tos_acceptance.py")
    assert src.is_file()
    body = _py(src)
    assert "list_users" in body and "tos_accepted_at" in body
    assert "return 1 if missing else 0" in body, (
        "the audit must exit non-zero when an account has no record, or it cannot gate a "
        "go-live checklist"
    )
