"""
DeFi Sentinel — Batch GoPlus + RugCheck Enrichment (v2)
Enriches ALL unique mints with GoPlus and RugCheck data.
Previous runs only got ~48 rugs and ~4000 legit. We need THOUSANDS more,
especially for rug tokens where GoPlus/RugCheck data is sparse.

Strategy:
  - Prioritize tokens that are labeled (rugs first, then legit)
  - Use async parallel requests with proper rate limiting
  - Cache results to disk after each batch (crash-safe)
  - GoPlus: POST /v1/solana/token_security (batch up to 100 addresses)
  - RugCheck: GET /v1/tokens/{mint}/report (one at a time, fast)

Usage:
  python3 scripts/enrich_goplus_rugcheck_batch.py [--sample N] [--skip-goplus] [--skip-rugcheck]
"""
import pandas as pd
import numpy as np
import aiohttp
import asyncio
import json
import time
import argparse
import os

HELIUS_KEY = "2616c6b9-ead3-4367-8ef0-e642d51d7020"

GOPLUS_URL   = "https://api.gopluslabs.com/api/v1/solana/token_security"
RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens"

INPUT  = "data/enriched/enriched_final.csv"
GP_CACHE  = "data/enriched/_goplus_cache.json"
RC_CACHE  = "data/enriched/_rugcheck_cache.json"
GP_OUTPUT = "data/enriched/goplus_enriched.csv"
RC_OUTPUT = "data/enriched/rugcheck_enriched.csv"

# Rate limits
GP_CONCURRENT = 5    # GoPlus allows ~5 req/s
RC_CONCURRENT = 10   # RugCheck is generous
GP_BATCH_SIZE = 50   # addresses per GoPlus request (max 100)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0, help="Limit to N mints (0=all)")
    p.add_argument("--skip-goplus", action="store_true")
    p.add_argument("--skip-rugcheck", action="store_true")
    return p.parse_args()


def prioritize_mints(df, labels_df):
    """Sort mints: VERIFIED_RUG first, then LIKELY_RUG, then LIKELY_LEGIT, then rest."""
    merged = df.merge(labels_df[["MINT", "RUG_LABEL"]].drop_duplicates("MINT"),
                      on="MINT", how="left", suffixes=("", "_lbl"))
    unique = merged.drop_duplicates("MINT")[["MINT", "RUG_LABEL"]]

    priority = {"VERIFIED_RUG": 0, "LIKELY_RUG": 1, "SUSPICIOUS": 2,
                "LIKELY_LEGIT": 3, "UNCERTAIN": 4}
    unique["_priority"] = unique["RUG_LABEL"].map(priority).fillna(5)
    unique = unique.sort_values("_priority")
    return unique["MINT"].tolist()


# ═══════════════════════════════════════════════════════════════
# GOPLUS ENRICHMENT
# ═══════════════════════════════════════════════════════════════

def parse_goplus_result(mint, data):
    """Extract structured features from GoPlus response for one token."""
    if not data:
        return None

    return {
        "MINT": mint,
        "gp_token_name": data.get("token_name"),
        "gp_token_symbol": data.get("token_symbol"),
        "gp_holder_count": safe_int(data.get("holder_count")),
        "gp_total_tvl": safe_float(data.get("tvl")),
        "gp_top3_holder_pct": None,  # compute from holders
        "gp_creator_pct": safe_float(data.get("creator_percent")),
        "gp_lp_count": safe_int(data.get("lp_count")),
        "gp_lp_holders_total": safe_int(data.get("lp_holders_total")),
        "gp_lp_locked_count": safe_int(data.get("lp_locked_count")),
        "gp_closable": safe_int(data.get("closable")),
        "gp_balance_mutable": safe_int(data.get("balance_mutable_authority")),
        "gp_freeze_authority": data.get("freeze_authority"),
        "gp_transfer_fee": safe_float(data.get("transfer_fee")),
        "gp_default_account_state": safe_int(data.get("default_account_state")),
        "gp_non_transferable": safe_int(data.get("non_transferable")),
        # NEW fields not in original enrichment
        "gp_is_open_source": safe_int(data.get("is_open_source")),
        "gp_is_proxy": safe_int(data.get("is_proxy")),
        "gp_is_mintable": safe_int(data.get("is_mintable")),
        "gp_can_take_back_ownership": safe_int(data.get("can_take_back_ownership")),
        "gp_owner_change_balance": safe_int(data.get("owner_change_balance")),
        "gp_selfdestruct": safe_int(data.get("selfdestruct")),
        "gp_is_true_token": safe_int(data.get("is_true_token")),
        "gp_is_airdrop_scam": safe_int(data.get("is_airdrop_scam")),
    }


def safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except:
            return None


async def fetch_goplus_batch(session, mints, sem):
    """Fetch GoPlus data for a batch of mints (up to 100)."""
    async with sem:
        addresses = ",".join(mints)
        params = {"contract_addresses": addresses}
        for attempt in range(3):
            try:
                async with session.get(GOPLUS_URL, params=params,
                                       timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 429:
                        wait = 5 * (attempt + 1)
                        print(f"      GoPlus 429, waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", {})
                    return {}
            except Exception as e:
                if attempt == 2:
                    print(f"      GoPlus error: {e}")
                    return {}
                await asyncio.sleep(2)
    return {}


async def run_goplus(mints, cache):
    """Run GoPlus enrichment for all mints."""
    todo = [m for m in mints if m not in cache]
    print(f"\n  GoPlus: {len(mints):,} total, {len(cache):,} cached, {len(todo):,} to fetch")

    if not todo:
        return cache

    sem = asyncio.Semaphore(GP_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=GP_CONCURRENT * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, len(todo), GP_BATCH_SIZE):
            batch = todo[i:i + GP_BATCH_SIZE]
            batch_num = i // GP_BATCH_SIZE + 1
            total_batches = (len(todo) + GP_BATCH_SIZE - 1) // GP_BATCH_SIZE
            print(f"    GoPlus batch {batch_num}/{total_batches} ({len(batch)} mints)...", end="")

            result = await fetch_goplus_batch(session, batch, sem)

            ok = 0
            for mint in batch:
                mint_data = result.get(mint.lower()) or result.get(mint)
                parsed = parse_goplus_result(mint, mint_data)
                cache[mint] = parsed if parsed else {"MINT": mint, "_empty": True}
                if parsed:
                    ok += 1

            print(f" ✓ {ok}/{len(batch)} with data")

            # Save cache
            with open(GP_CACHE, "w") as f:
                json.dump(cache, f)

            await asyncio.sleep(1.2)  # rate limit

    return cache


# ═══════════════════════════════════════════════════════════════
# RUGCHECK ENRICHMENT
# ═══════════════════════════════════════════════════════════════

def parse_rugcheck_result(mint, data):
    """Extract structured features from RugCheck response."""
    if not data or "error" in data:
        return None

    risks = data.get("risks", [])
    risk_names = [r.get("name", "") for r in risks]
    risk_levels = [r.get("level", "") for r in risks]
    risk_scores = [r.get("score", 0) for r in risks]

    # Top holder concentration
    top_holders = data.get("topHolders", [])
    top10_pct = sum(h.get("pct", 0) for h in top_holders[:10]) if top_holders else None
    top1_pct = top_holders[0].get("pct", 0) if top_holders else None

    # LP info
    markets = data.get("markets", [])
    total_liq = sum(m.get("lp", {}).get("lpLockedUSD", 0) + m.get("lp", {}).get("lpUnlockedUSD", 0)
                    for m in markets) if markets else None
    lp_locked = any(m.get("lp", {}).get("lpLocked", False) for m in markets) if markets else None
    lp_burned = any(m.get("lp", {}).get("lpBurned", False) for m in markets) if markets else None
    lp_lock_pct = max((m.get("lp", {}).get("lpLockedPct", 0) for m in markets), default=0) if markets else None

    return {
        "MINT": mint,
        "rc_score": data.get("score"),
        "rc_score_norm": data.get("score", 0) / 100000 if data.get("score") else None,
        "rc_risks_count": len(risks),
        "rc_top_risk": risk_names[0] if risk_names else None,
        "rc_top_risk_level": risk_levels[0] if risk_levels else None,
        "rc_top_risk_score": risk_scores[0] if risk_scores else None,
        "rc_risk_names": "|".join(risk_names) if risk_names else None,
        "rc_num_dangers": sum(1 for l in risk_levels if l == "danger"),
        "rc_num_warns": sum(1 for l in risk_levels if l == "warn"),
        "rc_top10_holder_pct": top10_pct,
        "rc_top1_holder_pct": top1_pct,
        "rc_total_market_liq": total_liq,
        "rc_total_holders": data.get("totalHolders"),
        "rc_total_lp_providers": data.get("totalLpProviders"),
        "rc_mint_authority": 1 if data.get("mintAuthority") else 0,
        "rc_freeze_authority": 1 if data.get("freezeAuthority") else 0,
        "rc_mutable_metadata": 1 if data.get("mutableMetadata") else 0,
        # NEW fields
        "rc_lp_locked": int(lp_locked) if lp_locked is not None else None,
        "rc_lp_burned": int(lp_burned) if lp_burned is not None else None,
        "rc_lp_lock_pct": lp_lock_pct,
        "rc_creator_pct": top_holders[0].get("pct") if top_holders and top_holders[0].get("insider") else None,
        "rc_rugged": 1 if data.get("rugged") else 0,
        "rc_token_type": data.get("tokenType"),
    }


async def fetch_rugcheck(session, mint, sem):
    """Fetch RugCheck report for a single mint."""
    async with sem:
        url = f"{RUGCHECK_URL}/{mint}/report"
        for attempt in range(3):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status == 200:
                        return await resp.json()
                    return None
            except Exception:
                if attempt == 2:
                    return None
                await asyncio.sleep(0.5)
    return None


async def run_rugcheck(mints, cache):
    """Run RugCheck enrichment for all mints."""
    todo = [m for m in mints if m not in cache]
    print(f"\n  RugCheck: {len(mints):,} total, {len(cache):,} cached, {len(todo):,} to fetch")

    if not todo:
        return cache

    sem = asyncio.Semaphore(RC_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=RC_CONCURRENT * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        batch_size = 200
        for i in range(0, len(todo), batch_size):
            batch = todo[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(todo) + batch_size - 1) // batch_size
            print(f"    RugCheck batch {batch_num}/{total_batches} ({len(batch)} mints)...", end="")

            tasks = [fetch_rugcheck(session, m, sem) for m in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            ok = 0
            for mint, result in zip(batch, results):
                if isinstance(result, dict) and "error" not in result:
                    parsed = parse_rugcheck_result(mint, result)
                    cache[mint] = parsed if parsed else {"MINT": mint, "_empty": True}
                    if parsed:
                        ok += 1
                else:
                    cache[mint] = {"MINT": mint, "_empty": True}

            print(f" ✓ {ok}/{len(batch)} with data")

            # Save cache
            with open(RC_CACHE, "w") as f:
                json.dump(cache, f)

            await asyncio.sleep(0.3)

    return cache


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    args = parse_args()

    print("=" * 70)
    print("  DeFi Sentinel — Batch GoPlus + RugCheck Enrichment (v2)")
    print("=" * 70)

    df = pd.read_csv(INPUT, low_memory=False)
    labels = pd.read_csv("data/enriched/verified_labels.csv")
    print(f"Loaded {len(df):,} rows, {df['MINT'].nunique():,} unique mints")

    # Prioritize: rugs first
    mints = prioritize_mints(df, labels)
    print(f"Prioritized mint list: {len(mints):,} mints (rugs first)")

    if args.sample > 0:
        mints = mints[:args.sample]
        print(f"Sampling first {args.sample} mints")

    # Load caches
    gp_cache = {}
    if os.path.exists(GP_CACHE):
        with open(GP_CACHE) as f:
            gp_cache = json.load(f)

    rc_cache = {}
    if os.path.exists(RC_CACHE):
        with open(RC_CACHE) as f:
            rc_cache = json.load(f)

    # ── GoPlus ──
    if not args.skip_goplus:
        gp_cache = await run_goplus(mints, gp_cache)

        # Build output
        gp_rows = [v for v in gp_cache.values() if isinstance(v, dict) and not v.get("_empty")]
        if gp_rows:
            gp_df = pd.DataFrame(gp_rows)
            gp_df.to_csv(GP_OUTPUT, index=False)
            print(f"  GoPlus output: {len(gp_df):,} tokens → {GP_OUTPUT}")

    # ── RugCheck ──
    if not args.skip_rugcheck:
        rc_cache = await run_rugcheck(mints, rc_cache)

        # Build output
        rc_rows = [v for v in rc_cache.values() if isinstance(v, dict) and not v.get("_empty")]
        if rc_rows:
            rc_df = pd.DataFrame(rc_rows)
            rc_df.to_csv(RC_OUTPUT, index=False)
            print(f"  RugCheck output: {len(rc_df):,} tokens → {RC_OUTPUT}")

    print(f"\n{'=' * 70}")
    print(f"  DONE!")
    print(f"  GoPlus cache: {len(gp_cache):,} | RugCheck cache: {len(rc_cache):,}")


if __name__ == "__main__":
    asyncio.run(main())
