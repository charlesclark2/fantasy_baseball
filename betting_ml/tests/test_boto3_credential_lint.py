"""
test_boto3_credential_lint.py  (W7b-1 AKID footgun guard — fast gate)
====================================================================
On the EC2 host S3 auth comes from the instance IAM ROLE, so AWS_ACCESS_KEY_ID is
UNSET. Constructing a boto3 client with `aws_access_key_id=os.environ.get(...)` passes
None, which DISABLES boto3's default credential chain → `AuthorizationHeaderMalformed:
a non-empty Access Key (AKID) must be provided`. This bit all 7 S3 exporters at once
(2026-06-29, first W7B_LAKEHOUSE_PARALLEL day). See CLAUDE.md "BOTO3 S3 WRITERS".

This lint FAILS the build if the instance-role-killing pattern is reintroduced anywhere:
any call passing `aws_access_key_id=` (or `aws_secret_access_key=`) a value of
`os.environ.get(...)` / `os.getenv(...)` (i.e. possibly-None). The safe pattern —
build a kwargs dict and add the key only `if akid and secret` — is NOT flagged, nor is
the shared helper `scripts/utils/lakehouse_raw_writer.make_s3_client()`.

AST-based (not string-in-source — see feedback "AST checks for import guards"), so
comments/docstrings that merely DESCRIBE the footgun (like this one) don't trip it.
"""
import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
# Roots that construct boto3 S3/DynamoDB clients (writers + ops + backend).
SCAN_ROOTS = ["scripts", "pipeline", "app", "betting_ml"]
_CRED_KWARGS = {"aws_access_key_id", "aws_secret_access_key", "aws_session_token"}


def _is_possibly_none_env(node: ast.AST) -> bool:
    """True if `node` is os.environ.get(...) / os.getenv(...) / environ.get(...) /
    getenv(...) — all of which return None when the var is absent."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    # os.environ.get(...)  /  environ.get(...)
    if isinstance(f, ast.Attribute) and f.attr == "get":
        base = f.value
        if isinstance(base, ast.Attribute) and base.attr == "environ":
            return True
        if isinstance(base, ast.Name) and base.id == "environ":
            return True
    # os.getenv(...)  /  getenv(...)
    if isinstance(f, ast.Attribute) and f.attr == "getenv":
        return True
    if isinstance(f, ast.Name) and f.id == "getenv":
        return True
    return False


def find_violations(src: str, path: str) -> list[str]:
    """Return 'path:line  aws_access_key_id=os.environ.get(...)' for each offending call."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []  # unparseable file is some other test's problem, not this lint's
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in _CRED_KWARGS and _is_possibly_none_env(kw.value):
                out.append(f"{path}:{kw.value.lineno}  {kw.arg}=<os.environ.get/getenv (possibly None)>")
    return out


def _scan_repo() -> list[str]:
    violations = []
    for root in SCAN_ROOTS:
        for py in (REPO / root).rglob("*.py"):
            if any(part in {".venv", "node_modules", "__pycache__", "build", "dist"} for part in py.parts):
                continue
            violations.extend(find_violations(py.read_text(encoding="utf-8", errors="ignore"),
                                              str(py.relative_to(REPO))))
    return violations


def test_no_instance_role_killing_boto3_construction():
    violations = _scan_repo()
    assert not violations, (
        "boto3 client/Session constructed with a possibly-None credential from "
        "os.environ.get/getenv — this DISABLES the EC2 instance-role chain "
        "(AuthorizationHeaderMalformed). Build a kwargs dict and add the key only "
        "`if akid and secret`, or use lakehouse_raw_writer.make_s3_client():\n  "
        + "\n  ".join(violations)
    )


def test_lint_positive_control():
    """Proof the lint FLAGS the footgun."""
    bad = "import boto3, os\nboto3.client('s3', aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'))\n"
    assert find_violations(bad, "bad.py"), "lint must flag aws_access_key_id=os.environ.get(...)"
    bad2 = "import boto3, os\nboto3.Session(aws_access_key_id=os.getenv('K'), aws_secret_access_key=os.getenv('S'))\n"
    assert len(find_violations(bad2, "bad2.py")) == 2


def test_lint_allows_safe_patterns():
    """The conditional-kwargs pattern and required-env (os.environ[...]) are NOT flagged."""
    safe = (
        "import boto3, os\n"
        "kwargs = {}\n"
        "akid, secret = os.environ.get('AWS_ACCESS_KEY_ID'), os.environ.get('AWS_SECRET_ACCESS_KEY')\n"
        "if akid and secret:\n"
        "    kwargs['aws_access_key_id'] = akid\n"
        "    kwargs['aws_secret_access_key'] = secret\n"
        "boto3.client('s3', **kwargs)\n"
    )
    assert find_violations(safe, "safe.py") == []
    # os.environ['X'] RAISES if absent (not None) — a deliberate required-cred choice, not the footgun
    required = "import boto3, os\nboto3.client('s3', aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'])\n"
    assert find_violations(required, "required.py") == []
