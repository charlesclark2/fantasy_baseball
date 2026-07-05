"""
test_snowflake_resolver_lint.py  (INC-22 straggler cure — fast gate)
====================================================================
The recurring box-runtime HALT: a script under scripts/ defines its OWN Snowflake resolver that
reads a key FILE (SNOWFLAKE_PRIVATE_KEY_PATH) and/or falls back to SNOWFLAKE_PASSWORD, but does NOT
support the INLINE key. On the EC2 box the key is an INLINE env var (SNOWFLAKE_PRIVATE_KEY) and
SNOWFLAKE_PASSWORD is UNSET → the script crashes at runtime (KeyError on subscript, or an
"either PATH or PASSWORD must be set" EnvironmentError even though the inline key is present). CI
can't catch it (CI mocks Snowflake). This bit the export_*_to_s3 + posterior/ingest stragglers
during INC-27/INC-28 (2026-07-05). See CLAUDE.md "Snowflake auth on the box = INLINE key" / INC-22.

INVARIANT (this guard): any scripts/*.py that does its OWN Snowflake auth — i.e. references the
string ``SNOWFLAKE_PRIVATE_KEY_PATH`` or ``SNOWFLAKE_PASSWORD`` in executable code — MUST either
(a) also reference the INLINE key ``SNOWFLAKE_PRIVATE_KEY`` (a multi-tier PATH→inline→password
resolver), or (b) delegate to the shared resolver ``betting_ml.utils.data_loader.get_snowflake_connection``
(which is inline-key-safe). Otherwise it is a box-crash landmine and this test FAILS.

AST-based (string constants only, docstrings excluded), so comments/docstrings that merely DESCRIBE
the footgun don't trip it. No import of the scripts — pure source scan → runs in the fast gate.
"""
import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
# Top-level scripts only (the straggler surface). scripts/ops, scripts/utils, scripts/ddl are
# separate namespaces addressed elsewhere; keep this guard's scope to what INC-22 swept.
SCRIPTS = sorted(p for p in (REPO / "scripts").glob("*.py") if p.name != "__init__.py")

_OWN_AUTH = {"SNOWFLAKE_PRIVATE_KEY_PATH", "SNOWFLAKE_PASSWORD"}
_INLINE = "SNOWFLAKE_PRIVATE_KEY"  # the inline key env var (NOT the _PATH variant)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id()s of Constant nodes that are docstrings (first stmt of a module/func/class body)."""
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            out.add(id(body[0].value))
    return out


def _string_constants(tree: ast.AST) -> set[str]:
    """All string-constant VALUES in executable positions (docstrings excluded)."""
    docs = _docstring_nodes(tree)
    vals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            vals.add(node.value)
    return vals


def _delegates_to_shared(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("data_loader"):
            if any(a.name == "get_snowflake_connection" for a in node.names):
                return True
    return False


def _rolls_own_pem_parse(tree: ast.AST) -> bool:
    """True if the script calls ``serialization.load_pem_private_key`` itself — i.e. it
    hand-rolls the inline-key → DER conversion instead of using the shared resolver. This is
    the EXACT gap that let ``settle_user_bets.py`` slip the guard during INC-27/INC-28: it
    referenced the inline key ``SNOWFLAKE_PRIVATE_KEY`` (so ``inline_ok`` was True) but its own
    parser did NOT unescape the box's ``\\n``-escaped value → ``InvalidByte(0, 92)`` at runtime.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "load_pem_private_key":
            return True
        if isinstance(node, ast.Name) and node.id == "load_pem_private_key":
            return True
    return False


def _unescapes_inline_key(tree: ast.AST) -> bool:
    r"""True if the script's own inline-key parser unescapes ``\n`` (``key_val.replace("\\n", "\n")``,
    the box authenticates with a ``\n``-escaped single-line SNOWFLAKE_PRIVATE_KEY). This is what
    the blessed shared resolver does (data_loader ``_load_private_key``) and what settle_user_bets
    was MISSING. A hand-rolled PEM parser is inline-safe iff it either delegates OR unescapes.
    """
    for node in ast.walk(tree):
        # match a string constant containing a backslash-n escape (the "\\n" search literal)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "\\n" in node.value:
            return True
    return False


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_snowflake_resolver_is_inline_safe(path):
    tree = ast.parse(path.read_text())
    consts = _string_constants(tree)
    does_own_auth = bool(_OWN_AUTH & consts)
    rolls_own_pem = _rolls_own_pem_parse(tree)
    if not does_own_auth and not rolls_own_pem:
        return  # no hand-rolled Snowflake auth / key parsing → nothing to check
    inline_ok = _INLINE in consts
    delegates = _delegates_to_shared(tree)

    # A script that parses the PEM itself is inline-safe iff it DELEGATES to the shared resolver
    # OR unescapes the box's \n-escaped inline key — mentioning SNOWFLAKE_PRIVATE_KEY is NOT
    # enough (that's exactly how settle_user_bets.py passed while its parser silently broke).
    if rolls_own_pem:
        assert delegates or _unescapes_inline_key(tree), (
            f"{path.name} calls serialization.load_pem_private_key itself (hand-rolled inline-key "
            f"parsing) but neither delegates to betting_ml.utils.data_loader.get_snowflake_connection "
            f"NOR unescapes the box's \\n-escaped SNOWFLAKE_PRIVATE_KEY (key_val.replace('\\\\n','\\n')). "
            f"This is the INC-28 straggler class that crashes on the EC2 box at runtime "
            f"(InvalidByte(0, 92)). Delegate to the shared resolver (preferred) or unescape. "
            f"See CLAUDE.md INC-22."
        )
        return

    assert inline_ok or delegates, (
        f"{path.name} does its own Snowflake auth (references {sorted(_OWN_AUTH & consts)}) but "
        f"neither supports the INLINE key '{_INLINE}' nor delegates to "
        f"betting_ml.utils.data_loader.get_snowflake_connection — it will CRASH on the EC2 box "
        f"(no SNOWFLAKE_PASSWORD / no key file). Repoint it at the shared resolver (INC-22)."
    )
