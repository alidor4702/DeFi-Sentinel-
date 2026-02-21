# DeFi Sentinel

AI-powered real-time rug-pull detection for Solana. HackEurope 2026 hackathon project (2-person team, 48h).

## Current State

Early skeleton — architecture spec, ML training scripts, and SolRPDS dataset are in place. Backend (FastAPI) and frontend (React) are **not yet built**. See `Architecture.md` for the full build spec.

## Project Structure

```
├── Architecture.md          # Full 686-line spec (read this first)
├── train_solrpds.py         # ML training script (AdaBoost/RF on SolRPDS)
├── enrich_dataset.py        # Enriches dataset with on-chain data via Helius
├── data/
│   ├── solrpds_dataset/     # SolRPDS CSV + JSON (2021–2024, ~116K mints)
│   ├── SolRPDS_paper.pdf    # Academic paper
│   └── SolRPDS_README.md
├── backend/                 # (planned) FastAPI + PostgreSQL + Redis
├── frontend/                # (planned) React + TypeScript + Vite + Tailwind
└── live_data/               # Untracked enrichment output
```

## Commands

### ML Training
```bash
# Install deps
pip install pandas scikit-learn joblib matplotlib seaborn numpy

# Train on SolRPDS dataset
python train_solrpds.py --data_dir ./data/solrpds_dataset/CSV --out_dir ./output

# Enrich dataset with on-chain data (needs Helius API key)
python enrich_dataset.py --helius_key YOUR_KEY
python enrich_dataset.py --helius_key YOUR_KEY --sample 100  # small test
```

### Backend (planned)
```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload  # runs on :8000
```

### Frontend (planned)
```bash
cd frontend && npm install
npm run dev  # runs on :5173
```

## Architecture

**Data Ingestion** → **Risk Engine** → **Output Layer**

1. **Ingestion**: Solana WebSocket (DEX pool creation events), Helius DAS API (token metadata, holders), Twitter/X API (social signals)
2. **Risk Engine**: 5 parallel analyzers (contract, holders, liquidity, deployer history, social) → 22 features → XGBoost classifier (or rule-based fallback) → risk score 0.0–1.0
3. **Output**: REST API (FastAPI), WebSocket live feed, React dashboard, Stripe billing, Telegram bot

Risk levels: CRITICAL (>=0.8), HIGH (>=0.7), MEDIUM (>=0.4), LOW (<0.4)

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Redis, httpx
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Recharts
- **ML**: scikit-learn, XGBoost, joblib
- **Solana**: solana-py, solders, Helius DAS API
- **Payments**: Stripe (Checkout, metered billing, webhooks)
- **DB**: PostgreSQL, Redis

## Environment

Copy `.env.example` to `.env` and fill in keys. Required:
- `HELIUS_API_KEY` — free at https://dev.helius.xyz/
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
- `SOLANA_RPC_URL`, `SOLANA_WS_URL` — defaults to mainnet-beta

## Build Phases (from Architecture.md)

1. **Core Pipeline** — FastAPI + Helius client + rule-based risk engine + `/tokens/{mint}/score`
2. **Real-Time Feed** — Solana WS listener + WebSocket broadcast + PostgreSQL storage
3. **Frontend Dashboard** — React scaffold + RiskGauge + LiveFeed + TokenDetail
4. **Stripe + Polish** — Checkout, pricing page, rate limiting, seed data
5. **Extras** — ML model training, social analyzer, Telegram bot, Confidential Transfers

## Conventions

- Async everywhere in backend (async def, httpx, asyncpg)
- Structured JSON logging
- All Helius/Solana calls: 10s timeout, 3 retries with exponential backoff
- Cache token scores in Redis (5min TTL), Helius responses (1min TTL)
- API rate limiting: free tier 50/day, pro unlimited
- Dark theme UI (#0a0a0f background, #1a1a2e cards)
- Solana accent: #9945FF, Safe: #00e5a0, Danger: #ef4444, Warning: #f59e0b
