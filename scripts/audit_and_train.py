"""
Full data audit + label analysis + live-feature training pipeline.
Answers: What data do we have? Are labels trustworthy? Can we train on live features?
"""
import os, json, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "enriched")

# ═══════════════════════════════════════════════════════════════════
# PART 1: DATA COVERAGE AUDIT
# ═══════════════════════════════════════════════════════════════════
print("=" * 70)
print("  PART 1: DATA COVERAGE AUDIT")
print("=" * 70)

df = pd.read_csv(os.path.join(DATA, "enriched_final.csv"), low_memory=False)
print(f"\nTotal rows: {len(df):,}")
print(f"Unique mints: {df['MINT'].nunique():,}")
print(f"Unique pools: {df['LIQUIDITY_POOL_ADDRESS'].nunique():,}")

# Per-source fill rates
sources = {
    "Helius (base)": ["TOKEN_NAME", "TOKEN_SUPPLY", "IS_MUTABLE", "HAS_IMAGE",
                       "MINT_AUTHORITY_ACTIVE", "FREEZE_AUTHORITY_ACTIVE", "TOKEN_DECIMALS"],
    "RugCheck (rc_)": [c for c in df.columns if c.startswith("rc_")],
    "GeckoTerminal (gt_)": [c for c in df.columns if c.startswith("gt_")],
    "GoPlus (gp_)": [c for c in df.columns if c.startswith("gp_")],
    "SolRPDS (historical)": ["TOTAL_ADDED_LIQUIDITY", "TOTAL_REMOVED_LIQUIDITY",
                              "NUM_LIQUIDITY_ADDS", "NUM_LIQUIDITY_REMOVES",
                              "LIFESPAN_H"],
}

print("\n── Source Fill Rates ──")
for src, cols in sources.items():
    existing = [c for c in cols if c in df.columns]
    if not existing:
        print(f"  {src}: NO COLUMNS FOUND")
        continue
    # A row "has data" if ANY column in the source is non-null
    has_data = df[existing].notna().any(axis=1).sum()
    pct = 100 * has_data / len(df)
    print(f"  {src}: {has_data:>7,} rows ({pct:5.1f}%) | {len(existing)} columns")

# GeckoTerminal detailed
gt_cols = [c for c in df.columns if c.startswith("gt_")]
if gt_cols:
    gt_filled = df[gt_cols].notna().any(axis=1).sum()
    gt_mints = df.loc[df[gt_cols].notna().any(axis=1), "MINT"].nunique()
    print(f"\n  GT detail: {gt_filled:,} rows with data across {gt_mints:,} unique mints")

# RC detailed
rc_cols = [c for c in df.columns if c.startswith("rc_")]
if rc_cols:
    rc_filled = df[rc_cols].notna().any(axis=1).sum()
    rc_mints = df.loc[df[rc_cols].notna().any(axis=1), "MINT"].nunique()
    print(f"  RC detail: {rc_filled:,} rows with data across {rc_mints:,} unique mints")

# GP detailed
gp_cols = [c for c in df.columns if c.startswith("gp_")]
if gp_cols:
    gp_filled = df[gp_cols].notna().any(axis=1).sum()
    gp_mints = df.loc[df[gp_cols].notna().any(axis=1), "MINT"].nunique()
    print(f"  GP detail: {gp_filled:,} rows with data across {gp_mints:,} unique mints")


# ═══════════════════════════════════════════════════════════════════
# PART 2: LABEL AUDIT — How are we defining "rug pull"?
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  PART 2: LABEL AUDIT — What makes a token a 'rug pull'?")
print("=" * 70)

# Check INACTIVITY_STATUS (the target used in train_model.py)
if "INACTIVITY_STATUS" in df.columns:
    print(f"\nINACTIVITY_STATUS distribution:")
    print(df["INACTIVITY_STATUS"].value_counts())
    inactive_pct = (df["INACTIVITY_STATUS"].str.upper() == "INACTIVE").mean() * 100
    print(f"  → Inactive (would be labeled 'rug'): {inactive_pct:.1f}%")

# Check RUG_LABEL from verified labels
if "RUG_LABEL" in df.columns:
    print(f"\nRUG_LABEL distribution (from verified_labels):")
    print(df["RUG_LABEL"].value_counts())

# Check signal columns
sig_cols = [c for c in df.columns if c.startswith("SIG_")]
if sig_cols:
    print(f"\n── Signal Columns (used to build labels) ──")
    for sc in sorted(sig_cols):
        if df[sc].dtype in [np.bool_, np.int64, np.float64]:
            pct = df[sc].mean() * 100
            print(f"  {sc:25s}: {pct:5.1f}% true")

# Analyze the actual label logic
if "RUG_SCORE" in df.columns:
    print(f"\nRUG_SCORE distribution:")
    print(df["RUG_SCORE"].describe())

# Cross-check: What does INACTIVITY_STATUS actually mean?
if "INACTIVITY_STATUS" in df.columns and "RUG_LABEL" in df.columns:
    print(f"\n── Cross-check: INACTIVITY_STATUS vs RUG_LABEL ──")
    ct = pd.crosstab(df["INACTIVITY_STATUS"], df["RUG_LABEL"])
    print(ct)

# Key question: are these REAL rugs or just dead projects?
print(f"\n── CRITICAL LABEL ANALYSIS ──")
if "INACTIVITY_STATUS" in df.columns:
    inactive = df[df["INACTIVITY_STATUS"].str.upper() == "INACTIVE"]
    active = df[df["INACTIVITY_STATUS"].str.upper() == "ACTIVE"]
    
    print(f"Inactive tokens: {len(inactive):,}")
    print(f"Active tokens:   {len(active):,}")
    
    # Check what % of "inactive" actually had liquidity drained
    if "SIG_DRAINED" in df.columns:
        drain_pct_inactive = inactive["SIG_DRAINED"].mean() * 100
        drain_pct_active = active["SIG_DRAINED"].mean() * 100
        print(f"\n  Liquidity DRAINED (>90% removed):")
        print(f"    Inactive: {drain_pct_inactive:.1f}%")
        print(f"    Active:   {drain_pct_active:.1f}%")
    
    if "LIFESPAN_H" in df.columns:
        print(f"\n  Lifespan (hours) — median:")
        print(f"    Inactive: {inactive['LIFESPAN_H'].median():.1f}h")
        print(f"    Active:   {active['LIFESPAN_H'].median():.1f}h")
    
    if "TOTAL_REMOVED_LIQUIDITY" in df.columns and "TOTAL_ADDED_LIQUIDITY" in df.columns:
        inactive_drain = (inactive["TOTAL_REMOVED_LIQUIDITY"] / 
                         (inactive["TOTAL_ADDED_LIQUIDITY"] + 1e-9)).median()
        active_drain = (active["TOTAL_REMOVED_LIQUIDITY"] / 
                       (active["TOTAL_ADDED_LIQUIDITY"] + 1e-9)).median()
        print(f"\n  Remove/Add liquidity ratio — median:")
        print(f"    Inactive: {inactive_drain:.2f}")
        print(f"    Active:   {active_drain:.2f}")


# ═══════════════════════════════════════════════════════════════════
# PART 3: LIVE-EQUIVALENT FEATURE SELECTION
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  PART 3: LIVE-EQUIVALENT FEATURE SELECTION")
print("=" * 70)

# These are features available BOTH in our training CSV AND via live APIs
LIVE_FEATURES = {
    # Helius DAS (available live + in training data)
    "TOKEN_DECIMALS": "helius",
    "TOKEN_SUPPLY": "helius",
    "MINT_AUTHORITY_ACTIVE": "helius",
    "FREEZE_AUTHORITY_ACTIVE": "helius",
    "IS_MUTABLE": "helius",
    "HAS_IMAGE": "helius",
    "HAS_JSON_URI": "helius",
    "HAS_METADATA": "helius",
    "IS_BURNT": "helius",
    "NUM_CREATORS": "helius",
    "CREATOR_VERIFIED": "helius",
    "TOKEN_PRICE_USD": "helius",
    # RugCheck (live API + in training data IF enriched)
    "rc_score": "rugcheck",
    "rc_score_norm": "rugcheck",
    "rc_risks_count": "rugcheck",
    "rc_top_risk_score": "rugcheck",
    "rc_total_market_liq": "rugcheck",
    "rc_total_lp_providers": "rugcheck",
    "rc_top_holders_pct": "rugcheck",
    "rc_creator_pct": "rugcheck",
    # GeckoTerminal (live API + in training data IF enriched)
    "gt_pool_count": "gecko",
    "gt_base_price_usd": "gecko",
    "gt_fdv_usd": "gecko",
    "gt_market_cap_usd": "gecko",
    "gt_reserve_usd": "gecko",
    "gt_vol_24h": "gecko",
    "gt_vol_6h": "gecko",
    "gt_vol_1h": "gecko",
    "gt_price_pct_5m": "gecko",
    "gt_price_pct_1h": "gecko",
    "gt_price_pct_24h": "gecko",
    "gt_txns_24h_buys": "gecko",
    "gt_txns_24h_sells": "gecko",
    # GoPlus (live API + in training data IF enriched)
    "gp_top3_holder_pct": "goplus",
    "gp_holder_count": "goplus",
    "gp_creator_pct": "goplus",
    "gp_total_tvl": "goplus",
    "gp_lp_count": "goplus",
    "gp_lp_holders_total": "goplus",
    "gp_lp_locked_count": "goplus",
    "gp_closable": "goplus",
    "gp_balance_mutable": "goplus",
    "gp_transfer_fee": "goplus",
    "gp_non_transferable": "goplus",
}

# NOT live: SolRPDS historical features (TOTAL_ADDED_LIQUIDITY, LIFESPAN_H, etc.)
# These summarize the ENTIRE history of a pool — not available for a new token

# Check which live features actually have data
print(f"\nLive-equivalent features spec: {len(LIVE_FEATURES)}")
available = {}
for feat, src in LIVE_FEATURES.items():
    if feat in df.columns:
        non_null = df[feat].notna().sum()
        pct = 100 * non_null / len(df)
        if pct > 0.1:  # at least 0.1% filled
            available[feat] = (src, pct)

print(f"Available with data (>0.1%): {len(available)}")
print()
for feat, (src, pct) in sorted(available.items(), key=lambda x: -x[1][1]):
    marker = "✅" if pct > 5 else "⚠️"
    print(f"  {marker} {feat:30s} ({src:10s}): {pct:5.1f}%")

# Features usable for training (>5% fill)
trainable = [f for f, (s, p) in available.items() if p > 5]
print(f"\nTrainable features (>5% fill): {len(trainable)}")


# ═══════════════════════════════════════════════════════════════════
# PART 4: TRAIN SAMPLE MODEL
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  PART 4: TRAIN SAMPLE MODEL (live-equivalent features only)")
print("=" * 70)

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, average_precision_score, accuracy_score, f1_score,
    precision_score, recall_score, matthews_corrcoef, classification_report,
    confusion_matrix
)

try:
    from xgboost import XGBClassifier
except ImportError:
    print("[ERROR] pip install xgboost")
    exit(1)

# Build target: Use a STRICTER definition than just INACTIVITY_STATUS
# Combine signals for a more reliable label:
#   RUG = (drained OR (short_life AND inactive))
#   LEGIT = active AND NOT drained
print("\n── Building reliable labels ──")

df["_inactive"] = df["INACTIVITY_STATUS"].str.upper() == "INACTIVE"
df["_drained"] = df.get("SIG_DRAINED", pd.Series(False, index=df.index)).astype(bool)
df["_short"] = df.get("SIG_SHORT_LIFE", pd.Series(False, index=df.index)).astype(bool)
df["_few_txn"] = df.get("SIG_FEW_TXN", pd.Series(False, index=df.index)).astype(bool)
df["_no_price"] = df.get("SIG_NO_PRICE", pd.Series(False, index=df.index)).astype(bool)

# Strict label: at least 2 rug signals
df["_rug_signals"] = (df["_drained"].astype(int) + df["_short"].astype(int) + 
                       df["_few_txn"].astype(int) + df["_no_price"].astype(int))

# VERIFIED_RUG/LIKELY_RUG: use directly from RUG_LABEL if available
if "RUG_LABEL" in df.columns:
    df["_is_verified_rug"] = df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
    df["_is_legit"] = df["RUG_LABEL"].isin(["LIKELY_LEGIT"])
else:
    df["_is_verified_rug"] = df["_rug_signals"] >= 3
    df["_is_legit"] = (~df["_inactive"]) & (~df["_drained"]) & (df["_rug_signals"] == 0)

# Create binary target: 1=rug, 0=legit, NaN=uncertain (drop)
df["TARGET"] = np.nan
df.loc[df["_is_verified_rug"], "TARGET"] = 1
df.loc[df["_is_legit"], "TARGET"] = 0

labeled = df[df["TARGET"].notna()].copy()
print(f"Labeled rows: {len(labeled):,} ({100*len(labeled)/len(df):.1f}% of total)")
print(f"  Rugs:  {(labeled['TARGET']==1).sum():,}")
print(f"  Legit: {(labeled['TARGET']==0).sum():,}")
print(f"  Dropped (uncertain): {len(df) - len(labeled):,}")

# Select trainable numeric features
feature_cols = []
for f in trainable:
    if f in labeled.columns:
        if labeled[f].dtype in [np.float64, np.float32, np.int64, np.int32, np.bool_]:
            feature_cols.append(f)
        else:
            # Try to coerce
            labeled[f] = pd.to_numeric(labeled[f], errors="coerce")
            if labeled[f].notna().mean() > 0.05:
                feature_cols.append(f)

print(f"\nUsing {len(feature_cols)} numeric live-equivalent features:")
for f in feature_cols:
    src = LIVE_FEATURES.get(f, "?")
    fill = labeled[f].notna().mean() * 100
    print(f"  {f:30s} ({src:10s}) {fill:5.1f}% filled")

# Prepare X, y
X = labeled[feature_cols].fillna(0).values
y = labeled["TARGET"].values.astype(int)

# Temporal split if possible
if "FIRST_POOL_ACTIVITY_TIMESTAMP" in labeled.columns:
    labeled["_ts"] = pd.to_datetime(labeled["FIRST_POOL_ACTIVITY_TIMESTAMP"], errors="coerce")
    labeled["_year"] = labeled["_ts"].dt.year
    
    train_mask = labeled["_year"] < 2024
    test_mask = labeled["_year"] == 2024
    
    if train_mask.sum() > 100 and test_mask.sum() > 100:
        X_train = labeled.loc[train_mask, feature_cols].fillna(0).values
        y_train = labeled.loc[train_mask, "TARGET"].values.astype(int)
        X_test = labeled.loc[test_mask, feature_cols].fillna(0).values
        y_test = labeled.loc[test_mask, "TARGET"].values.astype(int)
        split_type = "temporal (train<2024, test=2024)"
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
        split_type = "stratified 80/20"
else:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    split_type = "stratified 80/20"

n_pos_train = (y_train == 1).sum()
n_neg_train = (y_train == 0).sum()
print(f"\nSplit: {split_type}")
print(f"  Train: {len(y_train):,} (rug={n_pos_train:,}, legit={n_neg_train:,})")
print(f"  Test:  {len(y_test):,} (rug={(y_test==1).sum():,}, legit={(y_test==0).sum():,})")

# Train XGBoost
scale = n_neg_train / max(n_pos_train, 1)
model = XGBClassifier(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=scale,
    eval_metric="aucpr",
    random_state=42,
    n_jobs=-1,
    tree_method="hist",
    verbosity=0,
)

print(f"\nTraining XGBoost (300 trees, depth=6, scale_pos_weight={scale:.2f})...")
model.fit(X_train, y_train)

# Evaluate
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

print("\n" + "=" * 60)
print("  MODEL RESULTS (live-equivalent features only)")
print("=" * 60)

metrics = {
    "AUC-ROC": roc_auc_score(y_test, y_prob),
    "AUC-PR": average_precision_score(y_test, y_prob),
    "Accuracy": accuracy_score(y_test, y_pred),
    "F1 (weighted)": f1_score(y_test, y_pred, average="weighted"),
    "Precision (rug)": precision_score(y_test, y_pred, pos_label=1, zero_division=0),
    "Recall (rug)": recall_score(y_test, y_pred, pos_label=1, zero_division=0),
    "MCC": matthews_corrcoef(y_test, y_pred),
}

for name, val in metrics.items():
    print(f"  {name:25s} {val:.4f}")

print(f"\n  Classification Report:")
print(classification_report(y_test, y_pred, target_names=["Legit", "Rug Pull"]))

cm = confusion_matrix(y_test, y_pred)
print(f"  Confusion Matrix:")
print(f"                Predicted")
print(f"              Legit   Rug")
print(f"  Actual Legit  {cm[0][0]:>5}  {cm[0][1]:>5}")
print(f"  Actual Rug    {cm[1][0]:>5}  {cm[1][1]:>5}")

# Feature importance
importances = model.feature_importances_
imp_df = pd.DataFrame({"feature": feature_cols, "importance": importances})
imp_df["source"] = imp_df["feature"].map(LIVE_FEATURES)
imp_df = imp_df.sort_values("importance", ascending=False)

print(f"\n  Top 15 Features:")
for _, row in imp_df.head(15).iterrows():
    print(f"    {row['feature']:30s} ({row['source']:10s}) {row['importance']:.4f}")

# Source contribution
print(f"\n  Importance by Source:")
src_imp = imp_df.groupby("source")["importance"].sum().sort_values(ascending=False)
total_imp = src_imp.sum()
for src, imp in src_imp.items():
    print(f"    {src:15s}: {imp/total_imp*100:5.1f}%")

print("\n" + "=" * 60)
print("  VERDICT")
print("=" * 60)
auc = metrics["AUC-ROC"]
if auc > 0.95:
    print("  🟢 EXCELLENT — model strongly separates rugs from legit")
elif auc > 0.85:
    print("  🟡 GOOD — model works but could improve with more features")
elif auc > 0.70:
    print("  🟠 MODERATE — needs more enrichment data to be production-ready")
else:
    print("  🔴 WEAK — live features alone are not enough, need enrichment")

print(f"\n  Key insight: This model uses ONLY features available via live APIs.")
print(f"  No SolRPDS historical data (liquidity totals, lifespan, swap counts).")
print(f"  This is what the production model will actually look like.")
print("=" * 60)
