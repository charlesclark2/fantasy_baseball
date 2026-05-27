"""
migrate_artifacts_to_s3.py — One-time migration of all .pkl artifacts to S3.

Uploads every .pkl under betting_ml/models/ to
s3://baseball-betting-ml-artifacts/<sub-path> where <sub-path> is the path
relative to betting_ml/models/ (e.g. home_win/elasticnet_market_blind_2026.pkl).

Run once after creating the S3 bucket with the correct AWS credentials:
    uv run python scripts/migrate_artifacts_to_s3.py [--dry-run]

Required env vars:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION  (e.g. us-east-1)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")
_MODELS_DIR = _PROJECT_ROOT / "betting_ml" / "models"
_BUCKET = "baseball-betting-ml-artifacts"


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload all .pkl artifacts to S3.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be uploaded without actually uploading.")
    args = parser.parse_args()

    pkls = sorted(_MODELS_DIR.rglob("*.pkl"))
    if not pkls:
        print("No .pkl files found under betting_ml/models/. Nothing to upload.")
        sys.exit(0)

    print(f"Found {len(pkls)} .pkl files to upload to s3://{_BUCKET}/\n")

    if not args.dry_run:
        import boto3
        import botocore.exceptions
        s3 = boto3.client("s3")

    errors: list[str] = []
    for pkl in pkls:
        key = pkl.relative_to(_MODELS_DIR).as_posix()
        s3_uri = f"s3://{_BUCKET}/{key}"
        size_mb = pkl.stat().st_size / (1024 * 1024)

        if args.dry_run:
            print(f"  [DRY RUN] {pkl.relative_to(_PROJECT_ROOT)}  →  {s3_uri}  ({size_mb:.1f} MB)")
            continue

        try:
            with open(pkl, "rb") as fh:
                s3.upload_fileobj(fh, _BUCKET, key)
            print(f"  OK  {s3_uri}  ({size_mb:.1f} MB)")
        except botocore.exceptions.NoCredentialsError:
            print("ERROR: AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")
            sys.exit(1)
        except Exception as exc:
            print(f"  FAIL  {s3_uri}: {exc}")
            errors.append(str(pkl))

    if errors:
        print(f"\n{len(errors)} upload(s) failed:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    elif not args.dry_run:
        print(f"\nAll {len(pkls)} artifacts uploaded successfully.")
        print("\nNext steps:")
        print("  1. Verify a sample artifact loads:  python -c \"from betting_ml.utils.artifact_store import load_artifact; m = load_artifact('s3://baseball-betting-ml-artifacts/home_win/elasticnet_market_blind_2026.pkl'); print(type(m))\"")
        print("  2. Untrack committed pkls from git:  git rm --cached betting_ml/models/**/*.pkl")
        print("  3. Add AWS credentials to Dagster Cloud secrets and Streamlit environment:")
        print("       AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION")


if __name__ == "__main__":
    main()
