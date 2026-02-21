"""
DeFi Sentinel — thin FastAPI backend wrapping the live_data collector.

Endpoints:
  GET  /api/scan/{mint}     — collect 81 features for a token, return frontend-shaped response
  GET  /api/tokens          — cached list of ~20 real tokens for LivePoolMonitor
  POST /api/tokens/refresh  — trigger immediate rescan and return fresh token list

Run:
  python -m uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402
import json as json_mod  # noqa: E402
import httpx  # noqa: E402

# Load .env from project root
from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from live_data.collector import collect_features, CollectionResult  # noqa: E402
from ml_scorer import predict_rug_probability, get_model_meta  # noqa: E402

logger = logging.getLogger("backend")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# In-memory token cache
# ---------------------------------------------------------------------------
_token_cache: list[dict] = []
_cache_lock = asyncio.Lock()
_REFRESH_INTERVAL = 300  # 5 minutes
_TARGET_TOKENS = 20
_SCAN_CONCURRENCY = 2


# ---------------------------------------------------------------------------
# WebSocket manager
# ---------------------------------------------------------------------------
from starlette.websockets import WebSocket, WebSocketDisconnect  # noqa: E402


class _WSManager:
    """Manage active WebSocket connections for live push."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict):
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


_ws_mgr = _WSManager()


# ---------------------------------------------------------------------------
# Stripe setup
# ---------------------------------------------------------------------------
try:
    import stripe as _stripe

    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    _STRIPE_AVAILABLE = bool(_stripe.api_key)
except ImportError:
    _STRIPE_AVAILABLE = False
    _stripe = None  # type: ignore

_PLAN_PRICES = {
    "pro":      {"price_id": "price_1T3Gk57ouElHwHTvifJttL5b", "mode": "subscription"},
    "enterprise": {"price_id": "price_1T3GkK7ouElHwHTvVgt3vOnR", "mode": "subscription"},
    "pack-10":  {"price_id": "price_1T3GkW7ouElHwHTvz6GPpJ1A", "mode": "payment"},
    "pack-50":  {"price_id": "price_1T3GlA7ouElHwHTvTKrYtRHd", "mode": "payment"},
    "pack-200": {"price_id": "price_1T3Glh7ouElHwHTvSVmOv4By", "mode": "payment"},
}


# ---------------------------------------------------------------------------
# Feature → frontend mapping helpers
# ---------------------------------------------------------------------------

def _first(*values):
    """Return first non-None value, or None."""
    for v in values:
        if v is not None:
            return v
    return None


def _heuristic_risk_score(f: dict) -> int:
    """Weighted heuristic risk score 0-100 (placeholder for ML)."""
    score = 0.0

    # RugCheck score (0-1000 scale, higher = riskier)
    rc = f.get("rc_score")
    if rc is not None:
        score += min(rc / 10, 40)  # up to 40 pts
    else:
        score += 20  # unknown = moderate risk

    # Mint authority enabled
    if f.get("mint_authority_revoked") is False:
        score += 15

    # Freeze authority enabled
    if f.get("freeze_authority_revoked") is False:
        score += 10

    # Top holder concentration
    top_pct = f.get("rc_top_holder_pct")
    if top_pct is not None and top_pct > 50:
        score += min((top_pct - 50) * 0.4, 15)  # up to 15 pts

    # Low liquidity
    liq = _first(f.get("gt_reserve_usd"), f.get("rc_total_market_liquidity"))
    if liq is not None:
        if liq < 100:
            score += 10
        elif liq < 1000:
            score += 5

    # Young pool
    age = f.get("gt_pool_age_hours")
    if age is not None and age < 24:
        score += 10
    elif age is not None and age < 168:
        score += 3

    return max(0, min(100, round(score)))


def _build_risk_factors(f: dict) -> list[dict]:
    """Generate dynamic risk factors from real data."""
    factors = []

    if f.get("mint_authority_revoked") is False:
        factors.append({
            "level": "critical",
            "name": "Mint Authority Enabled",
            "score": 35,
            "description": "Creator can mint unlimited tokens, diluting holders to zero.",
        })

    if f.get("freeze_authority_revoked") is False:
        factors.append({
            "level": "medium",
            "name": "Freeze Authority Enabled",
            "score": 10,
            "description": "Creator can freeze your tokens, preventing transfers or sales.",
        })

    top_pct = f.get("rc_top_holder_pct")
    if top_pct is not None and top_pct > 50:
        factors.append({
            "level": "critical",
            "name": "Extreme Holder Concentration",
            "score": 25,
            "description": f"Top wallet holds {top_pct:.1f}% of supply. A single sell could crash the price.",
        })
    elif top_pct is not None and top_pct > 25:
        factors.append({
            "level": "high",
            "name": "High Holder Concentration",
            "score": 15,
            "description": f"Top wallet holds {top_pct:.1f}% of supply.",
        })

    liq = _first(f.get("gt_reserve_usd"), f.get("rc_total_market_liquidity"))
    if liq is not None and liq < 1000:
        factors.append({
            "level": "high",
            "name": "Critical Low Liquidity",
            "score": 20,
            "description": f"Only ${liq:,.0f} in pool. Trades will cause massive slippage.",
        })

    age = f.get("gt_pool_age_hours")
    if age is not None and age < 24:
        factors.append({
            "level": "high",
            "name": "Pool Age < 1 Day",
            "score": 15,
            "description": f"Pool is only {age:.0f} hours old. Matches timing pattern of most rug pulls.",
        })

    if f.get("is_mutable") is True:
        factors.append({
            "level": "medium",
            "name": "Mutable Metadata",
            "score": 5,
            "description": "Token metadata can be changed by the creator at any time.",
        })

    creator_age = f.get("creator_wallet_age_hours")
    if creator_age is not None and creator_age < 72:
        factors.append({
            "level": "medium",
            "name": "Fresh Creator Wallet",
            "score": 8,
            "description": f"Creator wallet is only {creator_age:.0f} hours old.",
        })

    if f.get("rc_copycat_token") is True:
        factors.append({
            "level": "high",
            "name": "Copycat Token",
            "score": 20,
            "description": "RugCheck flagged this as a copycat of an existing token.",
        })

    if f.get("rc_lp_locked") is False and f.get("rc_lp_burned") is False:
        factors.append({
            "level": "medium",
            "name": "LP Not Locked or Burned",
            "score": 10,
            "description": "Liquidity pool tokens are not locked — creator can remove liquidity.",
        })

    factors.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2}[x["level"]])
    return factors


def _build_ai_analysis(f: dict, risk_score: int) -> str:
    """Template-based analysis text built from real metrics (no LLM call)."""
    name = f.get("token_name") or "This token"
    symbol = f.get("token_symbol") or "???"
    parts = []

    # Verdict opener
    if risk_score >= 70:
        parts.append(f"EXTREME CAUTION: {name} ({symbol}) shows multiple high-risk indicators.")
    elif risk_score >= 40:
        parts.append(f"MODERATE RISK: {name} ({symbol}) has some concerning characteristics.")
    else:
        parts.append(f"{name} ({symbol}) appears to be a relatively low-risk token.")

    # Liquidity
    liq = _first(f.get("gt_reserve_usd"), f.get("rc_total_market_liquidity"))
    if liq is not None:
        if liq >= 1_000_000:
            parts.append(f"Liquidity is strong at ${liq / 1e6:.1f}M.")
        elif liq >= 1_000:
            parts.append(f"Liquidity is ${liq / 1e3:.1f}K.")
        else:
            parts.append(f"Liquidity is critically low at ${liq:,.0f}.")

    # Authorities
    mint_ok = f.get("mint_authority_revoked")
    freeze_ok = f.get("freeze_authority_revoked")
    if mint_ok is True and freeze_ok is True:
        parts.append("Mint and freeze authorities are disabled.")
    else:
        issues = []
        if mint_ok is False:
            issues.append("mint authority is still enabled")
        if freeze_ok is False:
            issues.append("freeze authority is still enabled")
        if issues:
            parts.append(f"Warning: {', '.join(issues)}.")

    # Pool age
    age = f.get("gt_pool_age_hours")
    if age is not None:
        if age < 24:
            parts.append(f"The pool is only {age:.0f} hours old.")
        elif age < 720:
            parts.append(f"Pool has been active for {age / 24:.0f} days.")
        else:
            parts.append(f"Pool has been active for {age / 720:.0f} months.")

    # Holder concentration
    top_pct = f.get("rc_top_holder_pct")
    if top_pct is not None:
        if top_pct > 50:
            parts.append(f"Top wallet holds {top_pct:.1f}% of supply — a classic rug pull setup.")
        elif top_pct > 20:
            parts.append(f"Top wallet holds {top_pct:.1f}% of supply.")

    # RugCheck
    rc_level = f.get("rc_risk_level")
    if rc_level:
        parts.append(f"RugCheck rates this as '{rc_level}'.")

    return " ".join(parts)


def _map_scan_result(result: CollectionResult) -> dict:
    """Map a CollectionResult to the frontend ScanResultData shape."""
    f = result.features

    rug_prob, risk_score = predict_rug_probability(f)
    verdict = "SAFE" if risk_score < 50 else "DANGER"

    price = _first(f.get("jup_price_usd"), f.get("gt_base_token_price_usd"))
    volume = _first(f.get("gt_volume_24h"), f.get("jup_daily_volume"))
    market_cap = _first(f.get("gt_market_cap_usd"), f.get("gt_fdv_usd"))
    liquidity = _first(f.get("gt_reserve_usd"), f.get("rc_total_market_liquidity")) or 0
    pool_age_hours = f.get("gt_pool_age_hours")
    pool_age_days = round(pool_age_hours / 24, 1) if pool_age_hours is not None else 0

    rc_score_raw = f.get("rc_score")
    rc_score_100 = round(rc_score_raw / 10, 1) if rc_score_raw is not None else 0

    return {
        "name": f.get("token_name") or "Unknown",
        "symbol": f.get("token_symbol") or "???",
        "mint": result.mint,
        "riskScore": risk_score,
        "verdict": verdict,
        "price": price,
        "volume24h": volume,
        "marketCap": market_cap,
        "geckoTerminalUrl": f"https://www.geckoterminal.com/solana/tokens/{result.mint}",
        "metrics": {
            "mlConfidence": round(rug_prob * 100, 1),
            "holders": 0,
            "liquidity": liquidity,
            "poolAge": pool_age_days,
            "mintAuthority": f.get("mint_authority_revoked") is False,
            "freezeAuthority": f.get("freeze_authority_revoked") is False,
            "rugCheckScore": rc_score_100,
            "topHolderPercent": round(f.get("rc_top_holder_pct") or 0, 1),
        },
        "riskFactors": _build_risk_factors(f),
        "aiAnalysis": _build_ai_analysis(f, risk_score),
        "featuresCollected": result.features_collected,
        "totalLatencyMs": result.total_latency_ms,
        "errors": result.errors,
    }


def _map_token_list_item(result: CollectionResult) -> dict:
    """Map a CollectionResult to the LivePoolMonitor token shape."""
    f = result.features
    _, risk_score = predict_rug_probability(f)
    liquidity = _first(f.get("gt_reserve_usd"), f.get("rc_total_market_liquidity")) or 0

    # Determine color from risk
    if risk_score >= 70:
        color = "#ef4444"
    elif risk_score >= 40:
        color = "#f59e0b"
    else:
        color = "#00e5a0"

    # Risk label for 3-tier display
    if risk_score >= 70:
        risk_label = "DANGER"
    elif risk_score >= 40:
        risk_label = "MODERATE"
    else:
        risk_label = "SAFE"

    return {
        "id": result.mint,
        "name": f.get("token_name") or "Unknown",
        "symbol": f.get("token_symbol") or "???",
        "mint": result.mint,
        "holders": 0,
        "liquidity": liquidity,
        "riskScore": risk_score,
        "riskLabel": risk_label,
        "color": color,
        "geckoTerminalUrl": f"https://www.geckoterminal.com/solana/tokens/{result.mint}",
        "price": _first(f.get("jup_price_usd"), f.get("gt_base_token_price_usd")),
        "volume24h": _first(f.get("gt_volume_24h"), f.get("jup_daily_volume")),
        "poolAgeHours": f.get("gt_pool_age_hours"),
    }


# ---------------------------------------------------------------------------
# Background token discovery + scanning
# ---------------------------------------------------------------------------

# Well-known tokens to seed the dashboard with variety (mix of risk levels)
_SEED_TOKENS = [
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "So11111111111111111111111111111111111111112",      # Wrapped SOL
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",   # JUP
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
    "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",  # POPCAT
]


async def _extract_mints_from_pools(data: dict, seen: set[str]) -> list[str]:
    """Extract mint addresses from a GeckoTerminal pools API response."""
    mints = []
    for pool in data.get("data") or []:
        relationships = pool.get("relationships") or {}
        base_token = (relationships.get("base_token") or {}).get("data") or {}
        token_id = base_token.get("id") or ""
        mint = token_id[len("solana_"):] if token_id.startswith("solana_") else token_id
        if mint and mint not in seen:
            seen.add(mint)
            mints.append(mint)
    return mints


async def _fetch_trending_pool_mints(target: int) -> list[str]:
    """Fetch mint addresses from GeckoTerminal trending_pools (established, higher-liq tokens)."""
    url = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"
    mints: list[str] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            mints = await _extract_mints_from_pools(resp.json(), seen)
        except Exception as e:
            logger.warning(f"trending_pools failed: {e}")

    return mints[:target]


async def _fetch_new_pool_mints(target: int) -> list[str]:
    """Fetch mint addresses from GeckoTerminal new_pools endpoint."""
    url = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
    mints: list[str] = []
    seen: set[str] = set()
    page = 1

    async with httpx.AsyncClient(timeout=15.0) as client:
        while len(mints) < target and page <= 3:
            try:
                resp = await client.get(
                    url,
                    params={"page": page},
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                new = await _extract_mints_from_pools(resp.json(), seen)
                mints.extend(new)
            except Exception as e:
                logger.warning(f"new_pools page {page} failed: {e}")
                break
            page += 1
            await asyncio.sleep(0.5)

    return mints[:target]


async def _refresh_token_cache():
    """Fetch a diversified mix of tokens: trending + new pools + seed tokens."""
    global _token_cache
    logger.info("Refreshing token cache (diversified feed)...")

    all_mints: list[str] = []
    seen: set[str] = set()

    # 1) Seed tokens (known established tokens for baseline variety)
    for mint in _SEED_TOKENS:
        if mint not in seen:
            seen.add(mint)
            all_mints.append(mint)

    # 2) Trending pools (established, higher-liq tokens — mixed risk)
    #    Small delay to avoid GeckoTerminal rate limits on startup
    await asyncio.sleep(2)
    try:
        trending = await _fetch_trending_pool_mints(target=12)
        for mint in trending:
            if mint not in seen:
                seen.add(mint)
                all_mints.append(mint)
    except Exception as e:
        logger.error(f"Failed to fetch trending pool mints: {e}")

    # 3) New pools (freshest launches — likely high risk)
    await asyncio.sleep(2)
    try:
        new_pools = await _fetch_new_pool_mints(target=10)
        for mint in new_pools:
            if mint not in seen:
                seen.add(mint)
                all_mints.append(mint)
    except Exception as e:
        logger.error(f"Failed to fetch new pool mints: {e}")

    if not all_mints:
        logger.warning("No mints discovered from any source")
        return

    logger.info(f"Scanning {len(all_mints)} tokens ({len(_SEED_TOKENS)} seed + trending + new)")

    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)
    results: list[dict] = []

    async def _scan_one(mint: str):
        async with sem:
            try:
                result = await collect_features(mint)
                item = _map_token_list_item(result)
                results.append(item)
            except Exception as e:
                logger.error(f"Failed to scan {mint[:12]}...: {e}")

    tasks = [asyncio.create_task(_scan_one(mint)) for mint in all_mints[:_TARGET_TOKENS + 5]]
    await asyncio.gather(*tasks)

    # Sort: safe first (proves model works), then moderate, then danger
    # Within each tier, sort by liquidity descending (most impressive first)
    def _sort_key(t):
        score = t.get("riskScore", 0)
        liq = t.get("liquidity", 0)
        if score < 40:
            tier = 0  # SAFE first
        elif score < 70:
            tier = 1  # MODERATE second
        else:
            tier = 2  # DANGER last
        return (tier, -liq)

    async with _cache_lock:
        _token_cache = sorted(results, key=_sort_key)

    logger.info(f"Token cache refreshed: {len(_token_cache)} tokens")

    # Log score distribution
    scores = [t.get("riskScore", 0) for t in _token_cache]
    if scores:
        high = sum(1 for s in scores if s >= 70)
        med = sum(1 for s in scores if 40 <= s < 70)
        low = sum(1 for s in scores if s < 40)
        logger.info(f"Score distribution: {high} DANGER / {med} MODERATE / {low} SAFE")

    # Push to WebSocket clients
    if _ws_mgr.count > 0:
        await _ws_mgr.broadcast({"type": "tokens", "data": _token_cache})


async def _background_refresh_loop():
    """Periodically refresh the token cache."""
    while True:
        try:
            await _refresh_token_cache()
        except Exception as e:
            logger.error(f"Background refresh error: {e}")
        await asyncio.sleep(_REFRESH_INTERVAL)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Solana WebSocket listener (real-time new token detection)
# ---------------------------------------------------------------------------

async def _resolve_mint_from_sig(sig: str, rpc_url: str) -> str | None:
    """Get the new token mint address from a transaction signature."""
    payload = {
        "jsonrpc": "2.0",
        "id": "resolve-mint",
        "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(rpc_url, json=payload)
        data = resp.json()
    result = data.get("result")
    if not result:
        return None
    # Check outer and inner instructions for InitializeMint
    for ix_list in [
        result.get("transaction", {}).get("message", {}).get("instructions", []),
        *[g.get("instructions", []) for g in result.get("meta", {}).get("innerInstructions", [])],
    ]:
        for ix in ix_list:
            parsed = ix.get("parsed")
            if isinstance(parsed, dict) and parsed.get("type") in ("initializeMint", "initializeMint2"):
                mint = parsed.get("info", {}).get("mint")
                if mint:
                    return mint
    return None


async def _solana_ws_listener():
    """Listen for new Solana token events via Helius WebSocket."""
    try:
        import websockets
    except ImportError:
        logger.warning("websockets not installed — Solana WS listener disabled")
        return

    from live_data.collector.config import CollectorSettings

    try:
        settings = CollectorSettings()
    except Exception:
        logger.warning("No HELIUS_API_KEY — Solana WS listener disabled")
        return

    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={settings.HELIUS_API_KEY}"
    rpc_url = settings.helius_rpc_url
    _TOKEN_PROGRAM = "TokenkegQEcnFiGhC7t8qkgAUNp84Xc7ELb8vxTG1VH6"
    _new_mints: asyncio.Queue[str] = asyncio.Queue(maxsize=100)

    async def _process_queue():
        """Scan newly discovered mints from WebSocket."""
        while True:
            mint = await _new_mints.get()
            try:
                result = await collect_features(mint)
                item = _map_token_list_item(result)
                async with _cache_lock:
                    _token_cache.insert(0, item)
                    if len(_token_cache) > 30:
                        _token_cache[:] = _token_cache[:30]
                if _ws_mgr.count > 0:
                    await _ws_mgr.broadcast({"type": "new_token", "data": item})
                logger.info(f"Solana WS: new token {item.get('symbol', '???')} risk={item.get('riskScore')}")
            except Exception as e:
                logger.error(f"Solana WS scan failed for {mint[:12]}: {e}")

    asyncio.create_task(_process_queue())

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                logger.info("✓ Connected to Solana WebSocket (Helius)")
                await ws.send(json_mod.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [_TOKEN_PROGRAM]},
                        {"commitment": "confirmed"},
                    ],
                }))
                async for raw in ws:
                    try:
                        msg = json_mod.loads(raw)
                        value = (msg.get("params") or {}).get("result", {}).get("value", {})
                        logs = value.get("logs") or []
                        sig = value.get("signature")
                        if sig and any("InitializeMint" in l for l in logs):
                            try:
                                mint = await _resolve_mint_from_sig(sig, rpc_url)
                                if mint and not _new_mints.full():
                                    await _new_mints.put(mint)
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Solana WS disconnected: {e}, reconnecting in 10s")
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_task = asyncio.create_task(_background_refresh_loop())
    solana_task = asyncio.create_task(_solana_ws_listener())
    yield
    refresh_task.cancel()
    solana_task.cancel()


app = FastAPI(title="DeFi Sentinel API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/scan/{mint}")
async def scan_token(mint: str):
    """Scan a single token and return frontend-shaped result."""
    if len(mint) < 32 or len(mint) > 50:
        raise HTTPException(status_code=400, detail="Invalid mint address length")

    try:
        result = await collect_features(mint)
    except Exception as e:
        logger.error(f"Scan failed for {mint}: {e}")
        raise HTTPException(status_code=502, detail=f"Data collection failed: {e}")

    return _map_scan_result(result)


@app.get("/api/tokens")
async def list_tokens():
    """Return cached token list for LivePoolMonitor."""
    async with _cache_lock:
        return _token_cache


@app.post("/api/tokens/refresh")
async def refresh_tokens():
    """Trigger an immediate rescan of new pool tokens."""
    await _refresh_token_cache()
    async with _cache_lock:
        return _token_cache


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket for real-time token updates."""
    await _ws_mgr.connect(ws)
    try:
        # Send current cache immediately
        async with _cache_lock:
            await ws.send_json({"type": "tokens", "data": _token_cache})
        # Keep alive — wait for disconnect
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_mgr.disconnect(ws)


@app.get("/api/model-stats")
async def model_stats():
    """Return ML model metadata and performance metrics."""
    meta = get_model_meta()
    if not meta:
        return {"loaded": False, "message": "ML model not loaded"}
    return {
        "loaded": True,
        "version": meta.get("model_version"),
        "features_count": meta.get("features_count"),
        "auc_roc": meta.get("metrics", {}).get("auc_roc"),
        "mcc": meta.get("metrics", {}).get("mcc"),
        "deployer_importance_pct": meta.get("deployer_importance_pct"),
        "top_features": meta.get("top_features", [])[:10],
    }


@app.post("/api/create-checkout")
async def create_checkout(body: dict):
    """Create a Stripe checkout session."""
    if not _STRIPE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Stripe not configured — add STRIPE_SECRET_KEY to .env",
        )

    plan = body.get("plan", "")
    if plan not in _PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    cfg = _PLAN_PRICES[plan]
    origin = "http://localhost:5173"

    try:
        session = _stripe.checkout.Session.create(
            mode=cfg["mode"],
            line_items=[{"price": cfg["price_id"], "quantity": 1}],
            success_url=f"{origin}/pricing?checkout=success",
            cancel_url=f"{origin}/pricing?checkout=cancel",
        )
        return {"url": session.url}
    except Exception as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
