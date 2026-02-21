# DeFi Sentinel 🛡️

**Real-time AI-powered rug-pull detection for Solana DeFi**

> Built at HackEurope 2026 — 48h hackathon

## What It Does

DeFi Sentinel monitors every new token launch on Solana, scores rug-pull risk using on-chain + social signals, and alerts traders before they lose money.

- 🔍 **Real-time monitoring** — WebSocket connection to Solana DEX programs (Raydium, Pump.fun, PumpSwap)
- 🧠 **ML-powered risk scoring** — 22-feature model analyzing contracts, holders, liquidity, deployer history, and social signals
- ⚡ **Instant alerts** — Live dashboard feed, REST API, and Telegram bot
- 💳 **Stripe billing** — Free tier + Pro subscription + metered API billing

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12, FastAPI, PostgreSQL, Redis |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| ML | XGBoost + rule-based fallback |
| Blockchain | Solana (solana-py, Helius DAS API) |
| Payments | Stripe Checkout + metered billing |
| Data | SolRPDS dataset (116K labeled Solana rug-pull records) |

## Quick Start

```bash
# Clone
git clone https://github.com/alidor4702/DeFi-Sentinel-.git
cd DeFi-Sentinel-

# Backend
cp .env.example .env  # Fill in your API keys
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## Dataset

Uses the [SolRPDS dataset](https://github.com/DeFiLabX/SolRPDS) — a Solana rug pull dataset derived from 3.69 billion blockchain transactions, containing 116K+ labeled liquidity pool records across 2021–2024.

## Architecture

See [Architecture.md](Architecture.md) for the full system design and build spec.

## License

MIT
