# DeFi Sentinel — Full Architecture & Build Spec

## Context: HackEurope 2026

This is a 48-hour hackathon project. We are a 2-person team. The project must be **complete, polished, and demoable** — not a sprawling half-baked prototype.

### Judging Criteria (CRITICAL — read this first)

1. **Startup Potential (40% weight):** "Could this become a real company?" Show the problem ($X lost), who pays, what competitors exist, your angle. The pitch matters as much as the code.
2. **Technical Complexity (30%):** "Not just a shiny UI — use advanced tools." Judges want to see real data pipelines, ML models, blockchain integration, not just API wrappers.
3. **Execution (30%):** "A complete, well-thought-out package, not stitched together by 10 AI agents." Clean code, proper error handling, bulletproof demo. Polished product doing 3 things perfectly beats a scraggly product attempting 8.

### Prize Targets

| Prize | Amount | Sponsor | What They Want |
|-------|--------|---------|----------------|
| Security Track | €1,000 | BlueDot Impact | Defensive security tool that detects/monitors/mitigates threats |
| Best Use of Data | €7,000 (1st) | Susquehanna (quant trading firm) | Sophisticated data pipeline, real-time analysis, quantitative rigor |
| Built on Solana | €3,500 | Superteam IE | Genuine Solana integration. Confidential Transfers = bonus points |
| Best Stripe Integration | €3,000 | Stripe | Meaningful Stripe integration, not bolted on |
| **Total ceiling** | **€14,500** | | |

---

## 1. What Is DeFi Sentinel?

**One sentence:** A real-time AI-powered fraud detection system that monitors every new token launch on Solana, scores rug-pull risk using on-chain + social signals, and alerts traders before they lose money.

**The problem:** Hundreds of new tokens launch on Solana daily. Many are rug pulls — scams where creators hype a token, attract investment, then drain all liquidity and vanish. MetaYield Farm rug pull stole $290M in Feb 2025. $370-500M was extracted from Solana users via MEV sandwich attacks over 16 months. Existing tools (Token Sniffer, QuillCheck) are basic rule-based checkers with no ML, no real-time monitoring, and no social analysis.

**The solution:** Real-time monitoring + multi-signal risk scoring + ML classification + instant alerts.

**Who pays:**
- B2B: DeFi platforms (Raydium, Jupiter, Phantom) pay monthly API subscription to show risk warnings to their users
- B2C: Individual traders get alerts via dashboard and Telegram bot (free tier + paid pro tier)

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION                           │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Solana WS    │    │ Helius       │    │ Twitter/X    │      │
│  │ (new pools)  │    │ DAS API      │    │ API          │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────┬───────┴───────────┬───────┘               │
│                     ▼                   │                        │
│              ┌─────────────┐            │                        │
│              │  Ingestion  │            │                        │
│              │  Pipeline   │◄───────────┘                        │
│              └──────┬──────┘                                     │
└─────────────────────┼───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RISK ENGINE                                │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Contract    │  │  Holder      │  │  Liquidity   │         │
│  │  Analyzer    │  │  Analyzer    │  │  Analyzer    │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                  │                  │
│  ┌──────┴───────┐  ┌──────┴───────┐         │                  │
│  │  Deployer    │  │  Social      │         │                  │
│  │  Analyzer    │  │  Analyzer    │         │                  │
│  └──────┬───────┘  └──────┬───────┘         │                  │
│         │                 │                  │                  │
│         └────────┬────────┴──────────┬───────┘                  │
│                  ▼                   │                           │
│           ┌─────────────┐           │                           │
│           │  Feature     │◄──────────┘                           │
│           │  Engineering │                                       │
│           └──────┬──────┘                                        │
│                  ▼                                               │
│           ┌─────────────┐                                        │
│           │  ML Model   │  (XGBoost / rule-based fallback)       │
│           │  Prediction │                                        │
│           └──────┬──────┘                                        │
│                  ▼                                               │
│           ┌─────────────┐                                        │
│           │  Risk Score │  0.0 → 1.0 + level + recommendation    │
│           └──────┬──────┘                                        │
└──────────────────┼──────────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OUTPUT LAYER                                │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  REST API    │  │  WebSocket   │  │  Telegram    │         │
│  │  (FastAPI)   │  │  Live Feed   │  │  Bot         │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │  React       │  │  Stripe      │                            │
│  │  Dashboard   │  │  Billing     │                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend Spec (Python / FastAPI)

### 3.1 Tech Stack

- **Python 3.12**, FastAPI, uvicorn
- **Database:** PostgreSQL (SQLAlchemy async + asyncpg)
- **Cache:** Redis (for rate limiting, caching scores)
- **ML:** scikit-learn + XGBoost (or rule-based fallback)
- **Solana:** solana-py, solders, websockets
- **Payments:** stripe python SDK
- **HTTP client:** httpx (async)

### 3.2 API Endpoints

#### `GET /health`
Returns service health including Solana connection status and model status.

#### `GET /api/v1/tokens/{mint_address}/score`
Main endpoint. Takes a Solana token mint address, runs the full risk pipeline, returns:
```json
{
  "mint": "7xKXtg...",
  "name": "SCAMCOIN",
  "symbol": "SCAM",
  "risk_score": 0.87,
  "risk_level": "HIGH",
  "signals": {
    "mint_authority_retained": true,
    "freeze_authority_retained": false,
    "lp_unlocked": true,
    "lp_percentage": 0.0,
    "top10_holder_pct": 0.91,
    "deployer_prev_rugs": 3,
    "deployer_wallet_age_days": 2,
    "social_bot_ratio": 0.74,
    "social_follower_count": 12500,
    "initial_liquidity_sol": 0.5
  },
  "recommendation": "AVOID — High rug-pull probability (mint authority retained, liquidity unlocked, deployer has 3 prior rugs)",
  "timestamp": "2026-02-21T14:30:00Z",
  "confidence": 0.85
}
```

#### `GET /api/v1/tokens/recent?limit=20&min_risk=0.5`
Returns recently scored tokens, filterable by risk level.

#### `GET /api/v1/tokens/flagged?limit=20`
Returns tokens flagged as HIGH or CRITICAL.

#### `GET /api/v1/deployers/{wallet}/history`
Returns a deployer wallet's track record: past launches, rug count, wallet age.

#### `GET /api/v1/stats`
Platform stats: tokens monitored, rugs detected, avg detection time.

#### `POST /api/v1/billing/checkout`
Creates Stripe Checkout session. Body: `{ "email": "...", "tier": "pro" }`

#### `POST /api/v1/billing/webhook`
Stripe webhook handler for subscription events.

#### `WebSocket /ws/feed`
Real-time feed of new token launches with risk scores. Clients connect and receive:
```json
{
  "type": "new_token",
  "data": {
    "mint": "...",
    "name": "...",
    "symbol": "...",
    "risk_score": 0.87,
    "risk_level": "HIGH",
    "dex": "raydium",
    "initial_liquidity_sol": 2.5,
    "timestamp": "..."
  }
}
```

### 3.3 Services

#### SolanaListener (`services/solana_listener.py`)
- Connects to Solana RPC websocket
- Subscribes to transaction logs mentioning DEX program IDs:
  - Raydium AMM V4: `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`
  - Pump.fun: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`
  - PumpSwap: `PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP`
- Detects pool creation events (look for "Initialize", "Create" in logs)
- Extracts mint address and deployer wallet from transaction
- Triggers risk scoring pipeline for each new token
- Must handle reconnection gracefully

#### RiskEngine (`services/risk_engine.py`)
The core scoring logic. Takes a mint address, runs 5 parallel analyses:

**1. Contract Analysis (weight: 0.30)**
- Fetch mint account via Helius `getAccountInfo` with `jsonParsed` encoding
- Check if `mintAuthority` is set (can print unlimited tokens → HIGH RISK)
- Check if `freezeAuthority` is set (can freeze your tokens)
- Check if program has upgrade authority retained

**2. Holder Distribution (weight: 0.25)**
- Fetch top holders via Helius `getTokenAccounts`
- Calculate top-10 holder concentration (% of supply)
- If top 10 hold >80% → high risk
- Calculate Gini coefficient of distribution

**3. Liquidity Analysis (weight: 0.20)**
- Check if LP tokens are locked (query LP mint token accounts)
- Check initial liquidity size in SOL
- Check deployer's % of LP tokens
- Low liquidity + unlocked LP = easy rug

**4. Deployer History (weight: 0.15)**
- Fetch deployer wallet's transaction history via `getSignaturesForAddress`
- Count previous token deployments
- Cross-reference with known rug-pull database
- Check wallet age (creation date)
- New wallet + multiple deployments = serial scammer

**5. Social Analysis (weight: 0.10)**
- If token has Twitter/X account in metadata, analyze:
  - Follower count vs engagement ratio (bots have high followers, low engagement)
  - Account age
  - Tweet frequency and patterns
- If no social presence, that's slightly positive (not running a hype campaign)

Final score = weighted sum, clamped to [0, 1]. Classified as:
- CRITICAL: >= 0.8
- HIGH: >= 0.7
- MEDIUM: >= 0.4
- LOW: < 0.4

#### HeliusClient (`services/helius_client.py`)
Wrapper for Helius RPC. Key methods:
- `get_asset(mint)` → token metadata (name, symbol, image, authorities)
- `get_token_accounts(mint, limit)` → top holders
- `get_signatures(address, limit)` → transaction history
- `get_account_info(address)` → raw account data

Use Helius because it provides enhanced APIs (DAS) that are much richer than base Solana RPC. Free tier gives 100K credits/day which is plenty for hackathon.

Sign up at https://dev.helius.xyz/ — API key goes in `.env` as `HELIUS_API_KEY`.

#### StripeBilling (`services/stripe_billing.py`)
- `create_checkout_session(price_id, email)` → Stripe Checkout URL
- `report_usage(subscription_item_id, quantity)` → metered billing
- `handle_webhook(payload, sig)` → process Stripe events
- `get_customer_subscription(customer_id)` → check tier

Stripe setup needed:
1. Create a Stripe test account
2. Create 2 products: "DeFi Sentinel Pro" ($29/mo) and "DeFi Sentinel API" (metered, per-request)
3. Get price IDs, put in `.env`
4. Set up webhook endpoint pointing to `/api/v1/billing/webhook`

### 3.4 ML Model (`ml/model.py`)

**Features (22 total):**
```
# Contract (3)
mint_authority_retained, freeze_authority_retained, upgrade_authority_retained

# Holders (4)
top10_holder_pct, top1_holder_pct, unique_holders, holder_gini_coefficient

# Liquidity (4)
initial_liquidity_sol, lp_locked, lp_lock_duration_days, deployer_lp_pct

# Deployer (4)
deployer_wallet_age_days, deployer_prev_deployments, deployer_prev_rugs, deployer_funded_by_mixer

# Social (4)
social_follower_count, social_bot_ratio, social_engagement_ratio, social_account_age_days

# Temporal (3)
hours_since_launch, trade_count_first_hour, buy_sell_ratio_first_hour
```

**Training approach:**
- If we have time: collect labeled data from known rug pulls (there are Kaggle datasets and the RPHunter paper data). Train XGBoost classifier. Save with joblib.
- If no time: use the rule-based fallback scoring in `RiskEngine._rule_based_score()`. This is fine for the demo — judges care about the pipeline, not just the model accuracy.

**Rule-based fallback scoring:**
- mint_authority_retained → +0.25
- freeze_authority_retained → +0.15
- lp_unlocked → +0.20
- top10_holder_pct > 0.9 → +0.20
- top10_holder_pct > 0.7 → +0.10
- deployer_prev_rugs > 0 → +0.15 per rug (max 0.30)
- deployer_wallet_age < 7 days → +0.10
- social_bot_ratio > 0.7 → +0.10

### 3.5 Database Schema

```sql
CREATE TABLE tokens (
    id SERIAL PRIMARY KEY,
    mint VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128),
    symbol VARCHAR(32),
    deployer VARCHAR(64),
    dex VARCHAR(32),
    risk_score FLOAT,
    risk_level VARCHAR(16),
    signals JSONB,
    recommendation TEXT,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_scored TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tokens_risk ON tokens(risk_score DESC);
CREATE INDEX idx_tokens_time ON tokens(first_seen DESC);
CREATE INDEX idx_tokens_deployer ON tokens(deployer);

CREATE TABLE deployers (
    id SERIAL PRIMARY KEY,
    wallet VARCHAR(64) UNIQUE NOT NULL,
    first_seen TIMESTAMPTZ,
    total_deployments INT DEFAULT 0,
    rug_count INT DEFAULT 0,
    wallet_age_days INT DEFAULT 0
);

CREATE TABLE api_usage (
    id SERIAL PRIMARY KEY,
    api_key VARCHAR(64),
    endpoint VARCHAR(128),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    response_time_ms INT
);
```

---

## 4. Frontend Spec (React + TypeScript)

### 4.1 Tech Stack

- React 18, TypeScript, Vite
- Tailwind CSS for styling
- Recharts for charts
- Use dark theme — this is a security/trading product, dark themes are expected

### 4.2 Pages & Components

#### Dashboard Page (`/`)
The main page. Three sections:

**1. Live Feed (left panel, ~60% width)**
- Real-time scrolling list of new token launches
- Each item shows: token name/symbol, mint address (truncated), risk score gauge, risk level badge (color-coded), DEX source, time ago
- Color coding: RED for HIGH/CRITICAL, YELLOW for MEDIUM, GREEN for LOW
- Clicking a token opens the detail view
- Connects to WebSocket `/ws/feed`
- New items slide in from top with subtle animation

**2. Stats Bar (top)**
- Tokens monitored (24h)
- Rugs detected (24h)
- Average detection time
- Model accuracy / confidence

**3. Risk Distribution (right panel, ~40% width)**
- Pie chart or bar chart: how many tokens at each risk level
- Recent flagged tokens list (HIGH + CRITICAL only)

#### Token Detail Page (`/token/:mint`)
Deep dive into a single token's risk analysis:

**1. Header**
- Token name, symbol, mint address (with copy button and Solscan link)
- Large risk score gauge (circular, color-coded)
- Risk level badge
- Recommendation text

**2. Signal Breakdown**
- Visual breakdown of each risk signal category with scores
- Use horizontal bar chart or radar chart
- Show each individual signal with explanation:
  - ✅ "Mint authority revoked" (green)
  - ❌ "LP tokens unlocked — creator can drain liquidity" (red)
  - ⚠️ "Top 10 holders own 78% of supply" (yellow)

**3. Deployer Profile**
- Wallet address, age, previous deployments
- If previous rugs: show them in a timeline
- Link to Solscan wallet page

**4. Holder Distribution**
- Bar chart or treemap of top holders
- Highlight if single wallet holds >50%

#### Pricing Page (`/pricing`)
- Free vs Pro comparison table
- Pro: $29/mo, unlimited API, Telegram alerts, webhooks
- Stripe Checkout button that creates a session and redirects

### 4.3 Key UI Components

**RiskGauge** — Circular gauge component (like a speedometer) that shows 0–100 risk score with color gradient (green → yellow → red). This is the signature visual element. Make it look really good.

**TokenCard** — Card component for the live feed. Shows token info + mini risk gauge. Compact but informative.

**SignalBar** — Horizontal bar showing a signal's contribution to the risk score. Red/yellow/green fill.

**LiveFeed** — WebSocket-connected scrolling list. New items animate in. Auto-scrolls but pauses when user hovers.

### 4.4 Design Direction

- **Dark theme**: #0a0a0f background, #1a1a2e cards
- **Accent colors**: Green (#00e5a0) for safe, Red (#ef4444) for danger, Yellow (#f59e0b) for warning, Purple (#9945FF) for Solana branding
- **Font**: Inter or JetBrains Mono for data
- **Feel**: Bloomberg terminal meets modern crypto dashboard. Dense data, professional, not cartoon-y.
- **No excessive animation.** Subtle transitions only.

---

## 5. Solana Integration Details

### 5.1 Monitoring (Core)
- WebSocket subscription to DEX program logs
- Parse transaction to extract: new token mint, deployer wallet, pool address, initial liquidity
- This is the most important Solana integration — it's what makes the product real-time

### 5.2 On-Chain Data (Core)
- Fetch token mint account to check authorities
- Fetch token accounts to analyze holder distribution
- Fetch deployer transaction history

### 5.3 Confidential Transfers (Bonus Points)
The challenge spec explicitly says: "Implementing Confidential Transfers (using Token Extensions) will be awarded extra credit or bonus points."

Token-2022 Confidential Transfers use zero-knowledge proofs (ZK ElGamal) to hide transfer amounts while proving validity. We can use this for:
- **Privacy-preserving premium subscriptions**: Users pay for Pro tier using SPL tokens with confidential transfers, so their subscription amount is hidden on-chain
- This is a stretch goal. Only do it if core product is solid first.

### 5.4 Risk Attestation (Nice to Have)
Store verified risk scores on-chain as a Solana program. Other apps can read our scores. This creates a public, tamper-proof record. Implement with Anchor if time permits.

---

## 6. Stripe Integration Details

### 6.1 Subscription Billing (Core)
- Free tier: 50 API calls/day, dashboard access
- Pro tier: $29/mo, unlimited API, Telegram alerts
- Use Stripe Checkout for the signup flow (redirect user to Stripe-hosted page)
- Handle webhook events for subscription lifecycle

### 6.2 Metered Billing (Core)
- Enterprise tier: pay per API call
- Report usage to Stripe using `SubscriptionItem.create_usage_record`
- Track usage in Redis for rate limiting

### 6.3 Stripe Agent Toolkit (Bonus)
Stripe has an agent toolkit (https://docs.stripe.com/agents) for embedding payments into agentic workflows. If we have time, integrate it so the DeFi Sentinel agent can handle its own billing operations. This would impress Stripe judges.

---

## 7. Demo Script

This is what we show the judges. Must be bulletproof.

**Setup:** Dashboard open on a large screen. Live feed running with real Solana data.

**Demo flow (3 minutes):**

1. **"Here's the problem"** (30s): Quick stat: $290M stolen in one rug pull. Show a headline. "Current tools are basic rule-based checkers."

2. **"Here's DeFi Sentinel"** (30s): Point at live dashboard. "Right now, we're monitoring every new token launching on Solana in real-time. Each one gets scored in seconds."

3. **"Watch it catch a scam"** (60s): Either:
   - Point at a real HIGH-risk token that just appeared in the feed
   - OR use a pre-prepared known rug-pull address — paste it into the search/lookup, show the full analysis
   - Walk through the signals: "Mint authority retained — the creator can print unlimited tokens. LP unlocked — they can drain liquidity anytime. This deployer wallet has launched 3 previous rug pulls."
   - Show the risk gauge going to RED

4. **"The data pipeline"** (30s): Show the architecture briefly. "We're pulling from Solana websocket, Helius DAS API, and Twitter simultaneously. 22 features feed into an ML classifier."

5. **"Who pays for this"** (30s): Show pricing page. Click "Subscribe to Pro" — Stripe Checkout opens. Show the Stripe dashboard with test subscription. "DeFi platforms integrate our API. Individual traders use the dashboard."

6. **"On-chain"** (15s): Show the Solana transaction for a risk attestation or confidential transfer. "Every score is verifiable on-chain."

---

## 8. Seed Data / Demo Data

For a convincing demo, we need some pre-loaded data:

**Known rug pulls to demonstrate detection on:**
- Search Solscan for recent rug pulls and save their mint addresses
- Or create test tokens on Solana devnet with rug-pull characteristics (retained mint authority, concentrated holders)

**Fallback for demo:** If live data isn't flowing during the demo, have a mock WebSocket server that replays saved token launch events. The judges should see the feed moving regardless.

Create a `scripts/seed_data.py` that:
1. Populates the DB with 50-100 pre-scored tokens (mix of safe and rugs)
2. Includes some known real rug-pull addresses with their actual on-chain data

Create a `scripts/mock_feed.py` that:
1. Reads from seed data and replays token launches over the WebSocket
2. As a fallback if Solana RPC is slow during demo

---

## 9. File Structure

```
defi-sentinel/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app, lifespan, CORS
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py            # REST endpoints
│   │   │   └── websocket.py         # WS live feed + connection manager
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py            # Pydantic settings from .env
│   │   │   └── database.py          # SQLAlchemy async engine + session
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── solana_listener.py   # WebSocket DEX monitor
│   │   │   ├── risk_engine.py       # Multi-signal scoring
│   │   │   ├── helius_client.py     # Helius API wrapper
│   │   │   ├── social_analyzer.py   # Twitter/X analysis
│   │   │   └── stripe_billing.py    # Stripe Checkout + metered billing
│   │   ├── ml/
│   │   │   ├── __init__.py
│   │   │   ├── model.py            # XGBoost classifier + rule fallback
│   │   │   ├── features.py         # Feature extraction from raw data
│   │   │   └── train.py            # Training script
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── schemas.py          # Pydantic models (request/response)
│   │       └── db_models.py        # SQLAlchemy ORM models
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # Router setup
│   │   ├── main.tsx                 # Entry point
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx        # Main dashboard page
│   │   │   ├── TokenDetail.tsx      # Single token deep dive
│   │   │   └── Pricing.tsx          # Stripe pricing page
│   │   ├── components/
│   │   │   ├── LiveFeed.tsx         # WebSocket real-time feed
│   │   │   ├── TokenCard.tsx        # Token summary card
│   │   │   ├── RiskGauge.tsx        # Circular risk score gauge
│   │   │   ├── SignalBreakdown.tsx  # Signal detail bars
│   │   │   ├── StatsBar.tsx         # Top stats row
│   │   │   ├── HolderChart.tsx      # Holder distribution chart
│   │   │   └── Navbar.tsx           # Top navigation
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts      # WS connection hook
│   │   │   └── useApi.ts            # API fetch hook
│   │   ├── utils/
│   │   │   ├── api.ts              # Axios/fetch wrapper
│   │   │   └── format.ts           # Address truncation, time formatting
│   │   └── index.css               # Tailwind imports + global styles
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── Dockerfile
├── scripts/
│   ├── seed_data.py
│   └── mock_feed.py
├── data/
│   └── labeled_tokens.csv
├── docker-compose.yml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## 10. Priority Order (What To Build First)

This is a 48h hackathon. Build in this order. Stop when time runs out — each step produces a demoable increment.

### Phase 1: Core Pipeline (0-10h) — MUST HAVE
1. FastAPI skeleton with health endpoint
2. Helius client (get_asset, get_token_accounts, get_account_info)
3. Risk engine with rule-based scoring (no ML yet)
4. `/api/v1/tokens/{mint}/score` endpoint working end-to-end
5. Test with a real Solana token mint address

### Phase 2: Real-Time Feed (10-18h) — MUST HAVE
6. Solana WebSocket listener monitoring DEX launches
7. WebSocket `/ws/feed` broadcasting new tokens
8. PostgreSQL storage for scored tokens
9. `/api/v1/tokens/recent` and `/api/v1/tokens/flagged` endpoints

### Phase 3: Frontend Dashboard (18-30h) — MUST HAVE
10. React app scaffold (Vite + TypeScript + Tailwind)
11. RiskGauge component (the signature visual)
12. LiveFeed component connected to WebSocket
13. Dashboard page with live feed + stats
14. TokenDetail page with signal breakdown

### Phase 4: Stripe + Polish (30-40h) — MUST HAVE
15. Stripe Checkout integration for Pro subscription
16. Pricing page
17. API rate limiting (Redis)
18. Metered billing for API calls
19. Seed data for demo

### Phase 5: Extras (40-48h) — NICE TO HAVE
20. ML model training (if labeled data available)
21. Social analyzer (Twitter API)
22. Telegram bot
23. Solana Confidential Transfers
24. On-chain risk attestation program
25. Demo rehearsal and edge case fixes

---

## 11. Environment Variables

```env
# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_WS_URL=wss://api.mainnet-beta.solana.com
HELIUS_API_KEY=           # Get free at https://dev.helius.xyz/
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_KEY

# Database
DATABASE_URL=postgresql://sentinel:sentinel@localhost:5432/defi_sentinel
REDIS_URL=redis://localhost:6379/0

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...

# Twitter (optional, phase 5)
TWITTER_BEARER_TOKEN=

# App
APP_ENV=development
CORS_ORIGINS=http://localhost:5173
```

---

## 12. Key Implementation Notes

### Error Handling
- Every Helius/Solana call must have timeout (10s) and retry logic (3 attempts with exponential backoff)
- If any single signal fails to fetch, score the token with available signals and note which ones are missing
- Never let one failed API call crash the entire scoring pipeline

### Caching
- Cache token scores in Redis with 5-minute TTL
- Cache Helius responses with 1-minute TTL
- This prevents hammering APIs during demo

### Rate Limiting
- Track API calls per user in Redis
- Free tier: 50/day, Pro: unlimited, check on every request
- Return 429 with clear message for free tier users

### Logging
- Structured JSON logging
- Log every token scored with risk level
- Log Solana connection status changes
- This helps debugging during hackathon

### Testing
- At minimum: test the risk engine scoring logic with fixture data
- Test that API endpoints return correct schemas
- Don't need 100% coverage, but risk engine tests are essential for demo confidence
