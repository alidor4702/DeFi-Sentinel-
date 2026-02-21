#!/usr/bin/env python3
"""Quick deployer audit for ML pipeline report."""
import pandas as pd

df = pd.read_csv('data/enriched/enriched_v2.csv', usecols=[
    'feat_deployer_past_tokens','feat_deployer_past_rugs','feat_deployer_past_rug_rate',
    'feat_deployer_past_labeled','feat_deployer_past_is_serial','MINT_AUTHORITY'
], low_memory=False)

print("=== DEPLOYER FEATURE FILL RATES (training data) ===")
for c in ['feat_deployer_past_tokens','feat_deployer_past_rugs',
          'feat_deployer_past_rug_rate','feat_deployer_past_labeled',
          'feat_deployer_past_is_serial']:
    fill = df[c].notna().mean()*100
    print(f"  {c:45s} fill={fill:5.1f}%  mean={df[c].mean():.4f}")

print()
print(f"MINT_AUTHORITY filled: {df['MINT_AUTHORITY'].notna().mean()*100:.1f}%")
print(f"Unique deployers: {df['MINT_AUTHORITY'].nunique()}")

pt = df['feat_deployer_past_tokens']
print(f"\npast_tokens == 0: {(pt == 0).sum()} ({(pt==0).mean()*100:.1f}%)")
print(f"past_tokens > 0:  {(pt > 0).sum()} ({(pt>0).mean()*100:.1f}%)")
print(f"past_tokens > 10: {(pt > 10).sum()} ({(pt>10).mean()*100:.1f}%)")
print(f"past_tokens median: {pt.median():.0f}")
print(f"past_tokens mean: {pt.mean():.1f}")

pl = df['feat_deployer_past_labeled']
print(f"\npast_labeled == 0: {(pl == 0).sum()} ({(pl==0).mean()*100:.1f}%)")
print(f"past_labeled > 0:  {(pl > 0).sum()} ({(pl>0).mean()*100:.1f}%)")
print(f"past_labeled median: {pl.median():.0f}")
print(f"past_labeled mean: {pl.mean():.1f}")
