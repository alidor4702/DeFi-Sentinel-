"""Debug: check ACTUAL raw features from the live collector for cached tokens."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backend.ml_scorer as ms
import numpy as np

ms._load_model()

# Now let's look at what the collector actually gives us
# We need to import the cache and see raw features
from backend.main import _token_cache

print(f"Cached tokens: {len(_token_cache)}")
if not _token_cache:
    print("No tokens cached — run backend first")
    sys.exit(1)

for mint, result in list(_token_cache.items())[:3]:
    f = result.features
    print(f"\n{'='*70}")
    print(f"  TOKEN: {f.get('token_name', '?')} ({f.get('token_symbol', '?')})")
    print(f"  MINT:  {mint}")
    print(f"  Total raw features: {len(f)}")
    print(f"{'='*70}")
    
    # Show the KEY features the model cares about
    key_features = [
        "deployer_past_tokens", "deployer_past_rugs", "deployer_past_rug_rate",
        "deployer_past_labeled", "deployer_past_is_serial",
        "gt_reserve_usd", "rc_total_market_liquidity", "gt_pool_age_hours",
        "is_mutable", "mint_authority_revoked", "freeze_authority_revoked",
        "token_supply", "token_decimals", "has_image", "metadata_uri",
        "metadata_uri_reachable", "has_description", "has_website", "has_twitter",
        "has_telegram", "rc_score", "rc_top_holder_pct",
    ]
    
    print("\n  KEY RAW FEATURES:")
    for k in key_features:
        v = f.get(k, "<<MISSING>>")
        print(f"    {k:35s} = {v}")
    
    # Now map and predict
    mapped = ms._map(f)
    vec = [float(mapped.get(n, 0) or 0) for n in ms._feature_names]
    X = np.array([vec], dtype=np.float32)
    proba = ms._model.predict_proba(X)[0]
    
    print(f"\n  MAPPED → MODEL PREDICTION: legit={proba[0]:.4f}  rug={proba[1]:.4f}  risk={round(proba[1]*100)}")
    
    # Show the deployer features specifically (most important)
    print(f"\n  DEPLOYER features mapped:")
    for fn in ms._feature_names:
        if "deployer" in fn:
            print(f"    {fn:40s} = {mapped.get(fn, 0)}")
