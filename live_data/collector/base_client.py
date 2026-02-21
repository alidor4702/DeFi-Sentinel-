import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from .config import CollectorSettings

logger = logging.getLogger("collector")


class BaseClient(ABC):
    """Base class with retry/backoff for all API clients."""

    name: str = "base"

    def __init__(self, settings: CollectorSettings):
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.settings.REQUEST_TIMEOUT)
        return self._client

    async def _request(
        self, method: str, url: str, **kwargs
    ) -> dict | list | None:
        """HTTP request with retries and exponential backoff."""
        for attempt in range(self.settings.MAX_RETRIES):
            try:
                resp = await self.client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    wait = 1.0 * (2 ** attempt)
                    logger.warning(f"{self.name}: rate limited, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException:
                logger.warning(
                    f"{self.name}: timeout attempt {attempt + 1}/{self.settings.MAX_RETRIES}"
                )
                await asyncio.sleep(1.0 * (2 ** attempt))
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"{self.name}: HTTP {e.response.status_code} attempt {attempt + 1}"
                )
                if e.response.status_code >= 500:
                    await asyncio.sleep(1.0 * (2 ** attempt))
                    continue
                return None
            except Exception as e:
                logger.error(f"{self.name}: error {e}, attempt {attempt + 1}")
                await asyncio.sleep(1.0 * (2 ** attempt))
        return None

    async def _rpc_call(self, method: str, params: dict | list) -> dict | None:
        """JSON-RPC call to Helius with retries."""
        payload = {
            "jsonrpc": "2.0",
            "id": "defi-sentinel",
            "method": method,
            "params": params,
        }
        for attempt in range(self.settings.MAX_RETRIES):
            try:
                resp = await self.client.post(
                    self.settings.helius_rpc_url, json=payload
                )
                if resp.status_code == 429:
                    wait = 1.0 * (2 ** attempt)
                    logger.warning(f"{self.name}: rate limited, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    logger.error(f"{self.name}: RPC error: {data['error']}")
                    return None
                return data.get("result")
            except httpx.TimeoutException:
                logger.warning(
                    f"{self.name}: timeout attempt {attempt + 1}/{self.settings.MAX_RETRIES}"
                )
                await asyncio.sleep(1.0 * (2 ** attempt))
            except Exception as e:
                logger.error(f"{self.name}: error {e}, attempt {attempt + 1}")
                await asyncio.sleep(1.0 * (2 ** attempt))
        return None

    @abstractmethod
    async def collect(self, mint: str, **kwargs) -> dict:
        """Collect features for a token. Returns {feature_name: value}."""
        ...

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
