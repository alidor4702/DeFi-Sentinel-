"""
Audit: Does INACTIVITY_STATUS == 'Inactive' actually mean rug pull?
Paper says: "We treat inactivity as a signal for suspicious behavior 
            and NOT as definitive evidence for rug pull."
Let's quantify the noise in this label.
"""
import pandas as pd
import numpy as np

dfs = []
for f in ['2021.csv', '2022.csv', '2023.csv', 'Jan_2024-Nov_2024.csv']:
    dfs.append(pd.read_csv(f'data/raw/solrpds_dataset/CSV/{f}'))
df = pd.concat(dfs, ignore_index=True)

inactive = df[df['INACTIVITY_STATUS'] == 'Inactive']
active = df[df['INACTIVITY_STATUS'] == 'Active']

print("=" * 70)
print("LABEL AUDIT: INACTIVITY_STATUS as proxy for IS_RUG")
print("=" * 70)
print(f"Active:   {len(active):>7,} rows ({len(active)/len(df)*100:.1f}%)")
print(f"Inactive: {len(inactive):>7,} rows ({len(inactive)/len(df)*100:.1f}%)")
print()

# --- Parse timestamps ---
df['FIRST'] = pd.to_datetime(df['FIRST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')
df['LAST'] = pd.to_datetime(df['LAST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')
df['LAST_SWAP'] = pd.to_datetime(df['LAST_SWAP_TIMESTAMP'], errors='coerce')
df['LIFESPAN_H'] = (df['LAST'] - df['FIRST']).dt.total_seconds() / 3600

inactive = df[df['INACTIVITY_STATUS'] == 'Inactive']
active = df[df['INACTIVITY_STATUS'] == 'Active']

# --- 1. Inactive token lifespans ---
print("--- INACTIVE TOKEN LIFESPANS ---")
print("Short-lived inactive = likely rug. Long-lived inactive = likely dead project.")
for label, lo, hi in [
    ("< 1 hour", None, 1), ("1-6 hours", 1, 6), ("6-24 hours", 6, 24),
    ("1-7 days", 24, 168), ("7-30 days", 168, 720), ("30-180 days", 720, 4320),
    ("> 180 days", 4320, None)
]:
    if lo is None:
        subset = inactive[inactive['LIFESPAN_H'] < hi]
    elif hi is None:
        subset = inactive[inactive['LIFESPAN_H'] >= lo]
    else:
        subset = inactive[(inactive['LIFESPAN_H'] >= lo) & (inactive['LIFESPAN_H'] < hi)]
    print(f"  {label:<15} {len(subset):>6,} ({len(subset)/len(inactive)*100:.1f}%)")
print()

# --- 2. Liquidity drain patterns ---
print("--- LIQUIDITY DRAIN PATTERNS (Inactive tokens) ---")
inactive_c = inactive.copy()
inactive_c['REMOVED_RATIO'] = inactive_c['TOTAL_REMOVED_LIQUIDITY'] / inactive_c['TOTAL_ADDED_LIQUIDITY'].replace(0, np.nan)

print(f"  Removed > 90% of added (clear drain):  {(inactive_c['REMOVED_RATIO'] > 0.9).sum():>6,} ({(inactive_c['REMOVED_RATIO'] > 0.9).mean()*100:.1f}%)")
print(f"  Removed 50-90% of added:                {((inactive_c['REMOVED_RATIO'] > 0.5) & (inactive_c['REMOVED_RATIO'] <= 0.9)).sum():>6,} ({((inactive_c['REMOVED_RATIO'] > 0.5) & (inactive_c['REMOVED_RATIO'] <= 0.9)).mean()*100:.1f}%)")
print(f"  Removed < 50% of added (partial drain): {(inactive_c['REMOVED_RATIO'] <= 0.5).sum():>6,} ({(inactive_c['REMOVED_RATIO'] <= 0.5).mean()*100:.1f}%)")
print(f"  Removed < 10% of added (barely drained):{(inactive_c['REMOVED_RATIO'] < 0.1).sum():>6,} ({(inactive_c['REMOVED_RATIO'] < 0.1).mean()*100:.1f}%)")
print()

# --- 3. Classic rug signature: 1 add, 1 remove, short life ---
print("--- CLASSIC RUG SIGNATURE ---")
classic_rug = inactive[
    (inactive['NUM_LIQUIDITY_ADDS'] == 1) &
    (inactive['NUM_LIQUIDITY_REMOVES'] == 1)
]
print(f"  1 add + 1 remove (textbook rug):  {len(classic_rug):>6,} ({len(classic_rug)/len(inactive)*100:.1f}% of inactive)")

classic_rug_short = classic_rug[classic_rug['LIFESPAN_H'] < 24]
print(f"    ... and lifespan < 24h:         {len(classic_rug_short):>6,} ({len(classic_rug_short)/len(inactive)*100:.1f}% of inactive)")
print()

# --- 4. Suspicious pattern: lots of activity then death ---
print("--- LIKELY DEAD PROJECTS (not rugs, just failed) ---")
many_txns = inactive[
    (inactive['NUM_LIQUIDITY_ADDS'] > 10) &
    (inactive['NUM_LIQUIDITY_REMOVES'] > 10)
]
print(f"  >10 adds AND >10 removes:        {len(many_txns):>6,} ({len(many_txns)/len(inactive)*100:.1f}% of inactive)")

long_lived = inactive[inactive['LIFESPAN_H'] > 720]  # > 30 days
print(f"  Lifespan > 30 days:               {len(long_lived):>6,} ({len(long_lived)/len(inactive)*100:.1f}% of inactive)")

dead_project = inactive[
    (inactive['NUM_LIQUIDITY_ADDS'] > 5) &
    (inactive['NUM_LIQUIDITY_REMOVES'] > 5) &
    (inactive['LIFESPAN_H'] > 168)  # > 7 days
]
print(f"  >5 adds, >5 removes, >7d life:   {len(dead_project):>6,} ({len(dead_project)/len(inactive)*100:.1f}% of inactive)")
print(f"  ^ These are probably FALSE POSITIVES if labeled as rug")
print()

# --- 5. Active tokens that look like slow rugs ---
print("--- FALSE NEGATIVES: ACTIVE TOKENS THAT LOOK LIKE RUGS ---")
active_c = active.copy()
active_c['REMOVED_RATIO'] = active_c['TOTAL_REMOVED_LIQUIDITY'] / active_c['TOTAL_ADDED_LIQUIDITY'].replace(0, np.nan)

active_drained = active_c[active_c['REMOVED_RATIO'] > 0.95]
print(f"  Active but >95% liquidity removed: {len(active_drained):>6,} ({len(active_drained)/len(active)*100:.1f}% of active)")

active_few_txns = active_c[
    (active_c['REMOVED_RATIO'] > 0.9) &
    (active_c['NUM_LIQUIDITY_ADDS'] <= 2) &
    (active_c['NUM_LIQUIDITY_REMOVES'] <= 2)
]
print(f"  Active, >90% drained, <=2 adds/removes: {len(active_few_txns):>6,} ({len(active_few_txns)/len(active)*100:.1f}% of active)")
print(f"  ^ These are probably SLOW RUGS mislabeled as Active")
print()

# --- 6. Use enriched data for ground truth cross-check ---
print("--- ENRICHED DATA CROSS-CHECK ---")
try:
    edf = pd.read_csv('data/enriched/enriched_full.csv', low_memory=False)
    inactive_e = edf[edf['INACTIVITY_STATUS'] == 'Inactive']
    active_e = edf[edf['INACTIVITY_STATUS'] == 'Active']
    
    for col, label in [
        ('HAS_METADATA', 'Has metadata'),
        ('IS_MUTABLE', 'Is mutable'),
        ('MINT_AUTHORITY_ACTIVE', 'Mint authority active'),
        ('FREEZE_AUTHORITY_ACTIVE', 'Freeze authority active'),
        ('IS_BURNT', 'Token is burnt'),
    ]:
        if col in edf.columns:
            ia_rate = inactive_e[col].mean()
            ac_rate = active_e[col].mean()
            print(f"  {label:<30} Inactive={ia_rate:.3f}  Active={ac_rate:.3f}  diff={ia_rate-ac_rate:+.3f}")
    
    # Price check: how many inactive tokens have a price (shouldn't if truly dead)
    inactive_has_price = inactive_e['TOKEN_PRICE_USD'].notna().mean()
    active_has_price = active_e['TOKEN_PRICE_USD'].notna().mean()
    print(f"\n  Has price on market:              Inactive={inactive_has_price:.3f}  Active={active_has_price:.3f}")
    
    # Inactive tokens WITH a price — these might not be real rugs
    inactive_priced = inactive_e[inactive_e['TOKEN_PRICE_USD'].notna()]
    print(f"  Inactive tokens still with price: {len(inactive_priced):,} ({len(inactive_priced)/len(inactive_e)*100:.1f}% of inactive)")
    print(f"  ^ If token still has market price, was it really a rug?")

except Exception as e:
    print(f"  Could not load enriched data: {e}")

print()
print("=" * 70)
print("VERDICT")
print("=" * 70)
print("""
The SolRPDS paper EXPLICITLY says:
  "We treat inactivity as a signal for suspicious behavior 
   and NOT as definitive evidence for rug pull."

Using Inactive = IS_RUG introduces TWO types of label noise:

  FALSE POSITIVES (Inactive but NOT a rug):
    - Legit projects that simply failed/died naturally
    - Tokens that migrated to a new contract
    - Seasonal/event tokens that completed their purpose
    - Tokens with long lifespans and lots of trading activity

  FALSE NEGATIVES (Active but IS a rug):
    - Slow rugs where liquidity is drained gradually
    - Tokens still traded by bots/unaware users after drain
    - "Suspected" cases the paper explicitly mentions

RECOMMENDATION: Create a CONFIDENCE-WEIGHTED label instead:
  - HIGH confidence rug:   Inactive + <24h life + 1 add/1 remove + >90% drained
  - MEDIUM confidence rug: Inactive + <7d life + >50% drained  
  - LOW confidence rug:    Inactive + long life or lots of activity
  - SUSPECTED rug:         Active + >90% drained + few transactions
  - LIKELY legit:          Active + balanced ratio + sustained trading
""")
