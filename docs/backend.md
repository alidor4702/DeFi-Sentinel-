# Backend Architecture

> FastAPI backend powering DeFi Sentinel's real-time rug-pull detection.

---

## System Overview

```mermaid
graph TB
    subgraph CLIENTS["🖥️ Clients"]
        REACT["React Frontend<br/>Dashboard · Scanner · Wallet"]
        WS_CLIENT["WebSocket Clients<br/>Real-time feed"]
    end

    subgraph BACKEND["⚙️ FastAPI Backend  (port 8000)"]
        API["REST API<br/>16 endpoints"]
        WSS["WebSocket Server<br/>/ws"]
        STRIPE_H["Stripe Handler<br/>Checkout · Webhooks"]
        SOL_H["Solana Handler<br/>Attestations · Payments"]
    end

    subgraph DATA["📡 Data Collection Layer"]
        COLLECTOR["Multi-API Collector<br/>(concurrent)"]
        HELIUS["Helius DAS"]
        RUGCHECK["RugCheck"]
        GOPLUS["GoPlus Security"]
        GECKO["GeckoTerminal"]
        JUPITER["Jupiter"]
    end

    subgraph ML["🧠 ML Scoring Engine"]
        MAPPER["Feature Mapper<br/>_map_v4() → 77 features"]
        XGBOOST["XGBoost v4<br/>600 trees · AUC 0.999"]
        HEURISTIC["Heuristic Adjustments"]
    end

    subgraph CHAIN["⛓️ Solana Blockchain"]
        MAINNET["Mainnet RPC<br/>Token data · WebSocket"]
        DEVNET["Devnet<br/>Attestations · Payments"]
    end

    subgraph STORAGE["💾 Storage"]
        SQLITE["SQLite<br/>attestations · payments"]
        CACHE["In-Memory Cache<br/>~20 live tokens"]
    end

    REACT --> API
    REACT --> WSS
    WS_CLIENT --> WSS

    API --> COLLECTOR
    API --> ML
    API --> STRIPE_H
    API --> SOL_H

    COLLECTOR --> HELIUS
    COLLECTOR --> RUGCHECK
    COLLECTOR --> GOPLUS
    COLLECTOR --> GECKO
    COLLECTOR --> JUPITER

    COLLECTOR --> MAPPER
    MAPPER --> XGBOOST
    XGBOOST --> HEURISTIC

    SOL_H --> DEVNET
    COLLECTOR --> MAINNET

    API --> SQLITE
    API --> CACHE

    style BACKEND fill:#1e293b,stroke:#6366f1,color:#e2e8f0
    style DATA fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style ML fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style CHAIN fill:#1e293b,stroke:#9945ff,color:#e2e8f0
    style STORAGE fill:#1e293b,stroke:#818cf8,color:#e2e8f0
    style CLIENTS fill:#1e293b,stroke:#818cf8,color:#e2e8f0
```

**Start command:**
```bash
cd DeFiSentinel
PYTHONPATH=. python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## API Endpoints (16 total)

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

Full pipeline from user request to risk score — the core operation of the system.

```mermaid
graph TD
    REQ["GET /api/scan/{mint}"] --> COLLECT["collect_features(mint)<br/>6 APIs concurrently"]

    COLLECT --> H["Helius DAS<br/>metadata · authorities · supply"]
    COLLECT --> RC["RugCheck<br/>risk score · LP lock · holders"]
    COLLECT --> GP["GoPlus Security<br/>holder % · TVL · honeypot"]
    COLLECT --> GT["GeckoTerminal<br/>price · volume · liquidity"]
    COLLECT --> JP["Jupiter<br/>strict-list check"]
    COLLECT --> DER["Derived<br/>metadata completeness<br/>authority risk"]

    H --> MAP["_map_v4()<br/>→ 77-column feature vector"]
    RC --> MAP
    GP --> MAP
    GT --> MAP
    JP --> MAP
    DER --> MAP

    MAP --> XGB["XGBoost predict<br/>P(rug) ∈ [0.0, 1.0]"]
    XGB --> ADJUST["Heuristic Adjustments<br/>• RugCheck < 300 → boost risk<br/>• Jupiter strict-list → reduce<br/>• Volume > $100K → reduce<br/>• Creator < 24h → boost"]
    ADJUST --> CAP["Established-Token Cap<br/>$1M+ liq & 30d+ → max 25"]
    CAP --> RESPONSE["JSON Response"]

    subgraph RESPONSE_DETAIL["📋 Response Payload"]
        RS["Risk Score 0–100"]
        VD["Verdict: SAFE / MODERATE / DANGER"]
        ML_CONF["ML Confidence %"]
        RF["Risk Factors (human-readable)"]
        AI["AI Analysis Narrative"]
        FB["Feature Breakdown (all collected)"]
        SRC["API Source Statuses"]
    end

    RESPONSE --> RESPONSE_DETAIL

    style REQ fill:#1e293b,stroke:#6366f1,color:#e2e8f0
    style COLLECT fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style MAP fill:#1e293b,stroke:#818cf8,color:#e2e8f0
    style XGB fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style ADJUST fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style CAP fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style RESPONSE fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style RESPONSE_DETAIL fill:#0f172a,stroke:#22c55e,color:#e2e8f0
```

---

## Data Flow: Live Token Feed

The dashboard uses two concurrent data sources to populate the real-time token feed:

```mermaid
graph TD
    subgraph BG["🔄 Background Refresh (every 5 min)"]
        GECKO_TREND["GeckoTerminal<br/>Trending tokens"]
        PUMP_NEW["Raydium / Pump.fun<br/>New pool launches"]
        GECKO_TREND --> SCAN_BG["Scan up to 25 tokens<br/>(semaphore: 2 concurrent)"]
        PUMP_NEW --> SCAN_BG
    end

    subgraph RT["⚡ Solana WebSocket (real-time)"]
        HELIUS_WS["Helius Mainnet WS<br/>logsSubscribe"]
        HELIUS_WS --> DETECT["Detect InitializeMint<br/>instructions"]
        DETECT --> RESOLVE["Resolve new<br/>token mint address"]
        RESOLVE --> SCAN_RT["Immediate scan<br/>via ML pipeline"]
    end

    SCAN_BG --> CACHE["In-Memory Cache<br/>~20 tokens sorted:<br/>SAFE → MODERATE → DANGER"]
    SCAN_RT --> CACHE

    CACHE --> REST_API["GET /api/tokens<br/>REST response"]
    CACHE --> WS_PUSH["WS /ws<br/>Push to all clients"]

    style BG fill:#0f172a,stroke:#f59e0b,color:#e2e8f0
    style RT fill:#0f172a,stroke:#22c55e,color:#e2e8f0
    style CACHE fill:#1e293b,stroke:#6366f1,color:#e2e8f0
```

---

## Scoring Pipeline Detail

The ML scorer (`backend/ml_scorer.py`) implements a multi-stage scoring process:

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                      SCORING PIPELINE STAGES                        │
  │                                                                     │
  │  Stage 1: Feature Mapping (_map_v4)                                │
  │  ├── Maps collector output → 77 XGBoost input columns              │
  │  ├── Uses np.nan for missing data (API failures, rate limits)      │
  │  └── Consistent ordering with models/feature_list_v4.json          │
  │                                                                     │
  │  Stage 2: XGBoost Prediction                                       │
  │  ├── Native NaN handling → routes missing features through          │
  │  │   learned optimal splits                                        │
  │  └── Output: P(rug) ∈ [0.0, 1.0]                                  │
  │                                                                     │
  │  Stage 3: Heuristic Adjustments                                    │
  │  ├── RugCheck score < 300      → risk boost                        │
  │  ├── Jupiter strict-list       → risk reduction                    │
  │  ├── 24h volume > $100K        → risk reduction                    │
  │  └── Creator wallet < 24h old  → risk boost                        │
  │                                                                     │
  │  Stage 4: Established-Token Cap                                    │
  │  ├── Liquidity > $1M AND pool age > 30 days                       │
  │  └── → max risk capped at 25 (blue-chip protection)               │
  │                                                                     │
  │  Stage 5: Fallback (if XGBoost unavailable)                        │
  │  └── Enhanced heuristic scoring using rule-based risk factors      │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## Payment Flows

### Stripe Checkout

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Stripe

    User->>Frontend: Click "Subscribe" on Pricing page
    Frontend->>Backend: POST /api/create-checkout {plan: "pro"}
    Backend->>Stripe: Create Checkout Session<br/>($9.99/mo or $99.99/mo)
    Stripe-->>Backend: Session URL
    Backend-->>Frontend: {url: "https://checkout.stripe.com/..."}
    Frontend->>Stripe: Redirect to Stripe Checkout
    User->>Stripe: Enter card (test: 4242...)
    Stripe-->>Frontend: Redirect to success URL
```

### SOL Payment

```mermaid
sequenceDiagram
    participant User
    participant Phantom
    participant Frontend
    participant Backend
    participant Solana as Solana Devnet

    User->>Frontend: Click "Pay with SOL" (scan pack)
    Frontend->>Phantom: Request SOL transfer<br/>(0.05–0.60 SOL)
    Phantom->>User: Approve transaction
    User->>Phantom: Confirm
    Phantom->>Solana: Submit SOL transfer
    Solana-->>Phantom: Transaction signature
    Phantom-->>Frontend: tx signature
    Frontend->>Backend: POST /api/verify-solana-payment<br/>{signature, wallet, pack}
    Backend->>Solana: Verify transaction on-chain
    Solana-->>Backend: Confirmed ✅
    Backend->>Backend: Credit scans to wallet
    Backend-->>Frontend: {credits: 10, tx: "..."}
```

---

## On-Chain Attestation Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Solana as Solana Devnet
    participant Memo as Memo Program

    User->>Frontend: Click "Attest on Solana"<br/>(after token scan)
    Frontend->>Backend: POST /api/attest<br/>{mint, riskScore, verdict, wallet}
    Backend->>Backend: Build Memo instruction<br/>(JSON: mint, score, verdict, timestamp)
    Backend->>Solana: Submit transaction with Memo
    Solana->>Memo: Execute Memo program
    Memo-->>Solana: Store in transaction log
    Solana-->>Backend: Transaction signature
    Backend->>Backend: Save to SQLite (attestations table)
    Backend-->>Frontend: {signature: "5Kx...", explorer_url: "..."}
    Frontend->>User: Show Solana Explorer link
```

---

## Database Schema

SQLite (`defi_sentinel.db`) stores persistent state:

```
  ┌──────────────────────────────────────┐    ┌──────────────────────────────────┐
  │          attestations                 │    │           payments               │
  │──────────────────────────────────────│    │──────────────────────────────────│
  │  id           INTEGER PK             │    │  id           INTEGER PK         │
  │  mint         TEXT                    │    │  wallet       TEXT               │
  │  risk_score   INTEGER                │    │  tx_signature TEXT UNIQUE        │
  │  verdict      TEXT                    │    │  pack         TEXT               │
  │  wallet       TEXT                    │    │  credits      INTEGER            │
  │  tx_signature TEXT UNIQUE             │    │  amount_sol   REAL               │
  │  timestamp    TEXT                    │    │  timestamp    TEXT               │
  └──────────────────────────────────────┘    └──────────────────────────────────┘
```

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

```
  ┌──────────────────┬────────────────────────────────────────┐
  │  Package          │  Purpose                               │
  ├──────────────────┼────────────────────────────────────────┤
  │  fastapi          │  Async web framework                   │
  │  uvicorn          │  ASGI server                           │
  │  httpx            │  Async HTTP client for 6 API sources   │
  │  xgboost          │  ML model inference                    │
  │  numpy            │  Feature array construction            │
  │  stripe           │  Payment processing                    │
  │  solders          │  Solana keypair & transaction building  │
  │  solana           │  Solana RPC client                     │
  │  python-dotenv    │  Environment variable loading          │
  │  websockets       │  Solana mainnet WebSocket listener     │
  └──────────────────┴────────────────────────────────────────┘
```
