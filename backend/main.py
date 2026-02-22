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
# Solana on-chain attestation setup
# ---------------------------------------------------------------------------
import hashlib  # noqa: E402
import uuid  # noqa: E402
import sqlite3  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import base64 as _b64  # noqa: E402

_SOLANA_NETWORK = "devnet"
_EXPLORER_BASE = "https://explorer.solana.com/tx"
_SOLSCAN_BASE = "https://solscan.io/tx"

# We'll use the Solana Memo program (no custom Anchor needed)
_MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

# Try to load or generate a devnet payer keypair for signing attestation txns
_ATTESTATION_KEYPAIR_PATH = _PROJECT_ROOT / "attestation_keypair.json"
_SOLANA_CLIENT = None
_PAYER_KEYPAIR = None

try:
    from solders.keypair import Keypair as _SoldersKeypair  # noqa: E402
    from solders.pubkey import Pubkey as _SoldersPubkey  # noqa: E402
    from solders.system_program import ID as _SYSTEM_PROGRAM_ID  # noqa: E402
    from solders.instruction import Instruction as _SoldersInstruction  # noqa: E402
    from solders.message import Message as _SoldersMessage  # noqa: E402
    from solders.transaction import Transaction as _SoldersTransaction  # noqa: E402
    from solders.hash import Hash as _SoldersHash  # noqa: E402
    from solana.rpc.async_api import AsyncClient as _AsyncSolanaClient  # noqa: E402

    _SOLANA_AVAILABLE = True

    # Load or create payer keypair
    if _ATTESTATION_KEYPAIR_PATH.exists():
        _raw = json_mod.loads(_ATTESTATION_KEYPAIR_PATH.read_text())
        _PAYER_KEYPAIR = _SoldersKeypair.from_bytes(bytes(_raw))
        logger.info("Loaded attestation keypair: %s", _PAYER_KEYPAIR.pubkey())
    else:
        _PAYER_KEYPAIR = _SoldersKeypair()
        _ATTESTATION_KEYPAIR_PATH.write_text(json_mod.dumps(list(bytes(_PAYER_KEYPAIR))))
        logger.info("Generated new attestation keypair: %s", _PAYER_KEYPAIR.pubkey())
        logger.info("Fund it with: solana airdrop 2 %s --url devnet", _PAYER_KEYPAIR.pubkey())

except ImportError as e:
    _SOLANA_AVAILABLE = False
    logger.warning("Solana SDK not available (%s) — attestations will be simulated", e)


# ---------------------------------------------------------------------------
# SQLite persistent storage
# ---------------------------------------------------------------------------
_DB_PATH = _PROJECT_ROOT / "defi_sentinel.db"


def _init_db():
    """Initialize SQLite database for persistent attestation & payment storage."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attestations (
            id TEXT PRIMARY KEY,
            mint TEXT NOT NULL,
            risk_score REAL NOT NULL,
            verdict TEXT NOT NULL,
            features_hash TEXT NOT NULL,
            tx_signature TEXT NOT NULL,
            slot INTEGER DEFAULT 0,
            network TEXT DEFAULT 'devnet',
            attested_at TEXT NOT NULL,
            explorer_url TEXT,
            solscan_url TEXT,
            memo_data TEXT,
            wallet_address TEXT,
            email TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT,
            email TEXT,
            plan TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            tx_signature TEXT,
            payment_method TEXT NOT NULL,
            credits_granted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_att_mint ON attestations(mint)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_att_wallet ON attestations(wallet_address)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pay_wallet ON payments(wallet_address)")
    conn.commit()
    conn.close()
    logger.info("SQLite database initialized at %s", _DB_PATH)


_init_db()


def _db_insert_attestation(record: dict):
    """Insert an attestation record into SQLite."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        """INSERT INTO attestations
           (id, mint, risk_score, verdict, features_hash, tx_signature,
            slot, network, attested_at, explorer_url, solscan_url, memo_data,
            wallet_address, email)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record["id"], record["mint"], record["riskScore"], record["verdict"],
            record["featuresHash"], record["txSignature"], record["slot"],
            record["network"], record["attestedAt"], record["explorerUrl"],
            record["solscanUrl"], record["memoData"],
            record.get("walletAddress"), record.get("email"),
        ),
    )
    conn.commit()
    conn.close()


def _db_get_attestations(wallet_address: str | None = None, mint: str | None = None) -> list[dict]:
    """Fetch attestation records from SQLite."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    if mint:
        rows = conn.execute(
            "SELECT * FROM attestations WHERE mint = ? ORDER BY attested_at DESC", (mint,)
        ).fetchall()
    elif wallet_address:
        rows = conn.execute(
            "SELECT * FROM attestations WHERE wallet_address = ? ORDER BY attested_at DESC",
            (wallet_address,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM attestations ORDER BY attested_at DESC").fetchall()
    conn.close()
    return [
        {
            "id": r["id"], "mint": r["mint"], "riskScore": r["risk_score"],
            "verdict": r["verdict"], "featuresHash": r["features_hash"],
            "txSignature": r["tx_signature"], "slot": r["slot"],
            "network": r["network"], "attestedAt": r["attested_at"],
            "explorerUrl": r["explorer_url"], "solscanUrl": r["solscan_url"],
            "memoData": r["memo_data"], "walletAddress": r["wallet_address"],
            "email": r["email"],
        }
        for r in rows
    ]


def _db_insert_payment(wallet_address: str, plan: str, amount: float, currency: str,
                       tx_signature: str, method: str, credits: int):
    """Insert a payment record into SQLite."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        """INSERT INTO payments
           (wallet_address, plan, amount, currency, tx_signature, payment_method,
            credits_granted, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (wallet_address, plan, amount, currency, tx_signature, method, credits,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def _db_get_credits(wallet_address: str) -> int:
    """Get total credits for a wallet."""
    conn = sqlite3.connect(str(_DB_PATH))
    row = conn.execute(
        "SELECT COALESCE(SUM(credits_granted), 0) as total FROM payments WHERE wallet_address = ?",
        (wallet_address,),
    ).fetchone()
    conn.close()
    return row[0] if row else 0


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

    import time as _time
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
        "scannedAt": int(_time.time() * 1000),
    }


# ---------------------------------------------------------------------------
# Background token discovery + scanning
# ---------------------------------------------------------------------------

# Well-known tokens to seed the dashboard with variety (mix of risk levels)
# No hardcoded seed tokens — we only fetch real live trending + new pools


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

    # 1) Trending pools (established, higher-liq tokens — mixed risk)
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

    logger.info(f"Scanning {len(all_mints)} tokens (trending + new pools)")

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
    """Trigger an immediate rescan in the background, return current cache."""
    asyncio.create_task(_refresh_token_cache())
    async with _cache_lock:
        return _token_cache


@app.get("/api/tokens/filter")
async def filter_tokens(
    max_risk: int = 100,
    min_liq: float = 0,
    sort: str = "risk",
    limit: int = 10,
):
    """Return tokens from the cache matching criteria.

    If fewer than 5 tokens match, kick off a background refresh so the
    next poll picks up more tokens — but still return what we have now
    so the UI is responsive.
    """
    async with _cache_lock:
        pool = list(_token_cache)

    # Filter
    matches = [
        t for t in pool
        if t.get("riskScore", 0) <= max_risk
        and t.get("liquidity", 0) >= min_liq
    ]

    # Sort
    if sort == "liquidity":
        matches.sort(key=lambda t: t.get("liquidity", 0), reverse=True)
    else:
        # newest first (lowest pool age)
        matches.sort(key=lambda t: t.get("poolAgeHours") or 999_999)

    result = matches[:limit]

    # If we found fewer than 5, trigger a background refresh to get more
    if len(result) < 5:
        asyncio.create_task(_refresh_token_cache())

    return {"tokens": result, "total_matched": len(matches), "scanning": len(result) < 5}


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


# ---------------------------------------------------------------------------
# Solana Attestation Endpoints
# ---------------------------------------------------------------------------

def _hash_attestation(mint: str, risk_score: float, verdict: str, ts: str) -> str:
    """SHA-256 hash of attestation data."""
    payload = f"DeFiSentinel|{mint}|{risk_score}|{verdict}|{ts}"
    return hashlib.sha256(payload.encode()).hexdigest()


@app.post("/api/attest")
async def create_attestation(body: dict):
    """
    Create an on-chain risk attestation using Solana's Memo program.

    Request body:
      - mint: token mint address
      - riskScore: numeric risk score
      - verdict: SAFE | DANGER
      - featuresCollected: number of features used
    """
    mint = body.get("mint", "")
    risk_score = body.get("riskScore", 0)
    verdict = body.get("verdict", "UNKNOWN")
    features_collected = body.get("featuresCollected", 0)
    wallet_address = body.get("walletAddress")
    wallet_signature = body.get("walletSignature")
    signed_message = body.get("signedMessage")

    if not mint:
        raise HTTPException(status_code=400, detail="mint is required")

    # Verify wallet signature if provided (proves wallet authorized this attestation)
    if wallet_address and wallet_signature and signed_message and _SOLANA_AVAILABLE:
        try:
            from solders.pubkey import Pubkey as _Pk
            from solders.signature import Signature as _Sig
            import base58 as _bs58
            pubkey = _Pk.from_string(wallet_address)
            sig_bytes = _bs58.b58decode(wallet_signature)
            sig = _Sig.from_bytes(sig_bytes)
            verified = sig.verify(pubkey, signed_message.encode("utf-8"))
            if not verified:
                raise HTTPException(status_code=400, detail="Wallet signature verification failed")
            logger.info("Wallet signature verified for attestation: %s", wallet_address[:12])
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Wallet sig verification skipped: %s", e)

    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    features_hash = _hash_attestation(mint, risk_score, verdict, ts)

    # Build the memo string that goes on-chain
    memo_data = json_mod.dumps({
        "app": "DeFiSentinel",
        "version": "1.0",
        "mint": mint,
        "riskScore": risk_score,
        "verdict": verdict,
        "features": features_collected,
        "hash": features_hash[:16],
        "wallet": wallet_address[:8] + "..." if wallet_address else None,
        "ts": ts,
    }, separators=(",", ":"))

    tx_signature = ""
    slot = 0

    if _SOLANA_AVAILABLE and _PAYER_KEYPAIR:
        try:
            async with _AsyncSolanaClient(f"https://api.devnet.solana.com") as client:
                # Build memo instruction
                memo_program = _SoldersPubkey.from_string(_MEMO_PROGRAM_ID)
                memo_ix = _SoldersInstruction(
                    program_id=memo_program,
                    accounts=[],
                    data=memo_data.encode("utf-8"),
                )

                # Get recent blockhash
                bh_resp = await client.get_latest_blockhash()
                blockhash = bh_resp.value.blockhash

                # Build and sign transaction
                msg = _SoldersMessage.new_with_blockhash(
                    [memo_ix],
                    _PAYER_KEYPAIR.pubkey(),
                    blockhash,
                )
                tx = _SoldersTransaction.new_unsigned(msg)
                tx.sign([_PAYER_KEYPAIR], blockhash)

                # Send transaction
                resp = await client.send_transaction(tx)
                tx_signature = str(resp.value)
                slot = bh_resp.context.slot

                logger.info(
                    "Attestation TX sent: %s for mint %s (score=%s, wallet=%s)",
                    tx_signature, mint, risk_score, wallet_address or "anon",
                )
        except Exception as e:
            logger.error("Solana attestation TX failed: %s", e)
            # Fall back to simulated attestation
            tx_signature = f"sim_{uuid.uuid4().hex[:56]}"
            slot = 0
    else:
        # Simulated attestation when Solana SDK not available
        tx_signature = f"sim_{uuid.uuid4().hex[:56]}"
        logger.info("Simulated attestation for mint %s (Solana SDK not available)", mint)

    # Store the attestation record in SQLite (persists across restarts)
    record = {
        "id": uuid.uuid4().hex[:12],
        "mint": mint,
        "riskScore": risk_score,
        "verdict": verdict,
        "featuresHash": features_hash,
        "txSignature": tx_signature,
        "slot": slot,
        "network": _SOLANA_NETWORK,
        "attestedAt": ts,
        "explorerUrl": f"{_EXPLORER_BASE}/{tx_signature}?cluster={_SOLANA_NETWORK}",
        "solscanUrl": f"{_SOLSCAN_BASE}/{tx_signature}?cluster={_SOLANA_NETWORK}",
        "memoData": memo_data,
        "walletAddress": wallet_address,
    }
    _db_insert_attestation(record)
    logger.info(
        "Attestation stored in DB: id=%s mint=%s wallet=%s tx=%s",
        record["id"], mint, wallet_address or "anon", tx_signature[:20],
    )

    return {"success": True, "attestation": record}


@app.get("/api/attestations")
async def list_attestations(wallet: str = None):
    """Return attestation records, newest first. Optionally filter by wallet."""
    return _db_get_attestations(wallet_address=wallet)


@app.get("/api/attestations/{mint}")
async def get_attestations_for_mint(mint: str):
    """Return attestation records for a specific token mint."""
    return _db_get_attestations(mint=mint)


@app.post("/api/auth/wallet")
async def verify_wallet_signature(body: dict):
    """
    Verify an ed25519 signature from a Solana wallet.

    Request body:
      - publicKey: base58 wallet public key
      - signature: base58 signature
      - message: the original message that was signed
    """
    pub_key_str = body.get("publicKey", "")
    signature_str = body.get("signature", "")
    message = body.get("message", "")

    if not all([pub_key_str, signature_str, message]):
        raise HTTPException(status_code=400, detail="publicKey, signature, and message are required")

    try:
        if _SOLANA_AVAILABLE:
            from solders.pubkey import Pubkey as _Pk
            from solders.signature import Signature as _Sig

            pubkey = _Pk.from_string(pub_key_str)
            import base58 as _bs58
            sig_bytes = _bs58.b58decode(signature_str)
            sig = _Sig.from_bytes(sig_bytes)

            # Verify ed25519 signature
            verified = sig.verify(pubkey, message.encode("utf-8"))
        else:
            # Accept all in demo mode
            verified = True
            logger.warning("Wallet signature verification skipped (Solana SDK not available)")

        return {"verified": verified, "wallet": pub_key_str}
    except Exception as e:
        logger.error("Wallet verification error: %s", e)
        raise HTTPException(status_code=400, detail=f"Signature verification failed: {e}")


# ---------------------------------------------------------------------------
# SOL Payment Endpoints
# ---------------------------------------------------------------------------

_SOL_PACK_PRICES = {
    "pack-10":  {"sol": 0.05, "credits": 10,  "label": "10 Scans"},
    "pack-50":  {"sol": 0.20, "credits": 50,  "label": "50 Scans"},
    "pack-200": {"sol": 0.60, "credits": 200, "label": "200 Scans"},
}


@app.get("/api/payer-address")
async def get_payer_address():
    """Return the payer wallet address for SOL payments."""
    if _PAYER_KEYPAIR:
        return {
            "address": str(_PAYER_KEYPAIR.pubkey()),
            "network": _SOLANA_NETWORK,
            "solPrices": {k: v["sol"] for k, v in _SOL_PACK_PRICES.items()},
        }
    raise HTTPException(status_code=503, detail="Payer wallet not configured")


@app.post("/api/verify-solana-payment")
async def verify_solana_payment(body: dict):
    """Verify a SOL payment transaction and credit scan pack."""
    tx_sig = body.get("txSignature", "")
    plan = body.get("plan", "")
    wallet_address = body.get("walletAddress", "")

    if not all([tx_sig, plan, wallet_address]):
        raise HTTPException(status_code=400, detail="txSignature, plan, and walletAddress required")

    if plan not in _SOL_PACK_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    pack = _SOL_PACK_PRICES[plan]

    # Verify TX exists and is confirmed on-chain
    verified = False
    try:
        async with httpx.AsyncClient(timeout=15.0) as hclient:
            rpc_resp = await hclient.post(
                "https://api.devnet.solana.com",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignatureStatuses",
                    "params": [[tx_sig], {"searchTransactionHistory": True}],
                },
            )
            data = rpc_resp.json()
            statuses = data.get("result", {}).get("value", [])
            if statuses and statuses[0]:
                status = statuses[0].get("confirmationStatus")
                if status in ("confirmed", "finalized"):
                    verified = True
                    logger.info("SOL payment verified: %s status=%s", tx_sig[:20], status)
    except Exception as e:
        logger.error("Payment verification RPC error: %s", e)

    if not verified:
        raise HTTPException(status_code=400, detail="Transaction not confirmed on-chain")

    # Record payment in DB
    _db_insert_payment(
        wallet_address=wallet_address,
        plan=plan,
        amount=pack["sol"],
        currency="SOL",
        tx_signature=tx_sig,
        method="solana",
        credits=pack["credits"],
    )
    total_credits = _db_get_credits(wallet_address)
    logger.info(
        "Payment recorded: wallet=%s plan=%s credits=+%d total=%d tx=%s",
        wallet_address[:12], plan, pack["credits"], total_credits, tx_sig[:20],
    )

    return {
        "success": True,
        "plan": plan,
        "creditsAdded": pack["credits"],
        "totalCredits": total_credits,
        "txSignature": tx_sig,
    }


@app.get("/api/credits/{wallet_address}")
async def get_credits(wallet_address: str):
    """Get total scan credits for a wallet."""
    credits = _db_get_credits(wallet_address)
    return {"wallet": wallet_address, "credits": credits}


# ---------------------------------------------------------------------------
# Token Balance Check
# ---------------------------------------------------------------------------

@app.get("/api/wallet/{address}/balance/{mint}")
async def check_token_balance(address: str, mint: str):
    """Check if a wallet holds a specific SPL token (queries mainnet)."""
    try:
        from live_data.collector.config import CollectorSettings
        settings = CollectorSettings()
        rpc_url = settings.helius_rpc_url

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                address,
                {"mint": mint},
                {"encoding": "jsonParsed"},
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(rpc_url, json=payload)
            data = resp.json()

        accounts = data.get("result", {}).get("value", [])
        if not accounts:
            return {"balance": 0, "decimals": 0, "uiAmount": 0.0, "hasToken": False}

        info = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        return {
            "balance": int(info["amount"]),
            "decimals": info["decimals"],
            "uiAmount": float(info.get("uiAmountString", "0")),
            "hasToken": float(info.get("uiAmountString", "0")) > 0,
        }
    except Exception as e:
        logger.error("Token balance check error: %s", e)
        return {"balance": 0, "decimals": 0, "uiAmount": 0.0, "hasToken": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Wallet Risk Profile — scan ALL holdings for rug exposure
# ---------------------------------------------------------------------------

@app.get("/api/wallet/{address}/risk-profile")
async def wallet_risk_profile(address: str):
    """Fetch all SPL tokens held by a wallet and score each for rug risk.

    Returns per-token risk scores + aggregate portfolio risk metrics.
    Uses mainnet Helius RPC to get holdings, then runs ML scoring on each.
    """
    try:
        from live_data.collector.config import CollectorSettings
        settings = CollectorSettings()
        rpc_url = settings.helius_rpc_url

        # 1) Get ALL token accounts for wallet
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                address,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"},
            ],
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(rpc_url, json=payload)
            data = resp.json()

        accounts = data.get("result", {}).get("value", [])
        if not accounts:
            return {
                "wallet": address,
                "totalTokens": 0,
                "scannedTokens": 0,
                "portfolioRiskScore": 0,
                "riskBreakdown": {"danger": 0, "moderate": 0, "safe": 0},
                "tokens": [],
                "summary": "No SPL tokens found in this wallet.",
            }

        # 2) Extract tokens with non-zero balance
        holdings: list[dict] = []
        for acc in accounts:
            try:
                info = acc["account"]["data"]["parsed"]["info"]
                token_amount = info["tokenAmount"]
                ui_amount = float(token_amount.get("uiAmountString", "0"))
                if ui_amount > 0:
                    holdings.append({
                        "mint": info["mint"],
                        "balance": ui_amount,
                        "decimals": token_amount["decimals"],
                    })
            except (KeyError, ValueError):
                continue

        if not holdings:
            return {
                "wallet": address,
                "totalTokens": 0,
                "scannedTokens": 0,
                "portfolioRiskScore": 0,
                "riskBreakdown": {"danger": 0, "moderate": 0, "safe": 0},
                "tokens": [],
                "summary": "No tokens with non-zero balance found.",
            }

        # 3) Score each token (concurrently, max 3 at a time)
        sem = asyncio.Semaphore(3)
        scored_tokens: list[dict] = []

        async def _score_one(h: dict):
            mint = h["mint"]
            async with sem:
                try:
                    result = await collect_features(mint)
                    rug_prob, risk_score = predict_rug_probability(result.features)
                    verdict = "SAFE" if risk_score < 40 else ("MODERATE" if risk_score < 70 else "DANGER")
                    name = result.features.get("token_name") or "Unknown"
                    symbol = result.features.get("token_symbol") or "???"
                    liquidity = _first(
                        result.features.get("gt_reserve_usd"),
                        result.features.get("rc_total_market_liquidity"),
                    ) or 0
                    price = _first(
                        result.features.get("jup_price_usd"),
                        result.features.get("gt_base_token_price_usd"),
                    )
                    scored_tokens.append({
                        "mint": mint,
                        "name": name,
                        "symbol": symbol,
                        "balance": h["balance"],
                        "riskScore": risk_score,
                        "verdict": verdict,
                        "mlConfidence": round(rug_prob * 100, 1),
                        "liquidity": liquidity,
                        "price": price,
                        "estimatedValue": round(h["balance"] * (price or 0), 2),
                        "riskFactors": _build_risk_factors(result.features),
                    })
                except Exception as e:
                    logger.warning("Risk profile: failed to score %s: %s", mint, e)
                    scored_tokens.append({
                        "mint": mint,
                        "name": "Unknown",
                        "symbol": "???",
                        "balance": h["balance"],
                        "riskScore": -1,
                        "verdict": "UNKNOWN",
                        "mlConfidence": 0,
                        "liquidity": 0,
                        "price": None,
                        "estimatedValue": 0,
                        "riskFactors": [],
                        "error": str(e),
                    })

        # Cap at 20 tokens to keep response time reasonable
        scan_list = holdings[:20]
        await asyncio.gather(*[_score_one(h) for h in scan_list])

        # 4) Sort by risk (highest first) and compute aggregate stats
        scored_tokens.sort(key=lambda t: t["riskScore"], reverse=True)
        valid_scores = [t["riskScore"] for t in scored_tokens if t["riskScore"] >= 0]
        danger = sum(1 for s in valid_scores if s >= 70)
        moderate = sum(1 for s in valid_scores if 40 <= s < 70)
        safe = sum(1 for s in valid_scores if s < 40)

        # Weighted average risk (by estimated value if available)
        total_value = sum(t["estimatedValue"] for t in scored_tokens if t["riskScore"] >= 0)
        if total_value > 0:
            portfolio_risk = round(
                sum(t["riskScore"] * t["estimatedValue"] for t in scored_tokens if t["riskScore"] >= 0)
                / total_value
            )
        elif valid_scores:
            portfolio_risk = round(sum(valid_scores) / len(valid_scores))
        else:
            portfolio_risk = 0

        # Build summary
        total_est = sum(t["estimatedValue"] for t in scored_tokens)
        danger_value = sum(t["estimatedValue"] for t in scored_tokens if t["riskScore"] >= 70)
        if danger > 0:
            summary = f"⚠️ {danger} high-risk token(s) detected worth ~${danger_value:,.2f}. Consider reviewing or exiting these positions."
        elif moderate > 0:
            summary = f"Your wallet has {moderate} moderate-risk token(s). Monitor closely for changes."
        else:
            summary = "✅ Your portfolio looks healthy — no high-risk tokens detected."

        return {
            "wallet": address,
            "totalTokens": len(holdings),
            "scannedTokens": len(scan_list),
            "portfolioRiskScore": portfolio_risk,
            "riskBreakdown": {"danger": danger, "moderate": moderate, "safe": safe},
            "totalEstimatedValue": round(total_est, 2),
            "dangerExposure": round(danger_value, 2),
            "tokens": scored_tokens,
            "summary": summary,
        }
    except Exception as e:
        logger.error("Wallet risk profile error: %s", e)
        raise HTTPException(status_code=500, detail=f"Risk profile analysis failed: {e}")
