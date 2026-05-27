"""
artifact_store.py
-----------------
Transparent load/upload helpers for model artifacts stored in S3 or on the
local filesystem. All scripts should use these instead of calling
joblib.load() / pickle.load() directly on artifact paths.

S3 URIs use the form:  s3://baseball-betting-ml-artifacts/<key>
Local paths are resolved relative to the project root if not absolute.

Environment variables required for S3 access:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION  (e.g. us-east-1)
"""

from __future__ import annotations

import io
import pickle
from pathlib import Path
from typing import Any

import joblib

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split 's3://bucket/key/path' into ('bucket', 'key/path')."""
    assert uri.startswith("s3://"), f"Not an S3 URI: {uri}"
    without_scheme = uri[5:]
    bucket, _, key = without_scheme.partition("/")
    return bucket, key


def _s3_client():
    import boto3
    return boto3.client("s3")


def _resolve_local(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def load_artifact(path: str | Path) -> Any:
    """Load a .pkl artifact from an S3 URI or local path.

    Falls back to pickle.load() if joblib cannot read the file (handles
    artifacts saved with plain pickle.dump() as well as joblib.dump()).
    """
    path_str = str(path)

    if path_str.startswith("s3://"):
        bucket, key = _parse_s3_uri(path_str)
        buf = io.BytesIO()
        _s3_client().download_fileobj(bucket, key, buf)
        buf.seek(0)
        try:
            return joblib.load(buf)
        except Exception:
            buf.seek(0)
            return pickle.load(buf)

    local = _resolve_local(path_str)
    try:
        return joblib.load(local)
    except Exception:
        with open(local, "rb") as fh:
            return pickle.load(fh)


def upload_artifact(local_path: str | Path, s3_uri: str) -> None:
    """Upload a local artifact file to S3.

    Called by training scripts immediately after saving locally so the
    S3 copy stays in sync.  Silently skips if AWS credentials are absent.
    """
    import botocore.exceptions

    local = _resolve_local(local_path)
    if not local.exists():
        raise FileNotFoundError(f"Artifact not found for upload: {local}")

    bucket, key = _parse_s3_uri(s3_uri)
    try:
        with open(local, "rb") as fh:
            _s3_client().upload_fileobj(fh, bucket, key)
        print(f"  Uploaded → {s3_uri}")
    except botocore.exceptions.NoCredentialsError:
        print(f"  [WARN] AWS credentials not configured — skipping S3 upload of {local.name}")
