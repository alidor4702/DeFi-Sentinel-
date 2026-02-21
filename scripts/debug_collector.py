"""Debug: run collector directly and check raw features + model prediction."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.WARNING)

import backend.ml_scorer as ms
import numpy as np
ms._load_model()

from live_data.collector.orchestrator import collect_features

async def analyze(label, mint):
    print(f"\n{'='*70}")
    print(f"  {label}: {mint}")
    print(f"{'='*70}")
    
    result = await collect_features(mint)
    f = result.features
    
    print(f"  Features collected: {result.features_collected}")
    print(f"  Errors: {result.errors}")
    
    # Show the 5 deployer features (89% of model importance)
    deployer_keys = [
        "deployer_past_tokens", "deployer_past_rugs", "deployer_past_rug_rate",
        "deployer_past_labeled", "deployer_past_is_serial",
    ]
    print(f"\n  DEPLOYER features (89% of model importance):")
    for k in deployer_keys:
        v = f.get(k, "<<MISSING>>")
        print(f"    {k:35s} = {v}")
    
    # Show other key features
    other_keys = [
        "gt_reserve_usd", "rc_total_market_liquidity", "gt_pool_age_hours",
        "is_mutable", "mint_authority_revoked", "freeze_authority_revoked",
        "token_supply", "token_decimals", "token_name", "token_symbol",
        "has_image", "metadata_uri", "rc_score",
        "creator_address",
    ]
    print(f"\n  OTHER key features:")
    for k in other_keys:
        v = f.get(k, "<<MISSING>>")
        if isinstance(v, str) and len(v) > 60:
            v = v[:60] + "..."
        print(f"    {k:35s} = {v}")
    
    # Map and predict
    mapped = ms._map(f)
    vec = [float(mapped.get(n, 0) or 0) for n in ms._feature_names]
    X = np.array([vec], dtype=np.float32)
    proba = ms._model.predict_proba(X)[0]
    
    print(f"\n  >>> MODEL: legit={proba[0]:.6f}  rug={proba[1]:.6f}  risk_score={round(proba[1]*100)}")
    
    # Show what the deployer features mapped to
    print(f"\n  DEPLOYER mapped for model:")
    for fn in ms._feature_names:
        if "deployer" in fn:
            print(f"    {fn:40s} = {mapped[fn]}")
    return proba[1]

async def main():
    # Test USDC (most trusted), BONK (legit meme), and grab a fresh pump token
    scores = {}
    scores["USDC"] = await analyze("USDC (stablecoin)", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    scores["BONK"] = await analyze("BONK (legit meme)", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
    
    print(f"\n\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    for name, score in scores.items():
        print(f"  {name:10s} → rug probability: {score:.4f} ({round(score*100)}%)")

asyncio.run(main())
