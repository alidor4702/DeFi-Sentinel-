"""
DeFi Sentinel — Comprehensive Feature Analysis
Maps 82-feature live spec → available data, then runs statistical analysis.
Outputs a detailed report to stdout.
"""
import pandas as pd
import numpy as np
from collections import OrderedDict
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────
print("=" * 80)
print("  DeFi Sentinel — Feature Analysis Report")
print("=" * 80)

df = pd.read_csv("data/enriched/enriched_final.csv")
labels = pd.read_csv("data/enriched/verified_labels.csv")
df = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]], 
              on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vl"))

# Use verified labels for analysis
rug_mask = df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit_mask = df["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = df[rug_mask | legit_mask].copy()
labeled["IS_RUG"] = rug_mask[labeled.index].astype(int)

total_rows = len(df)
labeled_rows = len(labeled)
n_rug = labeled["IS_RUG"].sum()
n_legit = labeled_rows - n_rug

print(f"\nDataset: {total_rows:,} rows | Labeled subset: {labeled_rows:,} rows ({n_rug:,} rug, {n_legit:,} legit)")

# ─────────────────────────────────────────────────────────────
# 2. 82-FEATURE SPEC MAPPING
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("  PART 1: 82-Feature Live Spec Coverage")
print("=" * 80)

cols = set(df.columns)

# Full 82-feature spec with source groups
spec = OrderedDict()

# Helius (21)
spec["Helius"] = OrderedDict([
    ("token_name", ["TOKEN_NAME"]),
    ("token_symbol", ["TOKEN_SYMBOL"]),
    ("token_decimals", ["TOKEN_DECIMALS"]),
    ("token_supply", ["TOKEN_SUPPLY"]),
    ("mint_authority", ["MINT_AUTHORITY"]),
    ("mint_authority_revoked", ["MINT_AUTHORITY_ACTIVE"]),
    ("freeze_authority", ["FREEZE_AUTHORITY"]),
    ("freeze_authority_revoked", ["FREEZE_AUTHORITY_ACTIVE"]),
    ("update_authority", []),
    ("is_mutable", ["IS_MUTABLE"]),
    ("token_standard", ["TOKEN_STANDARD"]),
    ("token_program", ["TOKEN_PROGRAM"]),
    ("creation_timestamp", []),
    ("metadata_uri", ["HAS_JSON_URI"]),
    ("metadata_uri_reachable", []),
    ("has_image", ["HAS_IMAGE"]),
    ("has_description", []),
    ("has_website", []),
    ("has_twitter", []),
    ("has_telegram", []),
    ("creator_address", ["OWNER"]),
])

# Creator Wallet (6)
spec["Creator Wallet"] = OrderedDict([
    ("creator_sol_balance", []),
    ("creator_wallet_age_hours", []),
    ("creator_token_count", []),
    ("creator_tx_count", []),
    ("creator_prev_tokens_rugged", []),
    ("creator_nft_count", []),
])

# RugCheck (18)
spec["RugCheck"] = OrderedDict([
    ("rc_score", ["RC_SCORE", "rc_score"]),
    ("rc_risk_level", ["rc_top_risk_level"]),
    ("rc_risk_count", ["RC_NUM_RISKS", "rc_risks_count"]),
    ("rc_mint_authority_disabled", ["RC_MINT_AUTHORITY", "rc_mint_authority"]),
    ("rc_freeze_authority_disabled", ["RC_FREEZE_AUTHORITY", "rc_freeze_authority"]),
    ("rc_mutable_metadata", []),
    ("rc_top10_holder_pct", ["rc_top_holders_pct"]),
    ("rc_top_holder_pct", ["RC_TOP_HOLDER_PCT"]),
    ("rc_lp_locked", []),
    ("rc_lp_lock_pct", []),
    ("rc_lp_lock_duration_days", []),
    ("rc_lp_burned", []),
    ("rc_single_holder_ownership", []),
    ("rc_high_concentration", []),
    ("rc_low_liquidity", []),
    ("rc_copycat_token", []),
    ("rc_total_market_liquidity", ["RC_TOTAL_MARKET_LIQ", "rc_total_market_liq"]),
    ("rc_num_markets", []),
])

# GeckoTerminal (25)
spec["GeckoTerminal"] = OrderedDict([
    ("gt_pool_count", ["gt_pool_count"]),
    ("gt_pool_address", []),
    ("gt_pool_name", ["gt_pool_name"]),
    ("gt_dex", ["gt_pool_dex"]),
    ("gt_base_token_price_usd", ["gt_base_price_usd"]),
    ("gt_quote_token_price_usd", []),
    ("gt_fdv_usd", ["gt_fdv_usd"]),
    ("gt_market_cap_usd", ["gt_market_cap_usd"]),
    ("gt_reserve_usd", ["gt_reserve_usd"]),
    ("gt_volume_5m", []),
    ("gt_volume_1h", ["gt_vol_1h"]),
    ("gt_volume_6h", ["gt_vol_6h"]),
    ("gt_volume_24h", ["gt_vol_24h"]),
    ("gt_price_change_5m", ["gt_price_pct_5m"]),
    ("gt_price_change_1h", ["gt_price_pct_1h"]),
    ("gt_price_change_6h", []),
    ("gt_price_change_24h", ["gt_price_pct_24h"]),
    ("gt_tx_count_5m_buys", []),
    ("gt_tx_count_5m_sells", []),
    ("gt_tx_count_1h_buys", []),
    ("gt_tx_count_1h_sells", []),
    ("gt_tx_count_24h_buys", ["gt_txns_24h_buys"]),
    ("gt_tx_count_24h_sells", ["gt_txns_24h_sells"]),
    ("gt_buy_sell_ratio_1h", []),
    ("gt_pool_age_hours", ["gt_pool_created"]),
])

# Jupiter (5)
spec["Jupiter"] = OrderedDict([
    ("jup_listed", []),
    ("jup_strict_list", []),
    ("jup_daily_volume", []),
    ("jup_price_usd", []),
    ("jup_tags", []),
])

# Derived (7)
spec["Derived"] = OrderedDict([
    ("liquidity_to_fdv_ratio", []),
    ("sell_pressure_score", []),
    ("metadata_completeness", []),
    ("authority_risk_score", []),
    ("wallet_freshness_flag", []),
    ("consensus_risk", []),
    ("price_liquidity_divergence", []),
])

# Tally
total_spec = sum(len(g) for g in spec.values())
covered_all = []
missing_all = []
source_summary = {}

for source, features in spec.items():
    covered = []
    missing = []
    for feat_name, col_matches in features.items():
        found = [c for c in col_matches if c in cols]
        if found:
            fill = df[found[0]].notna().sum() / total_rows * 100
            covered.append((feat_name, found[0], fill))
            covered_all.append((feat_name, source, found[0], fill))
        else:
            missing.append(feat_name)
            missing_all.append((feat_name, source))
    source_summary[source] = {"total": len(features), "covered": len(covered), "missing": len(missing)}
    
    # Print per-source
    print(f"\n{'─' * 60}")
    print(f"  {source} ({len(covered)}/{len(features)} available)")
    print(f"{'─' * 60}")
    
    if covered:
        print("  ✅ AVAILABLE:")
        for feat, col, fill in covered:
            fill_bar = "█" * int(fill / 5) + "░" * (20 - int(fill / 5))
            marker = "⚠️ LOW" if fill < 20 else ""
            print(f"     {feat:35s} → {col:30s} [{fill_bar}] {fill:5.1f}% {marker}")
    
    if missing:
        print("  ❌ MISSING:")
        for feat in missing:
            print(f"     {feat}")

# Summary table
print(f"\n{'=' * 80}")
print(f"  COVERAGE SUMMARY: {len(covered_all)}/{total_spec} features available ({100*len(covered_all)/total_spec:.1f}%)")
print(f"{'=' * 80}")
print(f"\n  {'Source':<20s} {'Have':>5s} {'Missing':>8s} {'Total':>6s} {'Coverage':>10s}")
print(f"  {'─' * 49}")
for source, s in source_summary.items():
    pct = 100 * s['covered'] / s['total'] if s['total'] > 0 else 0
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    print(f"  {source:<20s} {s['covered']:>5d} {s['missing']:>8d} {s['total']:>6d} [{bar}] {pct:.0f}%")
print(f"  {'─' * 49}")
print(f"  {'TOTAL':<20s} {len(covered_all):>5d} {len(missing_all):>8d} {total_spec:>6d} [{100*len(covered_all)/total_spec:.0f}%]")

# ─────────────────────────────────────────────────────────────
# 3. EXTRA FEATURES NOT IN SPEC (bonus columns in our CSV)
# ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"  BONUS: Columns in CSV NOT in 82-feature spec")
print(f"{'=' * 80}")

spec_cols = set()
for source, features in spec.items():
    for feat_name, col_matches in features.items():
        for c in col_matches:
            spec_cols.add(c)

# Also exclude internal/identity columns
internal = {"LIQUIDITY_POOL_ADDRESS", "MINT", "LAST_SWAP_TX_ID", "INACTIVITY_STATUS",
            "FIRST_POOL_ACTIVITY_TIMESTAMP", "LAST_POOL_ACTIVITY_TIMESTAMP", "LAST_SWAP_TIMESTAMP",
            "RUG_LABEL", "RUG_LABEL_vl", "IS_RUG"}
# Columns from verified labels / internal signals
signal_cols = {c for c in df.columns if c.startswith("SIG_") or c in 
               ["RUG_SIGNALS", "RUG_SCORE", "FIRST", "LAST", "LIFESPAN_H", "REMOVED_RATIO"]}

bonus = sorted(set(df.columns) - spec_cols - internal - signal_cols)
bonus_data = []
for col in bonus:
    if col in internal or col.startswith("SIG_") or col in signal_cols:
        continue
    fill = df[col].notna().sum() / total_rows * 100
    bonus_data.append((col, fill))

# Categorize bonus features
print(f"\n  We have {len(bonus_data)} additional columns beyond the 82-feature spec:")
for col, fill in sorted(bonus_data, key=lambda x: -x[1]):
    source = "Helius" if col.startswith(("TOKEN_", "HAS_", "IS_", "ROYALTY", "EDITION", "NUM_C", "CREATOR_V", "JSON_URI")) \
             else "RugCheck" if col.startswith(("RC_", "rc_")) \
             else "GeckoTerminal" if col.startswith("gt_") \
             else "GoPlus" if col.startswith("gp_") \
             else "SolRPDS" if col in ["TOTAL_ADDED_LIQUIDITY", "TOTAL_REMOVED_LIQUIDITY", "NUM_LIQUIDITY_ADDS", "NUM_LIQUIDITY_REMOVES", "ADD_TO_REMOVE_RATIO"] \
             else "Other"
    print(f"     {col:35s} [{source:15s}] {fill:5.1f}% filled")


# ─────────────────────────────────────────────────────────────
# 4. FEATURE-BY-FEATURE STATISTICAL ANALYSIS
# ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"  PART 2: Feature Statistical Analysis (Rug vs Legit)")
print(f"{'=' * 80}")
print(f"  Using labeled subset: {labeled_rows:,} rows ({n_rug:,} rug, {n_legit:,} legit)")

# Collect all numeric features
numeric_cols = []
for col in labeled.columns:
    if col in internal or col in signal_cols or col == "IS_RUG" or col.endswith("_vl"):
        continue
    if labeled[col].dtype in ['float64', 'int64', 'float32', 'int32']:
        non_null = labeled[col].notna().sum()
        if non_null > 100:  # at least 100 non-null values
            numeric_cols.append(col)

print(f"\n  Analyzing {len(numeric_cols)} numeric features with >100 non-null values\n")

# For each feature: compute rug mean, legit mean, effect size, fill rate, correlation
analysis_results = []

for col in numeric_cols:
    rug_data = labeled.loc[labeled["IS_RUG"] == 1, col].dropna()
    legit_data = labeled.loc[labeled["IS_RUG"] == 0, col].dropna()
    
    fill_total = labeled[col].notna().sum() / labeled_rows * 100
    fill_rug = len(rug_data) / n_rug * 100 if n_rug > 0 else 0
    fill_legit = len(legit_data) / n_legit * 100 if n_legit > 0 else 0
    
    if len(rug_data) < 10 or len(legit_data) < 10:
        continue
    
    rug_mean = rug_data.mean()
    legit_mean = legit_data.mean()
    rug_median = rug_data.median()
    legit_median = legit_data.median()
    
    # Cohen's d effect size
    pooled_std = np.sqrt((rug_data.std()**2 + legit_data.std()**2) / 2)
    cohens_d = abs(rug_mean - legit_mean) / pooled_std if pooled_std > 0 else 0
    
    # Point-biserial correlation with IS_RUG
    valid = labeled[[col, "IS_RUG"]].dropna()
    if len(valid) > 50:
        corr = valid[col].corr(valid["IS_RUG"])
    else:
        corr = 0
    
    # Determine source
    if col.startswith(("gp_",)):
        source = "GoPlus"
    elif col.startswith(("gt_",)):
        source = "GeckoTerminal"
    elif col.startswith(("RC_", "rc_")):
        source = "RugCheck"
    elif col in ["TOTAL_ADDED_LIQUIDITY", "TOTAL_REMOVED_LIQUIDITY", "NUM_LIQUIDITY_ADDS", 
                 "NUM_LIQUIDITY_REMOVES", "ADD_TO_REMOVE_RATIO"]:
        source = "SolRPDS"
    else:
        source = "Helius"
    
    analysis_results.append({
        "feature": col,
        "source": source,
        "fill_%": fill_total,
        "fill_rug_%": fill_rug,
        "fill_legit_%": fill_legit,
        "rug_mean": rug_mean,
        "legit_mean": legit_mean,
        "rug_median": rug_median,
        "legit_median": legit_median,
        "cohens_d": cohens_d,
        "correlation": corr,
        "abs_corr": abs(corr),
    })

results_df = pd.DataFrame(analysis_results).sort_values("abs_corr", ascending=False)

# Print top features by correlation
print(f"  {'─' * 100}")
print(f"  TOP FEATURES BY CORRELATION WITH RUG LABEL (|r| > 0.05)")
print(f"  {'─' * 100}")
print(f"  {'Feature':<35s} {'Source':<15s} {'Fill%':>6s} {'Rug Mean':>12s} {'Legit Mean':>12s} {'Cohen d':>8s} {'Corr':>8s} {'Signal'}")
print(f"  {'─' * 100}")

for _, row in results_df.iterrows():
    if row["abs_corr"] < 0.05:
        continue
    direction = "↑ RUG" if row["correlation"] > 0 else "↓ RUG"
    strength = "🔴 STRONG" if row["abs_corr"] > 0.3 else "🟠 MEDIUM" if row["abs_corr"] > 0.15 else "🟡 WEAK"
    
    # Format numbers nicely
    rug_m = f"{row['rug_mean']:.4g}"
    leg_m = f"{row['legit_mean']:.4g}"
    
    print(f"  {row['feature']:<35s} {row['source']:<15s} {row['fill_%']:>5.1f}% {rug_m:>12s} {leg_m:>12s} {row['cohens_d']:>8.3f} {row['correlation']:>+8.4f} {direction} {strength}")

# Print features with < 0.05 correlation
print(f"\n  {'─' * 80}")
print(f"  WEAK/NO-SIGNAL FEATURES (|r| < 0.05)")
print(f"  {'─' * 80}")
weak = results_df[results_df["abs_corr"] < 0.05]
for _, row in weak.iterrows():
    print(f"  {row['feature']:<35s} {row['source']:<15s} corr={row['correlation']:>+.4f}  fill={row['fill_%']:.1f}%")

# ─────────────────────────────────────────────────────────────
# 5. SOURCE-LEVEL ANALYSIS
# ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"  PART 3: Analysis by Data Source")
print(f"{'=' * 80}")

for source in ["Helius", "SolRPDS", "RugCheck", "GeckoTerminal", "GoPlus"]:
    src_feats = results_df[results_df["source"] == source].sort_values("abs_corr", ascending=False)
    if len(src_feats) == 0:
        print(f"\n  {source}: No analyzable features")
        continue
    
    avg_fill = src_feats["fill_%"].mean()
    avg_corr = src_feats["abs_corr"].mean()
    max_corr = src_feats["abs_corr"].max()
    strong = (src_feats["abs_corr"] > 0.15).sum()
    
    print(f"\n  {'─' * 70}")
    print(f"  {source} — {len(src_feats)} numeric features")
    print(f"  Avg fill: {avg_fill:.1f}% | Avg |corr|: {avg_corr:.4f} | Max |corr|: {max_corr:.4f} | Strong (>0.15): {strong}")
    print(f"  {'─' * 70}")
    
    for _, row in src_feats.head(10).iterrows():
        ac = row["abs_corr"] if not np.isnan(row["abs_corr"]) else 0
        bar_len = min(40, int(ac * 40))
        bar = "█" * bar_len + "░" * (40 - bar_len)
        print(f"  {row['feature']:<30s} [{bar}] r={row['correlation']:>+.4f} fill={row['fill_%']:.1f}%")

# ─────────────────────────────────────────────────────────────
# 6. LIVE-INFERENCE FEATURE READINESS
# ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"  PART 4: Live-Inference Readiness Assessment")
print(f"{'=' * 80}")

# Features that are BOTH in 82-spec AND have strong signal
print(f"\n  Features in 82-feature spec with |corr| > 0.05 and fill > 5%:")
live_ready = []
for feat_name, source, col, fill in covered_all:
    match = results_df[results_df["feature"] == col]
    if len(match) > 0:
        corr = match.iloc[0]["abs_corr"]
        raw_corr = match.iloc[0]["correlation"]
        if corr > 0.05 and fill > 5:
            live_ready.append((feat_name, source, col, fill, raw_corr, corr))

live_ready.sort(key=lambda x: -x[5])
print(f"\n  {'Spec Feature':<35s} {'Source':<15s} {'Column':<30s} {'Fill%':>6s} {'Corr':>8s}")
print(f"  {'─' * 100}")
for feat, src, col, fill, raw_c, abs_c in live_ready:
    strength = "🔴" if abs_c > 0.3 else "🟠" if abs_c > 0.15 else "🟡"
    print(f"  {feat:<35s} {src:<15s} {col:<30s} {fill:>5.1f}% {raw_c:>+.4f} {strength}")

print(f"\n  → {len(live_ready)} features ready for live inference with meaningful signal")

# Features in spec but NO signal
print(f"\n  Features in 82-feature spec with NO meaningful signal (|corr| < 0.05 or too low fill):")
no_signal = []
for feat_name, source, col, fill in covered_all:
    match = results_df[results_df["feature"] == col]
    if len(match) > 0:
        corr = match.iloc[0]["abs_corr"]
        if corr < 0.05 or fill < 5:
            no_signal.append((feat_name, source, col, fill, match.iloc[0]["correlation"]))
    else:
        no_signal.append((feat_name, source, col, fill, 0.0))

for feat, src, col, fill, raw_c in no_signal:
    reason = "low fill" if fill < 5 else "weak signal"
    print(f"  ⚪ {feat:<35s} {src:<15s} {col:<30s} fill={fill:.1f}% corr={raw_c:+.4f} ({reason})")

# ─────────────────────────────────────────────────────────────
# 7. CATEGORICAL FEATURE ANALYSIS
# ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"  PART 5: Categorical Feature Analysis")
print(f"{'=' * 80}")

cat_features = {
    "TOKEN_STANDARD": "Helius",
    "TOKEN_PROGRAM": "Helius", 
    "JSON_URI_DOMAIN": "Helius",
    "RC_TOKEN_TYPE": "RugCheck",
    "rc_top_risk": "RugCheck",
    "rc_top_risk_level": "RugCheck",
    "gt_pool_dex": "GeckoTerminal",
}

for col, source in cat_features.items():
    if col not in labeled.columns:
        continue
    fill = labeled[col].notna().sum() / labeled_rows * 100
    if fill < 1:
        print(f"\n  {col} ({source}): fill too low ({fill:.1f}%), skipping")
        continue
    
    print(f"\n  {col} ({source}) — {fill:.1f}% filled")
    
    # Cross-tab with IS_RUG
    ct = pd.crosstab(labeled[col].fillna("(null)"), labeled["IS_RUG"], margins=True)
    ct.columns = ["Legit", "Rug", "Total"]
    ct["Rug%"] = (ct["Rug"] / ct["Total"] * 100).round(1)
    ct = ct.sort_values("Total", ascending=False).head(10)
    
    print(f"  {'Value':<30s} {'Legit':>8s} {'Rug':>8s} {'Total':>8s} {'Rug%':>8s}")
    print(f"  {'─' * 65}")
    for idx, row in ct.iterrows():
        rug_pct = row["Rug%"]
        marker = "🔴" if rug_pct > 70 else "🟠" if rug_pct > 50 else "🟢" if rug_pct < 30 else ""
        print(f"  {str(idx):<30s} {int(row['Legit']):>8d} {int(row['Rug']):>8d} {int(row['Total']):>8d} {rug_pct:>7.1f}% {marker}")

# ─────────────────────────────────────────────────────────────
# 8. FINAL SUMMARY FOR REPORT
# ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"  SUMMARY — Key Findings for Report")
print(f"{'=' * 80}")

print(f"""
  82-Feature Spec Coverage:
  ─────────────────────────
  • {len(covered_all)}/82 features mapped to existing columns ({100*len(covered_all)/total_spec:.1f}%)
  • {len(missing_all)}/82 features missing ({100*len(missing_all)/total_spec:.1f}%)
  
  Coverage by Source:""")
for source, s in source_summary.items():
    pct = 100 * s['covered'] / s['total'] if s['total'] > 0 else 0
    print(f"    {source:<20s}: {s['covered']:>2d}/{s['total']:<2d} ({pct:.0f}%)")

strong_feats = results_df[results_df["abs_corr"] > 0.15]
medium_feats = results_df[(results_df["abs_corr"] > 0.05) & (results_df["abs_corr"] <= 0.15)]
weak_feats = results_df[results_df["abs_corr"] <= 0.05]

print(f"""
  Feature Signal Strength:
  ────────────────────────
  • 🔴 Strong (|r| > 0.15): {len(strong_feats)} features
  • 🟠 Medium (0.05 < |r| ≤ 0.15): {len(medium_feats)} features  
  • ⚪ Weak (|r| ≤ 0.05): {len(weak_feats)} features
  
  Top 5 Most Predictive Features:""")
for i, (_, row) in enumerate(results_df.head(5).iterrows(), 1):
    print(f"    {i}. {row['feature']:<30s} (r={row['correlation']:+.4f}, source={row['source']})")

# Source contribution
source_power = results_df.groupby("source").agg(
    n_features=("feature", "count"),
    avg_abs_corr=("abs_corr", "mean"),
    max_abs_corr=("abs_corr", "max"),
    strong_count=("abs_corr", lambda x: (x > 0.15).sum()),
).sort_values("avg_abs_corr", ascending=False)

print(f"""
  Source Predictive Power:
  ────────────────────────""")
for src, row in source_power.iterrows():
    print(f"    {src:<15s}: {int(row['n_features']):>3d} features, avg|r|={row['avg_abs_corr']:.4f}, max|r|={row['max_abs_corr']:.4f}, {int(row['strong_count'])} strong")

# What's most needed
print(f"""
  Critical Gaps (Missing features with highest expected impact):
  ─────────────────────────────────────────────────────────────
  1. Creator Wallet (0/6) — creator history is among the top rug indicators
     in the literature. Requires Helius RPC calls for wallet age, tx count,
     previous tokens rugged.
  2. Jupiter (0/5) — listing status on Jupiter is a strong legitimacy signal.
     If a token isn't on Jupiter's verified list, it's suspicious.
  3. Derived features (0/7) — these are computed from other features and can
     be added without any API calls.
  4. RugCheck LP locking (3/18 missing) — lp_locked, lp_lock_pct, lp_burned
     are critical rug indicators available from RugCheck.
  5. GeckoTerminal granular data (9/25 missing) — 5m volumes, 1h buy/sell
     counts, buy_sell_ratio for real-time detection.
""")

# Save analysis results to CSV
results_df.to_csv("data/enriched/feature_analysis_results.csv", index=False)
print(f"  📁 Saved detailed analysis to data/enriched/feature_analysis_results.csv")
print(f"{'=' * 80}")
