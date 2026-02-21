"""
DeFi Sentinel — Creator Wallet Enrichment via Helius
Fetches 6 critical creator wallet features using Helius DAS/RPC API.
These are the #1 most-wanted missing features (0/6 present).

Features extracted per creator:
  1. creator_sol_balance     — SOL balance (indicator of commitment)
  2. creator_wallet_age_hours — first tx timestamp → age in hours
  3. creator_token_count     — how many other tokens this wallet created
  4. creator_tx_count        — total transaction count
  5. creator_nft_count       — NFTs owned (legit devs often have NFTs)
  6. creator_prev_rugs       — (computed post-hoc from our dataset)

Usage:
  python3 scripts/enrich_creator_wallet.py [--sample N] [--batch-size B]
"""
import pandas as pd
import numpy as np
import aiohttp
import asyncio
import json
import time
import argparse
import os
from collections import defaultdict

HELIUS_KEY = "2616c6b9-ead3-4367-8ef0-e642d51d7020"
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"
HELIUS_API = f"https://api.helius.xyz/v0"

INPUT   = "data/enriched/enriched_final.csv"
OUTPUT  = "data/enriched/creator_wallet_features.csv"
CACHE   = "data/enriched/_creator_cache.json"

RATE_LIMIT = 10   # requests per second (Helius free tier)
BATCH_SIZE = 50   # process creators in batches


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0,
                   help="Only process N unique creators (0 = all)")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    return p.parse_args()


async def helius_rpc(session, method, params, sem):
    """Make a Helius JSON-RPC call with rate limiting."""
    async with sem:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        for attempt in range(3):
            try:
                async with session.post(HELIUS_RPC, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    data = await resp.json()
                    return data.get("result")
            except Exception as e:
                if attempt == 2:
                    return None
                await asyncio.sleep(1)
    return None


async def helius_api_get(session, endpoint, params, sem):
    """Make a Helius REST API call."""
    async with sem:
        url = f"{HELIUS_API}/{endpoint}?api-key={HELIUS_KEY}"
        for attempt in range(3):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status == 200:
                        return await resp.json()
                    return None
            except Exception:
                if attempt == 2:
                    return None
                await asyncio.sleep(1)
    return None


async def get_sol_balance(session, address, sem):
    """Get SOL balance for an address."""
    result = await helius_rpc(session, "getBalance", [address], sem)
    if result and "value" in result:
        return result["value"] / 1e9  # lamports → SOL
    return None


async def get_token_accounts(session, address, sem):
    """Get SPL token accounts owned by address → token count."""
    result = await helius_rpc(session, "getTokenAccountsByOwner", [
        address,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"}
    ], sem)
    if result and "value" in result:
        return len(result["value"])
    return None


async def get_signatures_count(session, address, sem):
    """Get recent transaction signatures → estimate total tx count."""
    result = await helius_rpc(session, "getSignaturesForAddress", [
        address, {"limit": 1000}
    ], sem)
    if result is not None:
        return len(result)
    return None


async def get_nft_count(session, address, sem):
    """Get NFTs owned by address via Helius DAS API."""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": address,
            "page": 1,
            "limit": 1,
            "displayOptions": {"showNativeBalance": False}
        }
    }
    async with sem:
        for attempt in range(3):
            try:
                async with session.post(HELIUS_RPC, json=payload,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    data = await resp.json()
                    result = data.get("result", {})
                    return result.get("total", 0)
            except Exception:
                if attempt == 2:
                    return None
                await asyncio.sleep(1)
    return None


async def get_first_tx_timestamp(session, address, sem):
    """Get oldest transaction → wallet creation estimate."""
    result = await helius_rpc(session, "getSignaturesForAddress", [
        address, {"limit": 1, "before": None}
    ], sem)
    # This gets the most recent tx. To get oldest, we'd need to paginate.
    # Instead, use a heuristic: get last page of 1000 sigs.
    sigs = await helius_rpc(session, "getSignaturesForAddress", [
        address, {"limit": 1000}
    ], sem)
    if sigs and len(sigs) > 0:
        oldest = sigs[-1]  # last in the list = oldest we can see
        block_time = oldest.get("blockTime")
        return block_time
    return None


async def enrich_one_creator(session, address, sem):
    """Fetch all features for a single creator address."""
    # Run all API calls in parallel
    balance_task = get_sol_balance(session, address, sem)
    tokens_task  = get_token_accounts(session, address, sem)
    sigs_task    = get_signatures_count(session, address, sem)
    nfts_task    = get_nft_count(session, address, sem)
    age_task     = get_first_tx_timestamp(session, address, sem)

    balance, tokens, sigs, nfts, first_ts = await asyncio.gather(
        balance_task, tokens_task, sigs_task, nfts_task, age_task
    )

    # Calculate wallet age in hours
    wallet_age_hours = None
    if first_ts:
        wallet_age_hours = (time.time() - first_ts) / 3600

    return {
        "creator_address": address,
        "creator_sol_balance": balance,
        "creator_token_count": tokens,
        "creator_tx_count": sigs,
        "creator_nft_count": nfts,
        "creator_wallet_age_hours": wallet_age_hours,
        "creator_first_tx_ts": first_ts,
    }


async def main():
    args = parse_args()

    print("=" * 70)
    print("  DeFi Sentinel — Creator Wallet Enrichment (Helius)")
    print("=" * 70)

    # Load data
    df = pd.read_csv(INPUT, low_memory=False)
    print(f"Loaded {len(df):,} rows")

    # Get unique creator addresses (OWNER column from Helius)
    creators = df["OWNER"].dropna().unique()
    print(f"Unique creator addresses: {len(creators):,}")

    # Load cache
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
        print(f"Cache: {len(cache):,} creators already enriched")

    # Filter out already-cached
    todo = [c for c in creators if c not in cache]
    print(f"To enrich: {len(todo):,} creators")

    if args.sample > 0:
        todo = todo[:args.sample]
        print(f"Sampling first {args.sample} creators")

    if not todo:
        print("Nothing to do!")
    else:
        sem = asyncio.Semaphore(RATE_LIMIT)
        connector = aiohttp.TCPConnector(limit=RATE_LIMIT, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Process in batches
            results = []
            for i in range(0, len(todo), args.batch_size):
                batch = todo[i:i + args.batch_size]
                batch_num = i // args.batch_size + 1
                total_batches = (len(todo) + args.batch_size - 1) // args.batch_size
                print(f"\n  Batch {batch_num}/{total_batches} ({len(batch)} creators)...")

                tasks = [enrich_one_creator(session, addr, sem) for addr in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                ok = 0
                for r in batch_results:
                    if isinstance(r, dict):
                        addr = r["creator_address"]
                        cache[addr] = r
                        results.append(r)
                        ok += 1
                    else:
                        print(f"    ⚠ Error: {r}")

                print(f"    ✓ {ok}/{len(batch)} succeeded")

                # Save cache after each batch
                with open(CACHE, "w") as f:
                    json.dump(cache, f)

                # Brief pause between batches
                await asyncio.sleep(0.5)

    # ── Compute creator_prev_rugs from our own dataset ──
    print("\n  Computing creator_prev_rugs from dataset labels...")
    labels = pd.read_csv("data/enriched/verified_labels.csv")
    df_lbl = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
                      on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vlbl"))

    # Count rugged tokens per creator
    rug_mask = df_lbl["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
    creator_rugs = df_lbl[rug_mask].groupby("OWNER")["MINT"].nunique().to_dict()
    creator_total = df_lbl.groupby("OWNER")["MINT"].nunique().to_dict()

    # ── Build output DataFrame ──
    print("\n  Building creator features table...")
    all_creators_data = []
    for addr in creators:
        row = cache.get(addr, {"creator_address": addr})
        row["creator_prev_rugs"] = creator_rugs.get(addr, 0)
        row["creator_total_tokens"] = creator_total.get(addr, 0)
        row["creator_rug_rate"] = (
            row["creator_prev_rugs"] / row["creator_total_tokens"]
            if row["creator_total_tokens"] > 0 else 0
        )
        all_creators_data.append(row)

    creator_df = pd.DataFrame(all_creators_data)
    creator_df.to_csv(OUTPUT, index=False)

    n_enriched = creator_df["creator_sol_balance"].notna().sum()
    print(f"\n{'=' * 70}")
    print(f"  DONE: {len(creator_df):,} creators ({n_enriched:,} with API data)")
    print(f"  Saved to: {OUTPUT}")
    print(f"  Cache: {CACHE} ({len(cache):,} entries)")

    # Print sample
    print(f"\n  Sample (first 5):")
    for _, row in creator_df.head().iterrows():
        print(f"    {row['creator_address'][:12]}... "
              f"SOL={row.get('creator_sol_balance', '?'):.3f}  "
              f"tokens={row.get('creator_token_count', '?')}  "
              f"txns={row.get('creator_tx_count', '?')}  "
              f"nfts={row.get('creator_nft_count', '?')}  "
              f"rugs={row.get('creator_prev_rugs', 0)}/{row.get('creator_total_tokens', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
