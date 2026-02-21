"""CLI: python -m live_data.collector <mint_address> [--json] [--verbose]"""

import argparse
import asyncio
import json
import logging
import sys

from .orchestrator import collect_features


def main():
    parser = argparse.ArgumentParser(
        description="Collect 81 features for a Solana token"
    )
    parser.add_argument("mint", help="Token mint address")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    result = asyncio.run(collect_features(args.mint))

    if args.json:
        output = {
            "mint": result.mint,
            "features": result.features,
            "latency_ms": result.latency_ms,
            "errors": result.errors,
            "total_latency_ms": result.total_latency_ms,
            "features_collected": result.features_collected,
        }
        # Convert bools/None properly for JSON
        print(json.dumps(output, indent=2, default=str))
    else:
        _print_table(result)


def _print_table(result):
    print(f"\n{'=' * 60}")
    print(f"  Token: {result.mint}")
    print(f"  Features collected: {result.features_collected} / {len(result.features)}")
    print(f"  Total latency: {result.total_latency_ms:.0f} ms")
    print(f"{'=' * 60}\n")

    # Group features by prefix
    groups: dict[str, list[tuple[str, object]]] = {}
    for k, v in result.features.items():
        prefix = k.split("_")[0] if "_" in k else "general"
        # More meaningful grouping
        if k.startswith("gt_"):
            group = "GeckoTerminal"
        elif k.startswith("rc_"):
            group = "RugCheck"
        elif k.startswith("jup_"):
            group = "Jupiter"
        elif k.startswith("creator_"):
            group = "Creator Wallet"
        elif k in (
            "liquidity_to_fdv_ratio",
            "sell_pressure_score",
            "metadata_completeness",
            "authority_risk_score",
            "wallet_freshness_flag",
            "consensus_risk",
            "price_liquidity_divergence",
        ):
            group = "Derived"
        else:
            group = "Helius"
        groups.setdefault(group, []).append((k, v))

    for group, items in groups.items():
        non_null = sum(1 for _, v in items if v is not None)
        print(f"  [{group}] ({non_null}/{len(items)} populated)")
        for k, v in items:
            marker = "+" if v is not None else "-"
            display = _fmt(v)
            print(f"    {marker} {k}: {display}")
        print()

    # Latency
    print("  [Latency]")
    for api, ms in result.latency_ms.items():
        print(f"    {api}: {ms:.0f} ms")

    if result.errors:
        print("\n  [Errors]")
        for err in result.errors:
            print(f"    ! {err}")
    print()


def _fmt(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.2f}"
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else "[]"
    return str(v)


if __name__ == "__main__":
    main()
