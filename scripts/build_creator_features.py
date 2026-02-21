#!/usr/bin/env python3
"""
Build serial-rugger features from MINT_AUTHORITY (deployer address).
Zero API calls — all from our own labeled dataset.

For each deployer:
- How many tokens they launched (in our dataset)
- How many of those were rugs
- Their rug rate
- Average lifespan of their tokens
- Average initial liquidity

Then for each token, compute a TEMPORAL version:
- Only use data from BEFORE that token was created (no future leakage)
"""
import pandas as pd
import numpy as np
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')

print("=" * 70)
print("BUILDING SERIAL RUGGER FEATURES")
print("=" * 70)

# Load v2 data
df = pd.read_csv(os.path.join(DATA, 'enriched_v2.csv'), low_memory=False)

# We need MINT_AUTHORITY from the clean data (was it dropped?)
if 'MINT_AUTHORITY' not in df.columns:
    print("MINT_AUTHORITY not in v2, loading from enriched_clean.csv...")
    clean = pd.read_csv(os.path.join(DATA, 'enriched_clean.csv'), 
                        usecols=['MINT', 'LIQUIDITY_POOL_ADDRESS', 'MINT_AUTHORITY'],
                        low_memory=False)
    df = df.merge(clean[['MINT', 'LIQUIDITY_POOL_ADDRESS', 'MINT_AUTHORITY']], 
                  on=['MINT', 'LIQUIDITY_POOL_ADDRESS'], how='left')

print(f"Dataset: {len(df):,} rows")
print(f"MINT_AUTHORITY filled: {df['MINT_AUTHORITY'].notna().sum():,} ({df['MINT_AUTHORITY'].notna().mean()*100:.1f}%)")
print(f"Unique deployers: {df['MINT_AUTHORITY'].nunique():,}")

# Load labels
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'),
                      usecols=['MINT', 'LIQUIDITY_POOL_ADDRESS', 'RUG_LABEL'])
df = df.merge(labels, on=['MINT', 'LIQUIDITY_POOL_ADDRESS'], how='left', suffixes=('', '_lab'))

# Parse timestamps for temporal ordering
df['_ts'] = pd.to_datetime(df['FIRST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')

# Create IS_RUG for the entire dataset (where labeled)
rug_mask = df['RUG_LABEL'].isin(['VERIFIED_RUG', 'LIKELY_RUG'])
legit_mask = df['RUG_LABEL'] == 'LIKELY_LEGIT'
df['_is_rug'] = np.where(rug_mask, 1, np.where(legit_mask, 0, np.nan))

# Sort by timestamp for temporal computation
df = df.sort_values('_ts').reset_index(drop=True)

print(f"\nLabeled rows: {df['_is_rug'].notna().sum():,}")
print(f"  Rugs: {(df['_is_rug']==1).sum():,}")
print(f"  Legit: {(df['_is_rug']==0).sum():,}")

# =====================================================================
# METHOD 1: GLOBAL DEPLOYER STATS (simpler, for all rows)
# =====================================================================
print("\n" + "=" * 70)
print("GLOBAL DEPLOYER STATS (all tokens by same deployer)")
print("=" * 70)

# Group by deployer - count total tokens in dataset
deployer_token_count = df.groupby('MINT_AUTHORITY')['MINT'].nunique()
df['feat_deployer_token_count'] = df['MINT_AUTHORITY'].map(deployer_token_count)

# Group by deployer - count how many labeled as rug
deployer_rug_count = df[df['_is_rug']==1].groupby('MINT_AUTHORITY')['MINT'].nunique()
df['feat_deployer_rug_count'] = df['MINT_AUTHORITY'].map(deployer_rug_count).fillna(0)

# Deployer rug rate
deployer_labeled = df[df['_is_rug'].notna()].groupby('MINT_AUTHORITY').agg(
    labeled_count=('_is_rug', 'count'),
    rug_sum=('_is_rug', 'sum')
)
deployer_labeled['rug_rate'] = deployer_labeled['rug_sum'] / deployer_labeled['labeled_count']
df['feat_deployer_rug_rate'] = df['MINT_AUTHORITY'].map(deployer_labeled['rug_rate'])

# Average initial liquidity per deployer
if 'TOTAL_ADDED_LIQUIDITY' in df.columns:
    deployer_avg_liq = df.groupby('MINT_AUTHORITY')['TOTAL_ADDED_LIQUIDITY'].median()
    df['feat_deployer_median_liquidity'] = df['MINT_AUTHORITY'].map(deployer_avg_liq)

# Is this a known "rug factory" (deployed >3 tokens AND rug_rate > 0.7)?
df['feat_deployer_is_rug_factory'] = (
    (df['feat_deployer_token_count'] >= 3) & 
    (df['feat_deployer_rug_rate'] > 0.7)
).astype(int)

# Is this a repeat deployer at all?
df['feat_deployer_is_repeat'] = (df['feat_deployer_token_count'] > 1).astype(int)

# =====================================================================
# METHOD 2: TEMPORAL DEPLOYER STATS (only past data, no future leakage)
# =====================================================================
print("\n" + "=" * 70)
print("TEMPORAL DEPLOYER STATS (only tokens created BEFORE this one)")
print("=" * 70)

# For each row, count how many tokens this deployer launched BEFORE this timestamp
# This is the honest version — no future leakage
temporal_features = []

# Group by deployer and iterate
deployer_groups = df.groupby('MINT_AUTHORITY')

total_deployers = len(deployer_groups)
processed = 0

# Pre-allocate arrays
n = len(df)
past_token_count = np.zeros(n)
past_rug_count = np.zeros(n)
past_rug_rate = np.full(n, np.nan)
past_labeled_count = np.zeros(n)

for deployer, group in deployer_groups:
    if pd.isna(deployer):
        continue
    
    processed += 1
    if processed % 5000 == 0:
        print(f"  Processed {processed}/{total_deployers} deployers...")
    
    # Sort by timestamp
    sorted_group = group.sort_values('_ts')
    idxs = sorted_group.index.values
    is_rug = sorted_group['_is_rug'].values
    
    # Cumulative counts (shifted by 1 to exclude current token)
    cum_count = np.arange(len(idxs))  # 0, 1, 2, ... (count before this one)
    cum_rug = np.zeros(len(idxs))
    cum_labeled = np.zeros(len(idxs))
    
    running_rug = 0
    running_labeled = 0
    for i in range(len(idxs)):
        cum_rug[i] = running_rug
        cum_labeled[i] = running_labeled
        if not np.isnan(is_rug[i]):
            running_rug += is_rug[i]
            running_labeled += 1
    
    past_token_count[idxs] = cum_count
    past_rug_count[idxs] = cum_rug
    past_labeled_count[idxs] = cum_labeled
    
    # Rate: only where we have at least 1 labeled past token
    for i, idx in enumerate(idxs):
        if cum_labeled[i] > 0:
            past_rug_rate[idx] = cum_rug[i] / cum_labeled[i]

df['feat_deployer_past_tokens'] = past_token_count
df['feat_deployer_past_rugs'] = past_rug_count
df['feat_deployer_past_rug_rate'] = past_rug_rate
df['feat_deployer_past_labeled'] = past_labeled_count

# Past rug factory flag (temporal)
df['feat_deployer_past_is_serial'] = (
    (df['feat_deployer_past_tokens'] >= 2) & 
    (df['feat_deployer_past_rug_rate'] > 0.5)
).astype(int)

print(f"\nProcessed {processed} deployers")

# =====================================================================
# SUMMARY
# =====================================================================
print("\n" + "=" * 70)
print("FEATURE SUMMARY")
print("=" * 70)

new_feats = [c for c in df.columns if c.startswith('feat_deployer_')]
for f in new_feats:
    fill = df[f].notna().mean() * 100
    if df[f].dtype in ['float64', 'int64']:
        print(f"  {f:<40s} fill={fill:5.1f}%  mean={df[f].mean():.4f}  median={df[f].median():.4f}")

# Check separation power on labeled set
print("\n" + "=" * 70)
print("SEPARATION POWER (labeled set)")
print("=" * 70)

labeled = df[df['_is_rug'].notna()].copy()
for f in new_feats:
    if labeled[f].dtype in ['float64', 'int64', 'float32']:
        rug_m = labeled.loc[labeled['_is_rug']==1, f].dropna().mean()
        leg_m = labeled.loc[labeled['_is_rug']==0, f].dropna().mean()
        std = labeled[f].std()
        sep = abs(rug_m - leg_m) / (std + 1e-10) if std > 0 else 0
        print(f"  {f:<40s} sep={sep:.3f}  rug={rug_m:.4f}  legit={leg_m:.4f}")

# =====================================================================
# SAVE
# =====================================================================
print("\n" + "=" * 70)
print("SAVING")
print("=" * 70)

# Drop temp columns
df.drop(columns=['_ts', '_is_rug', 'RUG_LABEL'], inplace=True, errors='ignore')

# Save updated v2
out_path = os.path.join(DATA, 'enriched_v2.csv')
df.to_csv(out_path, index=False)
print(f"Saved: {out_path}")
print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} cols")
print(f"New deployer features: {len(new_feats)}")
