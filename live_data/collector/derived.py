"""Compute 7 derived features from raw collected data. Pure computation, no I/O."""


def _safe_div(a, b, default=None):
    if a is None or b is None:
        return default
    try:
        return a / (b + 1)
    except (ZeroDivisionError, TypeError):
        return default


def compute_derived(features: dict) -> dict:
    derived = {}

    # 101: liquidity_to_fdv_ratio
    derived["liquidity_to_fdv_ratio"] = _safe_div(
        features.get("gt_reserve_usd"), features.get("gt_fdv_usd")
    )

    # 102: sell_pressure_score
    sells = features.get("gt_tx_count_1h_sells")
    buys = features.get("gt_tx_count_1h_buys")
    if sells is not None and buys is not None:
        derived["sell_pressure_score"] = sells / (buys + 1)
    else:
        derived["sell_pressure_score"] = None

    # 103: metadata_completeness
    meta_fields = [
        features.get("has_image"),
        features.get("has_description"),
        features.get("has_website"),
        features.get("has_twitter"),
        features.get("has_telegram"),
    ]
    if all(v is not None for v in meta_fields):
        derived["metadata_completeness"] = sum(bool(v) for v in meta_fields) / 5
    else:
        derived["metadata_completeness"] = None

    # 104: authority_risk_score (0-3)
    mint_rev = features.get("mint_authority_revoked")
    freeze_rev = features.get("freeze_authority_revoked")
    is_mut = features.get("is_mutable")
    if mint_rev is not None and freeze_rev is not None and is_mut is not None:
        derived["authority_risk_score"] = (
            int(not mint_rev) + int(not freeze_rev) + int(is_mut)
        )
    else:
        derived["authority_risk_score"] = None

    # 105: wallet_freshness_flag
    age = features.get("creator_wallet_age_hours")
    tx_count = features.get("creator_tx_count")
    if age is not None and tx_count is not None:
        derived["wallet_freshness_flag"] = age < 24 and tx_count < 10
    else:
        derived["wallet_freshness_flag"] = None

    # 106: consensus_risk — mean of normalized risk signals
    rc_score = features.get("rc_score")
    auth_risk = derived.get("authority_risk_score")
    top1 = features.get("rc_top_holder_pct")
    components = []
    if rc_score is not None:
        components.append(1 - rc_score / 1000)
    if auth_risk is not None:
        components.append(auth_risk / 3)
    if top1 is not None:
        components.append(top1 / 100)
    derived["consensus_risk"] = (
        sum(components) / len(components) if components else None
    )

    # 107: price_liquidity_divergence
    derived["price_liquidity_divergence"] = _safe_div(
        features.get("gt_fdv_usd"), features.get("gt_reserve_usd")
    )

    return derived
