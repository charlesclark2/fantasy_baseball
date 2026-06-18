"""
Push branded invite + verification HTML templates into the Cognito user pool.

Sets BOTH templates in one update-user-pool call so neither wipes the other.
Fetches current pool state first so unrelated settings are not disturbed.

Usage:
    python infrastructure/email/update_cognito_invite_template.py [--dry-run]
"""

import argparse
import json
import pathlib
import subprocess
import sys

POOL_ID = "us-east-1_gG9zMbwQt"
REGION = "us-east-1"
HERE = pathlib.Path(__file__).parent

INVITE_HTML_FILE = HERE / "cognito-invite-template.html"
INVITE_SUBJECT = "Your Credence Sports beta invitation"

VERIFY_HTML_FILE = HERE / "cognito-verification-template.html"
VERIFY_SUBJECT = "Your Credence Sports verification code"


def run(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print("ERROR:", result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout


def describe_pool():
    out = run([
        "aws", "cognito-idp", "describe-user-pool",
        "--user-pool-id", POOL_ID,
        "--region", REGION,
    ])
    return json.loads(out)["UserPool"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the payload without calling AWS")
    args = parser.parse_args()

    invite_html = INVITE_HTML_FILE.read_text()
    verify_html = VERIFY_HTML_FILE.read_text()
    print(f"Invite template:  {len(invite_html):,} chars")
    print(f"Verify template:  {len(verify_html):,} chars")

    # Fetch current pool to see what's already set
    print("Fetching current pool state…")
    pool = describe_pool()

    # Show existing templates so we can confirm nothing is lost
    existing_invite = pool.get("AdminCreateUserConfig", {}).get("InviteMessageTemplate", {})
    existing_verify = pool.get("VerificationMessageTemplate", {})
    print(f"  Current invite subject: {existing_invite.get('EmailSubject', '(none)')}")
    print(f"  Current verify subject: {existing_verify.get('EmailSubject', '(none)')}")

    # Build payloads
    admin_create_user_config = {
        # Preserve existing AllowAdminCreateUserOnly and UnusedAccountValidityDays
        "AllowAdminCreateUserOnly": pool.get("AdminCreateUserConfig", {}).get(
            "AllowAdminCreateUserOnly", True
        ),
        "UnusedAccountValidityDays": pool.get("AdminCreateUserConfig", {}).get(
            "UnusedAccountValidityDays", 7
        ),
        "InviteMessageTemplate": {
            "EmailMessage": invite_html,
            "EmailSubject": INVITE_SUBJECT,
        },
    }

    verification_message_template = {
        # Preserve DefaultEmailOption if already set
        "DefaultEmailOption": existing_verify.get("DefaultEmailOption", "CONFIRM_WITH_CODE"),
        "EmailMessage": verify_html,
        "EmailSubject": VERIFY_SUBJECT,
    }

    if args.dry_run:
        print("\n── DRY RUN — invite payload (first 400 chars) ──")
        print(json.dumps(admin_create_user_config)[:400] + "…")
        print("\n── DRY RUN — verify payload (first 400 chars) ──")
        print(json.dumps(verification_message_template)[:400] + "…")
        print("\nNo changes made.")
        return

    cmd = [
        "aws", "cognito-idp", "update-user-pool",
        "--user-pool-id", POOL_ID,
        "--region", REGION,
        "--admin-create-user-config", json.dumps(admin_create_user_config),
        "--verification-message-template", json.dumps(verification_message_template),
    ]
    print("\nApplying update…")
    run(cmd, capture=False)
    print("\nDone. Both templates updated.")
    print("Next: Cognito console → us-east-1_gG9zMbwQt → Users → Create user")
    print("      Send a test invite to ctcb57@gmail.com and verify the logo renders.")


if __name__ == "__main__":
    main()
