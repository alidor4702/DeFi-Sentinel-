"""
enrich_multi_source.py — Multi-Source Data Enrichment for DeFi Sentinel
========================================================================

Combines 3 FREE data sources to enrich the SolRPDS dataset:

  Source 1: RugCheck API      → risk score, rugged flag, risk labels,
                                 holder count, mint/freeze authority
  Source 2: GeckoTerminal API → pool liquidity, volume, tx counts,
                                 price, pool age
  Source 3: Helius DAS API    → token metadata, supply, token program,
                                 name/symbol

Output: enriched CSV with ~40 new features — ready for ML training.

Usage:
  # Quick test (5 tokens)
  python enrich_multi_source.py --sample 5

  # Fast mode — RugCheck + GeckoTerminal only (no Helius key needed)
  python enrich_multi_source.py --skip_helius

  # Full enrichment (all 3 sources)
  python enrich_multi_source.py --helius_key YOUR_KEY

  # Resume from checkpoint after interruption
  python enrich_multi_source.py  (auto-detects checkpoint)

Rate limits:
  - RugCheck:      ~30 req/min (free, no key)
  - GeckoTerminal: ~30 req/min (free, no key)
  - Helius DAS:    batch of 1000 per call, 10 req/s (free key)

Time estimates (33K unique mints):
  - RugCheck only:                ~20 min
  - RugCheck + GeckoTerminal:     ~40 min
  - All 3 sources:                ~42 min
"""

import os
import sys
import json
import time
import glob
import argparse
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    sys.exit("[ERROR] Run: pip install requests")

try:
    import pandas as pd
except ImportError:
    sys.exit("[ERROR] Run: pip install pandas")


# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────
RUGCHECK_BASE = "https://api.rugcheck.xyz/v1/tokens"
GECKO_BASE = "https://api.geckoterminal.com/api/v2/networks/solana/pools"
HELIUS_RPC_URL = "https://mainnet.helius-rpc.com/?api-key={key}"

# Rate limits (requests per second)
RUGCHECK_DELAY = 2.2    # ~27 req/min (under 30 limit)
GECKO_DELAY = 2.2       # ~27 req/min
HELIUS_DELAY = 0.12     # batch calls, very fast

MAX_RETRIES = 3
RETRY_BACKOFF = 3.0
HELIUS_BATCH_SIZE = 1000


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(
        description="Multi-source enrichment: RugCheck + GeckoTerminal + Helius"
    )
    p.add_argument("--data_dir", default="./data", help="CSV data directory")
    p.add_argument("--output", default="./output/enriched_multi_source.csv")
    p.add_argument("--helius_key", default=os.environ.get("HELIUS_API_KEY", ""))
    p.add_argument("--sample", type=int, default=0, help="Process only N unique pairs (for testing)")
    p.add_argument("--skip_helius", action="store_true", help="Skip Helius API calls")
    p.add_argument("--skip_gecko", action="store_true", help="Skip GeckoTerminal API calls")
    p.add_argument("--skip_rugcheck", action="store_true", help="Skip RugCheck API calls")
    p.add_argument("--checkpoint_every", type=int, default=500)
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────────────
def load_csvs(data_dir):
    csv_files = sorted(glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True))
    if not csv_files:
        sys.exit(f"[ERROR] No CSV files in '{data_dir}'")
    frames = []
    for f in csv_files:
        basename = os.path.basename(f)
        # Skip any output files
        if "enriched" in basename.lower() or "result" in basename.lower() or "feature_import" in basename.lower():
            continue
        print(f"  Loading {basename} ...", end=" ")
        try:
            df = pd.read_csv(f, low_memory=False)
            print(f"({len(df)} rows)")
            frames.append(df)
        except Exception as e:
            print(f"SKIP ({e})")
    if not frames:
        sys.exit("[ERROR] No valid CSV files loaded.")
    data = pd.concat(frames, ignore_index=True)
    data.columns = [c.strip().upper().replace(" ", "_") for c in data.columns]
    print(f"  Total: {len(data)} rows, {data['MINT'].nunique()} unique mints")
    return data


# ─────────────────────────────────────────────────────────────────────
# SOURCE 1: RUGCHECK API
# ─────────────────────────────────────────────────────────────────────
def fetch_rugcheck(mint):
    """Fetch RugCheck report for a single mint. Returns flat dict of features."""
    features = {
        "RC_SCORE": None,
        "RC_SCORE_NORM": None,
        "RC_RUGGED": None,
        "RC_TOTAL_HOLDERS": None,
        "RC_TOTAL_MARKET_LIQ": None,
        "RC_TOTAL_LP_PROVIDERS": None,
        "RC_MINT_AUTHORITY": 0,
        "RC_FREEZE_AUTHORITY": 0,
        "RC_NUM_RISKS": 0,
        "RC_NUM_DANGERS": 0,
        "RC_NUM_WARNS": 0,
        "RC_RISK_NAMES": "",
        "RC_TOKEN_TYPE": "",
        "RC_TRANSFER_FEE": None,
        "RC_TOP_HOLDER_PCT": None,
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(f"{RUGCHECK_BASE}/{mint}/report", timeout=15)
            if r.status_code == 429:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            if r.status_code != 200:
                return features
            d = r.json()

            features["RC_SCORE"] = d.get("score")
            features["RC_SCORE_NORM"] = d.get("score_normalised")
            features["RC_RUGGED"] = 1 if d.get("rugged") else 0
            features["RC_TOTAL_HOLDERS"] = d.get("totalHolders")
            features["RC_TOTAL_MARKET_LIQ"] = d.get("totalMarketLiquidity")
            features["RC_TOTAL_LP_PROVIDERS"] = d.get("totalLPProviders")
            features["RC_TOKEN_TYPE"] = d.get("tokenType", "")

            # Mint / Freeze authority
            features["RC_MINT_AUTHORITY"] = 1 if d.get("mintAuthority") else 0
            features["RC_FREEZE_AUTHORITY"] = 1 if d.get("freezeAuthority") else 0

            # Transfer fee
            tf = d.get("transferFee")
            if tf and isinstance(tf, dict):
                features["RC_TRANSFER_FEE"] = tf.get("pct", tf.get("percentage"))

            # Risks
            risks = d.get("risks") or []
            features["RC_NUM_RISKS"] = len(risks)
            features["RC_NUM_DANGERS"] = sum(1 for r in risks if r.get("level") == "danger")
            features["RC_NUM_WARNS"] = sum(1 for r in risks if r.get("level") == "warn")
            risk_names = [r.get("name", "") for r in risks]
            features["RC_RISK_NAMES"] = "|".join(risk_names)

            # Top holders
            top_holders = d.get("topHolders") or []
            if top_holders and isinstance(top_holders, list):
                total_pct = sum(h.get("pct", 0) for h in top_holders[:10] if isinstance(h, dict))
                features["RC_TOP_HOLDER_PCT"] = round(total_pct, 4)

            return features

        except requests.exceptions.Timeout:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
        except Exception:
            time.sleep(RETRY_BACKOFF)

    return features


# ─────────────────────────────────────────────────────────────────────
# SOURCE 2: GECKOTERMINAL API
# ─────────────────────────────────────────────────────────────────────
def fetch_gecko_pool(pool_address):
    """Fetch GeckoTerminal pool data. Returns flat dict of features."""
    features = {
        "GT_POOL_NAME": "",
        "GT_RESERVE_USD": None,
        "GT_VOL_24H": None,
        "GT_VOL_6H": None,
        "GT_VOL_1H": None,
        "GT_BUYS_24H": None,
        "GT_SELLS_24H": None,
        "GT_BUYERS_24H": None,
        "GT_SELLERS_24H": None,
        "GT_BUYS_1H": None,
        "GT_SELLS_1H": None,
        "GT_PRICE_USD": None,
        "GT_FDV_USD": None,
        "GT_MARKET_CAP": None,
        "GT_POOL_CREATED_AT": "",
        "GT_POOL_AGE_DAYS": None,
        "GT_PRICE_CHANGE_24H": None,
        "GT_PRICE_CHANGE_1H": None,
        "GT_LOCKED_LIQ_PCT": None,
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(f"{GECKO_BASE}/{pool_address}", timeout=15)
            if r.status_code == 429:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            if r.status_code != 200:
                return features
            a = r.json().get("data", {}).get("attributes", {})

            features["GT_POOL_NAME"] = a.get("name", "")
            features["GT_RESERVE_USD"] = _to_float(a.get("reserve_in_usd"))
            features["GT_FDV_USD"] = _to_float(a.get("fdv_usd"))
            features["GT_MARKET_CAP"] = _to_float(a.get("market_cap_usd"))
            features["GT_PRICE_USD"] = _to_float(a.get("base_token_price_usd"))
            features["GT_LOCKED_LIQ_PCT"] = _to_float(a.get("locked_liquidity_percentage"))

            # Volume
            vol = a.get("volume_usd") or {}
            features["GT_VOL_24H"] = _to_float(vol.get("h24"))
            features["GT_VOL_6H"] = _to_float(vol.get("h6"))
            features["GT_VOL_1H"] = _to_float(vol.get("h1"))

            # Transactions
            txs = a.get("transactions") or {}
            h24 = txs.get("h24") or {}
            h1 = txs.get("h1") or {}
            features["GT_BUYS_24H"] = h24.get("buys")
            features["GT_SELLS_24H"] = h24.get("sells")
            features["GT_BUYERS_24H"] = h24.get("buyers")
            features["GT_SELLERS_24H"] = h24.get("sellers")
            features["GT_BUYS_1H"] = h1.get("buys")
            features["GT_SELLS_1H"] = h1.get("sells")

            # Price change
            pc = a.get("price_change_percentage") or {}
            features["GT_PRICE_CHANGE_24H"] = _to_float(pc.get("h24"))
            features["GT_PRICE_CHANGE_1H"] = _to_float(pc.get("h1"))

            # Pool age
            created = a.get("pool_created_at")
            features["GT_POOL_CREATED_AT"] = created or ""
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
                    features["GT_POOL_AGE_DAYS"] = round(age, 2)
                except:
                    pass

            return features

        except requests.exceptions.Timeout:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
        except Exception:
            time.sleep(RETRY_BACKOFF)

    return features


def _to_float(val):
    """Safely convert to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────────
# SOURCE 3: HELIUS DAS API (batch)
# ─────────────────────────────────────────────────────────────────────
def fetch_helius_batch(mint_list, api_key):
    """Batch-fetch token metadata via Helius getAssetBatch."""
    url = HELIUS_RPC_URL.format(key=api_key)
    payload = {
        "jsonrpc": "2.0",
        "id": "enrich",
        "method": "getAssetBatch",
        "params": {"ids": mint_list},
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 429:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                return {}
            results = {}
            for asset in data.get("result", []):
                if asset and "id" in asset:
                    results[asset["id"]] = extract_helius(asset)
            return results
        except:
            time.sleep(RETRY_BACKOFF * (attempt + 1))

    return {}


def extract_helius(asset):
    """Extract flat features from Helius getAsset response."""
    f = {}
    content = asset.get("content") or {}
    metadata = content.get("metadata") or {}
    token_info = asset.get("token_info") or {}
    price_info = token_info.get("price_info") or {}

    f["HL_TOKEN_NAME"] = metadata.get("name", "")
    f["HL_TOKEN_SYMBOL"] = metadata.get("symbol", "")
    f["HL_TOKEN_STANDARD"] = metadata.get("token_standard", "")
    f["HL_HAS_METADATA"] = 1 if metadata.get("name") else 0
    f["HL_HAS_IMAGE"] = 1 if (content.get("links") or {}).get("image") else 0
    f["HL_TOKEN_DECIMALS"] = token_info.get("decimals")
    f["HL_TOKEN_SUPPLY"] = token_info.get("supply")
    f["HL_TOKEN_PROGRAM"] = token_info.get("token_program", "")
    f["HL_TOKEN_PRICE_USD"] = price_info.get("price_per_token")
    f["HL_IS_MUTABLE"] = 1 if asset.get("mutable") else 0
    f["HL_IS_BURNT"] = 1 if asset.get("burnt") else 0

    # Authority info
    authorities = asset.get("authorities") or []
    f["HL_MINT_AUTH_ACTIVE"] = 0
    f["HL_FREEZE_AUTH_ACTIVE"] = 0
    for auth in authorities:
        scopes = auth.get("scopes", [])
        if "full" in scopes or "mint" in scopes:
            f["HL_MINT_AUTH_ACTIVE"] = 1
        if "freeze" in scopes:
            f["HL_FREEZE_AUTH_ACTIVE"] = 1

    creators = asset.get("creators") or []
    f["HL_NUM_CREATORS"] = len(creators)
    f["HL_CREATOR_VERIFIED"] = 1 if any(c.get("verified") for c in creators) else 0

    return f


# ─────────────────────────────────────────────────────────────────────
# CHECKPOINT
# ─────────────────────────────────────────────────────────────────────
def load_checkpoint(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_checkpoint(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # ── Load ──
    print("\n[1/5] Loading data ...")
    df = load_csvs(args.data_dir)

    if "MINT" not in df.columns or "LIQUIDITY_POOL_ADDRESS" not in df.columns:
        sys.exit("[ERROR] Need MINT and LIQUIDITY_POOL_ADDRESS columns")

    # Get unique (mint, pool) pairs
    pairs = df[["MINT", "LIQUIDITY_POOL_ADDRESS"]].drop_duplicates()
    unique_mints = df["MINT"].dropna().unique().tolist()
    unique_pools = df["LIQUIDITY_POOL_ADDRESS"].dropna().unique().tolist()
    print(f"  Unique mints: {len(unique_mints)}, unique pools: {len(unique_pools)}")

    if args.sample > 0:
        unique_mints = unique_mints[: args.sample]
        unique_pools = unique_pools[: args.sample]
        print(f"  (Sampling {args.sample} for testing)")

    # ── Checkpoints ──
    ckpt_base = args.output.replace(".csv", "")
    rc_cache = load_checkpoint(f"{ckpt_base}_rugcheck.json")
    gt_cache = load_checkpoint(f"{ckpt_base}_gecko.json")
    hl_cache = load_checkpoint(f"{ckpt_base}_helius.json")
    print(f"  Checkpoints: RugCheck={len(rc_cache)}, Gecko={len(gt_cache)}, Helius={len(hl_cache)}")

    # ── Source 1: RugCheck ──
    if not args.skip_rugcheck:
        remaining = [m for m in unique_mints if m not in rc_cache]
        print(f"\n[2/5] RugCheck API — {len(remaining)} mints to fetch ...")
        est_min = len(remaining) * RUGCHECK_DELAY / 60
        print(f"  Estimated time: ~{est_min:.0f} min")

        for i, mint in enumerate(remaining):
            rc_cache[mint] = fetch_rugcheck(mint)
            time.sleep(RUGCHECK_DELAY)

            if (i + 1) % 50 == 0:
                pct = (i + 1) / len(remaining) * 100
                eta = (len(remaining) - i - 1) * RUGCHECK_DELAY / 60
                print(f"  [{i+1}/{len(remaining)}] ({pct:.0f}%) ETA: ~{eta:.0f} min")
                save_checkpoint(f"{ckpt_base}_rugcheck.json", rc_cache)

        save_checkpoint(f"{ckpt_base}_rugcheck.json", rc_cache)
        print(f"  ✓ RugCheck done: {len(rc_cache)} mints")
    else:
        print("\n[2/5] RugCheck — SKIPPED")

    # ── Source 2: GeckoTerminal ──
    if not args.skip_gecko:
        remaining = [p for p in unique_pools if p not in gt_cache]
        print(f"\n[3/5] GeckoTerminal API — {len(remaining)} pools to fetch ...")
        est_min = len(remaining) * GECKO_DELAY / 60
        print(f"  Estimated time: ~{est_min:.0f} min")

        for i, pool in enumerate(remaining):
            gt_cache[pool] = fetch_gecko_pool(pool)
            time.sleep(GECKO_DELAY)

            if (i + 1) % 50 == 0:
                pct = (i + 1) / len(remaining) * 100
                eta = (len(remaining) - i - 1) * GECKO_DELAY / 60
                print(f"  [{i+1}/{len(remaining)}] ({pct:.0f}%) ETA: ~{eta:.0f} min")
                save_checkpoint(f"{ckpt_base}_gecko.json", gt_cache)

        save_checkpoint(f"{ckpt_base}_gecko.json", gt_cache)
        print(f"  ✓ GeckoTerminal done: {len(gt_cache)} pools")
    else:
        print("\n[3/5] GeckoTerminal — SKIPPED")

    # ── Source 3: Helius ──
    if not args.skip_helius and args.helius_key:
        remaining = [m for m in unique_mints if m not in hl_cache]
        print(f"\n[4/5] Helius DAS API — {len(remaining)} mints in batches of {HELIUS_BATCH_SIZE} ...")

        for i in range(0, len(remaining), HELIUS_BATCH_SIZE):
            batch = remaining[i: i + HELIUS_BATCH_SIZE]
            batch_num = i // HELIUS_BATCH_SIZE + 1
            total_batches = (len(remaining) + HELIUS_BATCH_SIZE - 1) // HELIUS_BATCH_SIZE
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} mints) ...", end=" ")

            result = fetch_helius_batch(batch, args.helius_key)
            # For mints not found, store empty dict
            for m in batch:
                if m not in result:
                    result[m] = {}
            hl_cache.update(result)
            print(f"✓ {len(result)}")
            time.sleep(HELIUS_DELAY)

        save_checkpoint(f"{ckpt_base}_helius.json", hl_cache)
        print(f"  ✓ Helius done: {len(hl_cache)} mints")
    else:
        print("\n[4/5] Helius — SKIPPED" + (" (no key)" if not args.helius_key else ""))

    # ── Merge everything ──
    print(f"\n[5/5] Merging all sources into dataset ...")

    # Build RugCheck DataFrame
    rc_rows = [{"MINT": m, **feats} for m, feats in rc_cache.items()]
    rc_df = pd.DataFrame(rc_rows) if rc_rows else pd.DataFrame(columns=["MINT"])

    # Build GeckoTerminal DataFrame
    gt_rows = [{"LIQUIDITY_POOL_ADDRESS": p, **feats} for p, feats in gt_cache.items()]
    gt_df = pd.DataFrame(gt_rows) if gt_rows else pd.DataFrame(columns=["LIQUIDITY_POOL_ADDRESS"])

    # Build Helius DataFrame
    hl_rows = [{"MINT": m, **feats} for m, feats in hl_cache.items()]
    hl_df = pd.DataFrame(hl_rows) if hl_rows else pd.DataFrame(columns=["MINT"])

    # Merge
    enriched = df.copy()
    if len(rc_df) > 1:
        enriched = enriched.merge(rc_df, on="MINT", how="left")
    if len(gt_df) > 1:
        enriched = enriched.merge(gt_df, on="LIQUIDITY_POOL_ADDRESS", how="left")
    if len(hl_df) > 1:
        enriched = enriched.merge(hl_df, on="MINT", how="left")

    print(f"  Final shape: {enriched.shape}")

    # ── Save ──
    enriched.to_csv(args.output, index=False)
    print(f"\n✅ Saved: {args.output}")
    print(f"   Rows: {len(enriched)}")
    print(f"   Columns: {len(enriched.columns)}")
    print(f"   Original columns: {len(df.columns)}")
    print(f"   New features: {len(enriched.columns) - len(df.columns)}")

    # Summary of new columns
    new_cols = [c for c in enriched.columns if c not in df.columns]
    print(f"\n{'='*60}")
    print("  NEW FEATURES:")
    print(f"{'='*60}")
    for col in new_cols:
        nn = enriched[col].notna().sum()
        pct = nn / len(enriched) * 100
        print(f"  {col:35s} {nn:>7,} non-null ({pct:.1f}%)")
    print(f"{'='*60}")

    # Key insight: cross-tab RugCheck score vs label
    if "RC_SCORE" in enriched.columns and "INACTIVITY_STATUS" in enriched.columns:
        print("\n  KEY INSIGHT: RugCheck Score by label (median)")
        for status in ["Active", "Inactive"]:
            subset = enriched[enriched["INACTIVITY_STATUS"] == status]["RC_SCORE"]
            if subset.notna().sum() > 0:
                print(f"    {status}: median={subset.median():.0f}  mean={subset.mean():.0f}")

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
