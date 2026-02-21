#!/usr/bin/env python3
"""
ALL 7 QUICK WINS IN ONE SHOT
1. Drop 35 dead columns
2. Engineer TOKEN_NAME/SYMBOL features
3. Engineer TIMESTAMP features
4. Engineer TOKEN_SUPPLY features
5. Engineer TOTAL_ADDED_LIQUIDITY features
6. Merge 889 real RugCheck cache entries
7. Retrain model and compare
"""
import pandas as pd
import numpy as np
import json
import re
import os
import warnings
warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')

print("=" * 70)
print("LOADING DATA")
print("=" * 70)
df = pd.read_csv(os.path.join(DATA, 'enriched_clean.csv'), low_memory=False)
print(f"Starting: {len(df):,} rows x {len(df.columns)} cols")

# =====================================================================
# STEP 1: DROP 35 DEAD COLUMNS (<1% fill)
# =====================================================================
print("\n" + "=" * 70)
print("STEP 1: DROPPING DEAD COLUMNS")
print("=" * 70)

dead_cols = []
for c in df.columns:
    fill_pct = df[c].notna().mean() * 100
    if fill_pct < 1.0:
        dead_cols.append(c)

# Keep OWNER (might be useful later) but drop all RC/GP/GT dead cols
# Actually OWNER is 0.08% fill — useless. Drop it too.
print(f"Dropping {len(dead_cols)} dead columns:")
for c in dead_cols:
    print(f"  - {c} ({df[c].notna().mean()*100:.2f}%)")

df.drop(columns=dead_cols, inplace=True)
print(f"After drop: {len(df.columns)} cols")

# =====================================================================
# STEP 2: TOKEN_NAME / TOKEN_SYMBOL FEATURES
# =====================================================================
print("\n" + "=" * 70)
print("STEP 2: NAME/SYMBOL FEATURES")
print("=" * 70)

# Common scam patterns
SCAM_WORDS = [
    'moon', 'safe', 'elon', 'musk', 'doge', 'shib', 'pepe', 'wojak',
    'inu', 'floki', 'baby', 'mini', 'mega', 'super', 'king', 'queen',
    'rich', 'pump', 'gem', 'rocket', '100x', '1000x', 'lambo',
    'millionaire', 'billion', 'trillion', 'gold', 'diamond',
    'ai', 'gpt', 'chad', 'based', 'wagmi', 'hodl'
]
scam_pattern = re.compile('|'.join(SCAM_WORDS), re.IGNORECASE)

if 'TOKEN_NAME' in df.columns:
    name = df['TOKEN_NAME'].fillna('')
    df['feat_name_length'] = name.str.len()
    df['feat_name_is_empty'] = (name == '').astype(int)
    df['feat_name_all_caps'] = name.apply(lambda x: int(x == x.upper() and len(x) > 0))
    df['feat_name_has_numbers'] = name.str.contains(r'\d', regex=True).astype(int)
    df['feat_name_has_emoji'] = name.apply(lambda x: int(bool(re.search(r'[^\w\s\-\.\,\!\?\'\"\(\)\[\]\{\}\@\#\$\%\^\&\*\+\=\/\\]', x)))) 
    df['feat_name_has_scam_word'] = name.apply(lambda x: int(bool(scam_pattern.search(x))))
    df['feat_name_word_count'] = name.str.split().str.len().fillna(0).astype(int)
    df['feat_name_starts_with_dollar'] = name.str.startswith('$').astype(int)
    
    # Count how many tokens share the same name (popular = copycats)
    name_counts = name.value_counts().to_dict()
    df['feat_name_frequency'] = name.map(name_counts).fillna(1)
    
    print(f"  feat_name_length: mean={df['feat_name_length'].mean():.1f}")
    print(f"  feat_name_all_caps: {df['feat_name_all_caps'].mean()*100:.1f}%")
    print(f"  feat_name_has_scam_word: {df['feat_name_has_scam_word'].mean()*100:.1f}%")
    print(f"  feat_name_has_emoji: {df['feat_name_has_emoji'].mean()*100:.1f}%")
    print(f"  feat_name_frequency: median={df['feat_name_frequency'].median():.0f}")

if 'TOKEN_SYMBOL' in df.columns:
    sym = df['TOKEN_SYMBOL'].fillna('')
    df['feat_symbol_length'] = sym.str.len()
    df['feat_symbol_is_empty'] = (sym == '').astype(int)
    df['feat_symbol_all_caps'] = sym.apply(lambda x: int(x == x.upper() and len(x) > 0))
    df['feat_symbol_has_numbers'] = sym.str.contains(r'\d', regex=True).astype(int)
    
    # Symbol uniqueness
    sym_counts = sym.value_counts().to_dict()
    df['feat_symbol_frequency'] = sym.map(sym_counts).fillna(1)
    
    print(f"  feat_symbol_length: mean={df['feat_symbol_length'].mean():.1f}")
    print(f"  feat_symbol_has_numbers: {df['feat_symbol_has_numbers'].mean()*100:.1f}%")

new_name_cols = [c for c in df.columns if c.startswith('feat_name_') or c.startswith('feat_symbol_')]
print(f"  Created {len(new_name_cols)} name/symbol features")

# =====================================================================
# STEP 3: TIMESTAMP FEATURES
# =====================================================================
print("\n" + "=" * 70)
print("STEP 3: TIMESTAMP FEATURES")
print("=" * 70)

ts_col = 'FIRST_POOL_ACTIVITY_TIMESTAMP'
if ts_col in df.columns:
    ts = pd.to_datetime(df[ts_col], errors='coerce')
    df['feat_pool_hour'] = ts.dt.hour
    df['feat_pool_day_of_week'] = ts.dt.dayofweek  # 0=Mon, 6=Sun
    df['feat_pool_is_weekend'] = (ts.dt.dayofweek >= 5).astype(int)
    df['feat_pool_month'] = ts.dt.month
    df['feat_pool_is_night'] = ((ts.dt.hour >= 22) | (ts.dt.hour <= 5)).astype(int)
    
    # Era feature — rug behavior changes over time
    ref_date = pd.Timestamp('2022-01-01')
    df['feat_pool_days_since_2022'] = (ts - ref_date).dt.days
    
    print(f"  feat_pool_hour: mean={df['feat_pool_hour'].mean():.1f}")
    print(f"  feat_pool_is_weekend: {df['feat_pool_is_weekend'].mean()*100:.1f}%")
    print(f"  feat_pool_is_night: {df['feat_pool_is_night'].mean()*100:.1f}%")

ts_feats = [c for c in df.columns if c.startswith('feat_pool_')]
print(f"  Created {len(ts_feats)} timestamp features")

# =====================================================================
# STEP 4: TOKEN_SUPPLY FEATURES
# =====================================================================
print("\n" + "=" * 70)
print("STEP 4: SUPPLY FEATURES")
print("=" * 70)

if 'TOKEN_SUPPLY' in df.columns:
    supply = df['TOKEN_SUPPLY'].fillna(0).astype(float)
    
    df['feat_supply_log'] = np.log10(supply.clip(lower=1))
    df['feat_supply_is_zero'] = (supply == 0).astype(int)
    
    # Round number detection
    def trailing_zeros(x):
        if x == 0:
            return 0
        s = str(int(x))
        return len(s) - len(s.rstrip('0'))
    
    df['feat_supply_trailing_zeros'] = supply.apply(trailing_zeros)
    df['feat_supply_is_round_million'] = ((supply > 0) & (supply % 1_000_000 == 0)).astype(int)
    df['feat_supply_is_round_billion'] = ((supply > 0) & (supply % 1_000_000_000 == 0)).astype(int)
    
    # Common lazy supply amounts
    common_supplies = [1_000_000, 10_000_000, 100_000_000, 1_000_000_000, 
                       10_000_000_000, 100_000_000_000, 1_000_000_000_000]
    df['feat_supply_is_exact_common'] = supply.isin(common_supplies).astype(int)
    
    print(f"  feat_supply_log: mean={df['feat_supply_log'].mean():.1f}")
    print(f"  feat_supply_is_round_million: {df['feat_supply_is_round_million'].mean()*100:.1f}%")
    print(f"  feat_supply_trailing_zeros: mean={df['feat_supply_trailing_zeros'].mean():.1f}")
    print(f"  feat_supply_is_exact_common: {df['feat_supply_is_exact_common'].mean()*100:.1f}%")

supply_feats = [c for c in df.columns if c.startswith('feat_supply_')]
print(f"  Created {len(supply_feats)} supply features")

# =====================================================================
# STEP 5: LIQUIDITY FEATURES
# =====================================================================
print("\n" + "=" * 70)
print("STEP 5: LIQUIDITY FEATURES")
print("=" * 70)

if 'TOTAL_ADDED_LIQUIDITY' in df.columns:
    liq = df['TOTAL_ADDED_LIQUIDITY'].fillna(0).astype(float)
    
    df['feat_liq_log'] = np.log10(liq.clip(lower=1))
    df['feat_liq_is_zero'] = (liq == 0).astype(int)
    
    # Buckets
    df['feat_liq_bucket'] = pd.cut(
        liq, 
        bins=[-1, 0, 1000, 10000, 100000, 1000000, float('inf')],
        labels=[0, 1, 2, 3, 4, 5]
    ).astype(float)
    
    # Round liquidity detection
    df['feat_liq_trailing_zeros'] = liq.apply(trailing_zeros)
    
    # Ratio of supply to liquidity (token "price pressure")
    if 'TOKEN_SUPPLY' in df.columns:
        safe_supply = df['TOKEN_SUPPLY'].fillna(0).astype(float).clip(lower=1)
        df['feat_supply_to_liq_ratio'] = np.log10(safe_supply / liq.clip(lower=1))
    
    print(f"  feat_liq_log: mean={df['feat_liq_log'].mean():.1f}")
    print(f"  feat_liq_is_zero: {df['feat_liq_is_zero'].mean()*100:.1f}%")
    print(f"  Bucket distribution: {df['feat_liq_bucket'].value_counts().sort_index().to_dict()}")

liq_feats = [c for c in df.columns if c.startswith('feat_liq_') or c == 'feat_supply_to_liq_ratio']
print(f"  Created {len(liq_feats)} liquidity features")

# =====================================================================
# STEP 6: MERGE RUGCHECK CACHE
# =====================================================================
print("\n" + "=" * 70)
print("STEP 6: MERGE RUGCHECK CACHE")
print("=" * 70)

rc_cache_path = os.path.join(DATA, '_rugcheck_cache.json')
rc_data = json.load(open(rc_cache_path))

# Extract real entries (not empty)
rc_rows = []
for mint, data in rc_data.items():
    if isinstance(data, dict) and not data.get('_empty'):
        row = dict(data)
        row['MINT'] = mint  # ensure mint is set
        rc_rows.append(row)

print(f"Real RugCheck entries: {len(rc_rows)}")

if rc_rows:
    rc_df = pd.DataFrame(rc_rows)
    print(f"RC columns: {list(rc_df.columns)}")
    
    # Prefix with rc2_ to avoid collision with existing dead rc_ columns (already dropped)
    rc_keep = [c for c in rc_df.columns if c != 'MINT' and c != '_empty']
    rename_map = {}
    for c in rc_keep:
        if not c.startswith('rc_') and not c.startswith('RC_'):
            rename_map[c] = f'rc2_{c}'
    rc_df.rename(columns=rename_map, inplace=True)
    
    # Drop string cols that won't help the model
    str_drops = [c for c in rc_df.columns if rc_df[c].dtype == 'object' and c != 'MINT']
    rc_df.drop(columns=str_drops, inplace=True, errors='ignore')
    
    print(f"RC numeric features to merge: {[c for c in rc_df.columns if c != 'MINT']}")
    
    # Merge on MINT
    before = len(df.columns)
    df = df.merge(rc_df, on='MINT', how='left', suffixes=('', '_rc_dup'))
    
    # Drop any dup columns from merge
    dup_cols = [c for c in df.columns if c.endswith('_rc_dup')]
    df.drop(columns=dup_cols, inplace=True, errors='ignore')
    
    new_rc_cols = [c for c in df.columns if c.startswith('rc_') or c.startswith('rc2_')]
    for c in new_rc_cols:
        fill = df[c].notna().sum()
        print(f"  {c}: {fill} filled ({fill/len(df)*100:.2f}%)")
    
    print(f"Added {len(df.columns) - before} RC columns")

# =====================================================================
# SAVE ENRICHED V2
# =====================================================================
print("\n" + "=" * 70)
print("SAVING ENRICHED V2")
print("=" * 70)

out_path = os.path.join(DATA, 'enriched_v2.csv')
df.to_csv(out_path, index=False)
print(f"Saved: {out_path}")
print(f"Final shape: {df.shape[0]:,} rows x {df.shape[1]} cols")

# Summary of all new features
all_new = [c for c in df.columns if c.startswith('feat_') or c.startswith('rc_') or c.startswith('rc2_')]
print(f"\nTotal new features created: {len(all_new)}")

# =====================================================================
# STEP 7: RETRAIN MODEL
# =====================================================================
print("\n" + "=" * 70)
print("STEP 7: RETRAIN WITH NEW FEATURES")
print("=" * 70)

# Load labels
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'), 
                      usecols=['MINT', 'LIQUIDITY_POOL_ADDRESS', 'RUG_LABEL'])
merged = df.merge(labels, on=['MINT', 'LIQUIDITY_POOL_ADDRESS'], how='left', suffixes=('','_vl'))

rug = merged['RUG_LABEL'].isin(['VERIFIED_RUG', 'LIKELY_RUG'])
legit = merged['RUG_LABEL'] == 'LIKELY_LEGIT'
labeled = merged[rug | legit].copy()
labeled['IS_RUG'] = rug[labeled.index].astype(int)
print(f"Labeled set: {len(labeled):,} ({labeled.IS_RUG.sum():,} rug / {(~labeled.IS_RUG.astype(bool)).sum():,} legit)")

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
    'MINT_AUTHORITY', 'RUG_LABEL', 'IS_RUG'
}

# Select features
feature_cols = [c for c in labeled.columns 
                if c not in POST_OUTCOME 
                and c not in IDS
                and labeled[c].dtype in ['float64', 'int64', 'float32', 'int32', 'int8', 'uint8']]

print(f"Feature candidates: {len(feature_cols)}")

# Remove any with >80% missing
good_features = []
for c in feature_cols:
    if labeled[c].notna().mean() > 0.20:  # at least 20% fill in labeled set
        good_features.append(c)
    else:
        pass  # silently skip sparse

print(f"Features with >20% fill: {len(good_features)}")

# Temporal split
ts = pd.to_datetime(labeled['FIRST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')
cutoff = pd.Timestamp('2024-01-01')
train_mask = ts < cutoff
test_mask = ts >= cutoff

X_train = labeled.loc[train_mask, good_features].copy()
y_train = labeled.loc[train_mask, 'IS_RUG']
X_test = labeled.loc[test_mask, good_features].copy()
y_test = labeled.loc[test_mask, 'IS_RUG']

print(f"Train: {len(X_train):,} (rug={y_train.sum():,}), Test: {len(X_test):,} (rug={y_test.sum():,})")

# Fill NaN with -1 for XGBoost
X_train = X_train.fillna(-1)
X_test = X_test.fillna(-1)

# Train XGBoost
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, classification_report, matthews_corrcoef

model = XGBClassifier(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.1,
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

print(f"\n{'='*50}")
print(f"NEW MODEL RESULTS")
print(f"{'='*50}")
print(f"AUC-ROC: {auc:.4f}")
print(f"MCC: {mcc:.4f}")
print(classification_report(y_test, y_pred, target_names=['Legit', 'Rug'], digits=3))

# Compare with old model
print(f"\nPREVIOUS MODEL: AUC=0.9972 (50 features)")
print(f"NEW MODEL:      AUC={auc:.4f} ({len(good_features)} features)")
if auc > 0.9972:
    print(">>> IMPROVEMENT! <<<")
elif auc > 0.995:
    print(">>> COMPARABLE (within margin) <<<")
else:
    print(">>> Check for issues <<<")

# Feature importance
importances = dict(zip(good_features, model.feature_importances_))
sorted_imp = sorted(importances.items(), key=lambda x: -x[1])

print(f"\nTOP 20 FEATURES BY IMPORTANCE:")
for i, (feat, imp) in enumerate(sorted_imp[:20]):
    marker = "NEW" if feat.startswith('feat_') or feat.startswith('rc_') or feat.startswith('rc2_') else ""
    print(f"  {i+1:2d}. {imp*100:>5.1f}%  {feat:<50s} {marker}")

# How much do the NEW features contribute?
new_total = sum(imp for feat, imp in importances.items() 
                if feat.startswith('feat_') or feat.startswith('rc_') or feat.startswith('rc2_'))
print(f"\nNew features total importance: {new_total*100:.1f}%")

# Save the new model
print("\n" + "=" * 70)
print("SAVING NEW MODEL")
print("=" * 70)

model.save_model(os.path.join(BASE, 'models', 'model_v2.json'))
with open(os.path.join(BASE, 'models', 'feature_list_v2.json'), 'w') as f:
    json.dump(good_features, f, indent=2)

meta = {
    'model_version': 'v2_quick_wins',
    'algorithm': 'XGBClassifier',
    'n_estimators': 300,
    'max_depth': 6,
    'training_samples': int(len(X_train)),
    'test_samples': int(len(X_test)),
    'metrics': {
        'auc_roc': float(auc),
        'mcc': float(mcc),
    },
    'features_count': len(good_features),
    'new_features_added': len([c for c in good_features if c.startswith('feat_') or c.startswith('rc')]),
    'new_features_importance_pct': float(new_total * 100),
    'top_features': sorted_imp[:20],
    'dropped_dead_columns': len(dead_cols),
}
with open(os.path.join(BASE, 'models', 'model_meta_v2.json'), 'w') as f:
    json.dump(meta, f, indent=2, default=str)

print(f"Saved: models/model_v2.json, feature_list_v2.json, model_meta_v2.json")
print(f"\nDONE. {len(all_new)} new features, {len(dead_cols)} dead columns removed.")
