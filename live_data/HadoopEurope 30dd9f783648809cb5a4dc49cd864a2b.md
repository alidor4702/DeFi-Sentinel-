# HadoopEurope

[https://hackeurope.devpost.com/](https://hackeurope.devpost.com/)

# Ideas

## Idea 1:

## DeFi Sentinel — Deep Dive

### Snapshot

- **Name:** DeFi Sentinel
- **Subtitle:** AI Rug-Pull & Scam Detector for Solana
- **Tagline:** Real-time AI agent that monitors Solana token launches, scores rug-pull risk via on-chain + social signals, and sells monitoring subscriptions via Stripe.
- **Track:** Security (**€1,000 track prize**)
- **Challenges targeted:** Best Use of Data • Built on Solana • Best Stripe Integration
- **Prize ceiling:** **€14,500**
- **Judging scores (out of 5):** Startup Potential **5** • Technical Complexity **5** • Execution **4**
- **Composite score (weighted):** **4.7 / 5**
    - Weighting: Startup Potential 40% • Tech Complexity 30% • Execution 30%

---

### What it is (Plain English)

**In one sentence:**

A security tool that watches every new token launched on Solana in real-time and instantly predicts whether it’s likely a scam.

**The problem it solves:**

Solana has a high volume of rapid token launches; a meaningful share are rug pulls (creators drain liquidity / exit after hype). Most users and even some platforms cannot assess risk fast enough.

**How it works (high-level):**

It listens to on-chain launch events, enriches them with wallet + liquidity + holder data, adds social signals, and outputs an explainable **risk score** like “87% likely scam” backed by an ML model.

**Who uses it:**

- **B2B:** DEXs/aggregators and DeFi protocols (e.g., Raydium/Jupiter-style integrations) that want risk warnings in UI
- **B2C:** Traders who want real-time alerts via dashboard/Telegram

**Demo moment:**

Live dashboard shows real token launches streaming in; each token gets an instant risk score. Show a known recent scam and demonstrate it would have been flagged early.

---

### Technical Architecture (What it actually builds)

### 1) Real-time Solana Listener

- WebSocket listener connected to Solana RPC / indexer
- Detect token launches and pool creations from:
    - DEX launch flows (Raydium / Jupiter routing signals)
    - Launch platforms (e.g., pump.fun patterns)
- Emits events into a processing pipeline (queue + DB)

### 2) Data Enrichment Pipeline (On-chain + Meta)

For each new token/pool:

- **Contract / token config checks**
    - Mint authority status
    - Freeze authority status
    - Token-2022 vs SPL Token program signals
- **Liquidity + LP safety**
    - LP lock status (or absence of locks)
    - Liquidity concentration
- **Holder & distribution risk**
    - Holder concentration (top holders %)
    - New wallet clusters
    - Rapid accumulation patterns
- **Wallet graph analysis**
    - Developer wallet relationships
    - Known scam cluster proximity
    - Funding source patterns

(Uses an indexer API such as Helius for fast enrichment.)

### 3) Multi-signal Risk Scoring Engine

Signals combined into a single risk score and explanation:

- **On-chain heuristics**
    - Rug-pull primitives (authority control, liquidity extractability)
    - Suspicious transaction sequences
    - Concentration and wallet clustering
- **Social signals**
    - X/Twitter signals: account age, bot-like activity, sentiment spikes, reused copy
    - Mention velocity vs. organic growth
- **Behavioral features**
    - Early trade timing anomalies
    - Bundled buys/sells
    - Wallet reuse across launches

Outputs:

- Risk score (0–100)
- “Why” explanation (top contributing features)
- Confidence indicator

### 4) ML Classifier (Rug-pull Prediction)

- Train a supervised model on labeled rug-pull / legit launches
- Feature set combines:
    - Code/config features (authority flags, program metadata)
    - Transaction behavior features (early liquidity moves, holder growth)
    - Graph features (wallet connectivity, cluster similarity)
- Model choices:
    - XGBoost / logistic regression for speed + interpretability
    - Optional embeddings/graph model later; hackathon scope should prioritize reliability

### 5) Product Surface Area

**Dashboard**

- Live token launch feed (streaming)
- Risk heatmaps (by time / category)
- Wallet graph visualizations
- Historical accuracy metrics (precision/recall style, or “caught X of Y known scams”)

**Alerts**

- Webhooks / API alerts for B2B
- Telegram / email alerts for B2C

---

### Monetization (Stripe)

**Core business model:** monitoring subscriptions

- **API subscription for protocols/trading teams**
    - Tiered plans (e.g., Basic/Pro/Enterprise)
    - Metered usage (risk checks per token, alerts delivered, webhook calls)
- **Stripe implementation**
    - Stripe Checkout for subscription purchase
    - Metered billing for usage-based pricing
    - Customer portal for upgrades/cancellations
    - Webhook-driven entitlement enforcement (plan limits)

---

### Solana Native Bonus (Confidential Transfers)

- Optional privacy-preserving subscription payments using **Token-2022 Confidential Transfers**
- “Bonus points” alignment: privacy-focused payment path for premium alerts
- Note: availability may vary by cluster / program status; scope it as optional

---

### 48-Hour Execution Plan

**0–8h:**

Solana listener + token data pipeline + DB schema + Helius integration

**8–18h:**

Risk scoring model (train on labeled data) + social scraping + API endpoints

**18–28h:**

Stripe subscription flow + (optional) Confidential Transfers integration

**28–40h:**

Dashboard UI — live feed, heatmaps, wallet graphs, alerting

**40–48h:**

Polish, testing, demo prep, pitch, edge cases

---

### Startup Case (Why this can be a real company)

- Clear, recurring pain: scam detection needs to happen **before** users buy
- Competitors validate demand, but many are rule-based; differentiation is:
    - Real-time monitoring
    - ML + multi-signal fusion
    - Strong B2B integration story
- Obvious buyers:
    - DeFi frontends (risk warnings reduce user losses and reputational risk)
    - Power traders/funds (alerts and monitoring)

---

### Why it wins (Judges & narrative fit)

- **Security track:** directly aligned (fraud prevention)
- **Best Use of Data:** rich multi-source fusion (on-chain + social + graphs)
- **Built on Solana:** real-time Solana-native monitoring + optional Token-2022 privacy
- **Best Stripe Integration:** natural SaaS monetization with metered billing
- Strong demo: live launches → instant scores → explainability + alerts

---

### Key Risks / Constraints

- Multi-system complexity (listener + enrichment + ML + social + Stripe + UI)
- Need reliable labeled rug-pull dataset to train quickly (can start with heuristic labels + a small curated set)
- Confidential Transfers availability may be limited; keep it optional to avoid critical path risk

---

### Tech Stack (implementation)

- **Backend:** Python (FastAPI) or Rust services for high-throughput pieces
- **Solana:** web3.js, Solana RPC + indexer (e.g., Helius), WebSockets
- **ML:** scikit-learn / XGBoost
- **Social:** Tweepy / snscrape-style ingestion
- **Payments:** Stripe SDK with metered subscriptions
- **Privacy (optional):** Token-2022 Confidential Transfers
- **Frontend:** React dashboard + D3.js + WebSocket live updates

---

### Deliverables Checklist (what to ship)

- [ ]  Live launch listener (streaming feed)
- [ ]  Enrichment pipeline (authority + liquidity + holders + wallet graph features)
- [ ]  Risk scoring endpoint returning score + explanation
- [ ]  Alerting (webhook + Telegram)
- [ ]  Stripe subscription + metered usage enforcement
- [ ]  Dashboard (feed + heatmap + graph viz + basic metrics)
- [ ]  Demo script with one known scam case study + live stream view

claude research: [https://claude.ai/public/artifacts/58b815b6-f0b7-4dd9-bb94-7a13edc87677](https://claude.ai/public/artifacts/58b815b6-f0b7-4dd9-bb94-7a13edc87677)

hello world - LGTM

# RugRadar

## Data

RugCheck API

RugCheck reads on-chain data and applies **fixed rules** that add penalty points:

| Check | What it looks at | Example penalty |
| --- | --- | --- |
| **Mint Authority** | Can the creator print unlimited tokens? | High penalty |
| **Freeze Authority** | Can the creator freeze your wallet? | High penalty |
| **Top Holder Concentration** | Do 10 wallets own >50% of supply? | +1,054 pts |
| **Single Holder** | Does 1 wallet own a huge chunk? | +2,665 pts |
| **Low Liquidity** | Is there <$X in the pool? | +2,999 pts |
| **LP Unlocked** | Is the liquidity unlockable by the creator? | High penalty |
| **Low LP Providers** | Only 1-2 people providing liquidity? | +500 pts |
| **Missing Metadata** | No name/image/website? | Penalty |
| **Insider Graph** | Connected wallets buying together? | Penalty |
| **Creator History** | Has the creator made other tokens? | Checked |
| **Transfer Fee** | Hidden tax on every trade? | Penalty |

**Score = sum of all penalty points.** Score of 1 = clean. Score of 72,000 = disaster.

https://github.com/DeFiLabX/SolRPDS/tree/main

[2504.07132v1.pdf](2504.07132v1.pdf)

## Repartition

### Team Roles

| Person | Role | Focus |
| --- | --- | --- |
| **P1** | ML Engineer | Model + scoring engine |
| **P2** | Backend Dev | Solana listener + API + ML |
| **P3** | Frontend Dev | Dashboard + demo |
| **P4** | Infra/Biz | Stripe + pitch + glue |

---

### Phase 1: Foundation (Hours 0–6)

| Person | Tasks | Deliverable |
| --- | --- | --- |
| **P1** | 1. Improve train_solrpds.py — add better features (duration, ratios, log transforms), try XGBoost, tune hyperparams. 2. Build the combined scoring function (ML + heuristic rules) | model.joblib + `score_token()` function |
| **P2** | 1. Set up project skeleton (FastAPI backend). 2. Build Solana WebSocket listener (detect new pool creations via Helius webhooks or WSS). 3. Set up Helius API integration for real-time enrichment | Working listener that prints new tokens to console |
| **P3** | 1. Set up Next.js/React dashboard scaffold. 2. Build the live token feed UI component (table/cards). 3. Design risk score display (color-coded 0–100 gauge) | Dashboard shell with mock data |
| **P4** | 1. Set up Stripe account + products (Free/Pro/Enterprise tiers). 2. Implement Stripe Checkout + subscription flow. 3. Set up project repo, deployment (Vercel/Railway) | Working payment page |

**Sync at hour 6:** Everyone demos their piece. Agree on API contract (JSON format between backend → frontend).

---

### Phase 2: Integration (Hours 6–14)

| Person | Tasks | Deliverable |
| --- | --- | --- |
| **P1** | 1. Build /api/score endpoint — takes a mint address, returns risk score + explanation. 2. Add heuristic rules (mint authority, freeze authority, holder concentration). 3. Run full enrichment script (`--skip_rpc` mode, ~2 min) for demo data | Scoring API endpoint working |
| **P2** | 1. Connect listener → scoring pipeline → database/CSV. 2. Build `/api/tokens` endpoint (returns latest scored tokens). 3. Build `/api/token/{mint}` endpoint (detailed view). 4. Add Telegram/webhook alert system | API serving real scored tokens |
| **P3** | 1. Connect dashboard to real API. 2. Build risk heatmap / chart visualization. 3. Build token detail page (shows why it was flagged). 4. Add alert configuration UI | Live dashboard with real data |
| **P4** | 1. Integrate Stripe into dashboard (paywall for Pro features). 2. Build landing page / marketing site. 3. Start pitch deck (10 slides max). 4. Set up metered billing for API access | Stripe integrated, pitch draft |

**Sync at hour 14:** Full integration test. Can you: launch dashboard → see tokens streaming → click one → see risk score → sign up with Stripe?

---

### Phase 3: Polish & Demo (Hours 14–20)

| Person | Tasks | Deliverable |
| --- | --- | --- |
| **P1** | 1. Add "explainability" — top 3 reasons for each risk score. 2. Test with known rug-pull examples (find 3–5 famous ones). 3. Build accuracy metrics display (precision/recall on test set) | Model with explanations |
| **P2** | 1. Error handling, rate limiting, caching. 2. Deploy backend to production. 3. Load test with real Solana data | Stable deployed API |
| **P3** | 1. Polish UI/UX, animations, responsive design. 2. Add "historical accuracy" section. 3. Build demo walkthrough flow | Polished dashboard |
| **P4** | 1. Finalize pitch deck. 2. Record backup demo video (in case live demo fails). 3. Prepare 3 demo scenarios | Pitch ready |

---

### Phase 4: Demo Prep (Hours 20–23)

| Everyone together |  |
| --- | --- |
| **Hour 20–21** | Full dry run of the demo. Fix any bugs. |
| **Hour 21–22** | Practice pitch 3x. Time it. Cut anything over limit. |
| **Hour 22–23** | Final deploy. Prepare backup plan (screenshots/video if live fails). Rest. |

---

### 🎯 The Demo Script (3–5 minutes)

1. **"The Problem"** (30s) — Show a real rug-pull news article. "X million lost."
2. **Dashboard live** (60s) — Tokens streaming in. Point at risk scores. "This one is 87% likely a scam — here's why."
3. **Deep dive** (60s) — Click a flagged token. Show: mint authority active ✅, pool duration 2 hours 🚩, top holder owns 94% 🚩, liquidity removed 10x what was added 🚩.
4. **Historical proof** (30s) — "We trained on 116K liquidity pools from 2021–2024. Our model catches 94% of rug pulls."
5. **Stripe** (30s) — Show subscription flow. "Protocols pay $99/mo for API access. Traders pay $9/mo for alerts."
6. **Business case** (30s) — TAM, revenue model, why now.

---

### ⚡ Critical Path (what blocks everything)

- 
- 
- 
- 

### 🛡️ Risk Mitigation

| Risk | Backup plan |
| --- | --- |
| WebSocket listener doesn't work | Pre-load 100 recent tokens, simulate "live" feed |
| Model accuracy is low | Use the existing 94% model, don't over-engineer |
| Stripe integration takes too long | Use Stripe Payment Links (no code needed) |
| Live demo fails | Have a recorded video ready |

Want me to start building any of these pieces now? The most impactful first step would be improving the ML model and building the scoring API.

## Data

# DeFi Sentinel — ML Feature Set & Data Collection Reference

## How to read this document

Every feature below feeds into the ML classifier. They're grouped by category, with the **data source** and **API call** listed for each. Priority indicates hackathon importance:

- 🔴 **Critical** — must have for MVP, biggest signal weight
- 🟡 **Important** — strong signal, build if time allows
- 🟢 **Nice-to-have** — differentiator, but can be heuristic-only at first

---

## Category 1: Token Contract / Mint Configuration

These are the first things you check — they're fast, cheap, and high-signal.

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 1.1 | `mint_authority_active` | bool | 🔴 | Can creator mint more tokens? true = infinite dilution risk |
| 1.2 | `freeze_authority_active` | bool | 🔴 | Can creator freeze wallets (block selling)? true = honeypot risk |
| 1.3 | `metadata_mutable` | bool | 🔴 | Can token name/image/links be changed after launch? |
| 1.4 | `token_program` | categorical | 🟡 | SPL Token vs Token-2022 — Token-2022 has extensions that can hide risks |
| 1.5 | `has_transfer_fee` | bool | 🟡 | Token-2022 extension: hidden tax on every transfer |
| 1.6 | `has_permanent_delegate` | bool | 🔴 | Token-2022 extension: someone can move tokens OUT of any wallet |
| 1.7 | `has_transfer_hook` | bool | 🟡 | Token-2022 extension: custom code runs on every transfer (can block sells) |
| 1.8 | `total_supply` | float | 🟡 | Total token supply (Pump.fun = always 1B, others vary) |
| 1.9 | `decimals` | int | 🟢 | Unusual decimals can be a signal |
| 1.10 | `update_authority_revoked` | bool | 🟡 | Is metadata permanently locked? |

**Data source:** Helius DAS API
**API call:** `getAsset(mintAddress)` → returns authorities, extensions, metadata mutability
**Backup:** Solana RPC `getAccountInfo` on the mint account → decode the Mint struct directly

---

## Category 2: Liquidity Pool Configuration

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 2.1 | `lp_tokens_burned` | bool | 🔴 | Were LP tokens sent to a burn address? burned = creator can't remove liquidity |
| 2.2 | `lp_tokens_locked` | bool | 🔴 | Are LP tokens in a time-lock contract? |
| 2.3 | `lp_lock_duration_hours` | float | 🟡 | How long is the lock? Short locks (< 24h) are suspicious |
| 2.4 | `initial_liquidity_sol` | float | 🔴 | How much SOL was added as initial liquidity |
| 2.5 | `initial_liquidity_usd` | float | 🔴 | USD value of initial liquidity |
| 2.6 | `liquidity_ratio` | float | 🟡 | Liquidity relative to market cap — very low = easy to manipulate |
| 2.7 | `pool_type` | categorical | 🟡 | Raydium / PumpSwap / Orca / Meteora — different risk profiles |
| 2.8 | `bonding_curve_complete` | bool | 🟡 | For Pump.fun: has the token graduated to open trading? |
| 2.9 | `time_to_graduation_mins` | float | 🟡 | How fast did it graduate? Very fast can mean coordinated buying |
| 2.10 | `creator_lp_percentage` | float | 🔴 | % of LP tokens still held by creator (if not burned/locked) |

**Data source (LP burn/lock):** Helius parsed transaction history — look for transfers of LP tokens to known burn addresses (e.g., `1111111111111111111111111111111111`) or lock programs
**Data source (liquidity):** GeckoTerminal pool endpoint or Birdeye — `reserve_in_usd`, `volume_usd`**Data source (Pump.fun bonding):** Bitquery API or PumpPortal WebSocket — bonding curve progress, graduation status

---

## Category 3: Holder Distribution

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 3.1 | `top1_holder_pct` | float | 🔴 | % of supply held by the #1 holder (exclude known pools/burns) |
| 3.2 | `top5_holder_pct` | float | 🔴 | % of supply held by top 5 holders |
| 3.3 | `top10_holder_pct` | float | 🔴 | % of supply held by top 10 holders |
| 3.4 | `top20_holder_pct` | float | 🟡 | % of supply held by top 20 holders |
| 3.5 | `total_holders` | int | 🔴 | Total unique holders |
| 3.6 | `holder_growth_rate_5min` | float | 🟡 | How fast are new holders appearing? |
| 3.7 | `gini_coefficient` | float | 🟡 | Distribution inequality score (0 = equal, 1 = one holder has everything) |
| 3.8 | `creator_holding_pct` | float | 🔴 | % of supply still in the deployer wallet |
| 3.9 | `holders_with_over_1pct` | int | 🔴 | Count of wallets holding > 1% supply |
| 3.10 | `median_holder_balance` | float | 🟢 | Median balance — very low with high concentration = retail bait |

**Data source:** Helius `getTokenAccounts(mint)` → paginate through ALL token accounts → aggregate by owner
**Note:** You must exclude known addresses: the bonding curve address, the LP pool address, burn addresses, and any lock contract addresses. Otherwise "top holder" will be the pool itself.

---

## Category 4: Deployer Wallet Analysis

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 4.1 | `deployer_wallet_age_days` | float | 🔴 | How old is the wallet that created the token? |
| 4.2 | `deployer_sol_balance` | float | 🟡 | Current SOL balance of deployer |
| 4.3 | `deployer_previous_tokens` | int | 🔴 | How many tokens has this wallet deployed before? |
| 4.4 | `deployer_prev_token_survival_rate` | float | 🔴 | Of previous tokens, what % still have liquidity after 24h? |
| 4.5 | `deployer_prev_avg_lifespan_hours` | float | 🟡 | Average lifespan of deployer's previous tokens |
| 4.6 | `deployer_total_tx_count` | int | 🟡 | Total transaction history length — very low = fresh wallet |
| 4.7 | `deployer_funded_by_cex` | bool | 🟡 | Was the deployer funded from a known CEX (Binance, Coinbase)? More legit signal |
| 4.8 | `deployer_funded_by_mixer` | bool | 🔴 | Funded via mixing/tumbling service? High risk |
| 4.9 | `deployer_is_contract` | bool | 🟡 | Is deployer a program-owned account? |
| 4.10 | `deployer_linked_to_known_scam` | bool | 🔴 | Has this wallet interacted with wallets flagged in known rug pulls? |

**Data source:** Helius `getSignaturesForAddress(deployerWallet)` → transaction history
**Data source:** Helius parsed transactions → trace funding source backwards
**Data source:** For previous tokens — search `getAssetsByAuthority(deployerWallet)` or filter token creation instructions from tx history
**Labeled scam wallets:** SolRPDS dataset (GitHub: DeFiLabX/SolRPDS) provides labeled rug-pull deployer addresses

---

## Category 5: Early Trading Behavior (first 5–30 minutes)

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 5.1 | `buy_sell_ratio_5min` | float | 🔴 | Buys vs sells in first 5 mins — all buys, no sells = coordinated accumulation |
| 5.2 | `unique_buyers_5min` | int | 🔴 | Number of unique buying wallets in first 5 min |
| 5.3 | `unique_sellers_5min` | int | 🟡 | Number of unique selling wallets in first 5 min |
| 5.4 | `avg_buy_size_sol` | float | 🟡 | Average buy size — unusually uniform = bot activity |
| 5.5 | `buy_size_stddev` | float | 🟡 | Standard deviation of buy sizes — very low = coordinated |
| 5.6 | `largest_single_buy_pct` | float | 🔴 | Largest single buy as % of supply |
| 5.7 | `bundled_buys_count` | int | 🔴 | Buys in the same transaction/block as token creation |
| 5.8 | `bundled_buy_pct_supply` | float | 🔴 | % of supply acquired in bundled buys (same-block as creation) |
| 5.9 | `price_change_5min` | float | 🟡 | Price change in first 5 min |
| 5.10 | `price_change_30min` | float | 🟡 | Price change in first 30 min |
| 5.11 | `volume_5min_usd` | float | 🟡 | Trading volume in first 5 min |
| 5.12 | `tx_count_first_block` | int | 🔴 | Transactions in the same block as token creation — high = sniping |
| 5.13 | `time_to_first_sell_seconds` | float | 🟡 | How long until the first sell? Very fast large sells = dump |

**Data source (trades):** GeckoTerminal `/pools/{pool}/trades` or Bitquery trades subscription
**Data source (bundled buys):** Helius parsed transactions for the creation block — check if buy instructions are in the same tx as the create instruction
**Data source (price):** GeckoTerminal OHLCV endpoint (minute candles) or Birdeye price WebSocket

---

## Category 6: Wallet Cluster / Graph Features

This is where you go beyond what RugCheck does. These features catch coordinated wallet networks.

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 6.1 | `top10_funded_same_source` | int | 🔴 | Of top 10 holders, how many were funded by the same wallet? |
| 6.2 | `top10_funded_within_1h` | int | 🔴 | Of top 10 holders, how many received SOL within 1 hour of each other? |
| 6.3 | `top10_wallet_avg_age_days` | float | 🟡 | Average age of top 10 holder wallets |
| 6.4 | `top10_new_wallet_pct` | float | 🔴 | % of top 10 holders that are < 24h old wallets |
| 6.5 | `buyer_wallet_avg_age_days` | float | 🟡 | Average age of all early buyer wallets |
| 6.6 | `common_funding_source_count` | int | 🔴 | Number of distinct "source" wallets that funded multiple buyers |
| 6.7 | `max_cluster_size` | int | 🔴 | Largest group of holders funded from the same source |
| 6.8 | `cluster_holding_pct` | float | 🔴 | % of supply controlled by the largest connected wallet cluster |
| 6.9 | `deployer_to_holder_hops` | float | 🟡 | Avg transaction hops from deployer to top holders (1 hop = direct, more = layered) |
| 6.10 | `known_scam_cluster_overlap` | float | 🔴 | % of buyer wallets that appear in known scam wallet clusters from SolRPDS |

**Data source:** Helius `getSignaturesForAddress` + parsed transactions for each top holder → trace backwards to funding source
**Algorithm:**

1. Get top 20 holders from Category 3
2. For each holder, get their recent transaction history
3. Find their first SOL funding transaction (who sent them SOL?)
4. Build a graph: funding_source → holder
5. Detect clusters (connected components with shared funding sources)
6. Compute features from the graph

**This is computationally expensive** — for the hackathon, start with top 10–20 holders only. In production, expand to top 50+.

---

## Category 7: Social Signals

None of the current Solana tools do this. It's a major differentiator.

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 7.1 | `has_twitter` | bool | 🔴 | Does the token metadata include a Twitter link? |
| 7.2 | `twitter_account_age_days` | float | 🔴 | Age of the linked Twitter account |
| 7.3 | `twitter_follower_count` | int | 🟡 | Follower count |
| 7.4 | `twitter_following_ratio` | float | 🟡 | Followers / following — very low = bought followers |
| 7.5 | `twitter_tweet_count` | int | 🟡 | Total tweets — brand new accounts with few tweets |
| 7.6 | `twitter_has_profile_pic` | bool | 🟢 | Default avatar = low effort |
| 7.7 | `has_telegram` | bool | 🔴 | Does token metadata include a Telegram group? |
| 7.8 | `has_website` | bool | 🔴 | Does token metadata include a website? |
| 7.9 | `website_domain_age_days` | float | 🟡 | WHOIS lookup — domain registered yesterday? |
| 7.10 | `website_is_free_hosting` | bool | 🟡 | Is it on a free subdomain (netlify, vercel, github.io)? |
| 7.11 | `social_links_reused` | bool | 🔴 | Are the same social links used across multiple recent token launches? |
| 7.12 | `metadata_uri_is_valid` | bool | 🟡 | Does the token metadata URI actually resolve? |
| 7.13 | `metadata_image_is_unique` | bool | 🟢 | Is the token image unique or reused from another token? |

**Data source (social links):** Token metadata URI → fetch the JSON from Arweave/IPFS → extract twitter, telegram, website fields
**Data source (Twitter):** Twitter/X API v2 (if you have access) or scraping — get account creation date, follower count, tweet count
**Data source (Website):** WHOIS API (e.g., whoisxml API free tier) → domain registration date
**Data source (reuse detection):** Your own database — index social links from every token you scan, flag duplicates

---

## Category 8: Metadata & Name Signals

| # | Feature | Type | Priority | What it means |
| --- | --- | --- | --- | --- |
| 8.1 | `name_contains_celeb` | bool | 🟡 | Does the name reference a celebrity/public figure? Common scam pattern |
| 8.2 | `name_contains_trending` | bool | 🟡 | References trending topic/meme? Could be hype-jacking |
| 8.3 | `name_similarity_to_existing` | float | 🟡 | Levenshtein distance to known tokens — typosquatting detection |
| 8.4 | `symbol_length` | int | 🟢 | Unusual symbol lengths |
| 8.5 | `description_length` | int | 🟢 | Very short or empty descriptions |
| 8.6 | `metadata_hosted_on` | categorical | 🟢 | Arweave (more permanent) vs IPFS (can be unpinned) vs HTTP (can vanish) |

**Data source:** Token metadata URI → fetch and parse JSON
**Data source (similarity):** Your own token name index built from scan history

---

## Summary: Feature Count by Category

| Category | Feature Count | Priority Breakdown |
| --- | --- | --- |
| 1. Contract/Mint Config | 10 | 4🔴  4🟡  2🟢 |
| 2. Liquidity Pool | 10 | 4🔴  5🟡  1🟢 |
| 3. Holder Distribution | 10 | 5🔴  3🟡  2🟢 |
| 4. Deployer Wallet | 10 | 4🔴  4🟡  2🟢 |
| 5. Early Trading | 13 | 5🔴  7🟡  1🟢 |
| 6. Wallet Clusters | 10 | 6🔴  3🟡  1🟢 |
| 7. Social Signals | 13 | 4🔴  5🟡  4🟢 |
| 8. Metadata/Name | 6 | 0🔴  3🟡  3🟢 |
| **TOTAL** | **82** | **32🔴  34🟡  16🟢** |

---

## Data Source Summary

| Source | What it gives you | Cost | Latency |
| --- | --- | --- | --- |
| **Helius DAS API** | Token metadata, authorities, extensions, holder lists, parsed tx history | Free tier: 50K credits/day. Paid: $49+/mo | ~200ms per call |
| **Helius WebSockets / Webhooks** | Real-time new token detection, account changes | Included with API key | Sub-second |
| **Helius getTokenAccounts** | Full holder list for any token | Part of DAS API credits | ~500ms–2s (depends on holder count) |
| **GeckoTerminal API** | OHLCV price candles, pool data, trades, volume | Free: 10 calls/min. Paid via CoinGecko: $129+/mo | ~300ms, slight indexing delay for new tokens |
| **PumpPortal WebSocket** | Pump.fun token creations, trades, bonding curve | Free (data API) | Real-time streaming |
| **Bitquery GraphQL** | Pump.fun lifecycle, trades, bonding curve progress, holder tracking | Free tier: limited. Paid: $100+/mo | ~1-5s for queries, real-time for subscriptions |
| **Twitter/X API** | Account age, followers, tweets, profile data | Free tier: very limited. Basic: $100/mo | ~200ms per call |
| **WHOIS API** | Domain registration date, registrar | whoisxmlapi.com: 500 free lookups then $30+/mo | ~500ms |
| **SolRPDS Dataset** | Labeled rug-pull/legit token data for training | Free (CC BY 4.0 on GitHub) | N/A (offline dataset) |

---

## Data Collection Pipeline (execution order)

For each new token detected:

```
SECOND 0-1:  Token creation detected
             Source: Helius webhook or PumpPortal WebSocket
             Capture: mint address, deployer wallet, creation tx signature, timestamp

SECOND 1-2:  Contract check (parallel calls)
             Source: Helius getAsset(mint)
             Capture: Cat 1 features (authorities, extensions, metadata)

             Source: Fetch metadata URI (arweave/IPFS)
             Capture: Cat 7 features (social links), Cat 8 features (name/description)

SECOND 2-5:  Deployer analysis
             Source: Helius getSignaturesForAddress(deployer)
             Capture: Cat 4 features (wallet age, previous tokens, history)

             Source: Helius getAssetsByAuthority(deployer)
             Capture: deployer_previous_tokens, past token performance

SECOND 3-5:  Liquidity check
             Source: GeckoTerminal pool lookup or Helius tx parsing
             Capture: Cat 2 features (LP status, initial liquidity)

SECOND 5-10: Holder snapshot (initial)
             Source: Helius getTokenAccounts(mint)
             Capture: Cat 3 features (holder counts, concentration)

SECOND 5-15: Wallet cluster analysis
             Source: Helius getSignaturesForAddress for each top holder
             Capture: Cat 6 features (funding sources, clusters)

SECOND 10-30: Social verification (async, non-blocking)
              Source: Twitter API, WHOIS API
              Capture: Cat 7 features (account ages, followers)

ONGOING (5min, 15min, 30min): Trading behavior
              Source: GeckoTerminal trades + OHLCV, Bitquery
              Capture: Cat 5 features (buy/sell patterns, price action)
              Update risk score as new data arrives
```

---

## ML Model Architecture

### Training Data

- **SolRPDS dataset** — 62,895 labeled liquidity pools (rug vs legit)
- **Self-labeled data** — tokens you scan that rug within 24h = positive, tokens still active after 7 days = negative
- Label ratio will be heavily imbalanced (90%+ scams on Pump.fun) — use SMOTE or class weights

### Model Choice (hackathon)

- **Primary: XGBoost or Gradient Boosting** — fast training, handles mixed feature types, built-in feature importance for explainability
- **Secondary: Random Forest** — ensemble baseline, good for comparison
- **NOT recommended for hackathon:** deep learning, GNNs, transformers — too complex to train/debug in 48h

### Feature Engineering Notes

- Normalize all percentage features to 0-1
- Log-transform skewed distributions (SOL balances, holder counts, volumes)
- One-hot encode categorical features (pool_type, token_program, metadata_hosted_on)
- Handle missing data: social features will be null for tokens without Twitter — use a "has_twitter" binary + impute missing values with median
- Time-decay: features from 5min ago matter more than features from 30min ago for the trading behavior category

### Output

- **Risk score: 0–100** (probability from model × 100)
- **Confidence: low / medium / high** (based on how many feature categories have data — a score with all 8 categories populated is high confidence, a score with only Cat 1-3 is low confidence)
- **Top 3 risk factors** (from XGBoost feature importance or SHAP values — e.g., "88% of supply held by wallets funded from same source", "deployer has launched 7 tokens in last 24h, all dead", "Twitter account created 2 days ago")

---

## Hackathon Priority: What to Build First

### Phase 1 (Hours 0-12): Core features — enough to score

- Cat 1: All 🔴 features (mint auth, freeze auth, permanent delegate, metadata mutable)
- Cat 2: LP burned/locked, initial liquidity
- Cat 3: Top holder concentration, total holders, creator holdings
- Cat 4: Deployer wallet age, previous tokens
- **Train initial model on SolRPDS with these ~15 features**

### Phase 2 (Hours 12-24): Behavioral + cluster features

- Cat 5: Buy/sell ratio, bundled buys, unique buyers
- Cat 6: Top 10 funded from same source, new wallet %, cluster size
- **Retrain model with ~25-30 features**

### Phase 3 (Hours 24-36): Social + polish

- Cat 7: Twitter account age, has_telegram, has_website, social link reuse
- Cat 8: Name similarity, celeb detection
- **Final model with ~40+ features**

### Phase 4 (Hours 36-48): Integration + demo

- Wire model into real-time pipeline
- Dashboard showing live scores
- Telegram alert bot
- Demo script with known scam case study

# API KEYS

Helius API key: bf78d53e-daf7-4d2f-98c5-8f34e80d339a

BitQuery API key: aa079b2e-3fb6-4539-b41b-abf26abe951e

X bearer key: AAAAAAAAAAAAAAAAAAAAAM8K7wEAAAAAJ6Ci8AxF2FF0IhlSLeuruozoZiM%3DpkGl0iadyodFpLvPudkoOxrdyXhCulZDBZcBIT2aInA5JRCRmP