#!/usr/bin/env python3
"""
Test v4 model scoring with simulated real token data.
Verifies: model loads, feature mapping works, scores make sense.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ml_scorer import predict_rug_probability, get_model_meta

print("=" * 65)
print("  V4 MODEL SCORING TEST")
print("=" * 65)

# Check model loads
meta = get_model_meta()
print(f"\nModel: {meta['model_version']}")
print(f"Features: {meta['features_count']}")
print(f"AUC: {meta['metrics']['auc_roc']}")

# ═══════════════════════════════════════════════════════════════════
# Test tokens — simulate live collector output
# ═══════════════════════════════════════════════════════════════════

test_cases = [
    # ── USDC: major stablecoin, should be very low risk ──
    {
        "name": "USDC (stablecoin)",
        "expected": "SAFE (<30)",
        "features": {
            "token_name": "USD Coin",
            "token_symbol": "USDC",
            "token_decimals": 6,
            "token_supply": 30_000_000_000,
            "mint_authority_revoked": False,  # USDC keeps mint authority
            "freeze_authority_revoked": False,
            "is_mutable": False,
            "metadata_uri": "https://arweave.net/usdc",
            "has_image": True,
            "has_description": True,
            "has_website": True,
            "has_twitter": True,
            "has_telegram": False,
            "metadata_uri_reachable": True,
            # RugCheck
            "rc_score": 950,
            "rc_risk_count": 0,
            "rc_top_holder_pct": 8.5,
            "rc_top10_holder_pct": 35.0,
            "rc_total_market_liquidity": 500_000_000,
            "rc_mint_authority_disabled": False,
            "rc_freeze_authority_disabled": False,
            "rc_mutable_metadata": False,
            "rc_lp_locked": True,
            "rc_lp_burned": False,
            "rc_lp_lock_pct": 95.0,
            "rc_num_markets": 50,
            # GeckoTerminal
            "gt_pool_count": 20,
            "gt_reserve_usd": 500_000_000,
            "gt_pool_age_hours": 20_000,
            "gt_volume_24h": 50_000_000,
            "gt_price_change_24h": -0.01,
            # Jupiter
            "jup_listed": True,
            "jup_strict_list": True,
            "jup_daily_volume": 100_000_000,
        },
    },
    # ── BONK: established memecoin, should be safe ──
    {
        "name": "BONK (memecoin)",
        "expected": "SAFE (<35)",
        "features": {
            "token_name": "Bonk",
            "token_symbol": "BONK",
            "token_decimals": 5,
            "token_supply": 93_526_613_000_000,
            "mint_authority_revoked": True,
            "freeze_authority_revoked": True,
            "is_mutable": False,
            "metadata_uri": "https://arweave.net/bonk",
            "has_image": True,
            "has_description": True,
            "has_website": True,
            "has_twitter": True,
            "has_telegram": True,
            "metadata_uri_reachable": True,
            "rc_score": 870,
            "rc_risk_count": 1,
            "rc_top_holder_pct": 5.0,
            "rc_top10_holder_pct": 20.0,
            "rc_total_market_liquidity": 15_000_000,
            "rc_mint_authority_disabled": True,
            "rc_freeze_authority_disabled": True,
            "rc_mutable_metadata": False,
            "rc_lp_locked": True,
            "rc_lp_burned": True,
            "rc_lp_lock_pct": 100.0,
            "gt_pool_count": 10,
            "gt_reserve_usd": 15_000_000,
            "gt_pool_age_hours": 12_000,
            "gt_volume_24h": 5_000_000,
            "gt_price_change_24h": 3.5,
            "jup_listed": True,
            "jup_strict_list": True,
            "jup_daily_volume": 8_000_000,
        },
    },
    # ── Fresh pump.fun scam token ──
    {
        "name": "ELONSAFE100X (obvious scam)",
        "expected": "DANGER (>70)",
        "features": {
            "token_name": "$ELONSAFE100X 🚀🌙",
            "token_symbol": "ELON100X",
            "token_decimals": 9,
            "token_supply": 1_000_000_000,
            "mint_authority_revoked": False,
            "freeze_authority_revoked": False,
            "is_mutable": True,
            "metadata_uri": None,
            "has_image": False,
            "has_description": False,
            "has_website": False,
            "has_twitter": False,
            "has_telegram": False,
            "metadata_uri_reachable": False,
            "gt_pool_count": 1,
            "gt_reserve_usd": 200,
            "gt_pool_age_hours": 0.5,
            "gt_volume_24h": 50,
            "gt_price_change_24h": -85.0,
            "jup_listed": False,
            "jup_strict_list": False,
            # RugCheck not available yet (too fresh)
            "creator_wallet_age_hours": 2,
            "creator_tx_count": 3,
        },
    },
    # ── Moderate risk: new but not obviously scammy ──
    {
        "name": "NewCoin (moderate risk)",
        "expected": "WARNING (40-65)",
        "features": {
            "token_name": "NewCoin Finance",
            "token_symbol": "NCF",
            "token_decimals": 9,
            "token_supply": 100_000_000,
            "mint_authority_revoked": True,
            "freeze_authority_revoked": True,
            "is_mutable": False,
            "metadata_uri": "https://newcoin.io/meta.json",
            "has_image": True,
            "has_description": True,
            "has_website": True,
            "has_twitter": False,
            "has_telegram": False,
            "metadata_uri_reachable": True,
            "gt_pool_count": 1,
            "gt_reserve_usd": 5_000,
            "gt_pool_age_hours": 48,
            "gt_volume_24h": 2_000,
            "gt_price_change_24h": -5.0,
            "rc_score": 500,
            "rc_risk_count": 3,
            "rc_top_holder_pct": 30.0,
            "rc_top10_holder_pct": 55.0,
            "rc_total_market_liquidity": 5000,
            "rc_mint_authority_disabled": True,
            "rc_freeze_authority_disabled": True,
            "rc_mutable_metadata": False,
            "rc_lp_locked": False,
            "rc_lp_burned": False,
            "rc_lp_lock_pct": 0,
        },
    },
    # ── Minimal data (only Helius, no RC/GT) ──
    {
        "name": "Unknown Token (minimal data)",
        "expected": "HIGH RISK (60-80)",
        "features": {
            "token_name": "",
            "token_symbol": "",
            "token_decimals": 9,
            "token_supply": 1_000_000_000_000,
            "mint_authority_revoked": False,
            "freeze_authority_revoked": False,
            "is_mutable": True,
            "metadata_uri": None,
            "has_image": False,
            "metadata_uri_reachable": False,
        },
    },
]

print(f"\n{'Token':<35s} {'Score':>5s}  {'Expected':<20s}  {'Status'}")
print("-" * 80)

for tc in test_cases:
    prob, score = predict_rug_probability(tc["features"])
    
    # Determine label
    if score <= 30:
        label = "SAFE"
    elif score <= 50:
        label = "CAUTION"
    elif score <= 70:
        label = "WARNING"
    else:
        label = "DANGER"
    
    print(f"  {tc['name']:<33s} {score:>3d}%  {tc['expected']:<20s}  {label}")

print(f"\n{'=' * 65}")
print(f"  v4 scoring test complete!")
print(f"{'=' * 65}")
