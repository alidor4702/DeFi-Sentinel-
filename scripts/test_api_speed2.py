"""Quick test: Jupiter + Helius speed."""
import time, requests

mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Jupiter price v2
t0 = time.time()
r = requests.get(f"https://api.jup.ag/price/v2?ids={mint}", headers={"Accept": "application/json"})
t_jup = time.time() - t0
print(f"Jupiter price: {r.status_code} in {t_jup:.2f}s")
if r.status_code == 200:
    d = r.json().get("data", {})
    for k, v in d.items():
        print(f"  {k}: price={v.get('price')}")

# Jupiter strict token list
t0 = time.time()
try:
    r = requests.get("https://token.jup.ag/strict", timeout=10)
    t_jup2 = time.time() - t0
    jt = r.json() if r.status_code == 200 else []
    print(f"Jupiter strict: {r.status_code} in {t_jup2:.2f}s ({len(jt)} tokens)")
except Exception as e:
    print(f"Jupiter strict: FAILED ({e})")

# Helius RPC
hk = "2616c6b9-ead3-4367-8ef0-e642d51d7020"
creator = "3sXhnd7BRfwbM9rGKMR1WTwEZMz1QVuQdWGovqmVGJcM"

t0 = time.time()
r = requests.post(
    f"https://mainnet.helius-rpc.com/?api-key={hk}",
    json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [creator]},
)
t_bal = time.time() - t0
bal = r.json().get("result", {}).get("value", 0) if r.status_code == 200 else 0
print(f"Helius balance: {r.status_code} in {t_bal:.2f}s ({bal/1e9:.4f} SOL)")

t0 = time.time()
r = requests.post(
    f"https://mainnet.helius-rpc.com/?api-key={hk}",
    json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [creator, {"limit": 1000}],
    },
)
t_sig = time.time() - t0
sigs = r.json().get("result", []) if r.status_code == 200 else []
print(f"Helius sigs:   {r.status_code} in {t_sig:.2f}s ({len(sigs)} txs)")

print("\n=== SUMMARY ===")
print(f"RugCheck:      ~0.09s/req → 5000 tokens = {5000*0.09/60:.0f} min")
print(f"GeckoTerminal: ~0.14s/req → 5000 tokens = {5000*0.14/60:.0f} min (but 30 req/min free limit → {5000/30:.0f} min)")
print(f"Jupiter price: {t_jup:.2f}s/req → batches of 100 = {50*t_jup:.0f}s total")
print(f"Helius wallet: ~{t_bal+t_sig:.2f}s for 2 calls → 5000 × {t_bal+t_sig:.1f}s = {5000*(t_bal+t_sig)/60:.0f} min")
