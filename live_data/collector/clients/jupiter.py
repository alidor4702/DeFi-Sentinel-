import logging

from ..base_client import BaseClient

logger = logging.getLogger("collector.jupiter")


class JupiterClient(BaseClient):
    name = "jupiter"

    async def collect(self, mint: str, **kwargs) -> dict:
        features = self._empty()

        if not self.settings.JUPITER_API_KEY:
            logger.info("No JUPITER_API_KEY, skipping Jupiter client")
            return features

        base = self.settings.JUPITER_BASE_URL
        headers = {"x-api-key": self.settings.JUPITER_API_KEY}

        # Token search
        search_data = await self._request(
            "GET",
            f"{base}/tokens/v2/search",
            params={"query": mint},
            headers=headers,
        )

        if search_data and isinstance(search_data, list):
            # Find exact match
            token = None
            for t in search_data:
                if t.get("address") == mint or t.get("id") == mint:
                    token = t
                    break

            if token:
                features["jup_listed"] = True
                features["jup_strict_list"] = bool(
                    token.get("isVerified")
                    or "verified" in (token.get("tags") or [])
                )
                features["jup_tags"] = token.get("tags") or []
                stats = token.get("stats24h") or {}
                buy_vol = stats.get("buyVolume") or 0
                sell_vol = stats.get("sellVolume") or 0
                total = buy_vol + sell_vol
                if total > 0:
                    features["jup_daily_volume"] = float(total)
            else:
                features["jup_listed"] = False

        # Price API
        price_data = await self._request(
            "GET",
            f"{base}/price/v3",
            params={"ids": mint},
            headers=headers,
        )

        if price_data and isinstance(price_data, dict):
            token_price = price_data.get(mint) or (price_data.get("data") or {}).get(mint) or {}
            price = token_price.get("usdPrice")
            if price is not None:
                try:
                    features["jup_price_usd"] = float(price)
                except (ValueError, TypeError):
                    pass

        return features

    @staticmethod
    def _empty() -> dict:
        return {
            "jup_listed": None,
            "jup_strict_list": None,
            "jup_daily_volume": None,
            "jup_price_usd": None,
            "jup_tags": None,
        }
