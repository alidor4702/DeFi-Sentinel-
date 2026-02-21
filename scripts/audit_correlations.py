"""
DeFi Sentinel — Correlation Audit
Check for suspicious perfect correlations and sample-size artifacts.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("data/enriched/enriched_final.csv")
labels = pd.read_csv("data/enriched/verified_labels.csv")
df = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
              on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vl"))

rug_mask = df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit_mask = df["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = df[rug_mask | legit_mask].copy()
labeled["IS_RUG"] = rug_mask[labeled.index].astype(int)

num_cols = labeled.select_dtypes(include=[np.number]).columns.tolist()
num_cols = [c for c in num_cols if c != "IS_RUG"]

print(f"Labeled dataset: {len(labeled):,} rows ({labeled['IS_RUG'].sum():,} rug, {(~labeled['IS_RUG'].astype(bool)).sum():,} legit)")
print(f"Numeric columns: {len(num_cols)}")

# ── 1. Correlation with IS_RUG ──
print("\n" + "=" * 90)
print("TOP 30 features by |correlation| with IS_RUG")
print("=" * 90)

corr_with_rug = []
for col in num_cols:
    valid = labeled[[col, "IS_RUG"]].dropna()
    n = len(valid)
    if n < 10:
        continue
    r = valid[col].corr(valid["IS_RUG"])
    if np.isnan(r):
        continue
    n_rug = valid["IS_RUG"].sum()
    n_legit = n - n_rug
    corr_with_rug.append({
        "col": col, "r": r, "abs_r": abs(r),
        "n_valid": n, "n_rug": int(n_rug), "n_legit": int(n_legit),
        "fill_pct": n / len(labeled) * 100
    })

corr_with_rug.sort(key=lambda x: -x["abs_r"])

for i, row in enumerate(corr_with_rug[:30]):
    flag = ""
    if row["n_valid"] < 500:
        flag = " ⚠️ TINY SAMPLE"
    if row["abs_r"] > 0.95:
        flag += " 🚨 PERFECT"
    print(f"  {i+1:2d}. {row['col']:40s}  r={row['r']:+.4f}  "
          f"n={row['n_valid']:6,}  (rug={row['n_rug']:,}, legit={row['n_legit']:,})  "
          f"fill={row['fill_pct']:.1f}%{flag}")

# ── 2. Inter-feature pairs with |r| > 0.90 ──
print("\n" + "=" * 90)
print("FEATURE PAIRS WITH |r| > 0.90  (duplicate/redundant columns)")
print("=" * 90)

corr_matrix = labeled[num_cols].corr()
pairs = []
for i in range(len(num_cols)):
    for j in range(i + 1, len(num_cols)):
        r = corr_matrix.iloc[i, j]
        if abs(r) > 0.90 and not np.isnan(r):
            c1, c2 = num_cols[i], num_cols[j]
            n1 = labeled[c1].notna().sum()
            n2 = labeled[c2].notna().sum()
            pairs.append((c1, c2, r, n1, n2))

pairs.sort(key=lambda x: -abs(x[2]))
for c1, c2, r, n1, n2 in pairs:
    flag = " ⚠️ TINY" if min(n1, n2) < 500 else ""
    dup = " 🔴 DUPLICATE" if abs(r) > 0.99 else ""
    print(f"  {c1:35s} <-> {c2:35s}  r={r:+.4f}  fills=({n1:,}, {n2:,}){flag}{dup}")

# ── 3. Columns with near-zero variance (same value almost everywhere) ──
print("\n" + "=" * 90)
print("CONSTANT / NEAR-CONSTANT COLUMNS (>99% same value)")
print("=" * 90)

for col in num_cols:
    s = labeled[col].dropna()
    if len(s) < 10:
        continue
    mode_pct = s.value_counts(normalize=True).iloc[0] * 100
    if mode_pct > 99:
        mode_val = s.value_counts().index[0]
        print(f"  {col:40s}  mode={mode_val}  mode_pct={mode_pct:.1f}%  n={len(s):,}")

# ── 4. GeckoTerminal specifically — how many tokens? ──
print("\n" + "=" * 90)
print("GECKOTERMINAL COLUMNS — sample size check")
print("=" * 90)

gt_cols = [c for c in labeled.columns if c.startswith("gt_")]
for col in gt_cols:
    if labeled[col].dtype not in ["float64", "int64", "float32", "int32"]:
        print(f"  {col:35s}  type={labeled[col].dtype}  (non-numeric)")
        continue
    valid = labeled[col].dropna()
    n = len(valid)
    if n > 0:
        n_rug = labeled.loc[valid.index, "IS_RUG"].sum()
        n_legit = n - n_rug
        r = labeled.loc[valid.index, [col, "IS_RUG"]].corr().iloc[0, 1]
        print(f"  {col:35s}  n={n:5d}  rug={int(n_rug):4d}  legit={int(n_legit):4d}  r={r:+.4f}")
    else:
        print(f"  {col:35s}  n=0  (all NaN)")

# ── 5. GoPlus columns — sample check ──
print("\n" + "=" * 90)
print("GOPLUS COLUMNS — sample size check")
print("=" * 90)

gp_cols = [c for c in labeled.columns if c.startswith("gp_")]
for col in gp_cols:
    if labeled[col].dtype not in ["float64", "int64", "float32", "int32"]:
        print(f"  {col:35s}  type={labeled[col].dtype}  (non-numeric)")
        continue
    valid = labeled[col].dropna()
    n = len(valid)
    if n > 0:
        n_rug = labeled.loc[valid.index, "IS_RUG"].sum()
        n_legit = n - n_rug
        r = labeled.loc[valid.index, [col, "IS_RUG"]].corr().iloc[0, 1]
        print(f"  {col:35s}  n={n:5d}  rug={int(n_rug):4d}  legit={int(n_legit):4d}  r={r:+.4f}")
    else:
        print(f"  {col:35s}  n=0  (all NaN)")

# ── 6. Summary of data integrity issues ──
print("\n" + "=" * 90)
print("SUMMARY OF DATA INTEGRITY ISSUES")
print("=" * 90)

n_tiny = sum(1 for row in corr_with_rug if row["n_valid"] < 500 and row["abs_r"] > 0.3)
n_dup = sum(1 for _, _, r, _, _ in pairs if abs(r) > 0.99)
n_perfect = sum(1 for row in corr_with_rug if row["abs_r"] > 0.95)

print(f"  • Features with high correlation but tiny sample (<500 rows): {n_tiny}")
print(f"  • Duplicate column pairs (|r| > 0.99): {n_dup}")
print(f"  • Features with near-perfect rug correlation (|r| > 0.95): {n_perfect}")
print(f"  • GeckoTerminal columns with data in labeled set: {sum(1 for c in gt_cols if labeled[c].dtype in ['float64','int64'] and labeled[c].notna().sum() > 0)}")
print(f"  • GoPlus columns with data in labeled set: {sum(1 for c in gp_cols if labeled[c].dtype in ['float64','int64'] and labeled[c].notna().sum() > 0)}")
