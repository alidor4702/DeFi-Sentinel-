# DeFi Sentinel

**Real-time AI-powered rug-pull detection for Solana.**

Monitors new token launches, scores risk using on-chain + market signals from 6 APIs, and alerts traders before they lose money — all powered by an XGBoost ML model trained on 116K+ liquidity pool records with **AUC 0.999**.

---

## What It Does

- **Live Token Feed** — real-time dashboard showing newly launched Solana tokens with risk scores
- **Token Scanner** — scan any Solana token by mint address for a full 77-feature risk breakdown
- **ML Risk Scoring** — XGBoost v4 model trained on the SolRPDS dataset (CODASPY 2025) with multi-source enrichment
- **On-Chain Attestations** — publish immutable risk assessments to Solana devnet via Memo transactions
- **Wallet Risk Profile** — scan all tokens in a connected Phantom wallet for rug exposure
- **SOL Payments** — buy scan credit packs by paying SOL directly from Phantom
- **Stripe Subscriptions** — Pro ($9.99/mo) and Enterprise ($99.99/mo) plans via Stripe Checkout

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + Vite 5 + Tailwind CSS + shadcn/ui |
| **Backend** | FastAPI (Python) + SQLite |
| **ML Model** | XGBoost v4 — 77 features, AUC 0.999, temporal train/test split |
| **Data Sources** | Helius DAS, RugCheck, GoPlus, GeckoTerminal, Jupiter (6 APIs) |
| **Blockchain** | Solana (devnet for attestations/payments, mainnet for data) |
| **Payments** | Stripe (subscriptions + scan packs) + SOL (scan packs) |
| **Wallet** | Phantom via `@solana/wallet-adapter` |

---

## Quick Start

### Prerequisites

- **Node.js** ≥ 18 and **npm**
- **Python** ≥ 3.10 and **pip**
- A `.env` file with API keys (see below)

### 1. Clone & Install

```bash
git clone https://github.com/alidor4702/DeFi-Sentinel-.git
cd DeFi-Sentinel-/DeFiSentinel
```

### 2. Set Up Environment Variables

Create a `.env` file in the project root:

```env
HELIUS_API_KEY=your_helius_api_key
STRIPE_SECRET_KEY=sk_test_...
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...
SOLANA_PAYER_SECRET_KEY=your_base58_keypair
```

### 3. Start the Backend

```bash
pip install -r backend/requirements.txt
PYTHONPATH=. python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at **http://localhost:5173**.

---

## How to Test

### Live Token Feed
1. Open the dashboard at `/` — you'll see ~20 live Solana tokens with risk scores refreshing every 5 minutes
2. Tokens are scored SAFE (green), MODERATE (yellow), or DANGER (red)

### Scan a Token
1. Navigate to `/scan`
2. Paste any Solana token mint address (e.g., copy one from the live feed)
3. View the full risk breakdown: ML score, verdict, risk factors, AI explanation, feature details

### Wallet Features (requires Phantom)
1. Install [Phantom Wallet](https://phantom.app/) browser extension
2. Click **Connect Wallet** in the header
3. **Wallet Risk Profile** — go to `/wallet-risk` to scan all your tokens for rug exposure
4. **On-Chain Attestation** — after scanning a token, click "Attest on Solana" to publish the result on-chain (devnet)
5. **SOL Payments** — on `/pricing`, connect your wallet to see SOL payment options for scan packs

### Stripe Payments
1. On `/pricing`, click "Subscribe with Stripe" on Pro or Enterprise
2. Use Stripe test card: `4242 4242 4242 4242` (any future expiry, any CVC)

### API Endpoints
- `GET http://localhost:8000/api/tokens` — live token list
- `GET http://localhost:8000/api/scan/{mint}` — scan a specific token
- `GET http://localhost:8000/api/model-stats` — ML model metadata

---

## Project Structure

```
DeFiSentinel/
├── backend/
│   ├── main.py              # FastAPI app — REST + WebSocket + Stripe + Solana
│   ├── ml_scorer.py         # XGBoost v4 scorer (77 features → risk score)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/           # Dashboard, ScanToken, Pricing, WalletRisk, Connect, etc.
│       ├── components/      # LivePoolMonitor, ScanResult, Header, StatCard
│       ├── hooks/           # useUserPlan (plan management)
│       └── lib/             # API client, Solana utilities
├── live_data/
│   └── collector/           # Multi-API feature collection pipeline
├── models/
│   ├── model_v4.json        # XGBoost v4 production model
│   ├── feature_list_v4.json # 77 feature names
│   └── model_meta_v4.json   # Model metrics & feature importance
├── docs/                    # Detailed documentation (see below)
├── scripts/                 # Data enrichment & training scripts
└── data/                    # SolRPDS dataset + enriched CSVs + figures
```

---

## Documentation

For detailed technical documentation, see:

| Document | Description |
|----------|-------------|
| [**docs/data-ml.md**](docs/data-ml.md) | Data pipeline, multi-source enrichment (6 APIs → 113 features), label quality audit, XGBoost v4 model training & results |
| [**docs/backend.md**](docs/backend.md) | Backend API endpoints, data flow, scoring pipeline, database, environment variables |
| [**docs/solana-features.md**](docs/solana-features.md) | Solana integration: wallet connect, on-chain attestations, SOL payments, wallet risk profile, real-time token detection |

---

## Key Numbers

| Metric | Value |
|--------|-------|
| ML Model AUC-ROC | **0.999** |
| Training Features | 77 (all live-scannable) |
| Data Sources | 6 APIs + derived features |
| Total Enriched Features | 113 (9.4× enrichment from 12 raw columns) |
| Dataset Size | 116,308 pool records, 33,358 unique mints |
| Training Split | Temporal: pre-2024 train → 2024 test |

---

## License

MIT
