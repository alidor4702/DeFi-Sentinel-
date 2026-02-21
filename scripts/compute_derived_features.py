"""
DeFi Sentinel — Derived Features (FREE, no API calls)
Computes 7+ derived features from existing data columns.
Run: python3 scripts/compute_derived_features.py
"""
import pandas as pd
import numpy as np
import os

INPUT  = "data/enriched/enriched_final.csv"
OUTPUT = "data/enriched/enriched_with_derived.csv"

print("=" * 70)
print("  DeFi Sentinel — Derived Feature Computation")
print("=" * 70)

df = pd.read_csv(INPUT, low_memory=False)
n_before = len(df.columns)
print(f"Loaded {len(df):,} rows × {n_before} columns")

# ────────────────────────────────────────────────────────────
# 1. LIQUIDITY DEPTH RATIO
#    How much liquidity was removed relative to what was added.
#    High ratio → drained → rug signal
# ────────────────────────────────────────────────────────────
df["derived_liquidity_depth_ratio"] = np.where(
    df["TOTAL_ADDED_LIQUIDITY"] > 0,
    df["TOTAL_REMOVED_LIQUIDITY"] / df["TOTAL_ADDED_LIQUIDITY"],
    np.nan
)
print(f"  ✓ derived_liquidity_depth_ratio  (fill={df['derived_liquidity_depth_ratio'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 2. ADD/REMOVE VELOCITY
#    Average liquidity change per event.
#    Rug pulls: few big adds, then one massive remove.
# ────────────────────────────────────────────────────────────
df["derived_avg_add_size"] = np.where(
    df["NUM_LIQUIDITY_ADDS"] > 0,
    df["TOTAL_ADDED_LIQUIDITY"] / df["NUM_LIQUIDITY_ADDS"],
    0
)
df["derived_avg_remove_size"] = np.where(
    df["NUM_LIQUIDITY_REMOVES"] > 0,
    df["TOTAL_REMOVED_LIQUIDITY"] / df["NUM_LIQUIDITY_REMOVES"],
    0
)
# Ratio: if avg_remove >> avg_add, likely rug (one big drain)
df["derived_remove_add_size_ratio"] = np.where(
    df["derived_avg_add_size"] > 0,
    df["derived_avg_remove_size"] / df["derived_avg_add_size"],
    np.nan
)
print(f"  ✓ derived_avg_add_size             (fill={df['derived_avg_add_size'].notna().sum():,})")
print(f"  ✓ derived_avg_remove_size          (fill={df['derived_avg_remove_size'].notna().sum():,})")
print(f"  ✓ derived_remove_add_size_ratio    (fill={df['derived_remove_add_size_ratio'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 3. DRAIN SPEED (% per hour)
#    How fast was liquidity drained relative to pool lifespan.
#    Instant drain = rug.
# ────────────────────────────────────────────────────────────
df["derived_drain_speed_pct_per_hour"] = np.where(
    (df["LIFESPAN_H"] > 0) & (df["TOTAL_ADDED_LIQUIDITY"] > 0),
    (df["TOTAL_REMOVED_LIQUIDITY"] / df["TOTAL_ADDED_LIQUIDITY"]) / df["LIFESPAN_H"] * 100,
    np.nan
)
print(f"  ✓ derived_drain_speed_pct_per_hour (fill={df['derived_drain_speed_pct_per_hour'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 4. TIME TO FIRST REMOVE (hours)
#    How long before liquidity was first pulled. Proxy using
#    FIRST_POOL_ACTIVITY_TIMESTAMP vs LAST_POOL_ACTIVITY_TIMESTAMP
# ────────────────────────────────────────────────────────────
# FIRST and LAST are already epoch timestamps
first_ts = pd.to_datetime(df["FIRST_POOL_ACTIVITY_TIMESTAMP"], errors="coerce")
last_ts  = pd.to_datetime(df["LAST_POOL_ACTIVITY_TIMESTAMP"], errors="coerce")
df["derived_pool_active_hours"] = (last_ts - first_ts).dt.total_seconds() / 3600
df["derived_pool_active_hours"] = df["derived_pool_active_hours"].clip(lower=0)
print(f"  ✓ derived_pool_active_hours        (fill={df['derived_pool_active_hours'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 5. METADATA COMPLETENESS SCORE (0-1)
#    Tokens with no name, no image, no URI = likely rug.
# ────────────────────────────────────────────────────────────
meta_cols = []
for col in ["HAS_METADATA", "HAS_IMAGE", "HAS_JSON_URI"]:
    if col in df.columns:
        meta_cols.append(col)

# TOKEN_NAME exists → has name
df["_has_name"] = (~df["TOKEN_NAME"].isna() & (df["TOKEN_NAME"] != "")).astype(int)
# TOKEN_SYMBOL exists
df["_has_symbol"] = (~df["TOKEN_SYMBOL"].isna() & (df["TOKEN_SYMBOL"] != "")).astype(int)

all_meta = meta_cols + ["_has_name", "_has_symbol"]
df["derived_metadata_completeness"] = df[all_meta].mean(axis=1)
df.drop(columns=["_has_name", "_has_symbol"], inplace=True)
print(f"  ✓ derived_metadata_completeness    (fill={df['derived_metadata_completeness'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 6. SUPPLY vs DECIMALS RATIO
#    Scam tokens often have extreme supply + weird decimals.
#    log10(supply) / decimals — abnormal ratios are suspicious.
# ────────────────────────────────────────────────────────────
df["derived_log_supply"] = np.log10(df["TOKEN_SUPPLY"].replace(0, np.nan).clip(lower=1))
df["derived_supply_decimal_ratio"] = np.where(
    df["TOKEN_DECIMALS"] > 0,
    df["derived_log_supply"] / df["TOKEN_DECIMALS"],
    np.nan
)
print(f"  ✓ derived_log_supply               (fill={df['derived_log_supply'].notna().sum():,})")
print(f"  ✓ derived_supply_decimal_ratio     (fill={df['derived_supply_decimal_ratio'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 7. LIQUIDITY EVENT INTENSITY
#    Total events / lifespan hours — how frantic was trading?
# ────────────────────────────────────────────────────────────
total_events = df["NUM_LIQUIDITY_ADDS"].fillna(0) + df["NUM_LIQUIDITY_REMOVES"].fillna(0)
df["derived_events_per_hour"] = np.where(
    df["LIFESPAN_H"] > 0,
    total_events / df["LIFESPAN_H"],
    np.nan
)
print(f"  ✓ derived_events_per_hour          (fill={df['derived_events_per_hour'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 8. SINGLE-REMOVE RUG INDICATOR
#    If NUM_LIQUIDITY_REMOVES == 1 and REMOVED_RATIO > 0.9 → classic rug
# ────────────────────────────────────────────────────────────
df["derived_single_drain_flag"] = (
    (df["NUM_LIQUIDITY_REMOVES"] == 1) &
    (df["REMOVED_RATIO"] > 0.9)
).astype(int)
print(f"  ✓ derived_single_drain_flag        (fill={df['derived_single_drain_flag'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 9. PRICE PRESENCE (binary)
#    Whether the token ever had a price quoted.
# ────────────────────────────────────────────────────────────
df["derived_has_price"] = (df["TOKEN_PRICE_USD"].notna() & (df["TOKEN_PRICE_USD"] > 0)).astype(int)
print(f"  ✓ derived_has_price                (fill={df['derived_has_price'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 10. URI DOMAIN RISK SCORE
#     Encode known URI domain rug rates as a numeric feature.
# ────────────────────────────────────────────────────────────
# Load labels to compute domain rug rates
labels = pd.read_csv("data/enriched/verified_labels.csv")
df_temp = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
                   on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vlbl"))

rug_m = df_temp["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit_m = df_temp["RUG_LABEL"] == "LIKELY_LEGIT"
lbl = df_temp[rug_m | legit_m].copy()
lbl["_is_rug"] = rug_m[lbl.index].astype(int)

domain_rates = lbl.groupby("JSON_URI_DOMAIN")["_is_rug"].agg(["mean", "count"]).reset_index()
domain_rates.columns = ["JSON_URI_DOMAIN", "domain_rug_rate", "domain_count"]
# Only use domains with enough samples
domain_rates = domain_rates[domain_rates["domain_count"] >= 20]
domain_map = dict(zip(domain_rates["JSON_URI_DOMAIN"], domain_rates["domain_rug_rate"]))

df["derived_uri_domain_rug_rate"] = df["JSON_URI_DOMAIN"].map(domain_map)
# Tokens with no URI → assign high risk (0.9); unknown domain → 0.5
no_uri_mask = df["JSON_URI_DOMAIN"].isna()
still_na = df["derived_uri_domain_rug_rate"].isna()
df.loc[still_na & no_uri_mask, "derived_uri_domain_rug_rate"] = 0.9
df.loc[still_na & ~no_uri_mask, "derived_uri_domain_rug_rate"] = 0.5
print(f"  ✓ derived_uri_domain_rug_rate      (fill={df['derived_uri_domain_rug_rate'].notna().sum():,})")

# ────────────────────────────────────────────────────────────
# 11. TOKEN STANDARD RISK SCORE
#     Encode token standard rug rates.
# ────────────────────────────────────────────────────────────
std_rates = lbl.groupby("TOKEN_STANDARD")["_is_rug"].agg(["mean", "count"]).reset_index()
std_rates.columns = ["TOKEN_STANDARD", "std_rug_rate", "std_count"]
std_rates = std_rates[std_rates["std_count"] >= 10]
std_map = dict(zip(std_rates["TOKEN_STANDARD"], std_rates["std_rug_rate"]))
df["derived_token_std_rug_rate"] = df["TOKEN_STANDARD"].map(std_map).fillna(0.5)
print(f"  ✓ derived_token_std_rug_rate       (fill={df['derived_token_std_rug_rate'].notna().sum():,})")

# ── Save ──
n_after = len(df.columns)
new_cols = [c for c in df.columns if c.startswith("derived_")]
print(f"\n{'=' * 70}")
print(f"  DONE: {n_before} → {n_after} columns (+{len(new_cols)} derived)")
print(f"  New features: {new_cols}")
print(f"  Saved to: {OUTPUT}")
df.to_csv(OUTPUT, index=False)
