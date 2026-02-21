"""Quick analysis of the enriched multi-source dataset."""
import pandas as pd
import os

# Load
path = "./output/enriched_20.csv"
if not os.path.exists(path):
    path = "./output/enriched_multi_source.csv"
df = pd.read_csv(path, low_memory=False)

print(f"{'='*70}")
print(f"  DEFI SENTINEL — ENRICHED DATA ANALYSIS")
print(f"{'='*70}")
print(f"  Total rows: {len(df):,}")
print(f"  Total columns: {len(df.columns)}")
print(f"  Original: 12 | New from APIs: {len(df.columns) - 12}")

# ── Label distribution ──
print(f"\n{'─'*70}")
print("  LABEL DISTRIBUTION")
print(f"{'─'*70}")
for status, count in df["INACTIVITY_STATUS"].value_counts().items():
    pct = count / len(df) * 100
    print(f"  {status:12s}  {count:>7,}  ({pct:.1f}%)")

# ── RugCheck analysis ──
rc = df[df["RC_SCORE"].notna()].copy()
if len(rc) > 0:
    print(f"\n{'─'*70}")
    print(f"  RUGCHECK ANALYSIS ({len(rc):,} rows with data)")
    print(f"{'─'*70}")
    
    for status in ["Active", "Inactive"]:
        sub = rc[rc["INACTIVITY_STATUS"] == status]["RC_SCORE"]
        if len(sub) > 0:
            print(f"\n  {status} pools:")
            print(f"    Count:  {len(sub):,}")
            print(f"    Median: {sub.median():,.0f}")
            print(f"    Mean:   {sub.mean():,.0f}")
            print(f"    Min:    {sub.min():,.0f}")
            print(f"    Max:    {sub.max():,.0f}")
    
    # Show how well RC_SCORE separates labels
    print(f"\n  SEPARATION POWER:")
    thresholds = [100, 1000, 5000, 10000]
    for t in thresholds:
        active_above = (rc[(rc["INACTIVITY_STATUS"] == "Active") & (rc["RC_SCORE"] > t)]).shape[0]
        active_total = (rc[rc["INACTIVITY_STATUS"] == "Active"]).shape[0]
        inactive_above = (rc[(rc["INACTIVITY_STATUS"] == "Inactive") & (rc["RC_SCORE"] > t)]).shape[0]
        inactive_total = (rc[rc["INACTIVITY_STATUS"] == "Inactive"]).shape[0]
        
        a_pct = active_above / active_total * 100 if active_total > 0 else 0
        i_pct = inactive_above / inactive_total * 100 if inactive_total > 0 else 0
        print(f"    Score > {t:>6,}: Active={a_pct:5.1f}% flagged | Inactive={i_pct:5.1f}% flagged")

    # Risk breakdown
    print(f"\n  TOP RISK LABELS (from RugCheck):")
    risk_names = rc["RC_RISK_NAMES"].dropna().str.split("|").explode()
    risk_names = risk_names[risk_names != ""]
    for risk, count in risk_names.value_counts().head(10).items():
        print(f"    {risk:45s}  {count:>5,}")

    # Mint/Freeze authority by label
    print(f"\n  MINT AUTHORITY ENABLED:")
    for status in ["Active", "Inactive"]:
        sub = rc[rc["INACTIVITY_STATUS"] == status]
        if len(sub) > 0:
            pct = sub["RC_MINT_AUTHORITY"].mean() * 100
            print(f"    {status:12s}: {pct:.1f}% have mint authority")

    print(f"\n  FREEZE AUTHORITY ENABLED:")
    for status in ["Active", "Inactive"]:
        sub = rc[rc["INACTIVITY_STATUS"] == status]
        if len(sub) > 0:
            pct = sub["RC_FREEZE_AUTHORITY"].mean() * 100
            print(f"    {status:12s}: {pct:.1f}% have freeze authority")

# ── GeckoTerminal analysis ──
gt = df[df["GT_RESERVE_USD"].notna()].copy()
if len(gt) > 0:
    print(f"\n{'─'*70}")
    print(f"  GECKOTERMINAL ANALYSIS ({len(gt):,} rows with data)")
    print(f"{'─'*70}")
    
    for status in ["Active", "Inactive"]:
        sub = gt[gt["INACTIVITY_STATUS"] == status]
        if len(sub) > 0:
            print(f"\n  {status} pools:")
            print(f"    Count:        {len(sub):,}")
            print(f"    Reserve USD:  median=${sub['GT_RESERVE_USD'].median():,.2f}  mean=${sub['GT_RESERVE_USD'].mean():,.2f}")
            print(f"    Volume 24h:   median=${sub['GT_VOL_24H'].median():,.2f}  mean=${sub['GT_VOL_24H'].mean():,.2f}")
            if "GT_POOL_AGE_DAYS" in sub.columns:
                age = sub["GT_POOL_AGE_DAYS"].dropna()
                if len(age) > 0:
                    print(f"    Pool age:     median={age.median():,.0f} days  mean={age.mean():,.0f} days")

# ── Sample enriched rows ──
print(f"\n{'─'*70}")
print("  SAMPLE ENRICHED TOKENS (first 5 with RugCheck data)")
print(f"{'─'*70}")
sample = rc.drop_duplicates("MINT").head(5)
for _, row in sample.iterrows():
    mint = row["MINT"]
    status = row["INACTIVITY_STATUS"]
    score = row["RC_SCORE"]
    risks = row.get("RC_RISK_NAMES", "")
    holders = row.get("RC_TOTAL_HOLDERS", "?")
    reserve = row.get("GT_RESERVE_USD", "N/A")
    
    emoji = "🟢" if status == "Active" else "🔴"
    risks_str = str(risks) if pd.notna(risks) else "None"
    reserve_str = f"${reserve:,.2f}" if pd.notna(reserve) else "N/A"
    print(f"\n  {emoji} Mint: {mint[:20]}...")
    print(f"     Label: {status} | RugCheck Score: {score:,.0f}")
    print(f"     Holders: {holders} | Pool Reserve: {reserve_str}")
    print(f"     Risks: {risks_str[:80]}")

print(f"\n{'='*70}")
print(f"  Results file: {os.path.abspath(path)}")
print(f"{'='*70}")
