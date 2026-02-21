"""
enrich_dataset.py — Enrich SolRPDS dataset with real on-chain Solana data
==========================================================================

Uses two API strategies (both with free tiers):
  1. Helius DAS API (getAsset / getAssetBatch) — token metadata, supply,
     mint/freeze authority, token program, price info
  2. Solana public RPC (getTokenLargestAccounts, getTokenSupply) — holder
     concentration, total supply

Outputs: enriched CSV with ~15 new features added to each row.

Usage:
  # You need a free Helius API key from https://dashboard.helius.dev/signup
  python enrich_dataset.py --helius_key YOUR_KEY

  # Or set env variable HELIUS_API_KEY
  set HELIUS_API_KEY=YOUR_KEY
  python enrich_dataset.py

  # To test on a small sample first:
  python enrich_dataset.py --helius_key YOUR_KEY --sample 100

Rate limits (free plan):
  - Helius: 1M credits/month, 10 req/s  →  batch of 1000 = 1 call
  - 116K mints ÷ 1000 per batch = ~117 calls → trivial credit usage
  - getTokenLargestAccounts via public RPC: ~2 req/s to be safe
"""

import os
import sys
import csv
import json
import time
import glob
import struct
import base64
import argparse
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("[ERROR] 'requests' not installed. Run: pip install requests")

try:
    import pandas as pd
except ImportError:
    sys.exit("[ERROR] 'pandas' not installed. Run: pip install pandas")


# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────
HELIUS_RPC_URL = "https://mainnet.helius-rpc.com/?api-key={key}"
SOLANA_PUBLIC_RPC = "https://api.mainnet-beta.solana.com"

# Batch size for Helius getAssetBatch (max 1000)
BATCH_SIZE = 1000

# Rate limiting
HELIUS_DELAY = 0.12       # ~8 req/s (under 10 limit)
RPC_DELAY = 0.55          # ~1.8 req/s for public RPC (conservative)

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


# ─────────────────────────────────────────────────────────────────────
# ARGUMENT PARSING
# ─────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Enrich SolRPDS CSV with on-chain Solana data via Helius + Solana RPC."
    )
    parser.add_argument(
        "--helius_key",
        type=str,
        default=os.environ.get("HELIUS_API_KEY", ""),
        help="Helius API key (or set HELIUS_API_KEY env var).",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="./dataset",
        help="Path to folder containing SolRPDS CSV files.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./output/enriched_dataset.csv",
        help="Output path for enriched CSV.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="If > 0, only process this many unique mints (for testing).",
    )
    parser.add_argument(
        "--skip_rpc",
        action="store_true",
        help="Skip Solana public RPC calls (holder concentration). Faster but less data.",
    )
    parser.add_argument(
        "--checkpoint_every",
        type=int,
        default=5000,
        help="Save progress every N mints (default 5000).",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────
# LOAD CSV DATA
# ─────────────────────────────────────────────────────────────────────
def load_all_csvs(data_dir: str) -> pd.DataFrame:
    csv_files = sorted(
        glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True)
    )
    if not csv_files:
        sys.exit(f"[ERROR] No CSV files found in '{data_dir}'.")

    frames = []
    for f in csv_files:
        print(f"  Loading {os.path.basename(f)} ...", end=" ")
        try:
            df = pd.read_csv(f, low_memory=False)
            print(f"({len(df)} rows)")
            frames.append(df)
        except Exception as e:
            print(f"SKIPPED ({e})")

    data = pd.concat(frames, ignore_index=True)
    print(f"  Total: {len(data)} rows")
    return data


# ─────────────────────────────────────────────────────────────────────
# HELIUS DAS API — getAssetBatch
# ─────────────────────────────────────────────────────────────────────
def helius_get_asset_batch(mint_list: list, api_key: str) -> dict:
    """
    Call Helius getAssetBatch for up to 1000 mint addresses.
    Returns dict: mint_address → asset_info
    """
    url = HELIUS_RPC_URL.format(key=api_key)
    payload = {
        "jsonrpc": "2.0",
        "id": "enrich-batch",
        "method": "getAssetBatch",
        "params": {
            "ids": mint_list,
        },
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * (attempt + 1)
                print(f"    ⚠ Rate limited, waiting {wait}s ...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                print(f"    ⚠ API error: {data['error']}")
                return {}

            results = {}
            for asset in data.get("result", []):
                if asset and "id" in asset:
                    results[asset["id"]] = asset
            return results

        except requests.exceptions.Timeout:
            print(f"    ⚠ Timeout (attempt {attempt+1}/{MAX_RETRIES})")
            time.sleep(RETRY_BACKOFF * (attempt + 1))
        except Exception as e:
            print(f"    ⚠ Error: {e} (attempt {attempt+1}/{MAX_RETRIES})")
            time.sleep(RETRY_BACKOFF * (attempt + 1))

    return {}


def extract_helius_features(asset: dict) -> dict:
    """Extract enrichment features from a Helius getAsset response."""
    features = {}

    # --- Authorities ---
    authorities = asset.get("authorities", [])
    features["HAS_AUTHORITY"] = 1 if authorities else 0

    # --- Ownership / Mint authority / Freeze authority ---
    # These come from the on-chain mint account data
    ownership = asset.get("ownership") or {}
    features["OWNER"] = ownership.get("owner", "")
    features["IS_FROZEN"] = 1 if ownership.get("frozen", False) else 0

    # --- Content / Metadata ---
    content = asset.get("content") or {}
    metadata = content.get("metadata") or {}
    features["TOKEN_NAME"] = metadata.get("name", "")
    features["TOKEN_SYMBOL"] = metadata.get("symbol", "")
    features["TOKEN_STANDARD"] = metadata.get("token_standard", "")
    features["HAS_METADATA"] = 1 if metadata.get("name") else 0
    features["HAS_IMAGE"] = 1 if content.get("links", {}).get("image") else 0

    # JSON URI — often rug pulls have no metadata or use fake URIs
    json_uri = content.get("json_uri", "")
    features["HAS_JSON_URI"] = 1 if json_uri else 0
    features["JSON_URI_DOMAIN"] = ""
    if json_uri:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(json_uri)
            features["JSON_URI_DOMAIN"] = parsed.netloc
        except:
            pass

    # --- Token info ---
    token_info = asset.get("token_info") or {}
    features["TOKEN_DECIMALS"] = token_info.get("decimals", None)
    features["TOKEN_SUPPLY"] = token_info.get("supply", None)
    features["TOKEN_PROGRAM"] = token_info.get("token_program", "")

    # Price info
    price_info = token_info.get("price_info") or {}
    features["TOKEN_PRICE_USD"] = price_info.get("price_per_token", None)
    features["TOKEN_PRICE_CURRENCY"] = price_info.get("currency", "")

    # --- Mutable flag ---
    features["IS_MUTABLE"] = 1 if asset.get("mutable", False) else 0

    # --- Is burnt? ---
    features["IS_BURNT"] = 1 if asset.get("burnt", False) else 0

    # --- Compression ---
    compression = asset.get("compression") or {}
    features["IS_COMPRESSED"] = 1 if compression.get("compressed", False) else 0

    # --- Royalty info ---
    royalty = asset.get("royalty") or {}
    features["ROYALTY_PCT"] = royalty.get("percent", 0)

    # --- Supply info (for NFTs/editions) ---
    supply = asset.get("supply") or {}
    features["EDITION_TOTAL_SUPPLY"] = supply.get("print_max_supply", None)

    # --- Creator info ---
    creators = asset.get("creators", [])
    features["NUM_CREATORS"] = len(creators)
    features["CREATOR_VERIFIED"] = 1 if any(c.get("verified") for c in creators) else 0

    # --- Mint/Freeze authority from authorities list ---
    for auth in authorities:
        scopes = auth.get("scopes", [])
        address = auth.get("address", "")
        if "full" in scopes or "mint" in scopes:
            features["MINT_AUTHORITY"] = address
            features["MINT_AUTHORITY_ACTIVE"] = 1
        if "freeze" in scopes:
            features["FREEZE_AUTHORITY"] = address
            features["FREEZE_AUTHORITY_ACTIVE"] = 1

    # Defaults if not found
    features.setdefault("MINT_AUTHORITY", "")
    features.setdefault("MINT_AUTHORITY_ACTIVE", 0)
    features.setdefault("FREEZE_AUTHORITY", "")
    features.setdefault("FREEZE_AUTHORITY_ACTIVE", 0)

    return features


# ─────────────────────────────────────────────────────────────────────
# SOLANA RPC — Holder concentration
# ─────────────────────────────────────────────────────────────────────
def get_holder_concentration(mint: str) -> dict:
    """
    Use getTokenLargestAccounts to get top 20 holders,
    and getTokenSupply for total supply. Compute concentration metrics.
    """
    features = {
        "TOP1_HOLDER_PCT": None,
        "TOP5_HOLDER_PCT": None,
        "TOP10_HOLDER_PCT": None,
        "TOP20_HOLDER_PCT": None,
        "NUM_HOLDERS_IN_TOP20": None,
        "HOLDER_SUPPLY": None,
    }

    try:
        # Get top 20 largest token accounts
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [mint],
        }
        resp = requests.post(SOLANA_PUBLIC_RPC, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            return features

        accounts = data.get("result", {}).get("value", [])
        if not accounts:
            return features

        # Get total supply
        time.sleep(0.3)
        payload2 = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "getTokenSupply",
            "params": [mint],
        }
        resp2 = requests.post(SOLANA_PUBLIC_RPC, json=payload2, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()

        total_supply_str = data2.get("result", {}).get("value", {}).get("amount", "0")
        total_supply = int(total_supply_str)

        if total_supply == 0:
            return features

        # Calculate holder amounts
        amounts = []
        for acc in accounts:
            amt = int(acc.get("amount", "0"))
            amounts.append(amt)

        amounts.sort(reverse=True)
        features["NUM_HOLDERS_IN_TOP20"] = len(amounts)
        features["HOLDER_SUPPLY"] = total_supply

        cumsum = 0
        for i, amt in enumerate(amounts):
            cumsum += amt
            pct = (cumsum / total_supply) * 100
            if i == 0:
                features["TOP1_HOLDER_PCT"] = round(pct, 4)
            if i == 4:
                features["TOP5_HOLDER_PCT"] = round(pct, 4)
            if i == 9:
                features["TOP10_HOLDER_PCT"] = round(pct, 4)
            if i == 19:
                features["TOP20_HOLDER_PCT"] = round(pct, 4)

        # If fewer than 20 accounts, set top-N to cumulative
        total_pct = round((sum(amounts) / total_supply) * 100, 4)
        if len(amounts) < 5:
            features["TOP5_HOLDER_PCT"] = total_pct
        if len(amounts) < 10:
            features["TOP10_HOLDER_PCT"] = total_pct
        if len(amounts) < 20:
            features["TOP20_HOLDER_PCT"] = total_pct

    except Exception as e:
        pass  # Return defaults

    return features


# ─────────────────────────────────────────────────────────────────────
# MAIN ENRICHMENT PIPELINE
# ─────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    if not args.helius_key:
        print("=" * 70)
        print("  ⚠  No Helius API key provided!")
        print("  Get a FREE key at: https://dashboard.helius.dev/signup")
        print("  Then run: python enrich_dataset.py --helius_key YOUR_KEY")
        print("  Or set:   set HELIUS_API_KEY=YOUR_KEY")
        print("=" * 70)
        sys.exit(1)

    # ── LOAD DATA ────────────────────────────────────────────────────
    print("\n[1/4] Loading CSV data ...")
    df = load_all_csvs(args.data_dir)

    # Normalize column names
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    if "MINT" not in df.columns:
        sys.exit("[ERROR] No 'MINT' column found in data!")

    # Get unique mints
    unique_mints = df["MINT"].dropna().unique().tolist()
    print(f"\n  Unique mint addresses: {len(unique_mints)}")

    if args.sample > 0:
        unique_mints = unique_mints[: args.sample]
        print(f"  (Sampling {args.sample} for testing)")

    # ── CHECKPOINT: Load existing progress ───────────────────────────
    checkpoint_path = args.output.replace(".csv", "_checkpoint.json")
    enrichment_cache = {}
    if os.path.exists(checkpoint_path):
        print(f"\n  ✓ Found checkpoint, loading previous progress ...")
        with open(checkpoint_path, "r") as f:
            enrichment_cache = json.load(f)
        print(f"    Already enriched: {len(enrichment_cache)} mints")

    # Filter out already-processed mints
    remaining_mints = [m for m in unique_mints if m not in enrichment_cache]
    print(f"  Remaining to process: {len(remaining_mints)}")

    # ── STEP 2: Helius DAS API Enrichment ────────────────────────────
    print(f"\n[2/4] Fetching token metadata via Helius DAS API ...")
    print(f"  Batches of {BATCH_SIZE}, ~{len(remaining_mints) // BATCH_SIZE + 1} API calls needed")

    helius_data = {}
    total_batches = (len(remaining_mints) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(remaining_mints), BATCH_SIZE):
        batch = remaining_mints[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} mints) ...", end=" ")

        result = helius_get_asset_batch(batch, args.helius_key)
        helius_data.update(result)
        print(f"✓ got {len(result)} results")

        time.sleep(HELIUS_DELAY)

    print(f"  Helius total: {len(helius_data)} assets retrieved")

    # ── STEP 3: Extract features + optional holder data ──────────────
    print(f"\n[3/4] Extracting features ...")
    processed = 0
    skipped_rpc = 0

    for mint in remaining_mints:
        asset = helius_data.get(mint, {})
        features = extract_helius_features(asset) if asset else {}

        # Add holder concentration from Solana RPC
        if not args.skip_rpc and mint:
            try:
                holder_features = get_holder_concentration(mint)
                features.update(holder_features)
                time.sleep(RPC_DELAY)
            except Exception:
                skipped_rpc += 1
        else:
            skipped_rpc += 1

        enrichment_cache[mint] = features
        processed += 1

        # Progress & checkpoint
        if processed % 100 == 0:
            pct = (processed / len(remaining_mints)) * 100
            elapsed_mints = processed
            eta_remaining = len(remaining_mints) - processed
            if not args.skip_rpc:
                eta_seconds = eta_remaining * RPC_DELAY
                eta_min = eta_seconds / 60
                print(f"  Progress: {processed}/{len(remaining_mints)} ({pct:.1f}%) — ETA: ~{eta_min:.0f} min")
            else:
                print(f"  Progress: {processed}/{len(remaining_mints)} ({pct:.1f}%)")

        if processed % args.checkpoint_every == 0:
            print(f"  💾 Saving checkpoint ({len(enrichment_cache)} mints) ...")
            os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
            with open(checkpoint_path, "w") as f:
                json.dump(enrichment_cache, f)

    if not args.skip_rpc:
        print(f"  RPC skipped/failed: {skipped_rpc}")

    # Save final checkpoint
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    with open(checkpoint_path, "w") as f:
        json.dump(enrichment_cache, f)

    # ── STEP 4: Merge back into DataFrame ────────────────────────────
    print(f"\n[4/4] Merging enrichment data into dataset ...")

    # Build enrichment DataFrame
    enrich_records = []
    for mint, features in enrichment_cache.items():
        row = {"MINT": mint}
        row.update(features)
        enrich_records.append(row)

    enrich_df = pd.DataFrame(enrich_records)
    print(f"  Enrichment table: {enrich_df.shape}")

    # Merge with original data
    enriched = df.merge(enrich_df, on="MINT", how="left")
    print(f"  Merged shape: {enriched.shape}")

    # ── SAVE ─────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    enriched.to_csv(args.output, index=False)
    print(f"\n✅ Enriched dataset saved to: {args.output}")
    print(f"   Rows: {len(enriched)}")
    print(f"   Columns: {len(enriched.columns)}")
    print(f"   New features added: {len(enriched.columns) - len(df.columns)}")

    # ── SUMMARY ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  NEW FEATURES ADDED:")
    print("=" * 60)
    new_cols = [c for c in enriched.columns if c not in df.columns]
    for col in new_cols:
        non_null = enriched[col].notna().sum()
        pct = (non_null / len(enriched)) * 100
        print(f"  {col:35s} — {non_null:>7,} non-null ({pct:.1f}%)")
    print("=" * 60)

    # Print time estimate for full run
    if args.sample > 0 and not args.skip_rpc:
        full_mints = df["MINT"].dropna().nunique()
        est_time = full_mints * RPC_DELAY / 60
        print(f"\n  📊 Full run estimate ({full_mints} unique mints):")
        print(f"     With holder data (--skip_rpc off): ~{est_time:.0f} minutes")
        print(f"     Without holder data (--skip_rpc):  ~{full_mints / BATCH_SIZE * HELIUS_DELAY / 60:.1f} minutes")


if __name__ == "__main__":
    main()
