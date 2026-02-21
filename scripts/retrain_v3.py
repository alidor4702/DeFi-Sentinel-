#!/usr/bin/env python3
"""
Retrain model v3 with deployer features.
Compare with v2 (AUC=0.9988) and v1 (AUC=0.9972).
"""
import pandas as pd
import numpy as np
import json
import os
import warnings
warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')

print("=" * 70)
print("RETRAIN MODEL V3 WITH DEPLOYER FEATURES")
print("=" * 70)

df = pd.read_csv(os.path.join(DATA, 'enriched_v2.csv'), low_memory=False)
print(f"Dataset: {len(df):,} rows x {len(df.columns)} cols")

# Load labels
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'),
                      usecols=['MINT', 'LIQUIDITY_POOL_ADDRESS', 'RUG_LABEL'])
merged = df.merge(labels, on=['MINT', 'LIQUIDITY_POOL_ADDRESS'], how='left', suffixes=('', '_lab'))

rug = merged['RUG_LABEL'].isin(['VERIFIED_RUG', 'LIKELY_RUG'])
legit = merged['RUG_LABEL'] == 'LIKELY_LEGIT'
labeled = merged[rug | legit].copy()
labeled['IS_RUG'] = rug[labeled.index].astype(int)
print(f"Labeled: {len(labeled):,} ({labeled.IS_RUG.sum():,} rug / {(~labeled.IS_RUG.astype(bool)).sum():,} legit)")

# POST-OUTCOME features to exclude
POST_OUTCOME = {
    'TOKEN_PRICE_USD', 'TOTAL_REMOVED_LIQUIDITY', 'REMOVED_RATIO',
    'ADD_TO_REMOVE_RATIO', 'LIFESPAN_H', 'NUM_LIQUIDITY_REMOVES',
    'LAST_POOL_ACTIVITY_TIMESTAMP', 'LAST_SWAP_TIMESTAMP',
    'INACTIVITY_STATUS', 'NUM_SWAPS', 'TOTAL_SWAP_VOLUME',
    'derived_has_price', 'derived_pool_active_hours', 'derived_events_per_hour',
    'derived_drain_speed_pct_per_hour', 'derived_single_drain_flag',
    'derived_liquidity_depth_ratio', 'derived_avg_remove_size',
    'derived_remove_add_size_ratio'
}

IDS = {
    'MINT', 'LIQUIDITY_POOL_ADDRESS', 'OWNER', 'SOURCE',
    'POOL_OPEN_TIMESTAMP', 'POOL_OPEN_DATE', 'TOKEN_NAME', 'TOKEN_SYMBOL',
    'URI', 'URI_HASH', 'METADATA_URI', 'RAYDIUM_POOL_ID',
    'gt_pool_name', 'gt_pool_dex', 'gt_pool_created',
    'FIRST_POOL_ACTIVITY_TIMESTAMP', 'FIRST', 'LAST', 'TOKEN_PROGRAM',
    'MINT_AUTHORITY', 'RUG_LABEL', 'IS_RUG', 'RUG_LABEL_lab'
}

# Global deployer features could leak (they use future data)
# Only use TEMPORAL deployer features (past-only) to be honest
LEAKY_DEPLOYER = {
    'feat_deployer_token_count', 'feat_deployer_rug_count',
    'feat_deployer_rug_rate', 'feat_deployer_median_liquidity',
    'feat_deployer_is_rug_factory', 'feat_deployer_is_repeat',
}

# Select features
feature_cols = [c for c in labeled.columns
                if c not in POST_OUTCOME
                and c not in IDS
                and c not in LEAKY_DEPLOYER
                and labeled[c].dtype in ['float64', 'int64', 'float32', 'int32', 'int8', 'uint8']]

# Remove sparse (<20% fill)
good_features = [c for c in feature_cols if labeled[c].notna().mean() > 0.20]
print(f"Feature candidates: {len(feature_cols)}, after fill filter: {len(good_features)}")

# Temporal split
ts = pd.to_datetime(labeled['FIRST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')
cutoff = pd.Timestamp('2024-01-01')
train_mask = ts < cutoff
test_mask = ts >= cutoff

X_train = labeled.loc[train_mask, good_features].fillna(-1)
y_train = labeled.loc[train_mask, 'IS_RUG']
X_test = labeled.loc[test_mask, good_features].fillna(-1)
y_test = labeled.loc[test_mask, 'IS_RUG']
print(f"Train: {len(X_train):,} (rug={y_train.sum():,}), Test: {len(X_test):,} (rug={y_test.sum():,})")

# Train
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, classification_report, matthews_corrcoef

model = XGBClassifier(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.08,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=len(y_train[y_train==0]) / max(len(y_train[y_train==1]), 1),
    random_state=42,
    eval_metric='logloss',
    verbosity=0
)
model.fit(X_train, y_train)

# Evaluate
y_pred_proba = model.predict_proba(X_test)[:, 1]
y_pred = (y_pred_proba >= 0.5).astype(int)
auc = roc_auc_score(y_test, y_pred_proba)
mcc = matthews_corrcoef(y_test, y_pred)

print(f"\n{'='*60}")
print(f"MODEL V3 RESULTS")
print(f"{'='*60}")
print(f"AUC-ROC: {auc:.4f}")
print(f"MCC: {mcc:.4f}")
print(classification_report(y_test, y_pred, target_names=['Legit', 'Rug'], digits=4))

print(f"\nCOMPARISON:")
print(f"  v1 (original):   AUC=0.9972  MCC=0.9392  (50 features)")
print(f"  v2 (quick wins):  AUC=0.9988  MCC=0.9707  (49 features)")
print(f"  v3 (+ deployer):  AUC={auc:.4f}  MCC={mcc:.4f}  ({len(good_features)} features)")

# Feature importance
importances = dict(zip(good_features, model.feature_importances_))
sorted_imp = sorted(importances.items(), key=lambda x: -x[1])

print(f"\nTOP 25 FEATURES:")
for i, (feat, imp) in enumerate(sorted_imp[:25]):
    tag = ""
    if feat.startswith('feat_deployer_'): tag = "DEPLOYER"
    elif feat.startswith('feat_'): tag = "NEW"
    print(f"  {i+1:2d}. {imp*100:>5.1f}%  {feat:<50s} {tag}")

# Deployer features contribution
deployer_imp = sum(imp for f, imp in importances.items() if 'deployer' in f)
new_imp = sum(imp for f, imp in importances.items() if f.startswith('feat_'))
print(f"\nDeployer features total importance: {deployer_imp*100:.1f}%")
print(f"All new features total importance: {new_imp*100:.1f}%")

# Save
model.save_model(os.path.join(BASE, 'models', 'model_v3.json'))
with open(os.path.join(BASE, 'models', 'feature_list_v3.json'), 'w') as f:
    json.dump(good_features, f, indent=2)

meta = {
    'model_version': 'v3_deployer',
    'algorithm': 'XGBClassifier',
    'n_estimators': 400,
    'max_depth': 6,
    'training_samples': int(len(X_train)),
    'test_samples': int(len(X_test)),
    'metrics': {'auc_roc': float(auc), 'mcc': float(mcc)},
    'features_count': len(good_features),
    'deployer_features': [f for f in good_features if 'deployer' in f],
    'deployer_importance_pct': float(deployer_imp * 100),
    'top_features': [(f, float(imp)) for f, imp in sorted_imp[:25]],
}
with open(os.path.join(BASE, 'models', 'model_meta_v3.json'), 'w') as f:
    json.dump(meta, f, indent=2)

print(f"\nSaved: models/model_v3.json, feature_list_v3.json, model_meta_v3.json")
