import logging

import httpx

from ..base_client import BaseClient

logger = logging.getLogger("collector.helius")

METADATA_TIMEOUT = 2.0


class HeliusClient(BaseClient):
    name = "helius"

    async def collect(self, mint: str, **kwargs) -> dict:
        features = self._empty()
        asset = await self._rpc_call("getAsset", {"id": mint})
        if not asset:
            return features

        # Content / metadata
        content = asset.get("content") or {}
        metadata = content.get("metadata") or {}
        token_info = asset.get("token_info") or {}
        links = content.get("links") or {}

        features["token_name"] = metadata.get("name") or None
        features["token_symbol"] = metadata.get("symbol") or None
        features["token_standard"] = metadata.get("token_standard") or None
        features["token_decimals"] = token_info.get("decimals")
        features["token_program"] = token_info.get("token_program") or None

        # Supply (human-readable)
        raw_supply = token_info.get("supply")
        decimals = token_info.get("decimals")
        if raw_supply is not None and decimals is not None:
            try:
                features["token_supply"] = int(raw_supply) / (10 ** int(decimals))
            except (ValueError, TypeError, OverflowError):
                features["token_supply"] = None
        else:
            features["token_supply"] = None

        # Authorities
        authorities = asset.get("authorities") or []
        mint_auth = None
        freeze_auth = None
        creator_address = None
        update_authority = None

        for auth in authorities:
            scopes = auth.get("scopes", [])
            address = auth.get("address", "")
            if update_authority is None and address:
                update_authority = address
            if "full" in scopes or "mint" in scopes:
                mint_auth = address
                if creator_address is None:
                    creator_address = address
            if "freeze" in scopes:
                freeze_auth = address

        # Fallback creator from creators list
        if creator_address is None:
            creators = asset.get("creators") or []
            if creators:
                creator_address = creators[0].get("address")

        features["mint_authority"] = mint_auth
        features["mint_authority_revoked"] = mint_auth is None
        features["freeze_authority"] = freeze_auth
        features["freeze_authority_revoked"] = freeze_auth is None
        features["update_authority"] = update_authority
        features["is_mutable"] = bool(asset.get("mutable", False))
        features["creator_address"] = creator_address

        # Metadata URI
        json_uri = content.get("json_uri") or ""
        features["metadata_uri"] = json_uri or None
        features["has_image"] = bool(links.get("image"))

        # Fetch metadata JSON if URI exists
        meta_json = None
        if json_uri:
            meta_json = await self._fetch_metadata(json_uri)

        features["metadata_uri_reachable"] = meta_json is not None

        if meta_json and isinstance(meta_json, dict):
            features["has_description"] = bool(meta_json.get("description"))
            ext_links = meta_json.get("extensions") or {}
            features["has_website"] = bool(
                ext_links.get("website") or links.get("website")
            )
            features["has_twitter"] = bool(
                ext_links.get("twitter") or links.get("twitter")
            )
            features["has_telegram"] = bool(
                ext_links.get("telegram") or links.get("telegram")
            )
        else:
            features["has_description"] = bool(links.get("description")) if links else False
            features["has_website"] = bool(links.get("website"))
            features["has_twitter"] = bool(links.get("twitter"))
            features["has_telegram"] = bool(links.get("telegram"))

        return features

    async def _fetch_metadata(self, uri: str) -> dict | None:
        try:
            resp = await self.client.get(uri, timeout=METADATA_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    def _empty() -> dict:
        return {
            "token_name": None,
            "token_symbol": None,
            "token_decimals": None,
            "token_supply": None,
            "mint_authority": None,
            "mint_authority_revoked": None,
            "freeze_authority": None,
            "freeze_authority_revoked": None,
            "update_authority": None,
            "is_mutable": None,
            "token_standard": None,
            "token_program": None,
            "metadata_uri": None,
            "metadata_uri_reachable": None,
            "has_image": None,
            "has_description": None,
            "has_website": None,
            "has_twitter": None,
            "has_telegram": None,
            "creator_address": None,
        }
