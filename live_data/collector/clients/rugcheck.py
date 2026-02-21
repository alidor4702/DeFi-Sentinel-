import logging

from ..base_client import BaseClient

logger = logging.getLogger("collector.rugcheck")


class RugCheckClient(BaseClient):
    name = "rugcheck"

    async def collect(self, mint: str, **kwargs) -> dict:
        features = self._empty()
        base = self.settings.RUGCHECK_BASE_URL

        # Fetch summary (canonical score) and full report (richer data) in parallel
        import asyncio

        summary_task = self._request(
            "GET", f"{base}/v1/tokens/{mint}/report/summary"
        )
        full_task = self._request("GET", f"{base}/v1/tokens/{mint}/report")
        summary, full = await asyncio.gather(summary_task, full_task)

        if not summary or not isinstance(summary, dict):
            # Fall back to full report as summary
            if full and isinstance(full, dict) and full.get("mint"):
                summary = full
            else:
                return features

        if full and isinstance(full, dict) and not full.get("mint"):
            full = None

        # Core score — prefer score_normalised, fall back to score
        score = summary.get("score_normalised")
        if score is None or score == 0:
            score = summary.get("score")
        if score is not None:
            features["rc_score"] = score
            if score >= 800:
                features["rc_risk_level"] = "Good"
            elif score >= 400:
                features["rc_risk_level"] = "Warning"
            else:
                features["rc_risk_level"] = "Danger"

        # LP locked percentage
        lp_pct = summary.get("lpLockedPct")
        if lp_pct is not None:
            features["rc_lp_lock_pct"] = lp_pct
            features["rc_lp_locked"] = lp_pct > 0
            features["rc_lp_burned"] = lp_pct >= 100

        # Risks
        risks = summary.get("risks") or []
        features["rc_risk_count"] = len(risks)

        risk_names = " ".join(
            (r.get("name", "") + " " + r.get("description", "")).lower()
            for r in risks
        )
        features["rc_mint_authority_disabled"] = "mint authority" not in risk_names
        features["rc_freeze_authority_disabled"] = "freeze authority" not in risk_names
        features["rc_mutable_metadata"] = "mutable" in risk_names
        features["rc_single_holder_ownership"] = any(
            "single" in risk_names and "holder" in risk_names
            for _ in [1]
        )
        features["rc_high_concentration"] = "concentration" in risk_names
        features["rc_low_liquidity"] = "liquidity" in risk_names and "low" in risk_names
        features["rc_copycat_token"] = "copycat" in risk_names

        # Full report extras
        if full and isinstance(full, dict):
            # Top holders
            top_holders = full.get("topHolders") or []
            if top_holders:
                features["rc_top_holder_pct"] = top_holders[0].get("pct")
                total_top10 = sum(h.get("pct", 0) for h in top_holders[:10])
                features["rc_top10_holder_pct"] = total_top10

            # Markets
            markets = full.get("markets") or []
            features["rc_num_markets"] = len(markets)
            total_liq = 0
            max_lock_days = None
            for m in markets:
                liq = m.get("lp", {}).get("quoteUSD", 0) or 0
                total_liq += liq
                lock_end = m.get("lp", {}).get("lockEndTime")
                if lock_end and isinstance(lock_end, (int, float)) and lock_end > 0:
                    import time
                    remaining_days = (lock_end - time.time()) / 86400
                    if max_lock_days is None or remaining_days > max_lock_days:
                        max_lock_days = remaining_days
            features["rc_total_market_liquidity"] = total_liq if markets else None
            features["rc_lp_lock_duration_days"] = (
                round(max_lock_days, 1) if max_lock_days is not None else None
            )

        return features

    @staticmethod
    def _empty() -> dict:
        return {
            "rc_score": None,
            "rc_risk_level": None,
            "rc_risk_count": None,
            "rc_mint_authority_disabled": None,
            "rc_freeze_authority_disabled": None,
            "rc_mutable_metadata": None,
            "rc_top10_holder_pct": None,
            "rc_top_holder_pct": None,
            "rc_lp_locked": None,
            "rc_lp_lock_pct": None,
            "rc_lp_lock_duration_days": None,
            "rc_lp_burned": None,
            "rc_single_holder_ownership": None,
            "rc_high_concentration": None,
            "rc_low_liquidity": None,
            "rc_copycat_token": None,
            "rc_total_market_liquidity": None,
            "rc_num_markets": None,
        }
