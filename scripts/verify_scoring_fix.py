"""
Verify the blended scoring fix for the all-100% bug.
Tests with simulated collector outputs for various token types.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.ml_scorer import (
    predict_rug_probability,
    _heuristic_fallback,
    _deployer_data_available,
    _established_cap,
    _load_model,
    _map,
    _NEUTRAL_DEPLOYER,
)

_load_model()

# ── Test 1: USDC-like (established stablecoin, no deployer data) ──
usdc_features = {
    "token_name": "USD Coin",
    "token_symbol": "USDC",
    "token_supply": 1_000_000_000,
    "token_decimals": 6,
    "gt_reserve_usd": 27_918_581,
    "gt_pool_age_hours": 23095,
    "gt_volume_24h": 5_000_000,
    "rc_score": 0,
    "mint_authority_revoked": False,
    "freeze_authority_revoked": False,
    "is_mutable": False,
    "has_image": True,
    "has_description": True,
    "has_website": True,
    "has_twitter": True,
    "has_telegram": False,
    "metadata_uri": "https://arweave.net/...",
    "rc_top_holder_pct": 8,
    "jup_verified": True,
    "jup_daily_volume": 500_000,
    # deployer data = all zeros (unavailable)
    "deployer_past_tokens": 0,
    "deployer_past_rugs": 0,
    "deployer_past_rug_rate": 0.0,
    "deployer_past_labeled": 0,
    "deployer_past_is_serial": False,
}

# ── Test 2: BONK-like (established meme, no deployer data) ──
bonk_features = {
    "token_name": "Bonk",
    "token_symbol": "BONK",
    "token_supply": 93_526_183_000_000,
    "token_decimals": 5,
    "gt_reserve_usd": 3_500_000,
    "gt_pool_age_hours": 15000,
    "gt_volume_24h": 800_000,
    "rc_score": 100,
    "mint_authority_revoked": True,
    "freeze_authority_revoked": True,
    "is_mutable": False,
    "has_image": True,
    "has_description": True,
    "has_website": True,
    "has_twitter": True,
    "has_telegram": True,
    "metadata_uri": "https://arweave.net/...",
    "rc_top_holder_pct": 12,
    "jup_verified": True,
    "jup_daily_volume": 200_000,
    "deployer_past_tokens": 0,
    "deployer_past_rugs": 0,
    "deployer_past_rug_rate": 0.0,
    "deployer_past_labeled": 0,
    "deployer_past_is_serial": False,
}

# ── Test 3: Fresh pump.fun scam (no deployer data) ──
scam_features = {
    "token_name": "ELON MOON 100X",
    "token_symbol": "ELONMOON",
    "token_supply": 1_000_000_000,
    "token_decimals": 9,
    "gt_reserve_usd": 800,
    "gt_pool_age_hours": 0.3,
    "gt_volume_24h": 50,
    "rc_score": 800,
    "mint_authority_revoked": False,
    "freeze_authority_revoked": False,
    "is_mutable": True,
    "has_image": False,
    "has_description": False,
    "has_website": False,
    "has_twitter": False,
    "has_telegram": False,
    "metadata_uri": "",
    "rc_top_holder_pct": 85,
    "jup_verified": False,
    "jup_daily_volume": 0,
    "deployer_past_tokens": 0,
    "deployer_past_rugs": 0,
    "deployer_past_rug_rate": 0.0,
    "deployer_past_labeled": 0,
    "deployer_past_is_serial": False,
}

# ── Test 4: Scam WITH deployer data (serial rugger) ──
serial_rugger = {
    **scam_features,
    "deployer_past_tokens": 20,
    "deployer_past_rugs": 18,
    "deployer_past_rug_rate": 0.9,
    "deployer_past_labeled": 20,
    "deployer_past_is_serial": True,
}

# ── Test 5: New legit token (no deployer data, decent signals) ──
new_legit = {
    "token_name": "SomeProtocol",
    "token_symbol": "SPRO",
    "token_supply": 100_000_000,
    "token_decimals": 9,
    "gt_reserve_usd": 50_000,
    "gt_pool_age_hours": 72,
    "gt_volume_24h": 15_000,
    "rc_score": 200,
    "mint_authority_revoked": True,
    "freeze_authority_revoked": True,
    "is_mutable": False,
    "has_image": True,
    "has_description": True,
    "has_website": True,
    "has_twitter": True,
    "has_telegram": False,
    "metadata_uri": "https://arweave.net/...",
    "rc_top_holder_pct": 22,
    "jup_verified": False,
    "jup_daily_volume": 10_000,
    "deployer_past_tokens": 0,
    "deployer_past_rugs": 0,
    "deployer_past_rug_rate": 0.0,
    "deployer_past_labeled": 0,
    "deployer_past_is_serial": False,
}

# ── Test 6: USDC with REAL deployer data (ideal case) ──
usdc_with_deployer = {
    **usdc_features,
    "deployer_past_tokens": 50,
    "deployer_past_rugs": 0,
    "deployer_past_rug_rate": 0.0,
    "deployer_past_labeled": 50,
    "deployer_past_is_serial": False,
}

# ── Test 7: WIF-like (established meme, deployer has sketchy history) ──
wif_features = {
    "token_name": "dogwifhat",
    "token_symbol": "$WIF",
    "token_supply": 998_926_392,
    "token_decimals": 6,
    "gt_reserve_usd": 5_260_000,
    "gt_pool_age_hours": 824 * 24,  # ~824 days
    "gt_volume_24h": 200_000,
    "rc_score": 500,
    "mint_authority_revoked": False,
    "freeze_authority_revoked": True,
    "is_mutable": True,
    "has_image": True,
    "has_description": True,
    "has_website": True,
    "has_twitter": True,
    "has_telegram": False,
    "metadata_uri": "https://ipfs.io/...",
    "rc_top_holder_pct": 10,
    "jup_verified": True,
    "jup_daily_volume": 200_000,
    # Deployer HAS data — but sketchy (pump.fun creator with past rugs)
    "deployer_past_tokens": 4,
    "deployer_past_rugs": 3,
    "deployer_past_rug_rate": 0.75,
    "deployer_past_labeled": 4,
    "deployer_past_is_serial": True,
}

print("=" * 70)
print("  SCORING FIX VERIFICATION")
print("=" * 70)

tests = [
    ("USDC (no deployer data)", usdc_features, "LEGIT (< 30)"),
    ("BONK (no deployer data)", bonk_features, "LEGIT (< 30)"),
    ("SCAM (no deployer data)", scam_features, "DANGER (> 60)"),
    ("SERIAL RUGGER (deployer data)", serial_rugger, "DANGER (> 80)"),
    ("New legit project (no deployer)", new_legit, "MODERATE (20-50)"),
    ("USDC (WITH deployer data)", usdc_with_deployer, "LEGIT (< 30)"),
    ("WIF (established, sketchy deployer)", wif_features, "LEGIT (< 30)"),
]

all_pass = True
for label, features, expected in tests:
    has_dep = _deployer_data_available(features)
    h_prob, h_score = _heuristic_fallback(features)
    prob, score = predict_rug_probability(features)

    if score <= 30:
        verdict = "LEGIT"
    elif score <= 60:
        verdict = "MODERATE"
    else:
        verdict = "DANGER"

    print(f"\n  {label}")
    print(f"    Deployer data: {'YES' if has_dep else 'NO (blended)'}")
    print(f"    Heuristic: {h_score}")
    print(f"    Final:     risk={score}  ({verdict})")
    print(f"    Expected:  {expected}")

    # Sanity checks
    ok = True
    if "LEGIT" in expected and score > 35:
        ok = False
    if "DANGER" in expected and "60" in expected and score < 55:
        ok = False
    if "DANGER" in expected and "80" in expected and score < 70:
        ok = False
    if not ok:
        print(f"    ❌ UNEXPECTED SCORE!")
        all_pass = False
    else:
        print(f"    ✅ OK")

print("\n" + "=" * 70)
if all_pass:
    print("  ALL TESTS PASSED ✅")
else:
    print("  SOME TESTS FAILED ❌ — review above")
print("=" * 70)
