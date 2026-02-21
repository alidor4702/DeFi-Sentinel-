# DeFi Sentinel — Live Feature Specification

**For:** Backend Developer  
**Purpose:** Every feature the backend must query when a new Solana token is detected  
**Total features:** 110  
**Target latency:** < 600ms (all API calls in parallel)

---

## Architecture Overview

```
New token detected (Solana websocket)
        │
        ├──► Helius DAS API ──────────► 22 features  (~100ms)
        ├──► Creator Wallet (Helius) ──► 6 features   (~200ms)
        ├──► RugCheck API ────────────► 18 features  (~300ms)
        ├──► GoPlus Security API ─────► 24 features  (~500ms)
        ├──► GeckoTerminal API ───────► 25 features  (~500ms)
        └──► Jupiter API ────────────► 5 features   (~100ms)
                                          │
                              Compute 10 derived features (~0ms)
                                          │
                                  110-dim feature vector
                                          │
                                    XGBoost model
                                          │
                                 Risk score (0–1)
```

All 6 API calls are **independent** — fire them in parallel. Wall-clock time is limited by the slowest response (~500ms).

---

## 1. Helius DAS API — Token Metadata (22 features)

**Endpoint:** `POST https://mainnet.helius-rpc.com/?api-key={KEY}`  
**Method:** `getAsset` with `{ id: mint_address }`  
**Auth:** API key (we have one)  
**Rate limit:** 50 req/s on paid plan  
**Latency:** ~100ms

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 1 | `mint_address` | string | Token mint address (input, not queried) |
| 2 | `token_name` | string | Name from on-chain metadata. Rugs often copy known token names. |
| 3 | `token_symbol` | string | Symbol. Duplicates of SOL, USDC, BONK = red flag. |
| 4 | `token_decimals` | int | Standard is 6 or 9. Weird values (0, 18) = suspicious. |
| 5 | `token_supply` | float | Total supply. Extreme values flag pump-and-dump schemes. |
| 6 | `mint_authority` | string/null | Address that can mint more tokens. Null = revoked. |
| 7 | `mint_authority_revoked` | bool | `true` if mint_authority is null. Revoked = slightly safer. |
| 8 | `freeze_authority` | string/null | Address that can freeze holder accounts. |
| 9 | `freeze_authority_revoked` | bool | `true` if freeze_authority is null. |
| 10 | `update_authority` | string/null | Address that can change metadata (name, image, links). |
| 11 | `is_mutable` | bool | Metadata can be changed after launch. Allows bait-and-switch. |
| 12 | `token_standard` | string | `Fungible`, `FungibleAsset`, or `NonFungible`. |
| 13 | `token_program` | string | `TokenkegQ...` (legacy SPL) vs `Token-2022` (new). |
| 14 | `creation_timestamp` | datetime | When the mint account was created on-chain. |
| 15 | `metadata_uri` | string | URI pointing to off-chain JSON. Empty or broken = red flag. |
| 16 | `metadata_uri_reachable` | bool | HTTP GET the URI — does it return valid JSON? |
| 17 | `has_image` | bool | Off-chain metadata contains an `image` field. |
| 18 | `has_description` | bool | Off-chain metadata contains a `description` field. |
| 19 | `has_website` | bool | External links section contains a website URL. |
| 20 | `has_twitter` | bool | Social links include Twitter/X. |
| 21 | `has_telegram` | bool | Social links include Telegram. |
| 22 | `creator_address` | string | The wallet that deployed the token. Used for wallet analysis. |

**Implementation notes:**
- `metadata_uri_reachable`: requires an HTTP GET to the URI. Set a 2s timeout. If it fails, set to `false`.
- `has_image/description/website/twitter/telegram`: parse the JSON returned from the metadata URI.
- `creator_address`: extract from the `authorities` or `creators` array in the DAS response.

---

## 2. Creator Wallet Analysis (Helius) — 6 features

**Endpoints:**
- `getBalance` — SOL balance
- `getSignaturesForAddress` — transaction history
- `getAssetsByOwner` — tokens/NFTs owned

**Auth:** Same Helius API key  
**Latency:** ~200ms (2-3 calls)

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 23 | `creator_sol_balance` | float | SOL balance of creator wallet. Low (< 0.1 SOL) = disposable wallet. |
| 24 | `creator_wallet_age_hours` | float | Hours since first transaction. Brand new wallet = suspicious. |
| 25 | `creator_token_count` | int | Number of tokens this wallet has created. Serial deployers = serial ruggers. |
| 26 | `creator_tx_count` | int | Total transaction count. Fresh wallet with < 10 txs = red flag. |
| 27 | `creator_prev_tokens_rugged` | int | Cross-reference with our database: how many of this wallet's past tokens died. |
| 28 | `creator_nft_count` | int | NFTs held. Real developers tend to have wallet history. |

**Implementation notes:**
- `creator_wallet_age_hours`: get oldest signature from `getSignaturesForAddress` with `limit: 1` and `before: null`. Compare timestamp to now.
- `creator_token_count`: from `getAssetsByOwner`, count assets where the creator is also the authority.
- `creator_prev_tokens_rugged`: requires our own database of past predictions. Initially set to 0, build up over time.

---

## 3. RugCheck API — 18 features

**Endpoint:** `GET https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary`  
**Auth:** None required  
**Rate limit:** ~3 req/s (use 0.3s delay between requests)  
**Latency:** ~300ms

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 29 | `rc_score` | int | Overall risk score 0–1000. Higher = safer. |
| 30 | `rc_risk_level` | string | `"Good"`, `"Warning"`, or `"Danger"`. |
| 31 | `rc_risk_count` | int | Number of individual risk flags triggered. |
| 32 | `rc_mint_authority_disabled` | bool | Mint authority has been revoked. |
| 33 | `rc_freeze_authority_disabled` | bool | Freeze authority has been revoked. |
| 34 | `rc_mutable_metadata` | bool | Token metadata can still be changed. |
| 35 | `rc_top10_holder_pct` | float | % of total supply held by top 10 wallets. |
| 36 | `rc_top_holder_pct` | float | % held by single largest wallet. |
| 37 | `rc_lp_locked` | bool | Liquidity pool tokens are locked in a locker contract. |
| 38 | `rc_lp_lock_pct` | float | What % of LP tokens are locked. |
| 39 | `rc_lp_lock_duration_days` | float | How many days the LP is locked for. 0 if not locked. |
| 40 | `rc_lp_burned` | bool | LP tokens burned (permanent, irreversible lock). |
| 41 | `rc_single_holder_ownership` | bool | One wallet holds majority of supply. |
| 42 | `rc_high_concentration` | bool | Supply is concentrated in few wallets. |
| 43 | `rc_low_liquidity` | bool | Liquidity is thin — easy to drain or manipulate. |
| 44 | `rc_copycat_token` | bool | Token name/symbol copies a well-known token. |
| 45 | `rc_total_market_liquidity` | float | Total USD value across all pools. |
| 46 | `rc_num_markets` | int | Number of DEX pools this token has. |

**Implementation notes:**
- The response is a JSON object. `score` is at the top level. Risks are in a `risks` array.
- Extract `rc_top10_holder_pct` and `rc_top_holder_pct` from the `topHolders` section.
- LP lock info is in the `markets` array — check each market's `lp` field.
- If the token is too new for RugCheck to have data, all fields default to null/0.

---

## 4. GoPlus Security API — 24 features

**Endpoint:** `GET https://api.gopluslabs.com/api/v1/solana/token_security/{mint}`  
**Auth:** None required  
**Rate limit:** ~2 req/s (use 0.5s delay)  
**Latency:** ~500ms

> **IMPORTANT:** GoPlus binary flags can be misleading on Solana. Legit tokens (USDC) flag as
> "suspicious" because Circle controls freeze/mint. Drained rugs flag as "clean" because
> authorities were revoked after the steal. **Always prefer the numeric fields** (holder %,
> TVL, LP count) over binary flags for model features.

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 47 | `gp_holder_count` | int | Total token holders. Very low = just launched or abandoned. |
| 48 | `gp_top1_holder_pct` | float | **KEY** — Largest single holder %. > 50% = extreme risk. |
| 49 | `gp_top3_holder_pct` | float | **KEY** — Top 3 holders combined %. |
| 50 | `gp_top10_holder_pct` | float | Top 10 holders combined %. |
| 51 | `gp_creator_pct` | float | % of supply the creator still holds. |
| 52 | `gp_lp_holder_count` | int | Number of LP token holders. 1 = single entity controls all liquidity. |
| 53 | `gp_lp_top1_pct` | float | Largest LP holder %. If 100% = instant drain possible. |
| 54 | `gp_total_supply` | float | Total token supply as reported by GoPlus. |
| 55 | `gp_is_open_source` | bool | Contract code is verified/readable. |
| 56 | `gp_is_proxy` | bool | Contract is upgradeable (proxy pattern). |
| 57 | `gp_is_mintable` | bool | New tokens can be minted. |
| 58 | `gp_owner_address` | string | Current contract owner. |
| 59 | `gp_creator_address` | string | Original deployer. |
| 60 | `gp_buy_tax` | float | Hidden tax on buy transactions (0.0 – 1.0). |
| 61 | `gp_sell_tax` | float | Hidden tax on sell transactions. If 1.0 = honeypot. |
| 62 | `gp_cannot_buy` | bool | Buying is disabled. |
| 63 | `gp_cannot_sell_all` | bool | Cannot sell full position. **Honeypot indicator.** |
| 64 | `gp_is_honeypot` | bool | GoPlus simulated a sell and it failed. |
| 65 | `gp_is_blacklisted` | bool | Contract has blacklist function. |
| 66 | `gp_is_whitelisted` | bool | Contract has whitelist function. |
| 67 | `gp_transfer_pausable` | bool | Contract can pause all transfers. |
| 68 | `gp_anti_whale` | bool | Has anti-whale transaction limits. |
| 69 | `gp_trading_cooldown` | bool | Forced delay between trades per wallet. |
| 70 | `gp_personal_slippage_modifiable` | bool | Can change slippage requirements per address. |

**Implementation notes:**
- Response is nested: `result.{mint_address}.{fields}`.
- Holder data is in `holders` array — compute top1/top3/top10 yourself.
- LP data is in `lp_holders` array.
- `gp_buy_tax` and `gp_sell_tax` come as strings ("0.1" = 10% tax) — parse to float.
- If GoPlus has no data for the token, return nulls — don't use defaults.
- **No batch support on Solana** — one mint per request only.

---

## 5. GeckoTerminal API — 25 features

**Endpoint:** `GET https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}/pools?page=1`  
**Auth:** None required  
**Rate limit:** ~2 req/s (use 0.5s delay)  
**Latency:** ~500ms

> **NOTE:** Dead/rugged tokens often have NO pools on GeckoTerminal. `gt_pool_count = 0` is
> itself a powerful signal — it means the token has no active trading, which correlates
> strongly with rugs.

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 71 | `gt_pool_count` | int | Number of active pools. 0 = no trading = likely dead/rugged. |
| 72 | `gt_pool_address` | string | Address of the largest pool (by reserve). |
| 73 | `gt_dex_name` | string | Which DEX: Raydium, Orca, pump.fun, Meteora. Platform matters. |
| 74 | `gt_base_token_price_usd` | float | Current token price in USD. |
| 75 | `gt_fdv_usd` | float | Fully diluted valuation. |
| 76 | `gt_market_cap_usd` | float | Market cap. |
| 77 | `gt_reserve_usd` | float | **KEY** — Total liquidity in the pool (USD). Low = easy to drain. |
| 78 | `gt_reserve_base` | float | Token-side reserve (how many tokens in pool). |
| 79 | `gt_reserve_quote` | float | SOL/USDC-side reserve. |
| 80 | `gt_volume_5m_usd` | float | Trading volume in last 5 minutes. |
| 81 | `gt_volume_1h_usd` | float | Trading volume in last 1 hour. |
| 82 | `gt_volume_6h_usd` | float | Trading volume in last 6 hours. |
| 83 | `gt_volume_24h_usd` | float | Trading volume in last 24 hours. |
| 84 | `gt_price_change_5m` | float | % price change in last 5 minutes. |
| 85 | `gt_price_change_1h` | float | % price change in last 1 hour. |
| 86 | `gt_price_change_6h` | float | % price change in last 6 hours. |
| 87 | `gt_price_change_24h` | float | % price change in last 24 hours. |
| 88 | `gt_tx_count_5m_buys` | int | Buy transactions in last 5 minutes. |
| 89 | `gt_tx_count_5m_sells` | int | Sell transactions in last 5 minutes. |
| 90 | `gt_tx_count_1h_buys` | int | Buy transactions in last 1 hour. |
| 91 | `gt_tx_count_1h_sells` | int | Sell transactions in last 1 hour. |
| 92 | `gt_buy_sell_ratio_5m` | float | `buys / (sells + 1)`. Lopsided ratio = manipulation. |
| 93 | `gt_buy_sell_ratio_1h` | float | `buys / (sells + 1)`. |
| 94 | `gt_pool_created_at` | datetime | When the main pool was created. |
| 95 | `gt_pool_age_hours` | float | Hours since pool creation. Very new = higher risk. |

**Implementation notes:**
- Response is paginated. First page is enough — pools are sorted by liquidity.
- Use the **first pool** (highest liquidity) for all single-pool fields.
- `gt_pool_count`: count total items across pages, or just use `meta.total` if available.
- `gt_buy_sell_ratio`: compute as `buys / (sells + 1)` to avoid division by zero.
- `gt_pool_age_hours`: compute from `gt_pool_created_at` vs current time.
- If the token has **no pools**, set `gt_pool_count = 0` and all other fields to `null`.

---

## 6. Jupiter API — 5 features

**Endpoints:**
- Token list: `GET https://token.jup.ag/strict`
- Price: `GET https://price.jup.ag/v4/price?ids={mint}`

**Auth:** None required  
**Rate limit:** Generous  
**Latency:** ~100ms

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 96 | `jup_listed` | bool | Token appears on Jupiter at all. |
| 97 | `jup_strict_list` | bool | On the verified/strict list. **Strong legitimacy signal.** |
| 98 | `jup_daily_volume` | float | 24h volume through Jupiter aggregator. |
| 99 | `jup_price_usd` | float | Jupiter's quoted price. Compare to GeckoTerminal price for arb. |
| 100 | `jup_tags` | list[str] | Tags: `"verified"`, `"community"`, `"wormhole"`, etc. |

**Implementation notes:**
- Cache the strict list — it doesn't change every second. Refresh every 5 minutes.
- `jup_listed`: check if mint appears in the full token list (`GET https://token.jup.ag/all`).
- `jup_strict_list`: check if mint appears in the strict list.
- `jup_daily_volume`: from the price endpoint response.
- `jup_tags`: from the token list entry.

---

## 7. Derived Features (Computed by Backend) — 10 features

These require **no additional API calls**. Compute from the fields above.

| # | Feature | Formula | Description |
|---|---------|---------|-------------|
| 101 | `liquidity_to_fdv_ratio` | `gt_reserve_usd / (gt_fdv_usd + 1)` | Low ratio = inflated FDV with no real liquidity. Classic rug bait. |
| 102 | `holder_to_supply_ratio` | `gp_holder_count / (gp_total_supply + 1)` | How distributed is the token. |
| 103 | `creator_holds_majority` | `gp_creator_pct > 50` | Creator still owns more than half. |
| 104 | `lp_concentrated` | `gp_lp_top1_pct > 90` | Single wallet controls all liquidity — can drain instantly. |
| 105 | `sell_pressure_score` | `gt_tx_count_1h_sells / (gt_tx_count_1h_buys + 1)` | > 1.0 means more sells than buys. High = dump in progress. |
| 106 | `metadata_completeness` | `(has_image + has_desc + has_website + has_twitter + has_telegram) / 5` | 0.0 = no effort, 1.0 = fully filled out. Rugs are usually lazy. |
| 107 | `authority_risk_score` | `(!mint_authority_revoked) + (!freeze_authority_revoked) + is_mutable` | 0 = all authorities revoked. 3 = full control retained. |
| 108 | `wallet_freshness_flag` | `creator_wallet_age_hours < 24 AND creator_tx_count < 10` | Brand new wallet with almost no history. |
| 109 | `consensus_risk` | `mean(1 - rc_score/1000, authority_risk_score/3, gp_top1_holder_pct/100)` | Cross-source average risk. Higher = more dangerous. |
| 110 | `price_liquidity_divergence` | `gt_fdv_usd / (gt_reserve_usd + 1)` | Extreme values = artificial pump with thin liquidity. |

---

## Null Handling

When an API returns no data (token too new, not indexed yet, API down):

| Scenario | Action |
|----------|--------|
| API timeout (> 2s) | Set all features from that source to `null` |
| Token not found by API | Set all features from that source to `null` |
| Individual field missing | Set that field to `null` |
| Derived feature has null input | Set derived feature to `null` |

The ML model handles nulls — do **not** fill with zeros or defaults. Let the model decide.

---

## API Summary

| Source | Features | Auth | Rate Limit | Cost |
|--------|----------|------|-----------|------|
| Helius DAS | 22 | API key | 50 req/s (paid) | ~$50/mo |
| Creator Wallet (Helius) | 6 | Same key | Same | Included |
| RugCheck | 18 | None | ~3 req/s | Free |
| GoPlus Security | 24 | None | ~2 req/s | Free |
| GeckoTerminal | 25 | None | ~2 req/s | Free |
| Jupiter | 5 | None | Generous | Free |
| Derived | 10 | N/A | N/A | N/A |
| **Total** | **110** | | | |

---

## Response Schema

The backend should return a JSON object with all 110 features:

```json
{
  "mint_address": "So11111111111111111111111111111111111111112",
  "timestamp": "2026-02-21T16:00:00Z",
  "features": {
    "token_name": "Example Token",
    "token_symbol": "EXT",
    "token_decimals": 9,
    "token_supply": 1000000000.0,
    "mint_authority": null,
    "mint_authority_revoked": true,
    "...": "all 110 features"
  },
  "api_status": {
    "helius": "ok",
    "rugcheck": "ok",
    "goplus": "ok",
    "geckoterminal": "ok",
    "jupiter": "ok"
  },
  "latency_ms": {
    "helius": 120,
    "rugcheck": 280,
    "goplus": 490,
    "geckoterminal": 510,
    "jupiter": 95,
    "total": 510
  }
}
```
