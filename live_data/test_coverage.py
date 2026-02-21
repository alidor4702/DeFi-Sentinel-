"""
Coverage test: dynamically fetch ~100 diverse-age Solana tokens from GeckoTerminal
and measure real-world data availability across all 81 collector features.

Tokens are sourced from 3 endpoints for age diversity:
  - /new_pools      → minutes–hours old  (~40%)
  - /pools          → days old (top pools) (~40%)
  - /trending_pools → weeks–months+ old   (~20%)

Usage:
    python -m live_data.test_coverage [--count 100] [--concurrency 3]
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .collector import collect_features, CollectionResult

logger = logging.getLogger("test_coverage")

# All 81 feature keys grouped by source
SOURCE_FEATURES = {
    "helius": [
        "token_name", "token_symbol", "token_decimals", "token_supply",
        "mint_authority", "mint_authority_revoked", "freeze_authority",
        "freeze_authority_revoked", "update_authority", "is_mutable",
        "token_standard", "token_program", "metadata_uri",
        "metadata_uri_reachable", "has_image", "has_description",
        "has_website", "has_twitter", "has_telegram", "creator_address",
    ],
    "creator_wallet": [
        "creator_sol_balance", "creator_wallet_age_hours",
        "creator_token_count", "creator_tx_count",
        "creator_prev_tokens_rugged", "creator_nft_count",
    ],
    "rugcheck": [
        "rc_score", "rc_risk_level", "rc_risk_count",
        "rc_mint_authority_disabled", "rc_freeze_authority_disabled",
        "rc_mutable_metadata", "rc_top_holder_pct", "rc_top10_holder_pct",
        "rc_lp_locked", "rc_lp_lock_pct", "rc_lp_lock_duration_days",
        "rc_lp_burned", "rc_single_holder_ownership",
        "rc_high_concentration", "rc_low_liquidity", "rc_copycat_token",
        "rc_total_market_liquidity", "rc_num_markets",
    ],
    "geckoterminal": [
        "gt_pool_count", "gt_pool_address", "gt_pool_name", "gt_dex",
        "gt_base_token_price_usd", "gt_quote_token_price_usd",
        "gt_fdv_usd", "gt_market_cap_usd", "gt_reserve_usd",
        "gt_volume_5m", "gt_volume_1h", "gt_volume_6h", "gt_volume_24h",
        "gt_price_change_5m", "gt_price_change_1h", "gt_price_change_6h",
        "gt_price_change_24h", "gt_tx_count_5m_buys",
        "gt_tx_count_5m_sells", "gt_tx_count_1h_buys",
        "gt_tx_count_1h_sells", "gt_tx_count_24h_buys",
        "gt_tx_count_24h_sells", "gt_buy_sell_ratio_1h",
        "gt_pool_age_hours",
    ],
    "jupiter": [
        "jup_listed", "jup_strict_list", "jup_daily_volume",
        "jup_price_usd", "jup_tags",
    ],
    "derived": [
        "liquidity_to_fdv_ratio", "sell_pressure_score",
        "metadata_completeness", "authority_risk_score",
        "wallet_freshness_flag", "consensus_risk",
        "price_liquidity_divergence",
    ],
}

ALL_FEATURES = [f for feats in SOURCE_FEATURES.values() for f in feats]

# Age brackets: (label, min_hours, max_hours)
# max_hours=None means no upper bound
AGE_BRACKETS = [
    ("Minutes", 0, 1),
    ("Hours", 1, 24),
    ("Days", 24, 168),         # 1d – 7d
    ("Weeks", 168, 720),       # 7d – 30d
    ("Months+", 720, None),
]


def _extract_mint_and_timestamp(pool: dict) -> tuple[str | None, str | None]:
    """Extract (mint_address, pool_created_at) from a GeckoTerminal pool object."""
    relationships = pool.get("relationships") or {}
    base_token = (relationships.get("base_token") or {}).get("data") or {}
    token_id = base_token.get("id") or ""

    if token_id.startswith("solana_"):
        mint = token_id[len("solana_"):]
    else:
        mint = token_id

    if not mint:
        return None, None

    attrs = pool.get("attributes") or {}
    pool_created_at = attrs.get("pool_created_at")

    return mint, pool_created_at


async def _fetch_from_endpoint(
    client: httpx.AsyncClient,
    url: str,
    target: int,
    seen: set[str],
    label: str,
) -> list[tuple[str, str | None]]:
    """Fetch mints from a single GeckoTerminal endpoint with pagination.

    Returns list of (mint, pool_created_at_iso). Mutates `seen` set for dedup.
    """
    results: list[tuple[str, str | None]] = []
    page = 1
    max_pages = (target // 15) + 3  # ~20-30 per page, extra margin

    while len(results) < target and page <= max_pages:
        try:
            resp = await client.get(
                url,
                params={"page": page},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[{label}] Failed to fetch page {page}: {e}")
            break

        pools = data.get("data") or []
        if not pools:
            break

        for pool in pools:
            mint, created_at = _extract_mint_and_timestamp(pool)
            if mint and mint not in seen:
                seen.add(mint)
                results.append((mint, created_at))

        logger.info(
            f"[{label}] Page {page}: {len(pools)} pools, "
            f"{len(results)} unique mints so far"
        )
        page += 1
        await asyncio.sleep(0.5)

    return results[:target]


async def fetch_diverse_mints(
    target_count: int = 100,
) -> list[tuple[str, str | None]]:
    """Fetch tokens from 3 GeckoTerminal endpoints for age diversity.

    Returns list of (mint_address, pool_created_at_iso).
    Allocation: ~40% new_pools, ~40% top pools, ~20% trending.
    """
    n_new = round(target_count * 0.4)
    n_top = round(target_count * 0.4)
    n_trending = target_count - n_new - n_top

    seen: set[str] = set()
    all_mints: list[tuple[str, str | None]] = []

    base = "https://api.geckoterminal.com/api/v2/networks/solana"

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Fetch from all 3 endpoints sequentially to manage dedup via shared seen set
        new_mints = await _fetch_from_endpoint(
            client, f"{base}/new_pools", n_new, seen, "new_pools"
        )
        all_mints.extend(new_mints)
        logger.info(f"new_pools: {len(new_mints)} mints")

        top_mints = await _fetch_from_endpoint(
            client, f"{base}/pools", n_top, seen, "top_pools"
        )
        all_mints.extend(top_mints)
        logger.info(f"top_pools: {len(top_mints)} mints")

        trending_mints = await _fetch_from_endpoint(
            client, f"{base}/trending_pools", n_trending, seen, "trending"
        )
        all_mints.extend(trending_mints)
        logger.info(f"trending: {len(trending_mints)} mints")

    return all_mints[:target_count]


def classify_age_bracket(
    pool_created_at_iso: str | None,
) -> tuple[str, float | None]:
    """Classify a pool's age into a bracket.

    Returns (bracket_label, age_hours). Returns ("Unknown", None) for invalid input.
    """
    if not pool_created_at_iso:
        return "Unknown", None

    try:
        created = datetime.fromisoformat(pool_created_at_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - created).total_seconds() / 3600
    except (ValueError, TypeError):
        return "Unknown", None

    for label, min_h, max_h in AGE_BRACKETS:
        if max_h is None:
            if age_hours >= min_h:
                return label, round(age_hours, 1)
        elif min_h <= age_hours < max_h:
            return label, round(age_hours, 1)

    return "Unknown", round(age_hours, 1)


async def run_coverage(
    mints: list[tuple[str, str | None]], concurrency: int = 3
) -> list[dict]:
    """Run collector on all mints with concurrency control. Returns per-token results."""
    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    async def _collect_one(mint: str, pool_created_at: str | None, idx: int) -> dict:
        age_bracket, pool_age_hours = classify_age_bracket(pool_created_at)

        async with sem:
            t0 = time.perf_counter()
            try:
                result = await collect_features(mint)
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                entry = {
                    "mint": mint,
                    "age_bracket": age_bracket,
                    "pool_age_hours": pool_age_hours,
                    "features_collected": result.features_collected,
                    "features_total": len(result.features),
                    "coverage_pct": round(
                        result.features_collected / max(len(result.features), 1) * 100, 1
                    ),
                    "latency_ms": result.latency_ms,
                    "total_latency_ms": result.total_latency_ms,
                    "errors": result.errors,
                    "features": {
                        k: v is not None for k, v in result.features.items()
                    },
                    "source_coverage": {},
                }
                # Per-source coverage
                for source, feat_keys in SOURCE_FEATURES.items():
                    populated = sum(
                        1 for f in feat_keys if result.features.get(f) is not None
                    )
                    entry["source_coverage"][source] = {
                        "populated": populated,
                        "total": len(feat_keys),
                        "pct": round(populated / len(feat_keys) * 100, 1),
                    }
                logger.info(
                    f"[{idx + 1}/{len(mints)}] {mint[:8]}... "
                    f"[{age_bracket}] "
                    f"{result.features_collected}/{len(result.features)} features "
                    f"({elapsed:.0f}ms)"
                )
                return entry
            except Exception as e:
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                logger.error(f"[{idx + 1}/{len(mints)}] {mint[:8]}... FAILED: {e}")
                return {
                    "mint": mint,
                    "age_bracket": age_bracket,
                    "pool_age_hours": pool_age_hours,
                    "features_collected": 0,
                    "features_total": 81,
                    "coverage_pct": 0.0,
                    "latency_ms": {},
                    "total_latency_ms": elapsed,
                    "errors": [str(e)],
                    "features": {},
                    "source_coverage": {},
                    "failed": True,
                }

    tasks = [
        _collect_one(mint, created_at, i)
        for i, (mint, created_at) in enumerate(mints)
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


def compute_age_stats(results: list[dict]) -> dict:
    """Compute coverage statistics grouped by age bracket."""
    successful = [r for r in results if not r.get("failed")]

    # Group by bracket
    brackets: dict[str, list[dict]] = {}
    for r in successful:
        b = r.get("age_bracket", "Unknown")
        brackets.setdefault(b, []).append(r)

    age_stats = {}
    # Use canonical order from AGE_BRACKETS + Unknown
    bracket_order = [label for label, _, _ in AGE_BRACKETS] + ["Unknown"]

    for label in bracket_order:
        group = brackets.get(label)
        if not group:
            continue

        coverages = [r["coverage_pct"] for r in group]

        source_means = {}
        for source in SOURCE_FEATURES:
            source_covs = [
                r.get("source_coverage", {}).get(source, {}).get("pct", 0.0)
                for r in group
            ]
            source_means[source] = round(statistics.mean(source_covs), 1)

        age_stats[label] = {
            "count": len(group),
            "coverage_mean": round(statistics.mean(coverages), 1),
            "coverage_median": round(statistics.median(coverages), 1),
            "coverage_min": round(min(coverages), 1),
            "coverage_max": round(max(coverages), 1),
            "per_source_mean": source_means,
        }

    return age_stats


def compute_stats(results: list[dict]) -> dict:
    """Compute aggregate coverage statistics."""
    successful = [r for r in results if not r.get("failed")]
    failed = [r for r in results if r.get("failed")]

    if not successful:
        return {"error": "All tokens failed", "failed_count": len(failed)}

    # Overall coverage
    coverages = [r["coverage_pct"] for r in successful]

    # Per-source coverage (% of tokens with any data from that source)
    source_stats = {}
    for source in SOURCE_FEATURES:
        source_coverages = []
        for r in successful:
            sc = r.get("source_coverage", {}).get(source)
            if sc:
                source_coverages.append(sc["pct"])
            else:
                source_coverages.append(0.0)
        has_data = sum(1 for p in source_coverages if p > 0)
        source_stats[source] = {
            "tokens_with_data": has_data,
            "tokens_with_data_pct": round(has_data / len(successful) * 100, 1),
            "mean_coverage_pct": round(statistics.mean(source_coverages), 1),
            "median_coverage_pct": round(statistics.median(source_coverages), 1),
        }

    # Per-feature coverage (% of tokens where feature is non-None)
    feature_stats = {}
    for feat in ALL_FEATURES:
        populated = sum(1 for r in successful if r.get("features", {}).get(feat, False))
        feature_stats[feat] = {
            "populated_count": populated,
            "populated_pct": round(populated / len(successful) * 100, 1),
        }

    # Error aggregation
    error_counts: dict[str, int] = {}
    for r in results:
        for err in r.get("errors", []):
            source = err.split(":")[0] if ":" in err else "unknown"
            error_counts[source] = error_counts.get(source, 0) + 1

    # Latency stats
    latencies = [r["total_latency_ms"] for r in successful]

    # Age bracket stats
    per_age_bracket = compute_age_stats(results)

    return {
        "total_tokens": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "coverage": {
            "min": round(min(coverages), 1),
            "max": round(max(coverages), 1),
            "mean": round(statistics.mean(coverages), 1),
            "median": round(statistics.median(coverages), 1),
            "stdev": round(statistics.stdev(coverages), 1) if len(coverages) > 1 else 0.0,
        },
        "latency_ms": {
            "min": round(min(latencies), 0),
            "max": round(max(latencies), 0),
            "mean": round(statistics.mean(latencies), 0),
            "median": round(statistics.median(latencies), 0),
        },
        "per_source": source_stats,
        "per_feature": feature_stats,
        "per_age_bracket": per_age_bracket,
        "error_counts": error_counts,
    }


def print_age_report(stats: dict):
    """Print coverage breakdown by token age bracket."""
    age_data = stats.get("per_age_bracket")
    if not age_data:
        return

    # Short source labels for the table header
    source_labels = {
        "helius": "helius",
        "creator_wallet": "creator",
        "rugcheck": "rugchk",
        "geckoterminal": "gecko",
        "jupiter": "jupite",
        "derived": "derive",
    }

    print(f"\n  Coverage by Token Age")
    header = f"    {'Bracket':<10s} {'Count':>5s} {'Mean Cov':>9s}"
    for source in SOURCE_FEATURES:
        header += f" {source_labels.get(source, source[:6]):>8s}"
    print(header)
    print(f"    {'-' * (10 + 5 + 9 + 8 * len(SOURCE_FEATURES) + len(SOURCE_FEATURES))}")

    for bracket_label, bdata in age_data.items():
        row = (
            f"    {bracket_label:<10s} "
            f"{bdata['count']:>5d} "
            f"{bdata['coverage_mean']:>7.1f}%"
        )
        for source in SOURCE_FEATURES:
            pct = bdata["per_source_mean"].get(source, 0.0)
            row += f" {pct:>7.1f}%"
        print(row)


def print_report(stats: dict):
    """Print a formatted coverage report."""
    print(f"\n{'=' * 70}")
    print("  DeFi Sentinel — Feature Coverage Report")
    print(f"{'=' * 70}")

    print(f"\n  Tokens tested:  {stats['total_tokens']}")
    print(f"  Successful:     {stats['successful']}")
    print(f"  Failed:         {stats['failed']}")

    cov = stats["coverage"]
    print(f"\n  Overall Coverage")
    print(f"    Mean:   {cov['mean']:.1f}%")
    print(f"    Median: {cov['median']:.1f}%")
    print(f"    Min:    {cov['min']:.1f}%")
    print(f"    Max:    {cov['max']:.1f}%")
    print(f"    Stdev:  {cov['stdev']:.1f}%")

    lat = stats["latency_ms"]
    print(f"\n  Latency (per token)")
    print(f"    Mean:   {lat['mean']:.0f} ms")
    print(f"    Median: {lat['median']:.0f} ms")
    print(f"    Min:    {lat['min']:.0f} ms")
    print(f"    Max:    {lat['max']:.0f} ms")

    print(f"\n  Per-Source Coverage")
    print(f"    {'Source':<20s} {'Tokens w/ data':>14s} {'Mean Cov':>10s} {'Median':>10s}")
    print(f"    {'-' * 54}")
    for source, ss in stats["per_source"].items():
        print(
            f"    {source:<20s} "
            f"{ss['tokens_with_data']:>4d} ({ss['tokens_with_data_pct']:>5.1f}%) "
            f"{ss['mean_coverage_pct']:>8.1f}% "
            f"{ss['median_coverage_pct']:>8.1f}%"
        )

    # Age bracket report
    print_age_report(stats)

    # Features with <50% coverage (potential problems)
    low_cov = [
        (feat, fs)
        for feat, fs in stats["per_feature"].items()
        if fs["populated_pct"] < 50.0
    ]
    if low_cov:
        low_cov.sort(key=lambda x: x[1]["populated_pct"])
        print(f"\n  Low-Coverage Features (<50%)")
        print(f"    {'Feature':<35s} {'Coverage':>10s}")
        print(f"    {'-' * 45}")
        for feat, fs in low_cov:
            print(f"    {feat:<35s} {fs['populated_pct']:>8.1f}%")

    # Features with 100% coverage
    full_cov = [
        feat for feat, fs in stats["per_feature"].items()
        if fs["populated_pct"] == 100.0
    ]
    if full_cov:
        print(f"\n  Perfect Coverage (100%): {len(full_cov)} features")

    if stats["error_counts"]:
        print(f"\n  Error Counts by Source")
        for source, count in sorted(stats["error_counts"].items(), key=lambda x: -x[1]):
            print(f"    {source}: {count}")

    print(f"\n{'=' * 70}\n")


async def main_async(count: int, concurrency: int):
    start = time.perf_counter()

    # Step 1: Fetch diverse-age mints
    print(f"Fetching ~{count} diverse-age tokens from GeckoTerminal...")
    mints = await fetch_diverse_mints(target_count=count)
    print(f"Got {len(mints)} unique mints")

    if not mints:
        print("ERROR: No mints fetched. Check network connectivity.")
        sys.exit(1)

    # Print age distribution preview
    bracket_counts: dict[str, int] = {}
    for _, created_at in mints:
        bracket, _ = classify_age_bracket(created_at)
        bracket_counts[bracket] = bracket_counts.get(bracket, 0) + 1

    print(f"\n  Age distribution:")
    for label, _, _ in AGE_BRACKETS:
        c = bracket_counts.get(label, 0)
        if c:
            print(f"    {label:<10s} {c:>4d} tokens")
    unknown = bracket_counts.get("Unknown", 0)
    if unknown:
        print(f"    {'Unknown':<10s} {unknown:>4d} tokens")

    # Step 2: Run collector
    print(f"\nRunning collector on {len(mints)} tokens (concurrency={concurrency})...")
    results = await run_coverage(mints, concurrency=concurrency)

    # Step 3: Compute stats
    stats = compute_stats(results)

    # Step 4: Output
    print_report(stats)

    elapsed = round(time.perf_counter() - start, 1)
    print(f"  Total runtime: {elapsed}s\n")

    # Save full results
    output_path = Path(__file__).resolve().parent / "coverage_results.json"

    # Build source info for metadata
    sources = {
        "new_pools": round(count * 0.4),
        "top_pools": round(count * 0.4),
        "trending": count - round(count * 0.4) - round(count * 0.4),
    }

    output = {
        "meta": {
            "token_count": len(mints),
            "concurrency": concurrency,
            "runtime_seconds": elapsed,
            "age_distribution": bracket_counts,
            "sources": sources,
        },
        "stats": stats,
        "results": results,
    }
    output_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"  Full results saved to: {output_path}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Coverage test: collect features for ~100 diverse-age Solana tokens"
    )
    parser.add_argument(
        "--count", type=int, default=100,
        help="Number of tokens to test (default: 100)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help="Max concurrent token collections (default: 3)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    asyncio.run(main_async(args.count, args.concurrency))


if __name__ == "__main__":
    main()
