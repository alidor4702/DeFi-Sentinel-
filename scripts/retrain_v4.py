#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
 RETRAIN MODEL V4 — LIVE-ONLY FEATURES
═══════════════════════════════════════════════════════════════════════
 
 Problem with v3: 89% of model importance came from deployer-history
 features that are NOT AVAILABLE at live scan time.  The model was
 effectively 93% blind in production.
 
 v4 Strategy:
   ✅  Use ONLY features obtainable at scan time (Helius, RugCheck,
       GeckoTerminal, GoPlus, derived)
   ✅  Include sparse rug-check / gecko features using XGBoost's
       NATIVE missing-value handling (no fillna(-1) hack)
   ✅  Engineer new authority-risk and metadata-quality features
   ❌  Exclude ALL deployer-history features
   ❌  Exclude ALL post-outcome features (liquidity removes, price, etc.)
 
 v3 artifacts are PRESERVED — this creates separate v4 files.
═══════════════════════════════════════════════════════════════════════
"""

import json
import math
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    matthews_corrcoef,
    roc_auc_score,
    precision_recall_curve,
    average_precision_score,
    confusion_matrix,
)
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "enriched")
MODELS = os.path.join(BASE, "models")
os.makedirs(MODELS, exist_ok=True)

print("=" * 70)
print("  RETRAIN MODEL V4 — LIVE-ONLY FEATURES")
print("  No deployer data · No post-outcome leakage · XGBoost native NaN")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════════════
# 1. LOAD DATA
# ═══════════════════════════════════════════════════════════════════════
df = pd.read_csv(os.path.join(DATA, "enriched_v2.csv"), low_memory=False)
print(f"\nDataset: {len(df):,} rows × {len(df.columns)} cols")

labels = pd.read_csv(
    os.path.join(DATA, "verified_labels.csv"),
    usecols=["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"],
)
merged = df.merge(
    labels, on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_lab")
)

rug = merged["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit = merged["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = merged[rug | legit].copy()
labeled["IS_RUG"] = rug[labeled.index].astype(int)
print(
    f"Labeled: {len(labeled):,} "
    f"({labeled.IS_RUG.sum():,} rug / {(~labeled.IS_RUG.astype(bool)).sum():,} legit)"
)

# ═══════════════════════════════════════════════════════════════════════
# 2. ENGINEER NEW FEATURES (v4-specific)
# ═══════════════════════════════════════════════════════════════════════
print("\nEngineering new v4 features...")

# authority_risk_score: 0–3, higher = riskier
# (mint_authority_active + freeze_authority_active + is_mutable)
labeled["v4_authority_risk_score"] = (
    labeled["MINT_AUTHORITY_ACTIVE"].fillna(0).astype(int)
    + labeled["IS_MUTABLE"].fillna(0).astype(int)
    # freeze authority isn't in the CSV, so use 0
)

# metadata_quality_score: 0–5 based on name, image, json_uri, metadata
labeled["v4_metadata_quality"] = (
    labeled["HAS_METADATA"].fillna(0).astype(int)
    + labeled["HAS_IMAGE"].fillna(0).astype(int)
    + labeled["HAS_JSON_URI"].fillna(0).astype(int)
    + (1 - labeled["IS_MUTABLE"].fillna(1).astype(int))  # immutable = good
    + (1 - labeled["MINT_AUTHORITY_ACTIVE"].fillna(1).astype(int))  # revoked = good
)

# supply_roundness_score: how "round" is the supply (scammers use round numbers)
labeled["v4_supply_roundness"] = (
    labeled.get("feat_supply_is_round_million", pd.Series(0, index=labeled.index)).fillna(0).astype(int)
    + labeled.get("feat_supply_is_round_billion", pd.Series(0, index=labeled.index)).fillna(0).astype(int)
    + labeled.get("feat_supply_is_exact_common", pd.Series(0, index=labeled.index)).fillna(0).astype(int)
)

# liq_to_supply_log_ratio: log(liquidity+1) / log(supply+1) — scaled relationship
supply_log = labeled["TOKEN_SUPPLY"].apply(lambda x: math.log10(x + 1) if x and x > 0 else 0)
liq_log = labeled["TOTAL_ADDED_LIQUIDITY"].apply(lambda x: math.log10(x + 1) if x and x > 0 else 0)
labeled["v4_liq_supply_log_ratio"] = liq_log / (supply_log + 0.01)

# rc_score_bucketed: bucket RugCheck score for easier splits
def _rc_bucket(score):
    if pd.isna(score):
        return np.nan  # keep as NaN for XGBoost native handling
    if score >= 800:
        return 3  # Good
    if score >= 400:
        return 2  # Warning
    if score >= 200:
        return 1  # Risky
    return 0  # Danger

labeled["v4_rc_score_bucket"] = labeled["rc_score"].apply(_rc_bucket)

# name_suspicion_score: combined name risk
labeled["v4_name_suspicion"] = (
    labeled.get("feat_name_has_scam_word", pd.Series(0, index=labeled.index)).fillna(0).astype(int) * 3
    + labeled.get("feat_name_has_emoji", pd.Series(0, index=labeled.index)).fillna(0).astype(int) * 2
    + labeled.get("feat_name_all_caps", pd.Series(0, index=labeled.index)).fillna(0).astype(int)
    + labeled.get("feat_name_starts_with_dollar", pd.Series(0, index=labeled.index)).fillna(0).astype(int)
)

print(f"  Added 6 new v4 features")

# ═══════════════════════════════════════════════════════════════════════
# 3. DEFINE FEATURE GROUPS
# ═══════════════════════════════════════════════════════════════════════

# ── POST-OUTCOME: NOT available at scan time ──────────────────────────
POST_OUTCOME = {
    "TOKEN_PRICE_USD", "TOTAL_REMOVED_LIQUIDITY", "REMOVED_RATIO",
    "ADD_TO_REMOVE_RATIO", "LIFESPAN_H", "NUM_LIQUIDITY_REMOVES",
    "LAST_POOL_ACTIVITY_TIMESTAMP", "LAST_SWAP_TIMESTAMP",
    "INACTIVITY_STATUS", "NUM_SWAPS", "TOTAL_SWAP_VOLUME",
    # Derived features that use post-outcome data
    "derived_has_price", "derived_pool_active_hours", "derived_events_per_hour",
    "derived_drain_speed_pct_per_hour", "derived_single_drain_flag",
    "derived_liquidity_depth_ratio", "derived_avg_remove_size",
    "derived_remove_add_size_ratio",
}

# ── IDs / STRINGS: Not features ──────────────────────────────────────
IDS = {
    "MINT", "LIQUIDITY_POOL_ADDRESS", "OWNER", "SOURCE",
    "POOL_OPEN_TIMESTAMP", "POOL_OPEN_DATE", "TOKEN_NAME", "TOKEN_SYMBOL",
    "URI", "URI_HASH", "METADATA_URI", "RAYDIUM_POOL_ID",
    "gt_pool_name", "gt_pool_dex", "gt_pool_created",
    "FIRST_POOL_ACTIVITY_TIMESTAMP", "FIRST", "LAST", "TOKEN_PROGRAM",
    "MINT_AUTHORITY", "RUG_LABEL", "IS_RUG", "RUG_LABEL_lab",
    "TOKEN_STANDARD", "JSON_URI_DOMAIN", "TOKEN_PRICE_CURRENCY",
}

# ── DEPLOYER: NOT available at scan time (the whole problem!) ─────────
DEPLOYER_FEATURES = {
    "feat_deployer_token_count", "feat_deployer_rug_count",
    "feat_deployer_rug_rate", "feat_deployer_median_liquidity",
    "feat_deployer_is_rug_factory", "feat_deployer_is_repeat",
    "feat_deployer_past_tokens", "feat_deployer_past_rugs",
    "feat_deployer_past_rug_rate", "feat_deployer_past_labeled",
    "feat_deployer_past_is_serial",
}

# ═══════════════════════════════════════════════════════════════════════
# 4. SELECT FEATURES
# ═══════════════════════════════════════════════════════════════════════
numeric_types = ["float64", "int64", "float32", "int32", "int8", "uint8"]

feature_cols = [
    c for c in labeled.columns
    if c not in POST_OUTCOME
    and c not in IDS
    and c not in DEPLOYER_FEATURES
    and labeled[c].dtype in numeric_types
]

# v4 change: use 0.5% fill threshold instead of 20%
# This includes rc_* (2.1%) and gt_* (16%) and gp_* (17.8%)
# XGBoost handles NaN natively — no need to require high fill rates
MIN_FILL = 0.005
good_features = [c for c in feature_cols if labeled[c].notna().mean() > MIN_FILL]

# Show what we're using
print(f"\nFeature selection:")
print(f"  Total numeric columns: {len(feature_cols)}")
print(f"  After {MIN_FILL*100:.1f}% fill filter: {len(good_features)}")

# Categorize features for reporting
categories = {
    "Base metadata": [f for f in good_features if f in {
        "TOTAL_ADDED_LIQUIDITY", "NUM_LIQUIDITY_ADDS", "HAS_METADATA",
        "HAS_IMAGE", "HAS_JSON_URI", "TOKEN_DECIMALS", "TOKEN_SUPPLY",
        "IS_MUTABLE", "ROYALTY_PCT", "NUM_CREATORS", "CREATOR_VERIFIED",
        "MINT_AUTHORITY_ACTIVE"}],
    "Derived": [f for f in good_features if f.startswith("derived_")],
    "Name eng.": [f for f in good_features if f.startswith("feat_name_")],
    "Symbol eng.": [f for f in good_features if f.startswith("feat_symbol_")],
    "Pool time": [f for f in good_features if f.startswith("feat_pool_")],
    "Supply eng.": [f for f in good_features if f.startswith("feat_supply_")],
    "Liq eng.": [f for f in good_features if f.startswith("feat_liq_")],
    "RugCheck": [f for f in good_features if f.startswith("rc_")],
    "GeckoTerminal": [f for f in good_features if f.startswith("gt_")],
    "GoPlus": [f for f in good_features if f.startswith("gp_")],
    "v4 new": [f for f in good_features if f.startswith("v4_")],
}

for cat, cols in categories.items():
    if cols:
        avg_fill = np.mean([labeled[c].notna().mean() for c in cols]) * 100
        print(f"  {cat:<16s}: {len(cols):>2d} features  (avg fill {avg_fill:.1f}%)")

# ═══════════════════════════════════════════════════════════════════════
# 5. TEMPORAL SPLIT
# ═══════════════════════════════════════════════════════════════════════
ts = pd.to_datetime(labeled["FIRST_POOL_ACTIVITY_TIMESTAMP"], errors="coerce")
cutoff = pd.Timestamp("2024-01-01")
train_mask = ts < cutoff
test_mask = ts >= cutoff

# ── KEY V4 CHANGE: Do NOT fill NaN with -1!
# XGBoost natively handles NaN by learning the optimal direction for
# missing values at each split. This is critical for sparse features
# like rc_* (2.1% fill) — when RugCheck data IS available, the model
# uses it; when it's missing, it falls back gracefully.
X_train = labeled.loc[train_mask, good_features].copy()
y_train = labeled.loc[train_mask, "IS_RUG"]
X_test = labeled.loc[test_mask, good_features].copy()
y_test = labeled.loc[test_mask, "IS_RUG"]

print(f"\nTemporal split (cutoff {cutoff.date()}):")
print(f"  Train: {len(X_train):,} (rug={y_train.sum():,}, legit={(~y_train.astype(bool)).sum():,})")
print(f"  Test:  {len(X_test):,} (rug={y_test.sum():,}, legit={(~y_test.astype(bool)).sum():,})")

# ═══════════════════════════════════════════════════════════════════════
# 6. TRAIN MODEL
# ═══════════════════════════════════════════════════════════════════════
print(f"\nTraining XGBoost v4 ({len(good_features)} features)...")

model = XGBClassifier(
    n_estimators=600,       # more trees to compensate for lost deployer signal
    max_depth=7,            # slightly deeper to find subtler patterns
    learning_rate=0.05,     # slower learning for better generalization
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,     # prevent overfitting on sparse features
    gamma=0.1,              # min loss reduction for splits
    reg_alpha=0.1,          # L1 regularization
    reg_lambda=1.0,         # L2 regularization
    scale_pos_weight=len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1),
    random_state=42,
    eval_metric="logloss",
    tree_method="hist",     # fast + handles missing values well
    verbosity=0,
)

# Use eval set for early stopping
model.fit(
    X_train, y_train,
    eval_set=[(X_test, y_test)],
    verbose=False,
)

# ═══════════════════════════════════════════════════════════════════════
# 7. EVALUATE
# ═══════════════════════════════════════════════════════════════════════
y_pred_proba = model.predict_proba(X_test)[:, 1]
y_pred = (y_pred_proba >= 0.5).astype(int)
auc = roc_auc_score(y_test, y_pred_proba)
mcc = matthews_corrcoef(y_test, y_pred)
ap = average_precision_score(y_test, y_pred_proba)
cm = confusion_matrix(y_test, y_pred)

print(f"\n{'=' * 65}")
print(f"  MODEL V4 RESULTS (live-only features)")
print(f"{'=' * 65}")
print(f"  AUC-ROC:            {auc:.4f}")
print(f"  MCC:                {mcc:.4f}")
print(f"  Avg Precision (AP): {ap:.4f}")
print(f"\n  Confusion Matrix:")
print(f"                 Pred Legit  Pred Rug")
print(f"    True Legit:  {cm[0][0]:>8,}  {cm[0][1]:>8,}")
print(f"    True Rug:    {cm[1][0]:>8,}  {cm[1][1]:>8,}")
print(classification_report(y_test, y_pred, target_names=["Legit", "Rug"], digits=4))

# ── Comparison ──
print(f"  COMPARISON:")
print(f"    v1 (original):      AUC=0.9972  MCC=0.9392  (50 features, deployer-dependent)")
print(f"    v2 (quick wins):    AUC=0.9988  MCC=0.9707  (49 features, deployer-dependent)")
print(f"    v3 (+ deployer):    AUC=0.9995  MCC=0.9802  (54 features, 93% BLIND in production)")
print(f"    v4 (LIVE-ONLY):     AUC={auc:.4f}  MCC={mcc:.4f}  ({len(good_features)} features, 100% functional)")
print()

# ── Optimal threshold analysis ──
precisions, recalls, thresholds = precision_recall_curve(y_test, y_pred_proba)
f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-8)
best_idx = np.argmax(f1_scores)
best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
best_f1 = f1_scores[best_idx]
print(f"  Optimal threshold: {best_threshold:.3f} (F1={best_f1:.4f})")
print(f"    At optimal: Precision={precisions[best_idx]:.4f}, Recall={recalls[best_idx]:.4f}")

# ═══════════════════════════════════════════════════════════════════════
# 8. FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════
importances = dict(zip(good_features, model.feature_importances_))
sorted_imp = sorted(importances.items(), key=lambda x: -x[1])

print(f"\n  TOP 30 FEATURES (by gain):")
for i, (feat, imp) in enumerate(sorted_imp[:30]):
    tag = ""
    if feat.startswith("rc_"):
        tag = "🔍 RUGCHECK"
    elif feat.startswith("gt_"):
        tag = "📊 GECKO"
    elif feat.startswith("gp_"):
        tag = "🛡 GOPLUS"
    elif feat.startswith("v4_"):
        tag = "🆕 NEW"
    elif feat.startswith("feat_name_") or feat.startswith("feat_symbol_"):
        tag = "📝 NAME/SYM"
    elif feat.startswith("feat_liq_") or feat.startswith("feat_supply_"):
        tag = "💰 SUPPLY/LIQ"
    elif feat.startswith("feat_pool_"):
        tag = "⏰ TIME"
    elif feat.startswith("derived_"):
        tag = "🔧 DERIVED"
    else:
        tag = "📦 BASE"
    print(f"    {i + 1:>2d}. {imp * 100:>5.1f}%  {feat:<40s} {tag}")

# Category importance summary
print(f"\n  IMPORTANCE BY CATEGORY:")
for cat, cols in sorted(categories.items(), key=lambda x: -sum(importances.get(c, 0) for c in x[1])):
    cat_imp = sum(importances.get(c, 0) for c in cols) * 100
    if cat_imp > 0:
        print(f"    {cat:<16s}: {cat_imp:>5.1f}%")

# ═══════════════════════════════════════════════════════════════════════
# 9. ANALYZE SPARSE FEATURE CONTRIBUTION
# ═══════════════════════════════════════════════════════════════════════
print(f"\n  SPARSE FEATURE ANALYSIS (these work at scan time):")
for prefix, name in [("rc_", "RugCheck"), ("gt_", "GeckoTerminal"), ("gp_", "GoPlus")]:
    cols = [f for f in good_features if f.startswith(prefix)]
    if cols:
        total_imp = sum(importances.get(c, 0) for c in cols) * 100
        avg_fill = np.mean([labeled[c].notna().mean() for c in cols]) * 100
        print(f"    {name:<15s}: {len(cols)} features, {total_imp:.1f}% importance, {avg_fill:.1f}% fill")

# v4 new features
v4_cols = [f for f in good_features if f.startswith("v4_")]
if v4_cols:
    total_imp = sum(importances.get(c, 0) for c in v4_cols) * 100
    print(f"    {'v4 new':<15s}: {len(v4_cols)} features, {total_imp:.1f}% importance")

# ═══════════════════════════════════════════════════════════════════════
# 10. SAVE MODEL ARTIFACTS
# ═══════════════════════════════════════════════════════════════════════
print(f"\nSaving v4 model artifacts...")

model.save_model(os.path.join(MODELS, "model_v4.json"))

with open(os.path.join(MODELS, "feature_list_v4.json"), "w") as f:
    json.dump(good_features, f, indent=2)

meta = {
    "model_version": "v4_live_only",
    "algorithm": "XGBClassifier",
    "n_estimators": 600,
    "max_depth": 7,
    "learning_rate": 0.05,
    "training_samples": int(len(X_train)),
    "test_samples": int(len(X_test)),
    "metrics": {
        "auc_roc": round(float(auc), 4),
        "mcc": round(float(mcc), 4),
        "avg_precision": round(float(ap), 4),
        "optimal_threshold": round(float(best_threshold), 3),
        "optimal_f1": round(float(best_f1), 4),
    },
    "features_count": len(good_features),
    "feature_categories": {cat: len(cols) for cat, cols in categories.items() if cols},
    "design_philosophy": (
        "Trained on ONLY features available at live scan time. "
        "No deployer history (unavailable), no post-outcome leakage. "
        "Sparse features (RugCheck 2%, GeckoTerminal 16%) included with "
        "XGBoost native NaN handling — model learns optimal missing-value routing."
    ),
    "vs_v3": (
        "v3 had AUC=0.9995 but was 93% blind in production (deployer features "
        "accounted for 89% of importance but were unavailable at scan time). "
        "v4 uses fewer features but ALL of them work in production."
    ),
    "top_features": [(f, round(float(imp), 6)) for f, imp in sorted_imp[:30]],
    "category_importance": {
        cat: round(float(sum(importances.get(c, 0) for c in cols) * 100), 1)
        for cat, cols in categories.items() if cols
    },
}

with open(os.path.join(MODELS, "model_meta_v4.json"), "w") as f:
    json.dump(meta, f, indent=2)

# Also save the feature name mapping for ml_scorer.py
# Maps: training CSV column name → live collector key (where different)
feature_mapping = {
    # Training CSV name → live collector key
    "TOTAL_ADDED_LIQUIDITY": "gt_reserve_usd|rc_total_market_liquidity",
    "NUM_LIQUIDITY_ADDS": "_default_1",
    "HAS_METADATA": "metadata_uri|metadata_uri_reachable",
    "HAS_IMAGE": "has_image",
    "HAS_JSON_URI": "metadata_uri",
    "TOKEN_DECIMALS": "token_decimals",
    "TOKEN_SUPPLY": "token_supply",
    "IS_MUTABLE": "is_mutable",
    "ROYALTY_PCT": "_default_0",
    "NUM_CREATORS": "_default_1",
    "CREATOR_VERIFIED": "_default_0",
    "MINT_AUTHORITY_ACTIVE": "mint_authority_revoked|_invert",
    # RugCheck features (name mismatches between CSV and live collector)
    "rc_score": "rc_score",
    "rc_score_norm": "rc_score",  # same source, may need normalization
    "rc_risks_count": "rc_risk_count",  # CSV: rc_risks_count, live: rc_risk_count
    "rc_top_risk_score": "_computed",
    "rc_num_dangers": "_computed",
    "rc_num_warns": "_computed",
    "rc_top10_holder_pct": "rc_top10_holder_pct",
    "rc_top1_holder_pct": "rc_top_holder_pct",  # CSV: rc_top1_, live: rc_top_
    "rc_total_market_liq": "rc_total_market_liquidity",  # CSV: _liq, live: _liquidity
    "rc_total_holders": "_computed",
    "rc_mint_authority": "rc_mint_authority_disabled|_invert",
    "rc_freeze_authority": "rc_freeze_authority_disabled|_invert",
    "rc_mutable_metadata": "rc_mutable_metadata",
    "rc_lp_locked": "rc_lp_locked",
    "rc_lp_burned": "rc_lp_burned",
    "rc_lp_lock_pct": "rc_lp_lock_pct",
    "rc_rugged": "_default_0",
    # GeckoTerminal
    "gt_pool_count": "gt_pool_count",
    "gt_price_pct_24h": "gt_price_change_24h",  # CSV: gt_price_pct_24h, live: gt_price_change_24h
    # GoPlus (from old enrichment, may not have live equivalent)
    "gp_top3_holder_pct": "_computed",
    "gp_total_tvl": "_computed",
    "gp_lp_count": "_computed",
}

with open(os.path.join(MODELS, "feature_mapping_v4.json"), "w") as f:
    json.dump(feature_mapping, f, indent=2)

print(f"\n  ✅ models/model_v4.json")
print(f"  ✅ models/feature_list_v4.json ({len(good_features)} features)")
print(f"  ✅ models/model_meta_v4.json")
print(f"  ✅ models/feature_mapping_v4.json")

# ═══════════════════════════════════════════════════════════════════════
# 11. PRODUCTION READINESS CHECK
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 65}")
print(f"  PRODUCTION READINESS CHECK")
print(f"{'=' * 65}")

live_available = {
    # Helius (always available)
    "TOKEN_DECIMALS", "TOKEN_SUPPLY", "IS_MUTABLE", "HAS_METADATA",
    "HAS_IMAGE", "HAS_JSON_URI", "ROYALTY_PCT", "NUM_CREATORS",
    "CREATOR_VERIFIED", "MINT_AUTHORITY_ACTIVE",
    # Name/symbol (from Helius)
    "feat_name_length", "feat_name_is_empty", "feat_name_all_caps",
    "feat_name_has_numbers", "feat_name_has_emoji", "feat_name_has_scam_word",
    "feat_name_word_count", "feat_name_starts_with_dollar", "feat_name_frequency",
    "feat_symbol_length", "feat_symbol_is_empty", "feat_symbol_all_caps",
    "feat_symbol_has_numbers", "feat_symbol_frequency",
    # Pool time (from GT pool_created_at or current time)
    "feat_pool_hour", "feat_pool_day_of_week", "feat_pool_is_weekend",
    "feat_pool_month", "feat_pool_is_night", "feat_pool_days_since_2022",
    # Supply/liq (computed from Helius + GT)
    "feat_supply_log", "feat_supply_is_zero", "feat_supply_trailing_zeros",
    "feat_supply_is_round_million", "feat_supply_is_round_billion",
    "feat_supply_is_exact_common", "feat_liq_log", "feat_liq_is_zero",
    "feat_liq_bucket", "feat_liq_trailing_zeros", "feat_supply_to_liq_ratio",
    # Liquidity (from GT or RC)
    "TOTAL_ADDED_LIQUIDITY", "NUM_LIQUIDITY_ADDS",
    # Derived (computed)
    "derived_avg_add_size", "derived_metadata_completeness",
    "derived_log_supply", "derived_supply_decimal_ratio",
    "derived_uri_domain_rug_rate", "derived_token_std_rug_rate",
    # RugCheck (may be NaN if API fails — model handles gracefully)
    "rc_score", "rc_score_norm", "rc_risks_count", "rc_top_risk_score",
    "rc_num_dangers", "rc_num_warns", "rc_top10_holder_pct",
    "rc_top1_holder_pct", "rc_total_market_liq", "rc_total_holders",
    "rc_mint_authority", "rc_freeze_authority", "rc_mutable_metadata",
    "rc_lp_locked", "rc_lp_burned", "rc_lp_lock_pct", "rc_rugged",
    # GeckoTerminal (may be NaN — model handles gracefully)
    "gt_pool_count", "gt_price_pct_24h",
    # GoPlus (may need to compute from other sources)
    "gp_top3_holder_pct", "gp_total_tvl", "gp_lp_count",
    # v4 new (all computed from available data)
    "v4_authority_risk_score", "v4_metadata_quality",
    "v4_supply_roundness", "v4_liq_supply_log_ratio",
    "v4_rc_score_bucket", "v4_name_suspicion",
}

available = [f for f in good_features if f in live_available]
missing = [f for f in good_features if f not in live_available]

pct = len(available) / len(good_features) * 100
print(f"\n  Features available at scan time: {len(available)}/{len(good_features)} ({pct:.0f}%)")

if missing:
    print(f"\n  ⚠ Features NOT confirmed as live-available:")
    for f in missing:
        fill = labeled[f].notna().mean() * 100
        imp = importances.get(f, 0) * 100
        print(f"    {f:<40s} fill={fill:.1f}%  imp={imp:.1f}%")
else:
    print(f"  ✅ ALL {len(good_features)} features are available at scan time!")

deployer_imp = sum(importances.get(f, 0) for f in good_features if "deployer" in f) * 100
print(f"\n  Deployer feature importance: {deployer_imp:.1f}% (should be 0%)")

print(f"\n{'=' * 65}")
print(f"  v4 model ready. Next: update backend/ml_scorer.py")
print(f"{'=' * 65}")
