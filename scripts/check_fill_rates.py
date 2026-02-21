#!/usr/bin/env python3
"""Quick check: fill rates for all candidate v4 features in labeled data."""
import pandas as pd
import numpy as np
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')

df = pd.read_csv(os.path.join(DATA, 'enriched_v2.csv'), low_memory=False)
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'),
                      usecols=['MINT','LIQUIDITY_POOL_ADDRESS','RUG_LABEL'])
merged = df.merge(labels, on=['MINT','LIQUIDITY_POOL_ADDRESS'], how='left')
rug = merged['RUG_LABEL'].isin(['VERIFIED_RUG','LIKELY_RUG'])
legit = merged['RUG_LABEL'] == 'LIKELY_LEGIT'
labeled = merged[rug | legit].copy()

print(f"Labeled dataset: {len(labeled)} rows")
print(f"{'Column':<45s} {'Fill%':>6s}  {'Nunique':>8s}  {'dtype':>10s}")
print('-' * 75)

# All numeric columns
for c in sorted(labeled.columns):
    if labeled[c].dtype in ['float64','int64','float32','int32','int8','uint8','bool']:
        fill = labeled[c].notna().mean() * 100
        nuniq = labeled[c].nunique()
        print(f"  {c:<43s} {fill:>5.1f}%  {nuniq:>8d}  {str(labeled[c].dtype):>10s}")

print("\n\n--- NON-NUMERIC (for reference) ---")
for c in sorted(labeled.columns):
    if labeled[c].dtype not in ['float64','int64','float32','int32','int8','uint8','bool']:
        fill = labeled[c].notna().mean() * 100
        print(f"  {c:<43s} {fill:>5.1f}%  {str(labeled[c].dtype):>10s}")
