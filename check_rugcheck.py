"""Quick check: what does RugCheck actually analyze?"""
import requests, json

mint = "BzJ9tPP1RuALJ9iSsasi3EMKZvC98Tx9jJZojwpFpump"  # live token from GeckoTerminal
r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", timeout=15)
d = r.json()

print("=" * 60)
print("  WHAT RUGCHECK CHECKS (live token example)")
print("=" * 60)

print(f"\n  Token: {mint}")
print(f"  Score: {d.get('score')}")
print(f"  Rugged: {d.get('rugged')}")
print(f"  Token Type: {d.get('tokenType')}")
print(f"  Deploy Platform: {d.get('deployPlatform')}")
print(f"  Launchpad: {d.get('launchpad')}")

print(f"\n--- AUTHORITY CHECKS ---")
print(f"  Mint Authority: {d.get('mintAuthority')}")
print(f"  Freeze Authority: {d.get('freezeAuthority')}")

print(f"\n--- HOLDER ANALYSIS ---")
print(f"  Total Holders: {d.get('totalHolders')}")
top = d.get("topHolders") or []
print(f"  Top Holders tracked: {len(top)}")
for h in top[:3]:
    pct = h.get("pct", 0)
    addr = h.get("address", "?")[:20]
    insider = h.get("insider", False)
    print(f"    {addr}...  {pct:.2f}%  insider={insider}")

print(f"\n--- INSIDER DETECTION ---")
print(f"  Graph Insiders Detected: {d.get('graphInsidersDetected')}")
networks = d.get("insiderNetworks") or []
print(f"  Insider Networks: {len(networks)}")

print(f"\n--- LIQUIDITY / MARKETS ---")
print(f"  Total Market Liquidity: ${d.get('totalMarketLiquidity', 0):,.2f}")
print(f"  Total Stable Liquidity: ${d.get('totalStableLiquidity', 0):,.2f}")
print(f"  Total LP Providers: {d.get('totalLPProviders')}")
markets = d.get("markets") or []
print(f"  Markets: {len(markets)}")

print(f"\n--- CREATOR ANALYSIS ---")
print(f"  Creator: {d.get('creator', '?')[:30]}...")
print(f"  Creator Balance: {d.get('creatorBalance')}")
ct = d.get("creatorTokens") or []
print(f"  Other tokens by same creator: {len(ct)}")

print(f"\n--- TRANSFER FEE ---")
print(f"  Transfer Fee: {d.get('transferFee')}")

print(f"\n--- TOKEN EXTENSIONS ---")
print(f"  Extensions: {d.get('token_extensions')}")

print(f"\n--- RISKS (the scoring rules) ---")
risks = d.get("risks") or []
print(f"  Total risks found: {len(risks)}")
for risk in risks:
    level = risk.get("level", "?")
    name = risk.get("name", "?")
    desc = risk.get("description", "")
    score = risk.get("score", 0)
    print(f"  [{level:6s}] +{score:>6,} pts | {name}")
    print(f"           {desc[:80]}")

print(f"\n--- VERIFICATION ---")
print(f"  Verification: {d.get('verification')}")

print(f"\n{'='*60}")
print(f"  SUMMARY: RugCheck is a RULE-BASED system that checks:")
print(f"  1. Mint/Freeze authority (can creator mint infinite tokens?)")
print(f"  2. Top holder concentration (do 10 wallets own 90%?)")
print(f"  3. Insider wallet graph (connected wallets buying together)")
print(f"  4. LP lock status (is liquidity locked or unlocked?)")
print(f"  5. Market liquidity depth")
print(f"  6. Creator history (other tokens by same creator)")
print(f"  7. Transfer fees (hidden tax on trades?)")
print(f"  8. Token metadata (missing = suspicious)")
print(f"  9. Token extensions (Solana Token-2022 features)")
print(f"{'='*60}")
print(f"  It does NOT use: ML, historical patterns, behavioral analysis")
print(f"  It is: static snapshot, rule-based, current state only")
print(f"{'='*60}")
