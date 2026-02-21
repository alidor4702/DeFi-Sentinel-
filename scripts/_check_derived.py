"""Quick check: predictive power of new derived features."""
import pandas as pd, numpy as np

df = pd.read_csv("data/enriched/enriched_with_derived.csv", low_memory=False)
labels = pd.read_csv("data/enriched/verified_labels.csv")
df = df.merge(labels[["MINT","LIQUIDITY_POOL_ADDRESS","RUG_LABEL"]],
              on=["MINT","LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("","_vl"))
rug_mask = df["RUG_LABEL"].isin(["VERIFIED_RUG","LIKELY_RUG"])
legit_mask = df["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = df[rug_mask | legit_mask].copy()
labeled["IS_RUG"] = rug_mask[labeled.index].astype(int)

derived = [c for c in labeled.columns if c.startswith("derived_")]
print(f"Derived features: {len(derived)}")
print(f"Labeled: {len(labeled):,} rows\n")
print(f"{'Feature':45s} {'r':>8s} {'fill':>8s} {'rug_mean':>10s} {'legit_mean':>10s}")
print("-" * 85)
for col in sorted(derived):
    valid = labeled[[col, "IS_RUG"]].dropna()
    if len(valid) < 100:
        print(f"{col:45s} {'---':>8s} {len(valid):>8,} {'n/a':>10s} {'n/a':>10s}")
        continue
    r = valid[col].corr(valid["IS_RUG"])
    rug_mean = valid.loc[valid["IS_RUG"]==1, col].mean()
    leg_mean = valid.loc[valid["IS_RUG"]==0, col].mean()
    print(f"{col:45s} {r:+8.4f} {len(valid):8,} {rug_mean:10.4f} {leg_mean:10.4f}")
