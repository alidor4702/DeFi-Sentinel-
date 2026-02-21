# live_data/collector

Real-time feature collector for Solana tokens. Gathers **81 features** from 5 APIs for any token mint address, used as input to the DeFi Sentinel rug-pull detection model.

## Quick Start

```bash
# Install dependencies
pip install httpx pydantic-settings python-dotenv

# Create live_data/.env with at minimum:
echo "HELIUS_API_KEY=your_key_here" > live_data/.env

# Collect features for a token
python -m live_data.collector <mint_address>

# JSON output
python -m live_data.collector <mint_address> --json

# Debug logging
python -m live_data.collector <mint_address> --verbose
```

## CLI Usage

```
python -m live_data.collector <mint> [--json] [--verbose]
```

| Flag | Description |
|------|-------------|
| `mint` | Solana token mint address (required) |
| `--json` | Output raw JSON instead of formatted table |
| `--verbose` | Enable debug logging for all API calls |

Example output (table mode):

```
============================================================
  Token: So11111111111111111111111111111111111111112
  Features collected: 68 / 81
  Total latency: 3241 ms
============================================================

  [Helius] (18/20 populated)
    + token_name: Wrapped SOL
    + token_symbol: SOL
    ...

  [GeckoTerminal] (25/25 populated)
    + gt_pool_count: 47
    + gt_base_token_price_usd: 148.23
    ...

  [Latency]
    helius: 412 ms
    creator_wallet: 1102 ms
    rugcheck: 890 ms
    geckoterminal: 345 ms
    jupiter: 520 ms
```

## Programmatic API

```python
import asyncio
from live_data.collector import collect_features, CollectionResult

result: CollectionResult = asyncio.run(collect_features("So11111111111111111111111111111111111111112"))

print(result.features)             # dict of 81 feature keys
print(result.features_collected)   # count of non-None values
print(result.latency_ms)           # per-source latency
print(result.errors)               # list of error strings
print(result.total_latency_ms)     # end-to-end time
```

`CollectionResult` fields:

| Field | Type | Description |
|-------|------|-------------|
| `mint` | `str` | Token mint address |
| `features` | `dict` | All 81 features (None if unavailable) |
| `latency_ms` | `dict` | Per-source latency in ms |
| `errors` | `list[str]` | Error messages from failed sources |
| `total_latency_ms` | `float` | Total collection time in ms |
| `features_collected` | `int` | Count of non-None features |

## Configuration

Settings are loaded from `live_data/.env` via pydantic-settings.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HELIUS_API_KEY` | Yes | — | Helius API key (free at https://dev.helius.xyz/) |
| `JUPITER_API_KEY` | No | `""` | Jupiter API key (skips Jupiter if empty) |
| `HELIUS_RPC_URL` | No | `https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}` | Helius RPC endpoint |
| `RUGCHECK_BASE_URL` | No | `https://api.rugcheck.xyz` | RugCheck API base URL |
| `GECKOTERMINAL_BASE_URL` | No | `https://api.geckoterminal.com` | GeckoTerminal API base URL |
| `JUPITER_BASE_URL` | No | `https://api.jup.ag` | Jupiter API base URL |
| `REQUEST_TIMEOUT` | No | `10.0` | HTTP request timeout in seconds |
| `MAX_RETRIES` | No | `3` | Max retries per request (exponential backoff: 1s, 2s, 4s) |

## Architecture

Collection runs in 3 phases:

```
Phase 1: Helius (getAsset RPC)
   ↓ extracts creator_address
Phase 2: 4 clients in parallel
   ├── Creator Wallet (getBalance, getAssetsByOwner, getSignaturesForAddress)
   ├── RugCheck (summary + full report)
   ├── GeckoTerminal (token pools)
   └── Jupiter (token search + price)
Phase 3: Derived features (pure computation from Phase 1+2 data)
```

All HTTP clients share retry/backoff logic via `BaseClient` (3 retries, exponential backoff at 1s/2s/4s, 10s timeout).

## Feature Reference (81 total)

### Helius — 20 features

| Feature | Type | Description |
|---------|------|-------------|
| `token_name` | str | Token name from metadata |
| `token_symbol` | str | Token ticker symbol |
| `token_decimals` | int | Decimal places |
| `token_supply` | float | Total supply (human-readable) |
| `mint_authority` | str | Mint authority address |
| `mint_authority_revoked` | bool | True if no mint authority |
| `freeze_authority` | str | Freeze authority address |
| `freeze_authority_revoked` | bool | True if no freeze authority |
| `update_authority` | str | Update authority address |
| `is_mutable` | bool | Whether metadata is mutable |
| `token_standard` | str | Token standard (e.g. Fungible) |
| `token_program` | str | Token program ID |
| `metadata_uri` | str | Off-chain metadata JSON URI |
| `metadata_uri_reachable` | bool | Whether metadata URI responds |
| `has_image` | bool | Has image in metadata |
| `has_description` | bool | Has description in metadata |
| `has_website` | bool | Has website link |
| `has_twitter` | bool | Has Twitter/X link |
| `has_telegram` | bool | Has Telegram link |
| `creator_address` | str | Creator/deployer wallet address |

### Creator Wallet — 6 features

| Feature | Type | Description |
|---------|------|-------------|
| `creator_sol_balance` | float | Creator's SOL balance |
| `creator_wallet_age_hours` | float | Wallet age from oldest tx in batch |
| `creator_token_count` | int | Fungible tokens held by creator |
| `creator_tx_count` | int | Transaction count (up to 1000) |
| `creator_prev_tokens_rugged` | int | Previously rugged tokens (placeholder, always 0) |
| `creator_nft_count` | int | NFTs held by creator |

### RugCheck — 18 features

| Feature | Type | Description |
|---------|------|-------------|
| `rc_score` | float | RugCheck risk score (higher = safer) |
| `rc_risk_level` | str | Good / Warning / Danger |
| `rc_risk_count` | int | Number of risk flags |
| `rc_mint_authority_disabled` | bool | Mint authority disabled per RugCheck |
| `rc_freeze_authority_disabled` | bool | Freeze authority disabled per RugCheck |
| `rc_mutable_metadata` | bool | Metadata is mutable |
| `rc_top_holder_pct` | float | Top holder ownership % |
| `rc_top10_holder_pct` | float | Top 10 holders ownership % |
| `rc_lp_locked` | bool | LP tokens are locked |
| `rc_lp_lock_pct` | float | % of LP locked |
| `rc_lp_lock_duration_days` | float | LP lock remaining days |
| `rc_lp_burned` | bool | LP tokens burned (100% locked) |
| `rc_single_holder_ownership` | bool | Single holder dominance flag |
| `rc_high_concentration` | bool | High holder concentration flag |
| `rc_low_liquidity` | bool | Low liquidity flag |
| `rc_copycat_token` | bool | Copycat token flag |
| `rc_total_market_liquidity` | float | Total liquidity across markets (USD) |
| `rc_num_markets` | int | Number of trading markets |

### GeckoTerminal — 25 features

| Feature | Type | Description |
|---------|------|-------------|
| `gt_pool_count` | int | Number of pools for this token |
| `gt_pool_address` | str | Top pool address |
| `gt_pool_name` | str | Top pool name |
| `gt_dex` | str | DEX of top pool |
| `gt_base_token_price_usd` | float | Token price in USD |
| `gt_quote_token_price_usd` | float | Quote token price in USD |
| `gt_fdv_usd` | float | Fully diluted valuation |
| `gt_market_cap_usd` | float | Market cap |
| `gt_reserve_usd` | float | Total pool reserves in USD |
| `gt_volume_5m` | float | 5-minute trading volume |
| `gt_volume_1h` | float | 1-hour trading volume |
| `gt_volume_6h` | float | 6-hour trading volume |
| `gt_volume_24h` | float | 24-hour trading volume |
| `gt_price_change_5m` | float | 5-minute price change % |
| `gt_price_change_1h` | float | 1-hour price change % |
| `gt_price_change_6h` | float | 6-hour price change % |
| `gt_price_change_24h` | float | 24-hour price change % |
| `gt_tx_count_5m_buys` | int | Buy transactions (5 min) |
| `gt_tx_count_5m_sells` | int | Sell transactions (5 min) |
| `gt_tx_count_1h_buys` | int | Buy transactions (1 hour) |
| `gt_tx_count_1h_sells` | int | Sell transactions (1 hour) |
| `gt_tx_count_24h_buys` | int | Buy transactions (24 hours) |
| `gt_tx_count_24h_sells` | int | Sell transactions (24 hours) |
| `gt_buy_sell_ratio_1h` | float | 1-hour buy/sell ratio |
| `gt_pool_age_hours` | float | Hours since pool creation |

### Jupiter — 5 features

| Feature | Type | Description |
|---------|------|-------------|
| `jup_listed` | bool | Token found on Jupiter |
| `jup_strict_list` | bool | On Jupiter verified/strict list |
| `jup_daily_volume` | float | 24h volume via Jupiter |
| `jup_price_usd` | float | Price from Jupiter price API |
| `jup_tags` | list | Jupiter tags (e.g. verified, community) |

### Derived — 7 features

Computed from raw features, no additional API calls.

| Feature | Type | Description |
|---------|------|-------------|
| `liquidity_to_fdv_ratio` | float | `gt_reserve_usd / (gt_fdv_usd + 1)` |
| `sell_pressure_score` | float | `1h_sells / (1h_buys + 1)` |
| `metadata_completeness` | float | Fraction of 5 metadata booleans that are True (0.0–1.0) |
| `authority_risk_score` | int | 0–3 score: +1 each for mint auth active, freeze auth active, mutable metadata |
| `wallet_freshness_flag` | bool | True if creator wallet < 24h old AND < 10 txs |
| `consensus_risk` | float | Mean of normalized RugCheck score, authority risk, top holder concentration |
| `price_liquidity_divergence` | float | `gt_fdv_usd / (gt_reserve_usd + 1)` |
