"""Quick API speed test — run each source once to measure latency."""
import time
import requests

mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC

# 1. RugCheck
t0 = time.time()
r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary")
t_rc = time.time() - t0
print(f"RugCheck:     {r.status_code} in {t_rc:.2f}s")

# 2. GeckoTerminal
t0 = time.time()
r = requests.get(f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}/pools?page=1")
t_gt = time.time() - t0
pools = r.json().get("data", []) if r.status_code == 200 else []
print(f"GeckoTerm:    {r.status_code} in {t_gt:.2f}s  (pools: {len(pools)})")

# 3. Jupiter price (supports comma-separated bulk!)
t0 = time.time()
r = requests.get(f"https://api.jup.ag/price/v2?ids={mint}")
t_jup = time.time() - t0
jup_data = r.json().get("data", {}) if r.status_code == 200 else {}
print(f"Jupiter price:{r.status_code} in {t_jup:.2f}s  (keys: {list(jup_data.keys())[:3]})")

# 4. Jupiter verified token list (ONE call = all verified tokens)
t0 = time.time()
r = requests.get("https://tokens.jup.ag/tokens?tags=verified")
t_jup2 = time.time() - t0
jup_tokens = r.json() if r.status_code == 200 else []
print(f"Jupiter list: {r.status_code} in {t_jup2:.2f}s  ({len(jup_tokens)} verified tokens)")

# 5. Jupiter ALL tokens (including unverified)
t0 = time.time()
r = requests.get("https://tokens.jup.ag/tokens_with_markets")
t_jup3 = time.time() - t0
jup_all = r.json() if r.status_code == 200 else []
print(f"Jupiter all:  {r.status_code} in {t_jup3:.2f}s  ({len(jup_all)} total tokens)")

# 6. Helius RPC (getBalance — creator wallet check)
helius_key = "2616c6b9-ead3-4367-8ef0-e642d51d7020"
creator = "3sXhnd7BRfwbM9rGKMR1WTwEZMz1QVuQdWGovqmVGJcM"
t0 = time.time()
r = requests.post(
    f"https://mainnet.helius-rpc.com/?api-key={helius_key}",
    json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [creator]},
)
t_h = time.time() - t0
print(f"Helius RPC:   {r.status_code} in {t_h:.2f}s")

# 7. Helius getSignaturesForAddress (tx count)
t0 = time.time()
r = requests.post(
    f"https://mainnet.helius-rpc.com/?api-key={helius_key}",
    json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [creator, {"limit": 1}],
    },
)
t_h2 = time.time() - t0
sigs = r.json().get("result", []) if r.status_code == 200 else []
print(f"Helius sigs:  {r.status_code} in {t_h2:.2f}s  (returned {len(sigs)} sigs)")

# Summary
print("\n=== TIME ESTIMATES (5000 tokens) ===")
print(f"RugCheck:      5000 × {t_rc:.1f}s = {5000*t_rc/60:.0f} min  (no auth, ~2 req/s safe)")
print(f"GeckoTerminal: 5000 × {t_gt:.1f}s = {5000*t_gt/60:.0f} min  (30 req/min free = 167 min)")
print(f"Jupiter price: 100 bulk calls × {t_jup:.1f}s = {100*t_jup/60:.1f} min  (batches of 50)")
print(f"Jupiter list:  1 call = {t_jup2:.1f}s  (instant lookup table)")
print(f"Helius wallet: 5000 × 3 calls × {t_h:.1f}s = {5000*3*t_h/60:.0f} min")
