"""
DeFi Sentinel — Merge All Enrichment Sources
Combines: base data + derived features + creator wallet + GoPlus + RugCheck + Jupiter
into one final enriched dataset, dropping known-bad columns.

Run AFTER:
  1. python3 scripts/compute_derived_features.py
  2. python3 scripts/enrich_creator_wallet.py --sample 500
  3. python3 scripts/enrich_goplus_rugcheck_batch.py --sample 5000
  4. python3 scripts/enrich_jupiter.py --sample 5000

Then:
  python3 scripts/merge_all_enrichments.py
"""
import pandas as pd
import numpy as np
import os

BASE        = "data/enriched/enriched_with_derived.csv"
CREATOR     = "data/enriched/creator_wallet_features.csv"
GOPLUS      = "data/enriched/goplus_enriched.csv"
RUGCHECK    = "data/enriched/rugcheck_enriched.csv"
JUPITER     = "data/enriched/jupiter_enriched.csv"
OUTPUT      = "data/enriched/enriched_all_sources.csv"

# Columns to DROP (label leakage, duplicates, or useless)
DROP_COLS = [
    # Label leakage — these DEFINE the labels, can't be features
    "RUG_SIGNALS", "RUG_SCORE", "RUG_LABEL",
    "SIG_DRAINED", "SIG_NO_PRICE", "SIG_INACTIVE", "SIG_SHORT_LIFE",
    "SIG_FEW_TXN", "SIG_NO_NAME", "SIG_MUTABLE", "SIG_NO_METADATA", "SIG_NO_IMAGE",
    # Duplicate columns
    "HAS_AUTHORITY",       # = MINT_AUTHORITY_ACTIVE
    "RUG_LABEL_vl",        # merge artifact
    # IDs / non-features
    "LAST_SWAP_TX_ID",
    "INACTIVITY_STATUS",   # categorical duplicate of SIG_INACTIVE
]

# GeckoTerminal columns to FLAG (not drop, but mark as unreliable)
GT_SUSPICIOUS = [
    "gt_base_price_usd", "gt_fdv_usd", "gt_market_cap_usd", "gt_reserve_usd",
    "gt_vol_24h", "gt_vol_6h", "gt_vol_1h", "gt_price_pct_1h",
    "gt_txns_24h_buys", "gt_txns_24h_sells",
]


def main():
    print("=" * 70)
    print("  DeFi Sentinel — Merge All Enrichment Sources")
    print("=" * 70)

    # ── Load base ──
    if not os.path.exists(BASE):
        print(f"  ⚠ Base file not found: {BASE}")
        print(f"    Run: python3 scripts/compute_derived_features.py first")
        return
    df = pd.read_csv(BASE, low_memory=False)
    print(f"  Base: {len(df):,} rows × {len(df.columns)} cols")

    # ── Merge Creator Wallet ──
    if os.path.exists(CREATOR):
        cw = pd.read_csv(CREATOR)
        print(f"  Creator Wallet: {len(cw):,} creators")
        # Merge on OWNER (creator address)
        cw_cols = [c for c in cw.columns if c != "creator_address"]
        cw = cw.rename(columns={"creator_address": "OWNER"})
        df = df.merge(cw, on="OWNER", how="left", suffixes=("", "_cw"))
        # Remove dupes from merge
        for c in cw_cols:
            if f"{c}_cw" in df.columns:
                df[c] = df[c].fillna(df[f"{c}_cw"])
                df.drop(columns=[f"{c}_cw"], inplace=True)
        print(f"    → merged, now {len(df.columns)} cols")
    else:
        print(f"  Creator Wallet: NOT FOUND (run enrich_creator_wallet.py first)")

    # ── Merge GoPlus (new data overwrites old sparse columns) ──
    if os.path.exists(GOPLUS):
        gp = pd.read_csv(GOPLUS)
        print(f"  GoPlus: {len(gp):,} tokens")
        # Drop old GoPlus columns, replace with new
        old_gp = [c for c in df.columns if c.startswith("gp_")]
        df.drop(columns=old_gp, inplace=True, errors="ignore")
        df = df.merge(gp, on="MINT", how="left", suffixes=("", "_gp"))
        print(f"    → merged, replaced {len(old_gp)} old gp_ cols, now {len(df.columns)} cols")
    else:
        print(f"  GoPlus: NOT FOUND (run enrich_goplus_rugcheck_batch.py first)")

    # ── Merge RugCheck (new data overwrites old sparse columns) ──
    if os.path.exists(RUGCHECK):
        rc = pd.read_csv(RUGCHECK)
        print(f"  RugCheck: {len(rc):,} tokens")
        # Drop old RugCheck columns, replace with new
        old_rc = [c for c in df.columns if c.startswith(("RC_", "rc_"))]
        df.drop(columns=old_rc, inplace=True, errors="ignore")
        df = df.merge(rc, on="MINT", how="left", suffixes=("", "_rc"))
        print(f"    → merged, replaced {len(old_rc)} old RC/rc cols, now {len(df.columns)} cols")
    else:
        print(f"  RugCheck: NOT FOUND (run enrich_goplus_rugcheck_batch.py first)")

    # ── Merge Jupiter ──
    if os.path.exists(JUPITER):
        jup = pd.read_csv(JUPITER)
        print(f"  Jupiter: {len(jup):,} tokens")
        df = df.merge(jup, on="MINT", how="left", suffixes=("", "_jup"))
        print(f"    → merged, now {len(df.columns)} cols")
    else:
        print(f"  Jupiter: NOT FOUND (run enrich_jupiter.py first)")

    # ── Drop known-bad columns ──
    existing_drops = [c for c in DROP_COLS if c in df.columns]
    df.drop(columns=existing_drops, inplace=True, errors="ignore")
    print(f"\n  Dropped {len(existing_drops)} leaky/duplicate columns: {existing_drops}")

    # ── Flag unreliable GT columns ──
    gt_present = [c for c in GT_SUSPICIOUS if c in df.columns]
    if gt_present:
        print(f"  ⚠ FLAGGED {len(gt_present)} GeckoTerminal columns as unreliable (99% constant)")
        print(f"    These should NOT be used in training until re-enriched with proper sampling")

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print(f"  FINAL: {len(df):,} rows × {len(df.columns)} cols")
    print(f"  Saved to: {OUTPUT}")

    # Feature source breakdown
    sources = {
        "Helius": [c for c in df.columns if c.upper().startswith(("TOKEN_", "HAS_", "IS_", "MINT_", "FREEZE_", "OWNER", "CREATOR_", "JSON_URI"))],
        "GoPlus": [c for c in df.columns if c.startswith("gp_")],
        "RugCheck": [c for c in df.columns if c.startswith(("RC_", "rc_"))],
        "GeckoTerminal": [c for c in df.columns if c.startswith("gt_")],
        "Jupiter": [c for c in df.columns if c.startswith("jup_")],
        "Derived": [c for c in df.columns if c.startswith("derived_")],
        "Creator Wallet": [c for c in df.columns if c.startswith("creator_")],
        "SolRPDS (base)": [c for c in df.columns if c in [
            "TOTAL_ADDED_LIQUIDITY", "TOTAL_REMOVED_LIQUIDITY",
            "NUM_LIQUIDITY_ADDS", "NUM_LIQUIDITY_REMOVES", "ADD_TO_REMOVE_RATIO",
            "LIFESPAN_H", "REMOVED_RATIO",
        ]],
    }
    print(f"\n  Feature sources:")
    for src, cols in sources.items():
        print(f"    {src:20s}: {len(cols):3d} columns")

    df.to_csv(OUTPUT, index=False)


if __name__ == "__main__":
    main()
