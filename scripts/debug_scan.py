"""Debug: scan a token through the collector and dump raw features + model input."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.ml_scorer as ms
import numpy as np
ms._load_model()

from live_data.collector.scanner import scan_token

async def main():
    mints = {
        "USDC":  "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "BONK":  "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        # Also a random new pump.fun token from the cache
    }
    
    # Also grab a new token from the API
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/tokens", timeout=5)
        tokens = json.loads(resp.read())
        if tokens:
            mints[tokens[0]["symbol"]] = tokens[0]["mint"]
    except:
        pass
    
    for label, mint in mints.items():
        print(f"\n{'='*70}")
        print(f"  SCANNING: {label} ({mint})")
        print(f"{'='*70}")
        
        result = await scan_token(mint)
        f = result.features
        
        print(f"  Collector returned {len(f)} features, {len(result.errors)} errors")
        if result.errors:
            print(f"  Errors: {result.errors[:3]}")
        
        # KEY features
        key = [
            "deployer_past_tokens", "deployer_past_rugs", "deployer_past_rug_rate",
            "deployer_past_labeled", "deployer_past_is_serial",
            "gt_reserve_usd", "rc_total_market_liquidity", "gt_pool_age_hours",
            "is_mutable", "mint_authority_revoked", "freeze_authority_revoked",
            "token_supply", "token_decimals", "has_image", "metadata_uri",
            "rc_score",
        ]
        
        print(f"\n  KEY RAW FEATURES from collector:")
        for k in key:
            v = f.get(k, "<<MISSING>>")
            print(f"    {k:35s} = {v}")
        
        # Map and predict
        mapped = ms._map(f)
        vec = [float(mapped.get(n, 0) or 0) for n in ms._feature_names]
        X = np.array([vec], dtype=np.float32)
        proba = ms._model.predict_proba(X)[0]
        
        print(f"\n  MODEL PREDICTION: legit={proba[0]:.6f}  rug={proba[1]:.6f}  risk={round(proba[1]*100)}")
        
        # Show deployer features
        print(f"\n  DEPLOYER mapped values:")
        for fn in ms._feature_names:
            if "deployer" in fn:
                print(f"    {fn:40s} = {mapped[fn]}")

asyncio.run(main())
