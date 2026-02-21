"""Analyze deployer feature distributions in training data to determine proper defaults."""
import pandas as pd
import numpy as np

df = pd.read_csv("/Users/alidor/Desktop/Hackathon4/DeFiSentinel/data/enriched/enriched_v2.csv")
print(f"Total rows: {len(df)}")

# --- Find the label column ---
label = "rc_rugged"
print(f"\n=== Label: {label} ===")
print(f"  notna: {df[label].notna().sum()}")
print(f"  unique: {df[label].dropna().unique()}")
vc = df[label].value_counts(dropna=False)
print(f"  value_counts:\n{vc}")

# Create boolean label
y = df[label].fillna(False).astype(bool)
n_rug = y.sum()
n_legit = (~y).sum()
print(f"\nRug: {n_rug}  Legit: {n_legit}  Rug%: {100*n_rug/len(df):.1f}%")

# --- Deployer features ---
dep_cols = [c for c in df.columns if "deployer" in c.lower()]
print(f"\n=== Deployer columns ({len(dep_cols)}) ===")
for c in dep_cols:
    print(f"  {c}")

key_cols = [
    "feat_deployer_past_labeled",
    "feat_deployer_past_tokens",
    "feat_deployer_past_rugs",
    "feat_deployer_past_rug_rate",
    "feat_deployer_past_is_serial",
    "feat_deployer_token_count",
    "feat_deployer_rug_count",
    "feat_deployer_rug_rate",
    "feat_deployer_is_rug_factory",
    "feat_deployer_is_repeat",
]

print("\n=== Deployer feature distributions ===")
for c in key_cols:
    if c not in df.columns:
        print(f"  {c}: NOT FOUND")
        continue
    col = df[c]
    zeros = (col == 0).sum()
    nans = col.isna().sum()
    print(f"\n  {c}:")
    print(f"    zeros={zeros} ({100*zeros/len(df):.1f}%), NaN={nans}, mean={col.mean():.3f}, median={col.median():.1f}")
    print(f"    p25={col.quantile(0.25):.1f}, p75={col.quantile(0.75):.1f}, max={col.max():.1f}")

# --- CRITICAL: What happens when deployer_past_labeled == 0? ---
dpl = df["feat_deployer_past_labeled"]
print("\n=== CRITICAL: Rug rate when deployer_past_labeled == 0 ===")
mask_zero = dpl == 0
mask_nonzero = dpl > 0
rug_rate_zero = y[mask_zero].mean()
rug_rate_nonzero = y[mask_nonzero].mean()
print(f"  deployer_past_labeled == 0: n={mask_zero.sum()}, rug_rate={100*rug_rate_zero:.1f}%")
print(f"  deployer_past_labeled >  0: n={mask_nonzero.sum()}, rug_rate={100*rug_rate_nonzero:.1f}%")

# --- Rug rate at various deployer_past_labeled thresholds ---
print("\n=== Rug rate by deployer_past_labeled buckets ===")
bins = [0, 0.5, 1, 5, 10, 50, 100, 500, 10000]
for lo, hi in zip(bins, bins[1:]):
    mask = (dpl > lo) & (dpl <= hi)
    if mask.sum() > 0:
        rr = y[mask].mean()
        print(f"  ({lo}, {hi}]: n={mask.sum():>6}, rug_rate={100*rr:.1f}%")

# --- What do LEGIT tokens look like? ---
print("\n=== Deployer features for LEGIT tokens (rc_rugged=False) ===")
legit = df[~y]
for c in key_cols:
    if c in legit.columns:
        col = legit[c]
        print(f"  {c}: mean={col.mean():.2f}, median={col.median():.1f}, p25={col.quantile(0.25):.1f}, p75={col.quantile(0.75):.1f}")

# --- What do RUG tokens look like? ---
print("\n=== Deployer features for RUG tokens (rc_rugged=True) ===")
rugs = df[y]
for c in key_cols:
    if c in rugs.columns:
        col = rugs[c]
        print(f"  {c}: mean={col.mean():.2f}, median={col.median():.1f}, p25={col.quantile(0.25):.1f}, p75={col.quantile(0.75):.1f}")

# --- RECOMMENDATION ---
print("\n" + "="*60)
print("RECOMMENDATION FOR DEFAULT VALUES (unknown deployer)")
print("="*60)
# For tokens where we can't look up deployer history, we should
# use NEUTRAL values (between legit and rug medians) so the model
# focuses on other features instead of assuming rug
for c in key_cols:
    if c in df.columns:
        legit_med = legit[c].median()
        rug_med = rugs[c].median()
        neutral = (legit_med + rug_med) / 2
        print(f"  {c}: legit_median={legit_med:.1f}, rug_median={rug_med:.1f}, neutral={neutral:.2f}")
