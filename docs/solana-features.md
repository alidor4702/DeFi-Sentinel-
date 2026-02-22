# Solana-Based Features

> All blockchain-native features in DeFi Sentinel built on Solana.

---

## Overview

DeFi Sentinel integrates deeply with Solana at four levels:

1. **Phantom Wallet Connect** — authenticate users via wallet signature
2. **On-Chain Risk Attestations** — publish immutable scan results to Solana devnet
3. **SOL Payments** — pay for scan packs directly with SOL via Phantom
4. **Wallet Risk Profile** — scan all tokens in a connected wallet for rug exposure
5. **Real-Time Token Detection** — listen to Solana mainnet WebSocket for new token launches

---

## 1. Phantom Wallet Connect

**Frontend:** `@solana/wallet-adapter-react` + `@solana/wallet-adapter-wallets`  
**Page:** Connect page (`/connect`)

### How It Works

1. User clicks "Connect Wallet" → Phantom browser extension opens
2. User approves the connection → wallet adapter provides `publicKey`
3. For authenticated actions, the frontend requests a **message signature** via `signMessage()`
4. Backend verifies the signature using `solders` (`POST /api/auth/wallet`)
5. Wallet address is used as the user identity for attestations, payments, and credits

### Signature Verification

The backend uses Ed25519 signature verification:
```
PublicKey + Signature + Message → verified (boolean)
```
This proves the user controls the wallet without requiring any on-chain transaction.

---

## 2. On-Chain Risk Attestations

**Backend endpoint:** `POST /api/attest`  
**Network:** Solana **devnet**  
**Program:** Solana Memo Program (`MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr`)

### What It Does

When a user scans a token and clicks "Attest on Solana," DeFi Sentinel writes an **immutable record** of the risk assessment to the Solana blockchain via a Memo transaction.

### Attestation Flow

```
1. User scans token → gets risk score
2. User clicks "Attest on Solana"
3. Frontend requests wallet signature (optional co-sign)
4. Backend builds Memo transaction:
   {
     "app": "DeFiSentinel",
     "version": "1.0",
     "mint": "<token_address>",
     "riskScore": 85,
     "verdict": "DANGER",
     "features": 77,
     "hash": "<features_hash>",
     "wallet": "<user_wallet_prefix>",
     "ts": "2026-06-22T..."
   }
5. Backend signs with treasury keypair → sends to devnet
6. Transaction signature stored in SQLite + returned to frontend
7. User can view on Solana Explorer / Solscan
```

### Co-Signed Attestations

If the user has a connected Phantom wallet, they can **co-sign** the attestation:
- Frontend signs a message like `"DeFi Sentinel Risk Attestation: {mint} score={score}"`
- Backend verifies the signature before creating the on-chain transaction
- The attestation memo includes the wallet prefix, proving both the platform and the user endorsed the risk assessment

### Storage

Attestations are persisted in SQLite (`attestations` table) with:
- Transaction signature + Solana slot number
- Explorer URLs (Solana Explorer + Solscan, devnet cluster)
- Wallet address of the co-signer (if any)
- Full memo data JSON

### Treasury Wallet

- **Public key:** `5ez1L6GpFEbkeHwY1HuX21hvm5eurGusieLJPDh51Pqn`
- Signs all attestation transactions on devnet
- Funded with devnet SOL (free via faucet)

---

## 3. SOL Payments for Scan Packs

**Backend endpoints:** `GET /api/payer-address`, `POST /api/verify-solana-payment`, `GET /api/credits/{wallet}`  
**Network:** Solana **devnet**

### How It Works

Users can buy scan credit packs by paying SOL directly from their Phantom wallet — no credit card needed.

### Payment Flow

```
1. User connects Phantom wallet
2. Frontend fetches treasury address + SOL prices from /api/payer-address
3. User clicks "Pay X SOL" on a scan pack
4. Frontend builds a SystemProgram.transfer transaction:
   - From: user's wallet
   - To: treasury wallet
   - Amount: pack price in lamports
5. User signs via Phantom → transaction sent to devnet
6. Frontend waits for confirmation ("confirmed" commitment)
7. Frontend calls POST /api/verify-solana-payment with:
   - tx_signature, plan, wallet_address
8. Backend verifies on-chain:
   - Fetches transaction from devnet RPC
   - Confirms recipient = treasury address
   - Confirms amount matches plan price
   - Confirms sender = claimed wallet
9. Credits added to wallet's balance in SQLite
10. Frontend shows success + updated credit count
```

### Pricing (Devnet SOL)

| Pack | Scans | SOL Price | USD Equivalent |
|------|-------|-----------|----------------|
| Starter | 10 | 0.05 SOL | $1.99 |
| Standard | 50 | 0.20 SOL | $7.99 |
| Bulk | 200 | 0.60 SOL | $24.99 |

### Anti-Fraud Protections

- **On-chain verification** — backend independently fetches the transaction and verifies amount, recipient, and sender
- **Idempotency** — each transaction signature can only be redeemed once (checked against SQLite `payments` table)
- **Amount validation** — backend confirms the transferred lamports match the expected price

---

## 4. Wallet Risk Profile

**Backend endpoint:** `GET /api/wallet/{address}/risk-profile`  
**Frontend page:** `/wallet-risk`

### What It Does

Scans **every token** in a connected wallet and scores each for rug-pull risk, providing a portfolio-level risk assessment.

### How It Works

```
1. User navigates to Wallet Risk page
2. Frontend sends wallet address to /api/wallet/{address}/risk-profile
3. Backend queries Helius RPC: getTokenAccountsByOwner
   → Gets all SPL token accounts with non-zero balance
4. For each token (up to 20, concurrent with semaphore=3):
   a. collect_features(mint) — full 6-API data collection
   b. predict_rug_probability(features) — XGBoost ML scoring
   c. Build per-token result: name, symbol, balance, risk score, verdict, price, value
5. Aggregate portfolio metrics:
   - Portfolio risk score (value-weighted average)
   - Risk breakdown: DANGER / MODERATE / SAFE counts
   - Total estimated value
   - Danger exposure (USD value at risk)
6. Return sorted results (highest risk first) + summary message
```

### Response Shape

```json
{
  "wallet": "ABC...xyz",
  "totalTokens": 15,
  "scannedTokens": 15,
  "portfolioRiskScore": 32,
  "riskBreakdown": { "danger": 2, "moderate": 3, "safe": 10 },
  "totalEstimatedValue": 1234.56,
  "dangerExposure": 45.00,
  "tokens": [ /* per-token details */ ],
  "summary": "⚠️ 2 high-risk token(s) detected..."
}
```

---

## 5. Real-Time Solana Token Detection

**Backend:** Solana WebSocket listener in `_solana_ws_listener()`  
**Network:** Solana **mainnet** (via Helius WebSocket)

### How It Works

1. Backend connects to `wss://mainnet.helius-rpc.com/` via WebSocket
2. Subscribes to `logsSubscribe` for the **Token Program** (`TokenkegQEcnFiGhC7t8qkgAUNp84Xc7ELb8vxTG1VH6`)
3. Filters for `InitializeMint` log instructions → new token creation events
4. Resolves mint address from the transaction signature via `getTransaction` RPC
5. Immediately queues the mint for scanning → runs full 6-API data collection + ML scoring
6. Pushes the scored token to all connected WebSocket clients as a `new_token` event
7. Adds to the in-memory token cache (capped at 30 tokens)

### Resilience

- Auto-reconnects on WebSocket disconnection (10-second backoff)
- Queue-based processing (max 100 pending mints) prevents overload
- Gracefully degrades if Helius API key is not configured
