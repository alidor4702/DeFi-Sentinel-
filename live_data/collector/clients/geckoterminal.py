import logging
from datetime import datetime, timezone

from ..base_client import BaseClient

logger = logging.getLogger("collector.geckoterminal")


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class GeckoTerminalClient(BaseClient):
    name = "geckoterminal"

    async def collect(self, mint: str, **kwargs) -> dict:
        features = self._empty()
        base = self.settings.GECKOTERMINAL_BASE_URL

        data = await self._request(
            "GET",
            f"{base}/api/v2/networks/solana/tokens/{mint}/pools",
            params={"page": 1},
            headers={"Accept": "application/json"},
        )

        if not data or not isinstance(data, dict):
            return features

        pools = data.get("data") or []
        features["gt_pool_count"] = len(pools)

        if not pools:
            return features

        # Use first pool (highest liquidity by default)
        pool = pools[0]
        attrs = pool.get("attributes") or {}

        features["gt_pool_address"] = attrs.get("address")
        features["gt_pool_name"] = attrs.get("name")

        # DEX
        dex_data = (pool.get("relationships") or {}).get("dex", {}).get("data") or {}
        features["gt_dex"] = dex_data.get("id")

        # Prices
        features["gt_base_token_price_usd"] = _safe_float(
            attrs.get("base_token_price_usd")
        )
        features["gt_quote_token_price_usd"] = _safe_float(
            attrs.get("quote_token_price_usd")
        )
        features["gt_fdv_usd"] = _safe_float(attrs.get("fdv_usd"))
        features["gt_market_cap_usd"] = _safe_float(attrs.get("market_cap_usd"))
        features["gt_reserve_usd"] = _safe_float(attrs.get("reserve_in_usd"))

        # Volume
        volume = attrs.get("volume_usd") or {}
        features["gt_volume_5m"] = _safe_float(volume.get("m5"))
        features["gt_volume_1h"] = _safe_float(volume.get("h1"))
        features["gt_volume_6h"] = _safe_float(volume.get("h6"))
        features["gt_volume_24h"] = _safe_float(volume.get("h24"))

        # Price changes
        price_change = attrs.get("price_change_percentage") or {}
        features["gt_price_change_5m"] = _safe_float(price_change.get("m5"))
        features["gt_price_change_1h"] = _safe_float(price_change.get("h1"))
        features["gt_price_change_6h"] = _safe_float(price_change.get("h6"))
        features["gt_price_change_24h"] = _safe_float(price_change.get("h24"))

        # Transactions
        txns = attrs.get("transactions") or {}
        for period in ("m5", "h1", "h24"):
            period_data = txns.get(period) or {}
            buys = period_data.get("buys", 0) or 0
            sells = period_data.get("sells", 0) or 0
            suffix = {"m5": "5m", "h1": "1h", "h24": "24h"}[period]
            features[f"gt_tx_count_{suffix}_buys"] = buys
            features[f"gt_tx_count_{suffix}_sells"] = sells

        # Buy/sell ratio 1h
        h1_buys = features.get("gt_tx_count_1h_buys") or 0
        h1_sells = features.get("gt_tx_count_1h_sells") or 0
        features["gt_buy_sell_ratio_1h"] = h1_buys / (h1_sells + 1)

        # Pool age
        created_at = attrs.get("pool_created_at")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_hours = (
                    datetime.now(timezone.utc) - created
                ).total_seconds() / 3600
                features["gt_pool_age_hours"] = max(0, age_hours)
            except (ValueError, TypeError):
                pass

        return features

    @staticmethod
    def _empty() -> dict:
        return {
            "gt_pool_count": 0,
            "gt_pool_address": None,
            "gt_pool_name": None,
            "gt_dex": None,
            "gt_base_token_price_usd": None,
            "gt_quote_token_price_usd": None,
            "gt_fdv_usd": None,
            "gt_market_cap_usd": None,
            "gt_reserve_usd": None,
            "gt_volume_5m": None,
            "gt_volume_1h": None,
            "gt_volume_6h": None,
            "gt_volume_24h": None,
            "gt_price_change_5m": None,
            "gt_price_change_1h": None,
            "gt_price_change_6h": None,
            "gt_price_change_24h": None,
            "gt_tx_count_5m_buys": None,
            "gt_tx_count_5m_sells": None,
            "gt_tx_count_1h_buys": None,
            "gt_tx_count_1h_sells": None,
            "gt_tx_count_24h_buys": None,
            "gt_tx_count_24h_sells": None,
            "gt_buy_sell_ratio_1h": None,
            "gt_pool_age_hours": None,
        }
