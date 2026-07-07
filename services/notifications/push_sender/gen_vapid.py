#!/usr/bin/env python3
"""Generate a VAPID keypair for Web Push (E9.9 / A0.6). OPERATOR-run, once.

Writes the private key to a PEM file (default ./vapid_private.pem) and prints the
public key. The private PEM is what pywebpush's `vapid_private_key` accepts; the
public key is the base64url uncompressed EC point the browser's
`applicationServerKey` wants.

  • vapid_private.pem            → feed to provision-notifications.sh (Lambda env ONLY)
  • NEXT_PUBLIC_VAPID_PUBLIC_KEY → set in the frontend (Vercel) env; safe to ship

NEVER commit these; the private key stays server-side. `.pem` is gitignored, but
double-check before any `git add`.

Usage:  uv run python services/notifications/push_sender/gen_vapid.py [OUT.pem]
Deps:   cryptography  (already in the repo env)
"""

from __future__ import annotations

import base64
import os
import stat
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "vapid_private.pem"

    key = ec.generate_private_key(ec.SECP256R1())

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_point = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64url = base64.urlsafe_b64encode(public_point).rstrip(b"=").decode()

    # Write the private key with 0600 perms (owner read/write only).
    with open(out_path, "wb") as f:
        f.write(private_pem)
    os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)

    abspath = os.path.abspath(out_path)
    print(f"✅ wrote private key → {abspath}  (chmod 600)\n")
    print("Next:")
    print(f"  VAPID_PRIVATE_KEY=\"$(cat {out_path})\" \\")
    print("  VAPID_SUBJECT=\"mailto:support@credencesports.com\" \\")
    print("  SES_FROM_ADDRESS=\"alerts@credencesports.com\" \\")
    print("    ./services/notifications/provision-notifications.sh\n")
    print("Set this in the frontend (Vercel) env — safe to ship:")
    print(f"  NEXT_PUBLIC_VAPID_PUBLIC_KEY={public_b64url}")


if __name__ == "__main__":
    main()
