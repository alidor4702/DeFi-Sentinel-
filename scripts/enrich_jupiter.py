"""
DeFi Sentinel — Jupiter Price Enrichment
Fetches price data from Jupiter Aggregator API (free, no key needed).

Features extracted:
  1. jup_price_usd        — current price in USD
  2. jup_price_vs_sol     — price relative to SOL
  3. jup_confidence       — price confidence level
  4. jup_has_price        — whether Jupiter has a price quote (binary)
  5. jup_mint_listed      — whether Jupiter recognizes the token

Jupiter Price API:
  GET https://api.jup.ag/price/v2?ids=<mint1>,<mint2>,...
  - Free, no API key needed
  - Up to 100 mints per request
  - Fast (~100ms per batch)

Usage:
  python3 scripts/enrich_jupiter.py [--sample N]
"""
import pandas as pd
import numpy as np
import aiohttp
import asyncio
import json
import time
import argparse
import os

JUP_PRICE_URL = "https://api.jup.ag/price/v2"
JUP_TOKEN_LIST = "https://tokens.jup.ag/tokens?tags=verified,community"

INPUT  = "data/enriched/enriched_final.csv"
OUTPUT = "data/enriched/jupiter_enriched.csv"
CACHE  = "data/enriched/_jupiter_cache.json"

BATCH_SIZE = 100  # max mints per Jupiter request
CONCURRENT = 3


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0, help="Limit to N mints (0=all)")
    return p.parse_args()


async def fetch_jupiter_prices(session, mints, sem):
    """Fetch prices for up to 100 mints from Jupiter."""
    async with sem:
        ids_param = ",".join(mints)
        params = {"ids": ids_param, "showExtraInfo": "true"}
        for attempt in range(3):
            try:
                async with session.get(JUP_PRICE_URL, params=params,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("data", {})
                    return {}
            except Exception as e:
                if attempt == 2:
                    print(f"      Jupiter error: {e}")
                    return {}
                await asyncio.sleep(1)
    return {}


async def fetch_jupiter_token_list(session):
    """Fetch the Jupiter verified/community token list."""
    try:
        async with session.get(JUP_TOKEN_LIST, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                tokens = await resp.json()
                return {t["address"]: t for t in tokens}
    except Exception as e:
        print(f"  ⚠ Could not fetch Jupiter token list: {e}")
    return {}


def parse_jupiter_result(mint, price_data, token_list):
    """Extract features from Jupiter response."""
    listed = mint in token_list
    has_price = price_data is not None and price_data.get("price") is not None

    result = {
        "MINT": mint,
        "jup_mint_listed": int(listed),
        "jup_has_price": int(has_price),
        "jup_price_usd": None,
        "jup_confidence": None,
    }

    if has_price:
        try:
            result["jup_price_usd"] = float(price_data["price"])
        except (ValueError, TypeError):
            pass

        # Extra info
        extra = price_data.get("extraInfo", {})
        if extra:
            conf = extra.get("confidenceLevel")
            result["jup_confidence"] = conf

            # Depth info
            depth = extra.get("depth", {})
            if depth:
                result["jup_buy_depth_10"] = depth.get("buyPriceImpactRatio", {}).get("depth", {}).get("10")
                result["jup_sell_depth_10"] = depth.get("sellPriceImpactRatio", {}).get("depth", {}).get("10")

            # Quote timestamps
            qt = extra.get("quotedPrice", {})
            if qt:
                result["jup_buy_price"] = safe_float(qt.get("buyPrice"))
                result["jup_sell_price"] = safe_float(qt.get("sellPrice"))

    # From token list
    if listed:
        tok = token_list[mint]
        result["jup_daily_volume"] = safe_float(tok.get("daily_volume"))
        result["jup_freeze_authority_present"] = int(tok.get("freeze_authority") is not None)
        result["jup_mint_authority_present"] = int(tok.get("mint_authority") is not None)

    return result


def safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except:
        return None


async def main():
    args = parse_args()

    print("=" * 70)
    print("  DeFi Sentinel — Jupiter Price Enrichment")
    print("=" * 70)

    df = pd.read_csv(INPUT, low_memory=False)
    mints = df["MINT"].dropna().unique().tolist()
    print(f"Loaded {len(df):,} rows, {len(mints):,} unique mints")

    # Load cache
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
        print(f"Cache: {len(cache):,} mints already fetched")

    todo = [m for m in mints if m not in cache]

    if args.sample > 0:
        todo = todo[:args.sample]
    print(f"To fetch: {len(todo):,} mints")

    sem = asyncio.Semaphore(CONCURRENT)
    connector = aiohttp.TCPConnector(limit=CONCURRENT * 2)

    async with aiohttp.ClientSession(connector=connector) as session:
        # Fetch token list
        print("  Fetching Jupiter token list...")
        token_list = await fetch_jupiter_token_list(session)
        print(f"  Jupiter knows {len(token_list):,} tokens")

        # Fetch prices in batches
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"    Batch {batch_num}/{total_batches} ({len(batch)} mints)...", end="")

            price_data = await fetch_jupiter_prices(session, batch, sem)

            ok = 0
            for mint in batch:
                mint_price = price_data.get(mint)
                parsed = parse_jupiter_result(mint, mint_price, token_list)
                cache[mint] = parsed
                if parsed.get("jup_has_price"):
                    ok += 1

            print(f" ✓ {ok}/{len(batch)} have prices")

            # Save cache
            with open(CACHE, "w") as f:
                json.dump(cache, f)

            await asyncio.sleep(0.5)

    # Build output
    rows = [v for v in cache.values() if isinstance(v, dict)]
    jup_df = pd.DataFrame(rows)
    jup_df.to_csv(OUTPUT, index=False)

    n_priced = jup_df["jup_has_price"].sum() if "jup_has_price" in jup_df.columns else 0
    n_listed = jup_df["jup_mint_listed"].sum() if "jup_mint_listed" in jup_df.columns else 0

    print(f"\n{'=' * 70}")
    print(f"  DONE: {len(jup_df):,} mints processed")
    print(f"  With price: {int(n_priced):,}")
    print(f"  Jupiter-listed: {int(n_listed):,}")
    print(f"  Saved to: {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
