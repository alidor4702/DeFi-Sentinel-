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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from live_data.collector import collect_features, CollectionResult  # noqa: E402

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
_SCAN_CONCURRENCY = 3


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

    risk_score = _heuristic_risk_score(f)
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
            "mlConfidence": 0,
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
    risk_score = _heuristic_risk_score(f)
    liquidity = _first(f.get("gt_reserve_usd"), f.get("rc_total_market_liquidity")) or 0

    # Determine color from risk
    if risk_score >= 70:
        color = "#ef4444"
    elif risk_score >= 40:
        color = "#f59e0b"
    else:
        color = "#00e5a0"

    return {
        "id": result.mint,
        "name": f.get("token_name") or "Unknown",
        "symbol": f.get("token_symbol") or "???",
        "mint": result.mint,
        "holders": 0,
        "liquidity": liquidity,
        "riskScore": risk_score,
        "color": color,
        "geckoTerminalUrl": f"https://www.geckoterminal.com/solana/tokens/{result.mint}",
        "price": _first(f.get("jup_price_usd"), f.get("gt_base_token_price_usd")),
        "volume24h": _first(f.get("gt_volume_24h"), f.get("jup_daily_volume")),
        "poolAgeHours": f.get("gt_pool_age_hours"),
    }


# ---------------------------------------------------------------------------
# Background token discovery + scanning
# ---------------------------------------------------------------------------

async def _fetch_new_pool_mints(target: int) -> list[str]:
    """Fetch mint addresses from GeckoTerminal new_pools endpoint."""
    url = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
    mints: list[str] = []
    seen: set[str] = set()
    page = 1

    async with httpx.AsyncClient(timeout=15.0) as client:
        while len(mints) < target and page <= 5:
            try:
                resp = await client.get(
                    url,
                    params={"page": page},
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"new_pools page {page} failed: {e}")
                break

            pools = data.get("data") or []
            if not pools:
                break

            for pool in pools:
                relationships = pool.get("relationships") or {}
                base_token = (relationships.get("base_token") or {}).get("data") or {}
                token_id = base_token.get("id") or ""
                mint = token_id[len("solana_"):] if token_id.startswith("solana_") else token_id
                if mint and mint not in seen:
                    seen.add(mint)
                    mints.append(mint)

            page += 1
            await asyncio.sleep(0.5)

    return mints[:target]


async def _refresh_token_cache():
    """Fetch new pool mints and scan each, updating the global cache."""
    global _token_cache
    logger.info("Refreshing token cache...")

    try:
        mints = await _fetch_new_pool_mints(target=_TARGET_TOKENS)
    except Exception as e:
        logger.error(f"Failed to fetch new pool mints: {e}")
        return

    if not mints:
        logger.warning("No mints discovered")
        return

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

    tasks = [asyncio.create_task(_scan_one(mint)) for mint in mints]
    await asyncio.gather(*tasks)

    async with _cache_lock:
        _token_cache = sorted(
            results,
            key=lambda t: t.get("poolAgeHours") if t.get("poolAgeHours") is not None else float("inf"),
        )

    logger.info(f"Token cache refreshed: {len(_token_cache)} tokens")


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

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_background_refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="DeFi Sentinel API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
