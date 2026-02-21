#!/usr/bin/env python3
"""Audit: which model features are dead vs alive in production."""
import json, pathlib
import xgboost as xgb
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

model = xgb.XGBClassifier()
model.load_model(str(ROOT / "models/model_v3.json"))
features = json.load(open(ROOT / "models/feature_list_v3.json"))
raw_imps = model.feature_importances_
importances = {features[i]: float(raw_imps[i]) for i in range(len(features))}

# Features that are ALWAYS hardcoded/dummy in live mode
DEAD = {
    "feat_deployer_past_labeled", "feat_deployer_past_tokens",
    "feat_deployer_past_is_serial", "feat_deployer_past_rug_rate",
    "feat_deployer_past_rugs",
    "feat_name_frequency", "feat_symbol_frequency",
    "derived_uri_domain_rug_rate", "derived_token_std_rug_rate",
    "ROYALTY_PCT", "NUM_CREATORS", "CREATOR_VERIFIED",
    "NUM_LIQUIDITY_ADDS",
}

dead_pct = sum(importances.get(f, 0) for f in DEAD) * 100
live_pct = sum(v for k, v in importances.items() if k not in DEAD) * 100

print("=" * 70)
print("  MODEL FEATURE AUDIT — What's Dead vs Alive in Production")
print("=" * 70)
print(f"\n  ❌ DEAD features total:  {dead_pct:.1f}%")
print(f"  ✅ LIVE features total:  {live_pct:.1f}%")
print(f"\n  The model is {dead_pct:.0f}% blind in production.\n")

print(f"  {'Status':<6s}  {'Import':>7s}  Feature")
print(f"  {'-'*6}  {'-'*7}  {'-'*45}")
for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
    tag = "❌ DEAD" if feat in DEAD else "✅ live"
    if imp * 100 < 0.05:
        break
    tag = "❌ DEAD" if feat in DEAD else "✅ live"
    print(f"  {tag}  {imp*100:6.2f}%  {feat}")

# What we CAN get but DON'T — features not in the model at all
print("\n" + "=" * 70)
print("  SIGNALS WE *CAN* GET LIVE BUT MODEL DOESN'T USE")
print("=" * 70)
available_not_used = [
    ("rc_score (0-1000)",          "RugCheck risk score — already in heuristic, not in ML"),
    ("rc_top10_holder_pct",        "Top 10 holder concentration — from RugCheck"),
    ("rc_lp_locked_pct",           "% of LP tokens locked — from RugCheck"),
    ("gt_volume_24h",              "24h trading volume — from GeckoTerminal"),
    ("gt_buy_count_24h",           "Buy transactions 24h — from GeckoTerminal"),
    ("gt_sell_count_24h",          "Sell transactions 24h — from GeckoTerminal"),
    ("gt_price_change_1h/6h/24h",  "Price momentum — from GeckoTerminal"),
    ("gt_fdv_usd",                 "Fully diluted valuation — from GeckoTerminal"),
    ("creator_sol_balance",        "Deployer SOL balance — from Helius"),
    ("creator_wallet_age_hours",   "How old is deployer wallet — from Helius"),
    ("creator_tx_count",           "Deployer total transactions — from Helius"),
    ("creator_token_count",        "Deployer total token interactions — from Helius"),
    ("jup_strict_list",            "Jupiter verified/strict listing — from Jupiter"),
    ("jup_daily_volume",           "Jupiter daily volume — from Jupiter"),
    ("freeze_authority_active",    "Can token be frozen — from Helius"),
    ("GoPlus honeypot detection",  "Is it a honeypot — NOT IMPLEMENTED"),
    ("GoPlus buy/sell tax",        "Hidden taxes — NOT IMPLEMENTED"),
    ("GoPlus holder count",        "Total unique holders — NOT IMPLEMENTED"),
    ("Social link verification",   "Are twitter/telegram/website real — NOT IMPLEMENTED"),
]
for feat, desc in available_not_used:
    print(f"  🔵 {feat:<30s}  {desc}")
