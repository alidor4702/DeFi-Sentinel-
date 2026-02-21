"""Audit: which of the 82 live-inference features exist in enriched_final.csv"""
import pandas as pd

df = pd.read_csv("data/enriched/enriched_final.csv", nrows=5)
cols = set(df.columns)

# Spec → existing column mapping
spec = {
    # ── Helius (21) ──
    "token_name": ["TOKEN_NAME"],
    "token_symbol": ["TOKEN_SYMBOL"],
    "token_decimals": ["TOKEN_DECIMALS"],
    "token_supply": ["TOKEN_SUPPLY"],
    "mint_authority": ["MINT_AUTHORITY"],
    "mint_authority_revoked": ["MINT_AUTHORITY_ACTIVE"],
    "freeze_authority": ["FREEZE_AUTHORITY"],
    "freeze_authority_revoked": ["FREEZE_AUTHORITY_ACTIVE"],
    "update_authority": [],
    "is_mutable": ["IS_MUTABLE"],
    "token_standard": ["TOKEN_STANDARD"],
    "token_program": ["TOKEN_PROGRAM"],
    "creation_timestamp": [],
    "metadata_uri": ["HAS_JSON_URI"],
    "metadata_uri_reachable": [],
    "has_image": ["HAS_IMAGE"],
    "has_description": [],
    "has_website": [],
    "has_twitter": [],
    "has_telegram": [],
    "creator_address": ["OWNER"],
    # ── Creator Wallet (6) ──
    "creator_sol_balance": [],
    "creator_wallet_age_hours": [],
    "creator_token_count": [],
    "creator_tx_count": [],
    "creator_prev_tokens_rugged": [],
    "creator_nft_count": [],
    # ── RugCheck (18) ──
    "rc_score": ["RC_SCORE", "rc_score"],
    "rc_risk_level": ["rc_top_risk_level"],
    "rc_risk_count": ["RC_NUM_RISKS", "rc_risks_count"],
    "rc_mint_authority_disabled": ["RC_MINT_AUTHORITY", "rc_mint_authority"],
    "rc_freeze_authority_disabled": ["RC_FREEZE_AUTHORITY", "rc_freeze_authority"],
    "rc_mutable_metadata": [],
    "rc_top10_holder_pct": ["rc_top_holders_pct"],
    "rc_top_holder_pct": ["RC_TOP_HOLDER_PCT"],
    "rc_lp_locked": [],
    "rc_lp_lock_pct": [],
    "rc_lp_lock_duration_days": [],
    "rc_lp_burned": [],
    "rc_single_holder_ownership": [],
    "rc_high_concentration": [],
    "rc_low_liquidity": [],
    "rc_copycat_token": [],
    "rc_total_market_liquidity": ["RC_TOTAL_MARKET_LIQ", "rc_total_market_liq"],
    "rc_num_markets": [],
    # ── GeckoTerminal (25) ──
    "gt_pool_count": ["gt_pool_count"],
    "gt_pool_address": [],
    "gt_pool_name": ["gt_pool_name"],
    "gt_dex": ["gt_pool_dex"],
    "gt_base_token_price_usd": ["gt_base_price_usd"],
    "gt_quote_token_price_usd": [],
    "gt_fdv_usd": ["gt_fdv_usd"],
    "gt_market_cap_usd": ["gt_market_cap_usd"],
    "gt_reserve_usd": ["gt_reserve_usd"],
    "gt_volume_5m": [],
    "gt_volume_1h": ["gt_vol_1h"],
    "gt_volume_6h": ["gt_vol_6h"],
    "gt_volume_24h": ["gt_vol_24h"],
    "gt_price_change_5m": ["gt_price_pct_5m"],
    "gt_price_change_1h": ["gt_price_pct_1h"],
    "gt_price_change_6h": [],
    "gt_price_change_24h": ["gt_price_pct_24h"],
    "gt_tx_count_5m_buys": [],
    "gt_tx_count_5m_sells": [],
    "gt_tx_count_1h_buys": [],
    "gt_tx_count_1h_sells": [],
    "gt_tx_count_24h_buys": ["gt_txns_24h_buys"],
    "gt_tx_count_24h_sells": ["gt_txns_24h_sells"],
    "gt_buy_sell_ratio_1h": [],
    "gt_pool_age_hours": ["gt_pool_created"],
    # ── Jupiter (5) ──
    "jup_listed": [],
    "jup_strict_list": [],
    "jup_daily_volume": [],
    "jup_price_usd": [],
    "jup_tags": [],
    # ── Derived (7) ──
    "liquidity_to_fdv_ratio": [],
    "sell_pressure_score": [],
    "metadata_completeness": [],
    "authority_risk_score": [],
    "wallet_freshness_flag": [],
    "consensus_risk": [],
    "price_liquidity_divergence": [],
}

covered, missing_feats = [], []
for feat, matches in spec.items():
    found = [c for c in matches if c in cols]
    if found:
        covered.append((feat, found))
    else:
        missing_feats.append(feat)

print(f"=== COVERAGE: {len(covered)}/82 features present  |  {len(missing_feats)}/82 missing ===\n")

# Group missing by source
groups = {
    "Helius": [f for f in missing_feats if spec.keys().__iter__().__class__ and f in list(spec.keys())[:21]],
    "Creator Wallet": [f for f in missing_feats if f.startswith("creator_")],
    "RugCheck": [f for f in missing_feats if f.startswith("rc_")],
    "GeckoTerminal": [f for f in missing_feats if f.startswith("gt_")],
    "Jupiter": [f for f in missing_feats if f.startswith("jup_")],
    "Derived": [f for f in missing_feats if f in ["liquidity_to_fdv_ratio","sell_pressure_score","metadata_completeness","authority_risk_score","wallet_freshness_flag","consensus_risk","price_liquidity_divergence"]],
}
helius_missing = ["update_authority","creation_timestamp","metadata_uri_reachable","has_description","has_website","has_twitter","has_telegram"]
groups["Helius"] = [f for f in helius_missing if f in missing_feats]

print("── COVERED ──")
for f, c in covered:
    print(f"  ✅ {f:35s} → {c}")

print("\n── MISSING (by source) ──")
for src, feats in groups.items():
    if feats:
        print(f"\n  {src} ({len(feats)} missing):")
        for f in feats:
            print(f"    ❌ {f}")

# Also check fill rates for covered features
print("\n── FILL RATES (non-null %) for covered features ──")
df_full = pd.read_csv("data/enriched/enriched_final.csv")
total = len(df_full)
for feat, matched_cols in covered:
    col = matched_cols[0]
    non_null = df_full[col].notna().sum()
    pct = 100 * non_null / total
    marker = "⚠️" if pct < 20 else ""
    print(f"  {feat:35s} ({col:30s}): {pct:5.1f}% filled  {marker}")
