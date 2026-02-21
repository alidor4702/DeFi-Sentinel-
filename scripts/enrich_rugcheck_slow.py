#!/usr/bin/env python3
"""
Slow RugCheck enrichment — labeled mints only, 2s delay, incremental cache.
Target: enrich all labeled mints we don't already have in cache.
"""
import requests
import json
import time
import os
import sys
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')

# Load cache
CACHE_PATH = os.path.join(DATA, '_rugcheck_cache.json')
if os.path.exists(CACHE_PATH):
    cache = json.load(open(CACHE_PATH))
else:
    cache = {}

# Get already-cached mints with REAL data (not empty)
cached_real = {k for k, v in cache.items() if isinstance(v, dict) and not v.get('_empty')}
cached_empty = {k for k, v in cache.items() if isinstance(v, dict) and v.get('_empty')}
print(f"Cache: {len(cache)} total, {len(cached_real)} real, {len(cached_empty)} empty")

# Load labeled mints (priority)
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'),
                      usecols=['MINT', 'RUG_LABEL'])
labeled_mints = labels['MINT'].unique().tolist()
print(f"Labeled unique mints: {len(labeled_mints)}")

# Filter to only uncached mints
to_enrich = [m for m in labeled_mints if m not in cached_real]
print(f"Need to enrich: {len(to_enrich)} labeled mints")

# Optional limit from command line
limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(to_enrich)
to_enrich = to_enrich[:limit]
print(f"Will enrich: {len(to_enrich)} mints (limit={limit})")

DELAY = 2.0  # seconds between requests
SAVE_EVERY = 50
API_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"

success = 0
fail = 0
rate_limited = 0

for i, mint in enumerate(to_enrich):
    try:
        url = API_URL.format(mint=mint)
        resp = requests.get(url, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Extract useful fields
            entry = {'MINT': mint}
            
            # Score
            entry['rc_score'] = data.get('score', None)
            entry['rc_score_norm'] = data.get('score_normalised', data.get('score', None))
            
            # Risks
            risks = data.get('risks', [])
            entry['rc_risks_count'] = len(risks)
            if risks:
                # Sort by score desc
                sorted_risks = sorted(risks, key=lambda r: r.get('score', 0), reverse=True)
                entry['rc_top_risk'] = sorted_risks[0].get('name', '')
                entry['rc_top_risk_level'] = sorted_risks[0].get('level', '')
                entry['rc_top_risk_score'] = sorted_risks[0].get('score', 0)
                entry['rc_risk_names'] = '|'.join([r.get('name','') for r in sorted_risks[:5]])
                entry['rc_num_dangers'] = sum(1 for r in risks if r.get('level') == 'danger')
                entry['rc_num_warns'] = sum(1 for r in risks if r.get('level') == 'warn')
            
            # Token info
            entry['rc_total_market_liq'] = data.get('totalMarketLiquidity', None)
            entry['rc_total_holders'] = data.get('totalHolders', None)
            entry['rc_total_lp_providers'] = data.get('totalLpProviders', None)
            
            # Top holders
            top_holders = data.get('topHolders', [])
            if top_holders:
                entry['rc_top10_holder_pct'] = sum(h.get('pct', 0) for h in top_holders[:10])
                entry['rc_top1_holder_pct'] = top_holders[0].get('pct', 0) if top_holders else None
            
            # Authority
            entry['rc_mint_authority'] = 1 if data.get('mintAuthority') else 0
            entry['rc_freeze_authority'] = 1 if data.get('freezeAuthority') else 0
            entry['rc_mutable_metadata'] = 1 if data.get('mutableMetadata') else 0
            
            # LP info
            markets = data.get('markets', [])
            if markets:
                lp = markets[0].get('lp', {})
                entry['rc_lp_locked'] = 1 if lp.get('lpLocked', 0) > 0 else 0
                entry['rc_lp_burned'] = 1 if lp.get('lpBurned') else 0
                entry['rc_lp_lock_pct'] = lp.get('lpLockedPct', 0)
            
            # Creator
            creator = data.get('creator', '')
            if creator:
                creator_holders = [h for h in top_holders if h.get('address') == creator]
                entry['rc_creator_pct'] = creator_holders[0].get('pct', 0) if creator_holders else 0
            
            entry['rc_rugged'] = 1 if data.get('rugged') else 0
            entry['rc_token_type'] = data.get('tokenType', '')
            
            cache[mint] = entry
            success += 1
            
        elif resp.status_code == 429:
            rate_limited += 1
            if rate_limited >= 5:
                print(f"\n[{i+1}] Rate limited 5x in a row. Increasing delay to {DELAY+2}s")
                DELAY += 2
                rate_limited = 0
            cache[mint] = {'MINT': mint, '_empty': True}
            time.sleep(DELAY * 3)  # Extra wait on rate limit
            
        elif resp.status_code == 404:
            cache[mint] = {'MINT': mint, '_empty': True}
            success += 1  # Expected for some tokens
            
        else:
            cache[mint] = {'MINT': mint, '_empty': True}
            fail += 1
        
        # Progress
        if (i + 1) % 10 == 0:
            real = sum(1 for v in cache.values() if isinstance(v, dict) and not v.get('_empty'))
            print(f"[{i+1}/{len(to_enrich)}] success={success} fail={fail} rate_limited={rate_limited} cache_real={real} delay={DELAY}s")
        
        # Save periodically
        if (i + 1) % SAVE_EVERY == 0:
            with open(CACHE_PATH, 'w') as f:
                json.dump(cache, f)
        
        time.sleep(DELAY)
        
    except Exception as e:
        print(f"[{i+1}] Error for {mint[:20]}...: {e}")
        cache[mint] = {'MINT': mint, '_empty': True}
        fail += 1
        time.sleep(DELAY)

# Final save
with open(CACHE_PATH, 'w') as f:
    json.dump(cache, f)

real = sum(1 for v in cache.values() if isinstance(v, dict) and not v.get('_empty'))
print(f"\nDONE. Total cache: {len(cache)}, Real: {real}, New success: {success}, Fail: {fail}")
