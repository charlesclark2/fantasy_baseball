#!/usr/bin/env python3
"""G100-D1 — the launch cost model: project monthly Vercel + AWS spend against monthly visitors.

Run it:
    uv run python scripts/estimate_launch_cost.py
    uv run python scripts/estimate_launch_cost.py --visitors 1000 10000 100000 250000
    uv run python scripts/estimate_launch_cost.py --no-guardrails   # the pre-G100-D1 baseline
    uv run python scripts/estimate_launch_cost.py --markdown        # the table as it appears in docs/

WHY A SCRIPT AND NOT A TABLE IN A DOC. Every number below is a product of assumptions that will be
wrong within a quarter — Vercel re-prices, the page gets heavier, the cache TTLs get tuned. A static
table rots silently and is then quoted with confidence. This is executable, so the assumptions are
visible, changeable, and the table can be regenerated in one command.

🚨 THE OUTPUT IS AN ESTIMATE, AND ITS ERROR IS DOMINATED BY THE TRAFFIC ASSUMPTIONS, NOT THE RATES.
The unit prices are published and exact. `PAGEVIEWS_PER_SESSION`, `KB_PER_SESSION` and
`EDGE_REQUESTS_PER_SESSION` are guesses until we have real analytics, and the total moves roughly
linearly in each. Treat the SHAPE (where the cliffs are, which line dominates) as the finding, and
the absolute dollars as an order of magnitude. `--markdown` prints the assumption block with the
table so a pasted result always carries its own caveats.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

SECONDS_PER_MONTH = 30 * 24 * 3600


# ══════════════════════════════════════════════════════════════════════════════════════════════
# UNIT PRICES
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ AS OF 2026-08-08. Vercel in particular re-prices its managed-infrastructure line items, so
# these must be re-checked against the dashboard's Usage page before being quoted to anyone. The
# `included` figures are the Pro plan's monthly allowances; overage is charged on the excess only.


@dataclass(frozen=True)
class Metered:
    """A metered line item: `included` units free per month, then `rate` per `unit_size` units."""

    name: str
    included: float
    rate: float
    unit_size: float = 1.0

    def cost(self, usage: float) -> float:
        return max(0.0, usage - self.included) / self.unit_size * self.rate

    def headroom_fraction(self, usage: float) -> float:
        return usage / self.included if self.included else float("inf")


# ── Vercel Pro ────────────────────────────────────────────────────────────────────────────────
VERCEL_SEAT_USD = 20.00  # per member per month; 1 member assumed

VERCEL = {
    # Bytes served to visitors from the edge.
    "fast_data_transfer_gb": Metered("Fast Data Transfer (GB)", 1_000, 0.15),
    # Bytes pulled from the origin (our functions) into the edge network.
    "fast_origin_transfer_gb": Metered("Fast Origin Transfer (GB)", 100, 0.06),
    # Every HTTP request the edge answers, cache HIT or MISS. Static assets count.
    "edge_requests": Metered("Edge Requests", 10_000_000, 2.00, unit_size=1_000_000),
    # Only a cache MISS on a route handler costs one of these.
    "function_invocations": Metered("Function Invocations", 1_000_000, 0.60, unit_size=1_000_000),
    "function_gb_hours": Metered("Function Duration (GB-hr)", 1_000, 0.18),
    # `next.config.mjs` sets `images: { unoptimized: true }`, so this line is structurally $0 for
    # us. Kept visible because turning image optimization back on would silently start billing it.
    "image_optimizations": Metered("Image Optimization (source images)", 5_000, 0.05, unit_size=1_000),
}

# ── AWS us-east-1 ─────────────────────────────────────────────────────────────────────────────
AWS_LAMBDA_PER_REQUEST = 0.20 / 1_000_000
AWS_LAMBDA_PER_GB_SECOND = 0.0000166667
AWS_APIGW_HTTP_PER_REQUEST = 1.00 / 1_000_000
AWS_DDB_READ_PER_RRU = 0.125 / 1_000_000  # on-demand, post-2024 price cut
AWS_DDB_WRITE_PER_WRU = 0.625 / 1_000_000
AWS_S3_GET_PER_REQUEST = 0.40 / 1_000_000
AWS_EGRESS_PER_GB = 0.09
AWS_EGRESS_FREE_GB = 100.0
AWS_CLOUDWATCH_PER_GB = 0.50


# ══════════════════════════════════════════════════════════════════════════════════════════════
# TRAFFIC + WORKLOAD ASSUMPTIONS  — this is where the uncertainty lives
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Assumptions:
    # ── visitor behaviour ─────────────────────────────────────────────────────────────────────
    pageviews_per_session: float = 2.5
    #  First page load pulls the JS bundle; subsequent navigations are client-side and pull only
    #  data. ~600 KB first + ~60 KB per extra view is a normal Next app of this size.
    kb_per_session: float = 700.0
    #  HTML + JS/CSS chunks + fonts + the API calls. Static chunks are browser-cached after the
    #  first view, so this is not `pageviews × 30`.
    edge_requests_per_session: float = 40.0

    # ── how many of our own read endpoints a session touches ──────────────────────────────────
    #  Anonymous surfaces only. Post-guardrails these are CDN route-handler calls; pre-guardrails
    #  they were direct API Lambda calls.
    api_reads_per_session: float = 3.0

    # ── caching ───────────────────────────────────────────────────────────────────────────────
    #  ⚠️ THE SINGLE MOST IMPORTANT ASSUMPTION IN THE MODEL, AND THE EASIEST TO GET WRONG.
    #  A CDN cache is PER-POP, so a `s-maxage=300` object is fetched from origin roughly once per
    #  300s PER POP THAT SEES TRAFFIC, not once globally. For a US-centric audience call it ~5
    #  effective POPs. Setting this to 1 (the naive model) understates origin load ~5x.
    pop_multiplier: float = 5.0
    #  Distinct cache keys across the anonymous surfaces. The board's key includes (config, size),
    #  so this is not 1 — it is however many format combinations visitors actually request. Junk
    #  values cannot inflate it because the route validates both params before building the URL.
    distinct_cache_keys: float = 12.0
    #  Weighted mean TTL across the anonymous surfaces (featured 300s, board/manifest/projections
    #  900s, track-record 3600s).
    mean_s_maxage_seconds: float = 600.0

    # ── per-request work ──────────────────────────────────────────────────────────────────────
    lambda_memory_gb: float = 0.5  # the deployed API Lambda is 512 MB
    #  A cache-hit read (DynamoDB point read or one S3 GetObject) on a warm container. NOT the
    #  lakehouse path — that is seconds, and G100-D1 removed it from the public hot path.
    lambda_ms_per_read: float = 120.0
    ddb_rru_per_read: float = 0.5  # eventually-consistent read of a ≤4 KB item
    s3_gets_per_read: float = 1.0
    #  Vercel route-handler duration on a cache MISS: our own work plus the upstream round trip.
    vercel_fn_ms_per_miss: float = 250.0
    vercel_fn_memory_gb: float = 1.0
    #  Payload pulled from origin into the edge on a miss (the board blob is the big one).
    origin_kb_per_miss: float = 250.0

    # ── logging ───────────────────────────────────────────────────────────────────────────────
    cloudwatch_kb_per_lambda_invocation: float = 1.5

    label: str = "with guardrails"


def _gb(kb: float) -> float:
    return kb / (1024 * 1024)


@dataclass
class Result:
    visitors: int
    lines: dict[str, float] = field(default_factory=dict)
    usage: dict[str, float] = field(default_factory=dict)

    @property
    def vercel_total(self) -> float:
        return sum(v for k, v in self.lines.items() if k.startswith("vercel"))

    @property
    def aws_total(self) -> float:
        return sum(v for k, v in self.lines.items() if k.startswith("aws"))

    @property
    def total(self) -> float:
        return self.vercel_total + self.aws_total


def estimate(visitors: int, a: Assumptions, *, guardrails: bool) -> Result:
    """Monthly cost at `visitors` monthly unique visitors."""
    r = Result(visitors=visitors)

    sessions = float(visitors)
    api_reads = sessions * a.api_reads_per_session

    # ── how many of those reads actually reach an origin ──────────────────────────────────────
    if guardrails:
        # A cached surface is fetched from origin at most once per TTL per cache key per POP —
        # a ceiling that does NOT grow with visitors. That is the whole point of the guardrail:
        # above a few thousand visitors the origin cost stops tracking traffic and goes flat.
        windows = SECONDS_PER_MONTH / a.mean_s_maxage_seconds
        origin_ceiling = windows * a.distinct_cache_keys * a.pop_multiplier
        vercel_fn_invocations = min(api_reads, origin_ceiling)
        lambda_invocations = vercel_fn_invocations  # one upstream call per CDN miss
    else:
        # Pre-G100-D1: every anonymous view called the API Lambda directly. No CDN in between, so
        # no Vercel function invocations at all — and no ceiling either.
        vercel_fn_invocations = 0.0
        lambda_invocations = api_reads

    # ══ Vercel ════════════════════════════════════════════════════════════════════════════════
    edge_requests = sessions * a.edge_requests_per_session
    data_transfer_gb = _gb(sessions * a.kb_per_session)
    origin_transfer_gb = _gb(vercel_fn_invocations * a.origin_kb_per_miss)
    fn_gb_hours = vercel_fn_invocations * (a.vercel_fn_ms_per_miss / 1000.0) / 3600.0 * a.vercel_fn_memory_gb

    r.usage["Vercel edge requests"] = edge_requests
    r.usage["Vercel fast data transfer (GB)"] = data_transfer_gb
    r.usage["Vercel function invocations"] = vercel_fn_invocations
    r.usage["Vercel function GB-hours"] = fn_gb_hours

    r.lines["vercel_seat"] = VERCEL_SEAT_USD
    r.lines["vercel_edge_requests"] = VERCEL["edge_requests"].cost(edge_requests)
    r.lines["vercel_data_transfer"] = VERCEL["fast_data_transfer_gb"].cost(data_transfer_gb)
    r.lines["vercel_origin_transfer"] = VERCEL["fast_origin_transfer_gb"].cost(origin_transfer_gb)
    r.lines["vercel_fn_invocations"] = VERCEL["function_invocations"].cost(vercel_fn_invocations)
    r.lines["vercel_fn_duration"] = VERCEL["function_gb_hours"].cost(fn_gb_hours)
    r.lines["vercel_image_opt"] = 0.0  # images.unoptimized = true

    # ══ AWS ═══════════════════════════════════════════════════════════════════════════════════
    lambda_gb_seconds = lambda_invocations * (a.lambda_ms_per_read / 1000.0) * a.lambda_memory_gb
    egress_gb = _gb(lambda_invocations * a.origin_kb_per_miss)
    cw_gb = _gb(lambda_invocations * a.cloudwatch_kb_per_lambda_invocation)

    r.usage["API Gateway requests"] = lambda_invocations
    r.usage["Lambda invocations"] = lambda_invocations
    r.usage["Lambda GB-seconds"] = lambda_gb_seconds

    r.lines["aws_apigw"] = lambda_invocations * AWS_APIGW_HTTP_PER_REQUEST
    r.lines["aws_lambda_requests"] = lambda_invocations * AWS_LAMBDA_PER_REQUEST
    r.lines["aws_lambda_duration"] = lambda_gb_seconds * AWS_LAMBDA_PER_GB_SECOND
    r.lines["aws_dynamodb"] = lambda_invocations * a.ddb_rru_per_read * AWS_DDB_READ_PER_RRU
    r.lines["aws_s3_get"] = lambda_invocations * a.s3_gets_per_read * AWS_S3_GET_PER_REQUEST
    r.lines["aws_egress"] = max(0.0, egress_gb - AWS_EGRESS_FREE_GB) * AWS_EGRESS_PER_GB
    r.lines["aws_cloudwatch"] = cw_gb * AWS_CLOUDWATCH_PER_GB
    return r


# ══════════════════════════════════════════════════════════════════════════════════════════════
# reporting
# ══════════════════════════════════════════════════════════════════════════════════════════════

_QUOTA_KEYS = [
    ("Vercel edge requests", VERCEL["edge_requests"]),
    ("Vercel fast data transfer (GB)", VERCEL["fast_data_transfer_gb"]),
    ("Vercel function invocations", VERCEL["function_invocations"]),
    ("Vercel function GB-hours", VERCEL["function_gb_hours"]),
]


def _fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def render(visitors_list: list[int], a: Assumptions, *, guardrails: bool, markdown: bool) -> str:
    results = [estimate(v, a, guardrails=guardrails) for v in visitors_list]
    out: list[str] = []
    bar = "|" if markdown else " "

    header = ["Monthly visitors", "Vercel", "AWS", "TOTAL", "Largest single line"]
    rows = []
    for r in results:
        biggest = max(
            ((k, v) for k, v in r.lines.items() if k != "vercel_seat"),
            key=lambda kv: kv[1],
            default=("—", 0.0),
        )
        rows.append(
            [
                f"{r.visitors:,}",
                _fmt_usd(r.vercel_total),
                _fmt_usd(r.aws_total),
                _fmt_usd(r.total),
                f"{biggest[0]} ({_fmt_usd(biggest[1])})",
            ]
        )

    if markdown:
        out.append("| " + " | ".join(header) + " |")
        out.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in rows:
            out.append("| " + " | ".join(row) + " |")
    else:
        widths = [max(len(header[i]), *(len(r[i]) for r in rows)) for i in range(len(header))]
        out.append(bar.join(h.ljust(widths[i]) for i, h in enumerate(header)))
        out.append("-" * (sum(widths) + len(widths)))
        for row in rows:
            out.append(bar.join(c.ljust(widths[i]) for i, c in enumerate(row)))

    # Quota headroom — the "when do we hit the cliff" half of the question.
    out.append("")
    out.append("Included-quota utilisation (Vercel Pro):" if not markdown else "")
    if markdown:
        out.append("| Monthly visitors | " + " | ".join(k for k, _ in _QUOTA_KEYS) + " |")
        out.append("|" + "|".join(["---"] * (1 + len(_QUOTA_KEYS))) + "|")
    for r in results:
        cells = []
        for key, meter in _QUOTA_KEYS:
            frac = meter.headroom_fraction(r.usage.get(key, 0.0))
            cells.append(f"{frac * 100:,.1f}%")
        if markdown:
            out.append(f"| {r.visitors:,} | " + " | ".join(cells) + " |")
        else:
            out.append(f"  {r.visitors:>9,}  " + "  ".join(f"{c:>9}" for c in cells))
    return "\n".join(out)


def find_first_overage(a: Assumptions, *, guardrails: bool) -> dict[str, int]:
    """The visitor count at which each Vercel included quota is first exceeded — the 'cliff'.

    Coarse bisection on a monotone function; returns the first multiple of 1,000 that overshoots.
    """
    cliffs: dict[str, int] = {}
    for key, meter in _QUOTA_KEYS:
        lo, hi = 1_000, 100_000_000
        if estimate(hi, a, guardrails=guardrails).usage.get(key, 0.0) <= meter.included:
            cliffs[key] = -1  # never, at any plausible traffic
            continue
        while lo < hi:
            mid = (lo + hi) // 2
            if estimate(mid, a, guardrails=guardrails).usage.get(key, 0.0) > meter.included:
                hi = mid
            else:
                lo = mid + 1
        cliffs[key] = lo
    return cliffs


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The abuse scenario — the reason this story exists
# ══════════════════════════════════════════════════════════════════════════════════════════════


def abuse_scenario(a: Assumptions, *, requests_per_second: float = 50.0) -> str:
    """One determined scraper, sustained for a month, with and without the per-IP limit.

    ⭐ THIS IS THE FINDING THAT JUSTIFIES THE GUARDRAILS, and the visitor table above does NOT
    contain it. Organic cost at 100k visitors is under a dollar of AWS — the guardrails change it
    by pennies. What they change is the TAIL: abuse is not visitor-driven, has no natural ceiling,
    and its cost is dominated by a line the visitor model barely touches — EGRESS. A scraper pulling
    a 250 KB board 50×/s for a month moves ~32 TB, which is thousands of dollars on a card belonging
    to a self-funded company.

    The per-IP limiter does not reduce the REQUEST count (the attacker still connects); it reduces
    what each request COSTS us, because a 429 returns a few hundred bytes instead of a board.
    """
    seconds = SECONDS_PER_MONTH
    total_requests = requests_per_second * seconds

    def _cost(served_requests: float, refused_requests: float) -> tuple[float, float]:
        """(total_usd, egress_usd) for a mix of served and 429'd requests."""
        invocations = served_requests + refused_requests
        gb_seconds = (
            served_requests * (a.lambda_ms_per_read / 1000.0)
            # A 429 short-circuits in middleware — no DynamoDB, no S3, ~1 ms of work.
            + refused_requests * 0.001
        ) * a.lambda_memory_gb
        egress_gb = _gb(served_requests * a.origin_kb_per_miss + refused_requests * 0.3)
        total = (
            invocations * (AWS_APIGW_HTTP_PER_REQUEST + AWS_LAMBDA_PER_REQUEST)
            + gb_seconds * AWS_LAMBDA_PER_GB_SECOND
            + served_requests * a.ddb_rru_per_read * AWS_DDB_READ_PER_RRU
            + served_requests * a.s3_gets_per_read * AWS_S3_GET_PER_REQUEST
            + max(0.0, egress_gb - AWS_EGRESS_FREE_GB) * AWS_EGRESS_PER_GB
            + _gb(invocations * a.cloudwatch_kb_per_lambda_invocation) * AWS_CLOUDWATCH_PER_GB
        )
        return total, max(0.0, egress_gb - AWS_EGRESS_FREE_GB) * AWS_EGRESS_PER_GB

    unlimited_total, unlimited_egress = _cost(total_requests, 0.0)

    # With the per-IP bucket: one source sustains `per_second` successful reads; the rest are 429s.
    served = min(total_requests, public_policy_per_second() * seconds)
    limited_total, limited_egress = _cost(served, total_requests - served)

    lines = [
        "",
        f"--- Abuse scenario: ONE source at {requests_per_second:.0f} req/s for a month "
        f"({total_requests / 1e6:,.1f}M requests) ---",
        f"  {'':<34}{'TOTAL':>14}{'of which egress':>18}",
        f"  {'No per-IP limit (today)':<34}{_fmt_usd(unlimited_total):>14}{_fmt_usd(unlimited_egress):>18}",
        f"  {'With the per-IP limit':<34}{_fmt_usd(limited_total):>14}{_fmt_usd(limited_egress):>18}",
        f"  {'Avoided':<34}{_fmt_usd(unlimited_total - limited_total):>14}",
        "",
        "  ⚠️ The limiter does not stop the attacker CONNECTING — the residual is mostly API",
        "     Gateway + Lambda request charges for cheap 429s. The API-Gateway STAGE throttle is",
        "     the second layer that bounds those; per-IP shaping and a total-blast-radius cap are",
        "     complementary, not alternatives.",
        "  ⚠️ Assumes the scraper lands on warm containers so the in-process bucket sees it. A",
        "     low-and-slow attacker spread across cold starts is under-counted — see the honest",
        "     limitation in `cost_guardrails.py`.",
    ]
    return "\n".join(lines)


def public_policy_per_second() -> float:
    """The sustained per-IP allowance the deployed default grants (mirrors `public_policy()`)."""
    return 0.5


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--visitors", type=int, nargs="+", default=[1_000, 10_000, 100_000])
    p.add_argument("--no-guardrails", action="store_true", help="model the pre-G100-D1 per-view-Lambda path")
    p.add_argument("--markdown", action="store_true")
    args = p.parse_args()

    a = Assumptions()
    guardrails = not args.no_guardrails
    a.label = "with guardrails" if guardrails else "WITHOUT guardrails (pre-G100-D1 baseline)"

    print(f"\n=== Projected monthly cost — {a.label} ===\n")
    print(render(args.visitors, a, guardrails=guardrails, markdown=args.markdown))

    print("\n--- First overage ('the cliff'), monthly visitors ---")
    for key, at in find_first_overage(a, guardrails=guardrails).items():
        print(f"  {key:<38} {'never (at any plausible traffic)' if at < 0 else f'{at:,}'}")

    print(abuse_scenario(a))

    print("\n--- Assumptions (edit them in Assumptions, then re-run) ---")
    for name, value in vars(a).items():
        if name != "label":
            print(f"  {name:<38} {value}")
    print(
        "\n⚠️ Unit prices are as of 2026-08-08 and Vercel re-prices; verify against the dashboard\n"
        "   before quoting. Error is dominated by the traffic assumptions, not the rates.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
