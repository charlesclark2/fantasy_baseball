#!/usr/bin/env python3
"""E9.56 — the ATTACKER TEST. Hits the deployed API as an unauthenticated / forged-token caller and
asserts the paid data is not retrievable off the wire.

🚨 THIS, NOT CI, IS THE PROOF. CI mocks every IO boundary, so it cannot see the API Gateway
authorizer, the real Cognito JWKS, the real S3 blobs, or the deployed Lambda — every one of which is
load-bearing here. A UI that hides the 2026 numbers while the payload still carries them FAILS this
story, and only a direct fetch can tell the difference.

Run it from the LAPTOP (it only needs public internet):

    uv run python scripts/check_api_entitlement.py
    uv run python scripts/check_api_entitlement.py --api https://api.credencesports.com --strict

`--strict` exits non-zero on any FAIL, so it can gate the launch. Without it the script reports and
exits 0 (safe to run casually).

WHAT IT CHECKS
  1. Gated endpoints are unreachable unauthenticated (401 at the gateway, before Lambda).
  2. A FORGED JWT claiming `subscriber`/`admin` buys nothing anywhere.
  3. The public track-record surface serves past seasons and REFUSES the locked season.
  4. If a 2026 surface IS publicly reachable (i.e. the operator has flipped its gateway route to
     `--authorization-type NONE` for launch), then its payload must be LOCKED: no model value, and
     — the part that is easy to miss — no MODEL ORDERING either. A payload with every number
     stripped but the array order intact still hands over the ranking, because the array index IS
     the rank. So check 4b re-derives the order and requires it to look like the market's, not ours.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request

DEFAULT_API = "https://api.credencesports.com"
LOCKED_SEASON = 2026

# Field names that are pure model output. None of these may appear in a payload served to a
# non-entitled caller. Mirrors the server-side allowlist's complement for the shipped exports.
MODEL_FIELDS = [
    "fpStd", "fpHalf", "fpPpr", "fpSd", "fpP10", "fpP90",
    "pts", "ptsP10", "ptsP90", "vor", "vorP10", "vorP90", "repl",
    "posRank", "ovrRank", "conf", "uncType", "contrib", "g",
    "passYds", "passTd", "rushYds", "recYds", "recTd",
]

# Routes that must NEVER be reachable without a valid token.
GATED = [
    "/fantasy/nfl/my-teams",
    "/fantasy/leagues",
    "/fantasy/mlb/prospects/board",
    "/fantasy/mlb/prospects/manifest",
    "/picks/today",
    "/performance/summary",
    "/players",
    "/teams",
    "/bets",
    "/portfolio/preferences",
    "/users/profile",
    "/admin/finances",
    "/admin/data-quality-reports",  # E9.56: had NO server-side admin check before this story
    "/pipeline/status",
]

# DELIBERATELY PUBLIC — verified against the code, not assumed. These are marketing surfaces the
# logged-out landing page fetches with no token (`frontend/app/page.tsx` server-side-fetches both),
# so 200-unauthenticated is CORRECT here and a 401 would break the landing page.
#
# ⚠️ `/picks/featured` is the one-free-pick teaser and it ships the FULL model detail for that pick
# (edge, model vs market probability, the CI, the driver attributions, the narrative). That is a
# deliberate product decision, not a leak — but it makes the endpoint the single most attractive
# scrape target on the betting half: a competitor polling it daily accumulates our featured-pick
# history for free. It cannot be gated without removing the teaser, so the lever that applies is
# RATE LIMITING (see `infrastructure/aws_resources.md` → API Gateway throttling). What IS asserted
# below is the property that would turn the teaser into a real leak: it must stay ONE pick.
DELIBERATE_PUBLIC = [
    ("/health", None),
    ("/blog/posts", None),
    ("/picks/featured", "single_pick"),
    ("/fantasy/nfl/track-record/manifest", None),
]

# The 2026 surfaces. Gateway-gated today; public at launch. Either way they must never leak.
GATED_SEASON_SURFACES = [
    f"/fantasy/nfl/projections?season={LOCKED_SEASON}",
    f"/fantasy/nfl/manifest?season={LOCKED_SEASON}",
    f"/fantasy/nfl/board?season={LOCKED_SEASON}&config=full_ppr&size=12",
]

_results: list[tuple[str, str, str]] = []  # (verdict, label, detail)


def record(ok: bool | None, label: str, detail: str = "") -> None:
    verdict = "PASS" if ok else ("FAIL" if ok is False else "INFO")
    _results.append((verdict, label, detail))
    icon = {"PASS": "✅", "FAIL": "🚨", "INFO": "  "}[verdict]
    print(f"{icon} {verdict:4}  {label}" + (f"  — {detail}" if detail else ""))


def forged_token(groups: list[str]) -> str:
    """An unsigned JWT asserting paid membership. A correct server treats it as anonymous."""

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return ".".join(
        [
            b64({"alg": "RS256", "kid": "forged"}),
            b64(
                {
                    "sub": "attacker-0000",
                    "cognito:groups": groups,
                    "token_use": "access",
                    "client_id": "1qh95e78bd7g6ipqcvdcpf7ou6",
                    "exp": 9999999999,
                }
            ),
            "bm90LWEtcmVhbC1zaWduYXR1cmU",
        ]
    )


def get(api: str, path: str, token: str | None = None, timeout: float = 30.0):
    """Return (status, parsed_body_or_None, raw_text)."""
    req = urllib.request.Request(api + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # noqa: BLE001
        return 0, None, f"{type(e).__name__}: {e}"
    try:
        return status, json.loads(raw), raw
    except Exception:  # noqa: BLE001
        return status, None, raw


def _rows(body):
    """Player rows out of any of the three payload shapes (list board / dict projections)."""
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    if isinstance(body, dict):
        for key in ("players", "rows", "board"):
            v = body.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


# Manifest keys that exist ONLY to label the entitled feature-attribution panel. With `contrib`
# locked there is nothing for them to describe, so a locked manifest must not ship them (E9.56
# payload minimization — don't send what isn't rendered).
_MANIFEST_ENTITLED_ONLY = ["featureLegend", "featureContributionsMeta"]


def _assert_locked_manifest(path: str, body) -> None:
    """E9.56b — the manifest carries no player ROWS, so the row scan below reported "nothing to
    check" for it and its redaction went unverified by this script (it was only ever confirmed by
    hand, 2026-08-05). A check that cannot fail is not a check — assert on it directly."""
    if not isinstance(body, dict):
        record(False, f"{path} — manifest is not an object", type(body).__name__)
        return
    record(
        body.get("locked") is True and body.get("entitled") is False,
        f"{path} — manifest declares itself LOCKED",
        f"locked={body.get('locked')} entitled={body.get('entitled')}",
    )
    leaked = [k for k in _MANIFEST_ENTITLED_ONLY if k in body]
    record(
        not leaked,
        f"{path} — entitled-only metadata is stripped",
        f"leaked: {leaked}" if leaked else "featureLegend + featureContributionsMeta absent",
    )
    record(
        bool(body.get("upgrade")) and bool(body.get("positions")),
        f"{path} — still carries the page shell + the upgrade CTA",
        "a locked manifest must let the free page render its frame and its CTA",
    )


def _assert_locked_payload(path: str, body) -> None:
    """The core no-leak assertions for a publicly-reachable gated-season payload."""
    if "/manifest" in path:
        _assert_locked_manifest(path, body)
        return
    rows = _rows(body)
    if not rows:
        record(None, f"{path} — publicly reachable but carries no player rows", "nothing to check")
        return

    leaked = sorted({f for r in rows for f in MODEL_FIELDS if f in r})
    record(
        not leaked,
        f"{path} — no model FIELD in a public payload",
        f"leaked: {leaked}" if leaked else f"{len(rows)} rows, identity+market only",
    )

    marked = sum(1 for r in rows if r.get("locked") is True)
    record(
        marked == len(rows),
        f"{path} — every row carries the locked marker",
        f"{marked}/{len(rows)} marked (the CTA needs this)",
    )

    # 4b — THE ORDERING CHECK. Our exports are sorted by our own projection; a locked payload must
    # be re-sorted onto a public key or the array index reconstructs the ranking exactly.
    adps = [r.get("adp") for r in rows if isinstance(r.get("adp"), (int, float))]
    if len(adps) >= 10:
        ascending = sum(1 for a, b in zip(adps, adps[1:]) if a <= b)
        frac = ascending / max(len(adps) - 1, 1)
        record(
            frac > 0.95,
            f"{path} — array order is the MARKET's, not ours",
            f"{frac:.1%} of adjacent rows non-decreasing in ADP "
            "(a low value means our ranking survived as the row order)",
        )
    else:
        record(None, f"{path} — ordering check skipped", "too few ADP values to judge")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any FAIL")
    args = ap.parse_args()
    api = args.api.rstrip("/")

    print(f"\nE9.56 attacker test against {api}\n" + "=" * 78)

    # ── 1. reachability ──────────────────────────────────────────────────────────────────────────
    print("\n1. Gated endpoints, UNAUTHENTICATED")
    for path in GATED:
        status, _, _ = get(api, path)
        record(status in (401, 403), f"{path} → {status}", "" if status in (401, 403) else "REACHABLE")

    # ── 2. forged token ─────────────────────────────────────────────────────────────────────────
    print("\n2. Gated endpoints, FORGED 'subscriber'+'admin' token")
    tok = forged_token(["subscriber", "admin", "fantasy_comp"])
    for path in GATED:
        status, body, _ = get(api, path, token=tok)
        if status in (401, 403):
            record(True, f"{path} → {status}")
        else:
            record(False, f"{path} → {status}", "FORGED TOKEN ACCEPTED — signature not verified")

    # ── 2b. the deliberately-public marketing surfaces ──────────────────────────────────────────
    print("\n2b. Deliberately PUBLIC surfaces (must stay reachable, must stay minimal)")
    for path, rule in DELIBERATE_PUBLIC:
        status, body, _ = get(api, path)
        record(status == 200, f"{path} → {status}", "public by design (landing page needs it)")
        if rule == "single_pick" and isinstance(body, dict):
            # The teaser must be ONE pick. A list, or a slate-shaped payload, would turn the
            # marketing surface into the whole day's picks — the actual leak to watch for here.
            slate_keys = [k for k in ("picks", "games", "rows") if isinstance(body.get(k), list)]
            record(
                not slate_keys,
                f"{path} is ONE featured pick, not the slate",
                f"slate-shaped keys present: {slate_keys}" if slate_keys else "single pick object",
            )

    # ── 3. the public free tier ─────────────────────────────────────────────────────────────────
    print("\n3. Public past-season surface (free by design)")
    status, body, _ = get(api, "/fantasy/nfl/track-record/manifest")
    record(status == 200, f"/fantasy/nfl/track-record/manifest → {status}", "public receipts")
    if isinstance(body, dict):
        seasons = body.get("seasons") or []
        record(
            all(int(s) < LOCKED_SEASON for s in seasons),
            "manifest advertises past seasons only",
            f"seasons={seasons}",
        )
    status, _, _ = get(api, f"/fantasy/nfl/track-record/{LOCKED_SEASON}")
    record(
        status in (404, 422),
        f"/fantasy/nfl/track-record/{LOCKED_SEASON} → {status}",
        "the locked season is refused, not merely 'unpublished'",
    )

    # ── 4. the gated season, however it is currently exposed ────────────────────────────────────
    print(f"\n4. The {LOCKED_SEASON} surfaces (the paid data)")
    for path in GATED_SEASON_SURFACES:
        for label, token in (("anonymous", None), ("forged token", tok)):
            status, body, raw = get(api, path, token=token)
            if status in (401, 403):
                record(True, f"{path} [{label}] → {status}", "gateway-gated (pre-launch state)")
                continue
            if status == 404:
                record(None, f"{path} [{label}] → 404", "not published for that season")
                continue
            if status != 200:
                record(None, f"{path} [{label}] → {status}", raw[:120])
                continue
            record(
                None,
                f"{path} [{label}] → 200",
                "PUBLICLY REACHABLE — checking the payload is locked",
            )
            _assert_locked_payload(f"{path} [{label}]", body)

    # ── summary ─────────────────────────────────────────────────────────────────────────────────
    fails = [r for r in _results if r[0] == "FAIL"]
    passes = [r for r in _results if r[0] == "PASS"]
    print("\n" + "=" * 78)
    print(f"{len(passes)} passed, {len(fails)} FAILED")
    if fails:
        print("\n🚨 The paid data is retrievable off the wire:")
        for _, label, detail in fails:
            print(f"   • {label}  {detail}")
        return 1 if args.strict else 0
    print("✅ No gated data was retrievable as an unauthenticated or forged-token caller.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
