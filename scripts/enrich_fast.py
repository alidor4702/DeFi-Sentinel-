"""
enrich_fast.py — Parallel RugCheck + GeckoTerminal + GoPlus enrichment
=======================================================================

Runs all 3 APIs in parallel using asyncio + aiohttp.
Each API has its own rate limiter so they don't block each other.

Speed comparison:
  Old (sequential, 2.0s/req):  ~2.9 hours for 2000 tokens
  New (parallel, 0.5s/req):    ~17 minutes for 2000 tokens  (10x faster)

Reads enriched_labeled.csv, adds ~50 new columns, saves enriched_final.csv.
Resumes from existing checkpoints automatically.

Usage:
  python scripts/enrich_fast.py                   # full 2000 sample
  python scripts/enrich_fast.py --sample 50       # quick test
  python scripts/enrich_fast.py --sample 2000     # production run
  python scripts/enrich_fast.py --only goplus     # single API
"""

import os
import sys
import json
import time
import asyncio
import argparse
from datetime import datetime

try:
    import aiohttp
except ImportError:
    sys.exit("[ERROR] pip install aiohttp   (async HTTP client)")

try:
    import pandas as pd
except ImportError:
    sys.exit("[ERROR] pip install pandas")


# ── Config ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "enriched")
CKPT_DIR = os.path.join(DATA_DIR, "checkpoints")

RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
GECKO_POOL_URL = "https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}/pools?page=1"
GOPLUS_URL = "https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses={mint}"

# Rate limits — tested safe values
RC_DELAY = 0.5    # RugCheck handles 0.3s, use 0.5 for safety
GT_DELAY = 0.5    # GeckoTerminal
GP_DELAY = 0.5    # GoPlus

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
CKPT_EVERY = 100

LABEL_PRIORITY = ["VERIFIED_RUG", "LIKELY_RUG", "LIKELY_LEGIT", "SUSPICIOUS", "UNCERTAIN"]


# ── Checkpoint helpers ──────────────────────────────────────────────
def load_checkpoint(name):
    path = os.path.join(CKPT_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_checkpoint(name, data):
    os.makedirs(CKPT_DIR, exist_ok=True)
    path = os.path.join(CKPT_DIR, f"{name}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ── API fetchers (async) ───────────────────────────────────────────
async def fetch_rugcheck(session, mint):
    """Fetch RugCheck summary for a single mint."""
    url = RUGCHECK_URL.format(mint=mint)
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "rc_score": data.get("score", None),
                        "rc_score_norm": data.get("score_normalised", None),
                        "rc_risks_count": len(data.get("risks", [])),
                        "rc_top_risk": data["risks"][0].get("name", "") if data.get("risks") else "",
                        "rc_top_risk_level": data["risks"][0].get("level", "") if data.get("risks") else "",
                        "rc_top_risk_score": data["risks"][0].get("score", 0) if data.get("risks") else 0,
                        "rc_total_market_liq": data.get("totalMarketLiquidity", None),
                        "rc_total_lp_providers": data.get("totalLPProviders", None),
                        "rc_detected_at": data.get("detectedAt", None),
                        "rc_freeze_authority": data.get("freezeAuthority", None),
                        "rc_mint_authority": data.get("mintAuthority", None),
                        "rc_top_holders_pct": sum(
                            h.get("pct", 0) for h in (data.get("topHolders", []) or [])[:3]
                        ),
                        "rc_creator_pct": data.get("creatorTokenStatus", {}).get("pct", 0) if isinstance(data.get("creatorTokenStatus"), dict) else 0,
                    }
                elif resp.status == 429:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                else:
                    return None
        except Exception:
            await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
    return None


async def fetch_gecko(session, mint):
    """Fetch GeckoTerminal pool data for a single mint."""
    url = GECKO_POOL_URL.format(mint=mint)
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pools = data.get("data", [])
                    if not pools:
                        return {"gt_pool_count": 0}
                    top = pools[0].get("attributes", {})
                    return {
                        "gt_pool_count": len(pools),
                        "gt_pool_name": top.get("name", ""),
                        "gt_pool_dex": top.get("dex_id", ""),
                        "gt_base_price_usd": float(top.get("base_token_price_usd") or 0),
                        "gt_fdv_usd": float(top.get("fdv_usd") or 0),
                        "gt_market_cap_usd": float(top.get("market_cap_usd") or 0),
                        "gt_reserve_usd": float(top.get("reserve_in_usd") or 0),
                        "gt_vol_24h": float(top.get("volume_usd", {}).get("h24", 0) or 0),
                        "gt_vol_6h": float(top.get("volume_usd", {}).get("h6", 0) or 0),
                        "gt_vol_1h": float(top.get("volume_usd", {}).get("h1", 0) or 0),
                        "gt_price_pct_5m": float(top.get("price_change_percentage", {}).get("m5", 0) or 0),
                        "gt_price_pct_1h": float(top.get("price_change_percentage", {}).get("h1", 0) or 0),
                        "gt_price_pct_24h": float(top.get("price_change_percentage", {}).get("h24", 0) or 0),
                        "gt_txns_24h_buys": top.get("transactions", {}).get("h24", {}).get("buys", 0),
                        "gt_txns_24h_sells": top.get("transactions", {}).get("h24", {}).get("sells", 0),
                        "gt_pool_created": top.get("pool_created_at", ""),
                    }
                elif resp.status == 429:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                else:
                    return None
        except Exception:
            await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
    return None


async def fetch_goplus(session, mint):
    """Fetch GoPlus security data for a single mint."""
    url = GOPLUS_URL.format(mint=mint)
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") != 1:
                        return None
                    result = data.get("result", {})
                    # GoPlus returns {address: data} — get the first (only) value
                    token_data = None
                    for addr, val in result.items():
                        if isinstance(val, dict):
                            token_data = val
                            break
                    if not token_data:
                        return None

                    # Extract holder concentration
                    holders = token_data.get("holders", [])
                    if isinstance(holders, list):
                        top3_pct = sum(float(h.get("percent", 0) or 0) for h in holders[:3]) * 100
                        holder_count = len(holders)
                    else:
                        top3_pct = 0
                        holder_count = 0

                    # Extract DEX / TVL data
                    dex_list = token_data.get("dex", [])
                    total_tvl = 0
                    total_lp_holders = 0
                    total_lp_locked = 0
                    lp_count = 0
                    if isinstance(dex_list, list):
                        lp_count = len(dex_list)
                        for dex in dex_list:
                            total_tvl += float(dex.get("tvl", 0) or 0)
                            lph = dex.get("lp_holders")
                            if isinstance(lph, list):
                                total_lp_holders += len(lph)
                                total_lp_locked += sum(1 for h in lph if h.get("is_locked"))

                    # Creator info
                    creators = token_data.get("creators", [])
                    creator_pct = 0
                    if isinstance(creators, list) and creators:
                        creator_pct = float(creators[0].get("percent", 0) or 0) * 100

                    # Binary flags
                    closable = token_data.get("closable", {})
                    bal_mutable = token_data.get("balance_mutable_authority", {})
                    freeze = token_data.get("freeze_authority", {})
                    transfer_fee = token_data.get("transfer_fee", {})

                    return {
                        "gp_token_name": token_data.get("token_name", ""),
                        "gp_token_symbol": token_data.get("token_symbol", ""),
                        "gp_top3_holder_pct": round(top3_pct, 2),
                        "gp_holder_count": holder_count,
                        "gp_creator_pct": round(creator_pct, 2),
                        "gp_total_tvl": round(total_tvl, 2),
                        "gp_lp_count": lp_count,
                        "gp_lp_holders_total": total_lp_holders,
                        "gp_lp_locked_count": total_lp_locked,
                        "gp_closable": closable.get("status", "0") if isinstance(closable, dict) else "0",
                        "gp_balance_mutable": bal_mutable.get("status", "0") if isinstance(bal_mutable, dict) else "0",
                        "gp_freeze_authority": freeze.get("status", "") if isinstance(freeze, dict) else "",
                        "gp_transfer_fee": transfer_fee.get("status", "0") if isinstance(transfer_fee, dict) else "0",
                        "gp_default_account_state": token_data.get("default_account_state", ""),
                        "gp_non_transferable": token_data.get("non_transferable", {}).get("status", "0") if isinstance(token_data.get("non_transferable"), dict) else "0",
                    }
                elif resp.status == 429:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                else:
                    return None
        except Exception:
            await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
    return None


# ── Workers (one per API, rate-limited independently) ───────────────
async def run_api(name, fetch_fn, session, mints, cache, delay):
    """Process all mints for one API with rate limiting and checkpoints."""
    todo = [m for m in mints if m not in cache]
    total = len(mints)
    done = total - len(todo)
    start_time = time.time()

    est_min = len(todo) * delay / 60
    print(f"  [{name}] {done}/{total} cached, {len(todo)} remaining (~{est_min:.1f} min)")

    for i, mint in enumerate(todo):
        result = await fetch_fn(session, mint)
        if result is not None:
            cache[mint] = result

        # Progress + checkpoint
        done = total - len(todo) + i + 1
        if (i + 1) % CKPT_EVERY == 0 or i == len(todo) - 1:
            save_checkpoint(name, cache)
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(todo) - i - 1) / rate if rate > 0 else 0
            print(f"  [{name}] {done}/{total} ({(i+1)}/{len(todo)} new) "
                  f"| {rate:.1f} req/s | ETA {eta/60:.1f} min")

        await asyncio.sleep(delay)

    save_checkpoint(name, cache)
    print(f"  [{name}] DONE — {len(cache)} total cached")
    return cache


async def main_async(args):
    """Run all 3 API enrichments in parallel."""
    # Load dataset
    input_path = os.path.join(DATA_DIR, "enriched_labeled.csv")
    if not os.path.exists(input_path):
        sys.exit(f"[ERROR] Not found: {input_path}")

    print(f"Loading {input_path}...")
    df = pd.read_csv(input_path)
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    # Get priority-sorted unique mints
    if "LABEL_TIER" in df.columns:
        df["_sort"] = df["LABEL_TIER"].map({t: i for i, t in enumerate(LABEL_PRIORITY)}).fillna(99)
        mints = df.sort_values("_sort")["MINT"].drop_duplicates().tolist()
        df.drop("_sort", axis=1, inplace=True)
    else:
        mints = df["MINT"].drop_duplicates().tolist()

    if args.sample:
        mints = mints[:args.sample]
    print(f"  Processing {len(mints)} unique mints")

    # Load existing checkpoints
    rc_cache = load_checkpoint("rc_rugcheck")
    gt_cache = load_checkpoint("gt_gecko")
    gp_cache = load_checkpoint("gp_goplus")

    print(f"\nCheckpoints: RC={len(rc_cache)}, GT={len(gt_cache)}, GP={len(gp_cache)}")
    print(f"Starting parallel enrichment...\n")

    # Run all APIs in parallel
    async with aiohttp.ClientSession() as session:
        tasks = []

        if "rugcheck" not in (args.skip or []):
            tasks.append(run_api("rc_rugcheck", fetch_rugcheck, session, mints, rc_cache, RC_DELAY))
        if "gecko" not in (args.skip or []):
            tasks.append(run_api("gt_gecko", fetch_gecko, session, mints, gt_cache, GT_DELAY))
        if "goplus" not in (args.skip or []):
            tasks.append(run_api("gp_goplus", fetch_goplus, session, mints, gp_cache, GP_DELAY))

        if args.only:
            # Run only specified API
            tasks = []
            if args.only == "rugcheck":
                tasks.append(run_api("rc_rugcheck", fetch_rugcheck, session, mints, rc_cache, RC_DELAY))
            elif args.only == "gecko":
                tasks.append(run_api("gt_gecko", fetch_gecko, session, mints, gt_cache, GT_DELAY))
            elif args.only == "goplus":
                tasks.append(run_api("gp_goplus", fetch_goplus, session, mints, gp_cache, GP_DELAY))

        results = await asyncio.gather(*tasks)

    # Reload caches after parallel run
    rc_cache = load_checkpoint("rc_rugcheck")
    gt_cache = load_checkpoint("gt_gecko")
    gp_cache = load_checkpoint("gp_goplus")

    # Merge into dataframe
    print(f"\nMerging results into dataframe...")

    # RugCheck columns
    rc_df = pd.DataFrame([
        {"MINT": mint, **data}
        for mint, data in rc_cache.items()
        if mint in set(mints)
    ])
    if not rc_df.empty:
        # Drop existing RC columns if re-running
        existing_rc = [c for c in df.columns if c.startswith("rc_")]
        if existing_rc:
            df.drop(columns=existing_rc, inplace=True)
        df = df.merge(rc_df, on="MINT", how="left")
        print(f"  RugCheck: {len(rc_df)} mints → {len([c for c in rc_df.columns if c != 'MINT'])} columns")

    # GeckoTerminal columns
    gt_df = pd.DataFrame([
        {"MINT": mint, **data}
        for mint, data in gt_cache.items()
        if mint in set(mints)
    ])
    if not gt_df.empty:
        existing_gt = [c for c in df.columns if c.startswith("gt_")]
        if existing_gt:
            df.drop(columns=existing_gt, inplace=True)
        df = df.merge(gt_df, on="MINT", how="left")
        print(f"  GeckoTerminal: {len(gt_df)} mints → {len([c for c in gt_df.columns if c != 'MINT'])} columns")

    # GoPlus columns
    gp_df = pd.DataFrame([
        {"MINT": mint, **data}
        for mint, data in gp_cache.items()
        if mint in set(mints)
    ])
    if not gp_df.empty:
        existing_gp = [c for c in df.columns if c.startswith("gp_")]
        if existing_gp:
            df.drop(columns=existing_gp, inplace=True)
        df = df.merge(gp_df, on="MINT", how="left")
        print(f"  GoPlus: {len(gp_df)} mints → {len([c for c in gp_df.columns if c != 'MINT'])} columns")

    # Save
    output_path = os.path.join(DATA_DIR, "enriched_final.csv")
    df.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path}")
    print(f"  {len(df)} rows × {len(df.columns)} columns")
    print(f"  New columns: {[c for c in df.columns if c.startswith(('rc_', 'gt_', 'gp_'))]}")


def parse_args():
    p = argparse.ArgumentParser(description="Fast parallel API enrichment")
    p.add_argument("--sample", type=int, default=2000, help="Number of unique mints (default: 2000)")
    p.add_argument("--skip", nargs="+", choices=["rugcheck", "gecko", "goplus"], help="Skip specific APIs")
    p.add_argument("--only", choices=["rugcheck", "gecko", "goplus"], help="Run only one API")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print("=" * 70)
    print(f"  FAST PARALLEL ENRICHMENT — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  APIs: RugCheck + GeckoTerminal + GoPlus (async, 0.5s/req each)")
    print(f"  Sample: {args.sample} tokens")
    print("=" * 70)

    start = time.time()
    asyncio.run(main_async(args))
    elapsed = time.time() - start
    print(f"\nTotal time: {elapsed/60:.1f} min ({elapsed:.0f}s)")
