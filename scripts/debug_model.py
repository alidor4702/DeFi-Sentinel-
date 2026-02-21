"""Debug: check what feature values the model sees and what it predicts."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backend.ml_scorer as ms
import numpy as np

ms._load_model()
_model = ms._model
_feature_names = ms._feature_names
_map = ms._map
print(f"Model loaded: {len(_feature_names)} features")

# 1) Test with IDEAL legit features (what USDC should look like)
ideal_legit = {
    "token_name": "USD Coin",
    "token_symbol": "USDC",
    "token_supply": 1_000_000_000,
    "token_decimals": 6,
    "gt_reserve_usd": 500_000_000,
    "gt_pool_age_hours": 24000,
    "is_mutable": False,
    "mint_authority_revoked": True,
    "freeze_authority_revoked": True,
    "has_image": True,
    "has_description": True,
    "has_website": True,
    "has_twitter": True,
    "has_telegram": True,
    "metadata_uri": "https://example.com",
    "metadata_uri_reachable": True,
    "deployer_past_tokens": 50,
    "deployer_past_rugs": 0,
    "deployer_past_rug_rate": 0.0,
    "deployer_past_labeled": 50,
    "deployer_past_is_serial": False,
    "rc_score": 900,
}

# 2) Test with OBVIOUS scam features
obvious_scam = {
    "token_name": "ELON MOON 1000X",
    "token_symbol": "SCAM",
    "token_supply": 1_000_000_000_000,
    "token_decimals": 9,
    "gt_reserve_usd": 50,
    "gt_pool_age_hours": 0.1,
    "is_mutable": True,
    "mint_authority_revoked": False,
    "freeze_authority_revoked": False,
    "has_image": False,
    "metadata_uri": None,
    "deployer_past_tokens": 20,
    "deployer_past_rugs": 18,
    "deployer_past_rug_rate": 0.9,
    "deployer_past_labeled": 20,
    "deployer_past_is_serial": True,
}

for label, features in [("IDEAL LEGIT (USDC)", ideal_legit), ("OBVIOUS SCAM", obvious_scam)]:
    mapped = _map(features)
    vec = [float(mapped.get(n, 0) or 0) for n in _feature_names]
    X = np.array([vec], dtype=np.float32)
    proba = _model.predict_proba(X)[0]
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Prediction: legit={proba[0]:.6f}  rug={proba[1]:.6f}")
    print(f"  Risk score: {round(proba[1]*100)}")
    print(f"{'='*60}")
    print(f"  Feature values:")
    for fn in _feature_names:
        v = mapped.get(fn, 0)
        print(f"    {fn:40s} = {v}")

# 3) Now check the ACTUAL raw features from a live scan
print("\n\n" + "="*60)
print("  CHECKING ACTUAL LIVE FEATURES FOR USDC")
print("="*60)
import urllib.request
try:
    # Get a cached token from the API
    resp = urllib.request.urlopen("http://localhost:8000/api/tokens", timeout=5)
    tokens = json.loads(resp.read())
    if tokens:
        mint = tokens[0]["mint"]
        print(f"  First cached token: {tokens[0]['name']} ({mint})")
except:
    print("  (Backend not reachable for live test)")
