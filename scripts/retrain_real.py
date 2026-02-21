"""
DeFi Sentinel — REAL Honest Model (no temporal leakage)

Key insight: The dataset captures token state AFTER the rug pull happened.
Features like TOKEN_PRICE_USD, derived_has_price, REMOVED_RATIO etc.
reflect the OUTCOME (post-drain), not the pre-drain state.

For live inference, we see the token AT CREATION — all tokens have
a price, metadata, and liquidity at that point.

This model ONLY uses features available at token creation time:
  - Helius metadata (name, symbol, decimals, supply, authorities, etc.)
  - Token standard, URI domain, creator info
  - Derived risk scores (domain risk, standard risk)

It explicitly DROPS post-outcome features.
"""
import pandas as pd
import numpy as np
from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                             f1_score, matthews_corrcoef, classification_report)
from xgboost import XGBClassifier
import warnings
warnings.filterwarnings("ignore")

CLEAN = "data/enriched/enriched_clean.csv"
LABELS = "data/enriched/verified_labels.csv"

print("=" * 70)
print("  DeFi Sentinel — REAL Model (creation-time features only)")
print("=" * 70)

df = pd.read_csv(CLEAN, low_memory=False)
labels = pd.read_csv(LABELS)
df = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
              on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vl"))

rug_mask = df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit_mask = df["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = df[rug_mask | legit_mask].copy()
labeled["IS_RUG"] = rug_mask[labeled.index].astype(int)
print(f"Labeled: {len(labeled):,} rows ({labeled['IS_RUG'].sum():,} rug, {(~labeled['IS_RUG'].astype(bool)).sum():,} legit)")

# ── POST-OUTCOME features to EXCLUDE ──
# These reflect what happened AFTER the rug, not before
post_outcome = {
    # Price/liquidity state AFTER drain
    "TOKEN_PRICE_USD",          # 0 after rug, >0 before
    "derived_has_price",        # same thing binary
    # Drain metrics — these ARE the rug happening
    "TOTAL_REMOVED_LIQUIDITY",  # how much was removed
    "REMOVED_RATIO",            # % removed
    "ADD_TO_REMOVE_RATIO",      # ratio = rug signature
    "derived_liquidity_depth_ratio",    # same
    "derived_avg_remove_size",          # same
    "derived_remove_add_size_ratio",    # same
    "derived_drain_speed_pct_per_hour", # same
    "derived_single_drain_flag",        # same — "did they drain in 1 tx?"
    # Activity metrics that reflect post-drain state
    "LIFESPAN_H",               # short lifespan = already dead = outcome
    "derived_pool_active_hours",# same
    "derived_events_per_hour",  # same
    "NUM_LIQUIDITY_REMOVES",    # how many times removed = outcome
}

# ── CREATION-TIME features (available when token launches) ──
exclude_ids = {"LIQUIDITY_POOL_ADDRESS", "MINT", "OWNER", "IS_RUG",
               "TOKEN_NAME", "TOKEN_SYMBOL", "MINT_AUTHORITY", "FREEZE_AUTHORITY",
               "JSON_URI_DOMAIN", "TOKEN_STANDARD", "TOKEN_PROGRAM", "TOKEN_PRICE_CURRENCY",
               "FIRST_POOL_ACTIVITY_TIMESTAMP", "LAST_POOL_ACTIVITY_TIMESTAMP",
               "LAST_SWAP_TIMESTAMP", "FIRST", "LAST",
               "gt_pool_name", "gt_pool_dex", "gt_pool_created",
               "RC_RISK_NAMES", "RC_TOKEN_TYPE", "RUG_LABEL", "RUG_LABEL_vl",
               "rc_top_risk", "rc_top_risk_level", "rc_detected_at"}

all_exclude = post_outcome | exclude_ids

features = [c for c in labeled.columns
            if c not in all_exclude
            and labeled[c].dtype in ["float64", "int64", "float32", "int32"]
            and not c.startswith("SIG_")
            and c not in ["RUG_SIGNALS", "RUG_SCORE"]]

print(f"\nCreation-time features: {len(features)}")
for f in sorted(features):
    fill = labeled[f].notna().sum()
    pct = 100 * fill / len(labeled)
    print(f"  {'✓' if pct > 50 else '○'} {f:45s} fill={fill:,} ({pct:.0f}%)")

# ── Temporal split ──
labeled["_year"] = pd.to_datetime(labeled["FIRST"], errors="coerce").dt.year
train = labeled[labeled["_year"] < 2024].copy()
test = labeled[labeled["_year"] >= 2024].copy()
print(f"\nTemporal split: train={len(train):,} (<2024), test={len(test):,} (2024+)")
print(f"  Train: {train['IS_RUG'].sum():,} rug / {(~train['IS_RUG'].astype(bool)).sum():,} legit")
print(f"  Test:  {test['IS_RUG'].sum():,} rug / {(~test['IS_RUG'].astype(bool)).sum():,} legit")

X_train = train[features].copy()
y_train = train["IS_RUG"]
X_test = test[features].copy()
y_test = test["IS_RUG"]

# ── Train ──
print("\nTraining XGBoost (creation-time features only)...")
model = XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=len(y_train[y_train==0]) / max(len(y_train[y_train==1]), 1),
    eval_metric="auc", random_state=42, verbosity=0,
    tree_method="hist",
)
model.fit(X_train, y_train)

# ── Evaluate ──
y_prob = model.predict_proba(X_test)[:, 1]
y_pred = (y_prob >= 0.5).astype(int)

auc = roc_auc_score(y_test, y_prob)
prec = precision_score(y_test, y_pred, zero_division=0)
rec = recall_score(y_test, y_pred, zero_division=0)
f1 = f1_score(y_test, y_pred, zero_division=0)
mcc = matthews_corrcoef(y_test, y_pred)

print(f"\n{'=' * 70}")
print(f"  REAL MODEL RESULTS (creation-time features only)")
print(f"{'=' * 70}")
print(f"  AUC-ROC:   {auc:.4f}")
print(f"  Precision: {prec:.4f}  ({prec*100:.1f}%)")
print(f"  Recall:    {rec:.4f}  ({rec*100:.1f}%)")
print(f"  F1:        {f1:.4f}")
print(f"  MCC:       {mcc:.4f}")
print(f"\n{classification_report(y_test, y_pred, target_names=['Legit','Rug'])}")

# ── Feature importance ──
imp = dict(zip(features, model.feature_importances_))
imp_sorted = sorted(imp.items(), key=lambda x: -x[1])

print(f"\n  Top 20 feature importances (creation-time only):")
for i, (feat, val) in enumerate(imp_sorted[:20]):
    bar = "█" * int(val * 200)
    print(f"    {i+1:2d}. {feat:40s} {val:.4f}  {bar}")

# Source breakdown
src_imp = {}
for feat, val in imp.items():
    if feat.startswith("gp_"):       src = "GoPlus"
    elif feat.startswith(("RC_","rc_")): src = "RugCheck"
    elif feat.startswith("gt_"):     src = "GeckoTerminal"
    elif feat.startswith("derived_"):src = "Derived"
    else:                            src = "Helius/SolRPDS"
    src_imp[src] = src_imp.get(src, 0) + val

total = sum(src_imp.values()) or 1
print(f"\n  Importance by source:")
for src, val in sorted(src_imp.items(), key=lambda x: -x[1]):
    print(f"    {src:18s}: {val/total*100:5.1f}%")

print(f"\n{'=' * 70}")
print(f"  This is the REAL baseline. The enrichment scripts will add:")
print(f"    - Creator wallet features (6): wallet age, balance, prev rugs...")
print(f"    - Batch GoPlus/RugCheck (thousands more tokens)")
print(f"    - Jupiter pricing data (listed status, confidence)")
print(f"  These should significantly improve this honest baseline.")
print(f"{'=' * 70}")
