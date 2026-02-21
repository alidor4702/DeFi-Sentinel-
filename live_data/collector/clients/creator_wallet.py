import logging
from datetime import datetime, timezone

from ..base_client import BaseClient

logger = logging.getLogger("collector.creator_wallet")


class CreatorWalletClient(BaseClient):
    name = "creator_wallet"

    async def collect(self, mint: str, **kwargs) -> dict:
        features = self._empty()
        creator = kwargs.get("creator_address")
        if not creator:
            return features

        # Run 3 RPC calls in parallel
        import asyncio

        bal_task = self._rpc_call("getBalance", [creator])
        assets_task = self._rpc_call(
            "getAssetsByOwner",
            {"ownerAddress": creator, "page": 1, "limit": 1000},
        )
        recent_sigs_task = self._rpc_call(
            "getSignaturesForAddress",
            [creator, {"limit": 1000, "commitment": "confirmed"}],
        )

        bal, assets, recent_sigs = await asyncio.gather(
            bal_task, assets_task, recent_sigs_task
        )

        # Balance
        if bal is not None:
            value = bal.get("value", bal) if isinstance(bal, dict) else bal
            try:
                features["creator_sol_balance"] = int(value) / 1e9
            except (ValueError, TypeError):
                pass

        # Wallet age from oldest signature in the batch (last item = oldest)
        if recent_sigs and isinstance(recent_sigs, list) and len(recent_sigs) > 0:
            oldest = recent_sigs[-1]
            block_time = oldest.get("blockTime")
            if block_time:
                age_seconds = datetime.now(timezone.utc).timestamp() - block_time
                features["creator_wallet_age_hours"] = max(0, age_seconds / 3600)

        # Assets by owner
        if assets and isinstance(assets, dict):
            items = assets.get("items") or []
            fungible = 0
            nfts = 0
            for item in items:
                iface = (item.get("interface") or "").lower()
                if "fungible" in iface and "nft" not in iface:
                    fungible += 1
                elif "nft" in iface or "edition" in iface:
                    nfts += 1
            features["creator_token_count"] = fungible
            features["creator_nft_count"] = nfts

        # Tx count from recent signatures
        if recent_sigs and isinstance(recent_sigs, list):
            features["creator_tx_count"] = len(recent_sigs)

        # Placeholder — no internal DB yet
        features["creator_prev_tokens_rugged"] = 0

        return features

    @staticmethod
    def _empty() -> dict:
        return {
            "creator_sol_balance": None,
            "creator_wallet_age_hours": None,
            "creator_token_count": None,
            "creator_tx_count": None,
            "creator_prev_tokens_rugged": 0,
            "creator_nft_count": None,
        }
