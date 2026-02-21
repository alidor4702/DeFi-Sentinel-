"""
DeFi Sentinel — Data Cleanup
Fixes the 4 critical data integrity issues found during the correlation audit:
  1. Removes label-leaking SIG_*/RUG_SCORE/RUG_SIGNALS columns
  2. Removes duplicate columns (HAS_AUTHORITY=MINT_AUTHORITY_ACTIVE, etc.)
  3. Flags/removes fake GeckoTerminal columns (99% constant, r=-1.0 artifact)
  4. Removes near-constant columns (zero information)

Input:  data/enriched/enriched_with_derived.csv  (has 14 derived features)
Output: data/enriched/enriched_clean.csv          (training-ready)
"""
import pandas as pd
import numpy as np

INPUT  = "data/enriched/enriched_with_derived.csv"
OUTPUT = "data/enriched/enriched_clean.csv"

print("=" * 70)
print("  DeFi Sentinel — Data Cleanup")
print("=" * 70)

df = pd.read_csv(INPUT, low_memory=False)
n_start = len(df.columns)
print(f"Loaded: {len(df):,} rows × {n_start} columns\n")

dropped = {}

# ── 1. LABEL LEAKAGE — these build the labels, can't be features ──
leaky = [
    "RUG_SIGNALS", "RUG_SCORE", "RUG_LABEL",
    "SIG_DRAINED", "SIG_NO_PRICE", "SIG_INACTIVE", "SIG_SHORT_LIFE",
    "SIG_FEW_TXN", "SIG_NO_NAME", "SIG_MUTABLE", "SIG_NO_METADATA", "SIG_NO_IMAGE",
]
found = [c for c in leaky if c in df.columns]
df.drop(columns=found, inplace=True, errors="ignore")
dropped["Label leakage"] = found
print(f"  1. Dropped {len(found)} label-leaking columns:")
for c in found:
    print(f"     - {c}")

# ── 2. DUPLICATE COLUMNS ──
dupes = {
    "HAS_AUTHORITY": "= MINT_AUTHORITY_ACTIVE (r=1.0, identical)",
    "IS_MUTABLE": "= SIG_MUTABLE (just dropped, keep IS_MUTABLE for Helius parity)... actually SIG_MUTABLE is already dropped",
}
# HAS_AUTHORITY is the only true remaining dupe
dupe_cols = ["HAS_AUTHORITY"]
found = [c for c in dupe_cols if c in df.columns]
df.drop(columns=found, inplace=True, errors="ignore")
dropped["Duplicates"] = found
print(f"\n  2. Dropped {len(found)} duplicate columns:")
for c in found:
    print(f"     - {c}  ({dupes.get(c, '')})")

# ── 3. FAKE GECKOTERMINAL COLUMNS (99% constant, r=-1.0 artifact) ──
# These have data for ~3,598 rows but 99.2% is ONE token's value
# Making them appear r=-1.0 which is completely fake
gt_fake = [
    "gt_base_price_usd", "gt_fdv_usd", "gt_market_cap_usd", "gt_reserve_usd",
    "gt_vol_24h", "gt_vol_6h", "gt_vol_1h", "gt_price_pct_1h", "gt_price_pct_5m",
    "gt_txns_24h_buys", "gt_txns_24h_sells",
]
found = [c for c in gt_fake if c in df.columns]
df.drop(columns=found, inplace=True, errors="ignore")
dropped["GeckoTerminal fake (99% constant)"] = found
print(f"\n  3. Dropped {len(found)} fake GeckoTerminal columns (99% constant → r=-1.0 artifact):")
for c in found:
    print(f"     - {c}")

# Keep: gt_pool_count (not constant), gt_pool_name, gt_pool_dex, gt_price_pct_24h, gt_pool_created
gt_kept = [c for c in df.columns if c.startswith("gt_")]
print(f"     Kept {len(gt_kept)} GT columns: {gt_kept}")

# ── 4. NEAR-CONSTANT / ZERO-INFO COLUMNS ──
constant = []
for col in df.select_dtypes(include=[np.number]).columns:
    s = df[col].dropna()
    if len(s) < 100:
        continue
    mode_pct = s.value_counts(normalize=True).iloc[0]
    if mode_pct > 0.999:  # 99.9% same value
        constant.append(col)

# Don't drop binary features that happen to be skewed (those are fine for tree models)
# Only drop truly useless ones
skip_keep = {"derived_single_drain_flag", "derived_has_price"}  # these are useful despite skew
constant = [c for c in constant if c not in skip_keep]

df.drop(columns=constant, inplace=True, errors="ignore")
dropped["Near-constant (>99.9%)"] = constant
print(f"\n  4. Dropped {len(constant)} near-constant columns (>99.9% same value):")
for c in constant:
    print(f"     - {c}")

# ── 5. RugCheck columns with only 48 rows of data ──
# These have data for only 48 labeled tokens — too sparse to be reliable
# BUT we keep them because the batch enrichment will fill them later
rc_sparse = [c for c in df.columns if c.startswith("RC_") and c not in ["RC_SCORE", "RC_SCORE_NORM"]]
rc_fills = {c: df[c].notna().sum() for c in rc_sparse}
rc_very_sparse = [c for c in rc_sparse if rc_fills.get(c, 0) < 100]
print(f"\n  5. RugCheck sparse columns (kept but flagged, <100 rows of data):")
for c in rc_very_sparse:
    print(f"     ⚠ {c}  (fill={rc_fills[c]})")

# ── 6. Non-feature columns (IDs, artifacts) ──
non_feature = ["LAST_SWAP_TX_ID", "INACTIVITY_STATUS", "RUG_LABEL_vl"]
found = [c for c in non_feature if c in df.columns]
df.drop(columns=found, inplace=True, errors="ignore")
dropped["Non-features/IDs"] = found
print(f"\n  6. Dropped {len(found)} non-feature columns: {found}")

# ── Summary ──
n_end = len(df.columns)
total_dropped = sum(len(v) for v in dropped.values())

print(f"\n{'=' * 70}")
print(f"  CLEANUP COMPLETE")
print(f"  Before: {n_start} columns → After: {n_end} columns (dropped {total_dropped})")
print(f"{'=' * 70}")

# Source breakdown
sources = {
    "Helius":         [c for c in df.columns if c.upper() in ["TOKEN_NAME","TOKEN_SYMBOL","TOKEN_DECIMALS","TOKEN_SUPPLY","TOKEN_STANDARD","TOKEN_PROGRAM","TOKEN_PRICE_USD","TOKEN_PRICE_CURRENCY","HAS_METADATA","HAS_IMAGE","HAS_JSON_URI","JSON_URI_DOMAIN","IS_MUTABLE","IS_BURNT","IS_COMPRESSED","IS_FROZEN","MINT_AUTHORITY","MINT_AUTHORITY_ACTIVE","FREEZE_AUTHORITY","FREEZE_AUTHORITY_ACTIVE","ROYALTY_PCT","EDITION_TOTAL_SUPPLY","NUM_CREATORS","CREATOR_VERIFIED","OWNER"]],
    "GoPlus":         [c for c in df.columns if c.startswith("gp_")],
    "RugCheck":       [c for c in df.columns if c.startswith(("RC_", "rc_"))],
    "GeckoTerminal":  [c for c in df.columns if c.startswith("gt_")],
    "SolRPDS":        [c for c in df.columns if c in ["TOTAL_ADDED_LIQUIDITY","TOTAL_REMOVED_LIQUIDITY","NUM_LIQUIDITY_ADDS","NUM_LIQUIDITY_REMOVES","ADD_TO_REMOVE_RATIO","LIFESPAN_H","REMOVED_RATIO"]],
    "Derived":        [c for c in df.columns if c.startswith("derived_")],
}
print(f"\n  Feature sources:")
for src, cols in sources.items():
    print(f"    {src:18s}: {len(cols):3d} columns")

# Verify no label leakage remains
remaining_leak = [c for c in df.columns if c.startswith("SIG_") or c in ["RUG_SIGNALS","RUG_SCORE","RUG_LABEL"]]
if remaining_leak:
    print(f"\n  ⚠ WARNING: Possible label leakage still present: {remaining_leak}")
else:
    print(f"\n  ✅ No label leakage detected")

df.to_csv(OUTPUT, index=False)
print(f"\n  Saved to: {OUTPUT}")
