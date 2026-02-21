import asyncio
import logging
import time
from dataclasses import dataclass, field

from .config import CollectorSettings
from .clients import (
    HeliusClient,
    CreatorWalletClient,
    RugCheckClient,
    GeckoTerminalClient,
    JupiterClient,
)
from .derived import compute_derived

logger = logging.getLogger("collector")


@dataclass
class CollectionResult:
    mint: str
    features: dict = field(default_factory=dict)
    latency_ms: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    total_latency_ms: float = 0.0
    features_collected: int = 0


async def collect_features(
    mint: str, settings: CollectorSettings | None = None
) -> CollectionResult:
    """Collect all 81 features for a token mint address."""
    if settings is None:
        settings = CollectorSettings()

    start = time.perf_counter()
    result = CollectionResult(mint=mint)
    all_features: dict = {}

    # Create clients
    helius = HeliusClient(settings)
    creator_wallet = CreatorWalletClient(settings)
    rugcheck = RugCheckClient(settings)
    gecko = GeckoTerminalClient(settings)
    jupiter = JupiterClient(settings)

    all_clients = [helius, creator_wallet, rugcheck, gecko, jupiter]

    try:
        # Phase 1: Helius (need creator_address for phase 2)
        t0 = time.perf_counter()
        helius_features = await helius.collect(mint)
        result.latency_ms["helius"] = round((time.perf_counter() - t0) * 1000, 1)
        all_features.update(helius_features)

        creator_address = helius_features.get("creator_address")

        # Phase 2: Remaining 5 clients in parallel
        async def _timed(name: str, coro):
            t = time.perf_counter()
            try:
                data = await coro
                result.latency_ms[name] = round((time.perf_counter() - t) * 1000, 1)
                return data
            except Exception as e:
                result.latency_ms[name] = round((time.perf_counter() - t) * 1000, 1)
                result.errors.append(f"{name}: {e}")
                logger.error(f"{name} failed: {e}")
                return {}

        phase2 = await asyncio.gather(
            _timed(
                "creator_wallet",
                creator_wallet.collect(mint, creator_address=creator_address),
            ),
            _timed("rugcheck", rugcheck.collect(mint)),
            _timed("geckoterminal", gecko.collect(mint)),
            _timed("jupiter", jupiter.collect(mint)),
        )

        for features in phase2:
            if isinstance(features, dict):
                all_features.update(features)

        # Phase 3: Derived features
        derived = compute_derived(all_features)
        all_features.update(derived)

    finally:
        # Close all clients
        for c in all_clients:
            try:
                await c.close()
            except Exception:
                pass

    result.features = all_features
    result.total_latency_ms = round((time.perf_counter() - start) * 1000, 1)
    result.features_collected = sum(
        1 for v in all_features.values() if v is not None
    )

    return result
