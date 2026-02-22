# Backend Architecture

> FastAPI backend powering DeFi Sentinel's real-time rug-pull detection.

---

## Overview

The backend is a **FastAPI** application (`backend/main.py`) that:

1. **Collects** live on-chain and market data from 6 APIs
2. **Scores** tokens using an XGBoost v4 ML model (77 features, AUC 0.999)
3. **Serves** a REST API + WebSocket feed to the React frontend
4. **Manages** Stripe subscriptions, SOL payments, scan credits, and on-chain attestations
5. **Listens** to Solana mainnet via WebSocket for real-time new token detection

**Start command:**
```bash
cd DeFiSentinel
PYTHONPATH=. python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## API Endpoints

### Token Scanning

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/scan/{mint}` | Scan a single token — collects features from 6 APIs, runs ML model, returns full risk breakdown |
| `GET` | `/api/tokens` | Returns cached list of ~20 live tokens for the dashboard feed |
| `POST` | `/api/tokens/refresh` | Triggers a background cache refresh and returns current tokens |
| `GET` | `/api/tokens/filter` | Filter cached tokens by `max_risk`, `min_liq`, `sort`, `limit` |

### Real-time Feed

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WS` | `/ws` | WebSocket — pushes new token discoveries and cache updates in real-time |

### ML Model

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/model-stats` | Returns ML model metadata: version, feature count, AUC, top features |

### Payments & Billing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/create-checkout` | Creates a Stripe Checkout session for plan subscriptions or scan packs |
| `POST` | `/api/verify-solana-payment` | Verifies a SOL payment on-chain and credits scans to the wallet |
| `GET` | `/api/credits/{wallet}` | Returns total scan credits for a wallet address |
| `GET` | `/api/payer-address` | Returns the treasury wallet address + SOL prices for scan packs |

### Solana & Attestations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/attest` | Creates an on-chain risk attestation via Solana's Memo program |
| `GET` | `/api/attestations` | Lists all attestation records (optionally filtered by `?wallet=`) |
| `GET` | `/api/attestations/{mint}` | Lists attestations for a specific token mint |
| `POST` | `/api/auth/wallet` | Verifies a Phantom wallet signature for authentication |

### Wallet Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/wallet/{address}/balance/{mint}` | Checks if a wallet holds a specific SPL token |
| `GET` | `/api/wallet/{address}/risk-profile` | Scans ALL tokens in a wallet, scores each for rug risk, returns portfolio-level metrics |

---

## Data Flow: Token Scan

When `/api/scan/{mint}` is called:

```
1. collect_features(mint)     ← live_data/collector pipeline
   ├── Helius DAS API         → token metadata, authorities, supply
   ├── RugCheck API           → risk score, LP lock, holder concentration
   ├── GoPlus Security API    → holder %, TVL, honeypot detection
   ├── GeckoTerminal API      → price, volume, pool liquidity
   ├── Jupiter API            → listing status (strict-list check)
   └── Derived features       → metadata completeness, authority risk

2. predict_rug_probability(features)   ← ml_scorer.py
   ├── _map_v4()              → maps 6-API features to 77 model columns
   ├── XGBoost predict        → raw rug probability (0.0 – 1.0)
   ├── Heuristic adjustment   → boost/penalty for strong live signals
   └── Established-token cap  → $1M+ / 30d+ tokens capped at risk ≤25

3. _map_scan_result(result)   → frontend-shaped JSON response
   ├── Risk score (0–100)
   ├── Verdict (SAFE / MODERATE / DANGER)
   ├── ML confidence %
   ├── Risk factors (human-readable explanations)
   ├── AI analysis narrative
   ├── Feature breakdown (all collected features)
   └── API source statuses
```

---

## Data Flow: Live Token Feed

The dashboard token feed uses two data sources:

### 1. Background Refresh Loop (every 5 minutes)
- Fetches trending tokens from GeckoTerminal and new Raydium/pump.fun pools
- Scans up to 25 tokens concurrently (semaphore-limited to 2 at a time)
- Caches results in memory, sorted: SAFE first, then MODERATE, then DANGER
- Broadcasts updates to all WebSocket clients

### 2. Solana WebSocket Listener (real-time)
- Connects to Helius mainnet WebSocket
- Subscribes to `logsSubscribe` for the Token Program
- Detects `InitializeMint` instructions → resolves new token mint addresses
- Immediately scans new tokens and pushes to the live feed via WebSocket

---

## Scoring Pipeline

The ML scorer (`backend/ml_scorer.py`) implements:

1. **Feature mapping (`_map_v4`)** — Maps collector output to 77 XGBoost input features, using `np.nan` for missing data
2. **XGBoost prediction** — Native NaN handling routes missing features through learned optimal splits
3. **Heuristic adjustments:**
   - RugCheck score < 300 → risk boost
   - Jupiter strict-list → risk reduction
   - 24h volume > $100K → risk reduction
   - Fresh creator wallet (< 24h) → risk boost
4. **Established-token cap** — Tokens with $1M+ liquidity and 30d+ pool age capped at max risk 25
5. **Fallback** — If XGBoost model fails to load, uses enhanced heuristic scoring

---

## Database

SQLite (`defi_sentinel.db`) stores:

| Table | Purpose |
|-------|---------|
| `attestations` | On-chain risk attestation records (tx signature, risk score, wallet, mint) |
| `payments` | SOL payment records and scan credit balances per wallet |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HELIUS_API_KEY` | Yes | Helius API key for DAS + RPC calls |
| `STRIPE_SECRET_KEY` | Yes | Stripe test/live secret key |
| `SOLANA_PAYER_SECRET_KEY` | Yes | Base58-encoded keypair for attestation transactions |

---

## Dependencies

Key Python packages (`backend/requirements.txt`):
- `fastapi` + `uvicorn` — async web framework
- `httpx` — async HTTP client for API calls
- `xgboost` — ML model inference
- `numpy` — feature array construction
- `stripe` — payment processing
- `solders` + `solana` — Solana transaction building
- `python-dotenv` — environment variable loading
- `websockets` — Solana WebSocket listener
