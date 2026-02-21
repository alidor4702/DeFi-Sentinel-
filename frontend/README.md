# DeFi Sentinel — Frontend

AI-powered real-time rug-pull detection for Solana meme tokens. Built for HackEurope 2026.

## Tech Stack

- React 18 + TypeScript
- Vite (dev server & build)
- Tailwind CSS + shadcn/ui
- FastAPI backend (`../backend/`)
- Live data collector (`../live_data/collector/`)

## Features

- **Scan any token** — paste a Solana mint address, get an instant risk breakdown with AI analysis
- **Live Pool Monitor** — auto-discovers newly launched pools from GeckoTerminal, sorted by age
- **Risk scoring** — heuristic engine using 81 on-chain features (RugCheck, GeckoTerminal, Helius, Jupiter)

## Getting Started

### Backend (from project root)

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies API requests to the backend on port 8000.

## Environment

API keys are required in `live_data/.env`:

- `HELIUS_API_KEY` — free at https://dev.helius.xyz/
- `JUPITER_API_KEY` — from Jupiter API portal
