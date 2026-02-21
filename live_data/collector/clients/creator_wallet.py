import asyncio
import logging
from datetime import datetime, timezone

from ..base_client import BaseClient

logger = logging.getLogger("collector.creator_wallet")

_MAX_DEPLOYER_CHECK = 10
_RUGCHECK_URL = "https://api.rugcheck.xyz"


class CreatorWalletClient(BaseClient):
    name = "creator_wallet"

    async def collect(self, mint: str, **kwargs) -> dict:
        features = self._empty()
        creator = kwargs.get("creator_address")
        if not creator:
            return features

        bal_task = self._rpc_call("getBalance", [creator])
        assets_task = self._rpc_call(
            "getAssetsByOwner",
            {"ownerAddress": creator, "page": 1, "limit": 1000},
        )
        recent_sigs_task = self._rpc_call(
            "getSignaturesForAddress",
            [creator, {"limit": 1000, "commitment": "confirmed"}],
        )
        # Try BOTH authority and creator lookups — the deployer may be
        # indexed under either depending on the token program / metadata.
        authority_task = self._rpc_call(
            "getAssetsByAuthority",
            {"authorityAddress": creator, "page": 1, "limit": 100},
        )
        creator_assets_task = self._rpc_call(
            "getAssetsByCreator",
            {"creatorAddress": creator, "page": 1, "limit": 100},
        )

        bal, assets, recent_sigs, authority_assets, creator_assets = (
            await asyncio.gather(
                bal_task, assets_task, recent_sigs_task,
                authority_task, creator_assets_task,
            )
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

        # ── Deployer history (rug detection) ──
        # Merge tokens found via authority AND creator lookups (deduplicated)
        await self._check_deployer_history(
            features, authority_assets, creator_assets, mint
        )

        return features

    async def _check_deployer_history(
        self, features: dict, authority_assets, creator_assets, current_mint: str
    ):
        """Check deployer's past tokens for rug history via RugCheck.

        Merges results from getAssetsByAuthority **and** getAssetsByCreator
        since different token programs index the deployer wallet differently.
        """
        seen: set[str] = set()
        past_mints: list[str] = []

        # Collect fungible token mints from both lookups
        for asset_result in (authority_assets, creator_assets):
            if not asset_result or not isinstance(asset_result, dict):
                continue
            for item in asset_result.get("items") or []:
                iface = (item.get("interface") or "").lower()
                item_id = item.get("id") or ""
                if (
                    "fungible" in iface
                    and "nft" not in iface
                    and item_id
                    and item_id != current_mint
                    and item_id not in seen
                ):
                    seen.add(item_id)
                    past_mints.append(item_id)

        features["deployer_past_tokens"] = len(past_mints)

        if not past_mints:
            return

        # Quick-check a subset via RugCheck
        check = past_mints[:_MAX_DEPLOYER_CHECK]

        async def _rc_score(m: str) -> dict | None:
            try:
                return await self._request(
                    "GET", f"{_RUGCHECK_URL}/v1/tokens/{m}/report/summary"
                )
            except Exception:
                return None

        results = await asyncio.gather(*[_rc_score(m) for m in check])

        rugs = labeled = 0
        for r in results:
            if r and isinstance(r, dict) and r.get("score") is not None:
                labeled += 1
                score = r.get("score_normalised") or r.get("score") or 0
                if score < 300:
                    rugs += 1

        # Extrapolate if we only sampled
        total = len(past_mints)
        if labeled > 0 and total > len(check):
            rate = rugs / labeled
            est_labeled = round(labeled * total / len(check))
            est_rugs = round(rate * est_labeled)
        else:
            rate = rugs / max(labeled, 1)
            est_labeled = labeled
            est_rugs = rugs

        features["deployer_past_rugs"] = est_rugs
        features["deployer_past_rug_rate"] = round(rate, 4)
        features["deployer_past_labeled"] = est_labeled
        features["deployer_past_is_serial"] = rate > 0.5 and est_labeled >= 3

    @staticmethod
    def _empty() -> dict:
        return {
            "creator_sol_balance": None,
            "creator_wallet_age_hours": None,
            "creator_token_count": None,
            "creator_tx_count": None,
            "creator_nft_count": None,
            # Deployer history features
            "deployer_past_tokens": 0,
            "deployer_past_rugs": 0,
            "deployer_past_rug_rate": 0.0,
            "deployer_past_labeled": 0,
            "deployer_past_is_serial": False,
        }
