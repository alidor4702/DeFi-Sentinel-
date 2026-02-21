# DeFi Sentinel

Real-time rug-pull detection for Solana. Monitors new token launches, scores risk using on-chain and social signals, alerts traders.

## Setup

```bash
cp .env.example .env
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Architecture

See [Architecture.md](Architecture.md).
